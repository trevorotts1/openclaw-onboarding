#!/usr/bin/env node
// =============================================================================
// PRES-006 — generate the UI question sets from the ONE canonical contract.
// =============================================================================
// The hosted UI (pages/index.html, deployed-r2/public/index.html) embeds its
// QUESTIONS array between /*__QUESTIONS__*/[ ... ]; pages/questions.json is
// the JSON projection the box minted from (used by the fallback snapshot and
// the tests). Both are GENERATED here from schema/intake_fields.js — the UI
// never restates a field path, so form and validators cannot drift.
//
// Usage:
//   node tools/gen_ui_questions.mjs --check     # exit 1 when generated != on disk
//   node tools/gen_ui_questions.mjs             # rewrite both UIs + the JSON

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const here = dirname(fileURLToPath(import.meta.url));
const app = dirname(here);
const require = createRequire(import.meta.url);

// intake_fields.js is an ES module; the JSON projection is generated from it
// and consumed by the Python tests (stdlib-only).
const { INTAKE_CONTRACT } = await import("../schema/intake_fields.js");

const PAGES_HTML = join(app, "pages", "index.html");
const R2_HTML = join(app, "deployed-r2", "public", "index.html");
const QUESTIONS_JSON = join(app, "pages", "questions.json");
const CONTRACT_JSON = join(app, "schema", "intake_fields.json");

// ---- ES-literal rendering --------------------------------------------------

function jsStr(s) {
  return JSON.stringify(s);
}

function renderQuestionLiteral(q) {
  const lines = [];
  const tail = [];
  if (q.key !== undefined) tail.push(`key: ${jsStr(q.key)}`);
  if (q.logo_on_slides) tail.push(`logo_on_slides: ${jsStr(q.logo_on_slides)}`);
  if (q.conditional_on) tail.push(`conditional_on: { id: ${jsStr(q.conditional_on.id)}, equals: ${jsStr(q.conditional_on.equals)} }`);
  if (q.allowed_values) tail.push(`allowed_values: [${q.allowed_values.map(jsStr).join(", ")}]`);
  if (q.allowed_values && q.value_labels) {
    tail.push(`value_labels: { ${q.allowed_values.map((v) => `${jsStr(v)}: ${jsStr(q.value_labels[v])}`).join(", ")} }`);
  }
  lines.push(`      { id: ${jsStr(q.id)}, order: ${q.order}, kind: ${jsStr(q.kind)},`);
  lines.push(`        prompt: ${jsStr(q.prompt)},`);
  if (q.help !== undefined) lines.push(`        help: ${jsStr(q.help)},`);
  if (q.label !== undefined) lines.push(`        label: ${jsStr(q.label)},`);
  if (q.placeholder !== undefined) lines.push(`        placeholder: ${jsStr(q.placeholder)},`);
  if (q.default !== undefined) lines.push(`        default: ${jsStr(q.default)},`);
  lines.push(`        required: ${q.required ? "true" : "false"}, storeOn: ${jsStr(q.storeOn)}${tail.length ? "," : " }"}`);
  if (tail.length) lines.push(`        ${tail.join(", ")} }`);
  return lines.join("\n");
}

function renderQuestionsLiteral(questions) {
  const parts = questions.map(renderQuestionLiteral);
  return parts.join(",\n");
}

// The generated block replaces the array literal ONLY — page structure,
// styling, and submission plumbing are untouched.
const BLOCK_START = "/*__QUESTIONS__*/[";
const BLOCK_END_MATCH = /^\s{4}\];$/m;

function spliceQuestions(html, block) {
  const start = html.indexOf(BLOCK_START);
  if (start === -1) throw new Error("/*__QUESTIONS__*/[ marker not found");
  const afterStart = start + BLOCK_START.length;
  // Find the closing "];" of the array literal: first line that is exactly "    ];"
  const tail = html.slice(afterStart);
  const endMatch = tail.match(BLOCK_END_MATCH);
  if (!endMatch) throw new Error("closing ]; of the QUESTIONS array not found");
  const end = afterStart + endMatch.index;
  return html.slice(0, afterStart) + "\n" + block + "\n" + html.slice(end);
}

// ---- JSON projection -------------------------------------------------------

