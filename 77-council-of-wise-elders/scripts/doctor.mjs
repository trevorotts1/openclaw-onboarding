#!/usr/bin/env node
// Council of Wise Elders: offline doctor.
// Verifies the installed package structurally: layout inventory,
// frontmatter and version agreement, the nine-seat roster with exact
// profile labels, JSON validity, manifest agreement, and the rule
// that no council state lives inside the skill folder.
// Usage: node doctor.mjs [--root <skill-folder>] [--distribution]
// Default: source package including its archive. --distribution explicitly checks
// an extracted package without certifying the original source archive.
// Exit 0 when every check passes, 1 otherwise. No network, no writes.\n// Generated runtime/dist and runtime/node_modules are not part of source integrity.

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkArchiveContract } from "./archive-contract.mjs";

const args = process.argv.slice(2);
const distribution = args.includes("--distribution");
const rootIdx = args.indexOf("--root");
const root = rootIdx >= 0
  ? resolve(args[rootIdx + 1])
  : resolve(dirname(fileURLToPath(import.meta.url)), "..");

const EXPECTED_SEATS = [
  "simon-sinek", "td-jakes", "oprah-winfrey", "tiffany-aliche",
  "russell-brunson", "michelle-obama", "brene-brown", "dennis-kimbro",
  "les-brown",
];
const ADVISOR_FILES = [
  "profile.json", "briefing.md", "frameworks.json", "decision-rules.json",
  "failure-patterns.json", "questions.json", "communication.md",
  "sources.json", "coverage.json", "evals.json",
];
const REFERENCES = [
  "protocol.md", "scoring.md", "source-policy.md", "model-routing.md",
  "report-template.md", "install-matrix.md", "troubleshooting.md",
];
const TOP_FILES = [
  "SKILL.md", "INSTALL.md", "INSTRUCTIONS.md", "EXAMPLES.md",
  "CORE_UPDATES.md", "QC.md", "CHANGELOG.md", "PREREQS.json", "version",
  "skill-version.txt", "manifest.json", "qc-council-of-wise-elders.sh",
];

let failures = 0;
const pass = (m) => console.log(`PASS ${m}`);
const fail = (m) => { failures += 1; console.log(`FAIL ${m}`); };
const info = (m) => console.log(`INFO ${m}`);

// Root-level .wired-<version> sentinels are written into every skill folder by
// update-skills.sh during a fleet roll. They are roll bookkeeping, not skill
// content, so they must not count toward the manifest tree hash.
function isGeneratedRuntimePath(rel) {
  return rel === "runtime/dist" || rel.startsWith("runtime/dist/")
    || rel === "runtime/node_modules" || rel.startsWith("runtime/node_modules/")
    || /^\.wired-[^/]*$/.test(rel);
}

function walk(dir, out = [], base = dir) {
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    const rel = relative(base, p).split("\\").join("/");
    if (isGeneratedRuntimePath(rel)) continue;
    if (statSync(p).isDirectory()) walk(p, out, base);
    else out.push(p);
  }
  return out;
}

console.log(`Council doctor: root = ${root}`);

// 1. Layout inventory.
const missing = [];
for (const f of TOP_FILES) if (!existsSync(join(root, f))) missing.push(f);
for (const f of ["agents/openai.yaml", "config/defaults.json",
  "config/advisors.json", "schemas/README.md",
  "assets/portrait-manifest.json", "assets/portraits/README.md",
  "assets/icons/README.md", "tests/fixtures/README.md",
  "runtime/package.json", "runtime/package-lock.json",
  "runtime/tsconfig.json", "runtime/README.md",
  "scripts/build-bundles.mjs", "scripts/verify-bundles.mjs",
  "scripts/install-runtime.mjs", "scripts/doctor.mjs",
  "scripts/export-skill22.mjs", "scripts/qc-council-of-wise-elders.sh",
  "scripts/qc-council-of-wise-elders.ps1"]) {
  if (!existsSync(join(root, f))) missing.push(f);
}
for (const r of REFERENCES) {
  if (!existsSync(join(root, "references", r))) missing.push(`references/${r}`);
}
for (const seat of EXPECTED_SEATS) {
  for (const f of ADVISOR_FILES) {
    if (!existsSync(join(root, "advisors", seat, f))) {
      missing.push(`advisors/${seat}/${f}`);
    }
  }
}
if (missing.length === 0) pass("layout inventory complete");
else fail(`layout inventory missing: ${missing.join(", ")}`);

// 2. Frontmatter and version agreement.
const skillMd = existsSync(join(root, "SKILL.md"))
  ? readFileSync(join(root, "SKILL.md"), "utf8") : "";
const fm = skillMd.match(/^---\n([\s\S]*?)\n---/);
const fmName = fm?.[1].match(/^name:\s*(\S+)\s*$/m)?.[1];
const fmVersion = fm?.[1].match(/^version:\s*(\S+)\s*$/m)?.[1];
if (fmName === "council-of-wise-elders") {
  pass("SKILL.md frontmatter name is council-of-wise-elders");
} else {
  fail(`SKILL.md frontmatter name is ${fmName ?? "(missing)"}, expected council-of-wise-elders`);
}
const norm = (v) => (v ?? "").trim().replace(/^v/, "");
const versionFile = existsSync(join(root, "version"))
  ? readFileSync(join(root, "version"), "utf8") : "";
const skillVersionFile = existsSync(join(root, "skill-version.txt"))
  ? readFileSync(join(root, "skill-version.txt"), "utf8") : "";
