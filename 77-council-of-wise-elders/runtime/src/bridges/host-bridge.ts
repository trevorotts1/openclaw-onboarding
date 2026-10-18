/**
 * Host bridge shared machinery (CWE-010; directive Sections 13, 14, 25).
 *
 * The two host bridges (OpenClaw and Claude-Nine) sit behind the CWE-004
 * host ports so the SAME portable core runs under either harness. This
 * module is the harness-neutral half both bridges share:
 *
 * - The explicit route catalog semantics of CWE-008, mirrored into the
 *   canonical package from the CC-side catalog at commit fb714b7b
 *   (src/lib/council/providers.ts and src/lib/council/explicit-selection.ts,
 *   read in full by this unit). The CC module imports Command Center host
 *   functions and cannot be imported across repos or across harnesses, so
 *   the semantics live here in the canonical package and the parity
 *   surface (parity.ts) proves both bridges apply them identically.
 * - A guarded transport that wraps a harness delegate transport: the
 *   client's selected route reaches execution unchanged, a host attempt
 *   to execute a different model is refused or, only under a
 *   client-approved fallback policy with an approval record, surfaced as
 *   a recorded route-change event. Substitution is never silent.
 * - A bridge host composition over the CWE-004 standalone local host:
 *   council state is read and written ONLY through the CWE-004 ports
 *   (the shared local store in the per-user data directory), never a
 *   per-bridge private store, and the persisted state-authority mode is
 *   never silently switched (see assertStandaloneAuthorityMode).
 *
 * Identity law (Section 13.2): route identity has five distinct levels
 * and they are never conflated. A successful request is not proof of a
 * particular backend model, and runtime identity is never inferred from
 * a model's own prose response: a prose claim is recorded as ignored.
 *
 * Secret law (Sections 13.1, 28.5): credential VALUES never enter any
 * structure this module emits. Catalogs and selections carry credential
 * presence (env-var name and store label) only.
 *
 * Model law: this module prescribes no named model anywhere. The client
 * selects the route, or their configured default applies; the bridges
 * only carry the selection through unchanged.
 */

import type {
  Clock,
  ModelPolicy,
  ScopeFields,
} from '../contracts/index.js';
import { CouncilError, featureNotReady } from '../cli/errors.js';
import type {
  CouncilHost,
  CouncilStore,
  ModelTransport,
  TransportRequest,
  TransportResponse,
} from '../cli/host-ports.js';
import { createLocalHost, localScope } from '../cli/local-host.js';
import type { RouteDiscoveryInfo } from '../cli/route-discovery.js';

export type BridgeHarness = 'openclaw' | 'claude-nine';

/**
 * The state-authority mode both standalone bridges operate under
 * (Sections 5.4 and 25.6). It is persisted on the bridge instance and on
 * every grant the local composition admits; it is never silently
 * switched. Command Center mode is composed by the Command Center
 * adapter (CWE-007), not by these standalone bridges.
 */
export const STANDALONE_AUTHORITY_MODE = 'local_interactive_owner' as const;
export type StandaloneAuthorityMode = typeof STANDALONE_AUTHORITY_MODE;

/**
 * Fail closed when a caller asks a standalone bridge for a different
 * state-authority mode than the persisted standalone mode. Switching
 * modes silently would move council state authority without the owner
 * ever seeing it (Section 5.4), so any other mode is an honest
 * FEATURE_NOT_READY naming the owning unit, never a quiet local run.
 */
export function assertStandaloneAuthorityMode(
  requested: string | null | undefined,
): void {
  if (requested === undefined || requested === null) return;
  if (requested === STANDALONE_AUTHORITY_MODE) return;
  throw featureNotReady(
    `State-authority mode "${requested}" composition`,
    'the Command Center adapter (CWE-007); the standalone bridges persist local_interactive_owner and never switch modes silently',
  );
}

// ---------------------------------------------------------------------------
// Route identity levels (Section 13.2). Ordered weakest to strongest.
// ---------------------------------------------------------------------------

export const ROUTE_IDENTITY_LEVELS = [
  'configured',
  'transport_probed',
  'reported_identity',
  'resolved_identity_verified',
  'quality_qualified',
] as const;
export type RouteIdentityLevel = (typeof ROUTE_IDENTITY_LEVELS)[number];

export function identityLevelRank(level: RouteIdentityLevel): number {
  return ROUTE_IDENTITY_LEVELS.indexOf(level);
}

/**
 * The exact statement the product must show when a router hides the
 * underlying model identity (Section 13.2).
 */
export const HIDDEN_IDENTITY_STATEMENT =
  'Selected route used; underlying model identity not independently exposed.';

// ---------------------------------------------------------------------------
// Route kinds. A fixed-model route names one model. A combination route is
// an intentionally selected router combination (for example a 9Router
// combination): it may select among its configured members only, and it
// is never permission to add models, reorder members, or cross provider
// accounts (Section 13.3).
// ---------------------------------------------------------------------------

export type RouteKind = 'fixed_model' | 'combination';

