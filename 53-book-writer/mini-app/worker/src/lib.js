// ============================================================================
// lib.js — book-writer mini-app Worker core PURE logic (U02)
//
// No Cloudflare bindings, no globals, no I/O except through the injected
// `store` adapter. This makes every rule unit-testable with node --test using
// an in-memory fake (see src/lib.test.mjs). The edge is a DUMB RELAY: the
// token's KV binding row is the SOLE authority for the destination — the
// request never carries location_id / API key / contact id.
//
// Contract (master-plan section 1 + 3):
//   - token validation: has required fields, not expired, status open
//   - misfit: URL slug/phase must equal the binding's slug/phase (binding wins)
//   - order enforcement: a phase may only be served when the run's
//     current_phase is its predecessor (resume allowed on the same phase)
//   - per-step dedupe: INCR a per-step consumed counter; first INCR (==1) is
//     the only accepted submit; a replay returns >1 and is rejected
//   - 401 paths: missing / tampered / expired / replayed / misfit token → 401,
//     NO config, NO form, zero GHL calls
// ============================================================================

'use strict';

// ---------------------------------------------------------------------------
// Key / path builders
// ---------------------------------------------------------------------------

export function tokenKey(token) {
  return `tk:${token}`;
}

export function consumeStepKey(runId, phaseId, questionId) {
  return `ctr:${runId}:${phaseId}:${questionId}`;
}

export function configObjectPath(slug, phaseId, mode) {
  // P0-INTAKE has full/4x3x3 variants; other phases have a single config.
  const phase = phaseId === 'P0-INTAKE' ? `${phaseId}:${mode || 'full'}` : phaseId;
  return `config/${slug}/${phase}.json`;
}

export function appPointerPath() {
  return 'app/latest';
}

export function appShellPath(version) {
  return `app/${version}/index.html`;
}

// ---------------------------------------------------------------------------
// Pure token validation (no I/O)
// ---------------------------------------------------------------------------

export const REQUIRED_BINDING_FIELDS = [
  'client_id',
  'location_id',
  'slug',
  'phase_id',
  'run_id',
  'exp',
  'status',
];

/**
 * Validate a decoded token binding row (from KV) against time + lifecycle.
 * @param {object|null} row  parsed KV value, or null when the token is unknown
 * @param {number} nowMs     epoch ms to evaluate against
 * @returns {{ok:true} | {ok:false, reason:string}}
 */
export function validateTokenRow(row, nowMs) {
  if (!row || typeof row !== 'object') {
    return { ok: false, reason: 'UNKNOWN' };
  }
  for (const f of REQUIRED_BINDING_FIELDS) {
    if (row[f] === undefined || row[f] === null || row[f] === '') {
      return { ok: false, reason: 'MALFORMED' };
    }
  }
  // Type-check BEFORE semantic checks: a wrong-typed field means the token was
  // tampered/forged (MALFORMED), never a legitimate consumed/expired state.
  for (const f of ['client_id', 'location_id', 'slug', 'phase_id', 'run_id', 'status']) {
    if (typeof row[f] !== 'string') {
      return { ok: false, reason: 'MALFORMED' };
    }
  }
  if (typeof row.exp !== 'number') {
    return { ok: false, reason: 'MALFORMED' };
  }
  if (row.status !== 'open') {
    return { ok: false, reason: 'CONSUMED' }; // consumed (per-step) or done (intake complete)
  }
  if (row.exp <= nowMs) {
    return { ok: false, reason: 'EXPIRED' };
  }
  return { ok: true };
}

/**
 * Misfit check: the URL's slug/phase must equal the binding's slug/phase.
 * The binding is the SOLE authority; a mismatched URL gets a 401 even if the
 * token itself is valid (a fixture-client-b token cannot open fixture-client-c).
 * @param {object} row       valid binding row
 * @param {string|null} slug from URL path
 * @param {string|null} phaseId from URL path
 * @returns {{ok:true} | {ok:false, reason:string}}
 */
