/**
 * W30 single executor: one session's round jobs are claimed and run by
 * exactly one executor at a time. Each claim raises the session lease
 * epoch, so a second claim while an operation is live fences that
 * operation's settle (BUDGET_LEASE_FENCED) and loses a paid response.
 *
 * Runner:
 *   node --import tsx --test tests/single-executor.test.ts
 *
 * Offline: the transport is the deterministic fixture behind a short
 * delay, so the service supervisor and runSession really overlap.
 */

import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import type { RouteBudgetEntry } from '../src/budgets/route-budget.js';
import { DeterministicFixtureTransport } from '../src/cli/fixture-transport.js';
import type { ModelTransport } from '../src/cli/host-ports.js';
import { startCouncilService } from '../src/service/composition.js';

const ENTRY: RouteBudgetEntry = {
  route_id: 'claude-nine-configured',
  model: null,
  context_window_tokens: 200_000,
  max_output_tokens: 8_000,
  measured_min_bytes_per_token: 3.1,
  safety_factor: 0.8,
  response_schema_bytes: 10_159,
  measured_at: '2026-10-19T12:00:00.000Z',
  measurement_basis: 'fixture',
};

class SlowFixtureTransport implements ModelTransport {
  private readonly inner = new DeterministicFixtureTransport();
  active = 0;
  maxActive = 0;
  calls = 0;
  async generate(request: Parameters<ModelTransport['generate']>[0]) {
    this.calls += 1;
    this.active += 1;
    this.maxActive = Math.max(this.maxActive, this.active);
    try {
      await new Promise((resolve) => setTimeout(resolve, 120));
      return await this.inner.generate(request);
    } finally {
      this.active -= 1;
    }
  }
}

test('a slow real-shaped round settles every operation: one executor, no fenced settle', async () => {
  const root = mkdtempSync(join(tmpdir(), 'w30-single-'));
  const dataDir = join(root, 'data');
  const home = join(root, 'home');
  for (const dir of ['.claude-nine', '.claude', '.openclaw', join('.local', 'bin')]) {
    mkdirSync(join(home, dir), { recursive: true });
  }
  for (const name of ['claude-nine', 'claude']) {
    const exe = join(home, '.local', 'bin', name);
    writeFileSync(exe, '#!/bin/sh\nexit 0\n', 'utf8');
    chmodSync(exe, 0o755);
  }
  writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify({ models: { providers: {} } }), 'utf8');
  const configPath = join(root, 'route-budgets.json');
  writeFileSync(configPath, JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries: [ENTRY] }), 'utf8');
  const transport = new SlowFixtureTransport();
  const service = await startCouncilService({
    tenantId: 'tenant-w30',
    companyId: 'company-w30',
    dataDir,
    ports: [0],
    routeHomeDir: home,
    routeEnv: { PATH: '/usr/bin:/bin' } as NodeJS.ProcessEnv,
    routeBudgetConfigPath: configPath,
    resolveTransport: () => transport,
    workerPollIntervalMs: 20,
    handleSignals: false,
  });
  try {
    assert.equal(service.outcome.outcome, 'started');
    const origin = service.origin as string;
    const accepted = await fetch(`${origin}/api/council/convene`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sample: true, route_id: ENTRY.route_id }),
    });
    assert.equal(accepted.status, 202);
    const { session_id: sessionId } = (await accepted.json()) as { session_id: string };

    const backend = service.composition.backend;
    const deadline = Date.now() + 60_000;
    let state = '';
    while (Date.now() < deadline) {
      state = backend.repositories.getSession(backend.ownerEnvelope, sessionId)?.state.state ?? '';
      if (['COMPLETED', 'BLOCKED', 'FAILED'].includes(state)) break;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    const rows = backend.database.read((handle) => ({
      attempts: handle
        .prepare(`SELECT status, COUNT(*) AS n FROM council_provider_attempts GROUP BY status`)
        .all(),
      stuck: handle
        .prepare(`SELECT COUNT(*) AS n FROM council_jobs WHERE state IN ('leased','running')`)
        .get(),
    })) as { attempts: Array<{ status: string; n: number }>; stuck: { n: number } };

    assert.equal(state, 'COMPLETED', JSON.stringify(rows));
    assert.equal(transport.maxActive, 1, 'one session runs one operation at a time');
    assert.deepEqual(rows.attempts.filter((a) => a.status !== 'accepted'), []);
    assert.equal(rows.stuck.n, 0);
    const workerErrors = backend.database.read((handle) =>
      handle
        .prepare(`SELECT payload_json FROM council_events WHERE payload_json LIKE '%worker_error%'`)
        .all(),
    );
    assert.deepEqual(workerErrors, [], 'no worker error was journaled');
  } finally {
    await service.stop();
    rmSync(root, { recursive: true, force: true });
  }
});

/**
 * A fenced settle is never silent: the session epoch moves while the first
 * operation is in flight (a second process, or an expired-lease recovery).
 * 'valid' output reaches the 'fenced' outcome path; 'invalid' output reaches
 * the BUDGET_LEASE_FENCED throw path. Each must leave exactly one
 * worker_error journal row and one council-worker stderr line, and the paid
 * reservation must stay counted, never lapse to free.
 */
