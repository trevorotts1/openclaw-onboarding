/**
 * W28 decision 3: measured, operator-approved route budgets.
 *
 * Covers the conservative conversion (smallest ratio, safety factor,
 * null when unmeasured), the approval gate bound to the exact entry
 * hash, the resolver's live re-read, and the two operator scripts.
 */

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, test } from 'node:test';

import {
  RouteBudgetConfigError,
  computeRouteBudget,
  entrySha256,
  loadRouteBudgetApprovals,
  loadRouteBudgetConfig,
  minBytesPerToken,
  routeBudgetApprovalsPath,
  routeBudgetConfigPath,
  routeBudgetResolver,
  routeBudgetStatus,
  type RouteBudgetApproval,
  type RouteBudgetEntry,
} from '../src/budgets/route-budget.js';
import type { PinnedRouteSnapshot } from '../src/budgets/route-snapshot.js';

const skillRoot = join(import.meta.dirname, '..', '..');
const measureScript = join(skillRoot, 'scripts', 'measure-route-bytes-per-token.mjs');
const approveScript = join(skillRoot, 'scripts', 'approve-route-budget.mjs');
const shippedConfig = join(skillRoot, 'config', 'route-budgets.json');

const tmpDirs: string[] = [];
function tmp(): string {
  const d = mkdtempSync(join(tmpdir(), 'route-budget-'));
  tmpDirs.push(d);
  return d;
}
after(() => {
  for (const d of tmpDirs) rmSync(d, { recursive: true, force: true });
});

function entry(over: Partial<RouteBudgetEntry> = {}): RouteBudgetEntry {
  return {
    route_id: 'r1',
    model: null,
    context_window_tokens: 100_000,
    max_output_tokens: 8_000,
    measured_min_bytes_per_token: 2.5,
    safety_factor: 0.8,
    response_schema_bytes: 1_000,
    measured_at: '2026-10-19T00:00:00.000Z',
    measurement_basis: 'test basis',
    ...over,
  };
}

function snap(routeId: string, model: string | null): PinnedRouteSnapshot {
  return { routeId, requestedModelOrAlias: model } as unknown as PinnedRouteSnapshot;
}

function writeConfig(path: string, entries: RouteBudgetEntry[]): void {
  writeFileSync(path, JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries }));
}

function approvalFor(e: RouteBudgetEntry): RouteBudgetApproval {
  return {
    route_id: e.route_id,
    model: e.model,
    entry_sha256: entrySha256(e),
    approved_by: 'tester',
    approved_at: '2026-10-19T01:00:00.000Z',
  };
}

// ------------------------------------------------------------ computeRouteBudget

test('minBytesPerToken uses the smallest ratio, never the mean', () => {
  const pairs = [
    { bytes: 1200, input_tokens: 300 }, // 4.0
    { bytes: 1200, input_tokens: 600 }, // 2.0
    { bytes: 1200, input_tokens: 400 }, // 3.0
  ];
  assert.equal(minBytesPerToken(pairs), 2);
  const mean = (4 + 2 + 3) / 3;
  assert.notEqual(minBytesPerToken(pairs), mean);
});

test('minBytesPerToken skips pairs without a usable token count and floors to 4 decimals', () => {
  assert.equal(minBytesPerToken([{ bytes: 100, input_tokens: null }]), null);
  assert.equal(minBytesPerToken([{ bytes: 100, input_tokens: 0 }]), null);
  assert.equal(minBytesPerToken([]), null);
  // 10 / 3 = 3.3333... floored, never rounded up
  assert.equal(minBytesPerToken([{ bytes: 10, input_tokens: 3 }, { bytes: 5, input_tokens: null }]), 3.3333);
});

