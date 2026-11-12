import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { buildView, decodeRecording, eventPosition, LIMITS, parseRecording, reducedExport, timestampNs } from './model';
import { jsonl, makeEvents } from './test-fixture';

describe('bounded recording import', () => {
  it('reads synthetic native capture and keeps concurrency, outcome and privacy separate', () => {
    const recording = parseRecording(jsonl(makeEvents()));
    const view = buildView(recording);
    expect(recording.warnings).toEqual([]);
    expect(view.outcome).toBe('Failed');
    expect(recording.privacy).toBe('selected_content');
    expect(view.spans[1].from).toBeLessThan(view.spans[2].from!);
    expect(view.spans[1].to).toBeGreaterThan(view.spans[2].from!);
    expect(view.inputTokens).toBe(20); expect(view.outputTokens).toBe(5);
    expect(view.spans[0].start.data.input.value).toBeNull();
  });
  it('consumes the independent TypeScript producer and Python-generated fixtures', () => {
    const generated = execFileSync(process.execPath, ['--experimental-strip-types', 'scripts/produce-fixture.ts'], { encoding: 'utf8' });
    const recording = parseRecording(generated);
    expect(recording.warnings).toEqual([]); expect(buildView(recording).spans).toHaveLength(3);
    for (const name of ['failure','interrupted','success']) {
      const fixture = readFileSync(`../fixtures/demo-${name}.jsonl`, 'utf8');
      const parsed = parseRecording(fixture);
      expect(parsed.needsAcknowledgement).toBe(false);
      expect(parsed.events.length).toBeGreaterThan(3);
    }
  });
  it('uses imported source nanoseconds rather than conversion timestamps or sequence', () => {
    const events = makeEvents();
    events[0].data.capture_mode = 'imported_completed_spans';
    for (const e of events) { delete e.elapsed_us; e.recorded_at = '2030-10-10T10:10:10Z'; if (e.type.startsWith('span.')) { e.data.reconstructed = true; e.source_time = `2025-01-01T00:00:00.${String(e.seq).padStart(9,'0')}Z`; } }
    events[2].source_time = '2025-01-01T00:00:00.000000004Z';
    events[3].source_time = '2025-01-01T00:00:00.000000003Z';
    const r = parseRecording(jsonl(events)); const v = buildView(r);
    expect(v.duration).toBeCloseTo(.005);
    expect(r.events[2].span_id).toBe('3'.repeat(16));
    expect(eventPosition(events[4], r)).toBeCloseTo(.003);
  });
  it('keeps absent source time undated and imported unknown status unknown', () => {
    const events = makeEvents(); events[0].data.capture_mode = 'imported_completed_spans';
    events.forEach(e => { delete e.elapsed_us; if (e.type.startsWith('span.')) e.data.reconstructed = true; }); events[6].data.status = 'unknown';
    const r = parseRecording(jsonl(events)); const v = buildView(r);
    expect(v.spans.every(s => s.from === undefined)).toBe(true); expect(v.outcome).toBe('Unknown');
    expect(r.warnings.some(w => w.code === 'missing_source_time')).toBe(true);
  });
  it('flags unfinished spans without inferring failure, including a closed capture', () => {
    const events = makeEvents().filter(e => e.seq !== 6 && e.seq !== 7);
    events.at(-1)!.data.written_events = events.length;
    const r = parseRecording(jsonl(events));
    expect(buildView(r).outcome).toBe('Unfinished');
    for (const code of ['sequence_gap', 'missing_span_end','missing_root_end','capture_closed_with_open_spans']) expect(r.warnings.some(w => w.code === code)).toBe(true);
  });
  it('requires explicit acknowledgement for malformed middle records, but recovers a trailing fragment', () => {
    const source = jsonl(makeEvents());
    const middle = source.split('\n'); middle.splice(3,0,'{"bad":');
    expect(parseRecording(middle.join('\n')).needsAcknowledgement).toBe(true);
    const trailing = parseRecording(source + '{"schema_version":');
    expect(trailing.needsAcknowledgement).toBe(false); expect(trailing.partial).toBe(true);
    expect(trailing.warnings.some(w => w.code === 'partial_trailing_line')).toBe(true);
  });
  it('rejects unknown versions and mixed recordings as a whole', () => {
    const a = makeEvents(); (a[2] as any).schema_version = '99.0'; expect(() => parseRecording(jsonl(a))).toThrow('Unsupported recording version');
    const b = makeEvents(); b[2].recording_id = crypto.randomUUID(); expect(() => parseRecording(jsonl(b))).toThrow('one recording');
  });
  it('deduplicates identical events and gates conflicting identifiers', () => {
    const events = makeEvents(); events.splice(3,0,structuredClone(events[2]));
    const r = parseRecording(jsonl(events)); expect(r.events).toHaveLength(8); expect(r.warnings.some(w => w.code === 'duplicate_event')).toBe(true);
    events[3].data.name = 'Conflicting label'; expect(parseRecording(jsonl(events)).needsAcknowledgement).toBe(true);
  });
  it('does not choose a favorable result when end records conflict', () => {
    const events = makeEvents(); const other = structuredClone(events[5]); other.event_id = crypto.randomUUID(); other.seq = 9; other.data.status = 'ok'; events.push(other);
    const r = parseRecording(jsonl(events)); expect(buildView(r).spans.find(s => s.id === other.span_id)?.status).toBe('conflicting');
  });
  it('treats differing end timestamps as conflicting duration evidence', () => {
    const events = makeEvents(); const other = structuredClone(events[6]); other.event_id = crypto.randomUUID(); other.seq = 9; other.elapsed_us! += 5000; events.push(other);
    const r = parseRecording(jsonl(events)); expect(r.warnings.some(w => w.code === 'conflicting_span_end')).toBe(true); expect(buildView(r).outcome).toBe('Conflicting');
    expect(buildView(parseRecording(reducedExport(r))).outcome).toBe('Conflicting');
  });
  it('handles cyclic parents without recursive traversal', () => {
    const events = makeEvents(); events[1].parent_span_id = events[2].span_id;
    const r = parseRecording(jsonl(events)); expect(r.warnings.some(w => w.code === 'parent_cycle')).toBe(true); expect(buildView(r).spans).toHaveLength(3);
  });
  it('rejects file, line, payload, number, count and depth limits before displaying a partial view', () => {
    expect(() => parseRecording(' '.repeat(LIMITS.max_file_bytes + 1))).toThrow('25 MiB');
    expect(() => parseRecording('x'.repeat(LIMITS.max_event_bytes + 1))).toThrow('64 KiB');
    expect(() => parseRecording(('{}\n').repeat(LIMITS.max_events + 1))).toThrow('10,000');
    const payload = makeEvents(); payload[1].data.input.value = 'x'.repeat(LIMITS.max_payload_bytes + 1); expect(() => parseRecording(jsonl(payload))).toThrow('safety limits');
    const numbers = makeEvents(); numbers[1].data.input.value = 1e100; expect(() => parseRecording(jsonl(numbers))).toThrow('safety limits');
    const deep = makeEvents(); let nested: any = {}; deep[1].data.input.value = nested; for(let i=0;i<25;i++) { nested.child = {}; nested=nested.child; } expect(() => parseRecording(jsonl(deep))).toThrow('safety limits');
  });
  it('keeps hostile keys, scripts and URLs inert and never merges objects', () => {
    const events = makeEvents(); events[1].data.input.value = JSON.parse('{"__proto__":{"polluted":true},"constructor":{"prototype":{"polluted":true}},"html":"<img src=https://evil.invalid onerror=alert(1)>","url":"javascript:alert(1)"}');
    const r = parseRecording(jsonl(events)); expect(({} as any).polluted).toBeUndefined(); expect(buildView(r).spans[0].start.data.input.value.html).toContain('<img');
  });
  it('validates calendar dates and preserves nanosecond precision', () => {
    expect(timestampNs('2026-02-30T00:00:00Z')).toBeUndefined();
    expect(timestampNs('2026-01-01T00:00:00.000000002Z')! - timestampNs('2026-01-01T00:00:00.000000001Z')!).toBe(1n);
  });
  it('rejects duplicate JSON keys, including escaped-equivalent keys', () => {
    const source = jsonl(makeEvents());
    expect(() => parseRecording(source.replace('"status":"error"', '"status":"ok","status":"error"'))).toThrow('duplicate JSON keys');
    expect(() => parseRecording(source.replace('"status":"error"', '"status":"ok","\\u0073tatus":"error"'))).toThrow('duplicate JSON keys');
  });
  it('does not coerce numeric or array identifiers into strings', () => {
    const events = makeEvents(); (events[2] as any).span_id = 1111111111111111;
    expect(parseRecording(jsonl(events)).needsAcknowledgement).toBe(true);
    (events[2] as any).span_id = ['2'.repeat(16)]; expect(parseRecording(jsonl(events)).needsAcknowledgement).toBe(true);
    const second = makeEvents(); (second[2] as any).recording_id = [second[2].recording_id]; expect(parseRecording(jsonl(second)).needsAcknowledgement).toBe(true);
  });
  it('gates malformed final records and recovers only genuine JSON prefixes', () => {
    const source = jsonl(makeEvents());
    for (const tail of ['garbage', '{"x": nope}', '{"x":1,}', '[1,]']) expect(parseRecording(source + tail).needsAcknowledgement).toBe(true);
    for (const tail of ['{"x":', '{"x":"unfinished', '{"x":"\\u12', '{"x":tru', '{"x":1e+']) expect(parseRecording(source + tail).warnings.some(w=>w.code==='partial_trailing_line')).toBe(true);
  });
  it('rejects newline floods before allocating per-line objects and rejects invalid UTF-8', () => {
    expect(() => parseRecording('\n'.repeat(25 * 1024 * 1024))).toThrow('physical-line');
    expect(() => decodeRecording(new Uint8Array([0xc3, 0x28]).buffer)).toThrow('valid UTF-8');
    expect(decodeRecording(new TextEncoder().encode('valid UTF-8 ·').buffer)).toBe('valid UTF-8 ·');
  });
  it('does not double-count model totals through intervening generic spans', () => {
    const events = makeEvents(); events[1].data.kind = 'model'; events[3].data.kind = 'step'; events[2].parent_span_id = events[3].span_id;
    events[6].data.usage = { input_tokens: 100, output_tokens: 50 };
    const v = buildView(parseRecording(jsonl(events))); expect(v.inputTokens).toBe(20); expect(v.outputTokens).toBe(5);
  });
});

