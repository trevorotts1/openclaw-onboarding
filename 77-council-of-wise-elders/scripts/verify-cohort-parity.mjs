#!/usr/bin/env node
// WER-025 dependency-ready slice: cohort-parity detector (read-only).
//
// Detects a mixed/partial release cohort BEFORE admission:
//   1. the three version markers (skill-version.txt, SKILL.md frontmatter,
//      sibling `version`) must agree, and the CHANGELOG top entry must not
//      describe a newer or older cohort (see --strict-changelog);
//   2. manifest.json's recorded aggregate must equal the tree hash that
//      scripts/build-bundles.mjs computes, using the same walk, the same
//      per-file SHA-256 and the same "<sha256>  <path>" aggregate;
//   3. skill content changed under the skill folder while skill-version.txt
//      stayed put (the G3 condition) is reported as such, separately from a
//      version move whose manifest was never rebuilt.
//
// The verifier only reads. It makes no network/provider calls and writes no
// file, so it is idempotent and safe to run before admission or in CI.
//
// Usage: node verify-cohort-parity.mjs [--root <skill-folder>] [--strict-changelog]
// Exit codes: 0 = coherent cohort, 1 = detected drift, 2 = bad invocation.
//
// The two files owned by this WER-025 slice are new and their manifest rebuild
// is explicitly deferred by the unit scope (editing manifest.json is out of
// scope). While they are ABSENT from manifest.files they are exempted from the
// hash comparison by exact path and reported as a WARN; the moment a rebuilt
// manifest records them they are compared like any other file, and every other
// added/changed/removed path is still detected.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DETECTOR_PATHS = new Set([
  "scripts/verify-cohort-parity.mjs",
  "scripts/tests/verify-cohort-parity.test.mjs",
]);

const args = process.argv.slice(2);
const rootIdx = args.indexOf("--root");
if (rootIdx >= 0 && !args[rootIdx + 1]) {
  console.log("FAIL --root requires a directory");
  process.exit(2);
}
const root = rootIdx >= 0
  ? resolve(args[rootIdx + 1])
  : resolve(dirname(fileURLToPath(import.meta.url)), "..");
const strictChangelog = args.includes("--strict-changelog");

const failures = [];
const warnings = [];
const fail = (m) => failures.push(m);
const warn = (m) => warnings.push(m);
const norm = (v) => (v ?? "").trim().replace(/^v/, "");

function readText(rel) {
  const path = join(root, rel);
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function semver(v) {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v);
  return m ? m.slice(1).map(Number) : null;
}

function compareVersions(a, b) {
  const av = semver(a);
  const bv = semver(b);
  if (!av || !bv) return null;
  for (let i = 0; i < 3; i += 1) {
    if (av[i] !== bv[i]) return av[i] < bv[i] ? -1 : 1;
  }
  return 0;
}

// Same exclusions as scripts/build-bundles.mjs (including the root-level
// .wired-<version> sentinels that update-skills.sh writes during a roll).
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
    else out.push({ path: rel, file: p });
  }
  return out;
}

function aggregateOf(pairs) {
  return sha256(pairs.map((f) => `${f.sha256}  ${f.path}`).join("\n") + "\n");
}

console.log(`Cohort parity: root = ${root}`);

// 1. Version markers.
const skillVersionRaw = readText("skill-version.txt");
const versionRaw = readText("version");
const skillMd = readText("SKILL.md");
const frontmatter = skillMd?.match(/^---\n([\s\S]*?)\n---/);
const frontmatterVersion = frontmatter?.[1].match(/^version:\s*(\S+)\s*$/m)?.[1];
const markerValues = {
  "skill-version.txt": norm(skillVersionRaw),
  "SKILL.md frontmatter": norm(frontmatterVersion),
  version: norm(versionRaw),
};
const canonical = markerValues["skill-version.txt"]
  || markerValues["SKILL.md frontmatter"]
  || markerValues.version;

if (!canonical) {
  fail('version markers missing: skill-version.txt, SKILL.md frontmatter and version all lack a version; expected e.g. "1.0.10"');
} else {
  const seen = [];
  for (const [name, value] of Object.entries(markerValues)) {
    if (!value) {
      fail(`version marker missing: ${name} has no version, expected "${canonical}" from skill-version.txt`);
    } else if (value !== canonical) {
      seen.push({ name, value });
    }
  }
  if (seen.length === 0) {
    console.log(`PASS version markers agree: ${canonical}`);
  } else {
    const details = Object.entries(markerValues)
      .map(([name, value]) => `${name}="${value || "(missing)"}"`)
      .join(" ");
    const names = seen.map((s) => `${s.name}="${s.value}"`).join(", ");
    fail(`version marker drift: ${names}, expected "${canonical}" from skill-version.txt (${details})`);
  }
}

