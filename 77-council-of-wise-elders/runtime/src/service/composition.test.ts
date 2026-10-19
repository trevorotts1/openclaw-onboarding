/**
 * W20-U001: composition-root tests (F5).
 *
 * Runner (the runtime's own test runner):
 *   node --import tsx --test src/service/composition.test.ts
 *
 * Tier A only: one loopback listener on an ephemeral port, a temporary data
 * directory removed after each case, and the real on-disk runtime assets.
 * No provider request, no credential, no external network, no installed
 * service and no live session are claimed.
 *
 * Proven here:
 * - the composition root binds discovery/executable/packs/ui truthfully and
 *   (W22-U001) opens the real backend: store and worker are observed ready,
 *   and route reports its named configuration state instead of the old
 *   unbound probe;
 * - with no probes bound the readiness output keeps exactly the pre-change
 *   six-unknown + UI_NOT_BUNDLED shape;
 * - identity and health routes behave byte-identically to a bare front door;
 * - an injected admission sink is bound and receives admissions;
 * - startCouncilService starts and stops the door (signals disabled).
 */

import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import type { RouteBudgetEntry } from '../budgets/route-budget.js';
import { composeCouncilService, startCouncilService } from './composition.js';
import { CouncilFrontDoor } from './front-door.js';
import { evaluateServiceReadiness } from './readiness.js';
import type { AdmissionRequest } from './types.js';

const FIXED_NOW = '2026-10-19T12:00:00.000Z';
const TENANT = 'tenant-w20';
const COMPANY = 'company-w20';
const nowUtc = (): string => FIXED_NOW;

function options(dataDir: string) {
  return {
    tenantId: TENANT,
    companyId: COMPANY,
    dataDir,
    startedAt: FIXED_NOW,
    nowUtc,
    ports: [0],
    // Deterministic, hermetic route discovery: an empty home means no
    // configured route, so `route` reports a named blocker rather than
    // whichever route this machine happens to have.
    routeHomeDir: join(dataDir, 'empty-route-home'),
    routeEnv: {} as NodeJS.ProcessEnv,
  };
}

async function withComposed<T>(
  body: (input: {
    composition: ReturnType<typeof composeCouncilService>;
    origin: string;
    dataDir: string;
  }) => Promise<T>,
): Promise<T> {
  const dataDir = mkdtempSync(join(tmpdir(), 'w20-u001-composition-'));
  const composition = composeCouncilService(options(dataDir));
  const outcome = await composition.door.start();
  assert.equal(outcome.outcome, 'started');
  if (outcome.outcome !== 'started') throw new Error('unreachable');
  try {
    return await body({ composition, origin: outcome.origin, dataDir });
  } finally {
    await composition.door.stop();
    await composition.stop();
    rmSync(dataDir, { recursive: true, force: true });
  }
}

function byLayer(
  result: Awaited<ReturnType<CouncilFrontDoor['readiness']>>,
): Map<string, (typeof result.layers)[number]> {
  return new Map(result.layers.map((layer) => [layer.layer, layer]));
}

test('composition root binds the real backend and the W20 probes', async () => {
  await withComposed(async ({ composition, origin }) => {
    const readiness = await composition.door.readiness({ offline: true });
    assert.equal(readiness.origin, origin);
    assert.equal(readiness.provider_calls, 0);
    assert.equal(readiness.usable, false, 'a blocked route keeps usable honest');

    const layers = byLayer(readiness);
    for (const layer of ['discovery', 'executable', 'packs', 'ui']) {
      assert.equal(layers.get(layer)?.state, 'ready', `${layer} is observed ready`);
      assert.equal(layers.get(layer)?.blocker, null, `${layer} names no blocker`);
    }

    // W22-U001: the backend is real, not unbound.
    assert.equal(layers.get('store')?.state, 'ready');
    assert.match(layers.get('store')?.artifact ?? '', /18\/18 canonical tables/);
    assert.equal(layers.get('worker')?.state, 'ready');
    assert.match(layers.get('worker')?.artifact ?? '', /durable ledger readable/);
    assert.equal(layers.get('route')?.state, 'blocked');
    assert.equal(
      layers.get('route')?.blocker?.code,
      'ROUTE_NOT_CONFIGURED',
      'route reports its named configuration state, never the unbound probe',
    );

    assert.equal(
      layers.get('ui')?.artifact,
      'runtime/public/chamber/index.html',
    );
    assert.ok((layers.get('packs')?.artifact ?? '').includes('9/9 advisor packs'));
    assert.ok((layers.get('discovery')?.artifact ?? '').includes(origin));
  });
});

