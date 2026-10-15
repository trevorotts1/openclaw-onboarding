// The C01 image-led statement entry (Directive Sections 7.1 and
// 7.2; production implementation MG-005, catalog registration
// MG-044).
//
// Registered with the full bundle Section 16.1 requires: the closed
// input schema for the component's production spec shapes (the
// MG-005 Hyperframes spec family in runtime/src/hyperframes/
// generators.ts), the proof contract, and registered tests. The
// production renderer is the shipped Hyperframes adapter: its C01
// mask-reveal generator uncovers the named subject itself through a
// mask (subject-owned motion, M10) and its nested-detail generator
// embeds a detail sub-composition beside the same subject. The
// adapter evaluates the reveal assertions from decoded frames.
//
// Canonical-path note, recorded plainly: a C01 scene does not pass
// the dispatcher's contracts gate on this base, because the
// canonical contracts scene $def is closed on C05 and widening it is
// a contracts revision, not a catalog act. C01 jobs therefore reach
// the adapter as ValidatedMotionJob objects through the direct
// adapter lane (the MG-005 and MG-039 pattern), with the routing
// decision computed by the shipped routing module and recorded.
// What this bundle closes is the catalog side of that divergence:
// the catalog consult now finds C01, validates its scenes against
// the registered closed schema, and resolves it as dispatchable
// instead of reporting it registered-but-unavailable.

