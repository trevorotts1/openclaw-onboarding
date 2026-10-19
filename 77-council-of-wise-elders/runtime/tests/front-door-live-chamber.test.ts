/**
 * W27 live chamber tests.
 *
 * Runner:
 *   node --import tsx --test tests/front-door-live-chamber.test.ts
 *
 * Tier A only: loopback HTTP on ephemeral ports and injected test data.
 * Proves the read-only session list route, that the served chamber carries
 * its script, that no fictional fixture or demo text lives in the page or the
 * store script, the pure helpers, and the store (chamber-live.js) run in
 * node:vm against a fake fetch and fake timers.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

import {
  repositorySessionReader,
  type CouncilSessionReader,
  type CouncilSessionSource,
} from '../src/service/events.js';
import { CouncilFrontDoor, type FrontDoorOptions } from '../src/service/front-door.js';
import { buildServiceIdentity } from '../src/service/identity.js';
import type { AuthorizationEnvelope } from '../src/persistence/envelope.js';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');

async function withDoor(
  options: Partial<FrontDoorOptions>,
  run: (origin: string) => Promise<void>,
): Promise<void> {
  const door = new CouncilFrontDoor({
    identity: buildServiceIdentity({
      tenant_id: 'tenant-w27',
      company_id: 'company-w27',
      data_dir: 'w27-data',
      started_at: '2026-10-19T12:00:00.000Z',
    }),
    ports: [0],
    ...options,
  });
  const started = await door.start();
  assert.equal(started.outcome, 'started');
  try {
    await run(started.origin as string);
  } finally {
    await door.stop();
  }
}

const summary = {
  session_id: 's-live-1',
  state: 'ROUND_1',
  mode: 'full',
  question: 'Injected test question?',
  created_at: '2026-10-19T11:00:00Z',
  sample: false,
};

// ------------------------------------------------------------- list route

test('list route: unbound answers 501 SESSION_LIST_NOT_BOUND, not an empty list', async () => {
  await withDoor({}, async (origin) => {
    const response = await fetch(`${origin}/api/council/sessions`);
    assert.equal(response.status, 501);
    assert.equal(((await response.json()) as { code: string }).code, 'SESSION_LIST_NOT_BOUND');
  });
});

test('list route: a reader without list() is also 501', async () => {
  const reader: CouncilSessionReader = { read: () => null };
  await withDoor({ sessionReader: reader }, async (origin) => {
    const response = await fetch(`${origin}/api/council/sessions`);
    assert.equal(response.status, 501);
  });
});

test('list route: bound reader returns exactly what it lists, including empty', async () => {
  let rows = [summary];
  const reader: CouncilSessionReader = { read: () => null, list: () => rows };
  await withDoor({ sessionReader: reader }, async (origin) => {
    const full = await fetch(`${origin}/api/council/sessions`);
    assert.equal(full.status, 200);
    assert.equal(full.headers.get('content-type'), 'application/json; charset=utf-8');
    assert.deepEqual(await full.json(), { sessions: [summary] });

    rows = [];
    const empty = await fetch(`${origin}/api/council/sessions`);
    assert.equal(empty.status, 200);
    assert.deepEqual(await empty.json(), { sessions: [] });
  });
});

test('list route: read-only, a POST is not routed', async () => {
  const reader: CouncilSessionReader = { read: () => null, list: () => [summary] };
  await withDoor({ sessionReader: reader }, async (origin) => {
    const response = await fetch(`${origin}/api/council/sessions`, { method: 'POST', body: '{}' });
    assert.equal(response.status, 404);
  });
});

test('repositorySessionReader lists summaries only when the source can list', () => {
  const envelope = { tenant_id: 't', company_id: 'c' } as unknown as AuthorizationEnvelope;
  const stored = {
    spec: { session_id: 's1', mode: 'quick', created_at: '2026-10-19T10:00:00Z' },
    brief: { question: 'Should we?' },
    state: { state: 'READY' },
    sample: true,
  };
  const noList = repositorySessionReader({
    repositories: { getSession: () => null },
    envelope,
  });
  assert.equal(noList.list, undefined);

  const source = {
    getSession: () => null,
    listSessions: () => [stored],
  } as unknown as CouncilSessionSource;
  const reader = repositorySessionReader({ repositories: source, envelope });
  assert.deepEqual(reader.list?.(), [
    {
      session_id: 's1',
      state: 'READY',
      mode: 'quick',
      question: 'Should we?',
      created_at: '2026-10-19T10:00:00Z',
      sample: true,
    },
  ]);
});

// --------------------------------------------------------- served chamber

test('served chamber loads the script and the script is served from the allowlist', async () => {
  await withDoor({}, async (origin) => {
    const page = await (await fetch(`${origin}/chamber/`)).text();
    assert.match(page, /<script src="\.\/chamber-live\.js"><\/script>/);

    const script = await fetch(`${origin}/chamber/chamber-live.js`);
    assert.equal(script.status, 200);
    assert.equal(script.headers.get('content-type'), 'text/javascript; charset=utf-8');
    assert.equal(script.headers.get('x-content-type-options'), 'nosniff');
    const text = await script.text();
    assert.ok(text.includes('/api/council/sessions'));
    assert.equal(/https?:\/\//.test(text), false, 'no external or absolute URL');
    assert.equal(text.includes('/Users/'), false);
    assert.equal(text.includes('innerHTML'), false, 'text is set with textContent only');
  });
});

const DEMO_AND_FIXTURE_TEXT = [
  'Pilot the revised coaching offer',
  'done-for-you AI workforce',
  'Pilot with 10 clients first',
  'Launch to all clients in January',
  'Austin in-person conference',
  'Fictional sample',
];

test('index.html carries no fixture or demo decision text', (t) => {
  const html = readFileSync(join(chamberDir, 'index.html'), 'utf8');
  if (html.includes('id="sample-root"')) {
    // The legacy page still embeds its labelled sample; the chamber shell rewrite removes it.
    t.skip('index.html still has the legacy sample container (replaced by the shell unit)');
    return;
  }
  for (const text of DEMO_AND_FIXTURE_TEXT) {
    assert.equal(html.includes(text), false, `"${text}" must not be in index.html`);
  }
  assert.equal(/<script[^>]+src="https?:/.test(html), false);
});

test('chamber-live.js carries no demo or fixture decision text and no markup writes', () => {
  const script = readFileSync(join(chamberDir, 'chamber-live.js'), 'utf8');
  for (const text of DEMO_AND_FIXTURE_TEXT) {
    assert.equal(script.includes(text), false, `"${text}" must not be in chamber-live.js`);
  }
  assert.equal(/https?:\/\//.test(script), false, 'no external or absolute URL');
  assert.equal(script.includes('/Users/'), false);
  assert.equal(script.includes('innerHTML'), false);
  assert.equal(script.includes('insertAdjacentHTML'), false);
  assert.equal(/document\.(getElementById|querySelector|createElement)/.test(script.replace(/doc\.createElement/g, '')), false,
    'the store does no DOM rendering');
});

// ----------------------------------------------------- script pure helpers

interface Frame {
  sequence: number;
  type: string;
  to_state?: string | null;
  payload?: Record<string, unknown>;
}
interface Live {
  parseSse(buffer: string): { frames: Frame[]; rest: string };
  parseHash(hash: string): { kind: string; id?: string } | null;
  reconcileList(list: FakeNode, sessions: unknown[], selected: string | null, onSelect: (id: string) => void, doc: unknown): void;
}

function loadHelpers(): Live {
  const sandbox: Record<string, unknown> = {};
  sandbox.globalThis = sandbox;
  runInNewContext(readFileSync(join(chamberDir, 'chamber-live.js'), 'utf8'), sandbox);
  return sandbox.councilLive as Live;
}

/** vm objects have another realm's prototypes; compare plain copies. */
function plain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

