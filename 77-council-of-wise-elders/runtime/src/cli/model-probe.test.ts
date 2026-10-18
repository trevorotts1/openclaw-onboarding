/**
 * WER-006 remainder tests: the bounded capability probe.
 *
 * Runner (the runtime's own runner):
 *   node --import tsx --test src/cli/model-probe.test.ts
 *
 * Tier A only. These are simulated-shim and local subprocess tests: no
 * live provider probe, no real transport capture, no network traffic, no
 * credentials, no paid call. Those are deferred to WER-026/027 and are
 * NOT claimed here.
 *
 * Proven here:
 * - a snapshot failing verifyRouteSnapshotHash never spawns (spawn count 0);
 * - a time-out yields attempted-but-not-answered with unknown cost still
 *   reserved (state 'unknown', still counted, never zeroed);
 * - malformed output yields answered-but-not-schema-qualified and never
 *   callable;
 * - a non-probe-purpose grant is refused by the existing admission path
 *   before dispatch (spawn count 0, no reservation row);
 * - the reservation is committed BEFORE dispatch (observed from inside
 *   the spawn shim);
 * - a single token is answered but never qualified, and the result says a
 *   complete Council is not qualified;
 * - the only modified files in the worktree are the two owned files.
 */

import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test, { after } from 'node:test';

import {
  canonicalHash,
  type RunCeilings,
  type ScopeFields,
  type SessionStateRecord,
} from '../contracts/index.js';
import { buildSampleSession } from './fixture-transport.js';
import type { StoredSession } from './host-ports.js';
import { DurableBudgetService, type PinnedRouteSnapshot } from '../budgets/index.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import { envelopeFromScope, type AuthorizationEnvelope } from '../persistence/envelope.js';
import { COUNCIL_SCHEMA_SQL } from '../persistence/index.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import { CouncilDatabase } from '../persistence/sqlite.js';
import { freezeRouteSnapshot, type CouncilRouteSnapshot } from '../providers/route-snapshot.js';
import type { CouncilRouteSelection } from '../providers/selection.js';
import {
  ApprovalFrontDoor,
  RunAdmissionService,
  RunAuthorizationService,
  type RunGrantRecord,
  type TrustedPrincipal,
} from '../authorization/index.js';
import { ModelProbe, PROBE_ANSWER_SCHEMA, PROBE_QUALIFICATION_NOTE } from './model-probe.js';

const scratch = mkdtempSync(join(tmpdir(), 'operator-W06-U002-'));
after(() => {
  rmSync(scratch, { recursive: true, force: true });
});

// --------------------------------------------------------------- fixtures

let nowIso = '2026-10-18T12:00:00.000Z';
const clock = { nowUtc: () => nowIso };
let idCounter = 0;
const ids = { newId: () => `probe-id-${(idCounter += 1).toString().padStart(4, '0')}` };

const ROUTE_POLICY_SHA256 = canonicalHash({ policy: 'probe-route-policy' });

function scope(): ScopeFields {
  return {
    tenant_id: 'tenant-probe',
    company_id: 'company-probe',
    installation_id: 'install-probe',
    owner_subject: 'owner-probe',
  };
}

function principal(): TrustedPrincipal {
  const s = scope();
  return {
    tenant_id: s.tenant_id,
    company_id: s.company_id,
    installation_id: s.installation_id,
    subject: s.owner_subject ?? 'owner-probe',
    channel: 'local_owner',
    support_access: false,
  };
}

