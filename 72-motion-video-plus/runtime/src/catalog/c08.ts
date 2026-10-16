// The C08 waterfall explanation entry (Directive Sections 7.1 and
// 7.2; production implementation MG-016). Registered with its closed
// input schema, proof contract, tests, and engineering attestation
// per Section 16.1; see c06.ts for the registration pattern and the
// createDefault integration note.

import {
  C08_EXTRA_PROPERTIES,
  chartSceneSchema,
} from "./chart-scene-schema";
import type { ComponentEntry, RegistrationBundle } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** The MG-016 acceptance fixture scene, kept identical to
 * tests/fixtures/chart-components/waterfall-a/scene.json. */
const C08_EXAMPLE_SCENE: Record<string, unknown> = {
  schema_version: "2.0",
  id: "falls-01",
  component_id: "C08",
  component_version: "1.0.0",
  engine: "remotion",
  layout_variant: "landscape",
  duration_frames: 180,
  asset_ids: [],
  data_path: "dataset.json",
  design_path: "design.json",
  copy: {
    headline: "From starting revenue to the quarter end",
    disclosure: "Illustrative example",
  },
  motion: {
    kind: "waterfall_steps",
    start_frame: 15,
    end_frame_exclusive: 75,
    hold_to_frame_exclusive: 180,
    overshoot_data: false,
  },
  semantic_motion_assertions: [
    {
      id: "falls-bounds",
      kind: "timeline_bounds",
      subject_ids: ["falls-01"],
      frame: 75,
      expected_values: [],
      tolerance: 0,
      unit: "frames",
      evidence: ["geometry"],
    },
  ],
  contribution_colors: { positive: "#2F7D4F", negative: "#B03A2E" },
};

