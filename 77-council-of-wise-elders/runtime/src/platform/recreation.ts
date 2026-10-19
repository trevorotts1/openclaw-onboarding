/**
 * Restart / container-recreation restore (WER-022).
 *
 * A recreated container gets a NEW process and an EMPTY in-memory view. What
 * must survive is durable state written BEFORE the recreate: the session
 * authority records and the budget reservations. This module reads that
 * handoff and rebuilds the view without ever creating a second copy.
 *
 * The handoff is the OWNING AUTHORITY's record, not a second implementation
 * of the queue or session store: sessions reference their owning URL and
 * reservations reference their operation id, and nothing here re-derives a
 * budget or re-admits work.
 *
 * Guarantees proven by the colocated tests:
 * - a recreated process restores every session and reservation;
 * - restoring twice into the same view adds nothing the second time
 *   (`duplicates_created` is always 0);
 * - a snapshot with duplicate ids is refused, never silently deduplicated;
 * - a stale generation is refused, so a released reservation is never
 *   resurrected over a newer view.
 */

import { mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

import {
  platformRefusal,
  HANDOFF_SCHEMA,
  type PlatformRefusal,
} from './types.js';

export interface HandoffSession {
  session_id: string;
  authority: 'standalone' | 'managed';
  owning_session_url?: string | null;
}

export interface HandoffReservation {
  reservation_id: string;
  operation_id: string;
  state: 'held' | 'released' | 'unknown';
}

/** The durable document the owning authority leaves for the next process. */
export interface DurableHandoff {
  schema_version: typeof HANDOFF_SCHEMA;
  /** Monotonic; a lower generation must never overwrite a higher view. */
  generation: number;
  sessions: HandoffSession[];
  reservations: HandoffReservation[];
  written_at: string;
}

export interface DurableStateStore {
  read(): string | null | Promise<string | null>;
  write(text: string): void | Promise<void>;
  describe(): string;
}

/**
 * Durable-file store. Writes are atomic (temporary file in the same
 * directory, then rename) so a crash mid-write cannot leave a truncated
 * handoff behind.
 */
export function fileStateStore(path: string): DurableStateStore {
  return {
    describe: () => path,
    read: () => {
      try {
        return readFileSync(path, 'utf8');
      } catch (error) {
        if (error instanceof Error && (error as NodeJS.ErrnoException).code === 'ENOENT') {
          return null;
        }
        throw error;
      }
    },
    write: (text: string) => {
      mkdirSync(dirname(path), { recursive: true });
      const temporary = join(dirname(path), `.${process.pid}.${Date.now()}.handoff.tmp`);
      try {
        writeFileSync(temporary, text, 'utf8');
        renameSync(temporary, path);
      } catch (error) {
        try {
          unlinkSync(temporary);
        } catch {
          // Best-effort cleanup; the original error is what matters.
        }
        throw error;
      }
    },
  };
}

/** The in-memory view a service runs against after a recreate. */
export interface RestoredView {
  generation: number | null;
  sessions: Map<string, HandoffSession>;
  reservations: Map<string, HandoffReservation>;
}

export function createRestoredView(): RestoredView {
  return { generation: null, sessions: new Map(), reservations: new Map() };
}

export type RestoreOutcome =
  | {
      kind: 'restored';
      generation: number;
      sessions: number;
      reservations: number;
      added_sessions: number;
      existing_sessions: number;
      added_reservations: number;
      existing_reservations: number;
      /** Always 0: restore never adds an id the view already holds. */
      duplicates_created: 0;
      source: string;
      checked: string[];
    }
  | {
      kind: 'empty';
      generation: null;
      sessions: 0;
      reservations: 0;
      duplicates_created: 0;
      source: string;
      checked: string[];
    }
  | PlatformRefusal;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function nonEmpty(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function invalid(detail: string, checked: string[], recovery: string): PlatformRefusal {
  return platformRefusal({
    code: 'PLATFORM_STATE_HANDOFF_INVALID',
    condition: 'HANDOFF_INVALID',
    detail,
    recovery,
    checked,
  });
}

/**
 * Parse and validate a durable handoff. Total: every malformed shape is a
 * typed refusal naming what was wrong.
 */
export function parseHandoff(
  text: string,
  checked: string[] = [],
): DurableHandoff | PlatformRefusal {
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch (error) {
    return invalid(
      `The durable handoff is not valid JSON (${error instanceof Error ? error.message : String(error)}).`,
      checked,
      'Rewrite the handoff from the owning authority; do not start the service against unreadable durable state.',
    );
  }
  if (!isRecord(body)) {
    return invalid('The durable handoff is not a JSON object.', checked, 'Rewrite the handoff document.');
  }
  if (body.schema_version !== HANDOFF_SCHEMA) {
    return invalid(
      `The durable handoff schema is ${JSON.stringify(body.schema_version)}, expected ${HANDOFF_SCHEMA}.`,
      checked,
      'Write the handoff with the current schema version.',
    );
  }
  if (!Number.isInteger(body.generation) || (body.generation as number) < 0) {
    return invalid(
      'The durable handoff generation is not a non-negative integer.',
      checked,
      'Record a monotonic generation on every handoff write.',
    );
  }
  if (!Array.isArray(body.sessions) || !Array.isArray(body.reservations)) {
    return invalid(
      'The durable handoff must carry sessions[] and reservations[] arrays.',
      checked,
      'Rewrite the handoff with both arrays, even when empty.',
    );
  }

  const sessions: HandoffSession[] = [];
  const sessionIds = new Set<string>();
  for (const entry of body.sessions) {
    if (
      !isRecord(entry) ||
      !nonEmpty(entry.session_id) ||
      (entry.authority !== 'standalone' && entry.authority !== 'managed')
    ) {
      return invalid(
        'A durable session entry needs a non-empty session_id and an authority of standalone|managed.',
        checked,
        'Rewrite the handoff from the owning session authority.',
      );
    }
    if (sessionIds.has(entry.session_id)) {
      return platformRefusal({
        code: 'PLATFORM_STATE_HANDOFF_DUPLICATE',
        condition: 'HANDOFF_DUPLICATE',
        detail: `The durable handoff lists session ${entry.session_id} more than once. A recreated service must not start with duplicate authority records.`,
        recovery: 'Repair the durable handoff so each session appears exactly once.',
        checked,
      });
    }
    sessionIds.add(entry.session_id);
    sessions.push({
      session_id: entry.session_id,
      authority: entry.authority,
      owning_session_url:
        typeof entry.owning_session_url === 'string' ? entry.owning_session_url : null,
    });
  }

  const reservations: HandoffReservation[] = [];
  const reservationIds = new Set<string>();
  for (const entry of body.reservations) {
    if (
      !isRecord(entry) ||
      !nonEmpty(entry.reservation_id) ||
      !nonEmpty(entry.operation_id) ||
      (entry.state !== 'held' && entry.state !== 'released' && entry.state !== 'unknown')
    ) {
      return invalid(
        'A durable reservation entry needs reservation_id, operation_id and a state of held|released|unknown.',
        checked,
        'Rewrite the handoff from the owning budget ledger.',
      );
    }
    if (reservationIds.has(entry.reservation_id)) {
      return platformRefusal({
        code: 'PLATFORM_STATE_HANDOFF_DUPLICATE',
        condition: 'HANDOFF_DUPLICATE',
        detail: `The durable handoff lists reservation ${entry.reservation_id} more than once. A recreated service must not double-count a reservation.`,
        recovery: 'Repair the durable handoff so each reservation appears exactly once.',
        checked,
      });
    }
    reservationIds.add(entry.reservation_id);
    reservations.push({
      reservation_id: entry.reservation_id,
      operation_id: entry.operation_id,
      state: entry.state,
    });
  }

  return {
    schema_version: HANDOFF_SCHEMA,
    generation: body.generation as number,
    sessions,
    reservations,
    written_at: typeof body.written_at === 'string' ? body.written_at : '',
  };
}

export interface RestoreOptions {
  store: DurableStateStore;
  view: RestoredView;
  nowUtc?: () => string;
}

/**
 * Restore durable sessions and reservations into a (usually fresh) view.
 *
 * Re-running this against the same view is a no-op for records already
 * present: `added_*` becomes 0 and `existing_*` reports the matched ids, so a
 * double-init bug cannot duplicate a session or a reservation.
 */
export async function restoreAfterRecreation(
  options: RestoreOptions,
): Promise<RestoreOutcome> {
  const source = options.store.describe();
  const checked = [source];

  let text: string | null;
  try {
    text = await options.store.read();
  } catch (error) {
    return platformRefusal({
      code: 'PLATFORM_STATE_HANDOFF_INVALID',
      condition: 'HANDOFF_UNREADABLE',
      detail: `The durable handoff at ${source} could not be read (${error instanceof Error ? error.message : String(error)}).`,
      recovery:
        'Repair the durable volume or permissions before starting the service; never start against unreadable durable state.',
      checked,
    });
  }

  if (text === null || text.trim().length === 0) {
    return {
      kind: 'empty',
      generation: null,
      sessions: 0,
      reservations: 0,
      duplicates_created: 0,
      source,
      checked,
    };
  }

  const parsed = parseHandoff(text, checked);
  if ('kind' in parsed) return parsed;

  if (options.view.generation !== null && parsed.generation < options.view.generation) {
    return platformRefusal({
      code: 'PLATFORM_STATE_HANDOFF_INVALID',
      condition: 'HANDOFF_STALE',
      detail: `The durable handoff generation ${parsed.generation} is older than the view generation ${options.view.generation}. Applying it could resurrect a released reservation.`,
      recovery:
        'Point the service at the current durable handoff; never roll a recreated view back to an older generation.',
      checked,
    });
  }

  let addedSessions = 0;
  let existingSessions = 0;
  for (const session of parsed.sessions) {
    if (options.view.sessions.has(session.session_id)) {
      existingSessions += 1;
      continue;
    }
    options.view.sessions.set(session.session_id, session);
    addedSessions += 1;
  }

  let addedReservations = 0;
  let existingReservations = 0;
  for (const reservation of parsed.reservations) {
    if (options.view.reservations.has(reservation.reservation_id)) {
      existingReservations += 1;
      continue;
    }
    options.view.reservations.set(reservation.reservation_id, reservation);
    addedReservations += 1;
  }

  options.view.generation = parsed.generation;

  return {
    kind: 'restored',
    generation: parsed.generation,
    sessions: options.view.sessions.size,
    reservations: options.view.reservations.size,
    added_sessions: addedSessions,
    existing_sessions: existingSessions,
    added_reservations: addedReservations,
    existing_reservations: existingReservations,
    duplicates_created: 0,
    source,
    checked,
  };
}
