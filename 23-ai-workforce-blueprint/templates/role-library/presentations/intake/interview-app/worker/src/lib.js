// Presentation Interview app — pure, side-effect-free helpers.
//
// Everything here is unit-testable with plain `node --test` (no Cloudflare
// runtime, no network). The Worker (index.js) composes these with D1 + the
// request/response plumbing. This is the SAME contract the repo's
// intake-miniapp uses, so the box-side intake_bridge.py / deck-intake-driver.py
// replay path works unchanged.
//
// SINGLE SOURCE OF TRUTH: the questions come from the box, which generates the
// payload from deck-intake-questions.json (+ upsell-questions.json). This module
// only enforces ordering + shape — it never hardcodes a question.

export const TOKEN_BYTES = 16; // 128-bit capability token
export const DEFAULT_TTL_DAYS = 7;

/** Cryptographically-random lowercase-hex capability token (128-bit). */
export function randomToken(getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto)) {
  const buf = new Uint8Array(TOKEN_BYTES);
  getRandomValues(buf);
  return [...buf].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

export function expiryFrom(createdSeconds, ttlDays = DEFAULT_TTL_DAYS) {
  return createdSeconds + Math.round(ttlDays * 24 * 60 * 60);
}

/** A token is well-formed if it is 32 lowercase-hex chars. Cheap pre-DB guard. */
export function isValidTokenShape(token) {
  return typeof token === "string" && /^[0-9a-f]{32}$/.test(token);
}

/**
 * Validate a questions_payload handed to /api/sessions.
 * Permissive about extra fields, strict about the load-bearing shape.
 */
export function validateQuestionsPayload(payload) {
  if (!payload || typeof payload !== "object") return { ok: false, error: "payload must be an object" };
  const set = payload.question_set;
  if (set !== "standard" && set !== "signature") {
    return { ok: false, error: "question_set must be 'standard' or 'signature'" };
  }
  const qs = payload.questions;
  if (!Array.isArray(qs) || qs.length === 0) return { ok: false, error: "questions must be a non-empty array" };
  const seen = new Set();
  for (const q of qs) {
    if (!q || typeof q !== "object") return { ok: false, error: "each question must be an object" };
    if (typeof q.id !== "string" || !q.id) return { ok: false, error: "each question needs a string id" };
    if (seen.has(q.id)) return { ok: false, error: `duplicate question id '${q.id}'` };
    seen.add(q.id);
    if (typeof q.prompt !== "string" || !q.prompt) return { ok: false, error: `question '${q.id}' needs a prompt` };
  }
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Conditional-question evaluator, ported from deck-intake-driver.py
// auto_skip_all_conditionals() — covers BOTH conditional schemas.
// ---------------------------------------------------------------------------

function _askIfSatisfied(cond, answers) {
  const refId = cond.question_id;
  if (!refId) return null;
  const entry = answers[refId];
  if (entry === undefined) return null;
  const val = String(entry).trim().toLowerCase();
  if ("truthy" in cond) {
    const isTruthy = val === "yes" || val === "true" || val === "y" || val === "1"
      || (val !== "" && val !== "no" && val !== "false" && val !== "n" && val !== "0" && Boolean(val));
    return isTruthy === Boolean(cond.truthy);
  }
  if ("equals" in cond) return val === String(cond.equals).trim().toLowerCase();
  if ("contains" in cond) return val.includes(String(cond.contains).trim().toLowerCase());
  if ("contains_any" in cond) return (cond.contains_any || []).some((x) => val.includes(String(x).trim().toLowerCase()));
  if ("in" in cond) return (cond.in || []).map((x) => String(x).trim().toLowerCase()).includes(val);
  return true;
}

function _conditionMet(question, answers) {
  const cond = question.conditional_on;
  if (!cond) return true;
  const ctrlValue = answers[cond.id];
  if (ctrlValue === undefined) return null;
  return String(ctrlValue).trim().toLowerCase() === String(cond.equals).trim().toLowerCase();
}

export function isQuestionActive(question, answers) {
  if (!answers) return true;
  const askIf = question.ask_if;
  if (askIf) { const r = _askIfSatisfied(askIf, answers); if (r !== null) return r; }
  const condOn = question.conditional_on;
  if (condOn) { const r = _conditionMet(question, answers); if (r !== null) return r; }
  return null;
}

/** Ordered question list, sorted by `order` when present. */
export function orderedQuestions(payload, answers) {
  const qs = [...(payload.questions || [])];
  let filtered = qs;
  if (answers) filtered = qs.filter((q) => isQuestionActive(q, answers) !== false);
  const hasOrder = filtered.every((q) => typeof q.order === "number");
  if (hasOrder) filtered.sort((a, b) => a.order - b.order);
  return filtered;
}

/** Index of the first still-unanswered question in canonical order. Returns -1 when done. */
export function nextQuestionIndex(payload, answeredIds, answers) {
  const answered = new Set(answeredIds);
  const qs = orderedQuestions(payload, answers);
  for (let i = 0; i < qs.length; i++) {
    if (answered.has(qs[i].id)) continue;
    return i;
  }
  return -1;
}

/** Enforce one-at-a-time at the API layer. */
export function checkAnswerOrder(payload, answeredIds, questionId, answers) {
  const qs = orderedQuestions(payload, answers);
  const q = qs.find((x) => x.id === questionId);
  if (!q) return { ok: false, error: `unknown question id '${questionId}'` };
  const idx = nextQuestionIndex(payload, answeredIds, answers);
  if (idx === -1) return { ok: false, error: "all questions already answered" };
  const expected = qs[idx];
  if (expected.id !== questionId) {
    return {
      ok: false,
      error: `out-of-order answer: expected '${expected.id}', got '${questionId}'. One question at a time.`,
      question: expected,
    };
  }
  return { ok: true, question: q };
}

/** Coerce + validate a single answer value against its question kind. */
export function validateAnswerValue(question, rawValue) {
  const kind = question.kind || "text";
  const required = question.required !== false;
  let value = rawValue;

  if (value === null || value === undefined) value = "";
  if (typeof value !== "string") value = String(value);
  value = value.trim();

  if (!value) {
    if (required) return { ok: false, error: "an answer is required" };
    return { ok: true, value: "" };
  }

  if (kind === "enum") {
    const allowed = question.allowed_values || [];
    const norm = value.toLowerCase();
    if (allowed.length && !allowed.map((a) => String(a).toLowerCase()).includes(norm)) {
      return { ok: false, error: `must be one of: ${allowed.join(", ")}` };
    }
    return { ok: true, value: norm };
  }

  if (kind === "boolean") {
    const truthy = ["true", "yes", "y", "1"];
    const falsy = ["false", "no", "n", "0"];
    const norm = value.toLowerCase();
    if (truthy.includes(norm)) return { ok: true, value: "true" };
    if (falsy.includes(norm)) return { ok: true, value: "false" };
    return { ok: false, error: "answer yes or no" };
  }

  if (kind === "integer") {
    if (!/^-?\d+$/.test(value)) return { ok: false, error: "must be a whole number" };
    return { ok: true, value };
  }

  return { ok: true, value }; // text
}

/** Progress summary the UI renders ("Question k of N"). */
export function progress(payload, answeredIds, answers) {
  const qs = orderedQuestions(payload, answers);
  const total = qs.length;
  const answered = qs.filter((q) => answeredIds.includes(q.id)).length;
  const idx = nextQuestionIndex(payload, answeredIds, answers);
  return {
    total,
    answered,
    remaining: total - answered,
    current_id: idx === -1 ? null : qs[idx].id,
    current_index: idx === -1 ? null : idx,
    complete: idx === -1,
  };
}

/** Answers with a monotonic id strictly greater than `since` (poll cursor). */
export function answersSince(rows, since) {
  const cur = Number.isFinite(since) ? since : 0;
  return rows.filter((r) => Number(r.id) > cur).sort((a, b) => Number(a.id) - Number(b.id));
}

export function jsonResponse(obj, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...extraHeaders,
    },
  });
}

export function errorResponse(message, status = 400) {
  return jsonResponse({ status: "error", error: message }, status);
}
