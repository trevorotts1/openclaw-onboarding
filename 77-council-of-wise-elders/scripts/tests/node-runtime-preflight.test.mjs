import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  isSupportedCouncilRuntimeNode,
  verifyCouncilSqlite,
} from "../node-runtime-preflight.mjs";

const scriptsDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("runtime Node support rejects 18, 20 and 23; accepts 22.13+ and 24+", () => {
  for (const version of ["v18.20.8", "v20.19.0", "v22.12.0", "v23.10.0", "garbled"]) {
    assert.equal(isSupportedCouncilRuntimeNode(version), false, version);
  }
  for (const version of ["v22.13.0", "v22.16.0", "v24.0.0", "v25.2.0"]) {
    assert.equal(isSupportedCouncilRuntimeNode(version), true, version);
  }
});

test("supported running Node exposes a usable in-memory SQLite connection", async () => {
  if (!isSupportedCouncilRuntimeNode(process.version)) {
    // On Node 20 the installer must reject before trying node:sqlite.
    return;
  }
  await verifyCouncilSqlite();
});

test("--check-prereqs verifies the actual executing Node without installing", () => {
  const root = mkdtempSync(join(tmpdir(), "council-runtime-preflight-"));
  try {
    mkdirSync(join(root, "runtime"));
    writeFileSync(
      join(root, "runtime", "package.json"),
      JSON.stringify({ name: "fixture-council-runtime", version: "0.0.0", private: true }),
    );
    const run = spawnSync(
      process.execPath,
      [join(scriptsDir, "install-runtime.mjs"), "--root", root, "--check-prereqs"],
      { encoding: "utf8" },
    );
    if (isSupportedCouncilRuntimeNode(process.version)) {
      assert.equal(run.status, 0, run.stdout + run.stderr);
      assert.match(run.stdout, /in-memory SQLite read\/write/);
      assert.match(run.stdout, /RUNTIME-PREREQS: PASS/);
    } else {
      assert.equal(run.status, 1);
      assert.match(run.stdout, /requires Node\.js/);
    }
    assert.equal(existsSync(join(root, "runtime", "node_modules")), false);
    assert.equal(existsSync(join(root, "runtime", "dist")), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
