import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { makeBox } from './helpers.mjs';
import { Receipts } from '../dist/index.js';

function readAll(g, skill, key) {
  const n = g.readSkill.run(skill, 1, key).details.parts;
  for (let p = 2; p <= n; p++) g.readSkill.run(skill, p, key);
}

test('receipts are per session', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    readAll(g, '30-gamma', 'A');
    const abs = g.classifier.classify(box.p('30-gamma/SKILL.md')).abs;
    assert.equal(g.receipts.hasFile('A', abs), true);
    assert.equal(g.receipts.hasFile('B', abs), false);
  } finally { box.cleanup(); }
});

test('stale hash: a changed file voids its receipt', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    readAll(g, '30-gamma', 'A');
    const abs = g.classifier.classify(box.p('30-gamma/SKILL.md')).abs;
    assert.equal(g.receipts.hasFile('A', abs), true);
    fs.appendFileSync(abs, 'changed on disk\n');
    assert.equal(g.receipts.hasFile('A', abs), false);
  } finally { box.cleanup(); }
});

test('reset on session start, session end and compaction clears receipts and in-use marks', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const abs = g.classifier.classify(box.p('30-gamma/SKILL.md')).abs;
    for (const [name, ctx] of [['start', { sessionKey: 'S1' }], ['end', { sessionKey: 'S1', sessionId: 'id1' }], ['compaction', { sessionKey: 'S1' }]]) {
      readAll(g, '30-gamma', 'S1');
      assert.equal(g.receipts.hasFile('S1', abs), true, name);
      g.resetSession(ctx);
      assert.equal(g.receipts.hasFile('S1', abs), false, name);
      assert.deepEqual(g.receipts.inUse('S1'), [], name);
    }
    readAll(g, '30-gamma', 'id9');
    g.resetSession({ sessionId: 'id9' });
    assert.equal(g.receipts.hasFile('id9', abs), false);
  } finally { box.cleanup(); }
});

test('after a reset the gate demands the read again', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const run = () => g.beforeToolCall({ toolName: 'exec', params: { command: `bash '${box.p('30-gamma/scripts/go.sh')}'` } }, { sessionKey: 'R', runId: 'r-' + Math.random() });
    assert.ok(run().block);
    readAll(g, '30-gamma', 'R');
    assert.equal(run(), undefined);
    g.resetSession({ sessionKey: 'R' });
    assert.ok(run().block);
  } finally { box.cleanup(); }
});

test('mirror to disk: a new process (new store on the same state directory) sees the receipts', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    readAll(g, '30-gamma', 'persist/key:1');
    const abs = g.classifier.classify(box.p('30-gamma/SKILL.md')).abs;
    const files = fs.readdirSync(box.state).filter((f) => f.endsWith('.json'));
    assert.ok(files.length >= 1);
    const again = new Receipts(box.state);
    assert.equal(again.hasFile('persist/key:1', abs), true);
    again.reset('persist/key:1');
    assert.equal(new Receipts(box.state).hasFile('persist/key:1', abs), false);
  } finally { box.cleanup(); }
});

test('an unwritable state directory never breaks receipts (memory stays authoritative)', () => {
  const box = makeBox();
  try {
    const blocker = path.join(box.root, 'file-not-dir');
    fs.writeFileSync(blocker, 'x');
    const g = box.guard({ stateDir: path.join(blocker, 'sub') });
    readAll(g, '30-gamma', 'W');
    const abs = g.classifier.classify(box.p('30-gamma/SKILL.md')).abs;
    assert.equal(g.receipts.hasFile('W', abs), true);
  } finally { box.cleanup(); }
});
