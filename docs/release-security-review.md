# Release security review

Review date: November 12, 2026. Target: `v0.1.0-alpha.1` preparation.

The baseline review found **no confirmed credentials or private application data** in the tracked snapshot, reachable Git contents, or four existing package archives examined. Gitleaks reported zero findings in each of its three scan scopes. This is a bounded local review, not a guarantee that arbitrary secrets or personal information are absent.

## Baseline scope

This review ran while release preparation was in progress. Its snapshot and existing archives are distinct from the final release candidate, which requires a fresh scan after the preparation commits and package build.

| Scope | Examined |
| --- | --- |
| Current tracked snapshot | 84 files copied for a stable Gitleaks directory scan; no tracked symlinks |
| Git history | All 2 commits reachable from local refs; all 114 unique reachable file blobs checked separately |
| Reflog coverage | 2 unique reflog commit IDs and 2 reflog-reachable commits; zero additional commits outside all-ref reachability |
| Commit metadata | Both reachable commit objects checked for credential and personal-path patterns; no annotated tag refs existed |
| Existing `dist/` archives | Wheel: 22 members; source archive: 69 members |
| Existing `work/phase2-package/` archives | Wheel: 24 members; source archive: 90 members |
| Expanded archive contents | All 205 members examined; no archive members excluded |
| Supplemental current-file scan | 83 tracked files, 1,230 ignored or untracked files, 7,123 dependency/cache files, and repository-local Git configuration |
| Historical media metadata | All 8 reachable binary file blobs: 7 PNG versions and 1 WebM |

The supplemental scan observed one fewer tracked file than the earlier stable copy because release preparation was editing the checkout. It does not replace the final candidate scan. Twenty-six local symlinks were deliberately not followed. No regular file exceeded the supplemental scanner's 64 MiB per-file bound.

The review stayed within this repository and its existing package artifacts. It did not inspect external credential stores, live OpenClaw configuration or credentials, GlauxOS paths or configuration, or configuration referenced outside the repository. Repository-local `.git/config` was checked for credential patterns without printing its values. At this baseline, Git author and committer identity metadata was counted, not rewritten or reproduced in this report. The later authorized identity-only rewrite is documented in [validation](validation.md).

## Methods and results

Gitleaks `8.30.1` was downloaded from its [official release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1) into ignored local working storage. The Darwin ARM64 archive's SHA-256 matched the checksum published with that release. Nothing was globally installed or uploaded.

The local scanner used the built-in default rules, an explicit empty ignore file, `--ignore-gitleaks-allow`, and `--redact=100`. External Gitleaks configuration environment overrides were removed for these runs. The history invocation used `git --log-opts="--all --full-history"`; separate directory scans covered the stable tracked snapshot and expanded archives. Each completed successfully with **0 findings**. Retained local reports contain only safe categories, paths, counts, line positions, and commit identifiers, never matched secret values.

Supplemental byte-pattern checks covered common provider credentials, private-key headers, credential-bearing URLs, token-shaped values, and personal absolute paths. They examined all reachable file blobs, commit metadata, current repository files, and expanded archives. No credential-shaped or personal-path candidates appeared in the tracked files, reachable history, or archives.

Ignored build logs, virtual environments, installation metadata, and compiled caches contain local machine paths. These are local development artifacts excluded from the reviewed release files, not confirmed secret findings. Twelve credential-URL candidates in ignored third-party documentation/parser code and compiled copies contained standard example placeholders. Sensitive-name candidates were parser `token` modules and public CA certificate bundles, not private keys. No tracked or archive filename matched the sensitive-file screening rules.

## Samples, ignore rules, and media

The committed recording inventory is documented in [fixtures/README.md](../fixtures/README.md). Executed examples use a local simulated provider and synthetic order catalog; bundled demos are explicitly hand-authored illustrations. The reviewed example documentation identifies fake credential/redaction markers and distinguishes synthetic execution from model API activity. Committed JSONL fixtures and bundled demos are intentional ignore-rule exceptions and still require content review before adding or changing them.

Ignore probes confirmed exclusion of environment files, local recordings, working files, virtual environments, caches, build output, package output, dependencies, and the release preparation's credential/key filename patterns. Ignore rules do not protect files already tracked and do not establish that future samples are safe.

The six historical screenshot PNG blobs contain only image header/data/end chunks, with no text or EXIF metadata. A historical generated graphic additionally contains a C2PA provenance chunk; screening found no email or personal-path candidates in that chunk. The WebM metadata contains encoder, language, duration, and creation-time fields; no author, location, or personal-path candidate was found. C2PA signatures were not cryptographically validated. This metadata review did not perform exhaustive OCR or inspect every video frame.

## Limits and release gate

Pattern scanners can miss novel, encoded, encrypted, fragmented, or context-dependent secrets and private data. This review did not test whether any candidate credential was live, upload repository contents, inspect files beyond the authorized repository, follow local symlinks, or inspect dangling Git objects that are unreachable from both refs and reflogs. It is not a dependency-vulnerability audit or a substitute for application security testing.

Sanitized detailed evidence and tool verification are retained in ignored `work/phase3/`. That working directory, local environments, and logs must not be attached to a release.

Before publication, rerun the tracked-file, complete reachable-history, and expanded-archive scans against the final preparation commit and freshly built wheel/source archive. Record their commit, file/member counts, and results here or in the release checklist. The authorized publication still requires these final checks.

## Alpha qualification and final artifact evidence

The candidate implementation was qualified at `a80fcb3`. Updated screenshots display the alpha version; the desktop and narrow layouts were reviewed visually. Eight representative frames across the regenerated 22.72-second silent demonstration show only the committed synthetic workflow and redacted output. This is a sampled visual review, not exhaustive OCR or inspection of every frame.

Release preparation retains the verified scanner and generates the final commit/file/member counts and SHA-256 artifact manifest outside the repository. This avoids embedding a file's own final commit/hash in itself. The publication record must include that final scan result for the exact attached wheel, source distribution, and source ZIP; the baseline counts above are not silently presented as final-candidate counts. Do not attach ignored scan snapshots, virtual environments, logs, or credential stores.