test('computeRouteBudget applies the safety factor, floors the context limit, ceils the reserve', () => {
  const b = computeRouteBudget(entry({ measured_min_bytes_per_token: 2.5, safety_factor: 0.8 }));
  assert.deepEqual(b, {
    context_limit_bytes: Math.floor(100_000 * (2.5 * 0.8)),
    response_schema_bytes: 1_000,
    output_reserve_bytes: Math.ceil(8_000 * (2.5 * 0.8)),
  });
  assert.equal(b?.context_limit_bytes, 200_000);
  assert.equal(b?.output_reserve_bytes, 16_000);
  const tighter = computeRouteBudget(entry({ safety_factor: 0.4 }));
  assert.ok(tighter && tighter.context_limit_bytes < (b?.context_limit_bytes ?? 0));
  const fractional = computeRouteBudget(
    entry({ context_window_tokens: 1001, max_output_tokens: 1001, measured_min_bytes_per_token: 1.5, safety_factor: 0.5 }),
  );
  assert.equal(fractional?.context_limit_bytes, 750); // 750.75 floored
  assert.equal(fractional?.output_reserve_bytes, 751); // 750.75 ceiled
});

test('computeRouteBudget is null when any measured field is null', () => {
  assert.equal(computeRouteBudget(entry({ context_window_tokens: null })), null);
  assert.equal(computeRouteBudget(entry({ max_output_tokens: null })), null);
  assert.equal(computeRouteBudget(entry({ measured_min_bytes_per_token: null })), null);
  assert.ok(computeRouteBudget(entry()));
});

// ------------------------------------------------------------ loading

test('paths: config override env and approvals file name', () => {
  assert.equal(routeBudgetConfigPath('/skill', {}), join('/skill', 'config', 'route-budgets.json'));
  assert.equal(routeBudgetConfigPath('/skill', { WISE_ELDERS_ROUTE_BUDGETS: '/x/y.json' }), '/x/y.json');
  assert.equal(routeBudgetApprovalsPath('/data'), join('/data', 'route-budget-approvals.json'));
});

test('loadRouteBudgetConfig rejects malformed content with a typed error', () => {
  const dir = tmp();
  const p = join(dir, 'c.json');
  const bad: unknown[] = [
    'not json',
    JSON.stringify({ schema: 'wrong', entries: [] }),
    JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries: [{ ...entry(), safety_factor: 0.95 }] }),
    JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries: [{ ...entry(), safety_factor: 0 }] }),
    JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries: [{ ...entry(), extra: 1 }] }),
    JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries: [{ ...entry(), context_window_tokens: -5 }] }),
    JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries: [entry(), entry()] }),
  ];
  for (const text of bad) {
    writeFileSync(p, text as string);
    assert.throws(() => loadRouteBudgetConfig(p), RouteBudgetConfigError);
  }
  assert.throws(() => loadRouteBudgetConfig(join(dir, 'missing.json')), RouteBudgetConfigError);
});

test('loadRouteBudgetApprovals: missing file is empty, malformed file throws', () => {
  const dir = tmp();
  assert.deepEqual(loadRouteBudgetApprovals(join(dir, 'none.json')), []);
  const p = join(dir, 'a.json');
  writeFileSync(p, '{"not":"an array"}');
  assert.throws(() => loadRouteBudgetApprovals(p), RouteBudgetConfigError);
  writeFileSync(p, JSON.stringify([{ route_id: 'r1' }]));
  assert.throws(() => loadRouteBudgetApprovals(p), RouteBudgetConfigError);
});

// ------------------------------------------------------------ status + resolver

test('routeBudgetStatus: exact model first, then model:null; states are honest', () => {
  const generic = entry({ model: null, measured_min_bytes_per_token: 2 });
  const sonnet = entry({ model: 'sonnet', measured_min_bytes_per_token: 3 });
  const config = { schema: 'wise-elders.route-budgets/v1' as const, entries: [generic, sonnet] };
  const approvals = [approvalFor(generic), approvalFor(sonnet)];

  const s1 = routeBudgetStatus(config, approvals, 'r1', 'sonnet');
  assert.equal(s1.state, 'approved');
  assert.equal(s1.state === 'approved' ? s1.budget?.context_limit_bytes : -1, Math.floor(100_000 * (3 * 0.8)));
  const s2 = routeBudgetStatus(config, approvals, 'r1', 'other-model');
  assert.equal(s2.state === 'approved' ? s2.budget?.context_limit_bytes : -1, Math.floor(100_000 * (2 * 0.8)));
  const s3 = routeBudgetStatus(config, approvals, 'r1', null);
  assert.equal(s3.state === 'approved' ? s3.budget?.context_limit_bytes : -1, Math.floor(100_000 * (2 * 0.8)));

  assert.deepEqual(routeBudgetStatus(config, approvals, 'unknown-route', null), { state: 'no_entry', proposed: null });
  const awaiting = routeBudgetStatus(config, [], 'r1', 'sonnet');
  assert.equal(awaiting.state, 'awaiting_approval');
  assert.deepEqual('proposed' in awaiting ? awaiting.proposed : null, sonnet);

  const unmeasured = entry({ route_id: 'r2', measured_min_bytes_per_token: null });
  const nm = routeBudgetStatus({ ...config, entries: [unmeasured] }, [approvalFor(unmeasured)], 'r2', null);
  assert.equal(nm.state, 'not_measured');
});

