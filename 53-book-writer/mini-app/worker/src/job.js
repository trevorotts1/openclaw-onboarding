// ============================================================================
// job.js — book-writer mini-app per-run JOB STATE MACHINE + intake assembly
// gate (U14, Wave C).
//
// MASTER-PLAN section 9 (U14) + section 4 (job model + assembly gate):
//   - per-run job state machine:
//       queued -> collecting -> assembly-ready -> completed / failed
//   - intake assembly gate that REFUSES to assemble while ANY step is queued
//     (AF-BW-MA-JOB-PENDING). A queued/processing job is NEVER a missing field
//     (would false-fail AF-BK-INTAKE-MISSING) and is NEVER assembled (would
//     mint an incomplete intake).
//   - EXTRACT-NO-TEXT rule: a media answer with no extracted text NEVER trips
//     assembly-ready (AF-BW-MA-EXTRACT-NO-TEXT).
//   - explicit AF fail-closed codes for EVERY violation — never a silent pass.
//
// DUMB-RELAY edge module: holds ZERO client PITs, performs no GHL write, no
// Anthropic ids, no real zone/account ids, no hardcoded client/location.
//
// The gate is authoritative over EVIDENCE, never over a caller's verdict:
//   - typed evidence is read from the per-client BW_BINDINGS prefix (the same
//     `answer:` / `save:` keys U03/U11 write);
//   - media evidence is read from the MEDIA_JOBS KV row for a qid's answer_id
//     (authoritative when env.MEDIA_JOBS is bound). Raw media rows may also be
//     supplied in the request body (offline/test fallback) but are IGNORED for
//     any qid whose answer_id resolves through MEDIA_JOBS — the KV row wins, so
//     a forged body can never self-attest a job as done.
//
// The gate never trusts a bare status string: a field is "present" ONLY when
// its evidence is a `done` media job carrying non-empty text (or explicit N/A),
// or a non-empty typed answer. Everything else fails closed with a named AF
// code.
// ============================================================================

'use strict';

// ---------------------------------------------------------------------------
// Token shape (matches U03/U11's guard exactly — a cheap mint-time check, not
// an authority check; the KV binding row is the authority).
// ---------------------------------------------------------------------------
const TOKEN_RE = /^[0-9a-f]{32}$/;

export function isValidTokenShape(token) {
  return typeof token === "string" && TOKEN_RE.test(token);
}

// ---------------------------------------------------------------------------
// Run state machine + AF codes
// ---------------------------------------------------------------------------

export const RUN_STATE = Object.freeze({
  QUEUED: "queued", // run created, no required field present yet
  COLLECTING: "collecting", // answers arriving, gate closed (any required step not present)
  ASSEMBLY_READY: "assembly-ready", // every required field present; intake may assemble
  COMPLETED: "completed", // intake assembled + handed off (terminal)
  FAILED: "failed", // intake assembly failed permanently (terminal)
});

// Explicit AF fail-closed codes (MASTER-PLAN section 4 "New AF codes prefixed
// AF-BW-MA-*"). AF-BW-MA-ANTHROPIC is reserved — never an Anthropic id.
export const AF = Object.freeze({
  JOB_PENDING: "AF-BW-MA-JOB-PENDING", // assembled/tripped while a required job not done
  EXTRACT_NO_TEXT: "AF-BW-MA-EXTRACT-NO-TEXT", // media answer with no extracted text
  CAPABILITY: "AF-BW-MA-CAPABILITY", // required step failed / capability absent
  REJECT_FIELD: "AF-BW-MA-REJECT-FIELD", // missing / malformed / forged field evidence
  ANTHROPIC: "AF-BW-MA-ANTHROPIC", // reserved — an Anthropic id must never appear
});

// ---------------------------------------------------------------------------
// Pure field-status resolution (fail-closed; EXTRACT-NO-TEXT never present)
// ---------------------------------------------------------------------------

