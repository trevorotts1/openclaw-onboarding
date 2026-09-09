// Presentation intake mini-app — Cloudflare Worker (API + UI via Static Assets).
//
// Single-Worker deployment. It serves the branded UI (Static Assets from
// ./public) for non-/api paths AND the API (/api/*, /healthz). Storage is
// R2-backed (env.STORE) — D1 was never provisionable with the available API
// token's scopes (FABLE-TRUTH §3), so this R2 build is what runs in production.
//
// PRES-024 RECONCILIATION (this revision): the session store keeps the R2
// layout (one JSON object per grant under sessions/<token>.json) but separates
// the two roles the pre-PRES-024 code collapsed:
//
//   identity — a stable session_id carried on every grant object of the same
//     intake; answers live in one session-scoped stream object
//     answers/<session_id>.json, NOT per token, so a renewal keeps every prior
//     answer with no migration;
//   grant    — token + expires_at, renewable and revocable. Renewal mints a
//     new token bound to the SAME session_id / company / presentation run,
//     revokes the previous token (its object flips status='renewed' and the
//     token lands in revoked_tokens/), preserves questions schema + answers +
//     revision, and resumes at the exact first unmet active question. Expiry
//     of a token never erases the session's data.
//
// Endpoints:
//   GET  /healthz                                 -> liveness
//   POST /api/sessions                            -> mint a run session   (box auth)
//   GET  /api/sessions/:token                     -> payload + progress    (capability)
//   POST /api/sessions/:token/answers             -> record ONE answer   (capability)
//   GET  /api/sessions/:token/answers?since=      -> poll new answers    (capability)
//   POST /api/sessions/:token/complete            -> mark complete       (capability)
//   POST /api/sessions/renew                      -> renew (box auth; stable identity)
//   GET  /api/sessions/:token/review              -> editable stored answers (capability)
//   POST /api/sessions/:token/corrections         -> authenticated correction (capability)
//   POST /api/admin/retry-link                    -> record delivery to BOUND recipient (box auth)
//   POST /api/intake                              -> store finished intake JSON (box auth)
//   GET  /api/intake?id=<session>                 -> fetch stored intake (box auth)
//   GET  /api/intake/list                         -> enumerate stored intakes (box auth)
//   POST /api/dept-start                          -> trigger presentation dept (box auth)
//
// Bindings: STORE (R2 bucket). Secrets: INTAKE_ADMIN_TOKEN (box auth),
// COMMAND_CENTER_URL (CC board base URL), CC_DEPT_START_TOKEN (CC ingest auth).

import {
  randomToken, randomSessionId, sixDigitCode, nowSeconds, expiryFrom, isValidTokenShape,
  isValidSessionIdShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
  firstUnmetQuestionId,
  DEFAULT_TTL_DAYS,
} from "./lib.js";

