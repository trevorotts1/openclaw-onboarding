// Masked reveal geometry (Directive MG-012; Sections 5.4, 17.1 M10).
//
// A reveal is the subject itself changing state through a mask, not a
// background moving behind a static subject (M10: assertions inspect
// the named subject). The geometry here is a pure function of the
// frame: the reveal fraction interpolates linearly between the
// declared from/to fractions over the half-open frame range
// [startFrame, endFrameExclusive). Before the range the fraction is
// the from value; at and after endFrameExclusive it is the to value.
// Linear interpolation of a mask edge is monotonic by construction
// whenever the endpoints are ordered; checkSubjectMotion verifies the
// ordering and samples the curve so a mislabeled or malformed motion
// fails mechanically instead of by inspection.

import {
  Box,
  COMPOSITING_QC_CATEGORY,
  CompositingFinding,
  FrameRange,
} from "./types";

/** The subject edge the visible region stays anchored to while the
 * mask opens: "left" keeps the subject's left edge fixed and the
 * visible width grows rightward; "right", "top", and "bottom" are the
 * mirror images. */
export type RevealDirection = "left" | "right" | "top" | "bottom";

export const REVEAL_DIRECTIONS: readonly RevealDirection[] = [
  "left",
  "right",
  "top",
  "bottom",
];

/** A parametric subject motion over a half-open frame range. */
export interface SubjectMotion {
  kind: "reveal" | "hold" | "exit";
  range: FrameRange;
  /** Anchor edge for reveal and exit motions. */
  direction: RevealDirection;
  /** Visible fraction of the subject at and before the range start. */
  fromFraction: number;
  /** Visible fraction at and after the range end: the declared final
   * state for a reveal, 0 for an exit. */
  toFraction: number;
}

export const SUBJECT_MOTION_KINDS = ["reveal", "hold", "exit"] as const;

/** Reveal progress in [0, 1] for a frame in the half-open convention:
 * 0 before the range, 1 at and after endFrameExclusive, linear in
 * between. The last frame inside the range is endFrameExclusive - 1
 * with progress (duration - 1) / duration: the final state is reached
 * exactly at the exclusive end, never early. */
export function revealProgressAt(frame: number, range: FrameRange): number {
  if (
    !Number.isInteger(frame) ||
    !Number.isInteger(range.startFrame) ||
    !Number.isInteger(range.endFrameExclusive) ||
    range.startFrame < 0 ||
    range.endFrameExclusive <= range.startFrame
  ) {
    throw new Error(
      `invalid reveal frame or range: frame ${frame}, range ` +
        `[${range.startFrame}, ${range.endFrameExclusive})`
    );
  }
  if (frame < range.startFrame) return 0;
  if (frame >= range.endFrameExclusive) return 1;
  return (frame - range.startFrame) / (range.endFrameExclusive - range.startFrame);
}

/** The subject's visible fraction at a frame under a motion: the
 * from fraction before the range, the to fraction at and after the
 * exclusive end, linear interpolation inside. */
export function subjectFractionAt(frame: number, motion: SubjectMotion): number {
  const progress = revealProgressAt(frame, motion.range);
  if (progress === 0) return motion.fromFraction;
  if (progress === 1) return motion.toFraction;
  return motion.fromFraction + (motion.toFraction - motion.fromFraction) * progress;
}

/** The visible region of a subject box at a reveal progress: the
 * sub-box the mask has opened, in continuous canvas coordinates
 * (widths and heights are real numbers here; rasterization is the
 * renderer's). At progress 0 the region is empty (zero extent on the
 * reveal axis); at progress p its extent on that axis is exactly the
 * subject's extent times the motion's visible fraction at p. */
export function visibleRegionAt(
  subject: Box,
  direction: RevealDirection,
  fraction: number
): { box: { x: number; y: number; width: number; height: number }; fraction: number } {
  if (!(fraction >= 0) || !(fraction <= 1)) {
    throw new Error(`visible fraction must lie in [0, 1], got ${fraction}`);
  }
  const width = subject.width * (direction === "left" || direction === "right" ? fraction : 1);
  const height = subject.height * (direction === "top" || direction === "bottom" ? fraction : 1);
  const x =
    direction === "right" ? subject.x + (subject.width - width) : subject.x;
  const y =
    direction === "bottom" ? subject.y + (subject.height - height) : subject.y;
  return { box: { x, y, width, height }, fraction };
}

