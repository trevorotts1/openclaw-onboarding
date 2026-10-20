/**
 * Verdict "Why" and real Key Points, driven by the first real live council
 * (sess-bbc7dddb..., verdict WAIT, option B, 27 cards), saved read-only as
 * tests/fixtures/chamber/live-wait-session.json.
 *
 * Runner:
 *   node --import tsx --test tests/chamber-verdict-keypoints.test.ts
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const chamberDir = join(here, '..', 'public', 'chamber');

/* eslint-disable @typescript-eslint/no-explicit-any */
type Any = any;

const fixtureText = readFileSync(join(here, 'fixtures', 'chamber', 'live-wait-session.json'), 'utf8');
const fx: Any = JSON.parse(fixtureText);

function plain<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function load(files: string[], extra: Record<string, unknown> = {}): Any {
  const sandbox: Record<string, unknown> = { ...extra };
  sandbox.globalThis = sandbox;
  for (const f of files) runInNewContext(readFileSync(join(chamberDir, f), 'utf8'), sandbox);
  return sandbox.councilChamber;
}

function sessionView(): Any {
  const ns = load(['chamber-seats.js', 'chamber-state.js']);
  const m = ns.state.create(fx.readback.session);
  for (const frame of fx.events) ns.state.apply(m, frame);
  ns.state.applyRecord(m, fx.readback.session);
  return plain(ns.state.view(m, Date.parse('2026-10-20T00:30:00Z')));
}

const BANNED = /budget|allowance|spend limit|approval|approve/i;

test('fixture holds the real session and no keys, tokens or home paths', () => {
  assert.equal(fx.readback.session.state.state, 'COMPLETED');
  assert.equal(fx.readback.session.cards.length, 27);
  assert.equal(fx.readback.session.verdict.label, 'WAIT');
  assert.doesNotMatch(fixtureText, /\/Users\/|\/home\/|sk-[A-Za-z0-9]{8,}|Bearer |BEGIN [A-Z ]*PRIVATE/);
  assert.doesNotMatch(fixtureText, /"[a-zA-Z_]*(api_?key|token|secret|password)[a-zA-Z_]*"\s*:\s*"[^"]/i);
});

test('the verdict says why: what must happen first, the evidence in words, and the caution', () => {
  const why = sessionView().verdict.why;
  assert.match(why.headline, /^Wait\. The elders lean toward Option B: Pilot the revised offer/);
  assert.equal(why.stepsHeading, 'What has to happen first');
  assert.equal(why.steps.length, 4);
  assert.match(why.steps[0], /^Finance must confirm/);
  assert.equal(why.moreSteps, 1);
  assert.match(why.evidence, /^Low\. /);
  assert.equal(why.support, 'All 9 elders back it, each with conditions.');
  // Nobody voted against it, so the verdict has no dissent; the sharpest caution is credited by name.
  assert.equal(why.dissent.lead, 'Sharpest caution');
  assert.equal(why.dissent.by, 'Simon Sinek');
});

test('our own wording in the Why never mentions budget, allowance, spend limit or approval', () => {
  const why = sessionView().verdict.why;
  for (const own of [why.headline, why.stepsHeading, why.evidence, why.support, why.dissent.lead]) assert.doesNotMatch(own, BANNED);
});

test('a real strongest dissent is credited to the elder who wrote it', () => {
  const ns = load(['chamber-seats.js', 'chamber-state.js']);
  const rec = plain(fx.readback.session);
  const obj = rec.cards.find((c: Any) => c.round === 2 && c.seat_id === 'td-jakes').strongest_objection;
  rec.verdict.strongest_dissent = obj;
  const m = ns.state.create(rec);
  const why = plain(ns.state.view(m, 0).verdict.why);
  assert.deepEqual(why.dissent, { lead: 'Strongest dissent', text: obj, by: 'T. D. Jakes' });
});

test('no verdict, no Why; a consult answer has none either', () => {
  const ns = load(['chamber-seats.js', 'chamber-state.js']);
  const rec = plain(fx.readback.session);
  delete rec.verdict;
  assert.equal(ns.state.view(ns.state.create(rec), 0).verdict, null);
  const consult = plain(fx.readback.session);
  consult.verdict = { result_kind: 'consult' };
  assert.equal(ns.state.view(ns.state.create(consult), 0).verdict.why, null);
});

test('Key Points carry the real content, each line credited to an elder by full name', () => {
  const kp = sessionView().keyPoints;
  const by = (label: string) => kp.find((k: Any) => k.label === label);
  const r1 = by('ROUND 1: ALL 9 POSITIONS IN');
  assert.equal(r1.items.length, 9);
  assert.deepEqual(r1.items.map((i: Any) => i.by), [
    'Simon Sinek', 'T. D. Jakes', 'Oprah Winfrey', 'Tiffany Aliche', 'Russell Brunson',
    'Michelle Obama', 'Brené Brown', 'Dr. Dennis Kimbro', 'Les Brown',
  ]);
  assert.ok(r1.items.every((i: Any) => i.tag === 'Argument' && i.text.length > 20));

  const faults = by('CHAIR: FINDING THE FAULT LINES');
  assert.equal(faults.items.length, 2);
  assert.match(faults.items[0].text, /^Fault line 1 remains a blocking/);
  assert.equal(faults.items[0].by, 'The chair');

  const r2 = by('ROUND 2: ALL 9 POSITIONS IN');
  assert.equal(r2.items.length, 9);
  assert.ok(r2.items.every((i: Any) => i.tag === 'Concern'));

  const draft = by('CHAIR: DRAFTING THE RESOLUTION');
  assert.equal(draft.items.length, 5);
  assert.ok(draft.items.every((i: Any) => i.tag === 'Condition' && /\S/.test(i.by)));
  assert.equal(draft.items[0].by, 'Simon Sinek');

  const r3 = by('ROUND 3: ALL 9 POSITIONS IN');
  assert.equal(r3.detail, 'All 9 elders back it, each with conditions.');
  assert.deepEqual(r3.items.map((i: Any) => i.by), ['Tiffany Aliche', 'Michelle Obama', 'Dr. Dennis Kimbro', 'Dr. Dennis Kimbro']);

  const verdict = by('VERDICT: WAIT');
  assert.deepEqual(verdict.items.map((i: Any) => [i.tag, i.by]), [['Dissent', 'Simon Sinek'], ['Dissent', 'Brené Brown'], ['Dissent', 'Les Brown']]);
});