const SESSION_PREFIX = "sessions/";
const ANSWER_PREFIX = "answers/";
const INTAKE_PREFIX = "intakes/";
const REVOKED_PREFIX = "revoked_tokens/";
const CORRECTIONS_PREFIX = "corrections/";
const DELIVERIES_PREFIX = "retry_deliveries/";

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
  // Non-API paths: delegate to the Static Assets layer (SPA fallback serves
  // index.html for / and /s/<token>).
  if (parts[0] !== "api") {
    if (env.ASSETS) return env.ASSETS.fetch(request);
    return errorResponse("not found", 404);
  }
  if (parts[1] === "intake" && method === "POST") return storeIntake(request, env);
  if (parts[1] === "intake" && method === "GET" && parts[2] === "list") return listIntakes(request, env);
  if (parts[1] === "intake" && method === "GET") return fetchIntake(request, env);
  if (parts[1] === "dept-start" && method === "POST") return triggerDeptStart(request, env);
  if (parts[1] === "sessions" && parts[2] === "renew" && method === "POST") return renewSession(request, env);
  if (parts[1] === "admin" && parts[2] === "retry-link" && method === "POST") return postRetryDelivery(request, env);
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
  if (parts.length === 4 && parts[3] === "review" && method === "GET") return reviewAnswers(env, token);
  if (parts.length === 4 && parts[3] === "corrections" && method === "POST") return postCorrection(request, env, token);
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
    if (ex && ex.status === "open") return jsonResponse({ status: "exists", token: existing.token, capability_url: capabilityUrl(request, existing.token), reused: true });
  }

  const newToken = randomToken();
  const sessionId = randomSessionId();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const confirmCode = body.want_confirm_code ? sixDigitCode() : null;
  const session = {
    token: newToken, session_id: sessionId, run_id: runId, box_id: boxId,
    company_id: strOrNull(body.company_id), recipient_chat_id: strOrNull(body.recipient_chat_id),
    question_set: payload.question_set, questions_json: JSON.stringify(payload),
    confirm_code: confirmCode, status: "open", revision: 0,
    invalidated_at: null, invalidated_reason: null,
    created_at: created, expires_at: expires, completed_at: null,
  };
  await saveSession(env, session);
  const updatedRun = runRows.filter((r) => !(r.status === "open" && Number(r.expires_at) <= created));
  updatedRun.push({ token: newToken, session_id: sessionId, status: "open", expires_at: expires });
  await saveRunIndex(env, runId, updatedRun);
  return jsonResponse({ status: "created", token: newToken, session_id: sessionId, capability_url: capabilityUrl(request, newToken), confirm_code: confirmCode, expires_at: expires }, 201);
}

// ---- renew (PRES-024) ---------------------------------------------------------

/**
 * POST /api/sessions/renew (box auth) — same contract as the D1 workers: a
 * NEW expiring token bound to the SAME stable session id / company /
 * presentation run; previous tokens revoked (410 on reuse); questions schema +
 * answers + revision preserved; resumes at the exact first unmet active
 * question. Wrong company -> 403. Complete -> 409.
 */
async function renewSession(request, env) {
  const admin = env.INTAKE_ADMIN_TOKEN;
  if (!admin) return errorResponse("server not configured", 503);
  if (!authorized(request, admin)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const sessionId = typeof body.session_id === "string" ? body.session_id : "";
  const runId = typeof body.run_id === "string" ? body.run_id : "";
  if (!sessionId && !runId) return errorResponse("session_id or run_id required", 400);
  if (sessionId && !isValidSessionIdShape(sessionId)) return errorResponse("bad session_id", 400);

  const latest = await latestGrantFor(env, sessionId, runId);
  if (!latest) return errorResponse("session not found", 404);
  const sid = latest.session_id || latest.token;
  if (runId && latest.run_id !== runId) return errorResponse("session/run mismatch", 409);
  const now = nowSeconds();

  const boundCompany = latest.company_id || "";
  const presentedCompany = strOrNull(body.company_id);
  if (boundCompany && presentedCompany !== boundCompany) {
    return errorResponse("company mismatch", 403);
  }
  if (latest.status === "complete") return errorResponse("session already complete", 409);

  const newToken = randomToken();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(now, ttlDays);
  const revisionAfter = (Number(latest.revision) || 0) + 1;

  // Revoke every still-open grant of this session, then write the fresh grant.
  const openGrants = await openGrantsFor(env, sid, latest);
  const revocations = [];
  for (const g of openGrants) {
    const obj = await loadSession(env, g.token);
    if (!obj || obj.status !== "open") continue;
    obj.status = "renewed";
    await saveSession(env, obj);
    revocations.push(storePutJson(env, REVOKED_PREFIX + g.token + ".json", {
      token: g.token, session_id: sid, revoked_at: now, reason: "renewed",
    }));
  }
  await Promise.all(revocations);

  const fresh = {
    token: newToken, session_id: sid, run_id: latest.run_id, box_id: latest.box_id,
    company_id: latest.company_id, recipient_chat_id: latest.recipient_chat_id,
    question_set: latest.question_set, questions_json: latest.questions_json,
    confirm_code: null, status: "open", revision: (Number(latest.revision) || 0) + 1,
    invalidated_at: null, invalidated_reason: null,
    created_at: now, expires_at: expires, completed_at: null,
  };
  await saveSession(env, fresh);
  await refreshRunIndexFor(env, latest.run_id);

  const answeredRows = await loadAnswers(env, sid);
  const answeredIds = answeredRows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  let payload; try { payload = JSON.parse(latest.questions_json); } catch { return errorResponse("corrupt session payload", 500); }
  const resumeId = firstUnmetQuestionId(payload, answeredIds, answeredValues);
  return jsonResponse({
    status: "renewed",
    token: newToken,
    session_id: sid,
    run_id: latest.run_id,
    revision: (Number(latest.revision) || 0) + 1,
    capability_url: capabilityUrl(request, newToken),
    resume_question_id: resumeId,
    answered_count: answeredIds.length,
    expires_at: expires,
  }, 201);
}

async function getSession(env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  const answeredRows = await loadAnswers(env, sid);
  const answeredIds = answeredRows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: session.status, session_id: sid, revision: session.revision, run_id: session.run_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, requires_confirm_code: !!session.confirm_code, expires_at: session.expires_at });
}

