/**
 * W74-A session-close protocol check (assert-style, no framework).
 *
 * Proves the four timer cases of the contract:
 *   1. idle -> soft-close fires at 5m (one question per quiet spell),
 *   2. an explicit close phrase finalizes immediately,
 *   3. silence 10m after the soft-close auto-finalizes,
 *   4. restart-safe derivation: the close state survives a store
 *      restart (derived from the store, never from in-memory timers).
 *
 * Run standalone: node --import tsx --test tests/session-close.test.ts
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  type CouncilCard,
  type DecisionBrief,
  type ScopeFields,
  type SessionSpec,
  type SessionStateRecord,
  type Verdict,
} from '../src/contracts/index.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import { envelopeFromScope, type AuthorizationEnvelope } from '../src/persistence/envelope.js';
import { CouncilStoreService } from '../src/persistence/store.js';
import {
  AUTO_FINALIZE_SILENCE_MS,
  SOFT_CLOSE_IDLE_MS,
  SOFT_CLOSE_QUESTION,
  SessionCloseService,
  deriveCloseAction,
  isClosePhrase,
  storeSessionClosePort,
  type CloseReason,
  type SessionCloseMarker,
  type SessionClosePort,
} from '../src/protocol/session-close.js';

const T0 = Date.parse('2026-10-22T12:00:00.000Z');
function at(msOffset: number): string {
  return new Date(T0 + msOffset).toISOString();
}
const MINUTE = 60 * 1000;

// ------------------------------------------------------------- fake port

function fakePort(overrides: Partial<SessionClosePort> = {}): SessionClosePort & {
  softCloses: string[];
  interactions: string[];
  closes: Array<{ at: string; reason: CloseReason }>;
} {
  const state = {
    lastEventAt: at(0),
    marker: {
      soft_close_sent_at: null,
      closed_at: null,
      close_reason: null,
    } as SessionCloseMarker,
    softCloses: [] as string[],
    interactions: [] as string[],
    closes: [] as Array<{ at: string; reason: CloseReason }>,
  };
  return {
    softCloses: state.softCloses,
    interactions: state.interactions,
    closes: state.closes,
    lastEventAt: () => state.lastEventAt,
    readMarker: () => state.marker,
    recordSoftClose(_sessionId, sentAt) {
      // Idempotent per quiet spell, like the store outbox: a second
      // send inside the same spell records nothing new, while a new
      // spell (a client interaction since the last question) earns
      // its own question.
      const prev = state.marker.soft_close_sent_at;
      const superseded = prev !== null && Date.parse(state.lastEventAt) > Date.parse(prev);
      if (prev === null || superseded) {
        state.marker.soft_close_sent_at = sentAt;
        state.softCloses.push(sentAt);
      }
    },
    recordClientInteraction(_sessionId, interactionAt) {
      state.lastEventAt = interactionAt;
      state.interactions.push(interactionAt);
    },
    markClosed(_sessionId, closedAt, reason) {
      state.marker.closed_at = closedAt;
      state.marker.close_reason = reason;
      state.closes.push({ at: closedAt, reason });
    },
    sessionRecord: () => ({ spec: { session_id: 'session-1' } }) as StoredSession,
    ...overrides,
  };
}

const RENDERED = { path: '/council-data/artifacts/session-1/index.html', link: 'https://council.example/artifacts/session-1' };

// ------------------------------------------------------- 1. idle soft-close

test('idle -> soft-close fires at 5m, one question per quiet spell', async () => {
  const port = fakePort();
  const service = new SessionCloseService({
    port,
    renderArtifact: async () => RENDERED,
  });

  // 4:59 -> still quiet, the question is due in 1 second.
  let tick = await service.tick('session-1', at(4 * MINUTE + 59_000));
  assert.equal(tick.action, 'none');
  assert.equal(port.softCloses.length, 0);

  // 5:00 -> exactly one soft-close question.
  tick = await service.tick('session-1', at(SOFT_CLOSE_IDLE_MS));
  assert.equal(tick.action, 'send_soft_close');
  assert.equal(tick.question, SOFT_CLOSE_QUESTION);
  assert.equal(port.softCloses.length, 1);
  assert.equal(port.readMarker('session-1').soft_close_sent_at, at(SOFT_CLOSE_IDLE_MS));

  // A later tick in the same quiet spell never repeats the question.
  tick = await service.tick('session-1', at(7 * MINUTE));
  assert.equal(tick.action, 'none');
  assert.equal(port.softCloses.length, 1);
});

// ------------------------------------------- 2. explicit close finalizes now

test('explicit close phrase finalizes immediately', async () => {
  let renderedRecord: StoredSession | null = null;
  let renderCount = 0;
  const port = fakePort();
  const service = new SessionCloseService({
    port,
    renderArtifact: (sessionRecord) => {
      renderCount += 1;
      renderedRecord = sessionRecord;
      return RENDERED;
    },
  });

  // Before any soft-close question, a close phrase closes the sitting NOW.
  const { finalized } = await service.handleClientMessage(
    'session-1',
    "That's all.",
    at(2 * MINUTE),
  );
  assert.ok(finalized, 'an explicit close phrase must finalize');
  assert.equal(finalized.closed, true);
  assert.equal(finalized.close_reason, 'client_close_phrase');
  assert.deepEqual(finalized.artifact, RENDERED);
  assert.equal(finalized.render_error, null);
  assert.equal(port.closes.length, 1);
  assert.equal(port.closes[0].reason, 'client_close_phrase');
  assert.equal(renderCount, 1);
  assert.equal((renderedRecord as StoredSession | null)?.spec.session_id ?? null, 'session-1');

  // Finalize is idempotent: a second close phrase renders nothing more.
  const again = await service.handleClientMessage('session-1', 'finalize', at(3 * MINUTE));
  assert.ok(again.finalized);
  assert.equal(renderCount, 1);
  assert.equal(port.closes.length, 1);

  // A non-close answer is an interaction: no finalize, quiet clock restarts.
  const idle = fakePort();
  const idleService = new SessionCloseService({
    port: idle,
    renderArtifact: async () => RENDERED,
  });
  const stillWorking = await idleService.handleClientMessage(
    'session-1',
    'we are still working',
    at(MINUTE),
  );
  assert.equal(stillWorking.finalized, null);
  assert.equal(idle.interactions.length, 1);

  assert.equal(isClosePhrase("that's all"), true);
  assert.equal(isClosePhrase('finalize'), true);
  assert.equal(isClosePhrase('we are done'), true);
  assert.equal(isClosePhrase('we are still working'), false);
});

// --------------------------------- 3. 10m silence after soft-close auto-closes

test('silence 10m after the soft-close auto-finalizes', async () => {
  const port = fakePort();
  const service = new SessionCloseService({
    port,
    renderArtifact: async () => RENDERED,
  });

  await service.tick('session-1', at(SOFT_CLOSE_IDLE_MS));
  const softCloseAt = T0 + SOFT_CLOSE_IDLE_MS;

  // 9:59 after the question -> still open, one second to go.
  let tick = await service.tick('session-1', at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS - 1000));
  assert.equal(tick.action, 'none');

  // 10:00 after the question -> auto-finalize, never left hanging open.
  tick = await service.tick('session-1', at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS));
  assert.equal(tick.action, 'auto_finalize');
  assert.ok(tick.finalized);
  assert.equal(tick.finalized.close_reason, 'auto_finalize');
  assert.deepEqual(tick.finalized.artifact, RENDERED);
  assert.equal(port.closes.length, 1);

  // A client answer before the ten minutes supersede the question: the
  // sitting continues, the quiet clock restarts from the answer, and a
  // fresh quiet spell earns its own question — never an auto-finalize
  // over an answer (this tick is past the FIRST question's ten-minute
  // window: the answer is what defers it).
  const answered = fakePort();
  const answeredService = new SessionCloseService({
    port: answered,
    renderArtifact: async () => RENDERED,
  });
  await answeredService.tick('session-1', at(SOFT_CLOSE_IDLE_MS));
  await answeredService.handleClientMessage('session-1', 'one more thing', at(softCloseAt + 3 * MINUTE));
  tick = await answeredService.tick(
    'session-1',
    at(softCloseAt + 3 * MINUTE + SOFT_CLOSE_IDLE_MS - 1000),
  );
  assert.equal(tick.action, 'none');
  tick = await answeredService.tick(
    'session-1',
    at(softCloseAt + 3 * MINUTE + SOFT_CLOSE_IDLE_MS + 2 * MINUTE),
  );
  assert.equal(tick.action, 'send_soft_close');
  assert.equal(answered.closes.length, 0, 'an answer defers the auto-finalize');
  assert.equal(answered.softCloses.length, 2);
});

// ------------------------------------------ 4. restart-safe store derivation

const SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'install-a',
  owner_subject: null,
};

function storedSession(sessionId: string): StoredSession {
  const brief: DecisionBrief = {
    schema_version: 'wise-elders.brief/v1',
    brief_id: `brief-${sessionId}`,
    session_id: sessionId,
    revision: 1,
    question: 'Should the sitting close itself when the client walks away?',
    facts: [],
    assumptions: [],
    unknowns: [],
    constraints: [],
    options: [{ id: 'option-a', label: 'Close it', kind: 'change' }],
    relevance_weights: {},
    critical_domains: [],
    evidence_manifest: [],
    private_preference_ref: null,
    created_at: '2026-10-22T12:00:00.000Z',
    display_timezone: 'America/New_York',
  };
  const spec: SessionSpec = {
    schema_version: 'wise-elders.session/v1',
    session_id: sessionId,
    mode: 'consult',
    visibility: 'company',
    brief_revision: 1,
    brief_sha256: canonicalHash(brief),
    options: brief.options,
    seat_ids: ['simon-sinek'],
    model_policy: {
      selection: 'client_default',
      route_id: 'route-1',
      requested_model_id: null,
      reasoning_preference: null,
      fallback_policy: 'none',
    },
    source_pack_version: 'pack-v1',
    execution_policy: 'advisory_only',
    created_at: '2026-10-22T12:00:00.000Z',
    display_timezone: 'America/New_York',
  };
  const state: SessionStateRecord = {
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
    updated_at: '2026-10-22T12:00:00.000Z',
  };
  return { spec, brief, scope: SCOPE, state, sample: false };
}

/**
 * Seed the store's own card and verdict rows for a session — the rows
 * the default close path assembles the render record from (R1 contract).
 * Real writes through the repository layer; no stubbed seam.
 */
