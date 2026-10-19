/**
 * W28 decision 3: per-route token limits, with no approval step.
 *
 * Covers the conservative conversion (smallest ratio, safety factor),
 * the built-in defaults for an unmeasured route, the resolver's live
 * re-read, and the optional measurement script.
 */

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, test } from 'node:test';

import {
  RouteBudgetConfigError,
  computeRouteBudget,
  DEFAULT_CONTEXT_WINDOW_TOKENS,
  DEFAULT_MAX_OUTPUT_TOKENS,
  findRouteBudgetEntry,
  loadRouteBudgetConfig,
  minBytesPerToken,
  routeBudgetConfigPath,
  routeBudgetResolver,
  type RouteBudgetEntry,
} from '../src/budgets/route-budget.js';
import type { PinnedRouteSnapshot } from '../src/budgets/route-snapshot.js';

const skillRoot = join(import.meta.dirname, '..', '..');
const measureScript = join(skillRoot, 'scripts', 'measure-route-bytes-per-token.mjs');
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

function snap(
  routeId: string,
  model: string | null,
  caps: { contextWindowTokens: number | null; maxOutputTokens: number | null } = {
    contextWindowTokens: null,
    maxOutputTokens: null,
  },
): PinnedRouteSnapshot {
  return { routeId, requestedModelOrAlias: model, capabilitySnapshot: caps } as unknown as PinnedRouteSnapshot;
}

function writeConfig(path: string, entries: RouteBudgetEntry[]): void {
  writeFileSync(path, JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries }));
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
  assert.ok(tighter && tighter.context_limit_bytes < (b.context_limit_bytes));
  const fractional = computeRouteBudget(
    entry({ context_window_tokens: 2002, max_output_tokens: 1001, measured_min_bytes_per_token: 1.5, safety_factor: 0.5 }),
  );
  assert.equal(fractional.context_limit_bytes, 1501); // 1501.5 floored
  assert.equal(fractional.output_reserve_bytes, 751); // 750.75 ceiled
});

test('computeRouteBudget never refuses: unmeasured numbers fall back to conservative defaults', () => {
  // No entry at all: 1.0 bytes per token, safety 0.8, fallback window.
  const none = computeRouteBudget(null);
  assert.equal(none.context_limit_bytes, Math.floor(DEFAULT_CONTEXT_WINDOW_TOKENS * 0.8));
  assert.equal(none.output_reserve_bytes, Math.ceil(DEFAULT_MAX_OUTPUT_TOKENS * 0.8));
  // Unmeasured entry: the route's own reported limits are used.
  const reported = computeRouteBudget(
    entry({ context_window_tokens: null, max_output_tokens: null, measured_min_bytes_per_token: null }),
    { contextWindowTokens: 200_000, maxOutputTokens: 8_000 },
  );
  assert.equal(reported.context_limit_bytes, 160_000);
  assert.equal(reported.output_reserve_bytes, 6_400);
  // An answer limit that is not below the window is cut to a quarter of it.
  const silly = computeRouteBudget(null, { contextWindowTokens: 1_000, maxOutputTokens: 5_000 });
  assert.equal(silly.output_reserve_bytes, Math.ceil(250 * 0.8));
});

// ------------------------------------------------------------ loading

