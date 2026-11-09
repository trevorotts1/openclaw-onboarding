/**
 * W77S AUTO-MODE-1062 — automatic deliberation-mode selection, end to end.
 *
 * Trevor's binding rule (2026-10-25): EVERY mode seats the whole council.
 * Mode changes only rounds and concurrency, so this test deliberately makes
 * no claim about seat counts or rounds — other lanes own those. What is
 * proven here is the selection contract:
 *
 *   - an explicit client mode always wins (source = 'client')
 *   - with no explicit mode, question complexity decides (source = 'auto'):
 *     simple -> light, moderately complex -> medium, high-stakes
 *     multi-factor -> heavy
 *   - the same question always yields the same decision
 *   - every reason is non-empty and names the deciding factor
 *
 * Runner: node --import tsx --test tests/mode-autoselect-e2e.test.ts
 */

import assert from 'node:assert/strict';
import test from 'node:test';
import { selectMode } from '../src/flow/mode-select.js';

type Mode = 'light' | 'medium' | 'heavy';
type Source = 'client' | 'auto';

const MODES: readonly Mode[] = ['light', 'medium', 'heavy'];

/** One quick lookup with nothing at stake. */
const SIMPLE_QUESTIONS: readonly string[] = [
  'What should I name the folder for this month invoices?',
  'Should I reply to this email now or tomorrow morning?',
  'Where did I put the printer manual?',
];

/** Real trade-offs across a couple of factors, none of them high-stakes. */
const MODERATE_QUESTIONS: readonly string[] = [
  'Should we switch our CRM vendor or renegotiate the current contract?',
  'We are choosing between two office leases; help me weigh cost and commute.',
  'Which feature should we ship next in the roadmap release, and should we delay the newsletter campaign?',
];

/** Irreversible or high-stakes, with several factors in play at once. */
const HIGH_STAKES_QUESTIONS: readonly string[] = [
  'Should we accept the acquisition offer, raise another investment round, or file for bankruptcy, given the expiring lease, the lawsuit, and the payroll deadline?',
  'Should we fire the COO for the compliance breach, shut down the office lease, and restructure the debt?',
];

const ALL_QUESTIONS: readonly string[] = [
  ...SIMPLE_QUESTIONS,
  ...MODERATE_QUESTIONS,
  ...HIGH_STAKES_QUESTIONS,
];

function assertShape(label: string, result: ReturnType<typeof selectMode>): void {
  assert.ok(
    MODES.includes(result.mode as Mode),
    `${label}: mode must be light, medium or heavy, got ${String(result.mode)}`,
  );
  assert.ok(
    result.source === 'client' || result.source === 'auto',
    `${label}: source must be client or auto, got ${String(result.source)}`,
  );
  assert.equal(typeof result.reason, 'string', `${label}: reason must be a string`);
  assert.ok(
    result.reason.trim().length > 0,
    `${label}: reason must be non-empty and name the deciding factor`,
  );
}

void test('an explicit client mode always wins, whatever the question complexity', () => {
  for (const mode of MODES) {
    for (const question of ALL_QUESTIONS) {
      const label = `explicit ${mode} on ${JSON.stringify(question)}`;
      const result = selectMode(question, mode);
      assertShape(label, result);
      assert.equal(result.source, 'client', `${label}: source must be client`);
      assert.equal(result.mode, mode, `${label}: client choice must be returned verbatim`);
    }
  }
});

void test('an explicit client mode wins over the automatic classification it contradicts', () => {
  const simpleQuestion = SIMPLE_QUESTIONS[0]!;
  const highStakesQuestion = HIGH_STAKES_QUESTIONS[0]!;

  // A heavy question downgraded by the client stays light.
  assert.equal(selectMode(highStakesQuestion, 'light').mode, 'light');
  assert.equal(selectMode(highStakesQuestion, 'light').source, 'client');

  // A simple question upgraded by the client stays heavy.
  assert.equal(selectMode(simpleQuestion, 'heavy').mode, 'heavy');
  assert.equal(selectMode(simpleQuestion, 'heavy').source, 'client');

  // The automatic answer for each of those questions is the opposite tier.
  assert.notEqual(selectMode(highStakesQuestion).mode, 'light');
  assert.notEqual(selectMode(simpleQuestion).mode, 'heavy');
});

void test('with no explicit mode the source is auto', () => {
  for (const question of ALL_QUESTIONS) {
    const omitted = selectMode(question);
    const undefinedMode = selectMode(question, undefined);
    assertShape(question, omitted);
    assert.equal(omitted.source, 'auto', `${question}: omitted mode must come from auto`);
    assert.equal(undefinedMode.source, 'auto', `${question}: undefined mode must come from auto`);
  }
});

void test('simple questions select light', () => {
  for (const question of SIMPLE_QUESTIONS) {
    const result = selectMode(question);
    assertShape(question, result);
    assert.equal(result.source, 'auto', `${question}: expected the automatic path`);
    assert.equal(result.mode, 'light', `${question}: simple question must select light`);
  }
});

void test('moderately complex questions select medium', () => {
  for (const question of MODERATE_QUESTIONS) {
    const result = selectMode(question);
    assertShape(question, result);
    assert.equal(result.source, 'auto', `${question}: expected the automatic path`);
    assert.equal(result.mode, 'medium', `${question}: trade-off question must select medium`);
  }
});

void test('high-stakes multi-factor questions select heavy', () => {
  for (const question of HIGH_STAKES_QUESTIONS) {
    const result = selectMode(question);
    assertShape(question, result);
    assert.equal(result.source, 'auto', `${question}: expected the automatic path`);
    assert.equal(result.mode, 'heavy', `${question}: high-stakes question must select heavy`);
  }
});

void test('all three automatic tiers are reachable', () => {
  const tiers = new Set<Mode>([
    ...SIMPLE_QUESTIONS.map((question) => selectMode(question).mode as Mode),
    ...MODERATE_QUESTIONS.map((question) => selectMode(question).mode as Mode),
    ...HIGH_STAKES_QUESTIONS.map((question) => selectMode(question).mode as Mode),
  ]);
  assert.deepEqual([...tiers].sort(), [...MODES].sort());
});

void test('the decision is deterministic across repeated runs', () => {
  for (const question of ALL_QUESTIONS) {
    const first = selectMode(question);
    for (let run = 0; run < 5; run += 1) {
      const repeat = selectMode(question);
      assert.deepEqual(
        { mode: repeat.mode, source: repeat.source, reason: repeat.reason },
        { mode: first.mode, source: first.source, reason: first.reason },
        `${question}: run ${run + 2} differed from the first run`,
      );
    }
    for (const mode of MODES) {
      assert.deepEqual(selectMode(question, mode), selectMode(question, mode));
    }
  }
});

void test('the reason names the deciding factor for both sources', () => {
  for (const question of ALL_QUESTIONS) {
    const auto = selectMode(question);
    const client = selectMode(question, 'medium');

    // The client path names the client choice as the deciding factor.
    assert.match(
      client.reason,
      /client|explicit|request|specif/iu,
      `${question}: client reason must name the client choice, got ${JSON.stringify(client.reason)}`,
    );

    // The automatic path names a complexity factor.
    assert.match(
      auto.reason,
      /complex|score|stake|breadth|ambiguit|length|factor/iu,
      `${question}: auto reason must name the deciding factor, got ${JSON.stringify(auto.reason)}`,
    );

    // The two sources are decided by different factors, so they never share one reason.
    assert.notEqual(
      auto.reason,
      client.reason,
      `${question}: auto and client reasons must differ`,
    );
  }
});
