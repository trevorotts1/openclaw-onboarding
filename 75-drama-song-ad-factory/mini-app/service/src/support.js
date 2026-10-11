// ============================================================================
// support.js — Drama Studio service: the two small helpers every module needs
//
// 1. randomConnectHex(n) — the run-id shape the plan uses ("r_123", section
//    3.10). Lowercase hex, short, no names.
// 2. listKeys(store, prefix) — one paged listing over the injected KV adapter,
//    so index.js can read a client's own orders without a client-supplied
//    index. The adapter is the only I/O; this module stays binding-free.
// ============================================================================

'use strict';

import { randomHex } from './ids.js';

export function randomConnectHex(bytes = 4) {
  return randomHex(bytes);
}

/** Every key under `prefix` for the caller's own scope. Empty when the adapter
 *  cannot list — fail-closed, never a guessed key. */
export async function listKeys(store, prefix) {
  if (!store || typeof store.kvList !== 'function') return [];
  const names = await store.kvList(prefix);
  return Array.isArray(names) ? names : [];
}
