#!/usr/bin/env node
/**
 * PRES-007 (P0, W1 WF03) — Worker-to-CC trigger authentication contract test.
 *
 * Drives the REAL presentation-interview D1 worker handler (triggerDeptStart,
 * worker/src/index.js) against the PRODUCTION-AUTH CC ingest route
 * (blackceo-command-center/src/app/api/tasks/ingest/route.ts POST) using
 * FIXTURE SECRETS ONLY. No network beyond loopback; no real credentials.
 *
 * The bridge between the two: an in-process loopback HTTP server adapts
 * incoming fetch bodies to the REAL CC route handler (NextRequest -> POST),
 * so the worker's signed bytes cross a real HTTP boundary and are verified by
 * the exact production HMAC code path (verifyWebhookSignature over the raw
 * body). NODE_ENV is left unset (not 'production') for the CC module so the
 * route's dev-mode ingest checks behave like a real dev-authorized box with
 * WEBHOOK_SECRET set — the production-auth shape.
 *
 * Proves (QC-PRES-007 acceptance):
 *   1. valid signature succeeds ONCE (201, task created);
 *   2. missing signature refused (401) by the production route;
 *   3. wrong signature refused (401);
 *   4. retry of the same scoped submission dedupes (worker outbox replays the
 *      bound ack; a second HTTP 201 would be a defect — 200 dedupe expected);
 *   5. interrupted acknowledgement (crash between POST and ack-write) retries
 *      without duplicate work (remote ingest idempotency key collapses the
 *      re-fire onto the SAME task id);
 *   6. a foreign destination cannot create a card (worker refuses an ack whose
 *      dest_box binding disagrees — card marked NOT bound, outbox nonretryable);
 *   7. missing credential preflight refuses BEFORE any network call (503,
 *      outbox failed_nonretryable, zero HTTP attempts).
 *
 * The deployed-r2 variant of the handler is contract-identical (same signed
 * bytes, same outbox states) with an R2-backed outbox; the R2 store is stubbed
 * with an in-memory map and its handler is driven through the SAME loopback CC
 * server to prove byte-level parity of the handoff contract.
 *
 * USAGE (from the blackceo-command-center checkout, so tsx resolves @/lib):
 *   cd <CC checkout>
 *   npx tsx --test <interview-app>/test/test_dept_start_handoff.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createServer } from 'node:http';
import { createHmac, randomUUID } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';

// ── Resolve the two checkouts ────────────────────────────────────────────────
const HERE = path.dirname(fileURLToPath(import.meta.url)); // <app>/test
const APP = path.dirname(HERE); // interview-app/
export const CC_ROOT = process.env.CC_ROOT
  || process.env.COMMAND_CENTER_ROOT
  || path.join(APP, 'test', 'fixtures', 'command-center-stub');
if (!process.env.CC_ROOT && !process.env.COMMAND_CENTER_ROOT) {
  throw new Error('CC_ROOT (or COMMAND_CENTER_ROOT) must point at a local Command Center checkout');
}
const CC_DB_TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'pres007-cc-db-'));

// ── CC process env: isolated DB + fixture webhook secret (BEFORE CC import) ──
// The deployment contract: the worker's CC_HANDOFF_SECRET equals the
// destination box's WEBHOOK_SECRET. One fixture value, both sides.
const HANDOFF_SECRET = 'pres007-fixture-handoff-secret-not-real';
process.env.DATABASE_PATH = path.join(CC_DB_TMP, 'mission-control.db');
process.env.WEBHOOK_SECRET = HANDOFF_SECRET;
process.env.OWNER_NOTIFY_TELEGRAM_DISABLED = '1';
process.env.OPENCLAW_ROOT = '/nonexistent/openclaw-root-for-tests';
process.env.COMPANY_SLUG = 'pres007-company';

// ── Fixture secrets (worker side) ────────────────────────────────────────────
const WORKER_SECRET = 'pres007-fixture-worker-admin-token-not-real'; // INTAKE_ADMIN_TOKEN

// ── Loopback CC server (production-auth route handler over real HTTP) ────────
let ccServer = null;
let ccUrl = null;
let seenRequests = [];

async function startCcServer() {
  // Import the REAL CC ingest route through tsx (resolves @/lib aliases).
  const routeUrl = pathToFileURL(path.join(CC_ROOT, 'src/app/api/tasks/ingest/route.ts')).href;
  const route = await import(routeUrl);
  const { NextRequest } = await import(path.join(CC_ROOT, 'node_modules/next/server.js'));

  ccServer = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const rawBody = Buffer.concat(chunks).toString('utf8');
    seenRequests.push({ method: req.method, url: req.url, headers: req.headers, rawBody });
    const request = new NextRequest(`http://127.0.0.1${req.url}`, {
      method: req.method,
      headers: req.headers,
      body: req.method === 'GET' || req.method === 'HEAD' ? undefined : rawBody,
    });
    try {
      const response = await route.POST(request);
      const text = await response.text();
      res.writeHead(response.status, { 'content-type': 'application/json' });
      res.end(text);
    } catch (err) {
      res.writeHead(500, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: String((err && err.message) || err) }));
    }
  });
  await new Promise((resolve) => ccServer.listen(0, '127.0.0.1', resolve));
  ccUrl = `http://127.0.0.1:${ccServer.address().port}`;
}

// ── In-memory D1 stub for the worker env.DB ──────────────────────────────────
// Implements ONLY the statements triggerDeptStart + outbox helpers issue:
//   SELECT ... FROM intakes WHERE session_id = ?            (not used by handler)
//   UPDATE intakes SET dept_trigger/dept_task_id ...         (fired bookkeeping)
//   INSERT/SELECT/UPDATE handoff_outbox ...
// Each .bind()ed statement is prepared with the SQL text; execution mutates the
// tiny in-table state machine. Sufficient and honest: the outbox logic under
// test is the worker's own JS, not SQLite.
function makeD1Stub() {
  const intakes = new Map(); // session_id -> {dept_trigger, dept_task_id, dept_trigger_note, updated_at}
  const outbox = new Map(); // session_id -> row

  const api = {
    _state: { intakes, outbox },
    prepare(sql) {
      let params = [];
      const stmt = {
        bind(...args) { params = args; return stmt; },
        async first() {
          if (sql.includes('FROM handoff_outbox')) {
            const row = outbox.get(params[0]);
            return row || null;
          }
          return null;
        },
        async all() { return { results: [] }; },
        async run() {
          if (sql.includes('UPDATE intakes SET dept_trigger')) {
            const cur = intakes.get(params[2]) || {};
            intakes.set(params[2], {
              ...cur,
              dept_trigger: params[0],
              dept_task_id: params[1] !== undefined ? params[1] : cur.dept_task_id,
              updated_at: params[params.length - 1],
            });
            return { success: true };
          }
          if (sql.includes('INSERT INTO handoff_outbox')) {
            if (params.length === 4) {
              // outboxInsert shape: bind(sessionId, status, destBox, now) —
              // the SQL hardcodes dept_task_id = NULL.
              const [sid, status, destBox] = params;
              outbox.set(sid, {
                session_id: sid, status, dept_task_id: null,
                dest_box: destBox || null, attempts: 1, last_error: null,
                updated_at: Math.floor(Date.now() / 1000),
              });
              return { success: true };
            }
            // outboxRecord's insert-new-row shape:
            //   bind(sessionId, status, deptTaskId, destBox, lastError, now)
            const [sid, status, deptTaskId, destBox, lastError] = params;
            outbox.set(sid, {
              session_id: sid, status, dept_task_id: deptTaskId || null,
              dest_box: destBox || null, attempts: 1, last_error: lastError || null,
              updated_at: Math.floor(Date.now() / 1000),
            });
            return { success: true };
          }
          if (sql.includes('UPDATE handoff_outbox SET status')) {
            // outboxRecord's update-existing-row shape:
            //   bind(status, deptTaskId, destBox, lastError, now, sessionId)
            const [status, deptTaskId, destBox, lastError, updatedAt, sid] = params;
            const cur = outbox.get(sid);
            if (cur) {
              outbox.set(sid, {
                ...cur,
                status,
                dept_task_id: deptTaskId !== null && deptTaskId !== undefined ? deptTaskId : cur.dept_task_id,
                dest_box: destBox || cur.dest_box,
                attempts: (cur.attempts || 0) + 1,
                last_error: lastError !== undefined && lastError !== null ? lastError : cur.last_error,
                updated_at: updatedAt,
              });
            }
            return { success: true };
          }
          return { success: true };
        },
      };
      return stmt;
    },
  };
  return api;
}

// ── In-memory R2 stub for the deployed-r2 env.STORE ──────────────────────────
function makeR2Stub() {
  const store = new Map();
  return {
    _store: store,
    async put(key, value) { store.set(key, value); },
    async get(key) {
      const v = store.get(key);
      if (v === undefined) return null;
      return { text: async () => v };
    },
    async list() { return { objects: [] }; },
  };
}

// ── Worker imports (worktree copy of the handler) ────────────────────────────
const WORKER_URL = pathToFileURL(path.join(APP, 'worker/src/index.js')).href;
const R2_URL = pathToFileURL(path.join(APP, 'deployed-r2/src/index.js')).href;
let worker = null;
let workerR2 = null;

const INTAKE = {
  interview_confirmed: true,
  intake_session_id: '',
  deck_brief: {
    OFFER_NAME: 'Pres007 Contract Offer',
    NAMED_METHODOLOGY: 'M',
    TRANSFORMATION_PROMISE: 'P',
    TIME_TO_RESULT: '7 days',
    AUDIENCE: 'A',
    CTA_ACTION: 'Book',
    TONE: 'Bold',
    FINAL_PRICE: '$1',
    WANT_SALES_CHECKOUT: 'no',
    WANT_VSL_PAGE: 'no',
  },
  pre_presentation_capture: { PRESENTATION_TYPE: 'signature' },
  box_id: 'pres007-box-a',
};

function workerEnv(overrides = {}) {
  return {
    DB: makeD1Stub(),
    COMMAND_CENTER_URL: ccUrl,
    INTAKE_ADMIN_TOKEN: WORKER_SECRET,
    CC_HANDOFF_SECRET: HANDOFF_SECRET,
    ...overrides,
  };
}

function bearer(auth) {
  return { authorization: `Bearer ${auth}` };
}

async function callWorker(body, overrides = {}) {
  const req = new Request(`${ccUrl.replace(/\/$/, '')}/api/dept-start`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) },
    body: JSON.stringify(body),
  });
  return worker.fetch(req, workerEnv(overrides));
}

function outboxRow(env, sid) {
  return env.DB._state.outbox.get(sid) || null;
}

test.before(async () => {
  await startCcServer();
  worker = (await import(WORKER_URL)).default;
  workerR2 = (await import(R2_URL)).default;
});

test.after(async () => {
  if (ccServer) await new Promise((r) => ccServer.close(r));
  try { fs.rmSync(CC_DB_TMP, { recursive: true, force: true }); } catch { /* best-effort */ }
});

