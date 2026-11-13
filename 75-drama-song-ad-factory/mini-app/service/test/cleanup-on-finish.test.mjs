// ============================================================================
// cleanup-on-finish.test.mjs — U-Z07 (S75-083)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/cleanup-on-finish.test.mjs
//
// A finished order keeps nothing it no longer needs: on deliver, done or cancel
// the service deletes the order's intake objects (found through its upload job
// records) and its approval `staging/` copies. It keeps `files/`, `ready.json`
// and `decision.json` — the page still shows those.
//
// A store that refuses a delete does NOT fail the state change: the order is
// still delivered, and the record says `cleanup_pending: true` so the failure is
// visible instead of silent.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { handle } from '../src/index.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { randomClientId } from '../src/ids.js';
import { get, memStore, post } from './fakes.mjs';

const T0 = Date.UTC(2026, 9, 10, 12, 0, 0);

/** An object store with the one capability cleanup needs beyond get/put:
 *  delete, and a prefix list to find the staging copies. */
function memFiles({ deleteThrows = false } = {}) {
  const files = new Map();
  return {
    _files: files,
    objectGet: async (p) => (files.has(p) ? { value: files.get(p) } : null),
    objectPut: async (p, v) => {
      files.set(p, v);
    },
    objectDelete: async (p) => {
      if (deleteThrows) throw new Error('the bucket refused the delete');
      files.delete(p);
    },
    objectList: async (prefix) => [...files.keys()].filter((k) => k.startsWith(prefix)),
  };
}

async function boxWithKey(store) {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind: 'box', secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret };
}

test('U-Z07: a delivered order leaves neither intake object in the bucket', async () => {
  const store = memStore();
  const objects = memFiles();
  const { clientId, key } = await boxWithKey(store);

  const intake = [
    `clients/${clientId}/intake/u_1.jpg`,
    `clients/${clientId}/intake/u_2.jpg`,
  ];
  for (const [i, path] of intake.entries()) {
    await store.kvPut(`upload:${clientId}:u_${i + 1}`, JSON.stringify({ upload_id: `u_${i + 1}`, object_path: path }));
    objects._files.set(path, 'the client photo');
  }

  const created = await handle(
    post('/api/studio/orders', { title: 'Spring Sale', replies: ['1'], upload_ids: ['u_1', 'u_2'] }, key),
    {}, store, objects,
  );
  const orderId = (await created.json()).order.order_id;

  // The order's own approval staging copy, beside the frozen copy the page
  // still needs and the two records that stay answerable.
  const stageDir = `clients/${clientId}/orders/${orderId}/approvals-v2/script-v1`;
  objects._files.set(`${stageDir}/staging/take1.mp3`, 'staged bytes');
  objects._files.set(`${stageDir}/files/take1.mp3`, 'frozen bytes');
  objects._files.set(`${stageDir}/ready.json`, '{"stage":"script","version":1}');

  for (const event of ['claim', 'ready']) {
    const moved = await handle(post(`/api/studio/orders/${orderId}/state`, { event }, key), {}, store, objects);
    assert.equal(moved.status, 200, event);
  }
  const delivered = await handle(
    post(`/api/studio/orders/${orderId}/state`, {
      event: 'deliver',
      delivery: { url: 'https://media.example/v/1', kind: 'ghl' },
    }, key),
    {}, store, objects,
  );
  assert.equal(delivered.status, 200);
  assert.equal((await delivered.json()).order.state, 'delivered');
  assert.equal((await delivered.json()).order.cleanup_pending, undefined, 'a clean delete is not flagged');

  for (const path of intake) {
    assert.equal(objects._files.has(path), false, `${path} was deleted`);
  }
  assert.equal(objects._files.has(`${stageDir}/staging/take1.mp3`), false, 'the staging copy was deleted');
  assert.equal(objects._files.has(`${stageDir}/files/take1.mp3`), true, 'the frozen copy stays for the page');
  assert.equal(objects._files.has(`${stageDir}/ready.json`), true, 'the ready record stays answerable');
});

test('U-Z07: a cancel deletes the intake objects too', async () => {
  const store = memStore();
  const objects = memFiles();
  const { clientId, key } = await boxWithKey(store);

  const path = `clients/${clientId}/intake/u_9.jpg`;
  await store.kvPut(`upload:${clientId}:u_9`, JSON.stringify({ upload_id: 'u_9', object_path: path }));
  objects._files.set(path, 'the client photo');

  const created = await handle(
    post('/api/studio/orders', { title: 'Spring Sale', upload_ids: ['u_9'] }, key),
    {}, store, objects,
  );
  const orderId = (await created.json()).order.order_id;

  const cancelled = await handle(post(`/api/studio/orders/${orderId}/cancel`, {}, key), {}, store, objects);
  assert.equal(cancelled.status, 200);
  assert.equal((await cancelled.json()).order.state, 'cancelled');
  assert.equal(objects._files.has(path), false, 'a cancelled order keeps no intake file');
});

test('U-Z07: a delete that throws still delivers, and the order says cleanup_pending', async () => {
  const store = memStore();
  const objects = memFiles({ deleteThrows: true });
  const { clientId, key } = await boxWithKey(store);

  const path = `clients/${clientId}/intake/u_1.jpg`;
  await store.kvPut(`upload:${clientId}:u_1`, JSON.stringify({ upload_id: 'u_1', object_path: path }));
  objects._files.set(path, 'the client photo');

  const created = await handle(
    post('/api/studio/orders', { title: 'Spring Sale', upload_ids: ['u_1'] }, key),
    {}, store, objects,
  );
  const orderId = (await created.json()).order.order_id;

  for (const event of ['claim', 'ready']) {
    const moved = await handle(post(`/api/studio/orders/${orderId}/state`, { event }, key), {}, store, objects);
    assert.equal(moved.status, 200, event);
  }
  const delivered = await handle(
    post(`/api/studio/orders/${orderId}/state`, {
      event: 'deliver',
      delivery: { url: 'https://media.example/v/1', kind: 'ghl' },
    }, key),
    {}, store, objects,
  );
  assert.equal(delivered.status, 200, 'a refused delete never fails the delivery');
  assert.equal((await delivered.json()).order.state, 'delivered');

  const read = await handle(get(`/api/studio/orders/${orderId}`, key), {}, store, objects);
  assert.equal((await read.json()).order.cleanup_pending, true, 'the failed delete is on the record');
});
