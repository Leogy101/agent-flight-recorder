# File interoperability in version 0.1

The converter reads one selected trace from an OTLP JSON file and writes a new
native recording. It is not an OTLP receiver, does not install instrumentation,
and never executes a recorded operation. Native recording does not depend on
OpenTelemetry or OpenInference packages.

## Supported input

Input is UTF-8 (an optional UTF-8 BOM is accepted). The supported envelope is the OTLP protobuf JSON trace representation:
`resourceSpans[].scopeSpans[].spans[]`. The converter accepts the camelCase field
names in that representation. It does not accept arbitrary vendor exports,
newline-delimited OTLP, `instrumentationLibrarySpans`, protobuf bytes, or base64
trace/span IDs. IDs must be nonzero case-insensitive hex: 32 characters for a trace and
16 for a span. Conversion normalizes IDs and the trace selector to lowercase without
changing the source object. Empty or all-zero parent IDs indicate no parent. This follows
the [OTLP JSON encoding rules](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding).

Each span supplies `traceId`, `spanId`, optional `parentSpanId`, `name`, `kind`,
`startTimeUnixNano`, `endTimeUnixNano`, `status`, and `attributes`. Resource and
instrumentation scope names/attributes are never copied. Source span names and
the small mapped structural attribute set pass through the shared privacy policy;
they may still reveal developer-approved labels and are not guaranteed anonymous.

When multiple traces occur, `--trace-id` is required. One recording never silently
combines traces. Source size is limited to 25 MiB and 10,000 source spans. Expansion
must fit the native 10,000-event limit: two lifecycle events per span plus two
capture markers. Consequently at most 4,999 source spans fit an unextended
conversion. Line, payload, JSON depth, safe-integer, and total output limits are
also checked before any output file is created. Output creation is exclusive with
owner-only file permissions where supported; an existing recording is never
overwritten.

Before the CLI constructs a JSON object graph, a bounded lexical pass caps depth at 20, members/elements at 100,000 per container, and lexical tokens at 500,000. Tokens include keys and punctuation; quoted contents are skipped without building a token list. This conservative work bound can reject a dense document before its byte limit.

After decoding, JSON traversal is lazy, with at most 100,000 items in an individual object/array
and 500,000 visited values per bounded document. These defensive work limits can
reject a dense file before its byte limit; they prevent small JSON tokens from
expanding into an unbounded validation work queue. Payload depth reserves three
container levels for the native event envelope.

## Tested mapping revision

The recording provenance names mapping `otlp-json-subset-0.1`. The initial mapping
was reviewed against these upstream source revisions, retrieved read-only during
implementation:

