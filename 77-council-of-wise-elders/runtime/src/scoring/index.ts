/**
 * Deterministic scoring services (CWE-026).
 *
 * The produced artifact of CWE-026 is the deterministic-decision-validator:
 * the pure scoring services in this folder plus the verdict services in
 * ../protocol/verdict.ts. Per Section 34.3, a contract-only artifact
 * carries its verification level, its synthetic fixture identity, and
 * the obligations of the consumers that wire it to live sessions.
 */

export * from './critical-domains.js';
export * from './decision.js';

/** Identity and honesty envelope of the CWE-026 artifact (Section 34.3). */
export const DETERMINISTIC_DECISION_VALIDATOR = {
  artifact: 'deterministic-decision-validator',
  unit: 'CWE-026',
  /**
   * These services are proven against locked schemas and synthetic
   * fixtures. They are not wired to a live discussion engine here.
   */
  verification_level: 'contract_tested',
  fixture_identity: 'cwe-026-synthetic-fixtures/v1',
  consumer_obligations: [
    'CWE-050 wires these services to the complete engine and owns final exact-hash validation in the composed journey (Sections 17.5, 34 CWE-050).',
    'A result computed from synthetic fixture cards proves contract behavior only; it is not live council evidence and must never be presented as a live verdict.',
    'Consumers must feed the frozen brief weights and the frozen critical-domain classification; re-deriving either at scoring time breaks the freeze (Sections 12.1, 12.7).',
    'Publication requires validateVerdictForPublication against the exact verdict revision hash; earlier-round validation never substitutes (Sections 11.5, 14.6).',
  ],
} as const;
