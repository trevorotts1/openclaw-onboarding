// Entry-point gate (installer truth rule): the verifier must check the
// ACTUAL executable (byte hash + load) and fail visibly on a failed or
// missing build — never 'ready' from source presence, never a silent
// old-bundle reuse. One runnable check for scripts/entry-point-gate.mjs.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { checkEntryPoint, ENTRY_PATH } from "../entry-point-gate.mjs";

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
