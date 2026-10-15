// Compositing test runner (Directive MG-012). Runs the plan fixtures
// in tests/fixtures/compositing/ through validation and the QC
// checker, plus direct geometry cases for every primitive: the crop
// solver (including the worked example recorded in
// tests/evidence/mg012/measurements.json), reveal geometry, layer
// parallax, close-up anchoring and upscale honesty, and comparison
// layouts. Pure geometry and contract checks: no engine runtime, no
// rendering. Exit 0 only when every staged expectation holds.

import * as fs from "fs";
import * as path from "path";
import {
  CompositingError,
  UPSCALE_LIMIT,
  annotationAnchorAt,
  assessUpscale,
  assertCompositionPlan,
  buildLayerPlan,
  checkCompositionPlan,
  checkSubjectMotion,
  mapSourceBoxToTarget,
  parseCompositionPlan,
  placementForCrop,
  planComparison,
  requiredSourceSize,
  revealProgressAt,
  solveCrop,
  solveCropFromNormalized,
  sourcePointFromAnchor,
  subjectFractionAt,
  upscaleFinding,
  validateLayers,
  validateCompositionPlan,
  visibleRegionAt,
  zoomWindowAt,
  type Box,
  type SubjectMotion,
} from "../src/compositing";

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override && override.trim().length > 0) return override;
  return path.resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function evidencePath(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  const fixtures = override && override.trim().length > 0
    ? override
    : path.resolve(__dirname, "..", "..", "..", "tests", "fixtures");
  return path.resolve(fixtures, "..", "evidence", "mg012", "measurements.json");
}

