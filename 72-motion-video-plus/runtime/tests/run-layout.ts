// MG-014 layout-variant tests: shared content stored once, one
// layout record per destination, recomposition proven geometrically,
// data scales comparable numerically across variants, safe areas
// from the destination's own player profile, and the placement
// audit judging every variant at the size it will actually be
// seen: a full-frame pass must not rescue an inset whose effective
// text sizes fall below their role floors.
//
// Fixtures live under tests/fixtures/layout/ (override the fixtures
// root with MOTION_FIXTURES_ROOT). Expected numbers are pinned in
// tests/evidence/mg014/measurements.json; the suite fails on drift
// rather than rewriting the record.

import * as fs from "fs";
import * as path from "path";
import {
  LayoutError,
  assertLayoutVariant,
  assertSharedContent,
  auditPlacement,
  isScaledDuplicate,
  placementFacts,
  resolveVariantSet,
  type LayoutVariant,
  type SharedContentRecord,
} from "../src/layout";
import { loadTypographyTokens } from "../src/typography";

let passed = 0;
let failed = 0;

function report(ok: boolean, name: string, detail = ""): void {
  if (ok) {
    passed += 1;
    console.log(`PASS ${name}${detail ? ` (${detail})` : ""}`);
  } else {
    failed += 1;
    console.log(`FAIL ${name}${detail ? ` (${detail})` : ""}`);
  }
}

const fixturesRoot = process.env.MOTION_FIXTURES_ROOT
  ? path.resolve(process.env.MOTION_FIXTURES_ROOT)
  : path.resolve(__dirname, "..", "..", "..", "tests", "fixtures");
const layoutDir = path.join(fixturesRoot, "layout");
const evidencePath = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "tests",
  "evidence",
  "mg014",
  "measurements.json"
);

interface FixtureSet {
  content: SharedContentRecord;
  variants: LayoutVariant[];
}

function loadFixture(file: string): FixtureSet {
  const raw = JSON.parse(fs.readFileSync(path.join(layoutDir, file), "utf8")) as {
    content: unknown;
    variants: unknown[];
  };
  return {
    content: assertSharedContent(raw.content),
    variants: raw.variants.map((v) => assertLayoutVariant(v)),
  };
}

function variant(set: FixtureSet, id: string): LayoutVariant {
  const found = set.variants.find((v) => v.id === id);
  if (!found) throw new Error(`fixture variant "${id}" missing`);
  return found;
}

function approx(a: number, b: number, eps = 1e-9): boolean {
  return Math.abs(a - b) <= eps;
}

const tokens = loadTypographyTokens();
const evidence = JSON.parse(fs.readFileSync(evidencePath, "utf8")) as {
  comparability: {
    desktop: { plot_extent_px: number; pixels_per_unit: number; normalized_positions: Record<string, number> };
    mobile: { plot_extent_px: number; pixels_per_unit: number; normalized_positions: Record<string, number> };
  };
  inset_acceptance: { inset_scale: number; headline_effective_px: number };
  image_crops: {
    desktop_crop: { x: number; y: number; width: number; height: number };
    mobile_crop: { x: number; y: number; width: number; height: number };
    mobile_center_crop_x: number;
  };
};