// ---------------------------------------------------------------------------
// Credential presence. Names and presence only, never a value.
// ---------------------------------------------------------------------------

export type CredentialSourceName =
  | 'process.env'
  | 'env_file'
  | 'openclaw_json'
  | 'openclaw_auth_store';

export interface CredentialPresence {
  state: 'present' | 'absent' | 'not_required';
  /** Env-var NAME the credential was found under. Never the value. */
  envVar: string | null;
  /** Store the credential was found in. Never the value. */
  source: CredentialSourceName | null;
  /** Candidate env-var names checked when absent. Names only. */
  checked: string[];
}

// ---------------------------------------------------------------------------
// Capability snapshot. Frozen onto a selection at selection time (Section
// 13.3): a weekly model refresh can deprecate or rewrite catalog rows, so
// a session never re-reads live catalog facts at execution time.
// ---------------------------------------------------------------------------

export interface RouteCapabilitySnapshot {
  contextWindowTokens: number | null;
  maxOutputTokens: number | null;
  capabilities: string[];
  /**
   * Reasoning levels the route is documented or probed to support, in
   * the route's own vocabulary. Null means not yet probed: support is
   * unknown and no preference may be claimed active.
   */
  supportedReasoningLevels: string[] | null;
}

// ---------------------------------------------------------------------------
// Route descriptors: the configured-route facts a catalog is built from.
// Descriptors are inputs supplied by the installation's catalog owner;
// the bridges never invent routes and never resolve credential values.
// ---------------------------------------------------------------------------

export interface ProviderRouteDescriptor {
  /** Stable route reference, unique within the installation. */
  routeId: string;
  providerSlug: string;
  displayLabel: string;
  kind: RouteKind;
  /** The one named model for a fixed_model route. Null for combinations. */
  modelId: string | null;
  /**
   * Ordered, pinned member model ids for a combination route. The
   * approved combination is exactly this list. Empty for fixed routes.
   */
  combinationMembers: string[];
  /**
   * Opaque reference to the provider account this route is bound to.
   * Never a credential value.
   */
  providerAccountRef: string | null;
  capability: RouteCapabilitySnapshot;
  credential: CredentialPresence;
}

// ---------------------------------------------------------------------------
// Readiness and qualification evidence. Supplied by probe and evaluation
// owners (CWE-009 probes, CWE-042 qualification). The bridges define how
// the evidence maps to labels; they do not fabricate evidence.
// ---------------------------------------------------------------------------

export interface RouteEvidence {
  /** A real transport probe reached the endpoint for this route. */
  transportProbed: boolean;
  /** Identity the transport or provider reported, when it exposes one. */
  reportedModelId: string | null;
  /** Independent identity verification record, when one exists. */
  identityVerification: { verified: boolean; method: string } | null;
  /** Recorded quality evaluation, when one exists. */
  evaluation: {
    status: 'passed' | 'failed' | 'not_run';
    evaluationId: string | null;
    recordedAt: string | null;
  } | null;
}

export const NO_ROUTE_EVIDENCE: RouteEvidence = {
  transportProbed: false,
  reportedModelId: null,
  identityVerification: null,
  evaluation: null,
};

/**
 * Route readiness. A route that is merely listed is UNTESTED. A
 * transport probe raises it to PROBED, which is still not qualified.
 * Only a recorded, passing evaluation makes a route QUALIFIED.
 */
export type RouteReadiness = 'UNTESTED' | 'PROBED' | 'QUALIFIED';

export function deriveRouteReadiness(evidence: RouteEvidence): RouteReadiness {
  if (evidence.evaluation?.status === 'passed') return 'QUALIFIED';
  if (evidence.transportProbed) return 'PROBED';
  return 'UNTESTED';
}

/**
 * The strongest identity level the evidence supports, and no stronger.
 * An evaluation pass is required for `quality_qualified`; a provider
 * report alone never reaches `resolved_identity_verified`.
 */
export function deriveIdentityLevel(evidence: RouteEvidence): RouteIdentityLevel {
  if (evidence.evaluation?.status === 'passed') return 'quality_qualified';
  if (evidence.identityVerification?.verified) return 'resolved_identity_verified';
  if (evidence.reportedModelId) return 'reported_identity';
  if (evidence.transportProbed) return 'transport_probed';
  return 'configured';
}

// ---------------------------------------------------------------------------
// The catalog: safe route references plus qualification states. Every
// field here is client-safe: no credential values, no secrets, no server
// paths.
// ---------------------------------------------------------------------------

export interface RouteCatalogEntry {
  routeId: string;
  providerSlug: string;
  displayLabel: string;
  kind: RouteKind;
  modelId: string | null;
  combinationMembers: string[];
  providerAccountRef: string | null;
  capability: RouteCapabilitySnapshot;
  credential: CredentialPresence;
  identityLevel: RouteIdentityLevel;
  readiness: RouteReadiness;
  /** True only when a recorded evaluation passed. Listed is not qualified. */
  qualityQualified: boolean;
}

