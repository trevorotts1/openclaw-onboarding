// Measured render resource profiles (Directive MG-028).
//
// Every number in this file comes from measuring the shipped fixture
// scenes rendering on a real provisioned runtime, recorded with its
// method in 72-motion-video-plus/tests/evidence/mg028/measurements.json.
// Estimates are the measured peak of the whole engine process tree
// plus an uncertainty margin (the margin covers sampling granularity
// and scene-to-scene variation; it is stated, not hidden). No number
// here is copied from historical wall-clock promises or from another
// machine's documentation: re-measure on the target machine class
// before trusting these on different hardware (see
// references/resource-budgets.md for the method and how to re-run it).
//
// Profiles are per OPERATION, sized for ONE scene segment at a time:
// both adapters process a job scene by scene (Hyperframes renders and
// probes each scene segment before the next; Remotion composites one
// composition), so the reservation a job holds is the peak of its
// largest single segment, not the sum of the job. That is what keeps
// intermediate storage and memory bounded on large jobs while the
// canonical MG-021 timeline still governs layout: the scheduler never
// touches timing, it only bounds how much of the job is in flight.

import type { ResourceProfile } from "./types";

/** Margin applied to every measured peak: measured x 1.30, rounded up
 * to the nearest 16 MB. Stated here so the doc and the code agree. */
export const MEASUREMENT_MARGIN = 1.3;

function sized(measuredPeakMB: number): number {
  return Math.ceil((measuredPeakMB * MEASUREMENT_MARGIN) / 16) * 16;
}

/**
 * Measured peaks (MB, whole process tree RSS, 50 ms sampling) from
 * the MG-028 measurement runs of 2026-10-14 on the build machine
 * (2 cores, 7935 MB RAM, Linux x64, runtime lock-314fc289b233ca9e;
 * full record in tests/evidence/mg028/measurements.json, regenerated
 * by the measurement case in run-resources.ts, which asserts every
 * estimate derived below covers the peaks it measures).
 *
 * Per-phase peaks across the phase-aligned runs (maxima): Remotion
 * preview render 1283, warm-bundle still 634; Hyperframes render
 * 985 (peaking at 4 Chromium main processes inside the one
 * operation), validate 895, snapshot 812; standalone encode 517.
 */
export const MEASURED_PEAKS_MB = {
  /** Remotion video render. The phase-aligned preview render peaked
   * at 1264 MB; the earlier whole-sequence run peaked at 1469 MB
   * with a cold bundle build inside it. A render call can pay that
   * one-time bundle build (once per source-plus-runtime hash), so
   * the render profile is sized from the larger observation. */
  remotionRender: 1469,
  /** Remotion renderStill of one 1920x1080 frame on a warm bundle:
   * 624-634 MB across the runs. A still as the very first operation
   * against a fresh runtime also pays the bundle build and can
   * transiently approach the render peak; the host reserve absorbs
   * that one-off, and the reference doc says so. */
  remotionStill: 634,
  /** Hyperframes CLI render of the C05 fixture scene (180 frames,
   * 1920x1080, workers 1): CLI + Chromium tree + ffmpeg encode. */
  hyperframesRender: 985,
  /** Hyperframes snapshot of one frame (browser startup + capture). */
  hyperframesStill: 812,
  /** Hyperframes validate (compositions + lint + check) of one scene. */
  hyperframesValidate: 895,
  /** Standalone ffmpeg encode (libx264, crf 16) of a 180-frame
   * 1920x1080 preview: the encode share of a render, isolated. The
   * two engines' re-encodes measured 517 MB and 509 MB. */
  encodeStandalone: 517,
} as const;

/** Nested concurrency the adapters hand to the engines. Remotion
 * renders frames across Chromium tabs; tabs share one browser and are
 * accounted inside the reservation's memory estimate. The
 * Hyperframes CLI is already invoked with one worker by the adapter;
 * anything higher would multiply its browser count inside one
 * reservation and is not used. */
export function remotionNestedTabs(cpuCount: number): number {
  return Math.max(1, Math.min(cpuCount, 4));
}

