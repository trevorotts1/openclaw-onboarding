/**
 * Focused challenge round: crux extraction, challenge assignment, and
 * the Round 2 executor (CWE-025; directive Sections 10, 11.7, 14.3,
 * 14.5, and the Section 34 CWE-025 build steps 1 and 2).
 *
 * What lives here:
 * - extractCruxes: the chair's crux identification as DETERMINISTIC
 *   CODE over valid committed opening cards (the same architectural
 *   choice CWE-004's in-process engine made: "deterministic crux
 *   extraction"; the chair is a model ROLE for prose, but crux
 *   identification from recorded scores, preferences, and blocking
 *   conditions is arithmetic and record-keeping, and code cannot
 *   fabricate a dispute). Up to three decision-changing cruxes, each
 *   typed fact | numbers | values | execution, with competing claims
 *   quoted from the cards' own recorded values, responsible seats,
 *   needed evidence, and a resolution test (Section 14.3). Structural
 *   generators: a score spread of at least 4 on one option (numbers);
 *   a blocking condition attached to a contended leading option
 *   (execution); a split in preferred options (values); and, when
 *   every seat prefers the same option, the labeled adversarial test
 *   of the strongest neglected alternative (origin
 *   unanimity_stress_test, adversarial_test true; it is never recorded
 *   as genuine dissent, T039). No deterministic signal in the frozen
 *   card contract separates a factual dispute from a numeric one (the
 *   same recorded spread is a numbers crux), so this build types no
 *   crux 'fact' rather than inventing one; see the CWE-025 build
 *   report's discrepancy register.
 * - ChallengeRoundExecutor: the OperationExecutorPort CWE-027's
 *   durable runner dispatches through for Round 2 seat operations,
 *   composed exactly as CWE-024's opening executor composes (the
 *   runner owns admission through CWE-049, the one CWE-028 budget
 *   ledger, leases, fencing, and the bounded follow-on policy; this
 *   executor owns per-dispatch context assembly, input identity, the
 *   provider call on the pinned route, and deep card validation; it
 *   commits nothing itself).
 * - The planner surface (planSeat / planChallengeRound) deriving the
 *   exact input identity an enqueueing composition (CWE-050) uses as
 *   each job's input_sha256. EVERY panel seat is planned, including
 *   seats with no targeted challenge: a required seat returns a fresh
 *   Round 2 card even without one (T149), and a Round 1 card can never
 *   satisfy a Round 2 job because the Round 2 input identity binds
 *   the committed Round 1 card set and the crux set.
 *
 * Round 2's context posture is DELIBERATELY DIFFERENT from Round 1
 * (Section 14.3): independence is over. Each seat's provider payload
 * carries its own assembled evidence context (still narrowed to its
 * own source material through CWE-022's assembler), its own committed
 * Round 1 card, and ONLY the peer arguments necessary to answer its
 * assigned challenges: for each assigned crux, the competing claims
 * and the other responsible seats' recorded arguments about that
 * crux. The entire transcript is never expanded into every seat's
 * context by default, and a decisive opposing fact is never hidden
 * from an affected seat: the crux payload carries the opposing seat's
 * own decisive arguments and strongest objection verbatim. Two things
 * stay hidden in every round: the client preference (the brief view
 * in the payload omits private_preference_ref entirely, in Round 2
 * and Round 3 as in Round 1; CWE-022's assembler strips it only for
 * round_1_opening, so these executors strip it at the payload
 * boundary and bind the assembler's unstripped content hash in the
 * input identity, disclosed for CWE-050) and any seat's private
 * material (source items are per-seat; no seat's payload contains
 * another seat's source items).
 *
 * Failure honesty is inherited unchanged: transport failures keep
 * CWE-009's honesty flags through translation into the runner's
 * TransportDispatchError; an invalid card returns as an author payload
 * so the runner's validation drives the one bounded repair;
 * pre-dispatch refusals throw a definite TransportDispatchError with
 * actual_minor 0 before any provider call; nothing here fabricates a
 * card, an abstention, or a changed position.
 */

import {
  canonicalHash,
  isCouncilSize,
  MAX_ADVISOR_ROUND,
  SEAT_IDS,
  SEAT_ROSTER,
  validateCardAgainstBrief,
  type AdvisorCard,
  type AdvisorCardAuthor,
  type CouncilCard,
  type DecisionBrief,
  type SeatId,
  type SessionMode,
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
  assembleContext,
  ContextError,
  type AssembledContext,
  type ContextAssemblyResult,
  type MaterialCatalog,
  type RouteContextBudget,
} from '../context/index.js';
import type {
  ModelTransport,
  StoredSession,
  TransportResponse,
} from '../cli/host-ports.js';
import { CHALLENGE_SYSTEM, SEAT_FOCUS } from '../cli/engine.js';
import { authorPayloadFromText } from '../cli/card-text.js';
import {
  cardOutputContract,
  cardRequestSystem,
  cardSystemBytes,
} from '../cli/card-contract.js';
import { WEB_TODAY_SYSTEM_RULE } from '../sources/elder-knowledge.js';
import {
  SimulatedCrashError,
  TransportDispatchError,
  type OperationDispatchContext,
  type OperationDispatchResult,
  type OperationExecutorPort,
} from '../queue/runner.js';
import { isTransportError } from '../providers/errors.js';
import { validateCardSourceUse } from '../sources/packs.js';

// ------------------------------------------------------------ shared glue

/**
 * A pre-dispatch refusal: no provider call was made, so the runner
 * records a definite failure settled at actual_minor 0. Shared by the
 * CWE-025 executors (challenge, ratification, consult); CWE-024's
 * opening executor carries its own copy from its own build, and
 * consolidating the three is CWE-050 integration work.
 */
