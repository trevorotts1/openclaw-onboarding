// ============================================================================
// retention.js — Drama Studio service: retention rule (U2)
//
// Joint plan section 3.15, "How long", and section 3.10A item 1 (the 45-day
// unclaimed-waiting expiry) and item 2 (the 14-day done timer is a STATUS
// marker; it never keeps or deletes a file).
//
// | Kind                 | Deleted                                          |
// | -------------------- | ------------------------------------------------ |
// | intake_answer        | when the order is locked and picked up by the box |
// | intake_photo         | same as intake_answer                            |
// | approval_file        | when the stage is approved                       |
// | r2_fallback_video    | 7 days after delivery                            |
// | status_record        | 30 days after delivery                           |
// | waiting_unclaimed    | 45 days after the order was saved                |
// | project_object       | 45 days after creation (the storage rule)        |
// | enrollment_record    | NEVER — the scope rule excludes it               |
// | delivery_receipt     | NEVER                                            |
// | ghl_media            | NEVER — the studio never deletes a GHL copy      |
//
// Section 3.15: "Deletion code does not exist in either live mini app today.
// It is new work (U2)." This module IS that work: it decides, it never
// blanket-deletes, and it refuses the never-delete classes by construction.
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
};

export const AF_RET_UNKNOWN_KIND = 'AF-DS-RET-UNKNOWN-KIND';
export const AF_RET_NO_EVENT = 'AF-DS-RET-NO-EVENT';

/**
 * @param {string} kind
 * @param {{createdAtMs?:number, eventAtMs?:number, nowMs:number}} when
 *   `eventAtMs` is the pickup / stage-approved / delivered moment, whatever the
 *   rule's `from` names.
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
  const startMs = rule.from === 'created' ? when.createdAtMs : when.eventAtMs;
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
 */
export function dueForDeletion(items, nowMs) {
  const out = { delete: [], keep: [], never: [] };
  for (const item of items || []) {
    const v = retentionVerdict(item.kind, {
      createdAtMs: item.created_at_ms,
      eventAtMs: item.event_at_ms,
      nowMs,
    });
    if (v.never) out.never.push(item.path);
    else if (v.delete) out.delete.push(item.path);
    else out.keep.push(item.path);
  }
  return out;
}
