/**
 * The council projection outbox (CWE-006, directive Sections 16.2 and
 * 18.2).
 *
 * Notifications, task projections, and event fan-out are never sent
 * from inside the commit transaction. Instead the commit records a
 * durable intent in council_projection_outbox in the SAME transaction
 * as the state, card, and event writes it describes; a separate
 * consumer delivers intents afterwards. Delivery is therefore
 * crash-safe (an intent survives the process that committed it) and
 * idempotent: each intent carries a unique idempotency key per topic,
 * enqueueing the same intent twice returns the original row, and a
 * consumer that replays after restart sees delivered intents as
 * delivered, so each semantic event reaches the reducer once even when
 * the transport delivers duplicates.
 */

import { canonicalStringify } from '../contracts/index.js';
import type { AuthorizationEnvelope } from './envelope.js';
import type { CouncilDatabase, SqliteDatabaseHandle } from './sqlite.js';

export type OutboxState = 'pending' | 'delivered' | 'failed' | 'dead_letter';

export interface OutboxIntentInput {
  id: string;
  session_id: string | null;
  event_sequence: number | null;
  topic: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface OutboxIntent {
  id: string;
  session_id: string | null;
  event_sequence: number | null;
  topic: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
  state: OutboxState;
  attempt_count: number;
  next_attempt_at: string | null;
  last_error_code: string | null;
  created_at: string;
  delivered_at: string | null;
}

interface OutboxRow {
  id: string;
  session_id: string | null;
  event_sequence: number | null;
  topic: string;
  idempotency_key: string;
  payload_json: string;
  state: string;
  attempt_count: number;
  next_attempt_at: string | null;
  last_error_code: string | null;
  created_at: string;
  delivered_at: string | null;
}

function toIntent(row: OutboxRow): OutboxIntent {
  return {
    id: row.id,
    session_id: row.session_id,
    event_sequence: row.event_sequence,
    topic: row.topic,
    idempotency_key: row.idempotency_key,
    payload: JSON.parse(row.payload_json) as Record<string, unknown>,
    state: row.state as OutboxState,
    attempt_count: row.attempt_count,
    next_attempt_at: row.next_attempt_at,
    last_error_code: row.last_error_code,
    created_at: row.created_at,
    delivered_at: row.delivered_at,
  };
}

export class ProjectionOutbox {
  constructor(
    private readonly db: CouncilDatabase,
    private readonly maxAttempts: number,
  ) {}

  /**
   * Enqueue one intent inside the current transaction. Idempotent: a
   * replay with the same (scope, topic, idempotency_key) returns the
   * existing intent with `created: false` and records nothing new, so
   * a duplicate commit never duplicates the follow-through intent.
   */
  enqueue(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    input: OutboxIntentInput,
  ): { intent: OutboxIntent; created: boolean } {
    const existing = handle
      .prepare(
        `SELECT id, session_id, event_sequence, topic, idempotency_key, payload_json,
                state, attempt_count, next_attempt_at, last_error_code, created_at, delivered_at
           FROM council_projection_outbox
          WHERE tenant_id = ? AND company_id = ? AND topic = ? AND idempotency_key = ?`,
      )
      .get(
        envelope.tenant_id,
        envelope.company_id,
        input.topic,
        input.idempotency_key,
      ) as OutboxRow | undefined;
    if (existing) return { intent: toIntent(existing), created: false };
    handle
      .prepare(
        `INSERT INTO council_projection_outbox
           (tenant_id, company_id, session_id, id, event_sequence, topic, idempotency_key,
            payload_json, state, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)`,
      )
      .run(
        envelope.tenant_id,
        envelope.company_id,
        input.session_id,
        input.id,
        input.event_sequence,
        input.topic,
        input.idempotency_key,
        canonicalStringify(input.payload),
        input.created_at,
      );
    return {
      intent: {
        id: input.id,
        session_id: input.session_id,
        event_sequence: input.event_sequence,
        topic: input.topic,
        idempotency_key: input.idempotency_key,
        payload: input.payload,
        state: 'pending',
        attempt_count: 0,
        next_attempt_at: null,
        last_error_code: null,
        created_at: input.created_at,
        delivered_at: null,
      },
      created: true,
    };
  }

  /**
   * Claim due intents for delivery: pending, or failed and due for a
   * retry. Claiming only reads; the consumer marks the outcome, so a
   * crash mid-delivery leaves the intent claimable again (at-least-once
   * transport, exactly-once semantics via the idempotency key at the
   * consumer).
   */
  claimDue(
    envelope: AuthorizationEnvelope,
    nowIso: string,
    limit = 50,
  ): OutboxIntent[] {
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT id, session_id, event_sequence, topic, idempotency_key, payload_json,
                  state, attempt_count, next_attempt_at, last_error_code, created_at, delivered_at
             FROM council_projection_outbox
            WHERE tenant_id = ? AND company_id = ?
              AND state IN ('pending', 'failed')
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY created_at ASC
            LIMIT ?`,
        )
        .all(envelope.tenant_id, envelope.company_id, nowIso, limit),
    ) as OutboxRow[];
    return rows.map(toIntent);
  }

  /** Mark one intent delivered. Re-marking a delivered intent is a no-op. */
  markDelivered(envelope: AuthorizationEnvelope, id: string, deliveredAt: string): void {
    this.db.write((handle) => {
      handle
        .prepare(
          `UPDATE council_projection_outbox
              SET state = 'delivered', delivered_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND state != 'delivered'`,
        )
        .run(deliveredAt, envelope.tenant_id, envelope.company_id, id);
    });
  }

  /**
   * Record a failed delivery attempt. Below the attempt bound the
   * intent becomes claimable again at `nextAttemptAt`; at the bound it
   * is parked as dead_letter for operator attention, never retried
   * silently forever.
   */
  markFailed(
    envelope: AuthorizationEnvelope,
    id: string,
    errorCode: string,
    nextAttemptAt: string,
  ): OutboxIntent | null {
    return this.db.write((handle) => {
      const row = handle
        .prepare(
          `SELECT id, session_id, event_sequence, topic, idempotency_key, payload_json,
                  state, attempt_count, next_attempt_at, last_error_code, created_at, delivered_at
             FROM council_projection_outbox
            WHERE tenant_id = ? AND company_id = ? AND id = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, id) as OutboxRow | undefined;
      if (!row || row.state === 'delivered' || row.state === 'dead_letter') {
        return row ? toIntent(row) : null;
      }
      const attempts = row.attempt_count + 1;
      const state: OutboxState = attempts >= this.maxAttempts ? 'dead_letter' : 'failed';
      handle
        .prepare(
          `UPDATE council_projection_outbox
              SET state = ?, attempt_count = ?, last_error_code = ?, next_attempt_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?`,
        )
        .run(
          state,
          attempts,
          errorCode,
          state === 'dead_letter' ? null : nextAttemptAt,
          envelope.tenant_id,
          envelope.company_id,
          id,
        );
      return { ...toIntent(row), state, attempt_count: attempts, last_error_code: errorCode };
    });
  }

  /** All intents for one session, in creation order (operator view). */
  listForSession(envelope: AuthorizationEnvelope, sessionId: string): OutboxIntent[] {
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT id, session_id, event_sequence, topic, idempotency_key, payload_json,
                  state, attempt_count, next_attempt_at, last_error_code, created_at, delivered_at
             FROM council_projection_outbox
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
            ORDER BY created_at ASC`,
        )
        .all(envelope.tenant_id, envelope.company_id, sessionId),
    ) as OutboxRow[];
    return rows.map(toIntent);
  }
}
