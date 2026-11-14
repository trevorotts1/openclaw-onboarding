import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { makeBox, verdict, reasonOf, HERE } from './helpers.mjs';

const ctx = (k) => ({ sessionKey: k, runId: 'run-' + k });

test('ranged read of an instruction file is rewritten to a whole-file read', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const r = g.beforeToolCall({ toolName: 'read', params: { path: box.p('10-alpha/SKILL.md'), offset: 5, limit: 10 } }, ctx('a'));
    assert.deepEqual(r.params, { path: box.p('10-alpha/SKILL.md') });
    const r2 = g.beforeToolCall({ toolName: 'read', params: { file_path: box.p('10-alpha/SKILL.md'), cursor: 20, optional: true } }, ctx('a'));
    assert.deepEqual(r2.params, { file_path: box.p('10-alpha/SKILL.md'), optional: true });
    const r3 = g.beforeToolCall({ toolName: 'read', params: { path: 'workspace-skill://workspace/alpha/SKILL.md', offset: 2 } }, ctx('a'));
    assert.deepEqual(r3.params, { path: 'workspace-skill://workspace/alpha/SKILL.md' });
  } finally { box.cleanup(); }
});

test('plain reads, lookup reads and outside reads pass untouched', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    assert.equal(verdict(g, 'read', { path: box.p('10-alpha/SKILL.md') }), 'allow');
    assert.equal(verdict(g, 'read', { path: box.p('10-alpha/references/api.md'), offset: 3, limit: 4 }), 'allow');
    assert.equal(verdict(g, 'read', { path: box.p('10-alpha/data/x.json'), offset: 1, limit: 1 }), 'allow');
    assert.equal(verdict(g, 'read', { path: path.join(box.root, 'elsewhere.md'), offset: 3 }), 'allow');
    assert.equal(verdict(g, 'read', {}), 'allow');
  } finally { box.cleanup(); }
});

test('an instruction file too large for one read call is blocked and pointed to read_skill', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    assert.equal(verdict(g, 'read', { path: box.p('40-big/SKILL.md') }), 'block');
    const reason = reasonOf(g, 'read', { path: box.p('40-big/SKILL.md'), offset: 100, limit: 50 });
    assert.match(reason, /read_skill/);
    assert.match(reason, /40-big/);
  } finally { box.cleanup(); }
});

test('read_skill itself is never blocked; unrelated tools are untouched', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    assert.equal(verdict(g, 'read_skill', { skill: '10-alpha' }), 'allow');
    assert.equal(verdict(g, 'web_fetch', { url: 'x' }), 'allow');
    assert.equal(verdict(g, 'write', { path: box.p('10-alpha/SKILL.md'), content: 'x' }), 'allow');
  } finally { box.cleanup(); }
});

test('block reasons are plain and name read_skill and the skill', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const r = reasonOf(g, 'exec', { command: `grep foo '${box.p('10-alpha/SKILL.md')}'` });
    assert.match(r, /Full-Read Guard/);
    assert.match(r, /read_skill/);
    assert.match(r, /10-alpha/);
    assert.match(r, /may be searched/);
    const sop = reasonOf(g, 'exec', { command: `head -3 '${box.p('universal-sops/sop/SOP-1.md')}'` });
    assert.match(sop, /whole file/);
  } finally { box.cleanup(); }
});

test('gate: running a skill script needs the skill AND its direct dependencies read this session', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const key = 'gate-1';
    const run = () => g.beforeToolCall({ toolName: 'exec', params: { command: `bash '${box.p('10-alpha/scripts/run.sh')}'` } }, ctx(key));
    assert.ok(run().block);
    // reading only the skill's own files with whole-file reads is not enough: dependencies are missing
    for (const rel of ['10-alpha/SKILL.md', '10-alpha/INSTRUCTIONS.md']) {
      g.afterToolCall({ toolName: 'read', params: { path: box.p(rel) }, result: { content: [{ type: 'text', text: 'ok' }] } }, ctx(key));
    }
    const still = run();
    assert.ok(still.block);
    for (const rel of ['20-beta/SKILL.md', 'universal-sops/sop/SOP-1.md', 'universal-sops/sop/SOP-2.md']) {
      g.afterToolCall({ toolName: 'read', params: { path: box.p(rel) }, result: { content: [{ type: 'text', text: 'ok' }] } }, ctx(key));
    }
    assert.equal(run(), undefined);
    // another session has no receipt
    assert.ok(g.beforeToolCall({ toolName: 'exec', params: { command: `bash '${box.p('10-alpha/scripts/run.sh')}'` } }, ctx('other-session')).block);
  } finally { box.cleanup(); }
});

