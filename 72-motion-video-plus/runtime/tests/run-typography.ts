// Typography tests for MG-013 (Directive Section 6 MG-013, test T07).
//
// Pure, deterministic, offline: measurement parses the actual Liberation
// Sans font binaries on this box (the same files and sha256 values MG-006
// recorded for render fonts). The cases pin (1) the tokens table to the
// directive's exact role ranges, (2) the hand-rolled font parser against
// the real font's known metrics, (3) every fixture layout under
// tests/fixtures/typography to its expected audit verdict, isolating each
// T07 failure shape (long copy, missing font, substituted font, small
// placement, clipping, protected-area overlap), and (4) the fit decider's
// three outcomes, including the structural rule that it can never return
// a below-floor size as a solution.
//
// Exit code 0 when every case passes, 1 otherwise.

import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import {
  auditLayout,
  decideFit,
  loadFontFile,
  loadTypographyTokens,
  measureString,
  type LayoutRecord,
} from "../src/typography";

const REGULAR_PATH =
  "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf";
const BOLD_PATH =
  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf";
const REGULAR_SHA256 =
  "4659bc0c58c5028dd488ec928d41d9265db43d9b669fc14ca8b0832daca7b144";
const BOLD_SHA256 =
  "3973aa5054fb467dd5627245d3dc82e37bf16fe075756156a570455871351582";

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8")) as unknown;
}

