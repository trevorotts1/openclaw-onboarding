// Deterministic diagram layout and resolution (Directive MG-017).
//
// Layout places nodes so that label boxes, sized from REAL measured
// text widths (the measurer is injected; the production measurer reads
// the actual font binary through the MG-013 typography module), never
// collide. When a pattern cannot fit the canvas without collision, the
// resolver returns a named impossibility (MG_LAYOUT_IMPOSSIBLE with a
// specific code) instead of silently overlapping labels or shrinking
// essential text: shrinking a stage label to force a fit would break
// the typography floors, and overlapping labels fail the C09 minimum
// proof outright.
//
// Resolution then computes the full frame model: edge polylines that
// terminate exactly at target entry anchors, the subject path with its
// timing keyframes (including bottleneck constriction and relief), and
// per-node activation frames that encode causality: a node activates
// when the subject arrives or when its incoming edge finishes drawing,
// never before its upstream cause completes.

import {
  boxesOverlap,
  cumulativeLengths,
  polylineLength,
  type Box,
  type Point,
} from "./geometry";
import type { ResolvedDiagram, ResolvedEdge, ResolvedNode, SubjectPart } from "./frame";
import {
  findEdgeBetween,
  validateDiagramSpec,
  type DiagramFinding,
  type DiagramSpec,
} from "./model";

/** Node labels are essential text: they name the stages of the
 * mechanism. Measured and rendered at this size; never shrunk. */
export const LABEL_SIZE_PX = 46;
export const NODE_HEIGHT_PX = 96;
export const CANVAS_MARGIN_PX = 96;
const NODE_PAD_X_PX = 30;
const MIN_NODE_WIDTH_PX = 150;
const GAP_MAIN_PX = 110;
const GAP_CROSS_PX = 56;
/** The bottleneck constraint's traversal time is inflated by this
 * factor before renormalization: the subject visibly slows inside the
 * constraint while flow elsewhere keeps the declared window. */
const CONSTRAINT_TIME_FACTOR = 1.75;
/** Frames over which a relieved constraint widens to its full size. */
export const RELIEF_WIDEN_FRAMES = 18;

/** Text measurement source: width in px of a string at a size. The
 * production implementation measures with the actual font binary. */
export interface TextMeasurer {
  measure(text: string, sizePx: number): number;
}

export type LayoutResult =
  | { ok: true; resolved: ResolvedDiagram }
  | { ok: false; findings: DiagramFinding[] };

interface PlacedNode {
  id: string;
  /** Center along the flow (main) axis, in main-axis px. */
  centerMain: number;
  /** Center along the cross axis, in cross-axis px. */
  centerCross: number;
  width: number;
  height: number;
  labelWidth: number;
}

function impossible(code: string, message: string): LayoutResult {
  return {
    ok: false,
    findings: [{ category: "MG_LAYOUT_IMPOSSIBLE", path: "/diagram", message: `${code}: ${message}` }],
  };
}

