import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from agent_flight_recorder.demo import demo_events
from agent_flight_recorder.recording import validate_events, load_recording, write_recording

ROOT = Path(__file__).resolve().parents[1]


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(json.loads((ROOT / "schema/event.schema.json").read_text()))


@pytest.mark.parametrize("scenario", ["success", "failure", "interrupted"])
def test_synthetic_fixtures_conform_and_roundtrip(tmp_path, scenario):
    validator = Draft202012Validator(json.loads((ROOT / "schema/event.schema.json").read_text()), format_checker=FormatChecker())
    events = demo_events(scenario)
    for event in events:
        validator.validate(event)
    path = tmp_path / f"{scenario}.jsonl"
    write_recording(events, path)
    result = load_recording(path)
    assert result["events"] == events
    assert bool(result["warnings"]) is (scenario == "interrupted")
    assert demo_events(scenario) == events


def test_schema_rejects_payload_leaking_omitted_value():
    validator = Draft202012Validator(json.loads((ROOT / "schema/event.schema.json").read_text()))
    event = demo_events("success")[1]
    event["data"]["input"] = {"state": "omitted", "value": "SHOULD_NOT_BE_HERE"}
    assert list(validator.iter_errors(event))


def test_synthetic_fixture_ids_are_distinct():
    assert len({demo_events(name)[0]["trace_id"] for name in ("success", "failure", "interrupted")}) == 3


@pytest.mark.parametrize("defect", ["empty_source", "parent_on_end", "unknown_usage", "invalid_reconstructed"])
def test_schema_rejects_confirmed_consumer_contract_violations(defect):
    validator = Draft202012Validator(json.loads((ROOT / "schema/event.schema.json").read_text()), format_checker=FormatChecker())
    events = demo_events("success")
    if defect == "empty_source":
        event = events[0]
        event["data"]["source"] = {}
    elif defect == "parent_on_end":
        event = next(event for event in events if event["type"] == "span.ended")
        event["parent_span_id"] = "a" * 16
    elif defect == "unknown_usage":
        event = next(event for event in events if event["type"] == "span.ended")
        event["data"]["usage"] = {"input_tokens": 1, "unknown": 2}
    else:
        event = events[0]
        event["data"]["reconstructed"] = "yes"
    assert list(validator.iter_errors(event))
    with pytest.raises(ValueError):
        validate_events(events)


@pytest.mark.parametrize("scenario", ["success", "failure"])
def test_reviewed_executed_samples_conform_without_private_values(scenario):
    path = ROOT / "fixtures" / f"agent-example-{scenario}.jsonl"
    captured = load_recording(path)
    assert captured["warnings"] == []
    validator = Draft202012Validator(json.loads((ROOT / "schema/event.schema.json").read_text()), format_checker=FormatChecker())
    for event in captured["events"]:
        validator.validate(event)
    text = path.read_text()
    for forbidden in ("EXAMPLE-ONLY-FAKE-CREDENTIAL", "synthetic.customer@example.invalid", "SYNTHETIC-INTERNAL-NOTE-DO-NOT-SHARE"):
        assert forbidden not in text


def test_independent_typescript_and_otlp_schema_conformance():
    from agent_flight_recorder.otlp import convert_otlp
    validator = Draft202012Validator(json.loads((ROOT / "schema/event.schema.json").read_text()), format_checker=FormatChecker())
    independent = load_recording(ROOT / "fixtures/typescript-example.jsonl")
    assert independent["warnings"] == []
    converted = convert_otlp(json.loads((ROOT / "fixtures/otlp-example.json").read_text()))
    for event in [*independent["events"], *converted]:
        validator.validate(event)
    assert "SYNTHETIC-PAYLOAD-OMITTED-BY-DEFAULT" not in json.dumps(converted)
