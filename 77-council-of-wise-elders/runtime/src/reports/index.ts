/**
 * CWE-038 validated report export service (directive Section 24).
 *
 * Exports are produced ONLY from a verdict revision that passes
 * CWE-026 deterministic publication validation, under CWE-007 trusted
 * authorization, journaled through the CWE-006 event journal, and
 * registered as deliverables bound to the exact verdict revision and
 * content hash. Registered formats: canonical record JSON, Markdown
 * report, print HTML (all byte-deterministic from the one report
 * model), and PDF, which is registered not ready because the approved
 * Playwright/Chromium renderer is not in this runtime's dependency
 * bill; rendered PDF belongs to CWE-044 and is never faked.
 *
 * Not here, by design: production HTTP download endpoints and the CC
 * report-downloads composition belong to CWE-050; rendered-PDF visual
 * QA (T106) belongs to CWE-044. Consumers import this module by path,
 * like the CWE-007 authorization and CWE-026 scoring modules, until
 * integration wires the package barrel.
 */
export * from './errors.js';
export * from './model.js';
export * from './render.js';
export * from './registry.js';
export * from './journal.js';
export * from './service.js';

export const VALIDATED_REPORT_EXPORT_SERVICE = {
  artifact: 'validated-report-export-service',
  unit: 'CWE-038',
  verification_level: 'contract_tested',
  fixture_identity: 'cwe-038-synthetic-fixtures/v1',
  consumer_obligations: [
    'CWE-050 composes this service into the production export job and authenticated download path, wires the package barrel re-export, and binds the CC report-downloads surface; synthetic-fixture results are contract behavior only, never live report evidence.',
    'CWE-044 owns rendered PDF production through the approved Playwright/Chromium capability and the T106 visual QA; until then the pdf deliverable stays registered not_ready and exports requesting it refuse with EXPORT_FORMAT_NOT_READY.',
    'Hosts supply the trusted principal (CWE-007), the session scope and visibility, the current validated verdict revision, and the deletion-liveness port (CWE-006 tombstones); the service never resolves identity or session state itself.',
    'Seat qualifications are printed exactly as the caller recorded them from the seat-pack registry; this service never upgrades a qualification (CWE-012 condition 1).',
  ],
} as const;
