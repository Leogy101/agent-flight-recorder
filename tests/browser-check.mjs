// Real-browser acceptance checks against the packaged loopback server.
import { chromium } from '../viewer/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const python = process.env.AFR_PYTHON ?? (existsSync(join(root, '.venv/bin/python')) ? join(root, '.venv/bin/python') : 'python3');
const work = join(root, 'work/browser');
mkdirSync(work, { recursive: true });
const server = spawn(python, ['-m', 'agent_flight_recorder', 'view', '--no-open'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let browser;
try {
  const url = await new Promise((resolve, reject) => {
    let text = '';
    const timer = setTimeout(() => reject(new Error('Viewer server did not start')), 15000);
    server.stdout.on('data', data => {
      text += data;
      const match = text.match(/http:\/\/127\.0\.0\.1:\d+\//);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    server.once('error', reject);
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Viewer exited ${code}`)); });
  });
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
  const page = await context.newPage();
  const failures = [], external = [], uploads = [];
  page.on('pageerror', error => failures.push(error.message));
  await page.route('**/*', route => {
    const target = route.request().url();
    if (!['GET', 'HEAD'].includes(route.request().method()) || route.request().postData()) uploads.push(target);
    if (target.startsWith(url) || target.startsWith('blob:') || target.startsWith('data:')) route.continue();
    else { external.push(target); route.abort(); }
  });
  await page.goto(url);
  await page.getByRole('heading', { level: 1 }).waitFor();
  await page.getByRole('img', { name: /Agent Flight Recorder/ }).waitFor();
  await page.screenshot({ path: join(root, 'docs/screenshots/welcome.png'), fullPage: true });
  await page.getByRole('button', { name: /Explore an example/ }).click();
  await page.getByRole('heading', { name: 'Resolve a duplicate charge', exact: true, level: 1 }).waitFor();
  await page.getByRole('button', { name: /Issue refund.*attempt 1/ }).click();
  const inspector = page.getByLabel('Operation inspector');
  await inspector.getByText('invalid_argument', { exact: true }).waitFor();
  assert.match(await inspector.textContent(), /42\.00/);
  assert.match(await page.getByLabel('Recording evidence quality').textContent(), /No structural gaps/);
  mkdirSync(join(root, 'docs/screenshots'), { recursive: true });
  await page.screenshot({ path: join(root, 'docs/screenshots/flight-recorder.png'), fullPage: true });

  // Browser-produced reduced file must remain readable by the Python consumer.
  await page.getByRole('button', { name: 'Share a reduced copy' }).click();
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download reduced JSONL' }).click();
  const download = await downloaded;
  const reduced = join(work, 'reduced.jsonl');
  await download.saveAs(reduced);
  const shared = readFileSync(reduced, 'utf8');
  assert(!shared.includes('42.00') && !shared.includes('DEMO-2048') && !shared.includes('Resolve a duplicate charge'));
  execFileSync(python, ['-c', 'import sys; from agent_flight_recorder.recording import load_recording; r=load_recording(sys.argv[1]); assert r["events"]', reduced], { cwd: root });

  await page.getByRole('button', { name: 'Reset playback' }).click();
  await page.getByText('No operation starts at this point').waitFor();
  await page.getByRole('button', { name: 'Next event', exact: true }).click();
  await page.getByRole('button', { name: /Resolve a duplicate charge/ }).waitFor();
  await page.getByRole('button', { name: /Show all/ }).click();
  await page.getByRole('combobox', { name: 'Filter by kind' }).selectOption('tool');
  assert.equal(await page.locator('.operation-row').count(), 2);
  await page.getByRole('combobox', { name: 'Filter by kind' }).selectOption('all');

  const fileInput = page.getByLabel('Choose recording file');
  await fileInput.setInputFiles(join(root, 'fixtures/demo-interrupted.jsonl'));
  await page.getByRole('heading', { name: 'Research a delivery delay', exact: true, level: 1 }).waitFor();
  assert.match(await page.getByLabel('Recording evidence quality').textContent(), /recording notice/);
  await page.getByRole('button', { name: /Look up shipment/ }).click();
  assert.match(await inspector.textContent(), /does not establish that the operation failed/);

  // Imported strings are inert, including markup and remote image references.
  const original = readFileSync(join(root, 'fixtures/demo-success.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  const hostile = structuredClone(original);
  hostile.find(e => e.type === 'span.started').data.name = '<img src="https://afr-invalid.example/pixel" onerror="window.AFR_INJECTED=1">';
  hostile.find(e => e.type === 'span.started').data.input = { state: 'captured', value: '<script>window.AFR_INJECTED=1</script>' };
  await fileInput.setInputFiles({ name: 'hostile.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(hostile.map(JSON.stringify).join('\n') + '\n') });
  await page.getByRole('heading', { name: /<img src=/, level: 1 }).waitFor();
  assert.equal(await page.evaluate(() => window.AFR_INJECTED), undefined);
  assert.equal(await page.locator('img[src*="afr-invalid"]').count(), 0);

  // Invalid middle rows need explicit partial-view acknowledgement.
  const partial = original.map(JSON.stringify);
  partial.splice(3, 0, '{broken JSON');
  await fileInput.setInputFiles({ name: 'partial.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(partial.join('\n') + '\n') });
  await page.getByRole('dialog', { name: 'Review an incomplete import' }).waitFor();
  await page.getByRole('button', { name: 'Open partial view' }).click();
  await page.getByRole('heading', { name: 'Resolve a duplicate charge', exact: true, level: 1 }).waitFor();

  // Conflicting evidence must remain conflicting after filtering a share copy.
  const conflicting = structuredClone(original);
  const rootEnd = conflicting.find(e => e.type === 'span.ended' && e.span_id === conflicting[1].span_id);
  const alternate = structuredClone(rootEnd);
  alternate.data.status = 'error';
  conflicting.splice(conflicting.length - 1, 0, alternate);
  await fileInput.setInputFiles({ name: 'conflicting.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(conflicting.map(JSON.stringify).join('\n') + '\n') });
  await page.getByRole('dialog', { name: 'Review an incomplete import' }).waitFor();
  await page.getByRole('button', { name: 'Open partial view' }).click();
  await page.locator('.summary-grid').getByText('Conflicting', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Share a reduced copy' }).click();
  const conflictDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download reduced JSONL' }).click();
  const conflictPath = join(work, 'conflicting-reduced.jsonl');
  await (await conflictDownload).saveAs(conflictPath);
  await fileInput.setInputFiles(conflictPath);
  await page.locator('.summary-grid').getByText('Conflicting', { exact: true }).waitFor();
  execFileSync(python, ['-c', 'import sys; from agent_flight_recorder.recording import load_recording; r=load_recording(sys.argv[1]); assert any(w["code"]=="conflicting_duplicate" for w in r["warnings"])', conflictPath], { cwd: root });

  // Imported source intervals use their historical clock, never conversion time.
  const converted = execFileSync(python, ['-c', 'import json,sys; from agent_flight_recorder.otlp import convert_otlp; events=convert_otlp(json.load(open(sys.argv[1]))); print("\\n".join(map(json.dumps,events)))', join(root, 'fixtures/otlp-example.json')], { cwd: root });
  await fileInput.setInputFiles({ name: 'imported.jsonl', mimeType: 'application/x-ndjson', buffer: converted });
  await page.getByRole('heading', { name: 'Synthetic imported agent', level: 1, exact: true }).waitFor();
  assert.match(await page.getByLabel('Recording evidence quality').textContent(), /Imported completed spans/);
  await page.getByRole('button', { name: /Synthetic inventory lookup/ }).click();
  assert.match(await inspector.textContent(), /Reconstructed from a completed span/);

  // Execute the reproducible agent through the actual recorder, then inspect
  // both outcomes. Fixtures for these checks are not assembled by this script.
  const executed = join(work, `executed-${randomUUID()}`);
  execFileSync(python, ['examples/record_agent.py', '--output-dir', executed, '--capture-content'], { cwd: root });
  await fileInput.setInputFiles(join(executed, 'success.jsonl'));
  await page.locator('.summary-grid').getByText('Succeeded', { exact: true }).waitFor();
  assert.match(await page.locator('.summary-grid').textContent(), /Root succeeded.*earlier errors recorded/);
  await page.getByRole('button', { name: /lookup_order.*attempt 2/ }).click();
  assert.match(await inspector.textContent(), /SYN-1001/);
  assert.match(await inspector.textContent(), /shipped/);
  assert.match(await inspector.textContent(), /\[REDACTED\]/);
  assert(!(await inspector.textContent()).includes('synthetic.customer@example.invalid'));
  await page.screenshot({ path: join(root, 'docs/screenshots/executed-success.png'), fullPage: true });
  await fileInput.setInputFiles(join(executed, 'failure.jsonl'));
  await page.locator('.summary-grid').getByText('Failed', { exact: true }).waitFor();
  await page.getByRole('button', { name: /lookup_order.*attempt 2/ }).click();
  assert.match(await inspector.textContent(), /OrderNotFound/);
  assert.match(await inspector.textContent(), /SYN-4040/);
  await page.screenshot({ path: join(root, 'docs/screenshots/executed-failure.png'), fullPage: true });

  // Keyboard tab navigation and exact event inspection work without a mouse.
  await page.getByRole('tab', { name: 'Details', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await page.getByRole('tab', { name: 'Raw events', selected: true }).waitFor();
  assert.match(await page.getByRole('tabpanel').textContent(), /span.started/);
  await page.keyboard.press('Home');
  await page.getByRole('tab', { name: 'Details', selected: true }).waitFor();
  await page.getByRole('button', { name: 'Go to start', exact: true }).click();
  assert.match(await page.getByLabel('Current stored event').textContent(), /span.started/);
  assert.equal(await page.locator('.summary-grid').getByText('Failed', { exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Go to end', exact: true }).click();
  assert.match(await page.getByLabel('Current stored event').textContent(), /OrderNotFound/);
  await page.getByRole('button', { name: /Show all/ }).click();
  await page.getByRole('button', { name: 'Reset playback' }).click();
  assert.match(await page.getByLabel('Current stored event').textContent(), /capture.started/);
  await page.getByRole('button', { name: 'Play recorded events' }).click();
  await page.waitForFunction(() => Number(document.querySelector('[aria-label="Playback event position"]').value) > 0);
  await page.getByRole('button', { name: 'Pause playback' }).click();
  await page.getByRole('button', { name: /Show all/ }).click();

  await page.getByRole('textbox', { name: 'Search recorded operations' }).fill('no matching operation');
  assert.equal(await page.locator('.operation-row').count(), 0);
  assert.match(await page.locator('.timeline-empty').textContent(), /No operations/);
  await page.getByRole('button', { name: 'Clear search' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: /lookup_order.*attempt 2/ }).click();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Narrow layout must not overflow horizontally');
  assert.match(await inspector.textContent(), /OrderNotFound/);
  await page.screenshot({ path: join(root, 'docs/screenshots/narrow-view.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1050 });

  const metadataOnly = join(work, `metadata-${randomUUID()}`);
  execFileSync(python, ['examples/record_agent.py', '--scenario', 'success', '--output-dir', metadataOnly], { cwd: root });
  await fileInput.setInputFiles(join(metadataOnly, 'success.jsonl'));
  await page.locator('.summary-grid').getByText('Metadata only', { exact: true }).waitFor();
  await page.getByRole('button', { name: /lookup_order.*attempt 2/ }).click();
  assert.match(await inspector.textContent(), /Content was not retained/);
  assert(!(await inspector.textContent()).includes('SYN-1001'));

  // Near-limit file: 4,998 operations plus root and capture boundaries = 10,000 events.
  const capture = structuredClone(original[0]);
  capture.data.privacy_mode = 'metadata_only';
  capture.data.coverage = 'Synthetic 10000-event browser benchmark';
  const rootStart = structuredClone(original[1]);
  rootStart.data.name = 'Synthetic large recording';
  rootStart.data.input = { state: 'omitted', reason: 'policy' };
  const large = [capture, rootStart];
  const omitted = { state: 'omitted', reason: 'policy' };
  const makeEvent = (type, data, span_id, parent_span_id) => ({
    schema_version: '0.1', recording_id: capture.recording_id, trace_id: capture.trace_id,
    event_id: randomUUID(), seq: large.length + 1, type, recorded_at: capture.recorded_at,
    elapsed_us: large.length * 10, ...(span_id ? { span_id } : {}), ...(parent_span_id ? { parent_span_id } : {}), data,
  });
  for (let index = 1; index <= 4998; index++) {
    const spanId = index.toString(16).padStart(16, '0');
    large.push(makeEvent('span.started', { kind: 'tool', name: `Synthetic lookup ${index}`, input: omitted }, spanId, rootStart.span_id));
    large.push(makeEvent('span.ended', { status: 'ok', output: omitted }, spanId));
  }
  large.push(makeEvent('span.ended', { status: 'ok', output: omitted }, rootStart.span_id));
  large.push(makeEvent('capture.ended', { written_events: 10000, skipped_events: 0, failed_events: 0, limit_reached: false }));
  assert.equal(large.length, 10000);
  const largeText = large.map(JSON.stringify).join('\n') + '\n';
  const before = performance.now();
  await fileInput.setInputFiles({ name: 'large.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(largeText) });
  await page.getByRole('heading', { name: 'Synthetic large recording', exact: true, level: 1 }).waitFor();
  const largeImportMs = performance.now() - before;
  assert.equal(await page.locator('.operation-row').count(), 80);
  const filterStart = performance.now();
  await page.getByRole('textbox', { name: 'Search recorded operations' }).fill('Synthetic lookup 4998');
  await page.getByRole('button', { name: /Synthetic lookup 4998/ }).waitFor();
  const filterMs = performance.now() - filterStart;
  const browserHeap = await page.evaluate(() => performance.memory?.usedJSHeapSize ?? null);
  assert.deepEqual(failures, []);
  assert.deepEqual(external, []);
  assert.deepEqual(uploads, []);
  const report = { browser: browser.version(), largeImportMs: Math.round(largeImportMs), filterMs: Math.round(filterMs), bytes: Buffer.byteLength(largeText), events: large.length, usedJsHeapBytes: browserHeap, pageErrors: failures, outboundRequests: external, dataUploads: uploads, checks: ['synthetic failure inspection', 'reduced export Python conformance', 'playback', 'kind filter', 'interrupted evidence', 'inert malicious markup', 'explicit partial import', 'conflict preserved after sharing', 'imported source-time intervals', 'executed agent success with recovered error', 'executed agent failure inspection', 'keyboard inspector tabs', 'exact start/end event navigation', 'timed playback', 'empty search state', '390px narrow layout', 'default metadata-only execution capture', '10000 event import/filter'] };
  writeFileSync(join(work, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
