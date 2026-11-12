/** Bounded, side-effect-free consumer of recording contract 0.1. */
export const LIMITS = { max_file_bytes: 25 * 1024 * 1024, max_events: 10_000, max_event_bytes: 64 * 1024, max_payload_bytes: 8 * 1024, max_depth: 20 } as const;
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Payload = { state: 'captured' | 'omitted' | 'redacted' | 'unavailable'; value?: Json; reason?: string; truncated?: boolean; redacted_fields?: number };
export type EventType = 'capture.started' | 'span.started' | 'span.ended' | 'event.recorded' | 'capture.ended';
export type Event = {
  schema_version: '0.1'; recording_id: string; trace_id: string; event_id: string; seq: number;
  type: EventType; recorded_at: string; elapsed_us?: number; source_time?: string;
  span_id?: string; parent_span_id?: string; data: Record<string, any>;
};
export type Warning = { code: string; message: string; line?: number; count?: number };
export type Recording = { events: Event[]; warnings: Warning[]; partial: boolean; needsAcknowledgement: boolean; mode: 'native_lifecycle' | 'imported_completed_spans'; privacy: string; transformed: boolean; conflictSpanIds: string[] };
export type Span = { id: string; parent?: string; kind: string; name: string; start: Event; end?: Event; status: string; from?: number; to?: number; depth: number; conflicting: boolean };
export type ViewModel = { spans: Span[]; annotations: Event[]; duration: number; timed: boolean; outcome: string; inputTokens?: number; outputTokens?: number };
const encoder = new TextEncoder();
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TRACE = /^(?!0{32}$)[0-9a-f]{32}$/;
const SPAN = /^(?!0{16}$)[0-9a-f]{16}$/;
const uuid = (v: unknown) => typeof v === 'string' && UUID.test(v);
const traceId = (v: unknown) => typeof v === 'string' && TRACE.test(v);
const spanId = (v: unknown) => typeof v === 'string' && SPAN.test(v);
const kinds = new Set(['run', 'agent', 'model', 'tool', 'retrieval', 'step']);
const types = new Set(['capture.started', 'capture.ended', 'span.started', 'span.ended', 'event.recorded']);
const statuses = new Set(['ok', 'error', 'cancelled', 'unknown']);
const attrs = new Set(['provider', 'model', 'tool_name', 'tool_call_id', 'attempt', 'retry_of', 'otel_span_kind']);
export const WARNING_MESSAGES: Record<string, string> = {
  duplicate_event: 'Repeated event IDs were deduplicated.', conflicting_duplicate: 'An event ID has conflicting records; only its first record is displayed.',
  duplicate_sequence: 'More than one event has the same sequence number.', sequence_gap: 'Sequence numbers have gaps; observations may be missing.', sequence_order: 'File sequence numbers are out of order.',
  missing_capture_start: 'The capture start marker is missing; capture policy is uncertain.', missing_capture_end: 'The recording has no final capture marker.',
  duplicate_capture_start: 'The recording has multiple capture start markers.', duplicate_capture_end: 'The recording has multiple final capture markers.',
  capture_position: 'Capture markers are not at the expected boundaries.', capture_count_mismatch: 'The final written-event count does not match this file.',
  duplicate_span_start: 'An operation has multiple start records.', conflicting_span_end: 'An operation has conflicting end records.', duplicate_span_end: 'An operation has repeated end records.',
  missing_span_end: 'An operation has no recorded end. Its outcome is incomplete, not failed.', orphan_span_end: 'An end record has no matching start.',
  missing_parent: 'An operation refers to a parent absent from this recording.', parent_cycle: 'Parent relationships contain a cycle; nesting is not trustworthy.',
  missing_root_span: 'No root operation was recorded.', missing_root_end: 'A root operation has no recorded end.', capture_closed_with_open_spans: 'Capture was finalized while operations remained unfinished.',
  native_clock_anomaly: 'Native monotonic timestamps go backwards.', missing_source_time: 'Imported operations lack source timestamps and are shown as undated.',
  negative_source_duration: 'An imported operation ends before it starts.', source_time_ties: 'Imported source timestamps tie; their relative order is uncertain.',
  partial_trailing_line: 'A truncated final JSON line was excluded.', invalid_line: 'Invalid records were excluded. This is an explicitly accepted partial view.',
  recording_loss: 'The recorder reported skipped or failed events.', capture_limit_reached: 'The recorder reached a configured capture limit.',
  source_issue: 'The source export reported an unrecognized issue; inspect the original recording.', reduced_share: 'This is a reduced, transformed copy. Content, labels, identifiers, and absolute times were changed.',
  privacy_mismatch: 'Captured payload values are present despite a metadata-only policy declaration.',
};
export class RecordingError extends Error { constructor(message: string) { super(message); this.name = 'RecordingError'; } }
const object = (v: any): v is Record<string, any> => v !== null && typeof v === 'object' && !Array.isArray(v);
const int = (v: any, min = 0) => Number.isSafeInteger(v) && v >= min;
const label = (v: any) => typeof v === 'string' && v.length <= 512 && [...v].length <= 256;
const require = (ok: any, message: string) => { if (!ok) throw new RecordingError(message); };
// JSON object member order has no semantic meaning. Compare validated, bounded
// JSON without merging untrusted keys into an object or altering source events.
function canonicalJson(value: any): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}
const endFingerprint = (e: Event) => canonicalJson([e.data, e.elapsed_us ?? null, e.source_time ?? null]);

