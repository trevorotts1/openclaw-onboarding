/**
 * Chamber state engine tests (H-state).
 *
 * Runner:
 *   node --import tsx --test tests/chamber-state.test.ts
 *
 * Loads public/chamber/chamber-state.js in node:vm, the same way the browser
 * sees it, and replays real committed frame shapes: the CLI engine run
 * (tests/fixtures/chamber/engine-sample-run.frames.json), an equivalent
 * service-shape run, and the labelled fictional demo replay.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const chamberDir = join(here, '..', 'public', 'chamber');

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;

function loadState(): Any {
  const sandbox: Record<string, unknown> = {};
  sandbox.globalThis = sandbox;
  runInNewContext(readFileSync(join(chamberDir, 'chamber-state.js'), 'utf8'), sandbox);
  return (sandbox.councilChamber as Any).state;
}

/** vm objects carry another realm's prototypes; compare plain copies. */
function plain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const SEATS = [
  'simon-sinek', 'td-jakes', 'oprah-winfrey', 'tiffany-aliche', 'russell-brunson',
  'michelle-obama', 'brene-brown', 'dennis-kimbro', 'les-brown',
];
const OPTIONS = [
  { id: 'A', label: 'Launch now', kind: 'change' },
  { id: 'B', label: 'Pilot first', kind: 'bounded_test' },
  { id: 'C', label: 'Keep as is', kind: 'status_quo' },
];
const record = (extra: Record<string, unknown> = {}): Record<string, unknown> => ({
  session_id: 'sess-1',
  spec: {
    mode: 'full',
    seat_ids: SEATS,
    model_policy: { route_id: 'claude-configured', requested_model_id: 'sonnet-test' },
  },
  brief: { question: 'Should we do it?', options: OPTIONS },
  state: { state: 'DRAFT', updated_at: '2026-10-19T10:00:00.000Z' },
  ...extra,
});

const cliFrames: Any[] = JSON.parse(
  readFileSync(join(here, 'fixtures', 'chamber', 'engine-sample-run.frames.json'), 'utf8'),
);

/** Rewrite the CLI run into the service shape: to_state on top, reserved/completed with hashed operation ids (as the real service writes them). */
function serviceFrames(): Any[] {
  const out: Any[] = [];
  let seq = 0;
  const push = (f: Any): void => { seq += 1; out.push({ ...f, sequence: seq }); };
  for (const f of cliFrames) {
    const p = f.payload ?? {};
    if (f.type === 'session_created') {
      push({ ...f, to_state: 'DRAFT', payload: { state_record: { state: 'DRAFT' } } });
    } else if (f.type === 'session_state_changed') {
      push({ ...f, from_state: p.from, to_state: p.to, payload: { state_record: { state: p.to } } });
    } else if (f.type === 'card_accepted') {
      const op = `${(seq + 1).toString(16).padStart(64, 'c')}`;
      push({ type: 'operation_reserved', to_state: null, payload: { operation_id: op }, created_at: f.created_at });
      push({ ...f, payload: { operation_id: op, seat_id: p.seat_id, round: p.round, card_hash: 'h' } });
      push({ type: 'operation_completed', to_state: null, payload: { operation_id: op }, created_at: f.created_at });
    } else if (f.type === 'verdict_validated') {
      push({ ...f, payload: { verdict_revision: 1, result_kind: 'scored' } });
    }
    // crux_identified / resolution_drafted and the CLI operation_completed rows are CLI-only.
  }
  return out;
}

const COPY_ORDER = [
  'CHAIR: READING YOUR QUESTION',
  'ROUND 1: OPENING POSITIONS',
  'ROUND 1: ALL 9 POSITIONS IN',
  'CHAIR: FINDING THE FAULT LINES',
  'ROUND 2: DEBATE',
  'ROUND 2: ALL 9 POSITIONS IN',
  'CHAIR: DRAFTING THE RESOLUTION',
  'ROUND 3: THE VOTE',
  'ROUND 3: ALL 9 POSITIONS IN',
  'CHAIR: CHECKING THE VERDICT',
];

function frame(sequence: number, type: string, extra: Record<string, unknown> = {}): Any {
  return { sequence, type, to_state: null, payload: {}, created_at: '2026-10-19T10:00:00.000Z', ...extra };
}
const stateFrame = (sequence: number, to: string, at = '2026-10-19T10:00:00.000Z'): Any =>
  frame(sequence, 'session_state_changed', { to_state: to, payload: { state_record: { state: to } }, created_at: at });

const card = (seat: string, round: number, pref: string | null, extra: Record<string, unknown> = {}): Any => ({
  card_kind: round === 3 ? 'ratification' : 'advisor',
  seat_id: seat,
  round,
  stance: 'support',
  preferred_option_id: pref,
  ...(round === 3
    ? { resolution_stance: 'support', unresolved_objections: [`${seat} objection`], amendments: [] }
    : { decisive_arguments: [`${seat} argument r${round}`] }),
  ...extra,
});

const ALL_DONE = ['done', 'done', 'done', 'done', 'done', 'done'];

function stepStatuses(view: Any): string[] {
  return plain(view.steps.map((s: Any) => s.status));
}

// ---------------------------------------------------------------- replays

