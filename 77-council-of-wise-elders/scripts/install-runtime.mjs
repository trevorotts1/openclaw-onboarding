#!/usr/bin/env node
// Council of Wise Elders: canonical runtime installer (WER-004).
//
// Builds a usable runtime into an external release prefix through staged
// immutable releases with atomic activation, preserving the previous
// release until every stage verifies. Replaces the CWE-039 in-place
// installer contract: the source tree is never built in place, and
// durable user data never lives inside replaceable release trees.
//
// Stages (each gate must pass before the next writes anything):
//   1. Prerequisite probe on the RESOLVED launcher executable
//      (process.execPath, never a PATH lookup): in-memory node:sqlite
//      create/insert/read/close plus an isolated persistent
//      create/close/reopen cycle. Refuses Node 20 and other unsupported
//      lines before any file is written; accepts the tested Node 22.13+
//      and Node 24 line (engines: ^22.13.0 || >=24).
//   2. Staged install: copy protected SOURCE into a staging directory
//      (never node_modules, never dist), npm ci --no-audit --no-fund,
//      then npm run build. The active previous release is untouched.
//   3. Source integrity: canonical SHA-256 manifest hashes SOURCE only;
//      node_modules and dist can never enter it.
//   4. Generated-artifact receipt: independent of the source manifest,
//      records dist product hashes and the source manifest hash.
//   5. Atomic activation: rename staging into releases/<id>, then a
//      symlink swap. The old receipt is preserved and a rollback
//      instruction is printed.
//   6. Idempotence: when the active release already matches this
//      source, a repeated update is a no-op.
//
// Usage:
//   node install-runtime.mjs [--root <skill-folder>] [--prefix <dir>]
//        [--check-prereqs] [--force]
// Exit codes: 0 installed/no-op, 1 preflight/install/verify failure.
// Deferred (never claimed here): fresh-install, real-update and rollback
// execution on a live host belong to the installed checks of the
// release procedure.

import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { isSupportedCouncilRuntimeNode } from "./node-runtime-preflight.mjs";

export const DIST_PRODUCTS = ["dist/index.js", "dist/blackceo-council.mjs"];
const SOURCE_ROOTS = ["src", "scripts", "config", "schemas", "tests"];
const SOURCE_FILES = ["package.json", "package-lock.json", "tsconfig.json", "README.md"];
const SOURCE_EXCLUDE = new Set(["node_modules", "dist"]);

export function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

function hashFile(path) {
  return sha256(readFileSync(path));
}

function walkFiles(dir, acc) {
  for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walkFiles(full, acc);
    else if (entry.isFile()) acc.push(full);
  }
  return acc;
}

// Canonical source manifest. SOURCE ONLY: the walker skips node_modules
// and dist segments at every depth, so generated trees can never enter
// the canonical manifest even when they exist next to the source.
export function sourceManifest(baseDir) {
  const entries = [];
  for (const name of SOURCE_FILES) {
    const full = join(baseDir, name);
    if (existsSync(full) && statSync(full).isFile()) {
      entries.push({ path: name, sha256: hashFile(full) });
    }
  }
  for (const dirName of SOURCE_ROOTS) {
    const full = join(baseDir, dirName);
    if (!existsSync(full)) continue;
    for (const file of walkFiles(full, [])) {
      const rel = relative(baseDir, file).split("\\").join("/");
      if (rel.split("/").some((seg) => SOURCE_EXCLUDE.has(seg))) continue;
      entries.push({ path: rel, sha256: hashFile(file) });
    }
  }
  entries.sort((a, b) => a.path.localeCompare(b.path));
  const canonical = JSON.stringify({ version: 1, entries });
  return { entries, manifestSha256: sha256(canonical), canonical };
}

