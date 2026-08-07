// Offline unit gate for the Worker's pure logic (one-question-at-a-time +
// intake assembly). No Cloudflare runtime, no network.
//   node --test test/test_worker.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  randomToken,
  isValidTokenShape,
  validateQuestionsPayload,
  orderedQuestions,
  nextQuestionIndex,
  checkAnswerOrder,
  validateAnswerValue,
  progress,
  expiryFrom,
} from "../worker/src/lib.js";

const PAYLOAD = {
  question_set: "standard",
  questions: [
    { id: "offer_name", order: 1, prompt: "Your offer?", kind: "text", required: true, storeOn: "deck_brief.OFFER_NAME" },
    { id: "tone", order: 7, prompt: "Tone?", kind: "text", required: true },
    { id: "speech_speed_preference", order: 9, prompt: "Pace?", kind: "enum", required: true, allowed_values: ["default", "medium", "fast"] },
    { id: "want_sales_checkout", order: 10, prompt: "Sales page?", kind: "enum", required: true, allowed_values: ["yes", "no"] },
    { id: "client_notes", order: 12, prompt: "Notes?", kind: "text", required: false, default: "" },
  ],
};

test("randomToken is 32 lowercase-hex chars and unique", () => {
  const a = randomToken();
  const b = randomToken();
  assert.match(a, /^[0-9a-f]{32}$/);
  assert.ok(isValidTokenShape(a));
  assert.notEqual(a, b);
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

test("checkAnswerOrder ENFORCES one-at-a-time", () => {
  const bad = checkAnswerOrder(PAYLOAD, [], "tone");
  assert.ok(!bad.ok);
  assert.match(bad.error, /out-of-order/);
  assert.equal(bad.question.id, "offer_name");
  assert.ok(checkAnswerOrder(PAYLOAD, [], "offer_name").ok);
  assert.ok(!checkAnswerOrder(PAYLOAD, [], "ghost").ok);
});

test("validateAnswerValue coerces by kind", () => {
  const enumQ = PAYLOAD.questions[2];
  assert.equal(validateAnswerValue(enumQ, "FAST").value, "fast");
  assert.ok(!validateAnswerValue(enumQ, "blazing").ok);
  const optQ = PAYLOAD.questions[4];
  assert.ok(validateAnswerValue(optQ, "").ok); // optional, empty allowed
  const reqQ = PAYLOAD.questions[0];
  assert.ok(!validateAnswerValue(reqQ, "   ").ok);
});

test("progress reports k of N and completion", () => {
  const p0 = progress(PAYLOAD, []);
  assert.equal(p0.total, 5);
  assert.equal(p0.current_id, "offer_name");
  assert.equal(p0.complete, false);
  const pDone = progress(PAYLOAD, ["offer_name", "tone", "speech_speed_preference", "want_sales_checkout", "client_notes"]);
  assert.equal(pDone.complete, true);
});

test("expiryFrom adds the TTL window in seconds", () => {
  assert.equal(expiryFrom(1000, 7), 1000 + 7 * 86400);
});
