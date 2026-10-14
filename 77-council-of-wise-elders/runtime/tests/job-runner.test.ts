/**
 * CWE-027 tests: the durable deliberation job runner and session
 * controls (src/queue/runner.ts, src/queue/workers.ts), composed over
 * CWE-006's scoped store and job substrate, CWE-028's DurableBudget
 * service and runtime capacity, and CWE-049's RunAuthorizationService
 * and RunAdmissionService, with a deterministic fake clock, manual
 * timers, and fake executors (the CWE-004 fixture transport behind the
 * runner's executor port). No live provider calls.
 *
 * Section 35 contracts owned by CWE-027:
 * - T049: crash after a committed card resumes without repeating
 *   completed inference (crash injected at the admission port between
 *   the card commit and consumption recording).
 * - T050: crash after provider submission yields
 *   provider_completion_unknown: never auto-replayed, reservation
 *   retained at estimate until reconciled.
 * - T051: two workers, one job: one active lease, one rejected claim.
 * - T052: an expired worker cannot commit after a newer fencing
 *   generation owns the job.
 * - T053: a cancelled session rejects late results; no verdict or
 *   actions afterward; usage reconciled; CANCELLED terminal.
 * - T054: pause stops dispatch and preserves accounting; resume keeps
 *   the same pinned route and limits.
 * - T066: transport retry and output repair counters are distinct,
 *   bounded, and enforced across resumption and restart.
 * - T156: a provider call beyond the host scheduler's 90 second lease
 *   stays governed by the renewable council operation authority.
 * - T157: a worker without host AsyncLocalStorage job context still
 *   self-fences before every protected commit.
 * - T158: hot reload, restart, shutdown, and lost wakeups spawn no
 *   duplicate workers and strand no durable queue work.
 *
 * Also proven: the admission composition (no operation runs without
 * CWE-049 admission; grant revocation mid-run fences in-flight commits
 * and stops new dispatch), the capacity-full deferral, and the
 * admitted-but-never-dispatched recovery (hold released, job
 * requeued exactly once).
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  type RunCeilings,
  type ScopeFields,
  type SeatId,
  type SessionStateRecord,
} from '../src/contracts/index.js';
import {
  DeterministicFixtureTransport,
  buildSampleSession,
} from '../src/cli/fixture-transport.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import {
  RunAdmissionService,
  RunAuthorizationService,
  type TrustedPrincipal,
} from '../src/authorization/index.js';
import {
  BudgetCapacityError,
  DurableBudgetService,
  type PinnedRouteSnapshot,
} from '../src/budgets/index.js';
import { parsePersistenceConfig } from '../src/persistence/config.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from '../src/persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../src/persistence/index.js';
import { CouncilJobs } from '../src/persistence/jobs.js';
import { CouncilRepositories } from '../src/persistence/repositories.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';
import {
  DurableJobRunner,
  HOST_SCHEDULER_LEASE_MS,
  JobRunnerError,
  RuntimeCapacity,
  SimulatedCrashError,
  TransportDispatchError,
  startCouncilWorkers,
  stopCouncilWorkers,
  wakeCouncilWorkers,
  type JobClaim,
  type OperationDispatchContext,
  type OperationDispatchResult,
  type OperationExecutorPort,
  type RunnerTimers,
} from '../src/queue/index.js';

// ------------------------------------------------------------- fixtures

let nowIso = '2026-10-14T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

function advanceClock(ms: number): void {
  nowIso = new Date(Date.parse(nowIso) + ms).toISOString();
}

function resetClock(): void {
  nowIso = '2026-10-14T12:00:00.000Z';
}

const ROUTE_POLICY_SHA256 = canonicalHash({ policy: 'route-policy-a' });

function scope(overrides: Partial<ScopeFields> = {}): ScopeFields {
  return {
    tenant_id: 'tenant-a',
    company_id: 'company-a',
    installation_id: 'install-a',
    owner_subject: 'owner-1',
    ...overrides,
  };
}

function storedSession(sessionId: string, sessionScope: ScopeFields): StoredSession {
  const sample = buildSampleSession();
  const spec = { ...sample.spec, session_id: sessionId };
  const brief = { ...sample.brief, session_id: sessionId };
  spec.brief_sha256 = canonicalHash(brief);
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: sessionId,
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
  return { spec, brief, scope: sessionScope, state, sample: false };
}

function ownerEnvelope(sessionScope: ScopeFields): AuthorizationEnvelope {
  return envelopeFromScope(sessionScope, 'owner-1', 'owner', 'write');
}

function workerEnvelope(sessionScope: ScopeFields): AuthorizationEnvelope {
  // The host composes the worker envelope inside the session owner's
  // scope: the worker executes the owner's session in the owner's
  // installation, which is what makes private sessions visible to it
  // under CWE-006's repository rules.
  return envelopeFromScope(sessionScope, 'owner-1', 'worker', 'write');
}

function ownerPrincipal(sessionScope: ScopeFields): TrustedPrincipal {
  return {
    tenant_id: sessionScope.tenant_id,
    company_id: sessionScope.company_id,
    installation_id: sessionScope.installation_id,
    subject: sessionScope.owner_subject ?? 'owner-1',
    channel: 'local_owner',
    support_access: false,
  };
}

function routeSnapshot(
  sessionScope: ScopeFields,
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
      tenantId: sessionScope.tenant_id,
      companyId: sessionScope.company_id,
      installationId: sessionScope.installation_id,
      ownerSubject: sessionScope.owner_subject,
    },
    createdAt: nowIso,
    ...overrides,
  };
}

function ceilings(overrides: Partial<RunCeilings> = {}): RunCeilings {
  return {
    max_provider_requests: 50,
    max_output_repairs: 9,
    max_transport_retries: 8,
    max_input_tokens: null,
    max_output_tokens: null,
    max_money: { amount_minor: 100_000, currency: 'USD' },
    ...overrides,
  };
}

// ---------------------------------------------------------- manual timers

class ManualTimers implements RunnerTimers {
  private readonly everyFns = new Set<() => void>();
  private readonly delays: Array<{ resolve: () => void }> = [];

  every(_ms: number, fn: () => void): () => void {
    this.everyFns.add(fn);
    return () => this.everyFns.delete(fn);
  }

  delay(_ms: number): Promise<void> {
    return new Promise((resolve) => {
      this.delays.push({ resolve });
    });
  }

  tick(): void {
    for (const fn of [...this.everyFns]) fn();
  }

  releaseDelays(): void {
    for (const entry of this.delays.splice(0)) entry.resolve();
  }
}

// ------------------------------------------------------------- executors

const fixtureTransport = new DeterministicFixtureTransport();

async function fixtureResult(
  ctx: OperationDispatchContext,
): Promise<OperationDispatchResult> {
  const response = await fixtureTransport.generate({
    purpose: 'advisor',
    session_id: ctx.session.spec.session_id,
    seat_id: ctx.claim.seat_id as SeatId,
    round: (ctx.claim.descriptor.round === 2
      ? 2
      : ctx.claim.descriptor.round === 3
        ? 3
        : 1) as 1 | 2 | 3,
    route_id: ctx.session.spec.model_policy.route_id,
    model_policy: ctx.session.spec.model_policy,
    system: 'cwe027-test',
    input: {
      brief: ctx.session.brief,
      input_manifest_sha256: ctx.claim.job.input_sha256,
      pack_version: ctx.session.spec.source_pack_version,
    },
  });
  return {
    author: JSON.parse(response.text) as Record<string, unknown>,
    provider_request_id: response.provider_request_id,
    actual_minor: 100,
    input_tokens: response.usage.input_tokens,
    output_tokens: response.usage.output_tokens,
  };
}

class FakeExecutor implements OperationExecutorPort {
  dispatches = 0;
  handler: (
    ctx: OperationDispatchContext,
    callIndex: number,
  ) => Promise<OperationDispatchResult>;

  constructor(
    handler: (
      ctx: OperationDispatchContext,
      callIndex: number,
    ) => Promise<OperationDispatchResult> = (ctx) => fixtureResult(ctx),
  ) {
    this.handler = handler;
  }

  async dispatch(ctx: OperationDispatchContext): Promise<OperationDispatchResult> {
    this.dispatches += 1;
    return this.handler(ctx, this.dispatches);
  }
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// ------------------------------------------------------------ composition

interface Composition {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  jobs: CouncilJobs;
  budget: DurableBudgetService;
  grants: RunAuthorizationService;
  admission: RunAdmissionService;
}

function compose(dbPath: string): Composition {
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
  const jobs = new CouncilJobs(db, { clock, ids });
  const budget = new DurableBudgetService({ db, clock, ids });
  const grants = new RunAuthorizationService({ db, clock, ids });
  const admission = new RunAdmissionService(grants, budget);
  return { db, repositories, jobs, budget, grants, admission };
}

function makeRunner(
  ctx: Composition,
  executor: OperationExecutorPort,
  extra: {
    timers?: RunnerTimers;
    capacity?: RuntimeCapacity;
    admission?: RunAdmissionService;
  } = {},
): DurableJobRunner {
  return new DurableJobRunner({
    db: ctx.db,
    repositories: ctx.repositories,
    jobs: ctx.jobs,
    budget: ctx.budget,
    admission: extra.admission ?? ctx.admission,
    grants: ctx.grants,
    clock,
    ids,
    executor,
    timers: extra.timers ?? new ManualTimers(),
    capacity: extra.capacity,
  });
}

function tempDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `cwe027-${label}-`));
}

interface Setup {
  ctx: Composition;
  dbPath: string;
  session: StoredSession;
  envelope: AuthorizationEnvelope;
  worker: AuthorizationEnvelope;
  principal: TrustedPrincipal;
  grantId: string;
  snapshot: PinnedRouteSnapshot;
}

/**
 * A session created, granted (preview + approve), and walked to
 * ROUND_1, ready for enqueue/claim/execute.
 */
