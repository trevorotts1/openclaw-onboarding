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
// COMMAND_CENTER_URL (CC board base URL), CC_HANDOFF_SECRET (PRES-007: scoped
// server-only HMAC over the ingest handoff body — no INTAKE_ADMIN_TOKEN
// fallback), CC_DEPT_START_TOKEN (optional bearer; no admin-token fallback).

import {
  randomToken, sixDigitCode, nowSeconds, expiryFrom, isValidTokenShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
  DEFAULT_TTL_DAYS,
} from "./lib.js";
import {
  opaqueIdError, mintRunId, mintIntakeSessionId, questionSchemaFingerprint,
} from "./tenant.js";

const SESSION_PREFIX = "sessions/";
const ANSWER_PREFIX = "answers/";
const INTAKE_PREFIX = "intakes/";
const RUN_PREFIX = "runs/";

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

function tenantErrorResponse(errors) {
  return jsonResponse({ status: "error", error: "tenant identity invalid", details: errors }, 400);
}

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
  const runRows = await loadRunIndex(env, companyId, installationId, presentationId, displayName);
  const schemaFp = questionSchemaFingerprint(payload);
  const existing = runRows.find((r) => r.status === "open" && Number(r.expires_at) > created);
  if (existing) {
    const ex = await loadSession(env, existing.token);
    if (ex && ex.schema_fp === schemaFp) {
      return jsonResponse({ status: "exists", token: existing.token, capability_url: capabilityUrl(request, existing.token), reused: true });
    }
    // Incompatible question schema on the open session: mint a distinct
    // session (never reuse across schemas).
  }

  const newToken = randomToken();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const confirmCode = body.want_confirm_code ? sixDigitCode() : null;
  const storageRunId = mintRunId();
  const intakeSessionId = mintIntakeSessionId();
  const session = {
    token: newToken, run_id: storageRunId, display_run_id: displayName,
    box_id: String(body.box_id || "").slice(0, 200),
    company_id: companyId, installation_id: installationId, presentation_id: presentationId,
    intake_session_id: intakeSessionId, schema_fp: schemaFp,
    question_set: payload.question_set,
    questions_json: JSON.stringify(payload), confirm_code: confirmCode, status: "open",
    created_at: created, expires_at: expires, completed_at: null,
  };
  await saveSession(env, session);
  const updatedRun = runRows.filter((r) => !(r.status === "open" && Number(r.expires_at) <= created));
  updatedRun.push({ token: newToken, status: "open", expires_at: expires, run_id: storageRunId, schema_fp: schemaFp });
  await saveRunIndex(env, companyId, installationId, presentationId, displayName, updatedRun);
  return jsonResponse({
    status: "created", token: newToken, capability_url: capabilityUrl(request, newToken),
    confirm_code: confirmCode, run_id: storageRunId, intake_session_id: intakeSessionId,
    company_id: companyId, installation_id: installationId, presentation_id: presentationId,
    expires_at: expires,
  }, 201);
}

async function getSession(env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  const answeredRows = await loadAnswers(env, token);
  const answeredIds = answeredRows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of answeredRows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: session.status, run_id: session.run_id, company_id: session.company_id, installation_id: session.installation_id, presentation_id: session.presentation_id, intake_session_id: session.intake_session_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, requires_confirm_code: !!session.confirm_code, expires_at: session.expires_at });
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
    const runRows = await loadRunIndex(env, session.company_id, session.installation_id, session.presentation_id, session.display_run_id);
    const updatedRun = runRows.map((r) => (r.token === token ? { ...r, status: "complete" } : r));
    await saveRunIndex(env, session.company_id, session.installation_id, session.presentation_id, session.display_run_id, updatedRun);
  }
  return jsonResponse({ status: "complete", run_id: session.run_id, progress: prog });
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
  return jsonResponse({ status: "stored", session_id: record.session_id, file_name: record.file_name, stored_at: created, company_id: intake.company_id }, 201);
}

