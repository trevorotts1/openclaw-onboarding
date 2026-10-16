// The rendered-layout audit (Directive MG-013, test T07).
//
// A layout record declares a canvas, a default font request, protected
// areas, and text elements with role, copy, size, box, and placement. An
// element may override the font (a real layout mixes weights). The audit
// measures every element with the actual font binary it names and judges
// the size the viewer will actually see:
//
//   full_frame / recomposed  the authored size on the destination canvas.
//   inset                    authored size scaled by destination width over
//                            source canvas width. The role floor never
//                            scales down to meet the placement.
//
// Findings are structured and named; measurements travel with them so a
// reviewer sees numbers, not just a verdict.

import { existsSync } from "node:fs";
import {
  TypographyError,
  layoutText,
  loadFontFile,
  measureString,
  type ParsedFont,
} from "./font-metrics";
import type { TypographyTokens } from "./tokens";

export interface LayoutBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type Placement =
  | { kind: "full_frame" }
  | { kind: "recomposed" }
  | { kind: "inset"; destinationWidth: number; destinationHeight: number };

export interface FontSpec {
  family: string;
  weight: number;
  file: string;
}

export interface LayoutElement {
  id: string;
  role: string;
  copy: string;
  sizePx: number;
  box: LayoutBox;
  placement: Placement;
  /** Overrides the record's default font for this element. */
  font?: FontSpec;
}

export interface ProtectedArea extends LayoutBox {
  id: string;
  reason: string;
}

export interface LayoutRecord {
  id: string;
  canvas: { width: number; height: number };
  font: FontSpec;
  protectedAreas: ProtectedArea[];
  elements: LayoutElement[];
}

export interface TypeFinding {
  elementId: string | null;
  kind: string;
  severity: "error" | "warning";
  message: string;
  measured?: Record<string, number | string>;
}

export interface ElementMeasurement {
  elementId: string;
  role: string;
  declaredSizePx: number;
  effectiveSizePx: number;
  placementScale: number;
  lineCount: number;
  widestLinePx: number;
  totalHeightPx: number;
  capHeightPx: number | null;
  capHeightRatio: number | null;
}

export interface FontInfo {
  path: string;
  sha256: string;
  familyName: string;
  weightClass: number | null;
  unitsPerEm: number;
  capHeightRatio: number | null;
}

export interface AuditResult {
  layoutId: string;
  /** Info for the record's default font, when it resolved and matched. */
  font: FontInfo | null;
  measurements: ElementMeasurement[];
  findings: TypeFinding[];
  /** True when no error-severity finding exists. */
  pass: boolean;
}

const EPS = 0.5;
/** Cap-height ratio below which the reviewer should demand a larger size. */
export const LOW_CAP_HEIGHT_RATIO = 0.6;

function normalizeFamily(name: string): string {
  return name.trim().replace(/\s+/g, " ").toLowerCase();
}

function boxesIntersect(a: LayoutBox, b: LayoutBox): boolean {
  return (
    a.x < b.x + b.width &&
    b.x < a.x + a.width &&
    a.y < b.y + b.height &&
    b.y < a.y + a.height
  );
}

export function placementScale(
  element: LayoutElement,
  canvasWidth: number
): number {
  if (element.placement.kind === "inset") {
    return element.placement.destinationWidth / canvasWidth;
  }
  return 1;
}

function fontInfoOf(font: ParsedFont): FontInfo {
  return {
    path: font.path,
    sha256: font.sha256,
    familyName: font.familyName,
    weightClass: font.weightClass,
    unitsPerEm: font.unitsPerEm,
    capHeightRatio:
      font.capHeightUnits === null
        ? null
        : font.capHeightUnits / font.unitsPerEm,
  };
}

