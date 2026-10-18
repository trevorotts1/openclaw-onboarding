/**
 * Frozen normalized route snapshot (WER-006 contract slice).
 *
 * This module publishes the route/model/effort contract that WER-007,
 * WER-008 and WER-009 consume. It does NOT dispatch, probe, authenticate,
 * or capture a transport: the bounded probe dispatch is the rest of
 * WER-006 and stays deferred.
 *
 * Laws:
 * - One snapshot is self-contained. It holds values, never a reference to
 *   a live default profile, so changing a global default cannot reroute an
 *   already-frozen snapshot. There is no re-resolution step to forget.
 * - CONFIGURED identity (`identity.configured`) is what configuration says
 *   will be used. TRANSPORT-REPORTED identity (`identity.transportReported`)
 *   is runtime evidence and is a separate field. When nothing has reported,
 *   it is explicitly `UNKNOWN` with a reason; it is never inferred from the
 *   requested model, the alias, or model prose.
 * - The snapshot hash covers the PIN (configured contract state) only.
 *   Transport-reported identity is excluded on purpose: recording evidence
 *   later must not change the pin, and changing the pin must not be
 *   disguised as a new observation. "Transport-reported identity" means
 *   BOTH evidence fields: `identity.transportReported` and the per-member
 *   `combinationMembers[].reported`. The PIN carries the permitted member
 *   SET (`selection.combinationMembers` plus each
 *   `combinationMembers[].memberModelId`) — which is configured state —
 *   but not the evidence recorded about those members. `pinBody()`
 *   normalizes every member to `{ memberModelId }`, so evidence attached
 *   later recomputes to the identical hash on ANY route kind.
 * - An unsupported reasoning level or a member outside the approved
 *   combination raises a concrete TransportError. Nothing is downgraded,
 *   renamed, or silently substituted.
 */

import { canonicalHash } from '../contracts/index.js';
import { TransportError } from './errors.js';
import { mapReasoningToParams } from './reasoning.js';
import type { ReasoningParamStyle } from './reasoning.js';
import {
  freezeCopy,
  type CouncilRouteSelection,
  type RouteCapabilitySnapshot,
  type RouteKind,
} from './selection.js';

/** Explicit schema identifier for this contract. */
export const ROUTE_SNAPSHOT_SCHEMA = 'wise-elders.route-snapshot/v1';

export const ROUTE_API_FAMILIES = [
  'openai_compatible',
  'anthropic_messages',
  'ollama_chat',
  'other',
] as const;
export type RouteApiFamily = (typeof ROUTE_API_FAMILIES)[number];

/** The literal used wherever identity is not established. */
export const UNKNOWN_ROUTE_IDENTITY = 'UNKNOWN' as const;

export type TransportIdentityUnknownReason =
  | 'probe_deferred'
  | 'not_probed'
  | 'provider_hid_identity';

/**
 * Transport evidence about one model. An unreported member is UNKNOWN
 * with a reason; it is never filled with the requested model.
 */
export type TransportReportedRouteIdentity =
  | {
      state: 'unknown';
      modelId: typeof UNKNOWN_ROUTE_IDENTITY;
      reason: TransportIdentityUnknownReason;
    }
  | {
      state: 'reported';
      modelId: string;
      providerRequestId: string | null;
    };

/** What configuration says the route will use. Never transport evidence. */
export interface ConfiguredRouteIdentity {
  providerSlug: string;
  /** Configured model id for a fixed route; null for a combination alias. */
  modelId: string | null;
  /** Combination alias, or the fixed route's requested model string. */
  alias: string | null;
  accountRef: string | null;
  configProfile: string;
}

export interface RouteCombinationMemberIdentity {
  memberModelId: string;
  reported: TransportReportedRouteIdentity;
}

export interface RouteSnapshotIdentity {
  configured: ConfiguredRouteIdentity;
  transportReported: TransportReportedRouteIdentity;
  /** One entry per PERMITTED member for a combination route; null otherwise. */
  combinationMembers: RouteCombinationMemberIdentity[] | null;
}

/** Host and configuration selection for this snapshot. */
export interface RouteHostSelection {
  baseUrl: string;
  /** Named config profile that produced this snapshot (frozen, not live). */
  configProfile: string;
  apiFamily: RouteApiFamily;
}

/** Rate and concurrency limits relevant to the pinned route. */
export interface RouteSnapshotLimits {
  requestsPerMinute: number | null;
  tokensPerMinute: number | null;
  maxConcurrency: number | null;
}

