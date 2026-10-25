/**
 * Canonical durable operation producer (WER-011 dependency-ready slice).
 *
 * This is NOT a second scheduler and NOT a second state machine. It is
 * the single owning path that turns one admission command into durable
 * state, built entirely on the existing substrate:
 *
 * - `CouncilJobs` (persistence/jobs.ts) owns the council_jobs row, its
 *   deterministic operation identity `canonicalHash({session_id,
 *   attempt, phase_job_key, input_sha256})`, and the job lifecycle
 *   (queued -> leased -> running -> succeeded/failed/cancelled).
 * - `CouncilRepositories.transitionState` owns session state legality
 *   and the compare-and-swap state-version write.
 * - `EventJournal` owns the ordered, hash-chained event.
 * - `ProjectionOutbox` owns the durable event/outbox intent.
 * - `council_request_keys` is the canonical idempotency registry:
 *   `(tenant, source, operation, request_key) -> payload_fingerprint,
 *   response_operation_id`. No new key table is introduced.
 *
 * Transaction law: admission commits the requested session transition,
 * the durable job, the `operation_reserved` event, and the outbox
 * intent in ONE short transaction (`CouncilDatabase.write`). A failure
 * anywhere rolls all of them back. No provider call ever runs here.
 *
 * Operation state labels map onto the existing enums (see
 * OPERATION_STATE_LABEL_MAP and queue/producer.test.ts). The semantic
 * label is stored in the existing job payload; the persisted `state`
 * field is always the canonical `JobState`, and the safe accounting
 * projection is the existing `OperationReceipt` contract, validated
 * with `validateOperationReceipt`.
 *
 * Deferred, explicitly NOT claimed here: real provider dispatch, worker
 * acknowledgment, replay against a live transport, and installed
 * acceptance. Those require WER-014/026/027 and are untouched.
 */

import {
  SEAT_IDS,
  assertTransition,
  canonicalHash,
  canonicalStringify,
  isSha256Hex,
  validateOperationReceipt,
  type Clock,
  type CouncilEventType,
  type IdSource,
  type OperationReceipt as CanonicalOperationReceipt,
  type OperationStatus,
  type SeatId,
  type SessionState,
  type SessionStateRecord,
} from '../contracts/index.js';
import type { BudgetReservationKind } from '../budgets/index.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { CouncilJobs, type JobState } from '../persistence/jobs.js';
import type { StoredSession } from '../cli/host-ports.js';
import { ProjectionOutbox } from '../persistence/outbox.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from '../persistence/sqlite.js';
import { JobRunnerError } from './errors.js';

/** Idempotency source of the admission command in council_request_keys. */
export const OPERATION_ADMISSION_SOURCE = 'council-operation-admission';
/** Outbox topic for safe operation state fan-out. */
export const OPERATION_EVENT_TOPIC = 'council.operation';
/** Default council operation lease, matching the runner's canonical TTL. */
export const DEFAULT_OPERATION_LEASE_TTL_MS = 60_000;

/**
 * The persisted semantic labels WER-011 requires. They are derived /
 * mapped onto existing columns; they are never a parallel state enum in
 * the database. `job_state` is council_jobs.state and
 * `operation_status` is the canonical OPERATION_STATUSES enum used by
 * council_provider_attempts and the OperationReceipt contract.
 */
export type OperationStateLabel =
  | 'never_dispatched'
  | 'potentially_dispatched'
  | 'response_observed'
  | 'accepted'
  | 'known_failed'
  | 'cancelled_fenced'
  | 'outcome_unknown';

export const OPERATION_STATE_LABEL_MAP = {
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
} as const satisfies Record<
  OperationStateLabel,
  { job_state: JobState; operation_status: OperationStatus }
>;

export type CostKnowledge = 'estimated' | 'verified' | 'unknown';
export type RetryDisposition =
  | 'not_needed'
  | 'safe_to_retry'
  | 'reconcile_first'
  | 'blocked';

/** Integer-unit reservation; unknown values stay null, never zero. */
export interface OperationReservation {
  requests: number;
  tokens: number | null;
  moneyMinorUnits: number | null;
  currency: string | null;
  costKnowledge: CostKnowledge;
}

/** The canonical durable operation record for this producer. */
export interface ProducerOperationReceipt {
  operationId: string;
  sessionId: string;
  ownerId: string;
  runGeneration: number;
  operationKind: BudgetReservationKind;
  round: number | null;
  seatId: SeatId | null;
  purpose: string;
  inputHash: string;
  routeSnapshotHash: string;
  grantId: string;
  packHash: string | null;
  attemptId: string;
  /** Persisted; never reset by process restart. */
  attemptOrdinal: number;
  leaseOwner: string | null;
  /** Fencing token rechecked on every mutable commit. */
  leaseGeneration: number;
  leaseExpiresAt: string | null;
  providerRequestId: string | null;
  /** Canonical persisted job state, never a parallel enum. */
  state: JobState;
  stateLabel: OperationStateLabel;
  reservation: OperationReservation;
  observedUsage: Record<string, unknown> | null;
  acceptedResultHash: string | null;
  eventSequence: number | null;
  retryDisposition: RetryDisposition;
  /** Safe accounting projection validated against the canonical contract. */
  canonicalReceipt: CanonicalOperationReceipt;
}

