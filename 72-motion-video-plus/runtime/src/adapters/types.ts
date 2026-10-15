// Adapter contract types for the Skill 72 Motion Graphics V2 runtime
// (Directive MG-004, Section 5.5). Both production engines, Hyperframes and
// Remotion, plus the legacy compatibility renderer, expose the same typed
// interface: validated jobs in, structured evidence out. Renderer-specific
// assumptions must not leak into storytelling, task routing, or delivery, so
// every operation returns evidence that names the engine and the exact
// runtime that produced it.
//
// Frame ranges are half-open, [startFrame, endFrameExclusive), everywhere in
// this layer (Directive Section 5.4). Engine APIs that use inclusive ranges
// are adapted inside the engine adapters (MG-005, MG-006), never here.
//
// Structural job types come from the generated contracts types
// (src/validation/generated-types.ts); they are not redefined by hand.

import type { ExportRecord } from "../export/metadata";
import type { PreviewOptions, PreviewReviewRecord } from "../preview/types";
import type { Approval, ArtifactRef, Manifest } from "../validation/generated-types";
import type { ErrorCategory, Finding } from "../validation/semantics";

export type { PreviewOptions, PreviewReviewRecord };

/** The engines an adapter can serve. "legacy" is the V1 deterministic stack,
 * reachable only through the declared compatibility path (see routing.ts). */
export type Engine = "hyperframes" | "remotion" | "legacy";

/** The two V2 production engines. */
export type ProductionEngine = "hyperframes" | "remotion";

export const PRODUCTION_ENGINES: ProductionEngine[] = ["hyperframes", "remotion"];
export const ALL_ENGINES: Engine[] = ["hyperframes", "remotion", "legacy"];

/** Half-open frame range: frames startFrame .. endFrameExclusive - 1. */
export interface FrameRange {
  startFrame: number;
  endFrameExclusive: number;
}

/**
 * Identity of the exact runtime an evidence object was produced by. The
 * engine version and the runtime-lock identity come from a shared-runtime
 * probe record; both are null when no probe record exists, and evidence
 * must say so rather than invent a version.
 */
export interface RuntimeIdentity {
  engine: Engine;
  /** Exact installed engine version, or null when unprobed. */
  engineVersion: string | null;
  /** Identity (path or content id) of the runtime lock the version was read
   * from, or null when no lock record exists. */
  runtimeLockId: string | null;
  /** Node version of the probing process, for example "v24.20.0". */
  nodeVersion: string;
  /** Platform descriptor, for example "linux x64". */
  platform: string;
  /** ISO timestamp of the probe record, or null when unprobed. */
  probedAt: string | null;
}

/** Per-engine capability record: what one engine can do on this machine,
 * as stated by measured evidence. See capabilities.ts for the matrix file
 * format and the honesty rules that govern these records. */
export interface EngineCapabilityRecord {
  engine: Engine;
  /** "ready" requires a current probe record with a version and a launch
   * record behind it. "unprobed" means no record exists yet. "unavailable"
   * means a probe ran and the engine did not come up. */
  probeStatus: "ready" | "unprobed" | "unavailable";
  installedVersion: string | null;
  runtimeLockId: string | null;
  probedAt: string | null;
  platform: string | null;
  /** Supported output codecs, for example "h264", "prores", "vp9". */
  codecs: string[];
  transparency: {
    /** True only when an alpha-carrying export was actually probed. */
    alphaVideo: boolean;
    /** Alpha-capable delivery profiles confirmed for this engine. */
    profiles: string[];
  };
  /** Media types the engine can consume, for example "image", "video",
   * "audio", "svg", "font". */
  mediaTypes: string[];
  /** Qualified 3D features, named by the integration that provides them,
   * for example "webgl-depth". Empty until a 3D integration is qualified. */
  features3d: string[];
  /** Human-readable evidence notes: what was measured, when, and where the
   * underlying record lives. Empty when nothing has been measured. */
  evidence: string[];
}

/** The capability matrix: one record per engine. Serialized as
 * references/renderer-capabilities.json and consumed by routing. */
export interface CapabilityMatrix {
  schemaVersion: "1.0";
  /** ISO timestamp of the last refresh from runtime records, or null when
   * the matrix has never been refreshed from a record. */
  generatedAt: string | null;
  /** Where the records in this matrix came from. */
  source: string;
  engines: EngineCapabilityRecord[];
}

/** A job directory that has passed the MG-007 contracts validation layer
 * with zero findings. Adapters only ever receive validated jobs. */
export interface ValidatedMotionJob {
  jobDir: string;
  jobId: string;
  manifest: Manifest;
}

/** A validated job carrying an approval record for final render. The
 * dispatcher checks the decision before any adapter sees the job. */
export interface ApprovedMotionJob extends ValidatedMotionJob {
  approval: Approval;
}

/** Result of an adapter runtime probe. */
export interface RuntimeEvidence {
  engine: Engine;
  runtime: RuntimeIdentity;
  status: "ready" | "unprobed" | "unavailable";
  capabilities: EngineCapabilityRecord | null;
  checkedAt: string;
  detail: string;
}

/** Result of validating a job for one engine. */
export interface ValidationEvidence {
  engine: Engine;
  runtime: RuntimeIdentity;
  jobId: string;
  valid: boolean;
  findings: Finding[];
  firstErrorCategory: ErrorCategory | null;
  checkedAt: string;
}

