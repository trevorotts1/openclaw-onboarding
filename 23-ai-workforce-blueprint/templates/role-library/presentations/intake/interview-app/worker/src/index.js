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
// COMMAND_CENTER_URL (CC board base URL), CC_HANDOFF_SECRET (PRES-007: scoped
// server-only HMAC over the ingest handoff body — no INTAKE_ADMIN_TOKEN
// fallback), CC_DEPT_START_TOKEN (optional bearer; no admin-token fallback).

import {
  randomToken, randomSessionId, nowSeconds, expiryFrom, isValidTokenShape,
  isValidSessionIdShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
  firstUnmetQuestionId,
  DEFAULT_TTL_DAYS,
} from "./lib.js";
import {
  opaqueIdError, mintRunId, mintIntakeSessionId, questionSchemaFingerprint,
} from "./tenant.js";

// PRES-009 — idempotent additive D1 migration for tenant identity. Safe to
// run on cold start; each statement is skipped when already applied.
export const SCHEMA_MIGRATIONS = [
  "ALTER TABLE sessions ADD COLUMN display_name TEXT",
  "ALTER TABLE sessions ADD COLUMN company_id TEXT",
  "ALTER TABLE sessions ADD COLUMN installation_id TEXT",
  "ALTER TABLE sessions ADD COLUMN presentation_id TEXT",
  "ALTER TABLE sessions ADD COLUMN intake_session_id TEXT",
  "ALTER TABLE sessions ADD COLUMN schema_fp TEXT",
  "ALTER TABLE sessions ADD COLUMN tenant_state TEXT DEFAULT 'active'",
  "ALTER TABLE sessions ADD COLUMN quarantine_reason TEXT",
  "ALTER TABLE intakes ADD COLUMN company_id TEXT",
  "ALTER TABLE intakes ADD COLUMN installation_id TEXT",
  "ALTER TABLE intakes ADD COLUMN presentation_id TEXT",
  "ALTER TABLE intakes ADD COLUMN run_id TEXT",
  "ALTER TABLE intakes ADD COLUMN tenant_state TEXT DEFAULT 'active'",
  "ALTER TABLE intakes ADD COLUMN quarantine_reason TEXT",
  "ALTER TABLE intakes ADD COLUMN quarantine_remediation TEXT",
  "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_open_tenant_run ON sessions (company_id, installation_id, presentation_id, run_id) WHERE status = 'open' AND tenant_state = 'active'",
  "CREATE UNIQUE INDEX IF NOT EXISTS idx_intakes_tenant_session ON intakes (company_id, intake_session_id) WHERE tenant_state = 'active'",
];

let migrated = false;
async function ensureSchema(env) {
  if (migrated || !env.DB) return;
  for (const stmt of SCHEMA_MIGRATIONS) {
    try { await env.DB.exec(stmt); } catch { /* already applied */ }
  }
  migrated = true;
  // PRES-009 QC repair (F4): the legacy migration ran nowhere in production —
  // runLegacyMigration was exported but never invoked by any route, so real
  // legacy D1 databases kept cross-box run collisions active forever. Run it
  // once per cold start here (idempotent: the double-NULL predicate matches
  // only un-migrated legacy rows, which shrink to zero; never touches done or
  // already-quarantined rows). Never fatal — a migration failure must not take
  // the intake API down; the next cold start retries.
  try { await runLegacyMigration(env); } catch { /* retried next cold start */ }
}

/**
 * PRES-009 legacy migration. Pure helper in tenant.js (planLegacySessionMigration
 * / planLegacyIntakeMigration) computes the plan; this applies it:
 *   - a legacy run_id used by exactly ONE box_id and a valid opaque box id is
 *     UNAMBIGUOUS: backfill installation_id from the one box that minted it.
 *   - a run_id seen under MORE THAN ONE box is the PRES-009 collision itself:
 *     quarantine with an explicit reason, never guess.
 *   - a legacy intake row quarantined unless its own stored record carries all
 *     four tenant ids.
 */
