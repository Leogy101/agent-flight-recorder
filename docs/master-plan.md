# Agent Flight Recorder Master Build Plan

Approved by the user · November 12, 2026

This document preserves the approved design baseline. Implementation results and measured limitations are tracked separately in `validation.md`.

Build a small, standalone tool that helps a developer inspect a failed AI agent run from one portable recording. The first release should make the sequence of model calls, tool calls, retries, errors, and missing evidence understandable without requiring the original framework or provider credentials.

The recommended niche is **offline incident inspection with explicit recording quality**: what happened at instrumented boundaries, what evidence is available, and what cannot be concluded. This is a focused portfolio project, not a claim that agent tracing or flight recorders are new.

This plan covers research, MVP scope, architecture, the proposed event contract, privacy, playback, milestones, and release criteria. Implementation starts only after approval. The project will have its own repository, packages, examples, and documentation. GlauxOS is outside its scope and has not been inspected or modified.

## 1 Product purpose and positioning

The primary user is an individual developer debugging an agent locally or reviewing a recording attached to a bug report. The core question is: “Which observed operation failed or remained unfinished, what preceded it, and which details are missing?”

The main workflow is:

**Instrument selected boundaries → run the agent → open one recording → inspect the timeline and capture health → export a reduced recording for review.**

A successful portfolio demonstration lets a reviewer understand a realistic failure in under five minutes, using synthetic examples with no API key. A developer should be able to complete the installation and first recording in roughly ten minutes following the quickstart. These are usability targets to test, not measured results.

The engineering value comes from a clear event contract, honest failure handling, careful treatment of untrusted recordings, and reproducible tests. It does not depend on claiming automatic root-cause discovery.

## 2 Existing tools and the useful gap

The comparison separates standards and instrumentation from full observability products. Descriptions reflect the official sources reviewed for this proposal; software and license terms should be rechecked at implementation.

