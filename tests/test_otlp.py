import copy
import json
import unittest
from unittest.mock import patch

from agent_flight_recorder.otlp import convert_otlp
from agent_flight_recorder.recording import timestamp_ns, validate_events


def attribute(key, value):
    if type(value) is str:
        wrapped = {"stringValue": value}
    elif type(value) is int:
        wrapped = {"intValue": str(value)}
    else:
        wrapped = value
    return {"key": key, "value": wrapped}


def span(number=1, **changes):
    item = {"traceId": "a" * 32, "spanId": f"{number:016x}", "name": "model operation", "kind": 3,
            "startTimeUnixNano": "1730000000000000001", "endTimeUnixNano": "1730000000000000003", "status": {"code": 0},
            "attributes": [attribute("gen_ai.operation.name", "chat"), attribute("gen_ai.provider.name", "example"), attribute("gen_ai.request.model", "synthetic-model"), attribute("gen_ai.usage.input_tokens", 7)]}
    item.update(changes)
    return item


def export(*spans):
    return {"resourceSpans": [{"resource": {"attributes": [attribute("service.name", "resource-secret")]}, "scopeSpans": [{"scope": {"name": "scope-secret"}, "spans": list(spans)}]}]}


def operations(events, kind):
    return [item for item in events if item["type"] == kind]


