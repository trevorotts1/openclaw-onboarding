// Chart data contract tests for MG-015 (Directive Sections 6 MG-015,
// 16.6 rule 6, 16.9, 17.1 M04/M05, 17.2).
//
// Pure, deterministic, offline: no renders, no engines. The cases pin
// (1) every fixture dataset under tests/fixtures/datasets to its
// expected contract verdict, (2) the Section 17.2 C05 anchor numbers
// through the shared scale, cross-checked for exact agreement against
// the production scale in remotion/frame-math.ts, (3) formatting under
// the declared rounding rule, and (4) the overshoot guard: the data
// reveal is linear, monotonic, and never exceeds the final truthful
// width at any sampled progress, while the container easing may
// overshoot without touching data geometry.
//
// Exit code 0 when every case passes, 1 otherwise.

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import {
  ChartContractError,
  assertChartDataset,
  barGeometry,
  bandLayout,
  clampProgress,
  containerOvershoot,
  createDatasetScale,
  createLinearScale,
  formatDatasetValue,
  formatValue,
  resolveRowValues,
  revealBarGeometry,
  revealWidth,
  validateCanonicalShape,
  validateDataset,
  type ChartDataset,
  type DatasetFinding,
} from "../src/charts";
import { barWidthAt, revealProgressAt, scaleBarWidth } from "../src/remotion/frame-math";

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

function expectFindings(
  line: string,
  findings: DatasetFinding[],
  want: { count: number; messagePattern?: RegExp }
): void {
  const messages = findings.map((f) => f.message).join(" | ");
  let ok =
    findings.length === want.count &&
    findings.every((f) => f.category === "MG_SCHEMA_INVALID");
  if (ok && want.messagePattern) ok = want.messagePattern.test(messages);
  report(
    ok,
    line,
    `expected ${want.count} MG_SCHEMA_INVALID finding(s)` +
      (want.messagePattern ? ` matching ${want.messagePattern}` : "") +
      `, got ${findings.length}: ${messages || "(none)"}`
  );
}