export interface AdmissionCommand {
  sessionId: string;
  /** Caller idempotency key, scoped to this session and source. */
  idempotencyKey: string;
  operationKind: BudgetReservationKind;
  purpose: string;
  inputHash: string;
  routeSnapshotHash: string;
  grantId: string;
  packHash?: string | null;
  round?: number | null;
  seatId?: SeatId | null;
  ownerId?: string;
  reservation: OperationReservation;
  /**
   * Optional session transition committed atomically with the job.
   * expectedVersion is excluded from the idempotency fingerprint so an
   * exact retry may retain its original revision after the first
   * success advanced the session (plan Section "Admission, execution
   * and recovery algorithm", step 2).
   */
  transition?: { to: SessionState; expectedVersion: number };
}

export interface AdmissionResult {
  outcome: 'admitted' | 'replayed';
  receipt: ProducerOperationReceipt;
}

export interface OperationLeaseFence {
  operationId: string;
  leaseOwner: string;
  leaseGeneration: number;
}

export interface ReconcileQueuedWithoutJobResult {
  scanned: number;
  blocked: Array<{ sessionId: string; reason: 'queued_without_job' }>;
}

export interface DurableOperationProducerDeps {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  jobs: CouncilJobs;
  outbox?: ProjectionOutbox;
  clock: Clock;
  ids: IdSource;
  /** Outbox delivery attempt bound; defaults to the outbox's own 5. */
  outboxMaxAttempts?: number;
}

interface StoredJobRow {
  id: string;
  session_id: string | null;
  state: JobState;
  lease_epoch: number;
  lease_owner: string | null;
  lease_expires_at: string | null;
  payload_json: string;
  updated_at: string;
}

interface ProducerPayload {
  attempt: number;
  brief_revision: number;
  phase_job_key: string;
  seat_id: string | null;
  input_sha256: string;
  cancel_generation: number;
  producer?: {
    idempotency_key: string;
    fingerprint: string;
    attempt_id: string;
    attempt_ordinal: number;
    receipt: ProducerOperationReceipt;
  };
}

const OPERATION_KINDS: ReadonlySet<string> = new Set([
  'provider_request',
  'output_repair',
  'transport_retry',
  'semantic_verification',
]);
const COST_KNOWLEDGE: ReadonlySet<string> = new Set([
  'estimated',
  'verified',
  'unknown',
]);
const CURRENCY = /^[A-Z]{3}$/;

function nowPlus(clock: Clock, ms: number): string {
  return new Date(Date.parse(clock.nowUtc()) + ms).toISOString();
}

function validateCommand(command: AdmissionCommand): void {
  const fail = (message: string): never => {
    throw new JobRunnerError('OPERATION_ADMISSION_INVALID', message, { retryable: false });
  };
  if (!command.sessionId) fail('sessionId is required.');
  if (!command.idempotencyKey) fail('idempotencyKey is required.');
  if (!OPERATION_KINDS.has(command.operationKind)) {
    fail(`operationKind ${command.operationKind} is not a canonical operation kind.`);
  }
  if (!command.purpose) fail('purpose is required.');
  if (!isSha256Hex(command.inputHash)) {
    fail('inputHash must be a lowercase SHA-256 hex digest.');
  }
  if (!isSha256Hex(command.routeSnapshotHash)) {
    fail('routeSnapshotHash must be a lowercase SHA-256 hex digest.');
  }
  if (!command.grantId) fail('grantId is required.');
  if (command.packHash !== undefined && command.packHash !== null && !isSha256Hex(command.packHash)) {
    fail('packHash must be null or a lowercase SHA-256 hex digest.');
  }
  if (command.round !== undefined && command.round !== null) {
    if (!Number.isInteger(command.round) || command.round < 0) {
      fail('round must be null or a non-negative integer.');
    }
  }
  if (command.seatId !== undefined && command.seatId !== null) {
    if (!(SEAT_IDS as readonly string[]).includes(command.seatId)) {
      fail(`seatId ${command.seatId} is not one of the nine canonical seats.`);
    }
  }
  const r = command.reservation;
  if (!Number.isInteger(r.requests) || r.requests < 0) {
    fail('reservation.requests must be a non-negative integer.');
  }
  if (r.tokens !== null && (!Number.isInteger(r.tokens) || r.tokens < 0)) {
    fail('reservation.tokens must be null or a non-negative integer.');
  }
  if (r.moneyMinorUnits !== null) {
    if (!Number.isInteger(r.moneyMinorUnits) || r.moneyMinorUnits < 0) {
      fail('reservation.moneyMinorUnits must be null or a non-negative integer.');
    }
    if (r.currency === null || !CURRENCY.test(r.currency)) {
      fail('reservation.currency is required when moneyMinorUnits is set.');
    }
  }
  if (!COST_KNOWLEDGE.has(r.costKnowledge)) {
    fail(`costKnowledge ${r.costKnowledge} is not estimated|verified|unknown.`);
  }
  if (command.transition && !Number.isInteger(command.transition.expectedVersion)) {
    fail('transition.expectedVersion must be an integer.');
  }
}

