// PRES-023 gate — R2 session authority (deployed-r2 worker).
//
// Offline. The worker's storage layer runs against an in-memory mock with the
// R2 binding's own semantics (strong consistency; conditional put returning
// null on precondition failure; cursor-truncated list). The battery proves the
// QC-PRES-023 acceptance list:
//   1. two simultaneous answer/mint calls: no lost answer, one active session,
//      deterministic conflict or replay
//   2. two-tab completion: stable final revision
//   3. more submissions than one list page: all discovered exactly once
//   4. restart cursor halfway through: no lost work
//   5. large processed history does not slow new-job discovery (index rows
//      acked -> discovery scans pending rows only, bounded page)
//   + completion outbox persisted under the same authority
//
//   node --test test/test_pres023_worker_authority.mjs

import { test } from "node:test";
import assert from "node:assert/strict";

// ---- in-memory R2 mock: the binding semantics the live worker gets ----------
function makeR2Mock() {
  const objects = new Map();
  let counter = 0;
  function hash(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return "etag-" + (h >>> 0).toString(16).padStart(12, "0") + "-" + (++counter);
  }
  return {
    async get(key) {
      const o = objects.get(key);
      if (!o) return null;
      return { etag: o.etag, uploaded: new Date(o.uploaded), async text() { return o.body; } };
    },
    async head(key) {
      const o = objects.get(key);
      return o ? { etag: o.etag, uploaded: new Date(o.uploaded) } : null;
    },
    async put(key, body, opts = {}) {
      const existing = objects.get(key);
      if (opts.onlyIf) {
        const c = opts.onlyIf;
        if (c.etagMatches !== undefined && (!existing || existing.etag !== c.etagMatches)) return null;
        if (c.etagDoesNotMatch !== undefined) {
          if (c.etagDoesNotMatch === "*") { if (existing) return null; }
          else if (existing && existing.etag === c.etagDoesNotMatch) return null;
        }
      }
      const o = { body: String(body), etag: hash(key + "|" + String(body)), uploaded: Date.now() };
      objects.set(key, o);
      return { etag: o.etag, uploaded: new Date(o.uploaded) };
    },
    async delete(key) { objects.delete(key); },
    async list(opts = {}) {
      // Opaque string cursor (last key of the previous page, base64) — the
      // shape R2's binding hands back across HTTP-shaped boundaries.
      const keys = [...objects.keys()].filter((k) => !opts.prefix || k.startsWith(opts.prefix)).sort();
      let startIdx = 0;
      if (opts.cursor) {
        const lastKey = Buffer.from(String(opts.cursor), "base64").toString("utf8");
        const idx = keys.indexOf(lastKey);
        startIdx = idx === -1 ? 0 : idx + 1;
      }
      const page = keys.slice(startIdx, startIdx + (opts.limit || 1000));
      const truncated = startIdx + page.length < keys.length;
      const res = {
        objects: page.map((k) => ({ key: k, etag: objects.get(k).etag, uploaded: new Date(objects.get(k).uploaded) })),
        truncated,
      };
      if (truncated) res.cursor = Buffer.from(page[page.length - 1], "utf8").toString("base64");
      return res;
    },
    _debug: { objects },
  };
}

// ---- worker harness ----------------------------------------------------------
const WORKER_URL = "https://worker.test";
const worker = (await import("../deployed-r2/src/index.js")).default;
const auth = {
  INTAKE_ADMIN_TOKEN: "admin-token",
  STORE: null,
};

