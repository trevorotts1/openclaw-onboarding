// Comparison layouts (Directive MG-012): side-by-side and
// before/after plans in which each image is framed independently.
//
// Each image keeps its own focal point and protected regions: the
// layout solves a separate crop per image against its own placement
// box (the crop solver's per-image result), so honoring one image's
// focal constraints never silently reframes the other. A solver
// impossibility for either image is returned in that image's slot,
// not thrown and not papered over with a fallback crop.

import { Box, Size } from "./types";
import {
  AspectRatio,
  CropRequest,
  CropResult,
  placementForCrop,
  solveCrop,
  type CropPlacement,
} from "./crop";

/** A comparison input: a crop request without an aspect, because the
 * layout assigns each image the aspect of its own slot. */
export interface ComparisonImage extends Omit<CropRequest, "targetAspect"> {
  id: string;
}

export interface ComparisonSlot {
  id: string;
  /** Where this image lands on the canvas. */
  box: Box;
  /** The crop solved for this image alone, or its impossibility. */
  crop: CropResult;
  /** The placement of the solved crop in the slot box; null when the
   * crop was impossible. */
  placement: CropPlacement | null;
}

export interface ComparisonPlan {
  mode: "side_by_side" | "before_after";
  slots: ComparisonSlot[];
}

function slotFor(image: ComparisonImage, box: Box): ComparisonSlot {
  const aspect: AspectRatio = { w: box.width, h: box.height };
  const crop = solveCrop({ ...image, targetAspect: aspect });
  return {
    id: image.id,
    box,
    crop,
    placement: crop.ok ? placementForCrop(crop.crop, box) : null,
  };
}

/**
 * Plan a comparison of exactly two images on a canvas.
 * - side_by_side: the canvas splits along its width with a centered
 *   gutter (an even split; when the remaining width is odd the left
 *   slot takes the extra pixel). Each slot is full height.
 * - before_after: both images take the full canvas (the wipe between
 *   them is a reveal over the second image's slot, expressed by the
 *   caller with the reveal geometry); each is still cropped against
 *   its own focal constraints for that same box.
 */
export function planComparison(input: {
  canvas: Size;
  images: [ComparisonImage, ComparisonImage];
  mode: "side_by_side" | "before_after";
  /** Gutter width in canvas pixels for side_by_side. Default 24. */
  gutter?: number;
}): ComparisonPlan {
  const { canvas, images, mode } = input;
  const gutter = input.gutter ?? 24;
  if (!Number.isInteger(gutter) || gutter < 0 || gutter >= canvas.width) {
    throw new Error(`gutter must be an integer in [0, canvas width), got ${gutter}`);
  }
  if (mode === "before_after") {
    const full: Box = { x: 0, y: 0, width: canvas.width, height: canvas.height };
    return { mode, slots: images.map((image) => slotFor(image, full)) };
  }
  const leftWidth = Math.floor((canvas.width - gutter) / 2);
  const rightWidth = canvas.width - gutter - leftWidth;
  const left: Box = { x: 0, y: 0, width: leftWidth, height: canvas.height };
  const right: Box = {
    x: leftWidth + gutter,
    y: 0,
    width: rightWidth,
    height: canvas.height,
  };
  return { mode, slots: [slotFor(images[0], left), slotFor(images[1], right)] };
}
