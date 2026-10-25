// Selected-tree gate (verify-what-the-resolver-selects): the updater must
// verify the copy the runtime resolver actually selects, never declare
// success for having written an unused directory. One runnable check for
// scripts/selected-tree-gate.mjs — focused regression set (a)-(e).
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, chmodSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  CURRENT_CONTRACT_MARKER,
  STALE_CONTRACT_PHRASES,
  checkSelectedTree,
} from "../selected-tree-gate.mjs";
import { ENTRY_PATH } from "../entry-point-gate.mjs";
import { DISTRIBUTION_KINDS, HASH_METHOD, manifestEntries, treeAggregate } from "../manifest-tree.mjs";

const GOOD_ENTRY = "#!/usr/bin/env node\nif (process.argv.includes('--help')) process.exit(0);\nprocess.exit(2);\n";
const CURRENT_CONTRACT =
  "4b. Convene with `blackceo-council convene --brief FILE`. Convening is the approval: " +
  "the client chose the model and pays for it, so there is no grant to resolve and no approval step " +
  "to run or wait for. Do not improvise a parallel council.";
const STALE_CONTRACT =
  "Before execution: Resolve a real purpose-bound run grant through the installed authorization service.";

function fixtureHome(t) {
  const home = mkdtempSync(join(tmpdir(), "cwe-selected-tree-"));
  t.after(() => rmSync(home, { recursive: true, force: true }));
  return home;
}

// A council skill copy: every version carrier + SKILL.md + manifest.json +
// advisors/, with a packaged executable when `entry` is true (and an entry
// recorded but absent when entry is "recorded-only"). Carrier overrides exist
// so a disagreement can be exercised explicitly.
function makeCopy(
  dir,
  {
    version = "1.0.51",
    contract = CURRENT_CONTRACT,
    entry = true,
    skillVersion = version,
    frontmatterVersion = version,
    manifestVersion = null,
  } = {},
) {
  mkdirSync(join(dir, "advisors"), { recursive: true });
  mkdirSync(join(dir, "runtime", "dist"), { recursive: true });
  writeFileSync(join(dir, "version"), `${version}\n`);
  writeFileSync(join(dir, "skill-version.txt"), `v${skillVersion}\n`);
  writeFileSync(
    join(dir, "SKILL.md"),
    `---\nname: council-of-wise-elders\nversion: ${frontmatterVersion}\n---\n\n${contract}\n`,
  );
  const manifest = {};
  if (manifestVersion) manifest.skill_version = manifestVersion;
  if (entry) {
    writeFileSync(join(dir, ENTRY_PATH), GOOD_ENTRY);
    manifest.runtime_entry = {
      path: ENTRY_PATH,
      sha256: createHash("sha256").update(GOOD_ENTRY).digest("hex"),
      bytes: Buffer.byteLength(GOOD_ENTRY),
    };
    if (entry === "recorded-only") rmSync(join(dir, ENTRY_PATH));
  }
  writeFileSync(join(dir, "manifest.json"), JSON.stringify(manifest, null, 2));
  return dir;
}

// A prefix whose install-record names `skillDir`, with a real installed
// release entry beside it (the fleet install shape).
function makePrefix(home, skillDir, { name = "p1" } = {}) {
  const prefix = join(home, name);
  const release = join(prefix, "releases", "r1");
  mkdirSync(join(release, "dist"), { recursive: true });
  writeFileSync(join(release, "dist", "blackceo-council.mjs"), GOOD_ENTRY);
  writeFileSync(join(prefix, "active.json"), JSON.stringify({ releasePath: release }));
  mkdirSync(join(prefix, "releases"), { recursive: true });
  writeFileSync(join(prefix, "releases", "install-record.json"), JSON.stringify({ skill_dir: skillDir }));
  return prefix;
}

test("(c) an update that only touched an unused directory cannot report success", (t) => {
  const home = fixtureHome(t);
  const selected = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { version: "1.0.24", entry: false });
  const wired = makeCopy(join(home, "wired", "council-of-wise-elders"), { version: "1.0.51" });
  const prefix = makePrefix(home, selected); // the resolver selects the 1.0.24 tree
  const gate = checkSelectedTree({ home, skillDir: wired, prefix, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /updating only an unused directory/);
  assert.match(gate.problems.join("\n"), /1\.0\.24/);
});

