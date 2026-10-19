/**
 * W22-U001: real backend composition tests.
 *
 * Runner:
 *   node --import tsx --test src/service/backend-composition.test.ts
 *
 * Proven here, offline (zero provider calls):
 * - the composed root reports `store`, `route` and `worker` ready with
 *   observations that cite real state (canonical tables, the selected
 *   route, the live worker ledger);
 * - `ui`, `discovery`, `executable` and `packs` remain ready exactly as
 *   W20 bound them;
 * - a bare CouncilFrontDoor keeps the unchanged unbound shape;
 * - start then drain leaves no worker supervisor and no stray temp file
 *   outside the data directory, and the database handle is closed.
 *
 * No provider request, no credential value, no external network and no
 * live advisor turn are claimed.
 */

import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import {
  composeCouncilService,
  startCouncilService,
} from './composition.js';
import { CouncilFrontDoor } from './front-door.js';
import { evaluateServiceReadiness } from './readiness.js';
import { liveCouncilWorkerSupervisors } from '../queue/workers.js';

const FIXED_NOW = '2026-10-19T12:00:00.000Z';
const TENANT = 'tenant-w22';
const COMPANY = 'company-w22';
const nowUtc = (): string => FIXED_NOW;
const TMP_PREFIX = 'w22-u001-backend-';

interface Fixture {
  root: string;
  dataDir: string;
  homeDir: string;
  configPath: string;
}

function makeFixture(): Fixture {
  const root = mkdtempSync(join(tmpdir(), TMP_PREFIX));
  const dataDir = join(root, 'data');
  const homeDir = join(root, 'home');
  const configDir = join(homeDir, '.openclaw');
  mkdirSync(configDir, { recursive: true });
  const configPath = join(configDir, 'openclaw.json');
  writeFileSync(
    configPath,
    `${JSON.stringify(
      {
        models: {
          providers: {
            testprov: {
              baseUrl: 'http://127.0.0.1:9/v1',
              api: 'openai-completions',
              apiKey: 'fixture-presence-only',
              models: [{ id: 'model-a' }],
            },
          },
        },
        agents: { defaults: { model: { primary: 'testprov/model-a' } } },
      },
      null,
      2,
    )}\n`,
    'utf8',
  );
  return { root, dataDir, homeDir, configPath };
}

function options(fixture: Fixture, extra: Record<string, unknown> = {}) {
  return {
    tenantId: TENANT,
    companyId: COMPANY,
    dataDir: fixture.dataDir,
    startedAt: FIXED_NOW,
    nowUtc,
    ports: [0],
    routeId: 'testprov-configured',
    routeHomeDir: fixture.homeDir,
    routeEnv: {},
    // Offline readiness must never call this. The probe only checks that
    // the guarded dispatch port is present.
    providerDispatch: () => {
      throw new Error('provider dispatch must not be called offline');
    },
    ...extra,
  };
}

function byLayer(
  result: Awaited<ReturnType<CouncilFrontDoor['readiness']>>,
): Map<string, (typeof result.layers)[number]> {
  return new Map(result.layers.map((layer) => [layer.layer, layer]));
}

function tempEntries(): string[] {
  return readdirSync(tmpdir()).filter((name) => name.startsWith(TMP_PREFIX));
}

test('composed readiness observes store, route and worker from real state', async () => {
  const fixture = makeFixture();
  const composition = composeCouncilService(options(fixture));
  const outcome = await composition.door.start();
  assert.equal(outcome.outcome, 'started');
  if (outcome.outcome !== 'started') return;
  try {
    const readiness = await composition.door.readiness({ offline: true });
    assert.equal(readiness.origin, outcome.origin);
    assert.equal(readiness.provider_calls, 0, 'offline readiness makes zero provider calls');

    const layers = byLayer(readiness);
    for (const layer of ['discovery', 'executable', 'packs', 'ui']) {
      assert.equal(layers.get(layer)?.state, 'ready', `${layer} remains ready`);
      assert.equal(layers.get(layer)?.blocker, null, `${layer} names no blocker`);
    }

    const store = layers.get('store');
    assert.equal(store?.state, 'ready');
    assert.equal(store?.blocker, null);
    assert.match(store?.artifact ?? '', /18\/18 canonical tables present/);
    assert.match(store?.artifact ?? '', /journal and outbox bound/);

    const route = layers.get('route');
    assert.equal(route?.state, 'ready');
    assert.equal(route?.blocker, null);
    assert.match(route?.artifact ?? '', /testprov-configured configured/);
    assert.match(route?.artifact ?? '', /dispatch port bound/);

    const worker = layers.get('worker');
    assert.equal(worker?.state, 'ready');
    assert.equal(worker?.blocker, null);
    assert.match(worker?.artifact ?? '', /worker supervisor council-service-/);
    assert.match(worker?.artifact ?? '', /poll generation [0-9]+/);
    assert.match(worker?.artifact ?? '', /durable ledger readable/);

    assert.deepEqual(readiness.blocked_layers, []);
    // Token limits are always bound now (built-in defaults), so the
    // deliberation host is ready without any approval step.
    assert.equal(composition.backend.deliberation.readiness().ready, true);
  } finally {
    await composition.door.stop();
    await composition.stop();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('a bare front door keeps the unchanged unbound readiness shape', async () => {
  const fixture = makeFixture();
  const composed = composeCouncilService(options(fixture));
  const bare = new CouncilFrontDoor({ identity: composed.identity, ports: [0] });
  const outcome = await bare.start();
  assert.equal(outcome.outcome, 'started');
  if (outcome.outcome !== 'started') return;
  try {
    const observed = await bare.readiness({ offline: true });
    const control = await evaluateServiceReadiness(
      { nowUtc, origin: outcome.origin },
      { offline: true },
    );

    const normalize = (value: Awaited<ReturnType<CouncilFrontDoor['readiness']>>) =>
      JSON.stringify({
        ...value,
        origin: '<origin>',
        observed_at: '<observed>',
        layers: value.layers.map((layer) => ({
          ...layer,
          observed_at: '<observed>',
        })),
      });
    assert.equal(normalize(observed), normalize(control));
  } finally {
    await bare.stop();
    await composed.stop();
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('start then drain stops the worker and leaves no stray temp file', async () => {
  const fixture = makeFixture();
  const before = tempEntries();
  const started = await startCouncilService({
    ...options(fixture),
    handleSignals: false,
  });
  try {
    assert.equal(started.outcome.outcome, 'started');
    assert.equal(started.composition.door.getState(), 'running');
    const readiness = await started.composition.door.readiness({ offline: true });
    assert.equal(byLayer(readiness).get('worker')?.state, 'ready');
    const supervisors = started.composition.backend.workers?.supervisor_id ?? '';
    assert.ok(liveCouncilWorkerSupervisors().includes(supervisors));
  } finally {
    await started.stop();
  }

  assert.equal(started.composition.door.getState(), 'stopped');
  assert.equal(started.composition.backend.workers?.running, false);
  const supervisors = started.composition.backend.workers?.supervisor_id ?? '';
  assert.equal(
    liveCouncilWorkerSupervisors().includes(supervisors),
    false,
    'the supervisor is unregistered after drain',
  );
  assert.throws(
    () =>
      started.composition.backend.database.read((handle) =>
        handle.prepare('SELECT 1 AS closed').get(),
      ),
    'the canonical database handle is closed exactly once',
  );

  const after = tempEntries();
  assert.deepEqual(
    after.filter((name) => !before.includes(name)),
    [],
    'no stray temp file outside the data directory',
  );
  rmSync(fixture.root, { recursive: true, force: true });
});
