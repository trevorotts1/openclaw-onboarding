/**
 * CTR-101 gap C: every successful new or existing-session result carries
 * the DURABLE chamber URL, the supported invocation opens it on a desktop
 * box, and a read stays a read (no probe, no new request, no question).
 *
 * A durable origin is the one the box already recorded: the shim/env value
 * or the service's own service.json public_origin (written only after a
 * verified probe). Nothing here probes the network or launches a browser:
 * every opener is an injected recorder.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { runConvene } from '../src/cli/convene.js';

const PUBLIC = 'https://qcbox-council.example.com';

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

function temp(label: string): string {
  return mkdtempSync(join(tmpdir(), `ctr101-chamber-${label}-`));
}

function capture(): { io: CliIo; out: () => string; err: () => string } {
  let out = '';
  let err = '';
  return { io: { out: (t) => (out += t), err: (t) => (err += t) }, out: () => out, err: () => err };
}

function fakeFetch(replies: unknown[]): { fetchImpl: typeof fetch; calls: Array<{ url: string; method: string; body: Record<string, unknown> | null }> } {
  const calls: Array<{ url: string; method: string; body: Record<string, unknown> | null }> = [];
  let index = 0;
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    calls.push({
      url: String(url),
      method: init?.method ?? 'GET',
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : null,
    });
    const reply = replies[Math.min(index, replies.length - 1)];
    index += 1;
    return new Response(typeof reply === 'string' ? reply : JSON.stringify(reply), { status: 202 });
  }) as typeof fetch;
  return { fetchImpl, calls };
}

function serviceJson(publicOrigin: string | null): string {
  const dir = temp('svcjson');
  const path = join(dir, 'service.json');
  writeFileSync(path, JSON.stringify({ schema: 'council-service/v1', public_origin: publicOrigin }));
  return path;
}

test('convene: the service record public_origin is the durable chamber_url, with no probe fetch', async () => {
  const f = fakeFetch([ACCEPTED]);
  const c = capture();
  const code = await runConvene(['--sample', '--json'], {
    fetchImpl: f.fetchImpl,
    env: { WISE_ELDERS_SERVICE_JSON: serviceJson(PUBLIC), COUNCIL_CHAMBER_GUI: '0' } as NodeJS.ProcessEnv,
    io: c.io,
  });
  assert.equal(code, 0, c.err());
  assert.equal(JSON.parse(c.out()).chamber_url, `${PUBLIC}/chamber/#session=sess-1`);
  // Exactly one call: the convene POST. The durable record is trusted, not
  // re-probed, so convene never spends a request discovering its own link.
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].method, 'POST');
});

test('convene: a desktop session opens the same URL once; --no-open opens nothing', async () => {
  const opened: string[] = [];
  const f1 = fakeFetch([ACCEPTED]);
  const code1 = await runConvene(['--sample'], {
    fetchImpl: f1.fetchImpl,
    env: { WISE_ELDERS_SERVICE_JSON: serviceJson(PUBLIC), COUNCIL_CHAMBER_GUI: '1' } as NodeJS.ProcessEnv,
    io: capture().io,
    openUrl: (url) => opened.push(url),
  });
  assert.equal(code1, 0);
  assert.deepEqual(opened, [`${PUBLIC}/chamber/#session=sess-1`]);

  opened.length = 0;
  const f2 = fakeFetch([ACCEPTED]);
  const code2 = await runConvene(['--sample', '--no-open'], {
    fetchImpl: f2.fetchImpl,
    env: { WISE_ELDERS_SERVICE_JSON: serviceJson(PUBLIC), COUNCIL_CHAMBER_GUI: '1' } as NodeJS.ProcessEnv,
    io: capture().io,
    openUrl: (url) => opened.push(url),
  });
  assert.equal(code2, 0);
  assert.deepEqual(opened, []);
});

test('convene: a headless box opens nothing and still prints the chamber link', async () => {
  const opened: string[] = [];
  const f = fakeFetch([ACCEPTED]);
  const c = capture();
  const code = await runConvene(['--sample'], {
    fetchImpl: f.fetchImpl,
    env: { WISE_ELDERS_SERVICE_JSON: serviceJson(PUBLIC), COUNCIL_CHAMBER_GUI: '0' } as NodeJS.ProcessEnv,
    io: c.io,
    openUrl: (url) => opened.push(url),
  });
  assert.equal(code, 0);
  assert.deepEqual(opened, []);
  assert.ok(c.out().includes(`Open the Roast Room: ${PUBLIC}/chamber/#session=sess-1`));
});

test('convene: a completed prior session is refused, never printed as the new result', async () => {
  const opened: string[] = [];
  const f = fakeFetch([{ ...ACCEPTED, state: 'COMPLETED' }]);
  const c = capture();
  const code = await runConvene(['--sample', '--json'], {
    fetchImpl: f.fetchImpl,
    env: { WISE_ELDERS_SERVICE_JSON: serviceJson(PUBLIC), COUNCIL_CHAMBER_GUI: '1' } as NodeJS.ProcessEnv,
    io: c.io,
    openUrl: (url) => opened.push(url),
  });
  assert.equal(code, 3);
  assert.equal(JSON.parse(c.err()).error.code, 'CONVENE_NOT_NEW');
  assert.equal(c.out(), '');
  assert.deepEqual(opened, []);
});

test('convene: each explicit new request creates a NEW session, never the prior verdict', async () => {
  const replies = [
    { ...ACCEPTED, session_id: 'sess-a' },
    { ...ACCEPTED, session_id: 'sess-b' },
  ];
  const f = fakeFetch(replies);
  const env = { WISE_ELDERS_PUBLIC_ORIGIN: PUBLIC, COUNCIL_CHAMBER_GUI: '0' } as NodeJS.ProcessEnv;

  const first = capture();
  assert.equal(await runConvene(['--sample', '--json'], { fetchImpl: f.fetchImpl, env, io: first.io }), 0);
  const second = capture();
  assert.equal(await runConvene(['--sample', '--json'], { fetchImpl: f.fetchImpl, env, io: second.io }), 0);

  const a = JSON.parse(first.out());
  const b = JSON.parse(second.out());
  assert.equal(a.session_id, 'sess-a');
  assert.equal(b.session_id, 'sess-b');
  assert.notEqual(a.session_id, b.session_id);
  assert.equal(b.chamber_url, `${PUBLIC}/chamber/#session=sess-b`);
  // A new request never asks the service to resume anything.
  for (const call of f.calls) {
    assert.equal(call.method, 'POST');
    assert.equal(call.body?.session_id, undefined);
    assert.equal(call.body?.resume, undefined);
  }
});

test('existing-session read: status carries the durable chamber_url and starts nothing', async () => {
  const home = temp('home');
  const dataDir = temp('store');
  const env = { HOME: home } as NodeJS.ProcessEnv;

  const seeded = capture();
  assert.equal(await runCli(['create', '--sample', '--json', '--data-dir', dataDir], seeded.io, { env }), 0);
  const sessionId = JSON.parse(seeded.out()).session_id as string;

  const sj = serviceJson(PUBLIC);
  const read = capture();
  const code = await runCli(['status', sessionId, '--json', '--data-dir', dataDir], read.io, {
    env: { ...env, WISE_ELDERS_SERVICE_JSON: sj } as NodeJS.ProcessEnv,
  });
  assert.equal(code, 0, read.err());
  const body = JSON.parse(read.out());
  assert.equal(body.session_id, sessionId);
  assert.equal(body.chamber_url, `${PUBLIC}/chamber/#session=${sessionId}`);
  // No probe, no POST, no question: the human read is one short block.
  const human = capture();
  assert.equal(
    await runCli(['status', sessionId, '--data-dir', dataDir], human.io, {
      env: { ...env, WISE_ELDERS_SERVICE_JSON: sj } as NodeJS.ProcessEnv,
    }),
    0,
  );
  assert.ok(human.out().includes(`chamber_url: ${PUBLIC}/chamber/#session=${sessionId}`));
  assert.ok(!human.out().includes('?'), 'a read asks no question');
});

test('existing-session read: no durable origin means no chamber_url, never a guess', async () => {
  const home = temp('home');
  const dataDir = temp('store');
  const env = { HOME: home } as NodeJS.ProcessEnv;
  const seeded = capture();
  assert.equal(await runCli(['create', '--sample', '--json', '--data-dir', dataDir], seeded.io, { env }), 0);
  const sessionId = JSON.parse(seeded.out()).session_id as string;

  const read = capture();
  const code = await runCli(['status', sessionId, '--json', '--data-dir', dataDir], read.io, { env });
  assert.equal(code, 0, read.err());
  assert.equal('chamber_url' in JSON.parse(read.out()), false);
});
