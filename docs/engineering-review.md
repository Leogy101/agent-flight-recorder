# Phase 2 engineering review

Reviewed November 12, 2026 against the existing MVP, beginning at local commit `89d7f4b`. The review covered all Python modules, the format/schema, frontend model and UI, CLI/server, examples, fixtures, tests, build configuration, dependencies, and documentation. Core and viewer code were reviewed by reviewers other than their original implementers, with an additional cross-component review. This is an engineering review with reproducible tests, not an independent security certification.

## Classification

**Critical:** No confirmed critical issue was found in the reviewed scope. That is not proof that none exists.

**Important:** The following confirmed problems were fixed rather than redesigning the architecture.

| Area | Reproduction or impact | Fix and regression evidence |
| --- | --- | --- |
| Overlapping literal redaction | Rules `abc` and `bcd` on `abcd` left a matched character visible because replacements changed later matches. | Match original text, merge overlapping coverage, bound output. Tests cover rule order, self-overlap, and replacement-marker interactions. |
| Redacted key collisions | Two keys could become `[REDACTED]`, silently replacing one value with the other. | Omit the entire ambiguous payload with `redaction_collision`; no raw fallback. |
| Runtime ID failure | An injected UUID/entropy error escaped span construction, preventing the observed operation from executing. | Return an inert scope, disable capture, preserve original application results/exceptions, and report health degradation. |
| Hidden known capture loss | A second root or reused span executed again but left a file claiming zero skipped events. | Keep the one-root/single-use model; count discarded boundaries and preserve sequence gaps and loss notices in the artifact. |
| Link count mismatch | Writer retained only 32 relationships although the format supports 64. | Preserve all 64 supported links; test against actual prior recorded operations. |
| Unicode interoperability | Surrogateescaped input could be written with clean health but rejected by the reader. | Omit unsupported payload strings/keys and invalid labels before persistence. Accept ordinary emoji; reject invalid Unicode in browser imports. Native-to-reader tests cover real surrogateescape strings. |
| Duplicate evidence equality | Python treated `true` and `1` as equal; the viewer treated reordered object keys as different. | Type-aware JSON comparison on Python and canonical key-order comparison in TypeScript. Booleans remain distinct; integral numeric forms agree. |
| Numeric/label parity | Python rejected `1.0`/`1e0` in integer fields accepted by JSON Schema/JS; JS counted emoji as two label characters. | Accept mathematically integral safe JSON numbers; count Unicode code points for labels. Reject non-ASCII timestamp digits. |
| OTLP identifiers | Uppercase hex IDs from valid OTLP JSON were rejected. | Normalize IDs and explicit trace selectors without mutating source input. Unknown statuses remain unknown; source precision remains intact. |
| Import allocation | The OTLP CLI decoded dense JSON before checking node/container bounds. | A bounded lexical pass rejects excessive structure before object allocation. Tests patch the decoder and prove it is not invoked for excessive input. |
| Formal schema drift | Empty source metadata, parent IDs on ends, and unknown usage fields passed schema validation but failed consumers. | Align schema requirements with implemented semantics; add paired schema/reader regressions and executed-fixture conformance checks. |
| Playback evidence timing | Whole-file conflicts affected earlier cursor positions; ambiguous model spans contributed apparently certain usage totals. | Derive visible conflicts from the revealed evidence, retain unresolved source issues at full view, and suppress ambiguous model totals. |
| Stale imports | A slow earlier read could replace a newer file or reopen after Close/Home. | Invalidate obsolete asynchronous read results with a request generation counter; test controlled out-of-order completions. |
| Blank physical records | Browser silently skipped interior blank lines that Python treated as invalid evidence. | Require explicit partial-view acknowledgement and use the same physical line counting. |
| Inspection and navigation | Capture markers/orphan ends lacked direct inspection; repeated failed tool calls had identical accessible names. | Add current-event inspection, exact start/end navigation, keyboard tabs, and attempt/retry information in accessible row names. |
| Unbounded annotation rendering | A valid file with many annotations could generate thousands of DOM nodes. | Render annotations only when expanded and paginate them; cache search text without exposing future payloads during playback. |
| Packaged source freshness | CI could pass against new frontend source while a wheel shipped old checked-in assets. | Compare rebuilt assets with the checkout and reject untracked generated assets; install/smoke-test the wheel in a fresh environment. Include example JSON data in the source distribution. |
| Developer dependency advisory | The local pip 26.1.2 installer was affected by an upstream advisory. | Upgrade only the project environment to 26.3, add >=26.2 upgrade instructions/CI, and rerun the audit. No Python runtime dependency was added. See [dependency details](dependencies.md). |
| Demonstration fidelity | The original small example assigned decisions/results and reported invented model token totals. | Execute a read-only local support workflow through the real recorder; identify the provider simulation, preserve actual errors/order/timing, and leave token usage unknown. |

Regression coverage lives in `tests/test_privacy.py`, `test_recorder.py`, `test_recording.py`, `test_cli.py`, `test_otlp.py`, `test_contract.py`, `test_example.py`, and the viewer tests. `tests/browser-check.mjs` exercises the compiled package in a real browser, including executed scenarios, privacy, hostile text, uncertain evidence, keyboard navigation, narrow layout, and the 10,000-event workload. See [actual validation results](validation.md).

## Architecture and security assessment

The current separation is appropriate for the scope: explicit Python capture → bounded JSONL → in-memory browser inspection, with a file-only OTLP adapter. No database, queue, service account, large frontend framework, or runtime SDK integration was needed. Python capture still has no third-party dependencies. The recorder observes caller-invoked code; the viewer has no execution capability.

The static server's loopback binding, Host check, path allowlist, no upload API, and response policy were reviewed and exercised. Tests cover path traversal, disallowed hosts, sensitive error output, and inert imported markup. Browser acceptance records page errors, remote requests, and data uploads; these checks cannot exclude malicious extensions, a compromised host, or an independently modified build.

Privacy minimizes collection rather than promising secrecy. Explicit labels remain visible; filtered plaintext files are not encrypted or tamper-evident. Missing endpoints and recorder health are separate from application outcomes. The OTLP adapter remains a declared subset rather than a collector or full exporter implementation. In particular, source drop counts and omitted events/links are not reconstructed.

Performance remains bounded by declared file/event/payload limits, pagination, and synchronous capture. A measured ASCII-validation regression was reduced with a standard `str.isascii()` fast path while preserving Unicode checks. No background worker or cache service was introduced. Memory/latency guarantees for hostile processes, slow disks, or maximum-content workloads are outside the measured benchmark.

## Optional findings and deferred work

- Conduct a first-time-user and screen-reader session; automated keyboard tests are not an accessibility certification.
- Expand browser/platform coverage only when intended support expands. Chromium and local macOS/Linux checks are not proof of Firefox, Safari, Windows, or production suitability.
- Add a shared malformed-input corpus if producer diversity grows. Cross-language conformance remains a maintenance obligation, especially because JSON Schema cannot express all file-level evidence rules and work limits.
- Consolidate version literals when cutting the next version; they currently agree. Some frontend source remains compact and can be formatted in a future focused cleanup.
- Keep the declared one-process writer and fresh-scope restriction. Concurrent reuse of one Span instance, distributed traces, deterministic execution replay, fsync durability, and automatic coverage discovery require separate designs, not incidental extensions.

No confirmed critical or important finding from this review remains knowingly unfixed. The deliberate limitations above are documented product boundaries, not completed features.
