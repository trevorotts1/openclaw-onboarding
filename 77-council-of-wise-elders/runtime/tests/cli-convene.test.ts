/**
 * W28: `routes` and `convene` CLI commands against an injected fetch.
 * No network, no service, no filesystem outside a temp dir.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { detectHarness, runConvene, runRoutes } from '../src/cli/convene.js';

function capture(): { io: CliIo; out: () => string; err: () => string } {
  let o = '';
  let e = '';
  return { io: { out: (t) => (o += t), err: (t) => (e += t) }, out: () => o, err: () => e };
}

interface Call {
  url: string;
  method: string;
  body: Record<string, unknown> | null;
}

function fakeFetch(status: number, reply: unknown): { fetchImpl: typeof fetch; calls: Call[] } {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    calls.push({
      url: String(url),
      method: init?.method ?? 'GET',
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : null,
    });
    return new Response(typeof reply === 'string' ? reply : JSON.stringify(reply), { status });
  }) as typeof fetch;
  return { fetchImpl, calls };
}

const ACCEPTED = {
  session_id: 'sess-1',
  state: 'RUNNING',
  sample: true,
  route_id: 'deepseek-configured',
  model_label: 'deepseek-v4.1-flash',
  selection_source: 'client_default',
  grant_id: 'g1',
  session_path: '/council/sess-1',
  events_path: '/api/council/sessions/sess-1/events',
};

const NINE = { CLAUDE_CONFIG_DIR: '/home/x/.claude-nine', CLAUDECODE: '1' };
const CODE = { CLAUDECODE: '1', CLAUDE_CONFIG_DIR: '/home/x/.claude' };

test('detectHarness: claude-nine, claude-code, unknown', () => {
  assert.equal(detectHarness(NINE), 'claude-nine');
  assert.equal(detectHarness({ CLAUDE_CONFIG_DIR: '/home/x/.claude-nine/' }), 'claude-nine');
  assert.equal(detectHarness(CODE), 'claude-code');
  assert.equal(detectHarness({ CLAUDECODE: '1' }), 'claude-code');
  assert.equal(detectHarness({}), 'unknown');
  assert.equal(detectHarness({ CLAUDECODE: '0', CLAUDE_CONFIG_DIR: '/home/x/.claude' }), 'unknown');
  // A directory that merely contains the name is not claude-nine.
  assert.equal(detectHarness({ CLAUDE_CONFIG_DIR: '/home/x/.claude-nine/other' }), 'unknown');
});

test('convene --sample --harness deepseek posts exactly {sample, harness}', async () => {
  const f = fakeFetch(202, ACCEPTED);
  const c = capture();
  const code = await runConvene(['--sample', '--harness', 'deepseek'], { fetchImpl: f.fetchImpl, env: NINE, io: c.io });
  assert.equal(code, 0);
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].url, 'http://127.0.0.1:8787/api/council/convene');
  assert.equal(f.calls[0].method, 'POST');
  assert.deepEqual(f.calls[0].body, { sample: true, harness: 'deepseek' });
  const out = c.out();
  for (const s of ['sess-1', 'deepseek-configured', 'deepseek-v4.1-flash', 'client_default']) assert.ok(out.includes(s), s);
  assert.ok(out.includes('http://127.0.0.1:8787/council/sess-1'));
  assert.ok(out.includes('http://127.0.0.1:8787/api/council/sessions/sess-1/events'));
});

test('convene with no harness flag sends the detected harness', async () => {
  for (const [env, want] of [
    [NINE, 'claude-nine'],
    [CODE, 'claude-code'],
    [{}, 'unknown'],
  ] as const) {
    const f = fakeFetch(202, ACCEPTED);
    const code = await runConvene(['--sample'], { fetchImpl: f.fetchImpl, env, io: capture().io });
    assert.equal(code, 0);
    assert.deepEqual(f.calls[0].body, { sample: true, harness: want });
  }
});

test('convene passes --route, --model and --mode through verbatim', async () => {
  const f = fakeFetch(202, ACCEPTED);
  await runConvene(['--sample', '--route', 'my-route', '--model', 'Some/Model-9', '--mode', 'quick'], {
    fetchImpl: f.fetchImpl,
    env: {},
    io: capture().io,
  });
  assert.equal(f.calls[0].body?.route_id, 'my-route');
  assert.equal(f.calls[0].body?.model, 'Some/Model-9');
  assert.equal(f.calls[0].body?.mode, 'quick');
});

test('convene --brief and --fresh-facts files are sent; origin comes from env then flag', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'cli-convene-'));
  const brief = { decision: 'x' };
  const facts = [{ claim: 'c', url: 'https://example.com/a', title: null, retrieved_at: '2026-10-19T00:00:00Z' }];
  writeFileSync(join(dir, 'brief.json'), JSON.stringify(brief));
  writeFileSync(join(dir, 'facts.json'), JSON.stringify(facts));
  const f = fakeFetch(202, { ...ACCEPTED, sample: false });
  const c = capture();
  const code = await runConvene(['--brief', join(dir, 'brief.json'), '--fresh-facts', join(dir, 'facts.json'), '--json'], {
    fetchImpl: f.fetchImpl,
    env: { WISE_ELDERS_SERVICE_ORIGIN: 'http://127.0.0.1:9999/' },
    io: c.io,
  });
  assert.equal(code, 0);
  assert.equal(f.calls[0].url, 'http://127.0.0.1:9999/api/council/convene');
  assert.deepEqual(f.calls[0].body?.brief, brief);
  assert.deepEqual(f.calls[0].body?.fresh_facts, facts);
  assert.equal(JSON.parse(c.out()).events_url, 'http://127.0.0.1:9999/api/council/sessions/sess-1/events');

  const g = fakeFetch(202, ACCEPTED);
  await runConvene(['--sample', '--origin', 'http://127.0.0.1:1234'], {
    fetchImpl: g.fetchImpl,
    env: { WISE_ELDERS_SERVICE_ORIGIN: 'http://127.0.0.1:9999' },
    io: capture().io,
  });
  assert.equal(g.calls[0].url, 'http://127.0.0.1:1234/api/council/convene');
});

test('convene: a 503 COMPOSITION_NOT_READY refusal prints code and recovery, exit 3', async () => {
  const f = fakeFetch(503, {
    code: 'COMPOSITION_NOT_READY',
    detail: { unbound: ['material_catalog'] },
    recovery: 'Bind the missing services, then retry.',
  });
  const c = capture();
  const code = await runConvene(['--sample'], { fetchImpl: f.fetchImpl, env: {}, io: c.io });
  assert.equal(code, 3);
  assert.equal(c.out(), '');
  assert.ok(c.err().includes('COMPOSITION_NOT_READY'));
  assert.ok(c.err().includes('material_catalog'));
  assert.ok(c.err().includes('Bind the missing services, then retry.'));

  const j = capture();
  await runConvene(['--sample', '--json'], { fetchImpl: f.fetchImpl, env: {}, io: j.io });
  const env = JSON.parse(j.err());
  assert.equal(env.error.code, 'COMPOSITION_NOT_READY');
  assert.equal(env.error.action, 'Bind the missing services, then retry.');
});

test('convene: a refusal with a plain-English summary prints the summary, not raw JSON', async () => {
  const f = fakeFetch(503, {
    code: 'COMPOSITION_NOT_READY',
    detail: { unbound: ['material_catalog'], summary: 'the elder catalog is not bound yet' },
    recovery: 'Bind the missing services, then retry.',
  });
  const c = capture();
  await runConvene(['--sample'], { fetchImpl: f.fetchImpl, env: {}, io: c.io });
  assert.ok(c.err().includes('the elder catalog is not bound yet'));
  assert.ok(!c.err().includes('"unbound"'));
});

test('convene: connection refused is SERVICE_UNREACHABLE naming the origin tried', async () => {
  const fetchImpl = (async () => {
    throw Object.assign(new TypeError('fetch failed'), { cause: { code: 'ECONNREFUSED' } });
  }) as unknown as typeof fetch;
  const c = capture();
  const code = await runConvene(['--sample', '--origin', 'http://127.0.0.1:4'], { fetchImpl, env: {}, io: c.io });
  assert.equal(code, 3);
  assert.ok(c.err().includes('SERVICE_UNREACHABLE'));
  assert.ok(c.err().includes('http://127.0.0.1:4'));
  assert.ok(c.err().includes('ECONNREFUSED'));
});

test('convene: bad flags are usage errors (exit 2) and send nothing', async () => {
  for (const args of [[], ['--sample', '--brief', 'x.json'], ['--sample', '--harness', 'gpt'], ['--sample', '--bogus', '1']]) {
    const f = fakeFetch(202, ACCEPTED);
    const c = capture();
    const code = await runConvene(args, { fetchImpl: f.fetchImpl, env: {}, io: c.io });
    assert.equal(code, 2, args.join(' '));
    assert.equal(f.calls.length, 0);
  }
  const dir = mkdtempSync(join(tmpdir(), 'cli-convene-'));
  writeFileSync(join(dir, 'facts.json'), JSON.stringify([{ claim: 'no url' }]));
  const f = fakeFetch(202, ACCEPTED);
  const code = await runConvene(['--sample', '--fresh-facts', join(dir, 'facts.json')], {
    fetchImpl: f.fetchImpl,
    env: {},
    io: capture().io,
  });
  assert.equal(code, 2);
  assert.equal(f.calls.length, 0);
});

test('routes --json prints the service JSON unchanged', async () => {
  const body = {
    routes: [{ route_id: 'claude-configured', provider_slug: 'claude', kind: 'harness', composable: true, failure_code: null, default_for: ['claude-code'] }],
    harness_defaults: { 'claude-code': { route_id: 'claude-configured', model: 'sonnet' } },
  };
  const f = fakeFetch(200, body);
  const c = capture();
  const code = await runRoutes(['--json'], { fetchImpl: f.fetchImpl, env: {}, io: c.io });
  assert.equal(code, 0);
  assert.equal(f.calls[0].url, 'http://127.0.0.1:8787/api/council/routes');
  assert.equal(f.calls[0].method, 'GET');
  assert.deepEqual(JSON.parse(c.out()), body);

  const h = capture();
  await runRoutes([], { fetchImpl: f.fetchImpl, env: {}, io: h.io });
  assert.ok(h.out().includes('claude-configured'));
  assert.ok(h.out().includes('claude-code: claude-configured / sonnet'));
});

test('dispatcher routes the new commands to the service client', async () => {
  const c = capture();
  // Nothing listens on port 1: the dispatcher must reach the client and map the refusal.
  const code = await runCli(['routes', '--origin', 'http://127.0.0.1:1'], c.io);
  assert.equal(code, 3);
  assert.ok(c.err().includes('SERVICE_UNREACHABLE'));
  const u = capture();
  assert.equal(await runCli([], u.io), 0);
  assert.ok(u.out().includes('convene'));
});