/**
 * Reasoning, split into the three questions the contract must never
 * conflate: what was requested, what the route SUPPORTS, and what was
 * actually APPLIED.
 */
export interface RouteSnapshotReasoning {
  requested: string | null;
  /** null means support is not established (UNKNOWN), never "none". */
  supported: string[] | null;
  /** null means nothing was applied; never a substituted level. */
  applied: string | null;
  limitation: string | null;
  paramStyle: ReasoningParamStyle;
}

export interface RouteSnapshotDraft {
  selection: CouncilRouteSelection;
  sessionId: string;
  /** Session owner identity that requested this route. */
  sessionOwner: string;
  host: RouteHostSelection;
  reasoning: RouteSnapshotReasoning;
  capabilityVersion: string;
  policySha256: string;
  limits: RouteSnapshotLimits;
  /** Optional initial transport evidence. Absent means UNKNOWN/deferred. */
  transportReported?: TransportReportedRouteIdentity;
  /** Caller-supplied so the snapshot hash is deterministic. */
  createdAt: string;
}

export interface CouncilRouteSnapshot {
  schema: typeof ROUTE_SNAPSHOT_SCHEMA;
  sessionId: string;
  sessionOwner: string;
  /** The pinned route selection (route id, account, alias, fallback...). */
  selection: CouncilRouteSelection;
  host: RouteHostSelection;
  identity: RouteSnapshotIdentity;
  reasoning: RouteSnapshotReasoning;
  capabilityVersion: string;
  policySha256: string;
  limits: RouteSnapshotLimits;
  createdAt: string;
  /** Canonical hash of the pin body. Stable across serialization. */
  snapshotSha256: string;
}

// ---------------------------------------------------------------------------
// Hash and freeze
// ---------------------------------------------------------------------------

/**
 * The pin body: everything except the hash itself and transport evidence.
 *
 * Transport-reported identity is excluded by design — BOTH the top-level
 * `transportReported` field and each member's `reported` evidence — so
 * evidence learned later cannot move the pin and a pin change cannot hide
 * behind evidence. The member SET is pinned: each entry is normalized to
 * `{ memberModelId }`, keeping the permitted membership (which is
 * configured contract state, already duplicated in
 * `selection.combinationMembers`) and dropping only the evidence.
 *
 * This normalization is what makes the law hold for combination routes:
 * without it a reported member's evidence entered the hash, so
 * `withTransportReportedIdentity()` returned a snapshot that failed its
 * own published hash while its equality check passed on the stale field.
 */
function pinBody(
  snapshot: Omit<CouncilRouteSnapshot, 'snapshotSha256'> & {
    snapshotSha256?: string;
  },
): Record<string, unknown> {
  const { snapshotSha256: _hash, identity, ...rest } = snapshot;
  return {
    ...rest,
    identity: {
      configured: identity.configured,
      combinationMembers:
        identity.combinationMembers === null
          ? null
          : identity.combinationMembers.map((member) => ({
              memberModelId: member.memberModelId,
            })),
    },
  };
}

/** Canonical SHA-256 over the pin body of a snapshot (or snapshot-shaped draft). */
export function computeRouteSnapshotSha256(
  snapshot: Omit<CouncilRouteSnapshot, 'snapshotSha256'>,
): string {
  return canonicalHash(pinBody(snapshot as CouncilRouteSnapshot));
}

/** Recompute and compare the published hash. */
export function verifyRouteSnapshotHash(snapshot: CouncilRouteSnapshot): boolean {
  return computeRouteSnapshotSha256(snapshot) === snapshot.snapshotSha256;
}

function unknownIdentity(
  reason: TransportIdentityUnknownReason,
): TransportReportedRouteIdentity {
  return { state: 'unknown', modelId: UNKNOWN_ROUTE_IDENTITY, reason };
}

function assertNonEmpty(value: string, field: string): void {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new TransportError(
      'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
      `Route snapshot field "${field}" must be a non-empty string.`,
    );
  }
}

function assertLimit(value: number | null, field: string): void {
  if (value === null) return;
  if (!Number.isFinite(value) || value < 0) {
    throw new TransportError(
      'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
      `Route snapshot limit "${field}" must be a finite non-negative number or null; received ${String(value)}.`,
    );
  }
}

function assertPolicyHash(value: string): void {
  if (!/^[0-9a-f]{64}$/.test(value)) {
    throw new TransportError(
      'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
      'Route snapshot "policySha256" must be a 64-character lowercase hex SHA-256.',
    );
  }
}

/**
 * Refuse a reasoning selection the route cannot honestly serve. Applied
 * must be exactly what was requested (or absent); the wire mapping must
 * already exist. Nothing is downgraded or renamed.
 */