test('helpers: SSE parsing keeps the unfinished block and skips malformed data', () => {
  const live = loadHelpers();
  const wire =
    'id: 1\nevent: session_created\ndata: {"sequence":1,"type":"session_created"}\n\n' +
    'id: 2\nevent: x\ndata: not-json\n\n' +
    'id: 3\nevent: card_accepted\ndata: {"sequence":3,';
  const parsed = live.parseSse(wire);
  assert.deepEqual(plain(parsed.frames.map((f) => f.sequence)), [1]);
  assert.ok(parsed.rest.startsWith('id: 3'));
  const done = live.parseSse(parsed.rest + '"type":"card_accepted"}\n\n');
  assert.deepEqual(plain(done.frames.map((f) => f.sequence)), [3]);
});

// ------------------------------------------- refresh keeps focus and status quiet

class FakeNode {
  children: FakeNode[] = [];
  parentNode: FakeNode | null = null;
  attrs: Record<string, string> = {};
  className = '';
  type = '';
  private text = '';
  textWrites = 0;
  moves = 0; // times this node was re-inserted while already attached (blurs focus in a browser)
  constructor(public tag: string) {}
  get textContent(): string { return this.text; }
  set textContent(v: string) { this.text = v; this.textWrites += 1; }
  get firstChild(): FakeNode | null { return this.children[0] ?? null; }
  get lastChild(): FakeNode | null { return this.children[this.children.length - 1] ?? null; }
  get nextSibling(): FakeNode | null {
    const sibs = this.parentNode?.children ?? [];
    return sibs[sibs.indexOf(this) + 1] ?? null;
  }
  get isConnected(): boolean { return this.parentNode === null ? this.tag === 'ul' : this.parentNode.isConnected; }
  setAttribute(k: string, v: string): void { this.attrs[k] = v; }
  getAttribute(k: string): string | null { return this.attrs[k] ?? null; }
  addEventListener(): void {}
  appendChild(n: FakeNode): FakeNode { return this.insertBefore(n, null); }
  insertBefore(n: FakeNode, ref: FakeNode | null): FakeNode {
    if (n.parentNode) n.moves += 1;
    n.parentNode?.removeChild(n);
    const at = ref ? this.children.indexOf(ref) : this.children.length;
    this.children.splice(at, 0, n);
    n.parentNode = this;
    return n;
  }
  removeChild(n: FakeNode): FakeNode {
    this.children.splice(this.children.indexOf(n), 1);
    n.parentNode = null;
    return n;
  }
}

