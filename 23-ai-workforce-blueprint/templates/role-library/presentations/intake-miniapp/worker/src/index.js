// Presentation intake mini-app — Cloudflare Worker (API).
//
// The primary intake surface. It renders ONE question per screen (the Pages UI
// in ../pages) and physically cannot present or accept a batch: the API serves
// only the current question and rejects any out-of-order answer. The box bridge
// (../bridge/intake_bridge.py) polls the answers and replays each through the
// existing deck-intake-driver.py, so the intake_ledger, provers, Gate 0 and
// presentation-canonical-entry.sh's GATE 0 are all unchanged (the intake-ledger check was relocated from the retired deck-build-guard.sh, U025).
// This is a FRONT-END to the existing state
// machine, not a second state machine.
//
// Endpoints:
//   GET  /healthz                            -> liveness
//   POST /api/sessions                       -> mint a run session   (box auth)
//   GET  /api/sessions/:token                -> payload + progress    (capability)
//   POST /api/sessions/:token/answers        -> record ONE answer     (capability)
//   GET  /api/sessions/:token/answers?since= -> poll new answers      (capability)
//   POST /api/sessions/:token/complete       -> mark the run complete (capability)
//
// Bindings (see wrangler.toml): DB (D1). Secret: INTAKE_ADMIN_TOKEN (box auth).

import {
  randomToken, sixDigitCode, nowSeconds, expiryFrom, isValidTokenShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
  DEFAULT_TTL_DAYS,
} from "./lib.js";

export default {
  async fetch(request, env) {
    try { return await route(request, env); } catch (err) { return errorResponse("internal error", 500); }
  },
};

async function route(request, env) {
  const url = new URL(request.url);
  const parts = url.pathname.split("/").filter(Boolean);
  const method = request.method.toUpperCase();
  if (method === "GET" && url.pathname === "/healthz") return jsonResponse({ status: "ok", service: "presentation-intake", ttl_days: DEFAULT_TTL_DAYS });
  if (parts[0] !== "api" || parts[1] !== "sessions") return errorResponse("not found", 404);
  if (parts.length === 2 && method === "POST") return mintSession(request, env);
  const token = parts[2];
  if (!token || !isValidTokenShape(token)) return errorResponse("bad token", 400);
  if (parts.length === 3 && method === "GET") return getSession(env, token);
  if (parts.length === 4 && parts[3] === "answers" && method === "POST") return postAnswer(request, env, token);
  if (parts.length === 4 && parts[3] === "answers" && method === "GET") return pollAnswers(request, env, token);
  if (parts.length === 4 && parts[3] === "complete" && method === "POST") return completeSession(env, token);
  return errorResponse("not found", 404);
}

async function mintSession(request, env) {
  const admin = env.INTAKE_ADMIN_TOKEN;
  if (!admin) return errorResponse("server not configured", 503);
  const auth = request.headers.get("authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!timingSafeEqual(bearer, admin)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const runId = body.run_id, boxId = body.box_id, payload = body.questions_payload;
  if (typeof runId !== "string" || !runId) return errorResponse("run_id required", 400);
  if (typeof boxId !== "string" || !boxId) return errorResponse("box_id required", 400);
  const check = validateQuestionsPayload(payload);
  if (!check.ok) return errorResponse("questions_payload invalid: " + check.error, 400);
  const created = nowSeconds();
  const existing = await env.DB.prepare("SELECT token, expires_at FROM sessions WHERE run_id = ? AND status = 'open'").bind(runId).first();
  if (existing && Number(existing.expires_at) > created) return jsonResponse({ status: "exists", token: existing.token, capability_url: capabilityUrl(request, existing.token), reused: true });
  if (existing) await env.DB.prepare("UPDATE sessions SET status = 'expired' WHERE token = ?").bind(existing.token).run();
  const newToken = randomToken();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const confirmCode = body.want_confirm_code ? sixDigitCode() : null;
  await env.DB.prepare("INSERT INTO sessions (token, run_id, box_id, question_set, questions_json, confirm_code, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)").bind(newToken, runId, boxId, payload.question_set, JSON.stringify(payload), confirmCode, created, expires).run();
  return jsonResponse({ status: "created", token: newToken, capability_url: capabilityUrl(request, newToken), confirm_code: confirmCode, expires_at: expires }, 201);
}

async function getSession(env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  const answeredIds = await answeredIdList(env, token);
  const answeredValues = await answeredValueMap(env, token);
  return jsonResponse({ status: session.status, run_id: session.run_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, requires_confirm_code: !!session.confirm_code, expires_at: session.expires_at });
}

async function postAnswer(request, env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  if (session.status === "complete") return errorResponse("session already complete", 409);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  if (session.confirm_code) { const supplied = String(body.confirm_code || ""); if (!timingSafeEqual(supplied, session.confirm_code)) return errorResponse("confirmation code required or incorrect", 401); }
  const questionId = body.question_id;
  const answeredIds = await answeredIdList(env, token);
  const answeredValues = await answeredValueMap(env, token);
  const order = checkAnswerOrder(payload, answeredIds, questionId, answeredValues);
  if (!order.ok) return jsonResponse({ status: "rejected", error: order.error, expected: order.question || null }, 409);
  const val = validateAnswerValue(order.question, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);
  const created = nowSeconds();
  await env.DB.prepare("INSERT INTO answers (token, question_id, value, created_at) VALUES (?, ?, ?, ?) ON CONFLICT (token, question_id) DO UPDATE SET value = excluded.value, created_at = excluded.created_at").bind(token, questionId, val.value, created).run();
  const nowAnswered = answeredIds.includes(questionId) ? answeredIds : [...answeredIds, questionId];
  return jsonResponse({ status: "accepted", question_id: questionId, value: val.value, progress: progress(payload, nowAnswered, answeredValues) });
}

async function pollAnswers(request, env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const since = Number(new URL(request.url).searchParams.get("since") || 0);
  const res = await env.DB.prepare("SELECT id, question_id, value, created_at FROM answers WHERE token = ? ORDER BY id ASC").bind(token).all();
  const rows = res.results || [];
  const fresh = answersSince(rows, since);
  const answeredIds = rows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of rows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: "ok", session_status: session.status, cursor: rows.length ? Number(rows[rows.length - 1].id) : since, answers: fresh.map((r) => ({ id: Number(r.id), question_id: r.question_id, value: r.value, created_at: Number(r.created_at) })), progress: progress(payload, answeredIds, answeredValues) });
}

