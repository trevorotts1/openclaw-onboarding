// Orchestration dispatcher for Skill 72 Motion Graphics V2 (MG-004).
//
// One entry point between callers and the renderer adapters. For every
// render operation the dispatcher:
//   1. validates the job directory through the MG-007 contracts layer
//      (invalid jobs are rejected before any adapter is invoked),
//   2. derives per-scene requirements from the job files and routes them
//      through the Section 3.2 routing rules against the capability matrix,
//   3. resolves the owning adapter (a missing adapter is a dependency-class
//      error, MG_ENGINE_MISSING, exit class 3),
//   4. invokes the adapter under a timeout and cancellation contract, and
//   5. returns the adapter's structured evidence together with the routing
//      decision that selected it.
//
// Job-level operations run on the routing decision's assembly owner, the
// single final assembly owner for the program. Per-scene assignments are
// returned with every outcome so mixed-engine programs hand normalized
// scene assets and timeline metadata to that owner explicitly.
//
// MG-046 adds two wirings at this seam:
// - Settlement B (from MG-040's closure): when a caller supplies or
//   requests a live export toolchain probe, a job whose delivery
//   profile requires alpha is routed by the export layer's probed
//   qualification (export/select.ts) instead of being refused at
//   route time against the shipped matrix's empty alpha claims. The
//   shipped matrix file is never edited; the probe's confirmation is
//   applied to an in-memory routing view only, and when no profile
//   qualifies the refusal is the export layer's fail-by-name
//   MG_CAPABILITY_UNSUPPORTED, raised before any authoring.
// - Settlement A (from MG-027's closure): renderFinalCached opens a
//   cache session per job, supplies per-scene renderers backed by
//   the routed adapters, and assembles the final output only from
//   session.artifactPathFor, so interrupt and resume work through
//   the production dispatch path. Status emissions to a
//   MotionStatusTracker are optional and fail-soft.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { isAbsolute, join, relative } from "node:path";
import type { Approval, Manifest, Scene } from "../validation/generated-types";
import { firstErrorCategory, validateJob } from "../validation/semantics";
import { ComponentRegistry } from "../catalog/registry";
import { CatalogError, firstCatalogCategory, type CatalogErrorCategory } from "../catalog/errors";
import { evaluateRenderGate, GateError, type GateResult } from "../orchestrator/gate";
import {
  containerExtensionForProfile,
  deriveSceneWorkUnits,
  stageSceneJobDir,
} from "../orchestrator/cache-units";
import { CachedRenderSession } from "../cache/session";
import { probeMediaFile } from "../cache/verify";
import type { SceneRenderer, SessionRunReport } from "../cache/types";
import { selectExportRoute, type ExportSelection } from "../export/select";
import { probeExportToolchain, type ExportToolchainProbe } from "../export/probe";
import { exportProfileById } from "../export/profiles";
import type { MotionStatusTracker } from "../status/tracker";
import { loadCapabilityMatrix } from "./capabilities";
import { route, routeOrThrow, RoutingDecision, RoutingRequest, SceneRequirement } from "./routing";
import {
  AdapterError,
  ArtifactEvidence,
  ApprovedMotionJob,
  CallContext,
  CapabilityMatrix,
  Engine,
  MotionEvidence,
  MotionRendererAdapter,
  PreviewOptions,
  RuntimeEvidence,
  ValidatedMotionJob,
  ValidationEvidence,
} from "./types";

/** Default per-operation timeout: five minutes. Render finals on real
 * engines pass an explicit larger timeout through DispatchCallOptions. */
export const DEFAULT_TIMEOUT_MS = 300_000;

export interface AdapterRegistry {
  get(engine: Engine): MotionRendererAdapter | undefined;
  engines(): Engine[];
}

export function createRegistry(adapters: MotionRendererAdapter[]): AdapterRegistry {
  const map = new Map<Engine, MotionRendererAdapter>();
  for (const adapter of adapters) map.set(adapter.engine, adapter);
  return {
    get: (engine) => map.get(engine),
    engines: () => [...map.keys()],
  };
}

export interface DispatchCallOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
  matrix?: CapabilityMatrix;
  /** MG-024 preview options, forwarded to renderPreview only: a
   * spatial scale and/or the rough-layout flag. Absent means the
   * canonical full-fps preview. */
  preview?: PreviewOptions;
  /** MG-046 Settlement B: a live export toolchain probe record to
   * route alpha-profile jobs by (see export/probe.ts). Supplying
   * one (or null, meaning the probe ran and qualified nothing the
   * caller kept) opts the call into export-selection routing for
   * alpha jobs; leaving it undefined keeps the matrix-only routing
   * behavior unchanged. */
  exportToolchain?: ExportToolchainProbe | null;
  /** MG-046 Settlement B: run the live toolchain probe at route
   * time when exportToolchain is not supplied. The probe is a few
   * tiny ffmpeg micro-roundtrips in a scratch directory. */
  probeExportToolchain?: boolean;
  /** Scratch directory for a route-time toolchain probe. */
  toolchainScratchDir?: string;
  /** MG-046 Settlement A: cache session work directory for
   * renderFinalCached. Default: <jobDir>/working/cache. The
   * directory is the resume context: it survives the process, and
   * the same job reopened against it resumes instead of restarting. */
  cacheWorkDir?: string;
  /** MG-046: status tracker to emit structured phase transitions,
   * render receipts, failures, and recovery points to. Emissions
   * are fail-soft and never change the operation's outcome. */
  tracker?: MotionStatusTracker;
}

