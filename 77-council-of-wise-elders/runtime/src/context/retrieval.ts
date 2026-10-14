/**
 * CWE-022 authorized retrieval (directive Sections 8.6, 9.2, 28.2).
 *
 * Every retrieval passes the CWE-007 authorization ports with the
 * caller's trusted principal:
 *
 * 1. The session gate runs first (assertSessionRead). A denied caller
 *    gets the CWE-007 AuthorizationError and the catalog is never
 *    touched: no headers are listed, no content is loaded.
 * 2. Each candidate header is then decided with the same port
 *    (checkSessionRead against the material's own scope and
 *    visibility). Cross-tenant, cross-company, and cross-installation
 *    material is skipped; private material is admitted only for its
 *    owner (or an auditable host-granted support read, exactly as the
 *    CWE-007 session rule allows); company scope alone never admits
 *    private material.
 * 3. Source-scope rules from Section 8.3 apply on top: a user_private
 *    source is admitted only for its owner, and never into an assembly
 *    marked distributable (the CWE-012 condition 3 bar on the Brunson
 *    private-scope record). A revoked source (Section 8.6) is excluded
 *    from retrieval. Only evidence named by the frozen brief manifest,
 *    with a matching content hash, is admitted.
 * 4. Skips are silent and total: the result contains only admitted
 *    items. There are no exclusion counts, no skipped digests, and no
 *    error text derived from skipped material, so an out-of-scope item
 *    cannot be detected from any output of this layer.
 * 5. Content loads only for admitted IDs, and every loaded candidate is
 *    revalidated against the CWE-012 schemas and cross-checked (unit
 *    cites the record, version matches sourceVersionOf, canonical hash
 *    matches the header and the frozen manifest) before it becomes a
 *    RetrievedItem. A candidate that fails validation after admission
 *    fails the retrieval with a generic ContextError; no partial
 *    candidate set is returned.
 */
import {
  assertSessionRead,
  checkSessionRead,
  type AccessVia,
  type TrustedPrincipal,
} from '../authorization/index.js';
import {
  SEAT_IDS,
  canonicalHash,
  type EvidenceManifestEntry,
  type SeatId,
} from '../contracts/index.js';
import {
  evidenceUnitSchema,
  sourceRecordSchema,
  sourceVersionOf,
} from '../sources/schemas.js';
import { validateExportPackage, type Skill22ExportPackage } from '../sources/export-package.js';
import {
  ContextError,
  type CandidateHeader,
  type ItemProvenance,
  type MaterialCatalog,
  type RetrievedItem,
  type SessionAccessTarget,
} from './types.js';

export interface RetrievalOptions {
  /** True when the assembly will be marked distributable. */
  readonly distributable?: boolean;
  /** Source IDs withdrawn under Section 8.6. */
  readonly revokedSourceIds?: ReadonlySet<string>;
}

export interface RetrievalResult {
  readonly items: readonly RetrievedItem[];
  /** How the session gate admitted the caller (owner, company, support). */
  readonly access_via: AccessVia;
}

function seatOrder(seatId: SeatId): number {
  return (SEAT_IDS as readonly string[]).indexOf(seatId);
}

/** Deterministic candidate order: roster order, then evidence ID. */
export function compareHeaders(a: CandidateHeader, b: CandidateHeader): number {
  const bySeat = seatOrder(a.seat_id) - seatOrder(b.seat_id);
  if (bySeat !== 0) return bySeat;
  return a.evidence_id < b.evidence_id ? -1 : a.evidence_id > b.evidence_id ? 1 : 0;
}

function headerAdmitted(
  principal: TrustedPrincipal,
  header: CandidateHeader,
  manifestById: ReadonlyMap<string, EvidenceManifestEntry>,
  options: RetrievalOptions,
): boolean {
  // The CWE-007 port decides scope and visibility for the material
  // itself, with the same rule it applies to sessions.
  const decision = checkSessionRead(principal, {
    scope: header.scope,
    visibility: header.visibility,
  });
  if (!decision.allowed) return false;
  // Section 8.3 source scope: user_private material belongs to its
  // owner alone, whatever the session visibility says.
  if (
    header.allowed_scope === 'user_private' &&
    header.scope.owner_subject !== principal.subject
  ) {
    return false;
  }
  // CWE-012 condition 3: private-scope material never enters an
  // assembly marked distributable.
  if (options.distributable === true && header.allowed_scope === 'user_private') {
    return false;
  }
  // Section 8.6: a revoked source is excluded from future retrieval.
  if (options.revokedSourceIds?.has(header.source_id)) return false;
  // Frozen-manifest membership with hash equality (Section 11.6): the
  // assembly may only draw on the brief's frozen evidence, byte-exact.
  const entry = manifestById.get(header.evidence_id);
  if (!entry || entry.sha256 !== header.sha256) return false;
  return true;
}