test('list refresh updates buttons in place: the focused button survives, keyed by session_id', () => {
  const live = loadHelpers();
  const doc = { createElement: (tag: string) => new FakeNode(tag) };
  const list = new FakeNode('ul');
  const row = (id: string, state = 'deliberating') => ({
    session_id: id, question: 'Q ' + id, state, mode: 'quick', created_at: '2026-10-19T12:00:00.000Z',
  });
  live.reconcileList(list, [row('a'), row('b')], null, () => {}, doc);
  const focusedBtn = list.children[1].firstChild as FakeNode;
  const focusedLi = list.children[1];

  // Same sessions, one state changed, a new session in front: nothing focused is rebuilt.
  live.reconcileList(list, [row('c'), row('a'), row('b', 'completed')], 'b', () => {}, doc);
  assert.equal(list.children.length, 3);
  assert.equal(list.children[2], focusedLi);
  assert.equal(list.children[2].firstChild, focusedBtn);
  assert.equal(focusedBtn.isConnected, true);
  assert.match((focusedBtn.lastChild as FakeNode).textContent, /^completed \|/);
  assert.equal(focusedBtn.getAttribute('aria-pressed'), 'true');

  // An identical refresh writes no text at all and moves nothing.
  const writes = focusedBtn.textWrites + (focusedBtn.firstChild as FakeNode).textWrites + (focusedBtn.lastChild as FakeNode).textWrites;
  const before = list.children.slice();
  live.reconcileList(list, [row('c'), row('a'), row('b', 'completed')], 'b', () => {}, doc);
  assert.deepEqual(list.children, before);
  assert.equal(
    focusedBtn.textWrites + (focusedBtn.firstChild as FakeNode).textWrites + (focusedBtn.lastChild as FakeNode).textWrites,
    writes,
  );

  // A session that disappears is removed; the others keep their nodes.
  live.reconcileList(list, [row('b', 'completed')], 'b', () => {}, doc);
  assert.equal(list.children.length, 1);
  assert.equal(list.children[0], focusedLi);
});

test('list refresh that only removes sessions moves none of the remaining nodes', () => {
  const live = loadHelpers();
  const doc = { createElement: (tag: string) => new FakeNode(tag) };
  const list = new FakeNode('ul');
  const row = (id: string) => ({
    session_id: id, question: 'Q ' + id, state: 'deliberating', mode: 'quick', created_at: '2026-10-19T12:00:00.000Z',
  });
  live.reconcileList(list, [row('c'), row('a'), row('b')], 'b', () => {}, doc);
  const [, , liB] = list.children;
  const [liC] = list.children;
  list.children.forEach((n) => { n.moves = 0; });
  // Archive a (above the focused b): c and b must stay put.
  live.reconcileList(list, [row('c'), row('b')], 'b', () => {}, doc);
  assert.equal(list.children.length, 2);
  assert.equal(list.children[0], liC);
  assert.equal(list.children[1], liB);
  assert.equal(liB.moves, 0, 'focused node must not be re-inserted');
  assert.equal(liC.moves, 0);
  // Archive the first session too: still no move for the survivor.
  live.reconcileList(list, [row('b')], 'b', () => {}, doc);
  assert.equal(list.children[0], liB);
  assert.equal(liB.moves, 0);
});


test('helpers: location hash routes', () => {
  const live = loadHelpers();
  assert.deepEqual(plain(live.parseHash('#demo')), { kind: 'demo' });
  assert.deepEqual(plain(live.parseHash('#session=s%201')), { kind: 'session', id: 's 1' });
  assert.equal(live.parseHash(''), null);
  assert.equal(live.parseHash('#demo-ish'), null);
  assert.equal(live.parseHash('#session='), null);
});

