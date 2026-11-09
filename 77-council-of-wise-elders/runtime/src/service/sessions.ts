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
import { isCouncilSize } from '../contracts/index.js';

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
  /** The round the missing seats belong to (1, 2 or 3); null when no seat is missing. */
  missing_round: number | null;
  last_errors: Array<{ seat_id: string; outcome_code: string | null; message: string | null }>;
  /** Provider calls that were reserved but never reported a result. */
  unfinished_calls: Array<{ operation_id: string; outcome: string; minutes: number | null }>;
}

const ROUND_NAMES: Record<number, string> = { 1: 'round 1 (opening positions)', 2: 'round 2 (debate)', 3: 'round 3 (the vote)' };

/**
 * The blocked-reason label for a round. The four older modes keep their
 * fixed three names; the council sizes run 1..10 advisor rounds with no
 * ratification pass, so every pass after the opening is a challenge.
 */
function roundName(mode: string, round: number): string {
  if (isCouncilSize(mode)) {
    return round === 1 ? 'round 1 (opening positions)' : `round ${round} (challenge pass)`;
  }
  return ROUND_NAMES[round] ?? `round ${round}`;
}

/** The session state that carries a round number on the council-size paths. */
function stateForRound(mode: string, round: number): string {
  if (isCouncilSize(mode)) return round === 1 ? 'ROUND_1' : 'ROUND_2';
  return `ROUND_${round}`;
}

/**
 * Why a BLOCKED session is blocked, computed at read time from stored
 * data (spec seats minus accepted cards, failed jobs, journaled attempt
 * failures, provider calls that never answered), so sessions blocked
 * before the journal carried messages explain themselves too. Null when
 * the session is not BLOCKED.
 */
