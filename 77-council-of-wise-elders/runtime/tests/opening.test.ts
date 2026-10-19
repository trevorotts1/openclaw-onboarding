/**
 * CWE-024 tests: independent opening-round execution
 * (src/protocol/opening.ts), composed over the real CWE-027
 * DurableJobRunner, CWE-049 admission, CWE-028's DurableBudget
 * service, CWE-006 repositories, and CWE-022 context assembly, with
 * CWE-009-shaped fake transports and the CWE-004 deterministic fixture
 * transport. No live provider calls.
 *
 * Section 35 contracts exercised here:
 * - T018 (executor proof, owned by CWE-024): Round 1 independence is
 *   EXECUTED, not just assembled. The recorded provider requests are
 *   inspected: each seat's request carries only its own assembled
 *   context (its own material marker, no other seat's), the Round 1
 *   brief view omits the private preference reference entirely, and
 *   serial and parallel executions produce identical cards.
 * - T037 (owned by CWE-024): every committed opening card's
 *   input_manifest_sha256 is the distinct per-seat manifest the job
 *   was enqueued with, binding session, brief revision, seat, pack,
 *   the seat's assembled context hash, and the pinned route
 *   fingerprint. Input drift between planning and dispatch is refused
 *   before any provider call.
 * - T045 negative half (owned by CWE-025, exercised by these failure
 *   paths): a timeout-class unknown completion and an invalid card
 *   never become an abstention; they end in their own recorded
 *   outcomes (provider_completion_unknown, output_validation_failed).
 *
 * Also proven: the golden path stays intact (the executor's committed
 * cards feed CWE-026's analyzeDecision and reproduce the Section 32.2
 * values A 132/22 = 6.0, B 168/22 = 7.6 display, C 145/22 = 6.6
 * display); transport retry and output repair stay distinct admitted
 * operations in CWE-028's one ledger; an absent seat (no pack
 * material) can return an honest model-authored abstention and the
 * executor fabricates nothing; deep validation rejects cross-seat
 * evidence claims, unverified quotes, lenses on the wrong seat, and
 * round 1 challenge answers.
 */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync } from 'node:fs';
import type { AddressInfo } from 'node:net';
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
import {
  DeterministicFixtureTransport,
} from '../src/cli/fixture-transport.js';
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
  type JobClaim,
  type OperationDispatchContext,
  type RunnerTimers,
} from '../src/queue/index.js';
import type {
  CandidateHeader,
  MaterialCandidate,
  MaterialCatalog,
} from '../src/context/index.js';
import type {
  EvidenceUnit,
  SourceRecord,
} from '../src/sources/index.js';
import { TransportError } from '../src/providers/errors.js';
import { createCompatibleTransport } from '../src/providers/compatible.js';
import type { CouncilRouteSelection } from '../src/providers/selection.js';
import { analyzeDecision } from '../src/scoring/index.js';
import {
  OpeningRoundExecutor,
  type OpeningRoundDeps,
} from '../src/protocol/opening.js';

// ------------------------------------------------------------- fixtures

let nowIso = '2026-10-14T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

const SESSION_ID = 'sess-opening-1';
const PACK_VERSION = 'pack-test-1.0.0';
const PREFERENCE_MARKER = 'pref-marker-SECRET-024';

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

function fullCatalog(): ListCatalog {
  return new ListCatalog(SEAT_IDS.map((seatId) => seatCandidate(seatId)));
}

