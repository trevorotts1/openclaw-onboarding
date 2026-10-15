// Crop and focal-point solver (Directive MG-012; Sections 16.2 box,
// 17.1 M08). One shared implementation for every image-led component:
// given a source image, a target aspect, a focal point, and protected
// regions, it computes the integer crop rectangle a renderer must use.
//
// Guarantees, by construction:
// - No stretch, ever. The solver only chooses a sub-rectangle of the
//   source; placement (placementForCrop) maps it into a target box
//   with ONE uniform scale. The crop's aspect is the target aspect up
//   to the documented integer rounding below, and any residue appears
//   as a symmetric margin of at most one target pixel, never as an
//   anisotropic stretch.
// - The focal point lies inside the crop, and every protected region
//   (face, logo, proof detail) lies FULLY inside the crop, whenever
//   that is geometrically possible.
// - When it is not possible, the solver returns a structured
//   impossibility naming the offending region(s). It never returns a
//   crop that silently crops a protected region or loses the focal
//   point.
//
// Integer rounding, stated once for the whole module: the ideal crop
// dimensions are real numbers (source extent times the aspect ratio);
// the returned dimensions are their floors. Flooring preserves every
// containment inequality whose right side is an integer (floor(v) >= n
// exactly when v >= n for integer n), so a protected region that fits
// the ideal crop still fits the floored crop. The crop position is the
// focal-centered position clamped into the feasible integer interval
// and rounded to the nearest integer (halves round up); the interval
// endpoints are integers, so the rounded position stays feasible.

import {
  Box,
  NormalizedBox,
  NormalizedPoint,
  Point,
  ProtectedRegion,
  Size,
  boxContains,
  boxUnion,
  isBox,
  isFiniteNumber,
  isPositiveInt,
  isSize,
  normalizedBoxToSource,
  normalizedPointToSource,
} from "./types";

/** A target aspect as a ratio pair, for example { w: 16, h: 9 }. */
export interface AspectRatio {
  w: number;
  h: number;
}

export interface CropRequest {
  /** Source image dimensions in pixels. */
  source: Size;
  /** The aspect the crop must fill, as a ratio pair. */
  targetAspect: AspectRatio;
  /** Continuous source position of the focal point, or null. Convert
   * a manifest focal point with normalizedPointToSource. */
  focalPoint?: Point | null;
  /** Protected regions in integer source pixels. Convert sidecar
   * regions with protectedRegionsFromNormalized. */
  protectedRegions?: ProtectedRegion[];
}

/** A solved crop: an integer sub-rectangle of the source. */
export interface CropSolution {
  ok: true;
  crop: Box;
  /** The uniform scale that maps this crop into a target box is
   * computed by placementForCrop; the solver itself never scales
   * anisotropically. */
  aspect: AspectRatio;
}

export interface CropImpossibility {
  ok: false;
  /** Ids of the protected regions responsible, or ["<focal>"] when the
   * focal point alone cannot coexist with the regions. */
  regionIds: string[];
  /** Machine reason: "region-exceeds-crop", "regions-union-exceeds-crop",
   * or "focal-region-conflict". */
  reason:
    | "region-exceeds-crop"
    | "regions-union-exceeds-crop"
    | "focal-region-conflict";
  message: string;
}

export type CropResult = CropSolution | CropImpossibility;

/** Convert sidecar protected regions (normalized boxes with labels)
 * into integer source-pixel regions. Throws a plain Error naming the
 * region when a declared region collapses under rounding: that is a
 * malformed input document, not a geometry outcome. */
export function protectedRegionsFromNormalized(
  regions: Array<{ id: string; label?: string; box: NormalizedBox }>,
  source: Size
): ProtectedRegion[] {
  return regions.map((region) => {
    const box = normalizedBoxToSource(region.box, source);
    if (!box) {
      throw new Error(
        `protected region "${region.id}" collapses to nothing inside a ` +
          `${source.width}x${source.height} source: its normalized box ` +
          "rounds to less than one pixel"
      );
    }
    return { id: region.id, label: region.label, box };
  });
}

/**
 * The largest real-valued crop with the target aspect inside the
 * source, before integer flooring. Exported for tests and evidence:
 * containment decisions are made against the floored dimensions.
 */
export function idealCropSize(source: Size, aspect: AspectRatio): Size {
  if (source.width * aspect.h <= source.height * aspect.w) {
    // Width is the limiting extent.
    return { width: source.width, height: (source.width * aspect.h) / aspect.w };
  }
  return { width: (source.height * aspect.w) / aspect.h, height: source.height };
}

