/**
 * Focused WER-011 producer checks. node:test + tsx (the repository's own
 * runner: `node --import tsx --test src/queue/producer.test.ts`).
 *
 * Covered here:
 * - atomic admission writes transition + job + event + outbox;
 * - duplicate admission creates exactly one job and replays the receipt;
 * - changed fingerprint under one key conflicts before any write;
 * - a losing concurrent duplicate returns the committed receipt;
 * - QUEUED without its job is rejected;
 * - attemptOrdinal and attemptId survive a store restart;
 * - a stale lease generation cannot commit;
 * - every semantic state label maps onto the existing canonical enums.
 *
 * Deferred and NOT asserted here: real provider dispatch, worker
 * acknowledgment, live replay, installed acceptance.
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { buildSampleSession } from '../cli/fixture-transport.js';
import type { StoredSession } from '../cli/host-ports.js';
import type { SessionState, SessionStateRecord } from '../contracts/index.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from '../persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../persistence/index.js';
import { CouncilJobs } from '../persistence/jobs.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import { CouncilDatabase } from '../persistence/sqlite.js';
import { JobRunnerError } from './errors.js';
import {
  DurableOperationProducer,
  OPERATION_STATE_LABEL_MAP,
  type AdmissionCommand,
} from './producer.js';

// ------------------------------------------------------------- fixtures

const BUSY = { busyTimeoutMs: 500, busyMaxAttempts: 3, busyBaseDelayMs: 10 };

function tempDbPath(label: string): string {
  return join(mkdtempSync(join(tmpdir(), `wer011-${label}-`)), 'council.db');
}

function makeClock(): { nowUtc: () => string } {
  return { nowUtc: () => '2026-10-18T12:00:00.000Z' };
}

function makeIds(prefix: string): { newId: () => string } {
  let counter = 0;
  return { newId: () => `${prefix}-${(counter += 1).toString().padStart(4, '0')}` };
}

function storedSession(state: SessionState, stateVersion = 0): StoredSession {
  const sample = buildSampleSession();
  const record: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: sample.spec.session_id,
    mode: sample.spec.mode,
    state,
    state_version: stateVersion,
    brief_revision: sample.brief.revision,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: sample.spec.created_at,
  };
  return {
    spec: sample.spec,
    brief: sample.brief,
    scope: sample.scope,
    state: record,
    sample: false,
  };
}

interface Harness {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  producer: DurableOperationProducer;
  session: StoredSession;
  envelope: AuthorizationEnvelope;
}

function openHarness(
  dbPath: string,
  options: {
    state?: SessionState;
    stateVersion?: number;
    idPrefix?: string;
    createSession?: boolean;
  } = {},
): Harness {
  const clock = makeClock();
  const ids = makeIds(options.idPrefix ?? 'id');
  const db = CouncilDatabase.open(dbPath, BUSY);
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const repositories = new CouncilRepositories(db, {
    clock,
    ids,
    config: parsePersistenceConfig(),
  });
  const session = storedSession(options.state ?? 'READY', options.stateVersion ?? 0);
  const envelope = envelopeFromScope(session.scope, 'owner-1', 'owner', 'write');
  if (options.createSession !== false) repositories.createSession(envelope, session);
  const jobs = new CouncilJobs(db, { clock, ids });
  const producer = new DurableOperationProducer({ db, repositories, jobs, clock, ids });
  return { db, repositories, producer, session, envelope };
}

const SHA_A = 'a'.repeat(64);
const SHA_B = 'b'.repeat(64);
const SHA_C = 'c'.repeat(64);
const SHA_D = 'd'.repeat(64);
const SHA_E = 'e'.repeat(64);

function command(
  sessionId: string,
  overrides: Partial<AdmissionCommand> = {},
): AdmissionCommand {
  return {
    sessionId,
    idempotencyKey: 'admission-key-1',
    operationKind: 'provider_request',
    purpose: 'opening',
    inputHash: SHA_A,
    routeSnapshotHash: SHA_B,
    grantId: 'grant-1',
    packHash: SHA_C,
    round: 1,
    seatId: 'simon-sinek',
    reservation: {
      requests: 1,
      tokens: null,
      moneyMinorUnits: null,
      currency: null,
      costKnowledge: 'unknown',
    },
    transition: { to: 'QUEUED', expectedVersion: 0 },
    ...overrides,
  };
}

function countJobs(harness: Harness): number {
  return (
    harness.db.read((handle) =>
      handle
        .prepare(`SELECT COUNT(*) AS n FROM council_jobs WHERE kind = 'operation'`)
        .get(),
    ) as { n: number }
  ).n;
}

function jobRow(harness: Harness): {
  id: string;
  idempotency_key: string;
  state: string;
  lease_epoch: number;
} {
  return harness.db.read((handle) =>
    handle
      .prepare(
        `SELECT id, idempotency_key, state, lease_epoch FROM council_jobs WHERE kind = 'operation' LIMIT 1`,
      )
      .get(),
  ) as { id: string; idempotency_key: string; state: string; lease_epoch: number };
}

function countEvents(harness: Harness, type: string): number {
  return (
    harness.db.read((handle) =>
      handle
        .prepare(`SELECT COUNT(*) AS n FROM council_events WHERE type = ?`)
        .get(type),
    ) as { n: number }
  ).n;
}

function countOutbox(harness: Harness): number {
  return (
    harness.db.read((handle) =>
      handle.prepare(`SELECT COUNT(*) AS n FROM council_projection_outbox`).get(),
    ) as { n: number }
  ).n;
}

function codeOf(fn: () => unknown): string {
  try {
    fn();
  } catch (error) {
    assert.ok(error instanceof JobRunnerError, `expected JobRunnerError, got ${String(error)}`);
    return error.code;
  }
  assert.fail('expected the call to throw');
}

// ---------------------------------------------------------------- tests

test('admission commits transition, job, event and outbox atomically', () => {
  const harness = openHarness(tempDbPath('atomic'));
  const result = harness.producer.admitOperation(
    harness.envelope,
    command(harness.session.spec.session_id),
  );
  try {
    assert.equal(result.outcome, 'admitted');
    const receipt = result.receipt;
    assert.equal(receipt.state, 'queued');
    assert.equal(receipt.stateLabel, 'never_dispatched');
    assert.equal(receipt.attemptOrdinal, 1);
    assert.equal(receipt.runGeneration, 1);
    const reserved = harness.db.read((handle) =>
      handle
        .prepare(`SELECT sequence FROM council_events WHERE type = 'operation_reserved'`)
        .get(),
    ) as { sequence: number };
    assert.equal(receipt.eventSequence, reserved.sequence);

    const session = harness.repositories.getSession(
      harness.envelope,
      harness.session.spec.session_id,
    );
    assert.equal(session?.state.state, 'QUEUED');
    assert.equal(session?.state.state_version, 1);

    const job = jobRow(harness);
    assert.equal(job.state, 'queued');
    // The receipt's operationId IS the job's canonical operation key.
    assert.equal(receipt.operationId, job.idempotency_key);

    assert.equal(countEvents(harness, 'operation_reserved'), 1);
    assert.equal(countOutbox(harness), 1);
  } finally {
    harness.db.close();
  }
});

test('duplicate admission creates exactly one job and returns the original receipt', () => {
  const harness = openHarness(tempDbPath('duplicate'));
  const cmd = command(harness.session.spec.session_id);
  try {
    const first = harness.producer.admitOperation(harness.envelope, cmd);
    const second = harness.producer.admitOperation(harness.envelope, cmd);

    assert.equal(first.outcome, 'admitted');
    assert.equal(second.outcome, 'replayed');
    assert.deepEqual(second.receipt, first.receipt);
    assert.equal(countJobs(harness), 1);
    assert.equal(countEvents(harness, 'operation_reserved'), 1);
    assert.equal(countOutbox(harness), 1);
  } finally {
    harness.db.close();
  }
});

test('changed fingerprint under the same key conflicts before any write', () => {
  const harness = openHarness(tempDbPath('conflict'));
  const base = command(harness.session.spec.session_id);
  try {
    const first = harness.producer.admitOperation(harness.envelope, base);
    const changed = command(harness.session.spec.session_id, {
      purpose: 'challenge',
      inputHash: SHA_D,
      transition: undefined,
    });

    assert.equal(
      codeOf(() => harness.producer.admitOperation(harness.envelope, changed)),
      'OPERATION_ADMISSION_CONFLICT',
    );
    assert.equal(countJobs(harness), 1);
    assert.equal(countEvents(harness, 'operation_reserved'), 1);

    const requestKey = harness.db.read((handle) =>
      handle
        .prepare(
          `SELECT payload_fingerprint, response_operation_id
             FROM council_request_keys WHERE request_key = ?`,
        )
        .get(base.idempotencyKey),
    ) as { payload_fingerprint: string; response_operation_id: string };
    assert.equal(requestKey.response_operation_id !== null, true);
    assert.equal(
      harness.producer.readReceipt(harness.envelope, first.receipt.operationId).inputHash,
      SHA_A,
    );
  } finally {
    harness.db.close();
  }
});

test('a losing concurrent duplicate returns the committed matching receipt', () => {
  const dbPath = tempDbPath('concurrent');
  const winner = openHarness(dbPath, { idPrefix: 'winner' });
  const cmd = command(winner.session.spec.session_id);
  let loser: Harness | null = null;
  try {
    const first = winner.producer.admitOperation(winner.envelope, cmd);
    // A second store connection starts after the winner's BEGIN
    // IMMEDIATE transaction commits: its request-key read sees the
    // committed row and it performs no mutation.
    loser = openHarness(dbPath, { idPrefix: 'loser', createSession: false });
    const second = loser.producer.admitOperation(loser.envelope, cmd);

    assert.equal(first.outcome, 'admitted');
    assert.equal(second.outcome, 'replayed');
    assert.equal(second.receipt.operationId, first.receipt.operationId);
    assert.equal(second.receipt.attemptOrdinal, first.receipt.attemptOrdinal);
    assert.equal(countJobs(winner), 1);
  } finally {
    loser?.db.close();
    winner.db.close();
  }
});

test('QUEUED without its durable job is rejected', () => {
  const harness = openHarness(tempDbPath('orphan'));
  const cmd = command(harness.session.spec.session_id);
  try {
    const admitted = harness.producer.admitOperation(harness.envelope, cmd);
    const job = jobRow(harness);
    harness.db.write((handle) =>
      handle.prepare(`DELETE FROM council_jobs WHERE id = ?`).run(job.id),
    );

    assert.equal(
      codeOf(() => harness.producer.admitOperation(harness.envelope, cmd)),
      'OPERATION_QUEUED_WITHOUT_JOB',
    );
    assert.equal(
      codeOf(() =>
        harness.producer.assertQueuedHasJob(
          harness.envelope,
          harness.session.spec.session_id,
        ),
      ),
      'OPERATION_QUEUED_WITHOUT_JOB',
    );
    assert.equal(
      codeOf(() =>
        harness.producer.readReceipt(harness.envelope, admitted.receipt.operationId),
      ),
      'OPERATION_QUEUED_WITHOUT_JOB',
    );
  } finally {
    harness.db.close();
  }
});

test('attemptOrdinal and attemptId survive a store restart', () => {
  const dbPath = tempDbPath('restart');
  const first = openHarness(dbPath, { idPrefix: 'first' });
  const cmd = command(first.session.spec.session_id);
  let admitted!: ReturnType<DurableOperationProducer['admitOperation']>;
  let claimed!: ReturnType<DurableOperationProducer['claimOperation']>;
  try {
    admitted = first.producer.admitOperation(first.envelope, cmd);
    claimed = first.producer.claimOperation(
      first.envelope,
      admitted.receipt.operationId,
      'worker-a',
    );
    assert.equal(claimed.attemptOrdinal, 1);
  } finally {
    first.db.close();
  }

  const restarted = openHarness(dbPath, { idPrefix: 'second', createSession: false });
  try {
    const receipt = restarted.producer.readReceipt(
      restarted.envelope,
      admitted.receipt.operationId,
    );
    assert.equal(receipt.attemptOrdinal, 1);
    assert.equal(receipt.attemptId, admitted.receipt.attemptId);
    assert.equal(receipt.leaseGeneration, 1);
    assert.equal(receipt.leaseOwner, 'worker-a');
    assert.equal(receipt.state, 'leased');
    // A fresh claim after release advances the fencing generation but
    // never the persisted attempt ordinal.
    restarted.producer.releaseLease(restarted.envelope, {
      operationId: receipt.operationId,
      leaseOwner: 'worker-a',
      leaseGeneration: receipt.leaseGeneration,
    });
    const reclaimed = restarted.producer.claimOperation(
      restarted.envelope,
      receipt.operationId,
      'worker-b',
    );
    assert.equal(reclaimed.leaseGeneration, 2);
    assert.equal(reclaimed.attemptOrdinal, 1);
    assert.equal(reclaimed.attemptId, admitted.receipt.attemptId);
  } finally {
    restarted.db.close();
  }
});

test('a stale lease generation cannot commit', () => {
  const harness = openHarness(tempDbPath('fence'));
  const cmd = command(harness.session.spec.session_id);
  try {
    const admitted = harness.producer.admitOperation(harness.envelope, cmd);
    const operationId = admitted.receipt.operationId;

    const workerA = harness.producer.claimOperation(harness.envelope, operationId, 'worker-a');
    assert.equal(workerA.leaseGeneration, 1);
    harness.producer.releaseLease(harness.envelope, {
      operationId,
      leaseOwner: 'worker-a',
      leaseGeneration: workerA.leaseGeneration,
    });
    const workerB = harness.producer.claimOperation(harness.envelope, operationId, 'worker-b');
    assert.equal(workerB.leaseGeneration, 2);

    assert.equal(
      codeOf(() =>
        harness.producer.recordDispatchIntent(harness.envelope, {
          operationId,
          leaseOwner: 'worker-a',
          leaseGeneration: 1,
        }),
      ),
      'OPERATION_LEASE_FENCED',
    );

    const dispatched = harness.producer.recordDispatchIntent(harness.envelope, {
      operationId,
      leaseOwner: 'worker-b',
      leaseGeneration: 2,
    });
    assert.equal(dispatched.stateLabel, 'potentially_dispatched');
    assert.equal(dispatched.state, 'running');
    assert.equal(dispatched.retryDisposition, 'reconcile_first');
  } finally {
    harness.db.close();
  }
});

test('accepted result uses the existing job finish and canonical event', () => {
  const harness = openHarness(tempDbPath('accepted'));
  const cmd = command(harness.session.spec.session_id);
  try {
    const admitted = harness.producer.admitOperation(harness.envelope, cmd);
    const operationId = admitted.receipt.operationId;
    const claimed = harness.producer.claimOperation(harness.envelope, operationId, 'worker-a');
    const fence = {
      operationId,
      leaseOwner: 'worker-a',
      leaseGeneration: claimed.leaseGeneration,
    };
    harness.producer.recordDispatchIntent(harness.envelope, fence, {
      providerRequestId: 'provider-request-1',
    });
    const accepted = harness.producer.recordAcceptedResult(harness.envelope, fence, {
      acceptedResultHash: SHA_E,
      providerRequestId: 'provider-request-1',
      observedUsage: { input_tokens: 10, output_tokens: 20 },
    });

    assert.equal(accepted.state, 'succeeded');
    assert.equal(accepted.stateLabel, 'accepted');
    assert.equal(accepted.acceptedResultHash, SHA_E);
    assert.equal(accepted.canonicalReceipt.status, 'accepted');
    assert.equal(accepted.canonicalReceipt.output_sha256, SHA_E);
    assert.equal(accepted.canonicalReceipt.usage.input_tokens, 10);
    assert.equal(jobRow(harness).state, 'succeeded');
    assert.equal(countEvents(harness, 'operation_completed'), 1);
    assert.equal(countOutbox(harness), 2);
  } finally {
    harness.db.close();
  }
});

test('state labels map explicitly onto existing canonical enums', () => {
  assert.deepEqual(OPERATION_STATE_LABEL_MAP, {
    never_dispatched: { job_state: 'queued', operation_status: 'reserved' },
    potentially_dispatched: { job_state: 'running', operation_status: 'dispatched' },
    response_observed: { job_state: 'running', operation_status: 'dispatched' },
    accepted: { job_state: 'succeeded', operation_status: 'accepted' },
    known_failed: { job_state: 'failed', operation_status: 'failed' },
    cancelled_fenced: { job_state: 'cancelled', operation_status: 'cancelled' },
    outcome_unknown: {
      job_state: 'failed',
      operation_status: 'provider_completion_unknown',
    },
  });
});