function main(): number {
  const root = fixturesRoot();
  const datasetsDir = join(root, "datasets");
  if (!existsSync(datasetsDir)) {
    console.error(`FAIL datasets fixture dir not found: ${datasetsDir}`);
    return 1;
  }
  const load = (name: string): unknown => readJson(join(datasetsDir, name));
  const files = new Set(readdirSync(datasetsDir).filter((n) => n.endsWith(".json")));

  // ---- Fixture verdicts -------------------------------------------------
  const validFiles = [
    "valid-observed.json",
    "valid-illustrative.json",
    "valid-missing-with-policy.json",
    "valid-log-declared.json",
    // Valid as a dataset: its failure case is the undeclared log
    // request exercised below, not dataset validation.
    "invalid-undeclared-log.json",
  ];
  for (const name of validFiles) {
    if (!files.has(name)) {
      report(false, `fixture/${name}: file present`, "file missing");
      continue;
    }
    expectFindings(`fixture/${name}: validates clean`, validateDataset(load(name)), { count: 0 });
  }

  const invalidFiles: Array<{ name: string; count: number; messagePattern: RegExp }> = [
    { name: "invalid-unmarked.json", count: 1, messagePattern: /unmarked/ },
    { name: "invalid-observed-contradiction.json", count: 1, messagePattern: /invented evidence/ },
    { name: "invalid-nonfinite.json", count: 1, messagePattern: /non-finite/ },
    { name: "invalid-duplicate-categories.json", count: 1, messagePattern: /Duplicate dataset category id/ },
    { name: "invalid-domain-reversed.json", count: 1, messagePattern: /strictly increasing/ },
    { name: "invalid-totals-mismatch.json", count: 1, messagePattern: /declared_total 100 does not match the row total 60/ },
    {
      name: "invalid-missing-no-policy.json",
      count: 2,
      messagePattern: /requires a declared missing-value policy/,
    },
  ];
  for (const c of invalidFiles) {
    if (!files.has(c.name)) {
      report(false, `fixture/${c.name}: file present`, "file missing");
      continue;
    }
    expectFindings(
      `fixture/${c.name}: rejected as expected`,
      validateDataset(load(c.name)),
      { count: c.count, messagePattern: c.messagePattern }
    );
  }

  // The staged invalid corpus covers exactly the files on disk: a new
  // fixture without a staged expectation fails here so it cannot drift.
  const staged = new Set([...validFiles, ...invalidFiles.map((c) => c.name)]);
  const unstaged = [...files].filter((n) => !staged.has(n));
  report(
    unstaged.length === 0,
    "fixtures: every dataset fixture has a staged expectation",
    `unstaged: ${unstaged.join(", ")}`
  );

  // assertChartDataset throws the structured error for a bad document.
  {
    let caught: unknown = null;
    try {
      assertChartDataset(load("invalid-unmarked.json"));
    } catch (err) {
      caught = err;
    }
    const ok =
      caught instanceof ChartContractError &&
      caught.category === "MG_SCHEMA_INVALID" &&
      caught.exitClass === 2 &&
      caught.findings.length === 1;
    report(ok, "assert: invalid dataset throws ChartContractError (MG_SCHEMA_INVALID, exit class 2)");
  }

  // ---- Canonical parity and the documented schema gap -------------------
  const barsPath = join(root, "shared", "data", "bars.json");
  const bars = readJson(barsPath);
  expectFindings(
    "parity: shipped C05 bars.json passes canonical-shape validation",
    validateCanonicalShape(bars),
    { count: 0 }
  );
  {
    const findings = validateDataset(bars);
    const paths = findings.map((f) => f.path).sort();
    report(
      findings.length === 2 &&
        paths[0] === "display_rounding" &&
        paths[1] === "missing_value_policy" &&
        findings.every((f) => f.category === "MG_SCHEMA_INVALID"),
      "parity: shipped C05 bars.json fails the MG-015 contract on exactly the two undeclared fields",
      `got paths: ${paths.join(", ") || "(none)"}`
    );
  }

  // ---- Section 17.2 anchor through the shared scale ---------------------
  const c05 = assertChartDataset(load("valid-illustrative.json"));
  const domain = c05.domain;
  const widthsAt = (plotWidth: number, progress: number): number[] =>
    c05.rows.map((row) =>
      revealWidth(barGeometry(row.value as number, domain, plotWidth).width, progress)
    );
  const eq = (a: number[], b: number[]): boolean =>
    a.length === b.length && a.every((v, i) => v === b[i]);
  report(eq(widthsAt(1200, 1), [480, 720, 1200]), "anchor: landscape full widths 480/720/1200");
  report(eq(widthsAt(1200, 0.5), [240, 360, 600]), "anchor: landscape half-reveal widths 240/360/600");
  report(eq(widthsAt(1200, 0), [0, 0, 0]), "anchor: landscape zero at reveal start");
  report(eq(widthsAt(740, 1), [296, 444, 740]), "anchor: portrait full widths 296/444/740");
  report(eq(widthsAt(740, 0.5), [148, 222, 370]), "anchor: portrait half-reveal widths 148/222/370");

  // Exact agreement with the production C05 scale (frame-math) for
  // zero-min domains: identical arithmetic in identical order.
  {
    let agree = true;
    const domains: Array<readonly [number, number]> = [
      [0, 30],
      [0, 500],
      [0, 7],
    ];
    const plots = [1200, 740, 333];
    for (const d of domains) {
      for (const w of plots) {
        const scale = createLinearScale(d, [0, w]);
        for (const v of [0, 1, 2.5, 12, 18, 30, d[1]]) {
          if (v > d[1]) continue;
          if (scale.map(v) !== scaleBarWidth(v, d, w)) agree = false;
          if (barGeometry(v, d, w).width !== scaleBarWidth(v, d, w)) agree = false;
        }
      }
    }
    report(agree, "agreement: shared scale equals production scaleBarWidth exactly on zero-min domains");
  }

  // Production frame-clock agreement: the same frames the MG-006
  // render tests measure, through both reveal paths.
  {
    const motion = { startFrame: 15, endFrameExclusive: 75, authoredFps: 30 };
    let agree = true;
    for (const frame of [0, 15, 30, 45, 60, 75, 150, 179]) {
      const progress = revealProgressAt(frame, 30, motion);
      for (const row of c05.rows) {
        const mine = revealBarGeometry(
          barGeometry(row.value as number, domain, 1200),
          progress
        ).width;
        const production = barWidthAt(row.value as number, domain, 1200, frame, 30, motion);
        if (mine !== production) agree = false;
      }
    }
    report(agree, "agreement: reveal widths equal production barWidthAt at every proof frame");
  }

  // ---- Scales -------------------------------------------------------------
  {
    const scale = createLinearScale([0, 30], [0, 1200]);
    const ok =
      scale.map(0) === 0 &&
      scale.map(30) === 1200 &&
      Math.abs(scale.invert(scale.map(17.25)) - 17.25) < 1e-9;
    report(ok, "scale: linear endpoints exact and invert round-trips");
  }
  {
    // Zero-baseline semantics on a domain spanning zero.
    const w = 800;
    const zero = barGeometry(0, [-30, 30], w);
    const neg = barGeometry(-30, [-30, 30], w);
    const pos = barGeometry(30, [-30, 30], w);
    const ok =
      zero.width === 0 &&
      zero.baselinePosition === 400 &&
      neg.x === 0 &&
      neg.width === 400 &&
      pos.x === 400 &&
      pos.width === 400;
    report(ok, "scale: value 0 has zero width on a domain spanning zero; negatives grow left");
  }
  {
    // Non-zero baseline: rejected without a disclosed justification,
    // exact with one.
    let rejected = false;
    try {
      barGeometry(25, [10, 40], 900);
    } catch (err) {
      rejected = err instanceof ChartContractError && /zero baseline|baseline 0/.test(err.message);
    }
    let undisclosed = false;
    try {
      barGeometry(25, [10, 40], 900, { baseline: 10 });
    } catch (err) {
      undisclosed = err instanceof ChartContractError && /disclosed justification/.test(err.message);
    }
    const g = barGeometry(25, [10, 40], 900, {
      baseline: 10,
      baselineJustification: "Indexed to the 2024 opening value of 10; disclosed in the scene copy.",
    });
    const ok = rejected && undisclosed && g.width === 450 && g.x === 0;
    report(ok, "scale: non-zero baseline needs a disclosed justification; baseline outside domain rejected");
  }
  {
    const declared = assertChartDataset(load("valid-log-declared.json"));
    const log = createDatasetScale(declared, [0, 900], "log");
    const near = (a: number, b: number): boolean => Math.abs(a - b) < 1e-9;
    const ok =
      log.kind === "log" &&
      near(log.map(10), 300) &&
      near(log.map(100), 600) &&
      near(log.map(1000), 900) &&
      near(log.invert(600), 100);
    report(ok, "scale: declared log scale maps decades evenly and inverts");
  }
  {
    const undeclared = assertChartDataset(load("invalid-undeclared-log.json"));
    let threw = false;
    try {
      createDatasetScale(undeclared, [0, 900], "log");
    } catch (err) {
      threw =
        err instanceof ChartContractError &&
        err.category === "MG_SCHEMA_INVALID" &&
        /does not declare/.test(err.message);
    }
    const linearOk = createDatasetScale(undeclared, [0, 900]).kind === "linear";
    report(threw && linearOk, "scale: undeclared log request fails MG_SCHEMA_INVALID; linear still builds");
  }

  // ---- Bands ---------------------------------------------------------------
  {
    const bands = bandLayout(3, 440);
    const ok =
      bands.step === 440 / 3 &&
      bands.thickness === (440 / 3) * 0.75 &&
      bands.offset(0) < bands.center(0) &&
      bands.center(0) < bands.offset(1) &&
      bands.offset(2) + bands.thickness <= 440;
    report(ok, "bands: equal steps, centered marks, last band inside the extent");
  }

  // ---- Formatting under the declared rule ----------------------------------
  {
    const cases: Array<[number, number, string]> = [
      [480, 0, "480"],
      [12, 1, "12.0"],
      [12.24, 1, "12.2"],
      [12.25, 1, "12.3"],
      [2.5, 0, "3"],
      [-2.5, 0, "-3"],
      [0.125, 2, "0.13"],
      [1.005, 2, "1.01"],
      [999.95, 1, "1000.0"],
      [0.05, 1, "0.1"],
      [-0.04, 1, "0.0"],
      [0, 2, "0.00"],
    ];
    const bad = cases.filter(([v, d, want]) => formatValue(v, { decimals: d }) !== want);
    report(
      bad.length === 0,
      "format: declared rounding (half away from zero) matches on all edge cases",
      bad.map(([v, d, want]) => `${v}@${d} -> ${formatValue(v, { decimals: d })} (want ${want})`).join("; ")
    );
    const observed = assertChartDataset(load("valid-observed.json"));
    const displayed = observed.rows.map((r) => formatDatasetValue(observed, r.value as number));
    report(
      displayed.join(",") === "240,360,480" &&
        formatDatasetValue(observed, observed.declared_total as number) === "1080",
      "format: observed fixture displays integers under its declared rule"
    );
  }

  // ---- Missing-value resolution ---------------------------------------------
  {
    const skipDs = assertChartDataset(load("valid-missing-with-policy.json"));
    const resolved = resolveRowValues(skipDs);
    const ok =
      resolved[0].value === 40 && resolved[1].value === 90 && resolved[2].value === null;
    report(ok, "missing: skip policy keeps the missing row null and out of the marks");

    const interp: ChartDataset = {
      ...skipDs,
      id: "interp-fixture",
      missing_value_policy: "interpolate",
      declared_total: undefined,
      rows: [
        { id: "a", label: "A", value: 10 },
        { id: "b", label: "B", value: null },
        { id: "c", label: "C", value: 30 },
      ],
    };
    const interpResolved = resolveRowValues(interp);
    report(interpResolved[1].value === 20, "missing: interpolate policy fills the midpoint value 20");

    const zero: ChartDataset = { ...interp, missing_value_policy: "zero" };
    report(resolveRowValues(zero)[1].value === 0, "missing: zero policy counts a missing value as 0");
  }

  // ---- Overshoot guard (deliverable 6) ---------------------------------------
  {
    let monotonic = true;
    let neverExceeds = true;
    let maxExcess = 0;
    for (const plotWidth of [1200, 740]) {
      for (const row of c05.rows) {
        const geometry = barGeometry(row.value as number, domain, plotWidth);
        let previous = 0;
        for (let step = 0; step <= 600; step += 1) {
          const progress = step / 600;
          const w = revealBarGeometry(geometry, progress).width;
          if (w < previous) monotonic = false;
          if (w > geometry.width) {
            neverExceeds = false;
            maxExcess = Math.max(maxExcess, w - geometry.width);
          }
          previous = w;
        }
        if (revealBarGeometry(geometry, 1).width !== geometry.width) neverExceeds = false;
        if (revealBarGeometry(geometry, 0).width !== 0) neverExceeds = false;
      }
    }
    report(
      monotonic && neverExceeds && maxExcess === 0,
      "overshoot guard: data reveal is monotonic and never exceeds the final width at 601 sampled progresses per row",
      `monotonic=${monotonic} neverExceeds=${neverExceeds} maxExcess=${maxExcess}`
    );

    const container = containerOvershoot(0.8);
    const ok =
      container > 1 &&
      containerOvershoot(0) === 0 &&
      containerOvershoot(1) === 1 &&
      Math.abs(revealWidth(1200, 0.8) - 960) < 1e-9 &&
      clampProgress(1.4) === 1 &&
      clampProgress(-0.2) === 0;
    report(
      ok,
      "overshoot guard: container easing overshoots (1.0465 at p=0.8) while the data reveal at the same progress is 960 of 1200 (float tolerance)",
      `container(0.8)=${container}`
    );
  }

  const total = passed + failed;
  console.log(`Charts: ${passed}/${total} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

process.exit(main());