/**
 * Resolve ONE field's evidence to a gate status. The gate never trusts a
 * caller-supplied verdict — it reads `status`/`text` off the RAW media job
 * row, or the typed answer string.
 *
 * @param {{typedText?: string|null, mediaJob?: object|null}} evidence
 * @returns {{status: 'present'|'pending'|'failed'|'no-text'|'missing', code: string|null}}
 *   - media queued/processing      -> pending   (AF-BW-MA-JOB-PENDING)
 *   - media failed                 -> failed    (AF-BW-MA-CAPABILITY)
 *   - media done + non-empty text  -> present
 *   - media done + empty text      -> no-text   (AF-BW-MA-EXTRACT-NO-TEXT — NEVER present)
 *   - media with unknown/forged status -> missing (fail closed, never present)
 *   - typed non-empty              -> present
 *   - typed empty / none           -> missing
 */
export function fieldStatus({ typedText, mediaJob } = {}) {
  if (mediaJob && typeof mediaJob === "object") {
    const status = mediaJob.status;
    if (status === "queued" || status === "processing") {
      return { status: "pending", code: AF.JOB_PENDING };
    }
    if (status === "failed") {
      return { status: "failed", code: AF.CAPABILITY };
    }
    if (status === "done") {
      const t = typeof mediaJob.text === "string" ? mediaJob.text.trim() : "";
      if (t.length === 0) {
        // THE EXTRACT-NO-TEXT RULE: no extracted text NEVER trips assembly-ready.
        return { status: "no-text", code: AF.EXTRACT_NO_TEXT };
      }
      return { status: "present", code: null };
    }
    // Unknown / forged job status — fail closed (never treated as present).
    return { status: "missing", code: AF.REJECT_FIELD };
  }
  // Typed evidence.
  if (typeof typedText === "string" && typedText.trim().length > 0) {
    return { status: "present", code: null };
  }
  if (typeof typedText === "string") {
    // A blank typed answer is a not-answered field.
    return { status: "missing", code: AF.REJECT_FIELD };
  }
  return { status: "missing", code: AF.REJECT_FIELD };
}

// ---------------------------------------------------------------------------
// Pure intake assembly gate
// ---------------------------------------------------------------------------

/**
 * THE INTAKE ASSEMBLY GATE (MASTER-PLAN section 4 + U14). Given the required
 * qids and per-field evidence, decide whether intake may assemble.
 *
 * Rules (each violation names an explicit AF code — never a silent pass):
 *   - ANY required step queued/processing -> REFUSE, AF-BW-MA-JOB-PENDING
 *     (the master-plan invariant: never assemble while queued; a pending job is
 *      never treated as a missing field).
 *   - ANY media answer with no extracted text -> REFUSE, AF-BW-MA-EXTRACT-NO-TEXT.
 *   - ANY required step failed -> REFUSE, AF-BW-MA-CAPABILITY (retry surfaces).
 *   - ANY required field missing -> REFUSE, AF-BW-MA-REJECT-FIELD.
 *   - empty required set -> REFUSE (never a trivial pass).
 *   - ALL present -> {ok:true, verdict:'assembly-ready'}.
 *
 * @param {string[]} requiredQids
 * @param {Object<string, {typedText?: string|null, mediaJob?: object|null}>} evidenceByQid
 * @returns {{ok:boolean, verdict:string, code:string|null, reason:string|null, fields:Object<string,string>}}
 */