function seedStoreRows(
  store: CouncilStoreService,
  envelope: AuthorizationEnvelope,
  sessionId: string,
): void {
  const session = store.repositories.getSession(envelope, sessionId);
  if (session === null) throw new Error(`seedStoreRows: session ${sessionId} not found`);
  const brief = session.brief;
  const card: CouncilCard = {
    schema_version: 'wise-elders.card/v1',
    session_id: sessionId,
    brief_revision: brief.revision,
    seat_id: 'simon-sinek',
    input_manifest_sha256: canonicalHash({ manifest: 'seed' }),
    pack_version: 'pack-fixture-1.0.0',
    card_kind: 'advisor',
    round: 1,
    stance: 'conditional',
    preferred_option_id: brief.options[0]?.id ?? 'option-a',
    option_scores: brief.options.map((option) => ({
      option_id: option.id,
      score: 7,
      rationale: 'Fixture rationale.',
      evidence_ids: [],
    })),
    framework_applications: [],
    decisive_arguments: ['Seeded take.'],
    strongest_objection: 'Seeded objection.',
    conditions: [],
    critical_unknowns: [],
    change_my_mind: 'Seeded change-my-mind.',
    challenges_answered: [],
    quotes: [],
    evidence_strength: 'medium',
    minority_position: null,
    host: {
      scope: { ...session.scope },
      operation_id: 'op-seed-1',
      route_id: 'route-1',
      session_id: sessionId,
      stamped_at: at(0),
      source_status: 'unverified',
    },
  };
  store.repositories.acceptCard(
    envelope,
    card,
    { expected_state_version: session.state.state_version, cancel_generation: 0, lease_epoch: 0 },
  );
  const base = {
    schema_version: 'wise-elders.verdict/v1',
    result_kind: 'scored' as const,
    session_id: sessionId,
    verdict_revision: 1,
    recommended_option_id: brief.options[0]?.id ?? 'option-a',
    label: 'WAIT' as const,
    option_scores: [],
    active_weights: {},
    evidence_strength: 'medium' as const,
    hard_constraint_findings: [],
    main_reasons: ['Seeded verdict reason.'],
    strongest_dissent: null,
    accepted_amendments: [],
    rejected_amendments: [],
    critical_unknowns: [],
    prerequisites: ['Seeded prerequisite.'],
    action_proposals: [],
    cheapest_informative_test: null,
    stop_criteria: [],
    review_criteria: [],
    resolution_support: null,
    validation_status: 'valid' as const,
    ratification_status: 'ratified' as const,
    brief_sha256: session.spec.brief_sha256,
  };
  store.repositories.saveVerdict(envelope, {
    ...base,
    content_sha256: canonicalHash(base),
  } as Verdict);
}

