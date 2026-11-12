import asyncio
import json
import os
import select
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from agent_flight_recorder import Limits, PrivacyPolicy, Recorder


def read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_nested_recording_preserves_result_and_records_lifecycle(tmp_path):
    path = tmp_path / "run.jsonl"
    with Recorder(path, capture_content=True) as recorder:
        with recorder.run("demo") as root:
            with recorder.span("model", "respond", input={"question": "hello"}) as span:
                result = {"answer": "world"}
                span.set_output(result)
                span.set_usage(input_tokens=3, output_tokens=4)
                span.event("checkpoint", payload={"attempt": 1})
            root.set_output("done")
    assert result == {"answer": "world"}
    events = read_events(path)
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "capture.started"
    assert events[-1]["type"] == "capture.ended"
    assert events[-1]["data"]["written_events"] == len(events)
    child_start = next(event for event in events if event["type"] == "span.started" and event["span_id"] == span.span_id)
    assert child_start["parent_span_id"] == root.span_id
    child_end = next(event for event in events if event["type"] == "span.ended" and event["span_id"] == span.span_id)
    assert child_end["data"]["usage"] == {"input_tokens": 3, "output_tokens": 4}
    assert child_end["data"]["output"]["value"] == result
    assert not recorder.health["warnings"]
    assert [event["elapsed_us"] for event in events] == sorted(event["elapsed_us"] for event in events)


def test_default_capture_does_not_leak_payload_error_or_arbitrary_attributes(tmp_path):
    path = tmp_path / "run.jsonl"
    error = ValueError("SECRET_MESSAGE")
    with pytest.raises(ValueError) as caught:
        with Recorder(path) as recorder:
            with recorder.run("demo"):
                with recorder.span("tool", "lookup", input="SECRET_INPUT", attributes={"path": "SECRET_PATH"}) as span:
                    span.set_output("SECRET_OUTPUT")
                    span.event("note", payload="SECRET_NOTE")
                    raise error
    assert caught.value is error
    text = path.read_text()
    assert "SECRET_" not in text
    events = read_events(path)
    ends = [event for event in events if event["type"] == "span.ended"]
    assert all(event["data"]["status"] == "error" for event in ends)
    assert ends[0]["data"]["error"] == {"type": "ValueError"}
    assert events[-1]["type"] == "capture.ended"


def test_failing_start_write_does_not_skip_or_duplicate_operation(tmp_path, monkeypatch):
    path = tmp_path / "run.jsonl"
    calls = []

    class BrokenFile:
        def write(self, value):
            raise OSError("SECRET_DISK_DETAIL")

        def close(self):
            pass

    with Recorder(path) as recorder:
        original_file = recorder._file
        recorder._file = BrokenFile()
        try:
            with recorder.run("demo"):
                calls.append("called")
        finally:
            original_file.close()
    assert calls == ["called"]
    assert recorder.health["failed_events"] == 1
    assert recorder.health["disabled"]
    assert read_events(path)[-1]["type"] == "capture.started"


def test_disk_failure_does_not_replace_original_exception(tmp_path):
    error = RuntimeError("original")
    with pytest.raises(RuntimeError) as caught:
        with Recorder(tmp_path / "run.jsonl") as recorder:
            with recorder.run("demo"):
                recorder._file.close()
                raise error
    assert caught.value is error
    assert recorder.health["disabled"]


def test_span_id_failure_preserves_operation_and_original_exception(tmp_path, monkeypatch, capfd):
    path = tmp_path / "run.jsonl"
    calls = []
    original_error = RuntimeError("application error")

    def unavailable_entropy():
        raise OSError("SECRET_ENTROPY_DIAGNOSTIC")

    with Recorder(path) as recorder:
        monkeypatch.setattr("agent_flight_recorder.recorder.uuid.uuid4", unavailable_entropy)
        with pytest.raises(RuntimeError) as caught:
            with recorder.span("tool", "operation") as span:
                calls.append("performed exactly once")
                span.set_output("unused output")
                raise original_error
        assert caught.value is original_error
    assert calls == ["performed exactly once"]
    assert span.span_id is None
    assert recorder.health["disabled"]
    assert recorder.health["failed_events"] == 1
    assert "span_id_failure" in recorder.health["warnings"]
    assert [event["type"] for event in read_events(path)] == ["capture.started"]
    assert "SECRET_ENTROPY_DIAGNOSTIC" not in capfd.readouterr().err


