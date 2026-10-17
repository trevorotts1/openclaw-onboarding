// The C09 causal/branching diagram entry (Directive Sections 7.1 and
// 6, MG-017).
//
// Registered by its owning item with the full bundle Section 16.1
// requires: the closed input schema from the diagrams module, the
// proof contract, and the MG-017 test runner. The example scene is
// built by the same pattern builder the fixtures use, so the catalog
// example and tests/fixtures/diagrams/c09-branching.json share one
// source; the fixture additionally carries subject_identity assertions
// with font-measured expected positions, which the MG-017 runner
// verifies against the catalog example modulo those assertions.
//
// Branch selection is declared in the scene document
// (diagram.selected_branch_edge_id), never inferred from geometry or
// copy: the C09 minimum proof is a MEANINGFUL branch selection, and an
// inferred selection could silently change meaning when labels move.

import { C09_INPUT_SCHEMA } from "../diagrams/schema";
import { branchingDecision, diagramSceneDoc } from "../diagrams/patterns";
import type { DiagramSceneDoc } from "../diagrams/model";
import type { ComponentEntry } from "./types";

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** The registered example: an application reaches a qualification
 * decision and takes the declared Enroll branch. Structure identical
 * to the committed fixture; see the header note. */
export function c09ExampleScene(): DiagramSceneDoc {
  return diagramSceneDoc({
    id: "c09-branching",
    component_id: "C09",
    headline: "Where an application goes next",
    disclosure: "Illustrative decision rule. The diagram shows the rule; it does not prove an outcome.",
    spec: branchingDecision({
      input: { id: "application", label: "Application" },
      decision: { id: "qualified", label: "Qualified?" },
      outcomes: [
        { id: "enroll", label: "Enroll" },
        { id: "nurture", label: "Nurture" },
        { id: "decline", label: "Decline" },
      ],
      selectedOutcomeId: "enroll",
      subject: { id: "applicant-001", label: "Applicant" },
      timing: { start_frame: 10, end_frame_exclusive: 130, hold_to_frame_exclusive: 180 },
      canvas: { width: 1920, height: 1080, fps: 30 },
    }),
    assertions: [
      {
        id: "c09-timeline",
        kind: "timeline_bounds",
        subject_ids: ["applicant-001"],
        frame: 0,
        expected_values: [10, 130, 180, 180],
        tolerance: 0,
        unit: "frames",
        evidence: ["geometry"],
      },
      {
        id: "c09-labels-readable",
        kind: "text_readability",
        subject_ids: ["application", "qualified", "enroll", "nurture", "decline"],
        frame: 179,
        expected_values: [0],
        tolerance: 0,
        unit: "normalized",
        evidence: ["geometry"],
      },
    ],
  });
}

