// The motion status tracker (MG-046): owns the status document and
// the structured event stream for one task, from intake through
// delivery.
//
// One task identity: the tracker derives it from the job manifest.
// An insert job's manifest names its parent (the MG-037 bridge's
// parent identity: parent job id and parent task id), and the
// tracker reports the component under the PARENT task, returning to
// the parent job instead of creating an unrelated full production
// task. A standalone job reports under its own identity. Reopening
// a tracker on a job directory resumes the same document and the
// same event sequence: a retry never mints a second identity.
//
// Emissions: every state change appends one structured event to
// working/checkpoints/motion-status-events.jsonl and rewrites
// working/checkpoints/motion-status.json atomically. The board
// transport hook is fail-soft by construction: a transport that
// throws or reports failure is recorded on the document and never
// fails the production (integration V02). The transport of record
// is the Skill 47 bridge, 47-movie-producer/scripts/motion_status.py,
// which reads this document and drives cc_board.
//
// Production statuses advance only on evidence: RENDERED on a
// render receipt, QC_PASSED on a passing final-QC verdict over the
// rendered artifact, APPROVED when the MG-025 delivery gate passes,
// DELIVERED when delivery readiness is complete (every mandatory
// artifact measured on disk, final QC passed, delivery approval in
// force). Missing mandatory artifacts block DELIVERED by name.

import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, extname, isAbsolute, join } from "node:path";
import type { ArtifactEvidence, ValidatedMotionJob } from "../adapters/types";
import type { RoutingDecision } from "../adapters/routing";
import type { ExportSelection } from "../export/select";
import {
  evaluateDeliveryGate,
  type FinalQcRecord,
  type GateResult,
} from "../orchestrator/gate";
import type { GateRuntimeIdentity } from "../orchestrator/revision";
import type { Phase } from "../orchestrator/phases";
import { buildDeliveryReceipt, evaluateDeliveryReadiness, type DeliveryReceipt } from "./receipt";
import {
  StatusError,
  productionStatusAtLeast,
  type BoardTransport,
  type MotionStatusDoc,
  type ProductionApprovalRecord,
  type StatusArtifact,
  type StatusEvent,
  type StatusEventKind,
  type TaskIdentity,
} from "./types";

export const STATUS_DIR_PARTS = ["working", "checkpoints"] as const;
export const STATUS_DOC_NAME = "motion-status.json";
export const STATUS_EVENTS_NAME = "motion-status-events.jsonl";
export const DELIVERY_RECEIPT_NAME = "delivery-receipt.json";

function nowIso(): string {
  return new Date().toISOString();
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return (slug || "motion").slice(0, 64);
}

/** Map a produced file to its delivery kind. The manifest's
 * delivery.required kinds predate alpha profiles, so every video
 * container (.mp4, .mov, .webm) is the "mp4" delivery kind; the
 * receipt records the real path, so the container stays truthful. */
export function deliveryKindForPath(path: string): string {
  const ext = extname(path).toLowerCase();
  if (ext === ".mp4" || ext === ".mov" || ext === ".webm" || ext === ".mkv") return "mp4";
  if (ext === ".png" || ext === ".jpg" || ext === ".jpeg") return "poster";
  if (basename(path).includes("placement")) return "placement_metadata";
  return ext.replace(/^\./, "") || "artifact";
}

export interface TrackerOptions {
  transport?: BoardTransport;
  transportName?: string;
}

export class MotionStatusTracker {
  readonly jobDir: string;
  readonly doc: MotionStatusDoc;
  private seq: number;
  private readonly transport?: BoardTransport;
  private readonly requiredKinds: string[];

  private constructor(init: {
    jobDir: string;
    doc: MotionStatusDoc;
    seq: number;
    transport?: BoardTransport;
    requiredKinds: string[];
  }) {
    this.jobDir = init.jobDir;
    this.doc = init.doc;
    this.seq = init.seq;
    this.transport = init.transport;
    this.requiredKinds = init.requiredKinds;
  }

