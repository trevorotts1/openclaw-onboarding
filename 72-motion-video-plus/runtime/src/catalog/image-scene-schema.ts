// The closed input-schema builder for the MG-044 image components
// (C01 image-led statement, C02 product-detail demonstration, C03
// before/after comparison).
//
// These components do not consume the canonical contracts scene
// shape: their production scene documents are the Hyperframes
// adapter's registered spec shapes (schema_version "mg005-1" for C01,
// authored by MG-005; "mg044-1" for C02 and C03, authored by MG-044
// through the same generator seam). The canonical contracts scene
// $def is closed on C05 and is not MG-044's to widen, so, exactly as
// MG-016 did for the chart components, these schemas live at the
// catalog layer and describe the shapes the production adapter
// actually renders, field for field against the generator spec types
// in runtime/src/hyperframes/generators.ts. The catalog test suite
// asserts each registered example validates, each schema is closed,
// and mutations (extra keys, wrong component, wrong motion kind,
// wrong variant) are refused.

const ID_PATTERN = "^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$";
const PATH_PATTERN =
  "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*\\\\)[A-Za-z0-9][A-Za-z0-9._/-]*$";
const HEX_PATTERN = "^#[0-9A-Fa-f]{6}$";
const SHA256_PATTERN = "^[0-9a-f]{64}$";

const BOX = {
  type: "object",
  additionalProperties: false,
  properties: {
    x: { type: "integer", minimum: 0 },
    y: { type: "integer", minimum: 0 },
    width: { type: "integer", minimum: 1 },
    height: { type: "integer", minimum: 1 },
  },
  required: ["x", "y", "width", "height"],
};

const SIZE = {
  type: "object",
  additionalProperties: false,
  properties: {
    width: { type: "integer", minimum: 1 },
    height: { type: "integer", minimum: 1 },
  },
  required: ["width", "height"],
};

const COLORS = {
  type: "object",
  additionalProperties: false,
  properties: {
    background: { type: "string", pattern: HEX_PATTERN },
    ink: { type: "string", pattern: HEX_PATTERN },
    accent: { type: "string", pattern: HEX_PATTERN },
  },
  required: ["background", "ink", "accent"],
};

const DESIGN = {
  type: "object",
  additionalProperties: false,
  properties: { colors: COLORS },
  required: ["colors"],
};

function fractionAssertion(kind: string): Record<string, unknown> {
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      id: { type: "string", pattern: ID_PATTERN },
      kind: { const: kind },
      frame: { type: "integer", minimum: 0 },
      min_fraction: { type: "number", minimum: 0, maximum: 1 },
      max_fraction: { type: "number", minimum: 0, maximum: 1 },
    },
    required: ["id", "kind", "frame", "min_fraction", "max_fraction"],
  };
}

function motionBlock(kind: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      kind: { const: kind },
      start_frame: { type: "integer", minimum: 0 },
      end_frame_exclusive: { type: "integer", minimum: 1 },
      hold_to_frame_exclusive: { type: "integer", minimum: 1 },
      ...extra,
    },
    required: [
      "kind",
      "start_frame",
      "end_frame_exclusive",
      "hold_to_frame_exclusive",
      ...Object.keys(extra),
    ],
  };
}

const SUBJECT = {
  type: "object",
  additionalProperties: false,
  properties: {
    id: { type: "string", pattern: ID_PATTERN },
    box: BOX,
    measure_color: { type: "string", pattern: HEX_PATTERN },
  },
  required: ["id", "box", "measure_color"],
};

const CORE_REQUIRED = [
  "schema_version",
  "id",
  "component_id",
  "component_version",
  "engine",
  "duration_frames",
  "font_ref",
  "canvas",
  "design",
];

/** The closed catalog input schema for C01 (MG-005 spec shapes: the
 * mask-reveal scene and the nested-detail variant). */