// ---- 1. Chart job: desktop + genuinely recomposed mobile ---------
{
  const set = loadFixture("chart-desktop-mobile.json");
  const resolution = resolveVariantSet(set.content, set.variants);
  report(
    resolution.pass && resolution.findings.length === 0,
    "chart job: desktop and recomposed mobile variants resolve clean",
    resolution.findings.map((f) => f.kind).join(",") || "no findings"
  );
  const desktop = variant(set, "chart-desktop");
  const mobile = variant(set, "chart-mobile");
  report(
    isScaledDuplicate(desktop, mobile) === false,
    "chart job: mobile variant is not a scaled duplicate of the desktop"
  );

  const dFacts = resolution.results.find((r) => r.variantId === "chart-desktop")?.scaleFacts;
  const mFacts = resolution.results.find((r) => r.variantId === "chart-mobile")?.scaleFacts;
  const ev = evidence.comparability;
  report(
    !!dFacts &&
      dFacts.extentPx === ev.desktop.plot_extent_px &&
      dFacts.pixelsPerUnit === ev.desktop.pixels_per_unit,
    "comparability: desktop scale is 1200 px over domain [0, 30], 40 px per unit",
    dFacts ? `extent=${dFacts.extentPx} pxPerUnit=${dFacts.pixelsPerUnit}` : "no facts"
  );
  report(
    !!mFacts &&
      mFacts.extentPx === ev.mobile.plot_extent_px &&
      approx(mFacts.pixelsPerUnit, ev.mobile.pixels_per_unit, 1e-6),
    "comparability: mobile scale is 740 px over the same domain, about 24.6667 px per unit",
    mFacts ? `extent=${mFacts.extentPx} pxPerUnit=${mFacts.pixelsPerUnit}` : "no facts"
  );
  const normalizedAgree =
    !!dFacts &&
    !!mFacts &&
    dFacts.normalizedPositions.every((p) => {
      const other = mFacts.normalizedPositions.find((q) => q.rowId === p.rowId);
      const recorded = ev.desktop.normalized_positions[p.rowId];
      return (
        !!other &&
        approx(p.normalized, other.normalized) &&
        approx(p.normalized, recorded)
      );
    });
  report(
    normalizedAgree,
    "comparability: values 12, 18, 30 land at 0.4, 0.6, 1.0 of the plot extent in BOTH variants",
    dFacts
      ? dFacts.normalizedPositions.map((p) => `${p.rowId}=${p.normalized}`).join(" ")
      : ""
  );

  const mobileAudit = auditPlacement(set.content, mobile, tokens);
  report(
    mobileAudit.pass && mobileAudit.typography.pass,
    "chart job: mobile placement audit passes (labels legible at full size, no center crop)",
    mobileAudit.typography.findings.map((f) => f.kind).join(",") || "no findings"
  );
  const desktopAudit = auditPlacement(set.content, desktop, tokens);
  report(
    desktopAudit.pass,
    "chart job: desktop placement audit passes",
    desktopAudit.typography.findings.map((f) => f.kind).join(",") || "no findings"
  );
}

// ---- 2. Scale-only mobile variant is refused ----------------------
{
  const set = loadFixture("chart-scale-only-mobile.json");
  const resolution = resolveVariantSet(set.content, set.variants);
  const mobileResult = resolution.results.find((r) => r.variantId === "chart-mobile-scaled");
  const desktopResult = resolution.results.find((r) => r.variantId === "chart-desktop");
  report(
    !resolution.pass &&
      !!mobileResult &&
      mobileResult.findings.some((f) => f.kind === "LAYOUT_SCALED_DUPLICATE"),
    "scale-only mobile variant is rejected with LAYOUT_SCALED_DUPLICATE",
    mobileResult ? mobileResult.findings.map((f) => f.kind).join(",") : "missing"
  );
  report(
    !!desktopResult && desktopResult.pass,
    "scale-only fixture: the desktop sibling itself is clean",
    desktopResult ? desktopResult.findings.map((f) => f.kind).join(",") || "no findings" : "missing"
  );
  report(
    isScaledDuplicate(variant(set, "chart-desktop"), variant(set, "chart-mobile-scaled")) === true,
    "scaled-duplicate detector agrees on the raw geometry"
  );
}

