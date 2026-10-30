/**
 * CTR-144/CTR-147 results-cue regression, now a shipped test file.
 *
 * The cue is a small ES5 script with a pure `ns.cue` surface, so the
 * state mapping and dead-link guard can be proved without a browser or a
 * DOM implementation: the script is loaded into a fresh vm context, and
 * minimal node doubles are supplied. The DOM wiring (Observer, render)
 * is not exercised here; it needs a browser and is out of scope.
 *
 * Trevor owns running the suite; this lane leaves the test unexecuted.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const chamberDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'chamber');

function loadCue(): Record<string, any> {
  const source = readFileSync(join(chamberDir, 'chamber-cue.js'), 'utf8');
  const sandbox: Record<string, any> = {};
  sandbox.globalThis = sandbox;
  runInNewContext(source, sandbox);
  return sandbox.councilChamber.cue as Record<string, any>;
}

const shown = (id: string) => ({ id, hidden: false, offsetParent: {}, getClientRects: () => [{}] });
const hidden = (id: string) => ({ id, hidden: true, offsetParent: null, getClientRects: () => [] });
const docOf = (nodes: Record<string, unknown>) => ({
  getElementById: (id: string) => nodes[id] ?? null,
});

test('cue map: idle, active, paused, ready, stopped states', () => {
  const cue = loadCue();
  assert.equal(cue.model(null), null);
  assert.equal(cue.model({}), null);
  for (const status of ['preparing', 'running']) {
    const model = cue.model({ status });
    assert.equal(model.kind, 'active');
    assert.match(model.text, /will appear below/);
    assert.equal(model.linkText, null);
    assert.equal(model.arrow, true);
  }
  assert.equal(cue.model({ status: 'paused', state: 'PAUSED' }).kind, 'paused');
  assert.match(cue.model({ status: 'paused', state: 'PAUSE_REQUESTED' }).text, /pausing/);
  const ready = cue.model({ status: 'complete', state: 'COMPLETED' });
  assert.equal(ready.kind, 'ready');
  assert.equal(ready.text, 'Your results are ready.');
  assert.deepEqual(ready.targets, ['ch-advisory', 'ch-options']);
  assert.equal(ready.arrow, false);
  assert.equal(ready.linkText, 'Read your results');
  for (const status of ['blocked', 'failed', 'cancelled']) {
    const model = cue.model({ status });
    assert.equal(/\bready\b/i.test(model.text), false);
    assert.deepEqual(model.targets, ['ch-room']);
    assert.ok(model.linkText);
  }
  assert.match(cue.model({ status: 'cancelled', state: 'CANCEL_REQUESTED' }).text, /will be produced/);
});

test('cue map: a hidden target is never chosen and no dead link is written', () => {
  const cue = loadCue();
  assert.equal(cue.targetOf(['ch-advisory', 'ch-options'], docOf({ 'ch-advisory': hidden('x') })), null);
  assert.equal(
    cue.targetOf(['ch-advisory', 'ch-options'], docOf({ 'ch-advisory': hidden('x'), 'ch-options': shown('o') })).id,
    'ch-options',
  );
  assert.equal(cue.targetOf(['ch-advisory'], docOf({ 'ch-advisory': shown('a') })).id, 'ch-advisory');
  assert.equal(cue.isShown({ hidden: false, offsetParent: null, getClientRects: () => [] }), false);
});

test('cue is served, in normal flow, and respects reduced motion', () => {
  const html = readFileSync(join(chamberDir, 'index.html'), 'utf8');
  const css = readFileSync(join(chamberDir, 'chamber-cue.css'), 'utf8');
  const door = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'service', 'front-door.ts'),
    'utf8',
  );
  assert.match(html, /href="\.\/chamber-cue\.css"/);
  assert.match(html, /src="\.\/chamber-cue\.js"/);
  assert.ok(html.indexOf('id="ch-results-cue"') > html.indexOf('class="ch-stage-grid"'));
  assert.ok(html.indexOf('id="ch-results-cue"') < html.indexOf('id="ch-options"'));
  assert.ok(html.indexOf('chamber-cue.js') > html.indexOf('chamber-advisory.js'));
  assert.match(door, /\['chamber-cue\.css', 'text\/css; charset=utf-8'\]/);
  assert.match(door, /\['chamber-cue\.js', 'text\/javascript; charset=utf-8'\]/);
  assert.match(css, /prefers-reduced-motion: no-preference/);
  assert.match(css, /prefers-reduced-motion: reduce/);
});
