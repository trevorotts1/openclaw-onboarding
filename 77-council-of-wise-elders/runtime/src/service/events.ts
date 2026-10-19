/**
 * Front-door event-stream and session-reader adapters (W21-U001).
 *
 * The service slice owns the transport, never the durable source. These
 * are the INJECTION POINTS the composition root binds: an adapter over
 * the canonical `EventJournal` (CWE-006) for `text/event-stream`, and a
 * reader over the canonical repositories for `GET /council/<id>`.
 *
 * Nothing here opens a database, reads a credential or calls a network.
 * The factories take an already-composed source and translate its
 * committed rows into the wire shape the Command Center already speaks
 * (`id: <sequence>` / `event: <type>` / `data: <json>`), so there is one
 * event vocabulary, not a second backend and not a second task system.
 *
 * A frame is only ever a COMMITTED journal row. A read failure is
 * retried on the next poll from the same cursor; no frame is fabricated
 * to cover it, and an unknown session stays unknown.
 */

import type { StoredSession } from '../cli/host-ports.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type { JournalEvent } from '../persistence/journal.js';

/** One committed council event as served over SSE. */
export interface CouncilEventFrame {
  /** Per-session committed sequence; the SSE `id:` and the cursor. */
  sequence: number;
  type: string;
  [key: string]: unknown;
}

/**
 * One session's read cursor. `replay` returns committed frames after a
 * sequence; the optional `subscribe` follows newly committed frames and
 * returns its own detach function.
 */
export interface CouncilEventCursor {
  replay(
    afterSequence: number,
  ): readonly CouncilEventFrame[] | Promise<readonly CouncilEventFrame[]>;
  subscribe?(onFrame: (frame: CouncilEventFrame) => void): () => void;
}

/** The durable source the integration root binds to the front door. */
export interface CouncilEventStreamAdapter {
  /** Null means this source does not know the session (the route 404s). */
  open(
    sessionId: string,
  ): CouncilEventCursor | null | Promise<CouncilEventCursor | null>;
}

/** One durable session as served at `GET /council/<id>`. */
export interface CouncilSessionRecord {
  session_id: string;
  authority?: 'standalone' | 'managed';
  [key: string]: unknown;
}

/** The session source the integration root binds to the front door. */
export interface CouncilSessionReader {
  /** Null means the store does not know the session (the route 404s). */
  read(
    sessionId: string,
  ): CouncilSessionRecord | null | Promise<CouncilSessionRecord | null>;
}

/** The exact JournalEvent list surface; a fake is enough for tests. */
export interface JournalEventStreamSource {
  list(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    afterSequence?: number,
  ): JournalEvent[];
}

/** The exact repository session surface; a fake is enough for tests. */
export interface CouncilSessionSource {
  getSession(envelope: AuthorizationEnvelope, sessionId: string): StoredSession | null;
}

/** Map one canonical journal row to the served frame. */
export function toCouncilEventFrame(event: JournalEvent): CouncilEventFrame {
  return {
    sequence: event.sequence,
    type: event.type,
    event_id: event.event_id,
    from_state: event.from_state,
    to_state: event.to_state,
    actor_subject: event.actor_subject,
    payload: event.payload,
    prev_hash: event.prev_hash,
    event_hash: event.event_hash,
    created_at: event.created_at,
  };
}

/**
 * The accepted SSE wire format (Command Center CWE-030): the frame id is
 * the committed sequence, the event name is the committed type, and the
 * data line is the whole frame. Reused verbatim; no second vocabulary.
 */
export function formatCouncilEventFrame(frame: CouncilEventFrame): string {
  return `id: ${frame.sequence}\nevent: ${frame.type}\ndata: ${JSON.stringify(frame)}\n\n`;
}

/**
 * Adapter over the canonical journal. Replay and follow both read the
 * durable rows under the supplied envelope; a failed poll leaves the
 * cursor untouched and the next tick retries.
 */
export function journalEventStreamAdapter(options: {
  journal: JournalEventStreamSource;
  envelope: AuthorizationEnvelope;
  /** Follow interval; default 500 ms (CWE-030 stream cadence). */
  poll_ms?: number;
}): CouncilEventStreamAdapter {
  const pollMs = options.poll_ms ?? 500;
  return {
    open(sessionId: string): CouncilEventCursor {
      let cursor = 0;
      return {
        replay(afterSequence: number): readonly CouncilEventFrame[] {
          const after = Math.max(0, Math.floor(afterSequence));
          const events = options.journal.list(options.envelope, sessionId, after);
          if (events.length > 0) cursor = events[events.length - 1].sequence;
          return events.map(toCouncilEventFrame);
        },
        subscribe(onFrame: (frame: CouncilEventFrame) => void): () => void {
          let stopped = false;
          const timer: ReturnType<typeof setInterval> = setInterval(() => {
            if (stopped) return;
            try {
              const events = options.journal.list(options.envelope, sessionId, cursor);
              for (const event of events) {
                cursor = event.sequence;
                onFrame(toCouncilEventFrame(event));
              }
            } catch {
              // Durable journal: retry from the same cursor next tick.
            }
          }, pollMs);
          timer.unref?.();
          return () => {
            stopped = true;
            clearInterval(timer);
          };
        },
      };
    },
  };
}

/**
 * Reader over the canonical repositories. `getSession` already answers
 * null for an id that is absent, out of scope or not visible to the
 * envelope — the route turns that into a truthful 404 instead of the
 * unconditional `ui: "not_bundled"` page.
 */
export function repositorySessionReader(options: {
  repositories: CouncilSessionSource;
  envelope: AuthorizationEnvelope;
}): CouncilSessionReader {
  return {
    read(sessionId: string): CouncilSessionRecord | null {
      const session = options.repositories.getSession(options.envelope, sessionId);
      if (session === null) return null;
      return {
        session_id: session.spec.session_id,
        authority: 'standalone',
        spec: session.spec,
        brief: session.brief,
        scope: session.scope,
        state: session.state,
        sample: session.sample,
      };
    },
  };
}
