// The trusted gate evaluator (MG-025, Directive Sections 16.7, 16.8,
// 16.9). This module is the only construction path for production
// approval decisions in the runtime:
//
// - evaluateDesignGate: a design approval counts when it binds this
//   job and company, names the current design revision, and was issued
//   through the trusted issuer path (issuers.ts).
// - evaluateRenderGate: contracts validation and the catalog consult
//   are clean, the design gate passes, and a preview approval binds
//   the current full revision. A pass admits the job to
//   PREVIEW_APPROVED (Section 16.8) and buildApprovedJob constructs
//   the ApprovedMotionJob from the gate-verified permit. It is not a
//   type cast over a caller-supplied record.
// - evaluateDeliveryGate: the promotion check. A rendered artifact is
//   promotable as client-ready only in a production context, with a
//   delivery approval binding the current full revision and naming
//   the final artifact at its actual on-disk hash, plus a passing
//   final-QC record for those exact bytes. Fixture (diagnostic)
//   renders can never be promoted.
//
// Findings use the stable Section 16.9 categories and exit classes.
// Security findings (foreign job, hash mismatch, inauthentic event)
// stop ahead of every other class, per Section 16.9.

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve, sep } from "node:path";
import type { Approval, Manifest } from "../validation/generated-types";
import { validateAgainstDef } from "../validation/validate";
import { validateJob } from "../validation/semantics";
import { ComponentRegistry } from "../catalog/registry";
import type { ApprovedMotionJob, ValidatedMotionJob } from "../adapters/types";
import { canonicalJson } from "./canonical";
import {
  computeRevisionLock,
  type GateRuntimeIdentity,
  type RevisionLock,
} from "./revision";
import {
  FIXTURE_TEST_ISSUER,
  loadIssuerTrust,
  verifyApprovalEventSignature,
  type ApprovalEvent,
  type IssuerTrust,
} from "./issuers";
import { loadNarrationRecord } from "./narration";
import { GATE_PHASES, type Phase } from "./phases";

export type GateName = "design" | "render" | "delivery";

export type GateCategory =
  | "MG_SCHEMA_INVALID"
  | "MG_UNKNOWN_COMPONENT"
  | "MG_MODE_MISMATCH"
  | "MG_TIMELINE_INVALID"
  | "MG_INPUT_MISSING"
  | "MG_CAPABILITY_UNSUPPORTED"
  | "MG_RUNTIME_UNAVAILABLE"
  | "MG_APPROVAL_REQUIRED"
  | "MG_APPROVAL_STALE"
  | "MG_APPROVAL_AUTHORITY_UNAVAILABLE"
  | "MG_QC_FAILED"
  | "MG_HASH_MISMATCH"
  | "MG_FOREIGN_JOB"
  | "MG_SECURITY_VIOLATION";

export interface GateFinding {
  category: GateCategory;
  path: string;
  message: string;
}

/** Blocking order (Section 16.9): security first, then validation,
 * dependency, authority, execution, QC, delivery. */
const CATEGORY_ORDER: GateCategory[] = [
  "MG_FOREIGN_JOB",
  "MG_HASH_MISMATCH",
  "MG_SECURITY_VIOLATION",
  "MG_SCHEMA_INVALID",
  "MG_UNKNOWN_COMPONENT",
  "MG_MODE_MISMATCH",
  "MG_TIMELINE_INVALID",
  "MG_INPUT_MISSING",
  "MG_CAPABILITY_UNSUPPORTED",
  "MG_RUNTIME_UNAVAILABLE",
  "MG_APPROVAL_REQUIRED",
  "MG_APPROVAL_STALE",
  "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
  "MG_QC_FAILED",
];

export function exitClassForGateCategory(category: GateCategory): number {
  switch (category) {
    case "MG_FOREIGN_JOB":
    case "MG_HASH_MISMATCH":
    case "MG_SECURITY_VIOLATION":
      return 9;
    case "MG_SCHEMA_INVALID":
    case "MG_UNKNOWN_COMPONENT":
    case "MG_MODE_MISMATCH":
    case "MG_TIMELINE_INVALID":
      return 2;
    case "MG_INPUT_MISSING":
    case "MG_CAPABILITY_UNSUPPORTED":
    case "MG_RUNTIME_UNAVAILABLE":
      return 3;
    case "MG_APPROVAL_REQUIRED":
    case "MG_APPROVAL_STALE":
    case "MG_APPROVAL_AUTHORITY_UNAVAILABLE":
      return 4;
    case "MG_QC_FAILED":
      return 6;
  }
}

