/**
 * Skill 22 export package validation (CWE-012, Sections 8.5 and 34).
 *
 * The Skill 22 exporter (CWE-011) emits source records and evidence for
 * one seat at a time; this module is the receiving contract. The
 * exporter must reject unsupported source references and preserve
 * authorship and provenance metadata (Section 8.5): a package whose
 * evidence cites a source it does not carry, whose quotation evidence
 * lost its original speaker, or whose claimed titles are not backed by
 * records is rejected here with the same named diagnostics the pack
 * validator uses, so integration drift surfaces as a diagnostic, not a
 * silent format fork.
 *
 * FORMAT ASSUMPTION A1 (see README): the export package is expected to
 * carry Section 8.3 source records and evidence units under the field
 * names used here. Drift between this reading and CWE-011's emitted
 * packages is reconciled at the integration review, per the build plan.
 */

import type { PackQualification, WorkCoverage } from './coverage';
import { isSeatId, validateAdvisorPack, type PackValidationOptions } from './packs';
import { errorDiagnostic, hasErrors, type Diagnostic } from './schemas';

export interface Skill22ExportPackage {
  seat_id: string;
  pack_version: string;
  /** Section 8.3 source records (full records, not stubs). */
  sources: readonly unknown[];
  /** Evidence units for this seat. */
  evidence: readonly unknown[];
  /** Foundation titles the package claims to cover, if it claims any. */
  claimed_titles?: readonly string[];
}

export interface ExportPackageValidation {
  accepted: boolean;
  qualification: PackQualification | null;
  works: WorkCoverage[];
  diagnostics: Diagnostic[];
}

export function validateExportPackage(
  pkg: Skill22ExportPackage,
  options: PackValidationOptions = {},
): ExportPackageValidation {
  const diagnostics: Diagnostic[] = [];
  if (!isSeatId(pkg.seat_id)) {
    diagnostics.push(
      errorDiagnostic(
        'REGISTRY_UNKNOWN_SEAT',
        `Export package seat ${pkg.seat_id} is not one of the nine approved seats.`,
      ),
    );
    return { accepted: false, qualification: null, works: [], diagnostics };
  }
  // Route through the pack validator so one rule set governs both
  // surfaces: the package is a pack whose profile/coverage claims are
  // exactly the ones it makes, no more.
  const validation = validateAdvisorPack(
    {
      folder: pkg.seat_id,
      profile: {
        seat_id: pkg.seat_id,
        pack_version: pkg.pack_version,
        pack_status: 'in_progress',
        profile_label: '__export__',
        source_basis: (pkg.claimed_titles ?? []).map((title) => ({ title })),
      },
      sources: { records: [...pkg.sources], evidence: [...pkg.evidence] },
      coverage: { claimed_titles: [...(pkg.claimed_titles ?? [])] },
    },
    { ...options, expectProductionReady: false },
  );
  // The export surface has no profile file, so the pack-level label and
  // status checks do not apply to it; every other diagnostic stands.
  const relevant = validation.diagnostics.filter(
    (d) =>
      d.code !== 'PROFILE_LABEL_MISSING' &&
      d.code !== 'PROFILE_LABEL_MISMATCH' &&
      d.code !== 'FOUNDATION_NOT_SUBSTANTIVE',
  );
  diagnostics.push(...relevant);

  // Claimed-title presence is enforced by the pack route above: claimed
  // titles are passed as both source_basis and coverage claims, and the
  // pack validator checks them against carried records AND carried
  // bibliographic stubs (assumption A4), which is the correct presence
  // rule for an export that honestly registers absent works.

  // Qualification and per-work coverage come from the pack validation,
  // whose computation is stub-aware; recomputing here from full records
  // alone would misclassify stub-registered works as missing.
  const { qualification, works } = validation;
  return {
    accepted: !hasErrors(diagnostics),
    qualification,
    works,
    diagnostics,
  };
}
