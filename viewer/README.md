# Offline viewer

The React/TypeScript viewer reads one bounded JSONL recording in browser memory. The Python CLI serves the compiled files; end users do not need Node.

Development (Node 22.12+; tested with Node 26):

```sh
npm ci
npm test
npm run build
```

The build replaces `../src/agent_flight_recorder/static/` and copies the three synthetic demos from `../fixtures/`. It has no CDN assets, remote fonts, telemetry, persistence, upload endpoint, or execution capability. `npm run dev` starts a development server on loopback; for realistic security-header tests use the Python CLI's production viewer server.

`scripts/produce-fixture.ts` is a standalone TypeScript format producer with no recorder/viewer imports. It emits a synthetic native recording with overlapping operations. With Node's type stripping enabled, run:

```sh
node --experimental-strip-types scripts/produce-fixture.ts /path/to/new-fixture.jsonl
```

Omit the destination to write JSONL to stdout. A destination is created exclusively, never overwritten. This is a conformance fixture producer, not a second supported capture SDK.

Validation independently enforces the contract in `../docs/contract.md`. Invalid UTF-8, duplicate object keys, unsupported versions, mixed recordings, and safety-limit violations are rejected. Malformed records require an explicit partial-view acknowledgement; a genuinely unfinished final JSON prefix is recoverable with a visible notice. The 10,000 physical-line guard also bounds blank-line floods. End times and output differences remain conflicting evidence, including after a reduced export removes source content.

The model tests cover source-time ordering, unknown/incomplete status, parent cycles, parser attacks, limits, UTF-8, identifier types, independent producers, playback, warning preservation and strict reduced exports. UI tests exercise local file selection, partial acknowledgement, malicious text rendering, search, sharing review and playback without additional network calls. The repository's real-browser acceptance checks provide the complementary packaged-server checks.
