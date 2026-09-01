// Book Writer mini-app — media upload pure logic (U04).
//
// Pure, side-effect-free helpers for the POST /api/media Worker endpoint:
// format allowlist, size caps, job-registry rules, and the field-present gate.
// Everything here is unit-testable with plain `node --test` (no Cloudflare
// runtime, no network). The Worker (media.js) composes these with R2 + KV.
//
// The load-bearing property under test is the PRESENT-FOR-INTAKE gate from
// MASTER-PLAN section 4: a field counts as PRESENT for the intake gate ONLY
// when its job is `done` with non-empty text (or explicit N/A). queued /
// processing parks with a "Transcribing…" pill; failed surfaces retry — never
// a silent blank. Implemented as fail-closed state transitions: a job can only
// reach `done` by a transition that carries non-empty text, and a failed job
// is never silently blanked.

// ---------------------------------------------------------------------------
// Format allowlist + size caps (MASTER-PLAN section 4, "Security")
// ---------------------------------------------------------------------------

// Extension allowlist AND magic-byte/Content-Type sniff. Named reject codes:
// REJECT-FORMAT / REJECT-SIZE (section 4, "New AF codes prefixed AF-BW-MA-*").
export const ALLOWED_EXTENSIONS = {
  audio: ["mp3", "m4a", "opus", "webm", "ogg", "wav"],
  video: ["mp4", "webm", "mov", "m4v"],
};

// Content-Type allowlist per channel. The browser MediaRecorder emits
// audio/webm (opus) and video/webm; uploads may be mp3/m4a/mp4/mov/etc.
export const ALLOWED_MIME_PREFIX = {
  audio: ["audio/", "video/webm"], // MediaRecorder may label webm as video/webm
  video: ["video/"],
};

// Size caps in bytes. Audio is capped lower than video (MASTER-PLAN section 4).
export const SIZE_CAPS_BYTES = {
  audio: 100 * 1024 * 1024, // 100 MB
  video: 500 * 1024 * 1024, // 500 MB
};

// Magic bytes for extension/mime sniffing of the first few bytes of a stream.
export const MAGIC = [
  { sig: [0x49, 0x44, 0x33], ext: "mp3", mime: "audio/mpeg" }, // ID3 tag
  { sig: [0xff, 0xfb], ext: "mp3", mime: "audio/mpeg" }, // MP3 frame sync (partial)
  { sig: [0x4f, 0x67, 0x67, 0x53], ext: "ogg", mime: "audio/ogg" }, // OggS
  { sig: [0x66, 0x74, 0x79, 0x70], ext: "mp4", mime: "video/mp4" }, // ftyp box
  { sig: [0x1a, 0x45, 0xdf, 0xa3], ext: "webm", mime: "video/webm" }, // EBML/WebM
  { sig: [0x52, 0x49, 0x46, 0x46], ext: "wav", mime: "audio/wav" }, // RIFF
];

// Explicitly NOT supported in v1 (MASTER-PLAN section 4): `.docx` — rejected
// with an offer to type or record instead. PDF/.txt are NOT media (they ride
// the text path via pdf.js / FileReader), so they are intentionally absent
// here; this endpoint is media-only.
export const CHANNELS = ["audio", "video"];

// ---------------------------------------------------------------------------
// Text caps (MASTER-PLAN section 4): length-checked text.
// ---------------------------------------------------------------------------
export const TEXT_CAPS = {
  default: 50_000, // 50k chars/field
  long: 200_000, // book_about + book_stories
};

// Control characters stripped from extracted text (section 4: "control-chars
// stripped"). Keep \n \t \r as line structure; drop C0 control chars, DEL and
// the C1 range, plus lone surrogates that would corrupt JSON. Written as
// pure unicode escapes (no literal control bytes) so the file stays UTF-8 text.
// eslint-disable-next-line no-control-regex
const CONTROL_CHAR_RE = new RegExp(
  "[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F\\u007F-\\u009F]",
  "g"
);
const LONE_SURROGATE_RE = /[\uD800-\uDFFF]/g;

// ---------------------------------------------------------------------------
// Job status lifecycle
// ---------------------------------------------------------------------------
export const JOB_STATUS = {
  QUEUED: "queued",
  PROCESSING: "processing",
  DONE: "done",
  FAILED: "failed",
};

export const PENDING_STATUSES = [JOB_STATUS.QUEUED, JOB_STATUS.PROCESSING];

// ---------------------------------------------------------------------------
// Format allowlist helpers
// ---------------------------------------------------------------------------

/** Strip a leading dot and lowercase an extension. */
export function normalizeExt(raw) {
  if (typeof raw !== "string") return "";
  return raw.trim().replace(/^\.+/, "").toLowerCase();
}

/**
 * Validate a media upload's declared shape. Returns {ok, code, message}.
 * code is one of: ok | REJECT-FORMAT | REJECT-SIZE | REJECT-FIELD.
 * Fails closed on any missing/unknown field. Never accepts an extension that
 * the channel allowlist does not contain, regardless of MIME sniff.
 */
