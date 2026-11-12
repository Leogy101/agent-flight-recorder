"""Run with a fresh wheel-only interpreter; no pytest or source import required."""

from contextlib import contextmanager
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Thread
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

import agent_flight_recorder
from agent_flight_recorder import Recorder
from agent_flight_recorder.recording import load_recording
from agent_flight_recorder.server import make_server


OUTPUT_LIMIT = 8192
STARTUP_URL = re.compile(rb"(?m)^Agent Flight Recorder: (http://127\.0\.0\.1:[0-9]{1,5}/)\r?\n")
BOOTSTRAP = (
    "import faulthandler,signal;"
    "faulthandler.register(signal.SIGUSR1);"
    "import runpy;"
    "runpy.run_module('agent_flight_recorder',run_name='__main__')"
)


class SmokeFailure(AssertionError):
    """Contains only bounded, explicitly sanitized diagnostic JSON."""


@contextmanager
def timed_stage(stage, attempt=None):
    started, passed = time.monotonic(), False
    try:
        yield
        passed = True
    finally:
        print(json.dumps({"stage": stage, "attempt": attempt, "passed": passed,
                          "elapsed_s": round(time.monotonic() - started, 3)}), flush=True)


def safe_output(raw):
    """Retain known CLI text and stack locations, never arbitrary child text."""
    safe, omitted = [], 0
    known = {
        "Open a recording in the browser. Files stay in browser memory.",
        "Press Ctrl+C to stop.",
        "Error: unable to access file or bind local viewer; check path, permissions, and port",
        "Error: Viewer assets are missing. Build the viewer before packaging.",
    }
    for line in raw.decode("utf-8", "replace").splitlines():
        frame = re.fullmatch(r'\s*File "([^"\r\n]+)", line ([0-9]{1,7}),? in ([A-Za-z_<][A-Za-z0-9_.<>]{0,80})', line)
        if line in known or re.fullmatch(r"Agent Flight Recorder: http://127\.0\.0\.1:[0-9]{1,5}/", line):
            safe.append(line)
        elif frame:
            basename = re.split(r"[/\\]", frame[1])[-1]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\.py|<frozen [A-Za-z_.]{1,64}>", basename):
                safe.append(f"frame {basename}:{frame[2]} in {frame[3]}")
            else:
                omitted += 1
        elif re.fullmatch(r"Timeout \([0-9:.]+\)!", line):
            safe.append("faulthandler deadline snapshot")
        elif exception := re.fullmatch(r"(ModuleNotFoundError|ImportError|OSError|ValueError|RuntimeError|KeyboardInterrupt|AssertionError|TimeoutError|PermissionError|FileNotFoundError)(?::.*)?", line):
            safe.append(f"{exception[1]}: [message omitted]")
        elif line:
            omitted += 1
    if omitted:
        safe.append(f"[{omitted} unrecognized lines omitted]")
    return "\n".join(safe)[:OUTPUT_LIMIT]


class ChildOutput:
    """Drain both pipes while retaining only a bounded tail from each."""

    def __init__(self, process):
        self.process = process
        self.selector = selectors.DefaultSelector()
        self.data = {"stdout": bytearray(), "stderr": bytearray()}
        self.total = {"stdout": 0, "stderr": 0}
        for name in self.data:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, name)

    def drain(self, timeout=0):
        ready = self.selector.select(timeout)
        for key, _ in ready:
            try:
                chunk = os.read(key.fd, OUTPUT_LIMIT)
            except BlockingIOError:
                continue
            if not chunk:
                self.selector.unregister(key.fileobj)
                continue
            self.total[key.data] += len(chunk)
            self.data[key.data].extend(chunk)
            del self.data[key.data][:-OUTPUT_LIMIT]
        return bool(ready)

    def wait(self, predicate, timeout, *, stop_on_exit=False):
        deadline = time.monotonic() + timeout
        while True:
            if predicate():
                return "ready"
            if stop_on_exit and self.process.poll() is not None:
                self.final_drain()
                return "exited"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "deadline"
            self.drain(min(remaining, 0.05))

    def final_drain(self):
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline and self.drain():
            pass

    def summary(self):
        return {name: {"bytes": self.total[name], "truncated": self.total[name] > OUTPUT_LIMIT,
                       "safe_text": safe_output(data)} for name, data in self.data.items()}

    def close(self):
        self.selector.close()
        self.process.stdout.close()
        self.process.stderr.close()


