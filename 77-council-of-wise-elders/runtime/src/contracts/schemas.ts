/**
 * Canonical contract schemas for @blackceo/wise-elders-core (CWE-003).
 *
 * This module is the single schema source for the Council of Wise Elders
 * contracts (directive Sections 11, 12.7, 15, 16.6, 17, 25.6). JSON Schema
 * artifacts and TypeScript consumer types are generated from these exact
 * definitions (see generate.ts, generated/, and types.ts); drift between
 * them is a test failure, not a review comment.
 *
 * Boundary rules enforced here:
 * - strict objects: unknown fields are rejected, never silently dropped;
 * - unknown enum values and invalid IDs fail validation;
 * - unknown values are null, never empty strings masquerading as facts;
 * - author-created values are separate from trusted host-filled identity
 *   and accounting fields: an author payload that tries to carry tenant,
 *   verified-source status, grant, operation ID, or permission fields is
 *   rejected, because those exist only inside the host stamp.
 */

import { z } from 'zod';
import {
  AMENDMENT_DISPOSITIONS,
  AMENDMENT_MATERIALITIES,
  ATTRIBUTION_KINDS,
  AUTHORIZATION_KINDS,
  CARD_KINDS,
  CONDITION_KINDS,
  CONDITION_STATUSES,
  CONSTRAINT_RESULTS,
  CRITICAL_DOMAINS,
  CRITICAL_DOMAIN_STATUSES,
  EVIDENCE_STRENGTHS,
  EVENT_TYPES,
  EXECUTION_POLICIES,
  FALLBACK_POLICIES,
  GRANT_STATUSES,
  MODEL_SELECTION_SOURCES,
  OPERATION_STATUSES,
  OPTION_KINDS,
  RATIFICATION_STATUSES,
  RESOLUTION_STANCES,
  RISK_CLASSES,
  RUN_GRANT_AUTHORITY_MODES,
  RUN_PURPOSES,
  SEAT_IDS,
  SESSION_MODES,
  SESSION_STATES,
  SESSION_VISIBILITIES,
  STANCES,
  VALIDATION_STATUSES,
  VERDICT_LABELS,
} from './enums.js';
import { isSha256Hex, isUtcTimestamp, isValidId } from './primitives.js';
import { MAX_ADVISOR_ROUND } from './modes.js';
import type { ValidationIssue, ValidationResult } from './errors.js';

/** Current canonical contract version for this package surface. */
export const CONTRACT_PACKAGE_VERSION = 'wise-elders.core/1.0.0';

/** Schema version stamps carried by individual contract payloads. */
export const SCHEMA_VERSIONS = {
  session: 'wise-elders.session/v1',
  brief: 'wise-elders.brief/v1',
  card: 'wise-elders.card/v1',
  verdict: 'wise-elders.verdict/v1',
  grant: 'wise-elders.run-grant/v1',
  preview: 'wise-elders.run-preview/v1',
  event: 'wise-elders.event/v1',
  diagnosticPolicy: 'wise-elders.diagnostic-retention-policy/v1',
  endpoint: 'wise-elders.endpoint-contract/v1',
} as const;

// ---------------------------------------------------------------------------
// Primitive schema bindings
// ---------------------------------------------------------------------------

export const idSchema = z
  .string()
  .refine(isValidId, { message: 'must be an opaque ID (no names, text, or secrets)' });

export const sha256Schema = z
  .string()
  .refine(isSha256Hex, { message: 'must be a SHA-256 hex digest' });

export const utcTimestampSchema = z
  .string()
  .refine(isUtcTimestamp, { message: 'must be a UTC ISO 8601 timestamp' });

export const moneySchema = z.strictObject({
  amount_minor: z.number().int().safe(),
  currency: z.string().regex(/^[A-Z]{3}$/, 'must be an ISO 4217 currency code'),
});

/** A score is 0..10 or null (abstention). NaN can never reach validation. */
export const scoreSchema = z
  .number()
  .finite()
  .min(0, 'score below 0')
  .max(10, 'score above 10')
  .nullable();

export const seatIdSchema = z.enum(SEAT_IDS);
export const sessionStateSchema = z.enum(SESSION_STATES);

/**
 * Trusted scope binding. For private sessions owner_subject is required;
 * that rule is enforced by the refinements on scoped contracts below.
 * A caller never gains authority by supplying these fields (Section 11.1);
 * they are host-filled and authorization is checked before content loads.
 */
export const scopeFieldsSchema = z.strictObject({
  tenant_id: idSchema,
  company_id: idSchema,
  installation_id: idSchema,
  owner_subject: idSchema.nullable(),
});
export type ScopeFields = z.infer<typeof scopeFieldsSchema>;

/**
 * Trusted host stamp. Only the host fills this: tenant scope, operation
 * identity, route, and verified-source status live here and nowhere else.
 */
export const hostStampSchema = z.strictObject({
  scope: scopeFieldsSchema,
  operation_id: idSchema,
  route_id: idSchema,
  session_id: idSchema,
  stamped_at: utcTimestampSchema,
  source_status: z.enum(['verified', 'unverified', 'not_applicable']),
});
export type HostStamp = z.infer<typeof hostStampSchema>;

