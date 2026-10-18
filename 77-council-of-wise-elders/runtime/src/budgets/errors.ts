/**
 * Typed errors for the shared budget and capacity service (CWE-028,
 * directive Sections 13, 15.6, 15.7, 17.3).
 *
 * Codes follow the stable-code style of Section 17.3, matching the
 * shape of the CWE-004 CouncilError and the CWE-006 PersistenceError:
 * callers branch on `code`, never on message text. Every error carries
 * a plain English message, whether it is retryable, the next action an
 * operator can take, and optional machine-readable detail that never
 * contains secret values, raw provider bodies, or private decision
 * text.
 *
 * Readiness law (Sections 13.5 and 15.6): when a reservation cannot be
 * honored (no grant record, an inactive grant, an exhausted ceiling, a
 * fenced lease epoch, an unavailable store), the service fails with one
 * of these typed errors and records nothing. There is no partial
 * grant, no silent queue, and no best-effort reservation.
 */

export type BudgetCapacityErrorCode =
  | 'BUDGET_INVALID_INPUT'
  | 'BUDGET_GRANT_NOT_FOUND'
  | 'BUDGET_GRANT_INACTIVE'
  | 'BUDGET_GRANT_SESSION_MISMATCH'
  | 'BUDGET_CURRENCY_MISMATCH'
  | 'BUDGET_EXHAUSTED'
  | 'BUDGET_RESERVATION_NOT_FOUND'
  | 'BUDGET_RESERVATION_FINALIZED'
  | 'BUDGET_LEASE_FENCED'
  | 'BUDGET_RECONCILE_CONFLICT'
  | 'BUDGET_ROUTE_RESOLUTION_REFUSED'
  | 'BUDGET_STORE_UNAVAILABLE'
  | 'CAPACITY_CONFIG_INVALID';

export class BudgetCapacityError extends Error {
  readonly code: BudgetCapacityErrorCode;
  readonly retryable: boolean;
  readonly action: string;
  /** Machine-readable detail: ceiling names, counts, states. No content. */
  readonly detail: Record<string, unknown> | null;

  constructor(
    code: BudgetCapacityErrorCode,
    message: string,
    options: {
      retryable?: boolean;
      action?: string;
      detail?: Record<string, unknown> | null;
    } = {},
  ) {
    super(message);
    this.name = 'BudgetCapacityError';
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.action = options.action ?? 'Review the reported problem and try again.';
    this.detail = options.detail ?? null;
  }
}

export function isBudgetCapacityError(
  value: unknown,
): value is BudgetCapacityError {
  return value instanceof BudgetCapacityError;
}

export function budgetInvalidInput(message: string): BudgetCapacityError {
  return new BudgetCapacityError('BUDGET_INVALID_INPUT', message, {
    retryable: false,
    action: 'Correct the reservation input and retry.',
  });
}

export function budgetExhausted(args: {
  ceiling: string;
  limit: number;
  current: number;
  sessionId: string;
}): BudgetCapacityError {
  return new BudgetCapacityError(
    'BUDGET_EXHAUSTED',
    `Session ${args.sessionId} has reached its ${args.ceiling} ceiling of ${args.limit} (currently ${args.current}). No further reservation can be honored under this grant and settings envelope.`,
    {
      retryable: false,
      action:
        'Continue with the completed work, record a partial result honestly, or start a separately authorized session with its own envelope.',
      detail: {
        ceiling: args.ceiling,
        limit: args.limit,
        current: args.current,
        session_id: args.sessionId,
      },
    },
  );
}

export function budgetLeaseFenced(args: {
  sessionId: string;
  operationId: string;
  presentedEpoch: number;
  currentEpoch: number;
}): BudgetCapacityError {
  return new BudgetCapacityError(
    'BUDGET_LEASE_FENCED',
    `Operation ${args.operationId} in session ${args.sessionId} presented lease epoch ${args.presentedEpoch}, but the session lease is at epoch ${args.currentEpoch}. A stale worker cannot settle, release, or re-price a reservation.`,
    {
      retryable: false,
      action:
        'Discard the late outcome. Only the current lease owner may finalize this reservation.',
      detail: {
        session_id: args.sessionId,
        operation_id: args.operationId,
        presented_epoch: args.presentedEpoch,
        current_epoch: args.currentEpoch,
      },
    },
  );
}

export function budgetStoreUnavailable(message: string): BudgetCapacityError {
  return new BudgetCapacityError('BUDGET_STORE_UNAVAILABLE', message, {
    retryable: true,
    action:
      'Restore the council store (the canonical CWE-005 schema must be applied) and retry. No reservation was recorded.',
  });
}
