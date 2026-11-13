// ============================================================================
// upload-file.test.mjs — U-Z08: the studio can read the file a client sent
//
//   node --test mini-app/service/test/upload-file.test.mjs
//
// Proves the new read route and the order's upload check:
//   * the owner's box key gets the exact bytes back;
//   * the same client's LINK key is refused 403 (a link is a screen, not a
//     key to pull files);
//   * another client's box key answers 404, the same as an id that never was;
//   * a job with no object yet is 404 AF-DS-UP-NOT-ARRIVED;
//   * an order naming an upload id with no job record is refused 400.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { buildKeyRecord, mintKey } from '../src/keys.js';
import { randomClientId } from '../src/ids.js';
import { AF_UP_NOT_ARRIVED, AF_UP_UNKNOWN, uploadKey } from '../src/uploads.js';
import { handle } from '../src/index.js';
import { get, memObjects, memR2Bucket, memStore, post } from './fakes.mjs';

const T0 = Date.UTC(2026, 10, 12, 12, 0, 0);
const BYTES = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3, 4]);

async function clientWithKey(store, kind) {
  const clientId = randomClientId();
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { clientId, key: minted.secret };
}

function jobFor(clientId, uploadId) {
  return {
    client_id: clientId,
    upload_id: uploadId,
    channel: 'image',
    object_path: `clients/${clientId}/intake/${uploadId}.png`,
    content_type: 'image/png',
    size_bytes: BYTES.byteLength,
    status: 'queued',
    created_at: T0,
  };
}

async function setup() {
  const store = memStore();
  const objects = memObjects();
  const bucket = memR2Bucket();
  const env = { DRAMA_STUDIO: bucket };
  const box = await clientWithKey(store, 'box');
  const link = await clientWithKey(store, 'link');
  const other = await clientWithKey(store, 'box');
  return { store, objects, bucket, env, box, link, other };
}

test('upload file: the owner box key gets the exact bytes', async () => {
  const { store, objects, bucket, env, box } = await setup();
  const uploadId = `u_${'a'.repeat(24)}`;
  const job = jobFor(box.clientId, uploadId);
  await store.kvPut(uploadKey(box.clientId, uploadId), JSON.stringify(job));
  await bucket.put(job.object_path, BYTES);

  const res = await handle(get(`/api/studio/uploads/${uploadId}/file`, box.key), env, store, objects);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('content-type'), 'image/png');
  assert.equal(res.headers.get('cache-control'), 'no-store');
  assert.deepEqual(new Uint8Array(await res.arrayBuffer()), BYTES);
});

test('upload file: the link key is refused 403', async () => {
  const { store, objects, bucket, env, box, link } = await setup();
  // Same client, so the record exists — the refusal is about the KEY's kind.
  const uploadId = `u_${'b'.repeat(24)}`;
  const job = jobFor(box.clientId, uploadId);
  await store.kvPut(uploadKey(box.clientId, uploadId), JSON.stringify(job));
  await bucket.put(job.object_path, BYTES);

  const res = await handle(get(`/api/studio/uploads/${uploadId}/file`, link.key), env, store, objects);
  assert.equal(res.status, 403);
  assert.equal((await res.json()).code, 'AF-DS-UP-KIND');
});

test('upload file: another client answers 404, as an unknown id does', async () => {
  const { store, objects, bucket, env, box, other } = await setup();
  const uploadId = `u_${'c'.repeat(24)}`;
  const job = jobFor(box.clientId, uploadId);
  await store.kvPut(uploadKey(box.clientId, uploadId), JSON.stringify(job));
  await bucket.put(job.object_path, BYTES);

  const crossed = await handle(get(`/api/studio/uploads/${uploadId}/file`, other.key), env, store, objects);
  assert.equal(crossed.status, 404);
  assert.equal((await crossed.json()).code, AF_UP_NOT_ARRIVED);

  const unknown = await handle(get(`/api/studio/uploads/u_${'d'.repeat(24)}/file`, box.key), env, store, objects);
  assert.equal(unknown.status, 404);
  assert.equal((await unknown.json()).code, AF_UP_NOT_ARRIVED);
});

test('upload file: a job with no object yet is 404 NOT-ARRIVED', async () => {
  const { store, objects, env, box } = await setup();
  const uploadId = `u_${'e'.repeat(24)}`;
  await store.kvPut(uploadKey(box.clientId, uploadId), JSON.stringify(jobFor(box.clientId, uploadId)));

  const res = await handle(get(`/api/studio/uploads/${uploadId}/file`, box.key), env, store, objects);
  assert.equal(res.status, 404);
  assert.equal((await res.json()).code, AF_UP_NOT_ARRIVED);
});

test('orders: an upload id with no job record is refused 400', async () => {
  const { store, objects, env, box } = await setup();
  const body = {
    title: 'Spring Sale',
    replies: ['1', '2'],
    upload_ids: [`u_${'f'.repeat(24)}`],
    order_id: 'r_0123abcd',
  };

  const res = await handle(post('/api/studio/orders', body, box.key), env, store, objects);
  assert.equal(res.status, 400);
  assert.equal((await res.json()).code, AF_UP_UNKNOWN);
  assert.equal(await store.kvGet(`order:${box.clientId}:r_0123abcd`), null, 'a refused order must not be stored');
});

test('orders: an upload id this client accepted is stored on the order', async () => {
  const { store, objects, env, box } = await setup();
  const uploadId = `u_${'9'.repeat(24)}`;
  await store.kvPut(uploadKey(box.clientId, uploadId), JSON.stringify(jobFor(box.clientId, uploadId)));

  const res = await handle(post('/api/studio/orders', {
    title: 'Spring Sale', replies: ['1', '2'], upload_ids: [uploadId], order_id: 'r_89abcdef',
  }, box.key), env, store, objects);
  assert.equal(res.status, 201);
  const stored = JSON.parse(await store.kvGet(`order:${box.clientId}:r_89abcdef`));
  assert.deepEqual(stored.upload_ids, [uploadId]);
});
