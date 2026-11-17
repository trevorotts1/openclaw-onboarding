// =============================================================================
// RUNNABLE CHECK — the project page tells the truth as it changes (S75-073)
// -----------------------------------------------------------------------------
// mini-app/ui/checks/project-page-check.mjs
//
// Imports the SHIPPED page (../studio.js) with a minimal DOM shim, a FAKE CLOCK
// (setInterval/clearInterval are recorded, never real) and a FAKE SERVICE (the
// object service-client.js would install). No browser, no network, no
// dependency; exit codes that mean something.
//
// WHAT IT PROVES (the four carried acceptance cases, plus the rules behind):
//   (a) a state change on the service appears after ONE interval, with no
//       reload — the same page keeps painting from the same module instance;
//   (a2) an unchanged read repaints nothing, and the reader runs every 30 s;
//   (b) a text box on the page that holds text (or has focus) is never wiped
//       by a refresh; once it is empty the next interval paints;
//   (c) a cancelled order shows its sentence and a "Start it again" button,
//       and that button opens the recap with the order's own kept answers;
//   (d) no text on the page is a machine reason code;
//   (e) the stale line the service sends is shown under the status;
//   (f) the timeline lists only the stages the order reached plus the one it
//       is in now, and never lists "Needs you" unless it is the current state.
//
// The approvals view is not loaded here (the page renders its own "not here
// yet" line when it is absent), so this check exercises the page's own read,
// signature and redraw rules and nothing of the approval cards.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/project-page-check.mjs
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
const {
  state, render, PROJECT_REFRESH_MS, projectSignature, redrawBlocked,
  refreshProject, startProjectRefresh, stopProjectRefresh, timelineFor,
} = studio;

// ── the fake clock ───────────────────────────────────────────────────────────
const timers = [];
const cleared = [];
globalThis.setInterval = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
globalThis.clearInterval = (id) => { cleared.push(id); };
const latestTimer = () => timers[timers.length - 1];
const tick = async () => { await new Promise((r) => setTimeout(r, 0)); await new Promise((r) => setTimeout(r, 0)); };

// ── the DOM shim ─────────────────────────────────────────────────────────────
let repaints = 0;

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
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    append(...nodes) { for (const n of nodes) if (n) this.children.push(n); },
    appendChild(n) { this.children.push(n); return n; },
    replaceChildren(...nodes) {
      if (this.attrs && this.attrs.id === "main") repaints += 1;
      this.children = nodes.filter(Boolean);
    },
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

const documentListeners = Object.create(null);
globalThis.document = {
  activeElement: null,
  visibilityState: "visible",
  createElement: makeElement,
  getElementById: (id) => registry[id] || null,
  addEventListener(type, fn) { (documentListeners[type] ||= []).push(fn); },
};
globalThis.location = { hash: "", origin: "https://studio.example.com", pathname: "/" };
// setPage rewrites the fragment; a check has no browser history of its own.
globalThis.history = { replaceState() {} };

const textOf = (nodes) => (Array.isArray(nodes) ? nodes : [nodes])
  .flatMap((n) => walk(n))
  .map((n) => n.textContent)
  .filter(Boolean)
  .join(" | ");
const pageText = () => textOf(registry.main);
const findButton = (text) => walk(registry.main)
  .find((n) => n.tagName === "BUTTON" && n.textContent === text);
const click = async (node) => {
  for (const fn of node.listeners.click || []) await fn();
  await tick();
};

// ── the fake service ─────────────────────────────────────────────────────────
function fakeService(order) {
  let current = order;
  let stale = "";
  let items = [];
  const svc = {
    calls: [],
    setOrder(next) { current = next; },
    setStale(next) { stale = next; },
    setItems(next) { items = next; },
    async getSession() { return { client_id: "c-1", option_line: "", orders: [current], draft: null }; },
    async getOrder(orderId) {
      svc.calls.push(["getOrder", orderId]);
      return { order: current, stale_page_line: stale };
    },
    async listApprovals(orderId) {
      svc.calls.push(["listApprovals", orderId]);
      return { ok: true, items };
    },
    async getQuestions() { return { questions: [] }; },
    async saveDraft() { return { ok: true }; },
    async answerApproval() { return { ok: true }; },
    async getDelivery() { return null; },
    fetchApprovalMedia: async () => { throw new Error("no media in this check"); },
  };
  return svc;
}

