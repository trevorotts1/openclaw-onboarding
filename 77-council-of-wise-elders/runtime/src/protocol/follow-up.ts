/**
 * Follow-up questions (CWE-050; directive Sections 17.5, 25.6): after
 * a council completes, the owner may put ONE follow-up question to ONE
 * seat. A follow-up is a discrete consult operation in a NEW linked
 * session, never a reopened deliberation and never a re-vote:
 *
 * - The child session is a consult (one seat, one ConsultCard, no
 *   scoring), created over the accepted CWE-006 store with the
 *   parent's frozen brief material carried over and the follow-up
 *   question in place of the original question.
 * - The link is recorded on the PARENT session's journal as an
 *   operation_completed event whose payload carries kind
 *   'follow_up_link' (the frozen CWE-003 vocabulary has no dedicated
 *   link event type; the payload-kind convention is the same one
 *   CWE-038 uses for report exports; the vocabulary is not forked).
 * - The follow-up runs under its OWN purpose-bound grant: the caller
 *   supplies a grant approved for purpose 'follow_up' (T142: purposes
 *   never borrow a council_run grant). Admission enforces the
 *   binding; this service never mints or widens a grant.
 */

import { canonicalHash, type SeatId, type Verdict } from '../contracts/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type { CouncilDatabase } from '../persistence/sqlite.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import type { PinnedRouteSnapshot } from '../budgets/route-snapshot.js';
import { ProtocolError } from './errors.js';

/** The composition's session driver, as a port (composition.ts). */
export interface FollowUpDriver {
  runSession(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    options: {
      grant_id: string;
      route_snapshot: PinnedRouteSnapshot;
      purpose?: string;
    },
  ): Promise<{ status: string; verdict?: Verdict | null }>;
}

export interface FollowUpLink {
  parent_session_id: string;
  follow_up_session_id: string;
  seat_id: SeatId;
  parent_verdict_revision: number | null;
}

export class FollowUpService {
  constructor(
    private readonly deps: {
      db: CouncilDatabase;
      repositories: CouncilRepositories;
      driver: FollowUpDriver;
      ids: { newId(): string };
      clock: { nowUtc(): string };
    },
  ) {}

  /**
   * Create the linked consult session for a follow-up (DRAFT state)
   * and record the link on the parent's journal. The caller then
   * previews and approves a follow_up-purpose grant FOR THE CHILD
   * SESSION (CWE-049) and runs it through the composition driver.
   */
  createFollowUp(
    envelope: AuthorizationEnvelope,
    parentSessionId: string,
    args: { seat_id: SeatId; question: string },
  ): FollowUpLink {
    const parent = this.deps.repositories.getSession(envelope, parentSessionId);
    if (!parent) {
      throw new ProtocolError(
        'SESSION_NOT_FOUND',
        `Session ${parentSessionId} was not found.`,
        { session_id: parentSessionId },
      );
    }
    if (parent.state.state !== 'COMPLETED') {
      throw new ProtocolError(
        'FOLLOW_UP_INVALID',
        `Follow-ups attach to a completed council; session ${parentSessionId} is ${parent.state.state}.`,
        { session_id: parentSessionId, state: parent.state.state },
      );
    }
    if (!parent.spec.seat_ids.includes(args.seat_id)) {
      throw new ProtocolError(
        'FOLLOW_UP_INVALID',
        `Seat ${args.seat_id} was not on the panel of session ${parentSessionId}.`,
        { session_id: parentSessionId, seat_id: args.seat_id },
      );
    }
    if (!args.question.trim()) {
      throw new ProtocolError('FOLLOW_UP_INVALID', 'A follow-up question is required.', {
        session_id: parentSessionId,
      });
    }
    const parentVerdict = this.deps.repositories.getVerdict(envelope, parentSessionId);

    const childSessionId = `follow-up-${this.deps.ids.newId()}`;
    const now = this.deps.clock.nowUtc();
    const childBrief = {
      ...parent.brief,
      brief_id: `brief-${childSessionId}`,
      session_id: childSessionId,
      revision: 1,
      question: args.question,
      created_at: now,
    };
    const childSpec = {
      ...parent.spec,
      session_id: childSessionId,
      mode: 'consult' as const,
      brief_revision: 1,
      brief_sha256: canonicalHash(childBrief),
      seat_ids: [args.seat_id],
      created_at: now,
    };
    const child: StoredSession = {
      spec: childSpec,
      brief: childBrief,
      scope: parent.scope,
      state: {
        schema_version: 'wise-elders.session-state/v1',
        session_id: childSessionId,
        mode: 'consult',
        state: 'DRAFT',
        state_version: 0,
        brief_revision: 1,
        resume_phase: null,
        cancel_generation: 0,
        revocation_generation: 0,
        attempt: 1,
        lease_epoch: 0,
        archived: false,
        updated_at: now,
      },
      sample: false,
    };
    this.deps.repositories.createSession(envelope, child);

    const link: FollowUpLink = {
      parent_session_id: parentSessionId,
      follow_up_session_id: childSessionId,
      seat_id: args.seat_id,
      parent_verdict_revision: parentVerdict?.verdict_revision ?? null,
    };
    this.deps.db.write((handle) =>
      this.deps.repositories.journal.append(handle, envelope, parentSessionId, {
        event_id: this.deps.ids.newId(),
        type: 'operation_completed',
        from_state: parent.state.state,
        to_state: parent.state.state,
        actor_subject: envelope.actor_subject,
        payload: { kind: 'follow_up_link', ...link },
        created_at: now,
      }),
    );
    return link;
  }

