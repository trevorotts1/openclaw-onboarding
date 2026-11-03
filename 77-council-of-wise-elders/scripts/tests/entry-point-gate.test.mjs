// Entry-point gate (installer truth rule): the verifier must check the
// ACTUAL executable (byte hash + load) and fail visibly on a failed or
// missing build — never 'ready' from source presence, never a silent
// old-bundle reuse. One runnable check for scripts/entry-point-gate.mjs.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { ARCHIVE_FILE, checkEntryPoint, ENTRY_PATH } from "../entry-point-gate.mjs";

const GOOD_ENTRY = "#!/usr/bin/env node\nif (process.argv.includes('--help')) process.exit(0);\nprocess.exit(2);\n";

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "cwe-entry-gate-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, "runtime", "dist"), { recursive: true });
  const abs = join(root, ENTRY_PATH);
  writeFileSync(abs, GOOD_ENTRY);
  const bytes = Buffer.byteLength(GOOD_ENTRY);
  const manifest = {
    runtime_entry: {
      path: ENTRY_PATH,
      sha256: createHash("sha256").update(GOOD_ENTRY).digest("hex"),
      bytes,
    },
  };
  return { root, abs, manifest };
}

test("recorded, unmodified, loadable entry point passes (hash + load)", (t) => {
  const { root, manifest } = fixture(t);
  const gate = checkEntryPoint(root, manifest);
  assert.equal(gate.ok, true, gate.problems.join(" | "));
});

test("a stale entry point fails loudly and never reuses the old bundle", (t) => {
  const { root, abs, manifest } = fixture(t);
  writeFileSync(abs, GOOD_ENTRY + "// old bundle left behind\n");
  const gate = checkEntryPoint(root, manifest);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /stale entry point/);
});

test("a missing build is visibly incomplete with an actionable error", (t) => {
  const { root, abs, manifest } = fixture(t);
  rmSync(abs);
  const gate = checkEntryPoint(root, manifest);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /entry point missing/);
  assert.match(gate.problems.join("\n"), /npm ci --no-audit --no-fund && npm run build/);
});

test("source presence alone is never ready: no recorded entry fails", (t) => {
  const { root } = fixture(t);
  const gate = checkEntryPoint(root, {});
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /records no runtime entry/);
});

test("an entry point that cannot load fails the gate", (t) => {
  const { root, abs, manifest } = fixture(t);
  writeFileSync(abs, "const = broken syntax;\n");
  manifest.runtime_entry.sha256 = createHash("sha256").update("const = broken syntax;\n").digest("hex");
  manifest.runtime_entry.bytes = Buffer.byteLength("const = broken syntax;\n");
  const gate = checkEntryPoint(root, manifest);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /failed node --check/);
});

// --- the package's own archive -------------------------------------------
// A source tree carries no runtime/dist (runtime/.gitignore generates it and
// never commits it), but the package DOES ship the executable inside its
// distributable archive. That member is the entry only when its sha256 and byte
// length are exactly the recorded runtime_entry.

/** Build a source tree with an archive holding `memberBytes` (or nothing). */
function archiveFixture(t, { memberBytes = GOOD_ENTRY } = {}) {
  const zip = spawnSync("zip", ["-v"], { encoding: "utf8" });
  if (zip.status !== 0) {
    t.skip("zip not available");
    return null;
  }
  const root = mkdtempSync(join(tmpdir(), "cwe-entry-archive-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const staging = join(root, "staging");
  const member = join(staging, "council-of-wise-elders", dirname(ENTRY_PATH));
  mkdirSync(member, { recursive: true });
  writeFileSync(join(staging, "council-of-wise-elders", "SKILL.md"), "---\nname: council-of-wise-elders\n---\n");
  if (memberBytes !== null) writeFileSync(join(member, "blackceo-council.mjs"), memberBytes);
  const built = spawnSync("zip", ["-q", "-r", "-X", join(root, ARCHIVE_FILE), "council-of-wise-elders"], {
    cwd: staging,
    encoding: "utf8",
  });
  if (built.status !== 0) {
    t.skip(`zip failed: ${built.stderr ?? ""}`);
    return null;
  }
  const manifest = {
    runtime_entry: {
      path: ENTRY_PATH,
      sha256: createHash("sha256").update(GOOD_ENTRY).digest("hex"),
      bytes: Buffer.byteLength(GOOD_ENTRY),
    },
  };
  return { root, manifest };
}

test("a source tree with no runtime/dist verifies its entry from the archive", (t) => {
  const fixtureRoot = archiveFixture(t);
  if (!fixtureRoot) return;
  const gate = checkEntryPoint(fixtureRoot.root, fixtureRoot.manifest);
  assert.equal(gate.ok, true, gate.problems.join(" | "));
  assert.equal(gate.fromArchive, true);
  assert.equal(gate.entry.sha256, fixtureRoot.manifest.runtime_entry.sha256);
});

test("an archive carrying another build is not this release's executable", (t) => {
  const fixtureRoot = archiveFixture(t, { memberBytes: `${GOOD_ENTRY}// another build\n` });
  if (!fixtureRoot) return;
  const gate = checkEntryPoint(fixtureRoot.root, fixtureRoot.manifest);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /carries another build is not this release's executable/);
});

test("an archive without the entry member is a missing executable", (t) => {
  const fixtureRoot = archiveFixture(t, { memberBytes: null });
  if (!fixtureRoot) return;
  const gate = checkEntryPoint(fixtureRoot.root, fixtureRoot.manifest);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /carries no council-of-wise-elders\/runtime\/dist\/blackceo-council\.mjs/);
});

test("a present but stale on-disk entry is never replaced by the archive", (t) => {
  const fixtureRoot = archiveFixture(t);
  if (!fixtureRoot) return;
  mkdirSync(join(fixtureRoot.root, dirname(ENTRY_PATH)), { recursive: true });
  writeFileSync(join(fixtureRoot.root, ENTRY_PATH), `${GOOD_ENTRY}// stale source build\n`);
  const gate = checkEntryPoint(fixtureRoot.root, fixtureRoot.manifest);
  assert.equal(gate.ok, false);
  assert.match(gate.problems.join("\n"), /stale entry point/);
  assert.equal(gate.fromArchive, false);
});
