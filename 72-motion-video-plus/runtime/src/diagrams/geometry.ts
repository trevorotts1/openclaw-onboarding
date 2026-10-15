// Deterministic path geometry for diagrams (Directive MG-017).
//
// Every path is a polyline of exact points. Lengths are Euclidean sums,
// point-at-arc-length walks the segments linearly, and a path's final
// point is BY CONSTRUCTION the target node's entry anchor, so path
// termination exactness is a property of the construction, and the
// tests still measure it (tolerance 1e-6 source px, for float hygiene
// only). No timers, no randomness, no easing libraries: the same inputs
// produce the same points on every run and every seek.

export interface Point {
  x: number;
  y: number;
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function distance(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/** Total Euclidean length of a polyline. */
export function polylineLength(points: Point[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += distance(points[i - 1], points[i]);
  }
  return total;
}

/** Cumulative arc length at each point of a polyline. */
export function cumulativeLengths(points: Point[]): number[] {
  const out: number[] = [0];
  for (let i = 1; i < points.length; i += 1) {
    out.push(out[i - 1] + distance(points[i - 1], points[i]));
  }
  return out;
}

/**
 * The point at arc length `arc` along a polyline, clamped to the ends.
 * Linear within each segment: position is a deterministic function of
 * arc length, and arc length is a deterministic function of frame.
 */
export function pointAtArc(points: Point[], cumulative: number[], arc: number): Point {
  if (points.length === 0) return { x: 0, y: 0 };
  const total = cumulative[cumulative.length - 1];
  const clamped = Math.min(Math.max(arc, 0), total);
  let seg = 1;
  while (seg < cumulative.length - 1 && cumulative[seg] < clamped) seg += 1;
  const segStart = cumulative[seg - 1];
  const segLength = cumulative[seg] - segStart;
  const t = segLength === 0 ? 0 : (clamped - segStart) / segLength;
  const a = points[seg - 1];
  const b = points[seg];
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

/**
 * The sub-polyline covering the first `arc` length units of a path:
 * what "connection drawing progresses along the path" means concretely.
 * A partially drawn edge is a shorter path, never a faded whole path.
 */
export function subPolyline(points: Point[], cumulative: number[], arc: number): Point[] {
  if (points.length === 0) return [];
  const total = cumulative[cumulative.length - 1];
  const clamped = Math.min(Math.max(arc, 0), total);
  const out: Point[] = [points[0]];
  for (let i = 1; i < points.length; i += 1) {
    if (cumulative[i] <= clamped) {
      out.push(points[i]);
    } else {
      out.push(pointAtArc(points, cumulative, clamped));
      return out;
    }
  }
  return out;
}

/** Axis-aligned box overlap test, with an optional required gap. */
export function boxesOverlap(a: Box, b: Box, gap = 0): boolean {
  return (
    a.x - gap < b.x + b.width &&
    b.x - gap < a.x + a.width &&
    a.y - gap < b.y + b.height &&
    b.y - gap < a.y + a.height
  );
}

export function boxCenter(box: Box): Point {
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}