export function c09Entry(): ComponentEntry {
  return {
    componentId: "C09",
    version: "1.0.0",
    name: "Causal/branching diagram",
    availability: "available",
    unavailableReason: null,
    owningItem: "MG-017 (diagram primitives compatible with C09)",
    visibleChange:
      "Nodes and directed relationships build in a meaningful reading order",
    semanticPurpose:
      "Make a causal or branching structure legible: nodes and directed edges build in reading order, the selected branch is declared and meaningful, and no edge is orphaned or label-collided. A viewer can follow the same subject from the input, through the decision, to the declared outcome, and can see the untaken branches as real alternatives that were not chosen.",
    engines: ["remotion"],
    defaultEngine: "remotion",
    inputSchema: cloneJson(C09_INPUT_SCHEMA),
    schemaSource:
      "runtime/src/diagrams/schema.ts (C09 registration schema, MG-017). The canonical contracts schema is C05-only and unchanged; contracts-level job dispatch for C09 is an integration note for MG-025.",
    assetRequirements: [
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
          "Node and edge data under the C09 input schema registered by MG-017 (runtime/src/diagrams/schema.ts), plus the structural rules in runtime/src/diagrams/model.ts",
        notes:
          "Every edge must connect two declared nodes; branch selection must be declared, not inferred. Orphan edges and orphan nodes are schema-level refusals.",
      },
    ],
    layoutVariants: [
      {
        id: "landscape",
        aspect: "16:9",
        description:
          "16:9 canvas; input and decision read left to right, outcomes fan out in a right column stacked from measured label widths.",
      },
      {
        id: "portrait",
        aspect: "9:16",
        description:
          "9:16 canvas, genuinely recomposed: the flow runs vertically and outcomes stack along the reading axis, never a crop of the landscape layout.",
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
        "The complete diagram, all labels legible and the taken branch fully drawn, holds from the motion end to the hold end.",
      audioCueBehavior:
        "The component is silent. Audio belongs to the job or parent per timeline.audio_owner; the component emits no audio cues.",
    },
    proofContract: {
      selectors: [
        {
          assertionKinds: ["subject_identity", "timeline_bounds"],
          subjectSelector:
            "the traveling subject (diagram.subject.id) when the scene declares one, positioned by the resolved subject path; the untaken branch targets are checked as never entered",
          evidence: ["geometry", "decoded_frame"],
          proofFrames: [40, 90, 170],
          proofFrameFps: 30,
          measuredStates: [
            "frame 40: the subject is traveling from Application toward the decision; no outcome is active yet",
            "frame 90: the subject is on the declared Enroll branch; the untaken branches are drawing as alternatives, untraveled",
            "frame 170: the subject rests at the Enroll center; Nurture and Decline are drawn and labeled but were never entered",
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
            "label collisions: 0 on the registered fixtures, including the dense six-outcome fixture; a scene whose labels cannot fit is refused at layout with MG_LAYOUT_IMPOSSIBLE",
          ],
        },
      ],
      minimumProof:
        "Meaningful branch selection, no orphan edges or label collisions (Section 7.1).",
    },
    typographyRoles: [
      {
        role: "headline",
        designField: null,
        purpose: "States the structure's claim.",
      },
      {
        role: "node_label",
        designField: null,
        purpose:
          "Names each node inside its node box. Essential text: measured with the real font at 46px and never shrunk to fit.",
      },
      {
        role: "edge_label",
        designField: null,
        purpose: "Names a relationship where the diagram declares one.",
      },
      {
        role: "disclosure",
        designField: null,
        purpose:
          "Carries the claim discipline line: the diagram shows the rule or mechanism; it does not prove an outcome.",
      },
    ],
    variation: {
      composition:
        "Node field laid out in one reading order from measured label widths; edges route as straight runs or single elbows and never cross a label box.",
      framing:
        "The whole diagram fits the frame at its final state; landscape and portrait are separate computed layouts, never crops.",
      typeTreatment:
        "Node and edge labels at declared sizes measured with the real font, with collision checks as part of the proof, not a hope.",
      pacing:
        "Nodes and edges build in the declared causal order: a branch cannot draw before its decision activates, and the full structure holds.",
    },
    examples: [
      {
        id: "c09-fixture-branching",
        kind: "scene",
        description:
          "An application reaches a Qualified? decision and takes the declared Enroll branch (illustrative rule, honestly labeled). Identical in structure to tests/fixtures/diagrams/c09-branching.json.",
        scene: cloneJson(c09ExampleScene()) as unknown as Record<string, unknown>,
        beat: null,
      },
    ],
    tests: [
      {
        id: "mg017-diagrams",
        description:
          "MG-017 diagram tests: declared branch selection, subject never entering untaken branches, label non-collision on the dense fixture, orphan edge refusal, causality ordering, and path termination exactness.",
        evidence: "runtime/tests/run-diagrams.ts",
      },
      {
        id: "mg018-catalog-registration",
        description:
          "Catalog registration discipline: the entry validates against the catalog entry schema and the default registry holds twelve entries.",
        evidence: "runtime/tests/run-catalog.ts",
      },
    ],
    provenance:
      "Section 7.1 row C09. Production implementation: runtime/src/diagrams (MG-017), the same primitives as C04 with the branching pattern and declared branch selection. No borrowed primitives; the example scene is this repository's own fixture.",
  };
}