export function validateUpload({ channel, filename, sizeBytes, contentType, headerBytes = [] }) {
  if (channel !== "audio" && channel !== "video") {
    return { ok: false, code: "REJECT-FIELD", message: "channel must be audio or video" };
  }
  const ext = normalizeExt(filename ? filename.split(".").pop() : "");
  if (!ext || !ALLOWED_EXTENSIONS[channel].includes(ext)) {
    return { ok: false, code: "REJECT-FORMAT", message: `This file type (.${ext || "?"}) is not supported. Please record audio or upload a supported media file.` };
  }
  const size = Number(sizeBytes);
  if (!Number.isFinite(size) || size <= 0) {
    return { ok: false, code: "REJECT-FIELD", message: "sizeBytes must be a positive number" };
  }
  if (size > SIZE_CAPS_BYTES[channel]) {
    return { ok: false, code: "REJECT-SIZE", message: "This file is too big — please send it in Telegram instead." };
  }
  // Content-Type sniff: if a Content-Type is declared it must look sane for
  // the channel. A missing Content-Type is tolerated (browsers may omit it);
  // a clearly-wrong one is rejected.
  if (contentType) {
    const ct = String(contentType).split(";")[0].trim().toLowerCase();
    if (!ALLOWED_MIME_PREFIX[channel].some((p) => ct.startsWith(p))) {
      return { ok: false, code: "REJECT-FORMAT", message: `Content type "${ct}" is not allowed for ${channel}.` };
    }
  }
  // Magic-byte sniff: when header bytes are provided they must match a known
  // signature family that is compatible with the channel. A mismatch is a hard
  // REJECT-FORMAT (a renamed `.mp3` that is really a ZIP must fail closed), and
  // an UNKNOWN header (bytes that match no known media signature) is also
  // rejected — a media file must be recognizable, not opaque.
  if (Array.isArray(headerBytes) && headerBytes.length > 0) {
    const sniff = sniffMagic(headerBytes);
    if (!sniff) {
      return { ok: false, code: "REJECT-FORMAT", message: `The file header is not a recognized ${channel} format.` };
    }
    if (!channelAllowsExt(channel, sniff.ext)) {
      return { ok: false, code: "REJECT-FORMAT", message: `The file header does not match a ${channel} format.` };
    }
    if (sniff.ext !== ext && sniff.ext !== "mp3" && sniff.ext !== "webm") {
      // mp3 may be bare frames without an ID3 tag; webm is fine for both
      // channels. Anything else that disagrees with the extension fails closed.
      return { ok: false, code: "REJECT-FORMAT", message: `File header says ${sniff.mime} but the filename says .${ext}.` };
    }
  }
  return { ok: true, code: "ok", message: "" };
}

/** Does the channel allow the given (sniffed) extension? */
export function channelAllowsExt(channel, ext) {
  return ALLOWED_EXTENSIONS[channel].includes(ext);
}

/** Sniff magic bytes against MAGIC signatures. Returns {ext, mime} or null. */
export function sniffMagic(bytes) {
  const arr = Array.from(bytes);
  let best = null;
  for (const m of MAGIC) {
    const sig = m.sig;
    if (arr.length < sig.length) continue;
    if (sig.every((b, i) => arr[i] === b)) {
      best = m; // keep the longest / last-best match
    }
  }
  return best ? { ext: best.ext, mime: best.mime } : null;
}

// ---------------------------------------------------------------------------
// Job registry (status machine)
// ---------------------------------------------------------------------------

/**
 * Build a fresh queued job from an accepted upload. Deterministic aside from
 * timestamps, so tests inject the clock.
 */
export function buildQueuedJob({ intakeId, answerId, channel, sourceUri, sourceSha256, contentType, sizeBytes, createdAtUtc }) {
  return {
    intake_id: intakeId,
    answer_id: answerId,
    channel,
    source_uri: sourceUri,
    source_sha256: sourceSha256,
    status: JOB_STATUS.QUEUED,
    text: "",
    transcript_json: null,
    still_frame: null,
    content_type: contentType || null,
    size_bytes: sizeBytes || null,
    error: null,
    created_at: createdAtUtc,
    done_at: null,
  };
}

/**
 * Transition a job. Enforces the fail-closed rules:
 *   - queued -> processing (transcription began)
 *   - any -> done REQUIRES non-empty text (or explicit N/A); never a silent
 *     blank. `done: true, text: "N/A"` is the explicit-N/A path.
 *   - any -> failed (record the error); a failed job is never blanked.
 *   - terminal states (done/failed) reject further transitions.
 * Returns {ok, job, error} where error is a stable AF-BW-MA code.
 */
