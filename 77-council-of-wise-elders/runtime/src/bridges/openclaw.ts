/**
 * OpenClaw host bridge (CWE-010; directive Sections 13, 14, 25).
 *
 * Composes the portable council core under the OpenClaw host: the same
 * CWE-004 host ports, the same shared local store and data profile, and
 * a guarded transport per selected route (host-bridge.ts). The bridge
 * resolves the client's selected route inside the OpenClaw harness only.
 *
 * select_model.py is the OpenClaw host's own model machinery. It is
 * READ-ONLY for this build: the bridge never modifies it and never
 * silently rides it. CWE-001 recon read it in full (1,120 lines) and
 * mapped its silent-replacement points; the binding lock (CWE-002,
 * Part 4) carries that map. Every one of those points, if the host
 * engages it for a council request, produces a resolution attempt that
 * this bridge runs through the explicit-selection guard: under
 * fallback_policy none the substitution is REFUSED and recorded as a
 * substitution_refused event; under client_approved_only it proceeds
 * only with a client approval record and is recorded as a route-change
 * event with a new route revision. There is no path around the guard.
 *
 * Expired host OAuth (T035): this bridge never scrapes cookies or
 * tokens and never fabricates API entitlement from a subscription.
 * When the host reports an expired credential, the supported path is
 * the host's own renewal flow; the bridge surfaces the failure through
 * the normal transport error path and the council refuses to spend.
 */

import { invalidInput } from '../cli/errors.js';
import type { TransportRequest } from '../cli/host-ports.js';
import {
  composeBridgeHost,
  type BridgeHostOptions,
  type BridgeInstance,
  type CouncilRouteSelection,
  type HostResolutionAttempt,
  type HostResolutionSource,
} from './host-bridge.js';

// ---------------------------------------------------------------------------
// The select_model.py replacement-point map (CWE-001 recon, CWE-002
// binding lock Part 4). Each point names the host surface that can
// replace a selected model and the resolution source its attempt carries
// into the guard. openclaw.json fallback arrays and the fleet
// sovereignty cascade act outside the file and are mapped too: the
// bridge guards behavior, not one source file.
// ---------------------------------------------------------------------------

export interface OpenClawReplacementPoint {
  id: string;
  hostSurface: string;
  source: HostResolutionSource;
  description: string;
}

export const OPENCLAW_REPLACEMENT_POINTS: readonly OpenClawReplacementPoint[] = [
  {
    id: 'forbidden-prefix-filter',
    hostSurface: 'shared-utils/select_model.py FORBIDDEN_PREFIXES',
    source: 'cascade',
    description:
      'Models under a forbidden prefix are silently removed before selection, so a council-selected model can vanish from the candidate set without any event.',
  },
  {
    id: 'purpose-tier-cascade',
    hostSurface: 'shared-utils/select_model.py purpose-tier chains',
    source: 'cascade',
    description:
      'The purpose-tier cascade picks the first available model in its chain, which can be a different model than the client selected for the council.',
  },
  {
    id: 'cheapest-match-substitution',
    hostSurface: 'shared-utils/select_model.py cheapest-match selection',
    source: 'cascade',
    description:
      'Cheapest-match selection substitutes a lower-cost model that merely matches the request class, replacing the selected model on price alone.',
  },
  {
    id: 'department-default-resolution',
    hostSurface: 'shared-utils/select_model.py resolve_dept_default_model',
    source: 'sovereign_default',
    description:
      'When no task model resolves, the department default is substituted. A council session has a frozen selected route; a department default is never that route.',
  },
  {
    id: 'sovereignty-last-resort',
    hostSurface: 'fleet sovereignty cascade final rung (AGENTS.md N35)',
    source: 'cascade',
    description:
      'The fleet cascade final rung fires a universal last-resort model when earlier tiers fail. For a council selection that is a substitution and is guarded like any other.',
  },
  {
    id: 'agent-model-fallback-array',
    hostSurface: 'openclaw.json agents.list[].model.fallbacks',
    source: 'fallback',
    description:
      'Agent model objects carry fallback arrays the host consults when the primary fails. Council sessions default to fallback_policy none, so a fallback entry is never permission to proceed silently.',
  },
  {
    id: 'runtime-model-reconcile',
    hostSurface: 'host runtime model reconciliation',
    source: 'runtime_reconcile',
    description:
      'A live runtime model can overwrite the recorded model for work in flight. For a council selection the recorded selected route governs; a reconcile to a different model is a substitution attempt.',
  },
] as const;