/** Field names an author payload may never carry (host-filled only). */
export const HOST_ONLY_FIELDS: ReadonlySet<string> = new Set([
  'tenant_id',
  'company_id',
  'installation_id',
  'owner_subject',
  'operation_id',
  'grant_id',
  'verified',
  'source_status',
  'permission',
  'host',
  'scope',
]);

// ---------------------------------------------------------------------------
// Options, brief, evidence (Sections 9, 11.2, 11.6)
// ---------------------------------------------------------------------------

export const decisionOptionSchema = z.strictObject({
  id: idSchema,
  label: z.string().min(1),
  kind: z.enum(OPTION_KINDS),
});
export type DecisionOption = z.infer<typeof decisionOptionSchema>;

function assertUniqueOptionIds(
  options: Array<{ id: string }>,
  ctx: z.RefinementCtx,
): void {
  const seen = new Set<string>();
  options.forEach((option, index) => {
    if (seen.has(option.id)) {
      ctx.addIssue({
        code: 'custom',
        path: ['options', index, 'id'],
        message: `duplicate option id ${option.id}`,
      });
    }
    seen.add(option.id);
  });
}

export const typedFactSchema = z.strictObject({
  id: idSchema,
  statement: z.string().min(1),
  evidence_ids: z.array(idSchema),
});
export type TypedFact = z.infer<typeof typedFactSchema>;

export const evidenceManifestEntrySchema = z.strictObject({
  evidence_id: idSchema,
  sha256: sha256Schema,
  source_kind: z.enum(['book', 'article', 'transcript', 'client_document', 'other']),
  locator: z.string().min(1),
});
export type EvidenceManifestEntry = z.infer<typeof evidenceManifestEntrySchema>;

export const criticalDomainRequirementSchema = z.strictObject({
  schema_version: z.literal('wise-elders.critical-domain-requirement/v1'),
  domain: z.enum(CRITICAL_DOMAINS),
  status: z.enum(CRITICAL_DOMAIN_STATUSES),
  trigger_evidence_ids: z.array(idSchema),
  trigger_field_paths: z.array(z.string().min(1)),
  required_seat_id: seatIdSchema.nullable(),
  required_checker: z.enum(['seat', 'deterministic_code', 'qualified_professional']),
  unresolved_questions: z.array(z.string().min(1)),
  policy_version: z.string().min(1),
});
export type CriticalDomainRequirement = z.infer<
  typeof criticalDomainRequirementSchema
>;

export const decisionBriefSchema = z
  .strictObject({
    schema_version: z.literal(SCHEMA_VERSIONS.brief),
    brief_id: idSchema,
    session_id: idSchema,
    revision: z.number().int().min(1),
    question: z.string().min(1),
    facts: z.array(typedFactSchema),
    assumptions: z.array(typedFactSchema),
    unknowns: z.array(typedFactSchema),
    constraints: z.array(
      z.strictObject({
        id: idSchema,
        description: z.string().min(1),
        hard: z.boolean(),
        applies_to_option_ids: z.array(idSchema),
      }),
    ),
    options: z.array(decisionOptionSchema).min(1),
    /** Frozen before openings (Section 12.1): integer weights 1..3 per seat. */
    relevance_weights: z.partialRecord(
      seatIdSchema,
      z.number().int().min(1).max(3),
    ),
    critical_domains: z.array(criticalDomainRequirementSchema),
    evidence_manifest: z.array(evidenceManifestEntrySchema),
    /** Separately stored private preference: referenced, never inlined. */
    private_preference_ref: idSchema.nullable(),
    created_at: utcTimestampSchema,
    display_timezone: z.string().min(1),
  })
  .superRefine((brief, ctx) => {
    assertUniqueOptionIds(brief.options, ctx);
  });
export type DecisionBrief = z.infer<typeof decisionBriefSchema>;

// ---------------------------------------------------------------------------
// Session specification (Section 11.2, frozen)
// ---------------------------------------------------------------------------

export const modelPolicySchema = z.strictObject({
  selection: z.enum(MODEL_SELECTION_SOURCES),
  route_id: idSchema,
  requested_model_id: idSchema.nullable(),
  reasoning_preference: z.string().min(1).nullable(),
  fallback_policy: z.enum(FALLBACK_POLICIES),
});
export type ModelPolicy = z.infer<typeof modelPolicySchema>;

export const sessionSpecSchema = z
  .strictObject({
    schema_version: z.literal(SCHEMA_VERSIONS.session),
    session_id: idSchema,
    mode: z.enum(SESSION_MODES),
    visibility: z.enum(SESSION_VISIBILITIES),
    brief_revision: z.number().int().min(1),
    brief_sha256: sha256Schema,
    options: z.array(decisionOptionSchema).min(1),
    seat_ids: z.array(seatIdSchema).min(1),
    model_policy: modelPolicySchema,
    source_pack_version: z.string().min(1),
    execution_policy: z.enum(EXECUTION_POLICIES),
    created_at: utcTimestampSchema,
    display_timezone: z.string().min(1),
  })
  .superRefine((spec, ctx) => {
    assertUniqueOptionIds(spec.options, ctx);
    const seats = new Set<string>();
    spec.seat_ids.forEach((seat, index) => {
      if (seats.has(seat)) {
        ctx.addIssue({
          code: 'custom',
          path: ['seat_ids', index],
          message: `duplicate seat id ${seat}`,
        });
      }
      seats.add(seat);
    });
    if (spec.mode === 'full' && spec.seat_ids.length !== SEAT_IDS.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['seat_ids'],
        message: 'full mode requires all nine seats',
      });
    }
    if (spec.mode === 'consult' && spec.seat_ids.length !== 1) {
      ctx.addIssue({
        code: 'custom',
        path: ['seat_ids'],
        message: 'consult mode requires exactly one seat',
      });
    }
    if (
      spec.mode === 'selected' &&
      (spec.seat_ids.length < 2 || spec.seat_ids.length > 8)
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['seat_ids'],
        message: 'selected mode requires 2 to 8 seats',
      });
    }
    if (spec.mode === 'light' && spec.seat_ids.length !== SEAT_IDS.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['seat_ids'],
        message: 'light mode requires all nine seats',
      });
    }
    if (
      (spec.mode === 'medium' || spec.mode === 'heavy') &&
      spec.seat_ids.length !== SEAT_IDS.length
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['seat_ids'],
        message: `${spec.mode} mode requires all nine seats`,
      });
    }
  });
