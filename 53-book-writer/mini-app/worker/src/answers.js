// Book Writer Mini-App — Worker answers POST (U03).
//
// The edge Worker is a DUMB RELAY and holds ZERO client GHL credentials. The
// server-side KV binding row is the SOLE authority for the destination of an
// answer: any `location_id` / `contact_id` / `client_id` injected into the
// request body is IGNORED. A client's answers are staged in per-client R2/KV
// under the token-bound client's own prefix and are picked up later by the box
// ingest poller (U12) which owns the GHL write via Skill 44 rails.
//
// Endpoints:
//   POST /api/answers?tk=<token>   record one answer for the token-bound run
//                                  (idempotent; replay of a consumed step is
//                                  rejected, never duplicated)
//
// KV bindings (wrangler.toml):
//   BW_BINDINGS — key layout:
//     binding:<token>                 -> { client_id, location_id, phase_id,
//                                          run_id, intake_id, exp, status, ... }
//     consumed:<run_id>:<phase_id>:<qid> -> "1"   (per-step consumed counter,
//                                                  idempotency lock)
//     answer:<client_id>:<run_id>:<phase_id>:<qid> -> { qid, answer, ts,
//                                          source, received_at }  (staged answer)
//   BW_MEDIA (R2, optional this unit) — media staging happens in U04; this
//   unit stores TEXT answers and stage-references only.
//
// Secrets: none at this layer (no PITs on the edge by construction).
//
// Module shape:
//   - `handleAnswersPost(request, env)` — the Worker route, composes the pure
//     core with KV.
//   - `processAnswer(core, ctx)` — pure, side-effect-free decision core; every
//     branch is unit-tested offline with `node --test` and a stubbed KV.
//   - `normalizeAnswerValue` — the ONE normalization boundary (mirrors the
//     intake-schema note: trailing-space keys are fixed here, never in prompts).

/** UUID for answer_id — Cloudflare Workers expose crypto.randomUUID; fall back
 *  to a hex token if absent (tests run under Node 22 where it exists). */