| Tool | Existing strengths and deployment | Implication for this project |
| --- | --- | --- |
| OpenTelemetry and its GenAI conventions | OpenTelemetry supplies a general trace model and transport ecosystem. GenAI conventions describe model, tool, retrieval, and agent operations, but the current GenAI specification is marked Development. [Trace concepts](https://opentelemetry.io/docs/concepts/signals/traces/), [GenAI specification](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/README.md) | Reuse trace/span concepts and explicit mappings. Avoid inventing a competing universal standard or promising compatibility with every convention revision. |
| OpenInference | Apache-2.0 conventions and instrumentation built on OpenTelemetry, with AI-specific span kinds and input/output attributes. It is an instrumentation layer rather than a complete debugging application. [Project and license](https://github.com/Arize-ai/openinference), [schema](https://arize-ai.github.io/openinference/spec/) | Support a documented import subset and reuse the vocabulary. Keep the recorder independent of any one framework. |
| Langfuse | Broad tracing, evaluation, prompt tooling, and debugging views. The repository is MIT except enterprise directories. Self-hosting includes web and worker services plus PostgreSQL, ClickHouse, Redis/Valkey, and object storage. [Repository](https://github.com/langfuse/langfuse), [architecture](https://langfuse.com/self-hosting), [product documentation](https://langfuse.com/docs) | Compete on the small incident workflow and operational simplicity, not feature breadth. Langfuse can run locally and does not require its cloud service. |
| Phoenix | Framework/provider-independent tracing using OpenTelemetry/OpenInference, evaluations, datasets, and prompt experimentation. It supports a simple local Python startup. The current repository uses Elastic License 2.0; classify it as source-available rather than permissively licensed open source. [Repository](https://github.com/Arize-ai/phoenix), [local quickstart](https://arize.com/docs/phoenix/get-started), [license](https://github.com/Arize-ai/phoenix/blob/main/LICENSE) | Local operation and a timeline alone are insufficient differentiation. A smaller portable incident artifact is a product focus, not an exclusive capability claim. |
| LangSmith | Framework-independent tracing, nested runs, debugging, evaluations, and privacy controls. Its self-hosted platform is an Enterprise add-on. Include it as a commercial comparator, not an open-source observability backend. [Trace concepts](https://docs.langchain.com/langsmith/observability-concepts), [self-hosting](https://docs.langchain.com/langsmith/self-hosted) | Avoid recreating a commercial observability suite. Keep the core workflow usable without an account or deployed backend. |

Privacy filtering is already present in these products: [Langfuse masking](https://langfuse.com/docs/observability/features/masking), [Phoenix masking](https://arize.com/docs/phoenix/tracing/how-to-tracing/advanced/masking-span-attributes), and [LangSmith filtering](https://docs.langchain.com/langsmith/mask-inputs-outputs). Our proposed distinction is the combination of a deliberately small workflow, conservative defaults, and visible evidence limitations.

Direct flight-recorder competitors also exist. An existing repository uses the exact name [agent-flight-recorder](https://github.com/flaviorg/agent-flight-recorder); [Reflight](https://github.com/pauti04/reflight) and [Kinescope](https://github.com/satchmakua/kinescope) describe recording, local inspection, replay, and branching features. These are repository descriptions, not independently benchmarked capabilities. Retain Agent Flight Recorder as the working title and check repository/package naming before publishing. Do not copy their implementations or claim the category is unoccupied.

**Positioning hypothesis:** developers will value a compact, inspectable incident file whose viewer distinguishes observed facts from omitted, incomplete, and transformed evidence. Validate that hypothesis with a clean-install demo and two developer walkthroughs before adding broader integrations. If the workflow provides no useful advantage over an existing tool, tighten the scope instead of expanding into feature parity.

## 3 MVP boundaries

The first release supports one recorded run at a time, with one Python process writing the native recording. Threads and asynchronous tasks are supported within that process; their context behavior must be tested.

| Included in version 0.1 | Acceptance boundary |
| --- | --- |
| Small Python recording SDK | Explicit run/span context managers and structured event emission. No required agent framework or model-provider dependency. |
| Model, tool, agent, retrieval, and generic step spans | Manual instrumentation records operation boundaries. No promise of automatic coverage. |
| Portable JSONL recording | One versioned file, with one JSON object per line; authoritative evidence is independent of the viewer. |
| Offline browser viewer | Import a local file; show nested timeline, details, filters, errors, incomplete spans, and capture health. |
| Recorded playback | Step forward/backward through stored events, with no agent or tool execution. |
| Privacy controls | Structural metadata by default; selected content opt-in; filtering before persistence; explicit omission/redaction indicators. |
| Reduced share export | A new file rebuilt from a strict field allowlist, with a preview and transformation details. |
| Narrow standards import | Convert one documented OTLP JSON trace representation into the native format; understand selected OTel GenAI/OpenInference attributes. |
| Reproducible portfolio demo | Synthetic successful, failed, concurrent, and interrupted runs; tests and a short diagnostic walkthrough. |

“Framework-agnostic” means the format and manual recording API do not depend on an agent framework. It does not mean every framework is automatically instrumented. Python is the first supported SDK language. A tiny independent TypeScript fixture producer will demonstrate the format’s language neutrality without committing to a second full SDK.

Exclude from this release: live streaming, production collection services, multi-user accounts, authentication infrastructure, multi-run search, hosted storage, dashboards, evaluations, prompt management, AI diagnosis, guardrails, orchestration, automatic instrumentation, a desktop shell, binary attachments, token-by-token streaming, distributed execution capture, and deterministic re-execution. Costs and pricing catalogs are also deferred; show recorded token usage without inventing missing values.

## 4 Simplicity first architecture

Use a Python package for capture and command-line operations, with a prebuilt React/TypeScript viewer bundled as static assets. Development requires frontend build tools; end users should not need Node to view a recording. Pin supported dependency versions during the first implementation milestone.

The native path is:

**Agent code → explicit recording calls → bounded normalization and privacy filtering → locked JSONL append → browser file selection → in-memory timeline.**

The standards path is:

**User-selected OTLP JSON file → validation and filtering → documented mapping → new native recording → same viewer.**

Use no database, HTTP ingestion endpoint, external collector, message broker, or cloud service. JSONL is the source of truth; the browser builds temporary indexes in memory. Add SQLite only if a later, validated multi-run search requirement justifies it.

Proposed package responsibilities:

| Component | Responsibility |
| --- | --- |
| Recorder core | IDs, timing, context, lifecycle events, limits, privacy policy, append-only sink, health status. |
| Command-line interface | Open the viewer, validate recordings, convert supported OTLP files, and generate demo recordings. Exact command names follow package-name checks. |
| Viewer | Parse selected files, build a bounded view model, display evidence, navigate playback, and download reduced exports. |
| Shared contract and fixtures | Versioned schema, semantic rules, valid/invalid examples, and Python/TypeScript conformance cases. |
| Optional import module | OTel/OpenInference field mappings and source provenance; no native-capture dependency on OTel packages. |

The local viewer server binds only to loopback and serves an allowlist of bundled assets. It exposes no recording directory, file-path reader, shell endpoint, proxy, or upload API. The browser reads recordings only after file selection or drag-and-drop using the [File API](https://developer.mozilla.org/en-US/docs/Web/API/File_API). No recording content is sent to the static server.

Keep imported data in browser memory, without automatic local storage, analytics, remote fonts, or remote resources. Clearing the view releases application references; it is not a guarantee of forensic memory erasure.

## 5 Read only capture contract

“Read-only” refers to observing agent behavior. The recorder writes its own files, but does not intentionally change prompts, tool arguments, returned values, decisions, retries, permissions, or external systems.

Use explicit context managers instead of global monkey-patching or a network interception proxy. Attempt to append and flush a start event before entering the observed operation; a healthy recorder completes that write, while a recording failure still permits the operation. Attempt to emit its end afterward. The application remains responsible for calling tools and models. Streaming callers must explicitly scope the span around consumption; the recorder does not secretly consume generators or buffers.

For the MVP, synchronous append under one recorder lock is the simplest persistence mechanism. This adds time and I/O to the instrumented path, including an asynchronous caller. It is suitable for bounded local debugging, not a promise of nonblocking production instrumentation. Measure its overhead and revisit a bounded background writer only if evidence warrants the added failure modes.

Recorder failures must not replace the application’s return value, original exception, or cancellation. Normalize only exact supported built-in primitive/container types, within limits; reject custom subclasses and never call arbitrary object serialization, representations, or iteration to collect data. Detect cyclic containers and bound integer magnitude as well as strings and nesting. An unsupported value is marked unavailable. Serialization, filtering, and disk errors produce a health warning and disable or degrade recording without retrying the observed operation. Configuration errors can be reported explicitly before the run starts.

Expose recorder health in memory and issue one sanitized out-of-band warning when writes fail. A failed disk cannot reliably write its own failure event. The final summary includes known skipped/failed records when it can be written. Missing finalization means capture quality is unknown.

Create a new file exclusively and never overwrite an existing capture. Support a single writer per file; reject an attempt to reuse it across processes. Flush complete lines, without claiming durable storage after power loss or operating-system failure. Do not claim crash-proof capture, invisible instrumentation, or a complete record of uninstrumented activity.

## 6 Proposed event schema

Use a small recorder-specific lifecycle envelope around familiar trace concepts. A trace groups a run; a span identifies an operation inside it. Reuse OpenTelemetry-compatible trace and span identifiers. Keep the schema separate from evolving provider attributes.

| Envelope field | Proposed rule |
| --- | --- |
| `schema_version` | Required version string, initially `0.1`. Unsupported major versions are rejected. |
| `recording_id` | Required random UUID identifying this artifact. Derived exports receive a new value. |
| `trace_id` | Required 32-character lowercase hexadecimal ID; one trace per native file. |
| `event_id` | Required UUID identifying a record; distinct from a span identifier. |
| `seq` | Required increasing safe integer assigned under the writer lock for each attempted event. Gaps may indicate recording loss. |
| `type` | Required lifecycle/event type from the table below. |
| `recorded_at` | Required UTC timestamp when the recorder observed or converted the event. |
| `source_time` | Optional original timestamp, especially for imported spans. Preserve source precision as text. |
| `elapsed_us` | Monotonic microseconds relative to native recorder start, required for native events. Absent for imported events that have no such clock. |
| `span_id` | Required for span lifecycle events; 16-character lowercase hexadecimal ID. |
| `parent_span_id` | Optional on a span start; describes supplied nesting, not inferred causality. |
| `data` | Typed object specific to the event; bounded fields, not an unrestricted raw dump. |

| Event type | Meaning and principal data |
| --- | --- |
| `capture.started` | Recorder/version, capture mode, source/adapter version, privacy policy, limits, and coverage description. |
| `span.started` | Operation kind and static label, optional allowlisted attributes, optional input descriptor, explicit links. Native root has kind `run`. |
| `span.ended` | Status, output descriptor, optional structured error category, usage, and source duration. |
| `event.recorded` | A bounded annotation or diagnostic associated with a span, with privacy-filtered content. |
| `capture.ended` | Orderly recorder closure, event counts and known failures/skips, policy/limit flags. This is separate from whether the agent succeeded. |

Operation kinds are `run`, `agent`, `model`, `tool`, `retrieval`, and `step`. Preserve the source’s OTel span kind separately when imported; an OTel `CLIENT` span is not the same concept as a domain `model` span.

Operation status is `ok`, `error`, `cancelled`, or `unknown`. The viewer derives `incomplete` when a start has no end. An imported OTel status of `UNSET` remains unknown, rather than being converted to success. Multiple conflicting ends are a validation problem, not an invitation to choose the most favorable status.

Useful optional attributes include provider/model identifiers, static tool name, input/output token totals, coarse error code, and explicit retry attempt linkage. Store provider-supplied `tool_call_id` separately from internal `span_id`. Each actual retry is its own span; do not infer retries merely from repeated labels. Parent relationships show nesting; optional explicit links represent supplied cross-span relationships. [OTel tool semantics](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/execute-tool.md)

Represent each input/output as a descriptor with `state` equal to `captured`, `omitted`, `redacted`, or `unavailable`. A captured value can have `truncated: true` and redacted-field counts. Include coarse reason codes, not secret-bearing field values. An intentionally captured empty value or null differs from missing data. Never calculate an unsalted digest of omitted sensitive content as a replacement.

Timing and evidence rules:

- Sequence means recorder observation order. It does not establish a universal execution order, especially for imported spans.
- Native durations use the monotonic clock. Imported durations use supplied start/end times and remain subject to clock skew.
- Native timeline positions use `elapsed_us`, while native playback follows `seq`. Imported timeline positions use `source_time`, never the conversion-time `recorded_at`. Imported playback sorts by source time with a documented stable tie-breaker (starts before ends, then span ID); tied timestamps and clock anomalies remain visible. This is a display order, not proof of causality. Invalid or missing source times go into an undated/problem list rather than fabricated positions.
- Imported `seq` records the generated display order, not original observation order. A written `capture.ended` does not complete an unfinished operation; an ended root without capture closure still leaves recording finalization unknown.
- Display concurrent spans as overlapping. Do not manufacture a sequential causal narrative.
- Missing parents, orphan ends, conflicting IDs, negative source durations, sequence gaps, and missing closure are visible validation findings.
- A partial trailing line can be ignored with a prominent warning. Malformed middle records require explicit partial-view acknowledgement and a list of affected line numbers.
- Identical repeated event IDs may be deduplicated with a count; conflicting duplicates must be flagged. Unknown major versions fail clearly. Supported minor-version extensions remain inert and bounded.
- Record coverage as `native_lifecycle` or `imported_completed_spans`; a reduced export also records its transformation. “No detected gaps” never means every action was captured.

Initial proposed limits: 25 MiB per imported/native file, 10,000 records, 64 KiB per record, JSON container nesting depth 20, and 8 KiB per opted-in input/output value. Span-tree depth is separate: traverse parent relationships iteratively and report cycles rather than recursively trusting the graph. Reserve space in native limits for a final capture summary. At a limit, preserve small lifecycle metadata where possible, omit content with an explicit reason, then disable capture with a warning if necessary. Oversized imports fail clearly rather than silently hiding the tail. These values are configuration and test targets, to be adjusted from measurements before release.

## 7 Standards interoperability

Implement one bounded adapter for an explicitly documented OTLP JSON trace export shape. It is a file converter, not an OTLP receiver. If a file contains multiple traces, require selection of one; do not silently merge them. Preserve source trace/span IDs, intervals, status, and mapped attributes. Document unsupported fields and conversion losses. Preflight the filtered output against native size/count limits, including two lifecycle events per imported span and capture markers. Refuse conversion with an explanation if expansion exceeds those limits; do not silently truncate the converted trace.

Pin the tested OTel GenAI and OpenInference mapping revisions. Example mappings include model/provider, tool name/call ID, operation kind, and usage. Unknown raw attributes are not copied automatically. Imported content remains omitted by default. OpenInference provides granular hiding settings, but its documented hide defaults are false, so the recorder must apply its own policy. [OpenInference configuration](https://arize-ai.github.io/openinference/spec/configuration.html)

Standard OpenTelemetry processors normally export completed spans. An imported completed span can generate a pair of viewer lifecycle records, but both must be marked as reconstructed from the exported span. They are not evidence that its start was recorded before a crash. A completed-span-only file cannot reveal operations that never exported. [OpenTelemetry SDK](https://opentelemetry.io/docs/specs/otel/trace/sdk/)

Reuse input/output token totals conservatively. Cached-input and reasoning-output counts may be subsets of those totals; do not add every field together. Missing usage is unknown. Count usage on leaf model operations to avoid summing parent aggregates twice. [Inference semantics](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/client-inference.md)

Native capture and import converge on the same viewer model, while retaining their different evidence quality. Full OTLP compatibility, remote export, and multiple automatic framework adapters are later work.

## 8 Privacy and security approach

Protect against accidental sensitive logging, unsafe sharing, malicious trace content, excessive resource consumption, and unintended access through the local viewer. The MVP does not protect against a compromised operating system, a malicious agent that controls its own recorder, or an attacker who can edit the file. It is a debugging record, not an audit-grade attestation.

Default capture stores structural metadata: IDs, timing, status, kinds, usage, and developer-declared static labels. Prompts, completions, tool arguments/results, retrieved documents, exception messages, stack traces, URLs, paths, and arbitrary attributes require separate opt-in or remain omitted. Even labels and model names may be sensitive; do not derive them from user content.

Apply an allowlist before serialization. Support selective payload capture with recursive redaction rules and bounded sizes. If filtering fails, omit that payload; never fall back to the raw value. Do not automatically capture credentials, environment variables, headers, local variables, files, or hidden model reasoning. OTel also recommends opt-in capture for sensitive model content. [OTel content guidance](https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/main/docs/gen-ai/gen-ai-spans.md)

Create owner-only recording directories/files where the operating system supports that permission model. Keep real recordings out of Git by default. Do not make additional raw debug logs. Original traces are plaintext; filesystem permissions are not encryption. Deleting a recording does not erase external copies or backups. These boundaries align with the need to protect and minimize application logs. [OWASP logging guidance](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

The default share export rebuilds a new file from approved structural fields. It removes payloads, arbitrary attributes, free-text annotations, exception text, and source paths; replaces labels with neutral labels; remaps correlation IDs consistently; and shifts absolute time while retaining relative timing. Its manifest identifies the transformation and retained fields. Preserve existing warnings and add omissions caused by export. Reviewers still decide whether remaining structural information is appropriate to share; no automatic redactor guarantees safe publication.

Render every imported string as escaped text. Do not evaluate code, render raw HTML, fetch embedded media, or automatically activate links from a trace. Enforce parser limits and avoid unsafe object-key merging. Use a restrictive content security policy and an asset-only local server with allowed host checks and no permissive cross-origin data access. Verify that malicious recordings trigger no outbound requests. [OWASP DOM XSS guidance](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)

Keep default recordings, selected content capture, and reduced exports visibly distinct in the viewer. Distinguish capture health, payload availability, and agent outcome instead of collapsing them into one green “complete” badge.

## 9 Timeline UI and playback

The first screen offers a local recording picker and bundled synthetic examples. After import, use one focused workspace:

| Area | What it shows |
| --- | --- |
| Summary strip | Agent outcome, recorded duration, known usage, native/imported coverage, privacy mode, and recording warnings. |
| Left operation tree | Nested operations with kind/status labels and explicit retry attempts. |
| Main timeline | Duration bars, concurrent overlap, time ruler, incomplete spans, and selected event position. |
| Details panel | Available metadata, input/output states, filtered content, error category, parent/links, source provenance, and raw normalized event. |
| Navigation | Search available labels/content, filter by kind/status, jump to error/incomplete span, previous/next event, and reset. |

Keyboard navigation and textual status labels are part of the MVP; color alone must not convey errors or missing evidence. Playback reveals the stored event sequence up to the selected point. It never accesses model credentials or invokes an operation. Imported playback must disclose that the sequence was reconstructed from completed spans.

The demonstration should include an invalid tool argument followed by a repeated attempt and a final failure. The viewer should expose that sequence without declaring it the definitive root cause. A second example should show parallel tool calls where one recording ends mid-operation. Default metadata-only views explain that inspecting arguments requires an explicitly captured, filtered example.

## 10 Honest replay limitations

| Term | Meaning | Version 0.1 |
| --- | --- | --- |
| Playback | Navigate and inspect events already stored in a recording. | Included. No execution or external side effects. |
| Fixture-based re-execution | Run code against recorded or synthetic responses at controlled boundaries. | Deferred. Requires a separate execution harness and matching rules. |
| Live rerun | Invoke models/tools again using current code and external state. | Deferred. Results, costs, and side effects may differ. |
| Deterministic whole-agent replay | Reproduce the original execution, including every relevant nondeterministic input and state transition. | Not promised. |

A trace does not reconstruct unrecorded process state, hidden reasoning, unavailable/redacted inputs, lost events, historical files/databases, external side effects, scheduling, randomness, or provider behavior. A replayable timeline is not a reversible transaction log. It cannot undo an email, payment, file change, or any other action.

Existing tools also use replay for different activities. For example, Phoenix’s span replay can load a recorded model call into a playground for a fresh invocation. That is distinct from reproducing an entire historical execution. [Phoenix span replay](https://arize.com/docs/phoenix/prompt-engineering/overview-prompts/span-replay)

Use “recorded playback” consistently in the interface and README. Any future execution mode needs a separate design covering stubs, isolation, side effects, credentials, and explicit user intent.

## 11 Milestone based build plan

Milestones are sequential acceptance gates. Each ends with a reviewable result and evidence that it meets the criteria. Scope problems should be surfaced before adding features. Planning is complete when this proposal is delivered; all implementation milestones remain pending approval.

| Milestone | Deliverable | Completion criteria |
| --- | --- | --- |
| M0 Research and approval | This proposal and the initial scope decision. | User approves or revises the MVP and architecture before code is written. |
| M1 Contract and standalone foundation | New independent repository, proposed MIT license, package-name check, architecture decisions, threat model, schema, and synthetic fixtures. | Schema represents success, failure, cancellation, concurrency, retries, missing end, redaction, and invalid data. Event order and capture-quality rules are unambiguous. No GlauxOS dependency or copied component. |
| M2 Native recording | Python run/span API, context isolation, filtering, bounded JSONL writer, and health reporting. | Instrumented examples preserve results and original exceptions. Disk/serialization failures do not replace application failures. Concurrent tasks have correct parents; emitted starts survive a controlled process kill when already flushed. Incomplete capture remains visibly incomplete. |
| M3 Offline viewer | Packaged static UI, local import, operation tree, timeline, inspector, filtering, and playback. | A reviewer can locate failed and unfinished operations in fixtures. Overlap is visible. Playback performs no tool execution. Malformed/oversized files are handled clearly. Keyboard access works. |
| M4 Portability and privacy | Bounded OTLP JSON import, reduced share export, independent TypeScript fixture producer, and conformance checks. | Both producers render correctly. Imported spans retain provenance and completion limitations. Default-omitted fields contain no seeded fake secrets; configured filtering and label replacement in share exports pass their fixtures. Export leaves the original unchanged. |
| M5 Reliability and portfolio release | Integrated tests, benchmarks, clean-install package, README, architecture/schema docs, screenshots, and short demo walkthrough. | Offline demo works without credentials. Security/behavior tests pass. Performance and limits are published with environment details. Documentation makes no deterministic-replay or universal-coverage claim. Release contents include only approved synthetic recordings. |

Within M1, settle compatibility policy and package naming before public branding. Within M2, choose the smallest API that can record a nested run with an explicit model call and two tools. Within M3, complete the diagnostic workflow before cosmetic polish. Within M4, support one tested OTLP JSON shape rather than expanding to arbitrary exporter dumps. M5 ships the small product; it is not a catch-all for deferred integrations.

The full MVP requires M1 through M5. Live collection, databases, automatic providers, and execution replay must not silently enter those milestones. If usability or reliability work exceeds the initial expectation, adjust the schedule rather than weakening capture and privacy criteria. Estimates should follow M1’s fixture and packaging work; this plan makes no untested delivery-date commitment.

## 12 Validation and release evidence

Use tests that establish behavior and failure boundaries, not just functions that mirror the implementation.

| Area | Required evidence |
| --- | --- |
| Recorder behavior | Same results, exception identity, and cancellation propagation with and without recording; nested context isolation; a failed start write neither suppresses nor duplicates the operation. Hostile representations, custom container iteration, recursive containers, and oversized integers do not invoke user code or escape bounds. |
| Persistence | Read-only/unwritable destination, failed write, file limit, partial final line, interrupted process, missing closure, duplicate/conflicting records, and no overwrite. Test capture closure with unfinished spans and an ended root without capture closure separately. |
| Privacy | Seed fake secrets in default-omitted prompts, arguments, nested attributes, exception strings, paths, and annotations; verify their absence across native and imported captures. Test configured label filtering separately, and verify that reduced exports replace all user labels. Developer-approved static labels are not automatically guaranteed secret-free. |
| Viewer safety | HTML/script strings, dangerous URLs, hostile object keys, deep JSON, huge strings, and oversized files do not execute or fetch remote content. |
| Timing and semantics | Parallel spans stay parallel; retries require explicit linkage; unfinished spans are not labeled failed; unknown usage/status remain unknown; imported starts are marked reconstructed. |
| Portability | Python fixtures, independent TypeScript fixtures, and the selected OTLP JSON subset converge on expected views with documented differences. Conversion rejects output expansion beyond native limits, and imported ordering never uses conversion time. |
| Packaging | Clean install and offline demo on the declared support matrix, initially macOS and Linux; Windows support is added only after it is tested. |

Initial performance targets on a documented reference machine: open a 10,000-record file within two seconds, maintain responsive selection/filtering, and keep median append overhead below one millisecond for a roughly 1 KiB metadata event on a local SSD. Publish p50/p95 overhead, recording size, viewer memory, hardware, operating system, and workload. Targets are provisional; measurements may require tighter advertised limits or an architecture revision. No claim of zero overhead or bounded disk latency is acceptable.

Portfolio materials should include the problem statement, a 60–90 second demonstration, a quickstart, the architecture and schema, the privacy/threat model, the difference between playback and re-execution, test results, measured limitations, and a short case study explaining a failure from evidence. An optional future live-provider demo must be clearly distinguished from the synthetic examples and is not required to demonstrate the product.

## 13 Later work and approval decision

After the first release and user feedback, consider a background writer with explicit loss accounting, live file following, a full TypeScript SDK, additional standards adapters, multi-run comparison, and local indexing. Add only the feature that addresses the strongest observed need. Controlled re-execution deserves its own proposal and should not be treated as a small timeline enhancement.

Approve the following baseline to begin implementation:

1. A standalone local incident recorder/viewer with Python capture and a language-neutral format.
2. One JSONL file as the source of truth, a static browser timeline, and no database or cloud dependency.
3. Explicit read-only instrumentation, structural metadata by default, and filtered opt-in content.
4. Recorded playback only, with visible incomplete evidence and no execution replay.
5. A narrow OTLP file adapter, reduced share exports, and milestones M1 through M5 as defined above.

Approval authorizes starting the standalone implementation. No implementation code, repository, or deployment has been created as part of this planning phase.