export function buildRouteCatalog(
  routes: ProviderRouteDescriptor[],
  evidenceByRouteId: ReadonlyMap<string, RouteEvidence> = new Map(),
): RouteCatalogEntry[] {
  return routes.map((route) => {
    const evidence = evidenceByRouteId.get(route.routeId) ?? NO_ROUTE_EVIDENCE;
    const readiness = deriveRouteReadiness(evidence);
    return {
      routeId: route.routeId,
      providerSlug: route.providerSlug,
      displayLabel: route.displayLabel,
      kind: route.kind,
      modelId: route.modelId,
      combinationMembers: [...route.combinationMembers],
      providerAccountRef: route.providerAccountRef,
      capability: {
        contextWindowTokens: route.capability.contextWindowTokens,
        maxOutputTokens: route.capability.maxOutputTokens,
        capabilities: [...route.capability.capabilities],
        supportedReasoningLevels: route.capability.supportedReasoningLevels
          ? [...route.capability.supportedReasoningLevels]
          : null,
      },
      credential: {
        state: route.credential.state,
        envVar: route.credential.envVar,
        source: route.credential.source,
        checked: [...route.credential.checked],
      },
      identityLevel: deriveIdentityLevel(evidence),
      readiness,
      qualityQualified: readiness === 'QUALIFIED',
    };
  });
}

export function findCatalogEntry(
  catalog: RouteCatalogEntry[],
  routeId: string,
): RouteCatalogEntry | null {
  return catalog.find((entry) => entry.routeId === routeId) ?? null;
}

// ---------------------------------------------------------------------------
// Selection errors (same codes as the CWE-008 catalog, so both harnesses
// report selection failures identically).
// ---------------------------------------------------------------------------

export type BridgeSelectionErrorCode =
  | 'ROUTE_NOT_IN_CATALOG'
  | 'UNTRUSTED_SCOPE_FIELD'
  | 'INVALID_SELECTION'
  | 'COMBINATION_MEMBER_REQUIRED';

export class BridgeSelectionError extends Error {
  readonly code: BridgeSelectionErrorCode;
  constructor(code: BridgeSelectionErrorCode, message: string) {
    super(message);
    this.name = 'BridgeSelectionError';
    this.code = code;
  }
}

// ---------------------------------------------------------------------------
// Trusted scope (host-filled only, mirroring the CWE-003 ScopeFields
// rule: a caller never gains authority by supplying these fields).
// ---------------------------------------------------------------------------

export interface TrustedScope {
  tenantId: string;
  companyId: string;
  installationId: string;
  ownerSubject: string | null;
}

export function trustedScopeFromScopeFields(scope: ScopeFields): TrustedScope {
  return {
    tenantId: scope.tenant_id,
    companyId: scope.company_id,
    installationId: scope.installation_id,
    ownerSubject: scope.owner_subject,
  };
}

export function scopeFieldsFromTrustedScope(scope: TrustedScope): ScopeFields {
  return {
    tenant_id: scope.tenantId,
    company_id: scope.companyId,
    installation_id: scope.installationId,
    owner_subject: scope.ownerSubject,
  };
}

/** Field names a client body may never use to establish scope. */
const SCOPE_FIELD_NAMES = [
  'tenant_id',
  'tenantId',
  'company_id',
  'companyId',
  'installation_id',
  'installationId',
  'owner_subject',
  'ownerSubject',
] as const;

// ---------------------------------------------------------------------------
// Selection snapshot: the exact selected route and alias, reasoning
// preference, fallback policy, account reference, and capability
// snapshot, persisted at selection time (Section 13.3).
// ---------------------------------------------------------------------------

export type BridgeModelSelectionSource =
  | 'explicit'
  | 'client_default'
  | 'route_default';
export type BridgeFallbackPolicy = 'none' | 'client_approved_only';

export interface ReasoningPreferenceOutcome {
  /** Exactly what the client asked for. Never renamed. */
  requested: string | null;
  /** What will actually be applied. Null when nothing may be claimed active. */
  applied: string | null;
  /** True/false when support is known; null when the route is unprobed. */
  supported: boolean | null;
  /** Plain-language limitation, present whenever applied differs from asked. */
  limitation: string | null;
}

export interface CouncilRouteSelection {
  schema: 'wise-elders.route-selection/v1';
  selectionSource: BridgeModelSelectionSource;
  routeId: string;
  routeRevision: number;
  routeKind: RouteKind;
  providerSlug: string;
  /** Exact requested route reference (the catalog route id). */
  requestedRoute: string;
  /** Requested model or alias for a fixed route. Null for combinations. */
  requestedModelOrAlias: string | null;
  /** Pinned, ordered combination members. Null for fixed routes. */
  combinationMembers: string[] | null;
  reasoning: ReasoningPreferenceOutcome;
  fallbackPolicy: BridgeFallbackPolicy;
  providerAccountRef: string | null;
  capabilitySnapshot: RouteCapabilitySnapshot;
  credential: CredentialPresence;
  /** Identity level at selection time; never stronger than the evidence. */
  identityLevel: RouteIdentityLevel;
  scope: TrustedScope;
  createdAt: string;
}

