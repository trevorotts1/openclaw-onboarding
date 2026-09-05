// Book Writer Mini-App — U03 answers POST offline unit gate.
//
// No Cloudflare runtime, no network, no GHL — just `node --test`. A stubbed
// KV stands in for env.BW_BINDINGS. The three properties this gate locks are
// the master-plan section-3 invariants for the edge worker:
//
//   1. NORMAL submit  -> answer staged under the token-bound client prefix,
//                        receipt returned (201).
//   2. REPLAY         -> a second submit of an already-consumed step is
//                        REJECTED (409), never duplicated.
//   3. INJECTED DEST  -> a request carrying location_id/contact_id/client_id
//                        has those fields IGNORED; the KV binding row is the
//                        SOLE authority for where the answer lands.
//
// Plus the tamper/expiry negatives from section 3 (401s) and the per-step
// consumed counter from section 8's failure-mode table.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  isValidTokenShape,
  normalizeAnswerValue,
  normalizeAnswerObject,
  validateAnswersPayload,
  checkBinding,
  answerKeys,
  stagedKeyFor,
  decideSubmit,
  handleAnswersPost,
  donePageResponse,
} from "./answers.js";

// ---- Stub KV ---------------------------------------------------------------
// Cloudflare-style KV: get(key, {type:"json"}) -> parsed value or null;
// put(key, value) stores the string. In-memory for tests.
function stubKv(seed = {}) {
  const store = new Map(Object.entries(seed));
  return {
    store,
    async get(key, opts) {
      const v = store.get(key);
      if (v === undefined) return null;
      if (opts && opts.type === "json") {
        try { return JSON.parse(v); } catch { return null; }
      }
      return v;
    },
    async put(key, value) {
      store.set(key, String(value));
    },
  };
}

function bindingRow(over = {}) {
  return {
    client_id: "fixture-client-b",
    location_id: "loc_a_fake",
    phase_id: "intake",
    run_id: "run_abc123",
    intake_id: "int_abc123",
    exp: 2_000_000_000,
    status: "open",
    ...over,
  };
}

// The canonical 32-hex token used by the minting unit (U02).
const TOKEN = "a1b2c3d4e5f60718293a4b5c6d7e8f90";

function answersRequest(bodyObj) {
  const url = `https://bookwriter.zerohumanworkforce.com/api/answers?tk=${TOKEN}`;
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(bodyObj),
  });
}

// ---------------------------------------------------------------------------
// Token shape
// ---------------------------------------------------------------------------
test("isValidTokenShape accepts 32 lowercase-hex, rejects others", () => {
  assert.ok(isValidTokenShape(TOKEN));
  assert.ok(!isValidTokenShape("nope"));
  assert.ok(!isValidTokenShape(TOKEN.toUpperCase()));
  assert.ok(!isValidTokenShape(TOKEN.slice(0, 31)));
});

// ---------------------------------------------------------------------------
// Normalization (ONE boundary)
// ---------------------------------------------------------------------------
test("normalizeAnswerValue trims and strips control chars", () => {
  assert.equal(normalizeAnswerValue("  first_name  "), "first_name");
  assert.equal(normalizeAnswerValue("  hello world  "), "hello world");
  // Sloppy source keys with trailing spaces (intake-schema.json defect set).
  assert.equal(normalizeAnswerValue("firstname "), "firstname");
  assert.equal(normalizeAnswerValue("Idealavatar "), "Idealavatar");
  // Non-strings pass through untouched.
  assert.equal(normalizeAnswerValue(42), 42);
  assert.deepEqual(normalizeAnswerValue(["a"]), ["a"]);
});

test("normalizeAnswerObject strips key whitespace and ignores injected destination keys", () => {
  const raw = {
    "first_name ": " Jane ",
    "book_about ": "  My story  ",
    location_id: "loc_b_fake",   // INJECTED — must be dropped
    contact_id: "c_attacker",    // INJECTED — must be dropped
    client_id: "someone-else",   // INJECTED — must be dropped
    answer: "hello",
  };
  const out = normalizeAnswerObject(raw);
  assert.equal(out["first_name "], undefined);
  assert.equal(out.first_name, "Jane");
  assert.equal(out.book_about, "My story");
  assert.equal(out.location_id, undefined);
  assert.equal(out.contact_id, undefined);
  assert.equal(out.client_id, undefined);
  assert.deepEqual(Object.keys(out).sort(), ["answer", "book_about", "first_name"]);
});

// ---------------------------------------------------------------------------
// Payload validation
// ---------------------------------------------------------------------------
test("validateAnswersPayload requires question_id + answer", () => {
  assert.ok(validateAnswersPayload(JSON.stringify({ question_id: "q1", answer: "x" })).ok);
  assert.ok(!validateAnswersPayload(JSON.stringify({ answer: "x" })).ok);
  assert.ok(!validateAnswersPayload(JSON.stringify({ question_id: "q1" })).ok);
  assert.ok(!validateAnswersPayload("not json").ok);
  assert.ok(!validateAnswersPayload("").ok);
});

