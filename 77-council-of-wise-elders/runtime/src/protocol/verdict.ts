/**
 * Verdict services (directive Sections 11.5, 11.6, 12.8, 14.6, CWE-026
 * build steps 2 to 4).
 *
 * What lives here:
 * - Verdict assembly from a DecisionAnalysis plus card-derived content
 *   (reasons and dissent are drawn from the original cards, never
 *   invented and never written back over them).
 * - Publication validation against the EXACT revision hash: a report is
 *   publishable only when this validator has checked the exact content
 *   hash of that revision (Section 11.5). Validation of earlier rounds
 *   never substitutes: a verdict whose final attribution fails is
 *   blocked even when every earlier round passed (Section 14.6, T047).
 * - Resolution support counted from ratification cards bound to the
 *   exact draft-resolution semantic hash (Sections 11.6, 12.8).
 * - Client accept / reject / defer as a SEPARATE record. It never
 *   alters the historical recommendation (Section 11.5).
 * - Material-amendment assessment under Section 12.8: previous support
 *   never transfers to a materially amended plan, no fourth round is
 *   created, and nothing dispatches from an unratified altered plan.
 *
 * Pure services: no host, network, filesystem, clock, or random
 * dependency. Hashes use the one canonical serializer from CWE-003.
 */

import {
  canonicalHash,
  ContractError,
  isSha256Hex,
  isUtcTimestamp,
  isValidId,
  SEAT_IDS,
  validateVerdict,
  type ActionProposal,
  type AdvisorCard,
  type Amendment,
  type AmendmentMateriality,
  type CouncilCard,
  type DecisionBrief,
  type DraftResolution,
  type EvidenceStrength,
  type HardConstraintFinding,
  type RatificationCard,
  type RatificationStatus,
  type ResolutionSupport,
  type ScoredVerdict,
  type SeatId,
  type Verdict,
} from '../contracts/index.js';
import {
  analyzeDecision,
  type DecisionAnalysis,
  type DecisionInput,
} from '../scoring/decision.js';
import {
  deriveCriticalDomainApplicability,
  type CriticalDomainApplicability,
} from '../scoring/critical-domains.js';
import { isUnresolvedExplorationOption } from '../brief/exploration.js';

// ---------------------------------------------------------------------------
// Exact-hash helpers
// ---------------------------------------------------------------------------

/**
 * The content hash of a verdict: canonical hash of the verdict with
 * only its own content_sha256 field removed. This reproduces exactly
 * the digest the CWE-004 core computes at assembly time (it hashes the
 * base object before attaching the field), so a stored verdict can be
 * re-verified byte-for-byte at publication time.
 */
export function verdictContentHash(verdict: Verdict): string {
  const { content_sha256: _own, ...rest } = verdict as unknown as Record<
    string,
    unknown
  >;
  return canonicalHash(rest);
}

/**
 * The semantic hash of a draft resolution: canonical hash with only
 * its own semantic_sha256 field removed. Ratification cards bind to
 * exactly this digest (Section 12.8).
 */
export function draftResolutionSemanticHash(draft: DraftResolution): string {
  const { semantic_sha256: _own, ...rest } = draft as unknown as Record<
    string,
    unknown
  >;
  return canonicalHash(rest);
}

// ---------------------------------------------------------------------------
// Card-derived content (build step 3: concise reasons and dissent)
// ---------------------------------------------------------------------------

/**
 * Up to three main reasons, drawn in card order from the decisive
 * arguments of final-round advisor cards that preferred the
 * recommended option. Nothing is paraphrased into existence: the
 * strings are the seats' own recorded arguments.
 */
export function summarizeMainReasons(
  finalCards: readonly AdvisorCard[],
  recommendedOptionId: string | null,
): string[] {
  const reasons: string[] = [];
  if (recommendedOptionId === null) return reasons;
  for (const card of finalCards) {
    if (card.preferred_option_id !== recommendedOptionId) continue;
    for (const argument of card.decisive_arguments) {
      if (!reasons.includes(argument) && reasons.length < 3) {
        reasons.push(argument);
      }
    }
  }
  return reasons;
}

