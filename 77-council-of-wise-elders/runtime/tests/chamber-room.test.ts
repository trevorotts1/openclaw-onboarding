/**
 * Chamber unit C (room panel) tests.
 *
 * Runner:
 *   node --import tsx --test tests/chamber-room.test.ts
 *
 * Tier A only. chamber-room.js is loaded in node:vm twice: once with no
 * document (the pure helpers) and once against a tiny fake DOM, so the render
 * path (seats, bubbles, round panel, buttons, events) is exercised without a
 * browser. Real-browser geometry is proved separately with Playwright.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
const roomJs = readFileSync(join(chamberDir, 'chamber-room.js'), 'utf8');
const roomCss = readFileSync(join(chamberDir, 'chamber-room.css'), 'utf8');

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;

const SEATS: Record<string, { name: string; pill?: string; short: string; domain: string; weighing: string }> = {
  'simon-sinek': { name: 'Simon Sinek', short: 'Sinek', domain: 'purpose and strategic alignment', weighing: 'does this express why we exist?' },
  'td-jakes': { name: 'T. D. Jakes', short: 'Jakes', domain: 'instinct and reinvention', weighing: 'what is the client sensing?' },
  'oprah-winfrey': { name: 'Oprah Winfrey', short: 'Oprah', domain: 'intention and significance', weighing: 'what is the real intention?' },
  'tiffany-aliche': { name: 'Tiffany Aliche', short: 'Aliche', domain: 'financial stability', weighing: 'can this commitment be made safely?' },
  'russell-brunson': { name: 'Russell Brunson', short: 'Brunson', domain: 'offers and conversion', weighing: 'who wants this?' },
  'michelle-obama': { name: 'Michelle Obama', short: 'Obama', domain: 'grounded leadership', weighing: 'how do we move with integrity?' },
  'brene-brown': { name: 'Brené Brown', short: 'Brené Brown', domain: 'courage and trust', weighing: 'what hard conversation is avoided?' },
  'dennis-kimbro': { name: 'Dr. Dennis Kimbro', pill: 'Dennis Kimbro', short: 'Kimbro', domain: 'ownership and wealth', weighing: 'does this build ownership?' },
  'les-brown': { name: 'Les Brown', short: 'Les Brown', domain: 'self-belief and action', weighing: 'is the obstacle real?' },
};
const ORDER = Object.keys(SEATS);

function seatsApi(): Any {
  return {
    order: ORDER,
    get: (id: string) => (SEATS[id] ? { id, ...SEATS[id] } : { id, name: id, short: id, domain: '', weighing: '' }),
    portraitSources: (id: string) => [`portraits/${id}.webp`, `portraits/${id}.svg`],
  };
}

/* Pure helpers: no document in the context, so only the API half runs. */
function loadPure(): Any {
  const ctx: Any = {};
  ctx.globalThis = ctx;
  runInNewContext(roomJs, ctx);
  return ctx.councilChamber.room;
}

test('arcLayout(9) is a symmetric arch: centre highest, edges lowest and in front', () => {
  const room = loadPure();
  const pts = room.arcLayout(9, false);
  assert.equal(pts.length, 9);
  assert.equal(pts[0].xPct, 6);
  assert.equal(pts[8].xPct, 94);
  assert.equal(pts[4].xPct, 50);
  for (let i = 0; i < 9; i += 1) {
    assert.equal(pts[i].xPct + pts[8 - i].xPct, 100, `x mirrors at ${i}`);
    assert.equal(pts[i].yPct, pts[8 - i].yPct, `y mirrors at ${i}`);
    assert.equal(pts[i].z, pts[8 - i].z, `z mirrors at ${i}`);
  }
  const ys = pts.map((p: Any) => p.yPct);
  assert.equal(pts[4].yPct, Math.min(...ys), 'centre y is the minimum');
  assert.equal(pts[4].yPct, 0);
  assert.equal(pts[0].yPct, Math.max(...ys), 'edge y is the maximum');
  assert.equal(pts[0].yPct, 18, 'edge drop is 18 percent');
  const zs = pts.map((p: Any) => p.z);
  assert.equal(pts[0].z, Math.max(...zs), 'edges are in front');
  assert.equal(pts[0].z, 10);
  assert.equal(pts[4].z, 0);
  for (let i = 1; i < 9; i += 1) assert.ok(pts[i].xPct > pts[i - 1].xPct, 'x strictly increases');
  for (let i = 1; i <= 4; i += 1) assert.ok(pts[i].yPct < pts[i - 1].yPct, 'y falls toward the centre');
});