def test_overlapping_redaction_and_key_collision_reach_file_without_raw_fallback(tmp_path):
    path = tmp_path / "run.jsonl"
    with Recorder(path, capture_content=True, redact_patterns=("abc", "bcd", "alpha", "beta")) as recorder:
        with recorder.run("root", input={"alpha": "first", "beta": "second"}) as root:
            root.set_output("abcd")
    events = read_events(path)
    start = next(event for event in events if event["type"] == "span.started")
    end = next(event for event in events if event["type"] == "span.ended")
    assert start["data"]["input"] == {"state": "omitted", "reason": "redaction_collision"}
    assert end["data"]["output"]["state"] == "redacted"
    assert all(secret not in path.read_text() for secret in ("alpha", "beta", "first", "second", "abcd"))


def test_surrogateescape_input_keys_and_labels_produce_readable_native_capture(tmp_path):
    from agent_flight_recorder.recording import load_recording

    path = tmp_path / "run.jsonl"
    surrogate = b"\xff".decode("utf-8", errors="surrogateescape")
    calls = []
    with Recorder(path, capture_content=True) as recorder:
        with recorder.run("root" + surrogate, input=surrogate) as root:
            calls.append("operation")
            with recorder.span("tool", "lookup", input={surrogate: "value"}, attributes={"model": surrogate}) as tool:
                tool.set_output({"nested": [surrogate]})
                tool.event("note" + surrogate, payload=surrogate)
            root.set_output("\U0001f600")
    loaded = load_recording(path)
    assert calls == ["operation"]
    assert not loaded["warnings"]
    starts = [event for event in loaded["events"] if event["type"] == "span.started"]
    assert starts[0]["data"]["name"] == "label_omitted"
    assert starts[0]["data"]["input"] == {"state": "unavailable", "reason": "unsupported_value"}
    assert starts[1]["data"]["input"] == {"state": "unavailable", "reason": "unsupported_value"}
    assert starts[1]["data"]["attributes"] == {"model": "label_omitted"}
    annotation = next(event for event in loaded["events"] if event["type"] == "event.recorded")
    assert annotation["data"]["name"] == "label_omitted"
    assert annotation["data"]["payload"]["reason"] == "unsupported_value"
    root_end = next(event for event in loaded["events"] if event["type"] == "span.ended" and event["span_id"] == root.span_id)
    assert root_end["data"]["output"]["value"] == "\U0001f600"
    assert "\\udcff" not in path.read_text()


def test_unwritable_open_is_fail_open_and_warning_contains_no_path(tmp_path, monkeypatch, capfd):
    def denied(*args, **kwargs):
        raise PermissionError("SECRET_PATH")

    calls = []
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "open", denied)
        with Recorder(tmp_path / "SECRET_PATH") as recorder:
            with recorder.run("demo"):
                calls.append(1)
    assert calls == [1]
    assert recorder.health["disabled"]
    assert "SECRET_PATH" not in capfd.readouterr().err


def test_existing_destination_is_never_overwritten(tmp_path):
    path = tmp_path / "existing.jsonl"
    path.write_text("preserve me")
    with pytest.raises(FileExistsError):
        with Recorder(path):
            pass
    assert path.read_text() == "preserve me"


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner permission model")
def test_new_directories_and_file_are_private(tmp_path):
    path = tmp_path / "one" / "two" / "run.jsonl"
    with Recorder(path):
        pass
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.parent.parent.stat().st_mode) == 0o700


def test_event_limit_reserves_closure_and_reports_missing_operations(tmp_path):
    path = tmp_path / "run.jsonl"
    with Recorder(path, limits=Limits(max_events=4)) as recorder:
        with recorder.run("root"):
            with recorder.span("tool", "last"):
                recorder.event("beyond limit")
    events = read_events(path)
    assert len(events) == 4
    assert events[-1]["type"] == "capture.ended"
    assert events[-1]["data"]["limit_reached"] is True
    assert events[-1]["data"]["skipped_events"] == 3
    assert not any(event["type"] == "span.ended" for event in events)
    assert events[-1]["seq"] > len(events)


def test_file_limit_reserves_final_summary(tmp_path):
    path = tmp_path / "run.jsonl"
    limits = Limits(max_file_bytes=3000)
    with Recorder(path, limits=limits) as recorder:
        with recorder.run("root"):
            for index in range(40):
                recorder.event("event")
    events = read_events(path)
    assert path.stat().st_size <= limits.max_file_bytes
    assert events[-1]["type"] == "capture.ended"
    assert recorder.health["limit_reached"]


def test_oversize_content_is_omitted_but_operation_survives(tmp_path):
    path = tmp_path / "run.jsonl"
    with Recorder(path, capture_content=True) as recorder:
        with recorder.run("root"):
            with recorder.span("tool", "lookup", input="SECRET" * 10000):
                pass
    events = read_events(path)
    start = next(event for event in events if event["type"] == "span.started" and event["data"]["kind"] == "tool")
    assert start["data"]["input"] == {"state": "omitted", "reason": "payload_limit", "truncated": True}
    assert "SECRET" not in path.read_text()


