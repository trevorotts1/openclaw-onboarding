/**
 * Error type for the CWE-050 protocol services (session controls,
 * history, follow-up, outcomes, settings, composition). One typed
 * error with a stable code, in the style of the other service layers
 * (PersistenceError, JobRunnerError, RunAuthorizationError); hosts map
 * codes onto their own surfaces (CLI exit codes, HTTP statuses).
 */
export type ProtocolErrorCode =
  | 'SESSION_NOT_FOUND'
  | 'SESSION_STATE_CONFLICT'
  | 'IDEMPOTENCY_CONFLICT'
  | 'FOLLOW_UP_INVALID'
  | 'OUTCOME_CONFLICT'
  | 'OUTCOME_INVALID'
  | 'SETTINGS_INVALID'
  | 'COMPOSITION_NOT_READY'
  | 'VALIDATION_FAILED';

export class ProtocolError extends Error {
  readonly code: ProtocolErrorCode;
  readonly detail: Record<string, unknown> | null;

  constructor(
    code: ProtocolErrorCode,
    message: string,
    detail: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = 'ProtocolError';
    this.code = code;
    this.detail = detail;
  }
}
