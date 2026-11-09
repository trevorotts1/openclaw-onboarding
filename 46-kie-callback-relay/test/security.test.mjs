/**
 * Security regression suite for Skill 46 (kie-callback-relay).
 *
 * Covers the three security-critical components with STUBBED fetch / KV -- no
 * network, no live Kie, no live Worker. Run with: node test/security.test.mjs
 * (wired into qc-kie-callback-relay.sh).
 *
 * What is proven here:
 *   Worker (worker/src/index.js)
 *     - Kie HMAC signature verify + replay-window rejection (fix E)
 *     - /kv-read: 401 (bad bearer), 403 (bad preimage), 200 found (good) with the
 *       secret HMAC stripped from the response (fixes B/C/F/G)
 *     - per-client credential derivation: a token derived for client X is rejected
 *       for client Y (fix F)
 *     - preimage is read from the X-Kie-Preimage header, not a query param (fix G)
 *   box-kv-poller.js
 *     - _validatePerTaskSecret is an EXACT submitId match, not "any non-empty" (fix 34)
 *     - code 200 + zero allowlisted URLs => 'failed'/allowlist-rejected (fix 35)
 *     - callbacksEnabled=false skips the KV phase entirely (fix 33)
 *   kie-slide-submitter.js
 *     - constructor does NOT require Worker secrets (fix 33)
 *     - resume dedup: prefers the taskId row, marks the orphan 'superseded' (fix 37i)
 */

import { createHmac } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const require = createRequire(import.meta.url);
const here    = path.dirname(fileURLToPath(import.meta.url));
const skillDir = path.resolve(here, '..');

const workerMod = await import(path.join(skillDir, 'worker/src/index.js'));
const worker    = workerMod.default;
const { KieKvPoller }      = require(path.join(skillDir, 'box-kv-poller.js'));
const { KieSlideSubmitter, normalizeAdapterTask } = require(path.join(skillDir, 'kie-slide-submitter.js'));

// ── tiny assert harness ───────────────────────────────────────────────────────
let passed = 0;
const failures = [];
function ok(cond, msg) {
  if (cond) { passed++; console.log(`  ok  - ${msg}`); }
  else { failures.push(msg); console.error(`  FAIL - ${msg}`); }
}
async function section(name, fn) {
  console.log(`\n# ${name}`);
  try { await fn(); }
  catch (err) { failures.push(`${name}: threw ${err.stack || err}`); console.error(`  FAIL - threw: ${err.message}`); }
}

// ── crypto helpers that mirror the Worker's hmacHex/derivePerClient exactly ────
const hmacHex = (msg, key) => createHmac('sha256', key).update(msg).digest('hex');
const kieSig  = (taskId, ts, key) => createHmac('sha256', key).update(`${taskId}.${ts}`).digest('base64');

// ── in-memory KV stub (matches the subset the Worker uses) ─────────────────────
function makeKV(seed = {}) {
  const store = new Map(Object.entries(seed));
  return {
    store,
    async get(k) { return store.has(k) ? store.get(k) : null; },
    async put(k, v) { store.set(k, v); },
  };
}
function makeCtx() {
  const promises = [];
  return { ctx: { waitUntil: (p) => promises.push(p) }, settle: () => Promise.all(promises) };
}

const MASTER_CB    = 'master-callback-key-fixture';
const MASTER_KVR   = 'master-kvread-token-fixture';
const WEBHOOK_KEY  = 'kie-webhook-hmac-key-fixture';
const SLUG         = 'client-alpha';

// =============================================================================
await section('Worker: /healthz reports version 2.0.4', async () => {
  const res = await worker.fetch(new Request('https://w/healthz'), {}, makeCtx().ctx);
  ok(res.status === 200, 'healthz -> 200');
  const body = await res.json();
  ok(body.version === '2.0.4', `healthz version == 2.0.4 (got ${body.version})`);
});

await section('Worker: /kv-read auth + preimage (fixes B/C/F/G)', async () => {
  const submitId    = 'a'.repeat(32);
  const perClientCb = hmacHex(SLUG, MASTER_CB);          // fix F derived callback key
  const perClientTk = hmacHex(SLUG, MASTER_KVR);         // fix F derived bearer token
  const preimage    = 'per-task-secret-plaintext';
  const storedHmac  = hmacHex(preimage, perClientCb);    // what the box put as h=

  const env = {
    KIE_CALLBACK_HMAC_KEY: MASTER_CB,
    KVREAD_TOKEN:          MASTER_KVR,
    KIE_CALLBACK_KV: makeKV({
      [`result:${SLUG}:${submitId}`]: JSON.stringify({
        taskId: 'task-1', clientSlug: SLUG, submitId, code: 200,
        resultUrls: ['https://tempfile.aiquickdraw.com/x.png'],
        perTaskSecretHmac: storedHmac, receivedAt: 'now',
      }),
    }),
  };
  const base = `https://w/kv-read?c=${SLUG}&j=${submitId}`;

  // missing preimage header -> 400
  let res = await worker.fetch(new Request(base, { headers: { Authorization: `Bearer ${perClientTk}` } }), env, makeCtx().ctx);
  ok(res.status === 400, 'missing X-Kie-Preimage header -> 400');

  // wrong bearer -> 401
  res = await worker.fetch(new Request(base, { headers: { Authorization: 'Bearer nope', 'X-Kie-Preimage': preimage } }), env, makeCtx().ctx);
  ok(res.status === 401, 'wrong bearer -> 401');

  // token derived for a DIFFERENT client -> 401 (fix F blast-radius)
  const foreignTk = hmacHex('client-beta', MASTER_KVR);
  res = await worker.fetch(new Request(base, { headers: { Authorization: `Bearer ${foreignTk}`, 'X-Kie-Preimage': preimage } }), env, makeCtx().ctx);
  ok(res.status === 401, 'another client\'s derived token -> 401 (no cross-client access)');

  // right bearer, wrong preimage -> 403
  res = await worker.fetch(new Request(base, { headers: { Authorization: `Bearer ${perClientTk}`, 'X-Kie-Preimage': 'wrong-secret' } }), env, makeCtx().ctx);
  ok(res.status === 403, 'good bearer + wrong preimage -> 403');

  // right bearer, right preimage -> 200 found, secret hash stripped
  res = await worker.fetch(new Request(base, { headers: { Authorization: `Bearer ${perClientTk}`, 'X-Kie-Preimage': preimage } }), env, makeCtx().ctx);
  ok(res.status === 200, 'good bearer + good preimage -> 200');
  const body = await res.json();
  ok(body.found === true, 'result found');
  ok(body.result && body.result.perTaskSecretHmac === undefined, 'perTaskSecretHmac stripped from response (fix C)');
  ok(body.result.submitId === submitId, 'returned submitId matches');
});

