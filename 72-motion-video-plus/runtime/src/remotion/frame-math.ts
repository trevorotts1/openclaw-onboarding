// Frame math for the Remotion production adapter (Directive MG-006,
// Sections 5.4 and 17.2).
//
// Internal time is integer frames in half-open intervals
// [startFrame, endFrameExclusive). Scene state is a pure function of the
// current frame and the composition fps: the C05 reveal is authored in
// frames at the job's authored fps, and progress is computed through
// seconds, so the same scene at a different fps occupies the same seconds
// (start 0.5 s, end 2.5 s for the fixture at both 30 and 60 fps).
//
// The scale calculation here is the single shared implementation: the
// React component renders from it, the adapter's instrumented geometry
// check reads from it, and the tests compare decoded raster measurements
// against it. One implementation, three consumers, no divergent copies.

import type { FrameRange } from "../adapters/types";

/** The registered composition id for catalog component C05. Defined in
 * this dependency-free module so browser-side composition code and the
 * Node-side adapter import the same constant without dragging Node
 * builtins into the browser bundle graph. */
export const C05_COMPOSITION_ID = "C05";

/** Motion timing as authored in a scene file (frames at authoredFps). */
export interface RevealMotionTiming {
  startFrame: number;
  endFrameExclusive: number;
  /** The fps the authored frame numbers are expressed at. */
  authoredFps: number;
}

/**
 * Linear reveal progress in [0, 1] for a frame, computed through seconds:
 * progress = clamp((frame / fps - start) / (end - start)) with start and
 * end converted from authored frames to seconds. Before the start the
 * progress is exactly 0; at and after the end it is exactly 1 (the mark
 * holds its final, truthful size; overshoot is not part of C05).
 */
export function revealProgressAt(frame: number, fps: number, motion: RevealMotionTiming): number {
  if (!(fps > 0)) throw new Error(`fps must be positive, got ${fps}`);
  if (!(motion.authoredFps > 0)) {
    throw new Error(`authoredFps must be positive, got ${motion.authoredFps}`);
  }
  const startSeconds = motion.startFrame / motion.authoredFps;
  const endSeconds = motion.endFrameExclusive / motion.authoredFps;
  if (!(endSeconds > startSeconds)) {
    throw new Error(
      `motion end (${motion.endFrameExclusive}) must be after start (${motion.startFrame})`
    );
  }
  const t = frame / fps;
  if (t <= startSeconds) return 0;
  if (t >= endSeconds) return 1;
  return (t - startSeconds) / (endSeconds - startSeconds);
}

/**
 * The shared linear scale: a value's full width on a zero-based domain.
 * Computed as ((value - min) * plotWidth) / (max - min) so the fixture's
 * integer cases stay exact in floating point (12 * 1200 / 30 = 480).
 */
export function scaleBarWidth(
  value: number,
  domain: readonly [number, number],
  plotWidth: number
): number {
  const [min, max] = domain;
  if (!(max > min)) throw new Error(`dataset domain must be increasing, got [${min}, ${max}]`);
  return ((value - min) * plotWidth) / (max - min);
}

/** A bar's rendered width at a frame: reveal progress times its full
 * scaled width. At progress 0 the width is exactly 0 (no false data). */
export function barWidthAt(
  value: number,
  domain: readonly [number, number],
  plotWidth: number,
  frame: number,
  fps: number,
  motion: RevealMotionTiming
): number {
  return revealProgressAt(frame, fps, motion) * scaleBarWidth(value, domain, plotWidth);
}

/**
 * Adapt the internal half-open range to the inclusive [start, end] tuple
 * Remotion's render APIs expect (Section 5.4: the exclusive endpoint is
 * never passed through unchanged). A range of N frames renders frames
 * start .. start + N - 1.
 */
export function toInclusiveRange(range: FrameRange): [number, number] {
  if (
    !Number.isInteger(range.startFrame) ||
    !Number.isInteger(range.endFrameExclusive) ||
    range.startFrame < 0 ||
    range.endFrameExclusive <= range.startFrame
  ) {
    throw new Error(
      `invalid half-open frame range [${range.startFrame}, ${range.endFrameExclusive})`
    );
  }
  return [range.startFrame, range.endFrameExclusive - 1];
}

/** Duration in frames when a job authored at authoredFps is rendered at
 * another fps: the same seconds, rescaled and rounded to whole frames. */
export function rescaleDurationFrames(
  durationFrames: number,
  authoredFps: number,
  fps: number
): number {
  if (!(authoredFps > 0) || !(fps > 0)) {
    throw new Error(`fps values must be positive, got authored ${authoredFps}, target ${fps}`);
  }
  return Math.round((durationFrames * fps) / authoredFps);
}