/**
 * Untrusted client input. Every field is a request, never evidence.
 * Scope fields are detected only so a conflict can be rejected; they are
 * never read as authority.
 */
export interface RouteSelectionRequest {
  routeId: string;
  selectionSource?: BridgeModelSelectionSource;
  requestedModelOrAlias?: string | null;
  reasoningPreference?: string | null;
  fallbackPolicy?: BridgeFallbackPolicy;
  providerAccountRef?: string | null;
  [key: string]: unknown;
}

function assertNoConflictingScopeFields(
  request: RouteSelectionRequest,
  scope: TrustedScope,
): void {
  const trustedByField: Record<string, string | null> = {
    tenant_id: scope.tenantId,
    tenantId: scope.tenantId,
    company_id: scope.companyId,
    companyId: scope.companyId,
    installation_id: scope.installationId,
    installationId: scope.installationId,
    owner_subject: scope.ownerSubject,
    ownerSubject: scope.ownerSubject,
  };
  for (const field of SCOPE_FIELD_NAMES) {
    const supplied = request[field];
    if (supplied === undefined || supplied === null) continue;
    if (String(supplied) !== String(trustedByField[field] ?? '')) {
      throw new BridgeSelectionError(
        'UNTRUSTED_SCOPE_FIELD',
        `Body-supplied ${field} conflicts with the trusted scope and is not proof of scope.`,
      );
    }
  }
}

function resolveReasoning(
  requested: string | null,
  capability: RouteCapabilitySnapshot,
): ReasoningPreferenceOutcome {
  if (requested === null) {
    return { requested: null, applied: null, supported: null, limitation: null };
  }
  // `auto` is preserved as no forced vendor-specific reasoning parameter.
  if (requested === 'auto') {
    return { requested, applied: 'auto', supported: true, limitation: null };
  }
  const supportedLevels = capability.supportedReasoningLevels;
  if (supportedLevels === null) {
    return {
      requested,
      applied: null,
      supported: null,
      limitation:
        `Reasoning preference "${requested}" is recorded, but this route has not been probed ` +
        'for reasoning support, so the preference is not claimed active.',
    };
  }
  if (supportedLevels.includes(requested)) {
    return { requested, applied: requested, supported: true, limitation: null };
  }
  return {
    requested,
    applied: null,
    supported: false,
    limitation:
      `Reasoning preference "${requested}" is not supported by this route. ` +
      `Supported levels: ${supportedLevels.join(', ') || 'none documented'}. ` +
      'The requested value is retained as requested; it was not renamed to another level ' +
      'and is not claimed active.',
  };
}

/**
 * Create the pinned selection snapshot for a session revision. The
 * catalog entry is the frozen route fact source; the scope is the
 * trusted host argument only.
 */
export function createRouteSelection(
  entry: RouteCatalogEntry,
  request: RouteSelectionRequest,
  trustedScope: TrustedScope,
  options: { routeRevision: number; createdAt: string },
): CouncilRouteSelection {
  if (request.routeId !== entry.routeId) {
    throw new BridgeSelectionError(
      'ROUTE_NOT_IN_CATALOG',
      `Requested route ${request.routeId} does not match catalog entry ${entry.routeId}.`,
    );
  }
  assertNoConflictingScopeFields(request, trustedScope);

  if (entry.kind === 'fixed_model') {
    const requestedModel = request.requestedModelOrAlias ?? entry.modelId;
    if (!requestedModel || requestedModel !== entry.modelId) {
      throw new BridgeSelectionError(
        'INVALID_SELECTION',
        'A fixed-model selection must name the exact catalog model for the route.',
      );
    }
  }
  if (entry.kind === 'combination' && entry.combinationMembers.length === 0) {
    throw new BridgeSelectionError(
      'COMBINATION_MEMBER_REQUIRED',
      'A combination route must carry its pinned member list.',
    );
  }

  const fallbackPolicy: BridgeFallbackPolicy = request.fallbackPolicy ?? 'none';
  const reasoning = resolveReasoning(
    request.reasoningPreference ?? null,
    entry.capability,
  );

  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: request.selectionSource ?? 'explicit',
    routeId: entry.routeId,
    routeRevision: options.routeRevision,
    routeKind: entry.kind,
    providerSlug: entry.providerSlug,
    requestedRoute: entry.routeId,
    requestedModelOrAlias: entry.kind === 'fixed_model' ? entry.modelId : null,
    combinationMembers:
      entry.kind === 'combination' ? [...entry.combinationMembers] : null,
    reasoning,
    fallbackPolicy,
    providerAccountRef: request.providerAccountRef ?? entry.providerAccountRef,
    capabilitySnapshot: {
      contextWindowTokens: entry.capability.contextWindowTokens,
      maxOutputTokens: entry.capability.maxOutputTokens,
      capabilities: [...entry.capability.capabilities],
      supportedReasoningLevels: entry.capability.supportedReasoningLevels
        ? [...entry.capability.supportedReasoningLevels]
        : null,
    },
    credential: {
      state: entry.credential.state,
      envVar: entry.credential.envVar,
      source: entry.credential.source,
      checked: [...entry.credential.checked],
    },
    identityLevel: entry.identityLevel,
    scope: { ...trustedScope },
    createdAt: options.createdAt,
  };
}

