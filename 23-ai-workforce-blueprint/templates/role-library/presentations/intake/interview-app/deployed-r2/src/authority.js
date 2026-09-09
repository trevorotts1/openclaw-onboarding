// PRES-023 — session storage authority for the R2-backed worker.
//
// The base worker (src/index.js) had three serialization defects:
//   1. mintSession read-modify-wrote the shared per-run index JSON
//      (loadRunIndex -> filter -> saveRunIndex): two simultaneous mints could
//      both append, or one could clobber the other's row — competing active
//      sessions / lost index rows.
//   2. postAnswer loaded the WHOLE answers array and wrote it back
//      (loadAnswers -> map/push -> saveAnswers): two tabs answering in the
//      same tick lost one write entirely.
//   3. completeSession did the same read-modify-write on the session + run
//      index with no idempotency key: a retried or duplicated complete could
//      re-write a different revision.
// listIntakes() additionally made ONE STORE.list call, ignored truncation,
// and serially fetched every object for metadata — larger history hid waiting
// submissions behind the first list page and made each poll slow.
//
// This module is the fix, shaped for what the live deployment actually has:
// an R2 bucket binding (env.STORE). D1 was never provisionable for this
// deployment (see deployed-r2/README.md) and a Durable Object migration is a
// deploy decision — this landing is git-direction only. R2 puts are strongly
// consistent and the binding supports conditional writes (onlyIf), so this
// layer gives the guarantees D1 transactions would, with the bucket as the
// single authority per session:
//
//   - Every mutable record lives under a PER-SESSION (or per-row) key with a
//     monotonic revision. Writers do get -> decide on the FRESH value -> put
//     with onlyIf{etagMatches: read-etag}; a lost CAS (put returns null) makes
//     the caller re-read and re-decide. That retry loop is the serialization:
//     at most one concurrent writer wins each put and no update is lost.
//   - Mint uses create-if-not-exists on a per-run active-session pointer:
//     of N simultaneous mints, exactly one wins the pointer CAS; the others
//     read the winner's token and replay it (one active session per run).
//   - postAnswer carries an optional idempotency key: the first accepted put
//     records the result; a replayed key returns the recorded result verbatim.
//   - Completion flips the session status under CAS and the SAME winner
//     appends the completion-outbox event (deduped by revision, so retries
//     and recovery calls converge on exactly one event per revision).
//   - Discovery is a paginated scoped pending index (append-only per-session
//     rows, metadata in the row — no shared mutable queue JSON, no
//     serial fetch of every object) with claim/lease on the row and ack
//     (row delete) once processed, so polls never rescan processed history.
//
// Every function accepts any bucket-shaped object (get/put/list/delete), so
// tests drive an in-memory R2-semantics mock and the live worker passes
// env.STORE directly.

import { nowSeconds } from "./lib.js";

// Bounded CAS retry budget: each retry re-reads the authoritative object.
export const CAS_RETRIES = 8;
// Pending-index page size for listPendingIntakes (one STORE.list page).
export const PENDING_PAGE_LIMIT = 100;
// Default lease for a claimed pending row (a crashed poller self-heals).
export const LEASE_TTL_SECONDS = 300;

// ---------------------------------------------------------------------------
// Key scheme
// ---------------------------------------------------------------------------
//   sessions/<token>.json               session record (revision-bearing)
//   answers/<token>.json                answers record (revision + rows)
//   idem/<token>/<key>.json             idempotency memo (answers)
//   outbox/<token>.json                 completion outbox events (revisioned)
//   runs/<run_id>.active.json           per-run active-session pointer
//   intakes/<session_id>.json           stored finished intake (shape unchanged)
//   intakes-index/<stored_at>-<sid>.json pending rows (append-only, leasable)

export function sessionKey(token) { return "sessions/" + token + ".json"; }
export function answersKey(token) { return "answers/" + token + ".json"; }
export function idemKey(token, key) {
  return "idem/" + token + "/" + String(key).replace(/[^A-Za-z0-9._-]/g, "_") + ".json";
}
export function outboxKey(token) { return "outbox/" + token + ".json"; }
export function runActiveKey(runId) { return "runs/" + String(runId).replace(/[^A-Za-z0-9._-]/g, "") + ".active.json"; }
export function intakeIndexKey(storedAt, sessionId) {
  return "intakes-index/" + String(storedAt).padStart(12, "0") + "-" + String(sessionId).replace(/[^A-Za-z0-9._-]/g, "") + ".json";
}

// ---------------------------------------------------------------------------
// Conditional-write primitives (the only writes in this module)
// ---------------------------------------------------------------------------

/** Create-only put: succeeds exactly once for a key, ever. */
async function createOnce(bucket, key, value) {
  const res = await bucket.put(key, JSON.stringify(value), {
    onlyIf: { etagDoesNotMatch: "*" },
  });
  return res ? { etag: res.etag } : null; // null = already exists = lost race
}

