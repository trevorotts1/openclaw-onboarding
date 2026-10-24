#!/usr/bin/env node
// Council of Wise Elders runtime installer (WER-004 dependency-ready slice).
//
// Builds a usable runtime as a staged, verified, atomic release instead of an
// in-place mutation of runtime/. Behavior:
//   (a) Exact-executable prerequisite probe: node:sqlite in-memory
//       create/insert/read/close PLUS an isolated persistent
//       create/close/reopen cycle, run through the resolved launcher
//       executable (process.execPath, never a PATH assumption) BEFORE any
//       partial installation. Unsupported Node (20 and older, 23) refuses
//       first; the tested 22.13+ and 24 lines are accepted.
//   (b) Staged immutable install into an external release prefix using
//       `npm ci --no-audit --no-fund` and `npm run build`. The active
//       previous release is untouched until every stage verifies; releases
//       land under <prefix>/releases/<releaseId> and are never rewritten.
//   (c) Source-integrity verification hashes protected SOURCE only
//       (everything in runtime/ except node_modules, dist and this
//       installer's own generated receipts) into a canonical source
//       manifest. node_modules and dist are never hashed into it.
//   (d) An independent generated-artifact receipt (ARTIFACT-RECEIPT.json)
//       covers dist/** only and is re-read and re-verified from disk before
//       activation, separate from the source manifest.
//   (e) Atomic activation swaps <prefix>/current via symlink rename, copies
//       the receipt into a durable <prefix>/receipts ledger (old receipts
//       are preserved, never deleted), writes ROLLBACK.md naming the
//       previous release and the exact rollback command, and keeps durable
//       user data in <prefix>/user-data, outside the replaceable trees.
//   (f) Idempotence: releaseId is content-addressed from the source
//       manifest, so a repeated update of unchanged source is a no-op.
//
// Usage:
//   node install-runtime.mjs [--root <skill-folder>]
//                            [--prefix <release-prefix>]
//                            [--check-prereqs]
//                            [--activate <releaseId>]
//   --check-prereqs  probe only; installs and builds nothing
//   --activate       verify + activate an existing release (rollback path)
//   --probe-only     internal: child half of the exact-executable probe
// Release prefix default: $COUNCIL_RUNTIME_RELEASE_PREFIX or
//   ~/.blackceo/council-runtime (external to any checkout).
// Exit codes: 0 success or no-op, 1 preflight/install/verification failure.
//
// DEFERRED (never claimed by this script's tests): fresh-install,
// real-update and rollback checks against a live runtime checkout. Those
// installed checks are deferred to the release pipeline.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  renameSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { homedir, tmpdir } from "node:os";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { isSupportedCouncilRuntimeNode } from "./node-runtime-preflight.mjs";

export { isSupportedCouncilRuntimeNode };

const SELF = fileURLToPath(import.meta.url);

// Generated trees and this installer's own receipts are excluded from the
// canonical source manifest at any depth (c): node_modules and dist are
// NEVER hashed into it.
const SOURCE_EXCLUDES = [
  "node_modules",
  "dist",
  "SOURCE-MANIFEST.json",
  "ARTIFACT-RECEIPT.json",
];

// ---------------------------------------------------------------------------
// hashing / source manifest
// ---------------------------------------------------------------------------

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function sha256Json(value) {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

// Regular files under dir, sorted, skipping SOURCE_EXCLUDES at any depth.
function listSourceFiles(dir, base = dir) {
  const out = [];
  const entries = readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
  );
  for (const entry of entries) {
    if (SOURCE_EXCLUDES.includes(entry.name)) continue;
    const abs = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listSourceFiles(abs, base));
    else if (entry.isFile()) out.push(relative(base, abs));
  }
  return out;
}

// Every regular file under dir, sorted, as dir-relative paths (no excludes).
function listAllFiles(dir, base = dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
  )) {
    const abs = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listAllFiles(abs, base));
    else if (entry.isFile()) out.push(relative(base, abs));
  }
  return out;
}

export function computeSourceManifest(runtimeDir) {
  const files = {};
  for (const rel of listSourceFiles(runtimeDir)) {
    files[rel] = sha256File(join(runtimeDir, rel));
  }
  return {
    schema: "council-runtime.source-manifest/v1",
    excludes: [...SOURCE_EXCLUDES],
    files,
  };
}