function clampToInterval(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

/**
 * Solve the crop. Pure and deterministic: the same request always
 * yields the same crop or the same impossibility.
 */
export function solveCrop(request: CropRequest): CropResult {
  const { source, targetAspect } = request;
  if (!isSize(source)) {
    throw new Error(
      `crop source must be a positive integer size, got ${JSON.stringify(source)}`
    );
  }
  if (
    !isPositiveInt(targetAspect?.w) ||
    !isPositiveInt(targetAspect?.h)
  ) {
    throw new Error(
      `target aspect must be positive integers, got ${JSON.stringify(targetAspect)}`
    );
  }
  const focal = request.focalPoint ?? null;
  if (
    focal !== null &&
    (!isFiniteNumber(focal.x) ||
      !isFiniteNumber(focal.y) ||
      focal.x < 0 ||
      focal.y < 0 ||
      focal.x > source.width ||
      focal.y > source.height)
  ) {
    throw new Error(
      `focal point ${JSON.stringify(focal)} lies outside the ` +
        `${source.width}x${source.height} source`
    );
  }
  const regions = request.protectedRegions ?? [];
  for (const region of regions) {
    if (!isBox(region.box)) {
      throw new Error(
        `protected region "${region.id}" has a malformed box ${JSON.stringify(region.box)}`
      );
    }
    if (!boxContains({ x: 0, y: 0, width: source.width, height: source.height }, region.box)) {
      throw new Error(
        `protected region "${region.id}" extends outside the ` +
          `${source.width}x${source.height} source`
      );
    }
  }

  const ideal = idealCropSize(source, targetAspect);
  const cropWidth = Math.floor(ideal.width);
  const cropHeight = Math.floor(ideal.height);
  if (cropWidth < 1 || cropHeight < 1) {
    throw new Error(
      `a ${targetAspect.w}:${targetAspect.h} crop of a ${source.width}x${source.height} ` +
        "source is smaller than one pixel: the source is too small for the aspect"
    );
  }

  // Containment feasibility: the union of the protected regions must
  // fit inside the crop dimensions. A single region larger than the
  // crop is named on its own; otherwise the combination is named.
  let union: Box | null = null;
  if (regions.length > 0) {
    const oversized = regions.filter(
      (r) => r.box.width > cropWidth || r.box.height > cropHeight
    );
    if (oversized.length > 0) {
      const names = oversized.map((r) => `"${r.id}"`).join(", ");
      return {
        ok: false,
        regionIds: oversized.map((r) => r.id),
        reason: "region-exceeds-crop",
        message:
          `protected region(s) ${names} cannot fit inside a ` +
          `${targetAspect.w}:${targetAspect.h} crop of a ${source.width}x${source.height} ` +
          `source (largest such crop is ${cropWidth}x${cropHeight}): a crop must ` +
          "contain a protected region whole or not claim to protect it",
      };
    }
    union = boxUnion(regions.map((r) => r.box));
    if (union.width > cropWidth || union.height > cropHeight) {
      const names = regions.map((r) => `"${r.id}"`).join(", ");
      return {
        ok: false,
        regionIds: regions.map((r) => r.id),
        reason: "regions-union-exceeds-crop",
        message:
          `protected regions ${names} together span ${union.width}x${union.height}, ` +
          `which no ${targetAspect.w}:${targetAspect.h} crop of a ${source.width}x${source.height} ` +
          `source (largest ${cropWidth}x${cropHeight}) can contain whole`,
      };
    }
  }

  // Feasible position interval per axis: the crop must stay inside the
  // source, contain the union (when one exists), and contain the focal
  // point (when one is declared). Endpoints are integers except the
  // focal terms, which are ceiled/floored into the interval.
  const axis = (
    extent: number,
    cropExtent: number,
    unionStart: number | null,
    unionExtent: number,
    focalPos: number | null
  ): { lo: number; hi: number } => {
    let lo = 0;
    let hi = extent - cropExtent;
    if (unionStart !== null) {
      lo = Math.max(lo, unionStart + unionExtent - cropExtent);
      hi = Math.min(hi, unionStart);
    }
    if (focalPos !== null) {
      lo = Math.max(lo, Math.ceil(focalPos - cropExtent));
      hi = Math.min(hi, Math.floor(focalPos));
    }
    return { lo, hi };
  };
  const xAxis = axis(
    source.width,
    cropWidth,
    union ? union.x : null,
    union ? union.width : 0,
    focal ? focal.x : null
  );
  const yAxis = axis(
    source.height,
    cropHeight,
    union ? union.y : null,
    union ? union.height : 0,
    focal ? focal.y : null
  );
  if (xAxis.lo > xAxis.hi || yAxis.lo > yAxis.hi) {
    // The union fits the crop on its own (checked above), so an empty
    // interval means the focal point cannot share a crop with the
    // protected regions: the crop is too small to hold both.
    const names = regions.map((r) => `"${r.id}"`).join(", ");
    return {
      ok: false,
      regionIds: [...regions.map((r) => r.id), "<focal>"],
      reason: "focal-region-conflict",
      message:
        `no ${targetAspect.w}:${targetAspect.h} crop of a ${source.width}x${source.height} source can ` +
        `contain both the focal point (${focal ? `${focal.x}, ${focal.y}` : "none"}) and the ` +
        `protected region(s) ${names || "(none)"}: the crop (${cropWidth}x${cropHeight}) ` +
        "is too small to span them",
    };
  }

  // Desired position: centered on the focal point when one is
  // declared, centered on the source otherwise; clamped into the
  // feasible interval and rounded to the nearest integer (the
  // endpoints are integers, so rounding stays inside the interval).
  const desiredX = focal ? focal.x - cropWidth / 2 : (source.width - cropWidth) / 2;
  const desiredY = focal ? focal.y - cropHeight / 2 : (source.height - cropHeight) / 2;
  const x = Math.round(clampToInterval(desiredX, xAxis.lo, xAxis.hi));
  const y = Math.round(clampToInterval(desiredY, yAxis.lo, yAxis.hi));
  const crop: Box = { x, y, width: cropWidth, height: cropHeight };

  // Construction proof, checked rather than assumed: the crop lies in
  // the source, contains the union, and contains the focal point.
  const bounds: Box = { x: 0, y: 0, width: source.width, height: source.height };
  if (!boxContains(bounds, crop)) {
    throw new Error(`internal: solved crop ${JSON.stringify(crop)} escapes the source`);
  }
  if (union && !boxContains(crop, union)) {
    throw new Error(`internal: solved crop ${JSON.stringify(crop)} loses the protected union`);
  }
  if (
    focal &&
    (focal.x < crop.x || focal.x > crop.x + crop.width ||
      focal.y < crop.y || focal.y > crop.y + crop.height)
  ) {
    throw new Error(`internal: solved crop ${JSON.stringify(crop)} loses the focal point`);
  }
  return { ok: true, crop, aspect: { ...targetAspect } };
}

/** The placement of a solved crop inside a target box: ONE uniform
 * scale and a centered drawn rectangle. The drawn size is the crop
 * size times the scale, each dimension rounded to the nearest pixel;
 * the scale itself is never split per axis, so the image is never
 * stretched. Any residue is a symmetric margin of at most one pixel. */
export interface CropPlacement {
  /** The single uniform scale applied to both axes. */
  scale: number;
  /** Where the crop lands inside the target box, in target pixels. */
  drawn: Box;
}

export function placementForCrop(crop: Box, target: Size): CropPlacement {
  if (!isSize(target)) {
    throw new Error(`placement target must be a positive integer size, got ${JSON.stringify(target)}`);
  }
  const scale = Math.min(target.width / crop.width, target.height / crop.height);
  const drawnWidth = Math.round(crop.width * scale);
  const drawnHeight = Math.round(crop.height * scale);
  return {
    scale,
    drawn: {
      x: Math.floor((target.width - drawnWidth) / 2),
      y: Math.floor((target.height - drawnHeight) / 2),
      width: drawnWidth,
      height: drawnHeight,
    },
  };
}

/**
 * Map a source-space box through a crop and its placement into target
 * (canvas) coordinates. The result rounds OUTWARD (floor the origin,
 * ceil the far edge): a protected region mapped for an intersection
 * check is never smaller than its true raster footprint, so the M08
 * text-protection check cannot be rounded into a pass.
 */
export function mapSourceBoxToTarget(box: Box, crop: Box, placement: CropPlacement): Box {
  const { scale, drawn } = placement;
  const x0 = drawn.x + (box.x - crop.x) * scale;
  const y0 = drawn.y + (box.y - crop.y) * scale;
  const x1 = drawn.x + (box.x + box.width - crop.x) * scale;
  const y1 = drawn.y + (box.y + box.height - crop.y) * scale;
  const ix = Math.floor(x0);
  const iy = Math.floor(y0);
  return {
    x: ix,
    y: iy,
    width: Math.ceil(x1) - ix,
    height: Math.ceil(y1) - iy,
  };
}

/** Convenience for callers holding manifest-shaped inputs: solve
 * directly from a normalized focal point and normalized protected
 * regions. */
export function solveCropFromNormalized(
  source: Size,
  targetAspect: AspectRatio,
  focalPoint: NormalizedPoint | null,
  protectedRegions: Array<{ id: string; label?: string; box: NormalizedBox }>
): CropResult {
  return solveCrop({
    source,
    targetAspect,
    focalPoint: focalPoint ? normalizedPointToSource(focalPoint, source) : null,
    protectedRegions: protectedRegionsFromNormalized(protectedRegions, source),
  });
}
