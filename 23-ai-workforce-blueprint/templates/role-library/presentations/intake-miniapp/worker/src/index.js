// Presentation intake mini-app — Cloudflare Worker (API).
//
// The primary intake surface. It renders ONE question per screen (the Pages UI
// in ../pages) and physically cannot present or accept a batch: the API serves
// only the current question and rejects any out-of-order answer. The box bridge
// (../bridge/intake_bridge.py) polls the answers and replays each through the
// existing deck-intake-driver.py, so the intake_ledger, provers, Gate 0 and
// deck-build-guard are all unchanged. This is a FRONT-END to the existing state
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
  randomToken,
  sixDigitCode,
  nowSeconds,
  expiryFrom,
  isValidTokenShape,
  validateQuestionsPayload,
  checkAnswerOrder,
  validateAnswerValue,
  answersSince,
  progress,
  jsonResponse,
  errorResponse,
  DEFAULT_TTL_DAYS,
} from "./lib.js";

export default {
  async fetch(request, env) {
    try {
      return await route(request, env);
    } catch (err) {
      // Never leak internals or secrets in the body.
      return errorResponse("internal error", 500);
    }
  },
};

async function route(request, env) {
  const url = new URL(request.url);
  const parts = url.pathname.split("/").filter(Boolean); // e.g. ["api","sessions",":token","answers"]
  const method = request.method.toUpperCase();

  if (method === "GET" && url.pathname === "/healthz") {
    return jsonResponse({ status: "ok", service: "presentation-intake", ttl_days: DEFAULT_TTL_DAYS });
  }

  if (parts[0] !== "api" || parts[1] !== "sessions") {
    return errorResponse("not found", 404);
  }

  // POST /api/sessions  (box mints a session)
  if (parts.length === 2 && method === "POST") {
    return mintSession(request, env);
  }

  const token = parts[2];
  if (!token || !isValidTokenShape(token)) return errorResponse("bad token", 400);

  // GET /api/sessions/:token
  if (parts.length === 3 && method === "GET") {
    return getSession(env, token);
  }
  // POST /api/sessions/:token/answers
  if (parts.length === 4 && parts[3] === "answers" && method === "POST") {
    return postAnswer(request, env, token);
  }
  // GET /api/sessions/:token/answers?since=
  if (parts.length === 4 && parts[3] === "answers" && method === "GET") {
    return pollAnswers(request, env, token);
  }
  // POST /api/sessions/:token/complete
  if (parts.length === 4 && parts[3] === "complete" && method === "POST") {
    return completeSession(env, token);
  }

  return errorResponse("not found", 404);
}

// ---- box-authenticated: mint -------------------------------------------------

