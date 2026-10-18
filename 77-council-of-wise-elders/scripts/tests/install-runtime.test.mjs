// WER-004 dependency-ready slice: installer behavior tests.
//
// Covers the negative cases the plan requires:
//   - unsupported Node refuses BEFORE any partial installation,
//   - an interrupted/failing build leaves the previous release usable,
//   - a corrupt generated artifact fails verification without activating.
//
// The staged install is exercised with an injected fake npm so the suite stays
// hermetic and fast. A real npm/browser/installed acceptance run is DEFERRED
// and is never claimed by this file.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  SOURCE_IGNORED_NAMES,
  computeSourceManifest,
  defaultPrefix,
  isSupportedNodeVersion,
  parseArgs,
} from "../install-runtime.mjs";

const scriptsDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const installer = join(scriptsDir, "install-runtime.mjs");

function laneTemp(prefix) {
  return mkdtempSync(join(tmpdir(), `operator-W01-U002-${prefix}-`));
}

function writeFixtureRuntime(runtimeDir, { marker = "one" } = {}) {
  mkdirSync(join(runtimeDir, "src"), { recursive: true });
  writeFileSync(join(runtimeDir, "src", "index.ts"), `export const marker = ${JSON.stringify(marker)};\n`);
  writeFileSync(join(runtimeDir, "package.json"), JSON.stringify({
    name: "fixture-council-runtime",
    version: "0.0.0",
    private: true,
    type: "module",
    engines: { node: "^22.13.0 || >=24" },
    scripts: { build: "true" },
    dependencies: {},
    devDependencies: {},
  }, null, 2));
  writeFileSync(join(runtimeDir, "package-lock.json"), JSON.stringify({
    name: "fixture-council-runtime",
    version: "0.0.0",
    lockfileVersion: 3,
    requires: true,
    packages: { "": { name: "fixture-council-runtime", version: "0.0.0" } },
  }, null, 2));
}

function writeExecutable(dir, name, body) {
  const path = join(dir, name);
  writeFileSync(path, body);
  chmodSync(path, 0o755);
  return path;
}

function writeFakeNpm(dir) {
  return writeExecutable(dir, "fake-npm", `#!/bin/sh
set -e
case "$1" in
  ci)
    mkdir -p node_modules/fixture-dep
    printf 'module.exports = 1;\\n' > node_modules/fixture-dep/index.js
    exit 0
    ;;
  run)
    if [ "$2" != "build" ]; then exit 0; fi
    if [ "\${FAKE_BUILD_FAIL:-0}" = "1" ]; then
      echo "fake build failure" >&2
      exit 7
    fi
    mkdir -p dist
    printf 'export const built = true;\\n' > dist/index.js
    printf '#!/usr/bin/env node\\nconsole.log("council");\\n' > dist/blackceo-council.mjs
    exit 0
    ;;
esac
exit 0
`);
}

function writeFakeNode(dir, name, body) {
  return writeExecutable(dir, name, body);
}

function run(args, env = {}) {
  const result = spawnSync(process.execPath, [installer, ...args], {
    encoding: "utf8",
    env: { ...process.env, ...env },
    timeout: 120_000,
  });
  return { status: result.status, output: `${result.stdout || ""}${result.stderr || ""}` };
}

function readActive(prefix) {
  return JSON.parse(readFileSync(join(prefix, "active.json"), "utf8"));
}

test("Node support gate accepts 22.13+/24+ and rejects 20", () => {
  for (const version of ["v18.20.8", "v20.19.0", "v22.12.0", "v23.10.0", "garbled"]) {
    assert.equal(isSupportedNodeVersion(version), false, version);
  }
  for (const version of ["v22.13.0", "v22.16.1", "v24.0.0", "v24.21.0", "v25.2.0"]) {
    assert.equal(isSupportedNodeVersion(version), true, version);
  }
});

