// Remotion production adapter for Skill 72 Motion Graphics V2
// (Directive MG-006, Section 5.5 interface as frozen by MG-004).
//
// Design rules honored here:
// - Engines come from the shared render runtime only
//   (shared-utils/motion-render-runtime, MG-003). This adapter resolves
//   the provisioned install through .runtime/current, reads its
//   readiness from the runtime lock the provisioner's probe wrote, and
//   never installs a second copy of Remotion. A missing or failed
//   runtime is a dependency error (MG_ENGINE_MISSING, exit class 3),
//   never a silent fallback to another engine.
// - Compositions are registered React components (src/remotion). The
//   bundle is built once per source-plus-runtime hash and reused across
//   calls and processes. The composition is selected with the same
//   validated input props that are passed to rendering, and its
//   calculated metadata is checked against those props.
// - Frame ranges are half-open internally; Remotion's inclusive
//   frameRange is produced by frame-math's explicit adapter.
// - Every receipt names the engine and the exact runtime (engine
//   version and runtime-lock identity from the probe record; never an
//   invented version). Rendered outputs are verified after rendering
//   (PNG dimensions for stills; ffprobe frame count, dimensions, and
//   frame rate for video) before any artifact is claimed.

import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { firstErrorCategory, validateJob, type Finding } from "../validation/semantics";
import {
  AdapterError,
  type ApprovedMotionJob,
  type ArtifactEvidence,
  type CallContext,
  type EngineCapabilityRecord,
  type MotionEvidence,
  type MotionRendererAdapter,
  type PreviewOptions,
  type PreviewReviewRecord,
  type RuntimeEvidence,
  type RuntimeIdentity,
  type ValidatedMotionJob,
  type ValidationEvidence,
  type FrameRange,
} from "./types";
import {
  hashJobSourceInputs,
  hashPropsPayload,
  isIdentityPlan,
  planPreview,
  previewVariantSuffix,
  PreviewPlanError,
  type PreviewPlan,
} from "../preview";
import {
  getSharedRenderBudget,
  ResourceCancelledError,
  ResourceExhaustedError,
  type Reservation,
} from "../resources";
import {
  loadC05Job,
  instrumentedBarWidths,
  type LoadedC05Job,
} from "../remotion/job-props";
import { C05_COMPOSITION_ID, toInclusiveRange } from "../remotion/frame-math";
import { probeVideoFile, readPngDimensions, decodeFrameRgb, measureAccentBarWidths } from "../remotion/decode";
import { buildExportRecord, writeExportRecordSidecar } from "../export/metadata";
import { EXPORT_PROFILES } from "../export/profiles";

// ---------------------------------------------------------------------------
// Shared-runtime resolution
// ---------------------------------------------------------------------------

interface RuntimeLockDoc {
  result?: string;
  timestamp?: string;
  node?: string;
  platform?: { os?: string; arch?: string };
  packages?: Record<string, string>;
  browser?: { revision?: string; executable?: string; versionString?: string } | null;
  engines?: Record<string, { status?: string; version?: string }>;
}

export interface ResolvedRemotionRuntime {
  sharedRuntimeDir: string;
  stateDir: string;
  /** Real directory the .runtime/current symlink points at. */
  currentDir: string | null;
  lockPath: string | null;
  lock: RuntimeLockDoc | null;
  /** Runtime-lock identity recorded in receipts: the plan directory
   * name, for example "lock-314fc289b233ca9e". */
  lockId: string | null;
  engineVersion: string | null;
  browserExecutable: string | null;
  ready: boolean;
  detail: string;
}

export interface RemotionAdapterOptions {
  /** Override for the shared runtime directory
   * (shared-utils/motion-render-runtime). Defaults to the
   * MOTION_SHARED_RUNTIME_DIR env var, then a walk up from this module. */
  sharedRuntimeDir?: string;
  /** Base directory render outputs are written under. Defaults to the
   * job directory itself, so logical artifact paths such as
   * "renders/remotion/final.mp4" resolve inside the job. Tests point
   * this at scratch space to keep fixture directories clean. */
  outputDir?: string;
  /** Font search directories (tests use an empty list or empty dir to
   * prove missing fonts fail). */
  fontSearchDirs?: string[];
}

