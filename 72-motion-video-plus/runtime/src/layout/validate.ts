// Structural validation of layout documents (Directive MG-014;
// Sections 16.6, 16.9). parseSharedContent and parseLayoutVariant
// check a document's shape and its internal claims (closed key sets,
// id patterns, canvas and box sanity, arrangement and placement
// shapes) and throw a LayoutError carrying every contract finding
// (MG_SCHEMA_INVALID, exit class 2). Cross-document and acceptance
// questions (does this variant recompose or merely scale, do the
// scales compare, does the placement pass) belong to resolve.ts and
// audit.ts, never to parse.

import {
  createDatasetScale,
  formatDatasetValue,
  type ChartDataset,
} from "../charts";
import {
  isBox,
  isFiniteNumber,
  isNonNegativeInt,
  isPositiveInt,
  isRecord,
  isSize,
} from "../compositing";
import {
  LAYOUT_CONTRACT_CATEGORY,
  LayoutError,
  type ChartArrangement,
  type CopyRef,
  type DestinationId,
  type LayoutFinding,
  type LayoutFontSpec,
  type LayoutVariant,
  type PlacementSpec,
  type SharedContentRecord,
  type VariantTextElement,
} from "./types";

export const LAYOUT_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;

export const DESTINATIONS: readonly DestinationId[] = [
  "powerpoint_full_slide",
  "powerpoint_inset",
  "vsl_desktop",
  "vsl_mobile",
  "standalone",
];

const CONTENT_KEYS = new Set([
  "schema_version",
  "id",
  "message",
  "headline",
  "support",
  "cta",
  "disclosure",
  "chart",
  "image",
]);

const CHART_KEYS = new Set([
  "datasetId",
  "datasetKind",
  "units",
  "domain",
  "scaleType",
  "displayRounding",
  "rows",
]);

const IMAGE_KEYS = new Set([
  "assetId",
  "usage",
  "source",
  "focalPoint",
  "protectedRegions",
]);

const VARIANT_KEYS = new Set([
  "schema_version",
  "id",
  "contentId",
  "destination",
  "canvas",
  "exportAspect",
  "font",
  "safeAreaProfile",
  "platformDelivery",
  "arrangement",
  "imageBox",
  "protectedAreas",
  "elements",
  "placement",
]);

function finding(path: string, message: string): LayoutFinding {
  return {
    kind: "LAYOUT_SCHEMA_INVALID",
    severity: "error",
    variantId: null,
    elementId: null,
    message: `${path}: ${message}`,
  };
}

function unknownKeys(
  doc: Record<string, unknown>,
  allowed: Set<string>,
  path: string,
  findings: LayoutFinding[]
): void {
  for (const key of Object.keys(doc)) {
    if (!allowed.has(key)) {
      findings.push(
        finding(path, `unknown key "${key}" (closed record: undeclared fields are contract errors)`)
      );
    }
  }
}

function checkFontSpec(value: unknown, path: string, findings: LayoutFinding[]): void {
  if (!isRecord(value)) {
    findings.push(finding(path, "font must be an object { family, weight, file }"));
    return;
  }
  if (typeof value.family !== "string" || value.family.length === 0) {
    findings.push(finding(path, "font.family must be a non-empty string"));
  }
  if (!isPositiveInt(value.weight)) {
    findings.push(finding(path, "font.weight must be a positive integer weight class"));
  }
  if (typeof value.file !== "string" || value.file.length === 0) {
    findings.push(finding(path, "font.file must name the exact font file"));
  }
}