export function definiteDispatchRefusal(message: string): TransportDispatchError {
  return new TransportDispatchError(message, { actual_minor: 0 });
}

/** Translate a CWE-009 transport failure, preserving its honesty flags. */
export function translateTransportFailure(error: unknown): TransportDispatchError {
  if (isTransportError(error)) {
    const label = `transport ${error.code}: ${error.message}`;
    if (error.unknownCompletion) {
      return new TransportDispatchError(label, { unknownCompletion: true });
    }
    if (error.retryable) {
      return new TransportDispatchError(label, { retryable: true });
    }
    return new TransportDispatchError(label, { actual_minor: 0 });
  }
  const flagged = error as {
    retryable?: unknown;
    unknownCompletion?: unknown;
    message?: unknown;
  } | null;
  if (
    flagged !== null &&
    typeof flagged === 'object' &&
    (typeof flagged.retryable === 'boolean' ||
      typeof flagged.unknownCompletion === 'boolean')
  ) {
    const label = `transport failure: ${typeof flagged.message === 'string' ? flagged.message : 'no message'}`;
    if (flagged.unknownCompletion === true) {
      return new TransportDispatchError(label, { unknownCompletion: true });
    }
    if (flagged.retryable === true) {
      return new TransportDispatchError(label, { retryable: true });
    }
    return new TransportDispatchError(label, { actual_minor: 0 });
  }
  // Not a transport failure shape at all: a defect, not an outcome.
  throw error;
}

/** The author payload of a committed card (host stamp removed). */
export function authorOfCard(card: CouncilCard): Record<string, unknown> {
  const { host: _host, ...author } = card as unknown as Record<string, unknown>;
  return author;
}

/**
 * The brief view a CWE-025 provider payload carries: the assembled
 * context's view with private_preference_ref REMOVED in every round.
 * The preference content is never an assembly input at all; this
 * strips even the reference from the wire payload (see header).
 */
export function payloadBriefView(
  context: AssembledContext,
): Record<string, unknown> {
  const { private_preference_ref: _omitted, ...view } = context.brief as unknown as Record<
    string,
    unknown
  >;
  return view;
}

/** Composition dependencies shared by the CWE-025 round executors. */
export interface LaterRoundDeps {
  /** CWE-022 material catalog: pack and session material, host-composed. */
  readonly catalog: MaterialCatalog;
  /** The trusted principal per-seat assemblies run as (CWE-022/CWE-007). */
  readonly resolvePrincipal: (session: StoredSession) => TrustedPrincipal;
  /**
   * The CWE-009 transport serving the pinned route snapshot, or null
   * when no transport is composed for it. Null is an honest
   * pre-dispatch refusal, never a silent substitution.
   */
  readonly resolveTransport: (
    snapshot: PinnedRouteSnapshot,
    session: StoredSession,
  ) => ModelTransport | null | Promise<ModelTransport | null>;
  /**
   * The pinned route's real limits (Section 9.5), from verified route
   * data, never a guessed family default. Null when the route's limit
   * is not verified: planning reports the seat unplannable and
   * dispatch refuses before any provider call.
   */
  readonly routeBudget: (
    snapshot: PinnedRouteSnapshot,
  ) => Omit<RouteContextBudget, 'system_rules_bytes'> | null;
  /**
   * The session's committed cards, read through the CWE-006 store the
   * composition owns. Later rounds are functions of the committed
   * record: cruxes derive from committed Round 1 cards, the draft
   * from committed Round 2 cards. Synchronous because the CWE-006
   * repository read is synchronous.
   */
  readonly loadCommittedCards: (session: StoredSession) => readonly CouncilCard[];
  /**
   * Optional seat pack briefing text through the accepted pack
   * surface (the CWE-004 EvidenceProvider loadSeatPack shape). Absent
   * or null for a seat: the seat deliberates from its assembled
   * context, its Section 7 focus, and the committed record only.
   */
  readonly loadSeatBriefing?: (
    seatId: SeatId,
    session?: StoredSession,
  ) => Promise<{ briefing_text: string } | null>;
  /**
   * Optional actual-charge pricer for transports that meter money.
   * Absent (or returning null): the dispatch settles at the
   * operation's reserved estimate; unknown billed usage is never
   * reported as zero (Section 15.6).
   */
  readonly priceActual?: (info: {
    readonly response: TransportResponse;
    readonly snapshot: PinnedRouteSnapshot;
  }) => number | null;
  /** Assemblies are for internal deliberation unless composed otherwise. */
  readonly distributable?: boolean;
}

