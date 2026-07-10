// Presentation intake mini-app — pure, side-effect-free helpers.
//
// Everything here is unit-testable with plain `node --test` (no Cloudflare
// runtime, no network). The Worker (index.js) composes these with D1 + the
// request/response plumbing. Keeping the logic here is what lets the offline
// gate exercise the one-question-at-a-time guarantee.
//
// SINGLE SOURCE OF TRUTH: the questions themselves come from the box, which
// generates the payload from deck-intake-questions.json + sp-8-questions.json
// (see ../payload/build_questions_payload.py). This module never hardcodes a
// question — it only enforces ordering + shape.

export const TOKEN_BYTES = 16; // 128-bit capability token
export const DEFAULT_TTL_DAYS = 7;

/** Cryptographically-random lowercase-hex capability token (128-bit). */
export function randomToken(getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto)) {
  const buf = new Uint8Array(TOKEN_BYTES);
  getRandomValues(buf);
  return [...buf].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Optional 6-digit confirmation code (spoken in chat for high-trust clients). */
export function sixDigitCode(getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto)) {
  const buf = new Uint8Array(4);
  getRandomValues(buf);
  const n = ((buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3]) >>> 0;
  return String(n % 1000000).padStart(6, "0");
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
 * Validate a questions_payload handed to /api/sessions. Returns {ok, error}.
 * We keep this permissive about extra fields (the JSONs carry help/labels we
 * pass straight through) but strict about the load-bearing shape.
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

/**
 * The ordered question list, sorted by `order` when present, else array order.
 * Order is what makes batching impossible: the client can only ever be served,
 * and can only ever answer, the current question.
 */
export function orderedQuestions(payload) {
  const qs = [...(payload.questions || [])];
  const hasOrder = qs.every((q) => typeof q.order === "number");
  if (hasOrder) qs.sort((a, b) => a.order - b.order);
  return qs;
}

/**
 * Index of the first still-unanswered question in canonical order — the only
 * question the client may answer next. Optional questions are still presented
 * here (the UI offers a Skip that submits their default); they are not silently
 * dropped. Returns -1 when every question has an answer on record.
 */
export function nextQuestionIndex(payload, answeredIds) {
  const answered = new Set(answeredIds);
  const qs = orderedQuestions(payload);
  for (let i = 0; i < qs.length; i++) {
    if (answered.has(qs[i].id)) continue;
    return i; // first unanswered question in canonical order
  }
  return -1;
}

/**
 * Enforce the one-at-a-time contract at the API layer: the only question a
 * client may answer is the current expected one. Returns {ok, error, question}.
 * `expectedId` is the id at nextQuestionIndex; answering anything else — the
 * mechanism a batcher would need — is rejected.
 */
export function checkAnswerOrder(payload, answeredIds, questionId) {
  const qs = orderedQuestions(payload);
  const q = qs.find((x) => x.id === questionId);
  if (!q) return { ok: false, error: `unknown question id '${questionId}'` };
  const idx = nextQuestionIndex(payload, answeredIds);
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

/**
 * Coerce + validate a single answer value against its question kind. Mirrors
 * (a subset of) the box-side deck-intake-driver validation so the client gets
 * immediate feedback; the Python driver remains the authoritative gate when the
 * bridge replays the answer. Returns {ok, error, value}.
 */
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

/** Answers with a monotonic id strictly greater than `since` (poll cursor). */
export function answersSince(rows, since) {
  const cur = Number.isFinite(since) ? since : 0;
  return rows.filter((r) => Number(r.id) > cur).sort((a, b) => Number(a.id) - Number(b.id));
}

/** Progress summary the UI renders ("Question k of N"). */
export function progress(payload, answeredIds) {
  const qs = orderedQuestions(payload);
  const total = qs.length;
  const answered = qs.filter((q) => answeredIds.includes(q.id)).length;
  const idx = nextQuestionIndex(payload, answeredIds);
  return {
    total,
    answered,
    remaining: total - answered,
    current_id: idx === -1 ? null : qs[idx].id,
    current_index: idx === -1 ? null : idx,
    complete: idx === -1,
  };
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