export function assertSharedContent(doc: unknown): SharedContentRecord {
  const findings: LayoutFinding[] = [];
  if (!isRecord(doc)) {
    throw new LayoutError([finding("$", "shared content must be an object")]);
  }
  unknownKeys(doc, CONTENT_KEYS, "$", findings);
  if (doc.schema_version !== "1.0") {
    findings.push(finding("$.schema_version", 'must be "1.0"'));
  }
  if (typeof doc.id !== "string" || !LAYOUT_ID_PATTERN.test(doc.id)) {
    findings.push(finding("$.id", "must be an id matching the layout id pattern"));
  }
  if (typeof doc.message !== "string" || doc.message.length === 0) {
    findings.push(finding("$.message", "the shared message must be stated, once"));
  }
  if (typeof doc.headline !== "string" || doc.headline.length === 0) {
    findings.push(finding("$.headline", "shared content must carry a headline"));
  }
  for (const field of ["support", "cta", "disclosure"] as const) {
    if (doc[field] !== undefined && typeof doc[field] !== "string") {
      findings.push(finding(`$.${field}`, "must be a string when present"));
    }
  }
  if (doc.chart !== undefined) {
    const chart = doc.chart;
    if (!isRecord(chart)) {
      findings.push(finding("$.chart", "must be an object"));
    } else {
      unknownKeys(chart, CHART_KEYS, "$.chart", findings);
      if (typeof chart.datasetId !== "string" || chart.datasetId.length === 0) {
        findings.push(finding("$.chart.datasetId", "must name the shared dataset"));
      }
      if (chart.datasetKind !== "illustrative" && chart.datasetKind !== "observed") {
        findings.push(finding("$.chart.datasetKind", 'must be "illustrative" or "observed" (MG-015)'));
      }
      if (typeof chart.units !== "string" || chart.units.length === 0) {
        findings.push(finding("$.chart.units", "must state the dataset units"));
      }
      const domain = chart.domain;
      if (
        !Array.isArray(domain) ||
        domain.length !== 2 ||
        !isFiniteNumber(domain[0]) ||
        !isFiniteNumber(domain[1]) ||
        !(domain[0] < domain[1])
      ) {
        findings.push(finding("$.chart.domain", "must be [min, max] with min < max"));
      }
      if (chart.scaleType !== "linear" && chart.scaleType !== "log") {
        findings.push(finding("$.chart.scaleType", 'must be "linear" or "log"'));
      }
      if (
        !isRecord(chart.displayRounding) ||
        !isNonNegativeInt(chart.displayRounding.decimals)
      ) {
        findings.push(finding("$.chart.displayRounding", "must be { decimals: non-negative integer }"));
      }
      if (!Array.isArray(chart.rows) || chart.rows.length === 0) {
        findings.push(finding("$.chart.rows", "a chart content record carries at least one row"));
      } else {
        const seen = new Set<string>();
        chart.rows.forEach((row, i) => {
          const p = `$.chart.rows[${i}]`;
          if (!isRecord(row)) {
            findings.push(finding(p, "row must be an object { id, label, value }"));
            return;
          }
          if (typeof row.id !== "string" || row.id.length === 0) {
            findings.push(finding(p, "row.id must be a non-empty string"));
          } else if (seen.has(row.id)) {
            findings.push(finding(p, `duplicate row id "${row.id}"`));
          } else {
            seen.add(row.id);
          }
          if (typeof row.label !== "string" || row.label.length === 0) {
            findings.push(finding(p, "row.label must be a non-empty string"));
          }
          if (!isFiniteNumber(row.value)) {
            findings.push(finding(p, "row.value must be a finite number"));
          }
        });
      }
    }
  }
  if (doc.image !== undefined) {
    const image = doc.image;
    if (!isRecord(image)) {
      findings.push(finding("$.image", "must be an object"));
    } else {
      unknownKeys(image, IMAGE_KEYS, "$.image", findings);
      if (typeof image.assetId !== "string" || image.assetId.length === 0) {
        findings.push(finding("$.image.assetId", "must name the shared asset"));
      }
      if (
        image.usage !== "embed_original" &&
        image.usage !== "approved_derivative" &&
        image.usage !== "reference_only"
      ) {
        findings.push(finding("$.image.usage", "must be an MG-011 usage class"));
      }
      if (!isSize(image.source)) {
        findings.push(finding("$.image.source", "must be a positive integer size"));
      }
      const fp = image.focalPoint;
      if (
        fp !== null &&
        (!isRecord(fp) ||
          !isFiniteNumber(fp.x) ||
          !isFiniteNumber(fp.y) ||
          fp.x < 0 ||
          fp.x > 1 ||
          fp.y < 0 ||
          fp.y > 1)
      ) {
        findings.push(finding("$.image.focalPoint", "must be null or a normalized point in [0, 1]"));
      }
      if (!Array.isArray(image.protectedRegions)) {
        findings.push(finding("$.image.protectedRegions", "must be an array (possibly empty)"));
      } else {
        image.protectedRegions.forEach((region, i) => {
          const p = `$.image.protectedRegions[${i}]`;
          if (!isRecord(region) || typeof region.id !== "string" || region.id.length === 0) {
            findings.push(finding(p, "protected region must carry an id"));
            return;
          }
          const b = region.box;
          if (
            !isRecord(b) ||
            !isFiniteNumber(b.x) ||
            !isFiniteNumber(b.y) ||
            !isFiniteNumber(b.width) ||
            !isFiniteNumber(b.height) ||
            b.x < 0 ||
            b.y < 0 ||
            b.width <= 0 ||
            b.height <= 0 ||
            b.x + b.width > 1 ||
            b.y + b.height > 1
          ) {
            findings.push(finding(p, "protected region box must be a normalized box inside [0, 1]"));
          }
        });
      }
    }
  }
  // A record may be text-led (a typographic PowerPoint beat carries
  // neither chart nor image); completeness of what it does carry is
  // judged per variant in resolve.ts, not assumed here.
  if (findings.length > 0) throw new LayoutError(findings);
  return doc as unknown as SharedContentRecord;
}