export interface DispatchOutcome<T> {
  evidence: T;
  routing: RoutingDecision;
  /** MG-046: the export layer's route selection for the job's
   * delivery profile, when one was made (baseline contract for
   * opaque profiles; probe or matrix qualification for alpha). */
  exportSelection?: ExportSelection | null;
}

/** MG-046 Settlement A outcome: the assembled final evidence plus
 * the cache session's run report (per-scene reuse and render
 * actions, the recovery evidence for the job). */
export interface CachedRenderOutcome extends DispatchOutcome<ArtifactEvidence> {
  cache: SessionRunReport;
}

interface CatalogConsultFinding {
  spec: string;
  category: CatalogErrorCategory;
  message: string;
}

/**
 * MG-025 catalog consult (settlement from MG-018): classify every scene
 * spec against the MG-018 component registry. Runs alongside the
 * canonical contracts validation, never instead of it. Scene files that
 * are missing or unparseable are skipped here; the contracts layer
 * already reports those.
 */
function consultCatalog(jobDir: string, manifest: Manifest): CatalogConsultFinding[] {
  const registry = ComponentRegistry.createDefault();
  const out: CatalogConsultFinding[] = [];
  for (const entry of manifest.scenes ?? []) {
    const abs = join(jobDir, entry.spec);
    if (!existsSync(abs)) continue;
    let doc: unknown;
    try {
      doc = JSON.parse(readFileSync(abs, "utf8"));
    } catch {
      continue;
    }
    const result = registry.validateSceneProps(doc);
    for (const finding of result.findings) {
      out.push({ spec: entry.spec, category: finding.category, message: finding.message });
    }
  }
  return out;
}

function readManifestLenient(jobDir: string): Manifest | null {
  try {
    const parsed: unknown = JSON.parse(readFileSync(join(jobDir, "manifest.json"), "utf8"));
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Manifest;
    }
  } catch {
    // The contracts layer reports the failure.
  }
  return null;
}

/** The stable category of a dispatch failure, for status records. */
function errorCategoryOf(err: unknown): string {
  if (err instanceof AdapterError) return err.category;
  if (err instanceof GateError) return err.category;
  return "MG_RENDER_FAILED";
}

function sha256File(absPath: string): string {
  return createHash("sha256").update(readFileSync(absPath)).digest("hex");
}

/** Locate the artifact an adapter produced for one scene: the output
 * path carrying the delivery container extension, else the first
 * output. Relative paths resolve against the staged scene job
 * directory the adapter rendered. */
function pickProducedArtifact(
  evidence: ArtifactEvidence,
  stagedJobDir: string,
  ext: string
): string {
  const candidates = evidence.outputPaths.length > 0
    ? evidence.outputPaths
    : evidence.artifacts.map((a) => a.path);
  const chosen =
    candidates.find((p) => p.toLowerCase().endsWith(ext)) ?? candidates[0];
  if (!chosen) {
    throw new AdapterError({
      category: "MG_RENDER_FAILED",
      message: "The adapter reported success but produced no artifact path.",
    });
  }
  if (isAbsolute(chosen)) return chosen;
  const fromStaged = join(stagedJobDir, chosen);
  return existsSync(fromStaged) ? fromStaged : chosen;
}

/** Assemble the final output from verified scene artifacts, in
 * manifest order. One scene: the artifact is the output. Several:
 * an ffmpeg concat with stream copy, the same discipline the
 * MG-027 suite's assembly uses; the parts are same-profile scene
 * artifacts from one job, so their stream parameters agree. */
function assembleSceneArtifacts(parts: string[], outPath: string): void {
  if (parts.length === 1) {
    copyFileSync(parts[0], outPath);
    return;
  }
  const listPath = `${outPath}.concat.txt`;
  writeFileSync(
    listPath,
    parts.map((p) => `file '${p.replace(/'/g, "'\\''")}'`).join("\n") + "\n",
    "utf8"
  );
  const result = spawnSync(
    "ffmpeg",
    ["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", listPath, "-c", "copy", outPath],
    { encoding: "utf8" }
  );
  if (result.status !== 0 || !existsSync(outPath)) {
    throw new AdapterError({
      category: "MG_RENDER_FAILED",
      message: `Assembling ${parts.length} scene artifacts failed: ${(result.stderr ?? "").slice(-600)}`,
    });
  }
}

