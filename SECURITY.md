# Security policy

## Supported release

`v0.1.0-alpha.1` (`0.1.0a1` in Python packaging) is the current alpha release candidate. Only this candidate is being qualified; no stable support or production security certification is promised. Public repository/release publication is pending approval.

## Report a vulnerability

After the repository is public and private reporting has been enabled, use GitHub's **Security → Report a vulnerability** on `Leogy101/agent-flight-recorder`. The direct destination will be `https://github.com/Leogy101/agent-flight-recorder/security/advisories/new`. Its availability must be verified during publication; it is not claimed to be enabled now.

If that private-reporting option is unavailable, do not disclose exploit details, credentials, personal data, or real recordings in public issues. Wait for an available private channel. No email address is invented as a fallback.

Include the affected release, impact, reproduction steps, and a minimal **synthetic** example. Share only the data needed to explain the issue. Do not attach actual customer captures. Ordinary non-sensitive bug reports may use public issues once the repository exists.

## Security boundaries

The viewer is a loopback-only developer tool, not an internet-facing service, security boundary, or audit system. Run a trusted build. Captured files are plaintext. Metadata labels can be sensitive even when content capture is disabled. Filtering reduces collection but cannot guarantee anonymity. Playback never executes recorded tools or models.

The tool does not read live OpenClaw credentials or private GlauxOS configuration. It records only explicitly supplied values. Those applications are not dependencies or supported integrations of this alpha. Do not copy their private configuration into this repository.

Review [privacy and threat model](docs/privacy.md), [dependency policy](docs/dependencies.md), and [known limitations](docs/release-notes-v0.1.0-alpha.1.md). Relevant tests cover inert text rendering, restricted file serving, Host validation, input bounds, redaction, and preservation of application behavior.

## Release review

The local release review checks current source, complete reachable Git history, and packaged artifacts. Known important Phase 2 issues and their regressions are documented in [engineering review](docs/engineering-review.md). Secret scanning and dependency advisories are point-in-time evidence, not proof that every vulnerability or private datum has been found. Any sensitive finding blocks publication until resolved or explicitly addressed with the owner.
