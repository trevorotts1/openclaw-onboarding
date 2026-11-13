// =============================================================================
// RUNNABLE CHECK — the home page says what happened, in the client's words (S75-077)
// -----------------------------------------------------------------------------
// mini-app/ui/checks/home-page-check.mjs
//
// Imports the SHIPPED page (../studio.js) with a minimal DOM shim. No browser,
// no network, no dependency; exit codes that mean something.
//
// WHAT IT PROVES (steps 1, 2 and 5 of the unit, page side):
//   (1) a session the service refuses (401) is a page-level card, not the
//       "saving" line, and the empty project list is hidden; any other load
//       failure says the studio could not be reached;
//   (2) the project is named by the first 60 characters of the offer answer,
//       "Your video" when there is none, and never by a date;
//   (5) the Agnes line says "paused until tomorrow - today's plan time is used
//       up", and an unknown reason is printed as "paused" with no code.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/home-page-check.mjs
// =============================================================================

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

// ── the page, imported before a document exists ──────────────────────────────
// studio.js calls boot() only when `document` is already defined, so importing
// it first gives this check the module without a boot cycle racing it.
const studio = await import("../studio.js");
const { state, render, agnesProgressLine, orderTitle } = studio;

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
  createElement: makeElement,
  getElementById: (id) => registry[id] || null,
  addEventListener() {},
};
globalThis.location = { hash: "", origin: "https://studio.example.com" };
globalThis.history = { replaceState() {} };

const mainText = () => walk(registry.main).map((n) => n.textContent).filter(Boolean).join(" | ");

// ── (1) a refused link, and any other load failure ───────────────────────────
state.page = "start";
state.orders = [];
state.sessionFailure = "link";
render();
rule("(1) a refused link is a card on the page at once",
  mainText().includes("This studio link is no longer active. Ask for your new link - your projects are safe."),
  mainText().slice(0, 160));
rule("(1) the empty project list is hidden", !mainText().includes("Your projects"));
rule("(1) nothing is announced as a saving error",
  !/Something went wrong saving that/.test(registry.status.textContent), registry.status.textContent);

state.sessionFailure = "unreachable";
render();
rule("(1) any other load failure says the studio could not be reached",
  mainText().includes("The studio could not be reached. Check your connection and open the page again."),
  mainText().slice(0, 160));
rule("(1) only a refused link hides the project list", mainText().includes("Your projects"));

// ── (2) the order title is the offer answer, never a date ────────────────────
state.sessionFailure = null;
const offerText = `${"A".repeat(1)}${"b".repeat(79)}`;
state.visible = [{
  id: "offer",
  options: [{ n: 1, text: "Type it in", detail: "Reply with your own words." }],
}];
state.picks = ["1"];
state.texts = [offerText];
rule("(2) the title is the first 60 characters of the offer answer",
  orderTitle() === offerText.slice(0, 60), orderTitle());
rule("(2) the title carries no date", !/\d{4}-\d{2}-\d{2}/.test(orderTitle()), orderTitle());

state.texts = ["   "];
rule("(2) an empty offer names the project \"Your video\"", orderTitle() === "Your video", orderTitle());
state.visible = [];
state.picks = [];
state.texts = [];
rule("(2) no offer answer at all names it \"Your video\"", orderTitle() === "Your video", orderTitle());

// ── (5) the Agnes line, in the words the client gets ─────────────────────────
const waiting = { clips_total: 30, clips_done: 12, waiting_reason: "agnes-quota-next-day" };
rule("(5) the used-up plan time says paused until tomorrow",
  agnesProgressLine(waiting) === "paused until tomorrow - today's plan time is used up",
  agnesProgressLine(waiting));
const unknown = { ...waiting, waiting_reason: "agnes-some-new-reason" };
rule("(5) an unknown reason prints \"paused\" with no code",
  agnesProgressLine(unknown) === "paused", agnesProgressLine(unknown));

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\nhome-page check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\nhome-page check OK: ${results.length} rules passed (DOM shim)`);
process.exit(0);