import { c01SceneSchema } from "./image-scene-schema";
import type { ComponentEntry, RegistrationBundle } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const PALETTE = { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" };

/** The MG-005 acceptance reveal scene, kept identical to
 * tests/fixtures/image-components/c01-reveal.scene.json. The catalog
 * test suite asserts the two stay deep-equal. The job-level asset
 * hash is computed by the job builder at staging time (the MG-005
 * suite pattern), so the registered example carries no hash. */
const C01_REVEAL_SCENE: Record<string, unknown> = {
  schema_version: "mg005-1",
  id: "reveal-01",
  component_id: "C01",
  component_version: "1.0.0",
  engine: "hyperframes",
  duration_frames: 150,
  asset_file: "assets/subject.svg",
  font_ref: "font-fixture-sans",
  canvas: { width: 1920, height: 1080 },
  design: { colors: PALETTE },
  subject: {
    id: "work-crate",
    box: { x: 360, y: 190, width: 1200, height: 690 },
    measure_color: "#C04A26",
  },
  copy: {
    headline: "Inside every delivery: the work itself",
    caption: "One work crate, uncovered in full. Nothing else in the frame moves.",
    fixture_label: "ENGINEERING FIXTURE - ILLUSTRATIVE OBJECT",
  },
  headline_px: 84,
  caption_px: 40,
  motion: {
    kind: "mask_reveal",
    start_frame: 30,
    end_frame_exclusive: 90,
    hold_to_frame_exclusive: 150,
  },
  semantic_motion_assertions: [
    { id: "reveal-initial", kind: "subject_reveal", frame: 0, min_fraction: 0, max_fraction: 0.02 },
    { id: "reveal-proof", kind: "subject_reveal", frame: 60, min_fraction: 0.4, max_fraction: 0.85 },
    { id: "reveal-final", kind: "subject_reveal", frame: 149, min_fraction: 0.97, max_fraction: 1 },
  ],
};

/** The MG-005 nested-detail variant scene: the same subject held
 * constant while a detail sub-composition animates in beside it. */
const C01_NESTED_SCENE: Record<string, unknown> = {
  schema_version: "mg005-1",
  id: "nested-01",
  component_id: "C01",
  component_version: "1.0.0",
  variant: "nested_detail",
  engine: "hyperframes",
  duration_frames: 120,
  asset_file: "assets/subject.svg",
  font_ref: "font-fixture-sans",
  canvas: { width: 1920, height: 1080 },
  design: { colors: PALETTE },
  subject: {
    id: "work-crate",
    box: { x: 120, y: 250, width: 1000, height: 620 },
    measure_color: "#C04A26",
  },
  detail: {
    box: { x: 1220, y: 330, width: 580, height: 300 },
    start_frame: 30,
    measure_color: "#1D6FB8",
    variables: { label: "crates delivered this week", value: "128" },
  },
  copy: {
    headline: "The work, with its detail attached",
    fixture_label: "ENGINEERING FIXTURE - ILLUSTRATIVE OBJECT",
  },
  headline_px: 84,
};

export function c01Entry(): ComponentEntry {
  return {
    componentId: "C01",
    version: "1.0.0",
    name: "Image-led statement",
    availability: "available",
    unavailableReason: null,
    owningItem: "MG-005 (Hyperframes adapter and C01 generators); catalog bundle MG-044",
    visibleChange:
      "An approved subject/image is revealed or reframed to establish the idea; type supports it",
    semanticPurpose:
      "Establish the idea with a real subject: the approved image carries the meaning and typography supports it. The reveal is the subject itself changing state through a mask, never a background moving behind a static subject, and the composed statement holds readable to the scene end.",
    engines: ["hyperframes"],
    defaultEngine: "hyperframes",
    inputSchema: c01SceneSchema(),
    schemaSource:
      "Catalog-layer schema built by runtime/src/catalog/image-scene-schema.ts, describing the MG-005 production spec shapes (runtime/src/hyperframes/generators.ts ImageRevealSceneSpec and NestedDetailSceneSpec) field for field. The canonical contracts scene $def is closed on C05; promotion of this shape into the canonical schema is a contracts-revision item, as it was for MG-016's chart schemas.",
    assetRequirements: [
      {
        kind: "image",
        usage: ["embed_original", "approved_derivative"],
        role: "hero_image",
        required: true,
        notes:
          "The approved subject image, referenced by the scene's asset_file and verified against asset_sha256 when the job records one. Reference-only assets may inform the design but are never embedded.",
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
          "16:9 canvas; the subject box, crop, and type placement come from the scene spec and the job design record.",
      },
      {
        id: "portrait",
        aspect: "9:16",
        description:
          "9:16 canvas, genuinely recomposed from the scene spec (subject box and type placed for portrait), never a crop of the landscape layout.",
      },
    ],
    timelineContract: {
      intervalConvention: "half_open",
      durationSource:
        "scene.duration_frames; the reveal occupies [motion.start_frame, motion.end_frame_exclusive) and the composed statement holds to motion.hold_to_frame_exclusive",
      supportedFps: [30, 60],
      transitionHandleFields: [
        "timeline.scenes[].transition_in_frames",
        "timeline.scenes[].transition_out_frames",
      ],
      readableHold:
        "From motion.end_frame_exclusive to motion.hold_to_frame_exclusive the fully revealed subject plus its supporting headline and caption remain fully readable (fixture: frames 90 to 150 at 30 fps).",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["subject_reveal"],
          subjectSelector:
            "the named subject (scene.subject.id), measured as the measure_color fraction inside the subject box on decoded frames, normalized by the hold frame's fraction (the MG-005 adapter method)",
          evidence: ["geometry", "decoded_frame", "full_fps_clip"],
          proofFrames: [0, 60, 149],
          proofFrameFps: 30,
          measuredStates: [
            "frame 0: revealed fraction 0.000, within [0, 0.02]: the subject is covered, no false subject shown",
            "frame 60: revealed fraction 0.625, within [0.4, 0.85]: the mask is mid-travel and the subject itself is changing state",
            "frame 149: revealed fraction 1.000, within [0.97, 1]: the subject is fully revealed and held",
          ],
        },
      ],
      minimumProof:
        "Subject integrity, deliberate crop, readable opening and proof frames (Section 7.1).",
    },
    motionProof: null,
    typographyRoles: [
      {
        role: "headline",
        designField: null,
        purpose: "Supports the image; never competes with the subject. Sized by the scene's headline_px.",
      },
      {
        role: "caption",
        designField: null,
        purpose:
          "Names the subject honestly, including fixture labeling where the image is illustrative. Sized by the scene's caption_px.",
      },
    ],
    variation: {
      composition:
        "Image-first field: the subject box and its mask are placed by the scene spec, and type is composed around the subject, so two jobs with different subjects and boxes differ visibly.",
      framing:
        "Crop is deliberate and focal-point aware, from the asset record's focal point and protected regions (MG-012 crop solver); the image inside the mask never moves or scales during the reveal.",
      typeTreatment:
        "Headline and caption sized from the scene spec; essential text never shrinks.",
      pacing:
        "Reveal over the declared interval, then a readable hold on the composed statement; the nested variant holds the subject constant while its detail composition animates in.",
    },
    examples: [
      {
        id: "c01-fixture-reveal-01",
        kind: "scene",
        description:
          "The MG-005 acceptance reveal scene (illustrative object, honestly labeled), identical to tests/fixtures/image-components/c01-reveal.scene.json.",
        scene: cloneJson(C01_REVEAL_SCENE),
        beat: null,
      },
      {
        id: "c01-fixture-nested-01",
        kind: "scene",
        description:
          "The MG-005 nested-detail variant: the subject held constant while a detail sub-composition animates in beside it.",
        scene: cloneJson(C01_NESTED_SCENE),
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg005-hyperframes",
        description:
          "MG-005 Hyperframes adapter tests: the C01 reveal validates, its three assertions pass from decoded frames, the final render is a 150-frame full-fps clip, and the nested variant's detail chip animates while the subject fraction stays constant.",
        evidence: "runtime/tests/run-hyperframes.ts",
      },
      {
        id: "mg044-image-components",
        description:
          "MG-044 image component tests: catalog dispatch for C01 to C03, generator geometry, and decoded-frame proof for the C02 and C03 bundles registered with this entry.",
        evidence: "runtime/tests/run-image-components.ts",
      },
      {
        id: "mg018-catalog-registration",
        description:
          "Catalog registration discipline: the entry validates against the catalog entry schema and the default registry holds twelve entries.",
        evidence: "runtime/tests/run-catalog.ts",
      },
    ],
    provenance:
      "Section 7.1 row C01. Production implementation: runtime/src/hyperframes/generators.ts (generateC01Project, generateNestedProject, MG-005) rendered by runtime/src/adapters/hyperframes.ts. Catalog bundle registered by MG-044. No borrowed primitives; the example subject is this repository's own authored fixture SVG (tests/fixtures/image-components/subject.svg), labeled an engineering fixture wherever it appears.",
  };
}

/** The governed registration bundle for C01: the entry plus the
 * engineering review attestation Section 16.1 requires. This is an
 * engineering review of the bundle, never an owner approval. */
export function c01Registration(): RegistrationBundle {
  return {
    entry: c01Entry(),
    reviewAttestation: {
      reviewer: "MG-044 worker (engineering)",
      decision: "approved",
      statement:
        "Bundle reviewed against Section 7.2: closed input schema describing the shipped MG-005 production spec shapes, proof contract naming the MG-005 decoded-frame states recorded in tests/evidence/mg005, registered tests in runtime/tests/run-hyperframes.ts and runtime/tests/run-image-components.ts. The canonical contracts gate remains closed on C05; the entry records that limit instead of claiming dispatcher dispatch. Owner calibration is not claimed: the reference suite stays CALIBRATION_PENDING.",
      reviewedAt: "2026-10-15T00:00:00Z",
    },
  };
}
