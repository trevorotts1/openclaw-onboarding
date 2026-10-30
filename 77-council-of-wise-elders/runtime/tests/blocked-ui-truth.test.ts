/**
 * CTR-139 regression (UNEXECUTED here; Trevor owns the test run).
 *
 * A BLOCKED sitting must say what actually happened: a validator rejection
 * is not "has not answered", a genuinely unanswered provider call keeps that
 * wording, and a raw schema message is available only inside the native
 * disclosure as escaped text.
 *
 * Runner:
 *   node --import tsx --test tests/blocked-ui-truth.test.ts
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;

const SEATS = [
  'simon-sinek', 'td-jakes', 'oprah-winfrey', 'tiffany-aliche', 'russell-brunson',
  'michelle-obama', 'brene-brown', 'dennis-kimbro', 'les-brown',
];

function loadState(): Any {
  const sandbox: Record<string, unknown> = {};
  sandbox.globalThis = sandbox;
  for (const file of ['chamber-seats.js', 'chamber-state.js']) {
    runInNewContext(readFileSync(join(chamberDir, file), 'utf8'), sandbox);
  }
  return (sandbox.councilChamber as Any).state;
}

function record(blockedReason: Any): Any {
  return {
    session_id: 'sess-blocked-ui',
    spec: { mode: 'full', seat_ids: SEATS, model_policy: { route_id: 'claude-nine-configured' } },
    brief: { question: 'Should we launch?', options: [{ id: 'A', label: 'Launch', kind: 'change' }] },
    state: { state: 'BLOCKED', updated_at: '2026-10-30T09:00:00.000Z' },
    cards: [
      ...SEATS.filter((s) => s !== 'td-jakes' && s !== 'brene-brown')
        .map((seat_id) => ({ card_kind: 'advisor', round: 1, seat_id, preferred_option_id: 'A' })),
    ],
    blocked_reason: blockedReason,
  };
}

const plain = (value: Any): Any => JSON.parse(JSON.stringify(value));

// ------------------------------------------------------------------- DOM

class FakeNode {
  tag: string;
  childNodes: FakeNode[] = [];
  parentNode: FakeNode | null = null;
  attrs: Record<string, string> = {};
  classes = new Set<string>();
  className = '';
  hidden = false;
  id = '';
  nodeValue = '';
  style: Any = { setProperty(name: string, value: string) { this[name] = value; } };
  listeners: Record<string, Array<(e: Any) => void>> = {};
  constructor(tag: string) { this.tag = tag; }
  get firstChild(): FakeNode | null { return this.childNodes[0] ?? null; }
  appendChild(n: FakeNode): FakeNode { n.parentNode = this; this.childNodes.push(n); return n; }
  removeChild(n: FakeNode): FakeNode {
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
    if (v !== '') this.appendChild(Object.assign(new FakeNode('#text'), { nodeValue: v }));
  }
  setAttribute(k: string, v: string) { this.attrs[k] = String(v); }
  getAttribute(k: string) { return k in this.attrs ? this.attrs[k] : null; }
  addEventListener(t: string, fn: (e: Any) => void) { (this.listeners[t] ||= []).push(fn); }
  get classList() {
    const self = this;
    return {
      add: (c: string) => { self.classes.add(c); self.className = [...self.classes].join(' '); },
      toggle: (c: string, on?: boolean) => {
        const want = on === undefined ? !self.classes.has(c) : on;
        if (want) self.classes.add(c); else self.classes.delete(c);
        self.className = [...self.classes].join(' ');
      },
      contains: (c: string) => self.classes.has(c),
    };
  }
  hasClass(c: string) { return this.classes.has(c) || this.className.split(/\s+/).includes(c); }
  find(pred: (n: FakeNode) => boolean, out: FakeNode[] = []): FakeNode[] {
    if (pred(this)) out.push(this);
    for (const c of this.childNodes) c.find(pred, out);
    return out;
  }
}

function loadRoom(): { mount: FakeNode; push: (view: Any) => void } {
  const mount = new FakeNode('section');
  let subscriber: ((v: Any) => void) | null = null;
  const doc: Any = {
    readyState: 'complete',
    getElementById: (id: string) => (id === 'ch-room' ? mount : null),
    createElement: (tag: string) => new FakeNode(tag),
    createTextNode: (v: string) => Object.assign(new FakeNode('#text'), { nodeValue: v }),
    addEventListener: () => undefined,
    dispatchEvent: () => true,
  };
  const ctx: Any = {
    document: doc,
    CustomEvent: class { readonly type: string; readonly detail: Any; constructor(t: string, i: Any = {}) { this.type = t; this.detail = i.detail; } },
    councilChamber: {
      live: {
        subscribe: (fn: (v: Any) => void) => { subscriber = fn; return () => undefined; },
        startDemo: () => undefined,
        reconnect: () => undefined,
      },
    },
  };
  // Seat data comes from the real roster file, loaded the same way the page does.
  const seatsSandbox: Record<string, unknown> = {};
  seatsSandbox.globalThis = seatsSandbox;
  runInNewContext(readFileSync(join(chamberDir, 'chamber-seats.js'), 'utf8'), seatsSandbox);
  ctx.councilChamber.seats = (seatsSandbox.councilChamber as Any).seats;
  ctx.globalThis = ctx;
  runInNewContext(readFileSync(join(chamberDir, 'chamber-room.js'), 'utf8'), ctx);
  return { mount, push: (view) => (subscriber as (v: Any) => void)(view) };
}

// ------------------------------------------------------------------ test

test('blocked UI: rejection, pending and escaped technical detail stay distinct', () => {
  const S = loadState();
  const raw = '<script>alert("x")</script> lenses_used must be a string array; due_at must be UTC';
  const rejected = {
    code: 'FULL_MODE_SEATS_MISSING',
    detail: 'Full mode needs all nine seats; no accepted card in round 1 (opening positions) from: td-jakes, brene-brown.',
    missing_seats: ['td-jakes', 'brene-brown'],
    missing_round: 1,
    last_errors: [
      { seat_id: 'td-jakes', outcome_code: 'output_validation_failed', message: raw },
      { seat_id: 'brene-brown', outcome_code: 'output_validation_failed', message: 'answer failed validation twice' },
    ],
    unfinished_calls: [],
  };
  const pending = {
    code: 'FULL_MODE_SEATS_MISSING',
    detail: 'Full mode needs all nine seats; no accepted card in round 1 (opening positions) from: les-brown.',
    missing_seats: ['les-brown'],
    missing_round: 1,
    last_errors: [{ seat_id: 'les-brown', outcome_code: 'completion_unknown', message: 'The provider call ended with no result recorded about 10 minutes after it started.' }],
    unfinished_calls: [{ operation_id: 'op-1', outcome: 'completion_unknown', minutes: 10 }],
  };

  const rv = plain(S.view(S.create(record(rejected)), Date.parse('2026-10-30T09:10:00.000Z')));
  assert.match(rv.round.explain, /responses from T\. D\. Jakes and Brené Brown failed validation/);
  assert.doesNotMatch(rv.round.explain, /not answered/i, 'a rejected output is never called unanswered');
  assert.equal(rv.seats.find((s: Any) => s.id === 'td-jakes').blockedKind, 'rejected');
  assert.doesNotMatch(rv.round.explain, /<script>|lenses_used/, 'raw schema text is not the summary');
  assert.ok(rv.round.blockedDetails.some((d: Any) => d.text === raw), 'the exact validation text is retained');

  const pv = plain(S.view(S.create(record(pending)), Date.parse('2026-10-30T09:10:00.000Z')));
  assert.match(pv.round.explain, /Les Brown has not answered/);
  assert.match(pv.round.explain, /no result recorded about 10 minutes/);
  assert.doesNotMatch(pv.round.explain, /failed validation/i);
  assert.equal(pv.seats.find((s: Any) => s.id === 'les-brown').blockedKind, 'no_result');

  const room = loadRoom();
  room.push({ mode: 'live', connection: { status: 'live', text: '', canReconnect: false }, session: rv });
  const seat = room.mount.find((n) => n.getAttribute('data-seat-id') === 'td-jakes')[0];
  assert.match(seat.getAttribute('aria-label') as string, /Response failed validation/);
  assert.doesNotMatch(seat.getAttribute('aria-label') as string, /has not spoken/i);
  const tech = room.mount.find((n) => n.hasClass('ch-round-tech'))[0];
  assert.equal(tech.tag, 'details');
  assert.equal(tech.hidden, false);
  assert.match(tech.textContent, /<script>alert\("x"\)<\/script>/, 'technical text is carried as data');
  assert.equal(room.mount.find((n) => n.tag === 'script').length, 0, 'no markup is created from it');
});
