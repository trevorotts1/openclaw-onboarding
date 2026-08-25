// Presentation intake mini-app — Cloudflare Worker (API + UI via Static Assets).
//
// Single-Worker deployment: serves the branded UI (Static Assets from ./public)
// for non-/api paths AND the API (/api/*, /healthz). Storage is R2-backed
// (env.STORE); D1 is not provisionable with the available API token's scopes.
//
// Endpoints:
//   GET  /healthz                                 -> liveness
//   POST /api/sessions                            -> mint a run session   (box auth)
//   GET  /api/sessions/:token                     -> payload + progress  (capability)
//   POST /api/sessions/:token/answers             -> record ONE answer   (capability)
//   GET  /api/sessions/:token/answers?since=      -> poll new answers    (capability)
//   POST /api/sessions/:token/complete            -> mark complete       (capability)
//   POST /api/intake                              -> store finished intake JSON (box auth)
//   GET  /api/intake?id=<session>                 -> fetch stored intake (box auth)
//   POST /api/dept-start                          -> trigger presentation dept (box auth)
//
// Bindings: STORE (R2 bucket). Secret: INTAKE_ADMIN_TOKEN (box auth),
// COMMAND_CENTER_URL (CC board base URL), CC_DEPT_START_TOKEN (CC ingest auth).

import {
  randomToken, sixDigitCode, nowSeconds, expiryFrom, isValidTokenShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
  DEFAULT_TTL_DAYS,
} from "./lib.js";

const SESSION_PREFIX = "sessions/";
const ANSWER_PREFIX = "answers/";
const INTAKE_PREFIX = "intakes/";

export default {
  async fetch(request, env, ctx) {
    try { return await route(request, env); } catch (err) { return errorResponse("internal error", 500); }
  },
};

async function route(request, env) {
  const url = new URL(request.url);
  const parts = url.pathname.split("/").filter(Boolean);
  const method = request.method.toUpperCase();
  if (method === "GET" && url.pathname === "/healthz") return jsonResponse({ status: "ok", service: "presentation-intake", ttl_days: DEFAULT_TTL_DAYS });
  // Non-API paths: delegate to the Static Assets layer so the SPA fallback
  // serves index.html for / and /s/<token>.
  if (parts[0] !== "api") {
    if (env.ASSETS) return env.ASSETS.fetch(request);
    return errorResponse("not found", 404);
  }
  if (parts[1] === "intake" && method === "POST") return storeIntake(request, env);
  if (parts[1] === "intake" && method === "GET" && parts[2] === "list") return listIntakes(request, env);
  if (parts[1] === "intake" && method === "GET") return fetchIntake(request, env);
  if (parts[1] === "dept-start" && method === "POST") return triggerDeptStart(request, env);
  if (parts[1] === "sessions") return routeSessions(request, env, parts, method, url);
  return errorResponse("not found", 404);
}

// ---- session API (same contract as the repo intake-miniapp) -----------------
// parts includes the leading "api" segment (["api","sessions",...]).

async function routeSessions(request, env, parts, method, url) {
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
  if (!authorized(request, admin)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const runId = body.run_id, boxId = body.box_id, payload = body.questions_payload;
  if (typeof runId !== "string" || !runId) return errorResponse("run_id required", 400);
  if (typeof boxId !== "string" || !boxId) return errorResponse("box_id required", 400);
  const check = validateQuestionsPayload(payload);
  if (!check.ok) return errorResponse("questions_payload invalid: " + check.error, 400);
  const created = nowSeconds();

  const runRows = await loadRunIndex(env, runId);
  const existing = runRows.find((r) => r.status === "open" && Number(r.expires_at) > created);
  if (existing) {
    const ex = await loadSession(env, existing.token);
    if (ex) return jsonResponse({ status: "exists", token: existing.token, capability_url: capabilityUrl(request, existing.token), reused: true });
  }

  const newToken = randomToken();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const confirmCode = body.want_confirm_code ? sixDigitCode() : null;
  const session = {
    token: newToken, run_id: runId, box_id: boxId, question_set: payload.question_set,
    questions_json: JSON.stringify(payload), confirm_code: confirmCode, status: "open",
    created_at: created, expires_at: expires, completed_at: null,
  };
  await saveSession(env, session);
  const updatedRun = runRows.filter((r) => !(r.status === "open" && Number(r.expires_at) <= created));
  updatedRun.push({ token: newToken, status: "open", expires_at: expires });
  await saveRunIndex(env, runId, updatedRun);
  return jsonResponse({ status: "created", token: newToken, capability_url: capabilityUrl(request, newToken), confirm_code: confirmCode, expires_at: expires }, 201);
}

async function getSession(env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  const answeredRows = await loadAnswers(env, token);
  const answeredIds = answeredRows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: session.status, run_id: session.run_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, requires_confirm_code: !!session.confirm_code, expires_at: session.expires_at });
}

