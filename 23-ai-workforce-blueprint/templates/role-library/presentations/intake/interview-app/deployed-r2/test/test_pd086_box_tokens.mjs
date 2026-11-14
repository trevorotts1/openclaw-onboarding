// PD-086 acceptance A1 — per-installation box credentials for the interview
// worker. A box token (its SHA-256 listed in INTAKE_BOX_TOKENS) is scoped to
// its own installation: it cannot list, fetch, mint or renew for another
// tenant; an unscoped list with a box token is 403; the admin token is
// unchanged. No token is ever printed by the worker or this test.
//
//   node --test deployed-r2/test/test_pd086_box_tokens.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { R2Shim, WorkerHarness, PAYLOAD } from "../../test/pres024_env.mjs";
import worker from "../src/index.js";

const ADMIN = "admin-tok";
const TOK_A = "box-token-install-a-0000000000000000";
const TOK_B = "box-token-install-b-1111111111111111";
const TOK_C = "box-token-install-c-2222222222222222";
const sha256 = (s) => createHash("sha256").update(String(s)).digest("hex");

function makeEnv(extra = {}) {
  return {
    STORE: new R2Shim(),
    INTAKE_ADMIN_TOKEN: ADMIN,
    INTAKE_BOX_TOKENS: JSON.stringify({
      "install-a": sha256(TOK_A),
      "install-b": sha256(TOK_B),
      "install-c": { sha256: sha256(TOK_C), company_id: "co-c" },
    }),
    ...extra,
  };
}

async function mint(h, token, { company = "acme", installation = "install-a", runId = "run-1" } = {}) {
  return h.handle("POST", "/api/sessions", {
    token,
    body: {
      run_id: runId, box_id: "box1", questions_payload: PAYLOAD,
      company_id: company, installation_id: installation,
      presentation_id: "presentation-test", recipient_chat_id: "111",
    },
  });
}

test("PD-086 A1: a box token cannot mint, renew, list or fetch for another installation; unscoped list is 403; admin unchanged", async () => {
  const env = makeEnv();
  const h = new WorkerHarness(worker, env);

  // Box A mints for its own installation — allowed.
  let r = await mint(h, TOK_A, { installation: "install-a" });
  assert.equal(r.status, 201, "box A mints for A: " + JSON.stringify(r.body));
  const sessionA = r.body;

  // Box A minting for B — refused.
  r = await mint(h, TOK_A, { installation: "install-b", runId: "run-b-mint" });
  assert.equal(r.status, 403, "box A mint for B refused");
  assert.match(r.body.error, /installation/);

  // An admin-minted session for B, the target of the cross-tenant attempts.
  r = await mint(h, ADMIN, { installation: "install-b", runId: "run-b" });
  assert.equal(r.status, 201, "admin mints for B");
  const sessionB = r.body;

  // Box A renewing B's session — refused (and B's session is untouched).
  r = await h.handle("POST", "/api/sessions/renew", { token: TOK_A, body: { session_id: sessionB.session_id, company_id: "acme" } });
  assert.equal(r.status, 403, "box A renew for B refused");

  // Box A renewing its OWN session — allowed.
  r = await h.handle("POST", "/api/sessions/renew", { token: TOK_A, body: { session_id: sessionA.session_id, company_id: "acme" } });
  assert.equal(r.status, 201, "box A renew for A: " + JSON.stringify(r.body));

  // Box A listing B's index — refused.
  r = await h.handle("GET", "/api/intake/list?company_id=acme&installation_id=install-b", { token: TOK_A });
  assert.equal(r.status, 403, "box A list for B refused");

  // Unscoped list with a box token — refused.
  r = await h.handle("GET", "/api/intake/list", { token: TOK_A });
  assert.equal(r.status, 403, "unscoped list with box token refused");

  // Box A listing its own index — allowed.
  r = await h.handle("GET", "/api/intake/list?company_id=acme&installation_id=install-a", { token: TOK_A });
  assert.equal(r.status, 200, "box A scoped list allowed: " + JSON.stringify(r.body));

  // Box A fetching for B / unscoped — refused; own scope reaches storage (404).
  r = await h.handle("GET", "/api/intake?id=abc123&company_id=acme&installation_id=install-b", { token: TOK_A });
  assert.equal(r.status, 403, "box A fetch for B refused");
  r = await h.handle("GET", "/api/intake?id=abc123", { token: TOK_A });
  assert.equal(r.status, 403, "unscoped fetch with box token refused");
  r = await h.handle("GET", "/api/intake?id=abc123&company_id=acme&installation_id=install-a", { token: TOK_A });
  assert.equal(r.status, 404, "box A fetch in own scope reaches storage");

  // Admin is unchanged: unscoped list, unscoped fetch, cross-installation mint.
  r = await h.handle("GET", "/api/intake/list", { token: ADMIN });
  assert.equal(r.status, 200, "admin unscoped list unchanged");
  r = await h.handle("GET", "/api/intake?id=abc123", { token: ADMIN });
  assert.equal(r.status, 404, "admin unscoped fetch still reaches storage");
  r = await mint(h, ADMIN, { installation: "install-c", company: "co-c", runId: "run-admin-c" });
  assert.equal(r.status, 201, "admin mint for any installation unchanged");

  // An unknown bearer is still 401 and never treated as a box.
  r = await h.handle("GET", "/api/intake/list", { token: "not-a-real-token-333333333333333" });
  assert.equal(r.status, 401, "unknown token is 401");
  r = await h.handle("GET", "/api/intake/list");
  assert.equal(r.status, 401, "no token is 401");

  // A company-bound box entry also pins the company.
  r = await mint(h, TOK_C, { installation: "install-c", company: "co-c", runId: "run-c-ok" });
  assert.equal(r.status, 201, "company-bound box mints in its own company");
  r = await mint(h, TOK_C, { installation: "install-c", company: "acme", runId: "run-c-bad" });
  assert.equal(r.status, 403, "company-bound box refused for another company");
});
