/**
 * Chamber advisory panel: the finished council's answer in plain language.
 *
 * Runner (not executed by the lane that wrote this; Trevor runs it):
 *   node --import tsx --test tests/chamber-advisory.test.ts
 *
 * Loads chamber-advisory.js in node:vm. Only the pure model is exercised here:
 * the DOM half needs a fake document and belongs with the sibling chamber
 * tests. The fixture is synthetic: every sentence in it is invented test data.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');
const jsSource = readFileSync(join(chamberDir, 'chamber-advisory.js'), 'utf8');
const cssSource = readFileSync(join(chamberDir, 'chamber-advisory.css'), 'utf8');
const fixtures = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'chamber', 'advisory-sessions.json'), 'utf8'),
) as {
  sessions: Record<string, { record: unknown; view: unknown }>;
};

type Option = {
  id: string;
  letter: string;
  label: string;
  substantial: boolean;
  votes: number | null;
  voters: number | null;
  score: number | null;
  recommended: boolean;
};
type Model = {
  present: boolean;
  kind: string;
  actionable: boolean;
  title: string;
  sub: string;
  explanation: string;
  label: string | null;
  score: number | null;
  matches: string | null;
  recommendedId: string | null;
  recommendedLetter: string | null;
  reasons: string[];
  conditions: string[];
  objection: string | null;
  steps: Array<{ title: string; description: string | null; risk: string | null }>;
  unknowns: string[];
  options: Option[];
  canCompare: boolean;
  consultAnswer: string | null;
  consultNextStep: string | null;
};
type Badges = {
  recommended: boolean;
  votes: string | null;
  score: string | null;
  note: string | null;
};
type Api = {
  model(record: unknown, session: unknown): Model;
  optionsModel(record: unknown, session: unknown): Option[];
  optionBadges(option: unknown): Badges;
  isStandIn(label: unknown): boolean;
  labelText(raw: unknown): string | null;
  unique(list: unknown): string[];
  requestText(session: unknown, m: Model): string;
};

function loadApi(): Api {
  const sandbox: Record<string, unknown> = {};
  runInNewContext(jsSource, sandbox);
  return (sandbox.councilChamber as { advisory: Api }).advisory;
}

const api = loadApi();
const fixture = (name: string): { record: unknown; view: unknown } => fixtures.sessions[name];
/** vm objects have another realm's prototypes; compare plain copies. */
const plain = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

test('a placeholder option is never presented as an actionable recommendation', () => {
  const { record, view } = fixture('placeholder');
  const m = api.model(record, view);
  assert.equal(m.present, true);
  assert.equal(m.kind, 'scored');
  assert.equal(m.actionable, false);
  assert.equal(m.title, 'No actionable recommendation');
  assert.match(m.explanation, /placeholder/);
  // The stored label and score exist, but the panel does not headline them.
  assert.equal(m.label, 'Go, with conditions');
  assert.equal(m.score, 7.4);
  assert.equal(m.options.length, 1);
  assert.equal(m.options[0].substantial, false);
  assert.equal(m.canCompare, false);
});

test('a placeholder session still surfaces its real reasons, conditions and steps', () => {
  const { record, view } = fixture('placeholder');
  const m = api.model(record, view);
  assert.equal(m.reasons.length, 3);
  assert.equal(m.steps.length, 1);
  assert.equal(m.conditions.length, 2, 'the repeated condition is de-duplicated');
  assert.equal(m.unknowns.length, 5);
  assert.equal(m.objection, null);
});

test('a historical placeholder option keeps no recommended, vote or score chip', () => {
  const placeholder = api.optionsModel(fixture('placeholder').record, fixture('placeholder').view)[0];
  assert.equal(placeholder.substantial, false);
  assert.deepEqual(plain(api.optionBadges(placeholder)), {
    recommended: false,
    votes: null,
    score: null,
    note: 'Placeholder, not a weighed option',
  });

  const real = api
    .optionsModel(fixture('actionable').record, fixture('actionable').view)
    .filter((o) => o.id === 'option-b')[0];
  assert.deepEqual(plain(api.optionBadges(real)), {
    recommended: true,
    votes: '7 of 9 advisors',
    score: 'Scored 8.2 out of 10',
    note: null,
  });

  // The card must read the gate, never the raw option flags.
  assert.match(jsSource, /var badges = optionBadges\(option\);/);
  assert.doesNotMatch(jsSource, /if \(option\.recommended\)/);
});

