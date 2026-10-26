/**
 * CWE-050 production composition root (ONBOARDING/PORTABLE stream):
 * the full deliberation service composed ONLY from accepted parts.
 *
 * - CWE-024 OpeningRoundExecutor + CWE-025 ChallengeRoundExecutor,
 *   RatificationRoundExecutor, and ConsultExecutor, routed by
 *   operation round behind ONE OperationExecutorPort (the composite
 *   shape CWE-025's runner test documented as CWE-050's).
 * - CWE-027 DurableJobRunner: enqueue, admission-bound claim,
 *   fenced execution, in the supervisor's rhythm: the older modes claim
 *   one operation at a time (CWE-024 flag 8: claiming all seats first
 *   yields admission_refused requeues by design); the council sizes claim
 *   their whole wave under one lease-epoch bump, under CWE-028 capacity.
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
  AdvisorCard,
  CouncilCard,
  CouncilSettings,
  HardConstraintFinding,
  SeatId,
  SessionState,
  Verdict,
} from '../contracts/index.js';
import { isCouncilSize, MODE_ROUND_POLICY } from '../contracts/index.js';
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
  type DurableJobRunnerDeps,
  type OperationExecutorPort,
  type RunnerTimers,
  systemTimers,
} from '../queue/runner.js';
import { RuntimeCapacity } from '../queue/capacity.js';
import { OPERATION_LEASE_TTL_MS } from '../cli/leases.js';
import { deriveHardConstraintFindings } from '../scoring/decision.js';
import { OpeningRoundExecutor } from './opening.js';
import { ChallengeRoundExecutor } from './challenge.js';
import { evaluateConsensusStop } from './consensus.js';
import { isOllamaProvider } from '../providers/parallel.js';
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

/**
 * The one seat count a wave can hold: heavy runs nine seats and the wave
 * floor the design names is ten.
 */
const WAVE_SLOTS = 10;
/**
 * Default runtime capacity. A claimed wave runs to completion as a unit,
 * so the pool must admit a whole wave without refusing its later members
 * (claimWave raises the total anyway); three waves of head room plus the
 * private reserve keeps one session's wave from starving another's, and
 * the Section 15.7 private share still protects private work.
 */
export const DEFAULT_WAVE_CAPACITY = {
  total_slots: 3 * WAVE_SLOTS,
  private_reserved_slots: WAVE_SLOTS,
};

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
  /**
   * CWE-028 runtime capacity admission. Defaults to a wave-sized pool
   * (see DEFAULT_WAVE_CAPACITY) so claimWave's capacity guarantee is real
   * in production, not just in tests; a host may pass its own.
   */
  capacity?: RuntimeCapacity;
  timers?: RunnerTimers;
  /** Poll interval while waiting for another worker's round jobs; default 250ms. */
  roundWaitPollMs?: number;
  workerId?: string;
  distributable?: boolean;
  /** Reported when a paid response is discarded by a fenced settle. */
  onFencedSettle?: DurableJobRunnerDeps['onFencedSettle'];
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

/**
 * Money hold per operation. Zero: W77S-MODES removed every money
 * estimate and ceiling from the client path, and DurableBudgetService
 * accepts a zero estimate for an `estimated` cost knowledge (the
 * default), so the provider-request cap is the only enforced limit.
 */
const ESTIMATE_MINOR = 0;
const ROUND_WAIT_POLL_MS = 250;

