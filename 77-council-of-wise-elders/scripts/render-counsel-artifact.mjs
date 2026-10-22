#!/usr/bin/env node
// W74-B: the counsel artifact renderer.
//
// ONE fixed deterministic HTML template, uniform for every client and
// session. renderArtifact(sessionRecord) is a pure function of its input:
// no clock, no randomness, no per-client theming. It writes
//   <dataDir>/artifacts/<session-id>/index.html
// plus the copied assets it references (relative paths only) and returns
// { path, link, pdf }.
//
// The five sections, in this exact order:
//   1. header    - client name, date, the decision (runtime data, never
//                  hardcoded here) over a slim band of assets/seats/cover.png
//   2. consensus - the final verdict in large type
//   3. elders    - nine elder cards: seat emblem, name, lane, its take
//   4. actions   - numbered action steps from the verdict record
//   5. footer    - date, model used, question count in the sitting
//
// DATA SOURCE: the session record as assembled from council.db
// (sessions/events/verdicts/checkpoints tables; the cards and verdicts
// tables feed `cards` and `verdict` below). This module renders what it is
// given and never re-scores, re-derives, or invents content.
//
// The palette is one fixed deep-green and gold family matching the seat
// art. Print CSS is always in the template (page-break rules per elder
// card). A PDF is best effort only: produced by a headless renderer when
// one exists on the box (Chrome headless or macOS cupsfilter), otherwise
// the page degrades to print-from-browser. Nothing here ever blocks on
// PDF production and no PDF is ever faked by renaming HTML.
//
// Artifacts dir rotation guard: artifacts are per-session folders
// (<dataDir>/artifacts/<session-id>/), so the directory count is bounded
// by the session count and no rotation or pruning is needed here; if a
// host ever wants a cap, it prunes whole per-session folders oldest
// first, never files inside a folder another sitting may still link to.
//
// Repo content stays client-name-free: client names enter only as runtime
// data through sessionRecord.client_name.

import { spawnSync } from 'node:child_process';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { delimiter, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** The nine fixed seats in approved roster order (contracts SEAT_IDS). */
export const SEAT_IDS = [
  'simon-sinek',
  'td-jakes',
  'oprah-winfrey',
  'tiffany-aliche',
  'russell-brunson',
  'michelle-obama',
  'brene-brown',
  'dennis-kimbro',
  'les-brown',
];

/**
 * Display names and lanes. Names mirror contracts SEAT_ROSTER; lanes
 * mirror advisors/<seat>/profile.json "role". Fixed template content,
 * identical for every client and session.
 */
const SEAT_TABLE = {
  'simon-sinek': { name: 'Simon Sinek', lane: 'purpose and strategic alignment' },
  'td-jakes': { name: 'T. D. Jakes', lane: 'instinct, reinvention, and communication' },
  'oprah-winfrey': { name: 'Oprah Winfrey', lane: 'intention, significance, and human connection' },
  'tiffany-aliche': { name: 'Tiffany Aliche', lane: 'financial stability and sustainable commitments' },
  'russell-brunson': { name: 'Russell Brunson', lane: 'offers, acquisition, and conversion' },
  'michelle-obama': { name: 'Michelle Obama', lane: 'grounded leadership, identity, and community' },
  'brene-brown': { name: 'Brené Brown', lane: 'courage, trust, and accountable behavior' },
  'dennis-kimbro': { name: 'Dr. Dennis Kimbro', lane: 'ownership, wealth creation, and achievement' },
  'les-brown': { name: 'Les Brown', lane: 'self-belief, resilience, and committed action' },
};

/** The Section 8 honesty label shown on every elder card. */
function seatLabel(name) {
  return `AI perspective inspired by the published work of ${name}. Not the individual and not an endorsement.`;
}

const SIMULATION_NOTICE =
  'Simulated advisory perspectives. Every elder voice in this artifact is an AI perspective inspired by the published work of the named person. It is not the individual and not an endorsement.';

const SYNTHETIC_NOTICE =
  'SYNTHETIC FIXTURE: rendered from a synthetic test session, not a real client sitting.';

// ---------------------------------------------------------------------
// Validation at the trust boundary
// ---------------------------------------------------------------------

const SESSION_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

function requireText(value, field) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new TypeError(`sessionRecord.${field} must be a non-empty string`);
  }
  return value;
}

