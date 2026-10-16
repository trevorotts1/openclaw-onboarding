// Hyperframes production adapter for Skill 72 Motion Graphics V2 (MG-005).
//
// Implements the frozen Section 5.5 MotionRendererAdapter interface
// against the pinned Hyperframes CLI (0.8.155) from the shared rendering
// runtime (MG-003). The adapter never installs anything and never builds
// shell strings: every CLI invocation is a checked argument array passed
// to spawn without a shell (Directive Section 5.5), so user copy and
// filenames can never be reinterpreted by a shell.
//
// Engine access rule: the CLI binary, the GSAP bundle, and the runtime
// identity all come from the shared runtime's promoted install
// (shared-utils/motion-render-runtime/.runtime/current) and its
// runtime-lock.json record. When the lock is missing or does not record
// a hyperframes pass, render-path operations fail with the dependency
// error MG_ENGINE_MISSING (exit class 3) and probeRuntime reports the
// engine unavailable with the same cause in its detail.
//
// CLI operations used (flags verified against the pinned CLI's --help
// and locked here per Directive 16.10): compositions --json for the
// composition registry, lint --json and check --json for validation
// (check is the one-session lint + runtime + layout + motion + contrast
// gate; a report that evaluated zero checks is not a pass), snapshot
// --at for proof stills, render for preview and final MP4 output.
// Rendering mode and the exact CLI version are captured in a receipt
// sidecar next to every rendered artifact.

import { spawn, ChildProcess } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join, relative, resolve } from "node:path";
import type { Dataset, Design, Scene } from "../validation/generated-types";
import { firstErrorCategory, type Finding } from "../validation/semantics";
import {
  BeforeAfterSceneSpec,
  generateC01Project,
  generateC02Project,
  generateC03Project,
  generateC05Project,
  generateMediaProject,
  generateNestedProject,
  GeneratedProject,
  ImageRevealSceneSpec,
  MediaTimedSceneSpec,
  Mg005SceneSpec,
  Mg044SceneSpec,
  NestedDetailSceneSpec,
  ProductDetailSceneSpec,
} from "../hyperframes/generators";
import {
  resolveFont,
  ResolvedFont,
  sha256File,
  SharedRuntimePaths,
  vendorIntoProject,
} from "../hyperframes/project";
import { decodePng, measureBarWidth, measureColorFraction } from "../hyperframes/measure";
import { buildExportRecord, writeExportRecordSidecar, type ExportRecord } from "../export/metadata";
import { EXPORT_PROFILES } from "../export/profiles";
import { capabilityRecord, loadCapabilityMatrix } from "./capabilities";
import {
  AdapterError,
  ApprovedMotionJob,
  ArtifactEvidence,
  CallContext,
  EngineCapabilityRecord,
  FrameRange,
  MotionEvidence,
  MotionRendererAdapter,
  PreviewOptions,
  PreviewReviewRecord,
  RuntimeEvidence,
  RuntimeIdentity,
  ValidatedMotionJob,
  ValidationEvidence,
} from "./types";
import {
  hashJobSourceInputs,
  isIdentityPlan,
  planPreview,
  previewVariantSuffix,
  rescaleFrames,
  sha256Hex,
  PreviewPlanError,
  type PreviewPlan,
} from "../preview";
import {
  getSharedRenderBudget,
  profileFor,
  ResourceCancelledError,
  ResourceExhaustedError,
  type Reservation,
  type ResourceProfile,
} from "../resources";
import {
  applyNetworkPolicy,
  buildRenderEnv,
  networkModeFromEnv,
  ProcessRegistry,
  readStartTimeTicks,
  redactSecrets,
  sanitizeJobSegment,
  secretValuesOf,
  signalProcess,
  terminateJobProcesses,
  validateAssetRef,
  IsolationError,
} from "../isolation";

const ENGINE = "hyperframes" as const;
const OUTPUT_ROOT = join("renders", "hyperframes");
const TAIL_CHARS = 8000;

interface RuntimeLock {
  timestamp?: string;
  platform?: { os?: string; arch?: string };
  packages?: Record<string, string | null>;
  engines?: Record<string, { status?: string }>;
  result?: string;
}

interface ResolvedRuntime extends SharedRuntimePaths {
  lock: RuntimeLock;
  engineVersion: string;
}

/** Resolve the shared runtime install. Search order: explicit override,
 * MOTION_RUNTIME_DIR, then walk up from this module looking for the
 * shared-utils/motion-render-runtime sibling (the repository layout). */
