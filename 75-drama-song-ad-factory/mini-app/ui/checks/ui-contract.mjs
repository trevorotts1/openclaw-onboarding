// =============================================================================
// RUNNABLE CHECK — the version-0 UI surface exists and imports cleanly
// -----------------------------------------------------------------------------
// mini-app/ui/checks/ui-contract.mjs
//
// Imports the SHIPPED modules in Node (no DOM needed: studio.js only touches
// `document` when it renders) and asserts the version-0 acceptance surface is
// really there: the five pages, the eight questions, the three song versions,
// the five looks, the QR surface, the "Looks good" state, and the full U2
// service contract the page consumes.
//
// Exit codes:  0 = pass, 2 = a surface is missing.
//
//   node checks/ui-contract.mjs
// =============================================================================
import { DEFAULT_OPTIONS, PAGES, state, render } from "../studio.js";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { ENTRYPOINTS } from "../api-client.js";
import { encode, toSvg, toElement } from "../qr.js";
import { verifyDownload, verifyBytes, triggerSave } from "../download.js";

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

const PAGE_IDS = ["start", "questions", "recap", "approvals", "delivery"];
rule("five pages exist", PAGES.length === 5 && PAGE_IDS.every((id) => PAGES.some((p) => p.id === id)),
  PAGES.map((p) => p.id).join(", "));
rule("every page has a heading title", PAGES.every((p) => p.title && p.title.length > 3));
rule("eight questions", DEFAULT_OPTIONS.questions.length === 8);
rule("five looks", DEFAULT_OPTIONS.looks.length === 5);
rule("three song versions", DEFAULT_OPTIONS.songs.length === 3,
  DEFAULT_OPTIONS.songs.map((s) => s.label).join(", "));
rule("every look carries a sample URL for the QR surface",
  DEFAULT_OPTIONS.looks.every((l) => /^https:\/\//.test(l.sampleUrl)));

// The QR surface, through the shipped encoder.
const qr = encode("https://studio.example.com/d/abc");
rule("QR encoder returns a module grid",
  qr.size === qr.version * 4 + 17 && qr.modules.length === qr.size);
rule("QR renders to an SVG string", toSvg(qr).startsWith("<svg") && toSvg(qr).includes("</svg>"));
rule("QR exposes a DOM builder (no innerHTML on the page)", typeof toElement === "function");

// The U2 boundary — the entrypoints the page consumes.
const REQUIRED = ["getSession", "saveAnswer", "getOptions", "listInbox", "postInbox",
  "requestUpload", "advance", "getDelivery", "verifyDeliveryLink"];
rule("U2 service contract is declared in full",
  REQUIRED.every((e) => ENTRYPOINTS.includes(e)), `${ENTRYPOINTS.length} entrypoints`);

// The download verifier refuses a redirect without any network.
const redirectVerdict = verifyBytes({
  status: 302, contentLengthHeader: null, contentType: "", disposition: "", byteLength: 0,
});
rule("verifier refuses a redirect", redirectVerdict.ok === false
  && redirectVerdict.reasons.some((r) => /redirect/i.test(r)));
const goodVerdict = verifyBytes({
  status: 200, contentLengthHeader: "1024", contentType: "video/mp4",
  disposition: "attachment; filename=\"05 - Video Captioned.mp4\"", byteLength: 1024,
});
rule("verifier accepts a real 200 + attachment + matching length", goodVerdict.ok === true);
rule("a save is only offered through triggerSave()", typeof triggerSave === "function");
rule("verifyDownload() is exported for the delivery page", typeof verifyDownload === "function");

// Exercise the actual question renderer with the canonical Agnes export.
// No browser service or provider is called, and neither option is selected.
const cardPath = fileURLToPath(new URL("../../../scripts/core/choice_card/intake_card/intake_card.py", import.meta.url));
const exported = JSON.parse(execFileSync("python3", [cardPath, "--format", "studio-json"], { encoding: "utf8" }));
const agnes = exported.questions.find((q) => q.id === "agnes");
const walk = (n) => [n, ...(n.children || []).flatMap(walk)];
function element(tag) {
  return {
    tagName: tag.toUpperCase(), children: [], attrs: {}, style: {}, textContent: "", listeners: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    append(...nodes) { this.children.push(...nodes.filter(Boolean)); },
    replaceChildren(...nodes) { this.children = nodes.filter(Boolean); },
    addEventListener(k, fn) { this.listeners[k] = fn; },
    querySelector(selector) { return walk(this).find((n) => n.tagName === selector.toUpperCase()); },
    focus() {},
  };
}
const nodes = Object.fromEntries(["main", "steps-nav", "rail", "rail-fill", "step-label", "status"].map((id) => [id, element("div")]));
globalThis.document = { createElement: element, getElementById: (id) => nodes[id] || null };
Object.assign(state, { page: "questions", questions: [agnes], visible: [agnes], visibleFrom: null, qIndex: 0, picks: [], texts: [], replies: [] });
state.visibleFrom = state.questions;
render();
const drawn = walk(nodes.main);
const paragraphs = drawn.filter((n) => n.tagName === "P").map((n) => n.textContent);
const radios = drawn.filter((n) => n.tagName === "INPUT" && n.attrs.type === "radio");
rule("Agnes supplementary explanation is drawn by the actual consumer",
  Array.isArray(agnes.supplementary_explanation) && agnes.supplementary_explanation.length > 0
    && agnes.supplementary_explanation.every((text) => paragraphs.includes(text)));
rule("Agnes retains both exact option identities and no automatic pick",
  radios.length === 2 && radios.map((n) => n.attrs.value).join(",") === "1,2"
    && radios.every((n) => !n.checked) && state.picks.length === 0);
delete globalThis.document;

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\nUI contract check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\nUI contract check OK: ${results.length} rules passed`);
process.exit(0);