test('with no probes bound the pre-change six-unknown shape is unchanged', async () => {
  const result = await evaluateServiceReadiness(
    { nowUtc, origin: 'http://127.0.0.1:43999' },
    { offline: true },
  );
  const layers = byLayer(result);

  for (const layer of ['discovery', 'executable', 'store', 'route', 'packs', 'worker']) {
    assert.equal(layers.get(layer)?.state, 'unknown', `${layer} stays unknown`);
    assert.equal(layers.get(layer)?.blocker?.code, 'READINESS_PROBE_NOT_BOUND');
  }
  assert.equal(layers.get('ui')?.state, 'blocked');
  assert.equal(layers.get('ui')?.blocker?.code, 'UI_NOT_BUNDLED');

  assert.equal(result.usable, false);
  assert.deepEqual(result.blocked_layers, ['ui']);
  assert.equal(result.provider_calls, 0);
});

test('identity and health routes behave byte-identically to a bare front door', async () => {
  await withComposed(async ({ composition, origin }) => {
    const control = new CouncilFrontDoor({
      identity: composition.identity,
      ports: [0],
    });
    const controlOutcome = await control.start();
    assert.equal(controlOutcome.outcome, 'started');
    if (controlOutcome.outcome !== 'started') return;
    try {
      for (const path of ['/healthz', '/api/council/health', '/api/council/service/identity']) {
        const composedResponse = await fetch(`${origin}${path}`);
        const controlResponse = await fetch(`${controlOutcome.origin}${path}`);
        assert.equal(composedResponse.status, controlResponse.status, `${path} status`);
        assert.equal(
          composedResponse.headers.get('content-type'),
          controlResponse.headers.get('content-type'),
          `${path} content-type`,
        );
        const composedBody = (await composedResponse.text()).replaceAll(origin, '<origin>');
        const controlBody = (await controlResponse.text()).replaceAll(
          controlOutcome.origin,
          '<origin>',
        );
        assert.equal(composedBody, controlBody, `${path} body`);
      }

      const health = await (await fetch(`${origin}/healthz`)).json() as Record<string, unknown>;
      assert.equal(health.ok, true);
      assert.equal(health.state, 'running');
      assert.equal(health.draining, false);
      assert.equal(health.api_version, 'v1');
    } finally {
      await control.stop();
    }
  });
});

