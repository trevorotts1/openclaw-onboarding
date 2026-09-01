// ============================================================================
// save.js — book-writer mini-app Worker save & resume (U11)
//
// Wave B, unit U11. Turns "Save & come back later — your answers are safe"
// into a real promise: every answer the reader types is persisted to the
// Worker (debounced ~800ms on the client), and reopening the same link resumes
// exactly at the next unanswered question. Completion optionally records an
// email opt-in for a resume reminder ("Email me my draft", skippable).
//
// Endpoints (all under the token-bound run; the KV binding row is the SOLE
// authority for the destination — request bodies never carry location_id /
// contact_id / client_id):
//   POST /api/save?tk=<token>          persist one draft answer idempotently.
//                                      Uses the SAME per-step consumed counter
//                                      as U03 (/api/answers) so a replayed
//                                      save can never duplicate a staged
//                                      answer; a legit resume edit that differs
//                                      from the staged value overwrites it in
//                                      place (never a second row).
//   GET  /api/save/resume?tk=<token>   fetch staged answers for this run+phase
//                                      plus a resume hint {total, answered,
//                                      next_index} so the SPA reopens at the
//                                      next unanswered question.
//   POST /api/save/reminder?tk=<token> record an OPTIONAL email for a resume
//                                      reminder. Staged as
//                                      reminder:<run>:<email>. Skippable — the
//                                      completion screen always shows
//                                      "Keep this link — it's your way back"
//                                      with a copy affordance as the default.
//
// The Worker is a DUMB RELAY: zero client PITs. No Anthropic ids anywhere.
//
// KV namespace: BW_BINDINGS (same namespace as U02/U03).
//   consumed:<run>:<phase>:<qid>  -> { ts, qid, status:"consumed" }  (U03 key)
//   save:<client>:<run>:<phase>:<qid> -> { qid, answer, source, saved_at }
//   reminder:<run>:<email>        -> { email, run_id, phase_id, created_at }
//
// Pure decision core (side-effect free) is exported for offline node --test
// against an in-memory KV store (src/save.test.mjs).
// ============================================================================

'use strict';

// ---------------------------------------------------------------------------
// Key builders (match U03's contract exactly)
// ---------------------------------------------------------------------------

export function saveKey(clientId, runId, phaseId, qid) {
  return `save:${clientId}:${runId}:${phaseId}:${qid}`;
}

export function consumedKey(runId, phaseId, qid) {
  return `consumed:${runId}:${phaseId}:${qid}`;
}

export function reminderKey(runId, email) {
  return `reminder:${runId}:${email}`;
}

export function stagedAnswerKey(clientId, runId, phaseId, qid) {
  // U03's /api/answers writes to `answer:<client>:<run>:<phase>:<qid>`. The
  // save/resume reader returns the union of `answer:` (final, from a next tap)
  // and `save:` (draft, persisted on entry) so resume never loses either.
  return `answer:${clientId}:${runId}:${phaseId}:${qid}`;
}

// ---------------------------------------------------------------------------
// Normalization (ONE boundary — mirrors U03's normalizeAnswerValue)
// ---------------------------------------------------------------------------

/**
 * Trim + strip C0 control characters. This is the single normalization point
 * for saved answers (intake-schema.json trailing-space defect set fixed here,
 * never in a prompt).
 */
export function normalizeValue(raw) {
  if (typeof raw !== "string") return raw;
  return raw.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "").trim();
}

export const MAX_SAVE_ANSWER_CHARS = 200 * 1024;

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

export function isValidTokenShape(token) {
  return typeof token === "string" && /^[0-9a-f]{32}$/.test(token);
}

export function isValidEmail(email) {
  if (typeof email !== "string") return false;
  const e = email.trim();
  if (e.length < 3 || e.length > 254) return false;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e)) return false;
  // No bare domain, no spaces, no angle brackets (blocks <script> payloads).
  if (/[<>\s]/.test(e)) return false;
  return true;
}

/**
 * Validate the save payload. Returns { ok, qid, answer, source } or
 * { ok:false, status, error }.
 */
