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
//   POST /api/sessions/:token/complete            -> mark complete + enqueue the
//                                                    completion outbox     (capability)
//   GET  /api/sessions/:token/outbox              -> outbox status        (capability)
//   POST /api/intake                              -> store finished intake JSON (box auth)
//   GET  /api/intake?id=<session>                 -> fetch stored intake (box auth;
//                                                    the fetch IS the worker-accepted
//                                                    signal for the outbox)
//   GET  /api/intake/list?cursor=&limit=          -> paginated pending index (box auth)
//   POST /api/dept-start                          -> trigger presentation dept (box auth)
//
// PRES-005: the hosted UI is the canonical capability-token session UI. It
// never mints identity client-side, never POSTs /api/intake itself, and never
// sees the admin token. Completion assembles the validated intake SERVER-SIDE
// from the answers the server already validated (ordering + value shape at
// POST /answers time) into a durable completion outbox (outboxes/<token>.json,
// status queued) plus the intakes/<session>.json record the box bridge
// discovers via /api/intake/list. When the bridge fetches the intake, the
// outbox flips to worker_accepted — the only "accepted" the UI may show. A
// download from the UI is a backup labeled NOT SUBMITTED; download/deferred
// never renders as started/success.
//
// PRES-023 (session authority): mint/answer/complete are serialized through
// src/authority.js — per-session records with monotonic revisions written
// under R2 conditional writes (etag CAS), an idempotency key on answers and
// completes, a per-run active-session pointer (one open session per run), a
// completion outbox written by the same CAS winner that flips the status, and
// a paginated scoped pending-submission index (cursor + claim/lease + ack,
// bounded parallel metadata — no shared mutable queue JSON, no full-history
// rescan, no serial fetch of every object).
//
// Bindings: STORE (R2 bucket). Secret: INTAKE_ADMIN_TOKEN (box auth),
// COMMAND_CENTER_URL (CC board base URL), CC_HANDOFF_SECRET (PRES-007: scoped
// server-only HMAC over the ingest handoff body — no INTAKE_ADMIN_TOKEN
// fallback), CC_DEPT_START_TOKEN (optional bearer; no admin-token fallback).

import {
  randomToken, randomSessionId, sixDigitCode, nowSeconds, expiryFrom, isValidTokenShape,
  isValidSessionIdShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
  firstUnmetQuestionId,
  DEFAULT_TTL_DAYS,
} from "./lib.js";
import {
  opaqueIdError, mintRunId, mintIntakeSessionId, questionSchemaFingerprint,
} from "./tenant.js";
import {
  sessionKey, intakeIndexKey,
  newSessionRecord, loadSession, claimRunActiveSlot,
  idempotentOnce, answersValueMap, answersIdList,
  loadAnswersRecord, applyAnswerCAS, emptyAnswersRecord,
  appendOutboxEvent,
  indexIntakeRow, listPendingIntakes, claimIndexRow, ackIndexRow,
  casUpdate,
} from "./authority.js";

const SESSION_PREFIX = "sessions/";
const INTAKE_PREFIX = "intakes/";
const RUN_PREFIX = "runs/";
const OUTBOX_PREFIX = "outboxes/";
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
  if (parts.length === 4 && parts[3] === "complete" && method === "POST") return completeSession(request, env, token);
  if (parts.length === 4 && parts[3] === "outbox" && method === "GET") return outboxStatus(env, token);
  if (parts.length === 4 && parts[3] === "review" && method === "GET") return reviewAnswers(env, token);
  if (parts.length === 4 && parts[3] === "corrections" && method === "POST") return postCorrection(request, env, token);
  return errorResponse("not found", 404);
}

function tenantErrorResponse(errors) {
  return jsonResponse({ status: "error", error: "tenant identity invalid", details: errors }, 400);
}

/**
 * PRES-023 mint: the per-run active-session pointer is claimed under CAS
 * (create-if-not-exists semantics). Of N simultaneous mints for one run,
 * exactly one caller wins the pointer and creates a session; the losers read
 * the winner's pointer and replay its token — one active session, every
 * caller answered, deterministic. A pointer naming a dead session (expired/
 * complete/missing) is replaced by a fresh CAS winner (its session is
 * expired first), never by a read-modify-write race.
 */
async function mintSession(request, env) {
  const admin = env.INTAKE_ADMIN_TOKEN;
  if (!admin) return errorResponse("server not configured", 503);
  if (!authorized(request, admin)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }

  // PRES-009: durable tenant identity REQUIRED. The caller's run_id is
  // display-only; the storage run key is the minted opaque id. R2 run indexes
  // are keyed by the composite tenant tuple, never the human name.
  const companyErr = opaqueIdError("company_id", body.company_id);
  if (companyErr) return tenantErrorResponse([companyErr]);
  const installErr = opaqueIdError("installation_id", body.installation_id);
  if (installErr) return tenantErrorResponse([installErr]);
  const presErr = opaqueIdError("presentation_id", body.presentation_id);
  if (presErr) return tenantErrorResponse([presErr]);

  const payload = body.questions_payload;
  const check = validateQuestionsPayload(payload);
  if (!check.ok) return errorResponse("questions_payload invalid: " + check.error, 400);

  const created = nowSeconds();
  const companyId = body.company_id;
  const installationId = body.installation_id;
  const presentationId = body.presentation_id;

  // PRES-009: run indexes live under the tenant tuple; the DISPLAY run name
  // is the last segment (validated opaque-safe) so reuse resolves within the
  // tuple and two companies never share an index file. The minted run id is
  // per-mint and never the reuse key.
  const displayName = String(body.run_id || "").slice(0, 200) || "run";
  const schemaFp = questionSchemaFingerprint(payload);
  const runId = await sha256Hex(JSON.stringify([companyId, installationId, presentationId, displayName, schemaFp]));
  // Replay an existing live open session if the pointer names one.
  const bucket = env.STORE;
  const pointer = await bucket.get(runActivePointerKey(runId));
  if (pointer) {
    let ptr; try { ptr = JSON.parse(await pointer.text()); } catch { ptr = null; }
    if (ptr && ptr.token && Number(ptr.expires_at) > created && ptr.status === "open") {
      const ex = await loadSession(bucket, ptr.token);
      if (ex && ex.value && ex.value.status === "open" && Number(ex.value.expires_at) > created) {
        return jsonResponse({ status: "exists", token: ptr.token, capability_url: capabilityUrl(request, ptr.token), reused: true });
      }
    }
  }

  const newToken = randomToken();
  const sessionId = randomSessionId();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const confirmCode = body.want_confirm_code ? sixDigitCode() : null;
  const session = newSessionRecord({
    token: newToken, run_id: mintRunId(), box_id: String(body.box_id || ""), question_set: payload.question_set,
    questions_json: JSON.stringify(payload), confirm_code: confirmCode,
    created, expires,
  });

  Object.assign(session, { session_id: sessionId, recipient_chat_id: strOrNull(body.recipient_chat_id), run_slot_id: runId, company_id: companyId, installation_id: installationId, presentation_id: presentationId, display_run_id: displayName, intake_session_id: mintIntakeSessionId(), schema_fp: schemaFp });

  // Publish an immutable candidate before claiming so concurrent callers can
  // always read the winner. Unselected candidates never become active.
  const pub = await bucket.put(sessionKey(newToken), JSON.stringify(session), { onlyIf: { etagDoesNotMatch: "*" } });
  if (!pub) return errorResponse("session publication failed — retry", 503);
  const claimed = await claimRunActiveSlot(bucket, runId, newToken, expires);
  if (!claimed) return errorResponse("session slot busy — retry", 503);
  if (claimed.value && claimed.value.token !== newToken) {
    await bucket.delete(sessionKey(newToken));
    return jsonResponse({ status: "exists", token: claimed.value.token, capability_url: capabilityUrl(request, claimed.value.token), reused: true });
  }
  return jsonResponse({ status: "created", token: newToken, session_id: sessionId, capability_url: capabilityUrl(request, newToken), confirm_code: confirmCode, expires_at: expires, run_id: session.run_id, intake_session_id: session.intake_session_id, company_id: companyId, installation_id: installationId, presentation_id: presentationId }, 201);
}