export type SessionSpec = z.infer<typeof sessionSpecSchema>;

// ---------------------------------------------------------------------------
// Conditions and action proposals (Section 11.4)
// ---------------------------------------------------------------------------

export const conditionSchema = z.strictObject({
  id: idSchema,
  description: z.string().min(1),
  kind: z.enum(CONDITION_KINDS),
  blocking: z.boolean(),
  verification_method: z.string().min(1),
  required_evidence: z.array(z.string().min(1)),
  responsible_role: z.string().min(1),
  due_at: utcTimestampSchema.nullable(),
  status: z.enum(CONDITION_STATUSES),
  depends_on: z.array(idSchema),
});
export type Condition = z.infer<typeof conditionSchema>;

export const actionProposalSchema = z.strictObject({
  action_id: idSchema,
  session_id: idSchema,
  verdict_revision: z.number().int().min(1),
  title: z.string().min(1),
  description: z.string().min(1),
  rationale: z.string().min(1),
  source_condition_ids: z.array(idSchema),
  /** Unknown owners, SOPs, and personas stay null; never invented (11.4). */
  department_id: idSchema.nullable(),
  assigned_agent_id: idSchema.nullable(),
  sop_id: idSchema.nullable(),
  persona_id: idSchema.nullable(),
  acceptance_criteria: z.array(z.string().min(1)),
  budget_limit: moneySchema.nullable(),
  due_at: utcTimestampSchema.nullable(),
  depends_on_action_ids: z.array(idSchema),
  risk_class: z.enum(RISK_CLASSES),
  execution_authorization_required: z.literal(true),
});
export type ActionProposal = z.infer<typeof actionProposalSchema>;

// ---------------------------------------------------------------------------
// Cards: discriminated union AdvisorCard | RatificationCard | ConsultCard
// (Sections 11.3 and 11.6)
// ---------------------------------------------------------------------------

export const optionScoreSchema = z.strictObject({
  option_id: idSchema,
  score: scoreSchema,
  rationale: z.string().min(1),
  evidence_ids: z.array(idSchema),
});
export type OptionScore = z.infer<typeof optionScoreSchema>;

export const frameworkApplicationSchema = z.strictObject({
  framework_id: idSchema,
  source_evidence_ids: z.array(idSchema),
  case_evidence_ids: z.array(idSchema),
  application: z.string().min(1),
  attribution_kind: z.enum(ATTRIBUTION_KINDS),
});
export type FrameworkApplication = z.infer<typeof frameworkApplicationSchema>;

export const verifiedQuoteCandidateSchema = z.strictObject({
  quote_id: idSchema,
  text: z.string().min(1),
  evidence_id: idSchema,
  locator: z.string().min(1),
  /** Verification is a host/validator outcome, never author-asserted. */
  verification_status: z.enum(['candidate', 'verified', 'rejected']),
});
export type VerifiedQuoteCandidate = z.infer<typeof verifiedQuoteCandidateSchema>;

const cardBaseShape = {
  schema_version: z.literal(SCHEMA_VERSIONS.card),
  session_id: idSchema,
  brief_revision: z.number().int().min(1),
  seat_id: seatIdSchema,
  input_manifest_sha256: sha256Schema,
  pack_version: z.string().min(1),
};

export const advisorCardAuthorSchema = z.strictObject({
  ...cardBaseShape,
  card_kind: z.literal('advisor'),
  round: z.number().int().min(1).max(MAX_ADVISOR_ROUND),
  stance: z.enum(STANCES),
  preferred_option_id: idSchema.nullable(),
  option_scores: z.array(optionScoreSchema),
  framework_applications: z.array(frameworkApplicationSchema),
  decisive_arguments: z.array(z.string().min(1)),
  strongest_objection: z.string().min(1),
  conditions: z.array(conditionSchema),
  critical_unknowns: z.array(z.string().min(1)),
  change_my_mind: z.string().min(1),
  challenges_answered: z.array(idSchema),
  lenses_used: z.array(z.string().min(1)).optional(),
  quotes: z.array(verifiedQuoteCandidateSchema),
  evidence_strength: z.enum(EVIDENCE_STRENGTHS),
  minority_position: z.string().min(1).nullable(),
});
export type AdvisorCardAuthor = z.infer<typeof advisorCardAuthorSchema>;

