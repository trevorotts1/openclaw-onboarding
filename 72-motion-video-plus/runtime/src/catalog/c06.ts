// The C06 line trend entry (Directive Sections 7.1 and 7.2; production
// implementation MG-016).
//
// Registered by MG-016 with its closed input schema, proof contract,
// tests, and engineering attestation, per the Section 16.1 rule that a
// component is unavailable until the bundle lands together. The input
// schema mirrors the canonical contracts scene $def field for field
// (see chart-scene-schema.ts) with the C06 consts, because the
// canonical schema itself is closed on C05 and is not MG-016's to
// modify. Wiring this entry into ComponentRegistry.createDefault in
// place of the pending C06 entry is an integration step recorded in
// the MG-016 notes (registry.ts and run-catalog.ts are outside
// MG-016's file claims); the MG-016 test runner proves dispatch
// against a registry composed with this bundle.

import {
  C06_EXTRA_PROPERTIES,
  chartSceneSchema,
} from "./chart-scene-schema";
import type { ComponentEntry, RegistrationBundle } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** The MG-016 acceptance fixture scene, kept identical to
 * tests/fixtures/chart-components/line-trend-a/scene.json. The chart
 * component test suite asserts the two stay deep-equal. */
const C06_EXAMPLE_SCENE: Record<string, unknown> = {
  schema_version: "2.0",
  id: "trend-01",
  component_id: "C06",
  component_version: "1.0.0",
  engine: "remotion",
  layout_variant: "landscape",
  duration_frames: 180,
  asset_ids: [],
  data_path: "dataset.json",
  design_path: "design.json",
  copy: {
    headline: "Signups climb through the spring cohort",
    disclosure: "Illustrative example",
  },
  motion: {
    kind: "line_trend_reveal",
    start_frame: 15,
    end_frame_exclusive: 75,
    hold_to_frame_exclusive: 180,
    overshoot_data: false,
  },
  semantic_motion_assertions: [
    {
      id: "trend-bounds",
      kind: "timeline_bounds",
      subject_ids: ["trend-01"],
      frame: 75,
      expected_values: [],
      tolerance: 0,
      unit: "frames",
      evidence: ["geometry"],
    },
  ],
  annotations: [
    { id: "ann-apr", row_id: "apr", text: "April: the referral cohort lands" },
  ],
  focus_row_id: "apr",
};

