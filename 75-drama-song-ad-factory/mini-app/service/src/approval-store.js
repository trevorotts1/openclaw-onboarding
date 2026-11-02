// ============================================================================
// approval-store.js — Drama Studio service: create-once approval authority (P07)
//
// The approval record used to live in the KV adapter: read, decide in memory,
// write back. Two requests answered at the same moment both read "unanswered"
// and both wrote a decision, and a repeat publish handed out fresh upload links
// for object paths a later publish also used. KV has no compare-and-set here,
// so no amount of care in approvals-api.js could make that atomic.
//
// R2 does have a native precondition. `put(path, value, { onlyIf })` runs
// server-side and at most one competing create wins; the loser gets `null` back
// (https://developers.cloudflare.com/r2/reference/consistency/). So approval
// AUTHORITY lives in R2 as create-once objects and there is no process-local
// lock, no second database, no new secret and no new dependency.
//
// Layout, one version of one stage of one order:
//
//   clients/<client>/orders/<order>/approvals-v2/<stage>-v<version>/
//     intent.json     the published presentation, written BEFORE any upload
//                     link is minted (immutable)
//     staging/<name>  where a presigned PUT may still land (mutable)
//     files/<name>    the frozen bytes, created once from verified staging
//     ready.json      the answerable presentation, written after every file
//                     is frozen (immutable)
//     decision.json   the client's answer, created once (immutable)
//
// `approvals-v2` is a NEW namespace: upload links issued by the old code point
// at `approvals/<stage>-v<version>/`, so they can never reach these objects.
//
// Missing capability is a named refusal, never a KV fallback: a store that
// cannot create atomically cannot hold authority.
// ============================================================================

'use strict';

import { scopePath } from './ids.js';

/** The one code for "this deployment cannot hold approval authority". */
export const AF_APPROVAL_STORAGE = 'APPROVAL_STORAGE_UNAVAILABLE';
/** Frozen bytes on disk are not the bytes the intent declared. */
export const AF_APPROVAL_BYTES = 'APPROVAL_BYTES_CONFLICT';

/** New namespace — deliberately not `approvals` (see the header). */
export const AUTHORITY_DIR = 'approvals-v2';

/** A lowercase SHA-256 hex digest. */
export const DIGEST_RE = /^[0-9a-f]{64}$/;

export function authorityPrefix(clientId, orderId) {
  return scopePath(clientId, 'orders', orderId, AUTHORITY_DIR);
}

export function versionPrefix(clientId, orderId, stage, version) {
  return scopePath(clientId, 'orders', orderId, AUTHORITY_DIR, `${stage}-v${version}`);
}

export function intentPath(clientId, orderId, stage, version) {
  return `${versionPrefix(clientId, orderId, stage, version)}/intent.json`;
}

export function readyPath(clientId, orderId, stage, version) {
  return `${versionPrefix(clientId, orderId, stage, version)}/ready.json`;
}

export function decisionPath(clientId, orderId, stage, version) {
  return `${versionPrefix(clientId, orderId, stage, version)}/decision.json`;
}

export function stagingPath(clientId, orderId, stage, version, name) {
  return `${versionPrefix(clientId, orderId, stage, version)}/staging/${name}`;
}

export function frozenPath(clientId, orderId, stage, version, name) {
  return `${versionPrefix(clientId, orderId, stage, version)}/files/${name}`;
}

/** The R2 binding when it can read and write; null otherwise (fail closed). */
export function approvalBucket(env) {
  const bucket = env && env.DRAMA_STUDIO;
  if (!bucket || typeof bucket.get !== 'function' || typeof bucket.put !== 'function') return null;
  return bucket;
}

/**
 * Create one immutable record. Returns exactly one of:
 *   { created: true }   this caller won and the record now exists
 *   { exists: true }    another writer already created it (read it, never overwrite)
 *   { error: true }     the store refused or threw
 */
export async function createOnce(bucket, path, value, contentType = 'application/json') {
  const body = typeof value === 'string' ? value : JSON.stringify(value);
  try {
    const written = await bucket.put(path, body, {
      onlyIf: new Headers({ 'If-None-Match': '*' }),
      httpMetadata: { contentType, cacheControl: 'no-store' },
    });
    return written === null ? { created: false, exists: true } : { created: true };
  } catch {
    return { created: false, error: true };
  }
}

