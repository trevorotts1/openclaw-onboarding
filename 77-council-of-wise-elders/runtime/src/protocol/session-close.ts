/**
 * Session-close protocol (W74-A).
 *
 * A council sitting is one session, and every sitting closes; a
 * sitting never hangs open. The contract, in full:
 *
 * - Five minutes after the last client interaction in an open session,
 *   the council sends ONE soft-close question
 *   (SOFT_CLOSE_QUESTION). One per quiet spell: a client answer is a
 *   new interaction and restarts the five-minute quiet clock.
 * - An explicit close phrase (CLOSE_PHRASES, e.g. "that's all",
 *   "we're done", "finalize") finalizes immediately — no question.
 * - Ten minutes of silence after the soft-close question
 *   auto-finalizes. The session is never left open.
 * - Finalize = mark the session closed in the store, hand the session
 *   record to the artifact renderer's `renderArtifact(sessionRecord)`
 *   (the W74-B entry point, called by export name; returns
 *   `{ path, link }`), and the caller emits the artifact link in the
 *   reply.
 *
 * Bound state (rule 6): at most one active session per client stays
 * ("resolve existing sessions first, never create a duplicate" is
 * unchanged), and the close timers are RESUMABLE: no state lives in
 * memory. Everything is derived from store timestamps — the last
 * journal event on the session and the durable close marker written to
 * the projection outbox — so a service restart continues the same
 * quiet spell and can never send a second soft-close question.
 */

import { canTransition } from '../contracts/state-machine.js';
import type { CouncilCard, Verdict } from '../contracts/index.js';
import type { StoredSession } from '../cli/host-ports.js';
import {
  RenderInputError,
  assembleRenderRecord,
  type RenderExtras,
  type RenderSessionRecord,
} from '../reports/artifact-renderer.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import { ProtocolError } from './errors.js';

/** The session record at the render seam: the stored session as-is, or the assembled render record. */
export type RenderableSession = StoredSession | RenderSessionRecord;

/** Quiet time after the last client interaction before the soft close. */
export const SOFT_CLOSE_IDLE_MS = 5 * 60 * 1000;
/** Silence after the soft-close question before auto-finalize. */
export const AUTO_FINALIZE_SILENCE_MS = 10 * 60 * 1000;
export const SOFT_CLOSE_QUESTION = 'Is that all, or are we still working?';

/**
 * Explicit close phrases. Matched after normalization (lowercase,
 * apostrophes and punctuation stripped, whitespace collapsed): the
 * message equals one of these, or ends with one as its final clause.
 */
export const CLOSE_PHRASES = [
  "that's all",
  'that is all',
  'thats all',
  "that's it",
  'that is it',
  'thats it',
  "we're done",
  'we are done',
  'were done',
  "we're finished",
  'we are finished',
  'finalize',
  'finalise',
  'all done',
  'close it',
  'close the session',
  'wrap it up',
  'wrap up',
  "that's all for now",
] as const;