export function validateSavePayload(raw, maxChars = MAX_SAVE_ANSWER_CHARS) {
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
  // Reject injected destination fields at the boundary (isolation by
  // construction — the binding row is the sole authority).
  if ("location_id" in parsed || "contact_id" in parsed || "client_id" in parsed) {
    return { ok: false, status: 400, error: "injected destination rejected" };
  }
  const qid = typeof parsed.question_id === "string" ? normalizeValue(parsed.question_id) : "";
  if (!qid) return { ok: false, status: 400, error: "question_id required" };
  if (!("answer" in parsed)) return { ok: false, status: 400, error: "answer required" };
  const answer = normalizeValue(parsed.answer);
  if (typeof answer === "string" && answer.length > maxChars) {
    return { ok: false, status: 413, error: "answer too large" };
  }
  const source = typeof parsed.source === "string" ? normalizeValue(parsed.source) : "typed";
  return { ok: true, qid, answer, source };
}

// ---------------------------------------------------------------------------
// Pure decision core
// ---------------------------------------------------------------------------

/**
 * Decide how to persist a draft. Pure given the current staged + consumed
 * rows (inject for tests).
 *
 *  - Nothing staged yet, counter free  -> NEW draft (record).
 *  - Counter present, staged identical -> IDEMPOTENT replay (no-op, ok).
 *  - Counter present, staged DIFFERS   -> RESUME EDIT (overwrite in place —
 *    a legit "changed my mind before moving on", never a duplicate row).
 *  - Binding invalid                    -> rejected (no write).
 */
export function decideSave({ binding, qid, answer, source, nowSec, stagedRow, consumedRow }) {
  if (!binding || typeof binding !== "object") {
    return { ok: false, status: 401, error: "invalid or unknown token" };
  }
  if (binding.status === "completed" || binding.status === "done") {
    return { ok: false, status: 410, error: "run already completed" };
  }
  if (typeof binding.exp === "number" && binding.exp > 0 && binding.exp < nowSec) {
    return { ok: false, status: 401, error: "token expired" };
  }
  if (!binding.client_id || !binding.run_id || !binding.phase_id) {
    return { ok: false, status: 401, error: "binding row incomplete" };
  }

  if (consumedRow) {
    const same = stagedRow && stagedRow.answer === answer;
    if (same) {
      // Replay of a save that already landed — no-op, still a success.
      return { ok: true, idempotent: true, changed: false, draft: stagedRow };
    }
    // Legit resume edit: overwrite in place, advance saved_at.
    return {
      ok: true,
      idempotent: false,
      changed: true,
      draft: {
        qid,
        answer,
        source,
        saved_at: nowSec,
        edited_at: nowSec,
      },
    };
  }

  // Fresh draft — record + mark consumed (same counter U03 uses, so a later
  // /api/answers finalize is the only "next" transition).
  return {
    ok: true,
    idempotent: false,
    changed: true,
    draft: {
      qid,
      answer,
      source,
      saved_at: nowSec,
    },
  };
}

/**
 * Compute the resume hint from a list of staged answers. Pure.
 * A question counts as answered only when its staged answer has non-empty
 * text (a queued/processing transcription is NOT a blank, and a draft that was
 * cleared back to "" is NOT answered — matches U05's firstUnansweredIndex).
 * @param {Array} staged   [{qid, answer, ...}, ...]
 * @param {Array} questions config.questions (for total + order)
 * @returns {{total, answered, next_index}}
 */
export function resumeHint(staged, questions) {
  const total = Array.isArray(questions) ? questions.length : (Array.isArray(staged) ? staged.length : 0);
  const byQid = {};
  (staged || []).forEach((s) => {
    if (s && s.qid) byQid[s.qid] = s;
  });
  let answered = 0;
  // -1 sentinel: an unanswered question at index 0 must not be confused with
  // "none found yet".
  let nextIndex = -1;
  if (Array.isArray(questions)) {
    for (let i = 0; i < questions.length; i++) {
      const q = questions[i];
      if (!q || !q.id) continue;
      const s = byQid[q.id];
      if (s && typeof s.answer === "string" && s.answer.length > 0) {
        answered++;
      } else if (nextIndex === -1) {
        nextIndex = i;
      }
    }
  } else if (Array.isArray(staged)) {
    // No ordered question list (resume endpoint without a config): count
    // answered from the staged rows themselves, in staged order.
    for (let i = 0; i < staged.length; i++) {
      const s = staged[i];
      if (!s || !s.qid) continue;
      if (typeof s.answer === "string" && s.answer.length > 0) {
        answered++;
      } else if (nextIndex === -1) {
        nextIndex = i;
      }
    }
  }
  return { total, answered, next_index: nextIndex };
}

