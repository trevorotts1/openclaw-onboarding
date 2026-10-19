/**
 * W29-E seat card tests.
 *
 * Runner:
 *   node --import tsx --test tests/chamber-seatcard.test.ts
 *
 * Loads chamber-seatcard.js in node:vm (no document, so only the pure API
 * is installed) and checks the exact status strings, plus static guards on
 * the shipped files (no innerHTML, no colour literals, .ch-card-* prefix).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
const jsSource = readFileSync(join(chamberDir, 'chamber-seatcard.js'), 'utf8');
const cssSource = readFileSync(join(chamberDir, 'chamber-seatcard.css'), 'utf8');

interface Status {
  lead: string;
  quote: string | null;
}
interface Seatcard {
  statusLine(seatView: unknown, options: unknown): Status;
}

function load(): Seatcard {
  const sandbox: Record<string, unknown> = {};
  sandbox.globalThis = sandbox;
  runInNewContext(jsSource, sandbox);
  return (sandbox.councilChamber as { seatcard: Seatcard }).seatcard;
}

/** vm objects have another realm's prototypes; compare plain copies. */
const plain = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

const options = [
  { id: 'opt-a', letter: 'A', label: 'Launch to all clients in January' },
  { id: 'opt-b', letter: 'B', label: 'Pilot with 10 clients first' },
];
const advisor = {
  round: 1,
  kind: 'advisor',
  stance: 'support',
  stanceText: 'Supports',
  preferredOptionId: 'opt-b',
  preferredLetter: 'B',
  line: 'Start small and learn.',
  resolutionStance: null,
  pending: false,
};

test('no latest card: has not spoken yet, no quote', () => {
  const { statusLine } = load();
  const expected = { lead: 'This seat has not spoken yet.', quote: null };
  assert.deepEqual(plain(statusLine({ status: 'idle', latest: null }, options)), expected);
  assert.deepEqual(plain(statusLine(null, options)), expected);
  assert.deepEqual(plain(statusLine({ status: 'writing', latest: null }, options)), expected);
});

test('pending card: position is in, line still loading', () => {
  const { statusLine } = load();
  const got = statusLine({ status: 'done', latest: { ...advisor, pending: true, line: null } }, options);
  assert.deepEqual(plain(got), { lead: 'Round 1 position is in. Loading its line…', quote: null });
});

test('advisor card: stance, letter, option label and the decisive line', () => {
  const { statusLine } = load();
  const got = statusLine({ status: 'done', latest: advisor }, options);
  assert.deepEqual(plain(got), {
    lead: 'Round 1: Supports B, Pilot with 10 clients first',
    quote: 'Start small and learn.',
  });
});

test('advisor card with an unknown option keeps the letter and drops the label', () => {
  const { statusLine } = load();
  const got = statusLine({ status: 'done', latest: { ...advisor, preferredOptionId: 'gone' } }, options);
  assert.equal(got.lead, 'Round 1: Supports B');
});

test('ratification card maps every resolution stance to words', () => {
  const { statusLine } = load();
  const words: Record<string, string> = {
    support: 'Supports',
    conditional_support: 'Supports with conditions',
    oppose: 'Opposes',
    abstain: 'Abstains',
  };
  for (const [stance, word] of Object.entries(words)) {
    const latest = { round: 3, kind: 'ratification', resolutionStance: stance, line: 'Mind the cash.', pending: false };
    assert.deepEqual(plain(statusLine({ status: 'done', latest }, options)), {
      lead: `Round 3 vote: ${word} the draft resolution`,
      quote: 'Mind the cash.',
    });
  }
});

test('consult card', () => {
  const { statusLine } = load();
  const latest = { round: 1, kind: 'consult', line: 'Wait a quarter.', pending: false };
  assert.deepEqual(plain(statusLine({ status: 'done', latest }, options)), {
    lead: 'Consult answer',
    quote: 'Wait a quarter.',
  });
});

test('writing with a previous card appends the next round note', () => {
  const { statusLine } = load();
  const got = statusLine({ status: 'writing', latest: advisor }, options);
  assert.equal(got.lead, 'Round 1: Supports B, Pilot with 10 clients first Writing its round 2 position now.');
  assert.equal(got.quote, 'Start small and learn.');
});

test('shipped files: no innerHTML, no colour literals, scoped class names', () => {
  assert.doesNotMatch(jsSource, /innerHTML|outerHTML|insertAdjacentHTML|https?:\/\//);
  assert.doesNotMatch(cssSource, /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/);
  const classes = [...cssSource.matchAll(/\.(ch-[a-z0-9-]+)/g)].map((m) => m[1] as string);
  const allowed = /^ch-(card(-|$)|dialog$|btn$|eyebrow$)/;
  for (const c of classes) assert.match(c, allowed, `${c} is outside the .ch-card-* prefix`);
  for (const m of cssSource.matchAll(/var\((--[a-z0-9-]+)/g)) {
    assert.match(m[1] as string, /^--ch-/, `${m[1]} must be a --ch-* token`);
  }
});
