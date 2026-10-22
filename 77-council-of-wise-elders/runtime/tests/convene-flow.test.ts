/**
 * W74-D runnable check: the wired convene flow (assert-style, no framework).
 *
 * Proves the exact order the unit wires, on BOTH doors (the OpenClaw
 * door and the 999 / claude-nine door):
 *   1. brief-builder FIRST (permitted context through the door's own
 *      adapter) — the deliberation leg sees the assembled brief,
 *   2-3. deliberation, then verdict,
 *   4. session-close manages the sitting (the soft-close question,
 *      close phrase finalizes),
 *   5. finalize calls renderArtifact(sessionRecord) — the REAL W74-B
 *      renderer, reached through the W74-D entry point — and the
 *      delivery carries the artifact reply link beside the chamber.
 *
 * The artifact is written for real under a temp data dir and read back.
 *
 * Run standalone: node --import tsx --test tests/convene-flow.test.ts
 */
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  canonicalHash,
  type DecisionBrief,
  type ScopeFields,
  type SessionSpec,
  type SessionStateRecord,
} from '../src/contracts/index.js';
import type { StoredSession } from '../src/cli/host-ports.js';
import {
  conveneFlow,
  doorAdapterFor,
  doorForEnv,
  SOFT_CLOSE_QUESTION,
  type DeliberationResult,
} from '../src/flow/convene-flow.js';
import { envelopeFromScope } from '../src/persistence/envelope.js';
import { CouncilStoreService } from '../src/persistence/store.js';
import {
  AUTO_FINALIZE_SILENCE_MS,
  SOFT_CLOSE_IDLE_MS,
  resolveRenderArtifact,
  storeSessionClosePort,
} from '../src/protocol/session-close.js';
import type { DoorKind } from '../src/brief/permitted-brief.js';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'brief-builder');
const DOOR_DIRS: Record<DoorKind, string> = {
  openclaw: 'openclaw-door',
  'claude-nine': 'claude-nine-door',
};
const DOORS: readonly DoorKind[] = ['openclaw', 'claude-nine'];
const DECISION = 'Should the company open a second office in Austin this year?';
const OPTIONS = ['open the Austin office in Q3', 'wait until next year'];

const T0 = Date.parse('2026-10-22T12:00:00.000Z');
function at(msOffset: number): string {
  return new Date(T0 + msOffset).toISOString();
}
const MINUTE = 60 * 1000;

const SCOPE: ScopeFields = {
  tenant_id: 'tenant-a',
  company_id: 'company-a',
  installation_id: 'install-a',
  owner_subject: null,
};

// A real 1x1 PNG as a synthetic stand-in for the seat art, so this check
// runs anywhere and never depends on generated art.
const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

function makeSyntheticAssets(): string {
  const dir = mkdtempSync(join(tmpdir(), 'w74d-assets-'));
  writeFileSync(join(dir, 'cover.png'), PNG_1X1);
  for (const seat of SEATS) {
    writeFileSync(join(dir, `seat-${seat}.png`), PNG_1X1);
  }
  return dir;
}

const SEATS = [
  'simon-sinek', 'td-jakes', 'oprah-winfrey', 'tiffany-aliche', 'russell-brunson',
  'michelle-obama', 'brene-brown', 'dennis-kimbro', 'les-brown',
];

function storedSession(sessionId: string): StoredSession {
  const brief: DecisionBrief = {
    schema_version: 'wise-elders.brief/v1',
    brief_id: `brief-${sessionId}`,
    session_id: sessionId,
    revision: 1,
    question: DECISION,
    facts: [],
    assumptions: [],
    unknowns: [],
    constraints: [],
    options: [{ id: 'option-a', label: OPTIONS[0], kind: 'change' }],
    relevance_weights: {},
    critical_domains: [],
    evidence_manifest: [],
    private_preference_ref: null,
    created_at: at(0),
    display_timezone: 'America/New_York',
  };
  const spec: SessionSpec = {
    schema_version: 'wise-elders.session/v1',
    session_id: sessionId,
    mode: 'full',
    visibility: 'company',
    brief_revision: 1,
    brief_sha256: canonicalHash(brief),
    options: brief.options,
    seat_ids: [...SEATS],
    model_policy: {
      selection: 'client_default',
      route_id: 'route-1',
      requested_model_id: null,
      reasoning_preference: null,
      fallback_policy: 'none',
    },
    source_pack_version: 'pack-v1',
    execution_policy: 'advisory_only',
    created_at: at(0),
    display_timezone: 'America/New_York',
  };
  const state: SessionStateRecord = {
    schema_version: 'wise-elders.session-state/v1',
    session_id: sessionId,
    mode: 'full',
    state: 'COMPLETED',
    state_version: 0,
    brief_revision: 1,
    resume_phase: null,
    cancel_generation: 0,
    revocation_generation: 0,
    attempt: 1,
    lease_epoch: 0,
    archived: false,
    updated_at: at(0),
  };
  return { spec, brief, scope: SCOPE, state, sample: true };
}