/** Narrow one seat's assembled context through CWE-022's own controls. */
export function assembleSeatContext(args: {
  deps: LaterRoundDeps;
  session: StoredSession;
  snapshot: PinnedRouteSnapshot;
  seatId: SeatId;
  operation: 'round_2_response' | 'round_3_ratification' | 'consult';
  /** The round this assembly feeds, when the caller knows it. */
  round?: number | null;
  systemText: string;
}): ContextAssemblyResult {
  const limits = args.deps.routeBudget(args.snapshot);
  if (limits === null) {
    throw new ContextError(
      'CONTEXT_ROUTE_INVALID',
      'The pinned route has no verified context limit; later-round inputs cannot be assembled honestly.',
    );
  }
  const route: RouteContextBudget = {
    ...limits,
    system_rules_bytes: cardSystemBytes(
      args.systemText,
      args.operation === 'round_3_ratification'
        ? 'ratification'
        : args.operation === 'consult'
          ? 'consult'
          : 'advisor',
      args.round ?? null,
    ),
  };
  const seatBudgets: Partial<Record<SeatId, number>> = {};
  for (const other of SEAT_IDS) {
    if (other !== args.seatId) seatBudgets[other] = 0;
  }
  const result = assembleContext({
    principal: args.deps.resolvePrincipal(args.session),
    session: {
      scope: args.session.scope,
      visibility: args.session.spec.visibility,
      session_id: args.session.spec.session_id,
      mode: args.session.spec.mode,
      seat_ids: [args.seatId],
    },
    brief: args.session.brief,
    operation: args.operation,
    route,
    catalog: args.deps.catalog,
    seat_budgets: seatBudgets,
    distributable: args.deps.distributable === true,
  });
  if (
    result.status === 'assembled' &&
    result.context.items.some((item) => item.seat_id !== args.seatId)
  ) {
    // Fail closed: a later-round context holding another seat's source
    // material is never planned on, dispatched, or validated against.
    throw new ContextError(
      'CONTEXT_CANDIDATE_INVALID',
      'The assembled context contains source material belonging to another seat; refusing to use it.',
    );
  }
  return result;
}

export type SeatContextResult =
  | {
      readonly status: 'assembled';
      readonly context: AssembledContext;
    }
  | {
      readonly status: 'context_too_small';
      readonly readiness: 'CONTEXT_TOO_SMALL';
      readonly minimum_required_bytes: number;
      readonly available_bytes: number;
      readonly supported_lower_context_modes: readonly SessionMode[];
    };

export function toSeatContextResult(result: ContextAssemblyResult): SeatContextResult {
  if (result.status === 'context_too_small') {
    return {
      status: 'context_too_small',
      readiness: result.readiness,
      minimum_required_bytes: result.minimum_required_bytes,
      available_bytes: result.available_bytes,
      supported_lower_context_modes: result.supported_lower_context_modes,
    };
  }
  return { status: 'assembled', context: result.context };
}

/** Source status for a dispatch result, from the assembled context. */
export function sourceStatusOf(
  context: AssembledContext,
): 'verified' | 'unverified' | 'not_applicable' {
  if (context.items.length === 0) return 'not_applicable';
  return context.items.every(
    (item) => item.provenance.verification_status === 'verified',
  )
    ? 'verified'
    : 'unverified';
}

/**
 * Evidence-citation checks shared by the later-round validators: a
 * card may cite, as framework source evidence, only material its own
 * assembled context actually contained; case evidence must belong to
 * the frozen brief manifest; a quotation validates only when backed
 * by host-verified material in the seat's own context (in this build
 * no pack record is verified, so no quotation validates, matching
 * CWE-012's acceptance conditions).
 */
export function citationIssues(args: {
  context: AssembledContext;
  brief: DecisionBrief;
  framework_applications: readonly {
    source_evidence_ids: readonly string[];
    case_evidence_ids: readonly string[];
  }[];
  quotes: readonly { quote_id: string; evidence_id: string; verification_status: string }[];
}): string[] {
  const issues: string[] = [];
  const itemIds = new Set(args.context.items.map((item) => item.evidence_id));
  const briefIds = new Set(args.brief.evidence_manifest.map((e) => e.evidence_id));
  const verifiedItemIds = new Set(
    args.context.items
      .filter((item) => item.provenance.verification_status === 'verified')
      .map((item) => item.evidence_id),
  );
  for (const application of args.framework_applications) {
    for (const evidenceId of application.source_evidence_ids) {
      if (!itemIds.has(evidenceId)) {
        issues.push(
          `framework_applications.source_evidence_ids: evidence ${evidenceId} was not in this seat's assembled context`,
        );
      }
    }
    for (const evidenceId of application.case_evidence_ids) {
      if (!briefIds.has(evidenceId)) {
        issues.push(
          `framework_applications.case_evidence_ids: evidence ${evidenceId} is not in the frozen evidence manifest`,
        );
      }
    }
  }
  for (const quote of args.quotes) {
    if (quote.verification_status !== 'verified' || !verifiedItemIds.has(quote.evidence_id)) {
      issues.push(
        `quotes: quote ${quote.quote_id} is not backed by verified material in this seat's assembled context`,
      );
    }
  }
  return issues;
}

// ------------------------------------------------------------------ cruxes

export type CruxType = 'fact' | 'numbers' | 'values' | 'execution';

/**
 * How a crux arose. Genuine disagreement origins (score_spread,
 * preference_split, blocking_condition) are distinguished from the
 * labeled adversarial test so no surface can present the stress test
 * as spontaneous dissent (T039).
 */
export type CruxOrigin =
  | 'score_spread'
  | 'preference_split'
  | 'blocking_condition'
  | 'unanimity_stress_test';

/** One decision-changing crux (Section 14.3). */
export interface Crux {
  readonly crux_id: string;
  readonly type: CruxType;
  readonly origin: CruxOrigin;
  /** True only for the Section 14.3 adversarial alternative test. */
  readonly adversarial_test: boolean;
  readonly option_id: string;
  readonly competing_claims: readonly string[];
  readonly responsible_seats: readonly SeatId[];
  readonly needed_evidence: string;
  readonly resolution_test: string;
}

/** The minimum score spread that makes an option's disagreement a crux. */
export const CRUX_SCORE_SPREAD = 4;
/** The Section 14.3 ceiling: at most three cruxes. */
export const MAX_CRUXES = 3;

function dedupeCardsBySeat(cards: readonly AdvisorCard[]): AdvisorCard[] {
  const bySeat = new Map<SeatId, AdvisorCard>();
  for (const card of cards) {
    if (!bySeat.has(card.seat_id)) bySeat.set(card.seat_id, card);
  }
  return [...bySeat.values()];
}

