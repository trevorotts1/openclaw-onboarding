import assert from 'node:assert/strict';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { SEAT_IDS, SEAT_ROSTER } from '../src/contracts/enums.js';
import { inventoryCouncilSkill22Personas } from '../src/sources/skill22-inventory.js';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const root = resolve(repoRoot, '22-book-to-persona-coaching-leadership-system');
const inventory = inventoryCouncilSkill22Personas(root);

test('only the exact nine chosen Council members can be mapped from all Skill 22 personas', () => {
  assert.equal(SEAT_IDS.length, 9);
  assert.deepEqual(SEAT_IDS, [
    'simon-sinek', 'td-jakes', 'oprah-winfrey', 'tiffany-aliche',
    'russell-brunson', 'michelle-obama', 'brene-brown',
    'dennis-kimbro', 'les-brown',
  ]);
  assert.deepEqual(inventory.seats.map((s) => s.seat_id), SEAT_IDS);
  assert.equal(inventory.approved_seat_count, 9);
  assert.equal(new Set(inventory.seats.map((s) => s.display_name)).size, 9);
  assert.equal(inventory.seats.some((s) => /steve.harvey/i.test(s.display_name)), false);
  assert.equal(inventory.seats.some((s) => /steve.harvey/i.test(JSON.stringify(s.existing_personas))), false);
  assert.deepEqual(
    inventory.seats.map((s) => s.display_name),
    SEAT_ROSTER.map((s) => s.display_name),
  );
});

test('existing client Book-to-Persona extraction notes are inventoried, not erased or called absent', () => {
  const bySeat = (seat: string) => inventory.seats.find((s) => s.seat_id === seat)!;
  const expectExtracted = [
    ['simon-sinek', 'sinek-start-with-why'],
    ['simon-sinek', 'sinek-find-your-why'],
    ['td-jakes', 'jakes-instinct'],
    ['michelle-obama', 'obama-becoming'],
    ['michelle-obama', 'obama-light-we-carry'],
    ['brene-brown', 'brown-atlas-of-heart'],
  ];
  for (const [seat, key] of expectExtracted) {
    const row = bySeat(seat).existing_personas.find((p) => p.key === key);
    assert.ok(row, key + ' must not disappear from the Skill 22 bridge');
    assert.equal(row.content_level, 'extraction_and_blueprint', key);
    assert.ok(row.files.some((f) => f.file.endsWith('extraction-notes.md')));
    assert.ok(row.files.every((f) => /^[a-f0-9]{64}$/.test(f.sha256) && f.bytes > 0));
  }
});

test('the previously authored blueprint-only books remain visible without fake extraction claims', () => {
  const required = [
    ['tiffany-aliche', 'aliche-get-good-with-money'],
    ['dennis-kimbro', 'kimbro-the-wealth-choice'],
    ['dennis-kimbro', 'kimbro-what-makes-great-great'],
  ];
  for (const [seat, key] of required) {
    const row = inventory.seats.find((s) => s.seat_id === seat)
      ?.existing_personas.find((p) => p.key === key);
    assert.ok(row, key + ' is existing client work');
    assert.equal(row.content_level, 'blueprint_only');
  }
});

test('no derivative file is automatically treated as a verified primary book or authority to add seats', () => {
  const records = inventory.seats.flatMap((s) => s.existing_personas);
  assert.equal(records.length, inventory.existing_registered_personas);
  assert.ok(records.length >= 14, 'existing Skill 22 persona work must be preserved');
  assert.ok(records.every((p) => p.source_quality_certified === false));
  assert.ok(records.every((p) => p.limitation.includes('independent verification')));
  assert.equal(inventory.seats.length, 9);
});
