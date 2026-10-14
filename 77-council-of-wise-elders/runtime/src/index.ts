/**
 * @blackceo/wise-elders-core package surface (CWE-004 foundation).
 *
 * Re-exports the CWE-003 canonical contracts and the CWE-004 portable
 * core foundation: injected host ports, the standalone local host, the
 * deliberation engine, budget and lease implementations, the local
 * SQLite store, and the blackceo-council CLI dispatcher.
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
export * from './queue/index.js';
export * from './providers/errors.js';
export * from './providers/selection.js';
export * from './providers/url-policy.js';
export * from './providers/reasoning.js';
export * from './providers/diagnostics.js';
export * from './providers/http-core.js';
export * from './providers/compatible.js';
export * from './providers/ollama.js';