export const amendmentSchema = z.strictObject({
  amendment_id: idSchema,
  proposing_seat_id: seatIdSchema,
  target_path: z.string().min(1),
  old_value: z.string().nullable(),
  new_value: z.string().nullable(),
  statement: z.string().min(1),
  reason: z.string().min(1),
  evidence_ids: z.array(idSchema),
  materiality: z.enum(AMENDMENT_MATERIALITIES),
  disposition: z.enum(AMENDMENT_DISPOSITIONS),
  reviewer_reason: z.string().nullable(),
});
export type Amendment = z.infer<typeof amendmentSchema>;

export const ratificationCardAuthorSchema = z.strictObject({
  ...cardBaseShape,
  card_kind: z.literal('ratification'),
  round: z.literal(3),
  /** Binds this card to the exact frozen draft resolution (Section 12.8). */
  draft_resolution_sha256: sha256Schema,
  /** Judgment about the resolution itself; distinct from option stance. */
  resolution_stance: z.enum(RESOLUTION_STANCES),
  stance: z.enum(STANCES),
  preferred_option_id: idSchema.nullable(),
  option_scores: z.array(optionScoreSchema),
  amendments: z.array(amendmentSchema),
  accepted_condition_ids: z.array(idSchema),
  unresolved_objections: z.array(z.string().min(1)),
  evidence_strength: z.enum(EVIDENCE_STRENGTHS),
});
export type RatificationCardAuthor = z.infer<typeof ratificationCardAuthorSchema>;

export const consultCardAuthorSchema = z.strictObject({
  ...cardBaseShape,
  card_kind: z.literal('consult'),
  answer: z.string().min(1),
  framework_applications: z.array(frameworkApplicationSchema),
  evidence_ids: z.array(idSchema),
  assumptions: z.array(z.string().min(1)),
  limits: z.array(z.string().min(1)),
  next_step: z.string().min(1),
});
export type ConsultCardAuthor = z.infer<typeof consultCardAuthorSchema>;

/** Author-created card payloads. Carries NO host identity fields. */
export const cardAuthorSchema = z.discriminatedUnion('card_kind', [
  advisorCardAuthorSchema,
  ratificationCardAuthorSchema,
  consultCardAuthorSchema,
]);
export type CardAuthor = z.infer<typeof cardAuthorSchema>;

/** A persisted card: the author payload plus the trusted host stamp. */
export const advisorCardSchema = advisorCardAuthorSchema.extend({
  host: hostStampSchema,
});
export const ratificationCardSchema = ratificationCardAuthorSchema.extend({
  host: hostStampSchema,
});
export const consultCardSchema = consultCardAuthorSchema.extend({
  host: hostStampSchema,
});
export const cardSchema = z.discriminatedUnion('card_kind', [
  advisorCardSchema,
  ratificationCardSchema,
  consultCardSchema,
]);
export type AdvisorCard = z.infer<typeof advisorCardSchema>;
export type RatificationCard = z.infer<typeof ratificationCardSchema>;
export type ConsultCard = z.infer<typeof consultCardSchema>;
export type CouncilCard = z.infer<typeof cardSchema>;

export const CARD_KIND_VALUES = CARD_KINDS;

// ---------------------------------------------------------------------------
// Draft resolution and verdict (Sections 11.5, 11.6, 12.8)
// ---------------------------------------------------------------------------

export const draftResolutionSchema = z.strictObject({
  schema_version: z.literal('wise-elders.draft-resolution/v1'),
  session_id: idSchema,
  brief_revision: z.number().int().min(1),
  revision: z.number().int().min(1),
  recommended_option_id: idSchema,
  actions: z.array(z.string().min(1)),
  prerequisites: z.array(z.string().min(1)),
  limits: z.array(z.string().min(1)),
  /** Semantic hash excludes presentation-only fields; set by hashing helper. */
  semantic_sha256: sha256Schema,
});
export type DraftResolution = z.infer<typeof draftResolutionSchema>;

/**
 * Weighted support counts keyed to one exact resolution hash (Section 11.6).
 * These are counts, never a probability, and are never inferred from scores.
 */
export const resolutionSupportSchema = z.strictObject({
  resolution_sha256: sha256Schema,
  support: z.number().min(0),
  conditional_support: z.number().min(0),
  opposition: z.number().min(0),
  abstention: z.number().min(0),
});
export type ResolutionSupport = z.infer<typeof resolutionSupportSchema>;

export const hardConstraintFindingSchema = z.strictObject({
  constraint_id: idSchema,
  option_id: idSchema,
  result: z.enum(CONSTRAINT_RESULTS),
  checker: z.enum(['deterministic_code', 'seat', 'qualified_professional']),
  evidence_ids: z.array(idSchema),
});
export type HardConstraintFinding = z.infer<typeof hardConstraintFindingSchema>;

export const optionScoreSummarySchema = z.strictObject({
  option_id: idSchema,
  /** Full precision; null when no seat scored the option (never 0). */
  score: z.number().finite().nullable(),
  display_score: z.number().finite().nullable(),
  weighted_sum: z.number().finite(),
  denominator: z.number().finite(),
  coverage: z.number().finite().min(0).max(1),
  spread: z.number().finite().nullable(),
});
export type OptionScoreSummary = z.infer<typeof optionScoreSummarySchema>;

