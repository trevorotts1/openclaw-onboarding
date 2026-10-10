// ============================================================================
// fakes.mjs — in-memory adapters for the Drama Studio service tests/prover.
//
// The service takes its KV and object stores as INJECTED adapters (never a
// binding), which is what makes every rule here testable with no Cloudflare
// account, no network and no credentials. These fakes are the same shapes
// index.js's kvStore/r2Store produce.
// ============================================================================

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
