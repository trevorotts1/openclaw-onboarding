/**
 * W80 R1 regression: the DEFAULT store-backed session-close path must
 * deliver a renderable record to the ACTUAL W74-B renderer and write
 * the counsel artifact on disk.
 *
 * The R1 defect: `storeSessionClosePort.sessionRecord()` handed finalize
 * a bare `StoredSession`, and `renderArtifact` cast absent
 * `options.extras` through — `assembleRenderRecord` then dereferenced
 * undefined (`extras.client_name`) and finalize reported a render error
 * with NO artifact. The explicit conveneFlow path supplies extras, so
 * only the default path was broken.
 *
 * This check drives the REAL path end to end with zero stubs:
 *   REAL STORE (SQLite council.db with session + nine cards + verdict)
 *   -> DEFAULT CLOSE (storeSessionClosePort + SessionCloseService,
 *      NO injected renderer, NO conveneFlow extras)
 *   -> ACTUAL RENDERER (resolved BY EXPORT NAME, the fixed W74-B
 *      template writing index.html plus copied assets)
 *   -> index.html on disk with the five sections in order, and the
 *      honest PDF verdict (rendered by a real headless renderer, or
 *      the documented print-from-browser degrade when none exists).
 *
 * Run standalone: node --import tsx --test tests/session-close-render.test.ts
 */
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
  canonicalHash,
  SCHEMA_VERSIONS,
  SEAT_IDS,
  type CouncilCard,
  type DecisionBrief,
  type SessionSpec,
  type SessionStateRecord,
  type Verdict,
} from '../src/contracts/index.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { CouncilStoreService } from '../src/persistence/store.js';
import {
  CLIENT_NAME_UNRECORDED,
  SessionCloseService,
  storeSessionClosePort,
} from '../src/protocol/session-close.js';
import {
  RenderInputError,
  renderArtifact,
} from '../src/reports/artifact-renderer.js';
import { probePdfRenderer } from '../../scripts/render-counsel-artifact.mjs';

const T0 = Date.parse('2026-10-22T12:00:00.000Z');
function at(msOffset: number): string {
  return new Date(T0 + msOffset).toISOString();
}

const SESSION_ID = 'session-close-render-1';

/** The store's own session row (sample fixture, labeled sample). */
function storedSession(): StoredSession {
  const sample = buildSampleSession();
  const spec = { ...sample.spec, session_id: SESSION_ID } as SessionSpec;
  const brief = { ...sample.brief, session_id: SESSION_ID, brief_id: `brief-${SESSION_ID}` } as DecisionBrief;
  spec.brief_sha256 = canonicalHash(brief);
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: SESSION_ID,
    mode: 'full',
    state: 'COMPLETED',
    state_version: 0,
    brief_revision: brief.revision,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: at(0),
  };
  return {
    spec,
    brief,
    scope: sample.scope,
    state,
    sample: true,
  };
}

/** One committed advisor card per seat — the store's own card rows. */
function advisorCard(session: StoredSession, seatId: string, operationId: string): CouncilCard {
  const brief = session.brief;
  return {
    schema_version: 'wise-elders.card/v1',
    session_id: SESSION_ID,
    brief_revision: brief.revision,
    seat_id: seatId as CouncilCard['seat_id'],
    input_manifest_sha256: canonicalHash({ manifest: operationId }),
    pack_version: 'pack-fixture-1.0.0',
    card_kind: 'advisor',
    round: 1,
    stance: 'conditional',
    preferred_option_id: brief.options[0]!.id,
    option_scores: brief.options.map((option) => ({
      option_id: option.id,
      score: 7,
      rationale: 'Fixture rationale from the stored card row.',
      evidence_ids: [],
    })),
    framework_applications: [],
    decisive_arguments: [`The stored take for ${seatId}.`],
    strongest_objection: 'Fixture objection.',
    conditions: [],
    critical_unknowns: [],
    change_my_mind: `Stored change-my-mind for ${seatId}.`,
    challenges_answered: [],
    quotes: [],
    evidence_strength: 'medium',
    minority_position: null,
    host: {
      scope: { ...session.scope },
      operation_id: operationId,
      route_id: 'route-fixture-1',
      session_id: SESSION_ID,
      stamped_at: at(0),
      source_status: 'unverified',
    },
  } as CouncilCard;
}

