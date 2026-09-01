// Book Writer mini-app — U04 media upload unit gate.
//
// Offline unit tests for the Worker's media logic. No Cloudflare runtime, no
// network — just `node --test src/media.test.mjs`. The load-bearing properties
// under test (MASTER-PLAN section 4):
//   - upload -> queued job ("Transcribing…" pill)
//   - completion -> done with non-empty text (field counts PRESENT)
//   - failure -> failed (retry surfaces; never a silent blank)
//   - a blank completion is IMPOSSIBLE (EXTRACT-NO-TEXT)
//   - format/size allowlists reject with named codes (REJECT-FORMAT/REJECT-SIZE)

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  validateUpload,
  buildQueuedJob,
  transitionJob,
  cleanText,
  fieldPresent,
  intakeGateVerdict,
  pollView,
  normalizeExt,
  sniffMagic,
  randomObjectKey,
  ALLOWED_EXTENSIONS,
  SIZE_CAPS_BYTES,
} from "./media-lib.js";
import { acceptUpload, completeJob, failJob, pollJob, assemblyGate, selfTest } from "./media.js";

const NOW = "2026-08-07T00:00:00.000Z";

function memEnv() {
  const mem = new Map();
  return {
    MEDIA_JOBS: {
      async put(k, v) { mem.set(k, v); },
      async get(k) { return mem.get(k) ?? null; },
    },
    MEDIA_BUCKET: {
      async put() { return { key: "object" }; },
    },
    // Fake R2 credentials so the happy path mints a real presigned URL.
    R2_ACCOUNT_ID: "fakeaccountid",
    R2_ACCESS_KEY_ID: "fakeaccesskey",
    R2_SECRET_ACCESS_KEY: "fakesecret",
    MEDIA_BUCKET_NAME: "zhw-bookwriter",
  };
}

function acceptedJob(env, { answerId = "story-1", channel = "audio", filename = "rec.webm", sizeBytes = 4096, contentType = "audio/webm", headerBytes = [0x1a, 0x45, 0xdf, 0xa3, 0x01], session = "sess-A" } = {}) {
  return acceptUpload({
    env,
    body: { session, answer_id: answerId, channel, filename, size_bytes: sizeBytes, content_type: contentType, header_bytes: headerBytes, source_sha256: "abc123" },
    nowUtc: NOW,
    entropyHex: "e1e2e3e4e5e6e7e8e9eaebecedeeeff0",
  });
}