export function firstGateCategory(findings: GateFinding[]): GateCategory | null {
  for (const category of CATEGORY_ORDER) {
    if (findings.some((f) => f.category === category)) return category;
  }
  return null;
}

export interface GateResult {
  gate: GateName;
  verdict: "pass" | "blocked";
  jobId: string | null;
  companyId: string | null;
  /** True for fixture-context jobs: the result is diagnostic evidence
   * with no production delivery privilege. */
  diagnostic: boolean;
  /** The lifecycle phase a pass admits the job to (Section 16.8). */
  phase: Phase | null;
  designRevision: string | null;
  revision: string | null;
  /** The approval that satisfied this gate's own scope, on a pass. */
  approvalId: string | null;
  authorityBasis: string | null;
  findings: GateFinding[];
  firstErrorCategory: GateCategory | null;
  exitCode: number;
}

export class GateError extends Error {
  readonly category: GateCategory;
  readonly exitClass: number;
  readonly result: GateResult;

  constructor(result: GateResult) {
    const first = result.findings[0];
    super(
      `Gate ${result.gate} blocked for job ${result.jobId ?? "?"}: ` +
        `${result.firstErrorCategory ?? "MG_APPROVAL_REQUIRED"}: ${first?.message ?? "no detail"}`
    );
    this.name = "GateError";
    this.category = result.firstErrorCategory ?? "MG_APPROVAL_REQUIRED";
    this.exitClass = result.exitCode;
    this.result = result;
  }
}

/** Final-QC evidence for the delivery gate: a record, produced by QC
 * over the final bytes, naming the artifact it judged. */
export interface FinalQcRecord {
  artifact_path: string;
  artifact_sha256: string;
  verdict: "pass" | "fail";
}

export interface GateOptions {
  trust?: IssuerTrust;
}

type Doc = Record<string, unknown>;

