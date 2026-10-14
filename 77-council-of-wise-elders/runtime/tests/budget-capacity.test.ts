/**
 * CWE-028 tests: the shared budget reservation service over CWE-006's
 * scoped store, and runtime capacity admission (queue/capacity.ts).
 *
 * Primary-owned acceptance contract (Section 35):
 * - T150 (owned by CWE-028): two semantic-check calls, shared
 *   structural/semantic repairs, and transport retries all fit the
 *   same enforced 50-request ceiling.
 * Supporting contracts proven here:
 * - T061: concurrent admissions reserve atomically; two calls cannot
 *   spend the same remaining allowance (the count check runs inside
 *   the reservation transaction).
 * - T062: pending and uncertain attempts retain conservative
 *   reservations (unknown completion stays counted at its estimate).
 * - T063: unknown pricing/usage is labeled unknown, not zero (the
 *   money view keeps the unknown reservation outstanding at estimate).
 * - T065: the total cap includes all session-attributable inference;
 *   relabeled retries and repairs cannot bypass it (every kind counts
 *   toward the same session ceiling).
 * Unit acceptance proof (Section 34, CWE-028): reservations are
 * durable across restart, fenced by the operation lease epoch,
 * settled or released exactly once, auditable through the durable
 * event journal, and capacity refuses typed when full with the
 * Section 15.7 private minimum share protected.
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import type { ScopeFields, SessionStateRecord } from '../src/contracts/index.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import { InProcessBudgetLedger } from '../src/cli/budget.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import { parsePersistenceConfig } from '../src/persistence/config.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from '../src/persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../src/persistence/index.js';
import { CouncilRepositories } from '../src/persistence/repositories.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';
import {
  BudgetCapacityError,
  DurableBudgetService,
  type PinnedRouteSnapshot,
  type RouteResolutionOutcome,
} from '../src/budgets/index.js';
import { RuntimeCapacity } from '../src/queue/capacity.js';

// ------------------------------------------------------------- fixtures

let nowIso = '2026-10-14T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

function advanceClock(ms: number): void {
  nowIso = new Date(Date.parse(nowIso) + ms).toISOString();
}

function tempDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `cwe028-${label}-`));
}

function sampleStored(sessionId?: string, scope?: ScopeFields): StoredSession {
  const sample = buildSampleSession();
  const spec = sessionId ? { ...sample.spec, session_id: sessionId } : sample.spec;
  const brief = sessionId
    ? { ...sample.brief, session_id: sessionId }
    : sample.brief;
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
  return { spec, brief, scope: scope ?? sample.scope, state, sample: false };
}

function ownerEnvelope(
  session: StoredSession,
  purpose: AuthorizationEnvelope['purpose'] = 'write',
): AuthorizationEnvelope {
  return envelopeFromScope(session.scope, 'owner-1', 'owner', purpose);
}

interface Composition {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  budget: DurableBudgetService;
}

function compose(
  dbPath: string,
  options: { holdTtlMs?: number } = {},
): Composition {
  const db = CouncilDatabase.open(dbPath, {
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
  const budget = new DurableBudgetService({
    db,
    clock,
    ids,
    holdTtlMs: options.holdTtlMs,
  });
  return { db, repositories, budget };
}

/** Insert the durable RunGrant record CWE-049's service would issue. */
function insertGrant(
  db: CouncilDatabase,
  session: StoredSession,
  overrides: {
    id?: string;
    maxCostMinor?: number | null;
    currency?: string | null;
    status?: string;
    expiresAt?: string;
    sessionId?: string | null;
  } = {},
): string {
  const grantId = overrides.id ?? 'grant-1';
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
                 'council_run', 'owner-1', 'owner', NULL, 'test-scope-proof',
                 NULL, NULL, ?, ?, NULL, 0, ?, ?, ?, NULL, NULL, NULL)`,
      )
      .run(
        session.scope.tenant_id,
        session.scope.company_id,
        grantId,
        overrides.sessionId === undefined
          ? session.spec.session_id
          : overrides.sessionId,
        overrides.maxCostMinor ?? null,
        overrides.currency === undefined ? 'USD' : overrides.currency,
        overrides.status ?? 'active',
        nowIso,
        overrides.expiresAt ?? '2027-01-01T00:00:00.000Z',
      );
  });
  return grantId;
}

function routeSnapshot(
  session: StoredSession,
  overrides: Partial<PinnedRouteSnapshot> = {},
): PinnedRouteSnapshot {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: 'route-a',
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'provider-a',
    requestedRoute: 'route-a',
    requestedModelOrAlias: 'model-a',
    combinationMembers: null,
    reasoning: { requested: null, applied: null, supported: null, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot: {
      contextWindowTokens: 200000,
      maxOutputTokens: 8000,
      capabilities: ['text'],
      supportedReasoningLevels: null,
    },
    credential: {
      state: 'present',
      envVar: 'PROVIDER_A_API_KEY',
      source: 'process.env',
      checked: ['process.env'],
    },
    identityLevel: 'configured',
    scope: {
      tenantId: session.scope.tenant_id,
      companyId: session.scope.company_id,
      installationId: session.scope.installation_id,
      ownerSubject: session.scope.owner_subject,
    },
    createdAt: nowIso,
    ...overrides,
  };
}

function setupSession(
  label: string,
  options: { holdTtlMs?: number; grant?: Parameters<typeof insertGrant>[2] } = {},
): Composition & {
  session: StoredSession;
  envelope: AuthorizationEnvelope;
  grantId: string;
} {
  const dir = tempDir(label);
  const composition = compose(join(dir, 'council.db'), options);
  const session = sampleStored();
  const envelope = ownerEnvelope(session);
  composition.repositories.createSession(envelope, session);
  const grantId = insertGrant(composition.db, session, options.grant);
  return { ...composition, session, envelope, grantId };
}

function reserveArgs(
  session: StoredSession,
  grantId: string,
  operationId: string,
  extra: Record<string, unknown> = {},
) {
  return {
    session_id: session.spec.session_id,
    operation_id: operationId,
    grant_id: grantId,
    kind: 'provider_request' as const,
    estimate_minor: 100,
    lease_epoch: 0,
    route_snapshot: routeSnapshot(session),
    ...extra,
  };
}

function isBudget(code: string) {
  return (error: unknown) =>
    error instanceof BudgetCapacityError && error.code === code;
}

// ------------------------------------------------------------ lifecycle

test('reservation lifecycle: reserve, settle, release, journal and outbox audit', () => {
  const { repositories, budget, session, envelope, grantId } = setupSession('lifecycle');
  const sid = session.spec.session_id;

  const reserved = budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));
  assert.equal(reserved.state, 'reserved');
  assert.equal(reserved.kind, 'provider_request');
  assert.equal(reserved.route_snapshot.routeId, 'route-a');
  let snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.reserved, 1);
  assert.equal(snap.consumed.provider_requests, 0);
  assert.equal(snap.money.outstanding_minor, 100);

  const settled = budget.settle(envelope, {
    session_id: sid,
    operation_id: 'op-1',
    lease_epoch: 0,
    actual_minor: 80,
  });
  assert.equal(settled.state, 'committed');
  assert.equal(settled.actual_minor, 80);
  snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.consumed.provider_requests, 1);
  assert.equal(snap.reserved, 0);
  assert.equal(snap.money.committed_actual_minor, 80);
  assert.equal(snap.money.outstanding_minor, 80);

  budget.reserve(envelope, reserveArgs(session, grantId, 'op-2'));
  const released = budget.release(envelope, {
    session_id: sid,
    operation_id: 'op-2',
    lease_epoch: 0,
    reason: 'cancelled before dispatch',
  });
  assert.equal(released.state, 'released');
  snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.money.outstanding_minor, 80);

  // The journal is the audit trail: reserve and finalize events in
  // order, the route snapshot pinned on the reserve event, and the
  // hash chain verifies end to end.
  const events = repositories.journal.list(envelope, sid, 0);
  const budgetEvents = events.filter(
    (e) => e.type === 'operation_reserved' || e.type === 'operation_completed',
  );
  assert.deepEqual(
    budgetEvents.map((e) => [e.type, e.payload.outcome ?? null]),
    [
      ['operation_reserved', null],
      ['operation_completed', 'settled'],
      ['operation_reserved', null],
      ['operation_completed', 'released'],
    ],
  );
  const reservePayload = budgetEvents[0].payload;
  assert.equal(
    (reservePayload.route_snapshot as PinnedRouteSnapshot).routeId,
    'route-a',
  );
  assert.equal(typeof reservePayload.route_snapshot_fingerprint, 'string');
  const chain = repositories.journal.verifyChain(envelope, sid);
  assert.equal(chain.ok, true);

  const intents = repositories.outbox.listForSession(envelope, sid);
  assert.deepEqual(
    intents.map((i) => i.topic).sort(),
    ['budget.finalized', 'budget.finalized', 'budget.reserved', 'budget.reserved'],
  );
});

test('double settle and double release are refused; finalization is exactly once', () => {
  const { budget, session, envelope, grantId } = setupSession('exactly-once');
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));
  budget.settle(envelope, {
    session_id: sid,
    operation_id: 'op-1',
    lease_epoch: 0,
    actual_minor: 50,
  });
  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'op-1',
        lease_epoch: 0,
        actual_minor: 50,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );
  assert.throws(
    () =>
      budget.release(envelope, {
        session_id: sid,
        operation_id: 'op-1',
        lease_epoch: 0,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );

  budget.reserve(envelope, reserveArgs(session, grantId, 'op-2'));
  budget.release(envelope, { session_id: sid, operation_id: 'op-2', lease_epoch: 0 });
  assert.throws(
    () =>
      budget.release(envelope, {
        session_id: sid,
        operation_id: 'op-2',
        lease_epoch: 0,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );
  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'op-2',
        lease_epoch: 0,
        actual_minor: 10,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );
  const snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.consumed.provider_requests, 1);
  assert.equal(snap.reserved, 0);
});

test('idempotent re-reserve returns the same reservation; re-reserve after release revives it', () => {
  const { budget, session, envelope, grantId } = setupSession('idempotent');
  const sid = session.spec.session_id;
  const first = budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));
  const again = budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));
  assert.equal(again.reservation_id, first.reservation_id);
  assert.equal(budget.snapshot(envelope, sid, grantId).reserved, 1);

  budget.release(envelope, { session_id: sid, operation_id: 'op-1', lease_epoch: 0 });
  const revived = budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));
  assert.equal(revived.reservation_id, first.reservation_id);
  assert.equal(revived.state, 'reserved');
  assert.equal(budget.snapshot(envelope, sid, grantId).reserved, 1);
});

// --------------------------------------------------------------- fencing

test('stale lease epoch cannot settle, release, or reserve (Section 15.8 fence)', () => {
  const { repositories, budget, session, envelope, grantId } =
    setupSession('fencing');
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));

  // The session lease moves to epoch 1 (a new worker claimed it).
  const current = repositories.getSession(envelope, sid);
  assert.ok(current);
  repositories.writeStateRecord(
    envelope,
    {
      ...current.state,
      lease_epoch: 1,
      state_version: current.state.state_version + 1,
      updated_at: nowIso,
    },
    current.state.state_version,
    { type: 'session_state_changed', payload: {} },
  );

  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'op-1',
        lease_epoch: 0,
        actual_minor: 10,
      }),
    isBudget('BUDGET_LEASE_FENCED'),
  );
  assert.throws(
    () =>
      budget.release(envelope, {
        session_id: sid,
        operation_id: 'op-1',
        lease_epoch: 0,
      }),
    isBudget('BUDGET_LEASE_FENCED'),
  );
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'op-2', { lease_epoch: 0 }),
      ),
    isBudget('BUDGET_LEASE_FENCED'),
  );
  // The current epoch owner can still finalize.
  const settled = budget.settle(envelope, {
    session_id: sid,
    operation_id: 'op-1',
    lease_epoch: 1,
    actual_minor: 10,
  });
  assert.equal(settled.state, 'committed');
});

// -------------------------------------------------------------- durability

test('restart durability: reservations and counters survive close and reopen', () => {
  const dir = tempDir('restart');
  const dbPath = join(dir, 'council.db');
  const first = compose(dbPath);
  const session = sampleStored();
  const envelope = ownerEnvelope(session);
  const sid = session.spec.session_id;
  first.repositories.createSession(envelope, session);
  const grantId = insertGrant(first.db, session, {});
  first.budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));
  first.budget.reserve(envelope, reserveArgs(session, grantId, 'op-2'));
  first.budget.reserve(envelope, reserveArgs(session, grantId, 'op-3'));
  first.budget.settle(envelope, {
    session_id: sid,
    operation_id: 'op-1',
    lease_epoch: 0,
    actual_minor: 70,
  });
  first.budget.markProviderCompletionUnknown(envelope, {
    session_id: sid,
    operation_id: 'op-2',
    lease_epoch: 0,
  });
  first.db.close();

  const second = compose(dbPath);
  const snap = second.budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.consumed.provider_requests, 2);
  assert.equal(snap.reserved, 1);
  assert.equal(snap.unknown, 1);
  assert.equal(snap.money.committed_actual_minor, 70);
  assert.equal(snap.money.outstanding_minor, 70 + 100 + 100);
  const op2 = second.budget.getReservation(envelope, sid, 'op-2');
  assert.equal(op2?.state, 'unknown');
  assert.equal(op2?.route_snapshot.routeId, 'route-a');
  // Work continues after restart under the same fences.
  const settled = second.budget.settle(envelope, {
    session_id: sid,
    operation_id: 'op-3',
    lease_epoch: 0,
    actual_minor: 90,
  });
  assert.equal(settled.state, 'committed');
  const chain = second.repositories.journal.verifyChain(envelope, sid);
  assert.equal(chain.ok, true);
  second.db.close();
});

// --------------------------------------------------------------- ceilings

test('ceiling proof: the 51st provider request reservation is refused (T065)', () => {
  const { budget, session, envelope, grantId } = setupSession('ceiling-50');
  const sid = session.spec.session_id;
  for (let i = 1; i <= 50; i += 1) {
    budget.reserve(
      envelope,
      reserveArgs(session, grantId, `op-${i}`, { estimate_minor: 0 }),
    );
  }
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'op-51', { estimate_minor: 0 }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      error.detail?.ceiling === 'max_session_provider_requests',
  );
  const snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.envelope_breakdown.total_active, 50);
  assert.equal(snap.envelope_breakdown.hard_ceiling, 50);
  // Releasing one frees exactly one slot (T061: no double-spend of the
  // remaining allowance; the next admission takes it, the one after
  // is refused again).
  budget.release(envelope, { session_id: sid, operation_id: 'op-50', lease_epoch: 0 });
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-51', { estimate_minor: 0 }));
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'op-52', { estimate_minor: 0 }),
      ),
    isBudget('BUDGET_EXHAUSTED'),
  );
});

test('T150: semantic checks, repairs, and retries share the one 50-request ceiling', () => {
  const { budget, session, envelope, grantId } = setupSession('t150');
  const sid = session.spec.session_id;
  // 44 planned generations + 2 semantic verifications + 2 repairs +
  // 2 transport retries = 50, the full envelope of Sections 15.6/15.9.
  for (let i = 1; i <= 44; i += 1) {
    budget.reserve(
      envelope,
      reserveArgs(session, grantId, `gen-${i}`, { estimate_minor: 0 }),
    );
  }
  for (let i = 1; i <= 2; i += 1) {
    budget.reserve(
      envelope,
      reserveArgs(session, grantId, `sem-${i}`, {
        kind: 'semantic_verification',
        estimate_minor: 0,
      }),
    );
    budget.reserve(
      envelope,
      reserveArgs(session, grantId, `repair-${i}`, {
        kind: 'output_repair',
        original_operation_id: `gen-${i}`,
        estimate_minor: 0,
      }),
    );
    budget.reserve(
      envelope,
      reserveArgs(session, grantId, `retry-${i}`, {
        kind: 'transport_retry',
        original_operation_id: `gen-${40 + i}`,
        estimate_minor: 0,
      }),
    );
  }
  const snap = budget.snapshot(envelope, sid, grantId);
  assert.deepEqual(snap.envelope_breakdown, {
    hard_ceiling: 50,
    total_active: 50,
    planned_generations: 44,
    output_repairs: 2,
    transport_retries: 2,
    semantic_verifications: 2,
  });
  // One more of ANY kind is refused: the ceiling is shared, and
  // relabeling a call cannot bypass it (T065).
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'gen-45', { estimate_minor: 0 }),
      ),
    isBudget('BUDGET_EXHAUSTED'),
  );
});

test('the 8-retry sub-ceiling and per-original caps are enforced by the same service', () => {
  const { budget, session, envelope, grantId } = setupSession('retries');
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'orig-1', { estimate_minor: 0 }));
  budget.reserve(
    envelope,
    reserveArgs(session, grantId, 'retry-1', {
      kind: 'transport_retry',
      original_operation_id: 'orig-1',
      estimate_minor: 0,
    }),
  );
  // A second retry of the same request hits the per-request cap of 1.
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'retry-1b', {
          kind: 'transport_retry',
          original_operation_id: 'orig-1',
          estimate_minor: 0,
        }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      error.detail?.ceiling === 'max_transport_retries_per_request',
  );
  // Seven more distinct originals reach the total retry ceiling of 8.
  for (let i = 2; i <= 8; i += 1) {
    budget.reserve(
      envelope,
      reserveArgs(session, grantId, `orig-${i}`, { estimate_minor: 0 }),
    );
    budget.reserve(
      envelope,
      reserveArgs(session, grantId, `retry-${i}`, {
        kind: 'transport_retry',
        original_operation_id: `orig-${i}`,
        estimate_minor: 0,
      }),
    );
  }
  budget.reserve(envelope, reserveArgs(session, grantId, 'orig-9', { estimate_minor: 0 }));
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'retry-9', {
          kind: 'transport_retry',
          original_operation_id: 'orig-9',
          estimate_minor: 0,
        }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      error.detail?.ceiling === 'max_transport_retries_total',
  );
  // Repairs: one per original operation.
  budget.reserve(
    envelope,
    reserveArgs(session, grantId, 'repair-1', {
      kind: 'output_repair',
      original_operation_id: 'orig-1',
      estimate_minor: 0,
    }),
  );
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'repair-1b', {
          kind: 'output_repair',
          original_operation_id: 'orig-1',
          estimate_minor: 0,
        }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      error.detail?.ceiling === 'max_output_repairs_per_original_operation',
  );
  // The semantic-verification cap of 2 binds long before the total.
  budget.reserve(
    envelope,
    reserveArgs(session, grantId, 'sem-1', {
      kind: 'semantic_verification',
      estimate_minor: 0,
    }),
  );
  budget.reserve(
    envelope,
    reserveArgs(session, grantId, 'sem-2', {
      kind: 'semantic_verification',
      estimate_minor: 0,
    }),
  );
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'sem-3', {
          kind: 'semantic_verification',
          estimate_minor: 0,
        }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      error.detail?.ceiling === 'max_semantic_verification_requests',
  );
  assert.ok(sid.length > 0);
});

test('T062/T063: unknown completion keeps its reservation at estimate, never zero', () => {
  const { budget, session, envelope, grantId } = setupSession('unknown', {
    grant: { maxCostMinor: 250 },
  });
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));
  budget.markProviderCompletionUnknown(envelope, {
    session_id: sid,
    operation_id: 'op-1',
    lease_epoch: 0,
  });
  const snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.unknown, 1);
  assert.equal(snap.consumed.provider_requests, 1);
  // The unknown request still occupies 100 of the 250 money ceiling.
  assert.equal(snap.money.outstanding_minor, 100);
  // It cannot be released as free, and it blocks money like a live hold.
  assert.throws(
    () =>
      budget.release(envelope, {
        session_id: sid,
        operation_id: 'op-1',
        lease_epoch: 0,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'op-2', { estimate_minor: 200 }),
      ),
    isBudget('BUDGET_EXHAUSTED'),
  );
  // When the outcome is confirmed, the unknown reservation settles.
  const settled = budget.settle(envelope, {
    session_id: sid,
    operation_id: 'op-1',
    lease_epoch: 0,
    actual_minor: 95,
  });
  assert.equal(settled.state, 'committed');
  assert.equal(budget.snapshot(envelope, sid, grantId).unknown, 0);
});

test('grant money ceiling: outstanding worst case may reach but never exceed it', () => {
  const { budget, session, envelope, grantId } = setupSession('money', {
    grant: { maxCostMinor: 1000 },
  });
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-1', { estimate_minor: 700 }));
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'op-2', { estimate_minor: 400 }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      error.detail?.ceiling === 'grant_max_cost_minor',
  );
  budget.settle(envelope, {
    session_id: sid,
    operation_id: 'op-1',
    lease_epoch: 0,
    actual_minor: 650,
  });
  const ok = budget.reserve(
    envelope,
    reserveArgs(session, grantId, 'op-2', { estimate_minor: 350 }),
  );
  assert.equal(ok.state, 'reserved');
  assert.equal(budget.snapshot(envelope, sid, grantId).money.outstanding_minor, 1000);
});

// ------------------------------------------------------ readiness / grants

test('readiness and grant failures are typed, and a failed reserve records nothing', () => {
  // Store without the canonical schema: readiness refuses.
  const bareDir = tempDir('bare');
  const bareDb = CouncilDatabase.open(join(bareDir, 'council.db'), {
    busyTimeoutMs: 100,
    busyMaxAttempts: 1,
    busyBaseDelayMs: 1,
  });
  const bareBudget = new DurableBudgetService({ db: bareDb, clock, ids });
  assert.throws(() => bareBudget.readiness(), isBudget('BUDGET_STORE_UNAVAILABLE'));
  bareDb.close();

  const { budget, session, envelope } = setupSession('grants');
  const sid = session.spec.session_id;
  assert.deepEqual(budget.readiness().ready, true);
  // No grant record at all.
  assert.throws(
    () => budget.reserve(envelope, reserveArgs(session, 'grant-missing', 'op-1')),
    isBudget('BUDGET_GRANT_NOT_FOUND'),
  );
  assert.equal(budget.getReservation(envelope, sid, 'op-1'), null);
  assert.equal(budget.snapshot(envelope, sid).envelope_breakdown.total_active, 0);

  const { budget: b2, session: s2, envelope: e2 } = setupSession('grants-revoked', {
    grant: { id: 'grant-revoked', status: 'revoked' },
  });
  assert.throws(
    () => b2.reserve(e2, reserveArgs(s2, 'grant-revoked', 'op-1')),
    isBudget('BUDGET_GRANT_INACTIVE'),
  );
  const { budget: b3, session: s3, envelope: e3 } = setupSession('grants-expired', {
    grant: { id: 'grant-expired', expiresAt: '2026-01-01T00:00:00.000Z' },
  });
  assert.throws(
    () => b3.reserve(e3, reserveArgs(s3, 'grant-expired', 'op-1')),
    isBudget('BUDGET_GRANT_INACTIVE'),
  );
  // A grant bound to a different session pays for no other session.
  const other = setupSession('grants-mismatch');
  const secondSession = sampleStored('sess-second');
  other.repositories.createSession(other.envelope, secondSession);
  insertGrant(other.db, secondSession, { id: 'grant-second' });
  assert.throws(
    () =>
      other.budget.reserve(
        other.envelope,
        reserveArgs(other.session, 'grant-second', 'op-1'),
      ),
    isBudget('BUDGET_GRANT_SESSION_MISMATCH'),
  );
});

// ----------------------------------------------------------------- expiry

test('hold expiry frees allowance; unknown holds never expire; settle after expiry is refused', () => {
  const { budget, session, envelope, grantId } = setupSession('expiry', {
    holdTtlMs: 60_000,
  });
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-2'));
  budget.markProviderCompletionUnknown(envelope, {
    session_id: sid,
    operation_id: 'op-2',
    lease_epoch: 0,
  });
  advanceClock(61_000);
  const expired = budget.expireHolds(envelope, sid);
  assert.deepEqual(
    expired.map((e) => e.operation_id),
    ['op-1'],
  );
  assert.equal(budget.getReservation(envelope, sid, 'op-1')?.state, 'expired');
  assert.equal(budget.getReservation(envelope, sid, 'op-2')?.state, 'unknown');
  const snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.reserved, 0);
  assert.equal(snap.unknown, 1);
  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'op-1',
        lease_epoch: 0,
        actual_minor: 10,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );

  // Lazy expiry: a lapsed hold settles as expired inside the attempt.
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-3'));
  advanceClock(61_000);
  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'op-3',
        lease_epoch: 0,
        actual_minor: 10,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );
  assert.equal(budget.getReservation(envelope, sid, 'op-3')?.state, 'expired');
});

// --------------------------------------------------------- planted scopes

test('planted-scope negatives: cross-scope settle, snapshot, and grant are refused', () => {
  const { db, repositories, budget, session, envelope, grantId } =
    setupSession('scope');
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-1'));

  const foreignScope: ScopeFields = {
    tenant_id: session.scope.tenant_id,
    company_id: 'other-company',
    installation_id: session.scope.installation_id,
    owner_subject: null,
  };
  const foreign = envelopeFromScope(foreignScope, 'intruder', 'owner', 'write');
  // A reservation minted in one scope cannot be settled from another:
  // the session itself is invisible in the foreign scope, so the
  // settle fails as session-not-found and the reservation stays
  // reserved under its owning envelope.
  assert.throws(
    () =>
      budget.settle(foreign, {
        session_id: sid,
        operation_id: 'op-1',
        lease_epoch: 0,
        actual_minor: 1,
      }),
    (error: unknown) =>
      error instanceof Error &&
      (error as { code?: string }).code === 'PERSISTENCE_SESSION_NOT_FOUND',
  );
  assert.equal(budget.getReservation(envelope, sid, 'op-1')?.state, 'reserved');
  assert.equal(budget.getReservation(foreign, sid, 'op-1'), null);
  // Under the owning envelope, an operation that was never reserved
  // is a typed not-found.
  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'op-never-reserved',
        lease_epoch: 0,
        actual_minor: 1,
      }),
    isBudget('BUDGET_RESERVATION_NOT_FOUND'),
  );

  // A pinned snapshot carrying a foreign scope is not a charge target.
  const planted = routeSnapshot(session, {
    scope: {
      tenantId: session.scope.tenant_id,
      companyId: 'other-company',
      installationId: session.scope.installation_id,
      ownerSubject: null,
    },
  });
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'op-2', { route_snapshot: planted }),
      ),
    (error: unknown) =>
      error instanceof Error &&
      (error as { code?: string }).code === 'PERSISTENCE_SCOPE_DENIED',
  );

  // A session and grant that exist only in the other scope cannot be
  // charged from this envelope either.
  const otherSession = sampleStored('sess-other-scope', foreignScope);
  repositories.createSession(
    envelopeFromScope(foreignScope, 'owner-2', 'owner', 'write'),
    otherSession,
  );
  insertGrant(db, otherSession, { id: 'grant-foreign' });
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(otherSession, 'grant-foreign', 'op-9', {
          route_snapshot: routeSnapshot(session),
        }),
      ),
    (error: unknown) =>
      error instanceof Error &&
      (error as { code?: string }).code === 'PERSISTENCE_SESSION_NOT_FOUND',
  );
});

// ------------------------------------------------------------ route charges

test('route-aware accounting: refusal journaled, substitution pinned, charges never migrate', () => {
  const { repositories, budget, session, envelope, grantId } =
    setupSession('routes');
  const sid = session.spec.session_id;
  const snapshotA = routeSnapshot(session);

  // A refused resolution is journaled and mints nothing.
  const refused: RouteResolutionOutcome = {
    outcome: 'refused',
    effectiveModelId: null,
    identityLevel: 'configured',
    identityStatement: null,
    changeRecord: null,
    events: [
      {
        type: 'substitution_refused',
        routeId: 'route-a',
        requestedModelOrAlias: 'model-a',
        attemptedModelId: 'model-other',
        source: 'cascade',
        reason: 'Fallback policy is none.',
      },
      {
        type: 'prose_identity_claim_ignored',
        routeId: 'route-a',
        claimedModelId: 'model-other',
      },
    ],
  };
  const recorded = budget.recordRouteResolution(envelope, {
    session_id: sid,
    route_snapshot: snapshotA,
    resolution: refused,
  });
  assert.equal(recorded.recorded, true);
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'op-refused', { route_resolution: refused }),
      ),
    isBudget('BUDGET_ROUTE_RESOLUTION_REFUSED'),
  );
  assert.equal(budget.getReservation(envelope, sid, 'op-refused'), null);

  // An approved substitution reserves against the NEW pinned snapshot,
  // with the change record journaled on the reserve event.
  const snapshotB = routeSnapshot(session, {
    routeId: 'route-b',
    routeRevision: 2,
    requestedRoute: 'route-b',
    requestedModelOrAlias: 'model-b',
  });
  const substituted: RouteResolutionOutcome = {
    outcome: 'substituted_with_approval',
    effectiveModelId: 'model-b',
    identityLevel: 'configured',
    identityStatement: null,
    changeRecord: {
      reason: 'Client approved fallback.',
      originalRoute: 'route-a',
      replacementRoute: 'route-b',
      costImplications: 'Replacement route is priced per request.',
      newRouteRevision: 2,
      approvalRef: 'approval-1',
    },
    events: [
      {
        type: 'substitution_approved',
        routeId: 'route-a',
        change: {
          reason: 'Client approved fallback.',
          originalRoute: 'route-a',
          replacementRoute: 'route-b',
          costImplications: 'Replacement route is priced per request.',
          newRouteRevision: 2,
          approvalRef: 'approval-1',
        },
      },
    ],
  };
  const onB = budget.reserve(
    envelope,
    reserveArgs(session, grantId, 'op-b', {
      route_snapshot: snapshotB,
      route_resolution: substituted,
    }),
  );
  assert.equal(onB.route_snapshot.routeId, 'route-b');
  assert.equal(onB.route_snapshot.routeRevision, 2);

  // A route change on an existing reservation releases it with the
  // change record; the charge never migrates to the new route.
  budget.reserve(envelope, reserveArgs(session, grantId, 'op-a'));
  const releasedForChange = budget.releaseForRouteChange(envelope, {
    session_id: sid,
    operation_id: 'op-a',
    lease_epoch: 0,
    change: substituted.changeRecord!,
  });
  assert.equal(releasedForChange.state, 'released');
  assert.equal(releasedForChange.route_snapshot.routeId, 'route-a');

  const events = repositories.journal.list(envelope, sid, 0);
  const refusalEvent = events.find(
    (e) =>
      e.type === 'operation_completed' &&
      e.payload.outcome === 'route_resolution_refused',
  );
  assert.ok(refusalEvent);
  const reserveB = events.find(
    (e) =>
      e.type === 'operation_reserved' && e.payload.operation_id === 'op-b',
  );
  const resolutionPayload = reserveB?.payload.route_resolution as
    | RouteResolutionOutcome
    | undefined;
  assert.equal(resolutionPayload?.changeRecord?.newRouteRevision, 2);
  const changeRelease = events.find(
    (e) =>
      e.type === 'operation_completed' &&
      e.payload.outcome === 'route_changed_released',
  );
  assert.equal(
    (changeRelease?.payload.change_record as { originalRoute?: string })
      ?.originalRoute,
    'route-a',
  );
  // After the route release, only op-b remains active.
  assert.equal(
    budget.snapshot(envelope, sid, grantId).envelope_breakdown.total_active,
    1,
  );
});

// ------------------------------------------------- composition parity

test('composition parity: durable service ceilings equal the CWE-004 local ledger ceilings', () => {
  const { budget, session, envelope, grantId } = setupSession('parity');
  const local = new InProcessBudgetLedger();
  const localCeilings = local.snapshot('any-session').ceilings;
  const durableCeilings = budget.snapshot(
    envelope,
    session.spec.session_id,
    grantId,
  ).ceilings;
  assert.deepEqual(durableCeilings, localCeilings);
  assert.deepEqual(durableCeilings, {
    max_provider_requests: 50,
    max_output_repairs: 9,
    max_transport_retries: 8,
    max_semantic_verifications: 2,
  });
});

// --------------------------------------------------------------- capacity

test('capacity fairness: a company flood cannot take the private minimum share (Section 15.7)', () => {
  let nowMs = 1_000_000;
  let tokenCounter = 0;
  const capacity = new RuntimeCapacity(
    { total_slots: 4, private_reserved_slots: 2, slot_ttl_ms: 60_000 },
    { nowMs: () => nowMs, newTokenId: () => `tok-${(tokenCounter += 1)}` },
  );
  const companyScope = 'tenant:company-co:install';
  const privateScope = 'tenant:company-co:install';
  // Company work floods: it may take only total - reserved = 2 slots.
  for (let i = 1; i <= 10; i += 1) {
    const decision = capacity.tryAcquire({
      operation_key: `company-op-${i}`,
      work_class: 'company',
      scope_key: companyScope,
    });
    if (i <= 2) {
      assert.equal(decision.admitted, true);
    } else {
      assert.equal(decision.admitted, false);
      if (!decision.admitted) {
        assert.equal(decision.code, 'CAPACITY_FULL');
        assert.equal(decision.class_limit, 2);
        assert.equal(decision.class_in_use, 2);
      }
    }
  }
  // The private minimum share is intact despite the flood.
  for (let i = 1; i <= 2; i += 1) {
    const decision = capacity.tryAcquire({
      operation_key: `private-op-${i}`,
      work_class: 'private',
      scope_key: privateScope,
    });
    assert.equal(decision.admitted, true);
  }
  // Now the runtime is genuinely full for everyone.
  const full = capacity.tryAcquire({
    operation_key: 'private-op-3',
    work_class: 'private',
    scope_key: privateScope,
  });
  assert.equal(full.admitted, false);
  const usage = capacity.usage();
  assert.equal(usage.total_in_use, 4);
  assert.deepEqual(usage.by_class, { private: 2, company: 2 });
  assert.deepEqual(usage.class_limits, { private: 4, company: 2 });
  assert.ok(nowMs > 0);
});

test('capacity: cancellation and release free slots immediately; TTL expiry reclaims the rest', () => {
  let nowMs = 5_000_000;
  let tokenCounter = 0;
  const capacity = new RuntimeCapacity(
    { total_slots: 2, private_reserved_slots: 1, slot_ttl_ms: 1_000 },
    { nowMs: () => nowMs, newTokenId: () => `tok-${(tokenCounter += 1)}` },
  );
  const a = capacity.tryAcquire({
    operation_key: 'op-a',
    work_class: 'company',
    scope_key: 'scope-1',
  });
  const b = capacity.tryAcquire({
    operation_key: 'op-b',
    work_class: 'private',
    scope_key: 'scope-1',
  });
  assert.ok(a.admitted && b.admitted);
  const blocked = capacity.tryAcquire({
    operation_key: 'op-c',
    work_class: 'private',
    scope_key: 'scope-2',
  });
  assert.equal(blocked.admitted, false);

  // Cancelling the scope frees both slots at once (T069-adjacent:
  // cancellation is immediate, and the freed capacity is reusable in
  // the same tick).
  assert.equal(capacity.cancelScope('scope-1'), 2);
  assert.equal(capacity.usage().total_in_use, 0);
  const c = capacity.tryAcquire({
    operation_key: 'op-c',
    work_class: 'private',
    scope_key: 'scope-2',
  });
  assert.ok(c.admitted);

  // Idempotent re-acquire of a live operation takes no second slot.
  const cAgain = capacity.tryAcquire({
    operation_key: 'op-c',
    work_class: 'private',
    scope_key: 'scope-2',
  });
  assert.ok(cAgain.admitted);
  if (cAgain.admitted && c.admitted) {
    assert.equal(cAgain.token.token_id, c.token.token_id);
  }
  assert.equal(capacity.usage().total_in_use, 1);

  // Heartbeat extends; without it the slot lapses and is reclaimed.
  nowMs += 900;
  assert.ok(c.admitted && capacity.heartbeat(c.token.token_id));
  nowMs += 900;
  assert.equal(capacity.usage().total_in_use, 1);
  nowMs += 200;
  assert.equal(capacity.usage().total_in_use, 0);
  assert.equal(capacity.release('tok-missing'), false);
});
