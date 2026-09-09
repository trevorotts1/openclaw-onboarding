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
// PRES-024 — stable session identity vs renewable access-token grants:
//   POST /api/sessions/renew           -> admin re-mints an expired/lost token
//     bound to the SAME session/company/presentation run, revokes the previous
//     token, preserves questions schema + answers + revision, and resumes at
//     the exact first unmet active question (box auth).
//   GET  /api/sessions/:token/review   -> editable stored answer values
//     (capability).
//   POST /api/sessions/:token/corrections -> authenticated answer correction;
//     downstream invalidation when production already consumed a revision
//     (capability).
//   POST /api/admin/retry-link         -> record a retry-link delivery to the
//     session's BOUND recipient — a delivery naming any other recipient is
//     refused (box auth).
//
// Bindings (see wrangler.toml): DB (D1). Secret: INTAKE_ADMIN_TOKEN (box auth).

import {
  randomToken, randomSessionId, sixDigitCode, nowSeconds, expiryFrom, isValidTokenShape,
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
  if (method === "GET" && url.pathname === "/healthz") return jsonResponse({ status: "ok", service: "presentation-intake", ttl_days: DEFAULT_TTL_DAYS });
  if (parts[0] !== "api") return errorResponse("not found", 404);
  // PRES-024: renewal is addressed by the STABLE identity, never by a token.
  if (parts.length === 3 && parts[1] === "sessions" && parts[2] === "renew" && method === "POST") return renewSession(request, env);
  // PRES-024: retry-link delivery record (box auth, bound recipient).
  if (parts.length === 3 && parts[1] === "admin" && parts[2] === "retry-link" && method === "POST") return postRetryDelivery(request, env);
  if (parts[1] !== "sessions") return errorResponse("not found", 404);
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

// ---- mint -------------------------------------------------------------------

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
  const sessionId = randomSessionId();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const confirmCode = body.want_confirm_code ? sixDigitCode() : null;
  await env.DB.prepare(
    "INSERT INTO sessions (token, session_id, run_id, box_id, company_id, recipient_chat_id, question_set, questions_json, confirm_code, status, revision, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 0, ?, ?)"
  ).bind(newToken, sessionId, runId, boxId, strOrNull(body.company_id), strOrNull(body.recipient_chat_id), payload.question_set, JSON.stringify(payload), confirmCode, created, expires).run();
  return jsonResponse({ status: "created", token: newToken, session_id: sessionId, capability_url: capabilityUrl(request, newToken), confirm_code: confirmCode, expires_at: expires }, 201);
}

// ---- renew (PRES-024) ---------------------------------------------------------

