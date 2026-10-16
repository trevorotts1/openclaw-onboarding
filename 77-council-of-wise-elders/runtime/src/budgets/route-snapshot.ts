/**
 * The pinned route snapshot the budget service charges against
 * (CWE-028, directive Sections 13 and 15.6).
 *
 * These types mirror, field for field, the CWE-008 explicit route
 * catalog semantics defined in the Command Center worktree
 * (src/lib/council/providers.ts and explicit-selection.ts, CWE-008
 * commit fb714b7b): the CouncilRouteSelection snapshot, the five route
 * identity levels in ascending strength order, the hidden-identity
 * statement, the RouteChangeRecord, and the RouteResolutionOutcome.
 * The shapes are consumed here, never re-derived: the runtime does not
 * import Command Center code across the repository boundary, so the
 * snapshot arrives as data (host-filled by the selection layer) and is
 * pinned verbatim into the durable event journal with the reservation
 * it pays for.
 *
 * Accounting law that follows from the mirror:
 * - A reservation names exactly one pinned snapshot (route id, route
 *   revision, ordered combination members, reasoning outcome). The
 *   snapshot is stored with the operation_reserved journal event and
 *   never edited afterwards; a reservation cannot migrate routes.
 * - A reasoning preference the route does not support stays recorded
 *   as requested with `applied: null`; the budget service never
 *   renames it and never treats it as active (CWE-008 guarantee 1).
 * - Credential material is presence only (env var name and source);
 *   no credential value exists in this shape, so none can be charged,
 *   logged, or leaked through accounting.
 * - A prose identity claim is never identity evidence: resolution
 *   outcomes carry it only as a `prose_identity_claim_ignored` event.
 */

import { canonicalHash } from '../contracts/index.js';

/** The five route identity levels, weakest to strongest (Section 13.4). */
export const ROUTE_IDENTITY_LEVELS = [
  'configured',
  'transport_probed',
  'reported_identity',
  'resolved_identity_verified',
  'quality_qualified',
] as const;
export type RouteIdentityLevel = (typeof ROUTE_IDENTITY_LEVELS)[number];

/**
 * The exact statement shown when a router hides the underlying model
 * identity (Section 13.4; identical to CWE-008's
 * HIDDEN_IDENTITY_STATEMENT).
 */
export const HIDDEN_IDENTITY_STATEMENT =
  'Selected route used; underlying model identity not independently exposed.';

export type RouteKind = 'fixed_model' | 'combination';
export type ModelSelectionSource = 'explicit' | 'client_default' | 'route_default';
export type FallbackPolicy = 'none' | 'client_approved_only';

/** Trusted scope in the CWE-008 (host-filled) field naming. */
export interface RouteTrustedScope {
  tenantId: string;
  companyId: string;
  installationId: string;
  ownerSubject: string | null;
}

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

export interface RouteCapabilitySnapshot {
  contextWindowTokens: number | null;
  maxOutputTokens: number | null;
  capabilities: string[];
  supportedReasoningLevels: string[] | null;
}

/** Credential presence only: a name and a source, never a value. */
export interface CredentialPresence {
  state: string;
  envVar: string | null;
  source: string | null;
  checked: string[];
}

/**
 * The pinned selection snapshot (CWE-008 CouncilRouteSelection). The
 * budget service treats this as an opaque, immutable charge target:
 * it validates the trusted scope against the caller's authorization
 * envelope and fingerprints the whole snapshot into the journal.
 */
export interface PinnedRouteSnapshot {
  schema: 'wise-elders.route-selection/v1';
  selectionSource: ModelSelectionSource;
  routeId: string;
  routeRevision: number;
  routeKind: RouteKind;
  providerSlug: string;
  requestedRoute: string;
  requestedModelOrAlias: string | null;
  /** Pinned, ordered combination members. Null for fixed routes. */
  combinationMembers: string[] | null;
  reasoning: ReasoningPreferenceOutcome;
  fallbackPolicy: FallbackPolicy;
  providerAccountRef: string | null;
  capabilitySnapshot: RouteCapabilitySnapshot;
  credential: CredentialPresence;
  identityLevel: RouteIdentityLevel;
  scope: RouteTrustedScope;
  createdAt: string;
}

/** An approved route change, as recorded by CWE-008's guard. */
export interface RouteChangeRecord {
  reason: string;
  originalRoute: string;
  replacementRoute: string;
  costImplications: string;
  newRouteRevision: number;
  approvalRef: string;
}

export type HostResolutionSource =
  | 'explicit_route'
  | 'cascade'
  | 'sovereign_default'
  | 'runtime_reconcile'
  | 'combination_member'
  | 'fallback';

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

/**
 * The outcome of applying a host resolution to a pinned selection
 * (CWE-008 RouteResolutionOutcome). `refused` outcomes never mint a
 * reservation; `substituted_with_approval` outcomes mint against the
 * replacement route's new pinned snapshot, with this outcome (and its
 * change record) journaled alongside the reservation.
 */
export interface RouteResolutionOutcome {
  outcome: 'accepted' | 'refused' | 'substituted_with_approval';
  effectiveModelId: string | null;
  identityLevel: RouteIdentityLevel;
  identityStatement: string | null;
  changeRecord: RouteChangeRecord | null;
  events: RouteResolutionEvent[];
}

/** Canonical fingerprint of a pinned snapshot, for journal audit. */
export function routeSnapshotFingerprint(snapshot: PinnedRouteSnapshot): string {
  return canonicalHash(snapshot as unknown as Record<string, unknown>);
}
