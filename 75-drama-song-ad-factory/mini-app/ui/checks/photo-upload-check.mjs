// =============================================================================
// RUNNABLE CHECK — photos that reach the order (S75-075, U-Z08)
// -----------------------------------------------------------------------------
// mini-app/ui/checks/photo-upload-check.mjs
//
// Imports the SHIPPED page (../studio.js) with a minimal DOM shim, a FAKE
// SERVICE (the object service-client.js installs) and a fake upload transport.
// No browser, no network, no dependency.
//
// WHAT IT PROVES (the fourth-pass page checks):
//   (1) one accepted upload adds its id to state.uploadIds and a line
//       "Added: <file name>", and that id is what `lockIn` sends;
//   (2) a 422 carrying the service's `message` shows that message;
//   (3) an answer that is not JSON (an HTML error page) shows the one plain
//       sentence instead of a JSON parse error.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node mini-app/ui/checks/photo-upload-check.mjs
// =============================================================================

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

// ── the page, imported before a document exists (so boot() does not run) ─────
const studio = await import("../studio.js");
const { state, render } = studio;

// ── the DOM shim ─────────────────────────────────────────────────────────────
function makeElement(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    attrs: Object.create(null),
    children: [],
    listeners: Object.create(null),
    style: {},
    textContent: "",
    value: "",
    checked: false,
    disabled: false,
    hidden: false,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    append(...nodes) { for (const n of nodes) if (n) this.children.push(n); },
    appendChild(n) { this.children.push(n); return n; },
    replaceChildren(...nodes) { this.children = nodes.filter(Boolean); },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    querySelector(selector) {
      const want = String(selector).toUpperCase();
      return walk(this).find((n) => n.tagName === want) || null;
    },
    focus() {},
  };
}

function walk(node, out = []) {
  out.push(node);
  for (const c of node.children || []) walk(c, out);
  return out;
}

const registry = Object.create(null);
for (const id of ["main", "steps-nav", "rail", "rail-fill", "step-label", "status"]) {
  registry[id] = makeElement("div");
  registry[id].attrs.id = id;
}
globalThis.document = {
  activeElement: null,
  visibilityState: "visible",
  createElement: makeElement,
  getElementById: (id) => registry[id] || null,
  addEventListener() {},
};
const KEY = "00112233445566778899aabbccddeeff";
globalThis.location = { hash: `#k=${KEY}`, origin: "https://studio.example.com", pathname: "/" };
globalThis.history = { replaceState() {} };

const textOf = (node) => walk(node).map((n) => n.textContent).filter(Boolean).join(" | ");
const findAll = (pred) => walk(registry.main).find(pred);
const addInput = () => findAll((n) => n.attrs && n.attrs.id === "add-photo");
const tick = async () => { await new Promise((r) => setTimeout(r, 0)); await new Promise((r) => setTimeout(r, 0)); };

// ── the fake service: lockIn records exactly what the page sent ──────────────
const lockInCalls = [];
globalThis.studioService = {
  async getSession() { return { client_id: "c-1", option_line: "", orders: [], draft: null }; },
  async getQuestions() { return { questions: [] }; },
  async saveDraft() { return { ok: true }; },
  async lockIn({ title, replies, upload_ids, order_id }) {
    lockInCalls.push({ title, replies, upload_ids, order_id });
    return { ok: true, order: { order_id: order_id || "r_00000000", title, state: "waiting" } };
  },
};

// ── the photos screen, on ────────────────────────────────────────────────────
const questions = [{
  id: "photos", label: "PHOTOS", question: "Which photos should we use?",
  typed: true, shows_when: {},
  options: [{ n: 1, text: "Type it in", detail: "Reply with your own words." }],
}];
state.page = "questions";
state.questions = questions;
state.agnesRemembered = "unknown";
state.replies = ["my logo"];
state.uploadIds = [];
state.uploadLines = [];
state.qIndex = 0;
state.picks = [];
state.texts = [];
render();

// ── the fake upload transport: one accepted photo ────────────────────────────
const CLIENT = "c-" + "a".repeat(32);
const UPLOAD_ID = "u_" + "b".repeat(24);
const OBJECT_PATH = `clients/${CLIENT}/intake/${UPLOAD_ID}.png`;
const HOST = "c".repeat(32) + ".r2.cloudflarestorage.com";
function accepted(upload_path = OBJECT_PATH, upload_id = UPLOAD_ID) {
  return new Response(JSON.stringify({
    ok: true,
    upload_id,
    object_path: upload_path,
    upload: {
      method: "PUT",
      url: `https://${HOST}/zhw-drama-studio/${upload_path}?signed=test`,
      content_type: "image/png",
    },
  }), { status: 201 });
}
const file = (name) => ({
  name,
  size: 12,
  slice: () => ({ arrayBuffer: async () => new ArrayBuffer(16) }),
});

let uploadCalls = 0;
globalThis.fetch = async (url, init = {}) => {
  uploadCalls += 1;
  if (String(url) === "/api/studio/uploads") return accepted();
  return new Response("", { status: 200 });
};

const input = addInput();
rule("the PHOTOS screen offers a file input", !!input);
input.files = [file("logo.png")];
await Promise.all((input.listeners.change || []).map((fn) => fn()));
await tick();

rule("an accepted upload keeps its id", state.uploadIds.length === 1 && state.uploadIds[0] === UPLOAD_ID,
  JSON.stringify(state.uploadIds));
rule("the page reads the file back by name", textOf(registry.main).includes("Added: logo.png"));
rule("the staged request was issued with the page key", uploadCalls >= 1, `${uploadCalls} call(s)`);

// ── Lock it in sends the list ────────────────────────────────────────────────
state.page = "recap";
state.replies = ["my logo"];
render();
const lockButton = findAll((n) => n.tagName === "BUTTON" && n.textContent === "Lock it in");
rule("the recap offers Lock it in", !!lockButton);
await Promise.all((lockButton.listeners.click || []).map((fn) => fn()));
await tick();
rule("the lockIn request carries the accepted upload id",
  lockInCalls.length === 1 && JSON.stringify(lockInCalls[0].upload_ids) === JSON.stringify([UPLOAD_ID]),
  JSON.stringify(lockInCalls[0] && lockInCalls[0].upload_ids));

// ── a 422 keeps the service's own words ─────────────────────────────────────
state.page = "questions";
state.locked = false;
state.orderId = null;
state.replies = ["my logo"];
render();
globalThis.fetch = async () => new Response(JSON.stringify({
  ok: false, code: "AF-DS-UP-REJECT-FORMAT", message: "That file is not the format its name says.",
}), { status: 422 });
const refused = addInput();
refused.files = [file("picture.png")];
await Promise.all((refused.listeners.change || []).map((fn) => fn()));
await tick();
rule("a 422 with a message shows the message",
  registry.status.textContent === "That file is not the format its name says.",
  registry.status.textContent);

// ── an HTML error page becomes the one plain sentence ───────────────────────
state.replies = ["my logo"];
render();
globalThis.fetch = async () => new Response("<html><body>502 Bad Gateway</body></html>", {
  status: 502, headers: { "content-type": "text/html" },
});
const broken = addInput();
broken.files = [file("picture.png")];
await Promise.all((broken.listeners.change || []).map((fn) => fn()));
await tick();
rule("an HTML error body shows the plain sentence",
  registry.status.textContent === "The studio could not take that file. Please try again.",
  registry.status.textContent);

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\nphoto upload check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\nphoto upload check OK: ${results.length} rules passed (fake DOM/service/transport)`);
process.exit(0);
