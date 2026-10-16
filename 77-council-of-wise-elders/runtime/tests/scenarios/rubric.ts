/**
 * Section 32.5 qualification mechanics (CWE-042).
 *
 * Pure, deterministic functions that turn retained run grades into a
 * qualification decision, mechanically and only mechanically:
 *
 * - rubric weights are the directive's and sum to exactly 1.00;
 * - a run's rubric score is sum(weight x dimension_score) / 4 x 10,
 *   with dimension scores on the 0 to 4 scale;
 * - a mode qualifies only when every planned repetition of every case
 *   in the fixed qualification set is present and graded. A missing or
 *   NOT_RUN run keeps the mode unqualified: an unfunded test stays
 *   NOT_RUN, never PASS (Section 32.5);
 * - zero unresolved hard failures across all runs, overall mean at
 *   least 8.5, every case's repetition mean at least 8.0, no
 *   individual run below 7.5, and factual grounding plus source
 *   fidelity at least 3 of 4 in every run;
 * - baseline comparison: no more than a 0.25-point overall deficit
 *   against the single-advisor baseline and no new hard failure;
 * - modes qualify separately: this module decides one mode's record
 *   from that mode's runs only, so a full-mode result cannot transfer
 *   to quick, selected, or consult modes;
 * - blind differentiation passes only at 80 percent correct matches
 *   overall and at least 60 percent for every seat (Section 32.5).
 *
 * Nothing here generates, grades, or simulates a council run. It is
 * the arithmetic a qualification record is checked with after real
 * runs exist, and it is tested here with synthetic grade sets whose
 * expected outcomes are computed by hand in rubric.test.ts.
 */

export const RUBRIC_DIMENSIONS = [
  { key: 'factual_grounding', weight: 0.25 },
  { key: 'decision_quality', weight: 0.2 },
  { key: 'source_fidelity', weight: 0.15 },
  { key: 'advisor_differentiation', weight: 0.15 },
  { key: 'actionability_agency', weight: 0.15 },
  { key: 'clarity_dissent_effort', weight: 0.1 },
] as const;

export type RubricDimensionKey = (typeof RUBRIC_DIMENSIONS)[number]['key'];
export type DimensionScores = Record<RubricDimensionKey, number>;

/** The hard-failure kinds named in Section 32.5. */
export const HARD_FAILURE_KINDS = [
  'fabricated_case_fact_or_quotation',
  'wrong_speaker_passed_as_verified',
  'confirmed_hard_constraint_ignored',
  'false_model_identity_or_qualification',
  'unauthorized_data_or_action',
  'full_mode_claimed_missing_seat_ran',
  'corrupted_scoring_or_ratification',
  'toxic_or_professionally_unsafe_overreach',
] as const;
export type HardFailureKind = (typeof HARD_FAILURE_KINDS)[number];

export type RunStatus = 'graded' | 'not_run';

export interface RunGrade {
  case_id: string;
  repetition: number;
  status: RunStatus;
  /** Present exactly when status is 'graded'. Scores are 0 to 4. */
  dimension_scores: DimensionScores | null;
  /** Unresolved hard failures recorded against this run. */
  hard_failures: readonly HardFailureKind[];
  /** Recorded reason when status is 'not_run'. */
  not_run_reason: string | null;
}

export interface QualificationInput {
  /** Cases in the fixed qualification set (Q01 to Q10). */
  case_ids: readonly string[];
  /** Planned repetitions per case (3 for full-mode qualification). */
  repetitions_per_case: number;
  runs: readonly RunGrade[];
  /** Baseline record, when the baseline comparison has been run. */
  baseline: {
    status: RunStatus;
    overall_mean: number | null;
    hard_failures: readonly HardFailureKind[];
  } | null;
}

export interface QualificationDecision {
  qualified: boolean;
  /** Machine-readable reasons; empty exactly when qualified. */
  reasons: string[];
  overall_mean: number | null;
  per_case_means: Record<string, number | null>;
  graded_runs: number;
  planned_runs: number;
}

export function rubricWeightsSum(): number {
  return RUBRIC_DIMENSIONS.reduce((n, d) => n + d.weight, 0);
}

const round6 = (n: number): number => Math.round(n * 1e6) / 1e6;

/** One run's rubric score on the 0 to 10 scale (Section 32.5). */
export function rubricScore(scores: DimensionScores): number {
  let weighted = 0;
  for (const d of RUBRIC_DIMENSIONS) {
    const s = scores[d.key];
    if (typeof s !== 'number' || s < 0 || s > 4) {
      throw new Error(`dimension ${d.key} score out of range: ${String(s)}`);
    }
    weighted += d.weight * s;
  }
  return round6((weighted / 4) * 10);
}

/**
 * Decide one mode's qualification from that mode's retained grades.
 * Every threshold is the directive's; none is adjustable here, and
 * reviewers cannot change them after seeing results (Section 32.5).
 */