export function assemblyGate(requiredQids, evidenceByQid) {
  if (!Array.isArray(requiredQids) || requiredQids.length === 0) {
    // Fail closed on an empty required set — a gate that knows no fields must
    // never report ready (that would be a silent pass by omission).
    return {
      ok: false,
      verdict: "missing",
      code: AF.REJECT_FIELD,
      reason: "No required fields known for this phase; the gate cannot open.",
      fields: {},
    };
  }
  const fields = {};
  let anyPending = false;
  let anyNoText = false;
  let anyFailed = false;
  let anyMissing = false;
  const missingQids = [];

  for (const qid of requiredQids) {
    const ev = (evidenceByQid && evidenceByQid[qid]) || {};
    const fs = fieldStatus(ev);
    fields[qid] = fs.status;
    if (fs.status === "pending") anyPending = true;
    else if (fs.status === "no-text") anyNoText = true;
    else if (fs.status === "failed") anyFailed = true;
    else if (fs.status === "missing") {
      anyMissing = true;
      missingQids.push(qid);
    }
  }

  // Priority: a queued step closes the gate FIRST (the master-plan invariant
  // "NEVER assemble while queued" outranks every other refusal).
  if (anyPending) {
    return {
      ok: false,
      verdict: "blocked",
      code: AF.JOB_PENDING,
      reason: "A required step is still queued — never assemble while queued.",
      fields,
    };
  }
  if (anyNoText) {
    return {
      ok: false,
      verdict: "no-text",
      code: AF.EXTRACT_NO_TEXT,
      reason: "A media answer produced no extracted text — it never trips assembly-ready.",
      fields,
    };
  }
  if (anyFailed) {
    return {
      ok: false,
      verdict: "degraded",
      code: AF.CAPABILITY,
      reason: "A required step failed — retry surfaces; never assemble.",
      fields,
    };
  }
  if (anyMissing) {
    return {
      ok: false,
      verdict: "missing",
      code: AF.REJECT_FIELD,
      reason: `Missing required field(s): ${missingQids.join(", ")}.`,
      fields,
    };
  }
  return {
    ok: true,
    verdict: "assembly-ready",
    code: null,
    reason: null,
    fields,
  };
}

// ---------------------------------------------------------------------------
// Pure run-state transitions (the state machine)
// ---------------------------------------------------------------------------

/**
 * Advance the run's state from a gate verdict. The run state machine:
 *
 *   queued --(gate opens)-------------------------------------------> assembly-ready
 *   queued --(gate closed: pending/no-text/missing/degraded)--------> collecting
 *   collecting --(gate opens)--------------------------------------> assembly-ready
 *   collecting --(gate closed)-------------------------------------> collecting (stay)
 *   assembly-ready --(gate re-closed, evidence reverted)-----------> collecting
 *   assembly-ready --(markCompleted)-------------------------------> completed (terminal)
 *   any --(markFailed)---------------------------------------------> failed (terminal)
 *
 * Completed and failed are TERMINAL: no transition reopens them. A failed
 * required step parks the run in `collecting` (degraded) so retry can still
 * unblock it; only an explicit assembly failure parks `failed`.
 *
 * @param {Object} gate        result of assemblyGate()
 * @param {string|null} current current run state (or null = queued)
 * @returns {{ok:boolean, state:string, code:string|null, reason:string|null, changed:boolean}}
 */
export function applyGate(gate, current) {
  const cur = current || RUN_STATE.QUEUED;
  if (cur === RUN_STATE.COMPLETED || cur === RUN_STATE.FAILED) {
    return {
      ok: false,
      state: cur,
      code: (gate && gate.code) || AF.REJECT_FIELD,
      reason: `Run is terminal (${cur}); the gate cannot reopen it.`,
      changed: false,
    };
  }
  if (gate && gate.ok && gate.verdict === "assembly-ready") {
    return {
      ok: true,
      state: RUN_STATE.ASSEMBLY_READY,
      code: null,
      reason: "Every required field is present — intake may assemble.",
      changed: cur !== RUN_STATE.ASSEMBLY_READY,
    };
  }
  // Gate closed: the run is collecting (from queued, collecting, or even a
  // re-closed assembly-ready). Never a silent pass — the AF code rides along.
  const next = RUN_STATE.COLLECTING;
  return {
    ok: false,
    state: next,
    code: (gate && gate.code) || AF.REJECT_FIELD,
    reason: (gate && gate.reason) || "The intake assembly gate is closed.",
    changed: cur !== next,
  };
}

/**
 * Mark a run completed AFTER the intake has actually been assembled + handed
 * off. Only an assembly-ready run may complete; the gate state is the proof
 * that no step was still queued at completion time (belt-and-suspenders on
 * "never assemble while queued").
 *
 * @param {object|null} jobRow    the run job row (state machine record)
 * @param {{nowUtc?: string, assembledIntakeRef?: string|null}} opts
 * @returns {{ok:boolean, job:object|null, code:string|null, reason:string|null}}
 */
