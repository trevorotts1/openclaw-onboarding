/**
 * CWE-023 route snapshot pinning (directive Sections 10, 13.1, 13.2).
 *
 * The brief revision records the client's selected route snapshot in
 * CWE-008 catalog semantics: a route reference from the client's own
 * configured catalog, with its identity level stated honestly
 * (configured / transport_probed / reported_identity /
 * resolved_identity_verified / quality_qualified). The snapshot is
 * pinned at choice time with the canonical hash of the catalog entry
 * it came from. A later catalog change never moves a pinned snapshot:
 * drift is detected and reported, and changing the route means a new
 * explicit choice before freeze, never a silent replacement.
 *
 * The catalog itself is a port. CWE-008 owns the registry and
 * selection policy (CC providers plus the ONB registry binding lands
 * at integration); hosts supply the client's configured routes here.
 */
import {
  canonicalHash,
  type ModelPolicy,
} from '../contracts/index.js';
import {
  IntakeError,
  type RouteCatalogEntry,
  type RouteChoice,
  type RouteSnapshot,
} from './types.js';

export type {
  RouteCatalogEntry,
  RouteIdentityLevel,
  RouteSnapshot,
} from './types.js';

/** The CWE-008 catalog as intake consumes it (explicit-route-catalog). */
export interface RouteCatalogPort {
  listSelectableRoutes(): readonly RouteCatalogEntry[];
  /** The client's configured default route, or null when none exists. */
  configuredDefault(): RouteCatalogEntry | null;
}

export function pinRouteSnapshot(
  entry: RouteCatalogEntry,
  selectionSource: RouteSnapshot['selection_source'],
  pinnedAt: string,
): RouteSnapshot {
  return {
    route_id: entry.route_id,
    requested_model_id: entry.requested_model_id,
    reasoning_preference: entry.reasoning_preference,
    fallback_policy: entry.fallback_policy,
    identity_level: entry.identity_level,
    selection_source: selectionSource,
    catalog_entry_sha256: canonicalHash({ ...entry }),
    pinned_at: pinnedAt,
  };
}

/**
 * Resolve a route choice against the catalog and pin the snapshot.
 * An explicit choice must name a route the catalog actually offers;
 * an inherited choice uses the configured default. Either way the
 * result is displayed before start (Section 13.1) and pinned.
 */
export function resolveRouteSnapshot(
  catalog: RouteCatalogPort,
  choice: RouteChoice,
  pinnedAt: string,
): RouteSnapshot {
  if (choice.kind === 'explicit') {
    const entry = catalog
      .listSelectableRoutes()
      .find((e) => e.route_id === choice.route_id);
    if (!entry) {
      throw new IntakeError(
        'INTAKE_ROUTE_NOT_FOUND',
        'The selected route is not in the client-configured catalog. No route was substituted.',
        { route_id: choice.route_id },
      );
    }
    return pinRouteSnapshot(entry, 'explicit', pinnedAt);
  }
  const fallback = catalog.configuredDefault();
  if (!fallback) {
    throw new IntakeError(
      'INTAKE_ROUTE_NOT_FOUND',
      'No configured default route exists to inherit. The client must choose a route explicitly.',
    );
  }
  return pinRouteSnapshot(fallback, 'client_default', pinnedAt);
}

/**
 * Drift check for display and verification: has the catalog entry the
 * snapshot was pinned from changed since? The snapshot itself never
 * moves; this only reports that the world did.
 */
export function routeSnapshotDrift(
  snapshot: RouteSnapshot,
  currentEntry: RouteCatalogEntry | null,
): { readonly drifted: boolean; readonly reason: string | null } {
  if (currentEntry === null) {
    return {
      drifted: true,
      reason: 'The pinned route no longer appears in the catalog. The frozen snapshot stands; a new choice requires a new revision.',
    };
  }
  if (canonicalHash({ ...currentEntry }) !== snapshot.catalog_entry_sha256) {
    return {
      drifted: true,
      reason: 'The catalog entry changed after pinning. The frozen snapshot stands; a new choice requires a new revision.',
    };
  }
  return { drifted: false, reason: null };
}

/** The SessionSpec model policy for the frozen spec, from the snapshot. */
export function modelPolicyFromSnapshot(snapshot: RouteSnapshot): ModelPolicy {
  return {
    selection: snapshot.selection_source,
    route_id: snapshot.route_id,
    requested_model_id: snapshot.requested_model_id,
    reasoning_preference: snapshot.reasoning_preference,
    fallback_policy: snapshot.fallback_policy,
  };
}
