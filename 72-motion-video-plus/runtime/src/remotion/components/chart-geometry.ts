// Shared deterministic geometry for the MG-016 chart component library
// (Directive MG-016, Sections 7.1 and 17.2; foundation MG-015).
//
// Every chart component in this library (C05 bar comparison, C06 line
// trend, C07 stacked allocation, C08 waterfall) computes its marks from
// the functions in this module and from nothing else, so the React
// components, the instrumented test assertions, and the decoded raster
// measurements all read from one calculation. All geometry derives from
// the MG-015 chart utilities (charts/scale.ts, charts/dataset.ts): the
// directive text says "shared D3 geometry", but this build's shared
// geometry layer is the MG-015 utilities and no D3 dependency is pinned,
// so the library builds on those utilities and adds no dependency.
//
// Truthfulness rules enforced here, not left to callers:
// - Bar lengths (C05) are measured from a ZERO baseline through
//   MG-015 barGeometry. barGeometry refuses a baseline outside the
//   scale domain, so the bar scale domain is the dataset domain widened
//   to include zero: on domain [10, 40] the value 10 draws 10/40 of the
//   plot width (a nonzero, truthful length) and 40 draws the full plot
//   width. The previous production scale (frame-math scaleBarWidth,
//   measured from the domain minimum) drew value 10 as a zero-length
//   bar on that domain: that was defect D-CHART-BASELINE. On zero-min
//   domains the widened domain equals the dataset domain, so the
//   Section 17.2 proof states are unchanged.
// - Reveals are staged: the motion interval is divided into one equal
//   slot per mark, and each mark interpolates linearly inside its own
//   slot (slotProgress). No mark ever exceeds its final truthful size
//   (MG-015 reveal rule; container overshoot is never applied to data).
// - A stacked allocation refuses negative segments and a waterfall
//   refuses running levels outside the declared domain: both would
//   draw marks that misrepresent the data, so construction fails with
//   a chart-contract error (MG_SCHEMA_INVALID, exit class 2) instead.

import {
  ChartContractError,
  barGeometry,
  clampProgress,
  createDatasetScale,
  createLinearScale,
  resolveRowValues,
  revealBarGeometry,
  type BarGeometry,
  type ChartDataset,
} from "../../charts";
import { revealProgressAt, type RevealMotionTiming } from "../frame-math";

/** A plot box in canvas coordinates (source pixels). */
export interface PlotBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

// ---------------------------------------------------------------------
// C05 bar comparison (zero-baseline routing; fixes D-CHART-BASELINE)
// ---------------------------------------------------------------------

/**
 * The domain a bar scale measures over: the dataset domain widened to
 * include the zero baseline. Identity for domains that already contain
 * zero (including every zero-min domain), so existing proof states do
 * not move.
 */
export function zeroBaselineDomain(
  domain: readonly [number, number]
): [number, number] {
  return [Math.min(0, domain[0]), Math.max(0, domain[1])];
}

/**
 * Final geometry of one bar through MG-015 barGeometry on the
 * zero-baseline domain. Value 10 on domain [10, 40] over a 1200 px plot
 * yields width 300 (10/40 of the plot), value 40 yields the full 1200;
 * value 12 on domain [0, 30] yields 480, exactly the Section 17.2
 * anchor.
 */
export function barGeometryForValue(
  value: number,
  domain: readonly [number, number],
  plotWidth: number
): BarGeometry {
  return barGeometry(value, zeroBaselineDomain(domain), plotWidth);
}

/** One bar's geometry at a frame: the final truthful geometry revealed
 * linearly by the frame clock's progress (anchored at the baseline). */
export function barStateAt(
  value: number,
  domain: readonly [number, number],
  plotWidth: number,
  frame: number,
  fps: number,
  motion: RevealMotionTiming
): BarGeometry {
  return revealBarGeometry(
    barGeometryForValue(value, domain, plotWidth),
    revealProgressAt(frame, fps, motion)
  );
}

// ---------------------------------------------------------------------
// Label layout
// ---------------------------------------------------------------------

/** Estimate how many lines a label wraps to at a declared box width:
 * a greedy word wrap using the font's average advance (Liberation
 * Sans measures about 0.47 em average for mixed case prose), which
 * models the browser's word-boundary wrapping closely enough to size
 * label blocks before layout. Components use this to size label
 * blocks; under-allocation would let wrapped blocks overlap. */