function validateRecord(record) {
  if (typeof record !== 'object' || record === null) {
    throw new TypeError('sessionRecord must be an object');
  }
  const sessionId = requireText(record.session_id, 'session_id');
  if (!SESSION_ID_RE.test(sessionId)) {
    throw new TypeError(
      `sessionRecord.session_id must match ${SESSION_ID_RE} (it names an artifact folder)`,
    );
  }
  requireText(record.client_name, 'client_name');
  requireText(record.date, 'date');
  requireText(record.decision, 'decision');
  requireText(record.model_used, 'model_used');
  if (
    typeof record.question_count !== 'number' ||
    !Number.isInteger(record.question_count) ||
    record.question_count < 0
  ) {
    throw new TypeError('sessionRecord.question_count must be a non-negative integer');
  }
  if (!Array.isArray(record.cards)) {
    throw new TypeError('sessionRecord.cards must be an array of nine {seat_id, take} entries');
  }
  const seen = new Set();
  for (const card of record.cards) {
    if (typeof card !== 'object' || card === null) {
      throw new TypeError('each sessionRecord.cards entry must be an object');
    }
    if (!SEAT_IDS.includes(card.seat_id)) {
      throw new TypeError(`unknown seat_id in sessionRecord.cards: ${String(card.seat_id)}`);
    }
    if (seen.has(card.seat_id)) {
      throw new TypeError(`duplicate seat_id in sessionRecord.cards: ${card.seat_id}`);
    }
    seen.add(card.seat_id);
    requireText(card.take, `cards[${card.seat_id}].take`);
  }
  if (seen.size !== SEAT_IDS.length) {
    const missing = SEAT_IDS.filter((id) => !seen.has(id));
    throw new TypeError(`sessionRecord.cards is missing seats: ${missing.join(', ')}`);
  }
  if (typeof record.verdict !== 'object' || record.verdict === null) {
    throw new TypeError('sessionRecord.verdict must be the verdict record');
  }
  requireText(record.verdict.consensus, 'verdict.consensus');
  if (!Array.isArray(record.verdict.action_steps)) {
    throw new TypeError('sessionRecord.verdict.action_steps must be an array of strings');
  }
  for (const [i, step] of record.verdict.action_steps.entries()) {
    requireText(step, `verdict.action_steps[${i}]`);
  }
  return record;
}

// ---------------------------------------------------------------------
// HTML helpers
// ---------------------------------------------------------------------

export function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

