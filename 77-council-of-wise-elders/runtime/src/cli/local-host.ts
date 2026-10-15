/**
 * Standalone host composition (CWE-004; authorization composed by
 * CWE-050 from CWE-049's service).
 *
 * Assembles the real local host for the portable core: SQLite store in
 * the per-user data directory (never inside the skill tree), in-process
 * budget ledger and lease provider, a transport registry that starts
 * EMPTY (no live route is wired by this unit; live transports are
 * CWE-009 and CWE-010, and the registry never invents one), an evidence
 * provider that serves the frozen brief manifest and reports "no pack
 * installed" honestly, a secrets probe that never accepts or returns
 * values, and the run authorization provider composed from CWE-049's
 * standalone service (withRunAuthorization over
 * createStandaloneRunAuthorization): grants approved through the
 * `authorization` CLI commands resolve here, in the SAME provisioned
 * installation namespace the sessions are created under (localScope
 * with a data directory). Unapproved or unknown grant references still
 * resolve to null, so runs refuse with RUN_AUTHORIZATION_REQUIRED
 * rather than spending on a flag or a file. The result is a core that
 * runs fully offline and fails closed with typed errors wherever a
 * production dependency is not yet present.
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
import { InProcessBudgetLedger } from './budget.js';
import { InProcessLeaseProvider } from './leases.js';
import { LocalSqliteStore } from './local-store.js';
import { resolveDataDir } from './paths.js';

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
}

export interface LocalHost {
  host: CouncilHost;
  dataDir: string;
  store: CouncilStore;
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
      // No credential store is composed in the standalone foundation.
      // The probe never receives or returns a value (Section 13.7).
      credentialPresent: async () => false,
    },
    budget: new InProcessBudgetLedger(),
    capacity: new InProcessLeaseProvider(),
    events: {
      async publish(event: Omit<CouncilEvent, 'sequence'>): Promise<CouncilEvent> {
        return store.appendEvent(event);
      },
    },
    clock: {
      nowUtc: () => new Date().toISOString(),
    },
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
  return { host: composedHost, dataDir, store };
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
