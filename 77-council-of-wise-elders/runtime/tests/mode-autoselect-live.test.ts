/**
 * W77S AUTO-MODE-1062 repair (1064): the selector runs in the SHIPPED
 * convene path, not only in the unwired convene-flow.
 *
 * The live path is:
 *   POST /api/council/convene
 *     -> front-door handleConvene
 *     -> conveningPort.convene
 *     -> createCouncilDriver().convene
 *     -> resolveModeSelection (flow/mode-select.ts selectMode)
 *     -> session spec.mode / response mode_selection / audit line.
 *
 * Proven here, on the real composition root and the real loopback listener
 * with the deterministic fixture transport (no provider, no credential):
 *
 *   - an explicit client mode wins verbatim (source = 'client');
 *   - with no mode, the question decides (source = 'auto') and the response,
 *     the session record and the audit line all carry mode + source + reason;
 *   - a question with no text falls back to medium, source auto, and says so.
 *
 * Runner: node --import tsx --test tests/mode-autoselect-live.test.ts
 */

import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { DeterministicFixtureTransport, buildSampleSession } from '../src/cli/fixture-transport.js';
import { SESSION_MODES } from '../src/contracts/enums.js';
import { resolveModeSelection } from '../src/service/driver.js';
import { startCouncilService, type StartedCouncilService } from '../src/service/composition.js';

const TENANT = 'tenant-1064';
const COMPANY = 'company-1064';
const ROUTE = 'claude-nine-configured';

/** Classified light by the selector: one quick lookup, nothing at stake. */
const SIMPLE_QUESTION = 'What should I name the folder for this month invoices?';

/** Classified heavy: irreversible, several factors, several domains. */
const HEAVY_QUESTION =
  'Should we accept the acquisition offer, raise another investment round, or file for bankruptcy, given the expiring lease, the lawsuit, and the payroll deadline?';

interface Fixture {
  root: string;
  dataDir: string;
  service: StartedCouncilService;
  origin: string;
}

async function startFixture(): Promise<Fixture> {
  const root = mkdtempSync(join(tmpdir(), 'w77s-1064-convene-'));
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
  writeFileSync(
    configPath,
    JSON.stringify({
      schema: 'wise-elders.route-budgets/v1',
      entries: [
        {
          route_id: ROUTE,
          model: null,
          context_window_tokens: 200_000,
          max_output_tokens: 8_000,
          measured_min_bytes_per_token: 3.1,
          safety_factor: 0.8,
          response_schema_bytes: 10_159,
          measured_at: '2026-10-19T12:00:00.000Z',
          measurement_basis: 'fixture',
        },
      ],
    }),
    'utf8',
  );
  const service = await startCouncilService({
    tenantId: TENANT,
    companyId: COMPANY,
    dataDir,
    ports: [0],
    routeHomeDir: home,
    routeEnv: { PATH: '/usr/bin:/bin' } as NodeJS.ProcessEnv,
    routeBudgetConfigPath: configPath,
    resolveTransport: () => new DeterministicFixtureTransport(),
    workerPollIntervalMs: 20,
    handleSignals: false,
  });
  assert.equal(service.outcome.outcome, 'started');
  assert.ok(service.origin);
  return { root, dataDir, service, origin: service.origin as string };
}

async function stopFixture(fixture: Fixture): Promise<void> {
  await fixture.service.stop();
  rmSync(fixture.root, { recursive: true, force: true });
}

function briefWith(question: string) {
  return { ...buildSampleSession().brief, question };
}

interface ConveneBody {
  session_id: string;
  mode: string;
  mode_selection: { mode: string; source: string; reason: string };
  session_path: string;
}

