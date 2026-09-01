#!/usr/bin/env node
// ============================================================================
// self-test.mjs — U02 Worker core --self-test entry point (master-plan §9
// per-unit gate: "unit passes its own --self-test / negative test").
//
// Thin wrapper around the node --test suite in src/lib.test.mjs.
//   node self-test.mjs          → runs the suite, exits 0 on all-pass
//   node self-test.mjs --quiet  → prints a one-line pass/fail summary
// ============================================================================

import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const quiet = process.argv.includes('--quiet');

try {
  const out = execFileSync(process.execPath, ['--test', 'src/*.test.mjs'], {
    cwd: here,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const lines = out.split('\n');
  const pass = lines.find((l) => l.trim().startsWith('# pass')) || 'pass 0';
  const fail = lines.find((l) => l.trim().startsWith('# fail')) || 'fail 0';
  if (quiet) {
    process.stdout.write(`U02 worker core self-test: ${pass.trim()} / ${fail.trim()}\n`);
  } else {
    process.stdout.write(out);
  }
  if (!/fail 0/.test(out)) {
    process.exitCode = 1;
  }
} catch (err) {
  process.stderr.write(`self-test failed to run: ${err.message}\n`);
  process.exitCode = 2;
}
