#!/usr/bin/env node
// Behavioral checks for the Skill 58 n8n exports (publish rail ZpaoEQrHYtDM49y0).
// Runs the exported Code-node source in-process; no network. Run from the repo root:
//   node 58-podcast-production-engine/scripts/tests/podcast-n8n-rail-fixes.test.js
const fs = require('fs'); const path = require('path'); const assert = require('assert');
const dir = path.join(__dirname, '..', '..', 'config', 'n8n');
function load(f) { const w = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')); return [w, Object.fromEntries(w.nodes.map(n => [n.name, n]))]; }
{ const [w, N] = load('podbean-publish.workflow.json');
function runCode(name, ctx) {
  const f = new Function('$', '$input', 'Date', N[name].parameters.jsCode);
  return f(ctx.$, ctx.$input, ctx.Date || Date);
}
// Idempotency verdict
const verdict = (row, nowIso) => {
  const RealDate = Date; const now = RealDate.parse(nowIso);
  class FakeDate extends RealDate { static now() { return now; } }
  FakeDate.parse = RealDate.parse;
  const out = runCode('Idempotency  --  Determine Verdict', {
    $: () => ({ first: () => ({ json: { body: { idempotency_key: 'k1', podcast_id: 'c', source: 's' } } }) }),
    $input: { all: () => row ? [{ json: row }] : [] }, Date: FakeDate });
  return out[0].json.idempotency_verdict;
};
const t0 = '2026-10-13T10:00:00.000Z';
assert.strictEqual(verdict(null, t0), 'proceed');
assert.strictEqual(verdict({ idempotency_key: 'k1', status: 'completed', permalink_url: 'x' }, t0), 'replay');
assert.strictEqual(verdict({ idempotency_key: 'k1', status: 'in_flight', updatedAt: '2026-10-13T09:55:00.000Z' }, t0), 'in_flight');
assert.strictEqual(verdict({ idempotency_key: 'k1', status: 'in_flight', updatedAt: '2026-10-13T09:30:00.000Z' }, t0), 'in_flight');
assert.strictEqual(verdict({ idempotency_key: 'k1', status: 'in_flight', updatedAt: '2026-10-13T08:30:00.000Z' }, t0), 'proceed');
assert.strictEqual(verdict({ idempotency_key: 'k1', status: 'received', updatedAt: 'garbage' }, t0), 'in_flight');
assert.strictEqual(verdict({ idempotency_key: 'k1', status: 'publishing', updatedAt: '2026-08-05T09:13:08.159Z' }, t0), 'in_flight');
assert.strictEqual(verdict({ idempotency_key: 'k1', status: 'failed' }, t0), 'proceed');
// Readback verdict carries permalink
const rb = runCode('Readback Verdict  --  Assert Media + Description', {
  $: (n) => ({ first: () => n.startsWith('Podbean  --  Publish')
    ? { json: { episode: { id: 'E1', permalink_url: '' } } }
    : { json: { episode: { media_url: 'https://m/x.mp3', logo: 'https://m/x.jpg', content: 'y'.repeat(200), permalink_url: 'https://show.podbean.com/e/x' } } } }),
  $input: { all: () => [] } });
assert.strictEqual(rb[0].json.readback_failed, false);
assert.strictEqual(rb[0].json.readback_permalink_url, 'https://show.podbean.com/e/x');
// Graph checks
const tg = (n, b = 0) => ((w.connections[n] || {}).main || [])[b] ? w.connections[n].main[b].map(x => x.node) : [];
assert.deepStrictEqual(tg('Idempotency  --  Mark Completed'), ['Respond  --  Publish Success']);
assert.ok(!tg('IF  --  Episode Created Successfully').includes('Respond  --  Publish Success'));
assert.ok(!('onError' in N['Idempotency  --  Mark Completed']));
assert.strictEqual(N['Idempotency  --  Mark Completed'].alwaysOutputData, true);
assert.deepStrictEqual(tg('PUT Image  --  Upload to Podbean S3'), ['Idempotency  --  Mark Publishing']);
assert.deepStrictEqual(tg('Idempotency  --  Mark Publishing'), ['Set Upload Keys  --  Assemble Publish Payload']);
const sc = N['Set Config  --  Consolidate Workflow Variables'].parameters.assignments.assignments;
for (const k of ['episode_type', 'explicit']) assert.ok(sc.find(a => a.name === k).value.includes('.item.json.body.' + k));
for (const n of w.nodes) if (n.type.endsWith('.gmail')) assert.strictEqual(n.parameters.sendTo, 'trevor@blackceo.com', n.name);
assert.strictEqual(w.settings.errorWorkflow, 'QMNXZrNvXG0nn2U7');
assert.ok(N['Respond  --  Publish Success'].parameters.responseBody.includes('readback_permalink_url'));
console.log('selftest_rail: all checks passed');
// Permalink falls back to the readback copy (scheduled episodes can return none on create)
const mc = N['Idempotency  --  Mark Completed'].parameters.columns.value;
assert.ok(mc.permalink_url.includes('readback_permalink_url'));
assert.ok(mc.status.includes("'publishing'"));
assert.ok(N['Respond  --  Publish Success'].parameters.responseBody.includes("'permalink_missing'"));
}
