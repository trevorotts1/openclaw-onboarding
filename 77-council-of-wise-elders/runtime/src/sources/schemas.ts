/**
 * Source integrity schemas for the Council of Wise Elders (CWE-012).
 *
 * Implements the Section 8.3 source record contract and the evidence-unit
 * shape the quotation validator and coverage gate consume. These schemas
 * extend the CWE-003 canonical contracts; they do not redefine them. The
 * AdvisorCard quote surface stays the CWE-003 VerifiedQuoteCandidate; this
 * module verifies such candidates against source records and evidence.
 *
 * Boundary rules, mirroring the contracts package:
 * - strict objects: unknown fields are rejected, never silently dropped;
 * - unknown enum values and invalid IDs fail validation;
 * - unknown values are null, never empty strings masquerading as facts;
 * - a filename or a bibliographic entry is not ingestion (Section 8.2):
 *   only a full source record in this shape can ground a claim.
 */

import { z } from 'zod';
import { idSchema, seatIdSchema, sha256Schema } from '../contracts/schemas';

/** Claim-level locator (Section 8.3): page, timestamp, or section. */
export const sourceLocatorSchema = z.strictObject({
  kind: z.enum(['page', 'timestamp', 'section']),
  value: z.string().min(1),
});
export type SourceLocator = z.infer<typeof sourceLocatorSchema>;

export const SOURCE_TYPES = [
  'book',
  'article',
  'talk',
  'interview',
  'transcript',
] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];

export const RIGHTS_STATUSES = [
  'reference_only',
  'private_use',
  'licensed_distribution',
  'public_domain',
] as const;
export type RightsStatus = (typeof RIGHTS_STATUSES)[number];

export const SOURCE_SCOPES = ['shared_pack', 'tenant', 'user_private'] as const;
export type SourceScope = (typeof SOURCE_SCOPES)[number];

export const SOURCE_QUALITIES = [
  'primary_substantive',
  'secondary',
  'bibliographic_only',
  'unverified',
] as const;
export type SourceQuality = (typeof SOURCE_QUALITIES)[number];

/**
 * Section 8.3 source record, field for field. One deliberate addition:
 * the optional `version` string. Section 8.3 speaks of a source version
 * ("immutable within source version"; each evidence unit carries "a source
 * version/hash") without naming a version field, so when `version` is
 * absent the record's content_sha256 IS the source version. See
 * sourceVersionOf and format assumption A3 in this package's README.
 */
export const sourceRecordSchema = z.strictObject({
  source_id: idSchema,
  work_id: idSchema,
  work_title: z.string().min(1),
  credited_authors: z.array(z.string().min(1)).min(1),
  original_speaker: z.string().min(1).nullable(),
  source_type: z.enum(SOURCE_TYPES),
  publisher_or_host: z.string().min(1).nullable(),
  edition_or_publication_date: z.string().min(1).nullable(),
  retrieved_at: z.string().min(1),
  canonical_url: z.string().min(1).nullable(),
  /** Never expose filesystem paths in a pack; this is an opaque ID only. */
  private_asset_id: idSchema.nullable(),
  content_sha256: sha256Schema,
  rights_status: z.enum(RIGHTS_STATUSES),
  allowed_scope: z.enum(SOURCE_SCOPES),
  locators: z.array(sourceLocatorSchema),
  quality: z.enum(SOURCE_QUALITIES),
  version: z.string().min(1).optional(),
});
export type SourceRecord = z.infer<typeof sourceRecordSchema>;

/** The version a quote tuple or evidence unit must name for this record. */
export function sourceVersionOf(record: SourceRecord): string {
  return record.version ?? record.content_sha256;
}

/**
 * Concept marks from Section 8.1 step 5. Bibliographic references,
 * extracted text, author statements, third-party commentary, and BlackCEO
 * adaptations are separate evidence types and are never merged.
 */
export const CONCEPT_MARKS = [
  'direct_teaching',
  'paraphrase',
  'reported_example',
  'third_party_commentary',
  'blackceo_adaptation',
] as const;
export type ConceptMark = (typeof CONCEPT_MARKS)[number];

export const EVIDENCE_KINDS = [
  'concept',
  'application_case',
  'quotation',
] as const;
export type EvidenceKind = (typeof EVIDENCE_KINDS)[number];

/**
 * One evidence unit (Section 8.3): source version/hash, exact locator,
 * original speaker, a concise paraphrase or permitted excerpt, and the
 * seat/claim IDs it supports. An evidence unit establishes provenance; it
 * does not assert that the teaching is objectively correct.
 */
export const evidenceUnitSchema = z.strictObject({
  evidence_id: idSchema,
  source_id: idSchema,
  source_version: z.string().min(1),
  locator: sourceLocatorSchema,
  kind: z.enum(EVIDENCE_KINDS),
  mark: z.enum(CONCEPT_MARKS),
  original_speaker: z.string().min(1).nullable(),
  /** Permitted excerpt text; the only text a quotation may be checked against. */
  excerpt: z.string().min(1).nullable(),
  paraphrase: z.string().min(1).nullable(),
  claim_ids: z.array(idSchema),
  seat_id: seatIdSchema,
});
export type EvidenceUnit = z.infer<typeof evidenceUnitSchema>;

/** A source whose use has been withdrawn (Section 8.6), supplied by audit. */
export const revocationSchema = z.strictObject({
  source_id: idSchema,
  revoked_at: z.string().min(1),
  reason: z.string().min(1),
});
export type SourceRevocation = z.infer<typeof revocationSchema>;

/** One validator finding. Errors fail validation; warnings do not. */
export interface Diagnostic {
  code: string;
  severity: 'error' | 'warning';
  message: string;
  /** Dotted path into the validated input, when one applies. */
  path?: string;
}

export function errorDiagnostic(
  code: string,
  message: string,
  path?: string,
): Diagnostic {
  return { code, severity: 'error', message, path };
}

export function warningDiagnostic(
  code: string,
  message: string,
  path?: string,
): Diagnostic {
  return { code, severity: 'warning', message, path };
}

export function hasErrors(diagnostics: readonly Diagnostic[]): boolean {
  return diagnostics.some((d) => d.severity === 'error');
}
