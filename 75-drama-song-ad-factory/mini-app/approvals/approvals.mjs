// =============================================================================
// approvals.mjs — the APPROVALS layer (U8)
// -----------------------------------------------------------------------------
// 75-drama-song-ad-factory/mini-app/approvals/approvals.mjs
//
// THE FOUR BEHAVIOURS THIS MODULE OWNS (joint plan section 5, row U8):
//
//   1. FIRST ANSWER WINS  — once an answer is recorded for an approval item, a
//      second competing answer is REFUSED (a named code, not a silent accept)
//      and the recorded answer is left untouched.
//   2. VERSION DEDUP      — the same item arriving with the same version must
//      NOT produce a second approval item; a genuinely NEW version must.
//   3. ONE NUDGE, THEN REMINDER, THEN SILENCE — exactly two notices ever (one
//      nudge, one reminder); every later event is silent, no matter how many.
//   4. PRODUCER HAND-OFF  — carries an approved item to the producer and
//      REFUSES an unapproved one with a named refusal (the CLI exits non-zero).
//
// This is not a new framework, scheduler, dashboard or management app: it is a
// pure module over an injected store, exactly the shape the U2 service uses
// ("everything except presignPut and the store adapters is pure and takes an
// injected adapter"). The refusal dict reuses the skill's existing gate shape
// ({reason_code, detail, next_action}); the refusal exit code (5) is the one
// the existing gates (song_choices, channel_send) already use.
//
// The store adapter is the U2 seam, kept minimal and synchronous so a CLI and
// the browser check can both drive it:
//     store.get(key)          -> value|null
//     store.put(key, value)   -> void
//     store.list(prefix)      -> string[]   (sorted)
//
// No credentials, no network, no client-box write. Stdlib only.
// =============================================================================
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

//: The three approvals the studio asks for, in order (U3 page 4).
export const ITEM_IDS = Object.freeze(["script", "song", "storyboard"]);

//: The escalation ladder. Exactly these, then silence — the length IS the cap.
export const NOTICE_ORDER = Object.freeze(["nudge", "reminder"]);

//: The named refusal codes. A refusal always names itself, never a silent blank.
export const CODE = Object.freeze({
  ITEM_UNKNOWN: "APPROVAL_ITEM_UNKNOWN",
  ANSWER_TAKEN: "APPROVAL_ANSWER_TAKEN",
  NOT_APPROVED: "APPROVAL_NOT_APPROVED",
  BAD_INPUT: "APPROVAL_BAD_INPUT",
});

//: Refused-item exit code — the same one the skill's existing gates use.
export const REFUSED_EXIT = 5;

export class ApprovalError extends Error {
  constructor(message) { super(message); this.name = "ApprovalError"; this.code = CODE.BAD_INPUT; }
}

// ── keys ─────────────────────────────────────────────────────────────────────
// Namespaced like U2's `order:<client_id>:<order_id>`: a caller cannot name a
// key it does not already hold the ids for.
function itemKey(clientId, itemId, version) {
  return `approval:${clientId}:${itemId}:${version}`;
}

function requireText(value, what) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new ApprovalError(`${CODE.BAD_INPUT}: ${what} is required`);
  }
  return value;
}

function requireVersion(version) {
  const n = Number(version);
  if (!Number.isInteger(n) || n < 1) {
    throw new ApprovalError(`${CODE.BAD_INPUT}: version must be a positive integer`);
  }
  return n;
}

function refusal(code, detail, nextAction) {
  return { ok: false, code, reason_code: code, detail, next_action: nextAction };
}

// ── 2. VERSION DEDUP ─────────────────────────────────────────────────────────
/**
 * Register an approval item for arrival of (itemId, version).
 * The SAME (client, item, version) returns the EXISTING item (created:false) —
 * never a second approval item. A new version creates a new item (created:true).
 */
export function registerItem(store, { clientId, itemId, version, now = Date.now() }) {
  requireText(clientId, "clientId");
  requireText(itemId, "itemId");
  const v = requireVersion(version);
  const key = itemKey(clientId, itemId, v);
  const existing = store.get(key);
  if (existing) return { ok: true, created: false, item: existing }; // U8-GUARD:version-dedup
  const item = {
    client_id: clientId,
    item_id: itemId,
    version: v,
    registered_at: now,
    answer: null,
    escalation: { count: 0, last_at: null },
  };
  store.put(key, item);
  return { ok: true, created: true, item };
}

// ── 1. FIRST ANSWER WINS ─────────────────────────────────────────────────────
/**
 * Record the client's answer for an approval item. The FIRST recorded answer
 * WINS: a second, competing answer is refused by name and the record is
 * untouched — the loser is refused, never silently accepted.
 */
