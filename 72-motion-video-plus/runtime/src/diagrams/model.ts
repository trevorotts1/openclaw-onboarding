// Causal diagram model (Directive MG-017, Section 6).
//
// A diagram scene is a closed document: nodes with persistent ids and
// labels, directed edges between declared nodes, and (for mechanism
// components) one persistent subject that travels a declared path
// through the nodes. Temporal order must match causality: a downstream
// node can only activate after its upstream cause completes, and that
// rule is encoded in the resolved frame functions and checked by the
// assertions module, not left as reviewer folklore.
//
// The scene document rides in the canonical scene envelope shape
// (schema_version, id, component_id, duration_frames, copy) with the
// diagram itself under "diagram". The canonical contracts schema is
// C05-only and is NOT modified by this item; contracts-level job
// dispatch for C04/C09 is an integration note for the orchestrator
// item (MG-025), the same pattern MG-018 recorded for the catalog.

export type DiagramPattern =
  | "flow_through"
  | "branching_decision"
  | "before_after_system"
  | "bottleneck_removal";

export type DiagramNodeKind =
  | "input"
  | "stage"
  | "decision"
  | "outcome"
  | "state"
  | "constraint";

export type DiagramEdgeKind = "flow" | "branch" | "transform";

export interface DiagramNode {
  id: string;
  label: string;
  kind: DiagramNodeKind;
  /** Before/after pairing: nodes sharing a pair_id are the same object
   * in two states. Only meaningful for kind "state". */
  pair_id?: string;
  /** Which side of a before/after pair this node is. */
  state_role?: "before" | "after";
}

export interface DiagramEdge {
  id: string;
  source: string;
  target: string;
  kind: DiagramEdgeKind;
  label?: string;
}

export interface DiagramSubject {
  /** Persistent identity: the same id is trackable at every frame. */
  id: string;
  label: string;
  /** Node ids the subject visits, in causal order. Consecutive ids
   * must be connected by a declared edge. */
  path_node_ids: string[];
}

export interface DiagramTiming {
  /** First frame of subject motion (half-open interval convention). */
  start_frame: number;
  /** End of subject motion, exclusive. The final state holds from here. */
  end_frame_exclusive: number;
  /** End of the readable hold, exclusive; equals duration_frames. */
  hold_to_frame_exclusive: number;
}

export interface DiagramCanvas {
  width: number;
  height: number;
  fps: number;
}

/**
 * Bottleneck relief declaration (bottleneck_removal pattern only): at
 * relief.frame the constraint visibly widens by widen_ratio and the
 * subject, which has crept through creep_share of the constraint by
 * then, resumes full speed for the remainder of the constraint.
 */
export interface DiagramRelief {
  node_id: string;
  frame: number;
  widen_ratio: number;
  creep_share: number;
}

export interface DiagramSpec {
  pattern: DiagramPattern;
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  subject: DiagramSubject | null;
  /** The declared branch choice for branching_decision: the edge id of
   * the branch the subject (or the explanation) takes. Declared, never
   * inferred (Section 7.1 C09 minimum proof). */
  selected_branch_edge_id: string | null;
  relief: DiagramRelief | null;
  timing: DiagramTiming;
  canvas: DiagramCanvas;
}

/** Semantic motion assertion in the canonical contracts shape. */
export interface DiagramAssertion {
  id: string;
  kind: "subject_identity" | "timeline_bounds" | "text_readability" | "bar_widths";
  subject_ids: string[];
  frame: number;
  expected_values: number[];
  tolerance: number;
  unit: "source_px" | "normalized" | "frames";
  evidence: string[];
}

export interface DiagramSceneDoc {
  schema_version: "2.0";
  id: string;
  component_id: "C04" | "C09";
  component_version: "1.0.0";
  engine: "remotion";
  layout_variant: "landscape" | "portrait";
  duration_frames: number;
  copy: { headline: string; disclosure: string };
  diagram: DiagramSpec;
  semantic_motion_assertions: DiagramAssertion[];
}

export type DiagramFindingCategory =
  | "MG_SCHEMA_INVALID"
  | "MG_TIMELINE_INVALID"
  | "MG_LAYOUT_IMPOSSIBLE";

export interface DiagramFinding {
  category: DiagramFindingCategory;
  /** JSON-pointer-ish path into the scene document. */
  path: string;
  message: string;
}

const NODE_KINDS: ReadonlySet<string> = new Set([
  "input",
  "stage",
  "decision",
  "outcome",
  "state",
  "constraint",
]);
const EDGE_KINDS: ReadonlySet<string> = new Set(["flow", "branch", "transform"]);

