"""Bounded readers and evidence validation for the 0.1 recording format.

Semantic problems remain visible as warnings. Invalid envelopes and resource
limits are errors, because a viewer cannot safely interpret them.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_EVENTS = 10_000
MAX_EVENT_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 8 * 1024
MAX_DEPTH = 20
MAX_JSON_NODES = 500_000
MAX_CONTAINER_ITEMS = 100_000
MAX_SAFE_INTEGER = 2**53 - 1
_TRACE = re.compile(r"[0-9a-f]{32}\Z")
_SPAN = re.compile(r"[0-9a-f]{16}\Z")
_TIME = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z\Z")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
_KINDS = {"run", "agent", "model", "tool", "retrieval", "step"}
_TYPES = {"capture.started", "span.started", "span.ended", "event.recorded", "capture.ended"}
_ATTRS = {"provider", "model", "tool_name", "tool_call_id", "attempt", "retry_of", "otel_span_kind"}
_SOURCE_WARNING_CODES = frozenset({
    "duplicate_event", "conflicting_duplicate", "duplicate_sequence", "sequence_gap", "sequence_order",
    "missing_capture_start", "missing_capture_end", "duplicate_capture_start", "duplicate_capture_end",
    "capture_position", "capture_count_mismatch", "duplicate_span_start", "conflicting_span_end",
    "duplicate_span_end", "missing_span_end", "orphan_span_end", "missing_parent", "parent_cycle",
    "missing_root_span", "missing_root_end", "capture_closed_with_open_spans", "native_clock_anomaly",
    "missing_source_time", "negative_source_duration", "source_time_ties", "partial_trailing_line",
    "invalid_line", "recording_loss", "capture_limit_reached", "source_issue", "reduced_share", "privacy_mismatch",
})


def _integer(value, *, positive=False):
    return type(value) is int and (1 if positive else 0) <= value <= MAX_SAFE_INTEGER


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identifier(value, pattern):
    return type(value) is str and bool(pattern.fullmatch(value)) and int(value, 16) != 0


def _uuid(value):
    if type(value) is not str or not _UUID.fullmatch(value):
        return False
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def timestamp_ns(value):
    """Return exact integer UTC nanoseconds; do not round through a float."""
    if type(value) is not str:
        raise ValueError("Invalid UTC timestamp")
    match = _TIME.fullmatch(value)
    if not match:
        raise ValueError("Invalid UTC timestamp")
    try:
        date = datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError("Invalid UTC timestamp") from None
    delta = date - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + int((match[2] or "").ljust(9, "0"))


def _bounded_json(value, *, max_depth=MAX_DEPTH):
    """Inspect exact JSON builtins only, without invoking user serialization."""
    # Iterate siblings lazily: never allocate one pending tuple per array item.
    # Active identities are exactly the bounded container stack, not the entire
    # graph, so repeated (noncyclic) values remain legitimate JSON.
    stack = [(iter((value,)), 0, None)]
    active = set()
    visited = 0
    while stack:
        iterator, depth, identity = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            if identity is not None:
                active.remove(identity)
            continue
        visited += 1
        _require(visited <= MAX_JSON_NODES, "JSON traversal limit exceeded")
        kind = type(item)
        if kind in (dict, list):
            _require(depth < max_depth, "JSON nesting limit exceeded")
            _require(len(item) <= MAX_CONTAINER_ITEMS, "JSON container item limit exceeded")
            _require(id(item) not in active, "Cyclic JSON value")
            if kind is dict:
                _require(all(type(key) is str for key in item), "JSON object keys must be strings")
                children = iter(item.values())
            else:
                children = iter(item)
            active.add(id(item))
            stack.append((children, depth + 1, id(item)))
        elif kind is int:
            _require(abs(item) <= MAX_SAFE_INTEGER, "JSON integer outside safe range")
        elif kind is float:
            _require(math.isfinite(item), "JSON number must be finite")
            _require(not item.is_integer() or abs(item) <= MAX_SAFE_INTEGER, "JSON integer outside safe range")
        else:
            _require(kind in (str, bool, type(None)), "Unsupported JSON value")


def _encode(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError("Invalid JSON encoding") from None


def _label(value):
    return type(value) is str and len(value) <= 256


def _payload(value):
    _require(type(value) is dict, "Invalid payload descriptor")
    state = value.get("state")
    _require(type(state) is str and state in {"captured", "omitted", "redacted", "unavailable"}, "Invalid payload state")
    _require(("value" in value) == (state == "captured"), "Payload value inconsistent with state")
    if "reason" in value:
        _require(_label(value["reason"]), "Invalid payload reason")
    if "truncated" in value:
        _require(type(value["truncated"]) is bool, "Invalid payload truncation marker")
    if "redacted_fields" in value:
        _require(_integer(value["redacted_fields"]), "Invalid redaction count")
    if state == "captured":
        _require(len(_encode(value["value"])) <= MAX_PAYLOAD_BYTES, "Payload size limit exceeded")


def _validate_event(event):
    _require(type(event) is dict, "Recording event must be an object")
    _bounded_json(event)
    _require(len(_encode(event)) <= MAX_EVENT_BYTES, "Event size limit exceeded")
    _require(event.get("schema_version") == "0.1", "Unsupported recording schema version")
    _require(_uuid(event.get("recording_id")), "Invalid recording ID")
    _require(_uuid(event.get("event_id")), "Invalid event ID")
    _require(_identifier(event.get("trace_id"), _TRACE), "Invalid trace ID")
    _require(_integer(event.get("seq"), positive=True), "Invalid event sequence")
    timestamp_ns(event.get("recorded_at"))
    if "elapsed_us" in event:
        _require(_integer(event["elapsed_us"]), "Invalid elapsed time")
    if "source_time" in event:
        timestamp_ns(event["source_time"])
    event_type = event.get("type")
    _require(type(event_type) is str and event_type in _TYPES, "Unsupported recording event type")
    data = event.get("data")
    _require(type(data) is dict, "Event data must be an object")
    if event_type.startswith("span.") or "span_id" in event:
        _require(_identifier(event.get("span_id"), _SPAN), "Invalid span ID")
    if "parent_span_id" in event:
        _require(event_type == "span.started" and _identifier(event["parent_span_id"], _SPAN), "Invalid parent span ID")
    if event_type == "capture.started":
        _require(_label(data.get("recorder_version")), "Invalid recorder version")
        _require(type(data.get("capture_mode")) is str and data["capture_mode"] in {"native_lifecycle", "imported_completed_spans"}, "Invalid capture mode")
        _require(type(data.get("privacy_mode")) is str and data["privacy_mode"] in {"metadata_only", "selected_content"}, "Invalid privacy mode")
        _require(_label(data.get("coverage")), "Invalid coverage description")
        limits = data.get("limits")
        _require(type(limits) is dict, "Missing capture limits")
        for key, maximum in {"max_file_bytes": MAX_FILE_BYTES, "max_events": MAX_EVENTS, "max_event_bytes": MAX_EVENT_BYTES, "max_payload_bytes": MAX_PAYLOAD_BYTES, "max_depth": MAX_DEPTH}.items():
            _require(_integer(limits.get(key), positive=True) and limits[key] <= maximum, "Invalid capture limits")
        if "source" in data:
            source = data["source"]
            _require(type(source) is dict and _label(source.get("name")) and _label(source.get("version")), "Invalid source provenance")
        if "transform" in data:
            transform = data["transform"]
            _require(type(transform) is dict and transform.get("kind") == "reduced_share" and transform.get("version") == "0.1", "Invalid transformation provenance")
            _require(type(transform.get("source_issues")) is list and all(_label(code) for code in transform["source_issues"]), "Invalid transformation warnings")
    elif event_type == "span.started":
        _require(type(data.get("kind")) is str and data["kind"] in _KINDS, "Invalid span kind")
        _require(_label(data.get("name")), "Invalid span name")
        _payload(data.get("input"))
        if "attributes" in data:
            attributes = data["attributes"]
            _require(type(attributes) is dict, "Invalid span attributes")
            for key, value in attributes.items():
                _require(key in _ATTRS, "Unsupported structural attribute")
                valid = _integer(value) if key == "attempt" else _identifier(value, _SPAN) if key == "retry_of" else _label(value)
                _require(valid, "Invalid structural attribute")
        if "links" in data:
            _require(type(data["links"]) is list and len(data["links"]) <= 64, "Invalid span links")
            for link in data["links"]:
                _require(type(link) is dict and _identifier(link.get("span_id"), _SPAN) and type(link.get("relation")) is str and link["relation"] in {"retry_of", "follows_from"}, "Invalid span link")
    elif event_type == "span.ended":
        _require(type(data.get("status")) is str and data["status"] in {"ok", "error", "cancelled", "unknown"}, "Invalid span status")
        _payload(data.get("output"))
        if "usage" in data:
            usage = data["usage"]
            _require(type(usage) is dict and all(key in {"input_tokens", "output_tokens"} and _integer(value) for key, value in usage.items()), "Invalid token usage")
        if "error" in data:
            error = data["error"]
            _require(type(error) is dict and _label(error.get("type")) and ("code" not in error or _label(error["code"])), "Invalid error category")
    elif event_type == "event.recorded":
        _require(_label(data.get("name")), "Invalid event name")
        _payload(data.get("payload"))
    elif event_type == "capture.ended":
        for key in ("written_events", "skipped_events", "failed_events"):
            _require(_integer(data.get(key)), "Invalid capture summary count")
        _require(type(data.get("limit_reached")) is bool, "Invalid capture limit marker")
    if "reconstructed" in data:
        _require(type(data["reconstructed"]) is bool, "Invalid reconstructed marker")


def validate_events(events):
    """Validate bounded envelopes, returning evidence problems as static warnings."""
    _require(type(events) is list, "Events must be a list")
    _require(len(events) <= MAX_EVENTS, "Event count limit exceeded")
    total = 0
    for event in events:
        _validate_event(event)
        total += len(_encode(event)) + 1
        _require(total <= MAX_FILE_BYTES, "Recording size limit exceeded")
    warnings = []
    seen_warnings = set()

    def warn(code, message, line=None):
        marker = (code, line)
        if marker not in seen_warnings:
            seen_warnings.add(marker)
            warnings.append({"code": code, "message": message, **({"line": line} if line is not None else {})})

    identities = {(event["recording_id"], event["trace_id"]) for event in events}
    _require(len(identities) <= 1, "A recording must contain exactly one recording ID and trace ID")
    unique = []
    by_id = {}
    for index, event in enumerate(events, 1):
        old = by_id.get(event["event_id"])
        if old is not None:
            warn("duplicate_event" if old == event else "conflicting_duplicate", "Repeated event ID; conflicting data is not resolved." if old != event else "Identical event repeated; shown once in derived views.", index)
        else:
            by_id[event["event_id"]] = event
            unique.append((index, event))
    sequences = [event["seq"] for _, event in unique]
    if len(set(sequences)) != len(sequences):
        warn("duplicate_sequence", "Different events share a sequence number.")
    if sequences != sorted(sequences):
        warn("sequence_order", "File order differs from observation sequence.")
    ordered_sequences = sorted(set(sequences))
    if ordered_sequences and (ordered_sequences[0] != 1 or any(right != left + 1 for left, right in zip(ordered_sequences, ordered_sequences[1:]))):
        warn("sequence_gap", "Observation sequence has gaps; evidence may be missing.")
    captures = [event for _, event in unique if event["type"] == "capture.started"]
    closures = [event for _, event in unique if event["type"] == "capture.ended"]
    for records, name in ((captures, "start"), (closures, "end")):
        if not records:
            warn("missing_capture_" + name, "Capture lifecycle marker is missing.")
        elif len(records) > 1:
            warn("duplicate_capture_" + name, "Capture lifecycle marker is repeated.")
    if unique and ((captures and unique[0][1]["type"] != "capture.started") or (closures and unique[-1][1]["type"] != "capture.ended")):
        warn("capture_position", "Capture lifecycle markers are out of position.")
    if closures and closures[0]["data"]["written_events"] != len(unique):
        warn("capture_count_mismatch", "Capture summary differs from the number of unique records.")
    for closure in closures:
        summary = closure["data"]
        if summary["skipped_events"] or summary["failed_events"]:
            warn("recording_loss", "The recorder reported skipped or failed events.")
        if summary["limit_reached"]:
            warn("capture_limit_reached", "The recorder reached a configured capture limit.")
    for capture in captures:
        transform = capture["data"].get("transform")
        if transform is not None:
            warn("reduced_share", "This is a reduced, transformed copy; content, labels, identifiers and absolute times may differ from the original.")
            for source_code in transform["source_issues"]:
                if source_code in _SOURCE_WARNING_CODES:
                    warn(source_code, "The source recording reported this evidence issue before transformation.")
                else:
                    warn("source_issue", "The source recording reported an unrecognized issue; inspect the original recording.")
    mode = captures[0]["data"]["capture_mode"] if captures else None
    if any(capture["data"]["privacy_mode"] == "metadata_only" for capture in captures):
        payload_keys = {"span.started": "input", "span.ended": "output", "event.recorded": "payload"}
        if any(event["type"] in payload_keys and event["data"][payload_keys[event["type"]]]["state"] == "captured" for _, event in unique):
            warn("privacy_mismatch", "Captured payload values are present despite a metadata-only policy declaration.")
    starts, ends = {}, {}
    previous_elapsed = None
    source_times = []
    for index, event in sorted(unique, key=lambda pair: pair[1]["seq"]):
        if mode == "native_lifecycle":
            _require("elapsed_us" in event, "Native events require elapsed time")
            elapsed = event["elapsed_us"]
            if previous_elapsed is not None and elapsed < previous_elapsed:
                warn("native_clock_anomaly", "Native monotonic time moves backwards.", index)
            previous_elapsed = elapsed
        elif mode == "imported_completed_spans":
            _require("elapsed_us" not in event, "Imported events must not contain native elapsed time")
        if event["type"].startswith("span."):
            if mode == "imported_completed_spans":
                _require(event["data"].get("reconstructed") is True, "Imported span events must be marked reconstructed")
                if "source_time" not in event:
                    warn("missing_source_time", "Imported operation has an unavailable source time.", index)
                else:
                    source_times.append(timestamp_ns(event["source_time"]))
            target = starts if event["type"] == "span.started" else ends
            span_id = event["span_id"]
            if span_id in target:
                if event["type"] == "span.started":
                    warn("duplicate_span_start", "Span has multiple starts.", index)
                else:
                    equivalent = event["data"] == target[span_id]["data"] and event.get("source_time") == target[span_id].get("source_time") and event.get("elapsed_us") == target[span_id].get("elapsed_us")
                    warn("duplicate_span_end" if equivalent else "conflicting_span_end", "Span has multiple ends; the outcome is ambiguous.", index)
            else:
                target[span_id] = event
    if len(set(source_times)) != len(source_times):
        warn("source_time_ties", "Imported timestamps tie; displayed order does not establish causality.")
    for span_id, start in starts.items():
        parent = start.get("parent_span_id")
        if parent and parent not in starts:
            warn("missing_parent", "A span's parent is absent.")
        if span_id not in ends:
            warn("missing_span_end", "An observed span has no end; outcome is unknown.")
        else:
            end = ends[span_id]
            if "source_time" in start and "source_time" in end and timestamp_ns(end["source_time"]) < timestamp_ns(start["source_time"]):
                warn("negative_source_duration", "Source end precedes source start; interval is unreliable.")
            if "elapsed_us" in start and "elapsed_us" in end and end["elapsed_us"] < start["elapsed_us"]:
                warn("native_clock_anomaly", "Span end precedes its native start.")
    if any(span_id not in starts for span_id in ends):
        warn("orphan_span_end", "A span end has no observed start.")
    roots = [key for key, value in starts.items() if not value.get("parent_span_id")]
    if not roots:
        warn("missing_root_span", "No root operation was observed.")
    elif any(key not in ends for key in roots):
        warn("missing_root_end", "A root operation has no observed end.")
    if closures and any(key not in ends for key in starts):
        warn("capture_closed_with_open_spans", "Capture closed while observed operations remained unfinished.")
    visited = set()
    for span_id in starts:
        path = set()
        current = span_id
        while current in starts and current not in visited:
            if current in path:
                warn("parent_cycle", "Span parent relationships contain a cycle.")
                break
            path.add(current)
            current = starts[current].get("parent_span_id")
        visited.update(path)
    return warnings


def _depth_preflight(text):
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            _require(depth <= MAX_DEPTH, "JSON nesting limit exceeded")
        elif char in "]}":
            depth -= 1


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON object key")
        result[key] = value
    return result


def _parse_int(value):
    _require(len(value.lstrip("-")) <= 16, "JSON integer outside safe range")
    result = int(value)
    _require(abs(result) <= MAX_SAFE_INTEGER, "JSON integer outside safe range")
    return result


def _constant(_value):
    raise ValueError("JSON number must be finite")


def _incomplete_json(line, error):
    suffix = line[error.pos:]
    if error.pos >= len(line) or error.msg.startswith("Unterminated string"):
        return True
    if suffix in {"t", "tr", "tru", "f", "fa", "fal", "fals", "n", "nu", "nul", "-"}:
        return True
    if error.msg.startswith("Invalid \\uXXXX escape") and re.fullmatch(r"u[0-9a-fA-F]{0,3}", suffix):
        return True
    return bool(error.pos > 0 and line[error.pos - 1].isdigit() and suffix in {".", "e", "E", "e+", "e-", "E+", "E-"})


def load_recording(path_or_text, *, from_text=False, allow_partial=False):
    """Read a bounded recording; explicitly opt in to skip bad middle lines.

    Only syntactically truncated final JSON is automatically recoverable. Invalid
    envelopes, unsupported schemas and oversize data never silently disappear.
    """
    if from_text:
        _require(type(path_or_text) is str, "Recording text must be a string")
        try:
            raw = path_or_text.encode("utf-8")
        except UnicodeError:
            raise ValueError("Recording must contain valid UTF-8") from None
    else:
        with open(path_or_text, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    _require(len(raw) <= MAX_FILE_BYTES, "Recording size limit exceeded")
    physical_line_count = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
    _require(physical_line_count <= MAX_EVENTS, "Event count limit exceeded")
    truncated_utf8 = False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        if error.reason == "unexpected end of data" and error.end == len(raw):
            # A killed append can split the last UTF-8 codepoint. Its containing
            # incomplete JSON line is classified below; earlier bytes stay valid.
            text = raw[:error.start].decode("utf-8")
            truncated_utf8 = True
        else:
            raise ValueError("Recording must contain valid UTF-8") from None
    # JSONL is delimited by LF. Unicode line-separator characters are legal
    # inside JSON strings and must not create phantom physical records.
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    _require(not truncated_utf8 or bool(lines) and not text.endswith("\n"), "Recording must contain valid UTF-8")
    _require(len(lines) <= MAX_EVENTS, "Event count limit exceeded")
    events, parse_warnings, physical_lines = [], [], []
    partial = False
    for index, line in enumerate(lines, 1):
        _require(len(line.encode("utf-8")) <= MAX_EVENT_BYTES, "Event size limit exceeded")
        _depth_preflight(line)
        try:
            event = json.loads(line, parse_int=_parse_int, parse_constant=_constant, object_pairs_hook=_pairs)
        except json.JSONDecodeError as error:
            # A final incomplete physical line is the usual interrupted append.
            # A newline-terminated invalid last record is not presumed truncated.
            incomplete = _incomplete_json(line, error)
            trailing = index == len(lines) and not text.endswith(("\n", "\r")) and incomplete
            if trailing or allow_partial:
                parse_warnings.append({"code": "partial_trailing_line" if trailing else "invalid_line", "message": "Incomplete final JSON line was skipped." if trailing else "Invalid JSON line was skipped with partial-view acknowledgement.", "line": index})
                partial = True
                continue
            raise ValueError(f"Invalid JSON at line {index}; partial view requires allow_partial=True") from None
        except (ValueError, RecursionError):
            raise ValueError(f"Invalid bounded JSON at line {index}") from None
        _require(not truncated_utf8 or index != len(lines), "Recording must contain valid UTF-8")
        try:
            _validate_event(event)
        except ValueError as error:
            # Schema errors are not byte truncation, including on the last line.
            raise ValueError(f"{error} at line {index}") from None
        events.append(event)
        physical_lines.append(index)
    validation_warnings = validate_events(events)
    for warning in validation_warnings:
        if "line" in warning:
            warning["line"] = physical_lines[warning["line"] - 1]
    warnings = parse_warnings + validation_warnings
    return {"events": events, "warnings": warnings, "partial": partial}


def write_recording(events, path):
    """Preflight completely, then create a new owner-readable recording.

    Never overwrite an existing path or follow its final symlink. A failed write
    leaves a partial new recording, which the reader can identify as incomplete.
    """
    validate_events(events)
    encoded = b"".join(_encode(event) + b"\n" for event in events)
    _require(len(encoded) <= MAX_FILE_BYTES, "Recording size limit exceeded")
    target = Path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    try:
        handle = os.fdopen(fd, "wb")
    except Exception:
        os.close(fd)
        raise
    with handle:
        handle.write(encoded)
        handle.flush()
