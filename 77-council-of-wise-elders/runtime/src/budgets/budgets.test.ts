/**
 * WER-010 dependency-ready slice: durable budgets, reservations, and
 * fencing leases. node:test + tsx (the repository's own runner):
 *
 *   node --import tsx --test src/budgets/budgets.test.ts
 *
 * Proven here:
 * - the tightest applicable bound wins over a more generous runtime
 *   default, for both request counts and money;
 * - two concurrent admissions against one shared bound produce exactly
 *   one winner;
 * - a stale lease generation cannot commit;
 * - crash before reserve / after reserve / after response reconciles
 *   without double-spend;
 * - duplicate settlement of one operation charges once;
 * - unknown money stays reserved and is never treated as zero;
 * - revocation blocks new admission without erasing recorded usage;
 * - renewal adds capacity without resetting historical counters.
 *
 * Deferred and NOT asserted here: real provider dispatch, a live paid
 * operation, and end-to-end CLI wiring (cli/local-host.ts, cli/budget.ts,
 * cli/leases.ts).
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { Worker } from 'node:worker_threads';

import type { ScopeFields, SessionStateRecord } from '../contracts/index.js';
import { buildSampleSession } from '../cli/fixture-transport.js';
import type { StoredSession } from '../cli/host-ports.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from '../persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../persistence/index.js';
import { EventJournal } from '../persistence/journal.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import { CouncilDatabase } from '../persistence/sqlite.js';
import {
  BudgetCapacityError,
  DurableBudgetService,
  type PinnedRouteSnapshot,
  type ReserveInput,
} from './index.js';

// ------------------------------------------------------------- fixtures

let nowIso = '2026-10-18T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `wer010-${(idCounter += 1).toString().padStart(5, '0')}` };

const BUSY = { busyTimeoutMs: 2_000, busyMaxAttempts: 20, busyBaseDelayMs: 5 };

function tempDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `wer010-${label}-`));
}

function storedSession(sessionId?: string, scope?: ScopeFields): StoredSession {
  const sample = buildSampleSession();
  const spec = sessionId ? { ...sample.spec, session_id: sessionId } : sample.spec;
  const brief = sessionId ? { ...sample.brief, session_id: sessionId } : sample.brief;
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

function envelopeFor(session: StoredSession): AuthorizationEnvelope {
  return envelopeFromScope(session.scope, 'owner-1', 'owner', 'write');
}

interface Composition {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  budget: DurableBudgetService;
}

function openDb(db: CouncilDatabase): CouncilRepositories {
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  return new CouncilRepositories(db, {
    clock,
    ids,
    config: parsePersistenceConfig(),
  });
}

function compose(dbPath: string, options: { holdTtlMs?: number } = {}): Composition {
  const db = CouncilDatabase.open(dbPath, BUSY);
  const repositories = openDb(db);
  const budget = new DurableBudgetService({
    db,
    clock,
    ids,
    holdTtlMs: options.holdTtlMs,
  });
  return { db, repositories, budget };
}

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
        overrides.maxCostMinor === undefined ? 1_000 : overrides.maxCostMinor,
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
    routeId: 'route-wer010',
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'provider-a',
    requestedRoute: 'route-wer010',
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

function reserveArgs(
  session: StoredSession,
  grantId: string,
  operationId: string,
  extra: Partial<ReserveInput> = {},
): ReserveInput {
  return {
    session_id: session.spec.session_id,
    operation_id: operationId,
    grant_id: grantId,
    kind: 'provider_request',
    estimate_minor: 100,
    lease_epoch: 0,
    route_snapshot: routeSnapshot(session),
    ...extra,
  };
}

function setup(
  label: string,
  options: {
    holdTtlMs?: number;
    grant?: Parameters<typeof insertGrant>[2];
  } = {},
): Composition & {
  session: StoredSession;
  envelope: AuthorizationEnvelope;
  grantId: string;
} {
  const composition = compose(join(tempDir(label), 'council.db'), options);
  const session = storedSession();
  const envelope = envelopeFor(session);
  composition.repositories.createSession(envelope, session);
  const grantId = insertGrant(composition.db, session, options.grant);
  return { ...composition, session, envelope, grantId };
}

function isBudget(code: string) {
  return (error: unknown) =>
    error instanceof BudgetCapacityError && error.code === code;
}

/**
 * Advance the session's journaled lease epoch, the same durable record
 * the reservation fence reads. Stands in for the operation lease
 * renewal that happens outside this slice.
 */
