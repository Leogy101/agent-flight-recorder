"""Run with a fresh wheel-only interpreter; no pytest or source import required."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Thread
from urllib.parse import urljoin
from urllib.request import urlopen

import agent_flight_recorder
from agent_flight_recorder import Recorder
from agent_flight_recorder.recording import load_recording
from agent_flight_recorder.server import make_server


def main():
    assert "site-packages" in str(Path(agent_flight_recorder.__file__).resolve())
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

    server = make_server()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
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
        server.shutdown()
        server.server_close()
        thread.join()
    print("Installed wheel: recording, privacy, validation, CLI and bundled assets passed.")


if __name__ == "__main__":
    main()
