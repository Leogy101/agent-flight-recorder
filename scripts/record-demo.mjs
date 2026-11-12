// Capture a short real-browser walkthrough using reviewed synthetic recordings.
// Requires the existing viewer development dependency: npx playwright install chromium.
import { chromium } from '../viewer/node_modules/playwright/index.mjs';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const python = process.env.AFR_PYTHON ?? (existsSync(join(root, '.venv/bin/python')) ? join(root, '.venv/bin/python') : 'python3');
const output = join(root, 'docs/screenshots/agent-demo.webm');
const temporary = join(root, 'work/demo-video');
mkdirSync(temporary, { recursive: true });
mkdirSync(dirname(output), { recursive: true });
const server = spawn(python, ['-m', 'agent_flight_recorder', 'view', '--no-open'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
let browser;
try {
  const url = await new Promise((resolve, reject) => {
    let text = '';
    const timer = setTimeout(() => reject(new Error('Viewer did not start')), 15000);
    server.stdout.on('data', data => {
      text += data;
      const match = text.match(/http:\/\/127\.0\.0\.1:\d+\//);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    server.once('error', error => { clearTimeout(timer); reject(error); });
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Viewer exited ${code}`)); });
  });
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1280 }, recordVideo: { dir: temporary, size: { width: 1440, height: 1280 } } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    if (route.request().url().startsWith(url)) return route.continue();
    errors.push('Unexpected remote request');
    return route.abort();
  });
  await page.goto(url);
  await page.getByRole('img', { name: /Agent Flight Recorder/ }).waitFor();
  // These pauses pace a viewer demonstration; they never affect agent timing.
  await page.waitForTimeout(2000);
  const input = page.getByLabel('Choose recording file');
  await input.setInputFiles(join(root, 'fixtures/agent-example-failure.jsonl'));
  await page.getByRole('button', { name: /lookup_order.*attempt 1/ }).click();
  await page.waitForTimeout(3500);
  await page.getByRole('button', { name: /lookup_order.*attempt 2/ }).click();
  await page.waitForTimeout(3500);
  await page.getByRole('button', { name: 'Go to start', exact: true }).click();
  await page.waitForTimeout(2000);
  await page.getByRole('button', { name: 'Go to end', exact: true }).click();
  await page.waitForTimeout(2000);
  await page.getByRole('button', { name: /Show all/ }).click();
  await input.setInputFiles(join(root, 'fixtures/agent-example-success.jsonl'));
  await page.getByRole('button', { name: /lookup_order.*attempt 2/ }).click();
  await page.waitForTimeout(3500);
  await page.getByRole('button', { name: 'Share a reduced copy' }).click();
  await page.waitForTimeout(3000);
  const video = page.video();
  await context.close();
  if (errors.length) throw new Error(errors.join('\n'));
  await video.saveAs(output);
  await video.delete();
  console.log(`Saved synthetic browser demonstration: ${output}`);
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
