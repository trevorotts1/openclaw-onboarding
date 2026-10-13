// =============================================================================
// RUNNABLE CHECK — the approval cards the phone draws (W1-studio-page-U3)
// -----------------------------------------------------------------------------
// mini-app/ui/checks/approvals-view-check.mjs
//
// Imports the SHIPPED module with a fake `globalThis.studioService` and a
// minimal DOM shim (same idea as checks/a11y-check.mjs: no browser, no
// dependency, exit codes that mean something).
//
// WHAT IT PROVES:
//   * every stage renders a card, in the script -> song -> storyboard order,
//     under the exact headings mini-app/approvals/ui.mjs uses;
//   * every button sends the value the plan names:
//       script     "Looks great" -> "approve", "Change something" -> typed text
//       song       three players, "Pick this one" -> "1" / "2" / "3"
//       storyboard "Approve all" -> "GO", "Change this shot" -> "shot N: <text>"
//   * an answer the service refuses (HTTP 409 APPROVAL_ANSWER_TAKEN) shows
//     "Already answered" in words;
//   * an item that already has an answer shows the answer in words and offers
//     no buttons;
//   * no `innerHTML` anywhere in the shipped file.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/approvals-view-check.mjs
// =============================================================================
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { APPROVAL_HEADINGS } from "../../approvals/ui.mjs";
import { renderApprovalsFor } from "../approvals-view.js";

const here = dirname(fileURLToPath(import.meta.url));
const viewSource = readFileSync(join(here, "..", "approvals-view.js"), "utf8");

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

// ── the DOM shim ─────────────────────────────────────────────────────────────
function makeElement(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    attrs: Object.create(null),
    children: [],
    listeners: Object.create(null),
    textContent: "",
    value: "",
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    append(...nodes) { for (const n of nodes) if (n) this.children.push(n); },
    appendChild(n) { this.children.push(n); return n; },
    replaceChildren(...nodes) { this.children = nodes.filter(Boolean); },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    focus() {},
  };
}

const registry = Object.create(null);
globalThis.document = {
  createElement: makeElement,
  getElementById: (id) => registry[id] || null,
};
registry.status = makeElement("p");
registry.main = makeElement("main");

const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children || []) walk(c, out);
  return out;
};
const textOf = (node) => walk(node).map((n) => n.textContent).filter(Boolean).join(" | ");
const findButton = (root, text) => walk(root).find((n) => n.tagName === "BUTTON" && n.textContent === text);
const findCard = (root, stage) => walk(root)
  .find((n) => n.tagName === "DIV" && n.getAttribute("data-stage") === stage);
const buttonsIn = (node) => walk(node).filter((n) => n.tagName === "BUTTON");
const click = async (node) => {
  for (const fn of node.listeners.click || []) await fn();
};

const ORDER_ID = "order-77";
function fakeService(items, answerImpl) {
  const calls = [];
  return {
    calls,
    list: () => calls.filter((c) => c[0] === "list"),
    sent: () => calls.filter((c) => c[0] === "answer"),
    async listApprovals(orderId) {
      calls.push(["list", orderId]);
      return { ok: true, items: structuredClone(items) };
    },
    async answerApproval(orderId, stage, version, value) {
      calls.push(["answer", orderId, stage, version, value]);
      if (answerImpl) return answerImpl({ orderId, stage, version, value });
      return { ok: true };
    },
  };
}

const SAMPLE = [
  { stage: "storyboard", version: 2, text: "Every shot, with a picture and a card.",
    choices: [], files: [{ name: "shot-1.png", url: "https://cdn.test/shot-1.png" },
      { name: "shot-2.png", url: "https://cdn.test/shot-2.png" }], answer: null },
  { stage: "song", version: 3, text: "Listen to all three.",
    choices: [{ n: 1, label: "Version A" }, { n: 2, label: "Version B" }, { n: 3, label: "Version C" }],
    files: [{ name: "a.mp3", url: "https://cdn.test/a.mp3" },
      { name: "b.mp3", url: "https://cdn.test/b.mp3" },
      { name: "c.mp3", url: "https://cdn.test/c.mp3" }], answer: null },
  { stage: "script", version: 1, text: "The story and the song lyrics.",
    choices: [], files: [], answer: null },
];

async function render(items, answerImpl) {
  const svc = fakeService(items, answerImpl);
  globalThis.studioService = svc;
  const root = makeElement("div");
  const rendered = await renderApprovalsFor({ order_id: ORDER_ID }, root);
  return { svc, root, rendered };
}