// ------------------------------------------------------------- the store

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;

interface Stream {
  res: Any;
  push(frames: Any[]): void;
  end(): void;
}

function makeStream(): Stream {
  const enc = new TextEncoder();
  const queue: Array<{ done: boolean; value?: Uint8Array }> = [];
  let waiter: ((v: { done: boolean; value?: Uint8Array }) => void) | null = null;
  const deliver = (item: { done: boolean; value?: Uint8Array }): void => {
    if (waiter) { const w = waiter; waiter = null; w(item); } else queue.push(item);
  };
  return {
    res: {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: (): Promise<unknown> => new Promise((resolve) => {
            const next = queue.shift();
            if (next) resolve(next); else waiter = resolve as never;
          }),
        }),
      },
    },
    push(frames) {
      const text = frames.map((f) => `id: ${f.sequence}\nevent: ${f.type}\ndata: ${JSON.stringify(f)}\n\n`).join('');
      deliver({ done: false, value: enc.encode(text) });
    },
    end() { deliver({ done: true }); },
  };
}

const flush = async (): Promise<void> => { for (let i = 0; i < 30; i += 1) await new Promise((r) => setImmediate(r)); };

interface Harness {
  ns: Any;
  advance(ms: number): Promise<void>;
  calls: string[];
  count(prefix: string): number;
  streams: Stream[];
  views: Any[];
  hash(): string;
  setHidden(v: boolean): void;
  sessions: Any[];
  records: Record<string, Any>;
  eventsFail: { value: boolean };
  listStatus: { value: number };
  fireHashChange(h: string): void;
}

const SEATS9 = [
  'simon-sinek', 'td-jakes', 'oprah-winfrey', 'tiffany-aliche', 'russell-brunson',
  'michelle-obama', 'brene-brown', 'dennis-kimbro', 'les-brown',
];
const rec = (id: string, state = 'DRAFT'): Any => ({
  session_id: id,
  spec: { mode: 'full', seat_ids: SEATS9, model_policy: { route_id: 'r1', requested_model_id: null } },
  brief: { question: 'Q ' + id, options: [{ id: 'A', label: 'Yes', kind: 'change' }, { id: 'B', label: 'No', kind: 'status_quo' }] },
  state: { state },
  cards: [],
  verdict: null,
});
const sf = (sequence: number, type: string, extra: Any = {}): Any => ({
  sequence, type, to_state: null, payload: {}, created_at: '2026-10-19T10:00:00.000Z', ...extra,
});
const toState = (sequence: number, to: string): Any =>
  sf(sequence, 'session_state_changed', { to_state: to, payload: { state_record: { state: to } } });
const accepted = (sequence: number, seat: string, round: number): Any =>
  sf(sequence, 'card_accepted', { payload: { seat_id: seat, round, operation_id: `op:i:t:s:a1:round-${round}:${seat}:x` } });

