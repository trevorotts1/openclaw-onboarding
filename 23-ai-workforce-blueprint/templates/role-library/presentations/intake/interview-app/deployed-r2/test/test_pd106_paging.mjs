// PD-106 gate — the session scans follow R2 paging. `latestGrantFor` and
// `refreshRunIndexFor` used to read ONE list() page, so with a busy bucket the
// newest grant could sit past page one and a renew would answer "not found".
//
//   node --test deployed-r2/test/test_pd106_paging.mjs
//
// Rows:
//   A1c  1,200 stored sessions, newest grant last in key order -> renew 201,
//        same session_id, next revision, and the run index rebuilt from every
//        page (a fresh grant token is in the index)
//   A1d  control: a shim that returns only an unpaged first page -> renew 404
//        (proves the row above discriminates — the old code failed here)
import { test } from "node:test";
import assert from "node:assert/strict";
import { R2Shim, PAYLOAD } from "../../test/pres024_env.mjs";
import worker from "../src/index.js";

const DECOYS = 1199;              // + 2 grants for the target = 1,201 sessions
const TARGET_SESSION = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"; // 32 hex, per isValidSessionIdShape
const OLDER_TOKEN = "fffffffffffffffffffffffffffffffe";
const NEWEST_TOKEN = "ffffffffffffffffffffffffffffffff";
const QJSON = JSON.stringify(PAYLOAD);

/** R2 whose list() pages at `pageSize`, reporting truncated + cursor as R2 does. */
class PagingShim extends R2Shim {
  constructor(pageSize = 100) {
    super();
    this.pageSize = pageSize;
    this.pages = 0;
    this.cursorPages = 0;
  }
  async list({ prefix = "", cursor } = {}) {
    this.pages += 1;
    if (cursor) this.cursorPages += 1;
    const keys = [...this.map.keys()].filter((k) => k.startsWith(prefix)).sort();
    const rest = cursor ? keys.filter((k) => k > cursor) : keys;
    const objects = rest.slice(0, this.pageSize).map((k) => ({ key: k }));
    const truncated = rest.length > this.pageSize;
    return truncated
      ? { objects, truncated: true, cursor: objects[objects.length - 1].key }
      : { objects, truncated: false };
  }
}

/** The pre-PD-106 shape: one call, first page only, no truncated flag. */
class OnePageShim extends R2Shim {
  async list({ prefix = "" } = {}) {
    const keys = [...this.map.keys()].filter((k) => k.startsWith(prefix)).sort();
    return { objects: keys.slice(0, 1000).map((k) => ({ key: k })) };
  }
}

function seed(store) {
  for (let i = 1; i <= DECOYS; i += 1) {
    const token = i.toString(16).padStart(32, "0");
    store.map.set(`sessions/${token}.json`, JSON.stringify({
      token, session_id: `sess-decoy-${i}`, run_id: `run-decoy-${i}`, status: "open",
      company_id: "decoy-co", revision: 1, created_at: 1000, expires_at: 4102444800,
      questions_json: QJSON,
    }));
  }
  // Older grant, then the newest grant — both sort after every decoy key.
  store.map.set(`sessions/${OLDER_TOKEN}.json`, JSON.stringify({
    token: OLDER_TOKEN, session_id: TARGET_SESSION, run_id: "run-pd106", status: "renewed",
    company_id: "acme", revision: 1, created_at: 2000, expires_at: 4102444800,
    questions_json: QJSON,
  }));
  store.map.set(`sessions/${NEWEST_TOKEN}.json`, JSON.stringify({
    token: NEWEST_TOKEN, session_id: TARGET_SESSION, run_id: "run-pd106", status: "open",
    company_id: "acme", revision: 2, created_at: 3000, expires_at: 4102444800,
    questions_json: QJSON,
  }));
}

async function renew(store) {
  const env = { STORE: store, INTAKE_ADMIN_TOKEN: "admin-tok" };
  const req = new Request("https://pd106.test/api/sessions/renew", {
    method: "POST",
    headers: { authorization: "Bearer admin-tok", "content-type": "application/json" },
    body: JSON.stringify({ session_id: TARGET_SESSION, company_id: "acme" }),
  });
  const res = await worker.fetch(req, env, {});
  return { status: res.status, body: JSON.parse(await res.text()) };
}

test("PD-106 A1c: 1,200 stored sessions — renew still finds the newest grant", async () => {
  const store = new PagingShim(100);
  seed(store);
  const r = await renew(store);
  assert.equal(r.status, 201, JSON.stringify(r.body));
  assert.equal(r.body.session_id, TARGET_SESSION, "same stable identity");
  assert.equal(r.body.revision, 3, "continues past the newest grant's revision 2");
  assert.notEqual(r.body.token, NEWEST_TOKEN, "a fresh grant was minted");
  assert.ok(store.cursorPages > 0, "the scan followed the cursor: " + store.cursorPages);

  const idx = JSON.parse(store.map.get("runs/run-pd106.json"));
  assert.ok(Array.isArray(idx) && idx.some((row) => row.token === r.body.token),
    "run index rebuilt from every page, not just the first");
});

test("PD-106 A1d control: an unpaged first-page-only bucket answers 404", async () => {
  const store = new OnePageShim();
  seed(store);
  const r = await renew(store);
  assert.equal(r.status, 404, "the old one-call scan cannot see the newest grant: " + JSON.stringify(r.body));
});
