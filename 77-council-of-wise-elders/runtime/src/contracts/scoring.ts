/**
 * Deterministic scoring arithmetic (directive Sections 12.2 and 12.4).
 *
 * Arithmetic is code, never model output. Rules:
 * - weighted score = sum(weight * score) / sum(weight) over seats that
 *   actually scored the option; a null (abstention) is never a zero;
 * - coverage = scored weight / total active weight;
 * - spread = max scored value - min scored value, null when nothing scored;
 * - full precision is kept internally; display rounds to one decimal and
 *   display rounding changes no decision (test contract T148);
 * - a GO-style label requires at least 80 percent coverage AND no unresolved
 *   critical-domain abstention (the gate itself lives with the verdict
 *   builder in later units; the constants and label bands live here);
 * - a tie within 0.25 points is a near tie, not false precision.
 */

import { ContractError } from './errors';
import type { VerdictLabel } from './enums';

export interface SeatScoreEntry {
  seat_id: string;
  /** Frozen relevance weight, 1..3 (Section 12.1). */
  weight: number;
  /** 0..10, or null for an explicit abstention. Never NaN. */
  score: number | null;
}

export interface OptionScoreResult {
  weighted_sum: number;
  denominator: number;
  /** Null when no seat scored the option; never reported as 0. */
  score: number | null;
  display_score: number | null;
  coverage: number;
  spread: number | null;
}

export function computeOptionScore(
  entries: readonly SeatScoreEntry[],
  totalActiveWeight: number,
): OptionScoreResult {
  if (!Number.isFinite(totalActiveWeight) || totalActiveWeight <= 0) {
    throw new ContractError(
      'SCHEMA_VALIDATION',
      'totalActiveWeight must be a positive finite number',
      'weights',
    );
  }
  let weightedSum = 0;
  let denominator = 0;
  let min: number | null = null;
  let max: number | null = null;
  for (const entry of entries) {
    if (!Number.isInteger(entry.weight) || entry.weight < 1 || entry.weight > 3) {
      throw new ContractError(
        'SCHEMA_VALIDATION',
        `weight for seat ${entry.seat_id} must be an integer 1..3`,
        'weights',
      );
    }
    if (entry.score === null) continue; // abstention is not zero
    if (!Number.isFinite(entry.score) || entry.score < 0 || entry.score > 10) {
      throw new ContractError(
        'SCORE_OUT_OF_RANGE',
        `score for seat ${entry.seat_id} must be finite and within 0..10`,
        'score',
      );
    }
    weightedSum += entry.weight * entry.score;
    denominator += entry.weight;
    min = min === null ? entry.score : Math.min(min, entry.score);
    max = max === null ? entry.score : Math.max(max, entry.score);
  }
  const score = denominator === 0 ? null : weightedSum / denominator;
  return {
    weighted_sum: weightedSum,
    denominator,
    score,
    display_score: score === null ? null : Math.round(score * 10) / 10,
    coverage: denominator / totalActiveWeight,
    spread: min === null || max === null ? null : max - min,
  };
}

/** Minimum weighted coverage for a GO-style label (Section 12.2 policy). */
export const GO_COVERAGE_THRESHOLD = 0.8;

/** Score difference at or below which two options are a near tie. */
export const NEAR_TIE_BAND = 0.25;

export function isNearTie(a: number, b: number): boolean {
  return Math.abs(a - b) <= NEAR_TIE_BAND;
}

/** Default label bands (Section 12.4), applied AFTER eligibility checks. */
export function labelForScore(score: number): VerdictLabel {
  if (!Number.isFinite(score)) {
    throw new ContractError('NON_FINITE_NUMBER', 'labelForScore requires a finite score', 'score');
  }
  if (score >= 7.5) return 'GO';
  if (score >= 6.0) return 'GO_WITH_CONDITIONS';
  if (score >= 4.5) return 'RESHAPE';
  return 'DONT_DO_IT';
}