function isDoc(value: unknown): value is Doc {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

interface GateContext {
  jobDir: string;
  manifest: Manifest | null;
  jobId: string | null;
  companyId: string | null;
  executionContext: string | null;
  approvalPolicy: string | null;
  approvals: Approval[];
  trust: IssuerTrust;
  lock: RevisionLock;
  findings: GateFinding[];
}

function loadContext(
  jobDir: string,
  runtime: GateRuntimeIdentity | null,
  opts?: GateOptions
): GateContext {
  const findings: GateFinding[] = [];
  const abs = resolve(jobDir);
  let manifest: Manifest | null = null;
  const manifestPath = join(abs, "manifest.json");
  if (!existsSync(manifestPath)) {
    findings.push({
      category: "MG_INPUT_MISSING",
      path: "manifest.json",
      message: "Job manifest is missing; no gate can be evaluated.",
    });
  } else {
    try {
      const parsed: unknown = JSON.parse(readFileSync(manifestPath, "utf8"));
      if (isDoc(parsed)) manifest = parsed as unknown as Manifest;
      else {
        findings.push({
          category: "MG_SCHEMA_INVALID",
          path: "manifest.json",
          message: "manifest.json is not a JSON object.",
        });
      }
    } catch (err) {
      findings.push({
        category: "MG_SCHEMA_INVALID",
        path: "manifest.json",
        message: `manifest.json is not parseable JSON: ${(err as Error).message}`,
      });
    }
  }

  const approvals: Approval[] = [];
  const approvalsPath = join(abs, "approvals.json");
  if (existsSync(approvalsPath)) {
    try {
      const parsed: unknown = JSON.parse(readFileSync(approvalsPath, "utf8"));
      const list = Array.isArray(parsed) ? parsed : isDoc(parsed) ? [parsed] : null;
      if (list === null) {
        findings.push({
          category: "MG_SCHEMA_INVALID",
          path: "approvals.json",
          message: "approvals.json is neither an approval record nor a list of them.",
        });
      } else {
        for (const entry of list) {
          if (!isDoc(entry)) {
            findings.push({
              category: "MG_SCHEMA_INVALID",
              path: "approvals.json",
              message: "approvals.json contains a non-object entry.",
            });
            continue;
          }
          for (const error of validateAgainstDef("approval", entry)) {
            // Errors raised inside the def's allOf conditional (the
            // approved-record requirements: named actor, source event,
            // verified authority, at least one artifact ref) are
            // classified by this gate's explicit authority checks
            // below, not as bare schema failures. This mirrors the
            // Python validators' root-allOf filter in
            // motion_contracts.validate_document.
            if (error.schemaPath.includes("/allOf/")) continue;
            findings.push({
              category: "MG_SCHEMA_INVALID",
              path: `approvals.json${error.instancePath}`,
              message: `Approval ${String(entry.approval_id ?? "?")} fails the approval schema at ${error.instancePath || "/"}: ${error.message ?? "schema violation"}`,
            });
          }
          approvals.push(entry as unknown as Approval);
        }
      }
    } catch (err) {
      findings.push({
        category: "MG_SCHEMA_INVALID",
        path: "approvals.json",
        message: `approvals.json is not parseable JSON: ${(err as Error).message}`,
      });
    }
  }

  const lock = computeRevisionLock(abs, runtime);
  for (const problem of lock.problems) {
    findings.push({ category: problem.category, path: problem.path, message: problem.message });
  }

  return {
    jobDir: abs,
    manifest,
    jobId: manifest?.job_id ?? null,
    companyId: manifest?.company_id ?? null,
    executionContext: manifest?.execution_context ?? null,
    approvalPolicy: manifest?.approval_policy ?? null,
    approvals,
    trust: opts?.trust ?? loadIssuerTrust(),
    lock,
    findings,
  };
}

function finish(ctx: GateContext, gate: GateName, extra: Partial<GateResult>): GateResult {
  // Order findings by blocking class so the report reads in the
  // Section 16.9 order regardless of discovery order.
  const ordered = [...ctx.findings].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)
  );
  const first = firstGateCategory(ordered);
  const blocked = ordered.length > 0;
  return {
    gate,
    verdict: blocked ? "blocked" : "pass",
    jobId: ctx.jobId,
    companyId: ctx.companyId,
    diagnostic: ctx.executionContext === "fixture",
    phase: blocked ? null : GATE_PHASES[gate],
    designRevision: ctx.lock.designRevision,
    revision: ctx.lock.fullRevision,
    approvalId: extra.approvalId ?? null,
    authorityBasis: extra.authorityBasis ?? null,
    findings: ordered,
    firstErrorCategory: first,
    exitCode: blocked ? exitClassForGateCategory(first ?? "MG_APPROVAL_REQUIRED") : 0,
  };
}

/**
 * Verify one approval record's authority and event binding. Appends
 * findings to the context; returns the authority basis on success.
 */
