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
