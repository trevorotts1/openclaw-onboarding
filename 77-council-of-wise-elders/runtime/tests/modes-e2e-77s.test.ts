/**
 * W77S-MODES integration: one convene per council size, through the
 * service driver, over the real protocol composition, with a fake
 * transport and no network.
 *
 * This is the seam test for the four merged lanes: the driver chooses
 * the mode's panel and parallel limit (lane D), runSession claims waves
 * under one lease epoch (lane C) and drives the round loop (lane B), and
 * the assembly step completes with a verdict and ratification not_required.
 *
 * Asserts per mode: the seat count, the rounds actually run, the provider
 * requests counted (transport and budget agree), a completed verdict with
 * ratification not_required, and peak transport concurrency equal to the
 * parallel limit (3 on an Ollama $20 plan, 9 on OpenRouter).
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import type { TrustedPrincipal } from '../src/authorization/index.js';
import type { PinnedRouteSnapshot } from '../src/budgets/index.js';
import type {
  ModelTransport,
  StoredSession,
  TransportRequest,
  TransportResponse,
} from '../src/cli/host-ports.js';
import type {
  CandidateHeader,
  MaterialCandidate,
  MaterialCatalog,
} from '../src/context/index.js';
import {
  canonicalHash,
  GOLDEN_WEIGHTS,
  SEAT_IDS,
  type DecisionBrief,
  type RunCeilings,
  type ScopeFields,
  type SeatId,
  type SessionMode,
  type SessionSpec,
} from '../src/contracts/index.js';
import type { EvidenceUnit, SourceRecord } from '../src/sources/index.js';
import type { RunnerTimers } from '../src/queue/index.js';
import { TransportDispatchError } from '../src/queue/index.js';
import { COUNCIL_SCHEMA_SQL } from '../src/persistence/index.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';
import {
  composeDeliberationService,
  type DeliberationService,
  type RunSessionResult,
} from '../src/protocol/composition.js';
import { validateVerdictForPublication } from '../src/protocol/verdict.js';
import { CONVENING_SETTINGS } from '../src/service/composition.js';
import {
  createCouncilDriver,
  type ResolvedSessionRoute,
} from '../src/service/driver.js';

// ------------------------------------------------------------- fixtures

const clock = { nowUtc: () => '2026-10-25T12:00:00.000Z' };
let idCounter = 0;
const ids = { newId: () => `e2e-${(idCounter += 1).toString().padStart(5, '0')}` };

const SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'install-a',
  owner_subject: 'owner-1',
};
const COMPANY_SCOPE: ScopeFields = { ...SCOPE, owner_subject: null };

const principal: TrustedPrincipal = {
  tenant_id: SCOPE.tenant_id,
  company_id: SCOPE.company_id,
  installation_id: SCOPE.installation_id,
  subject: 'owner-1',
  channel: 'local_owner',
  support_access: false,
};

const OPTIONS = [
  { id: 'A', label: 'Keep the current offer', kind: 'status_quo' as const },
  { id: 'B', label: 'Pilot the revised offer', kind: 'bounded_test' as const },
  { id: 'C', label: 'Launch the revised offer broadly', kind: 'change' as const },
];

const LIGHT_PANEL: readonly SeatId[] = SEAT_IDS.slice(0, 3);

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
    retrieved_at: '2026-10-25T00:00:00Z',
    canonical_url: null,
    private_asset_id: null,
    content_sha256: canonicalHash({ record: seatId }),
    rights_status: 'reference_only',
    allowed_scope: 'shared_pack',
    locators: [{ kind: 'section', value: 'Part 1' }],
    quality: 'unverified',
  };
}

function seatCandidate(seatId: SeatId): MaterialCandidate {
  const src = seatSource(seatId);
  const unit: EvidenceUnit = {
    evidence_id: `ev-${seatId}`,
    source_id: src.source_id,
    source_version: src.content_sha256,
    locator: { kind: 'section', value: 'Part 1, Chapter 1' },
    kind: 'concept',
    mark: 'direct_teaching',
    original_speaker: seatId,
    excerpt: null,
    paraphrase: `SEAT-MATERIAL-${seatId}: the one teaching paraphrase held for this seat.`,
    claim_ids: [`claim-${seatId}-1`],
    seat_id: seatId,
  };
  const header: CandidateHeader = {
    evidence_id: unit.evidence_id,
    seat_id: seatId,
    scope: COMPANY_SCOPE,
    visibility: 'company',
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

function briefFor(panel: readonly SeatId[]): DecisionBrief {
  return {
    schema_version: 'wise-elders.brief/v1',
    brief_id: 'brief-e2e',
    session_id: 'sess-e2e',
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
    private_preference_ref: null,
    created_at: '2026-10-25T02:00:00Z',
    display_timezone: 'America/New_York',
  };
}

function routeSnapshot(routeId: string, providerSlug: string): PinnedRouteSnapshot {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId,
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug,
    requestedRoute: routeId,
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
      tenantId: SCOPE.tenant_id,
      companyId: SCOPE.company_id,
      installationId: SCOPE.installation_id,
      ownerSubject: SCOPE.owner_subject as string,
    },
    createdAt: '2026-10-25T12:00:00.000Z',
  };
}

/**
 * No runner timers in this test: `delay` never resolves, so the
 * provider-deadline race is won by the transport (the dispatch settles
 * first) and the round wait loop is never needed because no competing
 * worker holds this session's jobs.
 */