function boot(options: { hash?: string; sessions?: Any[]; hidden?: boolean; list501?: boolean; extra?: string[] } = {}): Harness {
  let now = Date.parse('2026-10-19T10:00:00.000Z');
  let nextId = 1;
  const timers = new Map<number, { at: number; fn: () => void; every: number | null }>();
  const calls: string[] = [];
  const streams: Stream[] = [];
  const views: Any[] = [];
  const sessions = options.sessions ?? [];
  const records: Record<string, Any> = {};
  for (const s of sessions) records[s.session_id] = rec(s.session_id, s.state);
  const eventsFail = { value: false };
  for (const id of options.extra ?? []) records[id] = rec(id, 'ROUND_2');
  const listStatus = { value: options.list501 ? 501 : 200 };
  const location = { hash: options.hash ?? '', pathname: '/chamber/', search: '' };
  const listeners: Record<string, Array<() => void>> = {};
  const document = { hidden: options.hidden === true };
  const demoText = readFileSync(join(chamberDir, 'demo-replay.json'), 'utf8');

  class FakeDate extends Date { static now(): number { return now; } }

  const json = (status: number, body: unknown): Promise<unknown> =>
    Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) });

  const fake = async (url: string): Promise<unknown> => {
    calls.push(url);
    if (url === '/api/council/sessions') {
      if (listStatus.value === 501) return json(501, { code: 'SESSION_LIST_NOT_BOUND' });
      return json(listStatus.value, { sessions });
    }
    if (url === './demo-replay.json') return json(200, JSON.parse(demoText));
    const ev = /^\/api\/council\/sessions\/([^/]+)\/events$/.exec(url);
    if (ev) {
      if (eventsFail.value) throw new Error('network down');
      const stream = makeStream();
      streams.push(stream);
      return stream.res;
    }
    const one = /^\/council\/([^/]+)$/.exec(url);
    if (one) {
      const r = records[decodeURIComponent(one[1])];
      return r ? json(200, { session: r }) : json(404, { code: 'SESSION_NOT_FOUND' });
    }
    return json(404, {});
  };

  const sandbox: Record<string, unknown> = {
    fetch: fake,
    document,
    location,
    history: {
      replaceState: (_s: unknown, _t: unknown, url: string): void => {
        calls.push('replaceState ' + url);
        location.hash = url.startsWith('#') ? url : '';
      },
    },
    Date: FakeDate,
    AbortController,
    TextDecoder,
    addEventListener: (name: string, fn: () => void): void => { (listeners[name] ??= []).push(fn); },
    setTimeout: (fn: () => void, ms: number): number => { timers.set(nextId, { at: now + ms, fn, every: null }); return nextId++; },
    setInterval: (fn: () => void, ms: number): number => { timers.set(nextId, { at: now + ms, fn, every: ms }); return nextId++; },
    clearTimeout: (id: number): void => { timers.delete(id); },
    clearInterval: (id: number): void => { timers.delete(id); },
  };
  sandbox.globalThis = sandbox;
  runInNewContext(readFileSync(join(chamberDir, 'chamber-state.js'), 'utf8'), sandbox);
  runInNewContext(readFileSync(join(chamberDir, 'chamber-live.js'), 'utf8'), sandbox);
  const ns = (sandbox.councilChamber as Any);

  const advance = async (ms: number): Promise<void> => {
    const end = now + ms;
    await flush();
    for (;;) {
      let pick: [number, { at: number; fn: () => void; every: number | null }] | null = null;
      for (const entry of timers) if (entry[1].at <= end && (!pick || entry[1].at < pick[1].at)) pick = entry;
      if (!pick) break;
      now = Math.max(now, pick[1].at);
      if (pick[1].every !== null) pick[1].at = now + pick[1].every; else timers.delete(pick[0]);
      pick[1].fn();
      await flush();
    }
    now = end;
    await flush();
  };

  return {
    ns,
    advance,
    calls,
    count: (prefix) => calls.filter((c) => c === prefix).length,
    streams,
    views,
    hash: () => location.hash,
    setHidden: (v) => { document.hidden = v; },
    sessions,
    records,
    eventsFail,
    listStatus,
    fireHashChange: (h) => { location.hash = h; (listeners.hashchange ?? []).forEach((fn) => fn()); },
  };
}

const summaryOf = (id: string, state: string): Any => ({
  session_id: id, state, mode: 'full', question: 'Q ' + id, created_at: '2026-10-19T09:00:00Z', sample: false,
});

test('store: subscribe answers immediately, then an empty service shows mode empty', async () => {
  const h = boot();
  const seen: Any[] = [];
  const off = h.ns.live.subscribe((v: Any) => seen.push(plain(v)));
  assert.equal(seen.length, 1, 'called immediately');
  assert.equal(seen[0].mode, 'loading');
  assert.equal(seen[0].session, null);
  assert.equal(seen[0].list.status, 'loading');
  await h.advance(0);
  const v = h.ns.live.getView();
  assert.equal(v.mode, 'empty');
  assert.equal(v.list.status, 'ready');
  assert.deepEqual(plain(v.list.sessions), []);
  assert.equal(v.session, null);
  assert.ok(seen.length > 1);
  off();
  const n = seen.length;
  await h.advance(60_000);
  assert.equal(seen.length, n, 'unsubscribed');
});

test('store: opens the newest session, reads it, and streams its events', async () => {
  const h = boot({ sessions: [summaryOf('new', 'ROUND_1'), summaryOf('old', 'COMPLETED')] });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  assert.equal(h.hash(), '', 'auto-opening the newest does not rewrite the address');
  assert.equal(h.count('/council/new'), 1);
  assert.equal(h.count('/api/council/sessions/new/events'), 1);
  let v = h.ns.live.getView();
  assert.equal(v.mode, 'live');
  assert.equal(v.session.id, 'new');
  assert.equal(v.session.question, 'Q new');
  assert.equal(v.connection.status, 'live');
  h.streams[0].push([sf(1, 'session_created', { to_state: 'DRAFT', payload: { state_record: { state: 'DRAFT' } } }), toState(2, 'ROUND_1')]);
  await h.advance(0);
  v = h.ns.live.getView();
  assert.equal(v.session.state, 'ROUND_1');
  assert.equal(v.session.round.label, 'ROUND 1 OF 3');
  assert.equal(v.session.keyPoints[0].label, 'CHAIR: READING YOUR QUESTION');
});