/** The store's own committed scored verdict. */
function scoredVerdict(session: StoredSession): Verdict {
  const base = {
    schema_version: SCHEMA_VERSIONS.verdict,
    result_kind: 'scored' as const,
    session_id: SESSION_ID,
    verdict_revision: 1,
    recommended_option_id: session.brief.options[0]!.id,
    label: 'WAIT' as const,
    option_scores: [],
    active_weights: {},
    evidence_strength: 'medium' as const,
    hard_constraint_findings: [],
    main_reasons: ['The stored verdict reason.'],
    strongest_dissent: null,
    accepted_amendments: [],
    rejected_amendments: [],
    critical_unknowns: [],
    prerequisites: ['Stored prerequisite one.'],
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

/**
 * Build the REAL store in a temp data dir: one full session, nine
 * committed advisor cards (one per seat), one committed verdict. This is
 * the session's own durable record — the assembled render record is
 * derived from exactly these rows.
 */
function openRealStore(dataDir: string): {
  store: CouncilStoreService;
  session: StoredSession;
} {
  const session = storedSession();
  const clock = { nowUtc: () => at(0) };
  let idCounter = 0;
  const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };
  const envelope = envelopeFromScope(session.scope, 'owner-1', 'owner', 'write');
  const store = CouncilStoreService.open({ dataDir, clock, ids, envelope });
  return { store, session };
}

test('R1: real store -> default close -> actual renderer writes index.html with five sections', async () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w80-r1-reg-'));
  // The renderer writes <dataDir>/artifacts/...; keep the run inside the
  // test's temp data dir, never the operator's live council data.
  const priorDataDir = process.env.BLACKCEO_COUNCIL_DATA_DIR;
  process.env.BLACKCEO_COUNCIL_DATA_DIR = dataDir;
  try {
  const { store, session } = openRealStore(dataDir);
  await store.createSession(session);

  // The store's own rows: nine cards, one verdict.
  const fence = { expected_state_version: 0, cancel_generation: 0, lease_epoch: 0 };
  for (const [index, seatId] of SEAT_IDS.entries()) {
    store.repositories.acceptCard(
      envelopeFromScope(session.scope, 'owner-1', 'owner', 'write'),
      advisorCard(session, seatId, `op-card-${index}`),
      fence,
    );
  }
  store.repositories.saveVerdict(
    envelopeFromScope(session.scope, 'owner-1', 'owner', 'write'),
    scoredVerdict(session),
  );

  // DEFAULT CLOSE: the store-backed port, NO injected renderer, NO
  // conveneFlow extras. finalize resolves renderArtifact BY EXPORT NAME
  // (the path the repro proved broken).
  const port = storeSessionClosePort(
    store.repositories,
    envelopeFromScope(session.scope, 'owner-1', 'owner', 'write'),
    { newId: () => `close-${Math.random().toString(36).slice(2, 10)}` },
  );
  const close = new SessionCloseService({ port });
  const finalized = await close.finalize(SESSION_ID, 'client_close_phrase', at(30 * 60 * 1000));

  assert.equal(finalized.closed, true, 'the sitting must close');
  assert.equal(finalized.render_error, null, `finalize must render without error, got: ${finalized.render_error}`);
  assert.ok(finalized.artifact, 'finalize must return the artifact');
  assert.ok(existsSync(finalized.artifact!.path), `the artifact file must exist at ${finalized.artifact!.path}`);

  // The artifact is readable HTML carrying the five sections in order,
  // the honest unrecorded-client header, the store's own card takes and
  // verdict rows.
  const html = readFileSync(finalized.artifact!.path, 'utf8');
  const sections = ['header', 'consensus', 'elders', 'actions', 'footer'];
  let cursor = -1;
  for (const section of sections) {
    const found = html.indexOf(`data-section="${section}"`);
    assert.ok(found !== -1, `the artifact must carry section ${section}`);
    assert.ok(found > cursor, `section ${section} must appear in order`);
    cursor = found;
  }
  assert.ok(html.includes(CLIENT_NAME_UNRECORDED), 'the header must carry the honest unrecorded-client state, never a fabricated name');
  assert.ok(html.includes('Stored change-my-mind for simon-sinek.'), 'the elders section must carry the store card take');
  assert.ok(html.includes('The stored verdict reason.'), 'the consensus section must carry the store verdict reason');
  assert.ok(html.includes('Stored prerequisite one.'), 'the actions section must carry the store verdict prerequisite');

  // PDF verdict, named for this box: rendered by the real headless
  // renderer when one exists, or the documented print-from-browser
  // degrade — never faked, never a blocker.
  const probe = probePdfRenderer();
  const pdf = finalized.artifact as { pdf?: { status: string; method: string | null; pdfPath: string | null } };
  if (probe.method !== null) {
    assert.equal(pdf?.pdf?.status, 'rendered', `a real ${probe.method} renderer exists, so the PDF must be rendered`);
    assert.ok(pdf!.pdf!.pdfPath && existsSync(pdf!.pdf!.pdfPath), 'the rendered PDF file must exist');
  } else {
    assert.equal(pdf?.pdf?.status, 'print-from-browser', 'no headless renderer on this box: the documented honest degrade');
  }

  // Idempotence unchanged: a second finalize renders nothing more.
  const again = await close.finalize(SESSION_ID, 'client_close_phrase', at(31 * 60 * 1000));
  assert.equal(again.artifact, null, 'an already-closed session is not re-rendered');

  store.close();
  } finally {
    if (priorDataDir === undefined) delete process.env.BLACKCEO_COUNCIL_DATA_DIR;
    else process.env.BLACKCEO_COUNCIL_DATA_DIR = priorDataDir;
  }
});

