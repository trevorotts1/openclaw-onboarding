// PD-106 gate — a session minted with a confirmation code guards its stored
// answers: GET /answers, GET /review and POST /corrections answer 401 unless
// the caller presents the code in `x-confirm-code`. A code-less session keeps
// exactly the behaviour it had (nothing changes for every existing link).
//
//   node --test deployed-r2/test/test_pd106_confirm_code.mjs
//
// Rows:
//   A1a  code session: answers/review/corrections without the header -> 401,
//        with the right header -> 200; wrong header -> 401
//   A1b  control: no code minted -> the same reads succeed with no header
import { test } from "node:test";
import assert from "node:assert/strict";
import { R2Shim, PAYLOAD } from "../../test/pres024_env.mjs";
import worker from "../src/index.js";

function makeEnv() {
  return { STORE: new R2Shim(), INTAKE_ADMIN_TOKEN: "admin-tok" };
}

/** Request driver; pres024_env's harness carries no arbitrary-header path. */
async function call(h, method, path, { token = null, body = null, headers = {} } = {}) {
  const hdrs = { ...headers };
  if (token) hdrs.authorization = "Bearer " + token;
  const req = new Request("https://pd106.test" + path, {
    method,
    headers: hdrs,
    body: body === null ? undefined : JSON.stringify(body),
  });
  const res = await h.fetch(req);
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch { json = { raw: text }; }
  return { status: res.status, body: json };
}

async function mint(h, runId, extra = {}) {
  const r = await call(h, "POST", "/api/sessions", {
    token: "admin-tok",
    body: { run_id: runId, box_id: "box1", questions_payload: PAYLOAD, company_id: "acme", installation_id: "install-test", presentation_id: "presentation-test", ...extra },
  });
  assert.equal(r.status, 201, "mint: " + JSON.stringify(r.body));
  return r.body;
}

test("PD-106 A1a: a coded session 401s every stored-answer read without x-confirm-code", async () => {
  const env = makeEnv();
  const h = { fetch: (req) => worker.fetch(req, env, {}) };
  const s = await mint(h, "run-pd106-a1a", { want_confirm_code: true });
  assert.match(String(s.confirm_code), /^[0-9]{6}$/, "mint returns a 6-digit code");

  // Answer once (POST /answers already accepts the code in the body).
  let r = await call(h, "POST", `/api/sessions/${s.token}/answers`, { body: { question_id: "offer_name", value: "The Momentum Method", confirm_code: s.confirm_code } });
  assert.equal(r.status, 200, "answer with code in body: " + JSON.stringify(r.body));

  // GET /answers
  r = await call(h, "GET", `/api/sessions/${s.token}/answers?since=0`);
  assert.equal(r.status, 401, "answers read without the code must be refused");
  r = await call(h, "GET", `/api/sessions/${s.token}/answers?since=0`, { headers: { "x-confirm-code": "000000" } });
  assert.equal(r.status, 401, "wrong code refused");
  r = await call(h, "GET", `/api/sessions/${s.token}/answers?since=0`, { headers: { "x-confirm-code": s.confirm_code } });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.answers.length, 1);

  // GET /review
  r = await call(h, "GET", `/api/sessions/${s.token}/review`);
  assert.equal(r.status, 401, "review without the code must be refused");
  r = await call(h, "GET", `/api/sessions/${s.token}/review`, { headers: { "x-confirm-code": s.confirm_code } });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.answers.offer_name, "The Momentum Method");

  // POST /corrections
  r = await call(h, "POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "offer_name", value: "Right" } });
  assert.equal(r.status, 401, "correction without the code must be refused");
  r = await call(h, "POST", `/api/sessions/${s.token}/corrections`, { headers: { "x-confirm-code": s.confirm_code }, body: { question_id: "offer_name", value: "Right" } });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.new_value, "Right");
});

test("PD-106 A1b: a code-less session is unchanged — reads need no header", async () => {
  const env = makeEnv();
  const h = { fetch: (req) => worker.fetch(req, env, {}) };
  const s = await mint(h, "run-pd106-a1b");
  assert.equal(s.confirm_code, null, "no code unless asked for");

  await call(h, "POST", `/api/sessions/${s.token}/answers`, { body: { question_id: "offer_name", value: "Plain Offer" } });
  for (const path of [`/api/sessions/${s.token}/answers?since=0`, `/api/sessions/${s.token}/review`]) {
    const r = await call(h, "GET", path);
    assert.equal(r.status, 200, path + " must stay open: " + JSON.stringify(r.body));
  }
  const c = await call(h, "POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "offer_name", value: "Fixed" } });
  assert.equal(c.status, 200, JSON.stringify(c.body));
});