await section('Worker: /cb signature verify, replay, validator (fixes D/E/F)', async () => {
  const submitId    = 'b'.repeat(32);
  const perClientCb = hmacHex(SLUG, MASTER_CB);
  const validator   = hmacHex(`${SLUG}:${submitId}`, perClientCb);      // s=
  const secretHmac  = hmacHex('the-secret', perClientCb);               // h=
  const taskId      = 'task-cb-1';
  const now         = Math.floor(Date.now() / 1000);

  const mkEnv = () => ({
    KIE_WEBHOOK_HMAC_KEY:  WEBHOOK_KEY,
    KIE_CALLBACK_HMAC_KEY: MASTER_CB,
    KVREAD_TOKEN:          MASTER_KVR,
    KIE_CALLBACK_KV:       makeKV(),
  });
  const cbUrl = `https://w/cb?c=${SLUG}&j=${submitId}&s=${validator}&h=${secretHmac}`;
  const payload = JSON.stringify({ code: 200, msg: 'ok', data: { taskId, info: { result_urls: ['https://tempfile.aiquickdraw.com/y.png'] } } });
  const mkReq = (ts, sig) => new Request(cbUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-webhook-timestamp': String(ts), 'x-webhook-signature': sig },
    body: payload,
  });

  // valid signature + fresh timestamp -> written to KV
  let env = mkEnv();
  let { ctx, settle } = makeCtx();
  let res = await worker.fetch(mkReq(now, kieSig(taskId, now, WEBHOOK_KEY)), env, ctx);
  ok(res.status === 200, 'valid /cb -> 200');
  await settle();
  ok(env.KIE_CALLBACK_KV.store.has(`result:${SLUG}:${submitId}`), 'valid /cb writes result to KV');
  const stored = JSON.parse(env.KIE_CALLBACK_KV.store.get(`result:${SLUG}:${submitId}`));
  ok(stored.perTaskSecretHmac === secretHmac, 'stored perTaskSecretHmac == h= (never the plaintext)');

  // bad signature -> dropped (not written)
  env = mkEnv(); ({ ctx, settle } = makeCtx());
  res = await worker.fetch(mkReq(now, 'AAAAbadsigAAAA=='), env, ctx);
  await settle();
  ok(!env.KIE_CALLBACK_KV.store.has(`result:${SLUG}:${submitId}`), 'bad Kie signature -> not written (fix E)');

  // replay: timestamp 10 minutes old -> dropped
  const old = now - 600;
  env = mkEnv(); ({ ctx, settle } = makeCtx());
  res = await worker.fetch(mkReq(old, kieSig(taskId, old, WEBHOOK_KEY)), env, ctx);
  await settle();
  ok(!env.KIE_CALLBACK_KV.store.has(`result:${SLUG}:${submitId}`), 'stale timestamp -> replay-dropped (fix E)');

  // wrong callback validator (s=) -> dropped
  env = mkEnv(); ({ ctx, settle } = makeCtx());
  const badReq = new Request(`https://w/cb?c=${SLUG}&j=${submitId}&s=deadbeef&h=${secretHmac}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-webhook-timestamp': String(now), 'x-webhook-signature': kieSig(taskId, now, WEBHOOK_KEY) },
    body: payload,
  });
  res = await worker.fetch(badReq, env, ctx);
  await settle();
  ok(!env.KIE_CALLBACK_KV.store.has(`result:${SLUG}:${submitId}`), 'wrong callback validator -> dropped (fix D)');
});

// =============================================================================
function tmpWorkspace() { return fs.mkdtempSync(path.join(os.tmpdir(), 'kie-test-')); }

// F21 item 11: paid-job state lives under the DURABLE root the shared resolver returns
// (<root>/data/kie-jobs/<scope>/{registry,index,done}), never under an arbitrary working
// folder. Each test passes its temp dir as the explicit `dataRoot` pin and derives the
// expected location from the SAME shape the resolver prints -- no `.kie` path is asserted
// any more, because that transient layout is exactly what the fix removed.
const kieState = (root) => path.join(root, 'data', 'kie-jobs', SLUG);

await section('box-kv-poller: _validatePerTaskSecret is exact submitId match (fix 34)', async () => {
  const ws = tmpWorkspace();
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', dataRoot: ws, kvReadToken: 'tk' });
  ok(p._validatePerTaskSecret({ submitId: 'want-this' }, 'want-this') === true, 'matching submitId -> true');
  ok(p._validatePerTaskSecret({ submitId: 'other-task' }, 'want-this') === false, 'different submitId -> false (confused-deputy blocked)');
  ok(p._validatePerTaskSecret({ submitId: '' }, 'want-this') === false, 'empty submitId -> false');
});

await section('box-kv-poller: code 200 + no allowlisted URLs -> failed (fix 35)', async () => {
  const ws = tmpWorkspace();
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', dataRoot: ws, kvReadToken: 'tk', pollIntervalMs: 5 });
  p._pollKv = async () => ({ submitId: 'sub-1', code: 200, resultUrls: ['https://evil.example.com/x.png'], receivedAt: 'now' });
  const marker = await p.waitForTask('sub-1', 'task-x', 'secret', { timeoutMs: 200 });
  ok(marker.status === 'failed', `code 200 w/ only non-allowlisted URLs -> failed (got ${marker.status})`);
  ok(marker.reason === 'allowlist-rejected', 'reason == allowlist-rejected');
  ok(Array.isArray(marker.resultUrls) && marker.resultUrls.length === 0, 'no safe URLs survive');
});

// ── ONB-46-001: the Kie recordInfo FALLBACK must obey the SAME outcome rule ────
// Helper: a poller whose callback never lands, so waitForTask always reaches the
// Phase-2 Kie recordInfo fallback, with both waits collapsed to ~1ms.
function fallbackPoller(ws, recordInfoBody) {
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', dataRoot: ws,
                              kvReadToken: 'tk', pollIntervalMs: 1 });
  p._pollKv = async () => null;                                   // callback never arrives
  p._sleep  = (ms) => new Promise(r => setTimeout(r, Math.min(ms, 1)));
  p._fetch  = async () => ({ json: async () => recordInfoBody });
  return p;
}

await section('box-kv-poller: fallback "success" with ZERO urls -> failed, NO done marker (ONB-46-001)', async () => {
  const ws = tmpWorkspace();
  const p  = fallbackPoller(ws, { code: 200, data: { state: 'success', resultJson: { images: [] } } });
  const marker = await p.waitForTask('sub-empty', 'task-empty', 'secret',
                                     { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.source === 'kie-poll', `resolved via the Kie fallback (got ${marker.source})`);
  ok(marker.status === 'failed', `zero downloadable URLs -> failed, never 'done' (got ${marker.status})`);
  ok(Array.isArray(marker.resultUrls) && marker.resultUrls.length === 0, 'no URLs on the marker');
  ok(marker.rawUrlCount === 0, 'rawUrlCount records that the provider carried nothing');
  const onDisk = JSON.parse(fs.readFileSync(path.join(kieState(ws), 'done', 'task-empty.json'), 'utf8'));
  ok(onDisk.status !== 'done', `the DURABLE marker on disk is not 'done' (got ${onDisk.status})`);
});

await section('box-kv-poller: fallback success with only NON-allowlisted urls -> failed (ONB-46-001)', async () => {
  const ws = tmpWorkspace();
  const p  = fallbackPoller(ws, { code: 200, data: { state: 'success',
              resultJson: { images: [{ url: 'https://evil.example.com/x.png' }] } } });
  const marker = await p.waitForTask('sub-bad', 'task-bad', 'secret',
                                     { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'failed', `all URLs dropped by the allowlist -> failed (got ${marker.status})`);
  ok(marker.reason === 'allowlist-rejected', 'reason == allowlist-rejected (same rule as the KV path)');
  ok(marker.rawUrlCount === 1, 'rawUrlCount reports the dropped URL so the mismatch is diagnosable');
});

await section('box-kv-poller: fallback success WITH a real url still -> done (no over-fail)', async () => {
  const ws = tmpWorkspace();
  const p  = fallbackPoller(ws, { code: 200, data: { state: 'success',
              resultJson: { images: [{ url: 'https://tempfile.aiquickdraw.com/ok.png' }] } } });
  const marker = await p.waitForTask('sub-ok', 'task-ok', 'secret',
                                     { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'done', `a real allowlisted URL still resolves 'done' (got ${marker.status})`);
  ok(marker.resultUrls.length === 1, 'the downloadable URL survives onto the marker');
  const onDisk = JSON.parse(fs.readFileSync(path.join(kieState(ws), 'done', 'task-ok.json'), 'utf8'));
  ok(onDisk.status === 'done', 'done marker written as before for a real result');
});

await section('box-kv-poller: KV path still resolves a real url as done (no regression)', async () => {
  const ws = tmpWorkspace();
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', dataRoot: ws,
                              kvReadToken: 'tk', pollIntervalMs: 1 });
  p._pollKv = async () => ({ submitId: 'sub-kv', code: 200,
                             resultUrls: ['https://tempfile.aiquickdraw.com/kv.png'], receivedAt: 'now' });
  const marker = await p.waitForTask('sub-kv', 'task-kv', 'secret', { timeoutMs: 200 });
  ok(marker.status === 'done', `KV path with an allowlisted URL -> done (got ${marker.status})`);
  ok(marker.source === 'callback-kv', 'resolved via the callback-KV path');
});

// =============================================================================
// Real KIE result shapes (live-probed 2026-10-05; KIE kie-models contract):
//   Market success: data.state 'success', data.resultJson is a JSON STRING
//   '{"resultUrls":[...]}', data.response is the parsed copy.
//   Suno audio success: tracks at response.data[].audio_url.
const MARKET_URL = 'https://tempfile.aiquickdraw.com/m/real-market.png';
const marketData = () => ({ taskId: 'task-m', model: 'gpt-image-2-text-to-image', state: 'success', successFlag: 1,
  failCode: null, failMsg: null,
  resultJson: JSON.stringify({ resultUrls: [MARKET_URL] }), response: { resultUrls: [MARKET_URL] } });
const SUNO_URL = 'https://tempfile.aiquickdraw.com/s/track1.mp3';
const sunoData = () => ({ taskId: 'task-s', state: 'success', successFlag: 1,
  response: { data: [{ audio_url: SUNO_URL, stream_audio_url: 'https://evil.example.com/stream', title: 't', duration: 30 }] } });

await section('box-kv-poller: REAL Market shape (resultJson string + response.resultUrls) -> done', async () => {
  // both fields present
  let p = fallbackPoller(tmpWorkspace(), { code: 200, data: marketData() });
  let marker = await p.waitForTask('sub-m1', 'task-m1', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'done', `Market success -> done (got ${marker.status})`);
  ok(marker.resultUrls.length === 1 && marker.resultUrls[0] === MARKET_URL, 'resultJson + response de-duplicated to one URL');
  // only the resultJson STRING (no response copy)
  const d = marketData(); delete d.response;
  p = fallbackPoller(tmpWorkspace(), { code: 200, data: d });
  marker = await p.waitForTask('sub-m2', 'task-m2', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'done' && marker.resultUrls[0] === MARKET_URL, 'resultJson string alone parses to resultUrls');
  // only response.resultUrls (no resultJson)
  const d2 = marketData(); delete d2.resultJson;
  p = fallbackPoller(tmpWorkspace(), { code: 200, data: d2 });
  marker = await p.waitForTask('sub-m3', 'task-m3', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'done' && marker.resultUrls[0] === MARKET_URL, 'response.resultUrls alone is accepted');
  // legacy images:[{url}] still works
  p = fallbackPoller(tmpWorkspace(), { code: 200, data: { state: 'success', resultJson: { images: [{ url: MARKET_URL }] } } });
  marker = await p.waitForTask('sub-m4', 'task-m4', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'done', 'legacy images:[{url}] still resolves done');
  // Market success whose resultUrls are on a foreign host -> still failed (allowlist stays strict)
  p = fallbackPoller(tmpWorkspace(), { code: 200, data: { state: 'success',
        resultJson: JSON.stringify({ resultUrls: ['https://evil.example.com/x.png'] }) } });
  marker = await p.waitForTask('sub-m5', 'task-m5', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'failed' && marker.reason === 'allowlist-rejected', 'foreign-host Market URL -> failed/allowlist-rejected');
});

await section('box-kv-poller: images array with null/garbage items does not throw (QC follow-up)', async () => {
  let p = fallbackPoller(tmpWorkspace(), { code: 200, data: { state: 'success', resultJson: { images: [null] } } });
  let marker = await p.waitForTask('sub-n1', 'task-n1', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'failed' && marker.source === 'kie-poll', `images:[null] -> failed via the poll path, not a swallowed TypeError (got ${marker.status}/${marker.source})`);
  p = fallbackPoller(tmpWorkspace(), { code: 200, data: { state: 'success',
        resultJson: { images: [null, undefined, 5, { url: MARKET_URL }] } } });
  marker = await p.waitForTask('sub-n2', 'task-n2', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'done' && marker.resultUrls.length === 1 && marker.resultUrls[0] === MARKET_URL, 'null items skipped, the real URL still resolves done');
});

await section('box-kv-poller: all-null images array falls through to resultUrls and completes (no hang)', async () => {
  const p = fallbackPoller(tmpWorkspace(), { code: 200, data: { state: 'success',
        resultJson: { images: [null, {}], resultUrls: [MARKET_URL] } } });
  const guard = new Promise((_, rej) => setTimeout(() => rej(new Error('poller hung past 5s')), 5000));
  const marker = await Promise.race([
    p.waitForTask('sub-f1', 'task-f1', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 }), guard]);
  ok(marker.status === 'done' && marker.resultUrls[0] === MARKET_URL, `all-null images + resultUrls -> done (got ${marker.status})`);
  ok(marker.source === 'kie-poll', 'completed through the poll path within the guard');
});

await section('box-kv-poller: Suno shape (response.data[].audio_url) -> done', async () => {
  const p = fallbackPoller(tmpWorkspace(), { code: 200, data: sunoData() });
  const marker = await p.waitForTask('sub-s1', 'task-s1', 'secret', { timeoutMs: 5, kieApiKey: 'k', fallbackPollIntervalMs: 1 });
  ok(marker.status === 'done', `Suno success -> done (got ${marker.status})`);
  ok(marker.resultUrls.length === 1 && marker.resultUrls[0] === SUNO_URL, 'audio_url taken; stream_audio_url not used');
});

await section('box-kv-poller: KV path recovers Market URLs from rawData when an old Worker sent resultUrls: []', async () => {
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', dataRoot: tmpWorkspace(),
                              kvReadToken: 'tk', pollIntervalMs: 1 });
  p._pollKv = async () => ({ submitId: 'sub-kv2', code: 200, resultUrls: [], rawData: marketData(), receivedAt: 'now' });
  const marker = await p.waitForTask('sub-kv2', 'task-kv2', 'secret', { timeoutMs: 200 });
  ok(marker.status === 'done' && marker.resultUrls[0] === MARKET_URL, 'rawData.resultJson recovered on the KV path');
});

await section('box-kv-poller: result-host allowlist stays strict', async () => {
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', dataRoot: tmpWorkspace(), kvReadToken: 'tk' });
  const r = (u) => p._resolveOutcome([u], 200, 't', 'kie-poll').status;
  ok(r('https://tempfile.redpandaai.co/a.png') === 'done', 'tempfile.redpandaai.co allowed');
  ok(r('https://tempfile.aiquickdraw.com/a.png') === 'done', 'tempfile.aiquickdraw.com allowed');
  ok(r('https://file.aiquickdraw.com/v/a.mp4') === 'done', 'file.aiquickdraw.com (documented Veo result host) allowed');
  ok(r('https://file.aiquickdraw.com.evil.com/a.png') === 'failed', 'suffix look-alike host rejected');
  ok(r('https://redpandaai.co/a.png') === 'failed', 'bare redpandaai.co is not allowlisted (exact hosts only)');
  ok(r('https://evil.example.com/a.png') === 'failed', 'foreign host rejected');
});

await section('Worker: /cb stores REAL Market + Suno result URLs (extractResultUrls)', async () => {
  const perClientCb = hmacHex(SLUG, MASTER_CB);
  const now = Math.floor(Date.now() / 1000);
  const run = async (submitId, taskId, data) => {
    const env = { KIE_WEBHOOK_HMAC_KEY: WEBHOOK_KEY, KIE_CALLBACK_HMAC_KEY: MASTER_CB, KVREAD_TOKEN: MASTER_KVR, KIE_CALLBACK_KV: makeKV() };
    const { ctx, settle } = makeCtx();
    const url = `https://w/cb?c=${SLUG}&j=${submitId}&s=${hmacHex(`${SLUG}:${submitId}`, perClientCb)}&h=${hmacHex('x', perClientCb)}`;
    const res = await worker.fetch(new Request(url, { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-webhook-timestamp': String(now), 'x-webhook-signature': kieSig(taskId, now, WEBHOOK_KEY) },
      body: JSON.stringify({ code: 200, msg: 'success', data: { ...data, taskId } }) }), env, ctx);
    await settle();
    return { res, stored: JSON.parse(env.KIE_CALLBACK_KV.store.get(`result:${SLUG}:${submitId}`) || 'null') };
  };
  let out = await run('c'.repeat(32), 'task-cbm', { state: 'success', resultJson: JSON.stringify({ resultUrls: [MARKET_URL] }) });
  ok(out.res.status === 200 && out.stored && out.stored.resultUrls[0] === MARKET_URL, 'Market callback resultJson string -> resultUrls');
  out = await run('d'.repeat(32), 'task-cbr', { state: 'success', response: { resultUrls: [MARKET_URL] } });
  ok(out.stored && out.stored.resultUrls[0] === MARKET_URL, 'Market callback response.resultUrls -> resultUrls');
  out = await run('e'.repeat(32), 'task-cbs', { callbackType: 'complete', data: [{ audio_url: SUNO_URL }] });
  ok(out.stored && out.stored.resultUrls[0] === SUNO_URL, 'Suno callback data[].audio_url -> resultUrls');
  out = await run('f'.repeat(32), 'task-cbl', { info: { result_urls: ['https://tempfile.aiquickdraw.com/legacy.png'] } });
  ok(out.stored && out.stored.resultUrls[0] === 'https://tempfile.aiquickdraw.com/legacy.png', 'legacy info.result_urls unchanged');
});

