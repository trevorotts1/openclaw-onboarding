// Typed component catalog: the public shapes of the registry that Directive
// MG-018 creates (Sections 7.1, 7.2, and 16.1). A catalog entry is the
// registration record for one motion component: its closed input schema,
// engine support, semantic purpose, asset requirements, layout variants,
// timeline contract, proof contract, typography roles, variation
// descriptors, and examples. The registry in registry.ts enforces the
// Section 16.1 rule: a component is unavailable until its schema, proof
// contract, and tests are registered together.

import type { ProductionEngine } from "../adapters/types";

/** Only "available" entries may be dispatched to production. */
export type ComponentAvailability = "available" | "unavailable";

/** Canonical asset kinds from contracts-v2 $defs/assets (MG-011 vocabulary). */
export type AssetKind = "image" | "video" | "audio" | "font" | "svg";

/** Canonical asset usage classes from contracts-v2 $defs/assets. */
export type AssetUsage =
  | "embed_original"
  | "approved_derivative"
  | "reference_only";

/** One media asset a component needs, in the MG-011 intake vocabulary. */
export interface AssetRequirement {
  kind: AssetKind;
  /** Usage classes the component accepts for this asset. */
  usage: AssetUsage[];
  /** The job role the asset fills, for example "hero_image". */
  role: string;
  required: boolean;
  notes: string;
}

/** Structured data a component consumes (distinct from media assets). */
export interface DataRequirement {
  /** The job role the data fills, for example "comparison_dataset". */
  role: string;
  required: boolean;
  /** The contract the data must satisfy. */
  contract: string;
  notes: string;
}

export interface LayoutVariant {
  id: string;
  aspect: "16:9" | "9:16";
  description: string;
}

/**
 * How a component occupies time, in the Section 5.4 convention: integer
 * frame intervals are half-open, [start_frame, end_frame_exclusive), and
 * durations are the difference of the endpoints. Conversion to seconds
 * happens only at engine boundaries.
 */
export interface TimelineContract {
  intervalConvention: "half_open";
  /** Where the component reads its total duration from. */
  durationSource: string;
  supportedFps: number[];
  /** Timeline fields that own transitions into and out of the scene. */
  transitionHandleFields: string[];
  /** The readable-hold obligation after motion completes. */
  readableHold: string;
  /** How audio cues behave for this component. */
  audioCueBehavior: string;
}

export type ProofEvidenceKind =
  | "geometry"
  | "decoded_frame"
  | "full_fps_clip";

/**
 * One measurable proof obligation, in the MG-009/MG-006 pattern: which
 * semantic assertion kinds prove the component, how inspection finds the
 * subjects, which evidence forms are required, and which measured states
 * count as proof.
 */
export interface ProofSelector {
  /** Canonical assertion kinds (contracts-v2 $defs/assertion) or "custom". */
  assertionKinds: string[];
  /** How inspection locates the measured subjects. */
  subjectSelector: string;
  evidence: ProofEvidenceKind[];
  /** Reference proof frames at proofFrameFps; empty means per-scene. */
  proofFrames: number[];
  proofFrameFps: number | null;
  measuredStates: string[];
}

export interface ProofContract {
  selectors: ProofSelector[];
  /** The Section 7.1 minimum-proof statement for the component. */
  minimumProof: string;
}

export interface TypographyRole {
  role: string;
  /** Design record field that sizes this role, when the design $def has one. */
  designField: string | null;
  purpose: string;
}

/**
 * Per-component variation descriptors (MG-018 acceptance: two branded jobs
 * must not become visually identical merely because they use the same
 * primitive). These record how composition, framing, type treatment, and
 * pacing are driven by the job's design inputs rather than fixed.
 */
export interface VariationDescriptor {
  composition: string;
  framing: string;
  typeTreatment: string;
  pacing: string;
}

export interface ComponentExample {
  id: string;
  kind: "scene" | "storyboard_beat";
  description: string;
  /** A complete scene document, present when kind is "scene". */
  scene: Record<string, unknown> | null;
  /** A Section 5.3 storyboard beat, present when kind is "storyboard_beat". */
  beat: Record<string, unknown> | null;
}