def test_event_size_limit_reduces_payload_before_dropping_lifecycle(tmp_path):
    path = tmp_path / "run.jsonl"
    with Recorder(path, capture_content=True, limits=Limits(max_event_bytes=1024)) as recorder:
        with recorder.run("root"):
            with recorder.span("tool", "lookup", input="a" * 2000):
                pass
    events = read_events(path)
    tool = next(event for event in events if event["type"] == "span.started" and event["data"]["kind"] == "tool")
    assert tool["data"]["input"]["reason"] == "event_limit"
    assert all(len(line) + 1 <= 1024 for line in path.read_bytes().splitlines())
    assert events[-1]["data"]["limit_reached"] is False


def test_small_depth_limit_applies_to_complete_event_not_just_payload(tmp_path):
    path = tmp_path / "run.jsonl"
    with Recorder(path, capture_content=True, limits=Limits(max_depth=3)) as recorder:
        with recorder.run("root") as root:
            with recorder.span("tool", "lookup", input=[1], attributes={"provider": "demo"}, links=[{"span_id": root.span_id, "relation": "follows_from"}]) as span:
                span.set_output("scalar")

    def depth(value):
        if type(value) is dict:
            return 1 + max((depth(item) for item in value.values()), default=0)
        if type(value) is list:
            return 1 + max((depth(item) for item in value), default=0)
        return 0

    assert all(depth(event) <= 3 for event in read_events(path))


def test_filter_failures_do_not_prevent_operation(tmp_path, monkeypatch):
    path = tmp_path / "run.jsonl"
    calls = []
    with Recorder(path, capture_content=True) as recorder:
        def broken(_):
            raise ValueError("SECRET_FILTER_DETAIL")

        monkeypatch.setattr(recorder.privacy, "payload", broken)
        with recorder.run("root", input="SECRET_INPUT"):
            calls.append(1)
    assert calls == [1]
    assert "SECRET_" not in path.read_text()
    assert "privacy_failure" in recorder.health["warnings"]


def test_async_parent_contexts_and_cancellation_are_preserved(tmp_path):
    path = tmp_path / "run.jsonl"
    identities = {}

    async def work():
        with Recorder(path) as recorder:
            with recorder.run("root") as root:
                identities["root"] = root.span_id

                async def child(name):
                    with recorder.span("tool", name) as span:
                        identities[name] = span.span_id
                        await asyncio.sleep(0)
                        with recorder.span("step", name + " nested") as nested:
                            identities[name + " nested"] = nested.span_id
                            await asyncio.sleep(0)

                await asyncio.gather(child("a"), child("b"))
                cancellation = asyncio.CancelledError("SECRET_CANCEL")
                with pytest.raises(asyncio.CancelledError) as caught:
                    with recorder.span("tool", "cancelled"):
                        raise cancellation
                assert caught.value is cancellation

    asyncio.run(work())
    events = read_events(path)
    starts = {event["span_id"]: event for event in events if event["type"] == "span.started"}
    for name in ("a", "b"):
        assert starts[identities[name]]["parent_span_id"] == identities["root"]
        assert starts[identities[name + " nested"]]["parent_span_id"] == identities[name]
    assert any(event["type"] == "span.ended" and event["data"]["status"] == "cancelled" for event in events)
    assert "SECRET_CANCEL" not in path.read_text()