export function verifySourceManifest(treeDir, manifest) {
  if (manifest?.schema !== "council-runtime.source-manifest/v1") {
    throw new Error("source integrity: unrecognized source manifest schema");
  }
  const live = computeSourceManifest(treeDir);
  const problems = [];
  for (const [rel, hash] of Object.entries(manifest.files ?? {})) {
    if (!(rel in live.files)) problems.push(`missing ${rel}`);
    else if (live.files[rel] !== hash) problems.push(`changed ${rel}`);
  }
  for (const rel of Object.keys(live.files)) {
    if (!(rel in (manifest.files ?? {}))) problems.push(`unexpected ${rel}`);
  }
  if (problems.length > 0) {
    throw new Error(
      `source integrity: ${problems.slice(0, 5).join("; ")}` +
        (problems.length > 5 ? ` (+${problems.length - 5} more)` : ""),
    );
  }
}

// Content-addressed release id: same source manifest -> same release -> no-op.
export function sourceReleaseId(manifest) {
  const sorted = {};
  for (const key of Object.keys(manifest.files).sort()) {
    sorted[key] = manifest.files[key];
  }
  return `rel-${sha256Json(sorted).slice(0, 16)}`;
}

// ---------------------------------------------------------------------------
// (a) exact-executable Node prerequisite probe
// ---------------------------------------------------------------------------

const PROBE_MARKERS = [
  "PROBE in-memory SQLite create/insert/read/close: OK",
  "PROBE persistent SQLite create/close/reopen: OK",
];