function deliberationResult(sessionId: string): DeliberationResult {
  return {
    sessionId,
    session: storedSession(sessionId),
    clientName: 'Example Client Co. (synthetic fixture)',
    modelUsed: 'fixture-model (synthetic fixture)',
    questionCount: 27,
    cards: SEATS.map((seat_id) => ({ seat_id, take: `Synthetic take for ${seat_id}.` })),
    verdict: {
      consensus: 'Synthetic consensus: Option B, with conditions.',
      action_steps: ['Confirm the missing cash figures.', 'Run the four-week test.'],
    },
    chamberUrl: 'https://council.example/chamber',
  };
}

interface Harness {
  order: string[];
  dataDir: string;
  result: Awaited<ReturnType<typeof conveneFlow>>;
  store: CouncilStoreService;
}

async function runFlow(door: DoorKind, opts: { now?: string } = {}): Promise<Harness> {
  const order: string[] = [];
  const dataDir = mkdtempSync(join(tmpdir(), 'cwe074d-flow-'));
  const clock = { nowUtc: () => at(0) };
  let idCounter = 0;
  const ids = { newId: () => `id-${(idCounter += 1).toString().padStart(4, '0')}` };
  const envelope = envelopeFromScope(SCOPE, 'owner-1', 'owner', 'write');
  const store = CouncilStoreService.open({ dataDir, clock, ids, envelope });

  const result = await conveneFlow(
    {
      door,
      contextRoot: join(FIXTURES, DOOR_DIRS[door]),
      decision: DECISION,
      options: OPTIONS,
    },
    {
      deliberate: async ({ permittedBrief }) => {
        order.push('deliberation');
        // The brief-builder ran FIRST: the deliberation leg receives the
        // assembled permitted-context brief, with the door's facts.
        assert.ok(
          JSON.stringify(permittedBrief).includes('Austin lease offer is $8,200 per month'),
          `${door}: deliberation did not receive the assembled brief`,
        );
        assert.ok(permittedBrief.unknowns.length > 0, `${door}: unknowns not marked`);
        const sessionId = `sess-${door}-1`;
        await store.createSession(storedSession(sessionId));
        return deliberationResult(sessionId);
      },
      closePort: storeSessionClosePort(store.repositories, envelope, ids),
      renderOptions: {
        dataDir: join(dataDir, 'council-data'),
        assetsDir: makeSyntheticAssets(),
        linkBase: 'https://council.example',
        pdf: false,
      },
    },
  );
  order.push('settled');
  return { order, dataDir, result, store };
}

// ------------------------------------------------- 1-3, 5: both doors