  static open(jobDir: string, job: ValidatedMotionJob, opts?: TrackerOptions): MotionStatusTracker {
    const manifest = job.manifest;
    const parent = manifest.parent ?? null;
    const identity: TaskIdentity = {
      jobId: manifest.job_id,
      companyId: manifest.company_id,
      taskId: parent ? parent.task_id : manifest.job_id,
      taskOrigin: parent ? "parent" : "own",
      parentJobId: parent ? parent.job_id : null,
      parentTaskId: parent ? parent.task_id : null,
      boardJobId: parent ? parent.job_id : manifest.job_id,
      stageSlug: `motion-${slugify(manifest.job_id)}`,
    };
    const requiredKinds = [...(manifest.delivery.required ?? [])];
    const dir = join(jobDir, ...STATUS_DIR_PARTS);
    mkdirSync(dir, { recursive: true });
    const docPath = join(dir, STATUS_DOC_NAME);
    const eventsPath = join(dir, STATUS_EVENTS_NAME);

    let doc: MotionStatusDoc;
    let seq = 0;
    let resumed = false;
    if (existsSync(docPath)) {
      try {
        const parsed = JSON.parse(readFileSync(docPath, "utf8")) as MotionStatusDoc;
        if (parsed && parsed.identity && parsed.identity.jobId === manifest.job_id) {
          doc = parsed;
          resumed = true;
          if (existsSync(eventsPath)) {
            seq = readFileSync(eventsPath, "utf8")
              .split("\n")
              .filter((l) => l.trim().length > 0).length;
          }
        } else {
          doc = freshDoc(identity, job, opts);
        }
      } catch {
        doc = freshDoc(identity, job, opts);
      }
    } else {
      doc = freshDoc(identity, job, opts);
    }
    doc.identity = identity;
    doc.missingMandatory = [...requiredKinds];
    const tracker = new MotionStatusTracker({
      jobDir,
      doc,
      seq,
      transport: opts?.transport,
      requiredKinds,
    });
    tracker.persist();
    tracker.emit("phase_transition", {
      phase: doc.phase ?? "CREATED",
      resumed,
      note: resumed
        ? "Tracker reopened on the existing status document; the same task identity and event sequence continue."
        : "Status tracking opened for this task.",
    });
    return tracker;
  }

  get identity(): TaskIdentity {
    return this.doc.identity;
  }

  // ------------------------------------------------------------------
  // Emissions
  // ------------------------------------------------------------------

  private emit(kind: StatusEventKind, detail: Record<string, unknown>): StatusEvent {
    const event: StatusEvent = {
      seq: this.seq,
      at: nowIso(),
      kind,
      jobId: this.doc.identity.jobId,
      taskId: this.doc.identity.taskId,
      phase: this.doc.phase,
      productionStatus: this.doc.productionStatus,
      detail,
    };
    this.seq += 1;
    const eventsPath = join(this.jobDir, ...STATUS_DIR_PARTS, STATUS_EVENTS_NAME);
    appendFileSync(eventsPath, `${JSON.stringify(event)}\n`, "utf8");
    return event;
  }

  private persist(): void {
    this.doc.updatedAt = nowIso();
    const dir = join(this.jobDir, ...STATUS_DIR_PARTS);
    mkdirSync(dir, { recursive: true });
    const docPath = join(dir, STATUS_DOC_NAME);
    const tmp = `${docPath}.tmp`;
    writeFileSync(tmp, `${JSON.stringify(this.doc, null, 2)}\n`, "utf8");
    renameSync(tmp, docPath);
  }

  /** Persist, emit, and offer the document to the board transport.
   * The transport runs last and fail-soft: its outcome is recorded
   * on the document without another sync (no recursion). */
  private async commit(kind: StatusEventKind, detail: Record<string, unknown>): Promise<void> {
    this.refreshMissing();
    this.persist();
    this.emit(kind, detail);
    if (this.transport) {
      try {
        const outcome = await this.transport.sync(this.doc);
        this.doc.board.lastSync = { ok: outcome.ok, at: nowIso(), detail: outcome.detail };
      } catch (err) {
        this.doc.board.lastSync = {
          ok: false,
          at: nowIso(),
          detail: `transport threw (fail-soft, production unaffected): ${(err as Error).message}`,
        };
      }
      this.persist();
    }
  }

  private refreshMissing(): void {
    const readiness = evaluateDeliveryReadiness(this.jobDir, this.doc, this.requiredKinds);
    this.doc.missingMandatory = readiness.missing.filter(
      (m) => m !== "final_qc" && m !== "delivery_approval" && m !== "production_context"
    );
  }

  // ------------------------------------------------------------------
  // Lifecycle emissions
  // ------------------------------------------------------------------

  async setPhase(phase: Phase, note?: string): Promise<void> {
    this.doc.phase = phase;
    await this.commit("phase_transition", { phase, note: note ?? null });
  }

  async progress(detail: Record<string, unknown>): Promise<void> {
    await this.commit("progress", detail);
  }

  async recordRouting(routing: RoutingDecision, exportSelection: ExportSelection | null): Promise<void> {
    this.doc.engine = routing.assemblyOwner;
    if (exportSelection) {
      this.doc.exportProfile = exportSelection.profile.id;
      this.doc.exportRoute = {
        kind: exportSelection.route.kind,
        confirmedBy: exportSelection.confirmedBy,
      };
    }
    await this.commit("progress", {
      routing: routing.assignments.map((a) => ({
        sceneId: a.sceneId,
        engine: a.engine,
        reasonCode: a.reasonCode,
      })),
      assemblyOwner: routing.assemblyOwner,
      exportConfirmedBy: exportSelection?.confirmedBy ?? null,
    });
  }

