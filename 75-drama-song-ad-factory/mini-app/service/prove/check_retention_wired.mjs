#!/usr/bin/env node
// ============================================================================
// check_retention_wired.mjs — U-GEN309 check (S75-083)
//
//   node 75-drama-song-ad-factory/mini-app/service/prove/check_retention_wired.mjs
//
// Prints the production import of the retention module and the call site of
// `dueForDeletion`, both under src/. Before the fix it printed neither: no file
// under src/ imported retention.js and no production code called the rule
// (S75-083 — the deletion rule was a pure library that production never ran).
//
// EXIT  0 PASS  — the service imports its rule AND calls it
//       2 FAIL  — one of the two is absent; the missing one is named
// ============================================================================

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// fileURLToPath, not `.pathname`: the drive path has spaces in it.
const SRC = fileURLToPath(new URL('../src/', import.meta.url));

const IMPORT_RE = /^\s*import\b[^;]*from\s+['"]\.\/retention\.js['"]/;
const CALL = 'dueForDeletion(';

const importers = [];
const callSites = [];

for (const name of readdirSync(SRC).sort()) {
  if (!name.endsWith('.js')) continue;
  const lines = readFileSync(join(SRC, name), 'utf8').split('\n');
  lines.forEach((line, i) => {
    if (IMPORT_RE.test(line)) importers.push(`src/${name}:${i + 1}: ${line.trim()}`);
    if (line.includes(CALL)) callSites.push(`src/${name}:${i + 1}: ${line.trim()}`);
  });
}

console.log('production import of ./retention.js under src/:');
if (importers.length === 0) console.log('  (none)');
for (const hit of importers) console.log(`  ${hit}`);

console.log(`\ncalls to ${CALL.slice(0, -1)} under src/:`);
// The definition line is not a call; only real call sites are printed.
const calls = callSites.filter((hit) => !hit.includes('export function dueForDeletion'));
if (calls.length === 0) console.log('  (none)');
for (const hit of calls) console.log(`  ${hit}`);

const missing = [];
if (importers.length === 0) missing.push('no src/ file imports ./retention.js (the rule is never loaded)');
if (calls.length === 0) missing.push(`no src/ file calls ${CALL.slice(0, -1)} (the rule is never run)`);

if (missing.length > 0) {
  for (const why of missing) console.log(`\nFAIL: ${why}`);
  process.exit(2);
}
console.log('\nPASS: production imports the deletion rule and calls it.');
