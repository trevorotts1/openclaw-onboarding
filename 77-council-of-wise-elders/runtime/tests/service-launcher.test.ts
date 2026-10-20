/**
 * W27: the canonical service launcher must go through the composition root.
 * A bare CouncilFrontDoor leaves the event, admission and session adapters
 * unbound (events answer 501).
 *
 * Runner: node --import tsx --test tests/service-launcher.test.ts
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(
  new URL('../scripts/service-launch.mjs', import.meta.url),
  'utf8',
).replace(/^\s*\/\/.*$/gm, '');

test('launcher calls the composition root', () => {
  assert.match(source, /\bstartCouncilService\s*\(/);
});

test('launcher never constructs a bare CouncilFrontDoor', () => {
  assert.doesNotMatch(source, /new\s+CouncilFrontDoor\b/);
});

test('launcher passes no fabricated materialCatalog or routeBudget', () => {
  assert.doesNotMatch(source, /materialCatalog\s*:|routeBudget\s*:/);
});

test('launcher hard-codes no operator home path', () => {
  assert.doesNotMatch(source, /\/Users\//);
});

test('launcher loads the composition module inside the try block', () => {
  const tryAt = source.indexOf('try {');
  const importAt = source.indexOf('await import(');
  const catchAt = source.indexOf('front_door_start_failed');
  assert.ok(tryAt >= 0 && importAt > tryAt && importAt < catchAt);
});

test('launcher documents and uses only the tsx run path', () => {
  const raw = readFileSync(new URL('../scripts/service-launch.mjs', import.meta.url), 'utf8');
  assert.match(raw, /node_modules\/tsx\/dist\/cli\.mjs <release>\/scripts\/service-launch\.mjs/);
  assert.doesNotMatch(raw, /node --import tsx runtime\/scripts/);
  assert.doesNotMatch(source, /dist\//);
});
