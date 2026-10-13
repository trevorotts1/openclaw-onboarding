// ============================================================================
// inbox-freshness.test.mjs — DSF-611 regression: the order the phone just
// created must be in the inbox object on the box's very FIRST read.
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/inbox-freshness.test.mjs
//
// SPEC §5: a box's poll claims a new order within 2 minutes of Lock it in.
// Measured on the live Worker (references/studio-e2e-receipt.md, "SPEC section
// 8 line 5b"): 11 min 49 s, because POST /api/studio/orders rebuilt
// clients/<id>/inbox.json from waitingList() = kvList(store, 'order.<id>.') —
// a Cloudflare KV LIST taken in the SAME request that kvPut that very order.
// KV list is eventually consistent, so the new key was not in the list and the
// object was stored with orders:[]; nothing refreshes it until an unrelated
// state or cancel event rewrites the object.
//
// Cloudflare KV list lag is not observable in-process, so the store used here
// is the honest instrument: its kvList NEVER returns a key written during the
// run (the live object stayed empty for 11 min 49 s until an unrelated event),
// while kvGet returns it immediately. The lag is asserted, not assumed — if
// the fake stops lagging the control assertion below goes red instead of the
// suite silently passing for the wrong reason.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { buildKeyRecord, mintKey } from '../src/keys.js';
import { randomClientId } from '../src/ids.js';
import { readInbox } from '../src/inbox.js';
import { handle } from '../src/index.js';
import { memObjects, post } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 13, 12, 0, 0);
const GOOD_ENV = {
  DS_ENROLLMENT_SECRET: 'enrollment-secret-placeholder-for-tests',
  DS_ADMIN_KEY: 'admin-key-placeholder-for-tests',
  R2_ACCOUNT_ID: 'fakeaccountid',
  R2_ACCESS_KEY_ID: 'fakeaccesskey',
  R2_SECRET_ACCESS_KEY: 'fakesecret',
  DRAMA_STUDIO_BUCKET: 'drama-studio',
};

/** A store whose LIST lags exactly the way Cloudflare KV's does. */
function laggingKv() {
  const mem = new Map();
  const settled = new Set(); // the only keys kvList may ever return
  return {
    kvGet: async (k) => (mem.has(k) ? mem.get(k) : null),
    kvPut: async (k, v) => {
      mem.set(k, v);
    },
    kvDelete: async (k) => {
      mem.delete(k);
    },
    kvList: async (prefix) => [...mem.keys()].filter((k) => k.startsWith(prefix) && settled.has(k)),
    /** Instrument control: make every key listable, as it would be later. */
    settle: () => {
      for (const k of mem.keys()) settled.add(k);
    },
    _mem: mem,
  };
}

/** The store shape the rest of the suite uses — list is immediately fresh. */
function freshKv() {
  const mem = new Map();
  return {
    kvGet: async (k) => (mem.has(k) ? mem.get(k) : null),
    kvPut: async (k, v) => {
      mem.set(k, v);
    },
    kvDelete: async (k) => {
      mem.delete(k);
    },
    kvList: async (prefix) => [...mem.keys()].filter((k) => k.startsWith(prefix)),
    _mem: mem,
  };
}

async function clientWithKey(store, kind = 'link') {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret };
}

// ---------------------------------------------------------------------------
// The instrument itself — a lagging list must be proved lagging, and a fresh
// one must be proved fresh, otherwise a red/green split means nothing.
// ---------------------------------------------------------------------------

test('DSF-611 instrument: the lagging store withholds the new key from LIST while GET sees it', async () => {
  const lagging = laggingKv();
  const fresh = freshKv();
  const { clientId, key } = await clientWithKey(lagging);
  await clientWithKey(fresh);

  const created = await handle(post('/api/studio/orders', { title: 'Spring Sale' }, key), GOOD_ENV, lagging, memObjects());
  assert.equal(created.status, 201);
  const orderId = (await created.json()).order.order_id;

  // Same key name, same prefix, two stores of the same shape.
  assert.ok(await lagging.kvGet(`order:${clientId}:${orderId}`), 'GET sees the record it just wrote');
  assert.deepEqual(
    await lagging.kvList(`order:${clientId}:`),
    [],
    'LIST does not — the lag this regression test exists to model',
  );

  // Positive control on the same instrument: nothing but freshness differs.
  const freshStore = freshKv();
  const other = await clientWithKey(freshStore);
  const ok = await handle(post('/api/studio/orders', { title: 'Spring Sale' }, other.key), GOOD_ENV, freshStore, memObjects());
  assert.equal(ok.status, 201);
  assert.equal((await freshStore.kvList(`order:${other.clientId}:`)).length, 1, 'a fresh list does return the new key');
});