export function timestampNs(value: unknown): bigint | undefined {
  if (typeof value !== 'string') return undefined;
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z$/.exec(value);
  if (!match) return undefined;
  const millis = Date.parse(`${match[1]}Z`);
  if (!Number.isFinite(millis) || new Date(millis).toISOString().slice(0, 19) !== match[1]) return undefined;
  return BigInt(millis) * 1_000_000n + BigInt((match[2] ?? '').padEnd(9, '0'));
}

function bounded(value: any) {
  const queue: [any, number][] = [[value, 0]];
  while (queue.length) {
    const [v, depth] = queue.pop()!;
    if (Array.isArray(v) || object(v)) require(depth < LIMITS.max_depth, 'JSON nesting exceeds the supported depth.');
    if (typeof v === 'number') require(Number.isFinite(v) && (!Number.isInteger(v) || Number.isSafeInteger(v)), 'A JSON number is outside the supported range.');
    if (typeof v === 'string') require(validUnicode(v), 'A JSON string contains invalid Unicode.');
    if (Array.isArray(v)) for (const item of v) queue.push([item, depth + 1]);
    else if (object(v)) for (const key of Object.keys(v)) { require(validUnicode(key), 'A JSON key contains invalid Unicode.'); queue.push([v[key], depth + 1]); }
  }
}

function validUnicode(value: string): boolean {
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(++i);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
    } else if (code >= 0xdc00 && code <= 0xdfff) return false;
  }
  return true;
}

function payload(value: any) {
  require(object(value) && ['captured', 'omitted', 'redacted', 'unavailable'].includes(value.state), 'A payload descriptor is invalid.');
  require(value.state === 'captured' ? Object.hasOwn(value, 'value') : !Object.hasOwn(value, 'value'), 'A payload value does not match its capture state.');
  if (value.reason !== undefined) require(label(value.reason), 'A payload reason is invalid.');
  if (value.truncated !== undefined) require(typeof value.truncated === 'boolean', 'A truncation marker is invalid.');
  if (value.redacted_fields !== undefined) require(int(value.redacted_fields), 'A redaction count is invalid.');
  if (value.state === 'captured') require(encoder.encode(JSON.stringify(value.value)).length <= LIMITS.max_payload_bytes, 'A captured payload exceeds the supported size.');
}

