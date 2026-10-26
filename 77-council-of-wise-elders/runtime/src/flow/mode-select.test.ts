/**
 * AUTO-MODE-1062 — selectMode unit tests. node:test + tsx (the repository's
 * own runner):
 *
 *   node --import tsx --test src/flow/mode-select.test.ts
 *
 * Proven here:
 * - an explicit client mode wins, even against a question that would
 *   otherwise classify the other way;
 * - EVERY canonical SESSION_MODES value is honoured explicitly and resolves
 *   to a deterministic council size — adding a mode to the enum without a
 *   mapping turns this file red;
 * - a simple question selects light, a moderately complex one medium, and
 *   a high-stakes multi-factor one heavy;
 * - the classification is deterministic (same question in, same mode out);
 * - every mode still seats the full roster the runtime enforces (SEAT_IDS),
 *   not a literal — this selector picks work depth, never the seat count;
 * - stake matching survives inflection (lawsuit/lawsuits, sue/suing/sued,
 *   merger/mergers, loan/loans);
 * - a negated stake term ("no legal risk") is not high stakes.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { SEAT_IDS, SESSION_MODES } from '../contracts/enums.js';
import { COUNCIL_SIZES, MODE_ROUND_POLICY, isCouncilSize } from '../contracts/modes.js';
import { selectMode, type CouncilMode, type ModeSelection } from './mode-select.js';

const SIMPLE = 'What time is the council meeting?';
const SIMPLE_MARKETING = 'Should I rename the newsletter?';
const MODERATE =
  'Should we renegotiate the vendor contract pricing before the renewal, or wait?';
const HEAVY =
  'Our company faces a lawsuit over a data breach; should we terminate the vendor contract, ' +
  'notify regulators, and lay off the security team while we negotiate the acquisition?';

/** Same subject as HEAVY, scored by stake terms only. */
const LAWSUIT_SINGULAR = 'What does the lawsuit say?';
const LAWSUIT_PLURAL = 'What do the lawsuits say?';
const INFLECTED_STAKES =
  'Three investors are suing; the mergers collapsed and the loans are due.';

const NEGATED_STAKES =
  'We have no legal risk and no contract issue; should I rename the newsletter?';
/** NEGATED_STAKES with the negators removed: the control that proves the check bites. */
const UNNEGATED_STAKES =
  'We have legal risk and a contract issue; should I rename the newsletter?';

const CORPUS = [
  SIMPLE,
  SIMPLE_MARKETING,
  MODERATE,
  HEAVY,
  LAWSUIT_SINGULAR,
  LAWSUIT_PLURAL,
  INFLECTED_STAKES,
  NEGATED_STAKES,
];

function assertSelection(actual: ModeSelection, mode: CouncilMode, source: 'client' | 'auto'): void {
  assert.equal(actual.mode, mode);
  assert.equal(actual.source, source);
  assert.equal(typeof actual.reason, 'string');
  assert.ok(actual.reason.length > 0, 'reason must explain the choice');
}

function assertAtLeastMedium(question: string): void {
  const selection = selectMode(question);
  assert.ok(
    selection.mode === 'medium' || selection.mode === 'heavy',
    `${question} scored ${selection.reason} but must land medium or heavy, never light`,
  );
}

test('explicit override wins over a heavy question', () => {
  const selection = selectMode(HEAVY, 'light');
  assertSelection(selection, 'light', 'client');
  assert.match(selection.reason, /client selected light/);
});

test('explicit override wins over a simple question', () => {
  assertSelection(selectMode(SIMPLE, 'heavy'), 'heavy', 'client');
});

test('explicit override is matched case-insensitively and trimmed', () => {
  assertSelection(selectMode(MODERATE, ' LIGHT '), 'light', 'client');
});

test('an unrecognized explicit value is not a mode and falls back to automatic', () => {
  const selection = selectMode(HEAVY, 'turbo');
  assertSelection(selection, 'heavy', 'auto');
  assert.match(selection.reason, /complexity score/);
});

