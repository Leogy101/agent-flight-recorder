// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { jsonl, makeEvents } from './test-fixture';

const response = (text: string) => ({ ok: true, arrayBuffer: async () => new TextEncoder().encode(text).buffer });
beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async () => response(jsonl(makeEvents())))); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
async function demo() { render(<App/>); await userEvent.click(screen.getByRole('button', {name:/Explore an example/i})); await screen.findByRole('heading', {name:'Synthetic test run'}); }

describe('incident workflow', () => {
  it('distinguishes repeated tool attempts and retry relationships in accessible row names', async () => {
    const events = makeEvents();
    events[2].data.kind = 'tool'; events[2].data.name = 'lookup_order'; events[2].data.attributes = { attempt: 1 };
    events[3].data.name = 'lookup_order'; events[3].data.attributes = { attempt: 2 };
    events[3].data.links = [{ span_id: events[2].span_id, relation: 'retry_of' }];
    events[4].data.status = 'error';
    vi.mocked(fetch).mockResolvedValue(response(jsonl(events)) as Response);
    await demo();
    expect(screen.getByRole('button', { name: 'lookup_order Failed tool attempt 1' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'lookup_order Failed tool attempt 2 Retry' })).toBeTruthy();
  });
  it('keeps the latest file selection when an older read completes later', async () => {
    render(<App/>);
    let finishOld!: (value: ArrayBuffer) => void;
    const old = new File([], 'old.jsonl');
    Object.defineProperty(old, 'arrayBuffer', { value: () => new Promise<ArrayBuffer>(resolve => { finishOld = resolve; }) });
    fireEvent.change(screen.getByLabelText('Choose recording file'), { target: { files: [old] } });
    const latestEvents = makeEvents(); latestEvents[1].data.name = 'Most recent run';
    const latest = new File([], 'latest.jsonl');
    Object.defineProperty(latest, 'arrayBuffer', { value: async () => new TextEncoder().encode(jsonl(latestEvents)).buffer });
    fireEvent.change(screen.getByLabelText('Choose recording file'), { target: { files: [latest] } });
    await screen.findByRole('heading', { name: 'Most recent run' });
    await act(async () => finishOld(new TextEncoder().encode(jsonl(makeEvents())).buffer));
    expect(screen.getByRole('heading', { name: 'Most recent run' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Synthetic test run' })).toBeNull();
  });
  it('does not reopen a pending example after navigating home', async () => {
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    render(<App/>);
    await userEvent.click(screen.getByRole('button', { name: /Explore an example/ }));
    await userEvent.click(screen.getByRole('link', { name: 'Agent Flight Recorder home' }));
    await act(async () => finish(response(jsonl(makeEvents())) as Response));
    expect(screen.queryByRole('heading', { name: 'Synthetic test run' })).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });
  it('supports the inspector tab keyboard pattern and operation event navigation', async () => {
    await demo();
    const details = screen.getByRole('tab', { name: 'Details' }); details.focus();
    await userEvent.keyboard('{ArrowRight}');
    const raw = screen.getByRole('tab', { name: 'Raw events' });
    expect(document.activeElement).toBe(raw);
    expect(raw.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(raw.id);
    await userEvent.keyboard('{Home}');
    expect(document.activeElement).toBe(details);
    await userEvent.click(screen.getByRole('button', { name: 'Go to start' }));
    expect(screen.getByLabelText('Current stored event').textContent).toContain('span.started');
    expect(screen.getByRole('slider', { name: 'Playback event position' }).getAttribute('aria-valuetext')).toContain('span.started');
    await userEvent.click(screen.getByRole('button', { name: 'Go to end' }));
    expect(screen.getByLabelText('Current stored event').textContent).toContain('span.ended');
  });
  it('lets users inspect orphan ends and capture markers without inventing a start', async () => {
    const events = makeEvents().filter(event => event.type !== 'span.started');
    events.at(-1)!.data.written_events = events.length;
    events[0].data.name = { unknown: 'inert source extension' };
    vi.mocked(fetch).mockResolvedValue(response(jsonl(events)) as Response);
    render(<App/>); await userEvent.click(screen.getByRole('button', { name: /Explore an example/ }));
    await screen.findByRole('heading', { name: 'Untitled recording' });
    await userEvent.click(screen.getByText('Inspect stored event'));
    expect(screen.getByLabelText('Current stored event').textContent).toContain('capture.ended');
    await userEvent.click(screen.getByRole('button', { name: 'Previous event' }));
    expect(screen.getByText(/This operation has no recorded start/)).toBeTruthy();
    expect(screen.getByLabelText('Current stored event').textContent).toContain('span.ended');
  });
  it('renders annotations lazily with bounded pagination', async () => {
    const events = makeEvents();
    for (let i = 0; i < 120; i++) events.splice(events.length - 1, 0, { ...structuredClone(events[0]), event_id: crypto.randomUUID(), seq: 10 + i, type: 'event.recorded', data: { name: `Note ${i}`, payload: { state: 'captured', value: `Annotation payload ${i}` } } });
    events.at(-1)!.data.written_events = events.length;
    vi.mocked(fetch).mockResolvedValue(response(jsonl(events)) as Response);
    await demo();
    expect(screen.queryByRole('button', { name: /Inspect annotation/ })).toBeNull();
    await userEvent.click(screen.getByText('120 recorded annotations'));
    await waitFor(() => expect(screen.getAllByRole('button', { name: /Inspect annotation/ })).toHaveLength(40));
    await userEvent.click(screen.getByRole('button', { name: 'Next annotations' }));
    expect(screen.getByRole('button', { name: 'Inspect annotation Note 40' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Inspect annotation Note 0' })).toBeNull();
  });
  it('distinguishes a recovered tool error from a failed root run', async () => {
    const events = makeEvents(); events[6].data.status = 'ok'; delete events[6].data.error;
    vi.mocked(fetch).mockResolvedValue(response(jsonl(events)) as Response);
    await demo();
    expect(screen.getByText('Succeeded')).toBeTruthy();
    expect(screen.getByText('Root succeeded · earlier errors recorded')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Synthetic tool Failed/ })).toBeTruthy();
  });
  it('opens a synthetic example, selects the failed tool, and navigates stored playback', async () => {
    await demo();
    const inspector = screen.getByLabelText('Operation inspector');
    expect(within(inspector).getByRole('heading', {name:'Synthetic tool'})).toBeTruthy();
    await userEvent.click(screen.getByRole('button', {name:'Reset playback'}));
    expect(screen.getByText('No operation starts at this point')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', {name:'Next event'}));
    expect(screen.getByRole('button', {name:/Synthetic test run Unfinished/})).toBeTruthy();
    await userEvent.click(screen.getByRole('button', {name:/Show all/}));
    expect(screen.getByRole('button', {name:/Synthetic tool Failed/})).toBeTruthy();
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1); expect(vi.mocked(fetch).mock.calls[0][0]).toBe('./demo-failure.jsonl');
  });
  it('requires explicit acknowledgement before showing a malformed partial recording', async () => {
    const source = jsonl(makeEvents()).split('\n'); source.splice(3,0,'this is invalid');
    vi.mocked(fetch).mockResolvedValue(response(source.join('\n')) as Response);
    render(<App/>); await userEvent.click(screen.getByRole('button', {name:/Explore an example/}));
    const dialog = await screen.findByRole('dialog', {name:'Review an incomplete import'});
    expect(screen.queryByRole('heading', {name:'Synthetic test run'})).toBeNull();
    await userEvent.click(within(dialog).getByRole('button', {name:'Open partial view'}));
    expect(await screen.findByRole('heading', {name:'Synthetic test run'})).toBeTruthy();
    expect(screen.getByRole('button', {name:/Review notices/})).toBeTruthy();
  });
  it('renders malicious payloads as plain text without active HTML or links', async () => {
    const events = makeEvents(); events[3].data.input.value = '<img src="https://evil.invalid/track" onerror="window.pwned=true"> javascript:alert(1)';
    vi.mocked(fetch).mockResolvedValue(response(jsonl(events)) as Response);
    await demo();
    expect(document.querySelector('img')).toBeNull(); expect((window as any).pwned).toBeUndefined();
    expect(screen.getByText(/<img src=/)).toBeTruthy(); expect(document.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });
  it('filters evidence and provides an explicit sharing review', async () => {
    await demo();
    await userEvent.type(screen.getByRole('textbox', {name:'Search recorded operations'}),'synthetic model');
    expect(screen.getByRole('button', {name:/Synthetic model OK/})).toBeTruthy(); expect(screen.queryByRole('button', {name:/Synthetic tool Failed/})).toBeNull();
    await userEvent.click(screen.getByRole('button', {name:/Share a reduced copy/}));
    expect(screen.getByRole('dialog', {name:'Share a reduced recording'})).toBeTruthy();
    expect(screen.getByText(/does not guarantee anonymity/)).toBeTruthy();
    await userEvent.keyboard('{Escape}'); expect(screen.queryByRole('dialog')).toBeNull();
  });
  it('does not label arbitrary filenames as synthetic and rejects malformed UTF-8', async () => {
    render(<App/>);
    const file = new File([], 'demo-failure.jsonl'); Object.defineProperty(file,'arrayBuffer',{value:async()=>new TextEncoder().encode(jsonl(makeEvents())).buffer});
    fireEvent.change(screen.getByLabelText('Choose recording file'), {target:{files:[file]}});
    await screen.findByRole('heading', {name:'Synthetic test run'});
    expect(screen.getByText('RECORDING / LOCAL FILE')).toBeTruthy(); expect(vi.mocked(fetch)).not.toHaveBeenCalled();
    const bad = new File([], 'bad.jsonl'); Object.defineProperty(bad,'arrayBuffer',{value:async()=>new Uint8Array([0xc3,0x28]).buffer});
    fireEvent.change(screen.getByLabelText('Choose recording file'), {target:{files:[bad]}});
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('not valid UTF-8'));
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });
});
