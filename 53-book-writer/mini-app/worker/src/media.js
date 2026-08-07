// Book Writer mini-app — media upload endpoint (U04).
//
// POST /api/media — Worker media upload (MASTER-PLAN section 4).
//
// Endpoints:
//   POST /api/media/upload            -> accept + validate an upload, create the
//                                        queued job, return a presigned DIRECT
//                                        R2 PUT url (bytes never ride a Worker
//                                        request body — section 4).
//   POST /api/media/:answerId/complete -> mark a job done WITH non-empty text
//                                        (or explicit N/A). Empty text fails
//                                        closed with AF-BW-MA-EXTRACT-NO-TEXT.
//   POST /api/media/:answerId/fail     -> mark a job failed (retry surfaces).
//   GET  /api/media/:answerId          -> job poll view (queued/processing ->
//                                        "Transcribing…" pill; failed -> retry;
//                                        done -> editable text; never blank).
//
// The Worker is a DUMB RELAY: it holds ZERO client PITs, stages bytes to R2 and
// the job row to KV, and never transcribes (transcription is box-side, U13,
// provider-neutral, hard non-Anthropic). An uploaded answer can never fabricate
// a receipt — the intake-assembly gate (media-lib.fieldPresent) requires a
// `done` job with non-empty text.
//
// Bindings (see wrangler.toml): R2 bucket `MEDIA_BUCKET`, KV `MEDIA_JOBS`.
// No real zone/account ids here — wrangler.toml carries <PLACEHOLDER> only.
// No Anthropic ids anywhere.

import {
  buildQueuedJob,
  cleanText,
  fieldPresent,
  intakeGateVerdict,
  pollView,
  randomObjectKey,
  transitionJob,
  validateUpload,
} from "./media-lib.js";

// Session is the run/binding context that scopes the R2 object key.
// In production it comes from the validated KV token binding
// (client_id/run_id). The endpoint accepts it in the body so the pure module
// stays offline-testable; the Worker's index.js is responsible for deriving it
// from the validated token and rejecting unknown/mismatched sessions.
function deriveSession(body) {
  if (typeof body.session === "string" && body.session) return body.session;
  if (typeof body.run_id === "string" && body.run_id) return body.run_id;
  return null;
}

// ---------------------------------------------------------------------------
// Upload acceptance
// ---------------------------------------------------------------------------

/**
 * Accept an upload: validate shape (channel, extension, size, content-type,
 * magic bytes), create the queued job, mint a presigned R2 PUT url.
 * Bytes are uploaded by the CLIENT directly to R2 via the presigned url; the
 * Worker only ever stores {source_uri, source_sha256, status: queued}.
 */
export async function acceptUpload({ body, env, nowUtc = new Date().toISOString(), entropyHex }) {
  if (!body || typeof body !== "object") {
    return { ok: false, status: 400, error: "AF-BW-MA-REJECT-FIELD", message: "Request body must be JSON." };
  }
  const channel = body.channel;
  const filename = typeof body.filename === "string" ? body.filename : "";
  const session = deriveSession(body);
  if (!session) {
    return { ok: false, status: 400, error: "AF-BW-MA-REJECT-FIELD", message: "session (or run_id) is required." };
  }
  if (!body.answer_id || typeof body.answer_id !== "string") {
    return { ok: false, status: 400, error: "AF-BW-MA-REJECT-FIELD", message: "answer_id is required." };
  }

  const check = validateUpload({
    channel,
    filename,
    sizeBytes: body.size_bytes,
    contentType: body.content_type,
    headerBytes: body.header_bytes,
  });
  if (!check.ok) {
    // REJECT-FORMAT / REJECT-SIZE / REJECT-FIELD — a named code always surfaces
    // to the client; never a silent blank.
    return { ok: false, status: 422, error: `AF-BW-MA-${check.code}`, message: check.message };
  }

  const ext = filename.toLowerCase().split(".").pop();
  const objectKey = randomObjectKey(session, ext, entropyHex);

  const job = buildQueuedJob({
    intakeId: session,
    answerId: body.answer_id,
    channel,
    sourceUri: `r2://${objectKey}`,
    sourceSha256: typeof body.source_sha256 === "string" ? body.source_sha256 : null,
    contentType: body.content_type || null,
    sizeBytes: body.size_bytes || null,
    createdAtUtc: nowUtc,
  });

  // Persist the queued job BEFORE handing out the presigned url, so a client
  // that uploads then crashes still has a pollable job (never a silent blank).
  await env.MEDIA_JOBS.put(`media:${body.answer_id}`, JSON.stringify(job));
  await env.MEDIA_JOBS.put(`media:index:${session}`, JSON.stringify([...(await indexList(env, session)), body.answer_id]));

  const presigned = await presignPut(env, objectKey, body.content_type);
  if (!presigned.ok) {
    // R2 creds unavailable -> park the job as failed with a surfaced retry,
    // never a silent blank.
    const failed = transitionJob(job, "fail", { error: `R2 not configured (${presigned.error})`, nowUtc });
    await env.MEDIA_JOBS.put(`media:${body.answer_id}`, JSON.stringify(failed.job));
    return { ok: false, status: 503, error: "AF-BW-MA-CAPABILITY", message: "Upload storage is not ready. Please try again shortly." };
  }

  return {
    ok: true,
    status: 201,
    job,
    view: pollView(job),
    upload: presigned.upload,
  };
}