function validateEvent(value: any): Event {
  bounded(value);
  require(object(value), 'Each record must be a JSON object.');
  require(value.schema_version === '0.1', 'Unsupported recording version. This viewer supports 0.1 only.');
  require(uuid(value.recording_id) && uuid(value.event_id) && traceId(value.trace_id), 'A recording identifier is invalid.');
  require(int(value.seq, 1) && types.has(value.type), 'An event sequence or type is invalid.');
  require(timestampNs(value.recorded_at) !== undefined && object(value.data), 'An event timestamp or data object is invalid.');
  if (value.elapsed_us !== undefined) require(int(value.elapsed_us), 'A monotonic timestamp is invalid.');
  if (value.source_time !== undefined) require(timestampNs(value.source_time) !== undefined, 'A source timestamp is invalid.');
  if (value.span_id !== undefined) require(spanId(value.span_id) && ['span.started','span.ended','event.recorded'].includes(value.type), 'An operation identifier is invalid.');
  if (value.parent_span_id !== undefined) require(spanId(value.parent_span_id) && value.type === 'span.started', 'A parent identifier is invalid.');
  const d = value.data;
  if (value.type === 'capture.started') {
    require(label(d.recorder_version) && label(d.coverage), 'Capture metadata is invalid.');
    require(['native_lifecycle', 'imported_completed_spans'].includes(d.capture_mode) && ['metadata_only', 'selected_content'].includes(d.privacy_mode), 'Capture policy is invalid.');
    require(object(d.limits) && Object.entries(LIMITS).every(([k, max]) => int(d.limits[k], 1) && d.limits[k] <= max), 'Capture limits are invalid.');
    if (d.source !== undefined) require(object(d.source) && label(d.source.name) && label(d.source.version), 'Source metadata is invalid.');
    if (d.transform !== undefined) require(object(d.transform) && d.transform.kind === 'reduced_share' && d.transform.version === '0.1' && Array.isArray(d.transform.source_issues) && d.transform.source_issues.every(label), 'Transformation metadata is invalid.');
  } else if (value.type === 'span.started') {
    require(spanId(value.span_id) && kinds.has(d.kind) && label(d.name), 'Operation start metadata is invalid.'); payload(d.input);
    if (d.attributes !== undefined) {
      require(object(d.attributes), 'Operation attributes are invalid.');
      for (const [key, item] of Object.entries(d.attributes)) require(attrs.has(key) && (key === 'attempt' ? int(item) : key === 'retry_of' ? spanId(item) : label(item)), 'An operation attribute is unsupported.');
    }
    if (d.links !== undefined) require(Array.isArray(d.links) && d.links.length <= 64 && d.links.every((l: any) => object(l) && spanId(l.span_id) && ['retry_of', 'follows_from'].includes(l.relation)), 'Operation links are invalid.');
  } else if (value.type === 'span.ended') {
    require(spanId(value.span_id) && statuses.has(d.status), 'Operation end metadata is invalid.'); payload(d.output);
    if (d.usage !== undefined) require(object(d.usage) && Object.entries(d.usage).every(([k, v]) => ['input_tokens', 'output_tokens'].includes(k) && int(v)), 'Token usage is invalid.');
    if (d.error !== undefined) require(object(d.error) && label(d.error.type) && (d.error.code === undefined || label(d.error.code)), 'Error metadata is invalid.');
  } else if (value.type === 'event.recorded') {
    require(label(d.name), 'Annotation metadata is invalid.'); payload(d.payload);
  } else require(int(d.written_events) && int(d.skipped_events) && int(d.failed_events) && typeof d.limit_reached === 'boolean', 'Capture summary is invalid.');
  if (d.reconstructed !== undefined) require(typeof d.reconstructed === 'boolean', 'Reconstruction metadata is invalid.');
  return value as Event;
}

/** Decode bytes strictly: replacement characters would silently alter recorded evidence. */
export function decodeRecording(bytes: ArrayBuffer): string {
  try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
  catch { throw new RecordingError('This file is not valid UTF-8. No data was imported.'); }
}

function rejectDuplicateKeys(text: string) {
  const stack: (Set<string> | null)[] = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '{') stack.push(new Set());
    else if (text[i] === '[') stack.push(null);
    else if (text[i] === '}' || text[i] === ']') stack.pop();
    else if (text[i] === '"') {
      const begin = i++;
      while (i < text.length) { if (text[i] === '\\') { i += 2; continue; } if (text[i] === '"') break; i++; }
      let after = i + 1; while (/\s/.test(text[after] ?? '') && after < text.length) after++;
      if (text[after] === ':') {
        const key = JSON.parse(text.slice(begin, i + 1)); const keys = stack.at(-1);
        if (keys?.has(key)) throw new RecordingError('A record contains duplicate JSON keys. No data was imported.');
        keys?.add(key);
      }
    }
  }
}

