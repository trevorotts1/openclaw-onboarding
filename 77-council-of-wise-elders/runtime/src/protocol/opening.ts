/**
 * Independent opening-round execution: the Round 1 engine (CWE-024;
 * directive Sections 9.4, 9.5, 11.3, 14.2, 15, and the Section 34
 * CWE-024 build steps).
 *
 * What lives here:
 * - OpeningRoundExecutor, the OperationExecutorPort that CWE-027's
 *   durable runner dispatches through for Round 1 seat operations.
 *   The runner owns admission (CWE-049 admitOperation), consumption
 *   recording (CWE-028's one budget ledger), leases, fencing, and the
 *   bounded follow-on policy (one transport retry, one output repair,
 *   each a distinct admitted operation). This executor owns ONLY the
 *   per-dispatch work: per-seat context assembly, input-manifest
 *   identity, the provider call on the pinned route, and deep card
 *   validation. It commits nothing itself.
 * - The planner surface (planSeat / planOpeningRound) that computes the
 *   exact input identity an enqueueing composition (CWE-050) must use
 *   as the job's input_sha256, so a committed card is findable under
 *   the job's identity and any drift between planning and dispatch is
 *   refused before a provider call is made (Section 15.2: a card with
 *   different inputs is a new operation, not a reused result).
 *
 * Independence is the core invariant (Section 14.2): each seat's
 * operation assembles a FRESH context through CWE-022's bounded
 * authorized assembly in its round_1_opening form (which omits the
 * private preference reference entirely), narrowed to that one seat
 * through the assembler's own controls (seat_ids carries only that
 * seat; every other seat's input budget is zero) and verified
 * fail-closed before use, so no seat's payload can contain another
 * seat's material or output. Independence is never implemented as "clear
 * your head" inside a shared conversation: there is no shared
 * conversation. Each dispatch is one transport request carrying only
 * that seat's assembled context, its Section 7 focus, and its pack
 * briefing.
 *
 * Failure honesty (Sections 15.3, 15.5): a transport failure, an
 * unresolved provider submission, and an invalid card are three
 * distinct outcomes and stay distinct. CWE-009 TransportError honesty
 * flags are translated into the runner's TransportDispatchError with
 * the flags preserved; an invalid card is returned as an author
 * payload so the runner's validation drives the one bounded repair;
 * pre-dispatch refusals (input drift, context too small, no transport
 * composed for the pinned route, an unusable route budget) throw a
 * definite TransportDispatchError with actual_minor 0 BEFORE any
 * provider call, so no spend is ever recorded for a call that did not
 * happen. A seat that cannot produce a valid card ends in the runner's
 * honest recorded failure state; this executor never fabricates a
 * card, an abstention, or seat content.
 */

