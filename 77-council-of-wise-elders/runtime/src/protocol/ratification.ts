/**
 * Draft resolution, ratification, consult completion, and the
 * completed-deliberation assembly (CWE-025; directive Sections 10,
 * 11.5 to 11.7, 12.8, 14.4, 14.5, and the Section 34 CWE-025 build
 * steps 3 and 4).
 *
 * What lives here:
 * - composeDraftResolution: the chair's draft as DETERMINISTIC CODE
 *   (Section 14.4: provisional scores are calculated in code; the
 *   chair's prose cannot change arithmetic). The recommended option
 *   comes from CWE-026's analyzeDecision over the committed Round 2
 *   cards, never from a second scorer. Actions are the Round 2
 *   conditions of seats that prefer the recommended option, duplicates
 *   merged without losing their source condition IDs; prerequisites
 *   are the frozen brief's unresolved critical-domain questions plus
 *   the analysis's named prerequisites; limits are the brief's hard
 *   constraints. The draft's semantic hash is CWE-026's
 *   draftResolutionSemanticHash, the exact digest ratification cards
 *   bind to (T046).
 * - evaluateQuickModeSkip: CWE-023 records the five quick-mode
 *   prerequisites verbatim at freeze with evaluated_by 'CWE-025';
 *   this is that evaluation, run against the run's actual cards and
 *   the composed draft (Section 10's gate, T022). Every prerequisite
 *   gets its own satisfied flag and detail; a tie, an invalid or
 *   missing card, a critical abstention, or a newly proposed material
 *   condition fails the gate, and no resolution-support votes are
 *   ever invented for a skipped round.
 * - RatificationRoundExecutor: the OperationExecutorPort for Round 3,
 *   composed with CWE-027's runner exactly as the opening and
 *   challenge executors compose. It composes the draft itself from
 *   the committed Round 2 record (deterministically, through
 *   composeDraftResolution), so planning, dispatch, and validation
 *   always bind the same draft the composition's resolution_drafted
 *   event names. Validation binds each card to the exact draft
 *   semantic hash (T046).
 * - ConsultExecutor: the one-seat consult operation (Sections 10,
 *   11.6, T023, T146). Its descriptor round is 0, the round key the
 *   CWE-006 store's findCard assigns consult cards (they carry no
 *   round field). A consult is not a vote: the executor produces one
 *   ConsultCard and the completion service below produces the
 *   discriminated ConsultResult, with no options, scores, or
 *   consensus anywhere in either.
 * - assembleDeliberationOutcome / assembleConsultOutcome: the
 *   completion services that hand a finished deliberation to CWE-026.
 *   Scoring flows ONLY through analyzeDecision + buildScoredVerdict;
 *   publication is checked through validateVerdictForPublication
 *   against the exact revision hash with the final cards required.
 *   Completeness follows Section 11.7 exactly: full mode needs nine
 *   valid cards or explicit abstentions in every required round and a
 *   missing seat is never disguised as an abstention (T021, T045);
 *   selected mode accounts for every selected seat by name (T023);
 *   quick mode completes without Round 3 only when the skip gate
 *   passes on the final proposed plan; three rounds is the ceiling,
 *   and a materially amended plan carries
 *   material_change_unratified with its old support counted only
 *   against the original hash (T046, T047 family, T048, T147).
 *
 * Amendment materiality is assessed with CWE-026's assessAmendment at
 * completion: a proposer labeling a material-root change
 * 'nonmaterial' does not make it so. Card VALIDATION deliberately
 * does not reject on claimed materiality; the assessment governs the
 * verdict's status instead (disclosed in the build report).
 */

import {
  canonicalHash,
  SEAT_ROSTER,
  validateCardAgainstBrief,
  validateVerdict,
  type AdvisorCard,
  type Amendment,
  type ConsultCard,
  type ConsultCardAuthor,
  type CouncilCard,
  type DecisionBrief,
  type DraftResolution,
  type HardConstraintFinding,
  type RatificationCard,
  type RatificationCardAuthor,
  type RatificationStatus,
  type ResolutionSupport,
  type ScoredVerdict,
  type SeatId,
  type SessionMode,
  type SessionSpec,
  type Verdict,
} from '../contracts/index.js';
import {
  AuthorizationError,
  type TrustedPrincipal,
} from '../authorization/index.js';
import {
  routeSnapshotFingerprint,
  type PinnedRouteSnapshot,
} from '../budgets/index.js';
import {
  ContextError,
  type AssembledContext,
  type MaterialCatalog,
  type RouteContextBudget,
} from '../context/index.js';
import type {
  ModelTransport,
  StoredSession,
  TransportResponse,
} from '../cli/host-ports.js';
import {
  CONSULT_SYSTEM as ENGINE_CONSULT_SYSTEM,
  RATIFICATION_SYSTEM,
  SEAT_FOCUS,
} from '../cli/engine.js';
import { authorPayloadFromText } from '../cli/card-text.js';
import {
  cardOutputContract,
  cardRequestSystem,
} from '../cli/card-contract.js';
import { WEB_TODAY_SYSTEM_RULE } from '../sources/elder-knowledge.js';
import {
  SimulatedCrashError,
  type OperationDispatchContext,
  type OperationDispatchResult,
  type OperationExecutorPort,
} from '../queue/runner.js';
import { validateCardSourceUse } from '../sources/packs.js';
import type { QuickModePolicyRecord } from '../intake/panel.js';
import {
  analyzeDecision,
  type DecisionAnalysis,
  type DecisionInput,
  type ProfessionalReviewOutcome,
} from '../scoring/index.js';
import {
  deriveCriticalDomainApplicability,
  type CriticalDomainApplicability,
} from '../scoring/critical-domains.js';

// CWE-050 consolidation: the applicability derivation lives once, in
// scoring/critical-domains.ts; re-exported here for compatibility with
// this module's earlier surface.
export { deriveCriticalDomainApplicability };
import {
  aggregateEvidenceStrength,
  assessAmendment,
  buildScoredVerdict,
  computeResolutionSupport,
  draftResolutionSemanticHash,
  findMisboundRatificationCards,
  summarizeMainReasons,
  summarizeStrongestDissent,
  validateVerdictForPublication,
  verdictContentHash,
  type PublicationValidation,
} from './verdict.js';
import {
  assembleSeatContext,
  assignedCruxesFor,
  authorOfCard,
  citationIssues,
  definiteDispatchRefusal,
  extractCruxes,
  payloadBriefView,
  sourceStatusOf,
  toSeatContextResult,
  translateTransportFailure,
  type LaterRoundDeps,
} from './challenge.js';

// --------------------------------------------------------- draft resolution

/** A composed draft plus the condition sources behind each action. */
export interface DraftComposition {
  readonly draft: DraftResolution;
  /**
   * Source condition IDs behind each draft action, parallel to
   * draft.actions: the conditions (from Round 2 cards of seats
   * preferring the recommended option) whose descriptions merged
   * into that action. No source is lost when duplicates merge
   * (Section 14.4).
   */
  readonly action_source_condition_ids: readonly (readonly string[])[];
  /** The CWE-026 analysis the recommendation came from. */
  readonly analysis: DecisionAnalysis;
}

export interface ComposeDraftInput {
  readonly brief: DecisionBrief;
  /** The session's panel, in spec order (Section 11.7 accounting). */
  readonly active_seat_ids: readonly SeatId[];
  readonly round2Cards: readonly AdvisorCard[];
  readonly hard_constraint_findings?: readonly HardConstraintFinding[];
  readonly professional_reviews?: readonly ProfessionalReviewOutcome[];
  /** Draft revision within the session attempt; 1 for the first draft. */
  readonly revision?: number;
}

