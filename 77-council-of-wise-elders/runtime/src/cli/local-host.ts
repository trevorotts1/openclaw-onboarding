/**
 * Standalone host composition (CWE-004; authorization composed by
 * CWE-050 from CWE-049's service; live route composition repaired by
 * RP-046-1 for DEFECT-046-A).
 *
 * Assembles the real local host for the portable core: SQLite store in
 * the per-user data directory (never inside the skill tree), in-process
 * budget ledger and lease provider, a transport registry, an evidence
 * provider that serves the frozen brief manifest and reports "no pack
 * installed" honestly, a secrets probe that never accepts or returns
 * values, and the run authorization provider composed from CWE-049's
 * standalone service (withRunAuthorization over
 * createStandaloneRunAuthorization): grants approved through the
 * `authorization` CLI commands resolve here, in the SAME provisioned
 * installation namespace the sessions are created under (localScope
 * with a data directory). Unapproved or unknown grant references still
 * resolve to null, so runs refuse with RUN_AUTHORIZATION_REQUIRED
 * rather than spending on a flag or a file.
 *
 * Live routes (RP-046-1): the registry additionally composes a real
 * transport for every route the client's EXISTING configuration
 * describes on this machine, discovered read-only by
 * route-discovery.ts (Section 25.2 step 7: discover the client's
 * existing route configuration, store references not credentials).
 * Harness config roots compose the CWE-010 bridge guard over a real
 * subprocess host-call delegate (Section 13.4 adapter 3);
 * OpenAI-compatible endpoints in the client's OpenClaw provider
 * configuration compose the CWE-009 compatible transport (adapter 1).
 * Nothing is invented: a route that is not configured, or whose
 * configuration cannot be bound unambiguously (no harness executable,
 * no unambiguous configured model, no credential present), is
 * discovered but NOT composed, is reported honestly by `models` and
 * the doctor, and dispatch on it keeps refusing with
 * COUNCIL_ROUTE_UNAVAILABLE. Explicit transports supplied by the
 * caller always win over discovered ones for the same route id. The
 * result is a core that runs fully offline and fails closed with
 * typed errors wherever a production dependency is not yet present.
 */

import { randomUUID } from 'node:crypto';
import type {
  CouncilEvent,
  RunGrant,
  ScopeFields,
  SeatId,
} from '../contracts/index.js';
import type {
  CouncilHost,
  CouncilStore,
  EvidenceProvider,
  ModelTransport,
  TransportRegistry,
} from './host-ports.js';
import {
  createStandaloneRunAuthorization,
  resolveStandaloneInstallation,
  standaloneScope,
  withRunAuthorization,
} from './authorization.js';
import {
  GuardedTransport,
  RouteResolutionJournal,
  trustedScopeFromScopeFields,
  type CouncilRouteSelection as BridgeRouteSelection,
  type HostResolutionAttempt,
} from '../bridges/host-bridge.js';
import { CompatibleHttpTransport } from '../providers/compatible.js';
import type { CouncilRouteSelection as ProviderRouteSelection } from '../providers/selection.js';
import { InProcessBudgetLedger } from './budget.js';
import { SubprocessHostCallTransport } from './host-call-transport.js';
import { InProcessLeaseProvider } from './leases.js';
import { LocalSqliteStore } from './local-store.js';
import { resolveDataDir } from './paths.js';
import {
  discoverConfiguredRoutes,
  resolveDiscoveredCredential,
  routeDiscoveryInfo,
  type DiscoveredRoute,
  type RouteDiscoveryInfo,
} from './route-discovery.js';

export class MapTransportRegistry implements TransportRegistry {
  private readonly routes = new Map<string, ModelTransport>();

  register(routeId: string, transport: ModelTransport): void {
    this.routes.set(routeId, transport);
  }

  resolve(routeId: string): ModelTransport | null {
    return this.routes.get(routeId) ?? null;
  }

  listRoutes(): string[] {
    return [...this.routes.keys()];
  }
}

export interface LocalHostOptions {
  dataDir?: string;
  skillRoot?: string;
  transports?: Array<{ routeId: string; transport: ModelTransport }>;
  /**
   * RP-046-1: compose real transports for the client's configured
   * routes discovered read-only on this machine. Default true. Set
   * false to compose the bare foundation host (no discovered routes).
   */
  discoverRoutes?: boolean;
  /** Home directory route discovery reads under. Default: the OS home. */
  homeDir?: string;
  /** Environment route discovery and credential presence read. Default: process.env. */
  env?: NodeJS.ProcessEnv;
  /** Verified deadline for harness host calls, when one is configured. */
  hostCallTimeoutMs?: number;
}

