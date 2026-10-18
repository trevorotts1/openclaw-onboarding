/**
 * Pinned route selections and route-resolution evaluation (CWE-009).
 *
 * The shapes in this module mirror the CWE-008 explicit route catalog
 * (blackceo-command-center, src/lib/council/providers.ts and
 * explicit-selection.ts, accepted at CC commit fb714b7b) field for
 * field, so a selection snapshot created on the Command Center side
 * crosses the repo boundary unchanged and reaches the transport
 * byte-identical. CWE-009 consumes the catalog; it does not create
 * selections, select models, or run any cascade.
 *
 * Pinning law (Sections 13.2 and 13.6): the transport is constructed
 * with ONE frozen selection snapshot. The endpoint and the wire model
 * come only from that snapshot and the transport's configured binding,
 * never from the per-request policy, so substitution is impossible by
 * construction; any attempted substitution is refused before dispatch
 * or surfaced as a recorded route-resolution outcome, never silent.
 *
 * Identity law (Section 13.4): five levels, never conflated, and
 * identity is never inferred from model prose. A transport can raise
 * evidence only to transport_probed or reported_identity; the two
 * stronger levels require an independent verification record or a
 * recorded passing evaluation, which a transport never fabricates.
 */

import { canonicalHash } from '../contracts/index.js';

// ---------------------------------------------------------------------------
// Identity levels (mirror of CWE-008 ROUTE_IDENTITY_LEVELS, Section 13.4)
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

/** Stronger of two levels, by the Section 13.4 ordering. */
export function maxIdentityLevel(
  a: RouteIdentityLevel,
  b: RouteIdentityLevel,
): RouteIdentityLevel {
  return identityLevelRank(a) >= identityLevelRank(b) ? a : b;
}

/**
 * The exact statement shown when a router hides the underlying model
 * identity (Section 13.4). Mirrors CWE-008 verbatim.
 */
export const HIDDEN_IDENTITY_STATEMENT =
  'Selected route used; underlying model identity not independently exposed.';

// ---------------------------------------------------------------------------
// Selection snapshot (mirror of CWE-008 CouncilRouteSelection)
// ---------------------------------------------------------------------------

export type RouteKind = 'fixed_model' | 'combination';
// Identical value sets to CWE-008; the canonical CWE-003 contract types
// are used and re-exported so the package surface carries one definition.
import type {
  FallbackPolicy,
  ModelSelectionSource,
} from '../contracts/index.js';
export type { FallbackPolicy, ModelSelectionSource };

export type CredentialSourceName =
  | 'process.env'
  | 'env_file'
  | 'openclaw_json'
  | 'openclaw_auth_store';

/** Credential presence only: names and state, never a value. */
export interface CredentialPresence {
  state: 'present' | 'absent' | 'not_required';
  envVar: string | null;
  source: CredentialSourceName | null;
  checked: string[];
}

export interface RouteCapabilitySnapshot {
  contextWindowTokens: number | null;
  maxOutputTokens: number | null;
  capabilities: string[];
  supportedReasoningLevels: string[] | null;
}

export interface ReasoningPreferenceOutcome {
  requested: string | null;
  applied: string | null;
  supported: boolean | null;
  limitation: string | null;
}

export interface TrustedScope {
  tenantId: string;
  companyId: string;
  installationId: string;
  ownerSubject: string | null;
}