test('CLI-shape replay ends COMPLETED with all six steps done and copy-table key points', () => {
  const S = loadState();
  const m = S.create(record({ state: undefined }));
  for (const f of cliFrames) assert.equal(S.apply(m, f), true);
  S.applyRecord(m, { verdict: { result_kind: 'scored', label: 'GO_WITH_CONDITIONS', recommended_option_id: 'B', option_scores: [] } });
  const v = S.view(m, Date.parse('2026-10-19T18:00:00.000Z'));
  assert.equal(v.state, 'COMPLETED');
  assert.equal(v.status, 'complete');
  assert.deepEqual(stepStatuses(v), ALL_DONE);
  assert.deepEqual(plain(v.steps.map((s: Any) => s.label)), ['Brief', 'Openings', 'Fault lines', 'Debate', 'Vote', 'Verdict']);
  assert.deepEqual(plain(v.keyPoints.map((k: Any) => k.label)), [
    ...COPY_ORDER, 'VERDICT: GO, WITH CONDITIONS',
  ]);
  assert.equal(v.keyPoints[v.keyPoints.length - 1].detail, 'Option B: Pilot first');
  // CLI-only chair fields are applied when present.
  assert.match(v.keyPoints.find((k: Any) => k.label === 'CHAIR: FINDING THE FAULT LINES').detail, /\S/);
  assert.equal(v.keyPoints.find((k: Any) => k.label === 'CHAIR: DRAFTING THE RESOLUTION').detail, 'Recommended: Option B: Pilot first');
});

test('service-shape replay ends COMPLETED with the same steps and key points', () => {
  const S = loadState();
  const frames = serviceFrames();
  const m = S.create(record());
  for (const f of frames) assert.equal(S.apply(m, f), true);
  S.applyRecord(m, { verdict: { result_kind: 'scored', label: 'GO', recommended_option_id: 'A', option_scores: [] } });
  const v = S.view(m, Date.parse('2026-10-19T18:00:00.000Z'));
  assert.equal(v.state, 'COMPLETED');
  assert.deepEqual(stepStatuses(v), ALL_DONE);
  assert.deepEqual(plain(v.keyPoints.map((k: Any) => k.label)), [...COPY_ORDER, 'VERDICT: GO']);
  assert.equal(v.keyPoints[v.keyPoints.length - 1].detail, 'Option A: Launch now');
});

test('duplicate and older sequences are ignored', () => {
  const S = loadState();
  const m = S.create(record());
  assert.equal(S.apply(m, stateFrame(5, 'ROUND_1')), true);
  assert.equal(S.apply(m, stateFrame(5, 'ROUND_2')), false, 'duplicate');
  assert.equal(S.apply(m, stateFrame(4, 'ROUND_3')), false, 'older');
  assert.equal(S.apply(m, { type: 'x' }), false, 'no sequence');
  assert.equal(S.apply(m, null), false);
  assert.equal(S.view(m, 0).state, 'ROUND_1');
  // Replaying the whole run a second time changes nothing.
  const frames = serviceFrames();
  const n = S.create(record());
  frames.forEach((f) => S.apply(n, f));
  const once = plain(S.view(n, 1_800_000_000_000));
  frames.forEach((f) => assert.equal(S.apply(n, f), false));
  assert.deepEqual(plain(S.view(n, 1_800_000_000_000)), once);
});

// ----------------------------------------------------------- step mapping

test('step mapping table', () => {
  const S = loadState();
  const want: Record<string, string | null> = {
    DRAFT: 'brief', READY: 'brief', QUEUED: 'brief', PREPARING: 'brief',
    ROUND_1: 'openings', CONSULTING: 'openings',
    CRUX_REVIEW: 'fault_lines', ROUND_2: 'debate',
    DRAFT_RESOLUTION: 'vote', ROUND_3: 'vote',
    VERIFYING: 'verdict', COMPLETED: 'verdict',
    PAUSED: null, BLOCKED: null, FAILED: null,
  };
  for (const [st, key] of Object.entries(want)) assert.equal(S.stepOf(st), key, st);
  // Each state puts the matching step at "current" (COMPLETED marks all done).
  const order = ['brief', 'openings', 'fault_lines', 'debate', 'vote', 'verdict'];
  for (const [st, key] of Object.entries(want)) {
    if (!key || st === 'COMPLETED' || st === 'CONSULTING') continue;
    const m = S.create(record());
    S.apply(m, stateFrame(1, st));
    const steps = S.view(m, 0).steps;
    const at = order.indexOf(key);
    assert.deepEqual(
      plain(steps.map((s: Any) => s.status)),
      order.map((_, i) => (i < at ? 'done' : i === at ? 'current' : 'todo')),
      st,
    );
  }
});

test('consult skips fault lines, debate and vote', () => {
  const S = loadState();
  const m = S.create(record({ spec: { mode: 'consult', seat_ids: ['simon-sinek'], model_policy: { route_id: 'r', requested_model_id: null } } }));
  S.apply(m, stateFrame(1, 'CONSULTING'));
  assert.deepEqual(stepStatuses(S.view(m, 0)), ['done', 'current', 'skipped', 'skipped', 'skipped', 'todo']);
  assert.equal(S.view(m, 0).round.label, 'CONSULT');
  S.apply(m, stateFrame(2, 'VERIFYING'));
  S.apply(m, stateFrame(3, 'COMPLETED'));
  assert.deepEqual(stepStatuses(S.view(m, 0)), ['done', 'done', 'skipped', 'skipped', 'skipped', 'done']);
});