  /** Record a render receipt: the job is RENDERED, with the
   * evidence's artifacts recorded as artifact locations. */
  async recordRenderReceipt(evidence: ArtifactEvidence): Promise<void> {
    this.doc.engine = evidence.engine;
    for (const ref of evidence.artifacts) {
      this.recordArtifact(deliveryKindForPath(ref.path), ref.path, ref.sha256);
    }
    if (!productionStatusAtLeast(this.doc.productionStatus, "RENDERED")) {
      this.doc.productionStatus = "RENDERED";
    }
    this.doc.phase = "FINAL_RENDERED";
    await this.commit("render_receipt", {
      engine: evidence.engine,
      engineVersion: evidence.runtime.engineVersion,
      runtimeLockId: evidence.runtime.runtimeLockId,
      kind: evidence.kind,
      artifacts: evidence.artifacts,
      exitCode: evidence.exitCode,
      durationMs: evidence.durationMs,
      exportRecord: evidence.exportRecord ?? null,
    });
  }

  /** Record one artifact location (poster, package, metadata). */
  async recordArtifactLocation(kind: string, path: string, sha256?: string | null): Promise<void> {
    this.recordArtifact(kind, path, sha256 ?? null);
    await this.commit("artifact_location", { kind, path });
  }

  private recordArtifact(kind: string, path: string, sha256: string | null): void {
    const abs = isAbsolute(path) ? path : join(this.jobDir, path);
    const bytes = existsSync(abs) ? statSync(abs).size : null;
    const existing = this.doc.artifacts.findIndex((a) => a.kind === kind);
    const record: StatusArtifact = { kind, path, sha256, bytes };
    if (existing >= 0) this.doc.artifacts[existing] = record;
    else this.doc.artifacts.push(record);
  }

  /** Record a review verdict: a passing final-QC verdict over the
   * rendered artifact advances the job to QC_PASSED. A failed
   * verdict is recorded as evidence and advances nothing. */
  async recordQcVerdict(record: {
    verdict: "pass" | "fail";
    artifactPath: string;
    artifactSha256: string;
    source: string;
  }): Promise<void> {
    this.doc.qc = { ...record, at: nowIso() };
    if (
      record.verdict === "pass" &&
      this.doc.productionStatus === "RENDERED"
    ) {
      this.doc.productionStatus = "QC_PASSED";
      this.doc.phase = "FINAL_QC_PASSED";
    }
    await this.commit("review_verdict", { ...record });
  }

  /** Record a production approval from an MG-025 gate result. Only
   * a passed gate with a verified approval id records anything: the
   * gate is the authority, this tracker is the ledger. A delivery
   * gate pass advances QC_PASSED to APPROVED. */
  async recordGateApproval(gate: GateResult): Promise<void> {
    if (gate.verdict !== "pass" || !gate.approvalId) return;
    const scope =
      gate.gate === "design" ? "design" : gate.gate === "render" ? "preview" : "delivery";
    const record: ProductionApprovalRecord = {
      kind: "production_approval",
      gate: gate.gate,
      scope,
      approvalId: gate.approvalId,
      decision: "approved",
      subjectRevision: gate.revision,
      authorityBasis: gate.authorityBasis,
      at: nowIso(),
    };
    this.doc.approvals = [
      ...this.doc.approvals.filter((a) => !(a.gate === record.gate && a.scope === record.scope)),
      record,
    ];
    if (gate.gate === "delivery" && this.doc.productionStatus === "QC_PASSED") {
      this.doc.productionStatus = "APPROVED";
    }
    await this.commit("approval_event", {
      gate: gate.gate,
      scope,
      approvalId: gate.approvalId,
      authorityBasis: gate.authorityBasis,
      approvalKind: "production_approval",
    });
  }

  /** Record a failure and its recovery point: the same task, the
   * same resume context. Production status does not regress; the
   * failure is evidence, and resume continues this document. */
  async recordFailure(record: {
    category: string;
    message: string;
    cacheWorkDir?: string | null;
    cacheJobKey?: string | null;
    failedScenes?: string[];
  }): Promise<void> {
    const recovery = this.doc.recovery ?? {
      cacheWorkDir: null,
      cacheJobKey: null,
      lastFailure: null,
      failedScenes: [],
    };
    if (record.cacheWorkDir !== undefined) recovery.cacheWorkDir = record.cacheWorkDir;
    if (record.cacheJobKey !== undefined) recovery.cacheJobKey = record.cacheJobKey;
    if (record.failedScenes !== undefined) recovery.failedScenes = record.failedScenes;
    recovery.lastFailure = { category: record.category, message: record.message, at: nowIso() };
    this.doc.recovery = recovery;
    await this.commit("failure", {
      category: record.category,
      message: record.message,
      failedScenes: recovery.failedScenes,
    });
    await this.commit("recovery_point", {
      cacheWorkDir: recovery.cacheWorkDir,
      cacheJobKey: recovery.cacheJobKey,
      resumeWith: "same task identity, same cache session state",
    });
  }