export function markCompleted(jobRow, { nowUtc = null, assembledIntakeRef = null } = {}) {
  if (!jobRow || typeof jobRow !== "object") {
    return { ok: false, job: null, code: AF.REJECT_FIELD, reason: "No run job row." };
  }
  if (jobRow.state === RUN_STATE.FAILED) {
    return { ok: false, job: jobRow, code: AF.CAPABILITY, reason: "A failed run cannot be completed." };
  }
  if (jobRow.state !== RUN_STATE.ASSEMBLY_READY) {
    // Not ready (queued / collecting) -> completion is refused: the gate's
    // assembly-ready state is the ONLY lawful path to completed.
    return { ok: false, job: jobRow, code: AF.JOB_PENDING, reason: "Only an assembly-ready run may complete." };
  }
  const job = {
    ...jobRow,
    state: RUN_STATE.COMPLETED,
    completed_at: nowUtc || jobRow.updated_at || null,
    assembled_intake: assembledIntakeRef || jobRow.assembled_intake || null,
  };
  return { ok: true, job, code: null, reason: null };
}

/**
 * Mark a run permanently failed (e.g. the intake assembly step itself threw).
 * A completed run cannot be failed.
 *
 * @param {object|null} jobRow
 * @param {{nowUtc?: string, error?: string}} opts
 * @returns {{ok:boolean, job:object|null, code:string|null, reason:string|null}}
 */
export function markFailed(jobRow, { nowUtc = null, error = null } = {}) {
  if (!jobRow || typeof jobRow !== "object") {
    return { ok: false, job: null, code: AF.REJECT_FIELD, reason: "No run job row." };
  }
  if (jobRow.state === RUN_STATE.COMPLETED) {
    return { ok: false, job: jobRow, code: AF.CAPABILITY, reason: "A completed run cannot be failed." };
  }
  const job = {
    ...jobRow,
    state: RUN_STATE.FAILED,
    failed_at: nowUtc || jobRow.updated_at || null,
    error: error || "intake assembly failed",
  };
  return { ok: true, job, code: null, reason: null };
}

// ---------------------------------------------------------------------------
// Run job row — storage adapter (Cloudflare-style KV: get(key, {type:"json"})
// / put(key, value), the same surface answers.js and save.js use against
// env.BW_BINDINGS).
// ---------------------------------------------------------------------------

export function runJobKey(runId) {
  return `runjob:${runId}`;
}

export function newRunJob(runId, phaseId, nowUtc) {
  return {
    run_id: runId,
    phase_id: phaseId,
    state: RUN_STATE.QUEUED,
    created_at: nowUtc,
    updated_at: nowUtc,
    completed_at: null,
    failed_at: null,
    error: null,
    assembled_intake: null,
  };
}

export async function loadRunJob(store, runId) {
  // Fail closed: a missing row AND a corrupt row both resolve to null, so the
  // caller can never mistake a broken store for a healthy-but-queued run.
  try {
    const raw = await store.get(runJobKey(runId), { type: "json" });
    if (!raw) return null;
    return raw; // {type:"json"} already parsed
  } catch {
    return null;
  }
}

export async function saveRunJob(store, job) {
  await store.put(runJobKey(job.run_id), JSON.stringify(job));
}

// ---------------------------------------------------------------------------
// Request handler (POST /api/job) — composes the pure gate with authoritative
// KV/MEDIA_JOBS evidence. Wired into src/index.js routing.
// ---------------------------------------------------------------------------

function jsonResponse(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      ...headers,
    },
  });
}

/**
 * Parse the /api/job payload. Shape:
 *   {
 *     "phase_id": string|null,          // defaults to the binding's phase
 *     "required": string[]|null,        // required qids; defaults to the phase config
 *     "media_answer_ids": {qid: answerId}   // qid -> answer_id, resolved via MEDIA_JOBS
 *                                           // (the AUTHORITATIVE media evidence path)
 *     "media": {qid: rawJobRow}         // raw job rows (offline/test fallback; ignored
 *                                           // for qids that resolve via MEDIA_JOBS)
 *   }
 */