test('control states keep the last step and set the status', () => {
  const S = loadState();
  const cases: Array<[string, string]> = [
    ['PAUSED', 'paused'], ['PAUSE_REQUESTED', 'paused'], ['CANCEL_REQUESTED', 'cancelled'],
    ['CANCELLED', 'cancelled'], ['BLOCKED', 'blocked'], ['FAILED', 'failed'],
  ];
  for (const [st, status] of cases) {
    const m = S.create(record());
    S.apply(m, stateFrame(1, 'ROUND_2'));
    S.apply(m, stateFrame(2, st));
    const v = S.view(m, 0);
    assert.equal(v.status, status, st);
    assert.deepEqual(stepStatuses(v), ['done', 'done', 'done', 'current', 'todo', 'todo'], st);
    assert.equal(v.round.label, st.replace(/_/g, ' '));
  }
  // RESUMING keeps the step and runs again.
  const r = S.create(record());
  S.apply(r, stateFrame(1, 'ROUND_3'));
  S.apply(r, stateFrame(2, 'PAUSED'));
  S.apply(r, stateFrame(3, 'RESUMING'));
  assert.equal(S.view(r, 0).status, 'running');
  assert.equal(S.view(r, 0).steps[4].status, 'current');
});

test('BLOCKED keeps the last step with status blocked and shows the reason', () => {
  const S = loadState();
  const m = S.create(record());
  S.apply(m, stateFrame(1, 'ROUND_1'));
  S.apply(m, stateFrame(2, 'BLOCKED'));
  S.apply(m, frame(3, 'session_blocked', { payload: { reason: 'Route budget exhausted.' } }));
  const v = S.view(m, 0);
  assert.equal(v.status, 'blocked');
  assert.equal(v.steps[1].status, 'current');
  assert.equal(v.round.explain, 'Route budget exhausted.');
  assert.equal(v.keyPoints[v.keyPoints.length - 1].label, 'BLOCKED');
  assert.equal(v.keyPoints[v.keyPoints.length - 1].detail, 'Route budget exhausted.');
});

test('a session read alone drives the view before any frame arrives', () => {
  const S = loadState();
  const m = S.create(record({ state: { state: 'PAUSED', resume_phase: 'ROUND_2', updated_at: '2026-10-19T10:00:00.000Z' } }));
  const v = S.view(m, Date.parse('2026-10-19T10:00:30.000Z'));
  assert.equal(v.status, 'paused');
  assert.equal(v.steps[3].status, 'current');
  assert.equal(v.round.timer, '0:30');
  assert.equal(v.question, 'Should we do it?');
  assert.deepEqual(plain(v.route), { routeId: 'claude-configured', model: 'sonnet-test' });
  assert.deepEqual(plain(v.options.map((o: Any) => [o.letter, o.label, o.votes])), [['A', 'Launch now', null], ['B', 'Pilot first', null], ['C', 'Keep as is', null]]);
});

// ------------------------------------------------------- copy and labels

test('copy table: headline, round label and explainer for each state', () => {
  const S = loadState();
  const table: Array<[string, string, string]> = [
    ['DRAFT', 'The chair is reading your question.', 'GETTING READY'],
    ['ROUND_1', 'The advisors are writing their opening positions.', 'ROUND 1 OF 3'],
    ['CRUX_REVIEW', 'The chair is finding the fault lines.', 'AFTER ROUND 1 OF 3'],
    ['ROUND_2', 'The advisors are debating the fault lines.', 'ROUND 2 OF 3'],
    ['DRAFT_RESOLUTION', 'The chair is drafting the resolution.', 'AFTER ROUND 2 OF 3'],
    ['ROUND_3', 'The advisors are voting on the resolution.', 'ROUND 3 OF 3'],
    ['VERIFYING', 'The chair is checking the verdict.', 'FINAL CHECKS'],
    ['COMPLETED', 'The council has reached its verdict.', 'VERDICT'],
  ];
  for (const [st, headline, label] of table) {
    const m = S.create(record());
    S.apply(m, stateFrame(1, st));
    const v = S.view(m, 0);
    assert.equal(v.round.headline, headline, st);
    assert.equal(v.round.label, label, st);
  }
  const m = S.create(record());
  S.apply(m, stateFrame(1, 'ROUND_1'));
  assert.equal(
    S.view(m, 0).round.explain,
    'Each advisor writes an independent position on Claude Code (sonnet-test). Their lines play here as soon as the round is in.',
  );
  // A raw route id never reaches the explainer: a friendly label stands in.
  assert.equal(S.routeLabel('demo-replay', null), 'Sample replay');
  assert.equal(S.routeLabel('deepseek-configured', 'latest_deepseek_flash'), 'DeepSeek (newest DeepSeek Flash)');
  assert.equal(S.routeLabel('claude-nine-configured', 'harness_default'), 'Claude Code (Nine)');
  for (const id of ['google', 'ollama', 'openrouter', 'agnes', '9router', 'openai']) {
    const name = S.routeLabel(id + '-configured', null);
    assert.notEqual(name, 'the selected model', id);
    assert.equal(name.includes('configured'), false, id);
  }
  assert.equal(S.routeLabel('some-new-route', 'glm-5.3'), 'glm-5.3');
  assert.equal(S.routeLabel('some-new-route', null), 'the selected model');
  assert.equal(S.routeLabel(null, null), '');
  const sample = S.create({ session_id: 'x', brief: { question: 'q', options: OPTIONS }, spec: { mode: 'consult', seat_ids: ['simon-sinek'], model_policy: { route_id: 'demo-replay', requested_model_id: null } } });
  S.apply(sample, stateFrame(1, 'ROUND_1'));
  assert.equal(S.view(sample, 0).round.explain, 'Each advisor writes an independent position on Sample replay. Their lines play here as soon as the round is in.');
  const bare = S.create({ session_id: 'x', brief: { question: 'q', options: OPTIONS } });
  S.apply(bare, stateFrame(1, 'ROUND_1'));
  assert.equal(S.view(bare, 0).round.explain, 'Each advisor writes an independent position. Their lines play here as soon as the round is in.');
});

