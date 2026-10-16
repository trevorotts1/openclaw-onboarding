// Typography system (Directive MG-013): role tokens, actual-font
// measurement, the fit/overflow decider, and the rendered-layout audit.

export {
  TypographyError,
  parseFontBytes,
  loadFontFile,
  measureString,
  lineHeightPx,
  layoutText,
  type ParsedFont,
  type TextMeasurement,
  type TextLayout,
  type LaidOutLine,
} from "./font-metrics";
export {
  loadTypographyTokens,
  tokensPath,
  type RoleToken,
  type RoleException,
  type TypographyTokens,
} from "./tokens";
export {
  decideFit,
  BELOW_FLOOR_NEAR_MISS_RATIO,
  type FitBox,
  type FitRequest,
  type FitResult,
} from "./fit";
export {
  auditLayout,
  placementScale,
  LOW_CAP_HEIGHT_RATIO,
  type AuditResult,
  type ElementMeasurement,
  type LayoutBox,
  type LayoutElement,
  type LayoutRecord,
  type Placement,
  type ProtectedArea,
  type TypeFinding,
} from "./audit";
