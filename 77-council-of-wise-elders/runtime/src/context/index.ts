/**
 * CWE-022 authorized retrieval and bounded context assembly (directive
 * Sections 8, 9, 13). Graph product: bounded-authorized-context.
 *
 * Consumes: the CWE-006 scoped store (through the CouncilStore port in
 * session-source.ts), the CWE-007 trusted authorization ports (every
 * retrieval decision in retrieval.ts), and the CWE-012 source-and-pack
 * validator (record and evidence schemas, sourceVersionOf, and the
 * export package validator, imported in-tree from runtime/src/sources).
 *
 * Produces: a deterministic, provenance-carrying, byte-bounded context
 * payload per operation, or the typed CONTEXT_TOO_SMALL readiness
 * result. CWE-023 (intake) and CWE-024 (opening executor) build on this
 * surface; nothing here calls a provider, reads a clock, or generates
 * an ID.
 */
export * from './types.js';
export * from './retrieval.js';
export * from './assembly.js';
export * from './session-source.js';