function req(method, path, { body, headers, query } = {}) {
  const url = new URL(WORKER_URL + path);
  for (const [k, v] of Object.entries(query || {})) url.searchParams.set(k, v);
  return new Request(url, {
    method,
    headers: { "content-type": "application/json", ...(headers || {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function call(method, path, opts = {}) {
  if (path.startsWith("/api/intake/list")) path += (path.includes("?") ? "&" : "?") + "company_id=test-company&installation_id=test-installation";
  const res = await worker.fetch(req(method, path, opts), auth);
  const body = await res.json();
  return { status: res.status, body };
}

const admin = { authorization: "Bearer admin-token" };

function payloadFor(ids, opts = {}) {
  return {
    question_set: "standard",
    questions: ids.map((id, i) => ({
      id, order: i + 1, prompt: "P " + id,
      kind: opts.kind?.[id] || "text",
      required: opts.optional?.includes(id) ? false : true,
    })),
  };
}

function freshEnv() {
  auth.STORE = makeR2Mock();
  return auth.STORE;
}

async function mintSession(runId, ids, extra = {}) {
  return call("POST", "/api/sessions", {
    body: { company_id: "test-company", installation_id: "test-installation", presentation_id: "test-presentation", run_id: runId, box_id: "box-a", questions_payload: payloadFor(ids, extra), ...extra.mint },
    headers: admin,
  });
}

// ---- 1. concurrent mint: one active session, deterministic -------------------

test("P023-1 concurrent mints on one run: exactly one create, all callers get the SAME token", async () => {
  freshEnv();
  const jobs = [1, 2, 3, 4, 5].map(() => mintSession("run-mint", ["q1", "q2", "q3"]));
  const results = await Promise.all(jobs);
  const tokens = results.map((r) => r.body.token);
  const created = results.filter((r) => r.body.status === "created");
  const reused = results.filter((r) => r.body.status === "exists");
  assert.ok(created.length <= 1, `at most one create (got ${created.length})`);
  assert.equal(created.length + reused.length, results.length, "every concurrent caller is answered");
  assert.equal(new Set(tokens).size, 1, "one active session token across all mints: " + tokens);
  // Exactly one session record exists for the run.
  const listed = await auth.STORE.list({ prefix: "sessions/" });
  assert.equal(listed.objects.length, 1);
});

test("P023-1b sequential re-mint after completion opens a NEW session (old pointer replaced under CAS)", async () => {
  freshEnv();
  const first = await mintSession("run-remint", ["a", "b"]);
  const token1 = first.body.token;
  const cap = { authorization: "Bearer " + token1 };
  await call("POST", `/api/sessions/${token1}/answers`, { body: { question_id: "a", value: "1", idempotency_key: "r1" }, headers: cap });
  await call("POST", `/api/sessions/${token1}/answers`, { body: { question_id: "b", value: "2", idempotency_key: "r2" }, headers: cap });
  await call("POST", `/api/sessions/${token1}/complete`, { body: {}, headers: cap });
  const second = await mintSession("run-remint", ["a", "b"]);
  assert.equal(second.body.status, "created", "completed run can mint a fresh session");
  assert.notEqual(second.body.token, token1);
  // Old session can no longer answer.
  const stale = await call("POST", `/api/sessions/${token1}/answers`, { body: { question_id: "a", value: "9", idempotency_key: "rz" }, headers: cap });
  assert.equal(stale.status, 409, "completed session refuses answers");
});

// ---- 2. concurrent answers: no loss, deterministic ---------------------------

test("P023-2 same question answered concurrently from two tabs with the SAME idempotency key: one accepted, replay returns the same body", async () => {
  freshEnv();
  const mint = await mintSession("run-ans1", ["a", "b", "c"]);
  const token = mint.body.token;
  const cap = { authorization: "Bearer " + token };
  const jobs = [1, 2, 3, 4].map(() =>
    call("POST", `/api/sessions/${token}/answers`, { body: { question_id: "a", value: "va", idempotency_key: "k1" }, headers: cap }));
  const results = await Promise.all(jobs);
  const accepted = results.filter((r) => r.body.status === "accepted");
  assert.equal(accepted.length, 1, "exactly one accept per tick");
  const replay = await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: "a", value: "TAMPERED", idempotency_key: "k1" }, headers: cap });
  assert.deepEqual(replay.body, accepted[0].body, "idempotent replay returns the original result verbatim, tamper ignored");
  // And the session advanced normally.
  const next = await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: "b", value: "vb", idempotency_key: "k2" }, headers: cap });
  assert.equal(next.body.status, "accepted");
});

