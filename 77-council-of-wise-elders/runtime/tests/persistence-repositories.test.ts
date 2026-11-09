/**
 * CWE-006 persistence tests: repositories, event journal, projection
 * outbox, configuration surface, authority profile, and the single
 * diagnostic sink over the canonical CWE-005 schema.
 *
 * Primary-owned acceptance contracts (Section 35):
 * - T056: database locks produce bounded backoff and a visible
 *   deferred state; no partial commit.
 * - T133: capture limits, expiry, and byte counters survive
 *   restart/resume; expired diagnostic content is inaccessible before
 *   physical cleanup.
 * - T134: deletion/revocation blocks late diagnostic writes and
 *   removes authorized content/export access, with no false
 *   backup-erasure claim.
 * Unit acceptance proof (Section 34, CWE-006): a crash between
 * state/card/event operations cannot produce a half-committed accepted
 * result, and a duplicate request/commit does not duplicate a card,
 * event sequence, or outbox intent.
 */
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  SCHEMA_VERSIONS,
  type CouncilCard,
  type DiagnosticRetentionPolicy,
  type JobCheckpoint,
  type SessionStateRecord,
  type Verdict,
} from '../src/contracts/index.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import {
  parsePersistenceConfig,
  DEFAULT_PERSISTENCE_CONFIG,
} from '../src/persistence/config.js';
import {
  envelopeFromScope,
  type AuthorizationEnvelope,
} from '../src/persistence/envelope.js';
import {
  PersistenceDeferredError,
  PersistenceError,
} from '../src/persistence/errors.js';
import { COUNCIL_SCHEMA_SQL } from '../src/persistence/index.js';
import { CouncilRepositories } from '../src/persistence/repositories.js';
import { CouncilDatabase } from '../src/persistence/sqlite.js';
import { CouncilStoreService } from '../src/persistence/store.js';

// ------------------------------------------------------------- fixtures

