// C08 waterfall_steps: the waterfall explanation component (Directive
// MG-016, Section 7.1 C08).
//
// A starting value walks to its ending value one signed contribution
// at a time: each column grows from its own base level (the running
// total before the step) to its landing level, a connector at the
// running level joins each completed step to the next, and the final
// column is the computed ending value, equal to the start plus all
// contributions (the arithmetic is enforced in chart-geometry.ts and
// by the dataset's declared total at the MG-015 layer). Gains and
// losses use the scene's declared contribution colors; the start and
// ending columns use the design accent. All steps share one scale and
// one zero baseline, so height differences are truthful.

import { createElement, type CSSProperties } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { bandLayout, formatDatasetValue } from "../../charts";
import { revealProgressAt } from "../frame-math";
import { ChartScaffold } from "./ChartScaffold";
import { waterfallStateAt } from "./chart-geometry";
import type { C08Props } from "./chart-props";

export function C08Waterfall(props: C08Props): unknown {
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
  const state = waterfallStateAt(props.dataset, plot, progress);
  const bands = bandLayout(state.steps.length, plot.width, 0.3);
  const contributionColors = props.contributionColors ?? {
    positive: colors.accent,
    negative: colors.ink,
  };
  const stepColor = (kind: string, delta: number): string => {
    if (kind !== "contribution") return colors.accent;
    return delta >= 0 ? contributionColors.positive : contributionColors.negative;
  };
  const signedLabel = (step: (typeof state.steps)[number]): string => {
    const delta = step.to - step.from;
    if (step.kind === "contribution" && delta > 0) {
      return `+${formatDatasetValue(props.dataset, delta)}`;
    }
    if (step.kind === "contribution") {
      return formatDatasetValue(props.dataset, delta);
    }
    return formatDatasetValue(props.dataset, step.to);
  };

  const children: unknown[] = [];
  if (state.zeroY !== null) {
    children.push(
      createElement("div", {
        key: "zero-line",
        style: {
          position: "absolute",
          left: plot.x,
          top: plot.y + state.zeroY,
          width: plot.width,
          height: 3,
          backgroundColor: colors.ink,
          opacity: 0.45,
        } as CSSProperties,
      })
    );
  }
  children.push(
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
    })
  );

  for (const connector of state.connectors) {
    const fromX = plot.x + bands.offset(connector.afterStepIndex) + bands.thickness;
    const toX = plot.x + bands.offset(connector.afterStepIndex + 1);
    children.push(
      createElement("div", {
        key: `connector-${connector.afterStepIndex}`,
        style: {
          position: "absolute",
          left: fromX,
          top: plot.y + connector.y - 1,
          width: toX - fromX,
          height: 3,
          backgroundColor: colors.ink,
          opacity: connector.visible ? 0.55 : 0,
        } as CSSProperties,
      })
    );
  }

  for (const step of state.steps) {
    const left = plot.x + bands.offset(step.index);
    children.push(
      createElement("div", {
        key: `step-${step.index}`,
        "data-subject-id": `step-${step.rowId ?? "total"}`,
        style: {
          position: "absolute",
          left,
          top: plot.y + step.currentTop,
          width: bands.thickness,
          height: step.currentHeight,
          backgroundColor: stepColor(step.kind, step.to - step.from),
        } as CSSProperties,
      })
    );
    // Value label at the column's FINAL extent (stable while the
    // column grows), above the top edge unless that would leave the
    // plot, in which case below the bottom edge.
    const labelAbove = step.top >= layout.value_px + 22;
    children.push(
      createElement(
        "div",
        {
          key: `value-${step.index}`,
          style: {
            position: "absolute",
            left: left - 20,
            top: labelAbove
              ? plot.y + step.top - layout.value_px - 14
              : plot.y + step.top + step.height + 14,
            width: bands.thickness + 40,
            textAlign: "center",
            fontSize: layout.value_px,
            fontWeight: 700,
            color: colors.ink,
            opacity: step.progress,
          } as CSSProperties,
        },
        signedLabel(step)
      ),
      createElement(
        "div",
        {
          key: `label-${step.index}`,
          style: {
            position: "absolute",
            left: plot.x + step.index * bands.step,
            // Step labels stagger into two bands by index, so a
            // wrapped label never shares a row with its neighbor.
            top:
              plot.y +
              plot.height +
              16 +
              (step.index % 2) * (layout.label_px * 1.15 + 10),
            width: bands.step,
            textAlign: "center",
            fontSize: layout.label_px,
            lineHeight: 1.15,
            color: colors.ink,
          } as CSSProperties,
        },
        step.label
      )
    );
  }

  return ChartScaffold({
    font: props.font,
    label: "C08",
    background: colors.background,
    ink: colors.ink,
    layout,
    layoutVariant: props.layoutVariant,
    headline: props.headline,
    disclosure: props.disclosure,
    children,
  });
}
