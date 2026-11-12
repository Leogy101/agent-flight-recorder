# Publish the first GitHub prerelease

This is a conditional runbook, not evidence that publication has happened. The proposed destination is `Leogy101/agent-flight-recorder`, public, with tag `v0.1.0-alpha.1`. Python distribution metadata uses the corresponding `0.1.0a1` version. No package-registry upload is part of this release.

Prepare and review the final commit, local verification results, release notes, and exact asset hashes before requesting publication approval. Run the remote mutation steps only when approval covers that repository, visibility, commit, and prerelease. A prior approval covering those actions is sufficient. If any gate fails, stop and fix it; changed source requires another qualified commit and matching assets.

## Readiness and ownership

- Review [validation evidence](validation.md), [the release checklist](release-checklist.md), [privacy](privacy.md), and [security reporting](../SECURITY.md). Local passing checks do not establish that GitHub Actions has passed.
- Review the complete history being pushed, including synthetic recordings and screenshots. Ignore patterns prevent many accidental additions, but do not remove already tracked files or historical secrets.
- The project is MIT licensed. The wheel includes the project license and bundled viewer notices; source releases include `THIRD_PARTY_NOTICES.md`. React, React DOM, Scheduler, and Vite's bundled preload helper have MIT notices. Python runtime dependencies are empty; Python development/build tools and npm build/test tools remain development dependencies. See [dependency declarations](dependencies.md).
- This is an independent project. It bundles no OpenClaw code, dependencies, adapter, or branding. No live OpenClaw credentials or private configuration locations were accessed during this review. Repository ignore rules exclude common private configuration names; they do not prove the contents of external locations.
- Confirm the account still matches the approved owner. An existing repository or remote is a reason to inspect the situation, not overwrite it. Do not change authentication as part of this runbook.

From the repository root, start a dedicated Bash shell for this runbook:

```sh
bash
```

Run all following blocks in that same shell, beginning with `set -euo pipefail` below. A failed command or assertion exits this shell, including failures within pipelines. Do not paste subsequent blocks into the parent shell after a failure; resolve it and reestablish the checked variables and gates in a new dedicated shell. These initial checks are read-only:

```sh
set -euo pipefail
AFR_OWNER="Leogy101"
AFR_REPO="$AFR_OWNER/agent-flight-recorder"
AFR_TAG="v0.1.0-alpha.1"
AFR_ROOT="$(git rev-parse --show-toplevel)"
AFR_COMMIT="$(git rev-parse HEAD)"
git status --short
git branch --show-current
git remote -v
git log --oneline --decorate
gh auth status
test "$(gh api user --jq .login)" = "$AFR_OWNER"
test -z "$(git status --porcelain)"
test "$(git branch --show-current)" = main
```

The working tree must be clean, the approved branch must be `main`, and the final commit hash must be recorded in the approval evidence. If using a different approved owner, change `AFR_OWNER` and the repository links before preparing that commit.

## Prepare exact assets locally

Use a fresh clone of the approved commit and a fresh build environment. Qualify that checkout with the documented Python, viewer, Chromium, and installed-wheel checks. The committed static viewer must match a Node 24 build. Do not build release assets from an uncommitted working tree or reuse earlier files in `dist/`.

The following build commands use a new ignored destination and refuse to reuse it. They require the final commit to exist locally. They do not publish anything:

```sh
AFR_ASSETS="$AFR_ROOT/release-artifacts/$AFR_TAG"
test ! -e "$AFR_ASSETS"
mkdir -p "$AFR_ASSETS"
AFR_BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/afr-release.XXXXXX")"
git clone --no-local --no-hardlinks "$AFR_ROOT" "$AFR_BUILD_ROOT/source"
git -C "$AFR_BUILD_ROOT/source" checkout --detach "$AFR_COMMIT"
test "$(git -C "$AFR_BUILD_ROOT/source" rev-parse HEAD)" = "$AFR_COMMIT"
python3 -m venv "$AFR_BUILD_ROOT/build-env"
"$AFR_BUILD_ROOT/build-env/bin/python" -m pip install --upgrade 'pip>=26.2' 'build>=1,<2'
"$AFR_BUILD_ROOT/build-env/bin/python" -m build --outdir "$AFR_ASSETS" "$AFR_BUILD_ROOT/source"
git archive --format=zip --prefix="agent-flight-recorder-$AFR_TAG/" \
  --output="$AFR_ASSETS/agent-flight-recorder-$AFR_TAG-source.zip" "$AFR_COMMIT"
```

Inspect both distribution file lists and metadata. Confirm version `0.1.0a1`, no Python runtime dependencies, viewer assets and notices in the wheel, and examples/data, schema, fixtures, tests, and documentation in the source distribution. Install the **exact** new wheel into a fresh environment with no dependencies and run its smoke check from the same checkout:

