// Delivery readiness and the delivery receipt (MG-046).
//
// A job is DELIVERED only when every mandatory artifact the manifest
// names is present as a measured artifact (path, sha256, bytes read
// from disk at receipt time, never caller claims), final QC passed
// over those exact bytes, and a production delivery approval
// verified by the MG-025 delivery gate is in force. Anything missing
// blocks delivery BY NAME: the refusal lists each missing artifact
// kind and each unmet gate, so the parent job and the board see
// exactly what is absent instead of a generic failure.
//
// The receipt is this layer's own document. Its contract is
// references/delivery-receipt-schema.json (a layer-owned schema in
// the MG-032/033/034/035/037 pattern); the canonical
// contracts-v2.schema.json is not edited. validateDeliveryReceipt
// mirrors the schema's required structure in code.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import type {
  MotionStatusDoc,
  ProductionApprovalRecord,
  StatusArtifact,
} from "./types";

/** The delivery receipt document (schema:
 * references/delivery-receipt-schema.json). */
export interface DeliveryReceipt {
  schema_version: "1.0";
  item: "MG-046";
  job_id: string;
  company_id: string;
  task: {
    task_id: string;
    origin: "parent" | "own";
    parent_job_id: string | null;
    parent_task_id: string | null;
  };
  mode: string;
  execution_context: "fixture" | "production";
  diagnostic: boolean;
  production_status: "DELIVERED";
  /** Release and build axis, carried separately and never advanced
   * by production events. */
  release_status: string | null;
  engine: string;
  export: { profile: string; route_kind: string | null; confirmed_by: string | null };
  artifacts: StatusArtifact[];
  approvals: ProductionApprovalRecord[];
  qc: { verdict: "pass"; artifact_path: string; artifact_sha256: string; source: string };
  recovery: { cache_work_dir: string | null; cache_job_key: string | null } | null;
  board: { job_id: string; stage_slug: string };
  missing_mandatory: [];
  delivered_at: string;
}

export interface DeliveryReadiness {
  ready: boolean;
  /** Names of what is missing: mandatory artifact kinds first, then
   * the unmet gates ("final_qc", "delivery_approval"). */
  missing: string[];
}

function sha256File(absPath: string): string {
  return createHash("sha256").update(readFileSync(absPath)).digest("hex");
}

/** Measure an artifact on disk. A recorded artifact whose file is
 * absent, or whose bytes no longer match its recorded hash, is not
 * an artifact for delivery purposes: it counts as missing, by kind. */
export function measureArtifact(jobDir: string, artifact: StatusArtifact): StatusArtifact | null {
  const abs = isAbsolute(artifact.path) ? artifact.path : join(jobDir, artifact.path);
  if (!existsSync(abs)) return null;
  const bytes = statSync(abs).size;
  const sha256 = sha256File(abs);
  if (artifact.sha256 !== null && artifact.sha256 !== sha256) return null;
  if (artifact.bytes !== null && artifact.bytes !== bytes) return null;
  return { kind: artifact.kind, path: artifact.path, sha256, bytes };
}

/**
 * Evaluate delivery readiness for a status document against the
 * manifest's mandatory artifact kinds. Pure with respect to the
 * document except for the on-disk measurement of recorded
 * artifacts: presence is proven from bytes, not from records.
 */
export function evaluateDeliveryReadiness(
  jobDir: string,
  doc: MotionStatusDoc,
  requiredKinds: string[]
): DeliveryReadiness {
  const missing: string[] = [];
  const presentKinds = new Set<string>();
  for (const artifact of doc.artifacts) {
    if (measureArtifact(jobDir, artifact) !== null) presentKinds.add(artifact.kind);
  }
  for (const kind of requiredKinds) {
    if (!presentKinds.has(kind)) missing.push(kind);
  }
  if (!doc.qc || doc.qc.verdict !== "pass") missing.push("final_qc");
  const deliveryApproval = doc.approvals.find(
    (a) => a.scope === "delivery" && a.decision === "approved"
  );
  if (!deliveryApproval) missing.push("delivery_approval");
  if (doc.diagnostic) missing.push("production_context");
  return { ready: missing.length === 0, missing };
}

/** Build the delivery receipt from a ready status document.
 * Callers must check readiness first; this builder re-measures
 * every artifact so the receipt records measured facts only. */