async function postAnswer(request, env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  if (session.status === "complete") return errorResponse("session already complete", 409);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  if (session.confirm_code) { const supplied = String(body.confirm_code || ""); if (!timingSafeEqual(supplied, session.confirm_code)) return errorResponse("confirmation code required or incorrect", 401); }
  const questionId = body.question_id;
  const answeredRows = await loadAnswers(env, token);
  const answeredIds = answeredRows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  const order = checkAnswerOrder(payload, answeredIds, questionId, answeredValues);
  if (!order.ok) return jsonResponse({ status: "rejected", error: order.error, expected: order.question || null }, 409);
  const val = validateAnswerValue(order.question, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);
  const created = nowSeconds();
  const existing = answeredRows.find((r) => r.question_id === questionId);
  const nextRows = existing
    ? answeredRows.map((r) => (r.question_id === questionId ? { ...r, value: val.value, created_at: created } : r))
    : [...answeredRows, { id: answeredRows.length ? answeredRows[answeredRows.length - 1].id + 1 : 1, token, question_id: questionId, value: val.value, created_at: created }];
  await saveAnswers(env, token, nextRows);
  const nowAnswered = answeredIds.includes(questionId) ? answeredIds : [...answeredIds, questionId];
  return jsonResponse({ status: "accepted", question_id: questionId, value: val.value, progress: progress(payload, nowAnswered, answeredValues) });
}

async function pollAnswers(request, env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const since = Number(new URL(request.url).searchParams.get("since") || 0);
  const rows = await loadAnswers(env, token);
  const fresh = answersSince(rows, since);
  const answeredIds = rows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of rows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: "ok", session_status: session.status, cursor: rows.length ? Number(rows[rows.length - 1].id) : since, answers: fresh.map((r) => ({ id: Number(r.id), question_id: r.question_id, value: r.value, created_at: Number(r.created_at) })), progress: progress(payload, answeredIds, answeredValues) });
}

async function completeSession(env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const answeredRows = await loadAnswers(env, token);
  const answeredIds = answeredRows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  const prog = progress(payload, answeredIds, answeredValues);
  const requiredUnanswered = payload.questions.filter((q) => {
    if (q.required === false) return false;
    if (answeredIds.includes(q.id)) return false;
    const active = isQuestionActive(q, answeredValues);
    if (active === false) return false;
    return q.block_gate !== false;
  }).map((q) => q.id);
  if (requiredUnanswered.length) return jsonResponse({ status: "blocked", missing: requiredUnanswered, progress: prog }, 409);
  if (session.status !== "complete") {
    session.status = "complete";
    session.completed_at = nowSeconds();
    await saveSession(env, session);
    const runRows = await loadRunIndex(env, session.run_id);
    const updatedRun = runRows.map((r) => (r.token === token ? { ...r, status: "complete" } : r));
    await saveRunIndex(env, session.run_id, updatedRun);
  }
  return jsonResponse({ status: "complete", run_id: session.run_id, progress: prog });
}

// ---- intake storage + dept-start trigger (R2-backed) ------------------------

function intakeKey(sessionId) { return INTAKE_PREFIX + String(sessionId).replace(/[^A-Za-z0-9._-]/g, "") + ".json"; }

/**
 * POST /api/intake — store the assembled intake JSON so the box bridge can
 * poll it into the run dir (R2-backed). Same contract as the D1 worker.
 * Body: { file_name, intake }.
 *
 * F21 COMPLETENESS GATE (mirrors the repo worker): an intake missing any
 * REQUIRED deck_brief field or pre_presentation_capture.PRESENTATION_TYPE is
 * rejected with 422 naming the missing fields. Before this gate the server
 * accepted `{}` and the hollow intake flowed downstream into a doomed build.
 */
const REQUIRED_BRIEF_FIELDS = [
  "OFFER_NAME",
  "NAMED_METHODOLOGY",
  "TRANSFORMATION_PROMISE",
  "TIME_TO_RESULT",
  "AUDIENCE",
  "CTA_ACTION",
  "TONE",
  "FINAL_PRICE",
  "WANT_SALES_CHECKOUT",
  "WANT_VSL_PAGE",
];

