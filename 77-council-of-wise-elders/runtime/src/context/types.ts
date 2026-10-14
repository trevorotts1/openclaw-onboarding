/**
 * CWE-022 authorized retrieval and bounded context assembly: shared types
 * (directive Sections 8, 9, 13; graph product bounded-authorized-context).
 *
 * The design rule that shapes everything here: authorization is decided
 * from metadata headers BEFORE any content loads. A catalog exposes
 * content-free headers (scope, visibility, provenance enums, and a
 * content hash) for every candidate; the retrieval layer admits or
 * silently skips each header using the CWE-007 authorization ports; and
 * content is loaded only for admitted evidence IDs. Material outside the
 * caller's scope therefore never enters the assembly candidate set, and
 * nothing about it (not its text, not its title, not a count, not a
 * digest) can appear in an assembly, a result, or an error message.
 */
import type {
  ScopeFields,
  SeatId,
  SessionVisibility,
} from '../contracts/index.js';
import type {
  EvidenceUnit,
  RightsStatus,
  SourceQuality,
  SourceRecord,
  SourceScope,
} from '../sources/schemas.js';

/** Operations a bounded context can be assembled for (Section 9). */
export type ContextOperation =
  | 'round_1_opening'
  | 'round_2_response'
  | 'round_3_ratification'
  | 'consult'
  | 'synthesis';

/** The session a retrieval runs against: trusted scope plus visibility. */
export interface SessionAccessTarget {
  readonly scope: ScopeFields;
  readonly visibility: SessionVisibility;
}

/**
 * Content-free candidate metadata. Carries no text of any kind: no
 * excerpt, no paraphrase, no title, no claim text. The sha256 is the
 * canonical hash of the evidence unit (the same value the frozen brief
 * manifest records), so provenance can be checked before content loads.
 */
export interface CandidateHeader {
  readonly evidence_id: string;
  /** Evidence units always belong to a seat (CWE-012 evidence schema). */
  readonly seat_id: SeatId;
  readonly scope: ScopeFields;
  readonly visibility: SessionVisibility;
  readonly source_id: string;
  readonly allowed_scope: SourceScope;
  readonly sha256: string;
}

/** A fully loaded candidate: the CWE-012 source record and evidence unit. */
export interface MaterialCandidate {
  readonly header: CandidateHeader;
  readonly source: SourceRecord;
  readonly unit: EvidenceUnit;
}

/**
 * The material catalog port. Hosts back this with the pack store and the
 * scoped session store (CWE-006); the context layer depends only on this
 * shape. Implementations must honor the port's discipline:
 * listCandidateHeaders returns metadata for every candidate it holds,
 * and loadCandidate is called only with evidence IDs the retrieval
 * layer already admitted.
 */
export interface MaterialCatalog {
  listCandidateHeaders(): readonly CandidateHeader[];
  loadCandidate(evidenceId: string): MaterialCandidate | null;
}

/**
 * Provenance carried by every assembled item (Section 8.3). The quality
 * label is the CWE-012 record's own label, carried verbatim and never
 * upgraded: unverified stays unverified, bibliographic_only stays
 * bibliographic_only. verification_status uses the host-stamp vocabulary
 * (verified | unverified) and is 'verified' only for a
 * primary_substantive record; every real record in the current build is
 * unverified or bibliographic_only, so real assemblies label items
 * unverified, matching the CWE-012 acceptance conditions.
 */
export interface ItemProvenance {
  readonly source_id: string;
  readonly source_version: string;
  readonly locator: { readonly kind: 'page' | 'timestamp' | 'section'; readonly value: string };
  readonly quality: SourceQuality;
  readonly verification_status: 'verified' | 'unverified';
  readonly rights_status: RightsStatus;
  readonly allowed_scope: SourceScope;
  readonly original_speaker: string | null;
  readonly mark: EvidenceUnit['mark'];
}

/** One retrieved, authorized, provenance-carrying context item. */
export interface RetrievedItem {
  readonly evidence_id: string;
  readonly seat_id: SeatId;
  readonly text: string;
  readonly provenance: ItemProvenance;
}

/** Typed context-layer failure. Messages never carry item content or IDs. */
export class ContextError extends Error {
  readonly code:
    | 'CONTEXT_BRIEF_INVALID'
    | 'CONTEXT_CANDIDATE_INVALID'
    | 'CONTEXT_PACKAGE_INVALID'
    | 'CONTEXT_ROUTE_INVALID'
    | 'CONTEXT_SESSION_UNAVAILABLE';

  constructor(
    code: ContextError['code'],
    message: string,
  ) {
    super(message);
    this.name = 'ContextError';
    this.code = code;
  }
}
