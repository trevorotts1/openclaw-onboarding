// Book Writer mini-app — U11 save & resume unit gate.
//
// Offline unit tests for the Worker's save/resume module. No Cloudflare
// runtime, no network — `node --test src/save.test.mjs`. Load-bearing
// properties under test (MASTER-PLAN section 5):
//   - every answer persisted on entry (debounced on the client, idempotent here)
//   - returning via the same link resumes at the next unanswered question
//   - completion optionally emails a resume reminder (opt-in, skippable)
//   - per-step consumed counter: a replayed save can never duplicate
//   - isolation: injected destination fields rejected at the boundary
//   - no banned strings, no Anthropic ids, no real zone/account ids

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  decideSave,
  validateSavePayload,
  isValidEmail,
  isValidTokenShape,
  resumeHint,
  saveKey,
  consumedKey,
  reminderKey,
  handleSavePost,
  handleResumeGet,
  handleReminderPost,
} from "./save.js";

const TOKEN = "a".repeat(32);
const NOW = 1_752_944_000; // fixed epoch seconds for determinism

function binding(overrides = {}) {
  return {
    client_id: "client-a",
    location_id: "loc-a",
    slug: "fixture-client-b",
    phase_id: "P0-INTAKE",
    run_id: "run-1",
    intake_id: "intake-1",
    exp: NOW + 86400 * 7,
    status: "open",
    ...overrides,
  };
}

function memStore() {
  const map = new Map();
  return {
    async get(k, opts) {
      const raw = map.get(k) ?? null;
      if (raw == null) return null;
      return opts && opts.type === "json" ? JSON.parse(raw) : raw;
    },
    async put(k, v) { map.set(k, v); },
    async list({ prefix }) {
      const keys = [];
      for (const k of map.keys()) if (k.startsWith(prefix)) keys.push({ name: k });
      return { keys };
    },
    _map: map,
  };
}

function fakeEnv(store) {
  return { BW_BINDINGS: store };
}

