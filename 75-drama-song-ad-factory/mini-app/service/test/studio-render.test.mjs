// ============================================================================
// studio-render.test.mjs — the page draws the box the contract asks for (DSR-107)
//
//   node --test 75-drama-song-ad-factory/mini-app/service/test/studio-render.test.mjs
//
// WHY THIS FILE LIVES HERE. brief.test.mjs proves the brief travels: the ids,
// the storage, the incomplete marking. It cannot see the page. The PR for
// DSR-105 claimed studio.js "renders a textarea for those" typed questions,
// and the call site passed no question through, so `typed` was unreachable and
// the wording of an option was still what chose the shape. This file sits next
// to brief.test.mjs so one `node --test` run from mini-app/service covers both
// halves of that claim: the brief travels, AND the page draws it the way the
// contract says.
//
// IT EXECUTES THE SHIPPED CODE. No substring match on studio.js, no regex over
// the source: it imports the real module, installs a minimal DOM shim (the same
// idea checks/approvals-view-check.mjs uses), calls the real render(), and
// inspects the element tree that comes out. A refactor that stops passing the
// question through makes these tests red, because the textarea stops being
// built at all.
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

/** Render ONE question on the real question screen and return its element tree. */
function renderQuestion(question) {
  state.page = 'questions';
  state.questions = [question];
  state.qIndex = 0;
  state.picks = [];
  state.texts = [];
  render();
  return walk(registry.main);
}

const byTag = (tree, tag) => tree.filter((n) => n.tagName === tag);
const labelsOf = (tree) => byTag(tree, 'LABEL').map((n) => n.textContent);
// the option radios are inputs too, so a "one-line box" is typed=text only
const textInputs = (tree) => byTag(tree, 'INPUT').filter((n) => n.attrs.type === 'text');

// ── 1. a typed brief question really draws a textarea ────────────────────────

test('studio render: the served typed brief question draws a textarea', () => {
  const offer = committed.questions.find((q) => q.id === 'offer');
  assert.ok(offer, 'questions.json no longer carries the offer question');
  assert.equal(offer.typed, true, 'the contract must say this one is typed');

  const tree = renderQuestion(offer);
  const areas = byTag(tree, 'TEXTAREA');

  assert.equal(areas.length, 1,
    'the typed contract did not reach the renderer: expected one <textarea>, '
    + `got ${areas.length} (element tags present: ${[...new Set(tree.map((n) => n.tagName))].join(', ')})`);
  assert.equal(areas[0].attrs.rows, '3');
  assert.ok(labelsOf(tree).includes('Your answer, in your own words'),
    'the typed screen keeps its own label');

  // the box sits inside the fieldset that carries the question, not beside it
  const fieldset = byTag(tree, 'FIELDSET')[0];
  assert.ok(fieldset, 'the question screen has no fieldset');
  assert.ok(walk(fieldset).some((n) => n.tagName === 'TEXTAREA'),
    'the textarea is not inside the question fieldset');
});

// ── 2. the untyped BUDGET question still draws one line ──────────────────────

test('studio render: the untyped budget question still draws a single-line input', () => {
  const spend = committed.questions.find((q) => q.id === 'spend');
  assert.ok(spend, 'questions.json no longer carries the spend question');
  assert.equal(spend.typed, false, 'the budget is an amount, not a sentence');

  const tree = renderQuestion(spend);
  assert.equal(byTag(tree, 'TEXTAREA').length, 0,
    'the budget became a multi-line box — typed must decide the shape');
  const lines = textInputs(tree);
  assert.equal(lines.length, 1, `expected one single-line box, got ${lines.length}`);
  assert.ok(labelsOf(tree).includes('Your answer'));
});

// ── 3. `typed` decides the shape, not the wording of the option ──────────────
//
// Both questions below carry the SAME option wording — the wording the page
// sniffs to decide whether a text box appears at all. The only difference is
// the contract's own `typed` flag. Pre-fix, both drew an <input> because the
// flag never reached the renderer; post-fix they differ.

test('studio render: identical option wording, opposite shape, decided by typed', () => {
  const wording = 'Reply with your own words.';
  const base = (typed) => ({
    id: `probe-${typed}`, label: 'PROBE', typed,
    question: 'Say the thing.',
    options: [{ n: 1, text: 'Type it in', detail: wording, price: null, recommended: false }],
  });

  const typedTree = renderQuestion(base(true));
  assert.equal(byTag(typedTree, 'TEXTAREA').length, 1,
    'typed:true with free-text wording must draw a textarea');
  assert.equal(textInputs(typedTree).length, 0);

  const untypedTree = renderQuestion(base(false));
  assert.equal(byTag(untypedTree, 'TEXTAREA').length, 0,
    'typed:false with the same wording must stay one line');
  assert.equal(textInputs(untypedTree).length, 1);

  // the typed box starts empty, and what is typed in it reaches the answer
  // store through the callback answerBox wired up — so the shape change did
  // not quietly orphan the answer
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

// ── 4. the other half: the wording still gates whether a box appears ─────────
//
// The PR says the shape comes from `typed` and the presence of a text box
// still comes from reading the option's own detail. This pins that second half
// so neither half can drift silently: typed:true is NOT enough on its own.

test('studio render: typed:true with non-typeable wording draws no text box', () => {
  const tree = renderQuestion({
    id: 'probe-gate', label: 'PROBE', typed: true, question: 'Pick one.',
    options: [{ n: 1, text: 'Option A', detail: 'A or B, not a sentence', price: null, recommended: false }],
  });
  assert.equal(byTag(tree, 'TEXTAREA').length, 0,
    'a typed question whose option is not typeable grew a textarea');
  assert.equal(textInputs(tree).length, 0,
    'a typed question whose option is not typeable grew a text box');
  assert.equal(byTag(tree, 'INPUT').length, 1, 'the option itself is still a plain radio');
});

// ── 5. every question the page is served is drawn from the contract ──────────

test('studio render: all served brief questions draw the textarea', () => {
  const brief = committed.questions.filter((q) => q.typed);
  assert.equal(brief.length, 5, 'the card opens with five typed brief questions');
  for (const q of brief) {
    const tree = renderQuestion(q);
    assert.equal(byTag(tree, 'TEXTAREA').length, 1, `${q.id} drew no textarea`);
  }
});