/**
 * Build the pinned selection from a frozen session spec's model policy
 * (CWE-003 ModelPolicy). This is how a bridge binds the route the
 * session actually selected: the spec is the frozen fact, never a live
 * re-read of the catalog at execution time.
 */
export function selectionFromModelPolicy(
  entry: RouteCatalogEntry,
  policy: ModelPolicy,
  scope: ScopeFields,
  options: { routeRevision: number; createdAt: string },
): CouncilRouteSelection {
  return createRouteSelection(
    entry,
    {
      routeId: entry.routeId,
      selectionSource: policy.selection,
      requestedModelOrAlias: policy.requested_model_id,
      reasoningPreference: policy.reasoning_preference,
      fallbackPolicy: policy.fallback_policy,
    },
    trustedScopeFromScopeFields(scope),
    options,
  );
}

// ---------------------------------------------------------------------------
// Host resolution guard. The harness reports what it actually resolved;
// this guard decides whether that resolution may stand for a council
// selection, and records the outcome explicitly either way. Identical
// semantics to the CWE-008 catalog guard (same branches, same order), so
// both harnesses produce the same catalog behavior for the same
// selection.
// ---------------------------------------------------------------------------

export type HostResolutionSource =
  | 'explicit_route'
  | 'cascade'
  | 'sovereign_default'
  | 'runtime_reconcile'
  | 'combination_member'
  | 'fallback';

export interface ClientFallbackApproval {
  approvalRef: string;
  reason: string;
  /** Cost implications of the change, stated by the approval record. */
  costImplication: string;
}

export interface HostResolutionAttempt {
  source: HostResolutionSource;
  /** Model the host used or tried to use, when the transport exposes one. */
  attemptedModelId: string | null;
  /**
   * Identity reported by the transport or provider through a structured
   * field. This is the only reported-identity input. Null when the
   * router hides the underlying model.
   */
  reportedModelId?: string | null;
  /**
   * A model identity claimed in a model's own prose response. Accepted
   * only so the outcome can record that it was ignored: prose is never
   * identity evidence (Section 13.2).
   */
  proseClaimedModelId?: string | null;
  /** Client approval for a fallback change, when one exists. */
  approval?: ClientFallbackApproval | null;
}

export interface RouteChangeRecord {
  reason: string;
  originalRoute: string;
  replacementRoute: string;
  costImplications: string;
  newRouteRevision: number;
  approvalRef: string;
}

export type RouteResolutionEvent =
  | {
      type: 'route_resolution_accepted';
      routeId: string;
      effectiveModelId: string | null;
      source: HostResolutionSource;
    }
  | {
      type: 'substitution_refused';
      routeId: string;
      requestedModelOrAlias: string | null;
      attemptedModelId: string | null;
      source: HostResolutionSource;
      reason: string;
    }
  | {
      type: 'substitution_approved';
      routeId: string;
      change: RouteChangeRecord;
    }
  | {
      type: 'combination_member_resolved';
      routeId: string;
      memberModelId: string;
    }
  | {
      type: 'identity_not_exposed';
      routeId: string;
      statement: string;
    }
  | {
      type: 'prose_identity_claim_ignored';
      routeId: string;
      claimedModelId: string;
    };

export interface RouteResolutionOutcome {
  outcome: 'accepted' | 'refused' | 'substituted_with_approval';
  /** The model the council may proceed with. Null when refused. */
  effectiveModelId: string | null;
  /** Strongest identity level the structured evidence supports. */
  identityLevel: RouteIdentityLevel;
  /** Set when the underlying identity is hidden and must be disclosed. */
  identityStatement: string | null;
  changeRecord: RouteChangeRecord | null;
  events: RouteResolutionEvent[];
}

function refusedOutcome(
  selection: CouncilRouteSelection,
  attempt: HostResolutionAttempt,
  reason: string,
  events: RouteResolutionEvent[],
): RouteResolutionOutcome {
  events.push({
    type: 'substitution_refused',
    routeId: selection.routeId,
    requestedModelOrAlias: selection.requestedModelOrAlias,
    attemptedModelId: attempt.attemptedModelId,
    source: attempt.source,
    reason,
  });
  return {
    outcome: 'refused',
    effectiveModelId: null,
    identityLevel: selection.identityLevel,
    identityStatement: null,
    changeRecord: null,
    events,
  };
}

