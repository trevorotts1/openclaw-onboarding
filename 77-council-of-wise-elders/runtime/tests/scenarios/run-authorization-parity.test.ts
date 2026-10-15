/**
 * CWE-045 cross-repo parity proof, ONB side (CWE-049 remainder).
 *
 * The ONE canonical RunAuthorizationService must behave identically
 * from the portable runtime and from Command Center consumers: same
 * fences, same reservation semantics, same typed refusals. The
 * scenario definitions live in run-authorization-parity-scenarios.json
 * beside this file; a byte-identical copy lives in Command Center
 * (tests/fixtures/run-authorization-parity-scenarios.json) and its
 * runner (tests/unit/council-cross-repo-parity.test.ts) asserts the
 * same expectations. Both runners pin the scenario file's sha256, so
 * the two sides can never drift into proving different things.
 *
 * Every step outcome is canonical: ok with the named fields, or the
 * typed refusal code. Ids, timestamps, and hashes never appear.
 */

import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  canonicalHash,
  type RunCeilings,
  type ScopeFields,
  type SessionStateRecord,
} from '../../src/contracts/index.js';
import { buildSampleSession } from '../../src/cli/fixture-transport.js';
import type { StoredSession } from '../../src/cli/host-ports.js';
import {
  RunAdmissionService,
  RunAuthorizationError,
  RunAuthorizationService,
  type TrustedPrincipal,
} from '../../src/authorization/index.js';
import { DurableBudgetService, type PinnedRouteSnapshot } from '../../src/budgets/index.js';
import { parsePersistenceConfig } from '../../src/persistence/config.js';
import { envelopeFromScope, type AuthorizationEnvelope } from '../../src/persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../../src/persistence/index.js';
import { CouncilRepositories } from '../../src/persistence/repositories.js';
import { CouncilDatabase } from '../../src/persistence/sqlite.js';

const SCENARIO_FILE_SHA256 = '1c92d43f6bddd5597244aa99fd4ed60581e78084d2d84e1466c89ef48a20ee56';
const scenarioPath = join(
  dirname(fileURLToPath(import.meta.url)),
  'run-authorization-parity-scenarios.json',
);
const scenarioBytes = readFileSync(scenarioPath);
const scenarios = JSON.parse(scenarioBytes.toString('utf8'));

let nowIso = '2026-10-14T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };
const ROUTE_POLICY_SHA256 = canonicalHash({ policy: 'route-policy-a' });

function scopeFields(overrides: Partial<ScopeFields> = {}): ScopeFields {
  return {
    tenant_id: 'tenant-a',
    company_id: 'company-a',
    installation_id: 'install-a',
    owner_subject: 'owner-1',
    ...overrides,
  };
}

function storedSession(sessionId: string, sessionScope: ScopeFields): StoredSession {
  const sample = buildSampleSession();
  const spec = { ...sample.spec, session_id: sessionId };
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

function routeSnapshot(sessionScope: ScopeFields): PinnedRouteSnapshot {
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
  };
}

interface World {
  db: CouncilDatabase;
  grants: RunAuthorizationService;
  admission: RunAdmissionService;
  envelope: AuthorizationEnvelope;
  principal: TrustedPrincipal;
  otherEnvelope: AuthorizationEnvelope;
  sessionScope: ScopeFields;
  previewId: string | null;
  grantId: string | null;
}

