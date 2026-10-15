// Shared chart scale and geometry utilities (Directive MG-015,
// Sections 16.6 rule 6 and 17.1 M04/M05; foundation for MG-016).
//
// Every chart component computes layout from these functions and from
// nothing else, so instrumented geometry, rendered rasters, and tests
// all read from one calculation. The arithmetic order matches the
// production C05 scale in remotion/frame-math.ts exactly
// (((value - min) * extent) / (max - min)) so integer fixture cases
// stay exact in floating point: 12 * 1200 / 30 = 480.
//
// Truthfulness rules enforced here, not left to callers:
// - Bar lengths are measured from a zero baseline (MG-015). A non-zero
//   baseline is permitted only with a disclosed justification, and the
//   baseline must lie inside the domain; otherwise construction fails
//   with a chart-contract error instead of drawing a misleading bar.
// - A log scale may only be built for a dataset that declares
//   scale_type "log" in its own document. Undeclared log use fails.
// - The data-mark reveal is a plain linear interpolation: monotonic,
//   clamped to [0, 1] progress, and never wider than the final truthful
//   width at any progress. Overshoot exists only in
//   containerOvershoot, an easing for whole-container transforms
//   (scale/translate of the plot container); it is never applied to a
//   data mark's geometry.

import { ChartContractError, type ChartDataset } from "./dataset";

export interface LinearScale {
  readonly kind: "linear";
  readonly domain: readonly [number, number];
  readonly range: readonly [number, number];
  /** Map a data value to range (pixel) coordinates. */
  map(value: number): number;
  /** Inverse of map. */
  invert(position: number): number;
}

export interface LogScale {
  readonly kind: "log";
  readonly domain: readonly [number, number];
  readonly range: readonly [number, number];
  map(value: number): number;
  invert(position: number): number;
}

function assertDomain(domain: readonly [number, number], what: string): void {
  const [min, max] = domain;
  if (!Number.isFinite(min) || !Number.isFinite(max) || !(min < max)) {
    throw new Error(`${what} domain must be finite and strictly increasing, got [${min}, ${max}]`);
  }
}

function assertRange(range: readonly [number, number], what: string): void {
  const [a, b] = range;
  if (!Number.isFinite(a) || !Number.isFinite(b) || a === b) {
    throw new Error(`${what} range must be finite with distinct endpoints, got [${a}, ${b}]`);
  }
}

/** A linear scale with an explicit domain and range. */
export function createLinearScale(
  domain: readonly [number, number],
  range: readonly [number, number]
): LinearScale {
  assertDomain(domain, "linear scale");
  assertRange(range, "linear scale");
  const [d0, d1] = domain;
  const [r0, r1] = range;
  return {
    kind: "linear",
    domain,
    range,
    map: (value: number): number => r0 + ((value - d0) * (r1 - r0)) / (d1 - d0),
    invert: (position: number): number => d0 + ((position - r0) * (d1 - d0)) / (r1 - r0),
  };
}

/**
 * A base-10 log scale. Construction is the enforcement point for the
 * MG-015 explicit-declaration rule only when built through
 * createDatasetScale; this raw constructor enforces the mathematical
 * precondition (a positive domain) and throws a plain Error for an
 * impossible domain, like the other geometry constructors.
 */
export function createLogScale(
  domain: readonly [number, number],
  range: readonly [number, number]
): LogScale {
  assertDomain(domain, "log scale");
  assertRange(range, "log scale");
  const [d0, d1] = domain;
  if (!(d0 > 0)) {
    throw new Error(`log scale domain must be positive, got [${d0}, ${d1}]`);
  }
  const [r0, r1] = range;
  const l0 = Math.log10(d0);
  const l1 = Math.log10(d1);
  return {
    kind: "log",
    domain,
    range,
    map: (value: number): number => {
      if (!(value > 0)) {
        throw new Error(`log scale cannot map a non-positive value, got ${value}`);
      }
      return r0 + ((Math.log10(value) - l0) * (r1 - r0)) / (l1 - l0);
    },
    invert: (position: number): number =>
      Math.pow(10, l0 + ((position - r0) * (l1 - l0)) / (r1 - r0)),
  };
}

/**
 * Build the value scale for a validated dataset over a pixel range.
 * "linear" always works; "log" requires the dataset itself to declare
 * scale_type "log" (MG-015: log axes are declared explicitly). An
 * undeclared log request is a chart-contract violation, category
 * MG_SCHEMA_INVALID, not a silent fallback to linear.
 */
export function createDatasetScale(
  dataset: ChartDataset,
  range: readonly [number, number],
  type: "linear" | "log" = dataset.scale_type
): LinearScale | LogScale {
  if (type === "log") {
    if (dataset.scale_type !== "log") {
      throw new ChartContractError([
        {
          category: "MG_SCHEMA_INVALID",
          path: "scale_type",
          message:
            `Log scale requested for dataset "${dataset.id}" but the dataset does not declare ` +
            'scale_type "log": log axes must be declared explicitly in the dataset (MG-015).',
        },
      ]);
    }
    return createLogScale(dataset.domain, range);
  }
  return createLinearScale(dataset.domain, range);
}

export interface BarGeometryOptions {
  /**
   * The value the bar is measured from. Default 0 (MG-015 zero
   * baseline). A non-zero baseline requires baselineJustification.
   */
  baseline?: number;
  /** Disclosed justification for a non-zero baseline; required then. */
  baselineJustification?: string;
}

