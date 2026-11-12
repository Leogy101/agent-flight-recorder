# Change log

## Unreleased — preparation for 0.1.0

- Added an executing, dependency-free support-agent example with a clearly identified simulated provider, real local read-only lookup, argument-correction retry, and success/failure recordings.
- Fixed overlapping literal redaction and transformed-key collisions, preserving privacy and payload meaning.
- Preserved application execution when runtime span-ID generation fails; exposed skipped boundaries from unsupported repeated roots or reused span scopes.
- Aligned the recorder with the 64-link schema bound and Python/JavaScript duplicate and integer semantics; accepted case-insensitive OTLP IDs.
- Corrected playback conflict timing, stale asynchronous imports, and incomplete-input handling; improved inspection and keyboard navigation.
- Added the supplied project logo, refreshed screenshots, installation/example guides, engineering findings, version/dependency documentation, and release preparation.
- Added installed-wheel CI checks and pinned action revisions. Kept Python runtime dependencies at zero and the existing local architecture intact.

No public release, tag, package upload, or GitHub push has occurred. Version 0.1.0 in package metadata is the current local alpha build, not evidence of a published release.
