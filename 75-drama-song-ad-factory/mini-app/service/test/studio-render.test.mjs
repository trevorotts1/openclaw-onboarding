// ============================================================================
// studio-render.test.mjs — the page draws the screen the card asks for (DSR-107)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/studio-render.test.mjs
//
// WHY THIS FILE LIVES HERE. brief.test.mjs proves the brief travels: the ids,
// the storage, the incomplete marking. It cannot see the page. This file sits
// next to brief.test.mjs so one `node --test` run from mini-app/service covers
// both halves: the brief travels, AND the page draws it the way the contract
// says.
//
// S75-074 (U-Z10) rewrote these five tests. A typed question is now drawn as
// the question, its example and ONE text box — never an option row, and never
// a box that appears because an option's wording was sniffed. A choice screen
// keeps its option row; a box appears there only when the option the client
// picks reads typed text ("reply with …"), and that box stays single-line for
// an amount such as BUDGET's own limit. The served export reaches both shapes
// (an older export carries the one "reply with" row for a typed screen), so
// every test below passes with either export.
//
// IT EXECUTES THE SHIPPED CODE. No substring match on studio.js, no regex over
// the source: it imports the real module, installs a minimal DOM shim (the same
// idea checks/approvals-view-check.mjs uses), calls the real render(), and
// inspects the element tree that comes out.
//
// No live end to end: no link minted, no order placed, nothing runs against a
// deployed Worker.
// ============================================================================

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// Imported BEFORE any `document` exists — studio.js boots only when a DOM is
// there at module scope, and this file installs its own shim below, afterwards.
import { render, state } from '../../ui/studio.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const QUESTIONS_JSON = resolve(HERE, '..', '..', 'ui', 'questions.json');
const committed = JSON.parse(readFileSync(QUESTIONS_JSON, 'utf8'));

// ── the DOM shim ─────────────────────────────────────────────────────────────
function makeElement(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    attrs: Object.create(null),
    children: [],
    listeners: Object.create(null),
    textContent: '',
    value: '',
    style: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
    },
    append(...nodes) { for (const n of nodes) if (n) this.children.push(n); },
    appendChild(n) { this.children.push(n); return n; },
    replaceChildren(...nodes) { this.children = nodes.filter(Boolean); },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    focus() { this.focused = true; },
    querySelector(selector) {
      const want = String(selector).toUpperCase();
      return walk(this).find((n) => n !== this && n.tagName === want) || null;
    },
  };
}

const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children || []) walk(c, out);
  return out;
};

const registry = Object.create(null);
for (const id of ['status', 'main', 'steps-nav', 'rail', 'rail-fill', 'step-label']) {
  registry[id] = makeElement('div');
}
registry.main = makeElement('main');
globalThis.document = {
  createElement: makeElement,
  getElementById: (id) => registry[id] || null,
};
globalThis.location = { hash: '', origin: 'https://studio.example.com', pathname: '/' };
globalThis.history = { replaceState() {} };

/** Render ONE question on the real question screen and return its element tree. */
function renderQuestion(question) {
  state.page = 'questions';
  state.questions = [question];
  state.visible = [];
  state.visibleFrom = null;
  state.qIndex = 0;
  state.picks = [];
  state.texts = [];
  state.replies = [];
  state.note = '';
  render();
  return walk(registry.main);
}

/** Pick an option the way a client does: fire the radio's own change listener. */
function pick(tree, value) {
  const radio = byTag(tree, 'INPUT').find((n) => n.attrs.type === 'radio' && n.attrs.value === String(value));
  assert.ok(radio, `no radio with value ${value}`);
  const onChange = (radio.listeners.change || [])[0];
  assert.equal(typeof onChange, 'function', 'the option is not wired to anything');
  onChange();
  return walk(registry.main);
}

