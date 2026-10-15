// Category band layout (Directive MG-015, MG-016 foundation).
//
// Charts lay categories out in equal bands along one axis: the extent
// is divided into `count` equal steps, and each band's mark occupies
// the middle (1 - paddingRatio) of its step. Pure deterministic
// arithmetic, identical for instrumented checks and rendered output.

export interface BandLayout {
  readonly count: number;
  readonly extent: number;
  readonly paddingRatio: number;
  /** Distance between the starts of adjacent bands. */
  readonly step: number;
  /** Mark thickness inside each band. */
  readonly thickness: number;
  /** Start offset of band i (mark edge, padding included). */
  offset(index: number): number;
  /** Center of band i. */
  center(index: number): number;
}

/**
 * Lay out `count` category bands over `extent` plot units.
 * paddingRatio is the fraction of each step left as gap, split evenly
 * on both sides of the mark; 0 means marks touch, and it must stay
 * below 1 so every mark has positive thickness.
 */
export function bandLayout(count: number, extent: number, paddingRatio = 0.25): BandLayout {
  if (!Number.isInteger(count) || count < 1) {
    throw new Error(`band count must be a positive integer, got ${count}`);
  }
  if (!Number.isFinite(extent) || !(extent > 0)) {
    throw new Error(`band extent must be a positive finite number, got ${extent}`);
  }
  if (!Number.isFinite(paddingRatio) || paddingRatio < 0 || paddingRatio >= 1) {
    throw new Error(`band padding ratio must lie in [0, 1), got ${paddingRatio}`);
  }
  const step = extent / count;
  const thickness = step * (1 - paddingRatio);
  const inset = (step - thickness) / 2;
  const checkIndex = (index: number): void => {
    if (!Number.isInteger(index) || index < 0 || index >= count) {
      throw new Error(`band index ${index} outside [0, ${count})`);
    }
  };
  return {
    count,
    extent,
    paddingRatio,
    step,
    thickness,
    offset: (index: number): number => {
      checkIndex(index);
      return index * step + inset;
    },
    center: (index: number): number => {
      checkIndex(index);
      return index * step + step / 2;
    },
  };
}