async function fencedSettle(mode: 'valid' | 'invalid') {
  const root = mkdtempSync(join(tmpdir(), 'w30-fence-'));
  const dataDir = join(root, 'data');
  const home = join(root, 'home');
  for (const dir of ['.claude-nine', '.claude', '.openclaw', join('.local', 'bin')]) {
    mkdirSync(join(home, dir), { recursive: true });
  }
  for (const name of ['claude-nine', 'claude']) {
    const exe = join(home, '.local', 'bin', name);
    writeFileSync(exe, '#!/bin/sh\nexit 0\n', 'utf8');
    chmodSync(exe, 0o755);
  }
  writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify({ models: { providers: {} } }), 'utf8');
  const configPath = join(root, 'route-budgets.json');
  writeFileSync(configPath, JSON.stringify({ schema: 'wise-elders.route-budgets/v1', entries: [ENTRY] }), 'utf8');
  const stderrLines: string[] = [];
  const realWrite = process.stderr.write.bind(process.stderr);
  (process.stderr as { write: unknown }).write = (chunk: unknown, ...rest: unknown[]) => {
    stderrLines.push(String(chunk));
    return (realWrite as (...a: unknown[]) => boolean)(chunk, ...rest);
  };
  const inner = new DeterministicFixtureTransport();
  let backend: { repositories: any; ownerEnvelope: any; deliberation: any; database: any } | null = null;
  let intruded = false;
  const transport: ModelTransport = {
    async generate(request) {
      if (!intruded && backend) {
        intruded = true;
        const session = backend.repositories.getSession(backend.ownerEnvelope, request.session_id);
        backend.deliberation.runner['bumpSessionEpoch'](backend.ownerEnvelope, session, 'intruder', 'intruder-job');
      }
      const response = await inner.generate(request);
      return mode === 'invalid' ? { ...response, text: '{"not":"a card"}' } : response;
    },
  };
  const service = await startCouncilService({
    tenantId: 'tenant-w30',
    companyId: 'company-w30',
    dataDir,
    ports: [0],
    routeHomeDir: home,
    routeEnv: { PATH: '/usr/bin:/bin' } as NodeJS.ProcessEnv,
    routeBudgetConfigPath: configPath,
    resolveTransport: () => transport,
    workerPollIntervalMs: 20,
    handleSignals: false,
  });
  try {
    backend = service.composition.backend as never;
    const accepted = await fetch(`${service.origin}/api/council/convene`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sample: true, route_id: ENTRY.route_id }),
    });
    const { session_id: sessionId } = (await accepted.json()) as { session_id: string };
    const deadline = Date.now() + 60_000;
    while (Date.now() < deadline) {
      const state = backend!.repositories.getSession(backend!.ownerEnvelope, sessionId)?.state.state ?? '';
      if (['COMPLETED', 'BLOCKED', 'FAILED'].includes(state)) break;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
    return backend!.database.read((handle: any) => ({
      intruded,
      workerErrors: handle
        .prepare(`SELECT payload_json FROM council_events WHERE payload_json LIKE '%"worker_error"%'`)
        .all()
        .map((row: { payload_json: string }) => JSON.parse(row.payload_json)),
      reservations: handle
        .prepare(`SELECT state, COUNT(*) AS n FROM council_budget_reservations GROUP BY state`)
        .all(),
      stderr: stderrLines.filter((line) => line.includes('council-worker')),
    })) as {
      intruded: boolean;
      workerErrors: Array<{ code: string | null }>;
      reservations: Array<{ state: string; n: number }>;
      stderr: string[];
    };
  } finally {
    (process.stderr as { write: unknown }).write = realWrite;
    await service.stop();
    rmSync(root, { recursive: true, force: true });
  }
}

test('a fenced late result (outcome path) is journaled and logged, and its reservation stays counted', async () => {
  const seen = await fencedSettle('valid');
  assert.equal(seen.intruded, true);
  const fenced = seen.workerErrors.filter((e) => e.code === 'OPERATION_LEASE_FENCED');
  assert.equal(fenced.length, 1, JSON.stringify(seen));
  assert.ok(seen.stderr.some((line) => line.includes('OPERATION_LEASE_FENCED')), JSON.stringify(seen.stderr));
  assert.equal(seen.reservations.filter((r) => r.state === 'expired').length, 0);
  assert.ok(seen.reservations.some((r) => r.state === 'unknown'), JSON.stringify(seen.reservations));
});

test('a fenced settle that throws (BUDGET_LEASE_FENCED) is journaled and logged', async () => {
  const seen = await fencedSettle('invalid');
  assert.equal(seen.intruded, true);
  assert.ok(seen.workerErrors.length >= 1, JSON.stringify(seen));
  assert.ok(seen.stderr.length >= 1, JSON.stringify(seen.stderr));
  assert.equal(seen.workerErrors.length, seen.stderr.length, 'one stderr line per journaled worker error');
});