// ---------------------------------------------------------------------------
// Binding checks (tamper / expiry / completed)
// ---------------------------------------------------------------------------
test("checkBinding rejects unknown, expired, completed bindings", () => {
  assert.ok(!checkBinding(null).ok);
  assert.equal(checkBinding(null).status, 401);
  assert.ok(!checkBinding(bindingRow({ exp: 1 })).ok); // expired
  assert.equal(checkBinding(bindingRow({ exp: 1 })).status, 401);
  assert.ok(!checkBinding(bindingRow({ status: "completed" })).ok);
  assert.equal(checkBinding(bindingRow({ status: "completed" })).status, 410);
  assert.ok(checkBinding(bindingRow()).ok);
});

// ---------------------------------------------------------------------------
// Keys
// ---------------------------------------------------------------------------
test("answerKeys build per-client consumed + staged keys", () => {
  const b = bindingRow();
  const { consumed, staged } = answerKeys(b, "first_name");
  assert.equal(consumed, "consumed:run_abc123:intake:first_name");
  assert.equal(staged, "answer:fixture-client-b:run_abc123:intake:first_name");
  assert.equal(stagedKeyFor(b, "first_name"), staged);
});

// ---------------------------------------------------------------------------
// decideSubmit — pure core
// ---------------------------------------------------------------------------
test("decideSubmit accepts a fresh step and records the BOUND destination", () => {
  const b = bindingRow();
  // decideSubmit receives the payload AFTER the normalize boundary
  // (validateAnswersPayload -> normalizeAnswerObject), so values are trimmed.
  const d = decideSubmit({
    binding: b,
    qid: "book_about",
    normalized: { question_id: "book_about", answer: "My book", source: "typed" },
    nowSec: 1_700_000_000,
    stagedExisting: null,
    consumedExisting: null,
  });
  assert.ok(d.ok);
  assert.equal(d.answer.answer, "My book");
  assert.equal(d.answer.destination.client_id, "fixture-client-b");
  assert.equal(d.answer.destination.location_id, "loc_a_fake");
  assert.equal(d.answer.destination.phase_id, "intake");
  assert.equal(d.answer.destination.run_id, "run_abc123");
});

test("decideSubmit REJECTS a replayed/consumed step (409, no duplicate)", () => {
  const b = bindingRow();
  const replay = decideSubmit({
    binding: b,
    qid: "first_name",
    normalized: { question_id: "first_name", answer: "Jane" },
    nowSec: 1_700_000_000,
    stagedExisting: null,
    consumedExisting: { ts: 1_699_000_000, status: "consumed" },
  });
  assert.ok(!replay.ok);
  assert.equal(replay.status, 409);
  assert.ok(replay.receipt.already_recorded);

  // Staged-present also counts as consumed.
  const stagedPresent = decideSubmit({
    binding: b,
    qid: "first_name",
    normalized: { question_id: "first_name", answer: "Jane2" },
    nowSec: 1_700_000_000,
    stagedExisting: { qid: "first_name" },
    consumedExisting: null,
  });
  assert.ok(!stagedPresent.ok);
  assert.equal(stagedPresent.status, 409);
});

test("decideSubmit trims a padded qid for the consumed key", () => {
  const b = bindingRow();
  // In the real flow validateAnswersPayload normalizes question_id; the pure
  // core also trims defensively so 'first_name ' and 'first_name' are the same
  // step (idempotency survives a padded replay).
  const a = decideSubmit({
    binding: b, qid: "first_name ",
    normalized: { question_id: "first_name ", answer: "Jane" },
    nowSec: 1_700_000_000, stagedExisting: null, consumedExisting: null,
  });
  assert.ok(a.ok);
  assert.equal(a.answer.qid, "first_name");
  // stagedKeyFor trims, so a padded qid resolves to the SAME staged key as the
  // clean qid — a replayed padded submit collides with the original.
  assert.equal(stagedKeyFor(b, "first_name "), "answer:fixture-client-b:run_abc123:intake:first_name");
  assert.equal(stagedKeyFor(b, "first_name"), "answer:fixture-client-b:run_abc123:intake:first_name");
});

// ---------------------------------------------------------------------------
// End-to-end via the Worker handler (stubbed KV)
// ---------------------------------------------------------------------------
test("NORMAL submit: stores answer under the bound client prefix + receipts", async () => {
  const kv = stubKv({ [`binding:${TOKEN}`]: JSON.stringify(bindingRow()) });
  const env = { BW_BINDINGS: kv };
  const res = await handleAnswersPost(answersRequest({ question_id: "book_about", answer: "My book", source: "typed" }), env, 1_700_000_000);
  assert.equal(res.status, 201);
  const body = await res.json();
  assert.ok(body.ok);
  assert.equal(body.receipt.client_id, "fixture-client-b");
  assert.equal(body.receipt.phase_id, "intake");
  assert.equal(body.receipt.run_id, "run_abc123");
  assert.equal(body.done_page, "/done");
  // Consumed counter + staged answer exist.
  const consumed = await kv.get("consumed:run_abc123:intake:book_about", { type: "json" });
  assert.equal(consumed.status, "consumed");
  const staged = await kv.get("answer:fixture-client-b:run_abc123:intake:book_about", { type: "json" });
  assert.equal(staged.answer, "My book");
  assert.equal(staged.destination.client_id, "fixture-client-b");
  // Staged under the BOUND client prefix — nothing under any other client.
  assert.ok(!(await kv.get("answer:loc_b_fake:run_abc123:intake:book_about", { type: "json" })));
});