/** CAS put against a read etag. Returns {etag} or null (CAS lost). */
async function casPut(bucket, key, value, etag) {
  const res = await bucket.put(key, JSON.stringify(value), {
    onlyIf: { etagMatches: etag },
  });
  return res ? { etag: res.etag } : null;
}

async function getJson(bucket, key) {
  const obj = await bucket.get(key);
  if (!obj) return null;
  let parsed;
  try { parsed = JSON.parse(await obj.text()); } catch { return null; }
  return { value: parsed, etag: obj.etag };
}

/**
 * Read-decide-write under CAS with bounded retries. `mutate(current)` returns
 * the next value, or null/undefined for "no change" (returns
 * {value: current, unchanged: true} without writing). On CAS loss the FRESH
 * value is re-read and mutate runs again — decisions are always made against
 * the authoritative state, never a stale snapshot. Returns null only when
 * retries are exhausted (a visible retryable conflict, never a silent loss).
 */
export async function casUpdate(bucket, key, mutate, { retries = CAS_RETRIES } = {}) {
  for (let attempt = 0; attempt < retries; attempt++) {
    const cur = await getJson(bucket, key);
    const next = mutate(cur ? cur.value : null, attempt);
    if (next === null || next === undefined) {
      return { value: cur ? cur.value : null, etag: cur ? cur.etag : null, unchanged: true };
    }
    const res = cur
      ? await casPut(bucket, key, next, cur.etag)
      : await createOnce(bucket, key, next);
    if (res) return { value: next, etag: res.etag, unchanged: false };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export function newSessionRecord({ token, run_id, box_id, question_set, questions_json, confirm_code, created, expires }) {
  return {
    token, run_id, box_id, question_set, questions_json,
    confirm_code: confirm_code || null,
    status: "open",
    created_at: created, expires_at: expires, completed_at: null,
    revision: 1,
  };
}

export async function loadSession(bucket, token) {
  return getJson(bucket, sessionKey(token)); // { value, etag } | null
}

/**
 * Per-run active-session pointer. Exactly one open session per run: the
 * pointer is claimed with create-if-not-exists semantics under CAS; the CAS
 * winner names the session token. `force` replaces a pointer whose named
 * session is unusable (expired/complete/missing) — still a single CAS, still
 * one winner.
 */
export async function claimRunActiveSlot(bucket, runId, token, expiresAt, { force = false, now = nowSeconds } = {}) {
  return casUpdate(bucket, runActiveKey(runId), (cur) => {
    if (cur && cur.token && Number(cur.expires_at) > now() && cur.status === "open" && !force) {
      return null; // a live open session already owns the run slot
    }
    return { token, expires_at: expiresAt, status: "open" };
  });
}

// ---------------------------------------------------------------------------
// Idempotency memos (answers)
// ---------------------------------------------------------------------------

/**
 * First writer records; replays read. Returns {record, replayed}.
 * A null/undefined makeRecord() is a READ-ONLY PROBE: nothing is written and
 * {record: null, replayed: false} comes back — a probe must never create a
 * placeholder record, because the placeholder would shadow the winner's real
 * result forever (replays would see an empty record instead of the outcome
 * they must replay verbatim).
 */
export async function idempotentOnce(bucket, token, key, makeRecord) {
  const k = idemKey(token, key);
  const existing = await getJson(bucket, k);
  if (existing && existing.value !== null && existing.value !== undefined) {
    return { record: existing.value, replayed: true };
  }
  const value = makeRecord();
  if (value === null || value === undefined) return { record: null, replayed: false };
  const created = await createOnce(bucket, k, value);
  if (created) return { record: value, replayed: false };
  // Lost the create race: the winner's record is readable — replay it.
  const winner = await getJson(bucket, k);
  if (winner && winner.value !== null && winner.value !== undefined) {
    return { record: winner.value, replayed: true };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Answers (per-session record under CAS — the only writer of that object)
// ---------------------------------------------------------------------------

export function emptyAnswersRecord() {
  return { revision: 0, answers: [] };
}

export function answersValueMap(record) {
  const map = {};
  for (const r of (record && record.answers) || []) map[r.question_id] = r.value;
  return map;
}

export function answersIdList(record) {
  return ((record && record.answers) || []).map((r) => r.question_id);
}

export async function loadAnswersRecord(bucket, token) {
  const row = await getJson(bucket, answersKey(token));
  return row || { value: emptyAnswersRecord(), etag: null };
}

/**
 * Apply one answer under CAS. `decide(record)` is called with the FRESH
 * answers record and returns {accepted, answers} (write) or {accepted:false}
 * (no write). Lost CAS => decide re-runs on the fresh record, so concurrent
 * tabs each get a deterministic verdict and no accepted answer is lost.
 */
export async function applyAnswerCAS(bucket, token, decide) {
  return casUpdate(bucket, answersKey(token), (cur) => {
    const record = cur || emptyAnswersRecord();
    const decision = decide(record);
    if (!decision || !decision.accepted) return null;
    return {
      revision: (record.revision || 0) + 1,
      answers: decision.answers,
    };
  });
}

// ---------------------------------------------------------------------------
// Completion outbox (same CAS authority; one event per session revision)
// ---------------------------------------------------------------------------

export async function appendOutboxEvent(bucket, token, event) {
  return casUpdate(bucket, outboxKey(token), (cur) => {
    const record = cur || { revision: 0, events: [] };
    // Dedupe by revision AND idempotency key: retries and recovery converge.
    if (record.events.some((e) => e.revision === event.revision)) return null;
    if (event.idempotency_key && record.events.some((e) => e.idempotency_key === event.idempotency_key)) return null;
    return { revision: (record.revision || 0) + 1, events: [...record.events, event] };
  });
}

export async function loadOutbox(bucket, token) {
  const row = await getJson(bucket, outboxKey(token));
  return row ? row.value : { revision: 0, events: [] };
}

/** All outbox events across sessions — paginated (one list page per call). */
export async function listOutbox(bucket, { cursor, limit = PENDING_PAGE_LIMIT } = {}) {
  const listed = await bucket.list({ prefix: "outbox/", cursor: cursor || undefined, limit });
  const events = [];
  for (const o of listed.objects) {
    const token = o.key.slice("outbox/".length).replace(/\.json$/, "");
    const rec = await getJson(bucket, o.key);
    if (rec) for (const e of rec.value.events || []) events.push({ ...e, token });
  }
  events.sort((a, b) => (a.token + ":" + a.revision) < (b.token + ":" + b.revision) ? -1 : 1);
  const out = { events, truncated: !!listed.truncated };
  if (listed.truncated) out.cursor = listed.cursor;
  return out;
}

// ---------------------------------------------------------------------------
// Pending-submission index: paginated, scoped, claim/lease, ack
// ---------------------------------------------------------------------------

/**
 * Append an index row when an intake is stored. One row per session — NO
 * shared mutable queue JSON. Metadata lives IN the row, so discovery needs
 * zero per-object fetches; the full intake is fetched only for claimed rows.
 */
export async function indexIntakeRow(bucket, sessionId, fileName, storedAt) {
  const key = intakeIndexKey(storedAt, sessionId);
  const row = { session_id: sessionId, file_name: fileName || null, stored_at: storedAt, lease: null };
  const created = await createOnce(bucket, key, row);
  if (created) return true;
  // Same session re-stored: refresh metadata under CAS (bounded).
  const upd = await casUpdate(bucket, key, (cur) => (cur ? { ...cur, file_name: row.file_name, stored_at: storedAt } : row), { retries: 3 });
  return !!upd;
}

/**
 * One page of pending submissions (metadata-only rows, newest first) with the
 * continuation cursor when more pages exist. Callers pass the cursor back —
 * no full-history rescan, and acked (processed) rows are gone from the index
 * entirely, so discovery cost tracks PENDING work, not history.
 */
export async function listPendingIntakes(bucket, { cursor, limit = PENDING_PAGE_LIMIT } = {}) {
  const listed = await bucket.list({ prefix: "intakes-index/", cursor: cursor || undefined, limit });
  const rows = listed.objects.map((o) => {
    const rest = o.key.slice("intakes-index/".length);
    const dash = rest.indexOf("-");
    const stored_at = dash > 0 ? Number(rest.slice(0, dash)) : null;
    const session_id = dash > 0 ? rest.slice(dash + 1).replace(/\.json$/, "") : rest.replace(/\.json$/, "");
    return { session_id, stored_at, key: o.key };
  });
  rows.sort((a, b) => (b.stored_at || 0) - (a.stored_at || 0));
  const out = { intakes: rows, truncated: !!listed.truncated };
  if (listed.truncated) out.cursor = listed.cursor;
  return out;
}

/**
 * Claim a pending row for processing: CAS a lease onto the row. Returns the
 * lease when claimed, null when a live foreign lease holds it. Lease expiry
 * makes claims self-healing after a crashed poller.
 */
export async function claimIndexRow(bucket, key, owner, { ttlSeconds = LEASE_TTL_SECONDS, now = nowSeconds } = {}) {
  const res = await casUpdate(bucket, key, (cur) => {
    if (!cur) return null;
    const t = now();
    if (cur.lease && cur.lease.owner !== owner && Number(cur.lease.expires_at) > t) return null;
    return { ...cur, lease: { owner, expires_at: t + ttlSeconds } };
  });
  if (!res || res.unchanged || !res.value) return null;
  return res.value.lease;
}

export async function releaseIndexRow(bucket, key, owner) {
  const res = await casUpdate(bucket, key, (cur) => {
    if (!cur || !cur.lease || cur.lease.owner !== owner) return null;
    return { ...cur, lease: null };
  });
  return !!res && !res.unchanged;
}

/** Ack (remove) a processed row — idempotent. */
export async function ackIndexRow(bucket, key) {
  await bucket.delete(key);
  return true;
}