def test_threads_use_explicit_parent_and_writer_sequence_is_serial(tmp_path):
    path = tmp_path / "run.jsonl"
    with Recorder(path) as recorder:
        with recorder.run("root") as root:
            def child():
                with recorder.span("tool", "worker", parent_span_id=root.span_id):
                    recorder.event("inside")

            threads = [threading.Thread(target=child) for _ in range(12)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
                assert not thread.is_alive()
    events = read_events(path)
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    workers = [event for event in events if event["type"] == "span.started" and event["data"]["kind"] == "tool"]
    assert len(workers) == 12
    assert all(event["parent_span_id"] == root.span_id for event in workers)


def test_all_relationships_within_the_declared_link_limit_are_preserved(tmp_path):
    path = tmp_path / "run.jsonl"
    links = []
    with Recorder(path) as recorder:
        with recorder.run("root"):
            for _ in range(64):
                with recorder.span("step", "prior operation") as prior:
                    links.append({"span_id": prior.span_id, "relation": "follows_from"})
            with recorder.span("step", "aggregate", links=links) as aggregate:
                pass
    start = next(event for event in read_events(path) if event["type"] == "span.started" and event["span_id"] == aggregate.span_id)
    assert start["data"]["links"] == links
    assert not recorder.health["warnings"]


def test_process_reuse_rejects_writing_before_taking_lock(tmp_path, monkeypatch):
    path = tmp_path / "run.jsonl"
    with Recorder(path) as recorder:
        size = path.stat().st_size
        original_pid = recorder._pid
        monkeypatch.setattr(recorder, "_pid", original_pid + 1)
        recorder.event("child must not write")
        assert path.stat().st_size == size
        assert "process_mismatch" in recorder.health["warnings"]
        monkeypatch.setattr(recorder, "_pid", original_pid)


def test_active_span_can_remain_incomplete_when_capture_is_closed(tmp_path):
    path = tmp_path / "run.jsonl"
    with Recorder(path) as recorder:
        with recorder.run("root"):
            recorder.close()
    events = read_events(path)
    assert events[-1]["type"] == "capture.ended"
    assert not any(event["type"] == "span.ended" for event in events)


def test_rejected_second_run_is_visible_as_capture_loss_without_changing_its_body(tmp_path):
    from agent_flight_recorder.recording import load_recording

    path = tmp_path / "run.jsonl"
    calls = []
    original_error = RuntimeError("second operation failure")
    with Recorder(path) as recorder:
        with recorder.run("first"):
            calls.append("first")
        with pytest.raises(RuntimeError) as caught:
            with recorder.run("second"):
                calls.append("second")
                raise original_error
        assert caught.value is original_error
    events = read_events(path)
    assert calls == ["first", "second"]
    assert [event["data"]["name"] for event in events if event["type"] == "span.started"] == ["first"]
    assert events[-1]["data"]["skipped_events"] == 2
    assert events[-1]["seq"] == len(events) + 2
    assert recorder.health["skipped_events"] == 2
    assert {warning["code"] for warning in load_recording(path)["warnings"]} >= {"sequence_gap", "recording_loss"}


@pytest.mark.parametrize("nested", [False, True], ids=["sequential_reuse", "nested_reuse"])
def test_reused_span_boundaries_are_reported_without_duplicate_ids_or_context_leaks(tmp_path, nested):
    path = tmp_path / "run.jsonl"
    calls = []
    with Recorder(path) as recorder:
        with recorder.run("root") as root:
            span = recorder.span("tool", "first operation")
            with span:
                calls.append("first")
                if nested:
                    with span:
                        calls.append("second")
            if not nested:
                with span:
                    calls.append("second")
            with recorder.span("step", "after reuse") as after:
                pass
    events = read_events(path)
    assert calls == ["first", "second"]
    assert len([event for event in events if event.get("span_id") == span.span_id]) == 2
    after_start = next(event for event in events if event["type"] == "span.started" and event["span_id"] == after.span_id)
    assert after_start["parent_span_id"] == root.span_id
    assert events[-1]["data"]["skipped_events"] == 2
    assert events[-1]["seq"] == len(events) + 2
    assert "reused_span" in recorder.health["warnings"]


def test_unsupported_object_error_strings_and_links_never_invoke_user_code(tmp_path):
    class Hostile:
        def __repr__(self):
            raise AssertionError("repr")

        def __str__(self):
            raise AssertionError("str")

        def __iter__(self):
            raise AssertionError("iteration")

    class HostileError(Exception):
        @property
        def __class__(self):
            raise AssertionError("error class introspection")

        def __str__(self):
            raise AssertionError("error str")

    path = tmp_path / "run.jsonl"
    error = HostileError()
    with pytest.raises(HostileError) as caught:
        with Recorder(path, capture_content=True) as recorder:
            with recorder.run("root"):
                with recorder.span(Hostile(), Hostile(), input=Hostile(), attributes=Hostile(), links=Hostile()) as span:
                    span.set_output(Hostile())
                    span.set_usage(input_tokens=Hostile())
                    raise error
    assert caught.value is error
    assert "unsupported_value" in path.read_text()


@pytest.mark.skipif(os.name != "posix", reason="controlled process-kill fixture")
def test_flushed_start_survives_controlled_process_kill(tmp_path):
    path = tmp_path / "killed.jsonl"
    code = """
import sys, time
from agent_flight_recorder import Recorder
with Recorder(sys.argv[1]) as recorder:
    with recorder.run('interrupted'):
        with recorder.span('tool', 'waiting'):
            print('flushed', flush=True)
            time.sleep(30)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    process = subprocess.Popen([sys.executable, "-c", code, str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        assert select.select([process.stdout], [], [], 5)[0]
        assert process.stdout.readline() == b"flushed\n"
        process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
    events = read_events(path)
    assert [event["type"] for event in events] == ["capture.started", "span.started", "span.started"]
    assert not any(event["type"] == "capture.ended" for event in events)


@pytest.mark.parametrize("kwargs", [{"max_events": 1}, {"max_file_bytes": 100}, {"max_depth": 30}, {"max_events": True}])
def test_limits_reject_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        Limits(**kwargs)