// One fixed stylesheet: deep green and gold family matching the seat art.
// Print-ready from the start: page-break rules per elder card, exact
// colors, nothing fetched from the network.
const STYLES = `
:root {
  --ink: #1c2b24;
  --deep-green: #14372b;
  --green: #1e5540;
  --gold: #b98f2e;
  --gold-soft: #d9bd74;
  --ivory: #f7f2e6;
  --paper: #fffdf7;
  --line: #d8c99b;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--ivory);
  color: var(--ink);
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 12.5pt;
  line-height: 1.55;
}
.cover-band {
  height: 96px;
  overflow: hidden;
  background: var(--deep-green);
  border-bottom: 4px solid var(--gold);
}
.cover-band img {
  width: 100%;
  height: 96px;
  object-fit: cover;
  object-position: center;
  display: block;
}
header { padding: 22px 32px 10px; border-bottom: 1px solid var(--line); }
.eyebrow {
  margin: 0 0 6px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-size: 10pt;
  color: var(--gold);
}
header h1 {
  margin: 0 0 10px;
  font-size: 21pt;
  color: var(--deep-green);
  line-height: 1.25;
}
.header-meta { margin: 0 0 6px; font-size: 10.5pt; color: var(--green); }
.header-meta .sep { color: var(--gold); padding: 0 8px; }
.client-name { font-weight: bold; color: var(--deep-green); }
.decision { margin: 10px 0 0; font-size: 13pt; }
.decision .decision-label {
  display: block;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 9pt;
  color: var(--gold);
  margin-bottom: 3px;
}
main { padding: 8px 32px 24px; }
h2 {
  margin: 26px 0 12px;
  font-size: 13pt;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--green);
  border-bottom: 2px solid var(--gold-soft);
  padding-bottom: 5px;
}
.consensus-text {
  margin: 0;
  font-size: 20pt;
  line-height: 1.35;
  color: var(--deep-green);
  background: var(--paper);
  border: 2px solid var(--gold);
  border-left: 8px solid var(--gold);
  padding: 18px 22px;
}
.elder-grid { display: block; }
.elder-card {
  display: flex;
  gap: 16px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-top: 3px solid var(--green);
  padding: 14px 18px;
  margin: 0 0 14px;
  break-inside: avoid;
  page-break-inside: avoid;
}
.seat-emblem {
  width: 92px;
  height: 92px;
  flex: 0 0 92px;
  border: 2px solid var(--gold-soft);
  border-radius: 50%;
  object-fit: cover;
}
.elder-body { flex: 1; min-width: 0; }
.elder-card h3 { margin: 0 0 2px; font-size: 14pt; color: var(--deep-green); }
.lane {
  margin: 0 0 8px;
  font-size: 10pt;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--gold);
}
.take { margin: 0 0 8px; }
.seat-label { margin: 0; font-size: 8.5pt; color: var(--green); font-style: italic; }
.action-steps { margin: 0; padding-left: 24px; }
.action-steps li { margin: 0 0 10px; break-inside: avoid; page-break-inside: avoid; }
.action-steps .empty { list-style: none; margin-left: -24px; color: var(--green); }
footer {
  margin-top: 18px;
  padding: 16px 32px 24px;
  border-top: 4px solid var(--gold);
  background: var(--deep-green);
  color: var(--ivory);
  break-inside: avoid;
  page-break-inside: avoid;
}
.footer-meta { margin: 0 0 8px; font-size: 10.5pt; }
.footer-meta .sep { color: var(--gold-soft); padding: 0 8px; }
.disclaimer { margin: 0; font-size: 9pt; color: var(--gold-soft); }
.synthetic-banner {
  background: var(--gold);
  color: var(--deep-green);
  text-align: center;
  font-size: 10pt;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  padding: 8px;
}
@media print {
  body { background: #ffffff; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .elder-card, .action-steps li, footer { break-inside: avoid; page-break-inside: avoid; }
  h2 { break-after: avoid; page-break-after: avoid; }
  .cover-band img { height: 72px; }
  @page { margin: 14mm 12mm; }
}
`;

