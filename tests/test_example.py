"""Run the local workflow rather than asserting against assembled trace JSON."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from agent_flight_recorder.recording import load_recording, validate_events


EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "examples" / "record_agent.py"
SPEC = importlib.util.spec_from_file_location("executing_agent_example", EXAMPLE_PATH)
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)


def starts(events, kind):
    return [event for event in events if event["type"] == "span.started" and event["data"]["kind"] == kind]


def ending(events, span_id):
    return next(event for event in events if event["type"] == "span.ended" and event["span_id"] == span_id)


def payloads(events):
    return [event["data"][key] for event in events for key in ("input", "output", "payload") if key in event["data"]]


def test_success_executes_tool_calls_and_records_real_retry_order(tmp_path):
    output = tmp_path / "success.jsonl"
    original_catalog = example.ORDER_DATA.read_bytes()
    with patch.object(example, "lookup_order", wraps=example.lookup_order) as tool:
        result = example.run_scenario("success", output)
    assert result == {"order_id": "SYN-1001", "status": "shipped", "answer": "Synthetic order SYN-1001 is shipped.", "tool_attempts": 2}
    assert tool.call_count == 2
    assert tool.call_args_list[0].args[0] == {"order_id": 1001}
    assert tool.call_args_list[1].args[0] == {"order_id": "SYN-1001"}
    assert example.ORDER_DATA.read_bytes() == original_catalog
    captured = load_recording(output)
    assert captured["warnings"] == []
    events = captured["events"]
    first, second = starts(events, "tool")
    assert [first["data"]["attributes"]["attempt"], second["data"]["attributes"]["attempt"]] == [1, 2]
    assert second["data"]["attributes"]["retry_of"] == first["span_id"]
    assert second["data"]["links"] == [{"span_id": first["span_id"], "relation": "retry_of"}]
    first_end, second_end = ending(events, first["span_id"]), ending(events, second["span_id"])
    assert first_end["data"]["error"]["type"] == "InvalidToolArguments"
    assert first_end["data"]["status"] == "error"
    assert second_end["data"]["status"] == "ok"
    assert first["seq"] < first_end["seq"] < second["seq"] < second_end["seq"]
    assert first["elapsed_us"] <= first_end["elapsed_us"] <= second["elapsed_us"] <= second_end["elapsed_us"]
    root = starts(events, "run")[0]
    assert ending(events, root["span_id"])["data"]["status"] == "ok"
    assert all(event["parent_span_id"] == root["span_id"] for event in starts(events, "model") + starts(events, "tool"))
    assert all("usage" not in event["data"] for event in events)
    assert all(event["data"]["attributes"]["provider"] == "local-simulation" for event in starts(events, "model"))


def test_failure_executes_validation_retry_and_propagates_not_found(tmp_path):
    output = tmp_path / "failure.jsonl"
    with patch.object(example, "lookup_order", wraps=example.lookup_order) as tool:
        with pytest.raises(example.OrderNotFound):
            example.run_scenario("failure", output)
    assert tool.call_count == 2
    assert tool.call_args_list[1].args[0] == {"order_id": "SYN-4040"}
    captured = load_recording(output)
    assert captured["warnings"] == []
    events = captured["events"]
    first, second = starts(events, "tool")
    assert ending(events, first["span_id"])["data"]["error"]["type"] == "InvalidToolArguments"
    assert ending(events, second["span_id"])["data"]["error"]["type"] == "OrderNotFound"
    assert ending(events, starts(events, "run")[0]["span_id"])["data"]["status"] == "error"
    assert len(starts(events, "model")) == 2  # No answer generation after failure.
    assert events[-1]["type"] == "capture.ended"
    assert events[-1]["data"]["failed_events"] == 0  # Application error is not recorder failure.


def test_catalog_change_changes_actual_result_without_touching_original(tmp_path):
    catalog = json.loads(example.ORDER_DATA.read_text())
    catalog["orders"][0]["status"] = "awaiting pickup"
    changed = tmp_path / "catalog.json"
    changed.write_text(json.dumps(catalog))
    result = example.run_scenario("success", tmp_path / "changed.jsonl", data_path=changed)
    assert result["status"] == "awaiting pickup"
    assert result["answer"] == "Synthetic order SYN-1001 is awaiting pickup."
    assert json.loads(example.ORDER_DATA.read_text())["orders"][0]["status"] == "shipped"


def test_default_privacy_omits_inputs_outputs_and_sensitive_values(tmp_path):
    output = tmp_path / "default.jsonl"
    example.run_scenario("success", output)
    events = load_recording(output)["events"]
    assert events[0]["data"]["privacy_mode"] == "metadata_only"
    assert all(payload["state"] != "captured" for payload in payloads(events))
    text = output.read_text()
    for value in ("SYN-1001", example.SYNTHETIC_CREDENTIAL, example.SYNTHETIC_EMAIL, "SYNTHETIC-INTERNAL-NOTE-DO-NOT-SHARE"):
        assert value not in text


def test_selected_content_exposes_actual_argument_correction_but_redacts_private_fields(tmp_path):
    output = tmp_path / "selected.jsonl"
    example.run_scenario("success", output, capture_content=True)
    events = load_recording(output)["events"]
    assert events[0]["data"]["privacy_mode"] == "selected_content"
    first, second = starts(events, "tool")
    assert first["data"]["input"]["value"] == {"order_id": 1001}
    assert second["data"]["input"]["value"] == {"order_id": "SYN-1001"}
    result = ending(events, second["span_id"])["data"]["output"]
    assert result["value"]["status"] == "shipped"
    assert result["value"]["customer_email"] == "[REDACTED]"
    assert result["value"]["internal_note"] == "[REDACTED]"
    assert result["redacted_fields"] >= 2
    text = output.read_text()
    for value in (example.SYNTHETIC_CREDENTIAL, example.SYNTHETIC_EMAIL, "SYNTHETIC-INTERNAL-NOTE-DO-NOT-SHARE"):
        assert value not in text


def test_original_exception_identity_preserved_and_sensitive_messages_not_recorded(tmp_path, capsys):
    expected = example.OrderNotFound("PRIVATE-ERROR-MESSAGE")
    output = tmp_path / "failure.jsonl"
    with patch.object(example, "lookup_order", side_effect=[example.InvalidToolArguments("PRIVATE-VALIDATION-DETAIL"), expected]):
        with pytest.raises(example.OrderNotFound) as caught:
            example.run_scenario("failure", output, capture_content=True)
    assert caught.value is expected
    text = output.read_text()
    assert "PRIVATE-ERROR-MESSAGE" not in text
    assert "PRIVATE-VALIDATION-DETAIL" not in text
    assert "PRIVATE" not in capsys.readouterr().out


def test_bad_arguments_are_rejected_before_any_catalog_read(tmp_path):
    absent_catalog = tmp_path / "does-not-exist.json"
    for arguments in ({"order_id": 1001}, {"order_id": "invalid"}, {"order_id": "SYN-1001", "extra": True}, None):
        with pytest.raises(example.InvalidToolArguments):
            example.lookup_order(arguments, data_path=absent_catalog)


def test_example_never_overwrites_and_does_not_execute_on_existing_path(tmp_path):
    output = tmp_path / "existing.jsonl"
    output.write_text("keep this file")
    with patch.object(example, "lookup_order", wraps=example.lookup_order) as tool:
        with pytest.raises(FileExistsError):
            example.run_scenario("success", output)
    assert tool.call_count == 0
    assert output.read_text() == "keep this file"


def test_cli_runs_both_without_network_and_uses_new_directory(tmp_path, capsys):
    target = tmp_path / "new-recordings"
    with patch("socket.socket", side_effect=AssertionError("network access is forbidden")):
        assert example.main(["--output-dir", str(target), "--capture-content"]) == 0
    output = capsys.readouterr().out
    assert "deterministic provider stand-in" in output
    assert "expected OrderNotFound" in output
    assert example.SYNTHETIC_CREDENTIAL not in output
    assert example.SYNTHETIC_EMAIL not in output
    original = {path.name: path.read_bytes() for path in target.iterdir()}
    assert set(original) == {"success.jsonl", "failure.jsonl"}
    assert all(validate_events(load_recording(target / name)["events"]) == [] for name in original)
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o700
    assert example.main(["--output-dir", str(target)]) == 2
    assert original == {path.name: path.read_bytes() for path in target.iterdir()}


def test_default_cli_creates_a_temporary_directory(tmp_path, capsys):
    target = tmp_path / "created-temporary-directory"
    target.mkdir(mode=0o700)
    with patch.object(example.tempfile, "mkdtemp", return_value=str(target)) as create:
        assert example.main(["--scenario", "success"]) == 0
    create.assert_called_once_with(prefix="afr-agent-example-")
    assert (target / "success.jsonl").exists()
    assert not (target / "failure.jsonl").exists()
    assert str(target) in capsys.readouterr().out


def test_legacy_output_path_runs_one_success_and_refuses_overwrite(tmp_path):
    target = tmp_path / "nested" / "legacy.jsonl"
    assert example.main(["--output", str(target)]) == 0
    captured = load_recording(target)
    assert captured["warnings"] == []
    assert ending(captured["events"], starts(captured["events"], "run")[0]["span_id"])["data"]["status"] == "ok"
    original = target.read_bytes()
    assert example.main(["--output", str(target)]) == 2
    assert target.read_bytes() == original
    other = tmp_path / "both.jsonl"
    assert example.main(["--output", str(other), "--scenario", "both"]) == 2
    assert not other.exists()


def test_cli_does_not_print_unexpected_sensitive_exceptions(tmp_path, capsys):
    with patch.object(example, "run_scenario", side_effect=RuntimeError("PRIVATE-SETUP-ERROR")):
        assert example.main(["--output-dir", str(tmp_path / "failed")]) == 1
    assert "PRIVATE-SETUP-ERROR" not in capsys.readouterr().out


def test_cli_reports_missing_capture_separately_from_agent_result(tmp_path, capsys):
    with patch.object(example, "run_scenario", return_value={"answer": "Synthetic answer", "tool_attempts": 2}):
        assert example.main(["--scenario", "success", "--output-dir", str(tmp_path / "missing-capture")]) == 1
    assert "recording is unavailable" in capsys.readouterr().out


def test_script_entrypoint_works_from_another_directory(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(EXAMPLE_PATH.parents[1] / "src")
    completed = subprocess.run([sys.executable, str(EXAMPLE_PATH), "--output-dir", str(tmp_path / "cli"), "--scenario", "success"], cwd=tmp_path, env=environment, text=True, capture_output=True, check=False)
    assert completed.returncode == 0
    assert "Synthetic order SYN-1001 is shipped" in completed.stdout
    assert load_recording(tmp_path / "cli" / "success.jsonl")["warnings"] == []