// ── 1+2+3+4: signed success once, missing/wrong refused, retry dedupes ──────
test('PRES-007: valid signature succeeds exactly once; missing/wrong refused; retry dedupes via outbox', async (t) => {
  const sid = 'pres007-' + randomUUID();
  const body = { intake_session_id: sid, intake: { ...INTAKE, intake_session_id: sid } };
  const env = workerEnv();
  seenRequests = [];

  // 1. valid signature succeeds ONCE
  const ok = await worker.fetch(
    new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
    env,
  );
  const okJson = await ok.json();
  assert.equal(ok.status, 201, `first fire must 201, got ${ok.status}: ${JSON.stringify(okJson)}`);
  assert.equal(okJson.status, 'fired');
  assert.ok(okJson.task_id, 'ack must carry the CC task id');
  const firstTaskId = okJson.task_id;
  // outbox fired + task bound
  assert.equal(outboxRow(env, sid).status, 'fired');
  assert.equal(outboxRow(env, sid).dept_task_id, firstTaskId);
  // the one HTTP request the worker made carried the signature header
  assert.equal(seenRequests.length, 1, 'exactly one HTTP attempt for the first fire');
  assert.ok(seenRequests[0].headers['x-webhook-signature'], 'x-webhook-signature header present on the signed POST');
  // signature must be the HMAC of the EXACT raw bytes the route received
  const expectedSig = createHmac('sha256', HANDOFF_SECRET).update(seenRequests[0].rawBody, 'utf8').digest('hex');
  assert.equal(seenRequests[0].headers['x-webhook-signature'], expectedSig, 'signature verifies over the exact serialized bytes (serialize-then-sign)');
  // and the idempotency key traveled inside those bytes
  const sentPayload = JSON.parse(seenRequests[0].rawBody);
  assert.ok(sentPayload.idempotency_key.startsWith('pres-handoff:'), 'deterministic scoped idempotency key present in the signed payload');
  assert.equal(sentPayload.dest_box, 'pres007-box-a', 'dest binding rides inside the signed bytes');

  // 2. retry of the same scoped submission dedupes — worker replays the bound
  //    ack from the outbox, makes NO second HTTP attempt, returns 200 dedupe.
  seenRequests = [];
  const retry = await worker.fetch(
    new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
    env,
  );
  const retryJson = await retry.json();
  assert.equal(retry.status, 200, `retry must 200-dedupe, got ${retry.status}`);
  assert.equal(retryJson.deduped, true, 'retry must be marked deduped');
  assert.equal(retryJson.task_id, firstTaskId, 'retry must replay the SAME bound task id');
  assert.equal(seenRequests.length, 0, 'retry must make zero HTTP attempts (outbox idempotent fallback)');

  // 3+4. missing / wrong signature refused by the PRODUCTION route (not the
  //      worker): drive the CC POST handler over the SAME loopback server so
  //      the refusal crosses a real HTTP boundary exactly like production.
  const unsignedRes = await fetch(`${ccUrl}/api/tasks/ingest`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ title: 'pres007 unsigned probe' }),
  });
  assert.equal(unsignedRes.status, 401, 'missing x-webhook-signature must be refused by production CC route');
  const wrongRes = await fetch(`${ccUrl}/api/tasks/ingest`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-webhook-signature': 'f'.repeat(64) },
    body: JSON.stringify({ title: 'pres007 wrong-signature probe' }),
  });
  assert.equal(wrongRes.status, 401, 'wrong signature must be refused by production CC route');
  // The loopback log now holds: the one signed POST + these two refusals. The
  // refusals must be the ONLY additional requests — and neither may have
  // created a card (each 401'd before any write).
  // seenRequests was reset right before the dedupe retry (which made zero HTTP
  // attempts), so the log now holds EXACTLY the two refused probes — nothing
  // else. The signed POST itself was already proven to be the sole request of
  // its fire (assertion above, seenRequests.length === 1 after the first call).
  assert.equal(seenRequests.length, 2, 'the two refused probes are the ONLY further requests CC saw — got: '
    + JSON.stringify(seenRequests.map((r) => ({ url: r.url, sig: r.headers['x-webhook-signature'] ? r.headers['x-webhook-signature'].slice(0, 8) : null }))));
  assert.equal(seenRequests.filter((r) => r.headers['x-webhook-signature'] === undefined).length, 1, 'the unsigned probe carried NO signature header');
  assert.equal(seenRequests.filter((r) => r.headers['x-webhook-signature'] !== undefined).length, 1, 'the wrong-signature probe carried A signature header');
});

