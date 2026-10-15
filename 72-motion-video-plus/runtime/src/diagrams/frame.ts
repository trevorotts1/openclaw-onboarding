// Resolved diagram geometry plus the pure frame functions
// (Directive MG-017).
//
// A ResolvedDiagram is plain serializable data: node boxes, edge
// polylines, the subject path with its timing keyframes, and per-node
// activation frames. Every visual state of the scene is a pure function
// of (resolved diagram, frame): the same frame always yields the same
// position, drawn length, and activation, in the test harness, in the
// Remotion composition, and on any seek. That determinism is what makes
// subject persistence and causality checkable rather than impressionistic.

import type { Box, Point } from "./geometry";
import { pointAtArc, subPolyline } from "./geometry";
import type {
  DiagramCanvas,
  DiagramNodeKind,
  DiagramPattern,
  DiagramRelief,
  DiagramTiming,
} from "./model";

export interface ResolvedNode {
  id: string;
  label: string;
  kind: DiagramNodeKind;
  pair_id: string | null;
  state_role: "before" | "after" | null;
  /** The node's box at base layout (before any relief widening). */
  box: Box;
  /** The measured label's own box, centered inside the node box. */
  labelBox: Box;
  center: Point;
  entryAnchor: Point;
  exitAnchor: Point;
  /** Arc position of this node's center along the subject path, for
   * path nodes; null for nodes the subject never visits. */
  centerArc: number | null;
  /** First frame at which the node is active (subject arrived, or its
   * incoming edge finished drawing). Null only for a node that never
   * activates, which structural validation forbids. */
  activationFrame: number | null;
}

export interface ResolvedEdge {
  id: string;
  source: string;
  target: string;
  kind: "flow" | "branch" | "transform";
  label: string | null;
  points: Point[];
  cumulative: number[];
  length: number;
  isPathEdge: boolean;
  /** Arc range this edge covers on the subject path (path edges only). */
  pathArcFrom: number | null;
  pathArcTo: number | null;
  /** Draw window in frames (non-path edges; path edges derive their
   * progress from the subject arc instead). */
  drawStartFrame: number;
  drawEndFrame: number;
}

export interface SubjectPart {
  type: "node" | "edge";
  id: string;
  /** Arc range [from, to) this part covers on the subject path. */
  from: number;
  to: number;
}

export interface ResolvedSubject {
  id: string;
  label: string;
  points: Point[];
  cumulative: number[];
  totalLength: number;
  parts: SubjectPart[];
  /** (frame, arc) keyframes: subject arc position is piecewise linear
   * in frame through these points, clamped outside the motion window. */
  keyframes: { frame: number; arc: number }[];
  /** Arc at which a before/after subject changes state; null for other
   * patterns. */
  stateFlipArc: number | null;
}

export interface ResolvedDiagram {
  pattern: DiagramPattern;
  orientation: "landscape" | "portrait";
  canvas: DiagramCanvas;
  timing: DiagramTiming;
  nodes: ResolvedNode[];
  edges: ResolvedEdge[];
  subject: ResolvedSubject | null;
  relief: (DiagramRelief & { widenFrames: number }) | null;
}

export function nodeById(resolved: ResolvedDiagram, id: string): ResolvedNode {
  const node = resolved.nodes.find((candidate) => candidate.id === id);
  if (!node) throw new Error(`resolved diagram has no node "${id}"`);
  return node;
}

export function edgeById(resolved: ResolvedDiagram, id: string): ResolvedEdge {
  const edge = resolved.edges.find((candidate) => candidate.id === id);
  if (!edge) throw new Error(`resolved diagram has no edge "${id}"`);
  return edge;
}

function clamp01(value: number): number {
  return Math.min(Math.max(value, 0), 1);
}

/** Subject arc position at a frame: piecewise linear through the
 * keyframes, clamped to [0, totalLength] outside the motion window. */
