// Shared geometry and plan types for deliberate image and object
// compositing (Directive MG-012, Sections 5.4, 16.9, 17.1 M08/M10).
//
// Coordinate conventions used by every function in this module:
// - Source space is the asset's own pixel grid, origin top-left, x
//   right, y down. Pixel boxes are INTEGER rectangles: a box
//   {x, y, width, height} covers pixels [x, x+width) x [y, y+height),
//   the same half-open reading the timeline uses for frames.
// - Normalized coordinates (the asset manifest's focal_point and the
//   provenance sidecar's protected_regions) are continuous values in
//   [0, 1] over the source extent: a normalized point (nx, ny) sits at
//   continuous source position (nx * width, ny * height).
// - Conversion from normalized to integer source boxes rounds
//   OUTWARD (floor the origin, ceil the far edge), so a protected
//   region is never understated by rounding. The focal point converts
//   to a continuous position and is never rounded before the solver
//   has used it.
// - Canvas space is the composition's output pixel grid. Boxes a plan
//   declares for text and subjects live in canvas space.
//
// Error surface (Section 16.9): structural plan problems are contract
// errors, category MG_SCHEMA_INVALID, exit class 2. Acceptance
// failures over a structurally valid plan are MG_QC_FAILED, exit
// class 6 ("actual result failed acceptance"). A thrown
// CompositingError reports the first blocking class in the Section
// 16.9 order (validation before QC) while carrying every finding.

/** The Section 16.9 category for structural plan (contract) errors. */
export const COMPOSITING_CONTRACT_CATEGORY = "MG_SCHEMA_INVALID" as const;
/** The Section 16.9 category for compositing acceptance failures. */
export const COMPOSITING_QC_CATEGORY = "MG_QC_FAILED" as const;
/** Exit class for MG_SCHEMA_INVALID in the Section 16.9 table. */
export const COMPOSITING_CONTRACT_EXIT_CLASS = 2 as const;
/** Exit class for MG_QC_FAILED in the Section 16.9 table. */
export const COMPOSITING_QC_EXIT_CLASS = 6 as const;

export type CompositingErrorCategory =
  | typeof COMPOSITING_CONTRACT_CATEGORY
  | typeof COMPOSITING_QC_CATEGORY;

export interface CompositingFinding {
  category: CompositingErrorCategory;
  /** Stable machine rule id, for example "subject-visibility". */
  rule: string;
  /** Plan-relative locator, for example "subject_motion" or "text_boxes[0]". */
  path: string;
  message: string;
}

/** Thrown by the asserting entry points; carries every finding. The
 * category and exit class follow the first blocking class in the
 * Section 16.9 order: contract (exit 2) before QC (exit 6). */
export class CompositingError extends Error {
  readonly category: CompositingErrorCategory;
  readonly exitClass: number;
  readonly findings: CompositingFinding[];

  constructor(findings: CompositingFinding[]) {
    super(
      findings.length > 0
        ? findings.map((f) => `${f.path}: ${f.message}`).join("; ")
        : "compositing contract violation"
    );
    this.name = "CompositingError";
    this.findings = findings;
    const hasContract = findings.some(
      (f) => f.category === COMPOSITING_CONTRACT_CATEGORY
    );
    this.category = hasContract
      ? COMPOSITING_CONTRACT_CATEGORY
      : COMPOSITING_QC_CATEGORY;
    this.exitClass = hasContract
      ? COMPOSITING_CONTRACT_EXIT_CLASS
      : COMPOSITING_QC_EXIT_CLASS;
  }
}

/** An integer pixel size. Both dimensions are positive integers. */
export interface Size {
  width: number;
  height: number;
}

/** An integer pixel box (the contracts schema's `box` shape). */
export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A continuous point in source coordinates. */
export interface Point {
  x: number;
  y: number;
}

/** A normalized point in [0, 1] over the source extent (the manifest
 * focal_point shape). */
export interface NormalizedPoint {
  x: number;
  y: number;
}

/** A normalized box in [0, 1] over the source extent (the provenance
 * sidecar's protected_regions shape), with its label. */
export interface NormalizedBox {
  x: number;
  y: number;
  width: number;
  height: number;
  label?: string;
}

/** A protected region in integer source pixels: a face, a logo, or a
 * proof detail that crops, motion, and text must not violate. */
export interface ProtectedRegion {
  id: string;
  /** Human label from the sidecar, for example "face" or "logo". */
  label?: string;
  box: Box;
}

/** Internal frame interval in the Section 5.4 half-open convention:
 * frames startFrame .. endFrameExclusive - 1. */
export interface FrameRange {
  startFrame: number;
  endFrameExclusive: number;
}

/** The asset usage classes of the MG-011 manifest vocabulary. */
export type AssetUsage =
  | "embed_original"
  | "approved_derivative"
  | "reference_only";

/** True when a value is a non-null, non-array object. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** True when a value is a positive integer. */
export function isPositiveInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

/** True when a value is a non-negative integer. */
export function isNonNegativeInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

/** True when a value is a finite number. */
export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Structural check for an integer pixel box. */
export function isBox(value: unknown): value is Box {
  return (
    isRecord(value) &&
    isNonNegativeInt(value.x) &&
    isNonNegativeInt(value.y) &&
    isPositiveInt(value.width) &&
    isPositiveInt(value.height)
  );
}

/** Structural check for a positive integer size. */
export function isSize(value: unknown): value is Size {
  return (
    isRecord(value) && isPositiveInt(value.width) && isPositiveInt(value.height)
  );
}

/** Positive-area intersection of two boxes, or null when they do not
 * overlap. Touching edges do not intersect: the boxes are half-open. */
export function boxIntersection(a: Box, b: Box): Box | null {
  const x = Math.max(a.x, b.x);
  const y = Math.max(a.y, b.y);
  const width = Math.min(a.x + a.width, b.x + b.width) - x;
  const height = Math.min(a.y + a.height, b.y + b.height) - y;
  if (width <= 0 || height <= 0) return null;
  return { x, y, width, height };
}

/** True when `inner` lies fully inside `outer` (edges may touch). */
export function boxContains(outer: Box, inner: Box): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  );
}

/** The smallest box containing every given box. Requires >= 1 box. */
export function boxUnion(boxes: Box[]): Box {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const b of boxes) {
    x0 = Math.min(x0, b.x);
    y0 = Math.min(y0, b.y);
    x1 = Math.max(x1, b.x + b.width);
    y1 = Math.max(y1, b.y + b.height);
  }
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

/**
 * Convert a normalized box to an integer source box, rounding
 * OUTWARD (floor the origin, ceil the far edge) and clamping to the
 * source, so the protected area a crop must respect is never smaller
 * than the declared region. Returns null when the declared region
 * collapses to nothing inside the source (a contract error upstream).
 */
export function normalizedBoxToSource(box: NormalizedBox, source: Size): Box | null {
  const x0 = Math.max(0, Math.floor(box.x * source.width));
  const y0 = Math.max(0, Math.floor(box.y * source.height));
  const x1 = Math.min(source.width, Math.ceil((box.x + box.width) * source.width));
  const y1 = Math.min(source.height, Math.ceil((box.y + box.height) * source.height));
  if (x1 - x0 < 1 || y1 - y0 < 1) return null;
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

/** Convert a normalized focal point to a continuous source position.
 * The position stays unrounded: the crop solver works with the exact
 * point and only the final integer crop is rounded. */
export function normalizedPointToSource(point: NormalizedPoint, source: Size): Point {
  return { x: point.x * source.width, y: point.y * source.height };
}
