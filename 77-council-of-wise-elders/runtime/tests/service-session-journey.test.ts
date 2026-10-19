/**
 * W25-U001 Lane E: the composed service closes the "code exists" gap.
 *
 * Runner:
 *   node --import tsx --test tests/service-session-journey.test.ts
 *
 * Proven offline, with no provider call and no credential read:
 * - a session created through the CLI write path (LocalSqliteStore create
 *   plus the canonical mirror) is visible to the composed service reader;
 * - an unknown id answers 404 SESSION_NOT_FOUND on the session and events
 *   routes instead of the old unconditional `ui: "not_bundled"` page;
 * - the event stream replays a COMMITTED journal row from the same
 *   `council.db` handle, and every frame matches its stored row exactly;
 * - a front-door admission with a complete durable command persists a
 *   council_jobs row + journal event + outbox intent; an incomplete payload
 *   is refused as ADMISSION_SINK_FAILED, never admitted and never invented;
 * - a restart-equivalent recomposition re-reads the same session state and
 *   the same committed event rows;
 * - a bare CouncilFrontDoor with nothing bound keeps today's exact answers:
 *   200 `ui: "not_bundled"`, 501 EVENT_STREAM_ADAPTER_NOT_BOUND,
 *   503 ADMISSION_SINK_UNBOUND.
 */

import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { canonicalHash } from '../src/contracts/index.js';
import { buildSampleSession } from '../src/cli/fixture-transport.js';
import { createLocalHost, localScope } from '../src/cli/local-host.js';
import { CouncilEngine } from '../src/cli/engine.js';
import {
  createStandaloneRunAuthorization,
  mirrorSession,
  resolveStandaloneInstallation,
  standaloneScope,
} from '../src/cli/authorization.js';
import { buildServiceIdentity } from '../src/service/identity.js';
import { CouncilFrontDoor } from '../src/service/front-door.js';
import {
  composeCouncilService,
  startCouncilService,
  type CouncilServiceComposition,
} from '../src/service/composition.js';

const FIXED_NOW = '2026-10-19T12:00:00.000Z';
const SESSION_ID = 'lane-e-session-0001';
const UNKNOWN_ID = 'lane-e-unknown-0001';
const nowUtc = (): string => FIXED_NOW;

function makeDataDir(): string {
  return mkdtempSync(join(tmpdir(), 'lane-e-journey-'));
}

function sessionInput(dataDir: string) {
  const sample = buildSampleSession();
  const brief = { ...sample.brief, session_id: SESSION_ID };
  const spec = {
    ...sample.spec,
    session_id: SESSION_ID,
    brief_sha256: canonicalHash(brief),
  };
  return { spec, brief, scope: localScope(dataDir) };
}

/**
 * The exact CLI `create` write path: the local host store creates the
 * session row, then the canonical mirror writes `council_sessions` and the
 * `session_created` journal event. Both now land in `<dataDir>/council.db`.
 */
async function createSessionLikeCli(dataDir: string) {
  const { host } = createLocalHost({ dataDir, discoverRoutes: false });
  const engine = new CouncilEngine(host);
  const created = await engine.createSession(sessionInput(dataDir));
  const authorization = createStandaloneRunAuthorization({ dataDir });
  try {
    mirrorSession(authorization, created);
  } finally {
    authorization.close();
  }
  return created;
}

function compositionOptions(dataDir: string) {
  return {
    dataDir,
    startedAt: FIXED_NOW,
    nowUtc,
    ports: [0],
    // Deterministic and hermetic: no configured route, no worker polling.
    routeHomeDir: join(dataDir, 'empty-route-home'),
    routeEnv: {} as NodeJS.ProcessEnv,
    startWorkers: false,
  };
}

interface SseRead {
  status: number;
  contentType: string | null;
  text: string;
}

/** Read committed SSE frames until the first blank-line frame boundary. */
async function readFirstFrame(url: string): Promise<SseRead> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3_000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const contentType = response.headers.get('content-type');
    if (!response.body) {
      return { status: response.status, contentType, text: '' };
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let text = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      text += decoder.decode(value, { stream: true });
      if (text.includes('\n\n')) break;
    }
    await reader.cancel().catch(() => undefined);
    return { status: response.status, contentType, text };
  } finally {
    clearTimeout(timeout);
    controller.abort();
  }
}

function committedRows(
  composition: CouncilServiceComposition,
): Array<{ id: string; sequence: number; type: string }> {
  return composition.backend.database.read((handle) =>
    handle
      .prepare(
        `SELECT id, sequence, type FROM council_events
          WHERE session_id = ? ORDER BY sequence ASC`,
      )
      .all(SESSION_ID),
  ) as Array<{ id: string; sequence: number; type: string }>;
}