test('routeBudgetResolver: null without approval, null when numbers changed, budget when approved', () => {
  const dir = tmp();
  const configPath = join(dir, 'config.json');
  const approvalsPath = join(dir, 'approvals.json');
  const e = entry();
  writeConfig(configPath, [e]);
  const resolve = routeBudgetResolver({ configPath, approvalsPath });

  // Entry exists, approvals file missing.
  assert.equal(resolve(snap('r1', 'any')), null);

  // Matching approval appears while the resolver is live: no restart needed.
  writeFileSync(approvalsPath, JSON.stringify([approvalFor(e)]));
  assert.deepEqual(resolve(snap('r1', 'any')), {
    context_limit_bytes: 200_000,
    response_schema_bytes: 1_000,
    output_reserve_bytes: 16_000,
  });

  // Numbers change after approval: the hash no longer matches.
  writeConfig(configPath, [entry({ measured_min_bytes_per_token: 3 })]);
  assert.equal(resolve(snap('r1', 'any')), null);

  // A fresh approval for the new numbers re-enables it.
  writeFileSync(approvalsPath, JSON.stringify([approvalFor(entry({ measured_min_bytes_per_token: 3 }))]));
  assert.equal(resolve(snap('r1', 'any'))?.context_limit_bytes, 240_000);

  // Approval for another route or model never counts.
  writeFileSync(approvalsPath, JSON.stringify([{ ...approvalFor(entry({ measured_min_bytes_per_token: 3 })), route_id: 'r9' }]));
  assert.equal(resolve(snap('r1', 'any')), null);
});

test('routeBudgetResolver fails closed on missing or malformed files', () => {
  const dir = tmp();
  const configPath = join(dir, 'config.json');
  const approvalsPath = join(dir, 'approvals.json');
  const resolve = routeBudgetResolver({ configPath, approvalsPath });
  assert.equal(resolve(snap('r1', null)), null); // no config at all
  const e = entry();
  writeConfig(configPath, [e]);
  writeFileSync(approvalsPath, 'garbage');
  assert.equal(resolve(snap('r1', null)), null);
});

test('shipped config proposes the three routes, unmeasured, and the resolver returns null for them', () => {
  const config = loadRouteBudgetConfig(shippedConfig);
  const keys = config.entries.map((e) => `${e.route_id}|${e.model}`).sort();
  assert.deepEqual(keys, [
    'claude-configured|sonnet',
    'claude-nine-configured|null',
    'deepseek-configured|null',
  ]);
  for (const e of config.entries) {
    assert.equal(e.measured_min_bytes_per_token, null);
    assert.equal(e.measured_at, null);
    assert.equal(computeRouteBudget(e), null);
  }
  const resolve = routeBudgetResolver({
    configPath: shippedConfig,
    approvalsPath: join(tmp(), 'route-budget-approvals.json'),
  });
  assert.equal(resolve(snap('deepseek-configured', 'deepseek-v4.1-flash')), null);
  assert.equal(resolve(snap('claude-configured', 'sonnet')), null);
  assert.equal(resolve(snap('claude-nine-configured', null)), null);
});

// ------------------------------------------------------------ scripts

