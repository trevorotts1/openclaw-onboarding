/**
 * CWE-050 production composition root (ONBOARDING/PORTABLE stream):
 * the full deliberation service composed ONLY from accepted parts.
 *
 * - CWE-024 OpeningRoundExecutor + CWE-025 ChallengeRoundExecutor,
 *   RatificationRoundExecutor, and ConsultExecutor, routed by
 *   operation round behind ONE OperationExecutorPort (the composite
 *   shape CWE-025's runner test documented as CWE-050's).
 * - CWE-027 DurableJobRunner: enqueue, admission-bound claim,
 *   fenced execution, in the supervisor's rhythm (claim one, execute,
 *   repeat; CWE-024 flag 8: claiming all seats first yields
 *   admission_refused requeues by design).
 * - CWE-049 RunAuthorizationService + RunAdmissionService: preview,
 *   approve, admission; purposes run under their own grants.
 * - CWE-028 DurableBudgetService: the ONLY budget ledger.
 * - CWE-022 context through the executors' material catalog port
 *   (hosts supply the real pack catalog, e.g. the CWE-011 export
 *   adapter in sources/export-v2.ts).
 * - CWE-009 transports resolved per pinned route snapshot; a null
 *   resolution is an honest pre-dispatch refusal, never a silent
 *   substitution.
 *
 * Production resolution discipline (T123): this module imports no
 * fixture transport and no test double; a composition built without a
 * binding reports that binding unbound in readiness() (T129) and
 * refuses to run, naming what is missing. Readiness is derived from
 * the actual bound services, never from a flag.
 *
 * Completion discipline: a scored session completes only through
 * CWE-025's assembleDeliberationOutcome (publication-validated);
 * anything less is a visible BLOCKED partial record, never a smaller
 * council. Hard-constraint findings follow the reconciled CWE-026
 * semantics (deriveHardConstraintFindings): recorded checker results
 * supplied by the host win; unchecked hard constraints are `unknown`
 * and block an unconditional recommendation.
 */

import type {
  CouncilCard,
  CouncilSettings,
  HardConstraintFinding,
  SeatId,
  SessionState,
  Verdict,
} from '../contracts/index.js';
import type { TrustedPrincipal } from '../authorization/index.js';
import { RunAdmissionService } from '../authorization/admission.js';
import { RunAuthorizationService } from '../authorization/run-grants.js';
import { DurableBudgetService, type DurableBudgetSnapshot } from '../budgets/service.js';
import type { PinnedRouteSnapshot } from '../budgets/route-snapshot.js';
import type { MaterialCatalog } from '../context/types.js';
import type { RouteContextBudget } from '../context/assembly.js';
import type { StoredSession } from '../cli/host-ports.js';
import type { ModelTransport } from '../cli/host-ports.js';
import { quickModePolicyRecord } from '../intake/panel.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { envelopeFromScope } from '../persistence/envelope.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import { CouncilJobs } from '../persistence/jobs.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import type { CouncilDatabase } from '../persistence/sqlite.js';
import type { Clock, IdSource } from '../cli/host-ports.js';
import {
  DurableJobRunner,
  type OperationExecutorPort,
  type RunnerTimers,
} from '../queue/runner.js';
import { deriveHardConstraintFindings } from '../scoring/decision.js';
import { OpeningRoundExecutor } from './opening.js';
import { ChallengeRoundExecutor } from './challenge.js';
import {
  assembleConsultOutcome,
  assembleDeliberationOutcome,
  ConsultExecutor,
  evaluateQuickModeSkip,
  RatificationRoundExecutor,
  type DraftComposition,
} from './ratification.js';
import { ProtocolError } from './errors.js';
import { SessionControlsService } from './session-controls.js';
import { SessionHistoryService } from './history.js';
import { FollowUpService } from './follow-up.js';
import { OutcomeReviewService } from './outcomes.js';

