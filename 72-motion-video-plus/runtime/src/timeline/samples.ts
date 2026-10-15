// Frame, second, and sample conversions for the timeline compiler
// (Directive MG-021, Section 5.4).
//
// THE ONE ROUNDING RULE: every conversion of a sub-frame position uses
// round-half-up applied to the exact value: roundHalfUp(x) =
// floor(x + 0.5) for x >= 0. There is no second rule anywhere in the
// compiler, and no consumer re-rounds a value the compiler produced.
//
// THE RATE: 48000 Hz. It is the delivery sample rate of the pipelines
// this compiler feeds (the webinar/VSL assembly delivers H.264/AAC in
// MP4, and its measured presenter audio is 48000 Hz), and at both
// contract frame rates it yields an integer number of samples per
// frame (48000 / 30 = 1600, 48000 / 60 = 800), so integer frame
// positions convert to samples EXACTLY and the rounding rule binds
// only genuinely sub-frame positions (music-beat grids, measured word
// boundaries). Legacy Skill 72 synth helpers synthesize source audio
// at 44100 Hz; those are source assets that assembly resamples
// (MG-023), not the compiled timeline's rate.

import { TIMELINE_SAMPLE_RATE } from "./types";

/** Round half up: floor(x + 0.5). Defined for x >= 0; every position in
 * a timeline is non-negative. Ties go up, always, so a position exactly
 * halfway between two samples lands on the later sample. */
export function roundHalfUp(x: number): number {
  if (!(x >= 0)) throw new Error(`roundHalfUp expects a non-negative value, got ${x}`);
  return Math.floor(x + 0.5);
}

/** Samples per frame at a contract frame rate. Exact integers at both
 * 30 and 60 fps; any other rate is a programming error, not data. */
export function samplesPerFrame(fps: number): number {
  const spf = TIMELINE_SAMPLE_RATE / fps;
  if (!Number.isInteger(spf)) {
    throw new Error(
      `sample rate ${TIMELINE_SAMPLE_RATE} does not divide evenly at fps ${fps}`
    );
  }
  return spf;
}

/** An integer frame position in samples. Exact: no rounding occurs. */
export function frameToSample(frame: number, fps: number): number {
  if (!Number.isInteger(frame) || frame < 0) {
    throw new Error(`frameToSample expects a non-negative integer frame, got ${frame}`);
  }
  return frame * samplesPerFrame(fps);
}

/** A position in seconds to samples, under the one rounding rule. Used
 * for sub-frame positions (music beats, measured word boundaries),
 * never for integer frame positions, which convert exactly. */
export function secondsToSample(seconds: number): number {
  if (!(seconds >= 0)) throw new Error(`secondsToSample expects >= 0, got ${seconds}`);
  return roundHalfUp(seconds * TIMELINE_SAMPLE_RATE);
}

/** A position in seconds to the nearest frame, under the one rounding
 * rule. */
export function secondsToFrame(seconds: number, fps: number): number {
  if (!(seconds >= 0)) throw new Error(`secondsToFrame expects >= 0, got ${seconds}`);
  return roundHalfUp(seconds * fps);
}

/** The frame whose half-open interval contains a sample position.
 * Spoken-word cues use this: the picture event for a word lands in the
 * frame the word starts in, never in a later frame. */
export function sampleToFrameFloor(sample: number, fps: number): number {
  if (!Number.isInteger(sample) || sample < 0) {
    throw new Error(`sampleToFrameFloor expects a non-negative integer sample, got ${sample}`);
  }
  return Math.floor(sample / samplesPerFrame(fps));
}

/** The sample position of a possibly half-frame midpoint between frame
 * start and frame end (both integers), under the one rounding rule.
 * midpointSampleTimesTwo / 2 would be the frame midpoint; this returns
 * roundHalfUp(((start + end) / 2) * samplesPerFrame) computed without
 * ever materializing a rounded frame first. */
export function rangeMidpointSample(startFrame: number, endFrameExclusive: number, fps: number): number {
  const spf = samplesPerFrame(fps);
  return roundHalfUp(((startFrame + endFrameExclusive) * spf) / 2);
}