export async function runLegacyMigration(env) {
  if (!env.DB) return { session_backfills: [], session_quarantined: [], intake_backfills: [], intake_quarantined: [] };
  await ensureSchema(env);
  // PRES-009 repair (QC): legacy rows are detected by MISSING tenant identity
  // (company_id IS NULL AND installation_id IS NULL), not by tenant_state.
  // ADD COLUMN ... DEFAULT 'active' backfills pre-existing rows with 'active',
  // so the old `tenant_state IS NULL` predicate matched zero rows on a real
  // legacy DB and the migration never ran. New rows always carry company_id,
  // backfilled rows carry installation_id, so the double-NULL marks exactly
  // the un-migrated legacy set; already-quarantined rows are never touched.
  const sessionRes = await env.DB.prepare(
    "SELECT token, run_id, box_id, company_id, tenant_state FROM sessions WHERE company_id IS NULL AND installation_id IS NULL AND (tenant_state IS NULL OR tenant_state = '' OR tenant_state = 'active')",
  ).all();
  const sessionRows = (sessionRes && sessionRes.results) || [];
  const byRun = new Map();
  for (const r of sessionRows) {
    const k = String(r.run_id);
    if (!byRun.has(k)) byRun.set(k, new Set());
    byRun.get(k).add(String(r.box_id));
  }
  const sessionBackfills = [];
  let sessionQuarantined = 0;
  for (const r of sessionRows) {
    const boxes = byRun.get(String(r.run_id));
    if (boxes && boxes.size === 1) {
      const box = [...boxes][0];
      const err = opaqueIdError("installation_id", box);
      if (!err) {
        await env.DB.prepare(
          "UPDATE sessions SET installation_id = ?, tenant_state = 'active' WHERE token = ? AND (tenant_state IS NULL OR tenant_state = '' OR tenant_state = 'active')",
        ).bind(box, r.token).run();
        sessionBackfills.push({ token: r.token, installation_id: box });
        continue;
      }
    }
    await env.DB.prepare(
      "UPDATE sessions SET tenant_state = 'quarantined', quarantine_reason = 'ambiguous_legacy_run_reused_across_boxes' WHERE token = ? AND (tenant_state IS NULL OR tenant_state = '' OR tenant_state = 'active')",
    ).bind(r.token).run();
    sessionQuarantined += 1;
  }

  const intakeRes = await env.DB.prepare(
    "SELECT session_id, intake_json FROM intakes WHERE company_id IS NULL AND (tenant_state IS NULL OR tenant_state = '' OR tenant_state = 'active')",
  ).all();
  const intakeRows = (intakeRes && intakeRes.results) || [];
  const intakeBackfills = [];
  const intakeQuarantined = [];
  for (const r of intakeRows) {
    let intake = null;
    try { intake = JSON.parse(r.intake_json || "null"); } catch { intake = null; }
    const c = intake && intake.company_id, i = intake && intake.installation_id,
          p = intake && intake.presentation_id, run = intake && intake.run_id;
    if (!opaqueIdError("company_id", c) && !opaqueIdError("installation_id", i)
      && !opaqueIdError("presentation_id", p) && !opaqueIdError("run_id", run)) {
      await env.DB.prepare(
        "UPDATE intakes SET company_id = ?, installation_id = ?, presentation_id = ?, run_id = ?, tenant_state = 'active' WHERE session_id = ? AND (tenant_state IS NULL OR tenant_state = '' OR tenant_state = 'active')",
      ).bind(c, i, p, run, r.session_id).run();
      intakeBackfills.push({ session_id: r.session_id, company_id: c });
    } else {
      await env.DB.prepare(
        "UPDATE intakes SET tenant_state = 'quarantined', quarantine_reason = 'ambiguous_legacy_owner_unknown', quarantine_remediation = ? WHERE session_id = ? AND (tenant_state IS NULL OR tenant_state = '' OR tenant_state = 'active')",
      ).bind(
        "Re-store the intake with company_id/installation_id/presentation_id/run_id (mint a session first), or delete the row explicitly if it is junk. The worker never guesses an owner.",
        r.session_id,
      ).run();
      intakeQuarantined.push({ session_id: r.session_id, reason: "ambiguous_legacy_owner_unknown" });
    }
  }
  return { session_backfills: sessionBackfills, session_quarantined: sessionQuarantined, intake_backfills: intakeBackfills, intake_quarantined: intakeQuarantined };
}
// PRES-006: the completeness gate and the legacy migration are GENERATED from
// the one canonical field-path contract (../schema/intake_fields.js). The
// hand-copied REQUIRED_BRIEF_FIELDS array this worker used to carry is gone —
// it drifted from the form and rejected every complete payload (the upsell
// flags are stored canonically under pre_presentation_capture.*, not
// deck_brief). validateAndMigrate distinguishes a real "no" answer from a
// missing one and refuses contradictory legacy records with an explanation.
import { validateAndMigrate } from "../../schema/intake_contract.js";

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
  await ensureSchema(env);
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

