#!/usr/bin/env node
// render.mjs - Generic workforce-structure infographic renderer.
//
// Reads a JSON input file describing the company + its departments, fills the
// HTML template with parameter substitutions, opens it in a headless Chromium
// via Playwright, and screenshots at exactly 1920x1080 to the output path.
//
// Usage:
//   node render.mjs --input <input.json> --output <output.png>
//
// Input JSON shape (any extras are ignored):
//   {
//     "companyName":     "Marico Consulting",
//     "monogramLetter":  "M",                       // optional, falls back to first letter
//     "ownerName":       "Maria Anderson",
//     "ceoAgentName":    "Sir Jordan",
//     "ceoAgentTagline": "Routes all work · Reports to Maria Anderson",
//     "departments": [
//       { "slug": "marketing", "name": "Marketing",  "roles": 2, "emoji": "📣" },
//       ...
//     ]
//   }
//
// Cluster assignment is done by ./cluster-classifier.js (see that file for the
// canonical slug → cluster map). Unmapped depts fall into Technology so they
// are never silently dropped.
//
// This script renders the chart with PERFECT text labels (every department
// name and role count is real DOM text, not a diffusion-model hallucination).
// It is therefore the default for any text-heavy ZHC closeout infographic.

import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { classify } from './cluster-classifier.js';

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--input') out.input = argv[++i];
    else if (a === '--output') out.output = argv[++i];
    else if (a === '--template') out.template = argv[++i];
    else if (a === '--keep-html') out.keepHtml = true;
  }
  return out;
}

function fail(msg, code = 1) {
  console.error('[render] ERROR: ' + msg);
  process.exit(code);
}

function firstLetter(s) {
  if (!s || typeof s !== 'string') return '';
  const m = s.trim().match(/[A-Za-z0-9]/);
  return m ? m[0].toUpperCase() : '';
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.input || !args.output) {
    fail('usage: node render.mjs --input <input.json> --output <output.png>', 2);
  }

  const __dirname = dirname(fileURLToPath(import.meta.url));
  const templatePath = args.template
    ? resolve(args.template)
    : resolve(__dirname, 'index.html.template');

  let raw;
  try {
    raw = await readFile(args.input, 'utf8');
  } catch (e) {
    fail('cannot read input ' + args.input + ': ' + e.message);
  }
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    fail('input is not valid JSON: ' + e.message);
  }

  const companyName = (data.companyName || 'Your Company').toString();
  const monogramLetter = (data.monogramLetter || firstLetter(companyName) || 'Z').toString();
  const ownerName = (data.ownerName || 'the Owner').toString();
  const ceoAgentName = (data.ceoAgentName || data.agentName || 'CEO Agent').toString();
  const ceoAgentTagline = (data.ceoAgentTagline || ('Routes all work · Reports to ' + ownerName)).toString();
  const departments = Array.isArray(data.departments) ? data.departments : [];

  const buckets = classify(departments);
  const totalDepts = departments.length;
  const totalRoles = departments.reduce((acc, d) => acc + (Number(d && (d.roles ?? d.rolesDone)) || 0), 0);

  let template;
  try {
    template = await readFile(templatePath, 'utf8');
  } catch (e) {
    fail('cannot read template ' + templatePath + ': ' + e.message);
  }

  const replacements = {
    '{{COMPANY_NAME}}': companyName,
    '{{MONOGRAM_LETTER}}': monogramLetter,
    '{{OWNER_NAME}}': ownerName,
    '{{CEO_AGENT_NAME}}': ceoAgentName,
    '{{CEO_AGENT_TAGLINE}}': ceoAgentTagline,
    '{{TOTAL_DEPTS}}': String(totalDepts),
    '{{TOTAL_ROLES}}': String(totalRoles),
    '{{DEPTS_OPERATIONS_JSON}}': JSON.stringify(buckets.ops),
    '{{DEPTS_REVENUE_JSON}}': JSON.stringify(buckets.rev),
    '{{DEPTS_CREATIVE_JSON}}': JSON.stringify(buckets.cre),
    '{{DEPTS_TECHNOLOGY_JSON}}': JSON.stringify(buckets.tec)
  };

  let html = template;
  for (const [k, v] of Object.entries(replacements)) {
    html = html.split(k).join(v);
  }

  const workDir = await mkdtemp(join(tmpdir(), 'zhc-org-chart-'));
  const htmlPath = join(workDir, 'index.html');
  await writeFile(htmlPath, html, 'utf8');

  // Defer the playwright import so a missing install fails with a clear msg.
  let chromium;
  try {
    ({ chromium } = await import('playwright'));
  } catch (e) {
    fail('playwright is not installed. Run: npm install playwright && npx playwright install chromium');
  }

  const browser = await chromium.launch();
  try {
    const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
    const page = await ctx.newPage();
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'networkidle' });
    // Give web fonts a beat to settle so type renders crisp instead of fallback.
    await page.waitForTimeout(1200);
    await page.screenshot({ path: args.output, fullPage: false, omitBackground: false });
  } finally {
    await browser.close();
    if (!args.keepHtml) {
      await rm(workDir, { recursive: true, force: true });
    } else {
      console.log('[render] kept HTML at ' + htmlPath);
    }
  }

  console.log('[render] wrote ' + args.output + ' (' + totalDepts + ' depts, ' + totalRoles + ' roles)');
}

main().catch((e) => fail(e && e.stack ? e.stack : String(e)));
