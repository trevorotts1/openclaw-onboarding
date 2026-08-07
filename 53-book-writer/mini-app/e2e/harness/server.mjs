// ============================================================================
// Book Writer mini-app — U18 stub Worker + SPA server (headless harness)
// ----------------------------------------------------------------------------
// Serves the REAL production SPA (U05 pages/index.html + pages/app.js) exactly
// as the Cloudflare Worker (U02) serves it, and routes the SPA's API calls to
// the REAL Worker modules (U03 answers, U11 save/resume) over an in-memory KV
// store. A stub GHL endpoint records every write keyed by location_id, so T10
// proves browser-level isolation (alpha answers never reach beta's location).
//
// Routes:
//   GET  /<slug>/<phase>?tk=<token>   -> SPA shell + injected bw-bootstrap
//                                        (mirrors U02 index.js, including 401
//                                        on missing/misfit/expired token)
//   GET  /app.js | /welcome.js | ...  -> the real page modules (static)
//   POST /api/answers?tk=             -> REAL U03 handleAnswersPost
//   POST /api/save?tk=                -> REAL U11 handleSavePost
//   GET  /api/save/resume?tk=         -> REAL U11 handleResumeGet
//   POST /api/save/reminder?tk=       -> REAL U11 handleReminderPost
//   POST /api/media/upload?tk=        -> stub presign (SPA then PUTs to the URL)
//   PUT  /api/media/upload/:file      -> stub R2 accept (records the blob)
//   GET  /api/media/:answerId         -> stub job poll (queued -> done)
//   POST /api/ghl/:location/contact   -> stub GHL contact write
//   POST /api/ghl/:location/note      -> stub GHL note write
//   GET  /__e2e/ghl                   -> audit the stub GHL (isolation asserts)
//   GET  /__e2e/reset                 -> reset runtime rows + GHL (per-test)
//
// Headless + offline: no real hosts, no credentials, no Anthropic ids.
// ============================================================================

import { createServer } from 'node:http';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { MemoryKV } from './store.mjs';
import { GHL } from './ghl-stub.mjs';
import { CLIENTS, BINDINGS, CONFIG_P0_INTAKE, configForPhase, contextFor } from '../fixtures/index.mjs';
import { SPA_INJECT_TEMPLATE, validateTokenRow, checkMisfit, lookupToken, loadRunState, assertPhaseAllowed } from '../../worker/src/lib.js';
import { handleAnswersPost } from '../../worker/src/answers.js';
import { handleSavePost, handleResumeGet, handleReminderPost } from '../../worker/src/save.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const pagesDir = path.resolve(here, '../../pages');
const workerSrcDir = path.resolve(here, '../../worker/src');

const PORT = Number(process.env.E2E_PORT || 9780);

// ---------------------------------------------------------------------------
// Static asset map — serve the real page modules (never a reimplementation).
// ---------------------------------------------------------------------------
const PAGES_STATIC = new Map();
for (const f of readdirSync(pagesDir)) {
  const fp = path.join(pagesDir, f);
  if (!statSync(fp).isFile()) continue;
  if (/\.(js|mjs)$/.test(f)) PAGES_STATIC.set('/' + f, fp);
}

// The SPA shell (U05 index.html) with its script tags — the harness injects
// bw-bootstrap exactly as the Worker does (SPA_INJECT_TEMPLATE).
const SHELL_HTML = readFileSync(path.join(pagesDir, 'index.html'), 'utf8');

// ---------------------------------------------------------------------------
// In-memory store + seeded KV bindings + R2 configs (per-client isolation).
// ---------------------------------------------------------------------------
const store = new MemoryKV();