export function checkMisfit(row, slug, phaseId) {
  if (slug !== row.slug || phaseId !== row.phase_id) {
    return { ok: false, reason: 'MISFIT' };
  }
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Order enforcement (resume-aware)
// ---------------------------------------------------------------------------

/**
 * A phase may only be served when the run state permits it:
 *   - same phase already in progress → resume is allowed (NOT replay)
 *   - next phase in order → allowed
 *   - anything else → rejected (no skipping ahead, no going backwards)
 * @param {object|null} state    run:<run_id> row
 * @param {string} phaseId       requested phase
 * @returns {{ok:true} | {ok:false, reason:string}}
 */
export function assertPhaseAllowed(state, phaseId) {
  if (!state || typeof state !== 'object' || !Array.isArray(state.phase_order)) {
    // No run state yet → the very first phase of a run (P0-INTAKE) is the
    // only valid entry point.
    return phaseId === 'P0-INTAKE'
      ? { ok: true }
      : { ok: false, reason: 'ORDER' };
  }
  const idx = state.phase_order.indexOf(phaseId);
  if (idx === -1) {
    return { ok: false, reason: 'UNKNOWN_PHASE' };
  }
  const curIdx = state.phase_order.indexOf(state.current_phase);
  // Same phase in progress → resume.
  if (phaseId === state.current_phase) {
    return { ok: true };
  }
  // Next phase in sequence → allowed (order preserved).
  if (curIdx !== -1 && idx === curIdx + 1) {
    return { ok: true };
  }
  return { ok: false, reason: 'ORDER' };
}

// ---------------------------------------------------------------------------
// Storage-dependent helpers (adapter `store`)
//   store.kvGet(key)        -> Promise<string|null>
//   store.kvPut(key, val, ttlSecs?) -> Promise<void>
//   store.incr(key)         -> Promise<number>   (atomic KV counter)
//   store.objectGet(path)   -> Promise<{value: string, etag?: string}|null>
// ---------------------------------------------------------------------------

export async function lookupToken(store, token) {
  const raw = await store.kvGet(tokenKey(token));
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function loadPhaseConfig(store, slug, phaseId, mode) {
  const path = configObjectPath(slug, phaseId, mode);
  const obj = await store.objectGet(path);
  if (!obj) return null;
  try {
    return JSON.parse(obj.value);
  } catch {
    return null;
  }
}

export async function loadRunState(store, runId) {
  const raw = await store.kvGet(`run:${runId}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Per-step dedupe. INCR the per-step consumed counter atomically.
 * Returns the new count; the caller accepts ONLY when count === 1.
 * A replayed submit returns >1 → rejected (idempotent, no duplicate).
 */
export async function consumeStep(store, runId, phaseId, questionId) {
  return store.incr(consumeStepKey(runId, phaseId, questionId));
}

export async function markBindingConsumed(store, token, status) {
  const key = tokenKey(token);
  const raw = await store.kvGet(key);
  if (!raw) return;
  const row = JSON.parse(raw);
  row.status = status;
  await store.kvPut(key, JSON.stringify(row));
}

// ---------------------------------------------------------------------------
// SPA + config assembly (GET / route)
// ---------------------------------------------------------------------------

/**
 * Build the SPA document: read the app shell (pointer-flip atomic unit),
 * inject the phase config + binding context as a JSON <script>, and hand back
 * the HTML string.
 */
export async function loadAppShell(store) {
  const pointerObj = await store.objectGet(appPointerPath());
  if (!pointerObj) return null;
  let pointer;
  try {
    pointer = JSON.parse(pointerObj.value);
  } catch {
    return null;
  }
  if (!pointer || typeof pointer.version !== 'string') return null;
  const shellObj = await store.objectGet(appShellPath(pointer.version));
  if (!shellObj) return null;
  return shellObj.value;
}

export function SPA_INJECT_TEMPLATE(shell, configJson, contextJson) {
  return shell.replace(
    /<\/body>/i,
    `<script id="bw-bootstrap" type="application/json" data-config="${escapeAttr(configJson)}" data-context="${escapeAttr(contextJson)}"></script></body>`
  );
}

function escapeAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

// ---------------------------------------------------------------------------
// 401 page (fail-closed: no config, no form)
// ---------------------------------------------------------------------------

export function render401(reason) {
  const msg =
    reason === 'EXPIRED'
      ? 'This link has expired.'
      : reason === 'CONSUMED'
        ? 'This link has already been used.'
        : reason === 'MISFIT'
          ? "This link doesn't match this step."
          : 'This link is not valid.';
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="X-Content-Type-Options" content="nosniff">
<title>Link not available</title>
<style>body{background:#FBF6EE;color:#3a2e22;font-family:'Nunito Sans',system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0}
.card{max-width:560px;padding:48px 32px;text-align:center}h1{font-family:Georgia,'Source Serif',serif;font-size:28px;margin:0 0 12px}
p{font-size:18px;line-height:1.6;color:#6b5b47}</style></head>
<body><div class="card"><h1>That link can't open this step.</h1><p>${msg}</p>
<p>If you think this is a mistake, ask for a fresh link — your earlier answers are safe.</p></div></body></html>`;
  return html;
}
