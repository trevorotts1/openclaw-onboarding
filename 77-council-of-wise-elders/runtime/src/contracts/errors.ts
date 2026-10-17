/**
 * Typed contract errors for @blackceo/wise-elders-core (CWE-003).
 *
 * Every validation or canonicalization failure in the deterministic core is a
 * ContractError carrying a stable machine-readable code. Callers must branch on
 * `code`, never on message text. No host, network, filesystem, clock, or random
 * dependency exists in this module.
 */

export type ContractErrorCode =
  | 'NON_FINITE_NUMBER'
  | 'DUPLICATE_KEY'
  | 'INVALID_JSON'
  | 'UNSUPPORTED_VALUE'
  | 'INVALID_ID'
  | 'INVALID_TIMESTAMP'
  | 'INVALID_HASH'
  | 'INVALID_MONEY'
  | 'SCHEMA_VALIDATION'
  | 'UNKNOWN_ENUM_VALUE'
  | 'DUPLICATE_OPTION'
  | 'INVALID_REFERENCE'
  | 'SCORE_OUT_OF_RANGE'
  | 'ILLEGAL_TRANSITION'
  | 'VERSION_MISMATCH'
  | 'RETENTION_POLICY_VIOLATION';

export class ContractError extends Error {
  readonly code: ContractErrorCode;
  /** JSON-path style location of the offending value, when known. */
  readonly path: string | null;

  constructor(code: ContractErrorCode, message: string, path: string | null = null) {
    super(message);
    this.name = 'ContractError';
    this.code = code;
    this.path = path;
  }
}

/** A schema validation failure carrying the individual issues found. */
export interface ValidationIssue {
  path: string;
  code: string;
  message: string;
}

export type ValidationResult<T> =
  | { ok: true; value: T }
  | { ok: false; issues: ValidationIssue[] };
