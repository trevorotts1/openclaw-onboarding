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
const { KieSlideSubmitter } = require(path.join(skillDir, 'kie-slide-submitter.js'));

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
await section('Worker: /healthz reports version 1.1.0', async () => {
  const res = await worker.fetch(new Request('https://w/healthz'), {}, makeCtx().ctx);
  ok(res.status === 200, 'healthz -> 200');
  const body = await res.json();
  ok(body.version === '1.1.0', `healthz version == 1.1.0 (got ${body.version})`);
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

await section('box-kv-poller: _validatePerTaskSecret is exact submitId match (fix 34)', async () => {
  const ws = tmpWorkspace();
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', workspaceDir: ws, kvReadToken: 'tk' });
  ok(p._validatePerTaskSecret({ submitId: 'want-this' }, 'want-this') === true, 'matching submitId -> true');
  ok(p._validatePerTaskSecret({ submitId: 'other-task' }, 'want-this') === false, 'different submitId -> false (confused-deputy blocked)');
  ok(p._validatePerTaskSecret({ submitId: '' }, 'want-this') === false, 'empty submitId -> false');
});

await section('box-kv-poller: code 200 + no allowlisted URLs -> failed (fix 35)', async () => {
  const ws = tmpWorkspace();
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', workspaceDir: ws, kvReadToken: 'tk', pollIntervalMs: 5 });
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
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', workspaceDir: ws,
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
  const onDisk = JSON.parse(fs.readFileSync(path.join(ws, '.kie', 'done', 'task-empty.json'), 'utf8'));
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
  const onDisk = JSON.parse(fs.readFileSync(path.join(ws, '.kie', 'done', 'task-ok.json'), 'utf8'));
  ok(onDisk.status === 'done', 'done marker written as before for a real result');
});

await section('box-kv-poller: KV path still resolves a real url as done (no regression)', async () => {
  const ws = tmpWorkspace();
  const p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', workspaceDir: ws,
                              kvReadToken: 'tk', pollIntervalMs: 1 });
  p._pollKv = async () => ({ submitId: 'sub-kv', code: 200,
                             resultUrls: ['https://tempfile.aiquickdraw.com/kv.png'], receivedAt: 'now' });
  const marker = await p.waitForTask('sub-kv', 'task-kv', 'secret', { timeoutMs: 200 });
  ok(marker.status === 'done', `KV path with an allowlisted URL -> done (got ${marker.status})`);
  ok(marker.source === 'callback-kv', 'resolved via the callback-KV path');
});

await section('box-kv-poller: BOTH paths share ONE outcome rule (_resolveOutcome)', async () => {
  const ws = tmpWorkspace();
  const p  = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: 'https://w', workspaceDir: ws, kvReadToken: 'tk' });
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
  try { p = new KieKvPoller({ clientSlug: SLUG, kvWorkerUrl: '', workspaceDir: ws, callbacksEnabled: false }); }
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
  try { new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', workspaceDir: ws }); }
  catch (_) { threw = true; }
  ok(!threw, 'no callbackHmacKey/kvReadToken required at construction time');
});

await section('kie-slide-submitter: resume dedup prefers taskId, supersedes orphan (fix 37i)', async () => {
  const ws = tmpWorkspace();
  const regDir = path.join(ws, '.kie', 'registry');
  fs.mkdirSync(regDir, { recursive: true });
  const label = 'deck1_slide1';
  // orphan (crash before Kie returned): taskId null, older
  const orphan = { submitId: 'orphan-id', label, deckId: 'deck1', slideId: 'slide1', taskId: null, submittedAt: '2026-07-05T00:00:00.000Z' };
  // the real paid task: taskId set, newer
  const real   = { submitId: 'real-id',  label, deckId: 'deck1', slideId: 'slide1', taskId: 'kie-task-99', submittedAt: '2026-07-05T00:00:05.000Z' };
  fs.writeFileSync(path.join(regDir, 'orphan-id.json'), JSON.stringify(orphan));
  fs.writeFileSync(path.join(regDir, 'real-id.json'),   JSON.stringify(real));

  const s = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', workspaceDir: ws });
  const byLabel = s._loadRegistryByLabel();
  ok(byLabel[label] && byLabel[label].taskId === 'kie-task-99', 'winner is the row WITH a taskId (no double-submit)');
  const orphanAfter = JSON.parse(fs.readFileSync(path.join(regDir, 'orphan-id.json'), 'utf8'));
  ok(orphanAfter.status === 'superseded', 'orphan row marked superseded on disk');
  ok(orphanAfter.supersededBy === 'real-id', 'orphan records supersededBy the winner');
});

await section('kie-slide-submitter: a durable "done" marker with no file is reconciled to failed (ONB-46-001)', async () => {
  const ws = tmpWorkspace();
  const s  = new KieSlideSubmitter({ clientSlug: SLUG, kieApiKey: 'k', workspaceDir: ws });
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

  // Both branches (fresh wait AND resume/already-resolved) must delegate.
  const src = fs.readFileSync(path.join(skillDir, 'kie-slide-submitter.js'), 'utf8');
  const delegations = (src.match(/this\._reconcileDoneStatus\(/g) || []).length;
  ok(delegations === 2, `both result paths delegate to _reconcileDoneStatus (found ${delegations})`);
});

// ── summary ───────────────────────────────────────────────────────────────────
console.log(`\n${'='.repeat(60)}`);
if (failures.length === 0) {
  console.log(`PASS - ${passed} assertions passed`);
  process.exit(0);
} else {
  console.error(`FAIL - ${failures.length} failure(s), ${passed} passed:`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