function buildJsonProjection() {
  const fields = INTAKE_CONTRACT.fields;
  const questions = fields.map((f) => {
    const q = { ...f.question };
    return q;
  });
  return {
    $schema: "https://openclaw.ai/schemas/intake-section/v1",
    section: "deck-intake-mini",
    version: "2.0.0",
    question_set: "standard",
    source: "GENERATED from interview-app/schema/intake_fields.js (PRES-006 canonical field-path contract) — edit the contract, not this file. tools/gen_ui_questions.mjs regenerates pages/index.html, deployed-r2/public/index.html and this snapshot in one pass so the form can never disagree with the Workers' schema-driven completeness gate.",
    contract_version: INTAKE_CONTRACT.version,
    description:
      "Curated intake question set for the Presentation Interview app, GENERATED from the one canonical field-path contract. Every question id, prompt, kind, allowed_values, value_labels, storeOn and conditional_on comes from schema/intake_fields.js. The upsell yes/no flags and their verbatim declined-reason waivers store canonically under pre_presentation_capture.* (the storeTarget home every engine consumer reads); the Workers gate completeness against the same contract. Cap 20; this set is " + questions.length + ".",
    questions,
  };
}

// ---- contract JSON projection (Python-side pinning) ------------------------

function buildContractProjection() {
  const c = INTAKE_CONTRACT;
  return {
    contract: c.contract,
    version: c.version,
    description: c.description,
    required_fields: c.required_fields,
    migration: c.migration,
    fields: c.fields.map((f) => ({
      id: f.id,
      canonical_path: f.canonical_path,
      section: f.section,
      kind: f.kind,
      required: f.required,
      block_gate: f.block_gate,
      allowed_values: f.allowed_values || null,
      legacy_aliases: f.legacy_aliases || [],
    })),
  };
}

// ---- main ------------------------------------------------------------------

function main() {
  const checkOnly = process.argv.includes("--check");
  const projection = buildJsonProjection();
  const block = renderQuestionsLiteral(projection.questions);
  const newText = JSON.stringify(projection, null, 2) + "\n";
  const contractText = JSON.stringify(buildContractProjection(), null, 2) + "\n";

  let failed = false;

  for (const [label, path] of [["pages/index.html", PAGES_HTML], ["deployed-r2/public/index.html", R2_HTML]]) {
    const html = readFileSync(path, "utf-8");
    const generated = spliceQuestions(html, block);
    if (checkOnly) {
      if (generated !== html) {
        console.error(`[gen-ui] DRIFT: ${label} does not match the contract output (run tools/gen_ui_questions.mjs to regenerate)`);
        failed = true;
      } else {
        console.log(`[gen-ui] OK: ${label} matches the contract`);
      }
    } else {
      writeFileSync(path, generated, "utf-8");
      console.log(`[gen-ui] wrote ${label} (${projection.questions.length} questions)`);
    }
  }

  const jsonNow = readFileSync(QUESTIONS_JSON, "utf-8");
  if (checkOnly) {
    if (jsonNow !== newText) {
      console.error("[gen-ui] DRIFT: pages/questions.json does not match the contract output");
      failed = true;
    } else {
      console.log("[gen-ui] OK: pages/questions.json matches the contract");
    }
  } else {
    writeFileSync(QUESTIONS_JSON, newText, "utf-8");
    console.log(`[gen-ui] wrote pages/questions.json (${projection.questions.length} questions)`);
  }

  // The JSON projection the Python tests read (stdlib json only — they cannot
  // import an ES module). Regenerated in the same pass so it cannot drift.
  let contractNow = "";
  try { contractNow = readFileSync(CONTRACT_JSON, "utf-8"); } catch { /* first run */ }
  if (checkOnly) {
    if (contractNow !== contractText) {
      console.error("[gen-ui] DRIFT: schema/intake_fields.json does not match the contract");
      failed = true;
    } else {
      console.log("[gen-ui] OK: schema/intake_fields.json matches the contract");
    }
  } else {
    writeFileSync(CONTRACT_JSON, contractText, "utf-8");
    console.log("[gen-ui] wrote schema/intake_fields.json (contract projection)");
  }

  if (failed) process.exit(1);
}

main();