test('restart-safe derivation: close state lives in the store, not in timers', async () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'cwe074-close-'));
  const clock = { nowUtc: () => at(0) };
  let idCounter = 0;
  const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };
  const envelope = envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write');
  const sessionId = 'session-close-1';

  // Process 1: a session, one soft-close at the 5m mark.
  const store1 = CouncilStoreService.open({ dataDir, clock, ids, envelope });
  await store1.createSession(storedSession(sessionId));
  // The store's own card and verdict rows: what the close port assembles
  // the render record from (R1 contract) at finalize time.
  seedStoreRows(store1, envelope, sessionId);
  const port1 = storeSessionClosePort(store1.repositories, envelope, ids);
  const service1 = new SessionCloseService({ port: port1 });
  const softCloseAt = at(SOFT_CLOSE_IDLE_MS);
  const tick1 = await service1.tick(sessionId, softCloseAt);
  assert.equal(tick1.action, 'send_soft_close');
  assert.equal(tick1.question, SOFT_CLOSE_QUESTION);
  store1.close();

  // Process 2 (restart): the same quiet spell is derived from the store.
  // No in-memory timer survived; nothing is lost and nothing repeats.
  const store2 = CouncilStoreService.open({ dataDir, clock, ids, envelope });
  const port2 = storeSessionClosePort(store2.repositories, envelope, ids);
  const service2 = new SessionCloseService({ port: port2 });

  const marker = port2.readMarker(sessionId);
  assert.equal(marker.soft_close_sent_at, softCloseAt, 'soft-close marker survives the restart');
  assert.equal(marker.closed_at, null);

  // 9:59 after the question -> still open, no second question.
  const near = await service2.tick(sessionId, at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS - 1000));
  assert.equal(near.action, 'none');
  assert.equal(port2.readMarker(sessionId).soft_close_sent_at, softCloseAt, 'the question is sent ONCE');

  // 10:00 after the question -> auto-finalize from store-derived state.
  // The close port assembles the render record from the store's own rows
  // (R1 contract): this session carries one card and one verdict, so the
  // port hands the renderer an ASSEMBLED RenderSessionRecord, never a
  // bare StoredSession.
  const rendererCalls: StoredSession[] = [];
  const service2b = new SessionCloseService({
    port: port2,
    renderArtifact: (record) => {
      rendererCalls.push(record);
      return RENDERED;
    },
  });
  const done = await service2b.tick(
    sessionId,
    at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS),
  );
  assert.equal(done.action, 'auto_finalize');
  assert.ok(done.finalized);
  assert.equal(done.finalized.close_reason, 'auto_finalize');
  assert.deepEqual(done.finalized.artifact, RENDERED);
  assert.equal(rendererCalls.length, 1);
  assert.equal(
    (rendererCalls[0] as { session_id?: string }).session_id ?? null,
    sessionId,
    'the default close path hands the renderer the assembled render record',
  );
  assert.equal(port2.readMarker(sessionId).closed_at, at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS));
  store2.close();

  // Process 3 (second restart): the close itself also survives.
  const store3 = CouncilStoreService.open({ dataDir, clock, ids, envelope });
  const port3 = storeSessionClosePort(store3.repositories, envelope, ids);
  const marker3 = port3.readMarker(sessionId);
  assert.equal(marker3.closed_at, at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS));
  assert.equal(marker3.close_reason, 'auto_finalize');
  const after = await new SessionCloseService({ port: port3 }).tick(
    sessionId,
    at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS + 60 * MINUTE),
  );
  assert.equal(after.action, 'none', 'a closed session never soft-closes again');
  store3.close();
});

// ------------------------------------------------- derivation sanity (pure)

test('deriveCloseAction is pure over store timestamps', () => {
  const open = { soft_close_sent_at: null, closed_at: null, close_reason: null };
  assert.equal(
    deriveCloseAction({ last_event_at: at(0), marker: open }, at(SOFT_CLOSE_IDLE_MS)).action,
    'send_soft_close',
  );
  assert.equal(
    deriveCloseAction({ last_event_at: at(0), marker: open }, at(SOFT_CLOSE_IDLE_MS - 1)).action,
    'none',
  );
  assert.equal(
    deriveCloseAction(
      {
        last_event_at: at(0),
        marker: { soft_close_sent_at: at(SOFT_CLOSE_IDLE_MS), closed_at: null, close_reason: null },
      },
      at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS),
    ).action,
    'auto_finalize',
  );
  assert.equal(
    deriveCloseAction(
      {
        last_event_at: at(0),
        marker: { soft_close_sent_at: at(SOFT_CLOSE_IDLE_MS), closed_at: at(1), close_reason: 'auto_finalize' },
      },
      at(2 * 60 * MINUTE),
    ).action,
    'none',
  );
});