/** DecisionInput over a card set, mirroring CWE-026's own derivation. */
export function decisionInputForCards(args: {
  brief: DecisionBrief;
  active_seat_ids: readonly SeatId[];
  cards: readonly (AdvisorCard | RatificationCard)[];
  hard_constraint_findings?: readonly HardConstraintFinding[];
  professional_reviews?: readonly ProfessionalReviewOutcome[];
}): DecisionInput {
  const cardSeats = new Set(args.cards.map((c) => c.seat_id));
  return {
    options: args.brief.options,
    active_seat_ids: args.active_seat_ids,
    weights: args.brief.relevance_weights,
    scores: args.cards.flatMap((card) =>
      card.option_scores.map((s) => ({
        option_id: s.option_id,
        seat_id: card.seat_id,
        score: s.score,
      })),
    ),
    missing_seat_ids: args.active_seat_ids.filter((s) => !cardSeats.has(s)),
    hard_constraints: args.hard_constraint_findings ?? [],
    critical_domains: args.brief.critical_domains,
    critical_domain_applicability: deriveCriticalDomainApplicability(args.brief),
    professional_reviews: args.professional_reviews ?? [],
  };
}

/**
 * Compose the chair's draft resolution from the committed Round 2
 * record (Section 14.4). Pure and deterministic: the same committed
 * cards, brief, and findings always compose the same draft and the
 * same semantic hash, at planning time, dispatch time, validation
 * time, and completion time.
 */
export function composeDraftResolution(input: ComposeDraftInput): DraftComposition {
  const analysis = analyzeDecision(
    decisionInputForCards({
      brief: input.brief,
      active_seat_ids: input.active_seat_ids,
      cards: input.round2Cards,
      hard_constraint_findings: input.hard_constraint_findings,
      professional_reviews: input.professional_reviews,
    }),
  );
  const recommended =
    analysis.recommended_option_id ??
    analysis.leading_option_id ??
    input.brief.options[0].id;

  const actions: string[] = [];
  const actionSources: string[][] = [];
  for (const card of input.round2Cards) {
    if (card.preferred_option_id !== recommended) continue;
    for (const condition of card.conditions) {
      const existing = actions.indexOf(condition.description);
      if (existing >= 0) {
        if (!actionSources[existing].includes(condition.id)) {
          actionSources[existing].push(condition.id);
        }
      } else if (actions.length < 5) {
        actions.push(condition.description);
        actionSources.push([condition.id]);
      }
    }
  }

  const prerequisites: string[] = [];
  for (const domain of input.brief.critical_domains) {
    if (domain.status === 'assessed') continue;
    for (const question of domain.unresolved_questions) {
      if (!prerequisites.includes(question)) prerequisites.push(question);
    }
  }
  for (const needed of analysis.prerequisites_needed) {
    if (!prerequisites.includes(needed)) prerequisites.push(needed);
  }

  const unsigned = {
    schema_version: 'wise-elders.draft-resolution/v1' as const,
    session_id: input.brief.session_id,
    brief_revision: input.brief.revision,
    revision: input.revision ?? 1,
    recommended_option_id: recommended,
    actions,
    prerequisites,
    limits: input.brief.constraints
      .filter((c) => c.hard)
      .map((c) => c.description),
    semantic_sha256: '',
  };
  const semantic = draftResolutionSemanticHash(unsigned as DraftResolution);
  return {
    draft: { ...unsigned, semantic_sha256: semantic },
    action_source_condition_ids: actionSources,
    analysis,
  };
}

// ------------------------------------------------------------ quick-mode gate

export interface QuickSkipPrerequisiteResult {
  readonly id: string;
  readonly text: string;
  readonly satisfied: boolean;
  readonly detail: string;
}

export interface QuickSkipEvaluation {
  readonly skip: boolean;
  /** The exact status a skipped Round 3 records (Section 10). */
  readonly ratification_status_when_skipped: 'not_run_by_quick_mode_policy';
  readonly prerequisites: readonly QuickSkipPrerequisiteResult[];
}

export interface QuickSkipInput {
  readonly policy: QuickModePolicyRecord;
  readonly brief: DecisionBrief;
  readonly round1Cards: readonly AdvisorCard[];
  readonly round2Cards: readonly AdvisorCard[];
  readonly draft: DraftResolution;
  /** Source condition IDs per draft action, when the composer supplied them. */
  readonly draft_action_source_condition_ids?: readonly (readonly string[])[];
  readonly hard_constraint_findings?: readonly HardConstraintFinding[];
}

/**
 * Evaluate CWE-023's frozen quick-mode policy record against the
 * run's actual cards and the final proposed plan (Section 10, T022).
 * The gate is evaluated per prerequisite and fails closed: anything
 * unproven is unsatisfied.
 */
