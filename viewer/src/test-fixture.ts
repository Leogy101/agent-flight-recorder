import { LIMITS, type Event } from './model';
export function makeEvents(): Event[] {
  const base = { schema_version: '0.1' as const, recording_id: '00000000-0000-4000-8000-000000000001', trace_id: '1'.repeat(32), recorded_at: '2026-11-12T01:00:00Z' };
  const data: Partial<Event>[] = [
    { type: 'capture.started', data: { recorder_version: '0.1', capture_mode: 'native_lifecycle', privacy_mode: 'selected_content', coverage: 'Synthetic fixture', limits: LIMITS } },
    { type: 'span.started', span_id: '1'.repeat(16), data: { kind: 'run', name: 'Synthetic test run', input: { state: 'captured', value: null } } },
    { type: 'span.started', span_id: '2'.repeat(16), parent_span_id: '1'.repeat(16), data: { kind: 'model', name: 'Synthetic model', input: { state: 'omitted', reason: 'policy' }, attributes: { provider: 'synthetic' } } },
    { type: 'span.started', span_id: '3'.repeat(16), parent_span_id: '1'.repeat(16), data: { kind: 'tool', name: 'Synthetic tool', input: { state: 'captured', value: { amount: '42.00' }, redacted_fields: 1 } } },
    { type: 'span.ended', span_id: '2'.repeat(16), data: { status: 'ok', output: { state: 'captured', value: 'synthetic answer' }, usage: { input_tokens: 20, output_tokens: 5 } } },
    { type: 'span.ended', span_id: '3'.repeat(16), data: { status: 'error', output: { state: 'unavailable', reason: 'not_supplied' }, error: { type: 'ValueError' } } },
    { type: 'span.ended', span_id: '1'.repeat(16), data: { status: 'error', output: { state: 'omitted', reason: 'policy' } } },
    { type: 'capture.ended', data: { written_events: 8, skipped_events: 0, failed_events: 0, limit_reached: false } },
  ];
  return data.map((event, index) => ({ ...base, event_id: `00000000-0000-4000-8000-${String(index + 1).padStart(12,'0')}`, seq: index + 1, elapsed_us: index * 10000, ...event } as Event));
}
export const jsonl = (events: Event[]) => events.map(e => JSON.stringify(e)).join('\n') + '\n';
