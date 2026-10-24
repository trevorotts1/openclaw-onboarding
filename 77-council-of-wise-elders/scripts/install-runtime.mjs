#!/usr/bin/env node
// Council of Wise Elders: runtime installer (WER-004 dependency-ready slice).
//
// This is the canonical installer named by INSTALL.md. It builds the runtime
// into an IMMUTABLE EXTERNAL RELEASE PREFIX instead of mutating the checked-out
// skill tree, and it activates a release only after every stage verifies.
//
// Pipeline:
//   1. Prerequisite probe through the EXACT resolved launcher executable:
//      report its own version, then run node:sqlite in-memory
//      create/insert/read/close plus an isolated persistent
//      create/close/reopen cycle. Nothing is written before this passes.
//   2. Source integrity: SHA-256 manifest over protected SOURCE only.
//      node_modules/ and dist/ are NEVER hashed into the source manifest.
//   3. Staged install into <prefix>/staging/: copy source, `npm ci
//      --no-audit --no-fund`, `npm run build`. The active release is untouched.
//   4. Independent generated-artifact receipt over dist/.
//   5. Verification of the staged artifact (sources + artifact bytes, plus a
//      load check of the real entry point: hash + load, never 'ready' from
//      SKILL.md presence or source match alone).
//   6. Atomic activation via an atomically replaced <prefix>/active.json.
//      The previous receipt is preserved and ROLLBACK.md is rewritten.
//   7. Idempotence: an identical source/artifact/node combination is a no-op.
//
// Durable user data lives in <prefix>/data (or --data-dir), never inside a
// replaceable release tree. This installer does not run migrations: the
// application that owns the store acquires its own migration/backup lock.
//
// Usage:
//   node install-runtime.mjs [options]
// Options:
//   --root <skill-folder>       skill folder containing runtime/ (default: ..)
//   --runtime-dir <dir>         explicit runtime source directory
//   --prefix <dir>              external release prefix (env COUNCIL_RUNTIME_PREFIX)
//   --data-dir <dir>            durable user data root (default <prefix>/data)
//   --node-executable <path>    exact launcher executable (default process.execPath)
//   --npm-executable <path>     npm launcher (default npm / npm.cmd on PATH)
//   --check-prereqs             probe only; never installs, never writes a release
//   --verify-release <dir>      verify an installed release against its receipts
//   --rollback                  atomically re-activate the previous release
//   --json                      emit a machine-readable result on stdout
// Exit codes: 0 installed / verified / no-op, 1 preflight or install failure.

import { spawnSync } from "node:child_process";
import {
  accessSync,
  constants as fsConstants,
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createHash, randomBytes } from "node:crypto";
import { homedir } from "node:os";
import { basename, dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SOURCE_RECEIPT_SCHEMA = "wise-elders.council-runtime-source/v1";
const ARTIFACT_RECEIPT_SCHEMA = "wise-elders.council-runtime-artifact/v1";
const RELEASE_RECEIPT_SCHEMA = "wise-elders.council-runtime-release/v1";
const ACTIVE_SCHEMA = "wise-elders.council-runtime-active/v1";

// Never hashed into the canonical SOURCE manifest, never copied into a release
// from the source tree. They are either installed (node_modules) or generated
// (dist) and are covered by the independent artifact receipt instead.
export const SOURCE_IGNORED_NAMES = new Set([
  "node_modules",
  "dist",
  ".git",
  ".cache",
  ".turbo",
  ".nyc_output",
  "coverage",
  ".DS_Store",
]);

export const ENTRY_ARTIFACT = "dist/blackceo-council.mjs";
export const REQUIRED_ARTIFACTS = ["dist/index.js", ENTRY_ARTIFACT];

const PROBE_TIMEOUT_MS = 60_000;
const NPM_TIMEOUT_MS = 15 * 60_000;

/** Accept the tested Node lines only: 22.13+ or 24+. Node 20 must refuse. */
export function isSupportedNodeVersion(version) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)/.exec(String(version));
  if (!match) return false;
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return (major === 22 && minor >= 13) || major >= 24;
}