function verifyAuthority(ctx: GateContext, approval: Approval): string | null {
  const findings = ctx.findings;
  const actor = approval.actor_id;
  if (approval.authority_status !== "verified") {
    findings.push({
      category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
      path: "approvals.json",
      message: `Approval ${approval.approval_id} claims authority_status "${approval.authority_status}"; only a verified authority can satisfy a gate.`,
    });
    return null;
  }
  if (typeof actor !== "string" || actor.length === 0) {
    findings.push({
      category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
      path: "approvals.json",
      message: `Approval ${approval.approval_id} names no actor; its authority cannot be verified.`,
    });
    return null;
  }

  let basis: string;
  if (ctx.executionContext === "fixture") {
    if (ctx.approvalPolicy !== "fixture_only" || actor !== FIXTURE_TEST_ISSUER) {
      findings.push({
        category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
        path: "approvals.json",
        message:
          `Fixture jobs run under test-only authority: the single accepted issuer is ` +
          `${FIXTURE_TEST_ISSUER} under the fixture_only policy; got actor ${actor} ` +
          `under policy ${String(ctx.approvalPolicy)}.`,
      });
      return null;
    }
    basis = "fixture_test_issuer";
  } else if (ctx.executionContext === "production") {
    if (actor === FIXTURE_TEST_ISSUER) {
      findings.push({
        category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
        path: "approvals.json",
        message: "Production jobs reject the fixture test issuer; a real authorized approval event is required.",
      });
      return null;
    }
    const entry = ctx.trust.registry.find((e) => e.actorId === actor);
    if (
      !entry ||
      (entry.role !== "owner" && entry.role !== "authorized_reviewer") ||
      !entry.policies.includes("owner_or_existing_authorized_reviewer")
    ) {
      findings.push({
        category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
        path: "approvals.json",
        message:
          `Actor ${actor} is not a recognized production issuer in the configured registry ` +
          `(${ctx.trust.registrySource}); the job's policy is owner_or_existing_authorized_reviewer. ` +
          "No trusted approval source is configured for this actor, so the approval cannot be verified.",
      });
      return null;
    }
    basis = `registry:${entry.role}`;
  } else {
    findings.push({
      category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
      path: "manifest.json",
      message: `Execution context ${String(ctx.executionContext)} has no authority rule in this gate.`,
    });
    return null;
  }

  const key = ctx.trust.keyring[actor];
  if (!key) {
    findings.push({
      category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
      path: "approvals.json",
      message: `No verification key is configured for issuer ${actor} (${ctx.trust.keyringSource}); the approval event cannot be authenticated.`,
    });
    return null;
  }

  // Event binding: the approval must name its source event, bind the
  // event artifact's exact hash in artifact_refs, and the event must
  // repeat the approval's binding fields and verify under the key.
  const ref = approval.source_event_ref;
  if (typeof ref !== "string" || ref.length === 0) {
    findings.push({
      category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
      path: "approvals.json",
      message: `Approval ${approval.approval_id} names no source event; there is no trusted event to verify it against.`,
    });
    return null;
  }
  const eventAbs = resolve(join(ctx.jobDir, ref));
  if (eventAbs !== ctx.jobDir && !eventAbs.startsWith(ctx.jobDir + sep)) {
    findings.push({
      category: "MG_SECURITY_VIOLATION",
      path: ref,
      message: `Approval ${approval.approval_id} names a source event outside the job directory: ${ref}.`,
    });
    return null;
  }
  if (!existsSync(eventAbs)) {
    findings.push({
      category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
      path: ref,
      message: `Approval ${approval.approval_id} names source event ${ref}, which is absent from the job package; its authority cannot be verified.`,
    });
    return null;
  }
  const eventHash = sha256File(eventAbs);
  const bound = approval.artifact_refs.find((r) => r.path === ref);
  if (!bound) {
    findings.push({
      category: "MG_SECURITY_VIOLATION",
      path: "approvals.json",
      message: `Approval ${approval.approval_id} does not bind its source event ${ref} in artifact_refs; the event is not part of what was approved.`,
    });
    return null;
  }
  if (bound.sha256 !== eventHash) {
    findings.push({
      category: "MG_HASH_MISMATCH",
      path: ref,
      message: `Approval ${approval.approval_id} binds event ${ref} at sha256 ${bound.sha256}, but the event on disk hashes to ${eventHash}.`,
    });
    return null;
  }
  let event: ApprovalEvent;
  try {
    event = JSON.parse(readFileSync(eventAbs, "utf8")) as ApprovalEvent;
  } catch (err) {
    findings.push({
      category: "MG_SCHEMA_INVALID",
      path: ref,
      message: `Approval event ${ref} is not parseable JSON: ${(err as Error).message}`,
    });
    return null;
  }
  const mismatches: string[] = [];
  if (event.approval_id !== approval.approval_id) mismatches.push("approval_id");
  if (event.job_id !== approval.job_id) mismatches.push("job_id");
  if (event.company_id !== approval.company_id) mismatches.push("company_id");
  if (event.scope !== approval.scope) mismatches.push("scope");
  if (event.decision !== approval.decision) mismatches.push("decision");
  if (event.subject_revision !== approval.subject_revision) mismatches.push("subject_revision");
  if (event.actor_id !== approval.actor_id) mismatches.push("actor_id");
  if (canonicalJson(event.artifact_refs ?? []) !== canonicalJson(approval.artifact_refs.filter((r) => r.path !== ref))) {
    // The event carries the artifacts the approver approved; the
    // approval record carries those same refs plus the event binding
    // entry itself (an event cannot bind its own hash).
    mismatches.push("artifact_refs");
  }
  if (mismatches.length > 0) {
    findings.push({
      category: "MG_SECURITY_VIOLATION",
      path: ref,
      message: `Approval event ${ref} disagrees with approval ${approval.approval_id} on: ${mismatches.join(", ")}; the event does not authenticate this record.`,
    });
    return null;
  }
  if (!verifyApprovalEventSignature(event, key)) {
    findings.push({
      category: "MG_SECURITY_VIOLATION",
      path: ref,
      message: `Approval event ${ref} does not verify under the key registered for issuer ${actor}; the event is not authentic.`,
    });
    return null;
  }
  return `${basis}+signed_event`;
}