test("(a) the maintained copy is the resolver-selected copy: healthy pass", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: true });
  assert.equal(gate.ok, true, gate.problems.join(" | "));
  assert.equal(gate.selectedPath, gate.selected.physical);
});

test("(e) stale grant instruction text in the SELECTED tree fails the upgrade", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), {
    contract: STALE_CONTRACT,
    entry: false,
  });
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /stale instruction text in the SELECTED copy/);
  assert.match(gate.problems.join("\n"), /Resolve a real purpose-bound run grant/);
});

test("(e) a SELECTED tree without the current convene contract fails", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), {
    contract: "We convene whenever convenient.",
    entry: false,
  });
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /does not carry the current convene contract/);
});

test("(d) a source-only SELECTED artifact (no executable) fails", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: false });
  const gate = checkSelectedTree({ home, skillDir: wired, load: false }); // no record: fallback walk selects it
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /source-only artifact/);
});

test("(d) a recorded runtime_entry that is shipped nowhere fails (packaging lie)", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: "recorded-only" });
  const gate = checkSelectedTree({ home, skillDir: wired, load: false }); // no record, no archive
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /records runtime_entry/);
});

test("(d) an installed release naming the tree satisfies the shipped-executable rule", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: "recorded-only" });
  const prefix = makePrefix(home, wired); // the fleet shape: entry lives in the installed release
  const gate = checkSelectedTree({ home, skillDir: wired, prefix, load: false });
  assert.equal(gate.ok, true, gate.problems.join(" | "));
});

test("(b) competing copies are detected and reported loudly, never equated", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  const dup = makeCopy(join(home, ".agents", "skills", "council-of-wise-elders"), {
    version: "1.0.24",
    contract: STALE_CONTRACT,
    entry: false,
  });
  makePrefix(home, wired);
  // Agent-resolver evidence names the wired tree: only now may the duplicate be
  // treated as unused. Without it the same fixture must not pass.
  const gate = checkSelectedTree({ home, skillDir: wired, load: false, agentSelected: wired, agentSource: "openclaw resolver test" });
  assert.equal(gate.ok, true, gate.problems.join(" | "));
  const warnings = gate.warnings.join("\n");
  assert.match(warnings, new RegExp(`DUPLICATE council-of-wise-elders at ${dup.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  assert.match(warnings, /NOT what the resolver selects/);
  assert.match(warnings, /STALE-CONTRACT-TEXT/);
  assert.match(warnings, /CONFLICT: .* is at version 1\.0\.24/);
});

test("(b) a duplicate with no agent-resolver evidence is UNPROVEN, never a pass", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  makeCopy(join(home, ".agents", "skills", "council-of-wise-elders"), {
    version: "1.0.24",
    contract: STALE_CONTRACT,
    entry: false,
  });
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.equal(gate.selectionProven, false);
  assert.match(gate.problems.join("\n"), /agent selection unproven/);
});

test("(c) the record the LIVE executable consults wins over the updater's prefix", (t) => {
  const home = fixtureHome(t);
  const live = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { version: "1.0.51", entry: false });
  const wired = makeCopy(join(home, "wired", "council-of-wise-elders"), { version: "1.0.52" });
  // 999-shape shim: variable entry path through the data profile's `current`.
  const profileRoot = join(home, "wise");
  const agg = join(profileRoot, "runtime", "agg1");
  mkdirSync(join(agg, "runtime", "dist"), { recursive: true });
  writeFileSync(join(agg, "run-council.mjs"), GOOD_ENTRY);
  mkdirSync(join(profileRoot, "runtime"), { recursive: true });
  symlinkSync(agg, join(profileRoot, "runtime", "current"));
  writeFileSync(join(agg, "install-record.json"), JSON.stringify({ skill_dir: live }));
  const bin = join(home, ".local", "bin");
  mkdirSync(bin, { recursive: true });
  writeFileSync(join(bin, "blackceo-council.profile"), `${profileRoot}\n`);
  writeFileSync(
    join(bin, "blackceo-council"),
    `#!/bin/bash\nENTRY="$PROFILE_ROOT/runtime/current/run-council.mjs"\nexec "$NODE_BIN" "$ENTRY" "$@"\n`,
  );
  makePrefix(home, wired); // the updater's own prefix names the wired tree
  const gate = checkSelectedTree({
    home,
    skillDir: wired,
    prefix: join(home, "p1"),
    load: false,
    agentSelected: live,
    agentSource: "blackceo-council.profile shim",
  });
  assert.ok(gate.selected, gate.problems.join(" | "));
  assert.match(gate.selected.path, /\.claude[\\/]skills[\\/]council-of-wise-elders$/);
  assert.match(gate.warnings.join("\n"), /the resolver selects .* while this update maintains/);
  // The updater maintains 1.0.52 while the agent reads 1.0.51: that is a real
  // failure, not a warning-only condition.
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /updating only an unused directory/);
});

