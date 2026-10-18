#!/usr/bin/env node
/**
 * WER-013: protect and account for the USER'S existing Skill 22 material.
 *
 * READ ONLY. This inventory never modifies the Council roster, writes to
 * Skill 22, promotes derivative notes to verified books, or adds a person.
 * It deliberately reads only the explicitly approved nine-seat mapping.
 *
 * From onboarding repo:
 *   node 77-council-of-wise-elders/scripts/audit-skill22-personas.mjs --json
 *   node 77-council-of-wise-elders/scripts/audit-skill22-personas.mjs --check
 *
 * An existing persona blueprint is a valuable source candidate, not proof
 * of licensed full-book ingestion or primary-source qualification.
 */
import { createHash } from "node:crypto";
import { existsSync, lstatSync, readFileSync, readdirSync, realpathSync } from "node:fs";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SKILL22 = "22-book-to-persona-coaching-leadership-system";
const SKILL77 = "77-council-of-wise-elders";

export const APPROVED_PERSONA_MAPPING = Object.freeze([
  { seat_id: "simon-sinek", name: "Simon Sinek", folders: ["sinek-start-with-why", "sinek-find-your-why"] },
  { seat_id: "td-jakes", name: "T. D. Jakes", folders: ["jakes-instinct"] },
  { seat_id: "oprah-winfrey", name: "Oprah Winfrey", folders: [] },
  { seat_id: "tiffany-aliche", name: "Tiffany Aliche", folders: ["aliche-get-good-with-money"] },
  { seat_id: "russell-brunson", name: "Russell Brunson", folders: [
    "brunson-marketing-secrets-blackbook",
    "brunson-network-marketing-secrets",
    "russell-brunson-lead-funnels",
    "russell-brunson-the-funnel-hackers-cookbook",
    "russell-brunson-traffic-secrets",
  ] },
  { seat_id: "michelle-obama", name: "Michelle Obama", folders: ["obama-becoming", "obama-light-we-carry"] },
  { seat_id: "brene-brown", name: "Brené Brown", folders: ["brown-atlas-of-heart"] },
  { seat_id: "dennis-kimbro", name: "Dr. Dennis Kimbro", folders: [
    "kimbro-the-wealth-choice", "kimbro-what-makes-great-great",
  ] },
  { seat_id: "les-brown", name: "Les Brown", folders: [] },
]);

export const EXPECTED_SEAT_IDS = Object.freeze(APPROVED_PERSONA_MAPPING.map((seat) => seat.seat_id));
const MAX_ARTIFACT_BYTES = 10 * 1024 * 1024;
const EXPECTED_ARTIFACT_SUFFIXES = new Set([".md", ".json"]);

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function safelyRead(path, allowedRoot) {
  const target = resolve(path);
  const realRoot = realpathSync(allowedRoot);
  const rootPrefix = realRoot + sep;
  const lexicalRoot = resolve(allowedRoot);
  if (!(target === lexicalRoot || target.startsWith(lexicalRoot + sep))) {
    throw new Error("Skill 22 asset path escaped its approved root");
  }
  const info = lstatSync(target);
  if (info.isSymbolicLink() || !info.isFile()) {
    throw new Error("Skill 22 asset is not an ordinary file: " + path);
  }
  if (info.size > MAX_ARTIFACT_BYTES) {
    throw new Error("Skill 22 asset is over the bounded audit size: " + path);
  }
  const real = realpathSync(target);
  if (!(real === realRoot || real.startsWith(rootPrefix))) {
    throw new Error("Skill 22 asset resolves outside the approved root: " + path);
  }
  return readFileSync(real);
}

function rosterFromContracts(text) {
  const matched = text.match(/export const SEAT_IDS\s*=\s*\[([\s\S]*?)\]\s*as const/);
  if (!matched) throw new Error("Canonical Skill 77 SEAT_IDS not found");
  return [...matched[1].matchAll(/'([a-z0-9-]+)'/g)].map((m) => m[1]);
}

export function validateRoster(repoRoot) {
  const skill77 = join(repoRoot, SKILL77);
  const contractText = readFileSync(join(skill77, "runtime/src/contracts/enums.ts"), "utf8");
  const skillText = readFileSync(join(skill77, "SKILL.md"), "utf8");
  const ids = rosterFromContracts(contractText);
  if (JSON.stringify(ids) !== JSON.stringify(EXPECTED_SEAT_IDS)) {
    throw new Error("Council contract roster differs from the user's nine approved advisors");
  }
  const rosterSection = skillText.split("## The nine seats")[1]?.split("\n## ")[0] ?? "";
  const idsFromSkill = [...rosterSection.matchAll(/^\|\s*([a-z0-9-]+)\s*\|/gm)]
    .map((m) => m[1])
    // Markdown's |---|---| separator is not a seat ID.
    .filter((id) => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id));
  if (JSON.stringify(idsFromSkill) !== JSON.stringify(EXPECTED_SEAT_IDS)) {
    throw new Error("Council SKILL.md roster is inconsistent with the user's nine approved advisors");
  }
  return ids;
}

