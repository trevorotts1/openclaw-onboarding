// ============================================================================
// retention-real-records.test.mjs — Drama Studio service: the sweep reads the
// keys the store actually writes (U-GEN310, finding S75-083).
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/retention-real-records.test.mjs
//
// Before this fix `dueForDeletion` read `created_at_ms` / `event_at_ms`. No
// writer in the service produces either name: `lifecycle.transition` stamps
// `<state>_at` on the order record, `approvals-api.composeReady` writes
// `finalized_at` beside the frozen approval files, and the order record itself
// carries `created_at` and `delivered_at` (schema.sql sections 4 and R2). Both
// reads were therefore undefined on every stored record, every kind returned
// `awaiting-event` -> keep, and the sweep ran and deleted nothing.
//
// Every record below is built from schema.sql's own column names. If the sweep
// goes back to invented keys, the first assertion fails because a record the
// store really writes is left in `keep`.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';

import { DAY_MS, dueForDeletion } from '../src/retention.js';

const T0 = 1_790_000_000_000;
const day = DAY_MS;

/** A delivered order record, exactly the columns schema.sql section 4 names. */
function deliveredOrder() {
  return {
    order_id: 'r_1a2b3c4d',
    client_id: 'c-00000000000000000000000000000001',
    state: 'delivered',
    created_at: T0 - 40 * day,
    updated_at: T0,
    in_production_at: T0 - 39 * day,
    delivered_at: T0,
    accepted_at: null,
    downloaded_at: null,
    last_actor: 'box',
  };
}

test('the sweep deletes a real delivered record once its clock is up', () => {
  const order = deliveredOrder();
  const out = dueForDeletion([
    { ...order, kind: 'r2_fallback_video', path: 'clients/c-00000000000000000000000000000001/video/final.mp4' },
    { ...order, kind: 'status_record', path: 'clients/c-00000000000000000000000000000001/status.json' },
  ], T0 + 30 * day);

  assert.deepEqual(out.delete.sort(), [
    'clients/c-00000000000000000000000000000001/status.json',
    'clients/c-00000000000000000000000000000001/video/final.mp4',
  ], 'a due record from the real store must be classified delete');
  assert.deepEqual(out.keep, []);
});

test('the same real record is kept before its clock is up', () => {
  const order = deliveredOrder();
  const out = dueForDeletion([
    { ...order, kind: 'r2_fallback_video', path: 'clients/x/video/final.mp4' },
  ], T0 + 7 * day - 1);
  assert.deepEqual(out.delete, []);
  assert.deepEqual(out.keep, ['clients/x/video/final.mp4']);
});

test('a real record with no delivery yet is kept, never swept', () => {
  const order = { ...deliveredOrder(), state: 'in_production', delivered_at: null };
  const out = dueForDeletion([
    { ...order, kind: 'r2_fallback_video', path: 'clients/x/video/final.mp4' },
  ], T0 + 400 * day);
  assert.deepEqual(out.delete, []);
});

test('the sweep reads the pickup and stage-approved columns the store writes', () => {
  const waiting = {
    order_id: 'r_1a2b3c4d',
    client_id: 'c-00000000000000000000000000000001',
    state: 'waiting',
    created_at: T0 - 40 * day,
    updated_at: T0 - 40 * day,
    delivered_at: null,
  };
  const intake = { ...waiting, kind: 'intake_answer', path: 'clients/x/intake/a.json' };
  assert.deepEqual(dueForDeletion([intake], T0).keep, ['clients/x/intake/a.json'],
    'not picked up yet: kept, never swept');

  const pickedUp = { ...intake, in_production_at: T0 - day };
  assert.deepEqual(dueForDeletion([pickedUp], T0).delete, ['clients/x/intake/a.json'],
    'in_production_at is the pickup clock');

  const finalized = { ...waiting, kind: 'approval_file', path: 'clients/x/approval.png', finalized_at: T0 - day };
  assert.deepEqual(dueForDeletion([finalized], T0).delete, ['clients/x/approval.png'],
    'finalized_at is the stage-approved clock');
});

test('the sweep reads created_at for the 45-day clocks', () => {
  const record = {
    order_id: 'r_1a2b3c4d',
    client_id: 'c-00000000000000000000000000000001',
    state: 'waiting',
    created_at: T0 - 45 * day,
    updated_at: T0 - 45 * day,
  };
  const out = dueForDeletion([
    { ...record, kind: 'waiting_unclaimed', path: 'clients/x/inbox.json' },
    { ...record, kind: 'project_object', path: 'clients/x/project.json' },
  ], T0);
  assert.deepEqual(out.delete.sort(), ['clients/x/inbox.json', 'clients/x/project.json']);
});

test('a protected class is still never swept, whatever columns it carries', () => {
  const order = deliveredOrder();
  const out = dueForDeletion([
    { ...order, kind: 'enrollment_record', path: 'clients/x/enrollment.json' },
    { ...order, kind: 'delivery_receipt', path: 'clients/x/receipt.json' },
    { ...order, kind: 'ghl_media', path: 'clients/x/ghl.json' },
  ], T0 + 3650 * day);
  assert.deepEqual(out.delete, []);
  assert.equal(out.never.length, 3);
});