export function parseJobPayload(raw) {
  if (typeof raw !== "string" || raw.length > 300 * 1024) {
    return { ok: false, status: 400, error: "body too large or missing" };
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false, status: 400, error: "invalid JSON body" };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, status: 400, error: "body must be a JSON object" };
  }
  // Injected destination fields are IGNORED at the boundary (isolation by
  // construction — the binding row is the sole destination authority).
  if ("location_id" in parsed || "contact_id" in parsed || "client_id" in parsed) {
    return { ok: false, status: 400, error: "injected destination rejected" };
  }
  const out = { phase_id: null, required: null, media_answer_ids: null, media: null };
  if (parsed.phase_id !== undefined) {
    if (typeof parsed.phase_id !== "string") return { ok: false, status: 400, error: "phase_id must be a string" };
    out.phase_id = parsed.phase_id.trim() || null;
  }
  if (parsed.required !== undefined) {
    if (!Array.isArray(parsed.required) || !parsed.required.every((q) => typeof q === "string")) {
      return { ok: false, status: 400, error: "required must be an array of qid strings" };
    }
    out.required = parsed.required.map((q) => q.trim()).filter(Boolean);
  }
  if (parsed.media_answer_ids !== undefined) {
    if (!parsed.media_answer_ids || typeof parsed.media_answer_ids !== "object" || Array.isArray(parsed.media_answer_ids)) {
      return { ok: false, status: 400, error: "media_answer_ids must be an object map" };
    }
    out.media_answer_ids = {};
    for (const [qid, aid] of Object.entries(parsed.media_answer_ids)) {
      if (typeof aid !== "string") return { ok: false, status: 400, error: "media_answer_ids values must be strings" };
      out.media_answer_ids[qid] = aid;
    }
  }
  if (parsed.media !== undefined) {
    if (!parsed.media || typeof parsed.media !== "object" || Array.isArray(parsed.media)) {
      return { ok: false, status: 400, error: "media must be an object map" };
    }
    out.media = {};
    for (const [qid, row] of Object.entries(parsed.media)) {
      if (!row || typeof row !== "object") return { ok: false, status: 400, error: `media row for ${qid} must be an object` };
      out.media[qid] = row;
    }
  }
  return { ok: true, body: out };
}

/**
 * Load the authoritative media job row for a qid, if resolvable.
 * When env.MEDIA_JOBS is bound AND the payload carries media_answer_ids[qid],
 * the KV row WINS over any raw `media` body row (a forged body can never
 * self-attest a done job). Returns null when no authoritative row exists.
 */
async function resolveMediaJob(env, payload, qid) {
  if (env && env.MEDIA_JOBS && typeof env.MEDIA_JOBS.get === "function") {
    const answerId = payload.media_answer_ids && payload.media_answer_ids[qid];
    if (typeof answerId === "string" && answerId) {
      const raw = await env.MEDIA_JOBS.get(`media:${answerId}`);
      if (raw) {
        try {
          return JSON.parse(raw);
        } catch {
          return null; // corrupt row -> treat as no evidence -> field missing (fail closed)
        }
      }
    }
    // MEDIA_JOBS is bound but no answer_id maps to this qid: no authoritative
    // media evidence. A `media` body row for this qid is IGNORED (never trust
    // the wire when the authoritative store is reachable).
    return null;
  }
  // No MEDIA_JOBS binding (offline / test): fall back to the raw body rows.
  return (payload.media && payload.media[qid]) || null;
}

/**
 * POST /api/job?tk=<token>
 * Run the intake assembly gate for the token-bound run, advance the run job
 * state machine, persist the run job row, and return the verdict.
 *
 * Responses:
 *   200 { ok:true,  gate:{verdict:'assembly-ready',...}, run:{state:'assembly-ready'} }
 *   409 { ok:false, gate:{verdict:'blocked'|'no-text'|'degraded'|'missing',
 *                          code:AF-BW-MA-*}, run:{state:'collecting'} }
 *   400 / 401 / 410 / 503 for invalid token / tampered / completed / no KV.
 */