test('R1 seam: a bare StoredSession without extras is a typed contract violation, never a silent undefined dereference', async () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w80-r1-seam-'));
  const { store, session } = openRealStore(dataDir);
  await store.createSession(session);
  store.close();

  // The old defect threw `Cannot read properties of undefined (reading
  // 'client_name')`. The fixed seam throws the typed RenderInputError.
  await assert.rejects(
    renderArtifact(session),
    (err: unknown) => {
      assert.ok(err instanceof RenderInputError, `must be a RenderInputError, got: ${String(err)}`);
      assert.equal(err.code, 'RENDER_INPUT_INCOMPLETE');
      assert.ok(err.message.includes('extras'), 'the error must name the missing extras');
      return true;
    },
  );
});

test('R1 honesty: a store session with no committed cards/verdict surfaces the typed state, never an invented record', async () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'w80-r1-empty-'));
  const { store, session } = openRealStore(dataDir);
  await store.createSession(session);

  // No cards, no verdict: the default close path must report the typed
  // incompleteness through render_error — NOT fabricate takes or a
  // verdict to force an artifact.
  const port = storeSessionClosePort(
    store.repositories,
    envelopeFromScope(session.scope, 'owner-1', 'owner', 'write'),
    { newId: () => `close-${Math.random().toString(36).slice(2, 10)}` },
  );
  const close = new SessionCloseService({ port });
  const finalized = await close.finalize(SESSION_ID, 'client_close_phrase', at(30 * 60 * 1000));
  assert.equal(finalized.closed, true, 'the sitting still closes');
  assert.equal(finalized.artifact, null, 'no artifact may be invented');
  assert.ok(
    finalized.render_error !== null && finalized.render_error.includes('RENDER_INPUT_INCOMPLETE'),
    `render_error must carry the typed state, got: ${finalized.render_error}`,
  );

  store.close();
});