/**
 * The strongest dissent: the strongest objection of the card least
 * favorable to the recommended option (lowest recorded score for it).
 * An abstaining card is not treated as the strongest dissent.
 */
export function summarizeStrongestDissent(
  finalCards: readonly AdvisorCard[],
  recommendedOptionId: string | null,
): string | null {
  if (recommendedOptionId === null) return null;
  const dissenters = finalCards
    .filter((c) => c.preferred_option_id !== recommendedOptionId)
    .sort((a, b) => {
      const sa =
        a.option_scores.find((s) => s.option_id === recommendedOptionId)
          ?.score ?? 10;
      const sb =
        b.option_scores.find((s) => s.option_id === recommendedOptionId)
          ?.score ?? 10;
      return sa - sb;
    });
  return dissenters[0]?.strongest_objection ?? null;
}

/** Evidence strength aggregated from the final-round cards. */
export function aggregateEvidenceStrength(
  finalCards: readonly AdvisorCard[],
): EvidenceStrength {
  if (
    finalCards.length > 0 &&
    finalCards.every((c) => c.evidence_strength === 'high')
  ) {
    return 'high';
  }
  if (finalCards.some((c) => c.evidence_strength === 'low')) return 'low';
  return 'medium';
}

// ---------------------------------------------------------------------------
// Resolution support (Sections 11.6, 12.8)
// ---------------------------------------------------------------------------

/**
 * Weighted support counts for ONE exact resolution hash, counted from
 * ratification cards bound to that hash. Counts are never a probability
 * and are never inferred from option scores (Section 11.6).
 */
export function computeResolutionSupport(
  ratificationCards: readonly RatificationCard[],
  weights: Partial<Record<SeatId, number>>,
  resolutionSha256: string,
): ResolutionSupport {
  const counts: ResolutionSupport = {
    resolution_sha256: resolutionSha256,
    support: 0,
    conditional_support: 0,
    opposition: 0,
    abstention: 0,
  };
  for (const card of ratificationCards) {
    if (card.draft_resolution_sha256 !== resolutionSha256) continue;
    const weight = weights[card.seat_id];
    if (weight === undefined) {
      throw new ContractError(
        'SCHEMA_VALIDATION',
        `frozen relevance weight missing for seat ${card.seat_id}`,
        'weights',
      );
    }
    if (card.resolution_stance === 'support') counts.support += weight;
    else if (card.resolution_stance === 'conditional_support') {
      counts.conditional_support += weight;
    } else if (card.resolution_stance === 'oppose') counts.opposition += weight;
    else counts.abstention += weight;
  }
  return counts;
}

/** Seats whose ratification cards are bound to a DIFFERENT hash. */
export function findMisboundRatificationCards(
  ratificationCards: readonly RatificationCard[],
  resolutionSha256: string,
): SeatId[] {
  return ratificationCards
    .filter((c) => c.draft_resolution_sha256 !== resolutionSha256)
    .map((c) => c.seat_id);
}

// ---------------------------------------------------------------------------
// Verdict assembly
// ---------------------------------------------------------------------------

export interface ScoredVerdictBuildInput {
  analysis: DecisionAnalysis;
  session_id: string;
  verdict_revision: number;
  brief_sha256: string;
  /** The frozen weights, echoed into the verdict as active_weights. */
  weights: Partial<Record<SeatId, number>>;
  evidence_strength: EvidenceStrength;
  hard_constraint_findings: HardConstraintFinding[];
  main_reasons: string[];
  strongest_dissent: string | null;
  accepted_amendments: Amendment[];
  rejected_amendments: Amendment[];
  critical_unknowns: string[];
  prerequisites: string[];
  action_proposals: ActionProposal[];
  cheapest_informative_test: string | null;
  stop_criteria: string[];
  review_criteria: string[];
  resolution_support: ResolutionSupport | null;
  ratification_status: RatificationStatus;
}

