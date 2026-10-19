/**
 * CWE-050 composition integration tests (ONBOARDING/PORTABLE stream):
 * the full deliberation service composed ONLY from accepted parts
 * (CWE-024 opening + CWE-025 later rounds behind CWE-027's runner,
 * CWE-049 preview/approve/admission, CWE-028 the only ledger, CWE-022
 * context, fixture transports on a pinned route snapshot), driven end
 * to end: intake-frozen brief -> verdict -> CWE-038 report.
 *
 * Section 35 contracts exercised on the portable side:
 * - T021/T146/T149 (through the composition): full pipeline, all nine
 *   seats in every round, golden values reproduced (A 6.0, B 7.6
 *   display, C 6.6 display), 27 provider requests counted once.
 * - T022/T039: quick journey completes without Round 3 when the
 *   Section 10 skip predicate holds on real committed cards.
 * - T023: consult journey: one seat, one card, discriminated result.
 * - T150 (composition half): the 50-request ceiling binds through the
 *   composition itself: a grant approved with a smaller ceiling stops
 *   the run visibly instead of overspending.
 * - T123: the production composition module resolves no fixture
 *   service (source scan) and refuses unbound transports honestly.
 * - T129: readiness is derived from the actual bound services; a
 *   scaffold composition reports not ready and refuses to run.
 * - Section 12.3 / CWE-026 divergence (a): with no recorded checker
 *   result, an unchecked hard constraint yields WAIT (never a silent
 *   pass); with a recorded pass, the golden GO reproduces.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import {
  canonicalHash,
  GOLDEN_EXPECTED,
  GOLDEN_WEIGHTS,
  SEAT_IDS,
  type DecisionBrief,
  type HardConstraintFinding,
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
import type { TrustedPrincipal } from '../src/authorization/index.js';
import type { PinnedRouteSnapshot } from '../src/budgets/index.js';
import { COUNCIL_SCHEMA_SQL } from '../src/persistence/index.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';
import type { RunnerTimers } from '../src/queue/index.js';
import type {
  CandidateHeader,
  MaterialCandidate,
  MaterialCatalog,
} from '../src/context/index.js';
import type { EvidenceUnit, SourceRecord } from '../src/sources/index.js';
import {
  composeDeliberationService,
  type DeliberationService,
} from '../src/protocol/composition.js';
import { ProtocolError } from '../src/protocol/errors.js';
import {
  createCwe006ExportJournal,
  createCwe006SessionLiveness,
  InMemoryDeliverableRegistry,
  ReportExportService,
} from '../src/reports/index.js';
import { CouncilStoreService } from '../src/persistence/store.js';

// ------------------------------------------------------------- fixtures

const clock = { nowUtc: () => '2026-10-14T12:00:00.000Z' };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

const PACK_VERSION = 'pack-test-1.0.0';
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
    brief_id: `brief-${sessionId}`,
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
    private_preference_ref: null,
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
  };
}

function storedSession(
  mode: SessionSpec['mode'],
  panel: readonly SeatId[],
  sessionId: string,
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
    createdAt: '2026-10-14T12:00:00.000Z',
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
  every(_ms: number, _fn: () => void): () => void {
    return () => {};
  }
  delay(_ms: number): Promise<void> {
    return new Promise(() => {});
  }
}

class RecordingTransport implements ModelTransport {
  readonly requests: TransportRequest[] = [];
  private readonly fixture = new DeterministicFixtureTransport();
  constructor(
    private readonly script?: (
      request: TransportRequest,
    ) => Promise<TransportResponse> | TransportResponse,
  ) {}
  async generate(request: TransportRequest): Promise<TransportResponse> {
    this.requests.push(request);
    if (this.script) return this.script(request);
    return this.fixture.generate(request);
  }
}

const RECORDED_PASS: HardConstraintFinding[] = [
  {
    constraint_id: 'con-1',
    option_id: 'B',
    result: 'pass',
    checker: 'deterministic_code',
    evidence_ids: ['ev-case-1'],
  },
  {
    constraint_id: 'con-1',
    option_id: 'C',
    result: 'pass',
    checker: 'deterministic_code',
    evidence_ids: ['ev-case-1'],
  },
];

interface Harness {
  service: DeliberationService;
  dir: string;
  owner: ReturnType<typeof envelopeFromScope>;
  worker: ReturnType<typeof envelopeFromScope>;
  snapshot: PinnedRouteSnapshot;
  transport: RecordingTransport;
  grantFor: (sessionId: string, ceilings?: RunCeilings, purpose?: string) => string;
}

function harness(
  label: string,
  options: {
    transport?: RecordingTransport;
    recordedFindings?: readonly HardConstraintFinding[];
    catalog?: MaterialCatalog | null;
  } = {},
): Harness {
  const dir = mkdtempSync(join(tmpdir(), `cwe050-${label}-`));
  const db = CouncilDatabase.open(join(dir, 'council.db'), {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const transport = options.transport ?? new RecordingTransport();
  const service = composeDeliberationService({
    db,
    clock,
    ids,
    catalog:
      options.catalog !== undefined
        ? options.catalog
        : new ListCatalog(SEAT_IDS.map((seatId) => seatCandidate(seatId))),
    resolvePrincipal: () => principal(),
    resolveTransport: () => transport,
    routeBudget: () => ({
      context_limit_bytes: 1_000_000,
      response_schema_bytes: 2_000,
      output_reserve_bytes: 8_000,
    }),
    timers: new ManualTimers(),
    recordedHardConstraintFindings: options.recordedFindings
      ? () => options.recordedFindings!
      : undefined,
  });
  const owner = envelopeFromScope(SESSION_SCOPE, 'owner-1', 'owner', 'write');
  const worker = envelopeFromScope(SESSION_SCOPE, 'owner-1', 'worker', 'write');
  const snapshot = routeSnapshot();
  const grantFor = (
    sessionId: string,
    ceilings: RunCeilings = CEILINGS,
    purpose?: string,
  ): string => {
    const preview = service.grants.previewRun(owner, {
      session_id: sessionId,
      purpose: purpose as never,
      route_snapshot: snapshot,
      route_policy_sha256: canonicalHash({ policy: 'route-policy-a' }),
      ceilings,
    });
    const grant = service.grants.approveRun(owner, preview.preview_id, {
      principal: principal(),
      authority_mode: 'local_interactive_owner',
      interactive_confirmation: true,
    });
    return grant.grant_id;
  };
  return { service, dir, owner, worker, snapshot, transport, grantFor };
}

// ------------------------------------------------------------- tests

test('composition: full session end to end reproduces the golden verdict and a CWE-038 report', async () => {
  const h = harness('golden', { recordedFindings: RECORDED_PASS });
  const session = storedSession('full', SEAT_IDS, 'sess-cwe050-golden');
  h.service.repositories.createSession(h.owner, session);
  const grantId = h.grantFor(session.spec.session_id);

  const result = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });
  assert.equal(result.status, 'completed');
  if (result.status !== 'completed' || result.verdict.result_kind !== 'scored') return;
  const verdict = result.verdict;
  assert.equal(verdict.label, 'GO');
  assert.equal(verdict.recommended_option_id, 'B');
  assert.equal(verdict.ratification_status, 'ratified');
  const byId = new Map(verdict.option_scores.map((o) => [o.option_id, o]));
  for (const optionId of ['A', 'B', 'C'] as const) {
    const expected = GOLDEN_EXPECTED[optionId];
    const mine = byId.get(optionId);
    assert.ok(mine);
    assert.equal(mine.weighted_sum, expected.weighted_sum, `${optionId} sum`);
    assert.equal(mine.denominator, expected.denominator, `${optionId} denominator`);
    assert.equal(mine.score, expected.score, `${optionId} score`);
    assert.equal(mine.display_score, expected.display_score, `${optionId} display`);
  }
  assert.ok(verdict.resolution_support);
  assert.equal(
    verdict.resolution_support.support +
      verdict.resolution_support.conditional_support +
      verdict.resolution_support.opposition +
      verdict.resolution_support.abstention,
    22,
  );
  // 27 provider requests, counted exactly once in CWE-028's ledger.
  assert.equal(result.budget.consumed.provider_requests, 27);
  assert.equal(h.transport.requests.length, 27);
  const cards = h.service.repositories.listCards(h.worker, session.spec.session_id);
  assert.equal(cards.length, 27);
  const stored = h.service.repositories.getSession(h.worker, session.spec.session_id);
  assert.equal(stored?.state.state, 'COMPLETED');

  // CWE-038 report through the composed service, with CWE-038's own
  // CWE-006 journal and liveness adapters over the same store: the
  // exact verdict hash is a registered deliverable (B15 closure).
  const store = CouncilStoreService.open({
    dataDir: h.dir,
    databasePath: join(h.dir, 'council.db'),
    clock,
    ids,
    envelope: h.owner,
  });
  const reports = new ReportExportService({
    journal: createCwe006ExportJournal(store, {
      tenant_id: SESSION_SCOPE.tenant_id,
      company_id: SESSION_SCOPE.company_id,
    }),
    registry: new InMemoryDeliverableRegistry(),
    liveness: createCwe006SessionLiveness(store),
  });
  const exported = await reports.exportReport({
    request_id: 'req-cwe050-golden-1',
    principal: principal(),
    session_id: session.spec.session_id,
    session_scope: SESSION_SCOPE,
    session_visibility: 'company',
    verdict,
    brief: session.brief,
    final_cards: cards,
    current_verdict_revision: verdict.verdict_revision,
    formats: ['record_json', 'markdown'],
    context: { report_date: '2026-10-14' },
    exported_at: '2026-10-14T12:30:00.000Z',
  });
  assert.equal(exported.verdict_content_sha256, verdict.content_sha256);
  assert.equal(exported.artifacts.length, 2);
  for (const artifact of exported.artifacts) {
    assert.equal(artifact.sha256.length, 64);
    assert.ok(artifact.bytes.length > 0);
  }
  const recordJson = exported.artifacts.find((a) => a.format === 'record_json');
  assert.ok(recordJson);
  assert.ok(recordJson.bytes.includes(verdict.content_sha256));
});

test('composition: unchecked hard constraint yields WAIT, never a silent pass (divergence (a))', async () => {
  const h = harness('findings-default');
  const session = storedSession('full', SEAT_IDS, 'sess-cwe050-wait');
  h.service.repositories.createSession(h.owner, session);
  const grantId = h.grantFor(session.spec.session_id);
  const result = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });
  assert.equal(result.status, 'completed');
  if (result.status !== 'completed' || result.verdict.result_kind !== 'scored') return;
  assert.equal(result.verdict.label, 'WAIT');
  assert.equal(result.verdict.recommended_option_id, 'B');
  assert.ok(
    result.verdict.hard_constraint_findings.some(
      (f) => f.constraint_id === 'con-1' && f.option_id === 'B' && f.result === 'unknown',
    ),
  );
  assert.ok(
    result.verdict.prerequisites.some((p) => p.includes('con-1')),
    'the unchecked constraint is a named prerequisite',
  );
});

test('composition: the approved ceiling binds the composition itself (T150)', async () => {
  const h = harness('ceiling', { recordedFindings: RECORDED_PASS });
  const session = storedSession('full', SEAT_IDS, 'sess-cwe050-ceiling');
  h.service.repositories.createSession(h.owner, session);
  const grantId = h.grantFor(session.spec.session_id, {
    ...CEILINGS,
    max_provider_requests: 10,
  });
  const result = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });
  // The run cannot complete: admission refuses beyond the approved
  // ceiling, the session lands BLOCKED as a visible partial, and the
  // ledger never exceeds the ceiling the owner approved.
  assert.notEqual(result.status, 'completed');
  assert.ok(result.budget.consumed.provider_requests <= 10);
  const stored = h.service.repositories.getSession(h.worker, session.spec.session_id);
  assert.equal(stored?.state.state, 'BLOCKED');
  assert.equal(
    h.service.repositories.getVerdict(h.worker, session.spec.session_id),
    null,
    'no verdict is assembled from a partial council',
  );
});

test('composition: quick journey completes without Round 3 (T022)', async () => {
  const panel: SeatId[] = ['simon-sinek', 'tiffany-aliche', 'russell-brunson', 'brene-brown'];
  const uniformScores = { A: 5, B: 9, C: 6 };
  const transport = new RecordingTransport(async (request) => {
    if (request.round === 1 || request.round === 2) {
      const fixture = new DeterministicFixtureTransport();
      const base = await fixture.generate({
        ...request,
        input: request.input,
      });
      void base;
      // Scripted unanimous card, shaped like CWE-025's advisorAuthor.
      const input = request.input as {
        brief: { session_id: string; revision: number };
        input_manifest_sha256: string;
        pack_version: string;
        challenges_for_seat?: Array<{ crux_id: string }>;
      };
      const card = {
        schema_version: 'wise-elders.card/v1',
        session_id: input.brief.session_id,
        brief_revision: input.brief.revision,
        seat_id: request.seat_id,
        input_manifest_sha256: input.input_manifest_sha256,
        pack_version: input.pack_version,
        card_kind: 'advisor',
        round: request.round ?? 1,
        stance: 'support',
        preferred_option_id: 'B',
        option_scores: OPTIONS.map((o) => ({
          option_id: o.id,
          score: uniformScores[o.id as 'A' | 'B' | 'C'],
          rationale: `Unanimous scripted rationale from ${request.seat_id} for ${o.id}.`,
          evidence_ids: [],
        })),
        framework_applications: [],
        decisive_arguments: ['The pilot is the bounded next step.'],
        strongest_objection: 'Retention is still unmeasured.',
        conditions: [],
        critical_unknowns: [],
        change_my_mind: 'Evidence the pilot cannot be staffed.',
        challenges_answered: (input.challenges_for_seat ?? []).map((c) => c.crux_id),
        quotes: [],
        evidence_strength: 'medium',
        minority_position: null,
      };
      return {
        text: JSON.stringify(card),
        provider_request_id: `quick-${request.seat_id}-${request.round}`,
        reported_model_id: 'scripted-transport',
        usage: { input_tokens: null, output_tokens: null },
      };
    }
    return new DeterministicFixtureTransport().generate(request);
  });
  const h = harness('quick', { transport, recordedFindings: RECORDED_PASS });
  const session = storedSession('quick', panel, 'sess-cwe050-quick');
  h.service.repositories.createSession(h.owner, session);
  const grantId = h.grantFor(session.spec.session_id);
  const result = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });
  assert.equal(result.status, 'completed');
  if (result.status !== 'completed' || result.verdict.result_kind !== 'scored') return;
  assert.equal(result.verdict.ratification_status, 'not_run_by_quick_mode_policy');
  assert.equal(result.verdict.resolution_support, null);
  assert.equal(result.budget.consumed.provider_requests, 8, 'two rounds of four seats, no Round 3 spend');
  assert.equal(
    h.service.repositories
      .listCards(h.worker, session.spec.session_id)
      .filter((c) => c.card_kind === 'ratification').length,
    0,
  );
});

test('composition: consult journey produces a discriminated consult result (T023)', async () => {
  const h = harness('consult');
  const session = storedSession('consult', ['tiffany-aliche'], 'sess-cwe050-consult');
  h.service.repositories.createSession(h.owner, session);
  const grantId = h.grantFor(session.spec.session_id);
  const result = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });
  assert.equal(result.status, 'completed');
  if (result.status !== 'completed') return;
  assert.equal(result.verdict.result_kind, 'consult');
  assert.equal(h.transport.requests.length, 1, 'exactly one provider request');
  assert.equal(h.transport.requests[0].purpose, 'consult');
  const serialized = result.verdict as unknown as Record<string, unknown>;
  assert.ok(!('option_scores' in serialized), 'no invented scores');
  assert.ok(!('label' in serialized), 'no invented verdict label');
});

test('composition: readiness is derived from bound services; a scaffold refuses (T129, T123)', async () => {
  const h = harness('scaffold', { catalog: null });
  const readiness = h.service.readiness();
  assert.equal(readiness.ready, false);
  assert.ok(
    readiness.checks.some((c) => c.name === 'material_catalog' && !c.bound),
    'the unbound catalog is named',
  );
  const session = storedSession('full', SEAT_IDS, 'sess-cwe050-scaffold');
  h.service.repositories.createSession(h.owner, session);
  const grantId = h.grantFor(session.spec.session_id);
  await assert.rejects(
    () =>
      h.service.runSession(h.worker, session.spec.session_id, {
        grant_id: grantId,
        route_snapshot: h.snapshot,
      }),
    (error: unknown) =>
      error instanceof ProtocolError && error.code === 'COMPOSITION_NOT_READY',
  );
  assert.equal(h.transport.requests.length, 0, 'nothing was dispatched');

  // T123 source scan: the production composition module (and the
  // protocol services) resolve no fixture service.
  const compositionSource = readFileSync(
    fileURLToPath(new URL('../src/protocol/composition.ts', import.meta.url)),
    'utf8',
  );
  assert.ok(!compositionSource.includes('fixture-transport'));
  assert.ok(!compositionSource.includes('DeterministicFixtureTransport'));
});

test('composition: follow-up runs as a linked consult under its own purpose grant (T142)', async () => {
  const h = harness('followup', { recordedFindings: RECORDED_PASS });
  const session = storedSession('full', SEAT_IDS, 'sess-cwe050-follow');
  h.service.repositories.createSession(h.owner, session);
  const grantId = h.grantFor(session.spec.session_id);
  const run = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });
  assert.equal(run.status, 'completed');

  const before = h.transport.requests.length;
  const { link, verdict } = await h.service.followUp.askFollowUp(
    h.owner,
    session.spec.session_id,
    {
      seat_id: 'tiffany-aliche',
      question: 'What would make the pilot affordable at committed cash levels?',
      authorize: (followUpSessionId) => ({
        grant_id: h.grantFor(followUpSessionId, CEILINGS, 'follow_up'),
        route_snapshot: h.snapshot,
      }),
    },
  );
  assert.equal(link.parent_session_id, session.spec.session_id);
  assert.equal(verdict.result_kind, 'consult');
  assert.equal(verdict.session_id, link.follow_up_session_id);
  assert.equal(h.transport.requests.length, before + 1, 'one follow-up provider request');
  const links = h.service.followUp.listFollowUps(h.owner, session.spec.session_id);
  assert.equal(links.length, 1);
  assert.equal(links[0].follow_up_session_id, link.follow_up_session_id);
  // The follow-up never reopens the parent: its verdict is untouched.
  const parentVerdict = h.service.repositories.getVerdict(h.owner, session.spec.session_id);
  assert.equal(parentVerdict?.content_sha256, run.status === 'completed' ? run.verdict.content_sha256 : '');
});

// ----------------------------------------- W30 acceptance fix round 1

test('composition: a refused Round 2 job stops the session; Round 3 is never planned from a partial record', async () => {
  // Real run: the grant refused one Round 2 repair, the round loop stopped,
  // the refused job stayed queued, Round 3 was planned from 8 cards, and the
  // leftover job later committed a card that changed the draft hash, so all
  // nine Round 3 dispatches refused as input drift.
  const h = harness('round2-refused', { recordedFindings: RECORDED_PASS });
  const session = storedSession('full', SEAT_IDS, 'sess-w30-r2-refused');
  h.service.repositories.createSession(h.owner, session);
  const grantId = h.grantFor(session.spec.session_id, {
    ...CEILINGS,
    max_provider_requests: 12, // 9 Round 1 + 3 Round 2, then refusal
  });
  const result = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });
  assert.equal(result.status, 'incomplete');
  const stored = h.service.repositories.getSession(h.worker, session.spec.session_id);
  assert.equal(stored?.state.state, 'BLOCKED');
  const jobs = h.service.runner.listSessionJobs(h.worker, session.spec.session_id);
  assert.equal(
    jobs.filter((j) => j.phase_job_key.startsWith('round-3:')).length,
    0,
    'no Round 3 job is enqueued while Round 2 work is unfinished',
  );
  assert.ok(jobs.some((j) => j.phase_job_key.startsWith('round-2:') && j.state === 'queued'));
});

test('composition: full mode stops after a Round 1 seat produced no card, spending no Round 2 call', async () => {
  const transport = new RecordingTransport(async (request) => {
    if (request.round === 1 && request.seat_id === 'oprah-winfrey') {
      return {
        text: '{"not":"a card"}',
        provider_request_id: `bad-${request.seat_id}`,
        reported_model_id: 'scripted-transport',
        usage: { input_tokens: null, output_tokens: null },
      };
    }
    return new DeterministicFixtureTransport().generate(request);
  });
  const h = harness('round1-missing', { transport, recordedFindings: RECORDED_PASS });
  const session = storedSession('full', SEAT_IDS, 'sess-w30-r1-missing');
  h.service.repositories.createSession(h.owner, session);
  const result = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: h.grantFor(session.spec.session_id),
    route_snapshot: h.snapshot,
  });
  assert.equal(result.status, 'incomplete');
  if (result.status !== 'incomplete') return;
  assert.deepEqual(result.missing, [{ round: 1, seat_id: 'oprah-winfrey' }]);
  assert.equal(
    transport.requests.filter((r) => r.round === 2 || r.round === 3).length,
    0,
    'no paid Round 2 or Round 3 call after Round 1 is already short a seat',
  );
  assert.equal(
    h.service.repositories.getSession(h.worker, session.spec.session_id)?.state.state,
    'BLOCKED',
  );
});