function tenantErrorResponse(errors) {
  return jsonResponse({ status: "error", error: "tenant identity invalid", details: errors }, 400);
}

async function mintSession(request, env) {
  const admin = env.INTAKE_ADMIN_TOKEN;
  if (!admin) return errorResponse("server not configured", 503);
  if (!authorized(request, admin)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }

  // PRES-009: durable tenant identity is REQUIRED. The caller's run_id is
  // display-only; the storage key run_id is minted here. Two companies reusing
  // one human run name get distinct tokens/data; one company launching two
  // simultaneous decks never collapses onto one session.
  const companyErr = opaqueIdError("company_id", body.company_id);
  if (companyErr) return tenantErrorResponse([companyErr]);
  const installErr = opaqueIdError("installation_id", body.installation_id);
  if (installErr) return tenantErrorResponse([installErr]);
  const presErr = opaqueIdError("presentation_id", body.presentation_id);
  if (presErr) return tenantErrorResponse([presErr]);
  // PRES-009 QC repair (F2): box_id is the legacy-migration attribution source
  // (runLegacyMigration backfills installation_id FROM box_id). It must be the
  // caller's real box id, opaque-validated — never the display run name. The
  // pre-repair INSERT bound displayName into box_id, which misattributed every
  // minted row and broke the migration plan's single-box detection.
  const boxErr = opaqueIdError("box_id", body.box_id);
  if (boxErr) return tenantErrorResponse([boxErr]);

  const payload = body.questions_payload;
  const check = validateQuestionsPayload(payload);
  if (!check.ok) return errorResponse("questions_payload invalid: " + check.error, 400);

  const created = nowSeconds();
  const companyId = body.company_id;
  const installationId = body.installation_id;
  const presentationId = body.presentation_id;
  const boxId = body.box_id;

  // Composite reuse: exact tenant tuple + display run name + compatible
  // question schema + open. The caller's human run_id identifies the run
  // WITHIN the tuple (display_name column); the minted run id differs per
  // mint and must never be the reuse key.
  const displayName = String(body.display_run_id || body.run_id || "").slice(0, 200) || null;
  const schemaFp = questionSchemaFingerprint(payload);
  const existing = await env.DB.prepare(
    "SELECT token, expires_at, schema_fp FROM sessions WHERE company_id = ? AND installation_id = ? AND presentation_id = ? AND display_name = ? AND status = 'open' AND (tenant_state IS NULL OR tenant_state = 'active') ORDER BY created_at DESC LIMIT 1",
  ).bind(companyId, installationId, presentationId, displayName).first();
  if (existing && Number(existing.expires_at) > created && existing.schema_fp === schemaFp) {
    return jsonResponse({ status: "exists", token: existing.token, capability_url: capabilityUrl(request, existing.token), reused: true });
  }
  if (existing && Number(existing.expires_at) <= created) {
    await env.DB.prepare("UPDATE sessions SET status = 'expired' WHERE token = ? AND status = 'open'").bind(existing.token).run();
  }

  const newToken = randomToken();
  const sessionId = randomSessionId();
  const storageRunId = mintRunId();
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  await env.DB.prepare(
    "INSERT INTO sessions (token, session_id, run_id, box_id, company_id, recipient_chat_id, display_name, installation_id, presentation_id, intake_session_id, schema_fp, question_set, questions_json, status, revision, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 0, ?, ?)"
  ).bind(newToken, sessionId, storageRunId, boxId, companyId, strOrNull(body.recipient_chat_id), displayName, installationId, presentationId, sessionId, schemaFp, payload.question_set, JSON.stringify(payload), created, expires).run();
  return jsonResponse({ status: "created", token: newToken, session_id: sessionId, run_id: storageRunId, intake_session_id: sessionId, company_id: companyId, installation_id: installationId, presentation_id: presentationId, capability_url: capabilityUrl(request, newToken), expires_at: expires }, 201);
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
    "INSERT INTO sessions (token, session_id, run_id, box_id, company_id, recipient_chat_id, display_name, installation_id, presentation_id, intake_session_id, schema_fp, question_set, questions_json, status, revision, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)"
  ).bind(newToken, sid, latest.run_id, latest.box_id, latest.company_id, latest.recipient_chat_id, latest.display_name, latest.installation_id, latest.presentation_id, latest.intake_session_id, latest.schema_fp, latest.question_set, latest.questions_json, revisionAfter, now, expires));
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
  return jsonResponse({ status: session.status, session_id: sid, revision: session.revision, run_id: session.run_id, company_id: session.company_id, installation_id: session.installation_id, presentation_id: session.presentation_id, intake_session_id: session.intake_session_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, expires_at: session.expires_at });
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
 * PRES-006 SCHEMA-DRIVEN COMPLETENESS GATE: the required set comes from the
 * one canonical field-path contract (schema/intake_fields.js via
 * schema/intake_contract.js) — no independent REQUIRED_BRIEF_FIELDS copy that
 * can drift. A "no"/"false" answer is a REAL answer and never counts as
 * missing; only undefined/null/blank is missing. A legacy (pre-contract)
 * record is MIGRATED forward first; a record carrying contradictory legacy
 * values is REFUSED (422) with the migration explanation naming both values.
 * The F21 fail-closed posture is unchanged: an incomplete intake is rejected
 * naming the missing fields.
 */
