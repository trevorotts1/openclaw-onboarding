/** Explicit, deterministic Skill22 derivative -> canonical Council package bridge.
 * Mapping assertions are supplied evidence, never independent source verification.
 * No inference, original-book ingestion, registry edits or advisor-pack replacement.
 */
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { z } from 'zod';
import { idSchema, sha256Schema } from '../contracts/schemas.js';
import { inventoryCouncilSkill22Personas } from './skill22-inventory.js';
import { validateExportPackage, type Skill22ExportPackage } from './export-package.js';
import { evidenceUnitSchema, sourceRecordSchema, sourceVersionOf, type EvidenceUnit, type SourceRecord } from './schemas.js';
import { normalizeTitle, sameSpeaker } from './text.js';

const passageSchema = z.strictObject({
  file: z.string().min(1),
  sha256: sha256Schema,
  start_line: z.number().int().positive(),
  end_line: z.number().int().positive(),
  text_field: z.enum(['paraphrase', 'excerpt']),
  evidence: evidenceUnitSchema.omit({ paraphrase: true, excerpt: true }),
});
const entrySchema = z.strictObject({
  persona_key: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
  source: sourceRecordSchema,
  hash_basis: z.enum(['retained_original', 'skill22_derivative']),
  provenance_reference: idSchema,
  shared_export_approved: z.boolean(),
  passages: z.array(z.unknown()).min(1),
});
const mappingSchema = z.strictObject({
  schema: z.literal('wise-elders.skill22-mapping/v1'),
  pack_version: z.string().min(1),
  entries: z.array(z.unknown()),
  revoked_source_ids: z.array(idSchema),
});
export interface ExportDiagnostic {
  code: string;
  entry?: number;
  passage?: number;
  seat_id?: string;
  persona_key?: string;
  field?: string;
}
const hash = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex');
export function exportSkill22(skill22Root: string, mapping: unknown) {
  const input = mappingSchema.parse(mapping);
  const inventory = inventoryCouncilSkill22Personas(skill22Root);
  const personas = new Map(inventory.seats.flatMap(seat => seat.existing_personas.map(persona =>
    [persona.key, { seat_id: seat.seat_id, persona }] as const)));
  const packages: Skill22ExportPackage[] = inventory.seats.map(seat => ({
    seat_id: seat.seat_id, pack_version: input.pack_version, sources: [], evidence: [], claimed_titles: [],
  }));
  const diagnostics: ExportDiagnostic[] = [];
  const receipts: Array<{ evidence_id: string; file: string; sha256: string; start_line: number; end_line: number;
    hash_basis: string; provenance_reference: string }> = [];
  const seenPersonas = new Set<string>();
  const sourceById = new Map<string, SourceRecord>();
  const evidenceIds = new Set<string>();
  const revoked = new Set(input.revoked_source_ids);
  const root = realpathSync(resolve(skill22Root, 'personas'));
  const note = (code: string, entry?: number, passage?: number) => diagnostics.push({ code, entry, passage });
  input.entries.forEach((raw, i) => {
    const parsed = entrySchema.safeParse(raw);
    if (!parsed.success) {
      diagnostics.push({ code: 'MAPPING_ENTRY_INVALID', entry: i, field: parsed.error.issues[0]?.path.join('.') });
      return;
    }
    const entry = parsed.data;
    const found = personas.get(entry.persona_key);
    if (!found) { note('PERSONA_NOT_REGISTERED_FOR_COUNCIL', i); return; }
    seenPersonas.add(entry.persona_key);
    const source = entry.source;
    if (!entry.shared_export_approved || source.allowed_scope !== 'shared_pack' || source.rights_status === 'private_use') {
      note('SHARED_EXPORT_NOT_PERMITTED', i); return;
    }
    if (revoked.has(source.source_id)) { note('SOURCE_REVOKED', i); return; }
    if (normalizeTitle(source.work_title) !== normalizeTitle(found.persona.book) ||
        !source.credited_authors.some(author => sameSpeaker(author, found.persona.author))) {
      note('PERSONA_SOURCE_MISMATCH', i); return;
    }
    // A hash of derivative notes never certifies an original or primary teaching.
    if (entry.hash_basis === 'skill22_derivative' && (source.quality === 'primary_substantive' ||
        !found.persona.files.some(file => file.sha256 === source.content_sha256))) {
      note('DERIVATIVE_SOURCE_BASIS_INVALID', i); return;
    }
    const previousSource = sourceById.get(source.source_id);
    if (previousSource && JSON.stringify(previousSource) !== JSON.stringify(source)) {
      note('SOURCE_ID_CONFLICT', i); return;
    }
    const pkg = packages.find(p => p.seat_id === found.seat_id)!;
    entry.passages.forEach((rawPassage, j) => {
      const parsedPassage = passageSchema.safeParse(rawPassage);
      if (!parsedPassage.success) {
        diagnostics.push({ code: 'PASSAGE_MAPPING_INVALID', entry: i, passage: j, field: parsedPassage.error.issues[0]?.path.join('.') });
        return;
      }
      const passage = parsedPassage.data;
      const unit = passage.evidence;
      if (unit.seat_id !== found.seat_id || unit.source_id !== source.source_id ||
          unit.source_version !== sourceVersionOf(source) ||
          !source.locators.some(loc => loc.kind === unit.locator.kind && loc.value === unit.locator.value)) {
        note('EVIDENCE_PROVENANCE_MISMATCH', i, j); return;
      }
      if (evidenceIds.has(unit.evidence_id)) { note('EVIDENCE_ID_DUPLICATE', i, j); return; }
      if (passage.text_field === 'excerpt' && !['licensed_distribution', 'public_domain'].includes(source.rights_status)) {
        note('EXCERPT_RELEASE_NOT_PERMITTED', i, j); return;
      }
      if (unit.kind === 'quotation' && (passage.text_field !== 'excerpt' || !unit.original_speaker ||
          !source.original_speaker || !sameSpeaker(unit.original_speaker, source.original_speaker))) {
        note('QUOTATION_ATTRIBUTION_UNRESOLVED', i, j); return;
      }
      // Only allow the selected persona's inventoried artifacts, not arbitrary files.
      const receipt = found.persona.files.find(file => file.file === passage.file);
      if (!receipt || !passage.file.startsWith(entry.persona_key + '/')) {
        note('DERIVATIVE_FILE_NOT_IN_PERSONA', i, j); return;
      }
      let bytes: Buffer;
      try {
        const path = realpathSync(resolve(root, passage.file));
        if (!path.startsWith(resolve(root, entry.persona_key) + sep)) throw new Error('outside persona');
        bytes = readFileSync(path);
      } catch { note('DERIVATIVE_FILE_UNREADABLE', i, j); return; }
      if (hash(bytes) !== passage.sha256 || receipt.sha256 !== passage.sha256) {
        note('DERIVATIVE_HASH_MISMATCH', i, j); return;
      }
      let lines: string[];
      try { lines = new TextDecoder('utf-8', { fatal: true }).decode(bytes).split(/\r?\n/); }
      catch { note('DERIVATIVE_ENCODING_INVALID', i, j); return; }
      if (passage.end_line < passage.start_line || passage.end_line > lines.length) {
        note('DERIVATIVE_RANGE_INVALID', i, j); return;
      }
      const text = lines.slice(passage.start_line - 1, passage.end_line).join('\n').trim();
      if (!text) { note('DERIVATIVE_RANGE_EMPTY', i, j); return; }
      const evidence: EvidenceUnit = { ...unit, paraphrase: null, excerpt: null, [passage.text_field]: text };
      const sources = (pkg.sources as SourceRecord[]).some(s => s.source_id === source.source_id)
        ? [...pkg.sources] : [...pkg.sources, source];
      const candidate = { ...pkg, sources, evidence: [...pkg.evidence, evidence],
        claimed_titles: [...new Set([...(pkg.claimed_titles ?? []), source.work_title])] };
      const validation = validateExportPackage(candidate, { contextScope: 'shared_pack', revokedSourceIds: revoked });
      if (!validation.accepted) {
        // Codes only: diagnostic messages can quote excluded/private source content.
        validation.diagnostics.filter(d => d.severity === 'error').forEach(d => note(d.code, i, j));
        return;
      }
      Object.assign(pkg, candidate);
      sourceById.set(source.source_id, source);
      evidenceIds.add(evidence.evidence_id);
      receipts.push({ evidence_id: evidence.evidence_id, file: passage.file, sha256: passage.sha256,
        start_line: passage.start_line, end_line: passage.end_line, hash_basis: entry.hash_basis,
        provenance_reference: entry.provenance_reference });
    });
  });
  for (const [key, found] of personas) {
    if (!seenPersonas.has(key)) diagnostics.push({ code: 'PERSONA_MAPPING_MISSING', seat_id: found.seat_id, persona_key: key });
  }
  const seats = packages.map(pkg => {
    const validation = validateExportPackage(pkg, { contextScope: 'shared_pack', revokedSourceIds: revoked });
    if (!validation.accepted) throw new Error('Exporter produced an invalid package.');
    if (!pkg.evidence.length) diagnostics.push({ code: 'SEAT_HAS_NO_EXPORTED_EVIDENCE', seat_id: pkg.seat_id });
    return { seat_id: pkg.seat_id, package_sha256: hash(JSON.stringify(pkg)), evidence_units: pkg.evidence.length,
      qualification: validation.qualification, works: validation.works };
  });
  return { schema: 'wise-elders.canonical-skill22-export/v1', scope: 'shared_pack', packages, seats, receipts, diagnostics,
    mapping_sha256: hash(JSON.stringify(input)),
    source_verification: 'Mapping assertions retained; original access, passage fidelity and permission are not independently certified by this exporter.' };
}
