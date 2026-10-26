/**
 * W77S-MODES lane B: the council-size round protocol.
 *
 * Proves the consensus stop rule exactly as designed, the light/medium/
 * heavy round loop end to end through the production composition (one
 * pass per seat per round, cruxes from the round before, no separate
 * ratification pass, verdict composed from the LAST completed round),
 * the per-pass challenge input identity, and the generalized blocked
 * reasons. The four older modes keep their own tests elsewhere and are
 * untouched by this suite.
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  GOLDEN_WEIGHTS,
  SEAT_IDS,
  type AdvisorCard,
  type CouncilSettings,
  type DecisionBrief,
  type RunCeilings,
  type ScopeFields,
  type SeatId,
  type SessionSpec,
} from '../src/contracts/index.js';
import { DEFAULT_COUNCIL_SETTINGS } from '../src/contracts/schemas.js';
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
import { TransportDispatchError } from '../src/queue/index.js';
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
import { evaluateConsensusStop } from '../src/protocol/consensus.js';
import { buildBlockedReason } from '../src/service/sessions.js';

// ------------------------------------------------------ consensus unit

function cardFor(seatId: string, scores: Record<string, number | null>, stance = 'conditional'): AdvisorCard {
  return {
    card_kind: 'advisor',
    seat_id: seatId,
    stance,
    preferred_option_id: null,
    round: 2,
    option_scores: Object.entries(scores).map(([option_id, score]) => ({
      option_id,
      score,
      rationale: 'unit fixture',
      evidence_ids: [],
    })),
  } as unknown as AdvisorCard;
}

test('W77S: consensus needs seven seats and a 1.5-point lead', () => {
  const options = ['A', 'B', 'C'];
  const seven = [
    ...Array.from({ length: 7 }, (_, i) => cardFor(`s${i}`, { A: 9, B: 5, C: 3 })),
    cardFor('s7', { A: 5, B: 9, C: 3 }),
    cardFor('s8', { A: 5, B: 9, C: 3 }),
  ];
  const stopped = evaluateConsensusStop(seven, options);
  assert.equal(stopped.panel, 9);
  assert.equal(stopped.top_option_id, 'A');
  assert.equal(stopped.share, 7);
  // mean(A) 8.111 - mean(B) 5.889 over the nine paired seats.
  assert.ok(Math.abs((stopped.lead as number) - 20 / 9) < 1e-9, `lead ${stopped.lead}`);
  assert.equal(stopped.stop, true);

  // Six of nine is not enough even with a huge lead.
  const six = [
    ...Array.from({ length: 6 }, (_, i) => cardFor(`s${i}`, { A: 9, B: 5, C: 3 })),
    cardFor('s6', { A: 5, B: 9, C: 3 }),
    cardFor('s7', { A: 5, B: 9, C: 3 }),
    cardFor('s8', { A: 5, B: 9, C: 3 }),
  ];
  const noShare = evaluateConsensusStop(six, options);
  assert.equal(noShare.share, 6);
  assert.equal(noShare.stop, false);

  // Seven seats sharing a top but only a one-point lead: no stop.
  const narrow = Array.from({ length: 9 }, (_, i) =>
    cardFor(`s${i}`, i < 7 ? { A: 8, B: 7, C: 1 } : { A: 7, B: 8, C: 1 }),
  );
  const noLead = evaluateConsensusStop(narrow, options);
  assert.equal(noLead.share, 7);
  assert.ok((noLead.lead as number) < 1.5, `lead ${noLead.lead}`);
  assert.equal(noLead.stop, false);
});

test('W77S: a tied top, an abstention or an invalid card has no top', () => {
  const options = ['A', 'B', 'C'];
  const cards = [
    cardFor('tie', { A: 7, B: 7, C: 3 }),
    cardFor('abstain', { A: 9, B: 5, C: 3 }, 'abstain'),
    cardFor('silent', { A: null, B: null, C: null }),
    cardFor('only', { A: 6, B: null, C: null }),
  ];
  const result = evaluateConsensusStop(cards, options);
  assert.equal(result.panel, 4);
  assert.equal(result.top_option_id, 'A');
  assert.equal(result.share, 1);
  assert.equal(result.stop, false);
  // A tie for highest among ALL scored options leaves no top at all.
  assert.equal(evaluateConsensusStop([cards[0]], options).top_option_id, null);
  // Nothing scored: no top, no lead, never a stop.
  const empty = evaluateConsensusStop([], options);
  assert.deepEqual(empty, {
    stop: false,
    top_option_id: null,
    share: 0,
    panel: 0,
    lead: null,
  });
});

// ------------------------------------------------------------- fixtures

const clock = { nowUtc: () => '2026-10-25T12:00:00.000Z' };
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
    created_at: '2026-10-25T02:00:00Z',
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
    created_at: '2026-10-25T02:00:00Z',
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

function routeSnapshot(providerSlug = 'provider-a', routeId = 'route-a'): PinnedRouteSnapshot {
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
      tenantId: SESSION_SCOPE.tenant_id,
      companyId: SESSION_SCOPE.company_id,
      installationId: SESSION_SCOPE.installation_id,
      ownerSubject: SESSION_SCOPE.owner_subject,
    },
    createdAt: '2026-10-25T12:00:00.000Z',
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

const HEAVY_CEILINGS: RunCeilings = {
  ...CEILINGS,
  max_provider_requests: 100,
  max_output_repairs: 100,
  max_transport_retries: 100,
};

class ManualTimers implements RunnerTimers {
  every(_ms: number, _fn: () => void): () => void {
    return () => {};
  }
  delay(_ms: number): Promise<void> {
    return new Promise(() => {});
  }
}

// ------------------------------------------------------------- transport

type ScoreScript = 'consensus' | 'split';

function scriptedScores(seatId: SeatId, script: ScoreScript): Record<string, number> {
  if (script === 'consensus') return { A: 9, B: 5, C: 3 };
  const prefersA = SEAT_IDS.indexOf(seatId) < 4;
  return { A: prefersA ? 9 : 5, B: prefersA ? 5 : 9, C: 3 };
}

/** Every other call for a seat/round is an invalid card, forcing a repair. */
class ScriptedTransport implements ModelTransport {
  readonly requests: TransportRequest[] = [];
  private readonly calls = new Map<string, number>();

