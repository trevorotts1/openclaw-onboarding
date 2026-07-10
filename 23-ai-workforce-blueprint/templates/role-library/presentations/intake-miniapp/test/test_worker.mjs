// Offline unit gate for the Worker's pure logic. No Cloudflare runtime, no
// network — just `node --test test/test_worker.mjs`. The load-bearing property
// under test is the one-question-at-a-time guarantee: the API rejects any
// out-of-order answer, which is what makes batching physically impossible.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  randomToken,
  sixDigitCode,
  isValidTokenShape,
  validateQuestionsPayload,
  orderedQuestions,
  nextQuestionIndex,
  checkAnswerOrder,
  validateAnswerValue,
  answersSince,
  progress,
  expiryFrom,
} from "../worker/src/lib.js";

const PAYLOAD = {
  question_set: "standard",
  questions: [
    { id: "deck_type", order: 0, prompt: "Which deck?", kind: "enum", required: true,
      allowed_values: ["webinar", "signature_presentation"] },
    { id: "grounded", order: 1, prompt: "Your content?", kind: "text", required: true },
    { id: "dark_ok", order: 2, prompt: "Dark slides?", kind: "boolean", required: true },
    { id: "wpm", order: 3, prompt: "Pace?", kind: "integer", required: false, default: 140 },
  ],
};

test("randomToken is 32 lowercase-hex chars and unique", () => {
  const a = randomToken();
  const b = randomToken();
  assert.match(a, /^[0-9a-f]{32}$/);
  assert.ok(isValidTokenShape(a));
  assert.notEqual(a, b);
});

test("sixDigitCode is exactly 6 digits", () => {
  assert.match(sixDigitCode(), /^\d{6}$/);
});

test("isValidTokenShape rejects malformed tokens", () => {
  assert.ok(!isValidTokenShape("nope"));
  assert.ok(!isValidTokenShape("ABCDEF0123456789ABCDEF0123456789")); // uppercase
  assert.ok(!isValidTokenShape("0123456789abcdef")); // too short
});

test("validateQuestionsPayload accepts good, rejects bad", () => {
  assert.ok(validateQuestionsPayload(PAYLOAD).ok);
  assert.ok(!validateQuestionsPayload({ question_set: "x", questions: [] }).ok);
  assert.ok(!validateQuestionsPayload({ question_set: "standard", questions: [] }).ok);
  assert.ok(!validateQuestionsPayload({ question_set: "standard",
    questions: [{ id: "a", prompt: "?" }, { id: "a", prompt: "?" }] }).ok); // dup id
});

test("orderedQuestions sorts by order", () => {
  const shuffled = { questions: [{ id: "b", order: 2, prompt: "?" }, { id: "a", order: 1, prompt: "?" }] };
  assert.deepEqual(orderedQuestions(shuffled).map((q) => q.id), ["a", "b"]);
});

test("nextQuestionIndex walks in canonical order", () => {
  assert.equal(nextQuestionIndex(PAYLOAD, []), 0);
  assert.equal(nextQuestionIndex(PAYLOAD, ["deck_type"]), 1);
  assert.equal(nextQuestionIndex(PAYLOAD, ["deck_type", "grounded", "dark_ok", "wpm"]), -1);
});

test("checkAnswerOrder ENFORCES one-at-a-time (rejects skipping ahead)", () => {
  // Current expected is deck_type; answering 'grounded' first is the batching move.
  const bad = checkAnswerOrder(PAYLOAD, [], "grounded");
  assert.ok(!bad.ok);
  assert.match(bad.error, /out-of-order/);
  assert.equal(bad.question.id, "deck_type");
  // Answering the current one is fine.
  assert.ok(checkAnswerOrder(PAYLOAD, [], "deck_type").ok);
  // Unknown id rejected.
  assert.ok(!checkAnswerOrder(PAYLOAD, [], "ghost").ok);
});

test("validateAnswerValue coerces by kind", () => {
  const enumQ = PAYLOAD.questions[0];
  assert.deepEqual(validateAnswerValue(enumQ, "Webinar"), { ok: true, value: "webinar" });
  assert.ok(!validateAnswerValue(enumQ, "podcast").ok);

  const boolQ = PAYLOAD.questions[2];
  assert.equal(validateAnswerValue(boolQ, "Yes").value, "true");
  assert.equal(validateAnswerValue(boolQ, "no").value, "false");
  assert.ok(!validateAnswerValue(boolQ, "maybe").ok);

  const intQ = PAYLOAD.questions[3];
  assert.equal(validateAnswerValue(intQ, "150").value, "150");
  assert.ok(!validateAnswerValue(intQ, "fast").ok);
  assert.ok(validateAnswerValue(intQ, "").ok); // optional, empty allowed

  const textReq = PAYLOAD.questions[1];
  assert.ok(!validateAnswerValue(textReq, "   ").ok); // required, blank rejected
  assert.ok(validateAnswerValue(textReq, "The Momentum Method").ok);
});

test("answersSince filters by monotonic cursor", () => {
  const rows = [{ id: 1 }, { id: 2 }, { id: 3 }];
  assert.deepEqual(answersSince(rows, 1).map((r) => r.id), [2, 3]);
  assert.deepEqual(answersSince(rows, 0).map((r) => r.id), [1, 2, 3]);
  assert.deepEqual(answersSince(rows, 3), []);
});

test("progress reports k of N and completion", () => {
  const p0 = progress(PAYLOAD, []);
  assert.equal(p0.total, 4);
  assert.equal(p0.answered, 0);
  assert.equal(p0.current_id, "deck_type");
  assert.equal(p0.complete, false);

  const pDone = progress(PAYLOAD, ["deck_type", "grounded", "dark_ok", "wpm"]);
  assert.equal(pDone.complete, true);
  assert.equal(pDone.current_id, null);
});

test("expiryFrom adds the TTL window in seconds", () => {
  assert.equal(expiryFrom(1000, 7), 1000 + 7 * 86400);
});