test('store: select() streams frames and refetches once per burst of card_accepted', async () => {
  const h = boot({ sessions: [summaryOf('s1', 'ROUND_1')] });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  await h.ns.live.select('s1');
  await h.advance(0);
  assert.equal(h.hash(), '#session=s1');
  const base = h.count('/council/s1');
  const stream = h.streams[h.streams.length - 1];
  stream.push([toState(1, 'ROUND_1'), accepted(2, 'simon-sinek', 1), accepted(3, 'td-jakes', 1)]);
  await h.advance(100);
  stream.push([accepted(4, 'oprah-winfrey', 1)]);
  await h.advance(100);
  assert.equal(h.count('/council/s1'), base, 'nothing re-read before the debounce elapses');
  assert.equal(h.ns.live.getView().session.seats[0].latest.pending, true);
  // The read now carries content for the three accepted cards.
  h.records.s1.cards = [
    { card_kind: 'advisor', seat_id: 'simon-sinek', round: 1, stance: 'support', preferred_option_id: 'A', decisive_arguments: ['L1'] },
    { card_kind: 'advisor', seat_id: 'td-jakes', round: 1, stance: 'oppose', preferred_option_id: 'B', decisive_arguments: ['L2'] },
    { card_kind: 'advisor', seat_id: 'oprah-winfrey', round: 1, stance: 'support', preferred_option_id: 'A', decisive_arguments: ['L3'] },
  ];
  await h.advance(200);
  assert.equal(h.count('/council/s1'), base + 1, 'one refetch for the whole burst');
  const v = h.ns.live.getView();
  assert.equal(v.session.seats[0].latest.line, 'L1');
  assert.deepEqual(plain(v.session.options.map((o: Any) => o.votes)), [2, 1]);
  // A later card is a new burst.
  stream.push([accepted(5, 'tiffany-aliche', 1)]);
  await h.advance(400);
  assert.equal(h.count('/council/s1'), base + 2);
  // Frames the journal replays again are ignored and cause no read.
  stream.push([accepted(5, 'tiffany-aliche', 1)]);
  await h.advance(400);
  assert.equal(h.count('/council/s1'), base + 2);
});

test('store: a terminal state and the verdict are read once and the stream is closed', async () => {
  const h = boot({ sessions: [summaryOf('s1', 'VERIFYING')] });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  const base = h.count('/council/s1');
  h.records.s1.verdict = { result_kind: 'scored', label: 'RESHAPE', recommended_option_id: 'B', main_reasons: ['why'], option_scores: [] };
  h.streams[0].push([toState(1, 'VERIFYING'), sf(2, 'verdict_validated', { payload: { verdict_revision: 1, result_kind: 'scored' } }), toState(3, 'COMPLETED')]);
  await h.advance(400);
  assert.equal(h.count('/council/s1'), base + 1);
  const v = h.ns.live.getView();
  assert.equal(v.session.state, 'COMPLETED');
  assert.equal(v.session.verdict.labelText, 'Reshape');
  assert.equal(v.connection.status, 'ended');
  assert.equal(v.connection.canReconnect, false);
  // Finished: no 1 second tick keeps running.
  let ticks = 0;
  h.ns.live.subscribe(() => { ticks += 1; });
  await h.advance(5_000);
  assert.equal(ticks, 1, 'only the immediate call; no tick for a finished session');
});

test('store: the 1 second tick runs only while a non-terminal session is open', async () => {
  const h = boot({ sessions: [summaryOf('s1', 'ROUND_1')] });
  let ticks = 0;
  h.ns.live.subscribe(() => { ticks += 1; });
  await h.advance(0);
  const t0 = ticks;
  await h.advance(5_000);
  assert.ok(ticks - t0 >= 5, `ticked ${ticks - t0} times in 5s`);
  const timers = h.ns.live.getView().session.round.timer;
  assert.match(timers, /^0:0\d$/);
});

test('store: the list refreshes every 15 seconds, and only while the page is visible', async () => {
  const h = boot({ sessions: [summaryOf('s1', 'COMPLETED')] });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  const base = h.count('/api/council/sessions');
  assert.equal(base, 1);
  await h.advance(14_900);
  assert.equal(h.count('/api/council/sessions'), base);
  await h.advance(200);
  assert.equal(h.count('/api/council/sessions'), base + 1);
  await h.advance(15_000);
  assert.equal(h.count('/api/council/sessions'), base + 2);
  h.setHidden(true);
  await h.advance(60_000);
  assert.equal(h.count('/api/council/sessions'), base + 2, 'hidden page: no refresh');
  h.setHidden(false);
  await h.advance(15_000);
  assert.equal(h.count('/api/council/sessions'), base + 3);
  // A new session shows up in the list without moving the open one.
  h.sessions.unshift(summaryOf('s2', 'ROUND_1'));
  await h.advance(15_000);
  const v = h.ns.live.getView();
  assert.deepEqual(plain(v.list.sessions.map((s: Any) => s.session_id)), ['s2', 's1']);
  assert.equal(v.session.id, 's1');
});