export function c01SceneSchema(): Record<string, unknown> {
  const reveal = {
    type: "object",
    additionalProperties: false,
    properties: {
      schema_version: { const: "mg005-1" },
      id: { type: "string", pattern: ID_PATTERN },
      component_id: { const: "C01" },
      component_version: { const: "1.0.0" },
      engine: { const: "hyperframes" },
      duration_frames: { type: "integer", minimum: 1 },
      asset_file: { type: "string", pattern: PATH_PATTERN },
      asset_sha256: { type: "string", pattern: SHA256_PATTERN },
      font_ref: { type: "string", pattern: ID_PATTERN },
      canvas: SIZE,
      design: DESIGN,
      subject: SUBJECT,
      copy: {
        type: "object",
        additionalProperties: false,
        properties: {
          headline: { type: "string", minLength: 1 },
          caption: { type: "string", minLength: 1 },
          fixture_label: { type: "string", minLength: 1 },
        },
        required: ["headline", "caption", "fixture_label"],
      },
      headline_px: { type: "integer", minimum: 1 },
      caption_px: { type: "integer", minimum: 1 },
      motion: motionBlock("mask_reveal"),
      semantic_motion_assertions: {
        type: "array",
        minItems: 1,
        items: fractionAssertion("subject_reveal"),
      },
    },
    required: [
      ...CORE_REQUIRED,
      "asset_file",
      "subject",
      "copy",
      "headline_px",
      "caption_px",
      "motion",
      "semantic_motion_assertions",
    ],
  };
  const nested = {
    type: "object",
    additionalProperties: false,
    properties: {
      schema_version: { const: "mg005-1" },
      id: { type: "string", pattern: ID_PATTERN },
      component_id: { const: "C01" },
      component_version: { const: "1.0.0" },
      variant: { const: "nested_detail" },
      engine: { const: "hyperframes" },
      duration_frames: { type: "integer", minimum: 1 },
      asset_file: { type: "string", pattern: PATH_PATTERN },
      asset_sha256: { type: "string", pattern: SHA256_PATTERN },
      font_ref: { type: "string", pattern: ID_PATTERN },
      canvas: SIZE,
      design: DESIGN,
      subject: SUBJECT,
      detail: {
        type: "object",
        additionalProperties: false,
        properties: {
          box: BOX,
          start_frame: { type: "integer", minimum: 0 },
          measure_color: { type: "string", pattern: HEX_PATTERN },
          variables: {
            type: "object",
            additionalProperties: false,
            properties: {
              label: { type: "string", minLength: 1 },
              value: { type: "string", minLength: 1 },
            },
            required: ["label", "value"],
          },
        },
        required: ["box", "start_frame", "measure_color", "variables"],
      },
      copy: {
        type: "object",
        additionalProperties: false,
        properties: {
          headline: { type: "string", minLength: 1 },
          fixture_label: { type: "string", minLength: 1 },
        },
        required: ["headline", "fixture_label"],
      },
      headline_px: { type: "integer", minimum: 1 },
    },
    required: [
      ...CORE_REQUIRED,
      "variant",
      "asset_file",
      "subject",
      "detail",
      "copy",
      "headline_px",
    ],
  };
  return { anyOf: [reveal, nested] };
}

/** The closed catalog input schema for C02 (MG-044 detail_closeup
 * spec shape). */
