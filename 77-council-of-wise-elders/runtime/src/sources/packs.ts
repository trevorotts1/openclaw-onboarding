/**
 * Advisor pack validation (CWE-012): the structural and substantive
 * audit of one seat's pack, plus the seat registry checks (T001) and
 * the T. D. Jakes one-seat-three-lenses structure (T003 groundwork).
 *
 * Packs are validated from parsed file contents, never from filenames:
 * a file named like a book is not the book (Sections 8.2, 39.5). The
 * validator distinguishes all four source classes the directive names:
 * bibliographic-only, primary teaching, complete-book extraction, and
 * BlackCEO adaptation (a concept mark, never foundation evidence), and
 * it reports coverage honestly: a pack whose foundation is not
 * substantiated is labeled, not silently passed and not fabricated.
 */

import {
  SEAT_IDS,
  SEAT_ROSTER,
  advisorProfileLabel,
  type SeatId,
} from '../contracts/enums.js';

const SEAT_ID_SET: ReadonlySet<string> = new Set(SEAT_IDS);

/** Type guard the contracts package does not export; defined locally. */
export function isSeatId(value: string): value is SeatId {
  return SEAT_ID_SET.has(value);
}
import {
  computePackQualification,
  type PackQualification,
  type WorkCoverage,
} from './coverage.js';
import {
  errorDiagnostic,
  evidenceUnitSchema,
  hasErrors,
  sourceRecordSchema,
  warningDiagnostic,
  type Diagnostic,
  type EvidenceUnit,
  type SourceRecord,
} from './schemas.js';
import { normalizeTitle } from './text.js';

/** Pack-level claim surface the validator audits (parsed JSON files). */
export interface PackInput {
  /** Seat folder name the pack was loaded from. */
  folder: string;
  profile: Record<string, unknown>;
  sources: Record<string, unknown>;
  coverage: Record<string, unknown>;
  frameworks?: Record<string, unknown>;
  decisionRules?: Record<string, unknown>;
  failurePatterns?: Record<string, unknown>;
  questions?: Record<string, unknown>;
  evals?: Record<string, unknown>;
  /** Free text of briefing.md and communication.md, when present. */
  markdownTexts?: readonly string[];
}

export interface PackValidationOptions {
  /**
   * Audit context: a pack compiled for a shared pack may not draw on
   * tenant or user_private sources at all (T012 leakage boundary).
   */
  contextScope?: 'shared_pack' | 'tenant' | 'user_private';
  /** Source IDs withdrawn under Section 8.6. */
  revokedSourceIds?: ReadonlySet<string>;
  /** Fail the pack when its foundation is below the substantive gate. */
  expectProductionReady?: boolean;
}

