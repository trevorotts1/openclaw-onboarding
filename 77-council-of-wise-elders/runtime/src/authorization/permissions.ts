/**
 * CWE-007 trusted authorization ports: permission kinds, the four
 * separate authorizations, machine-client binding, and the query
 * credential guard (directive Sections 1.2, 17.1, 17.5, 28.2).
 */
import type { AuthorizationKind } from '../contracts/index.js';
import {
  AuthorizationError,
  type AccessDecision,
  type TrustedPrincipal,
} from './scope.js';

/**
 * The permission vocabulary downstream units check (CWE-007 prose build
 * step 2). 'run', 'read', 'evidence', and 'export' are session
 * operations; 'approve_plan', 'create_tasks', and 'execute' act on the
 * world outside the session and therefore sit behind their own
 * authorization kinds below.
 */
export type CouncilPermission =
  | 'run'
  | 'read'
  | 'evidence'
  | 'export'
  | 'approve_plan'
  | 'create_tasks'
  | 'execute'
  | 'diagnostic_capture';

/**
 * Which of the four separate authorizations a permission requires
 * (Section 1.2). build, council_run, action_plan_approval, and execution
 * are never interchangeable: a council_run grant does not approve a plan,
 * and no council outcome is an execution credential. Read-family
 * permissions map to null because they are governed by the scope and
 * visibility decisions in scope.ts, not by a grant kind.
 */
export const AUTHORIZATION_KIND_FOR_PERMISSION: Readonly<
  Record<CouncilPermission, AuthorizationKind | null>
> = {
  run: 'council_run',
  approve_plan: 'action_plan_approval',
  create_tasks: 'action_plan_approval',
  execute: 'execution',
  read: null,
  evidence: null,
  export: null,
  diagnostic_capture: null,
};

export function authorizationKindForPermission(
  permission: CouncilPermission,
): AuthorizationKind | null {
  return AUTHORIZATION_KIND_FOR_PERMISSION[permission];
}

/**
 * A machine client's approved binding (Section 17.1): the pairing or
 * bearer mechanism admits the client to exactly one installation and
 * company, a fixed set of operations, and optionally one session.
 */
export interface MachineBinding {
  readonly installation_id: string;
  readonly company_id: string;
  readonly operations: readonly CouncilPermission[];
  readonly session_id?: string | null;
}

/**
 * Machine-binding check (T077). Fails unless the principal arrived on the
 * machine channel, its trusted scope equals the binding's installation
 * and company, the operation is inside the binding's operation set, and
 * a session-pinned binding is used only for that session. A browser or
 * local-owner principal can never satisfy a machine binding, and a
 * machine principal gains nothing beyond its binding.
 */
export function checkMachineBinding(
  principal: TrustedPrincipal,
  binding: MachineBinding,
  operation: CouncilPermission,
  sessionId?: string | null,
): AccessDecision {
  const fail = (message: string): AccessDecision => ({
    allowed: false,
    code: 'COUNCIL_MACHINE_BINDING',
    message,
  });
  if (principal.channel !== 'machine') {
    return fail('Machine operations require a machine-bound principal.');
  }
  if (principal.installation_id !== binding.installation_id) {
    return fail('Principal is not bound to this installation.');
  }
  if (principal.company_id !== binding.company_id) {
    return fail('Principal is not bound to this company.');
  }
  if (!binding.operations.includes(operation)) {
    return fail(`Operation ${operation} is outside this machine binding.`);
  }
  if (
    binding.session_id !== undefined &&
    binding.session_id !== null &&
    binding.session_id !== sessionId
  ) {
    return fail('Machine binding is pinned to a different session.');
  }
  // A binding decision is not a session visibility grant; report the
  // generic 'company' channel since the binding is company-scoped.
  return { allowed: true, via: 'company' };
}

/** Throwing form of checkMachineBinding. */
export function assertMachineBinding(
  principal: TrustedPrincipal,
  binding: MachineBinding,
  operation: CouncilPermission,
  sessionId?: string | null,
): void {
  const decision = checkMachineBinding(principal, binding, operation, sessionId);
  if (!decision.allowed) {
    throw new AuthorizationError(decision.code, decision.message);
  }
}

/**
 * Query parameter names that would carry a credential (Section 17.1: API
 * keys and tokens never appear in URL query parameters). Council
 * surfaces reject any request carrying one of these names, regardless of
 * value, so a credential can never leak through a logged URL.
 */
export const QUERY_CREDENTIAL_PARAMETERS: ReadonlySet<string> = new Set([
  'api_key',
  'apikey',
  'api-key',
  'access_token',
  'token',
  'key',
  'secret',
  'password',
  'auth',
  'bearer',
]);

/** Returns the offending parameter name (never its value), or null. */
export function findQueryCredentialParameter(
  parameterNames: Iterable<string>,
): string | null {
  for (const name of parameterNames) {
    if (QUERY_CREDENTIAL_PARAMETERS.has(name.toLowerCase())) return name;
  }
  return null;
}

/** Throws COUNCIL_QUERY_CREDENTIAL naming the parameter, never its value. */
export function assertNoQueryCredentialParameter(
  parameterNames: Iterable<string>,
): void {
  const offender = findQueryCredentialParameter(parameterNames);
  if (offender !== null) {
    throw new AuthorizationError(
      'COUNCIL_QUERY_CREDENTIAL',
      `Credentials are not accepted in URL query parameters (${offender}).`,
      400,
    );
  }
}
