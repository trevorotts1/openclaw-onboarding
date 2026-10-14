/**
 * Job substrate and operation checkpoints (CWE-006, directive Sections
 * 15.4 and 16.2; belongs to unit CWE-006's repository layer).
 *
 * The canonical council_jobs table is a generic durable job row: a
 * kind, a deterministic idempotency key, a lifecycle state, lease
 * fields, and JSON payload and checkpoint columns. This repository
 * gives it the operation semantics Section 15.4 defines:
 *
 * - An operation job is addressed by the deterministic identity
 *   (session, attempt, phase_job_key, input_sha256), carried as the
 *   idempotency key. Claiming the same operation twice returns the
 *   same job row instead of creating a duplicate (Sections 15.4, 17).
 * - A checkpoint is written only after its output has passed full
 *   schema validation (Section 15.4); this repository re-validates the
 *   checkpoint against the canonical contract before storing it in the
 *   checkpoint row's checkpoint_json, so an invalid partial can never
 *   be persisted as a resumable result. Checkpoints are their own job
 *   rows (kind 'operation_checkpoint') keyed by the full checkpoint
 *   identity, which adds the seat to the operation identity.
 * - Resume is fenced: the stored cancellation generation must equal
 *   the caller's current generation, or the checkpoint is refused
 *   (Section 15.2). A brief-revision mismatch is likewise refused.
 * - Job lifecycle writes are compare-and-swap on the current state and
 *   lease epoch, so two workers cannot both own or finish one job,
 *   and a replaced worker's late finish is rejected (Section 15.8).
 */

import {
  canonicalHash,
  canonicalStringify,
  validateJobCheckpoint,
  type Clock,
  type IdSource,
  type JobCheckpoint,
} from '../contracts/index.js';
import type { AuthorizationEnvelope } from './envelope.js';
import { PersistenceError } from './errors.js';
import { DELETION_TOMBSTONE_OPERATION, DELETION_TOMBSTONE_SOURCE } from './repositories.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from './sqlite.js';

export const OPERATION_JOB_KIND = 'operation';
export const CHECKPOINT_JOB_KIND = 'operation_checkpoint';

export type JobState =
  | 'queued'
  | 'leased'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'dead_letter'
  | 'cancelled';

export interface JobRecord {
  id: string;
  session_id: string;
  attempt: number;
  phase_job_key: string;
  input_sha256: string;
  state: JobState;
  lease_epoch: number;
  cancel_generation: number;
  brief_revision: number;
}

interface JobPayload {
  attempt: number;
  brief_revision: number;
  phase_job_key: string;
  seat_id: string | null;
  input_sha256: string;
  cancel_generation: number;
  result_ref?: string;
}

interface JobRow {
  id: string;
  session_id: string | null;
  state: JobState;
  lease_epoch: number;
  payload_json: string;
  checkpoint_json: string | null;
}

function operationKey(sessionId: string, attempt: number, phaseJobKey: string, inputSha256: string): string {
  return canonicalHash({
    session_id: sessionId,
    attempt,
    phase_job_key: phaseJobKey,
    input_sha256: inputSha256,
  });
}

function checkpointKey(
  sessionId: string,
  attempt: number,
  phaseJobKey: string,
  seatId: string | null,
  inputSha256: string,
): string {
  return canonicalHash({
    session_id: sessionId,
    attempt,
    phase_job_key: phaseJobKey,
    seat_id: seatId ?? '',
    input_sha256: inputSha256,
  });
}

export class CouncilJobs {
  constructor(
    private readonly db: CouncilDatabase,
    private readonly deps: { clock: Clock; ids: IdSource },
  ) {}

