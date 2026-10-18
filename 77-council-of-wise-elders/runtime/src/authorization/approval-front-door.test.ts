/**
 * WER-009 approval front door tests.
 *
 * Runner (the runtime's own test runner):
 *   node --import tsx --test src/authorization/approval-front-door.test.ts
 *
 * Tier A only: no network, no provider dispatch, no credentials, no
 * mounted browser flow, no authenticated real session, no live paid
 * run. Those are DEFERRED and are not claimed here.
 *
 * Proven here:
 * - an exact retry of a full approval command returns the ORIGINAL
 *   committed receipt and creates no second grant;
 * - a changed ceiling, expiry, parent/renewal linkage, or route option
 *   under the same idempotency key conflicts with ZERO writes (the
 *   whole store digest is compared);
 * - session B's preview submitted to session A's approval command
 *   performs zero grant, state, event, or request-key writes even when
 *   the same owner is used;
 * - principal/scope checks reuse the trusted CWE-007 rules;
 * - revoked and expired authority both refuse without mutating;
 * - a new user reaches Start from the approval's idempotency key
 *   without raw JSON and without a fabricated grant id.
 */

import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import {
  canonicalHash,
  type RunCeilings,
  type ScopeFields,
  type SessionStateRecord,
} from '../contracts/index.js';
import { buildSampleSession } from '../cli/fixture-transport.js';
import type { StoredSession } from '../cli/host-ports.js';
import { DurableBudgetService, type PinnedRouteSnapshot } from '../budgets/index.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from '../persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../persistence/index.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import { CouncilDatabase } from '../persistence/sqlite.js';
import { freezeRouteSnapshot, type CouncilRouteSnapshot } from '../providers/route-snapshot.js';
import type { CouncilRouteSelection } from '../providers/selection.js';
import {
  ApprovalFrontDoor,
  RunAuthorizationError,
  RunAuthorizationService,
  type ApprovalCommand,
  type TrustedPrincipal,
} from './index.js';

// -------------------------------------------------------------- fixtures

let nowIso = '2026-10-18T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

function advanceClock(ms: number): void {
  nowIso = new Date(Date.parse(nowIso) + ms).toISOString();
}

function resetClock(): void {
  nowIso = '2026-10-18T12:00:00.000Z';
}

const ROUTE_POLICY_SHA256 = canonicalHash({ policy: 'route-policy-a' });

function scope(overrides: Partial<ScopeFields> = {}): ScopeFields {
  return {
    tenant_id: 'tenant-a',
    company_id: 'company-a',
    installation_id: 'install-a',
    owner_subject: 'owner-1',
    ...overrides,
  };
}

function storedSession(
  sessionId: string,
  sessionScope: ScopeFields,
  options: { visibility?: 'private' | 'company' } = {},
): StoredSession {
  const sample = buildSampleSession();
  const spec = { ...sample.spec, session_id: sessionId };
  if (options.visibility) spec.visibility = options.visibility;
  const brief = { ...sample.brief, session_id: sessionId };
  spec.brief_sha256 = canonicalHash(brief);
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: sessionId,
    mode: spec.mode,
    state: 'DRAFT',
    state_version: 0,
    brief_revision: brief.revision,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: spec.created_at,
  };
  return { spec, brief, scope: sessionScope, state, sample: false };
}

function ownerEnvelope(sessionScope: ScopeFields): AuthorizationEnvelope {
  return envelopeFromScope(sessionScope, sessionScope.owner_subject ?? 'owner-1', 'owner', 'write');
}

function ownerPrincipal(sessionScope: ScopeFields): TrustedPrincipal {
  return {
    tenant_id: sessionScope.tenant_id,
    company_id: sessionScope.company_id,
    installation_id: sessionScope.installation_id,
    subject: sessionScope.owner_subject ?? 'owner-1',
    channel: 'local_owner',
    support_access: false,
  };
}

function routeSnapshot(
  sessionScope: ScopeFields,
  overrides: Partial<PinnedRouteSnapshot> = {},
): PinnedRouteSnapshot {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: 'route-a',
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'provider-a',
    requestedRoute: 'route-a',
    requestedModelOrAlias: 'model-a',
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
      tenantId: sessionScope.tenant_id,
      companyId: sessionScope.company_id,
      installationId: sessionScope.installation_id,
      ownerSubject: sessionScope.owner_subject,
    },
    createdAt: nowIso,
    ...overrides,
  };
}

