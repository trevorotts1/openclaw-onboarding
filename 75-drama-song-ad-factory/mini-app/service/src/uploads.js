// ============================================================================
// uploads.js — Drama Studio service: upload handling (U2)
//
// Joint plan section 3.2: "uploads go straight from phone to storage through a
// short-lived upload link (Book Writer pattern,
// 53-book-writer/mini-app/worker/src/media.js)". The bytes never ride a Worker
// request body: the service validates the SHAPE, mints a presigned direct R2
// PUT, and stores only {object_path, sha256, status: queued}.
//
// Every object lands under clients/<client_id>/intake/... — the caller's own
// scope, from the key record, never from the body (isolation.js).
//
// A rejection always names its code. A silent blank is a defect.
// ============================================================================

'use strict';

import { randomHex, scopePath } from './ids.js';

export const MAX_BYTES = { audio: 25 * 1024 * 1024, image: 25 * 1024 * 1024, video: 200 * 1024 * 1024 };

export const EXTENSIONS = {
  audio: ['webm', 'mp3', 'm4a', 'wav', 'ogg'],
  image: ['jpg', 'jpeg', 'png', 'heic', 'webp'],
  video: ['mp4', 'mov', 'webm'],
};

// First-bytes signatures for the extensions we accept. Not a scanner — a shape
// check at the trust boundary, so a renamed executable cannot ride an image
// upload.
const MAGIC = {
  webm: [[0x1a, 0x45, 0xdf, 0xa3]],
  mp4: null, // ISO-BMFF: bytes 4..8 are "ftyp"
  mov: null,
  mp3: [[0x49, 0x44, 0x33], [0xff, 0xfb], [0xff, 0xf3], [0xff, 0xf2]],
  m4a: null,
  wav: [[0x52, 0x49, 0x46, 0x46]],
  ogg: [[0x4f, 0x67, 0x67, 0x53]],
  jpg: [[0xff, 0xd8, 0xff]],
  jpeg: [[0xff, 0xd8, 0xff]],
  png: [[0x89, 0x50, 0x4e, 0x47]],
  heic: null, // ISO-BMFF
  webp: [[0x52, 0x49, 0x46, 0x46]],
};

const ISO_BMFF = new Set(['mp4', 'mov', 'm4a', 'heic']);

export const AF_UP_FIELD = 'AF-DS-UP-REJECT-FIELD';
export const AF_UP_FORMAT = 'AF-DS-UP-REJECT-FORMAT';
export const AF_UP_SIZE = 'AF-DS-UP-REJECT-SIZE';
export const AF_UP_CAPABILITY = 'AF-DS-UP-CAPABILITY';
export const AF_UP_CROSS = 'AF-DS-UP-CROSS';

export function uploadKey(clientId, uploadId) {
  return `upload:${clientId}:${uploadId}`;
}

/**
 * Shape check. Returns {ok:true, ext} or {ok:false, code, message}.
 * `headerBytes` is the first few bytes read on the client before it asks for a
 * link; without them nothing is accepted.
 */
export function validateUpload({ channel, filename, sizeBytes, contentType, headerBytes }) {
  const allowed = EXTENSIONS[channel];
  if (!allowed) {
    return { ok: false, code: AF_UP_FIELD, message: 'channel must be audio, image or video.' };
  }
  if (typeof filename !== 'string' || !filename.includes('.')) {
    return { ok: false, code: AF_UP_FIELD, message: 'filename is required.' };
  }
  const ext = filename.toLowerCase().split('.').pop();
  if (!allowed.includes(ext)) {
    return { ok: false, code: AF_UP_FORMAT, message: `.${ext} is not accepted for ${channel}.` };
  }
  if (typeof sizeBytes !== 'number' || sizeBytes <= 0) {
    return { ok: false, code: AF_UP_FIELD, message: 'size_bytes is required.' };
  }
  if (sizeBytes > MAX_BYTES[channel]) {
    return {
      ok: false,
      code: AF_UP_SIZE,
      message: `That file is too big (limit ${Math.round(MAX_BYTES[channel] / 1024 / 1024)} MB).`,
    };
  }
  const sigs = MAGIC[ext];
  if (Array.isArray(headerBytes) && headerBytes.length >= 4) {
    const matches = ISO_BMFF.has(ext)
      ? headerBytes.slice(4, 8).join(',') === '102,116,121,112'
      : (sigs || []).some((sig) => sig.every((b, i) => headerBytes[i] === b));
    if (!matches) {
      return { ok: false, code: AF_UP_FORMAT, message: 'That file is not the format its name says.' };
    }
  } else {
    return { ok: false, code: AF_UP_FIELD, message: 'header_bytes is required.' };
  }
  return { ok: true, ext };
}

/**
 * Accept an upload: validate, mint the scoped object key, create the queued
 * job, hand back a presigned direct R2 PUT.
 *
 * @param {string} clientId  from the resolved key record — NEVER from the body
 */
