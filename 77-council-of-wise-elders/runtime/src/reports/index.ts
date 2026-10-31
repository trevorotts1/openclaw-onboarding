/**
 * CWE-038 validated report export service (directive Section 24).
 *
 * Exports are produced ONLY from a verdict revision that passes
 * CWE-026 deterministic publication validation, under CWE-007 trusted
 * authorization, journaled through the CWE-006 event journal, and
 * registered as deliverables bound to the exact verdict revision and
 * content hash. Registered formats: canonical record JSON, Markdown
 * report, print HTML (all byte-deterministic from the one report
 * model), and PDF, rendered from the same print HTML by the host
 * renderer capability (`pdf-renderer.ts`) and ready only when that
 * capability is actually present; a PDF is never faked with renamed
 * bytes.
 *
 * `report-download.ts` composes the saved-session PDF download over
 * this service for the standalone front door: one saved record, no
 * provider call, no new inference. The Command Center's own
 * report-downloads composition remains CWE-050.
 */
export * from './errors.js';
export * from './model.js';
export * from './render.js';
export * from './registry.js';
export * from './journal.js';
export * from './service.js';
export * from './pdf-renderer.js';
export * from './report-download.js';
export * from './capability-snapshot.js';
export * from './seat-descriptors.js';
export * from './asset-embed.js';

export const VALIDATED_REPORT_EXPORT_SERVICE = {
  artifact: 'validated-report-export-service',
  unit: 'CWE-038',
  verification_level: 'contract_tested',
  fixture_identity: 'cwe-038-synthetic-fixtures/v1',
  consumer_obligations: [
    'CWE-050 composes this service into the production export job and authenticated download path, wires the package barrel re-export, and binds the CC report-downloads surface; synthetic-fixture results are contract behavior only, never live report evidence.',
    'The pdf deliverable is produced by the host renderer capability (headless Chrome/Chromium, the Playwright browser cache, or the CUPS filter) and is ready only where that probe passes; elsewhere exports requesting pdf refuse with EXPORT_FORMAT_NOT_READY naming the missing piece. T106 visual QA of a rendered PDF is still owned by CWE-044.',
    'Hosts supply the trusted principal (CWE-007), the session scope and visibility, the current validated verdict revision, and the deletion-liveness port (CWE-006 tombstones); the service never resolves identity or session state itself.',
    'Seat qualifications are printed exactly as the caller recorded them from the seat-pack registry; this service never upgrades a qualification (CWE-012 condition 1).',
  ],
} as const;
