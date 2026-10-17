import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  existsSync, lstatSync, mkdtempSync, mkdirSync, readFileSync,
  rmSync, symlinkSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  APPROVED_PERSONA_MAPPING,
  EXPECTED_SEAT_IDS,
  auditExistingSkill22,
  inspectPersonaDirectory,
} from "../audit-skill22-personas.mjs";

const script = resolve(dirname(fileURLToPath(import.meta.url)), "..", "audit-skill22-personas.mjs");
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

test("the exact nine user-selected Council seats are the ONLY mapping", () => {
  const expected = [
    "simon-sinek", "td-jakes", "oprah-winfrey", "tiffany-aliche",
    "russell-brunson", "michelle-obama", "brene-brown", "dennis-kimbro",
    "les-brown",
  ];
  assert.deepEqual([...EXPECTED_SEAT_IDS], expected);
  assert.equal(APPROVED_PERSONA_MAPPING.length, 9);
  assert.ok(!JSON.stringify(APPROVED_PERSONA_MAPPING).toLowerCase().includes("steve-harvey"));
  assert.ok(!JSON.stringify(APPROVED_PERSONA_MAPPING).toLowerCase().includes("steve harvey"));
  assert.equal(new Set(APPROVED_PERSONA_MAPPING.flatMap((s) => s.folders)).size, 14);
});

test("real Skill 22 has 14 registered existing derivatives tied only to approved seats", () => {
  const result = auditExistingSkill22(repoRoot);
  assert.equal(result.summary.approved_seats, 9);
  assert.equal(result.summary.mapped_existing_personas, 14);
  assert.equal(result.summary.seats_with_existing_personas, 7);
  assert.equal(result.summary.seats_without_existing_personas, 2);
  assert.ok(result.summary.existing_artifacts >= 14);
  assert.equal(result.summary.qualified_primary_books_by_this_audit, 0);
  for (const seat of result.seats) {
    assert.equal(seat.primary_material_qualified, false);
    for (const p of seat.personas) {
      assert.equal(p.registered, true);
      assert.equal(p.is_original_book_verified, false);
      assert.equal(p.has_persona_blueprint, true);
      assert.ok(p.artifacts.every((a) =>
        a.source_class === "skill22_derived_artifact_not_verified_primary_text" &&
        /^[a-f0-9]{64}$/.test(a.sha256) && a.bytes > 0,
      ));
    }
  }
  assert.deepEqual(
    result.seats.filter((s) => !s.has_matching_existing_persona).map((s) => s.seat_id),
    ["oprah-winfrey", "les-brown"],
  );
});

test("CLI check and JSON modes are real, read-only and preserve Skill 22 data", () => {
  const baseline = readFileSync(join(
    repoRoot,
    "22-book-to-persona-coaching-leadership-system/personas/sinek-start-with-why/persona-blueprint.md",
  ));
  const original = createHash("sha256").update(baseline).digest("hex");
  const text = execFileSync(process.execPath, [script, "--check"], { encoding: "utf8" });
  assert.match(text, /14 registered existing personas/);
  const doc = JSON.parse(execFileSync(process.execPath, [script, "--json"], { encoding: "utf8" }));
  assert.equal(doc.schema, "wise-elders.existing-skill22-persona-audit/v1");
  assert.equal(doc.readonly, true);
  const after = readFileSync(join(
    repoRoot,
    "22-book-to-persona-coaching-leadership-system/personas/sinek-start-with-why/persona-blueprint.md",
  ));
  assert.equal(createHash("sha256").update(after).digest("hex"), original);
});

test("a symlinked or missing persona blueprint is rejected rather than used as a book", () => {
  const root = mkdtempSync(join(tmpdir(), "council-skill22-safety-"));
  try {
    const folder = join(root, "22-book-to-persona-coaching-leadership-system/personas/sinek-start-with-why");
    mkdirSync(folder, { recursive: true });
    const outside = join(root, "outside.txt");
    writeFileSync(outside, "Do not import this linked content.");
    const blueprint = join(folder, "persona-blueprint.md");
    symlinkSync(outside, blueprint);
    assert.throws(() => inspectPersonaDirectory(root, "sinek-start-with-why"), /not an ordinary file|outside/);
    rmSync(blueprint);
    assert.throws(() => inspectPersonaDirectory(root, "sinek-start-with-why"), /lacks its persona-blueprint/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("path traversal and unapproved person folders do not enter the fixed mapping", () => {
  const root = mkdtempSync(join(tmpdir(), "council-skill22-unknown-"));
  try {
    assert.throws(() => inspectPersonaDirectory(root, "../../steve-harvey"), /Rejected unapproved/);
    assert.throws(() => inspectPersonaDirectory(root, "steve-harvey"), /missing/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