/** Recognize genuine unfinished JSON prefixes without depending on browser error wording. */
function unfinishedJson(text: string): boolean {
  let i = 0;
  const incomplete = Symbol(), invalid = Symbol();
  const space = () => { while (i < text.length && /[\x20\t\r\n]/.test(text[i])) i++; };
  function string() {
    if (text[i++] !== '"') throw invalid;
    while (i < text.length) {
      const c = text[i++]; if (c === '"') return;
      if (c.charCodeAt(0) < 32) throw invalid;
      if (c === '\\') {
        if (i === text.length) throw incomplete;
        const escaped = text[i++];
        if (escaped === 'u') for (let n = 0; n < 4; n++) { if (i === text.length) throw incomplete; if (!/[0-9a-f]/i.test(text[i++])) throw invalid; }
        else if (!'"\\/bfnrt'.includes(escaped)) throw invalid;
      }
    }
    throw incomplete;
  }
  function value(depth: number) {
    if (depth > LIMITS.max_depth) throw invalid;
    space(); if (i === text.length) throw incomplete;
    if (text[i] === '"') return string();
    if (text[i] === '{' || text[i] === '[') {
      const obj = text[i++] === '{'; const close = obj ? '}' : ']'; space();
      if (text[i] === close) { i++; return; }
      while (true) {
        space(); if (i === text.length) throw incomplete;
        if (obj) { string(); space(); if (i === text.length) throw incomplete; if (text[i++] !== ':') throw invalid; }
        value(depth + 1); space(); if (i === text.length) throw incomplete;
        if (text[i] === close) { i++; return; } if (text[i++] !== ',') throw invalid;
      }
    }
    for (const literal of ['true','false','null']) if (text[i] === literal[0]) {
      for (const char of literal) { if (i === text.length) throw incomplete; if (text[i++] !== char) throw invalid; } return;
    }
    const rest = text.slice(i); const numeric = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(rest);
    if (numeric) {
      i += numeric[0].length;
      const tail = text.slice(i);
      if (tail === '.' || /^[eE][+-]?$/.test(tail) || /^\.\d+[eE][+-]?$/.test(tail)) throw incomplete;
      return;
    }
    if (rest === '-') throw incomplete;
    throw invalid;
  }
  try { value(0); space(); return false; } catch (e) { return e === incomplete; }
}