export function transitionJob(job, action, { text = "", transcriptJson = null, stillFrame = null, error = null, nowUtc = null, capKey = "default" } = {}) {
  if (!job) return { ok: false, error: "AF-BW-MA-JOB-PENDING", job: null };
  const status = job.status;

  if (action === "start") {
    if (status !== JOB_STATUS.QUEUED) return { ok: false, error: "BAD-TRANSITION", job };
    return { ok: true, job: { ...job, status: JOB_STATUS.PROCESSING }, error: null };
  }

  if (action === "fail") {
    if (status === JOB_STATUS.DONE) return { ok: false, error: "BAD-TRANSITION", job };
    const e = error || "transcription failed";
    return { ok: true, job: { ...job, status: JOB_STATUS.FAILED, error: e, done_at: nowUtc }, error: null };
  }

  if (action === "complete") {
    if (status === JOB_STATUS.DONE || status === JOB_STATUS.FAILED) {
      return { ok: false, error: "BAD-TRANSITION", job };
    }
    const clean = cleanText(text, capKey);
    const isExplicitNA = clean === "N/A" || clean === "NA" || clean === "n/a" || clean === "na";
    if (clean.length === 0 && !isExplicitNA) {
      return { ok: false, error: "AF-BW-MA-EXTRACT-NO-TEXT", job };
    }
    return {
      ok: true,
      job: {
        ...job,
        status: JOB_STATUS.DONE,
        text: isExplicitNA ? "N/A" : clean,
        transcript_json: transcriptJson,
        still_frame: stillFrame,
        done_at: nowUtc,
        error: null,
      },
      error: null,
    };
  }

  return { ok: false, error: "BAD-TRANSITION", job };
}

/** Strip control chars, trim, enforce the field text cap. Returns cleaned text. */
export function cleanText(raw, capKey = "default") {
  if (typeof raw !== "string") return "";
  let s = raw.replace(CONTROL_CHAR_RE, "").replace(LONE_SURROGATE_RE, "");
  s = s.trim();
  const cap = TEXT_CAPS[capKey] || TEXT_CAPS.default;
  if (s.length > cap) s = s.slice(0, cap);
  return s;
}

/**
 * THE FIELD-PRESENT GATE (section 4): a field counts as PRESENT for the intake
 * gate ONLY when its job is `done` with non-empty text (or explicit N/A).
 * Returns "present" | "pending" | "missing" | "failed".
 *   - done + non-empty text / N/A          -> "present"
 *   - queued / processing                   -> "pending"  (Transcribing… pill)
 *   - done + empty text (shouldn't happen)  -> "missing"  (never silent blank)
 *   - failed                                -> "failed"   (retry surfaces)
 */
export function fieldPresent(job) {
  if (!job) return "missing";
  if (job.status === JOB_STATUS.QUEUED || job.status === JOB_STATUS.PROCESSING) return "pending";
  if (job.status === JOB_STATUS.FAILED) return "failed";
  if (job.status === JOB_STATUS.DONE) {
    const t = typeof job.text === "string" ? job.text.trim() : "";
    if (t.length > 0) return "present";
    return "missing"; // done with empty text — never treated as present
  }
  return "missing";
}

/**
 * Collect field-present verdicts for a set of required media fields and report
 * the intake-assembly gate verdict. Returns {verdict, fields}.
 * verdict: "ready" (all present) | "blocked" (any pending) | "degraded" (any
 * failed, none pending) | "missing" (any missing with nothing failed/pending).
 * An intake is assembled ONLY when verdict is "ready".
 */
export function intakeGateVerdict(jobsByAnswerId) {
  const fields = {};
  let hasPending = false;
  let hasFailed = false;
  let hasMissing = false;
  for (const [answerId, job] of Object.entries(jobsByAnswerId)) {
    const v = fieldPresent(job);
    fields[answerId] = v;
    if (v === "pending") hasPending = true;
    if (v === "failed") hasFailed = true;
    if (v === "missing") hasMissing = true;
  }
  let verdict = "ready";
  if (hasPending) verdict = "blocked";
  else if (hasFailed) verdict = "degraded";
  else if (hasMissing) verdict = "missing";
  return { verdict, fields };
}

/**
 * Deterministic random object key for a staged upload:
 * `<session>/<uuid>.<ext>` (section 4 security: random object key, extension
 * allowlisted). uuid is derived from a caller-supplied entropy source so tests
 * stay deterministic.
 */
export function randomObjectKey(session, ext, entropyHex) {
  const e = entropyHex || "00000000000000000000000000000000";
  return `${session}/${e}.${ext}`;
}

/**
 * Poll-view shape the client reads to decide the UI pill. Never returns a
 * silent blank: pending shows the transcribing pill, failed shows retry.
 */
export function pollView(job) {
  if (!job) return { status: "missing", pill: "Answer not received yet." };
  switch (job.status) {
    case JOB_STATUS.QUEUED:
    case JOB_STATUS.PROCESSING:
      return { status: job.status, pill: "Transcribing…", text: null, error: null };
    case JOB_STATUS.FAILED:
      return { status: "failed", pill: "Something went wrong with your recording. Please re-record or type it instead.", text: null, error: job.error };
    case JOB_STATUS.DONE: {
      const t = typeof job.text === "string" ? job.text.trim() : "";
      if (t.length === 0) {
        return { status: "done-no-text", pill: "Your recording came back empty. Please try again.", text: null, error: "AF-BW-MA-EXTRACT-NO-TEXT" };
      }
      return { status: "done", pill: null, text: job.text, error: null };
    }
    default:
      return { status: "missing", pill: "Answer not received yet.", text: null, error: null };
  }
}