  /** Record a recovery point without a failure (for example when a
   * cache session opens for a render). */
  async recordRecoveryPoint(record: {
    cacheWorkDir: string | null;
    cacheJobKey: string | null;
    failedScenes?: string[];
  }): Promise<void> {
    const recovery = this.doc.recovery ?? {
      cacheWorkDir: null,
      cacheJobKey: null,
      lastFailure: null,
      failedScenes: [],
    };
    recovery.cacheWorkDir = record.cacheWorkDir;
    recovery.cacheJobKey = record.cacheJobKey;
    if (record.failedScenes !== undefined) recovery.failedScenes = record.failedScenes;
    this.doc.recovery = recovery;
    await this.commit("recovery_point", {
      cacheWorkDir: record.cacheWorkDir,
      cacheJobKey: record.cacheJobKey,
    });
  }

  // ------------------------------------------------------------------
  // Delivery
  // ------------------------------------------------------------------

  /**
   * Deliver the job. In a production context the MG-025 delivery
   * gate is evaluated first (trusted delivery approval current for
   * the full revision, naming the final artifact at its actual
   * hash, plus the passing final-QC record for those bytes); its
   * pass is recorded as the production delivery approval. Readiness
   * is then evaluated from measured artifacts. Anything missing
   * blocks delivery BY NAME with a StatusError
   * (MG_DELIVERY_INCOMPLETE) and a delivery_blocked event; the job
   * is never marked DELIVERED on partial evidence. Fixture-context
   * jobs are diagnostic and can never be delivered as production.
   */
  async deliver(init: {
    runtime: GateRuntimeIdentity | null;
    finalArtifact: { path: string; sha256: string };
    qc: FinalQcRecord | null;
  }): Promise<DeliveryReceipt> {
    const missing: string[] = [];
    if (this.doc.executionContext === "production") {
      const gate = evaluateDeliveryGate(this.jobDir, init.runtime, init.finalArtifact, init.qc);
      if (gate.verdict === "pass") {
        await this.recordGateApproval(gate);
      } else {
        missing.push(`delivery_gate:${gate.firstErrorCategory ?? "MG_APPROVAL_REQUIRED"}`);
      }
    }
    const readiness = evaluateDeliveryReadiness(this.jobDir, this.doc, this.requiredKinds);
    missing.push(...readiness.missing);
    const uniqueMissing = [...new Set(missing)];
    if (uniqueMissing.length > 0) {
      await this.commit("delivery_blocked", { missing: uniqueMissing });
      throw new StatusError({
        category: "MG_DELIVERY_INCOMPLETE",
        exitClass: 6,
        missing: uniqueMissing,
        message:
          `Delivery blocked for job ${this.doc.identity.jobId}: missing ${uniqueMissing.join(", ")}. ` +
          "A task reaches DELIVERED only with every mandatory artifact measured on disk, " +
          "a passing final QC over those bytes, and a verified production delivery approval.",
      });
    }
    const deliveredAt = nowIso();
    const receipt = buildDeliveryReceipt(this.jobDir, this.doc, deliveredAt);
    const receiptPath = join(this.jobDir, ...STATUS_DIR_PARTS, DELIVERY_RECEIPT_NAME);
    writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`, "utf8");
    this.doc.productionStatus = "DELIVERED";
    this.doc.phase = "DELIVERED";
    this.doc.deliveredAt = deliveredAt;
    await this.commit("delivered", {
      receipt: DELIVERY_RECEIPT_NAME,
      artifacts: receipt.artifacts.map((a) => ({ kind: a.kind, path: a.path, sha256: a.sha256 })),
    });
    return receipt;
  }
}

function freshDoc(
  identity: TaskIdentity,
  job: ValidatedMotionJob,
  opts?: TrackerOptions
): MotionStatusDoc {
  return {
    schemaVersion: "1.0",
    item: "MG-046",
    identity,
    mode: job.manifest.mode,
    executionContext: job.manifest.execution_context,
    diagnostic: job.manifest.execution_context === "fixture",
    phase: "CREATED",
    productionStatus: null,
    releaseStatus: null,
    engine: null,
    exportProfile: job.manifest.delivery.video_profile,
    exportRoute: null,
    artifacts: [],
    approvals: [],
    qc: null,
    recovery: null,
    missingMandatory: [...(job.manifest.delivery.required ?? [])],
    board: { transport: opts?.transportName ?? "skill47-motion-status-bridge", lastSync: null },
    deliveredAt: null,
    updatedAt: nowIso(),
  };
}