export function recordAnswer(store, { clientId, itemId, version, answer, actor = "client", now = Date.now() }) {
  requireText(clientId, "clientId");
  requireText(itemId, "itemId");
  requireText(answer, "answer");
  const v = requireVersion(version);
  const key = itemKey(clientId, itemId, v);
  const item = store.get(key);
  if (!item) {
    return refusal(CODE.ITEM_UNKNOWN, `no approval item ${itemId} v${v} for this client`,
      "Register the item before answering it.");
  }
  if (item.answer) return refusal(CODE.ANSWER_TAKEN, `the first answer ("${item.answer.answer}") is already recorded for ${itemId} v${v}`, "Show the recorded answer; a later competing answer cannot overwrite it."); // U8-GUARD:first-answer-wins
  item.answer = { answer, actor, at: now };
  store.put(key, item);
  return { ok: true, recorded: true, item };
}

// ── 3. ONE NUDGE, THEN REMINDER, THEN SILENCE ────────────────────────────────
/**
 * The next notice for an unanswered item, on one event. Returns
 * {ok, notice: "nudge"|"reminder"|null, count}. Exactly one nudge, then one
 * reminder, then null forever — no matter how many later events arrive. An
 * already-answered item is always silent.
 */
export function escalate(store, { clientId, itemId, version, now = Date.now() }) {
  requireText(clientId, "clientId");
  requireText(itemId, "itemId");
  const v = requireVersion(version);
  const key = itemKey(clientId, itemId, v);
  const item = store.get(key);
  if (!item) {
    return refusal(CODE.ITEM_UNKNOWN, `no approval item ${itemId} v${v} for this client`,
      "Register the item before escalating it.");
  }
  if (item.answer) return { ok: true, notice: null, count: item.escalation.count };
  const count = item.escalation.count;
  if (count >= NOTICE_ORDER.length) return { ok: true, notice: null, count }; // U8-GUARD:escalation-cap
  const notice = NOTICE_ORDER[count];
  item.escalation = { count: count + 1, last_at: now };
  store.put(key, item);
  return { ok: true, notice, count: count + 1 };
}

// ── 4. PRODUCER HAND-OFF ─────────────────────────────────────────────────────
/**
 * The one gate in front of the producer. An APPROVED item yields the payload
 * the producer consumes; an UNANSWERED (or unknown) item is refused by name, so
 * the caller (the CLI) exits non-zero and nothing starts.
 */
export function producerPayload(store, { clientId, itemId, version }) {
  requireText(clientId, "clientId");
  requireText(itemId, "itemId");
  const v = requireVersion(version);
  const key = itemKey(clientId, itemId, v);
  const item = store.get(key);
  if (!item) {
    return refusal(CODE.ITEM_UNKNOWN, `no approval item ${itemId} v${v} for this client`,
      "Nothing is handed to the producer for an item that does not exist.");
  }
  if (!item.answer) return refusal(CODE.NOT_APPROVED, `${itemId} v${v} has not been approved`, "Wait for the client's answer; the producer must not start on an unapproved item."); // U8-GUARD:producer-refuse
  return {
    ok: true,
    payload: {
      client_id: item.client_id,
      item_id: item.item_id,
      version: item.version,
      answer: item.answer.answer,
      approved_at: item.answer.at,
      approved_by: item.answer.actor,
    },
  };
}

/** True only when the item exists AND carries a recorded answer. */
export function isApproved(store, { clientId, itemId, version }) {
  const item = store.get(itemKey(clientId, itemId, requireVersion(version)));
  return !!(item && item.answer);
}

// ── store adapters (the injected seam) ───────────────────────────────────────
/** In-memory store. Deep-copies on get/put so callers cannot alias the record. */
export function memoryStore(seed = {}) {
  const map = new Map(Object.entries(seed));
  const copy = (v) => JSON.parse(JSON.stringify(v));
  return {
    get: (k) => (map.has(k) ? copy(map.get(k)) : null),
    put: (k, v) => { map.set(k, copy(v)); },
    list: (prefix = "") => [...map.keys()].filter((k) => k.startsWith(prefix)).sort(),
  };
}

/** A single JSON file holding the whole key -> record map. No cache: every
 *  read is fresh, so a CLI and the checks never see a stale copy. */
export function fileStore(path) {
  const load = () => { try { return JSON.parse(readFileSync(path, "utf8")); } catch { return {}; } };
  const save = (db) => { mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, JSON.stringify(db, null, 2) + "\n"); };
  return {
    get: (k) => { const db = load(); return Object.prototype.hasOwnProperty.call(db, k) ? db[k] : null; },
    put: (k, v) => { const db = load(); db[k] = v; save(db); },
    list: (prefix = "") => Object.keys(load()).filter((k) => k.startsWith(prefix)).sort(),
  };
}
