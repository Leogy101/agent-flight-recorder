from contextlib import contextmanager
import json
import signal
import subprocess
import sys
import time

import pytest

from installed_smoke import (
    BOOTSTRAP,
    ChildOutput,
    STARTUP_URL,
    OUTPUT_LIMIT,
    SmokeFailure,
    check_cli_process,
    cli_restart_check,
    safe_output,
)


REGISTER = "import faulthandler,signal;faulthandler.register(signal.SIGUSR1);"


def failing_child(source, *, timeout=10):
    with pytest.raises(SmokeFailure) as caught:
        check_cli_process([sys.executable, "-c", REGISTER + source], 2, startup_timeout=timeout)
    return json.loads(str(caught.value))


def test_early_exit_reports_status_and_omits_arbitrary_stderr():
    result = failing_child("import sys;sys.stderr.write('SYNTHETIC-SECRET /private/machine/file\\n');sys.exit(7)")
    assert result["stage"] == "startup" and result["reason"] == "exited"
    assert result["exception_type"] == "AssertionError"
    assert result["attempt"] == 2
    assert result["returncode_before_cleanup"] == result["returncode_after_cleanup"] == 7
    assert result["cleanup"] == "not_needed"
    assert result["output"]["stderr"]["bytes"] > 0
    assert result["output"]["stderr"]["safe_text"] == "[1 unrecognized lines omitted]"
    assert "SYNTHETIC-SECRET" not in json.dumps(result)
    assert "/private/machine" not in json.dumps(result)


@contextmanager
def running_child(source):
    process = subprocess.Popen([sys.executable, "-c", REGISTER + source], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = ChildOutput(process)
    try:
        yield process, output
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        output.final_drain()
        output.close()


@pytest.mark.parametrize("prefix", ["", "Agent Flight Recorder: http://127.0.0.1:12345/"])
def test_silent_and_partial_line_startup_have_bounded_deadline(prefix):
    source = f"import sys,time;sys.stdout.write({prefix!r});sys.stdout.flush();sys.stderr.write('READY\\n');sys.stderr.flush();time.sleep(5)"
    with running_child(source) as (_, output):
        assert output.wait(lambda: b"READY" in output.data["stderr"], 10) == "ready"
        started = time.monotonic()
        assert output.wait(lambda: STARTUP_URL.search(output.data["stdout"]), 0.15) == "deadline"
        assert time.monotonic() - started < 2


def test_excessive_stderr_is_drained_bounded_and_sanitized():
    source = ("import os,time;"
              "data=b'SYNTHETIC-SECRET /private/machine/file\\n'*6000;"
              "os.write(2,data);os.write(2,b'READY\\n');time.sleep(5)")
    with running_child(source) as (_, output):
        assert output.wait(lambda: b"READY" in output.data["stderr"], 10) == "ready"
        result = output.summary()
    assert result["stderr"]["bytes"] > OUTPUT_LIMIT
    assert result["stderr"]["truncated"]
    assert len(result["stderr"]["safe_text"]) <= OUTPUT_LIMIT
    encoded = json.dumps(result)
    assert len(encoded) < OUTPUT_LIMIT * 2 + 2000
    assert "SYNTHETIC-SECRET" not in encoded and "/private/machine" not in encoded
    assert "omitted" in result["stderr"]["safe_text"]


def test_failure_stack_retains_location_without_machine_path():
    blocked = "import sys,time\ndef blocked_startup():\n    sys.stderr.write('READY\\n');sys.stderr.flush()\n    time.sleep(5)\nblocked_startup()"
    with running_child(f"exec(compile({blocked!r}, '/private/synthetic-host/socket.py', 'exec'))") as (process, output):
        assert output.wait(lambda: b"READY" in output.data["stderr"], 10) == "ready"
        process.send_signal(signal.SIGUSR1)
        # Faulthandler writes a frame in chunks; a filename alone is not a frame.
        assert output.wait(lambda: "frame socket.py:4 in blocked_startup" in
                           output.summary()["stderr"]["safe_text"], 10) == "ready"
        text = output.summary()["stderr"]["safe_text"]
    assert "frame socket.py:4 in blocked_startup" in text
    assert "/private" not in text and "synthetic-host" not in text


def test_output_allowlist_and_environment_do_not_echo_unrelated_values(monkeypatch):
    monkeypatch.setenv("AFR_SYNTHETIC_TOKEN", "SYNTHETIC-SECRET")
    monkeypatch.setenv("AFR_SYNTHETIC_PATH", "/private/machine/file")
    result = failing_child("import sys;sys.exit(9)")
    assert set(result["environment"]) == {"os", "python", "selector"}
    assert "SYNTHETIC-SECRET" not in json.dumps(result)
    assert "/private/machine" not in json.dumps(result)
    text = safe_output(
        b'Agent Flight Recorder: http://127.0.0.1:12345/\n'
        b'Press Ctrl+C to stop.\n'
        b'  File "/private/machine/socket.py", line 789 in getfqdn\n'
        b'  File "<frozen runpy>", line 198 in _run_module_as_main\n'
        b'SYNTHETIC-SECRET\n'
        b'ModuleNotFoundError: SYNTHETIC-SECRET /private/machine/file\n')
    assert "http://127.0.0.1:12345/" in text
    assert "frame socket.py:789 in getfqdn" in text
    assert "frame <frozen runpy>:198 in _run_module_as_main" in text
    assert "/private" not in text and "SYNTHETIC-SECRET" not in text
    assert "ModuleNotFoundError: [message omitted]" in text


def test_real_cli_http_sigint_and_same_port_restart(capsys):
    assert "dump_traceback_later" not in BOOTSTRAP
    cli_restart_check()
    stages = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [(entry["attempt"], entry["stage"]) for entry in stages] == [
        (attempt, stage) for attempt in (1, 2) for stage in ("startup", "http", "sigint_shutdown")]
    assert all(entry["passed"] for entry in stages)
