/**
 * Report existing Skill 22 persona/book assets for only the approved
 * nine Council advisors. Read-only; never modifies source or adds seats.
 *
 * node --import tsx scripts/audit-skill22-preservation.ts [--json]
 */
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { inventoryCouncilSkill22Personas } from '../src/sources/skill22-inventory.js';

const skillRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const repoRoot = resolve(skillRoot, '..');
const skill22 = resolve(repoRoot, '22-book-to-persona-coaching-leadership-system');
const result = inventoryCouncilSkill22Personas(skill22);

if (process.argv.includes('--json')) {
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
} else {
  process.stdout.write(
    'Skill 22 preserved: ' + result.existing_registered_personas +
    ' registered persona books; ' + result.personas_with_extraction_notes +
    ' with extraction notes; ' + result.personas_blueprint_only +
    ' blueprint-only, across exactly 9 Council seats.\n',
  );
  for (const seat of result.seats) {
    process.stdout.write(seat.display_name + ': ' + seat.registered_persona_count + ' existing books\n');
    for (const persona of seat.existing_personas) {
      process.stdout.write('  - ' + persona.book + ' [' + persona.content_level + '] (' + persona.key + ')\n');
    }
  }
  process.stdout.write(
    'SOURCE NOTE: Existing Skill 22 derivative books and blueprints are preserved. ' +
    'Original-book access, citation accuracy, rights and production source-gate status ' +
    'remain independently unverified until checked.\n',
  );
}