- [OpenTelemetry GenAI conventions, e6658f14](https://github.com/open-telemetry/semantic-conventions-genai/tree/e6658f14c9d9ea0760825f029cb82e7673f48fab/docs/gen-ai)
- [OpenInference specification, fb166749](https://github.com/Arize-ai/openinference/tree/fb1667497ecf94381476d74cb761dad7140491e9/spec)

These references document vocabulary; this project implements only the table
below, not full conformance to either specification. GenAI conventions remain
in development. Recheck upstream changes before extending the mapping.

| Native field | Source precedence, first present |
| --- | --- |
| Kind | Recognized `gen_ai.operation.name`; then recognized `openinference.span.kind`; otherwise `step` |
| Provider | `gen_ai.provider.name`, legacy `gen_ai.system`, `llm.provider` |
| Model | `gen_ai.response.model`, `gen_ai.request.model`, `llm.model_name` |
| Tool name | `gen_ai.tool.name`, `tool.name` |
| Tool call ID | `gen_ai.tool.call.id`, `tool_call.id` |
| Input token total | `gen_ai.usage.input_tokens`, `llm.token_count.prompt` |
| Output token total | `gen_ai.usage.output_tokens`, `llm.token_count.completion` |
| Input, only with opt-in | `gen_ai.input.messages`, `gen_ai.tool.call.arguments`, `input.value` |
| Output, only with opt-in | `gen_ai.output.messages`, `gen_ai.tool.call.result`, `output.value` |

Recognized operations: `chat`, `text_completion`, and `generate_content` map to
`model`; `execute_tool` to `tool`; `invoke_agent` to `agent`; `invoke_workflow` and
`invoke_runner` to `step`; `retrieval` and `retrieve` to `retrieval`. OpenInference
`LLM`, `AGENT`, `CHAIN`, `TOOL`, and `RETRIEVER` map to corresponding native kinds.
Unknown operations remain generic steps. OTel `CLIENT`/`INTERNAL`/etc. are preserved
separately as `otel_span_kind`, never confused with the AI operation kind.

OTLP AnyValue supports `stringValue`, `boolValue`, `intValue` (decimal string or
safe integer), `doubleValue`, `arrayValue.values`, and `kvlistValue.values` for
mapped attributes. Binary `bytesValue` is unsupported. Structured content is
normalized and filtered by the same policy as native capture. JSON encoded inside
an `input.value`/`output.value` string remains a string; the converter does not
guess its MIME type or parse nested encodings. Duplicate mapped attribute names
are rejected. Unknown attributes are discarded rather than decoded or copied.

OTel `UNSET`/missing status becomes `unknown`; `OK` becomes `ok`; `ERROR` becomes
`error`. Numeric status enums are standard OTLP JSON. Protobuf JSON enum names
are accepted as a convenience extension, not claimed as standard OTLP encoding.
An error records the fixed category `source_error`; status descriptions, exception
messages, stack traces, arbitrary source errors and source events are not copied.
Usage is optional and unknown when absent. Cached-input or reasoning-output
breakdowns are not added to totals. Provider tool-call ID remains separate from
the recorder's span ID; retries and causal links are never inferred from names.

## Timing and evidence limitations

Source times must be unsigned decimal-string Unix nanoseconds. Valid values retain
all nine fractional digits. Missing, zero, malformed, and out-of-range times remain
undated and produce evidence warnings; the conversion timestamp is not substituted.
Native `elapsed_us` is not fabricated for imports. `recorded_at` identifies when
conversion happened and is never the imported timeline axis.

Imported lifecycle records are ordered by source timestamp, starts before ends,
then span ID. Undated records follow dated records with the same start/end and ID
tie-breaker. This produces a stable display order, not historical observation
order or proof of causality. Timestamp ties and negative intervals remain warnings.
Parent cycles, absent parents, conflicting spans and closure inconsistencies remain
visible validation findings; conversion does not silently repair historical data.

Every imported start and end has `reconstructed: true`. Standard OTel processors
normally export finished spans; a missing, hung or crashed operation that never
exported cannot be recovered from the file. See the [OTel tracing SDK's processor
contract](https://opentelemetry.io/docs/specs/otel/trace/sdk/). An imported
`capture.ended` means file conversion completed. It does not certify original
capture coverage or historical agent success.

The converter ignores span events, links, dropped-attribute counts, arbitrary
resource metadata, multimodal binaries, OpenInference flattened message-array
attributes, token subcounts, and provider-specific continuity state. This release
therefore cannot reconstruct every message, retry, handoff or tool call from an
arbitrary OTel trace. Exporter loss before this file is unknown. A source exporter
may already have persisted sensitive content; importing with privacy defaults
does not erase that original file.

## Reader behavior

Readers reject unsupported schema versions, non-finite or unsafe integers,
duplicate JSON keys, invalid envelopes, oversized data, and excessive depth.
Semantic evidence problems produce static warning codes without including source
payloads in errors. A genuinely incomplete final JSON line without a terminating
newline can be skipped with a warning; malformed middle lines require explicit
`--allow-partial`. Schema and limit violations are never bypassed by partial mode.
Identical repeated event IDs remain in the raw evidence and are flagged; derived
views may deduplicate them. Conflicting duplicates remain ambiguous. A missing end
is incomplete evidence, not proof of agent failure.
