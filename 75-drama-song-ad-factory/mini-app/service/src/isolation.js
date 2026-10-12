// ============================================================================
// isolation.js — Drama Studio service: per-client isolation (U2)
//
// Joint plan section 3.15, "One client can never see another's":
//   1. POSSESSION  — a request reaches a client's records only with a key the
//      studio minted. No key record -> refused before any read.
//   2. BINDING     — client_id comes ONLY from the stored key record. Any
//      client_id inside a request body is IGNORED, and a body that claims a
//      DIFFERENT client_id is refused outright (AF-DS-ISO-CROSS).
//   3. SCOPE       — every object path is checked with ownsPath before a read
//      or a presign, so a key can never address another client's namespace.
//   4. ENROLLMENT  — the fleet enrollment secret lets a box REGISTER a new
//      client. It can never adopt or read an existing one.
//
// Section 3.16: "Version 0 ships with a test that tries to read across clients
// and must fail." prove/prove_service_boundaries.mjs is that test.
// ============================================================================

'use strict';

import { AF_ID_INVALID, isClientId, ownsPath, randomClientId } from './ids.js';
import { AF_KEY_MALFORMED, AF_KEY_REVOKED, AF_KEY_UNKNOWN, fingerprintOf, keyRecordKey } from './keys.js';

export const AF_ISO_CROSS = 'AF-DS-ISO-CROSS';
export const AF_ISO_SCOPE = 'AF-DS-ISO-SCOPE';
export const AF_ENROLL_REFUSED = 'AF-DS-ENROLL-REFUSED';

/**
 * Resolve a presented key to the studio's own record for it.
 * @returns {{ok:true, record:object} | {ok:false, code:string}}
 */
export async function resolveKey(store, presentedKey) {
  if (typeof presentedKey !== 'string' || presentedKey.length < 32) {
    return { ok: false, code: AF_KEY_MALFORMED };
  }
  const raw = await store.kvGet(keyRecordKey(await fingerprintOf(presentedKey)));
  if (!raw) return { ok: false, code: AF_KEY_UNKNOWN };
  let record;
  try {
    record = JSON.parse(raw);
  } catch {
    return { ok: false, code: AF_KEY_MALFORMED };
  }
  if (!record || typeof record.client_id !== 'string') {
    return { ok: false, code: AF_KEY_MALFORMED };
  }
  if (record.status !== 'active') return { ok: false, code: AF_KEY_REVOKED };
  return { ok: true, record };
}

/**
 * The one door every client-scoped route goes through.
 *
 * `claimedClientId` is whatever the request body/query said. It is allowed to
 * be absent, and it is allowed to equal the key's own client_id. Anything else
 * is a cross-client attempt and is refused — the key record still wins.
 */
export async function authorizeClient(store, presentedKey, claimedClientId) {
  const resolved = await resolveKey(store, presentedKey);
  if (!resolved.ok) return resolved;
  const own = resolved.record.client_id;
  if (!isClientId(own)) {
    // A key record whose client_id is not a studio-issued id (e.g. one paired
    // before the admin surface validated it) can never open a scoped path.
    // Refuse it HERE, in ONE place, so no key-authorized route throws
    // AF-DS-ID-INVALID out of scopePath and crashes the Worker (CHECKIN-500).
    return { ok: false, code: AF_ID_INVALID };
  }
  if (claimedClientId !== undefined && claimedClientId !== null && claimedClientId !== own) {
    return { ok: false, code: AF_ISO_CROSS };
  }
  return { ok: true, client_id: own, record: resolved.record };
}

/** Read one of the caller's own objects. Refuses any path outside the scope. */
export async function readOwnObject(objectStore, clientId, path) {
  if (!ownsPath(clientId, path)) return { ok: false, code: AF_ISO_SCOPE };
  const obj = await objectStore.objectGet(path);
  return { ok: true, value: obj ? obj.value : null };
}

// ---------------------------------------------------------------------------
// Enrollment (section 3.15) — register a NEW client, never adopt an old one
// ---------------------------------------------------------------------------

/**
 * @param {object} args
 * @param {object} args.store
 * @param {object} args.env          must carry DS_ENROLLMENT_SECRET
 * @param {string} args.presentedSecret
 * @param {string|undefined} args.claimedClientId  refused if it names anyone
 * @param {number} args.nowMs
 * @param {string} [args.entropyHex]
 */
export async function enrollClient({ store, env, presentedSecret, claimedClientId, nowMs, entropyHex }) {
  const expected = env && env.DS_ENROLLMENT_SECRET;
  if (typeof expected !== 'string' || !expected) {
    // No secret configured is fail-closed: registration is unavailable, never
    // open. The value itself is never read back out or logged.
    return { ok: false, code: AF_ENROLL_REFUSED };
  }
  if (typeof presentedSecret !== 'string' || presentedSecret !== expected) {
    return { ok: false, code: AF_ENROLL_REFUSED };
  }
  if (claimedClientId !== undefined && claimedClientId !== null) {
    // Holding the fleet secret lets someone register a new box. It never lets
    // them attach to, or read, an existing client.
    return { ok: false, code: AF_ENROLL_REFUSED };
  }
  const clientId = randomClientId(entropyHex);
  const existing = await store.kvGet(`client:${clientId}`);
  if (existing) return { ok: false, code: AF_ENROLL_REFUSED };
  await store.kvPut(
    `client:${clientId}`,
    JSON.stringify({ client_id: clientId, created_at: nowMs }),
  );
  return { ok: true, client_id: clientId };
}
