// Status model types for MG-046: one task identity and truthful
// production state from intake through delivery.
//
// The model keeps three axes strictly separate, because conflating
// them is how a task gets marked complete before its deliverables
// exist:
//
// - Production statuses (this module's axis): RENDERED, QC_PASSED,
//   APPROVED, DELIVERED. They advance only on production evidence:
//   a render receipt, a final-QC verdict over the final bytes, a
//   production approval event verified by the MG-025 gate layer, and
//   a delivery that names every mandatory artifact.
// - Release and build statuses (versions, bundles, pull requests,
//   tags) belong to the release process. They live on their own
//   field of the status document and production events never write
//   to it.
// - Code-review approval is a different system from production
//   approval. Approval events recorded here are production approvals
//   only: each carries the MG-025 gate that verified it, its scope
//   (design, preview, delivery), and its authority basis. A record
//   that did not come through a gate cannot be filed as one.

import type { Phase } from "../orchestrator/phases";

/** The production statuses, in lifecycle order. */
export const PRODUCTION_STATUSES = [
  "RENDERED",
  "QC_PASSED",
  "APPROVED",
  "DELIVERED",
] as const;

export type ProductionStatus = (typeof PRODUCTION_STATUSES)[number];

/** True when `status` is at or beyond `target` on the production axis. */
export function productionStatusAtLeast(
  status: ProductionStatus | null,
  target: ProductionStatus
): boolean {
  if (status === null) return false;
  return PRODUCTION_STATUSES.indexOf(status) >= PRODUCTION_STATUSES.indexOf(target);
}

/** One task identity, from intake through delivery. For a motion
 * insert, the task identity is the PARENT job's task (the MG-037
 * bridge's parent identity, carried in the manifest's parent
 * record): the component returns to that task instead of creating
 * an unrelated full production task. For a standalone job, the task
 * identity is the job's own. */
export interface TaskIdentity {
  jobId: string;
  companyId: string;
  /** The Command Center task this work reports under. */
  taskId: string;
  /** "parent" when the manifest names a parent job (an insert);
   * "own" for a standalone job. */
  taskOrigin: "parent" | "own";
  parentJobId: string | null;
  parentTaskId: string | null;
  /** The board campaign this task's stage lives on: the parent's
   * campaign for an insert (no second campaign is created), the
   * job's own campaign for a standalone job. */
  boardJobId: string;
  /** The board stage slug for this motion task. */
  stageSlug: string;
}

/** A production approval event, as verified by an MG-025 gate. The
 * discriminant `kind` is the literal "production_approval": code
 * review approval is never recorded in this list. */
export interface ProductionApprovalRecord {
  kind: "production_approval";
  gate: "design" | "render" | "delivery";
  scope: "design" | "preview" | "delivery";
  approvalId: string;
  decision: string;
  subjectRevision: string | null;
  authorityBasis: string | null;
  at: string;
}

export interface StatusArtifact {
  /** Delivery kind: one of the manifest's delivery.required kinds
   * ("mp4", "poster", "source_package", "placement_metadata",
   * "audio_stems", "captions") or another named kind. */
  kind: string;
  path: string;
  sha256: string | null;
  bytes: number | null;
}

export interface StatusQcRecord {
  verdict: "pass" | "fail";
  artifactPath: string;
  artifactSha256: string;
  source: string;
  at: string;
}

export interface StatusRecovery {
  /** Cache session work directory that holds the resume state. */
  cacheWorkDir: string | null;
  cacheJobKey: string | null;
  lastFailure: { category: string; message: string; at: string } | null;
  failedScenes: string[];
}

/** The current status document for one task. Written atomically to
 * working/checkpoints/motion-status.json inside the job directory;
 * the append-only event stream beside it is
 * motion-status-events.jsonl. The Skill 47 bridge
 * (47-movie-producer/scripts/motion_status.py) consumes this
 * document and transports it to the Command Center board. */
export interface MotionStatusDoc {
  schemaVersion: "1.0";
  item: "MG-046";
  identity: TaskIdentity;
  mode: string;
  executionContext: "fixture" | "production";
  /** True for fixture-context jobs: every status here is diagnostic
   * evidence with no production delivery privilege (MG-025). */
  diagnostic: boolean;
  phase: Phase | null;
  productionStatus: ProductionStatus | null;
  /** Release and build axis. Production code never advances this;
   * it stays null until the release process records its own state. */
  releaseStatus: string | null;
  engine: string | null;
  exportProfile: string | null;
  exportRoute: { kind: string; confirmedBy: string } | null;
  artifacts: StatusArtifact[];
  approvals: ProductionApprovalRecord[];
  qc: StatusQcRecord | null;
  recovery: StatusRecovery | null;
  /** Mandatory delivery kinds (from the manifest) with no artifact
   * recorded. Non-empty blocks DELIVERED, by name. */
  missingMandatory: string[];
  board: {
    transport: string;
    lastSync: { ok: boolean; at: string; detail: string } | null;
  };
  deliveredAt: string | null;
  updatedAt: string;
}

/** One structured status event. Every emission the directive names
 * (phase transitions, progress, render receipts, review verdicts,
 * recovery points, artifact locations) is a kind here. */
export type StatusEventKind =
  | "phase_transition"
  | "progress"
  | "render_receipt"
  | "review_verdict"
  | "approval_event"
  | "recovery_point"
  | "artifact_location"
  | "failure"
  | "delivery_blocked"
  | "delivered";

export interface StatusEvent {
  seq: number;
  at: string;
  kind: StatusEventKind;
  jobId: string;
  taskId: string;
  phase: Phase | null;
  productionStatus: ProductionStatus | null;
  detail: Record<string, unknown>;
}

/** Board transport hook. Implementations move the status document
 * toward the Command Center board (or a test double). The tracker
 * calls it after every persisted change and treats every failure as
 * non-fatal: board transport is fail-soft (integration V02) and a
 * transport failure never fails the production. */
export interface BoardTransport {
  sync(doc: MotionStatusDoc): Promise<{ ok: boolean; detail: string }>;
}

/** Named status-layer failure. Categories follow Section 16.9 exit
 * classes: delivery incompleteness is a delivery-class refusal
 * raised before any Done claim, never a silent pass. */
export class StatusError extends Error {
  readonly category: string;
  readonly exitClass: number;
  readonly missing: string[];

  constructor(opts: { category: string; message: string; exitClass: number; missing?: string[] }) {
    super(opts.message);
    this.name = "StatusError";
    this.category = opts.category;
    this.exitClass = opts.exitClass;
    this.missing = opts.missing ?? [];
  }
}
