#!/usr/bin/env node
// Operator step, run once after Trevor signs off on the proposed numbers:
//
//   node scripts/approve-route-budget.mjs --route ID [--model M]
//        --approved-by NAME --data-dir DIR
//
// Prints the exact proposed numbers, then writes ONE approval bound to the
// sha256 of that exact entry into <DIR>/route-budget-approvals.json. DIR is
// the service data dir. It must be outside the skill folder, because update
// sync replaces skill folders. If the proposed numbers change later, the
// hash no longer matches and the route returns to "awaiting approval".
// Prints no credential.

import { existsSync, mkdirSync, realpathSync, renameSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, relative, resolve, isAbsolute, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const skillRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const runtimeDir = join(skillRoot, 'runtime');

async function loadRuntime(rel) {
  const dist = join(runtimeDir, 'dist', `${rel}.js`);
  if (existsSync(dist)) return import(pathToFileURL(dist).href);
  const src = join(runtimeDir, 'src', `${rel}.ts`);
  const require = createRequire(join(runtimeDir, 'package.json'));
  const { tsImport } = await import(pathToFileURL(require.resolve('tsx/esm/api')).href);
  return tsImport(pathToFileURL(src).href, import.meta.url);
}

function die(message) {
  console.error(message);
  process.exit(2);
}

const opts = {};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i += 1) {
  const a = argv[i];
  if (!['--route', '--model', '--approved-by', '--data-dir'].includes(a)) die(`unknown argument ${a}`);
  if (i + 1 >= argv.length) die(`${a} needs a value`);
  opts[a.slice(2)] = argv[(i += 1)];
}
if (!opts.route) die('--route ID is required');
if (!opts['data-dir']) die('--data-dir DIR is required');
const approvedBy = (opts['approved-by'] ?? '').trim();
if (!approvedBy || approvedBy.length > 200 || /[\u0000-\u001f]/.test(approvedBy)) {
  die('--approved-by NAME is required (plain text, up to 200 characters)');
}
const model = opts.model ?? null;

// Deepest existing ancestor resolved through symlinks, so a symlinked
// data dir pointing into the skill folder is caught too.
function realTarget(p) {
  let cur = resolve(p);
  const tail = [];
  while (!existsSync(cur)) {
    tail.unshift(cur.slice(dirname(cur).length + 1));
    cur = dirname(cur);
  }
  return join(realpathSync(cur), ...tail);
}
const dataDir = realTarget(opts['data-dir']);
const rel = relative(realpathSync(skillRoot), dataDir);
if (rel === '' || !(rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel))) {
  die('--data-dir is inside the skill folder; approvals must live in the service data dir');
}

const rb = await loadRuntime('budgets/route-budget');
const configPath = rb.routeBudgetConfigPath(skillRoot, process.env);
let config;
try {
  config = rb.loadRouteBudgetConfig(configPath);
} catch (err) {
  die(`cannot read the proposed entries: ${err.message}`);
}
const entry = config.entries.find((e) => e.route_id === opts.route && e.model === model);
if (!entry) die(`no proposed entry for route ${opts.route} model ${model ?? 'null'}`);
const budget = rb.computeRouteBudget(entry);
if (!budget) die('this entry is not fully measured (a measured field is null); nothing to approve');

const sha = rb.entrySha256(entry);
console.log(JSON.stringify({ proposed_entry: entry, computed_budget_bytes: budget, entry_sha256: sha }, null, 2));

const approvalsPath = rb.routeBudgetApprovalsPath(dataDir);
let existing;
try {
  existing = rb.loadRouteBudgetApprovals(approvalsPath);
} catch (err) {
  die(`existing approvals file is malformed, not overwriting: ${err.message}`);
}
const approval = {
  route_id: entry.route_id,
  model: entry.model,
  entry_sha256: sha,
  approved_by: approvedBy,
  approved_at: new Date().toISOString(),
};
const next = [
  ...existing.filter((a) => !(a.route_id === entry.route_id && a.model === entry.model)),
  approval,
];
mkdirSync(dataDir, { recursive: true, mode: 0o700 });
const tmp = `${approvalsPath}.tmp-${process.pid}`;
writeFileSync(tmp, `${JSON.stringify(next, null, 2)}\n`, { mode: 0o600 });
renameSync(tmp, approvalsPath);
console.error(`approval recorded for route ${entry.route_id} model ${entry.model ?? 'null'}`);