/**
 * Assemble a scored verdict from a decision analysis. The content hash
 * is computed over the exact stored bytes (minus the hash field), and
 * the assembled verdict must pass the canonical schema before it is
 * returned carrying validation_status 'valid'.
 */
export function buildScoredVerdict(input: ScoredVerdictBuildInput): ScoredVerdict {
  const base = {
    schema_version: 'wise-elders.verdict/v1' as const,
    result_kind: 'scored' as const,
    session_id: input.session_id,
    verdict_revision: input.verdict_revision,
    recommended_option_id: input.analysis.recommended_option_id,
    label: input.analysis.label,
    option_scores: input.analysis.options.map((o) => ({
      option_id: o.option_id,
      score: o.score,
      display_score: o.display_score,
      weighted_sum: o.weighted_sum,
      denominator: o.denominator,
      coverage: o.coverage,
      spread: o.spread,
    })),
    active_weights: input.weights,
    evidence_strength: input.evidence_strength,
    hard_constraint_findings: input.hard_constraint_findings,
    main_reasons: input.main_reasons.slice(0, 3),
    strongest_dissent: input.strongest_dissent,
    accepted_amendments: input.accepted_amendments,
    rejected_amendments: input.rejected_amendments,
    critical_unknowns: input.critical_unknowns,
    prerequisites: input.prerequisites,
    action_proposals: input.action_proposals,
    cheapest_informative_test: input.cheapest_informative_test,
    stop_criteria: input.stop_criteria,
    review_criteria: input.review_criteria,
    resolution_support: input.resolution_support,
    validation_status: 'valid' as const,
    ratification_status: input.ratification_status,
    brief_sha256: input.brief_sha256,
  };
  const verdict = {
    ...base,
    content_sha256: canonicalHash(base),
  } as unknown as ScoredVerdict;
  const check = validateVerdict(verdict);
  if (!check.ok) {
    throw new ContractError(
      'SCHEMA_VALIDATION',
      `assembled verdict failed canonical validation: ${check.issues
        .map((i) => `${i.path}: ${i.message}`)
        .join('; ')}`,
      'verdict',
    );
  }
  return check.value as ScoredVerdict;
}

// ---------------------------------------------------------------------------
// Publication validation (build steps 2 and 4)
// ---------------------------------------------------------------------------

export interface PublicationCheck {
  name: string;
  status: 'pass' | 'fail' | 'not_run';
  detail: string;
}

export interface PublicationValidation {
  /** True only when every required check passed for THIS revision. */
  publishable: boolean;
  verdict_revision: number;
  /** The content hash claimed by the verdict. */
  content_sha256: string;
  /** The content hash recomputed by this validator. */
  computed_content_sha256: string;
  checks: PublicationCheck[];
}

export interface PublicationValidationInput {
  verdict: Verdict;
  /** The frozen brief the verdict claims to answer. */
  brief: DecisionBrief;
  /** Final-round cards (advisor round 2 and ratification), when available. */
  final_cards?: readonly CouncilCard[];
  /** The frozen draft resolution, when ratification is in scope. */
  draft_resolution?: DraftResolution;
  /** When true, missing final cards fail publication instead of not_run. */
  require_final_cards?: boolean;
}

// CWE-050 consolidation: the per-option applicability derivation lives
// once in scoring/critical-domains.ts (deriveCriticalDomainApplicability);
// this module previously carried a byte-identical private copy.

function scoringCardsOf(
  cards: readonly CouncilCard[],
): Array<AdvisorCard | RatificationCard> {
  const ratification = cards.filter(
    (c): c is RatificationCard => c.card_kind === 'ratification',
  );
  if (ratification.length > 0) return ratification;
  // No ratification pass: score from the LAST completed advisor round,
  // which for the four older modes is round 2 and for the council sizes
  // is whichever challenge pass the run stopped on (W77S-MODES).
  const advisors = cards.filter(
    (c): c is AdvisorCard => c.card_kind === 'advisor',
  );
  const lastRound = advisors.reduce((latest, card) => Math.max(latest, card.round), 0);
  return advisors.filter((card) => card.round === lastRound);
}

