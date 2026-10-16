// Composition registration for the MG-032 decoy. Metadata is
// calculated from the input props so the registered composition and
// the render inputs cannot disagree (the MG-017 root pattern).

import { createElement } from "react";
import { Composition } from "remotion";
import {
  DecoyComposition,
  type DecoyCompositionProps,
} from "./decoy-composition";
import { DECOY_COMPOSITION_ID } from "./ids";

export { DECOY_COMPOSITION_ID };

const DEFAULT_PROPS: DecoyCompositionProps = {
  width: 1920,
  height: 1080,
  fps: 30,
  durationFrames: 1,
  headline: "Unregistered default",
  headlineBox: { x: 120, y: 90, width: 1680, height: 170 },
  plotX: 420,
  barHeight: 90,
  bars: [],
  colors: { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" },
};

export function DecoyRoot(): unknown {
  return createElement(Composition, {
    id: DECOY_COMPOSITION_ID,
    component: DecoyComposition,
    durationInFrames: DEFAULT_PROPS.durationFrames,
    fps: DEFAULT_PROPS.fps,
    width: DEFAULT_PROPS.width,
    height: DEFAULT_PROPS.height,
    defaultProps: DEFAULT_PROPS,
    calculateMetadata: ({ props }: { props: DecoyCompositionProps }) => ({
      durationInFrames: props.durationFrames,
      fps: props.fps,
      width: props.width,
      height: props.height,
      props,
    }),
  });
}
