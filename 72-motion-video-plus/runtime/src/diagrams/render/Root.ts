// Composition registration for the diagrams render harness
// (Directive MG-017).
//
// Metadata (canvas, fps, duration) is CALCULATED from the input props,
// mirroring the MG-006 C05 root, so the registered composition and the
// render inputs cannot disagree. The default props carry an empty
// resolved diagram and no font files: a render attempted without real
// input props fails at the font gate instead of substituting a font.

import { createElement } from "react";
import { Composition } from "remotion";
import {
  DIAGRAM_COMPOSITION_ID,
  DiagramComposition,
  type DiagramCompositionProps,
} from "./DiagramComposition";

export { DIAGRAM_COMPOSITION_ID };

const DEFAULT_PROPS: DiagramCompositionProps = {
  resolved: {
    pattern: "flow_through",
    orientation: "landscape",
    canvas: { width: 1920, height: 1080, fps: 30 },
    timing: { start_frame: 0, end_frame_exclusive: 1, hold_to_frame_exclusive: 1 },
    nodes: [],
    edges: [],
    subject: null,
    relief: null,
  },
  headline: "Unregistered default",
  disclosure: "Unregistered default",
  durationFrames: 1,
  font: { family: "Liberation Sans", files: [] },
};

export function DiagramRoot(): unknown {
  return createElement(Composition, {
    id: DIAGRAM_COMPOSITION_ID,
    component: DiagramComposition,
    durationInFrames: DEFAULT_PROPS.durationFrames,
    fps: DEFAULT_PROPS.resolved.canvas.fps,
    width: DEFAULT_PROPS.resolved.canvas.width,
    height: DEFAULT_PROPS.resolved.canvas.height,
    defaultProps: DEFAULT_PROPS,
    calculateMetadata: ({ props }: { props: DiagramCompositionProps }) => ({
      durationInFrames: props.durationFrames,
      fps: props.resolved.canvas.fps,
      width: props.resolved.canvas.width,
      height: props.resolved.canvas.height,
      props,
    }),
  });
}