/**
 * Select the approval of one scope that satisfies a gate: bound to
 * this job, approved, current for the expected revision, and issued
 * through the trusted path. Appends findings; returns the record and
 * its authority basis on success.
 */
function selectApproval(
  ctx: GateContext,
  scope: Approval["scope"],
  expectedRevision: string | null,
  revisionLabel: string
): { approval: Approval; authorityBasis: string } | null {
  const findings = ctx.findings;
  for (const approval of ctx.approvals) {
    if (approval.job_id !== ctx.jobId || approval.company_id !== ctx.companyId) {
      findings.push({
        category: "MG_FOREIGN_JOB",
        path: "approvals.json",
        message:
          `Approval ${approval.approval_id} is bound to job ${approval.job_id} / company ` +
          `${approval.company_id}, not this job ${ctx.jobId} / ${ctx.companyId}; a foreign ` +
          "approval is never evidence here.",
      });
      return null;
    }
  }
  const candidates = ctx.approvals.filter((a) => a.scope === scope);
  if (candidates.length === 0) {
    findings.push({
      category: "MG_APPROVAL_REQUIRED",
      path: "approvals.json",
      message: `No ${scope}-scope approval is recorded for this job.`,
    });
    return null;
  }
  const approved = candidates.filter((a) => a.decision === "approved");
  if (approved.length === 0) {
    const named = candidates[0];
    findings.push({
      category: "MG_APPROVAL_REQUIRED",
      path: "approvals.json",
      message: `The ${scope} approval ${named.approval_id} carries decision "${named.decision}"; no ${scope} approval is in force.`,
    });
    return null;
  }
  if (expectedRevision === null) {
    findings.push({
      category: "MG_RUNTIME_UNAVAILABLE",
      path: "revision",
      message: `The ${revisionLabel} cannot be computed (a revision input is unavailable), so no ${scope} approval can be checked against it.`,
    });
    return null;
  }
  const current = approved.find((a) => a.subject_revision === expectedRevision);
  if (!current) {
    findings.push({
      category: "MG_APPROVAL_STALE",
      path: "approvals.json",
      message:
        `No ${scope} approval covers the current ${revisionLabel} ${expectedRevision}; recorded ` +
        `${scope} approvals bind: ${approved.map((a) => a.subject_revision).join(", ")}. ` +
        "A material change after approval stales the approval by construction.",
    });
    return null;
  }
  const authorityBasis = verifyAuthority(ctx, current);
  if (authorityBasis === null) return null;
  return { approval: current, authorityBasis };
}

/** Catalog consult for the render gate: every scene must classify
 * clean against the MG-018 registry. Mirrors the dispatcher wiring. */
function catalogFindings(ctx: GateContext): GateFinding[] {
  if (!ctx.manifest) return [];
  const out: GateFinding[] = [];
  const registry = ComponentRegistry.createDefault();
  for (const entry of ctx.manifest.scenes ?? []) {
    const specPath = join(ctx.jobDir, entry.spec);
    if (!existsSync(specPath)) continue; // contracts validation reports it
    let doc: unknown;
    try {
      doc = JSON.parse(readFileSync(specPath, "utf8"));
    } catch {
      continue; // contracts validation reports it
    }
    const result = registry.validateSceneProps(doc);
    for (const finding of result.findings) {
      out.push({
        category: finding.category,
        path: `${entry.spec}${finding.path}`,
        message: finding.message,
      });
    }
  }
  return out;
}

function narrationFindings(ctx: GateContext): GateFinding[] {
  if (!ctx.manifest) return [];
  const { problems } = loadNarrationRecord(ctx.jobDir, ctx.manifest);
  return problems.map((p) => ({
    category: "MG_SCHEMA_INVALID" as const,
    path: p.path,
    message: p.message,
  }));
}

/** The design gate: a trusted design approval for the current design
 * revision. Admits DESIGN_APPROVED. */