test("source manifest hashes protected source only, never node_modules or dist", () => {
  const workspace = laneTemp("manifest");
  try {
    const runtimeDir = join(workspace, "runtime");
    writeFixtureRuntime(runtimeDir);
    const before = computeSourceManifest(runtimeDir);

    // Generated/dependency trees appear and change: the SOURCE digest must not.
    mkdirSync(join(runtimeDir, "node_modules", "zod"), { recursive: true });
    writeFileSync(join(runtimeDir, "node_modules", "zod", "index.js"), "zod bytes\n");
    mkdirSync(join(runtimeDir, "dist"), { recursive: true });
    writeFileSync(join(runtimeDir, "dist", "index.js"), "built bytes\n");
    const withGenerated = computeSourceManifest(runtimeDir);
    assert.equal(withGenerated.digest, before.digest);
    assert.equal(withGenerated.fileCount, before.fileCount);
    assert.ok(!withGenerated.entries.some((entry) => entry.path.startsWith("node_modules/")));
    assert.ok(!withGenerated.entries.some((entry) => entry.path.startsWith("dist/")));

    // A real source change MUST change the digest.
    writeFileSync(join(runtimeDir, "src", "index.ts"), "export const marker = \"two\";\n");
    const changed = computeSourceManifest(runtimeDir);
    assert.notEqual(changed.digest, before.digest);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("exclusions are named explicitly", () => {
  assert.ok(SOURCE_IGNORED_NAMES.has("node_modules"));
  assert.ok(SOURCE_IGNORED_NAMES.has("dist"));
});

test("release prefix defaults outside the checkout and honours the env override", () => {
  const saved = process.env.COUNCIL_RUNTIME_PREFIX;
  try {
    process.env.COUNCIL_RUNTIME_PREFIX = join(tmpdir(), "operator-W01-U002-prefix-probe");
    assert.equal(defaultPrefix(), resolve(process.env.COUNCIL_RUNTIME_PREFIX));
    delete process.env.COUNCIL_RUNTIME_PREFIX;
    assert.equal(defaultPrefix().startsWith(resolve(scriptsDir)), false);
  } finally {
    if (saved === undefined) delete process.env.COUNCIL_RUNTIME_PREFIX;
    else process.env.COUNCIL_RUNTIME_PREFIX = saved;
  }
});

test("prerequisite probe runs through the resolved executable and writes nothing", () => {
  const workspace = laneTemp("prereq");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    writeFixtureRuntime(runtimeDir);
    const result = run(["--runtime-dir", runtimeDir, "--prefix", prefix, "--check-prereqs"]);
    assert.equal(result.status, 0, result.output);
    assert.match(result.output, /in-memory SQLite read\/write and persistent reopen/);
    assert.match(result.output, /RUNTIME-PREREQS: PASS/);
    assert.ok(result.output.includes(realpathSync(process.execPath)), result.output);
    assert.equal(existsSync(prefix), false, "no release prefix may be written before installation");
    assert.equal(existsSync(join(runtimeDir, "node_modules")), false);
    assert.equal(existsSync(join(runtimeDir, "dist")), false);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("unsupported Node refuses before any partial installation", () => {
  const workspace = laneTemp("node20");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    writeFixtureRuntime(runtimeDir);
    const fakeNode = writeFakeNode(workspace, "node20", `#!/bin/sh
if [ "$1" = "--version" ]; then echo "v20.19.0"; exit 0; fi
exit 0
`);
    const result = run([
      "--runtime-dir", runtimeDir,
      "--prefix", prefix,
      "--node-executable", fakeNode,
    ]);
    assert.equal(result.status, 1, result.output);
    assert.match(result.output, /requires Node\.js/);
    assert.equal(existsSync(prefix), false, "unsupported Node must refuse before writing the prefix");
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("a failing node:sqlite probe blocks the install before any file is written", () => {
  const workspace = laneTemp("probe");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    writeFixtureRuntime(runtimeDir);
    const fakeNode = writeFakeNode(workspace, "probe-fails", `#!/bin/sh
if [ "$1" = "--version" ]; then echo "v22.13.0"; exit 0; fi
echo "node:sqlite disabled in this build" >&2
exit 9
`);
    const result = run([
      "--runtime-dir", runtimeDir,
      "--prefix", prefix,
      "--node-executable", fakeNode,
    ]);
    assert.equal(result.status, 1, result.output);
    assert.match(result.output, /node:sqlite/);
    assert.equal(existsSync(prefix), false, "probe failure must block before any partial installation");
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("install stages, verifies and activates an immutable release", () => {
  const workspace = laneTemp("install");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    writeFixtureRuntime(runtimeDir);
    const npm = writeFakeNpm(workspace);
    const result = run([
      "--runtime-dir", runtimeDir,
      "--prefix", prefix,
      "--npm-executable", npm,
      "--idempotent",
    ]);
    assert.equal(result.status, 0, result.output);
    writeFixtureRuntime(runtimeDir); // restore fixture source (cpSync leaves it untouched, this is a guard)

    const active = readActive(prefix);
    assert.match(active.releaseId, /^rel-[0-9a-f]{12}$/);
    assert.equal(active.previousReleaseId, null);
    assert.ok(existsSync(join(active.releasePath, "dist", "index.js")));
    assert.ok(existsSync(join(active.releasePath, "dist", "blackceo-council.mjs")));
    assert.ok(existsSync(join(prefix, "receipts", `${active.releaseId}.source.json`)));
    assert.ok(existsSync(join(prefix, "receipts", `${active.releaseId}.artifact.json`)));
    assert.ok(existsSync(join(prefix, "ROLLBACK.md")));
    assert.ok(existsSync(join(prefix, "data")), "durable data dir must exist outside release trees");
    assert.equal(active.dataDir, join(prefix, "data"));
    assert.equal(active.dataDir.startsWith(join(prefix, "releases")), false);

    const sourceReceipt = JSON.parse(
      readFileSync(join(prefix, "receipts", `${active.releaseId}.source.json`), "utf8")
    );
    assert.ok(!sourceReceipt.entries.some((entry) => entry.path.startsWith("node_modules/")));
    assert.ok(!sourceReceipt.entries.some((entry) => entry.path.startsWith("dist/")));
    // node_modules/dependency bytes must never enter the canonical source manifest.
    assert.equal(sourceReceipt.digest, active.sourceManifestDigest);

    const artifactReceipt = JSON.parse(
      readFileSync(join(prefix, "receipts", `${active.releaseId}.artifact.json`), "utf8")
    );
    assert.notEqual(artifactReceipt.digest, sourceReceipt.digest);
    assert.ok(artifactReceipt.entries.some((entry) => entry.path === "dist/index.js"));
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("a repeated install is a no-op that changes nothing", () => {
  const workspace = laneTemp("noop");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    writeFixtureRuntime(runtimeDir);
    const npm = writeFakeNpm(workspace);
    const args = ["--runtime-dir", runtimeDir, "--prefix", prefix, "--npm-executable", npm];

    const first = run(args);
    assert.equal(first.status, 0, first.output);
    const activePath = join(prefix, "active.json");
    const activeBefore = readFileSync(activePath, "utf8");

    const second = run(args);
    assert.equal(second.status, 0, second.output);
    assert.match(second.output, /NOOP/);
    assert.equal(readFileSync(activePath, "utf8"), activeBefore);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("a failing build leaves the previous release active and usable", () => {
  const workspace = laneTemp("buildfail");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    const npm = writeFakeNpm(workspace);
    writeFixtureRuntime(runtimeDir, { marker: "one" });
    const args = ["--runtime-dir", runtimeDir, "--prefix", prefix, "--npm-executable", npm];

    const first = run(args);
    assert.equal(first.status, 0, first.output);
    const activeBefore = readFileSync(join(prefix, "active.json"), "utf8");
    const previousRelease = readActive(prefix).releasePath;
    const previousDist = readFileSync(join(previousRelease, "dist", "index.js"));

    // New source, then a build that fails mid-install.
    writeFixtureRuntime(runtimeDir, { marker: "two" });
    const failed = run(args, { FAKE_BUILD_FAIL: "1" });
    assert.equal(failed.status, 1, failed.output);
    assert.match(failed.output, /runtime build/);
    assert.match(failed.output, /unchanged and still active/);

    assert.equal(readFileSync(join(prefix, "active.json"), "utf8"), activeBefore);
    assert.ok(existsSync(join(previousRelease, "dist", "index.js")));
    assert.deepEqual(readFileSync(join(previousRelease, "dist", "index.js")), previousDist);
    assert.deepEqual(readdirSync(join(prefix, "staging")), [], "failed staging must be cleaned up");
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("a corrupt artifact fails verification without activating", () => {
  const workspace = laneTemp("corrupt");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    writeFixtureRuntime(runtimeDir);
    const npm = writeFakeNpm(workspace);
    const args = ["--runtime-dir", runtimeDir, "--prefix", prefix, "--npm-executable", npm];

    const first = run(args);
    assert.equal(first.status, 0, first.output);
    const active = readActive(prefix);
    const activeBefore = readFileSync(join(prefix, "active.json"), "utf8");

    writeFileSync(join(active.releasePath, "dist", "index.js"), "corrupted bytes\n");

    const verified = run(["--prefix", prefix, "--verify-release", active.releasePath]);
    assert.equal(verified.status, 1, verified.output);
    assert.match(verified.output, /corrupt generated file|integrity mismatch/);
    assert.equal(readFileSync(join(prefix, "active.json"), "utf8"), activeBefore);

    // A fresh install must detect the failed verification and rebuild rather
    // than trusting the corrupt active release as a no-op.
    const rebuilt = run(args);
    assert.equal(rebuilt.status, 0, rebuilt.output);
    assert.doesNotMatch(rebuilt.output, /NOOP/);
    assert.match(readFileSync(join(prefix, "active.json"), "utf8"), /rel-/);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("activation preserves the previous receipt and rollback restores it", () => {
  const workspace = laneTemp("rollback");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    const npm = writeFakeNpm(workspace);
    const args = ["--runtime-dir", runtimeDir, "--prefix", prefix, "--npm-executable", npm];

    writeFixtureRuntime(runtimeDir, { marker: "one" });
    assert.equal(run(args).status, 0);
    const first = readActive(prefix);

    writeFixtureRuntime(runtimeDir, { marker: "two" });
    assert.equal(run(args).status, 0);
    const second = readActive(prefix);
    assert.notEqual(second.releaseId, first.releaseId);
    assert.equal(second.previousReleaseId, first.releaseId);
    assert.ok(existsSync(join(prefix, "receipts", `${first.releaseId}.release.json`)));
    assert.ok(existsSync(join(prefix, "previous-active.json")));
    assert.match(readFileSync(join(prefix, "ROLLBACK.md"), "utf8"), /--rollback/);
    assert.match(readFileSync(join(prefix, "ROLLBACK.md"), "utf8"), /does NOT downgrade or reverse a/);

    const rolledBack = run(["--prefix", prefix, "--rollback"]);
    assert.equal(rolledBack.status, 0, rolledBack.output);
    const restored = readActive(prefix);
    assert.equal(restored.releaseId, first.releaseId);
    assert.equal(restored.previousReleaseId, second.releaseId);
    assert.ok(existsSync(join(prefix, "releases", second.releaseId, "dist", "index.js")));
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("durable data inside the replaceable releases tree is refused", () => {
  const workspace = laneTemp("datadir");
  try {
    const runtimeDir = join(workspace, "runtime");
    const prefix = join(workspace, "prefix");
    writeFixtureRuntime(runtimeDir);
    const result = run([
      "--runtime-dir", runtimeDir,
      "--prefix", prefix,
      "--data-dir", join(prefix, "releases", "data"),
      "--npm-executable", writeFakeNpm(workspace),
    ]);
    assert.equal(result.status, 1, result.output);
    assert.match(result.output, /durable data .* must live outside replaceable release trees/);
    assert.equal(existsSync(join(prefix, "releases")), false);
  } finally {
    rmSync(workspace, { recursive: true, force: true });
  }
});

test("argument parsing rejects unknown options instead of guessing", () => {
  assert.throws(() => parseArgs(["--nonsense"]), /unknown option/);
  const parsed = parseArgs(["--root", "/tmp/operator-W01-U002-root", "--idempotent"]);
  assert.equal(parsed.runtimeDir, resolve("/tmp/operator-W01-U002-root", "runtime"));
});
