/**
 * Convene-time public link: with no fixed origin, the CLI probes the candidate
 * Council address once (no redirect following, hard timeout) and keeps it only
 * for a 302/303 to a *.cloudflareaccess.com host. Never fails the council.
 */
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import type { CliIo } from '../src/cli/dispatcher.js';
import { conveneCandidates, runConvene } from '../src/cli/convene.js';

const CAND = 'https://qcbox-council.zerohumanworkforce.com';
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
const ACCESS = { status: 302, headers: { location: 'https://acme.cloudflareaccess.com/cdn-cgi/access/login/x' } };

type Probe = { status: number; headers?: Record<string, string> } | 'hang' | 'throw';

async function run(probe: Probe, env: NodeJS.ProcessEnv) {
  let out = '';
  const calls: Array<{ url: string; redirect?: string }> = [];
  const io: CliIo = { out: (t) => (out += t), err: () => undefined };
  const fetchImpl = ((url: string, init?: RequestInit) => {
    calls.push({ url: String(url), redirect: init?.redirect });
    if (String(url).endsWith('/status')) {
      if (probe === 'throw') return Promise.reject(new Error('dns'));
      if (probe === 'hang') return new Promise(() => undefined);
      return Promise.resolve(new Response(null, { status: probe.status, headers: probe.headers }));
    }
    return Promise.resolve(new Response(JSON.stringify(ACCEPTED), { status: 202 }));
  }) as typeof fetch;
  const code = await runConvene(['--sample', '--json'], { fetchImpl, env, io, probeTimeoutMs: 50 });
  return { code, json: JSON.parse(out) as Record<string, unknown>, calls };
}

test('302 to cloudflareaccess: link emitted, probe does not follow redirects, origin persisted', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'cvl-'));
  const svc = join(dir, 'service.json');
  writeFileSync(svc, JSON.stringify({ schema: 'council-service/v1', public_origin: null }));
  const r = await run(ACCESS, { WISE_ELDERS_PUBLIC_CANDIDATE: CAND, WISE_ELDERS_SERVICE_JSON: svc });
  assert.equal(r.code, 0);
  assert.equal(r.json.chamber_url, `${CAND}/chamber/#session=sess-9`);
  const probe = r.calls.find((c) => c.url.endsWith('/status'));
  assert.equal(probe?.url, `${CAND}/status`);
  assert.equal(probe?.redirect, 'manual');
  assert.equal(JSON.parse(readFileSync(svc, 'utf8')).public_origin, CAND);
});

test('303 is accepted too', async () => {
  const r = await run({ status: 303, headers: { location: 'https://x.cloudflareaccess.com/l' } }, { WISE_ELDERS_PUBLIC_CANDIDATE: CAND });
  assert.equal(r.json.chamber_url, `${CAND}/chamber/#session=sess-9`);
});

test('dropped without a link and without failing: 200, non-Access host, lookalike, no Location, timeout, network error', async () => {
  const cases: Array<[string, Probe]> = [
    ['200', { status: 200 }],
    ['non-access host', { status: 302, headers: { location: 'https://evil.example.com/login' } }],
    ['lookalike suffix', { status: 302, headers: { location: 'https://cloudflareaccess.com.evil.net/x' } }],
    ['lookalike prefix', { status: 302, headers: { location: 'https://evilcloudflareaccess.com/x' } }],
    ['http Access host', { status: 302, headers: { location: 'http://x.cloudflareaccess.com/x' } }],
    ['no Location', { status: 302 }],
    ['timeout', 'hang'],
    ['network error', 'throw'],
  ];
  for (const [name, p] of cases) {
    const r = await run(p, { WISE_ELDERS_PUBLIC_CANDIDATE: CAND });
    assert.equal(r.code, 0, name);
    assert.equal('chamber_url' in r.json, false, name);
  }
});

test('a persist failure never fails the council', async () => {
  const r = await run(ACCESS, { WISE_ELDERS_PUBLIC_CANDIDATE: CAND, WISE_ELDERS_SERVICE_JSON: '/nonexistent/dir/service.json' });
  assert.equal(r.code, 0);
  assert.equal(r.json.chamber_url, `${CAND}/chamber/#session=sess-9`);
});

test('IP literal, localhost, http or path candidates are never probed or linked', async () => {
  for (const bad of ['https://203.0.113.9', 'https://[::1]', 'https://localhost', 'http://a-council.example.com', `${CAND}/x`]) {
    const r = await run(ACCESS, { WISE_ELDERS_PUBLIC_CANDIDATE: bad });
    assert.equal('chamber_url' in r.json, false, bad);
    assert.equal(r.calls.some((c) => c.url.endsWith('/status')), false, bad);
  }
  for (const bad of ['https://203.0.113.9:3000', 'http://localhost:3000', '10.0.0.5']) {
    assert.deepEqual(conveneCandidates({ CC_PUBLIC_URL: bad }), [], bad);
  }
});

test('an explicit public origin skips the probe entirely', async () => {
  const r = await run(ACCESS, { WISE_ELDERS_PUBLIC_ORIGIN: 'https://fixed.example.com', WISE_ELDERS_PUBLIC_CANDIDATE: CAND });
  assert.equal(r.calls.some((c) => c.url.endsWith('/status')), false);
  assert.equal(r.json.chamber_url, 'https://fixed.example.com/chamber/#session=sess-9');
});

test('candidate is re-derived at convene time with no interview state, from install-time sources', () => {
  const home = mkdtempSync(join(tmpdir(), 'cvh-'));
  // nothing yet: no candidate
  assert.deepEqual(conveneCandidates({ HOME: home }), []);
  // the Command Center app's .env.local (written at provisioning, before any interview)
  const app = join(home, 'projects', 'command-center');
  mkdirSync(app, { recursive: true });
  writeFileSync(join(app, '.env.local'), 'MC_API_TOKEN=secret\nMC_TENANT_PUBLIC_URL="https://ann.zerohumanworkforce.com"\n');
  assert.deepEqual(conveneCandidates({ HOME: home }), ['https://ann-council.zerohumanworkforce.com']);
  // process env beats the file; baked candidate is last; duplicates collapse
  assert.deepEqual(
    conveneCandidates({ HOME: home, CC_PUBLIC_URL: 'https://bob.zerohumanworkforce.com', WISE_ELDERS_PUBLIC_CANDIDATE: 'https://ann-council.zerohumanworkforce.com' }),
    ['https://bob-council.zerohumanworkforce.com', 'https://ann-council.zerohumanworkforce.com'],
  );
  // launch state seeded at install time is a further source
  const oc = join(home, '.openclaw', 'workspace');
  mkdirSync(oc, { recursive: true });
  writeFileSync(join(oc, '.workforce-build-state.json'), JSON.stringify({ commandCenterUrl: 'https://cy.zerohumanworkforce.com' }));
  assert.deepEqual(conveneCandidates({ HOME: home }), [
    'https://ann-council.zerohumanworkforce.com',
    'https://cy-council.zerohumanworkforce.com',
  ]);
});