let now = '2026-10-14T12:00:00.000Z';
const clock = { nowUtc: () => now };
let idCounter = 0;
const ids = {
  newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}`,
};

function tempDir(label: string): string {
  return mkdtempSync(join(tmpdir(), `cwe006-${label}-`));
}

function sampleStored(sessionId?: string): StoredSession {
  const sample = buildSampleSession();
  const spec = sessionId
    ? { ...sample.spec, session_id: sessionId }
    : sample.spec;
  const brief = sessionId
    ? { ...sample.brief, session_id: sessionId }
    : sample.brief;
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: spec.session_id,
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
  return { spec, brief, scope: sample.scope, state, sample: false };
}

function ownerEnvelope(session: StoredSession, purpose: AuthorizationEnvelope['purpose'] = 'write'): AuthorizationEnvelope {
  return envelopeFromScope(session.scope, 'owner-1', 'owner', purpose);
}

function openService(dataDir: string, config?: unknown): CouncilStoreService {
  const session = sampleStored();
  return CouncilStoreService.open({
    dataDir,
    clock,
    ids,
    envelope: ownerEnvelope(session),
    config,
  });
}

/** Compose the repository layer directly over a database we control. */
function composeDirect(dbPath: string, busy = { busyTimeoutMs: 500, busyMaxAttempts: 3, busyBaseDelayMs: 10 }) {
  const db = CouncilDatabase.open(dbPath, busy);
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const config = parsePersistenceConfig();
  const repositories = new CouncilRepositories(db, { clock, ids, config });
  return { db, repositories, config };
}

function advisorCard(session: StoredSession, operationId: string): CouncilCard {
  const brief = session.brief;
  return {
    schema_version: 'wise-elders.card/v1',
    session_id: session.spec.session_id,
    brief_revision: brief.revision,
    seat_id: 'simon-sinek',
    input_manifest_sha256: canonicalHash({ manifest: operationId }),
    pack_version: 'pack-fixture-1.0.0',
    card_kind: 'advisor',
    round: 1,
    stance: 'support',
    preferred_option_id: 'B',
    option_scores: brief.options.map((o) => ({
      option_id: o.id,
      score: o.id === 'B' ? 8 : 5,
      rationale: 'Fixture rationale.',
      evidence_ids: ['ev-1'],
    })),
    framework_applications: [],
    decisive_arguments: ['The pilot is the bounded next step.'],
    strongest_objection: 'Retention is unmeasured.',
    conditions: [],
    critical_unknowns: [],
    change_my_mind: 'Evidence the pilot cannot be staffed.',
    challenges_answered: [],
    quotes: [],
    evidence_strength: 'medium',
    minority_position: null,
    host: {
      scope: { ...session.scope },
      operation_id: operationId,
      route_id: 'route-fixture-1',
      session_id: session.spec.session_id,
      stamped_at: '2026-10-14T12:00:00.000Z',
      source_status: 'unverified',
    },
  } as CouncilCard;
}

function scoredVerdict(session: StoredSession): Verdict {
  const base = {
    schema_version: SCHEMA_VERSIONS.verdict,
    result_kind: 'scored' as const,
    session_id: session.spec.session_id,
    verdict_revision: 1,
    recommended_option_id: 'B',
    label: 'WAIT' as const,
    option_scores: [],
    active_weights: {},
    evidence_strength: 'medium' as const,
    hard_constraint_findings: [],
    main_reasons: ['Fixture reason.'],
    strongest_dissent: null,
    accepted_amendments: [],
    rejected_amendments: [],
    critical_unknowns: [],
    prerequisites: [],
    action_proposals: [],
    cheapest_informative_test: null,
    stop_criteria: [],
    review_criteria: [],
    resolution_support: null,
    validation_status: 'valid' as const,
    ratification_status: 'ratified' as const,
    brief_sha256: session.spec.brief_sha256,
  };
  return { ...base, content_sha256: canonicalHash(base) } as Verdict;
}

function grantPolicy(sessionId: string, overrides: Partial<DiagnosticRetentionPolicy> = {}): DiagnosticRetentionPolicy {
  return {
    schema_version: SCHEMA_VERSIONS.diagnosticPolicy,
    enabled: true,
    authorized_by_principal: 'owner-1',
    authorization_kind: 'owner',
    session_id: sessionId,
    capture_window_minutes: 60,
    payload_ttl_hours: 24,
    max_bytes_per_operation: 5 * 1024 * 1024,
    max_bytes_per_session: 25 * 1024 * 1024,
    ...overrides,
  };
}

function isPersistence(code: string) {
  return (err: unknown) => err instanceof PersistenceError && err.code === code;
}

// ------------------------------------------------------------ config

test('config: the locked default surface carries the canonical defaults', () => {
  const config = parsePersistenceConfig();
  assert.equal(config.authority_mode, 'standalone');
  assert.equal(config.settings.max_session_provider_requests, 50);
  assert.equal(config.settings.fallback_policy, 'none');
  assert.equal(config.diagnostics.enabled, false);
  assert.equal(config.diagnostics.capture_window_minutes, 60);
  assert.equal(config.diagnostics.payload_ttl_hours, 24);
  assert.equal(config.diagnostics.max_bytes_per_operation, 5242880);
  assert.equal(config.diagnostics.max_bytes_per_session, 26214400);
  assert.deepEqual(config, DEFAULT_PERSISTENCE_CONFIG);
});

test('config: an unknown key fails precisely, by name, at every level', () => {
  assert.throws(
    () => parsePersistenceConfig({ api_key: 'planted' }),
    (err: unknown) =>
      err instanceof PersistenceError &&
      err.code === 'PERSISTENCE_CONFIG_INVALID' &&
      /api_key/.test(err.message),
  );
  assert.throws(
    () => parsePersistenceConfig({ diagnostics: { secret_token: 'planted' } }),
    (err: unknown) =>
      err instanceof PersistenceError && /diagnostics\.secret_token/.test(err.message),
  );
  assert.throws(
    () => parsePersistenceConfig({ settings: { backdoor: true } }),
    (err: unknown) =>
      err instanceof PersistenceError && /settings\.backdoor/.test(err.message),
  );
});

test('config: an unsafe value fails precisely, with its field path', () => {
  assert.throws(
    () => parsePersistenceConfig({ busy_max_attempts: 99 }),
    (err: unknown) =>
      err instanceof PersistenceError &&
      err.code === 'PERSISTENCE_CONFIG_INVALID' &&
      /busy_max_attempts/.test(err.message),
  );
  assert.throws(
    () => parsePersistenceConfig({ diagnostics: { payload_ttl_hours: 100 } }),
    (err: unknown) =>
      err instanceof PersistenceError && /diagnostics\.payload_ttl_hours/.test(err.message),
  );
  assert.throws(
    () => parsePersistenceConfig({ settings: { max_session_provider_requests: 101 } }),
    (err: unknown) =>
      err instanceof PersistenceError &&
      /settings\.max_session_provider_requests/.test(err.message),
  );
});

// ------------------------------------------------------- authority mode

test('authority: the mode is recorded at first open and a switch is refused', () => {
  const dir = tempDir('authority');
  const service = openService(dir);
  service.createSession(sampleStored());
  service.close();
  assert.equal(service.profile.authority_mode, 'standalone');
  // A later open asking for the other mode is refused, including when
  // it dresses itself as a network-failure fallback.
  assert.throws(
    () => openService(dir, { authority_mode: 'managed' }),
    isPersistence('PERSISTENCE_AUTHORITY_MODE_MISMATCH'),
  );
  // The recorded mode still opens fine.
  const again = openService(dir);
  assert.ok(again.getSession(sampleStored().spec.session_id));
  again.close();
});

test('authority: a fresh managed installation is not silently served standalone', () => {
  const dir = tempDir('authority-managed');
  assert.throws(
    () => openService(dir, { authority_mode: 'managed' }),
    isPersistence('PERSISTENCE_AUTHORITY_MODE_MISMATCH'),
  );
});

test('authority: the recorded profile contains no secret material', () => {
  const dir = tempDir('authority-profile');
  const service = openService(dir);
  service.close();
  const raw = readFileSync(join(dir, 'council-profile.json'), 'utf8');
  const profile = JSON.parse(raw) as Record<string, unknown>;
  assert.deepEqual(Object.keys(profile).sort(), [
    'authority_mode',
    'authority_ref',
    'config_schema_version',
    'installation_id',
    'recorded_at',
    'schema_version',
  ]);
  assert.ok(!/key|token|secret|password/i.test(raw.replace('authority', '')));
});

// ------------------------------------------------------------- sessions

test('sessions: create, read back, and duplicate create is refused', async () => {
  const service = openService(tempDir('sessions'));
  const session = sampleStored();
  await service.createSession(session);
  const loaded = await service.getSession(session.spec.session_id);
  assert.ok(loaded);
  assert.equal(loaded.spec.session_id, session.spec.session_id);
  assert.equal(loaded.state.state, 'DRAFT');
  assert.equal(loaded.brief.revision, session.brief.revision);
  await assert.rejects(
    () => service.createSession(session),
    isPersistence('PERSISTENCE_DUPLICATE_OPERATION'),
  );
  service.close();
});

test('sessions: state compare-and-swap refuses a stale writer', async () => {
  const service = openService(tempDir('cas'));
  const session = sampleStored();
  await service.createSession(session);
  const next: SessionStateRecord = {
    ...session.state,
    state: 'READY',
    state_version: 1,
    updated_at: '2026-10-14T12:05:00.000Z',
  };
  await assert.rejects(
    () => service.updateState(next, 7),
    isPersistence('PERSISTENCE_STATE_CONFLICT'),
  );
  await service.updateState(next, 0);
  const loaded = await service.getSession(session.spec.session_id);
  assert.equal(loaded?.state.state, 'READY');
  assert.equal(loaded?.state.state_version, 1);
  service.close();
});

test('sessions: legal transitions journal, cancel bumps the generation once', async () => {
  const service = openService(tempDir('transitions'));
  const session = sampleStored();
  await service.createSession(session);
  const envelope = ownerEnvelope(session);
  const ready = service.repositories.transitionState(
    envelope,
    session.spec.session_id,
    'READY',
    0,
  );
  assert.equal(ready.state, 'READY');
  const cancelling = service.repositories.transitionState(
    envelope,
    session.spec.session_id,
    'CANCEL_REQUESTED',
    ready.state_version,
  );
  assert.equal(cancelling.cancel_generation, 1);
  const loaded = await service.getSession(session.spec.session_id);
  assert.equal(loaded?.state.cancel_generation, 1);
  // An illegal jump is refused by the canonical transition table.
  assert.throws(() =>
    service.repositories.transitionState(
      envelope,
      session.spec.session_id,
      'ROUND_1',
      cancelling.state_version,
    ),
  );
  service.close();
});

test('sessions: cross-scope reads resolve to nothing and private sessions answer only to their owner', async () => {
  const service = openService(tempDir('scope'));
  const session = sampleStored();
  await service.createSession(session);
  const foreign: AuthorizationEnvelope = {
    tenant_id: 'other-tenant',
    company_id: 'other-company',
    installation_id: 'other-installation',
    actor_subject: 'owner-1',
    actor: 'owner',
    purpose: 'read',
  };
  assert.equal(service.repositories.getSession(foreign, session.spec.session_id), null);

  const priv = sampleStored('sess-private-1');
  priv.spec = { ...priv.spec, visibility: 'private' };
  priv.scope = { ...priv.scope, owner_subject: 'owner-1' };
  service.repositories.createSession(ownerEnvelope(priv), priv);
  const stranger = envelopeFromScope(priv.scope, 'someone-else', 'owner', 'read');
  assert.equal(service.repositories.getSession(stranger, priv.spec.session_id), null);
  assert.ok(service.repositories.getSession(ownerEnvelope(priv, 'read'), priv.spec.session_id));
  service.close();
});

test('sessions: brief revisions are sequential and immutable', async () => {
  const service = openService(tempDir('briefs'));
  const session = sampleStored();
  await service.createSession(session);
  const envelope = ownerEnvelope(session);
  const revised = {
    ...session.brief,
    revision: session.brief.revision + 1,
    question: 'Revised question?',
  };
  service.repositories.saveBriefRevision(envelope, revised);
  const loaded = await service.getSession(session.spec.session_id);
  assert.equal(loaded?.brief.revision, revised.revision);
  assert.equal(loaded?.brief.question, 'Revised question?');
  // Replaying the same revision is a conflict, never an overwrite.
  assert.throws(
    () => service.repositories.saveBriefRevision(envelope, revised),
    isPersistence('PERSISTENCE_STATE_CONFLICT'),
  );
  service.close();
});

// ------------------------------------------- atomic commit and duplicates

test('commit: card, event, and outbox intent commit atomically; a duplicate commit duplicates nothing', async () => {
  const service = openService(tempDir('commit'));
  const session = sampleStored();
  await service.createSession(session);
  const envelope = ownerEnvelope(session);
  const card = advisorCard(session, 'op-card-1');
  const fence = { expected_state_version: 0, cancel_generation: 0, lease_epoch: 0 };
  const first = service.repositories.acceptCard(envelope, card, fence);
  assert.equal(first.outcome, 'committed');
  const eventsAfterFirst = service.repositories.journal.list(envelope, session.spec.session_id);
  const outboxAfterFirst = service.repositories.outbox.listForSession(envelope, session.spec.session_id);
  assert.equal(outboxAfterFirst.length, 1);
  assert.equal(outboxAfterFirst[0].topic, 'card.accepted');

  const duplicate = service.repositories.acceptCard(envelope, card, fence);
  assert.equal(duplicate.outcome, 'duplicate');
  assert.equal(service.repositories.listCards(envelope, session.spec.session_id).length, 1);
  assert.equal(
    service.repositories.journal.list(envelope, session.spec.session_id).length,
    eventsAfterFirst.length,
  );
  assert.equal(
    service.repositories.outbox.listForSession(envelope, session.spec.session_id).length,
    1,
  );

  // The same operation with different content is a conflict.
  const mutated = advisorCard(session, 'op-card-1');
  (mutated as { decisive_arguments: string[] }).decisive_arguments = ['Changed content.'];
  assert.throws(
    () => service.repositories.acceptCard(envelope, mutated, fence),
    isPersistence('PERSISTENCE_OPERATION_CONFLICT'),
  );
  service.close();
});

test('commit: a stale fence refuses the commit and stores nothing', async () => {
  const service = openService(tempDir('fence'));
  const session = sampleStored();
  await service.createSession(session);
  const envelope = ownerEnvelope(session);
  assert.throws(
    () =>
      service.repositories.acceptCard(envelope, advisorCard(session, 'op-stale'), {
        expected_state_version: 0,
        cancel_generation: 0,
        lease_epoch: 99,
      }),
    isPersistence('PERSISTENCE_STATE_CONFLICT'),
  );
  assert.equal(service.repositories.listCards(envelope, session.spec.session_id).length, 0);
  assert.equal(
    service.repositories.outbox.listForSession(envelope, session.spec.session_id).length,
    0,
  );
  service.close();
});

test('commit: a fault mid-commit rolls back state, card, event, and outbox together', () => {
  const dir = tempDir('rollback');
  // Rig the ID source so the journal append inside acceptCard collides
  // with an existing event ID after the card insert has run: the whole
  // transaction must roll back.
  let rigged = false;
  const riggedIds = {
    newId: () => {
      if (rigged) {
        rigged = false;
        return 'collision-event-id';
      }
      return ids.newId();
    },
  };
  const db = CouncilDatabase.open(join(dir, 'council.db'), {
    busyTimeoutMs: 500,
    busyMaxAttempts: 3,
    busyBaseDelayMs: 10,
  });
  db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const config = parsePersistenceConfig();
  const repositories = new CouncilRepositories(db, { clock, ids: riggedIds, config });
  const session = sampleStored();
  const envelope = ownerEnvelope(session);
  repositories.createSession(envelope, session);
  db.write((handle) =>
    repositories.journal.append(handle, envelope, session.spec.session_id, {
      event_id: 'collision-event-id',
      type: 'brief_revised',
      from_state: null,
      to_state: null,
      actor_subject: 'owner-1',
      payload: {},
      created_at: now,
    }),
  );
  const eventsBefore = repositories.journal.list(envelope, session.spec.session_id).length;
  rigged = true;
  assert.throws(() =>
    repositories.acceptCard(envelope, advisorCard(session, 'op-rollback'), {
      expected_state_version: 0,
      cancel_generation: 0,
      lease_epoch: 0,
    }),
  );
  assert.equal(repositories.listCards(envelope, session.spec.session_id).length, 0);
  assert.equal(repositories.journal.list(envelope, session.spec.session_id).length, eventsBefore);
  assert.equal(repositories.outbox.listForSession(envelope, session.spec.session_id).length, 0);
  const loaded = repositories.getSession(envelope, session.spec.session_id);
  assert.equal(loaded?.state.state_version, 0);
  db.close();
});

// ------------------------------------------------------------------ T056

test('T056: a locked database defers visibly within the bounded budget and commits nothing', () => {
  const dir = tempDir('t056');
  const dbPath = join(dir, 'council.db');
  const blocker = CouncilDatabase.open(dbPath, {
    busyTimeoutMs: 100,
    busyMaxAttempts: 1,
    busyBaseDelayMs: 1,
  });
  blocker.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  const session = sampleStored();
  const envelope = ownerEnvelope(session);
  // Compose the writer connection BEFORE the lock is taken, so its own
  // schema application is not part of the measured deferral.
  const { db, repositories } = composeDirect(dbPath, {
    busyTimeoutMs: 60,
    busyMaxAttempts: 2,
    busyBaseDelayMs: 10,
  });
  // Hold the write lock from the first connection.
  blocker.handle.exec('BEGIN IMMEDIATE');
  blocker.handle
    .prepare(
      `INSERT INTO council_request_keys (tenant_id, source, operation, request_key, payload_fingerprint, session_id, created_at)
       VALUES (?, 'lock-holder', 'hold', 'hold', 'fp', NULL, ?)`,
    )
    .run(session.scope.tenant_id, now);
  const started = Date.now();
  let caught: unknown;
  try {
    repositories.createSession(envelope, session);
  } catch (err) {
    caught = err;
  }
  const elapsed = Date.now() - started;
  assert.ok(caught instanceof PersistenceDeferredError, `expected deferred, got ${String(caught)}`);
  assert.equal((caught as PersistenceDeferredError).code, 'PERSISTENCE_STORE_DEFERRED');
  assert.equal((caught as PersistenceDeferredError).attempts, 2);
  assert.ok(elapsed < 10_000, `deferral took ${elapsed}ms, outside the bounded budget`);
  blocker.handle.exec('ROLLBACK');
  // Nothing from the deferred attempt was committed.
  assert.equal(repositories.getSession(envelope, session.spec.session_id), null);
  // And the same write succeeds once the lock clears.
  repositories.createSession(envelope, session);
  assert.ok(repositories.getSession(envelope, session.spec.session_id));
  db.close();
  blocker.close();
});

// ------------------------------------------------------- journal integrity

test('journal: the hash chain verifies, and tampering is detected at the exact sequence', () => {
  const dir = tempDir('journal');
  const { db, repositories } = composeDirect(join(dir, 'council.db'));
  const session = sampleStored();
  const envelope = ownerEnvelope(session);
  repositories.createSession(envelope, session);
  repositories.acceptCard(envelope, advisorCard(session, 'op-chain'), {
    expected_state_version: 0,
    cancel_generation: 0,
    lease_epoch: 0,
  });
  const ok = repositories.journal.verifyChain(envelope, session.spec.session_id);
  assert.equal(ok.ok, true);
  assert.equal(ok.checked, 2);
  db.handle
    .prepare(
      `UPDATE council_events SET payload_json = '{"tampered":true}'
        WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND sequence = 2`,
    )
    .run(session.scope.tenant_id, session.scope.company_id, session.spec.session_id);
  const bad = repositories.journal.verifyChain(envelope, session.spec.session_id);
  assert.equal(bad.ok, false);
  assert.equal(bad.first_bad_sequence, 2);
  db.close();
});

// ----------------------------------------------------------------- outbox

test('outbox: intents are claimed once, delivered, and dead-lettered at the attempt bound', async () => {
  const service = openService(tempDir('outbox'), { outbox_max_attempts: 2 });
  const session = sampleStored();
  await service.createSession(session);
  const envelope = ownerEnvelope(session);
  service.repositories.acceptCard(envelope, advisorCard(session, 'op-outbox'), {
    expected_state_version: 0,
    cancel_generation: 0,
    lease_epoch: 0,
  });
  const due = service.repositories.outbox.claimDue(envelope, now);
  assert.equal(due.length, 1);
  service.repositories.outbox.markDelivered(envelope, due[0].id, now);
  assert.equal(service.repositories.outbox.claimDue(envelope, now).length, 0);

  service.repositories.acceptCard(envelope, advisorCard(session, 'op-outbox-2'), {
    expected_state_version: 0,
    cancel_generation: 0,
    lease_epoch: 0,
  });
  const second = service.repositories.outbox.claimDue(envelope, now);
  assert.equal(second.length, 1);
  const once = service.repositories.outbox.markFailed(envelope, second[0].id, 'transport_down', now);
  assert.equal(once?.state, 'failed');
  const twice = service.repositories.outbox.markFailed(envelope, second[0].id, 'transport_down', now);
  assert.equal(twice?.state, 'dead_letter');
  assert.equal(service.repositories.outbox.claimDue(envelope, now).length, 0);
  service.close();
});

// --------------------------------------------------------------- verdicts

test('verdicts: save, duplicate save, conflicting revision, and consult round trip', async () => {
  const service = openService(tempDir('verdicts'));
  const session = sampleStored();
  await service.createSession(session);
  const envelope = ownerEnvelope(session);
  const verdict = scoredVerdict(session);
  const first = service.repositories.saveVerdict(envelope, verdict);
  assert.equal(first.outcome, 'committed');
  const dup = service.repositories.saveVerdict(envelope, verdict);
  assert.equal(dup.outcome, 'duplicate');
  const loaded = await service.getVerdict(session.spec.session_id);
  assert.equal(loaded?.result_kind, 'scored');
  const conflicting = scoredVerdict(session);
  (conflicting as { main_reasons: string[] }).main_reasons = ['Different reasons.'];
  conflicting.content_sha256 = canonicalHash(
    Object.fromEntries(Object.entries(conflicting).filter(([k]) => k !== 'content_sha256')),
  );
  assert.throws(
    () => service.repositories.saveVerdict(envelope, conflicting),
    isPersistence('PERSISTENCE_OPERATION_CONFLICT'),
  );
  service.close();
});

// ------------------------------------------------------- jobs, checkpoints

test('jobs: deterministic claim, lease fencing, checkpoints, and generation-fenced resume', async () => {
  const service = openService(tempDir('jobs'));
  const session = sampleStored();
  await service.createSession(session);
  const envelope = ownerEnvelope(session);
  const claim = {
    sessionId: session.spec.session_id,
    attempt: 1,
    briefRevision: 1,
    phaseJobKey: 'round-1:simon-sinek',
    inputSha256: canonicalHash({ input: 'jobs' }),
    cancelGeneration: 0,
    seatId: 'simon-sinek',
  };
  const first = service.jobs.claimJob(envelope, claim);
  const again = service.jobs.claimJob(envelope, claim);
  assert.equal(again.id, first.id);
  const leased = service.jobs.leaseJob(envelope, first.id, 'worker-1', 60, 0);
  assert.ok(leased);
  assert.equal(leased.lease_epoch, 1);
  // A second lease attempt finds nothing queued.
  assert.equal(service.jobs.leaseJob(envelope, first.id, 'worker-2', 60, 0), null);
  // A stale-epoch finish is rejected; the owner's finish succeeds.
  assert.equal(
    service.jobs.finishJob(envelope, first.id, 99, { status: 'succeeded', resultRef: 'card-1' }),
    false,
  );
  assert.equal(
    service.jobs.finishJob(envelope, first.id, 1, { status: 'succeeded', resultRef: 'card-1' }),
    true,
  );

  const checkpoint: JobCheckpoint = {
    schema_version: 'wise-elders.job-checkpoint/v1',
    installation_id: session.scope.installation_id,
    tenant_id: session.scope.tenant_id,
    session_id: session.spec.session_id,
    attempt: 1,
    brief_revision: 1,
    phase: 'round-1:simon-sinek',
    seat_id: 'simon-sinek',
    input_sha256: claim.inputSha256,
    pack_version: 'pack-fixture-1.0.0',
    model_policy_revision: 0,
    status: 'accepted',
    provider_request_id: null,
    usage: { input_tokens: null, output_tokens: null, provider_requests: 1 },
    committed_at: now,
  };
  await service.saveCheckpoint(checkpoint);
  const resumed = await service.getCheckpoint(
    session.spec.session_id,
    'round-1:simon-sinek',
    'simon-sinek',
    claim.inputSha256,
  );
  assert.equal(resumed?.phase, 'round-1:simon-sinek');
  // After a cancellation the generation moves and the checkpoint is refused.
  const ready = service.repositories.transitionState(envelope, session.spec.session_id, 'READY', 0);
  service.repositories.transitionState(
    envelope,
    session.spec.session_id,
    'CANCEL_REQUESTED',
    ready.state_version,
  );
  assert.equal(
    await service.getCheckpoint(
      session.spec.session_id,
      'round-1:simon-sinek',
      'simon-sinek',
      claim.inputSha256,
    ),
    null,
  );
  // An invalid checkpoint is never stored.
  await assert.rejects(
    () => service.saveCheckpoint({ ...checkpoint, status: 'bogus' } as JobCheckpoint),
    isPersistence('PERSISTENCE_VALIDATION_FAILED'),
  );
  service.close();
});

// ------------------------------------------------------------ request keys

test('request keys: first claim wins, replay matches, a changed payload conflicts', async () => {
  const service = openService(tempDir('reqkeys'));
  const session = sampleStored();
  await service.createSession(session);
  const base = {
    tenantId: session.scope.tenant_id,
    source: 'command-center',
    operation: 'create-session',
    requestKey: 'req-1',
    sessionId: session.spec.session_id,
  };
  assert.equal(
    service.repositories.claimRequestKey({ ...base, payloadFingerprint: 'fp-a' }).outcome,
    'claimed',
  );
  assert.equal(
    service.repositories.claimRequestKey({ ...base, payloadFingerprint: 'fp-a' }).outcome,
    'replay',
  );
  assert.equal(
    service.repositories.claimRequestKey({ ...base, payloadFingerprint: 'fp-b' }).outcome,
    'conflict',
  );
  service.close();
});

// ------------------------------------------------------------------ T133

test('T133: capture limits, byte counters, and expiry survive restart; expired content is inaccessible before cleanup', async () => {
  const dir = tempDir('t133');
  now = '2026-10-14T12:00:00.000Z';
  const service = openService(dir);
  const session = sampleStored();
  await service.createSession(session);
  const diagEnvelope = ownerEnvelope(session, 'diagnostic_capture');
  const policy = grantPolicy(session.spec.session_id, {
    payload_ttl_hours: 1,
    max_bytes_per_operation: 100,
    max_bytes_per_session: 150,
  });
  const grant = service.diagnostics.recordGrant(diagEnvelope, policy);
  const body = 'x'.repeat(80);
  const first = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-diag-1',
    dataClass: 'provider_response',
    body,
  });
  assert.equal(first.stored, 'payload');
  if (first.stored !== 'payload') return;
  assert.equal(first.byte_count, 80);
  const second = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-diag-2',
    dataClass: 'provider_response',
    body,
  });
  // Only 70 bytes of session budget remain: truncated, labeled.
  assert.equal(second.stored, 'payload');
  if (second.stored !== 'payload') return;
  assert.equal(second.byte_count, 70);
  assert.equal(second.truncated, true);
  const third = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-diag-3',
    dataClass: 'provider_response',
    body,
  });
  assert.equal(third.stored, 'metadata');
  if (third.stored === 'metadata') assert.equal(third.reason_code, 'session_byte_ceiling');
  const firstCaptureId = first.capture_id;
  const payloadFile = join(dir, 'diagnostics', session.spec.session_id, `${firstCaptureId}.bin`);
  assert.ok(existsSync(payloadFile));
  service.close();

  // Restart: counters come from stored rows, so the ceiling still holds.
  now = '2026-10-14T12:30:00.000Z';
  const reopened = openService(dir);
  const afterRestart = reopened.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-diag-4',
    dataClass: 'provider_response',
    body: 'y'.repeat(10),
  });
  assert.equal(afterRestart.stored, 'metadata');
  const readBack = reopened.diagnostics.readPayload(
    ownerEnvelope(session, 'diagnostic_read'),
    session.spec.session_id,
    firstCaptureId,
  );
  assert.equal(readBack.byte_count, 80);

  // Past the one-hour TTL the payload is inaccessible even though the
  // file has not been physically cleaned up yet.
  now = '2026-10-14T13:30:00.000Z';
  assert.throws(
    () =>
      reopened.diagnostics.readPayload(
        ownerEnvelope(session, 'diagnostic_read'),
        session.spec.session_id,
        firstCaptureId,
      ),
    isPersistence('PERSISTENCE_DIAGNOSTIC_DENIED'),
  );
  assert.ok(existsSync(payloadFile), 'expiry must precede physical cleanup in this test');
  const swept = reopened.diagnostics.sweepExpiredAndRevoked();
  assert.ok(swept.removed >= 1);
  assert.ok(!existsSync(payloadFile));
  assert.ok(grant.grant_id.length > 0);
  reopened.close();
});

// ------------------------------------------------------------------ T134

test('T134: revocation and deletion block late diagnostic writes and remove content access, with no backup-erasure claim', async () => {
  const dir = tempDir('t134');
  now = '2026-10-14T12:00:00.000Z';
  const service = openService(dir);
  const session = sampleStored();
  await service.createSession(session);
  const diagEnvelope = ownerEnvelope(session, 'diagnostic_capture');
  const grant = service.diagnostics.recordGrant(
    diagEnvelope,
    grantPolicy(session.spec.session_id),
  );
  const captured = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-diag-1',
    dataClass: 'provider_response',
    body: 'sensitive body',
  });
  assert.equal(captured.stored, 'payload');
  if (captured.stored !== 'payload') return;

  // Revocation: reads denied at once, late writes record no payload.
  service.diagnostics.revokeGrant(diagEnvelope, session.spec.session_id, grant.grant_id);
  assert.throws(
    () =>
      service.diagnostics.readPayload(
        ownerEnvelope(session, 'diagnostic_read'),
        session.spec.session_id,
        captured.capture_id,
      ),
    isPersistence('PERSISTENCE_DIAGNOSTIC_DENIED'),
  );
  const lateAfterRevoke = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-diag-2',
    dataClass: 'provider_response',
    body: 'late body',
  });
  assert.equal(lateAfterRevoke.stored, 'none');

  // A fresh grant, one capture, then explicit deletion.
  const grant2 = service.diagnostics.recordGrant(
    diagEnvelope,
    grantPolicy(session.spec.session_id),
  );
  const captured2 = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-diag-3',
    dataClass: 'provider_response',
    body: 'second body',
  });
  assert.equal(captured2.stored, 'payload');
  const deletion = service.repositories.deleteSession(
    ownerEnvelope(session, 'delete'),
    session.spec.session_id,
  );
  assert.equal(deletion.deleted, true);
  assert.deepEqual(Object.keys(deletion).sort(), ['deleted', 'diagnosticProtectedRefs']);
  assert.ok(deletion.diagnosticProtectedRefs.length >= 1);
  assert.ok(!/backup|erasure|erased/i.test(JSON.stringify(deletion)));
  service.diagnostics.purgePayloadFiles(deletion.diagnosticProtectedRefs);
  assert.equal(await service.getSession(session.spec.session_id), null);
  assert.equal(
    service.repositories.isDeleted(session.scope.tenant_id, session.spec.session_id),
    true,
  );
  // Late writes are blocked and never reconstitute the session.
  const lateCapture = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-diag-4',
    dataClass: 'provider_response',
    body: 'zombie body',
  });
  assert.equal(lateCapture.stored, 'none');
  assert.throws(
    () =>
      service.repositories.acceptCard(ownerEnvelope(session), advisorCard(session, 'op-zombie'), {
        expected_state_version: 0,
        cancel_generation: 0,
        lease_epoch: 0,
      }),
    isPersistence('PERSISTENCE_SESSION_DELETED'),
  );
  assert.throws(
    () => service.repositories.createSession(ownerEnvelope(session), session),
    isPersistence('PERSISTENCE_SESSION_DELETED'),
  );
  assert.ok(grant2.grant_id.length > 0);
  service.close();
});

// ------------------------------------------------------------- secret law

test('secrets: a planted secret never reaches a stored row, a payload file, or the database bytes', async () => {
  const dir = tempDir('secrets');
  now = '2026-10-14T12:00:00.000Z';
  const PLANTED = 'sk-PLANTEDSECRET1234567890abcdef';
  const service = openService(dir);
  const session = sampleStored();
  await service.createSession(session);
  const diagEnvelope = ownerEnvelope(session, 'diagnostic_capture');
  service.diagnostics.recordGrant(diagEnvelope, grantPolicy(session.spec.session_id));
  const outcome = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-secret-1',
    dataClass: 'provider_response',
    body: JSON.stringify({ api_key: PLANTED, note: 'ordinary diagnostic content' }),
  });
  assert.equal(outcome.stored, 'payload');
  service.repositories.acceptCard(ownerEnvelope(session), advisorCard(session, 'op-secret-card'), {
    expected_state_version: 0,
    cancel_generation: 0,
    lease_epoch: 0,
  });
  service.close();
  // Scan every artifact the store produced: the database, its WAL, the
  // profile, and every diagnostic payload file.
  const artifacts: string[] = [];
  const walk = (path: string) => {
    for (const entry of readdirSync(path, { withFileTypes: true })) {
      const full = join(path, entry.name);
      if (entry.isDirectory()) walk(full);
      else artifacts.push(full);
    }
  };
  walk(dir);
  assert.ok(artifacts.length >= 3);
  for (const artifact of artifacts) {
    const bytes = readFileSync(artifact);
    assert.ok(
      !bytes.includes(Buffer.from(PLANTED)),
      `planted secret found in ${artifact}`,
    );
    assert.ok(
      !bytes.includes(Buffer.from('PLANTEDSECRET')),
      `planted secret fragment found in ${artifact}`,
    );
  }
  // The redacted capture still reads back, with the secret replaced.
  const reopened = openService(dir);
  if (outcome.stored === 'payload') {
    const readBack = reopened.diagnostics.readPayload(
      ownerEnvelope(session, 'diagnostic_read'),
      session.spec.session_id,
      outcome.capture_id,
    );
    assert.ok(readBack.body.includes('[REDACTED]'));
    assert.ok(!readBack.body.includes('PLANTEDSECRET'));
  }
  reopened.close();
});

test('diagnostics: never-captured classes and disabled capture record metadata only', async () => {
  const dir = tempDir('diag-never');
  now = '2026-10-14T12:00:00.000Z';
  const service = openService(dir);
  const session = sampleStored();
  await service.createSession(session);
  const diagEnvelope = ownerEnvelope(session, 'diagnostic_capture');
  // No grant at all: nothing is stored, not even metadata.
  const noGrant = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-nogrant',
    dataClass: 'provider_response',
    body: 'body',
  });
  assert.deepEqual(noGrant, { stored: 'none', reason_code: 'no_active_grant' });
  service.diagnostics.recordGrant(diagEnvelope, grantPolicy(session.spec.session_id));
  const never = service.diagnostics.capture(diagEnvelope, {
    sessionId: session.spec.session_id,
    operationId: 'op-never',
    dataClass: 'access_token',
    body: 'should never persist',
  });
  assert.equal(never.stored, 'metadata');
  if (never.stored === 'metadata') assert.equal(never.reason_code, 'never_captured');
  const listed = service.diagnostics.listCaptures(diagEnvelope, session.spec.session_id);
  const metadataRows = listed.filter((r) => r.record_kind === 'metadata');
  assert.equal(metadataRows.length, 1);
  assert.ok(!JSON.stringify(listed).includes('should never persist'));
  service.close();
});

// ------------------------------------------------------------ restart load

test('restart: sessions, journal chain, and outbox intents survive close and reopen', async () => {
  const dir = tempDir('restart');
  const service = openService(dir);
  const session = sampleStored();
  await service.createSession(session);
  const envelope = ownerEnvelope(session);
  service.repositories.acceptCard(envelope, advisorCard(session, 'op-restart'), {
    expected_state_version: 0,
    cancel_generation: 0,
    lease_epoch: 0,
  });
  service.close();
  const reopened = openService(dir);
  const loaded = await reopened.getSession(session.spec.session_id);
  assert.ok(loaded);
  assert.equal(reopened.repositories.listCards(envelope, session.spec.session_id).length, 1);
  const chains = reopened.verifyAllChains();
  assert.equal(chains.length, 1);
  assert.equal(chains[0].ok, true);
  const due = reopened.repositories.outbox.claimDue(envelope, now);
  assert.equal(due.length, 1);
  assert.equal(due[0].topic, 'card.accepted');
  reopened.close();
});
