/**
 * Session controls (CWE-050; directive Sections 15.4, 17.5, 19):
 * pause, resume, cancel, and archive over the accepted stores and
 * services. The control mechanics themselves are CWE-027's
 * (DurableJobRunner.pauseSession / resumeSession / cancelSession:
 * idempotent at the target state, precise legal-state conflicts,
 * cancellation generation fencing, budget and capacity release). This
 * service adds the protocol surface around them:
 *
 * - Expected-version checks (T058's portable half): a caller holding
 *   a stale state version gets a precise conflict naming both
 *   versions BEFORE anything moves, so a stale writer can never
 *   overwrite a newer transition.
 * - Idempotency keys (T078): a control call may carry a request key.
 *   The first claim wins; a replay with the same payload returns the
 *   recorded outcome without re-executing; the same key with a
 *   different payload is a conflict and changes nothing. Claims ride
 *   CWE-006's council_request_keys via repositories.claimRequestKey.
 * - Repeated controls are idempotent (T055): pausing a paused session
 *   and cancelling a cancelled session return the current record;
 *   resuming a session that is not paused or blocked is a precise
 *   legal-state conflict, never a silent no-op success.
 *
 * Archive is a visibility flag, not a state change (CWE-006
 * setArchived); archived sessions stay readable to their scope.
 */

import { canonicalHash } from '../contracts/index.js';
import type { SessionStateRecord } from '../contracts/index.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import type { DurableJobRunner } from '../queue/runner.js';
import { ProtocolError } from './errors.js';

export type SessionControlAction = 'pause' | 'resume' | 'cancel';

export interface SessionControlRequest {
  action: SessionControlAction;
  /** Caller's view of the state version; stale values conflict (T058). */
  expected_version?: number;
  /** Idempotency key for this control call (T078). */
  request_key?: string;
}

export interface SessionControlResult {
  action: SessionControlAction;
  session_id: string;
  record: SessionStateRecord;
  /** True when the idempotency key replayed a recorded outcome. */
  replayed: boolean;
}

export class SessionControlsService {
  constructor(
    private readonly deps: {
      repositories: CouncilRepositories;
      runner: DurableJobRunner;
    },
  ) {}

  control(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    request: SessionControlRequest,
  ): SessionControlResult {
    const session = this.deps.repositories.getSession(envelope, sessionId);
    if (!session) {
      throw new ProtocolError('SESSION_NOT_FOUND', `Session ${sessionId} was not found.`, {
        session_id: sessionId,
      });
    }

    // Idempotency is resolved BEFORE the optimistic-version check
    // (T078): a repeat of a keyed request returns its recorded
    // outcome even though the session has since moved on, and the
    // same key carrying a changed payload (including a changed
    // expected version) is an idempotency conflict, never a stale
    // write.
    if (request.request_key) {
      const claim = this.deps.repositories.claimRequestKey({
        tenantId: envelope.tenant_id,
        source: 'protocol-session-controls',
        operation: request.action,
        requestKey: request.request_key,
        payloadFingerprint: canonicalHash({
          session_id: sessionId,
          action: request.action,
          expected_version: request.expected_version ?? null,
        }),
        sessionId,
      });
      if (claim.outcome === 'conflict') {
        throw new ProtocolError(
          'IDEMPOTENCY_CONFLICT',
          `Idempotency key ${request.request_key} was already used for ${request.action} with a different payload.`,
          { session_id: sessionId, request_key: request.request_key },
        );
      }
      if (claim.outcome === 'replay') {
        // The control already ran under this key: return the current
        // record as the recorded outcome, executing nothing again.
        const current = this.deps.repositories.getSession(envelope, sessionId);
        return {
          action: request.action,
          session_id: sessionId,
          record: current!.state,
          replayed: true,
        };
      }
    }

    if (
      request.expected_version !== undefined &&
      request.expected_version !== session.state.state_version
    ) {
      throw new ProtocolError(
        'SESSION_STATE_CONFLICT',
        `Session ${sessionId} is at state version ${session.state.state_version}; the caller expected ${request.expected_version}. A stale control cannot overwrite a newer transition.`,
        {
          session_id: sessionId,
          expected_version: request.expected_version,
          current_version: session.state.state_version,
          current_state: session.state.state,
        },
      );
    }

    const record =
      request.action === 'pause'
        ? this.deps.runner.pauseSession(envelope, sessionId)
        : request.action === 'resume'
          ? this.deps.runner.resumeSession(envelope, sessionId)
          : this.deps.runner.cancelSession(envelope, sessionId);
    return { action: request.action, session_id: sessionId, record, replayed: false };
  }

  pause(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    options: Omit<SessionControlRequest, 'action'> = {},
  ): SessionControlResult {
    return this.control(envelope, sessionId, { ...options, action: 'pause' });
  }

  resume(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    options: Omit<SessionControlRequest, 'action'> = {},
  ): SessionControlResult {
    return this.control(envelope, sessionId, { ...options, action: 'resume' });
  }

  cancel(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    options: Omit<SessionControlRequest, 'action'> = {},
  ): SessionControlResult {
    return this.control(envelope, sessionId, { ...options, action: 'cancel' });
  }

  /** Archive or unarchive: a visibility flag, never a state change. */
  setArchived(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    archived: boolean,
  ): void {
    const session = this.deps.repositories.getSession(envelope, sessionId);
    if (!session) {
      throw new ProtocolError('SESSION_NOT_FOUND', `Session ${sessionId} was not found.`, {
        session_id: sessionId,
      });
    }
    this.deps.repositories.setArchived(envelope, sessionId, archived);
  }
}
