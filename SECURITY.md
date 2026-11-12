# Security

Use synthetic reproductions in public issues. Do not post credentials or real incident captures. A private reporting channel has not yet been configured; until one exists, avoid publicly disclosing sensitive exploit details or affected data.

Version 0.1 is local development software. It is not a production observability service, remote server, security boundary, or audit-grade evidence system. Keep the viewer bound to loopback and run a trusted build. Review `docs/privacy.md` before enabling content capture or sharing files.

Security-sensitive changes should add regression coverage for unsafe content rendering, file access, host validation, resource limits, privacy filtering, and fail-open operation semantics where applicable.
