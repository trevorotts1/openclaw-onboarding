/**
 * WER-011 receipted-producer tests (unit W01-U003) for
 * src/queue/operation-producer.ts (OperationProducer, the
 * OperationAdmissionReceipt producer) over CWE-006's scoped store,
 * composed like the CWE-027 runner tests: deterministic fake clock,
 * in-file id source, real schema, no live provider calls, no worker
 * acknowledgment, no dispatch, no replay. Those are DEFERRED to the
 * runner units and are never claimed here.
 *
 * The sibling producer (src/queue/producer.ts, DurableOperationProducer)
 * is NOT tested here; it keeps its own producer.test.ts. The final test
 * in this file only proves that the queue barrel exports both.
 *
 * Wiring note: `npm test` runs tests/*.test.ts and
 * tests/scenarios/*.test.ts, so this file (under src/queue) is NOT in
 * that glob. Run it directly:
 *   node --import tsx --test src/queue/operation-producer.test.ts
 *
 * Required coverage:
 * - duplicate admission under one idempotency key creates exactly
 *   one job and returns the original committed receipt;
 * - a changed fingerprint under the same key conflicts before any
 *   write;
 * - a losing concurrent duplicate returns the committed matching
 *   receipt;
 * - queued-without-job is rejected as invalid admission, and the
 *   reconcile readmit branch resolves it into a live operation;
 * - attempt_ordinal survives restart;
 * - a stale lease_generation cannot commit;
 * - an explicit null clears a nullable receipt field while an omitted
 *   one stays unchanged;
 * - potentially_dispatched and response_observed persist and read back
 *   distinctly;
 * - the queue barrel exports both producers.
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  canonicalStringify,
  type RunCeilings,
  type ScopeFields,
  type SeatId,
  type SessionStateRecord,
} from '../contracts/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import {
  buildSampleSession,
} from '../cli/fixture-transport.js';
import {
  RunAuthorizationService,
  type TrustedPrincipal,
} from '../authorization/index.js';
import {
  DurableBudgetService,
  type PinnedRouteSnapshot,
} from '../budgets/index.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { envelopeFromScope } from '../persistence/envelope.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import { CouncilDatabase } from '../persistence/sqlite.js';
import { CouncilJobs } from '../persistence/jobs.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import { COUNCIL_SCHEMA_SQL } from '../persistence/index.js';
import {
  OperationProducer,
  type AdmitOperationRequest,
  type OperationAdmissionReceipt,
} from '../queue/operation-producer.js';
import { JobRunnerError } from '../queue/errors.js';

// ------------------------------------------------------------- fixtures

let nowIso = '2026-10-14T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

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

function ownerEnvelope(s: ScopeFields): AuthorizationEnvelope {
  return envelopeFromScope(s, 'owner-1', 'owner', 'write');
}

function workerEnvelope(s: ScopeFields): AuthorizationEnvelope {
  return envelopeFromScope(s, 'owner-1', 'worker', 'write');
}

function ownerPrincipal(s: ScopeFields): TrustedPrincipal {
  return {
    tenant_id: s.tenant_id,
    company_id: s.company_id,
    installation_id: s.installation_id,
    subject: s.owner_subject ?? 'owner-1',
    channel: 'local_owner',
    support_access: false,
  };
}

function routeSnapshot(s: ScopeFields): PinnedRouteSnapshot {
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
      tenantId: s.tenant_id,
      companyId: s.company_id,
      installationId: s.installation_id,
      ownerSubject: s.owner_subject,
    },
    createdAt: nowIso,
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

interface Composition {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  jobs: CouncilJobs;
  grants: RunAuthorizationService;
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
  void budget;
  return { db, repositories, jobs, grants };
}

interface Setup {
  ctx: Composition;
  dbPath: string;
  envelope: AuthorizationEnvelope;
  worker: AuthorizationEnvelope;
  grantId: string;
  snapshot: PinnedRouteSnapshot;
  session: StoredSession;
}

/** Session created, granted, walked to READY (the admission-legal pre-state). */
function setupReadySession(label: string): Setup {
  nowIso = '2026-10-14T12:00:00.000Z';
  const s = scope();
  const dbPath = join(mkdtempSync(join(tmpdir(), `openclaw-onboarding-W01-U003-${label}-`)), 'council.db');
  const ctx = compose(dbPath);
  const session = storedSession('sess-1', s);
  const envelope = ownerEnvelope(s);
  ctx.repositories.createSession(envelope, session);
  const snapshot = routeSnapshot(s);
  const preview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: snapshot,
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  const grant = ctx.grants.approveRun(envelope, preview.preview_id, {
    principal: ownerPrincipal(s),
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  let version = 0;
  for (const to of ['READY'] as const) {
    ctx.repositories.transitionState(envelope, session.spec.session_id, to, version);
    version += 1;
  }
  return {
    ctx,
    dbPath,
    envelope,
    worker: workerEnvelope(s),
    grantId: grant.grant_id,
    snapshot,
    session,
  };
}

function request(setup: Setup, overrides: Partial<AdmitOperationRequest> = {}): AdmitOperationRequest {
  const seat = setup.session.spec.seat_ids[0];
  return {
    session_id: setup.session.spec.session_id,
    phase_job_key: `round-1:${seat}`,
    seat_id: seat as SeatId,
    input_sha256: canonicalHash({ w01u003: 'input-1' }),
    descriptor: {
      kind: 'provider_request',
      purpose: 'council_run',
      grant_id: setup.grantId,
      estimate_minor: 100,
      currency: 'USD',
      round: 1,
    },
    route_snapshot: setup.snapshot,
    ...overrides,
  };
}

function producer(ctx: Composition): OperationProducer {
  return new OperationProducer({
    db: ctx.db,
    repositories: ctx.repositories,
    jobs: ctx.jobs,
    clock,
    ids,
  });
}

function sessionJobs(setup: Setup): { n: number } {
  return setup.ctx.db.read((handle) =>
    handle
      .prepare(
        `SELECT COUNT(*) AS n FROM council_jobs
          WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND kind = 'operation'`,
      )
      .get(setup.envelope.tenant_id, setup.envelope.company_id, setup.session.spec.session_id),
  ) as { n: number };
}

// ------------------------------------------------------------------ tests

test('duplicate admission under one idempotency key creates exactly one job and returns the original committed receipt', () => {
  const setup = setupReadySession('dup');
  const p = producer(setup.ctx);
  const req = request(setup);

  const first = p.admitOperation(setup.envelope, req);
  assert.equal(first.outcome, 'committed');
  assert.ok(first.created);

  const second = p.admitOperation(setup.envelope, req);
  assert.equal(second.outcome, 'committed');
  assert.equal(second.created, false);
  assert.equal(canonicalHash(second.receipt), canonicalHash(first.receipt));

  assert.equal(sessionJobs(setup).n, 1);
  assert.equal(first.receipt.attempt_ordinal, 1);
  assert.equal(first.receipt.state, 'queued');
  assert.equal(first.receipt.operation_kind, 'provider_request');
  assert.equal(first.receipt.grant_id, setup.grantId);
  // The session transitioned READY -> QUEUED exactly once (version 2).
  const session = setup.ctx.repositories.getSession(
    setup.envelope,
    setup.session.spec.session_id,
  );
  assert.ok(session);
  assert.equal(session.state.state, 'QUEUED');
  assert.equal(session.state.state_version, 2);
});

test('a changed fingerprint under the same key conflicts before any write', () => {
  const setup = setupReadySession('conflict');
  const p = producer(setup.ctx);
  const original = request(setup);
  const first = p.admitOperation(setup.envelope, original);
  assert.ok(first.created);

  const changed = request(setup, {
    descriptor: {
      ...original.descriptor,
      estimate_minor: 999,
    },
  });
  assert.throws(() => p.admitOperation(setup.envelope, changed), (error: unknown) => {
    assert.ok(error instanceof JobRunnerError);
    assert.equal(error.code, 'JOB_DESCRIPTOR_CONFLICT');
    return true;
  });

  // Exactly one job, one receipt, unchanged.
  assert.equal(sessionJobs(setup).n, 1);
  const reread = p.getReceipt(setup.envelope, {
    session_id: original.session_id,
    attempt: 1,
    phase_job_key: original.phase_job_key,
    input_sha256: original.input_sha256,
  });
  assert.ok(reread);
  assert.equal(reread.reserved_units, 100);
  assert.equal(reread.admission_fingerprint, first.receipt.admission_fingerprint);
});

test('a losing concurrent duplicate returns the committed matching receipt', () => {
  const setup = setupReadySession('race');
  const p = producer(setup.ctx);
  const req = request(setup);

  // Two admissions of the same identity on one connection serialize
  // through BEGIN IMMEDIATE: the second sees the first's committed
  // receipt and returns it (created: false), never a second job.
  const first = p.admitOperation(setup.envelope, req);
  const loser = p.admitOperation(setup.envelope, req);
  assert.equal(first.created, true);
  assert.equal(loser.created, false);
  assert.equal(canonicalHash(loser.receipt), canonicalHash(first.receipt));
  assert.equal(loser.receipt.operation_id, first.receipt.operation_id);
  assert.equal(sessionJobs(setup).n, 1);
});

test('queued-without-job is rejected as invalid admission', () => {
  // Historical broken state: session QUEUED with no operation job.
  const setup = setupReadySession('qwj');
  const s = scope();
  const ctx = setup.ctx;
  const brokenSession = storedSession('sess-broken', s);
  const envelope = ownerEnvelope(s);
  ctx.repositories.createSession(envelope, brokenSession);
  let version = 0;
  for (const to of ['READY', 'QUEUED'] as const) {
    ctx.repositories.transitionState(envelope, brokenSession.spec.session_id, to, version);
    version += 1;
  }
  // No job row for sess-broken: queued-without-job.

  const p = producer(ctx);
  const req = request(setup, { session_id: brokenSession.spec.session_id });
  assert.throws(() => p.admitOperation(envelope, req), (error: unknown) => {
    assert.ok(error instanceof JobRunnerError);
    assert.equal(error.code, 'JOB_INVALID_INPUT');
    assert.equal((error.detail as { queued_without_job?: boolean }).queued_without_job, true);
    return true;
  });

  // Reconciliation through the owning service resolves it truthfully.
  const reconciled = p.reconcileQueuedWithoutJob(
    envelope,
    { session_id: brokenSession.spec.session_id },
    { action: 'fail_session' },
  );
  assert.equal(reconciled.reconciled, true);
  const after = ctx.repositories.getSession(envelope, brokenSession.spec.session_id);
  assert.ok(after);
  assert.equal(after.state.state, 'FAILED');
});

test('attempt_ordinal survives restart', () => {
  const setup = setupReadySession('restart');
  const p1 = producer(setup.ctx);
  const req = request(setup);
  const first = p1.admitOperation(setup.envelope, req);
  assert.ok(first.created);
  assert.equal(first.receipt.attempt_ordinal, 1);
  const committedOperationId = first.receipt.operation_id;
  const committedFingerprint = first.receipt.admission_fingerprint;

  // Simulated restart: the whole store is reopened from disk; a fresh
  // producer (fresh process state) reads the receipt back.
  setup.ctx.db.close();
  const ctx2 = compose(setup.dbPath);
  const p2 = producer(ctx2);
  const replay = p2.getReceipt(setup.envelope, {
    session_id: req.session_id,
    attempt: 1,
    phase_job_key: req.phase_job_key,
    input_sha256: req.input_sha256,
  });
  assert.ok(replay);
  assert.equal(replay.operation_id, committedOperationId);
  assert.equal(replay.attempt_ordinal, 1);
  assert.equal(replay.admission_fingerprint, committedFingerprint);

  // A replay admission after restart still returns the SAME receipt.
  const replayed = p2.admitOperation(setup.envelope, req);
  assert.equal(replayed.created, false);
  assert.equal(replayed.receipt.attempt_ordinal, 1);
  assert.equal(canonicalHash(replayed.receipt), canonicalHash(first.receipt));
  ctx2.db.close();
});

test('a stale lease_generation cannot commit', () => {
  const setup = setupReadySession('stale-gen');
  const p = producer(setup.ctx);
  const req = request(setup);
  const first = p.admitOperation(setup.envelope, req);
  assert.ok(first.created);
  const receipt = first.receipt;
  const identity = {
    session_id: req.session_id,
    attempt: 1,
    phase_job_key: req.phase_job_key,
    input_sha256: req.input_sha256,
  };

  // Positive control: the current owner commits at its own generation.
  const okCommit = p.commitMutable(setup.envelope, identity, {
    expected_lease_generation: receipt.lease_generation,
    state: 'response_observed',
    provider_request_id: 'prov-req-1',
  });
  assert.ok(okCommit.committed, 'the owning generation can commit');

  // A newer claim bumps the job row's lease_epoch past the receipt's
  // generation (exactly what a competing worker's claim does).
  setup.ctx.db.write((handle) => {
    handle
      .prepare(
        `UPDATE council_jobs SET lease_epoch = lease_epoch + 1, state = 'leased',
            lease_owner = 'worker-2', updated_at = ?
          WHERE tenant_id = ? AND company_id = ? AND idempotency_key = ?`,
      )
      .run(
        nowIso,
        setup.envelope.tenant_id,
        setup.envelope.company_id,
        receipt.operation_id,
      );
  });

  // The pre-claim generation is now stale: no commit with it lands.
  const attempt = p.commitMutable(setup.envelope, identity, {
    expected_lease_generation: receipt.lease_generation,
    state: 'response_observed',
    provider_request_id: 'prov-req-2',
  });
  assert.equal(attempt.committed, false);
  assert.ok(attempt.receipt);
  assert.equal(
    attempt.receipt.provider_request_id,
    'prov-req-1',
    'the stale commit changed nothing past the fenced owner last write',
  );

  // An arbitrarily higher generation is also refused: the fencing
  // token must MATCH the committed receipt's generation exactly; it
  // is never "greater passes".
  const forged = p.commitMutable(setup.envelope, identity, {
    expected_lease_generation: receipt.lease_generation + 5,
    state: 'response_observed',
    provider_request_id: 'prov-req-3',
  });
  assert.equal(forged.committed, false);
});

// --------------------------------------------- reconciliation (readmit)

/** DRAFT -> READY -> QUEUED with no operation job: the historical break. */
function queuedWithoutJobSession(
  ctx: Composition,
  sessionId: string,
): { session: StoredSession; envelope: AuthorizationEnvelope } {
  const s = scope();
  const session = storedSession(sessionId, s);
  const envelope = ownerEnvelope(s);
  ctx.repositories.createSession(envelope, session);
  let version = 0;
  for (const to of ['READY', 'QUEUED'] as const) {
    ctx.repositories.transitionState(envelope, session.spec.session_id, to, version);
    version += 1;
  }
  return { session, envelope };
}

function operationRows(
  ctx: Composition,
  envelope: AuthorizationEnvelope,
  sessionId: string,
): { id: string; state: string; payload_json: string }[] {
  return ctx.db.read((handle) =>
    handle
      .prepare(
        `SELECT id, state, payload_json FROM council_jobs
          WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND kind = 'operation'
          ORDER BY id`,
      )
      .all(envelope.tenant_id, envelope.company_id, sessionId),
  ) as { id: string; state: string; payload_json: string }[];
}

function countRows(ctx: Composition, sql: string, ...params: unknown[]): number {
  const row = ctx.db.read((handle) => handle.prepare(sql).get(...params)) as { n: number };
  return row.n;
}

test('readmit resolves a queued-without-job session into one live operation', () => {
  const setup = setupReadySession('readmit');
  const { session: broken, envelope } = queuedWithoutJobSession(setup.ctx, 'sess-readmit');
  const p = producer(setup.ctx);
  const req = request(setup, { session_id: broken.spec.session_id });

  // The break is real before the repair.
  assert.equal(operationRows(setup.ctx, envelope, broken.spec.session_id).length, 0);

  const out = p.reconcileQueuedWithoutJob(
    envelope,
    { session_id: broken.spec.session_id },
    { action: 'readmit', request: req },
  );
  assert.equal(out.reconciled, true);
  assert.equal(out.detail.action, 'readmit');
  assert.equal(out.detail.jobs_present, false);
  assert.equal(out.detail.created, true);

  // The repair closes the gap rather than abandoning the queued work.
  const after = setup.ctx.repositories.getSession(envelope, broken.spec.session_id);
  assert.ok(after);
  assert.equal(after.state.state, 'QUEUED');
  assert.equal(after.state.state_version, 2);

  // Exactly one durable operation job, queued, with its receipt.
  const rows = operationRows(setup.ctx, envelope, broken.spec.session_id);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].state, 'queued');
  const receipt = p.getReceipt(envelope, {
    session_id: req.session_id,
    attempt: 1,
    phase_job_key: req.phase_job_key,
    input_sha256: req.input_sha256,
  });
  assert.ok(receipt);
  assert.equal(out.detail.operation_id, receipt.operation_id);
  assert.equal(receipt.state, 'queued');
  assert.equal(receipt.state_label, 'never_dispatched');
  assert.equal(receipt.attempt_ordinal, 1);

  // The journal event and outbox intent committed in the same unit.
  assert.equal(
    countRows(
      setup.ctx,
      `SELECT COUNT(*) AS n FROM council_events
        WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND type = 'operation_reserved'`,
      envelope.tenant_id,
      envelope.company_id,
      broken.spec.session_id,
    ),
    1,
  );
  assert.equal(
    countRows(
      setup.ctx,
      `SELECT COUNT(*) AS n FROM council_projection_outbox
        WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND topic = 'operation.admitted'`,
      envelope.tenant_id,
      envelope.company_id,
      broken.spec.session_id,
    ),
    1,
  );

  // Idempotent: a second reconciliation finds the job and writes nothing.
  const again = p.reconcileQueuedWithoutJob(
    envelope,
    { session_id: broken.spec.session_id },
    { action: 'readmit', request: req },
  );
  assert.equal(again.detail.action, 'none');
  assert.equal(again.detail.jobs_present, true);
  assert.equal(operationRows(setup.ctx, envelope, broken.spec.session_id).length, 1);
});