let passed = 0;
let failed = 0;
function report(ok: boolean, line: string, detail?: string): void {
  if (ok) passed += 1;
  else failed += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${line}`);
  if (!ok && detail) console.log(`  ${detail}`);
}

const tokens = loadTypographyTokens();

// ---------------------------------------------------------------------
// 1. Tokens integrity: the role table is the directive's table.
// ---------------------------------------------------------------------
{
  const expect: Record<string, [number, number, number]> = {
    headline: [96, 160, 96],
    hero_number: [180, 300, 180],
    essential_support: [54, 72, 54],
    cta: [72, 110, 72],
  };
  for (const [role, [min, max, floor]] of Object.entries(expect)) {
    const t = tokens.role(role);
    report(
      t !== null && t.minPx === min && t.maxPx === max && t.floorPx === floor && t.essential,
      `role ${role} carries the directive range ${min}-${max} with floor ${floor}`,
      t ? `got ${t.minPx}-${t.maxPx} floor ${t.floorPx}` : "role missing"
    );
  }
  report(
    tokens.statement.includes("not universal accessibility standards"),
    "tokens state plainly that the ranges are BlackCEO defaults, not universal accessibility standards"
  );
  report(
    tokens.roles.every((r) => r.floorPx === r.minPx),
    "every role floor equals its range minimum (no hidden smaller size inside a band)"
  );
  const exceptionRoles = ["axis_tick", "caption_metadata", "decorative_label", "disclosure"];
  report(
    exceptionRoles.every((name) => {
      const r = tokens.role(name);
      return r !== null && r.exception !== null && r.exception.id.length > 0 && r.exception.bound.length > 0;
    }),
    "every exception role names its exception and states its bound"
  );
  report(
    ["chart_category_label", "chart_value"].every((name) => {
      const r = tokens.role(name);
      return r !== null && r.essential && r.exception === null;
    }),
    "chart label and chart value are essential roles with no exception path"
  );
}

// ---------------------------------------------------------------------
// 2. Font parser against the real font binaries.
// ---------------------------------------------------------------------
const regular = loadFontFile(REGULAR_PATH);
const bold = loadFontFile(BOLD_PATH);
{
  report(regular.unitsPerEm === 2048, "Liberation Sans regular parses to 2048 units per em", `got ${regular.unitsPerEm}`);
  report(regular.familyName === "Liberation Sans", "regular family name comes from the font's own name table", `got ${regular.familyName}`);
  report(regular.weightClass === 400 && bold.weightClass === 700, "weight classes parse as 400 (regular) and 700 (bold)", `got ${regular.weightClass}/${bold.weightClass}`);
  report(regular.capHeightUnits === 1409, "cap height parses from OS/2 sCapHeight as 1409 units", `got ${regular.capHeightUnits}`);
  report(
    regular.sha256 === REGULAR_SHA256 && bold.sha256 === BOLD_SHA256,
    "font sha256 values match the MG-006 render-font evidence exactly"
  );
  const h = measureString(regular, "H", 100);
  report(
    h.capHeightPx !== null && Math.abs(h.capHeightPx - 68.8) < 0.05,
    "cap height of 'H' at 100 px measures 68.8 px from the font's own tables",
    `got ${h.capHeightPx}`
  );
}

// ---------------------------------------------------------------------
// 3. Fixture layout audits.
// ---------------------------------------------------------------------
function loadFixture(name: string): LayoutRecord {
  const path = join(fixturesRoot(), "typography", `${name}.json`);
  if (!existsSync(path)) throw new Error(`missing typography fixture ${path}`);
  return readJson(path) as LayoutRecord;
}

function kindsFor(result: ReturnType<typeof auditLayout>, elementId: string): string[] {
  return result.findings
    .filter((f) => f.elementId === elementId)
    .map((f) => f.kind);
}

{
  const audit = auditLayout(loadFixture("pass-full-frame"), tokens);
  report(audit.pass, "pass-full-frame: full-frame roles in range audit clean", JSON.stringify(audit.findings));
  const headline = audit.measurements.find((m) => m.elementId === "headline");
  report(
    headline !== undefined && headline.lineCount === 2 && headline.widestLinePx > 1370 && headline.widestLinePx < 1376,
    "pass-full-frame: headline wraps to 2 measured lines, widest about 1373 px",
    headline ? `got ${headline.lineCount} lines, widest ${headline.widestLinePx}` : "no measurement"
  );
  console.log(
    `  worked measurement: "Every region grew this quarter" in Liberation Sans Bold at 128 px: ` +
      `lines ${headline?.lineCount}, widest line ${headline?.widestLinePx} px, ` +
      `total height ${headline?.totalHeightPx} px, cap height ${headline?.capHeightPx} px`
  );
}
{
  const audit = auditLayout(loadFixture("pass-inset"), tokens);
  report(audit.pass, "pass-inset: inset at 1440 wide still passes at effective sizes", JSON.stringify(audit.findings));
  const eff = Object.fromEntries(audit.measurements.map((m) => [m.elementId, m.effectiveSizePx]));
  report(
    eff.headline === 120 && eff.support === 54 && eff.cta === 72,
    "pass-inset: effective sizes are 120 (headline), 54 (support), 72 (cta) at scale 0.75",
    JSON.stringify(eff)
  );
}
{
  const audit = auditLayout(loadFixture("pass-mobile"), tokens);
  report(audit.pass, "pass-mobile: recomposed 1080x1920 layout passes measured on its own canvas", JSON.stringify(audit.findings));
  report(
    audit.measurements.every((m) => m.placementScale === 1),
    "pass-mobile: recomposed placements are judged at authored size, never inherited from landscape"
  );
}
{
  const audit = auditLayout(loadFixture("pass-chart-labels"), tokens);
  report(audit.pass, "pass-chart-labels: category labels, values, ticks, and disclosure pass destination-size review", JSON.stringify(audit.findings));
}
{
  const audit = auditLayout(loadFixture("fail-oversized-headline"), tokens);
  report(
    !audit.pass && kindsFor(audit, "headline").includes("TYPO_CLIPPING") && kindsFor(audit, "support").length === 0,
    "fail-oversized-headline: oversized copy clips instead of shrinking; the passing support element stays clean",
    JSON.stringify(audit.findings)
  );
}
{
  const audit = auditLayout(loadFixture("fail-inset-effective"), tokens);
  const eff = Object.fromEntries(audit.measurements.map((m) => [m.elementId, m.effectiveSizePx]));
  report(
    !audit.pass &&
      kindsFor(audit, "headline").includes("TYPO_BELOW_FLOOR") &&
      kindsFor(audit, "cta").includes("TYPO_BELOW_FLOOR") &&
      eff.headline === 56 &&
      eff.cta === 44,
    "fail-inset-effective: sizes that pass at source (112, 88) fail at destination (56, 44) in a half-width inset",
    JSON.stringify(audit.findings)
  );
}
{
  const audit = auditLayout(loadFixture("fail-missing-font"), tokens);
  report(
    !audit.pass && audit.findings.some((f) => f.kind === "TYPO_FONT_MISSING") && audit.measurements.length === 0,
    "fail-missing-font: a missing font file is a named finding and nothing is measured with a substitute",
    JSON.stringify(audit.findings)
  );
}
{
  const audit = auditLayout(loadFixture("fail-substituted-font"), tokens);
  report(
    !audit.pass && audit.findings.some((f) => f.kind === "TYPO_FONT_SUBSTITUTED") && audit.measurements.length === 0,
    "fail-substituted-font: requesting Liberation Serif with Sans bytes is reported as substitution, never measured as serif",
    JSON.stringify(audit.findings)
  );
}
{
  const audit = auditLayout(loadFixture("fail-protected-conflict"), tokens);
  report(
    !audit.pass &&
      kindsFor(audit, "cta").includes("TYPO_PROTECTED_CONFLICT") &&
      !kindsFor(audit, "cta").includes("TYPO_CLIPPING"),
    "fail-protected-conflict: the CTA box over the logo zone is the isolated failure",
    JSON.stringify(audit.findings)
  );
}
{
  const record = loadFixture("fail-below-floor-long-copy");
  const audit = auditLayout(record, tokens);
  report(
    !audit.pass &&
      kindsFor(audit, "headline").includes("TYPO_BELOW_FLOOR") &&
      !kindsFor(audit, "headline").includes("TYPO_CLIPPING"),
    "fail-below-floor-long-copy: the shrunk 88 px headline fits its box and still fails, on the floor",
    JSON.stringify(audit.findings)
  );
  const el = record.elements[0];
  const fit = decideFit({
    copy: el.copy,
    role: tokens.role("headline") as NonNullable<ReturnType<typeof tokens.role>>,
    box: { widthPx: el.box.width, heightPx: el.box.height },
    font: bold,
  });
  report(
    fit.outcome === "below_floor" && fit.wouldFitSizePx < 96 && fit.wouldFitSizePx >= 72,
    "fail-below-floor-long-copy: the decider agrees the copy fits only below the floor (would-fit size is evidence, not a size)",
    JSON.stringify(fit)
  );
}
{
  // Missing glyph: an emoji codepoint Liberation Sans has no glyph for.
  const record = loadFixture("pass-full-frame");
  record.elements = [
    {
      id: "glyph",
      role: "headline",
      copy: "Growth 😀",
      sizePx: 128,
      box: { x: 120, y: 80, width: 1200, height: 200 },
      placement: { kind: "full_frame" },
    },
  ];
  const audit = auditLayout(record, tokens);
  report(
    !audit.pass && kindsFor(audit, "glyph").includes("TYPO_MISSING_GLYPH"),
    "missing glyph: a codepoint with no glyph in the actual font is reported, not rendered as a silent .notdef",
    JSON.stringify(audit.findings)
  );
}

// ---------------------------------------------------------------------
// 4. The fit decider: three outcomes, and no below-floor solution.
// ---------------------------------------------------------------------
{
  const headline = tokens.role("headline") as NonNullable<ReturnType<typeof tokens.role>>;
  const support = tokens.role("essential_support") as NonNullable<ReturnType<typeof tokens.role>>;

  const fits = decideFit({
    copy: "Every region grew this quarter",
    role: headline,
    box: { widthPx: 1600, heightPx: 340 },
    font: bold,
    requestedSizePx: 128,
  });
  report(
    fits.outcome === "fits" && fits.sizePx === 128 && fits.lineCount === 2,
    "decider fits: headline at its requested 128 px with measured line breaks",
    JSON.stringify(fits)
  );

  const settled = decideFit({
    copy: "Why owners are switching this quarter",
    role: headline,
    box: { widthPx: 1500, heightPx: 400 },
    font: bold,
    requestedSizePx: 160,
  });
  report(
    settled.outcome === "fits" && settled.sizePx >= 96 && settled.sizePx < 160,
    "decider settles inside the band: 160 px does not fit, a legal in-band size does (never below the floor)",
    JSON.stringify(settled)
  );

  const split = decideFit({
    copy: "Bookings doubled after the new onboarding flow shipped in March. Retention climbed with it, and churn fell for the third straight quarter.",
    role: support,
    box: { widthPx: 900, heightPx: 150 },
    font: regular,
  });
  report(
    split.outcome === "restructure_required" && split.viablePath === "split",
    "decider restructure: support copy that fits two sequential boxes at floor size is told to split",
    JSON.stringify(split)
  );

  const shortenVolume = decideFit({
    copy: "Bookings doubled. Retention climbed. Churn fell. Referrals rose. Upgrades increased. Renewals held steady. Support tickets dropped. Onboarding shortened. Activation improved. Expansion revenue grew.",
    role: support,
    box: { widthPx: 900, heightPx: 150 },
    font: regular,
  });
  report(
    shortenVolume.outcome === "restructure_required" && shortenVolume.viablePath === "shorten",
    "decider restructure: copy too large for two boxes at floor size is told to shorten",
    JSON.stringify(shortenVolume)
  );

  const shortenWord = decideFit({
    copy: "Antidisestablishmentarianismexplained",
    role: support,
    box: { widthPx: 700, heightPx: 150 },
    font: regular,
  });
  report(
    shortenWord.outcome === "restructure_required" && shortenWord.viablePath === "shorten",
    "decider restructure: a single unbreakable word wider than the box cannot be split, only shortened",
    JSON.stringify(shortenWord)
  );

  const below = decideFit({
    copy: "Growth in every single region",
    role: headline,
    box: { widthPx: 1250, heightPx: 130 },
    font: bold,
  });
  report(
    below.outcome === "below_floor" && !("sizePx" in below),
    "decider below_floor: the result type carries no sizePx field, so a below-floor shrink cannot be consumed as a solution",
    JSON.stringify(below)
  );
}

console.log(`Typography: ${passed}/${passed + failed} checks passed, ${failed} failed.`);
process.exit(failed === 0 ? 0 : 1);
