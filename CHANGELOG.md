# Change log

## v0.1.0-alpha.1 — release candidate, 2026-11-12

- Added an executing, dependency-free support-agent example with a clearly identified simulated provider, real local read-only lookup, argument-correction retry, and success/failure recordings.
- Fixed overlapping literal redaction and transformed-key collisions, preserving privacy and payload meaning.
- Preserved application execution when runtime span-ID generation fails; exposed skipped boundaries from unsupported repeated roots or reused span scopes.
- Aligned the recorder with the 64-link schema bound and Python/JavaScript duplicate and integer semantics; accepted case-insensitive OTLP IDs.
- Corrected playback conflict timing, stale asynchronous imports, and incomplete-input handling; improved inspection and keyboard navigation.
- Added the supplied project logo, refreshed screenshots, installation/example guides, engineering findings, version/dependency documentation, and release preparation.
- Added installed-wheel CI checks and pinned action revisions. Kept Python runtime dependencies at zero and the existing local architecture intact.

Release preparation aligns Python metadata at `0.1.0a1` and frontend/GitHub naming at `0.1.0-alpha.1`, adds Vite helper attribution, strengthens private-config exclusions, and qualifies clean installation, OTLP import, privacy-safe export, and viewer shutdown/restart. Existing schema and historical fixture versions remain unchanged.

No public release, tag publication, package upload, or GitHub push has occurred. This heading names the prepared candidate; it does not claim external publication.