function buildHtml(record) {
  const cards = SEAT_IDS.map((seatId) => {
    const entry = record.cards.find((c) => c.seat_id === seatId);
    const table = SEAT_TABLE[seatId];
    return `
  <article class="elder-card" data-seat-id="${escapeHtml(seatId)}">
    <img class="seat-emblem" src="assets/seat-${escapeHtml(seatId)}.png" alt="Seat emblem for ${escapeHtml(table.name)}">
    <div class="elder-body">
      <h3>${escapeHtml(table.name)}</h3>
      <p class="lane">${escapeHtml(table.lane)}</p>
      <p class="take">${escapeHtml(entry.take)}</p>
      <p class="seat-label">${escapeHtml(seatLabel(table.name))}</p>
    </div>
  </article>`;
  }).join('\n');

  const steps =
    record.verdict.action_steps.length === 0
      ? `\n  <li class="empty">No action steps recorded.</li>`
      : record.verdict.action_steps.map((step) => `\n  <li>${escapeHtml(step)}</li>`).join('');

  const syntheticBanner = record.synthetic
    ? `\n<div class="synthetic-banner">${escapeHtml(SYNTHETIC_NOTICE)}</div>`
    : '';

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Council of Wise Elders: ${escapeHtml(record.decision)}</title>
<style>${STYLES}
</style>
</head>
<body data-session-id="${escapeHtml(record.session_id)}">${syntheticBanner}
<header data-section="header">
  <div class="cover-band"><img src="assets/cover.png" alt=""></div>
  <p class="eyebrow">Council of Wise Elders</p>
  <h1>${escapeHtml(record.decision)}</h1>
  <p class="header-meta"><span class="client-name">${escapeHtml(record.client_name)}</span><span class="sep">|</span><span class="header-date">${escapeHtml(record.date)}</span></p>
  <p class="decision"><span class="decision-label">The decision</span>${escapeHtml(record.decision)}</p>
</header>
<main>
<section data-section="consensus">
  <h2>Overall consensus</h2>
  <p class="consensus-text">${escapeHtml(record.verdict.consensus)}</p>
</section>
<section data-section="elders">
  <h2>The nine elders</h2>
  <div class="elder-grid">${cards}
  </div>
</section>
<section data-section="actions">
  <h2>Action steps</h2>
  <ol class="action-steps">${steps}
  </ol>
</section>
</main>
<footer data-section="footer">
  <p class="footer-meta"><span class="footer-date">${escapeHtml(record.date)}</span><span class="sep">|</span><span class="footer-model">Model: ${escapeHtml(record.model_used)}</span><span class="sep">|</span><span class="footer-questions">Questions in the sitting: ${String(record.question_count)}</span></p>
  <p class="disclaimer">${escapeHtml(SIMULATION_NOTICE)}</p>
</footer>
</body>
</html>
`;
}

// ---------------------------------------------------------------------
// PDF: best effort only, never blocking, never faked
// ---------------------------------------------------------------------

function whichSync(command, env) {
  const pathVar = env.PATH ?? '';
  for (const dir of pathVar.split(delimiter)) {
    if (dir === '') continue;
    const candidate = join(dir, command);
    try {
      if (statSync(candidate).isFile()) return candidate;
    } catch {
      // not here; keep scanning
    }
  }
  return null;
}

/**
 * Probe for a headless PDF renderer. Pure inspection: no render, no
 * network. Returns { method, command } with method null when the box has
 * none, and never throws.
 */
export function probePdfRenderer(env = process.env) {
  try {
    const chromeCandidates = [
      env.CHROME_PATH,
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      join(env.HOME ?? '', 'Applications', 'Google Chrome.app', 'Contents', 'MacOS', 'Google Chrome'),
      whichSync('google-chrome', env),
      whichSync('chromium', env),
      whichSync('chromium-browser', env),
    ];
    for (const candidate of chromeCandidates) {
      if (candidate && existsSync(candidate)) {
        return { method: 'chrome-headless', command: candidate };
      }
    }
    const cups = whichSync('cupsfilter', env);
    if (cups) return { method: 'cupsfilter', command: cups };
    return { method: null, command: null };
  } catch {
    return { method: null, command: null };
  }
}

/**
 * Best-effort PDF beside index.html. Degrades gracefully to
 * print-from-browser: this NEVER throws and never blocks longer than its
 * timeout. A PDF is produced only by a real renderer; when none exists
 * the honest outcome is { status: 'print-from-browser' }.
 */
export function maybeRenderPdf(htmlPath, options = {}) {
  const outPath = options.outPath ?? htmlPath.replace(/index\.html$/, 'index.pdf');
  const env = options.env ?? process.env;
  const probe = options.probe ?? probePdfRenderer(env);
  const timeoutMs = options.timeoutMs ?? 60000;
  const spawn = options.spawnImpl ?? spawnSync;
  if (probe.method === null) {
    return { status: 'print-from-browser', method: null, pdfPath: null };
  }
  try {
    if (probe.method === 'chrome-headless') {
      const result = spawn(
        probe.command,
        [
          '--headless',
          '--disable-gpu',
          '--no-pdf-header-footer',
          `--print-to-pdf=${outPath}`,
          htmlPath,
        ],
        { timeout: timeoutMs, encoding: 'utf8' },
      );
      if (
        result.status === 0 &&
        existsSync(outPath) &&
        statSync(outPath).size > 0
      ) {
        return { status: 'rendered', method: probe.method, pdfPath: outPath };
      }
    } else if (probe.method === 'cupsfilter') {
      const result = spawn(probe.command, ['-m', 'application/pdf', htmlPath], {
        timeout: timeoutMs,
        maxBuffer: 64 * 1024 * 1024,
      });
      const bytes = result.stdout;
      if (
        result.status === 0 &&
        bytes &&
        bytes.length > 4 &&
        bytes.subarray(0, 4).toString('latin1') === '%PDF'
      ) {
        writeFileSync(outPath, bytes);
        return { status: 'rendered', method: probe.method, pdfPath: outPath };
      }
    }
  } catch {
    // fall through to the honest degrade below
  }
  return { status: 'print-from-browser', method: probe.method, pdfPath: null };
}

// ---------------------------------------------------------------------
// The renderer
// ---------------------------------------------------------------------

/** Default assets source: <skill-root>/assets/seats beside this script. */
export function defaultAssetsDir() {
  return resolve(dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'seats');
}

const ASSET_FILES = ['cover.png', ...SEAT_IDS.map((id) => `seat-${id}.png`)];

/**
 * renderArtifact(sessionRecord, options) -> { path, link, pdf }
 *
 * Writes <dataDir>/artifacts/<session-id>/index.html plus the copied
 * assets it needs (referenced by relative paths only) and best-effort
 * index.pdf. `link` is the artifact link for the reply: relative by
 * default, absolute when options.linkBase (the box's public origin) is
 * given.
 */
export function renderArtifact(sessionRecord, options = {}) {
  const record = validateRecord(sessionRecord);
  const dataDir = resolve(
    options.dataDir ??
      process.env.BLACKCEO_COUNCIL_DATA_DIR ??
      join(process.env.HOME ?? '.', '.openclaw', 'council-data'),
  );
  const assetsDir = resolve(options.assetsDir ?? defaultAssetsDir());
  const artifactDir = join(dataDir, 'artifacts', record.session_id);
  const assetsOut = join(artifactDir, 'assets');

  // Copy the needed assets first: a missing seat emblem fails the render
  // before any HTML is written, so no artifact ever ships with a broken
  // image.
  const missing = ASSET_FILES.filter((f) => !existsSync(join(assetsDir, f)));
  if (missing.length > 0) {
    throw new Error(
      `counsel artifact assets missing from ${assetsDir}: ${missing.join(', ')}`,
    );
  }
  mkdirSync(assetsOut, { recursive: true, mode: 0o700 });
  for (const file of ASSET_FILES) {
    copyFileSync(join(assetsDir, file), join(assetsOut, file));
  }

  const htmlPath = join(artifactDir, 'index.html');
  writeFileSync(htmlPath, buildHtml(record), 'utf8');

  const pdf =
    options.pdf === false
      ? { status: 'skipped', method: null, pdfPath: null }
      : maybeRenderPdf(htmlPath, {
          env: options.env,
          probe: options.probe,
          spawnImpl: options.spawnImpl,
          timeoutMs: options.timeoutMs,
        });

  const link =
    options.linkBase === undefined || options.linkBase === null
      ? `artifacts/${record.session_id}/index.html`
      : `${String(options.linkBase).replace(/\/$/, '')}/artifacts/${record.session_id}/index.html`;

  return { path: htmlPath, link, pdf };
}

// ---------------------------------------------------------------------
// Small CLI so a session-close flow can call it from a shell:
//   node scripts/render-counsel-artifact.mjs --record rec.json
//     [--data-dir DIR] [--assets-dir DIR] [--link-base URL] [--no-pdf]
// Prints the { path, link, pdf } JSON and never a secret.
// ---------------------------------------------------------------------

function parseCliArgs(argv) {
  const out = { record: null, options: {} };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (flag === '--record') {
      out.record = value;
      i += 1;
    } else if (flag === '--data-dir') {
      out.options.dataDir = value;
      i += 1;
    } else if (flag === '--assets-dir') {
      out.options.assetsDir = value;
      i += 1;
    } else if (flag === '--link-base') {
      out.options.linkBase = value;
      i += 1;
    } else if (flag === '--no-pdf') {
      out.options.pdf = false;
    } else {
      throw new Error(`unknown flag: ${flag}`);
    }
  }
  return out;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const { record, options } = parseCliArgs(process.argv.slice(2));
    if (record === null) throw new Error('usage: render-counsel-artifact.mjs --record FILE');
    const sessionRecord = JSON.parse(readFileSync(record, 'utf8'));
    const result = renderArtifact(sessionRecord, options);
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } catch (err) {
    process.stderr.write(`render-counsel-artifact: ${err instanceof Error ? err.message : String(err)}\n`);
    process.exit(1);
  }
}