test('arcLayout(1) is centred and arcLayout(0) is empty', () => {
  const room = loadPure();
  assert.deepEqual(JSON.parse(JSON.stringify(room.arcLayout(1, false))), [{ xPct: 50, yPct: 0, z: 0 }]);
  assert.deepEqual(JSON.parse(JSON.stringify(room.arcLayout(1, true))), [{ xPct: 50, yPct: 0, z: 0 }]);
  assert.equal(room.arcLayout(0, false).length, 0);
});

test('arcLayout(9, compact) is two staggered rows: 5 back and 4 front, offset by half a step', () => {
  const room = loadPure();
  const pts = room.arcLayout(9, true);
  assert.equal(pts.length, 9);
  const back = pts.filter((p: Any) => p.yPct === 0);
  const front = pts.filter((p: Any) => p.yPct > 0);
  assert.equal(back.length, 5);
  assert.equal(front.length, 4);
  assert.deepEqual(Array.from(back, (p: Any) => p.xPct), [6, 28, 50, 72, 94]);
  assert.deepEqual(Array.from(front, (p: Any) => p.xPct), [17, 39, 61, 83]);
  // the front row drops 56 percent: room for a two-line full name above its bubbles (CSS --ch-room-drop matches)
  assert.ok(front.every((p: Any) => p.yPct === 56));
  // roster order: the first five seats fill the back row, the last four the front row
  assert.equal(JSON.stringify(pts.slice(0, 5)), JSON.stringify(back));
  assert.equal(JSON.stringify(pts.slice(5)), JSON.stringify(front));
  // the front row is drawn in front of the back row
  assert.ok(Math.min(...front.map((p: Any) => p.z)) > Math.max(...back.map((p: Any) => p.z)));
});

test('weighingParts: weighing uses the short name and the seat weighing text', () => {
  const room = loadPure();
  const seats = seatsApi();
  const w = { seatId: 'simon-sinek', kind: 'weighing', text: 'ignored when the seat has its own' };
  assert.deepEqual(JSON.parse(JSON.stringify(room.weighingParts(w, seats))), {
    name: 'Sinek',
    rest: ' is weighing: does this express why we exist?',
  });
});

test('weighingParts: said quotes the line with curly quotes', () => {
  const room = loadPure();
  const w = { seatId: 'td-jakes', kind: 'said', text: 'Pilot first.' };
  assert.deepEqual(JSON.parse(JSON.stringify(room.weighingParts(w, seatsApi()))), {
    name: 'Jakes',
    rest: ' said: “Pilot first.”',
  });
});

test('weighingParts: chair is "The chair" with the supplied text', () => {
  const room = loadPure();
  const w = { seatId: null, kind: 'chair', text: 'is the question clear?' };
  assert.deepEqual(JSON.parse(JSON.stringify(room.weighingParts(w, seatsApi()))), {
    name: 'The chair',
    rest: ' is weighing: is the question clear?',
  });
});

test('weighingParts accepts an array or a map of seats, and tolerates null', () => {
  const room = loadPure();
  const arr = ORDER.map((id) => ({ id, ...SEATS[id] }));
  const w = { seatId: 'les-brown', kind: 'weighing', text: '' };
  const expected = { name: 'Les Brown', rest: ' is weighing: is the obstacle real?' };
  assert.deepEqual(JSON.parse(JSON.stringify(room.weighingParts(w, arr))), expected);
  assert.deepEqual(JSON.parse(JSON.stringify(room.weighingParts(w, SEATS))), { name: 'Les Brown', rest: ' is weighing: is the obstacle real?' });
  assert.deepEqual(JSON.parse(JSON.stringify(room.weighingParts(null, arr))), { name: '', rest: '' });
});

test('seatLabel, progressModel and connectionNote', () => {
  const room = loadPure();
  const seat = SEATS['simon-sinek'];
  assert.equal(room.seatLabel(seat, 'writing'), 'Simon Sinek, purpose and strategic alignment. Writing now');
  assert.equal(room.seatLabel(seat, 'done'), 'Simon Sinek, purpose and strategic alignment. Position in');
  assert.equal(room.seatLabel(seat, 'idle'), 'Simon Sinek, purpose and strategic alignment. Has not spoken yet');
  assert.equal(room.seatLabel(seat, undefined), 'Simon Sinek, purpose and strategic alignment. Has not spoken yet');

  assert.deepEqual(JSON.parse(JSON.stringify(room.progressModel({ indeterminate: true, value: 0.5 }))), { indeterminate: true, pct: 0 });
  assert.deepEqual(JSON.parse(JSON.stringify(room.progressModel({ indeterminate: false, value: 4 / 9 }))), { indeterminate: false, pct: 44.4 });
  assert.deepEqual(JSON.parse(JSON.stringify(room.progressModel({ indeterminate: false, value: 1 }))), { indeterminate: false, pct: 100 });
  assert.equal(room.progressModel({ indeterminate: false, value: 250 }).pct, 100);
  assert.equal(room.progressModel({ indeterminate: false, value: -1 }).pct, 0);

  for (const status of ['retrying', 'lost', 'ended', 'unavailable']) {
    assert.deepEqual(JSON.parse(JSON.stringify(room.connectionNote({ status, text: 'x', canReconnect: status === 'lost' }))), {
      text: 'x',
      canReconnect: status === 'lost',
    });
  }
  for (const status of ['idle', 'connecting', 'live']) assert.equal(room.connectionNote({ status, text: 'x', canReconnect: false }), null);
  assert.equal(room.connectionNote(null), null);
});

