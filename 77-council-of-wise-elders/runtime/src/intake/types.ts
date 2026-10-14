/**
 * CWE-023 decision intake and revision management: shared types
 * (directive Sections 9, 10, 11; graph product intake-and-brief-revisions).
 *
 * The design rules that shape this module:
 *
 * - Intake is a resumable question flow over stable question IDs. Every
 *   answer is saved immediately (an intake revision), so an interrupted
 *   intake resumes at the exact step with the exact partial answers.
 *   The current step is a pure function of the saved draft.
 * - Briefs are immutable revisions. Composing an answer that changes
 *   brief content produces the NEXT brief revision with its canonical
 *   content hash; nothing ever edits a saved revision in place, and a
 *   writer holding a stale intake revision gets a typed conflict,
 *   never a silent overwrite.
 * - The client's preference is a separate record (client_preference_private).
 *   The brief carries only its opaque reference ID. The preference value
 *   never enters the brief body, the frozen evidence manifest, or any
 *   assembled context (CWE-022 enforces the context side; this module
 *   owns the storage side).
 * - Freezing binds the brief revision, the evidence manifest hash, the
 *   panel assessment, and the pinned route snapshot into one record.
 *   After freeze, the intake refuses content edits; new factual input
 *   is queued as a proposed amendment against the frozen revision and
 *   is never applied to it.
 * - No clock, randomness, or ID generation lives here: hosts inject
 *   Clock and IdSource through the service constructor, exactly like
 *   the rest of the core.
 */
import type {
  CriticalDomain,
  DecisionBrief,
  DecisionOption,
  EvidenceManifestEntry,
  ScopeFields,
  SeatId,
  SessionMode,
  SessionVisibility,
  TypedFact,
} from '../contracts/index.js';

/** Schema/policy stamps for intake-owned records. */
export const INTAKE_SCHEMA_VERSION = 'wise-elders.intake/v1';
export const CRITICAL_DOMAIN_POLICY_VERSION = 'wise-elders.critical-domain-policy/v1';

/** Typed intake failure. Messages never carry private preference content. */
export class IntakeError extends Error {
  readonly code:
    | 'INTAKE_NOT_FOUND'
    | 'INTAKE_REVISION_CONFLICT'
    | 'INTAKE_FROZEN'
    | 'INTAKE_NOT_FROZEN'
    | 'INTAKE_BRIEF_INVALID'
    | 'INTAKE_QUESTION_UNKNOWN'
    | 'INTAKE_ANSWER_INVALID'
    | 'INTAKE_PANEL_INVALID'
    | 'INTAKE_ROUTE_NOT_FOUND'
    | 'INTAKE_NOT_READY'
    | 'INTAKE_SCOPE_MISMATCH'
    | 'INTAKE_STORE_CONFLICT';

  constructor(
    code: IntakeError['code'],
    message: string,
    readonly detail?: Readonly<Record<string, unknown>> | null,
  ) {
    super(message);
    this.name = 'IntakeError';
    this.code = code;
    this.detail = detail ?? null;
  }
}

// ---------------------------------------------------------------------------
// Intake answers (Section 9.1 brief fields, gathered one question at a time)
// ---------------------------------------------------------------------------

/**
 * Where a fact came from. Only client-confirmed and retrieval-confirmed
 * facts may enter the brief's facts. A standard-company scaffold
 * placeholder is `scaffold_unconfirmed`: it is recorded as an unknown,
 * never as claimed revenue, mission, or demand (T014).
 */
export type FactOrigin = 'client_statement' | 'retrieved_confirmed' | 'scaffold_unconfirmed';

export interface IntakeFact {
  readonly id: string;
  readonly statement: string;
  readonly origin: FactOrigin;
  /** Evidence IDs backing a retrieved fact; empty for client statements. */
  readonly evidence_ids: readonly string[];
  /** Short human source note for retrieved facts, for the review screen. */
  readonly source_ref: string | null;
}

/** Structured constraint kinds intake understands (Section 9.1). */
export type IntakeConstraintKind =
  | 'budget_cash'
  | 'time'
  | 'capacity'
  | 'obligation'
  | 'reversibility'
  | 'prohibition'
  | 'other';

export interface IntakeConstraint {
  readonly id: string;
  readonly description: string;
  readonly hard: boolean;
  readonly kind: IntakeConstraintKind;
  readonly applies_to_option_ids: readonly string[];
}

/**
 * Structured decision flags answered with the decision question. These
 * are the structured intake facts the deterministic critical-domain
 * classification (Section 12.7) reads; no keyword guessing is involved.
 */
export interface DecisionFlags {
  readonly involves_money_commitment: boolean;
  readonly involves_offer_or_pricing: boolean;
  readonly involves_rebrand_or_pivot: boolean;
  readonly involves_stakeholder_trust: boolean;
  readonly decision_is_communication: boolean;
  readonly involves_professional_domain: boolean;
}

export interface SuccessAnswer {
  readonly outcome: string | null;
  readonly horizon: string | null;
  /** True when the client explicitly stated the outcome is unknown. */
  readonly explicit_unknown: boolean;
}

/**
 * The intake's working answers. A null field means "not answered yet";
 * an empty array means "answered: none". The distinction is what lets
 * resume restore the exact step without re-asking.
 */
