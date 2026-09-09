// PRES-024 offline integration gate — the QC-PRES-024 battery against the
// canonical intake-miniapp D1 worker, on a REAL SQLite engine (node:sqlite)
// executing the REAL schema (worker/schema.sql). No Cloudflare runtime, no
// network.
//
//   node --test test/pres024_miniapp.test.mjs
//
// Covers every QC-PRES-024 check:
//   1. Expire link mid-interview then renew: prior answers intact, correct
//      current question, old token rejected, wrong-company renew rejected.
//   2. Same client two deck sessions renew independently.
//   3. Correction invalidates downstream outputs requiring rebuild but does
//      not mix revisions.
//   4. Retry-link delivery recorded to the bound recipient; other recipients
//      refused.
//   5. Expired token cannot read/write answers; expiry does not erase data.
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { D1Shim, makeDb, WorkerHarness, PAYLOAD } from "./pres024_env.mjs";
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

test("QC-PRES-024.1: expire mid-interview, renew — answers intact, correct resume question, old token rejected, wrong company rejected", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-expire");

  // Two answers in.
  let r = await answer(h, s.token, "offer_name", "The Momentum Method");
  assert.equal(r.status, 200);
  r = await answer(h, s.token, "tone", "bold");
  assert.equal(r.status, 200);
  assert.equal(r.body.progress.current_id, "speech_speed_preference");

  // Simulate wall-clock expiry of the grant (no data deletion — only the
  // token's expires_at moves into the past; this is exactly what time does).
  env.DB.db.prepare("UPDATE sessions SET expires_at = 1 WHERE token = ?").run(s.token);

  // Expired token can no longer read or write.
  r = await h.handle("GET", `/api/sessions/${s.token}`);
  assert.equal(r.status, 410);
  r = await answer(h, s.token, "speech_speed_preference", "fast");
  assert.equal(r.status, 410);

  // Renew with the WRONG company -> refused.
  r = await h.handle("POST", "/api/sessions/renew", {
    token: "admin-tok", body: { session_id: s.session_id, company_id: "other-co" },
  });
  assert.equal(r.status, 403, "wrong-company renew must be 403: " + JSON.stringify(r));

  // Renew with the right company -> new token, same identity.
  r = await h.handle("POST", "/api/sessions/renew", {
    token: "admin-tok", body: { session_id: s.session_id, company_id: "acme" },
  });
  assert.equal(r.status, 201, "renew must succeed: " + JSON.stringify(r));
  assert.equal(r.body.session_id, s.session_id, "renewal binds the SAME session identity");
  assert.equal(r.body.resume_question_id, "speech_speed_preference", "resumes the exact first unmet question");
  assert.equal(r.body.answered_count, 2, "both prior answers preserved");
  assert.equal(r.body.revision, 1, "renewal bumps revision to 1");
  const nt = r.body.token;
  assert.notEqual(nt, s.token);

  // Old token now rejected (revoked), never treated as unknown.
  r = await h.handle("GET", `/api/sessions/${s.token}`);
  assert.equal(r.status, 410);
  assert.match(r.body.error, /renewed|revoked/i);

  // New link continues the interview with every prior answer intact.
  r = await h.handle("GET", `/api/sessions/${nt}`);
  assert.equal(r.status, 200);
  assert.equal(r.body.answered.length, 2);
  assert.ok(r.body.answered.includes("offer_name"));
  assert.ok(r.body.answered.includes("tone"));
  assert.equal(r.body.progress.current_id, "speech_speed_preference", "correct current question after renewal");
  r = await answer(h, nt, "speech_speed_preference", "fast");
  assert.equal(r.status, 200, "answering continues after renewal");
  r = await answer(h, nt, "want_sales_checkout", "yes");
  assert.equal(r.status, 200);
  r = await h.handle("POST", `/api/sessions/${nt}/complete`, { body: {} });
  assert.equal(r.status, 200, "completable with the renewed grant");
});

