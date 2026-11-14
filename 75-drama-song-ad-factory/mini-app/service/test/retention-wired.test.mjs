// ============================================================================
// retention-wired.test.mjs — U-GEN309 (S75-083)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/retention-wired.test.mjs
//
// S75-083: `retention.js` is the service's own deletion rule and production
// never imported it, so nothing stored ever expired. These assertions hold the
// wiring in place: the rule is imported under src/, the sweep calls it, the
// check-in route runs the sweep, and the sweep deletes only what the rule names.
//
// The sweep reads the record columns retention.js reads. U-GEN310 corrects
// those column names, so this file probes the loaded rule once and builds its
// fixture in whichever shape the module in the tree uses; either way the same
// behaviour is asserted.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { DAY_MS, dueForDeletion } from '../src/retention.js';
import * as serviceIndex from '../src/index.js';
import { memStore } from './fakes.mjs';

// fileURLToPath, not `.pathname`: the drive path has spaces in it.
const SRC = fileURLToPath(new URL('../src/', import.meta.url));
const T0 = 1_790_000_000_000;
const CLIENT_A = 'c-0000000000000000000000000000000a';
const CLIENT_B = 'c-0000000000000000000000000000000b';

/** The stored-record columns, in the shape this tree's sweep reads.
 *  Probed through `dueForDeletion`, the entry point the sweep itself uses, so
 *  the probe cannot pass on a shape that the reader does not honour. */
const CLOCK = dueForDeletion(
  [{ kind: 'status_record', path: 'probe', created_at_ms: T0, event_at_ms: T0 }],
  T0 + 31 * DAY_MS,
).delete.length === 1
  ? { created_at_ms: T0, event_at_ms: T0 }
  : { created_at: T0, delivered_at: T0 };

function srcIndex() {
  return readFileSync(join(SRC, 'index.js'), 'utf8');
}

test('retention is imported under src/ by production code', () => {
  const importers = readdirSync(SRC)
    .filter((n) => n.endsWith('.js'))
    .filter((n) => /^\s*import\b[^;]*from\s+['"]\.\/retention\.js['"]/m.test(readFileSync(join(SRC, n), 'utf8')));
  assert.ok(importers.length >= 1, 'no src/ module imports ./retention.js — the rule is never loaded');
});

test('the sweep reaches dueForDeletion', () => {
  const src = srcIndex();
  assert.match(src, /dueForDeletion\(/, 'no production code calls dueForDeletion');
});

test('the check-in route runs the sweep', () => {
  const src = srcIndex();
  const route = src.slice(src.indexOf("url.pathname === '/api/studio/checkin'"));
  assert.match(route, /sweepExpiredRecords\(store, clientId, nowMs\)/, 'the check-in route does not call the sweep');
});

const sweep = (store, clientId, nowMs) => serviceIndex.sweepExpiredRecords(store, clientId, nowMs);

test('the service exports the sweep that calls the rule', () => {
  assert.equal(typeof serviceIndex.sweepExpiredRecords, 'function', 'the service exports no sweep');
});

test('a tagged record whose clock is up is deleted by the sweep', async () => {
  const store = memStore();
  const key = `order:${CLIENT_A}:r_1a2b3c4d`;
  await store.kvPut(key, JSON.stringify({
    order_id: 'r_1a2b3c4d', client_id: CLIENT_A, state: 'delivered',
    retention_kind: 'status_record', ...CLOCK,
  }));
  const out = await sweep(store, CLIENT_A, T0 + 31 * DAY_MS);
  assert.equal(out.swept, 1);
  assert.equal(await store.kvGet(key), null, 'a due record must be gone');
});

test('a record with no retention tag is never swept', async () => {
  const store = memStore();
  const key = `order:${CLIENT_A}:r_untagged`;
  await store.kvPut(key, JSON.stringify({ order_id: 'r_untagged', state: 'delivered', ...CLOCK }));
  const out = await sweep(store, CLIENT_A, T0 + 3650 * DAY_MS);
  assert.equal(out.swept, 0);
  assert.notEqual(await store.kvGet(key), null, 'an untagged record is not a retention object');
});

test('a kind the rule does not know is kept, and only the caller own records are read', async () => {
  const store = memStore();
  const unknown = `order:${CLIENT_A}:r_mystery`;
  const other = `order:${CLIENT_B}:r_other`;
  await store.kvPut(unknown, JSON.stringify({ order_id: 'r_mystery', retention_kind: 'mystery', ...CLOCK }));
  await store.kvPut(other, JSON.stringify({ order_id: 'r_other', retention_kind: 'status_record', ...CLOCK }));
  const out = await sweep(store, CLIENT_A, T0 + 3650 * DAY_MS);
  assert.equal(out.swept, 0);
  assert.notEqual(await store.kvGet(unknown), null, 'an unknown kind is never deleted');
  assert.notEqual(await store.kvGet(other), null, "another client's record is never reached");
});
