// ============================================================================
// fakes.mjs — in-memory adapters for the Drama Studio service tests/prover.
//
// The service takes its KV and object stores as INJECTED adapters (never a
// binding), which is what makes every rule here testable with no Cloudflare
// account, no network and no credentials. These fakes are the same shapes
// index.js's kvStore/r2Store produce.
// ============================================================================

import { createHash } from 'node:crypto';

export function memStore() {
  const mem = new Map();
  return {
    kvGet: async (k) => (mem.has(k) ? mem.get(k) : null),
    kvPut: async (k, v) => {
      mem.set(k, v);
    },
    kvDelete: async (k) => {
      mem.delete(k);
    },
    kvList: async (prefix) => [...mem.keys()].filter((k) => k.startsWith(prefix)),
    _mem: mem,
  };
}

export function memObjects() {
  const mem = new Map();
  return {
    objectGet: async (p) => (mem.has(p) ? { value: mem.get(p) } : null),
    objectPut: async (p, v) => {
      mem.set(p, v);
    },
    _mem: mem,
  };
}

/** R2-shaped bucket fake for the revisioned approvals contract.
 * Derived from the T07 QC harness bucket (W2A-T07-media-r1-qc/qc-media-check.mjs
 * memBucket) and shaped by exactly the calls approval-store.js makes:
 * get(path), put(path, body, { onlyIf, httpMetadata, sha256 }) and
 * list({ prefix, cursor, limit }). Nothing more. */
export function memR2Bucket() {
  const files = new Map();
  const enc = new TextEncoder();
  async function toBytes(body) {
    if (body instanceof ArrayBuffer) return new Uint8Array(body);
    if (ArrayBuffer.isView(body)) return new Uint8Array(body.buffer, body.byteOffset, body.byteLength);
    if (typeof body === 'string') return enc.encode(body);
    if (body && typeof body.arrayBuffer === 'function') return new Uint8Array(await body.arrayBuffer());
    return enc.encode(JSON.stringify(body));
  }
  return {
    _files: files,
    get: async (p) => {
      if (!files.has(p)) return null;
      const rec = files.get(p);
      return {
        body: rec.bytes,
        size: rec.bytes.byteLength,
        checksums: { sha256: rec.hex },
        httpEtag: '"etag"',
        httpMetadata: { contentType: rec.ctype },
        text: async () => new TextDecoder().decode(rec.bytes),
        json: async () => JSON.parse(new TextDecoder().decode(rec.bytes)),
        arrayBuffer: async () => rec.bytes.buffer.slice(rec.bytes.byteOffset, rec.bytes.byteOffset + rec.bytes.byteLength),
      };
    },
    put: async (p, body, opts = {}) => {
      const onlyIf = opts.onlyIf;
      let inm = null;
      if (onlyIf && typeof onlyIf.get === 'function') inm = onlyIf.get('If-None-Match');
      else if (onlyIf && typeof onlyIf === 'object') inm = onlyIf['If-None-Match'] || onlyIf['if-none-match'];
      if (inm === '*' && files.has(p)) return null;
      const bytes = await toBytes(body);
      const hx = createHash('sha256').update(bytes).digest('hex');
      if (opts.sha256 && String(opts.sha256).toLowerCase() !== hx) throw new Error('sha256 mismatch on put');
      files.set(p, { bytes, ctype: (opts.httpMetadata && opts.httpMetadata.contentType) || 'application/octet-stream', hex: hx });
      return { key: p };
    },
    list: async ({ prefix = '', cursor, limit = 1000 } = {}) => {
      const keys = [...files.keys()].filter((k) => k.startsWith(prefix)).sort();
      let start = 0;
      if (cursor !== undefined && cursor !== null) start = Number(cursor) || 0;
      const page = keys.slice(start, start + limit);
      const next = start + page.length;
      return { objects: page.map((key) => ({ key })), truncated: next < keys.length, cursor: next < keys.length ? String(next) : undefined };
    },
  };
}

/** A JSON POST, as the Worker sees it. */
export function post(path, body, key) {
  const headers = { 'content-type': 'application/json' };
  if (key) headers['x-ds-key'] = key;
  return new Request(`https://studio.example${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body || {}),
  });
}

export function get(path, key) {
  const headers = {};
  if (key) headers['x-ds-key'] = key;
  return new Request(`https://studio.example${path}`, { method: 'GET', headers });
}