test("QC-PRES-024.1b: renew by run_id works and never resets answers", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-by-runid");
  await answer(h, s.token, "offer_name", "Offer A");
  env.DB.db.prepare("UPDATE sessions SET expires_at = ? WHERE token = ?").run(Math.floor(Date.now() / 1000) - 10, s.token);
  const r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { run_id: "run-by-runid", company_id: "acme" } });
  assert.equal(r.status, 201);
  assert.equal(r.body.session_id, s.session_id);
  assert.equal(r.body.answered_count, 1);
  assert.equal(r.body.resume_question_id, "tone");
});

test("QC-PRES-024.2: same client two deck sessions renew independently (no cross-talk)", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s1 = await mint(h, "run-deck-1");
  const s2 = await mint(h, "run-deck-2");
  assert.notEqual(s1.session_id, s2.session_id, "two sessions, two identities");

  await answer(h, s1.token, "offer_name", "Deck One Offer");
  await answer(h, s2.token, "offer_name", "Deck Two Offer");

  // Expire only deck 1's grant.
  env.DB.db.prepare("UPDATE sessions SET expires_at = ? WHERE token = ?").run(Math.floor(Date.now() / 1000) - 10, s1.token);

  const r1 = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s1.session_id, company_id: "acme" } });
  assert.equal(r1.status, 201);
  const r2 = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s2.session_id, company_id: "acme" } });
  assert.equal(r2.status, 201, "deck 2 renews independently of deck 1");

  // Independent identities, independent answers, independent revisions.
  assert.notEqual(r1.body.session_id, r2.body.session_id);
  const g1 = await h.handle("GET", `/api/sessions/${r1.body.token}`);
  const g2 = await h.handle("GET", `/api/sessions/${r2.body.token}`);
  assert.equal(g1.body.answered.length, 1);
  assert.equal(g2.body.answered.length, 1);
  const v1 = await h.handle("GET", `/api/sessions/${r1.body.token}/review`);
  const v2 = await h.handle("GET", `/api/sessions/${r2.body.token}/review`);
  assert.equal(v1.body.answers.offer_name, "Deck One Offer");
  assert.equal(v2.body.answers.offer_name, "Deck Two Offer", "no revision mixing across the client's two sessions");
  assert.equal(r1.body.revision, 1);
  assert.equal(r2.body.revision, 1, "each session's revision advances independently");
});

test("QC-PRES-024.2b: answers never bleed between two sessions of the same client", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s1 = await mint(h, "run-bleed-1");
  const s2 = await mint(h, "run-bleed-2");
  await answer(h, s1.token, "offer_name", "ONLY-SESSION-ONE");
  const v2 = await h.handle("GET", `/api/sessions/${s2.token}/review`);
  assert.ok(!("offer_name" in v2.body.answers), "session two must not see session one's answer");
});

