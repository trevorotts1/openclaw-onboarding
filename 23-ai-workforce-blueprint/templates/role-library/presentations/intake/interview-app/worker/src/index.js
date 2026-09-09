// Presentation Interview app — Cloudflare Worker (API).
//
// This is the SUBMIT-TRIGGER surface. The Pages/static UI (../index.html) posts
// the completed intake here; this Worker:
//   1. stores the answers + assembled intake JSON (D1 or KV), and
//   2. fires the presentation-department start (kanban card on the Command
//      Center board via /api/tasks/ingest) — no shortcuts, the same governed
//      door the box-side bridge uses.
//
// It ALSO exposes the one-question-at-a-time session API used by the repo's
// canonical intake-miniapp, so a box can mint a capability link and replay
// answers through deck-intake-driver.py unchanged. The static mini-app in this
// directory can run either standalone (client-side download + dept-trigger via
// data-intake-sink / data-dept-trigger) or behind this Worker.
//
// Endpoints:
//   GET  /healthz                                 -> liveness
//   POST /api/sessions                            -> mint a run session  (box auth)
//   GET  /api/sessions/:token                     -> payload + progress  (capability)
//   POST /api/sessions/:token/answers             -> record ONE answer   (capability)
//   GET  /api/sessions/:token/answers?since=      -> poll new answers    (capability)
//   POST /api/sessions/:token/complete            -> mark complete       (capability)
//   POST /api/intake                              -> store finished intake JSON  (box/auth)
//   GET  /api/intake?id=<session>                 -> fetch stored intake (box auth)
//   POST /api/dept-start                          -> trigger presentation dept   (box/auth)
//
// PRES-024 — stable session identity vs renewable access-token grants:
//   POST /api/sessions/renew               -> admin re-mints an expired/lost
//     token bound to the SAME session/company/presentation run, revokes the
//     previous token, preserves questions + answers + revision, resumes at the
//     exact first unmet active question (box auth).
//   GET  /api/sessions/:token/review       -> editable stored answer values
//     (capability).
//   POST /api/sessions/:token/corrections  -> authenticated answer correction;
//     downstream invalidation when production already consumed a revision
//     (capability).
//   POST /api/admin/retry-link             -> record a retry-link delivery to
//     the session's BOUND recipient (box auth).
//
// Bindings (see wrangler.toml): DB (D1). Secrets: INTAKE_ADMIN_TOKEN (box auth),
// COMMAND_CENTER_URL (CC board base URL), CC_DEPT_START_TOKEN (CC ingest auth).

import {
  randomToken, randomSessionId, nowSeconds, expiryFrom, isValidTokenShape,
  isValidSessionIdShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
  firstUnmetQuestionId,
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
  if (method === "GET" && url.pathname === "/healthz") {
    return jsonResponse({ status: "ok", service: "presentation-interview", ttl_days: DEFAULT_TTL_DAYS });
  }
  if (parts[0] !== "api") return errorResponse("not found", 404);
  // F22 — the three intake routes below matched parts[0]/parts.length as if the
  // "/api" segment had been consumed. pathname.split("/").filter(Boolean) on
  // "/api/intake" yields ["api","intake"] (length 2), so every condition here was
  // dead code: POST /api/intake and /api/dept-start 404'd forever and deploying
  // this worker verbatim broke the whole submit path. Indexes now match reality.
  if (parts.length === 3 && parts[1] === "intake" && parts[2] === "list" && method === "GET") return listIntakes(request, env);
  if (parts.length === 2 && parts[1] === "intake" && method === "GET") return fetchIntake(request, env);
  if (parts.length === 2 && parts[1] === "intake" && method === "POST") return storeIntake(request, env);
  if (parts.length === 2 && parts[1] === "dept-start" && method === "POST") return triggerDeptStart(request, env);
  // PRES-024: renewal by stable identity + retry-link delivery record.
  if (parts.length === 3 && parts[1] === "sessions" && parts[2] === "renew" && method === "POST") return renewSession(request, env);
  if (parts.length === 3 && parts[1] === "admin" && parts[2] === "retry-link" && method === "POST") return postRetryDelivery(request, env);
  if (parts[1] === "sessions") return routeSessions(request, env, parts, method, url);
  return errorResponse("not found", 404);
}

// ---- session API (same contract as the repo intake-miniapp) ----------------

