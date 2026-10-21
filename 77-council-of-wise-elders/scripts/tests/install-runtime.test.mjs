// WER-004 installer tests. Run with the repo's own runner:
//   node --test scripts/tests/install-runtime.test.mjs
// Covers the negative contracts: unsupported Node refuses before any
// partial installation, a failing build leaves the previous release
// usable, a corrupt (empty) artifact fails verification without
// activating, and source integrity never hashes node_modules or dist.
// The staged-install test writes only into prefixed temp directories;
// fresh-install, real-update and rollback on a live host stay deferred.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import {
  activate,
  findActiveMatchingRelease,
  readReceipt,
  runPrerequisiteProbe,
  sha256,
  sourceManifest,
  verifyDistProducts,
  writeReceipt,
} from "../install-runtime.mjs";

const scriptsDir = fileURLToPath(new URL("..", import.meta.url));
const installer = join(scriptsDir, "install-runtime.mjs");
const skillRoot = resolve(scriptsDir, "..");
const realRuntimeDir = join(skillRoot, "runtime");
const BOX_TMP_PREFIX = join(tmpdir(), "lane-W01-U002-");

// macOS realpath maps /var -> /private/var; compare resolved forms.
function real(path) {
  return realpathSync(path);
}

function tempDir(label) {
  return mkdtempSync(BOX_TMP_PREFIX + label + "-");
}

function findUnsupportedNode() {
  // Named source: the nvm versions directory on this box. Not checked:
  // Homebrew, volta, asdf, system /usr/bin/node.
  const nvmDir = join(homedir(), ".nvm", "versions", "node");
  if (!existsSync(nvmDir)) return null;
  const v20 = readdirSync(nvmDir)
    .filter((name) => /^v20\./.test(name))
    .sort()
    .at(-1);
  const candidate = v20 ? join(nvmDir, v20, "bin", "node") : null;
  return candidate && existsSync(candidate) ? candidate : null;
}

function makeFixtureRuntime(dir, pkg) {
  mkdirSync(join(dir, "runtime", "src"), { recursive: true });
  const full = {
    name: "fixture-council-runtime",
    version: "0.0.0",
    private: true,
    ...pkg,
  };
  writeFileSync(join(dir, "runtime", "package.json"), JSON.stringify(full));
  writeFileSync(
    join(dir, "runtime", "package-lock.json"),
    JSON.stringify({
      name: full.name,
      version: full.version,
      lockfileVersion: 3,
      requires: true,
      packages: { "": { name: full.name, version: full.version, private: true } },
    }),
  );
  writeFileSync(join(dir, "runtime", "src", "index.ts"), "export const fixture = true;\n");
}

function installPreviousRelease(prefix, manifestSha256, releaseId = "prev-release") {
  const prevDir = join(prefix, "releases", releaseId);
  mkdirSync(prevDir, { recursive: true });
  writeFileSync(join(prevDir, "marker.txt"), `usable previous release ${releaseId}\n`);
  writeFileSync(
    join(prevDir, "release-receipt.json"),
    JSON.stringify({
      kind: "council-runtime-release-receipt",
      version: 1,
      releaseId,
      sourceManifestSha256: manifestSha256,
      nodeVersion: "fixture",
      npmCommands: ["fixture"],
      stagedAt: "fixture",
      dist: {},
    }),
  );
  symlinkSync(prevDir, join(prefix, "current"));
  return prevDir;
}

function runInstaller(nodeExe, rootArg, prefixArg, extra = []) {
  return spawnSync(nodeExe, [installer, "--root", rootArg, "--prefix", prefixArg, ...extra], {
    encoding: "utf8",
  });
}

