/**
 * WER-004: tests for the Council runtime installer (install-runtime.mjs).
 * Run with (the repo's own runner):
 *   node --test scripts/install-runtime.test.mjs
 *
 * Covers: the exact-executable SQLite prerequisite probe (in-memory plus
 * isolated persistent create/close/reopen), source integrity that hashes
 * protected SOURCE only (never node_modules or dist), the independent
 * generated-artifact receipt, staged install + atomic activation with
 * preserved receipts and a rollback instruction, durable user data outside
 * the replaceable trees, idempotent no-op re-runs, and the negative cases:
 * unsupported Node refuses before any partial installation, a failing or
 * interrupted build leaves the previous release usable, and a corrupt
 * artifact fails verification without activating.
 *
 * NOTE (deferred): fresh-install, real-update and rollback checks against a
 * live runtime checkout are deferred to the release pipeline and are NOT
 * claimed here.
 */

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import test from "node:test";

import {
  activateRelease,
  computeSourceManifest,
  isSupportedCouncilRuntimeNode,
  runPrerequisiteProbe,
  sourceReleaseId,
  stageRelease,
  verifyArtifactReceipt,
  verifyRelease,
  verifySourceManifest,
} from "./install-runtime.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const installer = join(here, "install-runtime.mjs");
const tmpBase = process.env.COUNCIL_TEST_TMPDIR ?? tmpdir();

function scratch() {
  return mkdtempSync(join(tmpBase, "council-runtime-install-"));
}

function fixtureRuntime(root, { tag = "v1", buildFails = false } = {}) {
  const runtime = join(root, "runtime");
  mkdirSync(join(runtime, "src"), { recursive: true });
  writeFileSync(
    join(runtime, "package.json"),
    JSON.stringify({
      name: "fixture-council-runtime",
      version: "1.0.0",
      private: true,
      main: "dist/app.js",
      scripts: { build: "node build.mjs" },
    }),
  );
  writeFileSync(
    join(runtime, "package-lock.json"),
    JSON.stringify({
      name: "fixture-council-runtime",
      version: "1.0.0",
      lockfileVersion: 3,
      requires: true,
      packages: { "": { name: "fixture-council-runtime", version: "1.0.0" } },
    }),
  );
  writeFileSync(join(runtime, "src", "data.txt"), `fixture source ${tag}\n`);
  const buildBody = buildFails
    ? [
        `import { mkdirSync, writeFileSync } from "node:fs";`,
        `mkdirSync("dist", { recursive: true });`,
        `writeFileSync("dist/partial.js", "half-written artifact");`,
        `process.exit(1); // simulated interrupted/failing build`,
      ]
    : [
        `import { mkdirSync, writeFileSync } from "node:fs";`,
        `mkdirSync("dist", { recursive: true });`,
        `writeFileSync("dist/app.js", 'export const tag = "${tag}";\\n');`,
        `writeFileSync("dist/app.js.map", "{}\\n");`,
      ];
  writeFileSync(join(runtime, "build.mjs"), `${buildBody.join("\n")}\n`);
  return runtime;
}

function runCli(args, { nodeArgs = [] } = {}) {
  const run = spawnSync(
    process.execPath,
    [...nodeArgs, installer, ...args],
    { encoding: "utf8" },
  );
  return {
    status: run.status,
    stdout: run.stdout ?? "",
    stderr: run.stderr ?? "",
    output: `${run.stdout ?? ""}${run.stderr ?? ""}`,
    error: run.error,
  };
}

test("exact-executable probe runs in-memory and persistent SQLite cycles through process.execPath", () => {
  const probe = runPrerequisiteProbe();
  assert.equal(probe.executable, process.execPath);
  assert.match(probe.output, /PROBE in-memory SQLite create\/insert\/read\/close: OK/);
  assert.match(probe.output, /PROBE persistent SQLite create\/close\/reopen: OK/);
  const child = runCli(["--probe-only"]);
  assert.equal(child.status, 0, child.output);
  assert.match(child.stdout, /PROBE in-memory SQLite create\/insert\/read\/close: OK/);
  assert.match(child.stdout, /PROBE persistent SQLite create\/close\/reopen: OK/);
});