export async function handleJobPost(request, env, now = Math.floor(Date.now() / 1000)) {
  const url = new URL(request.url);
  const token = url.searchParams.get("tk") || "";
  if (!isValidTokenShape(token)) {
    return jsonResponse({ error: "bad token", ok: false }, 400);
  }
  const kv = env.BW_BINDINGS;
  if (!kv || typeof kv.get !== "function" || typeof kv.put !== "function") {
    return jsonResponse({ error: "server not configured", ok: false }, 503);
  }

  const binding = await kv.get(`binding:${token}`, { type: "json" });
  if (!binding || typeof binding !== "object") {
    return jsonResponse({ error: "invalid or unknown token", ok: false }, 401);
  }
  if (binding.status === "completed" || binding.status === "done") {
    return jsonResponse({ error: "run already completed", ok: false }, 410);
  }
  if (typeof binding.exp === "number" && binding.exp > 0 && binding.exp < now) {
    return jsonResponse({ error: "token expired", ok: false }, 401);
  }
  if (!binding.client_id || !binding.run_id || !binding.phase_id) {
    return jsonResponse({ error: "binding row incomplete", ok: false }, 401);
  }

  const raw = await request.text();
  const parsed = parseJobPayload(raw);
  if (!parsed.ok) {
    return jsonResponse({ error: parsed.error, ok: false }, parsed.status);
  }

  const runId = binding.run_id;
  const phaseId = parsed.body.phase_id || binding.phase_id;

  // Required qids: caller-supplied, else derive from the phase config
  // (config is DATA, never code). Never a trivial pass on an empty set.
  let required = parsed.body.required;
  if (!Array.isArray(required) || required.length === 0) {
    let cfg = null;
    // lib.js's config contract is store.objectGet(path) -> { value } | null.
    if (env.ZHW_BOOKWRITER && typeof env.ZHW_BOOKWRITER.objectGet === "function") {
      const { loadPhaseConfig } = await import("./lib.js");
      cfg = await loadPhaseConfig(env.ZHW_BOOKWRITER, binding.slug, phaseId, binding.mode || "full");
    }
    required = cfg && Array.isArray(cfg.questions)
      ? cfg.questions.filter((q) => q && q.required === true).map((q) => q.id)
      : [];
  }

  // Build evidence: typed answers from BW_BINDINGS (authoritative); media from
  // MEDIA_JOBS (authoritative when bound).
  const evidence = {};
  for (const qid of required) {
    const [aRow, sRow] = await Promise.all([
      kv.get(`answer:${binding.client_id}:${runId}:${phaseId}:${qid}`, { type: "json" }),
      kv.get(`save:${binding.client_id}:${runId}:${phaseId}:${qid}`, { type: "json" }),
    ]);
    let typedText;
    if (aRow && typeof aRow.answer === "string") typedText = aRow.answer;
    else if (sRow && typeof sRow.answer === "string") typedText = sRow.answer;
    const mediaJob = await resolveMediaJob(env, parsed.body, qid);
    evidence[qid] = { typedText, mediaJob };
  }

  const gate = assemblyGate(required, evidence);

  let jobRow = await loadRunJob(kv, runId);
  const nowUtc = new Date(now * 1000).toISOString();
  if (!jobRow) {
    jobRow = newRunJob(runId, phaseId, nowUtc);
  }
  const next = applyGate(gate, jobRow.state);
  if (next.changed || gate.ok) {
    jobRow = { ...jobRow, state: next.state, updated_at: nowUtc };
    await saveRunJob(kv, jobRow);
  }

  return jsonResponse({
    ok: gate.ok,
    gate: { verdict: gate.verdict, code: gate.code, reason: gate.reason, fields: gate.fields },
    run: { run_id: runId, phase_id: phaseId, state: next.state, changed: next.changed },
  }, gate.ok ? 200 : 409);
}

/**
 * Route dispatcher — GET returns 405; POST delegates. This is the surface
 * src/index.js calls for the /api/job path.
 */
export async function handleJobRequest(request, env) {
  if (request.method === "POST") return handleJobPost(request, env);
  return jsonResponse({ error: "method not allowed", ok: false }, 405);
}

// ---------------------------------------------------------------------------
// Self-test entry (node src/job.js --self-test) + importable by node --test.
// Mirrors the media.js / save.js pattern.
// ---------------------------------------------------------------------------