function briefFor(sessionId: string, catalogSeats: readonly SeatId[]): DecisionBrief {
  const manifest = [
    ...catalogSeats.map((seatId) => {
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
  ];
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-opening-1',
    session_id: sessionId,
    revision: 1,
    question: 'Should we pilot the revised offer before a broad launch?',
    facts: [
      {
        id: 'fact-1',
        statement: 'Current offer converts at a measured baseline.',
        evidence_ids: ['ev-case-1'],
      },
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
    options: [
      { id: 'A', label: 'Keep the current offer', kind: 'status_quo' },
      { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' },
      { id: 'C', label: 'Launch the revised offer broadly', kind: 'change' },
    ],
    relevance_weights: Object.fromEntries(
      SEAT_IDS.map((seatId, i) => [seatId, GOLDEN_WEIGHTS[i]]),
    ),
    critical_domains: [],
    evidence_manifest: manifest,
    private_preference_ref: PREFERENCE_MARKER,
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
  };
}

function storedSession(
  sessionId: string = SESSION_ID,
  catalogSeats: readonly SeatId[] = SEAT_IDS,
): StoredSession {
  const brief = briefFor(sessionId, catalogSeats);
  const spec: SessionSpec = {
    schema_version: 'wise-elders.session/v1',
    session_id: sessionId,
    mode: 'full',
    visibility: 'company',
    brief_revision: 1,
    brief_sha256: canonicalHash(brief),
    options: brief.options.map((o) => ({ ...o })),
    seat_ids: [...SEAT_IDS],
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
      mode: 'full',
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

// ---------------------------------------------------------- manual timers

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
      this.requests.filter((r) => r.seat_id === request.seat_id).length;
    if (this.script) return this.script(request, callIndexForSeat);
    return this.fixture.generate(request);
  }
  forSeat(seatId: SeatId): TransportRequest[] {
    return this.requests.filter((r) => r.seat_id === seatId);
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

interface Setup {
  ctx: Composition;
  session: StoredSession;
  envelope: AuthorizationEnvelope;
  worker: AuthorizationEnvelope;
  grantId: string;
  snapshot: PinnedRouteSnapshot;
  executor: OpeningRoundExecutor;
  runner: DurableJobRunner;
}

function setup(
  label: string,
  options: {
    catalogSeats?: readonly SeatId[];
    transport?: RecordingTransport;
    deps?: Partial<OpeningRoundDeps>;
    executor?: OpeningRoundExecutor;
  } = {},
): Setup {
  nowIso = '2026-10-14T12:00:00.000Z';
  const dbPath = join(mkdtempSync(join(tmpdir(), `cwe024-${label}-`)), 'council.db');
  const ctx = compose(dbPath);
  const catalogSeats = options.catalogSeats ?? SEAT_IDS;
  const session = storedSession(SESSION_ID, catalogSeats);
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
  for (const to of ['READY', 'QUEUED', 'PREPARING', 'ROUND_1'] as const) {
    ctx.repositories.transitionState(envelope, SESSION_ID, to, version);
    version += 1;
  }
  const transport = options.transport ?? new RecordingTransport();
  const executor = options.executor ?? new OpeningRoundExecutor({
    catalog: new ListCatalog(catalogSeats.map((seatId) => seatCandidate(seatId))),
    resolvePrincipal: () => principal(),
    resolveTransport: () => transport,
    routeBudget: () => ({
      context_limit_bytes: 1_000_000,
      response_schema_bytes: 2_000,
      output_reserve_bytes: 8_000,
    }),
    ...options.deps,
  });
  const runner = new DurableJobRunner({
    db: ctx.db,
    repositories: ctx.repositories,
    jobs: ctx.jobs,
    budget: ctx.budget,
    admission: ctx.admission,
    grants: ctx.grants,
    clock,
    ids,
    executor,
    timers: new ManualTimers(),
  });
  return {
    ctx,
    session,
    envelope,
    worker,
    grantId: grant.grant_id,
    snapshot,
    executor,
    runner,
  };
}

function enqueueSeat(s: Setup, seatId: SeatId, inputOverride?: string): void {
  const planned = s.executor.planSeat(s.session, s.snapshot, seatId);
  assert.equal(planned.status, 'planned', `seat ${seatId} must plan`);
  if (planned.status !== 'planned') return;
  s.runner.enqueueOperation(s.worker, {
    session_id: SESSION_ID,
    phase_job_key: `round-1:${seatId}`,
    seat_id: seatId,
    input_sha256: inputOverride ?? planned.plan.input_manifest_sha256,
    descriptor: {
      kind: 'provider_request',
      purpose: 'council_run',
      grant_id: s.grantId,
      estimate_minor: 100,
      currency: 'USD',
      round: 1,
      pack_version: planned.plan.pack_version,
    },
    route_snapshot: s.snapshot,
  });
}

async function runSeat(s: Setup, seatId: SeatId, workerId = 'worker-1') {
  const claim = s.runner.claimNextOperation(s.worker, SESSION_ID, workerId);
  assert.ok(claim, `a claim must exist for ${seatId}`);
  assert.equal(claim.seat_id, seatId);
  return s.runner.executeClaimedOperation(s.worker, claim);
}

async function runAllSeats(s: Setup) {
  const outcomes = new Map<SeatId, Awaited<ReturnType<typeof runSeat>>>();
  for (const seatId of SEAT_IDS) {
    enqueueSeat(s, seatId);
  }
  for (const seatId of SEAT_IDS) {
    outcomes.set(seatId, await runSeat(s, seatId));
  }
  return outcomes;
}

function authorOf(card: unknown): Record<string, unknown> {
  const { host: _host, ...author } = card as Record<string, unknown>;
  return author;
}

// ------------------------------------------------------------------ tests

test('planning: per-seat manifests are deterministic, distinct, and bound to context and route', () => {
  const s = setup('planning');
  const plans = s.executor.planOpeningRound(s.session, s.snapshot);
  assert.equal(plans.size, 9);
  const manifests = new Set<string>();
  for (const seatId of SEAT_IDS) {
    const result = plans.get(seatId);
    assert.equal(result?.status, 'planned', `${seatId} plans`);
    if (result?.status !== 'planned') continue;
    manifests.add(result.plan.input_manifest_sha256);
    assert.deepEqual(result.plan.item_evidence_ids, [`ev-${seatId}`]);
    // Determinism: planning again yields the identical identity.
    const again = s.executor.planSeat(s.session, s.snapshot, seatId);
    assert.deepEqual(again, result);
  }
  assert.equal(manifests.size, 9, 'every seat has a distinct input manifest');
});

test('T018 + T037 + golden path: a full independent Round 1 commits nine cards that reproduce the Section 32.2 scoring', async () => {
  const transport = new RecordingTransport();
  const s = setup('golden', { transport });
  const outcomes = await runAllSeats(s);
  for (const seatId of SEAT_IDS) {
    assert.equal(outcomes.get(seatId)?.status, 'committed', `${seatId} commits`);
  }

  // T018, executed: inspect what each provider request actually carried.
  assert.equal(transport.requests.length, 9, 'exactly one dispatch per seat');
  const seenManifests = new Set<string>();
  for (const request of transport.requests) {
    const seatId = request.seat_id as SeatId;
    const input = request.input as {
      context: { operation: string; preference_excluded: boolean; items: unknown[] };
      brief: Record<string, unknown>;
      input_manifest_sha256: string;
    };
    const wire = JSON.stringify(request.input);
    assert.ok(
      wire.includes(seatMarker(seatId)),
      `${seatId} request carries its own material`,
    );
    for (const other of SEAT_IDS) {
      if (other !== seatId) {
        assert.ok(
          !wire.includes(seatMarker(other)),
          `${seatId} request must not contain ${other} material`,
        );
      }
    }
    assert.ok(
      !wire.includes(PREFERENCE_MARKER),
      'the private preference reference never reaches a provider',
    );
    assert.ok(
      !('private_preference_ref' in input.brief),
      'the Round 1 brief view omits private_preference_ref entirely',
    );
    assert.equal(input.context.operation, 'round_1_opening');
    assert.equal(input.context.preference_excluded, true);
    assert.equal(input.context.items.length, 1, 'exactly this seat\'s items');
    seenManifests.add(input.input_manifest_sha256);
  }
  assert.equal(seenManifests.size, 9, 'T037: distinct manifest per seat');

  // T037: committed cards echo the exact manifest their job owned.
  const cards = s.ctx.repositories.listCards(s.worker, SESSION_ID);
  assert.equal(cards.length, 9);
  for (const card of cards) {
    if (card.card_kind !== 'advisor') assert.fail('opening cards are advisor cards');
    const planned = s.executor.planSeat(s.session, s.snapshot, card.seat_id);
    assert.equal(planned.status, 'planned');
    if (planned.status === 'planned') {
      assert.equal(card.input_manifest_sha256, planned.plan.input_manifest_sha256);
    }
    assert.equal(card.round, 1);
    assert.equal(card.pack_version, PACK_VERSION);
    assert.equal(card.host.source_status, 'unverified');
  }

  // The golden path: the executor's cards feed CWE-026 unchanged.
  const scores = cards.flatMap((card) =>
    card.card_kind === 'advisor'
      ? card.option_scores.map((score) => ({
          option_id: score.option_id,
          seat_id: card.seat_id,
          score: score.score,
        }))
      : [],
  );
  const analysis = analyzeDecision({
    options: s.session.brief.options.map((o) => ({ ...o })),
    active_seat_ids: [...SEAT_IDS],
    weights: Object.fromEntries(SEAT_IDS.map((seatId, i) => [seatId, GOLDEN_WEIGHTS[i]])),
    scores,
  });
  const byId = new Map(analysis.options.map((o) => [o.option_id, o]));
  for (const optionId of ['A', 'B', 'C'] as const) {
    const expected = GOLDEN_EXPECTED[optionId];
    const mine = byId.get(optionId);
    assert.ok(mine);
    assert.equal(mine.weighted_sum, expected.weighted_sum, `${optionId} sum`);
    assert.equal(mine.denominator, expected.denominator, `${optionId} denominator`);
    assert.equal(mine.score, expected.score, `${optionId} score`);
    assert.equal(mine.display_score, expected.display_score, `${optionId} display`);
  }
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  assert.equal(budget.consumed.provider_requests, 9);
  assert.equal(budget.consumed.output_repairs, 0);
  assert.equal(budget.consumed.transport_retries, 0);
});

test('T018: serial and concurrent executions produce identical opening cards', async () => {
  const serialTransport = new RecordingTransport();
  const serial = setup('serial', { transport: serialTransport });
  await runAllSeats(serial);

  // The architecture's parallel unit is the session: CWE-027 fences a
  // session to one fencing generation at a time (a newer claim fences
  // an in-flight claim's commit, T052), so seats within a session run
  // under rolling sequential claims in every shape, and concurrency
  // happens across sessions. The concurrent shape here therefore runs
  // TWO sessions at once through ONE shared executor instance, their
  // claim/execute chains interleaved, and requires the outputs to be
  // identical to the serial run: the executor's cards depend only on
  // their inputs, never on execution order or timing.
  const sharedTransport = new RecordingTransport();
  const sharedExecutor = new OpeningRoundExecutor({
    catalog: fullCatalog(),
    resolvePrincipal: () => principal(),
    resolveTransport: () => sharedTransport,
    routeBudget: () => ({
      context_limit_bytes: 1_000_000,
      response_schema_bytes: 2_000,
      output_reserve_bytes: 8_000,
    }),
  });
  const a = setup('conc-a', { transport: sharedTransport, executor: sharedExecutor });
  const b = setup('conc-b', { transport: sharedTransport, executor: sharedExecutor });
  await Promise.all([runAllSeats(a), runAllSeats(b)]);

  const authorMap = (s: Setup) =>
    new Map(
      s.ctx.repositories
        .listCards(s.worker, SESSION_ID)
        .map((card) => [card.seat_id, authorOf(card)]),
    );
  const serialCards = authorMap(serial);
  assert.equal(serialCards.size, 9);
  for (const [label, concurrent] of [['a', a], ['b', b]] as const) {
    const cards = authorMap(concurrent);
    assert.equal(cards.size, 9, `concurrent session ${label} commits nine cards`);
    for (const seatId of SEAT_IDS) {
      assert.deepEqual(
        cards.get(seatId),
        serialCards.get(seatId),
        `${seatId}: concurrent card equals serial card`,
      );
    }
  }
  // The shared transport saw both sessions' full rounds, and no
  // request ever carried another session's identity.
  assert.equal(sharedTransport.requests.length, 18);
});

test('repair: an invalid card triggers exactly one bounded repair, a distinct admitted operation', async () => {
  const transport = new RecordingTransport(async (request, callIndex) => {
    if (request.seat_id === 'simon-sinek' && callIndex === 1) {
      // A card claiming another seat: canonical shape, wrong identity.
      return fixtureCard(request, (card) => {
        card.seat_id = 'td-jakes';
      });
    }
    return fixtureCard(request);
  });
  const s = setup('repair', { transport });
  enqueueSeat(s, 'simon-sinek');
  const outcome = await runSeat(s, 'simon-sinek');
  assert.equal(outcome.status, 'committed');

  const calls = transport.forSeat('simon-sinek');
  assert.equal(calls.length, 2, 'initial dispatch plus one repair');
  assert.ok(
    calls[1].system.includes('Your previous output failed validation'),
    'the repair dispatch carries the validation issues',
  );
  assert.ok(
    calls[1].system.includes('seat_id'),
    'the repair issues name the identity failure',
  );
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  assert.equal(budget.consumed.provider_requests, 2);
  assert.equal(budget.consumed.output_repairs, 1);
  assert.equal(budget.consumed.transport_retries, 0);
  const cards = s.ctx.repositories.listCards(s.worker, SESSION_ID);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].seat_id, 'simon-sinek');
});

test('T045 negative half: an invalid card twice ends output_validation_failed, never an abstention', async () => {
  const transport = new RecordingTransport(async (request) =>
    fixtureCard(request, (card) => {
      card.seat_id = 'td-jakes';
    }),
  );
  const s = setup('invalid-twice', { transport });
  enqueueSeat(s, 'simon-sinek');
  const outcome = await runSeat(s, 'simon-sinek');
  assert.equal(outcome.status, 'failed');
  assert.equal(outcome.reason, 'output_validation_failed');
  assert.equal(transport.forSeat('simon-sinek').length, 2, 'one repair, no more');
  assert.equal(
    s.ctx.repositories.listCards(s.worker, SESSION_ID).length,
    0,
    'no card is stored and no abstention is fabricated',
  );
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  assert.equal(budget.consumed.provider_requests, 2);
  assert.equal(budget.consumed.output_repairs, 1);
});

test('retry: a retryable transport failure admits one distinct transport retry, then commits', async () => {
  const transport = new RecordingTransport(async (request, callIndex) => {
    if (request.seat_id === 'simon-sinek' && callIndex === 1) {
      throw new TransportError('TRANSPORT_NETWORK_FAILED', 'connection reset', {
        retryable: true,
      });
    }
    return fixtureCard(request);
  });
  const s = setup('retry', { transport });
  enqueueSeat(s, 'simon-sinek');
  const outcome = await runSeat(s, 'simon-sinek');
  assert.equal(outcome.status, 'committed');
  assert.equal(transport.forSeat('simon-sinek').length, 2, 'two dispatches happened');
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  // Ledger semantics (CWE-028): the not-accepted attempt's reservation
  // is RELEASED, not consumed, so consumed provider requests count the
  // one accepted dispatch; the retry is its own consumed kind.
  assert.equal(budget.consumed.provider_requests, 1);
  assert.equal(budget.consumed.transport_retries, 1);
  assert.equal(budget.consumed.output_repairs, 0);
});

test('T045 negative half: an unresolved provider submission is provider_completion_unknown, never replayed, never an abstention', async () => {
  const transport = new RecordingTransport(async () => {
    throw new TransportError(
      'TRANSPORT_SUBMITTED_UNRESOLVED',
      'submitted; completion unresolved',
      { unknownCompletion: true },
    );
  });
  const s = setup('unknown', { transport });
  enqueueSeat(s, 'simon-sinek');
  const outcome = await runSeat(s, 'simon-sinek');
  assert.equal(outcome.status, 'provider_completion_unknown');
  assert.equal(transport.requests.length, 1, 'the submission is never replayed');
  assert.equal(s.ctx.repositories.listCards(s.worker, SESSION_ID).length, 0);
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  assert.equal(budget.unknown, 1, 'the reservation is retained at estimate');
});

test('definite rejection: a non-retryable transport failure settles as transport_rejected, distinct from repair and retry', async () => {
  const transport = new RecordingTransport(async () => {
    throw new TransportError('TRANSPORT_AUTH_FAILED', 'credential rejected', {});
  });
  const s = setup('rejected', { transport });
  enqueueSeat(s, 'simon-sinek');
  const outcome = await runSeat(s, 'simon-sinek');
  assert.equal(outcome.status, 'failed');
  assert.equal(outcome.reason, 'transport_rejected');
  assert.equal(transport.requests.length, 1);
  assert.equal(s.ctx.repositories.listCards(s.worker, SESSION_ID).length, 0);
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  assert.equal(budget.consumed.provider_requests, 1);
  assert.equal(budget.consumed.output_repairs, 0);
  assert.equal(budget.consumed.transport_retries, 0);
});

test('drift: inputs that changed after enqueue are refused before any provider call', async () => {
  const transport = new RecordingTransport();
  const s = setup('drift', { transport });
  enqueueSeat(s, 'simon-sinek', canonicalHash({ drifted: 'inputs' }));
  const outcome = await runSeat(s, 'simon-sinek');
  assert.equal(outcome.status, 'failed');
  assert.equal(
    transport.requests.length,
    0,
    'no provider call is made for drifted inputs',
  );
  assert.equal(s.ctx.repositories.listCards(s.worker, SESSION_ID).length, 0);
  const budget = s.ctx.budget.snapshot(s.worker, SESSION_ID, s.grantId);
  assert.equal(budget.consumed.provider_requests, 1, 'the refused dispatch is recorded once');
  assert.equal(
    budget.money.committed_actual_minor,
    0,
    'the refusal settles at zero actual charge: no provider call happened',
  );
});

test('context too small: the typed readiness outcome refuses dispatch with zero provider calls', async () => {
  const transport = new RecordingTransport();
  const s = setup('too-small', {
    transport,
    deps: {
      // A real but tiny budget: the reserves fit, the minimum context
      // (brief plus the seat's first item) does not, which is exactly
      // the Section 9.5 CONTEXT_TOO_SMALL case. The limit covers the
      // system text with its card-contract prose (about 7.5 KB).
      routeBudget: () => ({
        context_limit_bytes: 9500,
        response_schema_bytes: 500,
        output_reserve_bytes: 500,
      }),
    },
  });
  // Planning reports the same typed outcome the dispatch will honor.
  const planned = s.executor.planSeat(s.session, s.snapshot, 'simon-sinek');
  assert.equal(planned.status, 'context_too_small');
  if (planned.status === 'context_too_small') {
    assert.equal(planned.readiness, 'CONTEXT_TOO_SMALL');
    assert.ok(planned.minimum_required_bytes > planned.available_bytes);
  }
  // Enqueue under the plan a full-size route would have produced, by
  // planning with a second executor over the same inputs: the job is
  // real; the composed route budget at dispatch time is what refuses.
  const planner = new OpeningRoundExecutor({
    catalog: fullCatalog(),
    resolvePrincipal: () => principal(),
    resolveTransport: () => transport,
    routeBudget: () => ({
      context_limit_bytes: 1_000_000,
      response_schema_bytes: 2_000,
      output_reserve_bytes: 8_000,
    }),
  });
  const plan = planner.planSeat(s.session, s.snapshot, 'simon-sinek');
  assert.equal(plan.status, 'planned');
  if (plan.status !== 'planned') return;
  s.runner.enqueueOperation(s.worker, {
    session_id: SESSION_ID,
    phase_job_key: 'round-1:simon-sinek',
    seat_id: 'simon-sinek',
    input_sha256: plan.plan.input_manifest_sha256,
    descriptor: {
      kind: 'provider_request',
      purpose: 'council_run',
      grant_id: s.grantId,
      estimate_minor: 100,
      currency: 'USD',
      round: 1,
      pack_version: plan.plan.pack_version,
    },
    route_snapshot: s.snapshot,
  });
  const outcome = await runSeat(s, 'simon-sinek');
  assert.equal(outcome.status, 'failed');
  assert.equal(transport.requests.length, 0);
  assert.equal(s.ctx.repositories.listCards(s.worker, SESSION_ID).length, 0);
});

test('no transport composed for the pinned route: honest refusal, zero provider calls, no substitution', async () => {
  const s = setup('no-transport', {
    transport: new RecordingTransport(),
    deps: { resolveTransport: () => null },
  });
  enqueueSeat(s, 'simon-sinek');
  const outcome = await runSeat(s, 'simon-sinek');
  assert.equal(outcome.status, 'failed');
  assert.equal(s.ctx.repositories.listCards(s.worker, SESSION_ID).length, 0);
});

test('absent seat: a seat with no pack material returns an honest model-authored abstention; the executor fabricates nothing', async () => {
  const transport = new RecordingTransport(async (request) => {
    if (request.seat_id !== 'les-brown') return fixtureCard(request);
    const input = request.input as {
      input_manifest_sha256: string;
      pack_version: string;
      brief: DecisionBrief;
    };
    const card = {
      schema_version: 'wise-elders.card/v1',
      card_kind: 'advisor',
      session_id: SESSION_ID,
      brief_revision: 1,
      round: 1,
      seat_id: 'les-brown',
      input_manifest_sha256: input.input_manifest_sha256,
      pack_version: input.pack_version,
      stance: 'abstain',
      preferred_option_id: null,
      option_scores: input.brief.options.map((o) => ({
        option_id: o.id,
        score: null,
        rationale:
          'Abstaining: no source material for this seat exists in the current pack, so no grounded score can be given.',
        evidence_ids: [],
      })),
      framework_applications: [],
      decisive_arguments: [],
      strongest_objection:
        'This seat holds no verified or bibliographic material in the current pack and cannot ground a position.',
      conditions: [],
      critical_unknowns: ['Whether source material for this seat will be obtained.'],
      change_my_mind: 'Lawfully obtained source material for this seat, admitted to the pack.',
      challenges_answered: [],
      quotes: [],
      evidence_strength: 'low',
      minority_position: null,
    };
    return {
      text: JSON.stringify(card),
      provider_request_id: 'abstain-req-1',
      reported_model_id: 'fixture-abstention',
      usage: { input_tokens: null, output_tokens: null },
    };
  });
  const seatsWithMaterial = SEAT_IDS.filter((seatId) => seatId !== 'les-brown');
  const s = setup('absent', {
    transport,
    catalogSeats: seatsWithMaterial,
  });
  // The absent seat still plans: its context is the brief alone.
  const planned = s.executor.planSeat(s.session, s.snapshot, 'les-brown');
  assert.equal(planned.status, 'planned');
  if (planned.status === 'planned') {
    assert.deepEqual(planned.plan.item_evidence_ids, []);
  }
  enqueueSeat(s, 'les-brown');
  const outcome = await runSeat(s, 'les-brown');
  assert.equal(outcome.status, 'committed');
  const cards = s.ctx.repositories.listCards(s.worker, SESSION_ID);
  assert.equal(cards.length, 1);
  const card = cards[0];
  if (card.card_kind !== 'advisor') assert.fail('advisor card expected');
  assert.equal(card.stance, 'abstain');
  assert.equal(card.host.source_status, 'not_applicable');
  assert.ok(card.option_scores.every((score) => score.score === null));
});

// ------------------------------------------------- direct port-level tests

function dispatchCtx(
  s: Setup,
  seatId: SeatId,
  inputSha: string,
): OperationDispatchContext {
  const claim = {
    job: {
      id: 'job-direct',
      session_id: SESSION_ID,
      attempt: 1,
      phase_job_key: `round-1:${seatId}`,
      input_sha256: inputSha,
      brief_revision: 1,
    },
    operation_id: canonicalHash({ direct: seatId }),
    seat_id: seatId,
    worker_id: 'worker-direct',
    job_lease_epoch: 1,
    session_lease_epoch: 1,
    cancel_generation: 0,
    state_version_at_claim: 4,
    descriptor: {
      kind: 'provider_request',
      purpose: 'council_run',
      grant_id: s.grantId,
      estimate_minor: 100,
      currency: 'USD',
      round: 1,
      pack_version: PACK_VERSION,
    },
    route_snapshot: s.snapshot,
  } as unknown as JobClaim;
  return {
    session: s.session,
    claim,
    dispatch_operation_id: claim.operation_id,
    attempt_kind: 'initial',
    repair_issues: [],
  };
}

test('port level: dispatch returns a valid unstamped author payload and validateCard accepts it', async () => {
  const transport = new RecordingTransport();
  const s = setup('port-level', { transport });
  const planned = s.executor.planSeat(s.session, s.snapshot, 'td-jakes');
  assert.equal(planned.status, 'planned');
  if (planned.status !== 'planned') return;
  const ctx = dispatchCtx(s, 'td-jakes', planned.plan.input_manifest_sha256);
  const result = await s.executor.dispatch(ctx);
  assert.equal(result.provider_request_id, 'fixture-req-1');
  assert.equal(result.source_status, 'unverified');
  const author = result.author as Record<string, unknown>;
  assert.equal(author.seat_id, 'td-jakes');
  assert.equal(author.input_manifest_sha256, planned.plan.input_manifest_sha256);
  const stamped = {
    ...author,
    host: {
      scope: { ...SESSION_SCOPE },
      operation_id: ctx.claim.operation_id,
      route_id: 'route-a',
      session_id: SESSION_ID,
      stamped_at: nowIso,
      source_status: 'unverified' as const,
    },
  };
  assert.deepEqual(
    s.executor.validateCard(ctx, stamped as never),
    [],
    'a faithful opening card passes deep validation',
  );
});

test('port level: validateCard rejects cross-seat evidence, unverified quotes, wrong-seat lenses, and round 1 challenge answers', async () => {
  const transport = new RecordingTransport();
  const s = setup('validate-negatives', { transport });
  const planned = s.executor.planSeat(s.session, s.snapshot, 'simon-sinek');
  assert.equal(planned.status, 'planned');
  if (planned.status !== 'planned') return;
  const ctx = dispatchCtx(s, 'simon-sinek', planned.plan.input_manifest_sha256);
  const base = await fixtureCard({
    purpose: 'advisor',
    session_id: SESSION_ID,
    seat_id: 'simon-sinek',
    round: 1,
    route_id: 'route-a',
    model_policy: s.session.spec.model_policy,
    system: 'test',
    input: {
      brief: s.session.brief,
      input_manifest_sha256: planned.plan.input_manifest_sha256,
      pack_version: PACK_VERSION,
    },
  });
  const baseCard = JSON.parse(base.text) as Record<string, unknown>;
  const host = {
    scope: { ...SESSION_SCOPE },
    operation_id: ctx.claim.operation_id,
    route_id: 'route-a',
    session_id: SESSION_ID,
    stamped_at: nowIso,
    source_status: 'unverified' as const,
  };
  const validate = (mutate: (card: Record<string, unknown>) => void): string[] => {
    const card = JSON.parse(JSON.stringify(baseCard)) as Record<string, unknown>;
    mutate(card);
    return s.executor.validateCard(ctx, { ...card, host } as never);
  };

  // The fixture card cites the brief's first manifest entry in its
  // framework application; for this seat that entry is another seat's
  // material unless it is the seat's own item.
  const crossSeat = validate((card) => {
    const apps = card.framework_applications as Array<Record<string, unknown>>;
    apps[0].source_evidence_ids = ['ev-td-jakes'];
  });
  assert.ok(
    crossSeat.some((i) => i.includes('was not in this seat\'s assembled opening context')),
    `cross-seat evidence is rejected: ${crossSeat.join(' | ')}`,
  );

  const quoted = validate((card) => {
    card.quotes = [
      {
        quote_id: 'quote-1',
        text: 'An invented quotation.',
        evidence_id: 'ev-simon-sinek',
        locator: 'section:Part 1',
        verification_status: 'candidate',
      },
    ];
  });
  assert.ok(
    quoted.some((i) => i.includes('not backed by verified material')),
    `unverified quotes are rejected: ${quoted.join(' | ')}`,
  );

  const lensed = validate((card) => {
    card.lenses_used = ['instinct'];
  });
  assert.ok(
    lensed.some((i) => i.includes('LENS_ON_WRONG_SEAT')),
    `lenses on the wrong seat are rejected: ${lensed.join(' | ')}`,
  );

  const challenged = validate((card) => {
    card.challenges_answered = ['crux-1'];
  });
  assert.ok(
    challenged.some((i) => i.includes('answers no challenges')),
    `round 1 challenge answers are rejected: ${challenged.join(' | ')}`,
  );

  const wrongPack = validate((card) => {
    card.pack_version = 'pack-other-9.9.9';
  });
  assert.ok(
    wrongPack.some((i) => i.includes('pack_version')),
    `a foreign pack version is rejected: ${wrongPack.join(' | ')}`,
  );
});

test('port level: dispatch refuses a non-round-1 descriptor and a missing transport without calling the provider', async () => {
  const transport = new RecordingTransport();
  const s = setup('refusals', { transport });
  const planned = s.executor.planSeat(s.session, s.snapshot, 'simon-sinek');
  assert.equal(planned.status, 'planned');
  if (planned.status !== 'planned') return;
  const ctx = dispatchCtx(s, 'simon-sinek', planned.plan.input_manifest_sha256);
  const roundTwo = {
    ...ctx,
    claim: {
      ...ctx.claim,
      descriptor: { ...ctx.claim.descriptor, round: 2 },
    } as JobClaim,
  };
  await assert.rejects(
    () => s.executor.dispatch(roundTwo),
    (error: unknown) =>
      error instanceof TransportDispatchError &&
      error.retryable === false &&
      error.unknownCompletion === false &&
      error.actual_minor === 0,
  );
  assert.equal(transport.requests.length, 0);
});

test('loopback: a full Round 1 runs through CWE-009\'s real compatible transport over HTTP', async () => {
  // A loopback provider that answers with the deterministic fixture
  // card for whichever seat the request's own context names. The wire
  // bytes are captured so independence is asserted on what actually
  // left the process, not only on the port surface.
  const hits: Array<{ body: string }> = [];
  const fixture = new DeterministicFixtureTransport();
  const server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (c) => chunks.push(c as Buffer));
    req.on('end', () => {
      void (async () => {
        const body = Buffer.concat(chunks).toString('utf8');
        hits.push({ body });
        const wire = JSON.parse(body) as {
          messages: Array<{ role: string; content: string }>;
        };
        const input = JSON.parse(wire.messages[1].content) as {
          context: { items: Array<{ seat_id: SeatId }> };
          brief: DecisionBrief;
          input_manifest_sha256: string;
          pack_version: string;
        };
        const seatId = input.context.items[0]?.seat_id ?? 'les-brown';
        const cardResponse = await fixture.generate({
          purpose: 'advisor',
          session_id: SESSION_ID,
          seat_id: seatId,
          round: 1,
          route_id: 'route-a',
          model_policy: {
            selection: 'explicit',
            route_id: 'route-a',
            requested_model_id: 'model-selected-by-client',
            reasoning_preference: null,
            fallback_policy: 'none',
          },
          system: 'loopback',
          input: {
            brief: input.brief,
            input_manifest_sha256: input.input_manifest_sha256,
            pack_version: input.pack_version,
          },
        });
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(
          JSON.stringify({
            id: 'loopback-req-1',
            model: 'model-selected-by-client',
            choices: [
              {
                message: { role: 'assistant', content: cardResponse.text },
                finish_reason: 'stop',
              },
            ],
            usage: { prompt_tokens: 11, completion_tokens: 7 },
          }),
        );
      })();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = (server.address() as AddressInfo).port;
  try {
    const selection: CouncilRouteSelection = {
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
        capabilities: ['text_generation'],
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
    const loopbackTransport = createCompatibleTransport({
      selection,
      baseUrl: `http://127.0.0.1:${port}/v1`,
      // Test-only fixture credential, resolved in-flight and never
      // recorded, exactly as the CWE-009 binding contract requires.
      credentialResolver: async () => 'loopback-test-credential',
      sleep: async () => {},
      random: () => 0,
    });
    const s = setup('loopback', {
      deps: { resolveTransport: () => loopbackTransport },
    });
    const outcomes = await runAllSeats(s);
    for (const seatId of SEAT_IDS) {
      assert.equal(outcomes.get(seatId)?.status, 'committed', `${seatId} commits over loopback`);
    }
    assert.equal(hits.length, 9, 'nine HTTP dispatches, one per seat');
    for (const hit of hits) {
      const wire = JSON.parse(hit.body) as {
        model: string;
        messages: Array<{ role: string; content: string }>;
      };
      assert.equal(wire.model, 'model-selected-by-client');
      const userContent = wire.messages[1].content;
      const input = JSON.parse(userContent) as {
        context: { items: Array<{ seat_id: SeatId }> };
      };
      const seatId = input.context.items[0].seat_id;
      assert.ok(userContent.includes(seatMarker(seatId)), `${seatId} wire payload carries its own material`);
      for (const other of SEAT_IDS) {
        if (other !== seatId) {
          assert.ok(
            !userContent.includes(seatMarker(other)),
            `${seatId} wire payload must not contain ${other} material`,
          );
        }
      }
      assert.ok(!userContent.includes(PREFERENCE_MARKER), 'no private preference on the wire');
      assert.ok(
        !hit.body.includes('loopback-test-credential'),
        'the credential value never appears in the recorded request body',
      );
    }
    assert.equal(s.ctx.repositories.listCards(s.worker, SESSION_ID).length, 9);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