function seedEnv() {
  // KV binding rows (SOLE destination authority — U02/U03/U15). The U02 lib.js
  // looks tokens up under `tk:<token>`; U03 answers.js + U11 save.js look them
  // up under `binding:<token>` — both keyed to the SAME row.
  const bindingForSlug = (slug) => {
    if (slug === 'fake-alpha') return BINDINGS.alpha;
    if (slug === 'fake-beta') return BINDINGS.beta;
    if (slug === 'fake-gate1') return BINDINGS.gate1;
    return BINDINGS.alpha;
  };
  for (const client of Object.values(CLIENTS)) {
    const binding = bindingForSlug(client.slug);
    store.kvPut(`tk:${client.token}`, JSON.stringify(binding));
    store.kvPut(`binding:${client.token}`, JSON.stringify(binding));
  }
  // Run state: the gate1 client is mid-run at GATE-1-title (resume allowed).
  // The P0-INTAKE clients have no run state yet, so P0-INTAKE is their valid
  // entry point (mirrors U02 order enforcement).
  store.kvPut(`run:${CLIENTS.gate1.run_id}`, JSON.stringify({
    run_id: CLIENTS.gate1.run_id,
    client_id: CLIENTS.gate1.client_id,
    current_phase: 'GATE-1-title',
    phase_order: ['P0-INTAKE', 'GATE-1-title', 'GATE-2-outline', 'GATE-3-approval', 'GATE-4-approval-r2'],
  }));

  // R2 phase configs (U01 configs served as data, never code).
  store.seedObject(`config/fake-alpha/P0-INTAKE:full.json`, CONFIG_P0_INTAKE);
  store.seedObject(`config/fake-beta/P0-INTAKE:full.json`, CONFIG_P0_INTAKE);
  store.seedObject('config/fake-alpha/GATE-1-title.json', readJsonConfig('GATE-1-title.json'));
  store.seedObject('config/fake-beta/GATE-1-title.json', readJsonConfig('GATE-1-title.json'));
  store.seedObject('config/fake-gate1/GATE-1-title.json', readJsonConfig('GATE-1-title.json'));
  store.seedObject('config/fake-alpha/GATE-2-outline.json', readJsonConfig('GATE-2-outline.json'));
  store.seedObject('config/fake-beta/GATE-2-outline.json', readJsonConfig('GATE-2-outline.json'));

  // Run state (order enforcement, U02) — no state yet => P0-INTAKE is the
  // only entry point, which is exactly what the suite exercises.
  // R2 app shell pointer -> app/v1/index.html (the same file).
  store.seedObject('app/latest', { version: 'v1' });
  store.seedObjectRaw('app/v1/index.html', SHELL_HTML);

  // Stub GHL locations (fictitious). The location-scoped token convention is
  // `tok_<location_id>` — the write-back flush sends exactly that, and the stub
  // refuses any bearer that does not match (defense in depth at the transport).
  GHL.registerLocation('loc_alpha_fake', 'tok_loc_alpha_fake');
  GHL.registerLocation('loc_beta_fake', 'tok_loc_beta_fake');
  GHL.registerLocation('loc_gate1_fake', 'tok_loc_gate1_fake');
}

function readJsonConfig(name) {
  const p = path.resolve(here, '../fixtures/configs', name);
  return JSON.parse(readFileSync(p, 'utf8'));
}

seedEnv();

// ---------------------------------------------------------------------------
// Presigned-upload stub: the SPA's uploadMedia() POSTs /api/media/upload, gets
// back { upload: { url, method, headers } }, then PUTs the blob to that url,
// then polls GET /api/media/:answerId. We serve the PUT to a local route and
// complete the job on the first poll (proving the full staged path).
// ---------------------------------------------------------------------------
const uploadJobs = new Map(); // answerId -> { channel, filename, size, status, text, blob }

// ---------------------------------------------------------------------------
// JSON + HTML helpers
// ---------------------------------------------------------------------------
function json(res, status, body) {
  const buf = Buffer.from(JSON.stringify(body));
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
  });
  res.end(buf);
}

function html(res, status, body) {
  const buf = Buffer.from(body);
  res.writeHead(status, {
    'content-type': 'text/html; charset=utf-8',
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
  });
  res.end(buf);
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks);
}

// Adapt a Node http.IncomingMessage into a WHATWG Request so the REAL Worker
// modules (which call new URL(request.url) / request.arrayBuffer()) run
// unchanged. The request URL is always absolute on the local host.
async function toRequest(req, url) {
  const body = await readBody(req);
  const headers = {};
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    headers[req.rawHeaders[i].toLowerCase()] = req.rawHeaders[i + 1];
  }
  return new Request(url, {
    method: req.method || 'GET',
    headers,
    body: ['GET', 'HEAD'].includes(req.method || '') ? undefined : body,
  });
}

// ---------------------------------------------------------------------------
// Request → Response adapter so the REAL Worker modules run unchanged.
// The modules call `new Response(...)` / `new URL(request.url)` /
// `request.arrayBuffer()` — Node 22 provides these globally. env shape:
//   { BW_BINDINGS: <kv>, R2_ACCOUNT_ID: 'x', ... }
// ---------------------------------------------------------------------------
function envFor() {
  return {
    BW_BINDINGS: store,
    ZHW_BOOKWRITER: store,
    MEDIA_JOBS: store,
    MEDIA_BUCKET: store,
    R2_ACCOUNT_ID: 'fake_account',
    R2_ACCESS_KEY_ID: 'fake_key',
    R2_SECRET_ACCESS_KEY: 'fake_secret',
  };
}