function runActivePointerKey(runId) {
  // Local alias so this file never hardcodes the authority's key scheme twice.
  return "runs/" + String(runId).replace(/[^A-Za-z0-9._-]/g, "") + ".active.json";
}

async function expirePreviousSession(bucket, token) {
  await casUpdate(bucket, sessionKey(token), (cur) => {
    if (!cur || cur.status !== "open") return null;
    return { ...cur, status: "expired", revision: (cur.revision || 0) + 1 };
  });
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
    const obj = (await loadSession(env.STORE, g.token))?.value;
    if (!obj || obj.status !== "open") continue;
    obj.status = "renewed";
    await saveSession(env, obj);
    revocations.push(storePutJson(env, REVOKED_PREFIX + g.token + ".json", {
      token: g.token, session_id: sid, revoked_at: now, reason: "renewed",
    }));
  }
  await Promise.all(revocations);

  const fresh = {
    ...latest,
    token: newToken, session_id: sid, run_id: latest.run_id, box_id: latest.box_id,
    company_id: latest.company_id, recipient_chat_id: latest.recipient_chat_id,
    question_set: latest.question_set, questions_json: latest.questions_json,
    confirm_code: null, status: "open", revision: (Number(latest.revision) || 0) + 1,
    invalidated_at: null, invalidated_reason: null,
    created_at: now, expires_at: expires, completed_at: null,
  };
  await saveSession(env, fresh);
  if (fresh.run_slot_id) await casUpdate(env.STORE, runActivePointerKey(fresh.run_slot_id), cur => cur && cur.token === latest.token ? { token: newToken, expires_at: expires, status: "open" } : null);
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
  const answersRec = await loadAnswersRecord(env.STORE, session.session_id || token);
  const answeredIds = answersIdList(answersRec.value);
  const answeredValues = answersValueMap(answersRec.value);
  return jsonResponse({ status: session.status, run_id: session.run_id, company_id: session.company_id, installation_id: session.installation_id, presentation_id: session.presentation_id, intake_session_id: session.intake_session_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, requires_confirm_code: !!session.confirm_code, expires_at: session.expires_at });
}

/**
 * PRES-023 answer: idempotency key + CAS. The decide() closure runs against
 * the FRESH answers record on every CAS retry, so two concurrent tabs each
 * get a deterministic verdict (accepted / rejected-with-expected) and no
 * accepted answer is lost. A replayed idempotency key returns the recorded
 * result verbatim — never re-validated against a later state.
 */
async function postAnswer(request, env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  if (session.status === "complete") return errorResponse("session already complete", 409);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  if (session.confirm_code) { const supplied = String(body.confirm_code || ""); if (!timingSafeEqual(supplied, session.confirm_code)) return errorResponse("confirmation code required or incorrect", 401); }
  const questionId = body.question_id;
  const bucket = env.STORE;

  const memoKey = body.idempotency_key || body.idempotencyKey || null;
  if (memoKey) {
    // Read-only probe (null maker): never writes a placeholder — a placeholder
    // would shadow the winner's recorded result, and a replay would then fall
    // through to decide() AFTER the accepted write and wrongly return 409.
    const memo = await idempotentOnce(bucket, token, memoKey, () => null);
    if (memo && memo.replayed && memo.record) return jsonResponse(memo.record.body, memo.record.status || 200);
  }

  const decide = (record) => {
    const answeredRows = (record && record.answers) || [];
    const answeredIds = answeredRows.map((r) => r.question_id);
    const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
    const order = checkAnswerOrder(payload, answeredIds, questionId, answeredValues);
    if (!order.ok) return { accepted: false, order };
    const val = validateAnswerValue(order.question, body.value);
    if (!val.ok) return { accepted: false, val };
    const created = nowSeconds();
    const existing = answeredRows.find((r) => r.question_id === questionId);
    const nextRows = existing
      ? answeredRows.map((r) => (r.question_id === questionId ? { ...r, value: val.value, created_at: created } : r))
      : [...answeredRows, { id: answeredRows.length ? answeredRows[answeredRows.length - 1].id + 1 : 1, token, question_id: questionId, value: val.value, created_at: created }];
    const nowAnswered = answeredIds.includes(questionId) ? answeredIds : [...answeredIds, questionId];
    return {
      accepted: true,
      answers: nextRows,
      responseBody: { status: "accepted", question_id: questionId, value: val.value, revision: (record.revision || 0) + 1, progress: progress(payload, nowAnswered, answeredValues) },
    };
  };

  const res = await applyAnswerCAS(bucket, session.session_id || token, decide);
  if (!res) return errorResponse("answer conflict — retry", 503);

  if (!res.unchanged) {
    // Reconstruct the accepted body from the persisted record (revision is
    // the record's own, not a stale compute).
    const answersRec = res.value;
    const answeredRows = answersRec.answers;
    const answeredIds = answeredRows.map((r) => r.question_id);
    const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
    const acceptedBody = {
      status: "accepted", question_id: questionId,
      value: (answeredRows.find((r) => r.question_id === questionId) || {}).value,
      revision: answersRec.revision,
      progress: progress(payload, answeredIds, answeredValues),
    };
    if (memoKey) {
      await idempotentOnce(bucket, token, memoKey, () => ({ body: acceptedBody, status: 200 }));
    }
    return jsonResponse(acceptedBody);
  }

  // No write happened: replay the deterministic rejection from the fresh state.
  // res.value is null when no answers record exists yet (first-ever answer was
  // rejected) — treat that as the empty record, never a crash.
  const answersRec = res.value || emptyAnswersRecord();
  const answeredRows = (answersRec.answers) || [];
  const answeredIds = answeredRows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  const order = checkAnswerOrder(payload, answeredIds, questionId, answeredValues);
  if (!order.ok) return jsonResponse({ status: "rejected", error: order.error, expected: order.question || null }, 409);
  const val = validateAnswerValue(order.question, body.value);
  if (!val.ok) return jsonResponse({ status: "rejected", error: val.error, question_id: questionId }, 422);
  return jsonResponse({ status: "rejected", error: "conflict", question_id: questionId }, 409);
}