/**
 * Validate a job directory through the contracts layer and build the typed
 * job object adapters consume. Throws AdapterError with the contracts
 * layer's first error category (exit class 2) when findings exist.
 *
 * MG-025: the MG-018 catalog is consulted on the same pass, before any
 * adapter is resolved. When the contracts layer can only report a
 * scene's component as MG_UNKNOWN_COMPONENT but the catalog knows the
 * component as registered-but-unavailable, the refusal is the catalog's
 * MG_CAPABILITY_UNSUPPORTED (CatalogError, exit class 3). When the
 * contracts layer passes, any catalog refusal still blocks the job.
 */
export function loadValidatedJob(jobDir: string): ValidatedMotionJob {
  const findings = validateJob(jobDir);
  const lenientManifest = readManifestLenient(jobDir);
  const catalog = lenientManifest ? consultCatalog(jobDir, lenientManifest) : [];
  if (findings.length > 0) {
    const onlyUnknownComponents = findings.every((f) => f.category === "MG_UNKNOWN_COMPONENT");
    const unsupported = catalog.find((f) => f.category === "MG_CAPABILITY_UNSUPPORTED");
    if (onlyUnknownComponents && unsupported) {
      throw new CatalogError(
        "MG_CAPABILITY_UNSUPPORTED",
        `Job at ${jobDir} names a component the catalog has registered but ` +
          `cannot dispatch: ${unsupported.message}`,
        catalog.map((f) => ({ category: f.category, path: f.spec, message: f.message }))
      );
    }
    throw new AdapterError({
      category: firstErrorCategory(findings) ?? "MG_SCHEMA_INVALID",
      message:
        `Job at ${jobDir} failed contracts validation with ` +
        `${findings.length} finding(s); first finding: ${findings[0].message}`,
      findings,
    });
  }
  if (catalog.length > 0) {
    throw new CatalogError(
      firstCatalogCategory(
        catalog.map((f) => ({ category: f.category, path: f.spec, message: f.message }))
      ) ?? "MG_SCHEMA_INVALID",
      `Job at ${jobDir} failed the catalog consult: ${catalog[0].message}`,
      catalog.map((f) => ({ category: f.category, path: f.spec, message: f.message }))
    );
  }
  const manifest = JSON.parse(readFileSync(join(jobDir, "manifest.json"), "utf8")) as Manifest;
  return { jobDir, jobId: manifest.job_id, manifest };
}

const REPRESENTATION_KIND: Record<string, SceneRequirement["kind"]> = {
  chart: "data_chart",
  image: "editorial_image",
  diagram: "parameterized_infographic",
  mechanism: "spatial_reveal",
  typography: "generic",
};

/**
 * Derive per-scene routing requirements from a validated job's own files:
 * the scene spec's explicit engine wins at scene level, the storyboard
 * beat's representation classifies the scene kind, and an alpha delivery
 * profile adds the alpha and codec requirements every scene must confirm.
 */
export function deriveSceneRequirements(job: ValidatedMotionJob): SceneRequirement[] {
  const manifest = job.manifest;
  let beats: Array<Record<string, unknown>> = [];
  try {
    const storyboard = JSON.parse(
      readFileSync(join(job.jobDir, manifest.storyboard), "utf8")
    ) as Record<string, unknown>;
    if (Array.isArray(storyboard.beats)) beats = storyboard.beats as Array<Record<string, unknown>>;
  } catch {
    beats = [];
  }
  const profile = manifest.delivery.video_profile;
  const requiresAlpha = profile === "prores_4444_alpha" || profile === "vp9_alpha";
  const extraCodecs =
    profile === "prores_4444_alpha" ? ["prores"] : profile === "vp9_alpha" ? ["vp9"] : [];
  return manifest.scenes.map((entry) => {
    let explicitEngine: Engine | null = null;
    try {
      const spec = JSON.parse(readFileSync(join(job.jobDir, entry.spec), "utf8")) as Scene;
      explicitEngine = spec.engine ?? null;
    } catch {
      explicitEngine = null;
    }
    const beat = beats.find((b) => b.scene_id === entry.id);
    const representation = typeof beat?.representation === "string" ? beat.representation : "";
    return {
      sceneId: entry.id,
      kind: REPRESENTATION_KIND[representation] ?? "generic",
      explicitEngine,
      requiresAlpha,
      extraCodecs,
    };
  });
}

interface InFlight {
  controller: AbortController;
  engine: Engine;
}

export class MotionDispatcher {
  private readonly registry: AdapterRegistry;
  private readonly defaultTimeoutMs: number;
  private readonly matrixPath?: string;
  private readonly inflight = new Map<string, InFlight>();

  constructor(
    registry: AdapterRegistry,
    defaults?: { timeoutMs?: number; matrixPath?: string }
  ) {
    this.registry = registry;
    this.defaultTimeoutMs = defaults?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.matrixPath = defaults?.matrixPath;
  }

  private matrixFor(opts?: DispatchCallOptions): CapabilityMatrix {
    return opts?.matrix ?? loadCapabilityMatrix(this.matrixPath);
  }

