import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { buildView, decodeRecording, eventPosition, formatDuration, LIMITS, parseRecording, reducedExport, type Event as RecordedEvent, type Payload, type Recording } from './model';
import brandLogo from './assets/agent-flight-recorder.png';

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    flight: <><path d="M3 12h4l3-7 4 14 3-7h4"/><path d="M4 5v2M20 17v2"/></>,
    file: <><path d="M14 3H5v18h14V8z"/><path d="M14 3v6h5M8 13h8M8 17h5"/></>,
    upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/></>,
    down: <><path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    next: <><path d="m7 5 8 7-8 7M18 5v14"/></>,
    prev: <><path d="m17 5-8 7 8 7M6 5v14"/></>,
    reset: <><path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/></>,
    play: <path d="m8 4 12 8-12 8z"/>,
    pause: <><path d="M8 4v16M16 4v16"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    alert: <><path d="M12 3 2 21h20zM12 9v5M12 17v1"/></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/></>,
    branch: <><circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M6 7v10M18 7v3c0 4-12 1-12 5"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.file}</svg>;
}

function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    ref.current?.focus();
    return () => before?.focus();
  }, []);
  return <div className="modal-shade" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div ref={ref} className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} onKeyDown={e => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab') {
        const focusable = [...(ref.current?.querySelectorAll<HTMLElement>('button, input, select, [tabindex="0"]') ?? [])];
        const first = focusable[0], last = focusable.at(-1);
        if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && (document.activeElement === last || document.activeElement === ref.current)) { e.preventDefault(); first?.focus(); }
      }
    }}>
      <div className="modal-head"><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><Icon name="close"/></button></div>
      {children}
    </div>
  </div>;
}

function PayloadCard({ label, payload }: { label: string; payload?: Payload }) {
  const state = payload?.state ?? 'unavailable';
  return <section className="payload-card">
    <div className="section-heading"><h3>{label}</h3><span className={`payload-state ${state}`}>{state}</span></div>
    {state === 'captured' ? <pre>{JSON.stringify(payload?.value, null, 2)}</pre> : <p>{state === 'omitted' ? 'Content was not retained under the capture policy.' : state === 'redacted' ? 'Content was removed before persistence.' : 'No value is available in this recording.'}</p>}
    {payload?.truncated && <div className="small-warning">Content was truncated; this is not the full value.</div>}
    {!!payload?.redacted_fields && <div className="muted small">{payload.redacted_fields} field(s) redacted</div>}
    {payload?.reason && <div className="reason">Reason: <code>{payload.reason}</code></div>}
  </section>;
}

const statusLabel = (status: string) => ({ ok: 'OK', error: 'Failed', incomplete: 'Unfinished', cancelled: 'Cancelled', unknown: 'Unknown', conflicting: 'Conflicting' })[status] ?? status;
const kindSymbol: Record<string, string> = { run: 'R', agent: 'A', model: 'M', tool: 'T', retrieval: 'Q', step: 'S' };
const isProblem = (status: string) => ['error', 'incomplete', 'conflicting', 'cancelled'].includes(status);

