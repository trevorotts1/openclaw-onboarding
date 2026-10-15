/**
 * Deterministic decision analysis (directive Sections 12.2 to 12.7,
 * CWE-026 build step 1).
 *
 * Pure services over locked schemas and synthetic or real cards:
 * weighted scores, coverage, spread, option eligibility, verdict
 * labels, near ties, and the frozen critical-domain gates. Nothing here
 * waits for a live discussion engine, and nothing here invents an
 * argument a seat did not make.
 *
 * Arithmetic is delegated to the CWE-003 contracts scoring module
 * (computeOptionScore), the same module the CWE-004 core engine uses,
 * so these services and the core agree byte-for-byte on the golden
 * fixtures. This module adds what the contracts module deliberately
 * leaves to the verdict layer: eligibility, gates, and labels.
 *
 * Semantics enforced (Sections 12.2, 12.3, 12.4, 12.7):
 * - A null score is an explicit abstention. It is never a zero, never
 *   inferred support, and it reduces the denominator and coverage.
 * - A seat with no returned card is MISSING, reported separately. A
 *   timeout is one kind of missing; it is never relabeled an
 *   abstention (T045's boundary, enforced by input separation here).
 * - Eligibility is decided BEFORE labels: a confirmed hard-constraint
 *   FAIL disqualifies the option no matter how high it scores; a hard
 *   UNKNOWN blocks unconditional approval for that option.
 * - A GO-style label needs at least 80 percent weighted coverage on the
 *   recommended option AND no unresolved critical-domain gate on it.
 *   Mathematical coverage and decision safety stay separate: the
 *   golden abstention variant keeps 86.36 percent coverage and still
 *   cannot be an unconditional GO (Section 32.2).
 * - A missing critical assessment stays not_assessed and can never be
 *   laundered into PASS by a high mean, an abstention relabel, or a
 *   user checkbox (T144). An option-specific classification permits a
 *   justified safe alternative without endorsing an exposed unknown
 *   (T145).
 * - A difference within 0.25 is a near tie: the tradeoff is preserved.
 *   The less irreversible, lower-exposure option is preferred only
 *   when recorded exposure evidence supports that distinction;
 *   otherwise the unresolved crux and the next fact needed are
 *   returned instead of a rounding decision (T044).
 */

import {
  computeOptionScore,
  ContractError,
  GO_COVERAGE_THRESHOLD,
  isNearTie,
  labelForScore,
  NEAR_TIE_BAND,
  SEAT_IDS,
  CRITICAL_DOMAINS,
  type ConstraintResult,
  type CriticalDomain,
  type CriticalDomainRequirement,
  type DecisionBrief,
  type DecisionOption,
  type HardConstraintFinding,
  type SeatId,
  type SeatScoreEntry,
  type VerdictLabel,
} from '../contracts/index.js';
import type { CriticalDomainApplicability } from './critical-domains.js';

/** One seat's final-round judgment on one option, from a returned card. */
export interface OptionScoreInput {
  option_id: string;
  seat_id: SeatId;
  /** 0..10, or null for an explicit abstention. */
  score: number | null;
}

export type ExposureLevel = 'low' | 'medium' | 'high';

export interface OptionExposure {
  option_id: string;
  irreversibility: ExposureLevel;
  exposure: ExposureLevel;
}

/** A qualified professional review outcome for one option, or global. */
export interface ProfessionalReviewOutcome {
  /** Null means the outcome applies to every option. */
  option_id: string | null;
  result: ConstraintResult;
}