export function parseRecording(text: string): Recording {
  require(encoder.encode(text).length <= LIMITS.max_file_bytes, 'This file exceeds the 25 MiB import limit. No data was imported.');
  let physicalLines = 0;
  for (let n = 0; n < text.length; n++) if (text.charCodeAt(n) === 10 && ++physicalLines > LIMITS.max_events) throw new RecordingError('This file exceeds the 10,000 physical-line import limit. No data was imported.');
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/);
  if (lines.at(-1) === '') lines.pop();
  const records = lines.map((line, index) => ({ line, number: index + 1 }));
  require(records.length <= LIMITS.max_events, 'This file exceeds the 10,000 event import limit. No data was imported.');
  require(records.length > 0, 'This file contains no recording events.');
  const warnings: Warning[] = [];
  const add = (code: string, line?: number) => {
    const existing = warnings.find(w => w.code === code);
    if (existing) existing.count = (existing.count ?? 1) + 1;
    else warnings.push({ code, message: WARNING_MESSAGES[code] ?? WARNING_MESSAGES.source_issue, ...(line ? { line } : {}) });
  };
  const events: Event[] = [];
  const conflictSpanIds = new Set<string>();
  let needsAcknowledgement = false;
  const seen = new Map<string, string>();
  for (let i = 0; i < records.length; i++) {
    const { line, number } = records[i];
    require(encoder.encode(line).length <= LIMITS.max_event_bytes, `Record ${number} exceeds the 64 KiB limit. No data was imported.`);
    let value: any;
    try { value = JSON.parse(line); }
    catch {
      const trailing = !!line.trim() && i === records.length - 1 && !/\r?\n$/.test(text) && unfinishedJson(line);
      add(trailing ? 'partial_trailing_line' : 'invalid_line', number); if (!trailing) needsAcknowledgement = true; continue;
    }
    rejectDuplicateKeys(line);
    if (object(value) && Array.isArray(value.resourceSpans) && value.schema_version === undefined) throw new RecordingError('This is an OTLP export. Convert it with afr import-otlp, then open the resulting JSONL recording.');
    // An unknown version is never silently discarded as a recoverable bad line.
    if (object(value) && value.schema_version !== undefined && value.schema_version !== '0.1') throw new RecordingError('Unsupported recording version. This viewer supports 0.1 only.');
    try { validateEvent(value); }
    catch (error) {
      if (error instanceof RecordingError && /invalid Unicode/.test(error.message)) throw new RecordingError(`Record ${number} contains invalid Unicode. No data was imported.`);
      if (error instanceof RecordingError && /exceeds|nesting|range/.test(error.message)) throw new RecordingError(`Record ${number} exceeds supported safety limits. No data was imported.`);
      add('invalid_line', number); needsAcknowledgement = true; continue;
    }
    const serialized = canonicalJson(value);
    if (seen.has(value.event_id)) {
      const conflict = seen.get(value.event_id) !== serialized; add(conflict ? 'conflicting_duplicate' : 'duplicate_event', number);
      if (conflict) {
        needsAcknowledgement = true;
        const first = JSON.parse(seen.get(value.event_id)!); if (first.span_id) conflictSpanIds.add(first.span_id); if (value.span_id) conflictSpanIds.add(value.span_id);
      }
      continue;
    }
    seen.set(value.event_id, serialized); events.push(value);
  }
  require(events.length > 0, 'No valid recording events remain to display. Open a recorder JSONL file; convert OTLP exports with afr import-otlp first.');
  require(events.every(e => e.trace_id === events[0].trace_id && e.recording_id === events[0].recording_id), 'A file must contain one recording and one trace. No data was imported.');
  const starts = events.filter(e => e.type === 'capture.started');
  const ends = events.filter(e => e.type === 'capture.ended');
  const mode = starts[0]?.data.capture_mode ?? (events.some(e => e.elapsed_us !== undefined) ? 'native_lifecycle' : 'imported_completed_spans');
  if (mode === 'native_lifecycle') require(events.every(e => e.elapsed_us !== undefined), 'Native events require monotonic elapsed_us timestamps.');
  else {
    require(events.every(e => e.elapsed_us === undefined), 'Imported recordings cannot use native monotonic timestamps.');
    require(events.every(e => !e.type.startsWith('span.') || e.data.reconstructed === true), 'Imported span events must be marked as reconstructed.');
  }
  if (!starts.length) add('missing_capture_start'); if (!ends.length) add('missing_capture_end');
  if (starts.length > 1) add('duplicate_capture_start'); if (ends.length > 1) add('duplicate_capture_end');
  if ((starts.length && events[0].type !== 'capture.started') || (ends.length && events.at(-1)?.type !== 'capture.ended')) add('capture_position');
  for (const end of ends) {
    if (end.data.written_events !== events.length) add('capture_count_mismatch');
    if (end.data.skipped_events || end.data.failed_events) add('recording_loss');
    if (end.data.limit_reached) add('capture_limit_reached');
  }
  const seqs = new Set<number>(); let previous = 0; let previousTime = -1;
  for (const e of events) {
    if (seqs.has(e.seq)) add('duplicate_sequence');
    if (e.seq < previous) add('sequence_order');
    seqs.add(e.seq); previous = e.seq;
    if (e.elapsed_us !== undefined) { if (e.elapsed_us < previousTime) add('native_clock_anomaly'); previousTime = e.elapsed_us; }
  }
  const sortedSeq = [...seqs].sort((a, b) => a - b);
  if (sortedSeq.some((s, i) => s !== i + 1)) add('sequence_gap');
  const spanStarts = new Map<string, Event>(); const spanEnds = new Map<string, Event[]>();
  const sourceTimes = new Set<string>();
  for (const e of events) {
    if (e.type === 'span.started') { if (spanStarts.has(e.span_id!)) { add('duplicate_span_start'); conflictSpanIds.add(e.span_id!); } else spanStarts.set(e.span_id!, e); }
    if (e.type === 'span.ended') { const list = spanEnds.get(e.span_id!) ?? []; list.push(e); spanEnds.set(e.span_id!, list); }
    if (mode === 'imported_completed_spans' && e.type.startsWith('span.')) {
      const t = timestampNs(e.source_time);
      if (t === undefined) add('missing_source_time'); else { const key = t.toString(); if (sourceTimes.has(key)) add('source_time_ties'); sourceTimes.add(key); }
    }
  }
  let rootCount = 0; let incomplete = 0;
  for (const [id, start] of spanStarts) {
    const end = spanEnds.get(id)?.[0];
    if (!start.parent_span_id) rootCount++;
    if (!end) { incomplete++; add('missing_span_end'); if (!start.parent_span_id) add('missing_root_end'); }
    if (start.parent_span_id && !spanStarts.has(start.parent_span_id)) add('missing_parent');
    if (end && mode === 'imported_completed_spans') { const a = timestampNs(start.source_time); const b = timestampNs(end.source_time); if (a !== undefined && b !== undefined && b < a) add('negative_source_duration'); }
    if (end && mode === 'native_lifecycle' && end.elapsed_us! < start.elapsed_us!) add('native_clock_anomaly');
  }
  // Iterative graph walk, bounded by the number of operations, avoids recursion on hostile trees.
  const visited = new Set<string>();
  for (const id of spanStarts.keys()) {
    const path = new Set<string>(); let current: string | undefined = id;
    while (current && spanStarts.has(current) && !visited.has(current)) {
      if (path.has(current)) { add('parent_cycle'); break; }
      path.add(current); current = spanStarts.get(current)!.parent_span_id;
    }
    for (const p of path) visited.add(p);
  }
  for (const [id, list] of spanEnds) {
    if (!spanStarts.has(id)) add('orphan_span_end');
    if (list.length > 1) {
      const conflict = !list.every(e => endFingerprint(e) === endFingerprint(list[0])); add(conflict ? 'conflicting_span_end' : 'duplicate_span_end');
      if (conflict) conflictSpanIds.add(id);
    }
  }
  if (!rootCount) add('missing_root_span'); if (incomplete && ends.length) add('capture_closed_with_open_spans');
  const transform = starts[0]?.data.transform;
  if (transform) { add('reduced_share'); for (const code of transform.source_issues) add(Object.hasOwn(WARNING_MESSAGES, code) ? code : 'source_issue'); }
  if (starts[0]?.data.privacy_mode === 'metadata_only' && events.some(e => ['input','output','payload'].some(key => e.data[key]?.state === 'captured'))) add('privacy_mismatch');
  return { events: orderEvents(events, mode), warnings, partial: warnings.some(w => ['partial_trailing_line', 'invalid_line', 'conflicting_duplicate'].includes(w.code)), needsAcknowledgement, mode, privacy: starts[0]?.data.privacy_mode ?? 'unknown', transformed: !!transform, conflictSpanIds: [...conflictSpanIds] };
}