export function c06Entry(): ComponentEntry {
  return {
    componentId: "C06",
    version: "1.0.0",
    name: "Line trend",
    availability: "available",
    unavailableReason: null,
    owningItem: "MG-016 (Remotion chart components C06-C08)",
    visibleChange:
      "Points appear in time order, optionally connected after their values are established",
    semanticPurpose:
      "Show change over time without inventing data: points plot in time order at their true values, and any connecting line is drawn only after the values are established, with no fabricated smoothing.",
    engines: ["remotion", "hyperframes"],
    defaultEngine: "remotion",
    inputSchema: chartSceneSchema({
      componentId: "C06",
      motionKind: "line_trend_reveal",
      engines: ["remotion", "hyperframes"],
      extraProperties: C06_EXTRA_PROPERTIES,
      extraRequired: [],
    }),
    schemaSource:
      "Catalog-layer schema built by runtime/src/catalog/chart-scene-schema.ts, mirroring references/contracts-v2.schema.json#/$defs/scene field for field with the C06 component and motion-kind consts; canonical promotion is a contracts-revision item (the canonical scene $def is closed on C05).",
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
        role: "trend_series",
        required: true,
        contract:
          "MG-015 chart dataset (runtime/src/charts): schema_version 2.0 with kind, source_note, units, domain, scale_type, missing_value_policy, and display_rounding declared",
        notes:
          "Rows are the time-ordered points. Missing values follow the dataset's declared missing_value_policy: a skipped point breaks the line and is never silently interpolated by the component.",
      },
    ],
    layoutVariants: [
      {
        id: "landscape",
        aspect: "16:9",
        description:
          "16:9 canvas; plot box and type sizes from design layouts.landscape (fixture plot 1320x600 source px).",
      },
      {
        id: "portrait",
        aspect: "9:16",
        description:
          "9:16 canvas, genuinely recomposed; geometry from design layouts.portrait (fixture plot 800x720 source px).",
      },
    ],
    timelineContract: {
      intervalConvention: "half_open",
      durationSource:
        "scene.duration_frames; the reveal occupies [motion.start_frame, motion.end_frame_exclusive) in one equal stage per point, and the final state holds to motion.hold_to_frame_exclusive",
      supportedFps: [30, 60],
      transitionHandleFields: [
        "timeline.scenes[].transition_in_frames",
        "timeline.scenes[].transition_out_frames",
      ],
      readableHold:
        "From motion.end_frame_exclusive to motion.hold_to_frame_exclusive the completed trend, its annotations, and the settled focus ring remain fully readable (fixture: frames 75 to 180 at 30 fps).",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["custom"],
          subjectSelector:
            "data-subject-id attributes on point elements (point-<row id>), measured as decoded dot centers in source pixels against chart-geometry lineStateAt; annotation boxes as annotation-<id>",
          evidence: ["geometry", "decoded_frame"],
          proofFrames: [0, 30, 45, 60, 75, 150],
          proofFrameFps: 30,
          measuredStates: [
            "frame 0: no points established; axes, labels, and context composed, no false data shown",
            "frame 30: first point established, second point growing; no connecting segment yet (connections follow established values)",
            "frame 45: three points established and joined by straight segments through their true positions",
            "frame 60: four points established, fifth growing",
            "frame 75: all six points at exact final coordinates; the polyline equals the point list exactly",
            "frame 150: final state held stable, annotation and settled focus ring visible",
          ],
        },
      ],
      minimumProof: "Time order, correct plotted points, no fabricated smoothing",
    },
    typographyRoles: [
      {
        role: "headline",
        designField: "layouts.<variant>.headline_px",
        purpose: "States the trend claim the points must support.",
      },
      {
        role: "axis_label",
        designField: "layouts.<variant>.label_px",
        purpose: "Names each time step under the plot and the axis unit.",
      },
      {
        role: "value",
        designField: "layouts.<variant>.value_px",
        purpose: "Prints exact values at the points; formatted by the dataset display rule.",
      },
      {
        role: "disclosure",
        designField: "layouts.<variant>.disclosure_px",
        purpose: "Carries the data honesty disclosure.",
      },
    ],
    variation: {
      composition:
        "Headline above a time plot; points establish themselves in time order before connections draw. Plot box, palette, and type sizes come from the job design record.",
      framing:
        "The plot occupies the design-declared box; landscape and portrait are separate design layouts, never a crop of one another.",
      typeTreatment:
        "Axis and value type sized from the design record; essential text never shrinks; long time labels wrap inside their declared band.",
      pacing:
        "One stage per point across the declared motion interval; annotations land after the reveal; the completed trend holds.",
    },
    examples: [
      {
        id: "c06-fixture-trend-01",
        kind: "scene",
        description:
          "The MG-016 acceptance fixture scene (illustrative data, honestly labeled), identical to tests/fixtures/chart-components/line-trend-a/scene.json.",
        scene: cloneJson(C06_EXAMPLE_SCENE),
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg016-chart-components",
        description:
          "MG-016 chart component tests: geometry, staged reveal, decoded proof frames, portrait variant, title-only invariance, and the Hyperframes sample.",
        evidence: "runtime/tests/run-chart-components.ts",
      },
      {
        id: "mg015-chart-contracts",
        description:
          "MG-015 chart-data contract tests for the dataset layer C06 consumes.",
        evidence: "runtime/tests/run-charts.ts",
      },
    ],
    provenance:
      "Section 7.1 row C06. Production implementation: runtime/src/remotion/components/C06LineTrend.ts with geometry in chart-geometry.ts (MG-016); Hyperframes sample generator in runtime/src/hyperframes/generators.ts. No borrowed primitives; the example data is the repository's own labeled illustrative fixture.",
  };
}

/** The governed registration bundle for C06: the entry plus the
 * engineering review attestation Section 16.1 requires. This is an
 * engineering review of the bundle, never an owner approval. */
export function c06Registration(): RegistrationBundle {
  return {
    entry: c06Entry(),
    reviewAttestation: {
      reviewer: "MG-016 worker (engineering)",
      decision: "approved",
      statement:
        "Bundle reviewed against Section 7.2: closed input schema mirroring the canonical scene shape, proof contract naming frames and measured states, registered tests in runtime/tests/run-chart-components.ts, geometry and decoded-frame evidence under tests/evidence/mg016. Coordinator verification is separate and pending at registration time.",
      reviewedAt: "2026-10-14T00:00:00Z",
    },
  };
}