async function toNode(res, nodeRes) {
  const text = await res.text();
  nodeRes.writeHead(res.status, Object.fromEntries(res.headers.entries()));
  nodeRes.end(text);
}

// ---------------------------------------------------------------------------
// The SPA route — mirrors U02 index.js exactly.
// ---------------------------------------------------------------------------
async function serveSpa(url, res) {
  const cleanPath = url.pathname.replace(/^\/+|\/+$/g, '');
  const [slug, phaseId] = cleanPath.split('/');
  const pathParts = cleanPath.split('/');

  // API + e2e routes are handled elsewhere; this handler is the universal link.
  if (pathParts.length !== 2 || !slug || !phaseId) {
    return json(res, 404, { error: 'not-found', path: url.pathname });
  }

  const token = url.searchParams.get('tk') || '';
  if (!token) return json(res, 401, { error: 'MISSING-TOKEN' });

  const row = await lookupToken(store, token);
  const verdict = validateTokenRow(row, Date.now());
  if (!verdict.ok) return json(res, 401, { error: verdict.reason });

  const fit = checkMisfit(row, slug, phaseId);
  if (!fit.ok) return json(res, 401, { error: fit.reason });

  const mode = row.mode || 'full';
  const state = await loadRunState(store, row.run_id);
  const orderCheck = assertPhaseAllowed(state, phaseId);
  if (!orderCheck.ok) return json(res, 401, { error: orderCheck.reason });

  const config = await loadPhaseConfig(store, row.slug, phaseId, mode);
  if (!config) return json(res, 401, { error: 'NO-CONFIG' });

  const shell = (await loadAppShell(store)) || SHELL_HTML;

  const context = {
    slug: row.slug,
    phase_id: phaseId,
    mode,
    run_id: row.run_id,
    exp: row.exp,
    phase_order: ['P0-INTAKE', 'GATE-1-title', 'GATE-2-outline', 'GATE-3-approval', 'GATE-4-approval-r2'],
    current_phase: state ? state.current_phase : phaseId,
  };
  const configJson = JSON.stringify(config);
  const contextJson = JSON.stringify(context);
  let doc = SPA_INJECT_TEMPLATE(shell, configJson, contextJson);
  // The SPA shell references its JS with a relative src (`<script src="app.js">`),
  // which resolves against the DOCUMENT URL (the universal-link route
  // /<slug>/<phase>), not the origin root. A deployment's assembly anchors the
  // document to origin root so the assets resolve; the harness does the same
  // so the REAL SPA renders headless.
  doc = doc.replace('<head>', '<head><base href="/">');
  return html(res, 200, doc);
}

// import lib helpers not exported by the real modules directly
async function loadAppShell(store) {
  const pointerObj = await store.objectGet('app/latest');
  if (!pointerObj) return null;
  let pointer;
  try { pointer = JSON.parse(pointerObj.value); } catch { return null; }
  if (!pointer || typeof pointer.version !== 'string') return null;
  const shellObj = await store.objectGet(`app/${pointer.version}/index.html`);
  if (!shellObj) return null;
  return shellObj.value;
}

async function loadPhaseConfig(store, slug, phaseId, mode) {
  const phase = phaseId === 'P0-INTAKE' ? `${phaseId}:${mode || 'full'}` : phaseId;
  const obj = await store.objectGet(`config/${slug}/${phase}.json`);
  if (!obj) return null;
  try { return JSON.parse(obj.value); } catch { return null; }
}