const REMOTION_TABS_DEFAULT = 2;

const PROFILES: Record<string, ResourceProfile> = {
  "remotion:renderFinal": {
    memoryMB: sized(MEASURED_PEAKS_MB.remotionRender),
    browserUnits: 1,
    encodeUnits: 1,
    diskMB: 512,
    nestedConcurrency: REMOTION_TABS_DEFAULT,
    label: "remotion final render (one composition, tabs nested)",
  },
  "remotion:renderPreview": {
    memoryMB: sized(MEASURED_PEAKS_MB.remotionRender),
    browserUnits: 1,
    encodeUnits: 1,
    diskMB: 512,
    nestedConcurrency: REMOTION_TABS_DEFAULT,
    label: "remotion preview render (one composition, tabs nested)",
  },
  "remotion:renderStill": {
    memoryMB: sized(MEASURED_PEAKS_MB.remotionStill),
    browserUnits: 1,
    encodeUnits: 0,
    diskMB: 64,
    nestedConcurrency: 1,
    label: "remotion still (one frame)",
  },
  "remotion:inspectMotion": {
    memoryMB: sized(MEASURED_PEAKS_MB.remotionStill),
    browserUnits: 1,
    encodeUnits: 0,
    diskMB: 64,
    nestedConcurrency: 1,
    label: "remotion motion inspection (stills)",
  },
  "hyperframes:renderFinal": {
    memoryMB: sized(MEASURED_PEAKS_MB.hyperframesRender),
    browserUnits: 1,
    encodeUnits: 1,
    diskMB: 512,
    nestedConcurrency: 1,
    label: "hyperframes final render (one scene segment at a time, CLI workers 1)",
  },
  "hyperframes:renderPreview": {
    memoryMB: sized(MEASURED_PEAKS_MB.hyperframesRender),
    browserUnits: 1,
    encodeUnits: 1,
    diskMB: 512,
    nestedConcurrency: 1,
    label: "hyperframes preview render (one scene segment at a time, CLI workers 1)",
  },
  "hyperframes:renderStill": {
    memoryMB: sized(MEASURED_PEAKS_MB.hyperframesStill),
    browserUnits: 1,
    encodeUnits: 0,
    diskMB: 64,
    nestedConcurrency: 1,
    label: "hyperframes still (snapshot: browser startup + one frame)",
  },
  "hyperframes:inspectMotion": {
    memoryMB: sized(MEASURED_PEAKS_MB.hyperframesStill),
    browserUnits: 1,
    encodeUnits: 0,
    diskMB: 64,
    nestedConcurrency: 1,
    label: "hyperframes motion inspection (snapshots)",
  },
  "hyperframes:validate": {
    memoryMB: sized(MEASURED_PEAKS_MB.hyperframesValidate),
    browserUnits: 1,
    encodeUnits: 0,
    diskMB: 128,
    nestedConcurrency: 1,
    label: "hyperframes validation (compositions, lint, check)",
  },
  "hyperframes:encode": {
    memoryMB: sized(MEASURED_PEAKS_MB.encodeStandalone),
    browserUnits: 0,
    encodeUnits: 1,
    diskMB: 256,
    nestedConcurrency: 1,
    label: "ffmpeg encode step (segment scale or concat inside a render)",
  },
};

/** The measured profile for one engine operation. Unknown operations
 * fall back to the engine's render profile: over-reserving an
 * unlisted operation is the safe direction. */
export function profileFor(engine: string, operation: string): ResourceProfile {
  const exact = PROFILES[`${engine}:${operation}`];
  if (exact) return exact;
  const render = PROFILES[`${engine}:renderFinal`];
  if (render) return { ...render, label: `${engine} ${operation} (render profile fallback)` };
  return {
    memoryMB: 1024,
    browserUnits: 1,
    encodeUnits: 1,
    diskMB: 256,
    nestedConcurrency: 1,
    label: `${engine} ${operation} (generic fallback profile)`,
  };
}