test('every canonical session mode is explicit and resolves to a deterministic size', () => {
  for (const sessionMode of SESSION_MODES) {
    const selection = selectMode(HEAVY, sessionMode);
    assert.equal(
      selection.source,
      'client',
      `${sessionMode} is a canonical SESSION_MODES value and must not fall through to auto`,
    );
    assert.ok(
      isCouncilSize(selection.mode),
      `${sessionMode} must resolve to a council size the round policy knows`,
    );
    assert.deepEqual(
      selectMode(HEAVY, sessionMode),
      selection,
      `${sessionMode} must resolve to the same size every time`,
    );
  }
});

test('the four legacy session modes keep their documented council size', () => {
  assertSelection(selectMode(HEAVY, 'full'), 'heavy', 'client');
  assertSelection(selectMode(HEAVY, 'selected'), 'medium', 'client');
  assertSelection(selectMode(HEAVY, 'quick'), 'light', 'client');
  assertSelection(selectMode(HEAVY, 'consult'), 'light', 'client');
});

test('light, medium and heavy pass through unchanged', () => {
  for (const mode of COUNCIL_SIZES) {
    assertSelection(selectMode(SIMPLE, mode), mode, 'client');
  }
});

test('a simple question selects light', () => {
  assertSelection(selectMode(SIMPLE), 'light', 'auto');
});

test('a simple question that names one domain and hedges stays light', () => {
  assertSelection(selectMode(SIMPLE_MARKETING), 'light', 'auto');
});

test('a moderately complex question selects medium', () => {
  assertSelection(selectMode(MODERATE), 'medium', 'auto');
});

test('a high-stakes multi-factor question selects heavy', () => {
  assertSelection(selectMode(HEAVY), 'heavy', 'auto');
});

test('classification is deterministic: same question in, same mode out', () => {
  for (const question of CORPUS) {
    const first = selectMode(question);
    for (let repeat = 0; repeat < 5; repeat += 1) {
      assert.deepEqual(selectMode(question), first);
    }
  }
});

test('stake matching survives inflection: lawsuits, suing, mergers, loans', () => {
  assertAtLeastMedium(LAWSUIT_SINGULAR);
  assertAtLeastMedium(LAWSUIT_PLURAL);
  assertAtLeastMedium(INFLECTED_STAKES);
});

test('a negated stake term is not high stakes', () => {
  const selection = selectMode(NEGATED_STAKES);
  assert.notEqual(
    selection.mode,
    'heavy',
    `${NEGATED_STAKES} scored ${selection.reason}; negated stakes must not select heavy`,
  );
  // Control: the same sentence without the negators is genuinely heavy, so
  // the assertion above fails only when negation handling is broken.
  assertSelection(selectMode(UNNEGATED_STAKES), 'heavy', 'auto');
});

test('every mode the selector returns seats the full runtime roster', () => {
  // The roster the runtime actually enforces, never a literal: if a mode is
  // edited to seat a smaller panel, or the roster shrinks, this goes red.
  for (const size of COUNCIL_SIZES) {
    assert.equal(
      MODE_ROUND_POLICY[size].seats,
      SEAT_IDS.length,
      `${size} must seat all ${SEAT_IDS.length} advisors`,
    );
  }
  for (const question of CORPUS) {
    const selection = selectMode(question);
    assert.ok(isCouncilSize(selection.mode), `${selection.mode} has no round policy`);
    assert.equal(
      MODE_ROUND_POLICY[selection.mode].seats,
      SEAT_IDS.length,
      `${selection.mode} must seat all ${SEAT_IDS.length} advisors`,
    );
    // The selector carries no seat field: mode never narrows the council.
    assert.deepEqual(Object.keys(selection).sort(), ['mode', 'reason', 'source']);
  }
  assert.equal(new Set(SEAT_IDS).size, SEAT_IDS.length, 'the roster has no duplicate seat');
});