/* ---- Fake DOM so the render path runs without a browser ---------------- */

class FakeNode {
  parentNode: FakeNode | null = null;
  childNodes: FakeNode[] = [];
  className = '';
  hidden = false;
  type = '';
  alt: string | null = null;
  draggable = true;
  decoding = '';
  src = '';
  nodeValue = '';
  attrs: Record<string, string> = {};
  style: Record<string, string> & { setProperty?: (k: string, v: string) => void } = {};
  listeners: Record<string, Array<(e: Any) => void>> = {};
  classes = new Set<string>();
  constructor(public tag: string) {
    const self = this;
    this.style.setProperty = (k: string, v: string) => {
      self.style[k] = v;
    };
  }
  get classList() {
    const self = this;
    return {
      add: (c: string) => self.classes.add(c),
      toggle: (c: string, on?: boolean) => {
        const want = on === undefined ? !self.classes.has(c) : on;
        if (want) self.classes.add(c);
        else self.classes.delete(c);
      },
      contains: (c: string) => self.classes.has(c) || self.className.split(/\s+/).includes(c),
    };
  }
  get firstChild() {
    return this.childNodes[0] ?? null;
  }
  appendChild(n: FakeNode) {
    n.parentNode = this;
    this.childNodes.push(n);
    return n;
  }
  removeChild(n: FakeNode) {
    this.childNodes = this.childNodes.filter((c) => c !== n);
    n.parentNode = null;
    return n;
  }
  get textContent(): string {
    if (this.tag === '#text') return this.nodeValue;
    return this.childNodes.map((c) => c.textContent).join('');
  }
  set textContent(v: string) {
    this.childNodes = [];
    if (v !== '') this.appendChild(makeText(v));
  }
  setAttribute(k: string, v: string) {
    this.attrs[k] = String(v);
  }
  getAttribute(k: string) {
    return k in this.attrs ? this.attrs[k] : null;
  }
  hasAttribute(k: string) {
    return k in this.attrs;
  }
  addEventListener(t: string, fn: (e: Any) => void) {
    (this.listeners[t] ||= []).push(fn);
  }
  fire(t: string, ev: Any = {}) {
    for (const fn of this.listeners[t] || []) fn(ev);
  }
  click() {
    this.fire('click', { target: this });
  }
  find(pred: (n: FakeNode) => boolean, out: FakeNode[] = []): FakeNode[] {
    if (pred(this)) out.push(this);
    for (const c of this.childNodes) c.find(pred, out);
    return out;
  }
  hasClass(c: string) {
    return this.classList.contains(c);
  }
}

function makeText(v: string): FakeNode {
  const t = new FakeNode('#text');
  t.nodeValue = v;
  return t;
}

interface Booted {
  ctx: Any;
  mount: FakeNode;
  events: Array<{ type: string; detail: Any }>;
  calls: string[];
  push: (view: Any) => void;
  q: (cls: string) => FakeNode[];
}

function boot(): Booted {
  const events: Array<{ type: string; detail: Any }> = [];
  const calls: string[] = [];
  const docListeners: Record<string, Array<(e: Any) => void>> = {};
  const mount = new FakeNode('section');
  let subscriber: ((v: Any) => void) | null = null;
  const doc: Any = {
    readyState: 'complete',
    getElementById: (id: string) => (id === 'ch-room' ? mount : null),
    createElement: (tag: string) => new FakeNode(tag),
    createTextNode: (v: string) => makeText(v),
    addEventListener: (t: string, fn: (e: Any) => void) => {
      (docListeners[t] ||= []).push(fn);
    },
    dispatchEvent: (e: Any) => {
      events.push({ type: e.type, detail: e.detail });
      for (const fn of docListeners[e.type] || []) fn(e);
      return true;
    },
  };
  class CustomEventStub {
    type: string;
    detail: Any;
    constructor(type: string, init: Any = {}) {
      this.type = type;
      this.detail = init.detail;
    }
  }
  const ctx: Any = {
    document: doc,
    CustomEvent: CustomEventStub,
    councilChamber: {
      seats: seatsApi(),
      live: {
        subscribe: (fn: (v: Any) => void) => {
          subscriber = fn;
          return () => undefined;
        },
        startDemo: () => calls.push('startDemo'),
        reconnect: () => calls.push('reconnect'),
      },
    },
  };
  ctx.globalThis = ctx;
  runInNewContext(roomJs, ctx);
  const b: Booted = {
    ctx,
    mount,
    events,
    calls,
    push: (view) => (subscriber as (v: Any) => void)(view),
    q: (cls) => mount.find((n) => n.hasClass(cls)),
  };
  return b;
}