export interface IntakeAnswers {
  readonly decision: { readonly statement: string; readonly flags: DecisionFlags } | null;
  readonly options: readonly DecisionOption[] | null;
  readonly success: SuccessAnswer | null;
  readonly constraints: readonly IntakeConstraint[] | null;
  /** Client-stated facts only; retrieved facts live in known_facts. */
  readonly facts: readonly IntakeFact[] | null;
  readonly assumptions: readonly TypedFact[] | null;
  readonly unknowns: readonly TypedFact[] | null;
  readonly stakeholders: readonly string[] | null;
}

export const EMPTY_ANSWERS: IntakeAnswers = {
  decision: null,
  options: null,
  success: null,
  constraints: null,
  facts: null,
  assumptions: null,
  unknowns: null,
  stakeholders: null,
};

/** How the client chose the route for this intake (Section 13.1). */
export type RouteChoice =
  | { readonly kind: 'explicit'; readonly route_id: string }
  | { readonly kind: 'inherit_default' };

/** Identity evidence levels, verbatim from Section 13.2. */
export type RouteIdentityLevel =
  | 'configured'
  | 'transport_probed'
  | 'reported_identity'
  | 'resolved_identity_verified'
  | 'quality_qualified';

/** One client-configured selectable route, CWE-008 catalog semantics. */
export interface RouteCatalogEntry {
  readonly route_id: string;
  readonly requested_model_id: string | null;
  readonly reasoning_preference: string | null;
  readonly fallback_policy: 'none' | 'client_approved_only';
  readonly identity_level: RouteIdentityLevel;
}

/**
 * The pinned route snapshot recorded on the brief revision at freeze
 * (Sections 10, 13.1): the catalog entry as it was at pin time, with
 * its identity level and the canonical hash of the entry it came from.
 */
export interface RouteSnapshot {
  readonly route_id: string;
  readonly requested_model_id: string | null;
  readonly reasoning_preference: string | null;
  readonly fallback_policy: 'none' | 'client_approved_only';
  readonly identity_level: RouteIdentityLevel;
  readonly selection_source: 'explicit' | 'client_default';
  readonly catalog_entry_sha256: string;
  readonly pinned_at: string;
}

/**
 * The resumable intake draft. This is the working record; the canonical
 * DecisionBrief revisions composed from it are the durable product.
 */
export interface IntakeDraft {
  readonly schema_version: typeof INTAKE_SCHEMA_VERSION;
  readonly intake_id: string;
  readonly session_id: string;
  readonly brief_id: string;
  readonly scope: ScopeFields;
  readonly visibility: SessionVisibility;
  readonly display_timezone: string;
  readonly source_pack_version: string;
  readonly status: 'in_progress' | 'frozen';
  /** Compare-and-swap counter for intake writes; starts at 1. */
  readonly intake_revision: number;
  /** Highest brief revision composed so far; 0 before the first. */
  readonly current_brief_revision: number;
  readonly answers: IntakeAnswers;
  /** Authorized facts supplied through CWE-022 retrieval at begin. */
  readonly known_facts: readonly IntakeFact[];
  /** Out-of-scope supplied facts excluded at begin; count only, no content. */
  readonly dropped_known_fact_count: number;
  readonly evidence_manifest: readonly EvidenceManifestEntry[];
  readonly mode: SessionMode | null;
  readonly panel_seat_ids: readonly SeatId[] | null;
  /** Whether a qualified professional review is arranged, when asked. */
  readonly professional_review_arranged: boolean | null;
  readonly route_choice: RouteChoice | null;
  /** The snapshot pinned when the route was chosen; re-pinned on change. */
  readonly route_snapshot: RouteSnapshot | null;
  /** True when brief-affecting input changed since the last composition. */
  readonly brief_dirty: boolean;
  /** The client explicitly stated constraints are unknown (Section 9.3). */
  readonly constraints_explicit_unknown: boolean;
  /** The client explicitly stated no facts are known yet. */
  readonly facts_explicit_unknown: boolean;
  readonly preference_ref: string | null;
  /** Question IDs answered or explicitly skipped, in first-touch order. */
  readonly answered_question_ids: readonly string[];
  readonly skipped_question_ids: readonly string[];
  readonly created_at: string;
  readonly updated_at: string;
}

/**
 * The client's private preference, stored separately from the brief
 * (Section 9.4). Only its ID (preference_id) ever appears in a brief,
 * as private_preference_ref.
 */
export interface ClientPreferencePrivate {
  readonly schema_version: typeof INTAKE_SCHEMA_VERSION;
  readonly preference_id: string;
  readonly session_id: string;
  /** The option the client leans toward, or null when only a note exists. */
  readonly leaning_option_id: string | null;
  readonly statement: string | null;
  readonly updated_at: string;
}

/** A factual input received after freeze, queued and never applied (9.4). */
export interface ProposedAmendment {
  readonly schema_version: typeof INTAKE_SCHEMA_VERSION;
  readonly amendment_id: string;
  readonly session_id: string;
  /** The frozen brief revision this proposal was filed against. */
  readonly base_revision: number;
  readonly statement: string;
  readonly evidence_ids: readonly string[];
  readonly status: 'proposed';
  readonly recorded_at: string;
}

/** Domains whose required critical responsibility is missing from a panel. */
export type MissingCriticalDomain = CriticalDomain;