export function c02SceneSchema(): Record<string, unknown> {
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      schema_version: { const: "mg044-1" },
      id: { type: "string", pattern: ID_PATTERN },
      component_id: { const: "C02" },
      component_version: { const: "1.0.0" },
      variant: { const: "detail_closeup" },
      engine: { const: "hyperframes" },
      duration_frames: { type: "integer", minimum: 1 },
      asset_file: { type: "string", pattern: PATH_PATTERN },
      asset_sha256: { type: "string", pattern: SHA256_PATTERN },
      font_ref: { type: "string", pattern: ID_PATTERN },
      canvas: SIZE,
      design: DESIGN,
      product: {
        type: "object",
        additionalProperties: false,
        properties: { box: BOX, source: SIZE },
        required: ["box", "source"],
      },
      detail: {
        type: "object",
        additionalProperties: false,
        properties: {
          point: {
            type: "object",
            additionalProperties: false,
            properties: {
              x: { type: "number", minimum: 0, maximum: 1 },
              y: { type: "number", minimum: 0, maximum: 1 },
            },
            required: ["x", "y"],
          },
          measure_color: { type: "string", pattern: HEX_PATTERN },
        },
        required: ["point", "measure_color"],
      },
      zoom: {
        type: "object",
        additionalProperties: false,
        properties: {
          max_zoom: { type: "number", minimum: 1 },
          start_frame: { type: "integer", minimum: 0 },
          end_frame_exclusive: { type: "integer", minimum: 1 },
          hold_to_frame_exclusive: { type: "integer", minimum: 1 },
          output: BOX,
        },
        required: [
          "max_zoom",
          "start_frame",
          "end_frame_exclusive",
          "hold_to_frame_exclusive",
          "output",
        ],
      },
      copy: {
        type: "object",
        additionalProperties: false,
        properties: {
          headline: { type: "string", minLength: 1 },
          annotation_label: { type: "string", minLength: 1 },
          caption: { type: "string", minLength: 1 },
          fixture_label: { type: "string", minLength: 1 },
        },
        required: ["headline", "annotation_label", "caption", "fixture_label"],
      },
      headline_px: { type: "integer", minimum: 1 },
      caption_px: { type: "integer", minimum: 1 },
      annotation_px: { type: "integer", minimum: 1 },
      semantic_motion_assertions: {
        type: "array",
        minItems: 1,
        items: fractionAssertion("closeup_detail_fraction"),
      },
    },
    required: [
      ...CORE_REQUIRED,
      "variant",
      "asset_file",
      "product",
      "detail",
      "zoom",
      "copy",
      "headline_px",
      "caption_px",
      "annotation_px",
      "semantic_motion_assertions",
    ],
  };
}

/** The closed catalog input schema for C03 (MG-044 wipe_reveal spec
 * shape). */
export function c03SceneSchema(): Record<string, unknown> {
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      schema_version: { const: "mg044-1" },
      id: { type: "string", pattern: ID_PATTERN },
      component_id: { const: "C03" },
      component_version: { const: "1.0.0" },
      variant: { const: "wipe_reveal" },
      engine: { const: "hyperframes" },
      duration_frames: { type: "integer", minimum: 1 },
      before_file: { type: "string", pattern: PATH_PATTERN },
      before_sha256: { type: "string", pattern: SHA256_PATTERN },
      after_file: { type: "string", pattern: PATH_PATTERN },
      after_sha256: { type: "string", pattern: SHA256_PATTERN },
      font_ref: { type: "string", pattern: ID_PATTERN },
      canvas: SIZE,
      design: DESIGN,
      subject: SUBJECT,
      copy: {
        type: "object",
        additionalProperties: false,
        properties: {
          headline: { type: "string", minLength: 1 },
          before_label: { type: "string", minLength: 1 },
          after_label: { type: "string", minLength: 1 },
          caption: { type: "string", minLength: 1 },
          fixture_label: { type: "string", minLength: 1 },
        },
        required: ["headline", "before_label", "after_label", "caption", "fixture_label"],
      },
      headline_px: { type: "integer", minimum: 1 },
      caption_px: { type: "integer", minimum: 1 },
      label_px: { type: "integer", minimum: 1 },
      motion: motionBlock("wipe_reveal", {
        rest_fraction: { type: "number", exclusiveMinimum: 0, maximum: 1 },
      }),
      semantic_motion_assertions: {
        type: "array",
        minItems: 1,
        items: fractionAssertion("state_fraction"),
      },
    },
    required: [
      ...CORE_REQUIRED,
      "variant",
      "before_file",
      "after_file",
      "subject",
      "copy",
      "headline_px",
      "caption_px",
      "label_px",
      "motion",
      "semantic_motion_assertions",
    ],
  };
}