function seatView(overrides: Record<string, Any> = {}): Any[] {
  return ORDER.map((id) => ({ id, status: 'writing', spotlight: false, bubble: { kind: 'typing', text: '' }, ...(overrides[id] || {}) }));
}

function liveView(session: Record<string, Any>, extra: Record<string, Any> = {}): Any {
  return {
    mode: 'live',
    connection: { status: 'live', text: '', canReconnect: false },
    session: {
      demo: false,
      status: 'running',
      seats: seatView(),
      round: {
        label: 'ROUND 1 OF 3',
        timer: '1:31',
        headline: 'The advisors are writing their opening positions.',
        explain: 'Each advisor writes an independent position on a route.',
        progress: { indeterminate: true, value: 0 },
        progressText: '0 of 9 positions in',
        weighing: { seatId: 'simon-sinek', kind: 'weighing', text: '' },
        complete: false,
      },
      ...session,
    },
    ...extra,
  };
}

test('mounts into section#ch-room and renders nine seat buttons from the roster before any session', () => {
  const b = boot();
  b.push({ mode: 'empty', connection: { status: 'idle', text: '', canReconnect: false }, session: null });
  const seats = b.q('ch-seat');
  assert.equal(seats.length, 9);
  for (const s of seats) {
    assert.equal(s.tag, 'button');
    assert.equal(s.type, 'button');
    assert.equal(s.getAttribute('aria-haspopup'), 'dialog');
    assert.match(s.getAttribute('aria-label') as string, /\. Has not spoken yet$/);
    const img = s.find((n) => n.tag === 'img')[0];
    assert.equal(img.alt, '', 'portrait is decorative');
    assert.equal(img.src, `portraits/${s.getAttribute('data-seat-id')}.webp`);
  }
  assert.equal(b.mount.hasClass('ch-room-panel'), true);
  assert.equal(b.q('ch-round-headline')[0].textContent, 'No council in session.');
  assert.equal(b.q('ch-round-explain')[0].textContent, 'Ask a new question to convene the nine advisors, or watch a demo replay.');
  assert.equal(b.q('ch-round-top')[0].hidden, true, 'no round row without a session');
  assert.equal(b.q('ch-round-track')[0].hidden, true);
  const visible = b.q('ch-round-btn').filter((n) => !n.hidden && !(n.parentNode as FakeNode).hidden).map((n) => n.textContent);
  assert.deepEqual(visible, ['New question', 'Watch a demo replay']);
});

test('empty-room buttons dispatch chamber:open-composer and start the demo', () => {
  const b = boot();
  b.push({ mode: 'empty', connection: { status: 'idle', text: '', canReconnect: false }, session: null });
  const btn = (t: string) => b.q('ch-round-btn').find((n) => n.textContent === t) as FakeNode;
  btn('New question').click();
  assert.equal(b.events.at(-1)?.type, 'chamber:open-composer');
  btn('Watch a demo replay').click();
  assert.deepEqual(b.calls, ['startDemo']);
});

test('round panel: label with dot, timer, headline, explainer and bold-name weighing line', () => {
  const b = boot();
  b.push(liveView({ seats: seatView({ 'simon-sinek': { spotlight: true } }) }));
  assert.equal(b.q('ch-round-label')[0].textContent, '● ROUND 1 OF 3');
  assert.equal(b.q('ch-round-timer')[0].textContent, '1:31');
  assert.equal(b.q('ch-round-timer')[0].getAttribute('aria-hidden'), 'true', 'the timer is not announced');
  assert.equal(b.q('ch-round-headline')[0].textContent, 'The advisors are writing their opening positions.');
  assert.equal(b.q('ch-round-explain')[0].textContent, 'Each advisor writes an independent position on a route.');
  const weighing = b.q('ch-round-weighing')[0];
  assert.equal(weighing.hidden, false);
  assert.equal(b.q('ch-round-name')[0].tag, 'b');
  assert.equal(b.q('ch-round-name')[0].textContent, 'Sinek');
  assert.equal(weighing.textContent, 'Sinek is weighing: does this express why we exist?');
  assert.equal(b.q('ch-round-top')[0].hidden, false);
});