// ---------------------------------------------------------------------------
// HTTP server
// ---------------------------------------------------------------------------
const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const method = req.method || 'GET';
  const pathname = url.pathname;

  try {
    // ---- e2e control endpoints (tests only; never reach production) --------
    if (pathname === '/__e2e/reset' && method === 'POST') {
      await store.resetRuntime();
      GHL.reset();
      uploadJobs.clear();
      return json(res, 200, { ok: true });
    }
    // Mirrors the box ingest poller (U12) + GHL write-back (U15): reads the
    // staged answers for a client (keyed by the token's binding) and writes
    // them to the stub GHL under the binding's OWN location_id + token. This is
    // what lets T10 prove browser-level isolation — the destination comes from
    // the binding row, never from the answer body.
    if (pathname === '/__e2e/flush' && method === 'POST') {
      const body = await readBody(req);
      const { token } = JSON.parse(body.toString());
      const binding = await store.get(`binding:${token}`, { type: 'json' });
      if (!binding) return json(res, 404, { error: 'unknown token' });
      const prefix = `answer:${binding.client_id}:${binding.run_id}:${binding.phase_id}:`;
      const listed = await store.list({ prefix });
      const staged = [];
      for (const k of listed.keys) {
        const raw = await store.get(k.name, { type: 'json' });
        if (raw) staged.push({ key: k.name, ...raw });
      }
      // Contact write once (identity), then one note per answer field.
      const contact = {
        location_id: binding.location_id,
        auth_token: `tok_${binding.location_id}`,
        client_id: binding.client_id,
        run_id: binding.run_id,
        phase_id: binding.phase_id,
        source: 'e2e-writeback',
      };
      await GHL.writeContact(contact);
      const notes = [];
      for (const row of staged) {
        const note = await GHL.writeNote({
          location_id: binding.location_id,
          auth_token: `tok_${binding.location_id}`,
          question_id: row.qid,
          answer: typeof row.answer === 'string' ? row.answer : JSON.stringify(row.answer),
          source: row.source || 'typed',
          run_id: binding.run_id,
        });
        notes.push(note);
      }
      return json(res, 200, { ok: true, client_id: binding.client_id, location_id: binding.location_id, staged: staged.length, notes: notes.length });
    }
    if (pathname === '/__e2e/ghl' && method === 'GET') {
      return json(res, 200, GHL.hits());
    }
    if (pathname === '/__e2e/ghl' && method === 'POST') {
      const body = await readBody(req);
      const parsed = JSON.parse(body.toString());
      return json(res, 200, GHL.answersFor(parsed.location_id));
    }

    // ---- stub GHL (the transport the box write-back would hit) --------------
    if (pathname.startsWith('/api/ghl/') && method === 'POST') {
      const parts = pathname.split('/');
      const locationId = parts[3];
      const kind = parts[4]; // contact | note
      const body = await readBody(req);
      const payload = JSON.parse(body.toString());
      if (kind === 'contact') return json(res, 201, await GHL.writeContact({ ...payload, location_id: locationId }));
      if (kind === 'note') return json(res, 201, await GHL.writeNote({ ...payload, location_id: locationId }));
      return json(res, 404, { error: 'unknown ghl route' });
    }

    // ---- static page modules (real U05/U09/U10/U11 assets) ------------------
    if (method === 'GET' && PAGES_STATIC.has(pathname)) {
      const body = readFileSync(PAGES_STATIC.get(pathname));
      const type = pathname.endsWith('.mjs') ? 'text/javascript' : 'application/javascript';
      res.writeHead(200, { 'content-type': type, 'cache-control': 'no-store' });
      return res.end(body);
    }

    // ---- REAL U11 save/resume routes ---------------------------------------
    if (pathname === '/api/save' && method === 'POST') {
      const wReq = await toRequest(req, `http://127.0.0.1:${PORT}${pathname}${url.search}`);
      return toNode(await handleSavePost(wReq, envFor()), res);
    }
    if (pathname === '/api/save/resume' && method === 'GET') {
      const wReq = await toRequest(req, `http://127.0.0.1:${PORT}${pathname}${url.search}`);
      return toNode(await handleResumeGet(wReq, envFor()), res);
    }
    if (pathname === '/api/save/reminder' && method === 'POST') {
      const wReq = await toRequest(req, `http://127.0.0.1:${PORT}${pathname}${url.search}`);
      return toNode(await handleReminderPost(wReq, envFor()), res);
    }

    // ---- REAL U03 answers route ---------------------------------------------
    if (pathname === '/api/answers' && method === 'POST') {
      const wReq = await toRequest(req, `http://127.0.0.1:${PORT}${pathname}${url.search}`);
      return toNode(await handleAnswersPost(wReq, envFor()), res);
    }

    // ---- stub media upload (U04 contract shape) ------------------------------
    if (pathname === '/api/media/upload' && method === 'POST') {
      const body = await readBody(req);
      const parsed = JSON.parse(body.toString());
      const answerId = parsed.answer_id;
      if (!answerId) return json(res, 400, { error: 'answer_id required' });
      const fileKey = `blob_${answerId}.webm`;
      uploadJobs.set(answerId, {
        status: 'queued',
        channel: parsed.channel || 'audio',
        filename: parsed.filename || fileKey,
        size: parsed.size_bytes || 0,
        text: null,
        blob: null,
      });
      return json(res, 201, {
        ok: true,
        status: 201,
        view: { status: 'queued', pill: 'Transcribing…', text: null, error: null },
        upload: {
          url: `http://127.0.0.1:${PORT}/api/media/upload/${fileKey}`,
          method: 'PUT',
          headers: {},
        },
      });
    }
    if (pathname.startsWith('/api/media/upload/') && method === 'PUT') {
      const fileKey = pathname.split('/').pop();
      const body = await readBody(req);
      const job = [...uploadJobs.values()].find((j) => j.filename === fileKey || j.size === body.length);
      const answerId = [...uploadJobs.keys()].find((id) => {
        const j = uploadJobs.get(id);
        return j.filename === fileKey;
      });
      if (answerId) uploadJobs.get(answerId).blob = body;
      return json(res, 200, { ok: true });
    }
    if (pathname.startsWith('/api/media/') && method === 'GET') {
      const answerId = pathname.split('/').pop();
      const job = uploadJobs.get(answerId);
      if (!job) return json(res, 200, { status: 'missing', pill: 'Answer not received yet.', text: null, error: null });
      if (job.status === 'queued') {
        // first poll -> still queued; second poll -> done (proves the poll loop)
        if (!job._polled) { job._polled = true; return json(res, 200, { status: 'queued', pill: 'Transcribing…', text: null, error: null }); }
        job.status = 'done';
        job.text = 'Recorded words from the audio for ' + answerId.slice(0, 8);
        return json(res, 200, { status: 'done', pill: null, text: job.text, error: null });
      }
      if (job.status === 'done') return json(res, 200, { status: 'done', pill: null, text: job.text, error: null });
      return json(res, 200, { status: 'failed', pill: 'Try again or type instead.', text: null, error: 'test-fail' });
    }

    // ---- universal link (the SPA) --------------------------------------------
    if (method === 'GET') return serveSpa(url, res);

    return json(res, 404, { error: 'not-found', path: pathname });
  } catch (err) {
    return json(res, 500, { error: 'harness-error', message: String(err && err.message || err) });
  }
});