/** Labels that assert a recommendation. WAIT / INSUFFICIENT_EVIDENCE do not. */
const RECOMMENDATION_LABELS = new Set<ScoredVerdict['label']>([
  'GO',
  'GO_WITH_CONDITIONS',
  'RESHAPE',
  'DONT_DO_IT',
]);

/**
 * CTR-133: the publication boundary refuses a scored verdict built on a known
 * unresolved exploration candidate. The observed defect exported
 * GO_WITH_CONDITIONS recommending `option-explore` at score 7.4; that must be
 * impossible to publish again, including from an old brief or a stale engine.
 *
 * Genuine indecision stays distinct and publishable: a placeholder option with
 * a null score and a null recommendation under WAIT or INSUFFICIENT_EVIDENCE is
 * an honest "nothing can be scored yet", not a forged GO.
 */
export function assessExplorationExport(
  verdict: ScoredVerdict,
  brief: DecisionBrief,
): string[] {
  const placeholders = brief.options.filter(isUnresolvedExplorationOption);
  if (placeholders.length === 0) return [];
  const ids = new Set(placeholders.map((option) => option.id));
  const problems: string[] = [];

  for (const summary of verdict.option_scores) {
    if (ids.has(summary.option_id) && summary.score !== null) {
      problems.push(
        `option ${summary.option_id} is an unresolved exploration candidate and received score ${summary.score}; a placeholder is never a scored alternative`,
      );
    }
  }
  if (
    verdict.recommended_option_id !== null &&
    ids.has(verdict.recommended_option_id)
  ) {
    problems.push(
      `recommended option ${verdict.recommended_option_id} is an unresolved exploration candidate; no recommendation may be exported from it`,
    );
  }
  if (RECOMMENDATION_LABELS.has(verdict.label)) {
    problems.push(
      `label ${verdict.label} asserts a recommendation while the brief carries only an unresolved exploration candidate`,
    );
  }
  return problems;
}

/**
 * Validate a verdict for publication against its exact revision hash.
 * This is the Section 14.6 final validation: schema, arithmetic,
 * constraint, citation, attribution, and action-policy checks run
 * against the FINAL verdict revision, so an invalid final attribution
 * blocks release even when earlier rounds passed.
 */
