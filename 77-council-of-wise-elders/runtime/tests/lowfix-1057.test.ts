/**
 * LOWFIX-1057: the five review findings of the 1.0.56 council-modes build.
 *
 * Regression proof only — every case fails on origin/main 7477816dc:
 * - budget.snapshot() reports the session grant cap, not the service maximum;
 * - the production composition really runs CWE-028 capacity admission;
 * - readiness treats a route usable once a model is named as ready;
 * - a blocked council size scopes its cause window to the current pass.
 */
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import type { SessionStateRecord } from '../src/contracts/index.js';
import { DEFAULT_COUNCIL_SETTINGS, type CouncilSettings } from '../src/contracts/schemas.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import { parsePersistenceConfig } from '../src/persistence/config.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../src/persistence/index.js';
import { CouncilRepositories } from '../src/persistence/repositories.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';
import { DurableBudgetService } from '../src/budgets/index.js';
import { RuntimeCapacity } from '../src/queue/capacity.js';
import { DEFAULT_WAVE_CAPACITY } from '../src/protocol/composition.js';
import { composeCouncilService } from '../src/service/composition.js';
import { buildBlockedReason } from '../src/service/sessions.js';

const nowUtc = '2026-10-25T12:00:00.000Z';
const clock = { nowUtc: () => nowUtc };
let idCounter = 0;
const ids = { newId: () => `lowfix-${(idCounter += 1).toString().padStart(4, '0')}` };

function tempDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `lowfix-1057-${label}-`));
}

function sampleStored(sessionId: string): StoredSession {
  const sample = buildSampleSession();
  const spec = { ...sample.spec, session_id: sessionId };
  const brief = { ...sample.brief, session_id: sessionId };
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: spec.session_id,
    mode: spec.mode,
    state: 'DRAFT',
    state_version: 0,
    brief_revision: brief.revision,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: spec.created_at,
  };
  return { spec, brief, scope: sample.scope, state, sample: false };
}

/** The convening settings the service really ships (100/100/100 guards). */
const CONVENING_SETTINGS: CouncilSettings = {
  ...DEFAULT_COUNCIL_SETTINGS,
  max_session_provider_requests: 100,
  max_output_repair_requests: 100,
  max_transport_retries_total: 100,
};

/** Insert the durable run grant the approval service would issue. */
function insertGrant(
  db: CouncilDatabase,
  session: StoredSession,
  grantId: string,
  ceilings: { max_provider_requests: number; max_output_repairs: number; max_transport_retries: number } | null,
): void {
  db.write((handle) => {
    handle
      .prepare(
        `INSERT INTO council_approvals
           (tenant_id, company_id, id, kind, session_id, action_proposal_id,
            authority_mode, purpose, actor_subject, actor_role,
            parent_approval_id, scope_proof, current_plan_hash, verdict_hash,
            max_cost_minor, currency, seat_allowlist_json,
            company_scope_verified, status, issued_at, expires_at,
            revoked_at, revoked_by, consumed_at)
         VALUES (?, ?, ?, 'run_grant', ?, NULL, 'local_interactive_owner',
                 'council_run', 'owner-1', 'owner', NULL, ?,
                 NULL, NULL, NULL, NULL, NULL, 0, 'active', ?, ?, NULL, NULL, NULL)`,
      )
      .run(
        session.scope.tenant_id,
        session.scope.company_id,
        grantId,
        session.spec.session_id,
        JSON.stringify({ proof_version: 'run-grant-proof/v1', ceilings }),
        nowUtc,
        '2027-01-01T00:00:00.000Z',
      );
  });
}