export function evaluateQuickModeSkip(input: QuickSkipInput): QuickSkipEvaluation {
  const { policy, brief } = input;
  const panel = policy.seat_ids;
  const results = new Map<string, QuickSkipPrerequisiteResult>();
  const record = (id: string, satisfied: boolean, detail: string): void => {
    const source = policy.prerequisites.find((p) => p.id === id);
    results.set(id, { id, text: source?.text ?? id, satisfied, detail });
  };

  const round1BySeat = new Map(input.round1Cards.map((c) => [c.seat_id, c]));
  const round2BySeat = new Map(input.round2Cards.map((c) => [c.seat_id, c]));

  // 1. All four opening and challenge cards are valid. Committed cards
  // are valid by construction (the runner commits only validated
  // cards); presence for every named seat is the checkable fact.
  const missingCards: string[] = [];
  for (const seatId of panel) {
    if (!round1BySeat.has(seatId)) missingCards.push(`${seatId} opening`);
    if (!round2BySeat.has(seatId)) missingCards.push(`${seatId} challenge`);
  }
  record(
    'all_cards_valid',
    missingCards.length === 0,
    missingCards.length === 0
      ? 'all four seats hold committed opening and challenge cards'
      : `missing committed cards: ${missingCards.join(', ')}; a missing or invalid card can never satisfy the skip gate`,
  );

  // 2. All four seats have the same highest-ranked eligible option.
  const failedOptions = new Set(
    (input.hard_constraint_findings ?? [])
      .filter((f) => f.result === 'fail')
      .map((f) => f.option_id),
  );
  const tops = new Map<SeatId, string | null>();
  const topProblems: string[] = [];
  for (const seatId of panel) {
    const card = round2BySeat.get(seatId);
    if (!card) {
      tops.set(seatId, null);
      continue;
    }
    const eligible = card.option_scores.filter(
      (s) => s.score !== null && !failedOptions.has(s.option_id),
    );
    if (eligible.length === 0) {
      tops.set(seatId, null);
      topProblems.push(`${seatId} scored no eligible option (an abstention is not a ranking)`);
      continue;
    }
    const best = Math.max(...eligible.map((s) => s.score as number));
    const winners = eligible.filter((s) => s.score === best);
    if (winners.length > 1) {
      tops.set(seatId, null);
      topProblems.push(
        `${seatId} ties ${winners.map((w) => w.option_id).join(' and ')} at ${best}; a tie cannot satisfy the skip gate`,
      );
      continue;
    }
    tops.set(seatId, winners[0].option_id);
    if (card.preferred_option_id !== winners[0].option_id) {
      topProblems.push(
        `${seatId} prefers ${card.preferred_option_id ?? 'no option'} but ranks ${winners[0].option_id} highest; the panel has not converged on one option`,
      );
    }
  }
  const distinctTops = new Set([...tops.values()].filter((t) => t !== null));
  const commonTop =
    distinctTops.size === 1 && topProblems.length === 0
      ? ([...distinctTops][0] as string)
      : null;
  if (commonTop !== null && input.draft.recommended_option_id !== commonTop) {
    topProblems.push(
      `the draft recommends ${input.draft.recommended_option_id}, not the panel's common highest-ranked option ${commonTop}`,
    );
  }
  record(
    'same_highest_ranked_option',
    commonTop !== null && topProblems.length === 0,
    commonTop !== null && topProblems.length === 0
      ? `all four seats rank option ${commonTop} highest among eligible options, and the draft recommends it`
      : topProblems.join('; ') || 'the four seats do not share one highest-ranked eligible option',
  );

  // 3. The Round 2 score spread on that option is at most 3.
  if (commonTop === null) {
    record(
      'spread_at_most_3',
      false,
      'no common highest-ranked option exists, so no spread can satisfy the gate',
    );
  } else {
    const scores = panel.map(
      (seatId) =>
        round2BySeat.get(seatId)?.option_scores.find((s) => s.option_id === commonTop)
          ?.score ?? null,
    );
    if (scores.some((s) => s === null)) {
      record(
        'spread_at_most_3',
        false,
        `a seat abstained on option ${commonTop}; a critical abstention cannot satisfy the skip gate`,
      );
    } else {
      const values = scores as number[];
      const spread = Math.max(...values) - Math.min(...values);
      record(
        'spread_at_most_3',
        spread <= 3,
        `Round 2 spread on option ${commonTop} is ${spread} (at most 3 required)`,
      );
    }
  }

  // 4. No critical fact or constraint remains unresolved.
  const unresolvedDomains = brief.critical_domains.filter(
    (d) => d.status !== 'assessed',
  );
  const unknownFindings = (input.hard_constraint_findings ?? []).filter(
    (f) => f.result === 'unknown',
  );
  const criticalAbstentions: string[] = [];
  // The reference option is the panel's common top when one exists,
  // else the draft's recommendation: a required reviewer's abstention
  // on the option the plan would advance leaves that critical
  // assessment unresolved either way (Section 10 names a critical
  // abstention as gate-failing in its own right).
  const referenceOption = commonTop ?? input.draft.recommended_option_id;
  {
    for (const domain of brief.critical_domains) {
      if (domain.required_seat_id === null) continue;
      if (!panel.includes(domain.required_seat_id)) continue;
      const score = round2BySeat
        .get(domain.required_seat_id)
        ?.option_scores.find((s) => s.option_id === referenceOption)?.score;
      if (score === null || score === undefined) {
        criticalAbstentions.push(
          `${domain.required_seat_id} (required reviewer for ${domain.domain}) abstained on option ${referenceOption}`,
        );
      }
    }
  }
  const unresolvedProblems = [
    ...unresolvedDomains.map(
      (d) => `critical domain ${d.domain} is ${d.status}, not assessed`,
    ),
    ...unknownFindings.map(
      (f) => `hard constraint ${f.constraint_id} on option ${f.option_id} is unresolved (unknown)`,
    ),
    ...criticalAbstentions,
  ];
  record(
    'no_unresolved_critical_fact_or_constraint',
    unresolvedProblems.length === 0,
    unresolvedProblems.length === 0
      ? 'every frozen critical domain is assessed, no hard constraint is unknown, and no required reviewer abstained on the leading option'
      : unresolvedProblems.join('; '),
  );

  // 5. The final plan introduces no material condition or amendment
  // the seats have not assessed. Every draft action must trace to a
  // Round 2 condition recorded by a seat that prefers the recommended
  // option, and every blocking condition the four seats recorded must
  // survive into the draft (as an action or a prerequisite): a dropped
  // blocking condition is a material change the seats have not
  // assessed. No amendments exist before ratification, so the
  // amendment half of this prerequisite is vacuous at gate time.
  const planProblems: string[] = [];
  const conditionById = new Map<string, { seat_id: SeatId; description: string; blocking: boolean }>();
  for (const card of input.round2Cards) {
    for (const condition of card.conditions) {
      conditionById.set(condition.id, {
        seat_id: card.seat_id,
        description: condition.description,
        blocking: condition.blocking,
      });
    }
  }
  input.draft.actions.forEach((action, index) => {
    const sourceIds = input.draft_action_source_condition_ids?.[index];
    if (sourceIds && sourceIds.length > 0) {
      for (const conditionId of sourceIds) {
        const source = conditionById.get(conditionId);
        if (!source) {
          planProblems.push(
            `draft action "${action}" traces to condition ${conditionId}, which no committed Round 2 card records`,
          );
        } else if (
          round2BySeat.get(source.seat_id)?.preferred_option_id !==
          input.draft.recommended_option_id
        ) {
          planProblems.push(
            `draft action "${action}" comes from ${source.seat_id}, which does not prefer the recommended option ${input.draft.recommended_option_id}`,
          );
        }
      }
      return;
    }
    const traced = [...conditionById.values()].some(
      (c) =>
        c.description === action &&
        round2BySeat.get(c.seat_id)?.preferred_option_id ===
          input.draft.recommended_option_id,
    );
    if (!traced) {
      planProblems.push(
        `draft action "${action}" does not trace to any Round 2 condition from a seat preferring the recommended option`,
      );
    }
  });
  const draftTexts = new Set([...input.draft.actions, ...input.draft.prerequisites]);
  for (const card of input.round2Cards) {
    if (!panel.includes(card.seat_id)) continue;
    for (const condition of card.conditions) {
      if (condition.blocking && !draftTexts.has(condition.description)) {
        planProblems.push(
          `blocking condition from ${card.seat_id} ("${condition.description}") is missing from the draft; dropping it is a material change the seats have not assessed`,
        );
      }
    }
  }
  record(
    'no_unassessed_material_condition',
    planProblems.length === 0,
    planProblems.length === 0
      ? 'every draft action traces to an assessed Round 2 condition and no blocking condition was dropped'
      : planProblems.join('; '),
  );

  const prerequisites = policy.prerequisites.map(
    (p) =>
      results.get(p.id) ?? {
        id: p.id,
        text: p.text,
        satisfied: false,
        detail: 'prerequisite was not evaluated',
      },
  );
  return {
    skip: prerequisites.every((p) => p.satisfied),
    ratification_status_when_skipped: policy.ratification_status_when_skipped,
    prerequisites,
  };
}

// ------------------------------------------------------- ratification round

/**
 * The Section 14.5 logical prompt contract for ratification. CWE-050
 * consolidation: the single source is RATIFICATION_SYSTEM in
 * cli/engine.ts; this name is kept as the protocol surface.
 */
export const RATIFICATION_ROUND_SYSTEM = `${RATIFICATION_SYSTEM}\n${WEB_TODAY_SYSTEM_RULE}`;

/** Identity kind tag for a Round 3 ratification input manifest. */
export const RATIFICATION_INPUT_KIND = 'wise-elders.ratification-input/v1';

export interface RatificationInputIdentity {
  readonly session_id: string;
  readonly brief_revision: number;
  readonly brief_sha256: string;
  readonly seat_id: SeatId;
  readonly pack_version: string;
  readonly context_sha256: string;
  readonly route_fingerprint: string;
  /** The exact draft this seat is asked to judge (Section 12.8). */
  readonly draft_resolution_sha256: string;
}

export function ratificationInputManifestSha256(
  identity: RatificationInputIdentity,
): string {
  return canonicalHash({
    kind: RATIFICATION_INPUT_KIND,
    session_id: identity.session_id,
    brief_revision: identity.brief_revision,
    brief_sha256: identity.brief_sha256,
    seat_id: identity.seat_id,
    round: 3,
    pack_version: identity.pack_version,
    context_sha256: identity.context_sha256,
    route_fingerprint: identity.route_fingerprint,
    draft_resolution_sha256: identity.draft_resolution_sha256,
  });
}

export interface RatificationSeatPlan {
  readonly seat_id: SeatId;
  readonly pack_version: string;
  readonly context_sha256: string;
  readonly route_fingerprint: string;
  readonly input_manifest_sha256: string;
  readonly draft_resolution_sha256: string;
  readonly item_evidence_ids: readonly string[];
}

export type RatificationPlanResult =
  | { readonly status: 'planned'; readonly plan: RatificationSeatPlan }
  | {
      readonly status: 'context_too_small';
      readonly readiness: 'CONTEXT_TOO_SMALL';
      readonly minimum_required_bytes: number;
      readonly available_bytes: number;
      readonly supported_lower_context_modes: readonly SessionMode[];
    };

export interface RatificationRoundPlan {
  readonly draft: DraftResolution;
  readonly composition: DraftComposition;
  readonly plans: ReadonlyMap<SeatId, RatificationPlanResult>;
}

/** Extra composition inputs ratification needs beyond the shared deps. */
export interface RatificationRoundDeps extends LaterRoundDeps {
  /**
   * Hard-constraint findings recorded for the session (deterministic
   * checkers, seats, or qualified professionals, Section 12.3). Absent:
   * no findings, which the analysis treats as no confirmed failures.
   */
  readonly loadHardConstraintFindings?: (
    session: StoredSession,
  ) => readonly HardConstraintFinding[];
  /** Qualified professional review outcomes, when any exist. */
  readonly loadProfessionalReviews?: (
    session: StoredSession,
  ) => readonly ProfessionalReviewOutcome[];
}

