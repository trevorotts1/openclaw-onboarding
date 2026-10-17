// Preview plan computation (Directive MG-024). One documented rule set,
// shared by both adapters and by the legacy render.js compatibility
// path (which duplicates the two tiny formulas with a pointer here,
// because it is a dependency-free CommonJS script):
//
// - Spatial scale preserves aspect ratio exactly; scaled dimensions are
//   rounded to even numbers because the delivery pixel format
//   (yuv420p) requires even dimensions, with a floor of 2.
// - A rough layout render runs at 15 fps when the authored fps is
//   higher than 15, else at half the authored fps (floored, at least
//   1). A rough fps is therefore always strictly below the final fps,
//   which is what lets the motion gate refuse it on fps alone.
// - Duration in frames rescales with fps so the timeline in seconds is
//   identical: a rough preview shows the same events at the same times,
//   sampled less often. It is a layout check, never motion evidence.

import type { PreviewOptions } from "./types";

export interface CanvasSpec {
  width: number;
  height: number;
  fps: number;
}

export interface PreviewPlan {
  scale: number;
  roughLayoutOnly: boolean;
  label: "preview" | "rough_layout_only";
  width: number;
  height: number;
  fps: number;
  /** Frames the preview must hold: the final's frame count when the
   * fps is unchanged, else the same seconds rescaled to the rough fps. */
  durationFrames: number;
}

export class PreviewPlanError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PreviewPlanError";
  }
}

/** Round to the nearest even dimension (yuv420p requirement), min 2. */
export function evenDimension(value: number): number {
  return Math.max(2, Math.round(value / 2) * 2);
}

/** The rough-layout frame rate for an authored fps (see header). */
export function roughFpsFor(canvasFps: number): number {
  if (!(canvasFps > 1)) {
    throw new PreviewPlanError(
      `A rough layout render needs an authored fps above 1 to reduce; got ${canvasFps}.`
    );
  }
  return canvasFps > 15 ? 15 : Math.max(1, Math.floor(canvasFps / 2));
}

/** Duration in frames when the same seconds are sampled at another
 * fps (the frame-math rule of Directive Section 5.4). */
export function rescaleFrames(durationFrames: number, fromFps: number, toFps: number): number {
  return Math.round((durationFrames * toFps) / fromFps);
}

export function planPreview(
  canvas: CanvasSpec,
  durationFrames: number,
  opts?: PreviewOptions
): PreviewPlan {
  const scale = opts?.scale ?? 1;
  if (!Number.isFinite(scale) || scale <= 0 || scale > 1) {
    throw new PreviewPlanError(
      `Preview scale must be a finite number in (0, 1]; got ${String(opts?.scale)}. ` +
        "Previews reduce spatial resolution only; they never upscale."
    );
  }
  const roughLayoutOnly = opts?.roughLayout ?? false;
  const fps = roughLayoutOnly ? roughFpsFor(canvas.fps) : canvas.fps;
  return {
    scale,
    roughLayoutOnly,
    label: roughLayoutOnly ? "rough_layout_only" : "preview",
    width: scale === 1 ? canvas.width : evenDimension(canvas.width * scale),
    height: scale === 1 ? canvas.height : evenDimension(canvas.height * scale),
    fps,
    durationFrames:
      fps === canvas.fps ? durationFrames : rescaleFrames(durationFrames, canvas.fps, fps),
  };
}

/** True when the plan reproduces the adapters' historical preview
 * exactly: canonical dimensions at the full authored fps. */
export function isIdentityPlan(plan: PreviewPlan): boolean {
  return plan.scale === 1 && !plan.roughLayoutOnly;
}

/** Filename suffix distinguishing a variant preview artifact from the
 * canonical preview.mp4: "" for the identity plan, else for example
 * "scale-0p5", "rough", or "scale-0p5-rough". */
export function previewVariantSuffix(plan: PreviewPlan): string {
  const parts: string[] = [];
  if (plan.scale !== 1) parts.push(`scale-${String(plan.scale).replace(".", "p")}`);
  if (plan.roughLayoutOnly) parts.push("rough");
  return parts.join("-");
}