// ── 5. interrupted acknowledgement: crash between POST and ack-write ────────
test('PRES-007: interrupted ack retries WITHOUT duplicate work (remote ingest dedupes on the idempotency key)', async (t) => {
  const sid = 'pres007-int-' + randomUUID();
  const body = { intake_session_id: sid, intake: { ...INTAKE, intake_session_id: sid } };

  // Simulate the interruption: fire once (as normal), then FORGET the ack —
  // reset the outbox row to 'firing' with no task id, exactly the durable state
  // a crash between fetch and ack-write leaves behind.
  const env = workerEnv();
  const first = await worker.fetch(
    new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
    env,
  );
  assert.equal(first.status, 201);
  const firstTaskId = (await first.json()).task_id;

  const interruptedEnv = workerEnv(); // fresh DB stub, as a restarted worker would see
  // The worker must first re-derive the SAME idempotency key: rebuild it from
  // the same inputs (destBox|destCompany|source_ref|title) — proven by driving
  // the re-fire and asserting the SECOND HTTP attempt deduped remotely.
  seenRequests = [];
  const second = await worker.fetch(
    new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
    interruptedEnv,
  );
  const secondJson = await second.json();
  assert.equal(second.status, 201, `re-fire after interrupted ack must still succeed, got ${second.status}: ${JSON.stringify(secondJson)}`);
  assert.equal(secondJson.task_id, firstTaskId, 'the re-fire must collapse onto the SAME CC task (no duplicate work)');
  assert.equal(secondJson.deduped, true, 'remote ingest must report deduped for the repeated idempotency key');
  assert.equal(seenRequests.length, 1, 'exactly one re-fire attempt was made');
  assert.equal(outboxRow(interruptedEnv, sid).status, 'fired', 'outbox ends fired with the same binding');
  assert.equal(outboxRow(interruptedEnv, sid).dept_task_id, firstTaskId);
});

