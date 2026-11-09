/**
 * Golden vectors (directive Section 32.2) and canonical-hash fixtures.
 *
 * The arithmetic fixture is hand-calculated in the directive and verified
 * independently of this implementation: weights [2,3,2,3,3,2,3,2,2] total 22;
 * option A weighted sum 132 (score 6.0); option B weighted sum 168 (score
 * 168/22 = 7.63636..., display 7.6, spread 3); option C weighted sum 145
 * (score 145/22 = 6.59090..., display 6.6). If Tiffany Aliche abstains on B,
 * the sum becomes 150 over denominator 19, coverage 19/22 (about 86.36
 * percent), which still cannot produce an unconditional GO while a critical
 * affordability question is unresolved.
 *
 * The hash fixtures pin canonical serialization: the same logical value in
 * different key orders must hash identically in every consumer (T148).
 */

import { SEAT_IDS } from './enums.js';
import type { SeatScoreEntry } from './scoring.js';

export const GOLDEN_WEIGHTS: readonly number[] = [2, 3, 2, 3, 3, 2, 3, 2, 2];
export const GOLDEN_TOTAL_WEIGHT = 22;

function entries(scores: readonly (number | null)[]): SeatScoreEntry[] {
  return SEAT_IDS.map((seat_id, i) => ({
    seat_id,
    weight: GOLDEN_WEIGHTS[i],
    score: scores[i],
  }));
}

export const GOLDEN_SCORES = {
  A: entries([6, 5, 6, 8, 5, 6, 6, 6, 6]),
  B: entries([8, 8, 7, 6, 9, 8, 7, 8, 8]),
  C: entries([7, 9, 7, 3, 8, 6, 5, 7, 8]),
  /** B with Tiffany Aliche (seat index 3) abstaining: sum 150 over 19. */
  B_TIFFANY_ABSTAINS: entries([8, 8, 7, null, 9, 8, 7, 8, 8]),
} as const;

export const GOLDEN_EXPECTED = {
  A: { weighted_sum: 132, denominator: 22, score: 6.0, display_score: 6.0, coverage: 1, spread: 3 },
  B: { weighted_sum: 168, denominator: 22, score: 168 / 22, display_score: 7.6, coverage: 1, spread: 3 },
  C: { weighted_sum: 145, denominator: 22, score: 145 / 22, display_score: 6.6, coverage: 1, spread: 6 },
  B_TIFFANY_ABSTAINS: {
    weighted_sum: 150,
    denominator: 19,
    score: 150 / 19,
    display_score: 7.9,
    coverage: 19 / 22,
    spread: 2,
  },
} as const;

/**
 * Canonical-hash fixture: two key orderings of one logical payload. Both
 * must serialize to CANONICAL_TEXT and hash to the same digest everywhere.
 */
export const HASH_FIXTURE_A = {
  session_id: 'sess-golden-1',
  brief_revision: 1,
  options: [
    { id: 'A', label: 'Keep the current offer', kind: 'status_quo' },
    { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' },
  ],
  money: { amount_minor: 12500, currency: 'USD' },
  unknown_field: null,
} as const;

export const HASH_FIXTURE_B = {
  unknown_field: null,
  money: { currency: 'USD', amount_minor: 12500 },
  options: [
    { kind: 'status_quo', label: 'Keep the current offer', id: 'A' },
    { label: 'Pilot the revised offer', kind: 'bounded_test', id: 'B' },
  ],
  brief_revision: 1,
  session_id: 'sess-golden-1',
} as const;

export const HASH_FIXTURE_CANONICAL_TEXT =
  '{"brief_revision":1,"money":{"amount_minor":12500,"currency":"USD"},"options":[{"id":"A","kind":"status_quo","label":"Keep the current offer"},{"id":"B","kind":"bounded_test","label":"Pilot the revised offer"}],"session_id":"sess-golden-1","unknown_field":null}';