if (norm(versionFile) && norm(versionFile) === norm(skillVersionFile)
  && norm(versionFile) === norm(fmVersion)) {
  pass(`versions agree: version=${versionFile.trim()} skill-version.txt=${skillVersionFile.trim()} frontmatter=${fmVersion}`);
} else {
  fail(`version disagreement: version=${versionFile.trim()} skill-version.txt=${skillVersionFile.trim()} frontmatter=${fmVersion ?? "(missing)"}`);
}

// 3. Roster and labels.
let advisors = null;
try {
  advisors = JSON.parse(readFileSync(join(root, "config", "advisors.json"), "utf8"));
} catch (e) {
  fail(`config/advisors.json does not parse: ${e.message}`);
}
if (advisors) {
  const ids = advisors.seats?.map((s) => s.seat_id) ?? [];
  if (JSON.stringify(ids) === JSON.stringify(EXPECTED_SEATS)) {
    pass("roster is the fixed nine seats in order");
  } else {
    fail(`roster mismatch: ${ids.join(", ")}`);
  }
  let labelsOk = true;
  for (const seat of advisors.seats ?? []) {
    const expected = `AI perspective inspired by the published work of ${seat.name}. Not the individual and not an endorsement.`;
    if (seat.profile_label !== expected) {
      labelsOk = false;
      fail(`label mismatch for ${seat.seat_id}: ${seat.profile_label}`);
    }
    const profilePath = join(root, "advisors", seat.seat_id, "profile.json");
    if (existsSync(profilePath)) {
      const profile = JSON.parse(readFileSync(profilePath, "utf8"));
      if (profile.profile_label !== seat.profile_label) {
        labelsOk = false;
        fail(`profile.json label mismatch for ${seat.seat_id}`);
      }
    }
    info(`seat ${seat.seat_id}: pack_status=${seat.pack_status} owner=${seat.pack_owner_unit}`);
  }
  if (labelsOk) pass("all nine profile labels exact, config and profiles agree");
}

// 4. Every JSON file parses.
let jsonCount = 0;
for (const p of walk(root)) {
  if (p.endsWith(".json") && !p.includes("node_modules")) {
    jsonCount += 1;
    try { JSON.parse(readFileSync(p, "utf8")); }
    catch (e) { fail(`JSON parse: ${relative(root, p)}: ${e.message}`); }
  }
}
pass(`JSON files parsed: ${jsonCount}`);

// 5. No state inside the folder.
const stateHits = walk(root).filter((p) => {
  const rel = relative(root, p);
  return /\.(sqlite3?|db)$/i.test(rel)
    || /^(state|sessions|data)\//.test(rel)
    || /(^|\/)(sessions|verdicts|briefs)\.(json|ndjson)$/i.test(rel);
});
if (stateHits.length === 0) pass("no council state files inside the skill folder");
else fail(`state files inside skill folder: ${stateHits.map((p) => relative(root, p)).join(", ")}`);

// 6. Manifest agreement (tree hash), when a manifest exists.
const manifestPath = join(root, "manifest.json");
if (existsSync(manifestPath)) {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const archiveErrors = checkArchiveContract(root, manifest, distribution);
  for (const error of archiveErrors) fail(error);
  if (archiveErrors.length === 0) pass(distribution
    ? "explicit extracted distribution has no self-nested archive"
    : "source archive SHA-256 matches the source manifest");
  const pairs = [];
  for (const p of walk(root)) {
    const rel = relative(root, p).split("\\").join("/");
    if (rel === "manifest.json" || rel.endsWith(".skill")) continue;
    const bytes = readFileSync(p);
    pairs.push({ path: rel, hash: createHash("sha256").update(bytes).digest("hex") });
  }
  pairs.sort((a, b) => (a.path < b.path ? -1 : 1));
  const entries = pairs.map((x) => `${x.hash}  ${x.path}`);
  const aggregate = createHash("sha256").update(entries.join("\n") + "\n").digest("hex");
  if (aggregate === manifest.aggregate_sha256
    && entries.length === manifest.file_count) {
    pass(`manifest tree hash matches (${manifest.file_count} files)`);
  } else {
    fail(`manifest drift: computed ${aggregate} over ${entries.length} files, manifest says ${manifest.aggregate_sha256} over ${manifest.file_count}. Rebuild with scripts/build-bundles.mjs`);
  }
} else {
  fail("manifest.json missing: run scripts/build-bundles.mjs");
}

// 7. Optional: Skill 76 untouched, when inside a git checkout.
try {
  const repoRoot = resolve(root, "..");
  execFileSync("git", ["-C", repoRoot, "rev-parse", "--is-inside-work-tree"],
    { stdio: "pipe" });
  const status = execFileSync("git",
    ["-C", repoRoot, "status", "--porcelain", "--", "76-local-embedder"],
    { encoding: "utf8" });
  const diff = execFileSync("git",
    ["-C", repoRoot, "diff", "HEAD", "--name-only", "--", "76-local-embedder"],
    { encoding: "utf8" });
  if (status.trim() === "" && diff.trim() === "") {
    pass("76-local-embedder untouched in this checkout");
  } else {
    fail(`76-local-embedder has changes in this checkout: ${status.trim()} ${diff.trim()}`);
  }
} catch {
  info("not inside a git checkout: Skill 76 check skipped (source-tree check)");
}

console.log(failures === 0
  ? "DOCTOR: PASS"
  : `DOCTOR: FAIL (${failures} failing check(s))`);
process.exit(failures === 0 ? 0 : 1);