/** A large recording can contain thousands of annotations; render one page only. */
function Annotations({ events, inspect }: { events: RecordedEvent[]; inspect: (event: RecordedEvent) => void }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const pageSize = 40;
  const lastPage = Math.max(0, Math.ceil(events.length / pageSize) - 1);
  const currentPage = Math.min(page, lastPage);
  return <details className="annotations" open={open} onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>{events.length} recorded annotation{events.length === 1 ? '' : 's'}</summary>
    {open && <>
      {events.slice(currentPage * pageSize, (currentPage + 1) * pageSize).map(e => <div key={e.event_id}><span className="mono">#{e.seq}</span><strong>{e.data.name}</strong><span className="payload-state">{e.data.payload.state}</span><button className="text-button small" onClick={() => inspect(e)} aria-label={`Inspect annotation ${e.data.name}`}>Inspect event</button>{e.data.payload.state === 'captured' && <pre>{JSON.stringify(e.data.payload.value, null, 2)}</pre>}</div>)}
      {events.length > pageSize && <div className="annotation-pagination"><span>{currentPage * pageSize + 1}–{Math.min((currentPage + 1) * pageSize, events.length)} of {events.length} annotations</span><button className="button secondary small" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous annotations</button><button className="button secondary small" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Next annotations</button></div>}
    </>}
  </details>;
}

export default function App() {
  const [recording, setRecording] = useState<Recording | null>(null);
  const [fileName, setFileName] = useState('');
  const [bundledDemo, setBundledDemo] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [selected, setSelected] = useState<string>();
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const [status, setStatus] = useState('all');
  const [page, setPage] = useState(0);
  const [tab, setTab] = useState<'details' | 'events'>('details');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [pending, setPending] = useState<{ recording: Recording; name: string; demo: boolean }>();
  const [share, setShare] = useState(false);
  const [showWarnings, setShowWarnings] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [eventDetails, setEventDetails] = useState(false);
  const loadRequest = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const playback = useRef<HTMLInputElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const view = useMemo(() => recording ? buildView(recording, cursor) : null, [recording, cursor]);
  const fullView = useMemo(() => recording ? buildView(recording) : null, [recording]);
  const selectedSpan = view?.spans.find(s => s.id === selected);
  const searchIndex = useMemo(() => new Map(fullView?.spans.map(span => [span.id, {
    start: `${span.name} ${span.kind} ${JSON.stringify(span.start.data)}`.toLowerCase(),
    end: JSON.stringify(span.end?.data ?? {}).toLowerCase(),
  }]) ?? []), [fullView]);
  const filtered = useMemo(() => {
    const search = query.toLowerCase();
    return view?.spans.filter(span => {
    if (kind !== 'all' && span.kind !== kind) return false;
    if (status !== 'all' && span.status !== status) return false;
    if (!query) return true;
    const text = searchIndex.get(span.id);
    return `${text?.start ?? ''} ${span.status} ${span.end ? text?.end ?? '' : ''}`.includes(search);
    }) ?? [];
  }, [view, kind, status, query, searchIndex]);
  const pageSize = 80;
  const visibleSpans = filtered.slice(page * pageSize, (page + 1) * pageSize);
  const currentEvent = recording?.events[cursor];
  const currentPosition = useMemo(() => currentEvent && recording ? eventPosition(currentEvent, recording) : undefined, [currentEvent, recording]);
  const atEnd = !recording || cursor >= recording.events.length - 1;
  const inputTokens = view?.inputTokens; const outputTokens = view?.outputTokens;
  const isImported = recording?.mode === 'imported_completed_spans';
  const anyWarnings = !!recording?.warnings.length;
  const currentOperation = fullView?.spans.find(s => s.id === currentEvent?.span_id);

  function closeRecording() {
    loadRequest.current++;
    setRecording(null); setPlaying(false); setBusy(false); setError(''); setPending(undefined); setShare(false); setEventDetails(false);
  }

  function accept(next: Recording, name: string, demo = false) {
    const model = buildView(next);
    const selected = model.spans.find(s => s.status === 'error' && s.kind === 'tool') ?? model.spans.find(s => s.status === 'error' && s.parent) ?? model.spans.find(s => isProblem(s.status) && s.parent) ?? model.spans.find(s => isProblem(s.status)) ?? model.spans[0];
    setRecording(next); setFileName(name); setBundledDemo(demo); setCursor(next.events.length - 1); setSelected(selected?.id);
    setQuery(''); setKind('all'); setStatus('all'); setPage(selected ? Math.floor(model.spans.indexOf(selected) / pageSize) : 0); setPlaying(false); setError(''); setPending(undefined); setShowWarnings(false); setTab('details'); setEventDetails(false);
  }
  function parse(text: string, name: string, demo = false) {
    const next = parseRecording(text);
    if (next.needsAcknowledgement) setPending({ recording: next, name, demo }); else accept(next, name, demo);
  }
  async function openFile(file?: File) {
    if (!file) return;
    const request = ++loadRequest.current;
    setError(''); setBusy(true); setPlaying(false); setPending(undefined);
    try {
      if (file.size > LIMITS.max_file_bytes) throw new Error('This file exceeds the 25 MiB import limit. No data was imported.');
      const bytes = await file.arrayBuffer();
      if (request === loadRequest.current) parse(decodeRecording(bytes), file.name);
    } catch (e) { if (request === loadRequest.current) setError(e instanceof Error ? e.message : 'This recording could not be opened.'); }
    finally { if (request === loadRequest.current) { setBusy(false); if (fileInput.current) fileInput.current.value = ''; } }
  }
  async function loadDemo(name: 'failure' | 'interrupted' | 'success') {
    const request = ++loadRequest.current;
    setBusy(true); setError(''); setPlaying(false); setPending(undefined);
    try {
      // Only packaged, named synthetic fixtures are fetched. Imported files never leave memory.
      const response = await fetch(`./demo-${name}.jsonl`);
      if (!response.ok) throw new Error('The bundled example is unavailable. Open a recording from your computer.');
      const bytes = await response.arrayBuffer();
      if (request === loadRequest.current) parse(decodeRecording(bytes), `demo-${name}.jsonl`, true);
    } catch (e) { if (request === loadRequest.current) setError(e instanceof Error ? e.message : 'The bundled example could not be opened.'); }
    finally { if (request === loadRequest.current) setBusy(false); }
  }
  function step(delta: number) { setPlaying(false); setCursor(n => Math.min(Math.max(n + delta, 0), (recording?.events.length ?? 1) - 1)); }
  function jumpProblem() {
    if (!recording || !fullView) return;
    const problems = fullView.spans.filter(s => isProblem(s.status));
    const index = problems.findIndex(s => s.id === selected);
    const target = problems[(index + 1) % problems.length];
    if (!target) return;
    setPlaying(false); setCursor(recording.events.length - 1); setSelected(target.id); setQuery(''); setKind('all'); setStatus('all'); setPage(Math.floor(fullView.spans.indexOf(target) / pageSize));
  }
  function inspectEvent(event: RecordedEvent) {
    if (!recording) return;
    setPlaying(false); setCursor(recording.events.indexOf(event)); setEventDetails(true);
    if (event.span_id) setSelected(event.span_id);
  }
  function download() {
    if (!recording) return;
    try {
      const data = reducedExport(recording);
      const url = URL.createObjectURL(new Blob([data], { type: 'application/x-ndjson' }));
      const a = document.createElement('a'); a.href = url; a.download = 'recording-reduced.jsonl'; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000); setShare(false);
    } catch { setError('A reduced copy could not be created within the supported format and limits. Your original recording is unchanged.'); setShare(false); }
  }
  useEffect(() => { if (recording) mainRef.current?.focus(); }, [recording]);
  useEffect(() => { timelineRef.current?.querySelector<HTMLElement>(`[data-span-id="${selected}"]`)?.scrollIntoView?.({ block: 'nearest' }); }, [selected, page]);
  useEffect(() => () => { loadRequest.current++; }, []);
  useEffect(() => { if (page * pageSize >= filtered.length && page > 0) setPage(0); }, [filtered.length, page]);
  useEffect(() => {
    if (!playing || !recording) return;
    if (atEnd) { setPlaying(false); return; }
    const timer = setTimeout(() => setCursor(c => c + 1), 550);
    return () => clearTimeout(timer);
  }, [playing, cursor, recording, atEnd]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!recording || pending || share || e.altKey || e.ctrlKey || e.metaKey || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes((e.target as HTMLElement)?.tagName)) return;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); setPlaying(false); setCursor(c => Math.max(0, Math.min(c + (e.key === 'ArrowRight' ? 1 : -1), recording.events.length - 1))); }
    };
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey);
  }, [recording, pending, share]);

  return <div className={`app ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }} onDrop={e => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files.length !== 1) setError('Choose one recording at a time.'); else void openFile(e.dataTransfer.files[0]); }}>
    <a className="skip-link" href="#workspace">Skip to recording</a>
    <header className="topbar">
      <a className="brand" href="#" onClick={e => { e.preventDefault(); closeRecording(); }} aria-label="Agent Flight Recorder home"><span className="brand-mark"><Icon name="flight" size={25}/></span><span>Agent Flight Recorder<span className="brand-caption">LOCAL INCIDENT WORKSPACE</span></span></a>
      <div className="topbar-actions"><span className="local-badge"><span/> Local only</span><span className="version">v0.1</span><button className="button secondary" onClick={() => fileInput.current?.click()} disabled={busy}><Icon name="upload"/> Open recording</button></div>
      <input ref={fileInput} type="file" accept=".jsonl,.ndjson,.json" aria-label="Choose recording file" className="visually-hidden" onChange={e => void openFile(e.target.files?.[0])}/>
    </header>

    {error && <div className="error-banner" role="alert"><Icon name="alert"/><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><Icon name="close"/></button></div>}
    {busy && <div className="loading" role="status">Reading recording locally…</div>}

    <main id="workspace" ref={mainRef} tabIndex={-1}>
      {!recording || !view ? <div className="welcome">
        <div className="welcome-copy"><div className="eyebrow"><span/> OBSERVE. INSPECT. UNDERSTAND.</div><h1>Every run leaves<br/>a story.</h1><p className="welcome-lead">Follow the evidence from an agent run.<br/>Find the failed call, the unfinished step,<br/>and the details the recording cannot tell you.</p><div className="welcome-buttons"><button className="button primary large" onClick={() => fileInput.current?.click()}><Icon name="upload"/> Open a recording</button><button className="text-button" onClick={() => void loadDemo('failure')}>Explore an example <Icon name="arrow"/></button></div><p className="welcome-note"><Icon name="lock" size={15}/> Your file stays in this browser. No upload or account.</p></div>
        <div className="welcome-logo-panel"><img className="welcome-logo" src={brandLogo} alt="Agent Flight Recorder — an aircraft above a flight recorder" width="1254" height="1254"/><div className="logo-caption"><span/> Local capture. Portable evidence.</div></div>
        <div className="example-grid"><button onClick={() => void loadDemo('failure')}><span className="example-number">01</span><div><h2>A failed attempt</h2><p>Inspect a tool failure and an explicit retry.</p></div><Icon name="arrow"/></button><button onClick={() => void loadDemo('interrupted')}><span className="example-number">02</span><div><h2>An interrupted run</h2><p>See parallel work and missing evidence.</p></div><Icon name="arrow"/></button><button onClick={() => void loadDemo('success')}><span className="example-number">03</span><div><h2>A complete recording</h2><p>Follow a successful synthetic run.</p></div><Icon name="arrow"/></button></div>
        <div className="welcome-footer"><span>JSONL · Up to 25 MiB · 10,000 events</span><span>Recorded playback. No model calls. No tool execution.</span></div>
      </div> : <div className="workspace">
        <div className="recording-heading"><div><div className="eyebrow">RECORDING / {recording.transformed ? 'REDUCED COPY' : bundledDemo ? 'SYNTHETIC EXAMPLE' : 'LOCAL FILE'}</div><h1>{fullView?.spans.find(s => !s.parent)?.name ?? 'Untitled recording'}</h1><div className="file-meta"><Icon name="file" size={14}/><span>{fileName}</span><span className="divider">/</span><span>{recording.events.length.toLocaleString()} stored events</span></div></div><div className="recording-actions"><button className="button secondary" onClick={() => { setShare(true); setPlaying(false); }}><Icon name="down"/> Share a reduced copy</button><button className="text-button small" onClick={closeRecording}>Close recording</button></div></div>

        <div className="summary-grid">
          <div className="summary-cell"><div className="summary-label">AGENT OUTCOME</div><div className={`summary-value outcome-${view.outcome.toLowerCase()}`}><span className={`status-dot ${view.outcome === 'Failed' ? 'error' : view.outcome === 'Succeeded' ? 'ok' : 'incomplete'}`}/>{view.outcome}</div><div className="summary-note">{!atEnd ? 'At this playback position' : view.outcome === 'Succeeded' && view.spans.some(s => s.status === 'error') ? 'Root succeeded · earlier errors recorded' : 'From recorded root status'}</div></div>
          <div className="summary-cell"><div className="summary-label">RECORDED INTERVAL</div><div className="summary-value mono">{view.timed ? formatDuration(view.duration) : 'Undated'}</div><div className="summary-note">{isImported ? 'Source timestamps' : 'Monotonic capture clock'}</div></div>
          <div className="summary-cell"><div className="summary-label">KNOWN MODEL TOKENS</div><div className="summary-value mono">{inputTokens === undefined && outputTokens === undefined ? 'Unknown' : <>{inputTokens?.toLocaleString() ?? '—'}<span className="token-slash">/</span>{outputTokens?.toLocaleString() ?? '—'}</>}</div><div className="summary-note">Input / output · reported totals only</div></div>
          <div className="summary-cell"><div className="summary-label">PAYLOAD PRIVACY</div><div className="summary-value privacy-value"><Icon name="lock" size={17}/>{recording.privacy === 'metadata_only' && recording.events.some(e => ['input','output','payload'].some(k => e.data[k]?.state === 'captured')) ? 'Content present' : recording.privacy === 'metadata_only' ? 'Metadata only' : recording.privacy === 'selected_content' ? 'Selected content' : 'Unknown policy'}</div><div className="summary-note">{recording.transformed ? 'Labels and identifiers transformed' : 'Labels can still contain sensitive data'}</div></div>
        </div>

        <section className={`evidence-strip ${anyWarnings ? 'has-warning' : ''}`} aria-label="Recording evidence quality"><Icon name={anyWarnings ? 'alert' : 'check'} size={17}/><div><strong>{anyWarnings ? `${recording.warnings.length} recording notice${recording.warnings.length === 1 ? '' : 's'}` : 'No structural gaps detected'}</strong><span>{isImported ? 'Imported completed spans. Conversion closure does not establish historical capture completeness.' : 'Native lifecycle capture. Only explicitly instrumented boundaries are observable.'}</span></div>{anyWarnings && <button className="text-button small" aria-expanded={showWarnings} onClick={() => setShowWarnings(v => !v)}>{showWarnings ? 'Hide details' : 'Review notices'} <span aria-hidden="true">{showWarnings ? '−' : '+'}</span></button>}</section>
        {showWarnings && <section className="warning-list" aria-label="Recording notices">{recording.warnings.map(w => <div key={w.code}><span className="warning-code">{w.code}</span><p>{w.message}{w.line ? ` First affected line: ${w.line}.` : ''}{w.count && w.count > 1 ? ` (${w.count} occurrences)` : ''}</p></div>)}</section>}

        <div className="investigation-toolbar"><div className="toolbar-heading"><Icon name="branch"/><h2>Operation timeline</h2><span className="count-pill">{view.spans.length}</span></div><div className="filters"><label className="search-field"><Icon name="search" size={16}/><input aria-label="Search recorded operations" placeholder="Search recorded evidence…" value={query} onChange={e => { setQuery(e.target.value); setPage(0); }}/>{query && <button aria-label="Clear search" className="icon-button" onClick={() => { setQuery(''); setPage(0); }}><Icon name="close" size={13}/></button>}</label><select aria-label="Filter by kind" value={kind} onChange={e => { setKind(e.target.value); setPage(0); }}><option value="all">All kinds</option>{['run','agent','model','tool','retrieval','step'].map(k => <option key={k} value={k}>{k}</option>)}</select><select aria-label="Filter by status" value={status} onChange={e => { setStatus(e.target.value); setPage(0); }}><option value="all">All statuses</option>{['ok','error','incomplete','cancelled','unknown','conflicting'].map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}</select><button className="button subtle small" onClick={jumpProblem} disabled={!fullView?.spans.some(s => isProblem(s.status))}><Icon name="alert" size={15}/> Jump to issue</button></div></div>

        <div className="debugger-layout">
          <section className="timeline-panel" aria-label="Recorded operations">
            <div className="timeline-column-head"><span>OPERATION / STATUS</span><div className="time-ruler">{[0,.25,.5,.75,1].map(f => <span key={f}>{formatDuration(view.duration * f)}</span>)}</div></div>
            <div className="timeline-rows" ref={timelineRef}>
              {visibleSpans.map(span => {
                const duration = Math.max(view.duration, 1); const from = span.from ?? 0;
                const hasDuration = span.from !== undefined && span.to !== undefined && span.to >= span.from;
                const width = hasDuration ? Math.max((span.to! - from) / duration * 100, .5) : 0;
                const pendingEnd = Math.max(currentPosition ?? from, from);
                return <button key={span.id} data-span-id={span.id} className={`operation-row ${selected === span.id ? 'selected' : ''}`} aria-label={`${span.name} ${statusLabel(span.status)} ${span.kind}${span.start.data.attributes?.attempt !== undefined ? ` attempt ${span.start.data.attributes.attempt}` : ''}${span.start.data.attributes?.retry_of || span.start.data.links?.some((l: any) => l.relation === 'retry_of') ? ' Retry' : ''}`} aria-pressed={selected === span.id} onClick={() => setSelected(span.id)}>
                  <span className="operation-label" style={{ paddingLeft: `${16 + Math.min(span.depth, 5) * 12}px` }}><span className={`kind-icon kind-${span.kind}`}>{kindSymbol[span.kind]}</span><span className="operation-name"><span title={span.name}>{span.name}</span><span className="operation-subline"><span className={`status-dot ${span.status}`}/>{statusLabel(span.status)}{span.depth > 5 && <span className="attempt">Depth {span.depth}+</span>}{span.start.data.attributes?.attempt !== undefined && <span className="attempt">Attempt {span.start.data.attributes.attempt}</span>}{(span.start.data.attributes?.retry_of || span.start.data.links?.some((l: any) => l.relation === 'retry_of')) && <span className="attempt">Retry</span>}</span></span></span>
                  <span className="timeline-track"><span className="grid-lines"/>{span.from === undefined ? <span className="undated">Undated source</span> : <><span className={`duration-bar kind-${span.kind} status-${span.status} ${!hasDuration ? 'open-bar' : ''}`} style={{ left: `${Math.min(from / duration * 100, 99.5)}%`, width: `${hasDuration ? width : Math.max((pendingEnd - from) / duration * 100, 1)}%` }}/><span className="bar-duration">{hasDuration ? formatDuration(span.to! - from) : span.end ? 'Unknown interval' : 'No recorded end'}</span></>}</span>
                </button>;
              })}
              {!visibleSpans.length && <div className="timeline-empty"><Icon name="clock" size={28}/><h3>{view.spans.length ? 'No operations match' : 'No operation starts at this point'}</h3><p>{view.spans.length ? 'Try a different search or filter.' : atEnd ? 'Inspect the stored events below; start records may be missing.' : 'Step forward through the stored events to reveal the run.'}</p>{view.spans.length > 0 && <button className="button secondary small" onClick={() => { setQuery(''); setKind('all'); setStatus('all'); setPage(0); }}>Clear filters</button>}</div>}
            </div>
            <div className="timeline-bottom"><span>{filtered.length > pageSize ? `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, filtered.length)} of ${filtered.length} operations` : `${filtered.length} operation${filtered.length === 1 ? '' : 's'} shown`}<span className="muted"> · Overlapping bars show concurrent observations</span></span>{filtered.length > pageSize && <div className="pagination"><button disabled={!page} onClick={() => setPage(p => p - 1)} aria-label="Previous operation page">←</button><button disabled={(page + 1) * pageSize >= filtered.length} onClick={() => setPage(p => p + 1)} aria-label="Next operation page">→</button></div>}</div>
            {!!view.annotations.length && <Annotations key={recording.events[0].recording_id} events={view.annotations} inspect={inspectEvent}/>}
          </section>

          <aside className="inspector" aria-label="Operation inspector"><div className="inspector-top"><div><span className="eyebrow">INSPECTOR</span><h2>{selectedSpan?.name ?? 'Select an operation'}</h2></div>{selectedSpan && <span className={`status-tag ${selectedSpan.status}`}>{statusLabel(selectedSpan.status)}</span>}</div><div className="inspector-tabs" role="tablist" aria-label="Inspector view" onKeyDown={e => {
            if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
            e.preventDefault(); const next = e.key === 'Home' ? 'details' : e.key === 'End' ? 'events' : tab === 'details' ? 'events' : 'details';
            setTab(next); e.currentTarget.querySelector<HTMLButtonElement>(`#inspector-tab-${next}`)?.focus();
          }}><button id="inspector-tab-details" role="tab" tabIndex={tab === 'details' ? 0 : -1} aria-controls="inspector-panel" aria-selected={tab === 'details'} onClick={() => setTab('details')}>Details</button><button id="inspector-tab-events" role="tab" tabIndex={tab === 'events' ? 0 : -1} aria-controls="inspector-panel" aria-selected={tab === 'events'} onClick={() => setTab('events')}>Raw events</button></div><div id="inspector-panel" className="inspector-body" role="tabpanel" aria-labelledby={`inspector-tab-${tab}`} tabIndex={0}>
            {!selectedSpan ? <div className="inspector-placeholder"><Icon name="file" size={30}/><p>{selected ? 'This operation has not started at the current playback position.' : 'Select a timeline row to inspect its recorded evidence.'}</p></div> : tab === 'events' ? <><p className="inspector-note">Parsed source events, shown as text. Unknown fields are inert.</p><h3 className="raw-label">START EVENT</h3><pre className="raw-event">{JSON.stringify(selectedSpan.start, null, 2)}</pre>{selectedSpan.end ? <><h3 className="raw-label">END EVENT</h3><pre className="raw-event">{JSON.stringify(selectedSpan.end, null, 2)}</pre></> : <div className="small-warning">No end event is available at this position.</div>}</> : <>
              <div className="detail-grid"><div><span>KIND</span><strong>{selectedSpan.kind}</strong></div><div><span>DURATION</span><strong className="mono">{selectedSpan.from !== undefined && selectedSpan.to !== undefined ? formatDuration(selectedSpan.to - selectedSpan.from) : 'Unknown'}</strong></div><div className="full"><span>OPERATION ID</span><code>{selectedSpan.id}</code></div>{selectedSpan.parent && <div className="full"><span>PARENT</span><code>{selectedSpan.parent}</code></div>}</div>
              <div className="operation-navigation"><button className="button secondary small" onClick={() => inspectEvent(selectedSpan.start)}>Go to start</button><button className="button secondary small" disabled={!fullView?.spans.find(s => s.id === selectedSpan.id)?.end} onClick={() => { const end = fullView?.spans.find(s => s.id === selectedSpan.id)?.end; if (end) inspectEvent(end); }}>Go to end</button></div>
              {selectedSpan.start.data.reconstructed && <div className="small-warning">Reconstructed from a completed span export. This start was not recorded live by this recorder.</div>}
              {selectedSpan.status === 'incomplete' && <div className="small-warning">No end is visible here. This does not establish that the operation failed.</div>}
              {selectedSpan.conflicting && <div className="small-warning">This operation has conflicting evidence. The first retained records below are not a resolved outcome.</div>}
              {selectedSpan.end?.data.error && <section className="error-detail"><span className="eyebrow">RECORDED ERROR</span><strong>{selectedSpan.end.data.error.type}</strong>{selectedSpan.end.data.error.code && <code>{selectedSpan.end.data.error.code}</code>}<p>Reported category. No inferred root cause.</p></section>}
              <PayloadCard label="Input" payload={selectedSpan.start.data.input}/><PayloadCard label="Output" payload={selectedSpan.end?.data.output}/>
              {selectedSpan.start.data.attributes && Object.keys(selectedSpan.start.data.attributes).length > 0 && <section className="attributes"><h3>Recorded attributes</h3><dl>{Object.entries(selectedSpan.start.data.attributes).map(([k,v]) => <div key={k}><dt>{k}</dt><dd>{String(v)}</dd></div>)}</dl></section>}
              {selectedSpan.start.data.links?.length > 0 && <section className="attributes"><h3>Explicit relationships</h3><dl>{selectedSpan.start.data.links.map((l: any, i: number) => <div key={i}><dt>{l.relation}</dt><dd><code>{l.span_id}</code></dd></div>)}</dl></section>}
            </>}
          </div></aside>
        </div>

        <section className="playback" aria-label="Recorded playback"><div className="playback-label"><Icon name="flight" size={18}/><div><strong>Recorded playback</strong><span>No execution. Stored evidence only.</span></div></div><div className="playback-controls"><button className="icon-button" onClick={() => { setCursor(0); setPlaying(false); }} aria-label="Reset playback" title="Reset to the first event"><Icon name="reset" size={17}/></button><button className="icon-button" disabled={cursor === 0} onClick={() => step(-1)} aria-label="Previous event"><Icon name="prev" size={18}/></button><button className="play-button" onClick={() => { if (atEnd) setCursor(0); setPlaying(p => !p); }} aria-label={playing ? 'Pause playback' : 'Play recorded events'}><Icon name={playing ? 'pause' : 'play'} size={17}/></button><button className="icon-button" disabled={atEnd} onClick={() => step(1)} aria-label="Next event"><Icon name="next" size={18}/></button></div><div className="playback-scrub"><input ref={playback} type="range" min="0" max={recording.events.length - 1} value={cursor} aria-label="Playback event position" aria-valuetext={`Event ${cursor + 1} of ${recording.events.length}: ${currentEvent?.type}`} onChange={e => { setPlaying(false); setCursor(Number(e.target.value)); }}/><div><span>{currentEvent?.type}</span><span>EVENT {cursor + 1} / {recording.events.length}</span></div></div><button className="text-button small" disabled={atEnd} onClick={() => { setCursor(recording.events.length - 1); setPlaying(false); }}>Show all <Icon name="arrow" size={15}/></button></section>
        {currentEvent && <details className="current-event" open={eventDetails} onToggle={e => setEventDetails(e.currentTarget.open)}>
          <summary><span>Inspect stored event</span><code>#{currentEvent.seq} · {currentEvent.type}</code><span className="current-event-name">{currentOperation?.name ?? (currentEvent.type === 'event.recorded' ? currentEvent.data.name : currentEvent.span_id ? 'Operation record' : 'Capture metadata')}</span></summary>
          {eventDetails && <div className="current-event-body"><p>Source record at this playback position. Text only; nothing is executed.{currentEvent.span_id && !currentOperation ? ' This operation has no recorded start.' : ''}</p><pre aria-label="Current stored event">{JSON.stringify(currentEvent, null, 2)}</pre></div>}
        </details>}
        <footer className="workspace-footer"><span>{isImported ? 'Playback follows reconstructed source-time order; ties are uncertain.' : 'Playback follows observation sequence; timing does not prove causality.'}</span><span>Local browser memory · No upload · No execution</span></footer>
      </div>}
    </main>
    {dragging && <div className="drop-overlay"><Icon name="upload" size={42}/><h2>Drop one recording</h2><p>Read locally, in this browser.</p></div>}
    {pending && <Modal title="Review an incomplete import" onClose={() => setPending(undefined)}><p>Some records are invalid or conflict with earlier evidence. They will be excluded from this view. The remaining events may give an incomplete or misleading sequence.</p><div className="partial-summary">{pending.recording.events.length} usable events · {pending.recording.warnings.length} recording notices</div><ul className="modal-warning-list">{pending.recording.warnings.filter(w => ['invalid_line','conflicting_duplicate'].includes(w.code)).map(w => <li key={w.code}>{w.message}{w.line ? ` First affected line: ${w.line}.` : ''}{w.count ? ` ${w.count} occurrences.` : ''}</li>)}</ul><p className="muted small">The original file stays unchanged. A partial view is not a complete recording.</p><div className="modal-actions"><button className="button secondary" onClick={() => setPending(undefined)}>Cancel import</button><button className="button primary" onClick={() => accept(pending.recording, pending.name, pending.demo)}>Open partial view</button></div></Modal>}
    {share && recording && <Modal title="Share a reduced recording" onClose={() => setShare(false)}><p>A new copy will be rebuilt from a strict set of structural fields. Review whether the remaining information is appropriate to share.</p><div className="share-preview"><div><span className="preview-mark remove">−</span><div><strong>Removed</strong><p>All payload values, user labels, attributes, error details, source names, and unknown fields.</p></div></div><div><span className="preview-mark change">↻</span><div><strong>Replaced</strong><p>Labels become neutral operation names. Identifiers are remapped. Absolute timestamps are shifted.</p></div></div><div><span className="preview-mark keep">+</span><div><strong>Retained</strong><p>Operation kinds, statuses, hierarchy, explicit links, relative timing, token totals, and recording warning codes.</p></div></div></div><div className="small-warning">{recording.warnings.length} source notice(s) will remain visible. Structural details may still be sensitive. This export does not guarantee anonymity.</div><p className="muted small">The new final marker describes this export, not the completeness of the original capture. Your original recording is unchanged.</p><div className="modal-actions"><button className="button secondary" onClick={() => setShare(false)}>Cancel</button><button className="button primary" onClick={download}><Icon name="down" size={16}/> Download reduced JSONL</button></div></Modal>}
  </div>;
}