await section('box-kv-poller: BOTH paths share ONE outcome rule (_resolveOutcome)', async () => {
  const ws = tmpWorkspace();
  const p  = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', dataRoot: ws, kvReadToken: 'tk' });
  ok(typeof p._resolveOutcome === 'function', '_resolveOutcome exists (the single shared check)');
  ok(p._resolveOutcome([], 200, 't', 'kie-poll').status === 'failed', 'empty + code 200 -> failed');
  ok(p._resolveOutcome(undefined, 200, 't', 'kie-poll').status === 'failed', 'missing urls -> failed (never skipped)');
  ok(p._resolveOutcome(['https://tempfile.aiquickdraw.com/a.png'], 200, 't', 'callback-kv').status === 'done',
     'a real allowlisted URL -> done');
  ok(p._resolveOutcome(['https://tempfile.aiquickdraw.com/a.png'], 500, 't', 'callback-kv').status === 'failed',
     'non-200 -> failed even with URLs');
  // The rule has exactly ONE implementation: both call sites must delegate, so a
  // future edit cannot quietly re-inline a second (divergent) copy.
  const src = fs.readFileSync(path.join(skillDir, 'box-kv-poller.js'), 'utf8');
  const delegations = (src.match(/this\._resolveOutcome\(/g) || []).length;
  ok(delegations === 2, `both resolution paths delegate to _resolveOutcome (found ${delegations})`);
  // Exactly ONE executable `status: 'done'` may exist, and it must live INSIDE
  // _resolveOutcome. Comments/JSDoc are stripped first so only real code counts.
  // A second literal anywhere else means a path re-inlined the rule -- which is
  // exactly the ONB-46-001 defect this fix removed.
  const bare      = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '');
  const ruleStart = bare.indexOf('_resolveOutcome(rawUrls');
  const ruleEnd   = bare.indexOf('_extractResultJsonUrls(resultJson) {');
  ok(ruleStart > 0 && ruleEnd > ruleStart, '_resolveOutcome body located in source');
  const literals = [...bare.matchAll(/status:\s*'done'/g)];
  ok(literals.length === 1, `exactly one executable status:'done' literal (found ${literals.length})`);
  ok(literals.length === 1 && literals[0].index > ruleStart && literals[0].index < ruleEnd,
     "the only status:'done' literal lives inside _resolveOutcome");
});

