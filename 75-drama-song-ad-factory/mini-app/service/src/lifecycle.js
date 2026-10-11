// ============================================================================
// lifecycle.js — Drama Studio service: approved lifecycle, timer precedence and
// the one-operator-record-per-client-per-day rule (U2)
//
// Joint plan section 3.10A, APPROVED 2026-10-10 by Trevor (decision 22):
//   item 1  the order lifecycle table (states, who moves them)
//   item 2  what determines "done": Looks good, an observed download, or 14
//           days after delivery — whichever comes FIRST
//   item 3  how a notice clears: the operator inbox line is replaced, not
//           stacked — one line per client per day (rule 3)
//   rule 3  "The operator inbox line is at most one per client per day."
//   rule 6  one approval nudge, at most one 24-hour reminder, then silence
//
// TIMER PRECEDENCE (item 1 + the resolved note in item 2):
//   1. cancelled / expired are TERMINAL. Nothing overwrites them — the 14-day
//      delivery timer included.
//   2. done is reached by acceptance, by an observed download, or by the
//      14-day status timer, first one wins.
//   3. R2 availability is a SEPARATE field ("expired" storage), never an order
//      state. The 14-day done timer is a status marker that keeps or deletes
//      no file (retention.js owns file life).
//
// PURE. No bindings, no I/O, no clock of its own.
// ============================================================================

'use strict';

export const DAY_MS = 24 * 60 * 60 * 1000;

export const STATES = [
  'waiting',        // saved, no box or computer has claimed it
  'in_production',  // chip "In production" (teal), board in_progress
  'needs_you',      // chip "Needs you" (gold), board blocked
  'ready',          // approvals finished, delivery not verified
  'delivered',      // delivery verified
  'done',
  'cancelled',
  'expired',
];

export const TERMINAL_STATES = ['done', 'cancelled', 'expired'];

export const WAITING_EXPIRY_DAYS = 45;   // item 1: unclaimed waiting order
export const DONE_TIMER_DAYS = 14;       // item 2: status marker only
export const OPERATOR_LINE_MAX_PER_DAY = 1; // rule 3

export const AF_STATE_ILLEGAL = 'AF-DS-STATE-ILLEGAL';
export const AF_STATE_TERMINAL = 'AF-DS-STATE-TERMINAL';
export const AF_STATE_UNKNOWN = 'AF-DS-STATE-UNKNOWN';

/** Legal moves. `cancel` is allowed while waiting, or at an approval stop
 *  before paid production began (item 1). After spending, the client sends a
 *  question instead and admin stops future work — never a pretend refund. */
const TRANSITIONS = {
  waiting: ['in_production', 'cancelled', 'expired'],
  in_production: ['needs_you', 'ready', 'cancelled'],
  needs_you: ['in_production', 'ready', 'cancelled'],
  ready: ['delivered', 'cancelled'],
  delivered: ['done'],
  done: [],
  cancelled: [],
  expired: [],
};

const EVENTS = {
  claim: 'in_production',
  needs_you: 'needs_you',
  answer: 'in_production',
  ready: 'ready',
  deliver: 'delivered',
  done: 'done',
};

/**
 * @returns {{ok:true, order:object} | {ok:false, code:string, message:string}}
 */
export function transition(order, event, { nowMs, actor = 'service' } = {}) {
  if (!order || !STATES.includes(order.state)) {
    return { ok: false, code: AF_STATE_UNKNOWN, message: 'Unknown order state.' };
  }
  if (TERMINAL_STATES.includes(order.state)) {
    return { ok: false, code: AF_STATE_TERMINAL, message: `Order is ${order.state}; it never moves again.` };
  }
  const next = event === 'cancel' ? 'cancelled' : EVENTS[event];
  if (!next) {
    return { ok: false, code: AF_STATE_ILLEGAL, message: `Unknown event ${event}.` };
  }
  if (next === 'cancelled' && order.state !== 'waiting' && order.paid_started) {
    // Paid production already began: cancellation is not offered.
    return { ok: false, code: AF_STATE_ILLEGAL, message: 'Paid production already began; send a question instead.' };
  }
  if (!TRANSITIONS[order.state].includes(next)) {
    return { ok: false, code: AF_STATE_ILLEGAL, message: `${order.state} cannot move to ${next}.` };
  }
  const stamp = { [`${next}_at`]: nowMs, last_actor: actor, updated_at: nowMs };
  return { ok: true, order: { ...order, ...stamp, state: next } };
}

