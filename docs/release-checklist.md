# Preparing the first public 0.1.0 release

Phase 2 prepares a locally verified alpha for GitHub. It does not publish the repository or package. Retain the existing MIT license: it fits the intended small, reusable open-source debugging tool; preserve bundled third-party notices and identify the user-supplied logo as project artwork.

## Completed locally

- Existing architecture reviewed; confirmed important defects reproduced and fixed with regression coverage.
- Executing offline agent example, reviewed sample recordings, privacy defaults, and failure walkthrough supplied.
- README, architecture/contract, dependency/support policy, security guidance, screenshots, and contribution instructions prepared.
- Python, viewer, browser, package, dependency, and performance verification results recorded in `validation.md`.
- Local commits created; nothing pushed or published.

## Before a public release or tag

1. Choose the final GitHub repository name and description; check naming collisions and use the intended public commit-author email. The working title is shared by unrelated projects.
2. Create the repository and push only when authorized. Let the configured GitHub Actions matrix complete; local results do not substitute for a remote run.
3. Enable an actual private vulnerability-reporting channel and update `SECURITY.md` with its destination. Do not invent a contact address or publish sensitive reports in public issues.
4. Have at least one unfamiliar developer follow the five-minute quickstart and diagnose the example failure. Automated browser acceptance does not measure human onboarding time or replace a screen-reader review.
5. Recheck dependency advisories and the exact wheel/source contents, then tag an explicitly labeled alpha or 0.1.0 as appropriate. Publish registry artifacts only after separately deciding the package name and release policy.

## Optional follow-up, driven by use

- Test Firefox, Safari, Windows, screen readers, and slow-disk behavior before claiming support.
- Consolidate version strings when the next version is introduced; the current producer, CLI, and package version agree.
- Consider a shared cross-language malformed-input corpus, rather than adding a framework or rewriting the parser.
- Expand OTLP mappings only with concrete source fixtures. Source exporter drop counts, links, and arbitrary events are presently not mapped; full conformance is not claimed.

Do not add distributed ingestion, cloud accounts, automatic instrumentation, model orchestration, or execution replay simply to increase feature count.