async function storeIntake(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
  const intake = body.intake;
  if (!intake || typeof intake !== "object") return errorResponse("intake object required", 400);
  const result = validateAndMigrate(intake);
  if (!result.ok) {
    if (result.conflicts) {
      return jsonResponse({
        status: "rejected",
        error: "intake rejected — " + (result.note || "contradictory legacy values"),
        migration_conflicts: result.conflicts,
        migration_note: result.note,
      }, 422);
    }
    return jsonResponse({ status: "rejected", error: result.note || "intake incomplete — required fields missing or empty", missing: result.missing }, 422);
  }
  // PRES-009: durable tenant identity REQUIRED on every intake. The old
  // session_id-alone primary key let one company's write shadow another's
  // when the two shared a session id; every row now carries its tenant tuple.
  const tenantErrors = [];
  for (const field of ["company_id", "installation_id", "presentation_id", "run_id"]) {
    const err = opaqueIdError(field, intake[field]);
    if (err) tenantErrors.push(err);
  }
  if (tenantErrors.length) {
    return jsonResponse({ status: "rejected", error: "intake tenant identity invalid — mint a session and carry its tuple", details: tenantErrors }, 400);
  }
  // The opaque intake_session_id is minted by the session API; a caller-
  // supplied id is rejected when it is not a valid opaque id (never sanitized).
  let session_id = intake.intake_session_id;
  const sidErr = opaqueIdError("intake_session_id", session_id);
  if (sidErr) return jsonResponse({ status: "rejected", error: "intake tenant identity invalid", details: [sidErr] }, 400);
  const created = nowSeconds();
  if (env.DB) {
    // PRES-009 QC repair (F3d): session_id is the table PRIMARY KEY, so the old
    // ON CONFLICT (session_id) DO UPDATE let a second company storing the same
    // client-chosen (valid-shaped) id OVERWRITE the first company's row — a
    // cross-tenant clobber. Never overwrite another tenant's row: an existing
    // row with the same session_id but a DIFFERENT company_id is a hard 409;
    // the same company re-storing its own session id updates its own row.
    const existing = await env.DB.prepare(
      "SELECT company_id FROM intakes WHERE session_id = ?",
    ).bind(session_id).first();
    if (existing && existing.company_id && existing.company_id !== intake.company_id) {
      return jsonResponse({ status: "rejected", error: "intake session id already belongs to another company — mint a session to get a distinct intake_session_id" }, 409);
    }
    await env.DB.prepare(
      "INSERT INTO intakes (session_id, file_name, intake_json, company_id, installation_id, presentation_id, run_id, tenant_state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?) " +
      "ON CONFLICT (session_id) DO UPDATE SET intake_json = excluded.intake_json, company_id = excluded.company_id, installation_id = excluded.installation_id, presentation_id = excluded.presentation_id, run_id = excluded.run_id, created_at = excluded.created_at " +
      "WHERE intakes.company_id IS NULL OR intakes.company_id = excluded.company_id",
    ).bind(session_id, String(body.file_name || "intake.json").slice(0, 200), JSON.stringify(result.intake), intake.company_id, intake.installation_id, intake.presentation_id, intake.run_id, created).run();
  }
  return jsonResponse({ status: "stored", session_id, file_name: body.file_name || "intake.json", stored_at: created, company_id: intake.company_id, schema_version: result.intake.schema_version, migrated: result.migrated || [] }, 201);
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
  const params = new URL(request.url).searchParams;
  const id = params.get("id");
  if (!id) return errorResponse("id query param required", 400);
  const sidErr = opaqueIdError("id", id);
  if (sidErr) return jsonResponse({ status: "error", error: sidErr }, 400);
  // PRES-009 QC repair (F3e): the box bridge now passes its company_id +
  // installation_id (from --company-id/--installation-id or the
  // INTAKE_COMPANY_ID/INTAKE_INSTALLATION_ID env). A scoped caller may only
  // read rows under ITS tuple; an UNSCOPED legacy-admin caller may read only
  // pre-tenant flat rows (company_id IS NULL) — a tenant-tuple row is never
  // served to a caller that has not proven that tenant.
  const company = params.get("company_id") || "";
  const installation = params.get("installation_id") || "";
  const scoped = Boolean(company && installation
    && !opaqueIdError("company_id", company) && !opaqueIdError("installation_id", installation));
  if (!env.DB) return errorResponse("intake not found", 404);
  const row = await env.DB.prepare(
    "SELECT session_id, file_name, intake_json, company_id, installation_id, tenant_state, quarantine_reason, created_at FROM intakes WHERE session_id = ?"
  ).bind(id).first();
  if (!row) return errorResponse("intake not found", 404);
  if (row.company_id || row.installation_id) {
    // Tuple row: requires exact matching scope. An unscoped caller (or one
    // carrying a DIFFERENT tenant) never sees the row — 404, indistinguishable
    // from a nonexistent id.
    if (!scoped || row.company_id !== company || row.installation_id !== installation) {
      return errorResponse("intake not found", 404);
    }
  }
  // Legacy flat row (no tenant identity): served to the legacy-admin path.
  if (row.tenant_state === "quarantined") {
    return errorResponse("intake unavailable: " + (row.quarantine_reason || "quarantined") + " — requires operator remediation", 423);
  }
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
  // PRES-009: the list is SCOPED to the authenticated installation/company
  // when the caller presents scoped credentials. PRES-009 QC repair (F3f): an
  // UNSCOPED legacy-admin caller now sees ONLY pre-tenant flat rows
  // (company_id IS NULL) — the old unscoped WHERE returned EVERY company's
  // active rows, so one box's poller discovered and ingested another box's
  // intake. Tenant-tuple rows are served only to callers carrying the exact
  // company_id + installation_id; ambiguous quarantined rows stay withheld
  // (count + remediation only, never by id).
  const installation = new URL(request.url).searchParams.get("installation_id") || "";
  const company = new URL(request.url).searchParams.get("company_id") || "";
  const scoped = Boolean(company && installation
    && !opaqueIdError("company_id", company) && !opaqueIdError("installation_id", installation));
  let sql = "SELECT session_id, file_name, tenant_state, created_at FROM intakes WHERE (tenant_state IS NULL OR tenant_state = 'active')";
  const params = [];
  if (scoped) {
    sql += " AND company_id = ? AND installation_id = ?";
    params.push(company, installation);
  } else {
    // Unscoped: pre-tenant flat rows only. Legacy rows minted pre-PRES-009 have
    // NULL company_id; after runLegacyMigration backfills them they carry
    // company_id? No — legacy backfill sets installation_id only, leaving
    // company_id NULL. Those belong to the box that minted them; they surface
    // here so a legacy deployment keeps working.
    sql += " AND company_id IS NULL";
  }
  sql += " ORDER BY created_at DESC";
  const rows = await env.DB.prepare(sql).bind(...params).all();
  const intakes = (rows && rows.results || []).map((r) => ({
    session_id: r.session_id, file_name: r.file_name,
    stored_at: r.created_at != null ? Number(r.created_at) : null,
  }));
  const quarantinedRes = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM intakes WHERE tenant_state = 'quarantined'",
  ).first();
  return jsonResponse({ intakes, quarantined_count: (quarantinedRes && quarantinedRes.n) || 0 }, 200);
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
// Contract enforced here:
//   1. PREFLIGHT — no CC_HANDOFF_SECRET => 503 with a precise missing-credential
//      message BEFORE any network call; the delivery intent is recorded
//      nonretryable in the outbox. The secret is server-only and scoped to the
//      handoff (it never reaches the browser bundle; this module only runs in
//      the Worker runtime). The INTAKE_ADMIN_TOKEN fallback is REMOVED: the
//      admin bearer authenticates box→worker sessions, an unrelated privilege.
//   2. SERIALIZE-THEN-SIGN — the payload is JSON.stringify()'d ONCE and those
//      exact bytes are both signed and sent, byte-for-byte parity with
//      cc_board.py's _sign()/_request().
//   3. OUTBOX — every delivery intent is durably recorded with a retryable vs
//      nonretryable disposition, not just an HTTP 502 to the client.
//   4. ACK BINDING — the CC acknowledgement must contain the expected task id
//      AND the bound company/box scope before the outbox marks fired.
//   5. ONE HANDOFF OWNER — the worker outbox is idempotent: a retry of an
//      already-fired session returns the recorded ack instead of creating a
//      second card (the box-side bridge remains a compatible idempotent
//      fallback through CC's own ingest dedupe, not a competing creator).
// The bound destination installation/company is carried in the signed payload
// as dest_box (the box_id this session was minted under) and dest_company
// (the intake's company binding); the remote CC verifies scope with its own
// WEBHOOK_SECRET, so a signature minted for one installation cannot create a
// card on another.
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

  // PREFLIGHT (PRES-007 step 1): the scoped handoff secret is REQUIRED. There
  // is no INTAKE_ADMIN_TOKEN fallback — combining unrelated privileges was the
  // second half of the PRES-007 defect. Fail with a precise contract error
  // before any network call, and record the intent NONRETRYABLE in the outbox:
  // retrying without the credential can never succeed, so it must not spin.
  const secret = (env.CC_HANDOFF_SECRET || "").trim();
  if (!secret) {
    await outboxRecord(env, session_id, "failed_nonretryable", null,
      "CC_HANDOFF_SECRET unset — worker cannot sign the /api/tasks/ingest handoff. Set the scoped HMAC secret on the worker (wrangler secret put CC_HANDOFF_SECRET) matching the destination box's WEBHOOK_SECRET. NOT retried automatically.");
    return errorResponse("dept start not configured: CC_HANDOFF_SECRET is not set on this worker. The /api/tasks/ingest endpoint requires x-webhook-signature = HMAC-SHA256(CC_HANDOFF_SECRET, rawBody); provision the scoped secret (wrangler secret put CC_HANDOFF_SECRET) and retry.", 503);
  }

  // One handoff owner: an outbox row that already fired (or is mid-flight with
  // a task binding) short-circuits the retry — the interrupted-ack case re-reads
  // the recorded task instead of minting a second card.
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
  // PRES-009 support: the destination binding travels INSIDE the signed bytes
  // so a tampered body cannot re-route another box's session. box_id is the
  // session's owning box; company comes from the intake record when present.
  const destBox = body.box_id || intake.box_id || prior?.dest_box || "";
  const destCompany = intake.company_id || intake.company || "";
  // Deterministic idempotency key scoped to destination + run: two companies
  // reusing a run name still hash differently, and the same session retried
  // hashes identically so the REMOTE ingest dedupes the repeat.
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

  if (env.DB && prior === null) {
    await outboxInsert(env, session_id, "firing", destBox);
  }
  try {
    const resp = await fetch(cc.replace(/\/$/, "") + "/api/tasks/ingest", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        // Preserved bearer (now the dedicated handoff credential when the box
        // provisions CC_DEPT_START_TOKEN as the MC_API_TOKEN-equivalent), plus
        // the REQUIRED HMAC over the exact bytes above.
        ...(env.CC_DEPT_START_TOKEN ? { authorization: "Bearer " + env.CC_DEPT_START_TOKEN } : {}),
        "x-webhook-signature": signature,
      },
      body: rawBody,
    });
    const data = await resp.json().catch(() => ({}));
    // ACK BINDING: require the task id AND that the acknowledgement echoes the
    // destination scope we sent. A 200 whose ack lacks task_id, or whose
    // dest_box disagrees with our binding, is a failed handoff — record it and
    // refuse to mark fired.
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
      if (env.DB) {
        await env.DB.prepare("UPDATE intakes SET dept_trigger = 'fired', dept_task_id = ?, updated_at = ? WHERE session_id = ?").bind(ackTaskId, nowSeconds(), session_id).run();
      }
      return jsonResponse({ status: "fired", session_id, task_id: ackTaskId, deduped: !!data.deduped, dest_box: destBox || null }, 201);
    }
    // Retryable vs nonretryable: 4xx (auth refusal, bad payload, held card) is
    // permanent until a human changes the destination or secret; 5xx/transport
    // is retryable.
    const retryable = resp.status >= 500 || resp.status === 429;
    const detail = "dept start failed (HTTP " + resp.status + "): " + (data.error || data.detail || "unknown");
    await outboxRecord(env, session_id, retryable ? "failed_retryable" : "failed_nonretryable", null, detail, destBox);
    return errorResponse(detail, 502);
  } catch (err) {
    // Transport failure (DNS, reset, timeout): retryable by definition.
    const detail = "dept start transport error: " + (err && err.message ? err.message : "network");
    await outboxRecord(env, session_id, "failed_retryable", null, detail, destBox);
    return errorResponse(detail, 502);
  }
}

