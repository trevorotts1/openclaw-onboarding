/**
 * The durable council event journal (CWE-006, directive Sections 16.2
 * and 18).
 *
 * Events are committed before they are displayed, in a strict per-
 * session sequence, and they form a hash chain: every event records
 * the previous event's hash, so a tampered, reordered, or silently
 * dropped event is detectable by re-walking the chain. The journal is
 * the durable record the live stream, replay, and state reconstruction
 * all read from; consumers deduplicate by event ID and sequence
 * (Section 18.2).
 *
 * Journal appends participate in the caller's transaction (the
 * repository's commit unit), so an event and the state, card, and
 * outbox writes it describes commit or roll back together (Section
 * 16.4). Sequence allocation reads the current maximum inside that
 * same transaction, so concurrent writers cannot interleave sequences.
 */

import {
  canonicalHash,
  canonicalStringify,
  type CouncilEventType,
} from '../contracts/index.js';
import type { AuthorizationEnvelope } from './envelope.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from './sqlite.js';

export interface JournalEventInput {
  event_id: string;
  type: CouncilEventType;
  from_state: string | null;
  to_state: string | null;
  actor_subject: string;
  /** Safe event payload: metadata and references, never raw bodies or secrets. */
  payload: Record<string, unknown>;
  created_at: string;
}

export interface JournalEvent {
  event_id: string;
  type: CouncilEventType;
  sequence: number;
  from_state: string | null;
  to_state: string | null;
  actor_subject: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  event_hash: string;
  created_at: string;
}

interface EventRow {
  sequence: number;
  id: string;
  type: string;
  from_state: string | null;
  to_state: string | null;
  actor_subject: string;
  payload_json: string;
  prev_hash: string;
  event_hash: string;
  created_at: string;
}

function eventHashInput(args: {
  tenantId: string;
  companyId: string;
  sessionId: string;
  sequence: number;
  type: string;
  payloadJson: string;
  prevHash: string;
  createdAt: string;
}): Record<string, unknown> {
  return {
    tenant_id: args.tenantId,
    company_id: args.companyId,
    session_id: args.sessionId,
    sequence: args.sequence,
    type: args.type,
    payload_json: args.payloadJson,
    prev_hash: args.prevHash,
    created_at: args.createdAt,
  };
}

export class EventJournal {
  constructor(private readonly db: CouncilDatabase) {}

  /**
   * Append one event inside the current transaction. Returns the
   * committed event with its allocated sequence and chain hashes.
   */
  append(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
    input: JournalEventInput,
  ): JournalEvent {
    const last = handle
      .prepare(
        `SELECT sequence, event_hash FROM council_events
          WHERE tenant_id = ? AND company_id = ? AND session_id = ?
          ORDER BY sequence DESC LIMIT 1`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as
      | { sequence: number; event_hash: string }
      | undefined;
    const sequence = (last?.sequence ?? 0) + 1;
    const prevHash = last?.event_hash ?? '';
    const payloadJson = canonicalStringify(input.payload);
    const eventHash = canonicalHash(
      eventHashInput({
        tenantId: envelope.tenant_id,
        companyId: envelope.company_id,
        sessionId,
        sequence,
        type: input.type,
        payloadJson,
        prevHash,
        createdAt: input.created_at,
      }),
    );
    handle
      .prepare(
        `INSERT INTO council_events
           (tenant_id, company_id, session_id, sequence, id, type, from_state, to_state,
            actor_subject, payload_json, prev_hash, event_hash, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        envelope.tenant_id,
        envelope.company_id,
        sessionId,
        sequence,
        input.event_id,
        input.type,
        input.from_state,
        input.to_state,
        input.actor_subject,
        payloadJson,
        prevHash,
        eventHash,
        input.created_at,
      );
    return {
      event_id: input.event_id,
      type: input.type,
      sequence,
      from_state: input.from_state,
      to_state: input.to_state,
      actor_subject: input.actor_subject,
      payload: input.payload,
      prev_hash: prevHash,
      event_hash: eventHash,
      created_at: input.created_at,
    };
  }

  /** Events after `afterSequence`, in committed order (replay cursor). */
  list(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    afterSequence = 0,
  ): JournalEvent[] {
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT sequence, id, type, from_state, to_state, actor_subject,
                  payload_json, prev_hash, event_hash, created_at
             FROM council_events
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND sequence > ?
            ORDER BY sequence ASC`,
        )
        .all(envelope.tenant_id, envelope.company_id, sessionId, afterSequence),
    ) as EventRow[];
    return rows.map((row) => ({
      event_id: row.id,
      type: row.type as CouncilEventType,
      sequence: row.sequence,
      from_state: row.from_state,
      to_state: row.to_state,
      actor_subject: row.actor_subject,
      payload: JSON.parse(row.payload_json) as Record<string, unknown>,
      prev_hash: row.prev_hash,
      event_hash: row.event_hash,
      created_at: row.created_at,
    }));
  }

  /** The most recent event of one type, or null. Used for state reconstruction. */
  latestOfType(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    types: CouncilEventType[],
  ): JournalEvent | null {
    if (types.length === 0) return null;
    const placeholders = types.map(() => '?').join(', ');
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT sequence, id, type, from_state, to_state, actor_subject,
                  payload_json, prev_hash, event_hash, created_at
             FROM council_events
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND type IN (${placeholders})
            ORDER BY sequence DESC LIMIT 1`,
        )
        .get(envelope.tenant_id, envelope.company_id, sessionId, ...types),
    ) as EventRow | undefined;
    if (!row) return null;
    return {
      event_id: row.id,
      type: row.type as CouncilEventType,
      sequence: row.sequence,
      from_state: row.from_state,
      to_state: row.to_state,
      actor_subject: row.actor_subject,
      payload: JSON.parse(row.payload_json) as Record<string, unknown>,
      prev_hash: row.prev_hash,
      event_hash: row.event_hash,
      created_at: row.created_at,
    };
  }

  /**
   * Re-walk the chain for one session: every sequence increments by
   * one, every prev_hash links to the prior event_hash, and every
   * event_hash recomputes from its stored fields. Any break is
   * reported with the first offending sequence.
   */
  verifyChain(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): { ok: boolean; checked: number; first_bad_sequence: number | null } {
    const events = this.list(envelope, sessionId, 0);
    let prevHash = '';
    for (const [index, event] of events.entries()) {
      const expectedSequence = index + 1;
      if (event.sequence !== expectedSequence || event.prev_hash !== prevHash) {
        return { ok: false, checked: index, first_bad_sequence: event.sequence };
      }
      const recomputed = canonicalHash(
        eventHashInput({
          tenantId: envelope.tenant_id,
          companyId: envelope.company_id,
          sessionId,
          sequence: event.sequence,
          type: event.type,
          payloadJson: canonicalStringify(event.payload),
          prevHash: event.prev_hash,
          createdAt: event.created_at,
        }),
      );
      if (recomputed !== event.event_hash) {
        return { ok: false, checked: index, first_bad_sequence: event.sequence };
      }
      prevHash = event.event_hash;
    }
    return { ok: true, checked: events.length, first_bad_sequence: null };
  }
}