await section('box-kv-poller: callbacksEnabled=false skips KV (fix 33)', async () => {
  const ws = tmpWorkspace();
  // No kvReadToken supplied -> must NOT throw when callbacks disabled.
  let threw = false;
  let p;
  try { p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: '', dataRoot: ws, callbacksEnabled: false }); }
  catch (_) { threw = true; }
  ok(!threw, 'constructor does not require kvReadToken when callbacks disabled');
  let kvCalled = false;
  p._pollKv = async () => { kvCalled = true; return null; };
  const marker = await p.waitForTask('sub-2', 'task-y', null, {}); // no kieApiKey
  ok(kvCalled === false, 'KV phase never runs when callbacks disabled');
  ok(marker.status === 'timeout' && marker.source === 'no-callbacks-no-key', 'returns direct-path marker, not a KV wait');
});

// =============================================================================
await section('kie-slide-submitter: constructor works without Worker secrets (fix 33)', async () => {
  const ws = tmpWorkspace();
  let threw = false;
  try { new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', dataRoot: ws }); }
  catch (_) { threw = true; }
  ok(!threw, 'no callbackHmacKey/kvReadToken required at construction time');
});

await section('kie-slide-submitter: resume dedup prefers taskId, supersedes orphan (fix 37i)', async () => {
  const ws = tmpWorkspace();
  const regDir = path.join(kieState(ws), 'registry');
  fs.mkdirSync(regDir, { recursive: true });
  const label = 'deck1_slide1';
  // orphan (crash before Kie returned): taskId null, older
  const orphan = { submitId: 'orphan-id', label, deckId: 'deck1', slideId: 'slide1', taskId: null, submittedAt: '2026-07-05T00:00:00.000Z' };
  // the real paid task: taskId set, newer
  const real   = { submitId: 'real-id',  label, deckId: 'deck1', slideId: 'slide1', taskId: 'kie-task-99', submittedAt: '2026-07-05T00:00:05.000Z' };
  fs.writeFileSync(path.join(regDir, 'orphan-id.json'), JSON.stringify(orphan));
  fs.writeFileSync(path.join(regDir, 'real-id.json'),   JSON.stringify(real));

  const s = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', dataRoot: ws });
  const byLabel = s._loadRegistryByLabel();
  ok(byLabel[label] && byLabel[label].taskId === 'kie-task-99', 'winner is the row WITH a taskId (no double-submit)');
  const orphanAfter = JSON.parse(fs.readFileSync(path.join(regDir, 'orphan-id.json'), 'utf8'));
  ok(orphanAfter.status === 'superseded', 'orphan row marked superseded on disk');
  ok(orphanAfter.supersededBy === 'real-id', 'orphan records supersededBy the winner');
});

await section('kie-slide-submitter: a durable "done" marker with no file is reconciled to failed (ONB-46-001)', async () => {
  const ws = tmpWorkspace();
  const s  = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', dataRoot: ws });
  ok(typeof s._reconcileDoneStatus === 'function', '_reconcileDoneStatus exists (the single shared rule)');

  const missing = path.join(ws, 'no-such-slide.png');
  ok(s._reconcileDoneStatus('done', missing, 'slide1') === 'failed',
     "a 'done' status with no file on disk -> failed");
  ok(s._reconcileDoneStatus('done', null, 'slide1') === 'failed',
     "a 'done' status with no target path -> failed");

  const real = path.join(ws, 'rendered.png');
  fs.writeFileSync(real, 'png-bytes');
  ok(s._reconcileDoneStatus('done', real, 'slide1') === 'done',
     "a 'done' status with a real file stays done (no over-fail)");
  ok(s._reconcileDoneStatus('failed', real, 'slide1') === 'failed',
     'a failed status is never upgraded by the presence of a file');
});

// =============================================================================
// T0-58 — the RESUME path must reconcile against disk, not against intent.
//
// TIGHTENED (was: a regex counting `this._reconcileDoneStatus(` occurrences in the
// source and asserting the count was 2). That assertion measured the SHAPE OF THE
// TEXT, not the behaviour: it passed whenever two call sites existed, regardless of
// what either one did with the result, and it turned red on a refactor that made the
// rule MORE shared rather than less. It is replaced below by driving submitDeck()
// down BOTH paths and asserting the reported outcome, which is the thing the finding
// is about. QUALITY-CONTROL rule E4: read what a test asserts, not whether it passes.
// =============================================================================
await section('kie-slide-submitter: a RESUMED slide is reconciled against disk (T0-58)', async () => {
  // Drive the resume branch: a registry row with a taskId plus a durable done
  // marker puts the slide into `submitted`, which is the already-resolved path.
  // No new slides are submitted, so no network is touched.
  const seedResume = (doneMarker, { writeFile }) => {
    const ws = tmpWorkspace();
    const target = path.join(ws, 'out', 'slide1.png');
    fs.mkdirSync(path.join(kieState(ws), 'registry'), { recursive: true });
    fs.mkdirSync(path.join(kieState(ws), 'done'), { recursive: true });
    fs.writeFileSync(path.join(kieState(ws), 'registry', 'sub-1.json'), JSON.stringify({
      submitId: 'sub-1', label: 'deck1_slide1', deckId: 'deck1', slideId: 'slide1',
      taskId: 'task-1', targetPath: target, submittedAt: '2026-07-05T00:00:00.000Z'
    }));
    fs.writeFileSync(path.join(kieState(ws), 'done', 'task-1.json'), JSON.stringify(doneMarker));
    if (writeFile) {
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, 'png-bytes');
    }
    const s = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', dataRoot: ws });
    return { s, ws, target,
             slides: [{ deckId: 'deck1', slideId: 'slide1', prompt: 'p', targetPath: target }] };
  };

  // 1. THE FINDING. A durable 'done' marker whose file is absent and which carries
  //    no recoverable URL must NOT be counted complete, and must NOT report a path.
  {
    const { s, slides } = seedResume(
      { status: 'done', resultUrls: [], code: 200 }, { writeFile: false });
    const [r] = await s.submitDeck(slides, { callbackThreshold: 99 });
    ok(r.status === 'failed', "resumed 'done' with no file on disk -> failed (not counted complete)");
    ok(r.localPath === null,
       'resumed slide reports localPath null, not the intended target path');
  }

  // 2. RECOVERY. A durable 'done' marker whose file is absent but which carries a
  //    result URL re-enters the DOWNLOAD path instead of reporting completion.
  {
    const { s, target, slides } = seedResume(
      { status: 'done', resultUrls: ['https://example.invalid/slide1.png'], code: 200 },
      { writeFile: false });
    let fetched = 0;
    s._downloadFirst = async (urls, dest) => {
      fetched++;
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, 'recovered-bytes');
      return dest;
    };
    const [r] = await s.submitDeck(slides, { callbackThreshold: 99 });
    ok(fetched === 1, 'resumed slide with a missing file re-entered the download path');
    ok(r.status === 'done' && r.localPath === target, 'recovered slide reports done with a real path');
    ok(fs.existsSync(target), 'the recovered file is on disk');
  }

  // 3. ANTI-FALSE-FAIL CONTROL. A genuinely complete resumed slide is unchanged and
  //    costs no extra fetch -- the fix must not make a healthy deck re-download.
  {
    const { s, target, slides } = seedResume(
      { status: 'done', resultUrls: ['https://example.invalid/slide1.png'], code: 200 },
      { writeFile: true });
    let fetched = 0;
    s._downloadFirst = async () => { fetched++; return null; };
    const [r] = await s.submitDeck(slides, { callbackThreshold: 99 });
    ok(r.status === 'done', 'a complete resumed slide still reports done');
    ok(r.localPath === target, 'a complete resumed slide reports its real path');
    ok(fetched === 0, 'a complete resumed slide is not re-downloaded');
  }

  // 4. Both branches resolve through the ONE helper, asserted behaviourally: the
  //    fresh-wait path gets the same treatment.
  {
    const { s, target, slides } = seedResume(
      { status: 'done', resultUrls: [], code: 200 }, { writeFile: false });
    // Remove the done marker so the slide takes the fresh-WAIT branch instead.
    // submitDeck builds its own poller, so the stub goes on the prototype and is
    // restored immediately afterwards.
    fs.rmSync(path.join(s.doneDir, 'task-1.json'));
    const origWait = KieKvPoller.prototype.waitForTask;
    KieKvPoller.prototype.waitForTask = async () => ({ status: 'done', resultUrls: [], code: 200 });
    let results;
    try {
      results = await s.submitDeck(slides, { callbackThreshold: 99 });
    } finally {
      KieKvPoller.prototype.waitForTask = origWait;
    }
    ok(results[0].status === 'failed', "fresh-wait 'done' with no file -> failed (same rule)");
    ok(results[0].localPath === null, 'fresh-wait path also reports localPath null');
    ok(!fs.existsSync(target), 'nothing was written for a slide that produced no file');
  }
});

