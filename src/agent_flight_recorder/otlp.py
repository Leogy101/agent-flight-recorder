"""One bounded OTLP JSON file adapter, not a collector or general exporter parser."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .privacy import MISSING, PrivacyPolicy
from .recording import (
    MAX_DEPTH, MAX_EVENT_BYTES, MAX_EVENTS, MAX_FILE_BYTES, MAX_PAYLOAD_BYTES,
    MAX_SAFE_INTEGER, _SPAN, _TRACE, _bounded_json, _encode, _identifier,
    _integer, _require, timestamp_ns, validate_events,
)

MAPPING_VERSION = "otlp-json-subset-0.1"
OTEL_REVISION = "e6658f14c9d9ea0760825f029cb82e7673f48fab"
OPENINFERENCE_REVISION = "fb1667497ecf94381476d74cb761dad7140491e9"
_ALLOWED_ATTRIBUTES = {
    "gen_ai.operation.name", "openinference.span.kind", "gen_ai.provider.name",
    "gen_ai.system", "llm.provider", "gen_ai.request.model", "gen_ai.response.model",
    "llm.model_name", "gen_ai.tool.name", "tool.name", "gen_ai.tool.call.id", "tool_call.id",
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "llm.token_count.prompt",
    "llm.token_count.completion", "gen_ai.input.messages", "gen_ai.output.messages",
    "gen_ai.tool.call.arguments", "gen_ai.tool.call.result", "input.value", "output.value",
}
_CONTENT_ATTRIBUTES = {
    "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result", "input.value", "output.value",
}
_OTEL_KINDS = {0: "UNSPECIFIED", 1: "INTERNAL", 2: "SERVER", 3: "CLIENT", 4: "PRODUCER", 5: "CONSUMER"}
_OI_KINDS = {"LLM": "model", "AGENT": "agent", "CHAIN": "step", "TOOL": "tool", "RETRIEVER": "retrieval"}
_OP_KINDS = {
    "chat": "model", "text_completion": "model", "generate_content": "model",
    "execute_tool": "tool", "invoke_agent": "agent", "invoke_workflow": "step",
    "invoke_runner": "step", "retrieval": "retrieval", "retrieve": "retrieval",
}


def _array(value, message):
    _require(type(value) is list, message)
    return value


def _any_value(value):
    """Decode the deliberately supported OTLP AnyValue alternatives."""
    _require(type(value) is dict and len(value) == 1, "Invalid OTLP attribute value")
    key, payload = next(iter(value.items()))
    if key == "stringValue":
        _require(type(payload) is str, "Invalid OTLP string attribute")
        return payload
    if key == "boolValue":
        _require(type(payload) is bool, "Invalid OTLP boolean attribute")
        return payload
    if key == "intValue":
        if type(payload) is str:
            _require(len(payload.lstrip("-")) <= 16 and payload.lstrip("-").isascii() and payload.lstrip("-").isdigit(), "Invalid OTLP integer attribute")
            payload = int(payload)
        _require(type(payload) is int and abs(payload) <= MAX_SAFE_INTEGER, "OTLP integer attribute outside safe range")
        return payload
    if key == "doubleValue":
        _require(type(payload) in (int, float), "Invalid OTLP numeric attribute")
        _bounded_json(payload)
        return payload
    if key == "arrayValue":
        _require(type(payload) is dict, "Invalid OTLP array attribute")
        return [_any_value(item) for item in _array(payload.get("values", []), "Invalid OTLP array values")]
    if key == "kvlistValue":
        _require(type(payload) is dict, "Invalid OTLP object attribute")
        result = {}
        for item in _array(payload.get("values", []), "Invalid OTLP object values"):
            _require(type(item) is dict and type(item.get("key")) is str, "Invalid OTLP object key")
            _require(item["key"] not in result, "Duplicate OTLP object key")
            result[item["key"]] = _any_value(item.get("value"))
        return result
    # bytesValue would imply binary support and is intentionally not decoded.
    raise ValueError("Unsupported OTLP attribute encoding")


def _attributes(span, capture_content):
    result = {}
    for item in _array(span.get("attributes", []), "Invalid OTLP attributes"):
        _require(type(item) is dict and type(item.get("key")) is str, "Invalid OTLP attribute")
        key = item["key"]
        if key not in _ALLOWED_ATTRIBUTES:
            continue
        _require(key not in result, "Duplicate mapped OTLP attribute")
        if key in _CONTENT_ATTRIBUTES and not capture_content:
            # Preserve presence without inspecting or decoding the raw payload.
            # PrivacyPolicy(False) turns this placeholder into an omitted marker.
            result[key] = None
            continue
        result[key] = _any_value(item.get("value"))
    return result


def _first(attributes, names):
    for name in names:
        if name in attributes:
            return attributes[name]
    return MISSING


def _source_time(value):
    """Decode OTLP uint64 decimal nanoseconds, preserving all nine digits.

    Missing, zero, malformed or out-of-calendar timestamps remain undated. Their
    absence is then reported by validate_events, never replaced with import time.
    """
    if type(value) is not str or not value.isascii() or not value.isdigit() or len(value) > 20:
        return None
    number = int(value)
    if not 0 < number <= 2**64 - 1:
        return None
    seconds, nanoseconds = divmod(number, 1_000_000_000)
    try:
        instant = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    except (ValueError, OverflowError):
        return None
    return instant.strftime("%Y-%m-%dT%H:%M:%S") + f".{nanoseconds:09d}Z"


def _span_kind(span, attributes):
    operation = attributes.get("gen_ai.operation.name")
    inference_kind = attributes.get("openinference.span.kind")
    if type(operation) is str and operation in _OP_KINDS:
        return _OP_KINDS[operation]
    if type(inference_kind) is str and inference_kind in _OI_KINDS:
        return _OI_KINDS[inference_kind]
    return "step"


def _status(span):
    status = span.get("status", {})
    _require(type(status) is dict, "Invalid OTLP span status")
    code = status.get("code", 0)
    _require(type(code) in (str, int), "Invalid OTLP status code")
    if code in (1, "STATUS_CODE_OK"):
        return "ok"
    if code in (2, "STATUS_CODE_ERROR"):
        return "error"
    if code in (0, "STATUS_CODE_UNSET"):
        return "unknown"
    raise ValueError("Unsupported OTLP status code")


def convert_otlp(source: dict, *, trace_id=None, capture_content=False):
    """Convert one selected OTLP JSON trace into reconstructed lifecycle events.

    The supported shape is resourceSpans[].scopeSpans[].spans[]. Only explicitly
    mapped fields survive. This function does not execute or fetch trace content.
    """
    _require(type(source) is dict, "OTLP export must be an object")
    _require(type(capture_content) is bool, "capture_content must be a boolean")
    _bounded_json(source)
    _require(len(_encode(source)) <= MAX_FILE_BYTES, "OTLP input size limit exceeded")
    spans = []
    for resource in _array(source.get("resourceSpans"), "Expected OTLP resourceSpans array"):
        _require(type(resource) is dict, "Invalid OTLP resource entry")
        for scope in _array(resource.get("scopeSpans"), "Expected OTLP scopeSpans array"):
            _require(type(scope) is dict, "Invalid OTLP scope entry")
            for span in _array(scope.get("spans"), "Expected OTLP spans array"):
                _require(type(span) is dict, "Invalid OTLP span")
                source_trace_id = span.get("traceId")
                _require(type(source_trace_id) is str and _identifier(source_trace_id.lower(), _TRACE), "Invalid OTLP trace ID")
                # OTLP IDs are case-insensitive hex; our native contract uses
                # lowercase. Copy before normalization so source input is intact.
                spans.append({**span, "traceId": source_trace_id.lower()})
                _require(len(spans) <= MAX_EVENTS, "OTLP input span count limit exceeded")
    available = {span["traceId"] for span in spans}
    _require(bool(available), "OTLP export contains no spans")
    if trace_id is None:
        _require(len(available) == 1, "Multiple traces found; select one with trace_id")
        trace_id = next(iter(available))
    if type(trace_id) is str:
        trace_id = trace_id.lower()
    _require(_identifier(trace_id, _TRACE) and trace_id in available, "Selected trace is not present")
    selected = [span for span in spans if span["traceId"] == trace_id]
    _require(2 * len(selected) + 2 <= MAX_EVENTS, "OTLP conversion exceeds output event count limit")
    policy = PrivacyPolicy(capture_content=capture_content, max_depth=MAX_DEPTH - 3)
    recording_id = str(uuid4())
    converted_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def event(event_type, data, span=None, source_time=None):
        result = {"schema_version": "0.1", "recording_id": recording_id, "trace_id": trace_id,
                  "event_id": str(uuid4()), "seq": 1, "type": event_type, "recorded_at": converted_at, "data": data}
        if span is not None:
            result["span_id"] = span["spanId"]
        if source_time is not None:
            result["source_time"] = source_time
        return result

    operations = []
    for span in selected:
        if type(span.get("spanId")) is str:
            span["spanId"] = span["spanId"].lower()
        _require(_identifier(span.get("spanId"), _SPAN), "Invalid OTLP span ID")
        parent = span.get("parentSpanId")
        if type(parent) is str:
            parent = parent.lower()
        if parent not in (None, "", "0000000000000000"):
            _require(_identifier(parent, _SPAN), "Invalid OTLP parent span ID")
        else:
            parent = None
        attributes = _attributes(span, capture_content)
        mapped = {}
        for target, choices in {
            "provider": ("gen_ai.provider.name", "gen_ai.system", "llm.provider"),
            "model": ("gen_ai.response.model", "gen_ai.request.model", "llm.model_name"),
            "tool_name": ("gen_ai.tool.name", "tool.name"),
            "tool_call_id": ("gen_ai.tool.call.id", "tool_call.id"),
        }.items():
            value = _first(attributes, choices)
            if type(value) is str:
                mapped[target] = value
        otel_kind = span.get("kind", 0)
        if type(otel_kind) is int and otel_kind in _OTEL_KINDS:
            mapped["otel_span_kind"] = _OTEL_KINDS[otel_kind]
        elif type(otel_kind) is str and otel_kind.startswith("SPAN_KIND_") and otel_kind[10:] in _OTEL_KINDS.values():
            mapped["otel_span_kind"] = otel_kind[10:]
        data = {"kind": _span_kind(span, attributes), "name": policy.label(span.get("name", "imported operation")),
                "input": policy.payload(_first(attributes, ("gen_ai.input.messages", "gen_ai.tool.call.arguments", "input.value"))),
                "attributes": policy.attributes(mapped), "reconstructed": True}
        start = event("span.started", data, span, _source_time(span.get("startTimeUnixNano")))
        if parent:
            start["parent_span_id"] = parent
        end_data = {"status": _status(span), "output": policy.payload(_first(attributes, ("gen_ai.output.messages", "gen_ai.tool.call.result", "output.value"))), "reconstructed": True}
        if end_data["status"] == "error":
            end_data["error"] = {"type": "source_error"}
        usage = {}
        for target, choices in {"input_tokens": ("gen_ai.usage.input_tokens", "llm.token_count.prompt"), "output_tokens": ("gen_ai.usage.output_tokens", "llm.token_count.completion")}.items():
            value = _first(attributes, choices)
            if value is not MISSING:
                _require(_integer(value), "Invalid OTLP token total")
                usage[target] = value
        if usage:
            end_data["usage"] = usage
        end = event("span.ended", end_data, span, _source_time(span.get("endTimeUnixNano")))
        operations.extend((start, end))
    operations.sort(key=lambda item: ("source_time" not in item, timestamp_ns(item["source_time"]) if "source_time" in item else 0, 0 if item["type"] == "span.started" else 1, item["span_id"]))
    capture = event("capture.started", {
        "recorder_version": "0.1", "capture_mode": "imported_completed_spans",
        "privacy_mode": "selected_content" if capture_content else "metadata_only",
        "coverage": "Completed source spans only; lifecycle events reconstructed; original capture completeness unknown.",
        "source": {"name": "OTLP JSON file", "version": MAPPING_VERSION},
        "limits": {"max_file_bytes": MAX_FILE_BYTES, "max_events": MAX_EVENTS, "max_event_bytes": MAX_EVENT_BYTES,
                   "max_payload_bytes": MAX_PAYLOAD_BYTES, "max_depth": MAX_DEPTH},
    })
    closure = event("capture.ended", {"written_events": len(operations) + 2, "skipped_events": 0, "failed_events": 0, "limit_reached": False})
    result = [capture, *operations, closure]
    for seq, item in enumerate(result, 1):
        item["seq"] = seq
    validate_events(result)
    return result
