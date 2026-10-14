/**
 * Standalone host composition (CWE-004).
 *
 * Assembles the real local host for the portable core: SQLite store in
 * the per-user data directory (never inside the skill tree), in-process
 * budget ledger and lease provider, a transport registry that starts
 * EMPTY (no live route is wired by this unit; live transports are
 * CWE-009 and CWE-010, and the registry never invents one), an evidence
 * provider that serves the frozen brief manifest and reports "no pack
 * installed" honestly, a secrets probe that never accepts or returns
 * values, and an authorization provider that resolves nothing until
 * CWE-049's service is composed. The result is a core that runs fully
 * offline and fails closed with typed errors wherever a production
 * dependency is not yet present.
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
      // CWE-049 owns the grant store. Until it is composed, no grant
      // resolves, so runs refuse with RUN_AUTHORIZATION_REQUIRED rather
      // than spending on a flag or a file.
      async resolveRunGrant(
        _grantRef: string,
        _sessionId: string,
      ): Promise<RunGrant | null> {
        return null;
      },
    },
  };
  return { host, dataDir, store };
}

/** Fixed scope for standalone single-user runs (Section 5.4). */
export function localScope(): ScopeFields {
  return {
    installation_id: 'local-installation',
    tenant_id: 'local-tenant',
    company_id: 'local-company',
    owner_subject: 'local-owner',
  };
}