test('the round denominator and its labels follow the council size', () => {
  const S = loadState();
  const sized = (mode: string, seats: string[] = SEATS): Record<string, unknown> =>
    record({ spec: { mode, seat_ids: seats, model_policy: { route_id: 'claude-configured', requested_model_id: 'sonnet-test' } } });

  const cases: Array<[string, number, string[]]> = [
    ['light', 2, SEATS],
    ['medium', 4, SEATS],
    ['heavy', 10, SEATS],
    // The four older modes keep their three-round denominator.
    ['full', 3, SEATS],
    ['selected', 3, SEATS.slice(0, 4)],
    ['quick', 3, SEATS.slice(0, 4)],
  ];
  for (const [mode, total, seats] of cases) {
    for (const st of ['ROUND_1', 'ROUND_2', 'CRUX_REVIEW', 'DRAFT_RESOLUTION']) {
      const m = S.create(sized(mode, seats));
      S.apply(m, stateFrame(1, st));
      const v = S.view(m, 0);
      assert.equal(v.round.total, total, `${mode} ${st} total`);
      const n = st === 'ROUND_1' || st === 'CRUX_REVIEW' ? 1 : 2;
      const after = st === 'CRUX_REVIEW' || st === 'DRAFT_RESOLUTION' ? 'AFTER ROUND ' : 'ROUND ';
      assert.equal(v.round.label, after + n + ' OF ' + total, `${mode} ${st} label`);
    }
  }
});

test('a light council shows two rounds, never a third', () => {
  const S = loadState();
  const m = S.create(
    record({ spec: { mode: 'light', seat_ids: SEATS, model_policy: { route_id: 'r', requested_model_id: null } } }),
  );
  S.apply(m, stateFrame(1, 'ROUND_1'));
  assert.equal(S.view(m, 0).round.label, 'ROUND 1 OF 2');
  S.apply(m, stateFrame(2, 'CRUX_REVIEW'));
  assert.equal(S.view(m, 0).round.label, 'AFTER ROUND 1 OF 2');
  S.apply(m, stateFrame(3, 'ROUND_2'));
  assert.equal(S.view(m, 0).round.label, 'ROUND 2 OF 2');
  S.apply(m, stateFrame(4, 'DRAFT_RESOLUTION'));
  assert.equal(S.view(m, 0).round.label, 'AFTER ROUND 2 OF 2');
});

test('a heavy council counts and renders rounds past three', () => {
  const S = loadState();
  const m = S.create(
    record({ spec: { mode: 'heavy', seat_ids: SEATS, model_policy: { route_id: 'r', requested_model_id: null } } }),
  );
  S.apply(m, stateFrame(1, 'ROUND_1'));
  assert.equal(S.view(m, 0).round.label, 'ROUND 1 OF 10');
  S.apply(m, frame(2, 'card_accepted', { payload: { seat_id: 'simon-sinek', round: 6 } }));
  S.applyRecord(m, { cards: [card('simon-sinek', 6, 'A')] });
  const v = S.view(m, 0);
  assert.equal(v.votesRound, 6, 'the tally round follows the cards, not a fixed 1..3');
  assert.equal(v.round.total, 10);
  const seat = v.seats.find((s: Any) => s.id === 'simon-sinek');
  assert.equal(seat.cards[6].kind, 'advisor');
  assert.equal(seat.cards[6].line, 'simon-sinek argument r6');

  // Round 3 is an ordinary advisor round in heavy, never the vote pass.
  S.apply(m, frame(3, 'card_accepted', { payload: { seat_id: 'td-jakes', round: 3 } }));
  const pending = S.view(m, 0).seats.find((s: Any) => s.id === 'td-jakes');
  assert.equal(pending.cards[3].kind, 'advisor');
  assert.equal(pending.cards[3].pending, true);
});

test('verdict label text and key point', () => {
  const S = loadState();
  const texts: Record<string, string> = {
    GO: 'Go', GO_WITH_CONDITIONS: 'Go, with conditions', RESHAPE: 'Reshape', DONT_DO_IT: "Don't do it",
    WAIT: 'Wait', INSUFFICIENT_EVIDENCE: 'Not enough evidence',
  };
  for (const [label, labelText] of Object.entries(texts)) {
    const m = S.create(record({ verdict: { result_kind: 'scored', label, recommended_option_id: null, main_reasons: ['r1'], option_scores: [] } }));
    S.apply(m, stateFrame(1, 'COMPLETED'));
    const v = S.view(m, 0);
    assert.equal(v.verdict.labelText, labelText);
    assert.deepEqual(plain(v.verdict.reasons), ['r1']);
    assert.equal(v.keyPoints[v.keyPoints.length - 1].label, 'VERDICT: ' + labelText.toUpperCase());
    assert.equal(v.keyPoints[v.keyPoints.length - 1].detail, null);
  }
  // Until the verdict is read, no verdict line is invented.
  const none = S.create(record());
  S.apply(none, stateFrame(1, 'COMPLETED'));
  assert.equal(S.view(none, 0).verdict, null);
  assert.equal(S.view(none, 0).keyPoints.length, 0, 'no key point carries a made-up verdict');
});

