/**
 * OpenClaw VPS/container platform adapter (WER-022 dependency-ready slice).
 *
 * Consumed by path import — this slice adds no package export map entry:
 *
 *   import { resolvePlatform } from '../platform/index.js';
 *
 * Deferred, never claimed here: a real VPS deployment, a real container
 * recreate, real gateway connectivity and an authenticated remote origin.
 * Those belong to WER-026/WER-027 and are named in
 * `PLATFORM_DEFERRED_TO_REAL_HOST`.
 */

export * from './types.js';
export * from './mounts.js';
export * from './windows.js';
export * from './loopback.js';
export * from './identity.js';
export * from './ports.js';
export * from './recreation.js';
export * from './adapter.js';
