/**
 * CWE-022 composition with the CWE-006 scoped store.
 *
 * The store is the source of the session's frozen brief, spec, and
 * trusted scope. Its reads are already envelope-scoped (CWE-006: a read
 * outside the envelope scope resolves to nothing, so "does not exist"
 * and "not yours" are indistinguishable). This helper loads the stored
 * session through the CouncilStore port and hands assembly the exact
 * inputs it needs: the frozen brief, the seat set and mode from the
 * frozen spec, and the session access target for the CWE-007 gate.
 * Authorization still runs inside assembleContext; loading a session
 * record is never itself an authorization decision.
 */
import type { CouncilStore } from '../cli/host-ports.js';
import type { DecisionBrief, SessionSpec } from '../contracts/index.js';
import {
  assembleContext,
  type AssembleContextRequest,
  type ContextAssemblyResult,
} from './assembly.js';
import { ContextError, type SessionAccessTarget } from './types.js';

export interface StoredSessionContextInputs {
  readonly spec: SessionSpec;
  readonly brief: DecisionBrief;
  readonly target: SessionAccessTarget;
}

export async function loadStoredSessionInputs(
  store: CouncilStore,
  sessionId: string,
): Promise<StoredSessionContextInputs | null> {
  const session = await store.getSession(sessionId);
  if (session === null) return null;
  return {
    spec: session.spec,
    brief: session.brief,
    target: { scope: session.scope, visibility: session.spec.visibility },
  };
}

/**
 * Assemble context for a session held in the scoped store. The
 * request's session and brief fields are filled from the stored record;
 * everything else (principal, operation, route, catalog) comes from the
 * caller. A session the store does not resolve in this envelope fails
 * with CONTEXT_SESSION_UNAVAILABLE, with no distinction between missing
 * and out-of-scope, mirroring the store's own rule.
 */
export async function assembleStoredSessionContext(
  store: CouncilStore,
  request: Omit<AssembleContextRequest, 'session' | 'brief'> & {
    readonly session_id: string;
  },
): Promise<ContextAssemblyResult> {
  const loaded = await loadStoredSessionInputs(store, request.session_id);
  if (loaded === null) {
    throw new ContextError(
      'CONTEXT_SESSION_UNAVAILABLE',
      'The session is not available in this scope.',
    );
  }
  return assembleContext({
    ...request,
    brief: loaded.brief,
    session: {
      ...loaded.target,
      session_id: request.session_id,
      mode: loaded.spec.mode,
      seat_ids: loaded.spec.seat_ids,
    },
  });
}
