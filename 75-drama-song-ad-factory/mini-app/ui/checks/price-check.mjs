// =============================================================================
// RUNNABLE CHECK — the page's price is the card's price (S75-059, U-Z09)
// -----------------------------------------------------------------------------
// mini-app/ui/checks/price-check.mjs
//
// Imports the SHIPPED page (../studio.js) with a minimal DOM shim. No browser,
// no network, no dependency.
//
// WHAT IT PROVES
//   (1) the price the page computes for 60 s, 180 s and 600 s equals
//       `price-fixture.json` — the Python price function's own output
//       (`catalog_calculator.card_render.quote`), saved by U-E02 — for every
//       video model the card offers. A change to the page arithmetic that the
//       card does not make is a FAIL here, not a different price in the client's
//       face;
//   (2) before LENGTH is answered no number is invented: the option says
//       "price shown after you pick a length";
//   (3) the recap shows the question's plain wording and the option TEXT
//       ("The sound: R&B Flow") — never the upper-case label, never the number.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/price-check.mjs
// =============================================================================

import { readFileSync } from "node:fs";

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

// ── (1) the arithmetic against the Python function's own output ─────────────
let fixture = null;
try {
  fixture = JSON.parse(readFileSync(new URL("./price-fixture.json", import.meta.url), "utf8"));
} catch (err) {
  rule("price-fixture.json is on this branch", false,
    `${err.code || err.message} — U-E02 saves it from the Python price function`);
}

// Imported BEFORE any `document` exists, so boot() does not run.
const studio = await import("../studio.js");
const { state, render, optionPriceUsd, optionPriceLine, answerReply } = studio;

if (fixture) {
  const lengths = (fixture.lengths_s || []).map(String);
  rule("the fixture names the three lengths", lengths.join(",") === "60,180,600", lengths.join(","));

  const models = fixture.models || {};
  rule("the fixture carries every video model", Object.keys(models).length > 0,
    `${Object.keys(models).length} model(s)`);

  // U-E02 saves the picture rate, the song rate and the planning allowance ONCE
  // at the top of the fixture (`keyframe_usd`, `song_usd`, `redo_rate`), with
  // `keyframe_count_extra` beside them; a model may override any of the three.
  // Reading them off the model object alone gives undefined, the page rightly
  // refuses to price, and this check goes red for the wrong reason.
  const priceInputs = (model) => ({
    keyframe_usd: model.keyframe_usd ?? fixture.keyframe_usd,
    song_usd: model.song_usd ?? fixture.song_usd,
    redo_rate: model.redo_rate ?? fixture.redo_rate,
    keyframe_count_extra: fixture.keyframe_count_extra,
  });

  for (const [n, model] of Object.entries(models)) {
    for (const length of lengths) {
      const option = {
        n: Number(n), text: model.name, unit: model.unit, shot_s: model.shot_s,
        rate_usd: model.rate_usd, ...priceInputs(model),
      };
      const got = optionPriceUsd(option, Number(length));
      const want = model.prices_usd[length];
      rule(`${model.name} at ${length} s costs the card's price`,
        got === want, `page ${got} vs fixture ${want}`);
    }
  }

  // the price line itself: a figure once the length is known, a sentence before
  const first = Object.entries(models)[0];
  if (first) {
    const [n, model] = first;
    const option = {
      n: Number(n), text: model.name, unit: model.unit, shot_s: model.shot_s,
      rate_usd: model.rate_usd, ...priceInputs(model),
    };
    rule("a priced option with no length says so, no number",
      optionPriceLine(option, null) === "price shown after you pick a length",
      optionPriceLine(option, null));
    rule("a priced option at a known length shows that price",
      optionPriceLine(option, 60) === `about $${Number(model.prices_usd["60"]).toFixed(2)}`,
      optionPriceLine(option, 60));
    rule("an option with no rates shows no price at all",
      optionPriceLine({ n: 1, text: "Soul Ballad" }, 60) === "",
      optionPriceLine({ n: 1, text: "Soul Ballad" }, 60));
  }
}

// ── the DOM shim (the same idea as checks/project-page-check.mjs) ───────────
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
const ruleText = () => walk(registry.main)
  .filter((n) => n.tagName === "BUTTON").map((n) => n.textContent).filter(Boolean);

