/**
 * CWE-050 protocol services tests: session controls, history,
 * outcomes, and settings over the accepted stores, plus the
 * store-layer transitionState reconciliation (CWE-027 carried item).
 *
 * Section 35 contracts exercised on the portable side:
 * - T055: repeated pause/cancel are idempotent; resume of a session
 *   that is not paused is a precise legal-state conflict.
 * - T058: a stale expected state version cannot overwrite a newer
 *   transition (precise conflict naming both versions).
 * - T076 (portable half): history reads create no jobs, no tasks, and
 *   no inference.
 * - T078: an idempotency key with a changed payload conflicts; a
 *   matching repeat returns the recorded outcome.
 * - T079 (portable half): malformed service inputs fail validation
 *   before any state change or model call.
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  SEAT_IDS,
  type ScopeFields,
  type SeatId,
  type SessionSpec,
} from '../src/contracts/index.js';
import { DeterministicFixtureTransport } from '../src/cli/fixture-transport.js';
import type { ModelTransport, StoredSession } from '../src/cli/host-ports.js';
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
import { composeDeliberationService } from '../src/protocol/composition.js';
import { ProtocolError } from '../src/protocol/errors.js';
import {
  CouncilSettingsService,
  InMemorySettingsPersistence,
} from '../src/protocol/settings.js';

const clock = { nowUtc: () => '2026-10-14T12:00:00.000Z' };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

const SESSION_SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'install-a',
  owner_subject: 'owner-1',
};

function principal(): TrustedPrincipal {
  return {
    tenant_id: 'tenant-a',
    company_id: 'company-a',
    installation_id: 'install-a',
    subject: 'owner-1',
    channel: 'local_owner',
    support_access: false,
  };
}

function seatCandidate(seatId: SeatId): MaterialCandidate {
  const src: SourceRecord = {
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
    source_id: src.source_id,
    source_version: src.content_sha256,
    locator: { kind: 'section', value: 'Part 1, Chapter 1' },
    kind: 'concept',
    mark: 'direct_teaching',
    original_speaker: seatId,
    excerpt: null,
    paraphrase: `Material for ${seatId}.`,
    claim_ids: [`claim-${seatId}-1`],
    seat_id: seatId,
  };
  const header: CandidateHeader = {
    evidence_id: unit.evidence_id,
    seat_id: seatId,
    scope: { ...SESSION_SCOPE, owner_subject: null },
    visibility: 'company',
    source_id: src.source_id,
    allowed_scope: src.allowed_scope,
    sha256: canonicalHash(unit),
  };
  return { header, source: src, unit };
}

const catalog: MaterialCatalog = {
  listCandidateHeaders: () => [seatCandidate('tiffany-aliche').header],
  loadCandidate: (id) =>
    id === 'ev-tiffany-aliche' ? seatCandidate('tiffany-aliche') : null,
};

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
      tenantId: 'tenant-a',
      companyId: 'company-a',
      installationId: 'install-a',
      ownerSubject: 'owner-1',
    },
    createdAt: '2026-10-14T12:00:00.000Z',
  };
}

class ManualTimers implements RunnerTimers {
  every(): () => void {
    return () => {};
  }
  delay(): Promise<void> {
    return new Promise(() => {});
  }
}

function storedSession(sessionId: string, mode: SessionSpec['mode'] = 'consult'): StoredSession {
  // The canonical contract requires all nine seats in full mode.
  const panel: SeatId[] = mode === 'full' ? [...SEAT_IDS] : ['tiffany-aliche'];
  const brief = {
    schema_version: 'wise-elders.brief/v1' as const,
    brief_id: `brief-${sessionId}`,
    session_id: sessionId,
    revision: 1,
    question: 'Should we pilot the revised offer?',
    facts: [],
    assumptions: [],
    unknowns: [],
    constraints: [],
    options: [
      { id: 'A', label: 'Keep', kind: 'status_quo' as const },
      { id: 'B', label: 'Pilot', kind: 'bounded_test' as const },
    ],
    relevance_weights: Object.fromEntries(panel.map((seatId) => [seatId, 2])),
    critical_domains: [],
    evidence_manifest: [
      {
        evidence_id: 'ev-tiffany-aliche',
        sha256: seatCandidate('tiffany-aliche').header.sha256,
        source_kind: 'book' as const,
        locator: 'section:Part 1, Chapter 1',
      },
    ],
    private_preference_ref: null,
    created_at: '2026-10-14T02:00:00Z',
    display_timezone: 'America/New_York',
  };
  const spec: SessionSpec = {
    schema_version: 'wise-elders.session/v1',
    session_id: sessionId,
    mode,
    visibility: 'company',
    brief_revision: 1,
    brief_sha256: canonicalHash(brief),
    options: [
      { id: 'A', label: 'Keep', kind: 'status_quo' },
      { id: 'B', label: 'Pilot', kind: 'bounded_test' },
    ],
    seat_ids: panel,
    model_policy: {
      selection: 'explicit',
      route_id: 'route-a',
      requested_model_id: 'model-selected-by-client',
      reasoning_preference: null,
      fallback_policy: 'none',
    },
    source_pack_version: 'pack-test-1.0.0',
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

function harness(label: string) {
  const dir = mkdtempSync(join(tmpdir(), `cwe050-svc-${label}-`));
  const db = CouncilDatabase.open(join(dir, 'council.db'), {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const transport: ModelTransport = new DeterministicFixtureTransport();
  const service = composeDeliberationService({
    db,
    clock,
    ids,
    catalog,
    resolvePrincipal: () => principal(),
    resolveTransport: () => transport,
    routeBudget: () => ({
      context_limit_bytes: 1_000_000,
      response_schema_bytes: 2_000,
      output_reserve_bytes: 8_000,
    }),
    timers: new ManualTimers(),
  });
  const owner = envelopeFromScope(SESSION_SCOPE, 'owner-1', 'owner', 'write');
  const worker = envelopeFromScope(SESSION_SCOPE, 'owner-1', 'worker', 'write');
  return { service, owner, worker, dir };
}

function driveToPreparing(
  h: ReturnType<typeof harness>,
  sessionId: string,
): void {
  let version = 0;
  for (const to of ['READY', 'QUEUED', 'PREPARING'] as const) {
    const record = h.service.repositories.transitionState(h.owner, sessionId, to, version);
    version = record.state_version;
  }
}

// ------------------------------------------------------------- tests

test('transitionState: two-step pause records the pre-pause phase at the store layer', () => {
  const h = harness('pause-phase');
  const session = storedSession('sess-svc-pause', 'full');
  h.service.repositories.createSession(h.owner, session);
  let version = 0;
  const go = (to: string) => {
    const record = h.service.repositories.transitionState(
      h.owner,
      session.spec.session_id,
      to as never,
      version,
    );
    version = record.state_version;
    return record;
  };
  go('READY');
  go('QUEUED');
  go('PREPARING');
  go('ROUND_1');
  go('PAUSE_REQUESTED');
  const paused = go('PAUSED');
  // The reconciliation: resume_phase is the pre-pause phase, never
  // PAUSE_REQUESTED (which RESUMING can never target).
  assert.equal(paused.resume_phase, 'ROUND_1');
  go('RESUMING');
  const resumed = go('ROUND_1');
  assert.equal(resumed.state, 'ROUND_1');
});

test('controls: pause/resume/cancel are idempotent with precise conflicts (T055)', () => {
  const h = harness('controls');
  const session = storedSession('sess-svc-controls', 'full');
  h.service.repositories.createSession(h.owner, session);
  driveToPreparing(h, session.spec.session_id);

  const paused = h.service.controls.pause(h.owner, session.spec.session_id);
  assert.equal(paused.record.state, 'PAUSED');
  assert.equal(paused.record.resume_phase, 'PREPARING');
  const pausedAgain = h.service.controls.pause(h.owner, session.spec.session_id);
  assert.equal(pausedAgain.record.state, 'PAUSED');
  assert.equal(pausedAgain.record.state_version, paused.record.state_version);

  const resumed = h.service.controls.resume(h.owner, session.spec.session_id);
  assert.equal(resumed.record.state, 'PREPARING');
  assert.throws(
    () => h.service.controls.resume(h.owner, session.spec.session_id),
    /only a PAUSED or BLOCKED session can resume/,
  );

  const cancelled = h.service.controls.cancel(h.owner, session.spec.session_id);
  assert.equal(cancelled.record.state, 'CANCELLED');
  const cancelledAgain = h.service.controls.cancel(h.owner, session.spec.session_id);
  assert.equal(cancelledAgain.record.state, 'CANCELLED');
  assert.equal(cancelledAgain.record.state_version, cancelled.record.state_version);
  assert.throws(
    () => h.service.controls.pause(h.owner, session.spec.session_id),
    /only an actively processing session can be paused/,
  );
});

test('controls: stale expected version conflicts before anything moves (T058)', () => {
  const h = harness('versions');
  const session = storedSession('sess-svc-version', 'full');
  h.service.repositories.createSession(h.owner, session);
  driveToPreparing(h, session.spec.session_id);
  const before = h.service.repositories.getSession(h.owner, session.spec.session_id);
  assert.throws(
    () =>
      h.service.controls.pause(h.owner, session.spec.session_id, {
        expected_version: (before?.state.state_version ?? 0) + 5,
      }),
    (error: unknown) =>
      error instanceof ProtocolError && error.code === 'SESSION_STATE_CONFLICT',
  );
  const after = h.service.repositories.getSession(h.owner, session.spec.session_id);
  assert.equal(after?.state.state, 'PREPARING');
  assert.equal(after?.state.state_version, before?.state.state_version);
});

test('controls: idempotency keys replay matching outcomes and conflict on changed payloads (T078)', () => {
  const h = harness('idem');
  const session = storedSession('sess-svc-idem', 'full');
  h.service.repositories.createSession(h.owner, session);
  driveToPreparing(h, session.spec.session_id);

  const first = h.service.controls.pause(h.owner, session.spec.session_id, {
    request_key: 'req-pause-1',
  });
  assert.equal(first.replayed, false);
  assert.equal(first.record.state, 'PAUSED');
  const replay = h.service.controls.pause(h.owner, session.spec.session_id, {
    request_key: 'req-pause-1',
  });
  assert.equal(replay.replayed, true);
  assert.equal(replay.record.state, 'PAUSED');
  assert.throws(
    () =>
      h.service.controls.pause(h.owner, session.spec.session_id, {
        request_key: 'req-pause-1',
        expected_version: 99,
      }),
    (error: unknown) =>
      error instanceof ProtocolError && error.code === 'IDEMPOTENCY_CONFLICT',
  );
});

test('history: reads are scope-checked and create no jobs or inference (T076)', async () => {
  const h = harness('history');
  const a = storedSession('sess-svc-hist-a');
  const b = storedSession('sess-svc-hist-b');
  h.service.repositories.createSession(h.owner, a);
  h.service.repositories.createSession(h.owner, b);

  const jobsBefore = h.service.runner.listSessionJobs(h.worker, a.spec.session_id).length;
  const summaries = h.service.history.listSessions(h.owner);
  assert.equal(summaries.length, 2);
  assert.ok(summaries.every((s) => s.state === 'DRAFT'));
  const detail = h.service.history.getSession(h.owner, a.spec.session_id);
  assert.equal(detail.session.spec.session_id, a.spec.session_id);
  const events = h.service.history.listEvents(h.owner, a.spec.session_id);
  assert.ok(events.length >= 1);
  assert.equal(events[0].type, 'session_created');
  const jobsAfter = h.service.runner.listSessionJobs(h.worker, a.spec.session_id).length;
  assert.equal(jobsAfter, jobsBefore, 'reads created no jobs');

  const foreign = envelopeFromScope(
    { ...SESSION_SCOPE, tenant_id: 'tenant-b' },
    'owner-9',
    'owner',
    'read',
  );
  assert.throws(
    () => h.service.history.getSession(foreign, a.spec.session_id),
    (error: unknown) =>
      error instanceof ProtocolError && error.code === 'SESSION_NOT_FOUND',
  );

  // Archive is a visibility flag: archived sessions leave the default
  // list and stay readable when asked for explicitly.
  h.service.controls.setArchived(h.owner, a.spec.session_id, true);
  assert.equal(h.service.history.listSessions(h.owner).length, 1);
  assert.equal(
    h.service.history.listSessions(h.owner, { includeArchived: true }).length,
    2,
  );
});

test('outcomes: reviews attach to a completed verdict, one per horizon (Section 24.5)', async () => {
  const h = harness('outcomes');
  const session = storedSession('sess-svc-outcome');
  h.service.repositories.createSession(h.owner, session);
  const snapshot = routeSnapshot();
  const preview = h.service.grants.previewRun(h.owner, {
    session_id: session.spec.session_id,
    route_snapshot: snapshot,
    route_policy_sha256: canonicalHash({ policy: 'route-policy-a' }),
    ceilings: {
      max_provider_requests: 50,
      max_output_repairs: 9,
      max_transport_retries: 8,
      max_input_tokens: null,
      max_output_tokens: null,
      max_money: { amount_minor: 100_000, currency: 'USD' },
    },
  });
  const grant = h.service.grants.approveRun(h.owner, preview.preview_id, {
    principal: principal(),
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  const run = await h.service.runSession(h.worker, session.spec.session_id, {
    grant_id: grant.grant_id,
    route_snapshot: snapshot,
  });
  assert.equal(run.status, 'completed');

  const review = h.service.outcomes.recordReview(h.owner, session.spec.session_id, {
    horizon: '30d',
    planned_measure: { metric: 'pilot conversion', target: '>= baseline' },
    actual_evidence: { metric: 'pilot conversion', observed: 'above baseline' },
    assessment: { outcome: 'met', notes: 'The pilot met its planned measure.' },
    client_conclusion: 'Proceed to a broader launch decision.',
  });
  assert.equal(review.horizon, '30d');
  assert.equal(review.verdict_label, null, 'a consult verdict carries no label to inherit');
  assert.equal(h.service.outcomes.listReviews(h.owner, session.spec.session_id).length, 1);
  assert.throws(
    () =>
      h.service.outcomes.recordReview(h.owner, session.spec.session_id, {
        horizon: '30d',
        planned_measure: {},
        actual_evidence: {},
        assessment: { outcome: 'met', notes: 'Again.' },
        client_conclusion: null,
      }),
    (error: unknown) =>
      error instanceof ProtocolError && error.code === 'OUTCOME_CONFLICT',
  );
  // Malformed input fails validation before any write (T079).
  assert.throws(
    () =>
      h.service.outcomes.recordReview(h.owner, session.spec.session_id, {
        horizon: '30d',
        planned_measure: {},
        actual_evidence: {},
        assessment: { outcome: 'sideways', notes: 'Nope.' },
        client_conclusion: null,
      } as never),
    (error: unknown) =>
      error instanceof ProtocolError && error.code === 'OUTCOME_INVALID',
  );
  assert.equal(h.service.outcomes.listReviews(h.owner, session.spec.session_id).length, 1);
});

test('settings: scoped, validated, nonsecret by contract (Section 17.2)', () => {
  const service = new CouncilSettingsService(new InMemorySettingsPersistence());
  const scopeA = { tenant_id: 't', company_id: 'c', installation_id: 'i-a' };
  const scopeB = { tenant_id: 't', company_id: 'c', installation_id: 'i-b' };
  // Defaults carry the Section 15.6 ceiling of 50.
  assert.equal(service.getSettings(scopeA).max_session_provider_requests, 50);
  const updated = service.updateSettings(scopeA, {
    ...service.getSettings(scopeA),
    max_session_provider_requests: 25,
  });
  assert.equal(updated.max_session_provider_requests, 25);
  assert.equal(service.getSettings(scopeA).max_session_provider_requests, 25);
  assert.equal(service.getSettings(scopeB).max_session_provider_requests, 50);
  // The schema ceiling binds: 51 is not a legal setting.
  assert.throws(
    () =>
      service.updateSettings(scopeA, {
        ...service.getSettings(scopeA),
        max_session_provider_requests: 51,
      }),
    (error: unknown) =>
      error instanceof ProtocolError && error.code === 'SETTINGS_INVALID',
  );
  // A credential-shaped key can never be stored as a setting.
  assert.throws(
    () =>
      service.updateSettings(scopeA, {
        ...service.getSettings(scopeA),
        api_key: 'sk-live-example',
      }),
    (error: unknown) =>
      error instanceof ProtocolError && error.code === 'SETTINGS_INVALID',
  );
  assert.equal(service.getSettings(scopeA).max_session_provider_requests, 25);
});