function inSeatOrder(cards: readonly AdvisorCard[], seatOrder: readonly SeatId[]): AdvisorCard[] {
  const rank = new Map(seatOrder.map((seatId, index) => [seatId, index]));
  return [...cards].sort(
    (a, b) => (rank.get(a.seat_id) ?? 99) - (rank.get(b.seat_id) ?? 99),
  );
}

function weightedMean(
  cards: readonly AdvisorCard[],
  weights: Partial<Record<SeatId, number>>,
  optionId: string,
): number | null {
  let sum = 0;
  let weight = 0;
  for (const card of cards) {
    const score = card.option_scores.find((s) => s.option_id === optionId)?.score;
    if (score === null || score === undefined) continue;
    const w = weights[card.seat_id] ?? 1;
    sum += score * w;
    weight += w;
  }
  return weight === 0 ? null : sum / weight;
}

/**
 * The Section 14.3 adversarial alternative test, built when every
 * valid opening card prefers the same option: the strongest neglected
 * alternative (the highest weighted-mean non-preferred option) is
 * tested by the seat least convinced of the consensus and the seat
 * that scored the alternative highest. Labeled, never disguised as
 * genuine dissent (T039). Returns null when there is no unanimity or
 * no scored alternative to test.
 */
export function unanimityStressCrux(
  previousCards: readonly AdvisorCard[],
  brief: DecisionBrief,
  seatOrder: readonly SeatId[],
): Crux | null {
  const cards = inSeatOrder(dedupeCardsBySeat(previousCards), seatOrder);
  const preferences = cards
    .map((c) => c.preferred_option_id)
    .filter((p): p is string => p !== null);
  if (cards.length < 2 || preferences.length !== cards.length) return null;
  const unanimous = preferences[0];
  if (!preferences.every((p) => p === unanimous)) return null;

  let alternative: string | null = null;
  let alternativeMean = -Infinity;
  for (const option of brief.options) {
    if (option.id === unanimous) continue;
    const mean = weightedMean(cards, brief.relevance_weights, option.id);
    if (mean !== null && mean > alternativeMean) {
      alternativeMean = mean;
      alternative = option.id;
    }
  }
  if (alternative === null) return null;

  const scoredOnUnanimous = cards
    .map((card) => ({
      seat_id: card.seat_id,
      score: card.option_scores.find((s) => s.option_id === unanimous)?.score ?? null,
    }))
    .filter((e): e is { seat_id: SeatId; score: number } => e.score !== null);
  const scoredOnAlternative = cards
    .map((card) => ({
      seat_id: card.seat_id,
      score: card.option_scores.find((s) => s.option_id === alternative)?.score ?? null,
    }))
    .filter((e): e is { seat_id: SeatId; score: number } => e.score !== null);
  const leastConvinced = [...scoredOnUnanimous].sort((a, b) => a.score - b.score)[0];
  const alternativeAdvocate = [...scoredOnAlternative].sort((a, b) => b.score - a.score)[0];
  const responsible: SeatId[] = [];
  for (const entry of [leastConvinced, alternativeAdvocate]) {
    if (entry && !responsible.includes(entry.seat_id)) responsible.push(entry.seat_id);
  }
  if (responsible.length === 0) return null;

  return {
    crux_id: 'crux-unassigned',
    type: 'values',
    origin: 'unanimity_stress_test',
    adversarial_test: true,
    option_id: unanimous,
    competing_claims: [
      `All ${cards.length} seats prefer option ${unanimous} in the opening round.`,
      `Option ${alternative} is the strongest neglected alternative (weighted mean ${alternativeMean.toFixed(2)}); it has not been adversarially tested.`,
    ],
    responsible_seats: responsible,
    needed_evidence:
      'The strongest recorded case for the neglected alternative, tested against the binding facts in the frozen brief.',
    resolution_test: `Argue the strongest case for option ${alternative} against option ${unanimous}, then confirm or revise your position. This is adversarial testing, not genuine dissent.`,
  };
}

/**
 * Identify up to three decision-changing cruxes from valid committed
 * opening cards (Section 14.3). Deterministic: the same committed
 * record always yields the same cruxes, IDs assigned in final order
 * (genuine disagreements first: numbers, then execution, then values;
 * the labeled adversarial test last). Fabricates nothing: every
 * competing claim is composed from values the cards actually recorded.
 */
