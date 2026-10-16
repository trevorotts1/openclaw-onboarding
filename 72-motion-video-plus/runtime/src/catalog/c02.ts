// The C02 product-detail demonstration entry (Directive Sections
// 7.1 and 7.2; production implementation and catalog bundle MG-044).
//
// Registered with the full bundle Section 16.1 requires: the closed
// input schema for the detail_closeup spec shape, the proof
// contract, and registered tests. The production renderer is a
// Hyperframes generator through the existing adapter seam
// (generateC02Project in runtime/src/hyperframes/generators.ts): the
// original product view stays fixed and undistorted while a close
// view of the same source pixels zooms on the MG-012 close-up
// geometry, and the annotation anchor is a pure function of the
// detail point, the zoom window, and the output box, so the
// annotation names the same source point at every zoom step.
//
// Two honesty boundaries are recorded in this entry:
// - The MG-005 media_timing scene also carries component_id C02 in
//   its adapter fixture, but its own generator header states it is an
//   abstract timing fixture, not a product demonstration. It is not
//   registered here and is not evidence for this component.
// - VREF-04 (real product detail) stays BLOCKED_ASSET until an
//   actual approved product screenshot exists. The registered
//   example is a clearly labeled fictional product screen authored
//   for this bundle; it proves the mechanism, never a real product.

import { c02SceneSchema } from "./image-scene-schema";
import type { ComponentEntry, RegistrationBundle } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** The MG-044 acceptance scene, kept identical to
 * tests/fixtures/image-components/c02-detail.scene.json. The catalog
 * test suite asserts the two stay deep-equal. */
