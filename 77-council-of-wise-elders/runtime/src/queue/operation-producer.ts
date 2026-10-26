/**
 * Receipted operation producer for the Council runtime (WER-011
 * dependency-ready slice, unit W01-U003).
 *
 * TWO producers cover this slice, and they own different things. Both
 * are exported from src/queue/index.ts:
 *
 * - `DurableOperationProducer` (src/queue/producer.ts) owns the
 *   REQUEST-KEYED admission path: council_request_keys as the
 *   idempotency registry, plus the leased lifecycle
 *   (claim / release / dispatch intent / response observed / accepted
 *   result) behind a lease fence, projected onto the canonical
 *   OperationReceipt contract. Use it when the caller supplies its own
 *   idempotency key and drives the full worker lifecycle.
 * - `OperationProducer` (this module) owns the
 *   OperationAdmissionReceipt: the receipt committed INSIDE the job
 *   payload at admission, its admission-fingerprint conflict law, its
 *   non-resetting attempt_ordinal and lease_generation, the
 *   explicit-null mutable commit path with receipt-level fencing, and
 *   reconciliation of a QUEUED session that has no durable job. Use it
 *   when the caller addresses an operation by the deterministic
 *   operation identity (session, attempt, phase_job_key, input_sha256)
 *   and needs the receipt itself to be the durable business record.
 *
 * Neither producer replaces the other; there is no "only" or "primary"
 * producer here.
 *
 * What this adds over DurableJobRunner.enqueueOperation alone:
 * enqueueOperation commits the job row and its dispatch descriptor, but
 * records no receipt, no journal event, and no outbox intent, and the
 * session transition that queues the work happens in a separate call.
 * This producer makes ADMISSION the single owning-store transaction:
 * the session transition to QUEUED, the durable job row, the
 * OperationAdmissionReceipt, the operation_reserved journal event, and the
 * outbox intent all commit in ONE short transaction (Section 16.4), or
 * none of them do. A crash between the writes cannot leave a session
 * QUEUED without its job, a job without its receipt, or a receipt
 * without its event.
 *
 * Composition law (no second state machine, no second scheduler):
 * - The job row itself is still CWE-006's council_jobs through
 *   CouncilJobs.claimJob (called on the SAME handle inside the
 *   producer's transaction via withHandle), so job identity,
 *   idempotency-key derivation, and CAS discipline stay in one place.
 * - Dispatch stays CWE-027's runner; this module only produces. It
 *   never claims, executes, heartbeats, or dispatches. Worker
 *   acknowledgment, real provider dispatch, and live replay are
 *   DEFERRED to the runner units; nothing here claims them.
 * - Budget reservation stays at claim time (CWE-049 admission); the
 *   receipt records the grant and estimate the dispatch will charge
 *   against, never a reservation id (which does not exist yet).
 *
 * OperationAdmissionReceipt semantics (v2.4):
 * - operation_id is the stable business key: the same
 *   canonicalHash({session_id, attempt, phase_job_key, input_sha256})
 *   identity the job row, budget reservation, attempt ledger, and card
 *   host stamp already use. It is never reset by restart.
 * - The admission fingerprint (canonicalStringify of descriptor +
 *   route snapshot fingerprint) is committed with the receipt; the
 *   same idempotency key with a DIFFERENT fingerprint is a conflict
 *   refused before any write.
 * - attempt_ordinal is the receipt's own per-operation dispatch
 *   ordinal: 1 at admission and never reset by restart; retries and
 *   repairs are separate operations with their own receipts.
 * - lease_generation is the fencing token the receipt was admitted
 *   under. Every later mutable commit against this receipt rechecks it
 *   (commitMutable checks job lease_epoch AND session lease_epoch),
 *   so a stale generation cannot commit over a newer claim.
 *
 * State labels: every persisted `state` is an EXISTING canonical enum.
 * RECEIPT_STATE_TO_JOB_STATE maps the semantic label onto CWE-006
 * JobState; dispatch sublabels map onto contracts OPERATION_STATUSES.
 * No parallel state machine. The receipt ALSO persists the semantic
 * label itself (`state_label`), because two labels share one JobState
 * ('potentially_dispatched' and 'response_observed' both map to
 * 'leased') and would otherwise be indistinguishable once written.
 */

import {
  canonicalHash,
  canonicalStringify,
  type Clock,
  type CouncilEventType,
  type IdSource,
  type SeatId,
  type SessionStateRecord,
} from '../contracts/index.js';
import type { PinnedRouteSnapshot } from '../budgets/index.js';
import { routeSnapshotFingerprint } from '../budgets/route-snapshot.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { assertEnvelopePurpose } from '../persistence/envelope.js';
import { CouncilJobs, type JobRecord } from '../persistence/jobs.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from '../persistence/sqlite.js';
import type { OperationDescriptor } from './runner.js';
import { JobRunnerError } from './errors.js';