async function postAnswer(request, env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  if (session.status === "complete") return errorResponse("session already complete", 409);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  if (session.confirm_code) { const supplied = String(body.confirm_code || ""); if (!timingSafeEqual(supplied, session.confirm_code)) return errorResponse("confirmation code required or incorrect", 401); }
  const questionId = body.question_id;
  const sid = session.session_id || token;
  const answeredRows = await loadAnswers(env, sid);
  const answeredIds = answeredRows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  const order = checkAnswerOrder(payload, answeredIds, questionId, answeredValues);
  if (!order.ok) return jsonResponse({ status: "rejected", error: order.error, expected: order.question || null }, 409);
  const val = validateAnswerValue(order.question, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);
  const created = nowSeconds();
  // The answer stream hangs off the STABLE session id (PRES-024): a renewal
  // keeps every prior answer with no migration. `token` records the grant.
  const existing = answeredRows.find((r) => r.question_id === questionId);
  const nextRows = existing
    ? answeredRows.map((r) => (r.question_id === questionId ? { ...r, value: val.value, token, created_at: created } : r))
    : [...answeredRows, { id: answeredRows.length ? answeredRows[answeredRows.length - 1].id + 1 : 1, token, session_id: sid, question_id: questionId, value: val.value, created_at: created }];
  await saveAnswers(env, sid, nextRows);
  const nowAnswered = answeredIds.includes(questionId) ? answeredIds : [...answeredIds, questionId];
  return jsonResponse({ status: "accepted", question_id: questionId, value: val.value, session_id: sid, progress: progress(payload, nowAnswered, answeredValues) });
}

async function pollAnswers(request, env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  const since = Number(new URL(request.url).searchParams.get("since") || 0);
  const rows = await loadAnswers(env, sid);
  const fresh = answersSince(rows, since);
  const answeredIds = rows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of rows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: "ok", session_id: sid, revision: session.revision, session_status: session.status, cursor: rows.length ? Number(rows[rows.length - 1].id) : since, answers: fresh.map((r) => ({ id: Number(r.id), question_id: r.question_id, value: r.value, created_at: Number(r.created_at) })), progress: progress(payload, answeredIds, answeredValues) });
}

async function completeSession(env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  const answeredRows = await loadAnswers(env, sid);
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
    await refreshRunIndexFor(env, session.run_id);
  }
  return jsonResponse({ status: "complete", session_id: sid, revision: session.revision, run_id: session.run_id, progress: prog });
}

// ---- review / corrections (PRES-024) ------------------------------------------

/**
 * GET /api/sessions/:token/review — editable stored answer values keyed by
 * question id (the pre-PRES-024 getSession returned only the answered ID list,
 * which made a full review/edit UX impossible).
 */
async function reviewAnswers(env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  const answeredRows = await loadAnswers(env, sid);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  return jsonResponse({
    status: "ok",
    session_id: sid,
    revision: session.revision,
    invalidated_at: session.invalidated_at || null,
    invalidated_reason: session.invalidated_reason || null,
    answers: answeredValues,
    questions: payload.questions,
    expires_at: session.expires_at,
  });
}