export function applyHostResolution(
  selection: CouncilRouteSelection,
  attempt: HostResolutionAttempt,
): RouteResolutionOutcome {
  const events: RouteResolutionEvent[] = [];

  // A prose claim is recorded as ignored and never consulted again below.
  if (attempt.proseClaimedModelId) {
    events.push({
      type: 'prose_identity_claim_ignored',
      routeId: selection.routeId,
      claimedModelId: attempt.proseClaimedModelId,
    });
  }

  const reported = attempt.reportedModelId ?? null;
  let identityLevel: RouteIdentityLevel = selection.identityLevel;
  if (
    reported !== null &&
    identityLevelRank(identityLevel) < identityLevelRank('reported_identity')
  ) {
    identityLevel = 'reported_identity';
  }

  if (selection.routeKind === 'combination') {
    return resolveCombination(selection, attempt, reported, identityLevel, events);
  }
  return resolveFixedModel(selection, attempt, reported, identityLevel, events);
}

function resolveFixedModel(
  selection: CouncilRouteSelection,
  attempt: HostResolutionAttempt,
  reported: string | null,
  identityLevel: RouteIdentityLevel,
  events: RouteResolutionEvent[],
): RouteResolutionOutcome {
  const requested = selection.requestedModelOrAlias;
  const attempted = attempt.attemptedModelId ?? reported;

  // The provider-reported identity conflicts with the requested model:
  // the requested and observed identities are kept distinct and the
  // conflict is surfaced, never smoothed over.
  if (reported !== null && requested !== null && reported !== requested) {
    return refusedOutcome(
      selection,
      { ...attempt, attemptedModelId: reported },
      'Provider-reported identity differs from the requested model for this fixed-model selection.',
      events,
    );
  }

  if (attempted !== null && requested !== null && attempted === requested) {
    events.push({
      type: 'route_resolution_accepted',
      routeId: selection.routeId,
      effectiveModelId: attempted,
      source: attempt.source,
    });
    return {
      outcome: 'accepted',
      effectiveModelId: attempted,
      identityLevel,
      identityStatement: null,
      changeRecord: null,
      events,
    };
  }

  if (attempted === null) {
    // The transport exposed no model at all. The selected route was used
    // but its identity is not independently exposed, and that must be said.
    events.push({
      type: 'identity_not_exposed',
      routeId: selection.routeId,
      statement: HIDDEN_IDENTITY_STATEMENT,
    });
    return {
      outcome: 'accepted',
      effectiveModelId: requested,
      identityLevel: selection.identityLevel,
      identityStatement: HIDDEN_IDENTITY_STATEMENT,
      changeRecord: null,
      events,
    };
  }

  // The host resolved a different model than the client selected.
  if (selection.fallbackPolicy === 'client_approved_only' && attempt.approval) {
    const change: RouteChangeRecord = {
      reason: attempt.approval.reason,
      originalRoute: selection.requestedRoute,
      replacementRoute: attempted,
      costImplications: attempt.approval.costImplication,
      newRouteRevision: selection.routeRevision + 1,
      approvalRef: attempt.approval.approvalRef,
    };
    events.push({ type: 'substitution_approved', routeId: selection.routeId, change });
    return {
      outcome: 'substituted_with_approval',
      effectiveModelId: attempted,
      identityLevel,
      identityStatement: null,
      changeRecord: change,
      events,
    };
  }

  return refusedOutcome(
    selection,
    attempt,
    selection.fallbackPolicy === 'none'
      ? 'Fallback policy is none: a fixed-model council selection may not be replaced.'
      : 'Fallback requires a client approval record for this session.',
    events,
  );
}

function resolveCombination(
  selection: CouncilRouteSelection,
  attempt: HostResolutionAttempt,
  reported: string | null,
  identityLevel: RouteIdentityLevel,
  events: RouteResolutionEvent[],
): RouteResolutionOutcome {
  const members = selection.combinationMembers ?? [];
  const exposedMember = attempt.attemptedModelId ?? reported;

  if (exposedMember !== null) {
    if (!members.includes(exposedMember)) {
      return refusedOutcome(
        selection,
        attempt,
        'Resolved model is not a member of the approved combination. ' +
          'A combination is not permission to add models or cross provider accounts.',
        events,
      );
    }
    events.push({
      type: 'combination_member_resolved',
      routeId: selection.routeId,
      memberModelId: exposedMember,
    });
    events.push({
      type: 'route_resolution_accepted',
      routeId: selection.routeId,
      effectiveModelId: exposedMember,
      source: attempt.source,
    });
    return {
      outcome: 'accepted',
      effectiveModelId: exposedMember,
      identityLevel,
      identityStatement: null,
      changeRecord: null,
      events,
    };
  }

  // The router hid the member identity. The combination stands, the
  // member is not invented, and the limitation is stated with the exact
  // sentence.
  events.push({
    type: 'identity_not_exposed',
    routeId: selection.routeId,
    statement: HIDDEN_IDENTITY_STATEMENT,
  });
  return {
    outcome: 'accepted',
    effectiveModelId: null,
    identityLevel: selection.identityLevel,
    identityStatement: HIDDEN_IDENTITY_STATEMENT,
    changeRecord: null,
    events,
  };
}

// ---------------------------------------------------------------------------
// Client payload projection. A whitelist copy: only the fields a client
// may see, in a stable shape. Credential presence travels; values never
// exist in the selection, so they cannot leak here.
// ---------------------------------------------------------------------------