export function normalizeCloseText(text: string): string {
  return text
    .toLowerCase()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** True when the message is an explicit close phrase. */
export function isClosePhrase(text: string): boolean {
  const normalized = normalizeCloseText(text);
  if (normalized.length === 0) return false;
  for (const phrase of CLOSE_PHRASES) {
    const needle = normalizeCloseText(phrase);
    if (normalized === needle || normalized.endsWith(` ${needle}`)) return true;
  }
  return false;
}

export type CloseReason = 'client_close_phrase' | 'auto_finalize';

/** Durable close state, as derived from the store. */
export interface SessionCloseMarker {
  /** Created-at of the latest soft-close question, or null. */
  soft_close_sent_at: string | null;
  /** Closed-at of the finalize, or null while open. */
  closed_at: string | null;
  close_reason: CloseReason | null;
}

/** The store facts the close state derives from — never timers. */
export interface SessionCloseSnapshot {
  /** Timestamp of the last journal event on the session (the last client interaction). */
  last_event_at: string | null;
  marker: SessionCloseMarker;
}

export type CloseAction =
  | { action: 'none'; due_in_ms: number | null }
  | { action: 'send_soft_close'; question: typeof SOFT_CLOSE_QUESTION }
  | { action: 'auto_finalize' };

/**
 * Pure derivation of the close action from store timestamps. Restart
 * safe by construction: the same snapshot and clock always produce the
 * same action, whatever process reads them.
 */
export function deriveCloseAction(snapshot: SessionCloseSnapshot, nowIso: string): CloseAction {
  const now = Date.parse(nowIso);
  const { marker } = snapshot;
  if (marker.closed_at !== null) return { action: 'none', due_in_ms: null };

  // A client interaction after the soft-close question supersedes it:
  // the sitting continues and a later quiet spell earns a fresh
  // question. The marker itself is kept; only its authority lapses.
  let softCloseAt: number | null = null;
  if (marker.soft_close_sent_at !== null) {
    const sent = Date.parse(marker.soft_close_sent_at);
    const lastEvent = snapshot.last_event_at === null ? null : Date.parse(snapshot.last_event_at);
    if (lastEvent === null || lastEvent <= sent) softCloseAt = sent;
  }

  if (softCloseAt !== null) {
    const silence = now - softCloseAt;
    if (silence >= AUTO_FINALIZE_SILENCE_MS) return { action: 'auto_finalize' };
    return { action: 'none', due_in_ms: AUTO_FINALIZE_SILENCE_MS - silence };
  }

  if (snapshot.last_event_at === null) return { action: 'none', due_in_ms: null };
  const idle = now - Date.parse(snapshot.last_event_at);
  if (idle >= SOFT_CLOSE_IDLE_MS) return { action: 'send_soft_close', question: SOFT_CLOSE_QUESTION };
  return { action: 'none', due_in_ms: SOFT_CLOSE_IDLE_MS - idle };
}

/** The W74-B renderer contract: one call, artifact path plus link. */
export interface ArtifactRenderResult {
  path: string;
  link: string;
}
export type RenderArtifactFn = (
  sessionRecord: RenderableSession,
) => ArtifactRenderResult | Promise<ArtifactRenderResult>;

/**
 * Resolve the W74-B renderer entry point BY EXPORT NAME: the first
 * candidate module exporting a function named `renderArtifact` wins.
 * Absent modules are skipped; a module without that export is skipped
 * too, so a partially-landed renderer never breaks finalize.
 */
export async function resolveRenderArtifact(): Promise<RenderArtifactFn | null> {
  const candidates = [
    '../reports/artifact-renderer.js',
    '../reports/render-artifact.js',
    '../reports/artifact-render.js',
    '../artifacts/render-artifact.js',
    './artifact-renderer.js',
  ];
  for (const specifier of candidates) {
    try {
      const mod: Record<string, unknown> = await import(specifier);
      const fn = mod['renderArtifact'];
      if (typeof fn === 'function') return fn as RenderArtifactFn;
    } catch {
      // Candidate module not present; try the next one.
    }
  }
  return null;
}

/** The durable store surface the close protocol reads and writes. */
export interface SessionClosePort {
  /** Timestamp of the session's last journal event, or null. */
  lastEventAt(sessionId: string): string | null;
  readMarker(sessionId: string): SessionCloseMarker;
  /** Record the soft-close question; idempotent per quiet spell. */
  recordSoftClose(sessionId: string, sentAt: string): void;
  /** Record a client interaction (non-close) as the session's newest event. */
  recordClientInteraction(sessionId: string, at: string): void;
  /** Mark the session closed in the store; idempotent. */
  markClosed(sessionId: string, closedAt: string, reason: CloseReason): void;
  /** The session record finalize hands to renderArtifact: stored session or assembled render record. */
  sessionRecord(sessionId: string): RenderableSession | null;
}

export interface FinalizeResult {
  session_id: string;
  closed: true;
  close_reason: CloseReason;
  artifact: ArtifactRenderResult | null;
  render_error: string | null;
}

export interface TickResult {
  action: CloseAction['action'];
  question?: typeof SOFT_CLOSE_QUESTION;
  finalized?: FinalizeResult;
}

export class SessionCloseService {
  constructor(
    private readonly deps: {
      port: SessionClosePort;
      /** W74-B renderer; resolved by export name on first finalize when omitted. */
      renderArtifact?: RenderArtifactFn;
    },
  ) {}

  private snapshot(sessionId: string): SessionCloseSnapshot {
    return {
      last_event_at: this.deps.port.lastEventAt(sessionId),
      marker: this.deps.port.readMarker(sessionId),
    };
  }

  /** Pure read of the derived close state for one session. */
  status(sessionId: string, nowIso: string): CloseAction {
    return deriveCloseAction(this.snapshot(sessionId), nowIso);
  }

  /**
   * Evaluate one session against the store clock. Sends the ONE
   * soft-close question when the quiet spell is old enough, and
   * auto-finalizes after the ten quiet minutes. Callable at any
   * cadence and after any restart: nothing here is a timer.
   */
  async tick(sessionId: string, nowIso: string): Promise<TickResult> {
    const action = this.status(sessionId, nowIso);
    if (action.action === 'send_soft_close') {
      this.deps.port.recordSoftClose(sessionId, nowIso);
      return { action: 'send_soft_close', question: SOFT_CLOSE_QUESTION };
    }
    if (action.action === 'auto_finalize') {
      const finalized = await this.finalize(sessionId, 'auto_finalize', nowIso);
      return { action: 'auto_finalize', finalized };
    }
    return { action: 'none' };
  }

  /**
   * A client message. An explicit close phrase finalizes NOW;
   * anything else is an interaction that restarts the quiet clock.
   */
  async handleClientMessage(
    sessionId: string,
    text: string,
    nowIso: string,
  ): Promise<{ finalized: FinalizeResult | null }> {
    if (isClosePhrase(text)) {
      return { finalized: await this.finalize(sessionId, 'client_close_phrase', nowIso) };
    }
    this.deps.port.recordClientInteraction(sessionId, nowIso);
    return { finalized: null };
  }

  /**
   * Finalize a sitting: mark the session closed in the store, render
   * the counsel artifact through W74-B's `renderArtifact`, and hand
   * back path+link for the reply. Idempotent: an already-closed
   * session is not re-rendered and not re-marked.
   */
  async finalize(sessionId: string, reason: CloseReason, nowIso: string): Promise<FinalizeResult> {
    // The close port assembles the render record from the store's own
    // rows. A session whose sitting recorded no renderer rows (no seat
    // takes, no verdict) surfaces the typed RenderInputError here: the
    // sitting still closes (never hangs open), the typed state is
    // reported through render_error, and nothing is invented.
    let record: RenderableSession | null = null;
    let recordError: RenderInputError | null = null;
    try {
      record = this.deps.port.sessionRecord(sessionId);
    } catch (error) {
      if (error instanceof RenderInputError) {
        recordError = error;
      } else {
        throw error;
      }
    }
    if (record === null && recordError === null) {
      throw new ProtocolError('SESSION_NOT_FOUND', `Session ${sessionId} was not found.`, {
        session_id: sessionId,
      });
    }
    const prior = this.deps.port.readMarker(sessionId);
    if (prior.closed_at !== null) {
      return {
        session_id: sessionId,
        closed: true,
        close_reason: prior.close_reason ?? reason,
        artifact: null,
        render_error: null,
      };
    }
    this.deps.port.markClosed(sessionId, nowIso, reason);
    if (recordError !== null) {
      return {
        session_id: sessionId,
        closed: true,
        close_reason: reason,
        artifact: null,
        render_error: `${recordError.code}: ${recordError.message}`,
      };
    }
    if (record === null) {
      // Unreachable: a missing record threw SESSION_NOT_FOUND above and a
      // store-assembly failure returned the typed state just above. If the
      // port ever yields neither, report it — never render a null.
      return {
        session_id: sessionId,
        closed: true,
        close_reason: reason,
        artifact: null,
        render_error: 'RENDER_INPUT_INCOMPLETE: the close port produced no session record.',
      };
    }
    const render = this.deps.renderArtifact ?? (await resolveRenderArtifact());
    if (!render) {
      return {
        session_id: sessionId,
        closed: true,
        close_reason: reason,
        artifact: null,
        render_error: 'RENDERER_UNAVAILABLE',
      };
    }
    try {
      const artifact = await render(record);
      return {
        session_id: sessionId,
        closed: true,
        close_reason: reason,
        artifact,
        render_error: null,
      };
    } catch (error) {
      // The session is closed either way; a render failure is reported
      // and never reopens or re-marks the sitting. A bare record with no
      // extras surfaces as the typed state, never a bare TypeError.
      return {
        session_id: sessionId,
        closed: true,
        close_reason: reason,
        artifact: null,
        render_error:
          error instanceof RenderInputError
            ? `${error.code}: ${error.message}`
            : error instanceof Error
              ? error.message
              : 'RENDER_FAILED',
      };
    }
  }
}

// ------------------------------------------------- canonical store port

const SOFT_CLOSE_TOPIC = 'session_soft_close';
const SESSION_CLOSE_TOPIC = 'session_close';

/**
 * Honest placeholder for the one renderer row the store cannot derive by
 * construction: the store is client-name-free (the repo ships no client
 * names; a client name enters only as runtime data through the door
 * that knows the client). The default store-backed close path renders
 * the sitting the STORE can account for and says exactly this in the
 * header, rather than fabricating a client identity or bypassing the
 * privacy boundary to guess one.
 */
export const CLIENT_NAME_UNRECORDED = 'Client name not recorded for this sitting';

/**
 * The seat take the store's own card rows carry: the advisor's change-my-mind
 * threshold for the recorded card (ratification cards carry no take; consult
 * cards carry their answer). Derived, never invented.
 */
function cardTake(card: CouncilCard): string | null {
  if (card.card_kind === 'advisor') return card.change_my_mind;
  if (card.card_kind === 'consult') return card.answer;
  return null;
}

/**
 * The consensus line the store's own verdict row carries. Scored verdicts
 * state their label and main reasons; consult results state their answer
 * and next step. Derived, never invented.
 */
function verdictConsensus(verdict: Verdict): string {
  if (verdict.result_kind === 'scored') {
    const reasons = verdict.main_reasons.join(' ');
    return reasons.length > 0
      ? `${verdict.label}: ${reasons}`
      : `${verdict.label}.`;
  }
  return `Consult: ${verdict.consult_card.answer}`;
}

/**
 * The action steps the store's own verdict row carries. Scored verdicts
 * carry action proposals (title plus description) and prerequisites;
 * consult results carry their next step. Derived, never invented.
 */
function verdictActionSteps(verdict: Verdict): string[] {
  if (verdict.result_kind === 'scored') {
    const steps = verdict.action_proposals.map(
      (proposal) => `${proposal.title}: ${proposal.description}`,
    );
    return [...steps, ...verdict.prerequisites];
  }
  return [verdict.next_step];
}

/**
 * The store-backed close port's half of the close-to-render contract.
 * When the store carries the sitting's own card and verdict rows, this
 * assembles the renderer's record from them (the DEFAULT close path).
 * When it does not — the explicit conveneFlow path runs deliberation
 * live and supplies its own runtime rows — it returns the bare
 * StoredSession so the caller's extras seam assembles the record. It
 * never fabricates takes, a verdict, or a client identity, and never
 * crosses the privacy boundary; a bare record with no extras surfaces
 * the typed `RenderInputError` at the renderer's own trust boundary.
 */
export function assembleStoreRenderRecord(
  repositories: CouncilRepositories,
  envelope: AuthorizationEnvelope,
  session: StoredSession,
): RenderSessionRecord | StoredSession {
  const cards = repositories.listCards(envelope, session.spec.session_id);
  const withTakes: RenderExtras['cards'] = [];
  for (const card of cards) {
    const take = cardTake(card);
    if (typeof take === 'string' && take.length > 0) {
      withTakes.push({ seat_id: card.seat_id, take });
    }
  }
  const verdict = repositories.getVerdict(envelope, session.spec.session_id);
  if (withTakes.length === 0 || verdict === null) {
    // The store's own rows are not present yet: the caller's runtime
    // rows (the explicit conveneFlow path) assemble the record instead.
    return session;
  }
  const extras: RenderExtras = {
    client_name: CLIENT_NAME_UNRECORDED,
    model_used: session.spec.model_policy.requested_model_id
      ?? session.spec.model_policy.route_id,
    question_count: cards.length,
    cards: withTakes,
    verdict: {
      consensus: verdictConsensus(verdict),
      action_steps: verdictActionSteps(verdict),
    },
  };
  return assembleRenderRecord(session, extras);
}

/**
 * The close port over the canonical CWE-006 store. The close marker
 * lives in the projection outbox as durable intents (idempotent per
 * quiet spell / per session), and the last interaction timestamp is
 * the newest journal event — so every derivation input is in the store
 * and survives a restart.
 */
export function storeSessionClosePort(
  repositories: CouncilRepositories,
  envelope: AuthorizationEnvelope,
  deps: { newId: () => string },
): SessionClosePort {
  function episodeKey(sessionId: string): string {
    const events = repositories.journal.list(envelope, sessionId, 0);
    const last = events[events.length - 1];
    return last ? `${last.sequence}:${last.created_at}` : 'none';
  }

  return {
    lastEventAt(sessionId) {
      const events = repositories.journal.list(envelope, sessionId, 0);
      return events.length > 0 ? events[events.length - 1].created_at : null;
    },

    readMarker(sessionId) {
      const intents = repositories.outbox.listForSession(envelope, sessionId);
      let soft_close_sent_at: string | null = null;
      let closed_at: string | null = null;
      let close_reason: CloseReason | null = null;
      for (const intent of intents) {
        if (intent.topic === SOFT_CLOSE_TOPIC && intent.session_id === sessionId) {
          soft_close_sent_at = intent.created_at;
        }
        if (intent.topic === SESSION_CLOSE_TOPIC && intent.session_id === sessionId) {
          closed_at = (intent.payload['closed_at'] as string | undefined) ?? intent.created_at;
          close_reason =
            intent.payload['close_reason'] === 'client_close_phrase' ||
            intent.payload['close_reason'] === 'auto_finalize'
              ? intent.payload['close_reason']
              : null;
        }
      }
      return { soft_close_sent_at, closed_at, close_reason };
    },

    recordSoftClose(sessionId, sentAt) {
      // Idempotent per quiet spell: the episode key is derived from the
      // last event, so a replay inside the same quiet spell (including
      // one after a restart) returns the existing intent and writes
      // nothing. The question is sent ONCE.
      repositories.enqueueOutboxIntent(envelope, {
        id: deps.newId(),
        session_id: sessionId,
        event_sequence: null,
        topic: SOFT_CLOSE_TOPIC,
        idempotency_key: `soft-close:${sessionId}:${episodeKey(sessionId)}`,
        payload: { question: SOFT_CLOSE_QUESTION, sent_at: sentAt },
        created_at: sentAt,
      });
    },

    recordClientInteraction(sessionId, at) {
      // A client interaction is a session event: the close state derives
      // from the last event timestamp, so the interaction must land in
      // the journal to restart the quiet clock. Same-state record write
      // through the canonical primitive; the event vocabulary is the
      // canonical enum.
      const session = repositories.getSession(envelope, sessionId);
      if (!session) {
        throw new ProtocolError('SESSION_NOT_FOUND', `Session ${sessionId} was not found.`, {
          session_id: sessionId,
        });
      }
      const current = session.state;
      repositories.writeStateRecord(
        envelope,
        { ...current, state_version: current.state_version + 1, updated_at: at },
        current.state_version,
        {
          type: 'session_state_changed',
          payload: { interaction: 'client_message', from_state: current.state, to_state: current.state },
        },
      );
    },

    markClosed(sessionId, closedAt, reason) {
      // Durable close first: the marker is the close protocol's
      // authoritative "closed" flag and survives any later failure.
      repositories.enqueueOutboxIntent(envelope, {
        id: deps.newId(),
        session_id: sessionId,
        event_sequence: null,
        topic: SESSION_CLOSE_TOPIC,
        idempotency_key: `close:${sessionId}`,
        payload: { closed_at: closedAt, close_reason: reason },
        created_at: closedAt,
      });
      // The canonical deliberation state machine keeps authority over
      // its own terminal states: advance to COMPLETED only when its
      // transition table permits. The close marker stands regardless.
      const session = repositories.getSession(envelope, sessionId);
      if (!session) return;
      const current = session.state;
      if (!canTransition(current.mode, current.state, 'COMPLETED')) return;
      try {
        repositories.transitionState(envelope, sessionId, 'COMPLETED', current.state_version);
      } catch {
        // A concurrent writer owns the transition; the close marker
        // already records the sitting as closed.
      }
    },

    sessionRecord(sessionId) {
      // The default store-backed close path must hand finalize the
      // ASSEMBLED render record (the stored session plus the store's
      // own card and verdict rows), never a bare StoredSession: the
      // renderer validates exactly those rows, and a bare record made
      // finalize dereference undefined extras (R1). The assembled
      // record is derived from the store, never guessed.
      const session = repositories.getSession(envelope, sessionId);
      if (session === null) return null;
      return assembleStoreRenderRecord(repositories, envelope, session);
    },
  };
}
