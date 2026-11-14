import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { makeBox } from './helpers.mjs';

const ctx = { sessionKey: 'lb', runId: 'lb-run' };

test('the same call blocked three times in a row is allowed on the third and logged', () => {
  const box = makeBox();
  try {
    const logs = [];
    const g = box.guard({ log: (l, m) => logs.push(m) });
    const call = { toolName: 'exec', params: { command: `grep foo '${box.p('10-alpha/SKILL.md')}'` } };
    assert.ok(g.beforeToolCall(call, ctx).block);
    assert.ok(g.beforeToolCall(call, ctx).block);
    assert.equal(g.beforeToolCall(call, ctx), undefined);
    assert.ok(logs.some((m) => /loop-breaker/.test(m)));
    const events = fs.readFileSync(path.join(box.state, 'events.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
    assert.ok(events.some((e) => e.kind === 'loop-breaker' && e.repeats === 3));
    // the chain starts over afterwards
    assert.ok(g.beforeToolCall(call, ctx).block);
    assert.ok(g.beforeToolCall(call, ctx).block);
    assert.equal(g.beforeToolCall(call, ctx), undefined);
  } finally { box.cleanup(); }
});

test('a different blocked call in between restarts the count', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const a = { toolName: 'exec', params: { command: `grep foo '${box.p('10-alpha/SKILL.md')}'` } };
    const b = { toolName: 'exec', params: { command: `head -3 '${box.p('20-beta/SKILL.md')}'` } };
    assert.ok(g.beforeToolCall(a, ctx).block);
    assert.ok(g.beforeToolCall(a, ctx).block);
    assert.ok(g.beforeToolCall(b, ctx).block);
    assert.ok(g.beforeToolCall(a, ctx).block); // count restarted at 1
  } finally { box.cleanup(); }
});

test('the repeat count is configurable', () => {
  const box = makeBox();
  try {
    const g = box.guard({ loopBreakerRepeats: 2 });
    const a = { toolName: 'exec', params: { command: `grep foo '${box.p('10-alpha/SKILL.md')}'` } };
    assert.ok(g.beforeToolCall(a, ctx).block);
    assert.equal(g.beforeToolCall(a, ctx), undefined);
  } finally { box.cleanup(); }
});

test('safety valve: after too many blocks in one run the rest of the run is allowed', () => {
  const box = makeBox();
  try {
    const logs = [];
    const g = box.guard({ maxBlocksPerRun: 4, loopBreakerRepeats: 50, log: (l, m) => logs.push(m) });
    const results = [];
    for (let i = 0; i < 7; i++) {
      results.push(!!(g.beforeToolCall({ toolName: 'exec', params: { command: `grep w${i} '${box.p('10-alpha/SKILL.md')}'` } }, ctx) || {}).block);
    }
    assert.deepEqual(results, [true, true, true, true, false, false, false]);
    assert.ok(logs.some((m) => /passed 4 blocks/.test(m)));
    // a new run starts fresh
    assert.ok(g.beforeToolCall({ toolName: 'exec', params: { command: `grep z '${box.p('10-alpha/SKILL.md')}'` } }, { sessionKey: 'lb', runId: 'other-run' }).block);
  } finally { box.cleanup(); }
});

test('sessions do not share a chain', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const a = { toolName: 'exec', params: { command: `grep foo '${box.p('10-alpha/SKILL.md')}'` } };
    assert.ok(g.beforeToolCall(a, { sessionKey: 'one', runId: 'r1' }).block);
    assert.ok(g.beforeToolCall(a, { sessionKey: 'one', runId: 'r1' }).block);
    assert.ok(g.beforeToolCall(a, { sessionKey: 'two', runId: 'r2' }).block);
  } finally { box.cleanup(); }
});