test("QC-PRES-024.3: correction invalidates downstream (requires_rebuild) and never mixes revisions", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-correct");

  for (const [q, v] of [["offer_name", "Wrong Name"], ["tone", "bold"], ["speech_speed_preference", "fast"], ["want_sales_checkout", "yes"]]) {
    const r = await answer(h, s.token, q, v);
    assert.equal(r.status, 200, q);
  }
  let r = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(r.status, 200, "session completes");
  assert.equal(r.body.revision, 0);

  // Production "consumed" revision 0. Now the client corrects an answer.
  r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "offer_name", value: "The Corrected Offer" } });
  assert.equal(r.status, 200, JSON.stringify(r));
  assert.equal(r.body.old_value, "Wrong Name");
  assert.equal(r.body.new_value, "The Corrected Offer");
  assert.equal(r.body.revision, 1);
  assert.equal(r.body.revision_before, 0);
  assert.equal(r.body.requires_rebuild, true, "downstream outputs invalidated — rebuild required");
  assert.ok(r.body.invalidated_at > 0, "invalidation stamped");

  // The session is reopened at the corrected revision.
  r = await h.handle("GET", `/api/sessions/${s.token}/review`);
  assert.equal(r.body.answers.offer_name, "The Corrected Offer");
  assert.equal(r.body.revision, 1);
  assert.ok(r.body.invalidated_at > 0);
  assert.match(r.body.invalidated_reason, /rebuild/);
  assert.equal(r.body.answers.tone, "bold", "uncorrected answers untouched");
  assert.equal(r.body.answers.speech_speed_preference, "fast");
  assert.equal(r.body.answers.want_sales_checkout, "yes");

  // Second correction chains revision 1 -> 2 with clean before/after pairs.
  r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "tone", value: "warm" } });
  assert.equal(r.status, 200);
  assert.equal(r.body.revision_before, 1);
  assert.equal(r.body.revision, 2);
  r = await h.handle("GET", `/api/sessions/${s.token}/review`);
  assert.equal(r.body.answers.offer_name, "The Corrected Offer", "first correction survives the second — revisions never mix");
  assert.equal(r.body.answers.tone, "warm");

  // The corrections ledger recorded both, each with its own revision pair.
  const rows = env.DB.db.prepare("SELECT * FROM corrections WHERE session_id = ? ORDER BY id").all(s.session_id);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].question_id, "offer_name");
  assert.equal(Number(rows[0].revision_before), 0);
  assert.equal(Number(rows[0].revision_after), 1);
  assert.equal(rows[1].question_id, "tone");
  assert.equal(Number(rows[1].revision_before), 1);
  assert.equal(Number(rows[1].revision_after), 2);
});

test("QC-PRES-024.3b: correction before completion invalidates nothing (no rebuild needed)", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-correct-early");
  await answer(h, s.token, "offer_name", "Draft Name");
  const r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "offer_name", value: "Fixed early" } });
  assert.equal(r.status, 200);
  assert.equal(r.body.requires_rebuild, false, "nothing downstream consumed it yet");
  assert.equal(r.body.invalidated_at, null);
});

test("QC-PRES-024.3c: cannot correct an unanswered or unknown question; bad value rejected", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-correct-guard");
  await answer(h, s.token, "offer_name", "Offer");
  await answer(h, s.token, "tone", "bold");
  await answer(h, s.token, "speech_speed_preference", "fast");
  let r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "want_sales_checkout", value: "yes" } });
  assert.equal(r.status, 404, "unanswered question has nothing to correct");
  r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "ghost", value: "x" } });
  assert.equal(r.status, 404);
  r = await h.handle("POST", `/api/sessions/${s.token}/corrections`, { body: { question_id: "speech_speed_preference", value: "warp" } });
  assert.equal(r.status, 422, "correction value is validated like an answer");
});

test("QC-PRES-024.4: retry-link delivery recorded to the BOUND recipient; wrong recipient refused", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-deliver");

  // Right recipient recorded.
  let r = await h.handle("POST", "/api/admin/retry-link", {
    token: "admin-tok", body: { session_id: s.session_id, recipient_chat_id: "111", token: s.token },
  });
  assert.equal(r.status, 201, JSON.stringify(r));
  assert.equal(r.body.recipient_chat_id, "111");
  const rows = env.DB.db.prepare("SELECT * FROM retry_deliveries WHERE session_id = ?").all(s.session_id);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].recipient_chat_id, "111");

  // Wrong recipient refused — fail-closed, never recorded.
  r = await h.handle("POST", "/api/admin/retry-link", {
    token: "admin-tok", body: { session_id: s.session_id, recipient_chat_id: "999" },
  });
  assert.equal(r.status, 422);
  const rows2 = env.DB.db.prepare("SELECT * FROM retry_deliveries WHERE session_id = ?").all(s.session_id);
  assert.equal(rows2.length, 1, "the refused delivery was NOT recorded");

  // Renewal preserves the binding: delivery after renewal still bound to 111.
  env.DB.db.prepare("UPDATE sessions SET expires_at = ? WHERE token = ?").run(Math.floor(Date.now() / 1000) - 10, s.token);
  const nr = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s.session_id, company_id: "acme" } });
  assert.equal(nr.status, 201);
  r = await h.handle("POST", "/api/admin/retry-link", {
    token: "admin-tok", body: { session_id: s.session_id, recipient_chat_id: "111", token: nr.body.token },
  });
  assert.equal(r.status, 201);
});