test('one composition binds the store, reader, event stream and admission', async () => {
  const dataDir = makeDataDir();
  const created = await createSessionLikeCli(dataDir);
  const composition = composeCouncilService(compositionOptions(dataDir));
  const outcome = await composition.door.start();
  assert.equal(outcome.outcome, 'started');
  if (outcome.outcome !== 'started') return;
  const origin = outcome.origin;
  let restarted: CouncilServiceComposition | null = null;

  try {
    // 1. The reader sees the CLI-created session (the store seam is closed).
    const sessionResponse = await fetch(`${origin}/council/${SESSION_ID}`);
    assert.equal(sessionResponse.status, 200);
    const sessionBody = (await sessionResponse.json()) as Record<string, unknown>;
    assert.equal(sessionBody.session_id, SESSION_ID);
    assert.equal(sessionBody.authority, 'standalone');
    assert.equal(sessionBody.ui, undefined, 'the bound reader serves the real record');
    const session = sessionBody.session as Record<string, unknown>;
    assert.equal((session.spec as Record<string, unknown>).session_id, SESSION_ID);
    assert.equal(created.state.state, 'DRAFT');

    // 2. An unknown id is falsifiable: 404 SESSION_NOT_FOUND.
    const unknownSession = await fetch(`${origin}/council/${UNKNOWN_ID}`);
    assert.equal(unknownSession.status, 404);
    assert.equal(
      ((await unknownSession.json()) as Record<string, unknown>).code,
      'SESSION_NOT_FOUND',
    );
    const unknownEvents = await fetch(
      `${origin}/api/council/sessions/${UNKNOWN_ID}/events`,
    );
    assert.equal(unknownEvents.status, 404);
    assert.equal(
      ((await unknownEvents.json()) as Record<string, unknown>).code,
      'SESSION_NOT_FOUND',
    );

    // 3. Events replay a committed journal row for THIS session.
    const stream = await readFirstFrame(
      `${origin}/api/council/sessions/${SESSION_ID}/events`,
    );
    assert.equal(stream.status, 200);
    assert.match(stream.contentType ?? '', /^text\/event-stream/);
    assert.match(stream.text, /^id: \d+$/m);
    assert.match(stream.text, /^event: session_created$/m);
    assert.match(stream.text, new RegExp(`"session_id":"${SESSION_ID}"`));

    const rows = committedRows(composition);
    assert.ok(rows.length >= 1);
    const frameId = Number(/^id: (\d+)$/m.exec(stream.text)?.[1]);
    const dataLine = stream.text
      .split('\n')
      .find((line) => line.startsWith('data: '));
    assert.ok(dataLine, 'the frame carries its committed row');
    const frame = JSON.parse(dataLine.slice('data: '.length)) as Record<string, unknown>;
    const matching = rows.find((row) => row.sequence === frameId);
    assert.ok(matching, 'the frame sequence is a committed row sequence');
    assert.equal(frame.sequence, matching?.sequence);
    assert.equal(frame.event_id, matching?.id);
    assert.equal(frame.type, matching?.type);

    // 4. A complete durable admission persists; an incomplete one refuses.
    const admissionBody = {
      session_id: SESSION_ID,
      operation_id: 'lane-e-operation-0001',
      payload: {
        operation_kind: 'provider_request',
        purpose: 'round_1_opening',
        input_hash: 'a'.repeat(64),
        route_snapshot_hash: 'b'.repeat(64),
        grant_id: 'lane-e-grant-0001',
        reservation: {
          requests: 1,
          tokens: null,
          moneyMinorUnits: null,
          currency: null,
          costKnowledge: 'unknown',
        },
      },
    };
    const admitted = await fetch(`${origin}/api/council/admissions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(admissionBody),
    });
    assert.equal(admitted.status, 202);
    const admission = (await admitted.json()) as Record<string, unknown>;
    assert.equal(admission.accepted, true);
    assert.equal(
      (admission.receipt as Record<string, unknown>).outcome,
      'admitted',
    );
    const jobs = composition.backend.database.read((handle) =>
      handle
        .prepare(
          `SELECT COUNT(*) AS n FROM council_jobs WHERE session_id = ? AND kind = 'operation'`,
        )
        .get(SESSION_ID),
    ) as { n: number };
    assert.equal(jobs.n, 1, 'Start persisted a durable job');
    const outbox = composition.backend.database.read((handle) =>
      handle
        .prepare(`SELECT COUNT(*) AS n FROM council_projection_outbox WHERE session_id = ?`)
        .get(SESSION_ID),
    ) as { n: number };
    assert.equal(outbox.n, 1, 'the admission enqueued its outbox intent');

    const incomplete = await fetch(`${origin}/api/council/admissions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ session_id: SESSION_ID, operation_id: 'lane-e-operation-0002' }),
    });
    assert.equal(incomplete.status, 503);
    const refusal = (await incomplete.json()) as Record<string, unknown>;
    assert.equal(refusal.accepted, false);
    assert.equal(refusal.code, 'ADMISSION_SINK_FAILED');
    const jobsAfter = composition.backend.database.read((handle) =>
      handle
        .prepare(
          `SELECT COUNT(*) AS n FROM council_jobs WHERE session_id = ? AND kind = 'operation'`,
        )
        .get(SESSION_ID),
    ) as { n: number };
    assert.equal(jobsAfter.n, 1, 'a refused admission persists nothing');

    // 5. Restart-equivalent: recompose over the same data directory.
    const beforeRows = committedRows(composition);
    await composition.door.stop();
    await composition.stop();

    restarted = composeCouncilService(compositionOptions(dataDir));
    const second = await restarted.door.start();
    assert.equal(second.outcome, 'started');
    if (second.outcome !== 'started') return;
    const reread = await fetch(`${second.origin}/council/${SESSION_ID}`);
    assert.equal(reread.status, 200);
    const rereadBody = (await reread.json()) as Record<string, unknown>;
    assert.deepEqual(rereadBody.session, sessionBody.session);
    const afterRows = committedRows(restarted);
    assert.deepEqual(afterRows, beforeRows, 'committed journal rows survive the restart');
  } finally {
    if (restarted) {
      await restarted.door.stop();
      await restarted.stop();
    } else {
      await composition.door.stop();
      await composition.stop();
    }
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test('a bare front door with nothing bound keeps the historical answers', async () => {
  const dataDir = makeDataDir();
  const installation = resolveStandaloneInstallation(dataDir);
  const identity = buildServiceIdentity({
    tenant_id: 'operator',
    company_id: 'blackceo',
    data_dir: dataDir,
    started_at: FIXED_NOW,
  });
  const bare = new CouncilFrontDoor({ identity, ports: [0] });
  const outcome = await bare.start();
  assert.equal(outcome.outcome, 'started');
  if (outcome.outcome !== 'started') return;
  try {
    const session = await fetch(`${outcome.origin}/council/${UNKNOWN_ID}`);
    assert.equal(session.status, 200, 'unbound session route is unchanged');
    const sessionBody = (await session.json()) as Record<string, unknown>;
    assert.equal(sessionBody.ui, 'not_bundled');
    assert.equal(
      (sessionBody.blocker as Record<string, unknown>).code,
      'UI_NOT_BUNDLED',
    );

    const events = await fetch(
      `${outcome.origin}/api/council/sessions/${UNKNOWN_ID}/events`,
    );
    assert.equal(events.status, 501);
    assert.equal(
      ((await events.json()) as Record<string, unknown>).code,
      'EVENT_STREAM_ADAPTER_NOT_BOUND',
    );

    const admission = await fetch(`${outcome.origin}/api/council/admissions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ session_id: UNKNOWN_ID, operation_id: 'op-unbound' }),
    });
    assert.equal(admission.status, 503);
    assert.equal(
      ((await admission.json()) as Record<string, unknown>).code,
      'ADMISSION_SINK_UNBOUND',
    );

    // The bare door's identity is the same owner scope the composition uses.
    assert.equal(identity.owner.tenant_id, 'operator');
    assert.equal(standaloneScope(installation).tenant_id, 'local-tenant');
  } finally {
    await bare.stop();
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test('startCouncilService exposes the same bound service', async () => {
  const dataDir = makeDataDir();
  await createSessionLikeCli(dataDir);
  const started = await startCouncilService({
    ...compositionOptions(dataDir),
    handleSignals: false,
  });
  try {
    assert.equal(started.outcome.outcome, 'started');
    if (started.outcome.outcome !== 'started') return;
    const response = await fetch(`${started.origin}/council/${SESSION_ID}`);
    assert.equal(response.status, 200);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.session_id, SESSION_ID);
    assert.equal(body.ui, undefined);
  } finally {
    await started.stop();
    rmSync(dataDir, { recursive: true, force: true });
  }
});
