// The C04 object-through-mechanism entry (Directive Sections 7.1 and
// 6, MG-017).
//
// Registered by its owning item with the full bundle Section 16.1
// requires: the closed input schema from the diagrams module, the
// proof contract, and the MG-017 test runner. The example scene is
// built by the same pattern builder the fixtures use, so the catalog
// example and tests/fixtures/diagrams/c04-flow-mechanism.json share
// one source; the fixture additionally carries subject_identity
// assertions with font-measured expected positions, which the MG-017
// runner verifies against the catalog example modulo those assertions.
//
// Engine note, recorded plainly: Section 7.1 names Hyperframes as
// C04's default engine. The diagram primitives and frame functions are
// engine-agnostic, but at this item the only proven diagram render
// path is the Remotion composition in runtime/src/diagrams/render, so
// dispatch is registered for Remotion only. Hyperframes is NOT listed
// as supported until a Hyperframes diagram generator exists; claiming
// it now would be an unproven capability.

import { C04_INPUT_SCHEMA } from "../diagrams/schema";
import { diagramSceneDoc, flowThrough } from "../diagrams/patterns";
import type { DiagramSceneDoc } from "../diagrams/model";
import type { ComponentEntry } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** The registered example: a lead travels intake, qualification,
 * proposal, and delivery. Structure identical to the committed
 * fixture; see the header note about the fixture's extra assertions. */
export function c04ExampleScene(): DiagramSceneDoc {
  return diagramSceneDoc({
    id: "c04-flow-mechanism",
    component_id: "C04",
    headline: "How a lead becomes a delivery",
    disclosure: "Illustrative mechanism. The diagram shows the process; it does not prove a business outcome.",
    spec: flowThrough({
      stages: [
        { id: "intake", label: "Intake" },
        { id: "qualify", label: "Qualify" },
        { id: "proposal", label: "Proposal" },
        { id: "delivery", label: "Delivery" },
      ],
      subject: { id: "lead-001", label: "Lead" },
      timing: { start_frame: 15, end_frame_exclusive: 135, hold_to_frame_exclusive: 180 },
      canvas: { width: 1920, height: 1080, fps: 30 },
    }),
    assertions: [
      {
        id: "c04-timeline",
        kind: "timeline_bounds",
        subject_ids: ["lead-001"],
        frame: 0,
        expected_values: [15, 135, 180, 180],
        tolerance: 0,
        unit: "frames",
        evidence: ["geometry"],
      },
      {
        id: "c04-labels-readable",
        kind: "text_readability",
        subject_ids: ["intake", "qualify", "proposal", "delivery"],
        frame: 179,
        expected_values: [0],
        tolerance: 0,
        unit: "normalized",
        evidence: ["geometry"],
      },
    ],
  });
}