export function estimateLabelLines(
  text: string,
  fontPx: number,
  widthPx: number
): number {
  const advance = fontPx * 0.47;
  const words = text.split(/\s+/).filter((w) => w.length > 0);
  if (words.length === 0) return 1;
  let lines = 1;
  let lineWidth = 0;
  for (const word of words) {
    const wordWidth = word.length * advance;
    const needed = lineWidth === 0 ? wordWidth : lineWidth + advance + wordWidth;
    if (needed > widthPx && lineWidth > 0) {
      lines += 1;
      lineWidth = wordWidth;
    } else {
      lineWidth = needed;
    }
  }
  return lines;
}

/** Resolve vertical label collisions deterministically. Given label
 * centers and block heights in top-to-bottom order, return block tops
 * that preserve the centers where possible and enforce at least `gap`
 * pixels between consecutive blocks, clamped into [minTop, maxBottom]
 * when the whole stack fits. Data marks never move; only labels do. */
export function resolveLabelTops(
  centers: number[],
  heights: number[],
  gap: number,
  minTop: number,
  maxBottom: number
): number[] {
  const tops = centers.map((c, i) => c - heights[i] / 2);
  if (tops.length === 0) return tops;
  if (tops[0] < minTop) tops[0] = minTop;
  for (let i = 1; i < tops.length; i++) {
    tops[i] = Math.max(tops[i], tops[i - 1] + heights[i - 1] + gap);
  }
  const last = tops.length - 1;
  const overflow = tops[last] + heights[last] - maxBottom;
  if (overflow > 0) {
    for (let i = 0; i < tops.length; i++) tops[i] -= overflow;
    if (tops[0] < minTop) {
      const shift = minTop - tops[0];
      for (let i = 0; i < tops.length; i++) tops[i] += shift;
    }
  }
  return tops;
}

// ---------------------------------------------------------------------
// Staged reveal
// ---------------------------------------------------------------------

/**
 * Progress of one mark inside its own stage of a staged reveal: the
 * overall progress is divided into `count` equal slots in mark order,
 * and mark `index` interpolates linearly across its slot, clamped to
 * [0, 1]. Deterministic in the frame clock; no timers anywhere.
 */
export function slotProgress(
  overallProgress: number,
  index: number,
  count: number
): number {
  if (!Number.isInteger(count) || count < 1) {
    throw new Error(`slot count must be a positive integer, got ${count}`);
  }
  if (!Number.isInteger(index) || index < 0 || index >= count) {
    throw new Error(`slot index ${index} outside [0, ${count})`);
  }
  return clampProgress(overallProgress * count - index);
}

/** Frame-clock progress of one staged mark at a frame. */
export function stagedProgressAt(
  frame: number,
  fps: number,
  motion: RevealMotionTiming,
  index: number,
  count: number
): number {
  return slotProgress(revealProgressAt(frame, fps, motion), index, count);
}

// ---------------------------------------------------------------------
// C06 line trend
// ---------------------------------------------------------------------

export interface LinePoint {
  /** Dataset row index (time order). */
  index: number;
  rowId: string;
  label: string;
  value: number;
  /** Plot-local coordinates (origin at the plot's top-left, y down). */
  x: number;
  y: number;
}

export interface LineGeometry {
  points: LinePoint[];
  /** Adjacent point pairs the polyline may connect: both endpoints
   * present (a skipped missing value breaks the line, per the
   * dataset's declared missing-value policy). */
  segments: { fromIndex: number; toIndex: number }[];
  /** Plot-local y of value zero when zero lies inside the domain. */
  zeroY: number | null;
  yOf: (value: number) => number;
}

/**
 * Final line geometry. Points sit at their true values on the dataset
 * scale; x is the time-order position (equal spacing in row order,
 * endpoints on the plot edges). No smoothing of any kind: the polyline
 * joins true points with straight segments.
 */