export interface BarGeometry {
  /** Left edge of the bar, in plot coordinates starting at 0. */
  x: number;
  /** Bar length in plot units (pixels at render time). */
  width: number;
  /** Plot coordinate of the baseline the bar is measured from. */
  baselinePosition: number;
}

/**
 * Geometry of one bar on a zero-baseline linear scale over a plot of
 * the given width. The baseline edge is anchored: positive bars grow
 * right from the baseline position, negative bars grow left, and a
 * value equal to the baseline has width exactly 0.
 *
 * Arithmetic matches the production C05 scale exactly for the standard
 * case (domain min 0, baseline 0): ((value - 0) * plotWidth) / span.
 * Unlike a bare domain-min scale, length here is always measured from
 * the baseline value, so a domain like [10, 40] cannot silently turn
 * the value 10 into a zero-length bar.
 */
export function barGeometry(
  value: number,
  domain: readonly [number, number],
  plotWidth: number,
  options: BarGeometryOptions = {}
): BarGeometry {
  assertDomain(domain, "bar");
  if (!Number.isFinite(value)) {
    throw new Error(`bar value must be finite, got ${value}`);
  }
  if (!Number.isFinite(plotWidth) || !(plotWidth > 0)) {
    throw new Error(`plot width must be a positive finite number, got ${plotWidth}`);
  }
  const [d0, d1] = domain;
  const baseline = options.baseline ?? 0;
  if (!Number.isFinite(baseline) || baseline < d0 || baseline > d1) {
    throw new ChartContractError([
      {
        category: "MG_SCHEMA_INVALID",
        path: "domain",
        message:
          `Bar baseline ${baseline} lies outside the domain [${d0}, ${d1}]: ` +
          "bar lengths must be measured from a baseline inside the scale's declared extent (MG-015 zero baseline).",
      },
    ]);
  }
  if (baseline !== 0) {
    const justification = options.baselineJustification?.trim() ?? "";
    if (justification.length === 0) {
      throw new ChartContractError([
        {
          category: "MG_SCHEMA_INVALID",
          path: "domain",
          message:
            `Non-zero bar baseline ${baseline} requires a disclosed justification (MG-015: zero baselines ` +
            "unless a clearly disclosed alternative is justified).",
        },
      ]);
    }
  }
  const span = d1 - d0;
  const baselinePosition = ((baseline - d0) * plotWidth) / span;
  const tipPosition = ((value - d0) * plotWidth) / span;
  return {
    x: Math.min(baselinePosition, tipPosition),
    width: Math.abs(tipPosition - baselinePosition),
    baselinePosition,
  };
}

/** Clamp reveal progress to [0, 1]: before the reveal a mark shows
 * nothing (no false data); after it, it holds its final size. */
export function clampProgress(progress: number): number {
  if (!Number.isFinite(progress)) {
    throw new Error(`reveal progress must be finite, got ${progress}`);
  }
  if (progress <= 0) return 0;
  if (progress >= 1) return 1;
  return progress;
}

/**
 * A data mark's width at a reveal progress: linear interpolation from
 * 0 to the final truthful width. Monotonic non-decreasing in progress
 * and never greater than the final width, for any progress, by
 * construction (MG-015: no spring overshoot on data values).
 */
export function revealWidth(finalWidth: number, progress: number): number {
  if (!Number.isFinite(finalWidth) || finalWidth < 0) {
    throw new Error(`final width must be a non-negative finite number, got ${finalWidth}`);
  }
  return clampProgress(progress) * finalWidth;
}

/**
 * Bar geometry at a reveal progress: the width interpolates linearly
 * while the baseline edge stays anchored, so a negative bar grows
 * leftward from the baseline exactly as a positive bar grows right.
 */
export function revealBarGeometry(geometry: BarGeometry, progress: number): BarGeometry {
  const width = revealWidth(geometry.width, progress);
  const growsLeft = geometry.x < geometry.baselinePosition;
  return {
    x: growsLeft ? geometry.baselinePosition - width : geometry.baselinePosition,
    width,
    baselinePosition: geometry.baselinePosition,
  };
}

const EASE_OUT_BACK_C1 = 1.70158;
const EASE_OUT_BACK_C3 = EASE_OUT_BACK_C1 + 1;

/**
 * Ease-out-back for CONTAINER transforms only: the scale/translate of
 * a whole plot container may overshoot its resting value mid-animation
 * (MG-015 permits an outer container to overshoot) because it moves
 * every mark together and changes no mark's relative geometry. Never
 * apply this to a data mark's width, position, or value: that would
 * temporarily misrepresent the metric. Returns values outside [0, 1]
 * only inside the open interval (0, 1); the endpoints are exactly 0
 * and 1.
 */
export function containerOvershoot(progress: number): number {
  const p = clampProgress(progress);
  // Pin the endpoints exactly: the polynomial evaluates to 0 and 1 in
  // real arithmetic, and an animation system must land on the exact
  // resting state rather than a 1e-16 residue of it.
  if (p === 0) return 0;
  if (p === 1) return 1;
  const t = p - 1;
  return 1 + EASE_OUT_BACK_C3 * t * t * t + EASE_OUT_BACK_C1 * t * t;
}
