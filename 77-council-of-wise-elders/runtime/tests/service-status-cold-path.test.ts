/**
 * W27 /status cold-path regression.
 *
 * Runner (picked up by `npm test`):
 *   node --import tsx --test tests/service-status-cold-path.test.ts
 *
 * Tier A only: loopback HTTP on an ephemeral port with an injected probe.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import { CouncilFrontDoor } from '../src/service/front-door.js';
import { buildServiceIdentity } from '../src/service/identity.js';
import type { ReadinessObservation } from '../src/service/readiness.js';

const FIXED_NOW = '2026-10-19T12:00:00.000Z';
const ready: ReadinessObservation = { state: 'ready', artifact: 'observed' };

test('start pre-warms readiness so the first GET /status does not run cold probes', async () => {
  let probeRuns = 0;
  const door = new CouncilFrontDoor({
    identity: buildServiceIdentity({
      tenant_id: 'tenant-w27',
      company_id: 'company-w27',
      data_dir: '/tmp/w27-u001-data',
      started_at: FIXED_NOW,
    }),
    host: '127.0.0.1',
    ports: [0],
    readiness: {
      nowUtc: () => FIXED_NOW,
      store: () => {
        probeRuns += 1;
        return ready;
      },
    },
  });
  try {
    const started = await door.start();
    assert.equal(started.outcome, 'started');
    assert.equal(probeRuns, 1, 'readiness probes ran once during start, before any request');
    const response = await fetch(`${started.origin}/status`);
    assert.equal(response.status, 200);
    assert.equal(probeRuns, 2, 'the request re-observes live state (no stale cache)');
  } finally {
    await door.stop();
  }
});