// ------------------------------------------------------------ state labels

/**
 * Receipt lifecycle labels, each mapped onto the canonical enums the
 * repo already persists (recorded explicitly per WER-011):
 *
 * - never_dispatched: the operation was admitted durably; no worker
 *   has claimed the job yet. Maps onto JobState 'queued'.
 * - potentially_dispatched: a worker claimed the job (lease_epoch was
 *   bumped) but no provider response was observed. Covers JobState
 *   'leased' and 'running'.
 * - response_observed: a provider response was recorded by the
 *   attempt ledger but acceptance is not final. Maps onto
 *   OPERATION_STATUSES 'reserved'/'dispatched' rows on
 *   council_provider_attempts (JobState still leased/running).
 * - accepted: the job finished succeeded and the attempt ledger shows
 *   'accepted'. Maps onto JobState 'succeeded' + OPERATION_STATUSES
 *   'accepted'.
 * - known_failed: the job finished failed or dead_letter. Maps onto
 *   JobState 'failed'/'dead_letter' + OPERATION_STATUSES 'failed'.
 * - cancelled_fenced: the job was cancelled or fenced out (superseded
 *   cancel generation, session cancellation). Maps onto JobState
 *   'cancelled' + OPERATION_STATUSES 'cancelled'.
 * - outcome_unknown: provider completion is unknown. Maps onto
 *   OPERATION_STATUSES 'provider_completion_unknown' (JobState failed
 *   with that terminal reason per the runner's recovery law).
 */
export type ReceiptStateLabel =
  | 'never_dispatched'
  | 'potentially_dispatched'
  | 'response_observed'
  | 'accepted'
  | 'known_failed'
  | 'cancelled_fenced'
  | 'outcome_unknown';

export const RECEIPT_STATE_TO_JOB_STATE: Record<ReceiptStateLabel, string> = {
  never_dispatched: 'queued',
  // Both of these map onto 'leased': JobState is canonical and has no
  // sub-state for "claimed" versus "response observed". The receipt's
  // `state_label` field carries the distinction; this map only says
  // which JobState the label is allowed to sit on.
  potentially_dispatched: 'leased',
  response_observed: 'leased',
  accepted: 'succeeded',
  known_failed: 'failed',
  cancelled_fenced: 'cancelled',
  outcome_unknown: 'failed',
};

// ---------------------------------------------------------------- receipt

/** How the charge on the grant is known at receipt time. */
export type CostKnowledge = 'estimated' | 'verified' | 'unknown';

/**
 * What a caller should do with a receipt after a fault, per the v2.4
 * disposition law.
 */
export type RetryDisposition =
  | 'not_needed'
  | 'safe_to_retry'
  | 'reconcile_first'
  | 'blocked';

/**
 * The canonical admission receipt persisted in the job row's payload
 * (receipt_json). operation_id is the stable business key; every field
 * survives restart because it lives in the same committed payload as
 * the job itself.
 */
export interface OperationAdmissionReceipt {
  schema_version: 'wise-elders.operation-receipt/v1';
  /** Stable business key; equals the job's idempotency key. */
  operation_id: string;
  operation_id_hash: string;
  session_id: string;
  owner_subject: string;
  /** The session run generation (state lease_epoch) at admission. */
  run_generation: number;
  operation_kind: string;
  round: number;
  seat_id: string | null;
  purpose: string;
  input_hash: string;
  route_snapshot_hash: string;
  grant_id: string;
  pack_hash: string;
  /** The dispatch id when this operation is itself a follow-on. */
  attempt_id: string;
  /** Per-operation dispatch ordinal; 1 at admission, never reset. */
  attempt_ordinal: number;
  /** True when a later admission under the same key replayed. */
  replayed: boolean;
  lease_owner: string | null;
  /** Fencing token at admission; rechecked on every mutable commit. */
  lease_generation: number;
  lease_expires_at: string | null;
  provider_request_id: string | null;
  /** Maps onto JobState (see RECEIPT_STATE_TO_JOB_STATE). */
  state: string;
  /**
   * The semantic dispatch label this receipt was last committed at.
   * Distinct from `state` on purpose: 'potentially_dispatched' and
   * 'response_observed' both map to JobState 'leased', so this field is
   * the only place the two stay distinguishable after the write.
   * Absent on receipts admitted before the field existed; every reader
   * derives the label from the durable rows in that case.
   */
  state_label?: ReceiptStateLabel;
  /** Integer-unit reservation estimate; charged at dispatch. */
  reserved_units: number;
  cost_knowledge: CostKnowledge;
  observed_usage: { input_units: number | null; output_units: number | null } | null;
  accepted_result_hash: string | null;
  event_sequence: number;
  retry_disposition: RetryDisposition;
  admission_fingerprint: string;
  created_at: string;
  updated_at: string;
}