// ---------------------------------------------------------------------------
// Storage adapter helpers (KV)
// ---------------------------------------------------------------------------

export async function loadStagedAnswers(store, clientId, runId, phaseId) {
  // KV namespace list is not guaranteed on all KV emulators; we use a prefix
  // list when available, else fall back to the run-manifest of known qids.
  const prefix = `save:${clientId}:${runId}:${phaseId}:`;
  let out = [];
  if (typeof store.list === "function") {
    const listed = await store.list({ prefix });
    for (const key of listed.keys || []) {
      const raw = await store.get(key.name);
      if (raw) {
        try { out.push(JSON.parse(raw)); } catch { /* skip corrupt */ }
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Route handlers
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
 * POST /api/save?tk=<token>
 * Debounced persist of one draft answer (client debounces ~800ms). Stages the
 * draft under save:<client>:<run>:<phase>:<qid> and marks the per-step
 * consumed counter (U03's key) so a replayed save can never duplicate.
 */
export async function handleSavePost(request, env, now = Math.floor(Date.now() / 1000)) {
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
  if (!binding) return jsonResponse({ error: "invalid or unknown token", ok: false }, 401);

  const raw = await request.text();
  const parsed = validateSavePayload(raw);
  if (!parsed.ok) {
    return jsonResponse({ error: parsed.error, ok: false }, parsed.status);
  }
  const { qid, answer, source } = parsed;

  const cKey = consumedKey(binding.run_id, binding.phase_id, qid);
  const sKey = saveKey(binding.client_id, binding.run_id, binding.phase_id, qid);
  const [consumedRow, stagedRow] = await Promise.all([
    kv.get(cKey, { type: "json" }),
    kv.get(sKey, { type: "json" }),
  ]);

  const decision = decideSave({
    binding, qid, answer, source,
    nowSec: now,
    stagedRow,
    consumedRow,
  });
  if (!decision.ok) {
    return jsonResponse({ error: decision.error, ok: false }, decision.status);
  }

  if (decision.changed) {
    // Order: mark consumed BEFORE staging (a crash in between can never leave
    // an un-staged "saved" step).
    await kv.put(cKey, JSON.stringify({ ts: now, qid, status: "consumed" }));
    await kv.put(sKey, JSON.stringify(decision.draft));
  }

  const questions = parsed.questions ? parsed.questions : null;
  return jsonResponse({
    ok: true,
    idempotent: !!decision.idempotent,
    changed: !!decision.changed,
    saved_at: decision.draft.saved_at,
    resume: resumeHint([decision.draft], questions ? questions : [{ id: qid }]),
    qid,
  }, decision.changed ? 201 : 200);
}

/**
 * GET /api/save/resume?tk=<token>
 * Fetch staged answers for the run+phase and a resume hint. The SPA uses it on
 * reopen to resume at the next unanswered question.
 */
export async function handleResumeGet(request, env, now = Math.floor(Date.now() / 1000)) {
  const url = new URL(request.url);
  const token = url.searchParams.get("tk") || "";
  if (!isValidTokenShape(token)) {
    return jsonResponse({ error: "bad token", ok: false }, 400);
  }
  const kv = env.BW_BINDINGS;
  if (!kv || typeof kv.get !== "function") {
    return jsonResponse({ error: "server not configured", ok: false }, 503);
  }
  const binding = await kv.get(`binding:${token}`, { type: "json" });
  if (!binding) return jsonResponse({ error: "invalid or unknown token", ok: false }, 401);
  if (binding.status === "completed" || binding.status === "done") {
    return jsonResponse({ error: "run already completed", ok: false }, 410);
  }
  if (typeof binding.exp === "number" && binding.exp > 0 && binding.exp < now) {
    return jsonResponse({ error: "token expired", ok: false }, 401);
  }

  const staged = await loadStagedAnswers(kv, binding.client_id, binding.run_id, binding.phase_id);
  const answers = {};
  (staged || []).forEach((s) => {
    if (s && s.qid && s.answer !== undefined) answers[s.qid] = { text: s.answer, source: s.source || "saved" };
  });
  return jsonResponse({
    ok: true,
    answers,
    resume: resumeHint(staged, null),
  });
}

/**
 * POST /api/save/reminder?tk=<token>
 * Optional email opt-in for a resume reminder. Skippable — the completion
 * screen's default is "Keep this link — it's your way back".
 */
export async function handleReminderPost(request, env, now = Math.floor(Date.now() / 1000)) {
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
  if (!binding) return jsonResponse({ error: "invalid or unknown token", ok: false }, 401);
  if (binding.status === "completed" || binding.status === "done") {
    return jsonResponse({ error: "run already completed", ok: false }, 410);
  }

  const raw = await request.text();
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return jsonResponse({ error: "invalid JSON body", ok: false }, 400);
  }
  const email = typeof parsed.email === "string" ? parsed.email.trim() : "";
  if (!isValidEmail(email)) {
    return jsonResponse({ error: "email not valid", ok: false }, 400);
  }

  const row = { email, run_id: binding.run_id, phase_id: binding.phase_id, created_at: now };
  await kv.put(reminderKey(binding.run_id, email), JSON.stringify(row));
  return jsonResponse({
    ok: true,
    reminder: { run_id: binding.run_id, phase_id: binding.phase_id, email_stored: true },
  }, 201);
}

// ---------------------------------------------------------------------------
// Self-test entry (node src/save.js --selftest) + exports
// ---------------------------------------------------------------------------

export function selfTest() {
  const results = [];
  const binding = { client_id: "c", run_id: "r", phase_id: "p", exp: 9999999999, status: "open" };

  const fresh = decideSave({ binding, qid: "q", answer: "hi", source: "typed", nowSec: 1, stagedRow: null, consumedRow: null });
  results.push(["fresh save accepted", fresh.ok === true && fresh.changed === true]);

  const replay = decideSave({ binding, qid: "q", answer: "hi", source: "typed", nowSec: 2, stagedRow: { answer: "hi" }, consumedRow: { status: "consumed" } });
  results.push(["idempotent replay is a no-op", replay.ok === true && replay.idempotent === true && replay.changed === false]);

  const edit = decideSave({ binding, qid: "q", answer: "hello there", source: "typed", nowSec: 3, stagedRow: { answer: "hi" }, consumedRow: { status: "consumed" } });
  results.push(["resume edit overwrites in place", edit.ok === true && edit.changed === true && edit.draft.answer === "hello there"]);

  const expired = decideSave({ binding: { ...binding, exp: 5 }, qid: "q", answer: "x", source: "typed", nowSec: 10, stagedRow: null, consumedRow: null });
  results.push(["expired token rejected", expired.ok === false && expired.status === 401]);

  const done = decideSave({ binding: { ...binding, status: "done" }, qid: "q", answer: "x", source: "typed", nowSec: 10, stagedRow: null, consumedRow: null });
  results.push(["completed run rejected", done.ok === false && done.status === 410]);

  const injected = validateSavePayload(JSON.stringify({ question_id: "q", answer: "x", location_id: "l" }));
  results.push(["injected destination rejected", injected.ok === false]);

  results.push(["email valid", isValidEmail("reader@example.com") === true]);
  results.push(["email invalid", isValidEmail("not-an-email") === false]);
  results.push(["email blocks markup", isValidEmail("<script>@x.com") === false]);

  const hint = resumeHint(
    [{ qid: "a", answer: "done" }, { qid: "c", answer: "" }],
    [{ id: "a" }, { id: "b" }, { id: "c" }]
  );
  results.push(["resume hint: 1 answered of 3, next index 1", hint.answered === 1 && hint.total === 3 && hint.next_index === 1]);

  const hint0 = resumeHint([], [{ id: "a" }, { id: "b" }]);
  results.push(["resume hint: zero staged, next index 0", hint0.answered === 0 && hint0.next_index === 0]);

  const hintIdx0 = resumeHint([{ qid: "a", answer: "done" }], [{ id: "a" }, { id: "b" }]);
  results.push(["resume hint: index 0 answered, next index 1", hintIdx0.answered === 1 && hintIdx0.next_index === 1]);

  const pass = results.every((r) => r[1]);
  const lines = results.map((r) => (r[1] ? "PASS" : "FAIL") + "  " + r[0]);
  lines.forEach((l) => console.log(l));
  console.log(pass ? "U11 save & resume self-test: PASS" : "U11 save & resume self-test: FAIL");
  if (!pass) process.exitCode = 2;
  return pass;
}

if (typeof process !== "undefined" && process.argv && process.argv.indexOf("--selftest") !== -1) {
  selfTest();
}
