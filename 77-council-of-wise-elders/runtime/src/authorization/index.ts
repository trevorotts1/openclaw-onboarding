/**
 * CWE-007 trusted authorization ports (directive Sections 17, 28).
 *
 * Pure decision functions in canonical contract terms: trusted scope
 * resolution results, claimed-scope conflict rejection, private-owner
 * visibility, the four separate authorization kinds, machine-client
 * binding, and the query credential guard. Host adapters resolve a
 * TrustedPrincipal from their own verified identity mechanism (Command
 * Center tenant context; the local single-owner host) and consume these
 * decisions without re-implementing the checks.
 *
 * Not here, by design: run grants, previews, and admission belong to
 * CWE-049 (runtime/src/authorization/run-grants.ts and siblings), which
 * composes on top of this module.
 */
export * from './scope.js';
export * from './permissions.js';
// CWE-049 composition: the run authorization service (run-grants.ts)
// and per-operation admission (admission.ts) compose on the CWE-007
// ports above. These two lines are the barrel wiring CWE-007's header
// promised ("which are deliberately not defined here"); no CWE-007
// decision function is changed by them.
export * from './run-grants.js';
export * from './admission.js';
// WER-009 front door: one structured approval command with an
// idempotency fingerprint over the ENTIRE command, a committed receipt,
// preview-to-session association, and an idempotent read-only Start
// that resolves the committed grant (no fabricated grant id). It
// composes the service above; it is not a second authority store.
export * from './approval-front-door.js';