def check_cli_process(command, attempt, expected_port=0, *, startup_timeout=10):
    stage, started, output, process = "spawn", time.monotonic(), None, None
    failure, reason, before, cleanup, stack_request = False, "exception", None, "not_needed", "not_needed"
    exception_type = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = ChildOutput(process)
        stage = "startup"
        with timed_stage(stage, attempt):
            reason = output.wait(lambda: STARTUP_URL.search(output.data["stdout"]), startup_timeout, stop_on_exit=True)
            assert reason == "ready"
            reason = "invalid_startup_url_or_port"
            url = STARTUP_URL.search(output.data["stdout"])[1].decode("ascii")
            port = urlsplit(url).port
            assert port and (not expected_port or port == expected_port)
        stage, reason = "http", "http_failed"
        with timed_stage(stage, attempt):
            with urlopen(url, timeout=3) as response:
                assert response.status == 200
        stage, reason = "sigint_shutdown", "shutdown_failed"
        with timed_stage(stage, attempt):
            process.send_signal(signal.SIGINT)
            reason = output.wait(lambda: process.poll() is not None, 10)
            assert reason == "ready"
            output.final_drain()
            reason = "unclean_exit"
            assert process.returncode == 0 and not output.total["stderr"]
        return port
    except Exception as error:
        failure = True
        exception_type = type(error).__name__
    finally:
        before = process.poll() if process else None
        if process and before is None:
            if failure and stage == "startup" and output:
                try:
                    process.send_signal(signal.SIGUSR1)
                    stack_request = "SIGUSR1_sent_after_failure"
                    output.wait(lambda: False, 0.25, stop_on_exit=True)
                except OSError:
                    stack_request = "signal_unavailable"
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                cleanup = "killed"
            except subprocess.TimeoutExpired:
                cleanup = "kill_timeout"
            except OSError:
                cleanup = "cleanup_unavailable"
        if output:
            output.final_drain()
            diagnostic = output.summary()
            selector = type(output.selector).__name__
            output.close()
        else:
            diagnostic, selector = {}, None
    if failure:
        raise SmokeFailure(json.dumps({"attempt": attempt, "stage": stage, "reason": reason,
            "exception_type": exception_type,
            "elapsed_s": round(time.monotonic() - started, 3), "startup_timeout_s": startup_timeout,
            "returncode_before_cleanup": before, "returncode_after_cleanup": process.poll() if process else None,
            "cleanup": cleanup, "stack_request": stack_request,
            "environment": {"os": sys.platform, "python": list(sys.version_info[:3]),
            "selector": selector}, "output": diagnostic})) from None


def cli_restart_check():
    """A real Ctrl+C must close the listener so the same port can be reused."""
    port = 0
    for attempt in (1, 2):
        port = check_cli_process(
            [sys.executable, "-c", BOOTSTRAP, "view", "--no-open", "--port", str(port)], attempt, port)


def main():
    assert "site-packages" in str(Path(agent_flight_recorder.__file__).resolve())
    with timed_stage("recording_validation_import"):
        with tempfile.TemporaryDirectory(prefix="afr-installed-") as directory:
            path = Path(directory) / "run.jsonl"
            with Recorder(path) as recorder:
                with recorder.run("Installed smoke test", input={"api_key": "SYNTHETIC-PRIVATE-MARKER"}):
                    with recorder.span("tool", "Local calculation") as span:
                        span.set_output({"result": 2 + 2})
            assert not recorder.health["failed_events"]
            assert not recorder.health["skipped_events"]
            assert "SYNTHETIC-PRIVATE-MARKER" not in path.read_text()
            result = load_recording(path)
            assert len(result["events"]) == 6 and not result["warnings"]
            subprocess.run([sys.executable, "-m", "agent_flight_recorder", "validate", str(path)], check=True)

            imported = Path(directory) / "imported.jsonl"
            fixture = Path(__file__).resolve().parents[1] / "fixtures/otlp-example.json"
            subprocess.run([sys.executable, "-m", "agent_flight_recorder", "import-otlp", str(fixture), "--output", str(imported)], check=True, capture_output=True)
            converted = load_recording(imported)
            assert converted["events"][0]["data"]["capture_mode"] == "imported_completed_spans"
            assert "SYNTHETIC-PAYLOAD-OMITTED-BY-DEFAULT" not in imported.read_text()
            for event in converted["events"]:
                if event["type"].startswith("span."):
                    assert event["data"]["reconstructed"] is True
                    assert "elapsed_us" not in event
    with timed_stage("in_process_server_create"):
        server = make_server()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with timed_stage("in_process_http"):
            url = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(url + "/", timeout=3) as response:
                assert response.status == 200
                assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
                html = response.read().decode()
            assets = re.findall(r'(?:src|href)="(\.?/assets/[^\"]+)"', html)
            assert any(path.endswith(".js") for path in assets)
            assert any(path.endswith(".css") for path in assets)
            logo = list(Path(agent_flight_recorder.__file__).parent.glob("static/assets/agent-flight-recorder-*.png"))
            assert len(logo) == 1
            assets.append("/assets/" + logo[0].name)
            for asset in [*assets, "/demo-failure.jsonl", "/third-party-notices.txt"]:
                with urlopen(urljoin(url + "/", asset), timeout=3) as response:
                    assert response.status == 200 and response.read()
    finally:
        with timed_stage("in_process_shutdown"):
            server.shutdown()
            server.server_close()
            thread.join()
    cli_restart_check()
    print("Installed wheel: recording, privacy, OTLP, validation, CLI restart and bundled assets passed.")


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as failure:
        print(str(failure), file=sys.stderr)
        sys.exit(1)
