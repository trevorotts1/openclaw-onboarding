import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { makeBox } from './helpers.mjs';
import { loadManifest, isInstructionByName, globHitsInstructionNames, makeMatcher } from '../dist/index.js';

test('instruction names are never lookup, markdown defaults to instruction, code and data to lookup', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const c = (rel) => g.classifier.classify(box.p(rel));
    for (const rel of ['10-alpha/SKILL.md', '10-alpha/INSTRUCTIONS.md', '10-alpha/references/procedure.md', '20-beta/notes.md']) {
      const r = c(rel);
      assert.equal(r.scope, 'skill', rel);
      assert.equal(r.cls, 'instruction', rel);
    }
    for (const rel of ['10-alpha/scripts/run.sh', '10-alpha/scripts/run.py', '10-alpha/data/x.json', '10-alpha/models.json', '10-alpha/references/api.md', '10-alpha/notes/extra.md']) {
      assert.equal(c(rel).cls, 'lookup', rel);
    }
  } finally { box.cleanup(); }
});

test('manifest lookup, frontmatter lookup and default directories all exempt', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    assert.equal(g.classifier.classifyRel('10-alpha', 'references/api.md').reason, 'manifest lookup');
    assert.equal(g.classifier.classifyRel('10-alpha', 'notes/extra.md').cls, 'lookup'); // frontmatter lookup: [notes/*.md]
    assert.equal(g.classifier.classifyRel('85-docs', 'articles/a1.md').cls, 'lookup');
    assert.equal(g.classifier.classifyRel('30-gamma', 'tests/anything.md').cls, 'lookup'); // default dir
    assert.equal(g.classifier.classifyRel('30-gamma', 'CHANGELOG.md').cls, 'lookup'); // default file
  } finally { box.cleanup(); }
});

test('there is no size rule: a huge markdown file and a tiny one are both instruction', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    assert.equal(g.classifier.classify(box.p('40-big/SKILL.md')).cls, 'instruction');
    box.w('30-gamma/huge.md', 'x'.repeat(2_000_000));
    box.w('30-gamma/tiny.md', 'x');
    assert.equal(g.classifier.classify(box.p('30-gamma/huge.md')).cls, 'instruction');
    assert.equal(g.classifier.classify(box.p('30-gamma/tiny.md')).cls, 'instruction');
  } finally { box.cleanup(); }
});

test('SOP files are instruction; the SOP library root is not a skill', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const r = g.classifier.classify(box.p('universal-sops/sop/SOP-1.md'));
    assert.equal(r.scope, 'skill');
    assert.equal(r.skill, 'universal-sops');
    assert.equal(r.cls, 'instruction');
  } finally { box.cleanup(); }
});

test('skill name resolution: folder, number, bare name, frontmatter name, case', () => {
  const box = makeBox();
  try {
    const idx = box.guard().index;
    for (const q of ['10-alpha', '10', 'alpha', 'Alpha', 'ALPHA', ' 10-alpha/ ']) assert.equal(idx.resolve(q), '10-alpha', q);
    assert.equal(idx.resolve('99'), undefined);
    assert.equal(idx.resolve('nope'), undefined);
  } finally { box.cleanup(); }
});

test('workspace-skill virtual paths resolve to the skill folder', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const r = g.classifier.classify('workspace-skill://workspace/alpha/SKILL.md');
    assert.equal(r.scope, 'skill');
    assert.equal(r.skill, '10-alpha');
    assert.equal(r.rel, 'SKILL.md');
    const r2 = g.classifier.classify('workspace-skill://workspace/10-alpha/references/procedure.md');
    assert.equal(r2.rel, 'references/procedure.md');
    assert.equal(g.classifier.classify('workspace-skill://workspace/unknown/SKILL.md').scope, 'outside');
  } finally { box.cleanup(); }
});

test('relative paths resolve against the working directories; tail match finds copied paths', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    assert.equal(g.classifier.classify('SKILL.md', [box.p('10-alpha')]).skill, '10-alpha');
    assert.equal(g.classifier.classify('10-alpha/SKILL.md', [box.skills]).skill, '10-alpha');
    // a path that only shares the tail with the real tree
    assert.equal(g.classifier.classify('/somewhere/else/skills/10-alpha/SKILL.md').skill, '10-alpha');
    assert.equal(g.classifier.classify('/somewhere/else/skills/10-alpha/does-not-exist.md').scope, 'outside');
  } finally { box.cleanup(); }
});

test('symlinks are resolved before classification', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const link = path.join(box.root, 'link-to-skill.md');
    fs.symlinkSync(box.p('10-alpha/SKILL.md'), link);
    const r = g.classifier.classify(link);
    assert.equal(r.scope, 'skill');
    assert.equal(r.skill, '10-alpha');
    assert.equal(r.cls, 'instruction');
  } finally { box.cleanup(); }
});

test('files outside the skills tree are outside; external lookup roots are lookup', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    assert.equal(g.classifier.classify(path.join(box.root, 'notes.md')).scope, 'outside');
    const ext = g.classifier.classify(path.join(box.ext, 'sub', 'x.md'));
    assert.equal(ext.scope, 'external');
    assert.equal(ext.cls, 'lookup');
  } finally { box.cleanup(); }
});

test('hard rule: a shard cannot turn an instruction file into lookup', () => {
  const box = makeBox([['evil.json', { version: 1, skills: [{ skill: '30-gamma', lookup: [{ glob: 'SKILL.md' }, { glob: '*.md' }, { glob: '**' }, { glob: '*-full.md' }, { glob: 'ok/**' }] }] }]]);
  try {
    const m = loadManifest(box.manifestDir);
    assert.ok(m.errors.length >= 4, m.errors.join('\n'));
    assert.deepEqual(m.skills.get('30-gamma').lookup.map((r) => r.glob), ['ok/**']);
    const g = box.guard();
    assert.equal(g.classifier.classify(box.p('30-gamma/SKILL.md')).cls, 'instruction');
  } finally { box.cleanup(); }
});

test('hard rule helpers', () => {
  assert.ok(isInstructionByName('SKILL.md'));
  assert.ok(isInstructionByName('README.md'));
  assert.ok(isInstructionByName('thing-full.md'));
  assert.ok(!isInstructionByName('references/README.md'));
  assert.ok(!isInstructionByName('references/thing-full.md'));
  assert.deepEqual(globHitsInstructionNames('models.json'), []);
  assert.ok(globHitsInstructionNames('*.md').includes('SKILL.md'));
  assert.ok(makeMatcher(['references/*.md'])('references/a.md'));
  assert.ok(!makeMatcher(['references/*.md'])('references/sub/a.md'));
  assert.ok(makeMatcher(['a/**'])('a/b/c.md'));
  assert.ok(makeMatcher(['**/x.md'])('x.md'));
  assert.ok(makeMatcher(['{a,b}/**'])('b/z'));
});