export interface DecisionInput {
  options: readonly DecisionOption[];
  /** The active panel for this session. */
  active_seat_ids: readonly SeatId[];
  /** Frozen relevance weights (Section 12.1); required for every seat. */
  weights: Partial<Record<SeatId, number>>;
  /** Scores from returned final-round cards only. */
  scores: readonly OptionScoreInput[];
  /** Active seats that returned no card. Never scored, never abstentions. */
  missing_seat_ids?: readonly SeatId[];
  /** Subset of missing seats whose absence was a timeout. */
  timed_out_seat_ids?: readonly SeatId[];
  /** Hard-constraint findings per option (Section 12.3). */
  hard_constraints?: readonly HardConstraintFinding[];
  /** Frozen critical-domain classification from the reviewed brief. */
  critical_domains?: readonly CriticalDomainRequirement[];
  /** Per-option domain applicability; a domain with no pairs is global. */
  critical_domain_applicability?: readonly CriticalDomainApplicability[];
  /** Outcomes for the qualified_professional_review domain. */
  professional_reviews?: readonly ProfessionalReviewOutcome[];
  /** Recorded exposure evidence used only for near-tie resolution. */
  option_exposure?: readonly OptionExposure[];
}

export interface OptionAnalysis {
  option_id: string;
  eligible: boolean;
  eligibility_reasons: string[];
  weighted_sum: number;
  denominator: number;
  /** Null when no seat scored the option; never reported as 0. */
  score: number | null;
  display_score: number | null;
  coverage: number;
  spread: number | null;
  scored_seat_ids: SeatId[];
  abstained_seat_ids: SeatId[];
  hard_failure_constraint_ids: string[];
  hard_unknown_constraint_ids: string[];
  /** Critical domains still gating this option (decision safety). */
  critical_blockers: CriticalDomain[];
  /** Required reviewers who abstained on this option. */
  critical_abstentions: SeatId[];
  /** The label this option would carry if recommended, else null. */
  band_label: VerdictLabel | null;
}

export interface NearTieAnalysis {
  present: boolean;
  option_ids: string[];
  score_gap: number | null;
  resolution: 'less_irreversible_preferred' | 'unresolved_crux' | null;
  preferred_option_id: string | null;
  /** Named when the tie cannot be resolved on recorded evidence. */
  next_fact_needed: string | null;
}

export interface DecisionAnalysis {
  verification_level: 'contract_tested';
  total_active_weight: number;
  options: OptionAnalysis[];
  /** Highest-ranked eligible scored option before gate labels. */
  leading_option_id: string | null;
  /** The option the verdict may recommend; null when none is justified. */
  recommended_option_id: string | null;
  label: VerdictLabel;
  label_reasons: string[];
  /** Named prerequisites behind a WAIT, in deterministic order. */
  prerequisites_needed: string[];
  near_tie: NearTieAnalysis;
  missing_seat_ids: SeatId[];
  timed_out_seat_ids: SeatId[];
}

const EXPOSURE_RANK: Record<ExposureLevel, number> = { low: 0, medium: 1, high: 2 };

function assertKnownSeat(seatId: string, path: string): void {
  if (!(SEAT_IDS as readonly string[]).includes(seatId)) {
    throw new ContractError('UNKNOWN_ENUM_VALUE', `unknown seat id ${seatId}`, path);
  }
}

function domainAppliesTo(
  domain: CriticalDomain,
  optionId: string,
  applicability: readonly CriticalDomainApplicability[],
): boolean {
  const pairs = applicability.filter((p) => p.domain === domain);
  if (pairs.length === 0) return true;
  return pairs.some((p) => p.option_id === optionId);
}

/**
 * Derive the hard-constraint findings a verdict is evaluated against
 * (Section 12.3; CWE-050 reconciliation of CWE-026 divergence (a)).
 *
 * The canonical rule, owned by CWE-026's analysis: findings are
 * APPLIED, never assumed away. A recorded checker result (supplied by
 * the composition from a deterministic check, a seat, or a qualified
 * professional) wins for its constraint and option. Where no checker
 * has recorded a result, the honest deterministic state is `unknown`
 * from `deterministic_code` with no evidence: an unchecked hard
 * constraint is not a passed one, and under the analysis an unknown
 * blocks an unconditional recommendation until it is checked. The
 * pre-reconciliation CWE-004 engine emitted an empty findings list,
 * which silently treated every hard constraint as satisfied; that
 * behavior is retired everywhere by this shared derivation.
 */