test("(a) version carriers that disagree fail; the reader never prefers one file", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), {
    version: "1.0.52",
    skillVersion: "1.0.53",
  });
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  const problems = gate.problems.join("\n");
  assert.match(problems, /version carriers disagree/);
  assert.match(problems, /versionFile=1\.0\.52/);
  assert.match(problems, /skillVersionFile=1\.0\.53/);
});

test("(a) a manifest skill_version that disagrees is part of the same failure", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), {
    version: "1.0.53",
    manifestVersion: "1.0.52",
  });
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /manifestSkillVersion=1\.0\.52/);
});

test("(d) an archive that merely exists is not a valid artifact", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: "recorded-only" });
  writeFileSync(join(wired, "council-of-wise-elders.skill"), "not a zip\n");
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /is not a zip archive/);
});

test("(d) an installed entry that is empty fails even though the path exists", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: "recorded-only" });
  const prefix = makePrefix(home, wired);
  writeFileSync(join(prefix, "releases", "r1", "dist", "blackceo-council.mjs"), "");
  const gate = checkSelectedTree({ home, skillDir: wired, prefix, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /is empty: an existing path is not a valid artifact/);
});

test("(d) an installed entry that is not JavaScript fails node --check", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: "recorded-only" });
  const prefix = makePrefix(home, wired);
  writeFileSync(join(prefix, "releases", "r1", "dist", "blackceo-council.mjs"), "#!/usr/bin/env node\nthis is not js (\n");
  const gate = checkSelectedTree({ home, skillDir: wired, prefix, load: true });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /fails node --check/);
});

test("(b) agent evidence that names a non-skill path fails closed", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  makePrefix(home, wired);
  mkdirSync(join(home, "not-a-skill"), { recursive: true });
  const gate = checkSelectedTree({ home, skillDir: wired, load: false, agentSelected: join(home, "not-a-skill") });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /agent selection evidence is unusable/);
});

test("(d) a packaged entry that is EMPTY with a self-consistent manifest is refused", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  const empty = "";
  writeFileSync(join(wired, ENTRY_PATH), empty);
  const manifest = JSON.parse(readFileSync(join(wired, "manifest.json"), "utf8"));
  manifest.runtime_entry.sha256 = createHash("sha256").update(empty).digest("hex");
  manifest.runtime_entry.bytes = 0;
  writeFileSync(join(wired, "manifest.json"), JSON.stringify(manifest, null, 2));
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: true });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /entry point is empty \(0 bytes\)/);
});

test("(d) a recorded entry that is a DIRECTORY is refused, not a crash", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  rmSync(join(wired, ENTRY_PATH));
  mkdirSync(join(wired, ENTRY_PATH), { recursive: true });
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /entry point is not a regular file/);
});

test("(d) an archive whose entry member is empty is refused", (t) => {
  const zip = spawnSync("zip", ["-v"], { encoding: "utf8" });
  if (zip.status !== 0) {
    t.skip("zip not available");
    return;
  }
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: "recorded-only" });
  const staging = join(home, "zip-staging");
  mkdirSync(join(staging, dirname(ENTRY_PATH)), { recursive: true });
  writeFileSync(join(staging, ENTRY_PATH), "");
  execFileSync("zip", ["-qr", join(wired, "council-of-wise-elders.skill"), "."], { cwd: staging });
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /archive member .*is empty/);
});