test('readmit refuses a request bound to a different session', () => {
  const setup = setupReadySession('readmit-mismatch');
  const { session: broken, envelope } = queuedWithoutJobSession(
    setup.ctx,
    'sess-readmit-mismatch',
  );
  const p = producer(setup.ctx);
  assert.throws(
    () =>
      p.reconcileQueuedWithoutJob(
        envelope,
        { session_id: broken.spec.session_id },
        { action: 'readmit', request: request(setup) },
      ),
    (error: unknown) => {
      assert.ok(error instanceof JobRunnerError);
      assert.equal(error.code, 'JOB_INVALID_INPUT');
      assert.equal((error.detail as { session_mismatch?: boolean }).session_mismatch, true);
      return true;
    },
  );
  // Nothing was written for the target session, and it stays repairable.
  assert.equal(operationRows(setup.ctx, envelope, broken.spec.session_id).length, 0);
  const after = setup.ctx.repositories.getSession(envelope, broken.spec.session_id);
  assert.ok(after);
  assert.equal(after.state.state, 'QUEUED');
});

// ------------------------------------------ mutable commits: nulls/labels

test('an explicit null clears a nullable receipt field and an omitted one stays unchanged', () => {
  const setup = setupReadySession('null-clear');
  const p = producer(setup.ctx);
  const req = request(setup);
  const first = p.admitOperation(setup.envelope, req);
  assert.ok(first.created);
  const identity = {
    session_id: req.session_id,
    attempt: 1,
    phase_job_key: req.phase_job_key,
    input_sha256: req.input_sha256,
  };
  const gen = first.receipt.lease_generation;
  const hash = canonicalHash({ result: 'w01u003' });

  const owned = p.commitMutable(setup.envelope, identity, {
    expected_lease_generation: gen,
    lease_owner: 'worker-1',
    lease_expires_at: '2026-10-14T12:01:00.000Z',
    provider_request_id: 'prov-1',
    observed_usage: { input_units: 5, output_units: 7 },
    accepted_result_hash: hash,
  });
  assert.equal(owned.committed, true);

  // Omitted keys leave the committed values alone.
  const partial = p.commitMutable(setup.envelope, identity, {
    expected_lease_generation: gen,
    retry_disposition: 'safe_to_retry',
  });
  assert.equal(partial.committed, true);
  assert.equal(partial.receipt?.lease_owner, 'worker-1');
  assert.equal(partial.receipt?.lease_expires_at, '2026-10-14T12:01:00.000Z');
  assert.equal(partial.receipt?.provider_request_id, 'prov-1');
  assert.deepEqual(partial.receipt?.observed_usage, { input_units: 5, output_units: 7 });
  assert.equal(partial.receipt?.accepted_result_hash, hash);
  assert.equal(partial.receipt?.retry_disposition, 'safe_to_retry');

  // Explicit nulls clear every nullable field (the lease-release case).
  const cleared = p.commitMutable(setup.envelope, identity, {
    expected_lease_generation: gen,
    lease_owner: null,
    lease_expires_at: null,
    provider_request_id: null,
    observed_usage: null,
    accepted_result_hash: null,
  });
  assert.equal(cleared.committed, true);
  assert.equal(cleared.receipt?.lease_owner, null);
  assert.equal(cleared.receipt?.lease_expires_at, null);
  assert.equal(cleared.receipt?.provider_request_id, null);
  assert.equal(cleared.receipt?.observed_usage, null);
  assert.equal(cleared.receipt?.accepted_result_hash, null);

  // The clears are durable, not just the returned object.
  const reread = p.getReceipt(setup.envelope, identity);
  assert.ok(reread);
  assert.equal(reread.lease_owner, null);
  assert.equal(reread.lease_expires_at, null);
  assert.equal(reread.provider_request_id, null);
  assert.equal(reread.observed_usage, null);
  assert.equal(reread.accepted_result_hash, null);
});

