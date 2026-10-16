/**
 * CWE-025 tests, part 2: the later-round executors composed with the
 * real CWE-027 DurableJobRunner, CWE-049 admission, CWE-028's durable
 * budget, CWE-006 repositories, and CWE-022 context assembly, with
 * CWE-009-shaped fake transports and the CWE-004 deterministic
 * fixture transport. No live provider calls.
 *
 * Section 35 contracts exercised here:
 * - T021/T146: the full pipeline walks PREPARING -> ROUND_1 ->
 *   CRUX_REVIEW -> ROUND_2 -> DRAFT_RESOLUTION -> ROUND_3 ->
 *   VERIFYING with all nine seats in every round, and completion
 *   assembles a publishable verdict reproducing the Section 32.2
 *   golden values through CWE-026.
 * - T022 (real path): a quick session's Round 2 record passes the
 *   skip gate on real committed cards and completes with
 *   ratification not_run_by_quick_mode_policy and no invented
 *   resolution support; the quick state path goes DRAFT_RESOLUTION ->
 *   VERIFYING directly.
 * - T023/T146: a consult runs PREPARING -> CONSULTING -> VERIFYING,
 *   commits one ConsultCard through the runner, and completes as a
 *   discriminated consult result with no scores or vote.
 * - T038: a Round 2 card answering a fabricated crux, or a crux
 *   assigned to another seat, is rejected (repair, then honest
 *   failure); a changed score with the opening rationale repeated is
 *   rejected under Section 14.3.
 * - T039 (real path): a unanimous quick panel's challenge plan holds
 *   exactly the labeled adversarial test.
 * - T045: an explicit abstention Round 2 card commits AS an
 *   abstention; invalid cards never become abstentions.
 * - T046: ratification cards commit bound to the exact draft hash a
 *   card bound to another hash never commits.
 * - T048: every executor refuses an operation outside its own round;
 *   no fourth-round operation exists.
 * - T149: every panel seat is planned and returns a fresh Round 2
 *   card, including seats with no targeted challenge; a Round 1 card
 *   never satisfies a Round 2 job (the Round 2 input identity binds
 *   the Round 1 record, so the store's committed-card lookup misses).
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  GOLDEN_EXPECTED,
  GOLDEN_WEIGHTS,
  SEAT_IDS,
  type DecisionBrief,
  type RunCeilings,
  type ScopeFields,
  type SeatId,
  type SessionSpec,
} from '../src/contracts/index.js';
import { DeterministicFixtureTransport } from '../src/cli/fixture-transport.js';
import type {
  ModelTransport,
  StoredSession,
  TransportRequest,
  TransportResponse,
} from '../src/cli/host-ports.js';
import {
  RunAdmissionService,
  RunAuthorizationService,
  type TrustedPrincipal,
} from '../src/authorization/index.js';
import {
  DurableBudgetService,
  type PinnedRouteSnapshot,
} from '../src/budgets/index.js';
import { parsePersistenceConfig } from '../src/persistence/config.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from '../src/persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../src/persistence/index.js';
import { CouncilJobs } from '../src/persistence/jobs.js';
import { CouncilRepositories } from '../src/persistence/repositories.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';
import {
  DurableJobRunner,
  TransportDispatchError,
  type OperationDispatchContext,
  type OperationExecutorPort,
  type RunnerTimers,
} from '../src/queue/index.js';
import type {
  CandidateHeader,
  MaterialCandidate,
  MaterialCatalog,
} from '../src/context/index.js';
import type { EvidenceUnit, SourceRecord } from '../src/sources/index.js';
import { OpeningRoundExecutor } from '../src/protocol/opening.js';
import {
  ChallengeRoundExecutor,
  type LaterRoundDeps,
} from '../src/protocol/challenge.js';
import {
  ConsultExecutor,
  RatificationRoundExecutor,
  assembleConsultOutcome,
  assembleDeliberationOutcome,
  evaluateQuickModeSkip,
} from '../src/protocol/ratification.js';
import { quickModePolicyRecord } from '../src/intake/panel.js';

// ------------------------------------------------------------- fixtures

let nowIso = '2026-10-14T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

const SESSION_ID = 'sess-later-runner-1';
const PACK_VERSION = 'pack-test-1.0.0';
const PREFERENCE_MARKER = 'pref-marker-SECRET-025';

const SESSION_SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'install-a',
  owner_subject: 'owner-1',
};
const COMPANY_SCOPE: ScopeFields = { ...SESSION_SCOPE, owner_subject: null };

function principal(): TrustedPrincipal {
  return {
    tenant_id: SESSION_SCOPE.tenant_id,
    company_id: SESSION_SCOPE.company_id,
    installation_id: SESSION_SCOPE.installation_id,
    subject: 'owner-1',
    channel: 'local_owner',
    support_access: false,
  };
}

function seatMarker(seatId: SeatId): string {
  return `SEAT-MATERIAL-${seatId}`;
}

function seatSource(seatId: SeatId): SourceRecord {
  return {
    source_id: `src-${seatId}-work`,
    work_id: `work-${seatId}`,
    work_title: `Fixture work for ${seatId}`,
    credited_authors: [seatId],
    original_speaker: seatId,
    source_type: 'book',
    publisher_or_host: 'Fixture Publisher',
    edition_or_publication_date: '2020',
    retrieved_at: '2026-10-14T00:00:00Z',
    canonical_url: null,
    private_asset_id: null,
    content_sha256: canonicalHash({ record: seatId }),
    rights_status: 'reference_only',
    allowed_scope: 'shared_pack',
    locators: [{ kind: 'section', value: 'Part 1' }],
    quality: 'unverified',
  };
}

function seatUnit(seatId: SeatId, src: SourceRecord): EvidenceUnit {
  return {
    evidence_id: `ev-${seatId}`,
    source_id: src.source_id,
    source_version: src.content_sha256,
    locator: { kind: 'section', value: 'Part 1, Chapter 1' },
    kind: 'concept',
    mark: 'direct_teaching',
    original_speaker: seatId,
    excerpt: null,
    paraphrase: `${seatMarker(seatId)}: the one teaching paraphrase held for this seat.`,
    claim_ids: [`claim-${seatId}-1`],
    seat_id: seatId,
  };
}

function seatCandidate(seatId: SeatId): MaterialCandidate {
  const src = seatSource(seatId);
  const unit = seatUnit(seatId, src);
  const header: CandidateHeader = {
    evidence_id: unit.evidence_id,
    seat_id: seatId,
    scope: COMPANY_SCOPE,
    visibility: 'company',
    source_id: src.source_id,
    allowed_scope: src.allowed_scope,
    sha256: canonicalHash(unit),
  };
  return { header, source: src, unit };
}

class ListCatalog implements MaterialCatalog {
  constructor(private readonly candidates: readonly MaterialCandidate[]) {}
  listCandidateHeaders(): readonly CandidateHeader[] {
    return this.candidates.map((c) => c.header);
  }
  loadCandidate(evidenceId: string): MaterialCandidate | null {
    return this.candidates.find((c) => c.header.evidence_id === evidenceId) ?? null;
  }
}

const OPTIONS = [
  { id: 'A', label: 'Keep the current offer', kind: 'status_quo' as const },
  { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' as const },
  { id: 'C', label: 'Launch the revised offer broadly', kind: 'change' as const },
];

function briefFor(sessionId: string, panel: readonly SeatId[]): DecisionBrief {
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-later-runner-1',
    session_id: sessionId,
    revision: 1,
    question: 'Should we pilot the revised offer before a broad launch?',
    facts: [
      { id: 'fact-1', statement: 'Current offer converts at a measured baseline.', evidence_ids: ['ev-case-1'] },
    ],
    assumptions: [
      { id: 'asm-1', statement: 'Pilot capacity exists for one cohort.', evidence_ids: [] },
    ],
    unknowns: [
      { id: 'unk-1', statement: 'Pilot cohort retention is not yet measured.', evidence_ids: [] },
    ],
    constraints: [
      {
        id: 'con-1',
        description: 'Pilot spend must stay within the approved budget.',
        hard: true,
        applies_to_option_ids: ['B', 'C'],
      },
    ],
    options: OPTIONS.map((o) => ({ ...o })),
    relevance_weights: Object.fromEntries(
      panel.map((seatId) => [seatId, GOLDEN_WEIGHTS[SEAT_IDS.indexOf(seatId)]]),
    ),
    critical_domains: [],
    evidence_manifest: [
      ...panel.map((seatId) => {
        const candidate = seatCandidate(seatId);
        return {
          evidence_id: candidate.unit.evidence_id,
          sha256: candidate.header.sha256,
          source_kind: 'book' as const,
          locator: 'section:Part 1, Chapter 1',
        };
      }),
      {
        evidence_id: 'ev-case-1',
        sha256: canonicalHash({ case: 'baseline-metrics' }),
        source_kind: 'client_document' as const,
        locator: 'doc:baseline-metrics',
      },
    ],
    private_preference_ref: PREFERENCE_MARKER,
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
  };
}

function storedSession(
  mode: SessionSpec['mode'],
  panel: readonly SeatId[],
  sessionId: string = SESSION_ID,
): StoredSession {
  const brief = briefFor(sessionId, panel);
  const spec: SessionSpec = {
    schema_version: 'wise-elders.session/v1',
    session_id: sessionId,
    mode,
    visibility: 'company',
    brief_revision: 1,
    brief_sha256: canonicalHash(brief),
    options: OPTIONS.map((o) => ({ ...o })),
    seat_ids: [...panel],
    model_policy: {
      selection: 'explicit',
      route_id: 'route-a',
      requested_model_id: 'model-selected-by-client',
      reasoning_preference: null,
      fallback_policy: 'none',
    },
    source_pack_version: PACK_VERSION,
    execution_policy: 'advisory_only',
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
  };
  return {
    spec,
    brief,
    scope: { ...SESSION_SCOPE },
    state: {
      schema_version: 'wise-elders.session-state/v1',
      session_id: sessionId,
      mode,
      state: 'DRAFT',
      state_version: 0,
      brief_revision: 1,
      resume_phase: null,
      cancel_generation: 0,
      revocation_generation: 0,
      attempt: 1,
      lease_epoch: 0,
      archived: false,
      updated_at: spec.created_at,
    },
    sample: false,
  };
}

function routeSnapshot(): PinnedRouteSnapshot {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: 'route-a',
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'provider-a',
    requestedRoute: 'route-a',
    requestedModelOrAlias: 'model-selected-by-client',
    combinationMembers: null,
    reasoning: { requested: null, applied: null, supported: null, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot: {
      contextWindowTokens: 200000,
      maxOutputTokens: 8000,
      capabilities: ['text'],
      supportedReasoningLevels: null,
    },
    credential: {
      state: 'present',
      envVar: 'PROVIDER_A_API_KEY',
      source: 'process.env',
      checked: ['process.env'],
    },
    identityLevel: 'configured',
    scope: {
      tenantId: SESSION_SCOPE.tenant_id,
      companyId: SESSION_SCOPE.company_id,
      installationId: SESSION_SCOPE.installation_id,
      ownerSubject: SESSION_SCOPE.owner_subject,
    },
    createdAt: nowIso,
  };
}

const CEILINGS: RunCeilings = {
  max_provider_requests: 50,
  max_output_repairs: 9,
  max_transport_retries: 8,
  max_input_tokens: null,
  max_output_tokens: null,
  max_money: { amount_minor: 100_000, currency: 'USD' },
};

class ManualTimers implements RunnerTimers {
  private readonly everyFns = new Set<() => void>();
  every(_ms: number, fn: () => void): () => void {
    this.everyFns.add(fn);
    return () => this.everyFns.delete(fn);
  }
  delay(_ms: number): Promise<void> {
    return new Promise(() => {});
  }
}

// ------------------------------------------------------------- transports

type TransportScript = (
  request: TransportRequest,
  callIndexForSeat: number,
) => Promise<TransportResponse> | TransportResponse;

class RecordingTransport implements ModelTransport {
  readonly requests: TransportRequest[] = [];
  private readonly fixture = new DeterministicFixtureTransport();
  constructor(private readonly script?: TransportScript) {}
  async generate(request: TransportRequest): Promise<TransportResponse> {
    this.requests.push(request);
    const callIndexForSeat =
      this.requests.filter(
        (r) => r.seat_id === request.seat_id && r.round === request.round,
      ).length;
    if (this.script) return this.script(request, callIndexForSeat);
    return this.fixture.generate(request);
  }
  forSeat(seatId: SeatId, round?: number): TransportRequest[] {
    return this.requests.filter(
      (r) => r.seat_id === seatId && (round === undefined || r.round === round),
    );
  }
}

async function fixtureCard(
  request: TransportRequest,
  mutate?: (card: Record<string, unknown>) => void,
): Promise<TransportResponse> {
  const inner = new DeterministicFixtureTransport();
  const response = await inner.generate(request);
  if (!mutate) return response;
  const card = JSON.parse(response.text) as Record<string, unknown>;
  mutate(card);
  return { ...response, text: JSON.stringify(card) };
}

interface AdvisorScriptSpec {
  scores: Record<string, number | null>;
  preferred: string | null;
  stance?: string;
  conditions?: unknown[];
  challenges?: string[];
}

/** Build a valid advisor author card for a scripted transport. */
function advisorAuthor(request: TransportRequest, spec: AdvisorScriptSpec): Record<string, unknown> {
  const input = request.input as {
    brief: { session_id: string; revision: number };
    input_manifest_sha256: string;
    pack_version: string;
    challenges_for_seat?: Array<{ crux_id: string }>;
  };
  const seatId = request.seat_id as SeatId;
  return {
    schema_version: 'wise-elders.card/v1',
    session_id: input.brief.session_id,
    brief_revision: input.brief.revision,
    seat_id: seatId,
    input_manifest_sha256: input.input_manifest_sha256,
    pack_version: input.pack_version,
    card_kind: 'advisor',
    round: request.round ?? 1,
    stance: spec.stance ?? 'conditional',
    preferred_option_id: spec.preferred,
    option_scores: OPTIONS.map((o) => ({
      option_id: o.id,
      score: spec.scores[o.id] ?? null,
      rationale: `Scripted round ${request.round} rationale from ${seatId} for ${o.id}.`,
      evidence_ids: [],
    })),
    framework_applications: [
      {
        framework_id: 'fixture-framework-application',
        source_evidence_ids: [`ev-${seatId}`],
        case_evidence_ids: [],
        application: 'Applied the scripted framework to the frozen brief only.',
        attribution_kind: 'blackceo_adaptation',
      },
    ],
    decisive_arguments: [`Scripted decisive argument from ${seatId}.`],
    strongest_objection: 'Scripted objection: retention evidence is not yet measured.',
    conditions: spec.conditions ?? [],
    critical_unknowns: ['Scripted unknown: measured pilot retention.'],
    change_my_mind: 'Measured evidence that the binding constraint no longer holds.',
    challenges_answered:
      spec.challenges ?? (input.challenges_for_seat ?? []).map((c) => c.crux_id),
    quotes: [],
    evidence_strength: 'medium',
    minority_position: null,
  };
}