export function parseArgs(argv) {
  const options = {
    root: resolve(dirname(fileURLToPath(import.meta.url)), ".."),
    runtimeDir: null,
    prefix: null,
    dataDir: null,
    nodeExecutable: process.execPath,
    npmExecutable: process.platform === "win32" ? "npm.cmd" : "npm",
    checkPrereqs: false,
    verifyRelease: null,
    rollback: false,
    json: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const take = (name) => {
      const value = argv[i + 1];
      if (!value || value.startsWith("--")) {
        throw new Error(`${name} requires a value`);
      }
      i += 1;
      return value;
    };
    switch (arg) {
      case "--root": options.root = resolve(take(arg)); break;
      case "--runtime-dir": options.runtimeDir = resolve(take(arg)); break;
      case "--prefix": options.prefix = resolve(take(arg)); break;
      case "--data-dir": options.dataDir = resolve(take(arg)); break;
      case "--node-executable": options.nodeExecutable = take(arg); break;
      case "--npm-executable": options.npmExecutable = take(arg); break;
      case "--check-prereqs": options.checkPrereqs = true; break;
      case "--verify-release": options.verifyRelease = resolve(take(arg)); break;
      case "--rollback": options.rollback = true; break;
      case "--json": options.json = true; break;
      case "--idempotent": break; // updater parity; idempotence is always on
      case "--help":
      case "-h":
        options.help = true;
        break;
      default:
        throw new Error(`unknown option: ${arg}`);
    }
  }
  options.runtimeDir = options.runtimeDir ?? join(options.root, "runtime");
  return options;
}

/** Resolve the exact executable, not a PATH lookup. */
export function resolveExecutable(candidate) {
  if (!candidate) throw new Error("no executable supplied");
  let real;
  try {
    real = realpathSync(candidate);
  } catch (error) {
    throw new Error(`cannot resolve executable ${candidate}: ${error.message}`);
  }
  const stat = statSync(real);
  if (!stat.isFile()) throw new Error(`not a regular file: ${real}`);
  if (process.platform !== "win32") {
    accessSync(real, fsConstants.X_OK);
  }
  return real;
}

export function isInside(candidate, parent) {
  const rel = relative(resolve(parent), resolve(candidate));
  return rel === "" || (!rel.startsWith(`..${sep}`) && rel !== ".." && !rel.startsWith(sep));
}

export function defaultPrefix() {
  if (process.env.COUNCIL_RUNTIME_PREFIX) {
    return resolve(process.env.COUNCIL_RUNTIME_PREFIX);
  }
  if (process.platform === "win32") {
    return join(process.env.LOCALAPPDATA || homedir(), "blackceo", "council-runtime");
  }
  return join(homedir(), ".local", "share", "blackceo", "council-runtime");
}

// Runs in the child process started with the RESOLVED executable. It must not
// write anything except its own isolated temp database.
const SQLITE_PROBE_SOURCE = `
const assert = (await import("node:assert/strict")).default;
const { mkdtempSync, rmSync } = await import("node:fs");
const { tmpdir } = await import("node:os");
const { join } = await import("node:path");
const { DatabaseSync } = await import("node:sqlite");

// 1. In-memory create / insert / read / close.
const memory = new DatabaseSync(":memory:");
memory.exec("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)");
memory.prepare("INSERT INTO probe (value) VALUES (?)").run("council-sqlite-ok");
assert.equal(memory.prepare("SELECT value FROM probe").get().value, "council-sqlite-ok");
memory.close();

// 2. Isolated persistent create / close / reopen / read / close.
const probeDir = mkdtempSync(join(tmpdir(), "council-sqlite-probe-"));
try {
  const file = join(probeDir, "probe.sqlite");
  const first = new DatabaseSync(file);
  first.exec("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)");
  first.prepare("INSERT INTO probe (value) VALUES (?)").run("persistent-ok");
  first.close();
  const reopened = new DatabaseSync(file);
  assert.equal(reopened.prepare("SELECT value FROM probe").get().value, "persistent-ok");
  reopened.close();
} finally {
  rmSync(probeDir, { recursive: true, force: true });
}
console.log("COUNCIL-SQLITE-PROBE: PASS");
`;

