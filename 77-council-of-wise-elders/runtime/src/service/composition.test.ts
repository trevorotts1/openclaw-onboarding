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
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

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
