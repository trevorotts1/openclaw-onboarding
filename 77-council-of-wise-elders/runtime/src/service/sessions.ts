/**
 * Session authority resolution (WER-021).
 *
 * One authority per session. A managed session is LINKED to its owning
 * Command Center URL and is never started locally; a standalone session
 * lives on this service's verified origin. A managed record without a
 * valid owner URL is BLOCKED — never silently converted into a local
 * session.
 */

import {
  type SessionAuthorityRecord,
  type SessionTarget,
} from './types.js';

/** Canonical local session path; the shared CC UI route is /council/<id>. */
export function sessionPath(sessionId: string): string {
  return `/council/${encodeURIComponent(sessionId)}`;
}

export function eventsPath(sessionId: string): string {
  return `/api/council/sessions/${encodeURIComponent(sessionId)}/events`;
}

function absoluteHttpUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    return url;
  } catch {
    return null;
  }
}

/**
 * Build the true local session URL from the ACTUAL bound origin (the
 * origin the listener reported), never from a configured pretty host.
 */
export function sessionUrl(origin: string, sessionId: string): string {
  const base = absoluteHttpUrl(origin);
  if (!base) {
    throw new Error(`Origin "${origin}" is not an absolute HTTP(S) URL.`);
  }
  return new URL(sessionPath(sessionId), base).toString();
}

function blocked(
  record: SessionAuthorityRecord,
  code: string,
  detail: string,
  recovery: string,
): SessionTarget {
  return {
    kind: 'blocked',
    session_id: record.session_id,
    url: null,
    authority:
      record.authority === 'managed' || record.authority === 'standalone'
        ? record.authority
        : 'unknown',
    launched_locally: false,
    blocker: { code, detail },
    recovery,
  };
}

export function resolveSessionTarget(
  record: SessionAuthorityRecord,
  options: { origin: string | null },
): SessionTarget {
  if (!record.session_id || record.session_id.trim().length === 0) {
    return blocked(
      record,
      'SESSION_ID_MISSING',
      'The session record carries no session id.',
      'Supply the durable session id returned by the owning authority.',
    );
  }

  if (record.authority === 'managed') {
    const owner = record.owning_session_url?.trim();
    if (!owner) {
      return blocked(
        record,
        'MANAGED_SESSION_OWNER_URL_MISSING',
        `Managed session ${record.session_id} has no owning Command Center URL.`,
        'Link the session to its owning Command Center URL; a managed session is never duplicated locally.',
      );
    }
    if (!absoluteHttpUrl(owner)) {
      return blocked(
        record,
        'MANAGED_SESSION_OWNER_URL_INVALID',
        `Managed session ${record.session_id} carries an owner URL that is not absolute HTTP(S).`,
        'Correct the recorded owning Command Center URL; do not start a local copy.',
      );
    }
    return {
      kind: 'external',
      session_id: record.session_id,
      url: owner,
      authority: 'managed',
      launched_locally: false,
    };
  }

  if (record.authority === 'standalone') {
    if (!options.origin || !absoluteHttpUrl(options.origin)) {
      return blocked(
        record,
        'SERVICE_ORIGIN_UNAVAILABLE',
        'The standalone service is not bound to a verified local origin.',
        'Start the front-door service and re-resolve the session URL from its reported origin.',
      );
    }
    return {
      kind: 'local',
      session_id: record.session_id,
      url: sessionUrl(options.origin, record.session_id),
      authority: 'standalone',
      launched_locally: true,
    };
  }

  return blocked(
    record,
    'SESSION_AUTHORITY_UNKNOWN',
    `Session ${record.session_id} has no recognised authority.`,
    'Record exactly one authority (standalone or managed) for the session.',
  );
}

export interface BlockedReason {
  code: string;
  detail: string;
  missing_seats: string[];
  last_errors: Array<{ seat_id: string; outcome_code: string | null; message: string | null }>;
}

/**
 * Why a BLOCKED session is blocked, computed at read time from stored
 * data (spec seats minus accepted advisor cards, failed jobs, journaled
 * attempt failures), so sessions blocked before the journal carried
 * messages explain themselves too. Null when the session is not BLOCKED.
 */
export function buildBlockedReason(input: {
  state: string;
  mode: string;
  seat_ids: readonly string[];
  cards: ReadonlyArray<{ card_kind: string; round: number; seat_id?: string }>;
  failures: ReadonlyArray<{ seat_id: string | null; outcome_code: string | null }>;
  events: ReadonlyArray<{ type: string; payload: Record<string, unknown> }>;
}): BlockedReason | null {
  if (input.state !== 'BLOCKED') return null;
  // The first advisor round (1, then 2) that is short of seats.
  let missing: string[] = [];
  for (const round of [1, 2]) {
    const have = new Set(
      input.cards.filter((c) => c.card_kind === 'advisor' && c.round === round).map((c) => c.seat_id),
    );
    missing = input.seat_ids.filter((seat) => !have.has(seat));
    if (missing.length > 0) break;
  }
  const attemptFailures = input.events
    .filter((e) => e.type === 'operation_completed' && e.payload.kind === 'attempt_failed')
    .map((e) => e.payload);
  const lastErrors = missing.flatMap((seat) => {
    const logged = attemptFailures.filter((p) => p.seat_id === seat).pop();
    const job = input.failures.filter((f) => f.seat_id === seat).pop();
    if (!logged && !job) return [];
    return [{
      seat_id: seat,
      outcome_code: (logged?.outcome_code as string | undefined) ?? job?.outcome_code ?? null,
      message: (logged?.message as string | undefined) ?? null,
    }];
  });
  const settled = input.events
    .filter((e) => e.type === 'operation_completed' && e.payload.kind === 'worker_error')
    .map((e) => e.payload.code)
    .filter((c): c is string => typeof c === 'string')
    .pop();
  const code = missing.length > 0
    ? input.mode === 'full' ? 'FULL_MODE_SEATS_MISSING' : 'SEATS_MISSING'
    : settled ?? 'BLOCKED_REASON_NOT_RECORDED';
  const detail = missing.length > 0
    ? `${input.mode === 'full' ? 'Full mode needs all nine seats' : 'The council is short of seats'}; no accepted card from: ${missing.join(', ')}.`
    : 'The session is blocked and no seat is missing; no reason was recorded.';
  return { code, detail, missing_seats: missing, last_errors: lastErrors };
}
