// PRES-006 — offline gate for the canonical intake field-path contract.
//   node --test test/test_pres006_contract.mjs
//
// Covers: required set == contract, false-vs-missing, legacy migration
// (move / redundant / contradiction / version guards), and the generated UI
// sync (pages + questions.json + both HTML question blocks regenerate from
// the contract without drift).

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = dirname(here);

const { INTAKE_CONTRACT } = await import(join(app, "schema", "intake_fields.js"));
const {
  validateIntakeCompleteness,
  validateAndMigrate,
  migrateIntake,
  readPath,
  isPresent,
} = await import(join(app, "schema", "intake_contract.js"));

function completeIntake() {
  return {
    schema_version: 2,
    deck_brief: {
      OFFER_NAME: "The Momentum Method",
      NAMED_METHODOLOGY: "The Three-Move Pipeline",
      TRANSFORMATION_PROMISE: "stuck -> closing",
      TIME_TO_RESULT: "8 weeks",
      AUDIENCE: "women entrepreneurs, 35-55",
      CTA_ACTION: "book a call",
      TONE: "Inspirational",
      FINAL_PRICE: "$497",
    },
    pre_presentation_capture: {
      PRESENTATION_TYPE: "from_scratch",
      WANT_SALES_CHECKOUT: "yes",
      WANT_VSL_PAGE: "no",
    },
    intake: { speech_speed_preference: "default" },
    answers: {},
  };
}

test("required set comes from the contract, not a hand copy", () => {
  const derived = INTAKE_CONTRACT.fields
    .filter((f) => f.required && f.block_gate)
    .filter((f) => !f.conditional_on) // conditional follow-ups gate via their controller
    .map((f) => f.canonical_path)
    .sort();
  assert.deepEqual([...INTAKE_CONTRACT.required_fields].sort(), derived);
});

test("a complete intake passes", () => {
  const r = validateIntakeCompleteness(completeIntake());
  assert.ok(r.ok, JSON.stringify(r.missing));
  assert.equal(r.missing.length, 0);
});

test("false/no is an ANSWER, never missing", () => {
  const intake = completeIntake();
  intake.pre_presentation_capture.WANT_SALES_CHECKOUT = "no";
  intake.pre_presentation_capture.WANT_VSL_PAGE = false;
  const r = validateIntakeCompleteness(intake);
  assert.ok(r.ok, "a real no/false answer must satisfy the gate");
  assert.ok(isPresent("no"));
  assert.ok(isPresent(false));
});

test("missing is missing: absent/None/blank are named specifically", () => {
  const intake = completeIntake();
  delete intake.deck_brief.OFFER_NAME;
  intake.pre_presentation_capture.WANT_VSL_PAGE = "";
  const r = validateIntakeCompleteness(intake);
  assert.ok(!r.ok);
  assert.deepEqual(r.missing.sort(), [
    "deck_brief.OFFER_NAME",
    "pre_presentation_capture.WANT_VSL_PAGE",
  ]);
});

test("legacy deck_brief.WANT_SALES_CHECKOUT migrates to pre_presentation_capture", () => {
  const legacy = {
    deck_brief: { WANT_SALES_CHECKOUT: "yes", WANT_VSL_PAGE: "no", OFFER_NAME: "X" },
    pre_presentation_capture: { PRESENTATION_TYPE: "from_scratch" },
    intake: { speech_speed_preference: "default" },
  };
  // fill the rest minimally so the gate passes after migration
  Object.assign(legacy.deck_brief, {
    NAMED_METHODOLOGY: "M", TRANSFORMATION_PROMISE: "T", TIME_TO_RESULT: "8w",
    AUDIENCE: "A", CTA_ACTION: "C", TONE: "Tone", FINAL_PRICE: "$1",
  });
  const r = validateAndMigrate(legacy);
  assert.ok(r.ok, JSON.stringify(r));
  assert.equal(legacy.pre_presentation_capture.WANT_SALES_CHECKOUT, "yes");
  assert.equal(legacy.pre_presentation_capture.WANT_VSL_PAGE, "no");
  assert.equal(legacy.deck_brief.WANT_SALES_CHECKOUT, undefined);
  assert.equal(legacy.schema_version, 2);
});

test("booleanish legacy true/false normalizes to yes/no", () => {
  const legacy = {
    deck_brief: { WANT_SALES_CHECKOUT: true },
    pre_presentation_capture: {},
  };
  const r = migrateIntake(legacy);
  assert.ok(r.ok);
  assert.equal(legacy.pre_presentation_capture.WANT_SALES_CHECKOUT, "yes");
});

test("contradictory legacy values are REFUSED with the migration note", () => {
  const bad = {
    pre_presentation_capture: { WANT_SALES_CHECKOUT: "yes" },
    deck_brief: { WANT_SALES_CHECKOUT: "no" },
  };
  const r = migrateIntake(bad);
  assert.ok(!r.ok);
  assert.ok(r.note.includes("migration refused"));
  assert.ok(r.note.includes("WANT_SALES_CHECKOUT"));
  assert.equal(r.conflicts.length, 1);
  assert.equal(r.conflicts[0].legacy_value, "no");
  assert.equal(r.conflicts[0].canonical_value, "yes");
});

test("a newer schema_version refuses to downgrade", () => {
  const future = { schema_version: 99 };
  const r = migrateIntake(future);
  assert.ok(!r.ok);
  assert.match(r.note, /newer than this build/);
});

test("an already-current record passes through untouched", () => {
  const cur = completeIntake();
  const r = migrateIntake(cur);
  assert.ok(r.ok);
  assert.deepEqual(r.migrated, []);
});

test("validateAndMigrate names missing fields specifically", () => {
  const intake = { schema_version: 2, deck_brief: {}, pre_presentation_capture: {} };
  const r = validateAndMigrate(intake);
  assert.ok(!r.ok);
  assert.ok(r.missing.includes("pre_presentation_capture.WANT_SALES_CHECKOUT"));
  assert.ok(r.note.includes("missing"));
});

test("the generated UI regenerates from the contract without drift", () => {
  // --check exits non-zero when pages/index.html, pages/questions.json or
  // schema/intake_fields.json drift from the contract. (deployed-r2/
  // public/index.html is PRES-005-owned and server-driven — outside this
  // generator by design, see the disjoint-ownership repair.)
  execFileSync(process.execPath, [join(app, "tools", "gen_ui_questions.mjs"), "--check"], {
    cwd: app,
    stdio: "pipe",
  });
});

test("the PRES-006 UI page asks the conditional declined-reason only after a no", () => {
  for (const page of ["pages/index.html"]) {
    const html = readFileSync(join(app, page), "utf-8");
    assert.match(html, /conditional_on: \{ id: "want_sales_checkout", equals: "no" \}/, page);
    assert.match(html, /conditional_on: \{ id: "want_vsl_page", equals: "no" \}/, page);
    assert.match(html, /function conditionMet/, page);
  }
});