export interface DeliberationCompositionDeps {
  db: CouncilDatabase;
  clock: Clock;
  ids: IdSource;
  /** CWE-022 material catalog; null means unbound (readiness fails). */
  catalog: MaterialCatalog | null;
  /** Trusted principal per-seat assemblies run as (CWE-007/CWE-022). */
  resolvePrincipal: ((session: StoredSession) => TrustedPrincipal) | null;
  /** CWE-009 transport for a pinned route snapshot; null = unbound. */
  resolveTransport:
    | ((
        snapshot: PinnedRouteSnapshot,
        session: StoredSession,
      ) => ModelTransport | null | Promise<ModelTransport | null>)
    | null;
  /** The pinned route's verified limits (Section 9.5); null = unbound. */
  routeBudget:
    | ((snapshot: PinnedRouteSnapshot) => Omit<RouteContextBudget, 'system_rules_bytes'> | null)
    | null;
  loadSeatBriefing?: (
    seatId: SeatId,
  ) => Promise<{ briefing_text: string } | null>;
  priceActual?: (info: {
    response: import('../cli/host-ports.js').TransportResponse;
    snapshot: PinnedRouteSnapshot;
  }) => number | null;
  /** Recorded hard-constraint checker results, when the host has any. */
  recordedHardConstraintFindings?: (
    session: StoredSession,
  ) => readonly HardConstraintFinding[];
  settings?: CouncilSettings;
  timers?: RunnerTimers;
  workerId?: string;
  distributable?: boolean;
}

export interface CompositionReadiness {
  ready: boolean;
  checks: Array<{ name: string; bound: boolean; detail: string }>;
}

export type RunSessionResult =
  | {
      status: 'completed';
      verdict: Verdict;
      budget: DurableBudgetSnapshot;
    }
  | {
      status: 'incomplete';
      detail: string;
      missing: Array<{ round: number; seat_id: SeatId }>;
      budget: DurableBudgetSnapshot;
    }
  | {
      status: 'readiness_failed';
      readiness: 'CONTEXT_TOO_SMALL';
      detail: string;
      budget: DurableBudgetSnapshot;
    };

const ESTIMATE_MINOR = 100;

export class DeliberationService {
  readonly repositories: CouncilRepositories;
  readonly jobs: CouncilJobs;
  readonly budget: DurableBudgetService;
  readonly grants: RunAuthorizationService;
  readonly admission: RunAdmissionService;
  readonly runner: DurableJobRunner;
  readonly controls: SessionControlsService;
  readonly history: SessionHistoryService;
  readonly followUp: FollowUpService;
  readonly outcomes: OutcomeReviewService;

  private readonly opening: OpeningRoundExecutor;
  private readonly challenge: ChallengeRoundExecutor;
  private readonly ratification: RatificationRoundExecutor;
  private readonly consult: ConsultExecutor;
  private readonly workerId: string;

  constructor(private readonly deps: DeliberationCompositionDeps) {
    const { db, clock, ids } = deps;
    this.repositories = new CouncilRepositories(db, {
      clock,
      ids,
      config: parsePersistenceConfig(),
    });
    this.jobs = new CouncilJobs(db, { clock, ids });
    this.budget = new DurableBudgetService({
      db,
      clock,
      ids,
      settings: deps.settings,
    });
    this.grants = new RunAuthorizationService({ db, clock, ids });
    this.admission = new RunAdmissionService(this.grants, this.budget);

    const roundDeps = {
      catalog: deps.catalog as MaterialCatalog,
      resolvePrincipal: deps.resolvePrincipal as (
        session: StoredSession,
      ) => TrustedPrincipal,
      resolveTransport: deps.resolveTransport as NonNullable<
        DeliberationCompositionDeps['resolveTransport']
      >,
      routeBudget: deps.routeBudget as NonNullable<
        DeliberationCompositionDeps['routeBudget']
      >,
      loadCommittedCards: (session: StoredSession) =>
        this.repositories.listCards(
          this.envelopeFor(session),
          session.spec.session_id,
        ),
      loadSeatBriefing: deps.loadSeatBriefing,
      priceActual: deps.priceActual,
      distributable: deps.distributable,
    };
    this.opening = new OpeningRoundExecutor(roundDeps);
    this.challenge = new ChallengeRoundExecutor(roundDeps);
    this.ratification = new RatificationRoundExecutor(roundDeps);
    this.consult = new ConsultExecutor(roundDeps);

    const routeExecutor = (round: number): OperationExecutorPort => {
      if (round === 1) return this.opening;
      if (round === 2) return this.challenge;
      if (round === 3) return this.ratification;
      return this.consult;
    };
    const composite: OperationExecutorPort = {
      dispatch: (ctx) => routeExecutor(ctx.claim.descriptor.round).dispatch(ctx),
      validateCard: (ctx, card) =>
        routeExecutor(ctx.claim.descriptor.round).validateCard?.(ctx, card) ?? [],
    };
    this.runner = new DurableJobRunner({
      db,
      repositories: this.repositories,
      jobs: this.jobs,
      budget: this.budget,
      admission: this.admission,
      grants: this.grants,
      clock,
      ids,
      executor: composite,
      timers: deps.timers,
    });
    this.workerId = deps.workerId ?? 'council-composition-worker';

    this.controls = new SessionControlsService({
      repositories: this.repositories,
      runner: this.runner,
    });
    this.history = new SessionHistoryService({ repositories: this.repositories });
    this.outcomes = new OutcomeReviewService({
      db,
      repositories: this.repositories,
      ids,
      clock,
    });
    this.followUp = new FollowUpService({
      db,
      repositories: this.repositories,
      driver: this,
      ids,
      clock,
    });
  }

