/**
 * CWE-050 integration adapter: CWE-011 Skill 22 export (v1 shape) to
 * the strict CWE-012 source and evidence schemas, WITHOUT loosening
 * the strict schemas (CWE-022 carried finding; CWE-024 flag 4).
 *
 * What the real export carries, and what the adapter does with it:
 *
 * - Source records: the v1 export adds bookkeeping fields the strict
 *   schema rejects (status, record_status, anchor_role, artifacts,
 *   content_hash_basis, export_skill, extraction, flags, gaps,
 *   locator_kinds_available, retained_text, rights_note,
 *   skill22_persona_folder, coverage_label). The adapter constructs
 *   each strict record field by field from the canonical subset only;
 *   the dropped field names are reported, never silently merged in.
 * - Present records (content_sha256 set) adapt to strict records.
 *   Their content hash is the Skill 22 derivative artifact's hash
 *   (extraction-notes.md), per the export's own content_hash_basis;
 *   originals were never hashed or copied, and the adapter does not
 *   pretend otherwise.
 * - retrieved_at: only ONE record in the export carries its own
 *   retrieval date (Brunson Network Marketing Secrets, 2026-06-26);
 *   it is kept verbatim. For every other present record the adapter
 *   uses the export package's exported_at, recorded in the adaptation
 *   report as the date the record's content hash was fixed in the
 *   council pipeline by the CWE-011 export. That is a pipeline date,
 *   NOT the underlying Skill 22 retrieval date, and the record's
 *   quality label is carried verbatim (never upgraded).
 * - Absent records (no content hash: the verifiably absent works) get
 *   NO strict record: no hash or date is fabricated for them. They are
 *   emitted as absence entries in the adaptation report with their
 *   export-recorded gaps, and nothing loads for them downstream,
 *   matching the packs' source_absent treatment.
 * - Evidence units: concept units load with paraphrase = the export's
 *   summary. Quotation units are ALL verification_status 'candidate'
 *   in the export (build-wide standing fact: zero verified
 *   quotations; their verification_basis values are unverified-grade).
 *   Candidate quote text is therefore WITHHELD: quote units adapt with
 *   excerpt null and paraphrase null, carry no loadable text, and the
 *   adapted catalog never offers them as candidates. The permanent fix
 *   is a v2 export shape carrying located retained text; until then a
 *   candidate quote is never presented as a verified quotation.
 *
 * Every constructed record and unit is parsed through the strict
 * CWE-012 schemas; a parse failure throws naming the record or unit.
 * Fail closed, never drop silently.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { canonicalHash, type SeatId } from '../contracts/index.js';
import type {
  CandidateHeader,
  MaterialCandidate,
  MaterialCatalog,
} from '../context/types.js';
import type { ScopeFields, SessionVisibility } from '../contracts/index.js';
import {
  evidenceUnitSchema,
  sourceRecordSchema,
  type EvidenceUnit,
  type SourceRecord,
} from './schemas.js';

/** One absent work: no strict record exists for it, by design. */
export interface ExportAbsence {
  source_id: string;
  seat_id: string;
  work_title: string;
  /** The export's own gap notes, verbatim. */
  gaps: string[];
}

export interface AdaptationReport {
  exporter: string;
  exported_at: string;
  basis_commit: string | null;
  records_seen: number;
  records_adapted: number;
  absences: ExportAbsence[];
  /** source_id -> where its retrieved_at came from. */
  retrieved_at_basis: Record<string, 'record_verbatim' | 'export_package'>;
  /** Export-only field names the adapter dropped, sorted. */
  dropped_fields: string[];
  units_seen: number;
  units_adapted: number;
  concept_units: number;
  /** Quote units whose candidate text was withheld (excerpt null). */
  quote_units_text_withheld: number;
}

export interface AdaptedExport {
  records: SourceRecord[];
  units: EvidenceUnit[];
  report: AdaptationReport;
}

interface RawManifest {
  exporter?: { name?: string };
  exported_at?: string;
  source_tree?: { basis_commit?: string };
}

const CANONICAL_RECORD_FIELDS = new Set([
  'source_id',
  'work_id',
  'work_title',
  'credited_authors',
  'original_speaker',
  'source_type',
  'publisher_or_host',
  'edition_or_publication_date',
  'retrieved_at',
  'canonical_url',
  'private_asset_id',
  'content_sha256',
  'rights_status',
  'allowed_scope',
  'locators',
  'quality',
]);

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown>;
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/**
 * Adapt a CWE-011 export directory (the directory holding
 * export-manifest.json and one subdirectory per seat) into strict
 * CWE-012 records and units plus the adaptation report.
 */