/**
 * The current state of an order, timers applied in the approved precedence.
 * Returns { state, reason } and never mutates the input.
 */
export function resolveOrderState(order, nowMs) {
  if (!order) return { state: 'unknown', reason: 'no-order' };
  // 1. Terminal wins over every timer, the delivery timer included.
  if (order.state === 'cancelled') return { state: 'cancelled', reason: 'terminal' };
  if (order.state === 'expired') return { state: 'expired', reason: 'terminal' };
  if (order.state === 'done') return { state: 'done', reason: 'terminal' };
  // 2. Done: acceptance, then an observed download, then the 14-day timer.
  if (typeof order.accepted_at === 'number') return { state: 'done', reason: 'accepted' };
  if (typeof order.delivered_at === 'number' && typeof order.downloaded_at === 'number') {
    return { state: 'done', reason: 'downloaded' };
  }
  if (
    typeof order.delivered_at === 'number' &&
    nowMs >= order.delivered_at + DONE_TIMER_DAYS * DAY_MS
  ) {
    return { state: 'done', reason: 'done-timer-14d', timer: true };
  }
  // 3. An unclaimed waiting order expires after 45 days.
  if (
    order.state === 'waiting' &&
    typeof order.created_at === 'number' &&
    nowMs >= order.created_at + WAITING_EXPIRY_DAYS * DAY_MS
  ) {
    return { state: 'expired', reason: 'waiting-expiry-45d', timer: true };
  }
  return { state: order.state, reason: 'state' };
}

// ---------------------------------------------------------------------------
// Rule 3 — one operator record per client per day
// ---------------------------------------------------------------------------

export const OPERATOR_RECORD_TTL_SECONDS = 30 * DAY_MS / 1000; // prunes with the status record

/** The UTC day the record belongs to. */
export function utcDay(nowMs) {
  return new Date(nowMs).toISOString().slice(0, 10);
}

// ponytail: the day boundary is UTC. One line per UTC day is the rule the
// service can enforce without a per-client timezone it does not yet store.
// Upgrade path: read `record.timezone` and key on the client's local day.
export function operatorRecordKey(clientId, nowMs) {
  return `ops:${clientId}:${utcDay(nowMs)}`;
}

/**
 * Write THE one operator record for this client today.
 *
 * A second attempt on the same day REPLACES the existing record (item 3:
 * "It is also replaced, not stacked: one line per client per day") and returns
 * `created: false`. It never creates a second record and it never creates a
 * second key.
 */
export async function writeOperatorRecord(store, { clientId, line, nowMs }) {
  const key = operatorRecordKey(clientId, nowMs);
  const existing = await store.kvGet(key);
  let writes = 1;
  if (existing) {
    try {
      writes = (JSON.parse(existing).writes || 1) + 1;
    } catch {
      writes = 2;
    }
  }
  const record = {
    client_id: clientId,
    day: utcDay(nowMs),
    line,
    writes,
    updated_at: nowMs,
  };
  await store.kvPut(key, JSON.stringify(record), OPERATOR_RECORD_TTL_SECONDS);
  return { created: !existing, replaced: Boolean(existing), key, record };
}

/** How many operator records exist for this client on this day. Always 0 or 1. */
export async function operatorRecordCount(store, clientId, nowMs) {
  const raw = await store.kvGet(operatorRecordKey(clientId, nowMs));
  return raw ? 1 : 0;
}