export function c04Entry(): ComponentEntry {
  return {
    componentId: "C04",
    version: "1.0.0",
    name: "Object-through-mechanism",
    availability: "available",
    unavailableReason: null,
    owningItem: "MG-017 (mechanism primitives and persistent identities)",
    visibleChange:
      "An object or value travels through labeled stages and causes a visible result",
    semanticPurpose:
      "Make a mechanism causal and memorable: one persistent object travels through labeled stages in order and visibly causes the final outcome. Temporal order matches causality by construction: a stage activates only when the subject arrives, and the subject's position is a deterministic function of frame, so the same identity is trackable at every proof frame.",
    engines: ["remotion"],
    defaultEngine: "remotion",
    inputSchema: cloneJson(C04_INPUT_SCHEMA),
    schemaSource:
      "runtime/src/diagrams/schema.ts (C04 registration schema, MG-017). The canonical contracts schema is C05-only and unchanged; contracts-level job dispatch for C04 is an integration note for MG-025.",
    assetRequirements: [
      {
        kind: "svg",
        usage: ["embed_original", "approved_derivative"],
        role: "traveling_object",
        required: false,
        notes:
          "The traveling object may be a registered vector or a component-drawn shape; its identity must persist across stages. The registered composition draws the subject marker itself, so no asset is required for the base path.",
      },
      {
        kind: "font",
        usage: ["embed_original"],
        role: "scene_typography",
        required: true,
        notes:
          "Resolved through the job assets font_requirements (runtime_registry alias); substitution is forbidden. Layout measures labels with the actual font binary before any render.",
      },
    ],
    dataRequirements: [
      {
        role: "diagram_data",
        required: true,
        contract:
          "Node, edge, subject, and timing data under the C04 input schema registered by MG-017 (runtime/src/diagrams/schema.ts), plus the structural rules in runtime/src/diagrams/model.ts",
        notes:
          "Every edge connects two declared nodes; the subject path is a connected chain of declared edges; a diagram shows a mechanism and never claims a business outcome its data does not carry.",
      },
    ],
    layoutVariants: [
      {
        id: "landscape",
        aspect: "16:9",
        description:
          "16:9 canvas; the stage chain runs horizontally, laid out from measured label widths.",
      },
      {
        id: "portrait",
        aspect: "9:16",
        description:
          "9:16 canvas, genuinely recomposed: the chain runs vertically with the same measured label widths, never a crop of the landscape layout.",
      },
    ],
    timelineContract: {
      intervalConvention: "half_open",
      durationSource:
        "scene.duration_frames, which must equal diagram.timing.hold_to_frame_exclusive; subject motion occupies [diagram.timing.start_frame, diagram.timing.end_frame_exclusive)",
      supportedFps: [30, 60],
      transitionHandleFields: [
        "timeline.scenes[].transition_in_frames",
        "timeline.scenes[].transition_out_frames",
      ],
      readableHold:
        "From diagram.timing.end_frame_exclusive to the hold end the subject rests at the final stage and the completed mechanism, every label readable, holds.",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["subject_identity", "timeline_bounds"],
          subjectSelector:
            "the traveling subject (diagram.subject.id), positioned by the resolved subject path; geometry from the frame functions and decoded_frame from the rendered proof stills",
          evidence: ["geometry", "decoded_frame"],
          proofFrames: [30, 75, 170],
          proofFrameFps: 30,
          measuredStates: [
            "frame 30: the subject is inside the first edge, partway from Intake toward Qualify; the edge is drawn exactly to the subject",
            "frame 75: the subject is midway through the mechanism; upstream stages active, downstream stages not yet active",
            "frame 170: the subject rests at the Delivery center in the readable hold; every edge fully drawn",
          ],
        },
        {
          assertionKinds: ["text_readability"],
          subjectSelector:
            "node label boxes, measured with the actual font binary (MG-013 typography) at the declared label size",
          evidence: ["geometry"],
          proofFrames: [],
          proofFrameFps: null,
          measuredStates: [
            "label collisions: 0 on every registered fixture; a scene whose labels cannot fit is refused at layout with MG_LAYOUT_IMPOSSIBLE, never shrunk or overlapped",
          ],
        },
      ],
      minimumProof: "Persistent identity; causal order; final outcome (Section 7.1).",
    },
    motionProof: {
      subjects:
        "traveling_object: the mechanism's single traveling subject (diagram.subject.id), one persistent identity for the whole sequence",
      measurement:
        "accent_centroid: the accent centroid inside a window around the resolved subject position on the decoded frame, checked against the frame functions' position and the scene's declared subject_identity assertions",
      transformation: "path_transit",
      depthPolicy: "not_claimed",
    },
    typographyRoles: [
      {
        role: "headline",
        designField: null,
        purpose: "States the mechanism the viewer is about to follow.",
      },
      {
        role: "stage_label",
        designField: null,
        purpose:
          "Names each stage the object passes through. Essential text: measured with the real font at 46px and never shrunk to fit.",
      },
      {
        role: "outcome_label",
        designField: null,
        purpose: "Names the visible result the journey causes, at the final stage.",
      },
      {
        role: "disclosure",
        designField: null,
        purpose:
          "Carries the claim discipline line: the diagram shows a mechanism; it does not prove a business outcome.",
      },
    ],
    variation: {
      composition:
        "Stage chain laid out from measured label widths along the reading axis; the subject is the moving focal point and the whole path stays in frame so cause and effect share one composition.",
      framing:
        "Landscape runs the chain horizontally, portrait vertically; both are computed from the same spec by the layout solver, never cropped from one another.",
      typeTreatment:
        "Stage labels at one declared size measured with the real font; the headline and disclosure come from the scene copy, so two jobs with different copy differ visibly while the mechanism geometry follows the spec alone.",
      pacing:
        "Travel speed is proportional to path length inside the declared motion interval, with bottleneck constriction where the pattern declares it; the outcome holds after arrival.",
    },
    examples: [
      {
        id: "c04-fixture-flow-mechanism",
        kind: "scene",
        description:
          "A lead travels Intake, Qualify, Proposal, and Delivery (illustrative mechanism, honestly labeled). Identical in structure to tests/fixtures/diagrams/c04-flow-mechanism.json.",
        scene: cloneJson(c04ExampleScene()) as unknown as Record<string, unknown>,
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg017-diagrams",
        description:
          "MG-017 diagram tests: subject persistence, causality ordering, label non-collision and the named layout impossibility, path termination exactness, the four patterns, the title-change negative, and the Remotion render proof with decoded-frame subject positions.",
        evidence: "runtime/tests/run-diagrams.ts",
      },
      {
        id: "mg018-catalog-registration",
        description:
          "Catalog registration discipline: the entry validates against the catalog entry schema and the default registry holds twelve entries.",
        evidence: "runtime/tests/run-catalog.ts",
      },
      {
        id: "mg032-motion-proof",
        description:
          "MG-032 motion proof tests: the C04 mechanism sequence passes with geometry and decoded-frame subject positions agreeing at the initial, proof, and final checkpoints.",
        evidence: "runtime/tests/run-motion-proof.ts",
      },
    ],
    provenance:
      "Section 7.1 row C04. Production implementation: runtime/src/diagrams (MG-017). Engine deviation recorded in this entry: Section 7.1 names Hyperframes as the default engine; dispatch is registered for Remotion only, the engine with a proven diagram render path at this item. No borrowed primitives; the example scene is this repository's own fixture.",
  };
}