// ---- 3. PowerPoint: full-frame passes, the inset fails ------------
{
  const set = loadFixture("powerpoint-inset.json");
  const full = variant(set, "ppt-full-slide");
  const inset = variant(set, "ppt-inset");
  const insetMm = variant(set, "ppt-inset-mm");

  const fullAudit = auditPlacement(set.content, full, tokens);
  report(
    fullAudit.pass && fullAudit.typography.pass,
    "powerpoint: the full-slide placement passes the placement audit",
    fullAudit.typography.findings.map((f) => f.kind).join(",") || "no findings"
  );

  const facts = placementFacts(inset);
  report(
    facts.scale === evidence.inset_acceptance.inset_scale && facts.basis === "declared_px",
    "powerpoint: inset at 960x540 on the 1920x1080 canvas is scale 0.5",
    `scale=${facts.scale} basis=${facts.basis}`
  );
  const insetAudit = auditPlacement(set.content, inset, tokens);
  const headlineFinding = insetAudit.typography.findings.find(
    (f) => f.kind === "TYPO_BELOW_FLOOR" && f.elementId === "headline"
  );
  report(
    !insetAudit.pass &&
      !!headlineFinding &&
      headlineFinding.measured?.effectiveSizePx === evidence.inset_acceptance.headline_effective_px,
    "ACCEPTANCE: inset placement FAILS although the full-frame passes: headline effective 64 px under the 96 px floor",
    headlineFinding
      ? `effective=${headlineFinding.measured?.effectiveSizePx} floor=${headlineFinding.measured?.floorPx}`
      : "no headline floor finding"
  );

  const mmFacts = placementFacts(insetMm);
  report(
    mmFacts.basis === "declared_mm" &&
      mmFacts.displayWidthPx === 960 &&
      mmFacts.displayHeightPx === 540 &&
      mmFacts.scale === 0.5,
    "powerpoint: a millimetre declaration converts through the slide's own px-per-mm (169.333 mm on a 338.667 mm slide = 960 px)",
    `display=${mmFacts.displayWidthPx}x${mmFacts.displayHeightPx} scale=${mmFacts.scale}`
  );
  const mmAudit = auditPlacement(set.content, insetMm, tokens);
  report(
    !mmAudit.pass,
    "powerpoint: the millimetre-declared inset fails the same way"
  );
}

// ---- 4. Safe-area violation against the caption-band profile -----
{
  const set = loadFixture("mobile-safe-area.json");
  const resolution = resolveVariantSet(set.content, set.variants);
  const unsafe = resolution.findings.filter((f) => f.kind === "LAYOUT_UNSAFE_ZONE");
  report(
    !resolution.pass &&
      unsafe.length === 1 &&
      unsafe[0].elementId === "disclosure" &&
      unsafe[0].measured?.zone === "caption-band",
    "safe area: disclosure inside the player caption band is the one finding",
    unsafe.map((f) => `${f.elementId}@${f.measured?.zone}`).join(",") || "none"
  );
  const desktopResult = resolution.results.find((r) => r.variantId === "chart-desktop");
  report(
    !!desktopResult && desktopResult.pass,
    "safe area fixture: the desktop variant is unaffected"
  );
}

// ---- 5. Three-column comparison staged across mobile beats -------
{
  const set = loadFixture("chart-staged-mobile.json");
  const resolution = resolveVariantSet(set.content, set.variants);
  report(
    resolution.pass,
    "staged comparison: desktop columns and mobile staged rows resolve clean",
    resolution.findings.map((f) => f.kind).join(",") || "no findings"
  );
  const mobile = variant(set, "quarter-mobile-staged");
  const stagedBeats = mobile.arrangement?.beats;
  report(
    mobile.arrangement?.kind === "staged_rows" &&
      stagedBeats !== undefined &&
      stagedBeats.length === 3 &&
      stagedBeats.every((b) => b.rowIds.length === 1),
    "staged comparison: three columns become three beats, one number per beat"
  );
  const dFacts = resolution.results.find((r) => r.variantId === "quarter-desktop")?.scaleFacts;
  const mFacts = resolution.results.find((r) => r.variantId === "quarter-mobile-staged")?.scaleFacts;
  report(
    !!dFacts &&
      !!mFacts &&
      dFacts.extentPx === 700 &&
      mFacts.extentPx === 900 &&
      dFacts.normalizedPositions.every((p) => {
        const other = mFacts.normalizedPositions.find((q) => q.rowId === p.rowId);
        return !!other && approx(p.normalized, other.normalized);
      }),
    "staged comparison: scales stay comparable across orientations (42, 67, 85 at 0.42, 0.67, 0.85 of the extent)",
    dFacts
      ? dFacts.normalizedPositions.map((p) => `${p.rowId}=${p.normalized}`).join(" ")
      : ""
  );
  const mobileAudit = auditPlacement(set.content, mobile, tokens);
  report(
    mobileAudit.pass,
    "staged comparison: the staged mobile variant passes the placement audit",
    mobileAudit.typography.findings.map((f) => f.kind).join(",") || "no findings"
  );
}

