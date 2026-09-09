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
// COMMAND_CENTER_URL (CC board base URL), CC_DEPT_START_TOKEN (CC ingest auth).

import {
  randomToken, sixDigitCode, nowSeconds, expiryFrom, isValidTokenShape,
  validateQuestionsPayload, checkAnswerOrder, validateAnswerValue,
  answersSince, progress, jsonResponse, errorResponse, isQuestionActive,
  DEFAULT_TTL_DAYS,
} from "./lib.js";
import {
  sessionKey, intakeIndexKey,
  newSessionRecord, loadSession, claimRunActiveSlot,
  idempotentOnce, answersValueMap, answersIdList,
  loadAnswersRecord, applyAnswerCAS, emptyAnswersRecord,
  appendOutboxEvent,
  indexIntakeRow, listPendingIntakes, claimIndexRow, ackIndexRow,
  casUpdate,
} from "./authority.js";

const INTAKE_PREFIX = "intakes/";
const OUTBOX_PREFIX = "outboxes/";

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
  if (parts.length === 4 && parts[3] === "complete" && method === "POST") return completeSession(request, env, token);
  if (parts.length === 4 && parts[3] === "outbox" && method === "GET") return outboxStatus(env, token);
  return errorResponse("not found", 404);
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
  const runId = body.run_id, boxId = body.box_id, payload = body.questions_payload;
  if (typeof runId !== "string" || !runId) return errorResponse("run_id required", 400);
  if (typeof boxId !== "string" || !boxId) return errorResponse("box_id required", 400);
  const check = validateQuestionsPayload(payload);
  if (!check.ok) return errorResponse("questions_payload invalid: " + check.error, 400);
  const created = nowSeconds();

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
  const ttlDays = Number.isFinite(body.ttl_days) ? body.ttl_days : DEFAULT_TTL_DAYS;
  const expires = expiryFrom(created, ttlDays);
  const confirmCode = body.want_confirm_code ? sixDigitCode() : null;
  const session = newSessionRecord({
    token: newToken, run_id: runId, box_id: boxId, question_set: payload.question_set,
    questions_json: JSON.stringify(payload), confirm_code: confirmCode,
    created, expires,
  });

  // Serialize the run slot BEFORE publishing the session: the pointer CAS is
  // the single winner gate. The pointer winner publishes its session; every
  // loser re-reads the pointer and replays the winner's token.
  const claimed = await claimRunActiveSlot(bucket, runId, newToken, expires);
  if (!claimed) return errorResponse("session slot busy — retry", 503);
  if (claimed.value && claimed.value.token !== newToken) {
    // Another concurrent mint won the slot (or a live session already held
    // it): replay the winner's token — one active session per run.
    const winnerToken = claimed.value.token;
    const winner = await loadSession(bucket, winnerToken);
    if (winner && winner.value) {
      return jsonResponse({ status: "exists", token: winnerToken, capability_url: capabilityUrl(request, winnerToken), reused: true });
    }
    // Pointer names a vanished session: retire the pointer and retry once.
    const retried = await claimRunActiveSlot(bucket, runId, newToken, expires, { force: true });
    if (!retried || (retried.value && retried.value.token !== newToken)) {
      return errorResponse("session slot busy — retry", 503);
    }
  }

  // Expire any PREVIOUS pointer session this mint replaced (completed/expired
  // sessions are already terminal; this only matters for a force-retake of a
  // stale pointer, and runs only on the pointer winner's path).
  const prevPointerToken = claimed.value && claimed.value.token !== newToken ? claimed.value.token : null;
  if (prevPointerToken) {
    await expirePreviousSession(bucket, prevPointerToken);
  }

  // Publish the session record. Create-if-not-exists: a fresh token can never
  // collide, but the create semantics keep the invariant auditable.
  const pub = await bucket.put(sessionKey(newToken), JSON.stringify(session), { onlyIf: { etagDoesNotMatch: "*" } });
  if (!pub) return errorResponse("session slot busy — retry", 503);

  return jsonResponse({ status: "created", token: newToken, capability_url: capabilityUrl(request, newToken), confirm_code: confirmCode, expires_at: expires }, 201);
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

