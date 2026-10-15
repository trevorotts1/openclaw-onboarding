// Motion proof types (Directive MG-032). A motion proof case declares,
// for one required non-text motion beat, the named subject and the
// intended transformation, and the evaluator confirms the subject's
// geometry or identity in rendered frames at the declared checkpoint
// states (initial, intermediate proof, final). The case document shape
// is governed by references/motion-assertion-schema.json, owned by this
// item and deliberately separate from the canonical contracts schema.
//
// Verdict vocabulary (also used by the proof record):
// - "pass": every required assertion was measured and agreed.
// - "fail": the artifact was measured and the subject did not perform
//   the declared transformation, or required evidence was incomplete.
// - "refused": the evaluation could not be performed as specified
//   (malformed case, missing input, unimplemented measurement family,
//   a depth claim without depth evidence, tampered bindings). A
//   refusal is never a pass and never a measurement of the artifact.
// - "needs_human_judgment": the case routes to human judgment and no
//   human verdict record was supplied. Nothing was fabricated.
//
// Exit codes and categories are the Section 16.9 stable vocabulary.

export type MotionTransformationKind =
  | "linear_reveal"
  | "path_transit"
  | "depth_transit"
  | "semantic_change";

export type MotionEvidenceKind =
  | "geometry"
  | "decoded_frame"
  | "full_fps_clip"
  | "occlusion"
  | "depth";

export type CheckpointRole = "initial" | "proof" | "final" | "hold";

export interface SourceBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MotionSubject {
  id: string;
  role: "data_mark" | "traveling_object" | "layered_subject" | "semantic_subject";
  /** Subject region in source pixels, when the component's design
   * records do not supply one (synthetic raster fixtures). */
  region?: SourceBox;
}

export interface MotionCheckpoint {
  role: CheckpointRole;
  frame: number;
}

export interface OcclusionCheckpoint {
  subject_id: string;
  occluder_id: string;
  frame: number;
  expected_visible_fraction: number;
}

export interface MotionProofCase {
  schema_version: "1.0";
  kind: "motion_proof_case";
  id: string;
  job_id: string;
  scene_id: string;
  beat_id?: string | null;
  component_id: string;
  subjects: MotionSubject[];
  subject_appearance?: { color: string; notes?: string };
  /** Region (source px) inside which raster identification happens
   * for region-based families (occlusion). */
  subject_region?: SourceBox;
  transformation: {
    kind: MotionTransformationKind;
    interval: { start_frame: number; end_frame_exclusive: number } | null;
    claims_depth: boolean;
  };
  checkpoints: MotionCheckpoint[];
  occlusion_checkpoints?: OcclusionCheckpoint[];
  evidence_required: MotionEvidenceKind[];
  judgment: { mode: "automated" | "human"; reason?: string | null };
  tolerances?: {
    geometry_px?: number;
    decoded_px?: number;
    position_px?: number;
    visible_fraction?: number;
  };
}

export interface HumanVerdict {
  reviewer_id: string;
  decision: "approved" | "rejected";
  reviewed_at: string;
  note?: string | null;
}

export type MotionVerdict = "pass" | "fail" | "refused" | "needs_human_judgment";

export interface MotionFinding {
  category: string;
  message: string;
}

/** One checkpoint assertion outcome inside the proof record. */
export interface CheckpointAssertion {
  role: CheckpointRole;
  frame: number;
  /** What the scene specification says the subject must measure. */
  expected: number[];
  /** The value derived from the renderer's own frame functions or
   * layout geometry (the "geometry" evidence), when applicable. */
  geometry_measured: number[] | null;
  /** The value measured in decoded raster, restricted to the subject
   * region (the "decoded_frame" evidence). */
  raster_measured: number[] | null;
  verdict: "pass" | "fail" | "not_evaluated";
  detail: string;
}

export interface MotionProofRecord {
  schema_version: "1.0";
  kind: "motion_proof_record";
  item: "MG-032";
  case_id: string;
  job_id: string;
  scene_id: string;
  component_id: string;
  verdict: MotionVerdict;
  /** The first blocking Section 16.9 category, or null on a pass. */
  category: string | null;
  exit_code: number;
  bindings: {
    video_sha256: string | null;
    coverage_job_id: string | null;
    coverage_verdict: string | null;
    review_label: string | null;
    review_engine: string | null;
  };
  assertions: CheckpointAssertion[];
  /** Occlusion observations, present for depth_transit cases that
   * carried occlusion checkpoints. */
  occlusion: Array<{
    frame: number;
    subject_id: string;
    occluder_id: string;
    expected_visible_fraction: number;
    measured_visible_fraction: number | null;
    verdict: "pass" | "fail" | "not_evaluated";
  }> | null;
  /** Pixel change measured OUTSIDE the subject regions between the
   * initial and final checkpoint frames. Informational: it records
   * how much decorative activity surrounded the subject, so a failed
   * subject check next to a large context change is visibly a subject
   * failure and not a dead video. */
  context_change: { mean_abs_diff: number; frames: [number, number] } | null;
  clip: {
    path: string;
    frames: number;
    fps: string;
    sha256: string;
  } | null;
  frames: Array<{ frame: number; path: string; sha256: string }>;
  human_verdict: HumanVerdict | null;
  findings: MotionFinding[];
  generated_at: string;
}

export interface MotionProofResult {
  record: MotionProofRecord;
  exitCode: number;
}

/** Where the artifacts live. Artifact locations are evaluation inputs,
 * never part of the case document: the same case can be evaluated
 * against a preview, a final, or a suspect artifact. */
export interface MotionProofInputs {
  caseDoc: unknown;
  videoPath: string;
  coverageRecordPath: string;
  outputDir: string;
  /** Scene-specification source for chart components (a validated job
   * directory the geometry is derived from). */
  jobDir?: string;
  /** Scene-specification source for diagram components (the diagram
   * scene document whose resolved frame functions derive geometry). */
  diagramScenePath?: string;
  /** Font binary the diagram layout measurer uses. Defaults to the
   * fixture Liberation Sans path the MG-017 tests use. */
  fontPath?: string;
  humanVerdict?: HumanVerdict | null;
}