function storedSession(sessionScope: ScopeFields): StoredSession {
  const sample = buildSampleSession();
  const spec = { ...sample.spec, session_id: 'sess-probe' };
  const brief = { ...sample.brief, session_id: 'sess-probe' };
  spec.brief_sha256 = canonicalHash(brief);
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: 'sess-probe',
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

function pinnedRouteSnapshot(sessionScope: ScopeFields): PinnedRouteSnapshot {
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'explicit',
    routeId: 'route-probe',
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: 'fixture',
    requestedRoute: 'fixture-route',
    requestedModelOrAlias: 'fixture-model-v1',
    combinationMembers: null,
    reasoning: { requested: 'medium', applied: 'medium', supported: true, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot: {
      contextWindowTokens: 128000,
      maxOutputTokens: 4096,
      capabilities: ['text'],
      supportedReasoningLevels: ['low', 'medium', 'high'],
    },
    credential: {
      state: 'present',
      envVar: 'FIXTURE_API_KEY',
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

function routeSelection(sessionScope: ScopeFields): CouncilRouteSelection {
  return {
    ...pinnedRouteSnapshot(sessionScope),
    selectionSource: 'explicit',
    routeId: 'route-probe',
  } as CouncilRouteSelection;
}

function frozenSnapshot(sessionScope: ScopeFields): CouncilRouteSnapshot {
  return freezeRouteSnapshot({
    selection: routeSelection(sessionScope),
    sessionId: 'sess-probe',
    sessionOwner: sessionScope.owner_subject ?? 'owner-probe',
    host: {
      baseUrl: 'http://127.0.0.1:9',
      configProfile: 'fixture-profile',
      apiFamily: 'openai_compatible',
    },
    reasoning: {
      requested: 'medium',
      supported: ['low', 'medium', 'high'],
      applied: 'medium',
      limitation: null,
      paramStyle: 'reasoning_effort',
    },
    capabilityVersion: 'cap-1',
    policySha256: '0'.repeat(64),
    limits: { requestsPerMinute: null, tokensPerMinute: null, maxConcurrency: null },
    createdAt: nowIso,
  });
}

function ceilings(): RunCeilings {
  return {
    max_provider_requests: 50,
    max_output_repairs: 9,
    max_transport_retries: 8,
    max_input_tokens: null,
    max_output_tokens: null,
    max_money: { amount_minor: 100_000, currency: 'USD' },
  };
}

interface Harness {
  db: CouncilDatabase;
  budget: DurableBudgetService;
  grants: RunAuthorizationService;
  admission: RunAdmissionService;
  frontDoor: ApprovalFrontDoor;
  envelope: AuthorizationEnvelope;
  snapshot: CouncilRouteSnapshot;
}

function compose(label: string): Harness {
  const db = CouncilDatabase.open(join(scratch, `${label}.db`), {
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
  const frontDoor = new ApprovalFrontDoor({ grants, db, clock });
  const s = scope();
  const envelope = envelopeFromScope(s, s.owner_subject ?? 'owner-probe', 'owner', 'write');
  repositories.createSession(envelope, storedSession(s));
  return {
    db,
    budget,
    grants,
    admission,
    frontDoor,
    envelope,
    snapshot: frozenSnapshot(s),
  };
}

function grantFor(
  h: Harness,
  purpose: 'capability_probe' | 'council_run',
  key: string,
): RunGrantRecord {
  const preview = h.frontDoor.preview(h.envelope, {
    session_id: 'sess-probe',
    purpose,
    route_snapshot: h.snapshot.selection as PinnedRouteSnapshot,
    route_policy_sha256: ROUTE_POLICY_SHA256,
    ceilings: ceilings(),
  });
  const outcome = h.frontDoor.approve(h.envelope, principal(), {
    idempotency_key: key,
    session_id: 'sess-probe',
    preview_id: preview.preview_id,
    authority_mode: 'local_interactive_owner',
    interactive_confirmation: true,
    chosen_expires_at: new Date(Date.parse(nowIso) + 3_600_000).toISOString(),
    current_route_snapshot: h.snapshot.selection as PinnedRouteSnapshot,
  });
  const record = h.grants.loadGrantRecord(h.envelope, outcome.receipt.grant_id);
  assert.ok(record, 'the approved grant record must read back');
  return record;
}

function script(name: string, source: string): string {
  const path = join(scratch, name);
  writeFileSync(path, source, 'utf8');
  return path;
}

function nodeInvocation(scriptPath: string): {
  kind: 'native';
  file: string;
  args: string[];
  target: string;
} {
  return {
    kind: 'native',
    file: process.execPath,
    args: [scriptPath],
    target: process.execPath,
  };
}

/** A shim that answers with a harness envelope whose `result` is `text`. */
function answerScript(name: string, text: string): string {
  const encoded = JSON.stringify(JSON.stringify({ result: text }));
  return script(
    name,
    `process.stdin.resume(); process.stdin.on('end', () => { process.stdout.write(${encoded}); });`,
  );
}

function reservationRows(h: Harness, operationId: string): Array<{ state: string }> {
  return h.db.read((handle) =>
    handle
      .prepare(
        `SELECT state FROM council_budget_reservations WHERE operation_id = ? ORDER BY rowid`,
      )
      .all(operationId),
  ) as Array<{ state: string }>;
}

function makeProbe(
  h: Harness,
  grant: RunGrantRecord,
  options: {
    probeId: string;
    snapshot?: CouncilRouteSnapshot;
    invocation?: ReturnType<typeof nodeInvocation>;
    timeoutMs?: number;
    spawnImpl?: typeof spawn;
    releaser?: DurableBudgetService | null;
  },
): ModelProbe {
  return new ModelProbe({
    admission: h.admission,
    envelope: h.envelope,
    grant,
    session_id: 'sess-probe',
    seat_id: 'simon-sinek',
    route_snapshot: options.snapshot ?? h.snapshot,
    lease_epoch: 0,
    probe_id: options.probeId,
    transport: {
      command: 'unused',
      invocation: options.invocation,
      timeoutMs: options.timeoutMs,
      spawnImpl: options.spawnImpl,
      platform: process.platform,
    },
    releaser: options.releaser ?? null,
  });
}

// ------------------------------------------------------------------ tests

test('probe: a snapshot failing verifyRouteSnapshotHash never spawns', async () => {
  const h = compose('refused-snapshot');
  const grant = grantFor(h, 'capability_probe', 'click-snapshot');
  let spawned = 0;
  const tampered = {
    ...h.snapshot,
    snapshotSha256: 'f'.repeat(64),
  } as CouncilRouteSnapshot;

  const probe = makeProbe(h, grant, {
    probeId: 'probe-tampered',
    snapshot: tampered,
    invocation: nodeInvocation(answerScript('never-runs.mjs', '{"never":true}')),
    spawnImpl: ((...args: unknown[]) => {
      spawned += 1;
      return (spawn as unknown as (...a: unknown[]) => ChildProcess)(...args);
    }) as typeof spawn,
  });

  const result = await probe.run();
  assert.equal(result.status, 'refused');
  assert.equal(result.attempted, false);
  assert.equal(result.answered, false);
  assert.equal(result.schema_qualified, false);
  assert.equal(result.callable, false);
  assert.equal(result.qualifies_complete_council, false);
  assert.equal(spawned, 0, 'a tampered snapshot spawns nothing');
  assert.equal(reservationRows(h, 'model-probe:probe-tampered').length, 0);
});

test('probe: a non-probe-purpose grant is refused by admission before dispatch', async () => {
  const h = compose('refused-purpose');
  const runGrant = grantFor(h, 'council_run', 'click-run-purpose');
  let spawned = 0;

  const probe = makeProbe(h, runGrant, {
    probeId: 'probe-wrong-purpose',
    invocation: nodeInvocation(answerScript('never-runs-purpose.mjs', '{"never":true}')),
    spawnImpl: ((...args: unknown[]) => {
      spawned += 1;
      return (spawn as unknown as (...a: unknown[]) => ChildProcess)(...args);
    }) as typeof spawn,
  });

  const result = await probe.run();
  assert.equal(result.status, 'refused');
  assert.equal(result.callable, false);
  assert.equal(result.schema_qualified, false);
  assert.match(result.reason ?? '', /RUN_GRANT_PURPOSE_MISMATCH/);
  assert.equal(spawned, 0, 'a council_run grant never pays for a probe');
  assert.equal(
    reservationRows(h, 'model-probe:probe-wrong-purpose').length,
    0,
    'a refused purpose mints no reservation',
  );
});

test('probe: the reservation is committed BEFORE dispatch', async () => {
  const h = compose('reserve-before-dispatch');
  const grant = grantFor(h, 'capability_probe', 'click-reserve');
  let reservationSeenAtSpawn = -1;
  const operationId = 'model-probe:probe-reserve';

  const probe = makeProbe(h, grant, {
    probeId: 'probe-reserve',
    invocation: nodeInvocation(
      answerScript(
        'answer-ok.mjs',
        JSON.stringify({
          schema_version: PROBE_ANSWER_SCHEMA,
          status: 'ok',
          model_id: 'fixture-model-v1',
        }),
      ),
    ),
    spawnImpl: ((...args: unknown[]) => {
      reservationSeenAtSpawn = reservationRows(h, operationId).length;
      return (spawn as unknown as (...a: unknown[]) => ChildProcess)(...args);
    }) as typeof spawn,
  });

  const result = await probe.run();
  assert.equal(result.status, 'schema_qualified', JSON.stringify(result));
  assert.equal(
    reservationSeenAtSpawn,
    1,
    'the reservation row exists at the exact moment the child is spawned',
  );
  assert.equal(result.admission_state, 'reserved');
  assert.equal(result.reservation.costKnowledge, 'unknown');
  assert.equal(result.reserved, true);
});

test('probe: a timeout is attempted-but-not-answered with unknown cost still reserved', async () => {
  const h = compose('timeout');
  const grant = grantFor(h, 'capability_probe', 'click-timeout');
  const sleeping = script('sleep.mjs', 'setTimeout(() => {}, 30000);');

  const probe = makeProbe(h, grant, {
    probeId: 'probe-timeout',
    invocation: nodeInvocation(sleeping),
    timeoutMs: 150,
  });

  const result = await probe.run();
  assert.equal(result.status, 'attempted');
  assert.equal(result.attempted, true);
  assert.equal(result.answered, false);
  assert.equal(result.schema_qualified, false);
  assert.equal(result.callable, false);
  assert.equal(result.qualifies_complete_council, false);
  assert.equal(result.attempt_disposition, 'potentially_dispatched');
  assert.equal(result.reservation.costKnowledge, 'unknown');

  const rows = reservationRows(h, 'model-probe:probe-timeout');
  assert.equal(rows.length, 1, 'the reservation is never dropped');
  assert.equal(rows[0]?.state, 'unknown', 'unknown completion stays counted, never zero');
  assert.equal(result.reserved, true);
});

test('probe: malformed output is answered but not schema-qualified and never callable', async () => {
  const h = compose('malformed');
  const grant = grantFor(h, 'capability_probe', 'click-malformed');

  const probe = makeProbe(h, grant, {
    probeId: 'probe-malformed',
    invocation: nodeInvocation(answerScript('answer-malformed.mjs', 'this is not json at all')),
  });

  const result = await probe.run();
  assert.equal(result.status, 'answered');
  assert.equal(result.attempted, true);
  assert.equal(result.answered, true);
  assert.equal(result.schema_qualified, false);
  assert.equal(result.callable, false);
  assert.equal(result.answer, null);
  assert.match(result.reason ?? '', /not valid JSON/);
  assert.equal(result.reserved, true);
});

test('probe: a single token is answered but never qualifies a complete Council', async () => {
  const h = compose('single-token');
  const grant = grantFor(h, 'capability_probe', 'click-single-token');

  const probe = makeProbe(h, grant, {
    probeId: 'probe-single-token',
    invocation: nodeInvocation(answerScript('answer-token.mjs', 'ok')),
  });

  const result = await probe.run();
  assert.equal(result.status, 'answered');
  assert.equal(result.answered, true);
  assert.equal(result.schema_qualified, false);
  assert.equal(result.callable, false);
  assert.equal(result.qualifies_complete_council, false);
  assert.equal(result.qualification_note, PROBE_QUALIFICATION_NOTE);
  assert.match(result.reason ?? '', /single token/);
  assert.match(result.reason ?? '', /does not qualify a complete Council/);
});

test('probe: the only modified files are the two owned files', () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const runtimeRoot = resolve(here, '../..');
  let top: string;
  try {
    top = execFileSync('git', ['-C', runtimeRoot, 'rev-parse', '--show-toplevel'], {
      encoding: 'utf8',
    }).trim();
  } catch {
    // A source snapshot without git cannot prove this; do not pretend.
    return;
  }
  const status = execFileSync('git', ['-C', top, 'status', '--porcelain'], {
    encoding: 'utf8',
  });
  const owned = new Set([
    '77-council-of-wise-elders/runtime/src/cli/model-probe.ts',
    '77-council-of-wise-elders/runtime/src/cli/model-probe.test.ts',
  ]);
  for (const line of status.split('\n').filter((l) => l.trim().length > 0)) {
    const path = line.slice(3).trim();
    assert.ok(
      owned.has(path),
      `a file outside the two owned files was modified: ${JSON.stringify(path)}`,
    );
  }
});