/** A registered test that covers the component. */
export interface ComponentTestRef {
  id: string;
  description: string;
  /** Where the test lives (runner path or suite name). */
  evidence: string;
}

/**
 * How this component proves actual subject motion (Directive MG-032).
 * Optional and populated only for components with an implemented
 * measurement family in the motion-proof layer: absence means no
 * automated motion proof exists for the component yet, so a motion
 * claim for it routes to human judgment or is refused by the
 * evaluator, never waved through.
 */
export interface MotionProofDeclaration {
  /** The named subjects whose motion is the claim ("data_marks",
   * "traveling_object"). */
  subjects: string;
  /** The raster measurement the evaluator applies inside the subject
   * region ("accent_run_extent", "accent_centroid"). */
  measurement: string;
  /** The transformation family the evaluator implements
   * ("linear_reveal", "path_transit"). */
  transformation: string;
  /**
   * "not_claimed": the component makes no depth or 3D claim, and none
   * may be inferred from it. "requires_occlusion_or_depth_evidence":
   * the component may claim depth, and a claim without that evidence
   * is refused by the evaluator (MG_CAPABILITY_UNSUPPORTED).
   */
  depthPolicy: "not_claimed" | "requires_occlusion_or_depth_evidence";
}

/** One registered version of one component. */
export interface ComponentEntry {
  componentId: string;
  version: string;
  name: string;
  availability: ComponentAvailability;
  /** Why dispatch is refused; null exactly when availability is "available". */
  unavailableReason: string | null;
  /** The directive item that owns this component's production bundle. */
  owningItem: string;
  /** What visible change the component performs (Section 7.1). */
  visibleChange: string;
  /** What the component means: the viewer-facing purpose it serves. */
  semanticPurpose: string;
  engines: ProductionEngine[];
  defaultEngine: ProductionEngine | "either" | "qualified-native-integration";
  /**
   * The closed input schema (JSON Schema object with
   * additionalProperties: false; the catalog has no escape hatch).
   * Null while the component is unavailable.
   */
  inputSchema: Record<string, unknown> | null;
  /** Where the input schema comes from; null while unavailable. */
  schemaSource: string | null;
  assetRequirements: AssetRequirement[];
  dataRequirements: DataRequirement[];
  layoutVariants: LayoutVariant[];
  timelineContract: TimelineContract;
  /** Null while the component is unavailable. */
  proofContract: ProofContract | null;
  /** MG-032 motion proof declaration; null or absent while no
   * automated motion-proof family is implemented for the component. */
  motionProof?: MotionProofDeclaration | null;
  typographyRoles: TypographyRole[];
  variation: VariationDescriptor;
  examples: ComponentExample[];
  tests: ComponentTestRef[];
  /** License and provenance note for the primitive and its examples. */
  provenance: string;
}

/**
 * The engineering review record a governed custom registration must carry.
 * This is an engineering review of the component bundle, never an owner
 * approval of a job: Section 5.1 forbids code from writing owner approval.
 */
export interface ReviewAttestation {
  reviewer: string;
  decision: "approved";
  statement: string;
  reviewedAt: string;
}

/** The governed custom-component registration call (Section 16.1). */
export interface RegistrationBundle {
  entry: ComponentEntry;
  reviewAttestation: ReviewAttestation;
}

/**
 * The concrete layout a component computes from one design record for one
 * layout variant. Two jobs that share a primitive but carry different
 * design records produce different descriptors; that difference is the
 * anti-template evidence MG-018 owns.
 */
export interface LayoutDescriptor {
  componentId: string;
  componentVersion: string;
  layoutVariant: string;
  designId: string;
  palette: { background: string; ink: string; accent: string };
  /** The variant layout block (plot box, headline box, row positions). */
  geometry: Record<string, unknown>;
  typeScalePx: {
    headline: number;
    label: number;
    value: number;
    disclosure: number;
  };
  composition: string;
  framing: string;
  typeTreatment: string;
  pacing: string;
}
