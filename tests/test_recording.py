import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from agent_flight_recorder.recording import load_recording, timestamp_ns, validate_events, write_recording


def recording():
    recording_id = str(uuid4())
    payload = {"state": "omitted", "reason": "policy"}
    data = [
        ("capture.started", {"recorder_version": "0.1", "capture_mode": "native_lifecycle", "privacy_mode": "metadata_only", "coverage": "explicit boundaries", "limits": {"max_file_bytes": 25 * 1024 * 1024, "max_events": 10000, "max_event_bytes": 65536, "max_payload_bytes": 8192, "max_depth": 20}}),
        ("span.started", {"kind": "run", "name": "run", "input": payload}),
        ("span.ended", {"status": "ok", "output": payload}),
        ("capture.ended", {"written_events": 4, "skipped_events": 0, "failed_events": 0, "limit_reached": False}),
    ]
    events = []
    for seq, (kind, fields) in enumerate(data, 1):
        event = {"schema_version": "0.1", "recording_id": recording_id, "trace_id": "1" * 32, "event_id": str(uuid4()), "seq": seq, "type": kind, "recorded_at": "2026-11-12T12:00:00Z", "elapsed_us": seq, "data": copy.deepcopy(fields)}
        if kind.startswith("span."):
            event["span_id"] = "2" * 16
        events.append(event)
    return events


def encoded(events):
    return "".join(json.dumps(event) + "\n" for event in events)


def codes(events):
    return {warning["code"] for warning in validate_events(events)}