// ── summary ───────────────────────────────────────────────────────────────────

// =============================================================================
// Skill 74 handoff: prepareCallback -> `kie_live_adapter.py submit --callback-url` -> adoptAdapterTask.
// =============================================================================
await section('kie-slide-submitter: Skill 74 normalized task handoff', async () => {
  const mk = () => {
    const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'kie74-'));
    return { ws, s: new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', dataRoot: ws,
      kvWorkerUrl: 'https://relay.invalid', callbackHmacKey: hmacHex(SLUG, MASTER_CB), kvReadToken: hmacHex(SLUG, MASTER_KVR) }) };
  };

  const n = normalizeAdapterTask({ task_id: 't1', model_id: 'm1', state: 'queued', data: { callback_url: 'https://x/cb?j=1' } });
  ok(n.taskId === 't1' && n.modelId === 'm1' && n.callbackUrl === 'https://x/cb?j=1', 'normalizes the adapter result shape (data.callback_url)');
  const f = normalizeAdapterTask({ task_id: 't2', model_id: 'm2', callback_url: 'https://x/cb?j=2' });
  ok(f.taskId === 't2' && f.callbackUrl === 'https://x/cb?j=2', 'normalizes the flat shape (callback_url)');
  ok(normalizeAdapterTask(null).taskId === null, 'null input normalizes without throwing');

  const { ws, s } = mk();
  const target = path.join(ws, 'out', 'a.png');
  const { submitId, callBackUrl } = s.prepareCallback({ deckId: 'd', slideId: 's1', targetPath: target, model: 'm1' });
  const u = new URL(callBackUrl);
  ok(u.searchParams.get('c') === SLUG && u.searchParams.get('j') === submitId, 'prepared URL carries c= and j=submitId');
  ok(u.searchParams.get('s') === hmacHex(`${SLUG}:${submitId}`, hmacHex(SLUG, MASTER_CB)), 's= validator matches the Worker derivation');
  const reg = s._readRegistry(submitId);
  ok(reg.status === 'submitting' && reg.callBackUrl === callBackUrl && !!reg.perTaskSecret, 'registry row written before submit with the per-task secret');
  ok(!callBackUrl.includes(reg.perTaskSecret), 'raw per-task secret is not in the URL');

  const origWait = KieKvPoller.prototype.waitForTask;
  let waitedFor = null;
  KieKvPoller.prototype.waitForTask = async (sid, tid, secret) => {
    waitedFor = { sid, tid, secret };
    return { status: 'done', resultUrls: ['https://tempfile.aiquickdraw.com/a.png'], code: 200 };
  };
  try {
    s._downloadFirst = async (urls, dest) => { fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, 'img'); return dest; };
    const r = await s.adoptAdapterTask({ state: 'queued', task_id: 'task-74', model_id: 'm1', data: { callback_url: callBackUrl, callback_sent: true } });
    ok(waitedFor && waitedFor.tid === 'task-74' && waitedFor.sid === submitId && waitedFor.secret === reg.perTaskSecret, 'adopted task is waited on with the stored submitId and secret');
    ok(r.status === 'done' && r.localPath === target && fs.existsSync(target), 'adopted task reconciles to a real file on disk');
    ok(s._readRegistry(submitId).taskId === 'task-74', 'registry row records the Skill 74 taskId');
    ok(fs.existsSync(path.join(s.indexDir, 'task-74.json')), 'taskId -> submitId index written');

    // Foreign / tampered callback URL is refused and never waited on.
    waitedFor = null;
    let refused = false;
    try { await s.adoptAdapterTask({ state: 'queued', task_id: 'x', model_id: 'm', data: { callback_url: callBackUrl + '&z=1' } }); }
    catch (e) { refused = /does not match a prepared callback/.test(e.message); }
    ok(refused && waitedFor === null, 'tampered callback_url refused, no wait');
    refused = false;
    try { await s.adoptAdapterTask({ state: 'queued', task_id: 'x', model_id: 'm' }); }
    catch (e) { refused = true; }
    ok(refused, 'result with no callback_url refused');

    // Shadow-mode skip: no task, failed result, no wait.
    const p2 = s.prepareCallback({ deckId: 'd', slideId: 's2', targetPath: path.join(ws, 'out', 'b.png'), model: 'm1' });
    const r2 = await s.adoptAdapterTask({ state: 'skipped', fallback_used: true, task_id: null, data: { callback_url: p2.callBackUrl } });
    ok(r2.status === 'failed' && waitedFor === null, 'skipped (shadow) submit returns failed without waiting');
    ok(s._readRegistry(p2.submitId).status === 'failed-submit', 'skipped submit marks the registry row failed-submit');
  } finally {
    KieKvPoller.prototype.waitForTask = origWait;
  }

  // Callback mode needs the Worker secrets.
  const bare = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', dataRoot: fs.mkdtempSync(path.join(os.tmpdir(), 'kie74b-')) });
  let threw = false;
  try { bare.prepareCallback({ deckId: 'd', slideId: 's', targetPath: '/x' }); } catch (_) { threw = true; }
  ok(threw, 'prepareCallback without callbackHmacKey/kvReadToken throws');
});

