// Selected-tree gate (verify-what-the-resolver-selects): the updater must
// verify the copy the runtime resolver actually selects, never declare
// success for having written an unused directory. One runnable check for
// scripts/selected-tree-gate.mjs — focused regression set (a)-(e).
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
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

// A council skill copy: version + SKILL.md + manifest.json + advisors/,
// with a packaged executable when `entry` is true (and an entry recorded but
// absent when entry is "recorded-only").
function makeCopy(dir, { version = "1.0.51", contract = CURRENT_CONTRACT, entry = true } = {}) {
  mkdirSync(join(dir, "advisors"), { recursive: true });
  mkdirSync(join(dir, "runtime", "dist"), { recursive: true });
  writeFileSync(join(dir, "version"), `${version}\n`);
  writeFileSync(join(dir, "SKILL.md"), `---\nname: council-of-wise-elders\n---\n\n${contract}\n`);
  const manifest = {};
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
  const gate = checkSelectedTree({ home, skillDir: wired, load: false });
  assert.equal(gate.ok, true, gate.problems.join(" | "));
  const warnings = gate.warnings.join("\n");
  assert.match(warnings, new RegExp(`DUPLICATE council-of-wise-elders at ${dup.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  assert.match(warnings, /NOT what the resolver selects/);
  assert.match(warnings, /STALE-CONTRACT-TEXT/);
  assert.match(warnings, /CONFLICT: .* is at version 1\.0\.24/);
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
  const gate = checkSelectedTree({ home, skillDir: wired, prefix: join(home, "p1"), load: false });
  assert.ok(gate.selected, gate.problems.join(" | "));
  assert.match(gate.selected.path, /\.claude[\\/]skills[\\/]council-of-wise-elders$/);
  assert.match(gate.warnings.join("\n"), /the resolver selects .* while this update maintains/);
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
});