function run(script: string, args: string[], env: Record<string, string> = {}) {
  const r = spawnSync(process.execPath, [script, ...args], {
    encoding: 'utf8',
    env: { ...process.env, ...env },
    timeout: 60_000,
  });
  return { code: r.status, out: r.stdout, err: r.stderr };
}

const PAIRS = [
  { bytes: 12_000, input_tokens: 3_000 }, // 4.0
  { bytes: 12_000, input_tokens: 6_000 }, // 2.0 <- smallest
  { bytes: 12_000, input_tokens: 5_000 }, // 2.4
  { bytes: 9_000, input_tokens: null }, // unusable, skipped
];

function measurementsFile(dir: string, pairs: unknown[] = PAIRS, routeId = 'r1'): string {
  const p = join(dir, `measurements-${routeId}-${pairs.length}-${(pairs[0] as { input_tokens: number | null }).input_tokens}.json`);
  writeFileSync(
    p,
    JSON.stringify({
      route_id: routeId,
      model: null,
      measured_at: '2026-10-19T00:00:00.000Z',
      context_window_tokens: 100_000,
      max_output_tokens: 8_000,
      pairs,
    }),
  );
  return p;
}

test('measure script: --measurements recomputes the same entry deterministically', () => {
  const dir = tmp();
  const m = measurementsFile(dir);
  const cfg = join(dir, 'config.json');
  writeConfig(cfg, [entry({ measured_min_bytes_per_token: null, measured_at: null, context_window_tokens: null, max_output_tokens: null })]);
  const env = { WISE_ELDERS_ROUTE_BUDGETS: cfg };
  const a = run(measureScript, ['--route', 'r1', '--measurements', m], env);
  const b = run(measureScript, ['--route', 'r1', '--measurements', m], env);
  assert.equal(a.code, 0, a.err);
  assert.equal(a.out, b.out);
  const proposed = JSON.parse(a.out) as RouteBudgetEntry;
  assert.equal(proposed.measured_min_bytes_per_token, 2);
  assert.equal(proposed.measured_at, '2026-10-19T00:00:00.000Z');
  assert.equal(proposed.context_window_tokens, 100_000);
  assert.equal(proposed.max_output_tokens, 8_000);
  assert.equal(proposed.safety_factor, 0.8);
  assert.match(proposed.measurement_basis, /3 of 4 payloads/);
  assert.match(proposed.measurement_basis, /usage\.input_tokens/);
  // Without --write the config is untouched.
  assert.equal(loadRouteBudgetConfig(cfg).entries[0].measured_min_bytes_per_token, null);
});

test('measure script: --write updates the config only and never creates approvals', () => {
  const dir = tmp();
  const m = measurementsFile(dir);
  const cfg = join(dir, 'config.json');
  writeConfig(cfg, [entry({ measured_min_bytes_per_token: null, measured_at: null })]);
  const r = run(measureScript, ['--route', 'r1', '--measurements', m, '--write'], { WISE_ELDERS_ROUTE_BUDGETS: cfg });
  assert.equal(r.code, 0, r.err);
  const written = loadRouteBudgetConfig(cfg).entries[0];
  assert.equal(written.measured_min_bytes_per_token, 2);
  assert.equal(written.measured_at, '2026-10-19T00:00:00.000Z');
  assert.equal(existsSync(join(dir, 'route-budget-approvals.json')), false);
  // The proposed entry is not live: no approval, so the resolver says null.
  const resolve = routeBudgetResolver({ configPath: cfg, approvalsPath: routeBudgetApprovalsPath(dir) });
  assert.equal(resolve(snap('r1', null)), null);
});