  constructor(
    private readonly options: {
      script: ScoreScript;
      /** Calls per (seat, round) that are deliberately invalid, then valid. */
      invalidOnCall?: number;
    },
  ) {}

  async generate(request: TransportRequest): Promise<TransportResponse> {
    this.requests.push(request);
    const key = `${request.seat_id}:${request.round}`;
    const calls = (this.calls.get(key) ?? 0) + 1;
    this.calls.set(key, calls);
    const seatId = request.seat_id as SeatId;
    const scores = scriptedScores(seatId, this.options.script);
    const preferred = scores.A >= scores.B ? 'A' : 'B';
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
      preferred_option_id: preferred,
      option_scores: OPTIONS.map((option) => ({
        option_id: option.id,
        score: scores[option.id],
        rationale: `Scripted round ${request.round} rationale from ${seatId} for ${option.id}.`,
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
      conditions: [],
      critical_unknowns: ['Scripted unknown: measured pilot retention.'],
      change_my_mind: 'Measured evidence that the binding constraint no longer holds.',
      challenges_answered: (input.challenges_for_seat ?? []).map((c) => c.crux_id),
      quotes: [],
      evidence_strength: 'medium',
      minority_position: null,
    };
    if (this.options.invalidOnCall !== undefined && calls % 2 === 1) {
      // A definite schema violation: the runner's one bounded repair runs.
      card.stance = 'not_a_stance';
    }
    return {
      text: JSON.stringify(card),
      provider_request_id: `scripted-${seatId}-${request.round}-${calls}`,
      reported_model_id: 'scripted-transport',
      usage: { input_tokens: null, output_tokens: null },
    };
  }

  requestsForRound(round: number): TransportRequest[] {
    return this.requests.filter((r) => r.round === round);
  }
}

// -------------------------------------------------------------- harness

interface Harness {
  service: DeliberationService;
  owner: ReturnType<typeof envelopeFromScope>;
  worker: ReturnType<typeof envelopeFromScope>;
  snapshot: PinnedRouteSnapshot;
  transport: ScriptedTransport;
  grantFor: (
    sessionId: string,
    ceilings?: RunCeilings,
    snapshot?: PinnedRouteSnapshot,
  ) => string;
}

function harness(
  label: string,
  transport: ScriptedTransport,
  options: {
    providerSlug?: string;
    settings?: CouncilSettings;
    resolveTransport?: (snapshot: PinnedRouteSnapshot) => ModelTransport;
  } = {},
): Harness {
  const dir = mkdtempSync(join(tmpdir(), `w77s-${label}-`));
  const db = CouncilDatabase.open(join(dir, 'council.db'), {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const panelSeats = SEAT_IDS;
  const service = composeDeliberationService({
    db,
    clock,
    ids,
    catalog: new ListCatalog(panelSeats.map((seatId) => seatCandidate(seatId))),
    resolvePrincipal: () => principal(),
    resolveTransport:
      options.resolveTransport ?? (() => transport),
    routeBudget: () => ({
      context_limit_bytes: 1_000_000,
      response_schema_bytes: 2_000,
      output_reserve_bytes: 8_000,
    }),
    timers: new ManualTimers(),
    settings: options.settings,
  });
  const owner = envelopeFromScope(SESSION_SCOPE, 'owner-1', 'owner', 'write');
  const worker = envelopeFromScope(SESSION_SCOPE, 'owner-1', 'worker', 'write');
  const snapshot = routeSnapshot(options.providerSlug);
  const grantFor = (
    sessionId: string,
    ceilings: RunCeilings = CEILINGS,
    pinned: PinnedRouteSnapshot = snapshot,
  ): string => {
    const preview = service.grants.previewRun(owner, {
      session_id: sessionId,
      route_snapshot: pinned,
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
  return { service, owner, worker, snapshot, transport, grantFor };
}

const LIGHT_PANEL: readonly SeatId[] = SEAT_IDS;
async function runMode(
  h: Harness,
  mode: SessionSpec['mode'],
  panel: readonly SeatId[],
  sessionId: string,
  ceilings: RunCeilings = CEILINGS,
) {
  h.service.repositories.createSession(h.owner, storedSession(mode, panel, sessionId));
  const grantId = h.grantFor(sessionId, ceilings);
  const result = await h.service.runSession(h.worker, sessionId, {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });
  const cards = h.service.repositories.listCards(h.worker, sessionId);
  const state = h.service.repositories.getSession(h.worker, sessionId)?.state.state;
  return { result, cards, state };
}

function advisorRounds(cards: ReadonlyArray<{ card_kind: string; round: number }>): number[] {
  return [...new Set(cards.filter((c) => c.card_kind === 'advisor').map((c) => c.round))].sort(
    (a, b) => a - b,
  );
}

// ---------------------------------------------------------------- tests

test('W77S: light runs exactly two rounds over the full roster, eighteen requests, no ratification pass', async () => {
  const transport = new ScriptedTransport({ script: 'consensus' });
  const h = harness('light', transport);
  const { result, cards, state } = await runMode(h, 'light', LIGHT_PANEL, 'sess-w77s-light');

  assert.equal(result.status, 'completed');
  if (result.status !== 'completed' || result.verdict.result_kind !== 'scored') return;
  // Every mode seats all nine; light differs in rounds and wave width only.
  assert.equal(transport.requests.length, 18);
  assert.equal(transport.requestsForRound(1).length, 9);
  assert.equal(transport.requestsForRound(2).length, 9);
  assert.deepEqual(advisorRounds(cards), [1, 2]);
  assert.equal(cards.filter((c) => c.card_kind === 'advisor').length, 18);
  assert.equal(cards.filter((c) => c.card_kind === 'ratification').length, 0);
  assert.equal(result.verdict.ratification_status, 'not_required');
  assert.equal(state, 'COMPLETED');
  assert.equal(result.budget.consumed.provider_requests, 18);
});

test('W77S: a light session missing one seat stops instead of shrinking the council', async () => {
  const scripted = new ScriptedTransport({ script: 'consensus' });
  const missingSeat = SEAT_IDS[4];
  const primary: ModelTransport = {
    generate: async (request) => {
      if (request.seat_id === missingSeat) {
        throw new TransportDispatchError('upstream refused the seat', { retryable: false });
      }
      return scripted.generate(request);
    },
  };
  const h = harness('light-missing', scripted, { resolveTransport: () => primary });
  h.service.repositories.createSession(
    h.owner,
    storedSession('light', SEAT_IDS, 'sess-w77s-light-missing'),
  );
  const grantId = h.grantFor('sess-w77s-light-missing');
  const result = await h.service.runSession(h.worker, 'sess-w77s-light-missing', {
    grant_id: grantId,
    route_snapshot: h.snapshot,
  });

  // The old policy would have carried on with a smaller council; the
  // rule is the same as every other mode: all nine or a visible stop.
  assert.equal(result.status, 'incomplete');
  if (result.status !== 'incomplete') return;
  assert.match(result.detail, /light mode keeps its whole panel/);
  assert.deepEqual(result.missing.map((m) => m.seat_id), [missingSeat]);
  assert.equal(h.service.repositories.getSession(h.worker, 'sess-w77s-light-missing')?.state.state, 'BLOCKED');
});

test('W77S: medium stops after round 1 on consensus and composes from that round', async () => {
  const transport = new ScriptedTransport({ script: 'consensus' });
  const h = harness('medium-stop', transport);
  const { result, cards, state } = await runMode(h, 'medium', SEAT_IDS, 'sess-w77s-medium-stop');

  assert.equal(result.status, 'completed');
  if (result.status !== 'completed' || result.verdict.result_kind !== 'scored') return;
  assert.equal(transport.requests.length, 9);
  assert.deepEqual(advisorRounds(cards), [1]);
  assert.equal(result.verdict.ratification_status, 'not_required');
  assert.equal(state, 'COMPLETED');
});

test('W77S: medium runs to the four-round ceiling without consensus', async () => {
  const transport = new ScriptedTransport({ script: 'split' });
  const h = harness('medium-max', transport);
  const { result, cards, state } = await runMode(h, 'medium', SEAT_IDS, 'sess-w77s-medium-max');

  assert.equal(result.status, 'completed');
  if (result.status !== 'completed' || result.verdict.result_kind !== 'scored') return;
  assert.equal(transport.requests.length, 36);
  assert.deepEqual(advisorRounds(cards), [1, 2, 3, 4]);
  assert.equal(result.verdict.ratification_status, 'not_required');
  assert.equal(state, 'COMPLETED');

  // Every challenge pass binds its own round: the same seat's input
  // manifest differs on every pass.
  const hashes = new Set(
    transport.requests
      .filter((r) => r.seat_id === SEAT_IDS[0] && (r.round ?? 0) >= 2)
      .map((r) => (r.input as { input_manifest_sha256: string }).input_manifest_sha256),
  );
  assert.equal(hashes.size, 3);
});

test('W77S: heavy never stops before round 3, then stops on consensus', async () => {
  const transport = new ScriptedTransport({ script: 'consensus' });
  const h = harness('heavy-min', transport);
  const { result, cards } = await runMode(
    h,
    'heavy',
    SEAT_IDS,
    'sess-w77s-heavy-min',
    HEAVY_CEILINGS,
  );

  assert.equal(result.status, 'completed');
  if (result.status !== 'completed') return;
  assert.equal(transport.requests.length, 27);
  assert.deepEqual(advisorRounds(cards), [1, 2, 3]);
  assert.equal(transport.requestsForRound(3).length, 9);
});

test('W77S: heavy runs to the ten-round ceiling and exceeds 50 requests', async () => {
  const settings: CouncilSettings = {
    ...DEFAULT_COUNCIL_SETTINGS,
    max_session_provider_requests: 100,
  };
  const transport = new ScriptedTransport({ script: 'split' });
  const h = harness('heavy-max', transport, { settings });
  const { result, cards, state } = await runMode(
    h,
    'heavy',
    SEAT_IDS,
    'sess-w77s-heavy-max',
    HEAVY_CEILINGS,
  );

  assert.equal(result.status, 'completed');
  if (result.status !== 'completed' || result.verdict.result_kind !== 'scored') return;
  assert.equal(transport.requests.length, 90);
  assert.ok(transport.requests.length > 50, 'heavy must be able to exceed 50 requests');
  assert.deepEqual(advisorRounds(cards), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.equal(result.verdict.ratification_status, 'not_required');
  assert.equal(state, 'COMPLETED');
});

test('W77S: heavy is refused at 101 provider requests', async () => {
  const settings: CouncilSettings = {
    ...DEFAULT_COUNCIL_SETTINGS,
    max_session_provider_requests: 100,
    max_output_repair_requests: 100,
    max_transport_retries_total: 100,
  };
  // Every first attempt is invalid, so each seat burns a repair.
  const transport = new ScriptedTransport({ script: 'split', invalidOnCall: 1 });
  const h = harness('heavy-cap', transport, { settings });
  const { result } = await runMode(
    h,
    'heavy',
    SEAT_IDS,
    'sess-w77s-heavy-cap',
    HEAVY_CEILINGS,
  );

  assert.notEqual(result.status, 'completed');
  assert.ok(transport.requests.length > 50, 'the run must pass 50 requests');
  assert.equal(
    transport.requests.length,
    100,
    `the run must reach the 100 cap and be refused at 101, saw ${transport.requests.length}`,
  );
});

test('W77S: an Ollama seat that fails is re-run once on the fallback route', async () => {
  const scripted = new ScriptedTransport({ script: 'consensus' });
  const failingSeat = SEAT_IDS[5];
  let primaryCalls = 0;
  const primary: ModelTransport = {
    generate: async (request) => {
      if (request.seat_id === failingSeat) {
        primaryCalls += 1;
        scripted.requests.push(request);
        throw new TransportDispatchError('rate limited by the local daemon', {
          retryable: true,
        });
      }
      return scripted.generate(request);
    },
  };
  const fallbackSnapshot = routeSnapshot('openrouter-configured', 'route-b');
  const h = harness('ollama-fallback', scripted, {
    providerSlug: 'ollama',
    resolveTransport: (snapshot) =>
      snapshot.routeId === 'route-b' ? scripted : primary,
  });
  h.service.repositories.createSession(
    h.owner,
    storedSession('medium', SEAT_IDS, 'sess-w77s-fallback'),
  );
  const grantId = h.grantFor('sess-w77s-fallback');
  // The grant's route pin is a security invariant, so the fallback
  // route carries its own approved grant.
  const fallbackGrantId = h.grantFor('sess-w77s-fallback', CEILINGS, fallbackSnapshot);
  const result = await h.service.runSession(h.worker, 'sess-w77s-fallback', {
    grant_id: grantId,
    route_snapshot: h.snapshot,
    fallback_route_snapshot: fallbackSnapshot,
    fallback_grant_id: fallbackGrantId,
  });

  assert.equal(result.status, 'completed');
  // The failing seat's primary attempts (initial + one bounded retry)
  // never committed a card; the fallback pass is the one that did.
  assert.equal(primaryCalls, 2);
  const cards = h.service.repositories.listCards(h.worker, 'sess-w77s-fallback');
  assert.equal(
    cards.filter((c) => c.seat_id === failingSeat && c.round === 1).length,
    1,
  );
  const fallbackJobs = h.service.runner
    .listSessionJobs(h.worker, 'sess-w77s-fallback')
    .filter((job) => job.phase_job_key.endsWith(':fallback'));
  assert.equal(fallbackJobs.length, 1);
  assert.ok(fallbackJobs[0].phase_job_key.startsWith('round-1:'));
});

test('W77S: blocked reasons name the challenge pass of a council size', () => {
  const reason = buildBlockedReason({
    state: 'BLOCKED',
    mode: 'heavy',
    seat_ids: [...SEAT_IDS],
    cards: [
      ...SEAT_IDS.map((seatId) => ({ card_kind: 'advisor', round: 1, seat_id: seatId })),
      ...SEAT_IDS.map((seatId) => ({ card_kind: 'advisor', round: 2, seat_id: seatId })),
      ...SEAT_IDS.slice(0, 8).map((seatId) => ({ card_kind: 'advisor', round: 3, seat_id: seatId })),
    ],
    failures: [],
    events: [],
  });
  assert.ok(reason);
  assert.equal(reason.missing_round, 3);
  assert.match(reason.detail, /round 3 \(challenge pass\)/);
  assert.deepEqual(reason.missing_seats, [SEAT_IDS[8]]);
});