  private assertSessionUsable(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): void {
    const tombstone = handle
      .prepare(
        `SELECT request_key FROM council_request_keys
          WHERE tenant_id = ? AND source = ? AND operation = ? AND request_key = ?`,
      )
      .get(
        envelope.tenant_id,
        DELETION_TOMBSTONE_SOURCE,
        DELETION_TOMBSTONE_OPERATION,
        sessionId,
      ) as { request_key: string } | undefined;
    if (tombstone) {
      throw new PersistenceError(
        'PERSISTENCE_SESSION_DELETED',
        `Council session ${sessionId} was explicitly deleted. Late writes to a deleted session are blocked, and the session is never reconstituted by a late write.`,
        { retryable: false },
      );
    }
    const session = handle
      .prepare(
        `SELECT id FROM council_sessions WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as { id: string } | undefined;
    if (!session) {
      throw new PersistenceError(
        'PERSISTENCE_SESSION_NOT_FOUND',
        `No council session ${sessionId} exists in this tenant and company scope.`,
        { retryable: false },
      );
    }
  }

  private jobRowByKey(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    kind: string,
    idempotencyKey: string,
  ): JobRow | undefined {
    return handle
      .prepare(
        `SELECT id, session_id, state, lease_epoch, payload_json, checkpoint_json
           FROM council_jobs
          WHERE tenant_id = ? AND company_id = ? AND kind = ? AND idempotency_key = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, kind, idempotencyKey) as JobRow | undefined;
  }

  private toRecord(row: JobRow, sessionId: string): JobRecord {
    const payload = JSON.parse(row.payload_json) as JobPayload;
    return {
      id: row.id,
      session_id: sessionId,
      attempt: payload.attempt,
      phase_job_key: payload.phase_job_key,
      input_sha256: payload.input_sha256,
      state: row.state,
      lease_epoch: row.lease_epoch,
      cancel_generation: payload.cancel_generation,
      brief_revision: payload.brief_revision,
    };
  }

  /**
   * Claim the deterministic job for an operation, creating it queued
   * when absent. Idempotent: the same identity always returns the same
   * job row.
   */
  claimJob(
    envelope: AuthorizationEnvelope,
    input: {
      sessionId: string;
      attempt: number;
      briefRevision: number;
      phaseJobKey: string;
      inputSha256: string;
      cancelGeneration: number;
      seatId: string | null;
    },
  ): JobRecord {
    const key = operationKey(input.sessionId, input.attempt, input.phaseJobKey, input.inputSha256);
    return this.db.write((handle) => {
      this.assertSessionUsable(handle, envelope, input.sessionId);
      const existing = this.jobRowByKey(handle, envelope, OPERATION_JOB_KIND, key);
      if (existing) return this.toRecord(existing, input.sessionId);
      const id = this.deps.ids.newId();
      const now = this.deps.clock.nowUtc();
      const payload: JobPayload = {
        attempt: input.attempt,
        brief_revision: input.briefRevision,
        phase_job_key: input.phaseJobKey,
        seat_id: input.seatId,
        input_sha256: input.inputSha256,
        cancel_generation: input.cancelGeneration,
      };
      handle
        .prepare(
          `INSERT INTO council_jobs
             (tenant_id, company_id, session_id, id, kind, idempotency_key, state,
              payload_json, checkpoint_json, terminal_reason, attempt_count,
              next_attempt_at, lease_owner, lease_expires_at, lease_epoch,
              last_error_code, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, NULL, NULL, 0, NULL, NULL, NULL, 0,
                   NULL, ?, ?)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          input.sessionId,
          id,
          OPERATION_JOB_KIND,
          key,
          canonicalStringify(payload),
          now,
          now,
        );
      return {
        id,
        session_id: input.sessionId,
        attempt: input.attempt,
        phase_job_key: input.phaseJobKey,
        input_sha256: input.inputSha256,
        state: 'queued' as const,
        lease_epoch: 0,
        cancel_generation: input.cancelGeneration,
        brief_revision: input.briefRevision,
      };
    });
  }

  /**
   * Lease a queued job to a worker, bumping the lease epoch so any
   * prior owner's late commit fails its fence (Section 15.8).
   * Compare-and-swap on state: a job that is not queued, or whose
   * recorded cancellation generation no longer matches the caller's
   * current generation, is not leasable and returns null.
   */
  leaseJob(
    envelope: AuthorizationEnvelope,
    jobId: string,
    workerId: string,
    leaseSeconds: number,
    currentCancelGeneration: number,
  ): JobRecord | null {
    const now = this.deps.clock.nowUtc();
    const expires = new Date(Date.parse(now) + leaseSeconds * 1000).toISOString();
    return this.db.write((handle) => {
      const row = handle
        .prepare(
          `SELECT id, session_id, state, lease_epoch, payload_json, checkpoint_json
             FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, jobId, OPERATION_JOB_KIND) as
        | JobRow
        | undefined;
      if (!row || row.state !== 'queued' || row.session_id === null) return null;
      const payload = JSON.parse(row.payload_json) as JobPayload;
      if (payload.cancel_generation !== currentCancelGeneration) return null;
      const result = handle
        .prepare(
          `UPDATE council_jobs
              SET state = 'leased', lease_owner = ?, lease_epoch = lease_epoch + 1,
                  lease_expires_at = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND state = 'queued'`,
        )
        .run(workerId, expires, now, envelope.tenant_id, envelope.company_id, jobId);
      if (Number(result.changes) !== 1) return null;
      return {
        ...this.toRecord(row, row.session_id),
        state: 'leased',
        lease_epoch: row.lease_epoch + 1,
      };
    });
  }