// ------------------------------------------------------------------ timer

test('timer counts the time in the current state and freezes at terminal', () => {
  const S = loadState();
  const m = S.create(record());
  S.apply(m, stateFrame(1, 'ROUND_1', '2026-10-19T10:00:00.000Z'));
  const t0 = Date.parse('2026-10-19T10:00:00.000Z');
  assert.equal(S.view(m, t0 + 5_000).round.timer, '0:05');
  assert.equal(S.view(m, t0 + 91_000).round.timer, '1:31');
  assert.equal(S.view(m, t0 - 4_000).round.timer, '0:00', 'a client clock behind the server never shows a negative');
  S.apply(m, stateFrame(2, 'COMPLETED', '2026-10-19T10:03:07.000Z'));
  assert.equal(S.view(m, Date.parse('2026-10-19T10:03:07.000Z')).round.timer, '3:07', 'finished: the whole session, frozen');
  assert.equal(S.view(m, Date.parse('2026-10-19T12:00:00.000Z')).round.timer, '3:07');
  const m2 = S.create(record());
  S.apply(m2, stateFrame(1, 'ROUND_1', '2026-10-19T10:00:00.000Z'));
  S.apply(m2, stateFrame(2, 'FAILED', '2026-10-19T10:02:03.000Z'));
  assert.equal(S.view(m2, Date.parse('2026-10-19T10:30:00.000Z')).round.timer, '2:03', 'a failed session freezes at its own duration');
  const m3 = S.create(record());
  S.apply(m3, stateFrame(1, 'VERIFYING', '2026-10-19T10:00:00.000Z'));
  S.apply(m3, stateFrame(2, 'COMPLETED', '2026-10-19T10:01:00.000Z'));
  const a = S.view(m3, Date.parse('2026-10-19T10:05:00.000Z')).round.timer;
  const b = S.view(m3, Date.parse('2026-10-19T11:05:00.000Z')).round.timer;
  assert.equal(a, b);
});

// -------------------------------------------------------------- spotlight

function serviceRound1(): Any {
  const S = loadState();
  const m = S.create(record());
  S.apply(m, stateFrame(1, 'ROUND_1', '2026-10-19T10:00:00.000Z'));
  return { S, m };
}

test('operation frames (even ones whose id names a seat) never change who is typing; the spotlight keeps rotating', () => {
  const { S, m } = serviceRound1();
  const t = Date.parse('2026-10-19T10:00:00.000Z');
  const hash = (n: number): string => `op:i:t:s:a1:round-1:${SEATS[n]}:${n.toString(16).padStart(8, 'a')}`;
  // A reservation, then the gap after a completion, then the next reservation.
  S.apply(m, frame(2, 'operation_reserved', { payload: { operation_id: hash(0) } }));
  const check = (dt: number, finished: string[]): void => {
    const v = S.view(m, t + dt);
    const left = SEATS.filter((id) => !finished.includes(id));
    assert.deepEqual(plain(v.seats.filter((s: Any) => s.status === 'writing').map((s: Any) => s.id)), left, `writing at ${dt}`);
    assert.equal(v.seats.filter((s: Any) => s.bubble.kind === 'typing').length, left.length);
    assert.equal(v.seats.filter((s: Any) => s.spotlight).length, 1, `one spotlight at ${dt}`);
    assert.equal(v.round.weighing.kind, 'weighing');
    assert.equal(v.round.weighing.seatId, left[Math.floor(dt / 6000) % left.length]);
  };
  check(0, []);
  check(6_000, []);
  S.apply(m, frame(3, 'card_accepted', { payload: { operation_id: hash(0), seat_id: 'simon-sinek', round: 1 } }));
  S.apply(m, frame(4, 'operation_completed', { payload: { operation_id: hash(0) } }));
  // Gap: nothing reserved right now, yet every unfinished seat still types and one is spotlit.
  check(6_400, ['simon-sinek']);
  check(12_000, ['simon-sinek']);
  S.apply(m, frame(5, 'operation_reserved', { payload: { operation_id: hash(1) } }));
  check(12_100, ['simon-sinek']);
  const v = S.view(m, t + 1000);
  assert.equal(v.seats.find((s: Any) => s.id === 'simon-sinek').bubble.kind, 'done');
  assert.equal(v.round.progress.indeterminate, false);
  assert.equal(v.round.progressText, '1 of 9 advisors in');
});