test("(b) agent evidence that contradicts the install-record is refused", (t) => {
  const home = fixtureHome(t);
  const selected = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  const claimed = makeCopy(join(home, ".agents", "skills", "council-of-wise-elders"));
  const prefix = makePrefix(home, selected); // the record names the .claude copy
  const gate = checkSelectedTree({ home, skillDir: selected, prefix, load: false, agentSelected: claimed });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /agent evidence names .* but the live install-record/);
});

test("(b) agent evidence outside every known root with no record is refused", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  const outside = makeCopy(join(home, "elsewhere", "council-of-wise-elders"), { entry: false });
  const gate = checkSelectedTree({ home, skillDir: wired, load: false, agentSelected: outside });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /not a council-of-wise-elders copy under any known agent root/);
});

test("(c) equal versions with different content is a failure, not a warning", (t) => {
  const home = fixtureHome(t);
  const selected = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  const wired = makeCopy(join(home, "wired", "council-of-wise-elders"));
  writeFileSync(join(wired, "EXAMPLES.md"), "a file the selected copy does not have\n");
  makePrefix(home, selected);
  const gate = checkSelectedTree({ home, skillDir: wired, load: false, agentSelected: selected });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /both claim .* but their trees differ/);
});

test("(d) an archive member that is valid JavaScript but not the recorded build is refused", (t) => {
  const zip = spawnSync("zip", ["-v"], { encoding: "utf8" });
  if (zip.status !== 0) {
    t.skip("zip not available");
    return;
  }
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: "recorded-only" });
  const staging = join(home, "zip-staging");
  mkdirSync(join(staging, dirname(ENTRY_PATH)), { recursive: true });
  writeFileSync(join(staging, ENTRY_PATH), "#!/usr/bin/env node\nconsole.log('planted');\n");
  execFileSync("zip", ["-qr", join(wired, "council-of-wise-elders.skill"), "."], { cwd: staging });
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /is not the recorded build/);
});

test("(d) an archive member that is a shell script is refused even without loading", (t) => {
  const zip = spawnSync("zip", ["-v"], { encoding: "utf8" });
  if (zip.status !== 0) {
    t.skip("zip not available");
    return;
  }
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"), { entry: "recorded-only" });
  const shell = "#!/bin/sh\necho not javascript\n";
  const manifest = JSON.parse(readFileSync(join(wired, "manifest.json"), "utf8"));
  manifest.runtime_entry.sha256 = createHash("sha256").update(shell).digest("hex");
  manifest.runtime_entry.bytes = Buffer.byteLength(shell);
  writeFileSync(join(wired, "manifest.json"), JSON.stringify(manifest, null, 2));
  const staging = join(home, "zip-staging");
  mkdirSync(join(staging, dirname(ENTRY_PATH)), { recursive: true });
  writeFileSync(join(staging, ENTRY_PATH), shell);
  execFileSync("zip", ["-qr", join(wired, "council-of-wise-elders.skill"), "."], { cwd: staging });
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /does not look like a JavaScript entry point/);
});

test("(a) a symlinked version carrier cannot borrow another tree's identity", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  writeFileSync(join(wired, "version"), "1.0.99\n");
  rmSync(join(wired, "skill-version.txt"));
  symlinkSync(join(wired, "version"), join(wired, "skill-version.txt"));
  makePrefix(home, wired);
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /version carrier skill-version\.txt is a symlink/);
});

test("(a) a symlinked selected tree is verified through its pinned target", (t) => {
  const home = fixtureHome(t);
  const real = makeCopy(join(home, "real", "council-of-wise-elders"));
  mkdirSync(join(home, ".claude", "skills"), { recursive: true });
  const link = join(home, ".claude", "skills", "council-of-wise-elders");
  symlinkSync(real, link);
  makePrefix(home, link);
  const gate = checkSelectedTree({ home, skillDir: real, load: false, agentSelected: link, agentSource: "symlink test" });
  assert.equal(gate.ok, true, gate.problems.join(" | "));
  assert.equal(gate.selected.physical, realpathSync(real));
});