for (const door of DOORS) {
  test(`${door} door: brief-builder first, deliberation, verdict, finalize renders the artifact`, async () => {
    const h = await runFlow(door);
    try {
      // Step 1 ran before deliberation (the deliberate leg asserted it
      // received the assembled brief) and the brief is in the result.
      assert.ok(
        JSON.stringify(h.result.permittedBrief).includes('Austin lease offer is $8,200 per month'),
        `${door}: brief-builder output missing`,
      );
      assert.equal(h.result.permittedBrief.door, door);

      // Steps 4-5: finalize -> renderArtifact(sessionRecord) -> delivery.
      const done = await h.result.finalize('client_close_phrase', at(30 * MINUTE));
      assert.equal(done.closed, true);
      assert.equal(done.close_reason, 'client_close_phrase');
      assert.equal(done.render_error, null, `${door}: render failed: ${done.render_error}`);
      assert.ok(done.artifact, `${door}: no artifact`);
      assert.ok(done.artifact.path.endsWith(`/artifacts/${h.result.sessionId}/index.html`));

      // The artifact really exists and is the fixed five-section page.
      const html = readFileSync(done.artifact.path, 'utf8');
      assert.ok(html.includes(DECISION), `${door}: decision missing from artifact`);
      assert.ok(html.includes('Example Client Co. (synthetic fixture)'), `${door}: client name missing`);
      assert.ok(html.includes('Synthetic consensus: Option B, with conditions.'), `${door}: consensus missing`);
      for (const seat of SEATS) assert.ok(html.includes(seat), `${door}: seat card missing: ${seat}`);
      assert.ok(html.includes('Confirm the missing cash figures.'), `${door}: action step missing`);
      assert.ok(html.includes('SYNTHETIC FIXTURE'), `${door}: synthetic label missing`);
      // Assets copied beside it, relative paths only.
      assert.ok(existsSync(join(dirname(done.artifact.path), 'assets', 'cover.png')));

      // Delivery: the reply link beside the chamber link.
      assert.ok(done.delivery, `${door}: no delivery`);
      assert.equal(done.delivery.reply_link, done.artifact.link);
      assert.equal(done.delivery.chamber_url, 'https://council.example/chamber');
    } finally {
      h.store.close();
    }
  });
}

// ---------------------------------------------- 4: the close protocol

test('sitting: soft-close question at 5m, explicit close finalizes now', async () => {
  const h = await runFlow('openclaw');
  try {
    // 4:59 quiet: nothing yet. 5:00: exactly one soft-close question.
    assert.equal((await h.result.sitting.tick(at(4 * MINUTE + 59_000))).action, 'none');
    const soft = await h.result.sitting.tick(at(SOFT_CLOSE_IDLE_MS));
    assert.equal(soft.action, 'send_soft_close');
    assert.equal(soft.question, SOFT_CLOSE_QUESTION);

    // The client answers something else: the sitting continues.
    const answered = await h.result.sitting.handleClientMessage('one more thing', at(SOFT_CLOSE_IDLE_MS + MINUTE));
    assert.equal(answered.finalized, null);

    // An explicit close phrase finalizes immediately, question or not.
    const closed = await h.result.sitting.handleClientMessage("that's all", at(SOFT_CLOSE_IDLE_MS + 2 * MINUTE));
    assert.ok(closed.finalized, 'close phrase did not finalize');
    assert.equal(closed.finalized.close_reason, 'client_close_phrase');
    assert.ok(closed.finalized.artifact, 'finalize did not render');
    assert.equal(
      closed.finalized.artifact.link,
      'https://council.example/artifacts/sess-openclaw-1/index.html',
    );
  } finally {
    h.store.close();
  }
});

test('sitting: ten minutes of silence after the question auto-finalizes', async () => {
  const h = await runFlow('claude-nine');
  try {
    await h.result.sitting.tick(at(SOFT_CLOSE_IDLE_MS));
    const done = await h.result.sitting.tick(at(SOFT_CLOSE_IDLE_MS + AUTO_FINALIZE_SILENCE_MS));
    assert.equal(done.action, 'auto_finalize');
    assert.ok(done.finalized);
    assert.equal(done.finalized.close_reason, 'auto_finalize');
    assert.ok(done.finalized.artifact, 'auto-finalize did not render');
  } finally {
    h.store.close();
  }
});

// ------------------------------------------------------ the two doors

test('door adapters: harness markers select the door, adapters stay distinct', () => {
  assert.equal(doorForEnv({ CLAUDE_CONFIG_DIR: '/home/x/.claude-nine' }), 'claude-nine');
  assert.equal(doorForEnv({ CLAUDECODE: '1' }), 'claude-nine');
  assert.equal(doorForEnv({}), 'openclaw');
  // Each door selects its own adapter; the assembler behind them is shared.
  assert.equal(doorAdapterFor('openclaw'), 'openclaw');
  assert.equal(doorAdapterFor('claude-nine'), 'claude-nine');
});

test('the by-name render seam resolves the W74-B entry point', async () => {
  const render = await resolveRenderArtifact();
  assert.ok(render, 'resolveRenderArtifact found no renderArtifact export');
  assert.equal(typeof render, 'function');
});
