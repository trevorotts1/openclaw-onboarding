/**
 * CTR-149 screen: the results panel reads as an answer, not a jargon dump.
 *
 * UNEXECUTED in this lane (no test runner is allowed here). The integrator runs:
 *   node --import tsx --test tests/chamber-results-ux.test.ts
 *
 * Static assertions only: no browser, no HTTP, no PDF render, no live council.
 * The pure advisory API is read by evaluating the file in a vm sandbox. The
 * sibling chamber tests pass an EMPTY sandbox (no document at all), and the
 * module's `typeof document === 'undefined'` guard is what keeps the DOM half
 * unentered. This file supplies a minimal document stub as well; it is
 * harmless and exercises only the later `if (!host) return;` guard, because
 * getElementById returns null. Neither stub is required by the module.
 */

import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
const read = (name: string): string => readFileSync(join(chamberDir, name), 'utf8');

/* eslint-disable @typescript-eslint/no-explicit-any */
const jsSource = read('chamber-advisory.js');
const advisory = (() => {
  // The pure API is assigned before the DOM half, so the module returns early
  // on its own `typeof document === 'undefined'` guard even with no sandbox.
  // This stub only makes the later `if (!host) return;` path reachable: a null
  // mount keeps the DOM half unentered and boot is never attempted.
  const sandbox: any = {
    document: { getElementById: () => null },
  };
  runInNewContext(jsSource, sandbox);
  return sandbox.councilChamber.advisory;
})();

function actionableFixture() {
  const record = {
    brief: {
      options: [
        { id: 'option-a', label: 'Keep the weekly upload' },
        { id: 'option-b', label: 'Run a two-week test' },
      ],
    },
    verdict: {
      result_kind: 'scored',
      label: 'GO_WITH_CONDITIONS',
      recommended_option_id: 'option-b',
      main_reasons: ['r1', 'r2', 'r3'],
      prerequisites: ['c1', 'c2', 'c3', 'c4', 'c5', 'c6'],
      critical_unknowns: ['u1', 'u2', 'u3', 'u4', 'u5'],
      strongest_dissent: 'dissent',
      action_proposals: [
        { title: 'Publish the test brief', description: 'One page.', risk_class: 'low' },
        { title: 'Review after two weeks', description: 'Compare.', risk_class: 'low' },
      ],
      option_scores: [{ option_id: 'option-b', display_score: 8.2 }],
    },
  };
  const view = {
    id: 's1',
    status: 'complete',
    voters: 9,
    options: [
      { id: 'option-a', letter: 'A', label: 'Keep the weekly upload', votes: 2, score: 6.1, recommended: false },
      { id: 'option-b', letter: 'B', label: 'Run a two-week test', votes: 7, score: 8.2, recommended: true },
    ],
  };
  return { record, view };
}

test('the panel is reachable without a DOM and takes its documented guard', () => {
  assert.match(jsSource, /if \(typeof document === 'undefined'\) return;/);
  assert.match(jsSource, /if \(!host\) return;/);
  assert.ok(advisory && typeof advisory.model === 'function');
});

test('the headline is the named approach, and the verdict word is separate context', () => {
  const { record, view } = actionableFixture();
  const m = advisory.model(record, view);
  assert.equal(m.actionable, true);
  assert.equal(m.headline, 'Run a two-week test', 'plain name, not "Option B"');
  assert.match(jsSource, /setText\(els\.title, m\.headline \|\| m\.title\)/, 'the panel paints the headline');
  assert.equal(m.title, 'The council recommends Option B.', 'model.title is retained but is not what paints');
  assert.equal(m.decisionChip, 'Decision: Go, with conditions', 'the verdict word is its own chip');
  assert.equal(m.optionChip, 'Option B');
  assert.equal(m.subLine, 'Option B · Go, with conditions');
  assert.equal(m.startHere.title, 'Publish the test brief', 'one primary move');
});