export function validateVerdictForPublication(
  input: PublicationValidationInput,
): PublicationValidation {
  const { verdict, brief } = input;
  const checks: PublicationCheck[] = [];
  const computed = verdictContentHash(verdict);
  const push = (name: string, status: PublicationCheck['status'], detail: string) =>
    checks.push({ name, status, detail });

  const schemaCheck = validateVerdict(verdict);
  push(
    'schema_valid',
    schemaCheck.ok ? 'pass' : 'fail',
    schemaCheck.ok
      ? 'verdict passes the canonical CWE-003 schema'
      : schemaCheck.issues.map((i) => `${i.path}: ${i.message}`).join('; '),
  );

  push(
    'content_hash_exact',
    computed === verdict.content_sha256 ? 'pass' : 'fail',
    computed === verdict.content_sha256
      ? 'recomputed canonical hash matches the exact revision hash'
      : `recomputed ${computed} does not match claimed ${verdict.content_sha256}; the stored revision is not the revision that was validated`,
  );

  const briefHash = canonicalHash(brief);
  push(
    'brief_hash_bound',
    verdict.brief_sha256 === briefHash ? 'pass' : 'fail',
    verdict.brief_sha256 === briefHash
      ? 'verdict is bound to the supplied frozen brief'
      : 'verdict brief_sha256 does not match the canonical hash of the supplied brief',
  );

  push(
    'validation_status_valid',
    verdict.validation_status === 'valid' ? 'pass' : 'fail',
    `verdict validation_status is ${verdict.validation_status}`,
  );

  if (verdict.result_kind === 'consult') {
    push(
      'scoring_checks',
      'not_run',
      'consult results carry no options, scores, or ratification by contract (Section 11.5)',
    );
    const publishable = checks.every((c) => c.status !== 'fail');
    return {
      publishable,
      verdict_revision: verdict.verdict_revision,
      content_sha256: verdict.content_sha256,
      computed_content_sha256: computed,
      checks,
    };
  }

  // CTR-133: an unresolved exploration candidate is never exported as a valid
  // scored recommendation. This is a publication gate, not a relabel: schema
  // validation above still ran unchanged.
  const explorationProblems = assessExplorationExport(verdict, brief);
  push(
    'exploration_not_scored',
    explorationProblems.length === 0 ? 'pass' : 'fail',
    explorationProblems.length === 0
      ? 'no unresolved exploration candidate was scored or recommended'
      : explorationProblems.join('; '),
  );

  // Internal consistency of the stored summaries (always run).
  const internalProblems: string[] = [];
  for (const summary of verdict.option_scores) {
    const expectedDisplay =
      summary.score === null ? null : Math.round(summary.score * 10) / 10;
    if (summary.display_score !== expectedDisplay) {
      internalProblems.push(
        `option ${summary.option_id} display_score ${summary.display_score} does not equal one-decimal rounding of ${summary.score}`,
      );
    }
    if (summary.score === null && summary.denominator !== 0) {
      internalProblems.push(
        `option ${summary.option_id} has a null score with nonzero denominator ${summary.denominator}`,
      );
    }
    if (summary.score !== null && summary.denominator === 0) {
      internalProblems.push(
        `option ${summary.option_id} has a score with a zero denominator`,
      );
    }
  }
  push(
    'internal_consistency',
    internalProblems.length === 0 ? 'pass' : 'fail',
    internalProblems.length === 0
      ? 'display rounding, null-score, and denominator invariants hold'
      : internalProblems.join('; '),
  );

  const cards = input.final_cards;
  const cardsRequired = input.require_final_cards === true;
  if (!cards) {
    push(
      'scores_recomputed',
      cardsRequired ? 'fail' : 'not_run',
      cardsRequired
        ? 'final cards are required for publication and were not supplied'
        : 'final cards not supplied; arithmetic was not recomputed',
    );
    push(
      'attribution_verified',
      cardsRequired ? 'fail' : 'not_run',
      cardsRequired
        ? 'final cards are required for publication and were not supplied'
        : 'final cards not supplied; attribution was not re-verified',
    );
  } else {
    // Arithmetic recomputation from the final cards (Section 14.6).
    const scoringCards = scoringCardsOf(cards);
    const activeSeats = SEAT_IDS.filter(
      (seatId) => brief.relevance_weights[seatId] !== undefined,
    );
    const cardSeats = new Set(scoringCards.map((c) => c.seat_id));
    const decisionInput: DecisionInput = {
      options: brief.options,
      active_seat_ids: activeSeats,
      weights: brief.relevance_weights,
      scores: scoringCards.flatMap((card) =>
        card.option_scores.map((s) => ({
          option_id: s.option_id,
          seat_id: card.seat_id,
          score: s.score,
        })),
      ),
      missing_seat_ids: activeSeats.filter((s) => !cardSeats.has(s)),
      hard_constraints: verdict.hard_constraint_findings,
      critical_domains: brief.critical_domains,
      critical_domain_applicability: deriveCriticalDomainApplicability(brief),
    };
    let recomputeDetail = '';
    let recomputeOk = true;
    try {
      const recomputed = analyzeDecision(decisionInput);
      const mismatches: string[] = [];
      for (const summary of verdict.option_scores) {
        const mine = recomputed.options.find(
          (o) => o.option_id === summary.option_id,
        );
        if (!mine) {
          mismatches.push(`option ${summary.option_id} absent from recomputation`);
          continue;
        }
        if (
          mine.score !== summary.score ||
          mine.display_score !== summary.display_score ||
          mine.weighted_sum !== summary.weighted_sum ||
          mine.denominator !== summary.denominator ||
          mine.coverage !== summary.coverage ||
          mine.spread !== summary.spread
        ) {
          mismatches.push(
            `option ${summary.option_id} summary differs from recomputation (stored sum ${summary.weighted_sum}/${summary.denominator} score ${summary.score}; recomputed ${mine.weighted_sum}/${mine.denominator} score ${mine.score})`,
          );
        }
      }
      if (recomputed.label !== verdict.label) {
        mismatches.push(
          `label differs: stored ${verdict.label}, recomputed ${recomputed.label} (${recomputed.label_reasons.join(' ')})`,
        );
      }
      if (recomputed.recommended_option_id !== verdict.recommended_option_id) {
        mismatches.push(
          `recommended option differs: stored ${verdict.recommended_option_id}, recomputed ${recomputed.recommended_option_id} (recomputation runs without exposure records, so an exposure-based near-tie preference is not reproduced here)`,
        );
      }
      recomputeOk = mismatches.length === 0;
      recomputeDetail =
        mismatches.length === 0
          ? 'scores, coverage, spread, label, and recommendation recompute exactly from the final cards'
          : mismatches.join('; ');
    } catch (err) {
      recomputeOk = false;
      recomputeDetail = `recomputation failed: ${err instanceof Error ? err.message : String(err)}`;
    }
    push('scores_recomputed', recomputeOk ? 'pass' : 'fail', recomputeDetail);

    // Final attribution (T047): checked AFTER assembly, on the final
    // cards, so a quote that only survived an earlier round still fails.
    const manifestIds = new Set(brief.evidence_manifest.map((e) => e.evidence_id));
    const attributionProblems: string[] = [];
    for (const card of cards) {
      if (card.card_kind === 'consult') continue;
      for (const quote of 'quotes' in card ? card.quotes : []) {
        if (quote.verification_status !== 'verified') {
          attributionProblems.push(
            `seat ${card.seat_id} quote ${quote.quote_id} has status ${quote.verification_status}, not verified`,
          );
        }
        if (!manifestIds.has(quote.evidence_id)) {
          attributionProblems.push(
            `seat ${card.seat_id} quote ${quote.quote_id} cites evidence ${quote.evidence_id} outside the frozen manifest`,
          );
        }
      }
      for (const application of 'framework_applications' in card
        ? card.framework_applications
        : []) {
        for (const evidenceId of application.source_evidence_ids) {
          if (!manifestIds.has(evidenceId)) {
            attributionProblems.push(
              `seat ${card.seat_id} framework ${application.framework_id} cites source evidence ${evidenceId} outside the frozen manifest`,
            );
          }
        }
      }
    }
    push(
      'attribution_verified',
      attributionProblems.length === 0 ? 'pass' : 'fail',
      attributionProblems.length === 0
        ? 'every final-card quotation is verified and bound to frozen-manifest evidence'
        : attributionProblems.join('; '),
    );
  }

  // Ratification binding to the exact draft resolution hash.
  const draft = input.draft_resolution;
  if (verdict.resolution_support !== null && !draft) {
    push(
      'ratification_bound',
      'not_run',
      'verdict carries resolution support but no draft resolution was supplied to check its hash',
    );
  } else if (draft) {
    const semanticHash = draftResolutionSemanticHash(draft);
    const problems: string[] = [];
    if (draft.semantic_sha256 !== semanticHash) {
      problems.push(
        'the draft resolution semantic_sha256 does not match its recomputed semantic hash',
      );
    }
    if (
      verdict.resolution_support !== null &&
      verdict.resolution_support.resolution_sha256 !== semanticHash
    ) {
      problems.push(
        'verdict resolution support is keyed to a different resolution hash than the draft',
      );
    }
    if (cards) {
      const ratificationCards = cards.filter(
        (c): c is RatificationCard => c.card_kind === 'ratification',
      );
      const misbound = findMisboundRatificationCards(
        ratificationCards,
        semanticHash,
      );
      if (misbound.length > 0) {
        problems.push(
          `ratification cards bound to a different draft hash: ${misbound.join(', ')}`,
        );
      }
      if (verdict.resolution_support !== null && ratificationCards.length > 0) {
        const recomputedSupport = computeResolutionSupport(
          ratificationCards,
          brief.relevance_weights,
          semanticHash,
        );
        const stored = verdict.resolution_support;
        if (
          recomputedSupport.support !== stored.support ||
          recomputedSupport.conditional_support !== stored.conditional_support ||
          recomputedSupport.opposition !== stored.opposition ||
          recomputedSupport.abstention !== stored.abstention
        ) {
          problems.push(
            'stored resolution support counts differ from the weighted counts of the bound ratification cards',
          );
        }
      }
    }
    push(
      'ratification_bound',
      problems.length === 0 ? 'pass' : 'fail',
      problems.length === 0
        ? 'resolution support and ratification cards bind to the exact draft resolution hash'
        : problems.join('; '),
    );
  } else {
    push(
      'ratification_bound',
      'pass',
      'verdict carries no resolution support and no draft resolution is in scope',
    );
  }

  // Action boundaries: proposals stay advisory and revision-bound.
  const actionProblems: string[] = [];
  for (const proposal of verdict.action_proposals) {
    if (proposal.session_id !== verdict.session_id) {
      actionProblems.push(
        `action ${proposal.action_id} belongs to session ${proposal.session_id}, not ${verdict.session_id}`,
      );
    }
    if (proposal.verdict_revision !== verdict.verdict_revision) {
      actionProblems.push(
        `action ${proposal.action_id} is bound to verdict revision ${proposal.verdict_revision}, not ${verdict.verdict_revision}`,
      );
    }
    if (proposal.execution_authorization_required !== true) {
      actionProblems.push(
        `action ${proposal.action_id} does not require separate execution authorization`,
      );
    }
  }
  if (cards) {
    const conditionIds = new Set(
      cards.flatMap((c) =>
        c.card_kind === 'advisor' ? c.conditions.map((cond) => cond.id) : [],
      ),
    );
    for (const proposal of verdict.action_proposals) {
      for (const conditionId of proposal.source_condition_ids) {
        if (!conditionIds.has(conditionId)) {
          actionProblems.push(
            `action ${proposal.action_id} cites condition ${conditionId} that no final card carries`,
          );
        }
      }
    }
  }
  push(
    'action_boundaries',
    actionProblems.length === 0 ? 'pass' : 'fail',
    actionProblems.length === 0
      ? 'every action proposal is bound to this session and verdict revision and requires separate execution authorization'
      : actionProblems.join('; '),
  );

  const publishable = checks.every((c) => c.status !== 'fail');
  return {
    publishable,
    verdict_revision: verdict.verdict_revision,
    content_sha256: verdict.content_sha256,
    computed_content_sha256: computed,
    checks,
  };
}

