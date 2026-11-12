import json
from pathlib import Path

from agent_flight_recorder.cli import main


def test_demo_then_validate_and_no_overwrite(tmp_path, capsys):
    destination = tmp_path / "demo"
    assert main(["demo", "--output", str(destination)]) == 0
    assert main(["validate", str(destination / "demo-success.jsonl")]) == 0
    assert main(["validate", str(destination / "demo-interrupted.jsonl")]) == 1
    before = (destination / "demo-success.jsonl").read_bytes()
    assert main(["demo", "--output", str(destination)]) == 2
    assert (destination / "demo-success.jsonl").read_bytes() == before


def test_invalid_json_errors_do_not_echo_payload(tmp_path, capsys):
    source = tmp_path / "bad.json"
    source.write_text('{"SECRET-DO-NOT-ECHO": invalid}')
    assert main(["import-otlp", str(source), "--output", str(tmp_path / "converted.jsonl")]) == 2
    assert "SECRET-DO-NOT-ECHO" not in capsys.readouterr().err
    assert not (tmp_path / "converted.jsonl").exists()


def test_bad_port_and_missing_path(capsys):
    assert main(["view", "--no-open", "--port", "-1"]) == 2
    assert main(["validate", "/missing-recording-for-afr-test.jsonl"]) == 2


def test_duplicate_json_keys_are_not_silently_replaced(tmp_path, capsys):
    source = tmp_path / "duplicate.json"
    source.write_text('{"resourceSpans":[],"resourceSpans":[]}')
    assert main(["import-otlp", str(source), "--output", str(tmp_path / "out.jsonl")]) == 2
    assert "Duplicate JSON key" in capsys.readouterr().err
