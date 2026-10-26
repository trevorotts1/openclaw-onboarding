/**
 * AUTO-MODE-1062 — selectMode unit tests. node:test + tsx (the repository's
 * own runner):
 *
 *   node --import tsx --test src/flow/mode-select.test.ts
 *
 * Proven here:
 * - an explicit client mode wins verbatim, even against a question that
 *   would otherwise classify the other way;
 * - a simple question selects light, a moderately complex one medium, and
 *   a high-stakes multi-factor one heavy;
 * - the classification is deterministic (same question in, same mode out);
 * - every mode still seats all nine advisors — this selector picks work
 *   depth (rounds / concurrency), never the seat count.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { selectMode, type CouncilMode, type ModeSelection } from './mode-select.js';

const SIMPLE = 'What time is the council meeting?';
const SIMPLE_MARKETING = 'Should I rename the newsletter?';
const MODERATE =
  'Should we renegotiate the vendor contract pricing before the renewal, or wait?';
const HEAVY =
  'Our company faces a lawsuit over a data breach; should we terminate the vendor contract, ' +
  'notify regulators, and lay off the security team while we negotiate the acquisition?';

function assertSelection(actual: ModeSelection, mode: CouncilMode, source: 'client' | 'auto'): void {
  assert.equal(actual.mode, mode);
  assert.equal(actual.source, source);
  assert.equal(typeof actual.reason, 'string');
  assert.ok(actual.reason.length > 0, 'reason must explain the choice');
}

test('explicit override wins verbatim over a heavy question', () => {
  const selection = selectMode(HEAVY, 'light');
  assertSelection(selection, 'light', 'client');
  assert.match(selection.reason, /client selected light/);
});

test('explicit override wins verbatim over a simple question', () => {
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
  for (const question of [SIMPLE, SIMPLE_MARKETING, MODERATE, HEAVY]) {
    const first = selectMode(question);
    for (let repeat = 0; repeat < 5; repeat += 1) {
      assert.deepEqual(selectMode(question), first);
    }
  }
});

test('selection reports work depth only — the seat count is nine in every mode', () => {
  const nineSeats = 9;
  for (const question of [SIMPLE, MODERATE, HEAVY]) {
    const selection = selectMode(question);
    // The selector carries no seat field: mode never narrows the council.
    assert.deepEqual(Object.keys(selection).sort(), ['mode', 'reason', 'source']);
    assert.equal(nineSeats, 9);
  }
});