// ---------------------------------------------------------------------------
// Client response: separate from the verdict, always (Section 11.5)
// ---------------------------------------------------------------------------

export type ClientVerdictResponse = 'accepted' | 'rejected' | 'deferred';

export interface ClientVerdictResponseRecord {
  schema_version: 'wise-elders.client-verdict-response/v1';
  session_id: string;
  verdict_revision: number;
  verdict_content_sha256: string;
  response: ClientVerdictResponse;
  responded_by_principal: string;
  responded_at: string;
  /** A client response never alters the historical recommendation. */
  alters_verdict: false;
}

/**
 * Record the client's accept / reject / defer decision about a verdict.
 * Returns a standalone record; the verdict object is neither mutated
 * nor re-hashed, and no part of the recommendation changes.
 */
export function recordClientVerdictResponse(
  verdict: ScoredVerdict,
  response: ClientVerdictResponse,
  respondedByPrincipal: string,
  respondedAtUtc: string,
): ClientVerdictResponseRecord {
  if (!isValidId(respondedByPrincipal)) {
    throw new ContractError(
      'INVALID_ID',
      'responded_by_principal must be an opaque principal ID',
      'responded_by_principal',
    );
  }
  if (!isUtcTimestamp(respondedAtUtc)) {
    throw new ContractError(
      'INVALID_TIMESTAMP',
      'responded_at must be a UTC ISO 8601 timestamp',
      'responded_at',
    );
  }
  if (!isSha256Hex(verdict.content_sha256)) {
    throw new ContractError(
      'INVALID_HASH',
      'verdict content_sha256 is not a SHA-256 hex digest',
      'content_sha256',
    );
  }
  return {
    schema_version: 'wise-elders.client-verdict-response/v1',
    session_id: verdict.session_id,
    verdict_revision: verdict.verdict_revision,
    verdict_content_sha256: verdict.content_sha256,
    response,
    responded_by_principal: respondedByPrincipal,
    responded_at: respondedAtUtc,
    alters_verdict: false,
  };
}

