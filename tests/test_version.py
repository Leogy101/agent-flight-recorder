"""Keep release metadata distinct from the historical recording contract."""

import json
from pathlib import Path
import tomllib

import pytest

from agent_flight_recorder import Recorder, __version__
from agent_flight_recorder._version import DISPLAY_VERSION
from agent_flight_recorder.cli import main


ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_agrees_across_python_and_frontend():
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())
    frontend = json.loads((ROOT / "viewer/package.json").read_text())
    lock = json.loads((ROOT / "viewer/package-lock.json").read_text())
    assert package["project"]["version"] == __version__ == "0.1.0a1"
    assert frontend["version"] == lock["version"] == lock["packages"][""]["version"] == DISPLAY_VERSION == "0.1.0-alpha.1"


def test_cli_uses_human_release_display(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    assert capsys.readouterr().out.strip() == f"Agent Flight Recorder {DISPLAY_VERSION}"


def test_new_capture_has_package_provenance_and_unchanged_schema(tmp_path):
    path = tmp_path / "version.jsonl"
    with Recorder(path) as recorder:
        with recorder.run("synthetic version check"):
            pass
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert {event["schema_version"] for event in events} == {"0.1"}
    assert events[0]["data"]["recorder_version"] == __version__
