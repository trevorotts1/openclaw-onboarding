/**
 * Typed errors for the durable deliberation job runner (CWE-027,
 * directive Sections 15 and 34 CWE-027).
 *
 * Every refusal the runner raises is one of these codes, so callers
 * (and tests) distinguish a fencing loss from a control conflict from
 * a capability gap without matching message text. Errors from the
 * composed services keep their own types (CWE-028 BudgetCapacityError,
 * CWE-049 RunAuthorizationError, CWE-006 PersistenceError); the runner
 * never wraps them into its own codes, because their codes are the
 * contract CWE-050 reconciles against.
 */

export type JobRunnerErrorCode =
  | 'JOB_INVALID_INPUT'
  | 'JOB_NOT_FOUND'
  | 'JOB_SESSION_NOT_FOUND'
  | 'JOB_SESSION_NOT_RUNNABLE'
  | 'JOB_LEASE_FENCED'
  | 'JOB_LEASE_LOST'
  | 'JOB_CONTROL_CONFLICT'
  | 'JOB_DESCRIPTOR_CONFLICT'
  | 'WORKER_CAPABILITY_UNAVAILABLE';

export class JobRunnerError extends Error {
  readonly code: JobRunnerErrorCode;
  readonly retryable: boolean;
  readonly detail: Record<string, unknown> | null;

  constructor(
    code: JobRunnerErrorCode,
    message: string,
    options: { retryable?: boolean; detail?: Record<string, unknown> | null } = {},
  ) {
    super(message);
    this.name = 'JobRunnerError';
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.detail = options.detail ?? null;
  }
}

export function isJobRunnerError(
  error: unknown,
  code?: JobRunnerErrorCode,
): error is JobRunnerError {
  return (
    error instanceof JobRunnerError && (code === undefined || error.code === code)
  );
}

/**
 * Thrown by test doubles and crash simulators to emulate a worker
 * process dying mid-operation. The runner deliberately does NOT catch
 * it as an operation failure: a crash is not a failure verdict, it is
 * the absence of one, and the durable state (job lease, attempt
 * ledger, reservation) is what the next worker reconciles. Production
 * transports never throw this; it exists so tests can kill an
 * operation at the defined points (after admission, after dispatch,
 * after commit) and prove recovery from durable state alone.
 */
export class SimulatedCrashError extends Error {
  readonly code = 'SIMULATED_CRASH';
  constructor(point: string) {
    super(`Simulated worker crash at ${point}.`);
    this.name = 'SimulatedCrashError';
  }
}

export function isSimulatedCrash(error: unknown): boolean {
  return (
    error instanceof SimulatedCrashError ||
    (error instanceof Error && (error as { code?: unknown }).code === 'SIMULATED_CRASH')
  );
}
