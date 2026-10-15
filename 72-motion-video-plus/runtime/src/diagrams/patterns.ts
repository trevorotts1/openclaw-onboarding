// The four mechanism patterns as reusable scene builders
// (Directive MG-017, Section 6).
//
// Each builder takes pattern-level intent (stages, a decision, state
// pairs, a bottleneck) and produces a DiagramSpec whose structure
// already satisfies the pattern rules in model.ts: a list of process
// labels is never enough, so each builder wires the edges, the subject
// path, and the declarations (selected branch, relief) that make the
// mechanism demonstrable. Builders do not lay out or render; resolution
// (layout.ts) and the frame functions (frame.ts) own geometry and time.

import type {
  DiagramAssertion,
  DiagramCanvas,
  DiagramEdge,
  DiagramNode,
  DiagramSceneDoc,
  DiagramSpec,
  DiagramSubject,
  DiagramTiming,
} from "./model";

export interface StageInput {
  id: string;
  label: string;
}

export interface SubjectInput {
  id: string;
  label: string;
}

function chainEdges(stages: StageInput[], kind: DiagramEdge["kind"]): DiagramEdge[] {
  const edges: DiagramEdge[] = [];
  for (let i = 1; i < stages.length; i += 1) {
    edges.push({
      id: `edge-${stages[i - 1].id}-${stages[i].id}`,
      source: stages[i - 1].id,
      target: stages[i].id,
      kind,
    });
  }
  return edges;
}

/**
 * flow_through: one subject travels a path through labeled stages in
 * causal order and arrives at the final stage. The honest choice when
 * the explanation IS a sequence: intake to outcome, request to result.
 */
export function flowThrough(input: {
  stages: StageInput[];
  subject: SubjectInput | null;
  timing: DiagramTiming;
  canvas: DiagramCanvas;
}): DiagramSpec {
  const nodes: DiagramNode[] = input.stages.map((stage, i) => ({
    id: stage.id,
    label: stage.label,
    kind: i === 0 ? "input" : "stage",
  }));
  return {
    pattern: "flow_through",
    nodes,
    edges: chainEdges(input.stages, "flow"),
    subject:
      input.subject === null
        ? null
        : {
            id: input.subject.id,
            label: input.subject.label,
            path_node_ids: input.stages.map((stage) => stage.id),
          },
    selected_branch_edge_id: null,
    relief: null,
    timing: input.timing,
    canvas: input.canvas,
  };
}

/**
 * branching_decision: one input reaches a decision node and exactly
 * one declared branch is taken; the alternatives are drawn (they are
 * real possibilities) but not traveled. The honest choice when the
 * explanation is a rule: if this, then that, and here is why.
 */
export function branchingDecision(input: {
  input: StageInput;
  decision: StageInput;
  outcomes: StageInput[];
  selectedOutcomeId: string;
  subject: SubjectInput | null;
  timing: DiagramTiming;
  canvas: DiagramCanvas;
}): DiagramSpec {
  const nodes: DiagramNode[] = [
    { id: input.input.id, label: input.input.label, kind: "input" },
    { id: input.decision.id, label: input.decision.label, kind: "decision" },
    ...input.outcomes.map((outcome) => ({
      id: outcome.id,
      label: outcome.label,
      kind: "outcome" as const,
    })),
  ];
  const edges: DiagramEdge[] = [
    {
      id: `edge-${input.input.id}-${input.decision.id}`,
      source: input.input.id,
      target: input.decision.id,
      kind: "flow",
    },
    ...input.outcomes.map((outcome) => ({
      id: `edge-${input.decision.id}-${outcome.id}`,
      source: input.decision.id,
      target: outcome.id,
      kind: "branch" as const,
    })),
  ];
  const selectedEdge = edges.find(
    (edge) => edge.target === input.selectedOutcomeId && edge.kind === "branch"
  );
  return {
    pattern: "branching_decision",
    nodes,
    edges,
    subject:
      input.subject === null
        ? null
        : {
            id: input.subject.id,
            label: input.subject.label,
            path_node_ids: [input.input.id, input.decision.id, input.selectedOutcomeId],
          },
    selected_branch_edge_id: selectedEdge ? selectedEdge.id : null,
    relief: null,
    timing: input.timing,
    canvas: input.canvas,
  };
}

