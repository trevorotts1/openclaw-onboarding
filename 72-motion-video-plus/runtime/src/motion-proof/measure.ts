// Raster measurement for motion proof (Directive MG-032). Every
// measurement here is restricted to a declared subject region: whole-
// frame pixel change is never evidence, because decorative activity
// around a static subject produces plenty of it. The color-match rule
// (per-channel absolute difference sum within a tolerance) follows the
// established decoded-frame practice of MG-006 and MG-017, which
// absorbs the single antialiased edge pixel and H.264 noise.

import type { SourceBox } from "./types";

/** Per-channel absolute difference sum that counts as a color match.
 * The same constant the MG-006 bar measurement and the MG-017 subject
 * centroid use. */
export const COLOR_MATCH_TOLERANCE_SUM = 66;

export function hexToRgb(hex: string): [number, number, number] {
  const m = /^#([0-9a-fA-F]{6})$/.exec(hex);
  if (!m) throw new Error(`not a #RRGGBB color: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function matches(
  rgb: Buffer,
  offset: number,
  target: [number, number, number],
  toleranceSum: number
): boolean {
  return (
    Math.abs(rgb[offset] - target[0]) +
      Math.abs(rgb[offset + 1] - target[1]) +
      Math.abs(rgb[offset + 2] - target[2]) <=
    toleranceSum
  );
}

/**
 * Measure one bar's extent inside its subject region: scan the
 * region's vertical center line from the region's left edge and count
 * the contiguous run of pixels matching the subject color. The scan
 * never leaves the region, so a same-colored decoration elsewhere in
 * the frame cannot inflate the measurement.
 */
export function measureBarWidthInRegion(
  rgb: Buffer,
  frameWidth: number,
  region: SourceBox,
  colorHex: string,
  toleranceSum: number = COLOR_MATCH_TOLERANCE_SUM
): number {
  const target = hexToRgb(colorHex);
  const y = Math.round(region.y + region.height / 2);
  let run = 0;
  const xStart = Math.round(region.x);
  const xEnd = Math.round(region.x + region.width);
  for (let x = xStart; x < xEnd; x += 1) {
    const offset = (y * frameWidth + x) * 3;
    if (matches(rgb, offset, target, toleranceSum)) run += 1;
    else break;
  }
  return run;
}

/**
 * Centroid of the subject-colored pixels inside a square window
 * around an expected position. Returns null when no pixel matches.
 * The window is the subject restriction: accent material elsewhere in
 * the frame (labels of other stages, decorations) is excluded.
 */
export function accentCentroidInWindow(
  rgb: Buffer,
  frameWidth: number,
  frameHeight: number,
  center: { x: number; y: number },
  radius: number,
  colorHex: string,
  toleranceSum: number = COLOR_MATCH_TOLERANCE_SUM
): { x: number; y: number; pixels: number } | null {
  const target = hexToRgb(colorHex);
  const x0 = Math.max(0, Math.floor(center.x - radius));
  const x1 = Math.min(frameWidth - 1, Math.ceil(center.x + radius));
  const y0 = Math.max(0, Math.floor(center.y - radius));
  const y1 = Math.min(frameHeight - 1, Math.ceil(center.y + radius));
  let sumX = 0;
  let sumY = 0;
  let count = 0;
  for (let y = y0; y <= y1; y += 1) {
    for (let x = x0; x <= x1; x += 1) {
      const offset = (y * frameWidth + x) * 3;
      if (matches(rgb, offset, target, toleranceSum)) {
        sumX += x;
        sumY += y;
        count += 1;
      }
    }
  }
  if (count === 0) return null;
  return { x: sumX / count, y: sumY / count, pixels: count };
}

/** Count subject-colored pixels inside a box (occlusion evidence:
 * how much of the subject remains visible inside its region). */
export function accentCountInBox(
  rgb: Buffer,
  frameWidth: number,
  box: SourceBox,
  colorHex: string,
  toleranceSum: number = COLOR_MATCH_TOLERANCE_SUM
): number {
  const target = hexToRgb(colorHex);
  const x0 = Math.max(0, Math.round(box.x));
  const x1 = Math.round(box.x + box.width);
  const y0 = Math.max(0, Math.round(box.y));
  const y1 = Math.round(box.y + box.height);
  let count = 0;
  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const offset = (y * frameWidth + x) * 3;
      if (matches(rgb, offset, target, toleranceSum)) count += 1;
    }
  }
  return count;
}

/**
 * Mean absolute per-channel difference between two decoded frames,
 * computed over the pixels OUTSIDE every subject region. This is the
 * decoration control: it quantifies how much the frame changed where
 * the subject is not, so a report can show decorative motion and a
 * static subject side by side.
 */
export function meanAbsDiffOutsideRegions(
  a: Buffer,
  b: Buffer,
  frameWidth: number,
  frameHeight: number,
  regions: SourceBox[]
): number {
  const inside = (x: number, y: number): boolean =>
    regions.some(
      (r) => x >= r.x && x < r.x + r.width && y >= r.y && y < r.y + r.height
    );
  let sum = 0;
  let pixels = 0;
  for (let y = 0; y < frameHeight; y += 1) {
    for (let x = 0; x < frameWidth; x += 1) {
      if (inside(x, y)) continue;
      const offset = (y * frameWidth + x) * 3;
      sum +=
        Math.abs(a[offset] - b[offset]) +
        Math.abs(a[offset + 1] - b[offset + 1]) +
        Math.abs(a[offset + 2] - b[offset + 2]);
      pixels += 1;
    }
  }
  if (pixels === 0) return 0;
  return sum / pixels / 3;
}