/** Create one frozen file. `sha256` is verified by R2 natively on this write. */
export async function putFrozen(bucket, path, bytes, contentType, sha256) {
  try {
    const written = await bucket.put(path, bytes, {
      onlyIf: new Headers({ 'If-None-Match': '*' }),
      httpMetadata: { contentType, cacheControl: 'no-store' },
      sha256,
    });
    return written === null ? { created: false, exists: true } : { created: true };
  } catch {
    return { created: false, error: true };
  }
}

/**
 * A record that exists but could not be read is NOT an absent record. Absence is
 * `null`; every failure to read an object that should be there is this error,
 * which the route turns into HTTP 503 APPROVAL_STORAGE_UNAVAILABLE. Returning
 * `null` on a failed read would report a stored decision as unanswered and a
 * listed manifest as "nothing waiting" — a successful empty, not a fact.
 */
export class ApprovalStorageError extends Error {
  constructor(message = 'Approval storage could not be read.') {
    super(message);
    this.name = 'ApprovalStorageError';
    this.code = AF_APPROVAL_STORAGE;
  }
}

export async function readJson(bucket, path) {
  const object = await readObject(bucket, path);
  if (!object) return null;
  try {
    const parsed = JSON.parse(await object.text());
    if (parsed && typeof parsed === 'object') return parsed;
  } catch {
    // Fall through: an unreadable authoritative record is a read failure.
  }
  throw new ApprovalStorageError(`The approval record ${path} could not be read.`);
}

/** `null` ONLY when the store says the object does not exist. */
export async function readObject(bucket, path) {
  if (!bucket || typeof bucket.get !== 'function') {
    throw new ApprovalStorageError('This deployment has no approval object store.');
  }
  try {
    return (await bucket.get(path)) || null;
  } catch {
    throw new ApprovalStorageError(`The approval store could not be read for ${path}.`);
  }
}

/**
 * Every ready presentation for this order's NEW namespace. Only `ready.json`
 * is answerable; an intent with a lost or unverified upload is resumed, never
 * listed as if it had been published.
 */
export async function listReady(bucket, clientId, orderId) {
  const prefix = `${authorityPrefix(clientId, orderId)}/`;
  const found = [];
  let cursor;
  do {
    let page;
    try {
      page = await bucket.list({ prefix, cursor, limit: 1000 });
    } catch {
      throw new ApprovalStorageError('The approval store could not be listed.');
    }
    for (const object of (page && page.objects) || []) {
      const name = object && object.key;
      if (typeof name === 'string' && name.endsWith('/ready.json')) found.push(name);
    }
    cursor = page && page.truncated ? page.cursor : undefined;
  } while (cursor);
  const manifests = [];
  for (const path of found) {
    // A listed manifest that cannot be read is a failed read, never "no items".
    const manifest = await readJson(bucket, path);
    if (!manifest || typeof manifest.stage !== 'string' || !Number.isInteger(manifest.version)) {
      throw new ApprovalStorageError(`The listed approval manifest ${path} could not be read.`);
    }
    manifests.push(manifest);
  }
  return manifests;
}

/** Lowercase hex SHA-256 of bytes (Web Crypto; identical in Workers and Node 18+). */
export async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * True when this stored object is exactly the declared bytes. Prefers the
 * store's own checksum, and falls back to hashing the bytes it returns.
 */
function hexOf(bytes) {
  return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * R2 returns `checksums.sha256` as an ArrayBuffer; a test double or an older
 * adapter may hand back the same digest as lowercase hex. Both are the same
 * declaration, so both are read here.
 */
export function checksumHex(checksums) {
  const raw = checksums && checksums.sha256;
  if (typeof raw === 'string') return raw.toLowerCase();
  if (raw instanceof ArrayBuffer) return hexOf(raw);
  if (raw && ArrayBuffer.isView(raw)) {
    return hexOf(new Uint8Array(raw.buffer, raw.byteOffset, raw.byteLength));
  }
  return '';
}

export async function objectMatches(object, expectedBytes, expectedSha) {
  if (!object) return false;
  if (typeof object.size === 'number' && object.size !== expectedBytes) return false;
  const declared = checksumHex(object.checksums);
  if (DIGEST_RE.test(declared)) return declared === expectedSha;
  let bytes;
  try {
    bytes = await object.arrayBuffer();
  } catch {
    throw new ApprovalStorageError('The stored bytes could not be read back.');
  }
  if (!bytes || bytes.byteLength !== expectedBytes) return false;
  return (await sha256Hex(bytes)) === expectedSha;
}