export function resolveSharedRuntime(explicitRoot?: string): ResolvedRuntime {
  // An explicit root (constructor option or MOTION_RUNTIME_DIR) is
  // authoritative: it is the only candidate tried, so a wrong override
  // fails loudly instead of silently falling back to a discovered
  // runtime. Discovery by walking up runs only with no override.
  const candidates: string[] = [];
  if (explicitRoot) candidates.push(resolve(explicitRoot));
  else if (process.env.MOTION_RUNTIME_DIR) candidates.push(resolve(process.env.MOTION_RUNTIME_DIR));
  else {
    let dir = __dirname;
    for (let i = 0; i < 10; i += 1) {
      candidates.push(join(dir, "shared-utils", "motion-render-runtime"));
      const parent = dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  const problems: string[] = [];
  for (const root of candidates) {
    const lockPath = join(root, ".runtime", "runtime-lock.json");
    const currentLink = join(root, ".runtime", "current");
    if (!existsSync(lockPath)) {
      problems.push(`${root}: no .runtime/runtime-lock.json (runtime not provisioned)`);
      continue;
    }
    let lock: RuntimeLock;
    try {
      lock = JSON.parse(readFileSync(lockPath, "utf8")) as RuntimeLock;
    } catch (err) {
      problems.push(`${root}: runtime-lock.json is not valid JSON (${(err as Error).message})`);
      continue;
    }
    const hf = lock.engines?.hyperframes;
    if (!hf || hf.status !== "pass") {
      problems.push(
        `${root}: runtime lock does not record a hyperframes pass (status: ${hf?.status ?? "absent"})`
      );
      continue;
    }
    if (!existsSync(currentLink)) {
      problems.push(`${root}: .runtime/current promotion link is missing`);
      continue;
    }
    const currentDir = realpathSync(currentLink);
    const cliBin = join(currentDir, "node_modules", ".bin", "hyperframes");
    if (!existsSync(cliBin)) {
      problems.push(`${root}: hyperframes CLI missing at ${cliBin}`);
      continue;
    }
    const version = lock.packages?.hyperframes ?? null;
    if (!version) {
      problems.push(`${root}: runtime lock records no hyperframes package version`);
      continue;
    }
    return {
      runtimeRoot: root,
      currentDir,
      runtimeLockId: basename(currentDir),
      lockPath,
      cliBin,
      gsapPath: join(currentDir, "node_modules", "gsap", "dist", "gsap.min.js"),
      lock,
      engineVersion: version,
    };
  }
  throw new AdapterError({
    category: "MG_ENGINE_MISSING",
    engine: ENGINE,
    message:
      "The shared motion render runtime has no verified Hyperframes install. " +
      `Checked: ${problems.join("; ")}. Provision it with ` +
      "shared-utils/motion-render-runtime/provision.sh; the adapter does not install engines.",
  });
}

interface RunResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  durationMs: number;
}

function tailOf(text: string): string {
  return text.length > TAIL_CHARS ? text.slice(-TAIL_CHARS) : text;
}

/** Hash one materialized scene project (MG-024 props hash input): the
 * generated files are the exact content payload the CLI consumes, so
 * identical hashes across preview and final prove the two renders
 * consumed the same composition. */
function hashProjectFiles(project: GeneratedProject): string {
  const parts: string[] = [];
  for (const rel of Object.keys(project.files).sort()) {
    parts.push(`${rel}\0${project.files[rel]}`);
  }
  return sha256Hex(parts.join("\0"));
}

/** One scene of a job, resolved to its generator input. */
interface ScenePlan {
  sceneId: string;
  specRelPath: string;
  startFrame: number;
  durationFrames: number;
  kind: "c05" | "c01-reveal" | "c01-nested" | "c02-media" | "c02-detail" | "c03-compare";
  scene?: Scene;
  dataset?: Dataset;
  design?: Design;
  spec?: Mg005SceneSpec | Mg044SceneSpec;
  font: ResolvedFont;
  projectDir: string;
  outDir: string;
}

export class HyperframesAdapter implements MotionRendererAdapter {
  readonly engine = ENGINE;
  private readonly runtimeOverride?: string;
  private runtimeCache: ResolvedRuntime | null = null;
  private readonly contexts = new Map<string, { ctx: CallContext; recordedAt: number }>();
  private readonly children = new Map<string, Set<ChildProcess>>();
  private readonly cancelledJobs = new Set<string>();
  /** MG-029: the shared process registry this adapter records every
   * child into, and the per-job ownership tokens its children carry. */
  private processRegistryCache: ProcessRegistry | null = null;
  private readonly jobTokens = new Map<string, string>();

  private registry(): ProcessRegistry {
    if (!this.processRegistryCache) this.processRegistryCache = new ProcessRegistry();
    return this.processRegistryCache;
  }

  private jobToken(jobId: string): string {
    let token = this.jobTokens.get(jobId);
    if (!token) {
      token = this.registry().tokenFor(jobId);
      this.jobTokens.set(jobId, token);
    }
    return token;
  }

  constructor(opts?: { runtimeRoot?: string }) {
    this.runtimeOverride = opts?.runtimeRoot;
  }

  beginCall(ctx: CallContext): void {
    this.contexts.set(ctx.jobId, { ctx, recordedAt: Date.now() });
    // A fresh call supersedes any earlier cancellation of the same job:
    // the cancelled mark belongs to the call that was in flight when it
    // was set, not to the job forever.
    this.cancelledJobs.delete(ctx.jobId);
    if (ctx.signal.aborted) {
      this.cancelledJobs.add(ctx.jobId);
      return;
    }
    ctx.signal.addEventListener(
      "abort",
      () => {
        void this.cancel(ctx.jobId);
      },
      { once: true }
    );
  }

  async cancel(jobId: string): Promise<void> {
    this.cancelledJobs.add(jobId);
    const set = this.children.get(jobId);
    if (set) {
      for (const child of set) {
        // MG-029: signal the child's whole process group, not just the
        // CLI process, so the browser it launched cannot be orphaned
        // by its parent's death. The group is this child's own
        // (children spawn detached), never the caller's group.
        if (child.pid) signalProcess(child.pid, "SIGTERM", child.pid);
        else {
          try {
            child.kill("SIGTERM");
          } catch {
            // Already exited.
          }
        }
      }
      // Escalate shortly after if a child ignores SIGTERM.
      setTimeout(() => {
        for (const child of set) {
          if (child.pid) signalProcess(child.pid, "SIGKILL", child.pid);
          else {
            try {
              child.kill("SIGKILL");
            } catch {
              // Already exited.
            }
          }
        }
      }, 400).unref();
    }
    // MG-029 backstop: terminate any other process this job owns
    // (browser grandchildren of a CLI that already exited, helper
    // processes) through the registry's ownership verification. Only
    // processes proven to belong to this job are signaled.
    void terminateJobProcesses(this.registry(), jobId, { graceMs: 400 }).catch(
      () => undefined
    );
  }

  private runtime(): ResolvedRuntime {
    if (!this.runtimeCache) this.runtimeCache = resolveSharedRuntime(this.runtimeOverride);
    return this.runtimeCache;
  }

  private identity(): RuntimeIdentity {
    const rt = this.runtime();
    const os = rt.lock.platform?.os ?? process.platform;
    const arch = rt.lock.platform?.arch ?? process.arch;
    return {
      engine: ENGINE,
      engineVersion: rt.engineVersion,
      runtimeLockId: rt.runtimeLockId,
      nodeVersion: process.version,
      platform: `${os} ${arch}`,
      probedAt: rt.lock.timestamp ?? null,
    };
  }

  private capabilityRecord(): EngineCapabilityRecord | null {
    try {
      return capabilityRecord(loadCapabilityMatrix(), ENGINE);
    } catch {
      return null;
    }
  }

  /**
   * MG-028: the resource profile for one engine process launch. The
   * budget counts processes, so the profile follows what the process
   * actually is: a render carries a browser and an encoder, a
   * snapshot carries a browser, an ffmpeg step is the encoder alone,
   * a probe is neither. The render profile is sized from the
   * measured whole-tree peak (the CLI multiplies Chromium processes
   * internally; the peak already includes them).
   */
  private profileForCall(bin: string, args: string[]): ResourceProfile {
    const base = basename(bin);
    if (base === "ffprobe") {
      return {
        memoryMB: 128,
        browserUnits: 0,
        encodeUnits: 0,
        diskMB: 16,
        nestedConcurrency: 1,
        label: "ffprobe output probe",
      };
    }
    if (base === "ffmpeg") return profileFor(ENGINE, "encode");
    switch (args[0]) {
      case "render":
        return profileFor(ENGINE, "renderFinal");
      case "snapshot":
        return profileFor(ENGINE, "renderStill");
      case "check":
        return profileFor(ENGINE, "validate");
      default:
        return {
          memoryMB: 256,
          browserUnits: 0,
          encodeUnits: 0,
          diskMB: 32,
          nestedConcurrency: 1,
          label: `hyperframes CLI ${args[0] ?? "call"} (no browser or encoder)`,
        };
    }
  }

  /** MG-028: acquire the shared render-budget reservation for one
   * process launch, mapping budget refusals onto adapter errors. */
  private async acquireSlot(jobId: string, bin: string, args: string[]): Promise<Reservation> {
    const base = basename(bin);
    const operation =
      base === "ffmpeg" ? "encode" : base === "ffprobe" ? "probe" : (args[0] ?? "cli");
    try {
      return await getSharedRenderBudget().acquire(
        { engine: ENGINE, jobId, operation, profile: this.profileForCall(bin, args) },
        { isCancelled: () => this.cancelledJobs.has(jobId) }
      );
    } catch (err) {
      if (err instanceof ResourceCancelledError) {
        throw new AdapterError({ category: "MG_CANCELLED", engine: ENGINE, message: err.message });
      }
      if (err instanceof ResourceExhaustedError) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: ENGINE,
          message: err.message,
          retryable: true,
        });
      }
      throw err;
    }
  }

  /**
   * Run one CLI or helper process for a job under an MG-028
   * reservation: the slot is acquired before the process launches and
   * released when it exits, so at any instant the processes alive are
   * exactly the reservations held. Sequential launches inside one
   * adapter operation re-acquire between steps, which is what makes
   * the accounting honest at process granularity and lets a contended
   * machine interleave jobs at step boundaries. The one exception is
   * the runtime probe's --version check ("probe:" job ids): a version
   * probe must answer even when the render budget is fully booked,
   * and it launches no browser or encoder.
   *
   * MG-029 isolation applies to every child this spawns:
   * - the environment comes from the isolation layer's allowlist scrub
   *   (src/isolation/env.ts), so no provider secret present in the host
   *   environment reaches the engine, its browser, or the encoder; the
   *   job's ownership token rides along so every descendant process is
   *   attributable to this job, and HYPERFRAMES_SKIP_SKILLS plus the
   *   telemetry opt-outs are applied after the scrub;
   * - the child spawns detached (its own process group) and is
   *   recorded in the shared process registry with its kernel
   *   start-time, so cancellation and end-of-run cleanup can terminate
   *   exactly this job's processes and prove it;
   * - when MOTION_RENDER_NETWORK names a policy, the child runs inside
   *   a network namespace; a policy this machine cannot enforce
   *   refuses the launch instead of running open;
   * - captured output is secret-redacted before it is returned or
   *   stored as evidence.
   */
  private async runProcess(
    jobId: string,
    bin: string,
    args: string[],
    opts: { cwd: string; timeoutMs: number }
  ): Promise<RunResult> {
    if (jobId.startsWith("probe:")) {
      return this.runProcessReserved(jobId, bin, args, opts);
    }
    const reservation = await this.acquireSlot(jobId, bin, args);
    try {
      return await this.runProcessReserved(jobId, bin, args, opts);
    } finally {
      await reservation.release();
    }
  }

  /**
   * The process launch itself: checked argument array, no shell,
   * captured output tails, cancellation and timeout enforced by
   * killing the child. The child environment never carries a Gemini
   * key (the snapshot describe path must stay off: no network in
   * renders) and always sets HYPERFRAMES_SKIP_SKILLS so no CLI path
   * reaches for the skills registry.
   */
  private async runProcessReserved(
    jobId: string,
    bin: string,
    args: string[],
    opts: { cwd: string; timeoutMs: number }
  ): Promise<RunResult> {
    if (this.cancelledJobs.has(jobId)) {
      throw new AdapterError({
        category: "MG_CANCELLED",
        engine: ENGINE,
        message: `Hyperframes operation for job ${jobId} was cancelled before it started.`,
      });
    }
    const started = Date.now();
    const secretValues = secretValuesOf(process.env);
    let tmpDir: string | undefined;
    if (process.env.MOTION_JOB_WORK_ROOT) {
      tmpDir = join(process.env.MOTION_JOB_WORK_ROOT, sanitizeJobSegment(jobId), "tmp");
      mkdirSync(tmpDir, { recursive: true });
    }
    const built = buildRenderEnv(process.env, {
      jobId,
      jobToken: this.jobToken(jobId),
      tmpDir,
      extra: {
        HYPERFRAMES_SKIP_SKILLS: "1",
        // Rendering is local and deterministic: the CLI's anonymous
        // telemetry stays off for every child this adapter launches.
        HYPERFRAMES_NO_TELEMETRY: "1",
        DO_NOT_TRACK: "1",
      },
    });
    const env = built.env;
    let launchBin = bin;
    let launchArgs = args;
    try {
      const networkMode = networkModeFromEnv(process.env);
      if (networkMode !== "off") {
        const wrapped = applyNetworkPolicy(bin, args, networkMode);
        launchBin = wrapped.bin;
        launchArgs = wrapped.args;
      }
    } catch (err) {
      if (err instanceof IsolationError) {
        throw new AdapterError({
          category: "MG_CAPABILITY_MISSING",
          engine: ENGINE,
          message: err.message,
        });
      }
      throw err;
    }
    const registry = this.registry();
    const result = await new Promise<RunResult>((resolvePromise, rejectPromise) => {
      const child = spawn(launchBin, launchArgs, {
        cwd: opts.cwd,
        env,
        shell: false,
        detached: true,
      });
      if (child.pid) {
        registry.record({
          jobId,
          token: this.jobToken(jobId),
          role: basename(bin),
          bin,
          argv: args.map((a) => redactSecrets(a, secretValues)),
          cwd: opts.cwd,
          pid: child.pid,
          pgid: child.pid,
          startTimeTicks: readStartTimeTicks(child.pid),
          startedAt: new Date().toISOString(),
          state: "running",
          exitCode: null,
        });
      }
      let set = this.children.get(jobId);
      if (!set) {
        set = new Set();
        this.children.set(jobId, set);
      }
      set.add(child);
      let stdout = "";
      let stderr = "";
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        // Kill the child's process group, not only the CLI: a timed
        // out engine must not leave its browser running.
        if (child.pid) signalProcess(child.pid, "SIGKILL", child.pid);
        else {
          try {
            child.kill("SIGKILL");
          } catch {
            // Already exited.
          }
        }
      }, opts.timeoutMs);
      child.stdout.on("data", (d: Buffer) => {
        stdout = tailOf(stdout + d.toString("utf8"));
      });
      child.stderr.on("data", (d: Buffer) => {
        stderr = tailOf(stderr + d.toString("utf8"));
      });
      child.on("error", (err) => {
        clearTimeout(timer);
        set.delete(child);
        if (child.pid) registry.markExited(jobId, child.pid, null);
        rejectPromise(
          new AdapterError({
            category: "MG_ENGINE_MISSING",
            engine: ENGINE,
            message: `Failed to launch ${bin}: ${err.message}`,
          })
        );
      });
      child.on("close", (code) => {
        clearTimeout(timer);
        set.delete(child);
        if (child.pid) registry.markExited(jobId, child.pid, code ?? null);
        if (this.cancelledJobs.has(jobId)) {
          rejectPromise(
            new AdapterError({
              category: "MG_CANCELLED",
              engine: ENGINE,
              message: `Hyperframes operation for job ${jobId} was cancelled.`,
            })
          );
          return;
        }
        if (timedOut) {
          rejectPromise(
            new AdapterError({
              category: "MG_TIMEOUT",
              engine: ENGINE,
              message:
                `Hyperframes process ${basename(bin)} ${args[0] ?? ""} exceeded ` +
                `${opts.timeoutMs} ms and was killed.`,
              stderrLog: redactSecrets(tailOf(stderr), secretValues) || null,
            })
          );
          return;
        }
        resolvePromise({
          exitCode: code ?? 1,
          // stdout carries the CLI's JSON reports: redact exact host
          // secret values only, so the structure survives intact.
          // stderr is free text and gets full pattern redaction.
          stdout: redactSecrets(stdout, secretValues, { valuesOnly: true }),
          stderr: redactSecrets(stderr, secretValues),
          durationMs: Date.now() - started,
        });
      });
    });
    return result;
  }

  private timeoutFor(jobId: string, fallbackMs: number): number {
    const record = this.contexts.get(jobId);
    if (!record) return fallbackMs;
    // A CallContext describes ONE call: the dispatcher records it via
    // beginCall immediately before invoking the operation, and this
    // adapter consults it when spawning that call's first subprocess,
    // which happens seconds later at most (planning and materializing
    // are local file work). A context recorded long ago belongs to a
    // finished earlier call; letting its nearly expired deadline govern
    // a new call shrinks the new call's timeout toward the 1000 ms
    // floor and misreports the outcome as MG_TIMEOUT. Long operations
    // stay safe: later subprocess spawns fall back to the generous
    // per-operation defaults, and the dispatcher's own deadline race
    // and abort signal still bound the call as a whole.
    if (Date.now() - record.recordedAt > 60000) return fallbackMs;
    const remaining = record.ctx.deadlineEpochMs - Date.now();
    if (remaining <= 0) return fallbackMs;
    return Math.max(1000, Math.min(fallbackMs, remaining));
  }

  // ---------------------------------------------------------------------
  // Job loading and composition materialization
  // ---------------------------------------------------------------------

  private readJson<T>(jobDir: string, rel: string): T {
    const abs = join(jobDir, rel);
    if (!existsSync(abs)) {
      throw new AdapterError({
        category: "MG_SCHEMA_INVALID",
        engine: ENGINE,
        message: `Job ${jobDir} is missing a required file: ${rel}.`,
      });
    }
    try {
      return JSON.parse(readFileSync(abs, "utf8")) as T;
    } catch (err) {
      throw new AdapterError({
        category: "MG_SCHEMA_INVALID",
        engine: ENGINE,
        message: `Job file ${rel} is not valid JSON: ${(err as Error).message}`,
      });
    }
  }

  /** Scene start offsets declared by the job timeline, when one exists.
   * Scenes without a timeline entry are laid out sequentially in
   * manifest order by planScenes. */
  private timelineStarts(job: ValidatedMotionJob): Map<string, number> {
    const starts = new Map<string, number>();
    const timelineRel = job.manifest.timeline;
    if (timelineRel && existsSync(join(job.jobDir, timelineRel))) {
      try {
        const timeline = JSON.parse(readFileSync(join(job.jobDir, timelineRel), "utf8")) as {
          scenes?: Array<{ id: string; start_frame: number }>;
        };
        for (const s of timeline.scenes ?? []) starts.set(s.id, s.start_frame);
      } catch {
        // A malformed timeline is the contracts layer's finding; the
        // adapter falls back to sequential layout rather than guessing.
      }
    }
    return starts;
  }

  /**
   * Resolve every scene of the job to a generator plan. Unknown
   * components and unreadable specs are returned as findings (validate)
   * or thrown (render paths), per the caller's needs.
   */
  private planScenes(
    job: ValidatedMotionJob,
    findings: Finding[] | null
  ): ScenePlan[] {
    const plans: ScenePlan[] = [];
    const starts = this.timelineStarts(job);
    let sequentialCursor = 0;
    for (const entry of job.manifest.scenes) {
      const specRel = entry.spec;
      const fail = (category: Finding["category"], message: string): void => {
        if (findings) {
          findings.push({ category, path: specRel, message });
        } else {
          throw new AdapterError({ category, engine: ENGINE, message });
        }
      };
      let raw: Record<string, unknown>;
      try {
        raw = this.readJson<Record<string, unknown>>(job.jobDir, specRel);
      } catch (err) {
        fail("MG_SCHEMA_INVALID", (err as Error).message);
        continue;
      }
      const base = {
        sceneId: entry.id,
        specRelPath: specRel,
        startFrame: starts.get(entry.id) ?? sequentialCursor,
        projectDir: join(job.jobDir, OUTPUT_ROOT, entry.id, "src"),
        outDir: join(job.jobDir, OUTPUT_ROOT, entry.id),
      };
      if (raw.schema_version === "2.0" && raw.component_id === "C05") {
        const scene = raw as unknown as Scene;
        if (scene.engine !== "hyperframes") {
          fail(
            "MG_SCHEMA_INVALID",
            `Scene ${entry.id} names engine "${scene.engine}"; the Hyperframes adapter cannot render it.`
          );
          continue;
        }
        let dataset: Dataset;
        let design: Design;
        try {
          dataset = this.readJson<Dataset>(job.jobDir, scene.data_path);
          design = this.readJson<Design>(job.jobDir, scene.design_path);
        } catch (err) {
          fail("MG_SCHEMA_INVALID", (err as Error).message);
          continue;
        }
        let font: ResolvedFont;
        try {
          font = resolveFont(design.font_ref);
        } catch (err) {
          fail("MG_SCHEMA_INVALID", (err as Error).message);
          continue;
        }
        plans.push({
          ...base,
          kind: "c05",
          durationFrames: scene.duration_frames,
          scene,
          dataset,
          design,
          font,
        });
        sequentialCursor = base.startFrame + scene.duration_frames;
        continue;
      }
      if (raw.schema_version === "mg044-1") {
        const spec = raw as unknown as Mg044SceneSpec;
        if (spec.engine !== "hyperframes") {
          fail(
            "MG_SCHEMA_INVALID",
            `Scene ${entry.id} names engine "${spec.engine}"; the Hyperframes adapter cannot render it.`
          );
          continue;
        }
        let font: ResolvedFont;
        try {
          font = resolveFont(spec.font_ref);
        } catch (err) {
          fail("MG_SCHEMA_INVALID", (err as Error).message);
          continue;
        }
        const kind =
          spec.component_id === "C02" && spec.variant === "detail_closeup"
            ? "c02-detail"
            : spec.component_id === "C03" && spec.variant === "wipe_reveal"
              ? "c03-compare"
              : null;
        if (!kind) {
          fail(
            "MG_UNKNOWN_COMPONENT",
            `Scene ${entry.id} names component ${spec.component_id} variant ` +
              `${(spec as { variant?: string }).variant ?? "(none)"}, which no Hyperframes ` +
              "generator is registered for."
          );
          continue;
        }
        plans.push({ ...base, kind, durationFrames: spec.duration_frames, spec, font });
        sequentialCursor = base.startFrame + spec.duration_frames;
        continue;
      }
      if (raw.schema_version === "mg005-1") {
        const spec = raw as unknown as Mg005SceneSpec;
        if (spec.engine !== "hyperframes") {
          fail(
            "MG_SCHEMA_INVALID",
            `Scene ${entry.id} names engine "${spec.engine}"; the Hyperframes adapter cannot render it.`
          );
          continue;
        }
        let font: ResolvedFont;
        try {
          font = resolveFont(spec.font_ref);
        } catch (err) {
          fail("MG_SCHEMA_INVALID", (err as Error).message);
          continue;
        }
        const kind =
          spec.component_id === "C01" && spec.variant === "nested_detail"
            ? "c01-nested"
            : spec.component_id === "C01"
              ? "c01-reveal"
              : spec.component_id === "C02" && spec.variant === "media_timing"
                ? "c02-media"
                : null;
        if (!kind) {
          fail(
            "MG_UNKNOWN_COMPONENT",
            `Scene ${entry.id} names component ${spec.component_id} variant ` +
              `${(spec as { variant?: string }).variant ?? "(none)"}, which no Hyperframes ` +
              "generator is registered for."
          );
          continue;
        }
        plans.push({ ...base, kind, durationFrames: spec.duration_frames, spec, font });
        sequentialCursor = base.startFrame + spec.duration_frames;
        continue;
      }
      fail(
        "MG_UNKNOWN_COMPONENT",
        `Scene ${entry.id} has component_id ${JSON.stringify(raw.component_id)} with ` +
          `schema_version ${JSON.stringify(raw.schema_version)}; no Hyperframes generator ` +
          "is registered for it."
      );
    }
    return plans;
  }

  /** Verify declared asset files exist (and match their declared hash
   * when one is recorded). Returns findings; empty means inputs ready. */
  private assetFindings(job: ValidatedMotionJob, plan: ScenePlan): Finding[] {
    const out: Finding[] = [];
    const check = (rel: string, expectedSha: string | undefined, label: string): void => {
      // MG-029: the reference itself is validated before the
      // filesystem is touched for content. A hostile reference
      // (traversal, absolute path, URL) fails here with the rule code
      // named, instead of being resolved as an ordinary path. The
      // finding keeps the isolation layer's own category, so a hostile
      // reference surfaces as MG_SECURITY_VIOLATION end to end rather
      // than being flattened into a schema error.
      const refCheck = validateAssetRef(rel, { jobDir: job.jobDir });
      if (!refCheck.ok) {
        out.push({
          category: refCheck.findings[0].category,
          path: rel,
          message:
            `Scene ${plan.sceneId} ${label} reference refused ` +
            `[${refCheck.findings[0].code}]: ${refCheck.findings[0].message}`,
        });
        return;
      }
      const abs = join(job.jobDir, rel);
      if (!existsSync(abs)) {
        out.push({
          category: "MG_SCHEMA_INVALID",
          path: rel,
          message: `Scene ${plan.sceneId} references a missing ${label}: ${rel}.`,
        });
        return;
      }
      if (expectedSha) {
        const actual = sha256File(abs);
        if (actual !== expectedSha) {
          out.push({
            category: "MG_SCHEMA_INVALID",
            path: rel,
            message:
              `Scene ${plan.sceneId} ${label} hash mismatch: declared ${expectedSha}, ` +
              `actual ${actual}. The asset changed after the spec was authored.`,
          });
        }
      }
    };
    if (plan.kind === "c01-reveal" || plan.kind === "c01-nested") {
      const spec = plan.spec as ImageRevealSceneSpec | NestedDetailSceneSpec;
      check(spec.asset_file, spec.asset_sha256, "subject asset");
    }
    if (plan.kind === "c02-media") {
      const spec = plan.spec as MediaTimedSceneSpec;
      check(spec.media_file, spec.media_sha256, "media asset");
    }
    if (plan.kind === "c02-detail") {
      const spec = plan.spec as ProductDetailSceneSpec;
      check(spec.asset_file, spec.asset_sha256, "product view asset");
    }
    if (plan.kind === "c03-compare") {
      const spec = plan.spec as BeforeAfterSceneSpec;
      check(spec.before_file, spec.before_sha256, "before-state asset");
      check(spec.after_file, spec.after_sha256, "after-state asset");
    }
    return out;
  }

  /** Generate the scene's Hyperframes project into its source directory
   * and copy declared assets in. Deterministic: same spec, same bytes. */
  private materialize(job: ValidatedMotionJob, plan: ScenePlan): { project: GeneratedProject } {
    const rt = this.runtime();
    const fps = job.manifest.canvas.fps;
    let project: GeneratedProject;
    let assetRel: string | null = null;
    const extraAssets: string[] = [];
    if (plan.kind === "c05") {
      project = generateC05Project({
        scene: plan.scene as Scene,
        dataset: plan.dataset as Dataset,
        design: plan.design as Design,
        font: plan.font,
        fps,
        canvas: { width: job.manifest.canvas.width, height: job.manifest.canvas.height },
      });
    } else if (plan.kind === "c01-reveal") {
      const spec = plan.spec as ImageRevealSceneSpec;
      project = generateC01Project({ spec, font: plan.font, fps, assetFileName: basename(spec.asset_file) });
      assetRel = spec.asset_file;
    } else if (plan.kind === "c01-nested") {
      const spec = plan.spec as NestedDetailSceneSpec;
      project = generateNestedProject({ spec, font: plan.font, fps, assetFileName: basename(spec.asset_file) });
      assetRel = spec.asset_file;
    } else if (plan.kind === "c02-detail") {
      const spec = plan.spec as ProductDetailSceneSpec;
      project = generateC02Project({ spec, font: plan.font, fps, assetFileName: basename(spec.asset_file) });
      assetRel = spec.asset_file;
    } else if (plan.kind === "c03-compare") {
      const spec = plan.spec as BeforeAfterSceneSpec;
      project = generateC03Project({
        spec,
        font: plan.font,
        fps,
        beforeFileName: basename(spec.before_file),
        afterFileName: basename(spec.after_file),
      });
      assetRel = spec.before_file;
      extraAssets.push(spec.after_file);
    } else {
      const spec = plan.spec as MediaTimedSceneSpec;
      project = generateMediaProject({ spec, font: plan.font, fps, mediaFileName: basename(spec.media_file) });
      assetRel = spec.media_file;
    }
    rmSync(plan.projectDir, { recursive: true, force: true });
    mkdirSync(plan.projectDir, { recursive: true });
    vendorIntoProject(plan.projectDir, `${job.jobId}-${plan.sceneId}`, rt, plan.font);
    for (const [rel, content] of Object.entries(project.files)) {
      const abs = join(plan.projectDir, rel);
      mkdirSync(dirname(abs), { recursive: true });
      writeFileSync(abs, content, "utf8");
    }
    if (assetRel) this.copyAsset(job, plan, assetRel);
    for (const extra of extraAssets) this.copyAsset(job, plan, extra);
    return { project };
  }

  private copyAsset(job: ValidatedMotionJob, plan: ScenePlan, rel: string): void {
    // MG-029: same reference validation as the findings path; a
    // hostile reference is refused with its rule code named, and the
    // copy source is the validated, symlink-resolved path.
    const refCheck = validateAssetRef(rel, { jobDir: job.jobDir });
    if (!refCheck.ok) {
      throw new AdapterError({
        category: refCheck.findings[0].category,
        engine: ENGINE,
        message:
          `Scene ${plan.sceneId} asset reference refused ` +
          `[${refCheck.findings[0].code}]: ${refCheck.findings[0].message}`,
      });
    }
    const src = refCheck.resolvedPath ?? join(job.jobDir, rel);
    if (!existsSync(src)) {
      throw new AdapterError({
        category: "MG_SCHEMA_INVALID",
        engine: ENGINE,
        message: `Scene ${plan.sceneId} references a missing asset file: ${rel}.`,
      });
    }
    const dest = join(plan.projectDir, "assets", basename(rel));
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(src, dest);
  }

  // ---------------------------------------------------------------------
  // Interface operations
  // ---------------------------------------------------------------------

  async probeRuntime(): Promise<RuntimeEvidence> {
    const checkedAt = new Date().toISOString();
    let rt: ResolvedRuntime;
    try {
      rt = this.runtime();
    } catch (err) {
      return {
        engine: ENGINE,
        runtime: {
          engine: ENGINE,
          engineVersion: null,
          runtimeLockId: null,
          nodeVersion: process.version,
          platform: `${process.platform} ${process.arch}`,
          probedAt: null,
        },
        status: "unavailable",
        capabilities: null,
        checkedAt,
        detail: (err as Error).message,
      };
    }
    // A real launch record: the pinned CLI must answer --version and its
    // output must agree with the version the runtime lock measured.
    try {
      const res = await this.runProcess("probe:hyperframes", rt.cliBin, ["--version"], {
        cwd: rt.runtimeRoot,
        timeoutMs: 60000,
      });
      const printed = (res.stdout || res.stderr).trim().split("\n")[0] ?? "";
      if (res.exitCode !== 0 || !printed.includes(rt.engineVersion)) {
        return {
          engine: ENGINE,
          runtime: this.identity(),
          status: "unavailable",
          capabilities: this.capabilityRecord(),
          checkedAt,
          detail:
            `Hyperframes CLI --version exited ${res.exitCode} printing "${printed}", ` +
            `which does not agree with the runtime lock version ${rt.engineVersion}.`,
        };
      }
      return {
        engine: ENGINE,
        runtime: this.identity(),
        status: "ready",
        capabilities: this.capabilityRecord(),
        checkedAt,
        detail:
          `Hyperframes CLI ${printed} launched from the shared runtime install ` +
          `${rt.runtimeLockId}; runtime lock ${rt.lockPath} records a hyperframes pass ` +
          `at ${rt.lock.timestamp ?? "unknown time"}.`,
      };
    } catch (err) {
      return {
        engine: ENGINE,
        runtime: this.identity(),
        status: "unavailable",
        capabilities: this.capabilityRecord(),
        checkedAt,
        detail: `Hyperframes CLI launch failed: ${(err as Error).message}`,
      };
    }
  }

  async validate(job: ValidatedMotionJob): Promise<ValidationEvidence> {
    const checkedAt = new Date().toISOString();
    const rt = this.runtime();
    const findings: Finding[] = [];
    const plans = this.planScenes(job, findings);
    for (const plan of plans) {
      const assetProblems = this.assetFindings(job, plan);
      findings.push(...assetProblems);
      // A scene whose spec failed to plan, or whose declared assets are
      // missing or hash-mismatched, is reported through findings and
      // never materialized: validation must fail clearly, not throw.
      if (assetProblems.length > 0) continue;
      if (findings.some((f) => f.path === plan.specRelPath)) continue;
      const { project } = this.materialize(job, plan);
      // Composition registry: the generated project must actually
      // register the composition ids the generator claims (broken ids
      // fail here, clearly, before any render).
      const listed = await this.runCli(job.jobId, rt, ["compositions", plan.projectDir, "--json"], plan.projectDir, 120000);
      if (listed.exitCode !== 0) {
        findings.push({
          category: "MG_SCHEMA_INVALID",
          path: plan.specRelPath,
          message: `hyperframes compositions failed for scene ${plan.sceneId}: ${tailOf(listed.stderr || listed.stdout)}`,
        });
        continue;
      }
      const ids = compositionIdsFromJson(listed.stdout);
      for (const id of project.compositionIds) {
        if (!ids.includes(id)) {
          findings.push({
            category: "MG_SCHEMA_INVALID",
            path: plan.specRelPath,
            message:
              `Composition id "${id}" for scene ${plan.sceneId} is not registered in the ` +
              "generated project (hyperframes compositions does not list it).",
          });
        }
      }
      // Static lint gate.
      const lint = await this.runCli(job.jobId, rt, ["lint", plan.projectDir, "--json"], plan.projectDir, 120000);
      const lintReport = parseJsonObject(lint.stdout);
      const errorCount = typeof lintReport?.errorCount === "number" ? lintReport.errorCount : null;
      if (lint.exitCode !== 0 || (errorCount !== null && errorCount > 0)) {
        findings.push({
          category: "MG_SCHEMA_INVALID",
          path: plan.specRelPath,
          message:
            `hyperframes lint reports ${errorCount ?? "an unknown number of"} error(s) for ` +
            `scene ${plan.sceneId}: ${firstLintMessages(lint.stdout)}`,
        });
        continue;
      }
      // One-session audit gate: lint + runtime + layout + motion +
      // contrast. Per Directive MG-005, a report with zero evaluated
      // checks is not a successful audit when checks were expected.
      const check = await this.runCli(
        job.jobId,
        rt,
        ["check", plan.projectDir, "--json", "--samples", "3"],
        plan.projectDir,
        this.timeoutFor(job.jobId, 600000)
      );
      const evaluated = countEvaluatedChecks(check.stdout);
      if (evaluated === 0) {
        findings.push({
          category: "MG_SCHEMA_INVALID",
          path: plan.specRelPath,
          message:
            `hyperframes check for scene ${plan.sceneId} evaluated zero checks; ` +
            "an empty audit is not a pass. Raw report head: " +
            (check.stdout || check.stderr).slice(0, 300),
        });
        continue;
      }
      if (check.exitCode !== 0) {
        findings.push({
          category: "MG_SCHEMA_INVALID",
          path: plan.specRelPath,
          message:
            `hyperframes check failed for scene ${plan.sceneId} (exit ${check.exitCode}, ` +
            `${evaluated} checks evaluated): ${tailOf(check.stderr || check.stdout)}`,
        });
      }
    }
    return {
      engine: ENGINE,
      runtime: this.identity(),
      jobId: job.jobId,
      valid: findings.length === 0,
      findings,
      firstErrorCategory: firstErrorCategory(findings),
      checkedAt,
    };
  }

  async renderStill(job: ValidatedMotionJob, frame: number): Promise<ArtifactEvidence> {
    const startedAt = new Date().toISOString();
    const started = Date.now();
    this.runtime();
    const plans = this.planScenes(job, null);
    const plan = plans.find((p) => frame >= p.startFrame && frame < p.startFrame + p.durationFrames);
    if (!plan) {
      throw new AdapterError({
        category: "MG_TIMELINE_INVALID",
        engine: ENGINE,
        message: `Frame ${frame} lies outside every scene of job ${job.jobId}.`,
      });
    }
    const png = await this.snapshotFrame(job, plan, frame - plan.startFrame, plan.outDir);
    const destRel = join(OUTPUT_ROOT, plan.sceneId, `still-${frame}.png`);
    const destAbs = join(job.jobDir, destRel);
    mkdirSync(dirname(destAbs), { recursive: true });
    copyFileSync(png, destAbs);
    const finishedAt = new Date().toISOString();
    return {
      engine: ENGINE,
      runtime: this.identity(),
      jobId: job.jobId,
      kind: "still",
      artifacts: [{ path: destRel.split("\\").join("/"), sha256: sha256File(destAbs) }],
      outputPaths: [destRel.split("\\").join("/")],
      exitCode: 0,
      stderrLog: null,
      startedAt,
      finishedAt,
      durationMs: Date.now() - started,
    };
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
          engine: ENGINE,
          message: err.message,
        });
      }
      throw err;
    }
    return this.renderVideo(job, "preview", "draft", plan);
  }

  async renderFinal(job: ApprovedMotionJob): Promise<ArtifactEvidence> {
    return this.renderVideo(job, "final", "delivery", null);
  }

  async inspectMotion(job: ValidatedMotionJob, range: FrameRange): Promise<MotionEvidence> {
    this.runtime();
    const plans = this.planScenes(job, null);
    const observations: string[] = [];
    let checked = 0;
    let passed = 0;
    for (const plan of plans) {
      if (plan.kind === "c05") {
        const scene = plan.scene as Scene;
        const design = plan.design as Design;
        const layout = design.layouts[scene.layout_variant];
        const fps = job.manifest.canvas.fps;
        for (const assertion of scene.semantic_motion_assertions) {
          if (assertion.kind !== "bar_widths") {
            observations.push(
              `assertion ${assertion.id}: kind ${assertion.kind} is not evaluated by the Hyperframes adapter`
            );
            continue;
          }
          const globalFrame = plan.startFrame + assertion.frame;
          if (globalFrame < range.startFrame || globalFrame >= range.endFrameExclusive) continue;
          const png = await this.snapshotFrame(job, plan, assertion.frame, join(plan.outDir, "inspect"));
          const img = await decodePng(png);
          const widths = (assertion.subject_ids as string[]).map((subjectId, i) => {
            const y = layout.row_y[i] + Math.floor(layout.bar_height / 2);
            return measureBarWidth(img, layout.plot.x, y, layout.plot.width, design.colors.accent);
          });
          // Directive M04: decoded raster boundary within 2 source
          // pixels excluding antialias edges. The assertion's own
          // declared tolerance is recorded alongside.
          const tolerance = Math.max(2, assertion.tolerance);
          const ok = widths.every(
            (w, i) => Math.abs(w - (assertion.expected_values[i] ?? NaN)) <= tolerance
          );
          checked += 1;
          if (ok) passed += 1;
          observations.push(
            `assertion ${assertion.id} at frame ${assertion.frame} (${fps} fps): measured bar ` +
              `widths [${widths.join(", ")}], expected [${assertion.expected_values.join(", ")}], ` +
              `decoded tolerance ${tolerance} px (declared ${assertion.tolerance} px): ${ok ? "PASS" : "FAIL"}`
          );
        }
      } else if (plan.kind === "c01-reveal") {
        const spec = plan.spec as ImageRevealSceneSpec;
        const holdFrame = spec.motion.hold_to_frame_exclusive - 1;
        const holdPng = await this.snapshotFrame(job, plan, holdFrame, join(plan.outDir, "inspect"));
        const holdImg = await decodePng(holdPng);
        const holdFraction = measureColorFraction(holdImg, spec.subject.box, spec.subject.measure_color);
        for (const assertion of spec.semantic_motion_assertions) {
          const globalFrame = plan.startFrame + assertion.frame;
          if (globalFrame < range.startFrame || globalFrame >= range.endFrameExclusive) continue;
          const png = await this.snapshotFrame(job, plan, assertion.frame, join(plan.outDir, "inspect"));
          const img = await decodePng(png);
          const raw = measureColorFraction(img, spec.subject.box, spec.subject.measure_color);
          const normalized = holdFraction > 0 ? raw / holdFraction : 0;
          const ok = normalized >= assertion.min_fraction && normalized <= assertion.max_fraction;
          checked += 1;
          if (ok) passed += 1;
          observations.push(
            `assertion ${assertion.id} at frame ${assertion.frame}: subject "${spec.subject.id}" ` +
              `revealed fraction ${normalized.toFixed(3)} (raw color fraction ${raw.toFixed(3)}, ` +
              `hold reference ${holdFraction.toFixed(3)}), expected within ` +
              `[${assertion.min_fraction}, ${assertion.max_fraction}]: ${ok ? "PASS" : "FAIL"}`
          );
        }
      } else if (plan.kind === "c03-compare") {
        const spec = plan.spec as BeforeAfterSceneSpec;
        const holdFrame = spec.motion.hold_to_frame_exclusive - 1;
        const holdPng = await this.snapshotFrame(job, plan, holdFrame, join(plan.outDir, "inspect"));
        const holdImg = await decodePng(holdPng);
        const holdFraction = measureColorFraction(holdImg, spec.subject.box, spec.subject.measure_color);
        for (const assertion of spec.semantic_motion_assertions) {
          const globalFrame = plan.startFrame + assertion.frame;
          if (globalFrame < range.startFrame || globalFrame >= range.endFrameExclusive) continue;
          const png = await this.snapshotFrame(job, plan, assertion.frame, join(plan.outDir, "inspect"));
          const img = await decodePng(png);
          const raw = measureColorFraction(img, spec.subject.box, spec.subject.measure_color);
          const normalized = holdFraction > 0 ? raw / holdFraction : 0;
          const ok = normalized >= assertion.min_fraction && normalized <= assertion.max_fraction;
          checked += 1;
          if (ok) passed += 1;
          observations.push(
            `assertion ${assertion.id} at frame ${assertion.frame}: after-state "${spec.subject.id}" ` +
              `fraction ${normalized.toFixed(3)} (raw color fraction ${raw.toFixed(3)}, ` +
              `hold reference ${holdFraction.toFixed(3)}), expected within ` +
              `[${assertion.min_fraction}, ${assertion.max_fraction}]: ${ok ? "PASS" : "FAIL"}`
          );
        }
      } else {
        observations.push(
          `scene ${plan.sceneId} (${plan.kind}): no adapter-evaluated semantic assertions registered`
        );
      }
    }
    return {
      engine: ENGINE,
      runtime: this.identity(),
      jobId: job.jobId,
      range,
      assertionsChecked: checked,
      assertionsPassed: passed,
      observations,
      inspectedAt: new Date().toISOString(),
    };
  }

  // ---------------------------------------------------------------------
  // Rendering internals
  // ---------------------------------------------------------------------

  private async runCli(
    jobId: string,
    rt: ResolvedRuntime,
    args: string[],
    cwd: string,
    timeoutMs: number
  ): Promise<RunResult> {
    return this.runProcess(jobId, rt.cliBin, args, { cwd, timeoutMs });
  }

  /** Capture one frame of one scene as a PNG via the snapshot command:
   * exact instant at frame / fps, end frame excluded (--no-end), the
   * deterministic software rasterizer (--no-browser-gpu), and the vision
   * describe path disabled (no network). Returns the PNG path. */
  private async snapshotFrame(
    job: ValidatedMotionJob,
    plan: ScenePlan,
    localFrame: number,
    outRoot: string
  ): Promise<string> {
    const rt = this.runtime();
    this.materialize(job, plan);
    const fps = job.manifest.canvas.fps;
    const snapDir = join(outRoot, "snapshots", `f${localFrame}`);
    rmSync(snapDir, { recursive: true, force: true });
    mkdirSync(snapDir, { recursive: true });
    const at = (localFrame / fps).toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
    const res = await this.runCli(
      job.jobId,
      rt,
      [
        "snapshot",
        plan.projectDir,
        "-o",
        snapDir,
        "--at",
        at === "" ? "0" : at,
        "--no-end",
        "--no-browser-gpu",
        "--describe",
        "false",
      ],
      plan.projectDir,
      this.timeoutFor(job.jobId, 600000)
    );
    if (res.exitCode !== 0) {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: ENGINE,
        message:
          `hyperframes snapshot failed for scene ${plan.sceneId} at frame ${localFrame} ` +
          `(exit ${res.exitCode}).`,
        stderrLog: tailOf(res.stderr || res.stdout) || null,
      });
    }
    const pngs = readdirSync(snapDir)
      .filter((f) => f.toLowerCase().endsWith(".png"))
      .sort();
    if (pngs.length === 0) {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: ENGINE,
        message: `hyperframes snapshot produced no PNG for scene ${plan.sceneId} at frame ${localFrame}.`,
        stderrLog: tailOf(res.stderr || res.stdout) || null,
      });
    }
    return join(snapDir, pngs[0]);
  }

  private async renderVideo(
    job: ValidatedMotionJob,
    kind: "preview" | "final",
    quality: string,
    preview: PreviewPlan | null
  ): Promise<ArtifactEvidence> {
    const startedAt = new Date().toISOString();
    const started = Date.now();
    const rt = this.runtime();
    const plans = this.planScenes(job, null);
    if (plans.length === 0) {
      throw new AdapterError({
        category: "MG_SCHEMA_INVALID",
        engine: ENGINE,
        message: `Job ${job.jobId} has no scenes the Hyperframes adapter can render.`,
      });
    }
    for (const plan of plans) {
      const assetProblems = this.assetFindings(job, plan);
      if (assetProblems.length > 0) {
        throw new AdapterError({
          category: "MG_SCHEMA_INVALID",
          engine: ENGINE,
          message: assetProblems[0].message,
          findings: assetProblems,
        });
      }
    }
    const canvasFps = job.manifest.canvas.fps;
    // MG-024: a preview renders at the plan's fps (the full authored
    // fps, or the labeled rough-layout rate) and may be spatially
    // scaled after the canonical render. The final render is
    // untouched: preview is null and every value below reduces to the
    // historical behavior.
    const fps = preview ? preview.fps : canvasFps;
    const variantSuffix =
      preview && !isIdentityPlan(preview) ? previewVariantSuffix(preview) : "";
    // MG-040: a final render follows the job's delivery profile. The
    // opaque default keeps the historical mp4 path exactly; an alpha
    // profile switches the CLI to its documented alpha format (mov
    // for ProRes 4444, webm for VP9 with alpha) and the artifact
    // extension with it. Previews are not delivery exports and stay
    // on the mp4 path regardless of profile.
    const exportProfile =
      kind === "final" && !preview ? EXPORT_PROFILES[job.manifest.delivery.video_profile] : null;
    const cliFormat = exportProfile
      ? exportProfile.id === "prores_4444_alpha"
        ? "mov"
        : exportProfile.id === "vp9_alpha"
          ? "webm"
          : null
      : null;
    const artifactExt = cliFormat ?? "mp4";
    const segments: string[] = [];
    const receipts: Array<Record<string, unknown>> = [];
    const projectHashes: string[] = [];
    let totalExpectedFrames = 0;
    for (const plan of plans) {
      const { project } = this.materialize(job, plan);
      projectHashes.push(hashProjectFiles(project));
      const expectedSceneFrames = preview
        ? rescaleFrames(plan.durationFrames, canvasFps, fps)
        : plan.durationFrames;
      totalExpectedFrames += expectedSceneFrames;
      const segmentPath = join(plan.outDir, `segment-${kind}.${artifactExt}`);
      mkdirSync(plan.outDir, { recursive: true });
      rmSync(segmentPath, { force: true });
      const args = [
        "render",
        plan.projectDir,
        "-o",
        segmentPath,
        "-f",
        String(fps),
        "-q",
        quality,
        "-w",
        "1",
        "--no-browser-gpu",
      ];
      if (cliFormat) args.push("--format", cliFormat);
      if (kind === "final") args.push("--strict");
      const res = await this.runCli(job.jobId, rt, args, plan.projectDir, this.timeoutFor(job.jobId, 1800000));
      if (res.exitCode !== 0 || !existsSync(segmentPath)) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: ENGINE,
          message:
            `hyperframes render failed for scene ${plan.sceneId} (exit ${res.exitCode}, ` +
            `output ${existsSync(segmentPath) ? "present" : "missing"}).`,
          stderrLog: tailOf(res.stderr || res.stdout) || null,
        });
      }
      const probe = await this.probeVideo(job.jobId, segmentPath);
      if (
        probe.width !== job.manifest.canvas.width ||
        probe.height !== job.manifest.canvas.height
      ) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: ENGINE,
          message:
            `Rendered segment for scene ${plan.sceneId} is ${probe.width}x${probe.height}, ` +
            `not the job canvas ${job.manifest.canvas.width}x${job.manifest.canvas.height}.`,
          stderrLog: tailOf(res.stderr) || null,
        });
      }
      if (probe.frames !== expectedSceneFrames) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: ENGINE,
          message:
            `Rendered segment for scene ${plan.sceneId} holds ${probe.frames} decoded frames, ` +
            `not the planned ${expectedSceneFrames} (Directive M01).`,
          stderrLog: tailOf(res.stderr) || null,
        });
      }
      if (preview && preview.scale < 1) {
        // MG-024 spatial scale. The pinned CLI's only scale mechanism
        // (--resolution) offers integer-multiple upscales from fixed
        // presets, never a sub-native render scale, so the preview is
        // derived from the engine's canonical frames at encode time:
        // same frames, same fps, same timing, lower spatial
        // resolution. The derivation is probed like any other output
        // before it may stand in for the segment.
        const scaledPath = join(plan.outDir, `segment-${kind}-scaled.mp4`);
        rmSync(scaledPath, { force: true });
        const scaleRes = await this.runProcess(
          job.jobId,
          "ffmpeg",
          [
            "-v", "error",
            "-i", segmentPath,
            "-vf", `scale=${preview.width}:${preview.height}:flags=lanczos`,
            "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-an",
            "-y", scaledPath,
          ],
          { cwd: plan.outDir, timeoutMs: this.timeoutFor(job.jobId, 600000) }
        );
        if (scaleRes.exitCode !== 0 || !existsSync(scaledPath)) {
          throw new AdapterError({
            category: "MG_RENDER_FAILED",
            engine: ENGINE,
            message:
              `Scaling the rendered segment for scene ${plan.sceneId} to ` +
              `${preview.width}x${preview.height} failed (exit ${scaleRes.exitCode}).`,
            stderrLog: tailOf(scaleRes.stderr) || null,
          });
        }
        const scaledProbe = await this.probeVideo(job.jobId, scaledPath);
        if (
          scaledProbe.width !== preview.width ||
          scaledProbe.height !== preview.height ||
          scaledProbe.frames !== expectedSceneFrames
        ) {
          throw new AdapterError({
            category: "MG_RENDER_FAILED",
            engine: ENGINE,
            message:
              `Scaled segment for scene ${plan.sceneId} probed as ${scaledProbe.width}x` +
              `${scaledProbe.height} with ${scaledProbe.frames} frames, not the planned ` +
              `${preview.width}x${preview.height} with ${expectedSceneFrames} frames.`,
          });
        }
        renameSync(scaledPath, segmentPath);
      }
      segments.push(segmentPath);
      receipts.push({
        sceneId: plan.sceneId,
        engine: ENGINE,
        engineVersion: rt.engineVersion,
        runtimeLockId: rt.runtimeLockId,
        renderingMode: renderingModeFromOutput(res.stdout + res.stderr),
        quality,
        fps,
        workers: 1,
        cliArgs: args.slice(1),
        exitCode: res.exitCode,
        durationMs: res.durationMs,
        segment: {
          path: relative(job.jobDir, segmentPath).split("\\").join("/"),
          sha256: sha256File(segmentPath),
          bytes: statSync(segmentPath).size,
          decodedFrames: probe.frames,
          width: probe.width,
          height: probe.height,
          codec: probe.codec,
        },
      });
    }
    const outName = variantSuffix ? `${kind}-${variantSuffix}.mp4` : `${kind}.${artifactExt}`;
    const outRel = join(OUTPUT_ROOT, outName);
    const outAbs = join(job.jobDir, outRel);
    mkdirSync(dirname(outAbs), { recursive: true });
    if (segments.length === 1) {
      renameSync(segments[0], outAbs);
    } else {
      const listPath = join(
        job.jobDir,
        OUTPUT_ROOT,
        variantSuffix ? `concat-${kind}-${variantSuffix}.txt` : `concat-${kind}.txt`
      );
      writeFileSync(
        listPath,
        segments.map((s) => `file '${s.replace(/'/g, "'\\''")}'`).join("\n") + "\n",
        "utf8"
      );
      const concat = await this.runProcess(
        job.jobId,
        "ffmpeg",
        ["-v", "error", "-f", "concat", "-safe", "0", "-i", listPath, "-c", "copy", "-y", outAbs],
        { cwd: job.jobDir, timeoutMs: this.timeoutFor(job.jobId, 600000) }
      );
      if (concat.exitCode !== 0 || !existsSync(outAbs)) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: ENGINE,
          message: `ffmpeg concat of scene segments failed (exit ${concat.exitCode}).`,
          stderrLog: tailOf(concat.stderr) || null,
        });
      }
      const probe = await this.probeVideo(job.jobId, outAbs);
      const expectedTotal = preview ? totalExpectedFrames : job.manifest.duration_frames;
      if (probe.frames !== expectedTotal) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: ENGINE,
          message:
            `Concatenated ${kind} holds ${probe.frames} decoded frames, not the job's ` +
            `planned ${expectedTotal} (Directive M01).`,
          stderrLog: tailOf(concat.stderr) || null,
        });
      }
    }
    // MG-024: build the preview review record from a probe of the
    // finished artifact, so the record states measured output.
    let previewRecord: PreviewReviewRecord | null = null;
    if (preview) {
      const artifactProbe = await this.probeVideo(job.jobId, outAbs);
      if (
        artifactProbe.width !== preview.width ||
        artifactProbe.height !== preview.height ||
        artifactProbe.frames !== totalExpectedFrames
      ) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: ENGINE,
          message:
            `Preview artifact probed as ${artifactProbe.width}x${artifactProbe.height} ` +
            `with ${artifactProbe.frames} frames, not the planned ${preview.width}x` +
            `${preview.height} with ${totalExpectedFrames} frames.`,
        });
      }
      previewRecord = {
        schemaVersion: "1.0",
        engine: ENGINE,
        jobId: job.jobId,
        kind: "preview",
        label: preview.label,
        roughLayoutOnly: preview.roughLayoutOnly,
        scale: preview.scale,
        scaleMethod: preview.scale === 1 ? "none" : "post_encode_scale",
        sourceHash: hashJobSourceInputs(job.jobDir, job.manifest),
        propsHash: sha256Hex(projectHashes.join("\n")),
        previewHash: sha256File(outAbs),
        final: {
          width: job.manifest.canvas.width,
          height: job.manifest.canvas.height,
          fps: canvasFps,
          durationFrames: job.manifest.duration_frames,
        },
        preview: {
          width: artifactProbe.width,
          height: artifactProbe.height,
          fps,
          durationFrames: artifactProbe.frames,
          durationSeconds: artifactProbe.frames / fps,
        },
        generatedAt: new Date().toISOString(),
      };
    }
    // MG-040: the packaging record for a final is built from
    // measurement of the finished artifact. buildExportRecord throws
    // (MG_QC_FAILED) rather than write a record the artifact
    // contradicts, so a final that lost its alpha channel fails here
    // instead of shipping with a transparent label.
    let exportRecord: ExportRecord | null = null;
    if (exportProfile) {
      const route = exportProfile.routes.hyperframes;
      exportRecord = buildExportRecord({
        profile: exportProfile,
        route: { engine: ENGINE, kind: route.kind, detail: route.detail },
        artifactAbsPath: outAbs,
        artifactLogicalPath: outRel.split("\\").join("/"),
      });
      if (exportRecord.stream.codec !== exportProfile.streamCodec) {
        throw new AdapterError({
          category: "MG_RENDER_FAILED",
          engine: ENGINE,
          message:
            `Rendered final ${outAbs} probed as codec ${exportRecord.stream.codec}, not the ` +
            `${exportProfile.streamCodec} the delivery profile ${exportProfile.id} requires.`,
        });
      }
      writeExportRecordSidecar(exportRecord, `${outAbs}.export-record.json`);
    }
    const receiptName = variantSuffix
      ? `render-receipt-${kind}-${variantSuffix}.json`
      : `render-receipt-${kind}.json`;
    const receiptPath = join(job.jobDir, OUTPUT_ROOT, receiptName);
    writeFileSync(
      receiptPath,
      JSON.stringify(
        {
          jobId: job.jobId,
          kind,
          engine: ENGINE,
          engineVersion: rt.engineVersion,
          runtimeLockId: rt.runtimeLockId,
          runtimeLockPath: rt.lockPath,
          platform: `${process.platform} ${process.arch}`,
          scenes: receipts,
          artifact: {
            path: outRel.split("\\").join("/"),
            sha256: sha256File(outAbs),
            bytes: statSync(outAbs).size,
          },
          ...(previewRecord ? { previewReview: previewRecord } : {}),
          ...(exportRecord ? { exportRecord } : {}),
          startedAt,
          finishedAt: new Date().toISOString(),
        },
        null,
        2
      ) + "\n",
      "utf8"
    );
    return {
      engine: ENGINE,
      runtime: this.identity(),
      jobId: job.jobId,
      kind,
      artifacts: [{ path: outRel.split("\\").join("/"), sha256: sha256File(outAbs) }],
      outputPaths: [outRel.split("\\").join("/")],
      exitCode: 0,
      stderrLog: null,
      startedAt,
      finishedAt: new Date().toISOString(),
      durationMs: Date.now() - started,
      ...(previewRecord ? { previewReview: previewRecord } : {}),
      ...(exportRecord ? { exportRecord } : {}),
    };
  }

  /** ffprobe a rendered video: decoded frame count, dimensions, codec. */
  private async probeVideo(
    jobId: string,
    path: string
  ): Promise<{ frames: number; width: number; height: number; codec: string }> {
    const res = await this.runProcess(
      jobId,
      "ffprobe",
      [
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,codec_name,nb_read_frames",
        "-of",
        "json",
        path,
      ],
      { cwd: dirname(path), timeoutMs: 300000 }
    );
    if (res.exitCode !== 0) {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: ENGINE,
        message: `ffprobe failed on rendered output ${path} (exit ${res.exitCode}).`,
        stderrLog: tailOf(res.stderr) || null,
      });
    }
    const parsed = parseJsonObject(res.stdout) as {
      streams?: Array<{ width?: number; height?: number; codec_name?: string; nb_read_frames?: string }>;
    } | null;
    const stream = parsed?.streams?.[0];
    if (!stream || typeof stream.width !== "number" || typeof stream.height !== "number") {
      throw new AdapterError({
        category: "MG_RENDER_FAILED",
        engine: ENGINE,
        message: `ffprobe returned no video stream for ${path}.`,
      });
    }
    return {
      frames: parseInt(stream.nb_read_frames ?? "0", 10),
      width: stream.width,
      height: stream.height,
      codec: stream.codec_name ?? "unknown",
    };
  }
}