test("P023-2b concurrent answers on DIFFERENT questions (double-tab page race): no answer lost", async () => {
  // Two tabs both believe 'a' is current; tab A answers a, tab B answers b.
  // The one-at-a-time contract means b is out-of-order when a lands first —
  // but the CAS layer must make the outcome deterministic and never LOSE an
  // accepted write: whichever write lands first is persisted, the other gets
  // a 409 with the expected question. Then b is answerable and IS accepted.
  freshEnv();
  const mint = await mintSession("run-ans2", ["a", "b"]);
  const token = mint.body.token;
  const cap = { authorization: "Bearer " + token };
  const [ra, rb] = await Promise.all([
    call("POST", `/api/sessions/${token}/answers`, { body: { question_id: "a", value: "va", idempotency_key: "ta" }, headers: cap }),
    call("POST", `/api/sessions/${token}/answers`, { body: { question_id: "b", value: "vb", idempotency_key: "tb" }, headers: cap }),
  ]);
  const acceptedFirst = [ra, rb].find((r) => r.body.status === "accepted");
  assert.ok(acceptedFirst, "one of the two concurrent answers is accepted");
  // Whatever was rejected comes back with the expected question (deterministic conflict).
  const rejected = [ra, rb].find((r) => r.body.status === "rejected");
  if (rejected) {
    assert.equal(rejected.status, 409);
    assert.ok(rejected.body.expected, "rejection names the expected question");
  }
  // The session now accepts the remaining question in order — no lost work.
  const state = await call("GET", `/api/sessions/${token}`, { headers: cap });
  const answered = state.body.answered;
  assert.equal(answered.length, 1, "exactly one answer persisted from the race");
  const remaining = ["a", "b"].find((q) => !answered.includes(q));
  const finish = await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: remaining, value: "v" + remaining, idempotency_key: "t" + remaining }, headers: cap });
  assert.equal(finish.body.status, "accepted", "the other question still answerable — nothing lost");
  const finalState = await call("GET", `/api/sessions/${token}`, { headers: cap });
  assert.equal(finalState.body.answered.length, 2, "both answers end up on record");
});

test("P023-2c CAS retries never lose a write under sustained contention", async () => {
  freshEnv();
  const mint = await mintSession("run-ans3", ["a", "b", "c", "d", "e", "f", "g", "h"]);
  const token = mint.body.token;
  const cap = { authorization: "Bearer " + token };
  // Answer strictly in order but with 3-way duplicated fire for each step —
  // every step must end with exactly one accepted value and no lost write.
  for (const q of ["a", "b", "c", "d", "e", "f", "g", "h"]) {
    const results = await Promise.all([1, 2, 3].map((n) =>
      call("POST", `/api/sessions/${token}/answers`, { body: { question_id: q, value: "v-" + q, idempotency_key: q + ":" + n }, headers: cap })));
    const accepted = results.filter((r) => r.body.status === "accepted");
    assert.equal(accepted.length, 1, `${q}: exactly one accept`);
    const revisions = new Set(accepted.map((r) => r.body.revision));
    assert.equal(revisions.size, 1, `${q}: all acceptors agree on one revision`);
  }
  const state = await call("GET", `/api/sessions/${token}`, { headers: cap });
  assert.equal(state.body.answered.length, 8);
  assert.equal(state.body.progress.complete, true);
});

// ---- 3. two-tab completion: stable final revision ----------------------------

