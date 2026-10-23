#!/usr/bin/env node
// Council of Wise Elders: bundle verifier.
// Recomputes the tree hash and compares it with manifest.json, checks
// the SKILL.md frontmatter name against the portable skill name, and
// checks that no state files live inside the folder.
// Usage: node verify-bundles.mjs [--root <skill-folder>] [--distribution]
// Default: source package including its archive. --distribution explicitly checks
// an extracted package without certifying the original source archive.
// Exit 0 on agreement, 1 on any drift.\n// Generated runtime/dist and runtime/node_modules are excluded from source integrity.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkArchiveContract } from "./archive-contract.mjs";
import { checkEntryPoint } from "./entry-point-gate.mjs";

const args = process.argv.slice(2);
const distribution = args.includes("--distribution");
const rootIdx = args.indexOf("--root");
const root = rootIdx >= 0
  ? resolve(args[rootIdx + 1])
  : resolve(dirname(fileURLToPath(import.meta.url)), "..");

let failures = 0;
const pass = (m) => console.log(`PASS ${m}`);
const fail = (m) => { failures += 1; console.log(`FAIL ${m}`); };

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

const manifestPath = join(root, "manifest.json");
if (!existsSync(manifestPath)) {
  console.log("FAIL manifest.json missing: run scripts/build-bundles.mjs");
  process.exit(1);
}
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

const skillMd = readFileSync(join(root, "SKILL.md"), "utf8");
const fmName = skillMd.match(/^---\n[\s\S]*?^name:\s*(\S+)\s*$/m)?.[1];
if (fmName === manifest.skill && fmName === "council-of-wise-elders") {
  pass("frontmatter name matches the portable skill name");
} else {
  fail(`frontmatter name ${fmName ?? "(missing)"} != manifest skill ${manifest.skill}`);
}

const current = new Map();
for (const p of walk(root)) {
  const rel = relative(root, p).split("\\").join("/");
  if (rel === "manifest.json" || rel.endsWith(".skill")) continue;
  current.set(rel, createHash("sha256").update(readFileSync(p)).digest("hex"));
}
const listed = new Map(manifest.files.map((f) => [f.path, f.sha256]));
for (const [path, hash] of listed) {
  if (!current.has(path)) fail(`missing file: ${path}`);
  else if (current.get(path) !== hash) fail(`hash drift: ${path}`);
}
for (const path of current.keys()) {
  if (!listed.has(path)) fail(`unlisted file: ${path}`);
}
const aggregate = createHash("sha256")
  .update([...current.entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([path, hash]) => `${hash}  ${path}`).join("\n") + "\n")
  .digest("hex");
if (aggregate === manifest.aggregate_sha256) {
  pass(`aggregate tree hash matches (${manifest.file_count} files)`);
} else {
  fail(`aggregate drift: computed ${aggregate}, manifest ${manifest.aggregate_sha256}`);
}

const stateHits = [...current.keys()].filter((rel) =>
  /\.(sqlite3?|db)$/i.test(rel) || /^(state|sessions|data)\//.test(rel));
if (stateHits.length === 0) pass("no state files inside the skill folder");
else fail(`state files present: ${stateHits.join(", ")}`);

const archiveErrors = checkArchiveContract(root, manifest, distribution);
for (const error of archiveErrors) fail(error);
if (archiveErrors.length === 0) pass(distribution
  ? "explicit extracted distribution has no self-nested archive"
  : "source archive SHA-256 matches the source manifest");

// --- entry point (installer truth): the actual executable, hash + load ---
// A package is never 'ready' from SKILL.md or source presence: the entry
// point must exist, match the recorded build byte for byte, and load.
// A missing, stale or broken build fails visibly with an actionable error.
const gate = checkEntryPoint(root, manifest);
if (gate.ok) {
  pass(`entry point verified: ${gate.entry.path} sha256 ${gate.entry.sha256} (hash + load)`);
} else {
  for (const problem of gate.problems) fail(problem);
}

console.log(failures === 0 ? "VERIFY: PASS" : `VERIFY: FAIL (${failures})`);
process.exit(failures === 0 ? 0 : 1);