export function subjectArcAt(resolved: ResolvedDiagram, frame: number): number {
  const subject = resolved.subject;
  if (!subject) return 0;
  const keys = subject.keyframes;
  if (frame <= keys[0].frame) return keys[0].arc;
  for (let i = 1; i < keys.length; i += 1) {
    if (frame <= keys[i].frame) {
      const a = keys[i - 1];
      const b = keys[i];
      const span = b.frame - a.frame;
      const t = span === 0 ? 1 : (frame - a.frame) / span;
      return a.arc + (b.arc - a.arc) * t;
    }
  }
  return keys[keys.length - 1].arc;
}

/** The subject's position at a frame: a deterministic function of the
 * frame alone. The subject id never changes; only its position (and,
 * for before/after, its declared state) does. */
export function subjectPositionAt(resolved: ResolvedDiagram, frame: number): Point | null {
  const subject = resolved.subject;
  if (!subject) return null;
  return pointAtArc(subject.points, subject.cumulative, subjectArcAt(resolved, frame));
}

/** Before/after subject state at a frame: "before" while the subject
 * is on the near side of its transform midpoint, "after" beyond it. */
export function subjectStateAt(
  resolved: ResolvedDiagram,
  frame: number
): "before" | "after" | null {
  const subject = resolved.subject;
  if (!subject || subject.stateFlipArc === null) return null;
  return subjectArcAt(resolved, frame) < subject.stateFlipArc ? "before" : "after";
}

/**
 * How much of an edge is drawn at a frame, as a fraction of its length.
 * Path edges draw exactly as the subject traverses them (the drawn tip
 * is the subject's position projected on the edge); other edges draw
 * over their declared frame window after their source activates.
 * Drawing is progress along the path, never a whole-edge fade.
 */
export function edgeDrawProgressAt(resolved: ResolvedDiagram, edge: ResolvedEdge, frame: number): number {
  if (edge.isPathEdge && edge.pathArcFrom !== null && edge.pathArcTo !== null) {
    const arc = subjectArcAt(resolved, frame);
    const span = edge.pathArcTo - edge.pathArcFrom;
    if (span <= 0) return arc >= edge.pathArcTo ? 1 : 0;
    return clamp01((arc - edge.pathArcFrom) / span);
  }
  const span = edge.drawEndFrame - edge.drawStartFrame;
  if (span <= 0) return frame >= edge.drawEndFrame ? 1 : 0;
  return clamp01((frame - edge.drawStartFrame) / span);
}

/** The points of an edge as drawn at a frame: a prefix of its polyline
 * whose length is progress times the edge length. */
export function edgeDrawnPoints(resolved: ResolvedDiagram, edge: ResolvedEdge, frame: number): Point[] {
  const progress = edgeDrawProgressAt(resolved, edge, frame);
  return subPolyline(edge.points, edge.cumulative, progress * edge.length);
}

/** The arc position projected on a path edge at a frame (path edges). */
export function edgeDrawnLengthAt(resolved: ResolvedDiagram, edge: ResolvedEdge, frame: number): number {
  return edgeDrawProgressAt(resolved, edge, frame) * edge.length;
}

/** Whether a node is active at a frame (subject arrived, or its
 * incoming edge completed). Inactive nodes render as context only. */
export function nodeActiveAt(resolved: ResolvedDiagram, node: ResolvedNode, frame: number): boolean {
  return node.activationFrame !== null && frame >= node.activationFrame;
}

/**
 * A node's box at a frame. Only the bottleneck constraint changes: from
 * the relief frame it widens symmetrically around its center by
 * widen_ratio over widenFrames frames, so the opening the subject
 * passes through is visibly larger after relief. Anchors stay at the
 * base box edges; the widened box contains them.
 */
export function nodeBoxAt(resolved: ResolvedDiagram, node: ResolvedNode, frame: number): Box {
  const relief = resolved.relief;
  if (!relief || relief.node_id !== node.id) return node.box;
  const t = clamp01((frame - relief.frame) / relief.widenFrames);
  const scale = 1 + relief.widen_ratio * t;
  const width = node.box.width * scale;
  return {
    x: node.center.x - width / 2,
    y: node.box.y,
    width,
    height: node.box.height,
  };
}