// Stage 1: exact-executable prerequisite probe. The child IS the resolved
// launcher executable (process.execPath); a PATH assumption is never used.
const PROBE_SRC = `
const { DatabaseSync } = require("node:sqlite");
const db = new DatabaseSync(":memory:");
db.exec("CREATE TABLE council_runtime_probe (value INTEGER NOT NULL)");
db.prepare("INSERT INTO council_runtime_probe (value) VALUES (?)").run(77);
const row = db.prepare("SELECT value FROM council_runtime_probe LIMIT 1").get();
db.close();
if (row?.value !== 77) throw new Error("in-memory probe did not round-trip 77");
const { mkdtempSync, rmSync } = require("node:fs");
const { join } = require("node:path");
const { tmpdir } = require("node:os");
const dir = mkdtempSync(join(tmpdir(), "council-sqlite-persist-"));
const file = join(dir, "probe.sqlite");
let w = new DatabaseSync(file);
w.exec("CREATE TABLE persisted (marker TEXT NOT NULL)");
w.prepare("INSERT INTO persisted (marker) VALUES (?)").run("wer004");
w.close();
w = null;
const r = new DatabaseSync(file);
const got = r.prepare("SELECT marker FROM persisted LIMIT 1").get();
r.close();
rmSync(dir, { recursive: true, force: true });
if (got?.marker !== "wer004") throw new Error("persistent reopen probe failed");
`;

export function runPrerequisiteProbe(execPath) {
  if (!isSupportedCouncilRuntimeNode(process.version)) {
    return {
      ok: false,
      reason: `Council runtime requires Node.js ^22.13.0 || >=24 with node:sqlite; found ${process.version}`,
    };
  }
  const result = spawnSync(execPath, ["-e", PROBE_SRC], { encoding: "utf8" });
  if (result.error) {
    return { ok: false, reason: `could not execute the resolved launcher ${execPath} (${result.error.message})` };
  }
  if (result.status !== 0) {
    return {
      ok: false,
      reason: `node:sqlite probe failed on the resolved executable ${execPath} (in-memory create/insert/read/close plus persistent create/close/reopen): ${result.stderr || `exit ${result.status}`}`,
    };
  }
  return { ok: true };
}

function copyTree(src, dest) {
  mkdirSync(dest, { recursive: true });
  for (const entry of readdirSync(src, { withFileTypes: true })) {
    const s = join(src, entry.name);
    const d = join(dest, entry.name);
    if (entry.isDirectory()) copyTree(s, d);
    else if (entry.isFile()) copyFileSync(s, d);
  }
}

function copySourceTree(from, to) {
  for (const name of SOURCE_FILES) {
    const src = join(from, name);
    if (existsSync(src)) copyFileSync(src, join(to, name));
  }
  for (const dirName of SOURCE_ROOTS) {
    const src = join(from, dirName);
    if (existsSync(src)) copyTree(src, join(to, dirName));
  }
}

function runNpm(cwd, npmArgs, label) {
  // npm resolves from the same directory as the resolved Node launcher,
  // not from a PATH assumption about which npm pairs with this Node.
  const npmName = process.platform === "win32" ? "npm.cmd" : "npm";
  const npmSibling = join(dirname(process.execPath), npmName);
  const npmExe = existsSync(npmSibling) ? npmSibling : npmName;
  console.log(`INFO ${label}: ${npmExe} ${npmArgs.join(" ")} (cwd: ${cwd})`);
  const result = spawnSync(npmExe, npmArgs, { cwd, stdio: "inherit" });
  if (result.error) return { ok: false, reason: `could not run npm (${result.error.message})` };
  if (result.status !== 0) return { ok: false, reason: `npm exited with status ${result.status}` };
  return { ok: true };
}

// Stage 3 gate: verify staged build products. An empty or truncated
// (corrupt) artifact fails here, before activation.
export function verifyDistProducts(dir) {
  for (const rel of DIST_PRODUCTS) {
    const full = join(dir, rel);
    if (!existsSync(full)) return { ok: false, reason: `runtime/${rel} missing after staged build` };
    if (statSync(full).size === 0) return { ok: false, reason: `runtime/${rel} is empty (corrupt build artifact)` };
  }
  return { ok: true };
}

// Stage 4: generated-artifact receipt, independent of the source manifest.
export function writeReceipt(dir, { releaseId, sourceManifestSha256, nodeVersion, npmCommands, stagedAt }) {
  const check = verifyDistProducts(dir);
  if (!check.ok) return { ok: false, reason: check.reason };
  const dist = {};
  for (const rel of DIST_PRODUCTS) dist[rel] = hashFile(join(dir, rel));
  const receipt = {
    kind: "council-runtime-release-receipt",
    version: 1,
    releaseId,
    sourceManifestSha256,
    nodeVersion,
    npmCommands,
    stagedAt,
    dist,
    dataLocation:
      "durable user data lives outside this replaceable release tree (council state is never inside the runtime tree)",
  };
  const serialized = JSON.stringify(receipt, null, 2);
  writeFileSync(join(dir, "release-receipt.json"), `${serialized}\n`);
  return { ok: true, receipt };
}