const C02_EXAMPLE_SCENE: Record<string, unknown> = {
  schema_version: "mg044-1",
  id: "detail-01",
  component_id: "C02",
  component_version: "1.0.0",
  variant: "detail_closeup",
  engine: "hyperframes",
  duration_frames: 180,
  asset_file: "assets/product.svg",
  font_ref: "font-fixture-sans",
  canvas: { width: 1920, height: 1080 },
  design: { colors: { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" } },
  product: {
    box: { x: 80, y: 250, width: 1000, height: 575 },
    source: { width: 1200, height: 690 },
  },
  detail: { point: { x: 0.7925, y: 0.6232 }, measure_color: "#16A34A" },
  zoom: {
    max_zoom: 2.5,
    start_frame: 30,
    end_frame_exclusive: 90,
    hold_to_frame_exclusive: 180,
    output: { x: 1090, y: 250, width: 720, height: 414 },
  },
  copy: {
    headline: "The approval step, up close",
    annotation_label: "Approve button: the step that releases the delivery",
    caption:
      "The original screen never moves or stretches. The close view is its own pixels, enlarged within the declared limit.",
    fixture_label: "ENGINEERING FIXTURE - FICTIONAL PRODUCT SCREEN",
  },
  headline_px: 84,
  caption_px: 40,
  annotation_px: 36,
  semantic_motion_assertions: [
    { id: "detail-wide", kind: "closeup_detail_fraction", frame: 0, min_fraction: 0, max_fraction: 0.35 },
    { id: "detail-close", kind: "closeup_detail_fraction", frame: 150, min_fraction: 0.85, max_fraction: 1 },
  ],
};

export function c02Entry(): ComponentEntry {
  return {
    componentId: "C02",
    version: "1.0.0",
    name: "Product-detail demonstration",
    availability: "available",
    unavailableReason: null,
    owningItem: "MG-044 (C02 generator through the Hyperframes adapter seam, on the MG-012 close-up geometry)",
    visibleChange:
      "A product view remains authentic while a pointer, highlight, or close view identifies a specific detail",
    semanticPurpose:
      "Show a real product detail without faking the product: the original view keeps its fidelity, unmoved and unstretched, while a close view of its own pixels identifies exactly one detail, with the annotation attached to that detail at every zoom step and no detail claimed beyond what the source resolution carries.",
    engines: ["hyperframes"],
    defaultEngine: "hyperframes",
    inputSchema: c02SceneSchema(),
    schemaSource:
      "Catalog-layer schema built by runtime/src/catalog/image-scene-schema.ts, describing the MG-044 production spec shape (runtime/src/hyperframes/generators.ts ProductDetailSceneSpec) field for field. The canonical contracts scene $def is closed on C05; promotion into the canonical schema is a contracts-revision item, as it was for MG-016's chart schemas.",
    assetRequirements: [
      {
        kind: "image",
        usage: ["embed_original"],
        role: "product_view",
        required: true,
        notes:
          "The original product screenshot or capture, embedded unmodified, referenced by the scene's asset_file and verified against asset_sha256 when the job records one. Redrawn product UI is prohibited. A fictional screen may be used only as a labeled engineering fixture, never as product proof.",
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
          "16:9 canvas; the product view and the close-view output box are placed by the scene spec side by side.",
      },
      {
        id: "portrait",
        aspect: "9:16",
        description:
          "9:16 canvas, genuinely recomposed from the scene spec (product view stacked above the close view), never a crop of the landscape layout.",
      },
    ],
    timelineContract: {
      intervalConvention: "half_open",
      durationSource:
        "scene.duration_frames; the zoom occupies [zoom.start_frame, zoom.end_frame_exclusive) and the annotated detail holds to zoom.hold_to_frame_exclusive",
      supportedFps: [30, 60],
      transitionHandleFields: [
        "timeline.scenes[].transition_in_frames",
        "timeline.scenes[].transition_out_frames",
      ],
      readableHold:
        "From zoom.end_frame_exclusive to zoom.hold_to_frame_exclusive the close view, its anchor marker, and the annotation label remain fully readable (fixture: frames 90 to 180 at 30 fps).",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["closeup_detail_fraction"],
          subjectSelector:
            "the detail region inside the close-view output box, measured as the detail measure_color fraction on decoded frames, normalized by the maximum-zoom hold frame; the annotation anchor is checked against the MG-012 annotationAnchorAt geometry for the same detail point",
          evidence: ["geometry", "decoded_frame"],
          proofFrames: [0, 150],
          proofFrameFps: 30,
          measuredStates: [
            "frame 0: the close view shows the full product view; the detail occupies its true small share of the output (normalized fraction within the scene's declared band)",
            "frame 150: the close view is at the declared maximum zoom; the detail fills its computed window share (normalized fraction within the scene's declared band) and the anchor marker sits on the detail point the geometry names",
            "upscale: the MG-012 assessment for the fixture (source 1200x690, zoom 2.5, output 720x414) reports its factor against the 2x readable-detail limit in the bundle's evidence record",
          ],
        },
      ],
      minimumProof:
        "Original UI fidelity; annotation follows the correct detail (Section 7.1).",
    },
    motionProof: null,
    typographyRoles: [
      {
        role: "annotation_label",
        designField: null,
        purpose: "Names the detail the annotation points at. Sized by the scene's annotation_px.",
      },
      {
        role: "caption",
        designField: null,
        purpose: "States why the detail matters, in one line. Sized by the scene's caption_px.",
      },
      {
        role: "headline",
        designField: null,
        purpose: "States the claim the detail supports. Sized by the scene's headline_px.",
      },
    ],
    variation: {
      composition:
        "Full product view with the close view placed by the scene spec near the detail it explains; which detail, which zoom, and where the close view lands all come from the spec, so two jobs differ visibly.",
      framing:
        "The original view is never distorted; the close view is a true window of the source pixels computed by the MG-012 zoom geometry, never a redraw.",
      typeTreatment:
        "Annotation labels sized from the scene spec and kept clear of player controls.",
      pacing:
        "One detail at a time; the zoom travels over the declared interval and the annotation holds long enough to be read.",
    },
    examples: [
      {
        id: "c02-fixture-detail-01",
        kind: "scene",
        description:
          "The MG-044 acceptance scene (fictional product screen, honestly labeled), identical to tests/fixtures/image-components/c02-detail.scene.json.",
        scene: cloneJson(C02_EXAMPLE_SCENE),
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg044-image-components",
        description:
          "MG-044 image component tests: catalog dispatch, generator geometry against the MG-012 close-up functions, the upscale assessment, adapter validation, and decoded-frame detail fractions at the wide and close states.",
        evidence: "runtime/tests/run-image-components.ts",
      },
      {
        id: "mg012-compositing",
        description:
          "MG-012 compositing tests for the close-up geometry this component renders: zoom windows, annotation anchor round-trip, and the upscale limit.",
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
      "Section 7.1 row C02. Production implementation: runtime/src/hyperframes/generators.ts (generateC02Project, MG-044) on the MG-012 close-up geometry in runtime/src/compositing/closeup.ts, rendered by runtime/src/adapters/hyperframes.ts. No borrowed primitives; the example product screen is this repository's own authored fictional fixture (tests/fixtures/image-components/product.svg), labeled as fictional wherever it appears. VREF-04 remains BLOCKED_ASSET for real product proof.",
  };
}

/** The governed registration bundle for C02: the entry plus the
 * engineering review attestation Section 16.1 requires. This is an
 * engineering review of the bundle, never an owner approval. */
export function c02Registration(): RegistrationBundle {
  return {
    entry: c02Entry(),
    reviewAttestation: {
      reviewer: "MG-044 worker (engineering)",
      decision: "approved",
      statement:
        "Bundle reviewed against Section 7.2: closed input schema for the detail_closeup production shape, proof contract naming decoded-frame states and the MG-012 upscale assessment, registered tests in runtime/tests/run-image-components.ts. The MG-005 media_timing fixture is explicitly not claimed as this component's evidence, and VREF-04 stays BLOCKED_ASSET. Owner calibration is not claimed.",
      reviewedAt: "2026-10-15T00:00:00Z",
    },
  };
}