test('measure script: a new route is appended as a proposal; implausible ratios are refused', () => {
  const dir = tmp();
  const cfg = join(dir, 'config.json');
  writeConfig(cfg, [entry()]);
  const m = measurementsFile(dir, PAIRS, 'r2');
  const ok = run(measureScript, ['--route', 'r2', '--measurements', m, '--write'], { WISE_ELDERS_ROUTE_BUDGETS: cfg });
  assert.equal(ok.code, 0, ok.err);
  assert.equal(loadRouteBudgetConfig(cfg).entries.length, 2);

  const before = readFileSync(cfg, 'utf8');
  const huge = measurementsFile(dir, [{ bytes: 12_000, input_tokens: 5 }]); // 2400 bytes/token
  const bad = run(measureScript, ['--route', 'r1', '--measurements', huge, '--write'], { WISE_ELDERS_ROUTE_BUDGETS: cfg });
  assert.equal(bad.code, 3);
  assert.match(bad.err, /implausible/);
  assert.equal(bad.out, '');
  assert.equal(readFileSync(cfg, 'utf8'), before);
});

test('approve script: writes one hash-bound approval outside the skill folder, then the resolver goes live', () => {
  const dir = tmp();
  const dataDir = join(dir, 'service');
  const cfg = join(dir, 'config.json');
  const e = entry();
  writeConfig(cfg, [e]);
  const env = { WISE_ELDERS_ROUTE_BUDGETS: cfg };

  const r = run(approveScript, ['--route', 'r1', '--approved-by', 'Trevor', '--data-dir', dataDir], env);
  assert.equal(r.code, 0, r.err);
  const printed = JSON.parse(r.out) as { computed_budget_bytes: { context_limit_bytes: number }; entry_sha256: string };
  assert.equal(printed.computed_budget_bytes.context_limit_bytes, 200_000);
  assert.equal(printed.entry_sha256, entrySha256(e));

  const approvals = loadRouteBudgetApprovals(routeBudgetApprovalsPath(dataDir));
  assert.equal(approvals.length, 1);
  assert.equal(approvals[0].entry_sha256, entrySha256(e));
  assert.equal(approvals[0].approved_by, 'Trevor');

  const resolve = routeBudgetResolver({ configPath: cfg, approvalsPath: routeBudgetApprovalsPath(dataDir) });
  assert.equal(resolve(snap('r1', 'x'))?.context_limit_bytes, 200_000);

  // Re-approving replaces, never duplicates.
  const again = run(approveScript, ['--route', 'r1', '--approved-by', 'Trevor', '--data-dir', dataDir], env);
  assert.equal(again.code, 0, again.err);
  assert.equal(loadRouteBudgetApprovals(routeBudgetApprovalsPath(dataDir)).length, 1);

  // Changing the numbers invalidates the approval until approved again.
  writeConfig(cfg, [entry({ measured_min_bytes_per_token: 3 })]);
  assert.equal(resolve(snap('r1', 'x')), null);
});

test('approve script refuses unmeasured entries, unknown routes, and a data dir inside the skill folder', () => {
  const dir = tmp();
  const cfg = join(dir, 'config.json');
  writeConfig(cfg, [entry({ route_id: 'unmeasured', measured_min_bytes_per_token: null }), entry()]);
  const env = { WISE_ELDERS_ROUTE_BUDGETS: cfg };
  const dataDir = join(dir, 'service');

  const u = run(approveScript, ['--route', 'unmeasured', '--approved-by', 'T', '--data-dir', dataDir], env);
  assert.equal(u.code, 2);
  assert.match(u.err, /not fully measured/);
  const n = run(approveScript, ['--route', 'nope', '--approved-by', 'T', '--data-dir', dataDir], env);
  assert.equal(n.code, 2);
  const noWho = run(approveScript, ['--route', 'r1', '--data-dir', dataDir], env);
  assert.equal(noWho.code, 2);
  assert.equal(existsSync(routeBudgetApprovalsPath(dataDir)), false);

  const inside = join(skillRoot, 'config', 'approval-must-not-exist');
  const refused = run(approveScript, ['--route', 'r1', '--approved-by', 'T', '--data-dir', inside], env);
  assert.equal(refused.code, 2);
  assert.match(refused.err, /inside the skill folder/);
  assert.equal(existsSync(inside), false);

  // A symlink that points into the skill folder is refused too.
  mkdirSync(dataDir, { recursive: true });
  const link = join(dir, 'link');
  spawnSync('ln', ['-s', join(skillRoot, 'config'), link]);
  const viaLink = run(approveScript, ['--route', 'r1', '--approved-by', 'T', '--data-dir', link], env);
  assert.equal(viaLink.code, 2);
  assert.equal(existsSync(join(skillRoot, 'config', 'route-budget-approvals.json')), false);
});