test('only the spotlight seat is marked, and its name matches the weighing line', () => {
  const b = boot();
  b.push(liveView({ seats: seatView({ 'russell-brunson': { spotlight: true } }), round: { ...liveView({}).session.round, weighing: { seatId: 'russell-brunson', kind: 'weighing', text: '' } } }));
  const spot = b.q('ch-seat').filter((s) => s.hasClass('ch-seat--spot'));
  assert.equal(spot.length, 1);
  assert.equal(spot[0].getAttribute('data-seat-id'), 'russell-brunson');
  assert.ok(b.q('ch-round-weighing')[0].textContent.startsWith('Brunson is weighing'));
  // the spotlight moves: the previous seat loses the marker
  b.push(liveView({ seats: seatView({ 'les-brown': { spotlight: true } }) }));
  const after = b.q('ch-seat').filter((s) => s.hasClass('ch-seat--spot'));
  assert.deepEqual(after.map((s) => s.getAttribute('data-seat-id')), ['les-brown']);
});

test('aria-label follows seat status and bubbles follow bubble kind', () => {
  const b = boot();
  b.push(
    liveView({
      seats: seatView({
        'simon-sinek': { status: 'done', bubble: { kind: 'done', text: '' } },
        'td-jakes': { status: 'writing', bubble: { kind: 'line', text: 'Pilot first.' } },
        'les-brown': { status: 'idle', bubble: { kind: 'none', text: '' } },
      }),
    }),
  );
  const by = (id: string) => b.q('ch-seat').find((s) => s.getAttribute('data-seat-id') === id) as FakeNode;
  assert.equal(by('simon-sinek').getAttribute('aria-label'), 'Simon Sinek, purpose and strategic alignment. Position in');
  assert.equal(by('td-jakes').getAttribute('aria-label'), 'T. D. Jakes, instinct and reinvention. Writing now');
  assert.equal(by('les-brown').getAttribute('aria-label'), 'Les Brown, self-belief and action. Has not spoken yet');
  const bubble = (id: string) => by(id).find((n) => n.hasClass('ch-bubble'))[0];
  assert.equal(bubble('simon-sinek').getAttribute('data-kind'), 'done');
  assert.equal(bubble('td-jakes').getAttribute('data-kind'), 'line');
  assert.equal(by('td-jakes').find((n) => n.hasClass('ch-bubble-text'))[0].textContent, 'Pilot first.');
  assert.equal(by('td-jakes').hasClass('ch-seat--speaking'), true);
  assert.equal(bubble('les-brown').hidden, true, 'a seat with no bubble hides it');
  assert.equal(bubble('oprah-winfrey').getAttribute('data-kind'), 'typing');
  assert.equal(bubble('oprah-winfrey').hidden, false);
  assert.equal(bubble('oprah-winfrey').find((n) => n.hasClass('ch-bubble-dot')).length, 3, 'three typing dots');
});

test('progress bar: indeterminate slider first, then a determinate fill that reaches 100%', () => {
  const b = boot();
  const track = () => b.q('ch-round-track')[0];
  const fill = () => b.q('ch-round-fill')[0];
  const rnd = (progress: Any, extra: Any = {}) => ({ ...liveView({}).session.round, progress, ...extra });
  b.push(liveView({ round: rnd({ indeterminate: true, value: 0 }) }));
  assert.equal(track().getAttribute('data-mode'), 'indeterminate');
  assert.equal(fill().style.width ?? '', '');
  b.push(liveView({ round: rnd({ indeterminate: false, value: 3 / 9 }) }));
  assert.equal(track().getAttribute('data-mode'), 'determinate');
  assert.equal(fill().style.width, '33.3%');
  b.push(liveView({ round: rnd({ indeterminate: false, value: 1 }, { complete: true }) }));
  assert.equal(fill().style.width, '100%');
});

test('after a round is in, the weighing line says what the speaking seat said', () => {
  const b = boot();
  const round = { ...liveView({}).session.round, weighing: { seatId: 'oprah-winfrey', kind: 'said', text: 'Ask the people affected.' }, complete: true };
  b.push(liveView({ round, seats: seatView({ 'oprah-winfrey': { spotlight: true, bubble: { kind: 'line', text: 'Ask the people affected.' } } }) }));
  assert.equal(b.q('ch-round-weighing')[0].textContent, 'Oprah said: “Ask the people affected.”');
  const chair = { ...round, weighing: { seatId: null, kind: 'chair', text: 'is the draft ready?' } };
  b.push(liveView({ round: chair }));
  assert.equal(b.q('ch-round-weighing')[0].textContent, 'The chair is weighing: is the draft ready?');
});