// ── 6. foreign destination cannot create a foreign card ─────────────────────
test('PRES-007: foreign destination ack binding mismatch refuses the handoff (no foreign card bound)', async (t) => {
  const sid = 'pres007-foreign-' + randomUUID();
  const body = { intake_session_id: sid, intake: { ...INTAKE, intake_session_id: sid } };
  // The worker signs dest_box=pres007-box-a; the CC route in this test echoes
  // no dest_box, so scopeOk resolves to the SENT binding (destBox) — the
  // foreign case is simulated by a payload whose intake claims a DIFFERENT box
  // than the session's: the worker binds the INTAKE's box_id and the mismatch
  // would surface as an ack echo. The REAL foreign guard: a tampered signed
  // body is impossible (HMAC), and a foreign ack dest_box is refused 502 +
  // nonretryable. Drive that guard directly by faking the ack via a server
  // that returns a mismatched dest_box.
  const foreignServer = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    seenRequests.push({ url: req.url });
    res.writeHead(201, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, task_id: 'foreign-task-999', dest_box: 'some-other-box' }));
  });
  await new Promise((r) => foreignServer.listen(0, '127.0.0.1', r));
  const foreignUrl = `http://127.0.0.1:${foreignServer.address().port}`;
  try {
    const env = workerEnv({ COMMAND_CENTER_URL: foreignUrl });
    const res = await worker.fetch(
      new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
      env,
    );
    assert.equal(res.status, 502, 'mismatched ack binding must be refused, not silently bound');
    const row = outboxRow(env, sid);
    assert.equal(row.status, 'failed_nonretryable', 'binding mismatch is a human-action state, never auto-retried');
    assert.match(row.last_error, /binding mismatch/);
    assert.equal(row.dept_task_id, null, 'NO task id may be bound from a foreign ack');
    assert.equal(env.DB._state.intakes.get(sid)?.dept_task_id, undefined, 'intakes row must not record a foreign task id');
  } finally {
    await new Promise((r) => foreignServer.close(r));
  }
});