async function pollAnswers(request, env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const sid = session.session_id || token;
  const since = Number(new URL(request.url).searchParams.get("since") || 0);
  const answersRec = await loadAnswersRecord(env.STORE, session.session_id || token);
  const rows = (answersRec.value && answersRec.value.answers) || [];
  const fresh = answersSince(rows, since);
  const answeredIds = rows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of rows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: "ok", session_id: sid, revision: session.revision, session_status: session.status, cursor: rows.length ? Number(rows[rows.length - 1].id) : since, answers: fresh.map((r) => ({ id: Number(r.id), question_id: r.question_id, value: r.value, created_at: Number(r.created_at) })), progress: progress(payload, answeredIds, answeredValues) });
}

/**
 * POST /api/sessions/:token/complete — PRES-005 transactional completion,
 * PRES-023 serialized. CAS-serialized status flip with a monotonic revision;
 * idempotent (Idempotency-Key header or body key) — re-POST returns the same
 * durable outbox (never a second intake). The durable completion outbox is
 * appended by the SAME CAS winner that flips the status, deduped by revision
 * and idempotency key, so two tabs / retries / recovery converge on exactly
 * one event and one final revision. When required answers are still missing
 * the session stays open and NOTHING is queued (409 with the missing ids) —
 * zero false start.
 */
async function completeSession(request, env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const { session, payload } = row;
  const bucket = env.STORE;
  let body = {};
  try { body = await request.json(); } catch { body = {}; }
  const memoKey = request.headers.get("idempotency-key") || body.idempotency_key || body.idempotencyKey || null;

  // Read-only probe (null maker) — never a placeholder write (see postAnswer).
  const memo = memoKey ? await idempotentOnce(bucket, token, "complete-" + memoKey, () => null) : null;
  if (memo && memo.replayed && memo.record) return jsonResponse(memo.record.body, memo.record.status || 200);

  const existingOutbox = await loadOutbox(env, token);

  // Answers snapshot for gate + progress (read-only here; answers are closed
  // after completion by the status check in postAnswer).
  const answersRec = await loadAnswersRecord(bucket, session.session_id || token);
  const answeredRows = (answersRec.value && answersRec.value.answers) || [];
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
  if (requiredUnanswered.length) {
    return jsonResponse({ status: "blocked", missing: requiredUnanswered, progress: prog,
      outbox: { status: existingOutbox ? existingOutbox.status : "none", job_ref: existingOutbox ? existingOutbox.job_ref : "" } }, 409);
  }

  if (session.status === "complete") {
    // Already complete: replay the durable outbox — never a second intake.
    const completeBody = { status: "complete", run_id: session.run_id, revision: session.revision, progress: prog,
      outbox: outboxStatusPayload(existingOutbox || { status: "none", job_ref: "" }) };
    if (memoKey && !memo) await idempotentOnce(bucket, token, "complete-" + memoKey, () => ({ body: completeBody, status: 200 }));
    return jsonResponse(completeBody);
  }

  // The flip + outbox append happen in ONE CAS winner chain: flip the session
  // under CAS; only the winner enqueues the intake and writes the durable
  // completion outbox (the intake record is written FIRST, the outbox key
  // LAST — a torn write can only ever leave "not yet queued", never "queued
  // without an intake to fetch").
  let flipped = null;
  const flipRes = await casUpdate(bucket, sessionKey(token), (cur) => {
    if (!cur) return null;
    if (cur.status === "complete") { flipped = "already"; return null; }
    if (cur.status !== "open") return null;
    return { ...cur, status: "complete", completed_at: nowSeconds(), revision: (cur.revision || 0) + 1 };
  });
  if (!flipRes) return errorResponse("completion conflict — retry", 503);

  let revision;
  if (flipRes.unchanged && flipped === "already") {
    const cur = (await loadSession(bucket, token)).value;
    revision = cur.revision;
  } else {
    revision = flipRes.value.revision;
    // PRES-005: assemble the validated intake SERVER-SIDE from the answers
    // the server already validated. The assembly carries its own fail-closed
    // gate (assembleValidatedIntake) so an ungrounded deck type NEVER queues —
    // the caller gets action_needed instead.
    const session_id = session.intake_session_id;
    const built = assembleValidatedIntake(payload, answeredRows, session);
    let outbox;
    if (built.error) {
      outbox = {
        token, session_id, run_id: session.run_id, question_set: session.question_set,
        status: "action_needed", job_ref: "",
        file_name: "intake-sess-" + token + ".json",
        error: built.error,
        enqueued_at: nowSeconds(), fetched_at: null,
      };
    } else {
      outbox = {
        token, session_id, run_id: session.run_id, question_set: session.question_set,
        status: "queued", job_ref: "job-" + token.slice(0, 8) + "-" + nowSeconds().toString(36),
        file_name: "intake-sess-" + token + ".json",
        intake: built.intake,
        enqueued_at: nowSeconds(), fetched_at: null,
      };
      // One durable transaction (single-key R2 write): the outbox record AND the
      // intake record the box bridge discovers. The outbox key is written LAST
      // so a torn write can only ever leave "not yet queued" — never "queued"
      // without an intake to fetch.
      await storePutJson(env, intakeKey(built.intake), {
        session_token: token, session_id: outbox.session_id, intake_session_id: outbox.session_id, company_id: session.company_id, installation_id: session.installation_id, presentation_id: session.presentation_id, run_id: session.run_id, file_name: outbox.file_name,
        intake: outbox.intake, stored_at: nowSeconds(),
      });
      // PRES-023: the enqueued intake lands on the paginated pending index the
      // box bridge discovers — same row shape POST /api/intake produces.
      await indexIntakeRow(scopedIndexBucket(env.STORE, session.company_id, session.installation_id), outbox.session_id, outbox.file_name, nowSeconds());
    }
    await saveOutbox(env, outbox);
    // PRES-023: the same winner ALSO appends the revisioned completion-outbox
    // event under the CAS authority (deduped by revision + idempotency key) —
    // the cross-session event log stays one-per-revision.
    await appendOutboxEvent(bucket, token, {
      revision, token, run_id: session.run_id,
      idempotency_key: memoKey || null,
      completed_at: flipRes.value.completed_at,
      progress: prog,
      job_ref: outbox.job_ref || "",
      outbox_status: outbox.status,
    });
    // Retire the run's active-session pointer (CAS-safe): the slot is free
    // for the next mint on this run. If the pointer was already replaced by a
    // concurrent flow, leave it — that flow owns it now.
    await casUpdate(bucket, runActivePointerKey(session.run_id), (cur) => {
      if (!cur || cur.token !== token) return null;
      return { ...cur, status: "complete" };
    });
  }

  const finalOutbox = (await loadOutbox(env, token)) || existingOutbox;
  if (session.run_slot_id) await casUpdate(bucket, runActivePointerKey(session.run_slot_id), cur =>
    cur && cur.token === token ? { ...cur, status: "complete" } : null);
  const completeBody = { status: "complete", run_id: session.run_id, revision, progress: prog,
    outbox: outboxStatusPayload(finalOutbox) };
  if (memoKey && !memo) await idempotentOnce(bucket, token, "complete-" + memoKey, () => ({ body: completeBody, status: 200 }));
  return jsonResponse(completeBody);
}