function makeAnswerId() {
  if (typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  const buf = new Uint8Array(16);
  if (typeof globalThis.crypto !== "undefined" && typeof globalThis.crypto.getRandomValues === "function") {
    globalThis.crypto.getRandomValues(buf);
  } else {
    for (let i = 0; i < buf.length; i += 1) buf[i] = Math.floor(Math.random() * 256);
  }
  return [...buf].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Token shape: opaque 32 lowercase-hex chars (matches the minting unit). */
const TOKEN_RE = /^[0-9a-f]{32}$/;

/** Max raw body bytes for an answers POST (generous for audio/video refs). */
const MAX_BODY_BYTES = 300 * 1024;

// ---------------------------------------------------------------------------
// Normalization (ONE boundary — matches intake-schema.json's contract: keys
// with trailing/leading spaces such as 'firstname ' / 'Idealavatar ' are fixed
// here and never reach a prompt).
// ---------------------------------------------------------------------------

/** Trim whitespace from string answers; leave non-strings untouched. */
export function normalizeAnswerValue(raw) {
  if (typeof raw !== "string") return raw;
  // Strip C0 control chars (NUL..BS, VT, FF, SO..US, DEL) via explicit hex
  // ranges — no literal control bytes in the source — then trim surrounding
  // whitespace. This is the ONE normalization boundary (intake-schema.json).
  return raw.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "").trim();
}

/** Strip trailing/leading whitespace from a raw object's keys and trim values. */
export function normalizeAnswerObject(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return raw;
  const out = {};
  for (const [k, v] of Object.entries(raw)) {
    const cleanKey = normalizeAnswerValue(k);
    if (!cleanKey) continue; // empty key after trim — drop
    if (cleanKey === "location_id" || cleanKey === "contact_id" || cleanKey === "client_id") {
      // INJECTED DESTINATION — never copied into the staged answer. The KV
      // binding row is the sole authority; these are IGNORED by construction.
      continue;
    }
    out[cleanKey] = normalizeAnswerValue(v);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/** Cheap pre-KV token shape guard (mint-time check; not an authority check). */
export function isValidTokenShape(token) {
  return typeof token === "string" && TOKEN_RE.test(token);
}

/**
 * Validate + normalize the raw request body. Returns { ok, body } or
 * { ok:false, error }.
 */
export function validateAnswersPayload(raw) {
  if (typeof raw !== "string" || raw.length > MAX_BODY_BYTES) {
    return { ok: false, error: "body too large or missing" };
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false, error: "invalid JSON body" };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, error: "body must be a JSON object" };
  }
  const qid = typeof parsed.question_id === "string" ? parsed.question_id.trim() : "";
  if (!qid) return { ok: false, error: "question_id required" };
  if (!("answer" in parsed)) return { ok: false, error: "answer required" };
  if (parsed.source !== undefined && typeof parsed.source !== "string") {
    return { ok: false, error: "source must be a string when present" };
  }
  const body = normalizeAnswerObject(parsed);
  // Re-check after normalization: answer may be any type (string/object/array).
  if (!("answer" in body)) return { ok: false, error: "answer required" };
  return { ok: true, body };
}

// ---------------------------------------------------------------------------
// Pure decision core
// ---------------------------------------------------------------------------

/**
 * Check whether the token's binding row allows a new answer for this step.
 * Returns { ok:true } if the binding is valid/open; otherwise a 4xx response
 * (401 tampered/expired, 409 consumed, 410 binding completed).
 */
export function checkBinding(binding) {
  if (!binding || typeof binding !== "object") {
    return { ok: false, error: "invalid or unknown token", status: 401 };
  }
  if (binding.status === "completed" || binding.status === "done") {
    return { ok: false, error: "run already completed", status: 410 };
  }
  if (typeof binding.exp === "number" && binding.exp > 0 && binding.exp < Math.floor(Date.now() / 1000)) {
    return { ok: false, error: "token expired", status: 401 };
  }
  if (!binding.client_id || !binding.run_id || !binding.phase_id) {
    return { ok: false, error: "binding row incomplete", status: 401 };
  }
  return { ok: true };
}

/**
 * Build the per-step consumed-counter key and staged-answer key.
 */
export function answerKeys(binding, qid) {
  const runId = binding.run_id;
  const phaseId = binding.phase_id;
  const consumed = `consumed:${runId}:${phaseId}:${qid}`;
  const staged = `answer:${binding.client_id}:${runId}:${phaseId}:${qid}`;
  return { consumed, staged };
}

/**
 * The idempotency + staging decision. Pure given `nowSec` (inject for tests).
 * `stagedExisting` is the KV value currently at the staged key (null if none).
 * `consumedExisting` is the KV value at the consumed key (null if none).
 */
export function decideSubmit({ binding, qid, normalized, nowSec, stagedExisting, consumedExisting }) {
  const bindingCheck = checkBinding(binding);
  if (!bindingCheck.ok) return bindingCheck;

  if (typeof qid !== "string" || !qid) {
    return { ok: false, error: "question_id required", status: 400 };
  }
  // Normalize the qid itself so 'first_name ' and 'first_name' are the same step.
  qid = qid.trim();

  // IDEMPOTENCY: a consumed step cannot be submitted again — a replayed submit
  // of an already-consumed step is rejected, never duplicated.
  if (consumedExisting != null || stagedExisting != null) {
    return {
      ok: false,
      error: "step already answered",
      status: 409,
      receipt: {
        qid,
        already_recorded: true,
        staged_key: stagedKeyFor(binding, qid),
      },
    };
  }

  const answer = {
    qid,
    answer: normalized.answer,
    source: typeof normalized.source === "string" ? normalized.source : "typed",
    received_at: nowSec,
    answer_id: makeAnswerId(),
    // Destination authority lives on the binding row ONLY. We record the
    // bound destination for the box poller — never any injected value.
    destination: {
      client_id: binding.client_id,
      location_id: binding.location_id || null,
      phase_id: binding.phase_id,
      run_id: binding.run_id,
      intake_id: binding.intake_id || null,
    },
  };

  return { ok: true, answer };
}

/** Pure helper so the reject path can reference the key (used in tests). */
export function stagedKeyFor(binding, qid) {
  return answerKeys(binding, qid.trim()).staged;
}

// ---------------------------------------------------------------------------
// Worker entry
// ---------------------------------------------------------------------------

async function readBodyBytes(request) {
  const buf = await request.arrayBuffer();
  return new TextDecoder().decode(buf);
}

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

function donePageHtml() {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Received — your answer is safe</title>
<style>
  body{margin:0;font-family:Georgia,serif;background:#FBF6EE;color:#3B2A1E;display:flex;
       min-height:100vh;align-items:center;justify-content:center;padding:24px}
  .card{max-width:560px;background:#fffdf8;border:1px solid #E8DCC8;border-radius:16px;
        padding:40px 32px;text-align:center;box-shadow:0 8px 24px rgba(59,42,30,.08)}
  h1{font-size:1.6rem;margin:0 0 12px;color:#C96F4A}
  p{font-size:1.05rem;line-height:1.6;color:#5A4633;margin:0}
  .book{font-size:2.4rem;margin-bottom:12px}
</style></head>
<body><main class="card">
  <div class="book">📖</div>
  <h1>Received — thank you.</h1>
  <p>Your answer is safe. You can close this page or come back to this link anytime —
     you'll pick up right where you left off.</p>
</main></body></html>`;
}

/**
 * POST /api/answers?tk=<token>
 * Re-validates token binding, normalizes the answer, enforces the per-step
 * consumed counter (idempotent — a replayed submit cannot duplicate), stages
 * the answer to per-client KV, and returns a receipt.
 */
export async function handleAnswersPost(request, env, now = Math.floor(Date.now() / 1000)) {
  const url = new URL(request.url);
  const token = url.searchParams.get("tk") || "";

  if (!isValidTokenShape(token)) {
    return jsonResponse({ error: "bad token", ok: false }, 400);
  }

  const kv = env.BW_BINDINGS;
  if (!kv || typeof kv.get !== "function" || typeof kv.put !== "function") {
    return jsonResponse({ error: "server not configured", ok: false }, 503);
  }

  // 1. Re-validate the token binding row (the SOLE authority).
  const binding = await kv.get(`binding:${token}`, { type: "json" });
  const bindingCheck = checkBinding(binding);
  if (!bindingCheck.ok) {
    return jsonResponse({ error: bindingCheck.error, ok: false }, bindingCheck.status);
  }

  // 2. Read + validate + normalize the payload.
  const raw = await readBodyBytes(request);
  const parsed = validateAnswersPayload(raw);
  if (!parsed.ok) {
    return jsonResponse({ error: parsed.error, ok: false }, 400);
  }
  const { body } = parsed;
  const qid = body.question_id;

  // 3. Load the per-step consumed counter + staged answer (idempotency check).
  const { consumed, staged } = answerKeys(binding, qid);
  const [consumedExisting, stagedExisting] = await Promise.all([
    kv.get(consumed, { type: "json" }),
    kv.get(staged, { type: "json" }),
  ]);

  const decision = decideSubmit({ binding, qid, normalized: body, nowSec: now, stagedExisting, consumedExisting });
  if (!decision.ok) {
    return jsonResponse({ error: decision.error, ok: false, receipt: decision.receipt }, decision.status);
  }

  // 4. Store the answer to per-client KV. Order: mark consumed BEFORE staging
  //    so a crash between the two cannot leave an un-staged "answered" step.
  await kv.put(consumed, JSON.stringify({ ts: now, qid: decision.answer.qid, status: "consumed" }));
  await kv.put(staged, JSON.stringify(decision.answer));

  // 5. Receipt + done page.
  return jsonResponse({
    ok: true,
    receipt: {
      answer_id: decision.answer.answer_id,
      qid: decision.answer.qid,
      client_id: binding.client_id,
      phase_id: binding.phase_id,
      run_id: binding.run_id,
      intake_id: binding.intake_id || null,
      received_at: decision.answer.received_at,
    },
    done_page: "/done",
  }, 201);
}

/** Response for the done page (SPA owns the route; a bare GET is harmless). */
export function donePageResponse() {
  return new Response(donePageHtml(), {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}