/**
 * POST /api/sessions/:token/corrections — authenticated answer correction,
 * same contract as the D1 workers: already-answered questions only, +1
 * revision per correction recorded in corrections/<session>/<n>.json, and
 * downstream invalidation (invalidated_at + completed state revoked) when the
 * session was already complete.
 */
async function postCorrection(request, env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const questionId = body.question_id;
  if (typeof questionId !== "string" || !questionId) return errorResponse("question_id required", 400);
  const q = (payload.questions || []).find((x) => x.id === questionId);
  if (!q) return errorResponse(`unknown question id '${questionId}'`, 404);
  const answeredRows = await loadAnswers(env, sid);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  if (!(questionId in answeredValues)) return errorResponse("question has no stored answer to correct", 404);
  const val = validateAnswerValue(q, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);

  const revisionBefore = Number(session.revision) || 0;
  const revisionAfter = revisionBefore + 1;
  const now = nowSeconds();
  const wasComplete = session.status === "complete";
  const old = answeredValues[questionId];

  const existing = answeredRows.find((r) => r.question_id === questionId);
  const nextRows = existing
    ? answeredRows.map((r) => (r.question_id === questionId ? { ...r, value: val.value, token, created_at: now } : r))
    : [...answeredRows, { id: answeredRows.length ? answeredRows[answeredRows.length - 1].id + 1 : 1, token, session_id: sid, question_id: questionId, value: val.value, created_at: now }];
  await saveAnswers(env, sid, nextRows);
  await storePutJson(env, CORRECTIONS_PREFIX + sid + "/" + revisionAfter + ".json", {
    session_id: sid, question_id: questionId,
    old_value: old == null ? null : String(old), new_value: val.value,
    revision_before: revisionBefore, revision_after: revisionAfter,
    actor: strOrNull(body.actor) || "client", corrected_at: now,
  });
  if (wasComplete) {
    session.status = "open";
    session.revision = revisionAfter;
    session.invalidated_at = now;
    session.invalidated_reason = "answer corrected after completion — downstream outputs require rebuild";
    session.completed_at = null;
  } else {
    session.revision = revisionAfter;
  }
  await saveSession(env, session);
  await refreshRunIndexFor(env, session.run_id);
  return jsonResponse({
    status: "corrected",
    question_id: questionId,
    old_value: old == null ? null : old,
    new_value: val.value,
    revision: revisionAfter,
    revision_before: revisionBefore,
    invalidated_at: wasComplete ? now : null,
    requires_rebuild: wasComplete,
  }, 200);
}

// ---- retry-link delivery record (PRES-024) -------------------------------------

/**
 * POST /api/admin/retry-link (box auth) — record that a retry link was sent.
 * FAIL-CLOSED on the bound recipient (422 when the presented chat id differs
 * from the session's bound recipient). Body:
 * { session_id | run_id, recipient_chat_id, channel?, delivered_at?, token? }
 */