async function completeSession(env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const answeredIds = await answeredIdList(env, token);
  const answeredValues = await answeredValueMap(env, token);
  const prog = progress(payload, answeredIds, answeredValues);
  // U058: conditionally-inactive questions not required. Gate matches driver:830 (required && block_gate).
  // Before: 23 blocking. After: 11 blocking.
  const requiredUnanswered = payload.questions.filter((q) => {
    if (q.required === false) return false;
    if (answeredIds.includes(q.id)) return false;
    const active = isQuestionActive(q, answeredValues);
    if (active === false) return false;
    return q.block_gate !== false;
  }).map((q) => q.id);
  if (requiredUnanswered.length) return jsonResponse({ status: "blocked", missing: requiredUnanswered, progress: prog }, 409);
  if (session.status !== "complete") await env.DB.prepare("UPDATE sessions SET status = 'complete', completed_at = ? WHERE token = ?").bind(nowSeconds(), token).run();
  return jsonResponse({ status: "complete", run_id: session.run_id, progress: prog });
}

async function loadOpenSession(env, token, allowComplete = false) {
  const session = await env.DB.prepare("SELECT token, run_id, box_id, question_set, questions_json, confirm_code, status, created_at, expires_at FROM sessions WHERE token = ?").bind(token).first();
  if (!session) return { error: errorResponse("session not found", 404) };
  if (Number(session.expires_at) <= nowSeconds() && session.status !== "complete") return { error: errorResponse("session expired", 410) };
  if (session.status === "expired") return { error: errorResponse("session expired", 410) };
  if (session.status === "complete" && !allowComplete) return { error: errorResponse("session already complete", 409) };
  let payload; try { payload = JSON.parse(session.questions_json); } catch { return { error: errorResponse("corrupt session payload", 500) }; }
  return { session, payload };
}

async function answeredIdList(env, token) {
  const res = await env.DB.prepare("SELECT question_id FROM answers WHERE token = ? ORDER BY id ASC").bind(token).all();
  return (res.results || []).map((r) => r.question_id);
}

async function answeredValueMap(env, token) {
  const res = await env.DB.prepare("SELECT question_id, value FROM answers WHERE token = ? ORDER BY id ASC").bind(token).all();
  const map = {}; for (const r of (res.results || [])) map[r.question_id] = r.value;
  return map;
}

function capabilityUrl(request, token) { return `${new URL(request.url).origin}/s/${token}`; }

function timingSafeEqual(a, b) {
  const sa = String(a), sb = String(b);
  if (sa.length !== sb.length) return false;
  let diff = 0; for (let i = 0; i < sa.length; i++) diff |= sa.charCodeAt(i) ^ sb.charCodeAt(i);
  return diff === 0;
}
