// =============================================================================
// RUNNABLE CHECK — the delivery screen works (S75-070)
// -----------------------------------------------------------------------------
// mini-app/ui/checks/delivery-page-check.mjs
//
// Imports the SHIPPED page (../studio.js) with a minimal DOM shim, the same way
// checks/ui-contract.mjs and checks/approvals-view-check.mjs do: no browser, no
// dependency, exit codes that mean something.
//
// WHAT IT PROVES:
//   (a) an order with a delivery address draws a real <video> player and an
//       ENABLED plain download link — and no "check the download first" step,
//       because a button that refuses to work until a check passed is a button
//       that does not work;
//   (b) nothing on that screen talks about header names, byte counts or HTTP
//       statuses — the client is not the studio's debug log;
//   (c) an order whose link is `r2-expired` says the link ended, says the video
//       is still in their own media library, and offers no player.
//
// Plus the project screen's two promises: the link to the video reads
// "Open my video" (never the raw address as its text), and "Watch it now"
// still opens the player for that same video.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/delivery-page-check.mjs
// =============================================================================
import { state, render } from "../studio.js";

const DELIVERY_URL = "https://storage.googleapis.com/drama-studio/deliveries/order-77/master.mp4";

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

// ── the DOM shim ─────────────────────────────────────────────────────────────
function walk(node, out = []) {
  out.push(node);
  for (const c of node.children || []) walk(c, out);
  return out;
}

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
      return walk(this).find((n) => n.tagName === String(selector).toUpperCase()) || null;
    },
    focus() {},
  };
}

const registry = Object.create(null);
for (const id of ["main", "steps-nav", "rail", "rail-fill", "step-label", "status"]) {
  registry[id] = makeElement("div");
}
globalThis.document = {
  createElement: makeElement,
  getElementById: (id) => registry[id] || null,
};
// setPage reads the hash; a check has no browser location of its own.
globalThis.location = { hash: "", origin: "https://studio.example", pathname: "/" };

const textOf = (nodes) => nodes.map((n) => n.textContent).filter(Boolean).join(" | ");
const click = (node) => { for (const fn of node.listeners.click || []) fn(); };

function drawDelivery(delivery) {
  state.page = "delivery";
  state.delivery = delivery;
  render();
  return walk(registry.main);
}

// ── (a) a delivery address: a player and an enabled plain download link ──────
{
  const page = drawDelivery({
    masterUrl: DELIVERY_URL, clips: [], qrPayload: DELIVERY_URL, availability: "available",
  });
  const video = page.find((n) => n.tagName === "VIDEO");
  rule("(a) a delivery with a working link draws a video player",
    !!video && video.getAttribute("src") === DELIVERY_URL,
    video ? String(video.getAttribute("src")) : "no video element");
  rule("(a) the player is a real player (controls, playsinline, preload=metadata)",
    !!video && video.getAttribute("controls") !== null
      && video.getAttribute("playsinline") !== null
      && video.getAttribute("preload") === "metadata");

  const saves = page.filter((n) => n.tagName === "A" && n.textContent === "Download my video");
  rule("(a) “Download my video” is one plain link that saves the file",
    saves.length === 1
      && saves[0].getAttribute("href") === DELIVERY_URL
      && saves[0].getAttribute("download") !== null,
    `${saves.length} link(s)`);
  rule("(a) the download link is enabled — no gate to pass first",
    saves.length === 1
      && saves[0].getAttribute("aria-disabled") !== "true"
      && saves[0].getAttribute("disabled") === null);

  rule("(a) no “check the download” step is offered",
    !page.some((n) => n.tagName === "BUTTON" && /check the download/i.test(n.textContent)));
  rule("(a) the phone advice is on the page",
    textOf(page).includes("press and hold it and choose Save"));

  // ── (b) no studio debug talk on the client's screen ────────────────────────
  const pageText = textOf(page);
  rule("(b) no header name, byte count or HTTP status is printed",
    !/Content-/i.test(pageText) && !/\bbytes\b/i.test(pageText) && !/\bHTTP\b/.test(pageText),
    pageText.slice(0, 160));
}

// ── (c) the link ended: words, and no player ─────────────────────────────────
{
  const page = drawDelivery({
    masterUrl: DELIVERY_URL, clips: [], qrPayload: DELIVERY_URL, availability: "r2-expired",
  });
  const pageText = textOf(page);
  rule("(c) an expired link says the link ended 7 days after delivery",
    pageText.includes("This download link ended 7 days after delivery"));
  rule("(c) an expired link says the video is still in their own media library",
    pageText.includes("Your video is still in your own media library. Ask us for a fresh link."));
  rule("(c) an expired link offers no player and no save link",
    !page.some((n) => n.tagName === "VIDEO")
      && !page.some((n) => n.tagName === "A" && n.textContent === "Download my video"));
}

// ── the project screen: "Open my video", and "Watch it now" ──────────────────
{
  state.page = "approvals";
  state.order = {
    order_id: "order-77",
    title: "Your ad",
    state: "delivered",
    delivery: { url: DELIVERY_URL },
    availability: "available",
  };
  state.orders = [state.order];
  state.agnesProgress = null;
  render();
  const project = walk(registry.main);

  const open = project.filter((n) => n.tagName === "A" && n.textContent === "Open my video");
  rule("project page: the link to the video reads “Open my video”",
    open.length === 1 && open[0].getAttribute("href") === DELIVERY_URL,
    `${open.length} link(s)`);
  rule("project page: the raw address is never the link text",
    !project.some((n) => n.tagName === "A" && n.textContent === DELIVERY_URL));

  const watch = project.find((n) => n.tagName === "BUTTON" && n.textContent === "Watch it now");
  rule("project page: “Watch it now” is still offered", !!watch);
  if (watch) click(watch);
  rule("project page: “Watch it now” opens the player for that same video",
    state.page === "delivery" && state.delivery && state.delivery.masterUrl === DELIVERY_URL,
    `page=${state.page}`);
  rule("project page: the player it opens honours the order's availability",
    state.delivery && state.delivery.availability === "available",
    String(state.delivery && state.delivery.availability));
}

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\ndelivery-page check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\ndelivery-page check OK: ${results.length} rules passed`);
process.exit(0);
