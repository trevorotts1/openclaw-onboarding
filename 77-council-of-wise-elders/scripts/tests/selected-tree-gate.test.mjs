// Selected-tree gate (verify-what-the-resolver-selects): the updater must
// verify the copy the runtime resolver actually selects, never declare
// success for having written an unused directory. One runnable check for
// scripts/selected-tree-gate.mjs — focused regression set (a)-(e).
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
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