export interface LocalHost {
  host: CouncilHost;
  dataDir: string;
  store: CouncilStore;
  /** Secret-free discovery report for this composition (RP-046-1). */
  routeDiscovery?: RouteDiscoveryInfo[];
}

/**
 * Compose the real adapter transport for one discovered route
 * (RP-046-1). Harness routes get the CWE-010 guard over the subprocess
 * host-call delegate (adapter 3); compatible routes get the CWE-009
 * transport pinned to the configuration's own model (adapter 1). A
 * construction failure (for example an endpoint the URL policy
 * refuses) leaves the route uncomposed and is reported, never hidden.
 */
function composeDiscoveredTransport(
  route: DiscoveredRoute,
  options: {
    scope: ScopeFields;
    clock: CouncilHost['clock'];
    env: NodeJS.ProcessEnv;
    hostCallTimeoutMs?: number;
  },
): ModelTransport {
  const createdAt = options.clock.nowUtc();
  const capabilitySnapshot = {
    contextWindowTokens: null,
    maxOutputTokens: null,
    capabilities: ['text'],
    supportedReasoningLevels: null,
  };
  const reasoning = { requested: null, applied: null, supported: null, limitation: null };
  if (route.kind === 'harness') {
    const selection: BridgeRouteSelection = {
      schema: 'wise-elders.route-selection/v1',
      selectionSource: 'client_default',
      routeId: route.routeId,
      routeRevision: 1,
      routeKind: 'fixed_model',
      providerSlug: route.providerSlug,
      requestedRoute: route.routeId,
      // The harness owns its configured model; the council pins the
      // ROUTE and prescribes no model to the harness (adapter 3). The
      // pinned resolver reports the attempt with no named model, and
      // the guard accepts it under the hidden-identity statement.
      requestedModelOrAlias: null,
      combinationMembers: null,
      reasoning,
      fallbackPolicy: 'none',
      providerAccountRef: null,
      capabilitySnapshot,
      credential: { state: 'not_required', envVar: null, source: null, checked: [] },
      identityLevel: 'configured',
      scope: trustedScopeFromScopeFields(options.scope),
      createdAt,
    };
    return new GuardedTransport({
      harness: 'claude-nine',
      selection,
      delegate: new SubprocessHostCallTransport({
        executable: route.harness!.executable!,
        configDir: route.harness!.configDir,
        timeoutMs: options.hostCallTimeoutMs,
      }),
      // The pinned-route resolution report, with exactly the
      // semantics of the CWE-010 bridge's pinned resolver: the
      // harness runs the selected route exactly as selected, and for
      // a route that names no model the attempt reports none, so the
      // guard accepts it under the hidden-identity statement. (Built
      // here rather than imported from the Claude-Nine bridge module
      // so neither bridge's import graph reaches the other bridge:
      // the harness isolation law in bridges/host-bridge.ts.)
      reportAttempt: async (sel): Promise<HostResolutionAttempt> => ({
        source: 'explicit_route',
        attemptedModelId:
          sel.routeKind === 'combination' ? null : sel.requestedModelOrAlias,
        reportedModelId: null,
        proseClaimedModelId: null,
        approval: null,
      }),
      journal: new RouteResolutionJournal(),
      clock: options.clock,
    });
  }
  const compatible = route.compatible!;
  const selection: ProviderRouteSelection = {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: 'client_default',
    routeId: route.routeId,
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: route.providerSlug,
    requestedRoute: route.routeId,
    requestedModelOrAlias: compatible.modelId,
    combinationMembers: null,
    reasoning,
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot,
    credential: {
      state: compatible.credential.state,
      envVar: compatible.credential.envVar,
      source: compatible.credential.source,
      checked: ['openclaw.json', 'process.env'],
    },
    identityLevel: 'configured',
    scope: trustedScopeFromScopeFields(options.scope),
    createdAt,
  };
  return new CompatibleHttpTransport({
    selection,
    baseUrl: compatible.baseUrl,
    credentialResolver:
      compatible.credential.state === 'present'
        ? async () => resolveDiscoveredCredential(route, options.env)
        : undefined,
  });
}