test('paths: config override env', () => {
  assert.equal(routeBudgetConfigPath('/skill', {}), join('/skill', 'config', 'route-budgets.json'));
  assert.equal(routeBudgetConfigPath('/skill', { WISE_ELDERS_ROUTE_BUDGETS: '/x/y.json' }), '/x/y.json');
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

// ------------------------------------------------------------ lookup + resolver

test('findRouteBudgetEntry: exact model first, then model:null, else null', () => {
  const generic = entry({ model: null, measured_min_bytes_per_token: 2 });
  const sonnet = entry({ model: 'sonnet', measured_min_bytes_per_token: 3 });
  const config = { schema: 'wise-elders.route-budgets/v1' as const, entries: [generic, sonnet] };
  assert.equal(findRouteBudgetEntry(config, 'r1', 'sonnet'), sonnet);
  assert.equal(findRouteBudgetEntry(config, 'r1', 'other-model'), generic);
  assert.equal(findRouteBudgetEntry(config, 'r1', null), generic);
  assert.equal(findRouteBudgetEntry(config, 'unknown-route', null), null);
  assert.equal(findRouteBudgetEntry(null, 'r1', null), null);
});

test('routeBudgetResolver: always returns limits, re-reads the config live, no approval file', () => {
  const dir = tmp();
  const configPath = join(dir, 'config.json');
  const resolve = routeBudgetResolver({ configPath });

  // Missing config: conservative defaults, never a refusal.
  assert.equal(resolve(snap('r1', 'any')).context_limit_bytes, Math.floor(DEFAULT_CONTEXT_WINDOW_TOKENS * 0.8));

  writeConfig(configPath, [entry()]);
  assert.deepEqual(resolve(snap('r1', 'any')), {
    context_limit_bytes: 200_000,
    response_schema_bytes: 1_000,
    output_reserve_bytes: 16_000,
  });
  // Numbers change while running: picked up with no restart and no approval.
  writeConfig(configPath, [entry({ measured_min_bytes_per_token: 3 })]);
  assert.equal(resolve(snap('r1', 'any')).context_limit_bytes, 240_000);
  // Malformed config falls back to the defaults.
  writeFileSync(configPath, 'garbage');
  assert.equal(resolve(snap('r1', 'any')).context_limit_bytes, Math.floor(DEFAULT_CONTEXT_WINDOW_TOKENS * 0.8));
  // A null path (no shipped config) works too.
  assert.ok(routeBudgetResolver({ configPath: null })(snap('r1', null)).context_limit_bytes > 0);
});

test('shipped config: DeepSeek Flash carries the measured numbers, the others use defaults', () => {
  const config = loadRouteBudgetConfig(shippedConfig);
  const keys = config.entries.map((e) => `${e.route_id}|${e.model}`).sort();
  assert.deepEqual(keys, [
    'claude-configured|sonnet',
    'claude-nine-configured|null',
    'deepseek-configured|null',
  ]);
  const deepseek = findRouteBudgetEntry(config, 'deepseek-configured', 'deepseek-flash');
  assert.equal(deepseek?.measured_min_bytes_per_token, 1.429);
  assert.equal(deepseek?.safety_factor, 0.8);
  const resolve = routeBudgetResolver({ configPath: shippedConfig });
  const ds = resolve(snap('deepseek-configured', 'deepseek-flash'));
  assert.equal(ds.context_limit_bytes, Math.floor(1_048_576 * 1.429 * 0.8));
  assert.equal(ds.output_reserve_bytes, Math.ceil(393_216 * 1.429 * 0.8));
  for (const [route, model] of [['claude-configured', 'sonnet'], ['claude-nine-configured', null]] as const) {
    assert.equal(findRouteBudgetEntry(config, route, model)?.measured_min_bytes_per_token, null);
    const limits = resolve(snap(route, model));
    assert.equal(limits.context_limit_bytes, Math.floor(DEFAULT_CONTEXT_WINDOW_TOKENS * 0.8));
  }
  // A route nobody listed still convenes on the defaults.
  assert.ok(resolve(snap('some-new-route', null)).context_limit_bytes > 0);
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

test('measure script: --write updates the config only', () => {
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
  // The refined numbers are live at once: no approval step.
  assert.equal(routeBudgetResolver({ configPath: cfg })(snap('r1', null)).context_limit_bytes, 160_000);
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
  assert.ok(!m.out.includes(secret) && !m.err.includes(secret));
});

test('owned files contain no em dash', () => {
  const dash = String.fromCharCode(0x2014);
  for (const f of [
    join(skillRoot, 'runtime', 'src', 'budgets', 'route-budget.ts'),
    join(skillRoot, 'runtime', 'tests', 'route-budget.test.ts'),
    shippedConfig,
    measureScript,
  ]) {
    assert.ok(!readFileSync(f, 'utf8').includes(dash), f);
  }
});

test('no approval script ships and no client-facing text asks for an approval', () => {
  assert.equal(existsSync(join(skillRoot, 'scripts', 'approve-route-budget.mjs')), false);
  for (const f of ['SKILL.md', 'INSTALL.md', 'INSTRUCTIONS.md']) {
    const text = readFileSync(join(skillRoot, f), 'utf8');
    assert.doesNotMatch(text, /budget/i, f);
    assert.doesNotMatch(text, /approve-route/i, f);
  }
  for (const f of ['EXAMPLES.md', 'references/troubleshooting.md', 'references/install-matrix.md']) {
    const text = readFileSync(join(skillRoot, f), 'utf8');
    assert.doesNotMatch(text, /budget|spend limit|run grant/i, f);
  }
  assert.doesNotMatch(readFileSync(join(skillRoot, 'INSTALL.md'), 'utf8'), /spend limit|run grant/i);
  const chamber = join(skillRoot, 'runtime', 'public', 'chamber');
  for (const f of readdirSync(chamber).filter((n) => n.endsWith('.html') || n.endsWith('.js'))) {
    assert.doesNotMatch(readFileSync(join(chamber, f), 'utf8'), /grant-ref|budget|spend limit/i, f);
  }
  // demo-replay.json is recorded sample data; checked separately for the budget line the client would see.
  assert.doesNotMatch(readFileSync(join(chamber, 'demo-replay.json'), 'utf8'), /Budget: /, 'demo-replay.json');
});