const byTag = (tree, tag) => tree.filter((n) => n.tagName === tag);
const labelsOf = (tree) => byTag(tree, 'LABEL').map((n) => n.textContent);
// the option radios are inputs too, so a "one-line box" is typed=text only
const textInputs = (tree) => byTag(tree, 'INPUT').filter((n) => n.attrs.type === 'text');
const radios = (tree) => byTag(tree, 'INPUT').filter((n) => n.attrs.type === 'radio');

// ── 1. a typed brief question: the question, the example, ONE text box ───────

test('studio render: the served typed brief question draws a textarea and no option row', () => {
  const offer = committed.questions.find((q) => q.id === 'offer');
  assert.ok(offer, 'questions.json no longer carries the offer question');
  assert.equal(offer.typed, true, 'the contract must say this one is typed');

  const tree = renderQuestion(offer);
  const areas = byTag(tree, 'TEXTAREA');

  assert.equal(areas.length, 1,
    'the typed contract did not reach the renderer: expected one <textarea>, '
    + `got ${areas.length} (element tags present: ${[...new Set(tree.map((n) => n.tagName))].join(', ')})`);
  assert.equal(areas[0].attrs.rows, '3');
  assert.equal(radios(tree).length, 0, 'a typed screen must not draw an option row');
  assert.ok(labelsOf(tree).includes('Your answer, in your own words'),
    'the typed screen keeps its own label');

  // the box sits inside the fieldset that carries the question, not beside it
  const fieldset = byTag(tree, 'FIELDSET')[0];
  assert.ok(fieldset, 'the question screen has no fieldset');
  assert.ok(walk(fieldset).some((n) => n.tagName === 'TEXTAREA'),
    'the textarea is not inside the question fieldset');
  // and the example is drawn with the question
  if (offer.example) {
    assert.ok(walk(fieldset).some((n) => String(n.textContent).includes(String(offer.example))),
      'the typed screen lost its example');
  }
});

// ── 2. BUDGET is a choice screen: a recommended limit, or a box for my own ───

test('studio render: the budget screen offers the recommended limit and a single-line box', () => {
  // The shape the re-export gives BUDGET (S75-074 step 4): option 1 carries the
  // recommended limit as a dollar figure; option 2 reads typed text.
  const spend = {
    id: 'spend', label: 'BUDGET', title: 'Your spending limit', typed: false,
    question: 'What is the most this video may spend? Work stops and asks you before going over.',
    options: [
      { n: 1, text: 'Use the recommended limit - about $24', detail: '', recommended: true },
      { n: 2, text: 'Set my own limit', detail: 'reply with a dollar amount, like $25', recommended: false },
    ],
    why: 'The limit includes a redo allowance.',
  };

  let tree = renderQuestion(spend);
  assert.equal(byTag(tree, 'TEXTAREA').length, 0, 'BUDGET must not become a multi-line box');
  assert.equal(textInputs(tree).length, 0, 'no box before the client picks how to set the limit');
  assert.equal(radios(tree).length, 2, 'BUDGET is a choice of two options');

  // the recommended limit is drawn once, as a figure, with its tag
  const text = tree.map((n) => n.textContent).filter(Boolean).join(' | ');
  assert.match(text, /\$\d/, 'BUDGET shows no dollar figure at all');
  assert.equal(byTag(tree, 'SPAN').filter((n) => /(^|\s)tag(\s|$)/.test(String(n.attrs.class || ''))).length, 1,
    'BUDGET must carry exactly one Recommended tag');

  // picking "Set my own limit" grows ONE single-line box, labelled 'Your answer'
  tree = pick(tree, '2');
  const lines = textInputs(tree);
  assert.equal(lines.length, 1, `expected one single-line box, got ${lines.length}`);
  assert.equal(byTag(tree, 'TEXTAREA').length, 0, 'a limit is an amount, not a sentence');
  assert.ok(labelsOf(tree).includes('Your answer'));
});

// ── 3. `typed` decides the shape, not the wording of the option ──────────────
//
// The typed screen below carries the SAME "reply with" wording as the choice
// screen's typeable option. The contract's own `typed` flag decides: a typed
// screen draws the box directly, a choice screen draws it only once picked.