export function resolveDiagram(spec: DiagramSpec, measurer: TextMeasurer): LayoutResult {
  const structural = validateDiagramSpec(spec);
  if (structural.length > 0) return { ok: false, findings: structural };

  const landscape = spec.canvas.width >= spec.canvas.height;
  const mainExtent = landscape ? spec.canvas.width : spec.canvas.height;
  const crossExtent = landscape ? spec.canvas.height : spec.canvas.width;
  if (mainExtent - 2 * CANVAS_MARGIN_PX <= 0 || crossExtent - 2 * CANVAS_MARGIN_PX <= 0) {
    return impossible(
      "canvas_too_small",
      `canvas ${spec.canvas.width}x${spec.canvas.height} leaves no room inside the ${CANVAS_MARGIN_PX}px margins`
    );
  }
  /** A node's extent along the main axis: its width in landscape, its
   * height in portrait (the chain runs vertically there). */
  const mainSize = (p: PlacedNode): number => (landscape ? p.width : p.height);
  const crossSize = (p: PlacedNode): number => (landscape ? p.height : p.width);

  const placed = new Map<string, PlacedNode>();
  for (const node of spec.nodes) {
    const labelWidth = measurer.measure(node.label, LABEL_SIZE_PX);
    placed.set(node.id, {
      id: node.id,
      centerMain: 0,
      centerCross: 0,
      width: Math.max(MIN_NODE_WIDTH_PX, Math.ceil(labelWidth) + 2 * NODE_PAD_X_PX),
      height: NODE_HEIGHT_PX,
      labelWidth,
    });
  }
  const get = (id: string): PlacedNode => {
    const p = placed.get(id);
    if (!p) throw new Error(`layout lost node "${id}"`);
    return p;
  };

  /** Stack nodes along the cross axis, centered, refusing overflow. */
  const stackCross = (ids: string[], code: string): LayoutResult | null => {
    const total =
      ids.reduce((sum, id) => sum + crossSize(get(id)), 0) + GAP_CROSS_PX * (ids.length - 1);
    if (total + 2 * CANVAS_MARGIN_PX > crossExtent) {
      return impossible(
        code,
        `stacking ${ids.length} nodes needs ${total}px of cross axis plus margins, canvas offers ${crossExtent}px`
      );
    }
    let cursor = (crossExtent - total) / 2;
    for (const id of ids) {
      const p = get(id);
      p.centerCross = cursor + crossSize(p) / 2;
      cursor += crossSize(p) + GAP_CROSS_PX;
    }
    return null;
  };

  if (spec.pattern === "flow_through" || spec.pattern === "bottleneck_removal") {
    const order =
      spec.subject !== null ? spec.subject.path_node_ids : spec.nodes.map((node) => node.id);
    const totalMain =
      order.reduce((sum, id) => sum + mainSize(get(id)), 0) + GAP_MAIN_PX * (order.length - 1);
    if (totalMain + 2 * CANVAS_MARGIN_PX > mainExtent) {
      return impossible(
        "chain_exceeds_canvas",
        `the chain of ${order.length} stages needs ${totalMain}px of main axis at measured label widths plus margins, canvas offers ${mainExtent}px; shorten labels, split the chain across beats, or use a larger canvas`
      );
    }
    let cursor = (mainExtent - totalMain) / 2;
    for (const id of order) {
      const p = get(id);
      p.centerMain = cursor + mainSize(p) / 2;
      p.centerCross = crossExtent / 2;
      cursor += mainSize(p) + GAP_MAIN_PX;
    }
    // Nodes not on the chain (not expected for these patterns, but the
    // spec permits context nodes): place them on a second row.
    const offChain = spec.nodes.filter((node) => !order.includes(node.id)).map((node) => node.id);
    if (offChain.length > 0) {
      const failure = stackCross(offChain, "context_nodes_exceed_canvas");
      if (failure) return failure;
      for (const id of offChain) {
        const p = get(id);
        p.centerMain = mainExtent / 2;
        p.centerCross = crossExtent - CANVAS_MARGIN_PX - crossSize(p) / 2;
      }
    }
  } else if (spec.pattern === "branching_decision") {
    const decision = spec.nodes.find((node) => node.kind === "decision");
    if (!decision) throw new Error("branching layout without a decision node");
    const branchEdges = spec.edges.filter(
      (edge) => edge.source === decision.id && edge.kind === "branch"
    );
    const outcomeIds = branchEdges.map((edge) => edge.target);
    const inputIds = spec.nodes
      .filter((node) => node.id !== decision.id && !outcomeIds.includes(node.id))
      .map((node) => node.id);
    if (inputIds.length !== 1) {
      return {
        ok: false,
        findings: [
          {
            category: "MG_SCHEMA_INVALID",
            path: "/diagram/nodes",
            message: `branching_decision layout needs exactly one input-side node besides the decision; found ${inputIds.length}.`,
          },
        ],
      };
    }
    const input = get(inputIds[0]);
    const decisionPlaced = get(decision.id);
    input.centerMain = CANVAS_MARGIN_PX + mainSize(input) / 2;
    input.centerCross = crossExtent / 2;
    decisionPlaced.centerMain =
      CANVAS_MARGIN_PX + mainSize(input) + GAP_MAIN_PX + mainSize(decisionPlaced) / 2;
    decisionPlaced.centerCross = crossExtent / 2;
    const decisionRight = decisionPlaced.centerMain + mainSize(decisionPlaced) / 2;
    let outcomesLeft = Number.POSITIVE_INFINITY;
    for (const id of outcomeIds) {
      const p = get(id);
      p.centerMain = mainExtent - CANVAS_MARGIN_PX - mainSize(p) / 2;
      outcomesLeft = Math.min(outcomesLeft, p.centerMain - mainSize(p) / 2);
    }
    if (decisionRight + GAP_MAIN_PX > outcomesLeft) {
      return impossible(
        "columns_overlap",
        `the decision column ends at ${Math.round(decisionRight)}px and the outcome column begins at ${Math.round(outcomesLeft)}px; outcome labels measured too wide for this canvas`
      );
    }
    const failure = stackCross(outcomeIds, "outcomes_exceed_canvas");
    if (failure) return failure;
  } else {
    // before_after_system: before column left, after column right, one
    // row per pair in declared pair order.
    const pairOrder: string[] = [];
    for (const node of spec.nodes) {
      if (node.pair_id !== undefined && !pairOrder.includes(node.pair_id)) {
        pairOrder.push(node.pair_id);
      }
    }
    const beforeIds = pairOrder.map(
      (pairId) =>
        spec.nodes.find((node) => node.pair_id === pairId && node.state_role === "before")?.id ?? ""
    );
    const afterIds = pairOrder.map(
      (pairId) =>
        spec.nodes.find((node) => node.pair_id === pairId && node.state_role === "after")?.id ?? ""
    );
    let beforeRight = 0;
    for (const id of beforeIds) {
      const p = get(id);
      p.centerMain = CANVAS_MARGIN_PX + mainSize(p) / 2;
      beforeRight = Math.max(beforeRight, p.centerMain + mainSize(p) / 2);
    }
    let afterLeft = Number.POSITIVE_INFINITY;
    for (const id of afterIds) {
      const p = get(id);
      p.centerMain = mainExtent - CANVAS_MARGIN_PX - mainSize(p) / 2;
      afterLeft = Math.min(afterLeft, p.centerMain - mainSize(p) / 2);
    }
    if (beforeRight + GAP_MAIN_PX > afterLeft) {
      return impossible(
        "columns_overlap",
        `the before column ends at ${Math.round(beforeRight)}px and the after column begins at ${Math.round(afterLeft)}px at measured label widths`
      );
    }
    const beforeFailure = stackCross(beforeIds, "pairs_exceed_canvas");
    if (beforeFailure) return beforeFailure;
    const afterFailure = stackCross(afterIds, "pairs_exceed_canvas");
    if (afterFailure) return afterFailure;
  }

  // ---- Screen boxes, anchors, polylines -------------------------------
  const toScreen = (p: PlacedNode): { box: Box; center: Point } => {
    const cx = landscape ? p.centerMain : p.centerCross;
    const cy = landscape ? p.centerCross : p.centerMain;
    return {
      box: { x: cx - p.width / 2, y: cy - p.height / 2, width: p.width, height: p.height },
      center: { x: cx, y: cy },
    };
  };
  const geometry = new Map<string, { box: Box; center: Point; entry: Point; exit: Point }>();
  for (const node of spec.nodes) {
    const p = get(node.id);
    const { box, center } = toScreen(p);
    geometry.set(node.id, {
      box,
      center,
      entry: { x: box.x, y: center.y },
      exit: { x: box.x + box.width, y: center.y },
    });
  }
  // Direction-aware anchors: an edge exits the side facing its target.
  const anchorsFor = (sourceId: string, targetId: string): { exit: Point; entry: Point } => {
    const s = geometry.get(sourceId);
    const t = geometry.get(targetId);
    if (!s || !t) throw new Error("anchor lookup for undeclared node");
    if (landscape) {
      const forward = t.center.x >= s.center.x;
      return {
        exit: forward
          ? { x: s.box.x + s.box.width, y: s.center.y }
          : { x: s.box.x, y: s.center.y },
        entry: forward
          ? { x: t.box.x, y: t.center.y }
          : { x: t.box.x + t.box.width, y: t.center.y },
      };
    }
    const forward = t.center.y >= s.center.y;
    return {
      exit: forward
        ? { x: s.center.x, y: s.box.y + s.box.height }
        : { x: s.center.x, y: s.box.y },
      entry: forward
        ? { x: t.center.x, y: t.box.y }
        : { x: t.center.x, y: t.box.y + t.box.height },
    };
  };
  const edgePoints = (sourceId: string, targetId: string): Point[] => {
    const { exit, entry } = anchorsFor(sourceId, targetId);
    if (landscape) {
      if (Math.abs(exit.y - entry.y) < 0.5) return [exit, entry];
      const midX = (exit.x + entry.x) / 2;
      return [exit, { x: midX, y: exit.y }, { x: midX, y: entry.y }, entry];
    }
    if (Math.abs(exit.x - entry.x) < 0.5) return [exit, entry];
    const midY = (exit.y + entry.y) / 2;
    return [exit, { x: exit.x, y: midY }, { x: entry.x, y: midY }, entry];
  };
  // Per-node canonical anchors: the entry anchor faces the previous
  // path node (or first incoming neighbor), the exit anchor faces the
  // next path node (or first outgoing neighbor). Edge polylines are
  // computed per edge from anchorsFor directly, so termination is exact
  // for every edge regardless of these canonical choices.
  for (const node of spec.nodes) {
    const g = geometry.get(node.id);
    if (!g) continue;
    const pathIdx =
      spec.subject !== null ? spec.subject.path_node_ids.indexOf(node.id) : -1;
    const prevId =
      spec.subject !== null && pathIdx > 0
        ? spec.subject.path_node_ids[pathIdx - 1]
        : undefined;
    const nextId =
      spec.subject !== null && pathIdx >= 0 && pathIdx < spec.subject.path_node_ids.length - 1
        ? spec.subject.path_node_ids[pathIdx + 1]
        : undefined;
    const entryFrom = prevId ?? spec.edges.find((edge) => edge.target === node.id)?.source;
    const exitTo = nextId ?? spec.edges.find((edge) => edge.source === node.id)?.target;
    if (entryFrom && entryFrom !== node.id) {
      g.entry = anchorsFor(entryFrom, node.id).entry;
    }
    if (exitTo && exitTo !== node.id) {
      g.exit = anchorsFor(node.id, exitTo).exit;
    }
  }

  const resolvedEdges: ResolvedEdge[] = spec.edges.map((edge) => {
    const points = edgePoints(edge.source, edge.target);
    const cumulative = cumulativeLengths(points);
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      kind: edge.kind,
      label: edge.label ?? null,
      points,
      cumulative,
      length: cumulative[cumulative.length - 1],
      isPathEdge: false,
      pathArcFrom: null,
      pathArcTo: null,
      drawStartFrame: spec.timing.end_frame_exclusive,
      drawEndFrame: spec.timing.end_frame_exclusive,
    };
  });
  const edgeMap = new Map(resolvedEdges.map((edge) => [edge.id, edge]));

  // ---- Subject path, parts, keyframes ---------------------------------
  const D = spec.timing.end_frame_exclusive - spec.timing.start_frame;
  let resolvedSubject: ResolvedDiagram["subject"] = null;
  const centerArcByNode = new Map<string, number>();
  if (spec.subject !== null) {
    const path = spec.subject.path_node_ids;
    interface Segment {
      type: "node" | "edge";
      id: string;
      points: Point[];
    }
    const segments: Segment[] = [];
    for (let i = 0; i < path.length; i += 1) {
      const nodeId = path[i];
      const g = geometry.get(nodeId);
      if (!g) throw new Error(`subject path node "${nodeId}" has no geometry`);
      if (i === 0) {
        segments.push({ type: "node", id: nodeId, points: [g.center, g.exit] });
      } else {
        segments.push({ type: "node", id: nodeId, points: [g.entry, g.center, g.exit] });
      }
      if (i < path.length - 1) {
        const nextId = path[i + 1];
        const edge = findEdgeBetween(spec, nodeId, nextId);
        if (!edge) throw new Error("subject path edge vanished after validation");
        segments.push({ type: "edge", id: edge.id, points: edgePoints(nodeId, nextId) });
      }
    }
    // The final node contributes only its entry-to-center half: the
    // subject ends at the destination node's center, so drop the exit
    // point from its [entry, center, exit] segment.
    const last = segments[segments.length - 1];
    if (last.type === "node" && last.points.length > 2) {
      last.points = last.points.slice(0, last.points.length - 1);
    }
    const points: Point[] = [];
    const segPointRange: { startIdx: number; endIdx: number }[] = [];
    for (const segment of segments) {
      const startIdx = points.length === 0 ? 0 : points.length - 1;
      segment.points.forEach((point, j) => {
        if (j === 0 && points.length > 0) return;
        points.push(point);
      });
      segPointRange.push({ startIdx, endIdx: points.length - 1 });
    }
    const cumulative = cumulativeLengths(points);
    const totalLength = cumulative[cumulative.length - 1];
    const parts: SubjectPart[] = segments.map((segment, i) => ({
      type: segment.type,
      id: segment.id,
      from: cumulative[segPointRange[i].startIdx],
      to: cumulative[segPointRange[i].endIdx],
    }));
    for (let i = 0; i < path.length; i += 1) {
      const g = geometry.get(path[i]);
      if (!g) continue;
      const idx = points.findIndex((point) => point.x === g.center.x && point.y === g.center.y);
      if (idx >= 0) centerArcByNode.set(path[i], cumulative[idx]);
    }
    // Durations per segment, bottleneck-inflated then renormalized.
    const segLengths = parts.map((part) => part.to - part.from);
    let durations = segLengths.map((len) => (totalLength === 0 ? 0 : (D * len) / totalLength));
    const relief = spec.relief;
    const constraintSegIdx = relief
      ? segments.findIndex((segment) => segment.type === "node" && segment.id === relief.node_id)
      : -1;
    if (constraintSegIdx >= 0) durations[constraintSegIdx] *= CONSTRAINT_TIME_FACTOR;
    const sum = durations.reduce((a, b) => a + b, 0);
    if (sum > 0) durations = durations.map((d) => (d * D) / sum);

    const keyframes: { frame: number; arc: number }[] = [
      { frame: spec.timing.start_frame, arc: 0 },
    ];
    let t = spec.timing.start_frame;
    for (let i = 0; i < segments.length; i += 1) {
      const segStart = t;
      const segEnd = t + durations[i];
      if (relief && i === constraintSegIdx) {
        const R = relief.frame;
        if (!(R > segStart && R < segEnd)) {
          return {
            ok: false,
            findings: [
              {
                category: "MG_TIMELINE_INVALID",
                path: "/diagram/relief/frame",
                message:
                  `relief frame ${R} lies outside the constraint traversal window ` +
                  `[${segStart.toFixed(1)}, ${segEnd.toFixed(1)}): the subject is not inside ` +
                  `"${relief.node_id}" at relief time. Move the relief frame inside the ` +
                  "constraint traversal or lengthen the motion window.",
              },
            ],
          };
        }
        keyframes.push({
          frame: R,
          arc: parts[i].from + relief.creep_share * segLengths[i],
        });
      }
      keyframes.push({ frame: segEnd, arc: parts[i].to });
      t = segEnd;
    }
    // The state flip for before/after: the midpoint of the subject's
    // transform edge part.
    let stateFlipArc: number | null = null;
    if (spec.pattern === "before_after_system") {
      const transformPart = parts.find((part) => {
        if (part.type !== "edge") return false;
        const edge = edgeMap.get(part.id);
        return edge !== undefined && edge.kind === "transform";
      });
      if (transformPart) stateFlipArc = (transformPart.from + transformPart.to) / 2;
    }
    for (let i = 0; i < segments.length; i += 1) {
      const segment = segments[i];
      if (segment.type !== "edge") continue;
      const resolvedEdge = edgeMap.get(segment.id);
      if (!resolvedEdge) continue;
      resolvedEdge.isPathEdge = true;
      resolvedEdge.pathArcFrom = parts[i].from;
      resolvedEdge.pathArcTo = parts[i].to;
    }
    resolvedSubject = {
      id: spec.subject.id,
      label: spec.subject.label,
      points,
      cumulative,
      totalLength,
      parts,
      keyframes,
      stateFlipArc,
    };
  }

  // ---- Activation frames (causality made concrete) --------------------
  const activation = new Map<string, number>();
  const frameAtArc = (arc: number): number => {
    if (!resolvedSubject) return spec.timing.start_frame;
    const keys = resolvedSubject.keyframes;
    for (let i = 1; i < keys.length; i += 1) {
      if (arc <= keys[i].arc) {
        const a = keys[i - 1];
        const b = keys[i];
        const span = b.arc - a.arc;
        const frac = span === 0 ? 1 : (arc - a.arc) / span;
        return Math.ceil(a.frame + (b.frame - a.frame) * frac);
      }
    }
    return Math.ceil(keys[keys.length - 1].frame);
  };
  if (resolvedSubject) {
    for (const [nodeId, arc] of centerArcByNode) {
      activation.set(nodeId, frameAtArc(arc));
    }
  }
  const nominalSpeed = resolvedSubject && D > 0 ? resolvedSubject.totalLength / D : 30;
  let progressed = true;
  let guard = 0;
  while (activation.size < spec.nodes.length && progressed && guard < 100) {
    guard += 1;
    progressed = false;
    for (const node of spec.nodes) {
      if (activation.has(node.id)) continue;
      const incoming = spec.edges.filter((edge) => edge.target === node.id);
      if (incoming.length === 0) {
        activation.set(node.id, spec.timing.start_frame);
        progressed = true;
        continue;
      }
      const ready = incoming.every((edge) => activation.has(edge.source));
      if (!ready) continue;
      let latest = spec.timing.start_frame;
      for (const edge of incoming) {
        const sourceActivation = activation.get(edge.source) as number;
        const resolvedEdge = edgeMap.get(edge.id);
        if (resolvedEdge && !resolvedEdge.isPathEdge) {
          const duration = Math.min(
            60,
            Math.max(8, Math.round(resolvedEdge.length / Math.max(nominalSpeed, 1)))
          );
          resolvedEdge.drawStartFrame = sourceActivation;
          resolvedEdge.drawEndFrame = sourceActivation + duration;
        }
        latest = Math.max(
          latest,
          resolvedEdge ? resolvedEdge.drawEndFrame : sourceActivation
        );
      }
      activation.set(node.id, latest);
      progressed = true;
    }
  }
  if (activation.size < spec.nodes.length) {
    return {
      ok: false,
      findings: [
        {
          category: "MG_SCHEMA_INVALID",
          path: "/diagram/edges",
          message:
            "Some nodes never activate: the edge graph has a cycle or a disconnected cause chain, so temporal order cannot match causality.",
        },
      ],
    };
  }
  // Path edges report their draw window in frames too (for evidence).
  if (resolvedSubject) {
    for (const edge of resolvedEdges) {
      if (edge.isPathEdge && edge.pathArcFrom !== null && edge.pathArcTo !== null) {
        edge.drawStartFrame = frameAtArc(edge.pathArcFrom);
        edge.drawEndFrame = frameAtArc(edge.pathArcTo);
      }
    }
  }

  const resolvedNodes: ResolvedNode[] = spec.nodes.map((node) => {
    const p = get(node.id);
    const g = geometry.get(node.id);
    if (!g) throw new Error(`node "${node.id}" lost its geometry`);
    const labelBox: Box = {
      x: g.center.x - p.labelWidth / 2,
      y: g.center.y - LABEL_SIZE_PX / 2,
      width: p.labelWidth,
      height: LABEL_SIZE_PX,
    };
    return {
      id: node.id,
      label: node.label,
      kind: node.kind,
      pair_id: node.pair_id ?? null,
      state_role: node.state_role ?? null,
      box: g.box,
      labelBox,
      center: g.center,
      entryAnchor: g.entry,
      exitAnchor: g.exit,
      centerArc: centerArcByNode.get(node.id) ?? null,
      activationFrame: activation.get(node.id) ?? null,
    };
  });

  const resolved: ResolvedDiagram = {
    pattern: spec.pattern,
    orientation: landscape ? "landscape" : "portrait",
    canvas: spec.canvas,
    timing: spec.timing,
    nodes: resolvedNodes,
    edges: resolvedEdges,
    subject: resolvedSubject,
    relief: spec.relief ? { ...spec.relief, widenFrames: RELIEF_WIDEN_FRAMES } : null,
  };
  return { ok: true, resolved };
}

/**
 * Pairwise label-box collisions in a resolved diagram. Layout never
 * produces them for the patterns it places (it refuses instead), so a
 * non-empty result means a hand-built or mutated layout bypassed the
 * resolver: exactly what the C09 proof must catch.
 */
export function labelCollisions(resolved: ResolvedDiagram): { a: string; b: string }[] {
  const out: { a: string; b: string }[] = [];
  for (let i = 0; i < resolved.nodes.length; i += 1) {
    for (let j = i + 1; j < resolved.nodes.length; j += 1) {
      if (boxesOverlap(resolved.nodes[i].labelBox, resolved.nodes[j].labelBox, 4)) {
        out.push({ a: resolved.nodes[i].id, b: resolved.nodes[j].id });
      }
    }
  }
  return out;
}

/** Total subject-path length helper for evidence records. */
export function subjectPathLength(resolved: ResolvedDiagram): number {
  return resolved.subject ? polylineLength(resolved.subject.points) : 0;
}