test('a preference count and a score are labelled as such, never as a probability', () => {
  const { record, view } = actionableFixture();
  const m = advisory.model(record, view);
  assert.equal(m.matches, '7 of 9 advisors preferred it');
  assert.match(m.preferenceNote as string, /not a probability/);
  assert.match(m.scoreNote as string, /not a probability/);
  assert.match(jsSource, /Neither is a probability/);
  assert.doesNotMatch(jsSource, /probability of|chance of/i, 'no probability claim is invented');
});

test('no condition or unknown is silently cut: every item is rendered', () => {
  assert.match(jsSource, /fillList\(els\.conditions\.body, m\.conditions, 'ol', null\)/);
  assert.match(jsSource, /fillList\(els\.unknowns\.body, m\.unknowns, 'ul', null\)/);
  assert.doesNotMatch(jsSource, /fillList\(els\.conditions\.body, m\.conditions, 'ol', \d+\)/);
});

test('the controls that act on the answer paint above the long detail', () => {
  const earlyAt = jsSource.indexOf("var early = el('div', 'ch-adv-early')");
  const reasonsAppend = jsSource.indexOf('host.appendChild(els.reasons.node)');
  const earlyInsert = jsSource.indexOf('host.insertBefore(early, els.reasons.node)');
  assert.ok(earlyAt > 0, 'the early control row exists');
  assert.ok(earlyInsert > reasonsAppend, 'it is inserted after the stable append order');
  assert.match(jsSource, /early\.appendChild\(els\.pdf\)/);
  assert.match(jsSource, /early\.appendChild\(actions\)/);
  assert.match(jsSource, /'Ask a follow-up'/, 'the follow-up control is named plainly');
});

test('the one URL-shaped literal is the complete, quoted, inert SVG namespace', () => {
  const namespace = "'http://www.w3.org/2000/svg'";
  assert.equal(jsSource.split(namespace).length - 1, 1, 'exactly one complete quoted SVG namespace literal');
  const rest = jsSource.split(namespace).join('');
  // Broadened honestly beyond http(s): after the one inert namespace is
  // removed, no URI scheme in `scheme://` form and no quoted protocol-relative
  // `//` literal may remain. Line comments (`  // ...`) are not URL literals
  // and are not matched by these two patterns.
  assert.equal(/[a-z][a-z0-9+.-]*:\/\//i.test(rest), false, 'no other URI scheme in URL form');
  assert.equal(/["']\s*\/\//.test(rest), false, 'no quoted protocol-relative URL');
  assert.doesNotMatch(jsSource, /['"]http['"]\s*\+\s*['"]/, 'the namespace is not split to evade a scan');
});

test('one room paints: a second stage, seat box or pill is pruned and hidden', () => {
  const js = read('chamber-room.js');
  const css = read('chamber-room.css');
  assert.match(js, /function pruneDuplicates\(\)/);
  assert.match(js, /mount\.querySelectorAll\('\.ch-room-stage'\)/);
  assert.match(js, /if \(room\._booted\) \{\s*pruneDuplicates\(\);\s*return;/);
  assert.match(css, /#ch-room > \.ch-room-stage ~ \.ch-room-stage/);
  assert.match(css, /#ch-room \.ch-room-seats ~ \.ch-room-seats/);
});

test('all nine portrait files exist on disk and resolve from the seat roster', () => {
  const seats = (() => {
    const sandbox: any = {};
    runInNewContext(read('chamber-seats.js'), sandbox);
    return sandbox.councilChamber.seats;
  })();
  assert.equal(seats.order.length, 9);
  for (const id of seats.order) {
    const sources = [`portraits/${id}.webp`, `portraits/${id}.svg`];
    assert.deepEqual(seats.portraitSources(id), sources);
    for (const rel of sources) {
      assert.ok(existsSync(join(chamberDir, rel)), `${rel} must exist`);
    }
  }
});