function validateIntakeCompleteness(intake) {
  const brief = (intake && typeof intake.deck_brief === "object" && intake.deck_brief) || {};
  const pre = (intake && typeof intake.pre_presentation_capture === "object" && intake.pre_presentation_capture) || {};
  const missing = [];
  for (const f of REQUIRED_BRIEF_FIELDS) {
    const v = brief[f];
    if (v === undefined || v === null || (typeof v === "string" && !v.trim())) missing.push("deck_brief." + f);
  }
  if (!pre.PRESENTATION_TYPE || (typeof pre.PRESENTATION_TYPE === "string" && !pre.PRESENTATION_TYPE.trim())) {
    missing.push("pre_presentation_capture.PRESENTATION_TYPE");
  }
  return missing;
}

async function storeIntake(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const intake = body.intake;
  if (!intake || typeof intake !== "object") return errorResponse("intake object required", 400);
  const missingFields = validateIntakeCompleteness(intake);
  if (missingFields.length) {
    return jsonResponse({ status: "rejected", error: "intake incomplete — required fields missing or empty", missing: missingFields }, 422);
  }
  const file_name = (body.file_name || "intake.json").replace(/[^A-Za-z0-9._-]/g, "");
  const session_id = intake.intake_session_id || file_name.replace(/\..+$/, "");
  const created = nowSeconds();
  const key = intakeKey(session_id);
  await storePutJson(env, key, { session_id, file_name, intake, stored_at: created });
  return jsonResponse({ status: "stored", session_id, file_name, stored_at: created }, 201);
}

/**
 * GET /api/intake?id=<session> — fetch a stored intake for the box bridge.
 */
async function fetchIntake(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  const id = new URL(request.url).searchParams.get("id");
  if (!id) return errorResponse("id query param required", 400);
  const key = intakeKey(id);
  const obj = await storeGetJson(env, key);
  if (!obj) return errorResponse("intake not found", 404);
  return jsonResponse(obj, 200);
}

/**
 * GET /api/intake/list — enumerate stored finished intakes so the box-side
 * intake_bridge poll cron can discover which sessions to ingest.
 * Returns { intakes: [{ session_id, file_name, stored_at }] } (metadata only —
 * no payload, no secrets). Sorted newest-first.
 */
async function listIntakes(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  const listed = await env.STORE.list({ prefix: INTAKE_PREFIX });
  const intakes = [];
  for (const obj of (listed && listed.objects) || []) {
    const name = obj.key;
    const sessionId = name.slice(INTAKE_PREFIX.length).replace(/\.json$/, "");
    if (!sessionId) continue;
    let file_name = null;
    let stored_at = null;
    const meta = await storeGetJson(env, name);
    if (meta) {
      file_name = meta.file_name || null;
      stored_at = meta.stored_at != null ? Number(meta.stored_at) : null;
    }
    intakes.push({ session_id: sessionId, file_name, stored_at, key: name });
  }
  intakes.sort((a, b) => (b.stored_at || 0) - (a.stored_at || 0));
  return jsonResponse({ intakes }, 200);
}

/**
 * POST /api/dept-start — trigger the presentation department.
 * Body: { intake_session_id, intake, run_dir, title, description }.
 * This is the NO-SHORTCUTS door: it creates the Command Center kanban card via
 * /api/tasks/ingest (the same endpoint the box-side cc_board.ingest_deck_task
 * uses), keyed by the intake session id. The deck can then only build through
 * presentation-canonical-entry.sh's governed gates.
 */