// ---- PRES-005 server-side validated intake assembly -------------------------
// The intake record is built HERE from the answers the SERVER validated
// (ordering + value shape enforced at POST /answers) — never from a client
// POST. storeOn routing mirrors interview-app/pages questions + the bank's
// storeTarget so the box-side intake_writer.py / bridge consume it unchanged.

const ANSWER_STORE_TARGETS = {
  presentation_type: "pre_presentation_capture.PRESENTATION_TYPE",
  offer_name: "deck_brief.OFFER_NAME",
  named_methodology: "deck_brief.NAMED_METHODOLOGY",
  transformation_promise: "deck_brief.TRANSFORMATION_PROMISE",
  time_to_result: "deck_brief.TIME_TO_RESULT",
  audience: "deck_brief.AUDIENCE",
  cta_action: "deck_brief.CTA_ACTION",
  brand_primary: "deck_brief.BRAND_PRIMARY",
  image_links: "deck_brief.IMAGE_LINKS",
  tone: "deck_brief.TONE",
  final_price: "deck_brief.FINAL_PRICE",
  speech_speed_preference: "intake.speech_speed_preference",
  want_sales_checkout: "pre_presentation_capture.WANT_SALES_CHECKOUT",
  want_vsl_page: "pre_presentation_capture.WANT_VSL_PAGE",
  run_mode: "pre_presentation_capture.RUN_MODE",
  client_notes: "deck_brief.CLIENT_NOTES",
};

const DECK_TYPE_BY_PRESENTATION_TYPE = {
  from_scratch: { deck_type: "webinar", creation_mode: "from_scratch", presentation_mode: "general", audience_mode: "STANDARD" },
  content_personal: { deck_type: "webinar", creation_mode: "content_personal", presentation_mode: "one-person", audience_mode: "PERSONAL" },
  content_general: { deck_type: "webinar", creation_mode: "content_general", presentation_mode: "general", audience_mode: "GENERAL" },
  signature: { deck_type: "signature_presentation", creation_mode: "from_scratch", presentation_mode: "general", audience_mode: "STANDARD" },
};

/**
 * Assemble the dept-format intake from server-validated answers. FAIL-CLOSED:
 * a presentation_type answer that is missing or unrecognized returns
 * { error } and NOTHING is queued — the same grounding rule the box-side
 * intake_writer.py enforces, applied before the record ever leaves this
 * worker. Question prompts/labels come from the session's own questions
 * payload (the server-issued identity), never invented.
 */
export function assembleValidatedIntake(payload, answeredRows, session) {
  const brief = {};
  const pre = {};
  const intakeFlat = {};
  const answers = {};
  for (const r of answeredRows) {
    const qid = r.question_id;
    const q = (payload.questions || []).find((x) => x.id === qid);
    const storeOn = (q && (q.storeOn || ANSWER_STORE_TARGETS[qid])) || ANSWER_STORE_TARGETS[qid] || ("deck_brief." + qid.toUpperCase());
    const value = r.value;
    answers[qid] = value;
    const parts = String(storeOn).split(".");
    const section = parts.length > 1 ? parts[0] : "deck_brief";
    const key = parts.length > 1 ? parts[1] : qid.toUpperCase();
    if (section === "pre_presentation_capture") pre[key] = value;
    else if (section === "intake") intakeFlat[key] = value;
    else brief[key] = value;
  }

  const ptype = answers.presentation_type;
  const mapping = DECK_TYPE_BY_PRESENTATION_TYPE[ptype];
  if (!mapping) {
    return { error: "deck type not grounded: presentation_type answer " + JSON.stringify(ptype == null ? null : String(ptype)) + " is missing or unrecognized — nothing was queued. Ask the client to complete the type question and resend." };
  }

  const intake = {
    interview_confirmed: true,
    created_at: new Date().toISOString(),
    source: "presentation-interview-app",
    intake_session_id: session.intake_session_id,
    company_id: session.company_id, installation_id: session.installation_id, presentation_id: session.presentation_id,
    run_id: session.run_id,
    question_set: session.question_set || "standard",
    presentation_type: ptype,
    ...mapping,
    pre_presentation_capture: {
      REPRESENTATION_MIX: brief.AUDIENCE ? "100% of the stated audience" : "",
      AUDIENCE_COMPOSITION_NOTE: brief.AUDIENCE || "",
      GROUNDED_CONTENT: brief.OFFER_NAME || "",
      VISUAL_MIX: "mix",
      DARK_OK: false,
      HOOK_SEED: brief.TRANSFORMATION_PROMISE || "",
      ...pre,
    },
    deck_brief: brief,
    intake: intakeFlat,
    answers,
  };
  return { intake };
}

