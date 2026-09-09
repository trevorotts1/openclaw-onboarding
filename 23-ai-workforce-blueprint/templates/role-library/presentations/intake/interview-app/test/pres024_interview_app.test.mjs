// PRES-024 offline integration gate — the QC-PRES-024 battery against the
// interview-app D1 worker, on a REAL SQLite engine (node:sqlite) executing the
// REAL schema (worker/schema.sql).
//   node --test test/pres024_interview_app.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { D1Shim, makeDb, WorkerHarness, PAYLOAD } from "../../../intake-miniapp/test/pres024_env.mjs";
import worker from "../worker/src/index.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCHEMA = path.resolve(HERE, "../worker/schema.sql");

function makeEnv() {
  return { DB: new D1Shim(makeDb([SCHEMA])), INTAKE_ADMIN_TOKEN: "admin-tok" };
}

async function mint(h, runId, extra = {}) {
  const res = await h.handle("POST", "/api/sessions", {
    token: "admin-tok",
    body: { run_id: runId, box_id: "box1", questions_payload: PAYLOAD, company_id: "acme", recipient_chat_id: "111", ...extra },
  });
  assert.equal(res.status, 201, "mint should create: " + JSON.stringify(res));
  return res.body;
}

async function answer(h, token, questionId, value) {
  return h.handle("POST", `/api/sessions/${token}/answers`, { body: { question_id: questionId, value } });
}

test("PRES-024 [interview-app D1]: expire mid-interview, renew — answers intact, correct resume question, old token rejected, wrong company rejected", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-expire");

  let r = await answer(h, s.token, "offer_name", "The Momentum Method");
  assert.equal(r.status, 200);
  r = await answer(h, s.token, "tone", "bold");
  assert.equal(r.status, 200);

  env.DB.db.prepare("UPDATE sessions SET expires_at = 1 WHERE token = ?").run(s.token);
  r = await h.handle("GET", `/api/sessions/${s.token}`);
  assert.equal(r.status, 410);
  r = await answer(h, s.token, "speech_speed_preference", "fast");
  assert.equal(r.status, 410);

  r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s.session_id, company_id: "other-co" } });
  assert.equal(r.status, 403);
  r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s.session_id, company_id: "acme" } });
  assert.equal(r.status, 201);
  assert.equal(r.body.session_id, s.session_id);
  assert.equal(r.body.resume_question_id, "speech_speed_preference");
  assert.equal(r.body.answered_count, 2);
  const nt = r.body.token;

  r = await h.handle("GET", `/api/sessions/${s.token}`);
  assert.equal(r.status, 410);
  assert.match(r.body.error, /renewed|revoked/i);

  r = await h.handle("GET", `/api/sessions/${nt}`);
  assert.equal(r.status, 200);
  assert.equal(r.body.progress.current_id, "speech_speed_preference");
  r = await answer(h, nt, "speech_speed_preference", "fast");
  assert.equal(r.status, 200);
  r = await answer(h, nt, "want_sales_checkout", "yes");
  assert.equal(r.status, 200);
  r = await h.handle("POST", `/api/sessions/${nt}/complete`, { body: {} });
  assert.equal(r.status, 200);
});

test("PRES-024 [interview-app D1]: two deck sessions renew independently; no answer bleed", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s1 = await mint(h, "run-ia-1");
  const s2 = await mint(h, "run-ia-2");
  await answer(h, s1.token, "offer_name", "Deck One");
  await answer(h, s2.token, "offer_name", "Deck Two");
  env.DB.db.prepare("UPDATE sessions SET expires_at = ? WHERE token = ?").run(Math.floor(Date.now() / 1000) - 10, s1.token);
  const r1 = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s1.session_id, company_id: "acme" } });
  assert.equal(r1.status, 201);
  const v1 = await h.handle("GET", `/api/sessions/${r1.body.token}/review`);
  const v2 = await h.handle("GET", `/api/sessions/${s2.token}/review`);
  assert.equal(v1.body.answers.offer_name, "Deck One");
  assert.equal(v2.body.answers.offer_name, "Deck Two");
  assert.notEqual(r1.body.session_id, s2.session_id);
});

test("PRES-024 [interview-app D1]: correction after completion invalidates downstream and never mixes revisions", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-ia-correct");
  for (const [q, v] of [["offer_name", "Wrong"], ["tone", "bold"], ["speech_speed_preference", "fast"], ["want_sales_checkout", "yes"]]) {
    await answer(h, s.token, q, v);
  }
  let r = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(r.status, 200);
  r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "offer_name", value: "Right" } });
  assert.equal(r.status, 200);
  assert.equal(r.body.requires_rebuild, true);
  assert.equal(r.body.revision, 1);
  r = await h.handle("GET", `/api/sessions/${s.token}/review`);
  assert.equal(r.body.answers.offer_name, "Right");
  assert.ok(r.body.invalidated_at > 0);
  const rows = env.DB.db.prepare("SELECT * FROM corrections WHERE session_id = ?").all(s.session_id);
  assert.equal(rows.length, 1);
  assert.equal(Number(rows[0].revision_before), 0);
  assert.equal(Number(rows[0].revision_after), 1);
});

test("PRES-024 [interview-app D1]: retry-link delivery bound-recipient fail-closed; admin scope enforced", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-ia-deliver");
  let r = await h.handle("POST", "/api/admin/retry-link", { token: "admin-tok", body: { session_id: s.session_id, recipient_chat_id: "111" } });
  assert.equal(r.status, 201);
  r = await h.handle("POST", "/api/admin/retry-link", { token: "admin-tok", body: { session_id: s.session_id, recipient_chat_id: "999" } });
  assert.equal(r.status, 422);
  r = await h.handle("POST", "/api/admin/retry-link", { body: { session_id: s.session_id, recipient_chat_id: "111" } });
  assert.equal(r.status, 401);
  r = await h.handle("POST", "/api/sessions/renew", { body: { session_id: s.session_id } });
  assert.equal(r.status, 401);
  const rows = env.DB.db.prepare("SELECT * FROM retry_deliveries WHERE session_id = ?").all(s.session_id);
  assert.equal(rows.length, 1);
});

test("PRES-024 [interview-app D1]: legacy contract intact — reuse, completeness gate, intake fetch", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-ia-legacy");
  const again = await h.handle("POST", "/api/sessions", { token: "admin-tok", body: { run_id: "run-ia-legacy", box_id: "box1", questions_payload: PAYLOAD } });
  assert.equal(again.body.status, "exists");
  assert.equal(again.body.token, s.token);
  // F21 completeness gate still fires.
  const r = await h.handle("POST", "/api/intake", {
    token: "admin-tok",
    body: { file_name: "intake.json", intake: { intake_session_id: "ia-x", deck_brief: {} } },
  });
  assert.equal(r.status, 422);
  assert.ok(r.body.missing.includes("deck_brief.OFFER_NAME"));
});