/**
 * WER-013: preserve and inventory existing Skill 22 book-to-persona
 * derivatives before the Council imports, upgrades or re-researches them.
 *
 * A persona blueprint, analysis note, or extraction note is EXISTING WORK,
 * not proof that original copyrighted source text, rights or page locators
 * were independently verified. This module never promotes source quality,
 * copies private assets, or modifies Skill 22's canonical registry.
 *
 * Each author is matched ONLY against the approved fixed nine Council
 * seats. Skill 22 contains many other authors: no persona found in its
 * library can create a new Council seat or portrait.
 */
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { SEAT_ROSTER, type SeatId } from '../contracts/enums.js';

export const SKILL22_PERSONA_FILES = [
  'persona-blueprint.md',
  'analysis-notes.md',
  'extraction-notes.md',
  'PLAYBOOK-APPENDIX.md',
  'source.json',
] as const;

export interface PersonaFileReceipt {
  file: string;
  bytes: number;
  sha256: string;
}

export interface ExistingBookPersona {
  key: string;
  author: string;
  book: string;
  files: PersonaFileReceipt[];
  content_level: 'extraction_and_blueprint' | 'blueprint_only' | 'other_derived' | 'missing';
  source_quality_certified: false;
  limitation: string;
}

export interface Skill22CouncilSeatInventory {
  seat_id: SeatId;
  display_name: string;
  existing_personas: ExistingBookPersona[];
  registered_persona_count: number;
}

export interface Skill22CouncilInventory {
  schema: 'wise-elders.skill22-preservation-inventory/v1';
  source: string;
  source_kind: 'Skill 22 registered derivative files, NOT original book ingestion receipts';
  approved_seat_count: 9;
  existing_registered_personas: number;
  personas_with_extraction_notes: number;
  personas_blueprint_only: number;
  seats: Skill22CouncilSeatInventory[];
  unrecognized_registry_entries: number;
}

function normalizeAuthor(input: string): string {
  return input.normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\b(dr|mr|mrs|ms)\.?\s+/gi, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function checkedDerivedFile(root: string, path: string): PersonaFileReceipt | null {
  if (!existsSync(path)) return null;
  const canonicalRoot = realpathSync(root);
  const canonicalFile = realpathSync(path);
  if (!canonicalFile.startsWith(canonicalRoot + sep) || !statSync(canonicalFile).isFile()) {
    throw new Error('A Skill 22 persona file is outside the canonical persona directory.');
  }
  const buffer = readFileSync(canonicalFile);
  return {
    file: canonicalFile.slice(canonicalRoot.length + 1).replaceAll(sep, '/'),
    bytes: buffer.length,
    sha256: createHash('sha256').update(buffer).digest('hex'),
  };
}

export function inventoryCouncilSkill22Personas(skill22Root: string): Skill22CouncilInventory {
  const root = resolve(skill22Root);
  const personaRoot = join(root, 'personas');
  const seed = JSON.parse(readFileSync(join(root, 'persona-categories.json'), 'utf8')) as {
    personas?: Record<string, { author?: unknown; book?: unknown }>;
  };
  if (!seed.personas || Array.isArray(seed.personas) || typeof seed.personas !== 'object') {
    throw new Error('Skill 22 canonical persona-categories.json has no personas object.');
  }
  const authorBySeat = new Map(
    SEAT_ROSTER.map((seat) => [normalizeAuthor(seat.display_name), seat.seat_id]),
  );
  if (SEAT_ROSTER.length !== 9 || new Set(SEAT_ROSTER.map((seat) => seat.seat_id)).size !== 9) {
    throw new Error('Council roster is not exactly the nine approved seats.');
  }
  const bySeat = new Map<SeatId, ExistingBookPersona[]>(
    SEAT_ROSTER.map((seat) => [seat.seat_id, []]),
  );
  let unrecognizedRegistryEntries = 0;
  for (const [key, registry] of Object.entries(seed.personas)) {
    if (!registry || typeof registry.author !== 'string' || typeof registry.book !== 'string') {
      unrecognizedRegistryEntries += 1;
      continue;
    }
    const seat = authorBySeat.get(normalizeAuthor(registry.author));
    if (!seat) {
      // Other Skill 22 authors are legal library entries, but NEVER seats.
      unrecognizedRegistryEntries += 1;
      continue;
    }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(key)) {
      throw new Error('Unsafe Skill 22 persona key for an approved Council member.');
    }
    const dir = join(personaRoot, key);
    const files = SKILL22_PERSONA_FILES.map((file) => checkedDerivedFile(personaRoot, join(dir, file)))
      .filter((entry): entry is PersonaFileReceipt => entry !== null);
    const hasBlueprint = files.some((x) => x.file.endsWith('/persona-blueprint.md'));
    const hasExtraction = files.some((x) => x.file.endsWith('/extraction-notes.md'));
    const contentLevel: ExistingBookPersona['content_level'] = hasExtraction && hasBlueprint
      ? 'extraction_and_blueprint'
      : hasBlueprint
        ? 'blueprint_only'
        : files.length
          ? 'other_derived'
          : 'missing';
    bySeat.get(seat)!.push({
      key,
      author: registry.author,
      book: registry.book,
      files,
      content_level: contentLevel,
      source_quality_certified: false,
      limitation: 'Files in Skill 22 are existing derivative notes and personas. Their presence is not independent verification of original-source access, work completeness, citation accuracy, or redistribution rights.',
    });
  }
  const seats: Skill22CouncilSeatInventory[] = SEAT_ROSTER.map((seat) => {
    const existing = bySeat.get(seat.seat_id)!.sort((a, b) => a.key.localeCompare(b.key));
    return {
      seat_id: seat.seat_id,
      display_name: seat.display_name,
      existing_personas: existing,
      registered_persona_count: existing.length,
    };
  });
  const existing = seats.flatMap((seat) => seat.existing_personas);
  return {
    schema: 'wise-elders.skill22-preservation-inventory/v1',
    source: '22-book-to-persona-coaching-leadership-system/persona-categories.json + personas/',
    source_kind: 'Skill 22 registered derivative files, NOT original book ingestion receipts',
    approved_seat_count: 9,
    existing_registered_personas: existing.length,
    personas_with_extraction_notes: existing.filter((p) => p.content_level === 'extraction_and_blueprint').length,
    personas_blueprint_only: existing.filter((p) => p.content_level === 'blueprint_only').length,
    seats,
    unrecognized_registry_entries: unrecognizedRegistryEntries,
  };
}
