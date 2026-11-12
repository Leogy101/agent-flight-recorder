# v0.1.0-alpha.1 publication gate

The prepared release is an alpha of the existing independent project. Python packaging uses `0.1.0a1`; the GitHub tag and viewer use `0.1.0-alpha.1`. Schema and transformation version `0.1` are intentionally separate. Historical synthetic fixtures retain the provenance of their original generation.

## Required local evidence

- Current source, complete reachable Git history plus reflog coverage, and exact release artifacts have been scanned for credentials, private configuration, personal paths, and accidental logs. See [security review](release-security-review.md).
- Review the Git author and committer identity that will become public. Changing future configuration does not change earlier commits. Do not rewrite history or change the identity without authorization.
- Confirm the MIT project license and bundled MIT notices for React, React DOM, Scheduler, and Vite's helper. Preserve the supplied logo and its provenance. This repository contains no OpenClaw code, adapter, branding, or dependency.
- Qualify a clean clone and fresh environment: install, run both offline agent scenarios, validate recordings, open the viewer, inspect/play back events, import the OTLP sample, create a reduced export, and stop/restart cleanly.
- Execute Python, viewer, browser, and installed-package checks; reproduce the documented benchmarks. Record actual environments and results in [validation](validation.md).
- Verify package versions, empty Python runtime dependencies, source archive contents, bundled viewer freshness, and release-file SHA-256 hashes. Use exact alpha filenames, not a wildcard that includes old `0.1.0` artifacts.
- Commit verified preparation locally. Record the final commit and bind the release artifacts to it. Keep the repository working tree clean.

## Approval and external gates

No public repository, push, external tag, or release is authorized by preparation alone. Present the candidate, security findings, public commit identity, exact destination `Leogy101/agent-flight-recorder`, and artifact hashes for explicit approval.

After approval, follow [the publication runbook](publication.md). Create the approved public repository, enable and verify private vulnerability reporting, then push the reviewed commit. GitHub Actions must actually complete successfully for that exact commit before the tag/release gate. A configuration file or local test pass is not a remote CI result. Publish the annotated `v0.1.0-alpha.1` tag and a prerelease with the reviewed files, then verify published metadata and downloaded checksums.

No PyPI publishing is part of this request. No live OpenClaw credential access, GlauxOS inspection, credential changes, destructive Git operation, or history rewrite is part of preparation or the publication runbook.

## Remaining alpha limitations

Recorded playback is not deterministic execution replay. Capture is explicit, synchronous, single-process, plaintext, and not an audit-grade record. The importer supports a limited OTLP file shape. Unknown or missing evidence stays unknown. The simulated provider is not a real language model.

Human onboarding/diagnosis timing, screen-reader usability, additional browsers, Windows, and production/slow-disk behavior remain follow-up work. Obtain first-time developer feedback before declaring stable support; do not add cloud services or orchestration merely to expand the feature list.
