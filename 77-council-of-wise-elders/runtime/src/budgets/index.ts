/**
 * Shared budget reservation service barrel (CWE-028).
 *
 * The single shared budget service (service.ts), the pinned CWE-008
 * route snapshot shapes it charges against (route-snapshot.ts), and
 * its typed errors (errors.ts). Runtime capacity admission lives at
 * src/queue/capacity.ts, the path Section 34.3 assigns to CWE-028.
 */
export * from './errors.js';
export * from './route-snapshot.js';
export * from './service.js';
