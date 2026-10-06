// PRES-009 — server-minted tenant identity for the intake workers.
//
// Pure, side-effect-free helpers shared (byte-identical) by:
//   intake-miniapp/worker/src/            (D1 worker)
//   intake/interview-app/worker/src/      (D1 worker)
//   intake/interview-app/deployed-r2/src/ (R2 worker)
//
// Contract (SPEC.md PRES-009 step 1):
//   - company_id / installation_id / presentation_id / run_id /
//     intake_session_id are minted SERVER-SIDE and are immutable afterwards.
//     Caller-supplied names/slugs are DISPLAY ONLY and never key storage.
//   - Unique keys are composite tenant+presentation+session.
//   - Invalid opaque IDs are REJECTED, never lossy-sanitized (the old
//     intakeKey() strip-characters behavior let two distinct input ids
//     collapse onto one storage key).
//   - Legacy records with no durable owner are QUARANTINED with an explicit
//     remediation reason instead of being shown to every company.

// Opaque id shape: 3-64 chars, starts alphanumeric, then [A-Za-z0-9._-].
// Path separators, backslashes and any ".." run are structurally impossible —
// a stored id can never traverse out of its key namespace.
const OPID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/;

export function isValidOpaqueId(value) {
  if (typeof value !== "string") return false;
  if (value.length < 3 || value.length > 64) return false;
  if (value.includes("..") || value.includes("/") || value.includes("\\") || value.includes("\0")) return false;
  return OPID_RE.test(value);
}

export function opaqueIdError(name, value) {
  if (isValidOpaqueId(value)) return null;
  return (
    "invalid " + name +
    ": must be 3-64 chars, start alphanumeric, contain only [A-Za-z0-9._-], and never contain '/', '\\', or '..'"
  );
}

const ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz";

function randomSuffix(getRandomValues, length) {
  const buf = new Uint8Array(length);
  (getRandomValues || globalThis.crypto.getRandomValues.bind(globalThis.crypto))(buf);
  let out = "";
  for (let i = 0; i < length; i++) out += ID_ALPHABET[buf[i] % ID_ALPHABET.length];
  return out;
}

function timeToken(nowMs) {
  return (nowMs || Date.now()).toString(36);
}

/** Server-minted run id: globally unique per launch, safe as a storage key. */
export function mintRunId(nowMs, getRandomValues) {
  return "run-" + timeToken(nowMs) + "-" + randomSuffix(getRandomValues, 12);
}

/** Server-minted intake session id: globally unique, safe as a storage key. */
export function mintIntakeSessionId(nowMs, getRandomValues) {
  return "isn-" + timeToken(nowMs) + "-" + randomSuffix(getRandomValues, 12);
}

// Sync SHA-256 (compact, dependency-free) — used for the question-schema
// fingerprint so a capability link can only be reused against a COMPATIBLE
// question schema.
function sha256Hex(ascii) {
  const msg = [];
  for (let i = 0; i < ascii.length; i++) msg.push(ascii.charCodeAt(i) & 0xff);
  const bitLen = msg.length * 8;
  msg.push(0x80);
  while (msg.length % 64 !== 56) msg.push(0);
  const hi = Math.floor(bitLen / 0x100000000);
  const lo = bitLen >>> 0;
  msg.push((hi >>> 24) & 0xff, (hi >>> 16) & 0xff, (hi >>> 8) & 0xff, hi & 0xff);
  msg.push((lo >>> 24) & 0xff, (lo >>> 16) & 0xff, (lo >>> 8) & 0xff, lo & 0xff);
  const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a,
      h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;
  const w = new Array(64);
  const rotr = (x, n) => (x >>> n) | (x << (32 - n));
  for (let i = 0; i < msg.length; i += 64) {
    for (let t = 0; t < 16; t++) {
      w[t] = (msg[i + t * 4] << 24) | (msg[i + t * 4 + 1] << 16) | (msg[i + t * 4 + 2] << 8) | msg[i + t * 4 + 3];
    }
    for (let t = 16; t < 64; t++) {
      const s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
      const s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
    }
    let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
    for (let t = 0; t < 64; t++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + S1 + ch + K[t] + w[t]) | 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (S0 + maj) | 0;
      h = g; g = f; f = e; e = (d + temp1) | 0;
      d = c; c = b; b = a; a = (temp1 + temp2) | 0;
    }
    h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0; h5 = (h5 + f) | 0; h6 = (h6 + g) | 0; h7 = (h7 + h) | 0;
  }
  return [h0, h1, h2, h3, h4, h5, h6, h7].map((x) => (x >>> 0).toString(16).padStart(8, "0")).join("");
}