async function routeSessions(request, env, parts, method, url) {
  // F22 — same off-by-one as the router: parts includes the leading "api".
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
  const existing = await env.DB.prepare("SELECT token, expires_at FROM sessions WHERE run_id = ? AND status = 'open'").bind(runId).first();
  if (existing && Number(existing.expires_at) > created) return jsonResponse({ status: "exists", token: existing.token, capability_url: capabilityUrl(request, existing.token), reused: true });
  if (existing) await env.DB.prepare("UPDATE sessions SET status = 'expired' WHERE token = ?").bind(existing.token).run();
  const newToken = randomToken();
  const sessionId = randomSessionId();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  await env.DB.prepare(
    "INSERT INTO sessions (token, session_id, run_id, box_id, company_id, recipient_chat_id, question_set, questions_json, status, revision, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', 0, ?, ?)"
  ).bind(newToken, sessionId, runId, boxId, strOrNull(body.company_id), strOrNull(body.recipient_chat_id), payload.question_set, JSON.stringify(payload), created, expires).run();
  return jsonResponse({ status: "created", token: newToken, session_id: sessionId, capability_url: capabilityUrl(request, newToken), expires_at: expires }, 201);
}

// ---- renew (PRES-024) ---------------------------------------------------------

/**
 * POST /api/sessions/renew (box auth) — same contract as the intake-miniapp
 * worker's renew: a NEW expiring token bound to the SAME stable session id /
 * company / presentation run; the previous token is revoked (410 on reuse);
 * questions schema + answers + revision are preserved; the response names the
 * exact first unmet active question. Wrong company -> 403. Complete -> 409.
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
  const openGrants = await env.DB.prepare(
    "SELECT token FROM sessions WHERE (session_id = ? OR token = ?) AND status = 'open'"
  ).bind(sid, latest.token).all();
  const stmts = [];
  for (const g of (openGrants.results || [])) {
    stmts.push(env.DB.prepare("UPDATE sessions SET status = 'renewed' WHERE token = ?").bind(g.token));
    stmts.push(env.DB.prepare("INSERT INTO revoked_tokens (token, session_id, revoked_at, reason) VALUES (?, ?, ?, 'renewed') ON CONFLICT (token) DO NOTHING").bind(g.token, sid, now));
  }
  stmts.push(env.DB.prepare(
    "INSERT INTO sessions (token, session_id, run_id, box_id, company_id, recipient_chat_id, question_set, questions_json, status, revision, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)"
  ).bind(newToken, sid, latest.run_id, latest.box_id, latest.company_id, latest.recipient_chat_id, latest.question_set, latest.questions_json, revisionAfter, now, expires));
  try {
    await env.DB.batch(stmts);
  } catch (err) {
    return errorResponse("renewal failed", 500);
  }

  const answeredIds = await answeredIdListForSession(env, sid);
  const answeredValues = await answeredValueMapForSession(env, sid);
  let payload; try { payload = JSON.parse(latest.questions_json); } catch { return errorResponse("corrupt session payload", 500); }
  const resumeId = firstUnmetQuestionId(payload, answeredIds, answeredValues);
  return jsonResponse({
    status: "renewed",
    token: newToken,
    session_id: sid,
    run_id: latest.run_id,
    revision: revisionAfter,
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
  const answeredIds = await answeredIdListForSession(env, sid);
  const answeredValues = await answeredValueMapForSession(env, sid);
  return jsonResponse({ status: session.status, session_id: sid, revision: session.revision, run_id: session.run_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, expires_at: session.expires_at });
}

async function postAnswer(request, env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  if (session.status === "complete") return errorResponse("session already complete", 409);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const questionId = body.question_id;
  const sid = session.session_id || token;
  const answeredIds = await answeredIdListForSession(env, sid);
  const answeredValues = await answeredValueMapForSession(env, sid);
  const order = checkAnswerOrder(payload, answeredIds, questionId, answeredValues);
  if (!order.ok) return jsonResponse({ status: "rejected", error: order.error, expected: order.question || null }, 409);
  const val = validateAnswerValue(order.question, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);
  const created = nowSeconds();
  // Answers hang off the STABLE session identity (PRES-024) — a renewal keeps
  // every prior answer visible without any migration.
  await env.DB.prepare(
    "INSERT INTO answers (session_id, token, question_id, value, created_at) VALUES (?, ?, ?, ?, ?) " +
    "ON CONFLICT (session_id, question_id) DO UPDATE SET value = excluded.value, token = excluded.token, created_at = excluded.created_at"
  ).bind(sid, token, questionId, val.value, created).run();
  const nowAnswered = answeredIds.includes(questionId) ? answeredIds : [...answeredIds, questionId];
  return jsonResponse({ status: "accepted", question_id: questionId, value: val.value, session_id: sid, progress: progress(payload, nowAnswered, answeredValues) });
}

async function pollAnswers(request, env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  const since = Number(new URL(request.url).searchParams.get("since") || 0);
  const res = await env.DB.prepare("SELECT id, question_id, value, created_at FROM answers WHERE session_id = ? ORDER BY id ASC").bind(sid).all();
  const rows = res.results || [];
  const fresh = answersSince(rows, since);
  const answeredIds = rows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of rows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: "ok", session_id: sid, revision: session.revision, session_status: session.status, cursor: rows.length ? Number(rows[rows.length - 1].id) : since, answers: fresh.map((r) => ({ id: Number(r.id), question_id: r.question_id, value: r.value, created_at: Number(r.created_at) })), progress: progress(payload, answeredIds, answeredValues) });
}

async function completeSession(env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  const answeredIds = await answeredIdListForSession(env, sid);
  const answeredValues = await answeredValueMapForSession(env, sid);
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
    await env.DB.prepare("UPDATE sessions SET status = 'complete', completed_at = ? WHERE (token = ? OR session_id = ?) AND status IN ('open','renewed')").bind(nowSeconds(), token, sid).run();
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
  const answeredValues = await answeredValueMapForSession(env, sid);
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
 * same contract as the intake-miniapp worker: already-answered questions only,
 * +1 revision per correction with revision_before/after in the ledger, and
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
  const answeredValues = await answeredValueMapForSession(env, sid);
  if (!(questionId in answeredValues)) return errorResponse("question has no stored answer to correct", 404);
  const val = validateAnswerValue(q, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);

  const revisionBefore = Number(session.revision) || 0;
  const revisionAfter = revisionBefore + 1;
  const now = nowSeconds();
  const wasComplete = session.status === "complete";
  const old = answeredValues[questionId];

  const stmts = [
    env.DB.prepare(
      "INSERT INTO answers (session_id, token, question_id, value, created_at) VALUES (?, ?, ?, ?, ?) " +
      "ON CONFLICT (session_id, question_id) DO UPDATE SET value = excluded.value, token = excluded.token, created_at = excluded.created_at"
    ).bind(sid, token, questionId, val.value, now),
    env.DB.prepare(
      "INSERT INTO corrections (session_id, question_id, old_value, new_value, revision_before, revision_after, actor, corrected_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    ).bind(sid, questionId, old == null ? null : String(old), val.value, revisionBefore, revisionAfter, strOrNull(body.actor) || "client", now),
  ];
  if (wasComplete) {
    stmts.push(env.DB.prepare(
      "UPDATE sessions SET status = 'open', revision = ?, invalidated_at = ?, invalidated_reason = ?, completed_at = NULL WHERE token = ?"
    ).bind(revisionAfter, now, "answer corrected after completion — downstream outputs require rebuild", token));
  } else {
    stmts.push(env.DB.prepare("UPDATE sessions SET revision = ? WHERE token = ?").bind(revisionAfter, token));
  }
  try {
    await env.DB.batch(stmts);
  } catch (err) {
    return errorResponse("correction failed", 500);
  }
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
  await env.DB.prepare(
    "INSERT INTO retry_deliveries (session_id, recipient_chat_id, channel, delivered_at, token, recorded_at) VALUES (?, ?, ?, ?, ?, ?)"
  ).bind(latest.session_id || latest.token, bound, strOrNull(body.channel) || "telegram", deliveredAt, strOrNull(body.token), now).run();
  return jsonResponse({ status: "recorded", session_id: latest.session_id || latest.token, recipient_chat_id: bound, delivered_at: deliveredAt }, 201);
}

// ---- intake storage + dept-start trigger -----------------------------------

/**
 * POST /api/intake — store the assembled intake JSON file on the box.
 * Body: { file_name, intake }. The intake object is the dept-format record the
 * box's deck-intake-driver / cc_board ingest path expects. Stored in D1 and
 * made available to the box bridge (which polls it into the run dir).
 *
 * F21 COMPLETENESS GATE: an intake missing any REQUIRED deck_brief field (the
 * required+block_gate questions of the curated set) or pre_presentation_capture.
 * PRESENTATION_TYPE is rejected with 422 naming the missing fields. Before this
 * gate the server accepted `{}` — a hollow intake flowed downstream, the bridge
 * minted a card from it, and the failure only surfaced mid-build as garbage
 * copy. Server-side validation mirrors what the UI enforces client-side.
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
  if (env.DB) {
    await env.DB.prepare("INSERT INTO intakes (session_id, file_name, intake_json, created_at) VALUES (?, ?, ?, ?) ON CONFLICT (session_id) DO UPDATE SET intake_json = excluded.intake_json, created_at = excluded.created_at").bind(session_id, file_name, JSON.stringify(intake), created).run();
  }
  return jsonResponse({ status: "stored", session_id, file_name, stored_at: created }, 201);
}

/**
 * GET /api/intake?id=<session> — fetch a stored intake for the box bridge.
 *
 * FIX 58 (bridge rendezvous): intake_bridge.py's cmd_ingest() fetches the
 * finished intake via GET /api/intake?id=<session_id> (see _fetch_intake in
 * bridge/intake_bridge.py). This route was missing from the D1 worker — the
 * bridge's `ingest` command 404'd against it even though `poll` (which uses
 * /api/intake/list) worked, so a session picked up by poll could never be
 * re-fetched by session id. Same contract as deployed-r2/src/index.js
 * (the R2-backed worker live in production), converted to the D1 store.
 */
