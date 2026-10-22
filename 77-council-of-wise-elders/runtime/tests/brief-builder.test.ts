/**
 * W74-C runnable check: fixture memory files -> the assembled brief.
 *
 * Proves, on BOTH doors (the OpenClaw door and the 999 / claude-nine
 * door), that the shared permitted-context brief builder:
 * - contains the decision-relevant fact (never a file dump),
 * - EXCLUDES the irrelevant private detail (private stays in the
 *   private store) and the irrelevant permitted detail,
 * - follows pointer docs at most one hop (recursion never),
 * - respects the size cap, and
 * - marks unknowns explicitly.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  BRIEF_WORD_CAP,
  assembleBrief,
  collectPermittedDocuments,
  type DoorKind,
  type PermittedContextBrief,
} from '../src/brief/permitted-brief.js';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'brief-builder');
const DOOR_DIRS: Record<DoorKind, string> = {
  openclaw: 'openclaw-door',
  'claude-nine': 'claude-nine-door',
};
const DOORS: readonly DoorKind[] = ['openclaw', 'claude-nine'];
const DECISION = 'Should the company open a second office in Austin this year?';
const OPTIONS = ['open the Austin office in Q3', 'wait until next year'];

function build(door: DoorKind, wordCap?: number): PermittedContextBrief {
  return assembleBrief({
    door,
    rootDir: join(FIXTURES, DOOR_DIRS[door]),
    decision: DECISION,
    options: OPTIONS,
    ...(wordCap === undefined ? {} : { wordCap }),
  });
}

function dump(brief: PermittedContextBrief): string {
  return JSON.stringify(brief);
}

test('decision-relevant facts in, irrelevant and private detail out (both doors)', () => {
  for (const door of DOORS) {
    const brief = build(door);
    const text = dump(brief);
    // In: the decision-relevant facts from root and one-hop pointer docs.
    assert.ok(text.includes('Austin lease offer is $8,200 per month'), `${door}: lease fact missing`);
    assert.ok(text.includes('$140,000 in reserve'), `${door}: one-hop runway fact missing`);
    // Out: the irrelevant private detail (private stays in the private store),
    // the irrelevant permitted detail, and the two-hop trap fact.
    assert.ok(!text.includes('home renovation'), `${door}: private detail leaked`);
    assert.ok(!text.includes('Fifth Street'), `${door}: private detail leaked`);
    assert.ok(!text.includes('dental clinic'), `${door}: private store leaked`);
    assert.ok(!text.includes('Blue Train'), `${door}: irrelevant detail not excluded`);
    assert.ok(!text.includes('board already approved'), `${door}: two-hop doc was followed`);
    // One hop exactly: the pointer doc is read, the trap doc never is.
    assert.ok(brief.meta.sources_read.includes('runway.md') || brief.meta.sources_read.includes('memory/runway.md'),
      `${door}: one-hop pointer doc not read`);
    assert.ok(!brief.meta.sources_read.some((p) => p.includes('deep.md')), `${door}: recursion happened`);
    assert.ok(!brief.meta.sources_read.some((p) => p.includes('private')), `${door}: private path read`);
    // The opaque preference handle carries no content.
    assert.ok(brief.private_preference_ref !== null, `${door}: private handle missing`);
    assert.ok(!/renovation|Fifth|dental/.test(brief.private_preference_ref), `${door}: handle carries content`);
  }
});

test('size cap respected (both doors)', () => {
  assert.equal(BRIEF_WORD_CAP, 2000);
  for (const door of DOORS) {
    const natural = build(door);
    assert.equal(natural.meta.word_cap, 2000, `${door}: wrong cap`);
    assert.ok(natural.meta.word_count <= natural.meta.word_cap, `${door}: over cap`);
    // Forced small cap: the cap still holds, truncation is marked.
    const tight = build(door, 40);
    assert.equal(tight.meta.truncated, true, `${door}: truncation not marked`);
    assert.ok(tight.meta.word_count <= 40, `${door}: over forced cap`);
    assert.ok(tight.unknowns.some((u) => /omitted under the brief word cap/.test(u)),
      `${door}: omitted items not marked`);
  }
});

test('unknowns marked explicitly (both doors)', () => {
  for (const door of DOORS) {
    const brief = build(door);
    assert.ok(brief.unknowns.some((u) => /not yet known/.test(u)), `${door}: explicit unknown missing`);
    // Constraints that the permitted context states are kept as constraints.
    assert.ok(brief.constraints.some((c) => /cannot open before the September cohort/.test(c)),
      `${door}: constraint lost`);
    // No options given and none in context -> the gap is an explicit unknown.
    const noOptions = assembleBrief({
      door,
      rootDir: join(FIXTURES, DOOR_DIRS[door]),
      decision: DECISION,
    });
    assert.ok(noOptions.unknowns.some((u) => /real options are not stated/.test(u)),
      `${door}: options gap not marked`);
    assert.equal(noOptions.options.length, 0, `${door}: options invented`);
  }
});

test('identical brief shape regardless of door', () => {
  const a = build('openclaw');
  const b = build('claude-nine');
  assert.equal(a.schema, b.schema);
  assert.deepEqual(Object.keys(a).sort(), Object.keys(b).sort());
  assert.deepEqual(Object.keys(a.meta).sort(), Object.keys(b.meta).sort());
  for (const key of Object.keys(a) as Array<keyof PermittedContextBrief>) {
    assert.equal(typeof a[key], typeof b[key], `field ${key} differs in type`);
  }
  // Same facts land in the brief from either door.
  const aText = dump(a);
  const bText = dump(b);
  for (const fact of ['Austin lease offer is $8,200 per month', '$140,000 in reserve']) {
    assert.ok(aText.includes(fact), `openclaw: ${fact} missing`);
    assert.ok(bText.includes(fact), `claude-nine: ${fact} missing`);
  }
});

test('permitted context only: adapters read root files plus one hop, nothing else', () => {
  for (const door of DOORS) {
    const docs = collectPermittedDocuments(door, join(FIXTURES, DOOR_DIRS[door]));
    const rels = docs.map((d) => d.rel).sort();
    for (const rel of rels) {
      assert.ok(!rel.includes('private'), `${door}: private path read: ${rel}`);
      assert.ok(!rel.includes('deep.md'), `${door}: beyond one hop: ${rel}`);
    }
    assert.ok(docs.some((d) => d.depth === 1), `${door}: no one-hop doc read`);
  }
});

// ------------------------------------------------ W80 R2: the drop ladder
//
// The 2000-word cap holds across the WHOLE emitted brief (decision,
// options, constraints, facts, unknowns), `truncated` is accurate on
// every trimming path including the decision clip, and the priority
// order is honored: facts fall off first, then constraints, then
// options, then unknowns; the decision clips last.

function tmpContextRoot(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), 'cwe-r2-root-'));
  for (const [rel, text] of Object.entries(files)) {
    const abs = join(root, rel);
    mkdirSync(dirname(abs), { recursive: true });
    writeFileSync(abs, text);
  }
  return root;
}

function emittedWordCount(brief: PermittedContextBrief): number {
  return [brief.decision, ...brief.options, ...brief.constraints,
    ...brief.facts.map((f) => f.statement), ...brief.unknowns]
    .join(' ').split(/\s+/).filter(Boolean).length;
}

test('cap case (a): oversized unknowns are trimmed, brief stays under cap, truncated=true', () => {
  const lines = Array.from({ length: 260 }, (_, i) =>
    `- item ${i} is unknown pending review of the Austin office timeline`);
  const rootDir = tmpContextRoot({ 'CLAUDE.md': `# memory\n${lines.join('\n')}\n` });

  // Untrimmed reference: what the cap has to bite.
  const untrimmed = assembleBrief({ door: 'claude-nine', rootDir, decision: DECISION, wordCap: 100_000 });
  assert.ok(untrimmed.unknowns.length > 250, `setup: expected many unknowns, got ${untrimmed.unknowns.length}`);
  assert.ok(emittedWordCount(untrimmed) > BRIEF_WORD_CAP, 'setup: brief should overflow the cap');

  const brief = assembleBrief({ door: 'claude-nine', rootDir, decision: DECISION });
  assert.ok(brief.meta.word_count <= BRIEF_WORD_CAP, `over cap: ${brief.meta.word_count}`);
  assert.ok(emittedWordCount(brief) <= BRIEF_WORD_CAP, `emitted text over cap: ${emittedWordCount(brief)}`);
  assert.equal(brief.meta.truncated, true, 'unknowns were trimmed: truncated must be true');
  // The drop ladder trims unknowns (not just their tail note).
  assert.ok(brief.unknowns.length < untrimmed.unknowns.length, 'unknowns were not trimmed');
  // Priority order: the surviving unknowns are the leading ones.
  assert.deepEqual(
    brief.unknowns.slice(0, -1),
    untrimmed.unknowns.slice(0, brief.unknowns.length - 1),
    'surviving unknowns must be the leading ones',
  );
  // The omission note is appended and counts toward the cap.
  assert.match(brief.unknowns.at(-1) ?? '', /omitted under the brief word cap/);
});

test('cap case (b): oversized decision is clipped, brief stays under cap, truncated=true', () => {
  const longDecision = Array.from({ length: 5000 }, (_, i) => `word${i}`).join(' ');
  const rootDir = tmpContextRoot({ 'CLAUDE.md': '# memory\n' });

  const brief = assembleBrief({ door: 'claude-nine', rootDir, decision: longDecision });
  assert.ok(brief.meta.word_count <= BRIEF_WORD_CAP, `over cap: ${brief.meta.word_count}`);
  assert.ok(emittedWordCount(brief) <= BRIEF_WORD_CAP, `emitted text over cap: ${emittedWordCount(brief)}`);
  // The decision-clip path also marks truncation.
  assert.equal(brief.meta.truncated, true, 'decision was clipped: truncated must be true');
  // The clip is a prefix cut, never a rewording.
  assert.ok(longDecision.startsWith(brief.decision), 'clipped decision must be a prefix of the original');
  assert.ok(brief.decision.length < longDecision.length, 'decision was not clipped');
});

test('cap case (c): mixed oversized brief stays under cap, priority order honored, truncated=true', () => {
  const facts = Array.from({ length: 60 }, (_, i) =>
    `- Austin office fact ${i} ${'filler '.repeat(20).trim()}`);
  const rootDir = tmpContextRoot({
    'CLAUDE.md': [
      '# memory',
      ...facts,
      '- Constraint: the second office cannot open before the September cohort ends.',
      '- Constraint: the Austin budget cap is fixed for this year.',
      '- Constraint: no lease signing until the reserve is confirmed.',
      '- option 1: open the Austin office in Q3',
      '- option 2: wait until next year',
      '- item 7 is unknown pending review of the Austin timeline.',
      '- item 8 is unknown pending review of the Austin timeline.',
    ].join('\n'),
  });
  const wordCap = 300;

  const untrimmed = assembleBrief({ door: 'claude-nine', rootDir, decision: DECISION, wordCap: 100_000 });
  const brief = assembleBrief({ door: 'claude-nine', rootDir, decision: DECISION, wordCap });

  assert.ok(brief.meta.word_count <= wordCap, `over cap: ${brief.meta.word_count}`);
  assert.ok(emittedWordCount(brief) <= wordCap, `emitted text over cap: ${emittedWordCount(brief)}`);
  assert.equal(brief.meta.truncated, true, 'items were dropped: truncated must be true');

  // Priority order: facts fall off first and least-relevant first.
  assert.ok(brief.facts.length < untrimmed.facts.length, 'facts were not the first to go');
  assert.deepEqual(brief.facts, untrimmed.facts.slice(0, brief.facts.length), 'surviving facts must be the leading ones');
  // Constraints and options are only touched after facts are exhausted.
  assert.deepEqual(brief.constraints, untrimmed.constraints, 'constraints must survive while facts drop');
  assert.deepEqual(brief.options, untrimmed.options, 'options must survive while facts drop');
  // Unknowns survive in full; the omission note marks the dropped facts.
  assert.deepEqual(brief.unknowns.slice(0, -1), untrimmed.unknowns, 'unknowns must survive while facts drop');
  assert.match(brief.unknowns.at(-1) ?? '', /omitted under the brief word cap/);
});

test('cap case (d): below-cap brief is byte-preserved, truncated=false', () => {
  const rootDir = join(FIXTURES, DOOR_DIRS['openclaw']);
  const brief = build('openclaw');
  const untrimmed = assembleBrief({
    door: 'openclaw',
    rootDir,
    decision: DECISION,
    options: OPTIONS,
    wordCap: 100_000,
  });

  assert.ok(brief.meta.word_count < BRIEF_WORD_CAP, `expected a brief under the cap, got ${brief.meta.word_count}`);
  assert.equal(brief.meta.truncated, false, 'nothing was trimmed: truncated must be false');
  // Byte-preserved: identical content to an uncapped build, no omission note.
  assert.equal(brief.decision, untrimmed.decision);
  assert.deepEqual(brief.options, untrimmed.options);
  assert.deepEqual(brief.constraints, untrimmed.constraints);
  assert.deepEqual(brief.facts, untrimmed.facts);
  assert.deepEqual(brief.unknowns, untrimmed.unknowns);
});