export function deriveHardConstraintFindings(
  brief: DecisionBrief,
  recorded: readonly HardConstraintFinding[] = [],
): HardConstraintFinding[] {
  const recordedByKey = new Map<string, HardConstraintFinding>(
    recorded.map((f) => [`${f.constraint_id}::${f.option_id}`, f]),
  );
  const findings: HardConstraintFinding[] = [];
  for (const constraint of brief.constraints) {
    if (!constraint.hard) continue;
    const optionIds =
      constraint.applies_to_option_ids.length > 0
        ? constraint.applies_to_option_ids
        : brief.options.map((o) => o.id);
    for (const optionId of optionIds) {
      const existing = recordedByKey.get(`${constraint.id}::${optionId}`);
      if (existing) {
        findings.push(existing);
      } else {
        findings.push({
          constraint_id: constraint.id,
          option_id: optionId,
          result: 'unknown',
          checker: 'deterministic_code',
          evidence_ids: [],
        });
      }
    }
  }
  return findings;
}

/**
 * Analyze a scored decision. Pure and deterministic: no clock, no
 * randomness, no host access. Throws ContractError on malformed input
 * (duplicate seats or options, unknown references, missing weights);
 * decision-shaped problems (abstentions, disqualifications, gates) are
 * reported in the result, never thrown.
 */
