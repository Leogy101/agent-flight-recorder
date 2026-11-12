# Security

Use synthetic reproductions in public issues. Do not post credentials or real incident captures. A private reporting channel has not yet been configured; until one exists, avoid publicly disclosing sensitive exploit details or affected data.

Only the current 0.1.0 local alpha is being maintained; no supported public release is published yet. Confirmed important defects discovered during Phase 2 were fixed and documented in `docs/engineering-review.md`.

Version 0.1 is local development software. It is not a production observability service, remote server, security boundary, or audit-grade evidence system. Keep the viewer bound to loopback and run a trusted build. Review `docs/privacy.md` before enabling content capture or sharing files.

Security-sensitive changes should add regression coverage for unsafe content rendering, file access, host validation, resource limits, privacy filtering, and fail-open operation semantics where applicable.

For dependency support, audit results, and the installer update, see [dependencies](docs/dependencies.md). Before publication, configure a real private reporting destination and replace the prerelease reporting note above.