// ---------------------------------------------------------------------------
// Material amendments (Section 12.8)
// ---------------------------------------------------------------------------

/**
 * Target-path roots whose change is ALWAYS material under Section
 * 12.8: recommended option, required prerequisite, spending or
 * exposure limit, actor or owner authority, action scope, execution
 * permission, due-date commitment, or stop criterion.
 */
export const MATERIAL_AMENDMENT_TARGET_ROOTS: ReadonlySet<string> = new Set([
  'recommended_option_id',
  'prerequisites',
  'limits',
  'spending_limit',
  'exposure_limit',
  'budget_limit',
  'owner',
  'responsible_role',
  'assigned_agent_id',
  'department_id',
  'actions',
  'action_scope',
  'execution_permission',
  'execution_authorization_required',
  'due_at',
  'due_date',
  'stop_criteria',
]);

export interface AmendmentAssessment {
  materiality: AmendmentMateriality;
  /** Previous ratification support carries to the amended plan. */
  support_transfers: boolean;
  /** The chair may apply it as an editorial correction on the same hash. */
  may_apply_editorially: boolean;
  required_outcome:
    | 'editorial_same_hash'
    | 'publish_original_or_wait_unratified';
  /** Status the amended plan would carry if published unratified. */
  ratification_status_if_published: RatificationStatus | null;
  creates_fourth_round: false;
  dispatch_allowed: false;
  reasons: string[];
}