export interface PackValidation {
  valid: boolean;
  seat_id: SeatId | null;
  pack_version: string | null;
  qualification: PackQualification | null;
  works: WorkCoverage[];
  records: SourceRecord[];
  evidence: EvidenceUnit[];
  diagnostics: Diagnostic[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/**
 * Source-content injection screen (T012): source material that carries
 * instruction-like payload aimed at the consuming model cannot acquire
 * authority. The screen is deliberately narrow and documented: these
 * phrases mark an attempt to instruct the reader-model, which legitimate
 * teaching excerpts do not do.
 */
const INJECTION_PATTERNS: readonly RegExp[] = [
  /ignore (all )?(previous|prior|above) instructions/i,
  /disregard (the )?(system|previous|prior) (prompt|instructions)/i,
  /you are now (a|an) /i,
  /reveal (the )?(system prompt|your instructions)/i,
  /<\s*(system|assistant|developer)\s*>/i,
];

function containsInjection(text: string): boolean {
  return INJECTION_PATTERNS.some((p) => p.test(text));
}

/** A filesystem path must never appear where an opaque asset ID belongs. */
function looksLikePath(text: string): boolean {
  return /(^|\s)(\/|~\/|[A-Za-z]:\\)/.test(text) ||
    /\.(pdf|epub|mp3|mp4|txt|md)$/i.test(text.trim());
}

/** T001: the registry holds exactly the nine approved seat IDs. */
export function validateSeatRegistry(seatIds: readonly string[]): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const seen = new Set<string>();
  for (const id of seatIds) {
    if (!isSeatId(id)) {
      diagnostics.push(
        errorDiagnostic(
          'REGISTRY_UNKNOWN_SEAT',
          `Seat ID ${id} is not one of the nine approved seats.`,
        ),
      );
    } else if (seen.has(id)) {
      diagnostics.push(
        errorDiagnostic(
          'REGISTRY_DUPLICATE_SEAT',
          `Seat ID ${id} appears more than once in the registry.`,
        ),
      );
    }
    seen.add(id);
  }
  for (const id of SEAT_IDS) {
    if (!seen.has(id)) {
      diagnostics.push(
        errorDiagnostic(
          'REGISTRY_MISSING_SEAT',
          `Approved seat ${id} is missing from the registry.`,
        ),
      );
    }
  }
  return diagnostics;
}

interface StagedSources {
  records: SourceRecord[];
  evidence: EvidenceUnit[];
  /** Titles present as bibliographic stubs (acknowledged, not ingested). */
  stubTitles: string[];
  diagnostics: Diagnostic[];
}

/**
 * Stage source records and evidence out of a sources.json payload.
 * Records are full Section 8.3 records or bibliographic stubs shaped
 * {title, ...} (format assumption A4). Embedded per-record `evidence`
 * arrays and a top-level `evidence` array are both accepted (A5).
 */
function stageSources(sources: Record<string, unknown>): StagedSources {
  const diagnostics: Diagnostic[] = [];
  const records: SourceRecord[] = [];
  const evidence: EvidenceUnit[] = [];
  const stubTitles: string[] = [];
  const rawRecords = Array.isArray(sources.records) ? sources.records : [];

  const pushEvidence = (raw: unknown, where: string) => {
    if (!isRecord(raw)) {
      diagnostics.push(
        errorDiagnostic('EVIDENCE_INVALID', 'Evidence unit is not an object.', where),
      );
      return;
    }
    const locator = isRecord(raw.locator) ? raw.locator : null;
    if (
      !locator || typeof locator.value !== 'string' ||
      locator.value.trim().length === 0
    ) {
      diagnostics.push(
        errorDiagnostic(
          'EVIDENCE_LOCATOR_MISSING',
          'An evidence unit without an exact locator cannot ground a claim.',
          where,
        ),
      );
      return;
    }
    const parsed = evidenceUnitSchema.safeParse(raw);
    if (!parsed.success) {
      diagnostics.push(
        errorDiagnostic(
          'EVIDENCE_INVALID',
          `Evidence unit fails the evidence contract: ${parsed.error.issues[0]?.message ?? 'unknown'}`,
          where,
        ),
      );
      return;
    }
    evidence.push(parsed.data);
  };

  rawRecords.forEach((raw, i) => {
    const where = `sources.records[${i}]`;
    if (!isRecord(raw)) {
      diagnostics.push(
        errorDiagnostic('SOURCE_RECORD_INVALID', 'Source entry is not an object.', where),
      );
      return;
    }
    if (
      typeof raw.private_asset_id === 'string' &&
      looksLikePath(raw.private_asset_id)
    ) {
      diagnostics.push(
        errorDiagnostic(
          'PRIVATE_PATH_LEAK',
          'private_asset_id carries a filesystem path. Packs carry opaque asset IDs only; filesystem paths are never exposed.',
          where,
        ),
      );
    }
    if (typeof raw.source_id !== 'string') {
      // Bibliographic stub: a title acknowledged as not yet ingested.
      const title = asString(raw.title) ?? asString(raw.work_title);
      if (title) stubTitles.push(title);
      return;
    }
    const embedded = Array.isArray(raw.evidence) ? raw.evidence : [];
    const { evidence: _omit, ...recordCandidate } = raw;
    const parsed = sourceRecordSchema.safeParse(recordCandidate);
    if (!parsed.success) {
      diagnostics.push(
        errorDiagnostic(
          'SOURCE_RECORD_INVALID',
          `Source record fails the Section 8.3 contract: ${parsed.error.issues[0]?.message ?? 'unknown'}`,
          where,
        ),
      );
      return;
    }
    records.push(parsed.data);
    embedded.forEach((e, j) => pushEvidence(e, `${where}.evidence[${j}]`));
  });
  if (Array.isArray(sources.evidence)) {
    sources.evidence.forEach((e, j) => pushEvidence(e, `sources.evidence[${j}]`));
  }

  const seenIds = new Set<string>();
  for (const record of records) {
    if (seenIds.has(record.source_id)) {
      diagnostics.push(
        errorDiagnostic(
          'SOURCE_DUPLICATE_ID',
          `Source ID ${record.source_id} appears more than once in the pack.`,
        ),
      );
    }
    seenIds.add(record.source_id);
  }
  const recordById = new Map(records.map((r) => [r.source_id, r]));
  for (const unit of evidence) {
    const record = recordById.get(unit.source_id);
    if (!record) {
      diagnostics.push(
        errorDiagnostic(
          'EVIDENCE_SOURCE_UNKNOWN',
          `Evidence ${unit.evidence_id} cites source ${unit.source_id}, which is not in the pack.`,
        ),
      );
      continue;
    }
    const expected = record.version ?? record.content_sha256;
    if (unit.source_version !== expected) {
      diagnostics.push(
        errorDiagnostic(
          'EVIDENCE_VERSION_MISMATCH',
          `Evidence ${unit.evidence_id} names version ${unit.source_version}; the record's version is ${expected}.`,
        ),
      );
    }
    if (unit.kind === 'quotation' && unit.excerpt === null) {
      diagnostics.push(
        errorDiagnostic(
          'EVIDENCE_TEXT_MISSING',
          `Quotation evidence ${unit.evidence_id} carries no excerpt text to verify against.`,
        ),
      );
    }
    if (
      unit.kind === 'concept' && unit.excerpt === null && unit.paraphrase === null
    ) {
      diagnostics.push(
        errorDiagnostic(
          'EVIDENCE_TEXT_MISSING',
          `Concept evidence ${unit.evidence_id} carries neither an excerpt nor a paraphrase.`,
        ),
      );
    }
  }
  return { records, evidence, stubTitles, diagnostics };
}

/**
 * Validate one advisor pack. Structural failures, coverage dishonesty,
 * revoked or leaking sources, and foundation shortfalls are all named
 * diagnostics; `valid` is true exactly when no error diagnostic exists.
 */
export function validateAdvisorPack(
  pack: PackInput,
  options: PackValidationOptions = {},
): PackValidation {
  const diagnostics: Diagnostic[] = [];
  const profile = pack.profile;
  const seatRaw = asString(profile.seat_id);
  const seatId: SeatId | null = seatRaw !== null && isSeatId(seatRaw)
    ? seatRaw
    : null;

  if (seatId === null) {
    diagnostics.push(
      errorDiagnostic(
        'REGISTRY_UNKNOWN_SEAT',
        `Profile seat_id ${seatRaw ?? '(missing)'} is not one of the nine approved seats.`,
        'profile.seat_id',
      ),
    );
  } else {
    if (pack.folder !== seatId) {
      diagnostics.push(
        errorDiagnostic(
          'PROFILE_SEAT_MISMATCH',
          `Pack folder ${pack.folder} does not match profile seat ${seatId}.`,
          'profile.seat_id',
        ),
      );
    }
    const roster = SEAT_ROSTER.find((s) => s.seat_id === seatId);
    if (roster) {
      const label = asString(profile.profile_label);
      if (label === null) {
        diagnostics.push(
          errorDiagnostic(
            'PROFILE_LABEL_MISSING',
            'Every advisor profile carries the attribution label; this profile has none.',
            'profile.profile_label',
          ),
        );
      } else if (label !== advisorProfileLabel(roster.display_name)) {
        diagnostics.push(
          errorDiagnostic(
            'PROFILE_LABEL_MISMATCH',
            `Profile label does not equal the required attribution label for ${roster.display_name}.`,
            'profile.profile_label',
          ),
        );
      }
      const name = asString(profile.name);
      if (name !== null && name !== roster.display_name) {
        diagnostics.push(
          errorDiagnostic(
            'PROFILE_NAME_MISMATCH',
            `Profile name ${name} does not match the roster name ${roster.display_name}.`,
            'profile.name',
          ),
        );
      }
      // Jakes: three lenses, ONE seat, ONE vote (Section 7.3).
      if (seatId === 'td-jakes') {
        const votes = profile.votes;
        if (typeof votes === 'number' && votes !== 1) {
          diagnostics.push(
            errorDiagnostic(
              'JAKES_VOTE_INFLATION',
              'The Jakes seat declares more than one vote. Three lenses are one seat, never three votes.',
              'profile.votes',
            ),
          );
        }
        const declared = profile.lenses;
        if (Array.isArray(declared)) {
          for (const entry of declared) {
            // Lens entries are lens ID strings or {lens_id, ...} objects.
            const lens = typeof entry === 'string'
              ? entry
              : isRecord(entry)
                ? asString(entry.lens_id) ?? asString(entry.lens) ??
                  asString(entry.id)
                : null;
            if (
              lens === null ||
              !(roster.lenses as readonly string[]).includes(lens)
            ) {
              diagnostics.push(
                errorDiagnostic(
                  'JAKES_LENS_UNKNOWN',
                  `Declared lens ${lens ?? '(unreadable entry)'} is not one of the seat's three lenses.`,
                  'profile.lenses',
                ),
              );
            }
          }
        }
      }
    }
  }

  const staged = stageSources(pack.sources);
  diagnostics.push(...staged.diagnostics);
  const { records, evidence } = staged;

  // Revocation, scope, rights hygiene, injection, and path leakage.
  for (const record of records) {
    if (options.revokedSourceIds?.has(record.source_id)) {
      diagnostics.push(
        errorDiagnostic(
          'SOURCE_REVOKED',
          `Source ${record.source_id} has been revoked and is excluded from retrieval.`,
        ),
      );
    }
    if (
      (options.contextScope ?? 'shared_pack') === 'shared_pack' &&
      record.allowed_scope !== 'shared_pack'
    ) {
      diagnostics.push(
        errorDiagnostic(
          'SOURCE_SCOPE_LEAK',
          `Source ${record.source_id} is scoped ${record.allowed_scope}; it cannot appear in a shared pack audit.`,
        ),
      );
    }
    const asset = record.private_asset_id;
    if (asset !== null && looksLikePath(asset)) {
      diagnostics.push(
        errorDiagnostic(
          'PRIVATE_PATH_LEAK',
          'private_asset_id carries a filesystem path. Packs carry opaque asset IDs only.',
        ),
      );
    }
  }
  for (const unit of evidence) {
    const texts = [unit.excerpt, unit.paraphrase].filter(
      (t): t is string => t !== null,
    );
    if (texts.some(containsInjection)) {
      diagnostics.push(
        errorDiagnostic(
          'SOURCE_INJECTION_CONTENT',
          `Evidence ${unit.evidence_id} carries instruction-like payload text and cannot acquire authority.`,
        ),
      );
    }
  }
  for (const text of pack.markdownTexts ?? []) {
    if (containsInjection(text)) {
      diagnostics.push(
        errorDiagnostic(
          'SOURCE_INJECTION_CONTENT',
          'Pack markdown carries instruction-like payload text.',
        ),
      );
    }
  }

  // Coverage honesty: claimed titles must exist; counts must not exceed
  // the evidence actually present; readiness must not exceed the gate.
  let qualification: PackQualification | null = null;
  let works: WorkCoverage[] = [];
  if (seatId !== null) {
    const gate = computePackQualification(seatId, records, evidence, staged.stubTitles);
    qualification = gate.qualification;
    works = gate.works;

    const presentTitles = new Set([
      ...records.map((r) => normalizeTitle(r.work_title)),
      ...staged.stubTitles.map(normalizeTitle),
    ]);
    const claimed = new Set<string>();
    const basis = Array.isArray(profile.source_basis) ? profile.source_basis : [];
    for (const entry of basis) {
      const title = isRecord(entry) ? asString(entry.title) : null;
      if (title) claimed.add(title);
    }
    if (Array.isArray(pack.coverage.claimed_titles)) {
      for (const t of pack.coverage.claimed_titles) {
        if (typeof t === 'string') claimed.add(t);
      }
    }
    for (const title of claimed) {
      if (!presentTitles.has(normalizeTitle(title))) {
        diagnostics.push(
          errorDiagnostic(
            'COVERAGE_TITLE_UNLISTED',
            `The pack claims ${title}, but no source record or bibliographic stub for it exists in the pack. A claimed title the source does not contain fails.`,
          ),
        );
      }
    }

    const covered = isRecord(pack.coverage.covered) ? pack.coverage.covered : {};
    const actualConcepts = works.reduce((n, w) => n + w.traceable_concepts, 0);
    const actualCases = works.reduce((n, w) => n + w.application_cases, 0);
    if (
      typeof covered.concepts === 'number' && covered.concepts > actualConcepts
    ) {
      diagnostics.push(
        errorDiagnostic(
          'COVERAGE_COUNT_INFLATED',
          `Coverage claims ${covered.concepts} concepts; the evidence present supports ${actualConcepts}.`,
          'coverage.covered.concepts',
        ),
      );
    }
    if (
      typeof covered.application_cases === 'number' &&
      covered.application_cases > actualCases
    ) {
      diagnostics.push(
        errorDiagnostic(
          'COVERAGE_COUNT_INFLATED',
          `Coverage claims ${covered.application_cases} application cases; the evidence present supports ${actualCases}.`,
          'coverage.covered.application_cases',
        ),
      );
    }

    const status = asString(profile.pack_status);
    const claimsReady =
      options.expectProductionReady === true ||
      (status !== null &&
        !['not_yet_built', 'scaffold', 'draft', 'in_progress'].includes(status));
    for (const work of works) {
      if (!work.gate_met) {
        const diag = claimsReady
          ? errorDiagnostic(
            'FOUNDATION_NOT_SUBSTANTIVE',
            `Required foundation ${work.title} is ${work.work_class}: ${work.traceable_concepts} traceable concepts and ${work.application_cases} application cases present, gate is 3 and 1. Publisher-only description cannot qualify this foundation.`,
          )
          : warningDiagnostic(
            'FOUNDATION_NOT_SUBSTANTIVE',
            `Required foundation ${work.title} is ${work.work_class}: ${work.traceable_concepts} traceable concepts and ${work.application_cases} application cases present, gate is 3 and 1.`,
          );
        diagnostics.push(diag);
      }
    }

    // Evaluation floor (Section 7.1): five case types before production.
    const evalCases = isRecord(pack.evals) && Array.isArray(pack.evals.cases)
      ? pack.evals.cases
      : null;
    if (evalCases !== null && evalCases.length < 5 && claimsReady) {
      diagnostics.push(
        errorDiagnostic(
          'EVALS_INCOMPLETE',
          `Pack claims readiness with ${evalCases.length} evaluation cases; at least five are required.`,
          'evals.cases',
        ),
      );
    }
  }

  // Framework and decision-rule claims must resolve to real evidence.
  const evidenceIds = new Set(evidence.map((u) => u.evidence_id));
  const checkClaims = (
    file: Record<string, unknown> | undefined,
    fileName: string,
  ) => {
    if (!file || !Array.isArray(file.items)) return;
    file.items.forEach((item, i) => {
      if (!isRecord(item)) return;
      const where = `${fileName}.items[${i}]`;
      const refs = item.source_evidence_ids;
      if (Array.isArray(refs)) {
        for (const ref of refs) {
          if (typeof ref === 'string' && !evidenceIds.has(ref)) {
            diagnostics.push(
              errorDiagnostic(
                'CLAIM_REFERENCE_UNKNOWN',
                `Claim cites evidence ${ref}, which is not in the pack.`,
                where,
              ),
            );
          }
        }
      }
      const ids = item.claim_ids;
      if (Array.isArray(ids)) {
        for (const ref of ids) {
          if (typeof ref === 'string' && !evidenceIds.has(ref)) {
            diagnostics.push(
              errorDiagnostic(
                'CLAIM_REFERENCE_UNKNOWN',
                `Claim cites ${ref}, which is not in the pack.`,
                where,
              ),
            );
          }
        }
      }
      if (
        item.attribution_kind === 'source_principle' &&
        (!Array.isArray(refs) || refs.length === 0) &&
        (!Array.isArray(ids) || ids.length === 0)
      ) {
        diagnostics.push(
          errorDiagnostic(
            'CLAIM_UNSUPPORTED',
            'A source_principle claim carries no source evidence reference. Sourced claims without locators are rejected.',
            where,
          ),
        );
      }
    });
  };
  checkClaims(pack.frameworks, 'frameworks');
  checkClaims(pack.decisionRules, 'decision-rules');

  return {
    valid: !hasErrors(diagnostics),
    seat_id: seatId,
    pack_version: asString(profile.pack_version),
    qualification,
    works,
    records,
    evidence,
    diagnostics,
  };
}

/**
 * Card-level source use (Sections 7.3, 16.6): lenses are recorded per
 * card for the Jakes seat only, from the seat's declared lens set, and
 * no card structure may turn one seat into multiple votes.
 */
export function validateCardSourceUse(card: {
  seat_id: string;
  lenses_used?: readonly string[];
  votes?: number;
}): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  if (!isSeatId(card.seat_id)) {
    diagnostics.push(
      errorDiagnostic(
        'REGISTRY_UNKNOWN_SEAT',
        `Card seat ${card.seat_id} is not one of the nine approved seats.`,
      ),
    );
    return diagnostics;
  }
  const roster = SEAT_ROSTER.find((s) => s.seat_id === card.seat_id);
  const lenses = card.lenses_used ?? [];
  if (card.seat_id !== 'td-jakes' && lenses.length > 0) {
    diagnostics.push(
      errorDiagnostic(
        'LENS_ON_WRONG_SEAT',
        `Seat ${card.seat_id} declares lenses_used; lenses exist only inside the Jakes seat.`,
      ),
    );
  }
  if (card.seat_id === 'td-jakes' && roster) {
    for (const lens of lenses) {
      if (!(roster.lenses as readonly string[]).includes(lens)) {
        diagnostics.push(
          errorDiagnostic(
            'JAKES_LENS_UNKNOWN',
            `Lens ${lens} is not one of the seat's three lenses.`,
          ),
        );
      }
    }
  }
  if (typeof card.votes === 'number' && card.votes !== 1) {
    diagnostics.push(
      errorDiagnostic(
        'JAKES_VOTE_INFLATION',
        'A card declares more than one vote for one seat.',
      ),
    );
  }
  return diagnostics;
}