describe('recorded playback and reduced sharing', () => {
  it('reveals only evidence available at the playback cursor and does not run tools', () => {
    const r = parseRecording(jsonl(makeEvents()));
    expect(buildView(r,0).spans).toHaveLength(0);
    expect(buildView(r,2).spans).toHaveLength(2);
    expect(buildView(r,2).spans.every(s => s.status === 'incomplete')).toBe(true);
    expect(buildView(r).spans[2].status).toBe('error');
  });
  it('rebuilds shared files from an allowlist, remaps correlation IDs, and preserves source warnings', () => {
    const events = makeEvents().slice(0,-1);
    events[1].data.name = 'SECRET_LABEL'; events[1].data.input.value = 'SECRET_PAYLOAD'; events[1].data.unknown = 'SECRET_UNKNOWN';
    events[2].data.attributes = { provider:'SECRET_PROVIDER' }; events[3].data.links = [{span_id:events[2].span_id,relation:'retry_of'}]; events[5].data.error = {type:'SECRET_EXCEPTION',code:'SECRET_CODE'};
    const r = parseRecording(jsonl(events)); const before = JSON.stringify(r); const exported = reducedExport(r);
    expect(exported).not.toContain('SECRET'); expect(exported).not.toContain(r.events[0].recording_id); expect(exported).not.toContain(r.events[0].trace_id); expect(exported).not.toContain('2026-');
    expect(JSON.stringify(r)).toBe(before);
    const reread = parseRecording(exported); const view = buildView(reread);
    expect(reread.transformed).toBe(true); expect(reread.warnings.some(w => w.code === 'missing_capture_end')).toBe(true);
    expect(view.spans[1].parent).toBe(view.spans[0].id); expect(view.spans[2].start.data.links[0].span_id).toBe(view.spans[1].id);
    expect(view.spans[0].start.data.input.state).toBe('omitted'); expect(view.spans[0].start.data.input).not.toHaveProperty('value');
    expect(view.spans[1].to! - view.spans[1].from!).toBe(buildView(r).spans[1].to! - buildView(r).spans[1].from!);
  });
  it('retains known loss as a source issue even though the derived export closes successfully', () => {
    const events = makeEvents(); events.at(-1)!.data.failed_events = 2;
    const r = parseRecording(reducedExport(parseRecording(jsonl(events)))); expect(r.warnings.some(w => w.code === 'recording_loss')).toBe(true);
  });
  it('preserves conflicting evidence after exclusion and after payload removal', () => {
    const events = makeEvents(); events[6].data.status = 'ok';
    const duplicate = structuredClone(events[6]); duplicate.data.status = 'error'; events.push(duplicate);
    const r = parseRecording(jsonl(events)); expect(r.needsAcknowledgement).toBe(true); expect(buildView(r).outcome).toBe('Conflicting');
    expect(buildView(parseRecording(reducedExport(r))).outcome).toBe('Conflicting');
    const others = makeEvents(); others[6].data.status = 'ok'; others[6].data.output = {state:'captured',value:'A'};
    const end = structuredClone(others[6]); end.event_id = crypto.randomUUID(); end.seq = 9; end.data.output.value = 'B'; others.push(end);
    const another = parseRecording(jsonl(others)); expect(buildView(another).outcome).toBe('Conflicting'); expect(buildView(parseRecording(reducedExport(another))).outcome).toBe('Conflicting');
  });
});
