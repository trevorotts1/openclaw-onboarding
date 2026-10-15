/**
 * CWE-045: tests for the Skill 22 persona-category registry
 * procedure tool (register-skill22-personas.mjs). Run with:
 *   node --test scripts/register-skill22-personas.test.mjs
 * The fixtures under scripts/fixtures/skill22-registry are minimal
 * but shape-faithful: one seat already registered in the seed, one
 * seat with a present work the seed lacks, one seat whose works are
 * all absent, and six seats with no works at all.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  buildStaging,
  checkStaging,
  personaKey,
} from './register-skill22-personas.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, 'fixtures', 'skill22-registry');
const seed = JSON.parse(readFileSync(join(fixtures, 'seed.json'), 'utf8'));

test('buildStaging accounts for every seat exactly once, honestly', () => {
  const staging = buildStaging(join(fixtures, 'exports'), seed);
  assert.equal(staging.schema, 'wise-elders.persona-registry-staging/v1');
  const byKey = new Map(staging.entries.map((entry) => [entry.key, entry]));
  // The seed already carries this persona: recorded, no change proposed.
  const sinek = byKey.get('sinek-start-with-why');
  assert.equal(sinek.disposition, 'already_registered');
  assert.equal(sinek.provenance.council_seat_id, 'simon-sinek');
  // A present work the seed lacks: proposed with empty tags, never invented.
  const brown = byKey.get('brown-live-your-dreams');
  assert.equal(brown.disposition, 'register');
  assert.equal(brown.needs_owner_tagging, true);
  assert.deepEqual(brown.persona.domain, []);
  assert.deepEqual(brown.persona.perspective, []);
  assert.deepEqual(brown.persona.audiences, []);
  assert.deepEqual(brown.persona.topics, []);
  // Absent seats propose nothing and say why.
  const absentIds = staging.absent_seats.map((seat) => seat.council_seat_id).sort();
  assert.deepEqual(absentIds, [
    'brene-brown',
    'dennis-kimbro',
    'michelle-obama',
    'oprah-winfrey',
    'russell-brunson',
    'td-jakes',
    'tiffany-aliche',
  ]);
  for (const absent of staging.absent_seats) {
    assert.match(absent.reason, /No present works/);
  }
  assert.equal(staging.entries.length + staging.absent_seats.length, 9);
});

test('buildStaging is deterministic', () => {
  const first = JSON.stringify(buildStaging(join(fixtures, 'exports'), seed));
  const second = JSON.stringify(buildStaging(join(fixtures, 'exports'), seed));
  assert.equal(first, second);
});

test('personaKey follows the Skill 22 slug convention', () => {
  assert.equal(personaKey('T. D. Jakes', 'Instinct'), 'jakes-instinct');
  assert.equal(personaKey('Dr. Dennis Kimbro', 'The Wealth Choice'), 'kimbro-the-wealth-choice');
  assert.equal(personaKey('Brené Brown', 'Dare to Lead'), 'brown-dare-to-lead');
});

test('checkStaging passes on a freshly built staging file', () => {
  const staging = buildStaging(join(fixtures, 'exports'), seed);
  assert.deepEqual(checkStaging(staging, seed), []);
});

test('checkStaging refuses a tag outside the seed vocabularies', () => {
  const staging = buildStaging(join(fixtures, 'exports'), seed);
  const brown = staging.entries.find((entry) => entry.key === 'brown-live-your-dreams');
  brown.persona.domain = ['invented-domain'];
  const problems = checkStaging(staging, seed);
  assert.ok(problems.some((problem) => problem.includes('invented-domain')));
});

test('checkStaging refuses an unaccounted seat and a duplicate key', () => {
  const staging = buildStaging(join(fixtures, 'exports'), seed);
  staging.absent_seats = staging.absent_seats.filter((seat) => seat.council_seat_id !== 'oprah-winfrey');
  staging.entries.push({ ...staging.entries[0] });
  const problems = checkStaging(staging, seed);
  assert.ok(problems.some((problem) => problem.includes('oprah-winfrey')));
  assert.ok(problems.some((problem) => problem.includes('duplicate key')));
});