function advanceLeaseEpoch(
  db: CouncilDatabase,
  envelope: AuthorizationEnvelope,
  session: StoredSession,
  epoch: number,
): void {
  const journal = new EventJournal(db);
  db.write((handle) => {
    journal.append(handle, envelope, session.spec.session_id, {
      event_id: ids.newId(),
      type: 'session_state_changed',
      from_state: null,
      to_state: null,
      actor_subject: 'owner-1',
      payload: {
        state_record: { ...session.state, lease_epoch: epoch, state_version: 1 },
        reason: 'test lease advance',
      },
      created_at: nowIso,
    });
  });
}

// -------------------------------------------------------------- bounds

test('a lower grant/run ceiling wins over a more generous runtime default', () => {
  const { budget, session, envelope, grantId } = setup('tightest-requests', {
    grant: { maxCostMinor: 10_000 },
  });
  const sid = session.spec.session_id;

  // The runtime default is 50 provider requests. The grant carries a
  // tighter ceiling of 1; the tighter one must win.
  budget.reserve(
    envelope,
    reserveArgs(session, grantId, 'tight-op-1', {
      ceilings: { max_provider_requests: 1 },
    }),
  );
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'tight-op-2', {
          ceilings: { max_provider_requests: 1 },
        }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      (error.detail as { limit?: number } | null)?.limit === 1,
  );

  // Money: grant 10_000 vs caller-chosen 50 -> 50 wins.
  const second = setup('tightest-money-chosen', {
    grant: { maxCostMinor: 10_000 },
  });
  assert.throws(
    () =>
      second.budget.reserve(
        second.envelope,
        reserveArgs(second.session, second.grantId, 'money-op-1', {
          estimate_minor: 60,
          ceilings: { max_money: { amount_minor: 50, currency: 'USD' } },
        }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      (error.detail as { limit?: number } | null)?.limit === 50,
  );

  // Money: grant 40 vs caller-chosen 10_000 -> the grant's 40 wins.
  const third = setup('tightest-money-grant', { grant: { maxCostMinor: 40 } });
  assert.throws(
    () =>
      third.budget.reserve(
        third.envelope,
        reserveArgs(third.session, third.grantId, 'money-op-2', {
          estimate_minor: 60,
          ceilings: { max_money: { amount_minor: 10_000, currency: 'USD' } },
        }),
      ),
    (error: unknown) =>
      error instanceof BudgetCapacityError &&
      error.code === 'BUDGET_EXHAUSTED' &&
      (error.detail as { limit?: number } | null)?.limit === 40,
  );
  assert.equal(budget.snapshot(envelope, sid).money.outstanding_minor, 100);
});

// --------------------------------------------------------- concurrency

interface RaceReply {
  ok: boolean;
  code: string | null;
}

function raceWorker(reply: (value: RaceReply) => void, workerData: Record<string, unknown>): Worker {
  const code = `
    const { parentPort, workerData } = require('node:worker_threads');
    import('tsx/esm/api').then(async ({ register }) => {
      register();
      const { DurableBudgetService } = await import(workerData.serviceUrl);
      const { CouncilDatabase } = await import(workerData.sqliteUrl);
      let db = null;
      for (let attempt = 0; attempt < 100 && db === null; attempt += 1) {
        try {
          db = CouncilDatabase.open(workerData.dbPath, workerData.busy);
        } catch (error) {
          if (!/locked|busy/i.test(String(error && error.message))) throw error;
          await new Promise((resolve) => setTimeout(resolve, 20));
        }
      }
      if (db === null) throw new Error('race worker could not open the store');
      let counter = 0;
      const ids = { newId: () => workerData.idPrefix + (++counter) };
      const clock = { nowUtc: () => workerData.now };
      const budget = new DurableBudgetService({ db, clock, ids });
      try {
        budget.reserve(workerData.envelope, workerData.input);
        parentPort.postMessage({ ok: true, code: null });
      } catch (error) {
        parentPort.postMessage({ ok: false, code: error && error.code ? error.code : 'ERROR' });
      } finally {
        db.close();
      }
    }).catch((error) => parentPort.postMessage({ ok: false, code: String(error && error.message) }));
  `;
  const worker = new Worker(code, {
    eval: true,
    workerData,
    execArgv: ['--import', 'tsx'],
  });
  worker.on('message', reply);
  worker.on('error', (error) => {
    throw error;
  });
  return worker;
}

test('two concurrent admissions against one shared bound produce exactly one winner', async () => {
  const dbPath = join(tempDir('race'), 'council.db');
  const db = CouncilDatabase.open(dbPath, BUSY);
  const repositories = openDb(db);
  const session = storedSession();
  const envelope = envelopeFor(session);
  repositories.createSession(envelope, session);
  const grantId = insertGrant(db, session, { maxCostMinor: 100 });
  db.close();

  const results: RaceReply[] = [];
  const exits: Array<Promise<void>> = [];
  const done = new Promise<void>((resolve, reject) => {
    const finish = (): void => {
      if (results.length === 2) resolve();
    };
    for (const op of ['race-op-a', 'race-op-b']) {
      const worker = raceWorker(
        (reply) => {
          results.push(reply);
          finish();
        },
        {
          serviceUrl: new URL('./service.ts', import.meta.url).href,
          sqliteUrl: new URL('../persistence/sqlite.ts', import.meta.url).href,
          dbPath,
          busy: BUSY,
          idPrefix: `${op}-id-`,
          now: nowIso,
          envelope,
          input: {
            ...reserveArgs(session, grantId, op, { estimate_minor: 60 }),
            // The pinned snapshot is plain data; rebuild it for the worker.
            route_snapshot: routeSnapshot(session),
          },
        },
      );
      worker.on('error', reject);
      exits.push(
        new Promise<void>((resolveExit, rejectExit) => {
          worker.on('exit', (code) => {
            if (code !== 0) rejectExit(new Error(`race worker exited ${code}`));
            else resolveExit();
          });
        }),
      );
    }
  });
  await done;
  // Both worker connections must be closed before the parent reopens.
  await Promise.all(exits);

  const winners = results.filter((r) => r.ok);
  const losers = results.filter((r) => !r.ok);
  assert.equal(winners.length, 1, `expected exactly one winner, got ${JSON.stringify(results)}`);
  assert.equal(losers.length, 1);
  assert.equal(losers[0]?.code, 'BUDGET_EXHAUSTED');

  // Durable proof: one reservation, one held 60 under the 100 ceiling.
  const check = CouncilDatabase.open(dbPath, BUSY);
  const budget = new DurableBudgetService({ db: check, clock, ids });
  const snap = budget.snapshot(envelope, session.spec.session_id, grantId);
  assert.equal(snap.reserved, 1);
  assert.equal(snap.money.outstanding_minor, 60);
  check.close();
});

// -------------------------------------------------------------- fencing

test('a stale lease generation cannot commit, settle, or renew', () => {
  const { db, budget, session, envelope, grantId } = setup('fence');
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'fenced-op'));

  advanceLeaseEpoch(db, envelope, session, 7);

  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'fenced-op',
        lease_epoch: 0,
        actual_minor: 50,
      }),
    isBudget('BUDGET_LEASE_FENCED'),
  );
  assert.throws(
    () =>
      budget.release(envelope, {
        session_id: sid,
        operation_id: 'fenced-op',
        lease_epoch: 0,
      }),
    isBudget('BUDGET_LEASE_FENCED'),
  );
  assert.throws(
    () =>
      budget.renewGrantCeiling(envelope, {
        grant_id: grantId,
        session_id: sid,
        lease_epoch: 0,
        additional_minor: 100,
      }),
    isBudget('BUDGET_LEASE_FENCED'),
  );
  // Nothing changed under the stale generation.
  const reservation = budget.getReservation(envelope, sid, 'fenced-op');
  assert.equal(reservation?.state, 'reserved');
  assert.equal(budget.grantLedger(envelope, grantId).max_cost_minor, 1_000);
});