export function selectionClientPayload(selection: CouncilRouteSelection) {
  return {
    schema: selection.schema,
    routeId: selection.routeId,
    routeRevision: selection.routeRevision,
    routeKind: selection.routeKind,
    providerSlug: selection.providerSlug,
    requestedRoute: selection.requestedRoute,
    requestedModelOrAlias: selection.requestedModelOrAlias,
    combinationMembers: selection.combinationMembers
      ? [...selection.combinationMembers]
      : null,
    reasoning: { ...selection.reasoning },
    fallbackPolicy: selection.fallbackPolicy,
    providerAccountRef: selection.providerAccountRef,
    capability: {
      contextWindowTokens: selection.capabilitySnapshot.contextWindowTokens,
      maxOutputTokens: selection.capabilitySnapshot.maxOutputTokens,
      capabilities: [...selection.capabilitySnapshot.capabilities],
      supportedReasoningLevels: selection.capabilitySnapshot.supportedReasoningLevels
        ? [...selection.capabilitySnapshot.supportedReasoningLevels]
        : null,
    },
    credential: {
      state: selection.credential.state,
      envVar: selection.credential.envVar,
      source: selection.credential.source,
    },
    identityLevel: selection.identityLevel,
    companyId: selection.scope.companyId,
  };
}

// ---------------------------------------------------------------------------
// Resolution journal. Every resolution outcome a bridge produces is
// recorded here, in order, with its full event list: a substitution is
// impossible to hide because refused and approved changes both land in
// the same journal the parity surface and operators read. (The frozen
// CWE-003 CouncilEvent vocabulary has no route-change event type, so
// route records live in this bridge journal rather than being forced
// into a mismatched session event type; CWE-030/CWE-040 consume it.)
// ---------------------------------------------------------------------------

export interface RouteResolutionRecord {
  harness: BridgeHarness;
  route_id: string;
  session_id: string | null;
  outcome: RouteResolutionOutcome;
  recorded_at: string;
}

export class RouteResolutionJournal {
  private readonly records: RouteResolutionRecord[] = [];

  record(entry: RouteResolutionRecord): void {
    this.records.push(entry);
  }

  list(): RouteResolutionRecord[] {
    return [...this.records];
  }

  /** All recorded route-change events (refusals and approved changes). */
  routeChanges(): RouteResolutionRecord[] {
    return this.records.filter(
      (r) =>
        r.outcome.outcome === 'refused' ||
        r.outcome.outcome === 'substituted_with_approval',
    );
  }
}

// ---------------------------------------------------------------------------
// Guarded transport. Wraps a harness delegate transport (CWE-009 owns
// the real HTTP/local transports) and enforces the pinned selection on
// every request: the harness reports what it resolved, the guard
// decides, and only an accepted resolution reaches the delegate.
// ---------------------------------------------------------------------------

/** Thrown when the guard refuses a host resolution. Never retryable. */
export class RouteResolutionRefusedError extends Error {
  readonly retryable = false;
  readonly outcome: RouteResolutionOutcome;
  constructor(selection: CouncilRouteSelection, outcome: RouteResolutionOutcome) {
    const refusal = outcome.events.find((e) => e.type === 'substitution_refused');
    const reason =
      refusal && refusal.type === 'substitution_refused'
        ? refusal.reason
        : 'The host resolution did not preserve the selected route.';
    super(
      `Route resolution refused for route ${selection.routeId}: ${reason} ` +
        'The refusal was recorded as a substitution_refused event; the selected route was not replaced.',
    );
    this.name = 'RouteResolutionRefusedError';
    this.outcome = outcome;
  }
}

export interface GuardedTransportOptions {
  harness: BridgeHarness;
  selection: CouncilRouteSelection;
  delegate: ModelTransport;
  /**
   * The harness's own report of what it resolved for this request,
   * inside its own harness only. Supplied by the bridge (OpenClaw or
   * Claude-Nine), never by the other harness.
   */
  reportAttempt: (
    selection: CouncilRouteSelection,
    request: TransportRequest,
  ) => HostResolutionAttempt | Promise<HostResolutionAttempt>;
  journal: RouteResolutionJournal;
  clock: Clock;
}

export class GuardedTransport implements ModelTransport {
  private readonly options: GuardedTransportOptions;

  constructor(options: GuardedTransportOptions) {
    this.options = options;
  }

  get selection(): CouncilRouteSelection {
    return this.options.selection;
  }

  async generate(request: TransportRequest): Promise<TransportResponse> {
    const { selection, journal, clock, harness } = this.options;
    if (request.route_id !== selection.routeId) {
      throw new CouncilError(
        'COUNCIL_ROUTE_UNAVAILABLE',
        `Request was issued for route ${request.route_id} but this bridge guards route ${selection.routeId}. The selected route is never silently replaced.`,
        { retryable: false, exitCode: 3 },
      );
    }
    const attempt = await this.options.reportAttempt(selection, request);
    const outcome = applyHostResolution(selection, attempt);
    journal.record({
      harness,
      route_id: selection.routeId,
      session_id: request.session_id,
      outcome,
      recorded_at: clock.nowUtc(),
    });
    if (outcome.outcome === 'refused') {
      throw new RouteResolutionRefusedError(selection, outcome);
    }
    return this.options.delegate.generate(request);
  }
}

