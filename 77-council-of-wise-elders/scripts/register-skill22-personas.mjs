#!/usr/bin/env node
/**
 * register-skill22-personas.mjs: the Council of Wise Elders to
 * Skill 22 persona-category registry procedure tool (CWE-045; the
 * CWE-050 owner-tooling remainder for the persona-category registry).
 *
 * What it does:
 * - Reads a CWE-011 Skill 22 export (an export directory holding
 *   export-manifest.json plus one package per seat) and the Skill 22
 *   persona-category seed (22-book-to-persona-coaching-leadership-
 *   system/persona-categories.json), and emits a STAGING file
 *   (schema wise-elders.persona-registry-staging/v1) accounting for
 *   every council seat exactly once:
 *     already_registered: a present work whose author and book
 *       already have a seed entry (recorded with the seed's key; no
 *       change proposed);
 *     register: a present work with no seed entry (a seed-shaped
 *       persona proposed with EMPTY tag arrays and
 *       needs_owner_tagging: true; this tool never invents a tag);
 *     absent: a seat with no present works at all (no persona is
 *       proposed; the bibliographic absence recorded by CWE-011 is
 *       carried forward verbatim as the reason).
 * - With --check, validates a staging file against the seed: shape,
 *   seat accounting, already_registered keys really in the seed,
 *   register keys well formed and unused, tag values drawn only from
 *   the seed's declared vocabularies (domainTags, perspectiveTags,
 *   audienceTags, topicTags; custom is free-form per Skill 22), and
 *   provenance hashes well formed.
 *
 * What it never does: it never writes the seed, never writes Skill
 * 22's canonical workspace registry, and never classifies a persona
 * into a tag. Merging the staging file into the canonical registry
 * is an owner step, documented in
 * references/skill22-persona-registry-procedure.md.
 *
 * Usage:
 *   node register-skill22-personas.mjs --exports <dir> --seed <json> --out <staging.json>
 *   node register-skill22-personas.mjs --check <staging.json> --seed <json>
 * Exit codes: 0 ok; 2 usage error or check failure (usage-class
 * failures, printed as JSON on stderr).
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const STAGING_SCHEMA = 'wise-elders.persona-registry-staging/v1';
export const EXPORT_MANIFEST_SCHEMA = 'wise-elders.skill22-export/v1';

export const COUNCIL_SEAT_IDS = [
  'simon-sinek',
  'td-jakes',
  'oprah-winfrey',
  'tiffany-aliche',
  'russell-brunson',
  'michelle-obama',
  'brene-brown',
  'dennis-kimbro',
  'les-brown',
];

const PERSONA_TAG_FIELDS = ['domain', 'perspective', 'custom', 'audiences', 'topics'];
const VOCABULARY_BY_FIELD = {
  domain: 'domainTags',
  perspective: 'perspectiveTags',
  audiences: 'audienceTags',
  topics: 'topicTags',
};

function fail(message) {
  process.stderr.write(`${JSON.stringify({ error: 'usage', message })}\n`);
  process.exit(2);
}

function readJson(path, label) {
  if (!existsSync(path)) fail(`${label} not found: ${path}`);
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch (error) {
    fail(`${label} is not valid JSON (${path}): ${error.message}`);
  }
}

/** Lowercase, strip diacritics and apostrophes, non-alnum to hyphen. */
export function slugPart(text) {
  return String(text)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/** Normalize an author or book string for equality comparison. */
function normText(text) {
  return slugPart(text).replace(/-/g, ' ');
}

/** Surname slug of a credited author name ("T. D. Jakes" -> "jakes"). */
export function authorSlug(author) {
  const parts = String(author).replace(/^(Dr\.|Mr\.|Mrs\.|Ms\.)\s+/i, '').trim().split(/\s+/);
  return slugPart(parts[parts.length - 1] ?? '');
}

/** Skill 22 registry key for an author and book ("jakes-instinct"). */
export function personaKey(author, book) {
  return `${authorSlug(author)}-${slugPart(book)}`;
}

/** Find the seed entry for an author and book, by key or by fields. */
export function findSeedEntry(seed, author, book) {
  const personas = seed?.personas ?? {};
  const expectedKey = personaKey(author, book);
  if (personas[expectedKey]) return { key: expectedKey, entry: personas[expectedKey] };
  const wantedAuthor = normText(author);
  const wantedBook = normText(book);
  for (const [key, entry] of Object.entries(personas)) {
    if (normText(entry?.author ?? '') === wantedAuthor && normText(entry?.book ?? '') === wantedBook) {
      return { key, entry };
    }
  }
  return null;
}

/**
 * Build the staging document from an export directory and the seed.
 * Pure over its inputs (the export manifest plus each seat package's
 * sources.json); deterministic key order and sorting.
 */
export function buildStaging(exportDir, seed) {
  const manifest = readJson(join(exportDir, 'export-manifest.json'), 'export manifest');
  if (manifest.schema !== EXPORT_MANIFEST_SCHEMA) {
    fail(`export manifest schema is ${JSON.stringify(manifest.schema)}, expected ${EXPORT_MANIFEST_SCHEMA}`);
  }
  const entries = [];
  const absentSeats = [];
  const stagedSeats = new Set();
  for (const seat of [...(manifest.seats ?? [])].sort((a, b) => a.seat_id.localeCompare(b.seat_id))) {
    stagedSeats.add(seat.seat_id);
    const presentWorks = (seat.works ?? []).filter((work) => work.status === 'present');
    if (presentWorks.length === 0) {
      absentSeats.push({
        council_seat_id: seat.seat_id,
        disposition: 'absent',
        reason:
          'No present works in the CWE-011 export for this seat; no persona can be ' +
          'registered from absent source material.',
        export_content_sha256: seat.content_sha256,
      });
      continue;
    }
    const sourcesDoc = readJson(
      join(exportDir, seat.seat_id, 'sources.json'),
      `sources for seat ${seat.seat_id}`,
    );
    const sources = sourcesDoc?.sources ?? [];
    for (const work of presentWorks) {
      // The manifest carries short work titles; a package source may
      // carry the full title with a subtitle ("Network Marketing
      // Secrets" vs the source's full title). Join on normalized
      // equality or a word-boundary prefix, never on a substring.
      const wanted = normText(work.work_title);
      const source = sources.find((item) => {
        const candidate = normText(item.work_title ?? '');
        return candidate === wanted || candidate.startsWith(`${wanted} `);
      });
      const author = source?.credited_authors?.[0];
      if (!author) {
        fail(`seat ${seat.seat_id} work ${JSON.stringify(work.work_title)} has no credited author in its export sources`);
      }
      const existing = findSeedEntry(seed, author, work.work_title);
      if (existing) {
        entries.push({
          key: existing.key,
          disposition: 'already_registered',
          persona: {
            author: existing.entry.author,
            book: existing.entry.book,
          },
          provenance: {
            council_seat_id: seat.seat_id,
            work_title: work.work_title,
            coverage_label: work.coverage_label,
            export_content_sha256: seat.content_sha256,
          },
        });
      } else {
        entries.push({
          key: personaKey(author, work.work_title),
          disposition: 'register',
          persona: {
            author,
            book: work.work_title,
            domain: [],
            perspective: [],
            custom: [],
            audiences: [],
            topics: [],
          },
          needs_owner_tagging: true,
          provenance: {
            council_seat_id: seat.seat_id,
            work_title: work.work_title,
            coverage_label: work.coverage_label,
            export_content_sha256: seat.content_sha256,
          },
        });
      }
    }
  }
  for (const seatId of COUNCIL_SEAT_IDS) {
    if (!stagedSeats.has(seatId)) fail(`export manifest does not account for council seat ${seatId}`);
  }
  entries.sort((a, b) => a.key.localeCompare(b.key));
  return {
    schema: STAGING_SCHEMA,
    seed_schema_version: seed?.schemaVersion ?? null,
    entries,
    absent_seats: absentSeats,
  };
}

/** Validate a staging document against the seed. Returns problem strings. */
export function checkStaging(staging, seed) {
  const problems = [];
  if (staging?.schema !== STAGING_SCHEMA) {
    problems.push(`staging schema is ${JSON.stringify(staging?.schema)}, expected ${STAGING_SCHEMA}`);
  }
  const personas = seed?.personas ?? {};
  const accounted = new Map();
  const seenKeys = new Set();
  const account = (seatId, where) => {
    if (!COUNCIL_SEAT_IDS.includes(seatId)) {
      problems.push(`${where}: unknown council seat ${JSON.stringify(seatId)}`);
    }
    accounted.set(seatId, (accounted.get(seatId) ?? 0) + 1);
  };
  for (const [index, entry] of (staging?.entries ?? []).entries()) {
    const where = `entries[${index}] (${entry?.key ?? 'no key'})`;
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(entry?.key ?? '')) {
      problems.push(`${where}: key is not a well-formed Skill 22 slug`);
    }
    if (seenKeys.has(entry?.key)) problems.push(`${where}: duplicate key`);
    seenKeys.add(entry?.key);
    account(entry?.provenance?.council_seat_id, where);
    if (!/^[0-9a-f]{64}$/.test(entry?.provenance?.export_content_sha256 ?? '')) {
      problems.push(`${where}: provenance export_content_sha256 is not a sha256 hex digest`);
    }
    if (entry?.disposition === 'already_registered') {
      if (!personas[entry.key]) {
        problems.push(`${where}: marked already_registered but the key is not in the seed`);
      }
    } else if (entry?.disposition === 'register') {
      if (personas[entry.key]) {
        problems.push(`${where}: marked register but the key already exists in the seed`);
      }
      if (entry.needs_owner_tagging !== true) {
        problems.push(`${where}: register entries must carry needs_owner_tagging: true until an owner tags them`);
      }
      for (const field of PERSONA_TAG_FIELDS) {
        const values = entry.persona?.[field];
        if (!Array.isArray(values)) {
          problems.push(`${where}: persona.${field} must be an array`);
          continue;
        }
        const vocabularyKey = VOCABULARY_BY_FIELD[field];
        if (vocabularyKey) {
          const vocabulary = new Set(seed?.[vocabularyKey] ?? []);
          for (const value of values) {
            if (!vocabulary.has(value)) {
              problems.push(`${where}: persona.${field} value ${JSON.stringify(value)} is not in the seed ${vocabularyKey} vocabulary`);
            }
          }
        }
      }
    } else {
      problems.push(`${where}: unknown disposition ${JSON.stringify(entry?.disposition)}`);
    }
  }
  for (const [index, absent] of (staging?.absent_seats ?? []).entries()) {
    account(absent?.council_seat_id, `absent_seats[${index}]`);
    if (absent?.disposition !== 'absent' || typeof absent?.reason !== 'string' || absent.reason.length === 0) {
      problems.push(`absent_seats[${index}]: must carry disposition 'absent' and a non-empty reason`);
    }
  }
  for (const seatId of COUNCIL_SEAT_IDS) {
    // A seat with several present works accounts once per work; a seat
    // with none accounts once in absent_seats. Both are exact.
    if (!accounted.has(seatId)) problems.push(`council seat ${seatId} is not accounted for`);
  }
  return problems;
}