test('the live region carries only headline and progress text', () => {
  const b = boot();
  b.push(liveView({ round: { ...liveView({}).session.round, progressText: '2 of 9 positions in' } }));
  const sr = b.q('ch-round-sr')[0];
  assert.equal(sr.getAttribute('aria-live'), 'polite');
  assert.equal(sr.textContent, 'The advisors are writing their opening positions. 2 of 9 positions in');
});

test('clicking a seat dispatches chamber:open-seat with the seat id and the button as opener', () => {
  const b = boot();
  b.push(liveView({}));
  const seat = b.q('ch-seat').find((s) => s.getAttribute('data-seat-id') === 'michelle-obama') as FakeNode;
  seat.click();
  const ev = b.events.at(-1) as { type: string; detail: Any };
  assert.equal(ev.type, 'chamber:open-seat');
  assert.equal(ev.detail.seatId, 'michelle-obama');
  assert.equal(ev.detail.opener, seat);
});

test('a missing webp falls back to the svg, and a missing svg hides the image', () => {
  const b = boot();
  b.push(liveView({}));
  const img = b.q('ch-seat').find((s) => s.getAttribute('data-seat-id') === 'oprah-winfrey')?.find((n) => n.tag === 'img')[0] as FakeNode;
  assert.equal(img.src, 'portraits/oprah-winfrey.webp');
  img.fire('error');
  assert.equal(img.src, 'portraits/oprah-winfrey.svg');
  assert.equal(img.hasClass('ch-seat-img--medallion'), true);
  assert.notEqual(img.style.visibility, 'hidden');
  img.fire('error');
  assert.equal(img.style.visibility, 'hidden', 'no broken-image icon is ever shown');
});

test('connection note and Reconnect appear only for retrying, lost, ended and unavailable', () => {
  const b = boot();
  const conn = () => b.q('ch-round-conn')[0];
  const reconnect = () => b.q('ch-round-conn')[0].find((n) => n.tag === 'button')[0];
  b.push(liveView({}));
  assert.equal(conn().hidden, true);
  b.push(liveView({}, { connection: { status: 'retrying', text: 'Reconnecting (2 of 5)...', canReconnect: false } }));
  assert.equal(conn().hidden, false);
  assert.equal(b.q('ch-round-conn-text')[0].textContent, 'Reconnecting (2 of 5)...');
  assert.equal(reconnect().hidden, true);
  b.push(liveView({}, { connection: { status: 'lost', text: 'Connection lost.', canReconnect: true } }));
  assert.equal(reconnect().hidden, false);
  reconnect().click();
  assert.deepEqual(b.calls, ['reconnect']);
  b.push(liveView({}, { connection: { status: 'live', text: '', canReconnect: false } }));
  assert.equal(conn().hidden, true);
});

test('Replay again shows only for a finished demo', () => {
  const b = boot();
  const replay = () => b.q('ch-round-btn').find((n) => n.textContent === 'Replay again') as FakeNode;
  const shown = () => !replay().hidden && !(replay().parentNode as FakeNode).hidden;
  b.push(liveView({ demo: true, status: 'running' }, { mode: 'demo' }));
  assert.equal(shown(), false);
  b.push(liveView({ demo: false, status: 'complete' }));
  assert.equal(shown(), false, 'a finished real session has no replay button');
  b.push(liveView({ demo: true, status: 'complete' }, { mode: 'demo' }));
  assert.equal(shown(), true);
  replay().click();
  assert.deepEqual(b.calls, ['startDemo']);
});

test('re-rendering keeps the same seat nodes (focus and hover survive updates)', () => {
  const b = boot();
  b.push(liveView({}));
  const first = b.q('ch-seat');
  b.push(liveView({ seats: seatView({ 'les-brown': { spotlight: true } }) }));
  const second = b.q('ch-seat');
  assert.equal(second.length, 9);
  first.forEach((n, i) => assert.equal(n, second[i]));
});

/* ---- Source guards ----------------------------------------------------- */