test("sourceManifest hashes protected SOURCE only, never node_modules or dist", () => {
  const dir = tempDir("manifest");
  try {
    mkdirSync(join(dir, "src"), { recursive: true });
    mkdirSync(join(dir, "node_modules", "evil"), { recursive: true });
    mkdirSync(join(dir, "dist"), { recursive: true });
    mkdirSync(join(dir, "src", "nested", "node_modules"), { recursive: true });
    writeFileSync(join(dir, "package.json"), "{}");
    writeFileSync(join(dir, "src", "index.ts"), "export {};\n");
    writeFileSync(join(dir, "node_modules", "evil", "x.js"), "module.exports = 1;\n");
    writeFileSync(join(dir, "dist", "index.js"), "built();\n");
    writeFileSync(join(dir, "src", "nested", "node_modules", "y.js"), "1;\n");

    const manifest = sourceManifest(dir);
    const paths = manifest.entries.map((e) => e.path);
    assert.ok(paths.includes("src/index.ts"), `entries: ${paths.join(",")}`);
    assert.ok(paths.includes("package.json"), `entries: ${paths.join(",")}`);
    for (const path of paths) {
      assert.match(path, /^(package\.json|package-lock\.json|tsconfig\.json|README\.md|src\/|scripts\/|config\/|schemas\/|tests\/)/, path);
      assert.equal(path.includes("node_modules"), false, path);
      assert.equal(path.includes("dist/"), false, path);
    }
    assert.equal(manifest.manifestSha256, sha256(manifest.canonical));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("sourceManifest is deterministic across calls and changes when source changes", () => {
  const dir = tempDir("determinism");
  try {
    mkdirSync(join(dir, "src"), { recursive: true });
    writeFileSync(join(dir, "package.json"), "{}");
    writeFileSync(join(dir, "src", "a.ts"), "export const a = 1;\n");
    const first = sourceManifest(dir);
    const second = sourceManifest(dir);
    assert.equal(first.manifestSha256, second.manifestSha256);
    writeFileSync(join(dir, "src", "a.ts"), "export const a = 2;\n");
    const third = sourceManifest(dir);
    assert.notEqual(first.manifestSha256, third.manifestSha256);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("verifyDistProducts rejects missing and empty (corrupt) artifacts", () => {
  const dir = tempDir("verifydist");
  try {
    assert.equal(verifyDistProducts(dir).ok, false);
    mkdirSync(join(dir, "dist"), { recursive: true });
    assert.equal(verifyDistProducts(dir).ok, false); // files missing
    writeFileSync(join(dir, "dist", "index.js"), "");
    writeFileSync(join(dir, "dist", "blackceo-council.mjs"), "");
    const empty = verifyDistProducts(dir);
    assert.equal(empty.ok, false);
    assert.match(empty.reason, /empty \(corrupt build artifact\)/);
    writeFileSync(join(dir, "dist", "index.js"), "console.log(1);\n");
    writeFileSync(join(dir, "dist", "blackceo-council.mjs"), "console.log(2);\n");
    assert.equal(verifyDistProducts(dir).ok, true);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("receipt round trip: writeReceipt records dist hashes and source manifest hash", () => {
  const dir = tempDir("receipt");
  try {
    mkdirSync(join(dir, "dist"), { recursive: true });
    writeFileSync(join(dir, "dist", "index.js"), "a;\n");
    writeFileSync(join(dir, "dist", "blackceo-council.mjs"), "b;\n");
    const result = writeReceipt(dir, {
      releaseId: "r1",
      sourceManifestSha256: "abc",
      nodeVersion: "v24.0.0",
      npmCommands: ["npm ci --no-audit --no-fund", "npm run build"],
      stagedAt: "now",
    });
    assert.equal(result.ok, true);
    assert.equal(result.receipt.sourceManifestSha256, "abc");
    assert.equal(result.receipt.dist["dist/index.js"], sha256(Buffer.from("a;\n")));
    const read = readReceipt(dir);
    assert.equal(read.releaseId, "r1");
    assert.equal(read.kind, "council-runtime-release-receipt");
    assert.equal(verifyDistProducts(dir).ok, true);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("activate preserves the old receipt, swaps current atomically, and emits rollback", () => {
  const prefix = tempDir("activate");
  try {
    const prev = installPreviousRelease(prefix, "old-sha", "prev-release");
    const staging = tempDir("staging2");
    mkdirSync(join(staging, "dist"), { recursive: true });
    writeFileSync(join(staging, "dist", "index.js"), "new;\n");
    writeFileSync(join(staging, "dist", "blackceo-council.mjs"), "new;\n");
    const receipt = writeReceipt(staging, {
      releaseId: "new-release",
      sourceManifestSha256: "new-sha",
      nodeVersion: "v24",
      npmCommands: [],
      stagedAt: "now",
    });
    assert.equal(receipt.ok, true);

    const result = activate(staging, prefix, "new-release");
    assert.equal(result.ok, true);
    assert.equal(result.oldReleaseId, "prev-release");
    assert.equal(real(realpathSync(join(prefix, "current"))), real(join(prefix, "releases", "new-release")));
    assert.ok(result.rollback, "rollback instruction emitted");
    assert.match(result.rollback, /prev-release/);

    const bak = readFileSync(join(prefix, "releases", "prev-release.receipt.json.bak"), "utf8");
    assert.equal(JSON.parse(bak).releaseId, "prev-release");
    assert.ok(existsSync(prev), "old release tree untouched");
  } finally {
    rmSync(prefix, { recursive: true, force: true });
  }
});

test("findActiveMatchingRelease detects the active release by source manifest hash", () => {
  const prefix = tempDir("idem");
  try {
    assert.equal(findActiveMatchingRelease(prefix, "sha"), null);
    const active = installPreviousRelease(prefix, "sha-42", "active-release");
    assert.equal(real(findActiveMatchingRelease(prefix, "sha-42")?.activeDir), real(active));
    assert.equal(findActiveMatchingRelease(prefix, "different"), null);
  } finally {
    rmSync(prefix, { recursive: true, force: true });
  }
});

test("prerequisite probe passes on this supported Node through the resolved executable", () => {
  const result = runPrerequisiteProbe(process.execPath);
  assert.equal(result.ok, true, result.reason ?? "");
});

test("unsupported Node 20 refuses BEFORE any partial installation", { timeout: 120000 }, (t) => {
  const node20 = findUnsupportedNode();
  if (!node20) {
    t.skip("no Node 20 executable found in ~/.nvm/versions/node on this host");
    return;
  }
  const root = tempDir("node20");
  const prefix = join(tempDir("node20prefix-base"), "nested-prefix"); // must NOT be created
  t.after(() => {
    rmSync(root, { recursive: true, force: true });
    rmSync(join(tmpdir(), "lane-W01-U002-node20prefix-base-"), { recursive: true, force: true });
    rmSync(prefix, { recursive: true, force: true });
  });
  makeFixtureRuntime(root, {});

  const run = runInstaller(node20, root, prefix);
  assert.equal(run.status, 1, run.stdout + run.stderr);
  assert.match(run.stdout, /FAIL probe: Council runtime requires Node\.js/);
  // Probe runs through the resolved launcher executable, before any
  // partial installation: nothing is written under the prefix at all.
  assert.equal(existsSync(prefix), false, "prefix must not be created by a refused install");
  assert.equal(existsSync(join(root, "runtime", "node_modules")), false);
  assert.equal(existsSync(join(root, "runtime", "dist")), false);

  // The diagnostic path also refuses on unsupported Node.
  const check = runInstaller(node20, root, prefix, ["--check-prereqs"]);
  assert.equal(check.status, 1);
  assert.match(check.stdout, /requires Node\.js/);
});

test("failing build leaves the previous release usable and discards staging", { timeout: 300000 }, (t) => {
  const root = tempDir("failbuild");
  const prefix = tempDir("failbuildprefix");
  t.after(() => {
    rmSync(root, { recursive: true, force: true });
    rmSync(prefix, { recursive: true, force: true });
  });
  makeFixtureRuntime(root, { scripts: { build: 'node -e "process.exit(3)"' } });
  const prev = installPreviousRelease(prefix, "irrelevant-sha");

  const run = runInstaller(process.execPath, root, prefix);
  assert.equal(run.status, 1, run.stdout + run.stderr);
  assert.match(run.stdout, /FAIL build: npm exited with status 3/);
  assert.match(run.stdout, /staged partial install discarded; previous release untouched/);

  assert.equal(real(realpathSync(join(prefix, "current"))), real(prev));
  assert.ok(readFileSync(join(prev, "marker.txt"), "utf8").includes("usable previous release"));
  const stagingEntries = existsSync(join(prefix, "staging"))
    ? readdirSync(join(prefix, "staging"))
    : [];
  assert.equal(stagingEntries.length, 0, `staging must be empty: ${stagingEntries.join(",")}`);
  assert.equal(existsSync(join(root, "runtime", "node_modules")), false, "source tree never built in place");
});

test("corrupt (empty) artifact fails verification without activating", { timeout: 300000 }, (t) => {
  const root = tempDir("corrupt");
  const prefix = tempDir("corruptprefix");
  t.after(() => {
    rmSync(root, { recursive: true, force: true });
    rmSync(prefix, { recursive: true, force: true });
  });
  // Build "succeeds" but produces empty artifacts.
  makeFixtureRuntime(root, {
    scripts: {
      build:
        "node -e \"const fs=require('fs');fs.mkdirSync('dist',{recursive:true});fs.writeFileSync('dist/index.js','');fs.writeFileSync('dist/blackceo-council.mjs','')\"",
    },
  });
  const prev = installPreviousRelease(prefix, "irrelevant-sha");

  const run = runInstaller(process.execPath, root, prefix);
  assert.equal(run.status, 1, run.stdout + run.stderr);
  assert.match(run.stdout, /FAIL verify: runtime\/dist\/index\.js is empty \(corrupt build artifact\)/);
  assert.match(run.stdout, /staged partial install discarded/);
  assert.equal(real(realpathSync(join(prefix, "current"))), real(prev));
});

test("staged install of the real runtime builds a usable release; repeated run is a no-op", { timeout: 600000 }, (t) => {
  const prefix = tempDir("fullinstall");
  t.after(() => {
    rmSync(prefix, { recursive: true, force: true });
  });
  assert.ok(existsSync(join(realRuntimeDir, "package.json")), "real runtime source must exist");

  const first = runInstaller(process.execPath, skillRoot, prefix);
  assert.equal(first.status, 0, first.stdout + first.stderr);
  assert.match(first.stdout, /PASS probe: resolved launcher/);
  assert.match(first.stdout, /staged dependency install \(npm ci\)/);
  assert.match(first.stdout, /PASS build: npm run build complete in staging/);
  assert.match(first.stdout, /PASS verify: staged build products exist and are non-empty/);
  assert.match(first.stdout, /PASS activate: current -> releases\//);
  assert.match(first.stdout, /INSTALL-RUNTIME: PASS/);

  const current = realpathSync(join(prefix, "current"));
  assert.ok(
    real(current).startsWith(real(join(prefix, "releases")) + "/"),
    `current must resolve inside releases/: ${current}`,
  );
  assert.ok(verifyDistProducts(current).ok, "activated release must carry usable dist products");
  const manifest = sourceManifest(realRuntimeDir);
  const receipt = readReceipt(current);
  assert.equal(receipt.sourceManifestSha256, manifest.manifestSha256);
  assert.equal(receipt.npmCommands.join("; "), "npm ci --no-audit --no-fund; npm run build");
  assert.ok(existsSync(join(current, "source-manifest.json")));
  // The canonical manifest in the release must not hash node_modules or dist.
  const persisted = JSON.parse(readFileSync(join(current, "source-manifest.json"), "utf8"));
  for (const entry of persisted.entries) {
    assert.equal(entry.path.includes("node_modules"), false, entry.path);
    assert.equal(entry.path.startsWith("dist/"), false, entry.path);
  }

  // Idempotence: same source, repeated update is a no-op (no new release).
  const before = readdirSync(join(prefix, "releases")).length;
  const second = runInstaller(process.execPath, skillRoot, prefix);
  assert.equal(second.status, 0, second.stdout + second.stderr);
  assert.match(second.stdout, /PASS idempotence: active release .* already matches source manifest/);
  assert.match(second.stdout, /INSTALL-RUNTIME: PASS \(no-op; already installed\)/);
  assert.equal(readdirSync(join(prefix, "releases")).length, before, "no-op must not add a release");

  // A second activation would preserve the old receipt; simulate the
  // real-update path with --force against the same prefix to prove the
  // old receipt is preserved and a rollback instruction is printed.
  const third = runInstaller(process.execPath, skillRoot, prefix, ["--force"]);
  assert.equal(third.status, 0, third.stdout + third.stderr);
  assert.match(third.stdout, /INFO previous release preserved at releases\//);
  assert.match(third.stdout, /\.receipt\.json\.bak/);
  assert.match(third.stdout, /ROLLBACK: ln -sfn/);
  assert.ok(readdirSync(join(prefix, "releases")).length > before, "--force must add a release");
  assert.equal(
    readdirSync(join(prefix, "releases")).filter((n) => n.endsWith(".receipt.json.bak")).length,
    1,
    "exactly one preserved old receipt",
  );

  // --check-prereqs on the supported host Node installs nothing.
  const probe = runInstaller(process.execPath, skillRoot, prefix, ["--check-prereqs"]);
  assert.equal(probe.status, 0, probe.stdout + probe.stderr);
  assert.match(probe.stdout, /RUNTIME-PREREQS: PASS \(no installation performed\)/);
});

// Direct-file import guard: the test itself must import the module, and
// the installer must only run main() when invoked as the CLI entry point.
test("installer main does not run on import (test harness imports the module)", async () => {
  const url = pathToFileURL(installer).href;
  const probe = spawnSync(process.execPath, ["-e", `import(${JSON.stringify(url)})`], { encoding: "utf8" });
  assert.equal(probe.status, 0, probe.stdout + probe.stderr);
  assert.doesNotMatch(probe.stdout, /INSTALL-RUNTIME|FAIL/);
});