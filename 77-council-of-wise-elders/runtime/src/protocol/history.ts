/**
 * Session history (CWE-050; directive Sections 17.5, 18, 19): the
 * read side of the council. Lists and detail over the accepted
 * CWE-006 store: session summaries, one session's full record (spec,
 * frozen brief, state, committed cards, verdict), and the session's
 * hash-chained event journal in committed order.
 *
 * Read discipline (T076's portable half): history reads NEVER create
 * inference, jobs, or tasks. Every read is scope-checked through the
 * repositories (an out-of-scope session is indistinguishable from a
 * missing one), and event reads verify session visibility before the
 * journal is touched.
 */

import type {
  CouncilCard,
  SessionState,
  Verdict,
} from '../contracts/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type { JournalEvent } from '../persistence/journal.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import { ProtocolError } from './errors.js';

export interface SessionSummary {
  session_id: string;
  mode: StoredSession['spec']['mode'];
  visibility: StoredSession['spec']['visibility'];
  state: SessionState;
  state_version: number;
  brief_revision: number;
  seat_count: number;
  archived: boolean;
  updated_at: string;
}

export interface SessionDetail {
  session: StoredSession;
  cards: CouncilCard[];
  verdict: Verdict | null;
}

export class SessionHistoryService {
  constructor(private readonly deps: { repositories: CouncilRepositories }) {}

  listSessions(
    envelope: AuthorizationEnvelope,
    options: { includeArchived?: boolean; state?: SessionState } = {},
  ): SessionSummary[] {
    return this.deps.repositories
      .listSessions(envelope, options)
      .map((session) => ({
        session_id: session.spec.session_id,
        mode: session.spec.mode,
        visibility: session.spec.visibility,
        state: session.state.state,
        state_version: session.state.state_version,
        brief_revision: session.state.brief_revision,
        seat_count: session.spec.seat_ids.length,
        archived: session.state.archived,
        updated_at: session.state.updated_at,
      }));
  }

  getSession(envelope: AuthorizationEnvelope, sessionId: string): SessionDetail {
    const session = this.deps.repositories.getSession(envelope, sessionId);
    if (!session) {
      throw new ProtocolError('SESSION_NOT_FOUND', `Session ${sessionId} was not found.`, {
        session_id: sessionId,
      });
    }
    return {
      session,
      cards: this.deps.repositories.listCards(envelope, sessionId),
      verdict: this.deps.repositories.getVerdict(envelope, sessionId),
    };
  }

  /**
   * The session's event journal after a sequence cursor (replay
   * order). Visibility is verified through the repositories before
   * any journal row is read.
   */
  listEvents(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    afterSequence = 0,
  ): JournalEvent[] {
    const session = this.deps.repositories.getSession(envelope, sessionId);
    if (!session) {
      throw new ProtocolError('SESSION_NOT_FOUND', `Session ${sessionId} was not found.`, {
        session_id: sessionId,
      });
    }
    return this.deps.repositories.journal.list(envelope, sessionId, afterSequence);
  }
}