test("(b) a relative skill_dir in a record is refused, never resolved against cwd", (t) => {
  const home = fixtureHome(t);
  const wired = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  const prefix = makePrefix(home, wired);
  writeFileSync(join(prefix, "releases", "install-record.json"), JSON.stringify({ skill_dir: "." }));
  const gate = checkSelectedTree({ home, skillDir: wired, prefix, load: false });
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /records a relative skill_dir/);
});

test("(e) the shipped SKILL.md carries the current convene contract, not grant text", () => {
  // Source-level guard: the canonical tree this unit ships must carry the
  // convene-is-approval contract so upgrades can never resurrect grant text.
  const skillMd = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "SKILL.md");
  const text = readFileSync(skillMd, "utf8").replace(/\s+/g, " ");
  assert.ok(text.includes(CURRENT_CONTRACT_MARKER), "canonical SKILL.md lost the convene-is-approval contract");
  for (const phrase of STALE_CONTRACT_PHRASES) {
    assert.ok(!text.includes(phrase), `canonical SKILL.md carries stale grant text: ${phrase}`);
  }
  // Route resolution is caller-first: the runtime's routes are never offered
  // as if they were the calling agent's models (the OpenClaw mis-presentation).
  assert.ok(
    text.includes("they are NOT the calling agent's models"),
    "canonical SKILL.md no longer states that runtime routes are not the caller's models",
  );
  assert.ok(
    text.includes("None of those is your agent's model"),
    "canonical SKILL.md lost the no-matching-route refusal sentence",
  );
  assert.ok(
    !text.includes("the claude-nine configured default on claude-nine, Sonnet on Claude Code"),
    "canonical SKILL.md reintroduced the hardcoded harness menu",
  );
});

// ---------------------------------------------------------------------------
// Same-release proof: the 999 distribution of the canonical release this update
// maintains differs BY DESIGN. It must pass — and only on a proof whose witness
// is the release's own manifest, never the distribution's claims about itself.
// Every other mismatch still fails with the same message as before.
// ---------------------------------------------------------------------------

/** Rewrite manifest.json so it records the tree exactly as it is now. */
function manifestTree(dir, extra = {}) {
  const manifestPath = join(dir, "manifest.json");
  const base = JSON.parse(readFileSync(manifestPath, "utf8"));
  const { entries, aggregate } = treeAggregate(dir);
  const manifest = {
    ...base,
    ...extra,
    file_count: entries.length,
    aggregate_sha256: aggregate,
    hash_method: extra.hash_method ?? HASH_METHOD,
    files: entries,
  };
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  return manifest;
}

/**
 * The distribution contract the canonical release declares IN ADVANCE:
 * scripts/build-bundles.mjs computes it from its own post-strip staging tree,
 * so it describes what the release will accept, not what a vendor claims.
 */
function distributionWitness(distDir) {
  return {
    kinds: [...DISTRIBUTION_KINDS],
    files: manifestEntries(distDir),
    runtime_dist: manifestEntries(distDir, { includeRuntimeDist: true })
      .filter((f) => f.path.startsWith("runtime/dist/")),
    added_paths: ["DISTRIBUTION-RECONCILIATION.json"],
  };
}

function reconciliation(canonicalManifest, { scrubbed = [], aggregate = null, kinds = null } = {}) {
  const differences = [];
  if (kinds === null || kinds.includes("private_scope_items_dropped")) {
    differences.push({
      kind: "private_scope_items_dropped",
      rule: "private_scope items never enter a distributable artifact",
      items: scrubbed.map((file, i) => ({ file, item_index: i, item_sha256: "0".repeat(64) })),
    });
  }
  if (kinds === null || kinds.includes("file_added")) differences.push({ kind: "file_added", file: "DISTRIBUTION-RECONCILIATION.json" });
  if (kinds === null || kinds.includes("manifest_regenerated")) differences.push({ kind: "manifest_regenerated", file: "manifest.json" });
  return {
    artifact: "council-of-wise-elders 999 distribution reconciliation",
    generated_by: "scripts/vendor-council-bundle.mjs (test fixture)",
    canonical_source: {
      canonical_aggregate_sha256: aggregate ?? canonicalManifest.aggregate_sha256,
      canonical_file_count: canonicalManifest.file_count,
      skill_version: canonicalManifest.skill_version,
    },
    intentional_distribution_differences: differences,
  };
}