export function adaptSkill22Export(exportsDir: string): AdaptedExport {
  const manifest = readJson(join(exportsDir, 'export-manifest.json')) as RawManifest;
  const exportedAt = str(manifest.exported_at);
  if (!exportedAt) {
    throw new Error('export manifest carries no exported_at; cannot fix a retrieval basis date');
  }
  const seatDirs = readdirSync(exportsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  const records: SourceRecord[] = [];
  const units: EvidenceUnit[] = [];
  const report: AdaptationReport = {
    exporter: str(manifest.exporter?.name) ?? 'unknown',
    exported_at: exportedAt,
    basis_commit: str(manifest.source_tree?.basis_commit),
    records_seen: 0,
    records_adapted: 0,
    absences: [],
    retrieved_at_basis: {},
    dropped_fields: [],
    units_seen: 0,
    units_adapted: 0,
    concept_units: 0,
    quote_units_text_withheld: 0,
  };
  const dropped = new Set<string>();
  const recordById = new Map<string, SourceRecord>();

  for (const seatDir of seatDirs) {
    const sourcesDoc = readJson(join(exportsDir, seatDir, 'sources.json'));
    const rawSources = (sourcesDoc.sources ?? []) as Array<Record<string, unknown>>;
    for (const raw of rawSources) {
      report.records_seen += 1;
      for (const key of Object.keys(raw)) {
        if (!CANONICAL_RECORD_FIELDS.has(key)) dropped.add(key);
      }
      const sourceId = str(raw.source_id) ?? 'unknown';
      if (!str(raw.content_sha256)) {
        report.absences.push({
          source_id: sourceId,
          seat_id: seatDir,
          work_title: str(raw.work_title) ?? '',
          gaps: Array.isArray(raw.gaps) ? raw.gaps.map((g) => String(g)) : [],
        });
        continue;
      }
      const ownRetrievedAt = str(raw.retrieved_at);
      report.retrieved_at_basis[sourceId] = ownRetrievedAt
        ? 'record_verbatim'
        : 'export_package';
      const candidate = {
        source_id: raw.source_id,
        work_id: raw.work_id,
        work_title: raw.work_title,
        credited_authors: raw.credited_authors,
        original_speaker: raw.original_speaker ?? null,
        source_type: raw.source_type,
        publisher_or_host: raw.publisher_or_host ?? null,
        edition_or_publication_date: raw.edition_or_publication_date ?? null,
        retrieved_at: ownRetrievedAt ?? exportedAt,
        canonical_url: raw.canonical_url ?? null,
        private_asset_id: raw.private_asset_id ?? null,
        content_sha256: raw.content_sha256,
        rights_status: raw.rights_status,
        allowed_scope: raw.allowed_scope,
        locators: raw.locators ?? [],
        quality: raw.quality,
      };
      const parsed = sourceRecordSchema.safeParse(candidate);
      if (!parsed.success) {
        throw new Error(
          `adaptSkill22Export: strict parse failed for source record ${sourceId}: ${parsed.error.issues
            .map((i) => `${i.path.join('.')}: ${i.message}`)
            .join('; ')}`,
        );
      }
      records.push(parsed.data);
      recordById.set(parsed.data.source_id, parsed.data);
      report.records_adapted += 1;
    }

    const unitsDoc = readJson(join(exportsDir, seatDir, 'evidence-units.json'));
    const rawUnits = (unitsDoc.evidence_units ?? []) as Array<Record<string, unknown>>;
    for (const raw of rawUnits) {
      report.units_seen += 1;
      const evidenceId = str(raw.evidence_id) ?? 'unknown';
      const sourceId = str(raw.source_id) ?? '';
      const record = recordById.get(sourceId);
      if (!record) {
        throw new Error(
          `adaptSkill22Export: evidence unit ${evidenceId} references source ${sourceId}, which has no adapted record (absent works carry no units in this export)`,
        );
      }
      const unitKind = str(raw.unit_kind);
      const locators = (raw.locators ?? []) as Array<{ kind: 'page' | 'timestamp' | 'section'; value: string }>;
      if (locators.length === 0) {
        throw new Error(`adaptSkill22Export: evidence unit ${evidenceId} carries no locator`);
      }
      const quote = (raw.quote ?? null) as { original_speaker?: unknown } | null;
      const isQuote = unitKind === 'quote';
      const candidateUnit = {
        evidence_id: raw.evidence_id,
        source_id: sourceId,
        source_version: record.version ?? record.content_sha256,
        locator: locators[0],
        kind: isQuote ? 'quotation' : 'concept',
        mark: raw.kind,
        original_speaker: str(quote?.original_speaker) ?? record.original_speaker,
        // Candidate quote text is withheld (see the module header):
        // a 'candidate' verification status is not a verified quote.
        excerpt: null,
        paraphrase: isQuote ? null : str(raw.summary),
        claim_ids: [],
        seat_id: raw.seat_id,
      };
      const parsed = evidenceUnitSchema.safeParse(candidateUnit);
      if (!parsed.success) {
        throw new Error(
          `adaptSkill22Export: strict parse failed for evidence unit ${evidenceId}: ${parsed.error.issues
            .map((i) => `${i.path.join('.')}: ${i.message}`)
            .join('; ')}`,
        );
      }
      units.push(parsed.data);
      report.units_adapted += 1;
      if (isQuote) report.quote_units_text_withheld += 1;
      else report.concept_units += 1;
    }
  }

  report.dropped_fields = [...dropped].sort();
  return { records, units, report };
}

/**
 * A CWE-022 MaterialCatalog over an adapted export. Only units with
 * loadable text (a paraphrase or a permitted excerpt) are offered as
 * candidates; withheld candidate quotations are never listed, so the
 * retrieval path can never load them. Header hashes are the canonical
 * hash of the strict unit, as the accepted context path requires.
 */
export function createAdaptedMaterialCatalog(
  adapted: AdaptedExport,
  options: { scope: ScopeFields; visibility?: SessionVisibility },
): MaterialCatalog {
  const recordById = new Map(adapted.records.map((r) => [r.source_id, r]));
  const candidates = new Map<string, MaterialCandidate>();
  for (const unit of adapted.units) {
    if (unit.excerpt === null && unit.paraphrase === null) continue;
    const source = recordById.get(unit.source_id);
    if (!source) continue;
    const header: CandidateHeader = {
      evidence_id: unit.evidence_id,
      seat_id: unit.seat_id as SeatId,
      scope: options.scope,
      visibility: options.visibility ?? 'company',
      source_id: unit.source_id,
      allowed_scope: source.allowed_scope,
      sha256: canonicalHash(unit),
    };
    candidates.set(unit.evidence_id, { header, source, unit });
  }
  return {
    listCandidateHeaders: () => [...candidates.values()].map((c) => c.header),
    loadCandidate: (evidenceId) => candidates.get(evidenceId) ?? null,
  };
}