/** The pinned selection snapshot a transport is bound to. */
export interface CouncilRouteSelection {
  schema: 'wise-elders.route-selection/v1';
  selectionSource: ModelSelectionSource;
  routeId: string;
  routeRevision: number;
  routeKind: RouteKind;
  providerSlug: string;
  requestedRoute: string;
  requestedModelOrAlias: string | null;
  combinationMembers: string[] | null;
  reasoning: ReasoningPreferenceOutcome;
  fallbackPolicy: FallbackPolicy;
  providerAccountRef: string | null;
  capabilitySnapshot: RouteCapabilitySnapshot;
  credential: CredentialPresence;
  identityLevel: RouteIdentityLevel;
  scope: TrustedScope;
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Freezing and integrity. The transport freezes a deep copy at
// construction and recomputes this canonical hash before every
// dispatch: a mutated selection is a pinning failure, never a new route.
// ---------------------------------------------------------------------------

/** Canonical SHA-256 of the selection snapshot (CWE-003 canonical JSON). */
export function selectionSha256(selection: CouncilRouteSelection): string {
  return canonicalHash(selection);
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    for (const key of Object.keys(value as Record<string, unknown>)) {
      deepFreeze((value as Record<string, unknown>)[key]);
    }
    Object.freeze(value);
  }
  return value;
}

/**
 * A deep-frozen deep copy of any JSON-shaped value. Later mutation of the
 * caller's object cannot move the pin. Shared with route-snapshot.ts.
 */
export function freezeCopy<T>(value: T): T {
  return deepFreeze(JSON.parse(JSON.stringify(value)) as T);
}

/** A deep-frozen deep copy: later mutation of the caller's object cannot move the pin. */
export function freezeSelection(
  selection: CouncilRouteSelection,
): CouncilRouteSelection {
  return freezeCopy(selection);
}

// ---------------------------------------------------------------------------
// Evidence and identity derivation (mirror of CWE-008 deriveIdentityLevel)
// ---------------------------------------------------------------------------

export interface RouteEvidence {
  transportProbed: boolean;
  reportedModelId: string | null;
  identityVerification: { verified: boolean; method: string } | null;
  evaluation: {
    status: 'passed' | 'failed' | 'not_run';
    evaluationId: string | null;
    recordedAt: string | null;
  } | null;
}

/**
 * The strongest identity level the evidence supports, and no stronger.
 * Transport evidence alone (a probe, a provider-reported id) can never
 * reach resolved_identity_verified or quality_qualified.
 */
export function deriveIdentityLevel(evidence: RouteEvidence): RouteIdentityLevel {
  if (evidence.evaluation?.status === 'passed') return 'quality_qualified';
  if (evidence.identityVerification?.verified) return 'resolved_identity_verified';
  if (evidence.reportedModelId) return 'reported_identity';
  if (evidence.transportProbed) return 'transport_probed';
  return 'configured';
}

// ---------------------------------------------------------------------------
// Route-resolution evaluation (mirror of CWE-008 applyHostResolution).
// The execution owner (CWE-009) reports what the transport actually did
// through a HostResolutionAttempt; this guard decides whether that
// resolution may stand for the pinned selection, and records the outcome
// explicitly either way.
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
  costImplication: string;
}

export interface HostResolutionAttempt {
  source: HostResolutionSource;
  attemptedModelId: string | null;
  /**
   * Identity reported through a structured transport field (for example
   * the response body's model field). The ONLY reported-identity input.
   */
  reportedModelId?: string | null;
  /**
   * An identity claimed in a model's own prose. Accepted only so the
   * outcome can record that it was ignored: prose is never evidence.
   * The HTTP transports in this unit never populate this field; they do
   * not parse prose for identity at all.
   */
  proseClaimedModelId?: string | null;
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
  effectiveModelId: string | null;
  identityLevel: RouteIdentityLevel;
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

/**
 * Decide whether a reported host resolution may stand for the pinned
 * selection. Mirrors CWE-008's applyHostResolution semantics exactly:
 * a fixed-model provider report that conflicts with the requested model
 * is refused; a combination resolves only to an approved member; a
 * hidden identity is accepted with the exact disclosure statement and
 * is never invented.
 */
export function evaluateRouteResolution(
  selection: CouncilRouteSelection,
  attempt: HostResolutionAttempt,
): RouteResolutionOutcome {
  const events: RouteResolutionEvent[] = [];

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
