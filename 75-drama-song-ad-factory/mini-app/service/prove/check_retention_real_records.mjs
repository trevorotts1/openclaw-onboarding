// ============================================================================
// check_retention_real_records.mjs — U-GEN310 check (S75-083)
//
//   node 75-drama-song-ad-factory/mini-app/service/prove/check_retention_real_records.mjs
//
// Feeds one record built from schema.sql's own column names through the sweep
// and prints the delete/keep decision the sweep reaches. The same record, read
// with the keys the code used before the fix (`created_at_ms` / `event_at_ms`),
// prints `keep`: both are undefined on a stored record, so the pre-fix sweep
// ran and deleted nothing. Exits non-zero if the fixed sweep does not delete a
// record whose clock is up.
// ============================================================================

import { DAY_MS, dueForDeletion, retentionVerdict } from '../src/retention.js';

const T0 = 1_790_000_000_000;
const day = DAY_MS;

// An order record exactly as schema.sql section 4 names its columns.
const order = {
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

const items = [
  { ...order, kind: 'r2_fallback_video', path: 'clients/c-.../video/final.mp4' },
  { ...order, kind: 'status_record', path: 'clients/c-.../status.json' },
];
const nowMs = T0 + 30 * day;

const out = dueForDeletion(items, nowMs);
const verdicts = new Map(items.map((item) => [item.path, retentionVerdict(item.kind, { ...item, nowMs })]));

console.log(`sweep at day 30 after delivery (nowMs=${nowMs})`);
for (const item of items) {
  const decision = out.delete.includes(item.path) ? 'delete' : 'keep';
  const v = verdicts.get(item.path);
  console.log(`  ${item.kind.padEnd(18)} ${decision.padEnd(7)} ${item.path}  (${v.reason}, delete_at_ms=${v.delete_at_ms})`);
}

console.log('\nsame record under the keys used before the fix:');
for (const item of items) {
  const v = retentionVerdict(item.kind, {
    createdAtMs: item.created_at_ms,
    eventAtMs: item.event_at_ms,
    nowMs,
  });
  const decision = v.delete ? 'delete' : 'keep';
  console.log(`  ${item.kind.padEnd(18)} ${decision.padEnd(7)} ${item.path}  (${v.reason}, delete_at_ms=${v.delete_at_ms})`);
}

const failures = items.filter((item) => !out.delete.includes(item.path));
if (failures.length > 0) {
  console.log(`\nFAIL: ${failures.length} due record(s) kept; the sweep is reading keys the store does not write.`);
  process.exit(1);
}
console.log('\nPASS: every due record built from the schema\'s real columns is classified delete.');