/** Result of a render operation (still, preview, or final). */
export interface ArtifactEvidence {
  engine: Engine;
  runtime: RuntimeIdentity;
  jobId: string;
  kind: "still" | "preview" | "final";
  /** Produced artifacts with content hashes. */
  artifacts: ArtifactRef[];
  /** Actual output paths on disk, mirroring the artifact refs. */
  outputPaths: string[];
  /** Exit code of the engine process, or 0 for an in-process render. */
  exitCode: number;
  /** Captured stderr text (tail) when the engine ran as a process, else null. */
  stderrLog: string | null;
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  /** MG-024 preview review record: present on preview evidence.
   * Carries the source hash, the preview artifact hash, the scale
   * factor, and the fps and dimensions of both the final and the
   * preview, and labels a reduced-fps artifact "rough_layout_only"
   * so the full-fps motion gate can refuse it as motion evidence
   * (see src/preview/gate.ts). The same record is written as a
   * sidecar beside the artifact: preview.review.json for the
   * canonical preview, preview-<variant>.review.json for a scaled or
   * rough variant; the Hyperframes adapter also embeds it in its
   * render receipt. */
  previewReview?: PreviewReviewRecord;
  /** MG-040 export record: present on final evidence when the job's
   * delivery profile was exported through the export layer. The
   * record states the profile, the measured stream codec, and the
   * measured alpha verdict (never the profile's promise), and is
   * also written as a sidecar beside the artifact:
   * <artifact>.export-record.json. See src/export/metadata.ts. */
  exportRecord?: ExportRecord;
}

/** Result of a motion inspection over a half-open frame range. */
export interface MotionEvidence {
  engine: Engine;
  runtime: RuntimeIdentity;
  jobId: string;
  range: FrameRange;
  assertionsChecked: number;
  assertionsPassed: number;
  observations: string[];
  inspectedAt: string;
}

/**
 * Cooperative call context. The dispatcher creates one per operation and
 * hands it to adapters that expose beginCall; adapters pass the signal to
 * subprocesses and check it at await points. The dispatcher enforces the
 * deadline and cancellation even when an adapter never settles: it abandons
 * the operation promise and invokes cancel.
 */
export interface CallContext {
  jobId: string;
  signal: AbortSignal;
  timeoutMs: number;
  deadlineEpochMs: number;
}

/**
 * The Section 5.5 adapter interface. Every production adapter implements
 * exactly these operations. Implementations may accept an optional trailing
 * options argument (for example a CallContext) without breaking the
 * interface; callers must not depend on that.
 */
export interface MotionRendererAdapter {
  readonly engine: Engine;
  probeRuntime(): Promise<RuntimeEvidence>;
  validate(job: ValidatedMotionJob): Promise<ValidationEvidence>;
  renderStill(job: ValidatedMotionJob, frame: number): Promise<ArtifactEvidence>;
  renderPreview(job: ValidatedMotionJob, opts?: PreviewOptions): Promise<ArtifactEvidence>;
  renderFinal(job: ApprovedMotionJob): Promise<ArtifactEvidence>;
  inspectMotion(job: ValidatedMotionJob, range: FrameRange): Promise<MotionEvidence>;
  cancel(jobId: string): Promise<void>;
  /** Optional cooperative-cancellation hook used by the dispatcher. */
  beginCall?(ctx: CallContext): void;
}

/** Adapter-layer error categories. The four MG-007 contract categories keep
 * their meaning; the categories below are added by MG-004 and documented in
 * references/renderer-routing.md. */
export type AdapterErrorCategory =
  | ErrorCategory
  | "MG_ENGINE_MISSING"
  | "MG_CAPABILITY_MISSING"
  | "MG_CAPABILITY_UNSUPPORTED"
  | "MG_APPROVAL_REQUIRED"
  | "MG_RENDER_FAILED"
  | "MG_TIMEOUT"
  | "MG_CANCELLED";

/** Section 16.9 exit classes: 2 contract, 3 dependency, 4 approval,
 * 5 render, 8 cancelled, 9 security. */
export function exitClassForCategory(category: AdapterErrorCategory): number {
  switch (category) {
    case "MG_SCHEMA_INVALID":
    case "MG_UNKNOWN_COMPONENT":
    case "MG_MODE_MISMATCH":
    case "MG_TIMELINE_INVALID":
      return 2;
    case "MG_ENGINE_MISSING":
    case "MG_CAPABILITY_MISSING":
    case "MG_CAPABILITY_UNSUPPORTED":
      return 3;
    case "MG_APPROVAL_REQUIRED":
      return 4;
    case "MG_RENDER_FAILED":
    case "MG_TIMEOUT":
      return 5;
    case "MG_CANCELLED":
      return 8;
    case "MG_SECURITY_VIOLATION":
      return 9;
    default:
      return 5;
  }
}

/** Structured adapter-layer failure. Carries the stable category, the
 * Section 16.9 exit class, the engine involved when one is known, and the
 * validation findings when the failure came from the contracts layer. */
export class AdapterError extends Error {
  readonly category: AdapterErrorCategory;
  readonly exitClass: number;
  readonly engine: Engine | null;
  readonly retryable: boolean;
  readonly findings: Finding[];
  readonly stderrLog: string | null;

  constructor(opts: {
    category: AdapterErrorCategory;
    message: string;
    engine?: Engine | null;
    retryable?: boolean;
    findings?: Finding[];
    stderrLog?: string | null;
  }) {
    super(opts.message);
    this.name = "AdapterError";
    this.category = opts.category;
    this.exitClass = exitClassForCategory(opts.category);
    this.engine = opts.engine ?? null;
    this.retryable = opts.retryable ?? false;
    this.findings = opts.findings ?? [];
    this.stderrLog = opts.stderrLog ?? null;
  }
}