  /** The worker envelope a session's committed cards are read under. */
  private envelopeFor(session: StoredSession): AuthorizationEnvelope {
    return envelopeFromScope(session.scope, this.workerId, 'worker', 'read');
  }

  /**
   * Readiness derived from the actual bound services (T129): every
   * capability the deliberation needs is checked against the deps
   * this composition was really built with. A scaffold composition
   * (any binding null) reports not ready and names the gaps.
   */
  readiness(): CompositionReadiness {
    const checks: CompositionReadiness['checks'] = [
      {
        name: 'material_catalog',
        bound: this.deps.catalog !== null,
        detail:
          this.deps.catalog !== null
            ? `${this.deps.catalog.listCandidateHeaders().length} candidate headers bound`
            : 'no material catalog bound; seat context cannot assemble',
      },
      {
        name: 'principal_resolution',
        bound: this.deps.resolvePrincipal !== null,
        detail:
          this.deps.resolvePrincipal !== null
            ? 'trusted-principal resolver bound'
            : 'no principal resolver bound; retrieval authorization cannot run',
      },
      {
        name: 'transport_resolution',
        bound: this.deps.resolveTransport !== null,
        detail:
          this.deps.resolveTransport !== null
            ? 'transport resolver bound (per pinned route snapshot)'
            : 'no transport resolver bound; no route can dispatch',
      },
      {
        name: 'route_budget',
        bound: this.deps.routeBudget !== null,
        detail:
          this.deps.routeBudget !== null
            ? 'route-budget resolver bound (verified route limits, Section 9.5)'
            : 'no route-budget resolver bound; context readiness cannot be proven',
      },
      {
        name: 'run_authorization',
        bound: true,
        detail: 'CWE-049 preview/approve/admission composed over the shared store',
      },
      {
        name: 'budget_ledger',
        bound: true,
        detail: 'CWE-028 durable budget service is the only ledger',
      },
      {
        name: 'job_runner',
        bound: true,
        detail: 'CWE-027 durable job runner composed with the round executors',
      },
    ];
    return { ready: checks.every((c) => c.bound), checks };
  }

  private assertReady(): void {
    const readiness = this.readiness();
    if (!readiness.ready) {
      const missing = readiness.checks
        .filter((c) => !c.bound)
        .map((c) => c.name)
        .join(', ');
      throw new ProtocolError(
        'COMPOSITION_NOT_READY',
        `The deliberation composition is not ready: unbound services: ${missing}. A scaffold cannot report the complete council ready (T129).`,
        { unbound: missing },
      );
    }
  }