/**
 * Verify a subject motion's shape: the visible fraction must be
 * monotonic over the motion (non-decreasing for a reveal,
 * non-increasing for an exit, constant for a hold) and must reach
 * exactly the declared final state at the exclusive end. Sampling is
 * exhaustive over the integer frames of the range plus the frames
 * just outside it: frames are cheap integers, and an exhaustive check
 * cannot miss a dip a sparse sample might skip.
 *
 * Returns QC findings (Section 16.9 exit class 6): the motion document
 * is well-formed; it is the claimed movement that fails acceptance.
 */
export function checkSubjectMotion(
  motion: SubjectMotion,
  path: string
): CompositingFinding[] {
  const findings: CompositingFinding[] = [];
  const { startFrame, endFrameExclusive } = motion.range;
  let previous = subjectFractionAt(startFrame - 1, motion);
  let monotonic = true;
  for (let frame = startFrame; frame <= endFrameExclusive; frame += 1) {
    const fraction = subjectFractionAt(frame, motion);
    if (motion.kind === "reveal" && fraction < previous) monotonic = false;
    if (motion.kind === "exit" && fraction > previous) monotonic = false;
    if (motion.kind === "hold" && fraction !== previous) monotonic = false;
    previous = fraction;
  }
  if (!monotonic) {
    findings.push({
      category: COMPOSITING_QC_CATEGORY,
      rule: "subject-motion-monotonic",
      path,
      message:
        `subject motion "${motion.kind}" is not monotonic over ` +
        `[${startFrame}, ${endFrameExclusive}): from ${motion.fromFraction} to ` +
        `${motion.toFraction} moves against the declared kind, so the subject ` +
        "would visibly retreat or jump mid-motion",
    });
  }
  const finalFraction = subjectFractionAt(endFrameExclusive, motion);
  if (finalFraction !== motion.toFraction) {
    findings.push({
      category: COMPOSITING_QC_CATEGORY,
      rule: "subject-motion-final-state",
      path,
      message:
        `subject motion reaches fraction ${finalFraction} at frame ` +
        `${endFrameExclusive}, not its declared final state ${motion.toFraction}`,
    });
  }
  return findings;
}

/**
 * The subject-visibility acceptance rule (MG-012 acceptance: the
 * subject remains visible during motion). Two failures are checked:
 *
 * - The motion's declared final state is fraction 0 without a
 *   declared exit: a reveal or hold whose end state is invisible is
 *   an exit wearing another name.
 * - Sampling every frame of (startFrame, sampleTo): after the start
 *   frame itself (whose fraction is the declared initial state), the
 *   visible fraction must never be zero. Frames before the range are
 *   the pre-motion state and are not sampled.
 *
 * A declared exit (declaredExit, or kind "exit", which is itself the
 * declaration) is exempt: leaving is its declared purpose.
 */
export function checkSubjectVisibility(
  motion: SubjectMotion,
  declaredExit: boolean,
  sampleFrom: number,
  sampleTo: number,
  path: string
): CompositingFinding[] {
  const findings: CompositingFinding[] = [];
  if (declaredExit || motion.kind === "exit") return findings;
  if (motion.toFraction === 0) {
    findings.push({
      category: COMPOSITING_QC_CATEGORY,
      rule: "subject-visibility",
      path,
      message:
        `subject motion "${motion.kind}" declares final fraction 0 without a ` +
        "declared exit: its end state is invisible, so the subject leaves the " +
        "frame under a motion that does not admit it (MG-012 acceptance: the " +
        "subject remains visible during motion)",
    });
    return findings;
  }
  let firstZero = -1;
  let zeroCount = 0;
  const from = Math.max(sampleFrom, motion.range.startFrame + 1);
  for (let frame = from; frame < sampleTo; frame += 1) {
    if (subjectFractionAt(frame, motion) === 0) {
      if (firstZero < 0) firstZero = frame;
      zeroCount += 1;
    }
  }
  if (zeroCount > 0) {
    findings.push({
      category: COMPOSITING_QC_CATEGORY,
      rule: "subject-visibility",
      path,
      message:
        `subject visible fraction drops to 0 at ${zeroCount} frame(s), first at ` +
        `frame ${firstZero}, after its motion began, and the plan declares no ` +
        "exit: the subject vanishes mid-motion (MG-012 acceptance: the subject " +
        "remains visible during motion)",
    });
  }
  return findings;
}