test("QC-PRES-024.5: expired token cannot read/write answers; expiry never erases session data", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-expiry-data");
  await answer(h, s.token, "offer_name", "Durable Answer");
  env.DB.db.prepare("UPDATE sessions SET expires_at = ? WHERE token = ?").run(Math.floor(Date.now() / 1000) - 10, s.token);

  // Denied both ways.
  let r = await h.handle("GET", `/api/sessions/${s.token}`);
  assert.equal(r.status, 410);
  r = await h.handle("POST", `/api/sessions/${s.token}/answers`, { body: { question_id: "tone", value: "x" } });
  assert.equal(r.status, 410);
  r = await h.handle("GET", `/api/sessions/${s.token}/review`);
  assert.equal(r.status, 410, "expired grant cannot even review");

  // The data is still on the backend under the stable identity...
  const answers = env.DB.db.prepare("SELECT value FROM answers WHERE session_id = ?").all(s.session_id);
  assert.equal(answers.length, 1);
  assert.equal(answers[0].value, "Durable Answer");

  // ...and renewal hands it straight back.
  r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s.session_id, company_id: "acme" } });
  assert.equal(r.status, 201);
  assert.equal(r.body.answered_count, 1);
  const rv = await h.handle("GET", `/api/sessions/${r.body.token}/review`);
  assert.equal(rv.body.answers.offer_name, "Durable Answer", "expiry never erased the session's data");
});

test("QC-PRES-024.6: admin scope enforced — renew/retry-link need the box token", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  let r = await h.handle("POST", "/api/sessions/renew", { body: { run_id: "nope" } });
  assert.equal(r.status, 401);
  r = await h.handle("POST", "/api/admin/retry-link", { body: { run_id: "nope", recipient_chat_id: "1" } });
  assert.equal(r.status, 401);
  r = await h.handle("POST", "/api/sessions/renew", { token: "wrong", body: { run_id: "nope" } });
  assert.equal(r.status, 401);
});

test("QC-PRES-024.7: renewal of a complete session is refused (revisions never mix)", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-complete");
  for (const [q, v] of [["offer_name", "O"], ["tone", "t"], ["speech_speed_preference", "fast"], ["want_sales_checkout", "yes"]]) {
    await answer(h, s.token, q, v);
  }
  const done = await h.handle("POST", `/api/sessions/${s.token}/complete`, { body: {} });
  assert.equal(done.status, 200);
  const r = await h.handle("POST", "/api/sessions/renew", { token: "admin-tok", body: { session_id: s.session_id, company_id: "acme" } });
  assert.equal(r.status, 409, "a completed intake reopens only through the correction channel, never a renewal");
});

test("QC-PRES-024.8: legacy single-grant semantics preserved — pre-renewal flow unchanged (reuse, order gate, poll cursor)", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);
  const s = await mint(h, "run-legacy");
  // Mint again for the same live run -> reused, same token.
  const again = await h.handle("POST", "/api/sessions", {
    token: "admin-tok", body: { run_id: "run-legacy", box_id: "box1", questions_payload: PAYLOAD },
  });
  assert.equal(again.body.status, "exists");
  assert.equal(again.body.token, s.token);
  // Out-of-order still rejected.
  let r = await answer(h, s.token, "tone", "bold");
  assert.equal(r.status, 409);
  // Poll cursor semantics preserved.
  await answer(h, s.token, "offer_name", "O");
  r = await h.handle("GET", `/api/sessions/${s.token}/answers?since=0`);
  assert.equal(r.status, 200);
  assert.equal(r.body.answers.length, 1);
  assert.equal(r.body.cursor, 1);
});