class FrozenTimers implements RunnerTimers {
  every(_ms: number, _fn: () => void): () => void {
    return () => {};
  }
  delay(_ms: number): Promise<void> {
    return new Promise(() => {});
  }
}

// ------------------------------------------------------------ transport

/**
 * Deterministic split panel: no consensus ever forms, so every mode runs
 * its maximum rounds. Records the peak number of concurrent generate()
 * calls; the short timer keeps every wave member in flight together.
 */
class ConcurrencyTransport implements ModelTransport {
  readonly requests: TransportRequest[] = [];
  private active = 0;
  peak = 0;

  async generate(request: TransportRequest): Promise<TransportResponse> {
    this.requests.push(request);
    this.active += 1;
    if (this.active > this.peak) this.peak = this.active;
    await new Promise((resolve) => setTimeout(resolve, 10));
    this.active -= 1;
    const seatId = request.seat_id as SeatId;
    const prefersA = SEAT_IDS.indexOf(seatId) < 4;
    const scores: Record<string, number> = {
      A: prefersA ? 9 : 5,
      B: prefersA ? 5 : 9,
      C: 3,
    };
    const input = request.input as {
      brief: { session_id: string; revision: number };
      input_manifest_sha256: string;
      pack_version: string;
      challenges_for_seat?: Array<{ crux_id: string }>;
    };
    const card: Record<string, unknown> = {
      schema_version: 'wise-elders.card/v1',
      session_id: input.brief.session_id,
      brief_revision: input.brief.revision,
      seat_id: seatId,
      input_manifest_sha256: input.input_manifest_sha256,
      pack_version: input.pack_version,
      card_kind: 'advisor',
      round: request.round ?? 1,
      stance: 'conditional',
      preferred_option_id: scores.A >= scores.B ? 'A' : 'B',
      option_scores: OPTIONS.map((option) => ({
        option_id: option.id,
        score: scores[option.id],
        rationale: `E2E round ${request.round} rationale from ${seatId} for ${option.id}.`,
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
      decisive_arguments: [`E2E decisive argument from ${seatId}.`],
      strongest_objection: 'E2E objection: retention evidence is not yet measured.',
      conditions: [],
      critical_unknowns: ['E2E unknown: measured pilot retention.'],
      change_my_mind: 'Measured evidence that the binding constraint no longer holds.',
      challenges_answered: (input.challenges_for_seat ?? []).map((c) => c.crux_id),
      quotes: [],
      evidence_strength: 'medium',
      minority_position: null,
    };
    return {
      text: JSON.stringify(card),
      provider_request_id: `e2e-${seatId}-${request.round}-${this.requests.length}`,
      reported_model_id: 'e2e-transport',
      usage: { input_tokens: null, output_tokens: null },
    };
  }
}

// ---------------------------------------------------------------- rig

interface Rig {
  transport: ConcurrencyTransport;
  fallbackTransport: ConcurrencyTransport;
  service: DeliberationService;
  settled: Array<{ id: string; result: RunSessionResult | { status: 'error'; code: string } }>;
  convene: (input: {
    mode: SessionMode;
    seat_ids?: SeatId[];
    ollama_plan?: '20' | '100';
    fallback_model?: string;
    /** Override the frozen brief (e.g. one carrying weights for every seat). */
    brief?: DecisionBrief;
  }) => Promise<{ session_id: string; seats: number; parallel_limit: number; request_cap: number }>;
  drain: () => Promise<void>;
}

const FALLBACK_ROUTE_ID = 'openrouter-configured';

function rig(
  route: { routeId: string; providerSlug: string },
  opts: {
    failingSeat?: SeatId;
    /** Several seats that fail on the primary route. */
    failingSeats?: readonly SeatId[];
    /** Restrict the `failingSeats` failures to one round (keeps the run under the cap). */
    failRound?: number;
  } = {},
): Rig {
  const dir = mkdtempSync(join(tmpdir(), 'w77s-e2e-'));
  const db = CouncilDatabase.open(join(dir, 'council.db'), {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const transport = new ConcurrencyTransport();
  const fallbackTransport = new ConcurrencyTransport();
  const fails = (request: TransportRequest): boolean => {
    const seatId = request.seat_id as SeatId;
    if (opts.failingSeat !== undefined && seatId === opts.failingSeat) return true;
    if (opts.failingSeats === undefined || !opts.failingSeats.includes(seatId)) return false;
    return opts.failRound === undefined || request.round === opts.failRound;
  };
  const hasFallback = opts.failingSeat !== undefined || opts.failingSeats !== undefined;
  const primary: ModelTransport = {
    generate: async (request) => {
      if (fails(request)) {
        transport.requests.push(request);
        throw new TransportDispatchError('rate limited by the local daemon', {
          retryable: true,
        });
      }
      return transport.generate(request);
    },
  };
  const service = composeDeliberationService({
    db,
    clock,
    ids,
    catalog: new ListCatalog(SEAT_IDS.map((seatId) => seatCandidate(seatId))),
    resolvePrincipal: () => principal,
    resolveTransport: (snapshot) =>
      hasFallback && snapshot.routeId === FALLBACK_ROUTE_ID ? fallbackTransport : primary,
    routeBudget: () => ({
      context_limit_bytes: 1_000_000,
      response_schema_bytes: 2_000,
      output_reserve_bytes: 8_000,
    }),
    timers: new FrozenTimers(),
    settings: CONVENING_SETTINGS,
  });
  const owner = envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write');
  const snapshot = routeSnapshot(route.routeId, route.providerSlug);
  const settled: Rig['settled'] = [];

  const resolved = (pinned: PinnedRouteSnapshot): ResolvedSessionRoute => ({
    snapshot: pinned,
    model_policy: {
      selection: 'explicit',
      route_id: pinned.routeId,
      requested_model_id: 'model-selected-by-client',
      reasoning_preference: null,
      fallback_policy: 'none',
    },
    model_label: 'model-selected-by-client',
    selection_source: 'explicit',
    harness: null,
  });

  // The driver resolves the primary route and, when a fallback model is
  // given on an Ollama primary, the OpenRouter fallback route.
  const resolveRoute = async (request: { route_id?: string | null }): Promise<ResolvedSessionRoute> =>
    request.route_id === FALLBACK_ROUTE_ID
      ? resolved(routeSnapshot(FALLBACK_ROUTE_ID, FALLBACK_ROUTE_ID))
      : resolved(snapshot);

  const driver = createCouncilDriver({
    deliberation: service,
    envelope: owner,
    scope: SCOPE,
    principal,
    clock,
    ids,
    resolveRoute,
    auditLogPath: join(dir, 'convening-audit.jsonl'),
    dataDir: dir,
    onSettled: (id, result) => settled.push({ id, result }),
  });

  return {
    transport,
    fallbackTransport,
    service,
    settled,
    convene: async (input) =>
      driver.convene({
        requested_by: 'owner-1',
        brief: briefFor(input.seat_ids ?? [...SEAT_IDS]),
        route: {},
        ...input,
      }),
    drain: () => driver.drain(),
  };
}

function advisorRounds(cards: ReadonlyArray<{ card_kind: string; round: number }>): number[] {
  return [...new Set(cards.filter((c) => c.card_kind === 'advisor').map((c) => c.round))].sort(
    (a, b) => a - b,
  );
}

/** One convene per mode: driver -> composition -> waves -> verdict. */
async function conveneAndCheck(
  mode: SessionMode,
  route: { routeId: string; providerSlug: string },
  expected: {
    seats: number;
    rounds: number;
    parallel: number;
    seat_ids?: SeatId[];
    ollama_plan?: '20' | '100';
  },
): Promise<void> {
  const r = rig(route);
  const accepted = await r.convene({ mode, ...expected });
  await r.drain();

  assert.equal(accepted.seats, expected.seats, `${mode}: seat count`);
  assert.equal(accepted.parallel_limit, expected.parallel, `${mode}: parallel limit`);
  assert.equal(accepted.request_cap, mode === 'heavy' ? 100 : 50, `${mode}: request cap`);

  // Completed with a verdict, and no separate ratification pass.
  assert.equal(r.settled.length, 1, `${mode}: one settled run`);
  const settled = r.settled[0].result;
  assert.equal(settled.status, 'completed', `${mode}: ${JSON.stringify(settled).slice(0, 400)}`);
  if (settled.status !== 'completed') return;
  assert.equal(settled.verdict.ratification_status, 'not_required', `${mode}: ratification`);

  // Rounds actually run: every forced round, one advisor card per seat.
  const owner = envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write');
  const cards = r.service.repositories.listCards(owner, accepted.session_id);
  const rounds = advisorRounds(cards);
  assert.deepEqual(
    rounds,
    Array.from({ length: expected.rounds }, (_, i) => i + 1),
    `${mode}: rounds run`,
  );
  assert.equal(
    cards.filter((c) => c.card_kind === 'advisor').length,
    expected.seats * expected.rounds,
    `${mode}: one advisor card per seat per round`,
  );
  assert.equal(
    cards.filter((c) => c.card_kind === 'ratification').length,
    0,
    `${mode}: no ratification cards`,
  );

  // Provider requests counted: exactly one transport call per card, and
  // the budget service counted the same number.
  assert.equal(
    r.transport.requests.length,
    expected.seats * expected.rounds,
    `${mode}: transport requests`,
  );
  assert.equal(
    r.service.budget.snapshot(owner, accepted.session_id).consumed.provider_requests,
    r.transport.requests.length,
    `${mode}: budget provider_requests`,
  );

  // Real parallelism: peak in-flight calls equal the mode's parallel limit.
  assert.equal(r.transport.peak, expected.parallel, `${mode}: peak concurrency`);
}

// ---------------------------------------------------------------- tests

test('W77S-E2E: light convenes 3 seats, 2 rounds, 3 at a time on an Ollama $20 plan', async () => {
  await conveneAndCheck(
    'light',
    { routeId: 'ollama-configured', providerSlug: 'ollama' },
    { seats: 3, rounds: 2, parallel: 3, seat_ids: [...LIGHT_PANEL], ollama_plan: '20' },
  );
});

test('W77S-E2E: medium convenes all 9 seats for 4 rounds, all at once on OpenRouter', async () => {
  await conveneAndCheck(
    'medium',
    { routeId: 'openrouter-configured', providerSlug: 'openrouter-configured' },
    { seats: SEAT_IDS.length, rounds: 4, parallel: SEAT_IDS.length },
  );
});

test('W77S-E2E: heavy convenes all 9 seats for 10 rounds, all at once on OpenRouter', async () => {
  await conveneAndCheck(
    'heavy',
    { routeId: 'openrouter-configured', providerSlug: 'openrouter-configured' },
    { seats: SEAT_IDS.length, rounds: 10, parallel: SEAT_IDS.length },
  );
});

test('W77S-E2E: a rate-limited Ollama seat is re-run on the driver-approved fallback grant', async () => {
  const failingSeat = LIGHT_PANEL[2];
  const r = rig(
    { routeId: 'ollama-configured', providerSlug: 'ollama' },
    { failingSeat },
  );
  const accepted = await r.convene({
    mode: 'light',
    seat_ids: [...LIGHT_PANEL],
    ollama_plan: '20',
    fallback_model: 'some/model',
  });
  await r.drain();

  assert.match(accepted.fallback, /openrouter-configured/);
  assert.equal(r.settled.length, 1);
  const settled = r.settled[0].result;
  assert.equal(settled.status, 'completed', JSON.stringify(settled).slice(0, 400));

  // Both rounds fell back for the one failing seat, on the fallback
  // route only, and the run still completed with a verdict.
  assert.equal(r.fallbackTransport.requests.length, 2);
  assert.ok(
    r.fallbackTransport.requests.every((request) => request.seat_id === failingSeat),
    'only the failed seat is re-run on the fallback route',
  );
  const owner = envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write');
  const fallbackJobs = r.service.runner
    .listSessionJobs(owner, accepted.session_id)
    .filter((job) => job.phase_job_key.endsWith(':fallback'));
  assert.equal(fallbackJobs.length, 2);
  assert.ok(fallbackJobs.every((job) => job.state === 'succeeded'));
  if (settled.status !== 'completed') return;
  assert.equal(settled.verdict.ratification_status, 'not_required');
});

test('W77S-E2E: the Ollama fallback re-runs every failed seat in ONE wave on the fallback route', async () => {
  // Medium on an Ollama $20 plan: the primary waves are 3 wide. Four
  // seats fail in Round 1, so a fallback that inherited the primary's
  // wave width would need two serial OpenRouter round-trips. The
  // fallback route has no parallel limit: all four go in one wave.
  const failing = SEAT_IDS.slice(0, 4);
  const r = rig(
    { routeId: 'ollama-configured', providerSlug: 'ollama' },
    { failingSeats: failing, failRound: 1 },
  );
  const accepted = await r.convene({
    mode: 'medium',
    ollama_plan: '20',
    fallback_model: 'some/model',
  });
  await r.drain();

  assert.equal(accepted.parallel_limit, 3);
  assert.equal(r.fallbackTransport.requests.length, failing.length);
  assert.equal(
    r.fallbackTransport.peak,
    failing.length,
    'the fallback route runs every re-run at once, not in primary-sized waves',
  );
  assert.equal(r.settled[0].result.status, 'completed');
});

test('W77S-E2E: light freezes only its panel weights so the verdict passes publication', async () => {
  // A light convene over a brief that carries all nine weights: the
  // driver's panel is three seats, so the frozen brief must carry three
  // weights. Keeping the other six made publication recompute the
  // decision over nine seats while the verdict was built over three, and
  // the light verdict failed its own scores_recomputed check.
  const r = rig({ routeId: 'openrouter-configured', providerSlug: 'openrouter-configured' });
  const allWeights = briefFor([...SEAT_IDS]);
  const accepted = await r.convene({
    mode: 'light',
    seat_ids: [...LIGHT_PANEL],
    brief: allWeights,
  });
  await r.drain();

  const owner = envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write');
  const stored = r.service.repositories.getSession(owner, accepted.session_id);
  assert.ok(stored);
  assert.deepEqual(
    Object.keys(stored.brief.relevance_weights).sort(),
    [...LIGHT_PANEL].sort(),
    'the frozen brief carries exactly the panel weights',
  );
  // Every panel seat keeps the weight the caller gave it.
  for (const seatId of LIGHT_PANEL) {
    assert.equal(
      stored.brief.relevance_weights[seatId],
      allWeights.relevance_weights[seatId],
      seatId,
    );
  }

  const settled = r.settled[0].result;
  assert.equal(settled.status, 'completed');
  if (settled.status !== 'completed') return;
  const publication = validateVerdictForPublication({
    verdict: settled.verdict,
    brief: stored.brief,
    final_cards: r.service.repositories.listCards(owner, accepted.session_id),
    require_final_cards: true,
  });
  assert.equal(
    publication.publishable,
    true,
    publication.checks
      .filter((check) => check.status !== 'pass')
      .map((check) => `${check.name}: ${check.detail}`)
      .join('; '),
  );
});