export function replacementPointById(
  id: string,
): OpenClawReplacementPoint | null {
  return OPENCLAW_REPLACEMENT_POINTS.find((p) => p.id === id) ?? null;
}

// ---------------------------------------------------------------------------
// The OpenClaw host resolver port. The host reports, inside its own
// harness, what it resolved for a council request. The bridge converts
// the report into a canonical resolution attempt and the shared guard
// decides. A resolver that engages a replacement point names it via
// viaReplacementPoint so the attempt carries the right source and the
// journal shows exactly which host surface tried to substitute.
// ---------------------------------------------------------------------------

export interface OpenClawResolutionReport {
  /** Model the host used or tried to use, when exposed. */
  attemptedModelId: string | null;
  /** Structured transport/provider-reported identity, when exposed. */
  reportedModelId?: string | null;
  /** Identity claimed in model prose. Recorded as ignored, never used. */
  proseClaimedModelId?: string | null;
  /** Client approval for a fallback change, when one exists. */
  approval?: HostResolutionAttempt['approval'];
  /** Replacement point the host engaged, by map id, when it engaged one. */
  viaReplacementPoint?: string | null;
}

export interface OpenClawHostResolver {
  reportResolution(
    selection: CouncilRouteSelection,
    request: TransportRequest,
  ): OpenClawResolutionReport | Promise<OpenClawResolutionReport>;
}

export function openClawAttemptFromReport(
  report: OpenClawResolutionReport,
): HostResolutionAttempt {
  let source: HostResolutionSource = 'explicit_route';
  if (report.viaReplacementPoint) {
    const point = replacementPointById(report.viaReplacementPoint);
    if (!point) {
      throw invalidInput(
        `Unknown OpenClaw replacement point "${report.viaReplacementPoint}". Refusing to guess which host surface engaged; name a mapped replacement point or none.`,
      );
    }
    source = point.source;
  }
  return {
    source,
    attemptedModelId: report.attemptedModelId,
    reportedModelId: report.reportedModelId ?? null,
    proseClaimedModelId: report.proseClaimedModelId ?? null,
    approval: report.approval ?? null,
  };
}

/**
 * The pinned-route resolver for an installation whose OpenClaw config
 * pins the council route as the executing model: the host reports the
 * selected model unchanged and no replacement point is engaged. This is
 * the only resolver this unit ships; wiring a live host probe belongs
 * to the installation packaging (CWE-039/CWE-040) behind this same port.
 */
export class PinnedOpenClawResolver implements OpenClawHostResolver {
  reportResolution(
    selection: CouncilRouteSelection,
  ): OpenClawResolutionReport {
    return {
      attemptedModelId: selection.requestedModelOrAlias,
      reportedModelId: null,
    };
  }
}

// ---------------------------------------------------------------------------
// The bridge factory. Bindings supplied by the caller carry delegates
// only; the resolution guard is wired here from the bridge's resolver,
// so no caller can register an unguarded OpenClaw transport for a
// council route through this bridge.
// ---------------------------------------------------------------------------

export interface OpenClawBridgeOptions extends BridgeHostOptions {
  resolver?: OpenClawHostResolver;
}

export function createOpenClawBridge(
  options: OpenClawBridgeOptions = {},
): BridgeInstance {
  const resolver = options.resolver ?? new PinnedOpenClawResolver();
  const bindings = (options.bindings ?? []).map((binding) => ({
    ...binding,
    reportAttempt: async (
      selection: CouncilRouteSelection,
      request: TransportRequest,
    ) =>
      openClawAttemptFromReport(
        await resolver.reportResolution(selection, request),
      ),
  }));
  return composeBridgeHost('openclaw', { ...options, bindings });
}
