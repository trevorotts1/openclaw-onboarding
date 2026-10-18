/**
 * Standalone Council front-door service surface (WER-021 dependency-ready
 * slice).
 *
 * Consumed by path import — this slice adds no package export map entry:
 *
 *   import { CouncilFrontDoor } from '../service/index.js';
 *
 * The package barrel (src/index.ts) is owned by an existing file and is
 * deliberately not edited by this unit.
 */

export * from './types.js';
export * from './identity.js';
export * from './readiness.js';
export * from './sessions.js';
export * from './front-door.js';