async function triggerDeptStart(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const intake = body.intake || {};
  const session_id = body.intake_session_id || intake.intake_session_id || "pres-" + nowSeconds();
  const brief = intake.deck_brief || {};
  const title = body.title || (brief.OFFER_NAME ? "Deck — " + brief.OFFER_NAME : "Presentation intake — " + session_id);
  const description = body.description || [
    "Intake captured by the Presentation Interview app.",
    brief.OFFER_NAME ? "Offer: " + brief.OFFER_NAME : "",
    brief.TRANSFORMATION_PROMISE ? "Promise: " + brief.TRANSFORMATION_PROMISE : "",
    brief.AUDIENCE ? "Audience: " + brief.AUDIENCE : "",
    brief.TONE ? "Tone: " + brief.TONE : "",
    brief.CTA_ACTION ? "CTA: " + brief.CTA_ACTION : "",
    brief.FINAL_PRICE ? "Price: " + brief.FINAL_PRICE : "",
    intake.intake_session_id ? "Intake session: " + intake.intake_session_id : "",
  ].filter(Boolean).join("\n");

  const cc = env.COMMAND_CENTER_URL || "";
  const key = intakeKey(session_id);
  if (!cc) {
    // No CC board wired on this deployment: record the trigger intent in R2 so
    // the box-side intake_bridge picks the run up (no shortcuts — the build is
    // still gated by canonical-entry).
    const stored = await storeGetJson(env, key);
    await storePutJson(env, key, Object.assign({}, stored || {}, {
      session_id, file_name: (stored && stored.file_name) || "intake.json",
      dept_trigger: "deferred",
      dept_trigger_note: "COMMAND_CENTER_URL unset — box-side cc_board.ingest_deck_task will create the card",
      updated_at: nowSeconds(),
    }));
    return jsonResponse({ status: "deferred", session_id, note: "COMMAND_CENTER_URL not set; box-side ingest_deck_task will create the card on pick-up" }, 202);
  }

  const token = env.CC_DEPT_START_TOKEN || env.INTAKE_ADMIN_TOKEN || "";
  const source_ref = body.source_ref || intake.intake_session_id || session_id;
  const payload = {
    title, description,
    priority: body.priority || "medium",
    source: "presentation-interview-app",
    source_ref,
    department_slug: "presentations",
    persona: "Director of Presentations",
    external_session_id: session_id,
  };
  try {
    const resp = await fetch(cc.replace(/\/$/, "") + "/api/tasks/ingest", {
      method: "POST",
      headers: { "content-type": "application/json", ...(token ? { authorization: "Bearer " + token } : {}) },
      body: JSON.stringify(payload),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok && data.task_id) {
      const stored = await storeGetJson(env, key);
      await storePutJson(env, key, Object.assign({}, stored || {}, {
        session_id, file_name: (stored && stored.file_name) || "intake.json",
        dept_trigger: "fired", dept_task_id: String(data.task_id), updated_at: nowSeconds(),
      }));
      return jsonResponse({ status: "fired", session_id, task_id: data.task_id, deduped: !!data.deduped }, 201);
    }
    return errorResponse("dept start failed (HTTP " + resp.status + "): " + (data.error || "unknown"), 502);
  } catch (err) {
    return errorResponse("dept start transport error: " + (err && err.message ? err.message : "network"), 502);
  }
}

// ---- R2 storage helpers ----------------------------------------------------

async function storePutJson(env, key, obj) {
  await env.STORE.put(key, JSON.stringify(obj));
}

async function storeGetJson(env, key) {
  const obj = await env.STORE.get(key);
  if (!obj) return null;
  const text = await obj.text();
  try { return JSON.parse(text); } catch { return null; }
}

function sessionKey(token) { return SESSION_PREFIX + token + ".json"; }
function answerKey(token) { return ANSWER_PREFIX + token + ".json"; }

async function loadSession(env, token) {
  return storeGetJson(env, sessionKey(token));
}

async function saveSession(env, session) {
  await storePutJson(env, sessionKey(session.token), session);
}

async function loadAnswers(env, token) {
  const arr = await storeGetJson(env, answerKey(token));
  return Array.isArray(arr) ? arr : [];
}

async function saveAnswers(env, token, rows) {
  await storePutJson(env, answerKey(token), rows);
}

async function loadRunIndex(env, runId) {
  const arr = await storeGetJson(env, "runs/" + runId + ".json");
  return Array.isArray(arr) ? arr : [];
}

async function saveRunIndex(env, runId, rows) {
  await storePutJson(env, "runs/" + runId + ".json", rows);
}

async function loadOpenSession(env, token, allowComplete = false) {
  const session = await loadSession(env, token);
  if (!session) return { error: errorResponse("session not found", 404) };
  if (Number(session.expires_at) <= nowSeconds() && session.status !== "complete") return { error: errorResponse("session expired", 410) };
  if (session.status === "expired") return { error: errorResponse("session expired", 410) };
  if (session.status === "complete" && !allowComplete) return { error: errorResponse("session already complete", 409) };
  let payload; try { payload = JSON.parse(session.questions_json); } catch { return { error: errorResponse("corrupt session payload", 500) }; }
  return { session, payload };
}

function capabilityUrl(request, token) { return `${new URL(request.url).origin}/s/${token}`; }

function authorized(request, secret) {
  const auth = request.headers.get("authorization") || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  return timingSafeEqual(bearer, secret);
}

function requireAdmin(request, env) {
  const admin = env.INTAKE_ADMIN_TOKEN;
  if (!admin) return false;
  return authorized(request, admin);
}

function timingSafeEqual(a, b) {
  const sa = String(a), sb = String(b);
  if (sa.length !== sb.length) return false;
  let diff = 0; for (let i = 0; i < sa.length; i++) diff |= sa.charCodeAt(i) ^ sb.charCodeAt(i);
  return diff === 0;
}