export function evaluateDesignGate(jobDir: string, opts?: GateOptions): GateResult {
  const ctx = loadContext(jobDir, null, opts);
  let approvalId: string | null = null;
  let authorityBasis: string | null = null;
  if (ctx.manifest && ctx.lock.designRevision !== null) {
    const selected = selectApproval(ctx, "design", ctx.lock.designRevision, "design revision");
    if (selected) {
      approvalId = selected.approval.approval_id;
      authorityBasis = selected.authorityBasis;
    }
  } else if (ctx.manifest) {
    ctx.findings.push({
      category: "MG_INPUT_MISSING",
      path: "revision",
      message: "The design revision cannot be computed; a design input is missing.",
    });
  }
  return finish(ctx, "design", { approvalId, authorityBasis });
}

/**
 * The render gate: contracts validation and the catalog consult are
 * clean, the narration record is sound, the design gate passes, and a
 * trusted preview approval binds the current full revision. Admits
 * PREVIEW_APPROVED. Runtime identity is required: a revision that
 * cannot name its runtime cannot be approved for rendering.
 */
export function evaluateRenderGate(
  jobDir: string,
  runtime: GateRuntimeIdentity | null,
  opts?: GateOptions
): GateResult {
  const ctx = loadContext(jobDir, runtime, opts);
  if (runtime === null) {
    ctx.findings.push({
      category: "MG_RUNTIME_UNAVAILABLE",
      path: "revision",
      message: "No runtime identity was supplied; the full revision cannot be pinned to a runtime, so no preview approval can satisfy the render gate.",
    });
  }
  if (ctx.manifest) {
    for (const finding of validateJob(ctx.jobDir)) {
      ctx.findings.push({
        category: finding.category,
        path: finding.path,
        message: finding.message,
      });
    }
    ctx.findings.push(...catalogFindings(ctx));
    ctx.findings.push(...narrationFindings(ctx));
  }
  let approvalId: string | null = null;
  let authorityBasis: string | null = null;
  if (ctx.manifest && ctx.lock.designRevision !== null) {
    const design = selectApproval(ctx, "design", ctx.lock.designRevision, "design revision");
    if (design) authorityBasis = design.authorityBasis;
  }
  if (ctx.manifest && runtime !== null) {
    const preview = selectApproval(ctx, "preview", ctx.lock.fullRevision, "full revision");
    if (preview) {
      approvalId = preview.approval.approval_id;
      authorityBasis = preview.authorityBasis;
    }
  }
  return finish(ctx, "render", { approvalId, authorityBasis });
}

/**
 * The delivery gate (the promotion check): production context only,
 * trusted preview and delivery approvals current for the full
 * revision, and a passing final-QC record for the exact final
 * artifact bytes the delivery approval names. Admits FINAL_QC_PASSED,
 * ready to package and deliver.
 */