export const scoredVerdictSchema = z.strictObject({
  schema_version: z.literal(SCHEMA_VERSIONS.verdict),
  result_kind: z.literal('scored'),
  session_id: idSchema,
  verdict_revision: z.number().int().min(1),
  recommended_option_id: idSchema.nullable(),
  label: z.enum(VERDICT_LABELS),
  option_scores: z.array(optionScoreSummarySchema),
  active_weights: z.partialRecord(seatIdSchema, z.number().int().min(1).max(3)),
  evidence_strength: z.enum(EVIDENCE_STRENGTHS),
  hard_constraint_findings: z.array(hardConstraintFindingSchema),
  main_reasons: z.array(z.string().min(1)).max(3),
  strongest_dissent: z.string().nullable(),
  accepted_amendments: z.array(amendmentSchema),
  rejected_amendments: z.array(amendmentSchema),
  critical_unknowns: z.array(z.string().min(1)),
  prerequisites: z.array(z.string().min(1)),
  action_proposals: z.array(actionProposalSchema),
  cheapest_informative_test: z.string().nullable(),
  stop_criteria: z.array(z.string().min(1)),
  review_criteria: z.array(z.string().min(1)),
  resolution_support: resolutionSupportSchema.nullable(),
  validation_status: z.enum(VALIDATION_STATUSES),
  ratification_status: z.enum(RATIFICATION_STATUSES),
  brief_sha256: sha256Schema,
  content_sha256: sha256Schema,
});
export type ScoredVerdict = z.infer<typeof scoredVerdictSchema>;

/** Consult mode result: a discriminated result, no invented scores (11.5). */
export const consultResultSchema = z.strictObject({
  schema_version: z.literal(SCHEMA_VERSIONS.verdict),
  result_kind: z.literal('consult'),
  session_id: idSchema,
  verdict_revision: z.number().int().min(1),
  consult_card: consultCardSchema,
  next_step: z.string().min(1),
  validation_status: z.enum(VALIDATION_STATUSES),
  brief_sha256: sha256Schema,
  content_sha256: sha256Schema,
});
export type ConsultResult = z.infer<typeof consultResultSchema>;

export const verdictSchema = z.discriminatedUnion('result_kind', [
  scoredVerdictSchema,
  consultResultSchema,
]);
export type Verdict = z.infer<typeof verdictSchema>;

// ---------------------------------------------------------------------------
// Session state and job checkpoint (Sections 15.1, 15.2)
// ---------------------------------------------------------------------------

export const sessionStateRecordSchema = z.strictObject({
  schema_version: z.literal('wise-elders.session-state/v1'),
  session_id: idSchema,
  mode: z.enum(SESSION_MODES),
  state: sessionStateSchema,
  state_version: z.number().int().min(0),
  brief_revision: z.number().int().min(1),
  resume_phase: sessionStateSchema.nullable(),
  cancel_generation: z.number().int().min(0),
  revocation_generation: z.number().int().min(0),
  attempt: z.number().int().min(1),
  lease_epoch: z.number().int().min(0),
  /** Archive is a visibility flag, never a state (Section 15.1). */
  archived: z.boolean(),
  updated_at: utcTimestampSchema,
});
export type SessionStateRecord = z.infer<typeof sessionStateRecordSchema>;

export const jobCheckpointSchema = z.strictObject({
  schema_version: z.literal('wise-elders.job-checkpoint/v1'),
  /** Stable operation key parts (Section 15.3). */
  installation_id: idSchema,
  tenant_id: idSchema,
  session_id: idSchema,
  attempt: z.number().int().min(1),
  brief_revision: z.number().int().min(1),
  phase: z.string().min(1),
  seat_id: seatIdSchema.nullable(),
  input_sha256: sha256Schema,
  pack_version: z.string().min(1),
  model_policy_revision: z.number().int().min(0),
  status: z.enum(OPERATION_STATUSES),
  provider_request_id: idSchema.nullable(),
  usage: z.strictObject({
    input_tokens: z.number().int().min(0).nullable(),
    output_tokens: z.number().int().min(0).nullable(),
    provider_requests: z.number().int().min(0),
  }),
  committed_at: utcTimestampSchema.nullable(),
});
export type JobCheckpoint = z.infer<typeof jobCheckpointSchema>;

// ---------------------------------------------------------------------------
// Run preview and run grant (Section 25.6). CWE-049 owns the service that
// issues these; CWE-003 owns their canonical shape only.
// ---------------------------------------------------------------------------

export const runCeilingsSchema = z.strictObject({
  max_provider_requests: z.number().int().min(0),
  max_output_repairs: z.number().int().min(0),
  max_transport_retries: z.number().int().min(0),
  max_input_tokens: z.number().int().min(0).nullable(),
  max_output_tokens: z.number().int().min(0).nullable(),
  max_money: moneySchema.nullable(),
});
export type RunCeilings = z.infer<typeof runCeilingsSchema>;