  /**
   * Drive one session end to end: frozen brief to validated verdict.
   * The caller previews and approves first (CWE-049); admission inside
   * the runner enforces the grant on every operation.
   */
  async runSession(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    options: {
      grant_id: string;
      route_snapshot: PinnedRouteSnapshot;
      /** Admission purpose the grant was approved under (default council_run). */
      purpose?: string;
    },
  ): Promise<RunSessionResult> {
    this.assertReady();
    const session = this.repositories.getSession(envelope, sessionId);
    if (!session) {
      throw new ProtocolError('SESSION_NOT_FOUND', `Session ${sessionId} was not found.`, {
        session_id: sessionId,
      });
    }
    let version = session.state.state_version;
    const transition = (to: SessionState): void => {
      const record = this.repositories.transitionState(envelope, sessionId, to, version);
      version = record.state_version;
    };
    const current = (): StoredSession => {
      const fresh = this.repositories.getSession(envelope, sessionId);
      if (!fresh) throw new ProtocolError('SESSION_NOT_FOUND', `Session ${sessionId} vanished mid-run.`, { session_id: sessionId });
      return fresh;
    };
    const snapshotBudget = () => this.budget.snapshot(envelope, sessionId);

    if (session.state.state === 'DRAFT') transition('READY');
    else if (session.state.state !== 'READY') {
      throw new ProtocolError(
        'SESSION_STATE_CONFLICT',
        `Session ${sessionId} is ${session.state.state}; only a DRAFT or READY session can start a composed run.`,
        { session_id: sessionId, state: session.state.state },
      );
    }
    transition('QUEUED');
    transition('PREPARING');

    const findings = deriveHardConstraintFindings(
      session.brief,
      this.deps.recordedHardConstraintFindings?.(session) ?? [],
    );

    const enqueueRound = async (
      round: number,
      plans: ReadonlyMap<SeatId, { input_manifest_sha256: string; pack_version: string }>,
    ): Promise<void> => {
      for (const [seatId, plan] of plans) {
        this.runner.enqueueOperation(envelope, {
          session_id: sessionId,
          phase_job_key: `round-${round}:${seatId}`,
          seat_id: seatId,
          input_sha256: plan.input_manifest_sha256,
          descriptor: {
            kind: 'provider_request',
            purpose: options.purpose ?? 'council_run',
            grant_id: options.grant_id,
            estimate_minor: ESTIMATE_MINOR,
            currency: 'USD',
            round,
            pack_version: plan.pack_version,
          },
          route_snapshot: options.route_snapshot,
        });
      }
      // Supervisor rhythm (CWE-024 flag 8): claim one, execute, repeat.
      // An admission refusal returns the job to queued intact (the
      // grant cannot fund it), so a refused or deferred outcome stops
      // the round's driving: the assembly step then reports the round
      // incomplete instead of the loop spinning on a job that cannot
      // proceed under this grant.
      const maxIterations = plans.size * 4 + 16;
      for (let iteration = 0; iteration < maxIterations; iteration += 1) {
        const claim = this.runner.claimNextOperation(envelope, sessionId, this.workerId);
        if (!claim) break;
        const outcome = await this.runner.executeClaimedOperation(envelope, claim);
        if (outcome.status === 'admission_refused' || outcome.status === 'deferred') {
          break;
        }
      }
    };

    if (session.spec.mode === 'consult') {
      transition('CONSULTING');
      const plan = this.consult.planConsult(current(), options.route_snapshot);
      if (plan.status === 'context_too_small') {
        transition('BLOCKED');
        return {
          status: 'readiness_failed',
          readiness: 'CONTEXT_TOO_SMALL',
          detail: `consult seat needs ${plan.minimum_required_bytes} bytes; the pinned route offers ${plan.available_bytes}`,
          budget: snapshotBudget(),
        };
      }
      await enqueueRound(0, new Map([[plan.plan.seat_id, plan.plan]]));
      transition('VERIFYING');
      const cards = this.repositories.listCards(envelope, sessionId);
      const consultOutcome = assembleConsultOutcome({
        spec: session.spec,
        brief: session.brief,
        cards,
        verdict_revision: 1,
      });
      if (consultOutcome.status !== 'complete') {
        transition('BLOCKED');
        return {
          status: 'incomplete',
          detail: consultOutcome.detail,
          missing: session.spec.seat_ids.map((seat_id) => ({ round: 0, seat_id })),
          budget: snapshotBudget(),
        };
      }
      const verdict = consultOutcome.result;
      this.repositories.saveVerdict(envelope, verdict);
      transition('COMPLETED');
      return { status: 'completed', verdict, budget: snapshotBudget() };
    }

    // Round 1: opening.
    transition('ROUND_1');
    const openingPlans = this.opening.planOpeningRound(current(), options.route_snapshot);
    for (const result of openingPlans.values()) {
      if (result.status === 'context_too_small') {
        transition('BLOCKED');
        return {
          status: 'readiness_failed',
          readiness: 'CONTEXT_TOO_SMALL',
          detail: `a seat needs ${result.minimum_required_bytes} bytes; the pinned route offers ${result.available_bytes}`,
          budget: snapshotBudget(),
        };
      }
    }
    await enqueueRound(
      1,
      new Map(
        [...openingPlans].map(([seatId, result]) => [
          seatId,
          (result as { plan: { input_manifest_sha256: string; pack_version: string } }).plan,
        ]),
      ),
    );

    // Round 2: challenge.
    transition('CRUX_REVIEW');
    transition('ROUND_2');
    const challengeRound = this.challenge.planChallengeRound(current(), options.route_snapshot);
    for (const result of challengeRound.plans.values()) {
      if (result.status === 'context_too_small') {
        transition('BLOCKED');
        return {
          status: 'readiness_failed',
          readiness: 'CONTEXT_TOO_SMALL',
          detail: `a seat needs ${result.minimum_required_bytes} bytes; the pinned route offers ${result.available_bytes}`,
          budget: snapshotBudget(),
        };
      }
    }
    await enqueueRound(
      2,
      new Map(
        [...challengeRound.plans].map(([seatId, result]) => [
          seatId,
          (result as { plan: { input_manifest_sha256: string; pack_version: string } }).plan,
        ]),
      ),
    );

    // Draft + Round 3 (ratification), with the quick-mode skip rule.
    transition('DRAFT_RESOLUTION');
    const ratificationRound = this.ratification.planRatificationRound(
      current(),
      options.route_snapshot,
    );
    let draftComposition: DraftComposition | undefined = ratificationRound.composition;
    let runRound3 = session.spec.mode !== 'quick';
    if (session.spec.mode === 'quick') {
      const cards = this.repositories.listCards(envelope, sessionId);
      const skip = evaluateQuickModeSkip({
        policy: quickModePolicyRecord(session.spec.seat_ids),
        brief: session.brief,
        round1Cards: cards.filter((c) => c.card_kind === 'advisor' && c.round === 1) as never[],
        round2Cards: cards.filter((c) => c.card_kind === 'advisor' && c.round === 2) as never[],
        draft: ratificationRound.draft,
        draft_action_source_condition_ids: ratificationRound.composition.action_source_condition_ids,
        hard_constraint_findings: findings,
      });
      runRound3 = !skip.skip;
    }
    if (runRound3) {
      for (const result of ratificationRound.plans.values()) {
        if (result.status === 'context_too_small') {
          transition('BLOCKED');
          return {
            status: 'readiness_failed',
            readiness: 'CONTEXT_TOO_SMALL',
            detail: `a seat needs ${result.minimum_required_bytes} bytes; the pinned route offers ${result.available_bytes}`,
            budget: snapshotBudget(),
          };
        }
      }
      transition('ROUND_3');
      await enqueueRound(
        3,
        new Map(
          [...ratificationRound.plans].map(([seatId, result]) => [
            seatId,
            (result as { plan: { input_manifest_sha256: string; pack_version: string } }).plan,
          ]),
        ),
      );
    } else {
      draftComposition = ratificationRound.composition;
    }

    transition('VERIFYING');
    const cards: CouncilCard[] = this.repositories.listCards(envelope, sessionId);
    const outcome = assembleDeliberationOutcome({
      spec: session.spec,
      brief: session.brief,
      cards,
      draft_composition: draftComposition,
      quick_policy:
        session.spec.mode === 'quick'
          ? quickModePolicyRecord(session.spec.seat_ids)
          : undefined,
      hard_constraint_findings: findings,
      verdict_revision: 1,
    });
    if (outcome.status !== 'complete') {
      transition('BLOCKED');
      return {
        status: 'incomplete',
        detail: outcome.detail,
        missing: outcome.missing.map((m) => ({ round: m.round, seat_id: m.seat_id })),
        budget: snapshotBudget(),
      };
    }
    this.repositories.saveVerdict(envelope, outcome.verdict);
    transition('COMPLETED');
    return { status: 'completed', verdict: outcome.verdict, budget: snapshotBudget() };
  }
}

/** Compose the production deliberation service over one store. */
export function composeDeliberationService(
  deps: DeliberationCompositionDeps,
): DeliberationService {
  return new DeliberationService(deps);
}
