# Prepublication local qualification snapshot

Verified locally on November 12, 2026 for `v0.1.0-alpha.1` (`0.1.0a1` in Python). The implementation was qualified at local commit `a80fcb3` using a **new local Git clone, a new Python virtual environment, and a fresh npm installation**. Subsequent release-evidence documentation does not change runtime code or generated assets. Final artifacts must match the final preparation commit and pass the release artifact checks.

This is a historical snapshot taken before public repository, tag, or release publication. Remote GitHub Actions and public HTTPS clone/tag access were not exercised in this snapshot; the equivalent local clone/install path passed. Check [GitHub Actions](https://github.com/Leogy101/agent-flight-recorder/actions) for current commit-specific results and the [alpha release record](https://github.com/Leogy101/agent-flight-recorder/releases/tag/v0.1.0-alpha.1) for remote publication checks. Local tests do not substitute for remote CI.

Before publication, an authorized identity-only rewrite replaced author and committer email addresses in four commits with a GitHub noreply address. File trees, names, dates, and commit messages were preserved exactly; commit references in these documents use the replacement hashes. The private backup is not a release artifact.

## Executed checks

| Environment / check | Result |
| --- | --- |
| Fresh clone on macOS, Python 3.14.6 | **160 tests and 37 subtests passed**, 4.82 s |
| Clean archived source on Linux ARM64, Python 3.11.18 | **160 tests and 37 subtests passed**, 4.58 s |
| Clean archived source on Linux ARM64, Python 3.12.16 | **160 tests and 37 subtests passed**, 4.65 s |
| Clean archived source on Linux ARM64, Python 3.13.18 | **160 tests and 37 subtests passed**, 4.63 s |
| Fresh npm install, Node 24.22.3 | **44 viewer tests passed** |
| TypeScript / production build | Passed; fresh Node 24 output matches committed assets exactly |
| Chromium 158.0.8127.18 acceptance | **18 workflows passed**; no observed page errors, external requests, or data uploads |
| Installed alpha wheel | Installed with `--no-index --no-deps` into a fresh interpreter without pip or development packages; version, capture, default privacy, CLI, OTLP import, JS/CSS/logo/notices, and serving checks passed |
| Shutdown / restart | Actual CLI process stopped with SIGINT and exit 0, then started successfully on the same port; repeated clean shutdown passed |
| Dependency checks | `pip check` passed in each Python test environment. Full npm audit and fresh Python environment advisory audit reported no known vulnerabilities in auditable packages |
| Media review | Current alpha screenshots and eight sampled frames from the 22.72 s, no-audio demo show synthetic data; desktop version label and narrow layout fit |

The wheel smoke script rejects editable source imports so a development environment cannot conceal missing package files. It was initially invoked in the existing editable environment, correctly failed that guard, and was then run successfully in the separate installed-alpha environment. No product failure was suppressed. This local snapshot makes no claim that remote CI passed.

## Developer-experience qualification

The README installation sequence was followed in the fresh local clone: create `.venv`, upgrade pip, install the checkout, run the example with selected content, and validate both outputs. The installed CLI reports `0.1.0-alpha.1`.

1. **Clone and install:** a new clone of the local candidate contains no inherited virtual environment or node_modules. Source installation completed successfully. Public GitHub HTTPS clone/tag access was outside this local snapshot.
2. **Python versions:** the exact four interpreter/platform combinations above ran the complete Python suite. CI is configured for minimum/latest versions on macOS/Linux; intermediate versions were additionally checked locally on Linux.
3. **Dependencies:** Python runtime requirements remain empty. Build/development downloads are separate from runtime; npm uses its committed lockfile.
4. **Offline agent:** actual local validation, catalog lookup, correction retry, and answer/error behavior ran. The synthetic success capture has 15 events; failure has 13. Both validate with zero evidence warnings because an observed application failure is not recorder failure.
5. **Recording and inspection:** browser acceptance opens freshly executed captures, displays arguments/error categories, and distinguishes recovered success from failed root outcome.
6. **Viewer startup:** bundled assets are served only on loopback. Package tests fetch JS/CSS/logo, a bundled demo, and license notices and inspect security headers.
7. **Playback:** cursor, timed playback, and exact start/end navigation work on saved evidence, including capture-marker inspection. No tool or model runs in the viewer.
8. **OTLP:** the installed CLI converts the committed OTLP sample; browser checks use source-time intervals. Reconstructed provenance, default omission, and lack of native elapsed timestamps are checked.
9. **Reduced exports:** a real browser download reopens in Python; sensitive synthetic payloads/labels are absent, and known conflicts remain visible after export/reopen.
10. **Shutdown and restart:** SIGINT closes the real CLI cleanly and releases its port, as tested above.

Browser acceptance also covers filtering, interrupted evidence, hostile markup as inert text, explicit partial import, keyboard inspector tabs, empty search, a 390 px viewport, and metadata-only example output. It observes no network uploads or remote requests during those workflows; that is scoped evidence, not a guarantee about arbitrary extensions or modified builds.

## Measured performance

Apple M4 Pro (Mac16,11), 64 GiB RAM, macOS 26.3.1 arm64. Capture: Python 3.14.6. Browser: Chromium 158.0.8127.18, Node 24.22.3. Results are from the fresh clone's acceptance/benchmark commands.

| Workload | Observed |
| --- | --- |
| 1,000 empty tool scopes, metadata only | **21.625 μs median; 26.833 μs p95** per scope |
| Capture size | **2,004 events / 1,285,686 bytes**, 641.6 bytes/event |
| Import plus first rendered view | **359 ms** for **10,000 events / 3,946,806 bytes** |
| Search/filter update | **6 ms** |
| Browser-reported used JavaScript heap | **47,400,000 bytes (~47.4 MB)** at the end of acceptance; not peak or total process memory |

Capture measurements include IDs, filtering, context, and two synchronous flushed writes, but not application work. Browser measurements include test-driver overhead. These are synthetic single-machine measurements; slow disks, maximum-content payloads, real model latency, production throughput, and fsync durability are not represented. The prior Phase 2 reference (commit `bf2d61b`) measured 20.250 μs median / 24.666 μs p95 capture and 356 ms / 6 ms browser import/filter; small variation is expected.

## Reproduce local checks

From a fresh checkout with Python 3.11–3.14 and Node 24:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade 'pip>=26.2'
python -m pip install -e '.[dev]'
python -m pytest
cd viewer
npm ci
npm test
npm run build
npx playwright install chromium
cd ..
node tests/browser-check.mjs
python benchmarks/capture.py --output work/capture-benchmark.json
python -m build
python -m venv --without-pip work/installed
python -m pip --python work/installed/bin/python install --no-index --no-deps dist/agent_flight_recorder_local-0.1.0a1-py3-none-any.whl
work/installed/bin/python tests/installed_smoke.py
```

The browser script starts/stops its own server, writes `work/browser/report.json`, and refreshes synthetic screenshots. `node scripts/record-demo.mjs` regenerates the short demonstration; viewer pauses do not affect agent execution timing. Fresh example destinations intentionally refuse overwrite.

[Publication instructions](publication.md) build release files from a separate clean clone, verify exact package contents, and calculate hashes. They do not promise bit-identical builds with arbitrary range-selected Python build tools. Actual build/test versions and hashes accompany the locally prepared release evidence.

## External release checks and remaining human checks

The publication process separately verifies public clone/tag access, private vulnerability reporting, the five-job GitHub Actions matrix for the exact commit, and release download checksums. Those remote results belong in the release record, not this prepublication local snapshot.

First-time-user completion time, screen-reader usability, Windows, Firefox/Safari, production/slow-disk behavior, and distributed processes remain unverified. The provider is a deterministic simulation, not a live LLM. This release supports recorded playback only. See [release gates](release-checklist.md), [security review](release-security-review.md), and [limitations](release-notes-v0.1.0-alpha.1.md).