/**
 * Structural validation of one diagram spec (shape-level rules live in
 * the JSON schema in schema.ts; this layer enforces the semantic rules
 * a schema cannot): referential integrity (no orphan edges or nodes),
 * subject-path connectivity, and the pattern-specific rules. Returns
 * findings; an empty array means the spec is structurally sound.
 */
export function validateDiagramSpec(spec: DiagramSpec): DiagramFinding[] {
  const findings: DiagramFinding[] = [];
  const push = (category: DiagramFindingCategory, path: string, message: string): void => {
    findings.push({ category, path, message });
  };

  const nodeIds = new Set<string>();
  spec.nodes.forEach((node, i) => {
    if (nodeIds.has(node.id)) {
      push("MG_SCHEMA_INVALID", `/diagram/nodes/${i}`, `Duplicate node id "${node.id}".`);
    }
    nodeIds.add(node.id);
    if (!NODE_KINDS.has(node.kind)) {
      push("MG_SCHEMA_INVALID", `/diagram/nodes/${i}/kind`, `Unknown node kind "${node.kind}".`);
    }
  });

  const edgeIds = new Set<string>();
  const incident = new Set<string>();
  spec.edges.forEach((edge, i) => {
    if (edgeIds.has(edge.id)) {
      push("MG_SCHEMA_INVALID", `/diagram/edges/${i}`, `Duplicate edge id "${edge.id}".`);
    }
    edgeIds.add(edge.id);
    if (!EDGE_KINDS.has(edge.kind)) {
      push("MG_SCHEMA_INVALID", `/diagram/edges/${i}/kind`, `Unknown edge kind "${edge.kind}".`);
    }
    if (!nodeIds.has(edge.source)) {
      push(
        "MG_SCHEMA_INVALID",
        `/diagram/edges/${i}/source`,
        `Edge "${edge.id}" is an orphan: its source node "${edge.source}" is not declared.`
      );
    }
    if (!nodeIds.has(edge.target)) {
      push(
        "MG_SCHEMA_INVALID",
        `/diagram/edges/${i}/target`,
        `Edge "${edge.id}" is an orphan: its target node "${edge.target}" is not declared.`
      );
    }
    incident.add(edge.source);
    incident.add(edge.target);
  });
  spec.nodes.forEach((node, i) => {
    if (!incident.has(node.id)) {
      push(
        "MG_SCHEMA_INVALID",
        `/diagram/nodes/${i}`,
        `Node "${node.id}" is an orphan: no edge touches it, so it plays no part in the mechanism.`
      );
    }
  });

  // Timing: integer half-open interval inside the scene duration.
  const t = spec.timing;
  if (
    !Number.isInteger(t.start_frame) ||
    !Number.isInteger(t.end_frame_exclusive) ||
    !Number.isInteger(t.hold_to_frame_exclusive) ||
    t.start_frame < 0 ||
    !(t.start_frame < t.end_frame_exclusive) ||
    !(t.end_frame_exclusive <= t.hold_to_frame_exclusive)
  ) {
    push(
      "MG_TIMELINE_INVALID",
      "/diagram/timing",
      "Timing must satisfy 0 <= start_frame < end_frame_exclusive <= hold_to_frame_exclusive in integer frames."
    );
  }

  // Subject path connectivity.
  const edgeBetween = (a: string, b: string): DiagramEdge | undefined =>
    spec.edges.find((edge) => edge.source === a && edge.target === b);
  if (spec.subject !== null) {
    const path = spec.subject.path_node_ids;
    if (path.length < 2) {
      push(
        "MG_SCHEMA_INVALID",
        "/diagram/subject/path_node_ids",
        "A traveling subject needs at least two path nodes: a start and a destination."
      );
    }
    path.forEach((nodeId, i) => {
      if (!nodeIds.has(nodeId)) {
        push(
          "MG_SCHEMA_INVALID",
          `/diagram/subject/path_node_ids/${i}`,
          `Subject path names undeclared node "${nodeId}".`
        );
      }
      if (i > 0 && !edgeBetween(path[i - 1], nodeId)) {
        push(
          "MG_SCHEMA_INVALID",
          `/diagram/subject/path_node_ids/${i}`,
          `Subject path step "${path[i - 1]}" -> "${nodeId}" has no declared edge; the subject cannot teleport.`
        );
      }
    });
  }

  // Pattern rules.
  if (spec.pattern === "branching_decision") {
    const decisions = spec.nodes.filter((node) => node.kind === "decision");
    if (decisions.length !== 1) {
      push(
        "MG_SCHEMA_INVALID",
        "/diagram/nodes",
        `branching_decision needs exactly one decision node; found ${decisions.length}.`
      );
    } else {
      const branches = spec.edges.filter(
        (edge) => edge.source === decisions[0].id && edge.kind === "branch"
      );
      if (branches.length < 2) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/edges",
          "branching_decision needs at least two branch edges out of the decision node."
        );
      }
      if (spec.selected_branch_edge_id === null) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/selected_branch_edge_id",
          "branching_decision must declare its selected branch; branch selection is declared, never inferred."
        );
      } else if (!branches.some((edge) => edge.id === spec.selected_branch_edge_id)) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/selected_branch_edge_id",
          `Selected branch "${spec.selected_branch_edge_id}" is not a branch edge out of the decision node.`
        );
      }
      if (spec.subject !== null && spec.selected_branch_edge_id !== null) {
        const selected = spec.edges.find((edge) => edge.id === spec.selected_branch_edge_id);
        const path = spec.subject.path_node_ids;
        if (
          selected &&
          (!path.includes(decisions[0].id) || path[path.length - 1] !== selected.target)
        ) {
          push(
            "MG_SCHEMA_INVALID",
            "/diagram/subject/path_node_ids",
            "The subject path must pass through the decision node and end at the selected branch's target."
          );
        }
      }
    }
  }
  if (spec.pattern === "before_after_system") {
    const pairs = new Map<string, DiagramNode[]>();
    for (const node of spec.nodes) {
      if (node.kind !== "state" || node.pair_id === undefined || node.state_role === undefined) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/nodes",
          `before_after_system nodes must be state nodes carrying pair_id and state_role; node "${node.id}" is not.`
        );
        continue;
      }
      const list = pairs.get(node.pair_id) ?? [];
      list.push(node);
      pairs.set(node.pair_id, list);
    }
    for (const [pairId, members] of pairs) {
      const befores = members.filter((node) => node.state_role === "before");
      const afters = members.filter((node) => node.state_role === "after");
      if (befores.length !== 1 || afters.length !== 1) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/nodes",
          `Pair "${pairId}" must have exactly one before node and one after node.`
        );
        continue;
      }
      const link = spec.edges.find(
        (edge) =>
          edge.source === befores[0].id && edge.target === afters[0].id && edge.kind === "transform"
      );
      if (!link) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/edges",
          `Pair "${pairId}" has no transform edge from its before node to its after node.`
        );
      }
    }
  }
  if (spec.pattern === "bottleneck_removal") {
    if (spec.relief === null) {
      push(
        "MG_SCHEMA_INVALID",
        "/diagram/relief",
        "bottleneck_removal must declare its relief: the constraint node and the frame it is relieved."
      );
    } else {
      const node = spec.nodes.find((candidate) => candidate.id === spec.relief?.node_id);
      if (!node || node.kind !== "constraint") {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/relief/node_id",
          `Relief node "${spec.relief.node_id}" must be a declared constraint node.`
        );
      }
      if (
        spec.subject === null ||
        !spec.subject.path_node_ids.includes(spec.relief.node_id)
      ) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/relief/node_id",
          "The relieved constraint must sit on the subject path; flow cannot be relieved where nothing flows."
        );
      }
      if (!(t.start_frame < spec.relief.frame && spec.relief.frame < t.end_frame_exclusive)) {
        push(
          "MG_TIMELINE_INVALID",
          "/diagram/relief/frame",
          "The relief frame must lie strictly inside the subject motion interval."
        );
      }
      if (!(spec.relief.creep_share > 0 && spec.relief.creep_share < 1)) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/relief/creep_share",
          "creep_share must lie strictly between 0 and 1: by relief time the subject has crept partway through the constraint, not none or all of it."
        );
      }
      if (!(spec.relief.widen_ratio > 0)) {
        push(
          "MG_SCHEMA_INVALID",
          "/diagram/relief/widen_ratio",
          "widen_ratio must be positive: relief visibly widens the constraint."
        );
      }
    }
  }
  if (spec.pattern !== "bottleneck_removal" && spec.relief !== null) {
    push(
      "MG_SCHEMA_INVALID",
      "/diagram/relief",
      `Pattern ${spec.pattern} does not declare relief; relief belongs to bottleneck_removal only.`
    );
  }
  return findings;
}

/** The edge connecting two nodes, or null. */
export function findEdgeBetween(spec: DiagramSpec, source: string, target: string): DiagramEdge | null {
  return spec.edges.find((edge) => edge.source === source && edge.target === target) ?? null;
}
