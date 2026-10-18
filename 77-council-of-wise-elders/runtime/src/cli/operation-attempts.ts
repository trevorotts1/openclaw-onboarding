/**
 * Operation/attempt ledger for subprocess dispatches (WER-008 slice).
 *
 * The record is written BEFORE the child process is launched, so a
 * timeout or a crash can never be mistaken for proof that the provider
 * did no work. Only a definite pre-launch failure is retry-safe.
 *
 * Dispositions:
 * - `launching`   recorded, spawn not yet observed.
 * - `running`     spawn succeeded; the provider may be working.
 * - `completed`   the child exited and a result was accepted.
 * - `failed_definitely`  spawn failed (ENOENT/EACCES); no provider work.
 * - `potentially_dispatched`  deadline/abort/non-zero exit; the provider
 *   may have completed, so replay is refused.
 */

export type AttemptDisposition =
  | 'launching'
  | 'running'
  | 'completed'
  | 'failed_definitely'
  | 'potentially_dispatched';

export interface AttemptRecord {
  operationId: string;
  attemptId: string;
  routeId: string;
  disposition: AttemptDisposition;
  /** ISO timestamp when the record was created (before launch). */
  startedAt: string;
  updatedAt: string;
  /** Plain-English reason, safe to show an operator (no prompt content). */
  detail: string | null;
}

export interface AttemptInput {
  operationId: string;
  attemptId: string;
  routeId: string;
}

export class AttemptLedgerError extends Error {
  readonly code = 'TRANSPORT_ATTEMPT_UNKNOWN';
  constructor(message: string) {
    super(message);
    this.name = 'AttemptLedgerError';
  }
}

/**
 * In-memory ledger. Production durability belongs to the queue/persistence
 * owners; this recorder is the transport-local contract they can wrap.
 */
export class OperationAttemptLedger {
  private readonly records = new Map<string, AttemptRecord>();
  private readonly now: () => Date;

  constructor(options: { now?: () => Date } = {}) {
    this.now = options.now ?? (() => new Date());
  }

  private key(operationId: string, attemptId: string): string {
    return `${operationId}\u0000${attemptId}`;
  }

  /** Record the attempt BEFORE launch. Reusing a key is refused. */
  begin(input: AttemptInput): AttemptRecord {
    const key = this.key(input.operationId, input.attemptId);
    if (this.records.has(key)) {
      throw new AttemptLedgerError(
        `Attempt ${input.attemptId} for operation ${input.operationId} is already recorded; an attempt identity is never reused.`,
      );
    }
    const at = this.now().toISOString();
    const record: AttemptRecord = {
      ...input,
      disposition: 'launching',
      startedAt: at,
      updatedAt: at,
      detail: null,
    };
    this.records.set(key, record);
    return { ...record };
  }

  private update(
    operationId: string,
    attemptId: string,
    disposition: AttemptDisposition,
    detail: string | null,
  ): AttemptRecord {
    const key = this.key(operationId, attemptId);
    const existing = this.records.get(key);
    if (!existing) {
      throw new AttemptLedgerError(
        `No attempt ${attemptId} was recorded for operation ${operationId} before dispatch.`,
      );
    }
    const next: AttemptRecord = {
      ...existing,
      disposition,
      updatedAt: this.now().toISOString(),
      detail,
    };
    this.records.set(key, next);
    return { ...next };
  }

  markRunning(operationId: string, attemptId: string): AttemptRecord {
    return this.update(operationId, attemptId, 'running', null);
  }

  markCompleted(operationId: string, attemptId: string): AttemptRecord {
    return this.update(operationId, attemptId, 'completed', null);
  }

  markFailedDefinitely(operationId: string, attemptId: string, detail: string): AttemptRecord {
    return this.update(operationId, attemptId, 'failed_definitely', detail);
  }

  markPotentiallyDispatched(
    operationId: string,
    attemptId: string,
    detail: string,
  ): AttemptRecord {
    return this.update(operationId, attemptId, 'potentially_dispatched', detail);
  }

  get(operationId: string, attemptId: string): AttemptRecord | null {
    const record = this.records.get(this.key(operationId, attemptId));
    return record ? { ...record } : null;
  }

  list(): AttemptRecord[] {
    return [...this.records.values()].map((record) => ({ ...record }));
  }
}

/**
 * Whether replaying the SAME provider request is safe. Only a definite
 * pre-launch failure qualifies; every other non-success may have reached
 * the provider.
 */
export function isSafeToRetry(record: AttemptRecord): boolean {
  return record.disposition === 'failed_definitely';
}
