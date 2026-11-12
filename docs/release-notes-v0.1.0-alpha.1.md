# Agent Flight Recorder v0.1.0-alpha.1

The first alpha of a standalone, framework-agnostic tool for recording and inspecting AI agent execution locally. Its focus is a portable incident file: which operations ran, how they relate, where they failed or retried, and which evidence is missing.

## Included

- An explicit Python recording API with no Python runtime dependencies. Wrap agent, model, tool, retrieval, and step boundaries without a provider SDK or framework adapter.
- Bounded JSONL recordings with parent spans, error categories, retry links, timing, optional usage, and warnings for incomplete or contradictory evidence.
- A bundled local viewer with timeline inspection, filters, selected-event details, recorded playback, and a previewable reduced sharing export.
- Metadata-only capture by default, opt-in filtered payloads, literal/key redaction rules, exclusive output creation, and a loopback-only asset server.
- A narrow OTLP JSON file importer for one selected trace, including selected OpenTelemetry GenAI and OpenInference fields. Imported span boundaries are marked reconstructed; source timing and unknown status remain explicit.
- An executable local support-agent example: actual Python control flow, a read-only catalog lookup, a validation failure, one correction retry, and distinct successful/failed outcomes. Its provider is a labeled deterministic stand-in, not a language model. No network or credentials are required.

## Try it

Python 3.11 or newer is required. From an extracted source archive or a checkout of this tag:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade 'pip>=26.2'
python -m pip install .
python examples/record_agent.py
afr view
```

Open either generated recording in the viewer. Add `--capture-content` to the example command to inspect the filtered argument correction and tool result. Each default run writes to a new temporary directory. The packaged viewer is ready to use; Node is needed only to develop or rebuild it.

The attached wheel and source distribution use Python's prerelease version `0.1.0a1`, corresponding to GitHub tag `v0.1.0-alpha.1`. `SHA256SUMS` covers those two files and the explicitly attached source ZIP. There is no package-registry release.

## Alpha boundaries

Recorded playback moves through saved observations. It does not execute an agent again, reproduce a model response, restore external state, or undo a tool's effects. Capture is read-only with respect to the wrapped operation's arguments and results, but recording allocates memory and writes files. It has overhead and can lose evidence on interruption or storage failure.

Metadata, static labels, timing, and structure can still disclose information. Recordings are plaintext; filtering and reduced exports are not guarantees of anonymity or safe publication. Review any file before sharing it. Imported content is untrusted, and the OTLP importer deliberately supports only the documented subset.

This alpha has no hosted service, live collector, automatic instrumentation, or provider integration. It is independent of OpenClaw and bundles no OpenClaw adapter, code, or branding. Windows and browsers beyond the documented Chromium checks are not qualified. Schema and API details may change during the alpha.

The tagged source includes `docs/validation.md` for scoped test evidence, `docs/example.md` for the executed workflow, `docs/interoperability.md` for import limitations, and `docs/privacy.md` for the threat model. CI results must be assessed for the tagged commit; a workflow file alone is not evidence of a successful run. This release makes no production-readiness, benchmark, or security-certification claim.

Licensed under MIT. Bundled viewer component notices are included in `THIRD_PARTY_NOTICES.md` and the installed viewer. For a suspected vulnerability, use the repository's **Security → Report a vulnerability** channel once private reporting is enabled; do not post a sensitive recording in a public issue.