test("P023-3 two-tab completion: same idempotency key replays one revision; different keys still one outbox event per revision", async () => {
  freshEnv();
  const mint = await mintSession("run-done", ["a", "b"]);
  const token = mint.body.token;
  const cap = { authorization: "Bearer " + token };
  for (const [q, v] of [["a", "1"], ["b", "2"]]) {
    await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: q, value: v, idempotency_key: "d-" + q }, headers: cap });
  }
  // Two tabs complete simultaneously with the SAME Idempotency-Key.
  const [r1, r2] = await Promise.all([
    call("POST", `/api/sessions/${token}/complete`, { body: {}, headers: { ...cap, "idempotency-key": "done-1" } }),
    call("POST", `/api/sessions/${token}/complete`, { body: {}, headers: { ...cap, "idempotency-key": "done-1" } }),
  ]);
  assert.equal(r1.body.status, "complete");
  assert.equal(r2.body.status, "complete");
  assert.equal(r1.body.revision, r2.body.revision, "same key: stable final revision");
  const { listOutbox } = await import("../deployed-r2/src/authority.js");
  const outbox = await listOutbox(auth.STORE);
  const mine = outbox.events.filter((e) => e.token === token);
  assert.equal(mine.length, 1, "exactly one outbox event for the session");
  assert.equal(mine[0].revision, r1.body.revision, "outbox event carries the final revision");

  // A DIFFERENT key later (recovery path): no second status flip; revision
  // stays the completed one; outbox not duplicated for the same revision.
  const r3 = await call("POST", `/api/sessions/${token}/complete`, { body: {}, headers: { ...cap, "idempotency-key": "done-2" } });
  assert.equal(r3.body.revision, r1.body.revision, "completion revision is final and monotonic-stable");
  const outbox2 = await listOutbox(auth.STORE);
  const mine2 = outbox2.events.filter((e) => e.token === token);
  assert.equal(mine2.length, 1, "no duplicate outbox event for the same revision");
});

test("P023-3b concurrent two-tab completion with DIFFERENT keys: one winner flips, revision monotonic, one outbox event", async () => {
  freshEnv();
  const mint = await mintSession("run-done2", ["a", "b"]);
  const token = mint.body.token;
  const cap = { authorization: "Bearer " + token };
  for (const [q, v] of [["a", "1"], ["b", "2"]]) {
    await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: q, value: v, idempotency_key: "e-" + q }, headers: cap });
  }
  const [r1, r2] = await Promise.all([
    call("POST", `/api/sessions/${token}/complete`, { body: {}, headers: { ...cap, "idempotency-key": "tabA" } }),
    call("POST", `/api/sessions/${token}/complete`, { body: {}, headers: { ...cap, "idempotency-key": "tabB" } }),
  ]);
  assert.equal(r1.body.status, "complete");
  assert.equal(r2.body.status, "complete");
  assert.equal(r1.body.revision, r2.body.revision, "both tabs observe the SAME final revision");
  const { listOutbox } = await import("../deployed-r2/src/authority.js");
  const outbox = await listOutbox(auth.STORE);
  assert.equal(outbox.events.filter((e) => e.token === token).length, 1);
  // Late answers refused after completion.
  const late = await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: "a", value: "x", idempotency_key: "late" }, headers: cap });
  assert.equal(late.status, 409);
});

// ---- 4. paginated scoped pending index --------------------------------------

function intakeBody(sessionId, seq) {
  return {
    file_name: "intake-" + sessionId + ".json",
    intake: {
      intake_session_id: sessionId, company_id: "test-company", installation_id: "test-installation", presentation_id: "test-presentation", run_id: "test-run",
      deck_brief: {
        OFFER_NAME: "Offer " + seq, NAMED_METHODOLOGY: "M", TRANSFORMATION_PROMISE: "T",
        TIME_TO_RESULT: "30d", AUDIENCE: "A", CTA_ACTION: "C", TONE: "Tone",
        FINAL_PRICE: "$1", WANT_SALES_CHECKOUT: "no", WANT_VSL_PAGE: "no",
      },
      pre_presentation_capture: { PRESENTATION_TYPE: "signature", WANT_SALES_CHECKOUT: "no", WANT_VSL_PAGE: "no" },
    },
  };
}

test("P023-4 more submissions than one page: all discovered exactly once", async () => {
  freshEnv();
  const total = 250; // > default page limit 100
  const seqs = [];
  for (let i = 0; i < total; i++) {
    const sid = "sess-" + String(i).padStart(4, "0");
    seqs.push(sid);
    const r = await call("POST", "/api/intake", { body: intakeBody(sid, i), headers: admin });
    assert.equal(r.status, 201);
  }
  // Walk the pagination the way the bridge does.
  const seen = [];
  let cursor;
  for (let page = 0; page < 10; page++) {
    const q = { limit: "100" };
    if (cursor) q.cursor = cursor;
    const r = await call("GET", "/api/intake/list", { headers: admin, query: q });
    seen.push(...r.body.intakes.map((x) => x.session_id));
    if (!r.body.truncated) break;
    cursor = r.body.cursor;
  }
  assert.equal(seen.length, total, "every submission discovered");
  assert.equal(new Set(seen).size, total, "each discovered exactly once");
});

