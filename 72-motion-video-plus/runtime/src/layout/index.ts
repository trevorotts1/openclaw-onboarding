// Layout variants and placement (Directive MG-014): one shared
// content record per job, one layout record per destination, a
// resolver that proves recomposition and scale comparability, and a
// placement audit that judges every variant at the size it will
// actually be seen.

export {
  LAYOUT_CONTRACT_CATEGORY,
  LAYOUT_CONTRACT_EXIT_CLASS,
  LayoutError,
  destinationAspect,
  reduceAspect,
  type ChartArrangement,
  type CopyRef,
  type DestinationId,
  type LayoutFinding,
  type LayoutFontSpec,
  type LayoutVariant,
  type PlacementFacts,
  type PlacementSpec,
  type SharedChartContent,
  type SharedChartRow,
  type SharedContentRecord,
  type SharedImageContent,
  type VariantTextElement,
} from "./types";

export {
  getSafeAreaProfile,
  listSafeAreaProfiles,
  type SafeAreaProfile,
  type SafeAreaProfileKind,
  type UnsafeZone,
} from "./profiles";

export {
  LAYOUT_ID_PATTERN,
  assertLayoutVariant,
  assertSharedContent,
  chartScaleFacts,
  formatRowValue,
  materializeCopy,
  toChartDataset,
  valueAxisExtent,
  type ChartScaleFacts,
} from "./validate";

export {
  SCALE_DUPLICATE_TOLERANCE,
  isScaledDuplicate,
  resolveVariantSet,
  type VariantResolution,
  type VariantSetResolution,
} from "./resolve";

export {
  auditPlacement,
  placementFacts,
  type ImagePlacementFacts,
  type PlacementAuditResult,
} from "./audit";