test('every long line has its full text behind a short summary; phase headings stay as labels', () => {
  const kp = sessionView().keyPoints;
  assert.equal(kp.length, 11);
  for (const k of kp) for (const i of k.items) {
    assert.ok(i.text.length <= 221 || i.text.endsWith('…') || i.full);
    if (i.full) assert.ok(i.full.length > i.text.length);
  }
  const heads = kp.filter((k: Any) => k.items.length === 0).map((k: Any) => k.label);
  assert.ok(heads.includes('CHAIR: READING YOUR QUESTION'));
});

test('before the cards arrive a heading has no lines instead of invented ones', () => {
  const ns = load(['chamber-seats.js', 'chamber-state.js']);
  const m = ns.state.create({ session_id: 'x', spec: fx.readback.session.spec, brief: fx.readback.session.brief });
  for (const frame of fx.events.slice(0, 60)) ns.state.apply(m, frame);
  const kp = plain(ns.state.view(m, 0).keyPoints);
  assert.ok(kp.length > 0);
  assert.ok(kp.every((k: Any) => k.items.length === 0));
});

// ------------------------------------------------------------ renderers

class FakeNode {
  children: FakeNode[] = [];
  parent: FakeNode | null = null;
  attrs: Record<string, string> = {};
  classes = new Set<string>();
  className = '';
  textContent = '';
  hidden = false;
  id = '';
  type = '';
  style: Record<string, string> = {};
  listeners: Record<string, () => void> = {};
  constructor(readonly tag: string) {}
  get firstChild(): FakeNode | null { return this.children[0] ?? null; }
  appendChild(c: FakeNode): FakeNode { c.parent?.removeChild(c); c.parent = this; this.children.push(c); return c; }
  removeChild(c: FakeNode): FakeNode { this.children.splice(this.children.indexOf(c), 1); c.parent = null; return c; }
  setAttribute(n: string, v: string): void { this.attrs[n] = v; }
  getAttribute(n: string): string | undefined { return this.attrs[n]; }
  addEventListener(n: string, f: () => void): void { this.listeners[n] = f; }
  contains(): boolean { return false; }
  get classList(): { add(n: string): void; toggle(n: string, on: boolean): void } {
    return { add: (n) => void this.classes.add(n), toggle: (n, on) => void (on ? this.classes.add(n) : this.classes.delete(n)) };
  }
}

function all(n: FakeNode): FakeNode[] { return [n, ...n.children.flatMap(all)]; }
const words = (n: FakeNode) => all(n).map((x) => x.textContent).join(' ');

test('Key Points panel draws the lines, expands a long one, and keeps row nodes on update', () => {
  const aside = new FakeNode('aside');
  let push: (v: unknown) => void = () => undefined;
  const sandbox = {
    document: { getElementById: (id: string) => (id === 'ch-keypoints' ? aside : null), createElement: (t: string) => new FakeNode(t) },
    councilChamber: { live: { subscribe: (f: (v: unknown) => void) => { push = f; f({ session: null }); } } },
  };
  load(['chamber-keypoints.js'], sandbox as Record<string, unknown>);
  const sv = sessionView();
  push({ session: sv });
  const text = words(aside);
  assert.match(text, /Simon Sinek/);
  assert.match(text, /Fault line 1 remains/);
  assert.equal(aside.attrs.tabindex, '0');
  const rowsBefore = aside.children[1].children.slice();
  const more = all(aside).find((n) => n.className === 'ch-kp-more')!;
  const body = more.parent!.children.find((c) => c.className === 'ch-kp-point-text')!;
  const short = body.textContent;
  more.listeners.click();
  assert.ok(body.textContent.length > short.length);
  assert.equal(more.attrs['aria-expanded'], 'true');
  push({ session: sv });
  assert.deepEqual(aside.children[1].children, rowsBefore, 'the same session again rebuilds no row');
});

test('decision header draws the Why and hides it when there is no verdict', () => {
  const host = new FakeNode('section');
  let push: (v: unknown) => void = () => undefined;
  const sandbox = {
    CustomEvent: class {},
    document: { getElementById: (id: string) => (id === 'ch-decision' ? host : null), createElement: (t: string) => new FakeNode(t), activeElement: null },
    councilChamber: { live: { subscribe: (f: (v: unknown) => void) => { push = f; f(null); } } },
  };
  const ns = load(['chamber-decision.js'], sandbox as Record<string, unknown>);
  const why = host.children.find((c) => c.className === 'ch-dec-why')!;
  assert.equal(why.hidden, true);
  const sv = sessionView();
  assert.equal(ns.decision.whyModel(sv).steps.length, 4);
  push({ session: sv });
  assert.equal(why.hidden, false);
  const t = words(why);
  assert.match(t, /What has to happen first/);
  assert.match(t, /How strong the evidence is/);
  assert.match(t, /Sharpest caution, from Simon Sinek/);
  push({ session: { ...sv, verdict: null } });
  assert.equal(why.hidden, true);
  assert.equal(why.children.length, 0);
});
