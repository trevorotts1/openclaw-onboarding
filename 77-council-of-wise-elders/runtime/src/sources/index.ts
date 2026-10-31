/**
 * Source integrity and pack validation (CWE-012).
 *
 * Public surface: the Section 8.3 source record and evidence schemas,
 * the quotation tuple verifier, the coverage gate, the advisor pack
 * validator with its immutable audit output, the seat registry checks,
 * and the Skill 22 export package validator.
 */
export * from './schemas.js';
export * from './text.js';
export * from './quotes.js';
export * from './coverage.js';
export * from './packs.js';
export * from './audit.js';
export * from './export-package.js';
// CWE-050: the Skill 22 export (v1) to strict-schema adapter and its
// material catalog (sources/export-v2.ts).
export * from './export-v2.js';

export * from './skill22-exporter.js';
