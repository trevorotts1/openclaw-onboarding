// =============================================================================
// RUNNABLE CHECK — the question screens are plain (S75-074, U-Z10)
// -----------------------------------------------------------------------------
// mini-app/ui/checks/plain-questions-check.mjs
//
// Imports the SHIPPED page (../studio.js) with a minimal DOM shim. No browser,
// no network, no dependency.
//
// WHAT IT PROVES (page side of S75-074)
//   (1) no heading is all capitals — the exported `title` is the heading, and
//       an older export's upper-case `label` is never drawn as one;
//   (2) "Tap a link to watch a sample." never survives as a sentence, and a
//       card that carries a `sample_url` draws a real "Watch a sample" link;
//   (3) a screen that is drawn from the re-exported card never shows "Reply
//       with", "KIE", "Suno", "Kling" or "the card" (the copy itself is the
//       exporter's, U-E02; this proves the page draws nothing of its own and
//       renders that card's plain wording);
//   (4) BUDGET shows a dollar figure, its recommended limit carries one
//       "Recommended" tag, and `why` is drawn under the options;
//   (5) exactly one option per choice screen carries the tag, unless the
//       export marks none on that screen;
//   (6) a typed screen draws the question, its example and one text box, with
//       no option row — whatever the export's option list says;
//   (7) the progress line reads "Question 3 of 17" inside the questions and
//       "Step N of 5" elsewhere, and the top-bar Questions button starts the
//       order instead of opening an empty screen.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/plain-questions-check.mjs
// =============================================================================

import { readFileSync } from "node:fs";

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

// The committed export — the card the page is served today.
const committed = JSON.parse(
  readFileSync(new URL("../questions.json", import.meta.url), "utf8"));

// Imported BEFORE any `document` exists, so boot() does not run.
const studio = await import("../studio.js");
const { state, render, headingFor } = studio;