  private adapterFor(engine: Engine): MotionRendererAdapter {
    const adapter = this.registry.get(engine);
    if (!adapter) {
      throw new AdapterError({
        category: "MG_ENGINE_MISSING",
        engine,
        message:
          `No adapter is registered for engine ${engine}. Registered: ` +
          `${this.registry.engines().join(", ") || "(none)"}. Provision the ` +
          "shared runtime and register the adapter before dispatching.",
      });
    }
    return adapter;
  }

  /** Route a job directory without invoking any adapter.
   *
   * MG-046 Settlement B: for a job whose delivery profile requires
   * alpha, when the caller supplies or requests a live export
   * toolchain probe, routing consults the export layer's selection
   * (export/select.ts) per candidate engine in routing-preference
   * order. The first engine whose route the probe (or the matrix)
   * qualifies takes the job: the qualification is applied to an
   * in-memory copy of the matrix for this call only, so routing's
   * own confirmation rules pass on the strength of the probe, and
   * the shipped matrix file is never edited. When no candidate
   * qualifies, the export layer's ExportError
   * (MG_CAPABILITY_UNSUPPORTED) is thrown before any authoring.
   * Without a probe opt-in, routing behavior is exactly the
   * matrix-only behavior it has always been. */
  routeJob(
    jobDir: string,
    opts?: DispatchCallOptions
  ): { job: ValidatedMotionJob; routing: RoutingDecision; exportSelection: ExportSelection | null } {
    const job = loadValidatedJob(jobDir);
    const matrix = this.matrixFor(opts);
    const scenes = deriveSceneRequirements(job);
    const request = {
      scenes,
      manifestDefaultEngine: job.manifest.rendering.default_engine,
      allowLegacyFallback: job.manifest.rendering.allow_legacy_fallback,
    };
    const needsAlpha = scenes.some((s) => s.requiresAlpha === true);
    if (!needsAlpha) {
      const routing = routeOrThrow(request, matrix);
      return { job, routing, exportSelection: this.baselineSelection(job, routing, matrix) };
    }
    const probeOptedIn = opts?.exportToolchain !== undefined || opts?.probeExportToolchain === true;
    if (!probeOptedIn) {
      const routing = routeOrThrow(request, matrix);
      return { job, routing, exportSelection: null };
    }
    const toolchain =
      opts?.exportToolchain !== undefined
        ? opts.exportToolchain
        : probeExportToolchain(
            opts?.toolchainScratchDir ??
              join(tmpdir(), `motion-toolchain-probe-${job.jobId}`)
          );
    const profileId = job.manifest.delivery.video_profile;
    let firstSelectionError: unknown = null;
    for (const engine of this.alphaPreferenceOrder(request, matrix)) {
      let selection: ExportSelection;
      try {
        selection = selectExportRoute({ profileId, engine, matrix, toolchain });
      } catch (err) {
        if (firstSelectionError === null) firstSelectionError = err;
        continue;
      }
      const routing = routeOrThrow(request, this.augmentedMatrix(matrix, engine, selection));
      return { job, routing, exportSelection: selection };
    }
    if (firstSelectionError !== null) throw firstSelectionError;
    throw new AdapterError({
      category: "MG_CAPABILITY_UNSUPPORTED",
      message: `No production engine can be evaluated for alpha profile ${profileId}.`,
    });
  }

  /** The export selection for a non-alpha job: the profile's
   * baseline contract route on the routed engine. Null when the
   * routed engine is the legacy renderer (the export layer carries
   * no legacy routes) or the selection cannot be made. */
  private baselineSelection(
    job: ValidatedMotionJob,
    routing: RoutingDecision,
    matrix: CapabilityMatrix
  ): ExportSelection | null {
    const engine = routing.primaryEngine;
    if (engine !== "hyperframes" && engine !== "remotion") return null;
    try {
      return selectExportRoute({
        profileId: job.manifest.delivery.video_profile,
        engine,
        matrix,
        toolchain: null,
      });
    } catch {
      return null;
    }
  }

  /** Candidate engines for an alpha job, in routing-preference
   * order: route the job with the alpha requirements set aside
   * (the profile's own codec requirement goes with them, since the
   * export selection owns it), take the assigned engines in scene
   * order, then append any remaining production engine. */
  private alphaPreferenceOrder(
    request: RoutingRequest,
    matrix: CapabilityMatrix
  ): Array<"hyperframes" | "remotion"> {
    const profileCodecs = new Set(["prores", "vp9"]);
    const stripped: SceneRequirement[] = request.scenes.map((s) => ({
      ...s,
      requiresAlpha: false,
      extraCodecs: (s.extraCodecs ?? []).filter((c) => !profileCodecs.has(c)),
    }));
    const order: Array<"hyperframes" | "remotion"> = [];
    const result = route({ ...request, scenes: stripped }, matrix);
    if (result.kind === "routed") {
      for (const assignment of result.assignments) {
        if (
          (assignment.engine === "hyperframes" || assignment.engine === "remotion") &&
          !order.includes(assignment.engine)
        ) {
          order.push(assignment.engine);
        }
      }
    }
    for (const engine of ["remotion", "hyperframes"] as const) {
      if (!order.includes(engine)) order.push(engine);
    }
    return order;
  }

