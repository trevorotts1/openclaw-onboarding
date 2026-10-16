// The C03 before/after comparison entry (Directive Sections 7.1
// and 7.2; production implementation and catalog bundle MG-044).
//
// Registered with the full bundle Section 16.1 requires: the closed
// input schema for the wipe_reveal spec shape, the proof contract,
// and registered tests. The production renderer is a Hyperframes
// generator through the existing adapter seam (generateC03Project
// in runtime/src/hyperframes/generators.ts): both states share one
// subject box at the same crop and scale (each state framed by the
// MG-012 comparison geometry's rule that honoring one image never
// reframes the other), the after state is uncovered by a mask whose
// edge is the comparison boundary, and the boundary comes to rest at
// the declared rest fraction so the final hold compares the two
// states instead of replacing one with the other. The adapter
// evaluates the state-fraction assertions from decoded frames by
// the same normalized-fraction method as the C01 reveal.

import { c03SceneSchema } from "./image-scene-schema";
import type { ComponentEntry, RegistrationBundle } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** The MG-044 acceptance scene, kept identical to
 * tests/fixtures/image-components/c03-compare.scene.json. The catalog
 * test suite asserts the two stay deep-equal. */
const C03_EXAMPLE_SCENE: Record<string, unknown> = {
  schema_version: "mg044-1",
  id: "compare-01",
  component_id: "C03",
  component_version: "1.0.0",
  variant: "wipe_reveal",
  engine: "hyperframes",
  duration_frames: 180,
  before_file: "assets/before.svg",
  after_file: "assets/after.svg",
  font_ref: "font-fixture-sans",
  canvas: { width: 1920, height: 1080 },
  design: { colors: { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" } },
  subject: {
    id: "board-state",
    box: { x: 120, y: 240, width: 1200, height: 690 },
    measure_color: "#16A34A",
  },
  copy: {
    headline: "The same board, before and after",
    before_label: "Before",
    after_label: "After",
    caption: "Same crop, same scale: the boundary rests mid-frame.",
    fixture_label: "ENGINEERING FIXTURE - FICTIONAL BOARD",
  },
  headline_px: 84,
  caption_px: 40,
  label_px: 36,
  motion: {
    kind: "wipe_reveal",
    start_frame: 30,
    end_frame_exclusive: 90,
    hold_to_frame_exclusive: 180,
    rest_fraction: 0.55,
  },
  semantic_motion_assertions: [
    { id: "wipe-initial", kind: "state_fraction", frame: 0, min_fraction: 0, max_fraction: 0.02 },
    { id: "wipe-proof", kind: "state_fraction", frame: 60, min_fraction: 0.4, max_fraction: 0.6 },
    { id: "wipe-final", kind: "state_fraction", frame: 179, min_fraction: 0.97, max_fraction: 1 },
  ],
};

export function c03Entry(): ComponentEntry {
  return {
    componentId: "C03",
    version: "1.0.0",
    name: "Before/after comparison",
    availability: "available",
    unavailableReason: null,
    owningItem: "MG-044 (C03 generator through the Hyperframes adapter seam, on the MG-012 comparison geometry)",
    visibleChange:
      "Two states become directly comparable without hiding either state",
    semanticPurpose:
      "Let a viewer judge a change directly: both states stay visible at the same crop and scale with a legible comparison boundary, the boundary's travel is the explanation, and at the final hold both states remain readable together so neither state is hidden or exaggerated.",
    engines: ["hyperframes"],
    defaultEngine: "hyperframes",
    inputSchema: c03SceneSchema(),
    schemaSource:
      "Catalog-layer schema built by runtime/src/catalog/image-scene-schema.ts, describing the MG-044 production spec shape (runtime/src/hyperframes/generators.ts BeforeAfterSceneSpec) field for field. The canonical contracts scene $def is closed on C05; promotion into the canonical schema is a contracts-revision item, as it was for MG-016's chart schemas.",
    assetRequirements: [
      {
        kind: "image",
        usage: ["embed_original", "approved_derivative"],
        role: "before_state",
        required: true,
        notes:
          "The earlier state, embedded as approved, referenced by the scene's before_file and verified against before_sha256 when the job records one.",
      },
      {
        kind: "image",
        usage: ["embed_original", "approved_derivative"],
        role: "after_state",
        required: true,
        notes:
          "The later state, embedded as approved, referenced by the scene's after_file and verified against after_sha256 when the job records one. Both states must share the same source dimensions so the comparison is honest.",
      },
      {
        kind: "font",
        usage: ["embed_original"],
        role: "scene_typography",
        required: true,
        notes:
          "Resolved through the job assets font_requirements (runtime_registry alias); substitution is forbidden.",
      },
    ],
    dataRequirements: [],
    layoutVariants: [
      {
        id: "landscape",
        aspect: "16:9",
        description:
          "16:9 canvas; both states share the scene's subject box and the boundary travels horizontally to its rest fraction.",
      },
      {
        id: "portrait",
        aspect: "9:16",
        description:
          "9:16 canvas, genuinely recomposed from the scene spec (subject box and boundary restated for portrait), never a crop of the landscape layout.",
      },
    ],
    timelineContract: {
      intervalConvention: "half_open",
      durationSource:
        "scene.duration_frames; the boundary travel occupies [motion.start_frame, motion.end_frame_exclusive) and both states hold readable to motion.hold_to_frame_exclusive",
      supportedFps: [30, 60],
      transitionHandleFields: [
        "timeline.scenes[].transition_in_frames",
        "timeline.scenes[].transition_out_frames",
      ],
      readableHold:
        "From motion.end_frame_exclusive to motion.hold_to_frame_exclusive both states, their labels, and the boundary at its rest fraction remain visible and readable (fixture: frames 90 to 180 at 30 fps).",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["state_fraction"],
          subjectSelector:
            "the after state inside the shared subject box, measured as the measure_color fraction on decoded frames, normalized by the hold frame's fraction (the MG-005 adapter method); the boundary rest position is checked against motion.rest_fraction",
          evidence: ["geometry", "decoded_frame", "full_fps_clip"],
          proofFrames: [0, 60, 179],
          proofFrameFps: 30,
          measuredStates: [
            "frame 0: after-state fraction 0, within [0, 0.02]: only the before state is visible",
            "frame 60: after-state fraction at the declared mid-travel band: the boundary is mid-frame and both states are partially visible",
            "frame 179: after-state fraction at its hold value with the boundary resting at the declared rest fraction: both states and both labels remain visible together",
          ],
        },
      ],
      minimumProof:
        "Both states and the comparison boundary are visible (Section 7.1).",
    },
    motionProof: null,
    typographyRoles: [
      {
        role: "state_label",
        designField: null,
        purpose: "Labels each state so the comparison cannot be misread. Sized by the scene's label_px.",
      },
      {
        role: "caption",
        designField: null,
        purpose: "States what changed, in one line. Sized by the scene's caption_px.",
      },
      {
        role: "headline",
        designField: null,
        purpose: "States the comparison the viewer is making. Sized by the scene's headline_px.",
      },
    ],
    variation: {
      composition:
        "Two state fields sharing one frame with a declared boundary chosen by the scene spec; the boundary's rest fraction and the subject box come from the spec, so two jobs differ visibly.",
      framing:
        "Both states use the same crop and scale so the comparison is honest; each state is framed against its own focal constraints per the MG-012 comparison rule.",
      typeTreatment:
        "State labels sit at the compared region's corners and are sized from the scene spec.",
      pacing:
        "Boundary movement is deliberate over the declared interval and ends with both states readable together, never with one state replacing the other.",
    },
    examples: [
      {
        id: "c03-fixture-compare-01",
        kind: "scene",
        description:
          "The MG-044 acceptance scene (fictional board states, honestly labeled), identical to tests/fixtures/image-components/c03-compare.scene.json.",
        scene: cloneJson(C03_EXAMPLE_SCENE),
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg044-image-components",
        description:
          "MG-044 image component tests: catalog dispatch, adapter validation, decoded-frame state fractions at the initial, proof, and hold frames, and the boundary rest position.",
        evidence: "runtime/tests/run-image-components.ts",
      },
      {
        id: "mg012-compositing",
        description:
          "MG-012 compositing tests for the comparison geometry this component renders: per-image crops solved independently for side-by-side and before/after plans.",
        evidence: "runtime/tests/run-compositing.ts",
      },
      {
        id: "mg018-catalog-registration",
        description:
          "Catalog registration discipline: the entry validates against the catalog entry schema and the default registry holds twelve entries.",
        evidence: "runtime/tests/run-catalog.ts",
      },
    ],
    provenance:
      "Section 7.1 row C03. Production implementation: runtime/src/hyperframes/generators.ts (generateC03Project, MG-044) on the MG-012 comparison geometry in runtime/src/compositing/compare.ts, rendered by runtime/src/adapters/hyperframes.ts. No borrowed primitives; the example states are this repository's own authored fictional fixtures (tests/fixtures/image-components/before.svg and after.svg), labeled as fixtures wherever they appear.",
  };
}

/** The governed registration bundle for C03: the entry plus the
 * engineering review attestation Section 16.1 requires. This is an
 * engineering review of the bundle, never an owner approval. */
export function c03Registration(): RegistrationBundle {
  return {
    entry: c03Entry(),
    reviewAttestation: {
      reviewer: "MG-044 worker (engineering)",
      decision: "approved",
      statement:
        "Bundle reviewed against Section 7.2: closed input schema for the wipe_reveal production shape, proof contract naming decoded-frame state fractions and the boundary rest position, registered tests in runtime/tests/run-image-components.ts. Owner calibration is not claimed: the reference suite stays CALIBRATION_PENDING.",
      reviewedAt: "2026-10-15T00:00:00Z",
    },
  };
}
