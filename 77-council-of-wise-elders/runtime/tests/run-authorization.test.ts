/**
 * CWE-049 tests: the canonical run authorization service
 * (authorization/run-grants.ts) and per-operation admission
 * (authorization/admission.ts), composed over CWE-006's scoped store
 * and CWE-028's DurableBudgetService with a deterministic fake clock.
 *
 * Section 35 contracts owned by CWE-049 (Section 35.14):
 * - T135 (service half): a stored preview is approved into a real
 *   stored grant and resolves; the CLI half lives in
 *   cli-authorization.test.ts (fresh standalone profile end to end).
 * - T136: headless approval without a trusted standing or managed
 *   grant is denied; a fabricated flag value, an environment-style
 *   override, and a model-authored approval object confer no authority
 *   (there is no code path that reads them, and presenting them
 *   changes nothing).
 * - T137: a changed brief, mode, route, pack, evidence-sharing scope,
 *   or limits invalidates the preview/grant hash (brief revision and
 *   route change exercised directly; the remaining fields share the
 *   same comparison path in assertPreviewFresh).
 * - T138: wrong installation, company, principal, or operation purpose
 *   cannot reuse an existing run grant.
 * - T139: grant expiry and revocation fence future admissions; late
 *   accepted provider work is accounted without invented refunds.
 * - T140: renewal and resume preserve consumed and uncertain usage
 *   plus the original session and parent limits; no allowance reset.
 * - T141: a valid, narrowly matching standing grant avoids redundant
 *   approval while forbidding broader scope or external execution.
 * - T142: probe, intake, and follow-up inference require purpose-bound
 *   allowances and enter accounting.
 *
 * Also proven: the full lifecycle (preview, approve, resolve, admit,
 * consume to the ceiling, refusal past it), consumption reconciliation
 * against CWE-028's reservation rows exactly, the journal hash chain
 * over the whole lifecycle, and preview tamper evidence.
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
} from '../src/contracts/index.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import {
  RunAdmissionService,
  RunAuthorizationError,
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
import { CouncilRepositories } from '../src/persistence/repositories.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';

// ------------------------------------------------------------- fixtures

let nowIso = '2026-10-14T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };

function advanceClock(ms: number): void {
  nowIso = new Date(Date.parse(nowIso) + ms).toISOString();
}

function resetClock(): void {
  nowIso = '2026-10-14T12:00:00.000Z';
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

function ownerEnvelope(
  sessionScope: ScopeFields,
  actorSubject = 'owner-1',
): AuthorizationEnvelope {
  return envelopeFromScope(sessionScope, actorSubject, 'owner', 'write');
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

interface Composition {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
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
  const budget = new DurableBudgetService({ db, clock, ids });
  const grants = new RunAuthorizationService({ db, clock, ids });
  const admission = new RunAdmissionService(grants, budget);
  return { db, repositories, budget, grants, admission };
}

function tempDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `cwe049-${label}-`));
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

function setupSession(
  label: string,
  sessionId = 'sess-1',
  sessionScope: ScopeFields = scope(),
  options: { visibility?: 'private' | 'company' } = {},
): Composition & {
  session: StoredSession;
  envelope: AuthorizationEnvelope;
  principal: TrustedPrincipal;
} {
  resetClock();
  const composition = compose(join(tempDir(label), 'council.db'));
  const session = storedSession(sessionId, sessionScope, options);
  const envelope = ownerEnvelope(sessionScope);
  composition.repositories.createSession(envelope, session);
  return {
    ...composition,
    session,
    envelope,
    principal: ownerPrincipal(sessionScope),
  };
}

function previewAndApprove(
  ctx: Composition & { session: StoredSession; envelope: AuthorizationEnvelope; principal: TrustedPrincipal },
  overrides: {
    ceilings?: RunCeilings;
    purpose?: 'council_run' | 'capability_probe' | 'intake_refinement' | 'follow_up';
    routeSnapshot?: PinnedRouteSnapshot;
  } = {},
) {
  const preview = ctx.grants.previewRun(ctx.envelope, {
    session_id: ctx.session.spec.session_id,
    purpose: overrides.purpose,
    route_snapshot: overrides.routeSnapshot ?? routeSnapshot(ctx.session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: overrides.ceilings ?? ceilings(),
  });
  const grant = ctx.grants.approveRun(ctx.envelope, preview.preview_id, {
    principal: ctx.principal,
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  return { preview, grant };
}

function isRunAuth(code: string) {
  return (error: unknown) =>
    error instanceof RunAuthorizationError && error.code === code;
}

function admitArgs(
  session: StoredSession,
  grantId: string,
  operationId: string,
  extra: Record<string, unknown> = {},
) {
  return {
    grant_id: grantId,
    session_id: session.spec.session_id,
    operation_id: operationId,
    kind: 'provider_request' as const,
    estimate_minor: 100,
    currency: 'USD',
    lease_epoch: 0,
    route_snapshot: routeSnapshot(session.scope),
    ...extra,
  };
}

// ------------------------------------------------------------------ tests

test('lifecycle: preview, approve, resolve, admit, consume to the ceiling, refusal past it', () => {
  const ctx = setupSession('lifecycle');
  const { session, envelope } = ctx;
  const preview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings({ max_provider_requests: 3 }),
  });
  assert.equal(preview.purpose, 'council_run');
  assert.equal(
    Date.parse(preview.expires_at) - Date.parse(preview.created_at),
    15 * 60_000,
    'preview validity defaults to 15 minutes',
  );
  // No authority until approved: the prospective grant id resolves null.
  const anchorId = ctx.db.read((handle) =>
    handle
      .prepare(
        `SELECT grant_id FROM council_run_previews WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, preview.preview_id),
  ) as { grant_id: string };
  assert.equal(ctx.grants.resolveRunGrant(envelope, anchorId.grant_id), null);

  const grant = ctx.grants.approveRun(envelope, preview.preview_id, {
    principal: ctx.principal,
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  assert.equal(grant.grant_id, anchorId.grant_id);
  assert.equal(grant.status, 'active');
  assert.equal(grant.authority_mode, 'local_interactive_owner');
  assert.equal(
    Date.parse(grant.expires_at) - Date.parse(grant.created_at),
    24 * 3_600_000,
    'grant validity defaults to 24 hours',
  );
  assert.equal(grant.preview_sha256, preview.preview_sha256);
  assert.deepEqual(ctx.grants.resolveRunGrant(envelope, grant.grant_id, session.spec.session_id), grant);

  // Admit and consume to the count ceiling of 3.
  const a1 = ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-1'));
  assert.equal(a1.state, 'reserved');
  assert.equal(a1.replayed, false);
  const a1Replay = ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-1'));
  assert.equal(a1Replay.replayed, true, 'same operation key replays while the grant stands');
  assert.equal(a1Replay.reservation_id, a1.reservation_id);
  ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-2'));
  ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-3'));
  assert.throws(
    () => ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-4')),
    (error: unknown) =>
      error instanceof Error &&
      error.name === 'BudgetCapacityError' &&
      (error as { code?: string }).code === 'BUDGET_EXHAUSTED',
    'the fourth admission hits the shared ceiling inside CWE-028',
  );

  const consumed = ctx.admission.recordConsumption(envelope, {
    grant_id: grant.grant_id,
    session_id: session.spec.session_id,
    operation_id: 'op-1',
    lease_epoch: 0,
    outcome: 'settled',
    actual_minor: 90,
  });
  assert.equal(consumed.state, 'committed');
  assert.equal(consumed.actual_minor, 90);
  // Reconciliation: recordConsumption totals match the reservation rows exactly.
  const rows = ctx.budget.listReservations(envelope, session.spec.session_id);
  const committedActual = rows
    .filter((r) => r.state === 'committed')
    .reduce((sum, r) => sum + (r.actual_minor ?? 0), 0);
  const outstanding = rows
    .filter((r) => ['reserved', 'committed', 'unknown'].includes(r.state))
    .reduce(
      (sum, r) => sum + (r.state === 'committed' ? (r.actual_minor ?? r.estimate_minor) : r.estimate_minor),
      0,
    );
  assert.equal(consumed.totals.money.committed_actual_minor, committedActual);
  assert.equal(consumed.totals.money.outstanding_minor, outstanding);
  assert.equal(consumed.totals.money.authorized_minor, 100_000);

  const resolved = ctx.grants.resolveRunGrant(envelope, grant.grant_id, session.spec.session_id);
  assert.ok(resolved);
  assert.equal(resolved.consumed.provider_requests, 1);
  assert.equal(resolved.reserved.provider_requests, 2);

  const chain = ctx.repositories.journal.verifyChain(envelope, session.spec.session_id);
  assert.equal(chain.ok, true, 'the whole lifecycle stays on one intact hash chain');
});

test('T139: revocation mid-flight fences replays and new admissions; accepted work still accounts', () => {
  const ctx = setupSession('revoke');
  const { session, envelope } = ctx;
  const { grant } = previewAndApprove(ctx);
  ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-inflight'));

  const revoked = ctx.grants.revokeRunGrant(envelope, grant.grant_id, ctx.principal);
  assert.equal(revoked.status, 'revoked');
  assert.equal(ctx.grants.resolveRunGrant(envelope, grant.grant_id, session.spec.session_id), null);

  // Replay of the earlier admission token is refused after revocation.
  assert.throws(
    () => ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-inflight')),
    isRunAuth('RUN_GRANT_INACTIVE'),
  );
  // And so is any new admission.
  assert.throws(
    () => ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-new')),
    isRunAuth('RUN_GRANT_INACTIVE'),
  );
  // The already-accepted request retains accounting: its consumption is
  // recorded honestly, with the grant's revoked status reported, and no
  // invented refund (the actual charge stands).
  const consumption = ctx.admission.recordConsumption(envelope, {
    grant_id: grant.grant_id,
    session_id: session.spec.session_id,
    operation_id: 'op-inflight',
    lease_epoch: 0,
    outcome: 'settled',
    actual_minor: 100,
  });
  assert.equal(consumption.state, 'committed');
  assert.equal(consumption.grant_status, 'revoked');
  const events = ctx.repositories.journal.list(envelope, session.spec.session_id, 0);
  assert.ok(events.some((e) => e.type === 'grant_revoked'));
  assert.ok(
    events.some(
      (e) => e.type === 'operation_completed' && e.payload.outcome === 'admission_refused',
    ),
    'refusals are journaled',
  );
});

test('T139: grant expiry at 24h fences admissions and is journaled on first observation', () => {
  const ctx = setupSession('expiry');
  const { session, envelope } = ctx;
  const { grant } = previewAndApprove(ctx);
  ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-1'));
  advanceClock(24 * 3_600_000 + 1);
  assert.equal(ctx.grants.resolveRunGrant(envelope, grant.grant_id, session.spec.session_id), null);
  const record = ctx.grants.loadGrantRecord(envelope, grant.grant_id);
  assert.equal(record?.status, 'expired', 'lazy expiry flips the durable record');
  assert.throws(
    () => ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-2')),
    isRunAuth('RUN_GRANT_INACTIVE'),
  );
  const events = ctx.repositories.journal.list(envelope, session.spec.session_id, 0);
  assert.ok(
    events.some(
      (e) => e.type === 'operation_completed' && e.payload.outcome === 'grant_expired',
    ),
  );
});

test('T137: preview dies at 15 minutes and stales immediately on brief revision or route change', () => {
  const ctx = setupSession('stale');
  const { session, envelope } = ctx;
  const preview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  advanceClock(15 * 60_000 + 1);
  assert.throws(
    () =>
      ctx.grants.approveRun(envelope, preview.preview_id, {
        principal: ctx.principal,
        authority_mode: 'local_interactive_owner',
        interactive_confirmation: true,
      }),
    isRunAuth('RUN_PREVIEW_EXPIRED'),
  );

  // Brief revision after preview: stale.
  const ctx2 = setupSession('stale-brief');
  const preview2 = ctx2.grants.previewRun(ctx2.envelope, {
    session_id: ctx2.session.spec.session_id,
    route_snapshot: routeSnapshot(ctx2.session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  const revisedBrief = {
    ...ctx2.session.brief,
    revision: ctx2.session.brief.revision + 1,
    question: 'A materially different question?',
  };
  ctx2.repositories.saveBriefRevision(ctx2.envelope, revisedBrief);
  assert.throws(
    () =>
      ctx2.grants.approveRun(ctx2.envelope, preview2.preview_id, {
        principal: ctx2.principal,
        authority_mode: 'local_interactive_owner',
        interactive_confirmation: true,
      }),
    isRunAuth('RUN_PREVIEW_STALE'),
  );

  // Route change at approval: stale.
  const ctx3 = setupSession('stale-route');
  const preview3 = ctx3.grants.previewRun(ctx3.envelope, {
    session_id: ctx3.session.spec.session_id,
    route_snapshot: routeSnapshot(ctx3.session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  assert.throws(
    () =>
      ctx3.grants.approveRun(ctx3.envelope, preview3.preview_id, {
        principal: ctx3.principal,
        authority_mode: 'local_interactive_owner',
        interactive_confirmation: true,
        current_route_snapshot: routeSnapshot(ctx3.session.scope, { routeId: 'route-b' }),
      }),
    isRunAuth('RUN_PREVIEW_STALE'),
  );
});

test('T137: a tampered preview record is refused at approval', () => {
  const ctx = setupSession('tamper');
  const { session, envelope } = ctx;
  const preview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  ctx.db.write((handle) => {
    handle
      .prepare(
        `UPDATE council_run_previews SET preview_json = ? WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .run(
        JSON.stringify(preview).replace('100000', '999999'),
        envelope.tenant_id,
        envelope.company_id,
        preview.preview_id,
      );
  });
  assert.throws(
    () =>
      ctx.grants.approveRun(envelope, preview.preview_id, {
        principal: ctx.principal,
        authority_mode: 'local_interactive_owner',
        interactive_confirmation: true,
      }),
    isRunAuth('RUN_PREVIEW_TAMPERED'),
  );
});

test('T136: headless and bypass-shaped approvals confer no authority', () => {
  const ctx = setupSession('bypass');
  const { session, envelope } = ctx;
  const preview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });

  // Headless: local owner mode without the terminal confirmation.
  assert.throws(
    () =>
      ctx.grants.approveRun(envelope, preview.preview_id, {
        principal: ctx.principal,
        authority_mode: 'local_interactive_owner',
      }),
    isRunAuth('RUN_AUTHORIZATION_REQUIRED'),
  );
  // An environment-style override presented in the process changes nothing.
  process.env.COUNCIL_APPROVE_ALL = '1';
  try {
    assert.throws(
      () =>
        ctx.grants.approveRun(envelope, preview.preview_id, {
          principal: ctx.principal,
          authority_mode: 'local_interactive_owner',
          interactive_confirmation: false,
        }),
      isRunAuth('RUN_AUTHORIZATION_REQUIRED'),
    );
  } finally {
    delete process.env.COUNCIL_APPROVE_ALL;
  }
  // A model-authored approval object: extra self-asserted fields are
  // not inputs the service reads, so presenting them changes nothing.
  const modelAuthored = {
    principal: ctx.principal,
    authority_mode: 'local_interactive_owner',
    approved: true,
    yes: true,
    grant: 'self-issued',
    signature: 'model-output',
  } as unknown as Parameters<typeof ctx.grants.approveRun>[2];
  assert.throws(
    () => ctx.grants.approveRun(envelope, preview.preview_id, modelAuthored),
    isRunAuth('RUN_AUTHORIZATION_REQUIRED'),
  );
  // A local principal cannot dress up as a managed principal.
  assert.throws(
    () =>
      ctx.grants.approveRun(envelope, preview.preview_id, {
        principal: ctx.principal,
        authority_mode: 'managed_principal',
      }),
    isRunAuth('RUN_AUTHORITY_MODE_MISMATCH'),
  );
  // A council vote is not a run credential: an approval-shaped
  // reference that is not a stored run grant resolves to nothing.
  assert.equal(
    ctx.grants.resolveRunGrant(envelope, 'verdict-ratified-1', session.spec.session_id),
    null,
  );
  assert.throws(
    () =>
      ctx.admission.admitOperation(
        envelope,
        admitArgs(session, 'verdict-ratified-1', 'op-vote'),
      ),
    isRunAuth('RUN_GRANT_NOT_FOUND'),
  );
  // The preview survived every attempt untouched and can still be
  // approved through the real path.
  const grant = ctx.grants.approveRun(envelope, preview.preview_id, {
    principal: ctx.principal,
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  assert.equal(grant.status, 'active');
});

test('T138: wrong session, route, scope, principal, or purpose cannot reuse a grant', () => {
  const ctx = setupSession('binding');
  const { session, envelope } = ctx;
  const other = storedSession('sess-2', session.scope);
  ctx.repositories.createSession(envelope, other);
  const { grant } = previewAndApprove(ctx);

  // Session B cannot spend session A's grant.
  assert.throws(
    () => ctx.admission.admitOperation(envelope, admitArgs(other, grant.grant_id, 'op-x')),
    isRunAuth('RUN_GRANT_SCOPE_MISMATCH'),
  );
  // Route Y cannot spend a route X grant.
  assert.throws(
    () =>
      ctx.admission.admitOperation(
        envelope,
        admitArgs(session, grant.grant_id, 'op-y', {
          route_snapshot: routeSnapshot(session.scope, { routeId: 'route-b' }),
        }),
      ),
    isRunAuth('RUN_GRANT_ROUTE_MISMATCH'),
  );
  // Another installation's envelope sees no grant at all.
  const foreignEnvelope = ownerEnvelope(scope({ installation_id: 'install-b' }));
  assert.equal(
    ctx.grants.resolveRunGrant(foreignEnvelope, grant.grant_id, session.spec.session_id),
    null,
  );
  // A purpose-mismatched operation is refused.
  assert.throws(
    () =>
      ctx.admission.admitOperation(
        envelope,
        admitArgs(session, grant.grant_id, 'op-p', { purpose: 'follow_up' }),
      ),
    isRunAuth('RUN_GRANT_PURPOSE_MISMATCH'),
  );
});

test('T138: a company grant admits nothing private; a non-owner cannot approve a private run', () => {
  const privateScope = scope();
  const ctx = setupSession('private', 'sess-private', privateScope, {
    visibility: 'private',
  });
  const { session, envelope } = ctx;
  const { grant } = previewAndApprove(ctx);
  // Another principal in the same company, with its own envelope: the
  // private session is invisible to it, so the grant resolves null and
  // admission finds no session.
  const colleagueEnvelope = ownerEnvelope(privateScope, 'colleague-1');
  assert.equal(
    ctx.grants.resolveRunGrant(colleagueEnvelope, grant.grant_id, session.spec.session_id),
    null,
  );
  assert.throws(
    () =>
      ctx.admission.admitOperation(
        colleagueEnvelope,
        admitArgs(session, grant.grant_id, 'op-peek'),
      ),
    isRunAuth('RUN_SESSION_NOT_FOUND'),
  );
  // Approval by a non-owner principal is denied outright.
  const preview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  const colleaguePrincipal: TrustedPrincipal = {
    ...ctx.principal,
    subject: 'colleague-1',
  };
  const colleagueWrite = envelopeFromScope(privateScope, 'colleague-1', 'owner', 'write');
  assert.throws(
    () =>
      ctx.grants.approveRun(colleagueWrite, preview.preview_id, {
        principal: colleaguePrincipal,
        authority_mode: 'local_interactive_owner',
        interactive_confirmation: true,
      }),
    (error: unknown) =>
      // Denied either as session-invisible (by design the two cases are
      // indistinguishable) or as a CWE-007 authorization denial.
      (error instanceof RunAuthorizationError &&
        error.code === 'RUN_SESSION_NOT_FOUND') ||
      (error instanceof Error && error.name === 'AuthorizationError'),
  );
});

test('money: a required hard ceiling with no computable bound blocks; the grant money ceiling binds', () => {
  const ctx = setupSession('money');
  const { session, envelope } = ctx;
  assert.throws(
    () =>
      ctx.grants.previewRun(envelope, {
        session_id: session.spec.session_id,
        route_snapshot: routeSnapshot(session.scope),
        route_policy_sha256: ROUTE_POLICY_SHA256,
        ceilings: ceilings({ max_money: null }),
        require_money_bound: true,
      }),
    isRunAuth('RUN_MONEY_UNBOUNDED'),
  );
  const { grant } = previewAndApprove(ctx, {
    ceilings: ceilings({ max_money: { amount_minor: 150, currency: 'USD' } }),
  });
  ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-m1'));
  assert.throws(
    () => ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-m2')),
    (error: unknown) =>
      error instanceof Error &&
      error.name === 'BudgetCapacityError' &&
      (error as { code?: string }).code === 'BUDGET_EXHAUSTED',
    'worst-case reservations may not exceed the grant money ceiling',
  );
  // Unknown completion stays counted at the estimate, never zero.
  const unknown = ctx.admission.recordConsumption(envelope, {
    grant_id: grant.grant_id,
    session_id: session.spec.session_id,
    operation_id: 'op-m1',
    lease_epoch: 0,
    outcome: 'unknown',
  });
  assert.equal(unknown.state, 'unknown');
  assert.equal(unknown.totals.money.outstanding_minor, 100);
  assert.equal(unknown.totals.unknown, 1);
});

test('T141: a valid narrow standing grant approves without a prompt and cannot broaden', () => {
  const ctx = setupSession('standing');
  const { session, envelope } = ctx;
  const parent = ctx.grants.provisionStandingAuthorization(envelope, {
    principal: ctx.principal,
    purpose: 'council_run',
    route_policy_sha256: ROUTE_POLICY_SHA256,
    pack_version: session.spec.source_pack_version,
    seat_ids: [...session.spec.seat_ids],
    ceilings: ceilings(),
    expires_at: '2026-10-15T00:00:00.000Z',
  });
  const preview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings({ max_provider_requests: 10 }),
  });
  // No interactive confirmation: the standing record satisfies approval
  // through the same approveRun path, journaled as such.
  const grant = ctx.grants.approveRun(envelope, preview.preview_id, {
    principal: ctx.principal,
    authority_mode: 'existing_standing_grant',
    standing_parent_grant_id: parent.grant_id,
  });
  assert.equal(grant.authority_mode, 'existing_standing_grant');
  assert.equal(grant.standing_parent_grant_id, parent.grant_id);
  assert.equal(grant.ceilings.max_provider_requests, 10);
  const events = ctx.repositories.journal.list(envelope, session.spec.session_id, 0);
  const issued = events.find(
    (e) => e.type === 'grant_issued' && e.payload.lifecycle === 'approved',
  );
  assert.ok(issued);
  assert.equal(issued.payload.authority_mode, 'existing_standing_grant');
  assert.equal(issued.payload.standing_parent_grant_id, parent.grant_id);

  // The child's expiry is bounded by the parent's earlier expiry, and
  // the child admits while the parent stands.
  assert.ok(Date.parse(grant.expires_at) <= Date.parse(parent.expires_at));
  ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-s1'));

  // A broader request is not covered: lower parent money ceiling.
  const narrowParent = ctx.grants.provisionStandingAuthorization(envelope, {
    principal: ctx.principal,
    purpose: 'council_run',
    route_policy_sha256: ROUTE_POLICY_SHA256,
    pack_version: session.spec.source_pack_version,
    seat_ids: [...session.spec.seat_ids],
    ceilings: ceilings({ max_money: { amount_minor: 10, currency: 'USD' } }),
    expires_at: '2026-10-15T00:00:00.000Z',
  });
  const bigPreview = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  assert.throws(
    () =>
      ctx.grants.approveRun(envelope, bigPreview.preview_id, {
        principal: ctx.principal,
        authority_mode: 'existing_standing_grant',
        standing_parent_grant_id: narrowParent.grant_id,
      }),
    isRunAuth('RUN_GRANT_PARENT_INVALID'),
  );
  // A seat outside the parent's allowlist is not covered.
  const seatNarrowParent = ctx.grants.provisionStandingAuthorization(envelope, {
    principal: ctx.principal,
    purpose: 'council_run',
    route_policy_sha256: ROUTE_POLICY_SHA256,
    pack_version: session.spec.source_pack_version,
    seat_ids: [...session.spec.seat_ids.slice(1)],
    ceilings: ceilings(),
    expires_at: '2026-10-15T00:00:00.000Z',
  });
  const preview2 = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  assert.throws(
    () =>
      ctx.grants.approveRun(envelope, preview2.preview_id, {
        principal: ctx.principal,
        authority_mode: 'existing_standing_grant',
        standing_parent_grant_id: seatNarrowParent.grant_id,
      }),
    isRunAuth('RUN_GRANT_PARENT_INVALID'),
  );
  // Revoking the parent collapses the child's authority at once.
  ctx.grants.revokeRunGrant(envelope, parent.grant_id, ctx.principal);
  assert.equal(ctx.grants.resolveRunGrant(envelope, grant.grant_id, session.spec.session_id), null);
  assert.throws(
    () => ctx.admission.admitOperation(envelope, admitArgs(session, grant.grant_id, 'op-s2')),
    isRunAuth('RUN_GRANT_PARENT_INVALID'),
  );
});

test('T140: renewal inherits consumed and uncertain usage and the original session limits', () => {
  const ctx = setupSession('renewal');
  const { session, envelope } = ctx;
  const tight = ceilings({ max_provider_requests: 3 });
  const first = previewAndApprove(ctx, { ceilings: tight });
  ctx.admission.admitOperation(envelope, admitArgs(session, first.grant.grant_id, 'op-r1'));
  ctx.admission.admitOperation(envelope, admitArgs(session, first.grant.grant_id, 'op-r2'));
  ctx.admission.recordConsumption(envelope, {
    grant_id: first.grant.grant_id,
    session_id: session.spec.session_id,
    operation_id: 'op-r1',
    lease_epoch: 0,
    outcome: 'settled',
    actual_minor: 80,
  });
  ctx.admission.recordConsumption(envelope, {
    grant_id: first.grant.grant_id,
    session_id: session.spec.session_id,
    operation_id: 'op-r2',
    lease_epoch: 0,
    outcome: 'unknown',
  });
  ctx.grants.revokeRunGrant(envelope, first.grant.grant_id, ctx.principal);

  // Renewal for the remaining work: a fresh preview and approval that
  // names the grant it renews. Nothing resets: the session ledger is
  // the same ledger, so the two consumed operations (one settled, one
  // uncertain at estimate) still count against the same ceiling of 3.
  const preview2 = ctx.grants.previewRun(envelope, {
    session_id: session.spec.session_id,
    route_snapshot: routeSnapshot(session.scope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: tight,
  });
  const renewed = ctx.grants.approveRun(envelope, preview2.preview_id, {
    principal: ctx.principal,
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
    renews_grant_id: first.grant.grant_id,
  });
  const record = ctx.grants.loadGrantRecord(envelope, renewed.grant_id);
  assert.equal(record?.proof.renews_grant_id, first.grant.grant_id);
  const snapshot = ctx.budget.snapshot(envelope, session.spec.session_id, renewed.grant_id);
  assert.equal(snapshot.consumed.provider_requests, 2, 'consumed usage is inherited, not reset');
  assert.equal(snapshot.unknown, 1, 'uncertain usage stays counted at its estimate');
  ctx.admission.admitOperation(envelope, admitArgs(session, renewed.grant_id, 'op-r3'));
  assert.throws(
    () => ctx.admission.admitOperation(envelope, admitArgs(session, renewed.grant_id, 'op-r4')),
    (error: unknown) =>
      error instanceof Error &&
      error.name === 'BudgetCapacityError' &&
      (error as { code?: string }).code === 'BUDGET_EXHAUSTED',
    'the original session ceiling of 3 still binds after renewal',
  );
});

test('T142: probe, intake, and follow-up purposes bind their own allowances and enter accounting', () => {
  const ctx = setupSession('purposes');
  const { session, envelope } = ctx;
  for (const purpose of ['capability_probe', 'intake_refinement', 'follow_up'] as const) {
    const { grant } = previewAndApprove(ctx, { purpose });
    assert.equal(grant.purpose, purpose);
    // Each purpose-bound grant admits its own inference and the spend
    // lands in the shared accounting under its own grant.
    const admission = ctx.admission.admitOperation(
      envelope,
      admitArgs(session, grant.grant_id, `op-${purpose}`, { purpose }),
    );
    assert.equal(admission.state, 'reserved');
    const snapshot = ctx.budget.snapshot(envelope, session.spec.session_id, grant.grant_id);
    assert.equal(snapshot.money.authorized_minor, 100_000);
  }
  // A probe grant (provider_request only) refuses a repair kind: kinds
  // outside the purpose's allowance never enter accounting.
  const probe = previewAndApprove(ctx, { purpose: 'capability_probe' });
  assert.throws(
    () =>
      ctx.admission.admitOperation(
        envelope,
        admitArgs(session, probe.grant.grant_id, 'op-repair', {
          kind: 'output_repair',
          purpose: 'capability_probe',
          original_operation_id: 'op-x',
        }),
      ),
    isRunAuth('RUN_GRANT_KIND_NOT_ALLOWED'),
  );
  // All four purposes' reservations coexist in the ONE session ledger.
  const rows = ctx.budget.listReservations(envelope, session.spec.session_id);
  assert.equal(rows.length, 3);
});

test('restart durability: a fresh service instance over the same store resolves the same grant', () => {
  const dir = tempDir('restart');
  const dbPath = join(dir, 'council.db');
  const first = compose(dbPath);
  const sessionScope = scope();
  const session = storedSession('sess-1', sessionScope);
  const envelope = ownerEnvelope(sessionScope);
  first.repositories.createSession(envelope, session);
  const preview = first.grants.previewRun(envelope, {
    session_id: 'sess-1',
    route_snapshot: routeSnapshot(sessionScope),
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  const grant = first.grants.approveRun(envelope, preview.preview_id, {
    principal: ownerPrincipal(sessionScope),
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
  });
  first.db.close();
  const second = compose(dbPath);
  const resolved = second.grants.resolveRunGrant(envelope, grant.grant_id, 'sess-1');
  assert.ok(resolved, 'the grant survives restart; expiry never restarts with the worker');
  assert.equal(resolved.expires_at, grant.expires_at);
  second.db.close();
});
