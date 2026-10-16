// ============================================================================
// agnes-progress.test.mjs — runnable check for BUILD-PLAN W2-wiring-U3
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/agnes-progress.test.mjs
//
// The studio service's half of the Agnes hand-off (SPEC A11, A2):
//   * GET /api/studio/session answers `agnes_remembered` and a per-project
//     `agnes_progress` map, and writes NOTHING while doing it.
//   * POST /api/studio/checkin carries the two fields; they are stored on the
//     records that already exist (client record / per-run order record), each
//     one only when its value changed — the KV-free check-in rule. An
//     unchanged check-in costs zero writes, the phone may not report either
//     field, and index.js still answers the check-in itself.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { buildKeyRecord, mintKey } from '../src/keys.js';
import { authorizeClient } from '../src/isolation.js';
import { randomClientId } from '../src/ids.js';
import { pageRoute } from '../src/page-api.js';
import { memObjects, memStore } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 13, 12, 0, 0);

const OK_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };

function ok(data, status = 200) {
  return new Response(JSON.stringify({ ok: true, ...data }), { status, headers: OK_HEADERS });
}
function fail(status, code, message) {
  return new Response(JSON.stringify({ ok: false, code, message }), { status, headers: OK_HEADERS });
}

/** The same store, counting every write and read the routes make. */
function countingStore() {
  const store = memStore();
  const counts = { put: 0, get: 0, list: 0 };
  const { kvGet, kvPut, kvList } = store;
  store.kvGet = async (k) => { counts.get += 1; return kvGet(k); };
  store.kvPut = async (k, v, ttl) => { counts.put += 1; return kvPut(k, v, ttl); };
  store.kvList = async (prefix) => { counts.list += 1; return kvList(prefix); };
  store.counts = counts;
  return store;
}

async function clientWithKey(store, kind = 'box', clientId = randomClientId()) {
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret, record };
}

async function makeCtx(store, objects, key, body = {}) {
  const auth = await authorizeClient(store, key);
  assert.equal(auth.ok, true, `key must authorize: ${auth.code || ''}`);
  return {
    store,
    objects,
    auth,
    body,
    url: new URL('https://studio.example/'),
    nowMs: T0,
    ok,
    fail,
    project: (order) => ({ ...order }),
  };
}

async function putOrder(store, clientId, orderId, createdAt = T0) {
  await store.kvPut(
    `order:${clientId}:${orderId}`,
    JSON.stringify({ order_id: orderId, client_id: clientId, title: 'your video', state: 'in_production', created_at: createdAt, updated_at: createdAt }),
  );
}

async function json(response) {
  return JSON.parse(await response.text());
}

/** The whole check-in path: pageRoute first (as index.js dispatches it). */
async function checkIn(ctx) {
  ctx.url = new URL('https://studio.example/api/studio/checkin');
  const request = new Request('https://studio.example/api/studio/checkin', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(ctx.body || {}),
  });
  return pageRoute(request, ctx);
}

async function session(store, objects, key) {
  const ctx = await makeCtx(store, objects, key);
  ctx.url = new URL('https://studio.example/api/studio/session');
  const request = new Request('https://studio.example/api/studio/session', { method: 'GET', headers: { 'x-ds-key': key } });
  const response = await pageRoute(request, ctx);
  assert.ok(response, 'session must be this module\'s route');
  return json(response);
}

// ---------------------------------------------------------------------------
// GET /api/studio/session — the two Agnes fields, and no writes at all
// ---------------------------------------------------------------------------

test('session answers the remembered answer and an empty progress map by default', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store, 'box');
  const out = await session(store, objects, key);
  assert.equal(out.agnes_remembered, 'unknown');
  assert.deepEqual(out.agnes_progress, {});
});

test('session writes nothing — it only reads the two records it already needed', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store, 'box');
  await putOrder(store, clientId, 'r_a1b2c3d4');
  store.counts.put = 0;
  const out = await session(store, objects, key);
  assert.equal(store.counts.put, 0, 'the session route must perform zero writes');
  assert.equal(Object.keys(out.orders).length, 1);
});

test('session carries the stored progress per project, keyed by order id', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store, 'box');
  await putOrder(store, clientId, 'r_a1b2c3d4');
  const record = { clips_total: 30, clips_done: 12, in_flight: 2, waiting_reason: null, eta_minutes_low: 84, eta_minutes_high: 96 };
  await store.kvPut(`order:${clientId}:r_a1b2c3d4`, JSON.stringify({
    ...(JSON.parse(await store.kvGet(`order:${clientId}:r_a1b2c3d4`))),
    agnes_progress: record,
  }));
  const out = await session(store, objects, key);
  assert.deepEqual(out.agnes_progress, { r_a1b2c3d4: record });
});

// ---------------------------------------------------------------------------
// POST /api/studio/checkin — stored only when it changes
// ---------------------------------------------------------------------------

test('a box check-in stores a changed remembered answer, and index.js still owns the check-in', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store, 'box');
  store.counts.put = 0; // the key record above is setup, not this route
  const ctx = await makeCtx(store, objects, key, { agnes_remembered: 'yes', orders: true });
  const routed = await checkIn(ctx);
  assert.equal(routed, null, 'pageRoute must fall through so index.js answers the check-in');
  const out = await session(store, objects, key);
  assert.equal(out.agnes_remembered, 'yes');
  assert.equal(store.counts.put, 1, 'one answer change is exactly one write');
});

