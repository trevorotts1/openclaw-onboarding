// The C05 bar comparison entry: the catalog's first production component
// (Directive Sections 7.1 and 17.2; production implementation MG-006).
//
// The input schema is DERIVED at load time from the canonical contracts
// schema ($defs/scene in references/contracts-v2.schema.json), never
// hand-copied. Parity with the shipped MG-007 validators therefore holds
// by construction, and runtime/tests/run-catalog.ts additionally proves
// it empirically over a shared accept/reject corpus run against both the
// catalog and the shipped TypeScript and Python validators.

import { loadContractsSchema } from "../validation/validate";
import type { ComponentEntry } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** The shipped fixture scene, kept identical to
 * tests/fixtures/modes/powerpoint_graphic/scenes/bar-01.json. The catalog
 * test suite asserts the two stay deep-equal. */
const C05_EXAMPLE_SCENE: Record<string, unknown> = {
  schema_version: "2.0",
  id: "bar-01",
  component_id: "C05",
  component_version: "1.0.0",
  engine: "remotion",
  layout_variant: "landscape",
  duration_frames: 180,
  asset_ids: [],
  data_path: "data/bars.json",
  design_path: "design.json",
  copy: {
    headline: "Compare the three groups",
    disclosure: "Illustrative example",
  },
  motion: {
    kind: "linear_bar_reveal",
    start_frame: 15,
    end_frame_exclusive: 75,
    hold_to_frame_exclusive: 180,
    overshoot_data: false,
  },
  semantic_motion_assertions: [
    {
      id: "half-reveal",
      kind: "bar_widths",
      subject_ids: ["bar-a", "bar-b", "bar-c"],
      frame: 45,
      expected_values: [240, 360, 600],
      tolerance: 1,
      unit: "source_px",
      evidence: ["geometry", "decoded_frame", "full_fps_clip"],
    },
    {
      id: "final-ratios",
      kind: "bar_widths",
      subject_ids: ["bar-a", "bar-b", "bar-c"],
      frame: 75,
      expected_values: [480, 720, 1200],
      tolerance: 1,
      unit: "source_px",
      evidence: ["geometry", "decoded_frame"],
    },
  ],
};