// ── 1. what the file must not do ─────────────────────────────────────────────
rule("no innerHTML anywhere in approvals-view.js", !/\.innerHTML\s*=/.test(viewSource));
rule("does not import the unserved approvals/ui.mjs", !/from\s+["'][^"']*approvals\/ui\.mjs/.test(viewSource));

// ── 2. every stage renders, under the shared headings ────────────────────────
const first = await render(SAMPLE);
{
  const stages = first.root.children
    .map((c) => c.getAttribute("data-stage"));
  rule("three cards, ordered script, song, storyboard",
    JSON.stringify(stages) === JSON.stringify(["script", "song", "storyboard"]), stages.join(", "));
  rule("the service was asked for this order", first.svc.list()[0]?.[1] === ORDER_ID,
    String(first.svc.list()[0]?.[1]));
  for (const stage of ["script", "song", "storyboard"]) {
    const card = findCard(first.root, stage);
    const heading = card && card.children.find((n) => n.tagName === "H2");
    rule(`heading matches approvals/ui.mjs for ${stage}`,
      !!heading && heading.textContent === APPROVAL_HEADINGS[stage],
      heading ? heading.textContent : "no card");
  }
}

// ── 3. script: the two buttons and their values ──────────────────────────────
{
  const a = await render(SAMPLE);
  await click(findButton(findCard(a.root, "script"), "Looks great"));
  rule("script “Looks great” sends approve",
    JSON.stringify(a.svc.sent()[0]) === JSON.stringify(["answer", ORDER_ID, "script", 1, "approve"]),
    JSON.stringify(a.svc.sent()[0]));

  const b = await render(SAMPLE); // a fresh card: the answered one has no inputs left
  const card = findCard(b.root, "script");
  const input = walk(card).find((n) => n.tagName === "INPUT");
  input.value = "  make the opening shorter  ";
  await click(findButton(card, "Change something"));
  rule("script “Change something” sends the typed text",
    b.svc.sent()[0]?.[4] === "make the opening shorter", JSON.stringify(b.svc.sent()[0]));
}

// ── 4. an empty change box sends nothing ─────────────────────────────────────
{
  const { svc, root } = await render(SAMPLE);
  const card = findCard(root, "script");
  const input = walk(card).find((n) => n.tagName === "INPUT");
  input.value = "   ";
  await click(findButton(card, "Change something"));
  rule("empty change box sends nothing", svc.sent().length === 0, `${svc.sent().length} call(s)`);
}

// ── 5. song: three players, three values ─────────────────────────────────────
{
  const { root } = await render(SAMPLE);
  const card = findCard(root, "song");
  const audios = walk(card).filter((n) => n.tagName === "AUDIO");
  rule("song shows three audio players",
    audios.length === 3 && audios.map((a) => a.getAttribute("src")).join(",")
      === "https://cdn.test/a.mp3,https://cdn.test/b.mp3,https://cdn.test/c.mp3",
    `${audios.length} player(s)`);

  const sent = [];
  for (let i = 1; i <= 3; i++) {
    const fresh = await render(SAMPLE); // every answer repaints the cards
    const picks = walk(findCard(fresh.root, "song"))
      .filter((n) => n.tagName === "BUTTON" && n.textContent === "Pick this one");
    await click(picks[i - 1]);
    sent.push(fresh.svc.sent()[0]?.[4]);
  }
  rule("song “Pick this one” sends 1, 2, 3", sent.join(",") === "1,2,3", sent.join(","));
}

// ── 6. storyboard: stills, GO, and the shot number ───────────────────────────
{
  const { root } = await render(SAMPLE);
  const imgs = walk(findCard(root, "storyboard")).filter((n) => n.tagName === "IMG");
  rule("storyboard lists its stills", imgs.length === 2
    && imgs.every((i) => i.getAttribute("src").startsWith("https://cdn.test/shot-")), `${imgs.length} still(s)`);

  const go = await render(SAMPLE);
  await click(findButton(findCard(go.root, "storyboard"), "Approve all"));
  rule("storyboard “Approve all” sends GO",
    go.svc.sent()[0]?.[4] === "GO", JSON.stringify(go.svc.sent()[0]));

  const shot = await render(SAMPLE);
  const card = findCard(shot.root, "storyboard");
  const inputs = walk(card).filter((n) => n.tagName === "INPUT");
  inputs[1].value = "the door should be red";
  const changeButtons = walk(card).filter((n) => n.tagName === "BUTTON"
    && n.textContent === "Change this shot");
  await click(changeButtons[1]);
  rule("storyboard “Change this shot” sends shot N: text",
    shot.svc.sent()[0]?.[4] === "shot 2: the door should be red", JSON.stringify(shot.svc.sent()[0]));
}

// ── 7. the answer lands back on the card, in words ───────────────────────────
{
  const { root } = await render(SAMPLE);
  const card = findCard(root, "script");
  await click(findButton(card, "Looks great"));
  const after = findCard(root, "script");
  rule("an answered card shows the answer in words and no buttons",
    /approve/.test(textOf(after)) && buttonsIn(after).length === 0, textOf(after).slice(0, 120));
}

// ── 8. an item that arrives already answered ─────────────────────────────────
{
  const items = SAMPLE.map((i) => (i.stage === "song"
    ? { ...i, answer: { value: "2", by: "telegram", at: 1 } } : i));
  const { root } = await render(items);
  const card = findCard(root, "song");
  rule("an item answered elsewhere shows that answer in words",
    textOf(card).includes("“2”"), textOf(card).slice(0, 140));
  rule("an answered item offers no buttons", buttonsIn(card).length === 0,
    `${buttonsIn(card).length} button(s)`);
}

// ── 9. the second answer is refused with 409 ─────────────────────────────────
{
  const taken = () => {
    const err = new Error("This approval is already answered");
    err.code = "APPROVAL_ANSWER_TAKEN";
    err.status = 409;
    throw err;
  };
  const { root } = await render(SAMPLE, taken);
  const card = findCard(root, "script");
  await click(findButton(card, "Looks great"));
  const after = findCard(root, "script");
  rule("a refused (409) answer shows “Already answered”",
    textOf(after).includes("Already answered"), textOf(after).slice(0, 160));
}

// ── 10. no service installed → words, no crash ───────────────────────────────
{
  delete globalThis.studioService;
  const root = makeElement("main");
  let threw = null;
  try {
    await renderApprovalsFor({ order_id: ORDER_ID }, root);
  } catch (err) { threw = err; }
  rule("no service installed renders a sentence instead of throwing",
    threw === null && /not connected/.test(textOf(root)), threw ? threw.message : textOf(root).slice(0, 100));
}
delete globalThis.studioService;

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\napprovals-view check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\napprovals-view check OK: ${results.length} rules passed`);
process.exit(0);
