// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { jsonl, makeEvents } from './test-fixture';

const response = (text: string) => ({ ok: true, arrayBuffer: async () => new TextEncoder().encode(text).buffer });
beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async () => response(jsonl(makeEvents())))); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
async function demo() { render(<App/>); await userEvent.click(screen.getByRole('button', {name:/Explore an example/i})); await screen.findByRole('heading', {name:'Synthetic test run'}); }

describe('incident workflow', () => {
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
