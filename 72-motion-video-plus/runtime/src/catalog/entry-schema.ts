// The catalog entry schema: the closed JSON Schema every ComponentEntry
// must satisfy before the registry accepts it (Directive MG-018, Sections
// 7.2 and 16.1). The availability conditionals encode the Section 16.1
// registration rule structurally: an "available" entry must carry a
// non-null input schema, a non-null proof contract, and at least one
// registered test; an "unavailable" entry must carry none of the bundle
// and must state its reason.

import Ajv2020, { type ValidateFunction } from "ajv/dist/2020";

const ID_PATTERN = "^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$";

export const CATALOG_ENTRY_SCHEMA: Record<string, unknown> = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  title: "Motion component catalog entry",
  type: "object",
  additionalProperties: false,
  required: [
    "componentId",
    "version",
    "name",
    "availability",
    "unavailableReason",
    "owningItem",
    "visibleChange",
    "semanticPurpose",
    "engines",
    "defaultEngine",
    "inputSchema",
    "schemaSource",
    "assetRequirements",
    "dataRequirements",
    "layoutVariants",
    "timelineContract",
    "proofContract",
    "typographyRoles",
    "variation",
    "examples",
    "tests",
    "provenance",
  ],
  properties: {
    componentId: { type: "string", pattern: ID_PATTERN },
    version: { type: "string", pattern: "^[0-9]+\\.[0-9]+\\.[0-9]+$" },
    name: { type: "string", minLength: 1 },
    availability: { enum: ["available", "unavailable"] },
    unavailableReason: { type: ["string", "null"] },
    owningItem: { type: "string", minLength: 1 },
    visibleChange: { type: "string", minLength: 1 },
    semanticPurpose: { type: "string", minLength: 1 },
    engines: {
      type: "array",
      minItems: 1,
      uniqueItems: true,
      items: { enum: ["remotion", "hyperframes"] },
    },
    defaultEngine: {
      enum: ["remotion", "hyperframes", "either", "qualified-native-integration"],
    },
    inputSchema: { type: ["object", "null"] },
    schemaSource: { type: ["string", "null"] },
    assetRequirements: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["kind", "usage", "role", "required", "notes"],
        properties: {
          kind: { enum: ["image", "video", "audio", "font", "svg"] },
          usage: {
            type: "array",
            minItems: 1,
            uniqueItems: true,
            items: {
              enum: ["embed_original", "approved_derivative", "reference_only"],
            },
          },
          role: { type: "string", minLength: 1 },
          required: { type: "boolean" },
          notes: { type: "string" },
        },
      },
    },
    dataRequirements: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["role", "required", "contract", "notes"],
        properties: {
          role: { type: "string", minLength: 1 },
          required: { type: "boolean" },
          contract: { type: "string", minLength: 1 },
          notes: { type: "string" },
        },
      },
    },
    layoutVariants: {
      type: "array",
      minItems: 1,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["id", "aspect", "description"],
        properties: {
          id: { type: "string", minLength: 1 },
          aspect: { enum: ["16:9", "9:16"] },
          description: { type: "string", minLength: 1 },
        },
      },
    },
    timelineContract: {
      type: "object",
      additionalProperties: false,
      required: [
        "intervalConvention",
        "durationSource",
        "supportedFps",
        "transitionHandleFields",
        "readableHold",
        "audioCueBehavior",
      ],
      properties: {
        intervalConvention: { const: "half_open" },
        durationSource: { type: "string", minLength: 1 },
        supportedFps: {
          type: "array",
          minItems: 1,
          items: { type: "integer", minimum: 1 },
        },
        transitionHandleFields: {
          type: "array",
          items: { type: "string", minLength: 1 },
        },
        readableHold: { type: "string", minLength: 1 },
        audioCueBehavior: { type: "string", minLength: 1 },
      },
    },
    proofContract: {
      type: ["object", "null"],
      additionalProperties: false,
      required: ["selectors", "minimumProof"],
      properties: {
        selectors: {
          type: "array",
          minItems: 1,
          items: {
            type: "object",
            additionalProperties: false,
            required: [
              "assertionKinds",
              "subjectSelector",
              "evidence",
              "proofFrames",
              "proofFrameFps",
              "measuredStates",
            ],
            properties: {
              assertionKinds: {
                type: "array",
                minItems: 1,
                items: { type: "string", minLength: 1 },
              },
              subjectSelector: { type: "string", minLength: 1 },
              evidence: {
                type: "array",
                minItems: 1,
                uniqueItems: true,
                items: {
                  enum: ["geometry", "decoded_frame", "full_fps_clip"],
                },
              },
              proofFrames: {
                type: "array",
                items: { type: "integer", minimum: 0 },
              },
              proofFrameFps: { type: ["integer", "null"], minimum: 1 },
              measuredStates: {
                type: "array",
                minItems: 1,
                items: { type: "string", minLength: 1 },
              },
            },
          },
        },
        minimumProof: { type: "string", minLength: 1 },
      },
    },
    motionProof: {
      type: ["object", "null"],
      additionalProperties: false,
      required: ["subjects", "measurement", "transformation", "depthPolicy"],
      properties: {
        subjects: { type: "string", minLength: 1 },
        measurement: { type: "string", minLength: 1 },
        transformation: { type: "string", minLength: 1 },
        depthPolicy: {
          enum: ["not_claimed", "requires_occlusion_or_depth_evidence"],
        },
      },
    },
    typographyRoles: {
      type: "array",
      minItems: 1,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["role", "designField", "purpose"],
        properties: {
          role: { type: "string", minLength: 1 },
          designField: { type: ["string", "null"] },
          purpose: { type: "string", minLength: 1 },
        },
      },
    },
    variation: {
      type: "object",
      additionalProperties: false,
      required: ["composition", "framing", "typeTreatment", "pacing"],
      properties: {
        composition: { type: "string", minLength: 1 },
        framing: { type: "string", minLength: 1 },
        typeTreatment: { type: "string", minLength: 1 },
        pacing: { type: "string", minLength: 1 },
      },
    },
    examples: {
      type: "array",
      minItems: 1,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["id", "kind", "description", "scene", "beat"],
        properties: {
          id: { type: "string", minLength: 1 },
          kind: { enum: ["scene", "storyboard_beat"] },
          description: { type: "string", minLength: 1 },
          scene: { type: ["object", "null"] },
          beat: { type: ["object", "null"] },
        },
      },
    },
    tests: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["id", "description", "evidence"],
        properties: {
          id: { type: "string", minLength: 1 },
          description: { type: "string", minLength: 1 },
          evidence: { type: "string", minLength: 1 },
        },
      },
    },
    provenance: { type: "string", minLength: 1 },
  },
  allOf: [
    {
      if: {
        type: "object",
        properties: { availability: { const: "available" } },
        required: ["availability"],
      },
      then: {
        properties: {
          inputSchema: { type: "object" },
          schemaSource: { type: "string", minLength: 1 },
          proofContract: { type: "object" },
          tests: { minItems: 1 },
          unavailableReason: { type: "null" },
        },
      },
    },
    {
      if: {
        type: "object",
        properties: { availability: { const: "unavailable" } },
        required: ["availability"],
      },
      then: {
        properties: {
          inputSchema: { type: "null" },
          proofContract: { type: "null" },
          unavailableReason: { type: "string", minLength: 1 },
        },
      },
    },
  ],
};

let compiledEntryValidator: ValidateFunction | null = null;

function entryValidator(): ValidateFunction {
  if (compiledEntryValidator === null) {
    const ajv = new Ajv2020({ allErrors: true, strict: false });
    compiledEntryValidator = ajv.compile(CATALOG_ENTRY_SCHEMA);
  }
  return compiledEntryValidator;
}

/**
 * Validate one catalog entry against CATALOG_ENTRY_SCHEMA. Returns a list
 * of human-readable problems; an empty list means the entry is well-formed.
 */
export function validateCatalogEntry(entry: unknown): string[] {
  const validate = entryValidator();
  if (validate(entry)) {
    return [];
  }
  return (validate.errors ?? []).map(
    (error) =>
      `${error.instancePath || "/"} ${error.message ?? error.keyword}`.trim()
  );
}
