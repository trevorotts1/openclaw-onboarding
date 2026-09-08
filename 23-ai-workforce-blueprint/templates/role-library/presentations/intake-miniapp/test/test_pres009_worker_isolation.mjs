// PRES-009 — worker isolation integration tests against the REAL handlers
// with better-sqlite3 standing in for D1 (same SQL, real engine). No
// Cloudflare runtime, no network.
//   node --test test/test_pres009_worker_isolation.mjs
//
// What is proven (QC-PRES-009 §1):
//   - two companies reusing one human run name get DISTINCT tokens/data
//   - one company launching two simultaneous decks shares nothing
//   - foreign tokens / forged tuples are rejected
//   - traversal-shaped and collision ids are rejected, never sanitized
//   - restart preserves bindings (same store re-served)
//   - valid own-client session resumes; quarantined legacy rows stay withheld

import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
// better-sqlite3 is not a dependency of the skill template; resolve it from
// the CC checkout's node_modules when present (the same engine production D1
// semantics are validated against in the CC test suites).
const CC_BSQLITE = "/Users/blackceomacmini/blackceo-command-center/node_modules/better-sqlite3";
let Database;
try {
  Database = require("better-sqlite3");
} catch {
  Database = require(CC_BSQLITE);
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MINIAPP_WORKER = await import("../worker/src/index.js");
const R2_WORKER = await import("../../intake/interview-app/deployed-r2/src/index.js");

// ── D1 stand-in over better-sqlite3 (real SQL semantics) ───────────────────

class D1Stmt {
  constructor(db, sql, params = []) { this.db = db; this.sql = sql; this.params = params; }
  bind(...params) { return new D1Stmt(this.db, this.sql, params); }
  first() {
    const row = this.db.prepare(this.sql).get(...this.params);
    if (row === undefined) return null;
    return row;
  }
  all() { return { results: this.db.prepare(this.sql).all(...this.params) }; }
  run() { this.db.prepare(this.sql).run(...this.params); return { success: true }; }
}

class D1 {
  constructor() {
    this.db = new Database(":memory:");
    this.db.exec(`
      CREATE TABLE sessions (
        token TEXT PRIMARY KEY, run_id TEXT NOT NULL, display_name TEXT, box_id TEXT,
        question_set TEXT, questions_json TEXT, confirm_code TEXT,
        company_id TEXT, installation_id TEXT, presentation_id TEXT,
        intake_session_id TEXT, schema_fp TEXT,
        tenant_state TEXT DEFAULT 'active', quarantine_reason TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, completed_at INTEGER
      );
      CREATE TABLE answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT NOT NULL, question_id TEXT NOT NULL, value TEXT NOT NULL,
        created_at INTEGER NOT NULL, UNIQUE (token, question_id)
      );
      CREATE TABLE intakes (
        session_id TEXT PRIMARY KEY, file_name TEXT NOT NULL, intake_json TEXT NOT NULL,
        company_id TEXT, installation_id TEXT, presentation_id TEXT, run_id TEXT,
        tenant_state TEXT DEFAULT 'active', quarantine_reason TEXT, quarantine_remediation TEXT,
        created_at INTEGER NOT NULL, updated_at INTEGER
      );
    `);
  }
  prepare(sql) { return new D1Stmt(this.db, sql); }
  exec(sql) { this.db.exec(sql); }
}

function makeEnv({ admin = "test-admin-token-0001" } = {}) {
  return { DB: new D1(), INTAKE_ADMIN_TOKEN: admin };
}

// ── R2 store stand-in ───────────────────────────────────────────────────────

class MemR2 {
  constructor() { this.map = new Map(); }
  async put(key, value) { this.map.set(key, value); }
  async get(key) {
    const v = this.map.get(key);
    if (v === undefined) return null;
    return { text: async () => v };
  }
  async list({ prefix }) {
    const objects = [...this.map.keys()].filter((k) => k.startsWith(prefix)).map((key) => ({ key }));
    return { objects };
  }
}

function makeR2Env({ admin = "test-admin-token-0002" } = {}) {
  return { STORE: new MemR2(), ASSETS: null, INTAKE_ADMIN_TOKEN: admin };
}

function req(url, { method = "GET", body, token } = {}) {
  return new Request(url, {
    method,
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: "Bearer " + token } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
}

const PAYLOAD = {
  question_set: "standard",
  questions: [
    { id: "offer_name", order: 1, prompt: "Offer?", kind: "text", required: true },
    { id: "tone", order: 2, prompt: "Tone?", kind: "text", required: true },
  ],
};

const CO_A = "company-alpha", CO_B = "company-beta";
const INST_A = "inst-alpha-01", INST_B = "inst-beta-01";
const RUN_NAME = "summer-launch"; // human name both companies "reuse"

function mintBody(over = {}) {
  return {
    run_id: RUN_NAME, box_id: "box-test-01",
    company_id: CO_A, installation_id: INST_A, presentation_id: "deck-main-01",
    questions_payload: PAYLOAD, ...over,
  };
}

async function mint(worker, env, body) {
  const res = await worker.default.fetch(req("https://w.test/api/sessions", { method: "POST", body, token: env.INTAKE_ADMIN_TOKEN }), env);
  return { status: res.status, json: await res.json() };
}

// ── Both worker shapes: identical contract assertions ───────────────────────

for (const [label, makeTestEnv, worker] of [
  ["D1 miniapp worker", makeEnv, MINIAPP_WORKER],
  ["R2 deployed worker", makeR2Env, R2_WORKER],
]) {
  test(`[${label}] two companies reusing one human run name get distinct tokens and data`, async () => {
    const env = makeTestEnv();
    const a = await mint(worker, env, mintBody({ company_id: CO_A, installation_id: INST_A }));
    const b = await mint(worker, env, mintBody({ company_id: CO_B, installation_id: INST_B }));
    assert.equal(a.status, 201);
    assert.equal(b.status, 201);
    assert.ok(a.json.token && b.json.token);
    assert.notEqual(a.json.token, b.json.token, "tokens must differ across companies");
    assert.notEqual(a.json.run_id, b.json.run_id, "minted run ids must differ");
    assert.equal(a.json.company_id, CO_A);
    assert.equal(b.json.company_id, CO_B);
  });

  test(`[${label}] one company launching two simultaneous decks shares nothing`, async () => {
    const env = makeTestEnv();
    const deck1 = await mint(worker, env, mintBody({ presentation_id: "deck-one-01" }));
    const deck2 = await mint(worker, env, mintBody({ presentation_id: "deck-two-02" }));
    assert.equal(deck1.status, 201);
    assert.equal(deck2.status, 201);
    assert.notEqual(deck1.json.token, deck2.json.token);
    assert.notEqual(deck1.json.run_id, deck2.json.run_id);
    assert.notEqual(deck1.json.presentation_id, deck2.json.presentation_id);
  });

  test(`[${label}] exact tuple + compatible schema reuses the SAME open session (link reuse)`, async () => {
    const env = makeTestEnv();
    const first = await mint(worker, env, mintBody());
    const again = await mint(worker, env, mintBody());
    assert.equal(again.json.status, "exists");
    assert.equal(again.json.token, first.json.token);
  });

  test(`[${label}] same tuple but different question schema mints a NEW session`, async () => {
    const env = makeTestEnv();
    const first = await mint(worker, env, mintBody());
    const changedPayload = {
      question_set: "standard",
      questions: [
        ...PAYLOAD.questions,
        { id: "audience", order: 3, prompt: "Who?", kind: "text", required: true },
      ],
    };
    const second = await mint(worker, env, mintBody({ questions_payload: changedPayload }));
    assert.equal(second.status, 201);
    assert.ok(second.json.token !== first.json.token, "schema change must not reuse the link");
  });

  test(`[${label}] missing/invalid tenant fields are rejected precisely (never sanitized)`, async () => {
    const env = makeTestEnv();
    for (const bad of [
      mintBody({ company_id: undefined }),
      mintBody({ company_id: "../escape" }),
      mintBody({ installation_id: "a/b" }),
      mintBody({ presentation_id: ".." }),
      mintBody({ company_id: 42 }),
    ]) {
      const res = await mint(worker, env, bad);
      assert.equal(res.status, 400, "invalid tenant must 400: " + JSON.stringify(res.json));
      assert.match(String(res.json.error || ""), /tenant/i);
    }
  });

  test(`[${label}] foreign/forged capability tokens are rejected`, async () => {
    const env = makeTestEnv();
    await mint(worker, env, mintBody());
    const res = await worker.default.fetch(req("https://w.test/api/sessions/00000000000000000000000000000000"), env);
    assert.equal(res.status, 404, "unknown token must 404");
    const badShape = await worker.default.fetch(req("https://w.test/api/sessions/%2e%2e%2f%2e%2e%2fetc00"), env);
    assert.equal(badShape.status, 400, "traversal-shaped token must be a 400, never a lookup");
  });

  test(`[${label}] restart preserves bindings (same store re-served)`, async () => {
    const env = makeTestEnv();
    const first = await mint(worker, env, mintBody());
    // Simulate a worker restart: the SAME env (storage) is handed to a fresh fetch.
    const resumed = await worker.default.fetch(req(`https://w.test/api/sessions/${first.json.token}`), env);
    assert.equal(resumed.status, 200);
    const body = await resumed.json();
    assert.equal(body.run_id, first.json.run_id);
    assert.equal(body.company_id, CO_A);
    assert.equal(body.installation_id, INST_A);
    assert.equal(body.presentation_id, "deck-main-01");
    // And reuse still resolves to the same session after restart.
    const again = await mint(worker, env, mintBody());
    assert.equal(again.json.status, "exists");
    assert.equal(again.json.token, first.json.token);
  });

  test(`[${label}] quarantined legacy session is withheld (423), other sessions unaffected`, async () => {
    const env = makeTestEnv();
    if (env.DB) {
      // Seed an ambiguous legacy row the way the pre-PRES-009 worker left it.
      env.DB.db.prepare(
        "INSERT INTO sessions (token, run_id, box_id, question_set, questions_json, tenant_state, quarantine_reason, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, 'quarantined', 'ambiguous_legacy_run_reused_across_boxes', 'open', 1, 99999999999)",
      ).run("f".repeat(32), "legacy-run", "box-a", "standard", JSON.stringify(PAYLOAD));
      const res = await worker.default.fetch(req(`https://w.test/api/sessions/${"f".repeat(32)}`), env);
      assert.equal(res.status, 423, "quarantined session must be withheld, not served to any company");
    } else {
      // R2 shape: no flat-file legacy path in this test; assert the API still
      // answers a foreign well-shaped token with 404 (never a partial view).
      const res = await worker.default.fetch(req(`https://w.test/api/sessions/${"f".repeat(32)}`), env);
      assert.equal(res.status, 404);
    }
    // A normal minted session keeps working on the same store.
    const healthy = await mint(worker, env, mintBody());
    assert.equal(healthy.status, 201);
  });

  test(`[${label}] answers never cross sessions of another company`, async () => {
    const env = makeTestEnv();
    const a = await mint(worker, env, mintBody({ company_id: CO_A, installation_id: INST_A }));
    const b = await mint(worker, env, mintBody({ company_id: CO_B, installation_id: INST_B }));
    const post = (token, body) => worker.default.fetch(
      req(`https://w.test/api/sessions/${token}/answers`, { method: "POST", body }), env);
    const ra = await post(a.json.token, { question_id: "offer_name", value: "Alpha offer" });
    assert.equal(ra.status, 200);
    const rb = await post(b.json.token, { question_id: "offer_name", value: "Beta offer" });
    assert.equal(rb.status, 200);
    const pa = await (await worker.default.fetch(req(`https://w.test/api/sessions/${a.json.token}/answers`), env)).json();
    const pb = await (await worker.default.fetch(req(`https://w.test/api/sessions/${b.json.token}/answers`), env)).json();
    assert.equal(pa.answers.length, 1);
    assert.equal(pa.answers[0].value, "Alpha offer");
    assert.equal(pb.answers.length, 1);
    assert.equal(pb.answers[0].value, "Beta offer");
  });
}

// ── R2-specific: intake keys and run indexes ────────────────────────────────

test("[R2 deployed worker] intake storage keys on the tenant tuple; traversal ids are refused", async () => {
  const env = makeR2Env();
  const admin = env.INTAKE_ADMIN_TOKEN;
  const storeIntake = (body) => R2_WORKER.default.fetch(
    req("https://w.test/api/intake", { method: "POST", body, token: admin }), env);
  const good = {
    file_name: "intake.json",
    intake: {
      intake_session_id: "isn-abc123", company_id: CO_A, installation_id: INST_A,
      presentation_id: "deck-main-01", run_id: "run-x12345",
      deck_brief: { OFFER_NAME: "O", NAMED_METHODOLOGY: "M", TRANSFORMATION_PROMISE: "P", TIME_TO_RESULT: "T", AUDIENCE: "A", CTA_ACTION: "C", TONE: "T2", FINAL_PRICE: "F", WANT_SALES_CHECKOUT: "no", WANT_VSL_PAGE: "no" },
      pre_presentation_capture: { PRESENTATION_TYPE: "signature" },
    },
  };
  const okRes = await storeIntake(good);
  assert.equal(okRes.status, 201);
  // Exactly one object, at the tenant-tuple key.
  assert.equal(env.STORE.map.size, 1);
  const [key] = [...env.STORE.map.keys()];
  assert.equal(key, "intakes/company-alpha/inst-alpha-01/deck-main-01/run-x12345/isn-abc123.json");

  // Traversal company id: refused, never stored under a sanitized key.
  const evil = JSON.parse(JSON.stringify(good));
  evil.intake.company_id = "../../victim";
  const evilRes = await storeIntake(evil);
  assert.equal(evilRes.status, 400);
  assert.equal(env.STORE.map.size, 1, "no new object may be written");

  // Distinct session id never collapses onto the first key (the old strip-
  // characters intakeKey let "a b" and "ab" collide).
  const other = JSON.parse(JSON.stringify(good));
  other.intake.intake_session_id = "isn-abc124";
  await storeIntake(other);
  assert.equal(env.STORE.map.size, 2, "distinct ids must be distinct keys");
});

test("[R2 deployed worker] run index keys include the tenant tuple; two companies never share an index", async () => {
  const env = makeR2Env();
  const a = await mint(R2_WORKER, env, mintBody({ company_id: CO_A, installation_id: INST_A }));
  const b = await mint(R2_WORKER, env, mintBody({ company_id: CO_B, installation_id: INST_B }));
  assert.equal(a.status, 201);
  assert.equal(b.status, 201);
  const keys = [...env.STORE.map.keys()].filter((k) => k.startsWith("runs/"));
  assert.equal(keys.length, 2, "two run indexes, one per tenant tuple");
  assert.ok(keys.every((k) => k.includes(CO_A) || k.includes(CO_B)));
  assert.ok(!keys.some((k) => k === "runs/summer-launch.json"), "no bare human-name index may exist");
});