/**
 * GET /api/sessions/:token/outbox — capability-gated outbox status. The UI
 * polls this to show Queued vs Worker accepted vs Action needed. Status is
 * always real server state — never a client-side claim.
 */
async function outboxStatus(env, token) {
  const row = await loadOpenSession(env, token, true); if (row.error) return row.error;
  const outbox = await loadOutbox(env, token);
  if (!outbox) return jsonResponse({ status: "none", job_ref: "" });
  return jsonResponse(outboxStatusPayload(outbox));
}

function outboxStatusPayload(outbox) {
  return { status: outbox.status, job_ref: outbox.job_ref || "", session_id: outbox.session_id,
    enqueued_at: outbox.enqueued_at || null, worker_accepted_at: outbox.worker_accepted_at || null,
    error: outbox.error || "" };
}

function outboxKey(token) { return OUTBOX_PREFIX + token + ".json"; }

async function storePutJson(env, key, obj) {
  await env.STORE.put(key, JSON.stringify(obj));
}

async function storeGetJson(env, key) {
  const obj = await env.STORE.get(key);
  if (!obj) return null;
  const text = await obj.text();
  try { return JSON.parse(text); } catch { return null; }
}

async function loadOutbox(env, token) {
  return storeGetJson(env, outboxKey(token));
}

async function saveOutbox(env, outbox) {
  await storePutJson(env, outboxKey(outbox.token), outbox);
}

/**
 * Mark the outbox worker_accepted when the box bridge fetches the intake.
 * Called from fetchIntake(); best-effort — a race just means the next fetch
 * flips it.
 */
