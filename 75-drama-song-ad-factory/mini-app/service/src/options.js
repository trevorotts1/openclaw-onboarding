// ============================================================================
// options.js — Drama Studio service: the options surface (U2)
//
// Joint plan section 3.10. The option is chosen PER CLIENT and lives in the
// client's studio record. Option 3 can only be set when Trevor's approval for
// that client is recorded — by name, one client at a time (decision 8).
//
// The studio page always shows the option and the real wait. The first three
// strings are copied verbatim from the approved plan; U3 renders them, it does
// not reword them. The box sentence is Trevor's approved wording (U-Z14,
// package default D-5) and is used in the same slot.
//
//   1  "Your crew starts when you open Claude Code on your computer. Last
//       check-in: 3 hours ago."
//   2  "Your crew is watching. Orders start within about 2 minutes while your
//       computer is on. Last check-in: 1 minute ago."
//   3  "Your crew starts automatically within about 2 minutes while your
//       computer is on and awake. Last check-in: 2 minutes ago."
//   stale (any option, 30 minutes with an order waiting)
//      "Your studio computer has not checked in for 2 hours. Your order is safe
//       and starts when it is back." (a clock time only when the record carries
//       a time zone) plus ONE quiet line in the operator inbox; with no
//       check-in yet, "Your order is safe. It starts as soon as your studio
//       computer is on."
//   box (U-Z14, decision D-5; replaces the three above for a client whose
//      studio runs on an OpenClaw box — its key records include a `box` key and
//      no `machine` key)
//      "Your studio is on. Orders start within about 2 minutes."
//
// PURE apart from lastCheckIn and clientKeys, the two store reads this surface
// needs: the stores are injected, there are no bindings, and the clock is
// always passed in.
// ============================================================================

'use strict';

import { checkinKey } from './ids.js';
import { listKeys } from './support.js';

export const OPTIONS = [1, 2, 3];
export const DEFAULT_OPTION = 1;
export const STALE_AFTER_MS = 30 * 60 * 1000;
// How often a check-in re-saves its time. Boxes still ask every 2 minutes;
// saving every 2 minutes burned the KV free tier (1,000 writes/day, 2026-10-13).
// Must stay well under STALE_AFTER_MS or a live box reads as stale.
export const CHECKIN_SAVE_EVERY_MS = 20 * 60 * 1000;

export const AF_OPT_INVALID = 'AF-DS-OPT-INVALID';
export const AF_OPT_APPROVAL = 'AF-DS-OPT-APPROVAL';

const PENNY = {
  1: 'Your crew starts when you open Claude Code on your computer.',
  2: 'Your crew is watching. Orders start within about 2 minutes while your computer is on.',
  3: 'Your crew starts automatically within about 2 minutes while your computer is on and awake.',
};

/** U-Z14 (S75-077, decision D-5) — the sentence a client reads when their
 *  studio runs on an OpenClaw box. Approved wording, never reworded: it fills
 *  the same slot as the three above, so the real wait is appended the same way. */
export const BOX_LINE = 'Your studio is on. Orders start within about 2 minutes.';

/** True when `keys` — a client's stored key records — include an ACTIVE box key
 *  and no ACTIVE machine key. A revoked key is no longer one of the client's
 *  keys (U-Z12), so it never decides the sentence. Everything else keeps one of
 *  the three option sentences unchanged. */
export function boxOnlyClient(keys) {
  const active = (Array.isArray(keys) ? keys : []).filter((k) => k && k.status === 'active');
  return active.some((k) => k.kind === 'box') && !active.some((k) => k.kind === 'machine');
}

/** Every stored key record that belongs to one client, read through the same
 *  `key:` listing the admin revoke route uses. Unreadable records and other
 *  clients' records are skipped, never guessed at; no listing means no box key
 *  is proven, so the client keeps its option sentence.
 *  ponytail: one KV listing per call. A client-scoped key index would remove
 *  it; nothing writes one yet. */
export async function clientKeys(store, clientId) {
  const out = [];
  for (const name of await listKeys(store, 'key:')) {
    const raw = await store.kvGet(name);
    if (!raw) continue;
    try {
      const record = JSON.parse(raw);
      if (record && record.client_id === clientId) out.push(record);
    } catch {
      // A record this module cannot read is skipped, never guessed at.
    }
  }
  return out;
}

