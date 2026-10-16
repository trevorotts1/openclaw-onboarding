/**
 * @blackceo/wise-elders-core package surface (CWE-004 foundation;
 * integration completed by CWE-050).
 *
 * Re-exports the CWE-003 canonical contracts and the full portable
 * core: injected host ports, the standalone local host, the
 * deliberation engine, budget and lease implementations, the local
 * SQLite store, the blackceo-council CLI dispatcher, and every
 * composed service family (authorization, budgets, persistence,
 * context, intake, scoring, protocol, sources, reports). The bridges
 * family is consumed by path imports only (see the note at the foot
 * of this file). This completes the barrel/exports alignment
 * CWE-007's integrator flag deferred to integration: the
 * authorization composition is part of the package surface, and path
 * imports keep working alongside it.
 *
 * Importing this package has no side effects: it opens no database,
 * starts no job, and performs no provider request. Hosts compose a
 * CouncilHost explicitly (createLocalHost for standalone mode) and hand
 * it to CouncilEngine or the CLI dispatcher.
 */
export * from './contracts/index.js';
export * from './cli/errors.js';
export * from './cli/host-ports.js';
export * from './cli/paths.js';
export * from './cli/budget.js';
export * from './cli/leases.js';
export * from './cli/local-store.js';
export * from './cli/local-host.js';
export * from './cli/engine.js';
export * from './cli/fixture-transport.js';
export * from './cli/dispatcher.js';
export * from './cli/authorization.js';
export * from './cli/report-export.js';
export * from './queue/index.js';
export * from './providers/errors.js';
export * from './providers/selection.js';
export * from './providers/url-policy.js';
export * from './providers/reasoning.js';
export * from './providers/diagnostics.js';
export * from './providers/http-core.js';
export * from './providers/compatible.js';
export * from './providers/ollama.js';
// The authorization family is exported through the package's
// "./authorization" subpath instead of a root star-export: CWE-007's
// scope module declares route-selection types that providers/
// selection.ts also owns (parallel declarations across accepted
// units), and a root star-export would shadow one with the other.
// The CWE-049 composition (run-grants, admission) rides the same
// subpath; path imports keep working unchanged. The budgets family
// rides "./budgets" for the same reason (budgets/route-snapshot.ts
// declares the pinned route-selection vocabulary).
export * from './persistence/index.js';
export * from './context/index.js';
export * from './intake/index.js';
export * from './scoring/index.js';
export * from './protocol/index.js';
export * from './sources/index.js';
export * from './reports/index.js';
// SessionAccessTarget is declared by both the authorization scope
// module and the context types (the same shape, owned by CWE-007's
// scope rules); the explicit re-export pins the authorization one as
// the package-level name. RouteIdentityLevel is declared by both
// providers/selection.ts (CWE-009, the route owner) and intake/types
// (the same union); the explicit re-export pins the route owner's.
// CONSULT_SYSTEM is the Section 14 consult text whose single source
// is cli/engine.ts after the CWE-050 prompt consolidation (protocol/
// ratification.ts re-exports the same constant); the explicit
// re-export pins the single source.
export type { SessionAccessTarget } from './authorization/index.js';
export type { RouteIdentityLevel } from './providers/selection.js';
export { CONSULT_SYSTEM } from './cli/engine.js';
// The bridges family (CWE-010) has no package subpath and no barrel:
// CWE-010's harness-isolation test pins src/bridges/ to exactly its
// four modules (host-bridge, openclaw, claude-nine, parity) and
// forbids either bridge's import graph from reaching the other, so a
// combined barrel would break an accepted isolation invariant.
// Hosts import the bridge they run by path (src/bridges/openclaw.js
// or src/bridges/claude-nine.js), which keeps the isolation real.