function operationIdentity(
  sessionId: string,
  attempt: number,
  idempotencyKey: string,
  fingerprint: string,
): string {
  // Deliberately the SAME derivation as CouncilJobs.operationKey in
  // persistence/jobs.ts: one operation has one string across the job
  // row, budget reservations, the attempt ledger, and host stamps.
  return canonicalHash({
    session_id: sessionId,
    attempt,
    phase_job_key: idempotencyKey,
    input_sha256: fingerprint,
  });
}

function buildCanonicalReceipt(
  receipt: ProducerOperationReceipt,
  completedAt: string | null = null,
): CanonicalOperationReceipt {
  const usage = receipt.observedUsage ?? {};
  const inputTokens = typeof usage.input_tokens === 'number' ? usage.input_tokens : null;
  const outputTokens = typeof usage.output_tokens === 'number' ? usage.output_tokens : null;
  const money = receipt.reservation.moneyMinorUnits;
  const candidate: CanonicalOperationReceipt = {
    schema_version: 'wise-elders.operation-receipt/v1',
    operation_id: receipt.operationId,
    session_id: receipt.sessionId,
    status: OPERATION_STATE_LABEL_MAP[receipt.stateLabel].operation_status,
    provider_request_id: receipt.providerRequestId,
    input_sha256: receipt.inputHash,
    output_sha256: receipt.acceptedResultHash,
    usage: { input_tokens: inputTokens, output_tokens: outputTokens },
    cost:
      money !== null && receipt.reservation.currency !== null
        ? { amount_minor: money, currency: receipt.reservation.currency }
        : null,
    completed_at: receipt.stateLabel === 'accepted' ? completedAt : null,
  };
  const check = validateOperationReceipt(candidate);
  if (!check.ok) {
    throw new JobRunnerError(
      'OPERATION_ADMISSION_INVALID',
      'The operation receipt failed canonical contract validation.',
      { retryable: false, detail: { issues: check.issues } },
    );
  }
  return check.value;
}

function isFencedJobState(state: JobState): boolean {
  return state === 'leased' || state === 'running';
}

export class DurableOperationProducer {
  private readonly db: CouncilDatabase;
  private readonly repositories: CouncilRepositories;
  private readonly jobs: CouncilJobs;
  private readonly outbox: ProjectionOutbox;
  private readonly clock: Clock;
  private readonly ids: IdSource;

  constructor(deps: DurableOperationProducerDeps) {
    this.db = deps.db;
    this.repositories = deps.repositories;
    this.jobs = deps.jobs;
    this.outbox = deps.outbox ?? new ProjectionOutbox(deps.db, deps.outboxMaxAttempts ?? 5);
    this.clock = deps.clock;
    this.ids = deps.ids;
  }

  // ------------------------------------------------------------- admission