import {
  canonicalHash,
  SEAT_IDS,
  SEAT_ROSTER,
  validateCardAgainstBrief,
  type AdvisorCardAuthor,
  type CouncilCard,
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
import { OPENING_SYSTEM, SEAT_FOCUS } from '../cli/engine.js';
import { parseCardResponseText } from '../cli/card-text.js';
import {
  SimulatedCrashError,
  TransportDispatchError,
  type OperationDispatchContext,
  type OperationDispatchResult,
  type OperationExecutorPort,
} from '../queue/runner.js';
import { isTransportError } from '../providers/errors.js';
import { validateCardSourceUse } from '../sources/packs.js';

/**
 * The Section 14.2 logical prompt contract, verbatim. CWE-050
 * consolidation: the single source is OPENING_SYSTEM in cli/engine.ts
 * (the module this file already imports SEAT_FOCUS from); this name is
 * kept as the protocol surface for the same text.
 */
export const OPENING_ROUND_SYSTEM = OPENING_SYSTEM;

/** Identity kind tag for a Round 1 opening input manifest. */
export const OPENING_INPUT_KIND = 'wise-elders.opening-input/v1';

/** The exact inputs one opening operation is bound to. */
export interface OpeningInputIdentity {
  readonly session_id: string;
  readonly brief_revision: number;
  /** The frozen brief binding from the session spec. */
  readonly brief_sha256: string;
  readonly seat_id: SeatId;
  readonly pack_version: string;
  /** CWE-022 content hash of this seat's assembled Round 1 context. */
  readonly context_sha256: string;
  /** CWE-028 fingerprint of the pinned route snapshot. */
  readonly route_fingerprint: string;
}

/**
 * The one canonical derivation of an opening operation's input
 * manifest hash. The card a seat returns must echo this value in
 * input_manifest_sha256, and the job's input_sha256 must equal it, or
 * the card is not this operation's card.
 */
export function openingInputManifestSha256(identity: OpeningInputIdentity): string {
  return canonicalHash({
    kind: OPENING_INPUT_KIND,
    session_id: identity.session_id,
    brief_revision: identity.brief_revision,
    brief_sha256: identity.brief_sha256,
    seat_id: identity.seat_id,
    round: 1,
    pack_version: identity.pack_version,
    context_sha256: identity.context_sha256,
    route_fingerprint: identity.route_fingerprint,
  });
}

/** A fully planned opening seat operation, ready to enqueue. */
export interface OpeningSeatPlan {
  readonly seat_id: SeatId;
  readonly pack_version: string;
  readonly context_sha256: string;
  readonly route_fingerprint: string;
  readonly input_manifest_sha256: string;
  /** Evidence IDs this seat's assembled context actually contains. */
  readonly item_evidence_ids: readonly string[];
}

export type OpeningPlanResult =
  | { readonly status: 'planned'; readonly plan: OpeningSeatPlan }
  | {
      readonly status: 'context_too_small';
      readonly readiness: 'CONTEXT_TOO_SMALL';
      readonly minimum_required_bytes: number;
      readonly available_bytes: number;
      readonly supported_lower_context_modes: readonly SessionMode[];
    };

/**
 * Composition dependencies. Every port is an accepted surface owned by
 * another unit; this executor composes them and builds nothing
 * parallel: CWE-022's assembly is the only context assembler,
 * CWE-009's transports are the only provider path, CWE-028's service
 * (behind CWE-027's runner) is the only budget ledger.
 */
export interface OpeningRoundDeps {
  /** CWE-022 material catalog: pack and session material, host-composed. */
  readonly catalog: MaterialCatalog;
  /**
   * The trusted principal per-seat assemblies run as. Retrieval
   * authorization is decided by CWE-022/CWE-007 from this principal
   * before any content loads.
   */
  readonly resolvePrincipal: (session: StoredSession) => TrustedPrincipal;
  /**
   * The CWE-009 transport serving the pinned route snapshot, or null
   * when no transport is composed for it. A null resolution is an
   * honest pre-dispatch refusal, never a silent substitution: the
   * pinned route is the only route an opening operation may use.
   */
  readonly resolveTransport: (
    snapshot: PinnedRouteSnapshot,
    session: StoredSession,
  ) => ModelTransport | null | Promise<ModelTransport | null>;
  /**
   * The pinned route's real limits (Section 9.5), from verified route
   * data: never a guessed family default. context_limit_bytes is the
   * route's actual context limit in canonical bytes. Returns null when
   * the route's limit is not verified, in which case planning reports
   * the seat unplannable and dispatch refuses before any provider
   * call. The executor measures system_rules_bytes itself from the
   * exact prompt it sends and adds it to what this returns.
   */
  readonly routeBudget: (
    snapshot: PinnedRouteSnapshot,
  ) => Omit<RouteContextBudget, 'system_rules_bytes'> | null;
  /**
   * Optional seat pack briefing text through the accepted pack surface
   * (the CWE-004 EvidenceProvider loadSeatPack shape). Absent or null
   * for a seat: the seat deliberates from its assembled context and its
   * Section 7 focus only. Text is consumed as supplied; this executor
   * never invents seat content, quotations, or coverage.
   */
  readonly loadSeatBriefing?: (
    seatId: SeatId,
  ) => Promise<{ briefing_text: string } | null>;
  /**
   * Optional actual-charge pricer for transports that meter money.
   * Absent (or returning null): the dispatch settles at the
   * operation's reserved estimate. Unknown billed usage is never
   * reported as zero (Section 15.6); settling at the reserved estimate
   * is the conservative branch.
   */
  readonly priceActual?: (info: {
    readonly response: TransportResponse;
    readonly snapshot: PinnedRouteSnapshot;
  }) => number | null;
  /** Assemblies are for internal deliberation unless composed otherwise. */
  readonly distributable?: boolean;
}

interface PreparedSeat {
  readonly plan: OpeningSeatPlan;
  readonly context: AssembledContext;
}

type PrepareResult =
  | { readonly status: 'prepared'; readonly seat: PreparedSeat }
  | {
      readonly status: 'context_too_small';
      readonly readiness: 'CONTEXT_TOO_SMALL';
      readonly minimum_required_bytes: number;
      readonly available_bytes: number;
      readonly supported_lower_context_modes: readonly SessionMode[];
    };

function definiteRefusal(message: string): TransportDispatchError {
  // Neither honesty flag set: the runner records a definite failure
  // settled at actual_minor (0 here, because no provider call was
  // made). The message carries the true reason; the runner's outcome
  // vocabulary for this channel is its own (see the build report).
  return new TransportDispatchError(message, { actual_minor: 0 });
}

/** Translate a CWE-009 transport failure, preserving its honesty flags. */
function translateTransportError(error: unknown): TransportDispatchError {
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
  // Duck-typed flag carriers (the CWE-004 host-port transport shape):
  // the same honesty mapping applies to any transport that reports the
  // two flags.
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
  // Propagate so crash recovery, not a fabricated failure label,
  // governs the job.
  throw error;
}

export class OpeningRoundExecutor implements OperationExecutorPort {
  constructor(private readonly deps: OpeningRoundDeps) {}

  // ------------------------------------------------------------ planning

  /**
   * Plan one seat's opening operation against the session's pinned
   * route snapshot: assemble the seat's Round 1 context and derive the
   * input identity CWE-050 enqueues with. Deterministic for a fixed
   * catalog, brief, and snapshot: the same inputs plan the same
   * manifest at plan time, dispatch time, and validation time.
   */
  planSeat(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
    seatId: SeatId,
  ): OpeningPlanResult {
    const prepared = this.prepareSeat(session, snapshot, seatId, null);
    if (prepared.status === 'context_too_small') return prepared;
    return { status: 'planned', plan: prepared.seat.plan };
  }

  /** Plan every seated seat of the session, in spec order. */
  planOpeningRound(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
  ): ReadonlyMap<SeatId, OpeningPlanResult> {
    const results = new Map<SeatId, OpeningPlanResult>();
    for (const seatId of session.spec.seat_ids) {
      results.set(seatId, this.planSeat(session, snapshot, seatId));
    }
    return results;
  }

  // ------------------------------------------------------------ dispatch

  async dispatch(
    ctx: OperationDispatchContext,
  ): Promise<OperationDispatchResult> {
    const { session, claim } = ctx;
    const seatId = claim.seat_id;
    if (seatId === null) {
      throw definiteRefusal(
        'opening dispatch refused: the claimed operation has no seat',
      );
    }
    if (claim.descriptor.round !== 1 || claim.descriptor.kind !== 'provider_request') {
      throw definiteRefusal(
        `opening dispatch refused: operation is round ${claim.descriptor.round} kind ${claim.descriptor.kind}, not a round 1 provider request`,
      );
    }
    if (session.spec.mode === 'consult') {
      throw definiteRefusal(
        'opening dispatch refused: a consult session has no opening round',
      );
    }

    let prepared: PrepareResult;
    try {
      prepared = this.prepareSeat(session, claim.route_snapshot, seatId, claim);
    } catch (error) {
      if (error instanceof ContextError || error instanceof AuthorizationError) {
        throw definiteRefusal(
          `opening dispatch refused before any provider call: ${error.name} ${'code' in error ? String((error as { code: unknown }).code) : ''}: ${error.message}`,
        );
      }
      throw error;
    }
    if (prepared.status === 'context_too_small') {
      throw definiteRefusal(
        `opening dispatch refused before any provider call: CONTEXT_TOO_SMALL for seat ${seatId}: minimum ${prepared.minimum_required_bytes} canonical bytes, available ${prepared.available_bytes}`,
      );
    }
    const { plan, context } = prepared.seat;

    // Input drift: the inputs that exist now are not the inputs this
    // job was enqueued for. A card with different inputs is a new
    // operation (Section 15.2); refuse without dispatching.
    if (plan.input_manifest_sha256 !== claim.job.input_sha256) {
      throw definiteRefusal(
        `opening dispatch refused before any provider call: input drift for seat ${seatId}: planned manifest ${plan.input_manifest_sha256} does not match the enqueued operation input ${claim.job.input_sha256}`,
      );
    }

    const transport = await this.deps.resolveTransport(claim.route_snapshot, session);
    if (!transport) {
      throw definiteRefusal(
        `opening dispatch refused before any provider call: no transport is composed for the pinned route ${claim.route_snapshot.routeId}`,
      );
    }

    const pack = this.deps.loadSeatBriefing
      ? await this.deps.loadSeatBriefing(seatId)
      : null;

    const system =
      ctx.attempt_kind === 'output_repair' && ctx.repair_issues.length > 0
        ? `${OPENING_ROUND_SYSTEM}\nYour previous output failed validation: ${ctx.repair_issues.join('; ')}. Return a corrected card only.`
        : OPENING_ROUND_SYSTEM;

    let response: TransportResponse;
    try {
      response = await transport.generate({
        purpose: 'advisor',
        session_id: session.spec.session_id,
        seat_id: seatId,
        round: 1,
        route_id: claim.route_snapshot.routeId,
        model_policy: session.spec.model_policy,
        system,
        input: {
          // The assembled Round 1 context IS the seat's input: the
          // brief view inside it omits the private preference reference
          // entirely and carries only this seat's items, so nothing
          // about any other seat, and no private leaning, can reach
          // the provider through this payload.
          context,
          brief: context.brief,
          seat_focus: SEAT_FOCUS[seatId],
          seat_display_name:
            SEAT_ROSTER.find((s) => s.seat_id === seatId)?.display_name ?? seatId,
          pack_briefing: pack?.briefing_text ?? null,
          input_manifest_sha256: plan.input_manifest_sha256,
          pack_version: plan.pack_version,
        },
      });
    } catch (error) {
      if (error instanceof SimulatedCrashError) throw error;
      throw translateTransportError(error);
    }

    // Parse the author payload. An unparseable or non-object output
    // is an invalid card, not a dispatch failure: return an author
    // payload that can never validate, so the runner's validation
    // drives the one bounded repair and, failing that, the honest
    // output_validation_failed outcome. It is never committed.
    // CWE-048 item 13: parse through the shared tolerant card parser
    // (the same parser RP-046-3 adopted on the managed path). A direct
    // JSON parse keeps its historical semantics; when it fails or
    // yields a non-object, a balanced JSON object is located inside
    // prose-wrapped or fenced output and validated unchanged. A
    // response with no recoverable object still yields the empty
    // author payload, so validation drives the same bounded repair.
    let author: Record<string, unknown> = {};
    const parsedCard = parseCardResponseText(response.text);
    if (
      parsedCard.ok &&
      parsedCard.value !== null &&
      typeof parsedCard.value === 'object' &&
      !Array.isArray(parsedCard.value)
    ) {
      author = parsedCard.value as Record<string, unknown>;
    }

    const priced = this.deps.priceActual
      ? this.deps.priceActual({ response, snapshot: claim.route_snapshot })
      : null;

    return {
      author,
      provider_request_id: response.provider_request_id,
      actual_minor: priced ?? claim.descriptor.estimate_minor,
      input_tokens: response.usage.input_tokens,
      output_tokens: response.usage.output_tokens,
      source_status:
        context.items.length === 0
          ? 'not_applicable'
          : context.items.every(
                (item) => item.provenance.verification_status === 'verified',
              )
            ? 'verified'
            : 'unverified',
    };
  }

  // ---------------------------------------------------------- validation

  /**
   * Deep validation of a stamped opening card against the exact
   * inputs this operation owns: identity (session, brief revision,
   * seat, round, pack), the input manifest echo, the frozen brief
   * (canonical reference checks), the seat's assembled evidence (a
   * card may cite only material its own context actually contained),
   * quote gating (only host-verified material may carry a quote; in
   * this build no pack record is verified, so no quote validates),
   * and CWE-012's card source-use rules (Jakes lenses, one vote).
   */
  validateCard(ctx: OperationDispatchContext, card: CouncilCard): string[] {
    const { session, claim } = ctx;
    const issues: string[] = [];
    const seatId = claim.seat_id;
    if (card.card_kind !== 'advisor') {
      return [`card_kind: expected an advisor card, got ${card.card_kind}`];
    }
    const author: AdvisorCardAuthor = card;
    if (author.round !== 1) {
      issues.push(`round: opening cards are round 1, got ${author.round}`);
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
    if (author.challenges_answered.length > 0) {
      issues.push(
        'challenges_answered: an opening card answers no challenges; challenges belong to round 2',
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

    // Input binding: recompute the seat's assembled context and the
    // manifest it implies. A card that does not echo this operation's
    // manifest, or that cites evidence outside the seat's own
    // assembled context, is not this operation's card.
    if (seatId !== null) {
      let prepared: PrepareResult | null = null;
      try {
        prepared = this.prepareSeat(session, claim.route_snapshot, seatId, claim);
      } catch (error) {
        issues.push(
          `input_manifest_sha256: the opening inputs could not be reassembled for validation (${error instanceof Error ? error.message : 'unknown error'})`,
        );
      }
      if (prepared !== null) {
        if (prepared.status === 'context_too_small') {
          issues.push(
            'input_manifest_sha256: the opening inputs no longer fit the pinned route context budget',
          );
        } else {
          const { plan, context } = prepared.seat;
          if (author.input_manifest_sha256 !== plan.input_manifest_sha256) {
            issues.push(
              'input_manifest_sha256: card does not echo the opening input manifest for this operation',
            );
          }
          if (author.input_manifest_sha256 !== claim.job.input_sha256) {
            issues.push(
              'input_manifest_sha256: card does not match the enqueued operation input',
            );
          }
          const itemIds = new Set(context.items.map((item) => item.evidence_id));
          const briefIds = new Set(
            session.brief.evidence_manifest.map((e) => e.evidence_id),
          );
          const verifiedItemIds = new Set(
            context.items
              .filter((item) => item.provenance.verification_status === 'verified')
              .map((item) => item.evidence_id),
          );
          for (const application of author.framework_applications) {
            for (const evidenceId of application.source_evidence_ids) {
              if (!itemIds.has(evidenceId)) {
                issues.push(
                  `framework_applications.source_evidence_ids: evidence ${evidenceId} was not in this seat's assembled opening context`,
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
          for (const quote of author.quotes) {
            if (
              quote.verification_status !== 'verified' ||
              !verifiedItemIds.has(quote.evidence_id)
            ) {
              issues.push(
                `quotes: quote ${quote.quote_id} is not backed by verified material in this seat's assembled opening context`,
              );
            }
          }
        }
      }
    }
    return issues;
  }

  // ------------------------------------------------------------- helpers

  /**
   * Assemble one seat's Round 1 context and derive its plan.
   *
   * CWE-022's assembly retrieves every authorized manifest item and
   * then fills the context: the mandatory minimum is the first item
   * of each seat named in the request, and discretionary fill is
   * capped per seat by seat_budgets. The opening round narrows both
   * controls to the one seat: seat_ids carries only that seat (so the
   * mandatory minimum is its first item alone) and every other seat's
   * budget is zero (so no other seat's item can enter as discretionary
   * fill). The assembled payload can therefore contain only this
   * seat's items, which is what makes the independence invariant
   * structural rather than promissory. As a fail-closed guard, the
   * result is verified before use: a context containing any other
   * seat's item is refused, never dispatched.
   */
  private prepareSeat(
    session: StoredSession,
    snapshot: PinnedRouteSnapshot,
    seatId: SeatId,
    claim: { descriptor: { pack_version?: string | null } } | null,
  ): PrepareResult {
    const limits = this.deps.routeBudget(snapshot);
    if (limits === null) {
      throw new ContextError(
        'CONTEXT_ROUTE_INVALID',
        'The pinned route has no verified context limit; opening inputs cannot be assembled honestly.',
      );
    }
    const route: RouteContextBudget = {
      ...limits,
      system_rules_bytes: new TextEncoder().encode(OPENING_ROUND_SYSTEM).length,
    };
    const seatBudgets: Partial<Record<SeatId, number>> = {};
    for (const other of SEAT_IDS) {
      if (other !== seatId) seatBudgets[other] = 0;
    }
    const result: ContextAssemblyResult = assembleContext({
      principal: this.deps.resolvePrincipal(session),
      session: {
        scope: session.scope,
        visibility: session.spec.visibility,
        session_id: session.spec.session_id,
        mode: session.spec.mode,
        seat_ids: [seatId],
      },
      brief: session.brief,
      operation: 'round_1_opening',
      route,
      catalog: this.deps.catalog,
      seat_budgets: seatBudgets,
      distributable: this.deps.distributable === true,
    });
    if (result.status === 'context_too_small') {
      return {
        status: 'context_too_small',
        readiness: result.readiness,
        minimum_required_bytes: result.minimum_required_bytes,
        available_bytes: result.available_bytes,
        supported_lower_context_modes: result.supported_lower_context_modes,
      };
    }
    const packVersion =
      claim?.descriptor.pack_version ?? session.spec.source_pack_version;
    const context = result.context;
    // Fail closed on the independence invariant: whatever the
    // assembler's fill semantics, a Round 1 context holding another
    // seat's item is never planned on, dispatched, or validated
    // against.
    if (context.items.some((item) => item.seat_id !== seatId)) {
      throw new ContextError(
        'CONTEXT_CANDIDATE_INVALID',
        'The assembled opening context contains material belonging to another seat; refusing to use it.',
      );
    }
    const identity: OpeningInputIdentity = {
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
          input_manifest_sha256: openingInputManifestSha256(identity),
          item_evidence_ids: context.items.map((item) => item.evidence_id),
        },
        context,
      },
    };
  }
}
