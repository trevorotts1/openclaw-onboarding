// The C07 stacked allocation entry (Directive Sections 7.1 and 7.2;
// production implementation MG-016). Registered with its closed input
// schema, proof contract, tests, and engineering attestation per
// Section 16.1; see c06.ts for the registration pattern and the
// createDefault integration note.

import {
  C07_EXTRA_PROPERTIES,
  chartSceneSchema,
} from "./chart-scene-schema";
import type { ComponentEntry, RegistrationBundle } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** The MG-016 acceptance fixture scene, kept identical to
 * tests/fixtures/chart-components/stacked-a/scene.json. */
const C07_EXAMPLE_SCENE: Record<string, unknown> = {
  schema_version: "2.0",
  id: "stack-01",
  component_id: "C07",
  component_version: "1.0.0",
  engine: "remotion",
  layout_variant: "landscape",
  duration_frames: 180,
  asset_ids: [],
  data_path: "dataset.json",
  design_path: "design.json",
  copy: {
    headline: "Where the operating budget goes",
    disclosure: "Illustrative example",
  },
  motion: {
    kind: "stacked_accumulation",
    start_frame: 15,
    end_frame_exclusive: 75,
    hold_to_frame_exclusive: 180,
    overshoot_data: false,
  },
  semantic_motion_assertions: [
    {
      id: "stack-bounds",
      kind: "timeline_bounds",
      subject_ids: ["stack-01"],
      frame: 75,
      expected_values: [],
      tolerance: 0,
      unit: "frames",
      evidence: ["geometry"],
    },
  ],
  segment_colors: ["#2F7D4F", "#C04A26", "#31597F", "#8A6D3B"],
};