async function markOutboxAccepted(env, sessionId) {
  try {
    const token = sessionId.replace(/^sess-/, "");
    const outbox = await loadOutbox(env, token);
    if (!outbox || outbox.status === "worker_accepted") return;
    outbox.status = "worker_accepted";
    outbox.worker_accepted_at = nowSeconds();
    await saveOutbox(env, outbox);
  } catch { /* non-fatal */ }
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

/**
 * PRES-009: intake keys are the tenant tuple + the OPAQUE server-minted
 * intake_session_id, stored as its own R2 key segment. The old
 * strip-characters intakeKey() collapsed distinct ids ("a/b" and "ab", "x y"
 * and "xy") onto ONE storage key — cross-tenant overwrite. Invalid opaque ids
 * are rejected by the caller, never sanitized here.
 */
function intakeKey(intake) {
  return INTAKE_PREFIX + intake.company_id + "/" + intake.installation_id + "/" +
    intake.presentation_id + "/" + intake.run_id + "/" + intake.intake_session_id + ".json";
}

/** Legacy flat key (pre-tenant rows): opaque-id checked, no sanitizing. */
function legacyIntakeKey(sessionId) {
  if (!isValidTokenShapeLike(sessionId)) return null;
  return INTAKE_PREFIX + sessionId + ".json";
}

function isValidTokenShapeLike(id) {
  return typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/.test(id);
}

/**
 * POST /api/intake — store the assembled intake JSON so the box bridge can
 * poll it into the run dir (R2-backed). Same contract as the D1 worker.
 * Body: { file_name, intake }.
 *
 * F21 COMPLETENESS GATE (mirrors the repo worker): an intake missing any
 * REQUIRED deck_brief field or pre_presentation_capture.PRESENTATION_TYPE is
 * rejected with 422 naming the missing fields. Before this gate the server
 * accepted `{}` and the hollow intake flowed downstream into a doomed build.
 *
 * PRES-023: storing also appends a pending-submission index row (metadata in
 * the row, one per session) so discovery paginates a scoped index instead of
 * rescanning shared mutable queue JSON.
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
  // PRES-009: durable tenant identity REQUIRED — opaque ids, never sanitized.
  const tenantErrors = [];
  for (const field of ["company_id", "installation_id", "presentation_id", "run_id"]) {
    const err = opaqueIdError(field, intake[field]);
    if (err) tenantErrors.push(err);
  }
  const sidErr = opaqueIdError("intake_session_id", intake.intake_session_id);
  if (sidErr) tenantErrors.push(sidErr);
  if (tenantErrors.length) {
    return jsonResponse({ status: "rejected", error: "intake tenant identity invalid — mint a session and carry its tuple", details: tenantErrors }, 400);
  }
  const created = nowSeconds();
  const record = {
    session_id: intake.intake_session_id,
    intake_session_id: intake.intake_session_id,
    file_name: String(body.file_name || "intake.json").slice(0, 200),
    company_id: intake.company_id, installation_id: intake.installation_id,
    presentation_id: intake.presentation_id, run_id: intake.run_id,
    intake, stored_at: created,
  };
  await storePutJson(env, intakeKey(record), record);
  await indexIntakeRow(scopedIndexBucket(env.STORE, intake.company_id, intake.installation_id), record.session_id, record.file_name, created);
  return jsonResponse({ status: "stored", session_id: record.session_id, file_name: record.file_name, stored_at: created, company_id: intake.company_id }, 201);
}

/**
 * GET /api/intake?id=<session> — fetch a stored intake for the box bridge.
 * This fetch is the worker-accepted signal: it flips the session's completion
 * outbox to worker_accepted (best-effort, non-fatal on miss).
 */
async function fetchIntake(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  const params = new URL(request.url).searchParams;
  const id = params.get("id");
  if (!id) return errorResponse("id query param required", 400);
  // Scoped fetch (preferred): tuple + opaque id, exact-key read.
  const company = params.get("company_id") || "";
  const installation = params.get("installation_id") || "";
  const presentation = params.get("presentation_id") || "";
  const run = params.get("run_id") || "";
  if (!opaqueIdError("company_id", company) && !opaqueIdError("installation_id", installation)
    && !opaqueIdError("presentation_id", presentation) && !opaqueIdError("run_id", run)
    && !opaqueIdError("id", id)) {
    const scoped = await storeGetJson(env, INTAKE_PREFIX + company + "/" + installation + "/" + presentation + "/" + run + "/" + id + ".json");
    if (scoped) { await markOutboxAccepted(env, scoped.session_token || id); return jsonResponse(scoped, 200); }
    return errorResponse("intake not found", 404);
  }
  // PRES-009 QC repair (F3e): the bridge knows only the opaque intake_session_id
  // plus its OWN company/installation identity. With company+installation (no
  // presentation/run) scan THAT tenant's own prefix for a record whose stored
  // intake_session_id matches — bounded to the caller's own tenant rows, never
  // a global id lookup.
  if (company && installation
    && !opaqueIdError("company_id", company) && !opaqueIdError("installation_id", installation)
    && opaqueIdError("id", id) === null) {
    const prefix = INTAKE_PREFIX + company + "/" + installation + "/";
    const listed = await env.STORE.list({ prefix });
    for (const obj of (listed && listed.objects) || []) {
      const meta = await storeGetJson(env, obj.key);
      if (!meta) continue;
      if (meta.intake_session_id === id || meta.session_id === id) {
        await markOutboxAccepted(env, meta.session_token || id);
        return jsonResponse(meta, 200);
      }
    }
    return errorResponse("intake not found", 404);
  }
  // Legacy flat-key lookup: only valid opaque ids are ever probed (no
  // sanitizing — the PRES-009 lossy-collapse path is gone). Quarantined
  // legacy rows report their state instead of leaking across tenants.
  const key = legacyIntakeKey(id);
  if (!key) return jsonResponse({ status: "error", error: "invalid id: must be an opaque id (3-64 chars, [A-Za-z0-9._-], no '/', '\\', '..')" }, 400);
  const obj = await storeGetJson(env, key);
  if (!obj) return errorResponse("intake not found", 404);
  await markOutboxAccepted(env, id);
  return jsonResponse(obj, 200);
}

/**
 * GET /api/intake/list — enumerate PENDING stored intakes for the box-side
 * intake_bridge poll cron. PRES-023: paginated scoped index with an opaque
 * cursor (never one blind list call), claim/lease support, and ack-on-process
 * so processed sessions leave the index and polls never rescan history.
 *
 * Query params:
 *   cursor  opaque continuation token from a previous page
 *   limit   page size (default/bounded by PENDING_PAGE_LIMIT)
 *   claim   "1" to claim the returned page for <owner> (lease TTL applies)
 *   owner   lease owner id (required with claim=1)
 *   ack     session id to ack (remove from the index) — done BEFORE listing
 *
 * Returns { intakes: [{ session_id, file_name, stored_at }], truncated, cursor? }.
 */
async function listIntakes(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  const url = new URL(request.url);
  const company = url.searchParams.get("company_id") || "";
  const installation = url.searchParams.get("installation_id") || "";
  if ((company || installation) && (opaqueIdError("company_id", company) || opaqueIdError("installation_id", installation))) return errorResponse("both valid tenant ids required", 400);
  const bucket = scopedIndexBucket(env.STORE, company, installation);
  // Ack: repeatable `ack=<session_id>&stored_at=<ts>` pairs (and a bare ack
  // without stored_at, resolved against the index). getAll — a single
  // searchParams.get would drop every ack after the first.
  const ackIds = url.searchParams.getAll("ack").filter(Boolean);
  if (ackIds.length) {
    for (const ackId of ackIds) {
      const created0 = Number(url.searchParams.get("stored_at_" + ackId) || url.searchParams.get("stored_at") || 0);
      await ackIndexRow(bucket, intakeIndexKey(created0, ackId));
      // Bare ack (stored_at unknown): resolve this id against the pending
      // index — one bounded index scan for the id's actual row key.
      if (!created0) {
        const page = await listPendingIntakes(bucket, { limit: 1000 });
        for (const it of page.intakes) {
          if (it.session_id === ackId && it.key !== intakeIndexKey(created0, ackId)) await ackIndexRow(bucket, it.key);
        }
      }
    }
  }
  const claim = url.searchParams.get("claim") === "1";
  const owner = url.searchParams.get("owner") || null;
  const limitRaw = Number(url.searchParams.get("limit") || 0);
  const cursor = url.searchParams.get("cursor") || undefined;

  const page = await listPendingIntakes(bucket, {
    cursor,
    limit: Number.isFinite(limitRaw) && limitRaw > 0 ? Math.min(limitRaw, 1000) : undefined,
  });

  if (claim && owner) {
    // Bounded parallel claims (page-sized), each a single CAS on the row.
    const results = await Promise.all(page.intakes.map(async (it) => {
      const lease = await claimIndexRow(bucket, it.key, owner);
      return lease ? { ...it, lease_expires_at: lease.expires_at, claimed: true } : { ...it, claimed: false };
    }));
    const claimed = results.filter((r) => r.claimed);
    return jsonResponse({ intakes: claimed, truncated: page.truncated, ...(page.cursor ? { cursor: page.cursor } : {}), claimed: claimed.length, skipped: results.length - claimed.length }, 200);
  }

  return jsonResponse({
    intakes: page.intakes.map(({ session_id, file_name, stored_at, key }) => ({ session_id, file_name, stored_at, key })),
    truncated: page.truncated,
    ...(page.cursor ? { cursor: page.cursor } : {}),
  }, 200);
}

/**
 * POST /api/dept-start — trigger the presentation department.
 * Body: { intake_session_id, intake, run_dir, title, description }.
 * This is the NO-SHORTCUTS door: it creates the Command Center kanban card via
 * /api/tasks/ingest (the same endpoint the box-side cc_board.ingest_deck_task
 * uses), keyed by the intake session id. The deck can then only build through
 * presentation-canonical-entry.sh's governed gates.
 */
// PRES-007 (P0, W1 WF03): the worker → CC handoff is now the SAME raw-body
// HMAC contract cc_board.py uses — x-webhook-signature:
// HMAC-SHA256(CC_HANDOFF_SECRET, exactSerializedBodyBytes) hex, verified by
// src/lib/webhook-signature.ts's verifyWebhookSignature() in CC's ingest route
// (blackceo-command-center/src/app/api/tasks/ingest/route.ts:343–385). The
// legacy path sent Authorization: Bearer only, which production CC refuses
// (401) whenever WEBHOOK_SECRET is set, so every dept-start silently failed.
//
// Contract enforced here (identical semantics to the D1 worker; the outbox is
// an R2 JSON record instead of a D1 row):
//   1. PREFLIGHT — no CC_HANDOFF_SECRET => 503 with a precise missing-credential
//      message BEFORE any network call; the delivery intent is recorded
//      nonretryable in the outbox. Server-only scoped secret, never exposed to
//      the browser bundle. The INTAKE_ADMIN_TOKEN fallback is REMOVED.
//   2. SERIALIZE-THEN-SIGN — JSON.stringify() ONCE; those exact bytes are both
//      signed and sent, byte-for-byte parity with cc_board.py's _sign().
//   3. OUTBOX — every delivery intent is durably recorded in R2 under
//      outbox/<session>.json with retryable vs nonretryable disposition.
//   4. ACK BINDING — the CC acknowledgement must contain the expected task id
//      AND match the bound dest_box scope before the outbox marks fired.
//   5. ONE HANDOFF OWNER — a fired outbox record makes every later
//      /api/dept-start for the session an idempotent ack replay (no second
//      card); a mid-flight 'firing' record hands the retry back to the caller,
//      deduped by the REMOTE ingest idempotency key.
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
  // PRES-009: trigger-state writes key on the intake's OWN tenant tuple when
  // it carries one; a tenantless legacy intake keeps the legacy flat key.
  const tenantRecord = (!opaqueIdError("company_id", intake.company_id)
    && !opaqueIdError("installation_id", intake.installation_id)
    && !opaqueIdError("presentation_id", intake.presentation_id)
    && !opaqueIdError("run_id", intake.run_id)
    && !opaqueIdError("intake_session_id", session_id))
    ? { company_id: intake.company_id, installation_id: intake.installation_id,
        presentation_id: intake.presentation_id, run_id: intake.run_id,
        intake_session_id: session_id }
    : null;
  const key = tenantRecord ? intakeKey(tenantRecord) : legacyIntakeKey(session_id);
  if (!cc) {
    // No CC board wired on this deployment: record the trigger intent in R2 so
    // the box-side intake_bridge picks the run up (no shortcuts — the build is
    // still gated by canonical-entry).
    if (key) {
      const stored = await storeGetJson(env, key);
      await storePutJson(env, key, Object.assign({}, stored || {}, {
        session_id, file_name: (stored && stored.file_name) || "intake.json",
        dept_trigger: "deferred",
        dept_trigger_note: "COMMAND_CENTER_URL unset — box-side cc_board.ingest_deck_task will create the card",
        updated_at: nowSeconds(),
      }));
    }
    return jsonResponse({ status: "deferred", session_id, note: "COMMAND_CENTER_URL not set; box-side ingest_deck_task will create the card on pick-up" }, 202);
  }

  // PREFLIGHT (PRES-007 step 1): the scoped handoff secret is REQUIRED — no
  // INTAKE_ADMIN_TOKEN fallback. Record NONRETRYABLE; retrying without the
  // credential can never succeed.
  const secret = (env.CC_HANDOFF_SECRET || "").trim();
  if (!secret) {
    await outboxRecord(env, session_id, "failed_nonretryable", null,
      "CC_HANDOFF_SECRET unset — worker cannot sign the /api/tasks/ingest handoff. Set the scoped HMAC secret on the worker (wrangler secret put CC_HANDOFF_SECRET) matching the destination box's WEBHOOK_SECRET. NOT retried automatically.");
    return errorResponse("dept start not configured: CC_HANDOFF_SECRET is not set on this worker. The /api/tasks/ingest endpoint requires x-webhook-signature = HMAC-SHA256(CC_HANDOFF_SECRET, rawBody); provision the scoped secret (wrangler secret put CC_HANDOFF_SECRET) and retry.", 503);
  }

  // One handoff owner: a fired outbox record short-circuits the retry.
  const prior = await outboxGet(env, session_id);
  if (prior && prior.status === "fired" && prior.dept_task_id) {
    return jsonResponse({
      status: "fired", session_id, task_id: prior.dept_task_id,
      deduped: true, deduped_by: "outbox", dest_box: prior.dest_box || null,
    }, 200);
  }
  // A crash ANYWHERE between outbox-write and ack-write leaves 'firing' (or a
  // retryable failure) behind. Re-firing is SAFE in every one of those states
  // because the payload's idempotency key below is deterministic per
  // dest|company|run|title — the REMOTE ingest dedupes a repeat onto the first
  // card. Never a local blind duplicate; never a stuck 'firing' row.

  const source_ref = body.source_ref || intake.intake_session_id || session_id;
  // PRES-009 support: the destination binding travels INSIDE the signed bytes.
  const destBox = body.box_id || intake.box_id || (prior && prior.dest_box) || "";
  const destCompany = intake.company_id || intake.company || "";
  const idemInput = `${destBox}|${destCompany}|${source_ref}|${title}`;
  const idempotency_key = "pres-handoff:" + await sha256Hex(idemInput);
  const payload = {
    title, description,
    priority: body.priority || "medium",
    source: "presentation-interview-app",
    source_ref,
    department_slug: "presentations",
    persona: "Director of Presentations",
    external_session_id: session_id,
    idempotency_key,
    dest_box: destBox || undefined,
    dest_company: destCompany || undefined,
  };

  // SERIALIZE-THEN-SIGN: stringify ONCE; sign and send those exact bytes.
  const rawBody = JSON.stringify(payload);
  const signature = await hmacSha256Hex(secret, rawBody);

  if (prior === null) await outboxRecord(env, session_id, "firing", null, null, destBox);
  try {
    const resp = await fetch(cc.replace(/\/$/, "") + "/api/tasks/ingest", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(env.CC_DEPT_START_TOKEN ? { authorization: "Bearer " + env.CC_DEPT_START_TOKEN } : {}),
        "x-webhook-signature": signature,
      },
      body: rawBody,
    });
    const data = await resp.json().catch(() => ({}));
    // ACK BINDING: task id required AND the ack scope must match our binding.
    if (resp.ok && data.task_id) {
      const ackTaskId = String(data.task_id);
      const ackBox = data.dest_box === undefined || data.dest_box === null ? destBox : String(data.dest_box);
      const scopeOk = !destBox || !ackBox || ackBox === destBox;
      if (!scopeOk) {
        await outboxRecord(env, session_id, "failed_nonretryable", null,
          `CC ack company/box binding mismatch (sent dest_box=${destBox}, ack dest_box=${ackBox}) — card NOT bound to this run.`, destBox);
        return errorResponse("dept start refused: acknowledgement box/company binding mismatch — foreign destination", 502);
      }
      await outboxRecord(env, session_id, "fired", ackTaskId, null, destBox);
      if (key) {
        const stored = await storeGetJson(env, key);
        await storePutJson(env, key, Object.assign({}, stored || {}, {
          session_id, file_name: (stored && stored.file_name) || "intake.json",
          dept_trigger: "fired", dept_task_id: ackTaskId, updated_at: nowSeconds(),
        }));
      }
      return jsonResponse({ status: "fired", session_id, task_id: ackTaskId, deduped: !!data.deduped, dest_box: destBox || null }, 201);
    }
    const retryable = resp.status >= 500 || resp.status === 429;
    const detail = "dept start failed (HTTP " + resp.status + "): " + (data.error || data.detail || "unknown");
    await outboxRecord(env, session_id, retryable ? "failed_retryable" : "failed_nonretryable", null, detail, destBox);
    return errorResponse(detail, 502);
  } catch (err) {
    const detail = "dept start transport error: " + (err && err.message ? err.message : "network");
    await outboxRecord(env, session_id, "failed_retryable", null, detail, destBox);
    return errorResponse(detail, 502);
  }
}