export function lineGeometry(dataset: ChartDataset, plot: PlotBox): LineGeometry {
  const resolved = resolveRowValues(dataset);
  const yScale = createDatasetScale(dataset, [plot.height, 0]);
  const count = resolved.length;
  const xAt = (index: number): number =>
    count === 1 ? plot.width / 2 : (index * plot.width) / (count - 1);
  const points: LinePoint[] = [];
  resolved.forEach((entry, index) => {
    if (entry.value === null) return;
    points.push({
      index,
      rowId: entry.row.id,
      label: entry.row.label,
      value: entry.value,
      x: xAt(index),
      y: yScale.map(entry.value),
    });
  });
  const segments: { fromIndex: number; toIndex: number }[] = [];
  for (let i = 1; i < count; i += 1) {
    if (resolved[i - 1].value !== null && resolved[i].value !== null) {
      segments.push({ fromIndex: i - 1, toIndex: i });
    }
  }
  const [d0, d1] = dataset.domain;
  return {
    points,
    segments,
    zeroY: d0 <= 0 && 0 <= d1 ? yScale.map(0) : null,
    yOf: (value: number) => yScale.map(value),
  };
}

export interface LineDotState extends LinePoint {
  /** Reveal progress of this point's own stage, in [0, 1]. */
  progress: number;
  /** Rendered dot radius: the dot grows during the first half of its
   * stage, then holds its full radius. */
  radius: number;
  established: boolean;
}

export interface LineState {
  dots: LineDotState[];
  /** Polyline runs at this progress: each run is a list of plot-local
   * points to join with straight segments. A run ends mid-segment
   * while that segment is still drawing. */
  runs: { x: number; y: number }[][];
  /** Index of the most recently appearing point (the moving focus). */
  activeIndex: number | null;
}

/**
 * Line state at an overall reveal progress. Choreography per stage i:
 * point i's dot grows during the first half of its slot; the segment
 * from point i-1 to point i draws during the second half, so a
 * connection is only ever drawn between established values (Section
 * 7.1: points appear in time order, connected after their values are
 * established). At progress 1 the single run equals the point list
 * exactly (per unbroken stretch of present values).
 */
export function lineStateAt(
  dataset: ChartDataset,
  plot: PlotBox,
  overallProgress: number
): LineState {
  const geo = lineGeometry(dataset, plot);
  const count = dataset.rows.length;
  const byIndex = new Map(geo.points.map((p) => [p.index, p]));
  const dots: LineDotState[] = geo.points.map((point) => {
    const progress = slotProgress(overallProgress, point.index, count);
    return {
      ...point,
      progress,
      radius: 11 * clampProgress(progress * 2),
      established: progress >= 1,
    };
  });
  let activeIndex: number | null = null;
  for (const dot of dots) {
    if (dot.progress > 0) activeIndex = dot.index;
  }
  const runs: { x: number; y: number }[][] = [];
  let current: { x: number; y: number }[] | null = null;
  for (const segment of geo.segments) {
    const from = byIndex.get(segment.fromIndex) as LinePoint;
    const to = byIndex.get(segment.toIndex) as LinePoint;
    const slot = slotProgress(overallProgress, segment.toIndex, count);
    const draw = clampProgress((slot - 0.5) * 2);
    if (draw <= 0) {
      current = null;
      continue;
    }
    if (current === null) {
      current = [{ x: from.x, y: from.y }];
      runs.push(current);
    }
    current.push({
      x: from.x + (to.x - from.x) * draw,
      y: from.y + (to.y - from.y) * draw,
    });
    if (draw < 1) current = null;
  }
  return { dots, runs, activeIndex };
}

// ---------------------------------------------------------------------
// C07 stacked allocation
// ---------------------------------------------------------------------

export interface StackedSegment {
  index: number;
  rowId: string;
  label: string;
  value: number;
  /** Final segment height in plot units. */
  height: number;
  /** Distance from the plot's bottom edge to this segment's bottom. */
  bottomOffset: number;
}

export interface StackedGeometry {
  segments: StackedSegment[];
  /** The arithmetic sum of the segment values: the whole. */
  total: number;
}

/**
 * Final stacked geometry: segments accumulate upward from the zero
 * baseline in declared row order, each height linear in its value on
 * the scale of the whole (the sum of the parts). A negative segment is
 * refused: an allocation part cannot be negative without lying about
 * the whole. A zero segment is legal and occupies zero height at its
 * declared position in the stack.
 */
