// PD-082a — the web interview asks how long, who for, and what the source is.
// Rows A1-A3 against the real deployed-r2 worker on the in-memory R2 shim:
//   A1 completing a session without a duration returns 409 naming duration_min
//   A2 a completed record carries the client's number (as a number)
//   A3 a content_personal session cannot complete without recipient_name
//   node --test deployed-r2/test/test_pd082a_web_interview.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { R2Shim, WorkerHarness } from "../../test/pres024_env.mjs";
import worker from "../src/index.js";

const PTYPE = {
  id: "presentation_type", order: 0, kind: "enum", required: true,
  prompt: "What kind of presentation do you need?",
  storeOn: "pre_presentation_capture.PRESENTATION_TYPE",
  allowed_values: ["from_scratch", "content_personal", "content_general", "signature"],
};
const OFFER = { id: "offer_name", order: 9, kind: "text", required: true, block_gate: true, storeOn: "deck_brief.OFFER_NAME", prompt: "What is the exact name of the offer?" };
const DURATION = {
  id: "duration_min", order: 0.25, kind: "integer", required: true, block_gate: true,
  prompt: "How many minutes should the talk run?", storeOn: "deck_brief.DURATION_MIN",
};
const RECIPIENT = {
  id: "recipient_name", order: 0.3, kind: "text", required: true, block_gate: true,
  prompt: "What is the name of the person receiving this presentation?",
  storeOn: "pre_presentation_capture.RECIPIENT_NAME",
  conditional_on: { id: "presentation_type", equals: "content_personal" },
};

function payload(questions) {
  return { question_set: "standard", questions };
}

async function mint(h, runId, questions) {
  const res = await h.handle("POST", "/api/sessions", {
    token: "admin-tok",
    body: {
      run_id: runId, box_id: "box1", questions_payload: payload(questions),
      company_id: "acme", installation_id: "install-test", presentation_id: "presentation-test",
      recipient_chat_id: "111",
    },
  });
  assert.equal(res.status, 201, "mint: " + JSON.stringify(res.body));
  return res.body;
}

async function answer(h, token, questionId, value) {
  return h.handle("POST", `/api/sessions/${token}/answers`, { body: { question_id: questionId, value } });
}

function makeEnv() {
  return { STORE: new R2Shim(), INTAKE_ADMIN_TOKEN: "admin-tok" };
}

test("PD-082a A1: completing without a duration is 409 and names duration_min", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  // duration_min sits last so the earlier required answers can be given
  // first (the server serves one question at a time, in order).
  const s = await mint(h, "run-pd082a-a1", [
    { ...PTYPE },
    { ...OFFER, order: 1 },
    { ...DURATION, order: 2 },
  ]);
  assert.equal((await answer(h, s.token, "presentation_type", "from_scratch")).status, 200);
  assert.equal((await answer(h, s.token, "offer_name", "The Momentum Method")).status, 200);

  const done = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(done.status, 409, "completion must be refused: " + JSON.stringify(done.body));
  assert.equal(done.body.status, "blocked");
  assert.ok(done.body.missing.includes("duration_min"), "missing names duration_min: " + JSON.stringify(done.body.missing));
});

test("PD-082a A2: the completed record carries the client's number as a number", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-pd082a-a2", [{ ...PTYPE }, { ...DURATION }, { ...OFFER }]);
  assert.equal((await answer(h, s.token, "presentation_type", "from_scratch")).status, 200);
  assert.equal((await answer(h, s.token, "duration_min", "45")).status, 200);
  assert.equal((await answer(h, s.token, "offer_name", "The Momentum Method")).status, 200);

  const done = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(done.status, 200, "complete: " + JSON.stringify(done.body));

  const outbox = JSON.parse(env.STORE.map.get(`outboxes/${s.token}.json`));
  assert.equal(outbox.status, "queued", JSON.stringify(outbox));
  assert.equal(outbox.intake.target_talk_minutes, 45, "client's number at the record root");
  assert.equal(typeof outbox.intake.target_talk_minutes, "number", "stored as a number, not a string");
  assert.equal(outbox.intake.deck_brief.DURATION_MIN, "45", "the answer also rides its canonical field");
  assert.equal(outbox.intake.recipient_name, "", "no recipient for a from-scratch deck");
});

test("PD-082a A3: content_personal cannot complete without recipient_name", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-pd082a-a3", [
    { ...PTYPE },
    { ...DURATION, order: 1 },
    { ...RECIPIENT, order: 2 },
    { ...OFFER, order: 3 },
  ]);
  assert.equal((await answer(h, s.token, "presentation_type", "content_personal")).status, 200);
  assert.equal((await answer(h, s.token, "duration_min", "30")).status, 200);

  const done = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(done.status, 409, "completion must be refused: " + JSON.stringify(done.body));
  assert.ok(done.body.missing.includes("recipient_name"), "missing names recipient_name: " + JSON.stringify(done.body.missing));

  // ... and the same session completes once the name is given.
  assert.equal((await answer(h, s.token, "recipient_name", "Marcus Halloway")).status, 200);
  assert.equal((await answer(h, s.token, "offer_name", "The Momentum Method")).status, 200);
  const ok = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(ok.status, 200, "complete after the name: " + JSON.stringify(ok.body));
  const outbox = JSON.parse(env.STORE.map.get(`outboxes/${s.token}.json`));
  assert.equal(outbox.intake.recipient_name, "Marcus Halloway", "recipient at the record root");
  assert.equal(outbox.intake.pre_presentation_capture.RECIPIENT_NAME, "Marcus Halloway");
});

test("PD-082a: the source question is asked only for the two content types", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const SOURCE = {
    id: "extracted_substance", order: 1.5, kind: "text", required: true, block_gate: true,
    prompt: "What is the one core idea your existing material must convey?",
    storeOn: "pre_presentation_capture.EXTRACTED_SUBSTANCE",
    conditional_on: { id: "presentation_type", in: ["content_personal", "content_general"] },
  };
  const s = await mint(h, "run-pd082a-src", [
    { ...PTYPE }, { ...DURATION, order: 1 }, { ...SOURCE }, { ...OFFER, order: 2 },
  ]);
  assert.equal((await answer(h, s.token, "presentation_type", "from_scratch")).status, 200);
  assert.equal((await answer(h, s.token, "duration_min", "20")).status, 200);
  // from_scratch: the source question is INACTIVE, so offer_name is next.
  assert.equal((await answer(h, s.token, "offer_name", "The Momentum Method")).status, 200);
  const done = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(done.status, 200, "from_scratch completes without the source answer: " + JSON.stringify(done.body));
});