export const runPreviewSchema = z.strictObject({
  schema_version: z.literal(SCHEMA_VERSIONS.preview),
  preview_id: idSchema,
  session_id: idSchema,
  brief_revision: z.number().int().min(1),
  brief_sha256: sha256Schema,
  mode: z.enum(SESSION_MODES),
  seat_ids: z.array(seatIdSchema).min(1),
  purpose: z.enum(RUN_PURPOSES),
  route_policy_sha256: sha256Schema,
  pack_version: z.string().min(1),
  ceilings: runCeilingsSchema,
  /** Money bounded only when pricing supports it; unknown is not zero. */
  money_bounded: z.boolean(),
  created_at: utcTimestampSchema,
  expires_at: utcTimestampSchema,
  preview_sha256: sha256Schema,
});
export type RunPreview = z.infer<typeof runPreviewSchema>;

export const runGrantSchema = z.strictObject({
  schema_version: z.literal(SCHEMA_VERSIONS.grant),
  grant_id: idSchema,
  authority_mode: z.enum(RUN_GRANT_AUTHORITY_MODES),
  issuer_principal: idSchema,
  scope: scopeFieldsSchema,
  purpose: z.enum(RUN_PURPOSES),
  session_id: idSchema,
  brief_revision: z.number().int().min(1),
  brief_sha256: sha256Schema,
  mode: z.enum(SESSION_MODES),
  seat_ids: z.array(seatIdSchema).min(1),
  route_policy_sha256: sha256Schema,
  account_ref: idSchema.nullable(),
  pack_version: z.string().min(1),
  protocol_version: z.string().min(1),
  allowed_operation_kinds: z.array(z.string().min(1)).min(1),
  ceilings: runCeilingsSchema,
  created_at: utcTimestampSchema,
  expires_at: utcTimestampSchema,
  revocation_epoch: z.number().int().min(0),
  status: z.enum(GRANT_STATUSES),
  standing_parent_grant_id: idSchema.nullable(),
  preview_sha256: sha256Schema,
  consumed: z.strictObject({
    provider_requests: z.number().int().min(0),
    output_repairs: z.number().int().min(0),
    transport_retries: z.number().int().min(0),
  }),
  reserved: z.strictObject({
    provider_requests: z.number().int().min(0),
    output_repairs: z.number().int().min(0),
    transport_retries: z.number().int().min(0),
  }),
});
export type RunGrant = z.infer<typeof runGrantSchema>;

// ---------------------------------------------------------------------------
// Approvals, events, settings, receipts (Sections 17, 18, 19)
// ---------------------------------------------------------------------------

/** A user approval record. The four authorization kinds never merge. */
export const approvalRecordSchema = z.strictObject({
  schema_version: z.literal('wise-elders.approval/v1'),
  approval_id: idSchema,
  kind: z.enum(AUTHORIZATION_KINDS),
  session_id: idSchema,
  target_sha256: sha256Schema,
  approved_by_principal: idSchema,
  approved_at: utcTimestampSchema,
  expires_at: utcTimestampSchema.nullable(),
});
export type ApprovalRecord = z.infer<typeof approvalRecordSchema>;

/**
 * Council event envelope (Section 18). Scope is mandatory and non-null:
 * no council content event may use null or company-free scope.
 */
export const councilEventSchema = z.strictObject({
  schema_version: z.literal(SCHEMA_VERSIONS.event),
  event_id: idSchema,
  session_id: idSchema,
  sequence: z.number().int().min(0),
  event_type: z.enum(EVENT_TYPES),
  tenant_id: idSchema,
  company_id: idSchema,
  owner_subject: idSchema.nullable(),
  actor: z.enum(['owner', 'system', 'worker', 'chair']),
  payload: z.record(z.string(), z.unknown()),
  created_at: utcTimestampSchema,
});
export type CouncilEvent = z.infer<typeof councilEventSchema>;

/** Session budget and behavior settings (defaults from Section 15.6). */
export const councilSettingsSchema = z.strictObject({
  schema_version: z.literal('wise-elders.settings/v1'),
  max_session_provider_requests: z.number().int().min(1).max(100),
  max_output_repair_requests: z.number().int().min(0),
  max_semantic_verification_requests: z.number().int().min(0).max(2),
  max_transport_retries_total: z.number().int().min(0),
  max_transport_retries_per_request: z.number().int().min(0).max(1),
  max_output_repairs_per_original_operation: z.number().int().min(0).max(1),
  max_concurrent_seat_calls: z.number().int().min(1).max(9),
  max_active_council_sessions_per_client: z.number().int().min(1),
  fallback_policy: z.enum(FALLBACK_POLICIES),
});
export type CouncilSettings = z.infer<typeof councilSettingsSchema>;

export const DEFAULT_COUNCIL_SETTINGS: CouncilSettings = {
  schema_version: 'wise-elders.settings/v1',
  max_session_provider_requests: 50,
  max_output_repair_requests: 9,
  max_semantic_verification_requests: 2,
  max_transport_retries_total: 8,
  max_transport_retries_per_request: 1,
  max_output_repairs_per_original_operation: 1,
  max_concurrent_seat_calls: 9,
  max_active_council_sessions_per_client: 1,
  fallback_policy: 'none',
};

/** Operation receipt: safe accounting only, never raw provider bodies. */
export const operationReceiptSchema = z.strictObject({
  schema_version: z.literal('wise-elders.operation-receipt/v1'),
  operation_id: idSchema,
  session_id: idSchema,
  status: z.enum(OPERATION_STATUSES),
  provider_request_id: idSchema.nullable(),
  input_sha256: sha256Schema,
  output_sha256: sha256Schema.nullable(),
  usage: z.strictObject({
    input_tokens: z.number().int().min(0).nullable(),
    output_tokens: z.number().int().min(0).nullable(),
  }),
  /** Monetary cost stays null when not metered; unknown is never $0. */
  cost: moneySchema.nullable(),
  completed_at: utcTimestampSchema.nullable(),
});
export type OperationReceipt = z.infer<typeof operationReceiptSchema>;