function checkCopyRef(value: unknown, path: string, findings: LayoutFinding[]): void {
  if (!isRecord(value)) {
    findings.push(finding(path, "element copy must be a reference into the shared content"));
    return;
  }
  const keys = Object.keys(value);
  if (keys.length !== 1) {
    findings.push(finding(path, "a copy reference names exactly one source"));
    return;
  }
  if (keys[0] === "field") {
    if (!["headline", "support", "cta", "disclosure"].includes(value.field as string)) {
      findings.push(finding(path, 'field must be "headline", "support", "cta", or "disclosure"'));
    }
  } else if (keys[0] === "rowLabel" || keys[0] === "rowValue") {
    if (typeof value[keys[0]] !== "string" || (value[keys[0]] as string).length === 0) {
      findings.push(finding(path, `${keys[0]} must name a chart row id`));
    }
  } else {
    findings.push(finding(path, `unknown copy reference "${keys[0]}": elements never restate copy literally`));
  }
}

export function assertLayoutVariant(doc: unknown): LayoutVariant {
  const findings: LayoutFinding[] = [];
  if (!isRecord(doc)) {
    throw new LayoutError([finding("$", "a layout variant must be an object")]);
  }
  unknownKeys(doc, VARIANT_KEYS, "$", findings);
  if (doc.schema_version !== "1.0") {
    findings.push(finding("$.schema_version", 'must be "1.0"'));
  }
  if (typeof doc.id !== "string" || !LAYOUT_ID_PATTERN.test(doc.id)) {
    findings.push(finding("$.id", "must be an id matching the layout id pattern"));
  }
  if (typeof doc.contentId !== "string" || doc.contentId.length === 0) {
    findings.push(finding("$.contentId", "must name the shared content record this variant lays out"));
  }
  if (!DESTINATIONS.includes(doc.destination as DestinationId)) {
    findings.push(finding("$.destination", `must be one of ${DESTINATIONS.join(", ")}`));
  }
  if (!isSize(doc.canvas)) {
    findings.push(finding("$.canvas", "must be a positive integer size"));
  }
  const aspect = doc.exportAspect;
  if (!isRecord(aspect) || !isPositiveInt(aspect.w) || !isPositiveInt(aspect.h)) {
    findings.push(finding("$.exportAspect", "must be a reduced aspect { w, h } of positive integers"));
  }
  checkFontSpec(doc.font, "$.font", findings);
  if (typeof doc.safeAreaProfile !== "string" || doc.safeAreaProfile.length === 0) {
    findings.push(finding("$.safeAreaProfile", "must name a safe-area profile"));
  }
  if (doc.platformDelivery !== undefined && typeof doc.platformDelivery !== "boolean") {
    findings.push(finding("$.platformDelivery", "must be a boolean when present"));
  }
  if (doc.imageBox !== undefined && !isBox(doc.imageBox)) {
    findings.push(finding("$.imageBox", "must be an integer canvas box"));
  }
  if (doc.protectedAreas !== undefined) {
    if (!Array.isArray(doc.protectedAreas)) {
      findings.push(finding("$.protectedAreas", "must be an array when present"));
    } else {
      doc.protectedAreas.forEach((area, i) => {
        const p = `$.protectedAreas[${i}]`;
        if (!isRecord(area) || typeof area.id !== "string" || !isBox(area) || typeof area.reason !== "string") {
          findings.push(finding(p, "a protected area is { id, x, y, width, height, reason }"));
        }
      });
    }
  }
  if (doc.arrangement !== undefined) {
    const arr = doc.arrangement;
    if (!isRecord(arr)) {
      findings.push(finding("$.arrangement", "must be an object"));
    } else {
      if (!["rows", "columns", "staged_rows"].includes(arr.kind as string)) {
        findings.push(finding("$.arrangement.kind", 'must be "rows", "columns", or "staged_rows"'));
      }
      if (!isBox(arr.plot)) {
        findings.push(finding("$.arrangement.plot", "must be an integer canvas box"));
      }
      if (!isPositiveInt(arr.barThickness)) {
        findings.push(finding("$.arrangement.barThickness", "must be a positive integer"));
      }
      if (!Array.isArray(arr.slots) || arr.slots.length === 0) {
        findings.push(finding("$.arrangement.slots", "must name at least one slot"));
      } else {
        arr.slots.forEach((slot, i) => {
          const p = `$.arrangement.slots[${i}]`;
          if (!isRecord(slot) || typeof slot.rowId !== "string" || slot.rowId.length === 0) {
            findings.push(finding(p, "a slot names a chart row id"));
          } else if (slot.beatIndex !== undefined && !isNonNegativeInt(slot.beatIndex)) {
            findings.push(finding(p, "beatIndex must be a non-negative integer"));
          }
        });
      }
      if (arr.kind === "staged_rows") {
        if (!Array.isArray(arr.beats) || arr.beats.length === 0) {
          findings.push(finding("$.arrangement.beats", "a staged arrangement must declare its beats"));
        } else {
          arr.beats.forEach((beat, i) => {
            const p = `$.arrangement.beats[${i}]`;
            if (
              !isRecord(beat) ||
              !isNonNegativeInt(beat.index) ||
              !Array.isArray(beat.rowIds) ||
              beat.rowIds.length === 0
            ) {
              findings.push(finding(p, "a beat is { index, rowIds: non-empty array }"));
            }
          });
        }
      }
    }
  }
  if (!Array.isArray(doc.elements) || doc.elements.length === 0) {
    findings.push(finding("$.elements", "a variant carries at least one text element"));
  } else {
    const seen = new Set<string>();
    doc.elements.forEach((element, i) => {
      const p = `$.elements[${i}]`;
      if (!isRecord(element)) {
        findings.push(finding(p, "an element is an object"));
        return;
      }
      if (typeof element.id !== "string" || element.id.length === 0) {
        findings.push(finding(p, "element.id must be a non-empty string"));
      } else if (seen.has(element.id)) {
        findings.push(finding(p, `duplicate element id "${element.id}"`));
      } else {
        seen.add(element.id);
      }
      if (typeof element.role !== "string" || element.role.length === 0) {
        findings.push(finding(p, "element.role must name a typography role"));
      }
      checkCopyRef(element.ref, `${p}.ref`, findings);
      if (!isPositiveInt(element.sizePx)) {
        findings.push(finding(p, "element.sizePx must be a positive integer"));
      }
      if (!isBox(element.box)) {
        findings.push(finding(p, "element.box must be an integer canvas box"));
      }
      if (element.font !== undefined) checkFontSpec(element.font, `${p}.font`, findings);
    });
  }
  const placement = doc.placement;
  if (!isRecord(placement)) {
    findings.push(finding("$.placement", "a variant declares its delivery placement"));
  } else if (placement.kind === "full_frame") {
    // No further fields required.
  } else if (placement.kind === "inset") {
    const slide = placement.slide;
    if (!isRecord(slide)) {
      findings.push(finding("$.placement.slide", "an inset placement declares the slide it sits in"));
    } else {
      if (!isPositiveInt(slide.widthPx) || !isPositiveInt(slide.heightPx)) {
        findings.push(finding("$.placement.slide", "slide pixel size must be positive integers"));
      }
      if (!isFiniteNumber(slide.widthMm) || !(slide.widthMm > 0) || !isFiniteNumber(slide.heightMm) || !(slide.heightMm > 0)) {
        findings.push(finding("$.placement.slide", "slide millimetre size must be positive (placements are specified in real units)"));
      }
    }
    const hasPx = isRecord(placement.display);
    const hasMm = isRecord(placement.displayMm);
    if (!hasPx && !hasMm) {
      findings.push(finding("$.placement", "an inset placement declares its display size in pixels, millimetres, or both"));
    }
    if (hasPx) {
      const d = placement.display as Record<string, unknown>;
      if (!isPositiveInt(d.widthPx) || !isPositiveInt(d.heightPx)) {
        findings.push(finding("$.placement.display", "display pixel size must be positive integers"));
      }
    }
    if (hasMm) {
      const d = placement.displayMm as Record<string, unknown>;
      if (!isFiniteNumber(d.widthMm) || !(d.widthMm > 0) || !isFiniteNumber(d.heightMm) || !(d.heightMm > 0)) {
        findings.push(finding("$.placement.displayMm", "display millimetre size must be positive"));
      }
    }
  } else {
    findings.push(finding("$.placement.kind", 'must be "full_frame" or "inset"'));
  }
  if (findings.length > 0) throw new LayoutError(findings);
  return doc as unknown as LayoutVariant;
}