// ---------------------------------------------------------------------------
// Bridge host composition. Both bridges compose the SAME CWE-004 local
// host (same store implementation, same per-user data directory rules),
// so council state authority is identical on both harnesses and a
// session created through one bridge is readable through the other.
// ---------------------------------------------------------------------------

export interface BridgeRouteBinding {
  routeId: string;
  /** The harness delegate transport that performs accepted requests. */
  delegate: ModelTransport;
  /** The harness's resolution report for each request. */
  reportAttempt: (
    selection: CouncilRouteSelection,
    request: TransportRequest,
  ) => HostResolutionAttempt | Promise<HostResolutionAttempt>;
  /** Frozen session model policy, when the binding serves a session spec. */
  policy?: ModelPolicy;
  /** Explicit selection request, used when no policy is supplied. */
  request?: RouteSelectionRequest;
  /** Trusted scope for the selection. Defaults to the bridge scope. */
  scope?: ScopeFields;
  routeRevision?: number;
}

export interface BridgeHostOptions {
  dataDir?: string;
  skillRoot?: string;
  /**
   * Requested state-authority mode. Anything other than the persisted
   * standalone mode fails closed (assertStandaloneAuthorityMode); the
   * mode is never silently switched.
   */
  authorityMode?: string;
  /** Configured route descriptors for this installation's catalog. */
  routes?: ProviderRouteDescriptor[];
  evidenceByRouteId?: ReadonlyMap<string, RouteEvidence>;
  bindings?: BridgeRouteBinding[];
  /** Trusted scope for selections. Defaults to the standalone local scope. */
  scope?: ScopeFields;
  /** Home directory route discovery reads under. Default: the OS home. */
  homeDir?: string;
  /** Environment route discovery and credential presence read. Default: process.env. */
  env?: NodeJS.ProcessEnv;
  /** Compose real transports for discovered routes. Default true. */
  discoverRoutes?: boolean;
}

export interface BridgeInstance {
  harness: BridgeHarness;
  host: CouncilHost;
  dataDir: string;
  store: CouncilStore;
  catalog: RouteCatalogEntry[];
  /**
   * Secret-free route-discovery diagnostics from the SAME local host the
   * bridge composes (RP-046-1). Carried through so a wrapper that hands
   * the bridge to the CLI never swallows `models`/`doctor` diagnostics.
   */
  routeDiscovery: RouteDiscoveryInfo[];
  selections: ReadonlyMap<string, CouncilRouteSelection>;
  journal: RouteResolutionJournal;
  authorityMode: typeof STANDALONE_AUTHORITY_MODE;
}

export function composeBridgeHost(
  harness: BridgeHarness,
  options: BridgeHostOptions = {},
): BridgeInstance {
  assertStandaloneAuthorityMode(options.authorityMode);
  const { host, dataDir, store, routeDiscovery } = createLocalHost({
    dataDir: options.dataDir,
    skillRoot: options.skillRoot,
    homeDir: options.homeDir,
    env: options.env,
    discoverRoutes: options.discoverRoutes,
  });
  const catalog = buildRouteCatalog(
    options.routes ?? [],
    options.evidenceByRouteId ?? new Map(),
  );
  const journal = new RouteResolutionJournal();
  const bridgeScope = options.scope ?? localScope();
  const selections = new Map<string, CouncilRouteSelection>();
  for (const binding of options.bindings ?? []) {
    const entry = findCatalogEntry(catalog, binding.routeId);
    if (!entry) {
      throw new BridgeSelectionError(
        'ROUTE_NOT_IN_CATALOG',
        `Route ${binding.routeId} is not in this installation's route catalog. The bridge never invents a route.`,
      );
    }
    const scope = binding.scope ?? bridgeScope;
    const createdAt = host.clock.nowUtc();
    const selection = binding.policy
      ? selectionFromModelPolicy(entry, binding.policy, scope, {
          routeRevision: binding.routeRevision ?? 1,
          createdAt,
        })
      : createRouteSelection(
          entry,
          binding.request ?? { routeId: binding.routeId },
          trustedScopeFromScopeFields(scope),
          { routeRevision: binding.routeRevision ?? 1, createdAt },
        );
    selections.set(binding.routeId, selection);
    host.transportRegistry.register(
      binding.routeId,
      new GuardedTransport({
        harness,
        selection,
        delegate: binding.delegate,
        reportAttempt: binding.reportAttempt,
        journal,
        clock: host.clock,
      }),
    );
  }
  return {
    harness,
    host,
    dataDir,
    store,
    catalog,
    routeDiscovery: routeDiscovery ?? [],
    selections,
    journal,
    authorityMode: STANDALONE_AUTHORITY_MODE,
  };
}