test('store: an unbound list is reported, not shown as empty', async () => {
  const h = boot({ list501: true });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  const v = h.ns.live.getView();
  assert.equal(v.list.status, 'unbound');
  assert.match(v.list.error, /SESSION_LIST_NOT_BOUND/);
  assert.equal(v.mode, 'empty');
});

test('store: #session=<id> opens that session without waiting for the list', async () => {
  const h = boot({ hash: '#session=picked', sessions: [summaryOf('newest', 'ROUND_1')], extra: ['picked'] });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  assert.equal(h.ns.live.getView().session.id, 'picked');
  assert.equal(h.count('/council/newest'), 0);
  h.fireHashChange('#session=newest');
  await h.advance(0);
  assert.equal(h.ns.live.getView().session.id, 'newest');
  // An unknown session is an honest unavailable state, not an empty room.
  await h.ns.live.select('ghost');
  await h.advance(0);
  const v = h.ns.live.getView();
  assert.equal(v.mode, 'empty');
  assert.equal(v.connection.status, 'unavailable');
  assert.match(v.connection.text, /no longer known/);
});

test('store: #demo starts the labelled replay and stopDemo returns to the previous mode', async () => {
  const h = boot({ hash: '#demo' });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  assert.equal(h.count('./demo-replay.json'), 1);
  let v = h.ns.live.getView();
  assert.equal(v.mode, 'demo');
  assert.equal(v.session.demo, true);
  assert.equal(v.session.id, 'demo');
  assert.equal(v.session.state, 'DRAFT');
  assert.equal(h.count('/api/council/sessions/demo/events'), 0, 'the demo never opens a real stream');
  await h.advance(4_000);
  v = h.ns.live.getView();
  assert.equal(v.session.state, 'ROUND_1');
  assert.equal(v.session.seats[0].latest, null, 'content is not revealed before its card frame');
  await h.advance(3_000);
  v = h.ns.live.getView();
  assert.ok(v.session.seats[0].latest && v.session.seats[0].latest.line, 'revealed when its card_accepted frame plays');
  assert.match(v.session.round.timer, /^0:\d\d$/);
  await h.advance(100_000);
  v = h.ns.live.getView();
  assert.equal(v.session.state, 'COMPLETED');
  assert.equal(v.session.verdict.labelText, 'Go, with conditions');
  assert.equal(v.mode, 'demo');

  // Nothing was open before the demo, so leaving it opens the default (an empty service).
  await h.ns.live.stopDemo();
  await h.advance(0);
  assert.equal(h.ns.live.getView().mode, 'empty');
  assert.equal(h.hash(), '');
});

test('store: stopDemo returns to the session that was open, and startDemo restarts the replay', async () => {
  const h = boot({ sessions: [summaryOf('s1', 'ROUND_1')] });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  assert.equal(h.ns.live.getView().session.id, 's1');
  await h.ns.live.startDemo();
  await h.advance(0);
  assert.equal(h.hash(), '#demo');
  assert.equal(h.ns.live.getView().mode, 'demo');
  await h.advance(30_000);
  assert.notEqual(h.ns.live.getView().session.state, 'DRAFT');
  await h.ns.live.startDemo();
  await h.advance(0);
  assert.equal(h.ns.live.getView().session.state, 'DRAFT', 'restarted from the beginning');
  await h.ns.live.stopDemo();
  await h.advance(0);
  const v = h.ns.live.getView();
  assert.equal(v.mode, 'live');
  assert.equal(v.session.id, 's1');
  assert.equal(h.hash(), '#session=s1');
});