test('without reservations the spotlight rotates deterministically every 6 seconds', () => {
  const { S, m } = serviceRound1();
  const t = Date.parse('2026-10-19T10:00:00.000Z');
  const lead = (ms: number): string => {
    const v = S.view(m, ms);
    const one = v.seats.filter((s: Any) => s.spotlight);
    assert.equal(one.length, 1, 'exactly one spotlight');
    assert.equal(v.round.weighing.seatId, one[0].id);
    return one[0].id;
  };
  assert.equal(S.view(m, t).seats.every((s: Any) => s.status === 'writing' && s.bubble.kind === 'typing'), true);
  assert.equal(lead(t), SEATS[0]);
  assert.equal(lead(t + 5_999), SEATS[0]);
  assert.equal(lead(t + 6_000), SEATS[1]);
  assert.equal(lead(t + 12_500), SEATS[2]);
  assert.equal(lead(t + 6_000 * 9), SEATS[0], 'wraps around the nine seats');
  assert.equal(lead(t + 12_500), lead(t + 12_500), 'same input, same answer');
  // A finished seat leaves the rotation.
  S.apply(m, frame(2, 'card_accepted', { payload: { seat_id: 'simon-sinek', round: 1 } }));
  assert.equal(lead(t + 5_000), SEATS[1]);
  assert.equal(S.view(m, t).round.progress.indeterminate, false);
});

test('progress is indeterminate until the first card of a round', () => {
  const { S, m } = serviceRound1();
  const v = S.view(m, 0);
  assert.deepEqual(plain(v.round.progress), { indeterminate: true, value: 0 });
  S.apply(m, frame(2, 'card_accepted', { payload: { seat_id: 'td-jakes', round: 1 } }));
  assert.deepEqual(plain(S.view(m, 0).round.progress), { indeterminate: false, value: 1 / 9 });
  assert.equal(S.view(m, 0).round.complete, false);
  for (const id of SEATS) S.apply(m, frame(10 + SEATS.indexOf(id), 'card_accepted', { payload: { seat_id: id, round: 1 } }));
  const full = S.view(m, 0);
  assert.deepEqual(plain(full.round.progress), { indeterminate: false, value: 1 });
  assert.equal(full.round.complete, true);
});

// ---------------------------------------------------------------- playback

test('said lines play back in seat order, every 7 seconds, after a round is in and through the chair phase', () => {
  const S = loadState();
  const m = S.create(record());
  const t0 = Date.parse('2026-10-19T10:00:00.000Z');
  S.apply(m, stateFrame(1, 'ROUND_1', '2026-10-19T10:00:00.000Z'));
  SEATS.forEach((id, i) => S.apply(m, frame(2 + i, 'card_accepted', { payload: { seat_id: id, round: 1 }, created_at: '2026-10-19T10:00:09.000Z' })));
  S.applyRecord(m, { cards: SEATS.map((id) => card(id, 1, 'B')) });
  const done = t0 + 9_000;
  let v = S.view(m, done);
  assert.equal(v.round.complete, true);
  assert.deepEqual(plain(v.round.weighing), { seatId: 'simon-sinek', kind: 'said', text: 'simon-sinek argument r1' });
  assert.equal(v.seats[0].spotlight, true);
  assert.deepEqual(plain(v.seats[0].bubble), { kind: 'line', text: 'simon-sinek argument r1' });
  assert.equal(v.seats[1].bubble.kind, 'done');
  assert.equal(S.view(m, done + 6_999).round.weighing.seatId, 'simon-sinek');
  assert.equal(S.view(m, done + 7_000).round.weighing.seatId, 'td-jakes');
  assert.equal(S.view(m, done + 7_000 * 9).round.weighing.seatId, 'simon-sinek');
  // The next chair phase keeps playing the same round's lines.
  S.apply(m, stateFrame(20, 'CRUX_REVIEW', '2026-10-19T10:00:10.000Z'));
  v = S.view(m, done + 14_000);
  assert.deepEqual(plain(v.round.weighing), { seatId: 'oprah-winfrey', kind: 'said', text: 'oprah-winfrey argument r1' });
  // Round 2 starts: back to writing.
  S.apply(m, stateFrame(21, 'ROUND_2', '2026-10-19T10:00:20.000Z'));
  v = S.view(m, t0 + 21_000);
  assert.equal(v.round.weighing.kind, 'weighing');
  assert.equal(v.seats.every((s: Any) => s.status === 'writing'), true);
});

test('chair weighing shows when there are no lines to play yet', () => {
  const S = loadState();
  const m = S.create(record());
  S.apply(m, stateFrame(1, 'CRUX_REVIEW'));
  assert.deepEqual(plain(S.view(m, 0).round.weighing), { seatId: null, kind: 'chair', text: 'which disagreements would change the decision' });
  assert.equal(S.view(m, 0).seats.some((s: Any) => s.spotlight), false);
});

// ----------------------------------------------------------------- tallies

test('cards never reveal content before applyRecord; accepted cards are pending', () => {
  const S = loadState();
  const m = S.create(record());
  S.apply(m, stateFrame(1, 'ROUND_1'));
  S.apply(m, frame(2, 'card_accepted', { payload: { seat_id: 'les-brown', round: 1 } }));
  let v = S.view(m, 0);
  const les = v.seats.find((s: Any) => s.id === 'les-brown');
  assert.equal(les.status, 'done');
  assert.deepEqual(plain(les.latest), {
    round: 1, kind: 'advisor', stance: null, stanceText: null, preferredOptionId: null, preferredLetter: null,
    line: null, resolutionStance: null, pending: true,
  });
  assert.equal(v.votesRound, null);
  assert.equal(v.options[0].votes, null);
  S.applyRecord(m, { cards: [card('les-brown', 1, 'B')] });
  v = S.view(m, 0);
  const full = v.seats.find((s: Any) => s.id === 'les-brown').latest;
  assert.equal(full.pending, false);
  assert.equal(full.line, 'les-brown argument r1');
  assert.equal(full.stanceText, 'Supports');
  assert.equal(full.preferredLetter, 'B');
});

