// ============================================================================
// Book Writer mini-app — U18 e2e in-memory KV/R2 store (offline)
// ----------------------------------------------------------------------------
// Mirrors the Cloudflare KV/R2 binding surface the real Worker (U02/U03/U11)
// expects, so the harness can drive the REAL production modules (answers.js,
// save.js, lib.js) against an in-memory store instead of re-implementing their
// rules. Two distinct contracts are exposed:
//
//   kv.*            — Cloudflare-style KV (answers.js / save.js surface):
//                     get(key,{type:'json'}) / put(key,string) / list({prefix})
//   store.*         — U02 lib.js adapter surface: kvGet / kvPut / incr /
//                     objectGet (R2-backed config + shell reads)
//
// No real zone/account ids. No credentials. Fictitious clients only.
// ============================================================================

export class MemoryKV {
  constructor() {
    this.kv = new Map();
    this.objects = new Map(); // R2-style objects (value string)
    this.counters = new Map();
  }

  // ---- Cloudflare-style KV (used by answers.js / save.js) --------------------
  async get(key, opts = {}) {
    const raw = this.kv.has(key) ? this.kv.get(key) : null;
    if (raw === null || raw === undefined) return null;
    if (opts && opts.type === 'json') {
      try { return JSON.parse(raw); } catch { return null; }
    }
    return raw;
  }

  async put(key, value) {
    this.kv.set(key, String(value));
  }

  async delete(key) {
    this.kv.delete(key);
  }

  async list(opts = {}) {
    const prefix = opts.prefix || '';
    const keys = [];
    for (const k of this.kv.keys()) {
      if (k.startsWith(prefix)) keys.push({ name: k });
    }
    return { keys };
  }

  // ---- U02 lib.js adapter surface -------------------------------------------
  async kvGet(key) { return this.kv.has(key) ? this.kv.get(key) : null; }
  async kvPut(key, val) { this.kv.set(key, val); }
  async incr(key) {
    const next = (this.counters.get(key) || 0) + 1;
    this.counters.set(key, next);
    return next;
  }

  async objectGet(path) {
    return this.objects.has(path) ? { value: this.objects.get(path) } : null;
  }
  seedObject(path, value) { this.objects.set(path, JSON.stringify(value)); }
  seedObjectRaw(path, raw) { this.objects.set(path, raw); }

  // ---- e2e reset: clear runtime rows, keep seeded bindings/configs -----------
  async resetRuntime() {
    this.counters.clear();
    for (const k of [...this.kv.keys()]) {
      const keep =
        k.startsWith('binding:') ||   // answers.js / save.js token binding
        k.startsWith('tk:') ||        // lib.js token binding (same row, both keyed)
        k.startsWith('run:') ||       // run state
        k.startsWith('app:') ||       // R2 app shell pointer (object store, not kv)
        k.startsWith('config:');      // R2 config pointer (object store, not kv)
      if (!keep) this.kv.delete(k);
    }
  }
}
