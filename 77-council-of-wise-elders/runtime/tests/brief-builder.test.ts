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