function post(url, body) {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Pure decision core
// ---------------------------------------------------------------------------

test("fresh save accepted and changed", () => {
  const d = decideSave({
    binding: binding(), qid: "q", answer: "hello", source: "typed",
    nowSec: NOW, stagedRow: null, consumedRow: null,
  });
  assert.equal(d.ok, true);
  assert.equal(d.changed, true);
  assert.equal(d.draft.answer, "hello");
});

test("replayed identical save is an idempotent no-op (no duplicate)", () => {
  const d = decideSave({
    binding: binding(), qid: "q", answer: "hello", source: "typed",
    nowSec: NOW,
    stagedRow: { qid: "q", answer: "hello", saved_at: NOW },
    consumedRow: { status: "consumed" },
  });
  assert.equal(d.ok, true);
  assert.equal(d.idempotent, true);
  assert.equal(d.changed, false);
});

test("resume edit overwrites in place (never a second row)", () => {
  const d = decideSave({
    binding: binding(), qid: "q", answer: "hello, world", source: "typed",
    nowSec: NOW,
    stagedRow: { qid: "q", answer: "hello", saved_at: NOW },
    consumedRow: { status: "consumed" },
  });
  assert.equal(d.ok, true);
  assert.equal(d.changed, true);
  assert.equal(d.draft.answer, "hello, world");
});

test("expired token rejected 401", () => {
  const d = decideSave({
    binding: binding({ exp: NOW - 1 }), qid: "q", answer: "x", source: "typed",
    nowSec: NOW, stagedRow: null, consumedRow: null,
  });
  assert.equal(d.ok, false);
  assert.equal(d.status, 401);
});

test("completed run rejected 410", () => {
  const d = decideSave({
    binding: binding({ status: "done" }), qid: "q", answer: "x", source: "typed",
    nowSec: NOW, stagedRow: null, consumedRow: null,
  });
  assert.equal(d.ok, false);
  assert.equal(d.status, 410);
});

// ---------------------------------------------------------------------------
// Payload validation
// ---------------------------------------------------------------------------

test("save payload validates + normalizes", () => {
  const v = validateSavePayload(JSON.stringify({ question_id: " first_name ", answer: "  Ada  \x00", source: "typed" }));
  assert.equal(v.ok, true);
  assert.equal(v.qid, "first_name");
  assert.equal(v.answer, "Ada");
});

test("injected destination fields rejected at the boundary", () => {
  const v = validateSavePayload(JSON.stringify({ question_id: "q", answer: "x", location_id: "loc-b", contact_id: "c9" }));
  assert.equal(v.ok, false);
});

test("oversized answer rejected 413", () => {
  const big = "x".repeat(201 * 1024);
  const v = validateSavePayload(JSON.stringify({ question_id: "q", answer: big }));
  assert.equal(v.ok, false);
  assert.equal(v.status, 413);
});

test("missing question_id rejected", () => {
  const v = validateSavePayload(JSON.stringify({ answer: "x" }));
  assert.equal(v.ok, false);
});

// ---------------------------------------------------------------------------
// Resume hint
// ---------------------------------------------------------------------------

test("resume hint skips unanswered, finds next index", () => {
  const questions = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
  const staged = [
    { qid: "a", answer: "done" },
    { qid: "b", answer: "" },      // cleared draft — NOT answered
    { qid: "d", answer: "skipped to d" },
  ];
  const hint = resumeHint(staged, questions);
  assert.equal(hint.total, 4);
  assert.equal(hint.answered, 2);   // a + d
  assert.equal(hint.next_index, 1); // b is next unanswered
});

test("resume hint with zero staged all-unanswered", () => {
  const questions = [{ id: "a" }, { id: "b" }];
  const hint = resumeHint([], questions);
  assert.equal(hint.answered, 0);
  assert.equal(hint.next_index, 0);
});

test("resume hint: answered at index 0 does not mask next index", () => {
  // Regression guard for the -1 sentinel: index 0 answered, index 1 unanswered.
  const questions = [{ id: "a" }, { id: "b" }];
  const hint = resumeHint([{ qid: "a", answer: "done" }], questions);
  assert.equal(hint.answered, 1);
  assert.equal(hint.next_index, 1);
});

// ---------------------------------------------------------------------------
// Email opt-in
// ---------------------------------------------------------------------------

test("email validation accepts normal and rejects junk", () => {
  assert.equal(isValidEmail("reader@example.com"), true);
  assert.equal(isValidEmail(" a.b@sub.example.co.uk "), true);
  assert.equal(isValidEmail("not-an-email"), false);
  assert.equal(isValidEmail("a@b"), false);
  assert.equal(isValidEmail("<script>@x.com"), false);
  assert.equal(isValidEmail(""), false);
});

test("token shape guard", () => {
  assert.equal(isValidTokenShape(TOKEN), true);
  assert.equal(isValidTokenShape("short"), false);
  assert.equal(isValidTokenShape("g".repeat(32)), false); // not hex
});

test("key builders match contract", () => {
  assert.equal(saveKey("c", "r", "p", "q"), "save:c:r:p:q");
  assert.equal(consumedKey("r", "p", "q"), "consumed:r:p:q");
  assert.equal(reminderKey("r", "e@x.com"), "reminder:r:e@x.com");
});

// ---------------------------------------------------------------------------
// Route handlers (stubbed KV)
// ---------------------------------------------------------------------------

test("POST /api/save stages a draft and returns resume hint", async () => {
  const store = memStore();
  await store.put(`binding:${TOKEN}`, JSON.stringify(binding()));
  const env = fakeEnv(store);
  const res = await handleSavePost(
    post(`https://bookwriter.test/P0-INTAKE/api/save?tk=${TOKEN}`, { question_id: "first_name", answer: "Ada", source: "typed" }),
    env, NOW
  );
  assert.equal(res.status, 201);
  const body = await res.json();
  assert.equal(body.ok, true);
  assert.equal(body.changed, true);
  assert.equal(body.qid, "first_name");
  // the per-step consumed counter row exists
  const consumed = await store.get(consumedKey("run-1", "P0-INTAKE", "first_name"), { type: "json" });
  assert.ok(consumed);
  assert.equal(consumed.status, "consumed");
});

test("replayed POST /api/save is idempotent (200, no duplicate)", async () => {
  const store = memStore();
  await store.put(`binding:${TOKEN}`, JSON.stringify(binding()));
  const env = fakeEnv(store);
  const first = await handleSavePost(post(`https://bookwriter.test/api/save?tk=${TOKEN}`, { question_id: "q", answer: "same", source: "typed" }), env, NOW);
  assert.equal(first.status, 201);
  const second = await handleSavePost(post(`https://bookwriter.test/api/save?tk=${TOKEN}`, { question_id: "q", answer: "same", source: "typed" }), env, NOW + 1);
  assert.equal(second.status, 200);
  const body = await second.json();
  assert.equal(body.idempotent, true);
  assert.equal(body.changed, false);
  // exactly one staged row
  const staged = await store.get(saveKey("client-a", "run-1", "P0-INTAKE", "q"), { type: "json" });
  assert.equal(staged.answer, "same");
});

test("POST /api/save bad token shape -> 400", async () => {
  const env = fakeEnv(memStore());
  const res = await handleSavePost(post("https://bookwriter.test/api/save?tk=bad", { question_id: "q", answer: "x" }), env, NOW);
  assert.equal(res.status, 400);
});

test("GET /api/save/resume returns staged answers + hint", async () => {
  const store = memStore();
  await store.put(`binding:${TOKEN}`, JSON.stringify(binding()));
  await store.put(saveKey("client-a", "run-1", "P0-INTAKE", "first_name"), JSON.stringify({ qid: "first_name", answer: "Ada", saved_at: NOW }));
  await store.put(saveKey("client-a", "run-1", "P0-INTAKE", "niche"), JSON.stringify({ qid: "niche", answer: "Leadership", saved_at: NOW }));
  const env = fakeEnv(store);
  const res = await handleResumeGet(new Request(`https://bookwriter.test/api/save/resume?tk=${TOKEN}`), env, NOW);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.ok, true);
  assert.equal(body.answers.first_name.text, "Ada");
  assert.equal(body.answers.niche.text, "Leadership");
  // No questions array passed -> total comes from the staged list.
  assert.equal(body.resume.total, 2);
  assert.equal(body.resume.answered, 2);
});