// ---------------------------------------------------------------------------
// Diagnostic retention policy contract (Section 16.6; behavior in
// diagnostic-retention.ts)
// ---------------------------------------------------------------------------

export const DIAGNOSTIC_LIMITS = {
  defaultCaptureWindowMinutes: 60,
  maxCaptureWindowMinutes: 240,
  defaultPayloadTtlHours: 24,
  maxPayloadTtlHours: 72,
  maxBytesPerOperation: 5 * 1024 * 1024,
  maxBytesPerSession: 25 * 1024 * 1024,
} as const;

export const diagnosticRetentionPolicySchema = z
  .strictObject({
    schema_version: z.literal(SCHEMA_VERSIONS.diagnosticPolicy),
    /** Disabled by default; enabling needs named authority for one session. */
    enabled: z.boolean(),
    authorized_by_principal: idSchema.nullable(),
    authorization_kind: z
      .enum(['owner', 'audited_support'])
      .nullable(),
    session_id: idSchema.nullable(),
    capture_window_minutes: z
      .number()
      .int()
      .min(1)
      .max(DIAGNOSTIC_LIMITS.maxCaptureWindowMinutes),
    payload_ttl_hours: z
      .number()
      .int()
      .min(1)
      .max(DIAGNOSTIC_LIMITS.maxPayloadTtlHours),
    max_bytes_per_operation: z
      .number()
      .int()
      .min(1)
      .max(DIAGNOSTIC_LIMITS.maxBytesPerOperation),
    max_bytes_per_session: z
      .number()
      .int()
      .min(1)
      .max(DIAGNOSTIC_LIMITS.maxBytesPerSession),
  })
  .superRefine((policy, ctx) => {
    if (policy.enabled) {
      if (policy.authorized_by_principal === null) {
        ctx.addIssue({
          code: 'custom',
          path: ['authorized_by_principal'],
          message: 'enabled capture requires an authorizing principal',
        });
      }
      if (policy.authorization_kind === null) {
        ctx.addIssue({
          code: 'custom',
          path: ['authorization_kind'],
          message: 'enabled capture requires owner or audited support authorization',
        });
      }
      if (policy.session_id === null) {
        ctx.addIssue({
          code: 'custom',
          path: ['session_id'],
          message: 'enabled capture is authorized for one named session only',
        });
      }
    }
  });
export type DiagnosticRetentionPolicy = z.infer<
  typeof diagnosticRetentionPolicySchema
>;

export const DEFAULT_DIAGNOSTIC_RETENTION_POLICY: DiagnosticRetentionPolicy = {
  schema_version: SCHEMA_VERSIONS.diagnosticPolicy,
  enabled: false,
  authorized_by_principal: null,
  authorization_kind: null,
  session_id: null,
  capture_window_minutes: DIAGNOSTIC_LIMITS.defaultCaptureWindowMinutes,
  payload_ttl_hours: DIAGNOSTIC_LIMITS.defaultPayloadTtlHours,
  max_bytes_per_operation: DIAGNOSTIC_LIMITS.maxBytesPerOperation,
  max_bytes_per_session: DIAGNOSTIC_LIMITS.maxBytesPerSession,
};

// ---------------------------------------------------------------------------
// Endpoint contract (Sections 11.6 and 17)
// ---------------------------------------------------------------------------

export const endpointContractSchema = z.strictObject({
  schema_version: z.literal(SCHEMA_VERSIONS.endpoint),
  contract_id: idSchema,
  method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
  path: z.string().startsWith('/'),
  request_schema: z.string().min(1).nullable(),
  response_schema: z.string().min(1),
  authorization_purpose: z.enum(AUTHORIZATION_KINDS),
  idempotency: z.enum(['required_key', 'safe_read', 'not_applicable']),
  version_rule: z.string().min(1),
  service_owner: z.string().min(1),
  contract_test_gate: z.string().min(1),
  live_integration_gate: z.string().min(1),
});
export type EndpointContract = z.infer<typeof endpointContractSchema>;

// ---------------------------------------------------------------------------
// Validation helpers: every public validator returns a typed result instead
// of throwing, so boundaries can map failures to typed errors.
// ---------------------------------------------------------------------------

function toResult<T>(schema: z.ZodType<T>, value: unknown): ValidationResult<T> {
  const parsed = schema.safeParse(value);
  if (parsed.success) return { ok: true, value: parsed.data };
  const issues: ValidationIssue[] = parsed.error.issues.map((issue) => ({
    path: issue.path.map((p) => String(p)).join('.'),
    code: issue.code,
    message: issue.message,
  }));
  return { ok: false, issues };
}