  /** An in-memory copy of the matrix in which one engine's record
   * additionally confirms what the export selection qualified: the
   * alpha profile, its stream codec, and alpha video. The shipped
   * matrix is the record of engine probes; the export toolchain
   * probe is a separate measured authority, and this copy is where
   * the two meet for one routing call. The file on disk is never
   * written. */
  private augmentedMatrix(
    matrix: CapabilityMatrix,
    engine: "hyperframes" | "remotion",
    selection: ExportSelection
  ): CapabilityMatrix {
    const profile = exportProfileById(selection.profile.id);
    const copy: CapabilityMatrix = {
      ...matrix,
      engines: matrix.engines.map((record) => {
        if (record.engine !== engine) return record;
        return {
          ...record,
          codecs: [...new Set([...record.codecs, profile.streamCodec])],
          transparency: {
            alphaVideo: true,
            profiles: [...new Set([...record.transparency.profiles, profile.id])],
          },
          evidence: [
            ...record.evidence,
            `Alpha route for profile ${profile.id} confirmed by ${selection.confirmedBy} ` +
              `at dispatch time (MG-046 export-selection routing); the shipped matrix ` +
              "record itself is unchanged.",
          ],
        };
      }),
    };
    return copy;
  }

  /** Probe one engine's runtime through its adapter. */
  async probe(engine: Engine, opts?: DispatchCallOptions): Promise<RuntimeEvidence> {
    const adapter = this.adapterFor(engine);
    return this.runWithCall(adapter, `probe:${engine}`, opts, () => adapter.probeRuntime());
  }

  /** Validate a job for its routed engine. Contracts validation runs
   * first; the adapter then applies engine-specific checks. */
  async validate(
    jobDir: string,
    opts?: DispatchCallOptions
  ): Promise<DispatchOutcome<ValidationEvidence>> {
    const { job, routing, exportSelection } = this.routeJob(jobDir, opts);
    const adapter = this.adapterFor(routing.primaryEngine);
    const evidence = await this.runWithCall(adapter, job.jobId, opts, () =>
      adapter.validate(job)
    );
    return { evidence, routing, exportSelection };
  }

  async renderStill(
    jobDir: string,
    frame: number,
    opts?: DispatchCallOptions
  ): Promise<DispatchOutcome<ArtifactEvidence>> {
    const { job, routing, exportSelection } = this.routeJob(jobDir, opts);
    if (!Number.isInteger(frame) || frame < 0 || frame >= job.manifest.duration_frames) {
      throw new AdapterError({
        category: "MG_TIMELINE_INVALID",
        message: `Still frame ${frame} lies outside the job's frames 0..${job.manifest.duration_frames - 1}.`,
      });
    }
    const adapter = this.adapterFor(routing.primaryEngine);
    const evidence = await this.runWithCall(adapter, job.jobId, opts, () =>
      adapter.renderStill(job, frame)
    );
    return { evidence, routing, exportSelection };
  }

  async renderPreview(
    jobDir: string,
    opts?: DispatchCallOptions
  ): Promise<DispatchOutcome<ArtifactEvidence>> {
    const { job, routing, exportSelection } = this.routeJob(jobDir, opts);
    const adapter = this.adapterFor(routing.primaryEngine);
    const evidence = await this.runWithCall(adapter, job.jobId, opts, () =>
      adapter.renderPreview(job, opts?.preview)
    );
    return { evidence, routing, exportSelection };
  }

  /** Final render.
   *
   * Fixture-context jobs keep the MG-004 contract: the approval record
   * must carry an approved delivery decision; anything else is an
   * approval-class refusal (exit class 4) raised before any adapter is
   * invoked. Fixture renders are diagnostic evidence with no
   * production delivery privilege (see the delivery gate in
   * orchestrator/gate.ts).
   *
   * Production-context jobs are bound to the MG-025 gate: the render
   * gate must pass for the job's current immutable revision (trusted
   * design approval for the design revision, trusted preview approval
   * for the full revision, runtime identity from the routed engine's
   * probed capability record), and the record presented here must be
   * that gate-verified preview permit (Section 16.8: render accepts
   * the current PREVIEW approval; the delivery approval belongs to
   * the later package/delivery gate, after final QC). Gate failures
   * throw GateError with the stable Section 16.9 category, before any
   * adapter is invoked. */
  async renderFinal(
    jobDir: string,
    approval: Approval,
    opts?: DispatchCallOptions
  ): Promise<DispatchOutcome<ArtifactEvidence>> {
    const { job, routing, exportSelection } = this.routeJob(jobDir, opts);
    const tracker = opts?.tracker;
    if (tracker) await tracker.recordRouting(routing, exportSelection);
    try {
      const { approvedJob } = this.authorizeFinal(jobDir, job, routing, approval, opts);
      const adapter = this.adapterFor(routing.primaryEngine);
      const evidence = await this.runWithCall(adapter, job.jobId, opts, () =>
        adapter.renderFinal(approvedJob)
      );
      if (tracker) await tracker.recordRenderReceipt(evidence);
      return { evidence, routing, exportSelection };
    } catch (err) {
      if (tracker) {
        await tracker.recordFailure({
          category: errorCategoryOf(err),
          message: (err as Error).message,
        });
      }
      throw err;
    }
  }

