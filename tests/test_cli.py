import json
from pathlib import Path
from unittest.mock import patch

import pytest

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


def test_dense_otlp_container_is_rejected_before_json_allocation(tmp_path, capsys):
    source = tmp_path / "dense.json"
    source.write_text('{"resourceSpans":[' + ','.join('{}' for _ in range(100001)) + ']}')
    with patch("agent_flight_recorder.cli.json.loads", side_effect=AssertionError("decoder must not run")) as decode:
        assert main(["import-otlp", str(source), "--output", str(tmp_path / "out.jsonl")]) == 2
    decode.assert_not_called()
    assert "container item limit exceeded before decoding" in capsys.readouterr().err
    assert not (tmp_path / "out.jsonl").exists()


def test_total_tokens_are_bounded_across_individually_small_containers(tmp_path, capsys):
    source = tmp_path / "many-tokens.json"
    array = "[" + ",".join("0" for _ in range(90000)) + "]"
    source.write_text('{"resourceSpans":[],"a":' + array + ',"b":' + array + ',"c":' + array + '}')
    with patch("agent_flight_recorder.cli.json.loads", side_effect=AssertionError("decoder must not run")) as decode:
        assert main(["import-otlp", str(source), "--output", str(tmp_path / "out.jsonl")]) == 2
    decode.assert_not_called()
    assert "token limit exceeded before decoding" in capsys.readouterr().err


def test_deep_otlp_is_rejected_before_json_allocation(tmp_path, capsys):
    source = tmp_path / "deep.json"
    source.write_text("[" * 21 + "0" + "]" * 21)
    with patch("agent_flight_recorder.cli.json.loads", side_effect=AssertionError("decoder must not run")) as decode:
        assert main(["import-otlp", str(source), "--output", str(tmp_path / "out.jsonl")]) == 2
    decode.assert_not_called()
    assert "nesting limit exceeded before decoding" in capsys.readouterr().err


def test_preflight_ignores_escaped_string_structure_and_accepts_depth_boundary(tmp_path):
    source = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "otlp-example.json").read_text())
    source["ignoredString"] = '\\"}],[{: escaped backslash \\\\ and a quote " and newline\n' * 100
    nested = 0
    for _ in range(19):
        nested = [nested]
    source["ignoredNested"] = nested  # Root object + 19 arrays = 20 levels.
    path = tmp_path / "valid.json"
    path.write_text(json.dumps(source), encoding="utf-8-sig")
    assert main(["import-otlp", str(path), "--output", str(tmp_path / "valid.jsonl")]) == 0


def test_preflight_counts_keys_and_preserves_valid_json_text():
    from agent_flight_recorder._json_preflight import preflight_json
    # Tokens: {, key, :, value, } = 5. This is intentionally more conservative
    # than the later semantic traversal, which counts values but not key tokens.
    with patch("agent_flight_recorder._json_preflight.MAX_JSON_TOKENS", 4):
        with pytest.raises(ValueError, match="token limit"):
            preflight_json(b'{"key":"value"}')
    with patch("agent_flight_recorder._json_preflight.MAX_JSON_TOKENS", 5):
        assert preflight_json(b'{"key":"value"}') == '{"key":"value"}'
    for value in (None, True, 1, 1.25e-9, "quotes: \\\" brackets: [{]}", [], {}, {"a": [1, {"b": "c"}], "d": False}):
        encoded = json.dumps(value, ensure_ascii=False).encode()
        assert json.loads(preflight_json(encoded)) == value
    with patch("agent_flight_recorder._json_preflight.MAX_CONTAINER_ITEMS", 2):
        assert json.loads(preflight_json(b'{"a":1,"b":[1,2]}')) == {"a": 1, "b": [1, 2]}
        with pytest.raises(ValueError, match="container item"):
            preflight_json(b'{"a":1,"b":2,"c":3}')


def test_preflight_invalid_encoding_and_string_never_echo_payload(tmp_path, capsys):
    for number, raw in enumerate((b'{"PRIVATE": "unterminated', '{"PRIVATE":true}'.encode("utf-16"))):
        source = tmp_path / f"bad-{number}.json"
        source.write_bytes(raw)
        with patch("agent_flight_recorder.cli.json.loads", side_effect=AssertionError("decoder must not run")) as decode:
            assert main(["import-otlp", str(source), "--output", str(tmp_path / f"bad-{number}.jsonl")]) == 2
        decode.assert_not_called()
        assert "PRIVATE" not in capsys.readouterr().err
