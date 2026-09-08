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
// Bindings (see wrangler.toml): DB (D1). Secrets: INTAKE_ADMIN_TOKEN (box auth),
// COMMAND_CENTER_URL (CC board base URL), CC_DEPT_START_TOKEN (CC ingest auth).

import {
  randomToken, nowSeconds, expiryFrom, isValidTokenShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
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

  const payload = body.questions_payload;
  const check = validateQuestionsPayload(payload);
  if (!check.ok) return errorResponse("questions_payload invalid: " + check.error, 400);

  const created = nowSeconds();
  const companyId = body.company_id;
  const installationId = body.installation_id;
  const presentationId = body.presentation_id;

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
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const storageRunId = mintRunId();
  const intakeSessionId = mintIntakeSessionId();
  await env.DB.prepare(
    "INSERT INTO sessions (token, run_id, display_name, box_id, question_set, questions_json, company_id, installation_id, presentation_id, intake_session_id, schema_fp, tenant_state, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'open', ?, ?)",
  ).bind(
    newToken, storageRunId, displayName || storageRunId, displayName || storageRunId,
    payload.question_set, JSON.stringify(payload),
    companyId, installationId, presentationId, intakeSessionId, schemaFp, created, expires,
  ).run();
  return jsonResponse({
    status: "created", token: newToken, capability_url: capabilityUrl(request, newToken),
    run_id: storageRunId, intake_session_id: intakeSessionId,
    company_id: companyId, installation_id: installationId, presentation_id: presentationId,
    expires_at: expires,
  }, 201);
}

async function getSession(env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  const answeredIds = await answeredIdList(env, token);
  const answeredValues = await answeredValueMap(env, token);
  return jsonResponse({ status: session.status, run_id: session.run_id, company_id: session.company_id, installation_id: session.installation_id, presentation_id: session.presentation_id, intake_session_id: session.intake_session_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, expires_at: session.expires_at });
}

async function postAnswer(request, env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  if (session.status === "complete") return errorResponse("session already complete", 409);
  let body; try { body = await request.json(); } catch { return errorResponse("invalid JSON body", 400); }
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
  const session = await env.DB.prepare("SELECT token, run_id, box_id, company_id, installation_id, presentation_id, intake_session_id, question_set, questions_json, tenant_state, quarantine_reason, status, created_at, expires_at FROM sessions WHERE token = ?").bind(token).first();
  if (!session) return { error: errorResponse("session not found", 404) };
  if (session.tenant_state === "quarantined") {
    return { error: errorResponse("session unavailable: " + (session.quarantine_reason || "quarantined") + " — requires operator remediation", 423) };
  }
  if (Number(session.expires_at) <= nowSeconds() && session.status !== "complete") return { error: errorResponse("session expired", 410) };
  if (session.status === "expired") return { error: errorResponse("session expired", 410) };
  if (session.status === "complete" && !allowComplete) return { error: errorResponse("session already complete", 409) };
  let payload; try { payload = JSON.parse(session.questions_json); } catch { return { error: errorResponse("corrupt session payload", 500) }; }
  return { session, payload };
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
    await env.DB.prepare(
      "INSERT INTO intakes (session_id, file_name, intake_json, company_id, installation_id, presentation_id, run_id, tenant_state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?) " +
      "ON CONFLICT (session_id) DO UPDATE SET intake_json = excluded.intake_json, company_id = excluded.company_id, installation_id = excluded.installation_id, presentation_id = excluded.presentation_id, run_id = excluded.run_id, created_at = excluded.created_at",
    ).bind(session_id, String(body.file_name || "intake.json").slice(0, 200), JSON.stringify(intake), intake.company_id, intake.installation_id, intake.presentation_id, intake.run_id, created).run();
  }
  return jsonResponse({ status: "stored", session_id, file_name: body.file_name || "intake.json", stored_at: created, company_id: intake.company_id }, 201);
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
  const sidErr = opaqueIdError("id", id);
  if (sidErr) return jsonResponse({ status: "error", error: sidErr }, 400);
  if (!env.DB) return errorResponse("intake not found", 404);
  const row = await env.DB.prepare(
    "SELECT session_id, file_name, intake_json, tenant_state, quarantine_reason, created_at FROM intakes WHERE session_id = ?"
  ).bind(id).first();
  if (!row) return errorResponse("intake not found", 404);
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
  // when the caller presents scoped credentials. Legacy global-admin callers
  // (INTAKE_ADMIN_TOKEN bearer alone) still reach their own records but every
  // AMBIGUOUS legacy row (tenant_state='quarantined') is withheld and surfaced
  // only by count + remediation, never by id — an ambiguous row must not be
  // shown to every active company.
  const installation = new URL(request.url).searchParams.get("installation_id") || "";
  const company = new URL(request.url).searchParams.get("company_id") || "";
  let sql = "SELECT session_id, file_name, tenant_state, created_at FROM intakes WHERE (tenant_state IS NULL OR tenant_state = 'active')";
  const params = [];
  if (installation && !opaqueIdError("installation_id", installation)) {
    sql += " AND installation_id = ?";
    params.push(installation);
  }
  if (company && !opaqueIdError("company_id", company)) {
    sql += " AND company_id = ?";
    params.push(company);
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

async function answeredIdList(env, token) {
  const res = await env.DB.prepare("SELECT question_id FROM answers WHERE token = ? ORDER BY id ASC").bind(token).all();
  return (res.results || []).map((r) => r.question_id);
}

async function answeredValueMap(env, token) {
  const res = await env.DB.prepare("SELECT question_id, value FROM answers WHERE token = ? ORDER BY id ASC").bind(token).all();
  const map = {}; for (const r of (res.results || [])) map[r.question_id] = r.value;
  return map;
}