test('studio render: identical option wording, opposite shape, decided by typed', () => {
  const wording = 'Reply with your own words.';
  const typedScreen = {
    id: 'probe-typed', label: 'PROBE', title: 'Say the thing', typed: true,
    question: 'Say the thing.',
    options: [],
  };
  const choiceScreen = {
    id: 'probe-choice', label: 'PROBE', title: 'Pick one', typed: false,
    question: 'Pick one.',
    options: [{ n: 1, text: 'Type it in', detail: wording, price: null, recommended: false }],
  };

  const typedTree = renderQuestion(typedScreen);
  assert.equal(byTag(typedTree, 'TEXTAREA').length, 1,
    'typed:true must draw a textarea directly');
  assert.equal(radios(typedTree).length, 0);
  assert.equal(textInputs(typedTree).length, 0);

  let untypedTree = renderQuestion(choiceScreen);
  assert.equal(radios(untypedTree).length, 1, 'the choice keeps its option row');
  assert.equal(byTag(untypedTree, 'TEXTAREA').length, 0);
  assert.equal(textInputs(untypedTree).length, 0, 'no box before the typeable option is picked');
  untypedTree = pick(untypedTree, '1');
  assert.equal(byTag(untypedTree, 'TEXTAREA').length, 0,
    'the same wording on a choice screen must stay one line');
  assert.equal(textInputs(untypedTree).length, 1);

  // the typed box starts empty, and what is typed in it reaches the answer store
  const area = byTag(typedTree, 'TEXTAREA')[0];
  assert.equal(area.value, '', 'a fresh screen starts with nothing typed');
  assert.equal(area.attrs.id, 'q-answer', 'the box keeps the id its label points at');
  const onInput = (area.listeners.input || [])[0];
  assert.equal(typeof onInput, 'function', 'the typed box is not wired to anything');
  area.value = 'Sweet Details Cookie-Decorating Class';
  onInput();
  assert.equal(state.texts[0], 'Sweet Details Cookie-Decorating Class',
    'typing in the box never reached the answer store');
});

// ── 4. a choice screen with nothing typeable draws no box at all ─────────────
//
// The presence of a box on a choice screen still comes from the option the
// client picks, never from the screen's own wording; and a typed screen always
// has its box, whatever its (now empty) option list says.

test('studio render: a choice screen with no typeable option draws radios only', () => {
  const tree = renderQuestion({
    id: 'probe-gate', label: 'PROBE', title: 'Pick one', typed: false, question: 'Pick one.',
    options: [
      { n: 1, text: 'Option A', detail: 'A or B, not a sentence', price: null, recommended: false },
      { n: 2, text: 'Option B', detail: '', price: null, recommended: false },
    ],
  });
  assert.equal(radios(tree).length, 2, 'both options are drawn');
  assert.equal(byTag(tree, 'TEXTAREA').length, 0, 'a choice screen grew a textarea');
  assert.equal(textInputs(tree).length, 0, 'a choice screen grew a text box');

  const typed = renderQuestion({
    id: 'probe-empty', label: 'PROBE', title: 'Say it', typed: true, question: 'Say it.',
    options: [],
  });
  assert.equal(radios(typed).length, 0, 'a typed screen with no options grew a menu');
  assert.equal(byTag(typed, 'TEXTAREA').length, 1, 'a typed screen with no options lost its box');
});

// ── 5. every question the page is served is drawn from the contract ──────────

test('studio render: all served brief questions draw exactly one textarea', () => {
  const brief = committed.questions.filter((q) => q.typed);
  assert.ok(brief.length > 0, 'the card no longer marks its brief questions as typed');
  for (const q of brief) {
    const tree = renderQuestion(q);
    assert.equal(byTag(tree, 'TEXTAREA').length, 1, `${q.id} drew no textarea`);
    assert.equal(radios(tree).length, 0, `${q.id} drew an option row beside its box`);
  }
});