test('tallies and recommended come from applyRecord cards and verdict', () => {
  const S = loadState();
  const m = S.create(record());
  S.apply(m, stateFrame(1, 'ROUND_2'));
  const prefs = ['A', 'B', 'B', 'B', 'C', 'B', null, 'A', 'B'];
  S.applyRecord(m, { cards: SEATS.map((id, i) => card(id, 1, 'A')).concat(SEATS.slice(0, 9).map((id, i) => card(id, 2, prefs[i]))) });
  let v = S.view(m, 0);
  assert.equal(v.votesRound, 2);
  assert.equal(v.voters, 9);
  assert.deepEqual(plain(v.options.map((o: Any) => o.votes)), [2, 5, 1]);
  assert.deepEqual(plain(v.options.map((o: Any) => Math.round(o.share * 900))), [200, 500, 100]);
  assert.equal(v.options.some((o: Any) => o.recommended), false);
  assert.deepEqual(plain(v.options.map((o: Any) => o.score)), [null, null, null]);

  // A later round's partial content moves the tally to that round.
  S.applyRecord(m, { cards: [card('simon-sinek', 3, 'C')] });
  v = S.view(m, 0);
  assert.equal(v.votesRound, 3);
  assert.equal(v.voters, 1);
  assert.deepEqual(plain(v.options.map((o: Any) => o.votes)), [0, 0, 1]);
  // share is votes over ALL seats (1 of 9), not over the one seat that has voted so far.
  assert.deepEqual(plain(v.options.map((o: Any) => Math.round(o.share * 900))), [0, 0, 100]);

  S.applyRecord(m, {
    verdict: {
      result_kind: 'scored', label: 'GO', recommended_option_id: 'B', main_reasons: [],
      option_scores: [
        { option_id: 'A', display_score: 4.2 }, { option_id: 'B', display_score: 8.1 }, { option_id: 'C', display_score: null },
      ],
    },
  });
  v = S.view(m, 0);
  assert.deepEqual(plain(v.options.map((o: Any) => o.recommended)), [false, true, false]);
  assert.deepEqual(plain(v.options.map((o: Any) => o.score)), [4.2, 8.1, null]);
  assert.equal(v.verdict.recommendedOptionId, 'B');
});

test('card line: advisor argument, ratification objection or amendment, consult answer', () => {
  const S = loadState();
  const m = S.create(record());
  S.applyRecord(m, {
    cards: [
      { card_kind: 'advisor', seat_id: 'simon-sinek', round: 1, stance: 'conditional', preferred_option_id: 'C', decisive_arguments: ['first', 'second'] },
      { card_kind: 'ratification', seat_id: 'simon-sinek', round: 3, stance: 'oppose', resolution_stance: 'conditional_support', preferred_option_id: 'B',
        unresolved_objections: [], amendments: [{ statement: 'amend it' }] },
      { card_kind: 'ratification', seat_id: 'td-jakes', round: 3, stance: 'support', resolution_stance: 'support', preferred_option_id: 'B', unresolved_objections: ['obj'], amendments: [] },
      { card_kind: 'ratification', seat_id: 'oprah-winfrey', round: 3, stance: 'abstain', resolution_stance: 'abstain', preferred_option_id: null, unresolved_objections: [], amendments: [] },
      { card_kind: 'consult', seat_id: 'les-brown', answer: 'the answer' },
    ],
  });
  const v = S.view(m, 0);
  const by = (id: string): Any => v.seats.find((s: Any) => s.id === id);
  assert.equal(by('simon-sinek').cards[1].line, 'first');
  assert.equal(by('simon-sinek').cards[1].stanceText, 'Supports with conditions');
  assert.equal(by('simon-sinek').cards[1].preferredLetter, 'C');
  assert.equal(by('simon-sinek').cards[3].line, 'amend it');
  assert.equal(by('simon-sinek').cards[3].kind, 'ratification');
  assert.equal(by('simon-sinek').cards[3].resolutionStance, 'conditional_support');
  assert.equal(by('simon-sinek').latest.round, 3);
  assert.equal(by('td-jakes').cards[3].line, 'obj');
  assert.equal(by('oprah-winfrey').cards[3].line, null);
  assert.equal(by('oprah-winfrey').cards[3].stanceText, 'Abstains');
  assert.equal(by('les-brown').cards[1].kind, 'consult');
  assert.equal(by('les-brown').cards[1].line, 'the answer');
});

// ------------------------------------------------------------- demo replay