export function stackedGeometry(
  dataset: ChartDataset,
  plot: PlotBox
): StackedGeometry {
  const resolved = resolveRowValues(dataset);
  resolved.forEach((entry, index) => {
    if (entry.value === null) {
      throw new ChartContractError([
        {
          category: "MG_SCHEMA_INVALID",
          path: `rows[${index}]/value`,
          message:
            `Stacked allocation segment "${entry.row.id}" has no resolved value under the ` +
            `dataset's missing-value policy (${dataset.missing_value_policy}); a segment of ` +
            "the whole cannot be skipped silently.",
        },
      ]);
    }
    if ((entry.value as number) < 0) {
      throw new ChartContractError([
        {
          category: "MG_SCHEMA_INVALID",
          path: `rows[${index}]/value`,
          message:
            `Stacked allocation segment "${entry.row.id}" is negative (${entry.value}); ` +
            "allocation parts are non-negative by definition, so the stack cannot be drawn truthfully.",
        },
      ]);
    }
  });
  const total = resolved.reduce((acc, entry) => acc + (entry.value as number), 0);
  if (!(total > 0)) {
    throw new ChartContractError([
      {
        category: "MG_SCHEMA_INVALID",
        path: "rows",
        message: `Stacked allocation total is ${total}; a stack of zero or less has no whole to show.`,
      },
    ]);
  }
  const scale = createLinearScale([0, total], [0, plot.height]);
  let cumulative = 0;
  const segments = resolved.map((entry, index) => {
    const value = entry.value as number;
    const height = scale.map(value);
    const segment: StackedSegment = {
      index,
      rowId: entry.row.id,
      label: entry.row.label,
      value,
      height,
      bottomOffset: cumulative,
    };
    cumulative += height;
    return segment;
  });
  return { segments, total };
}

/** Stacked state at a progress: each segment grows inside its own
 * final band (bottom edge anchored at its final offset), so segment
 * boundaries and their labels never move during the reveal. */
export function stackedStateAt(
  dataset: ChartDataset,
  plot: PlotBox,
  overallProgress: number
): { segments: (StackedSegment & { progress: number; currentHeight: number })[]; total: number } {
  const geo = stackedGeometry(dataset, plot);
  const count = geo.segments.length;
  return {
    total: geo.total,
    segments: geo.segments.map((segment) => {
      const progress = slotProgress(overallProgress, segment.index, count);
      return { ...segment, progress, currentHeight: segment.height * progress };
    }),
  };
}

// ---------------------------------------------------------------------
// C08 waterfall explanation
// ---------------------------------------------------------------------

export type WaterfallStepKind = "start" | "contribution" | "total";

export interface WaterfallStep {
  index: number;
  kind: WaterfallStepKind;
  /** Dataset row id for start and contribution steps; null for the
   * computed total column. */
  rowId: string | null;
  label: string;
  /** Running level before this step (plot value space). */
  from: number;
  /** Running level after this step. */
  to: number;
  /** Plot-local y of the column's top edge (y down). */
  top: number;
  /** Column height in plot units. */
  height: number;
  /** Plot-local y of the from level (where the column starts). */
  baseY: number;
  /** Plot-local y of the to level (where the column lands). */
  tipY: number;
}

export interface WaterfallGeometry {
  steps: WaterfallStep[];
  /** Connector levels: after step i completes, a connector runs at
   * step i's landing level into step i+1. */
  connectors: { afterStepIndex: number; y: number }[];
  /** start + sum(contributions): identically the sum of all row
   * values under the row convention below. */
  endValue: number;
  zeroY: number | null;
}

/**
 * Final waterfall geometry. Row convention (declared in the C08
 * catalog entry): row 0 is the starting value, every later row is a
 * signed contribution, and the ending column is computed, never a row.
 * Under that convention the ending value equals the sum of all row
 * values, so a dataset declared_total pins the ending value through
 * the MG-015 totals check. Every running level must lie inside the
 * declared domain: a level outside it would be drawn clipped, so
 * construction refuses instead.
 */