function readJson(file: string): unknown {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

let passed = 0;
let failed = 0;
function report(ok: boolean, line: string, detail?: string): void {
  if (ok) {
    passed += 1;
    console.log(`PASS ${line}`);
  } else {
    failed += 1;
    console.log(`FAIL ${line}${detail ? `: ${detail}` : ""}`);
  }
}

function boxEq(a: Box | undefined, b: Box): boolean {
  return (
    a !== undefined &&
    a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height
  );
}

function close(a: number, b: number, eps = 1e-9): boolean {
  return Math.abs(a - b) <= eps;
}

// ---------------------------------------------------------------------
// Fixture expectations. Every fixture file on disk must be staged
// here; the guard at the end fails on drift either way.
// ---------------------------------------------------------------------

interface FixtureExpectation {
  file: string;
  /** "pass": no findings at all. "qc": parses, QC findings match.
   * "contract": parse throws with the staged findings. */
  mode: "pass" | "qc" | "contract";
  /** Expected finding rules, in order, for qc/contract modes. */
  rules?: string[];
  category?: string;
  /** Substring the concatenated messages must contain. */
  messageIncludes?: string;
}

const EXPECTED_FIXTURES: FixtureExpectation[] = [
  { file: "hero-reveal.pass.json", mode: "pass" },
  { file: "closeup.pass.json", mode: "pass" },
  { file: "layered-3d.pass.json", mode: "pass" },
  {
    file: "fail-subject-vanishes.json",
    mode: "qc",
    rules: ["subject-motion-monotonic", "subject-visibility"],
    category: "MG_QC_FAILED",
  },
  {
    file: "fail-crop-impossible.json",
    mode: "qc",
    rules: ["region-exceeds-crop"],
    category: "MG_QC_FAILED",
    messageIncludes: "proof-chart",
  },
  {
    file: "fail-title-covers-proof.json",
    mode: "qc",
    rules: ["protected-text-intersection"],
    category: "MG_QC_FAILED",
    messageIncludes: "face",
  },
  {
    file: "fail-depth-missing-kind.json",
    mode: "contract",
    rules: ["depth-kind-missing"],
    category: "MG_SCHEMA_INVALID",
  },
  {
    file: "fail-depth-3d-no-scene.json",
    mode: "contract",
    rules: ["depth-3d-without-spatial-scene"],
    category: "MG_SCHEMA_INVALID",
  },
  {
    file: "fail-upscale.json",
    mode: "qc",
    rules: ["detail-upscale-exceeded"],
    category: "MG_QC_FAILED",
    messageIncludes: "3840x2160",
  },
];

function runFixtures(): void {
  const dir = path.join(fixturesRoot(), "compositing");
  for (const expectation of EXPECTED_FIXTURES) {
    const file = path.join(dir, expectation.file);
    const doc = readJson(file);
    if (expectation.mode === "pass") {
      try {
        const { measurements } = assertCompositionPlan(doc);
        report(true, `fixture ${expectation.file} passes clean`);
        if (expectation.file === "hero-reveal.pass.json") {
          report(
            boxEq(measurements.crops["desktop"], { x: 0, y: 75, width: 4000, height: 2250 }) &&
              boxEq(measurements.crops["mobile"], { x: 1157, y: 0, width: 1687, height: 3000 }),
            "fixture hero-reveal crops match the worked example in both ratios",
            JSON.stringify(measurements.crops)
          );
          report(
            boxEq(measurements.mappedProtectedRegions["face"], { x: 806, y: 223, width: 308, height: 346 }),
            "fixture hero-reveal maps the protected face onto the canvas",
            JSON.stringify(measurements.mappedProtectedRegions)
          );
          report(
            measurements.subjectFinalFraction === 1,
            "fixture hero-reveal subject ends fully visible",
            String(measurements.subjectFinalFraction)
          );
        }
        if (expectation.file === "closeup.pass.json") {
          const closeUp = measurements.closeUp;
          report(
            closeUp !== undefined &&
              boxEq(closeUp.window, { x: 2720, y: 1134, width: 2000, height: 1333 }) &&
              close(closeUp.assessment.factor, 900 / 1333, 1e-12) &&
              closeUp.assessment.withinLimit &&
              closeUp.assessment.required.width === 1296 &&
              closeUp.assessment.required.height === 1350,
            "fixture closeup window, upscale factor, and required source size are exact",
            JSON.stringify(closeUp)
          );
        }
        if (expectation.file === "layered-3d.pass.json") {
          report(
            measurements.subjectFinalFraction === 1,
            "fixture layered-3d hold keeps the subject fully visible",
            String(measurements.subjectFinalFraction)
          );
        }
      } catch (error) {
        report(false, `fixture ${expectation.file} passes clean`, String(error));
      }
      continue;
    }
    if (expectation.mode === "contract") {
      let caught: unknown = null;
      try {
        parseCompositionPlan(doc);
      } catch (error) {
        caught = error;
      }
      const findings = caught instanceof CompositingError ? caught.findings : [];
      const rules = findings.map((f) => f.rule);
      report(
        caught instanceof CompositingError &&
          caught.exitClass === 2 &&
          JSON.stringify(rules) === JSON.stringify(expectation.rules ?? []) &&
          findings.every((f) => f.category === expectation.category),
        `fixture ${expectation.file} fails as a contract error`,
        caught instanceof CompositingError ? JSON.stringify(rules) : String(caught)
      );
      continue;
    }
    // mode "qc": the document parses; acceptance findings must match.
    try {
      const plan = parseCompositionPlan(doc);
      const { findings } = checkCompositionPlan(plan);
      const rules = findings.map((f) => f.rule);
      const messages = findings.map((f) => f.message).join(" | ");
      report(
        JSON.stringify(rules) === JSON.stringify(expectation.rules ?? []) &&
          findings.every((f) => f.category === expectation.category) &&
          (expectation.messageIncludes === undefined ||
            messages.includes(expectation.messageIncludes)),
        `fixture ${expectation.file} fails QC with exactly the staged rules`,
        JSON.stringify(rules)
      );
      if (expectation.file === "fail-upscale.json") {
        let caught: unknown = null;
        try {
          assertCompositionPlan(doc);
        } catch (error) {
          caught = error;
        }
        report(
          caught instanceof CompositingError && caught.exitClass === 6,
          "fixture fail-upscale assert throws a QC-class error (exit class 6)",
          String(caught)
        );
      }
    } catch (error) {
      report(false, `fixture ${expectation.file} fails QC with exactly the staged rules`, String(error));
    }
  }

  const staged = new Set(EXPECTED_FIXTURES.map((e) => e.file));
  const unstaged = fs
    .readdirSync(dir)
    .filter((name) => name.endsWith(".json") && !staged.has(name));
  report(
    unstaged.length === 0,
    "every compositing fixture on disk is staged in the runner",
    unstaged.join(", ")
  );
}

// ---------------------------------------------------------------------
// Direct geometry cases, one per primitive behavior.
// ---------------------------------------------------------------------

function runDirectCases(): void {
  const source = { width: 4000, height: 3000 };
  const focalNormalized = { x: 0.5, y: 0.4 };
  const regionsNormalized = [
    { id: "face", box: { x: 0.42, y: 0.18, width: 0.16, height: 0.24 } },
  ];

  // The worked example (also the static evidence record).
  const wide = solveCropFromNormalized(
    source, { w: 16, h: 9 }, focalNormalized, regionsNormalized
  );
  report(
    wide.ok && boxEq(wide.crop, { x: 0, y: 75, width: 4000, height: 2250 }),
    "crop solver: worked example 16:9 crop is {0, 75, 4000, 2250}",
    JSON.stringify(wide)
  );
  const tall = solveCropFromNormalized(
    source, { w: 9, h: 16 }, focalNormalized, regionsNormalized
  );
  report(
    tall.ok && boxEq(tall.crop, { x: 1157, y: 0, width: 1687, height: 3000 }),
    "crop solver: worked example 9:16 crop is {1157, 0, 1687, 3000}",
    JSON.stringify(tall)
  );
  if (wide.ok) {
    const placement = placementForCrop(wide.crop, { width: 1920, height: 1080 });
    report(
      placement.scale === 0.48 && boxEq(placement.drawn, { x: 0, y: 0, width: 1920, height: 1080 }),
      "placement: one uniform scale 0.48 fills 1920x1080 with no stretch",
      JSON.stringify(placement)
    );
    const mapped = mapSourceBoxToTarget(
      { x: 1680, y: 540, width: 640, height: 720 },
      wide.crop,
      placement
    );
    report(
      boxEq(mapped, { x: 806, y: 223, width: 308, height: 346 }),
      "mapping: protected face lands at {806, 223, 308, 346} on the canvas",
      JSON.stringify(mapped)
    );
  }

  // No-stretch invariant: the solved crop's aspect error is under one
  // source pixel of the non-floored dimension.
  const stretchCases = [
    { solved: wide, w: 16, h: 9 },
    { solved: tall, w: 9, h: 16 },
  ];
  report(
    stretchCases.every(({ solved, w, h }) =>
      solved.ok &&
      Math.abs(solved.crop.width * h - solved.crop.height * w) <= Math.max(w, h)
    ),
    "crop solver: no-stretch invariant holds within one pixel on both ratios"
  );

  // Impossibility results name the region; they never silently crop.
  const tooWide = solveCrop({
    source: { width: 2000, height: 2000 }, targetAspect: { w: 9, h: 16 },
    protectedRegions: [{ id: "proof-chart", box: { x: 100, y: 800, width: 1800, height: 400 } }],
  });
  report(
    !tooWide.ok && tooWide.reason === "region-exceeds-crop" &&
      JSON.stringify(tooWide.regionIds) === JSON.stringify(["proof-chart"]) &&
      tooWide.message.includes("proof-chart"),
    "crop solver: a region wider than any 9:16 crop is an impossibility naming it",
    JSON.stringify(tooWide)
  );
  const unionTooWide = solveCrop({
    source: { width: 3000, height: 2000 }, targetAspect: { w: 9, h: 16 },
    protectedRegions: [
      { id: "left-proof", box: { x: 0, y: 500, width: 1000, height: 500 } },
      { id: "right-proof", box: { x: 2000, y: 500, width: 1000, height: 500 } },
    ],
  });
  report(
    !unionTooWide.ok && unionTooWide.reason === "regions-union-exceeds-crop" &&
      JSON.stringify(unionTooWide.regionIds) === JSON.stringify(["left-proof", "right-proof"]),
    "crop solver: two regions whose union exceeds the crop are named together",
    JSON.stringify(unionTooWide)
  );
  const focalConflict = solveCrop({
    source, targetAspect: { w: 9, h: 16 },
    focalPoint: { x: 100, y: 2900 },
    protectedRegions: [{ id: "face", box: { x: 1680, y: 540, width: 640, height: 720 } }],
  });
  report(
    !focalConflict.ok && focalConflict.reason === "focal-region-conflict" &&
      focalConflict.regionIds.includes("face") && focalConflict.regionIds.includes("<focal>"),
    "crop solver: a focal point irreconcilable with a protected region is named, not dropped",
    JSON.stringify(focalConflict)
  );
  let threwOnBadFocal = false;
  try {
    solveCrop({ source, targetAspect: { w: 16, h: 9 }, focalPoint: { x: 4500, y: 10 } });
  } catch {
    threwOnBadFocal = true;
  }
  report(threwOnBadFocal, "crop solver: a focal point outside the source is a plain input error");

  // Letterbox placement keeps one uniform scale and centers.
  const letterbox = placementForCrop(
    { x: 0, y: 0, width: 1000, height: 1000 },
    { width: 1920, height: 1080 }
  );
  report(
    letterbox.scale === 1.08 && boxEq(letterbox.drawn, { x: 420, y: 0, width: 1080, height: 1080 }),
    "placement: a square crop letterboxes centered at one uniform scale",
    JSON.stringify(letterbox)
  );

  // Reveal geometry in the half-open convention.
  const range = { startFrame: 10, endFrameExclusive: 40 };
  report(
    revealProgressAt(9, range) === 0 && revealProgressAt(10, range) === 0 &&
      revealProgressAt(25, range) === 0.5 &&
      close(revealProgressAt(39, range), 29 / 30, 1e-12) &&
      revealProgressAt(40, range) === 1 && revealProgressAt(41, range) === 1,
    "reveal: progress is 0 before, linear inside, exactly 1 at the exclusive end"
  );
  const reveal: SubjectMotion = {
    kind: "reveal", range, direction: "left", fromFraction: 0, toFraction: 1,
  };
  report(
    subjectFractionAt(25, reveal) === 0.5 && subjectFractionAt(40, reveal) === 1,
    "reveal: subject fraction interpolates and reaches the declared final state"
  );
  const subjectBox: Box = { x: 100, y: 50, width: 400, height: 200 };
  const visLeft = visibleRegionAt(subjectBox, "left", 0.25);
  const visRight = visibleRegionAt(subjectBox, "right", 0.25);
  const visBottom = visibleRegionAt(subjectBox, "bottom", 0.5);
  report(
    visLeft.box.x === 100 && visLeft.box.width === 100 &&
      visRight.box.x === 400 && visRight.box.width === 100 &&
      visBottom.box.y === 150 && visBottom.box.height === 100,
    "reveal: the visible region stays anchored to the named edge at any fraction",
    JSON.stringify({ visLeft, visRight, visBottom })
  );
  report(
    checkSubjectMotion(reveal, "subject_motion").length === 0 &&
      checkSubjectMotion(
        { kind: "reveal", range, direction: "left", fromFraction: 0.8, toFraction: 0.2 },
        "subject_motion"
      ).some((f) => f.rule === "subject-motion-monotonic"),
    "reveal: a backwards reveal fails the monotonicity check, a true reveal passes"
  );

  // Layers: parallax is derived from order around the subject.
  const stack = [
    { id: "far", role: "background" as const },
    { id: "mid", role: "midground" as const },
    { id: "hero", role: "subject" as const },
    { id: "near", role: "foreground" as const },
  ];
  const plan = buildLayerPlan(stack);
  report(
    JSON.stringify(plan.map((p) => p.factor)) === JSON.stringify([0.5, 0.75, 1, 1.25]),
    "layers: parallax derives from layer order with the subject at exactly 1",
    JSON.stringify(plan.map((p) => p.factor))
  );
  const deepStack = buildLayerPlan([
    { id: "l0", role: "background" as const },
    { id: "l1", role: "background" as const },
    { id: "l2", role: "background" as const },
    { id: "l3", role: "background" as const },
    { id: "l4", role: "background" as const },
    { id: "s", role: "subject" as const },
  ]);
  report(
    deepStack[0].factor === 0.125 && deepStack[1].factor === 0.125 &&
      deepStack[2].factor === 0.25,
    "layers: parallax floors at 0.125 so distant layers never fully freeze",
    JSON.stringify(deepStack.map((p) => p.factor))
  );
  report(
    validateLayers(
      [{ id: "only", role: "subject" }],
      { kind: "2.5d_layered" },
      "layers"
    ).some((f) => f.rule === "depth-layered-needs-layers") &&
      validateLayers(
        [
          { id: "a", role: "background" },
          { id: "a", role: "subject" },
        ],
        { kind: "2.5d_layered" },
        "layers"
      ).some((f) => f.rule === "layers-duplicate-id"),
    "layers: a one-layer 2.5D claim and duplicate layer ids fail validation"
  );

  // Close-up: the anchor tracks the same source detail at every zoom.
  const product = { width: 6000, height: 4000 };
  const detail = { x: 3720, y: 1800 };
  const output: Box = { x: 960, y: 90, width: 864, height: 900 };
  const window3 = zoomWindowAt(product, detail, 3);
  report(
    boxEq(window3, { x: 2720, y: 1134, width: 2000, height: 1333 }) && window3.zoom === 3,
    "close-up: the zoom window at 3x is {2720, 1134, 2000, 1333}",
    JSON.stringify(window3)
  );
  const anchor3 = annotationAnchorAt(detail, window3, output);
  report(
    anchor3.x === 1392 && close(anchor3.y, 90 + 599400 / 1333, 1e-9),
    "close-up: the annotation anchor maps the detail into the output box",
    JSON.stringify(anchor3)
  );
  const attachedAtEveryZoom = [1, 3, 6].every((zoom) => {
    const window = zoomWindowAt(product, detail, zoom);
    const anchor = annotationAnchorAt(detail, window, output);
    const back = sourcePointFromAnchor(anchor, window, output);
    return (
      detail.x >= window.x && detail.x <= window.x + window.width &&
      detail.y >= window.y && detail.y <= window.y + window.height &&
      close(back.x, detail.x, 1e-6) && close(back.y, detail.y, 1e-6)
    );
  });
  report(
    attachedAtEveryZoom,
    "close-up: the anchor names the same source detail at zoom 1, 3, and 6 (round trip)"
  );
  const required = requiredSourceSize({ x: 0, y: 0, width: 1920, height: 1080 }, 4, 2);
  report(
    required.width === 3840 && required.height === 2160 && UPSCALE_LIMIT === 2,
    "close-up: required source at zoom 4 into 1920x1080 within the 2x limit is 3840x2160"
  );
  const overAssessment = assessUpscale({
    source: { width: 1200, height: 900 }, detail: { x: 600, y: 450 },
    maxZoom: 4, output: { x: 0, y: 0, width: 1920, height: 1080 },
  });
  const overFinding = upscaleFinding(overAssessment, "label-closeup", "close_up");
  report(
    close(overAssessment.factor, 6.4, 1e-12) && !overAssessment.withinLimit &&
      overFinding !== null && overFinding.rule === "detail-upscale-exceeded" &&
      overFinding.category === "MG_QC_FAILED",
    "close-up: a 6.4x enlargement is flagged as claiming detail the source lacks",
    JSON.stringify(overAssessment)
  );

  // Comparison: each image is framed against its own focal facts.
  const comparison = planComparison({
    canvas: { width: 1920, height: 1080 },
    mode: "side_by_side",
    images: [
      {
        id: "after",
        source, focalPoint: { x: 2000, y: 1200 },
        protectedRegions: [{ id: "face", box: { x: 1680, y: 540, width: 640, height: 720 } }],
      },
      { id: "before", source: { width: 2000, height: 3000 }, focalPoint: { x: 600, y: 1500 } },
    ],
  });
  const cropAfter = comparison.slots[0].crop;
  const cropBefore = comparison.slots[1].crop;
  report(
    boxEq(comparison.slots[0].box, { x: 0, y: 0, width: 948, height: 1080 }) &&
      boxEq(comparison.slots[1].box, { x: 972, y: 0, width: 948, height: 1080 }) &&
      cropAfter.ok &&
      boxEq(cropAfter.crop, { x: 684, y: 0, width: 2633, height: 3000 }) &&
      cropBefore.ok &&
      boxEq(cropBefore.crop, { x: 0, y: 361, width: 2000, height: 2278 }),
    "comparison: side-by-side solves each image against its own focal constraints",
    JSON.stringify(comparison.slots.map((s) => s.crop))
  );
  const beforeAfter = planComparison({
    canvas: { width: 1920, height: 1080 },
    mode: "before_after",
    images: [
      { id: "a", source, focalPoint: { x: 2000, y: 1200 }, protectedRegions: [{ id: "face", box: { x: 1680, y: 540, width: 640, height: 720 } }] },
      { id: "b", source, focalPoint: { x: 2000, y: 1200 } },
    ],
  });
  const beforeAfterCrop = beforeAfter.slots[0].crop;
  report(
    beforeAfter.slots.every((s) => boxEq(s.box, { x: 0, y: 0, width: 1920, height: 1080 })) &&
      beforeAfterCrop.ok &&
      boxEq(beforeAfterCrop.crop, { x: 0, y: 75, width: 4000, height: 2250 }),
    "comparison: before/after gives both images the full canvas, cropped independently"
  );

  // Plan shape discipline: unknown keys and a non-primary first
  // target are contract findings, never silent acceptance.
  const basePlan = {
    schema_version: "2.0", id: "shape-probe",
    canvas: { width: 1920, height: 1080 }, duration_frames: 30,
  };
  report(
    validateCompositionPlan({ ...basePlan, surprise: true }).some(
      (f) => f.category === "MG_SCHEMA_INVALID" && f.path === "surprise"
    ) &&
      validateCompositionPlan({
        ...basePlan,
        crop_targets: [
          { name: "small", aspect: { w: 16, h: 9 }, box: { width: 1280, height: 720 } },
        ],
      }).some((f) => f.rule === "crop-target-primary"),
    "plan validation: unknown keys and a first target that is not the canvas fail"
  );

  // The static evidence record must agree with the solver, so the
  // numbers in the record are the numbers the code produces.
  const evidence = readJson(evidencePath()) as {
    worked_example: {
      crop_16_9: Box; crop_9_16: Box; face_on_canvas: Box; placement_scale: number;
    };
    upscale_limit: { limit: number };
    failing_upscale_example: { factor: number; required_source: { width: number; height: number } };
  };
  report(
    wide.ok && boxEq(wide.crop, evidence.worked_example.crop_16_9) &&
      tall.ok && boxEq(tall.crop, evidence.worked_example.crop_9_16) &&
      evidence.upscale_limit.limit === UPSCALE_LIMIT &&
      close(evidence.failing_upscale_example.factor, overAssessment.factor, 1e-12) &&
      evidence.failing_upscale_example.required_source.width === overAssessment.required.width &&
      evidence.failing_upscale_example.required_source.height === overAssessment.required.height,
    "evidence: tests/evidence/mg012/measurements.json agrees with the solver and the upscale math"
  );
}

function main(): number {
  runFixtures();
  runDirectCases();
  console.log(`Compositing: ${passed}/${passed + failed} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

process.exit(main());
