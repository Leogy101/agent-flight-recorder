/** Independent TypeScript producer: no imports from the Python SDK or viewer. */
import { writeFileSync } from 'node:fs';

const recordingId = 'b1539398-1ae0-4c50-a5ea-e78bffacb950';
const traceId = 'ee5352f1e8954321b458d60ed682b307';
const run = 'e546714022304a1a', first = '4c838f02038a454c', second = 'ae4c037808bd489a';
const omitted = { state: 'omitted', reason: 'policy' };
const records: object[] = [];
function event(type: string, elapsedUs: number, data: object, spanId?: string, parentId?: string) {
  const seq = records.length + 1;
  records.push({ schema_version: '0.1', recording_id: recordingId, trace_id: traceId, event_id: `d4b36710-683d-491a-9fc4-${String(seq).padStart(12, '0')}`, seq, type, recorded_at: new Date(Date.UTC(2026, 0, 1) + elapsedUs / 1000).toISOString(), elapsed_us: elapsedUs, ...(spanId ? { span_id: spanId } : {}), ...(parentId ? { parent_span_id: parentId } : {}), data });
}
event('capture.started', 0, { recorder_version: 'independent-ts-0.1', capture_mode: 'native_lifecycle', privacy_mode: 'metadata_only', coverage: 'Synthetic TypeScript fixture; no external operations executed', source: { name: 'independent-typescript-producer', version: '0.1' }, limits: { max_file_bytes: 26214400, max_events: 10000, max_event_bytes: 65536, max_payload_bytes: 8192, max_depth: 20 } });
event('span.started', 1000, { kind: 'run', name: 'Independent TypeScript recording', input: omitted }, run);
event('span.started', 10000, { kind: 'tool', name: 'Read synthetic catalog', input: omitted }, first, run);
event('span.started', 12000, { kind: 'retrieval', name: 'Read synthetic policy', input: omitted }, second, run);
event('span.ended', 90000, { status: 'ok', output: omitted }, second);
event('span.ended', 120000, { status: 'ok', output: omitted }, first);
event('span.ended', 121000, { status: 'ok', output: omitted }, run);
event('capture.ended', 122000, { written_events: 8, skipped_events: 0, failed_events: 0, limit_reached: false });
const jsonl = records.map(record => JSON.stringify(record)).join('\n') + '\n';
if (process.argv[2]) writeFileSync(process.argv[2], jsonl, { flag: 'wx', mode: 0o600 });
else process.stdout.write(jsonl);