test("REPLAY of a consumed step is rejected (409), never duplicated", async () => {
  const kv = stubKv({
    [`binding:${TOKEN}`]: JSON.stringify(bindingRow()),
    "consumed:run_abc123:intake:first_name": JSON.stringify({ ts: 1_699_000_000, status: "consumed" }),
    "answer:fixture-client-b:run_abc123:intake:first_name": JSON.stringify({ qid: "first_name", answer: "Jane" }),
  });
  const env = { BW_BINDINGS: kv };
  const res = await handleAnswersPost(answersRequest({ question_id: "first_name", answer: "Jane" }), env, 1_700_000_000);
  assert.equal(res.status, 409);
  const body = await res.json();
  assert.equal(body.error, "step already answered");
  assert.ok(!body.ok);
  // No duplicate staged answer was written.
  const staged = await kv.get("answer:fixture-client-b:run_abc123:intake:first_name", { type: "json" });
  assert.equal(staged.answer, "Jane");
});

test("INJECTED destination is IGNORED — binding row is the sole authority", async () => {
  const kv = stubKv({ [`binding:${TOKEN}`]: JSON.stringify(bindingRow()) });
  const env = { BW_BINDINGS: kv };
  const malicious = {
    question_id: "niche",
    answer: "cats",
    location_id: "loc_b_fake",   // injection attempt
    contact_id: "c_attacker",    // injection attempt
    client_id: "someone-else",   // injection attempt
  };
  const res = await handleAnswersPost(answersRequest(malicious), env, 1_700_000_000);
  assert.equal(res.status, 201);
  const staged = await kv.get("answer:fixture-client-b:run_abc123:intake:niche", { type: "json" });
  assert.ok(staged);
  assert.equal(staged.destination.client_id, "fixture-client-b");
  assert.equal(staged.destination.location_id, "loc_a_fake");
  // Injected values never leaked into the staged record.
  assert.equal(staged.answer, "cats");
  assert.equal(staged.location_id, undefined);
  assert.equal(staged.contact_id, undefined);
  assert.equal(staged.client_id, undefined);
  // Nothing staged under the injected client's prefix.
  assert.ok(!(await kv.get("answer:someone-else:run_abc123:intake:niche", { type: "json" })));
});

test("tampered/unknown token -> 401 with zero writes", async () => {
  const kv = stubKv({}); // no binding row for any token
  const env = { BW_BINDINGS: kv };
  const url = "https://bookwriter.zerohumanworkforce.com/api/answers?tk=ffffffffffffffffffffffffffffffff";
  const res = await handleAnswersPost(new Request(url, { method: "POST", body: JSON.stringify({ question_id: "x", answer: "y" }) }), env, 1_700_000_000);
  assert.equal(res.status, 401);
  assert.equal(kv.store.size, 0);
});

test("expired token -> 401", async () => {
  const kv = stubKv({ [`binding:${TOKEN}`]: JSON.stringify(bindingRow({ exp: 1 })) });
  const env = { BW_BINDINGS: kv };
  const res = await handleAnswersPost(answersRequest({ question_id: "x", answer: "y" }), env, 1_700_000_000);
  assert.equal(res.status, 401);
  assert.equal(kv.store.size, 1); // only the binding row, no writes
});

test("completed binding -> 410", async () => {
  const kv = stubKv({ [`binding:${TOKEN}`]: JSON.stringify(bindingRow({ status: "completed" })) });
  const env = { BW_BINDINGS: kv };
  const res = await handleAnswersPost(answersRequest({ question_id: "x", answer: "y" }), env, 1_700_000_000);
  assert.equal(res.status, 410);
});

test("bad token shape -> 400 before any KV read", async () => {
  const kv = stubKv({});
  const env = { BW_BINDINGS: kv };
  const url = "https://bookwriter.zerohumanworkforce.com/api/answers?tk=not-a-token";
  const res = await handleAnswersPost(new Request(url, { method: "POST", body: "{}" }), env, 1_700_000_000);
  assert.equal(res.status, 400);
});

test("missing KV binding -> 503", async () => {
  const res = await handleAnswersPost(answersRequest({ question_id: "x", answer: "y" }), {}, 1_700_000_000);
  assert.equal(res.status, 503);
});

test("done page is warm, no banned strings", async () => {
  const res = donePageResponse();
  assert.equal(res.status, 200);
  const html = await res.text();
  assert.match(html, /Received — thank you/);
  for (const banned of ["Submit", "Required", "Error", "Deadline", "You must"]) {
    assert.ok(!html.includes(banned), `banned string present: ${banned}`);
  }
});