export interface AdmitOperationRequest {
  session_id: string;
  phase_job_key: string;
  seat_id: SeatId | null;
  input_sha256: string;
  descriptor: OperationDescriptor;
  route_snapshot: PinnedRouteSnapshot;
  /** Pack identity hash (source_pack_version by default). */
  pack_hash?: string | null;
}

export type AdmitOperationResult =
  | { outcome: 'committed'; receipt: OperationAdmissionReceipt; created: true }
  | { outcome: 'committed'; receipt: OperationAdmissionReceipt; created: false };

// -------------------------------------------------------------- internals

const RECEIPT_STATE_EVENT_TYPES: ReadonlySet<CouncilEventType> = new Set([
  'session_created',
  'session_state_changed',
  'session_paused',
  'session_cancelled',
  'session_blocked',
  'session_failed',
] as const satisfies readonly CouncilEventType[]);

interface ReceiptedJobPayload {
  receipt: OperationAdmissionReceipt;
  [key: string]: unknown;
}

class ProducerStateConflict extends Error {
  readonly code = 'PRODUCER_STATE_CONFLICT' as const;
  constructor(message: string, readonly detail: Record<string, unknown>) {
    super(message);
    this.name = 'ProducerStateConflict';
  }
}

function operationKey(
  sessionId: string,
  attempt: number,
  phaseJobKey: string,
  inputSha256: string,
): string {
  // Identical derivation to CWE-006 CouncilJobs and CWE-027's runner:
  // the admission operation id IS the job's idempotency key.
  return canonicalHash({
    session_id: sessionId,
    attempt,
    phase_job_key: phaseJobKey,
    input_sha256: inputSha256,
  });
}

/**
 * Run fn inside the owning store's transaction discipline. The
 * producer's writes are one commit unit, so nested participation is
 * correct: db.write opens BEGIN IMMEDIATE only at the outermost call.
 */
function withHandle<T>(
  db: CouncilDatabase,
  fn: (handle: SqliteDatabaseHandle) => T,
): T {
  return db.write(fn);
}

/**
 * Derive the semantic label from the durable rows alone. Exact for the
 * terminal job states and for an unclaimed 'queued' row; a claimed row
 * cannot be split into 'potentially_dispatched' versus
 * 'response_observed' from council_jobs plus the attempt ledger unless
 * an attempt row exists, which is why stateLabel() prefers the
 * persisted receipt label for those two.
 */
function labelFromJobRow(
  jobState: string,
  attemptStatus: string | null,
): ReceiptStateLabel | null {
  switch (jobState) {
    case 'queued':
      return 'never_dispatched';
    case 'leased':
    case 'running':
      if (attemptStatus === 'reserved') return 'response_observed';
      if (attemptStatus === 'dispatched') return 'response_observed';
      return 'potentially_dispatched';
    case 'succeeded':
      return 'accepted';
    case 'dead_letter':
      return 'known_failed';
    case 'failed':
      return attemptStatus === 'provider_completion_unknown'
        ? 'outcome_unknown'
        : 'known_failed';
    case 'cancelled':
      return 'cancelled_fenced';
    default:
      return null;
  }
}

// --------------------------------------------------------------- producer

export interface OperationProducerDeps {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  jobs: CouncilJobs;
  clock: Clock;
  ids: IdSource;
}

export class OperationProducer {
  private readonly db: CouncilDatabase;
  private readonly repositories: CouncilRepositories;
  private readonly jobs: CouncilJobs;
  private readonly clock: Clock;
  private readonly ids: IdSource;

  constructor(deps: OperationProducerDeps) {
    this.db = deps.db;
    this.repositories = deps.repositories;
    this.jobs = deps.jobs;
    this.clock = deps.clock;
    this.ids = deps.ids;
  }

  private nowIso(): string {
    return this.clock.nowUtc();
  }

  private operationId(request: AdmitOperationRequest, attempt: number): string {
    return operationKey(request.session_id, attempt, request.phase_job_key, request.input_sha256);
  }

  /**
   * Fingerprint the admission: everything that must be identical for
   * the same idempotency key. A changed fingerprint under the same key
   * is a conflict refused before any write.
   */
  private admissionFingerprint(
    request: AdmitOperationRequest,
  ): string {
    return canonicalHash({
      descriptor: request.descriptor,
      route_snapshot_hash: routeSnapshotFingerprint(request.route_snapshot),
      seat_id: request.seat_id,
      pack_hash: request.pack_hash ?? null,
    });
  }