export function c08Entry(): ComponentEntry {
  return {
    componentId: "C08",
    version: "1.0.0",
    name: "Waterfall explanation",
    availability: "available",
    unavailableReason: null,
    owningItem: "MG-016 (Remotion chart components C06-C08)",
    visibleChange:
      "Signed contributions move a starting value to an ending value",
    semanticPurpose:
      "Explain a net change arithmetically: each signed contribution steps the running total visibly, connectors preserve the running level, and the ending value equals the start plus the contributions.",
    engines: ["remotion"],
    defaultEngine: "remotion",
    inputSchema: chartSceneSchema({
      componentId: "C08",
      motionKind: "waterfall_steps",
      engines: ["remotion"],
      extraProperties: C08_EXTRA_PROPERTIES,
      extraRequired: ["contribution_colors"],
    }),
    schemaSource:
      "Catalog-layer schema built by runtime/src/catalog/chart-scene-schema.ts, mirroring references/contracts-v2.schema.json#/$defs/scene field for field with the C08 consts plus the declared contribution_colors; canonical promotion is a contracts-revision item (the canonical scene $def is closed on C05).",
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
        role: "waterfall_dataset",
        required: true,
        contract:
          "MG-015 chart dataset (runtime/src/charts); row 0 is the starting value, later rows are signed contributions, and declared_total pins the computed ending value (which equals the sum of all rows under this convention)",
        notes:
          "Every running level must lie inside the declared domain; a level outside it would be drawn clipped, so the geometry layer refuses it. The ending column is computed, never a data row.",
      },
    ],
    layoutVariants: [
      {
        id: "landscape",
        aspect: "16:9",
        description:
          "16:9 canvas; stepped columns across the plot with connectors at the running levels; geometry from design layouts.landscape (fixture plot 1280x600 source px).",
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
        "scene.duration_frames; the walk occupies [motion.start_frame, motion.end_frame_exclusive) in one equal stage per step (start, each contribution, and the computed total), and the ending value holds to motion.hold_to_frame_exclusive",
      supportedFps: [30, 60],
      transitionHandleFields: [
        "timeline.scenes[].transition_in_frames",
        "timeline.scenes[].transition_out_frames",
      ],
      readableHold:
        "From motion.end_frame_exclusive to motion.hold_to_frame_exclusive the ending column, equal to the start plus all contributions, and every step label remain fully readable (fixture: frames 75 to 180 at 30 fps).",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["custom"],
          subjectSelector:
            "data-subject-id attributes on step columns (step-<row id>, step-total), measured as decoded column extents against chart-geometry waterfallStateAt; connectors measured at their declared running levels",
          evidence: ["geometry", "decoded_frame"],
          proofFrames: [0, 45, 75, 150],
          proofFrameFps: 30,
          measuredStates: [
            "frame 0: no columns shown; zero line and context composed, no false data",
            "frame 45: the start column and the first contribution at full truthful extents, joined by the connector at the running level",
            "frame 75: every step at its exact final extent; the ending column's height equals the start plus the signed contributions",
            "frame 150: final state held stable",
          ],
        },
      ],
      minimumProof:
        "Arithmetic equality and correct connector/baseline behavior",
    },
    typographyRoles: [
      {
        role: "headline",
        designField: "layouts.<variant>.headline_px",
        purpose: "States the change being explained.",
      },
      {
        role: "step_label",
        designField: "layouts.<variant>.label_px",
        purpose: "Names each contribution under its step.",
      },
      {
        role: "value",
        designField: "layouts.<variant>.value_px",
        purpose: "Prints signed step values and start/end totals; formatted by the dataset display rule.",
      },
      {
        role: "disclosure",
        designField: "layouts.<variant>.disclosure_px",
        purpose: "Carries the data honesty disclosure.",
      },
    ],
    variation: {
      composition:
        "Stepped columns across the plot with connectors at the running level; colors for gains and losses are declared in the scene, the start and end columns take the design accent.",
      framing:
        "Baseline and scale are shared across all steps so height differences are truthful; landscape and portrait are separate design layouts.",
      typeTreatment:
        "Step labels and signed values sized from the design record; essential text never shrinks.",
      pacing:
        "One contribution lands at a time in declared order; the ending value holds.",
    },
    examples: [
      {
        id: "c08-fixture-falls-01",
        kind: "scene",
        description:
          "The MG-016 acceptance fixture scene (illustrative data, honestly labeled), identical to tests/fixtures/chart-components/waterfall-a/scene.json.",
        scene: cloneJson(C08_EXAMPLE_SCENE),
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg016-chart-components",
        description:
          "MG-016 chart component tests: waterfall step geometry on two datasets (including a zero-crossing running total and a zero contribution), arithmetic equality, connector levels, decoded proof frames.",
        evidence: "runtime/tests/run-chart-components.ts",
      },
      {
        id: "mg015-chart-contracts",
        description:
          "MG-015 chart-data contract tests, including declared-total arithmetic, for the dataset layer C08 consumes.",
        evidence: "runtime/tests/run-charts.ts",
      },
    ],
    provenance:
      "Section 7.1 row C08. Production implementation: runtime/src/remotion/components/C08Waterfall.ts with geometry in chart-geometry.ts (MG-016). No borrowed primitives; the example data is the repository's own labeled illustrative fixture.",
  };
}

/** The governed registration bundle for C08 (entry plus engineering
 * attestation, Section 16.1). Engineering review only, never an owner
 * approval. */
export function c08Registration(): RegistrationBundle {
  return {
    entry: c08Entry(),
    reviewAttestation: {
      reviewer: "MG-016 worker (engineering)",
      decision: "approved",
      statement:
        "Bundle reviewed against Section 7.2: closed input schema with the declared contribution colors required, proof contract naming frames and measured states, registered tests in runtime/tests/run-chart-components.ts, geometry and decoded-frame evidence under tests/evidence/mg016. Coordinator verification is separate and pending at registration time.",
      reviewedAt: "2026-10-14T00:00:00Z",
    },
  };
}