export function extractCruxes(
  previousCards: readonly AdvisorCard[],
  brief: DecisionBrief,
  seatOrder: readonly SeatId[],
): Crux[] {
  const cards = inSeatOrder(dedupeCardsBySeat(previousCards), seatOrder);
  const found: Crux[] = [];

  // numbers: a wide score spread on one option.
  for (const option of brief.options) {
    const scored = cards
      .map((card) => ({
        seat_id: card.seat_id,
        score: card.option_scores.find((s) => s.option_id === option.id)?.score ?? null,
      }))
      .filter((e): e is { seat_id: SeatId; score: number } => e.score !== null);
    if (scored.length < 2) continue;
    const values = scored.map((s) => s.score);
    const spread = Math.max(...values) - Math.min(...values);
    if (spread >= CRUX_SCORE_SPREAD) {
      const sorted = [...scored].sort((a, b) => a.score - b.score);
      const low = sorted[0];
      const high = sorted[sorted.length - 1];
      found.push({
        crux_id: 'crux-unassigned',
        type: 'numbers',
        origin: 'score_spread',
        adversarial_test: false,
        option_id: option.id,
        competing_claims: [
          `${low.seat_id} scores option ${option.id} at ${low.score}`,
          `${high.seat_id} scores option ${option.id} at ${high.score}`,
        ],
        responsible_seats: [low.seat_id, high.seat_id],
        needed_evidence: `Evidence that resolves the ${spread}-point spread on option ${option.id}.`,
        resolution_test: `Re-score option ${option.id} after examining the spread's decisive facts.`,
      });
    }
  }

  // execution: a blocking condition on the contended leading option.
  let leading: string | null = null;
  let leadingMean = -Infinity;
  for (const option of brief.options) {
    const mean = weightedMean(cards, brief.relevance_weights, option.id);
    if (mean !== null && mean > leadingMean) {
      leadingMean = mean;
      leading = option.id;
    }
  }
  if (leading !== null) {
    const blocking = cards.flatMap((card) =>
      card.conditions
        .filter((condition) => condition.blocking)
        .map((condition) => ({ seat_id: card.seat_id, condition })),
    );
    const preferring = cards.filter((c) => c.preferred_option_id === leading);
    if (blocking.length > 0 && preferring.length > 0) {
      const first = blocking[0];
      const responsible: SeatId[] = [first.seat_id];
      const advocate = preferring.find((c) => c.seat_id !== first.seat_id) ?? preferring[0];
      if (!responsible.includes(advocate.seat_id)) responsible.push(advocate.seat_id);
      found.push({
        crux_id: 'crux-unassigned',
        type: 'execution',
        origin: 'blocking_condition',
        adversarial_test: false,
        option_id: leading,
        competing_claims: [
          `${first.seat_id} records a blocking condition on the path to option ${leading}: ${first.condition.description}`,
          `${preferring.length} seat(s) prefer option ${leading}: ${preferring.map((c) => c.seat_id).join(', ')}`,
        ],
        responsible_seats: responsible,
        needed_evidence:
          first.condition.required_evidence.length > 0
            ? first.condition.required_evidence.join('; ')
            : `Evidence that the blocking condition can be satisfied: ${first.condition.description}`,
        resolution_test: first.condition.verification_method,
      });
    }
  }

  // values: the panel prefers different options.
  const preferenceGroups = new Map<string, SeatId[]>();
  for (const card of cards) {
    if (card.preferred_option_id === null) continue;
    const list = preferenceGroups.get(card.preferred_option_id) ?? [];
    list.push(card.seat_id);
    preferenceGroups.set(card.preferred_option_id, list);
  }
  if (preferenceGroups.size > 1) {
    const groups = [...preferenceGroups.entries()].sort(
      (a, b) =>
        b[1].length - a[1].length ||
        brief.options.findIndex((o) => o.id === a[0]) -
          brief.options.findIndex((o) => o.id === b[0]),
    );
    const [firstGroup, secondGroup] = groups;
    found.push({
      crux_id: 'crux-unassigned',
      type: 'values',
      origin: 'preference_split',
      adversarial_test: false,
      option_id: firstGroup[0],
      competing_claims: [
        `${firstGroup[1].join(', ')} prefer option ${firstGroup[0]}`,
        `${secondGroup[1].join(', ')} prefer option ${secondGroup[0]}`,
      ],
      responsible_seats: [firstGroup[1][0], secondGroup[1][0]],
      needed_evidence: 'The decisive fact or value that separates the two preferred options.',
      resolution_test: 'Each responsible seat states what evidence would change its preference.',
    });
  }

  // The labeled adversarial test joins only when unanimity holds; it
  // never displaces a genuine disagreement beyond the ceiling.
  const stress = unanimityStressCrux(cards, brief, seatOrder);
  if (stress) found.push(stress);

  return found
    .slice(0, MAX_CRUXES)
    .map((crux, index) => ({ ...crux, crux_id: `crux-${index + 1}` }));
}

/** The cruxes one seat is responsible for, in crux order. */
export function assignedCruxesFor(
  cruxes: readonly Crux[],
  seatId: SeatId,
): Crux[] {
  return cruxes.filter((crux) => crux.responsible_seats.includes(seatId));
}

/**
 * A peer's recorded argument about one crux, excerpted from its
 * committed opening card: exactly the peer material a challenged seat
 * needs (Section 14.3), never the whole transcript.
 */
export interface PeerArgumentExcerpt {
  readonly seat_id: SeatId;
  readonly stance: AdvisorCard['stance'];
  readonly preferred_option_id: string | null;
  readonly score_for_crux_option: number | null;
  readonly decisive_arguments: readonly string[];
  readonly strongest_objection: string;
}

export function peerArgumentsFor(
  crux: Crux,
  previousCards: readonly AdvisorCard[],
  forSeatId: SeatId,
): PeerArgumentExcerpt[] {
  const excerpts: PeerArgumentExcerpt[] = [];
  for (const seatId of crux.responsible_seats) {
    if (seatId === forSeatId) continue;
    const card = previousCards.find((c) => c.seat_id === seatId);
    if (!card) continue;
    excerpts.push({
      seat_id: seatId,
      stance: card.stance,
      preferred_option_id: card.preferred_option_id,
      score_for_crux_option:
        card.option_scores.find((s) => s.option_id === crux.option_id)?.score ?? null,
      decisive_arguments: card.decisive_arguments,
      strongest_objection: card.strongest_objection,
    });
  }
  return excerpts;
}

/** Canonical digest of a set of committed cards' author payloads. */
export function cardSetSha256(cards: readonly CouncilCard[]): string {
  const authors = cards
    .map((card) => authorOfCard(card))
    .sort((a, b) =>
      String(a.seat_id).localeCompare(String(b.seat_id)) ||
      String(a.card_kind).localeCompare(String(b.card_kind)) ||
      String(a.round ?? '').localeCompare(String(b.round ?? '')),
    );
  return canonicalHash(authors);
}

