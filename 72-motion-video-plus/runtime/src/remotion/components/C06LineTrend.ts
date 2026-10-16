// C06 line_trend_reveal: the line trend component (Directive MG-016,
// Section 7.1 C06).
//
// Points plot in time order at their true values on the dataset scale
// and establish themselves one stage at a time; the connecting
// polyline draws only between established values, joining true points
// with straight segments (no fabricated smoothing, ever). A focus ring
// tracks the most recent point while the trend develops (the moving
// time/value focus of Section 7.1) and settles on the declared focus
// row for the readable hold; declared annotations appear after the
// reveal with a leader line to their point. All geometry comes from
// chart-geometry.ts, shared with the tests; printed values use the
// dataset's declared display rounding.

import { createElement, type CSSProperties } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { formatDatasetValue } from "../../charts";
import { revealProgressAt } from "../frame-math";
import { ChartScaffold } from "./ChartScaffold";
import { lineGeometry, lineStateAt } from "./chart-geometry";
import type { C06Props } from "./chart-props";

export function C06LineTrend(props: C06Props): unknown {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { colors, layout } = props.design;
  const plot = layout.plot;
  const motion = {
    startFrame: props.motion.startFrame,
    endFrameExclusive: props.motion.endFrameExclusive,
    authoredFps: props.motion.authoredFps,
  };
  const progress = revealProgressAt(frame, fps, motion);
  const geo = lineGeometry(props.dataset, plot);
  const state = lineStateAt(props.dataset, plot, progress);

  // Focus: while the trend develops the ring tracks the most recent
  // point; in the hold it settles on the declared focus row, or on the
  // largest value when no focus row is declared.
  let focusIndex: number | null = state.activeIndex;
  if (progress >= 1) {
    if (props.focusRowId !== null) {
      focusIndex = geo.points.find((p) => p.rowId === props.focusRowId)?.index ?? null;
    } else if (geo.points.length > 0) {
      focusIndex = geo.points.reduce((best, p) => (p.value > best.value ? p : best)).index;
    }
  }
  const focusDot = state.dots.find((d) => d.index === focusIndex) ?? null;

  // Annotations fade in over the fifteen frames after the reveal ends.
  const annotationProgress = revealProgressAt(frame, fps, {
    startFrame: props.motion.endFrameExclusive,
    endFrameExclusive: props.motion.endFrameExclusive + 15,
    authoredFps: props.motion.authoredFps,
  });

  const svgChildren: unknown[] = [];
  if (geo.zeroY !== null) {
    svgChildren.push(
      createElement("line", {
        key: "zero-line",
        x1: 0,
        y1: geo.zeroY,
        x2: plot.width,
        y2: geo.zeroY,
        stroke: colors.ink,
        strokeWidth: 3,
        opacity: 0.4,
      })
    );
  }
  svgChildren.push(
    createElement("line", {
      key: "axis-left",
      x1: 0,
      y1: 0,
      x2: 0,
      y2: plot.height,
      stroke: colors.ink,
      strokeWidth: 3,
      opacity: 0.35,
    }),
    createElement("line", {
      key: "axis-bottom",
      x1: 0,
      y1: plot.height,
      x2: plot.width,
      y2: plot.height,
      stroke: colors.ink,
      strokeWidth: 3,
      opacity: 0.35,
    })
  );
  state.runs.forEach((run, runIndex) => {
    svgChildren.push(
      createElement("polyline", {
        key: `run-${runIndex}`,
        points: run.map((p) => `${p.x},${p.y}`).join(" "),
        fill: "none",
        stroke: colors.accent,
        strokeWidth: 6,
        strokeLinejoin: "round",
        strokeLinecap: "round",
      })
    );
  });
  if (focusDot && focusDot.progress > 0) {
    svgChildren.push(
      createElement("circle", {
        key: "focus-ring",
        cx: focusDot.x,
        cy: focusDot.y,
        r: 21,
        fill: "none",
        stroke: colors.ink,
        strokeWidth: 3,
      })
    );
  }
  state.dots.forEach((dot) => {
    if (dot.radius <= 0) return;
    svgChildren.push(
      createElement("circle", {
        key: `dot-${dot.rowId}`,
        "data-subject-id": `point-${dot.rowId}`,
        cx: dot.x,
        cy: dot.y,
        r: dot.radius,
        fill: colors.accent,
        stroke: colors.background,
        strokeWidth: 3,
      })
    );
  });
  // Annotation leader lines live in the SVG so they track their points.
  for (const annotation of props.annotations) {
    const dot = state.dots.find((d) => d.rowId === annotation.rowId);
    if (!dot || annotationProgress <= 0) continue;
    svgChildren.push(
      createElement("line", {
        key: `leader-${annotation.id}`,
        x1: dot.x,
        y1: dot.y,
        x2: dot.x + (dot.x > plot.width / 2 ? -30 : 30),
        y2: dot.y - 118,
        stroke: colors.ink,
        strokeWidth: 3,
        opacity: annotationProgress * 0.8,
      })
    );
  }

  const plotChildren: unknown[] = [
    createElement(
      "svg",
      {
        key: "plot-svg",
        width: plot.width,
        height: plot.height,
        viewBox: `0 0 ${plot.width} ${plot.height}`,
        style: { position: "absolute", left: 0, top: 0, overflow: "visible" } as CSSProperties,
      },
      svgChildren
    ),
  ];

  // Value labels ride with their points (visible once the dot starts
  // establishing); time labels sit at final positions under the plot
  // from the start, stable to read. When any category label is long
  // (it would wrap past one line at the declared box width), labels
  // stagger into two bands by index so wrapped blocks never share a
  // row with a neighbor: a deterministic layout rule, not a shrink.
  const staggerLabels = state.dots.some((d) => d.label.length > 14);
  for (const dot of state.dots) {
    const aboveTop = dot.y - layout.value_px - 20;
    plotChildren.push(
      createElement(
        "div",
        {
          key: `value-${dot.rowId}`,
          style: {
            position: "absolute",
            left: dot.x - 110,
            top: aboveTop >= -10 ? aboveTop : dot.y + 26,
            width: 220,
            textAlign: "center",
            fontSize: layout.value_px,
            fontWeight: 700,
            color: colors.ink,
            opacity: dot.progress > 0 ? 1 : 0,
          } as CSSProperties,
        },
        formatDatasetValue(props.dataset, dot.value)
      ),
      createElement(
        "div",
        {
          key: `label-${dot.rowId}`,
          style: {
            position: "absolute",
            left: dot.x - 150,
            top:
              plot.height +
              16 +
              (staggerLabels ? (dot.index % 2) * (layout.label_px * 1.15 + 10) : 0),
            width: 300,
            textAlign: "center",
            fontSize: layout.label_px,
            lineHeight: 1.15,
            color: colors.ink,
          } as CSSProperties,
        },
        dot.label
      )
    );
  }

  // Annotation callouts: fixed boxes tied to their points by the leader
  // lines above. Text appears only after the reveal (annotationProgress).
  for (const annotation of props.annotations) {
    const dot = state.dots.find((d) => d.rowId === annotation.rowId);
    if (!dot || annotationProgress <= 0) continue;
    plotChildren.push(
      createElement(
        "div",
        {
          key: `annotation-${annotation.id}`,
          "data-subject-id": `annotation-${annotation.id}`,
          style: {
            position: "absolute",
            // The callout sits on the side of the point with more
            // plot room, so it never covers a neighboring data mark.
            left: dot.x > plot.width / 2 ? dot.x - 38 - 430 : dot.x + 38,
            top: dot.y - 176,
            width: 430,
            padding: "14px 18px",
            border: `3px solid ${colors.ink}`,
            backgroundColor: colors.background,
            fontSize: layout.label_px,
            lineHeight: 1.2,
            color: colors.ink,
            opacity: annotationProgress,
          } as CSSProperties,
        },
        annotation.text
      )
    );
  }

  const children: unknown[] = [
    // The units label sits inside the plot's top-left, behind the
    // marks (it is painted first, and this plot region is where the
    // trend has not yet risen in the declared fixtures). The left
    // rail carries no endpoint labels: at the declared headline
    // sizes a two-line headline occupies that band, and the point
    // value labels plus the zero line already carry the scale.
    createElement(
      "div",
      {
        key: "axis-units",
        style: {
          position: "absolute",
          left: plot.x + 16,
          top: plot.y + 22,
          fontSize: layout.label_px,
          color: colors.ink,
          opacity: 0.55,
        } as CSSProperties,
      },
      props.dataset.units
    ),
    createElement(
      "div",
      {
        key: "plot",
        style: {
          position: "absolute",
          left: plot.x,
          top: plot.y,
          width: plot.width,
          height: plot.height,
        } as CSSProperties,
      },
      plotChildren
    ),
  ];

  return ChartScaffold({
    font: props.font,
    label: "C06",
    background: colors.background,
    ink: colors.ink,
    layout,
    layoutVariant: props.layoutVariant,
    headline: props.headline,
    disclosure: props.disclosure,
    children,
  });
}