// ---- handoff outbox (PRES-007 step 3) ---------------------------------------
// Durable delivery intent per intake session. States: firing (in flight),
// fired (ack bound), failed_retryable (5xx/transport — safe to retry),
// failed_nonretryable (4xx / missing credential / ack mismatch — human action).
// A retryable failure is re-armed to firing on the next attempt; a fired row
// makes every later call an idempotent ack replay.

async function outboxGet(env, sessionId) {
  if (!env.DB) return null;
  try {
    const row = await env.DB.prepare(
      "SELECT session_id, status, dept_task_id, dest_box, attempts, last_error, updated_at FROM handoff_outbox WHERE session_id = ?"
    ).bind(sessionId).first();
    return row || null;
  } catch { return null; } // table not yet migrated: treat as no prior state
}

async function outboxInsert(env, sessionId, status, destBox) {
  try {
    await env.DB.prepare(
      "INSERT INTO handoff_outbox (session_id, status, dept_task_id, dest_box, attempts, updated_at) VALUES (?, ?, NULL, ?, 1, ?)"
    ).bind(sessionId, status, destBox || null, nowSeconds()).run();
  } catch { /* observability must never turn into a 500 */ }
}

async function outboxRecord(env, sessionId, status, deptTaskId, lastError, destBox) {
  try {
    const existing = await outboxGet(env, sessionId);
    if (!existing) {
      await env.DB.prepare(
        "INSERT INTO handoff_outbox (session_id, status, dept_task_id, dest_box, attempts, last_error, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)"
      ).bind(sessionId, status, deptTaskId, destBox || null, lastError, nowSeconds()).run();
      return;
    }
    await env.DB.prepare(
      "UPDATE handoff_outbox SET status = ?, dept_task_id = COALESCE(?, dept_task_id), dest_box = COALESCE(?, dest_box), attempts = attempts + 1, last_error = ?, updated_at = ? WHERE session_id = ?"
    ).bind(status, deptTaskId, destBox || null, lastError, nowSeconds(), sessionId).run();
  } catch { /* observability must never turn into a 500 */ }
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

// ---- helpers -----------------------------------------------------------------

async function latestGrantFor(env, sessionId, runId) {
  if (sessionId) {
    return env.DB.prepare(
      "SELECT token, session_id, run_id, box_id, company_id, installation_id, presentation_id, intake_session_id, tenant_state, quarantine_reason, display_name, schema_fp, recipient_chat_id, questions_json, question_set, status, revision, expires_at FROM sessions WHERE session_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).bind(sessionId).first();
  }
  return env.DB.prepare(
    "SELECT token, session_id, run_id, box_id, company_id, installation_id, presentation_id, intake_session_id, tenant_state, quarantine_reason, display_name, schema_fp, recipient_chat_id, questions_json, question_set, status, revision, expires_at FROM sessions WHERE run_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1"
  ).bind(runId).first();
}

async function loadOpenSession(env, token, allowComplete = false) {
  const session = await env.DB.prepare("SELECT token, session_id, run_id, box_id, company_id, installation_id, presentation_id, intake_session_id, tenant_state, quarantine_reason, question_set, questions_json, status, revision, invalidated_at, invalidated_reason, created_at, expires_at, completed_at FROM sessions WHERE token = ?").bind(token).first();
  if (!session) {
    // PRES-024: a revoked token is REJECTED (410), never treated as unknown.
    const revoked = await env.DB.prepare("SELECT token FROM revoked_tokens WHERE token = ?").bind(token).first();
    if (revoked) return { error: errorResponse("session token revoked — use the renewed link", 410) };
    return { error: errorResponse("session not found", 404) };
  }
  // A renewed-away grant is dead FIRST — the revocation, not the clock, is
  // what killed it (PRES-024).
  if (session.tenant_state === "quarantined") return { error: errorResponse("session quarantined — operator remediation required", 423) };
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