/**
 * Probe the exact executable: its own reported version plus node:sqlite
 * in-memory and persistent reopen cycles. Throws before any install write.
 */
export function probeRuntime(nodeExecutable) {
  const executable = resolveExecutable(nodeExecutable);

  const versionRun = spawnSync(executable, ["--version"], {
    encoding: "utf8",
    timeout: PROBE_TIMEOUT_MS,
  });
  if (versionRun.error) {
    throw new Error(`could not run ${executable} --version: ${versionRun.error.message}`);
  }
  if (versionRun.status !== 0) {
    throw new Error(`${executable} --version exited ${versionRun.status}: ${(versionRun.stderr || "").trim()}`);
  }
  const version = `${versionRun.stdout || ""}`.trim();
  if (!isSupportedNodeVersion(version)) {
    throw new Error(
      `Council runtime requires Node.js ^22.13.0 || >=24 with node:sqlite; ` +
      `the resolved executable ${executable} reports ${version || "(no version)"}`
    );
  }

  const sqliteRun = spawnSync(
    executable,
    ["--input-type=module", "-e", SQLITE_PROBE_SOURCE],
    { encoding: "utf8", timeout: PROBE_TIMEOUT_MS }
  );
  if (sqliteRun.error) {
    throw new Error(`node:sqlite probe could not start under ${executable}: ${sqliteRun.error.message}`);
  }
  if (sqliteRun.status !== 0) {
    throw new Error(
      `node:sqlite in-memory/persistent probe failed under ${executable} ` +
      `(exit ${sqliteRun.status}): ${(sqliteRun.stderr || sqliteRun.stdout || "").trim()}`
    );
  }
  if (!/COUNCIL-SQLITE-PROBE: PASS/.test(sqliteRun.stdout || "")) {
    throw new Error(`node:sqlite probe produced no PASS marker under ${executable}`);
  }
  return { executable, version };
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function canonicalDigest(entries) {
  return createHash("sha256").update(JSON.stringify(entries)).digest("hex");
}

/**
 * Walk `sourceDir` and hash protected SOURCE only. node_modules and dist are
 * excluded by name at every level; they are covered by the artifact receipt.
 */
export function computeSourceManifest(sourceDir) {
  const entries = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      if (SOURCE_IGNORED_NAMES.has(name)) continue;
      const full = join(dir, name);
      const stat = lstatSync(full);
      if (stat.isSymbolicLink()) {
        const target = readlinkSync(full);
        entries.push({
          path: relative(sourceDir, full).split(sep).join("/"),
          kind: "symlink",
          sha256: createHash("sha256").update(target).digest("hex"),
          size: Buffer.byteLength(target),
        });
      } else if (stat.isDirectory()) {
        walk(full);
      } else if (stat.isFile()) {
        entries.push({
          path: relative(sourceDir, full).split(sep).join("/"),
          kind: "file",
          sha256: sha256File(full),
          size: stat.size,
        });
      }
    }
  };
  walk(sourceDir);
  entries.sort((a, b) => a.path.localeCompare(b.path));
  return { entries, digest: canonicalDigest(entries), fileCount: entries.length };
}

/** Hash every generated file under dist/ into an independent receipt. */
export function computeArtifactManifest(releaseDir) {
  const distDir = join(releaseDir, "dist");
  if (!existsSync(distDir)) {
    throw new Error(`generated artifact directory missing: ${distDir}`);
  }
  const entries = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      const full = join(dir, name);
      const stat = lstatSync(full);
      if (stat.isDirectory()) {
        walk(full);
      } else if (stat.isFile()) {
        entries.push({
          path: relative(releaseDir, full).split(sep).join("/"),
          sha256: sha256File(full),
          size: stat.size,
        });
      }
    }
  };
  walk(distDir);
  entries.sort((a, b) => a.path.localeCompare(b.path));
  for (const required of REQUIRED_ARTIFACTS) {
    if (!entries.some((entry) => entry.path === required)) {
      throw new Error(`required build product missing: ${required}`);
    }
  }
  return { entries, digest: canonicalDigest(entries), fileCount: entries.length };
}

