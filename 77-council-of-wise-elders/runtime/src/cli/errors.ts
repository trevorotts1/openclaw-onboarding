/**
 * Typed errors for the portable core host/CLI layer (CWE-004).
 *
 * Codes follow the stable-code style of directive Section 17.3: callers
 * branch on `code`, never on message text. Every error carries a plain
 * English message, whether it is retryable, the next action a user or
 * operator can take, and the process exit code the CLI dispatcher maps
 * it to. FEATURE_NOT_READY is the honest state for behavior owned by a
 * downstream unit that has not been composed into this foundation
 * (Sections 17.5 and 25.6): it is never simulated success.
 */

export type CouncilErrorCode =
  | 'COUNCIL_USAGE'
  | 'COUNCIL_INVALID_INPUT'
  | 'COUNCIL_SESSION_NOT_FOUND'
  | 'COUNCIL_STATE_CONFLICT'
  | 'COUNCIL_VERDICT_NOT_READY'
  | 'COUNCIL_FEATURE_NOT_READY'
  | 'COUNCIL_ROUTE_UNAVAILABLE'
  | 'COUNCIL_TRANSPORT_FAILED'
  | 'COUNCIL_CARD_INVALID'
  | 'COUNCIL_BUDGET_EXHAUSTED'
  | 'COUNCIL_LEASE_LOST'
  | 'RUN_AUTHORIZATION_REQUIRED'
  | 'COUNCIL_STORE_UNAVAILABLE'
  | 'COUNCIL_INTERNAL';

export class CouncilError extends Error {
  readonly code: CouncilErrorCode;
  readonly retryable: boolean;
  readonly action: string;
  readonly exitCode: number;

  constructor(
    code: CouncilErrorCode,
    message: string,
    options: { retryable?: boolean; action?: string; exitCode?: number } = {},
  ) {
    super(message);
    this.name = 'CouncilError';
    this.code = code;
    this.retryable = options.retryable ?? false;
    this.action = options.action ?? 'Review the reported problem and try again.';
    this.exitCode = options.exitCode ?? 1;
  }

  /** Section 17.3 style error envelope; safe for machine consumers. */
  toEnvelope(requestId: string | null = null): Record<string, unknown> {
    return {
      ok: false,
      error: {
        code: this.code,
        message: this.message,
        retryable: this.retryable,
        action: this.action,
        request_id: requestId,
      },
    };
  }
}

export function featureNotReady(what: string, ownerUnit: string): CouncilError {
  return new CouncilError(
    'COUNCIL_FEATURE_NOT_READY',
    `${what} is not available in this build yet. It is owned by ${ownerUnit}, and this foundation does not simulate it.`,
    {
      retryable: false,
      action: `Wait for ${ownerUnit} to land, or use the surfaces that are ready.`,
      exitCode: 3,
    },
  );
}

export function usageError(message: string): CouncilError {
  return new CouncilError('COUNCIL_USAGE', message, {
    retryable: false,
    action: 'Run blackceo-council with no arguments to see the command list.',
    exitCode: 2,
  });
}

export function invalidInput(message: string): CouncilError {
  return new CouncilError('COUNCIL_INVALID_INPUT', message, {
    retryable: false,
    action: 'Correct the input and try again.',
    exitCode: 2,
  });
}

export function isCouncilError(value: unknown): value is CouncilError {
  return value instanceof CouncilError;
}