/**
 * before_after_system: the same objects in two states with a declared
 * transformation between them. The subject is one of the objects: its
 * identity persists while its state flips at the transform midpoint.
 * The honest choice when the explanation is a change of state, not a
 * journey: unsorted to sorted, manual to automated.
 */
export function beforeAfterSystem(input: {
  pairs: {
    pairId: string;
    before: StageInput;
    after: StageInput;
  }[];
  subject: (SubjectInput & { pairId: string }) | null;
  timing: DiagramTiming;
  canvas: DiagramCanvas;
}): DiagramSpec {
  const nodes: DiagramNode[] = [];
  const edges: DiagramEdge[] = [];
  for (const pair of input.pairs) {
    nodes.push({
      id: pair.before.id,
      label: pair.before.label,
      kind: "state",
      pair_id: pair.pairId,
      state_role: "before",
    });
    nodes.push({
      id: pair.after.id,
      label: pair.after.label,
      kind: "state",
      pair_id: pair.pairId,
      state_role: "after",
    });
    edges.push({
      id: `edge-${pair.before.id}-${pair.after.id}`,
      source: pair.before.id,
      target: pair.after.id,
      kind: "transform",
    });
  }
  let subject: DiagramSubject | null = null;
  if (input.subject !== null) {
    const pair = input.pairs.find((candidate) => candidate.pairId === input.subject?.pairId);
    if (pair) {
      subject = {
        id: input.subject.id,
        label: input.subject.label,
        path_node_ids: [pair.before.id, pair.after.id],
      };
    }
  }
  return {
    pattern: "before_after_system",
    nodes,
    edges,
    subject,
    selected_branch_edge_id: null,
    relief: null,
    timing: input.timing,
    canvas: input.canvas,
  };
}

/**
 * bottleneck_removal: a chain whose constraint stage first constricts
 * the flow (the subject slows and creeps through) and is then visibly
 * widened at the relief frame while flow continues through it. The
 * honest choice when the explanation is a constraint and its removal:
 * the queue at review, the single approver, the narrow step.
 */
export function bottleneckRemoval(input: {
  stages: StageInput[];
  bottleneckStageId: string;
  reliefFrame: number;
  widenRatio?: number;
  creepShare?: number;
  subject: SubjectInput | null;
  timing: DiagramTiming;
  canvas: DiagramCanvas;
}): DiagramSpec {
  const nodes: DiagramNode[] = input.stages.map((stage, i) => ({
    id: stage.id,
    label: stage.label,
    kind:
      stage.id === input.bottleneckStageId ? "constraint" : i === 0 ? "input" : "stage",
  }));
  return {
    pattern: "bottleneck_removal",
    nodes,
    edges: chainEdges(input.stages, "flow"),
    subject:
      input.subject === null
        ? null
        : {
            id: input.subject.id,
            label: input.subject.label,
            path_node_ids: input.stages.map((stage) => stage.id),
          },
    selected_branch_edge_id: null,
    relief: {
      node_id: input.bottleneckStageId,
      frame: input.reliefFrame,
      widen_ratio: input.widenRatio ?? 0.8,
      creep_share: input.creepShare ?? 0.3,
    },
    timing: input.timing,
    canvas: input.canvas,
  };
}

/** Wrap a spec in the scene-document envelope the catalog validates. */
export function diagramSceneDoc(input: {
  id: string;
  component_id: "C04" | "C09";
  headline: string;
  disclosure: string;
  spec: DiagramSpec;
  assertions: DiagramAssertion[];
}): DiagramSceneDoc {
  return {
    schema_version: "2.0",
    id: input.id,
    component_id: input.component_id,
    component_version: "1.0.0",
    engine: "remotion",
    layout_variant: input.spec.canvas.width >= input.spec.canvas.height ? "landscape" : "portrait",
    duration_frames: input.spec.timing.hold_to_frame_exclusive,
    copy: { headline: input.headline, disclosure: input.disclosure },
    diagram: input.spec,
    semantic_motion_assertions: input.assertions,
  };
}
