/**
 * Source integrity and pack validation (CWE-012).
 *
 * Public surface: the Section 8.3 source record and evidence schemas,
 * the quotation tuple verifier, the coverage gate, the advisor pack
 * validator with its immutable audit output, the seat registry checks,
 * and the Skill 22 export package validator.
 */
export * from './schemas';
export * from './text';
export * from './quotes';
export * from './coverage';
export * from './packs';
export * from './audit';
export * from './export-package';
// CWE-050: the Skill 22 export (v1) to strict-schema adapter and its
// material catalog (sources/export-v2.ts).
export * from './export-v2';

export * from './skill22-exporter';
