/**
 * CWE-023 intake-and-brief-revisions: public surface.
 *
 * Guided intake (Section 9), modes and panels (Section 10), and
 * preference boundaries (Section 11) over the CWE-006 scoped store,
 * the CWE-008 route catalog semantics, and the CWE-022 bounded
 * context boundary. See README.md in this folder for the model.
 */
export {
  CRITICAL_DOMAIN_POLICY_VERSION,
  EMPTY_ANSWERS,
  INTAKE_SCHEMA_VERSION,
  IntakeError,
  type ClientPreferencePrivate,
  type DecisionFlags,
  type IntakeAnswers,
  type IntakeConstraint,
  type IntakeConstraintKind,
  type IntakeDraft,
  type IntakeFact,
  type FactOrigin,
  type ProposedAmendment,
  type RouteCatalogEntry,
  type RouteChoice,
  type RouteIdentityLevel,
  type RouteSnapshot,
  type SuccessAnswer,
} from './types.js';
export {
  INTAKE_QUESTIONS,
  currentQuestion,
  isFlowReadyToFreeze,
  isQuestionAnswered,
  missingMaterialQuestions,
  questionById,
  type IntakeQuestion,
  type IntakeQuestionId,
} from './questions.js';
export {
  CRITICAL_DOMAIN_REVIEWERS,
  classifyIntakeDomains,
  deriveSignals,
} from './classify.js';
export {
  modelPolicyFromSnapshot,
  pinRouteSnapshot,
  resolveRouteSnapshot,
  routeSnapshotDrift,
  type RouteCatalogPort,
} from './routes.js';
export {
  assessPanel,
  quickModePolicyRecord,
  recommendQuickPanel,
  validatePanel,
  type PanelAssessment,
  type PanelRecommendation,
  type QuickModePolicyRecord,
  type RequiredResponsibility,
} from './panel.js';
export { briefContentHash, composeBrief, evidenceManifestHash } from './brief.js';
export {
  FileIntakeWorkingStore,
  MemoryIntakeWorkingStore,
  RepositoryIntakeBriefStore,
  type IntakeBriefStore,
  type IntakeWorkingStore,
} from './stores.js';
export {
  IntakeService,
  type BeginIntakeInput,
  type IntakeAnswerValue,
  type IntakeServiceDeps,
} from './service.js';
export type {
  FreezeRecord,
  FreezeResult,
  IntakeReviewSummary,
} from './service-types.js';