test('an admission sink supplied to the root receives admissions', async () => {
  const seen: AdmissionRequest[] = [];
  const dataDir = mkdtempSync(join(tmpdir(), 'w20-u001-sink-'));
  const composition = composeCouncilService({
    ...options(dataDir),
    admissionSink: async (request) => {
      seen.push(request);
      return { accepted_by: 'test-authority', operation_id: request.operation_id };
    },
  });
  const outcome = await composition.door.start();
  assert.equal(outcome.outcome, 'started');
  if (outcome.outcome !== 'started') return;
  try {
    const response = await fetch(`${outcome.origin}/api/council/admissions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ session_id: 'session-w20', operation_id: 'operation-w20' }),
    });
    assert.equal(response.status, 202);
    const decision = await response.json() as Record<string, unknown>;
    assert.equal(decision.accepted, true);
    assert.deepEqual(seen, [
      { session_id: 'session-w20', operation_id: 'operation-w20' },
    ]);
  } finally {
    await composition.door.stop();
    await composition.stop();
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test('startCouncilService starts and stops the door without installing signals', async () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w20-u001-start-'));
  const started = await startCouncilService({ ...options(dataDir), handleSignals: false });
  try {
    assert.equal(started.outcome.outcome, 'started');
    assert.equal(started.composition.door.getState(), 'running');
    assert.equal(started.origin, started.composition.door.getOrigin());
    assert.ok((started.port ?? 0) > 0);
  } finally {
    await started.stop();
    rmSync(dataDir, { recursive: true, force: true });
  }
  assert.equal(started.composition.door.getState(), 'stopped');
});

// ------------------------------------------------- W28 service wiring

/** A temp host with all three configured routes: two harnesses and DeepSeek. */
function threeRouteHome(root: string): string {
  const home = join(root, 'home');
  for (const dir of ['.claude-nine', '.claude', '.openclaw', join('.local', 'bin')]) {
    mkdirSync(join(home, dir), { recursive: true });
  }
  for (const name of ['claude-nine', 'claude']) {
    const exe = join(home, '.local', 'bin', name);
    writeFileSync(exe, '#!/bin/sh\nexit 0\n', 'utf8');
    chmodSync(exe, 0o755);
  }
  writeFileSync(
    join(home, '.openclaw', 'openclaw.json'),
    JSON.stringify({
      models: {
        providers: {
          deepseek: {
            baseUrl: 'https://api.deepseek.test/v1',
            api: 'openai-completions',
            apiKey: 'fixture-key-not-real',
            models: [{ id: 'deepseek-flash' }],
          },
        },
      },
    }),
    'utf8',
  );
  return home;
}

function budgetEntry(extra: Partial<RouteBudgetEntry> = {}): RouteBudgetEntry {
  return {
    route_id: 'claude-nine-configured',
    model: null,
    context_window_tokens: 200_000,
    max_output_tokens: 8_000,
    measured_min_bytes_per_token: 3.1,
    safety_factor: 0.8,
    response_schema_bytes: 10_159,
    measured_at: '2026-10-19T12:00:00.000Z',
    measurement_basis: 'fixture',
    ...extra,
  };
}

function writeBudgetConfig(path: string, entries: RouteBudgetEntry[]): void {
  writeFileSync(
    path,
    JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries }),
    'utf8',
  );
}

test('three composable routes: route layer is ready, the route is chosen per session, nothing is ambiguous', async () => {
  const root = mkdtempSync(join(tmpdir(), 'w28-wiring-routes-'));
  const dataDir = join(root, 'data');
  const composition = composeCouncilService({
    ...options(dataDir),
    routeHomeDir: threeRouteHome(root),
    routeEnv: { PATH: '/usr/bin:/bin' } as NodeJS.ProcessEnv,
  });
  const outcome = await composition.door.start();
  assert.equal(outcome.outcome, 'started');
  if (outcome.outcome !== 'started') return;
  try {
    const route = byLayer(await composition.door.readiness({ offline: true })).get('route');
    assert.equal(route?.state, 'ready');
    assert.equal(route?.blocker, null);
    for (const id of ['claude-nine-configured', 'claude-configured', 'deepseek-configured']) {
      assert.match(route?.artifact ?? '', new RegExp(`${id} configured`));
    }
    assert.match(route?.artifact ?? '', /3\/3 route\(s\) composable/);
    assert.match(route?.artifact ?? '', /chosen per session/);
    assert.doesNotMatch(JSON.stringify(route), /ROUTE_SELECTION_AMBIGUOUS/);

    // GET /api/council/routes offers every route and the harness defaults.
    const routes = (await (await fetch(`${outcome.origin}/api/council/routes`)).json()) as {
      routes: Array<{ route_id: string; composable: boolean; default_for: string[] }>;
      harness_defaults: Record<string, { route_id: string }>;
    };
    assert.deepEqual(
      routes.routes.map((r) => r.route_id).sort(),
      ['claude-configured', 'claude-nine-configured', 'deepseek-configured'],
    );
    assert.ok(routes.routes.every((r) => r.composable));
    assert.deepEqual(
      routes.routes.find((r) => r.route_id === 'deepseek-configured')?.default_for,
      ['deepseek'],
    );
    assert.equal(routes.harness_defaults['claude-code'].route_id, 'claude-configured');
    assert.equal('budgets' in routes, false, 'no approval state is offered to the client');
  } finally {
    await composition.door.stop();
    await composition.stop();
    rmSync(root, { recursive: true, force: true });
  }
});

test('a fresh install is ready with no approval step, measured or not', async () => {
  const root = mkdtempSync(join(tmpdir(), 'w28-wiring-limits-'));
  const dataDir = join(root, 'data');
  mkdirSync(dataDir, { recursive: true });
  const configPath = join(root, 'route-budgets.json');
  writeBudgetConfig(configPath, [budgetEntry()]);
  const composition = composeCouncilService({
    ...options(dataDir),
    routeHomeDir: threeRouteHome(root),
    routeEnv: { PATH: '/usr/bin:/bin' } as NodeJS.ProcessEnv,
    routeBudgetConfigPath: configPath,
  });
  const outcome = await composition.door.start();
  assert.equal(outcome.outcome, 'started');
  if (outcome.outcome !== 'started') return;
  try {
    const deliberation = composition.backend.deliberation;
    const ready = deliberation.readiness();
    assert.equal(ready.ready, true, JSON.stringify(ready.checks.filter((c) => !c.bound)));
    assert.equal(ready.checks.find((c) => c.name === 'route_budget')?.bound, true);
    const route = byLayer(await composition.door.readiness({ offline: true })).get('route');
    assert.equal(route?.state, 'ready');
    assert.doesNotMatch(route?.artifact ?? '', /approv/i);
    // Changing the numbers (or having none) never un-readies the council.
    writeBudgetConfig(configPath, [budgetEntry({ measured_min_bytes_per_token: null })]);
    assert.equal(deliberation.readiness().ready, true);
    assert.equal(existsSync(join(dataDir, 'route-budget-approvals.json')), false);
  } finally {
    await composition.door.stop();
    await composition.stop();
    rmSync(root, { recursive: true, force: true });
  }
});

test('no readiness path emits the retired ROUTE_SELECTION_AMBIGUOUS code', async () => {
  await withComposed(async ({ composition }) => {
    const readiness = await composition.door.readiness({ offline: true });
    assert.doesNotMatch(JSON.stringify(readiness), /ROUTE_SELECTION_AMBIGUOUS/);
  });
});