test('the same remembered answer again writes nothing (KV-free check-in)', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store, 'box');
  await checkIn(await makeCtx(store, objects, key, { agnes_remembered: 'yes' }));
  store.counts.put = 0;
  for (let i = 0; i < 5; i += 1) {
    await checkIn(await makeCtx(store, objects, key, { agnes_remembered: 'yes', orders: true }));
  }
  assert.equal(store.counts.put, 0, 'five unchanged check-ins must write nothing');
  const out = await session(store, objects, key);
  assert.equal(out.agnes_remembered, 'yes');
});

test('an answer that actually changes is stored once', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store, 'box');
  await checkIn(await makeCtx(store, objects, key, { agnes_remembered: 'yes' }));
  store.counts.put = 0;
  await checkIn(await makeCtx(store, objects, key, { agnes_remembered: 'no' }));
  assert.equal(store.counts.put, 1);
  assert.equal((await session(store, objects, key)).agnes_remembered, 'no');
});

test('an unrecognised answer is ignored — the stored answer survives', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store, 'box');
  await checkIn(await makeCtx(store, objects, key, { agnes_remembered: 'no' }));
  store.counts.put = 0;
  for (const value of ['maybe', '', 42, true]) {
    await checkIn(await makeCtx(store, objects, key, { agnes_remembered: value }));
  }
  assert.equal(store.counts.put, 0);
  assert.equal((await session(store, objects, key)).agnes_remembered, 'no');
});

test('the phone may not report either field (SPEC §3)', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store, 'link');
  await putOrder(store, clientId, 'r_a1b2c3d4');
  store.counts.put = 0;
  const routed = await checkIn(await makeCtx(store, objects, key, {
    agnes_remembered: 'yes',
    agnes_progress: { r_a1b2c3d4: { clips_total: 30, clips_done: 30 } },
  }));
  assert.equal(routed, null, 'the check-in still reaches index.js');
  assert.equal(store.counts.put, 0, 'a link key stores nothing');
  const out = await session(store, objects, key);
  assert.equal(out.agnes_remembered, 'unknown');
  assert.deepEqual(out.agnes_progress, {});
});

test('a check-in with no Agnes fields does no storage work at all', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store, 'box');
  await putOrder(store, clientId, 'r_a1b2c3d4');
  const ctx = await makeCtx(store, objects, key, { orders: true });
  store.counts.put = 0;
  store.counts.get = 0;
  store.counts.list = 0;
  const routed = await checkIn(ctx);
  assert.equal(routed, null);
  assert.deepEqual(store.counts, { put: 0, get: 0, list: 0 }, 'a check-in without the Agnes fields reads and writes nothing here');
});

// ---------------------------------------------------------------------------
// per-project progress
// ---------------------------------------------------------------------------

test('progress lands on the project\'s own status record and repeats write nothing', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store, 'box');
  await putOrder(store, clientId, 'r_a1b2c3d4');
  const progress = { clips_total: 30, clips_done: 12, in_flight: 2, waiting_reason: null, eta_minutes_low: 84, eta_minutes_high: 96, updated_utc: '2026-10-13T12:00:00Z' };

  await checkIn(await makeCtx(store, objects, key, { agnes_progress: { r_a1b2c3d4: progress } }));
  const order = JSON.parse(await store.kvGet(`order:${clientId}:r_a1b2c3d4`));
  assert.deepEqual(order.agnes_progress, progress);
  assert.equal(order.state, 'in_production', 'the order record keeps everything else it held');
  assert.equal((await session(store, objects, key)).agnes_progress.r_a1b2c3d4.clips_done, 12);

  store.counts.put = 0;
  for (let i = 0; i < 5; i += 1) {
    await checkIn(await makeCtx(store, objects, key, { agnes_progress: { r_a1b2c3d4: progress } }));
  }
  assert.equal(store.counts.put, 0, 'five unchanged progress reports write nothing');
});

test('a progress record that moved on is written once', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store, 'box');
  await putOrder(store, clientId, 'r_a1b2c3d4');
  await checkIn(await makeCtx(store, objects, key, {
    agnes_progress: { r_a1b2c3d4: { clips_total: 30, clips_done: 12 } },
  }));
  store.counts.put = 0;
  await checkIn(await makeCtx(store, objects, key, {
    agnes_progress: { r_a1b2c3d4: { clips_total: 30, clips_done: 14 } },
  }));
  assert.equal(store.counts.put, 1);
  assert.equal((await session(store, objects, key)).agnes_progress.r_a1b2c3d4.clips_done, 14);
});

test('the bridge may send one record carrying order_id instead of the whole map', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store, 'machine');
  await putOrder(store, clientId, 'r_a1b2c3d4');
  const record = { order_id: 'r_a1b2c3d4', clips_total: 4, clips_done: 1, in_flight: 2, waiting_reason: 'agnes-video-running' };
  await checkIn(await makeCtx(store, objects, key, { agnes_progress: record }));
  assert.deepEqual((await session(store, objects, key)).agnes_progress, { r_a1b2c3d4: record });
});

test('progress for a project this client does not own writes nothing', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { key } = await clientWithKey(store, 'box');
  store.counts.put = 0;
  await checkIn(await makeCtx(store, objects, key, { agnes_progress: { r_deadbeef: { clips_total: 4, clips_done: 1 } } }));
  assert.equal(store.counts.put, 0, 'an id with no record under this client writes nothing');
  assert.deepEqual((await session(store, objects, key)).agnes_progress, {});
});

test('a progress body that is not an object is ignored, never a crash', async () => {
  const store = countingStore();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store, 'box');
  await putOrder(store, clientId, 'r_a1b2c3d4');
  store.counts.put = 0;
  for (const value of ['progress', 7, [1, 2], { r_a1b2c3d4: 'nope' }]) {
    await checkIn(await makeCtx(store, objects, key, { agnes_progress: value }));
  }
  assert.equal(store.counts.put, 0);
});