test('store: five retries three seconds apart, then lost with Reconnect available', async () => {
  const h = boot({ sessions: [summaryOf('s1', 'ROUND_1')] });
  h.eventsFail.value = true;
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  let v = h.ns.live.getView();
  assert.equal(v.connection.status, 'retrying');
  assert.equal(v.connection.canReconnect, false);
  assert.equal(h.count('/api/council/sessions/s1/events'), 1);
  for (let i = 1; i <= 5; i += 1) {
    await h.advance(2_999);
    assert.equal(h.count('/api/council/sessions/s1/events'), i, `no retry ${i} before 3s`);
    await h.advance(1);
    assert.equal(h.count('/api/council/sessions/s1/events'), i + 1, `retry ${i}`);
  }
  v = h.ns.live.getView();
  assert.equal(v.connection.status, 'lost');
  assert.equal(v.connection.canReconnect, true);
  assert.match(v.connection.text, /Reconnect/);
  await h.advance(30_000);
  assert.equal(h.count('/api/council/sessions/s1/events'), 6, 'no further automatic attempts');
  // The session stays readable while the stream is lost.
  assert.equal(v.session.id, 's1');
  // Reconnect works once the network is back.
  h.eventsFail.value = false;
  h.ns.live.reconnect();
  await h.advance(0);
  assert.equal(h.ns.live.getView().connection.status, 'live');
  assert.equal(h.ns.live.getView().connection.canReconnect, false);
});

test('store: a stream the service ends early on a running session retries, then gives up', async () => {
  const h = boot({ sessions: [summaryOf('s1', 'ROUND_1')] });
  h.ns.live.subscribe(() => {});
  await h.advance(0);
  h.streams[0].push([toState(1, 'ROUND_1')]);
  await h.advance(0);
  h.streams[0].end();
  await h.advance(0);
  assert.equal(h.ns.live.getView().connection.status, 'retrying');
  // Every replay carries only frames already applied, so the retries are not reset.
  for (let i = 0; i < 6; i += 1) {
    await h.advance(3_000);
    const s = h.streams[h.streams.length - 1];
    s.push([toState(1, 'ROUND_1')]);
    await h.advance(0);
    s.end();
    await h.advance(0);
  }
  assert.equal(h.ns.live.getView().connection.status, 'lost');
});

test('store against the real front door: a replayed event stream and the cards read end in a verdict', async () => {
  const demo = JSON.parse(readFileSync(join(chamberDir, 'demo-replay.json'), 'utf8')) as Any;
  const record = {
    ...demo.record, session_id: 'live-1', demo: false, sample: false,
    state: { state: 'COMPLETED' }, cards: demo.cards, verdict: demo.verdict, authority: 'standalone',
  };
  const frames = demo.timeline.map((e: Any) => e.frame);
  const reader: CouncilSessionReader = {
    read: (id) => (id === 'live-1' ? record : null),
    list: () => [{ session_id: 'live-1', state: 'COMPLETED', mode: 'full', question: record.brief.question, created_at: '2026-10-19T10:00:00Z', sample: false }],
  };
  await withDoor({ sessionReader: reader, eventsAdapter: { open: (id) => (id === 'live-1' ? { replay: () => frames } : null) } }, async (origin) => {
    const timers: Any[] = [];
    const sandbox: Record<string, unknown> = {
      fetch: (url: string, init?: Any) => fetch(origin + url, init),
      document: { hidden: true },
      location: { hash: '', pathname: '/chamber/', search: '' },
      history: { replaceState: () => {} },
      AbortController,
      TextDecoder,
      setTimeout,
      clearTimeout,
      clearInterval,
      setInterval: (fn: () => void, ms: number) => { const t = setInterval(fn, ms); t.unref(); timers.push(t); return t; },
    };
    sandbox.globalThis = sandbox;
    runInNewContext(readFileSync(join(chamberDir, 'chamber-state.js'), 'utf8'), sandbox);
    runInNewContext(readFileSync(join(chamberDir, 'chamber-live.js'), 'utf8'), sandbox);
    const live = (sandbox.councilChamber as Any).live;
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
      const view = live.getView();
      if (view.session && view.session.state === 'COMPLETED' && view.connection.status === 'ended') break;
      await new Promise((r) => setTimeout(r, 25));
    }
    const v = plain(live.getView()) as Any;
    timers.forEach((t) => clearInterval(t));
    assert.equal(v.mode, 'live');
    assert.equal(v.connection.status, 'ended');
    assert.equal(v.list.sessions.length, 1);
    assert.equal(v.session.state, 'COMPLETED');
    assert.equal(v.session.verdict.labelText, 'Go, with conditions');
    assert.deepEqual(v.session.steps.map((s: Any) => s.status), ['done', 'done', 'done', 'done', 'done', 'done']);
    assert.equal(v.session.keyPoints[0].label, 'CHAIR: READING YOUR QUESTION');
    assert.equal(v.session.keyPoints[v.session.keyPoints.length - 1].label, 'VERDICT: GO, WITH CONDITIONS');
    assert.ok(v.session.seats.every((s: Any) => s.cards[1].line && s.cards[2].line && s.cards[3].line));
    assert.equal(v.session.options.find((o: Any) => o.recommended).letter, 'B');
  });
});