// ---- handoff outbox (PRES-007, R2-backed) -----------------------------------
// Durable delivery intent per intake session at handoff-outbox/<session>.json.
// Same states and idempotency contract as the D1 worker's handoff_outbox
// table. Distinct prefix from the PRES-005 session completion outbox
// (outboxes/<token>.json) above: that one tracks session completion per
// capability token; this one tracks worker->CC delivery per intake session.

const HANDOFF_OUTBOX_PREFIX = "handoff-outbox/";
function handoffOutboxKey(sessionId) { return HANDOFF_OUTBOX_PREFIX + sessionId + ".json"; }

async function outboxGet(env, sessionId) {
  return storeGetJson(env, handoffOutboxKey(sessionId));
}

async function outboxRecord(env, sessionId, status, deptTaskId, lastError, destBox) { // PRES-007 handoff record (keyed under HANDOFF_OUTBOX_PREFIX)
  const existing = await outboxGet(env, sessionId);
  const record = Object.assign({}, existing || {}, {
    session_id: sessionId,
    status,
    dept_task_id: deptTaskId || (existing && existing.dept_task_id) || null,
    dest_box: destBox || (existing && existing.dest_box) || null,
    attempts: ((existing && existing.attempts) || 0) + 1,
    last_error: lastError !== undefined && lastError !== null ? lastError : (existing && existing.last_error) || null,
    updated_at: nowSeconds(),
  });
  try { await storePutJson(env, handoffOutboxKey(sessionId), record); } catch { /* observability, never fatal */ }
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256Hex(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ---- R2 storage helpers ----------------------------------------------------

/**
 * PRES-009: run indexes live under the composite tenant tuple. The human run
 * name is the LAST segment only — two companies reusing "summer-launch" (or
 * one company running two decks with the same name) get distinct index files.
 * The tuple segments are validated opaque ids before any key is built; a
 * traversal-shaped name can never reach storage.
 */
function tenantRunKeyPrefix(companyId, installationId, presentationId) {
  return RUN_PREFIX + companyId + "/" + installationId + "/" + presentationId + "/";
}

async function saveSession(env, session) { await storePutJson(env, sessionKey(session.token), session); }
async function loadAnswers(env, sid) { const rec = await loadAnswersRecord(env.STORE, sid); return rec.value?.answers || []; }
async function saveAnswers(env, sid, rows) { await applyAnswerCAS(env.STORE, sid, rec => ({ accepted: true, answers: rows })); }
async function loadRunIndex(env, runId) { const arr = await storeGetJson(env, "runs/" + runId + ".json"); return Array.isArray(arr) ? arr : []; }
async function saveRunIndex(env, runId, rows) { await storePutJson(env, "runs/" + runId + ".json", rows);
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
        if (!latest || (Number(s.revision) > Number(latest.revision) || (Number(s.revision) === Number(latest.revision) && Number(s.created_at) > Number(latest.created_at)))) latest = s;
      }
    }
    return latest;
  }
  const runRows = await loadRunIndex(env, runId);
  let latest = null;
  for (const r of runRows) {
    const s = (await loadSession(env.STORE, r.token))?.value;
    if (s && (!latest || (Number(s.revision) > Number(latest.revision) || (Number(s.revision) === Number(latest.revision) && Number(s.created_at) > Number(latest.created_at))))) latest = s;
  }
  return latest;
}

async function loadOpenSession(env, token, allowComplete = false) {
  const row = await loadSession(env.STORE, token);
  if (!row || !row.value) return { error: errorResponse("session not found", 404) };
  const session = row.value;
  if (session.status === "renewed") return { error: errorResponse("session token renewed — use renewed link", 410) };
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

// Keep the pending index inside the same tenant boundary as its intake records.
function scopedIndexBucket(bucket, company, installation) {
  const prefix = company && installation ? `tenant-index/${company}/${installation}/` : "";
  return {
    get: (key, ...args) => bucket.get(prefix + key, ...args),
    put: (key, ...args) => bucket.put(prefix + key, ...args),
    delete: (key) => bucket.delete(prefix + key),
    list: async (opts) => {
      const page = await bucket.list({ ...opts, prefix: prefix + opts.prefix });
      return { ...page, objects: page.objects.map(o => ({ ...o, key: o.key.slice(prefix.length) })) };
    },
  };
}
function strOrNull(v) {
  if (v === undefined || v === null) return null;
  const s = String(v).trim();
  return s ? s : null;
}