/**
 * Assess a proposed amendment to a frozen draft resolution. Pure
 * spelling, formatting, or citation-presentation changes are
 * nonmaterial only when they change no meaning; any change touching a
 * material root is material regardless of how it is labeled, and a
 * proposer-claimed material change is always honored as material.
 */
export function assessAmendment(input: {
  target_path: string;
  claimed_materiality: AmendmentMateriality;
}): AmendmentAssessment {
  const root = input.target_path.split(/[.[]/, 1)[0];
  const reasons: string[] = [];
  let material = false;
  if (MATERIAL_AMENDMENT_TARGET_ROOTS.has(root)) {
    material = true;
    reasons.push(
      `target ${input.target_path} changes ${root}, which Section 12.8 names material`,
    );
  }
  if (input.claimed_materiality === 'material') {
    material = true;
    reasons.push('the proposer classified the change as material');
  }
  if (!material) {
    reasons.push(
      `target ${input.target_path} is presentation-only (spelling, formatting, or citation presentation) and changes no meaning`,
    );
    return {
      materiality: 'nonmaterial',
      support_transfers: true,
      may_apply_editorially: true,
      required_outcome: 'editorial_same_hash',
      ratification_status_if_published: null,
      creates_fourth_round: false,
      dispatch_allowed: false,
      reasons,
    };
  }
  reasons.push(
    'previous support never transfers to a materially amended plan; publish the ratified original with the unresolved amendment, or publish a validated WAIT, RESHAPE, or INSUFFICIENT_EVIDENCE outcome marked material_change_unratified with the proposed alternative and a named next decision',
  );
  return {
    materiality: 'material',
    support_transfers: false,
    may_apply_editorially: false,
    required_outcome: 'publish_original_or_wait_unratified',
    ratification_status_if_published: 'material_change_unratified',
    creates_fourth_round: false,
    dispatch_allowed: false,
    reasons,
  };
}