// 2. CHANGELOG top entry.
const changelog = readText("CHANGELOG.md");
const topEntry = changelog?.match(/^##\s+[^\n]*?v?(\d+\.\d+\.\d+)\b/m)?.[1];
if (!changelog) {
  fail('CHANGELOG.md missing, expected a top entry for "' + (canonical || "(version markers)") + '"');
} else if (!topEntry) {
  fail(`CHANGELOG.md has no versioned "## " entry, expected a top entry for "${canonical || "(version markers)"}"`);
} else if (canonical) {
  const order = compareVersions(topEntry, canonical);
  if (order === null) {
    fail(`CHANGELOG.md top entry "${topEntry}" is not semver, expected "${canonical}" from version markers`);
  } else if (order > 0) {
    fail(`CHANGELOG.md top entry = "${topEntry}", expected "${canonical}" from version markers (changelog describes a newer cohort)`);
  } else if (order < 0) {
    const message = `CHANGELOG.md top entry = "${topEntry}", expected "${canonical}" from version markers (no changelog entry for the current version yet)`;
    if (strictChangelog) fail(message);
    else warn(`${message}; run with --strict-changelog to make this fatal`);
  } else {
    console.log(`PASS CHANGELOG.md top entry matches: ${canonical}`);
  }
}

// 3. Manifest agreement.
const manifestRaw = readText("manifest.json");
let manifest = null;
if (!manifestRaw) {
  fail('manifest.json missing, expected a generated manifest from scripts/build-bundles.mjs');
} else {
  try {
    manifest = JSON.parse(manifestRaw);
  } catch (e) {
    fail(`manifest.json is not valid JSON: ${e.message}`);
  }
}

let exempt = new Set();
if (manifest) {
  if (canonical && norm(manifest.skill_version) !== canonical) {
    fail(`manifest.json skill_version = "${manifest.skill_version ?? "(missing)"}", expected "${canonical}" from skill-version.txt (rebuild with scripts/build-bundles.mjs)`);
  }
  const recorded = Array.isArray(manifest.files) ? manifest.files : null;
  if (!recorded) {
    fail('manifest.json has no "files" array, expected the generated per-file list');
  } else {
    const shapeOk = recorded.every((f) => typeof f?.path === "string" && typeof f?.sha256 === "string");
    if (!shapeOk) {
      fail('manifest.json "files" entries are malformed, expected {path, sha256, bytes} for every file');
    } else {
      const recordedPairs = recorded
        .map((f) => ({ path: f.path, sha256: f.sha256 }))
        .sort((a, b) => (a.path < b.path ? -1 : 1));
      const recordedAggregate = aggregateOf(recordedPairs);
      if (typeof manifest.aggregate_sha256 !== "string" || recordedAggregate !== manifest.aggregate_sha256) {
        fail(`manifest.json is internally inconsistent: aggregate_sha256 = "${manifest.aggregate_sha256 ?? "(missing)"}", expected "${recordedAggregate}" over its own files list`);
      }
      if (manifest.file_count !== recorded.length) {
        fail(`manifest.json file_count = ${manifest.file_count ?? "(missing)"}, expected ${recorded.length} from its own files list`);
      }

      const manifestMap = new Map(recorded.map((f) => [f.path, f.sha256]));
      const disk = walk(root)
        .filter(({ path }) => path !== "manifest.json" && !path.endsWith(".skill"))
        .map(({ path, file }) => ({ path, sha256: sha256(readFileSync(file)) }))
        .sort((a, b) => (a.path < b.path ? -1 : 1));
      const diskMap = new Map(disk.map((f) => [f.path, f.sha256]));

      exempt = new Set(disk
        .map((f) => f.path)
        .filter((path) => DETECTOR_PATHS.has(path) && !manifestMap.has(path)));
      const scope = disk.filter((f) => !exempt.has(f.path));

      const changed = scope.filter((f) => manifestMap.has(f.path) && manifestMap.get(f.path) !== f.sha256).map((f) => f.path);
      const added = scope.filter((f) => !manifestMap.has(f.path)).map((f) => f.path);
      const removed = recorded.map((f) => f.path).filter((path) => !diskMap.has(path));
      const diffs = [...changed, ...added, ...removed].sort();
      const computedAggregate = aggregateOf(scope);
      const aggregateMatches = computedAggregate === manifest.aggregate_sha256
        && scope.length === manifest.file_count;

      if (exempt.size > 0) {
        warn(`detector files not yet recorded in manifest.json (manifest rebuild deferred for this WER-025 slice): ${[...exempt].sort().join(", ")}`);
      }

      if (aggregateMatches && diffs.length === 0) {
        console.log(`PASS manifest tree hash matches (${scope.length} files)`);
      } else {
        const list = diffs.length > 0 ? diffs.join(", ") : "(file list agrees; aggregate only)";
        const versionMoved = canonical
          && norm(manifest.skill_version)
          && norm(manifest.skill_version) !== canonical;
        if (versionMoved) {
          fail(`manifest drift: computed aggregate ${computedAggregate} over ${scope.length} files, manifest.json records ${manifest.aggregate_sha256} over ${manifest.file_count}; changed files: ${list}. Rebuild with scripts/build-bundles.mjs after the ${canonical} version bump and commit the regenerated manifest.json.`);
        } else {
          fail(`skill content changed without moving skill-version.txt: ${list}; skill-version.txt is still "${canonical}", expected a version bump (skill-version.txt, SKILL.md frontmatter and version) plus a rebuilt manifest.json (computed aggregate ${computedAggregate} over ${scope.length} files, manifest.json records ${manifest.aggregate_sha256} over ${manifest.file_count}).`);
        }
      }
    }
  }
}

for (const message of warnings) console.log(`WARN ${message}`);
for (const message of failures) console.log(`FAIL ${message}`);
console.log(failures.length === 0
  ? "COHORT PARITY: PASS"
  : `COHORT PARITY: FAIL (${failures.length} failing check(s))`);
process.exit(failures.length === 0 ? 0 : 1);
