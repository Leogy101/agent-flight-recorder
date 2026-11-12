import { copyFileSync } from 'node:fs';
for (const name of ['failure', 'interrupted', 'success']) {
  copyFileSync(new URL(`../../fixtures/demo-${name}.jsonl`, import.meta.url), new URL(`../../src/agent_flight_recorder/static/demo-${name}.jsonl`, import.meta.url));
}
copyFileSync(new URL('../../THIRD_PARTY_NOTICES.md', import.meta.url), new URL('../../src/agent_flight_recorder/static/third-party-notices.txt', import.meta.url));