/**
 * POST /api/sessions/renew  (box auth)
 * Body: { session_id | run_id, company_id, ttl_days?, box_id? }
 *
 * Separates the two things the pre-PRES-024 mint collapsed into one row:
 *   identity  — session_id; answers hang off it and NEVER move;
 *   grant     — token + expires_at; renewable, revocable, expiring.
 *
 * A renewal mints a NEW expiring token bound to the SAME session_id, the SAME
 * company (wrong company -> 403), and the SAME presentation run; it revokes
 * the previous token(s) (subsequent use -> 410, never silent); and it preserves
 * the questions schema + every answer + the revision counter, resuming at the
 * exact first unmet active question. Expiry of a token never erased the
 * session's data, so resuming loses nothing.
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

  // The LATEST grant of the stable session (or of the run) carries the
  // canonical questions + company + recipient bindings.
  const latest = await latestGrantFor(env, sessionId, runId);
  if (!latest) return errorResponse("session not found", 404);
  const sid = latest.session_id || latest.token;
  if (runId && latest.run_id !== runId) return errorResponse("session/run mismatch", 409);
  const now = nowSeconds();

  // Wrong-company renewals are refused: the renewal must bind the SAME
  // company that minted the session.
  const boundCompany = latest.company_id || "";
  const presentedCompany = strOrNull(body.company_id);
  if (boundCompany && presentedCompany !== boundCompany) {
    return errorResponse("company mismatch", 403);
  }

  // Already-completed sessions do not renew: the intake is final and lives in
  // the run dir. Reopening would mix revisions downstream.
  if (latest.status === "complete") return errorResponse("session already complete", 409);

  // The fresh grant, bound to the same identity/company/run. The revision
  // counter continues from the latest grant (preserved, never reset).
  const newToken = randomToken();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(now, ttlDays);
  const revisionAfter = (Number(latest.revision) || 0) + 1;
  // Atomic swap: revoke every still-open grant of this session, then insert
  // the new one. D1 has no interactive BEGIN; batch() is the atomic primitive.
  const openGrants = await env.DB.prepare(
    "SELECT token FROM sessions WHERE (session_id = ? OR token = ?) AND status = 'open'"
  ).bind(sid, latest.token).all();
  const stmts = [];
  for (const g of (openGrants.results || [])) {
    stmts.push(env.DB.prepare("UPDATE sessions SET status = 'renewed' WHERE token = ?").bind(g.token));
    stmts.push(env.DB.prepare("INSERT INTO revoked_tokens (token, session_id, revoked_at, reason) VALUES (?, ?, ?, 'renewed') ON CONFLICT (token) DO NOTHING").bind(g.token, sid, now));
  }
  stmts.push(env.DB.prepare(
    "INSERT INTO sessions (token, session_id, run_id, box_id, company_id, recipient_chat_id, question_set, questions_json, confirm_code, status, revision, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'open', ?, ?, ?)"
  ).bind(newToken, sid, latest.run_id, latest.box_id, latest.company_id, latest.recipient_chat_id, latest.question_set, latest.questions_json, revisionAfter, now, expires));
  try {
    await env.DB.batch(stmts);
  } catch (err) {
    return errorResponse("renewal failed", 500);
  }

  // Resume surface: the exact first unmet active question for the preserved
  // answer set.
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

// ---- read / answer / poll / complete (capability-scoped) ----------------------

async function getSession(env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  const answeredIds = await answeredIdListForSession(env, sid);
  const answeredValues = await answeredValueMapForSession(env, sid);
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
  const answeredIds = await answeredIdListForSession(env, sid);
  const answeredValues = await answeredValueMapForSession(env, sid);
  const order = checkAnswerOrder(payload, answeredIds, questionId, answeredValues);
  if (!order.ok) return jsonResponse({ status: "rejected", error: order.error, expected: order.question || null }, 409);
  const val = validateAnswerValue(order.question, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);
  const created = nowSeconds();
  // Answers hang off the STABLE session identity; the token column records the
  // grant that carried the write (audit) — a renewal keeps every prior answer
  // visible without any migration.
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
  if (session.status !== "complete") {
    // Mark every non-complete row of this stable session complete (the normal
    // single-grant path, plus a renewed-then-completed sibling).
    await env.DB.prepare("UPDATE sessions SET status = 'complete', completed_at = ? WHERE (token = ? OR session_id = ?) AND status IN ('open','renewed')").bind(nowSeconds(), token, sid).run();
  }
  return jsonResponse({ status: "complete", session_id: sid, revision: session.revision, run_id: session.run_id, progress: prog });
}

// ---- review / corrections (PRES-024) ------------------------------------------

/**
 * GET /api/sessions/:token/review — the stored, editable answer values keyed by
 * question id (the pre-PRES-024 getSession only exposed the answered ID list,
 * which made a review/correction UX impossible).
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
 * POST /api/sessions/:token/corrections — authenticated answer correction.
 * Body: { question_id, value, actor? }
 *
 * Contract:
 *   * only an already-answered question can be corrected (a NEW answer goes
 *     through the normal ordered answer flow);
 *   * every correction bumps the session revision by exactly one and records
 *     revision_before/revision_after in the corrections ledger, so two
 *     corrections never mix revisions;
 *   * when the session was already complete (production consumed a revision),
 *     the correction sets invalidated_at — downstream outputs built on the old
 *     revision require a rebuild, and the completed state is revoked so the
 *     session must be completed again.
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
 * POST /api/admin/retry-link (box auth) — record that a retry link was sent
 * for a session. FAIL-CLOSED on the bound recipient: a delivery naming any
 * chat id other than the session's bound recipient is refused (422), never
 * recorded. Body: { session_id | run_id, recipient_chat_id, channel?, delivered_at?, token? }
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

// ---- session loading -----------------------------------------------------------

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
  const session = await env.DB.prepare("SELECT token, session_id, run_id, box_id, question_set, questions_json, confirm_code, status, revision, invalidated_at, invalidated_reason, created_at, expires_at, completed_at FROM sessions WHERE token = ?").bind(token).first();
  if (!session) {
    // PRES-024: distinguish a revoked capability (renewed away) from a session
    // that never existed. A revoked token is REJECTED (410), never unknown.
    const revoked = await env.DB.prepare("SELECT token FROM revoked_tokens WHERE token = ?").bind(token).first();
    if (revoked) return { error: errorResponse("session token revoked — use the renewed link", 410) };
    return { error: errorResponse("session not found", 404) };
  }
  // A renewed-away grant is dead FIRST — the revocation, not the clock, is
  // what killed it (its expires_at is left untouched by the renewal).
  if (session.status === "renewed") return { error: errorResponse("session token renewed — use the renewed link", 410) };
  if (Number(session.expires_at) <= nowSeconds() && session.status !== "complete") {
    // Expiry does NOT erase the session: the data stays durable under the
    // stable session id; this grant is simply no longer usable.
    return { error: errorResponse("session expired", 410) };
  }
  if (session.status === "expired") return { error: errorResponse("session expired", 410) };
  if (session.status === "complete" && !allowComplete) return { error: errorResponse("session already complete", 409) };
  let payload; try { payload = JSON.parse(session.questions_json); } catch { return { error: errorResponse("corrupt session payload", 500) }; }
  return { session, payload };
}

// ---- answer reads, session-scoped (PRES-024) -------------------------------------

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