export function orderEvents(events: Event[], mode: Recording['mode']): Event[] {
  if (mode === 'native_lifecycle') return [...events].sort((a, b) => a.seq - b.seq);
  const rank = (e: Event) => e.type === 'span.started' ? 0 : e.type === 'span.ended' ? 1 : 2;
  return [...events].sort((a, b) => {
    if (a.type === 'capture.started') return b.type === 'capture.started' ? a.seq - b.seq : -1;
    if (b.type === 'capture.started') return 1;
    if (a.type === 'capture.ended') return b.type === 'capture.ended' ? a.seq - b.seq : 1;
    if (b.type === 'capture.ended') return -1;
    const at = timestampNs(a.source_time), bt = timestampNs(b.source_time);
    if (at === undefined || bt === undefined) return at === bt ? a.seq - b.seq : at === undefined ? 1 : -1;
    return at < bt ? -1 : at > bt ? 1 : rank(a) - rank(b) || (a.span_id ?? '').localeCompare(b.span_id ?? '') || a.seq - b.seq;
  });
}

export function eventPosition(e: Event, recording: Recording): number | undefined {
  if (recording.mode === 'native_lifecycle') return e.elapsed_us;
  const time = timestampNs(e.source_time); if (time === undefined) return undefined;
  let minimum: bigint | undefined;
  for (const item of recording.events) { const n = timestampNs(item.source_time); if (n !== undefined && (minimum === undefined || n < minimum)) minimum = n; }
  return minimum === undefined ? undefined : Number(time - minimum) / 1000;
}