// -------------------------------------------------------- reconciliation

test('crash before reserve, after reserve, and after response reconciles without double-spend', () => {
  const { budget, session, envelope, grantId } = setup('reconcile');
  const sid = session.spec.session_id;

  // Crash BEFORE reserve: nothing durable to reconcile; nothing charged.
  const before = budget.reconcileOperation(envelope, {
    session_id: sid,
    operation_id: 'never-reserved',
    lease_epoch: 0,
    dispatch: 'not_dispatched',
  });
  assert.equal(before.outcome, 'nothing_to_reconcile');
  assert.equal(before.reservation, null);
  assert.equal(budget.snapshot(envelope, sid, grantId).money.outstanding_minor, 0);

  // Crash AFTER reserve, before dispatch: release frees the hold once.
  budget.reserve(envelope, reserveArgs(session, grantId, 'crash-after-reserve'));
  const released = budget.reconcileOperation(envelope, {
    session_id: sid,
    operation_id: 'crash-after-reserve',
    lease_epoch: 0,
    dispatch: 'not_dispatched',
  });
  assert.equal(released.outcome, 'released_not_dispatched');
  assert.equal(released.released_not_dispatched, true);
  const afterRelease = budget.reconcileOperation(envelope, {
    session_id: sid,
    operation_id: 'crash-after-reserve',
    lease_epoch: 0,
    dispatch: 'not_dispatched',
  });
  assert.equal(afterRelease.outcome, 'already_released');
  assert.equal(budget.snapshot(envelope, sid, grantId).money.outstanding_minor, 0);

  // Crash AFTER dispatch, no response: held unknown, never free.
  budget.reserve(envelope, reserveArgs(session, grantId, 'crash-dispatch'));
  const unknown = budget.reconcileOperation(envelope, {
    session_id: sid,
    operation_id: 'crash-dispatch',
    lease_epoch: 0,
    dispatch: 'dispatched_no_response',
  });
  assert.equal(unknown.outcome, 'held_unknown');
  assert.equal(budget.snapshot(envelope, sid, grantId).money.unknown_minor, 100);
  const unknownAgain = budget.reconcileOperation(envelope, {
    session_id: sid,
    operation_id: 'crash-dispatch',
    lease_epoch: 0,
    dispatch: 'not_dispatched',
  });
  assert.equal(unknownAgain.outcome, 'held_unknown');

  // Crash AFTER response: settle once; replay is a no-op charge.
  budget.reserve(envelope, reserveArgs(session, grantId, 'crash-response'));
  const settled = budget.reconcileOperation(envelope, {
    session_id: sid,
    operation_id: 'crash-response',
    lease_epoch: 0,
    dispatch: 'response_observed',
    actual_minor: 70,
    cost_knowledge: 'verified',
  });
  assert.equal(settled.outcome, 'settled');
  assert.equal(settled.charged_minor, 70);
  const replay = budget.reconcileOperation(envelope, {
    session_id: sid,
    operation_id: 'crash-response',
    lease_epoch: 0,
    dispatch: 'response_observed',
    actual_minor: 70,
    cost_knowledge: 'verified',
  });
  assert.equal(replay.outcome, 'already_settled');
  assert.equal(replay.charged_minor, 70);

  const snap = budget.snapshot(envelope, sid, grantId);
  // consumed = committed + unknown: crash-response and crash-dispatch.
  assert.equal(snap.consumed.provider_requests, 2);
  assert.equal(snap.money.committed_actual_minor, 70);
  assert.equal(snap.money.outstanding_minor, 170); // 70 committed + 100 unknown
  assert.equal(snap.unknown, 1);

  // Replaying the whole reconciliation is stable: no second charge.
  budget.reconcileOperation(envelope, {
    session_id: sid,
    operation_id: 'crash-response',
    lease_epoch: 0,
    dispatch: 'response_observed',
    actual_minor: 70,
  });
  assert.equal(
    budget.snapshot(envelope, sid, grantId).money.committed_actual_minor,
    70,
  );
});

