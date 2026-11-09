/**
 * @blackceo/wise-elders-core: canonical contracts package surface (CWE-003).
 *
 * Proposed internal package identity per directive Section 6.2; this is not
 * an assertion that the package exists on npm and it must not be published
 * publicly without authorization.
 *
 * The deterministic core contains no host, UI, network, filesystem, clock,
 * or random imports. Clock and ID generation reach the core only through
 * the Clock and IdSource seams in primitives.ts.
 */

export * from './errors.js';
export * from './enums.js';
export * from './modes.js';
export * from './primitives.js';
export * from './canonical-json.js';
export { sha256Hex } from './sha256.js';
export * from './schemas.js';
export * from './state-machine.js';
export * from './scoring.js';
export * from './diagnostic-retention.js';
export * from './golden-vectors.js';
export {
  generateJsonSchemaArtifact,
  JSON_SCHEMA_ARTIFACT_PATH,
  cardAuthorJsonSchema,
  type CardAuthorKind,
} from './generate.js';
export type * from './types.js';
