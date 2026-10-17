/**
 * Typed errors for the council persistence layer (CWE-006).
 *
 * Codes follow the stable-code style of directive Section 17.3: callers
 * branch on `code`, never on message text. Messages are plain English and
 * never carry secret values, raw provider bodies, or private decision
 * text; a failure to persist is reported with the boundary that failed
 * and what was preserved (nothing partial is ever committed, Section
 * 16.4).
 */

export type PersistenceErrorCode =
  | 'PERSISTENCE_CONFIG_INVALID'
  | 'PERSISTENCE_SCOPE_DENIED'
  | 'PERSISTENCE_SESSION_NOT_FOUND'
  | 'PERSISTENCE_SESSION_DELETED'
  | 'PERSISTENCE_STATE_CONFLICT'
  | 'PERSISTENCE_DUPLICATE_OPERATION'
  | 'PERSISTENCE_OPERATION_CONFLICT'
  | 'PERSISTENCE_STORE_DEFERRED'
  | 'PERSISTENCE_AUTHORITY_MODE_MISMATCH'
  | 'PERSISTENCE_SCHEMA_UNAVAILABLE'
  | 'PERSISTENCE_DIAGNOSTIC_DENIED'
  | 'PERSISTENCE_VALIDATION_FAILED'
  | 'PERSISTENCE_INTERNAL';

export class PersistenceError extends Error {
  readonly code: PersistenceErrorCode;
  readonly retryable: boolean;
  readonly action: string;
  /** Machine-readable detail: field paths, counts, attempt numbers. No content. */
  readonly detail: Record<string, unknown> | null;

  constructor(
    code: PersistenceErrorCode,
    message: string,
    options: {
      retryable?: boolean;
      action?: string;
      detail?: Record<string, unknown> | null;
    } = {},
  ) {
    super(message);
    this.name = 'PersistenceError';
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.action = options.action ?? 'Review the reported problem and try again.';
    this.detail = options.detail ?? null;
  }
}

export function isPersistenceError(value: unknown): value is PersistenceError {
  return value instanceof PersistenceError;
}

export function configInvalid(message: string, detail?: Record<string, unknown>): PersistenceError {
  return new PersistenceError('PERSISTENCE_CONFIG_INVALID', message, {
    retryable: false,
    action: 'Correct the council persistence configuration and retry. Unknown or unsafe values are never silently accepted.',
    detail: detail ?? null,
  });
}

export function scopeDenied(message: string): PersistenceError {
  return new PersistenceError('PERSISTENCE_SCOPE_DENIED', message, {
    retryable: false,
    action: 'Use the authorization envelope of the owning tenant, company, and installation. A supplied scope never confers authority by itself.',
  });
}

export function sessionNotFound(sessionId: string): PersistenceError {
  return new PersistenceError(
    'PERSISTENCE_SESSION_NOT_FOUND',
    `Council session ${sessionId} does not exist in this scope.`,
    { retryable: false, action: 'Check the session ID and the active scope.' },
  );
}

export function sessionDeleted(sessionId: string): PersistenceError {
  return new PersistenceError(
    'PERSISTENCE_SESSION_DELETED',
    `Council session ${sessionId} was explicitly deleted. Deleted sessions are not reconstituted by late writes, delayed events, or stale workers.`,
    {
      retryable: false,
      action: 'Start a new session if the work is still needed; the deleted session ID stays retired.',
    },
  );
}

/**
 * The database stayed locked past the bounded busy budget (Section 16.4,
 * test T056). The write was NOT applied; the caller records a visible
 * deferred state and retries later. Nothing was partially committed.
 */
export class PersistenceDeferredError extends PersistenceError {
  readonly attempts: number;
  readonly waitedMs: number;

  constructor(attempts: number, waitedMs: number) {
    super(
      'PERSISTENCE_STORE_DEFERRED',
      `The council database stayed locked through ${attempts} bounded attempts (${waitedMs} ms). The write was deferred, not applied.`,
      {
        retryable: true,
        action: 'Retry the write after the lock clears. The operation remains in its prior committed state.',
        detail: { attempts, waited_ms: waitedMs },
      },
    );
    this.name = 'PersistenceDeferredError';
    this.attempts = attempts;
    this.waitedMs = waitedMs;
  }
}
