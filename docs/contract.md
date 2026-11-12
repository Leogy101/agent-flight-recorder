# Recording contract 0.1

Implementation baseline for the approved local recorder. All producers and consumers use this contract. UTF-8 JSONL, one trace and recording per file; exactly one JSON object per line; new files only. Version 0.1 is the only supported version in this release. Unknown fields are inert and subject to bounds.

## Envelope

Required: `schema_version: "0.1"`, `recording_id: UUID string`, `trace_id: 32 lowercase hex (nonzero)`, `event_id: UUID string`, `seq: positive safe integer`, `type`, `recorded_at: RFC3339 UTC timestamp`, `data: object`.

Native events also have `elapsed_us: nonnegative safe integer`. Imported events instead have optional `source_time: UTC RFC3339 with up to 9 fractional digits`. Span starts and ends require a nonzero 16-lowercase-hex `span_id`. A start may have `parent_span_id` in the same format. Optional span ID is allowed on an annotation. Never use conversion `recorded_at` to position imported spans.

## Event data

- `capture.started`: `recorder_version` (string), `capture_mode` (`native_lifecycle` or `imported_completed_spans`), `privacy_mode` (`metadata_only` or `selected_content`), `coverage` (static string), optional `source: {name,version}`, `limits: {max_file_bytes,max_events,max_event_bytes,max_payload_bytes,max_depth}`. Derived exports add `transform: {kind: "reduced_share", version: "0.1", source_issues: [static warning codes]}` and set privacy mode metadata_only.
- `span.started`: `kind` (`run`, `agent`, `model`, `tool`, `retrieval`, `step`), `name` (bounded static label), `input` (payload descriptor), optional `attributes` (allowlist below), optional `links: [{span_id,relation}]` with relation `retry_of` or `follows_from`. Import adds `reconstructed: true`.
- `span.ended`: `status` (`ok`, `error`, `cancelled`, `unknown`), `output` (payload descriptor), optional `usage: {input_tokens?,output_tokens?}` nonnegative safe integers, optional `error: {type: bounded static string,code?: bounded static string}`. Import adds `reconstructed: true`.
- `event.recorded`: `name` (bounded static label), `payload` (descriptor). No unfiltered free text in defaults.
- `capture.ended`: `written_events`, `skipped_events`, `failed_events` (nonnegative safe integers), `limit_reached` boolean. `written_events` includes this final marker. An imported closure means conversion completed, not the historical agent or capture was complete.

Payload descriptors always have `state` = `captured`, `omitted`, `redacted`, or `unavailable`. Only captured has `value` (including explicit null). Optional `reason` uses static codes; optional `truncated` boolean and `redacted_fields` count. Default descriptor is `{state:"omitted",reason:"policy"}`. Missing supplied value can be `{state:"unavailable",reason:"not_supplied"}`. Redaction failures omit content; never emit raw fallback. Redact before writing. Unknown object classes must not be stringified or iterated.

Allowed structural attributes: `provider`, `model`, `tool_name`, `tool_call_id`, `attempt`, `retry_of`, `otel_span_kind`. Strings are at most 256 characters; attempt is a nonnegative safe integer. Names are at most 256 characters. Metadata labels can be sensitive and are approved by caller; no automatic guarantee of secrecy. No arbitrary attrs, errors, headers, paths, or IDs from source resources.

## Bounds and evidence

Defaults: 25 MiB/file, 10,000 events, 64 KiB/line, 8 KiB/payload, JSON depth 20. Reserve a small closure budget in native writer. Reader refuses oversize data; JSON numbers must be finite and within JS safe integer bounds when integers. Parse errors use static messages/line numbers, not raw content. Python/TS readers detect duplicates, gaps, missing ends/parents, conflicting ends, parent cycles, source-clock anomalies, missing capture/root closure, and unsupported versions. Partial last JSON line is recoverable with warning; other bad lines need explicit partial-view acknowledgement. Never infer failure from missing end or OK from missing status.

Native seq is attempted observation order and elapsed_us is the axis. Imported seq is reconstructed order: source timestamp, starts before ends, span ID; ties are uncertain. Unavailable source times remain undated. Imported UNSET = unknown. Closure and agent outcome are separate.

## Public Python API

`from agent_flight_recorder import Recorder, Limits`

`with Recorder(path, capture_content=False) as recorder:` opens and closes capture; `with recorder.run("label") as run:` records a root span. `with recorder.span("tool", "lookup", input=..., attributes=..., parent_span_id=...) as span:` records child work. Contextvars maintain task parentage. Explicit parent_span_id supports threads. Each span exposes `.span_id`, `.set_output(value)`, `.set_usage(input_tokens=..., output_tokens=...)`, `.event(name, payload=...)`. `recorder.event(...)` also works outside spans. Sync context managers may be used inside async code. `recorder.health` exposes known recording degradation.

Recorder I/O/normalization failures preserve original exceptions/results and do not skip/duplicate application operations. One file one writer/process; new exclusive output with restrictive permissions; flushed append not fsync or crash-proof promise. No SDK runtime dependencies.

## Shared module interface

Core owner creates `privacy.py`, `recorder.py`, `__init__.py`. Privacy exports `PrivacyPolicy(capture_content=False, redact_keys=(), redact_patterns=())`, `.payload(value) -> descriptor`, `.attributes(mapping) -> dict`, `.label(value) -> str`, and `MISSING`. Recorder exports `Limits` dataclass with above field names.

Importer owner creates `otlp.py`, `recording.py`, own tests and interoperability docs. `load_recording(path_or_text, *, from_text=False, allow_partial=False)` returns `{events: list, warnings: list[dict(code,message,line?)], partial: bool}`. `validate_events(events)` returns warnings, raises ValueError on invalid required envelopes/limits. `convert_otlp(source: dict, *, trace_id=None, capture_content=False) -> list[dict]` returns filtered native events. `write_recording(events, path)` validates/bounds output before exclusive writing. Use core PrivacyPolicy; define no conflicting core files.

Viewer owner creates `viewer/` frontend and tests; `npm run build` emits bundled static assets into `src/agent_flight_recorder/static/`. Viewer duplicates consumer validation per contract, provides reduced export in browser. Root owns packaging, CLI/server, schema, synthetic demos/fixtures, integration tests, docs, and benchmarks. No one modifies other owners' files without coordination.