function main(argv) {
  const args = [...argv];
  const option = (name) => {
    const at = args.indexOf(name);
    return at >= 0 ? args[at + 1] : undefined;
  };
  const seedPath = option('--seed');
  if (!seedPath) fail('missing --seed <persona-categories.json>');
  const seed = readJson(seedPath, 'persona-category seed');
  const checkPath = option('--check');
  if (checkPath) {
    const staging = readJson(checkPath, 'staging file');
    const problems = checkStaging(staging, seed);
    if (problems.length > 0) {
      process.stderr.write(`${JSON.stringify({ error: 'check_failed', problems }, null, 2)}\n`);
      process.exit(2);
    }
    process.stdout.write(`${JSON.stringify({ ok: true, entries: staging.entries.length, absent_seats: staging.absent_seats.length })}\n`);
    return;
  }
  const exportDir = option('--exports');
  const outPath = option('--out');
  if (!exportDir || !outPath) fail('usage: register-skill22-personas.mjs --exports <dir> --seed <json> --out <staging.json>');
  const staging = buildStaging(exportDir, seed);
  writeFileSync(outPath, `${JSON.stringify(staging, null, 2)}\n`, 'utf8');
  process.stdout.write(
    `${JSON.stringify({ ok: true, out: outPath, entries: staging.entries.length, absent_seats: staging.absent_seats.length })}\n`,
  );
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main(process.argv.slice(2));
}