export function auditLayout(
  record: LayoutRecord,
  tokens: TypographyTokens
): AuditResult {
  const findings: TypeFinding[] = [];
  const measurements: ElementMeasurement[] = [];
  const cache = new Map<string, ParsedFont | null>();
  const capWarned = new Set<string>();

  // The font gate: the requested family and weight must be what renders.
  // A bad spec is reported once, against the first element that names it
  // (or the record, for the default font), and measurement with that spec
  // is refused rather than performed with the wrong font.
  const resolveFont = (
    spec: FontSpec,
    elementId: string | null
  ): ParsedFont | null => {
    const key = `${spec.file}|${spec.family}|${spec.weight}`;
    if (cache.has(key)) return cache.get(key) ?? null;
    let font: ParsedFont | null = null;
    if (!existsSync(spec.file)) {
      findings.push({
        elementId,
        kind: "TYPO_FONT_MISSING",
        severity: "error",
        message:
          `Font file not found: ${spec.file}. The job names this exact font; ` +
          `substitution is forbidden, so elements using it cannot be measured.`,
      });
    } else {
      try {
        font = loadFontFile(spec.file);
      } catch (err) {
        findings.push({
          elementId,
          kind: err instanceof TypographyError ? err.kind : "TYPO_FONT_PARSE",
          severity: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    }
    if (font) {
      if (normalizeFamily(font.familyName) !== normalizeFamily(spec.family)) {
        findings.push({
          elementId,
          kind: "TYPO_FONT_SUBSTITUTED",
          severity: "error",
          message:
            `Font file ${spec.file} is family "${font.familyName}" but the layout ` +
            `requests "${spec.family}". That is substitution; measurement is ` +
            `refused rather than performed with the wrong font.`,
        });
        font = null;
      } else if (font.weightClass !== null && font.weightClass !== spec.weight) {
        findings.push({
          elementId,
          kind: "TYPO_FONT_SUBSTITUTED",
          severity: "error",
          message:
            `Font file ${spec.file} has weight class ${font.weightClass} but the ` +
            `layout requests weight ${spec.weight}. The requested weight must be ` +
            `the weight that renders.`,
        });
        font = null;
      }
    }
    if (font) {
      const ratio = fontInfoOf(font).capHeightRatio;
      if (
        ratio !== null &&
        ratio < LOW_CAP_HEIGHT_RATIO &&
        !capWarned.has(font.path)
      ) {
        capWarned.add(font.path);
        findings.push({
          elementId: null,
          kind: "TYPO_LOW_CAP_HEIGHT",
          severity: "warning",
          message:
            `Font "${font.familyName}" has a cap-height ratio of ${ratio.toFixed(3)}; ` +
            `at the same nominal size its capitals read smaller than the reference ` +
            `fonts. The reviewer may demand larger sizes.`,
        });
      }
    }
    cache.set(key, font);
    return font;
  };

  const defaultFont = resolveFont(record.font, null);
  const defaultInfo = defaultFont ? fontInfoOf(defaultFont) : null;

  for (const element of record.elements) {
    const role = tokens.role(element.role);
    if (!role) {
      findings.push({
        elementId: element.id,
        kind: "TYPO_UNKNOWN_ROLE",
        severity: "error",
        message: `Element "${element.id}" declares role "${element.role}", which is not in the typography tokens. Every text element carries a known role.`,
      });
      continue;
    }
    const scale = placementScale(element, record.canvas.width);
    const effectiveSize = element.sizePx * scale;

    if (effectiveSize < role.floorPx - EPS) {
      findings.push({
        elementId: element.id,
        kind: "TYPO_BELOW_FLOOR",
        severity: "error",
        message:
          `Element "${element.id}" (${element.role}) renders at an effective ` +
          `${round2(effectiveSize)} px, below the role floor of ${role.floorPx} px` +
          (scale !== 1
            ? ` (authored ${element.sizePx} px at placement scale ${round2(scale)})`
            : "") +
          `. Sizes are judged at the destination, not at the source.`,
        measured: {
          effectiveSizePx: round2(effectiveSize),
          floorPx: role.floorPx,
          declaredSizePx: element.sizePx,
          placementScale: round2(scale),
        },
      });
    }
    if (effectiveSize > role.maxPx + EPS) {
      findings.push({
        elementId: element.id,
        kind: "TYPO_ABOVE_RANGE",
        severity: "warning",
        message:
          `Element "${element.id}" (${element.role}) renders at an effective ` +
          `${round2(effectiveSize)} px, above the role range maximum of ` +
          `${role.maxPx} px. A warning, not a failure: the reviewer decides.`,
        measured: { effectiveSizePx: round2(effectiveSize), maxPx: role.maxPx },
      });
    }

    for (const area of record.protectedAreas) {
      if (boxesIntersect(element.box, area)) {
        findings.push({
          elementId: element.id,
          kind: "TYPO_PROTECTED_CONFLICT",
          severity: "error",
          message:
            `Element "${element.id}" box intersects protected area "${area.id}" ` +
            `(${area.reason}). Text stays clear of protected content.`,
        });
      }
    }

    const font = resolveFont(element.font ?? record.font, element.id);
    if (!font) continue;
    const layout = layoutText(font, element.copy, element.sizePx, element.box.width);
    const m = measureString(font, element.copy, element.sizePx);
    measurements.push({
      elementId: element.id,
      role: element.role,
      declaredSizePx: element.sizePx,
      effectiveSizePx: round2(effectiveSize),
      placementScale: round2(scale),
      lineCount: layout.lines.length,
      widestLinePx: round2(layout.widestLinePx),
      totalHeightPx: round2(layout.totalHeightPx),
      capHeightPx: m.capHeightPx === null ? null : round2(m.capHeightPx),
      capHeightRatio: m.capHeightRatio === null ? null : round4(m.capHeightRatio),
    });
    const clippedLine = layout.lines.find(
      (l) => l.widthPx > element.box.width + EPS
    );
    if (clippedLine) {
      findings.push({
        elementId: element.id,
        kind: "TYPO_CLIPPING",
        severity: "error",
        message:
          `Element "${element.id}" has a line ${round2(clippedLine.widthPx)} px wide ` +
          `in a box ${element.box.width} px wide` +
          (clippedLine.unbreakableWord
            ? ` (single unbreakable word "${clippedLine.unbreakableWord}")`
            : "") +
          `. The text is clipped at its declared size.`,
        measured: {
          widestLinePx: round2(clippedLine.widthPx),
          boxWidthPx: element.box.width,
        },
      });
    } else if (layout.totalHeightPx > element.box.height + EPS) {
      findings.push({
        elementId: element.id,
        kind: "TYPO_CLIPPING",
        severity: "error",
        message:
          `Element "${element.id}" wraps to ${layout.lines.length} lines needing ` +
          `${round2(layout.totalHeightPx)} px of height in a box ${element.box.height} px ` +
          `tall. The text overflows its box at its declared size.`,
        measured: {
          totalHeightPx: round2(layout.totalHeightPx),
          boxHeightPx: element.box.height,
          lineCount: layout.lines.length,
        },
      });
    }
    if (layout.missingCodepoints.length > 0) {
      findings.push({
        elementId: element.id,
        kind: "TYPO_MISSING_GLYPH",
        severity: "error",
        message:
          `Element "${element.id}" contains codepoints the font "${font.familyName}" ` +
          `has no glyph for: ${layout.missingCodepoints
            .map((cp) => `U+${cp.toString(16).toUpperCase()}`)
            .join(", ")}. They would render as .notdef boxes.`,
      });
    }
  }

  return {
    layoutId: record.id,
    font: defaultInfo,
    measurements,
    findings,
    pass: findings.every((f) => f.severity !== "error"),
  };
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}