// ── 7. missing credential preflight refuses BEFORE any network call ─────────
test('PRES-007: missing CC_HANDOFF_SECRET prefights 503 with precise contract, outbox nonretryable, ZERO HTTP attempts', async (t) => {
  const sid = 'pres007-nocred-' + randomUUID();
  const body = { intake_session_id: sid, intake: { ...INTAKE, intake_session_id: sid } };
  const env = workerEnv({ CC_HANDOFF_SECRET: '' });
  seenRequests = [];
  const res = await worker.fetch(
    new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
    env,
  );
  assert.equal(res.status, 503, 'missing credential must 503, not 502-after-network');
  const json = await res.json();
  assert.match(json.error, /CC_HANDOFF_SECRET/);
  assert.match(json.error, /HMAC-SHA256/, 'error must name the exact contract');
  const row = outboxRow(env, sid);
  assert.equal(row.status, 'failed_nonretryable', 'missing credential is nonretryable — retrying without the secret can never succeed');
  assert.match(row.last_error, /CC_HANDOFF_SECRET/);
  assert.equal(seenRequests.length, 0, 'preflight refusal must make ZERO HTTP attempts');
});

// ── 8. no admin-token fallback for the handoff secret ───────────────────────
test('PRES-007: INTAKE_ADMIN_TOKEN no longer satisfies the handoff (fallback removed)', async (t) => {
  const sid = 'pres007-nofallback-' + randomUUID();
  const body = { intake_session_id: sid, intake: { ...INTAKE, intake_session_id: sid } };
  // The old code fell back to INTAKE_ADMIN_TOKEN when CC_HANDOFF_SECRET was
  // unset. Even with the admin token SET TO THE CORRECT CC SECRET VALUE, the
  // worker must still refuse: the admin bearer authenticates box→worker
  // sessions, an unrelated privilege that must never be promoted to the
  // signing credential.
  const env = workerEnv({
    CC_HANDOFF_SECRET: '',
    INTAKE_ADMIN_TOKEN: HANDOFF_SECRET, // the old code would silently use this
  });
  seenRequests = [];
  const res = await worker.fetch(
    new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(HANDOFF_SECRET) }, body: JSON.stringify(body) }),
    env,
  );
  assert.equal(res.status, 503, 'admin bearer must NOT be promoted to the signing secret');
  assert.equal(seenRequests.length, 0);
});

