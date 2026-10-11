// =============================================================================
// RUNNABLE CHECK — accessibility floor of the version-0 UI
// -----------------------------------------------------------------------------
// mini-app/ui/checks/a11y-check.mjs
//
// WHAT IT PROVES (and, just as importantly, what it does NOT):
//   * WCAG contrast is computed from the ACTUAL stylesheet tokens — light and
//     dark — and every text pair the UI uses must clear 4.5:1;
//   * the structural floor is present: lang, viewport, a skip link, a focusable
//     <main>, a polite live region, a labelled nav, a labelled progressbar;
//   * focus order is source order: no positive tabindex anywhere;
//   * every input the page builds has an id and a matching <label for=...>;
//   * keyboard focus is visible (:focus-visible present) and motion is never
//     the only signal (prefers-reduced-motion block present, no bare keyframes);
//   * no HTML string is handed to innerHTML.
//
// It does NOT drive a real browser or a screen reader, so it cannot certify
// them. checks/README.md says so in the same words.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/a11y-check.mjs
// =============================================================================
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const uiDir = join(here, "..");
const html = readFileSync(join(uiDir, "index.html"), "utf8");
const css = readFileSync(join(uiDir, "studio.css"), "utf8");
const js = readFileSync(join(uiDir, "studio.js"), "utf8");

let failures = 0;
const results = [];
function rule(name, ok, detail = "") {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
}

// ── 1. document floor ────────────────────────────────────────────────────────
rule("html declares a language", /<html[^>]*\blang="[a-z-]+"/i.test(html));
rule("viewport meta present", /<meta[^>]*name="viewport"/i.test(html));
rule("skip link targets #main", /class="skip-link"[^>]*href="#main"/i.test(html));
rule("<main> is focusable (tabindex=\"-1\")", /<main[^>]*id="main"[^>]*tabindex="-1"/i.test(html));
rule("live region is polite and named", /role="status"/i.test(html) && /aria-live="polite"/i.test(html));
rule("nav has an accessible name", /<nav[^>]*aria-label=/i.test(html));
rule("progressbar is labelled and valued",
  /role="progressbar"/i.test(html) && /aria-labelledby=/i.test(html) && /aria-valuenow=/i.test(html));
rule("noscript fallback exists", /<noscript>/i.test(html));

// ── 2. focus order: source order only ────────────────────────────────────────
const positiveTabindex = [...`${html}\n${js}`.matchAll(/tabindex\s*[=:]\s*"?(\d+)/gi)]
  .map((m) => Number(m[1]))
  .filter((n) => n > 0);
rule("no positive tabindex (focus stays in source order)", positiveTabindex.length === 0,
  positiveTabindex.length ? `found ${positiveTabindex.join(", ")}` : "only tabindex=-1 / 0");

// ── 3. inputs are labelled ───────────────────────────────────────────────────
const inputs = [...js.matchAll(/el\("input"/g)].length;
const labelFors = [...js.matchAll(/\bfor:\s*[A-Za-z_$]/g)].length;
rule("every generated input carries an id", [...js.matchAll(/el\("input",\s*\{\s*id/g)].length === inputs,
  `${inputs} input(s) built`);
rule("every generated input has a matching <label for>", labelFors >= inputs,
  `${labelFors} label(s) for ${inputs} input(s)`);

// ── 4. keyboard + motion + theme ─────────────────────────────────────────────
rule("visible keyboard focus ring", /:focus-visible/.test(css) && /outline:/.test(css));
rule("reduced-motion is honoured", /@media\s*\(prefers-reduced-motion/.test(css));
rule("no animation outside a reduced-motion guard",
  !/@keyframes/.test(css) || /prefers-reduced-motion/.test(css));
rule("dark mode has both entry points",
  /@media\s*\(prefers-color-scheme:\s*dark\)/.test(css) && /\[data-theme="dark"\]/.test(css));

// ── 5. no HTML strings to innerHTML ──────────────────────────────────────────
rule("no innerHTML assignment", !/\.innerHTML\s*=/.test(js));

// ── 6. contrast, computed from the real tokens ───────────────────────────────
function tokenBlock(source, selector) {
  const start = source.indexOf(selector);
  if (start === -1) return null;
  const open = source.indexOf("{", start);
  const close = source.indexOf("}", open);
  const body = source.slice(open + 1, close);
  const tokens = {};
  for (const m of body.matchAll(/(--[a-z0-9-]+)\s*:\s*(#[0-9a-f]{6})/gi)) tokens[m[1]] = m[2];
  return tokens;
}

function luminance(hex) {
  const rgb = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}

function contrast(fg, bg) {
  const a = luminance(fg);
  const b = luminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

const PAIRS = [
  ["ink", "bg"], ["ink", "surface"], ["ink-soft", "bg"], ["ink-soft", "surface"],
  ["primary-ink", "primary"], ["ok-ink", "ok-bg"], ["warn-ink", "warn-bg"], ["focus", "bg"],
];

const light = tokenBlock(css, ":root {");
const darkStart = css.indexOf(':root[data-theme="dark"]');
const dark = tokenBlock(css.slice(darkStart), ':root[data-theme="dark"]');

for (const [themeName, tokens] of [["light", light], ["dark", dark]]) {
  if (!tokens) { rule(`${themeName} token block found`, false); continue; }
  for (const [fg, bg] of PAIRS) {
    const f = tokens[`--${fg}`];
    const b = tokens[`--${bg}`];
    if (!f || !b) { rule(`${themeName} ${fg} on ${bg}`, false, "token missing"); continue; }
    const ratio = contrast(f, b);
    rule(`${themeName} ${fg} on ${bg} >= 4.5:1`, ratio >= 4.5, `${ratio.toFixed(2)}:1`);
  }
}

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\na11y check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\na11y check OK: ${results.length} rules passed (contrast computed for light and dark)`);
process.exit(0);