async function convene(origin: string, body: unknown): Promise<{ status: number; body: ConveneBody }> {
  const response = await fetch(`${origin}/api/council/convene`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  return { status: response.status, body: JSON.parse(text) as ConveneBody };
}

/** Wait until the session leaves the running states (bounded). */
async function settled(origin: string, sessionPath: string, timeoutMs = 60_000): Promise<{
  spec: { mode: string };
  state: { state: string; mode: string };
}> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const response = await fetch(`${origin}${sessionPath}`);
    assert.equal(response.status, 200);
    const payload = (await response.json()) as {
      session: { spec: { mode: string }; state: { state: string; mode: string } };
    };
    if (['COMPLETED', 'BLOCKED', 'CANCELLED'].includes(payload.session.state.state)) {
      return payload.session;
    }
    if (Date.now() > deadline) throw new Error(`session did not settle: ${payload.session.state.state}`);
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

// ------------------------------------------------- the resolver contract

test('an explicit client mode wins verbatim for all seven session modes', () => {
  for (const mode of SESSION_MODES) {
    const selection = resolveModeSelection(mode, HEAVY_QUESTION);
    assert.equal(selection.mode, mode, `${mode}: client choice must be returned verbatim`);
    assert.equal(selection.source, 'client', `${mode}: source must be client`);
    assert.match(selection.reason, /client/iu, `${mode}: reason must name the client choice`);
  }
});

test('a question with no text falls back to medium with an honest reason', () => {
  for (const question of ['', '   ']) {
    const selection = resolveModeSelection(undefined, question);
    assert.equal(selection.mode, 'medium');
    assert.equal(selection.source, 'auto');
    assert.match(selection.reason, /no question text|medium/iu);
  }
});

test('with no explicit mode the question classifies itself', () => {
  const simple = resolveModeSelection(undefined, SIMPLE_QUESTION);
  assert.deepEqual({ mode: simple.mode, source: simple.source }, { mode: 'light', source: 'auto' });
  const heavy = resolveModeSelection(undefined, HEAVY_QUESTION);
  assert.deepEqual({ mode: heavy.mode, source: heavy.source }, { mode: 'heavy', source: 'auto' });
  assert.ok(heavy.reason.trim().length > 0);
});

// ------------------------------------------------------ the live path

test('convene with no mode classifies the question: response, session record and audit agree', async () => {
  const fixture = await startFixture();
  try {
    const accepted = await convene(fixture.origin, {
      brief: briefWith(SIMPLE_QUESTION),
      route_id: ROUTE,
      requested_by: 'fixture-client',
    });
    assert.equal(accepted.status, 202);
    assert.equal(accepted.body.mode, 'light', 'the run uses the auto-selected mode');
    assert.deepEqual(
      { mode: accepted.body.mode_selection.mode, source: accepted.body.mode_selection.source },
      { mode: 'light', source: 'auto' },
    );
    assert.ok(
      accepted.body.mode_selection.reason.trim().length > 0,
      'the client is told why this mode was chosen',
    );

    const record = await settled(fixture.origin, accepted.body.session_path);
    assert.equal(record.spec.mode, 'light', 'the session record carries the resolved mode');
    assert.equal(record.state.mode, 'light');
    assert.equal(record.state.state, 'COMPLETED');

    const audit = readFileSync(join(fixture.dataDir, 'convening-audit.jsonl'), 'utf8')
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line) as Record<string, unknown>);
    assert.equal(audit.length, 1);
    assert.equal(audit[0]!.session_id, accepted.body.session_id);
    assert.equal(audit[0]!.mode, 'light');
    assert.equal(audit[0]!.mode_source, 'auto');
    assert.equal(audit[0]!.mode_reason, accepted.body.mode_selection.reason);
  } finally {
    await stopFixture(fixture);
  }
});

test('an explicit client mode still wins verbatim over the automatic classification', async () => {
  const fixture = await startFixture();
  try {
    // HEAVY_QUESTION classifies as heavy; the client asks for medium instead.
    const accepted = await convene(fixture.origin, {
      brief: briefWith(HEAVY_QUESTION),
      mode: 'medium',
      route_id: ROUTE,
      requested_by: 'fixture-client',
    });
    assert.equal(accepted.status, 202);
    assert.equal(accepted.body.mode, 'medium');
    assert.deepEqual(
      { mode: accepted.body.mode_selection.mode, source: accepted.body.mode_selection.source },
      { mode: 'medium', source: 'client' },
    );
    assert.match(accepted.body.mode_selection.reason, /client/iu);

    const record = await settled(fixture.origin, accepted.body.session_path);
    assert.equal(record.spec.mode, 'medium');
    assert.equal(record.state.state, 'COMPLETED');
  } finally {
    await stopFixture(fixture);
  }
});

test('the built-in sample keeps its fixture mode and says so', async () => {
  const fixture = await startFixture();
  try {
    const accepted = await convene(fixture.origin, {
      sample: true,
      route_id: ROUTE,
      requested_by: 'fixture-client',
    });
    assert.equal(accepted.status, 202);
    assert.equal(accepted.body.mode, 'full');
    assert.equal(accepted.body.mode_selection.mode, 'full');
    assert.equal(accepted.body.mode_selection.source, 'auto');
    assert.match(accepted.body.mode_selection.reason, /sample/iu);
    await settled(fixture.origin, accepted.body.session_path);
  } finally {
    await stopFixture(fixture);
  }
});