test('duplicate settlement of one operation charges once', () => {
  const { budget, session, envelope, grantId } = setup('duplicate-settle');
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'dup-op'));
  budget.settle(envelope, {
    session_id: sid,
    operation_id: 'dup-op',
    lease_epoch: 0,
    actual_minor: 80,
  });
  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'dup-op',
        lease_epoch: 0,
        actual_minor: 80,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );
  const snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.consumed.provider_requests, 1);
  assert.equal(snap.money.committed_actual_minor, 80);
  assert.equal(budget.grantLedger(envelope, grantId).committed_actual_minor, 80);
});

// ---------------------------------------------------------- unknown money

test('unknown money stays reserved and is never treated as zero', () => {
  const { budget, session, envelope, grantId } = setup('unknown-money', {
    grant: { maxCostMinor: 1_000 },
  });
  const sid = session.spec.session_id;

  // Unknown at zero is refused: that would silently treat it as free.
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'unknown-zero', {
          estimate_minor: 0,
          cost_knowledge: 'unknown',
        }),
      ),
    isBudget('BUDGET_INVALID_INPUT'),
  );

  const reserved = budget.reserve(
    envelope,
    reserveArgs(session, grantId, 'unknown-op', {
      estimate_minor: 250,
      cost_knowledge: 'unknown',
    }),
  );
  assert.equal(reserved.cost_knowledge, 'unknown');
  let snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.money.outstanding_minor, 250);
  assert.equal(snap.money.held_minor, 250);
  assert.equal(snap.money.unknown_cost_reservations, 1);

  // Unknown completion keeps the full hold, never zero.
  budget.markProviderCompletionUnknown(envelope, {
    session_id: sid,
    operation_id: 'unknown-op',
    lease_epoch: 0,
  });
  snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.money.unknown_minor, 250);
  assert.equal(snap.money.outstanding_minor, 250);
  assert.equal(budget.getReservation(envelope, sid, 'unknown-op')?.actual_minor, null);

  // Unknown money is never settled as unknown or as an estimate.
  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'unknown-op',
        lease_epoch: 0,
        actual_minor: 250,
        cost_knowledge: 'unknown',
      }),
    isBudget('BUDGET_INVALID_INPUT'),
  );
  assert.throws(
    () =>
      budget.settle(envelope, {
        session_id: sid,
        operation_id: 'unknown-op',
        lease_epoch: 0,
        actual_minor: 250,
        cost_knowledge: 'estimated',
      }),
    isBudget('BUDGET_INVALID_INPUT'),
  );
  // An unknown hold is never released as free either.
  assert.throws(
    () =>
      budget.release(envelope, {
        session_id: sid,
        operation_id: 'unknown-op',
        lease_epoch: 0,
      }),
    isBudget('BUDGET_RESERVATION_FINALIZED'),
  );

  // Only a verified amount resolves it.
  const settled = budget.settle(envelope, {
    session_id: sid,
    operation_id: 'unknown-op',
    lease_epoch: 0,
    actual_minor: 250,
    cost_knowledge: 'verified',
  });
  assert.equal(settled.state, 'committed');
  assert.equal(settled.cost_knowledge, 'unknown');
  assert.equal(budget.snapshot(envelope, sid, grantId).money.committed_actual_minor, 250);
});

