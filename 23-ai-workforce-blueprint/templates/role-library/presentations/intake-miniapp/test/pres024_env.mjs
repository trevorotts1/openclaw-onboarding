// PRES-024 offline integration harness — a real SQLite (node:sqlite) database
// behind a D1-shaped shim, an in-memory R2-shaped store, and a worker fetch
// driver. This is NOT the Cloudflare runtime: it exercises the worker's actual
// route/response code against a real SQL engine executing the real schema.
//   node --test <this dir's pres024 test files>
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));

export function nowSecondsFixed(t) { return t; }

/**
 * D1 shim over node:sqlite. Implements exactly the surface the workers use:
 * prepare().bind().first()/.all()/.run(), .batch([stmts]), .exec(sql).
 * Returns plain rows; booleans/numbers come back as SQLite stores them.
 */
export class D1Shim {
  constructor(db) {
    this.db = db;
    this._lastId = 0;
    this._lastIdMap = new Map();
  }

  prepare(sql) {
    const shim = this;
    return {
      sql,
      _args: [],
      bind(...args) { this._args = args.map(normalize); return this; },
      async first() {
        const stmt = shim.db.prepare(this.sql);
        const rows = stmt.all(...this._args);
        return rows.length ? rows[0] : null;
      },
      async all() {
        const stmt = shim.db.prepare(this.sql);
        const rows = stmt.all(...this._args);
        return { results: rows };
      },
      async run() {
        const stmt = shim.db.prepare(this.sql);
        const info = stmt.run(...this._args);
        return { success: true, meta: { changes: Number(info.changes), last_row_id: Number(info.lastInsertRowid) } };
      },
    };
  }

  async batch(stmts) {
    // D1 batch = implicit transaction: all-or-nothing. node:sqlite has no
    // autocommit control per statement here, so wrap in an explicit tx.
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const out = [];
      for (const s of stmts) {
        const stmt = this.db.prepare(s.sql);
        const info = stmt.run(...s._args);
        out.push({ success: true, meta: { changes: Number(info.changes) } });
      }
      this.db.exec("COMMIT");
      return out;
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }

  async exec(sql) { this.db.exec(sql); }
}

function normalize(v) {
  if (v === undefined) return null;
  if (typeof v === "boolean") return v ? 1 : 0;
  return v;
}

/** Apply a schema.sql (or migration) file to a fresh in-memory DB. */
export function makeDb(schemaPaths) {
  const db = new DatabaseSync(":memory:");
  db.exec("PRAGMA foreign_keys = OFF"); // ALTER TABLE backfills update sessions first
  for (const p of schemaPaths) {
    db.exec(readFileSync(p, "utf8"));
  }
  return db;
}

/**
 * In-memory R2 shim: get/put/list with prefix + JSON body text, exactly the
 * surface the R2 worker uses (STORE.put/get(key).text()).
 */
export class R2Shim {
  constructor() { this.map = new Map(); }
  async put(key, value) {
    this.map.set(key, typeof value === "string" ? value : String(value));
    return { key };
  }
  async get(key) {
    const v = this.map.get(key);
    if (v === undefined) return null;
    return { key, async text() { return v; } };
  }
  async list({ prefix = "" } = {}) {
    const objects = [...this.map.keys()].filter((k) => k.startsWith(prefix)).map((k) => ({ key: k }));
    return { objects };
  }
}

/** Minimal Request/Response driver around the worker's default export. */
export class WorkerHarness {
  constructor(worker, env) {
    this.worker = worker;
    this.env = env;
  }

  async handle(method, path, { token = null, body = null } = {}) {
    const headers = {};
    if (token) headers.authorization = "Bearer " + token;
    const req = new Request("https://pres024.test" + path, {
      method,
      headers,
      body: body === null ? undefined : (typeof body === "string" ? body : JSON.stringify(body)),
    });
    const res = await this.worker.fetch(req, this.env, {});
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { json = { raw: text }; }
    return { status: res.status, ok: res.ok, body: json };
  }
}

export const PAYLOAD = {
  question_set: "standard",
  questions: [
    { id: "offer_name", order: 1, prompt: "Your offer?", kind: "text", required: true, storeOn: "deck_brief.OFFER_NAME" },
    { id: "tone", order: 7, prompt: "Tone?", kind: "text", required: true },
    { id: "speech_speed_preference", order: 9, prompt: "Pace?", kind: "enum", required: true, allowed_values: ["default", "medium", "fast"] },
    { id: "want_sales_checkout", order: 10, prompt: "Sales page?", kind: "enum", required: true, allowed_values: ["yes", "no"] },
    { id: "client_notes", order: 12, prompt: "Notes?", kind: "text", required: false, default: "" },
  ],
};

export const HERE_PATH = HERE;