export function readReceipt(dir) {
  const path = join(dir, "release-receipt.json");
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

function releaseIdFromPath(releasesDir, dir) {
  const rel = relative(releasesDir, dir);
  return rel && !rel.startsWith("..") && !rel.startsWith("/") ? rel : null;
}

// Stage 5: atomic activation. staging is renamed into releases/<id> on the
// same filesystem (atomic), then the current symlink is swapped through a
// rename. The old receipt is preserved as <oldid>.receipt.json.bak and a
// rollback instruction is emitted.
export function activate(stagingDir, prefix, releaseId) {
  const releasesDir = join(prefix, "releases");
  mkdirSync(releasesDir, { recursive: true });
  const releaseDir = join(releasesDir, releaseId);
  if (existsSync(releaseDir)) return { ok: false, reason: `release id ${releaseId} already exists` };
  renameSync(stagingDir, releaseDir);

  const currentLink = join(prefix, "current");
  let oldReleaseId = null;
  if (existsSync(currentLink)) {
    try {
      const oldDir = realpathSync(currentLink);
      oldReleaseId = releaseIdFromPath(realpathSync(releasesDir), oldDir);
      const old = readReceipt(oldDir);
      if (old && oldReleaseId) {
        writeFileSync(join(releasesDir, `${oldReleaseId}.receipt.json.bak`), `${JSON.stringify(old, null, 2)}\n`);
      }
    } catch {
      oldReleaseId = null; // dangling/unreadable current link: replace it
    }
  }

  const tmpLink = join(prefix, `.current.tmp-${process.pid}`);
  try {
    unlinkSync(tmpLink);
  } catch {
    /* absent is fine */
  }
  symlinkSync(releaseDir, tmpLink);
  renameSync(tmpLink, currentLink);
  const rollback = oldReleaseId
    ? `ln -sfn ${JSON.stringify(join(releasesDir, oldReleaseId))} ${JSON.stringify(currentLink)}`
    : null;
  return { ok: true, oldReleaseId, rollback, releaseDir };
}

// Stage 6: idempotence. Same source manifest already active = no-op.
export function findActiveMatchingRelease(prefix, manifestSha256) {
  const currentLink = join(prefix, "current");
  if (!existsSync(currentLink)) return null;
  let activeDir;
  try {
    activeDir = realpathSync(currentLink);
  } catch {
    return null;
  }
  const receipt = readReceipt(activeDir);
  if (!receipt || receipt.sourceManifestSha256 !== manifestSha256) return null;
  return { receipt, activeDir };
}

export class InstallFailure extends Error {}

export async function main() {
  const args = process.argv.slice(2);
  function argValue(flag) {
    const i = args.indexOf(flag);
    return i >= 0 ? resolve(args[i + 1]) : undefined;
  }
  const root = argValue("--root") ?? resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const prefix =
    argValue("--prefix") ?? join(process.env.HOME || tmpdir(), ".openclaw", "council-of-wise-elders-runtime");
  const force = args.includes("--force");

  function fail(stage, reason) {
    throw new InstallFailure(`${stage}: ${reason}`);
  }

  // Stage 1 first: refuse before any file is written anywhere.
  const probe = runPrerequisiteProbe(process.execPath);
  if (!probe.ok) fail("probe", probe.reason);
  console.log(
    `PASS probe: resolved launcher ${process.execPath} (${process.version}) passed in-memory SQLite read/write plus persistent create/close/reopen probes`,
  );

  const runtimeDir = join(root, "runtime");
  if (!existsSync(join(runtimeDir, "package.json"))) fail("preflight", "runtime/package.json missing");
  const pkg = JSON.parse(readFileSync(join(runtimeDir, "package.json"), "utf8"));
  console.log(`INFO runtime package identity: ${pkg.name}@${pkg.version}`);

  if (args.includes("--check-prereqs")) {
    console.log("RUNTIME-PREREQS: PASS (no installation performed)");
    return;
  }

  const manifest = sourceManifest(runtimeDir);
  console.log(
    `INFO source integrity: ${manifest.entries.length} protected source files, manifest sha256 ${manifest.manifestSha256}`,
  );

  if (!force) {
    const active = findActiveMatchingRelease(prefix, manifest.manifestSha256);
    if (active) {
      console.log(
        `PASS idempotence: active release ${active.receipt.releaseId} already matches source manifest ${manifest.manifestSha256}; repeated update is a no-op`,
      );
      console.log("INSTALL-RUNTIME: PASS (no-op; already installed)");
      return;
    }
  }

  const stagedAt = new Date().toISOString().replace(/[:.]/g, "-");
  const releaseId = `${stagedAt}-${manifest.manifestSha256.slice(0, 12)}`;
  const stagingParent = join(prefix, "staging");
  mkdirSync(stagingParent, { recursive: true });
  const stagingDir = mkdtempSync(join(stagingParent, `stage-${releaseId}-`));
  let activated = false;
  try {
    console.log(`INFO stage: copying protected source into ${stagingDir}`);
    copySourceTree(runtimeDir, stagingDir);
    const stagedManifest = sourceManifest(stagingDir);
    if (stagedManifest.manifestSha256 !== manifest.manifestSha256) {
      fail("stage", "staged copy does not match the source manifest");
    }
    console.log("PASS stage: staged source matches the canonical manifest (no node_modules, no dist hashed)");

    const install = runNpm(stagingDir, ["ci", "--no-audit", "--no-fund"], "staged dependency install (npm ci)");
    if (!install.ok) fail("install", install.reason);
    console.log("PASS install: npm ci --no-audit --no-fund complete in staging");

    const build = runNpm(stagingDir, ["run", "build"], "staged runtime build");
    if (!build.ok) fail("build", build.reason);
    console.log("PASS build: npm run build complete in staging");

    const verified = verifyDistProducts(stagingDir);
    if (!verified.ok) fail("verify", verified.reason);
    console.log(`PASS verify: staged build products exist and are non-empty (${DIST_PRODUCTS.join(", ")})`);

    // Re-verify source integrity after the build: the canonical manifest
    // must be unchanged and still exclude generated trees.
    const postBuildManifest = sourceManifest(stagingDir);
    if (postBuildManifest.manifestSha256 !== manifest.manifestSha256) {
      fail("verify", "staged source tree changed during install/build");
    }

    writeFileSync(join(stagingDir, "source-manifest.json"), `${manifest.canonical}\n`);
    const receiptResult = writeReceipt(stagingDir, {
      releaseId,
      sourceManifestSha256: manifest.manifestSha256,
      nodeVersion: process.version,
      npmCommands: ["npm ci --no-audit --no-fund", "npm run build"],
      stagedAt,
    });
    if (!receiptResult.ok) fail("receipt", receiptResult.reason);
    console.log(`PASS receipt: release-receipt.json written (source manifest ${manifest.manifestSha256})`);

    const activation = activate(stagingDir, prefix, releaseId);
    if (!activation.ok) fail("activate", activation.reason);
    activated = true;
    console.log(`PASS activate: current -> releases/${releaseId}`);
    console.log(
      activation.oldReleaseId
        ? `INFO previous release preserved at releases/${activation.oldReleaseId}; old receipt at releases/${activation.oldReleaseId}.receipt.json.bak`
        : "INFO no previous release to preserve (fresh prefix)",
    );
    if (activation.rollback) console.log(`ROLLBACK: ${activation.rollback}`);
    console.log(
      "INSTALL-RUNTIME: PASS (staged immutable install, source integrity verified, receipt written, atomic activation complete)",
    );
  } finally {
    if (!activated) {
      // A failed or interrupted build discards the staged tree; the
      // previous release stays active and untouched.
      rmSync(stagingDir, { recursive: true, force: true });
      console.log("INFO staged partial install discarded; previous release untouched");
    }
  }
}

const invokedDirectly = import.meta.url === pathToFileURL(resolve(process.argv[1] ?? "")).href;
if (invokedDirectly) {
  try {
    await main();
    process.exit(0);
  } catch (error) {
    if (error instanceof InstallFailure) {
      console.log(`FAIL ${error.message}`);
      process.exit(1);
    }
    throw error;
  }
}