function setupRunningSession(
  label: string,
  options: { ceilings?: RunCeilings; sessionId?: string } = {},
): Setup {
  resetClock();
  const sessionScope = scope();
  const dbPath = join(tempDir(label), 'council.db');
  const ctx = compose(dbPath);
  const session = storedSession(options.sessionId ?? 'sess-1', sessionScope);
  const envelope = ownerEnvelope(sessionScope);
  ctx.repositories.createSession(envelope, session);
  const snapshot = routeSnapshot(sessionScope);
  const preview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: snapshot,
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: options.ceilings ?? ceilings(),
  });
  const grant = ctx.grants.approveRun(envelope, preview.preview_id, {
    principal: ownerPrincipal(sessionScope),
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  // Walk DRAFT -> READY -> QUEUED -> PREPARING -> ROUND_1.
  let version = 0;
  for (const to of ['READY', 'QUEUED', 'PREPARING', 'ROUND_1'] as const) {
    ctx.repositories.transitionState(envelope, session.spec.session_id, to, version);
    version += 1;
  }
  return {
    ctx,
    dbPath,
    session,
    envelope,
    worker: workerEnvelope(sessionScope),
    principal: ownerPrincipal(sessionScope),
    grantId: grant.grant_id,
    snapshot,
  };
}

function enqueueSeatOperation(
  runner: DurableJobRunner,
  setup: Setup,
  seat: SeatId,
  label: string,
): { jobId: string; operationId: string; inputSha: string } {
  const inputSha = canonicalHash({ cwe027_op: label });
  const job = runner.enqueueOperation(setup.worker, {
    session_id: setup.session.spec.session_id,
    phase_job_key: `round-1:${seat}`,
    seat_id: seat,
    input_sha256: inputSha,
    descriptor: {
      kind: 'provider_request',
      purpose: 'council_run',
      grant_id: setup.grantId,
      estimate_minor: 100,
      currency: 'USD',
      round: 1,
    },
    route_snapshot: setup.snapshot,
  });
  return { jobId: job.id, operationId: canonicalHash({
    session_id: setup.session.spec.session_id,
    attempt: 1,
    phase_job_key: `round-1:${seat}`,
    input_sha256: inputSha,
  }), inputSha };
}

function attemptRow(
  ctx: Composition,
  envelope: AuthorizationEnvelope,
  operationId: string,
): { status: string; outcome_code: string | null } | null {
  const row = ctx.db.read((handle) =>
    handle
      .prepare(
        `SELECT status, outcome_code FROM council_provider_attempts
          WHERE tenant_id = ? AND company_id = ? AND operation_id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, operationId),
  ) as { status: string; outcome_code: string | null } | undefined;
  return row ?? null;
}

function isBudgetCode(code: string) {
  return (error: unknown) =>
    error instanceof BudgetCapacityError && error.code === code;
}

function isRunnerCode(code: string) {
  return (error: unknown) =>
    error instanceof JobRunnerError && error.code === code;
}

// ------------------------------------------------------------------ tests

test('happy path: claim, admission, dispatch, fenced commit, one ledger entry', async () => {
  const setup = setupRunningSession('happy');
  const { ctx, worker } = setup;
  const executor = new FakeExecutor();
  const runner = makeRunner(ctx, executor);
  const seat = setup.session.spec.seat_ids[0];
  const { jobId, operationId, inputSha } = enqueueSeatOperation(runner, setup, seat, 'happy-1');

  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  assert.equal(claim.operation_id, operationId);
  assert.equal(claim.job_lease_epoch, 1);
  assert.equal(claim.session_lease_epoch, 1);

  const outcome = await runner.executeClaimedOperation(worker, claim);
  assert.equal(outcome.status, 'committed');
  assert.ok(outcome.card);
  assert.equal(executor.dispatches, 1);

  const jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs.find((j) => j.id === jobId)?.state, 'succeeded');
  const cards = ctx.repositories.listCards(worker, setup.session.spec.session_id);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].host.operation_id, operationId);
  assert.equal(attemptRow(ctx, worker, operationId)?.status, 'accepted');
  const checkpoint = ctx.jobs.getCheckpoint(worker, {
    sessionId: setup.session.spec.session_id,
    attempt: 1,
    briefRevision: 1,
    phaseJobKey: `round-1:${seat}`,
    seatId: seat,
    inputSha256: inputSha,
    currentCancelGeneration: 0,
  });
  assert.equal(checkpoint?.status, 'accepted');
  const snapshot = ctx.budget.snapshot(worker, setup.session.spec.session_id, setup.grantId);
  assert.equal(snapshot.consumed.provider_requests, 1);
  assert.equal(snapshot.reserved, 0);
  assert.equal(snapshot.unknown, 0);
  assert.equal(
    ctx.repositories.journal.verifyChain(worker, setup.session.spec.session_id).ok,
    true,
  );
  // Nothing left to claim: the work is done exactly once.
  assert.equal(runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1'), null);
});

test('T051: two workers racing one job produce one active lease and one rejected claim', () => {
  const setup = setupRunningSession('t051');
  const { ctx, worker } = setup;
  const runner = makeRunner(ctx, new FakeExecutor());
  const seat = setup.session.spec.seat_ids[0];
  enqueueSeatOperation(runner, setup, seat, 't051-1');

  const claimA = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-a');
  assert.ok(claimA);
  // The second worker's claim is rejected (null), not queued behind
  // the first and not an error: exactly one active lease exists.
  const claimB = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-b');
  assert.equal(claimB, null);
  // Even the owner cannot double-claim its own live lease.
  assert.equal(runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-a'), null);
  const jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].state, 'leased');
  assert.equal(jobs[0].lease_owner, 'worker-a');
  assert.equal(jobs[0].lease_epoch, 1);
});

test('T052: an expired worker cannot commit after a newer fencing generation owns the job', async () => {
  const setup = setupRunningSession('t052');
  const { ctx, worker } = setup;
  const executor = new FakeExecutor();
  const runner = makeRunner(ctx, executor);
  const seat = setup.session.spec.seat_ids[0];
  enqueueSeatOperation(runner, setup, seat, 't052-1');

  const claimA = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-a');
  assert.ok(claimA);
  assert.equal(claimA.session_lease_epoch, 1);

  // Worker A stalls past its 60 second lease. Worker B's first poll
  // reconciles the expired lease (nothing was admitted or dispatched,
  // so the job returns to queued); its next claim takes ownership at a
  // newer job epoch and a newer session fencing generation.
  advanceClock(61_000);
  assert.equal(runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-b'), null);
  const claimB = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-b');
  assert.ok(claimB);
  assert.equal(claimB.job_lease_epoch, 2);
  assert.ok(claimB.session_lease_epoch > claimA.session_lease_epoch);

  // The expired worker's own fence check rejects it...
  assert.throws(
    () => runner.assertFenceCurrent(worker, claimA),
    isRunnerCode('JOB_LEASE_FENCED'),
  );
  // ...its heartbeat cannot resurrect the lease...
  assert.throws(
    () => runner.heartbeatClaim(worker, claimA),
    isRunnerCode('JOB_LEASE_LOST'),
  );
  // ...and its execution is refused at admission by the budget epoch
  // fence, before any dispatch: the stale claim spends nothing.
  const staleOutcome = await runner.executeClaimedOperation(worker, claimA);
  assert.equal(staleOutcome.status, 'admission_refused');
  assert.equal(staleOutcome.reason, 'BUDGET_LEASE_FENCED');
  assert.equal(executor.dispatches, 0);

  // The current owner's execution commits exactly one card.
  const outcomeB = await runner.executeClaimedOperation(worker, claimB);
  assert.equal(outcomeB.status, 'committed');
  assert.equal(executor.dispatches, 1);
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 1);
});

test('T049: crash after a committed card resumes without repeating completed inference', async () => {
  const setup = setupRunningSession('t049');
  const { ctx, worker } = setup;
  const executor = new FakeExecutor();
  // Crash seam: the admission port dies between the card commit and
  // the consumption recording (a worker killed in that exact window).
  let crashArmed = true;
  const crashingAdmission = {
    admitOperation: (envelope: AuthorizationEnvelope, input: unknown) =>
      ctx.admission.admitOperation(envelope, input as never),
    recordConsumption: (envelope: AuthorizationEnvelope, input: unknown) => {
      if (crashArmed) {
        crashArmed = false;
        throw new SimulatedCrashError('after_card_commit_before_consumption');
      }
      return ctx.admission.recordConsumption(envelope, input as never);
    },
  } as unknown as RunAdmissionService;
  const runner = makeRunner(ctx, executor, { admission: crashingAdmission });
  const seat = setup.session.spec.seat_ids[0];
  const { operationId } = enqueueSeatOperation(runner, setup, seat, 't049-1');

  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  await assert.rejects(
    runner.executeClaimedOperation(worker, claim),
    (error: unknown) => error instanceof SimulatedCrashError,
  );
  // The crash window's durable truth: card committed, reservation
  // still held, job still leased to the dead worker.
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 1);
  assert.equal(
    ctx.budget.getReservation(worker, setup.session.spec.session_id, operationId)?.state,
    'reserved',
  );
  assert.equal(executor.dispatches, 1);

  // The worker is gone; its lease expires. A new worker's claim
  // reconciles from durable state alone: the committed card finishes
  // the job, and the unrecorded charge is marked unknown (counted at
  // estimate), never re-dispatched.
  advanceClock(61_000);
  const runner2 = makeRunner(ctx, executor);
  assert.equal(runner2.claimNextOperation(worker, setup.session.spec.session_id, 'worker-2'), null);
  const jobs = runner2.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs[0].state, 'succeeded');
  assert.equal(executor.dispatches, 1, 'completed inference was not repeated');
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 1);
  const reservation = ctx.budget.getReservation(worker, setup.session.spec.session_id, operationId);
  assert.equal(reservation?.state, 'unknown');
  const snapshot = ctx.budget.snapshot(worker, setup.session.spec.session_id, setup.grantId);
  assert.equal(snapshot.unknown, 1);
  assert.equal(snapshot.money.outstanding_minor, 100);
  assert.equal(attemptRow(ctx, worker, operationId)?.status, 'accepted');
});

test('T050: crash after provider submission yields an uncertain attempt, never a free retry', async () => {
  const setup = setupRunningSession('t050');
  const { ctx, worker } = setup;
  let submissions = 0;
  const executor = new FakeExecutor(async (ctx2) => {
    // The provider accepted the request; the worker dies before any
    // local commit. The would-be result never reaches the store.
    submissions += 1;
    void ctx2;
    throw new SimulatedCrashError('after_provider_submission_before_local_commit');
  });
  const runner = makeRunner(ctx, executor);
  const seat = setup.session.spec.seat_ids[0];
  const { operationId, inputSha } = enqueueSeatOperation(runner, setup, seat, 't050-1');

  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  await assert.rejects(
    runner.executeClaimedOperation(worker, claim),
    (error: unknown) => error instanceof SimulatedCrashError,
  );
  assert.equal(submissions, 1);
  assert.equal(attemptRow(ctx, worker, operationId)?.status, 'dispatched');

  // Lease expiry + a fresh worker: reconciliation marks the attempt
  // provider_completion_unknown, retains the reservation at its
  // estimate, and ends the job. It is never requeued and never
  // replayed, on this or any later poll.
  advanceClock(61_000);
  const runner2 = makeRunner(ctx, executor);
  assert.equal(runner2.claimNextOperation(worker, setup.session.spec.session_id, 'worker-2'), null);
  assert.equal(runner2.claimNextOperation(worker, setup.session.spec.session_id, 'worker-2'), null);
  assert.equal(submissions, 1, 'the uncertain attempt was not replayed');
  const jobs = runner2.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs[0].state, 'failed');
  assert.equal(jobs[0].lease_owner, 'worker-1');
  const reservation = ctx.budget.getReservation(worker, setup.session.spec.session_id, operationId);
  assert.equal(reservation?.state, 'unknown');
  const snapshot = ctx.budget.snapshot(worker, setup.session.spec.session_id, setup.grantId);
  assert.equal(snapshot.unknown, 1);
  assert.equal(snapshot.money.outstanding_minor, 100, 'reservation retained at estimate');
  assert.equal(attemptRow(ctx, worker, operationId)?.status, 'provider_completion_unknown');
  const checkpoint = ctx.jobs.getCheckpoint(worker, {
    sessionId: setup.session.spec.session_id,
    attempt: 1,
    briefRevision: 1,
    phaseJobKey: `round-1:${seat}`,
    seatId: seat,
    inputSha256: inputSha,
    currentCancelGeneration: 0,
  });
  assert.equal(checkpoint?.status, 'provider_completion_unknown');
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 0);
});

test('T053: a cancelled session rejects late results; no verdict afterward; usage reconciled', async () => {
  const setup = setupRunningSession('t053');
  const { ctx, worker, envelope } = setup;
  const gate = deferred<OperationDispatchResult>();
  const executor = new FakeExecutor(async (dispatchCtx) => {
    void dispatchCtx;
    return gate.promise;
  });
  const runner = makeRunner(ctx, executor);
  const seatA = setup.session.spec.seat_ids[0];
  const seatB = setup.session.spec.seat_ids[1];
  const first = enqueueSeatOperation(runner, setup, seatA, 't053-1');
  const second = enqueueSeatOperation(runner, setup, seatB, 't053-2');

  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  assert.equal(claim.operation_id, first.operationId);
  const execution = runner.executeClaimedOperation(worker, claim);
  // The dispatch is in flight (the executor was entered synchronously).
  assert.equal(attemptRow(ctx, worker, first.operationId)?.status, 'dispatched');

  // Cancel lands mid-flight: the generation increments immediately.
  const cancelled = runner.cancelSession(envelope, setup.session.spec.session_id);
  assert.equal(cancelled.state, 'CANCELLED');
  assert.equal(cancelled.cancel_generation, 1);
  // The still-queued second job is cancelled in place, never dispatched.
  const jobsAfterCancel = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobsAfterCancel.find((j) => j.id === second.jobId)?.state, 'cancelled');

  // The late provider result arrives and is fenced out: no card, no
  // verdict material, the session is not resurrected.
  gate.resolve(await fixtureResult({
    session: setup.session,
    claim,
    dispatch_operation_id: first.operationId,
    attempt_kind: 'initial',
    repair_issues: [],
  }));
  const outcome = await execution;
  assert.equal(outcome.status, 'fenced');
  assert.equal(outcome.card, null);
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 0);
  const events = ctx.repositories.journal.list(worker, setup.session.spec.session_id, 0);
  assert.equal(events.some((e) => e.type === 'card_accepted'), false);
  assert.equal(events.some((e) => e.type === 'verdict_validated'), false);
  const after = ctx.repositories.getSession(worker, setup.session.spec.session_id);
  assert.equal(after?.state.state, 'CANCELLED');
  assert.equal(after?.state.cancel_generation, 1);

  // Usage is reconciled, not erased: the in-flight request was really
  // made and its consumption is recorded as settled.
  const reservation = ctx.budget.getReservation(worker, setup.session.spec.session_id, first.operationId);
  assert.equal(reservation?.state, 'committed');
  assert.equal(reservation?.actual_minor, 100);
  const jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs.find((j) => j.id === first.jobId)?.state, 'cancelled');
  assert.equal(executor.dispatches, 1);

  // CANCELLED is terminal: no claim, and resume is a precise conflict.
  assert.equal(runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1'), null);
  assert.throws(
    () => runner.resumeSession(envelope, setup.session.spec.session_id),
    isRunnerCode('JOB_CONTROL_CONFLICT'),
  );
  // Repeated cancel is idempotent and changes nothing.
  const again = runner.cancelSession(envelope, setup.session.spec.session_id);
  assert.equal(again.state, 'CANCELLED');
  assert.equal(again.cancel_generation, 1);
  assert.equal(again.state_version, cancelled.state_version);
});

test('T054: pause stops dispatch, preserves accounting; resume keeps the pinned route and limits', async () => {
  const setup = setupRunningSession('t054');
  const { ctx, worker, envelope } = setup;
  const executor = new FakeExecutor();
  const runner = makeRunner(ctx, executor);
  const seatA = setup.session.spec.seat_ids[0];
  const seatB = setup.session.spec.seat_ids[1];
  const first = enqueueSeatOperation(runner, setup, seatA, 't054-1');
  const second = enqueueSeatOperation(runner, setup, seatB, 't054-2');

  const claim1 = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim1);
  const outcome1 = await runner.executeClaimedOperation(worker, claim1);
  assert.equal(outcome1.status, 'committed');
  const totalsBeforePause = ctx.budget.snapshot(worker, setup.session.spec.session_id, setup.grantId);
  assert.equal(totalsBeforePause.consumed.provider_requests, 1);

  const paused = runner.pauseSession(envelope, setup.session.spec.session_id);
  assert.equal(paused.state, 'PAUSED');
  assert.equal(paused.resume_phase, 'ROUND_1');
  // Pause is idempotent at its target: same record, no new version.
  const pausedAgain = runner.pauseSession(envelope, setup.session.spec.session_id);
  assert.equal(pausedAgain.state, 'PAUSED');
  assert.equal(pausedAgain.state_version, paused.state_version);
  // No new dispatch while paused, and nothing was spent by pausing.
  assert.equal(runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1'), null);
  assert.equal(executor.dispatches, 1);
  const totalsDuringPause = ctx.budget.snapshot(worker, setup.session.spec.session_id, setup.grantId);
  assert.equal(totalsDuringPause.consumed.provider_requests, 1);
  assert.deepEqual(totalsDuringPause.ceilings, totalsBeforePause.ceilings);

  const resumed = runner.resumeSession(envelope, setup.session.spec.session_id);
  assert.equal(resumed.state, 'ROUND_1');
  // Resume of a running session is a precise legal-state conflict.
  assert.throws(
    () => runner.resumeSession(envelope, setup.session.spec.session_id),
    isRunnerCode('JOB_CONTROL_CONFLICT'),
  );
  // The pinned route and limits are the grant's, untouched by the
  // pause: the next claim charges the identical snapshot the grant
  // was approved against, and the ceilings still bind.
  const grant = ctx.grants.resolveRunGrant(envelope, setup.grantId, setup.session.spec.session_id);
  assert.ok(grant);
  const claim2 = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim2);
  assert.equal(claim2.operation_id, second.operationId);
  assert.deepEqual(claim2.route_snapshot, setup.snapshot);
  const outcome2 = await runner.executeClaimedOperation(worker, claim2);
  assert.equal(outcome2.status, 'committed');
  const totalsAfter = ctx.budget.snapshot(worker, setup.session.spec.session_id, setup.grantId);
  assert.equal(totalsAfter.consumed.provider_requests, 2);
  assert.equal(totalsAfter.ceilings.max_provider_requests, 50);
  void first;
});

test('T066: retry and repair counters are distinct, bounded, and enforced across restart', async () => {
  // (a) Transport retry: distinct kind, admitted once per original,
  // settled in the one ledger; a second retry admission is refused by
  // CWE-028's per-original ceiling.
  const setupA = setupRunningSession('t066-retry');
  const executorA = new FakeExecutor(async (dispatchCtx, callIndex) => {
    if (callIndex === 1) {
      throw new TransportDispatchError('connection reset before acceptance', {
        retryable: true,
      });
    }
    return fixtureResult(dispatchCtx);
  });
  const runnerA = makeRunner(setupA.ctx, executorA);
  const seatA = setupA.session.spec.seat_ids[0];
  const opA = enqueueSeatOperation(runnerA, setupA, seatA, 't066-retry-1');
  const claimA = runnerA.claimNextOperation(setupA.worker, setupA.session.spec.session_id, 'worker-1');
  assert.ok(claimA);
  const outcomeA = await runnerA.executeClaimedOperation(setupA.worker, claimA);
  assert.equal(outcomeA.status, 'committed');
  assert.equal(executorA.dispatches, 2);
  const snapA = setupA.ctx.budget.snapshot(setupA.worker, setupA.session.spec.session_id, setupA.grantId);
  assert.equal(snapA.envelope_breakdown.transport_retries, 1);
  assert.equal(snapA.envelope_breakdown.planned_generations, 0, 'the not-accepted attempt was released, not counted as a generation');
  assert.equal(snapA.envelope_breakdown.output_repairs, 0);
  assert.equal(snapA.consumed.provider_requests, 1);
  const currentA = setupA.ctx.repositories.getSession(setupA.worker, setupA.session.spec.session_id);
  assert.ok(currentA);
  assert.throws(
    () =>
      setupA.ctx.admission.admitOperation(setupA.worker, {
        grant_id: setupA.grantId,
        session_id: setupA.session.spec.session_id,
        operation_id: `${opA.operationId}:retry:2`,
        kind: 'transport_retry',
        purpose: 'council_run',
        estimate_minor: 100,
        currency: 'USD',
        lease_epoch: currentA.state.lease_epoch,
        route_snapshot: setupA.snapshot,
        original_operation_id: opA.operationId,
      }),
    isBudgetCode('BUDGET_EXHAUSTED'),
    'a second transport retry for the same original is refused by the ledger',
  );

  // (b) Output repair: distinct kind and counter; the repair settles,
  // the job commits the repaired card, and the per-original repair
  // ceiling refuses any second repair, including after a restart
  // (fresh service instances over the same durable store).
  const setupB = setupRunningSession('t066-repair');
  // First output invalid, repair output valid.
  let repairCalls = 0;
  const executorB = new FakeExecutor(async (dispatchCtx) => {
    repairCalls += 1;
    const result = await fixtureResult(dispatchCtx);
    if (repairCalls === 1) {
      return { ...result, author: { ...result.author, stance: 'not-a-stance' } };
    }
    return result;
  });
  const runnerB = makeRunner(setupB.ctx, executorB);
  const seatB = setupB.session.spec.seat_ids[0];
  const opB = enqueueSeatOperation(runnerB, setupB, seatB, 't066-repair-1');
  const claimB = runnerB.claimNextOperation(setupB.worker, setupB.session.spec.session_id, 'worker-1');
  assert.ok(claimB);
  const outcomeB = await runnerB.executeClaimedOperation(setupB.worker, claimB);
  assert.equal(outcomeB.status, 'committed');
  assert.equal(repairCalls, 2);
  const snapB = setupB.ctx.budget.snapshot(setupB.worker, setupB.session.spec.session_id, setupB.grantId);
  assert.equal(snapB.envelope_breakdown.output_repairs, 1);
  assert.equal(snapB.envelope_breakdown.transport_retries, 0);
  assert.equal(snapB.envelope_breakdown.planned_generations, 1);
  assert.equal(snapB.consumed.provider_requests, 2, 'repairs share the one session envelope');

  // Restart: brand-new service instances over the same database file.
  // The counters live in CWE-028's ledger, not in any runner, so the
  // totals are identical after reopening and the repair ceiling still
  // refuses a second repair for this original.
  setupB.ctx.db.close();
  const reopened = compose(setupB.dbPath);
  const snapAfterRestart = reopened.budget.snapshot(
    setupB.worker,
    setupB.session.spec.session_id,
    setupB.grantId,
  );
  assert.equal(snapAfterRestart.envelope_breakdown.output_repairs, 1);
  assert.equal(snapAfterRestart.consumed.provider_requests, 2);
  const sessionAfterRestart = reopened.repositories.getSession(
    setupB.worker,
    setupB.session.spec.session_id,
  );
  assert.ok(sessionAfterRestart);
  assert.throws(
    () =>
      reopened.admission.admitOperation(setupB.worker, {
        grant_id: setupB.grantId,
        session_id: setupB.session.spec.session_id,
        operation_id: `${opB.operationId}:repair:2`,
        kind: 'output_repair',
        purpose: 'council_run',
        estimate_minor: 100,
        currency: 'USD',
        lease_epoch: sessionAfterRestart.state.lease_epoch,
        route_snapshot: setupB.snapshot,
        original_operation_id: opB.operationId,
      }),
    isBudgetCode('BUDGET_EXHAUSTED'),
    'a second output repair for the same original is refused, even after restart',
  );
  reopened.db.close();
});

test('admission: grant revoked mid-run fences the in-flight commit and stops new dispatch', async () => {
  const setup = setupRunningSession('revoke');
  const { ctx, worker, envelope, principal } = setup;
  const gate = deferred<OperationDispatchResult>();
  const executor = new FakeExecutor(async () => gate.promise);
  const runner = makeRunner(ctx, executor);
  const seatA = setup.session.spec.seat_ids[0];
  const seatB = setup.session.spec.seat_ids[1];
  const first = enqueueSeatOperation(runner, setup, seatA, 'revoke-1');
  const second = enqueueSeatOperation(runner, setup, seatB, 'revoke-2');

  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  const execution = runner.executeClaimedOperation(worker, claim);
  assert.equal(attemptRow(ctx, worker, first.operationId)?.status, 'dispatched');

  ctx.grants.revokeRunGrant(envelope, setup.grantId, principal);
  gate.resolve(await fixtureResult({
    session: setup.session,
    claim,
    dispatch_operation_id: first.operationId,
    attempt_kind: 'initial',
    repair_issues: [],
  }));
  const outcome = await execution;
  assert.equal(outcome.status, 'fenced');
  assert.equal(outcome.reason, 'grant_revoked_or_expired_mid_run');
  assert.equal(outcome.card, null);
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 0);
  // The already-accepted request is still accounted (no invented refund).
  const reservation = ctx.budget.getReservation(worker, setup.session.spec.session_id, first.operationId);
  assert.equal(reservation?.state, 'committed');

  // New dispatch under the revoked grant is refused at admission; the
  // job returns to queued unspent and the executor never runs.
  const claim2 = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim2);
  assert.equal(claim2.operation_id, second.operationId);
  const outcome2 = await runner.executeClaimedOperation(worker, claim2);
  assert.equal(outcome2.status, 'admission_refused');
  assert.equal(outcome2.reason, 'RUN_GRANT_INACTIVE');
  assert.equal(executor.dispatches, 1);
  const jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs.find((j) => j.id === second.jobId)?.state, 'queued');
});

test('admission: nothing runs without admission (session ceiling refusal is unspent)', async () => {
  const setup = setupRunningSession('ceiling', {
    ceilings: ceilings({ max_provider_requests: 2 }),
  });
  const { ctx, worker } = setup;
  const executor = new FakeExecutor();
  const runner = makeRunner(ctx, executor);
  const seats = setup.session.spec.seat_ids;
  const ops = [
    enqueueSeatOperation(runner, setup, seats[0], 'ceiling-1'),
    enqueueSeatOperation(runner, setup, seats[1], 'ceiling-2'),
    enqueueSeatOperation(runner, setup, seats[2], 'ceiling-3'),
  ];
  for (const op of ops.slice(0, 2)) {
    const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
    assert.ok(claim);
    assert.equal(claim.operation_id, op.operationId);
    const outcome = await runner.executeClaimedOperation(worker, claim);
    assert.equal(outcome.status, 'committed');
  }
  const claim3 = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim3);
  const outcome3 = await runner.executeClaimedOperation(worker, claim3);
  assert.equal(outcome3.status, 'admission_refused');
  assert.equal(outcome3.reason, 'BUDGET_EXHAUSTED');
  assert.equal(executor.dispatches, 2, 'the refused operation was never dispatched');
  const jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs.find((j) => j.id === ops[2].jobId)?.state, 'queued');
  const snapshot = ctx.budget.snapshot(worker, setup.session.spec.session_id, setup.grantId);
  assert.equal(snapshot.consumed.provider_requests, 2);
});

test('T156: a provider call beyond the 90 second host lease stays governed by renewable council operation authority', async () => {
  const setup = setupRunningSession('t156');
  const { ctx, worker } = setup;
  const timers = new ManualTimers();
  const gate = deferred<OperationDispatchResult>();
  const executor = new FakeExecutor(async () => gate.promise);
  const runner = makeRunner(ctx, executor, { timers });
  const seat = setup.session.spec.seat_ids[0];
  enqueueSeatOperation(runner, setup, seat, 't156-1');

  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  const execution = runner.executeClaimedOperation(worker, claim);

  // Simulate 300 seconds of provider latency: five minutes, far past
  // the host scheduler's 90 second lease and past several 60 second
  // operation-lease TTLs. The worker's 15 second heartbeat keeps the
  // council operation lease live the whole time; the session fencing
  // generation never moves (renewal touches no grant, no counter, no
  // generation).
  for (let i = 0; i < 20; i += 1) {
    advanceClock(15_000);
    timers.tick();
    const jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
    assert.equal(jobs[0].state, 'running');
    assert.ok(
      Date.parse(jobs[0].lease_expires_at ?? '') > Date.parse(nowIso),
      'the council lease is renewed ahead of the clock',
    );
  }
  assert.ok(300_000 > HOST_SCHEDULER_LEASE_MS);
  const midSession = ctx.repositories.getSession(worker, setup.session.spec.session_id);
  assert.equal(midSession?.state.lease_epoch, claim.session_lease_epoch);

  gate.resolve(await fixtureResult({
    session: setup.session,
    claim,
    dispatch_operation_id: claim.operation_id,
    attempt_kind: 'initial',
    repair_issues: [],
  }));
  const outcome = await execution;
  assert.equal(outcome.status, 'committed');
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 1);
});

test('T157: a worker without host job context fences itself before every protected commit', async () => {
  const setup = setupRunningSession('t157');
  const { ctx, worker } = setup;
  const executor = new FakeExecutor();
  const runner = makeRunner(ctx, executor);
  const seat = setup.session.spec.seat_ids[0];
  enqueueSeatOperation(runner, setup, seat, 't157-1');

  // This process has no host scheduler and no AsyncLocalStorage job
  // context at all (throwIfJobLeaseLost would return immediately and
  // prove nothing here). The runner's fence is durable-state only:
  // the legitimate claim passes its own check and commits.
  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  const fence = runner.assertFenceCurrent(worker, claim);
  assert.equal(fence.session_lease_epoch, claim.session_lease_epoch);
  assert.equal(fence.job_lease_epoch, claim.job_lease_epoch);

  // A forged claim (right job, wrong epoch) is rejected by the same
  // self-fence, with no host context involved on either side.
  const forged: JobClaim = { ...claim, job_lease_epoch: claim.job_lease_epoch + 99 };
  assert.throws(
    () => runner.assertFenceCurrent(worker, forged),
    isRunnerCode('JOB_LEASE_FENCED'),
  );
  const forgedSession: JobClaim = { ...claim, session_lease_epoch: claim.session_lease_epoch + 1 };
  assert.throws(
    () => runner.assertFenceCurrent(worker, forgedSession),
    isRunnerCode('JOB_LEASE_FENCED'),
  );

  const outcome = await runner.executeClaimedOperation(worker, claim);
  assert.equal(outcome.status, 'committed');
});

test('T158: start, wake, stop, and restart spawn no duplicate workers and strand no queue work', async () => {
  const setup = setupRunningSession('t158');
  const { ctx, worker } = setup;
  const executor = new FakeExecutor();
  const timers = new ManualTimers();
  const runner = makeRunner(ctx, executor, { timers });
  const seatA = setup.session.spec.seat_ids[0];
  const seatB = setup.session.spec.seat_ids[1];
  enqueueSeatOperation(runner, setup, seatA, 't158-1');

  const supervisorId = 'cwe027-t158-supervisor';
  const handle = startCouncilWorkers({
    runner,
    scopes: [{ envelope: worker, worker_id: 'worker-1' }],
    supervisor_id: supervisorId,
    timers,
  });
  // Re-registration (the hot-reload case) returns the SAME handle and
  // spawns no second supervisor.
  const again = startCouncilWorkers({
    runner,
    scopes: [{ envelope: worker, worker_id: 'worker-1' }],
    supervisor_id: supervisorId,
    timers,
  });
  assert.strictEqual(again, handle);
  wakeCouncilWorkers(handle);
  await stopCouncilWorkers(handle);
  assert.equal(executor.dispatches, 1, 'exactly one worker executed the job');
  let jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs.filter((j) => j.state === 'succeeded').length, 1);
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 1);

  // Shutdown does not strand durable work: enqueue while stopped,
  // then a fresh supervisor's boot reconciliation + first poll picks
  // it up exactly once, without any wakeup ever being delivered (the
  // manual timers never fire: the lost-wakeup case).
  enqueueSeatOperation(runner, setup, seatB, 't158-2');
  const handle2 = startCouncilWorkers({
    runner,
    scopes: [{ envelope: worker, worker_id: 'worker-1' }],
    supervisor_id: supervisorId,
    timers,
  });
  assert.notStrictEqual(handle2, handle);
  await stopCouncilWorkers(handle2);
  assert.equal(executor.dispatches, 2);
  jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs.filter((j) => j.state === 'succeeded').length, 2);
  assert.equal(ctx.repositories.listCards(worker, setup.session.spec.session_id).length, 2);

  // An ephemeral-only surface refuses typed instead of silently
  // pretending to schedule durable work.
  assert.throws(
    () =>
      startCouncilWorkers({
        runner,
        scopes: [{ envelope: worker, worker_id: 'worker-1' }],
        supervisor_id: 'cwe027-t158-ephemeral',
        timers,
        durable_worker_capability: false,
      }),
    isRunnerCode('WORKER_CAPABILITY_UNAVAILABLE'),
  );
});

test('recovery: crash after admission, before dispatch, releases the hold and requeues exactly once', async () => {
  const setup = setupRunningSession('requeue');
  const { ctx, worker } = setup;
  const executor = new FakeExecutor();
  // Crash seam: the capacity port dies on the first acquire, which is
  // after admission and before any dispatch. The durable trail is a
  // 'reserved' attempt, a held reservation, and a leased job.
  let crashArmed = true;
  const crashingCapacity = {
    tryAcquire: () => {
      if (crashArmed) {
        crashArmed = false;
        throw new SimulatedCrashError('after_admission_before_dispatch');
      }
      throw new Error('unreachable in this test');
    },
  } as unknown as RuntimeCapacity;
  const runner = makeRunner(ctx, executor, { capacity: crashingCapacity });
  const seat = setup.session.spec.seat_ids[0];
  const { operationId } = enqueueSeatOperation(runner, setup, seat, 'requeue-1');

  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  await assert.rejects(
    runner.executeClaimedOperation(worker, claim),
    (error: unknown) => error instanceof SimulatedCrashError,
  );
  assert.equal(executor.dispatches, 0);
  assert.equal(attemptRow(ctx, worker, operationId)?.status, 'reserved');
  assert.equal(
    ctx.budget.getReservation(worker, setup.session.spec.session_id, operationId)?.state,
    'reserved',
  );

  // After lease expiry, recovery releases the never-dispatched hold
  // and returns the job to queued; the next claim executes it, and
  // the ledger shows exactly one spent request in total.
  advanceClock(61_000);
  const runner2 = makeRunner(ctx, executor);
  assert.equal(runner2.claimNextOperation(worker, setup.session.spec.session_id, 'worker-2'), null);
  let jobs = runner2.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs[0].state, 'queued');
  assert.equal(
    ctx.budget.getReservation(worker, setup.session.spec.session_id, operationId)?.state,
    'released',
  );
  const claim2 = runner2.claimNextOperation(worker, setup.session.spec.session_id, 'worker-2');
  assert.ok(claim2);
  const outcome = await runner2.executeClaimedOperation(worker, claim2);
  assert.equal(outcome.status, 'committed');
  assert.equal(executor.dispatches, 1);
  jobs = runner2.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs[0].state, 'succeeded');
  const snapshot = ctx.budget.snapshot(worker, setup.session.spec.session_id, setup.grantId);
  assert.equal(snapshot.consumed.provider_requests, 1);
});

test('capacity: a full runtime defers the job unspent; a later cycle runs it', async () => {
  const setup = setupRunningSession('capacity');
  const { ctx, worker } = setup;
  const executor = new FakeExecutor();
  const capacity = new RuntimeCapacity(
    { total_slots: 1, private_reserved_slots: 0 },
    { nowMs: () => Date.parse(nowIso), newTokenId: () => 'cap-token-1' },
  );
  // Occupy the only slot with unrelated work in another scope.
  const held = capacity.tryAcquire({
    operation_key: 'other-operation',
    work_class: 'company',
    scope_key: 'tenant-a:company-a:install-a:other-session',
  });
  assert.equal(held.admitted, true);
  const runner = makeRunner(ctx, executor, { capacity });
  const seat = setup.session.spec.seat_ids[0];
  const { operationId } = enqueueSeatOperation(runner, setup, seat, 'capacity-1');

  const claim = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim);
  const deferredOutcome = await runner.executeClaimedOperation(worker, claim);
  assert.equal(deferredOutcome.status, 'deferred');
  assert.equal(deferredOutcome.reason, 'capacity_full');
  assert.equal(executor.dispatches, 0);
  // The admission was released (never dispatched) and the job is
  // queued again: capacity deferral spends nothing.
  assert.equal(
    ctx.budget.getReservation(worker, setup.session.spec.session_id, operationId)?.state,
    'released',
  );
  let jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs[0].state, 'queued');

  if (held.admitted) capacity.release(held.token.token_id);
  const claim2 = runner.claimNextOperation(worker, setup.session.spec.session_id, 'worker-1');
  assert.ok(claim2);
  const outcome = await runner.executeClaimedOperation(worker, claim2);
  assert.equal(outcome.status, 'committed');
  assert.equal(executor.dispatches, 1);
  jobs = runner.listSessionJobs(worker, setup.session.spec.session_id);
  assert.equal(jobs[0].state, 'succeeded');
});