export function waterfallGeometry(
  dataset: ChartDataset,
  plot: PlotBox
): WaterfallGeometry {
  const resolved = resolveRowValues(dataset);
  if (resolved.length < 2) {
    throw new ChartContractError([
      {
        category: "MG_SCHEMA_INVALID",
        path: "rows",
        message:
          "A waterfall needs a starting value row and at least one contribution row.",
      },
    ]);
  }
  resolved.forEach((entry, index) => {
    if (entry.value === null) {
      throw new ChartContractError([
        {
          category: "MG_SCHEMA_INVALID",
          path: `rows[${index}]/value`,
          message:
            `Waterfall step "${entry.row.id}" has no resolved value under the dataset's ` +
            `missing-value policy (${dataset.missing_value_policy}); a running total cannot skip a step.`,
        },
      ]);
    }
  });
  const values = resolved.map((entry) => entry.value as number);
  const levels: number[] = [values[0]];
  for (let i = 1; i < values.length; i += 1) {
    levels.push(levels[i - 1] + values[i]);
  }
  const endValue = levels[levels.length - 1];
  const [d0, d1] = dataset.domain;
  const yScale = createDatasetScale(dataset, [plot.height, 0]);
  const checkLevel = (level: number, what: string): void => {
    if (level < d0 || level > d1) {
      throw new ChartContractError([
        {
          category: "MG_SCHEMA_INVALID",
          path: "domain",
          message:
            `Waterfall ${what} level ${level} lies outside the declared domain ` +
            `[${d0}, ${d1}]; it would be drawn clipped. Widen the dataset domain to ` +
            "cover every running level.",
        },
      ]);
    }
  };
  checkLevel(0, "baseline");
  levels.forEach((level, i) => checkLevel(level, `step ${i}`));
  const makeStep = (
    index: number,
    kind: WaterfallStepKind,
    rowId: string | null,
    label: string,
    from: number,
    to: number
  ): WaterfallStep => {
    const fromY = yScale.map(from);
    const toY = yScale.map(to);
    return {
      index,
      kind,
      rowId,
      label,
      from,
      to,
      top: Math.min(fromY, toY),
      height: Math.abs(toY - fromY),
      baseY: fromY,
      tipY: toY,
    };
  };
  const steps: WaterfallStep[] = [
    makeStep(0, "start", resolved[0].row.id, resolved[0].row.label, 0, values[0]),
  ];
  for (let i = 1; i < values.length; i += 1) {
    steps.push(
      makeStep(i, "contribution", resolved[i].row.id, resolved[i].row.label, levels[i - 1], levels[i])
    );
  }
  steps.push(
    makeStep(steps.length, "total", null, "End", 0, endValue)
  );
  const connectors = steps
    .slice(0, steps.length - 1)
    .map((step) => ({ afterStepIndex: step.index, y: step.tipY }));
  return {
    steps,
    connectors,
    endValue,
    zeroY: d0 <= 0 && 0 <= d1 ? yScale.map(0) : null,
  };
}

/** Waterfall state at a progress: one step lands at a time in declared
 * order; each column grows from its own base level toward its landing
 * level, and a connector appears once the step it follows completes. */
export function waterfallStateAt(
  dataset: ChartDataset,
  plot: PlotBox,
  overallProgress: number
): {
  steps: (WaterfallStep & { progress: number; currentTop: number; currentHeight: number })[];
  connectors: { afterStepIndex: number; y: number; visible: boolean }[];
  endValue: number;
  zeroY: number | null;
} {
  const geo = waterfallGeometry(dataset, plot);
  const yScale = createDatasetScale(dataset, [plot.height, 0]);
  const count = geo.steps.length;
  const steps = geo.steps.map((step) => {
    const progress = slotProgress(overallProgress, step.index, count);
    const currentTo = step.from + (step.to - step.from) * progress;
    const fromY = yScale.map(step.from);
    const toY = yScale.map(currentTo);
    return {
      ...step,
      progress,
      currentTop: Math.min(fromY, toY),
      currentHeight: Math.abs(toY - fromY),
    };
  });
  const connectors = geo.connectors.map((connector) => ({
    ...connector,
    visible: slotProgress(overallProgress, connector.afterStepIndex, count) >= 1,
  }));
  return { steps, connectors, endValue: geo.endValue, zeroY: geo.zeroY };
}