```sh
python3 -m venv --without-pip "$AFR_BUILD_ROOT/installed"
"$AFR_BUILD_ROOT/build-env/bin/python" -m pip --python "$AFR_BUILD_ROOT/installed/bin/python" \
  install --no-index --no-deps "$AFR_ASSETS/agent_flight_recorder_local-0.1.0a1-py3-none-any.whl"
"$AFR_BUILD_ROOT/installed/bin/python" "$AFR_BUILD_ROOT/source/tests/installed_smoke.py"
```

Also check that the source archive contains no environment, credentials, real recordings, or unrelated project files. Build tooling is range-constrained rather than fully locked, so this procedure binds reviewed artifact bytes to a commit; it does not promise bit-for-bit reproducible builds.

After those checks, calculate hashes for exactly three assets:

```sh
python3 - "$AFR_ASSETS" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys

root = Path(sys.argv[1])
names = (
    "agent_flight_recorder_local-0.1.0a1-py3-none-any.whl",
    "agent_flight_recorder_local-0.1.0a1.tar.gz",
    "agent-flight-recorder-v0.1.0-alpha.1-source.zip",
)
lines = [f"{sha256((root / name).read_bytes()).hexdigest()}  {name}\n" for name in names]
with (root / "SHA256SUMS").open("x", encoding="ascii") as output:
    output.writelines(lines)
PY
```

Review these four files and the prepared [release notes](release-notes-v0.1.0-alpha.1.md) with the final commit. Checksums detect changed bytes; they are not signatures or independent build attestations.

## Create and push, after approval

