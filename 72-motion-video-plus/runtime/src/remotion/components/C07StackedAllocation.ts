// C07 stacked_allocation: the stacked allocation component (Directive
// MG-016, Section 7.1 C07).
//
// Parts accumulate into a truthful whole: segments land one stage at a
// time in declared order, each growing inside its own final band from
// the zero baseline, so the completed stack's total is the arithmetic
// sum of its parts and every segment boundary sits at its truthful
// cumulative level. The color/label mapping is declared data (the
// scene's segment_colors), printed beside each segment with its value
// and the dataset units; the total is printed above the stack once the
// last segment lands. Negative segments are refused by the geometry
// layer (chart-geometry.ts) before anything draws.

import { createElement, type CSSProperties } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { formatDatasetValue } from "../../charts";
import { revealProgressAt } from "../frame-math";
import { ChartScaffold } from "./ChartScaffold";
import {
  estimateLabelLines,
  resolveLabelTops,
  stackedStateAt,
} from "./chart-geometry";
import type { C07Props } from "./chart-props";

export function C07StackedAllocation(props: C07Props): unknown {
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
  const state = stackedStateAt(props.dataset, plot, progress);

  const columnWidth = Math.min(380, plot.width * 0.34);
  const columnX = plot.x + (plot.width - columnWidth) / 2;
  const segmentColor = (index: number): string =>
    props.segmentColors[index] ?? colors.accent;

  const children: unknown[] = [
    createElement("div", {
      key: "baseline",
      style: {
        position: "absolute",
        left: plot.x,
        top: plot.y + plot.height,
        width: plot.width,
        height: 3,
        backgroundColor: colors.ink,
        opacity: 0.35,
      } as CSSProperties,
    }),
  ];

  const labelItems: {
    segment: (typeof state.segments)[number];
    midY: number;
    text: string;
  }[] = [];
  const zeroMarkers: unknown[] = [];

  for (const segment of state.segments) {
    const top = plot.y + plot.height - segment.bottomOffset - segment.currentHeight;
    children.push(
      createElement("div", {
        key: `segment-${segment.rowId}`,
        "data-subject-id": `segment-${segment.rowId}`,
        style: {
          position: "absolute",
          left: columnX,
          top,
          width: columnWidth,
          height: segment.currentHeight,
          backgroundColor: segmentColor(segment.index),
        } as CSSProperties,
      })
    );
    // A zero-value segment occupies no height; a marker line in its
    // declared color keeps the color/label mapping visible at its
    // truthful level once its stage completes. Markers are collected
    // and painted after every segment (below), so the following
    // segment never covers the marker at their shared boundary.
    if (segment.height === 0 && segment.progress >= 1) {
      zeroMarkers.push(
        createElement("div", {
          key: `segment-zero-${segment.rowId}`,
          style: {
            position: "absolute",
            left: columnX,
            top: plot.y + plot.height - segment.bottomOffset - 2,
            width: columnWidth,
            height: 4,
            backgroundColor: segmentColor(segment.index),
          } as CSSProperties,
        })
      );
    }
    // Segment labels are collected here and laid out after the loop:
    // wrapped label blocks are de-collided vertically so adjacent
    // labels never overlap, however long the category names are.
    labelItems.push({
      segment,
      midY: plot.y + plot.height - segment.bottomOffset - segment.height / 2,
      text: `${segment.label}: ${formatDatasetValue(props.dataset, segment.value)} ${props.dataset.units}`,
    });
  }

  children.push(...zeroMarkers);

  // Labels sit in the right rail at their segments' final mid-heights
  // (they never move during the reveal), de-collided as blocks: each
  // block's height is its wrapped line count at the declared rail
  // width, and resolveLabelTops enforces a minimum gap. The leader
  // tick rides at the resolved block center, which stays inside its
  // segment's band for the declared fixtures.
  const labelLeft = columnX + columnWidth + 48;
  // The rail runs from the column to the canvas edge (less a margin):
  // category labels are prose, and a wider rail wraps less.
  const labelWidth = props.canvas.width - labelLeft - 40;
  const topToBottom = [...labelItems].reverse();
  const blockHeights = topToBottom.map(
    (item) => estimateLabelLines(item.text, layout.label_px, labelWidth) * layout.label_px * 1.15
  );
  const blockTops = resolveLabelTops(
    topToBottom.map((item) => item.midY),
    blockHeights,
    10,
    plot.y - 60,
    plot.y + plot.height + 90
  );
  topToBottom.forEach((item, i) => {
    const segment = item.segment;
    const blockCenter = blockTops[i] + blockHeights[i] / 2;
    children.push(
      createElement("div", {
        key: `leader-${segment.rowId}`,
        style: {
          position: "absolute",
          left: columnX + columnWidth + 8,
          top: blockCenter - 1,
          width: 26,
          height: 3,
          backgroundColor: colors.ink,
          opacity: 0.55 * segment.progress,
        } as CSSProperties,
      }),
      createElement(
        "div",
        {
          key: `label-${segment.rowId}`,
          style: {
            position: "absolute",
            left: labelLeft,
            top: blockTops[i],
            width: labelWidth,
            fontSize: layout.label_px,
            lineHeight: 1.15,
            color: colors.ink,
            opacity: segment.progress,
          } as CSSProperties,
        },
        `${segment.label}: `,
        createElement(
          "span",
          { style: { fontWeight: 700 } as CSSProperties },
          `${formatDatasetValue(props.dataset, segment.value)} ${props.dataset.units}`
        )
      )
    );
  });

  const lastProgress =
    state.segments.length > 0 ? state.segments[state.segments.length - 1].progress : 0;
  children.push(
    createElement(
      "div",
      {
        key: "total",
        "data-subject-id": "stack-total",
        style: {
          position: "absolute",
          left: plot.x,
          top: plot.y - layout.value_px - 30,
          width: plot.width,
          textAlign: "center",
          fontSize: layout.value_px,
          fontWeight: 700,
          color: colors.ink,
          opacity: lastProgress,
        } as CSSProperties,
      },
      `Total ${formatDatasetValue(props.dataset, state.total)} ${props.dataset.units}`
    )
  );

  return ChartScaffold({
    font: props.font,
    label: "C07",
    background: colors.background,
    ink: colors.ink,
    layout,
    layoutVariant: props.layoutVariant,
    headline: props.headline,
    disclosure: props.disclosure,
    children,
  });
}
