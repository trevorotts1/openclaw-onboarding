/**
 * TypeScript consumer types for @blackceo/wise-elders-core (CWE-003).
 *
 * These types are generated from the same canonical zod definitions in
 * schemas.ts (z.infer), never hand-maintained copies, so consumer types and
 * JSON Schema cannot drift from the canonical definitions. The drift test
 * regenerates the JSON Schema artifacts and compares them byte for byte.
 */

export type {
  ActionProposal,
  AdvisorCard,
  AdvisorCardAuthor,
  Amendment,
  ApprovalRecord,
  CardAuthor,
  Condition,
  ConsultCard,
  ConsultCardAuthor,
  ConsultResult,
  CouncilCard,
  CouncilEvent,
  CouncilSettings,
  CriticalDomainRequirement,
  DecisionBrief,
  DecisionOption,
  DiagnosticRetentionPolicy,
  DraftResolution,
  EndpointContract,
  EvidenceManifestEntry,
  FrameworkApplication,
  HostStamp,
  JobCheckpoint,
  ModelPolicy,
  OperationReceipt,
  OptionScore,
  OptionScoreSummary,
  RatificationCard,
  RatificationCardAuthor,
  ResolutionSupport,
  RunCeilings,
  RunGrant,
  RunPreview,
  ScopeFields,
  ScoredVerdict,
  SessionSpec,
  SessionStateRecord,
  TypedFact,
  Verdict,
  VerifiedQuoteCandidate,
} from './schemas';

export type {
  AmendmentDisposition,
  AmendmentMateriality,
  AttributionKind,
  AuthorizationKind,
  CardKind,
  ConditionKind,
  ConditionStatus,
  ConstraintResult,
  CriticalDomain,
  CriticalDomainStatus,
  EvidenceStrength,
  ExecutionPolicy,
  FallbackPolicy,
  GrantStatus,
  ModelSelectionSource,
  OperationStatus,
  OptionKind,
  RatificationStatus,
  ResolutionStance,
  RiskClass,
  RunGrantAuthorityMode,
  RunPurpose,
  SeatId,
  SessionMode,
  SessionState,
  SessionVisibility,
  Stance,
  ValidationStatus,
  VerdictLabel,
  CouncilEventType,
} from './enums';

export type { Money, Clock, IdSource } from './primitives';
export type { ContractErrorCode, ValidationIssue, ValidationResult } from './errors';
