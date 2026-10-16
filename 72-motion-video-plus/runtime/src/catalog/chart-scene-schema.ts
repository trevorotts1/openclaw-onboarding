// The closed input-schema builder for the MG-016 chart components
// (C06 line trend, C07 stacked allocation, C08 waterfall).
//
// The canonical contracts schema (references/contracts-v2.schema.json)
// is closed on C05: its scene $def pins component_id "C05" and motion
// kind "linear_bar_reveal", and MG-016 does not modify the canonical
// schema. The chart components therefore register catalog-layer input
// schemas that mirror the canonical scene $def field for field (same
// required set, same closed object, same assertion $ref, which the
// registry resolves against the canonical $defs exactly as it does for
// C05), changing only the component consts and adding the
// component-specific authoring fields each chart needs. Promotion of
// these shapes into the canonical schema is a contracts-revision item,
// recorded in the MG-016 integration notes.

const ID_PATTERN = "^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$";
const PATH_PATTERN =
  "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*\\\\)[A-Za-z0-9][A-Za-z0-9._/-]*$";
const HEX_PATTERN = "^#[0-9A-Fa-f]{6}$";

export interface ChartSceneSchemaOptions {
  componentId: "C06" | "C07" | "C08";
  motionKind: string;
  /** Engines a scene for this component may name. */
  engines: string[];
  /** Extra closed properties the component's scenes carry. */
  extraProperties: Record<string, unknown>;
  /** Extra required fields beyond the canonical scene set. */
  extraRequired: string[];
}

/** Build one chart component's closed scene input schema. */
export function chartSceneSchema(
  options: ChartSceneSchemaOptions
): Record<string, unknown> {
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      schema_version: { const: "2.0" },
      id: { type: "string", pattern: ID_PATTERN },
      component_id: { const: options.componentId },
      component_version: { const: "1.0.0" },
      engine:
        options.engines.length === 1
          ? { const: options.engines[0] }
          : { enum: options.engines },
      layout_variant: { enum: ["landscape", "portrait"] },
      duration_frames: { type: "integer", minimum: 1 },
      asset_ids: {
        type: "array",
        items: { type: "string", pattern: ID_PATTERN },
        minItems: 0,
      },
      data_path: { type: "string", pattern: PATH_PATTERN },
      design_path: { type: "string", pattern: PATH_PATTERN },
      copy: {
        type: "object",
        additionalProperties: false,
        properties: {
          headline: { type: "string", minLength: 1 },
          disclosure: { type: "string", minLength: 1 },
        },
        required: ["headline", "disclosure"],
      },
      motion: {
        type: "object",
        additionalProperties: false,
        properties: {
          kind: { const: options.motionKind },
          start_frame: { type: "integer", minimum: 0 },
          end_frame_exclusive: { type: "integer", minimum: 1 },
          hold_to_frame_exclusive: { type: "integer", minimum: 1 },
          overshoot_data: { const: false },
        },
        required: [
          "kind",
          "start_frame",
          "end_frame_exclusive",
          "hold_to_frame_exclusive",
          "overshoot_data",
        ],
      },
      semantic_motion_assertions: {
        type: "array",
        items: { $ref: "#/$defs/assertion" },
        minItems: 1,
      },
      ...options.extraProperties,
    },
    required: [
      "schema_version",
      "id",
      "component_id",
      "component_version",
      "engine",
      "layout_variant",
      "duration_frames",
      "asset_ids",
      "data_path",
      "design_path",
      "copy",
      "motion",
      "semantic_motion_assertions",
      ...options.extraRequired,
    ],
  };
}

/** C06 extras: annotations pinned to data rows, and the focus row the
 * final hold settles on. */
export const C06_EXTRA_PROPERTIES: Record<string, unknown> = {
  annotations: {
    type: "array",
    maxItems: 8,
    items: {
      type: "object",
      additionalProperties: false,
      properties: {
        id: { type: "string", pattern: ID_PATTERN },
        row_id: { type: "string", pattern: ID_PATTERN },
        text: { type: "string", minLength: 1 },
      },
      required: ["id", "row_id", "text"],
    },
  },
  focus_row_id: { type: ["string", "null"], pattern: ID_PATTERN },
};

/** C07 extras: the declared segment color mapping, one hex color per
 * dataset row, in row order (Section 7.1 C07 minimum proof). */
export const C07_EXTRA_PROPERTIES: Record<string, unknown> = {
  segment_colors: {
    type: "array",
    minItems: 1,
    items: { type: "string", pattern: HEX_PATTERN },
  },
};

/** C08 extras: the declared colors for positive and negative
 * contributions. */
export const C08_EXTRA_PROPERTIES: Record<string, unknown> = {
  contribution_colors: {
    type: "object",
    additionalProperties: false,
    properties: {
      positive: { type: "string", pattern: HEX_PATTERN },
      negative: { type: "string", pattern: HEX_PATTERN },
    },
    required: ["positive", "negative"],
  },
};
