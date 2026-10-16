// Layout variants and placement (Directive MG-014, Section 6 MG-014;
// Section 4.1 mode table; tests T06, T07).
//
// The model: a job's SHARED CONTENT (the message, the data, the asset
// facts, the essential copy) is stored exactly once. Every destination
// carries its OWN layout record: its canvas, its arrangement of the
// shared content, its plot geometry, its type assignments, its
// safe-area profile, and the placement it will actually be delivered
// at. A mobile variant is a recomposition of the shared content, never
// a scaled or cropped copy of the desktop layout; the resolver in
// resolve.ts proves that geometrically. The placement audit in
// audit.ts judges the variant at its final placement, so an inset
// PowerPoint graphic cannot pass merely because the full-frame
// original is readable.
//
// Error surface (Section 16.9): malformed layout documents are
// contract errors, category MG_SCHEMA_INVALID, exit class 2, thrown as
// LayoutError by the parse functions in validate.ts. Acceptance
// failures over well-formed documents are returned as findings by the
// resolver and the audit, never thrown.

import type { Box, Size } from "../compositing";
import type { ProtectedArea } from "../typography";

/** A font request in the MG-013 shape (family, weight, exact file).
 * Declared here because the typography barrel exports the audit but
 * not its FontSpec type; the shape is structurally identical to
 * typography/audit's FontSpec, so records pass between the modules
 * without adaptation. */
export interface LayoutFontSpec {
  family: string;
  weight: number;
  file: string;
}

/** The Section 16.9 category for structural layout (contract) errors. */
export const LAYOUT_CONTRACT_CATEGORY = "MG_SCHEMA_INVALID" as const;
/** Exit class for MG_SCHEMA_INVALID in the Section 16.9 table. */
export const LAYOUT_CONTRACT_EXIT_CLASS = 2 as const;

export interface LayoutFinding {
  kind: string;
  severity: "error" | "warning";
  /** The variant the finding belongs to, when scoped to one. */
  variantId: string | null;
  /** The element the finding belongs to, when scoped to one. */
  elementId: string | null;
  message: string;
  measured?: Record<string, number | string>;
}

/** Thrown by the parse functions; carries every structural finding. */
export class LayoutError extends Error {
  readonly category: typeof LAYOUT_CONTRACT_CATEGORY;
  readonly exitClass: number;
  readonly findings: LayoutFinding[];

  constructor(findings: LayoutFinding[]) {
    super(
      findings.length > 0
        ? findings.map((f) => `${f.kind}: ${f.message}`).join("; ")
        : "layout contract violation"
    );
    this.name = "LayoutError";
    this.category = LAYOUT_CONTRACT_CATEGORY;
    this.exitClass = LAYOUT_CONTRACT_EXIT_CLASS;
    this.findings = findings;
  }
}

/** The destinations a variant can target. The first four are the
 * Section 4.1 modes split by placement where placement changes the
 * contract (PowerPoint full-slide versus inset). */
export type DestinationId =
  | "powerpoint_full_slide"
  | "powerpoint_inset"
  | "vsl_desktop"
  | "vsl_mobile"
  | "standalone";

/** One row of a shared chart dataset: identity, label, value. The
 * value is part of the shared content; a variant may arrange it, it
 * may never restate it differently. */
export interface SharedChartRow {
  id: string;
  label: string;
  value: number;
}

/** The chart facts shared by every variant of a chart job. The domain
 * and scale type are the dataset's own (MG-015); comparability across
 * variants is judged against them. */
export interface SharedChartContent {
  datasetId: string;
  datasetKind: "illustrative" | "observed";
  units: string;
  domain: [number, number];
  scaleType: "linear" | "log";
  displayRounding: { decimals: number };
  rows: SharedChartRow[];
}

/** The image facts shared by every variant of an image-led job, in
 * the MG-011/MG-012 shapes: source size, normalized focal point,
 * normalized protected regions. Crops are solved per variant by the
 * MG-012 solver; no variant stores a crop of its own invention. */
export interface SharedImageContent {
  assetId: string;
  usage: "embed_original" | "approved_derivative" | "reference_only";
  source: Size;
  focalPoint: { x: number; y: number } | null;
  protectedRegions: Array<{
    id: string;
    label?: string;
    box: { x: number; y: number; width: number; height: number };
  }>;
}

