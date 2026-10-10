// ============================================================================
// inbox.js — Drama Studio service: inbox entry (U2)
//
// Joint plan section 3.2: "a 2-minute read of one small inbox file per box" —
// the studio writes ONE small inbox object per client, and the box (or Claude
// Code computer) reads it with its own key. Section 3.10: the bridge script
// prints nothing when there is no order, prints one line when there is one:
//
//   DRAMA_ORDER r_123 "Spring Sale"
//
// and records "last check-in" either way.
//
// The studio is a dumb relay: this module stores what the client said and
// hands back one line. It never decides to run anything.
// ============================================================================

'use strict';

import { scopePath } from './ids.js';

export const MAX_WAITING_ORDERS = 50;
export const INBOX_LINE_PREFIX = 'DRAMA_ORDER';

/** clients/<id>/inbox.json — the one small file per box. */
export function inboxPath(clientId) {
  return scopePath(clientId, 'inbox.json');
}

export function checkinKey(clientId) {
  return `checkin:${clientId}`;
}

/** The waiting orders only, newest last, capped so the file stays small. */
export function waitingOrders(orders) {
  const list = (orders || []).filter((o) => o && o.state === 'waiting');
  return list.slice(0, MAX_WAITING_ORDERS);
}

/**
 * Write the client's inbox: waiting orders only, never the whole order table
 * (a box has no business reading another stage's records).
 */
export async function writeInbox(objectStore, { clientId, orders, nowMs }) {
  const waiting = waitingOrders(orders);
  await objectStore.objectPut(
    inboxPath(clientId),
    JSON.stringify({ client_id: clientId, updated_at: nowMs, orders: waiting }),
  );
  return { ok: true, path: inboxPath(clientId), waiting: waiting.length };
}

export async function readInbox(objectStore, clientId) {
  const obj = await objectStore.objectGet(inboxPath(clientId));
  if (!obj) return { waiting: [] };
  try {
    const parsed = JSON.parse(obj.value);
    return { waiting: waitingOrders(parsed.orders) };
  } catch {
    return { waiting: [] };
  }
}

/** The one line a bridge prints. Null when there is nothing to do. */
export function inboxLine(orders) {
  const first = waitingOrders(orders)[0];
  if (!first) return null;
  const title = String(first.title || 'your video').replace(/"/g, "'");
  return `${INBOX_LINE_PREFIX} ${first.order_id} "${title}"`;
}

/**
 * A check-in from a box or computer: records the moment, returns the one line
 * (or nothing). Zero model tokens on the client side — this is the network
 * call, not a model turn.
 */
export async function checkIn(store, objectStore, { clientId, nowMs, orders }) {
  await store.kvPut(checkinKey(clientId), String(nowMs));
  const inbox = orders ? { waiting: waitingOrders(orders) } : await readInbox(objectStore, clientId);
  return { ok: true, checked_in_at: nowMs, line: inboxLine(inbox.waiting) };
}

export async function lastCheckIn(store, clientId) {
  const raw = await store.kvGet(checkinKey(clientId));
  const n = raw === null || raw === undefined ? NaN : Number(raw);
  return Number.isFinite(n) ? n : null;
}
