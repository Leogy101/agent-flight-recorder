// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import App from './App';
import { parseRecording, reducedExport } from './model';
import { jsonl, makeEvents } from './test-fixture';
import { VIEWER_VERSION } from './version';

afterEach(cleanup);

it('shows the release version and uses it for new export provenance only', () => {
  render(<App/>);
  expect(VIEWER_VERSION).toBe('0.1.0-alpha.1');
  expect(screen.getByText(`v${VIEWER_VERSION}`)).toBeTruthy();
  const source = parseRecording(jsonl(makeEvents()));
  const originalVersion = source.events[0].data.recorder_version;
  const exported = parseRecording(reducedExport(source));
  expect(exported.events[0].data.recorder_version).toBe(VIEWER_VERSION);
  expect(exported.events.every(event => event.schema_version === '0.1')).toBe(true);
  expect(exported.events[0].data.transform.version).toBe('0.1');
  expect(source.events[0].data.recorder_version).toBe(originalVersion);
});
