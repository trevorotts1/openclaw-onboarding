// The fit/overflow decider (Directive MG-013).
//
// Given copy, a role, a box, and the actual font, decide exactly one of:
//   fits                the copy fits inside the role band; the returned
//                       size is always >= the role floor.
//   below_floor         the copy would fit only under the role floor.
//                       This is a failure report carrying the would-fit size
//                       as evidence. It is not a size anyone may use.
//   restructure_required  no size saves the copy; the decider names the
//                       viable path: split (the copy at floor size fits in
//                       two sequential boxes or beats) or shorten.
//
// The result type has no field that could carry a below-floor size as a
// solution, so "solve overflow by shrinking" is structurally impossible
// for a caller of this module.

import {
  layoutText,
  measureString,
  type ParsedFont,
  type TextLayout,
} from "./font-metrics";
import type { RoleToken } from "./tokens";

export interface FitBox {
  widthPx: number;
  heightPx: number;
}

export interface FitRequest {
  copy: string;
  role: RoleToken;
  box: FitBox;
  font: ParsedFont;
  /** Author's intended size. Defaults to the role maximum. Clamped into the band. */
  requestedSizePx?: number;
}

export type FitResult =
  | {
      outcome: "fits";
      sizePx: number;
      lineCount: number;
      lines: Array<{ text: string; widthPx: number }>;
      widestLinePx: number;
      totalHeightPx: number;
      capHeightPx: number | null;
    }
  | {
      outcome: "below_floor";
      floorPx: number;
      /** Evidence only: the largest size under the floor at which the copy would fit. */
      wouldFitSizePx: number;
      reason: string;
    }
  | {
      outcome: "restructure_required";
      floorPx: number;
      viablePath: "split" | "shorten";
      reason: string;
      /** Lines the copy needs at floor size, for the restructure conversation. */
      linesAtFloor: number;
    };

const EPS = 0.5;

/**
 * How far under the floor a near miss may reach and still be reported as
 * below_floor rather than restructure_required: a shrink of at most one
 * quarter. A copy that only fits after a deeper shrink is not a near miss;
 * it is different copy or a different box, and the restructure path decides.
 */
export const BELOW_FLOOR_NEAR_MISS_RATIO = 0.75;

function fitsAt(
  font: ParsedFont,
  copy: string,
  sizePx: number,
  box: FitBox
): TextLayout | null {
  const layout = layoutText(font, copy, sizePx, box.widthPx);
  const widthOk = layout.lines.every(
    (l) => l.unbreakableWord === null && l.widthPx <= box.widthPx + EPS
  );
  const heightOk = layout.totalHeightPx <= box.heightPx + EPS;
  return widthOk && heightOk ? layout : null;
}

export function decideFit(request: FitRequest): FitResult {
  const { copy, role, box, font } = request;
  const floor = role.floorPx;
  const start = Math.min(
    Math.max(request.requestedSizePx ?? role.maxPx, floor),
    role.maxPx
  );

  // 1. Search the legal band, largest size first.
  for (let size = Math.floor(start); size >= floor; size -= 1) {
    const layout = fitsAt(font, copy, size, box);
    if (layout) {
      const capHeightPx =
        font.capHeightUnits === null
          ? null
          : font.capHeightUnits * (size / font.unitsPerEm);
      return {
        outcome: "fits",
        sizePx: size,
        lineCount: layout.lines.length,
        lines: layout.lines.map((l) => ({ text: l.text, widthPx: l.widthPx })),
        widestLinePx: layout.widestLinePx,
        totalHeightPx: layout.totalHeightPx,
        capHeightPx,
      };
    }
  }

  const atFloor = layoutText(font, copy, floor, box.widthPx);
  const linesAtFloor = atFloor.lines.length;

  // 2. The classic temptation case: one line that almost fits. The copy is
  //    a single logical line, too wide for the box at floor size, but at
  //    some size inside the near-miss band under the floor it sits on
  //    exactly one line and fits. Name that honestly as below_floor
  //    instead of letting anyone ship the shrink. Copy that needs several
  //    lines at every near-miss size is not a near miss; step 3 decides it.
  const singleLogicalLine = !copy.includes("\n");
  const unwrapped = copy.split(/\s+/).filter((w) => w.length > 0).join(" ");
  const singleLineWidthAtFloor = measureString(font, unwrapped, floor).widthPx;
  if (singleLogicalLine && singleLineWidthAtFloor > box.widthPx + EPS) {
    const nearMissLow = Math.ceil(floor * BELOW_FLOOR_NEAR_MISS_RATIO);
    for (let size = floor - 1; size >= nearMissLow; size -= 1) {
      const layout = fitsAt(font, copy, size, box);
      if (layout && layout.lines.length === 1) {
        return {
          outcome: "below_floor",
          floorPx: floor,
          wouldFitSizePx: size,
          reason:
            `Copy fits the box only at ${size} px, below the ${role.role} floor of ` +
            `${floor} px. Shrinking to fit is forbidden; shorten or split the copy, ` +
            `or give the role a larger box.`,
        };
      }
    }
  }

  // 3. No size saves it. Split when two sequential boxes or beats at floor
  //    size can hold the copy; shorten otherwise.
  const unbreakable = atFloor.lines.some((l) => l.unbreakableWord !== null);
  const fitsInTwoBoxes =
    !unbreakable && atFloor.totalHeightPx <= 2 * box.heightPx + EPS;
  if (fitsInTwoBoxes) {
    return {
      outcome: "restructure_required",
      floorPx: floor,
      viablePath: "split",
      reason:
        `At the ${role.role} floor of ${floor} px the copy needs ${linesAtFloor} lines ` +
        `(${Math.round(atFloor.totalHeightPx)} px), more than this box holds but no more ` +
        `than two sequential boxes or beats. Split it; do not shrink it.`,
      linesAtFloor,
    };
  }
  return {
    outcome: "restructure_required",
    floorPx: floor,
    viablePath: "shorten",
    reason: unbreakable
      ? `At the ${role.role} floor of ${floor} px a single unbreakable word is wider ` +
        `than the box (${Math.round(atFloor.widestLinePx)} px against ${box.widthPx} px). ` +
        `Splitting cannot fix a word that does not fit; shorten the copy.`
      : `At the ${role.role} floor of ${floor} px the copy needs ${linesAtFloor} lines ` +
        `(${Math.round(atFloor.totalHeightPx)} px), more than two sequential boxes or ` +
        `beats can hold. Shorten the copy.`,
    linesAtFloor,
  };
}