test("P023-5 restart cursor halfway: no lost work", async () => {
  freshEnv();
  const total = 150;
  for (let i = 0; i < total; i++) {
    await call("POST", "/api/intake", { body: intakeBody("rst-" + String(i).padStart(4, "0"), i), headers: admin });
  }
  // Page 1 processed, then "crash" (drop the cursor), then resume from the
  // saved cursor — the union must still cover every session exactly once.
  const p1 = await call("GET", "/api/intake/list", { headers: admin, query: { limit: "100" } });
  assert.equal(p1.body.truncated, true);
  const processedFromP1 = p1.body.intakes.map((x) => x.session_id);
  const savedCursor = p1.body.cursor; // durable restart point
  const p2 = await call("GET", "/api/intake/list", { headers: admin, query: { limit: "100", cursor: savedCursor } });
  const seen = new Set([...processedFromP1, ...p2.body.intakes.map((x) => x.session_id)]);
  assert.equal(seen.size, total, "resume from saved cursor loses nothing");
  assert.equal(p2.body.truncated, false, "second page ends the listing");
});

test("P023-6 ack removes processed rows: large processed history does not grow discovery", async () => {
  freshEnv();
  // 120 processed sessions get acked off the index.
  for (let i = 0; i < 120; i++) {
    await call("POST", "/api/intake", { body: intakeBody("old-" + String(i).padStart(4, "0"), i), headers: admin });
  }
  const all = [];
  let cursor;
  for (;;) {
    const q = { limit: "100" };
    if (cursor) q.cursor = cursor;
    const r = await call("GET", "/api/intake/list", { headers: admin, query: q });
    all.push(...r.body.intakes);
    if (!r.body.truncated) break;
    cursor = r.body.cursor;
  }
  assert.equal(all.length, 120);
  // Ack every row (bridge behavior after ingest).
  for (const it of all) {
    await call("GET", "/api/intake/list", { headers: admin, query: { ack: it.session_id, stored_at: String(it.stored_at) } });
  }
  // Discovery now sees an EMPTY pending index in ONE page — history size did
  // not make discovery slower or bigger.
  const after = await call("GET", "/api/intake/list", { headers: admin, query: { limit: "100" } });
  assert.equal(after.body.intakes.length, 0, "acked history is not rescanned");
  assert.equal(after.body.truncated, false);
  // New submission lands and is discovered immediately.
  await call("POST", "/api/intake", { body: intakeBody("new-0000", 999), headers: admin });
  const fresh = await call("GET", "/api/intake/list", { headers: admin, query: { limit: "100" } });
  assert.deepEqual(fresh.body.intakes.map((x) => x.session_id), ["new-0000"]);
});

test("P023-7 claim/lease: one claimant per row, foreign claim refused while live, expiry self-heals", async () => {
  freshEnv();
  await call("POST", "/api/intake", { body: intakeBody("lease-1", 1), headers: admin });
  const page = await call("GET", "/api/intake/list", { headers: admin, query: { claim: "1", owner: "box-1" } });
  assert.equal(page.body.claimed, 1);
  // A second box cannot claim the live lease.
  const page2 = await call("GET", "/api/intake/list", { headers: admin, query: { claim: "1", owner: "box-2" } });
  assert.equal(page2.body.claimed, 0);
  assert.equal(page2.body.skipped, 1);
  // Simulate lease expiry: backdate the lease, then box-2 claims successfully.
  const rowKeys = await auth.STORE.list({ prefix: "tenant-index/test-company/test-installation/intakes-index/" });
  const key = rowKeys.objects[0].key;
  const obj = await auth.STORE.get(key);
  const rec = JSON.parse(await obj.text());
  rec.lease.expires_at = 1; // expired
  await auth.STORE.put(key, JSON.stringify(rec), { onlyIf: { etagMatches: obj.etag } });
  const page3 = await call("GET", "/api/intake/list", { headers: admin, query: { claim: "1", owner: "box-2" } });
  assert.equal(page3.body.claimed, 1, "expired lease is claimable (self-healing)");
});