async function fetchIntake(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  const id = new URL(request.url).searchParams.get("id");
  if (!id) return errorResponse("id query param required", 400);
  if (!env.DB) return errorResponse("intake not found", 404);
  const row = await env.DB.prepare(
    "SELECT session_id, file_name, intake_json, created_at FROM intakes WHERE session_id = ?"
  ).bind(id).first();
  if (!row) return errorResponse("intake not found", 404);
  let intake = null;
  try { intake = JSON.parse(row.intake_json); } catch { return errorResponse("corrupt intake record", 500); }
  return jsonResponse({
    session_id: row.session_id,
    file_name: row.file_name,
    intake,
    stored_at: row.created_at != null ? Number(row.created_at) : null,
  }, 200);
}

/**
 * GET /api/intake/list — enumerate stored finished intakes so the box-side
 * intake_bridge poll cron can discover which sessions to ingest.
 * Returns { intakes: [{ session_id, file_name, stored_at }] } (metadata only).
 */
async function listIntakes(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  if (!env.DB) return jsonResponse({ intakes: [] }, 200);
  const rows = await env.DB.prepare(
    "SELECT session_id, file_name, created_at FROM intakes ORDER BY created_at DESC"
  ).all();
  const intakes = (rows && rows.results || []).map((r) => ({
    session_id: r.session_id, file_name: r.file_name,
    stored_at: r.created_at != null ? Number(r.created_at) : null,
  }));
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
  if (!cc) {
    // No CC board wired on this deployment: record the trigger intent in D1 so
    // the box-side intake_bridge picks the run up (no shortcuts — the build is
    // still gated by canonical-entry).
    if (env.DB) {
      await env.DB.prepare("UPDATE intakes SET dept_trigger = 'deferred', dept_trigger_note = ?, updated_at = ? WHERE session_id = ?")
        .bind("COMMAND_CENTER_URL unset — box-side cc_board.ingest_deck_task will create the card", nowSeconds(), session_id).run();
    }
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
      if (env.DB) {
        await env.DB.prepare("UPDATE intakes SET dept_trigger = 'fired', dept_task_id = ?, updated_at = ? WHERE session_id = ?").bind(String(data.task_id), nowSeconds(), session_id).run();
      }
      return jsonResponse({ status: "fired", session_id, task_id: data.task_id, deduped: !!data.deduped }, 201);
    }
    return errorResponse("dept start failed (HTTP " + resp.status + "): " + (data.error || "unknown"), 502);
  } catch (err) {
    return errorResponse("dept start transport error: " + (err && err.message ? err.message : "network"), 502);
  }
}