// ---------------------------------------------------------------------------
// 1. upload -> queued job
// ---------------------------------------------------------------------------
test("acceptUpload: valid audio upload mints a queued job with Transcribing pill", async () => {
  const env = memEnv();
  const res = await acceptedJob(env);
  assert.equal(res.ok, true);
  assert.equal(res.status, 201);
  assert.equal(res.job.status, "queued");
  assert.equal(res.job.answer_id, "story-1");
  assert.equal(res.job.channel, "audio");
  assert.match(res.job.source_uri, /^r2:\/\//);
  assert.equal(res.job.source_sha256, "abc123");
  assert.equal(res.view.pill, "Transcribing…");
  // queued is never PRESENT for the intake gate
  assert.equal(fieldPresent(res.job), "pending");
  // a presigned PUT url was minted
  assert.ok(res.upload && res.upload.method === "PUT");
  assert.match(res.upload.url, /r2\.cloudflarestorage\.com/);
});

test("acceptUpload: presigned url carries placeholder-free SigV4 query params", async () => {
  const env = memEnv();
  const res = await acceptedJob(env);
  assert.ok(res.upload.url.includes("X-Amz-Algorithm=AWS4-HMAC-SHA256"));
  assert.ok(res.upload.url.includes("X-Amz-Signature="));
  assert.ok(res.upload.url.includes("X-Amz-Expires=3600"));
  assert.ok(!res.upload.url.includes("<PLACEHOLDER>"));
});

test("acceptUpload: valid video upload is accepted", async () => {
  const env = memEnv();
  const res = await acceptedJob(env, { channel: "video", filename: "clip.mp4", contentType: "video/mp4", headerBytes: [0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d], answerId: "v-1" });
  assert.equal(res.ok, true);
  assert.equal(res.job.status, "queued");
});

test("acceptUpload: bad channel is rejected", async () => {
  const env = memEnv();
  const res = await acceptedJob(env, { channel: "pdf" });
  assert.equal(res.ok, false);
  assert.equal(res.error, "AF-BW-MA-REJECT-FIELD");
});

// ---------------------------------------------------------------------------
// 2. completion -> done with text (PRESENT for the intake gate)
// ---------------------------------------------------------------------------
test("completeJob: done with text is PRESENT for the intake gate", async () => {
  const env = memEnv();
  await acceptedJob(env);
  const res = await completeJob({ env, answerId: "story-1", body: { text: "  she grew up in Savannah  ", transcript_json: { segments: [] } }, nowUtc: NOW });
  assert.equal(res.ok, true);
  assert.equal(res.job.status, "done");
  assert.equal(res.job.text, "she grew up in Savannah");
  assert.equal(fieldPresent(res.job), "present");
  assert.equal(res.view.status, "done");
  assert.equal(res.job.done_at, NOW);
  assert.equal(res.job.error, null);
});

test("completeJob: explicit N/A is PRESENT (allowed by section 4)", async () => {
  const env = memEnv();
  await acceptedJob(env, { answerId: "na-1" });
  const res = await completeJob({ env, answerId: "na-1", body: { text: "N/A" }, nowUtc: NOW });
  assert.equal(res.ok, true);
  assert.equal(fieldPresent(res.job), "present");
  assert.equal(res.job.text, "N/A");
});

test("completeJob: blank completion fails closed to EXTRACT-NO-TEXT and surfaces retry", async () => {
  const env = memEnv();
  await acceptedJob(env, { answerId: "blank-1" });
  const res = await completeJob({ env, answerId: "blank-1", body: { text: "     " }, nowUtc: NOW });
  assert.equal(res.ok, false);
  assert.equal(res.error, "AF-BW-MA-EXTRACT-NO-TEXT");
  // the job is parked FAILED with a retry pill — never a silent blank
  const polled = await pollJob({ env, answerId: "blank-1" });
  assert.equal(polled.job.status, "failed");
  assert.equal(fieldPresent(polled.job), "failed");
  assert.ok(polled.view.pill);
});

test("completeJob: done job is immutable — re-completion is rejected", async () => {
  const env = memEnv();
  await acceptedJob(env);
  await completeJob({ env, answerId: "story-1", body: { text: "first" }, nowUtc: NOW });
  const again = await completeJob({ env, answerId: "story-1", body: { text: "changed" }, nowUtc: NOW });
  assert.equal(again.ok, false);
  assert.equal(again.error, "BAD-TRANSITION");
});

// ---------------------------------------------------------------------------
// 3. failure -> failed (retry surfaces, never silent blank)
// ---------------------------------------------------------------------------
test("failJob: surfaces a retry pill and reads 'failed' (not blank) for the gate", async () => {
  const env = memEnv();
  await acceptedJob(env, { answerId: "f-1" });
  const res = await failJob({ env, answerId: "f-1", body: { error: "ASR unavailable" }, nowUtc: NOW });
  assert.equal(res.ok, true);
  assert.equal(res.job.status, "failed");
  assert.equal(res.job.error, "ASR unavailable");
  assert.equal(fieldPresent(res.job), "failed");
  assert.ok(res.view.pill); // retry surface
  assert.equal(res.view.text, null); // never a silent blank
});

test("failJob: after done is rejected (receipt immutability)", async () => {
  const env = memEnv();
  await acceptedJob(env);
  await completeJob({ env, answerId: "story-1", body: { text: "done" }, nowUtc: NOW });
  const fail = await failJob({ env, answerId: "story-1", body: { error: "x" } });
  assert.equal(fail.ok, false);
});

// ---------------------------------------------------------------------------
// Field-present gate + assembly verdicts
// ---------------------------------------------------------------------------
test("intakeGateVerdict: blocked while any job is queued/processing", () => {
  const q = buildQueuedJob({ intakeId: "r", answerId: "a", channel: "audio", sourceUri: "u", sourceSha256: "h", createdAtUtc: NOW });
  const done = { ...q, status: "done", text: "hello" };
  const verdict = intakeGateVerdict({ a: q, b: done });
  assert.equal(verdict.verdict, "blocked");
  assert.equal(verdict.fields.a, "pending");
});

test("intakeGateVerdict: ready only when every field is done with text", () => {
  const done = (id) => ({ status: "done", text: "x", answer_id: id });
  const verdict = intakeGateVerdict({ a: done("a"), b: done("b") });
  assert.equal(verdict.verdict, "ready");
});

test("intakeGateVerdict: degraded when a job failed, missing when nothing is pending/failed", () => {
  const failed = { status: "failed", text: "", error: "boom" };
  const done = { status: "done", text: "ok" };
  const v1 = intakeGateVerdict({ a: failed, b: done });
  assert.equal(v1.verdict, "degraded");
  const v2 = intakeGateVerdict({ a: { status: "done", text: "" }, b: done });
  assert.equal(v2.verdict, "missing"); // done-with-empty is MISSING, never present
});

// ---------------------------------------------------------------------------
// Format / size allowlist (named reject codes)
// ---------------------------------------------------------------------------
test("validateUpload: reject unsupported format with REJECT-FORMAT", () => {
  const r = validateUpload({ channel: "audio", filename: "doc.docx", sizeBytes: 100, contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
  assert.equal(r.ok, false);
  assert.equal(r.code, "REJECT-FORMAT");
});

test("validateUpload: reject oversize with REJECT-SIZE", () => {
  const r = validateUpload({ channel: "audio", filename: "long.wav", sizeBytes: SIZE_CAPS_BYTES.audio + 1, contentType: "audio/wav", headerBytes: [0x52, 0x49, 0x46, 0x46] });
  assert.equal(r.ok, false);
  assert.equal(r.code, "REJECT-SIZE");
});

test("validateUpload: reject a renamed file whose magic bytes disagree", () => {
  // .mp3 extension but the header is a ZIP (PK..)
  const r = validateUpload({ channel: "audio", filename: "fake.mp3", sizeBytes: 200, contentType: "audio/mpeg", headerBytes: [0x50, 0x4b, 0x03, 0x04] });
  assert.equal(r.ok, false);
  assert.equal(r.code, "REJECT-FORMAT");
});

test("validateUpload: accept a matching webm upload", () => {
  const r = validateUpload({ channel: "audio", filename: "rec.webm", sizeBytes: 100, contentType: "audio/webm", headerBytes: [0x1a, 0x45, 0xdf, 0xa3] });
  assert.equal(r.ok, true);
});

test("cleanText: strips control chars, trims, enforces cap", () => {
  assert.equal(cleanText("  ab  "), "ab");
  const big = "x".repeat(200_001);
  assert.equal(cleanText(big, "long").length, 200_000);
});

test("normalizeExt and sniffMagic behave", () => {
  assert.equal(normalizeExt(".MP3"), "mp3");
  assert.equal(normalizeExt(""), "");
  assert.equal(sniffMagic([0x49, 0x44, 0x33, 0x04]).ext, "mp3");
  assert.equal(sniffMagic([0x00, 0x01]), null);
});

test("randomObjectKey is session-scoped with the allowlisted extension", () => {
  const k = randomObjectKey("sess-A", "webm", "f".repeat(32));
  assert.equal(k, "sess-A/ffffffffffffffffffffffffffffffff.webm");
});

// ---------------------------------------------------------------------------
// Self-test parity
// ---------------------------------------------------------------------------
test("selfTest reports zero failures", async () => {
  const failures = await selfTest();
  assert.deepEqual(failures, []);
});

// Allowlist sanity: no disallowed extension sneaks in.
test("allowlist covers only media extensions", () => {
  const all = [...ALLOWED_EXTENSIONS.audio, ...ALLOWED_EXTENSIONS.video];
  for (const e of all) {
    assert.match(e, /^[a-z0-9]+$/);
  }
  assert.ok(!all.includes("pdf"));
  assert.ok(!all.includes("txt"));
  assert.ok(!all.includes("docx"));
});
