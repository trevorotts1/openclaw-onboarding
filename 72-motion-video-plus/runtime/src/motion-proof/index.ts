// Motion proof layer (Directive MG-032): prove actual subject
// motion, not decorative activity.
//
//   schema.ts    the motion assertion schema (the layer's own
//                versioned JSON Schema beside the canonical contracts)
//   geometry.ts  expectation derivation from scene specifications
//   measure.ts   raster measurement inside subject regions
//   evaluate.ts  the evaluator: gates, measurement, verdicts, and the
//                proof package writer
export * from "./types";
export { validateMotionProofCase } from "./schema";
export {
  deriveBarsGeometry,
  deriveTransitGeometry,
  type BarsGeometry,
  type TransitGeometry,
} from "./geometry";
export {
  COLOR_MATCH_TOLERANCE_SUM,
  accentCentroidInWindow,
  accentCountInBox,
  hexToRgb,
  meanAbsDiffOutsideRegions,
  measureBarWidthInRegion,
} from "./measure";
export { evaluateMotionProof } from "./evaluate";
