/**
 * W28 convening driver: convening = approval, background deliberation over
 * the service's own store with the durable worker supervisor running at
 * the same time, and the runSession claim-loop race fix.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  SEAT_IDS,
  type ModelPolicy,
  type ScopeFields,
  type SeatId,
} from '../src/contracts/index.js';
import { buildSampleSession, DeterministicFixtureTransport } from '../src/cli/fixture-transport.js';
import type {
  ModelTransport,
  TransportRequest,
  TransportResponse,
} from '../src/cli/host-ports.js';
import type { TrustedPrincipal } from '../src/authorization/index.js';
import type { PinnedRouteSnapshot } from '../src/budgets/index.js';
import type {
  CandidateHeader,
  MaterialCandidate,
  MaterialCatalog,
} from '../src/context/index.js';
import { COUNCIL_SCHEMA_SQL } from '../src/persistence/index.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';
import {
  startCouncilWorkers,
  stopCouncilWorkers,
  TransportDispatchError,
  type RunnerTimers,
} from '../src/queue/index.js';
import type { EvidenceUnit, SourceRecord } from '../src/sources/index.js';
import {
  composeDeliberationService,
  type DeliberationService,
  type RunSessionResult,
} from '../src/protocol/composition.js';
import {
  createCouncilDriver,
  DriverRefusal,
  type ResolvedSessionRoute,
  type RouteChoiceRequest,
} from '../src/service/driver.js';

const clock = { nowUtc: () => '2026-10-19T12:00:00.000Z' };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(5, '0')}` };

const SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'install-a',
  owner_subject: 'owner-1',
};
const COMPANY_SCOPE: ScopeFields = { ...SCOPE, owner_subject: null };
const FIXTURE_ROUTE = 'route-fixture';

const principal: TrustedPrincipal = {
  tenant_id: SCOPE.tenant_id,
  company_id: SCOPE.company_id,
  installation_id: SCOPE.installation_id,
  subject: 'owner-1',
  channel: 'local_owner',
  support_access: false,
};

function candidate(seatId: SeatId): MaterialCandidate {
  const source: SourceRecord = {
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
  const unit: EvidenceUnit = {
    evidence_id: `ev-${seatId}`,
    source_id: source.source_id,
    source_version: source.content_sha256,
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
    source_id: source.source_id,
    allowed_scope: source.allowed_scope,
    sha256: canonicalHash(unit),
  };
  return { header, source, unit };
}

class ListCatalog implements MaterialCatalog {
  private readonly all = SEAT_IDS.map(candidate);
  listCandidateHeaders() {
    return this.all.map((c) => c.header);
  }
  loadCandidate(evidenceId: string) {
    return this.all.find((c) => c.header.evidence_id === evidenceId) ?? null;
  }
}

function snapshot(): PinnedRouteSnapshot {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: FIXTURE_ROUTE,
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'provider-a',
    requestedRoute: FIXTURE_ROUTE,
    requestedModelOrAlias: 'fixture-model',
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
    credential: { state: 'present', envVar: 'PROVIDER_A_API_KEY', source: 'process.env', checked: ['process.env'] },
    identityLevel: 'configured',
    scope: {
      tenantId: SCOPE.tenant_id,
      companyId: SCOPE.company_id,
      installationId: SCOPE.installation_id,
      ownerSubject: SCOPE.owner_subject,
    },
    createdAt: clock.nowUtc(),
  };
}

const MODEL_POLICY: ModelPolicy = {
  selection: 'explicit',
  route_id: FIXTURE_ROUTE,
  requested_model_id: 'fixture-model',
  reasoning_preference: null,
  fallback_policy: 'none',
};

async function resolveFixtureRoute(_req: RouteChoiceRequest): Promise<ResolvedSessionRoute> {
  return {
    snapshot: snapshot(),
    model_policy: MODEL_POLICY,
    model_label: 'fixture-model',
    selection_source: 'explicit',
    harness: null,
  };
}

class RecordingTransport implements ModelTransport {
  readonly requests: TransportRequest[] = [];
  private readonly fixture = new DeterministicFixtureTransport();
  constructor(private readonly script?: (r: TransportRequest) => Promise<TransportResponse>) {}
  async generate(request: TransportRequest): Promise<TransportResponse> {
    this.requests.push(request);
    return this.script ? this.script(request) : this.fixture.generate(request);
  }
}

interface Rig {
  dir: string;
  service: DeliberationService;
  owner: ReturnType<typeof envelopeFromScope>;
  worker: ReturnType<typeof envelopeFromScope>;
  transport: RecordingTransport;
  auditLogPath: string;
  settled: Array<{ id: string; result: RunSessionResult | { status: 'error'; code: string } }>;
}

function rig(
  label: string,
  opts: {
    transport?: RecordingTransport;
    catalog?: MaterialCatalog | null;
    routeBudget?: boolean;
    timers?: RunnerTimers;
    roundWaitPollMs?: number;
  } = {},
): Rig {
  const dir = mkdtempSync(join(tmpdir(), `w28-driver-${label}-`));
  const db = CouncilDatabase.open(join(dir, 'council.db'), {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const transport = opts.transport ?? new RecordingTransport();
  const service = composeDeliberationService({
    db,
    clock,
    ids,
    catalog: opts.catalog !== undefined ? opts.catalog : new ListCatalog(),
    resolvePrincipal: () => principal,
    resolveTransport: () => transport,
    routeBudget:
      opts.routeBudget === false
        ? null
        : () => ({ context_limit_bytes: 1_000_000, response_schema_bytes: 2_000, output_reserve_bytes: 8_000 }),
    timers: opts.timers,
    roundWaitPollMs: opts.roundWaitPollMs ?? 10,
    workerId: 'council-service-worker',
  });
  return {
    dir,
    service,
    owner: envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write'),
    worker: envelopeFromScope(SCOPE, 'owner-1', 'worker', 'write'),
    transport,
    auditLogPath: join(dir, 'convening-audit.jsonl'),
    settled: [],
  };
}

function driverFor(r: Rig) {
  return createCouncilDriver({
    deliberation: r.service,
    envelope: r.owner,
    scope: SCOPE,
    principal,
    clock,
    ids,
    resolveRoute: resolveFixtureRoute,
    auditLogPath: r.auditLogPath,
    onSettled: (id, result) => r.settled.push({ id, result }),
  });
}

function startWorkers(r: Rig, supervisorId: string) {
  return startCouncilWorkers({
    runner: r.service.runner,
    scopes: [{ envelope: r.worker, worker_id: 'council-service-worker' }],
    supervisor_id: supervisorId,
    poll_interval_ms: 5,
  });
}

function sessionRows(r: Rig): number {
  return r.service.repositories.listSessions(r.owner, {}).length;
}

test('convene({sample}) runs unprompted to COMPLETED with workers running, journaling events and one audit line', async () => {
  const r = rig('golden');
  const workers = startWorkers(r, 'w28-golden');
  const driver = driverFor(r);
  try {
    const accepted = await driver.convene({
      sample: true,
      route: { route_id: FIXTURE_ROUTE },
      requested_by: 'owner-1',
    });
    assert.equal(accepted.sample, true);
    assert.equal(accepted.route_id, FIXTURE_ROUTE);
    assert.equal(accepted.model_label, 'fixture-model');
    assert.equal(accepted.selection_source, 'explicit');
    assert.equal(accepted.session_path, `/council/${accepted.session_id}`);
    assert.equal(accepted.events_path, `/api/council/sessions/${accepted.session_id}/events`);
    await driver.drain();

    assert.equal(r.settled.length, 1);
    const result = r.settled[0]!.result;
    assert.equal(result.status, 'completed');
    const session = r.service.repositories.getSession(r.owner, accepted.session_id);
    assert.equal(session?.state.state, 'COMPLETED');
    assert.equal(session?.sample, true);

    const events = r.service.repositories.journal.list(r.owner, accepted.session_id);
    const sequences = events.map((e) => e.sequence);
    assert.deepEqual(sequences, [...sequences].sort((a, b) => a - b));
    assert.deepEqual(sequences, sequences.map((_, i) => i + 1));
    const types = new Set(events.map((e) => e.type));
    assert.ok(types.has('session_created'));
    assert.ok(events.filter((e) => e.to_state !== null).some((e) => e.to_state === 'COMPLETED'));
    assert.ok([...types].some((t) => /card/.test(t)), `card events in ${[...types]}`);
    assert.ok([...types].some((t) => /verdict/.test(t)), `verdict event in ${[...types]}`);
    // every card came from the transport: 27 requests, 27 cards
    assert.equal(r.service.repositories.listCards(r.owner, accepted.session_id).length, 27);
    assert.equal(r.transport.requests.length, 27);

    // the approval is the convene act: one active grant, no ceiling on money
    const audit = readFileSync(r.auditLogPath, 'utf8').trim().split('\n');
    assert.equal(audit.length, 1);
    const line = JSON.parse(audit[0]!) as Record<string, unknown>;
    assert.equal(line.session_id, accepted.session_id);
    assert.equal(line.grant_id, accepted.grant_id);
    assert.equal(line.approval_basis, 'convening_is_approval (Trevor decision 2026-10-19)');
    assert.equal(line.requested_by, 'owner-1');
    assert.equal(line.route_id, FIXTURE_ROUTE);
  } finally {
    await stopCouncilWorkers(workers);
  }
});

test('a second sample convene gets a distinct session id', async () => {
  const r = rig('second');
  const driver = driverFor(r);
  const a = await driver.convene({ sample: true, route: { route_id: FIXTURE_ROUTE }, requested_by: 'owner-1' });
  await driver.drain();
  const b = await driver.convene({ sample: true, route: { route_id: FIXTURE_ROUTE }, requested_by: 'owner-1' });
  await driver.drain();
  assert.notEqual(a.session_id, b.session_id);
  assert.equal(sessionRows(r), 2);
  assert.equal(readFileSync(r.auditLogPath, 'utf8').trim().split('\n').length, 2);
  assert.deepEqual(r.settled.map((s) => s.result.status), ['completed', 'completed']);
});

test('an unbound catalog refuses COMPOSITION_NOT_READY naming it, creating no session and no grant', async () => {
  const r = rig('unbound', { catalog: null });
  const driver = driverFor(r);
  await assert.rejects(
    driver.convene({ sample: true, route: { route_id: FIXTURE_ROUTE }, requested_by: 'owner-1' }),
    (error: unknown) => {
      assert.ok(error instanceof DriverRefusal);
      assert.equal(error.code, 'COMPOSITION_NOT_READY');
      assert.equal(error.http_status, 503);
      assert.deepEqual(error.detail.unbound, ['material_catalog']);
      assert.doesNotMatch(`${error.message} ${error.recovery}`, /budget|approv/i);
      return true;
    },
  );
  assert.equal(sessionRows(r), 0);
  assert.equal(existsSync(r.auditLogPath), false);
});

test('invalid input is refused typed before anything is written', async () => {
  const r = rig('invalid');
  const driver = driverFor(r);
  const base = { route: { route_id: FIXTURE_ROUTE }, requested_by: 'owner-1' };
  for (const input of [
    { ...base },
    { ...base, sample: true, brief: buildSampleSession().brief },
    { ...base, sample: true, requested_by: '' },
    { ...base, sample: true, mode: 'consult' as const },
  ]) {
    await assert.rejects(driver.convene(input), (e: unknown) => {
      assert.ok(e instanceof DriverRefusal);
      assert.equal(e.code, 'CONVENE_INPUT_INVALID');
      assert.equal(e.http_status, 422);
      return true;
    });
  }
  assert.equal(sessionRows(r), 0);
});

test('a route-choice refusal maps to a typed DriverRefusal and writes nothing', async () => {
  const r = rig('routeerr');
  const driver = createCouncilDriver({
    deliberation: r.service,
    envelope: r.owner,
    scope: SCOPE,
    principal,
    clock,
    ids,
    resolveRoute: async () => {
      throw Object.assign(new Error('Pick a route.'), {
        code: 'ROUTE_CHOICE_REQUIRED',
        recovery: 'Ask the client which model to use.',
      });
    },
    auditLogPath: r.auditLogPath,
  });
  await assert.rejects(driver.convene({ sample: true, route: {}, requested_by: 'owner-1' }), (e: unknown) => {
    assert.ok(e instanceof DriverRefusal);
    assert.equal(e.code, 'ROUTE_CHOICE_REQUIRED');
    assert.equal(e.http_status, 422);
    assert.equal(e.recovery, 'Ask the client which model to use.');
    return true;
  });
  assert.equal(sessionRows(r), 0);
});

test('fresh facts are handed to recordFreshFacts for the new session', async () => {
  const r = rig('facts');
  const seen: Array<[string, number]> = [];
  const driver = createCouncilDriver({
    deliberation: r.service,
    envelope: r.owner,
    scope: SCOPE,
    principal,
    clock,
    ids,
    resolveRoute: resolveFixtureRoute,
    recordFreshFacts: (id, facts) => seen.push([id, facts.length]),
    auditLogPath: r.auditLogPath,
  });
  const accepted = await driver.convene({
    sample: true,
    route: { route_id: FIXTURE_ROUTE },
    requested_by: 'owner-1',
    fresh_facts: [{ claim: 'A claim.', url: 'https://example.test/a', title: null, retrieved_at: clock.nowUtc() }],
  });
  await driver.drain();
  assert.deepEqual(seen, [[accepted.session_id, 1]]);
});

test('a typed transport failure ends BLOCKED with its reason, onSettled receives it, and no card is invented', async () => {
  const transport = new RecordingTransport(async () => {
    throw new TransportDispatchError('provider refused', { retryable: false });
  });
  const r = rig('fail', { transport });
  const workers = startWorkers(r, 'w28-fail');
  const driver = driverFor(r);
  try {
    const accepted = await driver.convene({ sample: true, route: { route_id: FIXTURE_ROUTE }, requested_by: 'owner-1' });
    await driver.drain();
    assert.equal(r.settled.length, 1);
    const result = r.settled[0]!.result;
    assert.equal(result.status, 'incomplete');
    assert.ok(result.status === 'incomplete' && result.detail.length > 0 && result.missing.length > 0);
    assert.equal(r.service.repositories.listCards(r.owner, accepted.session_id).length, 0);
    assert.equal(r.service.repositories.getSession(r.owner, accepted.session_id)?.state.state, 'BLOCKED');
  } finally {
    await stopCouncilWorkers(workers);
  }
});

test('an untyped runSession throw reaches onSettled as an error and leaves the session BLOCKED, not mid-round', async () => {
  const transport = new RecordingTransport(async () => {
    throw new Error('not a typed transport error');
  });
  const r = rig('throw', { transport });
  const driver = driverFor(r);
  const accepted = await driver.convene({ sample: true, route: { route_id: FIXTURE_ROUTE }, requested_by: 'owner-1' });
  await driver.drain();
  assert.deepEqual(r.settled.map((s) => s.result.status), ['error']);
  assert.equal(r.service.repositories.getSession(r.owner, accepted.session_id)?.state.state, 'BLOCKED');
  assert.equal(driver.inFlight(), 0);
});

/** A one-seat consult session with an approved grant, ready for runSession. */
function consultSession(r: Rig, sessionId: string) {
  const sample = buildSampleSession();
  const brief = { ...sample.brief, session_id: sessionId, brief_id: `brief-${sessionId}` };
  const spec = {
    ...sample.spec,
    session_id: sessionId,
    mode: 'consult' as const,
    seat_ids: ['tiffany-aliche' as SeatId],
    brief_sha256: canonicalHash(brief),
    model_policy: MODEL_POLICY,
  };
  r.service.repositories.createSession(r.owner, {
    spec,
    brief,
    scope: { ...SCOPE },
    state: {
      schema_version: 'wise-elders.session-state/v1',
      session_id: sessionId,
      mode: 'consult',
      state: 'DRAFT',
      state_version: 0,
      brief_revision: 1,
      resume_phase: null,
      cancel_generation: 0,
      revocation_generation: 0,
      attempt: 1,
      lease_epoch: 0,
      archived: false,
      updated_at: clock.nowUtc(),
    },
    sample: true,
  });
  const snap = snapshot();
  const preview = r.service.grants.previewRun(r.owner, {
    session_id: sessionId,
    purpose: 'council_run',
    route_snapshot: snap,
    route_policy_sha256: canonicalHash({ route_snapshot: snap }),
    ceilings: {
      max_provider_requests: 62,
      max_output_repairs: 27,
      max_transport_retries: 8,
      max_input_tokens: null,
      max_output_tokens: null,
      max_money: null,
    },
  });
  const grant = r.service.grants.approveRun(r.owner, preview.preview_id, {
    principal,
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  return { snap, grantId: grant.grant_id };
}

/** Run `afterEnqueue` the instant the round's jobs are enqueued. */
function afterEnqueue(r: Rig, hook: () => void): void {
  const enqueue = r.service.runner.enqueueOperation.bind(r.service.runner);
  r.service.runner.enqueueOperation = ((...args: Parameters<typeof enqueue>) => {
    const job = enqueue(...args);
    hook();
    return job;
  }) as typeof enqueue;
}

test('race: a worker that claimed the round job first no longer makes runSession report incomplete', async () => {
  const r = rig('race');
  const workers = startWorkers(r, 'w28-race');
  const { snap, grantId } = consultSession(r, 'sess-w28-race');
  let supervisorClaimed = false;
  // The supervisor wins the claim: wake it the instant the job is enqueued.
  afterEnqueue(r, () => {
    workers.wake();
    supervisorClaimed = true;
  });
  try {
    const result = await r.service.runSession(r.worker, 'sess-w28-race', {
      grant_id: grantId,
      route_snapshot: snap,
    });
    assert.equal(supervisorClaimed, true);
    assert.equal(result.status, 'completed', JSON.stringify(result));
    assert.equal(r.transport.requests.length, 1);
    const jobs = r.service.runner.listSessionJobs(r.worker, 'sess-w28-race');
    assert.deepEqual(jobs.map((j) => j.state), ['succeeded']);
  } finally {
    await stopCouncilWorkers(workers);
  }
});

test('the wait for another worker is bounded: a lease that never ends gives incomplete after lease TTL x jobs of polling', async () => {
  let delays = 0;
  const r = rig('bounded', {
    timers: { every: () => () => {}, delay: async () => { delays += 1; } },
    roundWaitPollMs: 10_000,
  });
  const service = r.service;
  const { snap, grantId } = consultSession(r, 'sess-w28-bounded');
  afterEnqueue(r, () => {
    // another worker takes the only job and never finishes it
    assert.ok(service.runner.claimNextOperation(r.worker, 'sess-w28-bounded', 'stuck-other-worker'));
  });
  const result = await service.runSession(r.worker, 'sess-w28-bounded', {
    grant_id: grantId,
    route_snapshot: snap,
  });
  assert.equal(result.status, 'incomplete');
  assert.equal(delays, 6, 'ceil(60000ms lease TTL x 1 job / 10000ms poll)');
  assert.equal(r.transport.requests.length, 0);
});