function toRetrievedItem(
  candidate: NonNullable<ReturnType<MaterialCatalog['loadCandidate']>>,
): RetrievedItem {
  const { source, unit } = candidate;
  const text = unit.excerpt ?? unit.paraphrase;
  if (text === null) {
    throw new ContextError(
      'CONTEXT_CANDIDATE_INVALID',
      'An authorized candidate failed provenance validation.',
    );
  }
  const provenance: ItemProvenance = {
    source_id: source.source_id,
    source_version: sourceVersionOf(source),
    locator: { kind: unit.locator.kind, value: unit.locator.value },
    quality: source.quality,
    verification_status: source.quality === 'primary_substantive' ? 'verified' : 'unverified',
    rights_status: source.rights_status,
    allowed_scope: source.allowed_scope,
    original_speaker: unit.original_speaker,
    mark: unit.mark,
  };
  return {
    evidence_id: unit.evidence_id,
    seat_id: unit.seat_id,
    text,
    provenance,
  };
}

/**
 * Retrieve the authorized candidate set for one session and one frozen
 * brief manifest. Throws the CWE-007 AuthorizationError when the
 * session gate denies the caller, and ContextError when an admitted
 * candidate fails provenance validation.
 */
export function retrieveAuthorizedMaterial(args: {
  principal: TrustedPrincipal;
  session: SessionAccessTarget;
  manifest: readonly EvidenceManifestEntry[];
  catalog: MaterialCatalog;
  options?: RetrievalOptions;
}): RetrievalResult {
  const options = args.options ?? {};
  // Session gate first: on denial this throws before the catalog is
  // touched, so a denied caller learns nothing about the catalog.
  const accessVia = assertSessionRead(args.principal, args.session);

  const manifestById = new Map(args.manifest.map((e) => [e.evidence_id, e]));
  const headers = [...args.catalog.listCandidateHeaders()].sort(compareHeaders);
  const items: RetrievedItem[] = [];
  for (const header of headers) {
    if (!headerAdmitted(args.principal, header, manifestById, options)) continue;
    const candidate = args.catalog.loadCandidate(header.evidence_id);
    if (candidate === null) {
      throw new ContextError(
        'CONTEXT_CANDIDATE_INVALID',
        'An authorized candidate failed provenance validation.',
      );
    }
    const source = sourceRecordSchema.safeParse(candidate.source);
    const unit = evidenceUnitSchema.safeParse(candidate.unit);
    if (!source.success || !unit.success) {
      throw new ContextError(
        'CONTEXT_CANDIDATE_INVALID',
        'An authorized candidate failed provenance validation.',
      );
    }
    if (
      unit.data.evidence_id !== header.evidence_id ||
      unit.data.seat_id !== header.seat_id ||
      unit.data.source_id !== source.data.source_id ||
      unit.data.source_version !== sourceVersionOf(source.data) ||
      canonicalHash(unit.data) !== header.sha256
    ) {
      throw new ContextError(
        'CONTEXT_CANDIDATE_INVALID',
        'An authorized candidate failed provenance validation.',
      );
    }
    items.push(toRetrievedItem({ header, source: source.data, unit: unit.data }));
  }
  return { items, access_via: accessVia };
}

/**
 * Package pre-flight: run the CWE-012 export package validator over the
 * packages an assembly will draw on. A package the validator does not
 * accept (unknown seat, evidence citing a source it does not carry,
 * version mismatch, revoked source) fails here with a generic error,
 * before any retrieval happens. Diagnostic detail stays with the
 * validator's own audit surface; it is never copied into context errors.
 */
export function assertPackagesValid(
  packages: readonly Skill22ExportPackage[],
  revokedSourceIds?: ReadonlySet<string>,
): void {
  for (const pkg of packages) {
    const result = validateExportPackage(pkg, { revokedSourceIds });
    if (!result.accepted) {
      throw new ContextError(
        'CONTEXT_PACKAGE_INVALID',
        'A source package failed validation and cannot supply context.',
      );
    }
  }
}