/** Resolve an element's copy from the shared content. Returns null
 * when the reference names content the record does not carry: an
 * acceptance finding in resolve.ts, not a parse error, because the
 * reference itself is well-formed. */
export function materializeCopy(
  content: SharedContentRecord,
  ref: CopyRef
): string | null {
  if ("field" in ref) {
    const value = content[ref.field];
    return typeof value === "string" ? value : null;
  }
  if (!content.chart) return null;
  if ("rowLabel" in ref) {
    return content.chart.rows.find((r) => r.id === ref.rowLabel)?.label ?? null;
  }
  const row = content.chart.rows.find((r) => r.id === ref.rowValue);
  if (!row) return null;
  return formatRowValue(content, row.value);
}

/** Format a row value under the dataset's declared rounding (MG-015
 * formatting, shared with every chart component). */
export function formatRowValue(content: SharedContentRecord, value: number): string {
  if (!content.chart) return String(value);
  return formatDatasetValue(toChartDataset(content), value);
}

/** Build the MG-015 dataset document the shared chart content names,
 * so scales and formatting come from the shipped chart layer, never
 * from a parallel implementation in this module. */
export function toChartDataset(content: SharedContentRecord): ChartDataset {
  const chart = content.chart;
  if (!chart) throw new Error("toChartDataset requires chart content");
  return {
    schema_version: "2.0",
    id: chart.datasetId,
    kind: chart.datasetKind,
    source_note: "Shared content record of the layout variant set (MG-014).",
    units: chart.units,
    domain: chart.domain,
    scale_type: chart.scaleType,
    missing_value_policy: "error",
    display_rounding: chart.displayRounding,
    rows: chart.rows.map((r) => ({ id: r.id, label: r.label, value: r.value })),
  };
}