/**
 * GET /api/intake?id=<session> — fetch a stored intake for the box bridge.
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
    if (scoped) return jsonResponse(scoped, 200);
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
  // PRES-009: list is SCOPED to an installation/company when the caller passes
  // them; unscoped legacy-admin callers get their own flat-key rows only.
  // Tenant-tuple rows surface under their tuple prefix, never globally mixed.
  const params = new URL(request.url).searchParams;
  const company = params.get("company_id") || "";
  const installation = params.get("installation_id") || "";
  const prefixParts = [];
  if (company && !opaqueIdError("company_id", company)) prefixParts.push(company);
  if (installation && !opaqueIdError("installation_id", installation)) prefixParts.push(installation);
  let prefix = INTAKE_PREFIX;
  let scopedList = false;
  if (prefixParts.length === 2) {
    prefix = INTAKE_PREFIX + prefixParts[0] + "/" + prefixParts[1] + "/";
    scopedList = true;
  } else if (prefixParts.length > 0) {
    return jsonResponse({ status: "error", error: "list scoping requires both company_id and installation_id" }, 400);
  }
  const listed = await env.STORE.list({ prefix });
  const intakes = [];
  for (const obj of (listed && listed.objects) || []) {
    const name = obj.key;
    const meta = await storeGetJson(env, name);
    if (!meta) continue;
    let sessionId;
    if (scopedList) {
      sessionId = meta.session_id;
    } else {
      // PRES-009 QC repair (F3a): an UNSCOPED legacy-admin caller sees ONLY
      // single-segment legacy flat keys. The old unscoped branch listed the
      // whole INTAKE_PREFIX including tenant-tuple keys and derived
      // session_id from the key PATH — a "compA/instA/.../isn-..." composite
      // the bridge's opaque-id validator then rejects, stalling every tuple
      // intake on a mixed deployment (and naming foreign tenants to a caller
      // that never proved one). Tuple rows surface ONLY to scoped callers.
      if (name.slice(INTAKE_PREFIX.length).includes("/")) continue;
      sessionId = name.slice(INTAKE_PREFIX.length).replace(/\.json$/, "");
    }
    if (!sessionId) continue;
    intakes.push({
      session_id: sessionId,
      file_name: meta.file_name || null,
      stored_at: meta.stored_at != null ? Number(meta.stored_at) : null,
      company_id: meta.company_id || null,
      key: name,
    });
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
// Durable delivery intent per intake session at outbox/<session>.json. Same
// states and idempotency contract as the D1 worker's handoff_outbox table.

const OUTBOX_PREFIX = "outbox/";
function outboxKey(sessionId) { return OUTBOX_PREFIX + sessionId + ".json"; }

async function outboxGet(env, sessionId) {
  return storeGetJson(env, outboxKey(sessionId));
}

async function outboxRecord(env, sessionId, status, deptTaskId, lastError, destBox) {
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
  try { await storePutJson(env, outboxKey(sessionId), record); } catch { /* observability, never fatal */ }
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

async function loadRunIndex(env, companyId, installationId, presentationId, runName) {
  for (const v of [companyId, installationId, presentationId, runName]) {
    if (isValidTokenShapeLike(v)) continue;
    return []; // reject traversal-shaped tuple members — nothing to load
  }
  const arr = await storeGetJson(env, tenantRunKeyPrefix(companyId, installationId, presentationId) + runName + ".json");
  return Array.isArray(arr) ? arr : [];
}

async function saveRunIndex(env, companyId, installationId, presentationId, runName, rows) {
  for (const v of [companyId, installationId, presentationId, runName]) {
    if (!isValidTokenShapeLike(v)) return; // never persist a traversal-shaped key
  }
  await storePutJson(env, tenantRunKeyPrefix(companyId, installationId, presentationId) + runName + ".json", rows);
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
