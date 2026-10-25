/**
 * W29 unit B: chamber decision header.
 *
 * Runner:
 *   node --import tsx --test tests/chamber-decision.test.ts
 *
 * Loads chamber-decision.js in node:vm. The pure model is tested directly; the
 * DOM half runs against a tiny fake document so the empty state, button wiring,
 * badges, recommended mark and "only changed nodes are touched" are proven too.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
const jsSource = readFileSync(join(chamberDir, 'chamber-decision.js'), 'utf8');
const cssSource = readFileSync(join(chamberDir, 'chamber-decision.css'), 'utf8');

type Row = {
  letter: string;
  label: string;
  valueText: string;
  widthPct: number;
  recommended: boolean;
  srText: string;
};
type Api = {
  rowsModel(session: unknown): Row[];
  badgesModel(session: unknown): Array<{ kind: string; text: string }>;
  subText(mode: unknown): string | null;
};

function plain<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}
function loadApi(): Api {
  const sandbox: Record<string, unknown> = {};
  runInNewContext(jsSource, sandbox);
  return (sandbox.councilChamber as { decision: Api }).decision;
}

const opt = (id: string, letter: string, label: string, votes: number | null, extra = {}) => ({
  id,
  letter,
  label,
  kind: 'other',
  votes,
  share: votes === null ? 0 : votes / 9,
  recommended: false,
  score: null,
  ...extra,
});
const session = (options: unknown[], extra = {}) => ({
  question: 'Should we launch?',
  sample: false,
  demo: false,
  options,
  votesRound: 2,
  voters: 9,
  verdict: null,
  ...extra,
});

test('rowsModel: no positions gives a dash, zero width and the no-positions sentence', () => {
  const rows = plain(loadApi().rowsModel(session([opt('o1', 'A', 'Launch now', null)])));
  assert.deepEqual(rows[0], {
    letter: 'A',
    label: 'Launch now',
    valueText: '–',
    widthPct: 0,
    recommended: false,
    srText: 'Option A, Launch now: no positions yet.',
  });
});

test('rowsModel: 3 of 9 reads "3" and 33.3%, letters follow option order, srText matches', () => {
  const rows = plain(
    loadApi().rowsModel(
      session([
        opt('o1', 'A', 'Launch now', 3),
        opt('o2', 'B', 'Pilot with 10 clients first', 4),
        opt('o3', 'C', 'Wait', 2),
      ]),
    ),
  );
  assert.deepEqual(
    rows.map((r) => r.letter),
    ['A', 'B', 'C'],
  );
  assert.equal(rows[0].valueText, '3');
  assert.equal(rows[0].widthPct, 33.3);
  assert.equal(
    rows[1].srText,
    'Option B, Pilot with 10 clients first: 4 of 9 advisors prefer this in round 2.',
  );
  assert.equal(rows[2].widthPct, 22.2);
});

test('rowsModel: a zero vote is "0" (not a dash); share falls back to votes/voters', () => {
  const o = { id: 'o1', letter: 'A', label: 'x', votes: 0 };
  const rows = plain(loadApi().rowsModel(session([o, { id: 'o2', letter: 'B', label: 'y', votes: 3 }])));
  assert.equal(rows[0].valueText, '0');
  assert.equal(rows[0].widthPct, 0);
  assert.equal(rows[1].widthPct, 33.3);
});

test('rowsModel: recommended comes from the flag or from the verdict id', () => {
  const api = loadApi();
  const flagged = plain(api.rowsModel(session([opt('o1', 'A', 'a', 1), opt('o2', 'B', 'b', 5, { recommended: true })])));
  assert.deepEqual(
    flagged.map((r) => r.recommended),
    [false, true],
  );
  const byVerdict = plain(
    api.rowsModel(
      session([opt('o1', 'A', 'a', 1), opt('o2', 'B', 'b', 5)], {
        verdict: { labelText: 'Go', recommendedOptionId: 'o1' },
      }),
    ),
  );
  assert.deepEqual(
    byVerdict.map((r) => r.recommended),
    [true, false],
  );
});

test('rowsModel: null session and empty options give no rows', () => {
  const api = loadApi();
  assert.deepEqual(plain(api.rowsModel(null)), []);
  assert.deepEqual(plain(api.rowsModel(session([]))), []);
});

test('badgesModel: Sample decision only when sample and not demo; Verdict when set', () => {
  const api = loadApi();
  assert.deepEqual(plain(api.badgesModel(session([], { sample: true }))), [
    { kind: 'sample', text: 'Sample decision' },
  ]);
  assert.deepEqual(plain(api.badgesModel(session([], { sample: true, demo: true }))), []);
  assert.deepEqual(
    plain(api.badgesModel(session([], { verdict: { labelText: 'Go, with conditions', recommendedOptionId: 'o1' } }))),
    [{ kind: 'verdict', text: 'Verdict: Go, with conditions' }],
  );
  assert.deepEqual(plain(api.badgesModel(null)), []);
});

test('subText: each council size names its own advisors and rounds; older modes add nothing', () => {
  const api = loadApi();
  assert.equal(api.subText('light'), 'Light council: three advisors, two rounds, one verdict.');
  assert.equal(api.subText('medium'), 'Medium council: nine advisors, up to four rounds, one verdict.');
  assert.equal(api.subText('heavy'), 'Heavy council: nine advisors, up to ten rounds, one verdict.');
  for (const mode of ['full', 'quick', 'selected', 'consult', null, undefined, 3, 'Light']) {
    assert.equal(api.subText(mode), null, String(mode));
  }
});

// ------------------------------------------------------------ fake DOM
const focused: { current: FakeNode | null } = { current: null };

class FakeNode {
  tagName: string;
  className = '';
  id = '';
  hidden = false;
  tabIndex = 0;
  type = '';
  style: Record<string, string> = {};
  attrs: Record<string, string> = {};
  children: FakeNode[] = [];
  listeners: Record<string, Array<() => void>> = {};
  textWrites = 0;
  private text = '';
  constructor(tag: string) {
    this.tagName = tag;
  }
  get textContent(): string {
    return this.text + this.children.map((c) => c.textContent).join('');
  }
  set textContent(v: string) {
    this.textWrites += 1;
    this.text = v;
    this.children = [];
  }
  get firstChild(): FakeNode | undefined {
    return this.children[0];
  }
  get classList() {
    const self = this;
    return {
      add(c: string) {
        self.className = (self.className + ' ' + c).trim();
      },
      toggle(c: string, on: boolean) {
        const set = new Set(self.className.split(/\s+/).filter(Boolean));
        if (on) set.add(c);
        else set.delete(c);
        self.className = [...set].join(' ');
      },
    };
  }
  appendChild(n: FakeNode) {
    this.children.push(n);
    return n;
  }
  removeChild(n: FakeNode) {
    this.children.splice(this.children.indexOf(n), 1);
    return n;
  }
  setAttribute(k: string, v: string) {
    this.attrs[k] = v;
  }
  addEventListener(t: string, fn: () => void) {
    (this.listeners[t] ||= []).push(fn);
  }
  focus() {
    focused.current = this;
  }
  contains(n: unknown): boolean {
    return n === this || this.children.some((c) => c.contains(n));
  }
  find(cls: string): FakeNode[] {
    const own = this.className.split(/\s+/).includes(cls) ? [this] : [];
    return own.concat(...this.children.map((c) => c.find(cls)));
  }
}

type View = { mode: string; session: unknown };
function boot() {
  const host = new FakeNode('section');
  host.id = 'ch-decision';
  const events: string[] = [];
  const details: unknown[] = [];
  focused.current = null;
  let push: (v: View) => void = () => {};
  const live = {
    started: 0,
    startDemo() {
      live.started += 1;
    },
    subscribe(fn: (v: View) => void) {
      push = fn;
      fn({ mode: 'empty', session: null });
      return () => {};
    },
  };
  const sandbox: Record<string, unknown> = {
    document: {
      getElementById: (id: string) => (id === 'ch-decision' ? host : null),
      createElement: (t: string) => new FakeNode(t),
      dispatchEvent: (e: { type: string; detail?: unknown }) => {
        events.push(e.type);
        details.push(e.detail);
      },
      get activeElement() {
        return focused.current;
      },
    },
    CustomEvent: class {
      type: string;
      detail: unknown;
      constructor(t: string, init?: { detail?: unknown }) {
        this.type = t;
        this.detail = init && init.detail;
      }
    },
    councilChamber: { live },
  };
  runInNewContext(jsSource, sandbox);
  return { host, events, details, live, push: (v: View) => push(v) };
}

const EMPTY_SUB =
  'Light, medium or heavy: three advisors and two rounds, up to nine advisors and ten rounds. One verdict.';

test('DOM: empty state shows the invitation and wires both buttons', () => {
  const { host, events, live } = boot();
  assert.equal(host.find('ch-dec-title')[0].textContent, 'Ask the council a question');
  assert.equal(host.find('ch-dec-title')[0].id, 'ch-decision-title');
  assert.equal(host.find('ch-dec-title')[0].tagName, 'h1');
  assert.equal(host.find('ch-dec-sub')[0].textContent, EMPTY_SUB);
  assert.equal(host.find('ch-dec-actions')[0].hidden, false);
  assert.equal(host.find('ch-dec-options')[0].hidden, true);
  host.find('ch-dec-new')[0].listeners.click[0]();
  host.find('ch-dec-demo')[0].listeners.click[0]();
  assert.deepEqual(events, ['chamber:open-composer']);
  assert.equal(live.started, 1);
});

test('DOM: a council-size session shows its own format caption; older modes stay captionless', () => {
  const { host, push } = boot();
  push({ mode: 'live', session: session([opt('o1', 'A', 'Launch now', null)], { mode: 'light' }) });
  assert.equal(host.find('ch-dec-sub')[0].textContent, 'Light council: three advisors, two rounds, one verdict.');
  assert.equal(host.find('ch-dec-sub')[0].hidden, false);
  push({ mode: 'live', session: session([opt('o1', 'A', 'Launch now', null)], { mode: 'heavy' }) });
  assert.equal(host.find('ch-dec-sub')[0].textContent, 'Heavy council: nine advisors, up to ten rounds, one verdict.');
  push({ mode: 'live', session: session([opt('o1', 'A', 'Launch now', null)], { mode: 'full' }) });
  assert.equal(host.find('ch-dec-sub')[0].textContent, '');
  assert.equal(host.find('ch-dec-sub')[0].hidden, true);
});

test('DOM: focus moves to the title when the focused empty-state button is hidden', () => {
  const { host, events, details, push } = boot();
  const title = host.find('ch-dec-title')[0];
  host.find('ch-dec-new')[0].listeners.click[0]();
  assert.equal((details[0] as { opener: unknown }).opener, title, 'composer opener survives the hide');
  assert.deepEqual(events, ['chamber:open-composer']);
  focused.current = host.find('ch-dec-demo')[0];
  push({ mode: 'demo', session: { question: 'Q?', options: [] } });
  assert.equal(host.find('ch-dec-actions')[0].hidden, true);
  assert.equal(focused.current, title);
  assert.equal(title.tabIndex, -1);
});

test('DOM: focus elsewhere is left alone when the empty state hides', () => {
  const { host, push } = boot();
  const other = new FakeNode('input');
  focused.current = other;
  push({ mode: 'demo', session: { question: 'Q?', options: [] } });
  assert.equal(focused.current, other);
  assert.equal(host.find('ch-dec-title')[0].tabIndex, 0);
});

test('DOM: a replayed vote sequence updates rows, keeps node identity and marks the verdict', () => {
  const { host, push } = boot();
  const options = (votes: Array<number | null>, reco = '') => [
    opt('o1', 'A', 'Launch to all clients in January', votes[0], { recommended: reco === 'o1' }),
    opt('o2', 'B', 'Pilot with 10 clients first', votes[1], { recommended: reco === 'o2' }),
  ];
  push({ mode: 'demo', session: session(options([null, null]), { sample: true, demo: false }) });
  const title = host.find('ch-dec-title')[0];
  assert.equal(title.textContent, 'Should we launch?');
  assert.equal(host.find('ch-dec-actions')[0].hidden, true);
  assert.equal(host.find('ch-dec-sub')[0].hidden, true);
  assert.deepEqual(
    host.find('ch-dec-badge').map((b) => b.textContent),
    ['Sample decision'],
  );
  const rowsBefore = host.find('ch-dec-row');
  assert.equal(rowsBefore.length, 2);
  assert.deepEqual(
    host.find('ch-dec-value').map((v) => v.textContent),
    ['–', '–'],
  );

  push({ mode: 'demo', session: session(options([3, 4]), { sample: true }) });
  assert.deepEqual(
    host.find('ch-dec-value').map((v) => v.textContent),
    ['3', '4'],
  );
  assert.deepEqual(
    host.find('ch-dec-fill').map((f) => f.style.width),
    ['33.3%', '44.4%'],
  );
  assert.equal(host.find('ch-dec-row')[0], rowsBefore[0], 'rows are reused, not rebuilt');

  const titleWrites = title.textWrites;
  const labelWrites = host.find('ch-dec-label')[0].textWrites;
  push({ mode: 'demo', session: session(options([3, 5]), { sample: true }) });
  assert.equal(title.textWrites, titleWrites, 'unchanged title is not rewritten');
  assert.equal(host.find('ch-dec-label')[0].textWrites, labelWrites, 'unchanged label is not rewritten');

  push({
    mode: 'live',
    session: session(options([2, 6], 'o2'), {
      verdict: { labelText: 'Go, with conditions', recommendedOptionId: 'o2' },
    }),
  });
  assert.deepEqual(
    host.find('ch-dec-badge').map((b) => b.textContent),
    ['Verdict: Go, with conditions'],
  );
  const rows = host.find('ch-dec-row');
  assert.ok(!rows[0].className.includes('ch-dec-row--reco'));
  assert.ok(rows[1].className.includes('ch-dec-row--reco'));
  assert.equal(rows[1].find('ch-dec-reco')[0].hidden, false);
  assert.equal(rows[1].find('ch-dec-reco')[0].textContent, 'Recommended');
  assert.equal(rows[0].find('ch-dec-reco')[0].hidden, true);

  push({ mode: 'live', session: session(options([2, 6, null]).slice(0, 1)) });
  assert.equal(host.find('ch-dec-row').length, 1, 'rows shrink with the option list');
});

test('source hygiene: no innerHTML, no URLs, no colour literals in the decision css', () => {
  assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML/.test(jsSource));
  assert.ok(!/https?:\/\//.test(jsSource + cssSource));
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/.test(cssSource), 'colours only via var(--ch-*)');
  assert.ok(/prefers-reduced-motion/.test(cssSource));
  assert.ok(/var\(--ch-/.test(cssSource));
});