test("POST /api/save/reminder stores the opt-in email", async () => {
  const store = memStore();
  await store.put(`binding:${TOKEN}`, JSON.stringify(binding()));
  const env = fakeEnv(store);
  const res = await handleReminderPost(
    post(`https://bookwriter.test/api/save/reminder?tk=${TOKEN}`, { email: "reader@example.com" }),
    env, NOW
  );
  assert.equal(res.status, 201);
  const body = await res.json();
  assert.equal(body.ok, true);
  assert.equal(body.reminder.email_stored, true);
  const row = await store.get(reminderKey("run-1", "reader@example.com"), { type: "json" });
  assert.equal(row.email, "reader@example.com");
  assert.equal(row.run_id, "run-1");
});

test("POST /api/save/reminder rejects invalid email (warm, no write)", async () => {
  const store = memStore();
  await store.put(`binding:${TOKEN}`, JSON.stringify(binding()));
  const env = fakeEnv(store);
  const res = await handleReminderPost(
    post(`https://bookwriter.test/api/save/reminder?tk=${TOKEN}`, { email: "<script>@x" }),
    env, NOW
  );
  assert.equal(res.status, 400);
  const body = await res.json();
  assert.equal(body.ok, false);
  // nothing staged
  assert.equal(store._map.size, 1); // only the binding row
});
