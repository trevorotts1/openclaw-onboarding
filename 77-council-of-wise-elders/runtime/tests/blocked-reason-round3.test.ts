/**
 * W35-B: a council blocked in round 3 explains itself.
 *
 * Runner:
 *   node --import tsx --test tests/blocked-reason-round3.test.ts
 *
 * Replays the shape of the real claude-nine session that ended BLOCKED:
 * rounds 1 and 2 complete, round 3 ratified by six of nine seats, three
 * provider calls closed as completion_unknown ten minutes after they
 * were reserved, and a worker_error SESSION_INCOMPLETE naming the seats.
 * The old text said "no seat is missing; no reason was recorded".
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

import { buildBlockedReason } from '../src/service/sessions.js';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;

const SEATS = [
  'simon-sinek', 'td-jakes', 'oprah-winfrey', 'tiffany-aliche', 'russell-brunson',
  'michelle-obama', 'brene-brown', 'dennis-kimbro', 'les-brown',
];
const MISSING = ['brene-brown', 'dennis-kimbro', 'les-brown'];

const cards = [
  ...SEATS.map((seat_id) => ({ card_kind: 'advisor', round: 1, seat_id })),
  ...SEATS.map((seat_id) => ({ card_kind: 'advisor', round: 2, seat_id })),
  ...SEATS.filter((s) => !MISSING.includes(s)).map((seat_id) => ({ card_kind: 'ratification', round: 3, seat_id })),
];

const reserved = (operation_id: string, created_at: string) => ({
  type: 'operation_reserved', to_state: null, created_at, payload: { kind: 'provider_request', operation_id },
});
const unknown = (operation_id: string, created_at: string) => ({
  type: 'operation_completed', to_state: null, created_at, payload: { operation_id, outcome: 'completion_unknown' },
});

const events = [
  { type: 'session_state_changed', to_state: 'ROUND_3', created_at: '2026-10-20T08:43:00.000Z', payload: {} },
  reserved('ab41e770', '2026-10-20T08:45:26.000Z'), unknown('ab41e770', '2026-10-20T08:55:26.134Z'),
  reserved('cc28ab7c', '2026-10-20T08:55:27.000Z'), unknown('cc28ab7c', '2026-10-20T09:05:27.477Z'),
  reserved('b6b969f5', '2026-10-20T09:05:28.000Z'), unknown('b6b969f5', '2026-10-20T09:15:29.010Z'),
  { type: 'session_blocked', to_state: 'BLOCKED', created_at: '2026-10-20T09:15:29.784Z', payload: {} },
  {
    type: 'operation_completed', to_state: 'BLOCKED', created_at: '2026-10-20T09:15:29.839Z',
    payload: {
      kind: 'worker_error', code: 'SESSION_INCOMPLETE', outcome: 'worker_error',
      message: 'full mode keeps all nine seats: brene-brown round 3, dennis-kimbro round 3, les-brown round 3 missing; the result is a visible partial record, not a smaller council',
    },
  },
];

const input = { state: 'BLOCKED', mode: 'full', seat_ids: SEATS, cards, failures: [], events };

test('API: round 3 missing seats, the cause and the unfinished calls are reported', () => {
  const reason = buildBlockedReason(input);
  assert.ok(reason);
  assert.equal(reason.code, 'FULL_MODE_SEATS_MISSING');
  assert.deepEqual(reason.missing_seats, MISSING);
  assert.equal(reason.missing_round, 3);
  assert.doesNotMatch(reason.detail, /no seat is missing/i);
  assert.doesNotMatch(reason.detail, /no reason was recorded/i);
  assert.match(reason.detail, /round 3 \(the vote\)/);
  for (const seat of MISSING) assert.match(reason.detail, new RegExp(seat));
  assert.match(reason.detail, /about 10 minutes/);
  assert.deepEqual(reason.unfinished_calls.map((c) => c.minutes), [10, 10, 10]);
  assert.deepEqual(reason.last_errors.map((e) => e.seat_id), MISSING);
  for (const e of reason.last_errors) {
    assert.equal(e.outcome_code, 'completion_unknown');
    assert.match(e.message ?? '', /no result recorded.*10 minutes/);
  }
});

// The real journal holds repaired round 2 failures (sess-2e504919 seq 45 brene-brown
// validation) before ROUND_3 began; they must not be blamed for the round 3 block.
const earlierRound = [
  { type: 'session_state_changed', to_state: 'ROUND_2', created_at: '2026-10-20T08:06:36.662Z', payload: {} },
  {
    type: 'operation_completed', to_state: null, created_at: '2026-10-20T07:59:38.391Z',
    payload: { kind: 'attempt_failed', seat_id: 'brene-brown', outcome_code: 'output_validation_failed', message: "response was not valid JSON: Unexpected token 'M'" },
  },
  {
    type: 'operation_completed', to_state: null, created_at: '2026-10-20T08:10:56.943Z',
    payload: { kind: 'attempt_failed', seat_id: 'td-jakes', outcome_code: 'output_validation_failed', message: 'answer failed validation twice' },
  },
];

test('API: a repaired earlier-round failure is not the round 3 cause', () => {
  const reason = buildBlockedReason({
    ...input,
    events: [...earlierRound, ...events],
    failures: [{ seat_id: 'brene-brown', outcome_code: 'output_validation_failed', phase_job_key: 'round-2:brene-brown' }],
  });
  assert.deepEqual(reason?.missing_seats, MISSING);
  assert.deepEqual(reason?.last_errors.map((e) => e.seat_id), MISSING);
  for (const e of reason?.last_errors ?? []) {
    assert.equal(e.outcome_code, 'completion_unknown');
    assert.match(e.message ?? '', /no result recorded.*10 minutes/);
    assert.doesNotMatch(e.message ?? '', /not valid JSON/);
  }
  assert.match(reason?.detail ?? '', /Cause: the provider call ended with no result recorded/);
});

test('chamber: the round 3 text uses the round 3 cause for every seat, not an earlier round 2 message', () => {
  const ns = loadChamber();
  const reason = buildBlockedReason({ ...input, events: [...earlierRound, ...events] });
  const v = JSON.parse(JSON.stringify(ns.state.view(ns.state.create(sessionRecord({ blocked_reason: reason })), 0)));
  assert.doesNotMatch(v.round.explain, /not valid JSON/);
  assert.equal((v.round.explain.match(/no result recorded/g) ?? []).length >= 1, true);
});

test('API: a recorded per-seat error wins over the unanswered-call cause', () => {
  const reason = buildBlockedReason({
    ...input,
    events: [
      ...events,
      { type: 'operation_completed', to_state: null, payload: { kind: 'attempt_failed', seat_id: 'les-brown', outcome_code: 'output_validation_failed', message: 'answer failed validation twice' } },
    ],
  });
  const les = reason?.last_errors.find((e) => e.seat_id === 'les-brown');
  assert.equal(les?.outcome_code, 'output_validation_failed');
  assert.equal(les?.message, 'answer failed validation twice');
});

test('API: seats are not blamed for a call nobody can attribute to them', () => {
  const reason = buildBlockedReason({ ...input, events: events.slice(0, 3) }); // one unfinished call, three seats
  assert.deepEqual(reason?.last_errors, []);
});

test('API: blocked before round 3 does not call round 3 seats missing; it reports the worker error', () => {
  const early = buildBlockedReason({
    ...input,
    cards: cards.filter((c) => c.round < 3),
    events: events.filter((e) => e.to_state !== 'ROUND_3'),
  });
  assert.deepEqual(early?.missing_seats, []);
  assert.equal(early?.code, 'SESSION_INCOMPLETE');
  assert.match(early?.detail ?? '', /full mode keeps all nine seats/);
  assert.doesNotMatch(early?.detail ?? '', /no seat is missing/i);
});

// ---- chamber ----

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
function loadChamber(): Any {
  const sandbox: Record<string, unknown> = {};
  sandbox.globalThis = sandbox;
  for (const file of ['chamber-seats.js', 'chamber-state.js']) {
    runInNewContext(readFileSync(join(chamberDir, file), 'utf8'), sandbox);
  }
  return sandbox.councilChamber;
}

const sessionRecord = (extra: Record<string, unknown>): Record<string, unknown> => ({
  session_id: 'sess-2e504919',
  spec: { mode: 'full', seat_ids: SEATS, model_policy: { route_id: 'claude-nine-configured' } },
  brief: { question: 'Should we do it?', options: [{ id: 'A', label: 'Launch', kind: 'change' }] },
  state: { state: 'BLOCKED', resume_phase: 'VERIFYING', updated_at: '2026-10-20T09:15:29.784Z' },
  ...extra,
});

test('chamber: a blocked session names the missing advisors and why, and the chair is not "working"', () => {
  const ns = loadChamber();
  const m = ns.state.create(sessionRecord({ blocked_reason: buildBlockedReason(input) }));
  const v = JSON.parse(JSON.stringify(ns.state.view(m, Date.parse('2026-10-20T09:20:00.000Z'))));
  const text = [v.statusText, v.round.explain].join(' ');
  assert.equal(v.status, 'blocked');
  assert.match(v.round.explain, /^The council is blocked because .+ have not answered in round 3 \(the vote\)\./);
  for (const seat of MISSING) {
    const full = ns.seats.get(seat).name;
    assert.ok(full.includes(' '), `full name for ${seat}`);
    assert.ok(text.includes(full), `${full} named`);
  }
  assert.match(v.round.explain, /no result recorded.*10 minutes/);
  assert.doesNotMatch(text, /no seat is missing|no reason was recorded/i);
  assert.doesNotMatch(v.round.progressText, /chair is working/i);
  assert.equal(v.round.progressText, 'Blocked');
});

test('chamber: a blocked session with no seat missing shows the service detail, not a contradiction', () => {
  const ns = loadChamber();
  const reason = buildBlockedReason({ ...input, cards: cards.filter((c) => c.round < 3), events: events.filter((e) => e.to_state !== 'ROUND_3') });
  const v = JSON.parse(JSON.stringify(ns.state.view(ns.state.create(sessionRecord({ blocked_reason: reason })), 0)));
  assert.match(v.round.explain, /full mode keeps all nine seats/);
  assert.equal(v.round.progressText, 'Blocked');
});