function routeSelection(
  sessionScope: ScopeFields,
  overrides: Partial<CouncilRouteSelection> = {},
): CouncilRouteSelection {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: 'route-elders-primary',
    routeRevision: 3,
    routeKind: 'fixed_model',
    providerSlug: 'openai_compatible',
    requestedRoute: 'elders.primary',
    requestedModelOrAlias: 'model-a',
    combinationMembers: null,
    reasoning: { requested: 'high', applied: 'high', supported: true, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: 'acct-operator-1',
    capabilitySnapshot: {
      contextWindowTokens: 200000,
      maxOutputTokens: 32000,
      capabilities: ['chat'],
      supportedReasoningLevels: ['low', 'medium', 'high'],
    },
    credential: {
      state: 'present',
      envVar: 'PROVIDER_A_API_KEY',
      source: 'process.env',
      checked: ['process.env'],
    },
    identityLevel: 'configured',
    scope: {
      tenantId: sessionScope.tenant_id,
      companyId: sessionScope.company_id,
      installationId: sessionScope.installation_id,
      ownerSubject: sessionScope.owner_subject,
    },
    createdAt: nowIso,
    ...overrides,
  };
}

function frozenRouteSnapshot(
  sessionScope: ScopeFields,
  overrides: { routeRevision?: number } = {},
): CouncilRouteSnapshot {
  return freezeRouteSnapshot({
    selection: routeSelection(sessionScope, {
      routeRevision: overrides.routeRevision ?? 3,
    }),
    sessionId: 'sess-a',
    sessionOwner: sessionScope.owner_subject ?? 'owner-1',
    host: {
      baseUrl: 'https://api.example.test/v1',
      configProfile: 'operator-default',
      apiFamily: 'openai_compatible',
    },
    reasoning: {
      requested: 'high',
      supported: ['low', 'medium', 'high'],
      applied: 'high',
      limitation: null,
      paramStyle: 'reasoning_effort',
    },
    capabilityVersion: 'catalog-2026-10-18',
    policySha256: 'a'.repeat(64),
    limits: { requestsPerMinute: 60, tokensPerMinute: null, maxConcurrency: 4 },
    createdAt: nowIso,
  });
}

function ceilings(overrides: Partial<RunCeilings> = {}): RunCeilings {
  return {
    max_provider_requests: 50,
    max_output_repairs: 9,
    max_transport_retries: 8,
    max_input_tokens: null,
    max_output_tokens: null,
    max_money: { amount_minor: 100_000, currency: 'USD' },
    ...overrides,
  };
}

interface Harness {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  budget: DurableBudgetService;
  grants: RunAuthorizationService;
  frontDoor: ApprovalFrontDoor;
  session: StoredSession;
  envelope: AuthorizationEnvelope;
  principal: TrustedPrincipal;
}

function compose(label: string): Harness {
  resetClock();
  const db = CouncilDatabase.open(join(tempDir(label), 'council.db'), {
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
  const budget = new DurableBudgetService({ db, clock, ids });
  const grants = new RunAuthorizationService({ db, clock, ids });
  const frontDoor = new ApprovalFrontDoor({ grants, db, clock });
  const sessionScope = scope();
  const session = storedSession('sess-a', sessionScope);
  const envelope = ownerEnvelope(sessionScope);
  repositories.createSession(envelope, session);
  return {
    db,
    repositories,
    budget,
    grants,
    frontDoor,
    session,
    envelope,
    principal: ownerPrincipal(sessionScope),
  };
}

function tempDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `wer009-${label}-`));
}

function addSession(
  h: Harness,
  sessionId: string,
  sessionScope: ScopeFields = scope(),
): StoredSession {
  const session = storedSession(sessionId, sessionScope);
  h.repositories.createSession(
    envelopeFromScope(sessionScope, sessionScope.owner_subject ?? 'owner-1', 'owner', 'write'),
    session,
  );
  return session;
}

