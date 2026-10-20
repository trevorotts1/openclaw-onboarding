/**
 * L2-access: WISE_ELDERS_PUBLIC_ORIGIN / --public-origin only changes the link
 * the client is handed. API calls still go to the loopback service origin.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import type { CliIo } from '../src/cli/dispatcher.js';
import { runConvene } from '../src/cli/convene.js';

const PUBLIC = 'https://qcbox-council.zerohumanworkforce.com';
const ACCEPTED = {
  session_id: 'sess-9',
  state: 'RUNNING',
  sample: true,
  route_id: 'deepseek-configured',
  model_label: 'm',
  selection_source: 'client_default',
  session_path: '/council/sess-9',
  events_path: '/api/council/sessions/sess-9/events',
};

function run(args: string[], env: NodeJS.ProcessEnv) {
  let out = '';
  let err = '';
  const urls: string[] = [];
  const io: CliIo = { out: (t) => (out += t), err: (t) => (err += t) };
  const fetchImpl = (async (url: string) => {
    urls.push(String(url));
    return new Response(JSON.stringify(ACCEPTED), { status: 202 });
  }) as typeof fetch;
  return runConvene(args, { fetchImpl, env, io }).then((code) => ({ code, out, err, urls }));
}

test('env public origin: JSON gains chamber_url, POST stays on loopback', async () => {
  const r = await run(['--sample', '--json'], { WISE_ELDERS_PUBLIC_ORIGIN: PUBLIC });
  assert.equal(r.code, 0);
  assert.deepEqual(r.urls, ['http://127.0.0.1:8787/api/council/convene']);
  assert.equal(JSON.parse(r.out).chamber_url, `${PUBLIC}/chamber/#session=sess-9`);
});

test('text output: first link line is the Roast Room link', async () => {
  const r = await run(['--sample'], { WISE_ELDERS_PUBLIC_ORIGIN: PUBLIC });
  assert.equal(r.code, 0);
  const lines = r.out.split('\n');
  const first = lines.find((l) => /https?:\/\//.test(l));
  assert.equal(first, `Open the Roast Room: ${PUBLIC}/chamber/#session=sess-9`);
});

test('--public-origin flag beats the env var', async () => {
  const r = await run(['--sample', '--json', '--public-origin', 'https://flag.example.com'], { WISE_ELDERS_PUBLIC_ORIGIN: PUBLIC });
  assert.equal(JSON.parse(r.out).chamber_url, 'https://flag.example.com/chamber/#session=sess-9');
});

test('unset: no chamber_url and no Roast Room line', async () => {
  const j = await run(['--sample', '--json'], {});
  assert.equal('chamber_url' in JSON.parse(j.out), false);
  const t = await run(['--sample'], {});
  assert.equal(t.out.includes('Roast Room'), false);
});

test('http or a path is rejected with the typed invalid-input error, before any POST', async () => {
  for (const bad of ['http://qcbox-council.zerohumanworkforce.com', `${PUBLIC}/chamber`, `${PUBLIC}/?x=1`, 'not a url']) {
    const r = await run(['--sample', '--json'], { WISE_ELDERS_PUBLIC_ORIGIN: bad });
    assert.equal(r.code, 2, bad);
    assert.equal(JSON.parse(r.err).error?.code ?? JSON.parse(r.err).code, 'COUNCIL_INVALID_INPUT', bad);
    assert.equal(r.urls.length, 0, bad);
  }
});