test("P023-8 answer cursor (since) remains monotonic and complete for the sync bridge", async () => {
  freshEnv();
  const mint = await mintSession("run-sync", ["a", "b", "c"]);
  const token = mint.body.token;
  const cap = { authorization: "Bearer " + token };
  for (const q of ["a", "b"]) {
    await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: q, value: "v-" + q, idempotency_key: "s-" + q }, headers: cap });
  }
  const poll1 = await call("GET", `/api/sessions/${token}/answers`, { headers: cap, query: { since: "0" } });
  assert.equal(poll1.body.answers.length, 2);
  const cur = poll1.body.cursor;
  const poll2 = await call("GET", `/api/sessions/${token}/answers`, { headers: cap, query: { since: String(cur) } });
  assert.equal(poll2.body.answers.length, 0, "cursor resume: nothing redelivered");
  // A NEW answer (one-at-a-time contract: 'c' follows 'b') produces a NEW
  // monotonic id the poller has not seen — never redelivery, never reuse.
  await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: "c", value: "v-c", idempotency_key: "s-c" }, headers: cap });
  const poll3 = await call("GET", `/api/sessions/${token}/answers`, { headers: cap, query: { since: String(cur) } });
  assert.equal(poll3.body.answers.length, 1);
  assert.ok(Number(poll3.body.answers[0].id) > cur);
  assert.equal(poll3.body.answers[0].value, "v-c");
  assert.equal(poll3.body.answers[0].question_id, "c");
  // Every answer id is strictly monotonic across the whole session.
  const ids = poll1.body.answers.map((r) => Number(r.id)).concat(poll3.body.answers.map((r) => Number(r.id)));
  assert.deepEqual(ids, [...ids].sort((x, y) => x - y), "answer ids strictly monotonic");
  // And a replayed idempotency key does NOT mint another id (no dup rows).
  const again = await call("POST", `/api/sessions/${token}/answers`, { body: { question_id: "c", value: "v-c", idempotency_key: "s-c" }, headers: cap });
  assert.equal(again.body.status, "accepted", "idempotent replay accepted");
  const poll4 = await call("GET", `/api/sessions/${token}/answers`, { headers: cap, query: { since: String(cur) } });
  assert.equal(poll4.body.answers.length, 1, "replay minted no extra row");
});

test("P023-9 legacy contract intact: mint exists-replay, confirm-code gate, poll shape", async () => {
  freshEnv();
  const m1 = await mintSession("run-legacy", ["q1", "q2"], { mint: { want_confirm_code: true } });
  assert.equal(m1.status, 201);
  assert.ok(m1.body.confirm_code, "confirm code minted");
  const m2 = await mintSession("run-legacy", ["q1", "q2"]);
  assert.equal(m2.body.status, "exists");
  assert.equal(m2.body.token, m1.body.token, "re-mint replays the live session");
  const cap = { authorization: "Bearer " + m1.body.token };
  const noCode = await call("POST", `/api/sessions/${m1.body.token}/answers`, { body: { question_id: "q1", value: "x" }, headers: cap });
  assert.equal(noCode.status, 401, "confirm code required");
  const withCode = await call("POST", `/api/sessions/${m1.body.token}/answers`, { body: { question_id: "q1", value: "x", confirm_code: m1.body.confirm_code, idempotency_key: "l1" }, headers: cap });
  assert.equal(withCode.body.status, "accepted");
  const incomplete = await call("POST", "/api/intake", { body: { file_name: "bad.json", intake: {} }, headers: admin });
  assert.equal(incomplete.status, 422, "completeness gate intact");
  const blocked = await (async () => {
    const t = (await mintSession("run-block", ["a", "b"])).body.token;
    return call("POST", `/api/sessions/${t}/complete`, { body: {}, headers: { authorization: "Bearer " + t } });
  })();
  assert.equal(blocked.status, 409, "missing-required gate intact");
  assert.deepEqual(blocked.body.missing, ["a", "b"]);
});
