// ============================================================================
// retention.js — Drama Studio service: retention rule (U2)
//
// Joint plan section 3.15, "How long", and section 3.10A item 1 (the 45-day
// unclaimed-waiting expiry) and item 2 (the 14-day done timer is a STATUS
// marker; it never keeps or deletes a file).
//
// | Kind                 | Deleted                                          |
// | -------------------- | ------------------------------------------------ |
// | intake_answer        | at delivery, done or cancel (index.js, U-Z07)    |
// | intake_photo         | same as intake_answer                            |
// | approval_file        | when the stage is approved                       |
// | r2_fallback_video    | 7 days after delivery                            |
// | status_record        | 30 days after delivery                           |
// | waiting_unclaimed    | 45 days after the order was saved                |
// | project_object       | 45 days after creation (the storage rule)        |
// | enrollment_record    | NEVER — the scope rule excludes it               |
// | delivery_receipt     | NEVER                                            |
// | ghl_media            | NEVER — the studio never deletes a GHL copy      |
// | push_subscription    | NEVER — U20. A subscription is removed only by an  |
// |                      | explicit unsubscribe or a push service 404/410,    |
// |                      | never by a time sweep. The plan states no retention|
// |                      | for an optional version-2 push record, so the       |
// |                      | studio takes the never-surprise choice: a client    |
// |                      | never stops hearing from the studio on a timer.    |
//
// The approval `staging/` copies (approvals-v2) go at the same moment as the
// intake files: on deliver, done or cancel (index.js, U-Z07). The frozen
// `files/`, `ready.json` and `decision.json` are NOT deleted there — the page
// still shows them — and the bucket's 45-day rule removes them later.
//
// Section 3.15: "Deletion code does not exist in either live mini app today.
// It is new work (U2)." This module IS that work: it decides, it never
// blanket-deletes, and it refuses the never-delete classes by construction.
//
// Every retention-managed stored object carries one of these names in
// `retention_kind` (RETENTION_TAG_FIELD), written by the module that stores it.
// A credential record (a key) and the bare check-in millisecond count are not
// retention objects and carry no tag; they are revoked or overwritten, never
// swept, and the table names no class for them. Without the tag every real
// object reached this module as an unknown kind and was kept forever (S75-083).
//
// PURE. No bindings, no I/O, no clock of its own.
// ============================================================================

'use strict';

export const DAY_MS = 24 * 60 * 60 * 1000;

/** Where the clock starts for each kind. */
export const RETENTION_RULES = {
  intake_answer: { from: 'pickup', days: 0 },
  intake_photo: { from: 'pickup', days: 0 },
  approval_file: { from: 'stage_approved', days: 0 },
  r2_fallback_video: { from: 'delivered', days: 7 },
  status_record: { from: 'delivered', days: 30 },
  waiting_unclaimed: { from: 'created', days: 45 },
  project_object: { from: 'created', days: 45 },
  enrollment_record: { never: true },
  delivery_receipt: { never: true },
  ghl_media: { never: true },
  push_subscription: { never: true },
};

export const AF_RET_UNKNOWN_KIND = 'AF-DS-RET-UNKNOWN-KIND';
export const AF_RET_NO_EVENT = 'AF-DS-RET-NO-EVENT';

/**
 * The property every stored object carries, holding one of the names above.
 *
 * The service already uses `kind` for two other vocabularies — a key's role
 * ('link' | 'box' | 'machine', keys.js) and a delivery's transport ('ghl' |
 * 'r2', index.js) — so the retention tag is its own field and nothing already
 * stored is renamed. Writers emit THIS table's names; the two older
 * vocabularies stay as they are.
 */
export const RETENTION_TAG_FIELD = 'retention_kind';

/** True only for a name RETENTION_RULES knows. */
export function isRetentionKind(kind) {
  return typeof kind === 'string' && Object.prototype.hasOwnProperty.call(RETENTION_RULES, kind);
}

/**
 * Tag one stored record with the table name for its class. An unknown name
 * throws, the same way buildKeyRecord throws on an unknown key kind: a writer
 * can never store an object this sweep would fall back to unknown-kind -> keep.
 */
export function withRetentionKind(record, kind) {
  if (!isRetentionKind(kind)) throw new Error(AF_RET_UNKNOWN_KIND);
  return { ...record, [RETENTION_TAG_FIELD]: kind };
}

/**
 * The class a stored order record belongs to: an order nobody claimed is the
 * 45-day waiting class; every other state is the status record (30 days after
 * delivery). Computed at the writer, never guessed by the sweep.
 */
export function orderRetentionKind(order) {
  return order && order.state === 'waiting' ? 'waiting_unclaimed' : 'status_record';
}

/**
 * The column the store itself writes for each `from` moment. These are the names
 * the writers use — `lifecycle.js` stamps `<state>_at` on every move
 * (`claim`/`answer` -> `in_production_at`), `approvals-api.js` writes
 * `finalized_at` beside the frozen approval files, and the order record carries
 * `created_at` and `delivered_at`. This module never invents a column name.
 */
export const EVENT_COLUMN = {
  pickup: 'in_production_at',
  stage_approved: 'finalized_at',
  delivered: 'delivered_at',
};

/**
 * @param {string} kind
 * @param {{created_at?:number, in_production_at?:number, finalized_at?:number,
 *          delivered_at?:number, nowMs:number}} when
 *   The stored record, under the store's own column names, plus the sweep's
 *   `nowMs` clock. Which event column is read is decided by the rule's `from`
 *   (see EVENT_COLUMN).
 * @returns {{keep:boolean, delete:boolean, never:boolean, delete_at_ms:number|null, reason:string, code?:string}}
 */
export function retentionVerdict(kind, when) {
  const rule = RETENTION_RULES[kind];
  const nowMs = when && typeof when.nowMs === 'number' ? when.nowMs : 0;
  if (!rule) {
    return { keep: true, delete: false, never: false, delete_at_ms: null, reason: 'unknown-kind', code: AF_RET_UNKNOWN_KIND };
  }
  if (rule.never) {
    return { keep: true, delete: false, never: true, delete_at_ms: null, reason: 'never-delete' };
  }
  const startMs = rule.from === 'created' ? when.created_at : when[EVENT_COLUMN[rule.from]];
  if (typeof startMs !== 'number') {
    // No event has happened yet (nothing picked up, nothing delivered): there is
    // no clock running, so nothing is due. Never a silent delete.
    return { keep: true, delete: false, never: false, delete_at_ms: null, reason: 'awaiting-event', code: AF_RET_NO_EVENT };
  }
  const deleteAtMs = startMs + rule.days * DAY_MS;
  const due = nowMs >= deleteAtMs;
  return {
    keep: !due,
    delete: due,
    never: false,
    delete_at_ms: deleteAtMs,
    reason: `${kind}-from-${rule.from}`,
  };
}

/**
 * Partition a batch of stored items into delete / keep / never.
 * `never` items are returned separately so a caller can never lump them into a
 * delete sweep, and a caller that ignores the partition deletes nothing.
 *
 * The item is the stored record: its own columns are read as they were written
 * (`created_at` plus the rule's real event column), so a record the store wrote
 * decides its own fate. A record with no event yet is kept, never swept.
 */
export function dueForDeletion(items, nowMs) {
  const out = { delete: [], keep: [], never: [] };
  for (const item of items || []) {
    const v = retentionVerdict(item.kind, { ...item, nowMs });
    if (v.never) out.never.push(item.path);
    else if (v.delete) out.delete.push(item.path);
    else out.keep.push(item.path);
  }
  return out;
}