test('gate: read_skill satisfies the gate in one step', () => {
  const box = makeBox();
  try {
    const g = box.guard({ chunkChars: 500 });
    const key = 'gate-2';
    const parts = g.readSkill.run('10-alpha', 1, key).details.parts;
    for (let p = 2; p <= parts; p++) g.readSkill.run('10-alpha', p, key);
    assert.equal(g.beforeToolCall({ toolName: 'exec', params: { command: `bash '${box.p('10-alpha/scripts/run.sh')}'` } }, ctx(key)), undefined);
  } finally { box.cleanup(); }
});

test('after_tool_call: truncated or ranged reads give no receipt', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const key = 'gate-3';
    const abs = g.classifier.classify(box.p('20-beta/SKILL.md')).abs;
    g.afterToolCall({ toolName: 'read', params: { path: box.p('20-beta/SKILL.md'), offset: 2 }, result: {} }, ctx(key));
    assert.equal(g.receipts.hasFile(key, abs), false);
    g.afterToolCall({ toolName: 'read', params: { path: box.p('20-beta/SKILL.md') }, result: { details: { kind: 'truncated' } } }, ctx(key));
    assert.equal(g.receipts.hasFile(key, abs), false);
    g.afterToolCall({ toolName: 'read', params: { path: box.p('20-beta/SKILL.md') }, error: 'boom' }, ctx(key));
    assert.equal(g.receipts.hasFile(key, abs), false);
    g.afterToolCall({ toolName: 'read', params: { path: box.p('20-beta/SKILL.md') }, result: { content: [{ type: 'text', text: 'whole' }] } }, ctx(key));
    assert.equal(g.receipts.hasFile(key, abs), true);
  } finally { box.cleanup(); }
});

test('modes: audit logs but never blocks or rewrites; off does nothing; enforce is the default', () => {
  const box = makeBox();
  try {
    const logs = [];
    const cmd = { command: `grep foo '${box.p('10-alpha/SKILL.md')}'` };
    const audit = box.guard({ env: { HOME: box.root, OPENCLAW_FRG_MODE: 'audit' }, log: (l, m) => logs.push(m) });
    assert.equal(audit.mode, 'audit');
    assert.equal(verdict(audit, 'exec', cmd), 'allow');
    assert.equal(verdict(audit, 'read', { path: box.p('10-alpha/SKILL.md'), offset: 3 }), 'allow');
    assert.ok(logs.some((m) => /would block/.test(m)));
    assert.equal(box.guard({ mode: 'off' }).mode, 'off');
    assert.equal(verdict(box.guard({ mode: 'off' }), 'exec', cmd), 'allow');
    assert.equal(box.guard().mode, 'enforce');
    assert.equal(box.guard({ mode: 'bogus' }).mode, 'enforce');
  } finally { box.cleanup(); }
});

test('fail open: an internal error never blocks and is logged', () => {
  const box = makeBox();
  try {
    const logs = [];
    const g = box.guard({ log: (l, m) => logs.push(m) });
    const evil = { toolName: 'read', get params() { throw new Error('boom'); } };
    assert.equal(g.beforeToolCall(evil, ctx('f')), undefined);
    assert.ok(logs.some((m) => /fail-open/.test(m)));
    assert.equal(g.beforeToolCall(null, ctx('f')), undefined);
  } finally { box.cleanup(); }
});

