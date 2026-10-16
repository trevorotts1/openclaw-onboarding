// Engine-native timing exports from a compiled timeline (Directive
// MG-021, Sections 3.3 and 5.4).
//
// The compiled plan is the only timing authority. These exports adapt
// it at the engine boundary, which is the one place Section 5.4 allows
// representation changes:
//
// - Remotion consumes integer frames. Sequence placement uses
//   (fromFrame, durationInFrames); APIs that take a frame range take
//   the INCLUSIVE range [start, end - 1], produced by the shared
//   toInclusiveRange in remotion/frame-math.ts. The exclusive endpoint
//   is never passed through unchanged.
// - Hyperframes consumes seconds (frames / fps, the identical
//   definition to hyperframes/project.ts seconds()). Values are exact
//   frame-derived decimals; consumers that serialize them into
//   attributes use the project module's secondsAttr formatting.
//
// These are data contracts. The adapters do not consume them yet:
// wiring the compiled plan into the Remotion and Hyperframes adapters
// and into assembly lands with MG-022 and MG-023, which own the
// adapter and assembly files. Nothing here nests one engine inside
// the other (Section 3.3); each export is a flat per-scene record the
// engine's own code reads.

import { toInclusiveRange } from "../remotion/frame-math";
import type { CompiledTimeline } from "./types";

export interface RemotionSceneTiming {
  sceneId: string;
  /** Sequence start frame (inclusive). */
  fromFrame: number;
  durationInFrames: number;
  /** Inclusive [start, end] for Remotion APIs that take a frame range:
   * a scene of N frames renders frames start .. start + N - 1. */
  inclusiveRange: [number, number];
  transitionInFrames: number;
  transitionOutFrames: number;
}

export interface RemotionTiming {
  fps: number;
  totalFrames: number;
  scenes: RemotionSceneTiming[];
}

export function toRemotionTiming(compiled: CompiledTimeline): RemotionTiming {
  const { sidecar } = compiled;
  return {
    fps: sidecar.fps,
    totalFrames: sidecar.total_frames,
    scenes: sidecar.scenes.map((s) => ({
      sceneId: s.id,
      fromFrame: s.placedRange.startFrame,
      durationInFrames: s.durationFrames,
      inclusiveRange: toInclusiveRange({
        startFrame: s.placedRange.startFrame,
        endFrameExclusive: s.placedRange.endFrameExclusive,
      }),
      transitionInFrames: s.transitionInFrames,
      transitionOutFrames: s.transitionOutFrames,
    })),
  };
}

export interface HyperframesSceneTiming {
  sceneId: string;
  startSec: number;
  durationSec: number;
  endSec: number;
  transitionInSec: number;
  transitionOutSec: number;
}

export interface HyperframesTiming {
  fps: number;
  durationSec: number;
  scenes: HyperframesSceneTiming[];
}

export function toHyperframesTiming(compiled: CompiledTimeline): HyperframesTiming {
  const { sidecar } = compiled;
  const fps = sidecar.fps;
  const sec = (frames: number): number => frames / fps;
  return {
    fps,
    durationSec: sec(sidecar.total_frames),
    scenes: sidecar.scenes.map((s) => ({
      sceneId: s.id,
      startSec: sec(s.placedRange.startFrame),
      durationSec: sec(s.durationFrames),
      endSec: sec(s.placedRange.endFrameExclusive),
      transitionInSec: sec(s.transitionInFrames),
      transitionOutSec: sec(s.transitionOutFrames),
    })),
  };
}