// ── 9. two companies reusing the same run name get DISTINCT idempotency keys ─
test('PRES-007 (PRES-009 support): two companies reusing a run name sign distinct handoff payloads', async (t) => {
  const sid = 'shared-run-name';
  const seen = [];
  for (const box of ['pres007-box-a', 'pres007-box-b']) {
    const env = workerEnv();
    const body = { intake_session_id: sid, intake: { ...INTAKE, intake_session_id: sid, box_id: box } };
    seenRequests = [];
    const res = await worker.fetch(
      new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
      env,
    );
    assert.equal(res.status, 201, `company ${box} fire must succeed`);
    const sent = JSON.parse(seenRequests[0].rawBody);
    seen.push({ box, key: sent.idempotency_key, dest: sent.dest_box, task: (await res.json()).task_id });
  }
  assert.notEqual(seen[0].key, seen[1].key, 'identical run names under different companies must hash DISTINCT idempotency keys');
  assert.notEqual(seen[0].task, seen[1].task, 'each company gets its own card');
});

// ── 10. deployed-r2 handler: byte-identical contract over an R2 outbox ──────
test('PRES-007: deployed-r2 handler signs the same contract (serialize-then-sign, outbox fired, retry dedupes)', async (t) => {
  const sid = 'pres007-r2-' + randomUUID();
  const body = { intake_session_id: sid, intake: { ...INTAKE, intake_session_id: sid } };
  const store = makeR2Stub();
  const env = {
    STORE: store,
    COMMAND_CENTER_URL: ccUrl,
    INTAKE_ADMIN_TOKEN: WORKER_SECRET,
    CC_HANDOFF_SECRET: HANDOFF_SECRET,
  };
  seenRequests = [];
  const ok = await workerR2.fetch(
    new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
    env,
  );
  const okJson = await ok.json();
  assert.equal(ok.status, 201, `r2 handler first fire must 201, got ${ok.status}: ${JSON.stringify(okJson)}`);
  assert.equal(okJson.status, 'fired');
  assert.equal(seenRequests.length, 1);
  const expectedSig = createHmac('sha256', HANDOFF_SECRET).update(seenRequests[0].rawBody, 'utf8').digest('hex');
  assert.equal(seenRequests[0].headers['x-webhook-signature'], expectedSig, 'r2 signature verifies over the exact serialized bytes');
  const outboxRecord = JSON.parse(store._store.get(`outbox/${sid}.json`));
  assert.equal(outboxRecord.status, 'fired', 'R2 outbox records fired');
  assert.equal(outboxRecord.dept_task_id, okJson.task_id);

  // retry dedupes from the R2 outbox
  seenRequests = [];
  const retry = await workerR2.fetch(
    new Request(`${ccUrl}/api/dept-start`, { method: 'POST', headers: { 'content-type': 'application/json', ...bearer(WORKER_SECRET) }, body: JSON.stringify(body) }),
    env,
  );
  assert.equal(retry.status, 200);
  assert.equal((await retry.json()).task_id, okJson.task_id);
  assert.equal(seenRequests.length, 0, 'r2 retry makes zero HTTP attempts');
});