interface PreparedRatification {
  readonly plan: RatificationSeatPlan;
  readonly context: AssembledContext;
  readonly composition: DraftComposition;
  readonly round2Cards: readonly AdvisorCard[];
}

type PrepareRatificationResult =
  | { readonly status: 'prepared'; readonly seat: PreparedRatification }
  | Extract<RatificationPlanResult, { status: 'context_too_small' }>;

export class RatificationRoundExecutor implements OperationExecutorPort {
  constructor(private readonly deps: RatificationRoundDeps) {}

  // ------------------------------------------------------------ planning

  /** Compose the draft from the committed Round 2 record. */
  composeDraft(session: StoredSession): DraftComposition {
    return composeDraftResolution({
      brief: session.brief,
      active_seat_ids: session.spec.seat_ids,
      round2Cards: this.round2Cards(session),
      hard_constraint_findings: this.deps.loadHardConstraintFindings?.(session) ?? [],
      professional_reviews: this.deps.loadProfessionalReviews?.(session) ?? [],
    });
  }

  planSeat(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
    seatId: SeatId,
  ): RatificationPlanResult {
    const prepared = this.prepareSeat(session, snapshot, seatId, null);
    if (prepared.status === 'context_too_small') return prepared;
    return { status: 'planned', plan: prepared.seat.plan };
  }

  /** Plan the whole ratification round: one draft, one plan per seat. */
  planRatificationRound(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
  ): RatificationRoundPlan {
    const composition = this.composeDraft(session);
    const plans = new Map<SeatId, RatificationPlanResult>();
    for (const seatId of session.spec.seat_ids) {
      plans.set(seatId, this.planSeat(session, snapshot, seatId));
    }
    return { draft: composition.draft, composition, plans };
  }

  // ------------------------------------------------------------ dispatch

  async dispatch(
    ctx: OperationDispatchContext,
  ): Promise<OperationDispatchResult> {
    const { session, claim } = ctx;
    const seatId = claim.seat_id;
    if (seatId === null) {
      throw definiteDispatchRefusal(
        'ratification dispatch refused: the claimed operation has no seat',
      );
    }
    if (claim.descriptor.round !== 3 || claim.descriptor.kind !== 'provider_request') {
      throw definiteDispatchRefusal(
        `ratification dispatch refused: operation is round ${claim.descriptor.round} kind ${claim.descriptor.kind}, not a round 3 provider request`,
      );
    }
    if (session.spec.mode === 'consult') {
      throw definiteDispatchRefusal(
        'ratification dispatch refused: a consult session has no ratification round',
      );
    }

    let prepared: PrepareRatificationResult;
    try {
      prepared = this.prepareSeat(session, claim.route_snapshot, seatId, claim);
    } catch (error) {
      if (error instanceof ContextError || error instanceof AuthorizationError) {
        throw definiteDispatchRefusal(
          `ratification dispatch refused before any provider call: ${error.name} ${'code' in error ? String((error as { code: unknown }).code) : ''}: ${error.message}`,
        );
      }
      throw error;
    }
    if (prepared.status === 'context_too_small') {
      throw definiteDispatchRefusal(
        `ratification dispatch refused before any provider call: CONTEXT_TOO_SMALL for seat ${seatId}: minimum ${prepared.minimum_required_bytes} canonical bytes, available ${prepared.available_bytes}`,
      );
    }
    const { plan, context, composition, round2Cards } = prepared.seat;
    const draft = composition.draft;

    if (plan.input_manifest_sha256 !== claim.job.input_sha256) {
      throw definiteDispatchRefusal(
        `ratification dispatch refused before any provider call: input drift for seat ${seatId}: planned manifest ${plan.input_manifest_sha256} does not match the enqueued operation input ${claim.job.input_sha256}`,
      );
    }

    const transport = await this.deps.resolveTransport(claim.route_snapshot, session);
    if (!transport) {
      throw definiteDispatchRefusal(
        `ratification dispatch refused before any provider call: no transport is composed for the pinned route ${claim.route_snapshot.routeId}`,
      );
    }

    const pack = this.deps.loadSeatBriefing
      ? await this.deps.loadSeatBriefing(seatId, session)
      : null;

    const round1Cards = this.deps
      .loadCommittedCards(session)
      .filter((c): c is AdvisorCard => c.card_kind === 'advisor' && c.round === 1);
    const cruxes = extractCruxes(round1Cards, session.brief, session.spec.seat_ids);
    const ownRound2 = round2Cards.find((c) => c.seat_id === seatId) ?? null;
    const briefView = payloadBriefView(context);

    const system = cardRequestSystem(
      RATIFICATION_ROUND_SYSTEM,
      'ratification',
      null,
      ctx.attempt_kind === 'output_repair' ? ctx.repair_issues : [],
    );

    let response: TransportResponse;
    try {
      response = await transport.generate({
        signal: ctx.signal,
        purpose: 'ratification',
        session_id: session.spec.session_id,
        seat_id: seatId,
        round: 3,
        route_id: claim.route_snapshot.routeId,
        model_policy: session.spec.model_policy,
        system,
        input: {
          context: { ...context, brief: briefView },
          brief: briefView,
          seat_focus: SEAT_FOCUS[seatId],
          seat_display_name:
            SEAT_ROSTER.find((s) => s.seat_id === seatId)?.display_name ?? seatId,
          pack_briefing: pack?.briefing_text ?? null,
          input_manifest_sha256: plan.input_manifest_sha256,
          pack_version: plan.pack_version,
          // The exact draft under judgment, in full and by hash.
          draft_resolution: draft,
          own_challenge_card: ownRound2 ? authorOfCard(ownRound2) : null,
          // The challenges this seat was responsible for (Section 14.5:
          // each seat sees the draft, the relevant challenges, and the
          // frozen evidence).
          relevant_cruxes: assignedCruxesFor(cruxes, seatId),
          output_contract: cardOutputContract('ratification', null),
        },
      });
    } catch (error) {
      if (error instanceof SimulatedCrashError) throw error;
      throw translateTransportFailure(error);
    }

    // CWE-048 item 13: parse through the shared tolerant card parser
    // (the same parser RP-046-3 adopted on the managed path). A direct
    // JSON parse keeps its historical semantics; when it fails or
    // yields a non-object, a balanced JSON object is located inside
    // prose-wrapped or fenced output and validated unchanged. A
    // response with no recoverable object still yields the empty
    // author payload, so validation drives the same bounded repair.
    const { author, parse_error } = authorPayloadFromText(response.text);

    const priced = this.deps.priceActual
      ? this.deps.priceActual({ response, snapshot: claim.route_snapshot })
      : null;

    return {
      author,
      parse_error,
      provider_request_id: response.provider_request_id,
      actual_minor: priced ?? claim.descriptor.estimate_minor,
      input_tokens: response.usage.input_tokens,
      output_tokens: response.usage.output_tokens,
      source_status: sourceStatusOf(context),
    };
  }

  // ---------------------------------------------------------- validation

