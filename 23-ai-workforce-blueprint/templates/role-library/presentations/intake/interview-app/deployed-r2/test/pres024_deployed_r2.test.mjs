// PRES-024 offline integration gate — the QC-PRES-024 battery against the
// deployed-r2 worker (the R2-backed build that matches production), on an
// in-memory R2 shim. Same contract as the D1 batteries.
//   node --test deployed-r2/test/pres024_deployed_r2.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { R2Shim, WorkerHarness, PAYLOAD } from "../../../../intake-miniapp/test/pres024_env.mjs";
import worker from "../src/index.js";

function makeEnv() {
  return { STORE: new R2Shim(), INTAKE_ADMIN_TOKEN: "admin-tok" };
}

async function mint(h, runId, extra = {}) {
  const res = await h.handle("POST", "/api/sessions", {
    token: "admin-tok",
    body: { run_id: runId, box_id: "box1", questions_payload: PAYLOAD, company_id: "acme", installation_id: "install-test", presentation_id: "presentation-test", recipient_chat_id: "111", ...extra },
  });
  assert.equal(res.status, 201, "mint should create: " + JSON.stringify(res));
  return res.body;
}

async function answer(h, token, questionId, value) {
  return h.handle("POST", `/api/sessions/${token}/answers`, { body: { question_id: questionId, value } });
}

test("PRES-024 [deployed-r2]: expire mid-interview, renew — answers intact, correct resume question, old token rejected, wrong company rejected", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-r2-expire");

  let r = await answer(h, s.token, "offer_name", "The Momentum Method");
  assert.equal(r.status, 200);
  r = await answer(h, s.token, "tone", "bold");
  assert.equal(r.status, 200);

  // Age the grant past its expiry (no data touched).
  const envStore = env.STORE;
  const sess = JSON.parse(envStore.map.get(`sessions/${s.token}.json`));
  sess.expires_at = 1;
  envStore.map.set(`sessions/${s.token}.json`, JSON.stringify(sess));

  r = await h.handle("GET", `/api/sessions/${s.token}`);
  assert.equal(r.status, 410);
  r = await answer(h, s.token, "speech_speed_preference", "fast");
  assert.equal(r.status, 410);

  r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s.session_id, company_id: "other-co" } });
  assert.equal(r.status, 403, "wrong-company renew rejected");
  r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s.session_id, company_id: "acme" } });
  assert.equal(r.status, 201, JSON.stringify(r));
  assert.equal(r.body.session_id, s.session_id, "same stable identity");
  assert.equal(r.body.resume_question_id, "speech_speed_preference");
  assert.equal(r.body.answered_count, 2, "prior answers intact");
  const nt = r.body.token;
  assert.notEqual(nt, s.token);

  // Old token rejected (revoked), never unknown.
  r = await h.handle("GET", `/api/sessions/${s.token}`);
  assert.equal(r.status, 410);
  assert.match(r.body.error, /renewed|revoked/i);

  r = await h.handle("GET", `/api/sessions/${nt}`);
  assert.equal(r.status, 200);
  assert.equal(r.body.answered.length, 2);
  assert.equal(r.body.progress.current_id, "speech_speed_preference");
  r = await answer(h, nt, "speech_speed_preference", "fast");
  assert.equal(r.status, 200);
  r = await answer(h, nt, "want_sales_checkout", "yes");
  assert.equal(r.status, 200);
  r = await h.handle("POST", `/api/sessions/${nt}/complete`, { body: {} });
  assert.equal(r.status, 200);
});

test("PRES-024 [deployed-r2]: two deck sessions renew independently; answers never bleed", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s1 = await mint(h, "run-r2-1");
  const s2 = await mint(h, "run-r2-2");
  assert.notEqual(s1.session_id, s2.session_id);
  await answer(h, s1.token, "offer_name", "Deck One Offer");
  await answer(h, s2.token, "offer_name", "Deck Two Offer");

  const envStore = env.STORE;
  const sess = JSON.parse(envStore.map.get(`sessions/${s1.token}.json`));
  sess.expires_at = 1;
  envStore.map.set(`sessions/${s1.token}.json`, JSON.stringify(sess));

  const r1 = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s1.session_id, company_id: "acme" } });
  assert.equal(r1.status, 201);
  const r2 = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s2.session_id, company_id: "acme" } });
  assert.equal(r2.status, 201, "independent renewal");

  const v1 = await h.handle("GET", `/api/sessions/${r1.body.token}/review`);
  const v2 = await h.handle("GET", `/api/sessions/${r2.body.token}/review`);
  assert.equal(v1.body.answers.offer_name, "Deck One Offer");
  assert.equal(v2.body.answers.offer_name, "Deck Two Offer", "no revision mixing");
  assert.equal(v1.body.revision, r1.body.revision);
  assert.equal(v2.body.revision, r2.body.revision);
});