function showOrder(order) {
  Object.assign(state, {
    page: "approvals", order, orders: [order],
    staleLine: "", approvalItems: [], projectSig: "",
    locked: true, sending: false, agnesProgress: null,
  });
  render();
}

// ── (a) + (a2): one interval, no reload, no needless repaint ─────────────────
const WAITING = {
  order_id: "r_aaaa1111", title: "My ad", state: "waiting",
  created_at: 1, replies: ["1", "a sentence"],
};
const svc = fakeService(WAITING);
globalThis.studioService = svc;

showOrder(WAITING);
rule("the project page starts its reader", timers.length === 1, `${timers.length} interval(s)`);
rule("the reader runs every 30 seconds", timers.length === 1 && latestTimer().ms === PROJECT_REFRESH_MS,
  timers.length ? `${latestTimer().ms} ms` : "no interval");

await tick();
rule("(a) drawing the page shows the order's own state", pageText().includes("Status: Waiting for the studio to start"));

const quietRepaints = repaints;
latestTimer().fn();
await tick();
rule("(a2) an unchanged read repaints nothing", repaints === quietRepaints, `${repaints - quietRepaints} repaint(s)`);

svc.setOrder({ ...WAITING, state: "in_production", in_production_at: 5 });
const beforeRepaints = repaints;
latestTimer().fn();
await tick();
rule("(a) a state change on the service appears after one interval",
  pageText().includes("Status: In production") && !pageText().includes("Status: Waiting for the studio to start"),
  pageText().slice(0, 120));
rule("(a) it appears with no reload — the page is still the project page", state.page === "approvals");
rule("(a) the change really was a repaint", repaints > beforeRepaints, `${repaints - beforeRepaints} repaint(s)`);

// ── (e) the stale line ───────────────────────────────────────────────────────
svc.setStale("This page was behind. It has just been brought up to date.");
latestTimer().fn();
await tick();
rule("(e) the service's stale line is shown under the status",
  pageText().includes("This page was behind. It has just been brought up to date."));

// ── (b) a text box with text is never wiped ──────────────────────────────────
{
  const box = makeElement("textarea");
  box.value = "half a storyboard note I am still writing";
  registry.main.append(box);

  svc.setOrder({ ...WAITING, state: "ready", in_production_at: 5, ready_at: 9 });
  const keptRepaints = repaints;
  latestTimer().fn();
  await tick();
  rule("(b) a text box with content is not wiped by a refresh",
    walk(registry.main).includes(box), "box still on the page");
  rule("(b) and the page did not repaint over it", repaints === keptRepaints, `${repaints - keptRepaints} repaint(s)`);
  rule("(b) the client still sees the state they had", pageText().includes("Status: In production"));

  // Focus alone is enough to hold the page still.
  box.value = "";
  globalThis.document.activeElement = box;
  latestTimer().fn();
  await tick();
  rule("(b) a text box with focus holds the page too", repaints === keptRepaints, `${repaints - keptRepaints} repaint(s)`);
  rule("(b) the box rule is the reason", redrawBlocked() === true);

  // Empty and not focused: the next interval paints.
  globalThis.document.activeElement = null;
  latestTimer().fn();
  await tick();
  rule("(b) with the box empty and unfocused the next interval paints",
    repaints > keptRepaints && pageText().includes("Status: Ready for you"),
    pageText().slice(0, 120));
}

// ── the approvals list is part of the signature (no repaint without it) ──────
{
  const currentOrder = state.order;
  const none = projectSignature(currentOrder, "", []);
  const one = projectSignature(currentOrder, "", [{ stage: "script", version: 1 }]);
  const two = projectSignature(currentOrder, "", [{ stage: "script", version: 2 }]);
  rule("a new approval version changes the signature", none !== one && one !== two);
  rule("the order of the listing does not change the signature",
    projectSignature(currentOrder, "", [{ stage: "song", version: 1 }, { stage: "script", version: 1 }])
    === projectSignature(currentOrder, "", [{ stage: "script", version: 1 }, { stage: "song", version: 1 }]));
}

// ── "Check for updates" ──────────────────────────────────────────────────────
{
  const button = findButton("Check for updates");
  rule("the project page offers “Check for updates”", !!button);
  if (button) {
    registry.status.textContent = "";
    await click(button);
    rule("“Check for updates” with nothing new says so in words",
      registry.status.textContent === "Nothing has changed yet.", registry.status.textContent);
  }
}