test('the demo replay reaches COMPLETED with a verdict through create/apply/applyRecord', () => {
  const S = loadState();
  const demo: Any = JSON.parse(readFileSync(join(chamberDir, 'demo-replay.json'), 'utf8'));
  assert.equal(demo.schema, 'chamber-demo/v1');
  assert.match(demo.label, /fictional/);
  assert.match(demo.label, /^Demo replay:/);
  assert.equal(demo.record.demo, true);
  assert.equal(demo.record.sample, true);
  assert.equal(demo.record.session_id, 'demo');
  assert.deepEqual(demo.record.spec.seat_ids, SEATS);
  assert.deepEqual(demo.record.spec.model_policy, { route_id: 'demo-replay', requested_model_id: null });
  assert.equal(demo.record.brief.options.length, 4);
  assert.equal(demo.cards.length, 27);

  const m = S.create(demo.record);
  assert.equal(S.view(m, 0).keyPoints.length, 0);
  let lastAt = -1;
  const revealed: Record<string, boolean> = {};
  let beforeCard = 0;
  for (const { at_ms, frame: f } of demo.timeline) {
    assert.ok(at_ms >= lastAt, 'timeline is in order');
    lastAt = at_ms;
    assert.equal(S.apply(m, f), true);
    const p = f.payload ?? {};
    if (f.type === 'card_accepted') {
      // Content is withheld until this frame plays.
      const key = `${p.seat_id}:${p.round}`;
      const before = S.view(m, 0).seats.find((s: Any) => s.id === p.seat_id).cards[p.round];
      assert.equal(before.pending, true, key + ' pending when accepted');
      beforeCard += 1;
      S.applyRecord(m, { cards: demo.cards.filter((c: Any) => c.seat_id === p.seat_id && c.round === p.round) });
      revealed[key] = true;
    } else if (f.type === 'verdict_validated') {
      assert.equal(S.view(m, 0).verdict, null);
      S.applyRecord(m, { verdict: demo.verdict });
    }
  }
  assert.equal(beforeCard, 27);
  assert.ok(lastAt >= 90_000 && lastAt <= 110_000, `about 100 seconds, got ${lastAt}`);
  const v = S.view(m, Date.parse(demo.timeline[demo.timeline.length - 1].frame.created_at));
  assert.equal(v.state, 'COMPLETED');
  assert.equal(v.demo, true);
  assert.equal(v.sample, true);
  assert.ok(v.verdict);
  assert.equal(v.verdict.labelText, 'Go, with conditions');
  assert.equal(v.verdict.recommendedOptionId, 'B');
  assert.deepEqual(stepStatuses(v), ALL_DONE);
  for (const seat of v.seats) {
    for (const r of [1, 2, 3]) assert.ok(seat.cards[r] && seat.cards[r].line, `${seat.id} has a line for round ${r}`);
  }
  assert.deepEqual(plain(v.keyPoints.map((k: Any) => k.label)), [...COPY_ORDER, 'VERDICT: GO, WITH CONDITIONS']);
  assert.equal(v.votesRound, 3);
  assert.equal(v.options.find((o: Any) => o.recommended).letter, 'B');
  // Every line is a distinct sentence in that seat's own voice.
  const lines = new Set(v.seats.flatMap((s: Any) => [1, 2, 3].map((r) => s.cards[r].line)));
  assert.equal(lines.size, 27);
});

test('during every demo round each unfinished seat types and exactly one is spotlit, with no gaps', () => {
  const S = loadState();
  const demo: Any = JSON.parse(readFileSync(join(chamberDir, 'demo-replay.json'), 'utf8'));
  const m = S.create(demo.record);
  let checked = 0;
  for (const { frame: f } of demo.timeline) {
    S.apply(m, f);
    const p = f.payload ?? {};
    if (f.type === 'card_accepted') S.applyRecord(m, { cards: demo.cards.filter((c: Any) => c.seat_id === p.seat_id && c.round === p.round) });
    const t = Date.parse(f.created_at);
    for (const dt of [0, 100, 250, 399]) {
      const v = S.view(m, t + dt);
      if (!/^ROUND_[123]$/.test(v.state) || v.round.complete) continue;
      const open = v.seats.filter((s: Any) => s.status !== 'done');
      assert.equal(open.every((s: Any) => s.status === 'writing' && s.bubble.kind === 'typing'), true, `seq ${f.sequence} +${dt}`);
      assert.equal(v.seats.filter((s: Any) => s.spotlight).length, 1, `one spotlight at seq ${f.sequence} +${dt}`);
      assert.ok(v.round.weighing && v.round.weighing.kind === 'weighing', `weighing line at seq ${f.sequence} +${dt}`);
      checked += 1;
    }
  }
  assert.ok(checked > 100, `checked ${checked} samples`);
});

test('the demo gives every seat its turn as the speaker in each round, in the real browser pace', () => {
  const S = loadState();
  const demo: Any = JSON.parse(readFileSync(join(chamberDir, 'demo-replay.json'), 'utf8'));
  const m = S.create(demo.record);
  const said: Record<number, Set<string>> = { 1: new Set(), 2: new Set(), 3: new Set() };
  const base = Date.parse(demo.timeline[0].frame.created_at) - demo.timeline[0].at_ms;
  let i = 0;
  const end = demo.timeline[demo.timeline.length - 1].at_ms;
  for (let at = 0; at <= end; at += 250) {
    while (i < demo.timeline.length && demo.timeline[i].at_ms <= at) {
      const f = demo.timeline[i++].frame;
      S.apply(m, f);
      const p = f.payload ?? {};
      if (f.type === 'card_accepted') S.applyRecord(m, { cards: demo.cards.filter((c: Any) => c.seat_id === p.seat_id && c.round === p.round) });
    }
    const v = S.view(m, base + at);
    const w = v.round.weighing;
    if (w && w.kind === 'said') said[v.round.complete ? v.round.number : /CRUX/.test(v.state) ? 1 : /DRAFT_RES/.test(v.state) ? 2 : 3].add(w.seatId);
  }
  for (const r of [1, 2, 3]) assert.deepEqual([...said[r]].sort(), [...demo.record.spec.seat_ids].sort(), `round ${r}`);
});
