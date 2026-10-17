/**
 * Byte-for-byte parity (drift) test between the canonical contracts and
 * the generated Command Center consumer artifact (CWE-003, decision D-006;
 * test contract T148 cross-consumer parity evidence).
 *
 * Usage:
 *   node verify-cc-parity.mjs --consumer <cc contracts dir>
 * Optional overrides:
 *   --canonical <onb contracts dir>   (default: this script's parent dir)
 *   --schemas <onb schemas dir>       (default: <skill root>/schemas)
 *
 * Exit code 0 and a PASS line when the consumer tree equals the generator's
 * expected output byte for byte. Any drift, missing file, or extra file
 * exits 1 and names the differing paths. Pure Node, no dependencies.
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildConsumerFiles } from './generate-cc-consumer.mjs';

function listFiles(root) {
  const out = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full);
      else out.push(relative(root, full).split(sep).join('/'));
    }
  };
  walk(root);
  return out.sort();
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!key.startsWith('--') || argv[i + 1] === undefined) {
      throw new Error(`bad argument near ${String(key)}`);
    }
    args[key.slice(2)] = argv[i + 1];
  }
  return args;
}

function main() {
  const here = dirname(fileURLToPath(import.meta.url));
  const canonicalDir = join(here, '..');
  const args = parseArgs(process.argv.slice(2));
  const canonical = args.canonical ?? canonicalDir;
  const schemas = args.schemas ?? join(canonical, '..', '..', '..', 'schemas');
  const consumer = args.consumer;
  if (!consumer) throw new Error('--consumer <cc contracts dir> is required');
  if (!existsSync(consumer)) throw new Error(`consumer dir not found: ${consumer}`);

  const expected = buildConsumerFiles(canonical, schemas);
  const actualFiles = listFiles(consumer);
  const problems = [];

  for (const rel of actualFiles) {
    if (!expected.has(rel)) problems.push(`extra file in consumer: ${rel}`);
  }
  for (const [rel, bytes] of expected) {
    const full = join(consumer, rel);
    if (!existsSync(full)) {
      problems.push(`missing file in consumer: ${rel}`);
      continue;
    }
    const actual = readFileSync(full);
    if (!actual.equals(bytes)) {
      problems.push(`byte drift: ${rel} (expected ${bytes.length} bytes, found ${actual.length})`);
    }
  }

  if (problems.length > 0) {
    process.stdout.write('PARITY FAIL\n');
    for (const p of problems) process.stdout.write(`  ${p}\n`);
    process.exit(1);
  }
  process.stdout.write(
    `PARITY PASS: consumer tree matches canonical generation byte for byte (${expected.size} files)\n`,
  );
}

main();
