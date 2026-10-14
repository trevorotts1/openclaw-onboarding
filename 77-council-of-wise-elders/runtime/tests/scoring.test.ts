/**
 * CWE-026 scoring services: deterministic decision analysis and frozen
 * critical-domain classification (directive Sections 12.2 to 12.7,
 * 12.6 fixture list, 32.2 golden fixture).
 *
 * Fixture identity: cwe-026-synthetic-fixtures/v1. These are contract
 * tests over synthetic cards; they prove the pure services, not a live
 * council (Section 34.3, verification_level: contract_tested).
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  computeOptionScore,
  GOLDEN_EXPECTED,
  GOLDEN_SCORES,
  GOLDEN_TOTAL_WEIGHT,
  GOLDEN_WEIGHTS,
  SEAT_IDS,
  type CriticalDomainRequirement,
  type DecisionOption,
  type SeatId,
} from '../src/contracts/index.js';
import {
  analyzeDecision,
  classifyCriticalDomains,
  type DecisionInput,
  type OptionScoreInput,
} from '../src/scoring/index.js';

const OPTIONS: DecisionOption[] = [
  { id: 'A', label: 'Keep the current offer', kind: 'status_quo' },
  { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' },
  { id: 'C', label: 'Launch the revised offer broadly', kind: 'change' },
];

const GOLDEN_WEIGHT_MAP: Partial<Record<SeatId, number>> = Object.fromEntries(
  SEAT_IDS.map((seatId, i) => [seatId, GOLDEN_WEIGHTS[i]]),
);

function goldenScores(optionId: 'A' | 'B' | 'C'): OptionScoreInput[] {
  return GOLDEN_SCORES[optionId].map((entry) => ({
    option_id: optionId,
    seat_id: entry.seat_id as SeatId,
    score: entry.score,
  }));
}

function goldenInput(overrides: Partial<DecisionInput> = {}): DecisionInput {
  return {
    options: OPTIONS,
    active_seat_ids: SEAT_IDS,
    weights: GOLDEN_WEIGHT_MAP,
    scores: [...goldenScores('A'), ...goldenScores('B'), ...goldenScores('C')],
    ...overrides,
  };
}

function requirement(
  partial: Partial<CriticalDomainRequirement> &
    Pick<CriticalDomainRequirement, 'domain'>,
): CriticalDomainRequirement {
  return {
    schema_version: 'wise-elders.critical-domain-requirement/v1',
    status: 'assessed',
    trigger_evidence_ids: [],
    trigger_field_paths: [],
    required_seat_id: null,
    required_checker: 'seat',
    unresolved_questions: [],
    policy_version: 'critical-domains/v1',
    ...partial,
  };
}

test('golden fixture: exact Section 32.2 arithmetic and GO for B', () => {
  const analysis = analyzeDecision(goldenInput());
  assert.equal(analysis.verification_level, 'contract_tested');
  assert.equal(analysis.total_active_weight, GOLDEN_TOTAL_WEIGHT);
  const byId = new Map(analysis.options.map((o) => [o.option_id, o]));
  for (const optionId of ['A', 'B', 'C'] as const) {
    const expected = GOLDEN_EXPECTED[optionId];
    const mine = byId.get(optionId);
    assert.ok(mine);
    assert.equal(mine.weighted_sum, expected.weighted_sum, `${optionId} sum`);
    assert.equal(mine.denominator, expected.denominator, `${optionId} denominator`);
    assert.equal(mine.score, expected.score, `${optionId} score`);
    assert.equal(mine.display_score, expected.display_score, `${optionId} display`);
    assert.equal(mine.coverage, expected.coverage, `${optionId} coverage`);
    assert.equal(mine.spread, expected.spread, `${optionId} spread`);
    // Byte-for-byte agreement with the CWE-003 contracts module the
    // CWE-004 core uses: same inputs, same outputs, field by field.
    const core = computeOptionScore(
      GOLDEN_SCORES[optionId].map((e) => ({
        seat_id: e.seat_id,
        weight: e.weight,
        score: e.score,
      })),
      GOLDEN_TOTAL_WEIGHT,
    );
    assert.deepEqual(
      {
        weighted_sum: mine.weighted_sum,
        denominator: mine.denominator,
        score: mine.score,
        display_score: mine.display_score,
        coverage: mine.coverage,
        spread: mine.spread,
      },
      core,
    );
  }
  assert.equal(analysis.label, 'GO');
  assert.equal(analysis.recommended_option_id, 'B');
  assert.equal(analysis.leading_option_id, 'B');
  assert.equal(analysis.near_tie.present, false);
});

test('golden fixture: a confirmed hard failure disqualifies B despite 7.6', () => {
  const analysis = analyzeDecision(
    goldenInput({
      hard_constraints: [
        {
          constraint_id: 'con-budget-cap',
          option_id: 'B',
          result: 'fail',
          checker: 'deterministic_code',
          evidence_ids: ['ev-1'],
        },
      ],
    }),
  );
  const b = analysis.options.find((o) => o.option_id === 'B');
  assert.ok(b);
  assert.equal(b.eligible, false);
  assert.equal(b.score, 168 / 22); // arithmetic is still reported honestly
  assert.deepEqual(b.hard_failure_constraint_ids, ['con-budget-cap']);
  // With B removed, C (145/22 = 6.59) outranks A (6.0); both sit in the
  // GO_WITH_CONDITIONS band.
  assert.equal(analysis.leading_option_id, 'C');
  assert.equal(analysis.recommended_option_id, 'C');
  assert.equal(analysis.label, 'GO_WITH_CONDITIONS');
});

test('golden fixture: Tiffany abstains on B; affordability gate still blocks GO', () => {
  const scores = [
    ...goldenScores('A'),
    ...GOLDEN_SCORES.B_TIFFANY_ABSTAINS.map((entry) => ({
      option_id: 'B',
      seat_id: entry.seat_id as SeatId,
      score: entry.score,
    })),
    ...goldenScores('C'),
  ];
  const analysis = analyzeDecision(
    goldenInput({
      scores,
      critical_domains: [
        requirement({
          domain: 'financial_feasibility',
          status: 'unresolved',
          required_seat_id: 'tiffany-aliche',
          required_checker: 'seat',
          unresolved_questions: [
            'Is the pilot affordable at committed cash levels?',
          ],
        }),
      ],
    }),
  );
  const b = analysis.options.find((o) => o.option_id === 'B');
  assert.ok(b);
  const expected = GOLDEN_EXPECTED.B_TIFFANY_ABSTAINS;
  assert.equal(b.weighted_sum, expected.weighted_sum); // 150
  assert.equal(b.denominator, expected.denominator); // 19
  assert.equal(b.score, expected.score); // 150/19
  assert.equal(b.coverage, expected.coverage); // 19/22, about 86.36 percent
  assert.deepEqual(b.abstained_seat_ids, ['tiffany-aliche']);
  assert.deepEqual(b.critical_abstentions, ['tiffany-aliche']);
  assert.ok(b.critical_blockers.includes('financial_feasibility'));
  // Coverage exceeds 80 percent, yet the label is not a GO-style label:
  // mathematical coverage and decision safety stay separate (32.2).
  assert.equal(analysis.label, 'WAIT');
  assert.equal(analysis.recommended_option_id, 'B');
  assert.ok(
    analysis.prerequisites_needed.includes(
      'Is the pilot affordable at committed cash levels?',
    ),
  );
});

test('hand-calculated fixture, independent of the implementation (12.6)', () => {
  // By hand: weights 1, 2, 3; scores 10, 4, 5.
  // Weighted sum = 1*10 + 2*4 + 3*5 = 33; denominator 6; score 33/6 = 5.5.
  // Spread = 10 - 4 = 6. Band for 5.5 is RESHAPE (4.5 to 5.999...).
  const analysis = analyzeDecision({
    options: [{ id: 'X', label: 'Option X', kind: 'change' }],
    active_seat_ids: ['simon-sinek', 'td-jakes', 'oprah-winfrey'],
    weights: { 'simon-sinek': 1, 'td-jakes': 2, 'oprah-winfrey': 3 },
    scores: [
      { option_id: 'X', seat_id: 'simon-sinek', score: 10 },
      { option_id: 'X', seat_id: 'td-jakes', score: 4 },
      { option_id: 'X', seat_id: 'oprah-winfrey', score: 5 },
    ],
  });
  const x = analysis.options[0];
  assert.equal(x.weighted_sum, 33);
  assert.equal(x.denominator, 6);
  assert.equal(x.score, 5.5);
  assert.equal(x.display_score, 5.5);
  assert.equal(x.spread, 6);
  assert.equal(analysis.label, 'RESHAPE');
});

test('equal weights fixture', () => {
  const analysis = analyzeDecision({
    options: [
      { id: 'X', label: 'X', kind: 'change' },
      { id: 'Y', label: 'Y', kind: 'bounded_test' },
    ],
    active_seat_ids: ['simon-sinek', 'td-jakes', 'oprah-winfrey'],
    weights: { 'simon-sinek': 1, 'td-jakes': 1, 'oprah-winfrey': 1 },
    scores: [
      { option_id: 'X', seat_id: 'simon-sinek', score: 5 },
      { option_id: 'X', seat_id: 'td-jakes', score: 5 },
      { option_id: 'X', seat_id: 'oprah-winfrey', score: 5 },
      { option_id: 'Y', seat_id: 'simon-sinek', score: 8 },
      { option_id: 'Y', seat_id: 'td-jakes', score: 8 },
      { option_id: 'Y', seat_id: 'oprah-winfrey', score: 8 },
    ],
  });
  assert.equal(analysis.options[0].score, 5);
  assert.equal(analysis.options[1].score, 8);
  assert.equal(analysis.label, 'GO');
  assert.equal(analysis.recommended_option_id, 'Y');
});

test('all abstain: scores are null and the label is INSUFFICIENT_EVIDENCE (T041)', () => {
  const scores = goldenInput().scores.map((s) => ({ ...s, score: null }));
  const analysis = analyzeDecision(goldenInput({ scores }));
  for (const option of analysis.options) {
    assert.equal(option.score, null);
    assert.equal(option.denominator, 0);
    assert.equal(option.coverage, 0);
  }
  assert.equal(analysis.label, 'INSUFFICIENT_EVIDENCE');
  assert.equal(analysis.recommended_option_id, null);
  assert.equal(analysis.leading_option_id, null);
});

test('missing card reduces coverage; a timeout is never an abstention (T045 boundary)', () => {
  const scores = goldenInput().scores.filter((s) => s.seat_id !== 'les-brown');
  const analysis = analyzeDecision(
    goldenInput({
      scores,
      missing_seat_ids: ['les-brown'],
      timed_out_seat_ids: ['les-brown'],
    }),
  );
  const b = analysis.options.find((o) => o.option_id === 'B');
  assert.ok(b);
  assert.equal(b.denominator, 20); // 22 minus Les Brown's weight 2
  assert.equal(b.coverage, 20 / 22);
  assert.deepEqual(b.abstained_seat_ids, []); // missing is not abstaining
  assert.deepEqual(analysis.missing_seat_ids, ['les-brown']);
  assert.deepEqual(analysis.timed_out_seat_ids, ['les-brown']);
  assert.equal(analysis.label, 'GO'); // coverage still above 80 percent
});

test('duplicate seat entry and duplicate option are rejected (12.6)', () => {
  const duplicateSeat = goldenInput();
  duplicateSeat.scores = [
    ...duplicateSeat.scores,
    { option_id: 'A', seat_id: 'simon-sinek', score: 1 },
  ];
  assert.throws(() => analyzeDecision(duplicateSeat), /duplicate score/);
  assert.throws(
    () =>
      analyzeDecision(
        goldenInput({
          options: [...OPTIONS, { id: 'A', label: 'dup', kind: 'other' }],
        }),
      ),
    /duplicate option id/,
  );
});

test('NaN and out-of-range scores are rejected, never averaged in (12.6)', () => {
  for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, 11, -1]) {
    const input = goldenInput();
    input.scores = input.scores.map((s) =>
      s.option_id === 'A' && s.seat_id === 'simon-sinek' ? { ...s, score: bad } : s,
    );
    assert.throws(() => analyzeDecision(input));
  }
});

test('zero denominator: an option scored by nobody has score null, not 0', () => {
  const scores = goldenInput().scores.filter((s) => s.option_id !== 'C');
  const analysis = analyzeDecision(goldenInput({ scores }));
  const c = analysis.options.find((o) => o.option_id === 'C');
  assert.ok(c);
  assert.equal(c.score, null);
  assert.equal(c.display_score, null);
  assert.equal(c.spread, null);
  assert.equal(c.denominator, 0);
});

test('hard UNKNOWN blocks unconditional approval with a named prerequisite (T043)', () => {
  const analysis = analyzeDecision(
    goldenInput({
      hard_constraints: [
        {
          constraint_id: 'con-permit',
          option_id: 'B',
          result: 'unknown',
          checker: 'qualified_professional',
          evidence_ids: [],
        },
      ],
    }),
  );
  assert.equal(analysis.label, 'WAIT');
  assert.equal(analysis.recommended_option_id, 'B');
  assert.ok(
    analysis.prerequisites_needed.some((p) => p.includes('con-permit')),
  );
});

test('near tie within 0.25 is preserved as an unresolved crux (T044)', () => {
  const analysis = analyzeDecision({
    options: [
      { id: 'P', label: 'P', kind: 'change' },
      { id: 'Q', label: 'Q', kind: 'bounded_test' },
    ],
    active_seat_ids: ['simon-sinek', 'td-jakes'],
    weights: { 'simon-sinek': 1, 'td-jakes': 1 },
    scores: [
      { option_id: 'P', seat_id: 'simon-sinek', score: 8 },
      { option_id: 'P', seat_id: 'td-jakes', score: 7 },
      { option_id: 'Q', seat_id: 'simon-sinek', score: 7.4 },
      { option_id: 'Q', seat_id: 'td-jakes', score: 7.4 },
    ],
  });
  assert.equal(analysis.near_tie.present, true);
  assert.deepEqual(analysis.near_tie.option_ids, ['P', 'Q']);
  assert.equal(analysis.near_tie.resolution, 'unresolved_crux');
  assert.ok(analysis.near_tie.next_fact_needed);
  assert.equal(analysis.recommended_option_id, 'P'); // leader kept, tie disclosed
  assert.ok(
    analysis.label_reasons.some((r) => r.includes('not resolved by rounding')),
  );
});

test('near tie resolved only by recorded exposure evidence (T044)', () => {
  const analysis = analyzeDecision({
    options: [
      { id: 'P', label: 'P', kind: 'change' },
      { id: 'Q', label: 'Q', kind: 'bounded_test' },
    ],
    active_seat_ids: ['simon-sinek', 'td-jakes'],
    weights: { 'simon-sinek': 1, 'td-jakes': 1 },
    scores: [
      { option_id: 'P', seat_id: 'simon-sinek', score: 8 },
      { option_id: 'P', seat_id: 'td-jakes', score: 7 },
      { option_id: 'Q', seat_id: 'simon-sinek', score: 7.4 },
      { option_id: 'Q', seat_id: 'td-jakes', score: 7.4 },
    ],
    option_exposure: [
      { option_id: 'P', irreversibility: 'high', exposure: 'high' },
      { option_id: 'Q', irreversibility: 'low', exposure: 'low' },
    ],
  });
  assert.equal(analysis.near_tie.resolution, 'less_irreversible_preferred');
  assert.equal(analysis.near_tie.preferred_option_id, 'Q');
  assert.equal(analysis.recommended_option_id, 'Q');
  assert.equal(analysis.label, 'GO_WITH_CONDITIONS'); // Q is 7.4
});

test('coverage below 80 percent prevents an actionable GO (T042)', () => {
  const scores = goldenInput().scores.filter(
    (s) => s.option_id !== 'B' || ['simon-sinek', 'td-jakes', 'oprah-winfrey'].includes(s.seat_id),
  );
  const analysis = analyzeDecision(goldenInput({ scores }));
  const b = analysis.options.find((o) => o.option_id === 'B');
  assert.ok(b);
  assert.equal(b.coverage, 7 / 22);
  assert.equal(analysis.label, 'INSUFFICIENT_EVIDENCE');
  assert.equal(analysis.recommended_option_id, null);
  assert.equal(analysis.leading_option_id, 'B'); // leading, but not recommendable
});

test('changed weights change the arithmetic exactly (12.6 changed-weights fixture)', () => {
  const flat = analyzeDecision(
    goldenInput({
      weights: Object.fromEntries(SEAT_IDS.map((s) => [s, 1])),
    }),
  );
  // Equal weights: A = 54/9 = 6.0, B = 69/9 = 7.666..., C = 60/9 = 6.666...
  const b = flat.options.find((o) => o.option_id === 'B');
  assert.ok(b);
  assert.equal(b.weighted_sum, 69);
  assert.equal(b.denominator, 9);
  assert.equal(b.score, 69 / 9);
  assert.equal(flat.total_active_weight, 9);
});

test('status quo win: the status quo option can lead and be recommended', () => {
  const scores = goldenInput().scores.map((s) =>
    s.option_id === 'A' ? { ...s, score: 9 } : s.option_id === 'B' ? { ...s, score: 4 } : s,
  );
  const analysis = analyzeDecision(goldenInput({ scores }));
  assert.equal(analysis.recommended_option_id, 'A');
  assert.equal(analysis.label, 'GO');
});

test('all options disqualified: INSUFFICIENT_EVIDENCE with no recommendation', () => {
  const analysis = analyzeDecision(
    goldenInput({
      hard_constraints: OPTIONS.map((o) => ({
        constraint_id: `con-${o.id}`,
        option_id: o.id,
        result: 'fail' as const,
        checker: 'deterministic_code' as const,
        evidence_ids: [],
      })),
    }),
  );
  assert.equal(analysis.label, 'INSUFFICIENT_EVIDENCE');
  assert.equal(analysis.recommended_option_id, null);
  assert.equal(analysis.leading_option_id, null);
});

test('a missing critical reviewer blocks the GO even when the domain says assessed (T144)', () => {
  const scores = goldenInput().scores.filter((s) => s.seat_id !== 'russell-brunson');
  const analysis = analyzeDecision(
    goldenInput({
      scores,
      missing_seat_ids: ['russell-brunson'],
      critical_domains: [
        requirement({
          domain: 'demand_and_delivery',
          status: 'assessed',
          required_seat_id: 'russell-brunson',
          required_checker: 'seat',
        }),
      ],
    }),
  );
  assert.equal(analysis.label, 'WAIT');
  const b = analysis.options.find((o) => o.option_id === 'B');
  assert.ok(b);
  assert.ok(b.critical_blockers.includes('demand_and_delivery'));
});

test('option-specific classification gates only the exposed option (T145)', () => {
  const analysis = analyzeDecision(
    goldenInput({
      critical_domains: [
        requirement({
          domain: 'financial_feasibility',
          status: 'unresolved',
          required_seat_id: 'tiffany-aliche',
          required_checker: 'seat',
          unresolved_questions: ['Can committed cash fund a broad launch?'],
        }),
      ],
      critical_domain_applicability: [
        { domain: 'financial_feasibility', option_id: 'C' },
      ],
    }),
  );
  const b = analysis.options.find((o) => o.option_id === 'B');
  const c = analysis.options.find((o) => o.option_id === 'C');
  assert.ok(b && c);
  assert.deepEqual(b.critical_blockers, []);
  assert.deepEqual(c.critical_blockers, ['financial_feasibility']);
  assert.equal(analysis.label, 'GO'); // the safe alternative is not endorsed into the unknown
  assert.equal(analysis.recommended_option_id, 'B');
});

test('qualified professional review is a gate no seat can substitute for (12.7)', () => {
  const domain = requirement({
    domain: 'qualified_professional_review',
    status: 'unresolved',
    required_seat_id: null,
    required_checker: 'qualified_professional',
    unresolved_questions: ['A licensed review of the tax treatment is missing.'],
  });
  const blocked = analyzeDecision(goldenInput({ critical_domains: [domain] }));
  assert.equal(blocked.label, 'WAIT');

  const failed = analyzeDecision(
    goldenInput({
      critical_domains: [{ ...domain, status: 'assessed' }],
      professional_reviews: [{ option_id: 'B', result: 'fail' }],
    }),
  );
  const b = failed.options.find((o) => o.option_id === 'B');
  assert.ok(b);
  assert.equal(b.eligible, false);
});

test('classifyCriticalDomains freezes reviewers, triggers, and rejects removals (T143)', () => {
  const classified = classifyCriticalDomains({
    policy_version: 'critical-domains/v1',
    signals: [
      {
        domain: 'financial_feasibility',
        origin: 'constraint_tag',
        trigger_fact_ids: ['fact-1'],
        trigger_field_paths: ['constraints.con-1'],
        applies_to_option_ids: ['B', 'C'],
        open_questions: ['Is the pilot affordable at committed cash levels?'],
      },
      {
        domain: 'communication',
        origin: 'model_proposal',
        trigger_fact_ids: [],
        trigger_field_paths: ['facts.fact-2'],
        applies_to_option_ids: [],
        open_questions: [],
      },
      {
        domain: 'qualified_professional_review',
        origin: 'intake_fact',
        trigger_fact_ids: ['fact-3'],
        trigger_field_paths: [],
        applies_to_option_ids: [],
        open_questions: [],
      },
    ],
    model_removal_requests: ['financial_feasibility'],
  });
  assert.deepEqual(classified.rejected_removals, ['financial_feasibility']);
  const financial = classified.requirements.find(
    (r) => r.domain === 'financial_feasibility',
  );
  assert.ok(financial);
  assert.equal(financial.status, 'unresolved');
  assert.equal(financial.required_seat_id, 'tiffany-aliche');
  assert.equal(financial.required_checker, 'seat');
  assert.equal(financial.policy_version, 'critical-domains/v1');
  assert.deepEqual(financial.unresolved_questions, [
    'Is the pilot affordable at committed cash levels?',
  ]);
  const professional = classified.requirements.find(
    (r) => r.domain === 'qualified_professional_review',
  );
  assert.ok(professional);
  assert.equal(professional.required_seat_id, null);
  assert.equal(professional.required_checker, 'qualified_professional');
  assert.equal(professional.status, 'not_assessed');
  assert.deepEqual(classified.applicability, [
    { domain: 'financial_feasibility', option_id: 'B' },
    { domain: 'financial_feasibility', option_id: 'C' },
  ]);
  // Deterministic: a second run over the same input is identical.
  const again = classifyCriticalDomains({
    policy_version: 'critical-domains/v1',
    signals: [
      {
        domain: 'financial_feasibility',
        origin: 'constraint_tag',
        trigger_fact_ids: ['fact-1'],
        trigger_field_paths: ['constraints.con-1'],
        applies_to_option_ids: ['B', 'C'],
        open_questions: ['Is the pilot affordable at committed cash levels?'],
      },
      {
        domain: 'communication',
        origin: 'model_proposal',
        trigger_fact_ids: [],
        trigger_field_paths: ['facts.fact-2'],
        applies_to_option_ids: [],
        open_questions: [],
      },
      {
        domain: 'qualified_professional_review',
        origin: 'intake_fact',
        trigger_fact_ids: ['fact-3'],
        trigger_field_paths: [],
        applies_to_option_ids: [],
        open_questions: [],
      },
    ],
    model_removal_requests: ['financial_feasibility'],
  });
  assert.deepEqual(again, classified);
});