  /**
   * Deep validation of a stamped Round 3 card: identity, the input
   * manifest echo, the frozen brief, and above all the exact
   * draft-resolution hash binding (T046). Amendment authorship is
   * checked (a seat proposes only its own amendments); amendment
   * materiality is NOT judged here (completion assesses it through
   * CWE-026's assessAmendment, Section 12.8). Accepted condition IDs
   * must name conditions the committed Round 2 record actually
   * carries.
   */
  validateCard(ctx: OperationDispatchContext, card: CouncilCard): string[] {
    const { session, claim } = ctx;
    const issues: string[] = [];
    const seatId = claim.seat_id;
    if (card.card_kind !== 'ratification') {
      return [`card_kind: expected a ratification card, got ${card.card_kind}`];
    }
    const author: RatificationCardAuthor = card;
    if (author.round !== 3) {
      issues.push(`round: ratification cards are round 3, got ${author.round}`);
    }
    if (seatId === null || author.seat_id !== seatId) {
      issues.push(
        `seat_id: card claims seat ${author.seat_id}, expected ${seatId ?? 'none'}`,
      );
    }
    if (author.session_id !== session.spec.session_id) {
      issues.push('session_id: card does not belong to this session');
    }
    const packVersion = claim.descriptor.pack_version ?? session.spec.source_pack_version;
    if (author.pack_version !== packVersion) {
      issues.push(
        `pack_version: card claims ${author.pack_version}, expected ${packVersion}`,
      );
    }
    const against = validateCardAgainstBrief(author, session.brief);
    if (!against.ok) {
      issues.push(...against.issues.map((i) => `${i.path}: ${i.message}`));
    }
    for (const amendment of author.amendments) {
      if (amendment.proposing_seat_id !== author.seat_id) {
        issues.push(
          `amendments: amendment ${amendment.amendment_id} is proposed by ${amendment.proposing_seat_id}, not by the card's seat ${author.seat_id}`,
        );
      }
    }

    if (seatId !== null) {
      let prepared: PrepareRatificationResult | null = null;
      try {
        prepared = this.prepareSeat(session, claim.route_snapshot, seatId, claim);
      } catch (error) {
        issues.push(
          `input_manifest_sha256: the ratification inputs could not be reassembled for validation (${error instanceof Error ? error.message : 'unknown error'})`,
        );
      }
      if (prepared !== null) {
        if (prepared.status === 'context_too_small') {
          issues.push(
            'input_manifest_sha256: the ratification inputs no longer fit the pinned route context budget',
          );
        } else {
          const { plan, composition, round2Cards } = prepared.seat;
          if (author.input_manifest_sha256 !== plan.input_manifest_sha256) {
            issues.push(
              'input_manifest_sha256: card does not echo the ratification input manifest for this operation',
            );
          }
          if (author.input_manifest_sha256 !== claim.job.input_sha256) {
            issues.push(
              'input_manifest_sha256: card does not match the enqueued operation input',
            );
          }
          if (author.draft_resolution_sha256 !== composition.draft.semantic_sha256) {
            issues.push(
              `draft_resolution_sha256: card is bound to ${author.draft_resolution_sha256}, not to the exact draft resolution hash ${composition.draft.semantic_sha256}; support never transfers to a different resolution`,
            );
          }
          const knownConditionIds = new Set(
            round2Cards.flatMap((c) => c.conditions.map((cond) => cond.id)),
          );
          for (const conditionId of author.accepted_condition_ids) {
            if (!knownConditionIds.has(conditionId)) {
              issues.push(
                `accepted_condition_ids: condition ${conditionId} is not in the committed Round 2 record`,
              );
            }
          }
        }
      }
    }
    return issues;
  }

  // ------------------------------------------------------------- helpers

  private round2Cards(session: StoredSession): AdvisorCard[] {
    return this.deps
      .loadCommittedCards(session)
      .filter((c): c is AdvisorCard => c.card_kind === 'advisor' && c.round === 2);
  }

  private prepareSeat(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
    seatId: SeatId,
    claim: { descriptor: { pack_version?: string | null } } | null,
  ): PrepareRatificationResult {
    const assembled = toSeatContextResult(
      assembleSeatContext({
        deps: this.deps,
        session,
        snapshot,
        seatId,
        operation: 'round_3_ratification',
        systemText: RATIFICATION_ROUND_SYSTEM,
      }),
    );
    if (assembled.status === 'context_too_small') return assembled;
    const context = assembled.context;
    const round2Cards = this.round2Cards(session);
    const composition = this.composeDraft(session);
    const packVersion =
      claim?.descriptor.pack_version ?? session.spec.source_pack_version;
    const identity: RatificationInputIdentity = {
      session_id: session.spec.session_id,
      brief_revision: session.brief.revision,
      brief_sha256: session.spec.brief_sha256,
      seat_id: seatId,
      pack_version: packVersion,
      context_sha256: context.content_sha256,
      route_fingerprint: routeSnapshotFingerprint(snapshot),
      draft_resolution_sha256: composition.draft.semantic_sha256,
    };
    return {
      status: 'prepared',
      seat: {
        plan: {
          seat_id: seatId,
          pack_version: packVersion,
          context_sha256: context.content_sha256,
          route_fingerprint: identity.route_fingerprint,
          input_manifest_sha256: ratificationInputManifestSha256(identity),
          draft_resolution_sha256: composition.draft.semantic_sha256,
          item_evidence_ids: context.items.map((item) => item.evidence_id),
        },
        context,
        composition,
        round2Cards,
      },
    };
  }
}

// ------------------------------------------------------------------- consult

/**
 * The Section 14 consult prompt contract. CWE-050 consolidation: the
 * single source is CONSULT_SYSTEM in cli/engine.ts; re-exported under
 * the same name for this module's existing surface.
 */
export const CONSULT_SYSTEM = `${ENGINE_CONSULT_SYSTEM}\n${WEB_TODAY_SYSTEM_RULE}`;

/** Identity kind tag for a consult input manifest. */
export const CONSULT_INPUT_KIND = 'wise-elders.consult-input/v1';

/**
 * The descriptor and store round key for consult operations: consult
 * cards carry no round field, and the CWE-006 store's findCard maps
 * them to round 0 (the same key CWE-004's engine used).
 */
export const CONSULT_DESCRIPTOR_ROUND = 0;

export interface ConsultInputIdentity {
  readonly session_id: string;
  readonly brief_revision: number;
  readonly brief_sha256: string;
  readonly seat_id: SeatId;
  readonly pack_version: string;
  readonly context_sha256: string;
  readonly route_fingerprint: string;
}

export function consultInputManifestSha256(identity: ConsultInputIdentity): string {
  return canonicalHash({
    kind: CONSULT_INPUT_KIND,
    session_id: identity.session_id,
    brief_revision: identity.brief_revision,
    brief_sha256: identity.brief_sha256,
    seat_id: identity.seat_id,
    round: null,
    pack_version: identity.pack_version,
    context_sha256: identity.context_sha256,
    route_fingerprint: identity.route_fingerprint,
  });
}

export interface ConsultPlan {
  readonly seat_id: SeatId;
  readonly pack_version: string;
  readonly context_sha256: string;
  readonly route_fingerprint: string;
  readonly input_manifest_sha256: string;
  readonly item_evidence_ids: readonly string[];
}

export type ConsultPlanResult =
  | { readonly status: 'planned'; readonly plan: ConsultPlan }
  | {
      readonly status: 'context_too_small';
      readonly readiness: 'CONTEXT_TOO_SMALL';
      readonly minimum_required_bytes: number;
      readonly available_bytes: number;
      readonly supported_lower_context_modes: readonly SessionMode[];
    };

interface PreparedConsult {
  readonly plan: ConsultPlan;
  readonly context: AssembledContext;
}

type PrepareConsultResult =
  | { readonly status: 'prepared'; readonly seat: PreparedConsult }
  | Extract<ConsultPlanResult, { status: 'context_too_small' }>;

export class ConsultExecutor implements OperationExecutorPort {
  constructor(private readonly deps: LaterRoundDeps) {}

  planConsult(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
  ): ConsultPlanResult {
    const seatId = session.spec.seat_ids[0];
    if (session.spec.mode !== 'consult' || session.spec.seat_ids.length !== 1 || !seatId) {
      throw new ContextError(
        'CONTEXT_SESSION_UNAVAILABLE',
        'A consult plan requires a consult session with exactly one seat.',
      );
    }
    const prepared = this.prepare(session, snapshot, seatId, null);
    if (prepared.status === 'context_too_small') return prepared;
    return { status: 'planned', plan: prepared.seat.plan };
  }