test('chamber-room.js uses textContent only and carries no URL', () => {
  assert.doesNotMatch(roomJs, /innerHTML|outerHTML|insertAdjacentHTML|document\.write/);
  assert.doesNotMatch(roomJs, /https?:\/\//);
});

test('chamber-room.css takes every colour from var(--ch-*): no raw colour literals', () => {
  const css = roomCss.replace(/\/\*[\s\S]*?\*\//g, '');
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,8}\b/, 'hex colour');
  assert.doesNotMatch(css, /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/i, 'colour function');
  const named = /\b(?:white|black|red|green|blue|navy|gray|grey|silver|gold|yellow|orange|purple|pink|brown|cyan|magenta|teal|maroon|olive|lime|aqua|fuchsia|ivory|beige|tan)\b/i;
  const decls = css.split(/[;{}]/).filter((d) => /^\s*(?:background|color|border|outline|box-shadow|fill|stroke|-webkit-mask|mask)[\w-]*\s*:/.test(d));
  for (const d of decls) assert.doesNotMatch(d.replace(/var\(--[a-z0-9-]+\)/g, ''), named, `named colour in: ${d.trim()}`);
  assert.match(css, /var\(--ch-gold\)/);
  assert.match(css, /var\(--ch-surface-2\)/);
});

test('chamber-room.css honours the layout contract and prefers-reduced-motion', () => {
  assert.match(roomCss, /clamp\(96px, 10\.5vw, 150px\)/, 'bust width at >=600px');
  assert.match(roomCss, /--ch-room-w: 76px/, 'bust width on phone');
  assert.match(roomCss, /max-width: 599\.98px/, 'phone breakpoint');
  assert.match(roomCss, /--ch-room-drop: 0\.56;/, 'phone front-row drop matches COMPACT_DROP (56)');
  assert.match(roomCss, /max-width: 660px/, 'round panel width');
  assert.match(roomCss, /blackceo-logo\.png/, 'watermark mask');
  assert.match(roomCss, /opacity: 0\.05/, 'watermark opacity is at most 6 percent');
  assert.match(roomCss, /border-radius: 50% 50% 0 0 \/ var\(--ch-room-dome\)/, 'dome table');
  const reduced = roomCss.slice(roomCss.indexOf('@media (prefers-reduced-motion: reduce)'));
  assert.match(reduced, /\.ch-bubble-dot[\s\S]*animation: none/);
  assert.match(reduced, /ch-round-fill[\s\S]*animation: none/);
  // every class the script and stylesheet own stays inside the unit prefixes
  const classes = new Set([...roomCss.matchAll(/\.(ch-[a-z0-9-]+)/g)].map((m) => m[1]));
  for (const c of classes) assert.match(c, /^ch-(?:room|seat|bubble|table|round)-?/, `class ${c} is outside the C prefixes`);
});

/* ---- Framing against the real F portraits (W29 fix round 1) ------------- */

const cssNoComments = roomCss.replace(/\/\*[\s\S]*?\*\//g, '');

test('the dome cuts below the chin: cover is 15 percent of the bust height or less', () => {
  // F's webps are head crops: the chin sits at 65 to 75 percent of the height.
  const m = cssNoComments.match(/--ch-room-cover:\s*calc\(var\(--ch-room-bust-h\)\s*\*\s*([0-9.]+)\)/);
  assert.ok(m, 'desktop cover is a share of the bust height');
  assert.ok(Number(m[1]) <= 0.15, `cover ${m[1]} would hide chins`);
  const pillTop = cssNoComments.match(/--ch-room-pill-top:\s*([0-9.]+)/);
  assert.ok(pillTop && Number(pillTop[1]) >= 0.76, 'the pill hangs from the collar, below the chin');
  assert.match(cssNoComments, /\.ch-seat-pillslot\s*\{[^}]*top:\s*calc\(var\(--ch-room-bubble\)[^}]*var\(--ch-room-pill-top\)/, 'pill is top-anchored so it grows downward');
  assert.doesNotMatch(cssNoComments, /\.ch-seat-pillslot\s*\{[^}]*bottom:/, 'a bottom-anchored pill climbs over the face');
});

test('the phone round card cuts at the collar, not at the nose', () => {
  const phone = cssNoComments.slice(cssNoComments.indexOf('max-width: 599.98px'));
  assert.match(phone, /\.ch-table\s*\{[^}]*margin-top:\s*calc\(var\(--ch-room-cover\)\s*\*\s*-1\)/);
  assert.doesNotMatch(phone, /bust-h\)\s*\*\s*-0\.3/);
});