export function inspectPersonaDirectory(repoRoot, folder) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(folder)) {
    throw new Error("Rejected unapproved persona folder identifier");
  }
  const base = join(repoRoot, SKILL22, "personas");
  const location = join(base, folder);
  if (!existsSync(location)) {
    throw new Error("Previously registered Skill 22 persona folder is missing: " + folder);
  }
  if (lstatSync(location).isSymbolicLink() || !lstatSync(location).isDirectory()) {
    throw new Error("Persona folder is not an ordinary directory: " + folder);
  }
  const files = readdirSync(location).sort();
  const artifacts = [];
  for (const name of files) {
    if (!EXPECTED_ARTIFACT_SUFFIXES.has(extname(name))) {
      throw new Error("Unexpected asset type in approved Skill 22 persona " + folder + ": " + name);
    }
    if (name.includes("/") || name.includes("\\")) {
      throw new Error("Unsafe Skill 22 artifact name: " + name);
    }
    const candidate = join(location, name);
    const bytes = safelyRead(candidate, base);
    artifacts.push({
      file: relative(repoRoot, candidate).split(sep).join("/"),
      bytes: bytes.length,
      sha256: sha256(bytes),
      source_class: "skill22_derived_artifact_not_verified_primary_text",
    });
  }
  if (!artifacts.some((a) => a.file.endsWith("/persona-blueprint.md"))) {
    throw new Error("Approved Skill 22 folder lacks its persona-blueprint.md: " + folder);
  }
  return {
    folder,
    artifacts,
    has_extraction_notes: files.includes("extraction-notes.md"),
    has_analysis_notes: files.includes("analysis-notes.md"),
    has_persona_blueprint: true,
    is_original_book_verified: false,
  };
}

export function auditExistingSkill22(repoRoot = ROOT) {
  validateRoster(repoRoot);
  const skill22Base = join(repoRoot, SKILL22);
  const seed = JSON.parse(
    readFileSync(join(skill22Base, "persona-categories.json"), "utf8"),
  );
  if (typeof seed !== "object" || !seed || !seed.personas || typeof seed.personas !== "object") {
    throw new Error("Skill 22 canonical persona registry is invalid");
  }
  const seen = new Set();
  const seats = APPROVED_PERSONA_MAPPING.map((seat) => ({
    seat_id: seat.seat_id,
    display_name: seat.name,
    personas: seat.folders.map((folder) => {
      if (seen.has(folder)) throw new Error("Skill 22 folder mapped into Council twice: " + folder);
      seen.add(folder);
      const registered = seed.personas[folder];
      if (!registered || !registered.book || !registered.author) {
        throw new Error("Existing Skill 22 persona not found in canonical registry: " + folder);
      }
      return {
        registry_key: folder,
        author_in_skill22: registered.author,
        book_in_skill22: registered.book,
        registered: true,
        ...inspectPersonaDirectory(repoRoot, folder),
      };
    }),
    // A missing exact Skill 22 folder is an evidence supply gap, not
    // permission to substitute another person's book or an unrelated persona.
    has_matching_existing_persona: seat.folders.length > 0,
    primary_material_qualified: false,
  }));
  const all = seats.flatMap((seat) => seat.personas);
  const detected = new Set(seats.map((seat) => seat.seat_id));
  if (seats.length !== 9 || detected.size !== 9 || all.length !== 14) {
    throw new Error("Nine-seat/fourteen-existing-persona invariant failed");
  }
  return {
    schema: "wise-elders.existing-skill22-persona-audit/v1",
    canonical_skill: SKILL77,
    existing_persona_skill: SKILL22,
    readonly: true,
    source_quality_note: "Existing extraction-notes and persona blueprints are preserved and candidate-useful, but unverified primary texts. Do not manufacture quotations, promote source coverage or add Council members.",
    summary: {
      approved_seats: seats.length,
      mapped_existing_personas: all.length,
      seats_with_existing_personas: seats.filter((s) => s.has_matching_existing_persona).length,
      seats_without_existing_personas: seats.filter((s) => !s.has_matching_existing_persona).length,
      existing_artifacts: all.reduce((sum, p) => sum + p.artifacts.length, 0),
      qualified_primary_books_by_this_audit: 0,
    },
    seats,
  };
}

function cli() {
  const args = process.argv.slice(2);
  if (args.some((a) => !["--json", "--check"].includes(a))) {
    process.stderr.write("Usage: node audit-skill22-personas.mjs [--json|--check]\n");
    process.exitCode = 2;
    return;
  }
  try {
    const report = auditExistingSkill22();
    if (args.includes("--json")) {
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
      return;
    }
    const { summary } = report;
    process.stdout.write(
      "Skill 22 read-only audit PASS: " +
      summary.approved_seats + " Council seats, " +
      summary.mapped_existing_personas + " registered existing personas, " +
      summary.existing_artifacts + " derivative artifacts, " +
      summary.seats_without_existing_personas + " seats without existing Skill 22 personas.\n",
    );
    process.stdout.write(
      "Primary-source qualification is NOT implied; no roster or Skill 22 files changed.\n",
    );
  } catch (error) {
    process.stderr.write(
      "Skill 22 Council inventory FAIL: " +
      (error instanceof Error ? error.message : String(error)) + "\n",
    );
    process.exitCode = 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) cli();
