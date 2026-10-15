#!/usr/bin/env node
// Council of Wise Elders: runtime build asset step (CWE-039 repair,
// finding F-1).
//
// src/persistence/index.ts loads the canonical council schema from
// ./migrations/0001-council-schema.sql, resolved against the module's
// own URL at module load. That works unchanged from src/ (the tsx
// suites) and from the tsc output module (dist/persistence/index.js),
// but the esbuild single-file bundle (dist/blackceo-council.mjs)
// resolves the same relative URL to dist/migrations/, and no build
// step populated it: tsc does not copy .sql assets and the bundle step
// added none. The bundled CLI therefore died with ENOENT at startup,
// before any command ran, in every clean installed copy.
//
// This step makes the schema asset travel with the build. After the
// bundle is written, it copies the canonical migrations folder, byte
// for byte, to both locations the built outputs resolve against:
//   dist/migrations/             (the single-file bundle)
//   dist/persistence/migrations/ (the tsc module output)
// The .sql file under src/persistence/migrations/ stays the single
// source of truth. Nothing here edits, embeds, or regenerates its
// text, so the exported COUNCIL_SCHEMA_SQL value and the Command
// Center statement-parity story for the schema are untouched. The
// step fails loudly if the canonical folder is missing or empty, so
// a build can never silently ship output whose schema asset is
// absent.

import { cpSync, existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const runtimeDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceDir = join(runtimeDir, "src", "persistence", "migrations");
const targets = [
  join(runtimeDir, "dist", "migrations"),
  join(runtimeDir, "dist", "persistence", "migrations"),
];

if (!existsSync(sourceDir)) {
  console.error(`FAIL copy-runtime-assets: canonical migrations folder missing: ${sourceDir}`);
  process.exit(1);
}
const assets = readdirSync(sourceDir).sort();
if (assets.length === 0) {
  console.error(`FAIL copy-runtime-assets: canonical migrations folder is empty: ${sourceDir}`);
  process.exit(1);
}
for (const target of targets) {
  cpSync(sourceDir, target, { recursive: true });
  console.log(`PASS copy-runtime-assets: ${assets.join(", ")} -> ${target}`);
}