// ---------------------------------------------------------------------------
// The regression: create -> very next read of the inbox -> the order is there.
// No state event, no cancel, no sleep, no second request that rewrites it.
// ---------------------------------------------------------------------------

test('DSF-611: the created order is in the inbox object on the very next read (no state event, no sleep)', async () => {
  const store = laggingKv();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  const created = await handle(post('/api/studio/orders', { title: 'Spring Sale' }, key), GOOD_ENV, store, objects);
  assert.equal(created.status, 201);
  const orderId = (await created.json()).order.order_id;

  // The very next read of clients/<id>/inbox.json — nothing runs in between.
  const inbox = await readInbox(objects, clientId);
  assert.deepEqual(
    inbox.waiting.map((o) => o.order_id),
    [orderId],
    'the order Lock it in just created must be in the inbox the box reads',
  );
  assert.equal(inbox.waiting[0].title, 'Spring Sale');
  assert.equal(inbox.waiting[0].state, 'waiting');
});

test('DSF-611: the box’s first check-in after Lock it in prints the DRAMA_ORDER line', async () => {
  const store = laggingKv();
  const objects = memObjects();
  const { key } = await clientWithKey(store);

  const created = await handle(post('/api/studio/orders', { title: 'Spring Sale' }, key), GOOD_ENV, store, objects);
  assert.equal(created.status, 201);
  const orderId = (await created.json()).order.order_id;

  // A box's check-in sends no orders array — it only READS the inbox.
  const poll = await handle(post('/api/studio/checkin', {}, key), GOOD_ENV, store, objects);
  assert.equal(poll.status, 200);
  assert.equal(
    (await poll.json()).line,
    `DRAMA_ORDER ${orderId} "Spring Sale"`,
    'SPEC §5: the first poll after Lock it in must name the order',
  );
});

test('DSF-611: creating an order never LISTs KV at all — the inbox comes from the object, not a list', async () => {
  // The same store, minus the lag question: LIST is made to fail outright, so
  // "the order-created path no longer derives the inbox from a KV list" is a
  // behaviour, not a timing assumption.
  const store = laggingKv();
  store.kvList = async () => {
    throw new Error('kvList must not be consulted while creating an order');
  };
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  const created = await handle(post('/api/studio/orders', { title: 'Spring Sale' }, key), GOOD_ENV, store, objects);
  assert.equal(created.status, 201, 'order creation must not depend on a KV LIST');
  const orderId = (await created.json()).order.order_id;

  const poll = await handle(post('/api/studio/checkin', {}, key), GOOD_ENV, store, objects);
  assert.equal((await poll.json()).line, `DRAMA_ORDER ${orderId} "Spring Sale"`);
  assert.equal((await readInbox(objects, clientId)).waiting.length, 1);
});

test('DSF-611: a second order joins the first instead of replacing it (read-modify-write of one object)', async () => {
  const store = laggingKv();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  const first = await handle(post('/api/studio/orders', { title: 'First' }, key), GOOD_ENV, store, objects);
  const firstId = (await first.json()).order.order_id;
  const second = await handle(post('/api/studio/orders', { title: 'Second' }, key), GOOD_ENV, store, objects);
  const secondId = (await second.json()).order.order_id;

  assert.deepEqual(
    (await readInbox(objects, clientId)).waiting.map((o) => o.order_id),
    [firstId, secondId],
    'the inbox is rebuilt from its own content plus the new order — never from a KV list',
  );
});

test('DSF-611: re-posting the same order id does not duplicate it in the inbox', async () => {
  const store = laggingKv();
  const objects = memObjects();
  const { clientId, key } = await clientWithKey(store);

  const orderId = `r_${'b'.repeat(8)}`;
  const first = await handle(post('/api/studio/orders', { title: 'Once', order_id: orderId }, key), GOOD_ENV, store, objects);
  assert.equal(first.status, 201);
  const again = await handle(post('/api/studio/orders', { title: 'Once', order_id: orderId }, key), GOOD_ENV, store, objects);
  assert.equal(again.status, 201);

  const waiting = (await readInbox(objects, clientId)).waiting;
  assert.deepEqual(waiting.map((o) => o.order_id), [orderId]);
});