// ── the DOM shim (the same idea as checks/price-check.mjs) ──────────────────
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
    replaceChildren(...nodes) { this.children = nodes.filter(Boolean); },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    querySelector(selector) {
      const want = String(selector).toUpperCase();
      return walk(this).find((n) => n !== this && n.tagName === want) || null;
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
globalThis.location = { hash: "", origin: "https://studio.example.com", pathname: "/" };
globalThis.history = { replaceState() {} };

const pageText = () => walk(registry.main).map((n) => n.textContent).filter(Boolean).join(" | ");
const headings = () => walk(registry.main).filter((n) => n.tagName === "H1");
const radios = () => walk(registry.main).filter((n) => n.tagName === "INPUT" && n.attrs.type === "radio");
const boxes = () => walk(registry.main).filter((n) => n.tagName === "TEXTAREA");
const textInputs = () => walk(registry.main).filter((n) => n.tagName === "INPUT" && n.attrs.type === "text");
const tags = () => walk(registry.main)
  .filter((n) => /(^|\s)tag(\s|$)/.test(String(n.attrs.class || "")))
  .map((n) => String(n.textContent).trim());

/** Render ONE screen on the real question page and return the page text. */
function draw(screen, opts = {}) {
  const questions = opts.questions || [screen];
  state.page = "questions";
  state.questions = questions;
  state.visible = questions.slice();
  state.visibleFrom = null;
  state.qIndex = opts.qIndex || 0;
  state.picks = opts.picks || [];
  state.texts = opts.texts || [];
  state.replies = opts.replies || [];
  state.note = "";
  render();
  return pageText();
}

const countOf = (haystack, needle) => String(haystack).split(needle).length - 1;

// ── (1) no heading is all capitals ───────────────────────────────────────────
for (const screen of committed.questions) {
  draw(screen);
  const drawn = headings().map((n) => String(n.textContent || "").trim());
  const heading = drawn[0] || "";
  const upper = heading.length > 0 && heading === heading.toUpperCase();
  rule(`(1) ${screen.id}: the heading is not all capitals`, !upper, heading || "(no heading)");
}
// the helper itself: an upper-case label is skipped, a plain label is kept
rule("(1) an upper-case label is never the heading",
  headingFor({ label: "BUDGET", question: "What may this video spend?" })
    === "What may this video spend?",
  headingFor({ label: "BUDGET", question: "What may this video spend?" }));
rule("(1) the exported title wins over both",
  headingFor({ title: "Your spending limit", label: "BUDGET", question: "What may this video spend?" })
    === "Your spending limit",
  headingFor({ title: "Your spending limit", label: "BUDGET", question: "What may this video spend?" }));

// ── (2) the sample sentence, and the real link ───────────────────────────────
const look = committed.questions.find((q) => q.id === "look");
if (look) {
  rule("(2) the source card really carries the sample sentence",
    /Tap a link to watch a sample/i.test(String(look.question)), String(look.question));
  draw(look);
  rule("(2) the page never draws \"Tap a link to watch a sample.\"",
    !/Tap a link to watch a sample/i.test(pageText()), pageText().slice(0, 200));
  rule("(2) no sample link is drawn when no option carries a sample_url",
    !walk(registry.main).some((n) => n.tagName === "A" && String(n.textContent) === "Watch a sample"));
}
{
  draw({
    id: "look", label: "VIDEO STYLE", title: "The look", typed: false,
    question: "How should your video look? Tap a link to watch a sample.",
    options: [
      { n: 1, text: "Lifelike 3D", detail: "", recommended: true, sample_url: "https://example.com/sample-a" },
      { n: 2, text: "2D Hand-Painted", detail: "", recommended: false },
    ],
  });
  const link = walk(registry.main)
    .find((n) => n.tagName === "A" && String(n.textContent) === "Watch a sample");
  rule("(2) a sample_url becomes a real \"Watch a sample\" link",
    Boolean(link) && link.attrs.href === "https://example.com/sample-a",
    link ? link.attrs.href : "(no link)");
  rule("(2) and the plain sentence is still gone", !/Tap a link to watch a sample/i.test(pageText()));
}

// ── (3) plain words on a re-exported screen ─────────────────────────────────
// The card U-E02 re-exports: titles, no typed option row, plain AGNES copy.
const plainCard = {
  id: "agnes", label: "AGNES", title: "Your Agnes plan", typed: false,
  question: "Should your Agnes plan make the pictures and clips for this video?",
  example: "\"Yes - use my Agnes plan.\" You have a plan and you want it used.",
  why: "The studio's own models make everything if you do not have a plan.",
  options: [
    { n: 1, text: "Yes - use my Agnes plan.", detail: "", recommended: true },
    { n: 2, text: "No - use the studio's own models.", detail: "", recommended: false },
  ],
  supplementary_explanation: [
    "Option 1 uses the plan you already pay Agnes for to make the pictures and clips. The song and the talking close-ups are still charged to your studio balance, and that cost is in your estimate.",
    "Option 2 uses the studio's own models for everything. You pick the quality next and see the cost before anything is made.",
  ],
};
draw(plainCard);
{
  const text = pageText();
  for (const banned of ["Reply with", "KIE", "Suno", "Kling", "the card"]) {
    rule(`(3) the screen never says "${banned}"`, !text.includes(banned), text.slice(0, 200));
  }
}
// and a typed screen from that same card draws no "Reply with" row
{
  const typedScreen = {
    id: "offer", label: "OFFER", title: "What you are promoting", typed: true,
    question: "What are we promoting?", example: "\"My 6-week program.\" The name and the link.",
    options: [],
  };
  draw(typedScreen);
  const text = pageText();
  rule("(3) a typed screen shows no \"Reply with\" text", !text.includes("Reply with"), text.slice(0, 200));
  rule("(3) and no option row at all", radios().length === 0, `${radios().length} radio(s)`);
  rule("(3) and exactly one text box, with its example",
    boxes().length === 1 && text.includes("See a great answer:"), text.slice(0, 200));
  rule("(3) and no lower-case heading bug: the title is the heading",
    (headings()[0] || {}).textContent === "What you are promoting",
    (headings()[0] || {}).textContent);
}
// an OLD export's typed screen (the single "reply with" row) takes the same shape
{
  const legacy = committed.questions.find((q) => q.id === "offer");
  if (legacy) {
    draw(legacy);
    rule("(3) an older typed export draws the box, not its reply-with row",
      radios().length === 0 && boxes().length === 1 && !pageText().includes("Reply with"),
      `${radios().length} radio(s), ${boxes().length} box(es)`);
  }
}

// ── (4) BUDGET: one dollar figure, one tag, and the card's `why` ────────────
const budget = {
  id: "spend", label: "BUDGET", title: "Your spending limit", typed: false,
  question: "What is the most this video may spend? Work stops and asks you before going over.",
  options: [
    { n: 1, text: "Use the recommended limit - about $24", detail: "", recommended: true },
    { n: 2, text: "Set my own limit", detail: "reply with a dollar amount, like $25", recommended: false },
  ],
  why: "The limit includes a redo allowance.",
};
{
  const text = draw(budget);
  rule("(4) BUDGET shows a dollar figure", /\$\d/.test(text), text.slice(0, 220));
  rule("(4) exactly one option carries the Recommended tag",
    tags().length === 1 && tags()[0] === "Recommended", tags().join(",") || "(none)");
  rule("(4) the card's `why` line is drawn under the options", text.includes("redo allowance"),
    text.slice(0, 220));
}
// the price is drawn once when `detail` already states it
{
  const withPrice = {
    id: "model", label: "VIDEO MODEL", title: "Picture quality", typed: false,
    question: "Which quality?",
    options: [{
      n: 1, text: "High", recommended: true,
      detail: "Recommended balance, about $24.00 for this length.",
      price: "about $24.00",
    }],
  };
  const text = draw(withPrice);
  rule("(4) a price already in the detail is not drawn a second time",
    countOf(text, "about $24.00") === 1, `${countOf(text, "about $24.00")} time(s): ${text.slice(0, 220)}`);
}

// ── (5) the tag count follows the export, screen by screen ──────────────────
for (const screen of committed.questions) {
  const recommended = (screen.options || []).filter((o) => o.recommended).length;
  draw(screen);
  const drawn = tags().length;
  const ok = recommended === 0 ? drawn === 0 : drawn === 1;
  rule(`(5) ${screen.id}: ${recommended} recommended option(s) — ${drawn} tag(s) drawn`,
    ok, `export ${recommended}, page ${drawn}`);
}
rule("(5) the committed export never marks more than one option per screen",
  committed.questions.every((q) => (q.options || []).filter((o) => o.recommended).length <= 1));

// ── (6) a typed screen is the question, the example and the box ─────────────
{
  const typed = {
    id: "character", label: "CHARACTER", title: "Who stars in it", typed: true,
    question: "Who stars in your video?",
    example: "\"Tasha, a warm 40-year-old braider with locs, in a denim apron.\"",
    options: [],
  };
  const text = draw(typed);
  rule("(6) the question is drawn", text.includes("Who stars in your video?"), text.slice(0, 200));
  rule("(6) the example is drawn", text.includes("a warm 40-year-old braider"),
    text.slice(0, 240));
  rule("(6) one box, no menu", boxes().length === 1 && radios().length === 0,
    `${boxes().length} box(es), ${radios().length} radio(s)`);
  rule("(6) the box is labelled in the client's words",
    walk(registry.main).some((n) => n.tagName === "LABEL"
      && String(n.textContent) === "Your answer, in your own words"),
    walk(registry.main).filter((n) => n.tagName === "LABEL").map((n) => n.textContent).join(","));
}

// ── (7) the progress line, and the top-bar Questions button ────────────────
{
  const three = ["purpose", "audience", "length"].map((id) => ({
    id, label: id.toUpperCase(), title: id, typed: false, question: id,
    options: [{ n: 1, text: "One", detail: "", recommended: false },
      { n: 2, text: "Two", detail: "", recommended: false }],
  }));
  state.page = "questions";
  state.questions = three;
  state.visible = three.slice();
  state.visibleFrom = three;
  state.qIndex = 2;
  state.picks = [];
  state.texts = [];
  state.replies = [];
  render();
  rule("(7) the questions show \"Question 3 of 3\"",
    registry["step-label"].textContent === "Question 3 of 3", registry["step-label"].textContent);

  state.page = "start";
  render();
  rule("(7) the five pages show \"Step 1 of 5\"",
    registry["step-label"].textContent === "Step 1 of 5", registry["step-label"].textContent);
}
{
  // the top-bar Questions button starts the order (it does not open a blank page)
  globalThis.studioService = {
    getQuestions: async () => ({ questions: [{
      id: "offer", label: "OFFER", title: "What you are promoting", typed: true,
      question: "What are we promoting?", options: [],
    }] }),
  };
  state.page = "start";
  state.questions = [];
  state.visible = [];
  state.visibleFrom = null;
  render();
  const nav = walk(registry["steps-nav"]).find((n) => n.tagName === "BUTTON"
    && String(n.textContent) === "Questions");
  rule("(7) the top bar carries a Questions button", Boolean(nav));
  if (nav) {
    await (nav.listeners.click || [])[0]();
    rule("(7) tapping it starts the order on the questions",
      state.page === "questions" && state.questions.length === 1, `${state.page}, ${state.questions.length} question(s)`);
  }
  delete globalThis.studioService;
}

delete globalThis.document;

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\nplain-questions check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\nplain-questions check OK: ${results.length} rules passed (DOM shim, no browser)`);
process.exit(0);