export function c07Entry(): ComponentEntry {
  return {
    componentId: "C07",
    version: "1.0.0",
    name: "Stacked allocation",
    availability: "available",
    unavailableReason: null,
    owningItem: "MG-016 (Remotion chart components C06-C08)",
    visibleChange:
      "Parts accumulate into a truthful whole with labels tied to segments",
    semanticPurpose:
      "Show how parts compose a whole: segments accumulate in declared order, each labeled with its value, and the stack total is the arithmetic sum of its parts.",
    engines: ["remotion"],
    defaultEngine: "remotion",
    inputSchema: chartSceneSchema({
      componentId: "C07",
      motionKind: "stacked_accumulation",
      engines: ["remotion"],
      extraProperties: C07_EXTRA_PROPERTIES,
      extraRequired: ["segment_colors"],
    }),
    schemaSource:
      "Catalog-layer schema built by runtime/src/catalog/chart-scene-schema.ts, mirroring references/contracts-v2.schema.json#/$defs/scene field for field with the C07 consts plus the declared segment_colors mapping; canonical promotion is a contracts-revision item (the canonical scene $def is closed on C05).",
    assetRequirements: [
      {
        kind: "font",
        usage: ["embed_original"],
        role: "scene_typography",
        required: true,
        notes:
          "Resolved through the job assets font_requirements (runtime_registry alias). Substitution is forbidden: unresolved fonts fail at the component font gate.",
      },
    ],
    dataRequirements: [
      {
        role: "allocation_dataset",
        required: true,
        contract:
          "MG-015 chart dataset (runtime/src/charts) with declared_total pinning the segment sum; segment values are non-negative parts of the whole",
        notes:
          "The scene's segment_colors declare the color/label mapping, one color per row in row order; the mapping is data, never inferred. Negative segments fail the chart contract (an allocation part cannot be negative).",
      },
    ],
    layoutVariants: [
      {
        id: "landscape",
        aspect: "16:9",
        description:
          "16:9 canvas; one centered stack column with a right label rail; geometry from design layouts.landscape (fixture plot 1320x600 source px).",
      },
      {
        id: "portrait",
        aspect: "9:16",
        description:
          "9:16 canvas, genuinely recomposed; geometry from design layouts.portrait.",
      },
    ],
    timelineContract: {
      intervalConvention: "half_open",
      durationSource:
        "scene.duration_frames; the accumulation occupies [motion.start_frame, motion.end_frame_exclusive) in one equal stage per segment, and the completed whole holds to motion.hold_to_frame_exclusive",
      supportedFps: [30, 60],
      transitionHandleFields: [
        "timeline.scenes[].transition_in_frames",
        "timeline.scenes[].transition_out_frames",
      ],
      readableHold:
        "From motion.end_frame_exclusive to motion.hold_to_frame_exclusive the completed stack, every segment labeled with value and units, and the printed total remain fully readable (fixture: frames 75 to 180 at 30 fps).",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["custom"],
          subjectSelector:
            "data-subject-id attributes on segment elements (segment-<row id>), measured as decoded color runs along the stack column against chart-geometry stackedStateAt; the total as stack-total",
          evidence: ["geometry", "decoded_frame"],
          proofFrames: [0, 45, 75, 150],
          proofFrameFps: 30,
          measuredStates: [
            "frame 0: no segments shown; baseline and context composed, no false data",
            "frame 45: the first two segments at full truthful heights, later segments absent",
            "frame 75: all segments at exact final heights summing to the printed total; the zero-height segment, when present, reads as a marker line at its truthful level",
            "frame 150: final state held stable",
          ],
        },
      ],
      minimumProof: "Segment values, sums, units, and color/label mapping",
    },
    typographyRoles: [
      {
        role: "headline",
        designField: "layouts.<variant>.headline_px",
        purpose: "States what whole is being allocated.",
      },
      {
        role: "segment_label",
        designField: "layouts.<variant>.label_px",
        purpose: "Names each segment beside it and prints its value with units.",
      },
      {
        role: "value",
        designField: "layouts.<variant>.value_px",
        purpose: "Prints the stack total above the column; formatted by the dataset display rule.",
      },
      {
        role: "disclosure",
        designField: "layouts.<variant>.disclosure_px",
        purpose: "Carries the data honesty disclosure.",
      },
    ],
    variation: {
      composition:
        "One accumulating stack column with a label rail; segment colors, palette, plot box, and type sizes come from the scene and design records.",
      framing:
        "The full whole is in frame from the first segment so accumulation reads against the total; landscape and portrait are separate design layouts.",
      typeTreatment:
        "Labels and values sized from the design record; essential text never shrinks; long segment names wrap inside the rail.",
      pacing:
        "Segments accumulate one at a time in declared order inside their final bands, so boundaries and labels never move; the completed whole holds.",
    },
    examples: [
      {
        id: "c07-fixture-stack-01",
        kind: "scene",
        description:
          "The MG-016 acceptance fixture scene (illustrative data, honestly labeled), identical to tests/fixtures/chart-components/stacked-a/scene.json.",
        scene: cloneJson(C07_EXAMPLE_SCENE),
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg016-chart-components",
        description:
          "MG-016 chart component tests: segment geometry on two datasets (including a zero segment and long names), staged accumulation, decoded proof frames.",
        evidence: "runtime/tests/run-chart-components.ts",
      },
      {
        id: "mg015-chart-contracts",
        description:
          "MG-015 chart-data contract tests, including declared-total arithmetic, for the dataset layer C07 consumes.",
        evidence: "runtime/tests/run-charts.ts",
      },
    ],
    provenance:
      "Section 7.1 row C07. Production implementation: runtime/src/remotion/components/C07StackedAllocation.ts with geometry in chart-geometry.ts (MG-016). No borrowed primitives; the example data is the repository's own labeled illustrative fixture.",
  };
}

/** The governed registration bundle for C07 (entry plus engineering
 * attestation, Section 16.1). Engineering review only, never an owner
 * approval. */
export function c07Registration(): RegistrationBundle {
  return {
    entry: c07Entry(),
    reviewAttestation: {
      reviewer: "MG-016 worker (engineering)",
      decision: "approved",
      statement:
        "Bundle reviewed against Section 7.2: closed input schema with the declared segment color mapping required, proof contract naming frames and measured states, registered tests in runtime/tests/run-chart-components.ts, geometry and decoded-frame evidence under tests/evidence/mg016. Coordinator verification is separate and pending at registration time.",
      reviewedAt: "2026-10-14T00:00:00Z",
    },
  };
}