function writeReconciliation(distDir, record) {
  writeFileSync(join(distDir, "DISTRIBUTION-RECONCILIATION.json"), JSON.stringify(record, null, 2));
}

/** Restamp the distribution manifest, dropping the inherited witness block. */
function restampDistribution(distDir, extra = {}) {
  const manifest = manifestTree(distDir, extra);
  delete manifest.distribution;
  writeFileSync(join(distDir, "manifest.json"), JSON.stringify(manifest, null, 2));
  return manifest;
}

/**
 * A canonical release tree plus its 999 distribution: one scrubbed file, the
 * built runtime, the reconciliation record, a regenerated manifest naming the
 * canonical aggregate.
 */
function distributionFixture(t) {
  const home = fixtureHome(t);
  const canonical = join(home, "wired", "council-of-wise-elders");
  const dist = join(home, ".agents", "skills", "council-of-wise-elders");
  makeCopy(canonical, { version: "1.0.58" });
  writeFileSync(join(canonical, "advisors", "pack.json"), '{"items":[1,2,3]}\n');
  writeFileSync(join(canonical, "runtime", "dist", "vendored-bundle.mjs"), "export const vendored = true;\n");
  manifestTree(canonical);
  const canonicalManifest = JSON.parse(readFileSync(join(canonical, "manifest.json"), "utf8"));

  cpSync(canonical, dist, { recursive: true });
  writeFileSync(join(dist, "advisors", "pack.json"), '{"items":[1,2]}\n');
  // The release declares what its distribution may look like before it exists.
  manifestTree(canonical, { distribution: distributionWitness(dist) });
  writeReconciliation(dist, reconciliation(canonicalManifest, { scrubbed: ["advisors/pack.json"] }));
  restampDistribution(dist, {
    canonical_aggregate_sha256: canonicalManifest.aggregate_sha256,
    canonical_file_count: canonicalManifest.file_count,
  });
  return { home, canonical, dist, canonicalManifest };
}

function runPair(home, canonical, dist) {
  return checkSelectedTree({
    home,
    skillDir: canonical,
    agentSelected: dist,
    agentSource: "distribution test",
    load: false,
  });
}

test("(same release) the 999 distribution of the maintained tree passes and says so", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, true, gate.problems.join(" | "));
  const warnings = gate.warnings.join("\n");
  assert.match(warnings, /SAME RELEASE: distribution .* is the 999 packaging of canonical aggregate/);
  assert.ok(warnings.includes(canonicalManifest.aggregate_sha256), "the proof must name the canonical aggregate");
  assert.match(warnings, /proven by manifest recomputation/);
  assert.match(warnings, /recorded files and \d+ built files matched/);
});

test("(same release) a distribution with an extra unmanifested non-dist file is refused", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  writeFileSync(join(dist, "EXAMPLES.md"), "a file the distribution manifest does not record\n");
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /but their trees differ/);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*is not the tree its own manifest records/);
});

test("(same release) a distribution file tampered against its own manifest is refused", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  writeFileSync(join(dist, "advisors", "pack.json"), '{"items":[1,2,3],"planted":true}\n');
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*recomputed [0-9a-f]{64} over \d+ files, manifest/);
});

test("(same release) a distribution of a DIFFERENT canonical aggregate is refused", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  const manifest = JSON.parse(readFileSync(join(dist, "manifest.json"), "utf8"));
  manifest.canonical_aggregate_sha256 = "0".repeat(64);
  writeFileSync(join(dist, "manifest.json"), JSON.stringify(manifest, null, 2));
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*packaging of DIFFERENT canonical releases/);
});

