# Validation and release status

Verified November 12, 2026 for Phase 2 of the existing local alpha. No GitHub push, public release, tag, or registry upload has occurred. GitHub Actions is configured but has not run remotely. These results are from executed local commands, not inferred from CI configuration.

## Executed verification

| Check | Actual result |
| --- | --- |
| Python suite, macOS / Python 3.14.6 | **157 tests and 37 subtests passed**, 4.57 seconds. |
| Python suite, Linux ARM64 / Python 3.11.18 container | **157 tests and 37 subtests passed**, 4.63 seconds. Source was mounted read-only and copied into the disposable container. |
| Viewer unit suite | **43 tests passed**. |
| TypeScript and production build | Passed; current JS/CSS/logo assets are bundled with the Python package. |
| Real Chromium acceptance | **18 workflows passed**. No page errors, attempted external requests, or data uploads were observed. |
| Executing local agent | Success and intended failure both ran; actual lookups, validation/retry order, original exception identity, unchanged catalog, no-network behavior, and both privacy modes are covered by 14 integration tests. |
| Clean quickstart | Fresh virtual environment, installer upgrade, editable installation, both selected-content scenarios, and CLI validation completed. Success has 15 events; failure has 13. Both validate with zero evidence warnings. |
| Installed wheel | Fresh interpreter without pip or development packages installed the wheel offline with `--no-index --no-deps`. Recording, default privacy, reader, CLI validation, server headers, JS/CSS/logo, demos, and notices passed the smoke script. |
| Cross-language contract | Synthetic Python, independently produced TypeScript, executed example, converted OTLP, and browser-produced reduced files pass their applicable schema/reader checks. |
| Dependency checks | `pip check` passed. Full npm audit, including development packages, reported zero vulnerabilities. The Python environment audit reported no known vulnerabilities after upgrading the affected installer; the unpublished project has no advisory-database entry. |
| Demonstration | A real-browser synthetic walkthrough was recorded as a 22.72-second VP9 WebM, 1440 × 1280, 2,835,619 bytes. Screenshots and a video frame were inspected visually. |

The browser checks include failure inspection; Python-readable reduced export; cursor playback; filtering; interrupted evidence; inert hostile markup; explicit partial import; conflicts retained after sharing; source-time imports; successful agent recovery; failed agent execution; keyboard inspector tabs; exact start/end navigation; timed playback; empty search state; 390-pixel layout; metadata-only capture; and the 10,000-event workload. Desktop screenshots were captured at 1440 pixels wide. The successful and failed samples are separately inspectable.

Earlier checks exposed real issues and did not all pass on the first attempt: review repros exposed the defects listed in [engineering review](engineering-review.md), browser acceptance found indistinguishable retry row names, and the first installed-wheel smoke check incorrectly assumed absolute asset URLs. The accessible names and smoke script were corrected and the affected checks rerun successfully. No unresolved test failure is being treated as a pass.

## Measured performance

Reference machine: Apple M4 Pro, Mac16,11, 64 GiB RAM, macOS 26.3.1, arm64. Capture uses Python 3.14.6; browser checks use Chromium 158.0.8127.18 and Node 26.10.0.

| Workload | Observed result |
| --- | --- |
| 1,000 empty tool scopes, metadata only | **20.250 μs median; 24.666 μs p95 per scope**, including two synchronous flushed records, IDs, filtering, and context work. |
| Capture size | **2,004 events; 1,285,619 bytes**, about 641.5 bytes/event. |
| Browser import plus first rendered view | **356 ms** for **10,000 events / 3,946,806 bytes** in the latest acceptance run. |
| Search/filter update | **6 ms** in that run. |
| Browser-reported used JavaScript heap | **53,500,000 bytes (~53.5 MB)** at the end of the acceptance sequence. This is not peak or total browser memory. |

These are single-machine synthetic measurements, not production guarantees. The browser numbers include test-driver overhead and normal background activity. Capture timing does not simulate slow disks, network filesystems, large sensitive payloads, or actual model latency. Flushing is not fsync durability. A new Unicode check initially raised the capture median to 31.875 μs; an ASCII fast path reduced that measured overhead while retaining Unicode regression coverage.

## Reproduce

From an installed development checkout:

```sh
python -m pytest
python benchmarks/capture.py --output work/capture-benchmark.json
cd viewer
npm ci
npm test
npm run build
npx playwright install chromium
cd ..
node tests/browser-check.mjs
python -m build
python -m venv --without-pip work/installed
python -m pip --python work/installed/bin/python install --no-index --no-deps dist/*.whl
work/installed/bin/python tests/installed_smoke.py
node scripts/record-demo.mjs
```

Browser checks start and stop their own loopback server, save their report under `work/browser`, and refresh reviewed synthetic screenshots under `docs/screenshots`. The demo script produces the short WebM and does not invoke recorded tools. Use fresh output directories for example runs; they intentionally refuse overwrites.

The wheel test deliberately uses a separate interpreter so an editable source installation cannot hide missing package files. CI also rejects checked-in viewer assets that differ from a fresh build. The source distribution includes the example's local JSON catalog, schema, tests, docs, viewer source/logo, and build configuration.

## Honest support and remaining work

Locally verified: macOS/Python 3.14, Linux ARM64/Python 3.11, and Chromium. CI targets the minimum/latest Python versions on macOS/Linux and Node 24 for frontend work; those remote matrix jobs remain unexecuted. Python 3.12/3.13, Windows, other browser engines, screen readers, real providers, distributed processes, and production workloads are not claimed as individually verified here.

The five-minute quickstart was followed mechanically in a clean environment. Human completion time and the original onboarding/diagnosis targets remain unmeasured. Get first-time developer feedback, configure private vulnerability reporting, and run remote CI after authorized publication before tagging v0.1.0. See [release preparation](release-checklist.md).
