/**
 * Council sizes (W77S-MODES): light / medium / heavy.
 *
 * One source of truth for the per-mode round policy, the consensus stop
 * rule constants and the advisor-card round ceiling. The four older modes
 * (full, selected, quick, consult) are unchanged and keep their own
 * behaviour in every consumer; nothing here reinterprets them.
 *
 * A ROUND is one pass in which every panel seat answers once. Round 1 is
 * the isolated opening; every later pass challenges the open cruxes from
 * the previous round's cards.
 */
import { SEAT_IDS } from './enums.js';

export const COUNCIL_SIZES = ['light', 'medium', 'heavy'] as const;
export type CouncilSize = (typeof COUNCIL_SIZES)[number];

/**
 * Every council size seats the FULL roster. Mode never selects a smaller
 * panel (Trevor decision 2026-10-25: "all of the modes should be all of the
 * agents... all council members are used"). Mode controls ROUNDS and
 * CONCURRENCY only.
 */
export const MODE_SEATS = SEAT_IDS.length;

export interface ModeRoundPolicy {
  /** Panel seats: the full roster in every mode. */
  seats: number;
  /** Rounds that always run before any stop rule may fire. */
  min_rounds: number;
  /** Hard ceiling on rounds. */
  max_rounds: number;
  /** Earliest round at which the consensus rule may stop; null never stops early. */
  stop_from_round: number | null;
  /** Provider-request cap for the session (the only enforced limit). */
  max_provider_requests: number;
  /** Provider calls dispatched at once (wave width) — the one concurrency knob. */
  max_concurrent_calls: number;
}

export const MODE_ROUND_POLICY: Readonly<Record<CouncilSize, ModeRoundPolicy>> = {
  light: {
    seats: MODE_SEATS,
    min_rounds: 2,
    max_rounds: 2,
    stop_from_round: null,
    max_provider_requests: 50,
    max_concurrent_calls: 3,
  },
  medium: {
    seats: MODE_SEATS,
    min_rounds: 1,
    max_rounds: 4,
    stop_from_round: 1,
    max_provider_requests: 50,
    max_concurrent_calls: MODE_SEATS,
  },
  heavy: {
    seats: MODE_SEATS,
    min_rounds: 3,
    max_rounds: 10,
    stop_from_round: 3,
    max_provider_requests: 100,
    max_concurrent_calls: MODE_SEATS,
  },
};

/** Seats that must share the same top option for the consensus stop rule. */
export const CONSENSUS_MIN_SEATS = 7;
/** Points by which the leading option must beat the runner-up. */
export const CONSENSUS_LEAD = 1.5;
/** Highest advisor-card round number a challenge pass may carry. */
export const MAX_ADVISOR_ROUND = 10;

export function isCouncilSize(mode: string): mode is CouncilSize {
  return (COUNCIL_SIZES as readonly string[]).includes(mode);
}