// ── (c) + (d) a cancelled order ──────────────────────────────────────────────
const CANCELLED = {
  order_id: "r_bbbb2222", title: "Old ad", state: "cancelled",
  created_at: 1, cancelled_at: 3, replies: ["1", "my offer, in my words"],
  state_reason: "AF-DS-TERMINAL-CANCELLED",
};
{
  svc.setOrder(CANCELLED);
  svc.setStale("");
  showOrder(CANCELLED);
  await tick();

  const text = pageText();
  rule("(c) a cancelled order says what happened",
    text.includes("This order was cancelled before any work was charged."), text.slice(0, 160));
  rule("(c) it says the answers were kept", text.includes("Your answers were kept."));
  rule("(c) it does not claim a draft that was cleared at lock-in", !/kept as a draft/i.test(text));

  const restart = findButton("Start it again");
  rule("(c) a cancelled order offers “Start it again”", !!restart);

  // (d) no machine reason code anywhere on the screen.
  rule("(d) no upper-case reason code is printed",
    !/[A-Z]{2,}[-_][A-Z0-9]/.test(text), text.match(/[A-Z]{2,}[-_][A-Z0-9][A-Z0-9-]*/)?.[0] || "");
  rule("(d) `state_reason` is not printed", !/state_reason/i.test(text) && !/\bterminal\b/i.test(text));

  if (restart) {
    await click(restart);
    rule("(c) “Start it again” opens the recap",
      state.page === "recap", `page=${state.page}`);
    rule("(c) the recap carries the order's own kept answers",
      JSON.stringify(state.replies) === JSON.stringify(CANCELLED.replies), JSON.stringify(state.replies));
    rule("(c) a new order gets a new id", state.orderId === null || state.orderId !== CANCELLED.order_id);
  }
}

// ── an expired order says its own sentence ───────────────────────────────────
{
  const EXPIRED = { order_id: "r_cccc3333", title: "Old ad", state: "expired", created_at: 1, replies: ["1"] };
  svc.setOrder(EXPIRED);
  showOrder(EXPIRED);
  await tick();
  const text = pageText();
  rule("an expired order says it was not picked up in 45 days",
    text.includes("This order was not picked up in 45 days and has ended."));
  rule("an expired order offers “Start it again”", !!findButton("Start it again"));
}

// ── (f) the timeline only shows what really happened ────────────────────────
{
  const rows = (order) => timelineFor(order).flatMap((n) => walk(n)).map((n) => n.textContent).filter(Boolean);

  const ready = rows({ order_id: "r_d", state: "ready", created_at: 1, in_production_at: 2, ready_at: 3 });
  rule("(f) the timeline lists the stages reached plus the current one",
    ready.includes("Waiting for the studio to start — finished")
    && ready.includes("In production — finished")
    && ready.includes("Ready for you — now"), ready.join(" / "));
  rule("(f) a stage the order never reached is not listed",
    !ready.some((t) => /Delivered|Finished/.test(t)), ready.join(" / "));

  const checked = rows({ order_id: "r_e", state: "in_production", created_at: 1, in_production_at: 2, needs_you_at: 2 });
  rule("(f) “Needs you” is never listed as history",
    !checked.some((t) => /Needs you/.test(t)), checked.join(" / "));

  const needs = rows({ order_id: "r_f", state: "needs_you", created_at: 1, in_production_at: 2, needs_you_at: 3 });
  rule("(f) “Needs you” is a line while it is the current state",
    needs.includes("Needs you — now"), needs.join(" / "));

  const cancelled = rows({ order_id: "r_g", state: "cancelled", created_at: 1, cancelled_at: 3 });
  rule("(f) a cancelled order shows the state it is in now",
    cancelled.includes("Cancelled — now") && cancelled.includes("Waiting for the studio to start — finished"),
    cancelled.join(" / "));
}

// ── the reader stops when the page is left ──────────────────────────────────
{
  const before = cleared.length;
  state.page = "start";
  render();
  rule("the reader stops on any other page", cleared.length > before, `${cleared.length - before} stop(s)`);
  const afterStop = timers.length;
  state.page = "approvals";
  state.order = { ...WAITING, state: "waiting" };
  state.orders = [state.order];
  render();
  rule("coming back to the project page starts a fresh reader", timers.length > afterStop);
  stopProjectRefresh();
}

delete globalThis.studioService;

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\nproject-page check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\nproject-page check OK: ${results.length} rules passed (fake clock, fake service, DOM shim)`);
process.exit(0);
