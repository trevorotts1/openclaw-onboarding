// Closed input schemas for the diagram components (Directive MG-017,
// Sections 7.2 and 16.1).
//
// C04 and C09 register component-specific closed schemas here, in the
// diagrams module, because the canonical contracts schema is C05-only
// and is not modified by this item. The catalog compiles these schemas
// exactly as it compiles C05's (the contracts $defs travel with them,
// unused but available). Document-level validation combines the JSON
// schema (shape) with the structural rules in model.ts (referential
// integrity and pattern semantics) and the timeline rule that the
// envelope duration equals the diagram's hold end.

import { validateWithSchema } from "../validation/validate";
import {
  validateDiagramSpec,
  type DiagramFinding,
  type DiagramSceneDoc,
} from "./model";

const ID_PATTERN = "^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$";

const NODE_SCHEMA: Record<string, unknown> = {
  type: "object",
  additionalProperties: false,
  required: ["id", "label", "kind"],
  properties: {
    id: { type: "string", pattern: ID_PATTERN },
    label: { type: "string", minLength: 1 },
    kind: {
      enum: ["input", "stage", "decision", "outcome", "state", "constraint"],
    },
    pair_id: { type: "string", minLength: 1 },
    state_role: { enum: ["before", "after"] },
  },
};

const EDGE_SCHEMA: Record<string, unknown> = {
  type: "object",
  additionalProperties: false,
  required: ["id", "source", "target", "kind"],
  properties: {
    id: { type: "string", pattern: ID_PATTERN },
    source: { type: "string", pattern: ID_PATTERN },
    target: { type: "string", pattern: ID_PATTERN },
    kind: { enum: ["flow", "branch", "transform"] },
    label: { type: "string", minLength: 1 },
  },
};

const SUBJECT_SCHEMA: Record<string, unknown> = {
  type: "object",
  additionalProperties: false,
  required: ["id", "label", "path_node_ids"],
  properties: {
    id: { type: "string", pattern: ID_PATTERN },
    label: { type: "string", minLength: 1 },
    path_node_ids: {
      type: "array",
      minItems: 2,
      items: { type: "string", pattern: ID_PATTERN },
    },
  },
};

const RELIEF_SCHEMA: Record<string, unknown> = {
  type: "object",
  additionalProperties: false,
  required: ["node_id", "frame", "widen_ratio", "creep_share"],
  properties: {
    node_id: { type: "string", pattern: ID_PATTERN },
    frame: { type: "integer", minimum: 0 },
    widen_ratio: { type: "number", exclusiveMinimum: 0 },
    creep_share: { type: "number", exclusiveMinimum: 0, exclusiveMaximum: 1 },
  },
};

const ASSERTION_SCHEMA: Record<string, unknown> = {
  type: "object",
  additionalProperties: false,
  required: [
    "id",
    "kind",
    "subject_ids",
    "frame",
    "expected_values",
    "tolerance",
    "unit",
    "evidence",
  ],
  properties: {
    id: { type: "string", pattern: ID_PATTERN },
    kind: {
      enum: ["subject_identity", "timeline_bounds", "text_readability", "bar_widths"],
    },
    subject_ids: {
      type: "array",
      minItems: 1,
      items: { type: "string", pattern: ID_PATTERN },
    },
    frame: { type: "integer", minimum: 0 },
    expected_values: { type: "array", items: { type: "number" } },
    tolerance: { type: "number", minimum: 0 },
    unit: { enum: ["source_px", "normalized", "frames"] },
    evidence: { type: "array", minItems: 1, items: { type: "string", minLength: 1 } },
  },
};

function diagramSpecSchema(
  patterns: string[],
  subjectRequired: boolean
): Record<string, unknown> {
  return {
    type: "object",
    additionalProperties: false,
    required: [
      "pattern",
      "nodes",
      "edges",
      "subject",
      "selected_branch_edge_id",
      "relief",
      "timing",
      "canvas",
    ],
    properties: {
      pattern: { enum: patterns },
      nodes: { type: "array", minItems: 2, items: NODE_SCHEMA },
      edges: { type: "array", minItems: 1, items: EDGE_SCHEMA },
      subject: subjectRequired ? SUBJECT_SCHEMA : { anyOf: [SUBJECT_SCHEMA, { type: "null" }] },
      selected_branch_edge_id: {
        anyOf: [{ type: "string", pattern: ID_PATTERN }, { type: "null" }],
      },
      relief: { anyOf: [RELIEF_SCHEMA, { type: "null" }] },
      timing: {
        type: "object",
        additionalProperties: false,
        required: ["start_frame", "end_frame_exclusive", "hold_to_frame_exclusive"],
        properties: {
          start_frame: { type: "integer", minimum: 0 },
          end_frame_exclusive: { type: "integer", minimum: 1 },
          hold_to_frame_exclusive: { type: "integer", minimum: 1 },
        },
      },
      canvas: {
        type: "object",
        additionalProperties: false,
        required: ["width", "height", "fps"],
        properties: {
          width: { type: "integer", minimum: 320 },
          height: { type: "integer", minimum: 320 },
          fps: { type: "integer", minimum: 1 },
        },
      },
    },
  };
}

