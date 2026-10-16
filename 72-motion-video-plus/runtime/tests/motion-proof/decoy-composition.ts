// The MG-032 decoy composition: a plausible-looking data chart whose
// DATA MARKS NEVER MOVE. The bars are drawn at their final widths from
// frame 0 and hold there; all of the frame's motion is decorative: the
// headline slides sideways for the whole duration and an ink band
// sweeps across the bottom of the frame. A pixel-change or whole-frame
// diff check would call this "animated"; the motion proof evaluator
// must fail it, because the named subjects (the bars) perform no
// transformation at all.
//
// The composition is deliberately built from the REAL C05 fixture
// job's layout, dataset values, and final instrumented widths (the
// runner passes them as props), so the only thing wrong with the
// artifact is the motion itself. Plain createElement, no JSX,
// mirroring the codebase's composition style.

import { createElement, type CSSProperties } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

export { DECOY_COMPOSITION_ID } from "./ids";

export interface DecoyBarProp {
  id: string;
  label: string;
  valueLabel: string;
  /** The bar's FINAL width in source px, drawn from frame 0. */
  finalWidth: number;
  y: number;
}

export interface DecoyCompositionProps {
  width: number;
  height: number;
  fps: number;
  durationFrames: number;
  headline: string;
  headlineBox: { x: number; y: number; width: number; height: number };
  plotX: number;
  barHeight: number;
  bars: DecoyBarProp[];
  colors: { background: string; ink: string; accent: string };
}

const FONT = "Liberation Sans, Arial, sans-serif";

export function DecoyComposition(props: DecoyCompositionProps): unknown {
  const frame = useCurrentFrame();
  const last = Math.max(1, props.durationFrames - 1);
  const t = frame / last;
  // Decorative motion 1: the headline slides steadily rightward.
  const headlineX = props.headlineBox.x + t * 300;
  // Decorative motion 2: an ink band sweeps in from off-frame left
  // and parks at the bottom center, so the frame's non-subject pixels
  // change substantially between the first and last states.
  const sweepX = -560 + t * 1260;
  const { colors } = props;

  const children: unknown[] = [
    createElement("div", {
      key: "headline",
      style: {
        position: "absolute",
        left: headlineX,
        top: props.headlineBox.y,
        width: props.headlineBox.width,
        fontFamily: FONT,
        fontSize: 64,
        fontWeight: 700,
        color: colors.ink,
        whiteSpace: "nowrap",
      } as CSSProperties,
    }, props.headline),
    createElement("div", {
      key: "sweep",
      style: {
        position: "absolute",
        left: sweepX,
        top: 960,
        width: 560,
        height: 56,
        backgroundColor: colors.ink,
        opacity: 0.85,
      } as CSSProperties,
    }),
  ];
  for (const bar of props.bars) {
    children.push(
      createElement("div", {
        key: `label-${bar.id}`,
        style: {
          position: "absolute",
          left: 140,
          top: bar.y + 22,
          width: 240,
          fontFamily: FONT,
          fontSize: 40,
          color: colors.ink,
        } as CSSProperties,
      }, bar.label),
      // THE DEFECT, on purpose: the bar is at its final width at every
      // frame. No reveal, no growth, no transformation.
      createElement("div", {
        key: `bar-${bar.id}`,
        style: {
          position: "absolute",
          left: props.plotX,
          top: bar.y,
          width: bar.finalWidth,
          height: props.barHeight,
          backgroundColor: colors.accent,
        } as CSSProperties,
      }),
      createElement("div", {
        key: `value-${bar.id}`,
        style: {
          position: "absolute",
          left: props.plotX + bar.finalWidth + 24,
          top: bar.y + 22,
          fontFamily: FONT,
          fontSize: 40,
          color: colors.ink,
        } as CSSProperties,
      }, bar.valueLabel)
    );
  }
  return createElement(
    AbsoluteFill,
    { style: { backgroundColor: colors.background } as CSSProperties },
    ...children
  );
}