test("(same release) a distribution without its reconciliation record is refused", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  rmSync(join(dist, "DISTRIBUTION-RECONCILIATION.json"));
  restampDistribution(dist, { canonical_aggregate_sha256: canonicalManifest.aggregate_sha256 });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*carries no DISTRIBUTION-RECONCILIATION\.json/);
});

test("(same release) a maintained tree tampered against its own manifest is refused", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  writeFileSync(join(canonical, "advisors", "pack.json"), '{"items":[1,2,3],"edited-after-build":true}\n');
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: the maintained tree .*is not the tree its own manifest records/);
});

test("(same release) a distribution claiming another version is refused", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  writeFileSync(join(dist, "version"), "1.0.59\n");
  writeFileSync(join(dist, "skill-version.txt"), "v1.0.59\n");
  writeFileSync(
    join(dist, "SKILL.md"),
    readFileSync(join(dist, "SKILL.md"), "utf8").replace(/^version:\s*\S+$/m, "version: 1.0.59"),
  );
  restampDistribution(dist, {
    skill_version: "1.0.59",
    canonical_aggregate_sha256: canonicalManifest.aggregate_sha256,
  });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: versions differ \(selected 1\.0\.59 vs maintained 1\.0\.58\)/);
});

test("(same release) a plain mismatch is never dressed up as a distribution", (t) => {
  const home = fixtureHome(t);
  const selected = makeCopy(join(home, ".claude", "skills", "council-of-wise-elders"));
  const wired = makeCopy(join(home, "wired", "council-of-wise-elders"));
  writeFileSync(join(wired, "EXAMPLES.md"), "a file the selected copy does not have\n");
  const gate = checkSelectedTree({ home, skillDir: wired, agentSelected: selected, load: false });
  assert.equal(gate.ok, false);
  const problems = gate.problems.join("\n");
  assert.match(problems, /but their trees differ .*an update that wrote any other file must not report success/);
  assert.ok(!problems.includes("SAME-RELEASE PROOF REFUSED"), "a non-distribution must not get a proof line");
  assert.ok(!gate.warnings.join("\n").includes("SAME RELEASE"), "a non-distribution must not be accepted");
});

// --- reviewer bypasses: each one is refused, and says why -------------------

test("(bypass 1) an impostor tree cannot borrow the canonical aggregate", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  // Fresh content on every shared path, a self-consistent manifest, the real
  // canonical aggregate copied in, and a truthful-looking record: the shape of
  // the bypass that passed when the proof trusted the distribution's claims.
  writeFileSync(join(dist, "SKILL.md"), `---\nname: council-of-wise-elders\nversion: 1.0.58\n---\n\n${CURRENT_CONTRACT}\n`);
  writeFileSync(join(dist, "advisors", "impostor.mjs"), "export const impostor = true;\n");
  rmSync(join(dist, "advisors", "pack.json"));
  writeReconciliation(dist, reconciliation(canonicalManifest, { scrubbed: [] }));
  restampDistribution(dist, { canonical_aggregate_sha256: canonicalManifest.aggregate_sha256 });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: the selected copy .* does not carry the distribution the release records/);
});

test("(bypass 2) a regenerated manifest cannot smuggle an extra executable", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  writeFileSync(join(dist, "advisors", "evil-helper.mjs"), "export const pwned = true;\n");
  restampDistribution(dist, { canonical_aggregate_sha256: canonicalManifest.aggregate_sha256 });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*carries advisors\/evil-helper\.mjs, which the release neither records nor declares/);
});

test("(bypass 3) a modified runtime/dist payload is refused", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  // runtime/dist is excluded from every tree aggregate, so this leaves the
  // distribution's own manifest perfectly consistent — only the release's
  // recorded build can catch it.
  writeFileSync(join(dist, "runtime", "dist", "vendored-bundle.mjs"), 'export const vendored = "pwned";\n');
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*runtime\/dist\/vendored-bundle\.mjs.*a modified build is not the release's build/);
});