function diagramSceneSchema(
  componentId: "C04" | "C09",
  patterns: string[],
  subjectRequired: boolean
): Record<string, unknown> {
  return {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    title: `${componentId} diagram scene (MG-017 registration schema)`,
    type: "object",
    additionalProperties: false,
    required: [
      "schema_version",
      "id",
      "component_id",
      "component_version",
      "engine",
      "layout_variant",
      "duration_frames",
      "copy",
      "diagram",
      "semantic_motion_assertions",
    ],
    properties: {
      schema_version: { const: "2.0" },
      id: { type: "string", pattern: ID_PATTERN },
      component_id: { const: componentId },
      component_version: { const: "1.0.0" },
      engine: { const: "remotion" },
      layout_variant: { enum: ["landscape", "portrait"] },
      duration_frames: { type: "integer", minimum: 1 },
      copy: {
        type: "object",
        additionalProperties: false,
        required: ["headline", "disclosure"],
        properties: {
          headline: { type: "string", minLength: 1 },
          disclosure: { type: "string", minLength: 1 },
        },
      },
      diagram: diagramSpecSchema(patterns, subjectRequired),
      semantic_motion_assertions: {
        type: "array",
        minItems: 1,
        items: ASSERTION_SCHEMA,
      },
    },
  };
}

/** C04 object-through-mechanism: a persistent subject is required, and
 * the patterns are the ones where an object travels or transforms. */
export const C04_INPUT_SCHEMA: Record<string, unknown> = diagramSceneSchema(
  "C04",
  ["flow_through", "before_after_system", "bottleneck_removal"],
  true
);

/** C09 causal/branching diagram: the branching pattern and the plain
 * causal chain; a traveling subject is optional (a pure build has none). */
export const C09_INPUT_SCHEMA: Record<string, unknown> = diagramSceneSchema(
  "C09",
  ["branching_decision", "flow_through"],
  false
);

export function inputSchemaFor(componentId: string): Record<string, unknown> | null {
  if (componentId === "C04") return C04_INPUT_SCHEMA;
  if (componentId === "C09") return C09_INPUT_SCHEMA;
  return null;
}

/**
 * Full document validation for a diagram scene: JSON schema shape,
 * structural rules, and the envelope timeline rule. Returns findings
 * in the diagrams finding vocabulary; empty means valid.
 */
export function validateDiagramSceneDoc(doc: unknown): DiagramFinding[] {
  if (typeof doc !== "object" || doc === null || Array.isArray(doc)) {
    return [
      { category: "MG_SCHEMA_INVALID", path: "", message: "Diagram scene document must be an object." },
    ];
  }
  const componentId = (doc as { component_id?: unknown }).component_id;
  const schema = typeof componentId === "string" ? inputSchemaFor(componentId) : null;
  if (schema === null) {
    return [
      {
        category: "MG_SCHEMA_INVALID",
        path: "/component_id",
        message: `Diagram scenes exist only for C04 and C09; got component_id ${JSON.stringify(componentId)}.`,
      },
    ];
  }
  const findings: DiagramFinding[] = validateWithSchema(schema, doc).map((error) => ({
    category: "MG_SCHEMA_INVALID" as const,
    path: error.instancePath,
    message: error.message,
  }));
  if (findings.length > 0) return findings;

  const typed = doc as DiagramSceneDoc;
  findings.push(...validateDiagramSpec(typed.diagram));
  if (typed.duration_frames !== typed.diagram.timing.hold_to_frame_exclusive) {
    findings.push({
      category: "MG_TIMELINE_INVALID",
      path: "/duration_frames",
      message:
        `duration_frames ${typed.duration_frames} must equal the diagram hold end ` +
        `${typed.diagram.timing.hold_to_frame_exclusive}: the envelope and the diagram own one timeline.`,
    });
  }
  const expectedVariant =
    typed.diagram.canvas.width >= typed.diagram.canvas.height ? "landscape" : "portrait";
  if (typed.layout_variant !== expectedVariant) {
    findings.push({
      category: "MG_SCHEMA_INVALID",
      path: "/layout_variant",
      message: `layout_variant "${typed.layout_variant}" disagrees with the canvas aspect (${expectedVariant}).`,
    });
  }
  return findings;
}