/** Canonical digest of a crux set. */
export function cruxSetSha256(cruxes: readonly Crux[]): string {
  return canonicalHash(cruxes);
}

// ------------------------------------------------------- challenge executor

/**
 * The Section 14.3 logical prompt contract for the challenge round.
 * CWE-050 consolidation: the single source is CHALLENGE_SYSTEM in
 * cli/engine.ts; this name is kept as the protocol surface.
 */
export const CHALLENGE_ROUND_SYSTEM = `${CHALLENGE_SYSTEM}\n${WEB_TODAY_SYSTEM_RULE}`;

/** Identity kind tag for a Round 2 challenge input manifest. */
export const CHALLENGE_INPUT_KIND = 'wise-elders.challenge-input/v1';

/** The exact inputs one challenge operation is bound to. */
export interface ChallengeInputIdentity {
  readonly session_id: string;
  readonly brief_revision: number;
  readonly brief_sha256: string;
  readonly seat_id: SeatId;
  readonly pack_version: string;
  /** CWE-022 content hash of this seat's assembled challenge context. */
  readonly context_sha256: string;
  /** CWE-028 fingerprint of the pinned route snapshot. */
  readonly route_fingerprint: string;
  /**
   * Digest of the committed PREVIOUS round's card set the cruxes derive
   * from: round 1 cards for pass 2, round k-1 cards for pass k. The
   * field name is kept for the round-2 identity the earlier tests pin.
   */
  readonly round1_cards_sha256: string;
  /** Digest of the crux set extracted from those cards. */
  readonly cruxes_sha256: string;
  /**
   * The challenge pass this operation is. Round 2 is the first pass;
   * medium and heavy re-enter the challenge with rounds 3..10, and the
   * round is part of the input identity so every pass hashes differently
   * even when the committed card set repeats.
   */
  readonly round?: number;
}

export function challengeInputManifestSha256(identity: ChallengeInputIdentity): string {
  const round = identity.round ?? 2;
  return canonicalHash({
    kind: CHALLENGE_INPUT_KIND,
    session_id: identity.session_id,
    brief_revision: identity.brief_revision,
    brief_sha256: identity.brief_sha256,
    seat_id: identity.seat_id,
    round,
    pack_version: identity.pack_version,
    context_sha256: identity.context_sha256,
    route_fingerprint: identity.route_fingerprint,
    round1_cards_sha256: identity.round1_cards_sha256,
    cruxes_sha256: identity.cruxes_sha256,
  });
}

/** A fully planned challenge seat operation, ready to enqueue. */
export interface ChallengeSeatPlan {
  readonly seat_id: SeatId;
  readonly pack_version: string;
  readonly context_sha256: string;
  readonly route_fingerprint: string;
  readonly input_manifest_sha256: string;
  /** Cruxes this seat must answer; empty is a valid, planned state (T149). */
  readonly assigned_crux_ids: readonly string[];
  readonly item_evidence_ids: readonly string[];
}

export type ChallengePlanResult =
  | { readonly status: 'planned'; readonly plan: ChallengeSeatPlan }
  | {
      readonly status: 'context_too_small';
      readonly readiness: 'CONTEXT_TOO_SMALL';
      readonly minimum_required_bytes: number;
      readonly available_bytes: number;
      readonly supported_lower_context_modes: readonly SessionMode[];
    };

/** The full challenge round plan: the cruxes plus one plan per seat. */
export interface ChallengeRoundPlan {
  readonly cruxes: readonly Crux[];
  readonly plans: ReadonlyMap<SeatId, ChallengePlanResult>;
}

interface PreparedChallenge {
  readonly plan: ChallengeSeatPlan;
  readonly context: AssembledContext;
  readonly cruxes: readonly Crux[];
  readonly previousCards: readonly AdvisorCard[];
}

type PrepareChallengeResult =
  | { readonly status: 'prepared'; readonly seat: PreparedChallenge }
  | Extract<ChallengePlanResult, { status: 'context_too_small' }>;

export class ChallengeRoundExecutor implements OperationExecutorPort {
  constructor(private readonly deps: LaterRoundDeps) {}

  // ------------------------------------------------------------ planning

  planSeat(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
    seatId: SeatId,
    round = 2,
  ): ChallengePlanResult {
    const prepared = this.prepareSeat(session, snapshot, seatId, null, round);
    if (prepared.status === 'context_too_small') return prepared;
    return { status: 'planned', plan: prepared.seat.plan };
  }

  /**
   * Plan one challenge pass: extract the cruxes from the PREVIOUS
   * round's committed record once, then plan EVERY panel seat in spec
   * order, challenged or not (T149). Round 2 is the first pass; medium
   * and heavy re-enter with rounds 3..MAX_ADVISOR_ROUND, each pass
   * deriving its cruxes from the round before it.
   */
  planChallengeRound(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
    round = 2,
  ): ChallengeRoundPlan {
    const priorCards = this.previousCards(session, round);
    const cruxes = extractCruxes(priorCards, session.brief, session.spec.seat_ids);
    const plans = new Map<SeatId, ChallengePlanResult>();
    for (const seatId of session.spec.seat_ids) {
      plans.set(seatId, this.planSeat(session, snapshot, seatId, round));
    }
    return { cruxes, plans };
  }

  /** The cruxes the committed record before `round` currently yields. */
  cruxesFor(session: StoredSession, round = 2): Crux[] {
    return extractCruxes(
      this.previousCards(session, round),
      session.brief,
      session.spec.seat_ids,
    );
  }