  /**
   * Admit one logical operation. One short owning-store transaction
   * commits: request-key claim, optional session transition, durable
   * job, `operation_reserved` event, and outbox intent.
   *
   * - Same idempotency key + same fingerprint: returns the committed
   *   receipt, performs no mutation.
   * - Same key + changed fingerprint: conflicts before any write.
   * - Concurrent loser: the request-key primary key serializes the
   *   race; the loser replays the committed matching receipt.
   * - A recorded admission whose job row is absent is rejected as
   *   QUEUED-without-job, never silently re-admitted.
   */
  admitOperation(
    envelope: AuthorizationEnvelope,
    command: AdmissionCommand,
  ): AdmissionResult {
    validateCommand(command);
    const fingerprint = canonicalHash({
      session_id: command.sessionId,
      idempotency_key: command.idempotencyKey,
      owner_id: command.ownerId ?? null,
      operation_kind: command.operationKind,
      purpose: command.purpose,
      round: command.round ?? null,
      seat_id: command.seatId ?? null,
      input_sha256: command.inputHash,
      route_snapshot_sha256: command.routeSnapshotHash,
      grant_id: command.grantId,
      pack_sha256: command.packHash ?? null,
      reservation: command.reservation,
      transition_to: command.transition?.to ?? null,
    });

    return this.db.write((handle) => {
      const session = this.requireSession(envelope, command.sessionId);
      const existing = this.readRequestKey(handle, envelope, command.sessionId, command.idempotencyKey);
      if (existing) {
        if (existing.payload_fingerprint !== fingerprint) {
          throw new JobRunnerError(
            'OPERATION_ADMISSION_CONFLICT',
            `Idempotency key ${command.idempotencyKey} is already committed with a different command fingerprint. Nothing was written.`,
            {
              retryable: false,
              detail: {
                session_id: command.sessionId,
                operation_id: existing.response_operation_id,
              },
            },
          );
        }
        const job =
          existing.response_operation_id === null
            ? null
            : this.readJobByOperationId(handle, envelope, existing.response_operation_id);
        if (!job || !this.parsePayload(job).producer) {
          throw new JobRunnerError(
            'OPERATION_QUEUED_WITHOUT_JOB',
            `Admission key ${command.idempotencyKey} is recorded but its durable job ${existing.response_operation_id ?? '(none)'} is absent. A QUEUED row without its job is not a valid admission.`,
            {
              retryable: false,
              detail: { session_id: command.sessionId },
            },
          );
        }
        return { outcome: 'replayed' as const, receipt: this.parsePayload(job).producer!.receipt };
      }

      if (command.transition) {
        if (session.state.state_version !== command.transition.expectedVersion) {
          throw new JobRunnerError(
            'OPERATION_ADMISSION_CONFLICT',
            `Expected session revision ${command.transition.expectedVersion}, current revision is ${session.state.state_version}. No admission was written.`,
            { retryable: false, detail: { session_id: command.sessionId } },
          );
        }
        this.repositories.transitionState(
          envelope,
          command.sessionId,
          command.transition.to,
          command.transition.expectedVersion,
        );
      }

      const refreshed = this.requireSession(envelope, command.sessionId);
      const operationId = operationIdentity(
        command.sessionId,
        refreshed.state.attempt,
        command.idempotencyKey,
        fingerprint,
      );
      const ownerId =
        command.ownerId ?? refreshed.scope.owner_subject ?? envelope.actor_subject;
      const attemptOrdinal = 1;
      const attemptId = canonicalHash({
        operation_id: operationId,
        attempt_ordinal: attemptOrdinal,
      });

      // Reuse CWE-006's job substrate. Same deterministic identity,
      // same payload fields, same session-usable checks.
      const job = this.jobs.claimJob(envelope, {
        sessionId: command.sessionId,
        attempt: refreshed.state.attempt,
        briefRevision: refreshed.state.brief_revision,
        phaseJobKey: command.idempotencyKey,
        inputSha256: fingerprint,
        cancelGeneration: refreshed.state.cancel_generation,
        seatId: command.seatId ?? null,
      });

      const receipt: ProducerOperationReceipt = {
        operationId,
        sessionId: command.sessionId,
        ownerId,
        runGeneration: refreshed.state.attempt,
        operationKind: command.operationKind,
        round: command.round ?? null,
        seatId: command.seatId ?? null,
        purpose: command.purpose,
        inputHash: command.inputHash,
        routeSnapshotHash: command.routeSnapshotHash,
        grantId: command.grantId,
        packHash: command.packHash ?? null,
        attemptId,
        attemptOrdinal,
        leaseOwner: null,
        leaseGeneration: job.lease_epoch,
        leaseExpiresAt: null,
        providerRequestId: null,
        state: job.state,
        stateLabel: 'never_dispatched',
        reservation: { ...command.reservation },
        observedUsage: null,
        acceptedResultHash: null,
        eventSequence: null,
        retryDisposition: 'not_needed',
        canonicalReceipt: {} as CanonicalOperationReceipt,
      };
      receipt.canonicalReceipt = buildCanonicalReceipt(receipt);

      const event = this.repositories.journal.append(handle, envelope, command.sessionId, {
        event_id: this.ids.newId(),
        type: 'operation_reserved',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          operation_id: operationId,
          operation_kind: command.operationKind,
          purpose: command.purpose,
          round: receipt.round,
          seat_id: receipt.seatId,
          input_sha256: receipt.inputHash,
          route_snapshot_sha256: receipt.routeSnapshotHash,
          grant_id: receipt.grantId,
          pack_sha256: receipt.packHash,
          job_id: job.id,
          attempt_id: attemptId,
          attempt_ordinal: attemptOrdinal,
          state_label: receipt.stateLabel,
        },
        created_at: this.clock.nowUtc(),
      });
      receipt.eventSequence = event.sequence;
      receipt.canonicalReceipt = buildCanonicalReceipt(receipt);

      this.writeProducerPayload(handle, envelope, job.id, {
        idempotency_key: command.idempotencyKey,
        fingerprint,
        attempt_id: attemptId,
        attempt_ordinal: attemptOrdinal,
        receipt,
      });
      this.insertRequestKey(
        handle,
        envelope,
        command.sessionId,
        command.idempotencyKey,
        fingerprint,
        operationId,
      );
      this.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: command.sessionId,
        event_sequence: event.sequence,
        topic: OPERATION_EVENT_TOPIC,
        idempotency_key: `${operationId}:reserved`,
        payload: {
          operation_id: operationId,
          session_id: command.sessionId,
          job_id: job.id,
          state: receipt.state,
          state_label: receipt.stateLabel,
          attempt_ordinal: attemptOrdinal,
        },
        created_at: this.clock.nowUtc(),
      });
      return { outcome: 'admitted' as const, receipt };
    });
  }

  // ------------------------------------------------------------- read/lease

  readReceipt(
    envelope: AuthorizationEnvelope,
    operationId: string,
  ): ProducerOperationReceipt {
    const job = this.db.read((handle) => this.readJobByOperationId(handle, envelope, operationId));
    if (!job) {
      const recorded = this.db.read((handle) =>
        handle
          .prepare(
            `SELECT request_key FROM council_request_keys
              WHERE tenant_id = ? AND source = ? AND response_operation_id = ?`,
          )
          .get(envelope.tenant_id, OPERATION_ADMISSION_SOURCE, operationId),
      ) as { request_key: string } | undefined;
      if (recorded) {
        throw new JobRunnerError(
          'OPERATION_QUEUED_WITHOUT_JOB',
          `Operation ${operationId} is recorded as admitted but its durable job is absent.`,
          { retryable: false, detail: { operation_id: operationId } },
        );
      }
      throw new JobRunnerError('OPERATION_NOT_FOUND', `No operation ${operationId} exists in this scope.`, {
        retryable: false,
      });
    }
    const producer = this.parsePayload(job).producer;
    if (!producer) {
      throw new JobRunnerError(
        'OPERATION_NOT_FOUND',
        `Job ${job.id} was not created by the durable producer; it has no producer receipt.`,
        { retryable: false },
      );
    }
    return producer.receipt;
  }

  /**
   * Claim a queued operation under a durable lease. The compare-and-swap
   * bumps lease_epoch (the fencing generation); a losing claimer gets a
   * typed fence error, never a second owner.
   */
  claimOperation(
    envelope: AuthorizationEnvelope,
    operationId: string,
    workerId: string,
    leaseTtlMs: number = DEFAULT_OPERATION_LEASE_TTL_MS,
  ): ProducerOperationReceipt {
    if (!Number.isInteger(leaseTtlMs) || leaseTtlMs < 1) {
      throw new JobRunnerError('OPERATION_ADMISSION_INVALID', 'leaseTtlMs must be a positive integer.', {
        retryable: false,
      });
    }
    return this.db.write((handle) => {
      const job = this.readJobByOperationId(handle, envelope, operationId);
      if (!job) {
        throw new JobRunnerError('OPERATION_NOT_FOUND', `No operation ${operationId} exists.`, {
          retryable: false,
        });
      }
      const payload = this.parsePayload(job);
      if (!payload.producer) {
        throw new JobRunnerError('OPERATION_NOT_FOUND', `Job ${job.id} has no producer receipt.`, {
          retryable: false,
        });
      }
      if (job.state !== 'queued') {
        throw new JobRunnerError(
          'OPERATION_LEASE_FENCED',
          `Operation ${operationId} is ${job.state}; only a queued operation can be claimed.`,
          { retryable: false, detail: { operation_id: operationId, state: job.state } },
        );
      }
      const now = this.clock.nowUtc();
      const expires = nowPlus(this.clock, leaseTtlMs);
      const result = handle
        .prepare(
          `UPDATE council_jobs
              SET state = 'leased', lease_owner = ?, lease_epoch = lease_epoch + 1,
                  lease_expires_at = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = 'operation'
              AND state = 'queued'`,
        )
        .run(workerId, expires, now, envelope.tenant_id, envelope.company_id, job.id);
      if (Number(result.changes) !== 1) {
        throw new JobRunnerError(
          'OPERATION_LEASE_FENCED',
          `Operation ${operationId} was claimed by another worker first.`,
          { retryable: true, detail: { operation_id: operationId } },
        );
      }
      const claimed = this.readJobByOperationId(handle, envelope, operationId)!;
      const receipt: ProducerOperationReceipt = {
        ...payload.producer.receipt,
        state: claimed.state,
        leaseOwner: workerId,
        leaseGeneration: claimed.lease_epoch,
        leaseExpiresAt: claimed.lease_expires_at,
      };
      receipt.canonicalReceipt = buildCanonicalReceipt(receipt);
      this.writeProducerPayload(handle, envelope, job.id, {
        ...payload.producer,
        receipt,
      });
      return receipt;
    });
  }

  /** Return a claimed operation to queued. Fence-checked. */
  releaseLease(envelope: AuthorizationEnvelope, fence: OperationLeaseFence): boolean {
    return this.db.write((handle) => {
      const { job } = this.fence(handle, envelope, fence);
      const result = handle
        .prepare(
          `UPDATE council_jobs
              SET state = 'queued', lease_owner = NULL, lease_expires_at = NULL, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?
              AND state IN ('leased', 'running') AND lease_owner = ? AND lease_epoch = ?`,
        )
        .run(
          this.clock.nowUtc(),
          envelope.tenant_id,
          envelope.company_id,
          job.id,
          fence.leaseOwner,
          fence.leaseGeneration,
        );
      if (Number(result.changes) !== 1) {
        throw new JobRunnerError('OPERATION_LEASE_FENCED', 'The lease could not be released; it moved.', {
          retryable: false,
        });
      }
      const fresh = this.readJobById(handle, envelope, job.id)!;
      const payload = this.parsePayload(fresh);
      const receipt: ProducerOperationReceipt = {
        ...payload.producer!.receipt,
        state: fresh.state,
        leaseOwner: null,
        leaseExpiresAt: null,
      };
      receipt.canonicalReceipt = buildCanonicalReceipt(receipt);
      this.writeProducerPayload(handle, envelope, job.id, { ...payload.producer!, receipt });
      return true;
    });
  }

  // ------------------------------------------------------ fenced mutations

  /**
   * Persist the dispatch intent before any network call. The persisted
   * label becomes `potentially_dispatched`: the intent exists, but the
   * send outcome is not proved, so retry is `reconcile_first`.
   */
  recordDispatchIntent(
    envelope: AuthorizationEnvelope,
    fence: OperationLeaseFence,
    input: { providerRequestId?: string | null } = {},
  ): ProducerOperationReceipt {
    return this.db.write((handle) => {
      const { job, payload } = this.fence(handle, envelope, fence);
      const receipt: ProducerOperationReceipt = {
        ...payload.producer!.receipt,
        state: 'running',
        stateLabel: 'potentially_dispatched',
        providerRequestId: input.providerRequestId ?? payload.producer!.receipt.providerRequestId,
        retryDisposition: 'reconcile_first',
      };
      receipt.canonicalReceipt = buildCanonicalReceipt(receipt);
      const result = handle
        .prepare(
          `UPDATE council_jobs SET state = 'running', updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?
              AND state IN ('leased', 'running') AND lease_owner = ? AND lease_epoch = ?`,
        )
        .run(
          this.clock.nowUtc(),
          envelope.tenant_id,
          envelope.company_id,
          job.id,
          fence.leaseOwner,
          fence.leaseGeneration,
        );
      if (Number(result.changes) !== 1) {
        throw new JobRunnerError('OPERATION_LEASE_FENCED', 'Dispatch intent could not be recorded; lease moved.', {
          retryable: false,
        });
      }
      this.writeProducerPayload(handle, envelope, job.id, {
        ...payload.producer!,
        receipt,
      });
      return receipt;
    });
  }

  /** Record that a provider response was observed but not yet accepted. */
  recordResponseObserved(
    envelope: AuthorizationEnvelope,
    fence: OperationLeaseFence,
    input: {
      providerRequestId: string | null;
      observedUsage?: Record<string, unknown> | null;
    },
  ): ProducerOperationReceipt {
    return this.db.write((handle) => {
      const { job, payload } = this.fence(handle, envelope, fence);
      const previous = payload.producer!.receipt;
      if (
        previous.stateLabel !== 'potentially_dispatched' &&
        previous.stateLabel !== 'response_observed'
      ) {
        throw new JobRunnerError(
          'OPERATION_ADMISSION_CONFLICT',
          `Cannot record a response for an operation in label ${previous.stateLabel}.`,
          { retryable: false },
        );
      }
      const receipt: ProducerOperationReceipt = {
        ...previous,
        state: 'running',
        stateLabel: 'response_observed',
        providerRequestId: input.providerRequestId,
        observedUsage: input.observedUsage ?? previous.observedUsage,
        retryDisposition: 'not_needed',
      };
      receipt.canonicalReceipt = buildCanonicalReceipt(receipt);
      const result = handle
        .prepare(
          `UPDATE council_jobs SET state = 'running', updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?
              AND state IN ('leased', 'running') AND lease_owner = ? AND lease_epoch = ?`,
        )
        .run(
          this.clock.nowUtc(),
          envelope.tenant_id,
          envelope.company_id,
          job.id,
          fence.leaseOwner,
          fence.leaseGeneration,
        );
      if (Number(result.changes) !== 1) {
        throw new JobRunnerError('OPERATION_LEASE_FENCED', 'Response could not be recorded; lease moved.', {
          retryable: false,
        });
      }
      this.writeProducerPayload(handle, envelope, job.id, {
        ...payload.producer!,
        receipt,
      });
      return receipt;
    });
  }

  /**
   * Accept a validated result. Finishes the durable job through the
   * existing `CouncilJobs.finishJob` CAS, appends the canonical
   * `operation_completed` event, and enqueues the outbox intent in the
   * same transaction.
   */
  recordAcceptedResult(
    envelope: AuthorizationEnvelope,
    fence: OperationLeaseFence,
    input: {
      acceptedResultHash: string;
      providerRequestId?: string | null;
      observedUsage?: Record<string, unknown> | null;
    },
  ): ProducerOperationReceipt {
    if (!isSha256Hex(input.acceptedResultHash)) {
      throw new JobRunnerError(
        'OPERATION_ADMISSION_INVALID',
        'acceptedResultHash must be a lowercase SHA-256 hex digest.',
        { retryable: false },
      );
    }
    return this.db.write((handle) => {
      const { job, payload } = this.fence(handle, envelope, fence);
      const previous = payload.producer!.receipt;
      if (
        previous.stateLabel !== 'potentially_dispatched' &&
        previous.stateLabel !== 'response_observed'
      ) {
        throw new JobRunnerError(
          'OPERATION_ADMISSION_CONFLICT',
          `Cannot accept a result for an operation in label ${previous.stateLabel}.`,
          { retryable: false },
        );
      }
      const finished = this.jobs.finishJob(envelope, job.id, fence.leaseGeneration, {
        status: 'succeeded',
        resultRef: input.acceptedResultHash,
      });
      if (!finished) {
        throw new JobRunnerError(
          'OPERATION_LEASE_FENCED',
          `Operation ${fence.operationId} could not finish; its lease generation is stale.`,
          { retryable: false },
        );
      }
      const event = this.repositories.journal.append(handle, envelope, previous.sessionId, {
        event_id: this.ids.newId(),
        type: 'operation_completed',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          operation_id: previous.operationId,
          provider_request_id: input.providerRequestId ?? previous.providerRequestId,
          accepted_result_sha256: input.acceptedResultHash,
          state_label: 'accepted',
        },
        created_at: this.clock.nowUtc(),
      });
      const receipt: ProducerOperationReceipt = {
        ...previous,
        state: 'succeeded',
        stateLabel: 'accepted',
        providerRequestId: input.providerRequestId ?? previous.providerRequestId,
        observedUsage: input.observedUsage ?? previous.observedUsage,
        acceptedResultHash: input.acceptedResultHash,
        eventSequence: event.sequence,
        retryDisposition: 'not_needed',
      };
      const completedAt = this.clock.nowUtc();
      receipt.canonicalReceipt = buildCanonicalReceipt(receipt, completedAt);
      this.writeProducerPayload(handle, envelope, job.id, {
        ...payload.producer!,
        receipt,
      });
      this.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: previous.sessionId,
        event_sequence: event.sequence,
        topic: OPERATION_EVENT_TOPIC,
        idempotency_key: `${previous.operationId}:accepted`,
        payload: {
          operation_id: previous.operationId,
          session_id: previous.sessionId,
          state: receipt.state,
          state_label: receipt.stateLabel,
          accepted_result_sha256: input.acceptedResultHash,
          attempt_ordinal: previous.attemptOrdinal,
        },
        created_at: completedAt,
      });
      return receipt;
    });
  }

  // ------------------------------------------------------- reconciliation

  /**
   * Reject a QUEUED session that has no durable operation job. This is
   * the explicit "QUEUED without its job is not a valid admission"
   * check; it never writes.
   */
  assertQueuedHasJob(envelope: AuthorizationEnvelope, sessionId: string): void {
    const session = this.db.read((handle) => this.sessionRow(handle, envelope, sessionId));
    if (!session || session.state !== 'QUEUED') return;
    const jobs = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT id FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND kind = 'operation'
            LIMIT 1`,
        )
        .get(envelope.tenant_id, envelope.company_id, sessionId),
    ) as { id: string } | undefined;
    if (!jobs) {
      throw new JobRunnerError(
        'OPERATION_QUEUED_WITHOUT_JOB',
        `Session ${sessionId} is QUEUED but has no durable operation job. This is not a valid admission.`,
        { retryable: false, detail: { session_id: sessionId } },
      );
    }
  }

  /**
   * Deterministic historical repair through the owning service: every
   * session in QUEUED with no operation job is moved to BLOCKED with a
   * `queued_without_job` reason, in stable session-id order. Idempotent:
   * a second pass finds nothing still QUEUED and orphans nothing. It
   * never invents a job, a grant, or an input hash.
   */
  reconcileQueuedWithoutJob(
    envelope: AuthorizationEnvelope,
    actor: 'owner' | 'system' | 'worker' | 'chair' = 'system',
  ): ReconcileQueuedWithoutJobResult {
    const sessions = this.repositories
      .listSessions(envelope, {})
      .filter((session) => session.state.state === 'QUEUED')
      .sort((a, b) => a.spec.session_id.localeCompare(b.spec.session_id));
    const blocked: ReconcileQueuedWithoutJobResult['blocked'] = [];
    for (const session of sessions) {
      const hasJob = this.db.read((handle) => {
        const row = handle
          .prepare(
            `SELECT id FROM council_jobs
              WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND kind = 'operation'
              LIMIT 1`,
          )
          .get(envelope.tenant_id, envelope.company_id, session.spec.session_id);
        return row !== undefined;
      });
      if (hasJob) continue;
      const current = this.repositories.getSession(envelope, session.spec.session_id);
      if (!current || current.state.state !== 'QUEUED') continue;
      const { stateVersion } = assertTransition({
        mode: current.state.mode,
        from: current.state.state,
        to: 'BLOCKED',
        expectedVersion: current.state.state_version,
        currentVersion: current.state.state_version,
        actor,
      });
      const next: SessionStateRecord = {
        ...current.state,
        state: 'BLOCKED',
        state_version: stateVersion,
        updated_at: this.clock.nowUtc(),
      };
      this.repositories.writeStateRecord(envelope, next, current.state.state_version, {
        type: 'session_blocked' as CouncilEventType,
        payload: {
          from_state: current.state.state,
          to_state: 'BLOCKED',
          reconciliation: 'queued_without_job',
        },
      });
      blocked.push({ sessionId: session.spec.session_id, reason: 'queued_without_job' });
    }
    return { scanned: sessions.length, blocked };
  }

  // ------------------------------------------------------------- internals

  private requireSession(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): StoredSession {
    const session = this.repositories.getSession(envelope, sessionId);
    if (!session) {
      throw new JobRunnerError(
        'JOB_SESSION_NOT_FOUND',
        `No council session ${sessionId} exists in this scope (or it is not visible to this envelope).`,
        { retryable: false, detail: { session_id: sessionId } },
      );
    }
    return session;
  }

  private sessionRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): { state: SessionState } | undefined {
    return handle
      .prepare(
        `SELECT state FROM council_sessions
          WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as
      | { state: SessionState }
      | undefined;
  }

  private readJobById(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    jobId: string,
  ): StoredJobRow | undefined {
    return handle
      .prepare(
        `SELECT id, session_id, state, lease_epoch, lease_owner, lease_expires_at,
                payload_json, updated_at
           FROM council_jobs
          WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = 'operation'`,
      )
      .get(envelope.tenant_id, envelope.company_id, jobId) as StoredJobRow | undefined;
  }

  private readJobByOperationId(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    operationId: string,
  ): StoredJobRow | undefined {
    return handle
      .prepare(
        `SELECT id, session_id, state, lease_epoch, lease_owner, lease_expires_at,
                payload_json, updated_at
           FROM council_jobs
          WHERE tenant_id = ? AND company_id = ? AND kind = 'operation'
            AND idempotency_key = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, operationId) as
      | StoredJobRow
      | undefined;
  }

  private readRequestKey(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
    requestKey: string,
  ): { payload_fingerprint: string; response_operation_id: string | null } | undefined {
    return handle
      .prepare(
        `SELECT payload_fingerprint, response_operation_id
           FROM council_request_keys
          WHERE tenant_id = ? AND source = ? AND operation = ? AND request_key = ?`,
      )
      .get(envelope.tenant_id, OPERATION_ADMISSION_SOURCE, sessionId, requestKey) as
      | { payload_fingerprint: string; response_operation_id: string | null }
      | undefined;
  }

  private insertRequestKey(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
    requestKey: string,
    fingerprint: string,
    operationId: string,
  ): void {
    handle
      .prepare(
        `INSERT INTO council_request_keys
           (tenant_id, source, operation, request_key, payload_fingerprint, session_id,
            response_operation_id, response_status, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        envelope.tenant_id,
        OPERATION_ADMISSION_SOURCE,
        sessionId,
        requestKey,
        fingerprint,
        sessionId,
        operationId,
        202,
        this.clock.nowUtc(),
      );
  }

  private parsePayload(job: StoredJobRow): ProducerPayload {
    return JSON.parse(job.payload_json) as ProducerPayload;
  }

  private writeProducerPayload(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    jobId: string,
    producer: NonNullable<ProducerPayload['producer']>,
  ): void {
    const row = this.readJobById(handle, envelope, jobId);
    if (!row) {
      throw new JobRunnerError('OPERATION_NOT_FOUND', `Job ${jobId} vanished during a producer write.`, {
        retryable: false,
      });
    }
    const payload = this.parsePayload(row);
    payload.producer = producer;
    handle
      .prepare(
        `UPDATE council_jobs SET payload_json = ?, updated_at = ?
          WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .run(
        canonicalStringify(payload),
        this.clock.nowUtc(),
        envelope.tenant_id,
        envelope.company_id,
        jobId,
      );
  }

  /**
   * Re-read the job and session inside the mutable transaction and
   * recheck the fencing generation: owner, lease epoch, live expiry,
   * and the session cancellation generation captured at admission.
   * This is the one fence every mutable commit calls.
   */
  private fence(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    fence: OperationLeaseFence,
  ): { job: StoredJobRow; payload: ProducerPayload } {
    const job = this.readJobByOperationId(handle, envelope, fence.operationId);
    if (!job) {
      throw new JobRunnerError('OPERATION_NOT_FOUND', `No operation ${fence.operationId} exists.`, {
        retryable: false,
      });
    }
    const payload = this.parsePayload(job);
    const stored = payload.producer?.receipt;
    if (!stored) {
      throw new JobRunnerError('OPERATION_NOT_FOUND', `Job ${job.id} has no producer receipt.`, {
        retryable: false,
      });
    }
    const expired =
      job.lease_expires_at !== null &&
      Date.parse(job.lease_expires_at) <= Date.parse(this.clock.nowUtc());
    if (
      !isFencedJobState(job.state) ||
      job.lease_owner !== fence.leaseOwner ||
      job.lease_epoch !== fence.leaseGeneration ||
      expired
    ) {
      throw new JobRunnerError(
        'OPERATION_LEASE_FENCED',
        `Operation ${fence.operationId} is not owned by ${fence.leaseOwner} at lease generation ${fence.leaseGeneration} (row: owner ${job.lease_owner ?? 'none'}, generation ${job.lease_epoch}, state ${job.state}${expired ? ', expired' : ''}). The commit was refused.`,
        {
          retryable: false,
          detail: {
            operation_id: fence.operationId,
            lease_owner: fence.leaseOwner,
            lease_generation: fence.leaseGeneration,
          },
        },
      );
    }
    const session = this.requireSession(envelope, stored.sessionId);
    if (
      session.state.cancel_generation !== payload.cancel_generation ||
      session.state.state === 'CANCELLED' ||
      session.state.state === 'CANCEL_REQUESTED'
    ) {
      throw new JobRunnerError(
        'OPERATION_LEASE_FENCED',
        `Session ${stored.sessionId} moved to cancellation generation ${session.state.cancel_generation}; this operation's result is fenced out.`,
        { retryable: false, detail: { operation_id: fence.operationId } },
      );
    }
    return { job, payload };
  }
}