// ── (1b) the price is drawn on the MODEL screen, from the LENGTH answer ─────
{
  const lengthScreen = {
    id: "length", label: "LENGTH", title: "How long", typed: false, question: "How long?",
    shows_when: {}, options: [
      { n: 1, text: "60 seconds", detail: "" },
      { n: 4, text: "3 minutes + 60s and 90s clips", detail: "" },
    ],
  };
  const modelOne = fixture && fixture.models && fixture.models["1"];
  const modelScreen = {
    id: "model", label: "VIDEO MODEL", title: "Picture quality", typed: false,
    question: "Which video model?", shows_when: {},
    options: [{
      n: 1, text: "MiniMax H3", detail: "great quality, best value", price: null,
      rate_usd: modelOne ? modelOne.rate_usd : 0.04,
      unit: modelOne ? modelOne.unit : "second",
      shot_s: modelOne ? modelOne.shot_s : 15,
      keyframe_usd: 0.02, song_usd: 0.06, redo_rate: 0.5, keyframe_count_extra: 7,
    }],
  };
  const questions = [lengthScreen, modelScreen];

  const draw = (picks) => {
    state.page = "questions";
    state.questions = questions;
    state.visible = questions;
    state.visibleFrom = questions;
    state.qIndex = 1;
    state.picks = picks;
    state.texts = [];
    state.note = "";
    render();
    return pageText();
  };

  const before = draw([]);
  rule("(2) with no length answered the option names the reason, no figure",
    before.includes("price shown after you pick a length"), before.slice(0, 200));
  rule("(2) and it shows no dollar figure at all", !/\$\d/.test(before), before.slice(0, 200));

  const at180 = draw(["4"]);
  const want180 = fixture && fixture.models && fixture.models["1"]
    ? Number(fixture.models["1"].prices_usd["180"]).toFixed(2) : "11.46";
  rule("(1) the drawn price follows the LENGTH answer",
    at180.includes(`about $${want180}`), at180.slice(0, 240));
}

// ── (3) the recap: plain wording and option text, never a number or a label ─
{
  const questions = [
    { id: "purpose", label: "PURPOSE", title: "What is this video for?", typed: false,
      question: "What is this video for?", shows_when: {}, options: [
        { n: 1, text: "Grow my business", detail: "" },
        { n: 2, text: "Teach a lesson", detail: "" },
      ] },
    { id: "music", label: "MUSIC STYLE", title: "The sound", typed: false,
      question: "Which sound fits your story?", shows_when: {}, options: [
        { n: 1, text: "Soul Ballad", detail: "" },
        { n: 2, text: "R&B Flow", detail: "" },
      ] },
  ];
  state.page = "recap";
  state.questions = questions;
  state.visible = questions;
  state.visibleFrom = questions;
  state.picks = ["1", "2"];
  state.texts = [];
  state.locked = false;
  state.orderId = null;
  render();

  const rows = ruleText();
  rule("(3) the recap draws one line per question", rows.length >= 2, `${rows.length} button(s)`);
  rule("(3) a row names the question in plain words", rows.some((t) => t.includes("The sound")),
    rows.join(" / "));
  rule("(3) and the option TEXT the client picked", rows.some((t) => t.includes("R&B Flow")),
    rows.join(" / "));
  rule("(3) an upper-case label is never the heading",
    !rows.some((t) => /MUSIC STYLE|PURPOSE/.test(t)), rows.join(" / "));
  rule("(3) the option number is never the answer",
    !rows.some((t) => /:\s*2\s*$/.test(t)), rows.join(" / "));
}

// ── (4) the reply travels with its text, for the box to compare (U-K04) ─────
{
  const screen = { id: "music", options: [
    { n: 1, text: "Soul Ballad", detail: "" },
    { n: 2, text: "R&B Flow", detail: "" },
    { n: 3, text: "Type it in", detail: "Reply with your own words." },
  ] };
  rule("(4) a pick is sent as \"<n>. <option text>\"",
    answerReply(screen, "2", "") === "2. R&B Flow", answerReply(screen, "2", ""));
  rule("(4) a typed answer is sent exactly as typed",
    answerReply(screen, "3", "  a slow gospel hymn  ") === "a slow gospel hymn",
    answerReply(screen, "3", "  a slow gospel hymn  "));
  rule("(4) an unanswered screen sends nothing",
    answerReply(screen, "", "") === "" && answerReply(screen, "2", "") !== "");
}

delete globalThis.document;

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\nprice check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\nprice check OK: ${results.length} rules passed (fixture-pinned, DOM shim, no browser)`);
process.exit(0);