test("unsupported Node refuses before any partial installation", () => {
  const root = scratch();
  try {
    const runtime = fixtureRuntime(root);
    const prefix = join(root, "release-prefix");
    const shim = join(root, "fake-node-version.mjs");
    writeFileSync(
      shim,
      `Object.defineProperty(process, "version", { value: "v20.19.0", configurable: true });\n`,
    );
    const run = runCli(["--root", root, "--prefix", prefix], {
      nodeArgs: ["--import", pathToFileURL(shim).href],
    });
    assert.equal(run.status, 1, run.output);
    assert.match(run.stdout, /requires Node\.js/);
    // Refusal must precede ANY write: no prefix, no staging, no install tree.
    assert.equal(existsSync(prefix), false);
    assert.equal(existsSync(join(runtime, "node_modules")), false);
    assert.equal(existsSync(join(runtime, "dist")), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("--check-prereqs probes the executing Node and writes nothing", () => {
  const root = scratch();
  try {
    const runtime = fixtureRuntime(root);
    const prefix = join(root, "release-prefix");
    const run = runCli(["--root", root, "--prefix", prefix, "--check-prereqs"]);
    if (isSupportedCouncilRuntimeNode(process.version)) {
      assert.equal(run.status, 0, run.output);
      assert.match(run.stdout, /in-memory SQLite read\/write/);
      assert.match(run.stdout, /RUNTIME-PREREQS: PASS/);
    } else {
      assert.equal(run.status, 1);
      assert.match(run.stdout, /requires Node\.js/);
    }
    assert.equal(existsSync(prefix), false);
    assert.equal(existsSync(join(runtime, "node_modules")), false);
    assert.equal(existsSync(join(runtime, "dist")), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("source manifest hashes protected SOURCE only, never node_modules or dist", () => {
  const root = scratch();
  try {
    const runtime = fixtureRuntime(root);
    // Simulate junk a previous in-place install/build would have left.
    mkdirSync(join(runtime, "node_modules", "leftover"), { recursive: true });
    writeFileSync(join(runtime, "node_modules", "leftover", "index.js"), "junk");
    mkdirSync(join(runtime, "dist"), { recursive: true });
    writeFileSync(join(runtime, "dist", "junk.js"), "junk");

    const manifest = computeSourceManifest(runtime);
    const paths = Object.keys(manifest.files);
    assert.ok(paths.includes("src/data.txt"));
    assert.ok(paths.includes("package.json"));
    assert.ok(paths.includes("package-lock.json"));
    for (const rel of paths) {
      assert.ok(!rel.includes("node_modules"), `node_modules leaked into manifest: ${rel}`);
      assert.ok(!rel.startsWith("dist/"), `dist leaked into manifest: ${rel}`);
    }
    assert.ok(manifest.excludes.includes("node_modules"));
    assert.ok(manifest.excludes.includes("dist"));

    // Junk in the excluded trees never trips verification...
    verifySourceManifest(runtime, manifest);
    writeFileSync(join(runtime, "node_modules", "leftover", "index.js"), "more junk");
    writeFileSync(join(runtime, "dist", "junk.js"), "more junk");
    verifySourceManifest(runtime, manifest);

    // ...but protected source tampering does.
    writeFileSync(join(runtime, "src", "data.txt"), "tampered\n");
    assert.throws(
      () => verifySourceManifest(runtime, manifest),
      /source integrity:.*changed src\/data\.txt/,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("staged install activates atomically, preserves old receipt, writes rollback, keeps user data", () => {
  const root = scratch();
  try {
    const prefix = join(root, "release-prefix");
    fixtureRuntime(root, { tag: "v1" });
    const first = runCli(["--root", root, "--prefix", prefix]);
    assert.equal(first.status, 0, first.output);
    assert.match(first.stdout, /INSTALL-RUNTIME: PASS/);

    const manifestA = computeSourceManifest(join(root, "runtime"));
    const idA = sourceReleaseId(manifestA);
    const releaseA = join(prefix, "releases", idA);
    assert.equal(readlinkSync(join(prefix, "current")), join("releases", idA));
    assert.ok(existsSync(join(releaseA, "SOURCE-MANIFEST.json")));
    assert.ok(existsSync(join(releaseA, "ARTIFACT-RECEIPT.json")));
    assert.ok(existsSync(join(releaseA, "dist", "app.js")));
    assert.ok(existsSync(join(prefix, "receipts", `${idA}.json`)));
    assert.ok(existsSync(join(prefix, "ROLLBACK.md")));
    assert.ok(existsSync(join(prefix, "user-data")));
    verifyRelease(releaseA);

    // Durable user data lives outside the replaceable trees.
    writeFileSync(join(prefix, "user-data", "marker.txt"), "keep me\n");

    fixtureRuntime(root, { tag: "v2" });
    const second = runCli(["--root", root, "--prefix", prefix]);
    assert.equal(second.status, 0, second.output);
    const idB = sourceReleaseId(computeSourceManifest(join(root, "runtime")));
    assert.notEqual(idB, idA);
    assert.equal(readlinkSync(join(prefix, "current")), join("releases", idB));

    // Old release and its receipt survive activation of the new one.
    assert.ok(existsSync(releaseA));
    assert.ok(existsSync(join(prefix, "receipts", `${idA}.json`)));
    const rollback = readFileSync(join(prefix, "ROLLBACK.md"), "utf8");
    assert.ok(rollback.includes(idA), "rollback instruction must name the preserved previous release");
    assert.ok(rollback.includes(`--activate ${idA}`), "rollback must carry the exact rollback command");
    assert.equal(readFileSync(join(prefix, "user-data", "marker.txt"), "utf8"), "keep me\n");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("repeated update of unchanged source is a no-op", () => {
  const root = scratch();
  try {
    const prefix = join(root, "release-prefix");
    fixtureRuntime(root);
    const first = runCli(["--root", root, "--prefix", prefix]);
    assert.equal(first.status, 0, first.output);
    const currentBefore = readlinkSync(join(prefix, "current"));

    const second = runCli(["--root", root, "--prefix", prefix]);
    assert.equal(second.status, 0, second.output);
    assert.match(second.stdout, /NO-OP/);
    assert.equal(readlinkSync(join(prefix, "current")), currentBefore);
    assert.equal(readdirSync(join(prefix, "releases")).length, 1);
    assert.equal(readdirSync(join(prefix, "receipts")).length, 1);
    assert.ok(!existsSync(join(prefix, ".staging")) || readdirSync(join(prefix, ".staging")).length === 0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("failing or interrupted build leaves the previous release usable", () => {
  const root = scratch();
  try {
    const prefix = join(root, "release-prefix");
    fixtureRuntime(root, { tag: "good" });
    const first = runCli(["--root", root, "--prefix", prefix]);
    assert.equal(first.status, 0, first.output);
    const idGood = sourceReleaseId(computeSourceManifest(join(root, "runtime")));
    const releaseGood = join(prefix, "releases", idGood);

    fixtureRuntime(root, { tag: "broken", buildFails: true });
    const second = runCli(["--root", root, "--prefix", prefix]);
    assert.notEqual(second.status, 0, second.output);
    assert.match(second.output, /staged runtime build: npm run build exited with status/);

    // Previous release untouched and still the active one.
    assert.equal(readlinkSync(join(prefix, "current")), join("releases", idGood));
    verifyRelease(releaseGood);
    assert.ok(existsSync(join(releaseGood, "dist", "app.js")));
    assert.equal(readdirSync(join(prefix, "releases")).length, 1);
    assert.ok(!existsSync(join(prefix, ".staging")) || readdirSync(join(prefix, ".staging")).length === 0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("corrupt artifact fails verification without activating", () => {
  const root = scratch();
  try {
    const prefix = join(root, "release-prefix");
    const runtime = fixtureRuntime(root);
    const id = sourceReleaseId(computeSourceManifest(runtime));
    stageRelease({ root, prefix, releaseId: id });

    // Corrupt a generated artifact in the staged release.
    appendFileSync(join(prefix, "releases", id, "dist", "app.js"), "// corrupt\n");
    assert.throws(() => activateRelease({ prefix, releaseId: id }), /artifact receipt:.*corrupt dist\/app\.js/);
    assert.equal(existsSync(join(prefix, "current")), false, "corrupt artifact must not activate");
    assert.equal(existsSync(join(prefix, "receipts", `${id}.json`)), false);
    assert.throws(() => verifyArtifactReceipt(join(prefix, "releases", id)), /corrupt dist\/app\.js/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("corrupt protected source in a staged release also refuses activation", () => {
  const root = scratch();
  try {
    const prefix = join(root, "release-prefix");
    const runtime = fixtureRuntime(root);
    const id = sourceReleaseId(computeSourceManifest(runtime));
    stageRelease({ root, prefix, releaseId: id });

    writeFileSync(join(prefix, "releases", id, "src", "data.txt"), "tampered\n");
    assert.throws(() => activateRelease({ prefix, releaseId: id }), /source integrity/);
    assert.equal(existsSync(join(prefix, "current")), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