async function postRetryDelivery(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const sessionId = typeof body.session_id === "string" ? body.session_id : "";
  const runId = typeof body.run_id === "string" ? body.run_id : "";
  if (!sessionId && !runId) return errorResponse("session_id or run_id required", 400);
  const latest = await latestGrantFor(env, sessionId, runId);
  if (!latest) return errorResponse("session not found", 404);
  const bound = latest.recipient_chat_id || "";
  const presented = strOrNull(body.recipient_chat_id) || "";
  if (!presented) return errorResponse("recipient_chat_id required", 400);
  if (!bound || presented !== bound) return errorResponse("recipient does not match the session's bound recipient", 422);
  const now = nowSeconds();
  const deliveredAt = Number.isFinite(body.delivered_at) ? body.delivered_at : now;
  const recSessionId = latest.session_id || latest.token;
  await storePutJson(env, DELIVERIES_PREFIX + recSessionId + "/" + deliveredAt + ".json", {
    session_id: recSessionId, recipient_chat_id: bound,
    channel: strOrNull(body.channel) || "telegram", delivered_at: deliveredAt,
    token: strOrNull(body.token), recorded_at: now,
  });
  return jsonResponse({ status: "recorded", session_id: recSessionId, recipient_chat_id: bound, delivered_at: deliveredAt }, 201);
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
function answerKey(sessionId) { return ANSWER_PREFIX + sessionId + ".json"; }

async function loadSession(env, token) {
  return storeGetJson(env, sessionKey(token));
}

async function saveSession(env, session) {
  await storePutJson(env, sessionKey(session.token), session);
}

/**
 * PRES-024: answers are stored per STABLE session id — one stream shared by
 * every grant of the session, so a renewal keeps all prior answers. The
 * legacy per-token objects (answers/<token>.json) are read back for a session
 * whose id equals its original token (pre-PRES-024 rows), which preserves
 * existing data without a rewrite.
 */
async function loadAnswers(env, sessionId) {
  const arr = await storeGetJson(env, answerKey(sessionId));
  if (Array.isArray(arr)) return arr;
  return [];
}

async function saveAnswers(env, sessionId, rows) {
  await storePutJson(env, answerKey(sessionId), rows);
}

async function loadRunIndex(env, runId) {
  const arr = await storeGetJson(env, "runs/" + runId + ".json");
  return Array.isArray(arr) ? arr : [];
}

async function saveRunIndex(env, runId, rows) {
  await storePutJson(env, "runs/" + runId + ".json", rows);
}

/**
 * Rebuild the run index from the session objects that reference the run —
 * PRES-024: a renewal writes a NEW grant and flips the old one, so a stale
 * cached index would keep naming a revoked token as the run's open session.
 */
async function refreshRunIndexFor(env, runId) {
  const listed = await env.STORE.list({ prefix: SESSION_PREFIX });
  const rows = [];
  for (const obj of (listed && listed.objects) || []) {
    const s = await storeGetJson(env, obj.key);
    if (s && s.run_id === runId) {
      rows.push({ token: s.token, session_id: s.session_id || null, status: s.status, expires_at: s.expires_at });
    }
  }
  await saveRunIndex(env, runId, rows);
}

async function openGrantsFor(env, sid, latest) {
  // The run index names this session's sibling grants; fall back to the
  // latest grant itself when the index has no session_id entries.
  const runRows = await loadRunIndex(env, latest.run_id);
  const withSid = runRows.filter((r) => r.session_id === sid);
  if (withSid.length) return withSid;
  return [{ token: latest.token, session_id: sid, status: latest.status, expires_at: latest.expires_at }];
}

async function latestGrantFor(env, sessionId, runId) {
  if (sessionId) {
    // Walk every grant object carrying this session id (revoked ones included)
    // and return the newest by created_at.
    const listed = await env.STORE.list({ prefix: SESSION_PREFIX });
    let latest = null;
    for (const obj of (listed && listed.objects) || []) {
      const s = await storeGetJson(env, obj.key);
      if (s && (s.session_id === sessionId)) {
        if (!latest || Number(s.created_at) > Number(latest.created_at)) latest = s;
      }
    }
    return latest;
  }
  const runRows = await loadRunIndex(env, runId);
  let latest = null;
  for (const r of runRows) {
    const s = await loadSession(env, r.token);
    if (s && (!latest || Number(s.created_at) > Number(latest.created_at))) latest = s;
  }
  return latest;
}

async function loadOpenSession(env, token, allowComplete = false) {
  const session = await loadSession(env, token);
  if (!session) {
    // PRES-024: a revoked token is REJECTED (410), never treated as unknown.
    const revoked = await storeGetJson(env, REVOKED_PREFIX + token + ".json");
    if (revoked) return { error: errorResponse("session token revoked — use the renewed link", 410) };
    return { error: errorResponse("session not found", 404) };
  }
  // A renewed-away grant is dead FIRST — the revocation, not the clock, is
  // what killed it (PRES-024).
  if (session.status === "renewed") return { error: errorResponse("session token renewed — use the renewed link", 410) };
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

function strOrNull(v) {
  if (v === undefined || v === null) return null;
  const s = String(v).trim();
  return s ? s : null;
}