  /**
   * Create a follow-up, let the caller authorize the CHILD session
   * under a follow_up-purpose grant, and run it end to end. Returns
   * the child consult's verdict.
   */
  async askFollowUp(
    envelope: AuthorizationEnvelope,
    parentSessionId: string,
    args: {
      seat_id: SeatId;
      question: string;
      authorize: (
        followUpSessionId: string,
      ) => Promise<{ grant_id: string; route_snapshot: PinnedRouteSnapshot }> | {
        grant_id: string;
        route_snapshot: PinnedRouteSnapshot;
      };
    },
  ): Promise<{ link: FollowUpLink; verdict: Verdict }> {
    const link = this.createFollowUp(envelope, parentSessionId, args);
    const { grant_id, route_snapshot } = await args.authorize(link.follow_up_session_id);
    const run = await this.deps.driver.runSession(envelope, link.follow_up_session_id, {
      grant_id,
      route_snapshot,
      purpose: 'follow_up',
    });
    if (run.status !== 'completed' || !run.verdict) {
      throw new ProtocolError(
        'FOLLOW_UP_INVALID',
        `The follow-up consult did not complete (driver status: ${run.status}).`,
        { session_id: link.follow_up_session_id, status: run.status },
      );
    }
    return { link, verdict: run.verdict };
  }

  /** All follow-up links recorded on a session's journal, in order. */
  listFollowUps(
    envelope: AuthorizationEnvelope,
    parentSessionId: string,
  ): FollowUpLink[] {
    const parent = this.deps.repositories.getSession(envelope, parentSessionId);
    if (!parent) {
      throw new ProtocolError(
        'SESSION_NOT_FOUND',
        `Session ${parentSessionId} was not found.`,
        { session_id: parentSessionId },
      );
    }
    return this.deps.repositories
      .journal.list(envelope, parentSessionId, 0)
      .filter((event) => event.payload.kind === 'follow_up_link')
      .map((event) => ({
        parent_session_id: parentSessionId,
        follow_up_session_id: String(event.payload.follow_up_session_id),
        seat_id: event.payload.seat_id as SeatId,
        parent_verdict_revision:
          typeof event.payload.parent_verdict_revision === 'number'
            ? event.payload.parent_verdict_revision
            : null,
      }));
  }
}