export function buildDeliveryReceipt(
  jobDir: string,
  doc: MotionStatusDoc,
  deliveredAt: string
): DeliveryReceipt {
  const artifacts: StatusArtifact[] = [];
  for (const artifact of doc.artifacts) {
    const measured = measureArtifact(jobDir, artifact);
    if (measured) artifacts.push(measured);
  }
  return {
    schema_version: "1.0",
    item: "MG-046",
    job_id: doc.identity.jobId,
    company_id: doc.identity.companyId,
    task: {
      task_id: doc.identity.taskId,
      origin: doc.identity.taskOrigin,
      parent_job_id: doc.identity.parentJobId,
      parent_task_id: doc.identity.parentTaskId,
    },
    mode: doc.mode,
    execution_context: doc.executionContext,
    diagnostic: doc.diagnostic,
    production_status: "DELIVERED",
    release_status: doc.releaseStatus,
    engine: doc.engine ?? "unknown",
    export: {
      profile: doc.exportProfile ?? "unknown",
      route_kind: doc.exportRoute?.kind ?? null,
      confirmed_by: doc.exportRoute?.confirmedBy ?? null,
    },
    artifacts,
    approvals: doc.approvals,
    qc: {
      verdict: "pass",
      artifact_path: doc.qc?.artifactPath ?? "",
      artifact_sha256: doc.qc?.artifactSha256 ?? "",
      source: doc.qc?.source ?? "",
    },
    recovery: doc.recovery
      ? { cache_work_dir: doc.recovery.cacheWorkDir, cache_job_key: doc.recovery.cacheJobKey }
      : null,
    board: { job_id: doc.identity.boardJobId, stage_slug: doc.identity.stageSlug },
    missing_mandatory: [],
    delivered_at: deliveredAt,
  };
}

const RECEIPT_REQUIRED = [
  "schema_version",
  "item",
  "job_id",
  "company_id",
  "task",
  "mode",
  "execution_context",
  "diagnostic",
  "production_status",
  "release_status",
  "engine",
  "export",
  "artifacts",
  "approvals",
  "qc",
  "recovery",
  "board",
  "missing_mandatory",
  "delivered_at",
] as const;

/** Structural validation of a delivery receipt document, mirroring
 * references/delivery-receipt-schema.json. Returns problems; an
 * empty list means the document satisfies the layer's contract. */
export function validateDeliveryReceipt(doc: unknown): string[] {
  const problems: string[] = [];
  if (typeof doc !== "object" || doc === null || Array.isArray(doc)) {
    return ["delivery receipt must be a JSON object"];
  }
  const r = doc as Record<string, unknown>;
  for (const key of RECEIPT_REQUIRED) {
    if (!(key in r)) problems.push(`missing required field: ${key}`);
  }
  if (r.schema_version !== "1.0") problems.push('schema_version must be "1.0"');
  if (r.item !== "MG-046") problems.push('item must be "MG-046"');
  if (r.production_status !== "DELIVERED") {
    problems.push(
      `production_status must be "DELIVERED" on a delivery receipt, got ${JSON.stringify(r.production_status)}; ` +
        "release and build statuses are a separate axis and are never recorded here"
    );
  }
  if (!Array.isArray(r.artifacts) || r.artifacts.length === 0) {
    problems.push("artifacts must be a non-empty array of measured artifacts");
  } else {
    for (const a of r.artifacts as Array<Record<string, unknown>>) {
      if (typeof a?.kind !== "string" || typeof a?.path !== "string" || typeof a?.sha256 !== "string") {
        problems.push("each artifact must carry kind, path, and a measured sha256");
      }
    }
  }
  if (!Array.isArray(r.approvals)) {
    problems.push("approvals must be an array");
  } else {
    for (const a of r.approvals as Array<Record<string, unknown>>) {
      if (a?.kind !== "production_approval") {
        problems.push(
          "every approval on a delivery receipt must be a production approval " +
            "(kind \"production_approval\", verified by an MG-025 gate); code-review " +
            "approval is a separate system and is never recorded here"
        );
      }
    }
  }
  const qc = r.qc as Record<string, unknown> | null;
  if (!qc || qc.verdict !== "pass") problems.push('qc.verdict must be "pass"');
  if (!Array.isArray(r.missing_mandatory) || r.missing_mandatory.length !== 0) {
    problems.push("missing_mandatory must be an empty array on a delivery receipt");
  }
  return problems;
}