test('approve script refuses a skill-folder child whose name starts with two dots', () => {
  const dir = tmp();
  const cfg = join(dir, 'config.json');
  writeConfig(cfg, [entry()]);
  const evil = join(skillRoot, '..evil-approval-must-not-exist');
  const r = run(approveScript, ['--route', 'r1', '--approved-by', 'T', '--data-dir', evil], { WISE_ELDERS_ROUTE_BUDGETS: cfg });
  const wrote = existsSync(evil);
  rmSync(evil, { recursive: true, force: true }); // only matters if the guard regresses
  assert.equal(wrote, false);
  assert.equal(r.code, 2);
  assert.match(r.err, /inside the skill folder/);
  // A sibling outside the skill folder whose name starts with two dots is fine.
  const ok = run(approveScript, ['--route', 'r1', '--approved-by', 'T', '--data-dir', join(dir, '..svc')], { WISE_ELDERS_ROUTE_BUDGETS: cfg });
  assert.equal(ok.code, 0, ok.err);
});

test('measure script: the recording model selects the entry, with or without --route', () => {
  const dir = tmp();
  const cfg = join(dir, 'config.json');
  const blank = { measured_min_bytes_per_token: null, measured_at: null } as const;
  writeConfig(cfg, [entry({ model: null, ...blank }), entry({ model: 'sonnet', ...blank })]);
  const m = join(dir, 'sonnet.json');
  writeFileSync(m, JSON.stringify({ route_id: 'r1', model: 'sonnet', measured_at: '2026-10-19T00:00:00.000Z', pairs: PAIRS }));
  const env = { WISE_ELDERS_ROUTE_BUDGETS: cfg };

  const withRoute = run(measureScript, ['--route', 'r1', '--measurements', m, '--write'], env);
  assert.equal(withRoute.code, 0, withRoute.err);
  assert.equal((JSON.parse(withRoute.out) as RouteBudgetEntry).model, 'sonnet');
  const entries = loadRouteBudgetConfig(cfg).entries;
  assert.equal(entries.length, 2);
  assert.equal(entries.find((e) => e.model === 'sonnet')?.measured_min_bytes_per_token, 2);
  assert.equal(entries.find((e) => e.model === null)?.measured_min_bytes_per_token, null);

  const without = run(measureScript, ['--measurements', m], env);
  assert.equal(without.out, withRoute.out);

  const conflict = run(measureScript, ['--route', 'r1', '--model', 'opus', '--measurements', m], env);
  assert.equal(conflict.code, 2);
  assert.match(conflict.err, /conflicts with the recording/);
});

test('scripts never print a credential', () => {
  const dir = tmp();
  const cfg = join(dir, 'config.json');
  writeConfig(cfg, [entry({ measured_min_bytes_per_token: null, measured_at: null })]);
  const secret = 'sk-test-0123456789-should-never-appear';
  const env = { WISE_ELDERS_ROUTE_BUDGETS: cfg, DEEPSEEK_API_KEY: secret, ANTHROPIC_AUTH_TOKEN: secret };
  const m = run(measureScript, ['--route', 'r1', '--measurements', measurementsFile(dir)], env);
  const a = run(approveScript, ['--route', 'r1', '--approved-by', 'T', '--data-dir', join(dir, 'd')], { ...env, WISE_ELDERS_ROUTE_BUDGETS: cfg });
  for (const r of [m, a]) {
    assert.ok(!r.out.includes(secret) && !r.err.includes(secret));
  }
});

test('owned files contain no em dash', () => {
  const dash = String.fromCharCode(0x2014);
  for (const f of [
    join(skillRoot, 'runtime', 'src', 'budgets', 'route-budget.ts'),
    join(skillRoot, 'runtime', 'tests', 'route-budget.test.ts'),
    shippedConfig,
    measureScript,
    approveScript,
  ]) {
    assert.ok(!readFileSync(f, 'utf8').includes(dash), f);
  }
});