// ---- 6. Image-led job: focal-solved crops, never a center crop ---
{
  const set = loadFixture("image-desktop-mobile.json");
  const resolution = resolveVariantSet(set.content, set.variants);
  report(
    resolution.pass,
    "image job: desktop and mobile variants resolve clean",
    resolution.findings.map((f) => f.kind).join(",") || "no findings"
  );
  const desktopAudit = auditPlacement(set.content, variant(set, "image-desktop"), tokens);
  const mobileAudit = auditPlacement(set.content, variant(set, "image-mobile"), tokens);
  const dc = desktopAudit.imageFacts?.crop;
  const mc = mobileAudit.imageFacts?.crop;
  const evc = evidence.image_crops;
  report(
    !!dc &&
      dc.x === evc.desktop_crop.x &&
      dc.y === evc.desktop_crop.y &&
      dc.width === evc.desktop_crop.width &&
      dc.height === evc.desktop_crop.height,
    "image job: desktop crop is the full-width 16:9 window (0, 45, 2400, 1350)",
    dc ? JSON.stringify(dc) : "no crop"
  );
  report(
    !!mc &&
      mc.x === evc.mobile_crop.x &&
      mc.y === evc.mobile_crop.y &&
      mc.width === evc.mobile_crop.width &&
      mc.height === evc.mobile_crop.height &&
      mc.x !== evc.mobile_center_crop_x,
    "image job: mobile crop is solved around the focal point (x=270), NOT the center crop (x=750)",
    mc ? JSON.stringify(mc) : "no crop"
  );
  report(
    desktopAudit.pass &&
      mobileAudit.pass &&
      desktopAudit.imageFacts?.focalInsideCrop === true &&
      mobileAudit.imageFacts?.focalInsideCrop === true,
    "image job: both placement audits pass with the protected face region intact and text clear of it",
    [...desktopAudit.findings, ...mobileAudit.findings].map((f) => f.kind).join(",") || "no findings"
  );
}

// ---- 7. Profile discipline and contract edges ---------------------
{
  const set = loadFixture("chart-desktop-mobile.json");
  const mobile = variant(set, "chart-mobile");

  const socialClone = JSON.parse(JSON.stringify(mobile)) as LayoutVariant;
  socialClone.safeAreaProfile = "social-platform-1080x1920";
  const socialResolution = resolveVariantSet(set.content, [socialClone]);
  report(
    socialResolution.findings.some((f) => f.kind === "LAYOUT_PROFILE_NOT_APPLICABLE"),
    "profile discipline: a social-platform profile on a mobile VSL without platform delivery is refused"
  );

  const unknownClone = JSON.parse(JSON.stringify(variant(set, "chart-desktop"))) as LayoutVariant;
  unknownClone.safeAreaProfile = "no-such-profile";
  const unknownResolution = resolveVariantSet(set.content, [unknownClone]);
  report(
    unknownResolution.findings.some((f) => f.kind === "LAYOUT_PROFILE_UNKNOWN"),
    "profile discipline: an unregistered profile name is a finding, not a silent pass"
  );

  const exportClone = JSON.parse(JSON.stringify(variant(set, "chart-desktop"))) as LayoutVariant;
  exportClone.exportAspect = { w: 4, h: 3 };
  const exportResolution = resolveVariantSet(set.content, [exportClone]);
  report(
    exportResolution.findings.some((f) => f.kind === "LAYOUT_EXPORT_ASPECT"),
    "16:9 rule: an export aspect that disagrees with the canvas is refused (placement never rewrites the export aspect)"
  );

  let contractError: LayoutError | null = null;
  try {
    assertSharedContent({ schema_version: "1.0", id: "x", message: "m", headline: "h", bogus: 1 });
  } catch (e) {
    if (e instanceof LayoutError) contractError = e;
  }
  report(
    contractError !== null &&
      contractError.category === "MG_SCHEMA_INVALID" &&
      contractError.exitClass === 2,
    "contract: an unknown key in shared content is MG_SCHEMA_INVALID, exit class 2"
  );
}

console.log(
  `\nLayout: ${passed}/${passed + failed} checks passed, ${failed} failed.`
);
process.exit(failed === 0 ? 0 : 1);
