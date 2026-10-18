/**
 * Typed transport errors (CWE-009).
 *
 * Codes follow the stable-code style of directive Section 17.3: callers
 * branch on `code`, never on message text. Messages are plain English
 * and NEVER contain a credential value, a request or response body, an
 * authorization header, or a complete prompt (Sections 16.6 and 28.5):
 * a parse failure carries only a safe error code, a schema path, a byte
 * count, and a response hash.
 *
 * Two flags are part of the CWE-004 host-port contract and are read by
 * the deliberation engine's operation loop:
 * - `retryable`: true only for transient classes where the request is
 *   provably not accepted or the failure is a retryable status (429 or
 *   5xx). Auth, missing-model, policy, and endpoint errors are never
 *   retryable (Section 15.5).
 * - `unknownCompletion`: true when the provider may have accepted the
 *   request but completion is unknown (the first-class
 *   provider_submitted_unresolved state). Such a request is never
 *   replayed blindly; its budget reservation is retained until the
 *   outcome is reconciled.
 */

export type TransportErrorCode =
  | 'TRANSPORT_CONFIG_INVALID'
  | 'TRANSPORT_ENDPOINT_BLOCKED'
  | 'TRANSPORT_ROUTE_MISMATCH'
  | 'TRANSPORT_SELECTION_MUTATED'
  | 'TRANSPORT_CREDENTIAL_MISSING'
  | 'TRANSPORT_REASONING_UNMAPPED'
  | 'TRANSPORT_REASONING_UNSUPPORTED'
  | 'TRANSPORT_ROUTE_SNAPSHOT_INVALID'
  | 'TRANSPORT_COMBINATION_MEMBER_UNKNOWN'
  | 'TRANSPORT_REDIRECT_REFUSED'
  | 'TRANSPORT_AUTH_FAILED'
  | 'TRANSPORT_NOT_FOUND'
  | 'TRANSPORT_BAD_REQUEST'
  | 'TRANSPORT_RATE_LIMITED'
  | 'TRANSPORT_PROVIDER_ERROR'
  | 'TRANSPORT_NETWORK_FAILED'
  | 'TRANSPORT_SUBMITTED_UNRESOLVED'
  | 'TRANSPORT_RESPONSE_MALFORMED'
  | 'TRANSPORT_ROUTE_REFUSED'
  | 'TRANSPORT_CANCELLED'
  | 'TRANSPORT_BUDGET_EXHAUSTED';

/** Safe parse-failure metadata (Section 16.6). Never a raw body. */
export interface SafeParseDiagnostics {
  schemaPath: string;
  byteCount: number;
  responseSha256: string;
}

export interface TransportErrorOptions {
  retryable?: boolean;
  unknownCompletion?: boolean;
  cancelled?: boolean;
  httpStatus?: number | null;
  retryAfterMs?: number | null;
  parseDiagnostics?: SafeParseDiagnostics | null;
  /** The route-resolution outcome when a substitution was refused. */
  resolution?: unknown;
}

export class TransportError extends Error {
  readonly code: TransportErrorCode;
  /** Engine contract flag: transient, provably safe to retry once. */
  readonly retryable: boolean;
  /** Engine contract flag: provider completion is unknown. */
  readonly unknownCompletion: boolean;
  readonly cancelled: boolean;
  readonly httpStatus: number | null;
  readonly retryAfterMs: number | null;
  readonly parseDiagnostics: SafeParseDiagnostics | null;
  readonly resolution: unknown;

  constructor(
    code: TransportErrorCode,
    message: string,
    options: TransportErrorOptions = {},
  ) {
    super(message);
    this.name = 'TransportError';
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.unknownCompletion = options.unknownCompletion ?? false;
    this.cancelled = options.cancelled ?? false;
    this.httpStatus = options.httpStatus ?? null;
    this.retryAfterMs = options.retryAfterMs ?? null;
    this.parseDiagnostics = options.parseDiagnostics ?? null;
    this.resolution = options.resolution ?? null;
  }
}

export function isTransportError(value: unknown): value is TransportError {
  return value instanceof TransportError;
}

export function configError(message: string): TransportError {
  return new TransportError('TRANSPORT_CONFIG_INVALID', message);
}
