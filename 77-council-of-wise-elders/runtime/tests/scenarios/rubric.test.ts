/**
 * CWE-042 scenario harness: Section 32.5 mechanics (T152, T153).
 *
 * These tests prove the qualification arithmetic is mechanical and
 * fail-closed. Every grade set below is synthetic and labeled as such;
 * expected values were computed by hand from the directive's weights
 * and thresholds. No synthetic set is evidence about any real council
 * run: the only qualification record for real runs lives in
 * records/qualification-ledger.json, where every planned run is
 * NOT_RUN (no live evaluation allowance exists for this build).
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  RUBRIC_DIMENSIONS,
  evaluateDifferentiation,
  evaluateQualification,
  rubricScore,
  rubricWeightsSum,
  stripForBlindReview,
  type DimensionScores,
  type QualificationInput,
  type RunGrade,
} from './rubric.js';

const CASES = ['Q01', 'Q02', 'Q03', 'Q04', 'Q05', 'Q06', 'Q07', 'Q08', 'Q09', 'Q10'];

const dims = (
  grounding: number, decision: number, fidelity: number,
  differentiation: number, actionability: number, clarity: number,
): DimensionScores => ({
  factual_grounding: grounding,
  decision_quality: decision,
  source_fidelity: fidelity,
  advisor_differentiation: differentiation,
  actionability_agency: actionability,
  clarity_dissent_effort: clarity,
});

const ALL4 = dims(4, 4, 4, 4, 4, 4);
// weighted 1.00 + 0.60 + 0.60 + 0.45 + 0.60 + 0.30 = 3.65 -> 9.125
const SCORE_9_125 = dims(3, 4, 4, 4, 4, 3);

function gradedRuns(scores: DimensionScores, overrides?: (run: RunGrade) => void): RunGrade[] {
  const runs: RunGrade[] = [];
  for (const caseId of CASES) {
    for (let rep = 1; rep <= 3; rep++) {
      const run: RunGrade = {
        case_id: caseId, repetition: rep, status: 'graded',
        dimension_scores: scores, hard_failures: [], not_run_reason: null,
      };
      if (overrides) overrides(run);
      runs.push(run);
    }
  }
  return runs;
}

function input(runs: RunGrade[], baselineMean: number | null): QualificationInput {
  return {
    case_ids: CASES,
    repetitions_per_case: 3,
    runs,
    baseline: baselineMean === null
      ? { status: 'not_run', overall_mean: null, hard_failures: [] }
      : { status: 'graded', overall_mean: baselineMean, hard_failures: [] },
  };
}

test('rubric weights are the directive weights and sum to one', () => {
  assert.deepEqual(
    RUBRIC_DIMENSIONS.map((d) => [d.key, d.weight]),
    [
      ['factual_grounding', 0.25],
      ['decision_quality', 0.2],
      ['source_fidelity', 0.15],
      ['advisor_differentiation', 0.15],
      ['actionability_agency', 0.15],
      ['clarity_dissent_effort', 0.1],
    ],
  );
  assert.ok(Math.abs(rubricWeightsSum() - 1) < 1e-9);
});

test('rubric score formula: sum(weight x dimension) / 4 x 10', () => {
  assert.equal(rubricScore(ALL4), 10);
  assert.equal(rubricScore(dims(0, 0, 0, 0, 0, 0)), 0);
  // 0.25*4 + 0.20*3 + 0.15*4 + 0.15*3 + 0.15*4 + 0.10*3 = 3.55 -> 8.875
  assert.equal(rubricScore(dims(4, 3, 4, 3, 4, 3)), 8.875);
  assert.equal(rubricScore(SCORE_9_125), 9.125);
  assert.throws(() => rubricScore(dims(5, 4, 4, 4, 4, 4)));
});

test('a complete clean set at 9.125 with a 9.3 baseline qualifies', () => {
  const d = evaluateQualification(input(gradedRuns(SCORE_9_125), 9.3));
  assert.equal(d.qualified, true, JSON.stringify(d.reasons));
  assert.equal(d.overall_mean, 9.125);
  assert.equal(d.graded_runs, 30);
  assert.equal(d.planned_runs, 30);
});

test('an unfunded NOT_RUN set never qualifies (Section 32.5)', () => {
  const runs: RunGrade[] = [];
  for (const caseId of CASES) {
    for (let rep = 1; rep <= 3; rep++) {
      runs.push({
        case_id: caseId, repetition: rep, status: 'not_run',
        dimension_scores: null, hard_failures: [],
        not_run_reason: 'no live evaluation allowance',
      });
    }
  }
  const d = evaluateQualification(input(runs, null));
  assert.equal(d.qualified, false);
  assert.equal(d.graded_runs, 0);
  assert.ok(d.reasons.filter((r) => r.startsWith('run_not_graded')).length === 30);
  assert.ok(d.reasons.includes('baseline_not_run'));
});

test('one unresolved hard failure disqualifies despite a perfect mean', () => {
  const runs = gradedRuns(ALL4, (run) => {
    if (run.case_id === 'Q10' && run.repetition === 2) {
      run.hard_failures = ['wrong_speaker_passed_as_verified'];
    }
  });
  const d = evaluateQualification(input(runs, 9.9));
  assert.equal(d.qualified, false);
  assert.equal(d.overall_mean, 10);
  assert.ok(d.reasons.some((r) => r.startsWith('unresolved_hard_failure:Q10#2')));
  assert.ok(d.reasons.includes('new_hard_failure_vs_baseline:wrong_speaker_passed_as_verified'));
});

test('a single run below 7.5 disqualifies', () => {
  const runs = gradedRuns(ALL4, (run) => {
    if (run.case_id === 'Q09' && run.repetition === 1) run.dimension_scores = dims(2, 2, 2, 2, 2, 2);
  });
  const d = evaluateQualification(input(runs, 9.9));
  assert.equal(d.qualified, false);
  assert.ok(d.reasons.some((r) => r.startsWith('run_below_7_5:Q09#1:5')));
});

test('a case mean below 8.0 disqualifies even when every run is at least 7.5', () => {
  const runs = gradedRuns(ALL4, (run) => {
    if (run.case_id === 'Q06') run.dimension_scores = dims(3, 3, 3, 3, 3, 4); // 7.75
  });
  const d = evaluateQualification(input(runs, 9.9));
  assert.equal(d.qualified, false);
  assert.ok(d.reasons.some((r) => r.startsWith('case_mean_below_8:Q06:7.75')));
});

test('an overall mean below 8.5 disqualifies even when every case passes', () => {
  const d = evaluateQualification(input(gradedRuns(dims(3, 4, 3, 3, 4, 3)), 8.0)); // 8.375 each
  assert.equal(d.qualified, false);
  assert.ok(d.reasons.includes('overall_mean_below_8_5:8.375'));
});

test('grounding or fidelity below 3 in any run disqualifies despite a high score', () => {
  const runs = gradedRuns(ALL4, (run) => {
    if (run.case_id === 'Q02' && run.repetition === 3) run.dimension_scores = dims(2, 4, 4, 4, 4, 4); // 8.75
  });
  const d = evaluateQualification(input(runs, 9.9));
  assert.equal(d.qualified, false);
  assert.ok(d.reasons.includes('grounding_below_3:Q02#3'));
});

test('a baseline deficit above 0.25 disqualifies; at or under it does not', () => {
  const failing = evaluateQualification(input(gradedRuns(SCORE_9_125), 9.5));
  assert.equal(failing.qualified, false);
  assert.ok(failing.reasons.includes('baseline_deficit_above_0_25:0.375'));
  const passing = evaluateQualification(input(gradedRuns(SCORE_9_125), 9.375));
  assert.equal(passing.qualified, true, JSON.stringify(passing.reasons));
});

test('modes qualify separately: a full-mode record says nothing about quick mode', () => {
  const full = evaluateQualification(input(gradedRuns(ALL4), 9.9));
  assert.equal(full.qualified, true);
  const quick = evaluateQualification({ ...input([], null) });
  assert.equal(quick.qualified, false);
  assert.ok(quick.reasons.filter((r) => r.startsWith('run_not_graded')).length === 30);
});

test('blind differentiation thresholds: 80 percent overall, 60 percent per seat', () => {
  const seat = (seat_id: string, correct: number, total = 5) => ({ seat_id, correct, total });
  const passing = evaluateDifferentiation([
    seat('a', 4), seat('b', 4), seat('c', 4), seat('d', 4), seat('e', 4),
    seat('f', 4), seat('g', 4), seat('h', 5), seat('i', 5),
  ]); // 38/45 = 84.44 percent; every seat at least 80
  assert.equal(passing.pass, true, JSON.stringify(passing.reasons));
  const lowOverall = evaluateDifferentiation([
    seat('a', 4), seat('b', 4), seat('c', 4), seat('d', 4), seat('e', 4),
    seat('f', 4), seat('g', 4), seat('h', 4), seat('i', 3),
  ]); // 35/45 = 77.78 percent
  assert.equal(lowOverall.pass, false);
  assert.ok(lowOverall.reasons.some((r) => r.startsWith('overall_below_80')));
  const weakSeat = evaluateDifferentiation([
    seat('a', 5), seat('b', 5), seat('c', 5), seat('d', 5), seat('e', 5),
    seat('f', 5), seat('g', 5), seat('h', 5), seat('i', 2),
  ]); // 42/45 = 93.33 percent overall; seat i at 40
  assert.equal(weakSeat.pass, false);
  assert.ok(weakSeat.reasons.some((r) => r.startsWith('seat_below_60:i')));
});

test('blind strip removes names and catchphrases case-insensitively (T153 procedure)', () => {
  const card = 'Fixture card: As SIMON SINEK teaches in Start With Why, begin from purpose. The Golden Circle frames it.';
  const stripped = stripForBlindReview(card, ['Simon Sinek', 'Start With Why', 'Golden Circle']);
  assert.ok(!/sinek/i.test(stripped));
  assert.ok(!/start with why/i.test(stripped));
  assert.ok(!/golden circle/i.test(stripped));
  assert.ok(stripped.includes('[seat]'));
});