  // ------------------------------------------------------------ dispatch

  async dispatch(
    ctx: OperationDispatchContext,
  ): Promise<OperationDispatchResult> {
    const { session, claim } = ctx;
    const seatId = claim.seat_id;
    if (seatId === null) {
      throw definiteDispatchRefusal(
        'challenge dispatch refused: the claimed operation has no seat',
      );
    }
    const claimedRound = claim.descriptor.round;
    const round = claimedRound as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;
    // Round 2 is the first challenge pass for every scored mode. The
    // council sizes re-enter the challenge for passes 3..10; the four
    // older modes never do, exactly as before.
    const roundOk = isCouncilSize(session.spec.mode)
      ? claimedRound >= 2 && claimedRound <= MAX_ADVISOR_ROUND
      : claimedRound === 2;
    if (!roundOk || claim.descriptor.kind !== 'provider_request') {
      throw definiteDispatchRefusal(
        `challenge dispatch refused: operation is round ${claimedRound} kind ${claim.descriptor.kind}, not a challenge provider request`,
      );
    }
    if (session.spec.mode === 'consult') {
      throw definiteDispatchRefusal(
        'challenge dispatch refused: a consult session has no challenge round',
      );
    }

    let prepared: PrepareChallengeResult;
    try {
      prepared = this.prepareSeat(session, claim.route_snapshot, seatId, claim, round);
    } catch (error) {
      if (error instanceof ContextError || error instanceof AuthorizationError) {
        throw definiteDispatchRefusal(
          `challenge dispatch refused before any provider call: ${error.name} ${'code' in error ? String((error as { code: unknown }).code) : ''}: ${error.message}`,
        );
      }
      throw error;
    }
    if (prepared.status === 'context_too_small') {
      throw definiteDispatchRefusal(
        `challenge dispatch refused before any provider call: CONTEXT_TOO_SMALL for seat ${seatId}: minimum ${prepared.minimum_required_bytes} canonical bytes, available ${prepared.available_bytes}`,
      );
    }
    const { plan, context, cruxes, previousCards } = prepared.seat;

    if (plan.input_manifest_sha256 !== claim.job.input_sha256) {
      throw definiteDispatchRefusal(
        `challenge dispatch refused before any provider call: input drift for seat ${seatId}: planned manifest ${plan.input_manifest_sha256} does not match the enqueued operation input ${claim.job.input_sha256}`,
      );
    }

    const transport = await this.deps.resolveTransport(claim.route_snapshot, session);
    if (!transport) {
      throw definiteDispatchRefusal(
        `challenge dispatch refused before any provider call: no transport is composed for the pinned route ${claim.route_snapshot.routeId}`,
      );
    }

    const pack = this.deps.loadSeatBriefing
      ? await this.deps.loadSeatBriefing(seatId, session)
      : null;

    const assigned = assignedCruxesFor(cruxes, seatId);
    const ownOpening = previousCards.find((c) => c.seat_id === seatId) ?? null;
    const briefView = payloadBriefView(context);

    const challengeIds = assigned.map((crux) => crux.crux_id);
    const system = cardRequestSystem(
      CHALLENGE_ROUND_SYSTEM,
      'advisor',
      challengeIds,
      ctx.attempt_kind === 'output_repair' ? ctx.repair_issues : [],
      round,
    );

    let response: TransportResponse;
    try {
      response = await transport.generate({
        signal: ctx.signal,
        purpose: 'advisor',
        session_id: session.spec.session_id,
        seat_id: seatId,
        round,
        route_id: claim.route_snapshot.routeId,
        model_policy: session.spec.model_policy,
        system,
        input: {
          // The seat's own assembled evidence context (its own source
          // material only), with the preference-free brief view.
          context: { ...context, brief: briefView },
          brief: briefView,
          seat_focus: SEAT_FOCUS[seatId],
          seat_display_name:
            SEAT_ROSTER.find((s) => s.seat_id === seatId)?.display_name ?? seatId,
          pack_briefing: pack?.briefing_text ?? null,
          input_manifest_sha256: plan.input_manifest_sha256,
          pack_version: plan.pack_version,
          // Its own committed previous-round position, to confirm or update.
          own_opening_card: ownOpening ? authorOfCard(ownOpening) : null,
          // Only the challenges assigned to this seat, each with the
          // peer arguments necessary to answer it (Section 14.3).
          challenges_for_seat: assigned.map((crux) => ({
            crux_id: crux.crux_id,
            question: `Resolve with evidence: ${crux.resolution_test}`,
          })),
          assigned_cruxes: assigned.map((crux) => ({
            ...crux,
            peer_arguments: peerArgumentsFor(crux, previousCards, seatId),
          })),
          challenge_note:
            assigned.length === 0
              ? `No targeted challenge is assigned to your seat. Confirm or update your previous position against the evidence; a fresh round ${round} card is still required.`
              : null,
          output_contract: cardOutputContract('advisor', challengeIds, round),
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
   * Deep validation of a stamped Round 2 card: identity, the input
   * manifest echo, the frozen brief, challenge integrity (T038: every
   * answered challenge is a real crux assigned to this seat; a
   * fabricated dispute or a crux belonging to another seat is
   * rejected; every assigned crux is answered unless the card is an
   * explicit abstention), the changed-score explanation rule
   * (Section 14.3), evidence citation bounds, quote gating, and
   * CWE-012's card source-use rules.
   */
  validateCard(ctx: OperationDispatchContext, card: CouncilCard): string[] {
    const { session, claim } = ctx;
    const issues: string[] = [];
    const seatId = claim.seat_id;
    if (card.card_kind !== 'advisor') {
      return [`card_kind: expected an advisor card, got ${card.card_kind}`];
    }
    const author: AdvisorCardAuthor = card;
    const round = claim.descriptor.round;
    if (author.round !== round) {
      issues.push(
        `round: challenge cards are round ${round}, got ${author.round}`,
      );
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
    for (const diagnostic of validateCardSourceUse({
      seat_id: author.seat_id,
      lenses_used: author.lenses_used,
    })) {
      if (diagnostic.severity === 'error') {
        issues.push(`source_use ${diagnostic.code}: ${diagnostic.message}`);
      }
    }

    if (seatId !== null) {
      let prepared: PrepareChallengeResult | null = null;
      try {
        prepared = this.prepareSeat(session, claim.route_snapshot, seatId, claim, round);
      } catch (error) {
        issues.push(
          `input_manifest_sha256: the challenge inputs could not be reassembled for validation (${error instanceof Error ? error.message : 'unknown error'})`,
        );
      }
      if (prepared !== null) {
        if (prepared.status === 'context_too_small') {
          issues.push(
            'input_manifest_sha256: the challenge inputs no longer fit the pinned route context budget',
          );
        } else {
          const { plan, context, cruxes, previousCards } = prepared.seat;
          if (author.input_manifest_sha256 !== plan.input_manifest_sha256) {
            issues.push(
              'input_manifest_sha256: card does not echo the challenge input manifest for this operation',
            );
          }
          if (author.input_manifest_sha256 !== claim.job.input_sha256) {
            issues.push(
              'input_manifest_sha256: card does not match the enqueued operation input',
            );
          }
          // T038: challenge references must be real and assigned here.
          const allCruxIds = new Set(cruxes.map((c) => c.crux_id));
          const assignedIds = new Set(
            assignedCruxesFor(cruxes, seatId).map((c) => c.crux_id),
          );
          for (const answeredId of author.challenges_answered) {
            if (!allCruxIds.has(answeredId)) {
              issues.push(
                `challenges_answered: ${answeredId} is not a disagreement identified from the committed opening record; a fabricated dispute is rejected`,
              );
            } else if (!assignedIds.has(answeredId)) {
              issues.push(
                `challenges_answered: ${answeredId} is assigned to another seat, not to ${seatId}`,
              );
            }
          }
          if (author.stance !== 'abstain') {
            for (const cruxId of assignedIds) {
              if (!author.challenges_answered.includes(cruxId)) {
                issues.push(
                  `challenges_answered: assigned challenge ${cruxId} is not answered; a seat that does not abstain must answer its assigned challenges`,
                );
              }
            }
          }
          // Section 14.3: a changed score without an explanation fails.
          const ownOpening = previousCards.find((c) => c.seat_id === seatId);
          if (ownOpening) {
            for (const score of author.option_scores) {
              const before = ownOpening.option_scores.find(
                (s) => s.option_id === score.option_id,
              );
              if (!before) continue;
              if (before.score !== score.score && before.rationale === score.rationale) {
                issues.push(
                  `option_scores.${score.option_id}: score changed from ${before.score} to ${score.score} with the opening rationale repeated verbatim; a changed score without an explanation is invalid`,
                );
              }
            }
          }
          issues.push(
            ...citationIssues({
              context,
              brief: session.brief,
              framework_applications: author.framework_applications,
              quotes: author.quotes,
            }),
          );
        }
      }
    }
    return issues;
  }

  // ------------------------------------------------------------- helpers

  /** The committed advisor cards of the round BEFORE `round`. */
  private previousCards(session: StoredSession, round: number): AdvisorCard[] {
    const wanted = round - 1;
    return this.deps
      .loadCommittedCards(session)
      .filter(
        (c): c is AdvisorCard => c.card_kind === 'advisor' && c.round === wanted,
      );
  }

  private prepareSeat(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
    seatId: SeatId,
    claim: { descriptor: { pack_version?: string | null } } | null,
    round = 2,
  ): PrepareChallengeResult {
    const assembled = toSeatContextResult(
      assembleSeatContext({
        deps: this.deps,
        session,
        snapshot,
        seatId,
        operation: 'round_2_response',
        round,
        systemText: CHALLENGE_ROUND_SYSTEM,
      }),
    );
    if (assembled.status === 'context_too_small') return assembled;
    const context = assembled.context;
    const previousCards = this.previousCards(session, round);
    const cruxes = extractCruxes(previousCards, session.brief, session.spec.seat_ids);
    const packVersion =
      claim?.descriptor.pack_version ?? session.spec.source_pack_version;
    const identity: ChallengeInputIdentity = {
      session_id: session.spec.session_id,
      brief_revision: session.brief.revision,
      brief_sha256: session.spec.brief_sha256,
      seat_id: seatId,
      pack_version: packVersion,
      context_sha256: context.content_sha256,
      route_fingerprint: routeSnapshotFingerprint(snapshot),
      round1_cards_sha256: cardSetSha256(previousCards),
      cruxes_sha256: cruxSetSha256(cruxes),
      round,
    };
    return {
      status: 'prepared',
      seat: {
        plan: {
          seat_id: seatId,
          pack_version: packVersion,
          context_sha256: context.content_sha256,
          route_fingerprint: identity.route_fingerprint,
          input_manifest_sha256: challengeInputManifestSha256(identity),
          assigned_crux_ids: assignedCruxesFor(cruxes, seatId).map((c) => c.crux_id),
          item_evidence_ids: context.items.map((item) => item.evidence_id),
        },
        context,
        cruxes,
        previousCards,
      },
    };
  }
}
