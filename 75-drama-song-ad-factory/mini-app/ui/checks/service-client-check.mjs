// =============================================================================
// RUNNABLE CHECK — the page's service client matches the SPEC route contract
// -----------------------------------------------------------------------------
// mini-app/ui/checks/service-client-check.mjs
//
// Imports the SHIPPED service-client.js in Node with a fake `location` and a
// fake `fetch`, and proves:
//   * a valid #k=<32 hex> fragment installs globalThis.studioService, a
//     malformed or absent key installs nothing;
//   * every request carries the key in the `x-ds-key` header and goes
//     same-origin (a relative path);
//   * every method hits the exact method + route of SPEC.md §4, with the
//     right JSON body;
//   * linkKey() and personalLink() read the fragment;
//   * a 409 answer rejects with the service's own code;
//   * listInbox/postInbox keep their "not built yet" answer.
//
// It does NOT drive a real browser or talk to the real service, so it cannot
// certify either; checks/README.md says so for every check in this folder.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/service-client-check.mjs
// =============================================================================
const KEY = "0123456789abcdef0123456789abcdef"; // 32 hex
const CLIENT_URL = "https://studio.example.com/";

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

const clientUrl = new URL("../service-client.js", import.meta.url).href;
let importCount = 0;

/** Import a fresh copy of the shipped module under a faked page. */
async function loadPage({ hash, answer }) {
  const calls = [];
  globalThis.location = { hash, origin: CLIENT_URL.replace(/\/$/, "") };
  globalThis.fetch = async (path, init = {}) => {
    calls.push({
      path: String(path),
      method: init.method || "GET",
      headers: init.headers || {},
      body: init.body ? JSON.parse(init.body) : undefined,
    });
    const out = (answer && answer(String(path))) || { ok: true };
    return { ok: out.status ? out.status < 400 : true, status: out.status || 200, json: async () => out };
  };
  delete globalThis.studioService;
  importCount += 1;
  return { api: await import(`${clientUrl}?v=${importCount}`), calls };
}

// ── 1. with a key: the service is installed, the header carries it ───────────
{
  const { api, calls } = await loadPage({ hash: `#k=${KEY}&p=home` });
  rule("linkKey() reads the fragment", api.linkKey() === KEY);
  rule("personalLink() rebuilds the link",
    api.personalLink() === `${CLIENT_URL}#k=${KEY}`);
  rule("a valid key installs studioService", !!globalThis.studioService);

  const svc = globalThis.studioService;
  const expect = async (label, method, path, run, body) => {
    calls.length = 0;
    await run();
    const c = calls[0];
    rule(`${label} → ${method} ${path}`,
      !!c && c.method === method && c.path === path,
      c ? `${c.method} ${c.path}` : "no fetch");
    if (c) rule(`${label} sends x-ds-key`, c.headers["x-ds-key"] === KEY,
      String(c.headers["x-ds-key"]));
    if (c) rule(`${label} goes same-origin`, !/^[a-z]+:/i.test(c.path), c.path);
    if (body !== undefined) rule(`${label} body`, JSON.stringify(c.body) === JSON.stringify(body),
      JSON.stringify(c.body));
  };

  await expect("getSession", "GET", "/api/studio/session", () => svc.getSession());
  await expect("saveDraft", "PUT", "/api/studio/draft",
    () => svc.saveDraft({ replies: ["1", "yes"] }), { replies: ["1", "yes"] });
  await expect("getQuestions", "GET", "/questions.json", () => svc.getQuestions());
  await expect("lockIn", "POST", "/api/studio/orders",
    () => svc.lockIn({ title: "Drama video", replies: ["1", "yes"], upload_ids: ["u_1"] }),
    { title: "Drama video", replies: ["1", "yes"], upload_ids: ["u_1"] });
  await expect("listApprovals", "GET", "/api/studio/orders/r_abc123/approvals",
    () => svc.listApprovals("r_abc123"));
  await expect("answerApproval", "POST", "/api/studio/orders/r_abc123/approvals/script/answer",
    () => svc.answerApproval("r_abc123", "script", 2, "approve"), { version: 2, value: "approve" });
  await expect("requestUpload", "POST", "/api/studio/uploads",
    () => svc.requestUpload({ channel: "photo", filename: "a.jpg", content_type: "image/jpeg", size_bytes: 12 }),
    { channel: "photo", filename: "a.jpg", content_type: "image/jpeg", size_bytes: 12 });
  await expect("getDelivery", "GET", "/api/studio/orders/r_abc123",
    () => svc.getDelivery("r_abc123"));

  // getDelivery unwraps order.delivery, and nothing there means null.
  calls.length = 0;
  globalThis.fetch = async (path, init = {}) => {
    calls.push({ path: String(path), method: init.method || "GET" });
    return { ok: true, status: 200, json: async () => ({ ok: true, order: { delivery: { url: "https://cdn.example.com/v.mp4", kind: "r2" } } }) };
  };
  const d = await svc.getDelivery("r_abc123");
  rule("getDelivery returns order.delivery", d && d.url === "https://cdn.example.com/v.mp4" && d.kind === "r2");
  globalThis.fetch = async (path, init = {}) => {
    calls.push({ path: String(path), method: init.method || "GET" });
    return { ok: true, status: 200, json: async () => ({ ok: true, order: {} }) };
  };
  rule("getDelivery is null before delivery", (await svc.getDelivery("r_abc123")) === null);

  // The out-of-scope inbox: one empty list, one refusal, no network at all.
  calls.length = 0;
  rule("listInbox resolves { messages: [] }",
    JSON.stringify(await svc.listInbox()) === '{"messages":[]}');
  const inboxErr = await svc.postInbox({ body: "hi" }).then(() => null, (e) => e);
  rule("postInbox refuses until it exists",
    !!inboxErr && /not available/i.test(inboxErr.message) && inboxErr.code === "STUDIO_INBOX_UNAVAILABLE",
    inboxErr ? inboxErr.message : "resolved");
  rule("the inbox never touches the network", calls.length === 0, `${calls.length} call(s)`);
}

// ── 2. a 409 rejects with the service's own code ─────────────────────────────
{
  await loadPage({
    hash: `#k=${KEY}`,
    answer: () => ({ ok: false, status: 409, code: "APPROVAL_ANSWER_TAKEN", message: "Already answered." }),
  });
  const err = await globalThis.studioService
    .answerApproval("r_abc123", "script", 1, "approve")
    .then(() => null, (e) => e);
  rule("a 409 rejects with the service's code",
    !!err && err.code === "APPROVAL_ANSWER_TAKEN" && err.message === "Already answered.",
    err ? `${err.code}: ${err.message}` : "resolved");
}

// ── 3. no key (or a malformed one) → nothing installed ───────────────────────
for (const [label, hash] of [
  ["no hash at all", ""],
  ["a hash without a key", "#p=questions"],
  ["a key of the wrong length", "#k=0123456789abcdef"],
  ["a key that is not hex", "#k=zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"],
]) {
  const { api } = await loadPage({ hash });
  rule(`${label} → studioService stays unset`, globalThis.studioService === undefined);
  rule(`${label} → linkKey() is null`, api.linkKey() === null);
  rule(`${label} → personalLink() is null`, api.personalLink() === null);
}

delete globalThis.studioService;
delete globalThis.location;
delete globalThis.fetch;

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\nservice-client check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\nservice-client check OK: ${results.length} rules passed (fake fetch/location, SPEC.md §4 routes)`);
process.exit(0);
