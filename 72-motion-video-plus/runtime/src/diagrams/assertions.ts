// Semantic motion assertions for diagrams (Directive MG-017,
// Sections 6 and 7.2).
//
// The assertions a diagram scene declares are evaluated against the
// resolved frame functions, not against reviewer impressions:
// - subject_identity: the persistent subject is at the declared
//   position at the declared frame (the same id, tracked through the
//   mechanism).
// - timeline_bounds: the envelope duration and the diagram timing
//   agree, in frames.
// - text_readability: the named nodes' label boxes do not collide and
//   every label fits inside its node box at the measured width.
// Causality gets its own evaluation: for every edge, the target cannot
// activate before the source, and no edge starts drawing before its
// source activates. Temporal order matching causality is a computed
// property of the frame functions, checked here mechanically.

import { subjectPositionAt } from "./frame";
import type { ResolvedDiagram } from "./frame";
import { labelCollisions } from "./layout";
import type { DiagramAssertion, DiagramSceneDoc } from "./model";

export interface AssertionResult {
  assertion_id: string;
  kind: DiagramAssertion["kind"];
  frame: number;
  pass: boolean;
  measured: number[];
  expected: number[];
  tolerance: number;
  unit: DiagramAssertion["unit"];
  detail: string;
}

function close(actual: number[], expected: number[], tolerance: number): boolean {
  return (
    actual.length === expected.length &&
    actual.every((value, i) => Math.abs(value - expected[i]) <= tolerance)
  );
}

export function evaluateAssertion(
  assertion: DiagramAssertion,
  doc: DiagramSceneDoc,
  resolved: ResolvedDiagram
): AssertionResult {
  const base = {
    assertion_id: assertion.id,
    kind: assertion.kind,
    frame: assertion.frame,
    expected: assertion.expected_values,
    tolerance: assertion.tolerance,
    unit: assertion.unit,
  };
  if (assertion.kind === "subject_identity") {
    const subjectId = assertion.subject_ids[0];
    if (resolved.subject && resolved.subject.id === subjectId) {
      const position = subjectPositionAt(resolved, assertion.frame);
      const measured = position ? [round2(position.x), round2(position.y)] : [];
      return {
        ...base,
        pass: position !== null && close(measured, assertion.expected_values, assertion.tolerance),
        measured,
        detail: position
          ? `subject "${subjectId}" is at (${measured[0]}, ${measured[1]}) at frame ${assertion.frame}; identity persists (same id at every frame)`
          : `subject "${subjectId}" has no position at frame ${assertion.frame}`,
      };
    }
    const node = resolved.nodes.find((candidate) => candidate.id === subjectId);
    if (node) {
      const measured = [round2(node.center.x), round2(node.center.y)];
      return {
        ...base,
        pass: close(measured, assertion.expected_values, assertion.tolerance),
        measured,
        detail: `node "${subjectId}" center is at (${measured[0]}, ${measured[1]})`,
      };
    }
    return {
      ...base,
      pass: false,
      measured: [],
      detail: `assertion names unknown subject "${subjectId}"`,
    };
  }
  if (assertion.kind === "timeline_bounds") {
    const measured = [
      doc.diagram.timing.start_frame,
      doc.diagram.timing.end_frame_exclusive,
      doc.diagram.timing.hold_to_frame_exclusive,
      doc.duration_frames,
    ];
    return {
      ...base,
      pass: close(measured, assertion.expected_values, assertion.tolerance),
      measured,
      detail: "start, motion end, hold end, and envelope duration in frames",
    };
  }
  if (assertion.kind === "text_readability") {
    const named = new Set(assertion.subject_ids);
    const collisions = labelCollisions(resolved).filter(
      (pair) => named.has(pair.a) && named.has(pair.b)
    );
    const slacks = resolved.nodes
      .filter((node) => named.has(node.id))
      .map((node) => node.box.width - node.labelBox.width);
    const minSlack = slacks.length > 0 ? Math.min(...slacks) : 0;
    const measured = [collisions.length, round2(minSlack)];
    return {
      ...base,
      pass: collisions.length === 0 && minSlack >= 0,
      measured,
      detail:
        `label collisions among named nodes: ${collisions.length}; ` +
        `tightest label fit slack ${round2(minSlack)}px (labels measured with the real font, never shrunk)`,
    };
  }
  return {
    ...base,
    pass: false,
    measured: [],
    detail: `assertion kind ${assertion.kind} does not apply to diagram components`,
  };
}

export function evaluateAssertions(
  doc: DiagramSceneDoc,
  resolved: ResolvedDiagram
): AssertionResult[] {
  return doc.semantic_motion_assertions.map((assertion) =>
    evaluateAssertion(assertion, doc, resolved)
  );
}

export interface CausalityCheck {
  edge_id: string;
  source: string;
  target: string;
  sourceActivationFrame: number | null;
  targetActivationFrame: number | null;
  drawStartFrame: number;
  ok: boolean;
  rule: string;
}

/**
 * The causality evaluation: for every edge, (1) the target activates no
 * earlier than the source, and (2) the edge starts drawing no earlier
 * than its source activates. Together with strictly increasing subject
 * arrival frames along the path, this is the mechanical form of
 * "temporal order matches causality".
 */
export function evaluateCausality(resolved: ResolvedDiagram): {
  pass: boolean;
  checks: CausalityCheck[];
  pathArrivalFrames: { node_id: string; activationFrame: number | null }[];
  pathOrderOk: boolean;
} {
  const activationOf = (id: string): number | null =>
    resolved.nodes.find((node) => node.id === id)?.activationFrame ?? null;
  const checks: CausalityCheck[] = resolved.edges.map((edge) => {
    const sourceActivation = activationOf(edge.source);
    const targetActivation = activationOf(edge.target);
    const ok =
      sourceActivation !== null &&
      targetActivation !== null &&
      targetActivation >= sourceActivation &&
      edge.drawStartFrame >= sourceActivation;
    return {
      edge_id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceActivationFrame: sourceActivation,
      targetActivationFrame: targetActivation,
      drawStartFrame: edge.drawStartFrame,
      ok,
      rule: "target activation >= source activation, and edge draw start >= source activation",
    };
  });
  const pathArrivalFrames = (resolved.subject?.parts ?? [])
    .filter((part) => part.type === "node")
    .map((part) => ({
      node_id: part.id,
      activationFrame: activationOf(part.id),
    }));
  let pathOrderOk = true;
  for (let i = 1; i < pathArrivalFrames.length; i += 1) {
    const prev = pathArrivalFrames[i - 1].activationFrame;
    const curr = pathArrivalFrames[i].activationFrame;
    if (prev === null || curr === null || !(curr > prev)) pathOrderOk = false;
  }
  return {
    pass: checks.every((check) => check.ok) && pathOrderOk,
    checks,
    pathArrivalFrames,
    pathOrderOk,
  };
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}