function validateReasoning(reasoning: RouteSnapshotReasoning): void {
  const { requested, supported, applied, limitation, paramStyle } = reasoning;

  if (applied !== null && applied !== requested) {
    throw new TransportError(
      'TRANSPORT_REASONING_UNSUPPORTED',
      `Reasoning was requested as ${JSON.stringify(requested)} but would be applied as ${JSON.stringify(applied)}. Silent substitution is refused; a route that cannot honor the request must surface the limitation with applied null.`,
    );
  }

  if (requested !== null && supported !== null && !supported.includes(requested)) {
    throw new TransportError(
      'TRANSPORT_REASONING_UNSUPPORTED',
      `Reasoning level ${JSON.stringify(requested)} is not supported by this route (supported: ${supported.join(', ') || 'none'}). It was not applied, downgraded, or renamed; correct the route catalog.`,
    );
  }

  // Reuse the transport's own mapping table so a level that could not be
  // sent later cannot be frozen as applied now.
  mapReasoningToParams(
    {
      requested,
      applied,
      supported:
        supported === null
          ? null
          : requested === null
            ? false
            : supported.includes(requested),
      limitation,
    },
    paramStyle,
  );
}

function configuredIdentityOf(
  selection: CouncilRouteSelection,
  host: RouteHostSelection,
): ConfiguredRouteIdentity {
  return {
    providerSlug: selection.providerSlug,
    modelId: selection.routeKind === 'fixed_model' ? selection.requestedModelOrAlias : null,
    alias: selection.requestedModelOrAlias,
    accountRef: selection.providerAccountRef,
    configProfile: host.configProfile,
  };
}

/**
 * Freeze a draft into an immutable snapshot with its published hash.
 * The input is deep-copied: later mutation of the caller's objects (or of
 * any live default it came from) cannot alter the frozen snapshot.
 */
export function freezeRouteSnapshot(draft: RouteSnapshotDraft): CouncilRouteSnapshot {
  const { selection, host, reasoning, limits } = draft;

  assertNonEmpty(draft.sessionId, 'sessionId');
  assertNonEmpty(draft.sessionOwner, 'sessionOwner');
  assertNonEmpty(host.baseUrl, 'host.baseUrl');
  assertNonEmpty(host.configProfile, 'host.configProfile');
  assertNonEmpty(draft.capabilityVersion, 'capabilityVersion');
  assertNonEmpty(draft.createdAt, 'createdAt');
  assertPolicyHash(draft.policySha256);
  assertLimit(limits.requestsPerMinute, 'limits.requestsPerMinute');
  assertLimit(limits.tokensPerMinute, 'limits.tokensPerMinute');
  assertLimit(limits.maxConcurrency, 'limits.maxConcurrency');

  if (selection.routeKind === 'combination') {
    const members = selection.combinationMembers;
    if (selection.requestedModelOrAlias === null) {
      throw new TransportError(
        'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
        'A combination route snapshot requires a combination alias in requestedModelOrAlias.',
      );
    }
    if (members === null || members.length === 0) {
      throw new TransportError(
        'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
        'A combination route snapshot requires at least one permitted combination member. An empty member list is not permission to select any model.',
      );
    }
  } else if (selection.combinationMembers !== null) {
    throw new TransportError(
      'TRANSPORT_ROUTE_SNAPSHOT_INVALID',
      'A fixed-model route snapshot must not carry combination members.',
    );
  }

  validateReasoning(reasoning);

  const transportReported =
    draft.transportReported ?? unknownIdentity('probe_deferred');
  if (transportReported.state === 'reported') {
    assertNonEmpty(transportReported.modelId, 'transportReported.modelId');
  }

  const members = selection.combinationMembers;
  const identity: RouteSnapshotIdentity = {
    configured: configuredIdentityOf(selection, host),
    transportReported,
    combinationMembers:
      members === null
        ? null
        : members.map((memberModelId) => ({
            memberModelId,
            reported: unknownIdentity('probe_deferred'),
          })),
  };

  const body: Omit<CouncilRouteSnapshot, 'snapshotSha256'> = {
    schema: ROUTE_SNAPSHOT_SCHEMA,
    sessionId: draft.sessionId,
    sessionOwner: draft.sessionOwner,
    selection,
    host,
    identity,
    reasoning,
    capabilityVersion: draft.capabilityVersion,
    policySha256: draft.policySha256,
    limits,
    createdAt: draft.createdAt,
  };

  const frozenBody = freezeCopy(body);
  const snapshot: CouncilRouteSnapshot = freezeCopy({
    ...frozenBody,
    snapshotSha256: computeRouteSnapshotSha256(frozenBody),
  });
  return snapshot;
}

