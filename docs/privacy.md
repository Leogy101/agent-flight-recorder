# Privacy and threat model

Default capture stores structural metadata: IDs, timing, operation kind/status, approved static labels, and allowlisted attributes. It omits prompts, outputs, tool arguments, documents, arbitrary metadata, exception messages, and stack traces. A static label can still contain a secret; the caller must choose appropriate labels.

`capture_content=True` opts into content capture. Privacy filtering happens before serialization and persistence. `redact_keys` adds case-insensitive exact object keys to the credential-key denylist. `redact_patterns` contains **literal sensitive substrings**, not regular expressions. Keeping matching literal avoids catastrophic regex behavior. Overlapping matches are removed together against the original string, independent of rule order. If two object keys become identical after filtering, the entire payload is omitted with `redaction_collision`, rather than silently overwriting a value. Configured filters also apply to labels/allowlisted string metadata. Review the actual policy and examples in `privacy.py` before recording sensitive workloads.

Only exact supported built-in values are normalized. Custom representations, custom container iteration, arbitrary serializers, unpaired Unicode surrogates, nonfinite numbers, excessive integers, cycles, and excessive nesting are rejected or omitted. A filtering failure never falls back to raw content. Oversized payloads may be omitted as a whole with an explicit limit marker; the recorder does not need to retain a potentially sensitive prefix.

The recorder never automatically reads environment variables, request headers, files, stack locals, process memory, or hidden model reasoning. It only sees values supplied at the explicitly instrumented boundary. Its default error record identifies a category without collecting the error's message.

## Local storage

New recordings use exclusive creation and restrictive permissions where supported. They are plaintext, not encrypted. Keep them outside shared/synced folders when needed; the project cannot control backup, sync, browser extensions, filesystem access, or other software on the host. Deleting a file is not secure erasure of all copies.

Git ignores real `.jsonl` recordings, local recording directories, and environment files. Only reviewed synthetic fixtures and static demos are exceptions. Never put real recordings into a public issue or commit without reviewing the entire artifact.

## Sharing

The viewer's reduced export starts from a positive allowlist. It removes input/output content, annotations' content, arbitrary metadata, source paths, exception text, and original labels; consistently remaps IDs; and shifts absolute time while preserving intervals. A transformation manifest retains static source-warning codes and explains the reduction. The original recording remains unchanged.

Inspect the export preview before downloading. Remaining timing, structure, operation kinds, and outcomes can still reveal information. Redaction and metadata-only capture are risk-reduction measures, not a guarantee that an artifact is appropriate to publish.

## Untrusted recordings

Treat every imported string as untrusted data. The viewer uses escaped text, not HTML execution or automatic URL navigation. It does not fetch images or other URLs embedded in a trace. The parser bounds file size, event count, event size, nesting, and numeric values, and reports missing or contradictory evidence.

The asset server binds to loopback, checks the request host, refuses data/upload routes, and serves only packaged assets. User-selected file data stays in browser memory; there is no analytics or persistence to browser storage. Clearing the view releases application references, not a guarantee of memory erasure.

## What this does not prove

The recorder cannot defend against a compromised operating system or an agent that can edit its own records. IDs and JSONL do not establish authenticity, non-repudiation, tamper resistance, complete coverage, or compliance. A recording is evidence for debugging, not an audit certification.

Read-only capture avoids intentional changes to observed operation arguments/results or external systems. It still allocates memory and writes files, so it adds overhead and can influence timing. An interrupted or failed recorder may lose events. Playback never reruns an operation or undoes its effects.
