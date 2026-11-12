# Change log

## v0.1.0-alpha.1 — 2026-11-12

- Added an executing, dependency-free support-agent example with a clearly identified simulated provider, real local read-only lookup, argument-correction retry, and success/failure recordings.
- Fixed overlapping literal redaction and transformed-key collisions, preserving privacy and payload meaning.
- Preserved application execution when runtime span-ID generation fails; exposed skipped boundaries from unsupported repeated roots or reused span scopes.
- Aligned the recorder with the 64-link schema bound and Python/JavaScript duplicate and integer semantics; accepted case-insensitive OTLP IDs.
- Corrected playback conflict timing, stale asynchronous imports, and incomplete-input handling; improved inspection and keyboard navigation.
- Added the supplied project logo, refreshed screenshots, installation/example guides, engineering findings, version/dependency documentation, and release preparation.
- Added installed-wheel CI checks and pinned action revisions. Kept Python runtime dependencies at zero and the existing local architecture intact.
- Removed an unnecessary hostname lookup from loopback-server startup after diagnostic CI identified resolver stalls on macOS with Python 3.11 and 3.14; retained real HTTP, shutdown, and port-reuse checks with bounded failure diagnostics. See the [investigation and verification status](docs/macos-startup.md).

Release preparation aligns Python metadata at `0.1.0a1` and frontend/GitHub naming at `0.1.0-alpha.1`, adds Vite helper attribution, strengthens private-config exclusions, and qualifies clean installation, OTLP import, privacy-safe export, and viewer shutdown/restart. Existing schema and historical fixture versions remain unchanged.

See the [GitHub release record](https://github.com/Leogy101/agent-flight-recorder/releases/tag/v0.1.0-alpha.1) for publication status, attached assets, and remote verification. No package-registry upload is part of this alpha.