async function mintSession(request, env) {
  const admin = env.INTAKE_ADMIN_TOKEN;
  if (!admin) return errorResponse("server not configured", 503);
  const auth = request.headers.get("authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!timingSafeEqual(bearer, admin)) return errorResponse("unauthorized", 401);

  let body;
  try {
    body = await request.json();
  } catch {
    return errorResponse("invalid JSON body", 400);
  }
  const runId = body.run_id;
  const boxId = body.box_id;
  const payload = body.questions_payload;
  if (typeof runId !== "string" || !runId) return errorResponse("run_id required", 400);
  if (typeof boxId !== "string" || !boxId) return errorResponse("box_id required", 400);
  const check = validateQuestionsPayload(payload);
  if (!check.ok) return errorResponse(`questions_payload invalid: ${check.error}`, 400);

  const created = nowSeconds();

  // Single active session per run: return the existing open one if present.
  const existing = await env.DB.prepare(
    "SELECT token, expires_at FROM sessions WHERE run_id = ? AND status = 'open'"
  ).bind(runId).first();
  if (existing && Number(existing.expires_at) > created) {
    return jsonResponse({
      status: "exists",
      token: existing.token,
      capability_url: capabilityUrl(request, existing.token),
      reused: true,
    });
  }
  // If an expired open row lingers, flip it so the unique index frees up.
  if (existing) {
    await env.DB.prepare("UPDATE sessions SET status = 'expired' WHERE token = ?")
      .bind(existing.token).run();
  }

  const token = randomToken();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const confirmCode = body.want_confirm_code ? sixDigitCode() : null;

  await env.DB.prepare(
    `INSERT INTO sessions (token, run_id, box_id, question_set, questions_json, confirm_code, status, created_at, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)`
  ).bind(
    token, runId, boxId, payload.question_set, JSON.stringify(payload), confirmCode, created, expires
  ).run();

  return jsonResponse({
    status: "created",
    token,
    capability_url: capabilityUrl(request, token),
    confirm_code: confirmCode, // returned to the BOX only; box speaks it in chat if used
    expires_at: expires,
  }, 201);
}

// ---- capability: read session (payload + progress) --------------------------

async function getSession(env, token) {
  const row = await loadOpenSession(env, token);
  if (row.error) return row.error;
  const { session, payload } = row;
  const answeredIds = await answeredIdList(env, token);
  return jsonResponse({
    status: session.status,
    run_id: session.run_id,
    question_set: session.question_set,
    questions: payload.questions,
    progress: progress(payload, answeredIds),
    answered: answeredIds,
    requires_confirm_code: !!session.confirm_code,
    expires_at: session.expires_at,
  });
}

// ---- capability: record one answer (order-enforced) -------------------------

async function postAnswer(request, env, token) {
  const row = await loadOpenSession(env, token);
  if (row.error) return row.error;
  const { session, payload } = row;
  if (session.status === "complete") return errorResponse("session already complete", 409);

  let body;
  try {
    body = await request.json();
  } catch {
    return errorResponse("invalid JSON body", 400);
  }

  if (session.confirm_code) {
    const supplied = String(body.confirm_code || "");
    if (!timingSafeEqual(supplied, session.confirm_code)) {
      return errorResponse("confirmation code required or incorrect", 401);
    }
  }

  const questionId = body.question_id;
  const answeredIds = await answeredIdList(env, token);

  // One at a time: only the current expected question may be answered.
  const order = checkAnswerOrder(payload, answeredIds, questionId);
  if (!order.ok) return jsonResponse({ status: "rejected", error: order.error, expected: order.question || null }, 409);

  const val = validateAnswerValue(order.question, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);

  const created = nowSeconds();
  await env.DB.prepare(
    `INSERT INTO answers (token, question_id, value, created_at) VALUES (?, ?, ?, ?)
     ON CONFLICT (token, question_id) DO UPDATE SET value = excluded.value, created_at = excluded.created_at`
  ).bind(token, questionId, val.value, created).run();

  const nowAnswered = answeredIds.includes(questionId) ? answeredIds : [...answeredIds, questionId];
  return jsonResponse({
    status: "accepted",
    question_id: questionId,
    value: val.value,
    progress: progress(payload, nowAnswered),
  });
}

// ---- capability: poll answers since cursor (box bridge) ---------------------

async function pollAnswers(request, env, token) {
  const row = await loadOpenSession(env, token, /*allowComplete*/ true);
  if (row.error) return row.error;
  const { session, payload } = row;
  const since = Number(new URL(request.url).searchParams.get("since") || 0);

  const res = await env.DB.prepare(
    "SELECT id, question_id, value, created_at FROM answers WHERE token = ? ORDER BY id ASC"
  ).bind(token).all();
  const rows = res.results || [];
  const fresh = answersSince(rows, since);
  const answeredIds = rows.map((r) => r.question_id);

  return jsonResponse({
    status: "ok",
    session_status: session.status,
    cursor: rows.length ? Number(rows[rows.length - 1].id) : since,
    answers: fresh.map((r) => ({ id: Number(r.id), question_id: r.question_id, value: r.value, created_at: Number(r.created_at) })),
    progress: progress(payload, answeredIds),
  });
}

// ---- capability: complete ---------------------------------------------------

async function completeSession(env, token) {
  const row = await loadOpenSession(env, token, /*allowComplete*/ true);
  if (row.error) return row.error;
  const { session, payload } = row;
  const answeredIds = await answeredIdList(env, token);
  const prog = progress(payload, answeredIds);

  // Only genuinely-complete interviews may close (required questions all answered).
  const requiredUnanswered = payload.questions
    .filter((q) => q.required !== false && !answeredIds.includes(q.id))
    .map((q) => q.id);
  if (requiredUnanswered.length) {
    return jsonResponse({ status: "blocked", missing: requiredUnanswered, progress: prog }, 409);
  }

  if (session.status !== "complete") {
    await env.DB.prepare("UPDATE sessions SET status = 'complete', completed_at = ? WHERE token = ?")
      .bind(nowSeconds(), token).run();
  }
  return jsonResponse({ status: "complete", run_id: session.run_id, progress: prog });
}

// ---- helpers ----------------------------------------------------------------

async function loadOpenSession(env, token, allowComplete = false) {
  const session = await env.DB.prepare(
    "SELECT token, run_id, box_id, question_set, questions_json, confirm_code, status, created_at, expires_at FROM sessions WHERE token = ?"
  ).bind(token).first();
  if (!session) return { error: errorResponse("session not found", 404) };
  if (Number(session.expires_at) <= nowSeconds() && session.status !== "complete") {
    return { error: errorResponse("session expired", 410) };
  }
  if (session.status === "expired") return { error: errorResponse("session expired", 410) };
  if (session.status === "complete" && !allowComplete) {
    return { error: errorResponse("session already complete", 409) };
  }
  let payload;
  try {
    payload = JSON.parse(session.questions_json);
  } catch {
    return { error: errorResponse("corrupt session payload", 500) };
  }
  return { session, payload };
}

async function answeredIdList(env, token) {
  const res = await env.DB.prepare("SELECT question_id FROM answers WHERE token = ? ORDER BY id ASC")
    .bind(token).all();
  return (res.results || []).map((r) => r.question_id);
}

function capabilityUrl(request, token) {
  const origin = new URL(request.url).origin;
  return `${origin}/s/${token}`;
}

/** Constant-time string compare to avoid leaking token length/content via timing. */
function timingSafeEqual(a, b) {
  const sa = String(a);
  const sb = String(b);
  if (sa.length !== sb.length) return false;
  let diff = 0;
  for (let i = 0; i < sa.length; i++) diff |= sa.charCodeAt(i) ^ sb.charCodeAt(i);
  return diff === 0;
}