export function buildView(recording: Recording, cursor = recording.events.length - 1): ViewModel {
  const visible = recording.events.slice(0, cursor + 1);
  const atEnd = cursor >= recording.events.length - 1;
  // Conflicting duplicate event IDs were excluded during import; their exact
  // observation point is not reconstructable. Apply those file-wide findings
  // at the full-recording view, never before the playback cursor reaches them.
  const visibleConflicts = new Set(atEnd ? recording.conflictSpanIds : []);
  const starts = new Map<string, Event>(); const ends = new Map<string, Event[]>();
  let sourceMinimum: bigint | undefined;
  for (const e of recording.events) { const t = timestampNs(e.source_time); if (t !== undefined && (sourceMinimum === undefined || t < sourceMinimum)) sourceMinimum = t; }
  const position = (e: Event) => { const t = timestampNs(e.source_time); return recording.mode === 'native_lifecycle' ? e.elapsed_us : t === undefined || sourceMinimum === undefined ? undefined : Number(t - sourceMinimum) / 1000; };
  let duration = 0; let timed = false;
  for (const e of recording.events) { const p = position(e); if (p !== undefined) { timed = true; duration = Math.max(duration, p); } }
  for (const e of visible) {
    if (e.type === 'span.started') {
      if (starts.has(e.span_id!)) visibleConflicts.add(e.span_id!);
      else starts.set(e.span_id!, e);
    }
    if (e.type === 'span.ended') { const list = ends.get(e.span_id!) ?? []; list.push(e); ends.set(e.span_id!, list); }
  }
  const spans: Span[] = [...starts.entries()].map(([id, start]) => {
    const allEnds = ends.get(id); const end = allEnds?.[0]; const conflicting = visibleConflicts.has(id) || !!allEnds && allEnds.length > 1 && allEnds.some(e => endFingerprint(e) !== endFingerprint(end!));
    return { id, parent: start.parent_span_id, kind: start.data.kind, name: start.data.name, start, end, status: conflicting ? 'conflicting' : end?.data.status ?? 'incomplete', from: position(start), to: end ? position(end) : undefined, depth: 0, conflicting };
  });
  const byId = new Map(spans.map(s => [s.id, s]));
  const children = new Map<string, Span[]>(); const roots: Span[] = [];
  for (const span of spans) { if (span.parent && byId.has(span.parent)) { const list = children.get(span.parent) ?? []; list.push(span); children.set(span.parent, list); } else roots.push(span); }
  const ordered: Span[] = []; const seen = new Set<string>();
  const walk = (first: Span) => { const stack: [Span, number][] = [[first, 0]]; while (stack.length) { const [span, depth] = stack.pop()!; if (seen.has(span.id)) continue; seen.add(span.id); span.depth = Math.min(depth, 12); ordered.push(span); for (const child of [...(children.get(span.id) ?? [])].reverse()) stack.push([child, depth + 1]); } };
  for (const r of roots) walk(r); for (const s of spans) if (!seen.has(s.id)) walk(s);
  const rootSpans = spans.filter(s => !s.parent);
  const hasConflicts = spans.some(s => s.conflicting) || atEnd && recording.warnings.some(w => ['conflicting_duplicate','conflicting_span_end','duplicate_span_start'].includes(w.code));
  const outcome = rootSpans.length === 0 ? 'Unknown' : hasConflicts || rootSpans.some(s => s.status === 'conflicting') ? 'Conflicting' : rootSpans.some(s => s.status === 'error') ? 'Failed' : rootSpans.some(s => s.status === 'incomplete') ? 'Unfinished' : rootSpans.some(s => s.status === 'cancelled') ? 'Cancelled' : rootSpans.every(s => s.status === 'ok') ? 'Succeeded' : 'Unknown';
  const modelBelow = new Set<string>();
  for (const s of [...ordered].reverse()) if (s.parent && (s.kind === 'model' || modelBelow.has(s.id))) modelBelow.add(s.parent);
  const modelSpans = spans.filter(s => s.kind === 'model' && !s.conflicting && !modelBelow.has(s.id));
  const tokenTotal = (key: string) => { const vals = modelSpans.map(s => s.end?.data.usage?.[key]).filter(v => v !== undefined); const sum = vals.reduce((a, b) => a + b, 0); return vals.length && Number.isSafeInteger(sum) ? sum : undefined; };
  return { spans: ordered, annotations: visible.filter(e => e.type === 'event.recorded'), duration, timed, outcome, inputTokens: tokenTotal('input_tokens'), outputTokens: tokenTotal('output_tokens') };
}

export function formatDuration(us: number | undefined): string {
  if (us === undefined || us < 0) return 'Unknown';
  if (us < 1000) return `${Math.round(us)} µs`;
  if (us < 1_000_000) return `${(us / 1000).toFixed(us < 10_000 ? 1 : 0)} ms`;
  return `${(us / 1_000_000).toFixed(2)} s`;
}