export function analyzeDecision(input: DecisionInput): DecisionAnalysis {
  // ---- structural validation -------------------------------------------
  if (input.options.length === 0) {
    throw new ContractError('SCHEMA_VALIDATION', 'at least one option is required', 'options');
  }
  const optionIds = new Set<string>();
  for (const option of input.options) {
    if (optionIds.has(option.id)) {
      throw new ContractError('DUPLICATE_OPTION', `duplicate option id ${option.id}`, 'options');
    }
    optionIds.add(option.id);
  }
  const activeSeats = new Set<SeatId>();
  for (const seatId of input.active_seat_ids) {
    assertKnownSeat(seatId, 'active_seat_ids');
    if (activeSeats.has(seatId)) {
      throw new ContractError('SCHEMA_VALIDATION', `duplicate active seat ${seatId}`, 'active_seat_ids');
    }
    activeSeats.add(seatId);
  }
  let totalActiveWeight = 0;
  for (const seatId of input.active_seat_ids) {
    const weight = input.weights[seatId];
    if (weight === undefined) {
      throw new ContractError(
        'SCHEMA_VALIDATION',
        `frozen relevance weight missing for seat ${seatId} (Section 12.1)`,
        'weights',
      );
    }
    totalActiveWeight += weight;
  }

  const missing = new Set<SeatId>(input.missing_seat_ids ?? []);
  const timedOut = new Set<SeatId>(input.timed_out_seat_ids ?? []);
  for (const seatId of missing) assertKnownSeat(seatId, 'missing_seat_ids');
  for (const seatId of timedOut) {
    assertKnownSeat(seatId, 'timed_out_seat_ids');
    if (!missing.has(seatId)) {
      throw new ContractError(
        'SCHEMA_VALIDATION',
        `timed out seat ${seatId} must also be listed as missing`,
        'timed_out_seat_ids',
      );
    }
  }

  const scoredKeys = new Set<string>();
  const entriesByOption = new Map<string, SeatScoreEntry[]>();
  for (const entry of input.scores) {
    assertKnownSeat(entry.seat_id, 'scores.seat_id');
    if (!optionIds.has(entry.option_id)) {
      throw new ContractError(
        'INVALID_REFERENCE',
        `score references unknown option ${entry.option_id}`,
        'scores.option_id',
      );
    }
    if (!activeSeats.has(entry.seat_id)) {
      throw new ContractError(
        'INVALID_REFERENCE',
        `score from seat ${entry.seat_id} which is not on the active panel`,
        'scores.seat_id',
      );
    }
    if (missing.has(entry.seat_id)) {
      throw new ContractError(
        'SCHEMA_VALIDATION',
        `seat ${entry.seat_id} is listed both as scored and as missing`,
        'scores.seat_id',
      );
    }
    const key = `${entry.option_id}:${entry.seat_id}`;
    if (scoredKeys.has(key)) {
      throw new ContractError(
        'SCHEMA_VALIDATION',
        `duplicate score for seat ${entry.seat_id} on option ${entry.option_id}`,
        'scores',
      );
    }
    scoredKeys.add(key);
    const list = entriesByOption.get(entry.option_id) ?? [];
    list.push({
      seat_id: entry.seat_id,
      weight: input.weights[entry.seat_id] as number,
      score: entry.score,
    });
    entriesByOption.set(entry.option_id, list);
  }

  const findingsByOption = new Map<string, HardConstraintFinding[]>();
  for (const finding of input.hard_constraints ?? []) {
    if (!optionIds.has(finding.option_id)) {
      throw new ContractError(
        'INVALID_REFERENCE',
        `hard constraint finding references unknown option ${finding.option_id}`,
        'hard_constraints.option_id',
      );
    }
    const list = findingsByOption.get(finding.option_id) ?? [];
    list.push(finding);
    findingsByOption.set(finding.option_id, list);
  }

  const applicability = input.critical_domain_applicability ?? [];
  const requirements = input.critical_domains ?? [];

  // ---- per-option analysis ---------------------------------------------
  const analyses: OptionAnalysis[] = input.options.map((option) => {
    const entries = entriesByOption.get(option.id) ?? [];
    const result = computeOptionScore(entries, totalActiveWeight);
    const scoredSeatIds = entries
      .filter((e) => e.score !== null)
      .map((e) => e.seat_id as SeatId);
    const abstainedSeatIds = entries
      .filter((e) => e.score === null)
      .map((e) => e.seat_id as SeatId);

    const findings = findingsByOption.get(option.id) ?? [];
    const hardFailures = findings.filter((f) => f.result === 'fail').map((f) => f.constraint_id);
    const hardUnknowns = findings
      .filter((f) => f.result === 'unknown')
      .map((f) => f.constraint_id);

    const eligibilityReasons: string[] = hardFailures.map(
      (id) => `hard constraint ${id} confirmed FAIL; option is disqualified (Section 12.3)`,
    );
    let eligible = hardFailures.length === 0;

    // Professional review failure is a hard failure of the option, not
    // a score adjustment (Section 12.7).
    const professionalOutcomes = (input.professional_reviews ?? []).filter(
      (r) => r.option_id === null || r.option_id === option.id,
    );
    if (professionalOutcomes.some((r) => r.result === 'fail')) {
      eligible = false;
      eligibilityReasons.push(
        'qualified professional review returned FAIL for this option; no seat vote can override it (Section 12.7)',
      );
    }

    // Frozen critical-domain gates for this option.
    const blockers: CriticalDomain[] = [];
    const criticalAbstentions: SeatId[] = [];
    for (const domain of CRITICAL_DOMAINS) {
      const requirement = requirements.find((r) => r.domain === domain);
      if (!requirement) continue;
      if (!domainAppliesTo(domain, option.id, applicability)) continue;
      let blocked = false;
      if (requirement.status !== 'assessed') blocked = true;
      const requiredSeat = requirement.required_seat_id;
      if (requiredSeat !== null) {
        const seatEntry = entries.find((e) => e.seat_id === requiredSeat);
        if (seatEntry && seatEntry.score === null) {
          blocked = true;
          if (!criticalAbstentions.includes(requiredSeat)) {
            criticalAbstentions.push(requiredSeat);
          }
        }
        if (missing.has(requiredSeat)) blocked = true;
      }
      if (domain === 'qualified_professional_review') {
        if (professionalOutcomes.some((r) => r.result === 'unknown')) blocked = true;
      }
      if (blocked) blockers.push(domain);
    }

    const gated =
      hardUnknowns.length > 0 || blockers.length > 0 || result.coverage < GO_COVERAGE_THRESHOLD;
    const bandLabel =
      eligible && result.score !== null && !gated ? labelForScore(result.score) : null;

    return {
      option_id: option.id,
      eligible,
      eligibility_reasons: eligibilityReasons,
      weighted_sum: result.weighted_sum,
      denominator: result.denominator,
      score: result.score,
      display_score: result.display_score,
      coverage: result.coverage,
      spread: result.spread,
      scored_seat_ids: scoredSeatIds,
      abstained_seat_ids: abstainedSeatIds,
      hard_failure_constraint_ids: hardFailures,
      hard_unknown_constraint_ids: hardUnknowns,
      critical_blockers: blockers,
      critical_abstentions: criticalAbstentions,
      band_label: bandLabel,
    };
  });

  const byId = new Map(analyses.map((a) => [a.option_id, a]));

  // ---- ranking -----------------------------------------------------------
  const ranked = analyses
    .filter((a) => a.eligible && a.score !== null)
    .sort((a, b) => (b.score as number) - (a.score as number));
  const leading = ranked[0] ?? null;

  // ---- near tie ------------------------------------------------------------
  const nearTie: NearTieAnalysis = {
    present: false,
    option_ids: [],
    score_gap: null,
    resolution: null,
    preferred_option_id: null,
    next_fact_needed: null,
  };
  let candidate = leading;
  if (leading && ranked.length > 1) {
    const second = ranked[1];
    if (second.option_id !== leading.option_id && isNearTie(leading.score as number, second.score as number)) {
      nearTie.present = true;
      nearTie.option_ids = [leading.option_id, second.option_id];
      nearTie.score_gap = (leading.score as number) - (second.score as number);
      const exposureById = new Map(
        (input.option_exposure ?? []).map((e) => [e.option_id, e]),
      );
      const leadExposure = exposureById.get(leading.option_id);
      const secondExposure = exposureById.get(second.option_id);
      const strictlySafer =
        leadExposure !== undefined &&
        secondExposure !== undefined &&
        EXPOSURE_RANK[secondExposure.irreversibility] <= EXPOSURE_RANK[leadExposure.irreversibility] &&
        EXPOSURE_RANK[secondExposure.exposure] <= EXPOSURE_RANK[leadExposure.exposure] &&
        (EXPOSURE_RANK[secondExposure.irreversibility] < EXPOSURE_RANK[leadExposure.irreversibility] ||
          EXPOSURE_RANK[secondExposure.exposure] < EXPOSURE_RANK[leadExposure.exposure]);
      if (strictlySafer) {
        nearTie.resolution = 'less_irreversible_preferred';
        nearTie.preferred_option_id = second.option_id;
        candidate = second;
      } else {
        nearTie.resolution = 'unresolved_crux';
        nearTie.preferred_option_id = leading.option_id;
        nearTie.next_fact_needed = `Evidence that distinguishes option ${leading.option_id} from option ${second.option_id} on the crux behind their near tie (score gap ${nearTie.score_gap.toFixed(4)} within the ${NEAR_TIE_BAND} band); the tradeoff is preserved, not resolved by rounding.`;
      }
    }
  }

  // ---- verdict label -------------------------------------------------------
  const labelReasons: string[] = [];
  const prerequisites: string[] = [];
  let label: VerdictLabel;
  let recommended: string | null = null;

  if (!leading || !candidate) {
    label = 'INSUFFICIENT_EVIDENCE';
    const anyEligible = analyses.some((a) => a.eligible);
    labelReasons.push(
      anyEligible
        ? 'No eligible option received any score; a score is null, never 0, so no justified recommendation can be made.'
        : 'Every option is disqualified by a confirmed hard-constraint failure; no justified recommendation can be made.',
    );
  } else if (candidate.coverage < GO_COVERAGE_THRESHOLD) {
    label = 'INSUFFICIENT_EVIDENCE';
    labelReasons.push(
      `Option ${candidate.option_id} has weighted score coverage ${(candidate.coverage * 100).toFixed(2)} percent, below the 80 percent policy threshold for a GO-style label (Section 12.2); missing scores are null and reduce coverage, never counted as zero.`,
    );
    prerequisites.push(
      `Obtain scored judgments covering at least 80 percent of the active weight for option ${candidate.option_id}.`,
    );
  } else if (candidate.hard_unknown_constraint_ids.length > 0) {
    label = 'WAIT';
    recommended = candidate.option_id;
    for (const id of candidate.hard_unknown_constraint_ids) {
      const prerequisite = `Resolve hard constraint ${id} for option ${candidate.option_id} with checkable evidence; an UNKNOWN blocks unconditional approval (Section 12.3).`;
      prerequisites.push(prerequisite);
      labelReasons.push(prerequisite);
    }
  } else if (candidate.critical_blockers.length > 0) {
    label = 'WAIT';
    recommended = candidate.option_id;
    for (const domain of candidate.critical_blockers) {
      const requirement = requirements.find((r) => r.domain === domain);
      const questions = requirement?.unresolved_questions ?? [];
      if (questions.length > 0) {
        for (const q of questions) prerequisites.push(q);
      } else {
        prerequisites.push(
          `Obtain the frozen critical-domain assessment for ${domain} (required reviewer: ${
            requirement?.required_seat_id ?? 'qualified professional'
          }); a missing critical judgment cannot become PASS by score, relabel, or checkbox (Section 12.7).`,
        );
      }
      labelReasons.push(
        `Critical domain ${domain} is unresolved for option ${candidate.option_id}${
          candidate.critical_abstentions.length > 0
            ? ` (critical abstention by ${candidate.critical_abstentions.join(', ')})`
            : ''
        }; mathematical coverage does not override decision safety.`,
      );
    }
  } else {
    const band = labelForScore(candidate.score as number);
    label = band;
    if (band === 'DONT_DO_IT') {
      const statusQuo = input.options.find(
        (o) => o.kind === 'status_quo' && o.id !== candidate?.option_id,
      );
      const statusQuoAnalysis = statusQuo ? byId.get(statusQuo.id) : undefined;
      if (statusQuo && statusQuoAnalysis && statusQuoAnalysis.eligible) {
        recommended = statusQuo.id;
        labelReasons.push(
          `The highest-ranked change option ${candidate.option_id} scores ${candidate.score?.toFixed(4)} (display ${candidate.display_score}), below the 4.5 DON'T DO IT floor; the recommendation is to keep the current course (option ${statusQuo.id}).`,
        );
      } else {
        recommended = null;
        labelReasons.push(
          `The highest-ranked option ${candidate.option_id} scores ${candidate.score?.toFixed(4)} (display ${candidate.display_score}), below the 4.5 DON'T DO IT floor, and no eligible status quo option exists to recommend.`,
        );
      }
    } else {
      recommended = candidate.option_id;
      labelReasons.push(
        `Option ${candidate.option_id} leads with score ${candidate.score?.toFixed(4)} (display ${candidate.display_score}), coverage ${(candidate.coverage * 100).toFixed(2)} percent, and no unresolved critical gate.`,
      );
    }
    if (nearTie.present && nearTie.resolution === 'less_irreversible_preferred') {
      labelReasons.push(
        `Near tie with option ${nearTie.option_ids.find((id) => id !== candidate?.option_id)} preserved: the less irreversible, lower-exposure option is preferred on recorded exposure evidence (Section 12.4).`,
      );
    } else if (nearTie.present) {
      labelReasons.push(
        `Near tie with option ${nearTie.option_ids.find((id) => id !== candidate?.option_id)} is preserved as an unresolved crux; it was not resolved by rounding.`,
      );
    }
  }

  return {
    verification_level: 'contract_tested',
    total_active_weight: totalActiveWeight,
    options: analyses,
    leading_option_id: leading?.option_id ?? null,
    recommended_option_id: recommended,
    label,
    label_reasons: labelReasons,
    prerequisites_needed: prerequisites,
    near_tie: nearTie,
    missing_seat_ids: [...missing],
    timed_out_seat_ids: [...timedOut],
  };
}