/** The value-axis pixel extent of an arrangement: the plot width for
 * row arrangements, the plot height for columns. */
export function valueAxisExtent(arrangement: ChartArrangement): number {
  return arrangement.kind === "columns"
    ? arrangement.plot.height
    : arrangement.plot.width;
}

/** The value-axis scale facts for one chart variant: domain, extent,
 * pixels per unit, and the normalized position of every row value.
 * Normalized positions are the comparability currency: two variants
 * are comparable when the same value lands at the same fraction of
 * the plot extent under the same domain (MG-015). */
export interface ChartScaleFacts {
  domain: [number, number];
  extentPx: number;
  pixelsPerUnit: number;
  normalizedPositions: Array<{ rowId: string; value: number; normalized: number }>;
}

export function chartScaleFacts(
  content: SharedContentRecord,
  arrangement: ChartArrangement
): ChartScaleFacts {
  const chart = content.chart;
  if (!chart) throw new Error("chartScaleFacts requires chart content");
  const extent = valueAxisExtent(arrangement);
  const scale = createDatasetScale(toChartDataset(content), [0, extent]);
  const span = chart.domain[1] - chart.domain[0];
  return {
    domain: [...chart.domain],
    extentPx: extent,
    pixelsPerUnit: extent / span,
    normalizedPositions: chart.rows.map((row) => ({
      rowId: row.id,
      value: row.value,
      normalized: scale.map(row.value) / extent,
    })),
  };
}

export { LAYOUT_CONTRACT_CATEGORY };