/** Sharing is a reconstruction from approved fields, never an object spread of source data. */
export function reducedExport(recording: Recording): string {
  const recordingId = crypto.randomUUID();
  const hexId = (bytes: number) => [...crypto.getRandomValues(new Uint8Array(bytes))].map(n => n.toString(16).padStart(2, '0')).join('');
  const traceId = hexId(16); const ids = new Map<string, string>();
  const remap = (id: string) => { if (!ids.has(id)) ids.set(id, hexId(8)); return ids.get(id)!; };
  const omitted: Payload = { state: 'omitted', reason: 'reduced_share' };
  const origin = timestampNs('2000-01-01T00:00:00Z')!;
  const allRecorded = recording.events.map(e => timestampNs(e.recorded_at)!);
  const recordedBase = allRecorded.reduce((a, b) => a < b ? a : b);
  const sourceTimes = recording.events.flatMap(e => { const t = timestampNs(e.source_time); return t === undefined ? [] : [t]; });
  const sourceBase = sourceTimes.length ? sourceTimes.reduce((a, b) => a < b ? a : b) : origin;
  const iso = (ns: bigint) => { const seconds = ns / 1_000_000_000n; const fraction = ns % 1_000_000_000n; return `${new Date(Number(seconds) * 1000).toISOString().slice(0, 19)}.${fraction.toString().padStart(9, '0')}Z`; };
  const native = recording.mode === 'native_lifecycle';
  const output: Event[] = [];
  const envelope = (type: EventType, recordedAt: string, elapsed?: number): Event => ({ schema_version: '0.1', recording_id: recordingId, trace_id: traceId, event_id: crypto.randomUUID(), seq: output.length + 1, type, recorded_at: recordedAt, ...(native ? { elapsed_us: elapsed ?? 0 } : {}), data: {} });
  const start = envelope('capture.started', iso(origin), 0);
  const issues = [...new Set(recording.warnings.map(w => Object.hasOwn(WARNING_MESSAGES, w.code) ? w.code : 'source_issue'))];
  start.data = { recorder_version: '0.1.0', capture_mode: recording.mode, privacy_mode: 'metadata_only', coverage: native ? 'Explicit instrumented boundaries only' : 'Imported completed spans; earlier capture completeness is unknown', limits: { ...LIMITS }, transform: { kind: 'reduced_share', version: '0.1', source_issues: issues } };
  output.push(start);
  const spanLabels = new Map<string, string>(); let annotationIndex = 0;
  for (const source of recording.events) {
    if (source.type === 'capture.started' || source.type === 'capture.ended') continue;
    const e = envelope(source.type, iso(origin + timestampNs(source.recorded_at)! - recordedBase), source.elapsed_us);
    if (source.span_id) e.span_id = remap(source.span_id);
    if (source.parent_span_id) e.parent_span_id = remap(source.parent_span_id);
    const st = timestampNs(source.source_time); if (st !== undefined) e.source_time = iso(origin + st - sourceBase);
    if (source.type === 'span.started') {
      if (!spanLabels.has(source.span_id!)) spanLabels.set(source.span_id!, `${source.data.kind} ${String(spanLabels.size + 1).padStart(2, '0')}`);
      e.data = { kind: source.data.kind, name: spanLabels.get(source.span_id!), input: omitted };
      if (source.data.links) e.data.links = source.data.links.map((link: any) => ({ span_id: remap(link.span_id), relation: link.relation }));
    } else if (source.type === 'span.ended') {
      e.data = { status: source.data.status, output: omitted };
      if (source.data.usage) { const usage: Record<string, number> = {}; for (const k of ['input_tokens', 'output_tokens']) if (source.data.usage[k] !== undefined) usage[k] = source.data.usage[k]; e.data.usage = usage; }
      if (source.data.error) e.data.error = { type: 'RecordedError' };
    } else e.data = { name: `annotation ${String(++annotationIndex).padStart(2, '0')}`, payload: omitted };
    if (source.data.reconstructed !== undefined) e.data.reconstructed = source.data.reconstructed;
    output.push(e);
  }
  const last = recording.events.at(-1)!;
  const end = envelope('capture.ended', iso(origin + timestampNs(last.recorded_at)! - recordedBase), Math.max(...recording.events.map(e => e.elapsed_us ?? 0)));
  end.data = { written_events: output.length + 1, skipped_events: 0, failed_events: 0, limit_reached: false };
  output.push(end);
  const serialized = output.map(e => JSON.stringify(e)).join('\n') + '\n';
  // Never offer an export that this release cannot safely reopen.
  parseRecording(serialized);
  return serialized;
}
