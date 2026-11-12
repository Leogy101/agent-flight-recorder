"""Bounded, opt-in payload collection. This is minimization, not a secrecy guarantee."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


MISSING = object()
MAX_SAFE_INTEGER = 2**53 - 1
_DEFAULT_REDACT_KEYS = frozenset({
    "password", "passwd", "secret", "token", "access_token", "refresh_token",
    "api_key", "apikey", "authorization", "cookie", "set_cookie", "credentials",
})
_UNSAFE_KEYS = frozenset({"__proto__", "prototype", "constructor"})
_ATTRIBUTE_STRINGS = frozenset({
    "provider", "model", "tool_name", "tool_call_id", "retry_of", "otel_span_kind",
})


class _Unsupported(Exception):
    pass


class _Limit(Exception):
    pass


class _Cycle(Exception):
    pass


@dataclass
class _Budget:
    remaining: int
    redacted: int = 0

    def charge(self, count: int) -> None:
        self.remaining -= count
        if self.remaining < 0:
            raise _Limit


class PrivacyPolicy:
    """Collect exact built-ins only, with bounded recursive filtering.

    ``redact_patterns`` contains literal, case-sensitive sensitive substrings,
    not regular expressions. ``redact_keys`` adds case-insensitive key names
    to the credential-key defaults. Approved labels/attributes are metadata:
    callers must not assume unknown secrets in them will be recognized.
    Oversized payloads are omitted wholesale instead of retaining a prefix.
    """

    def __init__(
        self,
        capture_content: bool = False,
        redact_keys: tuple[str, ...] | list[str] = (),
        redact_patterns: tuple[str, ...] | list[str] = (),
        *,
        max_payload_bytes: int = 8192,
        max_depth: int = 20,
    ) -> None:
        if type(capture_content) is not bool:
            raise ValueError("capture_content must be a boolean")
        if type(max_payload_bytes) is not int or not 1 <= max_payload_bytes <= 8192:
            raise ValueError("max_payload_bytes must be between 1 and 8192")
        if type(max_depth) is not int or not 0 <= max_depth <= 20:
            raise ValueError("max_depth must be between 0 and 20")
        for values in (redact_keys, redact_patterns):
            if type(values) not in (tuple, list) or len(values) > 64:
                raise ValueError("redaction rules must be a bounded list or tuple")
            if any(type(value) is not str or not 1 <= len(value) <= 256 for value in values):
                raise ValueError("redaction rules must be nonempty strings up to 256 characters")
        self.capture_content = capture_content
        self.max_payload_bytes = max_payload_bytes
        self.max_depth = max_depth
        self.redact_keys = tuple(redact_keys)
        self.redact_patterns = tuple(redact_patterns)
        self._keys = _DEFAULT_REDACT_KEYS | frozenset(self._key(key) for key in redact_keys)

    @staticmethod
    def _key(value: str) -> str:
        return value.casefold().replace("-", "_")

    def with_limits(self, *, max_payload_bytes: int, max_depth: int) -> PrivacyPolicy:
        return PrivacyPolicy(
            self.capture_content, self.redact_keys, self.redact_patterns,
            max_payload_bytes=min(self.max_payload_bytes, max_payload_bytes),
            max_depth=min(self.max_depth, max_depth),
        )

    def _filter_string(self, value: str) -> tuple[str, int]:
        count = 0
        for pattern in self.redact_patterns:
            occurrences = value.count(pattern)
            if occurrences:
                # Repeated short replacement rules must not expand input
                # exponentially. Check the exact replacement size first.
                expanded_size = len(value) + occurrences * (len("[REDACTED]") - len(pattern))
                if expanded_size > max(self.max_payload_bytes, 256):
                    raise _Limit
                value = value.replace(pattern, "[REDACTED]")
                count += occurrences
        return value, count

    def label(self, value: object) -> str:
        """Return bounded metadata without invoking unknown object behavior."""
        if type(value) is not str:
            return "unnamed"
        # Labels are caller-approved metadata, not arbitrary payloads. A long
        # label is omitted rather than cutting through a configured secret.
        if len(value) > 256:
            return "label_omitted"
        try:
            filtered, _ = self._filter_string(value)
        except _Limit:
            return "label_omitted"
        return filtered if len(filtered) <= 256 else "label_omitted"

    def attributes(self, mapping: object) -> dict:
        if type(mapping) is not dict or len(mapping) > 128:
            return {}
        result = {}
        # Do not use lookup on an unchecked dict: a hostile key with a
        # colliding hash could run its __eq__ against the lookup string.
        for key, value in mapping.items():
            if type(key) is not str:
                continue
            if key == "retry_of" and (type(value) is not str or len(value) != 16 or value == "0" * 16 or any(char not in "0123456789abcdef" for char in value)):
                continue
            if key in _ATTRIBUTE_STRINGS and type(value) is str and len(value) <= 256:
                filtered = self.label(value)
                if key != "retry_of" or filtered == value:
                    result[key] = filtered
            elif key == "attempt" and type(value) is int and 0 <= value <= MAX_SAFE_INTEGER:
                result[key] = value
        return result

    def payload(self, value: object = MISSING) -> dict:
        if value is MISSING:
            return {"state": "unavailable", "reason": "not_supplied"}
        if not self.capture_content:
            return {"state": "omitted", "reason": "policy"}
        budget = _Budget(self.max_payload_bytes)
        try:
            normalized = self._normalize(value, budget, 0, set())
            if normalized == "[REDACTED]" and budget.redacted:
                return {"state": "redacted", "reason": "configured_rule", "redacted_fields": budget.redacted}
            result = {"state": "captured", "value": normalized}
            if budget.redacted:
                result["redacted_fields"] = budget.redacted
            return result
        except _Limit:
            return {"state": "omitted", "reason": "payload_limit", "truncated": True}
        except _Cycle:
            return {"state": "unavailable", "reason": "cyclic_value"}
        except _Unsupported:
            return {"state": "unavailable", "reason": "unsupported_value"}
        except Exception:
            # A broken filter must never fall back to the unfiltered value.
            return {"state": "omitted", "reason": "filter_failure"}

    def _normalize(self, value: object, budget: _Budget, depth: int, active: set[int]):
        value_type = type(value)
        if value is None or value_type is bool:
            budget.charge(4 if value is None or value is True else 5)
            return value
        if value_type is int:
            if not -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
                raise _Unsupported
            budget.charge(len(str(value)))
            return value
        if value_type is float:
            if not math.isfinite(value) or (value.is_integer() and abs(value) > MAX_SAFE_INTEGER):
                raise _Unsupported
            budget.charge(len(json.dumps(value, allow_nan=False)))
            return value
        if value_type is str:
            if len(value) > self.max_payload_bytes:
                raise _Limit
            filtered, count = self._filter_string(value)
            budget.redacted += count
            budget.charge(len(json.dumps(filtered, ensure_ascii=True)))
            return filtered
        if value_type not in (list, tuple, dict):
            raise _Unsupported
        if depth >= self.max_depth or len(value) > self.max_payload_bytes:
            raise _Limit
        identity = id(value)
        if identity in active:
            raise _Cycle
        active.add(identity)
        try:
            budget.charge(2 + max(0, len(value) - 1))
            if value_type in (list, tuple):
                return [self._normalize(item, budget, depth + 1, active) for item in value]
            result = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise _Unsupported
                if len(key) > self.max_payload_bytes:
                    raise _Limit
                if key in _UNSAFE_KEYS:
                    budget.redacted += 1
                    continue
                safe_key, count = self._filter_string(key)
                budget.redacted += count
                budget.charge(len(json.dumps(safe_key, ensure_ascii=True)) + 1)
                if self._key(key) in self._keys:
                    budget.redacted += 1
                    budget.charge(12)
                    result[safe_key] = "[REDACTED]"
                else:
                    result[safe_key] = self._normalize(item, budget, depth + 1, active)
            return result
        finally:
            active.remove(identity)
