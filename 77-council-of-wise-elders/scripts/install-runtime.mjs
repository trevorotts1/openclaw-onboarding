#!/usr/bin/env node
// Council of Wise Elders: runtime installer (CWE-039 final packaging).
//
// This script performs the real isolated install documented in
// INSTALL.md Step 4. D6 decision record: the scaffold-era version of
// this script exited 3 in both branches and installed nothing. It is
// RECONCILED with the real install path rather than retired, because
// the doctor layout inventory requires this script to exist and
// INSTALL.md names it as the install entry point.
//
// Behavior:
//   1. Preflight: Node.js must satisfy the engines range declared in
//      runtime/package.json.
//   2. The pinned package set is derived from runtime/package.json
//      (dependencies plus devDependencies). Every version must be an
//      exact pin; a range value fails the install before anything runs.
//   3. npm install --no-save with those exact pins runs inside
//      runtime/ only, so neither package.json nor package-lock.json is
//      rewritten and nothing is installed globally or into another
//      skill's tree.
//   4. npm run build compiles the runtime (tsc) and bundles the CLI
//      (esbuild) into runtime/dist/.
//   5. The build products are verified to exist.
// Usage: node install-runtime.mjs [--root <skill-folder>]
// Exit codes: 0 installed and built, 1 preflight or install failure.

import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const rootIdx = args.indexOf("--root");
const root = rootIdx >= 0
  ? resolve(args[rootIdx + 1])
  : resolve(dirname(fileURLToPath(import.meta.url)), "..");
const runtimeDir = join(root, "runtime");

function fail(message) {
  console.log(`FAIL ${message}`);
  process.exit(1);
}

// 1. Node preflight against the runtime package's declared engines.
const [major, minor] = process.versions.node.split(".").map(Number);
const enginesOk =
  (major === 20 && minor >= 19) ||
  (major === 22 && minor >= 13) ||
  major >= 24;
if (!enginesOk) {
  fail(`preflight: Node.js ^20.19.0 || ^22.13.0 || >=24 required, found ${process.version}`);
}
console.log(`PASS preflight: Node.js ${process.version}`);

// 2. Read the runtime package and derive the exact pinned package set.
const pkgPath = join(runtimeDir, "package.json");
if (!existsSync(pkgPath)) {
  fail("preflight: runtime/package.json missing");
}
const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
console.log(`INFO runtime package identity: ${pkg.name}@${pkg.version} (private=${pkg.private})`);

const pins = [];
for (const section of ["dependencies", "devDependencies"]) {
  for (const [name, version] of Object.entries(pkg[section] ?? {})) {
    if (!/^\d+\.\d+\.\d+$/.test(version)) {
      fail(`preflight: ${name} is not an exact pin in runtime/package.json (${section}: ${version})`);
    }
    pins.push(`${name}@${version}`);
  }
}
pins.sort();
console.log(`INFO pinned package set (${pins.length}): ${pins.join(", ")}`);

// 3. Isolated pinned install inside runtime/ only.
const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
function runNpm(npmArgs, label) {
  console.log(`INFO ${label}: npm ${npmArgs.join(" ")} (cwd: runtime/)`);
  const result = spawnSync(npmCmd, npmArgs, { cwd: runtimeDir, stdio: "inherit" });
  if (result.error) {
    fail(`${label}: could not run npm (${result.error.message})`);
  }
  if (result.status !== 0) {
    fail(`${label}: npm exited with status ${result.status}`);
  }
  console.log(`PASS ${label}`);
}

runNpm(
  ["install", "--no-save", "--no-audit", "--no-fund", ...pins],
  "isolated dependency install"
);

// 4. Build the runtime in place.
runNpm(["run", "build"], "runtime build");

// 5. Verify the build products.
for (const rel of ["dist/index.js", "dist/blackceo-council.mjs"]) {
  if (!existsSync(join(runtimeDir, rel))) {
    fail(`verification: runtime/${rel} missing after build`);
  }
}
console.log("PASS verification: runtime/dist/index.js and runtime/dist/blackceo-council.mjs exist");
console.log("INSTALL-RUNTIME: PASS (isolated pinned install plus build complete)");
process.exit(0);