test('a real comparison is actionable and carries the score out of ten', () => {
  const { record, view } = fixture('actionable');
  const m = api.model(record, view);
  assert.equal(m.actionable, true);
  assert.equal(m.recommendedId, 'option-b');
  assert.equal(m.recommendedLetter, 'B');
  assert.equal(m.title, 'The council recommends Option B.');
  assert.equal(m.sub, 'FIXTURE: run a two-week test');
  assert.equal(m.score, 8.2);
  assert.equal(m.matches, '7 of 9 advisors preferred it');
  assert.equal(m.canCompare, true);
  assert.equal(m.objection, 'FIXTURE dissent: the test spends focus that the current plan needs.');
  assert.equal(m.steps.length, 2);
});

test('one real option among stand-ins is still not a comparison', () => {
  const record = {
    brief: {
      options: [
        { id: 'option-a', label: 'FIXTURE: one real option' },
        { id: 'option-b', label: 'Explore the question with the Council; no option has been chosen yet.' },
      ],
    },
    verdict: { result_kind: 'scored', label: 'GO', recommended_option_id: 'option-a', option_scores: [] },
  };
  const m = api.model(record, { id: 's1', status: 'complete', options: [], voters: 0 });
  assert.equal(m.actionable, false);
  assert.match(m.explanation, /nothing to compare/);
  assert.equal(m.score, null);
});

test('a consult is an answer, not a vote, and says so', () => {
  const { record, view } = fixture('consult');
  const m = api.model(record, view);
  assert.equal(m.kind, 'consult');
  assert.equal(m.actionable, false);
  assert.equal(m.consultAnswer, 'FIXTURE answer: the evidence on file does not settle the price.');
  assert.equal(m.consultNextStep, 'FIXTURE next step: collect three comparable price points.');
  assert.equal(m.title, 'The council answered your question.');
});

test('no verdict means nothing to render', () => {
  const m = api.model({ brief: { options: [] } }, { id: 's1', status: 'running', options: [] });
  assert.equal(m.present, false);
  assert.equal(m.actionable, false);
  assert.equal(api.model(null, null).present, false);
});

test('isStandIn treats an absent label as no choice', () => {
  assert.equal(api.isStandIn(''), true);
  assert.equal(api.isStandIn(null), true);
  assert.equal(api.isStandIn('no option has been chosen yet.'), true);
  assert.equal(api.isStandIn('FIXTURE: run a two-week test'), false);
});

test('the copyable request names the session and never claims approval', () => {
  const { record, view } = fixture('placeholder');
  const m = api.model(record, view);
  const text = api.requestText({ id: 'sess-fixture-placeholder' }, m);
  assert.match(text, /sess-fixture-placeholder/);
  assert.match(text, /no actionable recommendation/);
  assert.doesNotMatch(text, /approved|executed|sent/);

  const ok = api.model(fixture('actionable').record, fixture('actionable').view);
  const okText = api.requestText({ id: 'sess-fixture-actionable' }, ok);
  assert.match(okText, /Option B/);
});

test('duplicate removal keeps the first occurrence in order', () => {
  assert.deepEqual(api.unique(['a', 'b', 'a', '', null, 'b', 'c']), ['a', 'b', 'c']);
  assert.deepEqual(api.unique('not a list'), []);
});

test('the advisory stylesheet uses theme tokens only and keeps 44px targets', () => {
  assert.doesNotMatch(cssSource, /#[0-9a-fA-F]{3,8}\b/, 'no raw hex colour literal');
  assert.doesNotMatch(cssSource, /\b(?:rgb|hsl)a?\(/, 'no raw rgb/hsl literal');
  assert.match(cssSource, /min-height:\s*44px/);
  assert.match(cssSource, /\.ch-adv\[hidden\]/, 'the hidden attribute must win over display:block');
  assert.match(cssSource, /\.ch-dec--answered/, 'the decision bars are superseded once an answer renders');
});