export function evaluateQualification(
  input: QualificationInput,
): QualificationDecision {
  const reasons: string[] = [];
  const planned = input.case_ids.length * input.repetitions_per_case;
  const byKey = new Map<string, RunGrade>();
  for (const run of input.runs) {
    byKey.set(`${run.case_id}#${run.repetition}`, run);
  }

  let graded = 0;
  const runScores: number[] = [];
  const perCase = new Map<string, number[]>();
  let hardFailureFree = true;

  for (const caseId of input.case_ids) {
    perCase.set(caseId, []);
    for (let rep = 1; rep <= input.repetitions_per_case; rep++) {
      const run = byKey.get(`${caseId}#${rep}`);
      if (!run || run.status !== 'graded' || run.dimension_scores === null) {
        reasons.push(`run_not_graded:${caseId}#${rep}`);
        continue;
      }
      graded++;
      const score = rubricScore(run.dimension_scores);
      runScores.push(score);
      perCase.get(caseId)!.push(score);
      if (run.hard_failures.length > 0) {
        hardFailureFree = false;
        reasons.push(
          `unresolved_hard_failure:${caseId}#${rep}:${run.hard_failures.join('+')}`,
        );
      }
      if (score < 7.5) reasons.push(`run_below_7_5:${caseId}#${rep}:${round6(score)}`);
      if (run.dimension_scores.factual_grounding < 3) {
        reasons.push(`grounding_below_3:${caseId}#${rep}`);
      }
      if (run.dimension_scores.source_fidelity < 3) {
        reasons.push(`source_fidelity_below_3:${caseId}#${rep}`);
      }
    }
  }

  const perCaseMeans: Record<string, number | null> = {};
  for (const [caseId, scores] of perCase) {
    perCaseMeans[caseId] = scores.length === 0
      ? null
      : round6(scores.reduce((a, b) => a + b, 0) / scores.length);
    if (perCaseMeans[caseId] !== null && perCaseMeans[caseId]! < 8.0) {
      reasons.push(`case_mean_below_8:${caseId}:${perCaseMeans[caseId]}`);
    }
  }

  const overallMean = runScores.length === 0
    ? null
    : round6(runScores.reduce((a, b) => a + b, 0) / runScores.length);
  if (overallMean !== null && overallMean < 8.5) {
    reasons.push(`overall_mean_below_8_5:${overallMean}`);
  }

  if (input.baseline === null || input.baseline.status !== 'graded' ||
      input.baseline.overall_mean === null) {
    reasons.push('baseline_not_run');
  } else if (overallMean !== null) {
    const deficit = round6(input.baseline.overall_mean - overallMean);
    if (deficit > 0.25) reasons.push(`baseline_deficit_above_0_25:${deficit}`);
    const councilKinds = new Set<HardFailureKind>();
    for (const run of input.runs) {
      for (const k of run.hard_failures) councilKinds.add(k);
    }
    const baselineKinds = new Set(input.baseline.hard_failures);
    for (const k of councilKinds) {
      if (!baselineKinds.has(k)) reasons.push(`new_hard_failure_vs_baseline:${k}`);
    }
  }

  return {
    qualified: reasons.length === 0 && graded === planned && hardFailureFree,
    reasons,
    overall_mean: overallMean,
    per_case_means: perCaseMeans,
    graded_runs: graded,
    planned_runs: planned,
  };
}

export interface DifferentiationSeatResult {
  seat_id: string;
  correct: number;
  total: number;
}

export interface DifferentiationDecision {
  pass: boolean;
  overall_percent: number;
  per_seat_percent: Record<string, number>;
  reasons: string[];
}

/**
 * Blind differentiation thresholds (Section 32.5): at least 80 percent
 * correct matches overall and at least 60 percent for every seat.
 */
export function evaluateDifferentiation(
  seats: readonly DifferentiationSeatResult[],
): DifferentiationDecision {
  const reasons: string[] = [];
  let correct = 0;
  let total = 0;
  const perSeat: Record<string, number> = {};
  for (const s of seats) {
    correct += s.correct;
    total += s.total;
    perSeat[s.seat_id] = s.total === 0 ? 0 : round6((s.correct / s.total) * 100);
    if (perSeat[s.seat_id] < 60) reasons.push(`seat_below_60:${s.seat_id}:${perSeat[s.seat_id]}`);
  }
  const overall = total === 0 ? 0 : round6((correct / total) * 100);
  if (overall < 80) reasons.push(`overall_below_80:${overall}`);
  return { pass: reasons.length === 0, overall_percent: overall, per_seat_percent: perSeat, reasons };
}

/**
 * Blind-review preparation (T153 procedure): remove seat and person
 * identifiers and known catchphrases from a card so a reviewer must
 * match it to a role description from content alone. Replacements are
 * uniform so the strip itself leaks nothing about which seat wrote
 * the card.
 */
export function stripForBlindReview(
  text: string,
  identifiers: readonly string[],
): string {
  let out = text;
  const sorted = [...identifiers].sort((a, b) => b.length - a.length);
  for (const id of sorted) {
    if (id.length === 0) continue;
    const escaped = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    out = out.replace(new RegExp(escaped, 'gi'), '[seat]');
  }
  return out;
}