async function indexList(env, session) {
  try {
    const raw = await env.MEDIA_JOBS.get(`media:index:${session}`);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Presigned R2 PUT (S3-compatible API). Placeholder ids only — the worker
// reads real creds from bound secrets, never from source.
// ---------------------------------------------------------------------------
export async function presignPut(env, objectKey, contentType) {
  const accountId = env.R2_ACCOUNT_ID || "<PLACEHOLDER>";
  const accessKeyId = env.R2_ACCESS_KEY_ID || "<PLACEHOLDER>";
  const secretAccessKey = env.R2_SECRET_ACCESS_KEY || "<PLACEHOLDER>";
  const bucket = env.MEDIA_BUCKET_NAME || "zhw-bookwriter";
  if (accountId.startsWith("<") || accessKeyId.startsWith("<") || secretAccessKey.startsWith("<")) {
    return { ok: false, error: "R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY not set" };
  }
  // S3-compatible presigned PUT. This is the documented Cloudflare R2 pattern:
  //   PUT  https://<ACCOUNT_ID>.r2.cloudflarestorage.com/<BUCKET>/<KEY>
  // Signing uses the standard AWS SigV4 shape against the R2 endpoint.
  const host = `${accountId}.r2.cloudflarestorage.com`;
  const path = `/${bucket}/${objectKey}`;
  const amzDate = new Date().toISOString().replace(/[:-]|\.\d{3}/g, "");
  const dateStamp = amzDate.slice(0, 8);
  const scope = `${dateStamp}/auto/s3/aws4_request`;
  const payloadHash = "UNSIGNED-PAYLOAD";

  const query = [
    "X-Amz-Algorithm=AWS4-HMAC-SHA256",
    `X-Amz-Credential=${encodeURIComponent(`${accessKeyId}/${scope}`)}`,
    `X-Amz-Date=${amzDate}`,
    "X-Amz-Expires=3600",
    "X-Amz-SignedHeaders=host",
  ].sort().join("&");

  const canonicalRequest = ["PUT", path, query, `host:${host}`, "", "host", payloadHash].join("\n");
  const stringToSign = ["AWS4-HMAC-SHA256", amzDate, scope, await hexSha256(canonicalRequest)].join("\n");

  const signature = await hmacHex(
    await hmacHex(await hmacHex(await hmacHex(`AWS4${secretAccessKey}`, dateStamp), "auto"), "s3"),
    stringToSign
  );

  const url = `https://${host}${path}?${query}&X-Amz-Signature=${signature}`;
  return { ok: true, upload: { method: "PUT", url, contentType, expires_in: 3600 } };
}

// ---------------------------------------------------------------------------
// Crypto helpers — Web Crypto only (runs identically in Cloudflare Workers and
// Node 18+). No node:crypto, no Anthropic, no secrets printed.
// ---------------------------------------------------------------------------
async function hexSha256(input) {
  const data = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacHex(key, input) {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey(
    "raw",
    enc.encode(key),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", k, enc.encode(input));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ---------------------------------------------------------------------------
// Job lifecycle endpoints
// ---------------------------------------------------------------------------

/** Mark a job done with non-empty text (or explicit N/A). */
export async function completeJob({ env, answerId, body, nowUtc = new Date().toISOString() }) {
  const raw = await env.MEDIA_JOBS.get(`media:${answerId}`);
  if (!raw) return { ok: false, status: 404, error: "AF-BW-MA-JOB-PENDING", message: "Job not found." };
  const job = JSON.parse(raw);
  const res = transitionJob(job, "complete", {
    text: body.text,
    transcriptJson: body.transcript_json || null,
    stillFrame: body.still_frame || null,
    nowUtc,
    capKey: body.cap_key || "default",
  });
  if (!res.ok) {
    if (res.error === "AF-BW-MA-EXTRACT-NO-TEXT") {
      // Never a silent blank: record the failed state so the client sees retry.
      const failed = transitionJob(job, "fail", { error: "EXTRACT-NO-TEXT", nowUtc });
      await env.MEDIA_JOBS.put(`media:${answerId}`, JSON.stringify(failed.job));
      return { ok: false, status: 422, error: "AF-BW-MA-EXTRACT-NO-TEXT", message: "Your recording produced no text. Please re-record or type it instead.", view: pollView(failed.job) };
    }
    return { ok: false, status: 409, error: res.error, message: `Illegal transition from ${job.status}.` };
  }
  await env.MEDIA_JOBS.put(`media:${answerId}`, JSON.stringify(res.job));
  return { ok: true, status: 200, job: res.job, view: pollView(res.job) };
}

/** Mark a job failed; the error surfaces for retry (never a silent blank). */
export async function failJob({ env, answerId, body, nowUtc = new Date().toISOString() }) {
  const raw = await env.MEDIA_JOBS.get(`media:${answerId}`);
  if (!raw) return { ok: false, status: 404, error: "AF-BW-MA-JOB-PENDING", message: "Job not found." };
  const job = JSON.parse(raw);
  const res = transitionJob(job, "fail", {
    error: typeof body.error === "string" && body.error ? body.error : "transcription failed",
    nowUtc,
  });
  if (!res.ok) return { ok: false, status: 409, error: res.error, message: `Cannot fail a job in state ${job.status}.` };
  await env.MEDIA_JOBS.put(`media:${answerId}`, JSON.stringify(res.job));
  return { ok: true, status: 200, job: res.job, view: pollView(res.job) };
}

/** Poll a job: returns the field-present verdict + pill view. */
export async function pollJob({ env, answerId }) {
  const raw = await env.MEDIA_JOBS.get(`media:${answerId}`);
  if (!raw) return { ok: true, status: 200, job: null, present: "missing", view: pollView(null) };
  const job = JSON.parse(raw);
  return { ok: true, status: 200, job, present: fieldPresent(job), view: pollView(job) };
}

/** Intake-assembly gate over all media jobs for a run. */
export async function assemblyGate({ env, session }) {
  const answerIds = await indexList(env, session);
  const jobs = {};
  for (const id of answerIds) {
    const raw = await env.MEDIA_JOBS.get(`media:${id}`);
    if (raw) jobs[id] = JSON.parse(raw);
  }
  return intakeGateVerdict(jobs);
}

// ---------------------------------------------------------------------------
// Self-test (--self-test). Exercises the three states the unit gates on:
// upload -> queued; completion -> done with text; failure -> failed. Asserts
// the field-present gate: pending/failed never read as present, done-with-text
// does, and a blank completion is impossible.
// ---------------------------------------------------------------------------
export async function selfTest() {
  const failures = [];
  const mem = new Map();
  const env = {
    MEDIA_JOBS: {
      async put(k, v) { mem.set(k, v); },
      async get(k) { return mem.get(k) ?? null; },
    },
    // Fake R2 credentials so the happy path exercises the presigned-URL mint.
    R2_ACCOUNT_ID: "fakeaccountid",
    R2_ACCESS_KEY_ID: "fakeaccesskey",
    R2_SECRET_ACCESS_KEY: "fakesecret",
    MEDIA_BUCKET_NAME: "zhw-bookwriter",
  };

  // 1) upload -> queued job
  const up = await acceptUpload({
    env,
    body: {
      session: "sess-A", answer_id: "story-1", channel: "audio",
      filename: "rec.webm", size_bytes: 4096, content_type: "audio/webm",
      header_bytes: [0x1a, 0x45, 0xdf, 0xa3, 0x01],
      source_sha256: "abc123",
    },
    nowUtc: "2026-08-07T00:00:00.000Z",
    entropyHex: "e1e2e3e4e5e6e7e8e9eaebecedeeeff0",
  });
  if (!up.ok) failures.push(`upload failed: ${up.message}`);
  else if (up.job.status !== "queued") failures.push(`expected queued, got ${up.job.status}`);
  else if (up.view.pill !== "Transcribing…") failures.push(`pending pill should be Transcribing…, got "${up.view.pill}"`);

  // queued must NOT be present for the intake gate
  const preGate = await assemblyGate({ env, session: "sess-A" });
  if (preGate.verdict !== "blocked") failures.push(`queued-only gate should be blocked, got ${preGate.verdict}`);

  // 2) completion -> done with text (present)
  const done = await completeJob({
    env, answerId: "story-1",
    body: { text: "  my client told me about her childhood  ", transcript_json: { segments: [] } },
    nowUtc: "2026-08-07T00:00:05.000Z",
  });
  if (!done.ok) failures.push(`complete failed: ${done.message}`);
  else if (done.job.status !== "done") failures.push(`expected done, got ${done.job.status}`);
  else if (done.job.text !== "my client told me about her childhood") failures.push(`text not cleaned/trimmed: "${done.job.text}"`);
  else if (fieldPresent(done.job) !== "present") failures.push("done-with-text must be present");
  else if (done.view.status !== "done") failures.push(`done view should be done, got ${done.view.status}`);

  // 3) failure -> failed (retry surfaces, never blank). A fresh job completes
  // with blank text, which must fail closed to EXTRACT-NO-TEXT and leave the
  // job failed (retry surface), never done-with-blank.
  const up2 = await acceptUpload({
    env,
    body: { session: "sess-A", answer_id: "story-2", channel: "video", filename: "clip.mp4", size_bytes: 2048, content_type: "video/mp4", header_bytes: [0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d] },
    nowUtc: "2026-08-07T00:00:07.000Z",
    entropyHex: "f1f2f3f4f5f6f7f8f9fafbfcfdfeff00",
  });
  if (!up2.ok) failures.push(`second upload failed: ${up2.message}`);
  const blankDone = await completeJob({ env, answerId: "story-2", body: { text: "   " }, nowUtc: "2026-08-07T00:00:08.000Z" });
  if (blankDone.ok) failures.push("empty-text completion must fail (EXTRACT-NO-TEXT)");
  else if (blankDone.error !== "AF-BW-MA-EXTRACT-NO-TEXT") failures.push(`expected EXTRACT-NO-TEXT, got ${blankDone.error}`);
  const failedJob = await pollJob({ env, answerId: "story-2" });
  if (failedJob.job.status !== "failed") failures.push(`empty completion should leave job failed, got ${failedJob.job.status}`);
  else if (failedJob.present !== "failed") failures.push(`failed job must read failed (not present/blank), got ${failedJob.present}`);
  else if (!failedJob.view.pill) failures.push("failed job must surface a retry pill, never a blank");

  // 4) illegal transition: done -> done must be rejected (receipt immutability)
  const immut = await completeJob({ env, answerId: "story-1", body: { text: "changed" }, nowUtc: "2026-08-07T00:00:09.000Z" });
  if (immut.ok) failures.push("done job must reject re-completion");

  return failures;
}

// --self-test driver (also importable by node --test).
const RUNNING_DIRECTLY = process.argv[1] && process.argv[1].endsWith("media.js");
if (RUNNING_DIRECTLY && process.argv.includes("--self-test")) {
  selfTest().then((failures) => {
    if (failures.length === 0) {
      console.log("U04 self-test: PASS (upload->queued, complete->done+text, fail->failed, no silent blank)");
      process.exit(0);
    } else {
      console.error("U04 self-test: FAIL\n - " + failures.join("\n - "));
      process.exit(1);
    }
  });
}
