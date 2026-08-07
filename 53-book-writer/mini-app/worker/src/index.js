// ============================================================================
// index.js — book-writer mini-app Cloudflare Worker (U02 core)
//
// GET /<slug>/<phase>?tk=<token>  →  serve the SPA + phase config
//   - token validated against the bw_bindings KV namespace (binding row is the
//     SOLE authority; request never carries location_id / API key / contact id)
//   - bad/expired/replayed/misfit token → 401 page (no config, no form)
//   - order enforcement: only serve a phase the run state allows
//   - SPA shell + phase config served from R2 (ZHW_BOOKWRITER)
//
// DUMB RELAY: this Worker holds ZERO client PITs. GHL writes happen on the box
// that owns the run (Skill 44 rails). Never any Anthropic id anywhere.
// ============================================================================

import {
  validateTokenRow,
  checkMisfit,
  assertPhaseAllowed,
  lookupToken,
  loadPhaseConfig,
  loadRunState,
  loadAppShell,
  SPA_INJECT_TEMPLATE,
  render401,
} from './lib.js';

const DEFAULT_MODE = 'full';
const DEFAULT_PHASE_ORDER = [
  'P0-INTAKE',
  'GATE-1-title',
  'GATE-2-outline',
  'GATE-3-approval',
  'GATE-4-approval-r2',
];
const PHASE_ORDER_4X3X3 = [
  'P0-INTAKE',
  'GATE-433',
  'GATE-1-title',
  'GATE-2-outline',
  'GATE-3-approval',
];

// Warm, fail-closed fallback when the R2 app shell is not yet deployed (U05+).
const FALLBACK_SHELL = `<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="X-Content-Type-Options" content="nosniff">
<title>Your book</title>
<style>body{background:#FBF6EE;color:#3a2e22;font-family:'Nunito Sans',system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0}
.card{max-width:560px;padding:48px 32px;text-align:center}h1{font-family:Georgia,'Source Serif',serif;font-size:28px;margin:0 0 12px}
p{font-size:18px;line-height:1.6;color:#6b5b47}</style></head>
<body><div class="card"><h1>Your book is already in you.</h1>
<p>We just help it out. The questions for this step are loading — a fresh link will also get you right back here.</p></div></body></html>`;

const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };

function json(res, status, obj) {
  return new Response(JSON.stringify(obj), { status, headers: JSON_HEADERS });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/+|\/+$/g, '').split('/');
    const [slug, phaseId] = path;

    // Universal link shape: /<slug>/<phase>?tk=<token>  (any extra segments → 404)
    if (path.length !== 2 || !slug || !phaseId) {
      return json(null, 404, { error: 'not-found', path: url.pathname });
    }

    const token = url.searchParams.get('tk') || '';
    if (!token) {
      return unauthorized('MISSING-TOKEN');
    }

    // --- validate token against the KV binding ---------------------------------
    const row = await lookupToken(env.bw_bindings, token);
    const verdict = validateTokenRow(row, Date.now());
    if (!verdict.ok) {
      return unauthorized(verdict.reason);
    }

    // --- misfit: binding is the sole authority ---------------------------------
    const fit = checkMisfit(row, slug, phaseId);
    if (!fit.ok) {
      return unauthorized(fit.reason);
    }

    // --- order enforcement (resume-aware) --------------------------------------
    const mode = row.mode || DEFAULT_MODE;
    const state = await loadRunState(env.bw_bindings, row.run_id);
    const orderCheck = assertPhaseAllowed(state, phaseId);
    if (!orderCheck.ok) {
      return unauthorized(orderCheck.reason);
    }

    // --- phase config from R2 (config is DATA, never code) ---------------------
    const config = await loadPhaseConfig(env.ZHW_BOOKWRITER, row.slug, phaseId, mode);
    if (!config) {
      return unauthorized('NO-CONFIG');
    }

    // --- SPA shell from R2 (version-and-flip), fall back to warm shell ---------
    const shell = (await loadAppShell(env.ZHW_BOOKWRITER)) || FALLBACK_SHELL;

    const contextJson = JSON.stringify({
      slug: row.slug,
      phase_id: phaseId,
      mode,
      run_id: row.run_id,
      exp: row.exp,
      phase_order: mode === '4x3x3' ? PHASE_ORDER_4X3X3 : DEFAULT_PHASE_ORDER,
      current_phase: state ? state.current_phase : phaseId,
    });
    const configJson = JSON.stringify(config);
    const doc = SPA_INJECT_TEMPLATE(shell, configJson, contextJson);

    return new Response(doc, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store',
      },
    });
  },
};

function unauthorized(reason) {
  return new Response(render401(reason), {
    status: 401,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    },
  });
}