Create an empty public repository using the existing source and then set its topics. This deliberately keeps the first history push as a separate step. The owner is explicit; the existing README, license, and ignore file are retained. These options are documented in [repository creation](https://cli.github.com/manual/gh_repo_create) and [repository settings](https://cli.github.com/manual/gh_repo_edit).

```sh
gh repo create "$AFR_REPO" --public --source . --remote origin \
  --description "Local-first recordings, timeline inspection, and recorded playback for AI agent debugging."
gh repo edit "$AFR_REPO" \
  --add-topic ai-agents --add-topic observability --add-topic debugging \
  --add-topic opentelemetry --add-topic python --add-topic local-first
git remote get-url origin
```

Verify that `origin` identifies the approved `Leogy101/agent-flight-recorder` repository. Enable private vulnerability reporting and confirm it is enabled. The PUT requires repository administration access and returns no body on success; GET supplies the boolean status. The explicit `2026-03-10` header below matches the official API examples retrieved during release preparation. [GitHub's reporting API](https://docs.github.com/en/rest/repos/repos#enable-private-vulnerability-reporting-for-a-repository)

```sh
gh api --method PUT \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  "repos/$AFR_REPO/private-vulnerability-reporting"
test "$(gh api \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2026-03-10' \
  "repos/$AFR_REPO/private-vulnerability-reporting" --jq .enabled)" = true
test -z "$(git status --porcelain)"
test "$(git branch --show-current)" = main
test "$(git rev-parse HEAD)" = "$AFR_COMMIT"
git push --set-upstream origin main
gh repo edit "$AFR_REPO" --default-branch main
```

Check that the public repository's Security area offers **Report a vulnerability**, as described in [GitHub's private reporting guide](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting). Do not advertise reporting as enabled until the check succeeds.

## Require actual remote CI before a tag or release

Select the push run for the exact approved commit. Empty results mean no verified run exists yet. [Run filtering](https://cli.github.com/manual/gh_run_list)

```sh
gh run list --repo "$AFR_REPO" --workflow ci.yml --event push \
  --branch main --commit "$AFR_COMMIT" \
  --json databaseId,headSha,status,conclusion,url
AFR_RUN_ID="REPLACE_WITH_MATCHING_RUN_ID"
gh run watch "$AFR_RUN_ID" --repo "$AFR_REPO" --compact --exit-status --interval 10
gh run view "$AFR_RUN_ID" --repo "$AFR_REPO" \
  --json headSha,status,conclusion,jobs,url
```

`gh run watch` currently does not support fine-grained personal access tokens. If that limitation applies, inspect `gh run view` periodically until completion; do not switch credentials automatically. [Watch limitations](https://cli.github.com/manual/gh_run_watch)

Check the commit and completed success explicitly. `gh run view --exit-status` reports failure, but is not proof that a pending run has finished. The current workflow must show five successful jobs: four Python OS/version combinations and the viewer job. [Run status fields](https://cli.github.com/manual/gh_run_view)

```sh
test "$(gh run view "$AFR_RUN_ID" --repo "$AFR_REPO" --json headSha --jq .headSha)" = "$AFR_COMMIT"
test "$(gh run view "$AFR_RUN_ID" --repo "$AFR_REPO" \
  --json status,conclusion,jobs \
  --jq '.status == "completed" and .conclusion == "success" and (.jobs | length) == 5 and all(.jobs[]; .status == "completed" and .conclusion == "success")')" = true
test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$AFR_COMMIT"
```

The remote branch must still equal `AFR_COMMIT`. Retain the successful run URL with the release evidence. If CI changes the source, rebuild and review assets from the resulting commit, push it, and repeat this gate.

## Tag and publish the reviewed prerelease

Proceed only if approval covers this release and the remote CI gate passed. Confirm the tag does not already exist locally or remotely. Never force an existing tag. Create an annotated tag at the verified commit, then verify the remote tag's peeled commit equals it:

```sh
AFR_EXISTING_LOCAL_TAG="$(git tag --list "$AFR_TAG")"
test -z "$AFR_EXISTING_LOCAL_TAG"
AFR_EXISTING_REMOTE_TAG="$(git ls-remote origin "refs/tags/$AFR_TAG" "refs/tags/$AFR_TAG^{}")"
test -z "$AFR_EXISTING_REMOTE_TAG"
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$AFR_COMMIT"
git tag -a "$AFR_TAG" "$AFR_COMMIT" -m "Agent Flight Recorder $AFR_TAG"
git push origin "refs/tags/$AFR_TAG"
test "$(git ls-remote origin "refs/tags/$AFR_TAG^{}" | cut -f1)" = "$AFR_COMMIT"
```

The current workflow also runs on tag pushes. List the runs for this commit and select the push run whose `headBranch` is exactly `v0.1.0-alpha.1`; do not select the earlier `main` run. An absent or pending tag run is not a passing gate. Apply the same read-only polling fallback if `gh run watch` is unavailable:

```sh
gh run list --repo "$AFR_REPO" --workflow ci.yml --event push \
  --commit "$AFR_COMMIT" \
  --json databaseId,headBranch,headSha,status,conclusion,url
AFR_TAG_RUN_ID="REPLACE_WITH_MATCHING_TAG_RUN_ID"
gh run watch "$AFR_TAG_RUN_ID" --repo "$AFR_REPO" --compact --exit-status --interval 10
gh run view "$AFR_TAG_RUN_ID" --repo "$AFR_REPO" \
  --json event,headBranch,headSha,status,conclusion,jobs,url
test "$(gh run view "$AFR_TAG_RUN_ID" --repo "$AFR_REPO" --json event --jq .event)" = push
test "$(gh run view "$AFR_TAG_RUN_ID" --repo "$AFR_REPO" --json headBranch --jq .headBranch)" = "$AFR_TAG"
test "$(gh run view "$AFR_TAG_RUN_ID" --repo "$AFR_REPO" --json headSha --jq .headSha)" = "$AFR_COMMIT"
test "$(gh run view "$AFR_TAG_RUN_ID" --repo "$AFR_REPO" \
  --json status,conclusion,jobs \
  --jq '.status == "completed" and .conclusion == "success" and (.jobs | length) == 5 and all(.jobs[]; .status == "completed" and .conclusion == "success")')" = true
```

Recheck the four approved asset hashes. Attach explicit filenames so earlier `0.1.0` packages cannot be included accidentally. `--verify-tag` prevents automatic tag creation, and the release is explicitly a prerelease without the Latest label. [Release command behavior](https://cli.github.com/manual/gh_release_create)

```sh
gh release create "$AFR_TAG" --repo "$AFR_REPO" \
  --verify-tag --prerelease --latest=false \
  --title "Agent Flight Recorder $AFR_TAG" \
  --notes-file docs/release-notes-v0.1.0-alpha.1.md \
  "$AFR_ASSETS/agent_flight_recorder_local-0.1.0a1-py3-none-any.whl" \
  "$AFR_ASSETS/agent_flight_recorder_local-0.1.0a1.tar.gz" \
  "$AFR_ASSETS/agent-flight-recorder-v0.1.0-alpha.1-source.zip" \
  "$AFR_ASSETS/SHA256SUMS"
gh release view "$AFR_TAG" --repo "$AFR_REPO" \
  --json tagName,isDraft,isPrerelease,assets,url
```

Confirm the published tag, prerelease flag, notes, and all four assets; download the release assets into a new directory and compare their hashes with the reviewed local files. Keep the actual repository, CI run, and release URLs in the publication record. [Release inspection fields](https://cli.github.com/manual/gh_release_view)