  async dispatch(
    ctx: OperationDispatchContext,
  ): Promise<OperationDispatchResult> {
    const { session, claim } = ctx;
    const seatId = claim.seat_id;
    if (seatId === null) {
      throw definiteDispatchRefusal('consult dispatch refused: the claimed operation has no seat');
    }
    if (
      claim.descriptor.round !== CONSULT_DESCRIPTOR_ROUND ||
      claim.descriptor.kind !== 'provider_request'
    ) {
      throw definiteDispatchRefusal(
        `consult dispatch refused: operation is round ${claim.descriptor.round} kind ${claim.descriptor.kind}, not a consult provider request`,
      );
    }
    if (session.spec.mode !== 'consult') {
      throw definiteDispatchRefusal(
        'consult dispatch refused: the session is not a consult session',
      );
    }
    if (session.spec.seat_ids.length !== 1 || session.spec.seat_ids[0] !== seatId) {
      throw definiteDispatchRefusal(
        'consult dispatch refused: the claimed seat is not the consult session\'s one seat',
      );
    }

    let prepared: PrepareConsultResult;
    try {
      prepared = this.prepare(session, claim.route_snapshot, seatId, claim);
    } catch (error) {
      if (error instanceof ContextError || error instanceof AuthorizationError) {
        throw definiteDispatchRefusal(
          `consult dispatch refused before any provider call: ${error.name} ${'code' in error ? String((error as { code: unknown }).code) : ''}: ${error.message}`,
        );
      }
      throw error;
    }
    if (prepared.status === 'context_too_small') {
      throw definiteDispatchRefusal(
        `consult dispatch refused before any provider call: CONTEXT_TOO_SMALL for seat ${seatId}: minimum ${prepared.minimum_required_bytes} canonical bytes, available ${prepared.available_bytes}`,
      );
    }
    const { plan, context } = prepared.seat;

    if (plan.input_manifest_sha256 !== claim.job.input_sha256) {
      throw definiteDispatchRefusal(
        `consult dispatch refused before any provider call: input drift for seat ${seatId}: planned manifest ${plan.input_manifest_sha256} does not match the enqueued operation input ${claim.job.input_sha256}`,
      );
    }

    const transport = await this.deps.resolveTransport(claim.route_snapshot, session);
    if (!transport) {
      throw definiteDispatchRefusal(
        `consult dispatch refused before any provider call: no transport is composed for the pinned route ${claim.route_snapshot.routeId}`,
      );
    }

    const pack = this.deps.loadSeatBriefing
      ? await this.deps.loadSeatBriefing(seatId, session)
      : null;
    const briefView = payloadBriefView(context);

    const system = cardRequestSystem(
      CONSULT_SYSTEM,
      'consult',
      null,
      ctx.attempt_kind === 'output_repair' ? ctx.repair_issues : [],
    );

    let response: TransportResponse;
    try {
      response = await transport.generate({
        signal: ctx.signal,
        purpose: 'consult',
        session_id: session.spec.session_id,
        seat_id: seatId,
        round: null,
        route_id: claim.route_snapshot.routeId,
        model_policy: session.spec.model_policy,
        system,
        input: {
          context: { ...context, brief: briefView },
          brief: briefView,
          seat_focus: SEAT_FOCUS[seatId],
          seat_display_name:
            SEAT_ROSTER.find((s) => s.seat_id === seatId)?.display_name ?? seatId,
          pack_briefing: pack?.briefing_text ?? null,
          input_manifest_sha256: plan.input_manifest_sha256,
          pack_version: plan.pack_version,
          output_contract: cardOutputContract('consult', null),
        },
      });
    } catch (error) {
      if (error instanceof SimulatedCrashError) throw error;
      throw translateTransportFailure(error);
    }

    // CWE-048 item 13: parse through the shared tolerant card parser
    // (the same parser RP-046-3 adopted on the managed path). A direct
    // JSON parse keeps its historical semantics; when it fails or
    // yields a non-object, a balanced JSON object is located inside
    // prose-wrapped or fenced output and validated unchanged. A
    // response with no recoverable object still yields the empty
    // author payload, so validation drives the same bounded repair.
    const { author, parse_error } = authorPayloadFromText(response.text);

    const priced = this.deps.priceActual
      ? this.deps.priceActual({ response, snapshot: claim.route_snapshot })
      : null;

    return {
      author,
      parse_error,
      provider_request_id: response.provider_request_id,
      actual_minor: priced ?? claim.descriptor.estimate_minor,
      input_tokens: response.usage.input_tokens,
      output_tokens: response.usage.output_tokens,
      source_status: sourceStatusOf(context),
    };
  }

  validateCard(ctx: OperationDispatchContext, card: CouncilCard): string[] {
    const { session, claim } = ctx;
    const issues: string[] = [];
    const seatId = claim.seat_id;
    if (card.card_kind !== 'consult') {
      return [`card_kind: expected a consult card, got ${card.card_kind}`];
    }
    const author: ConsultCardAuthor = card;
    if (seatId === null || author.seat_id !== seatId) {
      issues.push(
        `seat_id: card claims seat ${author.seat_id}, expected ${seatId ?? 'none'}`,
      );
    }
    if (author.session_id !== session.spec.session_id) {
      issues.push('session_id: card does not belong to this session');
    }
    const packVersion = claim.descriptor.pack_version ?? session.spec.source_pack_version;
    if (author.pack_version !== packVersion) {
      issues.push(
        `pack_version: card claims ${author.pack_version}, expected ${packVersion}`,
      );
    }
    const against = validateCardAgainstBrief(author, session.brief);
    if (!against.ok) {
      issues.push(...against.issues.map((i) => `${i.path}: ${i.message}`));
    }
    // A consult card carries no options, scores, or consensus by
    // contract; the canonical schema already forbids extra fields,
    // and the checks below bind its evidence to the seat's own
    // assembled context and the frozen manifest.
    if (seatId !== null) {
      let prepared: PrepareConsultResult | null = null;
      try {
        prepared = this.prepare(session, claim.route_snapshot, seatId, claim);
      } catch (error) {
        issues.push(
          `input_manifest_sha256: the consult inputs could not be reassembled for validation (${error instanceof Error ? error.message : 'unknown error'})`,
        );
      }
      if (prepared !== null) {
        if (prepared.status === 'context_too_small') {
          issues.push(
            'input_manifest_sha256: the consult inputs no longer fit the pinned route context budget',
          );
        } else {
          const { plan, context } = prepared.seat;
          if (author.input_manifest_sha256 !== plan.input_manifest_sha256) {
            issues.push(
              'input_manifest_sha256: card does not echo the consult input manifest for this operation',
            );
          }
          if (author.input_manifest_sha256 !== claim.job.input_sha256) {
            issues.push(
              'input_manifest_sha256: card does not match the enqueued operation input',
            );
          }
          const briefIds = new Set(
            session.brief.evidence_manifest.map((e) => e.evidence_id),
          );
          for (const evidenceId of author.evidence_ids) {
            if (!briefIds.has(evidenceId)) {
              issues.push(
                `evidence_ids: evidence ${evidenceId} is not in the frozen evidence manifest`,
              );
            }
          }
          issues.push(
            ...citationIssues({
              context,
              brief: session.brief,
              framework_applications: author.framework_applications,
              quotes: [],
            }),
          );
        }
      }
    }
    return issues;
  }

  private prepare(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
    seatId: SeatId,
    claim: { descriptor: { pack_version?: string | null } } | null,
  ): PrepareConsultResult {
    const assembled = toSeatContextResult(
      assembleSeatContext({
        deps: this.deps,
        session,
        snapshot,
        seatId,
        operation: 'consult',
        systemText: CONSULT_SYSTEM,
      }),
    );
    if (assembled.status === 'context_too_small') return assembled;
    const context = assembled.context;
    const packVersion =
      claim?.descriptor.pack_version ?? session.spec.source_pack_version;
    const identity: ConsultInputIdentity = {
      session_id: session.spec.session_id,
      brief_revision: session.brief.revision,
      brief_sha256: session.spec.brief_sha256,
      seat_id: seatId,
      pack_version: packVersion,
      context_sha256: context.content_sha256,
      route_fingerprint: routeSnapshotFingerprint(snapshot),
    };
    return {
      status: 'prepared',
      seat: {
        plan: {
          seat_id: seatId,
          pack_version: packVersion,
          context_sha256: context.content_sha256,
          route_fingerprint: identity.route_fingerprint,
          input_manifest_sha256: consultInputManifestSha256(identity),
          item_evidence_ids: context.items.map((item) => item.evidence_id),
        },
        context,
      },
    };
  }
}