  /**
   * Terminal job write, compare-and-swap from the leased state at the
   * caller's lease epoch. Returns false when the job is no longer the
   * caller's to finish (already finished, or the lease moved on).
   */
  finishJob(
    envelope: AuthorizationEnvelope,
    jobId: string,
    leaseEpoch: number,
    outcome:
      | { status: 'succeeded'; resultRef: string }
      | { status: 'failed' | 'cancelled'; errorClass: string },
  ): boolean {
    return this.db.write((handle) => {
      const row = handle
        .prepare(
          `SELECT id, session_id, state, lease_epoch, payload_json, checkpoint_json
             FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, jobId, OPERATION_JOB_KIND) as
        | JobRow
        | undefined;
      if (!row || (row.state !== 'leased' && row.state !== 'running')) return false;
      if (row.lease_epoch !== leaseEpoch) return false;
      const now = this.deps.clock.nowUtc();
      if (outcome.status === 'succeeded') {
        const payload = JSON.parse(row.payload_json) as JobPayload;
        const result = handle
          .prepare(
            `UPDATE council_jobs
                SET state = 'succeeded', payload_json = ?, updated_at = ?
              WHERE tenant_id = ? AND company_id = ? AND id = ? AND lease_epoch = ?`,
          )
          .run(
            canonicalStringify({ ...payload, result_ref: outcome.resultRef }),
            now,
            envelope.tenant_id,
            envelope.company_id,
            jobId,
            leaseEpoch,
          );
        return Number(result.changes) === 1;
      }
      const result = handle
        .prepare(
          `UPDATE council_jobs
              SET state = ?, terminal_reason = ?, last_error_code = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND lease_epoch = ?`,
        )
        .run(
          outcome.status,
          outcome.errorClass,
          outcome.errorClass,
          now,
          envelope.tenant_id,
          envelope.company_id,
          jobId,
          leaseEpoch,
        );
      return Number(result.changes) === 1;
    });
  }

  /**
   * Persist a validated operation checkpoint. The payload is validated
   * against the canonical JobCheckpoint contract first: an invalid
   * partial is refused, never stored as a resumable result. Saving the
   * same checkpoint identity again replaces the stored checkpoint
   * (checkpoints are resumable snapshots, not immutable records).
   */
  saveCheckpoint(
    envelope: AuthorizationEnvelope,
    checkpoint: JobCheckpoint,
    sessionCancelGeneration: number,
  ): void {
    const check = validateJobCheckpoint(checkpoint);
    if (!check.ok) {
      throw new PersistenceError(
        'PERSISTENCE_VALIDATION_FAILED',
        'The checkpoint failed canonical contract validation and was not stored.',
        { retryable: false, detail: { issues: check.issues } },
      );
    }
    if (
      checkpoint.tenant_id !== envelope.tenant_id ||
      checkpoint.installation_id !== envelope.installation_id
    ) {
      throw new PersistenceError(
        'PERSISTENCE_SCOPE_DENIED',
        'The checkpoint tenant or installation does not match the authorization envelope. The checkpoint was not stored.',
        { retryable: false },
      );
    }
    const key = checkpointKey(
      checkpoint.session_id,
      checkpoint.attempt,
      checkpoint.phase,
      checkpoint.seat_id,
      checkpoint.input_sha256,
    );
    this.db.write((handle) => {
      this.assertSessionUsable(handle, envelope, checkpoint.session_id);
      const now = this.deps.clock.nowUtc();
      const payload: JobPayload = {
        attempt: checkpoint.attempt,
        brief_revision: checkpoint.brief_revision,
        phase_job_key: checkpoint.phase,
        seat_id: checkpoint.seat_id,
        input_sha256: checkpoint.input_sha256,
        cancel_generation: sessionCancelGeneration,
      };
      const existing = this.jobRowByKey(handle, envelope, CHECKPOINT_JOB_KIND, key);
      if (existing) {
        handle
          .prepare(
            `UPDATE council_jobs
                SET checkpoint_json = ?, payload_json = ?, updated_at = ?
              WHERE tenant_id = ? AND company_id = ? AND id = ?`,
          )
          .run(
            canonicalStringify(checkpoint),
            canonicalStringify(payload),
            now,
            envelope.tenant_id,
            envelope.company_id,
            existing.id,
          );
        return;
      }
      handle
        .prepare(
          `INSERT INTO council_jobs
             (tenant_id, company_id, session_id, id, kind, idempotency_key, state,
              payload_json, checkpoint_json, terminal_reason, attempt_count,
              next_attempt_at, lease_owner, lease_expires_at, lease_epoch,
              last_error_code, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'succeeded', ?, ?, NULL, 0, NULL, NULL, NULL, 0,
                   NULL, ?, ?)`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          checkpoint.session_id,
          this.deps.ids.newId(),
          CHECKPOINT_JOB_KIND,
          key,
          canonicalStringify(payload),
          canonicalStringify(checkpoint),
          now,
          now,
        );
    });
  }

  /**
   * Load a checkpoint for resume, fenced by the caller's CURRENT
   * cancellation generation and brief revision: a checkpoint written
   * under a superseded generation or revision is refused (returns
   * null), never silently reused (Sections 15.2 and 15.4).
   */
  getCheckpoint(
    envelope: AuthorizationEnvelope,
    input: {
      sessionId: string;
      attempt: number;
      briefRevision: number;
      phaseJobKey: string;
      seatId: string | null;
      inputSha256: string;
      currentCancelGeneration: number;
    },
  ): JobCheckpoint | null {
    const key = checkpointKey(
      input.sessionId,
      input.attempt,
      input.phaseJobKey,
      input.seatId,
      input.inputSha256,
    );
    const row = this.db.read((handle) =>
      this.jobRowByKey(handle, envelope, CHECKPOINT_JOB_KIND, key),
    );
    if (!row || row.checkpoint_json === null) return null;
    const checkpoint = JSON.parse(row.checkpoint_json) as JobCheckpoint;
    // The contract checkpoint carries no generation; the fence compares
    // the session generation recorded in the row payload at save time.
    const savedPayload = JSON.parse(row.payload_json) as JobPayload;
    if (savedPayload.cancel_generation !== input.currentCancelGeneration) return null;
    if (checkpoint.brief_revision !== input.briefRevision) return null;
    if (checkpoint.attempt !== input.attempt) return null;
    return checkpoint;
  }
}