export function evaluateDeliveryGate(
  jobDir: string,
  runtime: GateRuntimeIdentity | null,
  finalArtifact: { path: string; sha256: string },
  qc: FinalQcRecord | null,
  opts?: GateOptions
): GateResult {
  const ctx = loadContext(jobDir, runtime, opts);
  if (runtime === null) {
    ctx.findings.push({
      category: "MG_RUNTIME_UNAVAILABLE",
      path: "revision",
      message: "No runtime identity was supplied; the delivered revision cannot be pinned to a runtime.",
    });
  }
  if (ctx.manifest && ctx.executionContext === "fixture") {
    ctx.findings.push({
      category: "MG_APPROVAL_AUTHORITY_UNAVAILABLE",
      path: "manifest.json",
      message:
        "Fixture jobs run in a diagnostic test context with no production delivery privilege; " +
        "a fixture render can never be promoted as client-ready.",
    });
  }
  let approvalId: string | null = null;
  let authorityBasis: string | null = null;
  let deliveryApproval: Approval | null = null;
  if (ctx.manifest && ctx.executionContext === "production" && runtime !== null) {
    const preview = selectApproval(ctx, "preview", ctx.lock.fullRevision, "full revision");
    if (preview) authorityBasis = preview.authorityBasis;
    const delivery = selectApproval(ctx, "delivery", ctx.lock.fullRevision, "full revision");
    if (delivery) {
      approvalId = delivery.approval.approval_id;
      authorityBasis = delivery.authorityBasis;
      deliveryApproval = delivery.approval;
    }
  }

  // Final artifact and QC binding.
  const artifactAbs = resolve(join(ctx.jobDir, finalArtifact.path));
  if (artifactAbs !== ctx.jobDir && !artifactAbs.startsWith(ctx.jobDir + sep)) {
    ctx.findings.push({
      category: "MG_SECURITY_VIOLATION",
      path: finalArtifact.path,
      message: `Final artifact path ${finalArtifact.path} escapes the job directory.`,
    });
  } else if (!existsSync(artifactAbs)) {
    ctx.findings.push({
      category: "MG_INPUT_MISSING",
      path: finalArtifact.path,
      message: `Final artifact ${finalArtifact.path} is absent; there is nothing to promote.`,
    });
  } else {
    const diskHash = sha256File(artifactAbs);
    if (diskHash !== finalArtifact.sha256) {
      ctx.findings.push({
        category: "MG_HASH_MISMATCH",
        path: finalArtifact.path,
        message: `Final artifact ${finalArtifact.path} hashes to ${diskHash} on disk, not the presented ${finalArtifact.sha256}.`,
      });
    } else if (deliveryApproval) {
      const bound = deliveryApproval.artifact_refs.find((r) => r.path === finalArtifact.path);
      if (!bound) {
        ctx.findings.push({
          category: "MG_APPROVAL_STALE",
          path: "approvals.json",
          message: `The delivery approval does not name the final artifact ${finalArtifact.path}; it does not cover these bytes.`,
        });
      } else if (bound.sha256 !== diskHash) {
        ctx.findings.push({
          category: "MG_APPROVAL_STALE",
          path: "approvals.json",
          message: `The delivery approval binds ${finalArtifact.path} at sha256 ${bound.sha256}, but the artifact on disk hashes to ${diskHash}; the render changed after approval.`,
        });
      }
    }
    if (qc === null) {
      ctx.findings.push({
        category: "MG_INPUT_MISSING",
        path: "qc",
        message: "No final-QC record was supplied; delivery requires final QC on the final bytes, not preview QC (Section 16.8).",
      });
    } else if (qc.artifact_path !== finalArtifact.path || qc.artifact_sha256 !== diskHash) {
      ctx.findings.push({
        category: "MG_QC_FAILED",
        path: "qc",
        message: `The final-QC record names ${qc.artifact_path} at ${qc.artifact_sha256}, not the presented artifact ${finalArtifact.path} at ${diskHash}; QC of other bytes is not delivery evidence.`,
      });
    } else if (qc.verdict !== "pass") {
      ctx.findings.push({
        category: "MG_QC_FAILED",
        path: "qc",
        message: `Final QC verdict for ${finalArtifact.path} is "${qc.verdict}"; a failed final QC cannot be promoted.`,
      });
    }
  }
  return finish(ctx, "delivery", { approvalId, authorityBasis });
}

/** Throwing form of the delivery gate: the promotion check consumers
 * (package, delivery, handoff) call before claiming client-ready. */
export function assertDeliveryPromotable(
  jobDir: string,
  runtime: GateRuntimeIdentity | null,
  finalArtifact: { path: string; sha256: string },
  qc: FinalQcRecord | null,
  opts?: GateOptions
): GateResult {
  const result = evaluateDeliveryGate(jobDir, runtime, finalArtifact, qc, opts);
  if (result.verdict !== "pass") throw new GateError(result);
  return result;
}

/**
 * The trusted construction of an ApprovedMotionJob (Section 16.7):
 * runs the render gate and returns the job carrying the gate-verified
 * preview permit loaded from the job's own approval records. Throws
 * GateError when the gate blocks.
 */
export function buildApprovedJob(
  jobDir: string,
  runtime: GateRuntimeIdentity | null,
  opts?: GateOptions
): { job: ApprovedMotionJob; gate: GateResult } {
  const gate = evaluateRenderGate(jobDir, runtime, opts);
  if (gate.verdict !== "pass") throw new GateError(gate);
  const manifest = JSON.parse(readFileSync(join(jobDir, "manifest.json"), "utf8")) as Manifest;
  const approvalsPath = join(jobDir, "approvals.json");
  const parsed: unknown = JSON.parse(readFileSync(approvalsPath, "utf8"));
  const list = (Array.isArray(parsed) ? parsed : [parsed]) as Approval[];
  const permit = list.find((a) => a.approval_id === gate.approvalId);
  if (!permit) throw new GateError(gate);
  const job: ValidatedMotionJob = { jobDir, jobId: manifest.job_id, manifest };
  return { job: { ...job, approval: permit }, gate };
}