/**
 * Parse-level load check of the real entry point (the byte hash is covered by
 * the artifact receipt). The installer is never 'ready' from source match or
 * SKILL.md presence alone: the installed entry must actually load.
 */
export function verifyEntryLoad(nodeExecutable, entryPath) {
  const run = spawnSync(nodeExecutable, ["--check", entryPath], {
    encoding: "utf8",
    timeout: PROBE_TIMEOUT_MS,
  });
  if (run.error) {
    throw new Error(`entry load check could not start under ${nodeExecutable}: ${run.error.message}`);
  }
  if (run.status !== 0) {
    throw new Error(
      `entry load check failed for ${entryPath} (exit ${run.status}): ${(run.stderr || run.stdout || "").trim()}`
    );
  }
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

export function receiptPaths(prefix, releaseId) {
  return {
    source: join(prefix, "receipts", `${releaseId}.source.json`),
    artifact: join(prefix, "receipts", `${releaseId}.artifact.json`),
    release: join(prefix, "receipts", `${releaseId}.release.json`),
    ...activePaths(prefix),
  };
}

export function activePaths(prefix) {
  return {
    active: join(prefix, "active.json"),
    previousActive: join(prefix, "previous-active.json"),
    rollback: join(prefix, "ROLLBACK.md"),
  };
}

/**
 * Verify a release tree against its receipts. Corruption or drift fails.
 * The actual entry point is hash-covered by the artifact receipt AND load
 * checked here, so a known-broken bundle never verifies as healthy. Never
 * touches the active pointer.
 */
export function verifyRelease(prefix, releaseDir, nodeExecutable = process.execPath) {
  const releaseId = basename(resolve(releaseDir));
  const paths = receiptPaths(prefix, releaseId);
  const problems = [];
  if (!existsSync(releaseDir)) problems.push(`release directory missing: ${releaseDir}`);
  if (!existsSync(paths.source)) problems.push(`source receipt missing: ${paths.source}`);
  if (!existsSync(paths.artifact)) problems.push(`artifact receipt missing: ${paths.artifact}`);
  if (problems.length > 0) return { ok: false, releaseId, problems };

  const sourceReceipt = readJson(paths.source);
  const artifactReceipt = readJson(paths.artifact);
  try {
    const current = computeSourceManifest(releaseDir);
    if (current.digest !== sourceReceipt.digest) {
      problems.push(`source integrity mismatch: receipt ${sourceReceipt.digest} != actual ${current.digest}`);
    }
  } catch (error) {
    problems.push(`source verification failed: ${error.message}`);
  }
  try {
    const current = computeArtifactManifest(releaseDir);
    if (current.digest !== artifactReceipt.digest) {
      problems.push(`artifact integrity mismatch: receipt ${artifactReceipt.digest} != actual ${current.digest}`);
    }
    const expected = new Map(artifactReceipt.entries.map((entry) => [entry.path, entry.sha256]));
    for (const entry of current.entries) {
      const expectedHash = expected.get(entry.path);
      if (!expectedHash) {
        problems.push(`unexpected generated file: ${entry.path}`);
      } else if (expectedHash !== entry.sha256) {
        problems.push(`corrupt generated file: ${entry.path}`);
      }
    }
    for (const entry of artifactReceipt.entries) {
      if (!current.entries.some((actual) => actual.path === entry.path)) {
        problems.push(`generated file missing: ${entry.path}`);
      }
    }
  } catch (error) {
    problems.push(`artifact verification failed: ${error.message}`);
  }
  try {
    const entryPath = join(releaseDir, ...ENTRY_ARTIFACT.split("/"));
    if (!existsSync(entryPath)) {
      problems.push(`entry point missing: ${ENTRY_ARTIFACT}`);
    } else {
      verifyEntryLoad(nodeExecutable, entryPath);
    }
  } catch (error) {
    problems.push(`entry load check failed: ${error.message}`);
  }
  return { ok: problems.length === 0, releaseId, problems };
}

function writeJsonAtomic(path, value) {
  const tempPath = `${path}.tmp-${process.pid}-${randomBytes(4).toString("hex")}`;
  writeFileSync(tempPath, `${JSON.stringify(value, null, 2)}\n`);
  renameSync(tempPath, path);
}

function runStep(command, args, cwd, label) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    timeout: NPM_TIMEOUT_MS,
    env: process.env,
  });
  if (result.error) {
    throw new Error(`${label}: could not run ${command}: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const output = `${result.stdout || ""}${result.stderr || ""}`.trim();
    throw new Error(`${label}: ${command} exited ${result.status}${output ? `: ${output}` : ""}`);
  }
  return result;
}

function validatePinnedDependencies(pkg) {
  const pins = [];
  for (const section of ["dependencies", "devDependencies"]) {
    for (const [name, version] of Object.entries(pkg[section] ?? {})) {
      if (!/^\d+\.\d+\.\d+$/.test(version)) {
        throw new Error(`${name} is not an exact pin in runtime/package.json (${section}: ${version})`);
      }
      pins.push(`${name}@${version}`);
    }
  }
  pins.sort();
  return pins;
}

function writeRollbackInstructions(prefix, active) {
  const installer = fileURLToPath(import.meta.url);
  const previous = active.previousReleaseId || "(none)";
  const lines = [
    "# Council runtime rollback",
    "",
    `Active release: \`${active.releaseId}\``,
    `Previous release: \`${previous}\``,
    `Prefix: \`${prefix}\``,
    "",
    "## Automated rollback",
    "",
    "```bash",
    `node ${JSON.stringify(installer)} --prefix ${JSON.stringify(prefix)} --rollback`,
    "```",
    "",
    "This atomically re-points `active.json` at the previous verified release and",
    "preserves the current receipt. Durable user data in the data directory is",
    "never touched.",
    "",
    "## Manual rollback",
    "",
    `Restore \`${join(prefix, "previous-active.json")}\` over \`${join(prefix, "active.json")}\`.`,
    "Both files are written atomically by this installer; a manual copy is the",
    "last resort if the installer is unavailable.",
    "",
    "## Limits",
    "",
    "A rollback re-points the executable. It does NOT downgrade or reverse a",
    "schema migration. If a release applied a destructive migration, restore the",
    "database backup taken by the owning application before that migration; the",
    "application that owns the store, not this installer, applies migrations.",
    "",
  ];
  writeFileSync(join(prefix, "ROLLBACK.md"), lines.join("\n"));
}