// ---------------------------------------------------------------------------
// Identity semantics for the deferred probe/transport (WER-006 onwards)
// ---------------------------------------------------------------------------

/**
 * Record transport-reported identity as a NEW snapshot with the SAME hash.
 * The pin is unchanged; only the evidence field moves. A report that
 * contradicts the configured fixed model is refused, and a combination
 * member outside the permitted list is refused by name.
 */
export function withTransportReportedIdentity(
  snapshot: CouncilRouteSnapshot,
  reported: TransportReportedRouteIdentity,
): CouncilRouteSnapshot {
  if (!verifyRouteSnapshotHash(snapshot)) {
    throw new TransportError(
      'TRANSPORT_ROUTE_MISMATCH',
      'Route snapshot hash does not match its pin body; refusing to attach transport evidence to a mutated snapshot.',
    );
  }
  if (reported.state === 'reported') {
    assertNonEmpty(reported.modelId, 'transportReported.modelId');
  }

  if (snapshot.selection.routeKind === 'fixed_model') {
    const configured = snapshot.identity.configured.modelId;
    if (reported.state === 'reported' && configured !== null && reported.modelId !== configured) {
      throw new TransportError(
        'TRANSPORT_ROUTE_MISMATCH',
        `Transport reported model ${JSON.stringify(reported.modelId)} but the frozen route is configured for ${JSON.stringify(configured)}. Refused, never relabelled.`,
      );
    }
  } else if (reported.state === 'reported') {
    requirePermittedCombinationMember(snapshot, reported.modelId);
  }

  const combinationMembers =
    snapshot.identity.combinationMembers === null
      ? null
      : snapshot.identity.combinationMembers.map((member) =>
          reported.state === 'reported' && member.memberModelId === reported.modelId
            ? { ...member, reported }
            : member,
        );

  const next: CouncilRouteSnapshot = freezeCopy({
    ...snapshot,
    identity: { ...snapshot.identity, transportReported: reported, combinationMembers },
  });
  // The stamp is deliberately carried over, not recomputed: evidence never
  // republishes a pin. Assert the stamp against BOTH the previous pin and a
  // fresh recomputation. Comparing the two stamps alone would pass on the
  // stale published field while the returned snapshot failed its own hash —
  // that was the defect this recompute closes.
  if (next.snapshotSha256 !== snapshot.snapshotSha256) {
    throw new TransportError(
      'TRANSPORT_ROUTE_MISMATCH',
      'Attaching transport evidence changed the route pin hash; the pin body and evidence fields are not separated.',
    );
  }
  if (computeRouteSnapshotSha256(next) !== next.snapshotSha256) {
    throw new TransportError(
      'TRANSPORT_ROUTE_MISMATCH',
      'Route snapshot does not satisfy its own published hash after transport evidence was attached; the pin body still covers an evidence field.',
    );
  }
  return next;
}

/**
 * Refuse a model that is not a permitted member of this snapshot's
 * combination. A combination is never permission to add models.
 */
export function requirePermittedCombinationMember(
  snapshot: CouncilRouteSnapshot,
  modelId: string,
): void {
  const members = snapshot.selection.combinationMembers;
  if (members === null) {
    throw new TransportError(
      'TRANSPORT_COMBINATION_MEMBER_UNKNOWN',
      'This frozen route is a fixed-model route; it has no permitted combination members.',
    );
  }
  if (!members.includes(modelId)) {
    throw new TransportError(
      'TRANSPORT_COMBINATION_MEMBER_UNKNOWN',
      `Model ${JSON.stringify(modelId)} is not a permitted member of combination ${JSON.stringify(snapshot.selection.requestedModelOrAlias)} (permitted: ${members.join(', ')}). Refused, never substituted.`,
    );
  }
}

/**
 * The declared support the route carries. `null` means UNKNOWN (not
 * established), not "no support".
 */
export function supportedReasoningLevels(
  snapshot: CouncilRouteSnapshot,
): string[] | null {
  return snapshot.reasoning.supported;
}

/** Capability snapshot carried by the pinned selection, for consumers. */
export function routeSnapshotCapabilities(
  snapshot: CouncilRouteSnapshot,
): RouteCapabilitySnapshot {
  return snapshot.selection.capabilitySnapshot;
}

/** The route kind, re-exported for consumers that branch on it. */
export type RouteSnapshotKind = RouteKind;