  /**
   * Final render through the MG-027 cache session (MG-046,
   * Settlement A). Authorization is identical to renderFinal (the
   * same fixture rule, the same MG-025 render gate for production).
   * The render itself is decomposed per scene: a cache session opens
   * against the job's cache work directory (default
   * <jobDir>/working/cache; the directory is the resume context and
   * survives the process), each scene's renderer is backed by the
   * routed adapter rendering a scene-scoped view of the job, and the
   * final output is assembled ONLY from session.artifactPathFor, so
   * a scene the session has not verified complete and current can
   * never reach the output. A job interrupted mid-render and
   * rerun through this method resumes: finished scenes are reused
   * byte-identical and unre-rendered, the rest render, and the same
   * task completes.
   */
  async renderFinalCached(
    jobDir: string,
    approval: Approval,
    opts?: DispatchCallOptions
  ): Promise<CachedRenderOutcome> {
    const startedAt = new Date().toISOString();
    const startedMs = Date.now();
    const { job, routing, exportSelection } = this.routeJob(jobDir, opts);
    const tracker = opts?.tracker;
    if (tracker) await tracker.recordRouting(routing, exportSelection);
    const matrix = this.matrixFor(opts);
    const workDir = opts?.cacheWorkDir ?? join(jobDir, "working", "cache");
    let session: CachedRenderSession | null = null;
    try {
      const { approvedJob } = this.authorizeFinal(jobDir, job, routing, approval, opts);
      const profileId = job.manifest.delivery.video_profile;
      const ext = containerExtensionForProfile(profileId);
      const assemblyRecord = matrix.engines.find((r) => r.engine === routing.assemblyOwner);
      const units = deriveSceneWorkUnits(job, {
        engineFor: (sceneId) => {
          const assignment = routing.assignments.find((a) => a.sceneId === sceneId);
          const engine = assignment?.engine ?? routing.primaryEngine;
          const record = matrix.engines.find((r) => r.engine === engine);
          return { engine, adapterVersion: record?.installedVersion ?? "unprobed" };
        },
        runtimeLockId: assemblyRecord?.runtimeLockId ?? "unprobed",
        artifactFileNameFor: (sceneId) => `${sceneId}${ext}`,
      });
      session = await CachedRenderSession.open({ workDir, jobId: job.jobId, units });
      if (tracker) {
        await tracker.recordRecoveryPoint({
          cacheWorkDir: workDir,
          cacheJobKey: session.jobKey,
        });
      }
      const stagingRoot = join(jobDir, "working", "scene-jobs");
      const rendererFor = (sceneId: string): SceneRenderer => async (ctx) => {
        const assignment = routing.assignments.find((a) => a.sceneId === sceneId);
        const engine = (assignment?.engine ?? routing.primaryEngine) as Engine;
        const adapter = this.adapterFor(engine);
        const staged = stageSceneJobDir(job, sceneId, stagingRoot);
        const sceneJob: ApprovedMotionJob = {
          jobDir: staged.jobDir,
          jobId: job.jobId,
          manifest: staged.manifest,
          approval: approvedJob.approval,
        };
        const evidence = await this.runWithCall(adapter, job.jobId, opts, () =>
          adapter.renderFinal(sceneJob)
        );
        const produced = pickProducedArtifact(evidence, staged.jobDir, ext);
        copyFileSync(produced, ctx.artifactPath);
        await ctx.reportChunkComplete(0);
        try {
          return { probe: probeMediaFile(ctx.artifactPath) };
        } catch {
          return { probe: null };
        }
      };
      const report = await session.run((unit) => rendererFor(unit.sceneId));
      if (!report.ok) {
        const failed = report.results.filter((r) => r.action === "failed");
        const finding = report.findings[0];
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          message:
            `Cached final render for job ${job.jobId} failed for scene(s) ` +
            `${failed.map((f) => f.sceneId).join(", ")}: ` +
            `${finding ? `${finding.category}: ${finding.message}` : "no finding recorded"}. ` +
            "The cache session state is preserved; rerun to resume the failed scenes.",
        });
      }
      const parts: string[] = [];
      for (const entry of job.manifest.scenes) {
        const artifactPath = session.artifactPathFor(entry.id);
        if (!artifactPath) {
          throw new AdapterError({
            category: "MG_RENDER_FAILED",
            message:
              `Scene ${entry.id} has no verified complete artifact in the cache session; ` +
              "assembly from anything but artifactPathFor is refused.",
          });
        }
        parts.push(artifactPath);
      }
      const outDir = join(jobDir, "renders");
      mkdirSync(outDir, { recursive: true });
      const outPath = join(outDir, `final${ext}`);
      assembleSceneArtifacts(parts, outPath);
      const finishedAt = new Date().toISOString();
      const evidence: ArtifactEvidence = {
        engine: routing.assemblyOwner,
        runtime: {
          engine: routing.assemblyOwner,
          engineVersion: assemblyRecord?.installedVersion ?? null,
          runtimeLockId: assemblyRecord?.runtimeLockId ?? null,
          nodeVersion: process.version,
          platform: `${process.platform} ${process.arch}`,
          probedAt: assemblyRecord?.probedAt ?? null,
        },
        jobId: job.jobId,
        kind: "final",
        artifacts: [
          { path: relative(jobDir, outPath).split("\\").join("/"), sha256: sha256File(outPath) },
        ],
        outputPaths: [relative(jobDir, outPath).split("\\").join("/")],
        exitCode: 0,
        stderrLog: null,
        startedAt,
        finishedAt,
        durationMs: Date.now() - startedMs,
      };
      if (tracker) await tracker.recordRenderReceipt(evidence);
      return { evidence, routing, exportSelection, cache: report };
    } catch (err) {
      if (tracker) {
        await tracker.recordFailure({
          category: errorCategoryOf(err),
          message: (err as Error).message,
          cacheWorkDir: workDir,
          cacheJobKey: session?.jobKey ?? null,
          failedScenes:
            session === null
              ? []
              : Object.entries(session.currentState.scenes)
                  .filter(([, r]) => r.status === "failed")
                  .map(([sceneId]) => sceneId),
        });
      }
      throw err;
    }
  }

  /** The approval half of a final render, shared by renderFinal and
   * renderFinalCached so the two paths can never drift apart.
   * Fixture context: the record must be an approved delivery
   * approval. Production context: the MG-025 render gate must pass
   * and the presented record must be its verified preview permit. */
  private authorizeFinal(
    jobDir: string,
    job: ValidatedMotionJob,
    routing: RoutingDecision,
    approval: Approval,
    opts?: DispatchCallOptions
  ): { approvedJob: ApprovedMotionJob; gate: GateResult | null } {
    if (job.manifest.execution_context === "production") {
      return this.authorizeFinalProduction(jobDir, job, routing, approval, opts);
    }
    if (approval.decision !== "approved" || approval.scope !== "delivery") {
      throw new AdapterError({
        category: "MG_APPROVAL_REQUIRED",
        message:
          `Final render requires an approved delivery approval record; got ` +
          `decision "${approval.decision}" with scope "${approval.scope}".`,
      });
    }
    return { approvedJob: { ...job, approval }, gate: null };
  }

  private authorizeFinalProduction(
    jobDir: string,
    job: ValidatedMotionJob,
    routing: RoutingDecision,
    approval: Approval,
    opts?: DispatchCallOptions
  ): { approvedJob: ApprovedMotionJob; gate: GateResult } {
    const matrix = this.matrixFor(opts);
    const record = matrix.engines.find((r) => r.engine === routing.primaryEngine);
    if (
      !record ||
      record.probeStatus !== "ready" ||
      !record.installedVersion ||
      !record.runtimeLockId
    ) {
      const result: GateResult = {
        gate: "render",
        verdict: "blocked",
        jobId: job.jobId,
        companyId: job.manifest.company_id,
        diagnostic: false,
        phase: null,
        designRevision: null,
        revision: null,
        approvalId: null,
        authorityBasis: null,
        findings: [
          {
            category: "MG_RUNTIME_UNAVAILABLE",
            path: "capability-matrix",
            message:
              `Engine ${routing.primaryEngine} has no ready probe record with an exact version ` +
              "and runtime-lock identity; a production final render cannot pin its revision " +
              "to an unprobed runtime.",
          },
        ],
        firstErrorCategory: "MG_RUNTIME_UNAVAILABLE",
        exitCode: 3,
      };
      throw new GateError(result);
    }
    const gate = evaluateRenderGate(jobDir, {
      engine: routing.primaryEngine,
      engineVersion: record.installedVersion,
      runtimeLockId: record.runtimeLockId,
    });
    if (gate.verdict !== "pass") {
      throw new GateError(gate);
    }
    if (
      approval.approval_id !== gate.approvalId ||
      approval.subject_revision !== gate.revision ||
      approval.scope !== "preview" ||
      approval.decision !== "approved"
    ) {
      throw new AdapterError({
        category: "MG_APPROVAL_REQUIRED",
        message:
          "The record presented for this production final render is not the gate-verified " +
          `preview permit: the render gate passed on approval ${gate.approvalId} for revision ` +
          `${gate.revision}, but the presented record is approval ${approval.approval_id} ` +
          `(scope "${approval.scope}", decision "${approval.decision}", revision ` +
          `${approval.subject_revision}). Present the permit the gate verified.`,
      });
    }
    return { approvedJob: { ...job, approval }, gate };
  }

  async inspectMotion(
    jobDir: string,
    range: { startFrame: number; endFrameExclusive: number },
    opts?: DispatchCallOptions
  ): Promise<DispatchOutcome<MotionEvidence>> {
    const { job, routing, exportSelection } = this.routeJob(jobDir, opts);
    if (
      !Number.isInteger(range.startFrame) ||
      !Number.isInteger(range.endFrameExclusive) ||
      range.startFrame < 0 ||
      range.startFrame >= range.endFrameExclusive ||
      range.endFrameExclusive > job.manifest.duration_frames
    ) {
      throw new AdapterError({
        category: "MG_TIMELINE_INVALID",
        message:
          `Inspection range [${range.startFrame}, ${range.endFrameExclusive}) is not a ` +
          `valid half-open range within the job's ${job.manifest.duration_frames} frames.`,
      });
    }
    const adapter = this.adapterFor(routing.primaryEngine);
    const evidence = await this.runWithCall(adapter, job.jobId, opts, () =>
      adapter.inspectMotion(job, range)
    );
    return { evidence, routing, exportSelection };
  }

  /**
   * Cancel a job: abort its in-flight dispatcher call when one is tracked,
   * and notify the owning adapter. When no call is tracked, every
   * registered adapter is notified (cancel is contractually idempotent).
   */
  async cancel(jobId: string): Promise<void> {
    const tracked = this.inflight.get(jobId);
    if (tracked) {
      tracked.controller.abort();
      const adapter = this.registry.get(tracked.engine);
      if (adapter) await this.bestEffortCancel(adapter, jobId);
      return;
    }
    for (const engine of this.registry.engines()) {
      const adapter = this.registry.get(engine);
      if (adapter) await this.bestEffortCancel(adapter, jobId);
    }
  }

  private async bestEffortCancel(adapter: MotionRendererAdapter, jobId: string): Promise<void> {
    try {
      await Promise.race([
        adapter.cancel(jobId),
        new Promise<void>((resolve) => setTimeout(resolve, 2000)),
      ]);
    } catch {
      // Cancellation is best effort; the operation outcome is already set.
    }
  }

  /**
   * Invoke one adapter operation under the timeout and cancellation
   * contract. On timeout or abort the dispatcher invokes the adapter's
   * cancel for the job and reports MG_TIMEOUT (exit class 5) or
   * MG_CANCELLED (exit class 8). AdapterError failures pass through
   * unchanged; any other failure is wrapped as MG_RENDER_FAILED with the
   * original message preserved.
   */
  private async runWithCall<T>(
    adapter: MotionRendererAdapter,
    jobId: string,
    opts: DispatchCallOptions | undefined,
    op: () => Promise<T>
  ): Promise<T> {
    const timeoutMs = opts?.timeoutMs ?? this.defaultTimeoutMs;
    if (opts?.signal?.aborted) {
      throw new AdapterError({
        category: "MG_CANCELLED",
        engine: adapter.engine,
        message: `Operation for job ${jobId} was cancelled before it started.`,
      });
    }
    const controller = new AbortController();
    const onExternalAbort = (): void => controller.abort();
    opts?.signal?.addEventListener("abort", onExternalAbort, { once: true });
    this.inflight.set(jobId, { controller, engine: adapter.engine });
    const ctx: CallContext = {
      jobId,
      signal: controller.signal,
      timeoutMs,
      deadlineEpochMs: Date.now() + timeoutMs,
    };
    try {
      adapter.beginCall?.(ctx);
    } catch {
      // A failing context hook must not block the operation itself.
    }
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const abortPromise = new Promise<never>((_resolve, reject) => {
      const onAbort = (): void => {
        if (timedOut) {
          reject(
            new AdapterError({
              category: "MG_TIMEOUT",
              engine: adapter.engine,
              message: `Operation for job ${jobId} exceeded its timeout of ${timeoutMs} ms.`,
            })
          );
        } else {
          reject(
            new AdapterError({
              category: "MG_CANCELLED",
              engine: adapter.engine,
              message: `Operation for job ${jobId} was cancelled.`,
            })
          );
        }
      };
      if (controller.signal.aborted) onAbort();
      else controller.signal.addEventListener("abort", onAbort, { once: true });
    });
    try {
      return await Promise.race([op(), abortPromise]);
    } catch (err) {
      if (err instanceof AdapterError && (err.category === "MG_TIMEOUT" || err.category === "MG_CANCELLED")) {
        await this.bestEffortCancel(adapter, jobId);
        throw err;
      }
      if (err instanceof AdapterError) throw err;
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: adapter.engine,
        message: `Adapter ${adapter.engine} failed for job ${jobId}: ${(err as Error).message}`,
        stderrLog: null,
      });
    } finally {
      clearTimeout(timer);
      opts?.signal?.removeEventListener("abort", onExternalAbort);
      const tracked = this.inflight.get(jobId);
      if (tracked && tracked.controller === controller) this.inflight.delete(jobId);
    }
  }
}