/** The shared content record: stored once per job. */
export interface SharedContentRecord {
  schema_version: "1.0";
  id: string;
  /** The one message every variant must carry, stated once. */
  message: string;
  headline: string;
  support?: string;
  cta?: string;
  disclosure?: string;
  chart?: SharedChartContent;
  image?: SharedImageContent;
}

/** How a text element gets its copy: always by reference into the
 * shared content, never a literal restated in the variant. */
export type CopyRef =
  | { field: "headline" | "support" | "cta" | "disclosure" }
  | { rowLabel: string }
  | { rowValue: string };

export interface VariantTextElement {
  id: string;
  /** A typography role from references/typography-tokens.json. */
  role: string;
  ref: CopyRef;
  sizePx: number;
  box: Box;
  /** Overrides the variant's default font for this element. */
  font?: LayoutFontSpec;
}

/** The arrangement of a chart inside one variant.
 * - "rows": horizontal bars, one row per category, value axis along
 *   the plot width.
 * - "columns": vertical bars, one column per category, value axis
 *   along the plot height.
 * - "staged_rows": rows shown one beat at a time in the plot; the
 *   mobile staging pattern for comparisons that cannot share a
 *   vertical frame. `beats` is required and each slot names its beat.
 */
export interface ChartArrangement {
  kind: "rows" | "columns" | "staged_rows";
  plot: Box;
  barThickness: number;
  slots: Array<{ rowId: string; beatIndex?: number }>;
  beats?: Array<{ index: number; rowIds: string[] }>;
}

/** Where a variant's canvas lands at delivery.
 * - full_frame: the canvas is the frame.
 * - inset: the canvas is displayed at `display` pixels inside a
 *   slide of the declared size. `displayMm` may accompany or replace
 *   display pixels: presentation placements are often specified in
 *   millimetres, and the audit converts through the slide's own
 *   pixel-per-millimetre ratio rather than assuming a DPI. */
export type PlacementSpec =
  | { kind: "full_frame" }
  | {
      kind: "inset";
      display?: { widthPx: number; heightPx: number };
      displayMm?: { widthMm: number; heightMm: number };
      slide: {
        widthPx: number;
        heightPx: number;
        widthMm: number;
        heightMm: number;
      };
    };

/** One destination's layout record. */
export interface LayoutVariant {
  schema_version: "1.0";
  id: string;
  contentId: string;
  destination: DestinationId;
  canvas: Size;
  /** The aspect the delivered file keeps, reduced (for example
   * { w: 16, h: 9 }). It must equal the canvas aspect: a placement
   * inside a slide layout never rewrites the export's aspect. */
  exportAspect: { w: number; h: number };
  font: LayoutFontSpec;
  /** Safe-area profile id from profiles.ts. The profile must be the
   * actual destination's profile, measured for this variant's
   * canvas. */
  safeAreaProfile: string;
  /** True only when the destination explicitly declares delivery
   * inside a social platform's player. A plain mobile VSL never
   * inherits social-platform chrome. */
  platformDelivery?: boolean;
  arrangement?: ChartArrangement;
  /** For image content: the canvas box the solved crop is placed
   * into on this variant. */
  imageBox?: Box;
  /** Canvas-space protected areas beyond the image's own regions
   * (for example a fixed logo zone on a chart variant). */
  protectedAreas?: ProtectedArea[];
  elements: VariantTextElement[];
  placement: PlacementSpec;
}

/** The display size and effective scale a placement produces. */
export interface PlacementFacts {
  displayWidthPx: number;
  displayHeightPx: number;
  /** displayWidthPx over canvas width: the factor every authored
   * size is actually seen at. */
  scale: number;
  /** How the display size was obtained, for the record. */
  basis: "full_frame" | "declared_px" | "declared_mm";
}

/** Reduce an aspect to lowest terms. */
export function reduceAspect(size: Size): { w: number; h: number } {
  const gcd = (a: number, b: number): number => (b === 0 ? a : gcd(b, a % b));
  const g = gcd(size.width, size.height);
  return { w: size.width / g, h: size.height / g };
}

/** The aspect class a destination requires of its canvas. */
export function destinationAspect(
  destination: DestinationId
): { w: number; h: number } | Array<{ w: number; h: number }> {
  switch (destination) {
    case "powerpoint_full_slide":
    case "powerpoint_inset":
    case "vsl_desktop":
      return { w: 16, h: 9 };
    case "vsl_mobile":
      return { w: 9, h: 16 };
    case "standalone":
      return [
        { w: 16, h: 9 },
        { w: 9, h: 16 },
      ];
  }
}
