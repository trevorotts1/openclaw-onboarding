// ============================================================================
// ids.js — Drama Studio service: client identity and path scoping (U2)
//
// Joint plan section 3.15, "One client can never see another's":
//   - the studio, not the box, invents the client's internal identifier
//   - no names in links, no names in storage paths
//   - every stored file sits under that identifier
//
// PURE: Web Crypto only (works in Cloudflare Workers and Node 18+), no
// bindings, no I/O, no globals.
// ============================================================================

'use strict';

/** The one code for "this is not a studio-issued client id". */
export const AF_ID_INVALID = 'AF-DS-ID-INVALID';

const CLIENT_ID_RE = /^c-[0-9a-f]{32}$/;

/** Cryptographically random lowercase hex. */
export function randomHex(bytes) {
  const b = new Uint8Array(bytes);
  crypto.getRandomValues(b);
  return [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
}

/** Studio-invented client identifier. Never derived from a name or a slug. */
export function randomClientId(entropyHex) {
  if (typeof entropyHex === 'string' && /^[0-9a-f]{32}$/.test(entropyHex)) {
    return `c-${entropyHex}`;
  }
  return `c-${randomHex(16)}`;
}

export function isClientId(value) {
  return typeof value === 'string' && CLIENT_ID_RE.test(value);
}

/**
 * Every stored object path for a client lives under clients/<client_id>/.
 * Traversal segments throw rather than resolve outside the scope.
 */
export function scopePath(clientId, ...segments) {
  if (!isClientId(clientId)) throw new Error(AF_ID_INVALID);
  const tail = segments
    .map((s) => String(s).replace(/^\/+|\/+$/g, ''))
    .filter(Boolean);
  for (const s of tail) {
    if (s.includes('..')) throw new Error('AF-DS-ID-TRAVERSAL');
  }
  return ['clients', clientId, ...tail].join('/');
}

/**
 * True only when `path` is inside `clientId`'s own namespace. This is the
 * single predicate every read/write funnels through, so a cross-client path
 * can never be spelled by accident.
 */
export function ownsPath(clientId, path) {
  if (!isClientId(clientId) || typeof path !== 'string') return false;
  const parts = path.replace(/^\/+/, '').split('/');
  return parts[0] === 'clients' && parts[1] === clientId;
}
