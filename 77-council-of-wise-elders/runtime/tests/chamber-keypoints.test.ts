/**
 * Chamber KEY POINTS panel (unit D).
 *
 * Runner:
 *   node --import tsx --test tests/chamber-keypoints.test.ts
 *
 * Loads chamber-keypoints.js in node:vm: the pure diff, then the renderer
 * against a minimal fake DOM (append-only rows, node identity, reset).
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
const jsSource = readFileSync(join(chamberDir, 'chamber-keypoints.js'), 'utf8');
const cssSource = readFileSync(join(chamberDir, 'chamber-keypoints.css'), 'utf8');

type Point = { label: string; detail: string | null; at: string | null };
type Diff = { append: Point[]; reset: boolean };

const pt = (label: string, detail: string | null = null): Point => ({ label, detail, at: null });

// ------------------------------------------------------------- fake DOM

class FakeNode {
  children: FakeNode[] = [];
  parent: FakeNode | null = null;
  attrs: Record<string, string> = {};
  classes = new Set<string>();
  className = '';
  textContent = '';
  hidden = false;
  id = '';
  constructor(readonly tag: string) {}
  get firstChild(): FakeNode | null {
    return this.children[0] ?? null;
  }
  appendChild(child: FakeNode): FakeNode {
    child.parent = this;
    this.children.push(child);
    return child;
  }
  removeChild(child: FakeNode): FakeNode {
    this.children.splice(this.children.indexOf(child), 1);
    child.parent = null;
    return child;
  }
  setAttribute(name: string, value: string): void {
    this.attrs[name] = value;
  }
  get classList(): { add(name: string): void } {
    return { add: (name: string) => void this.classes.add(name) };
  }
}

function text(node: FakeNode): string[] {
  return node.children.map((child) => [child.textContent, ...text(child)].filter(Boolean).join('|'));
}

type Subscriber = (view: unknown) => void;

function boot(): { aside: FakeNode; push(session: unknown): void; ns: { keypoints: { diff(a: Point[], b: Point[]): Diff } } } {
  const aside = new FakeNode('aside');
  let subscriber: Subscriber = () => undefined;
  const sandbox: Record<string, unknown> = {
    document: {
      getElementById: (id: string) => (id === 'ch-keypoints' ? aside : null),
      createElement: (tag: string) => new FakeNode(tag),
    },
    councilChamber: {
      live: {
        subscribe: (fn: Subscriber) => {
          subscriber = fn;
          fn({ session: null });
          return () => undefined;
        },
      },
    },
  };
  sandbox.globalThis = sandbox;
  runInNewContext(jsSource, sandbox);
  return {
    aside,
    push: (session) => subscriber({ session }),
    ns: sandbox.councilChamber as never,
  };
}

function diffOf(prev: Point[], next: Point[]): Diff {
  return JSON.parse(JSON.stringify(boot().ns.keypoints.diff(prev, next))) as Diff;
}

// ----------------------------------------------------------------- diff

test('diff appends only the new tail', () => {
  const a = pt('CHAIR: READING YOUR QUESTION');
  const b = pt('ROUND 1: OPENING POSITIONS');
  const c = pt('ROUND 1: ALL 9 POSITIONS IN');
  assert.deepEqual(diffOf([a], [a, b, c]), { append: [b, c], reset: false });
  assert.deepEqual(diffOf([], [a, b]), { append: [a, b], reset: false });
});

test('diff signals reset when the first label differs, and when the list shrinks', () => {
  const a = pt('CHAIR: READING YOUR QUESTION');
  const b = pt('ROUND 1: OPENING POSITIONS');
  const other = pt('CONSULT: ANSWERING');
  assert.deepEqual(diffOf([a, b], [other, b]), { append: [other, b], reset: true });
  assert.deepEqual(diffOf([a, b], [a]), { append: [a], reset: true });
  assert.deepEqual(diffOf([a, b], []), { append: [], reset: true });
});

test('diff is a no-op for identical or empty lists', () => {
  const a = pt('CHAIR: READING YOUR QUESTION');
  assert.deepEqual(diffOf([a], [a]), { append: [], reset: false });
  assert.deepEqual(diffOf([], []), { append: [], reset: false });
  assert.deepEqual(diffOf([], undefined as never), { append: [], reset: false });
});

// ------------------------------------------------------------- renderer

const base = (id: string, keyPoints: Point[]) => ({ id, keyPoints });

test('renderer: header, aria wiring and the empty line', () => {
  const { aside } = boot();
  const [title, list, empty] = aside.children;
  assert.equal(title.tag, 'h2');
  assert.equal(title.id, 'ch-keypoints-title');
  assert.equal(title.textContent, 'KEY POINTS');
  assert.equal(list.tag, 'ol');
  assert.equal(list.attrs['aria-labelledby'], 'ch-keypoints-title');
  assert.equal(list.attrs['aria-live'], 'polite');
  assert.equal(list.attrs['aria-relevant'], 'additions');
  assert.equal(empty.textContent, 'Key points appear here as the council works.');
  assert.equal(empty.hidden, false);
  assert.equal(list.children.length, 0);
});

test('renderer: rows append without touching existing nodes, label then hairline then detail', () => {
  const { aside, push } = boot();
  const list = aside.children[1];
  const empty = aside.children[2];
  const first = pt('CHAIR: READING YOUR QUESTION');
  push(base('s1', [first]));
  assert.equal(empty.hidden, true);
  const firstRow = list.children[0];
  assert.deepEqual(text(list), ['CHAIR: READING YOUR QUESTION']);
  const [label, rule] = firstRow.children[0].children;
  assert.equal(label.className, 'ch-kp-label');
  assert.equal(rule.className, 'ch-kp-rule');
  assert.equal(rule.attrs['aria-hidden'], 'true');

  push(base('s1', [first, pt('ROUND 1: OPENING POSITIONS'), pt('VERDICT: GO', 'Option B: Pilot')]));
  assert.equal(list.children.length, 3);
  assert.equal(list.children[0], firstRow, 'existing row keeps its node identity');
  const detail = list.children[2].children[1];
  assert.equal(detail.className, 'ch-kp-detail');
  assert.equal(detail.textContent, 'Option B: Pilot');
  assert.equal(list.children[1].children.length, 1, 'no detail paragraph when detail is null');

  const before = list.children.slice();
  push(base('s1', [first, pt('ROUND 1: OPENING POSITIONS'), pt('VERDICT: GO', 'Option B: Pilot')]));
  assert.deepEqual(list.children, before, 'identical update changes nothing');
});

test('renderer: a different session rebuilds, even when the first label is the same', () => {
  const { aside, push } = boot();
  const list = aside.children[1];
  const empty = aside.children[2];
  const first = pt('CHAIR: READING YOUR QUESTION');
  push(base('s1', [first]));
  const oldRow = list.children[0];
  push(base('s2', [first]));
  assert.equal(list.children.length, 1);
  assert.notEqual(list.children[0], oldRow);
  push(null);
  assert.equal(list.children.length, 0);
  assert.equal(empty.hidden, false);
});

test('renderer: a detail that arrives after the row is drawn shows up in place', () => {
  const { aside, push } = boot();
  const list = aside.children[1];
  push(base('s1', [pt('CHAIR: FINDING THE FAULT LINES', null)]));
  const row = list.children[0];
  assert.equal(row.children.length, 1);
  push(base('s1', [pt('CHAIR: FINDING THE FAULT LINES', 'x')]));
  assert.equal(list.children.length, 1);
  assert.equal(list.children[0], row, 'first row keeps its node identity');
  assert.equal(row.children[1].className, 'ch-kp-detail');
  assert.equal(row.children[1].textContent, 'x');
  const detailNode = row.children[1];
  push(base('s1', [pt('CHAIR: FINDING THE FAULT LINES', 'y')]));
  assert.equal(row.children[1], detailNode);
  assert.equal(detailNode.textContent, 'y');
});

// --------------------------------------------------------------- static

test('static: no innerHTML, no URLs, no colour literals, token colours only', () => {
  assert.doesNotMatch(jsSource, /innerHTML|insertAdjacentHTML|document\.write/);
  assert.doesNotMatch(jsSource, /https?:\/\//);
  assert.doesNotMatch(cssSource, /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/);
  assert.match(cssSource, /var\(--ch-ink-muted\)/);
  assert.match(cssSource, /\.ch-kp-title\s*{[^}]*margin:\s*0 calc\(-1 \* var\(--ch-space-4\)\)[^}]*padding-inline:\s*var\(--ch-space-4\)/);
  assert.match(cssSource, /\.ch-kp-rule\s*{[^}]*flex:\s*1 1 1px/);
  assert.match(cssSource, /\.ch-kp-label\s*{[^}]*font-size:\s*11px[^}]*font-weight:\s*700/);
});
