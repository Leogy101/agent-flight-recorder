"""Deterministic, synthetic recordings. These examples never invoke models or tools."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5


def demo_events(scenario: str = "failure") -> list[dict]:
    if scenario not in {"failure", "interrupted", "success"}:
        raise ValueError("Unknown synthetic scenario")
    recording_id = str(uuid5(NAMESPACE_URL, f"afr-demo/{scenario}/recording"))
    trace_id = uuid5(NAMESPACE_URL, f"afr-demo/{scenario}/trace").hex
    base = datetime(2026, 11, 12, 14, 30, tzinfo=timezone.utc)
    events: list[dict] = []

    def sid(name):
        return uuid5(NAMESPACE_URL, f"afr-demo/{scenario}/{name}").hex[:16]

    def payload(value):
        return {"state": "captured", "value": value}

    def emit(at_ms, kind, data, span=None, parent=None):
        event = {
            "schema_version": "0.1", "recording_id": recording_id, "trace_id": trace_id,
            "event_id": str(uuid5(NAMESPACE_URL, f"afr-demo/{scenario}/event/{len(events)+1}")),
            "seq": len(events) + 1, "type": kind,
            "recorded_at": (base + timedelta(milliseconds=at_ms)).isoformat().replace("+00:00", "Z"),
            "elapsed_us": int(at_ms * 1000), "data": data,
        }
        if span:
            event["span_id"] = sid(span)
        if parent:
            event["parent_span_id"] = sid(parent)
        events.append(event)

    def start(at_ms, key, kind, name, parent=None, value=None, attrs=None, links=None):
        data = {"kind": kind, "name": name, "input": payload(value) if value is not None else {"state": "omitted", "reason": "policy"}}
        if attrs:
            data["attributes"] = attrs
        if links:
            data["links"] = links
        emit(at_ms, "span.started", data, key, parent)

    def end(at_ms, key, status="ok", value=None, usage=None, error=None):
        data = {"status": status, "output": payload(value) if value is not None else {"state": "unavailable", "reason": "not_supplied"}}
        if usage:
            data["usage"] = usage
        if error:
            data["error"] = {"type": "ValueError", "code": "invalid_argument"}
        emit(at_ms, "span.ended", data, key)

    emit(0, "capture.started", {
        "recorder_version": "0.1.0", "capture_mode": "native_lifecycle", "privacy_mode": "selected_content",
        "coverage": "Synthetic fixture. No live models, tools, payments, or customer data.",
        "source": {"name": "afr-synthetic-demo", "version": "0.1.0"},
        "limits": {"max_file_bytes": 26214400, "max_events": 10000, "max_event_bytes": 65536, "max_payload_bytes": 8192, "max_depth": 20},
    })

    if scenario == "interrupted":
        start(0, "run", "run", "Research a delivery delay", value={"request": "Check the synthetic order and shipping status."})
        start(10, "agent", "agent", "Support agent", "run")
        start(30, "model", "model", "Plan parallel lookups", "agent", attrs={"provider": "synthetic", "model": "scripted-demo"})
        end(480, "model", value={"tools": ["lookup_order", "lookup_shipment"]}, usage={"input_tokens": 402, "output_tokens": 61})
        start(500, "order", "tool", "Look up order", "agent", {"order_id": "DEMO-2048"}, {"tool_name": "lookup_order"})
        start(515, "shipment", "tool", "Look up shipment", "agent", {"shipment_id": "DEMO-SHIP-104"}, {"tool_name": "lookup_shipment"})
        end(1030, "order", value={"status": "shipped", "synthetic": True})
        emit(1510, "event.recorded", {"name": "Last observed checkpoint", "payload": payload({"note": "The fixture stops here. The shipment result and agent outcome were not recorded."})}, "agent")
        # Deliberately no tool end, root end, or capture closure.
        return events

    start(0, "run", "run", "Resolve a duplicate charge", value={"request": "Refund the duplicate $42 charge on demo order 2048."})
    start(12, "agent", "agent", "Refund support agent", "run")
    start(30, "policy", "retrieval", "Retrieve refund policy", "agent", {"query": "duplicate charge refund policy"})
    end(195, "policy", value={"refund_unit": "integer cents", "max_attempts": 2, "source": "synthetic policy"})
    start(215, "model", "model", "Select refund action", "agent", attrs={"provider": "synthetic", "model": "scripted-demo"})
    amount = "42.00" if scenario == "failure" else 4200
    args = {"order_id": "DEMO-2048", "amount_cents": amount}
    end(780, "model", value={"tool": "issue_refund", "arguments": args}, usage={"input_tokens": 680, "output_tokens": 94})
    start(800, "refund1", "tool", "Issue refund · attempt 1", "agent", args, {"tool_name": "issue_refund", "attempt": 1, "tool_call_id": "demo-call-1"})
    if scenario == "success":
        end(1120, "refund1", value={"refunded_cents": 4200, "receipt": "SYNTHETIC-NO-PAYMENT"})
        start(1140, "reply", "model", "Prepare confirmation", "agent", attrs={"provider": "synthetic", "model": "scripted-demo"})
        end(1650, "reply", value={"message": "The synthetic refund was accepted."}, usage={"input_tokens": 804, "output_tokens": 42})
        end(1660, "agent", value={"result": "synthetic success"})
        end(1675, "run", value={"result": "synthetic success"})
        finish_at = 1680
    else:
        end(890, "refund1", "error", error=True)
        emit(900, "event.recorded", {"name": "Validation rejected the argument", "payload": payload({"field": "amount_cents", "expected": "integer", "observed": "string"})}, "refund1")
        start(920, "retry", "model", "Prepare retry", "agent", attrs={"provider": "synthetic", "model": "scripted-demo"})
        end(1420, "retry", value={"tool": "issue_refund", "arguments": args}, usage={"input_tokens": 892, "output_tokens": 87})
        start(1440, "refund2", "tool", "Issue refund · attempt 2", "agent", args,
              {"tool_name": "issue_refund", "attempt": 2, "tool_call_id": "demo-call-2", "retry_of": sid("refund1")},
              [{"span_id": sid("refund1"), "relation": "retry_of"}])
        end(1530, "refund2", "error", error=True)
        emit(1540, "event.recorded", {"name": "Attempt limit reached", "payload": payload({"attempts": 2, "note": "Both observed tool calls used a string for amount_cents. No real refund was attempted."})}, "agent")
        end(1560, "agent", "error", error=True)
        end(1570, "run", "error", error=True)
        finish_at = 1580
    emit(finish_at, "capture.ended", {"written_events": len(events) + 1, "skipped_events": 0, "failed_events": 0, "limit_reached": False})
    return events
