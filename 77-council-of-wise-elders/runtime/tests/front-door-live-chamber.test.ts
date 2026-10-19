/**
 * W27 live chamber tests.
 *
 * Runner:
 *   node --import tsx --test tests/front-door-live-chamber.test.ts
 *
 * Tier A only: loopback HTTP on ephemeral ports and injected test data.
 * Proves the read-only session list route, that the served chamber carries
 * its script, and that the fictional fixture is never presented as live.
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

test('fixture content lives only inside the hidden, labelled sample container', () => {
  const html = readFileSync(join(chamberDir, 'index.html'), 'utf8');
  const sampleStart = html.indexOf('id="sample-root"');
  assert.ok(sampleStart > 0);
  const tag = html.slice(html.lastIndexOf('<', sampleStart), html.indexOf('>', sampleStart));
  assert.match(tag, /\shidden(\s|$)/, 'sample is hidden by default');
  assert.match(tag, /Fictional sample, not real data/);

  const live = html.slice(0, sampleStart);
  for (const fixtureText of [
    'Pilot the revised coaching offer',
    'Simon Sinek',
    'Round 2 of 3',
    '6 of 9 perspectives',
    'data-seat-id=',
  ]) {
    assert.equal(live.includes(fixtureText), false, `"${fixtureText}" must not precede the sample container`);
    assert.ok(html.includes(fixtureText), `"${fixtureText}" is still in the labelled sample`);
  }

  // The live region and honest empty state exist, the sample toggle starts hidden.
  assert.match(html, /id="live-root"/);
  assert.match(html, /No council sessions yet\./);
  assert.match(html, /id="sample-toggle"[^>]*\shidden/);
  assert.equal(/<script[^>]+src="https?:/.test(html), false);
});

test('live script never renders fixture seats and keeps live and sample exclusive', () => {
  const script = readFileSync(join(chamberDir, 'chamber-live.js'), 'utf8');
  assert.equal(script.includes('Pilot the revised'), false);
  assert.equal(script.includes('Fictional sample'), false);
  assert.match(script, /show\(liveRoot, !on\)/);
  assert.match(script, /show\(els\.sampleRoot, on\)/);
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
  newModel(seatIds: string[], state?: string): {
    order: string[];
    seats: Record<string, string[]>;
    events: Frame[];
    maxSeq: number;
    state: string | null;
  };
  applyFrame(model: ReturnType<Live['newModel']>, frame: Frame): boolean;
  describeFrame(frame: Frame): string;
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

test('helpers: frames update state and seats; duplicates and replays are ignored', () => {
  const live = loadHelpers();
  const model = live.newModel(['simon-sinek', 'les-brown'], 'READY');
  assert.equal(
    live.applyFrame(model, { sequence: 1, type: 'session_state_changed', to_state: 'ROUND_1' }),
    true,
  );
  assert.equal(model.state, 'ROUND_1');
  assert.equal(
    live.applyFrame(model, {
      sequence: 2,
      type: 'card_accepted',
      payload: { seat_id: 'simon-sinek', round: 'opening' },
    }),
    true,
  );
  assert.deepEqual(plain(model.seats['simon-sinek']), ['opening']);
  assert.deepEqual(plain(model.seats['les-brown']), [], 'a seat with no card stays empty, never invented');
  assert.equal(live.applyFrame(model, { sequence: 2, type: 'card_accepted' }), false, 'duplicate');
  assert.equal(live.applyFrame(model, { sequence: 1, type: 'session_created' }), false, 'replay');
  assert.equal(model.events.length, 2);
  assert.match(live.describeFrame(model.events[1]), /card accepted - Simon Sinek, round opening/);
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

test('only an explicit load announces "Loading"; the timer refresh stays silent', () => {
  const script = readFileSync(join(chamberDir, 'chamber-live.js'), 'utf8');
  assert.match(script, /if \(announce\) setText\(els\.status, 'Loading council sessions\.\.\.'\)/);
  assert.match(script, /loadList\(false\)/);
  assert.match(script, /els\.refresh\.addEventListener\('click', function \(\) \{ loadList\(true\); \}\)/);
  assert.equal(/els\.status\.textContent\s*=/.test(script), false);
  assert.equal(/clear\(els\.list\)/.test(script), false);
});