export async function acceptUpload({ store, env, clientId, body, nowUtc, entropyHex }) {
  if (!body || typeof body !== 'object') {
    return { ok: false, status: 400, code: AF_UP_FIELD, message: 'Request body must be JSON.' };
  }
  if (body.client_id !== undefined && body.client_id !== null && body.client_id !== clientId) {
    return { ok: false, status: 403, code: AF_UP_CROSS, message: 'That upload does not belong to this key.' };
  }
  const check = validateUpload({
    channel: body.channel,
    filename: typeof body.filename === 'string' ? body.filename : '',
    sizeBytes: body.size_bytes,
    contentType: body.content_type,
    headerBytes: body.header_bytes,
  });
  if (!check.ok) return { ok: false, status: 422, code: check.code, message: check.message };

  const uploadId = `u_${randomHex(12)}`;
  const objectPath = scopePath(clientId, 'intake', `${uploadId}.${check.ext}`);
  const job = {
    client_id: clientId,
    upload_id: uploadId,
    channel: body.channel,
    object_path: objectPath,
    source_sha256: typeof body.source_sha256 === 'string' ? body.source_sha256 : null,
    content_type: body.content_type || null,
    size_bytes: body.size_bytes,
    max_bytes: MAX_BYTES[body.channel],
    status: 'queued',
    created_at: nowUtc,
  };

  // Persist the queued job BEFORE the link is handed out, so a phone that
  // uploads and dies still has a pollable job.
  await store.kvPut(uploadKey(clientId, uploadId), JSON.stringify(job));

  const presigned = await presignPut(env, objectPath, body.content_type);
  if (!presigned.ok) {
    await store.kvPut(
      uploadKey(clientId, uploadId),
      JSON.stringify({ ...job, status: 'failed', error: 'storage-not-ready' }),
    );
    return { ok: false, status: 503, code: AF_UP_CAPABILITY, message: 'Upload storage is not ready. Try again shortly.' };
  }
  return { ok: true, status: 201, upload_id: uploadId, object_path: objectPath, upload: presigned.upload };
}

export async function pollUpload(store, { clientId, uploadId }) {
  const raw = await store.kvGet(uploadKey(clientId, uploadId));
  if (!raw) return { ok: false, status: 404, code: AF_UP_FIELD, message: 'Upload not found.' };
  return { ok: true, status: 200, job: JSON.parse(raw) };
}

// ---------------------------------------------------------------------------
// Presigned R2 PUT (S3-compatible). Placeholder ids only: real credentials come
// from bound secrets, never from source, and are never printed.
// ---------------------------------------------------------------------------
export async function presignPut(env, objectPath, contentType) {
  const e = env || {};
  const accountId = e.R2_ACCOUNT_ID || '<PLACEHOLDER>';
  const accessKeyId = e.R2_ACCESS_KEY_ID || '<PLACEHOLDER>';
  const secretAccessKey = e.R2_SECRET_ACCESS_KEY || '<PLACEHOLDER>';
  const bucket = e.DRAMA_STUDIO_BUCKET || 'zhw-drama-studio';
  if ([accountId, accessKeyId, secretAccessKey].some((v) => String(v).startsWith('<'))) {
    return { ok: false, error: 'storage credentials not set' };
  }
  const host = `${accountId}.r2.cloudflarestorage.com`;
  const path = `/${bucket}/${objectPath}`;
  const amzDate = new Date().toISOString().replace(/[:-]|\.\d{3}/g, '');
  const dateStamp = amzDate.slice(0, 8);
  const scope = `${dateStamp}/auto/s3/aws4_request`;
  const payloadHash = 'UNSIGNED-PAYLOAD';
  const query = [
    'X-Amz-Algorithm=AWS4-HMAC-SHA256',
    `X-Amz-Credential=${encodeURIComponent(`${accessKeyId}/${scope}`)}`,
    `X-Amz-Date=${amzDate}`,
    'X-Amz-Expires=3600',
    'X-Amz-SignedHeaders=host',
  ].sort().join('&');
  const canonicalRequest = ['PUT', path, query, `host:${host}`, '', 'host', payloadHash].join('\n');
  const stringToSign = ['AWS4-HMAC-SHA256', amzDate, scope, await hexSha256(canonicalRequest)].join('\n');
  // SigV4 derives each signing key from RAW HMAC bytes, never their hex text.
  const dateKey = await hmac(`AWS4${secretAccessKey}`, dateStamp);
  const regionKey = await hmac(dateKey, 'auto');
  const serviceKey = await hmac(regionKey, 's3');
  const signingKey = await hmac(serviceKey, 'aws4_request');
  const signature = [...await hmac(signingKey, stringToSign)]
    .map((b) => b.toString(16).padStart(2, '0')).join('');
  return {
    ok: true,
    upload: {
      method: 'PUT',
      url: `https://${host}${path}?${query}&X-Amz-Signature=${signature}`,
      content_type: contentType || 'application/octet-stream',
      expires_in: 3600,
    },
  };
}

// Web Crypto only — identical in Workers and Node 18+.
async function hexSha256(input) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function hmac(key, input) {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey('raw', typeof key === 'string' ? enc.encode(key) : key, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', k, enc.encode(input));
  return new Uint8Array(sig);
}
