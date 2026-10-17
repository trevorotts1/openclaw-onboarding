// Chart data contracts, scales, geometry, and formatting
// (Directive MG-015). One shared implementation for every chart
// component (MG-016 builds on this), the validators, and the tests.

export {
  DATASET_ERROR_CATEGORY,
  DATASET_ERROR_EXIT_CLASS,
  ChartContractError,
  assertChartDataset,
  numbersMatch,
  resolveRowValues,
  validateCanonicalShape,
  validateDataset,
  type ChartDataset,
  type ChartDatasetRow,
  type DatasetErrorCategory,
  type DatasetFinding,
  type DatasetKind,
  type DatasetSortDeclaration,
  type DisplayRounding,
  type MissingValuePolicy,
  type ScaleType,
} from "./dataset";

export {
  barGeometry,
  clampProgress,
  containerOvershoot,
  createDatasetScale,
  createLinearScale,
  createLogScale,
  revealBarGeometry,
  revealWidth,
  type BarGeometry,
  type BarGeometryOptions,
  type LinearScale,
  type LogScale,
} from "./scale";

export { bandLayout, type BandLayout } from "./bands";

export { formatDatasetValue, formatValue } from "./format";