export function c05Entry(): ComponentEntry {
  const contracts = loadContractsSchema();
  const sceneDef = (contracts as { $defs: Record<string, unknown> }).$defs
    .scene;
  return {
    componentId: "C05",
    version: "1.0.0",
    name: "Bar comparison",
    availability: "available",
    unavailableReason: null,
    owningItem:
      "MG-006 (production Remotion component); catalog registration MG-018; native Hyperframes build owned by MG-016",
    visibleChange:
      "Bar lengths grow or transform to the supplied values with a stable comparison scale",
    semanticPurpose:
      "Compare magnitudes truthfully: bar lengths are linear in the supplied values on one stable scale, so a viewer can judge ratios at a glance and read exact values and labels at the final hold.",
    engines: ["remotion", "hyperframes"],
    defaultEngine: "remotion",
    inputSchema: cloneJson(sceneDef) as Record<string, unknown>,
    schemaSource:
      "references/contracts-v2.schema.json#/$defs/scene, derived at load time from the canonical schema (never hand-copied)",
    assetRequirements: [
      {
        kind: "font",
        usage: ["embed_original"],
        role: "scene_typography",
        required: true,
        notes:
          "Resolved through the job assets font_requirements (runtime_registry alias). Substitution is forbidden: unresolved fonts fail MG_FONT_UNRESOLVED at the adapter layer.",
      },
    ],
    dataRequirements: [
      {
        role: "comparison_dataset",
        required: true,
        contract:
          "contracts-v2 $defs/dataset; the MG-015 chart contract layer (missing-value policy, display rounding, declared totals) applies on top",
        notes:
          "Referenced by scene data_path. Values must be finite; the domain must be two finite strictly increasing endpoints.",
      },
    ],
    layoutVariants: [
      {
        id: "landscape",
        aspect: "16:9",
        description:
          "16:9 canvas; geometry from design layouts.landscape (fixture plot width 1200 source px).",
      },
      {
        id: "portrait",
        aspect: "9:16",
        description:
          "9:16 canvas, genuinely recomposed; geometry from design layouts.portrait (fixture plot width 740 source px).",
      },
    ],
    timelineContract: {
      intervalConvention: "half_open",
      durationSource:
        "scene.duration_frames; the reveal occupies [motion.start_frame, motion.end_frame_exclusive) and the final state holds to motion.hold_to_frame_exclusive",
      supportedFps: [30, 60],
      transitionHandleFields: [
        "timeline.scenes[].transition_in_frames",
        "timeline.scenes[].transition_out_frames",
      ],
      readableHold:
        "From motion.end_frame_exclusive to motion.hold_to_frame_exclusive the final values and labels remain fully readable (fixture: frames 75 to 180 at 30 fps).",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["bar_widths"],
          subjectSelector:
            "data-subject-id attributes on bar elements (bar-<row id>), measured as source-pixel widths in the component coordinate space",
          evidence: ["geometry", "decoded_frame", "full_fps_clip"],
          proofFrames: [0, 15, 45, 75, 150, 179],
          proofFrameFps: 30,
          measuredStates: [
            "frame 0: widths 0, 0, 0; context composed, no false data shown",
            "frame 15: widths 0, 0, 0; the reveal begins",
            "frame 45: landscape 240, 360, 600 and portrait 148, 222, 370; half reveal with ratios preserved",
            "frame 75: landscape 480, 720, 1200 and portrait 296, 444, 740; full truthful values",
            "frames 150 and 179: final widths held stable",
          ],
        },
      ],
      minimumProof:
        "Intermediate geometry and exact final ratios/labels (Section 7.1).",
    },
    motionProof: {
      subjects:
        "data_marks: one bar per dataset row, identified by the scene's bar subject ids (bar-<row id>)",
      measurement:
        "accent_run_extent: the contiguous accent run inside each bar's row region on the decoded frame, checked against the MG-015 chart-scale derivation and the component's instrumented widths",
      transformation: "linear_reveal",
      depthPolicy: "not_claimed",
    },
    typographyRoles: [
      {
        role: "headline",
        designField: "layouts.<variant>.headline_px",
        purpose: "States the comparison the viewer is making.",
      },
      {
        role: "category_label",
        designField: "layouts.<variant>.label_px",
        purpose: "Names each bar's category in the left rail.",
      },
      {
        role: "value",
        designField: "layouts.<variant>.value_px",
        purpose: "Prints the exact value; formatted by the dataset display rule.",
      },
      {
        role: "disclosure",
        designField: "layouts.<variant>.disclosure_px",
        purpose: "Carries the honesty disclosure for the data shown.",
      },
    ],
    variation: {
      composition:
        "Headline block above a left-anchored plot field; category labels in a left rail, bars growing right, values trailing the plot. Driven by the job design record, not fixed coordinates.",
      framing:
        "The plot occupies the design-declared box with a zero baseline at its left edge; landscape and portrait are separate design layouts, never a crop of one another.",
      typeTreatment:
        "Four-role hierarchy (headline, label, value, disclosure) sized from the design record's per-variant pixel fields; palette from the design record's colors; essential text never shrinks.",
      pacing:
        "One linear reveal over the scene's declared motion interval with data overshoot forbidden, then a stable readable hold to the scene end.",
    },
    examples: [
      {
        id: "c05-fixture-bar-01",
        kind: "scene",
        description:
          "The shipped acceptance fixture scene from the powerpoint_graphic mode fixture job (illustrative data, honestly labeled).",
        scene: cloneJson(C05_EXAMPLE_SCENE),
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg006-remotion-c05-proof-states",
        description:
          "MG-006 Remotion adapter and render tests, including the Section 17.2 proof states measured three ways.",
        evidence: "runtime/tests/run-remotion.ts",
      },
      {
        id: "mg018-catalog-parity-corpus",
        description:
          "Catalog versus shipped-validator verdict parity over the shared accept/reject corpus.",
        evidence:
          "runtime/tests/run-catalog.ts with tests/fixtures/catalog/parity-corpus.json",
      },
      {
        id: "mg015-chart-contracts",
        description:
          "MG-015 chart-data contract tests for the dataset layer C05 consumes.",
        evidence: "runtime/tests/run-charts.ts",
      },
      {
        id: "mg032-motion-proof",
        description:
          "MG-032 motion proof tests: the animated C05 chart passes with three-way agreement (spec derivation, component geometry, decoded raster), the static-chart decoy fails as MG_FAKE_MOTION, depth claims without occlusion evidence are refused, and semantic cases route to human judgment.",
        evidence: "runtime/tests/run-motion-proof.ts",
      },
    ],
    provenance:
      "Section 7.1 row C05. Production implementation: runtime/src/remotion/components/C05BarChart.ts (MG-006). No borrowed primitives; the example scene is the repository's own fixture.",
  };
}