// =============================================================================
// F21 ITEM 10 — A CALLBACK MUST REUSE THE EXISTING JOB IDENTITY.
//
// The defect: prepareCallback() minted a fresh 128-bit submitId on EVERY call, so a retry
// after a crash or an uncertain submit produced a second job identity for one slide -- a
// second paid job -- while adoptAdapterTask() would happily REBIND an already-recorded
// provider task id to whatever the adapter result carried. Both are asserted here by
// driving the real functions; every id this section proves identical is printed.
// =============================================================================
await section('F21 item 10: prepareCallback reuses the job identity (never re-mints)', async () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'kie-id-'));
  const s = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', dataRoot: ws,
    kvWorkerUrl: 'https://relay.invalid', callbackHmacKey: hmacHex(SLUG, MASTER_CB), kvReadToken: hmacHex(SLUG, MASTER_KVR) });
  const job = { deckId: 'deck-id', slideId: 'slide-id', targetPath: path.join(ws, 'out', 'a.png'), model: 'm1' };

  const first = s.prepareCallback(job);
  ok(first.state === 'new' && first.resubmit === true && first.reused === false,
     `first preparation mints a new identity (state=${first.state}, resubmit=${first.resubmit})`);
  ok(first.taskId === null, 'a fresh identity carries no provider task id yet');

  // The crash/retry case: the SAME logical job is prepared again.
  const second = s.prepareCallback(job);
  const secondId = new URL(second.callBackUrl).searchParams.get('j');
  console.log(`  ids - first submitId=${first.submitId}  second submitId=${second.submitId}  j= in second URL=${secondId}`);
  ok(second.submitId === first.submitId,
     `the SECOND preparation returns the SAME submitId (${first.submitId} == ${second.submitId})`);
  ok(second.callBackUrl === first.callBackUrl, 'the callback URL is byte-identical (same j=, s= and h=)');
  ok(secondId === first.submitId, 'the j= inside the callback URL is the same job identity');
  ok(second.reused === true && second.resubmit === false,
     'the reuse is explicit: reused=true, resubmit=false');
  ok(second.state === 'uncertain',
     `a prepared-but-unresolved row is UNCERTAIN, not free to resubmit (state=${second.state})`);

  // Only ONE registry row exists for the label: the retry did not fork the job.
  const rows = fs.readdirSync(s.registryDir).filter(f => f.endsWith('.json'));
  ok(rows.length === 1, `exactly one registry row after two preparations (found ${rows.length}: ${rows.join(', ')})`);

  // A DIFFERENT slide is a different job: the reuse must not collapse it.
  const other = s.prepareCallback({ ...job, slideId: 'slide-2' });
  ok(other.submitId !== first.submitId && other.state === 'new',
     'a different slide keeps its own new identity (reuse does not collapse distinct jobs)');
  ok(fs.readdirSync(s.registryDir).filter(f => f.endsWith('.json')).length === 2,
     'two distinct jobs -> two registry rows');
});