function makeWorld(): World {
  nowIso = '2026-10-14T12:00:00.000Z';
  idCounter = 0;
  const dir = mkdtempSync(join(tmpdir(), 'cwe045-parity-'));
  const db = CouncilDatabase.open(join(dir, 'council.db'), {
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
  const sessionScope = scopeFields();
  const envelope = envelopeFromScope(sessionScope, 'owner-1', 'owner', 'write');
  repositories.createSession(envelope, storedSession('sess-1', sessionScope));
  const otherScope = scopeFields({
    company_id: 'company-b',
    installation_id: 'install-b',
    owner_subject: 'owner-2',
  });
  return {
    db,
    grants,
    admission,
    envelope,
    principal: {
      tenant_id: sessionScope.tenant_id,
      company_id: sessionScope.company_id,
      installation_id: sessionScope.installation_id,
      subject: 'owner-1',
      channel: 'local_owner',
      support_access: false,
    },
    otherEnvelope: envelopeFromScope(otherScope, 'owner-2', 'owner', 'write'),
    sessionScope,
    previewId: null,
    grantId: null,
  };
}

type Outcome = Record<string, unknown>;

function attempt(fn: () => Outcome): Outcome {
  try {
    return fn();
  } catch (error) {
    // Canonical typed refusals: the authorization layer throws
    // RunAuthorizationError and the budget layer throws
    // BudgetCapacityError; both carry the stable Section 17.3 code
    // callers branch on. Anything else is an unexpected failure and
    // is recorded as such so the parity diff shows it.
    if (error instanceof RunAuthorizationError) return { ok: false, code: error.code };
    const code = (error as { code?: unknown })?.code;
    if (typeof code === 'string') return { ok: false, code };
    return { ok: false, code: `UNEXPECTED:${error instanceof Error ? error.message : String(error)}` };
  }
}

function runStep(world: World, scenarioId: string, step: Record<string, any>): Outcome | null {
  // Operation keys are unique per (tenant, company) in BOTH repos'
  // canonical schemas, so each scenario namespaces its keys; the
  // transcripts stay comparable because outcomes never carry keys.
  const op = (id: string | undefined) => (id === undefined ? undefined : `${scenarioId}:${id}`);
  const defaults = scenarios.defaults;
  switch (step.do) {
    case 'advance_clock_ms':
      nowIso = new Date(Date.parse(nowIso) + step.ms).toISOString();
      return null;
    case 'preview':
      return attempt(() => {
        const preview = world.grants.previewRun(world.envelope, {
          session_id: 'sess-1',
          purpose: step.purpose,
          route_snapshot: routeSnapshot(world.sessionScope),
          route_policy_sha256: ROUTE_POLICY_SHA256,
          ceilings: { ...defaults.ceilings, ...(step.ceilings ?? {}) } as RunCeilings,
        });
        world.previewId = preview.preview_id;
        return { ok: true };
      });
    case 'approve':
      return attempt(() => {
        const grant = world.grants.approveRun(world.envelope, world.previewId!, {
          principal: world.principal,
          authority_mode: 'local_interactive_owner',
          interactive_confirmation: true,
        });
        world.grantId = grant.grant_id;
        return { ok: true, status: grant.status };
      });
    case 'resolve':
      return attempt(() => {
        const grant = world.grants.resolveRunGrant(world.envelope, world.grantId!, 'sess-1');
        return grant
          ? { ok: true, found: true, status: grant.status }
          : { ok: true, found: false };
      });
    case 'revoke':
      return attempt(() => {
        world.grants.revokeRunGrant(world.envelope, world.grantId!, world.principal);
        return { ok: true };
      });
    case 'admit':
      return attempt(() => {
        const envelope = step.scope === 'other' ? world.otherEnvelope : world.envelope;
        const admission = world.admission.admitOperation(envelope, {
          grant_id: world.grantId!,
          session_id: 'sess-1',
          operation_id: op(step.operation_id),
          kind: step.kind ?? 'provider_request',
          purpose: step.purpose,
          estimate_minor: defaults.estimate_minor,
          currency: defaults.currency,
          lease_epoch: defaults.lease_epoch,
          route_snapshot: routeSnapshot(world.sessionScope),
          original_operation_id: op(step.original_operation_id) ?? null,
        });
        return { ok: true, replayed: admission.replayed };
      });
    case 'consume':
      return attempt(() => {
        world.admission.recordConsumption(world.envelope, {
          grant_id: world.grantId!,
          session_id: 'sess-1',
          operation_id: op(step.operation_id),
          lease_epoch: defaults.lease_epoch,
          outcome: step.outcome,
          actual_minor: step.outcome === 'settled' ? defaults.estimate_minor : undefined,
        });
        return { ok: true };
      });
    case 'count_reservations':
      return attempt(() => {
        const count = world.db.read((handle) => {
          const row = handle
            .prepare('SELECT COUNT(*) AS n FROM council_budget_reservations WHERE session_id = ?')
            .get('sess-1') as { n: number };
          return row.n;
        });
        return { ok: true, count };
      });
    default:
      throw new Error(`unknown parity step: ${step.do}`);
  }
}

test('parity scenario file is the pinned canonical copy', () => {
  const digest = createHash('sha256').update(scenarioBytes).digest('hex');
  assert.equal(digest, SCENARIO_FILE_SHA256);
  assert.equal(scenarios.schema, 'wise-elders.run-authorization-parity/v1');
  for (const scenario of scenarios.scenarios) {
    for (const step of scenario.steps) {
      if (step.do !== 'advance_clock_ms') {
        assert.ok(step.expect, `${scenario.id} step (${step.do}) must pin an expected outcome`);
      }
    }
  }
});

test('run authorization parity scenarios (ONB runtime)', () => {
  const transcript: Array<Record<string, unknown>> = [];
  for (const scenario of scenarios.scenarios) {
    const world = makeWorld();
    scenario.steps.forEach((step: Record<string, any>, index: number) => {
      const outcome = runStep(world, scenario.id, step);
      if (outcome === null) return;
      transcript.push({ scenario: scenario.id, step: index, do: step.do, outcome });
      if (step.expect) {
        assert.deepEqual(
          outcome,
          step.expect,
          `${scenario.id} step ${index} (${step.do}) outcome must equal the pinned expectation`,
        );
      }
    });
  }
  if (process.env.PARITY_TRANSCRIPT_OUT) {
    writeFileSync(process.env.PARITY_TRANSCRIPT_OUT, `${JSON.stringify(transcript, null, 2)}\n`);
  }
});