// -------------------------------------------------------- revocation

test('revocation blocks new admission but does not erase recorded usage', () => {
  const { db, repositories, budget, session, envelope, grantId } = setup('revocation', {
    grant: { maxCostMinor: 1_000 },
  });
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'rev-op-1'));
  budget.settle(envelope, {
    session_id: sid,
    operation_id: 'rev-op-1',
    lease_epoch: 0,
    actual_minor: 90,
  });

  // WER-009's reviewed revokeRunGrant flips this same durable row.
  db.write((handle) => {
    handle
      .prepare(
        `UPDATE council_approvals
            SET status = 'revoked', revoked_at = ?, revoked_by = 'owner-1'
          WHERE tenant_id = ? AND company_id = ? AND id = ? AND status = 'active'`,
      )
      .run(nowIso, envelope.tenant_id, envelope.company_id, grantId);
  });

  assert.throws(
    () => budget.reserve(envelope, reserveArgs(session, grantId, 'rev-op-2')),
    isBudget('BUDGET_GRANT_INACTIVE'),
  );
  assert.throws(
    () =>
      budget.renewGrantCeiling(envelope, {
        grant_id: grantId,
        session_id: sid,
        lease_epoch: 0,
        additional_minor: 100,
      }),
    isBudget('BUDGET_GRANT_INACTIVE'),
  );

  // Prior effects stand: usage, reservation row, and journal remain.
  const snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.consumed.provider_requests, 1);
  assert.equal(snap.money.committed_actual_minor, 90);
  assert.equal(budget.getReservation(envelope, sid, 'rev-op-1')?.state, 'committed');
  const events = repositories.journal.list(envelope, sid, 0);
  assert.ok(events.some((event) => event.type === 'operation_reserved'));
  assert.ok(
    events.some(
      (event) =>
        event.type === 'operation_completed' &&
        event.payload.outcome === 'settled',
    ),
  );
});