test('potentially_dispatched and response_observed persist and read back distinctly', () => {
  const setup = setupReadySession('labels');
  const p = producer(setup.ctx);
  const req = request(setup);
  const first = p.admitOperation(setup.envelope, req);
  assert.ok(first.created);
  const identity = {
    session_id: req.session_id,
    attempt: 1,
    phase_job_key: req.phase_job_key,
    input_sha256: req.input_sha256,
  };
  const gen = first.receipt.lease_generation;

  // Admission starts never_dispatched, in the receipt and from the reader.
  assert.equal(first.receipt.state, 'queued');
  assert.equal(first.receipt.state_label, 'never_dispatched');
  assert.equal(p.stateLabel(setup.envelope, identity), 'never_dispatched');

  const potential = p.commitMutable(setup.envelope, identity, {
    expected_lease_generation: gen,
    state: 'potentially_dispatched',
  });
  assert.equal(potential.committed, true);
  assert.equal(potential.receipt?.state, 'leased'); // canonical JobState
  assert.equal(potential.receipt?.state_label, 'potentially_dispatched');
  assert.equal(p.stateLabel(setup.envelope, identity), 'potentially_dispatched');

  const observed = p.commitMutable(setup.envelope, identity, {
    expected_lease_generation: gen,
    state: 'response_observed',
  });
  assert.equal(observed.committed, true);
  assert.equal(observed.receipt?.state, 'leased'); // same JobState, distinct label
  assert.equal(observed.receipt?.state_label, 'response_observed');
  assert.equal(p.stateLabel(setup.envelope, identity), 'response_observed');

  // Durable: a fresh read of the committed receipt reports the label.
  const reread = p.getReceipt(setup.envelope, identity);
  assert.ok(reread);
  assert.equal(reread.state_label, 'response_observed');

  // A legacy receipt (no state_label, admitted before the field
  // existed) falls back to the durable rows, exactly as before.
  setup.ctx.db.write((handle) => {
    const row = handle
      .prepare(
        `SELECT payload_json FROM council_jobs
          WHERE tenant_id = ? AND company_id = ? AND idempotency_key = ?`,
      )
      .get(
        setup.envelope.tenant_id,
        setup.envelope.company_id,
        reread.operation_id,
      ) as { payload_json: string };
    const payload = JSON.parse(row.payload_json) as {
      receipt: Record<string, unknown>;
    };
    delete payload.receipt.state_label;
    handle
      .prepare(
        `UPDATE council_jobs SET payload_json = ?
          WHERE tenant_id = ? AND company_id = ? AND idempotency_key = ?`,
      )
      .run(
        canonicalStringify(payload),
        setup.envelope.tenant_id,
        setup.envelope.company_id,
        reread.operation_id,
      );
  });
  assert.equal(p.stateLabel(setup.envelope, identity), 'never_dispatched');

  // A terminal job row stays the newest truth for the reader.
  setup.ctx.db.write((handle) => {
    handle
      .prepare(
        `UPDATE council_jobs SET state = 'succeeded', updated_at = ?
          WHERE tenant_id = ? AND company_id = ? AND idempotency_key = ?`,
      )
      .run(
        nowIso,
        setup.envelope.tenant_id,
        setup.envelope.company_id,
        reread.operation_id,
      );
  });
  assert.equal(p.stateLabel(setup.envelope, identity), 'accepted');
});

// --------------------------------------------------------- barrel wiring

test('the queue barrel exports both producers', async () => {
  const barrel = await import('../queue/index.js');
  assert.equal(typeof barrel.OperationProducer, 'function');
  assert.equal(typeof barrel.DurableOperationProducer, 'function');
  assert.notEqual(barrel.OperationProducer, barrel.DurableOperationProducer);
  assert.equal(typeof barrel.RECEIPT_STATE_TO_JOB_STATE, 'object');
});