function scriptedResponse(request: TransportRequest, author: Record<string, unknown>): TransportResponse {
  return {
    text: JSON.stringify(author),
    provider_request_id: `scripted-${request.seat_id}-${request.round}`,
    reported_model_id: 'scripted-transport',
    usage: { input_tokens: null, output_tokens: null },
  };
}

// ------------------------------------------------------------ composition

interface Composition {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  jobs: CouncilJobs;
  budget: DurableBudgetService;
  grants: RunAuthorizationService;
  admission: RunAdmissionService;
}

function compose(dbPath: string): Composition {
  const db = CouncilDatabase.open(dbPath, {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const repositories = new CouncilRepositories(db, {
    clock,
    ids,
    config: parsePersistenceConfig(),
  });
  const jobs = new CouncilJobs(db, { clock, ids });
  const budget = new DurableBudgetService({ db, clock, ids });
  const grants = new RunAuthorizationService({ db, clock, ids });
  const admission = new RunAdmissionService(grants, budget);
  return { db, repositories, jobs, budget, grants, admission };
}

/** Routes each claimed operation to its round's executor (CWE-050's shape). */
class CompositeExecutor implements OperationExecutorPort {
  constructor(
    private readonly parts: {
      opening: OpeningRoundExecutor;
      challenge: ChallengeRoundExecutor;
      ratification: RatificationRoundExecutor;
      consult: ConsultExecutor;
    },
  ) {}
  private route(ctx: OperationDispatchContext): OperationExecutorPort {
    switch (ctx.claim.descriptor.round) {
      case 1: return this.parts.opening;
      case 2: return this.parts.challenge;
      case 3: return this.parts.ratification;
      default: return this.parts.consult;
    }
  }
  dispatch(ctx: OperationDispatchContext): Promise<import('../src/queue/index.js').OperationDispatchResult> {
    return this.route(ctx).dispatch(ctx);
  }
  validateCard(ctx: OperationDispatchContext, card: import('../src/contracts/index.js').CouncilCard): string[] {
    return this.route(ctx).validateCard?.(ctx, card) ?? [];
  }
}

interface Setup {
  ctx: Composition;
  session: StoredSession;
  envelope: AuthorizationEnvelope;
  worker: AuthorizationEnvelope;
  grantId: string;
  snapshot: PinnedRouteSnapshot;
  opening: OpeningRoundExecutor;
  challenge: ChallengeRoundExecutor;
  ratification: RatificationRoundExecutor;
  consult: ConsultExecutor;
  runner: DurableJobRunner;
  transition: (to: string) => void;
}

function setup(
  label: string,
  options: {
    mode?: SessionSpec['mode'];
    panel?: readonly SeatId[];
    transport?: RecordingTransport;
  } = {},
): Setup {
  nowIso = '2026-10-14T12:00:00.000Z';
  const mode = options.mode ?? 'full';
  const panel = options.panel ?? SEAT_IDS;
  const dbPath = join(mkdtempSync(join(tmpdir(), `cwe025-${label}-`)), 'council.db');
  const ctx = compose(dbPath);
  const session = storedSession(mode, panel);
  const envelope = envelopeFromScope(SESSION_SCOPE, 'owner-1', 'owner', 'write');
  const worker = envelopeFromScope(SESSION_SCOPE, 'owner-1', 'worker', 'write');
  ctx.repositories.createSession(envelope, session);
  const snapshot = routeSnapshot();
  const preview = ctx.grants.previewRun(envelope, {
    session_id: SESSION_ID,
    route_snapshot: snapshot,
    route_policy_sha256: canonicalHash({ policy: 'route-policy-a' }),
    ceilings: CEILINGS,
  });
  const grant = ctx.grants.approveRun(envelope, preview.preview_id, {
    principal: principal(),
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  let version = 0;
  const transition = (to: string): void => {
    ctx.repositories.transitionState(envelope, SESSION_ID, to as never, version);
    version += 1;
  };
  for (const to of ['READY', 'QUEUED', 'PREPARING'] as const) transition(to);

  const transport = options.transport ?? new RecordingTransport();
  const baseDeps: LaterRoundDeps = {
    catalog: new ListCatalog(panel.map((seatId) => seatCandidate(seatId))),
    resolvePrincipal: () => principal(),
    resolveTransport: () => transport,
    routeBudget: () => ({
      context_limit_bytes: 1_000_000,
      response_schema_bytes: 2_000,
      output_reserve_bytes: 8_000,
    }),
    loadCommittedCards: (s) => ctx.repositories.listCards(worker, s.spec.session_id),
  };
  const opening = new OpeningRoundExecutor({
    catalog: baseDeps.catalog,
    resolvePrincipal: baseDeps.resolvePrincipal,
    resolveTransport: baseDeps.resolveTransport,
    routeBudget: baseDeps.routeBudget,
  });
  const challenge = new ChallengeRoundExecutor(baseDeps);
  const ratification = new RatificationRoundExecutor(baseDeps);
  const consult = new ConsultExecutor(baseDeps);
  const runner = new DurableJobRunner({
    db: ctx.db,
    repositories: ctx.repositories,
    jobs: ctx.jobs,
    budget: ctx.budget,
    admission: ctx.admission,
    grants: ctx.grants,
    clock,
    ids,
    executor: new CompositeExecutor({ opening, challenge, ratification, consult }),
    timers: new ManualTimers(),
  });
  return {
    ctx, session, envelope, worker,
    grantId: grant.grant_id, snapshot,
    opening, challenge, ratification, consult, runner, transition,
  };
}

function enqueue(
  s: Setup,
  round: number,
  seatId: SeatId,
  inputSha256: string,
  packVersion: string,
): void {
  s.runner.enqueueOperation(s.worker, {
    session_id: SESSION_ID,
    phase_job_key: `round-${round}:${seatId}`,
    seat_id: seatId,
    input_sha256: inputSha256,
    descriptor: {
      kind: 'provider_request',
      purpose: 'council_run',
      grant_id: s.grantId,
      estimate_minor: 100,
      currency: 'USD',
      round,
      pack_version: packVersion,
    },
    route_snapshot: s.snapshot,
  });
}

async function runNext(s: Setup, seatId: SeatId, workerId = 'worker-1') {
  const claim = s.runner.claimNextOperation(s.worker, SESSION_ID, workerId);
  assert.ok(claim, `a claim must exist for ${seatId}`);
  assert.equal(claim.seat_id, seatId);
  return s.runner.executeClaimedOperation(s.worker, claim);
}

async function runRound1(s: Setup, seats: readonly SeatId[]): Promise<void> {
  s.transition('ROUND_1');
  for (const seatId of seats) {
    const planned = s.opening.planSeat(s.session, s.snapshot, seatId);
    assert.equal(planned.status, 'planned', `${seatId} opening plans`);
    if (planned.status !== 'planned') continue;
    enqueue(s, 1, seatId, planned.plan.input_manifest_sha256, planned.plan.pack_version);
    const outcome = await runNext(s, seatId);
    assert.equal(outcome.status, 'committed', `${seatId} opening commits`);
  }
}

async function runRound2(s: Setup, seats: readonly SeatId[]): Promise<void> {
  s.transition('CRUX_REVIEW');
  s.transition('ROUND_2');
  for (const seatId of seats) {
    const planned = s.challenge.planSeat(s.session, s.snapshot, seatId);
    assert.equal(planned.status, 'planned', `${seatId} challenge plans`);
    if (planned.status !== 'planned') continue;
    enqueue(s, 2, seatId, planned.plan.input_manifest_sha256, planned.plan.pack_version);
    const outcome = await runNext(s, seatId);
    assert.equal(outcome.status, 'committed', `${seatId} challenge commits`);
  }
}

// ------------------------------------------------------------------ tests

test('golden pipeline: nine seats through all three rounds assemble a publishable golden verdict (T021, T146, T149)', async () => {
  const transport = new RecordingTransport();
  const s = setup('golden', { transport });
  await runRound1(s, SEAT_IDS);

  // T149 planning half: every seat is planned for Round 2.
  const roundPlan = s.challenge.planChallengeRound(s.session, s.snapshot);
  assert.equal(roundPlan.plans.size, 9);

  await runRound2(s, SEAT_IDS);

  // Round 2 wire inspection: no seat saw the preference reference,
  // another seat's material, or the whole transcript; each request
  // carried only its assigned cruxes.
  const round2Requests = transport.requests.filter((r) => r.round === 2);
  assert.equal(round2Requests.length, 9, 'one Round 2 dispatch per seat');
  for (const request of round2Requests) {
    const wire = JSON.stringify(request.input);
    const seatId = request.seat_id as SeatId;
    assert.ok(wire.includes(seatMarker(seatId)), `${seatId} sees its own material`);
    for (const other of SEAT_IDS) {
      if (other !== seatId) {
        assert.ok(!wire.includes(seatMarker(other)), `${seatId} must not see ${other} material`);
      }
    }
    assert.ok(!wire.includes(PREFERENCE_MARKER), 'the preference reference never reaches a provider');
    const input = request.input as { assigned_cruxes: unknown[]; challenges_for_seat: unknown[] };
    assert.equal(input.assigned_cruxes.length, input.challenges_for_seat.length);
  }
  // T149: Round 2 cards are fresh participation, never Round 1 replays.
  const cardsAfterR2 = s.ctx.repositories.listCards(s.worker, SESSION_ID);
  assert.equal(cardsAfterR2.length, 18);
  const round1Manifests = new Set(
    cardsAfterR2.filter((c) => c.card_kind === 'advisor' && c.round === 1).map((c) => c.input_manifest_sha256),
  );
  for (const card of cardsAfterR2) {
    if (card.card_kind === 'advisor' && card.round === 2) {
      assert.ok(!round1Manifests.has(card.input_manifest_sha256), 'a Round 2 card carries a Round 2 identity');
    }
  }

  // Ratification: one composed draft, nine bound cards.
  s.transition('DRAFT_RESOLUTION');
  s.transition('ROUND_3');
  const ratificationPlan = s.ratification.planRatificationRound(s.session, s.snapshot);
  assert.equal(ratificationPlan.plans.size, 9);
  for (const seatId of SEAT_IDS) {
    const planned = ratificationPlan.plans.get(seatId);
    assert.equal(planned?.status, 'planned');
    if (planned?.status !== 'planned') continue;
    enqueue(s, 3, seatId, planned.plan.input_manifest_sha256, planned.plan.pack_version);
    const outcome = await runNext(s, seatId);
    assert.equal(outcome.status, 'committed', `${seatId} ratification commits`);
  }
  s.transition('VERIFYING');

  const cards = s.ctx.repositories.listCards(s.worker, SESSION_ID);
  assert.equal(cards.length, 27);
  for (const card of cards) {
    if (card.card_kind === 'ratification') {
      assert.equal(card.draft_resolution_sha256, ratificationPlan.draft.semantic_sha256, 'T046: bound to the exact draft');
    }
  }

  const outcome = assembleDeliberationOutcome({
    spec: s.session.spec,
    brief: s.session.brief,
    cards,
    draft_composition: ratificationPlan.composition,
  });
  assert.equal(outcome.status, 'complete');
  if (outcome.status !== 'complete') return;
  assert.equal(outcome.publication.publishable, true);
  assert.equal(outcome.verdict.recommended_option_id, 'B');
  const byId = new Map(outcome.verdict.option_scores.map((o) => [o.option_id, o]));
  for (const optionId of ['A', 'B', 'C'] as const) {
    const expected = GOLDEN_EXPECTED[optionId];
    const mine = byId.get(optionId);
    assert.ok(mine);
    assert.equal(mine.weighted_sum, expected.weighted_sum, `${optionId} sum`);
    assert.equal(mine.denominator, expected.denominator, `${optionId} denominator`);
    assert.equal(mine.score, expected.score, `${optionId} score`);
    assert.equal(mine.display_score, expected.display_score, `${optionId} display`);
  }
  assert.ok(outcome.resolution_support);
  const support = outcome.resolution_support;
  assert.equal(
    support.support + support.conditional_support + support.opposition + support.abstention,
    22,
    'support counts the full frozen weight, on the exact hash',
  );
  assert.equal(support.opposition, 0);
  assert.equal(outcome.ratification_status, 'ratified');
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  assert.equal(budget.consumed.provider_requests, 27, 'three rounds, counted once in CWE-028\'s ledger');
  assert.equal(budget.consumed.output_repairs, 0);
});

test('T038: a fabricated crux answer is rejected to honest failure; another seat\'s crux is rejected and repaired', async () => {
  const blocking = {
    id: 'cond-block-1',
    description: 'Pilot cohort capacity must be confirmed before any launch spend.',
    kind: 'evidence_required',
    blocking: true,
    verification_method: 'Confirm cohort capacity with the operations lead.',
    required_evidence: ['Written capacity confirmation'],
    responsible_role: 'operations',
    due_at: null,
    status: 'open',
    depends_on: [],
  };
  const openingSpecs: Partial<Record<SeatId, AdvisorScriptSpec>> = {
    'simon-sinek': { scores: { A: 9, B: 6, C: 5 }, preferred: 'A' },
    'td-jakes': { scores: { A: 2, B: 9, C: 5 }, preferred: 'B' },
    'brene-brown': { scores: { A: 8, B: 9, C: 5 }, preferred: 'B', conditions: [blocking] },
  };
  // Scripted openings for three seats; scripted Round 2 for simon
  // answers a crux that does not exist, on every attempt.
  const transportA = new RecordingTransport(async (request) => {
    if (request.round === 1) {
      const spec = openingSpecs[request.seat_id as SeatId];
      if (spec) return scriptedResponse(request, advisorAuthor(request, spec));
    }
    if (request.round === 2 && request.seat_id === 'simon-sinek') {
      return scriptedResponse(request, advisorAuthor(request, {
        scores: { A: 9, B: 5, C: 5 }, preferred: 'A', challenges: ['crux-99'],
      }));
    }
    return fixtureCard(request);
  });
  const a = setup('fabricated', { transport: transportA });
  await runRound1(a, ['simon-sinek', 'td-jakes', 'brene-brown']);
  a.transition('CRUX_REVIEW');
  a.transition('ROUND_2');
  const cruxes = a.challenge.cruxesFor(a.session);
  assert.ok(cruxes.length >= 2, 'the scripted record yields real cruxes');
  assert.ok(cruxes.every((c) => c.crux_id !== 'crux-99'));
  const plannedA = a.challenge.planSeat(a.session, a.snapshot, 'simon-sinek');
  assert.equal(plannedA.status, 'planned');
  if (plannedA.status === 'planned') {
    enqueue(a, 2, 'simon-sinek', plannedA.plan.input_manifest_sha256, plannedA.plan.pack_version);
  }
  const outcomeA = await runNext(a, 'simon-sinek');
  assert.equal(outcomeA.status, 'failed');
  assert.equal(outcomeA.reason, 'output_validation_failed');
  assert.equal(
    a.ctx.repositories.listCards(a.worker, SESSION_ID).filter(
      (c) => c.card_kind === 'advisor' && c.round === 2,
    ).length,
    0,
    'no card, and no fabricated abstention, is stored',
  );
  assert.equal(transportA.forSeat('simon-sinek', 2).length, 2, 'one repair, no more');

  // Scenario B: simon answers crux-2 (assigned to brene-brown and
  // td-jakes, not to simon) first; the repair returns a proper card.
  const transportB = new RecordingTransport(async (request, callIndex) => {
    if (request.round === 1) {
      const spec = openingSpecs[request.seat_id as SeatId];
      if (spec) return scriptedResponse(request, advisorAuthor(request, spec));
    }
    if (request.round === 2 && request.seat_id === 'simon-sinek' && callIndex === 1) {
      return scriptedResponse(request, advisorAuthor(request, {
        scores: { A: 9, B: 5, C: 5 }, preferred: 'A', challenges: ['crux-2'],
      }));
    }
    return fixtureCard(request);
  });
  const b = setup('foreign-crux', { transport: transportB });
  await runRound1(b, ['simon-sinek', 'td-jakes', 'brene-brown']);
  b.transition('CRUX_REVIEW');
  b.transition('ROUND_2');
  const cruxesB = b.challenge.cruxesFor(b.session);
  const foreign = cruxesB.find((c) => c.crux_id === 'crux-2');
  assert.ok(foreign, 'crux-2 exists');
  assert.ok(!foreign.responsible_seats.includes('simon-sinek'), 'crux-2 is not simon\'s');
  const plannedB = b.challenge.planSeat(b.session, b.snapshot, 'simon-sinek');
  assert.equal(plannedB.status, 'planned');
  if (plannedB.status === 'planned') {
    enqueue(b, 2, 'simon-sinek', plannedB.plan.input_manifest_sha256, plannedB.plan.pack_version);
  }
  const outcomeB = await runNext(b, 'simon-sinek');
  assert.equal(outcomeB.status, 'committed', 'the bounded repair recovers the seat');
  const budgetB = b.ctx.budget.snapshot(b.worker, SESSION_ID, b.grantId);
  assert.equal(budgetB.consumed.output_repairs, 1);
  const repairCall = transportB.forSeat('simon-sinek', 2)[1];
  assert.ok(
    repairCall.system.includes('assigned to another seat'),
    'the repair carries the T038 rejection reason',
  );
});

test('T038/14.3: a changed score with the opening rationale repeated verbatim is rejected, then repaired', async () => {
  const transport = new RecordingTransport(async (request, callIndex) => {
    if (request.round === 1 && request.seat_id === 'simon-sinek') {
      return scriptedResponse(request, advisorAuthor(request, {
        scores: { A: 9, B: 5, C: 5 }, preferred: 'A',
      }));
    }
    if (request.round === 1 && request.seat_id === 'td-jakes') {
      return scriptedResponse(request, advisorAuthor(request, {
        scores: { A: 2, B: 9, C: 5 }, preferred: 'B',
      }));
    }
    if (request.round === 2 && request.seat_id === 'simon-sinek' && callIndex === 1) {
      // Change the B score 5 -> 8 but repeat the opening rationale.
      const author = advisorAuthor(request, {
        scores: { A: 9, B: 8, C: 5 }, preferred: 'A',
      });
      const scores = author.option_scores as Array<Record<string, unknown>>;
      const bScore = scores.find((s) => s.option_id === 'B');
      if (bScore) bScore.rationale = 'Scripted round 1 rationale from simon-sinek for B.';
      return scriptedResponse(request, author);
    }
    return fixtureCard(request);
  });
  const s = setup('changed-score', { transport });
  await runRound1(s, ['simon-sinek', 'td-jakes']);
  s.transition('CRUX_REVIEW');
  s.transition('ROUND_2');
  const planned = s.challenge.planSeat(s.session, s.snapshot, 'simon-sinek');
  assert.equal(planned.status, 'planned');
  if (planned.status === 'planned') {
    enqueue(s, 2, 'simon-sinek', planned.plan.input_manifest_sha256, planned.plan.pack_version);
  }
  const outcome = await runNext(s, 'simon-sinek');
  assert.equal(outcome.status, 'committed');
  const calls = transport.forSeat('simon-sinek', 2);
  assert.equal(calls.length, 2);
  assert.ok(
    calls[1].system.includes('changed score without an explanation'),
    'the repair names the Section 14.3 quality rule',
  );
});

test('T045: an explicit abstention Round 2 card commits as an abstention', async () => {
  const transport = new RecordingTransport(async (request) => {
    if (request.round === 1 && request.seat_id === 'simon-sinek') {
      return scriptedResponse(request, advisorAuthor(request, {
        scores: { A: 9, B: 5, C: 5 }, preferred: 'A',
      }));
    }
    if (request.round === 1 && request.seat_id === 'td-jakes') {
      return scriptedResponse(request, advisorAuthor(request, {
        scores: { A: 2, B: 9, C: 5 }, preferred: 'B',
      }));
    }
    if (request.round === 2 && request.seat_id === 'td-jakes') {
      return scriptedResponse(request, advisorAuthor(request, {
        scores: { A: null, B: null, C: null },
        preferred: null,
        stance: 'abstain',
        challenges: [],
      }));
    }
    return fixtureCard(request);
  });
  const s = setup('abstention', { transport });
  await runRound1(s, ['simon-sinek', 'td-jakes']);
  s.transition('CRUX_REVIEW');
  s.transition('ROUND_2');
  const planned = s.challenge.planSeat(s.session, s.snapshot, 'td-jakes');
  assert.equal(planned.status, 'planned');
  if (planned.status === 'planned') {
    enqueue(s, 2, 'td-jakes', planned.plan.input_manifest_sha256, planned.plan.pack_version);
  }
  const outcome = await runNext(s, 'td-jakes');
  assert.equal(outcome.status, 'committed');
  const card = s.ctx.repositories
    .listCards(s.worker, SESSION_ID)
    .find((c) => c.card_kind === 'advisor' && c.round === 2 && c.seat_id === 'td-jakes');
  assert.ok(card && card.card_kind === 'advisor');
  assert.equal(card.stance, 'abstain');
  assert.ok(card.option_scores.every((score) => score.score === null));
});

test('T046: a ratification card bound to a different draft hash never commits', async () => {
  const uniform: AdvisorScriptSpec = { scores: { A: 5, B: 9, C: 6 }, preferred: 'B' };
  const transport = new RecordingTransport(async (request, callIndex) => {
    if (request.round === 1 || request.round === 2) {
      return scriptedResponse(request, advisorAuthor(request, uniform));
    }
    if (request.round === 3 && request.seat_id === 'simon-sinek') {
      return fixtureCard(request, (card) => {
        card.draft_resolution_sha256 = canonicalHash({ wrong: 'draft' });
      });
    }
    return fixtureCard(request);
  });
  const s = setup('misbound', { transport });
  const seats: SeatId[] = ['simon-sinek', 'td-jakes', 'brene-brown'];
  await runRound1(s, seats);
  await runRound2(s, seats);
  s.transition('DRAFT_RESOLUTION');
  s.transition('ROUND_3');
  const plan = s.ratification.planRatificationRound(s.session, s.snapshot);
  const planned = plan.plans.get('simon-sinek');
  assert.equal(planned?.status, 'planned');
  if (planned?.status === 'planned') {
    enqueue(s, 3, 'simon-sinek', planned.plan.input_manifest_sha256, planned.plan.pack_version);
  }
  const outcome = await runNext(s, 'simon-sinek');
  assert.equal(outcome.status, 'failed');
  assert.equal(outcome.reason, 'output_validation_failed');
  assert.equal(
    s.ctx.repositories.listCards(s.worker, SESSION_ID).filter((c) => c.card_kind === 'ratification').length,
    0,
    'the misbound card is not stored',
  );
  const calls = transport.forSeat('simon-sinek', 3);
  assert.equal(calls.length, 2, 'one repair, no more');
  assert.ok(calls[1].system.includes('exact draft resolution hash'));
});

test('quick pipeline: unanimous panel, labeled stress test, gate pass, completion without Round 3 (T022, T039, T146, T149)', async () => {
  const panel: SeatId[] = ['simon-sinek', 'tiffany-aliche', 'russell-brunson', 'brene-brown'];
  const uniform: AdvisorScriptSpec = { scores: { A: 5, B: 9, C: 6 }, preferred: 'B' };
  const transport = new RecordingTransport(async (request) => {
    if (request.round === 1 || request.round === 2) {
      return scriptedResponse(request, advisorAuthor(request, uniform));
    }
    return fixtureCard(request);
  });
  const s = setup('quick', { mode: 'quick', panel, transport });
  await runRound1(s, panel);

  // T039 in the real path: the challenge plan holds exactly the
  // labeled adversarial test, and every seat is planned (T149).
  const roundPlan = s.challenge.planChallengeRound(s.session, s.snapshot);
  assert.equal(roundPlan.cruxes.length, 1);
  assert.equal(roundPlan.cruxes[0].origin, 'unanimity_stress_test');
  assert.equal(roundPlan.cruxes[0].adversarial_test, true);
  assert.equal(roundPlan.plans.size, 4);
  const unchallenged = panel.filter(
    (seatId) => !roundPlan.cruxes[0].responsible_seats.includes(seatId),
  );
  assert.ok(unchallenged.length >= 2, 'seats exist with no targeted challenge');
  for (const seatId of unchallenged) {
    const planned = roundPlan.plans.get(seatId);
    assert.equal(planned?.status, 'planned');
    if (planned?.status === 'planned') {
      assert.deepEqual(planned.plan.assigned_crux_ids, []);
    }
  }

  await runRound2(s, panel);
  const cards = s.ctx.repositories.listCards(s.worker, SESSION_ID);
  assert.equal(cards.length, 8, 'four fresh Round 2 cards join the four openings (T149)');

  s.transition('DRAFT_RESOLUTION');
  const composition = s.ratification.composeDraft(s.session);
  const evaluation = evaluateQuickModeSkip({
    policy: quickModePolicyRecord(panel),
    brief: s.session.brief,
    round1Cards: cards.filter((c) => c.card_kind === 'advisor' && c.round === 1),
    round2Cards: cards.filter((c) => c.card_kind === 'advisor' && c.round === 2),
    draft: composition.draft,
    draft_action_source_condition_ids: composition.action_source_condition_ids,
  });
  assert.equal(evaluation.skip, true);

  const outcome = assembleDeliberationOutcome({
    spec: s.session.spec,
    brief: s.session.brief,
    cards,
    draft_composition: composition,
    quick_policy: quickModePolicyRecord(panel),
  });
  assert.equal(outcome.status, 'complete');
  if (outcome.status !== 'complete') return;
  assert.equal(outcome.ratification_status, 'not_run_by_quick_mode_policy');
  assert.equal(outcome.verdict.ratification_status, 'not_run_by_quick_mode_policy');
  assert.equal(outcome.resolution_support, null, 'no resolution-support votes are invented for a skipped round');
  assert.equal(outcome.verdict.recommended_option_id, 'B');
  assert.deepEqual(outcome.panel_seat_ids, panel, 'the quick verdict names its four seats');
  // The quick state path: DRAFT_RESOLUTION -> VERIFYING directly.
  s.transition('VERIFYING');
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  assert.equal(budget.consumed.provider_requests, 8, 'no Round 3 spend occurred');
});

test('consult pipeline: one seat, one card, a discriminated result with no invented vote (T023, T146)', async () => {
  const transport = new RecordingTransport();
  const panel: SeatId[] = ['tiffany-aliche'];
  const s = setup('consult', { mode: 'consult', panel, transport });
  s.transition('CONSULTING');
  const planned = s.consult.planConsult(s.session, s.snapshot);
  assert.equal(planned.status, 'planned');
  if (planned.status === 'planned') {
    enqueue(s, 0, 'tiffany-aliche', planned.plan.input_manifest_sha256, planned.plan.pack_version);
  }
  const outcome = await runNext(s, 'tiffany-aliche');
  assert.equal(outcome.status, 'committed');
  assert.equal(transport.requests.length, 1, 'exactly one provider request');
  assert.equal(transport.requests[0].purpose, 'consult');
  assert.equal(transport.requests[0].round, null);

  const cards = s.ctx.repositories.listCards(s.worker, SESSION_ID);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].card_kind, 'consult');

  s.transition('VERIFYING');
  const result = assembleConsultOutcome({ spec: s.session.spec, brief: s.session.brief, cards });
  assert.equal(result.status, 'complete');
  if (result.status !== 'complete') return;
  assert.equal(result.result.result_kind, 'consult');
  assert.equal(result.publication.publishable, true);
  const serialized = result.result as unknown as Record<string, unknown>;
  assert.ok(!('option_scores' in serialized), 'no invented scores');
  assert.ok(!('label' in serialized), 'no invented verdict label');
  assert.ok(!('resolution_support' in serialized), 'no invented consensus');
  assert.equal(result.result.next_step, result.result.consult_card.next_step);
});

test('T048: every later-round executor refuses an operation outside its own round', async () => {
  const s = setup('rounds-ceiling');
  const fakeCtx = (round: number): OperationDispatchContext =>
    ({
      session: s.session,
      claim: {
        seat_id: 'simon-sinek',
        descriptor: { round, kind: 'provider_request' },
        job: { input_sha256: canonicalHash({ fake: round }) },
        route_snapshot: s.snapshot,
      },
      dispatch_operation_id: 'op-fake',
      attempt_kind: 'initial',
      repair_issues: [],
    }) as unknown as OperationDispatchContext;

  await assert.rejects(
    () => s.challenge.dispatch(fakeCtx(4)),
    (err: unknown) => err instanceof TransportDispatchError && /round 4/.test(err.message),
    'the challenge executor refuses a fourth round',
  );
  await assert.rejects(
    () => s.challenge.dispatch(fakeCtx(1)),
    (err: unknown) => err instanceof TransportDispatchError,
    'the challenge executor refuses a Round 1 operation',
  );
  await assert.rejects(
    () => s.ratification.dispatch(fakeCtx(4)),
    (err: unknown) => err instanceof TransportDispatchError && /round 4/.test(err.message),
    'the ratification executor refuses a fourth round',
  );
  await assert.rejects(
    () => s.ratification.dispatch(fakeCtx(2)),
    (err: unknown) => err instanceof TransportDispatchError,
    'the ratification executor refuses a Round 2 operation',
  );
  await assert.rejects(
    () => s.consult.dispatch(fakeCtx(2)),
    (err: unknown) => err instanceof TransportDispatchError,
    'the consult executor refuses a scored-round operation',
  );
});

test('challenge drift: an enqueued input that no longer matches the committed record is refused before any provider call', async () => {
  const transport = new RecordingTransport();
  const s = setup('drift', { transport });
  await runRound1(s, ['simon-sinek', 'td-jakes']);
  s.transition('CRUX_REVIEW');
  s.transition('ROUND_2');
  enqueue(s, 2, 'simon-sinek', canonicalHash({ drifted: true }), PACK_VERSION);
  const outcome = await runNext(s, 'simon-sinek');
  assert.equal(outcome.status, 'failed');
  assert.equal(outcome.reason, 'transport_rejected');
  assert.equal(
    transport.forSeat('simon-sinek', 2).length,
    0,
    'no provider call was made for the drifted operation',
  );
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  // The drifted operation was admitted (its reservation exists) and
  // then refused inside dispatch, settling at actual_minor 0 through
  // CWE-027's transport_rejected channel: the ledger counts the
  // admitted attempt, and no provider call or charge occurred.
  assert.equal(budget.consumed.provider_requests, 3);
  assert.equal(budget.consumed.output_repairs, 0);
});