// -----------------------------------------------------------------------
// CLI report parsing helpers
// -----------------------------------------------------------------------

function parseJsonObject(text: string): Record<string, unknown> | null {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    return JSON.parse(text.slice(start, end + 1)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function compositionIdsFromJson(text: string): string[] {
  const parsed = parseJsonObject(text) as { compositions?: unknown } | null;
  const ids: string[] = [];
  const list = (parsed?.compositions ?? null) as Array<Record<string, unknown>> | null;
  if (Array.isArray(list)) {
    for (const entry of list) {
      const id = entry.id ?? entry.compositionId ?? entry.name;
      if (typeof id === "string") ids.push(id);
    }
  }
  // Fallback: the JSON may be a bare array or carry ids elsewhere; scan
  // for "id" fields as a last resort rather than failing the gate.
  if (ids.length === 0) {
    for (const m of text.matchAll(/"id"\s*:\s*"([^"]+)"/g)) ids.push(m[1]);
  }
  return ids;
}

/** Count how many checks a hyperframes check report actually evaluated.
 * The report is agent-readable JSON; count issue entries plus the
 * per-category pass markers. Zero means the audit evaluated nothing. */
function countEvaluatedChecks(text: string): number {
  const parsed = parseJsonObject(text) as Record<string, unknown> | null;
  if (!parsed) {
    // Non-JSON output: count explicit PASS/checked markers, else zero.
    return (text.match(/\b(pass|passed|checked|ok)\b/gi) ?? []).length;
  }
  let count = 0;
  const visit = (value: unknown, key: string): void => {
    if (Array.isArray(value)) {
      if (/issues|findings|checks|results|samples/i.test(key)) count += value.length;
      for (const v of value) visit(v, key);
      return;
    }
    if (value && typeof value === "object") {
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        if (typeof v === "number" && /count|total|samples|evaluated/i.test(k)) count += v;
        visit(v, k);
      }
    }
  };
  visit(parsed, "");
  return count;
}

function firstLintMessages(text: string): string {
  const parsed = parseJsonObject(text) as { findings?: Array<{ message?: string }> } | null;
  const messages = (parsed?.findings ?? [])
    .map((f) => f.message)
    .filter((m): m is string => typeof m === "string")
    .slice(0, 3);
  return messages.length > 0 ? messages.join("; ") : text.slice(0, 300);
}

/** The CLI prints its rendering mode in the render log; capture it when
 * present and otherwise record the local mode this adapter always uses
 * (it never passes --docker). */
function renderingModeFromOutput(text: string): string {
  if (/docker/i.test(text)) return "docker";
  if (/local/i.test(text)) return "local";
  return "local";
}

export function createHyperframesAdapter(opts?: { runtimeRoot?: string }): HyperframesAdapter {
  return new HyperframesAdapter(opts);
}