test("(bypass 4) a replaced entry point with a rewritten runtime_entry is refused", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  const payload = "#!/usr/bin/env node\nif (process.argv.includes('--help')) process.exit(0);\nrequire('fs').writeFileSync('/tmp/pwned','x');\n";
  writeFileSync(join(dist, ENTRY_PATH), payload);
  restampDistribution(dist, {
    canonical_aggregate_sha256: canonicalManifest.aggregate_sha256,
    runtime_entry: { path: ENTRY_PATH, sha256: createHash("sha256").update(payload).digest("hex"), bytes: Buffer.byteLength(payload) },
  });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*a modified build is not the release's build|does not ship the release's executable/);
});

test("(bypass 5) a reconciliation record that lies is refused", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  writeReconciliation(dist, {
    artifact: "council-of-wise-elders 999 distribution reconciliation",
    canonical_source: { canonical_aggregate_sha256: "f".repeat(64) },
    intentional_distribution_differences: [],
    note: "never parsed",
  });
  restampDistribution(dist, { canonical_aggregate_sha256: canonicalManifest.aggregate_sha256 });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: the reconciliation record .* names the canonical source f{64}/);
});

test("(bypass 6) a hash_method this gate cannot recompute is refused", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  restampDistribution(dist, {
    canonical_aggregate_sha256: canonicalManifest.aggregate_sha256,
    hash_method: "md5 over unsorted paths, files omitted",
  });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*records hash_method "md5 over unsorted paths, files omitted"/);
});

test("(bypass 7) a symlink cannot borrow content from outside the tree", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  writeFileSync(join(home, "outside.json"), '{"items":[1,2,3]}\n');
  rmSync(join(dist, "advisors", "pack.json"));
  symlinkSync(join(home, "outside.json"), join(dist, "advisors", "pack.json"));
  restampDistribution(dist, { canonical_aggregate_sha256: canonicalManifest.aggregate_sha256 });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*advisors\/pack\.json is a symlink/);
});

test("(bypass 8) an unverifiable archive cannot ride along", (t) => {
  const { home, canonical, dist, canonicalManifest } = distributionFixture(t);
  writeFileSync(join(dist, "council-of-wise-elders.skill"), "junk bytes, not the release's archive\n");
  restampDistribution(dist, { canonical_aggregate_sha256: canonicalManifest.aggregate_sha256 });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*carries the archive council-of-wise-elders\.skill .*an unverifiable archive/);
});

test("(regression) a roll sentinel carrying its own version is not a distribution difference", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  writeFileSync(join(dist, ".wired-1.0.58"), "1.0.58\n");
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, true, gate.problems.join(" | "));
});

test("(regression) a roll sentinel that does not carry its own version is refused", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  writeFileSync(join(dist, ".wired-1.0.58"), "planted payload\n");
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*carries \.wired-1\.0\.58, which is not a roll sentinel recording its own version/);
});

test("(regression) a dangling symlink is a clean FAIL with a summary line, never a crash", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  symlinkSync(join(home, "does-not-exist"), join(dist, "advisors", "broken-link"));
  const run = spawnSync(
    process.execPath,
    [join(dirname(fileURLToPath(import.meta.url)), "..", "selected-tree-gate.mjs"),
      "--home", home, "--skill-dir", canonical, "--agent-selected", dist, "--no-load"],
    { encoding: "utf8" },
  );
  assert.equal(run.status, 1, `expected exit 1, got ${run.status}\n${run.stderr}`);
  const out = `${run.stdout}${run.stderr}`;
  assert.match(out, /but their trees differ/);
  assert.match(out, /SAME-RELEASE PROOF REFUSED: .*broken-link is a symlink/);
  assert.match(out, /SELECTED-TREE: FAIL/);
  assert.ok(!/\n\s+at .*\.mjs:\d+/.test(out), `the gate must not dump a stack trace:\n${out}`);
});

test("(regression) an unreadable file is a clean FAIL, never a crash", (t) => {
  const { home, canonical, dist } = distributionFixture(t);
  const secret = join(dist, "advisors", "unreadable.json");
  writeFileSync(secret, "{}\n");
  chmodSync(secret, 0o000);
  t.after(() => { try { chmodSync(secret, 0o644); } catch { /* already gone */ } });
  const gate = runPair(home, canonical, dist);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*cannot be verified: .*unreadable|is not the tree its own manifest records/);
});