/** "3 hours ago" / "1 minute ago" / "just now" / "not yet". */
export function ageText(nowMs, sinceMs) {
  if (typeof sinceMs !== 'number') return 'not yet';
  const mins = Math.floor((nowMs - sinceMs) / 60000);
  if (mins < 1) return 'just now';
  if (mins === 1) return '1 minute ago';
  if (mins < 60) return `${mins} minutes ago`;
  const hours = Math.floor(mins / 60);
  if (hours === 1) return '1 hour ago';
  if (hours < 24) return `${hours} hours ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? '1 day ago' : `${days} days ago`;
}

/** CLOCK — "2:14 PM". Uses the client's own timezone when the record stores
 *  one, otherwise UTC (api), so the string never implies a local time it does
 *  not know. ponytail: add `timezone` to the client record when U12's admin
 *  page collects it. */
export function clockText(ms, timezone) {
  if (typeof ms !== 'number') return 'unknown';
  try {
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      timeZone: timezone || 'UTC',
    }).format(new Date(ms));
  } catch {
    return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }).format(new Date(ms));
  }
}

/**
 * The stored check-in for a client, in ms, or null when it has never checked
 * in. Read through the ONE shared key helper the check-in is written with
 * (ids.checkinKey, written by inbox.checkIn), so the page can never report a
 * different record from the one the box's check-in landed in. Stored in R2,
 * not KV: R2's free tier takes the fleet's check-ins, KV's 1,000 writes/day
 * does not.
 */
export async function lastCheckIn(objectStore, clientId) {
  const obj = await objectStore.objectGet(checkinKey(clientId));
  const n = obj ? Number(obj.value) : NaN;
  return Number.isFinite(n) ? n : null;
}

/**
 * The line the studio page shows under the option. `lastCheckMs` is the stored
 * check-in (lastCheckIn); `record.last_check_in` is only a fallback for a
 * record that already carries one — nothing in this service writes it after
 * the record is created. `keys` is the client's own key records (clientKeys):
 * a box key and no machine key means the studio runs on an OpenClaw box, and
 * the page says so (U-Z14). A caller that passes no keys is one that may not
 * LIST KV (the order route, DSF-611): the `box_only` verdict that key minting
 * and revocation keep on the client record decides, and a record without one
 * keeps its option sentence.
 */
export function optionLine(record, nowMs, lastCheckMs, keys) {
  const option = OPTIONS.includes(record && record.option) ? record.option : DEFAULT_OPTION;
  const last = typeof lastCheckMs === 'number' ? lastCheckMs : (record ? record.last_check_in : null);
  const box = Array.isArray(keys) ? boxOnlyClient(keys) : Boolean(record && record.box_only === true);
  const sentence = box ? BOX_LINE : PENNY[option];
  return `${sentence} Last check-in: ${ageText(nowMs, last)}.`;
}

/**
 * Option 3 is opt-in per client and needs a recorded approval naming the
 * client. Everything else is refused with a named code, never ignored.
 */
export function setOption(record, option, { nowMs, approval } = {}) {
  if (!OPTIONS.includes(option)) {
    return { ok: false, code: AF_OPT_INVALID, message: 'option must be 1, 2 or 3.' };
  }
  if (option === 3) {
    const approved = approval && approval.option3 === true && typeof approval.client_name === 'string' && approval.client_name;
    if (!approved) {
      return {
        ok: false,
        code: AF_OPT_APPROVAL,
        message: 'Option 3 needs Trevor\'s recorded approval for this client.',
      };
    }
  }
  return {
    ok: true,
    record: { ...record, option, option_set_at: nowMs, option_approval: option === 3 ? approval : null },
  };
}

/**
 * The 30-minute no-check-in rule (section 3.10, item 1 of section 3.10A): with
 * an order waiting, the page gets a quiet explanation and the operator inbox
 * gets ONE line — and that one line is subject to rule 3 (one per client per
 * day), which lifecycle.writeOperatorRecord enforces.
 */
export function staleVerdict({ record, lastCheckMs, hasWaitingOrder, nowMs }) {
  if (!hasWaitingOrder) return { stale: false, page_line: null, operator_line: null };
  if (typeof lastCheckMs === 'number' && nowMs - lastCheckMs < STALE_AFTER_MS) {
    return { stale: false, page_line: null, operator_line: null };
  }
  if (typeof lastCheckMs !== 'number') {
    return {
      stale: true,
      page_line: 'Your order is safe. It starts as soon as your studio computer is on.',
      operator_line: 'Computer has not checked in yet with an order waiting',
    };
  }
  // A clock time is only printed when the record says which zone it is in: a
  // bare time would be the operator's clock shown to the client as their own.
  if (!(record && record.timezone)) {
    // The sentence below already supplies "for", so the helper's trailing
    // "ago" is stripped: "for 31 minutes", never "for 31 minutes ago".
    const age = ageText(nowMs, lastCheckMs).replace(/ ago$/, '');
    return {
      stale: true,
      page_line: `Your studio computer has not checked in for ${age}. Your order is safe and starts when it is back.`,
      operator_line: `Computer has not checked in for ${age} with an order waiting`,
    };
  }
  const clock = clockText(lastCheckMs, record && record.timezone);
  return {
    stale: true,
    page_line: `Your computer has not checked in since ${clock}. Your order is safe and starts when it is back.`,
    operator_line: `Computer has not checked in since ${clock} with an order waiting`,
  };
}