// ---- helpers -----------------------------------------------------------------

async function latestGrantFor(env, sessionId, runId) {
  if (sessionId) {
    return env.DB.prepare(
      "SELECT token, session_id, run_id, box_id, company_id, recipient_chat_id, questions_json, question_set, status, revision, expires_at FROM sessions WHERE session_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).bind(sessionId).first();
  }
  return env.DB.prepare(
    "SELECT token, session_id, run_id, box_id, company_id, recipient_chat_id, questions_json, question_set, status, revision, expires_at FROM sessions WHERE run_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1"
  ).bind(runId).first();
}

async function loadOpenSession(env, token, allowComplete = false) {
  const session = await env.DB.prepare("SELECT token, session_id, run_id, box_id, question_set, questions_json, status, revision, invalidated_at, invalidated_reason, created_at, expires_at, completed_at FROM sessions WHERE token = ?").bind(token).first();
  if (!session) {
    // PRES-024: a revoked token is REJECTED (410), never treated as unknown.
    const revoked = await env.DB.prepare("SELECT token FROM revoked_tokens WHERE token = ?").bind(token).first();
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

async function answeredIdListForSession(env, sid) {
  const res = await env.DB.prepare("SELECT question_id FROM answers WHERE session_id = ? ORDER BY id ASC").bind(sid).all();
  const seen = new Set(); const out = [];
  for (const r of (res.results || [])) { if (!seen.has(r.question_id)) { seen.add(r.question_id); out.push(r.question_id); } }
  return out;
}

async function answeredValueMapForSession(env, sid) {
  const res = await env.DB.prepare("SELECT question_id, value FROM answers WHERE session_id = ? ORDER BY id ASC").bind(sid).all();
  const map = {}; for (const r of (res.results || [])) map[r.question_id] = r.value;
  return map;
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