/**
 * Fingerprint of the LOAD-BEARING question schema (ids, kinds, requiredness,
 * order). Prompt wording may be reworded without breaking link reuse; adding
 * or reordering questions cannot.
 */
export function questionSchemaFingerprint(payload) {
  const qs = (payload && Array.isArray(payload.questions)) ? payload.questions : [];
  const shape = qs.map((q) => ({
    id: q && q.id,
    kind: (q && q.kind) || "text",
    required: !q || q.required !== false,
    order: q && typeof q.order === "number" ? q.order : null,
  }));
  return sha256Hex(JSON.stringify({ question_set: payload && payload.question_set, questions: shape }));
}

/**
 * Tenant fields extracted + validated from a mint/store request body.
 * Returns { ok, tenant, errors } — tenant is { company_id, installation_id,
 * presentation_id } or errors lists precise per-field rejections.
 */
export function tenantFromRequest(body) {
  const errors = [];
  const tenant = {};
  for (const field of ["company_id", "installation_id", "presentation_id"]) {
    const v = body ? body[field] : undefined;
    const err = opaqueIdError(field, v);
    if (err) errors.push(err);
    else tenant[field] = v;
  }
  if (errors.length) return { ok: false, errors };
  return { ok: true, tenant };
}

/**
 * Migration plan for legacy session rows minted before tenant identity
 * existed (run_id reused across boxes, no company/installation columns).
 * PURE: pass rows like D1 returns (run_id, box_id, token).
 *   - run_id used by exactly ONE distinct box_id, itself a valid opaque id
 *     and never reused as another box's run binding -> UNAMBIGUOUS: the one
 *     box that minted it is its installation.
 *   - run_id seen under MORE THAN ONE box (the exact PRES-009 collision) ->
 *     AMBIGUOUS: quarantined, never guessed.
 * Backfills are explicit values only; nothing is invented.
 */
export function planLegacySessionMigration(rows) {
  const byRun = new Map();
  for (const r of rows || []) {
    const key = String(r.run_id);
    if (!byRun.has(key)) byRun.set(key, { boxes: new Set(), rows: [] });
    const entry = byRun.get(key);
    if (r.box_id) entry.boxes.add(String(r.box_id));
    entry.rows.push(r);
  }
  const backfills = [];
  const quarantined = [];
  for (const [runId, entry] of byRun) {
    if (entry.boxes.size === 1) {
      const box = [...entry.boxes][0];
      if (isValidOpaqueId(box)) {
        for (const r of entry.rows) {
          backfills.push({ token: r.token, installation_id: box, run_id: runId });
          continue;
        }
      } else {
        for (const r of entry.rows) quarantined.push({ token: r.token, reason: "legacy_box_id_invalid" });
      }
    } else {
      for (const r of entry.rows) quarantined.push({ token: r.token, reason: "ambiguous_legacy_run_reused_across_boxes" });
    }
  }
  return { backfills, quarantined };
}

/**
 * Migration plan for legacy intake rows keyed by session_id alone.
 * A row is unambiguous ONLY when its stored intake record itself carries the
 * durable tenant ids. Anything else is quarantined with a remediation reason
 * (operator re-attributes explicitly; the worker never guesses).
 */
export function planLegacyIntakeMigration(rows) {
  const backfills = [];
  const quarantined = [];
  for (const r of rows || []) {
    let intake = null;
    try { intake = JSON.parse(r.intake_json || "null"); } catch { intake = null; }
    const c = intake && intake.company_id;
    const i = intake && intake.installation_id;
    const p = intake && intake.presentation_id;
    const run = intake && intake.run_id;
    if (isValidOpaqueId(c) && isValidOpaqueId(i) && isValidOpaqueId(p) && isValidOpaqueId(run)) {
      backfills.push({
        session_id: r.session_id,
        company_id: c, installation_id: i, presentation_id: p, run_id: run,
      });
    } else {
      quarantined.push({
        session_id: r.session_id,
        reason: "ambiguous_legacy_owner_unknown",
        remediation:
          "Re-store the intake with company_id/installation_id/presentation_id/run_id (mint a session first), " +
          "or delete the row explicitly if it is junk. The worker never guesses an owner.",
      });
    }
  }
  return { backfills, quarantined };
}