test("PRES-024 [deployed-r2]: correction after completion invalidates downstream and never mixes revisions", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-r2-correct");
  for (const [q, v] of [["offer_name", "Wrong"], ["tone", "bold"], ["speech_speed_preference", "fast"], ["want_sales_checkout", "yes"]]) {
    await answer(h, s.token, q, v);
  }
  let r = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(r.status, 200);
  const completedRevision = r.body.revision;
  r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "offer_name", value: "Right" } });
  assert.equal(r.status, 200);
  assert.equal(r.body.requires_rebuild, true);
  assert.equal(r.body.revision_before, completedRevision);
  assert.equal(r.body.revision, completedRevision + 1);
  r = await h.handle("GET", `/api/sessions/${s.token}/review`);
  assert.equal(r.body.answers.offer_name, "Right");
  assert.equal(r.body.answers.tone, "bold", "uncorrected answers untouched");
  assert.ok(r.body.invalidated_at > 0);
  // Second correction chains 1 -> 2 cleanly.
  r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "tone", value: "warm" } });
  assert.equal(r.body.revision_before, completedRevision + 1);
  assert.equal(r.body.revision, completedRevision + 2);
  r = await h.handle("GET", `/api/sessions/${s.token}/review`);
  assert.equal(r.body.answers.offer_name, "Right", "revisions never mix");
  assert.equal(r.body.answers.tone, "warm");
});

test("PRES-024 [deployed-r2]: retry-link delivery bound-recipient fail-closed; admin scope enforced", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-r2-deliver");
  let r = await h.handle("POST", "/api/admin/retry-link", { token: "admin-tok", body: { session_id: s.session_id, recipient_chat_id: "111" } });
  assert.equal(r.status, 201);
  r = await h.handle("POST", "/api/admin/retry-link", { token: "admin-tok", body: { session_id: s.session_id, recipient_chat_id: "999" } });
  assert.equal(r.status, 422);
  r = await h.handle("POST", "/api/admin/retry-link", { body: { session_id: s.session_id, recipient_chat_id: "111" } });
  assert.equal(r.status, 401);
  r = await h.handle("POST", "/api/sessions/renew", { body: { session_id: s.session_id } });
  assert.equal(r.status, 401);
  const recs = [...env.STORE.map.keys()].filter((k) => k.startsWith("retry_deliveries/"));
  assert.equal(recs.length, 1, "only the bound-recipient delivery recorded");
});

test("PRES-024 [deployed-r2]: expiry never erases session data — renewal hands it straight back", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-r2-durable");
  await answer(h, s.token, "offer_name", "Durable Answer");
  const envStore = env.STORE;
  const sess = JSON.parse(envStore.map.get(`sessions/${s.token}.json`));
  sess.expires_at = 1;
  envStore.map.set(`sessions/${s.token}.json`, JSON.stringify(sess));

  let r = await h.handle("GET", `/api/sessions/${s.token}/review`);
  assert.equal(r.status, 410);
  r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s.session_id, company_id: "acme" } });
  assert.equal(r.status, 201);
  assert.equal(r.body.answered_count, 1);
  r = await h.handle("GET", `/api/sessions/${r.body.token}/review`);
  assert.equal(r.body.answers.offer_name, "Durable Answer");
});

test("PRES-024 [deployed-r2]: legacy contract intact — reuse, ordered answers, intake list", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-r2-legacy");
  const again = await h.handle("POST", "/api/sessions", { token: "admin-tok", body: { company_id: "acme", installation_id: "install-test", presentation_id: "presentation-test", run_id: "run-r2-legacy", box_id: "box1", questions_payload: PAYLOAD } });
  assert.equal(again.body.status, "exists");
  assert.equal(again.body.token, s.token);
  let r = await answer(h, s.token, "tone", "bold");
  assert.equal(r.status, 409, "one-question-at-a-time preserved");
  await answer(h, s.token, "offer_name", "O");
  r = await h.handle("GET", `/api/sessions/${s.token}/answers?since=0`);
  assert.equal(r.body.answers.length, 1);
  const intakes = await h.handle("GET", "/api/intake/list", { token: "admin-tok" });
  assert.equal(intakes.status, 200);
});

test("renew by server-minted run id preserves answers", async () => {
  const env = makeEnv(); const h = new WorkerHarness(worker, env);
  const s = await mint(h, "renew-by-run");
  await answer(h, s.token, "offer_name", "Offer");
  const r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { run_id: s.run_id, company_id: "acme" } });
  assert.equal(r.status, 201, JSON.stringify(r));
  assert.equal(r.body.session_id, s.session_id);
  assert.equal(r.body.answered_count, 1);
});