export function createLocalHost(options: LocalHostOptions = {}): LocalHost {
  const dataDir = resolveDataDir({
    override: options.dataDir ?? null,
    skillRoot: options.skillRoot ?? null,
  });
  const store = new LocalSqliteStore(dataDir);
  const registry = new MapTransportRegistry();
  for (const entry of options.transports ?? []) {
    registry.register(entry.routeId, entry.transport);
  }
  const clock: CouncilHost['clock'] = {
    nowUtc: () => new Date().toISOString(),
  };
  // RP-046-1 live route composition: bind the real adapters to the
  // client's existing configured routes, discovered read-only. A
  // discovered route whose configuration cannot be bound stays
  // uncomposed and is reported with its reason; a composition failure
  // is reported the same way. Neither is ever silently replaced by
  // another route.
  const discoveryEnv = options.env ?? process.env;
  const discovered =
    options.discoverRoutes === false
      ? []
      : discoverConfiguredRoutes({ homeDir: options.homeDir, env: discoveryEnv });
  const routeDiscovery: RouteDiscoveryInfo[] = [];
  const composedDiscovered = new Map<string, DiscoveredRoute>();
  for (const route of discovered) {
    if (registry.resolve(route.routeId) !== null) {
      // An explicit caller-supplied transport already serves this
      // route id; the discovered binding never overrides it.
      routeDiscovery.push(routeDiscoveryInfo(route, true));
      continue;
    }
    if (!route.composable) {
      routeDiscovery.push(routeDiscoveryInfo(route, false));
      continue;
    }
    try {
      registry.register(
        route.routeId,
        composeDiscoveredTransport(route, {
          scope: localScope(dataDir),
          clock,
          env: discoveryEnv,
          hostCallTimeoutMs: options.hostCallTimeoutMs,
        }),
      );
      composedDiscovered.set(route.routeId, route);
      routeDiscovery.push(routeDiscoveryInfo(route, true));
    } catch (err) {
      routeDiscovery.push({
        ...routeDiscoveryInfo(route, false),
        not_composed_reason: `transport composition failed: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  }
  const evidence: EvidenceProvider = {
    async loadEvidenceManifest(sessionId: string) {
      const session = await store.getSession(sessionId);
      return session?.brief.evidence_manifest ?? [];
    },
    async loadSeatPack(_seatId: SeatId) {
      // Seat packs are installed content (CWE-011 onward). Until a pack
      // resolver is composed, the honest answer is "no pack installed";
      // the engine then grounds prompts in the seat's frozen relevance
      // weight and Section 7 owned question only.
      return null;
    },
  };
  const host: CouncilHost = {
    store,
    transportRegistry: registry,
    evidence,
    secrets: {
      // Presence probe only: it never receives or returns a value
      // (Section 13.7). RP-046-1: for a composed discovered route the
      // answer comes from the discovered configuration itself (a
      // harness route's credential lives inside the harness; a
      // compatible route answers from its recorded presence state).
      credentialPresent: async (routeId: string) => {
        const route = composedDiscovered.get(routeId);
        if (!route) return false;
        if (route.kind === 'harness') return true;
        const state = route.compatible?.credential.state;
        return state === 'present' || state === 'not_required';
      },
    },
    budget: new InProcessBudgetLedger(),
    capacity: new InProcessLeaseProvider(),
    events: {
      async publish(event: Omit<CouncilEvent, 'sequence'>): Promise<CouncilEvent> {
        return store.appendEvent(event);
      },
    },
    clock,
    ids: {
      newId: () => randomUUID(),
    },
    authorize: {
      // Placeholder replaced below by CWE-049's composed provider
      // (withRunAuthorization); kept as the fail-closed default if the
      // composition is ever bypassed.
      async resolveRunGrant(
        _grantRef: string,
        _sessionId: string,
      ): Promise<RunGrant | null> {
        return null;
      },
    },
  };
  // CWE-050 composition (CWE-049 build report, standalone composition
  // list item 2): the host's grant resolution IS the standalone run
  // authorization service over the authorization store in the same
  // data directory, under the provisioned installation namespace.
  const authorization = createStandaloneRunAuthorization({ dataDir });
  const composedHost = withRunAuthorization(host, authorization);
  return { host: composedHost, dataDir, store, routeDiscovery };
}

/**
 * Scope for standalone single-user runs (Section 5.4). CWE-050
 * alignment: with a data directory, the scope IS the provisioned
 * standalone installation (resolveStandaloneInstallation +
 * standaloneScope), so sessions, envelopes, and grants share ONE
 * namespace: the authorization profile's UUID installation. The
 * no-argument form keeps the fixed foundation strings for callers
 * that compose no data directory (for example bridge defaults in
 * tests); production CLI paths always pass the data directory.
 */
export function localScope(dataDir?: string): ScopeFields {
  if (dataDir) {
    return standaloneScope(resolveStandaloneInstallation(dataDir));
  }
  return {
    installation_id: 'local-installation',
    tenant_id: 'local-tenant',
    company_id: 'local-company',
    owner_subject: 'local-owner',
  };
}