class RecordingTests(unittest.TestCase):
    def test_valid_round_trip_and_exclusive_owner_only_write(self):
        events = recording()
        self.assertEqual(validate_events(events), [])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "run.jsonl"
            write_recording(events, target)
            self.assertEqual(load_recording(target)["events"], events)
            if os.name == "posix":
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            original = target.read_bytes()
            with self.assertRaises(FileExistsError):
                write_recording(events, target)
            self.assertEqual(target.read_bytes(), original)

    def test_real_recorder_output_conforms_to_reader_for_deep_content_and_retries(self):
        from agent_flight_recorder import Limits, Recorder
        for max_depth in (3, 20):
            with self.subTest(max_depth=max_depth), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "native.jsonl"
                deep = {"token": "fake-secret", "value": [1, 2, 3]}
                for _ in range(18):
                    deep = {"nested": deep}
                with Recorder(target, capture_content=True, limits=Limits(max_depth=max_depth)) as recorder:
                    with recorder.run("test run"):
                        with recorder.span("tool", "first attempt", input=deep) as first:
                            first.set_output({"safe": True, "api_key": "fake-secret"})
                        with recorder.span("tool", "second attempt", attributes={"attempt": 2, "retry_of": first.span_id}, links=[{"span_id": first.span_id, "relation": "retry_of"}]) as second:
                            second.set_usage(input_tokens=12, output_tokens=3)
                            second.event("observation", payload={"safe": "content"})
                result = load_recording(target)
                self.assertEqual(result["warnings"], [])
                self.assertNotIn("fake-secret", target.read_text())
                self.assertEqual(recorder.health["warnings"], [])

    def test_preflight_does_not_create_invalid_output(self):
        events = recording()
        events[2]["data"]["status"] = "made_up"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "invalid.jsonl"
            with self.assertRaises(ValueError):
                write_recording(events, target)
            self.assertFalse(target.exists())

    def test_truncated_last_line_and_middle_acknowledgement(self):
        events = recording()
        result = load_recording(encoded(events[:3]) + '{"schema_version":', from_text=True)
        self.assertTrue(result["partial"])
        self.assertEqual(len(result["events"]), 3)
        self.assertIn("partial_trailing_line", {item["code"] for item in result["warnings"]})
        middle = encoded(events[:2]) + "not-json-secret\n" + encoded(events[2:])
        with self.assertRaisesRegex(ValueError, "line 3") as error:
            load_recording(middle, from_text=True)
        self.assertNotIn("secret", str(error.exception))
        result = load_recording(middle, from_text=True, allow_partial=True)
        self.assertTrue(result["partial"])
        self.assertEqual(result["warnings"][0]["line"], 3)
        self.assertEqual(len(result["events"]), 4)

    def test_bad_final_line_is_not_assumed_to_be_a_crash(self):
        for text in ("not json", '{"x":1} rubbish', '{"x":1}\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_recording(text, from_text=True)
        with self.assertRaises(ValueError):
            load_recording(encoded(recording()) + "broken\n", from_text=True)

    def test_trailing_partial_escapes_numbers_and_utf8_are_recoverable(self):
        prefix = encoded(recording()[:3])
        for suffix in ('{"x":"\\u26', '{"x":1e-', '{"x":tru'):
            with self.subTest(suffix=suffix):
                result = load_recording(prefix + suffix, from_text=True)
                self.assertTrue(result["partial"])
                self.assertEqual(len(result["events"]), 3)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "partial.jsonl"
            target.write_bytes(prefix.encode() + b'{"x":"\xe2\x80')
            result = load_recording(target)
            self.assertTrue(result["partial"])
            target.write_bytes(prefix.encode() + b'{"x":"\xff')
            with self.assertRaisesRegex(ValueError, "UTF-8"):
                load_recording(target)

    def test_schema_and_limit_errors_never_disappear_in_partial_mode(self):
        events = recording()
        for mutation in (
            lambda event: event.update(schema_version="2.0"),
            lambda event: event.update(seq=True),
            lambda event: event.update(seq=2**53),
            lambda event: event.update(trace_id="0" * 32),
            lambda event: event.update(recorded_at="2026-02-30T00:00:00Z"),
            lambda event: event["data"].update(capture_mode=[]),
        ):
            event = copy.deepcopy(events[0])
            mutation(event)
            with self.subTest(event=event), self.assertRaises(ValueError):
                load_recording(encoded([event]), from_text=True, allow_partial=True)
        with patch("agent_flight_recorder.recording.MAX_EVENTS", 3), self.assertRaisesRegex(ValueError, "count limit"):
            load_recording(encoded(events), from_text=True)
        with patch("agent_flight_recorder.recording.MAX_FILE_BYTES", 20), self.assertRaisesRegex(ValueError, "size limit"):
            load_recording(encoded(events), from_text=True)
        with self.assertRaisesRegex(ValueError, "nesting"):
            load_recording("[" * 21 + "]" * 21, from_text=True, allow_partial=True)

    def test_untrusted_json_numbers_duplicate_keys_and_oversize_payload(self):
        for text in ('{"x":NaN}', '{"x":Infinity}', '{"x":999999999999999999999}', '{"x":1,"x":2}', '{"x":1e100}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_recording(text, from_text=True, allow_partial=True)
        events = recording()
        events[1]["data"]["input"] = {"state": "captured", "value": "x" * 8192}
        with self.assertRaisesRegex(ValueError, "Payload size"):
            validate_events(events)

    def test_schema_alignment_limits_links_retry_ids_and_uuid(self):
        for mutate in (
            lambda events: events[0]["data"]["limits"].update(max_depth=21),
            lambda events: events[1]["data"].update(attributes={"retry_of": "not-a-span"}),
            lambda events: events[1]["data"].update(links=[{"span_id": "3" * 16, "relation": "retry_of"}] * 65),
            lambda events: events[1].update(event_id="12345678123412341234123456789012----"),
        ):
            events = recording()
            mutate(events)
            with self.assertRaises(ValueError):
                validate_events(events)

    def test_bounded_traversal_is_lazy_and_stops_at_work_limits(self):
        from agent_flight_recorder.recording import _bounded_json
        with self.assertRaisesRegex(ValueError, "container item"):
            _bounded_json([None] * 100001)
        with patch("agent_flight_recorder.recording.MAX_JSON_NODES", 10), self.assertRaisesRegex(ValueError, "traversal"):
            _bounded_json([[None] * 4] * 4)
        cycle = []
        cycle.append(cycle)
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            _bounded_json(cycle)
        shared = [1, 2]
        _bounded_json([shared, shared])

    def test_duplicate_event_conflicts_sequences_and_capture_summary(self):
        events = recording()
        events.insert(2, copy.deepcopy(events[1]))
        self.assertIn("duplicate_event", codes(events))
        self.assertNotIn("duplicate_span_start", codes(events))
        events[2]["data"]["name"] = "changed"
        self.assertIn("conflicting_duplicate", codes(events))
        events = recording()
        events[1]["seq"] = 9
        self.assertTrue({"sequence_gap", "sequence_order"}.issubset(codes(events)))
        events[1]["seq"] = 3
        self.assertIn("duplicate_sequence", codes(events))

    def test_missing_closure_root_and_open_spans_are_distinct(self):
        events = recording()
        self.assertEqual(codes(events[:-1]), {"missing_capture_end"})
        missing_end = [events[0], events[1], events[3]]
        issues = codes(missing_end)
        self.assertTrue({"missing_span_end", "missing_root_end", "capture_closed_with_open_spans", "sequence_gap", "capture_count_mismatch"}.issubset(issues))
        self.assertEqual(missing_end[1]["data"].get("status"), None)

    def test_capture_health_counts_are_evidence_even_with_complete_spans(self):
        events = recording()
        events[-1]["data"].update(failed_events=3, skipped_events=2, limit_reached=True)
        issues = codes(events)
        self.assertEqual(issues, {"recording_loss", "capture_limit_reached"})
        self.assertEqual(events[2]["data"]["status"], "ok")

    def test_metadata_policy_mismatch_is_detected_and_preserved_in_exports(self):
        events = recording()
        events[1]["data"]["input"] = {"state": "captured", "value": None}
        self.assertIn("privacy_mismatch", codes(events))
        events[0]["data"]["privacy_mode"] = "selected_content"
        self.assertNotIn("privacy_mismatch", codes(events))
        reduced = recording()
        reduced[0]["data"]["transform"] = {"kind": "reduced_share", "version": "0.1", "source_issues": ["privacy_mismatch"]}
        self.assertEqual(codes(reduced), {"privacy_mismatch", "reduced_share"})

    def test_imported_events_cannot_fabricate_native_elapsed_time(self):
        events = recording()
        events[0]["data"]["capture_mode"] = "imported_completed_spans"
        for event in events:
            event.pop("elapsed_us")
            if event["type"].startswith("span."):
                event["data"]["reconstructed"] = True
        self.assertIn("missing_source_time", codes(events))
        events[-1]["elapsed_us"] = 0
        with self.assertRaisesRegex(ValueError, "must not contain native elapsed"):
            validate_events(events)

    def test_reduced_copy_preserves_source_issues_without_echoing_untrusted_codes(self):
        events = recording()
        events[0]["data"]["transform"] = {
            "kind": "reduced_share", "version": "0.1",
            "source_issues": ["recording_loss", "missing_capture_end", "conflicting_duplicate", "secret-value-from-source", "secret-value-from-source"],
        }
        warnings = validate_events(events)
        self.assertEqual({item["code"] for item in warnings}, {"recording_loss", "missing_capture_end", "conflicting_duplicate", "reduced_share", "source_issue"})
        self.assertNotIn("secret-value", json.dumps(warnings))
        self.assertEqual(sum(item["code"] == "source_issue" for item in warnings), 1)
        copied = load_recording(encoded(events), from_text=True)
        self.assertEqual(copied["warnings"], warnings)

    def test_real_writer_limit_is_reported_and_survives_reduced_metadata(self):
        from agent_flight_recorder import Limits, Recorder
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "limited.jsonl"
            with Recorder(target, limits=Limits(max_events=3)) as recorder:
                with recorder.run("run"):
                    with recorder.span("tool", "tool"):
                        pass
            result = load_recording(target)
            self.assertTrue({"recording_loss", "capture_limit_reached", "missing_span_end"}.issubset({item["code"] for item in result["warnings"]}))
            self.assertTrue(recorder.health["limit_reached"])
            reduced = recording()
            reduced[0]["data"]["transform"] = {"kind": "reduced_share", "version": "0.1", "source_issues": [item["code"] for item in result["warnings"]]}
            self.assertTrue({"recording_loss", "capture_limit_reached", "missing_span_end", "reduced_share"}.issubset(codes(reduced)))

    def test_newline_only_input_is_rejected_before_materializing_all_lines(self):
        # Below the byte limit, but millions of physical records would otherwise
        # allocate an enormous split result. The byte count is checked first.
        with self.assertRaisesRegex(ValueError, "Event count limit"):
            load_recording("\n" * (25 * 1024 * 1024), from_text=True)

    def test_missing_parent_orphan_end_cycle_and_conflicting_end(self):
        events = recording()
        events[1]["parent_span_id"] = "3" * 16
        self.assertIn("missing_parent", codes(events))
        events[1]["parent_span_id"] = events[1]["span_id"]
        self.assertIn("parent_cycle", codes(events))
        events[2]["span_id"] = "4" * 16
        self.assertIn("orphan_span_end", codes(events))
        events = recording()
        end = copy.deepcopy(events[2])
        end.update(event_id=str(uuid4()), seq=4)
        end["data"]["status"] = "error"
        events.insert(3, end)
        self.assertIn("conflicting_span_end", codes(events))

    def test_iterative_parent_graph_handles_deep_chains(self):
        events = recording()[:1]
        previous = None
        for seq in range(2, 1602):
            item = copy.deepcopy(recording()[1])
            item.update(recording_id=events[0]["recording_id"], seq=seq, elapsed_us=seq, span_id=f"{seq:016x}")
            if previous:
                item["parent_span_id"] = previous
            previous = item["span_id"]
            events.append(item)
        self.assertIn("missing_span_end", codes(events))

    def test_one_recording_and_trace_are_required(self):
        events = recording()
        events[2]["trace_id"] = "a" * 32
        with self.assertRaisesRegex(ValueError, "one recording"):
            validate_events(events)

    def test_timestamp_nanoseconds_are_exact(self):
        self.assertEqual(timestamp_ns("2026-11-12T12:00:00.000000002Z") - timestamp_ns("2026-11-12T12:00:00.000000001Z"), 1)
        self.assertEqual(timestamp_ns("1970-01-01T00:00:00Z"), 0)
        self.assertEqual(timestamp_ns("1969-12-31T23:59:59.999999999Z"), -1)

    def test_unicode_line_separators_do_not_split_json_records(self):
        events = recording()
        events[1]["data"]["name"] = "label\u2028with\u0085separators"
        text = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)
        self.assertEqual(load_recording(text, from_text=True)["events"], events)


if __name__ == "__main__":
    unittest.main()
