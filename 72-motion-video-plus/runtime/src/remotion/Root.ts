// Composition registrations for the Remotion adapter (Directive MG-006).
//
// One registered composition per catalog component. C05's metadata
// (canvas, fps, duration) is CALCULATED from the input props, and the
// adapter selects the composition with the same validated input props
// it passes to rendering, so registered metadata and render inputs
// cannot disagree. The default props below exist only so registration
// is well-formed without I/O; they deliberately carry no font files, so
// a render attempted without real input props fails at the font gate
// instead of silently substituting a font.

import { createElement } from "react";
import { Composition } from "remotion";
import { C05BarChart } from "./components/C05BarChart";
import { C05_COMPOSITION_ID } from "./frame-math";
import type { C05Props } from "./job-props";

export { C05_COMPOSITION_ID };

const DEFAULT_PROPS: C05Props = {
  jobId: "unregistered-default",
  sceneId: "bar-01",
  componentId: "C05",
  componentVersion: "1.0.0",
  canvas: { width: 1920, height: 1080, fps: 30 },
  durationFrames: 180,
  layoutVariant: "landscape",
  headline: "Compare the three groups",
  disclosure: "Illustrative example",
  dataset: {
    domain: [0, 30],
    units: "items",
    rows: [
      { id: "a", label: "Group A", value: 12 },
      { id: "b", label: "Group B", value: 18 },
      { id: "c", label: "Group C", value: 30 },
    ],
  },
  design: {
    colors: { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" },
    layout: {
      headline_px: 112,
      label_px: 64,
      value_px: 72,
      disclosure_px: 48,
      plot: { x: 420, y: 360, width: 1200, height: 440 },
      bar_height: 90,
      row_y: [360, 520, 680],
      headline_box: { x: 120, y: 90, width: 1680, height: 170 },
    },
  },
  motion: {
    kind: "linear_bar_reveal",
    startFrame: 15,
    endFrameExclusive: 75,
    holdToFrameExclusive: 180,
    authoredFps: 30,
  },
  font: { family: "Liberation Sans", files: [] },
};

export function RemotionRoot(): unknown {
  return createElement(Composition, {
    id: C05_COMPOSITION_ID,
    component: C05BarChart,
    durationInFrames: DEFAULT_PROPS.durationFrames,
    fps: DEFAULT_PROPS.canvas.fps,
    width: DEFAULT_PROPS.canvas.width,
    height: DEFAULT_PROPS.canvas.height,
    defaultProps: DEFAULT_PROPS,
    calculateMetadata: ({ props }: { props: C05Props }) => ({
      durationInFrames: props.durationFrames,
      fps: props.canvas.fps,
      width: props.canvas.width,
      height: props.canvas.height,
      props,
    }),
  });
}
