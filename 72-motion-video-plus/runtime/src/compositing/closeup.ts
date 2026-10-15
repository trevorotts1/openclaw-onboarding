// Annotated product close-up and source-resolution honesty
// (Directive MG-012; Section 17.3 VREF-04 discipline).
//
// A close-up zooms a window of the source around a named detail. Two
// promises are kept mechanically:
// - The annotation stays attached to the detail. The anchor is a pure
//   function of the detail point, the current zoom window, and the
//   output box, so at every zoom step the anchor names the same
//   source point; there is no per-step state to drift.
// - Nobody claims detail the source does not contain. Showing a
//   source window of W pixels across an output of O pixels enlarges
//   source pixels by the factor O / W. At a factor of 2, three of
//   every four displayed pixels are interpolated; beyond it, calling
//   the result "detail" is fiction. UPSCALE_LIMIT is therefore 2: the
//   QC checker flags any close-up whose maximum-zoom factor exceeds
//   the plan's declared limit, which defaults to (and for a readable
//   detail claim is capped by) this constant. The computed factor and
//   the required source size are always reported in the QC
//   measurements, passing or failing, so the number is on the record
//   either way.

import {
  Box,
  COMPOSITING_QC_CATEGORY,
  CompositingFinding,
  Point,
  Size,
} from "./types";

/** The default maximum enlargement of source pixels in a close-up
 * that claims readable detail: at 2x, 75% of displayed pixels are
 * interpolated; beyond 2x a detail claim is not supported. */
export const UPSCALE_LIMIT = 2;

/** A zoom window into the source: an integer sub-box of the source. */
export interface ZoomWindow extends Box {
  /** The zoom this window represents (source extent / window extent
   * on the x axis; the y factor differs by under one pixel of
   * rounding and is not separately recorded). */
  zoom: number;
}

/**
 * The source window shown at a zoom factor, centered on the detail
 * point and clamped inside the source. Window dimensions are the
 * source dimensions divided by the zoom, floored to whole pixels
 * (minimum 1); the origin is the detail-centered origin rounded to
 * the nearest pixel and clamped, following the module rounding rules.
 */
export function zoomWindowAt(source: Size, detail: Point, zoom: number): ZoomWindow {
  if (!(zoom >= 1) || !Number.isFinite(zoom)) {
    throw new Error(`zoom must be a finite number >= 1, got ${zoom}`);
  }
  if (
    detail.x < 0 || detail.y < 0 || detail.x > source.width || detail.y > source.height
  ) {
    throw new Error(
      `detail point ${JSON.stringify(detail)} lies outside the ${source.width}x${source.height} source`
    );
  }
  const width = Math.max(1, Math.floor(source.width / zoom));
  const height = Math.max(1, Math.floor(source.height / zoom));
  const x = Math.min(
    source.width - width,
    Math.max(0, Math.round(detail.x - width / 2))
  );
  const y = Math.min(
    source.height - height,
    Math.max(0, Math.round(detail.y - height / 2))
  );
  return { x, y, width, height, zoom: source.width / width };
}

/**
 * The output-space anchor for an annotation attached to the detail:
 * the detail point mapped through the zoom window into the output
 * box, in continuous coordinates. Pure in (detail, window, output):
 * recompute it at any zoom step and it tracks the same source point.
 */
export function annotationAnchorAt(detail: Point, window: Box, output: Box): Point {
  return {
    x: output.x + ((detail.x - window.x) * output.width) / window.width,
    y: output.y + ((detail.y - window.y) * output.height) / window.height,
  };
}

/** The inverse of annotationAnchorAt: the source point an output
 * anchor names. Round-tripping an anchor through both functions
 * returns the detail point (to float precision), which is the
 * attachment proof the tests assert. */
export function sourcePointFromAnchor(anchor: Point, window: Box, output: Box): Point {
  return {
    x: window.x + ((anchor.x - output.x) * window.width) / output.width,
    y: window.y + ((anchor.y - output.y) * window.height) / output.height,
  };
}

/** The enlargement factor of a window shown in an output box: source
 * pixels are stretched by this factor on each axis; the reported
 * factor is the worse axis. */
export function upscaleFactor(window: Box, output: Box): number {
  return Math.max(output.width / window.width, output.height / window.height);
}

/**
 * The source size a close-up requires so that, at its maximum zoom,
 * the enlargement stays within `limit`: at zoom z the window is the
 * source divided by z, and it must still hold output / limit pixels
 * per axis. Dimensions are ceiled: a fractional requirement is a
 * whole pixel the source must actually have.
 */
export function requiredSourceSize(
  output: Box,
  maxZoom: number,
  limit: number
): Size {
  if (!(maxZoom >= 1) || !(limit >= 1)) {
    throw new Error(
      `maxZoom and limit must be >= 1, got zoom ${maxZoom}, limit ${limit}`
    );
  }
  return {
    width: Math.ceil((maxZoom * output.width) / limit),
    height: Math.ceil((maxZoom * output.height) / limit),
  };
}

export interface UpscaleAssessment {
  /** The enlargement factor at maximum zoom (worse axis). */
  factor: number;
  /** The effective limit applied. */
  limit: number;
  /** The source size the close-up would require at that limit. */
  required: Size;
  /** True when the factor is within the limit. */
  withinLimit: boolean;
}

/**
 * Assess a close-up: the window at maximum zoom, its enlargement
 * factor into the output box, and the source size that would be
 * required to stay within the limit. The effective limit is the
 * plan's declared max_upscale when present, tightened by (never
 * loosened past) UPSCALE_LIMIT for a readable-detail claim.
 */
export function assessUpscale(input: {
  source: Size;
  detail: Point;
  maxZoom: number;
  output: Box;
  declaredLimit?: number;
}): UpscaleAssessment {
  const window = zoomWindowAt(input.source, input.detail, input.maxZoom);
  const factor = upscaleFactor(window, input.output);
  const limit = Math.min(input.declaredLimit ?? UPSCALE_LIMIT, UPSCALE_LIMIT);
  return {
    factor,
    limit,
    required: requiredSourceSize(input.output, input.maxZoom, limit),
    withinLimit: factor <= limit,
  };
}

/** The QC finding for an out-of-limit close-up, or null when the
 * assessment is within its limit. Category MG_QC_FAILED (Section
 * 16.9 exit class 6): the plan is well-formed; its detail claim
 * fails acceptance. */
export function upscaleFinding(
  assessment: UpscaleAssessment,
  closeUpId: string,
  path: string
): CompositingFinding | null {
  if (assessment.withinLimit) return null;
  return {
    category: COMPOSITING_QC_CATEGORY,
    rule: "detail-upscale-exceeded",
    path,
    message:
      `close-up "${closeUpId}" enlarges source pixels by ` +
      `${assessment.factor.toFixed(3)}x at maximum zoom, beyond the limit ` +
      `${assessment.limit}x: at that enlargement the displayed detail is ` +
      "interpolated, not present in the source. The source would need at " +
      `least ${assessment.required.width}x${assessment.required.height} pixels ` +
      "to carry this claim (MG-012: flag excessive upscaling instead of " +
      "claiming new detail exists)",
  };
}