function budgetRig(label: string): {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  budget: DurableBudgetService;
} {
  const db = CouncilDatabase.open(join(tempDir(label), 'council.db'), {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const repositories = new CouncilRepositories(db, {
    clock,
    ids,
    config: parsePersistenceConfig(),
  });
  // The service maximum is the convening guard (100); the grant is what
  // a light session is really held to (50).
  const budget = new DurableBudgetService({
    db,
    clock,
    ids,
    settings: CONVENING_SETTINGS,
  });
  return { db, repositories, budget };
}

// ------------------------------------------------- finding 2: reported cap

test('LOWFIX-1057: a session reports the grant cap, not the service maximum', () => {
  const { db, repositories, budget } = budgetRig('cap');
  const session = sampleStored('sess-cap-1');
  const envelope = envelopeFromScope(session.scope, 'owner-1', 'owner', 'write');
  repositories.createSession(envelope, session);
  insertGrant(db, session, 'grant-cap', {
    max_provider_requests: 50,
    max_output_repairs: 50,
    max_transport_retries: 50,
  });

  const snapshot = budget.snapshot(envelope, session.spec.session_id);
  assert.equal(snapshot.ceilings.max_provider_requests, 50, 'enforced cap, not the 100 service maximum');
  assert.equal(snapshot.ceilings.max_output_repairs, 50);
  assert.equal(snapshot.ceilings.max_transport_retries, 50);
  assert.equal(snapshot.envelope_breakdown.hard_ceiling, 50);
});

test('LOWFIX-1057: with no grant record the service maximum still applies', () => {
  const { repositories, budget } = budgetRig('cap-control');
  const session = sampleStored('sess-cap-2');
  const envelope = envelopeFromScope(session.scope, 'owner-1', 'owner', 'write');
  repositories.createSession(envelope, session);
  const snapshot = budget.snapshot(envelope, session.spec.session_id);
  assert.equal(snapshot.ceilings.max_provider_requests, 100);
});

// ------------------------------------------------- finding 3: capacity live

test('LOWFIX-1057: the default capacity pool holds a whole wave', () => {
  // The pool the protocol composition really builds by default.
  const capacity = new RuntimeCapacity(DEFAULT_WAVE_CAPACITY);
  // A heavy wave is nine seats; the design floor is ten.
  assert.ok(capacity.classLimit('company') >= 10, 'a full wave fits in the company class');
  assert.ok(capacity.classLimit('private') >= capacity.classLimit('company'));
});

// --------------------------------------------- finding 4: readiness route

function ambiguousRouteHome(): string {
  const home = tempDir('route-home');
  mkdirSync(join(home, '.openclaw'), { recursive: true });
  writeFileSync(
    join(home, '.openclaw', 'openclaw.json'),
    JSON.stringify({
      models: {
        providers: {
          acme: {
            baseUrl: 'http://127.0.0.1:1234/v1',
            api: 'openai-completions',
            models: [{ id: 'model-a' }, { id: 'model-b' }],
          },
        },
      },
    }),
  );
  return home;
}

test('LOWFIX-1057: a route usable with a named model reports readiness ready', async () => {
  const home = ambiguousRouteHome();
  const dataDir = tempDir('readiness');
  const composition = composeCouncilService({
    dataDir,
    startedAt: nowUtc,
    nowUtc: () => nowUtc,
    routeHomeDir: home,
    routeEnv: { OPENCLAW_ROOT: join(home, '.openclaw'), PATH: '' } as NodeJS.ProcessEnv,
    startWorkers: false,
  });
  try {
    const readiness = await composition.door.readiness({ offline: true });
    const route = readiness.layers.find((layer) => layer.layer === 'route');
    assert.ok(route);
    assert.equal(route.state, 'ready', JSON.stringify(route.blocker ?? {}));
    assert.match(route.artifact ?? '', /usable once a model is named/);
    assert.match(route.artifact ?? '', /model-a \| model-b/);
  } finally {
    await composition.stop();
  }
});

test('LOWFIX-1057: readiness still blocks when no route is configured at all', async () => {
  const home = tempDir('empty-home');
  const dataDir = tempDir('readiness-control');
  const composition = composeCouncilService({
    dataDir,
    startedAt: nowUtc,
    nowUtc: () => nowUtc,
    routeHomeDir: join(home, 'no-routes-here'),
    routeEnv: {} as NodeJS.ProcessEnv,
    startWorkers: false,
  });
  try {
    const readiness = await composition.door.readiness({ offline: true });
    const route = readiness.layers.find((layer) => layer.layer === 'route');
    assert.equal(route?.state, 'blocked');
    assert.equal(route?.blocker?.code, 'ROUTE_NOT_CONFIGURED');
  } finally {
    await composition.stop();
  }
});

// ------------------------------------ finding 5: blocked-reason pass window

const SEATS = [
  'simon-sinek', 'td-jakes', 'oprah-winfrey', 'tiffany-aliche', 'russell-brunson',
  'michelle-obama', 'brene-brown', 'dennis-kimbro', 'les-brown',
];
const MISSING = ['dennis-kimbro', 'les-brown'];

test('LOWFIX-1057: a blocked council size blames the current pass, not an earlier one', () => {
  const cards = [
    ...SEATS.map((seat_id) => ({ card_kind: 'advisor', round: 1, seat_id })),
    ...SEATS.map((seat_id) => ({ card_kind: 'advisor', round: 2, seat_id })),
    ...SEATS.filter((s) => !MISSING.includes(s)).map((seat_id) => ({
      card_kind: 'advisor',
      round: 3,
      seat_id,
    })),
  ];
  const events = [
    { type: 'session_state_changed', to_state: 'ROUND_1', created_at: '2026-10-25T10:00:00.000Z', payload: {} },
    { type: 'session_state_changed', to_state: 'CRUX_REVIEW', created_at: '2026-10-25T10:10:00.000Z', payload: {} },
    // Pass 2 begins.
    { type: 'session_state_changed', to_state: 'ROUND_2', created_at: '2026-10-25T10:20:00.000Z', payload: {} },
    // A pass-2 failure that was repaired by pass 3 — not the current cause.
    {
      type: 'operation_completed',
      to_state: null,
      created_at: '2026-10-25T10:25:00.000Z',
      payload: {
        kind: 'attempt_failed',
        seat_id: 'dennis-kimbro',
        outcome_code: 'output_validation_failed',
        message: 'earlier challenge pass: response was not valid JSON',
      },
    },
    { type: 'session_state_changed', to_state: 'CRUX_REVIEW', created_at: '2026-10-25T10:30:00.000Z', payload: {} },
    // Pass 3 (the current one) begins; the two seats never answered.
    { type: 'session_state_changed', to_state: 'ROUND_2', created_at: '2026-10-25T10:40:00.000Z', payload: {} },
    { type: 'session_blocked', to_state: 'BLOCKED', created_at: '2026-10-25T10:50:00.000Z', payload: {} },
  ];
  const reason = buildBlockedReason({
    state: 'BLOCKED',
    mode: 'medium',
    seat_ids: SEATS,
    cards,
    failures: [],
    events,
  });
  assert.ok(reason);
  assert.equal(reason.missing_round, 3);
  assert.deepEqual(reason.missing_seats, MISSING);
  for (const seat of MISSING) {
    const error = reason.last_errors.find((e) => e.seat_id === seat);
    // The pass-2 validation failure was repaired; pass 3 has no recorded
    // attempt failure for these seats, so no earlier message may be quoted.
    assert.equal(error, undefined, `${seat} carries no earlier-pass cause`);
  }
  assert.doesNotMatch(reason.detail, /not valid JSON/);
});
