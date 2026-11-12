"""Explicit, synchronous, fail-open observation of one local agent run."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .privacy import MAX_SAFE_INTEGER, MISSING, PrivacyPolicy


_SPAN_ID = re.compile(r"[0-9a-f]{16}\Z")
_KINDS = frozenset({"run", "agent", "model", "tool", "retrieval", "step"})
_CLOSURE_BYTES = 1024


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 25 * 1024 * 1024
    max_events: int = 10000
    max_event_bytes: int = 64 * 1024
    max_payload_bytes: int = 8192
    max_depth: int = 20

    def __post_init__(self):
        bounds = {
            "max_file_bytes": (2048, 25 * 1024 * 1024),
            "max_events": (2, 10000),
            "max_event_bytes": (1024, 64 * 1024),
            "max_payload_bytes": (1, 8192),
            "max_depth": (3, 20),
        }
        for name, (minimum, maximum) in bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")


def _valid_span_id(value: object) -> bool:
    return type(value) is str and bool(_SPAN_ID.fullmatch(value)) and value != "0" * 16


class Recorder:
    """Write a new private JSONL artifact without running agent operations.

    Runtime recorder failures are reported through ``health`` and one static
    warning; they do not replace an exception raised by the observed code.
    Existing destinations and invalid configuration are rejected before use.
    Appends are synchronous and flushed, not fsynced or crash-proof.
    """

    def __init__(
        self, path: str | Path, *, capture_content: bool = False,
        limits: Limits | None = None, privacy: PrivacyPolicy | None = None,
        redact_keys: tuple[str, ...] | list[str] = (),
        redact_patterns: tuple[str, ...] | list[str] = (),
    ) -> None:
        self.path = Path(path)
        if limits is not None and type(limits) is not Limits:
            raise ValueError("limits must be a Limits instance")
        self.limits = limits or Limits()
        if privacy is not None and type(privacy) is not PrivacyPolicy:
            raise ValueError("privacy must be a PrivacyPolicy instance")
        base_policy = privacy or PrivacyPolicy(capture_content, redact_keys, redact_patterns)
        self.privacy = base_policy.with_limits(
            max_payload_bytes=self.limits.max_payload_bytes,
            max_depth=self.limits.max_depth - 3,
        )
        self.recording_id = str(uuid.uuid4())
        self.trace_id = uuid.uuid4().hex
        self._lock = threading.RLock()
        self._parent = contextvars.ContextVar(f"afr_parent_{self.recording_id}", default=None)
        self._pid = os.getpid()
        self._file = None
        self._entered = False
        self._closed = False
        self._disabled = False
        self._limit_reached = False
        self._warned = False
        self._warnings: list[str] = []
        self._seq = self._written = self._skipped = self._failed = self._bytes = 0
        self._origin_ns = time.monotonic_ns()
        self._root_claimed = False

    @property
    def health(self) -> dict:
        if os.getpid() != self._pid:
            self._process_ok()
            return self._health_snapshot()
        with self._lock:
            return self._health_snapshot()

    def _health_snapshot(self) -> dict:
        return {
            "written_events": self._written, "skipped_events": self._skipped,
            "failed_events": self._failed, "limit_reached": self._limit_reached,
            "disabled": self._disabled, "warnings": list(self._warnings),
        }

    def _notice(self, code: str) -> None:
        if code not in self._warnings and len(self._warnings) < 16:
            self._warnings.append(code)
        if not self._warned:
            self._warned = True
            try:
                os.write(2, b"Agent Flight Recorder: recording degraded; inspect recorder.health.\n")
            except Exception:
                pass

    def _process_ok(self) -> bool:
        if os.getpid() == self._pid:
            return True
        # Check before acquiring a potentially inherited, locked mutex.
        if not self._disabled:
            self._failed += 1
        self._disabled = True
        self._notice("process_mismatch")
        return False

    def __enter__(self) -> Recorder:
        if self._entered or self._closed:
            raise RuntimeError("A recorder can only be entered once")
        if not self._process_ok():
            return self
        self._entered = True
        self._origin_ns = time.monotonic_ns()
        try:
            missing = []
            directory = self.path.parent
            while not directory.exists():
                missing.append(directory)
                directory = directory.parent
            for directory in reversed(missing):
                try:
                    directory.mkdir(mode=0o700)
                except FileExistsError:
                    if not directory.is_dir():
                        raise
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600)
            try:
                self._file = os.fdopen(fd, "wb", buffering=0)
            except Exception:
                os.close(fd)
                raise
        except FileExistsError:
            raise FileExistsError("Recording destination already exists; choose a new file") from None
        except Exception:
            self._failed += 1
            self._disabled = True
            self._notice("open_failure")
        self._emit("capture.started", {
            "recorder_version": "0.1.0", "capture_mode": "native_lifecycle",
            "privacy_mode": "selected_content" if self.privacy.capture_content else "metadata_only",
            "coverage": "explicit_instrumented_boundaries", "limits": asdict(self.limits),
        })
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if not self._process_ok():
            return
        with self._lock:
            if self._closed:
                return
            try:
                if self._entered:
                    self._emit("capture.ended", {}, final=True)
            finally:
                self._closed = True
                if self._file is not None:
                    try:
                        self._file.close()
                    except Exception:
                        self._failed += 1
                        self._disabled = True
                        self._notice("close_failure")

    def _emit(self, event_type: str, data: dict, *, span_id=None, parent_span_id=None, final=False) -> bool:
        if not self._process_ok():
            self._skipped += 1
            return False
        with self._lock:
            self._seq += 1
            if self._disabled or self._closed or not self._entered or self._file is None:
                self._skipped += 1
                if not self._entered or self._closed:
                    self._notice("inactive_recorder")
                return False
            if self._limit_reached and not final:
                self._skipped += 1
                return False
            try:
                if final:
                    data = {
                        "written_events": self._written + 1, "skipped_events": self._skipped,
                        "failed_events": self._failed, "limit_reached": self._limit_reached,
                    }
                event = {
                    "schema_version": "0.1", "recording_id": self.recording_id,
                    "trace_id": self.trace_id, "event_id": str(uuid.uuid4()),
                    "seq": self._seq, "type": event_type,
                    "recorded_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    "elapsed_us": max(0, (time.monotonic_ns() - self._origin_ns) // 1000),
                    "data": data,
                }
                if span_id is not None:
                    event["span_id"] = span_id
                if parent_span_id is not None:
                    event["parent_span_id"] = parent_span_id
                line = self._encode(event)
                if len(line) > self.limits.max_event_bytes:
                    # Preserve lifecycle evidence when opted-in content is too large.
                    for key in ("input", "output", "payload"):
                        if key in data:
                            data[key] = {"state": "omitted", "reason": "event_limit", "truncated": True}
                    line = self._encode(event)
                    self._notice("content_event_limit")
                event_budget = self.limits.max_events if final else self.limits.max_events - 1
                byte_budget = self.limits.max_file_bytes if final else self.limits.max_file_bytes - _CLOSURE_BYTES
                if self._written >= event_budget or len(line) > self.limits.max_event_bytes or self._bytes + len(line) > byte_budget:
                    self._limit_reached = True
                    self._skipped += 1
                    self._notice("capture_limit")
                    return False
                written = self._file.write(line)
                if written != len(line):
                    raise OSError("incomplete recording write")
                self._file.flush()
                self._written += 1
                self._bytes += len(line)
                return True
            except Exception:
                self._failed += 1
                self._disabled = True
                self._notice("write_failure")
                return False

    @staticmethod
    def _encode(event: dict) -> bytes:
        return (json.dumps(event, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")

    def _payload(self, value) -> dict:
        try:
            result = self.privacy.payload(value)
            if result.get("reason") == "filter_failure":
                self._notice("privacy_failure")
            return result
        except Exception:
            self._notice("privacy_failure")
            return {"state": "omitted", "reason": "filter_failure"}

    def _skip_observation(self, code: str) -> None:
        """Keep intentionally discarded boundaries visible in the artifact."""
        if not self._process_ok():
            return
        with self._lock:
            self._seq += 1
            self._skipped += 1
            self._notice(code)

    def _label(self, value) -> str:
        try:
            return self.privacy.label(value)
        except Exception:
            self._notice("privacy_failure")
            return "label_unavailable"

    def run(self, name: str, *, input=MISSING, attributes=None) -> Span:
        return Span(self, "run", name, input=input, attributes=attributes, root=True)

    def span(self, kind: str, name: str, *, input=MISSING, attributes=None, parent_span_id=None, links=None) -> Span:
        return Span(self, kind, name, input=input, attributes=attributes, parent_span_id=parent_span_id, links=links)

    def event(self, name: str, *, payload=MISSING, span_id=None) -> None:
        if span_id is None:
            span_id = self._parent.get()
        elif not _valid_span_id(span_id):
            span_id = None
            self._notice("invalid_span_id")
        self._emit("event.recorded", {"name": self._label(name), "payload": self._payload(payload)}, span_id=span_id)


class Span:
    """One observation scope; create a fresh instance for each operation.

    A scope must not be shared across threads or asynchronous tasks. It never
    calls a model or tool itself. Reuse runs the body but records skipped
    boundaries instead of inventing another operation with the same ID.
    """

    def __init__(self, recorder: Recorder, kind, name, *, input=MISSING, attributes=None, parent_span_id=None, links=None, root=False):
        self.recorder = recorder
        self.span_id = None
        self._kind = kind
        self._name = name
        self._input = input
        self._attributes = attributes
        self._explicit_parent = parent_span_id
        self._links = links
        self._root = root
        self._entered = False
        self._entry_depth = 0
        self._ended = False
        self._token = None
        self._recording = True
        self._skipped_scope = False
        self._output = {"state": "unavailable", "reason": "not_supplied"}
        self._usage = {}
        if not recorder._process_ok():
            self._recording = False
        else:
            try:
                self.span_id = uuid.uuid4().hex[:16]
            except Exception:
                # ID allocation is recorder I/O too. An entropy-source
                # failure must not prevent the application scope from running.
                self._recording = False
                with recorder._lock:
                    recorder._failed += 1
                    recorder._disabled = True
                    recorder._notice("span_id_failure")

    def __enter__(self) -> Span:
        recorder = self.recorder
        if self._entered:
            self._entry_depth += 1
            recorder._skip_observation("reused_span")
            return self
        self._entered = True
        self._entry_depth = 1
        if not self._recording:
            return self
        if not recorder._process_ok():
            self._recording = False
            return self
        try:
            with recorder._lock:
                if self._root:
                    if recorder._root_claimed:
                        self._recording = False
                        self._skipped_scope = True
                        recorder._skip_observation("multiple_root_spans")
                        return self
                    recorder._root_claimed = True
                parent = None if self._root else recorder._parent.get()
                if self._explicit_parent is not None:
                    if _valid_span_id(self._explicit_parent):
                        parent = self._explicit_parent
                    else:
                        recorder._notice("invalid_parent_id")
                kind = self._kind if type(self._kind) is str and self._kind in _KINDS else "step"
                if kind == "run" and not self._root:
                    kind = "step"
                data = {"kind": kind, "name": recorder._label(self._name), "input": recorder._payload(self._input)}
                self._input = MISSING
                try:
                    attrs = recorder.privacy.attributes(self._attributes)
                    if attrs:
                        data["attributes"] = attrs
                except Exception:
                    recorder._notice("privacy_failure")
                self._attributes = None
                if type(self._links) in (list, tuple) and recorder.limits.max_depth >= 4:
                    links = []
                    for link in self._links[:64]:
                        if type(link) is dict and len(link) <= 8 and all(type(key) is str for key in link):
                            linked_id, relation = link.get("span_id"), link.get("relation")
                            if _valid_span_id(linked_id) and type(relation) is str and relation in ("retry_of", "follows_from"):
                                links.append({"span_id": linked_id, "relation": relation})
                    if links:
                        data["links"] = links
                self._links = None
                recorder._emit("span.started", data, span_id=self.span_id, parent_span_id=parent)
                self._token = recorder._parent.set(self.span_id)
        except Exception:
            recorder._notice("span_start_failure")
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if self._ended:
            if self._entry_depth:
                self._entry_depth -= 1
                self.recorder._skip_observation("reused_span")
            return False
        if self._entry_depth > 1:
            self._entry_depth -= 1
            self.recorder._skip_observation("reused_span")
            return False
        self._entry_depth = 0
        if not self._recording:
            self._ended = True
            if self._skipped_scope:
                self.recorder._skip_observation("multiple_root_spans")
            return False
        self._ended = True
        recorder = self.recorder
        try:
            status = "ok"
            data = {"status": status, "output": self._output}
            if exc is not None:
                actual_type = type(exc)
                data["status"] = "cancelled" if issubclass(actual_type, (asyncio.CancelledError, concurrent.futures.CancelledError, KeyboardInterrupt)) else "error"
                # Read the built-in type descriptor directly, without an
                # instance __class__ property or metaclass name override.
                error_name = type.__dict__["__name__"].__get__(actual_type)
                data["error"] = {"type": recorder._label(error_name)}
            if self._usage:
                data["usage"] = dict(self._usage)
            recorder._emit("span.ended", data, span_id=self.span_id)
        except Exception:
            recorder._notice("span_end_failure")
        finally:
            if self._token is not None:
                try:
                    recorder._parent.reset(self._token)
                except Exception:
                    recorder._notice("context_reset_failure")
        return False

    def set_output(self, value) -> None:
        self._output = self.recorder._payload(value)

    def set_usage(self, *, input_tokens=MISSING, output_tokens=MISSING) -> None:
        for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
            if value is MISSING:
                continue
            if type(value) is int and 0 <= value <= MAX_SAFE_INTEGER:
                self._usage[name] = value
            else:
                self.recorder._notice("invalid_usage")

    def event(self, name: str, *, payload=MISSING) -> None:
        self.recorder.event(name, payload=payload, span_id=self.span_id)
