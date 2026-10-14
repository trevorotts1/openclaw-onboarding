#!/usr/bin/env node
// Council of Wise Elders: runtime installer (scaffold stage).
// Performs preflight and verification ONLY. The runtime payload is
// owned by the core runtime unit (CWE-004) and is not yet built, so
// this script reports NOT_YET_BUILT and exits 3. It never simulates
// an install, never copies placeholder code, and never touches state
// outside the skill folder.
// Usage: node install-runtime.mjs [--root <skill-folder>]
// Exit codes: 0 installed (future), 1 preflight failure, 3 not built.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const rootIdx = args.indexOf("--root");
const root = rootIdx >= 0
  ? resolve(args[rootIdx + 1])
  : resolve(dirname(fileURLToPath(import.meta.url)), "..");

const major = Number(process.versions.node.split(".")[0]);
if (!(major >= 18)) {
  console.log(`FAIL preflight: Node.js >= 18 required, found ${process.version}`);
  process.exit(1);
}
console.log(`PASS preflight: Node.js ${process.version}`);

const pkgPath = join(root, "runtime", "package.json");
if (!existsSync(pkgPath)) {
  console.log("FAIL preflight: runtime/package.json missing");
  process.exit(1);
}
const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
console.log(`INFO runtime package identity: ${pkg.name}@${pkg.version} (private=${pkg.private})`);

const distEntry = join(root, "runtime", "dist", "index.js");
if (!existsSync(distEntry)) {
  console.log("NOT_YET_BUILT: the council runtime payload (runtime/dist) does not exist yet.");
  console.log("It is owned by the core runtime unit (CWE-004). No install was performed and nothing was simulated.");
  console.log("When the payload lands, this script installs dependencies in isolation inside runtime/ only.");
  process.exit(3);
}

console.log("The runtime payload exists, but installation is performed by the runtime unit's tested installer path.");
console.log("This scaffold installer performs no payload installation. See INSTALL.md Step 4.");
process.exit(3);
