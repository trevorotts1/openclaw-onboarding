// ============================================================================
// revoke.test.mjs — Drama Studio service: cutting off a leaked key (U-Z12)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/revoke.test.mjs
//
// S75-103. The admin route POST /api/studio/admin/revoke { admin_key,
// client_id, kind } marks every ACTIVE key record of one client and one kind
// `revoked` and answers how many it cut. The acceptance, from the unit:
//   - after revoke the old box key gets AF-DS-KEY-REVOKED on check-in
//   - the client's link key still works
//   - another client's keys are untouched
// Plus the shape the route must keep: it never takes or returns a key value,
// and only "box" and "machine" may be cut off here.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { handle } from '../src/index.js';
import { buildKeyRecord, mintKey } from '../src/keys.js';
import { resolveKey } from '../src/isolation.js';
import { randomClientId } from '../src/ids.js';
import { memObjects, memStore, post } from './fakes.mjs';

const T0 = Date.UTC(2026, 10, 12, 12, 0, 0);
const ADMIN_KEY = 'admin-key-placeholder-for-tests';

const ENV = { DS_ADMIN_KEY: ADMIN_KEY };

/** Mint one real key record of `kind` for `clientId` and store it, exactly as
 *  enrollment and pairing do. Returns the raw secret, which is never stored. */
async function keyFor(store, clientId, kind) {
  const minted = await mintKey();
  const record = await buildKeyRecord({ clientId, kind, secret: minted.secret, nowMs: T0 });
  await store.kvPut(`key:${record.fingerprint}`, JSON.stringify(record));
  return { key: minted.secret, record };
}

function revoke({ store, objects, clientId, kind, adminKey = ADMIN_KEY }) {
  return handle(post('/api/studio/admin/revoke', { admin_key: adminKey, client_id: clientId, kind }), ENV, store, objects);
}

function checkIn(store, objects, key) {
  return handle(post('/api/studio/checkin', {}, key), ENV, store, objects);
}

test('revoke: the box key is cut off, the link key still works, another client is untouched', async () => {
  const store = memStore();
  const objects = memObjects();
  const clientId = randomClientId();
  const otherClient = randomClientId();

  const box = await keyFor(store, clientId, 'box');
  const machine = await keyFor(store, clientId, 'machine');
  const link = await keyFor(store, clientId, 'link');
  const otherBox = await keyFor(store, otherClient, 'box');

  // Before the cut every key checks in.
  assert.equal((await checkIn(store, objects, box.key)).status, 200);
  assert.equal((await checkIn(store, objects, otherBox.key)).status, 200);

  const res = await revoke({ store, objects, clientId, kind: 'box' });
  assert.equal(res.status, 200);
  const json = await res.json();
  assert.equal(json.ok, true);
  assert.equal(json.client_id, clientId);
  assert.equal(json.kind, 'box');
  assert.equal(json.revoked, 1, 'exactly the one active box key is cut');

  // The route never takes or hands back a key VALUE.
  assert.equal('key' in json, false);
  assert.equal(JSON.stringify(json).includes(box.key), false);
  assert.equal(JSON.stringify(json).includes(box.record.fingerprint), false);

  // The old box key is refused at its very next check-in.
  const refused = await checkIn(store, objects, box.key);
  assert.equal(refused.status, 401);
  assert.equal((await refused.json()).code, 'AF-DS-KEY-REVOKED');

  // The client's link key and computer key still work.
  assert.equal((await resolveKey(store, link.key)).ok, true, 'a link is rotated, never cut here');
  assert.equal((await checkIn(store, objects, link.key)).status, 200);
  assert.equal((await checkIn(store, objects, machine.key)).status, 200);

  // Another client's box key is untouched, and so is its record status.
  assert.equal((await checkIn(store, objects, otherBox.key)).status, 200);
  const otherRaw = JSON.parse(await store.kvGet(`key:${otherBox.record.fingerprint}`));
  assert.equal(otherRaw.status, 'active');

  // A second call finds nothing active: it cuts 0 and changes nothing.
  const again = await revoke({ store, objects, clientId, kind: 'box' });
  assert.equal((await again.json()).revoked, 0);

  // Cutting the computer key leaves the link and the other client alone.
  const cutMachine = await revoke({ store, objects, clientId, kind: 'machine' });
  assert.equal((await cutMachine.json()).revoked, 1);
  const machineRefused = await checkIn(store, objects, machine.key);
  assert.equal(machineRefused.status, 401);
  assert.equal((await machineRefused.json()).code, 'AF-DS-KEY-REVOKED');
  assert.equal((await checkIn(store, objects, link.key)).status, 200);
  assert.equal((await checkIn(store, objects, otherBox.key)).status, 200);
});

test('revoke: a wrong admin key, a missing client and an unknown kind are all refused and cut nothing', async () => {
  const store = memStore();
  const objects = memObjects();
  const clientId = randomClientId();
  const box = await keyFor(store, clientId, 'box');
  const link = await keyFor(store, clientId, 'link');

  const wrongAdmin = await revoke({ store, objects, clientId, kind: 'box', adminKey: 'wrong' });
  assert.equal(wrongAdmin.status, 403);
  assert.equal((await wrongAdmin.json()).code, 'AF-DS-ADMIN-REFUSED');

  const noClient = await handle(post('/api/studio/admin/revoke', { admin_key: ADMIN_KEY, kind: 'box' }), ENV, store, objects);
  assert.equal(noClient.status, 400);
  assert.equal((await noClient.json()).code, 'AF-DS-ADMIN-INVALID');

  const badClient = await revoke({ store, objects, clientId: 'not-a-studio-id', kind: 'box' });
  assert.equal(badClient.status, 400);
  assert.equal((await badClient.json()).code, 'AF-DS-ADMIN-INVALID');

  // A personal link is rotated by minting a new one (link.js), never cut here.
  const linkKind = await revoke({ store, objects, clientId, kind: 'link' });
  assert.equal(linkKind.status, 400);
  assert.equal((await linkKind.json()).code, 'AF-DS-ADMIN-INVALID');

  const badKind = await revoke({ store, objects, clientId, kind: 'everything' });
  assert.equal(badKind.status, 400);
  assert.equal((await badKind.json()).code, 'AF-DS-ADMIN-INVALID');

  // Every refusal above left both keys exactly as they were.
  assert.equal((await checkIn(store, objects, box.key)).status, 200);
  assert.equal((await checkIn(store, objects, link.key)).status, 200);
});