await section('F21 item 10: the recorded task id is the identity, and it is never rebound', async () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'kie-id2-'));
  const s = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', dataRoot: ws,
    kvWorkerUrl: 'https://relay.invalid', callbackHmacKey: hmacHex(SLUG, MASTER_CB), kvReadToken: hmacHex(SLUG, MASTER_KVR) });
  const job = { deckId: 'deck-r', slideId: 'slide-r', targetPath: path.join(ws, 'out', 'r.png'), model: 'm1' };
  const prepared = s.prepareCallback(job);

  const origWait = KieKvPoller.prototype.waitForTask;
  KieKvPoller.prototype.waitForTask = async (sid, tid, secret) => ({ status: 'done', resultUrls: [], code: 200 });
  try {
    s._downloadFirst = async () => null;
    const adopted = await s.adoptAdapterTask({ state: 'queued', task_id: 'task-A', model_id: 'm1',
                                               data: { callback_url: prepared.callBackUrl } });
    const afterAdopt = s._readRegistry(prepared.submitId);
    console.log(`  ids - submitId=${prepared.submitId}  adapter task_id=task-A  registry task_id=${afterAdopt.taskId}`);
    ok(adopted.taskId === 'task-A' && afterAdopt.taskId === 'task-A',
       'the adapter task id and the registry task id are IDENTICAL (task-A)');

    // Re-preparing after adoption must return the ACCEPTED identity, not a new one.
    const again = s.prepareCallback(job);
    ok(again.submitId === prepared.submitId && again.taskId === 'task-A' && again.state === 'accepted',
       `re-preparation returns the accepted identity (submitId=${again.submitId}, taskId=${again.taskId}, state=${again.state})`);
    ok(again.resubmit === false, 'an accepted job is never marked resubmittable');

    // A different provider task answering for this identity is a different job: refuse.
    let rebound = null;
    try { await s.adoptAdapterTask({ state: 'queued', task_id: 'task-B', model_id: 'm1',
                                     data: { callback_url: prepared.callBackUrl } }); }
    catch (e) { rebound = e.message; }
    console.log(`  ids - registry still task-A after a task-B result: ${s._readRegistry(prepared.submitId).taskId}`);
    ok(rebound && /not the job identity recorded/.test(rebound),
       'a result carrying a DIFFERENT task id is refused, not bound over the recorded one');
    ok(s._readRegistry(prepared.submitId).taskId === 'task-A',
       'the recorded job identity is unchanged after the refused rebind');

    // No task id at all for a job that already has one is unresolved, not "failed and free".
    const missing = await s.adoptAdapterTask({ state: 'queued', task_id: null,
                                               data: { callback_url: prepared.callBackUrl } });
    const afterMissing = s._readRegistry(prepared.submitId);
    ok(missing.status === 'failed' && missing.code === 'identity-missing',
       'a taskId-less answer for a recorded job reports identity-missing, never a silent success');
    ok(afterMissing.taskId === 'task-A' && afterMissing.status === 'uncertain',
       'the recorded task id survives, and the row is marked uncertain for reconciliation');
  } finally {
    KieKvPoller.prototype.waitForTask = origWait;
  }

  // A changed model is a DIFFERENT job: new identity, old row retired by name.
  const changed = s.prepareCallback({ ...job, model: 'm2' });
  const old = s._readRegistry(prepared.submitId);
  ok(changed.submitId !== prepared.submitId && changed.state === 'new',
     'a changed model yields a new identity (it is a different job)');
  ok(old.status === 'superseded' && /model changed/.test(String(old.supersededReason)),
     'the earlier row is SUPERSEDED with the reason recorded, never silently orphaned');
});