// ---------------------------------------------------------------- completion

/** Per-seat accounting for one round (Section 11.7 completeness). */
export type SeatRoundAccounting = 'card' | 'explicit_abstention' | 'missing';

export interface DeliberationAccounting {
  readonly round1: Readonly<Partial<Record<SeatId, SeatRoundAccounting>>>;
  readonly round2: Readonly<Partial<Record<SeatId, SeatRoundAccounting>>>;
  readonly round3: Readonly<Partial<Record<SeatId, SeatRoundAccounting>>>;
}

export interface DeliberationOutcomeComplete {
  readonly status: 'complete';
  readonly mode: SessionMode;
  /** The panel exactly as frozen in the spec; a subset names itself (T023). */
  readonly panel_seat_ids: readonly SeatId[];
  readonly verdict: ScoredVerdict;
  readonly publication: PublicationValidation;
  readonly analysis: DecisionAnalysis;
  readonly draft: DraftResolution;
  readonly resolution_support: ResolutionSupport | null;
  readonly ratification_status: RatificationStatus;
  /** Present when quick mode completed by the Section 10 gate. */
  readonly quick_skip: QuickSkipEvaluation | null;
  readonly accounting: DeliberationAccounting;
}

export interface DeliberationOutcomeIncomplete {
  readonly status: 'incomplete';
  readonly mode: SessionMode;
  readonly panel_seat_ids: readonly SeatId[];
  /** Every unaccounted seat, by round: the visible partial record. */
  readonly missing: readonly { readonly round: 1 | 2 | 3; readonly seat_id: SeatId }[];
  readonly detail: string;
  readonly accounting: DeliberationAccounting;
}

export type DeliberationOutcome =
  | DeliberationOutcomeComplete
  | DeliberationOutcomeIncomplete;

export interface AssembleDeliberationInput {
  readonly spec: SessionSpec;
  readonly brief: DecisionBrief;
  readonly cards: readonly CouncilCard[];
  /** The composed draft, when the caller already holds it. */
  readonly draft_composition?: DraftComposition;
  /** CWE-023's frozen quick-mode policy record (quick sessions). */
  readonly quick_policy?: QuickModePolicyRecord | null;
  readonly hard_constraint_findings?: readonly HardConstraintFinding[];
  readonly professional_reviews?: readonly ProfessionalReviewOutcome[];
  readonly verdict_revision?: number;
}

function accountRound(
  panel: readonly SeatId[],
  cards: readonly (AdvisorCard | RatificationCard)[],
): Partial<Record<SeatId, SeatRoundAccounting>> {
  const bySeat = new Map(cards.map((c) => [c.seat_id, c]));
  const out: Partial<Record<SeatId, SeatRoundAccounting>> = {};
  for (const seatId of panel) {
    const card = bySeat.get(seatId);
    if (!card) {
      out[seatId] = 'missing';
    } else if (
      card.card_kind === 'ratification'
        ? card.resolution_stance === 'abstain'
        : card.stance === 'abstain'
    ) {
      out[seatId] = 'explicit_abstention';
    } else {
      out[seatId] = 'card';
    }
  }
  return out;
}

function missingList(
  accounting: DeliberationAccounting,
  rounds: readonly (1 | 2 | 3)[],
): { round: 1 | 2 | 3; seat_id: SeatId }[] {
  const out: { round: 1 | 2 | 3; seat_id: SeatId }[] = [];
  const byRound = { 1: accounting.round1, 2: accounting.round2, 3: accounting.round3 };
  for (const round of rounds) {
    for (const [seatId, state] of Object.entries(byRound[round])) {
      if (state === 'missing') out.push({ round, seat_id: seatId as SeatId });
    }
  }
  return out;
}

/**
 * Assemble the completed deliberation for a scored mode and validate
 * it for publication through CWE-026 (Sections 11.7, 14.6). Returns a
 * discriminated outcome: 'complete' carries the validated verdict;
 * 'incomplete' carries the exact missing record and never a verdict.
 * No fourth round exists anywhere in this surface (T048): unresolved
 * disagreement is published honestly through the analysis label, or
 * the outcome is incomplete.
 */