/** Job terminal reasons that a fallback route may retry (Ollama only). */
const FALLBACK_FAILURE_CODES: ReadonlySet<string> = new Set([
  'transport_failed',
  'transport_rejected',
]);

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

    const routeExecutor = (
      round: number,
      mode: StoredSession['spec']['mode'],
    ): OperationExecutorPort => {
      // The council sizes run advisor passes 1..10 and no ratification
      // pass: round 1 is the opening, every later pass challenges.
      if (isCouncilSize(mode)) {
        return round === 1 ? this.opening : this.challenge;
      }
      if (round === 1) return this.opening;
      if (round === 2) return this.challenge;
      if (round === 3) return this.ratification;
      return this.consult;
    };
    const executeFor = (ctx: {
      claim: { descriptor: { round: number } };
      session: StoredSession;
    }): OperationExecutorPort =>
      routeExecutor(ctx.claim.descriptor.round, ctx.session.spec.mode);
    const composite: OperationExecutorPort = {
      dispatch: (ctx) => executeFor(ctx).dispatch(ctx),
      validateCard: (ctx, card) => executeFor(ctx).validateCard?.(ctx, card) ?? [],
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
      capacity: deps.capacity ?? new RuntimeCapacity(DEFAULT_WAVE_CAPACITY),
      timers: deps.timers,
      onFencedSettle: deps.onFencedSettle,
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
      /**
       * Seats claimed per wave. Default 1 = one claim at a time, today's
       * behaviour. Every claim of a wave is awaited together before the
       * next wave is claimed.
       */
      parallel_limit?: number;
      /**
       * Route used to re-run seats that failed on a transport or rate-limit
       * class failure and committed no card (Ollama routes only). The
       * grant's route pin is a security invariant, so a fallback route
       * needs its own approved grant: pass it as fallback_grant_id.
       * Without one the fallback job is admitted under grant_id and the
       * route pin refuses it, leaving today's failure path in place.
       */
      fallback_route_snapshot?: PinnedRouteSnapshot | null;
      /** Approved grant pinned to fallback_route_snapshot, when there is one. */
      fallback_grant_id?: string;
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
      routeSnapshot: PinnedRouteSnapshot = options.route_snapshot,
      keySuffix = '',
      grantId: string = options.grant_id,
      // The wave width for THIS round's route. Defaults to the primary
      // route's limit; the Ollama fallback overrides it because it runs
      // on a different provider with a different parallel limit.
      waveLimit: number = Math.max(1, options.parallel_limit ?? 1),
    ): Promise<void> => {
      const roundPrefix = `round-${round}:`;
      for (const [seatId, plan] of plans) {
        this.runner.enqueueOperation(envelope, {
          session_id: sessionId,
          phase_job_key: `round-${round}:${seatId}${keySuffix}`,
          seat_id: seatId,
          input_sha256: plan.input_manifest_sha256,
          descriptor: {
            kind: 'provider_request',
            purpose: options.purpose ?? 'council_run',
            grant_id: grantId,
            estimate_minor: ESTIMATE_MINOR,
            currency: 'USD',
            round,
            pack_version: plan.pack_version,
          },
          route_snapshot: routeSnapshot,
        });
      }
      // Claim, execute and settle a WAVE of up to parallel_limit
      // operations, then claim the next wave: every claim in a wave is
      // awaited together before the next wave is claimed, so no
      // in-flight operation is ever fenced by a later claim of the same
      // round. Default limit 1 = one claim at a time, today's
      // behaviour (and what the single-claim delegate returns).
      //
      // An admission refusal returns the job to queued intact (the
      // grant cannot fund it), so a refused or deferred outcome stops
      // the round's driving: the assembly step then reports the round
      // incomplete instead of the loop spinning on a job that cannot
      // proceed under this grant.
      //
      // A null claim is not "round done" when another worker (the
      // service's background supervisor) holds this round's jobs under
      // a live lease: wait, bounded, for them to reach a terminal
      // state (or return to queued, which this loop then claims).
      // With no competing worker the first null claim ends the round,
      // exactly as before.
      const limit = Math.max(1, waveLimit);
      const maxIterations = plans.size * 4 + 16;
      const timers = this.deps.timers ?? systemTimers;
      const pollMs = this.deps.roundWaitPollMs ?? ROUND_WAIT_POLL_MS;
      const maxWaits = Math.ceil((OPERATION_LEASE_TTL_MS * plans.size) / pollMs);
      const heldByOthers = (): boolean =>
        this.runner
          .listSessionJobs(envelope, sessionId)
          .some(
            (job) =>
              job.phase_job_key.startsWith(roundPrefix) &&
              (job.state === 'leased' || job.state === 'running'),
          );
      let claims = 0;
      let waits = 0;
      while (claims < maxIterations) {
        const wave = this.runner.claimWave(envelope, sessionId, this.workerId, limit);
        if (wave.length === 0) {
          if (waits >= maxWaits || !heldByOthers()) break;
          waits += 1;
          await timers.delay(pollMs);
          continue;
        }
        claims += wave.length;
        const outcomes = await Promise.all(
          wave.map((claim) => this.runner.executeClaimedOperation(envelope, claim)),
        );
        if (
          outcomes.some(
            (outcome) =>
              outcome.status === 'admission_refused' || outcome.status === 'deferred',
          )
        ) {
          break;
        }
      }
    };

    /**
     * Ollama fallback (W77S-MODES): after a round's wave on an Ollama
     * route, re-enqueue every seat whose jobs ended on a transport or
     * rate-limit class failure and committed no card, on the fallback
     * route snapshot, and run them all at once. No fallback snapshot,
     * a non-Ollama primary route, or no failed seat: nothing happens and
     * the existing failure path stands.
     */
    const fallbackAfterRound = async (
      round: number,
      planSeat: (
        seatId: SeatId,
        snapshot: PinnedRouteSnapshot,
      ) =>
        | { status: 'planned'; plan: { input_manifest_sha256: string; pack_version: string } }
        | { status: 'context_too_small' }
        | null,
    ): Promise<void> => {
      const fallback = options.fallback_route_snapshot ?? null;
      if (fallback === null) return;
      if (!isOllamaProvider(options.route_snapshot.providerSlug)) return;
      const cards = this.repositories.listCards(envelope, sessionId);
      const roundPrefix = `round-${round}:`;
      const failed = new Set<SeatId>();
      for (const failure of this.runner.listSessionFailures(envelope, sessionId)) {
        if (failure.seat_id === null) continue;
        if (!failure.phase_job_key.startsWith(roundPrefix)) continue;
        if (failure.phase_job_key.endsWith(':fallback')) continue;
        if (!FALLBACK_FAILURE_CODES.has(failure.outcome_code ?? '')) continue;
        const committed = cards.some(
          (card) =>
            'round' in card && card.round === round && card.seat_id === failure.seat_id,
        );
        if (committed) continue;
        failed.add(failure.seat_id as SeatId);
      }
      if (failed.size === 0) return;
      const plans = new Map<
        SeatId,
        { input_manifest_sha256: string; pack_version: string }
      >();
      for (const seatId of session.spec.seat_ids) {
        if (!failed.has(seatId)) continue;
        const planned = planSeat(seatId, fallback);
        if (planned !== null && planned.status === 'planned') {
          plans.set(seatId, planned.plan);
        }
      }
      if (plans.size === 0) return;
      // The fallback runs on ITS OWN provider, so the primary route's
      // Ollama wave width does not apply: an OpenRouter fallback has no
      // parallel limit and every failed seat re-runs in one wave. A
      // fallback that is itself Ollama keeps the primary plan limit (the
      // plan belongs to the client's Ollama account, not to the route).
      const fallbackLimit = isOllamaProvider(fallback.providerSlug)
        ? Math.max(1, options.parallel_limit ?? 1)
        : Math.max(1, plans.size);
      await enqueueRound(
        round,
        plans,
        fallback,
        ':fallback',
        options.fallback_grant_id ?? options.grant_id,
        fallbackLimit,
      );
    };

    // A round that ended with its work unfinished must not feed the next
    // round's plan: a job still queued/leased/running (the grant refused
    // it, or the loop gave up) would later commit a card and change the
    // draft input hash, so every Round 3 dispatch would refuse as input
    // drift. In full mode a seat with no card can only end BLOCKED, so
    // continuing would spend paid Round 2/3 calls on a session that cannot
    // produce a verdict. Stop in place.
    //
    // The stopped session is left BLOCKED with its committed cards intact,
    // but it is NOT resumable by any runner this runtime ships: runSession
    // is a one-shot driver, the service exposes no resume route, and the
    // local CLI engine refuses the council sizes (only the four older
    // modes have a resumable pipeline). BLOCKED here means "stopped, safe
    // to inspect" — not "resume to finish" (W77S-MODES review).
    const stalledRound = (round: number): RunSessionResult | null => {
      const prefix = `round-${round}:`;
      const unfinished = this.runner
        .listSessionJobs(envelope, sessionId)
        .some(
          (job) =>
            job.phase_job_key.startsWith(prefix) &&
            (job.state === 'queued' || job.state === 'leased' || job.state === 'running'),
        );
      const cards = this.repositories.listCards(envelope, sessionId);
      const missing = session.spec.seat_ids.filter(
        (seatId) => !cards.some((c) => c.card_kind === 'advisor' && c.round === round && c.seat_id === seatId),
      );
      // Every council size keeps the full roster (Trevor, 2026-10-25):
      // mode changes rounds and concurrency, never the panel.
      const keepsAllSeats =
        session.spec.mode === 'full' || isCouncilSize(session.spec.mode);
      if (!unfinished && !(keepsAllSeats && missing.length > 0)) return null;
      transition('BLOCKED');
      return {
        status: 'incomplete',
        detail: unfinished
          ? `round ${round} ended with unfinished work (a job is still queued or running); the session is blocked and resumable instead of planning round ${round + 1} from a partial record`
          : session.spec.mode === 'full'
            ? `full mode keeps all nine seats: ${missing.join(', ')} missing in round ${round}; stopped before round ${round + 1} because a session missing a seat cannot produce a verdict`
            : `${session.spec.mode} mode keeps its whole panel: ${missing.join(', ')} missing in round ${round}; stopped before round ${round + 1} because a session missing a seat cannot produce a verdict`,
        missing: missing.map((seat_id) => ({ round, seat_id })),
        budget: snapshotBudget(),
      };
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

    // Council sizes (light/medium/heavy): Round 1 is the isolated
    // opening; every later pass challenges the cruxes derived from the
    // round before it, and no separate ratification pass ever runs. The
    // stop rule (contracts/modes.ts) decides how many passes happen.
    if (isCouncilSize(session.spec.mode)) {
      const policy = MODE_ROUND_POLICY[session.spec.mode];
      const optionIds = session.spec.options.map((option) => option.id);
      const openingPlanFor = (seatId: SeatId, snapshot: PinnedRouteSnapshot) => {
        const planned = this.opening.planSeat(current(), snapshot, seatId);
        return planned.status === 'planned'
          ? { status: 'planned' as const, plan: planned.plan }
          : { status: 'context_too_small' as const };
      };

      await fallbackAfterRound(1, openingPlanFor);
      const stalledAfterOpening = stalledRound(1);
      if (stalledAfterOpening) return stalledAfterOpening;

      let completedRound = 1;
      for (;;) {
        const roundCards = this.repositories
          .listCards(envelope, sessionId)
          .filter(
            (card): card is AdvisorCard =>
              card.card_kind === 'advisor' && card.round === completedRound,
          );
        let continueRun: boolean;
        if (completedRound < policy.min_rounds) continueRun = true;
        else if (completedRound >= policy.max_rounds) continueRun = false;
        else if (
          policy.stop_from_round !== null &&
          completedRound >= policy.stop_from_round &&
          evaluateConsensusStop(roundCards, optionIds).stop
        ) {
          continueRun = false;
        } else continueRun = true;
        if (!continueRun) break;

        const nextRound = completedRound + 1;
        // Every extra pass re-enters CRUX_REVIEW -> ROUND_2: the pass
        // number lives in the job descriptor and the card, never in a
        // new state value.
        transition('CRUX_REVIEW');
        transition('ROUND_2');
        const pass = this.challenge.planChallengeRound(
          current(),
          options.route_snapshot,
          nextRound,
        );
        for (const result of pass.plans.values()) {
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
          nextRound,
          new Map(
            [...pass.plans].map(([seatId, result]) => [
              seatId,
              (result as { plan: { input_manifest_sha256: string; pack_version: string } }).plan,
            ]),
          ),
        );
        await fallbackAfterRound(nextRound, (seatId, snapshot) => {
          const planned = this.challenge.planSeat(current(), snapshot, seatId, nextRound);
          return planned.status === 'planned'
            ? { status: 'planned' as const, plan: planned.plan }
            : { status: 'context_too_small' as const };
        });
        const stalled = stalledRound(nextRound);
        if (stalled) return stalled;
        completedRound = nextRound;
      }

      transition('DRAFT_RESOLUTION');
      transition('VERIFYING');
      const councilCards: CouncilCard[] = this.repositories.listCards(envelope, sessionId);
      const outcome = assembleDeliberationOutcome({
        spec: session.spec,
        brief: session.brief,
        cards: councilCards,
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

    const stalledAfterRound1 = stalledRound(1);
    if (stalledAfterRound1) return stalledAfterRound1;

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

    const stalledAfterRound2 = stalledRound(2);
    if (stalledAfterRound2) return stalledAfterRound2;

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