async function probeChildMain() {
  const { DatabaseSync } = await import("node:sqlite");

  // In-memory create/insert/read/close.
  const memory = new DatabaseSync(":memory:");
  try {
    memory.exec("CREATE TABLE council_runtime_probe (value INTEGER NOT NULL)");
    memory
      .prepare("INSERT INTO council_runtime_probe (value) VALUES (?)")
      .run(77);
    const row = memory
      .prepare("SELECT value FROM council_runtime_probe LIMIT 1")
      .get();
    if (row?.value !== 77) {
      throw new Error("node:sqlite in-memory probe did not round-trip 77");
    }
  } finally {
    memory.close();
  }
  console.log(PROBE_MARKERS[0]);

  // Isolated persistent create/close/reopen cycle.
  const scratch = mkdtempSync(join(tmpdir(), "council-runtime-sqlite-probe-"));
  try {
    const file = join(scratch, "probe.db");
    const first = new DatabaseSync(file);
    try {
      first.exec("CREATE TABLE probe_persist (value INTEGER NOT NULL)");
      first.prepare("INSERT INTO probe_persist (value) VALUES (?)").run(99);
    } finally {
      first.close();
    }
    const reopened = new DatabaseSync(file);
    try {
      const row = reopened.prepare("SELECT value FROM probe_persist LIMIT 1").get();
      if (row?.value !== 99) {
        throw new Error("persistent probe did not round-trip 99 after reopen");
      }
    } finally {
      reopened.close();
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
  console.log(PROBE_MARKERS[1]);
}

// Invoked through the resolved launcher executable (process.execPath), not a
// PATH `node` assumption. Runs before any install-tree write.
export function runPrerequisiteProbe() {
  const run = spawnSync(process.execPath, [SELF, "--probe-only"], {
    encoding: "utf8",
  });
  const output = `${run.stdout ?? ""}${run.stderr ?? ""}`;
  if (run.error) {
    throw new Error(
      `preflight: could not execute ${process.execPath} (${run.error.message})`,
    );
  }
  if (run.status !== 0) {
    throw new Error(
      `preflight: SQLite prerequisite probe failed in ${process.execPath} ` +
        `(exit ${run.status}): ${output.trim()}`,
    );
  }
  for (const marker of PROBE_MARKERS) {
    if (!output.includes(marker)) {
      throw new Error(
        `preflight: probe output missing marker "${marker}" from ${process.execPath}`,
      );
    }
  }
  return { executable: process.execPath, output };
}

// ---------------------------------------------------------------------------
// npm plumbing
// ---------------------------------------------------------------------------

const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";

function runNpm(npmArgs, cwd, label) {
  const run = spawnSync(npmCmd, npmArgs, { cwd, encoding: "utf8" });
  const output = `${run.stdout ?? ""}${run.stderr ?? ""}`;
  if (run.error) {
    throw new Error(`${label}: could not run npm (${run.error.message})`);
  }
  if (run.status !== 0) {
    throw new Error(
      `${label}: npm ${npmArgs.join(" ")} exited with status ${run.status}: ` +
        output.trim().slice(-2000),
    );
  }
}

function npmVersion() {
  const run = spawnSync(npmCmd, ["--version"], { encoding: "utf8" });
  return run.status === 0 ? run.stdout.trim() : "unknown";
}

// ---------------------------------------------------------------------------
// artifact receipt (d) — generated artifacts only (dist/**)
// ---------------------------------------------------------------------------

function collectStrings(value, out) {
  if (typeof value === "string") out.push(value);
  else if (value && typeof value === "object") {
    for (const inner of Object.values(value)) collectStrings(inner, out);
  }
  return out;
}

// Build products the package promises to expose: bin targets, main, and
// every exports target. All must exist after the build.
export function requiredArtifacts(pkg) {
  const rels = new Set();
  for (const raw of collectStrings(pkg.bin ?? {}, [])) {
    rels.add(raw.replace(/^\.\//, ""));
  }
  if (typeof pkg.main === "string") rels.add(pkg.main.replace(/^\.\//, ""));
  for (const raw of collectStrings(pkg.exports ?? {}, [])) {
    if (raw.startsWith("./")) rels.add(raw.slice(2));
  }
  return [...rels].sort();
}

export function verifyArtifactReceipt(releaseDir) {
  const receiptPath = join(releaseDir, "ARTIFACT-RECEIPT.json");
  if (!existsSync(receiptPath)) {
    throw new Error("artifact receipt: ARTIFACT-RECEIPT.json missing");
  }
  const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
  if (receipt.schema !== "council-runtime.artifact-receipt/v1") {
    throw new Error("artifact receipt: unrecognized receipt schema");
  }
  const distDir = join(releaseDir, "dist");
  const live = {};
  if (existsSync(distDir)) {
    for (const rel of listAllFiles(distDir)) {
      live[rel] = sha256File(join(distDir, rel));
    }
  }
  const problems = [];
  for (const [rel, hash] of Object.entries(receipt.artifacts ?? {})) {
    if (!(rel in live)) problems.push(`missing dist/${rel}`);
    else if (live[rel] !== hash) problems.push(`corrupt dist/${rel}`);
  }
  for (const rel of Object.keys(live)) {
    if (!(rel in (receipt.artifacts ?? {}))) problems.push(`unexpected dist/${rel}`);
  }
  if (problems.length > 0) {
    throw new Error(
      `artifact receipt: ${problems.slice(0, 5).join("; ")}` +
        (problems.length > 5 ? ` (+${problems.length - 5} more)` : ""),
    );
  }
  return receipt;
}

// Full pre-activation verification: source manifest AND artifact receipt.
export function verifyRelease(releaseDir) {
  const manifestPath = join(releaseDir, "SOURCE-MANIFEST.json");
  if (!existsSync(manifestPath)) {
    throw new Error("source integrity: SOURCE-MANIFEST.json missing");
  }
  verifySourceManifest(releaseDir, JSON.parse(readFileSync(manifestPath, "utf8")));
  verifyArtifactReceipt(releaseDir);
}

// ---------------------------------------------------------------------------
// (b) staged immutable install
// ---------------------------------------------------------------------------

export function stageRelease({ root, prefix, releaseId }) {
  const runtimeDir = join(root, "runtime");
  const pkg = JSON.parse(readFileSync(join(runtimeDir, "package.json"), "utf8"));
  const manifest = computeSourceManifest(runtimeDir);

  const staging = join(prefix, ".staging", releaseId);
  rmSync(staging, { recursive: true, force: true });
  mkdirSync(join(prefix, ".staging"), { recursive: true });
  try {
    cpSync(runtimeDir, staging, {
      recursive: true,
      filter: (src) => !SOURCE_EXCLUDES.includes(basename(src)),
    });
    writeFileSync(
      join(staging, "SOURCE-MANIFEST.json"),
      `${JSON.stringify({ ...manifest, releaseId }, null, 2)}\n`,
    );

    runNpm(["ci", "--no-audit", "--no-fund"], staging, "staged dependency install");
    runNpm(["run", "build"], staging, "staged runtime build");

    for (const rel of requiredArtifacts(pkg)) {
      if (!existsSync(join(staging, rel))) {
        throw new Error(`verification: required build product missing after build: ${rel}`);
      }
    }

    const distDir = join(staging, "dist");
    const artifacts = {};
    if (existsSync(distDir)) {
      for (const rel of listAllFiles(distDir)) {
        artifacts[rel] = sha256File(join(distDir, rel));
      }
    }
    if (Object.keys(artifacts).length === 0) {
      throw new Error("verification: build produced no dist artifacts");
    }

    const receipt = {
      schema: "council-runtime.artifact-receipt/v1",
      releaseId,
      builtAt: new Date().toISOString(),
      builtWith: {
        node: process.version,
        nodeExecutable: process.execPath,
        npm: npmVersion(),
      },
      artifacts,
    };
    writeFileSync(
      join(staging, "ARTIFACT-RECEIPT.json"),
      `${JSON.stringify(receipt, null, 2)}\n`,
    );

    // Independent verification pass: re-read the receipt from disk and
    // re-hash the artifacts before anything becomes active.
    verifyRelease(staging);

    const finalDir = join(prefix, "releases", releaseId);
    mkdirSync(join(prefix, "releases"), { recursive: true });
    renameSync(staging, finalDir); // immutable from here on
    return { releaseId, releaseDir: finalDir };
  } catch (error) {
    rmSync(staging, { recursive: true, force: true });
    throw error;
  }
}

// ---------------------------------------------------------------------------
// (e) atomic activation, receipt preservation, rollback instruction
// ---------------------------------------------------------------------------

function readCurrentReleaseId(prefix) {
  const current = join(prefix, "current");
  if (!existsSync(current)) return null;
  const target = readlinkSync(current);
  return basename(target);
}

function rollbackText({ prefix, releaseId, previousId }) {
  const lines = [
    "# Council runtime rollback",
    "",
    `Active release: ${releaseId}`,
    "",
  ];
  if (previousId && previousId !== releaseId) {
    lines.push(
      `Previous release preserved at: ${prefix}/releases/${previousId}`,
      `Previous receipt preserved at: ${prefix}/receipts/${previousId}.json`,
      "",
      "Roll back with:",
      "",
      `    node scripts/install-runtime.mjs --prefix ${prefix} --activate ${previousId}`,
      "",
      "or swap the symlink by hand:",
      "",
      `    ln -sfn releases/${previousId} ${prefix}/current`,
      "",
    );
  } else {
    lines.push("No previous release to roll back to.", "");
  }
  lines.push(
    "Durable user data lives in: " + join(prefix, "user-data"),
    "Release trees under releases/ are replaceable; user-data/ is never touched by installs.",
    "",
  );
  return lines.join("\n");
}

export function activateRelease({ prefix, releaseId }) {
  const releaseDir = join(prefix, "releases", releaseId);
  if (!existsSync(releaseDir)) {
    throw new Error(`activate: release ${releaseId} not found under ${prefix}`);
  }
  // Verification FIRST: a corrupt artifact or corrupt source refuses
  // activation and leaves the active release untouched.
  verifyRelease(releaseDir);

  mkdirSync(join(prefix, "receipts"), { recursive: true });
  copyFileSync(
    join(releaseDir, "ARTIFACT-RECEIPT.json"),
    join(prefix, "receipts", `${releaseId}.json`),
  );
  // Durable user data stays outside the replaceable release trees.
  mkdirSync(join(prefix, "user-data"), { recursive: true });

  const previousId = readCurrentReleaseId(prefix);
  writeFileSync(
    join(prefix, "ROLLBACK.md"),
    rollbackText({ prefix, releaseId, previousId }),
    "utf8",
  );

  // Atomic swap: build the symlink aside, then rename over `current`.
  const tmpLink = join(prefix, `.current-tmp-${process.pid}`);
  rmSync(tmpLink, { force: true });
  symlinkSync(join("releases", releaseId), tmpLink);
  renameSync(tmpLink, join(prefix, "current"));
  return { releaseId, previousId };
}

// ---------------------------------------------------------------------------
// (f) idempotent orchestration
// ---------------------------------------------------------------------------

function assertExactPins(pkg) {
  for (const section of ["dependencies", "devDependencies"]) {
    for (const [name, version] of Object.entries(pkg[section] ?? {})) {
      if (!/^\d+\.\d+\.\d+$/.test(version)) {
        throw new Error(
          `preflight: ${name} is not an exact pin in runtime/package.json ` +
            `(${section}: ${version})`,
        );
      }
    }
  }
}

export function runInstall({ root, prefix }) {
  const runtimeDir = join(root, "runtime");
  const pkgPath = join(runtimeDir, "package.json");
  if (!existsSync(pkgPath)) {
    throw new Error("preflight: runtime/package.json missing");
  }
  const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
  assertExactPins(pkg);

  const manifest = computeSourceManifest(runtimeDir);
  const releaseId = sourceReleaseId(manifest);
  const releaseDir = join(prefix, "releases", releaseId);

  if (existsSync(releaseDir)) {
    // Fail closed on tamper; never silently rebuild over a bad release.
    verifyRelease(releaseDir);
    if (readCurrentReleaseId(prefix) === releaseId) {
      return { releaseId, releaseDir, previousId: null, noop: true, reused: true };
    }
    const { previousId } = activateRelease({ prefix, releaseId });
    return { releaseId, releaseDir, previousId, noop: false, reused: true };
  }

  stageRelease({ root, prefix, releaseId });
  const { previousId } = activateRelease({ prefix, releaseId });
  return { releaseId, releaseDir, previousId, noop: false, reused: false };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function fail(message) {
  console.log(`FAIL ${message}`);
  process.exit(1);
}

function main() {
  const args = process.argv.slice(2);

  if (args.includes("--probe-only")) {
    probeChildMain()
      .then(() => process.exit(0))
      .catch((error) => {
        console.log(`FAIL ${error instanceof Error ? error.message : String(error)}`);
        process.exit(1);
      });
    return;
  }

  const rootIdx = args.indexOf("--root");
  const root =
    rootIdx >= 0
      ? resolve(args[rootIdx + 1])
      : resolve(dirname(SELF), "..");
  const prefixIdx = args.indexOf("--prefix");
  const prefix = resolve(
    prefixIdx >= 0
      ? args[prefixIdx + 1]
      : (process.env.COUNCIL_RUNTIME_RELEASE_PREFIX ??
          join(homedir(), ".blackceo", "council-runtime")),
  );

  // (a) Refuse unsupported Node before the probe and before any write.
  if (!isSupportedCouncilRuntimeNode(process.version)) {
    fail(
      `preflight: Council runtime requires Node.js ^22.13.0 || >=24 with ` +
        `node:sqlite; found ${process.version}`,
    );
  }

  // (a) Exact-executable probe; blocks before any file is written to the
  // install trees.
  let probe;
  try {
    probe = runPrerequisiteProbe();
  } catch (error) {
    fail(error instanceof Error ? error.message : String(error));
  }
  console.log(
    `PASS preflight: Node.js ${process.version} and in-memory SQLite ` +
      `read/write (${probe.executable})`,
  );

  const pkgPath = join(root, "runtime", "package.json");
  if (!existsSync(pkgPath)) {
    fail("preflight: runtime/package.json missing");
  }
  const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
  console.log(
    `INFO runtime package identity: ${pkg.name}@${pkg.version} (private=${pkg.private})`,
  );

  if (args.includes("--check-prereqs")) {
    console.log("RUNTIME-PREREQS: PASS (no installation performed)");
    process.exit(0);
  }

  const activateIdx = args.indexOf("--activate");
  try {
    if (activateIdx >= 0) {
      const releaseId = args[activateIdx + 1];
      const { previousId } = activateRelease({ prefix, releaseId });
      console.log(
        `INSTALL-RUNTIME: PASS (release ${releaseId} activated under ${prefix}` +
          (previousId ? `; previous release ${previousId} preserved` : "") +
          ")",
      );
      process.exit(0);
    }

    const result = runInstall({ root, prefix });
    if (result.noop) {
      console.log(
        `INSTALL-RUNTIME: NO-OP (release ${result.releaseId} already active ` +
          `at ${join(prefix, "current")})`,
      );
    } else {
      console.log(
        `INSTALL-RUNTIME: PASS (release ${result.releaseId} staged, verified, ` +
          `activated under ${prefix}` +
          (result.previousId
            ? `; previous release ${result.previousId} preserved, see ${join(prefix, "ROLLBACK.md")}`
            : "") +
          ")",
      );
    }
    process.exit(0);
  } catch (error) {
    fail(error instanceof Error ? error.message : String(error));
  }
}

const invokedDirectly =
  typeof process.argv[1] === "string" &&
  resolve(process.argv[1]) === resolve(SELF);
if (invokedDirectly) {
  main();
}
