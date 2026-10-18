/**
 * Council remote access surface (WER-023 code half).
 *
 * Consumed by path import; this new directory adds no package export map
 * entry and edits no existing file:
 *
 *   import { RemoteSessionBridge } from '../remote/index.js';
 *
 * It binds the application side of the EXISTING Cloudflare Access /
 * named Tunnel topology (team domain, pinned audience, exact allowed
 * origin, one named Tunnel endpoint). It creates no Cloudflare resource
 * and makes no network call unless a live JWKS source is read at
 * verification time.
 */

export * from './types.js';
export * from './access-jwt.js';
export * from './auth.js';
export * from './sessions.js';
