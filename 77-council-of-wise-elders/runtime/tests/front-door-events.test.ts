/**
 * W21-U001 front-door event-stream and session-reader tests.
 *
 * Runner:
 *   node --import tsx --test tests/front-door-events.test.ts
 *
 * Tier A only: loopback HTTP on ephemeral ports. Every event frame and
 * every session record below is INJECTED TEST DATA — no database, no
 * provider dispatch, no credential, no network beyond 127.0.0.1, no
 * live advisor turn. The test proves the transport contract and that the
 * unbound answers are unchanged; it does not claim a composed backend.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatCouncilEventFrame,
  journalEventStreamAdapter,
  type CouncilEventFrame,
  type CouncilEventStreamAdapter,
  type CouncilSessionReader,
} from '../src/service/events.js';
import { CouncilFrontDoor, type FrontDoorOptions } from '../src/service/front-door.js';
import { buildServiceIdentity } from '../src/service/identity.js';
import type { JournalEvent } from '../src/persistence/journal.js';

const FIXED_NOW = '2026-10-19T12:00:00.000Z';

function identity(): FrontDoorOptions['identity'] {
  return buildServiceIdentity({
    tenant_id: 'tenant-w21',
    company_id: 'company-w21',
    data_dir: '/tmp/w21-u001-data',
    started_at: FIXED_NOW,
  });
}

async function startDoor(options: Partial<FrontDoorOptions>): Promise<{
  door: CouncilFrontDoor;
  origin: string;
  stop: () => Promise<void>;
}> {
  const door = new CouncilFrontDoor({
    identity: identity(),
    ports: [0],
    ...options,
  });
  const started = await door.start();
  assert.equal(started.outcome, 'started');
  assert.ok(started.origin);
  return {
    door,
    origin: started.origin,
    stop: async () => {
      await door.stop();
    },
  };
}

async function get(origin: string, path: string): Promise<Response> {
  return fetch(`${origin}${path}`, { redirect: 'manual' });
}

// ------------------------------------------------------------ unbound (base)

test('unbound: events keeps the exact 501 EVENT_STREAM_ADAPTER_NOT_BOUND body', async () => {
  const { origin, stop } = await startDoor({});
  try {
    const response = await get(origin, '/api/council/sessions/s1/events');
    assert.equal(response.status, 501);
    assert.equal(response.headers.get('content-type'), 'application/json; charset=utf-8');
    assert.deepEqual(await response.json(), {
      code: 'EVENT_STREAM_ADAPTER_NOT_BOUND',
      session_id: 's1',
      detail:
        'The durable event stream adapter is bound by the integration root over the canonical journal/outbox; this slice does not fabricate a live stream.',
      recovery:
        'Bind the durable event stream adapter and re-run service-readiness before advertising events.',
    });
  } finally {
    await stop();
  }
});

test('unbound: /council/<any-id> keeps the exact 200 ui:not_bundled body', async () => {
  const { origin, stop } = await startDoor({});
  try {
    // The historical defect: an id that cannot exist answered 200.
    const response = await get(origin, '/council/does-not-exist-123');
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'application/json; charset=utf-8');
    const url = `${origin}/council/does-not-exist-123`;
    assert.deepEqual(await response.json(), {
      session_id: 'does-not-exist-123',
      authority: 'standalone',
      url,
      ui: 'not_bundled',
      blocker: {
        code: 'UI_NOT_BUNDLED',
        detail: 'The shared Council UI build is not packaged by this service slice.',
        recovery:
          'Package the accepted shared Council UI build (WER-021 full packaging), then re-run service-readiness.',
      },
      api: {
        session: url,
        events: '/api/council/sessions/does-not-exist-123/events',
      },
    });
  } finally {
    await stop();
  }
});

// -------------------------------------------------------------- bound (head)

test('bound: events serves text/event-stream frames from the injected source', async () => {
  const frames: CouncilEventFrame[] = [
    { sequence: 1, type: 'session_created', event_id: 'evt-1', payload: { injected: true } },
    { sequence: 2, type: 'session_state_changed', event_id: 'evt-2' },
  ];
  const adapter: CouncilEventStreamAdapter = {
    open: (sessionId) =>
      sessionId === 'known-id'
        ? { replay: (after) => frames.filter((frame) => frame.sequence > after) }
        : null,
  };
  const { origin, stop } = await startDoor({ eventsAdapter: adapter });
  try {
    const response = await get(origin, '/api/council/sessions/known-id/events');
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'text/event-stream; charset=utf-8');
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const text = await response.text();
    assert.match(text, /^id: 1\nevent: session_created\ndata: /);
    assert.match(text, /"event_id":"evt-1"/);
    assert.match(text, /id: 2\nevent: session_state_changed\ndata: /);

    const unknown = await get(origin, '/api/council/sessions/unknown-id/events');
    assert.equal(unknown.status, 404);
    assert.equal((await unknown.json()).code, 'SESSION_NOT_FOUND');
  } finally {
    await stop();
  }
});

test('bound: /council/<id> is falsifiable — 404 unknown, 200 known with data', async () => {
  const reader: CouncilSessionReader = {
    read: (sessionId) =>
      sessionId === 'known-id'
        ? {
            session_id: 'known-id',
            state: { state: 'READY', state_version: 3 },
            spec: { session_id: 'known-id', mode: 'quick' },
          }
        : null,
  };
  const adapter: CouncilEventStreamAdapter = {
    open: () => ({ replay: () => [] }),
  };
  const { origin, stop } = await startDoor({ sessionReader: reader, eventsAdapter: adapter });
  try {
    const known = await get(origin, '/council/known-id');
    assert.equal(known.status, 200);
    const body = (await known.json()) as Record<string, unknown>;
    assert.equal(body.session_id, 'known-id');
    assert.equal(body.authority, 'standalone');
    assert.equal(body.url, `${origin}/council/known-id`);
    assert.deepEqual(body.session, {
      session_id: 'known-id',
      state: { state: 'READY', state_version: 3 },
      spec: { session_id: 'known-id', mode: 'quick' },
    });

    const unknown = await get(origin, '/council/does-not-exist-123');
    assert.equal(unknown.status, 404);
    const refused = (await unknown.json()) as Record<string, unknown>;
    assert.equal(refused.code, 'SESSION_NOT_FOUND');
    assert.equal(refused.session_id, 'does-not-exist-123');

    // With a bound reader the events route is falsifiable too.
    const unknownStream = await get(origin, '/api/council/sessions/unknown-id/events');
    assert.equal(unknownStream.status, 404);
    assert.equal((await unknownStream.json()).code, 'SESSION_NOT_FOUND');
  } finally {
    await stop();
  }
});

// ------------------------------------------------- canonical journal adapter

function journalEvent(sequence: number, type: string): JournalEvent {
  return {
    event_id: `evt-${sequence}`,
    type: type as JournalEvent['type'],
    sequence,
    from_state: null,
    to_state: 'READY',
    actor_subject: 'operator',
    payload: { injected: true, sequence },
    prev_hash: sequence === 1 ? '' : 'hash',
    event_hash: `hash-${sequence}`,
    created_at: FIXED_NOW,
  };
}

test('journal adapter: replay reads committed rows and format matches the accepted SSE wire', async () => {
  const rows: JournalEvent[] = [journalEvent(1, 'session_created')];
  const adapter = journalEventStreamAdapter({
    journal: {
      list: (_envelope, _sessionId, after) => rows.filter((row) => row.sequence > (after ?? 0)),
    },
    envelope: {
      tenant_id: 'tenant-w21',
      company_id: 'company-w21',
      installation_id: 'installation-w21',
      actor_subject: 'operator',
      actor: 'worker',
      purpose: 'read',
    },
  });
  const cursor = await adapter.open('known-id');
  assert.ok(cursor);
  const frames = await cursor.replay(0);
  assert.equal(frames.length, 1);
  assert.equal(frames[0].event_id, 'evt-1');
  assert.equal(
    formatCouncilEventFrame(frames[0]),
    `id: 1\nevent: session_created\ndata: ${JSON.stringify(frames[0])}\n\n`,
  );
});

test('journal adapter: follow delivers a newly committed row, never a synthetic one', async () => {
  const rows: JournalEvent[] = [journalEvent(1, 'session_created')];
  const adapter = journalEventStreamAdapter({
    journal: {
      list: (_envelope, _sessionId, after) => rows.filter((row) => row.sequence > (after ?? 0)),
    },
    envelope: {
      tenant_id: 'tenant-w21',
      company_id: 'company-w21',
      installation_id: 'installation-w21',
      actor_subject: 'operator',
      actor: 'worker',
      purpose: 'read',
    },
    poll_ms: 5,
  });
  const cursor = await adapter.open('known-id');
  assert.ok(cursor?.subscribe, 'journal adapter follows the journal');
  const received: CouncilEventFrame[] = [];
  const detach = cursor.subscribe((frame) => received.push(frame));
  try {
    await cursor.replay(0); // cursor now at sequence 1
    rows.push(journalEvent(2, 'session_state_changed'));
    const deadline = Date.now() + 2_000;
    while (received.length === 0 && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    assert.deepEqual(received.map((frame) => frame.sequence), [2]);
    assert.equal(received[0].type, 'session_state_changed');
  } finally {
    detach();
  }
});