// ---------------------------------------------------------------------------
// Launch + self-test
// ---------------------------------------------------------------------------
export function start(port = PORT) {
  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      console.log(`[e2e-harness] serving on http://127.0.0.1:${port}`);
      resolve({ port, server });
    });
  });
}

export async function stop() {
  await new Promise((resolve) => server.close(resolve));
}

export { server };

// --selftest: prove the harness boots, serves the SPA, and the GHL stub works.
if (process.argv.includes('--selftest')) {
  (async () => {
    try {
      await start();
      const checks = [];
      const base = `http://127.0.0.1:${PORT}`;
      const res = await fetch(`${base}/fake-alpha/P0-INTAKE?tk=${CLIENTS.alpha.token}`);
      const body = await res.text();
      checks.push(['SPA serves 200 with bw-bootstrap', res.status === 200 && body.includes('bw-bootstrap') && body.includes('app.js')]);
      checks.push(['SPA injects the real config', body.includes('Which Avatar Alchemist')]);

      const bad = await fetch(`${base}/fake-beta/P0-INTAKE?tk=${CLIENTS.alpha.token}`);
      checks.push(['misfit token -> 401', bad.status === 401]);

      const missing = await fetch(`${base}/fake-alpha/P0-INTAKE`);
      checks.push(['missing token -> 401', missing.status === 401]);

      // REAL answers module through the harness:
      const ansRes = await fetch(`${base}/api/answers?tk=${CLIENTS.alpha.token}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ question_id: 'version', answer: 'book', source: 'choice' }),
      });
      const ansJson = await ansRes.json();
      checks.push(['U03 answers POST accepted', ansRes.status === 201 && ansJson.ok === true]);
      checks.push(['U03 receipt carries alpha client', ansJson.receipt && ansJson.receipt.client_id === 'client_alpha_fake']);

      const replay = await fetch(`${base}/api/answers?tk=${CLIENTS.alpha.token}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ question_id: 'version', answer: 'book', source: 'choice' }),
      });
      checks.push(['U03 replayed step -> 409 (idempotent)', replay.status === 409]);

      const failed = checks.every((c) => c[1]);
      for (const c of checks) console.log((c[1] ? 'PASS' : 'FAIL') + '  ' + c[0]);
      console.log(failed ? 'U18 e2e harness self-test: PASS' : 'U18 e2e harness self-test: FAIL');
      await stop();
      process.exit(failed ? 0 : 2);
    } catch (e) {
      console.error('U18 e2e harness self-test: FAILED to run —', e.message);
      process.exit(3);
    }
  })();
}