export function buildBlockedReason(input: {
  state: string;
  mode: string;
  seat_ids: readonly string[];
  cards: ReadonlyArray<{ card_kind: string; round: number; seat_id?: string }>;
  failures: ReadonlyArray<{ seat_id: string | null; outcome_code: string | null; phase_job_key?: string }>;
  events: ReadonlyArray<{ type: string; payload: Record<string, unknown>; created_at?: string; to_state?: string | null }>;
}): BlockedReason | null {
  if (input.state !== 'BLOCKED') return null;
  // The first round (1, 2, then the round 3 ratification) that is short of seats.
  let missing: string[] = [];
  let missingRound: number | null = null;
  // Round 3 counts only once the session reached it; blocked earlier, its seats are not "missing".
  const reachedRound3 =
    input.events.some((e) => e.to_state === 'ROUND_3') || input.cards.some((c) => c.card_kind === 'ratification');
  const councilMode = isCouncilSize(input.mode);
  // The council sizes have no ratification round: the rounds to check
  // are every advisor round the record actually reached (at least one).
  const reachedRounds: number[] = councilMode
    ? Array.from(
        { length: Math.max(1, ...input.cards.filter((c) => c.card_kind === 'advisor').map((c) => c.round)) },
        (_, index) => index + 1,
      )
    : reachedRound3
      ? [1, 2, 3]
      : [1, 2];
  for (const round of reachedRounds) {
    const kind = !councilMode && round === 3 ? 'ratification' : 'advisor';
    const have = new Set(
      input.cards.filter((c) => c.card_kind === kind && c.round === round).map((c) => c.seat_id),
    );
    missing = input.seat_ids.filter((seat) => !have.has(seat));
    if (missing.length > 0) {
      missingRound = round;
      break;
    }
  }
  // Only what happened since the session entered the short round counts: a
  // validation failure repaired in an earlier round is not this round's cause.
  // The council sizes re-enter ROUND_2 for every challenge pass, so the
  // window starts at the LAST real transition into the round's state (the
  // pass that is short now). A lease-claim state write repeats the current
  // state, so those entries are not transitions and do not move the window.
  const roundState = missingRound === null ? null : stateForRound(input.mode, missingRound);
  let enteredAt = -1;
  let seenState: string | null = null;
  if (roundState !== null) {
    for (let index = 0; index < input.events.length; index += 1) {
      const to = input.events[index].to_state;
      if (typeof to !== 'string' || to === seenState) continue;
      seenState = to;
      if (to === roundState) enteredAt = index;
    }
  }
  const sinceRound = missingRound === null ? input.events : input.events.slice(Math.max(0, enteredAt));
  const roundFailures = missingRound === null
    ? input.failures
    : input.failures.filter((f) => !f.phase_job_key || f.phase_job_key.startsWith(`round-${missingRound}:`));
  const completed = sinceRound.filter((e) => e.type === 'operation_completed');
  const attemptFailures = completed.filter((e) => e.payload.kind === 'attempt_failed').map((e) => e.payload);
  // A call reserved, then closed as completion_unknown: it never reported a result.
  const unfinished = completed
    .filter((e) => e.payload.outcome === 'completion_unknown' && typeof e.payload.operation_id === 'string')
    .map((e) => {
      const id = e.payload.operation_id as string;
      const reserved = input.events.find(
        (r) => r.type === 'operation_reserved' && r.payload.operation_id === id,
      );
      const ms = reserved?.created_at && e.created_at ? Date.parse(e.created_at) - Date.parse(reserved.created_at) : NaN;
      return { operation_id: id, outcome: 'completion_unknown', minutes: Number.isFinite(ms) ? Math.round(ms / 60_000) : null };
    });
  const unanswered = unfinished.length > 0
    ? `the provider call ended with no result recorded (completion unknown)${unfinished[0].minutes !== null ? ` about ${unfinished[0].minutes} minutes after it started` : ''}`
    : null;
  const unexplained = missing.filter(
    (seat) => !attemptFailures.some((p) => p.seat_id === seat) && !roundFailures.some((f) => f.seat_id === seat),
  );
  const lastErrors = missing.flatMap((seat) => {
    const logged = attemptFailures.filter((p) => p.seat_id === seat).pop();
    const job = roundFailures.filter((f) => f.seat_id === seat).pop();
    // Calls carry no seat, so a seat with no recorded error gets the
    // unanswered-call cause only when there are enough such calls to cover
    // every seat that has no other explanation.
    if (!logged && !job) {
      return unanswered && unfinished.length >= unexplained.length
        ? [{ seat_id: seat, outcome_code: 'completion_unknown', message: unanswered.charAt(0).toUpperCase() + unanswered.slice(1) + '.' }]
        : [];
    }
    return [{
      seat_id: seat,
      outcome_code: (logged?.outcome_code as string | undefined) ?? job?.outcome_code ?? null,
      message: (logged?.message as string | undefined) ?? null,
    }];
  });
  const worker = input.events
    .filter((e) => e.type === 'operation_completed' && e.payload.kind === 'worker_error')
    .map((e) => e.payload)
    .pop();
  const settled = typeof worker?.code === 'string' ? worker.code : undefined;
  const code = missing.length > 0
    ? input.mode === 'full' ? 'FULL_MODE_SEATS_MISSING' : 'SEATS_MISSING'
    : settled ?? 'BLOCKED_REASON_NOT_RECORDED';
  const where = missingRound ? ` in ${roundName(input.mode, missingRound)}` : '';
  const detail = missing.length > 0
    ? `${input.mode === 'full' ? 'Full mode needs all nine seats' : 'The council is short of seats'}; no accepted card${where} from: ${missing.join(', ')}.` +
      (unanswered && unfinished.length >= unexplained.length && unexplained.length > 0 ? ` Cause: ${unanswered}.` : '')
    : typeof worker?.message === 'string' && worker.message
      ? `The session is blocked: ${worker.message}`
      : 'The session is blocked, but every seat has an accepted card and the service recorded no further reason.';
  return { code, detail, missing_seats: missing, missing_round: missingRound, last_errors: lastErrors, unfinished_calls: unfinished };
}