// ---------------------------------------------------------- renewal

test('renewal adds authorized capacity without resetting historical counters', () => {
  const { budget, session, envelope, grantId } = setup('renewal', {
    grant: { maxCostMinor: 100 },
  });
  const sid = session.spec.session_id;
  budget.reserve(envelope, reserveArgs(session, grantId, 'renew-op-1', {
    estimate_minor: 80,
  }));
  budget.settle(envelope, {
    session_id: sid,
    operation_id: 'renew-op-1',
    lease_epoch: 0,
    actual_minor: 80,
  });
  const before = budget.grantLedger(envelope, grantId);
  assert.equal(before.committed_actual_minor, 80);
  assert.equal(before.consumed_provider_requests, 1);

  // The old ceiling refuses the next hold.
  assert.throws(
    () =>
      budget.reserve(
        envelope,
        reserveArgs(session, grantId, 'renew-op-2', { estimate_minor: 50 }),
      ),
    isBudget('BUDGET_EXHAUSTED'),
  );

  const renewal = budget.renewGrantCeiling(envelope, {
    grant_id: grantId,
    session_id: sid,
    lease_epoch: 0,
    additional_minor: 100,
    authority_ref: 'operator-renewal-1',
  });
  assert.equal(renewal.previous_max_cost_minor, 100);
  assert.equal(renewal.new_max_cost_minor, 200);
  // Renewal reports the preserved history, not reset counters.
  assert.equal(renewal.committed_actual_minor, 80);
  assert.equal(renewal.consumed_provider_requests, 1);

  const after = budget.grantLedger(envelope, grantId);
  assert.equal(after.max_cost_minor, 200);
  assert.equal(after.committed_actual_minor, 80);
  assert.equal(after.consumed_provider_requests, 1);
  const snap = budget.snapshot(envelope, sid, grantId);
  assert.equal(snap.consumed.provider_requests, 1);
  assert.equal(snap.money.committed_actual_minor, 80);

  // The added capacity is real.
  budget.reserve(envelope, reserveArgs(session, grantId, 'renew-op-2', {
    estimate_minor: 50,
  }));
  assert.equal(budget.grantLedger(envelope, grantId).outstanding_minor, 130);

  // Renewal only adds: a zero or negative add is refused.
  assert.throws(
    () =>
      budget.renewGrantCeiling(envelope, {
        grant_id: grantId,
        session_id: sid,
        lease_epoch: 0,
        additional_minor: 0,
      }),
    isBudget('BUDGET_INVALID_INPUT'),
  );
});