export function validateSessionSpec(value: unknown): ValidationResult<SessionSpec> {
  return toResult(sessionSpecSchema, value);
}
export function validateDecisionBrief(
  value: unknown,
): ValidationResult<DecisionBrief> {
  return toResult(decisionBriefSchema, value);
}
export function validateCardAuthor(value: unknown): ValidationResult<CardAuthor> {
  return toResult(cardAuthorSchema, value);
}
export function validateCard(value: unknown): ValidationResult<CouncilCard> {
  return toResult(cardSchema, value);
}
export function validateVerdict(value: unknown): ValidationResult<Verdict> {
  return toResult(verdictSchema, value);
}
export function validateCondition(value: unknown): ValidationResult<Condition> {
  return toResult(conditionSchema, value);
}
export function validateActionProposal(
  value: unknown,
): ValidationResult<ActionProposal> {
  return toResult(actionProposalSchema, value);
}
export function validateRunPreview(value: unknown): ValidationResult<RunPreview> {
  return toResult(runPreviewSchema, value);
}
export function validateRunGrant(value: unknown): ValidationResult<RunGrant> {
  return toResult(runGrantSchema, value);
}
export function validateSessionStateRecord(
  value: unknown,
): ValidationResult<SessionStateRecord> {
  return toResult(sessionStateRecordSchema, value);
}
export function validateJobCheckpoint(
  value: unknown,
): ValidationResult<JobCheckpoint> {
  return toResult(jobCheckpointSchema, value);
}
export function validateCouncilEvent(
  value: unknown,
): ValidationResult<CouncilEvent> {
  return toResult(councilEventSchema, value);
}
export function validateDiagnosticRetentionPolicy(
  value: unknown,
): ValidationResult<DiagnosticRetentionPolicy> {
  return toResult(diagnosticRetentionPolicySchema, value);
}
export function validateEndpointContract(
  value: unknown,
): ValidationResult<EndpointContract> {
  return toResult(endpointContractSchema, value);
}
export function validateApprovalRecord(
  value: unknown,
): ValidationResult<ApprovalRecord> {
  return toResult(approvalRecordSchema, value);
}
export function validateCouncilSettings(
  value: unknown,
): ValidationResult<CouncilSettings> {
  return toResult(councilSettingsSchema, value);
}
export function validateOperationReceipt(
  value: unknown,
): ValidationResult<OperationReceipt> {
  return toResult(operationReceiptSchema, value);
}

/**
 * Semantic card checks beyond shape (Section 11.3): every active option
 * appears exactly once in option_scores, and the preferred option exists.
 * Reference checks against the frozen brief manifest happen here, at the
 * contract boundary, so an invalid reference fails before any consumer runs.
 */
export function validateCardAgainstBrief(
  card: CardAuthor,
  brief: DecisionBrief,
): ValidationResult<CardAuthor> {
  const issues: ValidationIssue[] = [];
  if (card.session_id !== brief.session_id) {
    issues.push({
      path: 'session_id',
      code: 'INVALID_REFERENCE',
      message: 'card session_id does not match the brief',
    });
  }
  if (card.brief_revision !== brief.revision) {
    issues.push({
      path: 'brief_revision',
      code: 'INVALID_REFERENCE',
      message: 'card brief_revision does not match the brief revision',
    });
  }
  const manifestIds = new Set(brief.evidence_manifest.map((e) => e.evidence_id));
  if (card.card_kind !== 'consult') {
    const optionIds = brief.options.map((o) => o.id);
    const scoredIds = card.option_scores.map((s) => s.option_id);
    for (const optionId of optionIds) {
      const count = scoredIds.filter((id) => id === optionId).length;
      if (count !== 1) {
        issues.push({
          path: 'option_scores',
          code: count === 0 ? 'INVALID_REFERENCE' : 'DUPLICATE_OPTION',
          message: `option ${optionId} must appear exactly once in option_scores (found ${count})`,
        });
      }
    }
    for (const scoredId of scoredIds) {
      if (!optionIds.includes(scoredId)) {
        issues.push({
          path: 'option_scores',
          code: 'INVALID_REFERENCE',
          message: `option_scores references unknown option ${scoredId}`,
        });
      }
    }
    if (
      card.preferred_option_id !== null &&
      !optionIds.includes(card.preferred_option_id)
    ) {
      issues.push({
        path: 'preferred_option_id',
        code: 'INVALID_REFERENCE',
        message: `preferred_option_id ${card.preferred_option_id} is not an active option`,
      });
    }
    for (const score of card.option_scores) {
      for (const evidenceId of score.evidence_ids) {
        if (!manifestIds.has(evidenceId)) {
          issues.push({
            path: 'option_scores.evidence_ids',
            code: 'INVALID_REFERENCE',
            message: `evidence ${evidenceId} is not in the frozen evidence manifest`,
          });
        }
      }
    }
  } else {
    for (const evidenceId of card.evidence_ids) {
      if (!manifestIds.has(evidenceId)) {
        issues.push({
          path: 'evidence_ids',
          code: 'INVALID_REFERENCE',
          message: `evidence ${evidenceId} is not in the frozen evidence manifest`,
        });
      }
    }
  }
  return issues.length === 0 ? { ok: true, value: card } : { ok: false, issues };
}

/**
 * Contract version compatibility: a payload is compatible when its schema
 * version major line matches the version this package implements for that
 * contract family. Anything else is VERSION_MISMATCH, never a silent accept.
 */
export function checkSchemaVersionCompatibility(
  family: keyof typeof SCHEMA_VERSIONS,
  payloadVersion: unknown,
): boolean {
  return payloadVersion === SCHEMA_VERSIONS[family];
}