export function assembleDeliberationOutcome(
  input: AssembleDeliberationInput,
): DeliberationOutcome {
  const { spec, brief } = input;
  const panel = spec.seat_ids;
  const mode = spec.mode;
  if (mode === 'consult') {
    throw new Error(
      'assembleDeliberationOutcome does not serve consult sessions; use assembleConsultOutcome (a consult has no council verdict).',
    );
  }
  const round1 = input.cards.filter(
    (c): c is AdvisorCard => c.card_kind === 'advisor' && c.round === 1,
  );
  const round2 = input.cards.filter(
    (c): c is AdvisorCard => c.card_kind === 'advisor' && c.round === 2,
  );
  const round3 = input.cards.filter(
    (c): c is RatificationCard => c.card_kind === 'ratification',
  );
  const accounting: DeliberationAccounting = {
    round1: accountRound(panel, round1),
    round2: accountRound(panel, round2),
    round3: accountRound(panel, round3),
  };
  const incomplete = (detail: string, rounds: readonly (1 | 2 | 3)[]): DeliberationOutcomeIncomplete => ({
    status: 'incomplete',
    mode,
    panel_seat_ids: [...panel],
    missing: missingList(accounting, rounds),
    detail,
    accounting,
  });

  // Full mode (Section 11.7, T021): nine valid cards or explicit
  // abstentions in EVERY required round. A missing seat blocks
  // completion in place; the session is never converted to a smaller
  // mode and no verdict is assembled from a partial panel.
  if (mode === 'full') {
    const missing = missingList(accounting, [1, 2, 3]);
    if (missing.length > 0) {
      return incomplete(
        `full mode keeps all nine seats: ${missing.map((m) => `${m.seat_id} round ${m.round}`).join(', ')} missing; the result is a visible partial record, not a smaller council`,
        [1, 2, 3],
      );
    }
  }

  // The draft: composed deterministically from the Round 2 record
  // when the caller did not supply the composition.
  const composition =
    input.draft_composition ??
    composeDraftResolution({
      brief,
      active_seat_ids: panel,
      round2Cards: round2,
      hard_constraint_findings: input.hard_constraint_findings,
      professional_reviews: input.professional_reviews,
    });
  const draft = composition.draft;

  // Ratification binding (T046): a committed ratification card bound
  // to a different draft hash is a protocol breach, not a discount.
  if (round3.length > 0) {
    const misbound = findMisboundRatificationCards(round3, draft.semantic_sha256);
    if (misbound.length > 0) {
      return {
        status: 'incomplete',
        mode,
        panel_seat_ids: [...panel],
        missing: [],
        detail: `ratification cards from ${misbound.join(', ')} are bound to a different draft resolution hash than ${draft.semantic_sha256}; their support cannot be counted for this draft and the breach is not silently dropped`,
        accounting,
      };
    }
  }

  // Quick mode without Round 3 stands or falls on the Section 10 gate
  // evaluated on the final proposed plan (T022).
  let quickSkip: QuickSkipEvaluation | null = null;
  let ratificationStatus: RatificationStatus;
  if (round3.length === 0) {
    if (mode === 'quick') {
      if (!input.quick_policy) {
        return incomplete(
          'quick mode reached completion without Round 3 and without the frozen quick-mode policy record; the skip gate cannot be evaluated',
          [3],
        );
      }
      quickSkip = evaluateQuickModeSkip({
        policy: input.quick_policy,
        brief,
        round1Cards: round1,
        round2Cards: round2,
        draft,
        draft_action_source_condition_ids: composition.action_source_condition_ids,
        hard_constraint_findings: input.hard_constraint_findings,
      });
      if (!quickSkip.skip) {
        const failed = quickSkip.prerequisites
          .filter((p) => !p.satisfied)
          .map((p) => `${p.id}: ${p.detail}`)
          .join('; ');
        return {
          status: 'incomplete',
          mode,
          panel_seat_ids: [...panel],
          missing: missingList(accounting, [1, 2]),
          detail: `the quick-mode ratification-skip gate fails (${failed}) and Round 3 did not run; the honest outcome is an explicitly partial or WAIT result from the composition, never a fabricated ratification`,
          accounting,
        };
      }
      ratificationStatus = quickSkip.ratification_status_when_skipped;
    } else {
      // Selected mode's required path includes Round 3 (Section 11.7).
      return incomplete(
        `${mode} mode requires the ratification round; no ratification cards are committed`,
        [3],
      );
    }
  } else {
    ratificationStatus = 'ratified';
  }

  // Amendments (Section 12.8): adopted and rejected are recorded with
  // their reasons as the cards carry them; a proposed amendment that
  // is material under CWE-026's assessment marks the plan
  // material_change_unratified, and previous support is counted only
  // against the original hash (T147).
  const acceptedAmendments: Amendment[] = [];
  const rejectedAmendments: Amendment[] = [];
  let materialProposed = false;
  for (const card of round3) {
    for (const amendment of card.amendments) {
      const effective = assessAmendment({
        target_path: amendment.target_path,
        claimed_materiality: amendment.materiality,
      });
      if (amendment.disposition === 'accepted') acceptedAmendments.push(amendment);
      else if (amendment.disposition === 'rejected') rejectedAmendments.push(amendment);
      else if (effective.materiality === 'material') materialProposed = true;
    }
  }
  if (round3.length > 0 && materialProposed) {
    ratificationStatus = 'material_change_unratified';
  }

  const resolutionSupport =
    round3.length > 0
      ? computeResolutionSupport(round3, brief.relevance_weights, draft.semantic_sha256)
      : null;

  // Final scoring cards: ratification cards when Round 3 ran, else
  // the Round 2 cards (the same precedence CWE-026's publication
  // validator recomputes with).
  const finalCards: (AdvisorCard | RatificationCard)[] =
    round3.length > 0 ? round3 : round2;
  const analysis = analyzeDecision(
    decisionInputForCards({
      brief,
      active_seat_ids: panel,
      cards: finalCards,
      hard_constraint_findings: input.hard_constraint_findings,
      professional_reviews: input.professional_reviews,
    }),
  );

  const verdictRevision = input.verdict_revision ?? 1;
  const recommended = analysis.recommended_option_id;
  const prerequisites: string[] = [...analysis.prerequisites_needed];
  for (const card of round2) {
    for (const condition of card.conditions) {
      if (condition.blocking && !prerequisites.includes(condition.description)) {
        prerequisites.push(condition.description);
      }
    }
  }
  const proposals = draft.actions.map((action, index) => ({
    action_id: `act-${spec.session_id}-${index + 1}`,
    session_id: spec.session_id,
    verdict_revision: verdictRevision,
    title: action,
    description: action,
    rationale:
      'Proposed in the council draft resolution. Requires separate action-plan approval before any task is created; a council vote is not an execution credential.',
    source_condition_ids: [...(composition.action_source_condition_ids[index] ?? [])],
    department_id: null,
    assigned_agent_id: null,
    sop_id: null,
    persona_id: null,
    acceptance_criteria: [] as string[],
    budget_limit: null,
    due_at: null,
    depends_on_action_ids: [] as string[],
    risk_class: 'medium' as const,
    execution_authorization_required: true as const,
  }));
  const boundedTest = brief.options.find(
    (o) => o.kind === 'bounded_test' && o.id !== recommended,
  );

  const verdict = buildScoredVerdict({
    analysis,
    session_id: spec.session_id,
    verdict_revision: verdictRevision,
    brief_sha256: spec.brief_sha256,
    weights: Object.fromEntries(
      panel.map((seatId) => [seatId, brief.relevance_weights[seatId] ?? 1]),
    ),
    evidence_strength: aggregateEvidenceStrength(round2),
    hard_constraint_findings: [...(input.hard_constraint_findings ?? [])],
    main_reasons: summarizeMainReasons(round2, recommended),
    strongest_dissent: summarizeStrongestDissent(round2, recommended),
    accepted_amendments: acceptedAmendments,
    rejected_amendments: rejectedAmendments,
    critical_unknowns: [...new Set(round2.flatMap((c) => c.critical_unknowns))].slice(0, 10),
    prerequisites,
    action_proposals: proposals,
    cheapest_informative_test: boundedTest
      ? `Run the bounded test in option ${boundedTest.id} (${boundedTest.label}) to gather the missing evidence.`
      : null,
    stop_criteria: brief.constraints
      .filter((c) => c.hard)
      .map((c) => `Stop if this hard constraint is violated: ${c.description}`),
    review_criteria: brief.unknowns.map((u) => `Resolve the recorded unknown: ${u.statement}`),
    resolution_support: resolutionSupport,
    ratification_status: ratificationStatus,
  });

  const publication = validateVerdictForPublication({
    verdict,
    brief,
    final_cards: [...round2, ...round3],
    draft_resolution: draft,
    require_final_cards: true,
  });

  return {
    status: 'complete',
    mode,
    panel_seat_ids: [...panel],
    verdict,
    publication,
    analysis,
    draft,
    resolution_support: resolutionSupport,
    ratification_status: ratificationStatus,
    quick_skip: quickSkip,
    accounting,
  };
}

export interface ConsultOutcomeComplete {
  readonly status: 'complete';
  readonly mode: 'consult';
  readonly panel_seat_ids: readonly SeatId[];
  /** The discriminated consult result: no scores, no vote (T023). */
  readonly result: Extract<Verdict, { result_kind: 'consult' }>;
  readonly publication: PublicationValidation;
}

export interface ConsultOutcomeIncomplete {
  readonly status: 'incomplete';
  readonly mode: 'consult';
  readonly panel_seat_ids: readonly SeatId[];
  readonly detail: string;
}

export type ConsultOutcome = ConsultOutcomeComplete | ConsultOutcomeIncomplete;

/**
 * Assemble a consult result from the one committed ConsultCard
 * (Sections 11.5, 11.7, T146): PREPARING -> CONSULTING -> VERIFYING ->
 * COMPLETED with a single valid card and no council scoring anywhere.
 */
export function assembleConsultOutcome(input: {
  spec: SessionSpec;
  brief: DecisionBrief;
  cards: readonly CouncilCard[];
  verdict_revision?: number;
}): ConsultOutcome {
  const { spec, brief } = input;
  if (spec.mode !== 'consult') {
    throw new Error('assembleConsultOutcome serves consult sessions only.');
  }
  const card = input.cards.find((c): c is ConsultCard => c.card_kind === 'consult');
  if (!card) {
    return {
      status: 'incomplete',
      mode: 'consult',
      panel_seat_ids: [...spec.seat_ids],
      detail: 'no validated consult card is committed; the consult has no result yet',
    };
  }
  const base = {
    schema_version: 'wise-elders.verdict/v1' as const,
    result_kind: 'consult' as const,
    session_id: spec.session_id,
    verdict_revision: input.verdict_revision ?? 1,
    consult_card: card,
    next_step: card.next_step,
    validation_status: 'valid' as const,
    brief_sha256: spec.brief_sha256,
  };
  const result = { ...base, content_sha256: canonicalHash(base) } as Verdict;
  const check = validateVerdict(result);
  if (!check.ok) {
    throw new Error(
      `assembled consult result failed canonical validation: ${check.issues.map((i) => `${i.path}: ${i.message}`).join('; ')}`,
    );
  }
  const publication = validateVerdictForPublication({
    verdict: result,
    brief,
    final_cards: [card],
  });
  return {
    status: 'complete',
    mode: 'consult',
    panel_seat_ids: [...spec.seat_ids],
    result: result as Extract<Verdict, { result_kind: 'consult' }>,
    publication,
  };
}

// Re-exported so consumers of the completion surface see the exact
// verdict-hash helpers CWE-026 owns (no second implementation here).
export { draftResolutionSemanticHash, verdictContentHash };
export type { PublicationValidation };
export type { TrustedPrincipal, MaterialCatalog, RouteContextBudget, ModelTransport, PinnedRouteSnapshot };