export function selfTest() {
  const failures = [];
  const check = (name, cond) => {
    if (!cond) failures.push(name);
  };

  // 1) Gate negatives — never assemble while queued.
  const queuedGate = assemblyGate(["ideal_avatar"], { ideal_avatar: { mediaJob: { status: "queued", text: "" } } });
  check("queued step closes the gate", queuedGate.ok === false);
  check("queued step names JOB-PENDING", queuedGate.code === AF.JOB_PENDING);
  check("queued step verdict is blocked", queuedGate.verdict === "blocked");

  // 2) EXTRACT-NO-TEXT — a done media job with no text NEVER trips ready.
  const noTextGate = assemblyGate(["ideal_avatar"], { ideal_avatar: { mediaJob: { status: "done", text: "   " } } });
  check("done-with-no-text closes the gate", noTextGate.ok === false);
  check("done-with-no-text names EXTRACT-NO-TEXT", noTextGate.code === AF.EXTRACT_NO_TEXT);

  // 3) A pending step outranks a no-text step.
  const mixedGate = assemblyGate(["a", "b"], {
    a: { mediaJob: { status: "queued", text: "" } },
    b: { mediaJob: { status: "done", text: "" } },
  });
  check("pending outranks no-text", mixedGate.ok === false && mixedGate.code === AF.JOB_PENDING);

  // 4) Missing / failed / empty-set all fail closed.
  const missingGate = assemblyGate(["first_name"], { first_name: { typedText: "" } });
  check("missing field fails closed", missingGate.ok === false && missingGate.code === AF.REJECT_FIELD);
  const failedGate = assemblyGate(["x"], { x: { mediaJob: { status: "failed", error: "boom" } } });
  check("failed field names CAPABILITY", failedGate.ok === false && failedGate.code === AF.CAPABILITY);
  const emptyGate = assemblyGate([], {});
  check("empty required set never passes", emptyGate.ok === false && emptyGate.code === AF.REJECT_FIELD);

  // 5) All present -> assembly-ready.
  const readyGate = assemblyGate(["first_name", "ideal_avatar"], {
    first_name: { typedText: "Ada" },
    ideal_avatar: { mediaJob: { status: "done", text: "transcribed words" } },
  });
  check("all present opens the gate", readyGate.ok === true && readyGate.verdict === "assembly-ready");

  // 6) State machine transitions.
  const fromQueued = applyGate(readyGate, RUN_STATE.QUEUED);
  check("queued -> assembly-ready when gate opens", fromQueued.state === RUN_STATE.ASSEMBLY_READY);
  const fromQueuedClosed = applyGate(queuedGate, RUN_STATE.QUEUED);
  check("queued -> collecting when gate closed", fromQueuedClosed.state === RUN_STATE.COLLECTING);
  const collecting = { run_id: "r", phase_id: "p", state: RUN_STATE.COLLECTING, created_at: "now", updated_at: "now" };
  const doneRow = markCompleted({ ...collecting, state: RUN_STATE.ASSEMBLY_READY }, { nowUtc: "t", assembledIntakeRef: "intake.json" });
  check("assembly-ready may complete", doneRow.ok === true && doneRow.job.state === RUN_STATE.COMPLETED);
  const tooEarly = markCompleted(collecting, { nowUtc: "t" });
  check("collecting may NOT complete", tooEarly.ok === false && tooEarly.code === AF.JOB_PENDING);
  const terminal = markCompleted({ ...doneRow.job }, { nowUtc: "t2" });
  check("completed is terminal", terminal.ok === false);

  const failRow = markFailed({ run_id: "r", phase_id: "p", state: RUN_STATE.COLLECTING, updated_at: "t" }, { nowUtc: "t" });
  check("collecting may fail", failRow.ok === true && failRow.job.state === RUN_STATE.FAILED);
  const reopen = applyGate(readyGate, RUN_STATE.FAILED);
  check("failed is terminal (gate cannot reopen)", reopen.ok === false && reopen.state === RUN_STATE.FAILED);

  return failures;
}

const RUNNING_DIRECTLY = typeof process !== "undefined" && process.argv[1] && process.argv[1].endsWith("job.js");
if (RUNNING_DIRECTLY && process.argv.includes("--self-test")) {
  const failures = selfTest();
  if (failures.length === 0) {
    console.log("U14 job state machine self-test: PASS (gate closes on queued/no-text/missing/failed; opens only when all present)");
    process.exit(0);
  } else {
    console.error("U14 job state machine self-test: FAIL\n - " + failures.join("\n - "));
    process.exit(1);
  }
}
