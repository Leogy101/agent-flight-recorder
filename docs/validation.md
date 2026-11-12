# Validation and release status

Verified November 12, 2026. This is a local alpha implementation of the approved MVP. The repository and installable artifacts are prepared locally; GitHub publication and package-registry publication have not occurred. The configured GitHub Actions workflow has not run remotely.

## Verification results

| Check | Result |
| --- | --- |
| Python suite on macOS, Python 3.14.6 | 105 tests and 32 subtests passed. |
| Python suite on Linux ARM64, Python 3.11 container | 105 tests and 32 subtests passed. |
| Viewer unit tests | 28 passed, covering bounded parsing, sharing, evidence conflicts, privacy, timing, and interoperability. |
| TypeScript and production bundle | Passed. Only current hashed assets and reviewed demos are bundled. |
| Real Chromium browser acceptance | Ten workflows passed, including upload, failure inspection, playback, filtering, interrupted evidence, inert malicious markup, partial-import acknowledgement, conflict preservation after sharing, source-time imports, and a 10,000-event recording. No page errors or attempted remote requests in these checks. |
| Cross-language format | Independently produced TypeScript fixture, Python fixtures, and converted OTLP example pass the Python reader and JSON Schema. Browser-produced reduced exports also pass the Python reader. |
| Packaging | Wheel and source distribution build successfully. A fresh virtual environment installed the wheel offline with no dependencies; recording, default omission, parsing, packaged assets, demos, and local serving passed smoke checks. |
| Dependency checks | Python requirements check passed. npm production dependency audit reported zero vulnerabilities at the time of verification. |

The tests cover original exception identity, cancellation, concurrent task isolation, explicit thread parentage, failed writes, exclusive creation, partial trailing records, hostile serialization hooks, cyclic/deep inputs, unsafe numbers, secret omission, safe text rendering, source clock distinctions, and preserved uncertainty. A reduced export cannot turn a known conflicting outcome into a claimed success.

The package name `agent-flight-recorder-local` returned no existing PyPI distribution during the check. This is not a reservation. Agent Flight Recorder remains a working title shared by unrelated projects.

## Measured local performance

Reference machine: Apple M4 Pro, Mac16,11, 64 GiB RAM, macOS 26.3.1, arm64. Recording benchmark uses Python 3.14.6. Browser benchmark uses headless Chromium 158.0.8127.18 and Node 26.10.0.

| Measurement | Observed result |
| --- | --- |
| 1,000 empty tool scopes, metadata only | 19.834 microseconds median and 23.125 microseconds p95 per scope, including two synchronous flushed records, IDs, filtering, and context work. |
| Capture size | 2,004 records, 1,285,612 bytes; about 642 bytes per event. |
| Browser import and first rendered view | 345 ms for 10,000 synthetic events totaling 3,946,806 bytes. |
| Search/filter update | 9 ms in that browser acceptance run. |
| Browser reported used JavaScript heap | About 53.5 MB at the end of the acceptance sequence. This is not peak memory or total browser process memory. |

These are single-machine synthetic measurements, not production guarantees. The recording workload does not model slow disks, network filesystems, large sensitive payloads, or model latency. The browser measurement includes test-driver overhead; it is not an isolated parser microbenchmark. No fsync durability or bounded disk latency is claimed.

Reproduce the checks from the repository root:

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
```

The browser script starts and stops its own loopback server and writes temporary reports under `work/browser`. It saves a screenshot of the synthetic failure under `docs/screenshots`.

## Milestone status and remaining validation

M1 through M4 are implemented: independent foundation and schema, native recorder, offline viewer, and portable imports/exports. M5's local package, automated verification, measured limits, documentation, and demonstration are complete. Actual developer usability sessions and the ten-minute onboarding/five-minute diagnosis targets remain unmeasured. Collect that feedback before expanding scope.

Support is verified here for Python on macOS and Linux ARM64, and for the viewer in Chromium. Windows, other browser engines, distributed processes, production workloads, and execution replay are not verified support claims. The tool provides recorded playback only and has no API credentials or execution engine.