test('pills are one line on the arc, shrink with the seat gap, and wrap inside their border on the phone', () => {
  const pill = cssNoComments.match(/\n\.ch-seat-pill\s*\{([^}]*)\}/);
  assert.ok(pill, 'base pill rule');
  assert.match(pill[1], /white-space:\s*nowrap/);
  assert.match(pill[1], /font-size:\s*clamp\(9px/, 'type shrinks with the seat gap');
  assert.doesNotMatch(pill[1], /max-width/, 'no max-width squeezing the arc pills to two lines');
  const phone = cssNoComments.slice(cssNoComments.indexOf('max-width: 599.98px'));
  assert.match(phone, /\.ch-seat-pill\s*\{[^}]*white-space:\s*normal[^}]*overflow-wrap:\s*anywhere[^}]*max-width:\s*calc\(var\(--ch-room-step\) - 4px\)/);
  assert.match(phone, /\.ch-seat\s*\{[^}]*--ch-room-step:\s*calc\(\(100cqw - var\(--ch-room-w\)\) \* 0\.22\)/);
});

test('the pill shows the full name (pill text where given, else the seat name)', () => {
  const b = boot();
  b.push(liveView({}));
  const pills = b.q('ch-seat-pill');
  assert.equal(pills.length, 9);
  const labels = pills.map((p) => p.textContent);
  assert.deepEqual(labels, ORDER.map((id) => SEATS[id].pill || SEATS[id].name));
  assert.deepEqual(labels, ['Simon Sinek', 'T. D. Jakes', 'Oprah Winfrey', 'Tiffany Aliche', 'Russell Brunson', 'Michelle Obama', 'Brené Brown', 'Dennis Kimbro', 'Les Brown']);
});

/* ---- Click targets (W29 fix round 2): a face or pill opens ITS seat ------- */

test('silhouette turns the alpha channel into a polygon that leaves transparent sides out', () => {
  const room = loadPure();
  // 10 x 4 image: only columns 3..6 are opaque on every row.
  const w = 10;
  const h = 4;
  const rgba = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y += 1) for (let x = 3; x <= 6; x += 1) rgba[(y * w + x) * 4 + 3] = 255;
  const poly: string = room.silhouette(rgba, w, h);
  assert.match(poly, /^polygon\(/);
  const xs = [...poly.matchAll(/([0-9.]+)% [0-9.]+%/g)].map((m) => Number(m[1]));
  assert.equal(Math.min(...xs), 30, 'left edge is the first opaque column');
  assert.equal(Math.max(...xs), 70, 'right edge is just past the last opaque column');
  assert.equal(room.silhouette(new Uint8Array(w * h * 4), w, h), null, 'fully transparent has no shape');
});

test('the 150px seat box never takes the pointer: only bust, pill and bubble do', () => {
  assert.match(cssNoComments, /\.ch-seat\s*\{[^}]*pointer-events:\s*none/, 'the button box is click-through');
  assert.match(cssNoComments, /\.ch-seat-bust\s*\{[^}]*pointer-events:\s*auto[^}]*clip-path:\s*inset\(/, 'the bust is clickable, cut to a column until the alpha shape is known');
  assert.match(cssNoComments, /\n\.ch-seat-pill\s*\{[^}]*pointer-events:\s*auto/);
  assert.match(cssNoComments, /\n\.ch-bubble\s*\{[^}]*pointer-events:\s*auto/);
  // The slots are full seat width and sit over neighbours: they must inherit none.
  assert.doesNotMatch(cssNoComments, /\.ch-seat-(pill|bubble)slot\s*\{[^}]*pointer-events:\s*auto/);
});

test('a loaded portrait gets a clip-path from its alpha; the svg medallion keeps the stylesheet column', () => {
  const b = boot();
  const doc = b.ctx.document;
  const make = doc.createElement;
  doc.createElement = (tag: string) => {
    if (tag !== 'canvas') return make(tag);
    return {
      width: 0,
      height: 0,
      getContext: () => ({
        clearRect: () => undefined,
        drawImage: () => undefined,
        getImageData: (_x: number, _y: number, w: number, h: number) => {
          const data = new Uint8Array(w * h * 4);
          for (let y = 0; y < h; y += 1) for (let x = 60; x < 100; x += 1) data[(y * w + x) * 4 + 3] = 255;
          return { data };
        },
      }),
    };
  };
  b.push(liveView({}));
  const seat = b.q('ch-seat').find((s) => s.getAttribute('data-seat-id') === 'oprah-winfrey') as FakeNode;
  const img = seat.find((n) => n.tag === 'img')[0] as FakeNode;
  const bust = seat.find((n) => n.hasClass('ch-seat-bust'))[0] as FakeNode;
  img.fire('load');
  assert.match(String(bust.style.clipPath), /^polygon\(/, 'webp load shapes the click target');
  img.fire('error');
  assert.equal(bust.style.clipPath, '', 'svg fallback goes back to the stylesheet column');
  img.fire('load');
  assert.equal(bust.style.clipPath, '', 'the medallion is never shaped from its alpha');
});
