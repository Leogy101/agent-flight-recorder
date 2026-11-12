import json
import math

import pytest

from agent_flight_recorder.privacy import MISSING, PrivacyPolicy


def test_default_omits_content_without_inspecting_it():
    class Hostile:
        def __repr__(self):
            raise AssertionError("representation must not run")

    policy = PrivacyPolicy()
    assert policy.payload(Hostile()) == {"state": "omitted", "reason": "policy"}
    assert policy.payload(MISSING) == {"state": "unavailable", "reason": "not_supplied"}


def test_opt_in_preserves_empty_and_null_and_redacts_nested_credentials():
    policy = PrivacyPolicy(capture_content=True, redact_keys=("private_field",), redact_patterns=("demo-secret",))
    descriptor = policy.payload({
        "password": "never-persist", "nested": [{"private_field": "never-persist"}],
        "text": "prefix demo-secret suffix", "empty": "", "nothing": None,
    })
    assert descriptor["state"] == "captured"
    assert descriptor["value"]["empty"] == ""
    assert descriptor["value"]["nothing"] is None
    serialized = json.dumps(descriptor)
    assert "never-persist" not in serialized and "demo-secret" not in serialized
    assert descriptor["redacted_fields"] == 3
    assert policy.payload(None) == {"state": "captured", "value": None}


def test_substring_rules_are_literal_and_apply_to_metadata():
    policy = PrivacyPolicy(True, redact_patterns=("a.*b",))
    assert policy.payload("a.*b")["state"] == "redacted"
    assert policy.payload("axyzb")["value"] == "axyzb"
    assert policy.label("contains a.*b") == "contains [REDACTED]"
    assert policy.attributes({"model": "a.*b", "other": "never"}) == {"model": "[REDACTED]"}


@pytest.mark.parametrize("factory", [
    lambda: type("EvilList", (list,), {"__iter__": lambda self: (_ for _ in ()).throw(AssertionError())})([1]),
    lambda: type("EvilDict", (dict,), {"items": lambda self: (_ for _ in ()).throw(AssertionError())})({"a": 1}),
    lambda: type("EvilStr", (str,), {"__str__": lambda self: (_ for _ in ()).throw(AssertionError())})("secret"),
    lambda: type("EvilInt", (int,), {"__str__": lambda self: (_ for _ in ()).throw(AssertionError())})(4),
    lambda: iter([1, 2]),
    lambda: object(),
])
def test_unknown_objects_and_builtin_subclasses_are_not_invoked(factory):
    value = factory()
    policy = PrivacyPolicy(True)
    assert policy.payload(value)["reason"] == "unsupported_value"
    assert policy.label(value) == "unnamed"
    assert policy.attributes(value) == {}


def test_dict_keys_cannot_invoke_custom_equality_during_attribute_filtering():
    class Key:
        def __hash__(self):
            return hash("provider")

        def __eq__(self, other):
            raise AssertionError("lookup must not compare custom keys")

    value = {Key(): "secret"}
    policy = PrivacyPolicy(True)
    assert policy.attributes(value) == {}
    assert policy.payload(value)["reason"] == "unsupported_value"


def test_cycles_depth_and_size_are_bounded_without_partial_secret_prefixes():
    cyclic = []
    cyclic.append(cyclic)
    policy = PrivacyPolicy(True, max_payload_bytes=32, max_depth=2)
    assert policy.payload(cyclic)["reason"] == "cyclic_value"
    assert policy.payload([[[1]]])["reason"] == "payload_limit"
    assert policy.payload("secret" * 100)["reason"] == "payload_limit"
    assert policy.payload([None] * 10000)["reason"] == "payload_limit"
    assert "secret" not in json.dumps(policy.payload("secret" * 100))
    for value in ("é" * 20, {"small": "v" * 28}):
        assert policy.payload(value)["reason"] == "payload_limit"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 2**53, -(2**53), 1e50, 10**10000], ids=["nan", "infinity", "negative_infinity", "large_int", "negative_large_int", "large_integral_float", "enormous_int"])
def test_nonportable_numbers_are_unavailable(value):
    assert PrivacyPolicy(True).payload(value)["reason"] == "unsupported_value"


def test_repeated_shared_value_is_not_mistaken_for_a_cycle():
    value = [1, 2]
    assert PrivacyPolicy(True).payload([value, value])["value"] == [[1, 2], [1, 2]]


def test_hostile_keys_are_removed_without_touching_values():
    result = PrivacyPolicy(True).payload({"__proto__": object(), "safe": 1})
    assert result["value"] == {"safe": 1}
    assert result["redacted_fields"] == 1


def test_filter_failure_never_falls_back_to_raw_content(monkeypatch):
    policy = PrivacyPolicy(True)

    def fail(_):
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(policy, "_filter_string", fail)
    assert policy.payload("sensitive") == {"state": "omitted", "reason": "filter_failure"}


def test_large_metadata_and_unknown_attributes_are_omitted():
    policy = PrivacyPolicy(True)
    assert policy.label("x" * 257) == "label_omitted"
    assert policy.attributes({"model": "x" * 257, "secret": "value", "attempt": True}) == {}
    assert policy.attributes({"attempt": 3, "provider": "demo"}) == {"attempt": 3, "provider": "demo"}


def test_replacement_growth_is_bounded_and_filtered_ids_stay_valid():
    policy = PrivacyPolicy(True, redact_patterns=("E",) * 64)
    assert policy.payload("E" * 100)["reason"] == "payload_limit"
    assert policy.label("E" * 100) == "label_omitted"
    policy = PrivacyPolicy(True, redact_patterns=("abcd",))
    assert policy.attributes({"retry_of": "abcd123412341234"}) == {}
    assert policy.attributes({"retry_of": "not-an-id"}) == {}


@pytest.mark.parametrize("kwargs", [
    {"redact_patterns": ("",)}, {"redact_keys": "password"},
    {"max_depth": -1}, {"max_payload_bytes": 9000}, {"capture_content": 1},
])
def test_invalid_policy_configuration_is_explicit(kwargs):
    with pytest.raises(ValueError):
        PrivacyPolicy(**kwargs)