class OTLPTests(unittest.TestCase):
    def test_narrow_mapping_preserves_ids_unknown_status_and_exact_timing(self):
        result = convert_otlp(export(span()))
        self.assertEqual(validate_events(result), [])
        start = result[1]
        end = result[2]
        self.assertEqual(start["span_id"], "0000000000000001")
        self.assertEqual(start["trace_id"], "a" * 32)
        self.assertTrue(start["data"]["reconstructed"])
        self.assertEqual(start["data"]["kind"], "model")
        self.assertEqual(start["data"]["attributes"]["otel_span_kind"], "CLIENT")
        self.assertEqual(end["data"]["status"], "unknown")
        self.assertEqual(end["data"]["usage"], {"input_tokens": 7})
        self.assertNotIn("elapsed_us", start)
        self.assertEqual(timestamp_ns(end["source_time"]) - timestamp_ns(start["source_time"]), 2)
        self.assertTrue(start["source_time"].endswith(".000000001Z"))

    def test_default_omits_payload_resource_and_unmapped_secrets(self):
        item = span()
        item["attributes"] += [attribute("input.value", "input-secret"), attribute("output.value", "output-secret"), attribute("authorization", "header-secret"), attribute("exception.message", "exception-secret")]
        item["status"] = {"code": 2, "message": "status-secret"}
        item["events"] = [{"name": "event-secret"}]
        result = convert_otlp(export(item))
        text = json.dumps(result)
        for forbidden in ("input-secret", "output-secret", "header-secret", "exception-secret", "resource-secret", "scope-secret", "status-secret", "event-secret"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(result[1]["data"]["input"]["state"], "omitted")
        self.assertEqual(result[2]["data"]["error"], {"type": "source_error"})

    def test_opt_in_decodes_structured_content_through_privacy_policy(self):
        item = span()
        item["attributes"] += [attribute("gen_ai.input.messages", {"arrayValue": {"values": [{"kvlistValue": {"values": [attribute("role", "user"), attribute("content", "hello"), attribute("api_key", "secret-credential")]}}]}})]
        result = convert_otlp(export(item), capture_content=True)
        self.assertEqual(result[0]["data"]["privacy_mode"], "selected_content")
        payload = result[1]["data"]["input"]
        self.assertEqual(payload["state"], "captured")
        self.assertEqual(payload["value"][0]["content"], "hello")
        self.assertNotIn("secret-credential", json.dumps(result))

    def test_multiple_traces_need_selection(self):
        source = export(span(), span(2, traceId="b" * 32))
        with self.assertRaisesRegex(ValueError, "select one"):
            convert_otlp(source)
        result = convert_otlp(source, trace_id="b" * 32)
        self.assertEqual({item["trace_id"] for item in result}, {"b" * 32})
        with self.assertRaisesRegex(ValueError, "not present"):
            convert_otlp(source, trace_id="c" * 32)

    def test_out_of_order_source_is_sorted_by_source_time_not_conversion(self):
        later = span(1, startTimeUnixNano="1730000000000000008", endTimeUnixNano="1730000000000000009")
        earlier = span(2, startTimeUnixNano="1730000000000000001", endTimeUnixNano="1730000000000000004")
        result = convert_otlp(export(later, earlier))
        self.assertEqual([item["span_id"] for item in result[1:-1]], [earlier["spanId"], earlier["spanId"], later["spanId"], later["spanId"]])
        self.assertEqual({item["recorded_at"] for item in result}, {result[0]["recorded_at"]})
        self.assertNotEqual(result[1]["source_time"], result[1]["recorded_at"])

    def test_ties_starts_before_ends_then_span_id_are_visible(self):
        source = export(span(2, endTimeUnixNano="1730000000000000001"), span(1, endTimeUnixNano="1730000000000000001"))
        result = convert_otlp(source)
        self.assertEqual([item["type"] for item in result[1:-1]], ["span.started", "span.started", "span.ended", "span.ended"])
        self.assertEqual(result[1]["span_id"], "0000000000000001")
        self.assertIn("source_time_ties", {item["code"] for item in validate_events(result)})

    def test_bad_source_times_stay_undated_and_negative_intervals_warn(self):
        for bad_time in (None, "0", "invalid", 1730000000000000001, "18446744073709551616"):
            with self.subTest(bad_time=bad_time):
                # Integer uint64 violates the JSON-safe primitive contract before mapping.
                if type(bad_time) is int:
                    with self.assertRaises(ValueError):
                        convert_otlp(export(span(startTimeUnixNano=bad_time)))
                    continue
                result = convert_otlp(export(span(startTimeUnixNano=bad_time)))
                start = operations(result, "span.started")[0]
                self.assertNotIn("source_time", start)
                self.assertIn("missing_source_time", {item["code"] for item in validate_events(result)})
        result = convert_otlp(export(span(startTimeUnixNano="1730000000000000009")))
        self.assertIn("negative_source_duration", {item["code"] for item in validate_events(result)})

    def test_openinference_tool_mapping_and_usage_totals_only(self):
        item = span(kind="SPAN_KIND_INTERNAL")
        item["attributes"] = [attribute("openinference.span.kind", "TOOL"), attribute("tool.name", "lookup"), attribute("tool_call.id", "provider-call"), attribute("llm.token_count.prompt", 12), attribute("llm.token_count.completion", 4), attribute("llm.token_count.prompt_details.cache_read", 10)]
        result = convert_otlp(export(item))
        self.assertEqual(result[1]["data"]["kind"], "tool")
        self.assertEqual(result[1]["data"]["attributes"]["tool_call_id"], "provider-call")
        self.assertEqual(result[2]["data"]["usage"], {"input_tokens": 12, "output_tokens": 4})

    def test_expansion_preflight_and_payload_bounds(self):
        with patch("agent_flight_recorder.otlp.MAX_EVENTS", 3), self.assertRaisesRegex(ValueError, "output event count"):
            convert_otlp(export(span()))
        item = span()
        item["attributes"].append(attribute("input.value", "a" * 9000))
        result = convert_otlp(export(item), capture_content=True)
        self.assertNotEqual(result[1]["data"]["input"]["state"], "captured")
        self.assertLess(len(json.dumps(result)), 9000)

    def test_strict_shapes_status_and_duplicate_mapped_values(self):
        invalid = [
            {}, {"resourceSpans": []}, {"resourceSpans": [{"instrumentationLibrarySpans": []}]},
            export(span(traceId="0" * 32)), export(span(spanId="0" * 16)),
            export(span(status={"code": True})), export(span(status={"code": 19})),
        ]
        item = span()
        item["attributes"].append(attribute("gen_ai.operation.name", "execute_tool"))
        invalid.append(export(item))
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(ValueError):
                convert_otlp(source)

    def test_input_is_unchanged_and_parent_is_preserved(self):
        source = export(span(), span(2, parentSpanId="0000000000000001"))
        original = copy.deepcopy(source)
        result = convert_otlp(source)
        self.assertEqual(source, original)
        child = next(item for item in operations(result, "span.started") if item["span_id"] == "0000000000000002")
        self.assertEqual(child["parent_span_id"], "0000000000000001")


if __name__ == "__main__":
    unittest.main()