function activate(prefix, releaseId, releaseDir, sourceManifest, artifactReceipt, probe, dataDir) {
  const paths = receiptPaths(prefix, releaseId);
  const previous = existsSync(paths.active) ? readJson(paths.active) : null;
  if (previous) {
    writeJsonAtomic(paths.previousActive, previous);
  }
  const active = {
    schema: ACTIVE_SCHEMA,
    releaseId,
    releasePath: releaseDir,
    receiptPath: paths.release,
    sourceManifestDigest: sourceManifest.digest,
    artifactDigest: artifactReceipt.digest,
    nodeExecutable: probe.executable,
    nodeVersion: probe.version,
    platform: process.platform,
    arch: process.arch,
    dataDir,
    activatedAt: new Date().toISOString(),
    previousReleaseId: previous?.releaseId ?? null,
  };
  writeJsonAtomic(paths.active, active);
  writeRollbackInstructions(prefix, active);
  return active;
}

function formatError(error) {
  return error instanceof Error ? error.message : String(error);
}

export async function main(argv) {
  let options;
  try {
    options = parseArgs(argv);
  } catch (error) {
    console.log(`FAIL ${formatError(error)}`);
    return 1;
  }
  if (options.help) {
    console.log([
      "Usage: node install-runtime.mjs [options]",
      "  --root <skill-folder>     skill folder containing runtime/ (default: ..)",
      "  --runtime-dir <dir>       explicit runtime source directory",
      "  --prefix <dir>            external release prefix (env COUNCIL_RUNTIME_PREFIX)",
      "  --data-dir <dir>          durable user data root (default <prefix>/data)",
      "  --node-executable <path>  exact launcher executable (default process.execPath)",
      "  --npm-executable <path>   npm launcher (default npm on PATH)",
      "  --check-prereqs           probe only; installs nothing",
      "  --verify-release <dir>    verify an installed release against its receipts",
      "  --rollback                re-activate the previous verified release",
      "  --json                    emit a machine-readable result",
    ].join("\n"));
    return 0;
  }

  const runtimeDir = options.runtimeDir;
  const prefix = resolve(options.prefix ?? defaultPrefix());

  // ---- 1. Prerequisite probe. Nothing is written before this passes. ----
  let probe;
  try {
    probe = probeRuntime(options.nodeExecutable);
  } catch (error) {
    console.log(`FAIL preflight: ${formatError(error)}`);
    return 1;
  }
  console.log(`PASS preflight: ${probe.version} with in-memory SQLite read/write and persistent reopen (${probe.executable})`);

  // Guard: the release prefix and data dir must be external, replaceable trees.
  if (isInside(prefix, runtimeDir)) {
    console.log(`FAIL preflight: release prefix ${prefix} must live outside the runtime source tree ${runtimeDir}`);
    return 1;
  }
  const dataDir = resolve(options.dataDir ?? join(prefix, "data"));
  if (isInside(dataDir, join(prefix, "releases")) || isInside(dataDir, runtimeDir)) {
    console.log(`FAIL preflight: durable data ${dataDir} must live outside replaceable release trees`);
    return 1;
  }

  // ---- 2. Runtime package identity and exact pins ----
  const pkgPath = join(runtimeDir, "package.json");
  if (!existsSync(pkgPath)) {
    console.log(`FAIL preflight: runtime/package.json missing at ${pkgPath}`);
    return 1;
  }
  let pkg;
  try {
    pkg = readJson(pkgPath);
    validatePinnedDependencies(pkg);
  } catch (error) {
    console.log(`FAIL preflight: ${formatError(error)}`);
    return 1;
  }
  console.log(`INFO runtime package identity: ${pkg.name}@${pkg.version} (private=${pkg.private}, engines=${pkg.engines?.node ?? "unset"})`);

  if (options.checkPrereqs) {
    console.log("RUNTIME-PREREQS: PASS (no installation performed)");
    return 0;
  }

  // ---- Verify an existing release without activating anything ----
  if (options.verifyRelease) {
    const result = verifyRelease(prefix, options.verifyRelease, probe.executable);
    if (!result.ok) {
      console.log(`FAIL verify-release: ${result.problems.join("; ")}`);
      return 1;
    }
    console.log(`PASS verify-release: ${result.releaseId}`);
    return 0;
  }

  const paths = activePaths(prefix);
  const activePath = paths.active;

  // ---- Rollback: re-point the active receipt at the previous verified release ----
  if (options.rollback) {
    if (!existsSync(activePath)) {
      console.log(`FAIL rollback: no active release receipt at ${activePath}`);
      return 1;
    }
    const current = readJson(activePath);
    if (!current.previousReleaseId) {
      console.log("FAIL rollback: active receipt records no previous release");
      return 1;
    }
    const previousDir = join(prefix, "releases", current.previousReleaseId);
    const checked = verifyRelease(prefix, previousDir, probe.executable);
    if (!checked.ok) {
      console.log(`FAIL rollback: previous release is not usable: ${checked.problems.join("; ")}`);
      return 1;
    }
    const previousRelease = readJson(receiptPaths(prefix, current.previousReleaseId).release);
    writeJsonAtomic(paths.previousActive, current);
    const rolledBack = {
      ...previousRelease.active,
      activatedAt: new Date().toISOString(),
      previousReleaseId: current.releaseId,
    };
    writeJsonAtomic(activePath, rolledBack);
    writeRollbackInstructions(prefix, rolledBack);
    console.log(`PASS rollback: active release is now ${rolledBack.releaseId} (previous ${current.releaseId} preserved)`);
    return 0;
  }

  // ---- 3. Source integrity over protected source only ----
  let sourceManifest;
  try {
    sourceManifest = computeSourceManifest(runtimeDir);
  } catch (error) {
    console.log(`FAIL source-integrity: ${formatError(error)}`);
    return 1;
  }
  console.log(`INFO source manifest: ${sourceManifest.fileCount} protected file(s), sha256 ${sourceManifest.digest} (node_modules/dist excluded)`);

  const releaseId = `rel-${sourceManifest.digest.slice(0, 12)}`;

  // The installed bundle (<prefix>/releases/<id>/dist/blackceo-council.mjs)
  // has no SKILL.md, advisors/ or manifest.json above it. Its dispatcher
  // reads '../../install-record.json', which from there is
  // <prefix>/releases/install-record.json: record the skill folder it was
  // built from. Written before the idempotence check so a re-run heals a
  // prefix installed without it. Outside every release tree, so receipts
  // and integrity digests are unaffected.
  try {
    mkdirSync(join(prefix, "releases"), { recursive: true });
    writeJsonAtomic(join(prefix, "releases", "install-record.json"), { skill_dir: dirname(runtimeDir) });
  } catch (error) {
    console.log(`FAIL install-record: ${formatError(error)}`);
    return 1;
  }

  // ---- 4. Idempotence: identical, verified, active release is a no-op ----
  if (existsSync(activePath)) {
    try {
      const active = readJson(activePath);
      const sameSource = active.sourceManifestDigest === sourceManifest.digest;
      const sameNode = active.nodeExecutable === probe.executable && active.nodeVersion === probe.version;
      if (sameSource && sameNode && existsSync(active.releasePath)) {
        const checked = verifyRelease(prefix, active.releasePath, probe.executable);
        if (checked.ok) {
          console.log(`NOOP: release ${active.releaseId} already matches ${sourceManifest.digest} and verifies; nothing changed`);
          return 0;
        }
        console.log(`INFO active release failed verification (${checked.problems.join("; ")}); rebuilding`);
      }
    } catch (error) {
      console.log(`INFO active receipt unreadable (${formatError(error)}); rebuilding`);
    }
  }

  const releasesDir = join(prefix, "releases");
  const receiptsDir = join(prefix, "receipts");
  const stagingDir = join(prefix, "staging");
  const finalDir = join(releasesDir, releaseId);

  // Refuse to reuse a release id that is currently active.
  if (existsSync(activePath)) {
    const active = readJson(activePath);
    if (active.releaseId === releaseId && existsSync(finalDir)) {
      const checked = verifyRelease(prefix, finalDir, probe.executable);
      if (checked.ok) {
        console.log(`NOOP: release ${releaseId} is active and verifies; nothing changed`);
        return 0;
      }
    }
  }

  // ---- 5. Stage. The active release is untouched from here on. ----
  let stageDir = null;
  try {
    mkdirSync(stagingDir, { recursive: true });
    mkdirSync(releasesDir, { recursive: true });
    mkdirSync(receiptsDir, { recursive: true });
    mkdirSync(dataDir, { recursive: true });
    stageDir = join(stagingDir, `${releaseId}-${process.pid}-${randomBytes(4).toString("hex")}`);
    cpSync(runtimeDir, stageDir, {
      recursive: true,
      dereference: false,
      filter: (src) => !SOURCE_IGNORED_NAMES.has(basename(src)),
    });
    console.log(`INFO staged source at ${stageDir}`);

    runStep(options.npmExecutable, ["ci", "--no-audit", "--no-fund"], stageDir, "dependency install (npm ci)");
    console.log("PASS dependency install (npm ci)");
    runStep(options.npmExecutable, ["run", "build"], stageDir, "runtime build (npm run build)");
    console.log("PASS runtime build (npm run build)");

    // ---- 6. Independent generated-artifact receipt ----
    const artifactReceipt = {
      schema: ARTIFACT_RECEIPT_SCHEMA,
      releaseId,
      sourceManifestDigest: sourceManifest.digest,
      package: { name: pkg.name, version: pkg.version },
      builtAt: new Date().toISOString(),
      node: { executable: probe.executable, version: probe.version },
      platform: process.platform,
      arch: process.arch,
      ...computeArtifactManifest(stageDir),
    };
    console.log(`PASS artifact receipt: ${artifactReceipt.fileCount} generated file(s), sha256 ${artifactReceipt.digest}`);

    // ---- 7. Move into place, write receipts, verify, then activate ----
    rmSync(finalDir, { recursive: true, force: true });
    renameSync(stageDir, finalDir);
    stageDir = null;

    const sourceReceipt = {
      schema: SOURCE_RECEIPT_SCHEMA,
      releaseId,
      createdAt: new Date().toISOString(),
      sourceDir: runtimeDir,
      exclusions: [...SOURCE_IGNORED_NAMES].sort(),
      ...sourceManifest,
    };
    writeJsonAtomic(receiptPaths(prefix, releaseId).source, sourceReceipt);
    writeJsonAtomic(receiptPaths(prefix, releaseId).artifact, artifactReceipt);

    const checked = verifyRelease(prefix, finalDir, probe.executable);
    if (!checked.ok) {
      throw new Error(`staged release failed verification without activation: ${checked.problems.join("; ")}`);
    }

    const active = activate(prefix, releaseId, finalDir, sourceManifest, artifactReceipt, probe, dataDir);
    writeJsonAtomic(receiptPaths(prefix, releaseId).release, {
      schema: RELEASE_RECEIPT_SCHEMA,
      releaseId,
      sourceManifestDigest: sourceManifest.digest,
      artifactDigest: artifactReceipt.digest,
      dataDir,
      active,
    });

    console.log(`PASS activation: active.json now points at ${releaseId}`);
    if (active.previousReleaseId) {
      console.log(`INFO previous release ${active.previousReleaseId} preserved with its receipt; see ${join(prefix, "ROLLBACK.md")}`);
    }
    console.log(`INFO durable data directory: ${dataDir} (outside replaceable release trees)`);
    console.log("INSTALL-RUNTIME: PASS (staged immutable install, artifact receipt, atomic activation)");

    if (options.json) {
      console.log(JSON.stringify({
        status: "activated",
        releaseId,
        sourceManifestDigest: sourceManifest.digest,
        artifactDigest: artifactReceipt.digest,
        activePath: activePath,
        dataDir,
      }));
    }
    return 0;
  } catch (error) {
    if (stageDir) {
      rmSync(stageDir, { recursive: true, force: true });
    }
    console.log(`FAIL install: ${formatError(error)}`);
    if (existsSync(activePath)) {
      const active = readJson(activePath);
      console.log(`INFO previous release ${active.releaseId} is unchanged and still active at ${active.releasePath}`);
    } else {
      console.log("INFO no release was activated");
    }
    console.log("INSTALL-RUNTIME: DEGRADED install incomplete (previous files preserved; never report this state as ready). Fix the error above and re-run.");
    return 1;
  }
}

const invokedDirectly = (() => {
  const entry = process.argv[1];
  if (!entry) return false;
  const self = fileURLToPath(import.meta.url);
  try {
    return realpathSync(entry) === realpathSync(self);
  } catch {
    return resolve(entry) === resolve(self);
  }
})();

if (invokedDirectly) {
  process.exit(await main(process.argv.slice(2)));
}