function findSharedRuntimeDir(startDir: string): string | null {
  let dir = startDir;
  for (let i = 0; i < 12; i += 1) {
    const candidate = join(dir, "shared-utils", "motion-render-runtime");
    if (existsSync(join(candidate, "provision.sh"))) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function resolveRemotionRuntime(sharedRuntimeDir: string | null): ResolvedRemotionRuntime {
  const base: ResolvedRemotionRuntime = {
    sharedRuntimeDir: sharedRuntimeDir ?? "",
    stateDir: "",
    currentDir: null,
    lockPath: null,
    lock: null,
    lockId: null,
    engineVersion: null,
    browserExecutable: null,
    ready: false,
    detail: "",
  };
  if (!sharedRuntimeDir) {
    return {
      ...base,
      detail:
        "shared render runtime (shared-utils/motion-render-runtime) was not found above " +
        "this module; set MOTION_SHARED_RUNTIME_DIR or provision the repository checkout.",
    };
  }
  const stateDir = join(sharedRuntimeDir, ".runtime");
  base.stateDir = stateDir;
  const currentLink = join(stateDir, "current");
  let currentDir: string | null = null;
  try {
    if (existsSync(currentLink)) currentDir = realpathSync(currentLink);
  } catch {
    currentDir = null;
  }
  base.currentDir = currentDir;
  if (currentDir) base.lockId = currentDir.split("/").pop() ?? null;

  const lockCandidates = [join(stateDir, "runtime-lock.json")];
  if (currentDir) lockCandidates.push(join(currentDir, "runtime-lock.json"));
  let lock: RuntimeLockDoc | null = null;
  let lockPath: string | null = null;
  for (const candidate of lockCandidates) {
    if (existsSync(candidate)) {
      try {
        lock = JSON.parse(readFileSync(candidate, "utf8")) as RuntimeLockDoc;
        lockPath = candidate;
        break;
      } catch {
        lock = null;
      }
    }
  }
  base.lock = lock;
  base.lockPath = lockPath;
  if (!lock) {
    return {
      ...base,
      detail:
        `no readable runtime-lock.json under ${stateDir}; the shared runtime has not ` +
        "been provisioned. Run shared-utils/motion-render-runtime/provision.sh.",
    };
  }
  base.engineVersion = lock.packages?.remotion ?? null;
  if (currentDir && lock.browser?.executable) {
    const browserPath = join(currentDir, lock.browser.executable);
    base.browserExecutable = existsSync(browserPath) ? browserPath : null;
  }
  const remotionInstalled = currentDir
    ? existsSync(join(currentDir, "node_modules", "remotion", "package.json"))
    : false;
  if (lock.result !== "pass" || lock.engines?.remotion?.status !== "pass") {
    return {
      ...base,
      detail:
        `runtime lock ${lockPath} does not record a passing remotion probe ` +
        `(result ${lock.result ?? "?"}, remotion ${lock.engines?.remotion?.status ?? "?"}).`,
    };
  }
  if (!currentDir || !remotionInstalled) {
    return {
      ...base,
      detail:
        "runtime lock records a pass but .runtime/current does not resolve to an " +
        "install containing remotion; re-run the shared provisioner.",
    };
  }
  if (!base.browserExecutable) {
    return {
      ...base,
      detail:
        "runtime lock names no usable Chrome Headless Shell executable; re-run the " +
        "shared provisioner so the browser ensure step records one.",
    };
  }
  return { ...base, ready: true, detail: `runtime lock ${base.lockId} records remotion pass` };
}

// ---------------------------------------------------------------------------
// Remotion node API surface (loaded from the shared runtime at runtime)
// ---------------------------------------------------------------------------

interface RemotionCompositionConfig {
  id: string;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
}

interface BundlerModule {
  bundle: (options: Record<string, unknown>) => Promise<string>;
}

interface RendererModule {
  selectComposition: (options: Record<string, unknown>) => Promise<RemotionCompositionConfig>;
  renderStill: (options: Record<string, unknown>) => Promise<void>;
  renderMedia: (options: Record<string, unknown>) => Promise<void>;
  makeCancelSignal: () => { cancelSignal: unknown; cancel: () => void };
}

interface WebpackConfigLike {
  resolve?: {
    modules?: string[];
    alias?: Record<string, string | false>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

const CONTRACT_CATEGORIES = new Set([
  "MG_SCHEMA_INVALID",
  "MG_UNKNOWN_COMPONENT",
  "MG_MODE_MISMATCH",
  "MG_TIMELINE_INVALID",
]);

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function nowIso(): string {
  return new Date().toISOString();
}

// ---------------------------------------------------------------------------
// The adapter
// ---------------------------------------------------------------------------

export class RemotionAdapter implements MotionRendererAdapter {
  readonly engine = "remotion" as const;

  private readonly options: RemotionAdapterOptions;
  private resolved: ResolvedRemotionRuntime | null = null;
  private modulesCache: { bundler: BundlerModule; renderer: RendererModule } | null = null;
  private bundlePromises = new Map<string, Promise<{ serveUrl: string; bundleKey: string }>>();
  private compositionPromises = new Map<
    string,
    Promise<{ serveUrl: string; composition: RemotionCompositionConfig }>
  >();
  private currentCtx: CallContext | null = null;
  private readonly cancelledJobs = new Set<string>();
  /** Live Remotion cancel functions per job, registered while a render
   * call is in flight so cancel() stops the actual engine work, not
   * just the adapter's bookkeeping. */
  private readonly liveCancels = new Map<string, Set<() => void>>();

  private registerCancel(jobId: string): { cancelSignal: unknown; cancel: () => void } {
    const { renderer } = this.modules();
    const signal = renderer.makeCancelSignal();
    let set = this.liveCancels.get(jobId);
    if (!set) {
      set = new Set();
      this.liveCancels.set(jobId, set);
    }
    set.add(signal.cancel);
    return signal;
  }

  private unregisterCancel(jobId: string, cancel: () => void): void {
    const set = this.liveCancels.get(jobId);
    if (!set) return;
    set.delete(cancel);
    if (set.size === 0) this.liveCancels.delete(jobId);
  }

  constructor(options?: RemotionAdapterOptions) {
    this.options = options ?? {};
  }

  beginCall(ctx: CallContext): void {
    this.currentCtx = ctx;
  }

  // -- runtime plumbing ----------------------------------------------------

  private runtime(): ResolvedRemotionRuntime {
    if (!this.resolved) {
      const dir =
        this.options.sharedRuntimeDir ??
        process.env.MOTION_SHARED_RUNTIME_DIR ??
        findSharedRuntimeDir(__dirname);
      this.resolved = resolveRemotionRuntime(dir ?? null);
    }
    return this.resolved;
  }

  private requireReadyRuntime(): ResolvedRemotionRuntime {
    const resolved = this.runtime();
    if (!resolved.ready) {
      throw new AdapterError({
        category: "MG_ENGINE_MISSING",
        engine: "remotion",
        message:
          `The Remotion engine is not available: ${resolved.detail} ` +
          "Provision the shared runtime (shared-utils/motion-render-runtime/provision.sh) " +
          "before dispatching render work; no other engine is substituted silently.",
      });
    }
    return resolved;
  }

  private identity(): RuntimeIdentity {
    const resolved = this.runtime();
    return {
      engine: "remotion",
      engineVersion: resolved.engineVersion,
      runtimeLockId: resolved.lockId,
      nodeVersion: process.version,
      platform: `${process.platform} ${process.arch}`,
      probedAt: resolved.lock?.timestamp ?? null,
    };
  }

  private modules(): { bundler: BundlerModule; renderer: RendererModule } {
    if (this.modulesCache) return this.modulesCache;
    const resolved = this.requireReadyRuntime();
    const req = createRequire(join(resolved.currentDir as string, "package.json"));
    this.modulesCache = {
      bundler: req("@remotion/bundler") as BundlerModule,
      renderer: req("@remotion/renderer") as RendererModule,
    };
    return this.modulesCache;
  }

  private sourceDir(): string {
    const candidates = [
      resolve(__dirname, "..", "..", "..", "src", "remotion"),
      resolve(__dirname, "..", "remotion"),
    ];
    for (const candidate of candidates) {
      if (existsSync(join(candidate, "entry.ts"))) return candidate;
    }
    throw new AdapterError({
      category: "MG_ENGINE_MISSING",
      engine: "remotion",
      message: `Remotion composition sources (src/remotion/entry.ts) not found near ${__dirname}.`,
    });
  }

  private sourceHash(): string {
    const dir = this.sourceDir();
    const hash = createHash("sha256");
    const walk = (d: string): void => {
      for (const entry of readdirSync(d, { withFileTypes: true }).sort((a, b) =>
        a.name.localeCompare(b.name)
      )) {
        const p = join(d, entry.name);
        if (entry.isDirectory()) walk(p);
        else if (/\.(ts|tsx)$/.test(entry.name)) {
          hash.update(entry.name);
          hash.update(readFileSync(p));
        }
      }
    };
    walk(dir);
    return hash.digest("hex").slice(0, 24);
  }

  /** Bundle once per source-plus-runtime hash; the on-disk bundle in
   * the shared runtime state dir is reused across adapter instances
   * and processes. */
  private async ensureBundle(): Promise<{ serveUrl: string; bundleKey: string }> {
    const resolved = this.requireReadyRuntime();
    const bundleKey = `${this.sourceHash()}-${resolved.lockId ?? "nolock"}`;
    const cached = this.bundlePromises.get(bundleKey);
    if (cached) return cached;
    const promise = (async () => {
      const bundleDir = join(resolved.stateDir, "mg006-bundles", bundleKey);
      if (existsSync(join(bundleDir, "index.html"))) {
        return { serveUrl: bundleDir, bundleKey };
      }
      mkdirSync(bundleDir, { recursive: true });
      const { bundler } = this.modules();
      const nodeModules = join(resolved.currentDir as string, "node_modules");
      // The composition sources live in the skill tree, outside the
      // shared runtime's node_modules reach: point module resolution at
      // the provisioned install so 'react', 'react-dom' and 'remotion'
      // resolve to the exact shared copies (a single React instance).
      const applyResolution = (config: WebpackConfigLike): WebpackConfigLike => {
        config.resolve = config.resolve ?? {};
        config.resolve.modules = [...(config.resolve.modules ?? []), nodeModules];
        config.resolve.alias = {
          ...(config.resolve.alias ?? {}),
          react: join(nodeModules, "react"),
          "react-dom": join(nodeModules, "react-dom"),
          remotion: join(nodeModules, "remotion"),
        };
        return config;
      };
      const serveUrl = await bundler.bundle({
        entryPoint: join(this.sourceDir(), "entry.ts"),
        outDir: bundleDir,
        onProgress: () => undefined,
        webpackOverride: applyResolution,
        rspackOverride: applyResolution,
      });
      return { serveUrl, bundleKey };
    })();
    this.bundlePromises.set(bundleKey, promise);
    return promise;
  }

  /** Bundle descriptors for tests and diagnostics: one entry per
   * distinct bundle this instance has built or reused. */
  describeBundles(): { bundleKey: string }[] {
    return [...this.bundlePromises.keys()].map((bundleKey) => ({ bundleKey }));
  }

  private async compositionFor(
    loaded: LoadedC05Job
  ): Promise<{ serveUrl: string; composition: RemotionCompositionConfig }> {
    const propsKey = createHash("sha256")
      .update(JSON.stringify(loaded.props))
      .digest("hex")
      .slice(0, 24);
    const cached = this.compositionPromises.get(propsKey);
    if (cached) return cached;
    const promise = (async () => {
      const resolved = this.requireReadyRuntime();
      const { serveUrl } = await this.ensureBundle();
      const { renderer } = this.modules();
      const composition = await renderer.selectComposition({
        serveUrl,
        id: C05_COMPOSITION_ID,
        inputProps: loaded.props,
        browserExecutable: resolved.browserExecutable,
      });
      const p = loaded.props;
      if (
        composition.width !== p.canvas.width ||
        composition.height !== p.canvas.height ||
        composition.fps !== p.canvas.fps ||
        composition.durationInFrames !== p.durationFrames
      ) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: "remotion",
          message:
            `Composition metadata disagrees with the validated input props: metadata ` +
            `${composition.width}x${composition.height} at ${composition.fps} fps for ` +
            `${composition.durationInFrames} frames; props say ${p.canvas.width}x` +
            `${p.canvas.height} at ${p.canvas.fps} fps for ${p.durationFrames} frames.`,
        });
      }
      return { serveUrl, composition };
    })();
    this.compositionPromises.set(propsKey, promise);
    return promise;
  }

  private throwIfAborted(jobId: string): void {
    const ctxAborted =
      this.currentCtx && this.currentCtx.jobId === jobId && this.currentCtx.signal.aborted;
    if (this.cancelledJobs.has(jobId) || ctxAborted) {
      throw new AdapterError({
        category: "MG_CANCELLED",
        engine: "remotion",
        message: `Operation for job ${jobId} was cancelled.`,
      });
    }
  }

  private timeoutMs(jobId: string): number {
    if (this.currentCtx && this.currentCtx.jobId === jobId) {
      return Math.max(1000, this.currentCtx.deadlineEpochMs - Date.now());
    }
    return 280_000;
  }

  private outputFileFor(job: ValidatedMotionJob, logicalPath: string): string {
    const base = this.options.outputDir ?? job.jobDir;
    return join(base, logicalPath);
  }

  /**
   * MG-028: acquire a shared render-budget reservation for one
   * operation. The reservation is taken BEFORE any browser or encoder
   * launches (composition selection starts the browser, so the slot
   * precedes it) and is released by the caller's finally, so success,
   * failure, and cancellation all free the same capacity. Budget
   * refusals map onto adapter errors: a cancelled wait is the
   * adapter's own MG_CANCELLED; an exhausted budget is a retryable
   * render failure raised before anything launched.
   */
  private async acquireSlot(jobId: string, operation: string): Promise<Reservation> {
    try {
      return await getSharedRenderBudget().acquire(
        { engine: "remotion", jobId, operation },
        {
          isCancelled: () =>
            this.cancelledJobs.has(jobId) ||
            (this.currentCtx?.jobId === jobId && this.currentCtx.signal.aborted),
        }
      );
    } catch (err) {
      if (err instanceof ResourceCancelledError) {
        throw new AdapterError({
          category: "MG_CANCELLED",
          engine: "remotion",
          message: err.message,
        });
      }
      if (err instanceof ResourceExhaustedError) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: "remotion",
          message: err.message,
          retryable: true,
        });
      }
      throw err;
    }
  }

  private loadJob(job: ValidatedMotionJob, fpsOverride?: number): LoadedC05Job {
    return loadC05Job(job, {
      fpsOverride,
      fontSearchDirs: this.options.fontSearchDirs,
    });
  }

  // -- Section 5.5 operations ----------------------------------------------

  async probeRuntime(): Promise<RuntimeEvidence> {
    const resolved = this.runtime();
    const checkedAt = nowIso();
    if (!resolved.ready) {
      return {
        engine: "remotion",
        runtime: this.identity(),
        status: resolved.lock ? "unavailable" : "unprobed",
        capabilities: null,
        checkedAt,
        detail: resolved.detail,
      };
    }
    const lock = resolved.lock as RuntimeLockDoc;
    const capabilities: EngineCapabilityRecord = {
      engine: "remotion",
      probeStatus: "ready",
      installedVersion: resolved.engineVersion,
      runtimeLockId: resolved.lockId,
      probedAt: lock.timestamp ?? null,
      platform: `${lock.platform?.os ?? process.platform}/${lock.platform?.arch ?? process.arch}`,
      codecs: [],
      transparency: { alphaVideo: false, profiles: [] },
      mediaTypes: ["image/png"],
      features3d: [],
      evidence: [
        `shared runtime lock ${resolved.lockId} at ${resolved.lockPath}: probe result pass; ` +
          `the provisioner's probe rendered a real PNG still with remotion ` +
          `${resolved.engineVersion} and browser revision ${lock.browser?.revision ?? "unknown"}.`,
      ],
    };
    return {
      engine: "remotion",
      runtime: this.identity(),
      status: "ready",
      capabilities,
      checkedAt,
      detail: resolved.detail,
    };
  }

  async validate(job: ValidatedMotionJob): Promise<ValidationEvidence> {
    this.requireReadyRuntime();
    const findings: Finding[] = [...validateJob(job.jobDir)];
    if (findings.length === 0) {
      try {
        this.loadJob(job);
      } catch (err) {
        if (err instanceof AdapterError && err.category !== "MG_ENGINE_MISSING") {
          findings.push({
            category: CONTRACT_CATEGORIES.has(err.category)
              ? (err.category as Finding["category"])
              : "MG_SCHEMA_INVALID",
            path: job.jobId,
            message: err.message,
          });
        } else {
          throw err;
        }
      }
    }
    return {
      engine: "remotion",
      runtime: this.identity(),
      jobId: job.jobId,
      valid: findings.length === 0,
      findings,
      firstErrorCategory: firstErrorCategory(findings),
      checkedAt: nowIso(),
    };
  }

  async renderStill(
    job: ValidatedMotionJob,
    frame: number,
    opts?: { fpsOverride?: number }
  ): Promise<ArtifactEvidence> {
    // MG-028: the still's browser launch runs under a reservation.
    const reservation = await this.acquireSlot(job.jobId, "renderStill");
    try {
      return await this.renderStillReserved(job, frame, opts);
    } finally {
      await reservation.release();
    }
  }

  private async renderStillReserved(
    job: ValidatedMotionJob,
    frame: number,
    opts?: { fpsOverride?: number }
  ): Promise<ArtifactEvidence> {
    const startedAt = nowIso();
    const startMs = Date.now();
    this.requireReadyRuntime();
    const loaded = this.loadJob(job, opts?.fpsOverride);
    if (!Number.isInteger(frame) || frame < 0 || frame >= loaded.durationFrames) {
      throw new AdapterError({
        category: "MG_TIMELINE_INVALID",
        engine: "remotion",
        message:
          `Still frame ${frame} lies outside the composition's frames ` +
          `0..${loaded.durationFrames - 1} at ${loaded.fps} fps.`,
      });
    }
    this.throwIfAborted(job.jobId);
    const { serveUrl, composition } = await this.compositionFor(loaded);
    this.throwIfAborted(job.jobId);
    const fpsSuffix = opts?.fpsOverride ? `-${loaded.fps}fps` : "";
    const logicalPath = `renders/remotion/still-${loaded.props.layoutVariant}${fpsSuffix}-f${frame}.png`;
    const output = this.outputFileFor(job, logicalPath);
    mkdirSync(dirname(output), { recursive: true });
    const { renderer } = this.modules();
    const resolved = this.requireReadyRuntime();
    const signal = this.registerCancel(job.jobId);
    try {
      await renderer.renderStill({
        composition,
        serveUrl,
        frame,
        output,
        inputProps: loaded.props,
        browserExecutable: resolved.browserExecutable,
        imageFormat: "png",
        overwrite: true,
        cancelSignal: signal.cancelSignal,
        timeoutInMilliseconds: this.timeoutMs(job.jobId),
      });
    } finally {
      this.unregisterCancel(job.jobId, signal.cancel);
    }
    this.throwIfAborted(job.jobId);
    const dims = readPngDimensions(output);
    if (!dims || dims.width !== loaded.props.canvas.width || dims.height !== loaded.props.canvas.height) {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: "remotion",
        message:
          `Rendered still ${output} has dimensions ${dims ? `${dims.width}x${dims.height}` : "unreadable"}, ` +
          `expected ${loaded.props.canvas.width}x${loaded.props.canvas.height}.`,
      });
    }
    return {
      engine: "remotion",
      runtime: this.identity(),
      jobId: job.jobId,
      kind: "still",
      artifacts: [{ path: logicalPath, sha256: sha256File(output) }],
      outputPaths: [output],
      exitCode: 0,
      stderrLog: null,
      startedAt,
      finishedAt: nowIso(),
      durationMs: Date.now() - startMs,
    };
  }

  /** Shared video render for preview and final: identical source,
   * props, and timing (Section 17.1 M15 parity), then the output is
   * probed and must match the planned frame count, dimensions, and
   * frame rate exactly before any artifact is claimed (M01). */
  private async renderVideo(
    job: ValidatedMotionJob,
    kind: "preview" | "final",
    fileName: string,
    media?: { codec: string; pixelFormat: string; crf?: number; proResProfile?: string }
  ): Promise<{ evidence: ArtifactEvidence; loaded: LoadedC05Job }> {
    // MG-028: one reservation covers the whole video render; the
    // engine's nested tab concurrency is set from the reservation so
    // what the budget accounted for is what the engine runs.
    const reservation = await this.acquireSlot(
      job.jobId,
      kind === "final" ? "renderFinal" : "renderPreview"
    );
    try {
      return await this.renderVideoReserved(
        job,
        kind,
        fileName,
        reservation.profile.nestedConcurrency,
        media
      );
    } finally {
      await reservation.release();
    }
  }

  private async renderVideoReserved(
    job: ValidatedMotionJob,
    kind: "preview" | "final",
    fileName: string,
    tabs: number,
    media?: { codec: string; pixelFormat: string; crf?: number; proResProfile?: string }
  ): Promise<{ evidence: ArtifactEvidence; loaded: LoadedC05Job }> {
    const startedAt = nowIso();
    const startMs = Date.now();
    this.requireReadyRuntime();
    const loaded = this.loadJob(job);
    this.throwIfAborted(job.jobId);
    const { serveUrl, composition } = await this.compositionFor(loaded);
    this.throwIfAborted(job.jobId);
    const logicalPath = `renders/remotion/${fileName}`;
    const output = this.outputFileFor(job, logicalPath);
    mkdirSync(dirname(output), { recursive: true });
    const { renderer } = this.modules();
    const resolved = this.requireReadyRuntime();
    const frameRange = toInclusiveRange({
      startFrame: 0,
      endFrameExclusive: loaded.durationFrames,
    });
    const signal = this.registerCancel(job.jobId);
    try {
      await renderer.renderMedia({
        composition,
        serveUrl,
        // MG-040: the historical encode is h264/yuv420p/crf 16. A
        // delivery profile's media override (renderFinal, alpha
        // profiles only) replaces exactly the codec fields; every
        // other render input is identical.
        ...(media
          ? {
              codec: media.codec,
              pixelFormat: media.pixelFormat,
              ...(media.proResProfile ? { proResProfile: media.proResProfile } : {}),
              ...(media.crf !== undefined ? { crf: media.crf } : {}),
            }
          : { codec: "h264", pixelFormat: "yuv420p", crf: 16 }),
        outputLocation: output,
        inputProps: loaded.props,
        browserExecutable: resolved.browserExecutable,
        frameRange,
        concurrency: tabs,
        overwrite: true,
        cancelSignal: signal.cancelSignal,
        timeoutInMilliseconds: this.timeoutMs(job.jobId),
      });
    } finally {
      this.unregisterCancel(job.jobId, signal.cancel);
    }
    this.throwIfAborted(job.jobId);
    const probe = probeVideoFile(output);
    const problems: string[] = [];
    if (probe.width !== loaded.props.canvas.width || probe.height !== loaded.props.canvas.height) {
      problems.push(`dimensions ${probe.width}x${probe.height}, expected ${loaded.props.canvas.width}x${loaded.props.canvas.height}`);
    }
    if (probe.frameCount !== loaded.durationFrames) {
      problems.push(`frame count ${probe.frameCount}, expected ${loaded.durationFrames}`);
    }
    if (probe.fpsNumerator !== loaded.fps || probe.fpsDenominator !== 1) {
      problems.push(`frame rate ${probe.fpsNumerator}/${probe.fpsDenominator}, expected ${loaded.fps}/1`);
    }
    if (problems.length > 0) {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: "remotion",
        message: `Rendered video ${output} failed output verification: ${problems.join("; ")}.`,
      });
    }
    const evidence: ArtifactEvidence = {
      engine: "remotion",
      runtime: this.identity(),
      jobId: job.jobId,
      kind,
      artifacts: [{ path: logicalPath, sha256: sha256File(output) }],
      outputPaths: [output],
      exitCode: 0,
      stderrLog: null,
      startedAt,
      finishedAt: nowIso(),
      durationMs: Date.now() - startMs,
    };
    return { evidence, loaded };
  }

  /** MG-024: stamp a preview render with its review record and write
   * the record as a sidecar beside the artifact. The geometry passed
   * in comes from the probe the render path already enforced, so the
   * record states measured output, never the plan alone. */
  private stampPreviewReview(
    job: ValidatedMotionJob,
    fileName: string,
    output: string,
    loaded: LoadedC05Job,
    plan: PreviewPlan,
    probe: { width: number; height: number; frameCount: number; durationSeconds: number }
  ): PreviewReviewRecord {
    const record: PreviewReviewRecord = {
      schemaVersion: "1.0",
      engine: "remotion",
      jobId: job.jobId,
      kind: "preview",
      label: plan.label,
      roughLayoutOnly: plan.roughLayoutOnly,
      scale: plan.scale,
      scaleMethod: plan.scale === 1 ? "none" : "render_scale",
      sourceHash: hashJobSourceInputs(job.jobDir, job.manifest),
      propsHash: hashPropsPayload(loaded.props),
      previewHash: sha256File(output),
      final: {
        width: job.manifest.canvas.width,
        height: job.manifest.canvas.height,
        fps: job.manifest.canvas.fps,
        durationFrames: job.manifest.duration_frames,
      },
      preview: {
        width: probe.width,
        height: probe.height,
        fps: loaded.fps,
        durationFrames: probe.frameCount,
        durationSeconds: probe.durationSeconds,
      },
      generatedAt: nowIso(),
    };
    const sidecarName = fileName.replace(/\.mp4$/, ".review.json");
    writeFileSync(
      this.outputFileFor(job, `renders/remotion/${sidecarName}`),
      JSON.stringify(record, null, 2) + "\n",
      "utf8"
    );
    return record;
  }

  async renderPreview(
    job: ValidatedMotionJob,
    opts?: PreviewOptions
  ): Promise<ArtifactEvidence> {
    let plan: PreviewPlan;
    try {
      plan = planPreview(job.manifest.canvas, job.manifest.duration_frames, opts);
    } catch (err) {
      if (err instanceof PreviewPlanError) {
        throw new AdapterError({
          category: "MG_SCHEMA_INVALID",
          engine: "remotion",
          message: err.message,
        });
      }
      throw err;
    }
    if (isIdentityPlan(plan)) {
      // The historical preview, unchanged: canonical dimensions at the
      // full authored fps, rendered from the same props as the final.
      const { evidence, loaded } = await this.renderVideo(job, "preview", "preview.mp4");
      const record = this.stampPreviewReview(job, "preview.mp4", evidence.outputPaths[0], loaded, plan, {
        width: loaded.props.canvas.width,
        height: loaded.props.canvas.height,
        frameCount: loaded.durationFrames,
        durationSeconds: loaded.durationFrames / loaded.fps,
      });
      return { ...evidence, previewReview: record };
    }
    return this.renderVariantPreview(job, plan);
  }

  /** MG-024 variant preview: a spatially scaled and/or rough-layout
   * render of the same composition. The composition stays authored at
   * canonical dimensions and Remotion's own render scale reduces the
   * spatial resolution, so geometry is preserved by construction;
   * a rough variant additionally loads the job at the plan's reduced
   * fps, which preserves every event's time in seconds (frame-math).
   * The output is probed against the plan before any artifact is
   * claimed, exactly like the canonical render path. */
  private async renderVariantPreview(
    job: ValidatedMotionJob,
    plan: PreviewPlan
  ): Promise<ArtifactEvidence> {
    // MG-028: variant previews hold the same render reservation as
    // the canonical preview (identical footprint, scaled output).
    const reservation = await this.acquireSlot(job.jobId, "renderPreview");
    try {
      return await this.renderVariantPreviewReserved(
        job,
        plan,
        reservation.profile.nestedConcurrency
      );
    } finally {
      await reservation.release();
    }
  }

  private async renderVariantPreviewReserved(
    job: ValidatedMotionJob,
    plan: PreviewPlan,
    tabs: number
  ): Promise<ArtifactEvidence> {
    const startedAt = nowIso();
    const startMs = Date.now();
    this.requireReadyRuntime();
    const loaded = this.loadJob(job, plan.roughLayoutOnly ? plan.fps : undefined);
    this.throwIfAborted(job.jobId);
    const { serveUrl, composition } = await this.compositionFor(loaded);
    this.throwIfAborted(job.jobId);
    const fileName = `preview-${previewVariantSuffix(plan)}.mp4`;
    const logicalPath = `renders/remotion/${fileName}`;
    const output = this.outputFileFor(job, logicalPath);
    mkdirSync(dirname(output), { recursive: true });
    const { renderer } = this.modules();
    const resolved = this.requireReadyRuntime();
    const frameRange = toInclusiveRange({
      startFrame: 0,
      endFrameExclusive: loaded.durationFrames,
    });
    const signal = this.registerCancel(job.jobId);
    try {
      await renderer.renderMedia({
        composition,
        serveUrl,
        codec: "h264",
        outputLocation: output,
        inputProps: loaded.props,
        browserExecutable: resolved.browserExecutable,
        crf: 16,
        pixelFormat: "yuv420p",
        frameRange,
        concurrency: tabs,
        scale: plan.scale,
        overwrite: true,
        cancelSignal: signal.cancelSignal,
        timeoutInMilliseconds: this.timeoutMs(job.jobId),
      });
    } finally {
      this.unregisterCancel(job.jobId, signal.cancel);
    }
    this.throwIfAborted(job.jobId);
    const probe = probeVideoFile(output);
    const problems: string[] = [];
    if (probe.width !== plan.width || probe.height !== plan.height) {
      problems.push(
        `dimensions ${probe.width}x${probe.height}, expected the plan's ${plan.width}x${plan.height}`
      );
    }
    if (probe.frameCount !== loaded.durationFrames) {
      problems.push(`frame count ${probe.frameCount}, expected ${loaded.durationFrames}`);
    }
    if (probe.fpsNumerator !== loaded.fps || probe.fpsDenominator !== 1) {
      problems.push(
        `frame rate ${probe.fpsNumerator}/${probe.fpsDenominator}, expected ${loaded.fps}/1`
      );
    }
    if (problems.length > 0) {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: "remotion",
        message: `Rendered preview ${output} failed output verification: ${problems.join("; ")}.`,
      });
    }
    const evidence: ArtifactEvidence = {
      engine: "remotion",
      runtime: this.identity(),
      jobId: job.jobId,
      kind: "preview",
      artifacts: [{ path: logicalPath, sha256: sha256File(output) }],
      outputPaths: [output],
      exitCode: 0,
      stderrLog: null,
      startedAt,
      finishedAt: nowIso(),
      durationMs: Date.now() - startMs,
    };
    const record = this.stampPreviewReview(job, fileName, output, loaded, plan, {
      width: probe.width,
      height: probe.height,
      frameCount: probe.frameCount,
      durationSeconds: probe.durationSeconds,
    });
    return { ...evidence, previewReview: record };
  }

  async renderFinal(job: ApprovedMotionJob): Promise<ArtifactEvidence> {
    // MG-040: the final follows the job's delivery profile. The
    // opaque default is the historical final.mp4 path, unchanged.
    // ProRes 4444 renders natively through renderMedia. VP9 with
    // alpha has no native render wired here: the qualified route is
    // the export layer's image-sequence encode, so the request fails
    // capability by name instead of silently producing an opaque or
    // mislabeled artifact.
    const profile = EXPORT_PROFILES[job.manifest.delivery.video_profile];
    if (profile.id === "vp9_alpha") {
      throw new AdapterError({
        category: "MG_CAPABILITY_UNSUPPORTED",
        engine: "remotion",
        message:
          "The Remotion adapter has no native VP9 alpha render. Profile vp9_alpha is " +
          "qualified for Remotion only through the export layer's image-sequence " +
          "encode (PNG frames plus libvpx-vp9, yuva420p); see references/export-profiles.md.",
      });
    }
    const alpha = profile.id === "prores_4444_alpha";
    const fileName = alpha ? "final.mov" : "final.mp4";
    const { evidence } = await this.renderVideo(
      job,
      "final",
      fileName,
      alpha
        ? { codec: "prores", pixelFormat: "yuva444p10le", proResProfile: "4444" }
        : undefined
    );
    // MG-040: the packaging record is built from measurement of the
    // finished artifact and written as a sidecar beside it. A final
    // whose measured stream contradicts its profile fails here
    // (buildExportRecord throws MG_QC_FAILED) instead of shipping
    // with a label the artifact does not carry.
    const outAbs = evidence.outputPaths[0];
    const route = profile.routes.remotion;
    const exportRecord = buildExportRecord({
      profile,
      route: { engine: "remotion", kind: route.kind, detail: route.detail },
      artifactAbsPath: outAbs,
      artifactLogicalPath: `renders/remotion/${fileName}`,
    });
    if (exportRecord.stream.codec !== profile.streamCodec) {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: "remotion",
        message:
          `Rendered final ${outAbs} probed as codec ${exportRecord.stream.codec}, not the ` +
          `${profile.streamCodec} the delivery profile ${profile.id} requires.`,
      });
    }
    writeExportRecordSidecar(exportRecord, `${outAbs}.export-record.json`);
    const finalEvidence: ArtifactEvidence = { ...evidence, exportRecord };
    // The delivery poster is part of the final artifact set: the
    // manifest's declared poster frame, rendered from the same props
    // and recorded under its delivery name.
    const posterFrame = job.manifest.delivery.poster_frame;
    const poster = await this.renderStill(job, posterFrame);
    const posterLogical = `renders/remotion/poster-f${posterFrame}.png`;
    const posterOut = this.outputFileFor(job, posterLogical);
    if (poster.outputPaths[0] !== posterOut) {
      mkdirSync(dirname(posterOut), { recursive: true });
      copyFileSync(poster.outputPaths[0], posterOut);
    }
    return {
      ...finalEvidence,
      artifacts: [
        ...finalEvidence.artifacts,
        { path: posterLogical, sha256: sha256File(posterOut) },
      ],
      outputPaths: [...finalEvidence.outputPaths, posterOut],
      durationMs: finalEvidence.durationMs + poster.durationMs,
      finishedAt: nowIso(),
    };
  }

  async inspectMotion(job: ValidatedMotionJob, range: FrameRange): Promise<MotionEvidence> {
    this.requireReadyRuntime();
    const loaded = this.loadJob(job);
    const observations: string[] = [];
    let checked = 0;
    let passed = 0;
    for (const assertion of loaded.scene.semantic_motion_assertions) {
      if (assertion.frame < range.startFrame || assertion.frame >= range.endFrameExclusive) {
        continue;
      }
      checked += 1;
      if (assertion.kind !== "bar_widths") {
        observations.push(
          `assertion ${assertion.id} (kind ${assertion.kind}) at frame ${assertion.frame}: ` +
            "not measurable by the Remotion adapter in this implementation; counted as not passed."
        );
        continue;
      }
      const instrumented = instrumentedBarWidths(loaded.props, assertion.frame);
      const still = await this.renderStill(job, assertion.frame);
      const rgb = decodeFrameRgb(
        still.outputPaths[0],
        null,
        loaded.props.canvas.width,
        loaded.props.canvas.height
      );
      const decoded = measureAccentBarWidths(
        rgb,
        loaded.props.canvas.width,
        loaded.props.design.layout,
        loaded.props.design.colors.accent
      );
      const expected = assertion.expected_values;
      const instrumentedOk = expected.every(
        (v, i) => Math.abs(instrumented[i] - v) <= assertion.tolerance
      );
      const decodedOk = expected.every((v, i) => Math.abs(decoded[i] - v) <= 2);
      if (instrumentedOk && decodedOk) passed += 1;
      observations.push(
        `assertion ${assertion.id} at frame ${assertion.frame}: instrumented widths ` +
          `[${instrumented.map((w) => Math.round(w * 1000) / 1000).join(", ")}], decoded widths ` +
          `[${decoded.join(", ")}], expected [${expected.join(", ")}] ` +
          `(tolerance ${assertion.tolerance} instrumented, 2 decoded): ` +
          `${instrumentedOk && decodedOk ? "PASS" : "FAIL"}.`
      );
    }
    return {
      engine: "remotion",
      runtime: this.identity(),
      jobId: job.jobId,
      range,
      assertionsChecked: checked,
      assertionsPassed: passed,
      observations,
      inspectedAt: nowIso(),
    };
  }

  async cancel(jobId: string): Promise<void> {
    this.cancelledJobs.add(jobId);
    const set = this.liveCancels.get(jobId);
    if (set) {
      for (const cancel of [...set]) {
        try {
          cancel();
        } catch {
          // Cancellation is best effort; the dispatcher contract is
          // already satisfied by the cancelled mark above.
        }
      }
    }
  }
}

/** Construct the Remotion adapter for a dispatcher registry
 * (createRegistry([createRemotionAdapter()])). */
export function createRemotionAdapter(options?: RemotionAdapterOptions): RemotionAdapter {
  return new RemotionAdapter(options);
}