function previewFor(
  h: Harness,
  sessionId: string,
  options: { ceilings?: RunCeilings; sessionScope?: ScopeFields } = {},
) {
  const sessionScope = options.sessionScope ?? scope();
  return h.frontDoor.preview(h.envelope, {
    session_id: sessionId,
    route_snapshot: routeSnapshot(sessionScope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: options.ceilings ?? ceilings(),
  });
}

function approvalCommand(
  previewId: string,
  overrides: Partial<ApprovalCommand> = {},
): ApprovalCommand {
  return {
    idempotency_key: 'click-1',
    session_id: 'sess-a',
    preview_id: previewId,
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
    chosen_ceilings: { max_provider_requests: 40 },
    chosen_expires_at: new Date(Date.parse(nowIso) + 3_600_000).toISOString(),
    renews_grant_id: null,
    current_route_snapshot: routeSnapshot(scope()),
    route_options: { reasoning_effort: 'high', fallback: 'none' },
    ...overrides,
  };
}

function isFrontDoorError(code: string) {
  return (error: unknown) =>
    error instanceof RunAuthorizationError && error.code === code;
}

/**
 * Digest of every table an approval or Start could touch. Used to prove
 * a refusal wrote NOTHING, not merely that it threw.
 */
function storeDigest(db: CouncilDatabase): string {
  const rows = (table: string): unknown[] =>
    db.read((handle) =>
      handle.prepare(`SELECT * FROM ${table} ORDER BY rowid`).all(),
    );
  return canonicalHash({
    sessions: rows('council_sessions'),
    approvals: rows('council_approvals'),
    previews: rows('council_run_previews'),
    events: rows('council_events'),
    outbox: rows('council_projection_outbox'),
    request_keys: rows('council_request_keys'),
    jobs: rows('council_jobs'),
    reservations: rows('council_budget_reservations'),
    briefs: rows('council_brief_revisions'),
  });
}

function grantRowCount(h: Harness): number {
  const row = h.db.read((handle) =>
    handle
      .prepare(
        `SELECT COUNT(*) AS n FROM council_approvals WHERE tenant_id = ? AND company_id = ? AND kind = 'run_grant'`,
      )
      .get(h.envelope.tenant_id, h.envelope.company_id),
  ) as { n: number };
  return Number(row.n);
}

function requestKeyCount(h: Harness): number {
  const row = h.db.read((handle) =>
    handle
      .prepare(
        `SELECT COUNT(*) AS n FROM council_request_keys WHERE tenant_id = ? AND source = 'council-run-approval'`,
      )
      .get(h.envelope.tenant_id),
  ) as { n: number };
  return Number(row.n);
}

function setRevocationGeneration(h: Harness, sessionId: string, generation: number): void {
  // revocation_generation is carried in the journaled state record (the
  // council_sessions table does not persist it), so a revocation is
  // recorded through the repository's own state writer, exactly as the
  // session-controls layer does. The event is part of the fixture, and
  // the digest is captured AFTER it.
  const current = h.repositories.getSession(h.envelope, sessionId);
  assert.ok(current, 'fixture session exists');
  h.repositories.writeStateRecord(
    h.envelope,
    {
      ...current.state,
      revocation_generation: generation,
      updated_at: clock.nowUtc(),
    },
    current.state.state_version,
    { type: 'session_state_changed', payload: { reason: 'test_revocation' } },
  );
}

// ------------------------------------------------------------------ tests

test('exact approval retry returns the ORIGINAL committed receipt and creates no second grant', () => {
  const h = compose('retry');
  const preview = previewFor(h, 'sess-a');
  const command = approvalCommand(preview.preview_id);

  const first = h.frontDoor.approve(h.envelope, h.principal, command);
  assert.equal(first.replayed, false);
  assert.equal(first.receipt.session_id, 'sess-a');
  assert.equal(first.receipt.preview_id, preview.preview_id);
  assert.equal(first.receipt.preview_sha256, preview.preview_sha256);
  assert.equal(first.receipt.schema_version, 'wise-elders.approval-receipt/v1');
  assert.equal(grantRowCount(h), 1, 'the preview anchor became the one grant row');
  assert.equal(requestKeyCount(h), 1, 'one committed idempotency row');

  const grantsBefore = h.grants.loadGrantRecord(h.envelope, first.receipt.grant_id);
  const eventsBefore = h.repositories.journal.list(h.envelope, 'sess-a', 0).length;
  const digestBefore = storeDigest(h.db);

  const retry = h.frontDoor.approve(h.envelope, h.principal, command);
  assert.equal(retry.replayed, true, 'the retry replayed the committed receipt');
  assert.deepEqual(
    retry.receipt,
    first.receipt,
    'the retry returns the ORIGINAL receipt byte for byte',
  );
  assert.equal(grantRowCount(h), 1, 'no second grant was created');
  assert.equal(requestKeyCount(h), 1, 'no second idempotency row');
  assert.equal(storeDigest(h.db), digestBefore, 'the retry wrote nothing at all');
  assert.equal(
    h.repositories.journal.list(h.envelope, 'sess-a', 0).length,
    eventsBefore,
    'the retry appended no event',
  );
  assert.deepEqual(
    h.grants.loadGrantRecord(h.envelope, first.receipt.grant_id),
    grantsBefore,
    'the durable grant record is unchanged',
  );
});

test('a changed option under the same idempotency key CONFLICTS with zero writes', () => {
  const h = compose('conflict');
  const preview = previewFor(h, 'sess-a');
  const command = approvalCommand(preview.preview_id);
  h.frontDoor.approve(h.envelope, h.principal, command);
  const digestBefore = storeDigest(h.db);
  const grantsBefore = grantRowCount(h);

  const changed: Array<[string, Partial<ApprovalCommand>]> = [
    ['ceiling', { chosen_ceilings: { max_provider_requests: 41 } }],
    ['expiry', { chosen_expires_at: new Date(Date.parse(nowIso) + 7_200_000).toISOString() }],
    ['parent linkage', { authority_mode: 'existing_standing_grant', standing_parent_grant_id: 'parent-other' }],
    ['renewal linkage', { renews_grant_id: 'grant-renewal-other' }],
    [
      'route option',
      { route_options: { reasoning_effort: 'low', fallback: 'none' } },
    ],
    [
      'route snapshot',
      { route_snapshot: frozenRouteSnapshot(scope(), { routeRevision: 4 }) },
    ],
    [
      're-resolved route',
      { current_route_snapshot: routeSnapshot(scope(), { routeId: 'route-b' }) },
    ],
  ];
  for (const [label, change] of changed) {
    assert.throws(
      () => h.frontDoor.approve(h.envelope, h.principal, { ...command, ...change }),
      isFrontDoorError('RUN_APPROVAL_IDEMPOTENCY_CONFLICT'),
      `${label} change must conflict`,
    );
    assert.equal(storeDigest(h.db), digestBefore, `${label} change wrote nothing`);
    assert.equal(grantRowCount(h), grantsBefore, `${label} change created no grant`);
  }
});

test('session B preview submitted to session A approval command writes nothing, even with the same owner', () => {
  const h = compose('session-association');
  addSession(h, 'sess-b'); // same scope, same owner-1
  const previewB = previewFor(h, 'sess-b');
  const stateABefore = h.repositories.getSession(h.envelope, 'sess-a')!.state;
  const digestBefore = storeDigest(h.db);

  assert.throws(
    () =>
      h.frontDoor.approve(h.envelope, h.principal, {
        idempotency_key: 'click-cross',
        session_id: 'sess-a',
        preview_id: previewB.preview_id,
        authority_mode: 'local_interactive_owner',
        interactive_confirmation: true,
      }),
    isFrontDoorError('RUN_PREVIEW_SESSION_MISMATCH'),
  );
  assert.equal(storeDigest(h.db), digestBefore, 'zero grant, state, event, outbox, key writes');
  assert.equal(requestKeyCount(h), 0);
  assert.equal(
    h.repositories.getSession(h.envelope, 'sess-a')!.state.state_version,
    stateABefore.state_version,
    'session A state is untouched',
  );
  assert.equal(
    h.repositories.getSession(h.envelope, 'sess-b')!.state.state_version,
    0,
    'session B state is untouched',
  );
  const grantsForA = h.db.read((handle) =>
    handle
      .prepare(
        `SELECT COUNT(*) AS n FROM council_approvals WHERE tenant_id = ? AND company_id = ? AND session_id = 'sess-a' AND status = 'active'`,
      )
      .get(h.envelope.tenant_id, h.envelope.company_id),
  ) as { n: number };
  assert.equal(Number(grantsForA.n), 0, 'no active grant exists for session A');

  // The service itself also refuses when the approval name says the
  // session, so direct composition cannot bypass the front door.
  assert.throws(
    () =>
      h.grants.approveRun(h.envelope, previewB.preview_id, {
        principal: h.principal,
        authority_mode: 'local_interactive_owner',
        interactive_confirmation: true,
        expected_session_id: 'sess-a',
      }),
    isFrontDoorError('RUN_PREVIEW_SESSION_MISMATCH'),
  );
  assert.equal(storeDigest(h.db), digestBefore, 'the service refusal also wrote nothing');
});

test('principal and scope checks refuse cross-scope approval and Start', () => {
  const h = compose('principal');
  const preview = previewFor(h, 'sess-a');
  const foreignPrincipal: TrustedPrincipal = {
    ...h.principal,
    company_id: 'company-other',
  };
  const digestBefore = storeDigest(h.db);
  assert.throws(
    () =>
      h.frontDoor.approve(
        h.envelope,
        foreignPrincipal,
        approvalCommand(preview.preview_id, { idempotency_key: 'click-foreign' }),
      ),
    isFrontDoorError('RUN_GRANT_SCOPE_MISMATCH'),
  );
  assert.equal(storeDigest(h.db), digestBefore, 'a foreign principal writes nothing');

  const approved = h.frontDoor.approve(
    h.envelope,
    h.principal,
    approvalCommand(preview.preview_id, { idempotency_key: 'click-scope' }),
  );
  const afterApproval = storeDigest(h.db);
  assert.throws(
    () =>
      h.frontDoor.start(h.envelope, foreignPrincipal, {
        session_id: 'sess-a',
        approval_idempotency_key: 'click-scope',
      }),
    isFrontDoorError('RUN_GRANT_SCOPE_MISMATCH'),
  );
  assert.equal(storeDigest(h.db), afterApproval, 'a foreign Start writes nothing');
  assert.equal(approved.receipt.session_id, 'sess-a');
});

test('revoked authority refuses approval-with-a-dead-preview and Start without mutating', () => {
  const h = compose('revoked');
  const preview = previewFor(h, 'sess-a');
  // Session-level revocation after the preview was frozen.
  setRevocationGeneration(h, 'sess-a', 1);
  const revokeDigest = storeDigest(h.db);
  assert.throws(
    () =>
      h.frontDoor.approve(
        h.envelope,
        h.principal,
        approvalCommand(preview.preview_id, { idempotency_key: 'click-revoked' }),
      ),
    isFrontDoorError('RUN_AUTHORITY_REVOKED'),
  );
  assert.equal(storeDigest(h.db), revokeDigest, 'revoked approval authority wrote nothing');

  // A live approval, then a revoked grant, then Start.
  const h2 = compose('revoked-start');
  const preview2 = previewFor(h2, 'sess-a');
  const approved = h2.frontDoor.approve(
    h2.envelope,
    h2.principal,
    approvalCommand(preview2.preview_id, { idempotency_key: 'click-kill' }),
  );
  h2.grants.revokeRunGrant(h2.envelope, approved.receipt.grant_id, h2.principal);
  const revokedDigest = storeDigest(h2.db);
  assert.throws(
    () =>
      h2.frontDoor.start(h2.envelope, h2.principal, {
        session_id: 'sess-a',
        approval_idempotency_key: 'click-kill',
      }),
    isFrontDoorError('RUN_START_GRANT_REVOKED'),
  );
  assert.equal(storeDigest(h2.db), revokedDigest, 'revoked Start wrote nothing');
});

test('expired authority refuses approval and Start without mutating (no lazy flip on refusal)', () => {
  const h = compose('expired');
  const preview = previewFor(h, 'sess-a');
  advanceClock(15 * 60_000 + 1); // past the preview's 15-minute validity
  const expiredPreviewDigest = storeDigest(h.db);
  assert.throws(
    () =>
      h.frontDoor.approve(
        h.envelope,
        h.principal,
        approvalCommand(preview.preview_id, { idempotency_key: 'click-late' }),
      ),
    isFrontDoorError('RUN_PREVIEW_EXPIRED'),
  );
  assert.equal(storeDigest(h.db), expiredPreviewDigest, 'expired preview approval wrote nothing');

  resetClock();
  const h2 = compose('expired-start');
  const preview2 = previewFor(h2, 'sess-a');
  const approved = h2.frontDoor.approve(
    h2.envelope,
    h2.principal,
    approvalCommand(preview2.preview_id, { idempotency_key: 'click-expiry' }),
  );
  advanceClock(24 * 3_600_000 + 1); // past the grant's 24-hour validity
  const expiredDigest = storeDigest(h2.db);
  const recordBefore = h2.grants.loadGrantRecord(h2.envelope, approved.receipt.grant_id);
  assert.equal(recordBefore?.status, 'active', 'the record is still active before Start observes it');
  assert.throws(
    () =>
      h2.frontDoor.start(h2.envelope, h2.principal, {
        session_id: 'sess-a',
        approval_idempotency_key: 'click-expiry',
      }),
    isFrontDoorError('RUN_START_GRANT_EXPIRED'),
  );
  assert.equal(storeDigest(h2.db), expiredDigest, 'expired Start wrote nothing at all');
  assert.equal(
    h2.grants.loadGrantRecord(h2.envelope, approved.receipt.grant_id)?.status,
    'active',
    'the refusal did not lazily flip the record; a refusal is not a state transition',
  );
});

test('Start is reachable from the approval idempotency key with no raw JSON and no grant id', () => {
  const h = compose('start-handle');
  const preview = previewFor(h, 'sess-a');
  const approved = h.frontDoor.approve(
    h.envelope,
    h.principal,
    approvalCommand(preview.preview_id, { idempotency_key: 'click-start' }),
  );

  // A new user supplies only the session and the approval key. No
  // grant id and no JSON document exist in this call.
  const started = h.frontDoor.start(h.envelope, h.principal, {
    session_id: 'sess-a',
    approval_idempotency_key: 'click-start',
  });
  assert.equal(started.grant.grant_id, approved.receipt.grant_id);
  assert.equal(started.start.session_id, 'sess-a');
  assert.equal(started.start.grant_ref, approved.receipt.grant_id);
  assert.deepEqual(
    started.receipt,
    approved.receipt,
    'Start serves the ORIGINAL receipt',
  );

  // Idempotent by construction: the second Start returns the same
  // grant and writes nothing.
  const digestBefore = storeDigest(h.db);
  const again = h.frontDoor.start(h.envelope, h.principal, {
    session_id: 'sess-a',
    approval_idempotency_key: 'click-start',
  });
  assert.deepEqual(again, started);
  assert.equal(storeDigest(h.db), digestBefore, 'Start retry wrote nothing');

  // A fabricated / unknown approval key is refused, not guessed.
  assert.throws(
    () =>
      h.frontDoor.start(h.envelope, h.principal, {
        session_id: 'sess-a',
        approval_idempotency_key: 'fabricated-grant-id',
      }),
    isFrontDoorError('RUN_START_APPROVAL_NOT_FOUND'),
  );
  assert.equal(storeDigest(h.db), digestBefore, 'an unknown Start key wrote nothing');
});

test('WER-006 route snapshot input is verified and bound into the approval fingerprint', () => {
  const h = compose('route-snapshot');
  const preview = previewFor(h, 'sess-a');
  const frozen = frozenRouteSnapshot(scope());
  const command = approvalCommand(preview.preview_id, {
    idempotency_key: 'click-route',
    route_snapshot: frozen,
  });
  const first = h.frontDoor.approve(h.envelope, h.principal, command);
  assert.equal(first.replayed, false);
  const digestBefore = storeDigest(h.db);

  // Same command replays; a changed route option conflicts.
  assert.equal(h.frontDoor.approve(h.envelope, h.principal, command).replayed, true);
  assert.equal(storeDigest(h.db), digestBefore, 'route retry wrote nothing');
  assert.throws(
    () =>
      h.frontDoor.approve(h.envelope, h.principal, {
        ...command,
        route_options: { reasoning_effort: 'medium', fallback: 'none' },
      }),
    isFrontDoorError('RUN_APPROVAL_IDEMPOTENCY_CONFLICT'),
  );
  assert.equal(storeDigest(h.db), digestBefore, 'changed route option wrote nothing');

  // A tampered frozen snapshot never reaches approval.
  const tampered = { ...frozen, snapshotSha256: 'b'.repeat(64) };
  assert.throws(
    () =>
      h.frontDoor.approve(h.envelope, h.principal, {
        ...command,
        idempotency_key: 'click-tampered',
        route_snapshot: tampered,
      }),
    isFrontDoorError('RUN_INVALID_INPUT'),
  );
  assert.equal(storeDigest(h.db), digestBefore, 'a tampered route snapshot wrote nothing');
});