async function getSession(env, token) {
  const row = await loadOpenSession(env, token); if (row.error) return row.error;
  const { session, payload } = row;
  const answersRec = await loadAnswersRecord(env.STORE, token);
  const answeredIds = answersIdList(answersRec.value);
  const answeredValues = answersValueMap(answersRec.value);
  return jsonResponse({ status: session.status, run_id: session.run_id, question_set: session.question_set, questions: payload.questions, progress: progress(payload, answeredIds, answeredValues), answered: answeredIds, requires_confirm_code: !!session.confirm_code, expires_at: session.expires_at });
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

  const res = await applyAnswerCAS(bucket, token, decide);
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
  const since = Number(new URL(request.url).searchParams.get("since") || 0);
  const answersRec = await loadAnswersRecord(env.STORE, token);
  const rows = (answersRec.value && answersRec.value.answers) || [];
  const fresh = answersSince(rows, since);
  const answeredIds = rows.map((r) => r.question_id);
  const answeredValues = {}; for (const r of rows) answeredValues[r.question_id] = r.value;
  return jsonResponse({ status: "ok", session_status: session.status, cursor: rows.length ? Number(rows[rows.length - 1].id) : since, answers: fresh.map((r) => ({ id: Number(r.id), question_id: r.question_id, value: r.value, created_at: Number(r.created_at) })), progress: progress(payload, answeredIds, answeredValues) });
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
  const answersRec = await loadAnswersRecord(bucket, token);
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
    const session_id = "sess-" + token;
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
      await storePutJson(env, intakeKey(outbox.session_id), {
        session_id: outbox.session_id, file_name: outbox.file_name,
        intake: outbox.intake, stored_at: nowSeconds(),
      });
      // PRES-023: the enqueued intake lands on the paginated pending index the
      // box bridge discovers — same row shape POST /api/intake produces.
      await indexIntakeRow(env.STORE, outbox.session_id, outbox.file_name, nowSeconds());
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
    intake_session_id: "sess-" + session.token,
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
  const file_name = (body.file_name || "intake.json").replace(/[^A-Za-z0-9._-]/g, "");
  const session_id = intake.intake_session_id || file_name.replace(/\..+$/, "");
  const created = nowSeconds();
  const key = intakeKey(session_id);
  await env.STORE.put(key, JSON.stringify({ session_id, file_name, intake, stored_at: created }));
  await indexIntakeRow(env.STORE, session_id, file_name, created);
  return jsonResponse({ status: "stored", session_id, file_name, stored_at: created }, 201);
}

/**
 * GET /api/intake?id=<session> — fetch a stored intake for the box bridge.
 * This fetch is the worker-accepted signal: it flips the session's completion
 * outbox to worker_accepted (best-effort, non-fatal on miss).
 */
async function fetchIntake(request, env) {
  if (!requireAdmin(request, env)) return errorResponse("unauthorized", 401);
  const id = new URL(request.url).searchParams.get("id");
  if (!id) return errorResponse("id query param required", 400);
  const key = intakeKey(id);
  const obj = await env.STORE.get(key);
  if (!obj) return errorResponse("intake not found", 404);
  await markOutboxAccepted(env, id);
  const text = await obj.text();
  let parsed; try { parsed = JSON.parse(text); } catch { return errorResponse("corrupt intake record", 500); }
  return jsonResponse(parsed, 200);
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
  const bucket = env.STORE;
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
    const storedObj = await env.STORE.get(key);
    let storedJson = null; if (storedObj) { try { storedJson = JSON.parse(await storedObj.text()); } catch { storedJson = null; } }
    await env.STORE.put(key, JSON.stringify(Object.assign({}, storedJson || {}, {
      session_id, file_name: (storedJson && storedJson.file_name) || "intake.json",
      dept_trigger: "deferred",
      dept_trigger_note: "COMMAND_CENTER_URL unset — box-side cc_board.ingest_deck_task will create the card",
      updated_at: nowSeconds(),
    })));
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
      const storedObj = await env.STORE.get(key);
      let storedJson = null; if (storedObj) { try { storedJson = JSON.parse(await storedObj.text()); } catch { storedJson = null; } }
      await env.STORE.put(key, JSON.stringify(Object.assign({}, storedJson || {}, {
        session_id, file_name: (storedJson && storedJson.file_name) || "intake.json",
        dept_trigger: "fired", dept_task_id: String(data.task_id), updated_at: nowSeconds(),
      })));
      return jsonResponse({ status: "fired", session_id, task_id: data.task_id, deduped: !!data.deduped }, 201);
    }
    return errorResponse("dept start failed (HTTP " + resp.status + "): " + (data.error || "unknown"), 502);
  } catch (err) {
    return errorResponse("dept start transport error: " + (err && err.message ? err.message : "network"), 502);
  }
}

// ---- session helpers --------------------------------------------------------

async function loadOpenSession(env, token, allowComplete = false) {
  const row = await loadSession(env.STORE, token);
  if (!row || !row.value) return { error: errorResponse("session not found", 404) };
  const session = row.value;
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