// =============================================================================
// F21 ITEM 11 — THE DURABLE DATA ROOT, resolved once and used everywhere.
//
// The defect: registry/index/done were built from `path.join(workspaceDir, '.kie', ...)`
// in TWO files, so paid-job evidence lived wherever a caller's working folder pointed --
// including inside replaceable skill trees. The fix routes every one of those paths through
// shared-utils/durable-data-root.sh (Skill 74 executes the same file), so there is one
// computation and one answer.
// =============================================================================
await section('F21 item 11: state lives under the ONE durable root, never in the skill tree', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kie-root-'));
  const prev = process.env.OPENCLAW_DATA_ROOT;
  process.env.OPENCLAW_DATA_ROOT = root;
  let s;
  try {
    // No dataRoot option: the constructor must resolve the durable root itself.
    s = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k' });
  } finally {
    if (prev === undefined) delete process.env.OPENCLAW_DATA_ROOT; else process.env.OPENCLAW_DATA_ROOT = prev;
  }
  const expected = path.join(root, 'data', 'kie-jobs', SLUG);
  console.log(`  root - resolved registry dir=${s.registryDir}`);
  ok(s.registryDir === path.join(expected, 'registry'), 'registry lives under <root>/data/kie-jobs/<slug>/registry');
  ok(s.indexDir === path.join(expected, 'index') && s.doneDir === path.join(expected, 'done'),
     'index and done derive from the SAME resolved root');
  ok(s.layout.root === root, `the layout records the resolved root (${s.layout.root})`);
  ok(!s.registryDir.startsWith(skillDir), 'no state path sits inside the skill directory');
  ok(!s.registryDir.includes(path.join('', '.kie', '')), 'the transient .kie layout is gone');

  // Resolved ONCE and used everywhere: the poller the submitter builds inherits its layout.
  const poller = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', layout: s.layout,
                                   kvReadToken: 'tk', callbacksEnabled: false });
  ok(poller.registryDir === s.registryDir && poller.doneDir === s.doneDir,
     'a poller given the submitter\'s layout writes to the identical directories (one computation)');

  // The resolver refuses an unnameable root instead of guessing a location.
  const prevEnv = process.env.OPENCLAW_DATA_ROOT;
  process.env.OPENCLAW_DATA_ROOT = path.join(root, 'definitely-not-here');
  let refused = null;
  try { new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k' }); }
  catch (e) { refused = e.message; }
  finally { if (prevEnv === undefined) delete process.env.OPENCLAW_DATA_ROOT; else process.env.OPENCLAW_DATA_ROOT = prevEnv; }
  ok(refused && /durable data root did not resolve/.test(refused),
     'a non-existent root pin is REFUSED by name instead of silently writing elsewhere');
});

console.log(`\n${'='.repeat(60)}`);
if (failures.length === 0) {
  console.log(`PASS - ${passed} assertions passed`);
  process.exit(0);
} else {
  console.error(`FAIL - ${failures.length} failure(s), ${passed} passed:`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