test('recorded-shape events: fixtures behave as the schema says', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const dir = path.join(HERE, 'fixtures', 'events');
    const load = (n) => {
      const raw = fs.readFileSync(path.join(dir, n), 'utf8').split('{{SKILLS}}').join(box.skills);
      const j = JSON.parse(raw);
      return g.beforeToolCall(j.event, { ...j.ctx, sessionKey: 'fx-' + n });
    };
    assert.equal(load('read-whole.json'), undefined);
    assert.deepEqual(Object.keys(load('read-ranged.json').params), ['path']);
    assert.deepEqual(Object.keys(load('read-cursor.json').params), ['path']);
    assert.equal(load('read-optional.json'), undefined);
    assert.deepEqual(Object.keys(load('read-workspace-skill.json').params), ['path']);
    assert.equal(load('read-lookup.json'), undefined);
    assert.ok(load('exec-grep.json').block);
    assert.ok(load('exec-run-script.json').block);
    assert.ok(load('exec-cd-then-run.json').block);
  } finally { box.cleanup(); }
});

test('read-on-open: step files are not required upfront but are protected when opened', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const key = 'oo-1';
    const run = () => g.beforeToolCall({ toolName: 'exec', params: { command: `bash '${box.p('10-alpha/scripts/run.sh')}'` } }, ctx(key));
    for (const rel of ['10-alpha/SKILL.md', '10-alpha/INSTRUCTIONS.md', '20-beta/SKILL.md', 'universal-sops/sop/SOP-1.md', 'universal-sops/sop/SOP-2.md']) {
      g.afterToolCall({ toolName: 'read', params: { path: box.p(rel) }, result: { content: [{ type: 'text', text: 'ok' }] } }, ctx(key));
    }
    assert.equal(run(), undefined); // procedure.md and INSTALL.md were never read, yet the gate is satisfied
    const step = box.p('10-alpha/references/procedure.md');
    const install = box.p('10-alpha/INSTALL.md');
    assert.equal(verdict(g, 'read', { path: step }, ctx('oo-2')), 'allow'); // whole read of a step file is fine
    assert.equal(verdict(g, 'read', { path: step, offset: 3, limit: 4 }, ctx('oo-2')), 'rewrite');
    assert.equal(verdict(g, 'read', { path: install, limit: 2 }, ctx('oo-2')), 'rewrite');
    assert.equal(verdict(g, 'exec', { command: `grep -n step '${step}'` }, ctx('oo-3')), 'block');
    assert.equal(verdict(g, 'exec', { command: `head -3 '${install}'` }, ctx('oo-4')), 'block');
    assert.equal(g.classifier.classifyRel('10-alpha', 'references/procedure.md').upfront, false);
    assert.equal(g.classifier.classifyRel('10-alpha', 'INSTALL.md').upfront, false);
    assert.equal(g.classifier.classifyRel('10-alpha', 'INSTALL.md').cls, 'instruction');
    assert.equal(g.classifier.classifyRel('10-alpha', 'SKILL.md').upfront, true);
    assert.equal(g.classifier.classifyRel('10-alpha', 'notes.md').upfront, true);
  } finally { box.cleanup(); }
});

test('a direct dependency needs only its SKILL.md upfront; its other root docs are read-on-open but still protected', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const req = g.closure.requiredFiles('10-alpha').files.map((f) => `${f.skill}/${f.rel}`);
    assert.ok(req.includes('20-beta/SKILL.md'));
    assert.ok(!req.includes('20-beta/notes.md'));
    assert.ok(req.includes('10-alpha/INSTRUCTIONS.md')); // the skill in use keeps its full root set
    assert.equal(verdict(g, 'exec', { command: `grep -n beta '${box.p('20-beta/notes.md')}'` }, ctx('dep-1')), 'block');
    assert.equal(verdict(g, 'read', { path: box.p('20-beta/notes.md'), limit: 2 }, ctx('dep-1')), 'rewrite');
  } finally { box.cleanup(); }
});