  private sessionStateRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): {
    state: string;
    state_version: number;
    cancellation_generation: number;
    lease_owner: string | null;
    owner_subject: string | null;
  } {
    // lease_epoch and attempt live in the journaled SessionStateRecord
    // (the durable record Section 18 defines), not in the sessions row
    // columns (CWE-006 mapping note); read them from
    // sessionRecordFromJournal, never from the row.
    const row = handle
      .prepare(
        `SELECT state, state_version, cancellation_generation, lease_owner,
                owner_subject
           FROM council_sessions
          WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as
      | {
          state: string;
          state_version: number;
          cancellation_generation: number;
          lease_owner: string | null;
          owner_subject: string | null;
        }
      | undefined;
    if (!row) {
      throw new JobRunnerError(
        'JOB_SESSION_NOT_FOUND',
        `No council session ${sessionId} exists in this scope; admission is refused.`,
        { detail: { session_id: sessionId } },
      );
    }
    return row;
  }

  private sessionRecordFromJournal(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): SessionStateRecord | null {
    // The journal carries the full SessionStateRecord on every state
    // event payload (CWE-006 mapping note); the latest one is the
    // authoritative in-transaction record.
    const row = handle
      .prepare(
        `SELECT payload_json FROM council_events
          WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            AND type IN ('session_created','session_state_changed','session_paused',
                         'session_cancelled','session_blocked','session_failed')
          ORDER BY sequence DESC LIMIT 1`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as
      | { payload_json: string }
      | undefined;
    if (!row) return null;
    const payload = JSON.parse(row.payload_json) as {
      state_record?: SessionStateRecord;
    };
    return payload.state_record ?? null;
  }

  /**
   * The receipt for an existing job payload, when one was committed.
   */
  private receiptFromPayload(payloadJson: string): OperationAdmissionReceipt | null {
    const payload = JSON.parse(payloadJson) as Partial<ReceiptedJobPayload>;
    if (!payload.receipt) return null;
    const receipt = payload.receipt;
    if (receipt.schema_version !== 'wise-elders.operation-receipt/v1') {
      return null;
    }
    return receipt;
  }

  private receiptedPayloadMutation(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    operationId: string,
    mutate: (payload: ReceiptedJobPayload) => boolean,
  ): boolean {
    // operationId is the job's idempotency key (the row's id column is
    // a separate generated id, CWE-006 claimJob law).
    const row = handle
      .prepare(
        `SELECT payload_json FROM council_jobs
          WHERE tenant_id = ? AND company_id = ? AND kind = 'operation' AND idempotency_key = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, operationId) as
      | { payload_json: string }
      | undefined;
    if (!row) {
      throw new JobRunnerError(
        'JOB_NOT_FOUND',
        `Job for operation ${operationId} vanished inside the transaction.`,
        { detail: { operation_id: operationId } },
      );
    }
    const payload = JSON.parse(row.payload_json) as ReceiptedJobPayload;
    if (!mutate(payload)) return true; // nothing to change
    const result = handle
      .prepare(
        `UPDATE council_jobs SET payload_json = ?, updated_at = ?
          WHERE tenant_id = ? AND company_id = ? AND kind = 'operation' AND idempotency_key = ?`,
      )
      .run(
        canonicalStringify(payload),
        this.nowIso(),
        envelope.tenant_id,
        envelope.company_id,
        operationId,
      );
    return Number(result.changes) === 1;
  }

  /**
   * Admit one operation durably: session transition to QUEUED (when
   * the session is READY), the job row, the receipt, the
   * operation_reserved journal event, and the outbox intent, all in
   * ONE owning-store transaction.
   *
   * Idempotency: the key is the operation identity. A replay under
   * the same key with the SAME fingerprint returns the originally
   * committed receipt (created: false) and writes nothing. A replay
   * with a DIFFERENT fingerprint throws PRODUCER_FINGERPRINT_CONFLICT
   * before any write. A losing concurrent duplicate (the transaction
   * races another admission of the same identity) returns the winner's
   * committed receipt.
   *
   * Invalid admission: a session record whose queueing transition or
   * job identity would be inconsistent is refused before any write;
   * in particular a QUEUED session state without its job row is never
   * produced by this path, and reconciliation of historical
   * queued-without-job rows is reconcileQueuedWithoutJob below.
   */
  admitOperation(
    envelope: AuthorizationEnvelope,
    request: AdmitOperationRequest,
  ): AdmitOperationResult {
    return this.admitWithPolicy(envelope, request, 'reject');
  }

  /**
   * The admission body. `queuedWithoutJob` selects the law for a QUEUED
   * session that has no operation job: 'reject' is normal admission and
   * refuses that historical break, because the session is not a
   * re-admission target; 'readmit' is used only by
   * reconcileQueuedWithoutJob, which has already proved the absence
   * inside its own transaction and exists to close it. An outer
   * transaction is joined, never nested (sqlite.ts tx law), so the
   * readmit path commits as one unit.
   */
  private admitWithPolicy(
    envelope: AuthorizationEnvelope,
    request: AdmitOperationRequest,
    queuedWithoutJob: 'reject' | 'readmit',
  ): AdmitOperationResult {
    assertEnvelopePurpose(envelope, 'write', 'Operation admission');
    const fingerprint = this.admissionFingerprint(request);
    const now = this.nowIso();

    const outcome = withHandle(this.db, (handle) => {
      const session = this.sessionStateRow(handle, envelope, request.session_id);
      const record =
        this.sessionRecordFromJournal(handle, envelope, request.session_id) ?? null;
      if (!record) {
        throw new JobRunnerError(
          'JOB_SESSION_NOT_FOUND',
          `Session ${request.session_id} has no journaled state record; admission is refused.`,
          { detail: { session_id: request.session_id } },
        );
      }
      const attempt = record.attempt;
      const operationId = this.operationId(request, attempt);

      // 1. Session transition to QUEUED when the session is READY.
      //    The transition, its journal event, and everything below
      //    commit in this one transaction. transitionState opens its
      //    own db.write, which joins the outer unit (nested
      //    participation, sqlite.ts tx law).
      let stateVersion = record.state_version;
      if (record.state === 'READY') {
        const next = this.repositories.transitionState(
          envelope,
          request.session_id,
          'QUEUED',
          record.state_version,
        );
        stateVersion = next.state_version;
      } else if (record.state === 'QUEUED') {
        // QUEUED is valid ONLY with its committed job -- except on the
        // explicit readmit path, where the absence has already been
        // proved inside this transaction and this call is the repair
        // itself. Reject-only admission never passes the break through.
        const anyJob = handle
          .prepare(
            `SELECT id FROM council_jobs
              WHERE tenant_id = ? AND company_id = ? AND session_id = ?
                AND kind = 'operation'`,
          )
          .get(envelope.tenant_id, envelope.company_id, request.session_id);
        if (!anyJob && queuedWithoutJob === 'reject') {
          throw new JobRunnerError(
            'JOB_INVALID_INPUT',
            `Session ${request.session_id} is QUEUED with no durable operation job: this is an invalid admission target, not a re-admission. Reconcile it through reconcileQueuedWithoutJob.`,
            { detail: { session_id: request.session_id, queued_without_job: true } },
          );
        }
      } else {
        // Admission is only legal from READY or already-QUEUED: any
        // other state means the session is not awaiting queueing.
        throw new ProducerStateConflict(
          `Session ${request.session_id} is ${record.state}; admission requires READY or QUEUED.`,
          { session_state: record.state },
        );
      }

      // 2. Job row (CWE-006 claimJob on the same handle/unit).
      const job = this.jobs.claimJob(envelope, {
        sessionId: request.session_id,
        attempt,
        briefRevision: record.brief_revision,
        phaseJobKey: request.phase_job_key,
        inputSha256: request.input_sha256,
        cancelGeneration: record.cancel_generation,
        seatId: request.seat_id,
      });

      // 3. Receipt + descriptor: same key, compare fingerprints.
      const jobRow = handle
        .prepare(
          `SELECT payload_json FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = 'operation'`,
        )
        .get(envelope.tenant_id, envelope.company_id, job.id) as
        | { payload_json: string }
        | undefined;
      if (!jobRow) {
        throw new JobRunnerError(
          'JOB_NOT_FOUND',
          `Job ${job.id} vanished inside the admission transaction.`,
          { detail: { job_id: job.id } },
        );
      }
      const payload = JSON.parse(jobRow.payload_json) as ReceiptedJobPayload & {
        runner?: unknown;
      };
      const existingReceipt = payload.receipt ?? null;
      if (existingReceipt) {
        if (existingReceipt.admission_fingerprint !== fingerprint) {
          throw new JobRunnerError(
            'JOB_DESCRIPTOR_CONFLICT',
            `Operation ${operationId} was already admitted with a different fingerprint (descriptor, route, seat, or pack changed). The same idempotency key with different dispatch meaning is a caller bug, not a re-admission.`,
            { detail: { operation_id: operationId } },
          );
        }
        // Losing concurrent duplicate or deliberate replay: return the
        // committed receipt, write nothing.
        return { receipt: existingReceipt, created: false } as const;
      }

      // 4. Journal event (operation_reserved) + outbox intent, in
      //    this same transaction. Sequence allocation is inside the
      //    transaction (journal law), so the event_sequence recorded
      //    on the receipt is the one this commit allocated.
      const journal = this.repositories.journal;
      const event = journal.append(handle, envelope, request.session_id, {
        event_id: this.ids.newId(),
        type: 'operation_reserved',
        from_state: record.state,
        to_state: record.state === 'READY' ? 'QUEUED' : record.state,
        actor_subject: envelope.actor_subject,
        payload: {
          operation_id: operationId,
          grant_id: request.descriptor.grant_id,
          kind: request.descriptor.kind,
          purpose: request.descriptor.purpose ?? 'council_run',
          original_operation_id: request.descriptor.original_operation_id ?? null,
          estimate_minor: request.descriptor.estimate_minor,
          round: request.descriptor.round,
          seat_id: request.seat_id,
          input_sha256: request.input_sha256,
          route_snapshot_fingerprint: routeSnapshotFingerprint(request.route_snapshot),
          admitted_by: 'operation-producer',
        },
        created_at: now,
      });
      this.repositories.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: request.session_id,
        event_sequence: event.sequence,
        topic: 'operation.admitted',
        idempotency_key: operationId,
        payload: {
          session_id: request.session_id,
          operation_id: operationId,
          event_sequence: event.sequence,
        },
        created_at: now,
      });

      // 5. Receipt: commit descriptor (same law as enqueueOperation)
      //    plus the receipt itself.
      const descriptor = {
        ...request.descriptor,
        route_snapshot: request.route_snapshot,
      };
      const receipt: OperationAdmissionReceipt = {
        schema_version: 'wise-elders.operation-receipt/v1',
        operation_id: operationId,
        operation_id_hash: canonicalHash({ operation_id: operationId }),
        session_id: request.session_id,
        owner_subject: session.owner_subject ?? envelope.actor_subject,
        run_generation: record.lease_epoch,
        operation_kind: request.descriptor.kind,
        round: request.descriptor.round,
        seat_id: request.seat_id,
        purpose: request.descriptor.purpose ?? 'council_run',
        input_hash: request.input_sha256,
        route_snapshot_hash: routeSnapshotFingerprint(request.route_snapshot),
        grant_id: request.descriptor.grant_id,
        pack_hash: request.pack_hash ?? '',
        attempt_id: request.descriptor.original_operation_id ?? operationId,
        attempt_ordinal: 1,
        replayed: false,
        lease_owner: null,
        lease_generation: record.lease_epoch,
        lease_expires_at: null,
        provider_request_id: null,
        state: 'queued',
        state_label: 'never_dispatched',
        reserved_units: request.descriptor.estimate_minor,
        cost_knowledge: 'estimated',
        observed_usage: null,
        accepted_result_hash: null,
        event_sequence: event.sequence,
        retry_disposition: 'not_needed',
        admission_fingerprint: fingerprint,
        created_at: now,
        updated_at: now,
      };
      payload.receipt = receipt;
      payload.runner = descriptor;
      const result = handle
        .prepare(
          `UPDATE council_jobs SET payload_json = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND state = 'queued'`,
        )
        .run(
          canonicalStringify(payload),
          now,
          envelope.tenant_id,
          envelope.company_id,
          job.id,
        );
      if (Number(result.changes) !== 1) {
        throw new JobRunnerError(
          'JOB_LEASE_FENCED',
          `Job ${job.id} was not admitted as queued; a concurrent writer changed it inside this transaction.`,
          { detail: { job_id: job.id } },
        );
      }
      return { receipt, created: true } as const;
    });
    return { outcome: 'committed', receipt: outcome.receipt, created: outcome.created };
  }

  /**
   * The committed receipt for an operation identity, read-only. This
   * is the replay path: after a restart, the caller re-derives the
   * operation identity and reads the same committed receipt back,
   * including its attempt_ordinal and lease_generation (never reset).
   */
  getReceipt(
    envelope: AuthorizationEnvelope,
    identity: {
      session_id: string;
      attempt: number;
      phase_job_key: string;
      input_sha256: string;
    },
  ): OperationAdmissionReceipt | null {
    const operationId = operationKey(
      identity.session_id,
      identity.attempt,
      identity.phase_job_key,
      identity.input_sha256,
    );
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT payload_json FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND kind = 'operation' AND idempotency_key = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, operationId),
    ) as { payload_json: string } | undefined;
    if (!row) return null;
    return this.receiptFromPayload(row.payload_json);
  }

  /**
   * Mutable commit against an admitted receipt with the fencing token
   * rechecked inside the transaction: a stale lease_generation (the
   * job row's lease_epoch has moved on, or the session record's
   * lease_epoch has moved on) cannot commit. Restart never resets the
   * token: it is read from the committed receipt, not from memory.
   */
  commitMutable(
    envelope: AuthorizationEnvelope,
    identity: {
      session_id: string;
      attempt: number;
      phase_job_key: string;
      input_sha256: string;
    },
    mutation: {
      expected_lease_generation: number;
      lease_owner?: string | null;
      lease_expires_at?: string | null;
      provider_request_id?: string | null;
      state?: ReceiptStateLabel;
      cost_knowledge?: CostKnowledge;
      observed_usage?: { input_units: number | null; output_units: number | null } | null;
      accepted_result_hash?: string | null;
      retry_disposition?: RetryDisposition;
    },
  ): { committed: boolean; receipt: OperationAdmissionReceipt | null } {
    assertEnvelopePurpose(envelope, 'write', 'Receipt mutation');
    const operationId = operationKey(
      identity.session_id,
      identity.attempt,
      identity.phase_job_key,
      identity.input_sha256,
    );
    return withHandle(this.db, (handle) => {
      const jobRow = handle
        .prepare(
          `SELECT payload_json, lease_epoch FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND kind = 'operation' AND idempotency_key = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, operationId) as
        | { payload_json: string; lease_epoch: number }
        | undefined;
      if (!jobRow) {
        throw new JobRunnerError(
          'JOB_NOT_FOUND',
          `No admitted operation ${operationId} exists in this scope.`,
          { detail: { operation_id: operationId } },
        );
      }
      const receipt = this.receiptFromPayload(jobRow.payload_json);
      if (!receipt) {
        throw new JobRunnerError(
          'JOB_INVALID_INPUT',
          `Operation ${operationId} has no committed receipt; mutable commits require admission first.`,
          { detail: { operation_id: operationId } },
        );
      }
      // Fencing token recheck on EVERY mutable commit: the caller's
      // generation must still be the committed receipt's generation,
      // and the job row's lease_epoch must not have moved past it.
      if (
        mutation.expected_lease_generation !== receipt.lease_generation ||
        jobRow.lease_epoch > receipt.lease_generation
      ) {
        return { committed: false, receipt } as const;
      }
      const session = this.sessionStateRow(handle, envelope, identity.session_id);
      const sessionRecord = this.sessionRecordFromJournal(
        handle,
        envelope,
        identity.session_id,
      );
      if (
        sessionRecord &&
        sessionRecord.lease_epoch > receipt.lease_generation
      ) {
        return { committed: false, receipt } as const;
      }
      const now = this.nowIso();
      const next: OperationAdmissionReceipt = {
        ...receipt,
        // Nullable fields: omitted means "unchanged", an explicit null
        // means "clear". `??` cannot tell those apart, so every nullable
        // field tests for undefined explicitly -- otherwise a lease
        // release (lease_owner back to null) is unexpressible.
        lease_owner:
          mutation.lease_owner !== undefined ? mutation.lease_owner : receipt.lease_owner,
        lease_expires_at:
          mutation.lease_expires_at !== undefined
            ? mutation.lease_expires_at
            : receipt.lease_expires_at,
        provider_request_id:
          mutation.provider_request_id !== undefined
            ? mutation.provider_request_id
            : receipt.provider_request_id,
        state: mutation.state ? RECEIPT_STATE_TO_JOB_STATE[mutation.state] : receipt.state,
        state_label: mutation.state ?? receipt.state_label,
        cost_knowledge: mutation.cost_knowledge ?? receipt.cost_knowledge,
        observed_usage:
          mutation.observed_usage !== undefined
            ? mutation.observed_usage
            : receipt.observed_usage,
        accepted_result_hash:
          mutation.accepted_result_hash !== undefined
            ? mutation.accepted_result_hash
            : receipt.accepted_result_hash,
        retry_disposition: mutation.retry_disposition ?? receipt.retry_disposition,
        updated_at: now,
      };
      const updated = this.receiptedPayloadMutation(
        handle,
        envelope,
        operationId,
        (payload) => {
          if (payload.receipt === receipt) return false;
          payload.receipt = next;
          return true;
        },
      );
      if (!updated) {
        return { committed: false, receipt } as const;
      }
      return { committed: true, receipt: next } as const;
    });
  }

  /**
   * Deterministic reconciliation for historical queued-without-job
   * rows: a session left QUEUED (or later) with no operation job row
   * for the identity the caller expected. The owning service resolves
   * it truthfully, and the decision is journaled:
   *
   * - 'fail_session': the session is transitioned out of the broken
   *   queueing state to FAILED.
   * - 'readmit': the missing operation is admitted now, in this same
   *   transaction, when the caller still holds the full request. The
   *   session stays QUEUED because the repair closes the gap rather
   *   than abandoning the queued work. The request must be bound to
   *   `identity.session_id`; a request for any other session is
   *   refused.
   *
   * Queued-without-job is never silently passed through, and a
   * QUEUED session that already has its job is reported as
   * action: 'none'.
   */
  reconcileQueuedWithoutJob(
    envelope: AuthorizationEnvelope,
    identity: { session_id: string },
    resolution: { action: 'fail_session' } | { action: 'readmit'; request: AdmitOperationRequest },
  ): { reconciled: true; detail: Record<string, unknown> } {
    assertEnvelopePurpose(envelope, 'write', 'Queued-without-job reconciliation');
    return withHandle(this.db, (handle) => {
      const session = this.sessionStateRow(handle, envelope, identity.session_id);
      if (session.state === 'QUEUED') {
        // Verify the claimed absence inside the transaction.
        const anyJob = handle
          .prepare(
            `SELECT id FROM council_jobs
              WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND kind = 'operation'`,
          )
          .get(envelope.tenant_id, envelope.company_id, identity.session_id);
        if (anyJob) {
          return {
            reconciled: true as const,
            detail: { session_state: session.state, jobs_present: true, action: 'none' },
          };
        }
        if (resolution.action === 'readmit') {
          if (resolution.request.session_id !== identity.session_id) {
            throw new JobRunnerError(
              'JOB_INVALID_INPUT',
              `Readmission was asked to repair session ${identity.session_id} but its request is bound to ${resolution.request.session_id}; refusing to admit work for a different session.`,
              {
                detail: {
                  session_id: identity.session_id,
                  request_session_id: resolution.request.session_id,
                  session_mismatch: true,
                },
              },
            );
          }
          // Readmission closes the gap durably: the session stays
          // QUEUED (that is the state being repaired), the job, the
          // receipt, the operation_reserved event, and the outbox
          // intent commit now. The policy is what makes this call
          // succeed where plain admission correctly refuses.
          const readmitted = this.admitWithPolicy(
            envelope,
            resolution.request,
            'readmit',
          );
          return {
            reconciled: true as const,
            detail: {
              session_state: 'QUEUED',
              jobs_present: false,
              action: 'readmit',
              operation_id: readmitted.receipt.operation_id,
              created: readmitted.created,
            },
          };
        }
        // fail_session: the historical break is recorded truthfully.
        const record =
          this.sessionRecordFromJournal(handle, envelope, identity.session_id) ?? null;
        if (!record) {
          throw new JobRunnerError(
            'JOB_SESSION_NOT_FOUND',
            `Session ${identity.session_id} has no journaled state record to reconcile.`,
            { detail: { session_id: identity.session_id } },
          );
        }
        this.repositories.transitionState(
          envelope,
          identity.session_id,
          'FAILED',
          record.state_version,
        );
        return {
          reconciled: true as const,
          detail: {
            session_state: 'QUEUED',
            jobs_present: false,
            action: 'fail_session',
            failed_to: 'FAILED',
          },
        };
      }
      // Not queued: nothing to reconcile, report truthfully.
      return {
        reconciled: true as const,
        detail: { session_state: session.state, jobs_present: null, action: 'none' },
      };
    });
  }

  /**
   * State label for a receipt: the persisted `state_label` for the two
   * labels the durable rows cannot separate, otherwise derived from the
   * job row and attempt ledger rows. This is a read; it never mutates
   * and never invents a state.
   */
  stateLabel(
    envelope: AuthorizationEnvelope,
    identity: {
      session_id: string;
      attempt: number;
      phase_job_key: string;
      input_sha256: string;
    },
  ): ReceiptStateLabel | null {
    const operationId = operationKey(
      identity.session_id,
      identity.attempt,
      identity.phase_job_key,
      identity.input_sha256,
    );
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT state, terminal_reason, payload_json FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND kind = 'operation' AND idempotency_key = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, operationId),
    ) as { state: string; terminal_reason: string | null; payload_json: string } | undefined;
    if (!row) return null;
    const attempt = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT status FROM council_provider_attempts
            WHERE tenant_id = ? AND company_id = ? AND operation_id = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, operationId),
    ) as { status: string } | undefined;
    const derived = labelFromJobRow(row.state, attempt?.status ?? null);
    // A terminal job row is the newest truth; it always wins over a
    // receipt label written before the job finished.
    if (row.state !== 'queued' && row.state !== 'leased' && row.state !== 'running') {
      return derived;
    }
    // 'potentially_dispatched' and 'response_observed' both land on
    // JobState 'leased', so the persisted receipt label is the only
    // durable evidence of which one was committed. Everything else
    // keeps deriving from the rows.
    // ponytail: only those two labels are read back from the receipt.
    // Widen to every label if a writer outside this producer ever
    // persists receipts this reader does not also derive.
    const persisted = this.receiptFromPayload(row.payload_json)?.state_label ?? null;
    if (persisted === 'potentially_dispatched' || persisted === 'response_observed') {
      return persisted;
    }
    return derived;
  }
}

/** Exported for tests and CWE-050 reconciliation reporting. */
export {
  ProducerStateConflict,
  RECEIPT_STATE_EVENT_TYPES,
};