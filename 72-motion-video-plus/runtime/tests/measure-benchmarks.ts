// MG-045 production performance benchmark harness.
//
// What this measures, and what it refuses to claim:
//
// - It runs representative production work through the SHIPPED
//   pipeline (the production Remotion and Hyperframes adapters, the
//   MG-021 timeline compiler, the MG-027 cache session, the MG-031
//   critique bundle builder as the QC stage) and records per-stage
//   timings, peak memory, peak disk, output fidelity, and failures.
//   It adds no render path of its own.
// - Every number it emits is bound to its conditions: machine
//   metadata, runtime lock, scene, canvas, fps, duration, and
//   repetition are recorded inside every run record. A figure without
//   those conditions is not produced.
// - A faster run whose output differs from the reference output is
//   reported as DEGRADED with the measured difference, and is
//   excluded from every speed ranking. Speed never outranks fidelity.
// - A run that fails mid-stage is recorded as failed, with the stage
//   named, and counted in the failure rate. Failures are never
//   silently dropped, and the deliberate sabotage cell is labeled
//   deliberate wherever it is counted.
// - Cache savings are claimed stage by stage: only stages the cache
//   actually serves show savings. Stages it does not touch (input
//   hashing, timeline compile, QC) show zero savings and their real
//   repeated cost, measured.
// - Nothing here describes multi-machine or parallel-worker speedups.
//   Cells run sequentially on this one machine; the capacity figures
//   in the report are inputs to the MG-028 budget, measured on this
//   machine, not new enforced profiles.
//
// Roles (one file, following the measure-resources.ts convention):
// - Parent (default): spawns one child per benchmark cell, samples
//   the child's process tree every 50 ms via /proc (peak RSS, the
//   MG-028 method) and the cell scratch directory every 250 ms (peak
//   disk), assembles the per-repetition run records, then runs the
//   fidelity / degraded / failure analysis and writes analysis.json.
// - Child (--role cell): stages one cell's job, runs the pipeline
//   stages in-process, and writes its run record incrementally, so a
//   mid-stage failure still leaves a complete record of what ran.
// - Cache child (--role cache): runs the MG-027 cache program
//   (cold / warm / partial executions over two real C05 jobs) and
//   writes the cache record.
// - --self-check: exercises the analysis over synthetic records (a
//   normal run, a faster-but-degraded run, a failed run) and asserts
//   the honesty rules: degraded is flagged and excluded from ranking,
//   failures are counted, ranking picks the fastest NON-degraded run.
//
// Precondition: the shared runtime provisioned in THIS checkout
// (shared-utils/motion-render-runtime/provision.sh; the benchmark
// resolves it by the adapters' own walk-up discovery, so the numbers
// describe the same resolution path production uses).
//
// Usage:
//   node dist/tests/measure-benchmarks.js [--reps 2] [--cells a,b]
//       [--out-dir <dir>] [--write-evidence]
//   node dist/tests/measure-benchmarks.js --self-check

import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { loadavg } from "node:os";
import { basename, join, resolve } from "node:path";
import { createRemotionAdapter } from "../src/adapters/remotion";
import { HyperframesAdapter } from "../src/adapters/hyperframes";
import { loadValidatedJob } from "../src/adapters/dispatch";
import type {
  ApprovedMotionJob,
  ArtifactEvidence,
  MotionRendererAdapter,
  RuntimeEvidence,
  ValidatedMotionJob,
} from "../src/adapters/types";
import type { Approval, Manifest } from "../src/validation/generated-types";
import {
  CachedRenderSession,
  deriveSceneCacheKey,
  hashCanonical,
  type SceneKeyInputs,
  type SceneRenderContext,
  type SceneWorkUnit,
} from "../src/cache";
import { compileTimeline, type TimelineCompileInput } from "../src/timeline";
import { loadC05Job } from "../src/remotion/job-props";
import { probeVideoFile, readPngDimensions } from "../src/remotion/decode";
import {
  compareDecodedPixels,
  decodePngPixels,
  EXACT_PIXELS,
  toleranceVerdict,
} from "../src/determinism/pixels";
import { measureMachineCapacity } from "../src/resources/preflight";
import type { MachineCapacity } from "../src/resources/types";

// ---------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------

const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const FIXTURES_ROOT = join(SKILL_DIR, "tests", "fixtures");
const EVIDENCE_DIR = join(SKILL_DIR, "tests", "evidence", "mg045");
const SCRATCH_ROOT = join(REPO_ROOT, ".scratch", "mg045-benchmarks");
const RUNTIME_ROOT = join(REPO_ROOT, "shared-utils", "motion-render-runtime");
const RUNTIME_STATE = join(RUNTIME_ROOT, ".runtime");

function readJson(path: string): Record<string, any> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, any>;
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function runtimeLockInfo(): {
  lockId: string | null;
  remotion: string | null;
  hyperframes: string | null;
  lockTimestamp: string | null;
} {
  try {
    const lock = readJson(join(RUNTIME_STATE, "runtime-lock.json"));
    const current = join(RUNTIME_STATE, "current");
    let lockId: string | null = null;
    try {
      const { realpathSync } = require("node:fs") as typeof import("node:fs");
      lockId = basename(realpathSync(current));
    } catch {
      lockId = null;
    }
    return {
      lockId,
      remotion: (lock.packages?.remotion as string) ?? null,
      hyperframes: (lock.packages?.hyperframes as string) ?? null,
      lockTimestamp: (lock.timestamp as string) ?? null,
    };
  } catch {
    return { lockId: null, remotion: null, hyperframes: null, lockTimestamp: null };
  }
}

function machineRecord(): MachineCapacity & { loadAvg: number[] } {
  return { ...measureMachineCapacity(), loadAvg: loadavg() };
}

// ---------------------------------------------------------------------
// Records
// ---------------------------------------------------------------------

interface StageRecord {
  name: string;
  startedAt: number;
  endedAt: number;
  ms: number;
  ok: boolean;
  detail: Record<string, unknown>;
  error?: string;
}

interface ArtifactRecord {
  path: string;
  bytes: number;
  probe: Record<string, unknown> | null;
}

interface CellRunRecord {
  kind: "cell";
  item: "MG-045";
  cellId: string;
  sceneKind: "chart" | "image" | "mixed" | "degraded" | "sabotage";
  engine: string;
  rep: number;
  deliberate: boolean;
  startedAtIso: string;
  finishedAtIso: string;
  machine: MachineCapacity & { loadAvg: number[] };
  runtime: ReturnType<typeof runtimeLockInfo>;
  scene: {
    width: number;
    height: number;
    fps: number;
    durationFrames: number;
    scenes: Array<{ id: string; durationFrames: number }>;
  };
  status: "passed" | "failed";
  failedStage: string | null;
  error: string | null;
  stages: StageRecord[];
  artifacts: {
    stills: ArtifactRecord[];
    preview: ArtifactRecord | null;
    final: ArtifactRecord | null;
    encode: ArtifactRecord | null;
  };
  qc: { verdict: string | null; coveragePath: string | null } | null;
  wallMs: number;
  resources?: {
    peakRssMB: number;
    peakProcesses: number;
    peakBrowserMains: number;
    peakDiskBytes: number;
    finalDiskBytes: number;
    phasePeaks: Record<
      string,
      { peakRssMB: number; peakBrowserMains: number; peakProcesses: number; wallMs: number }
    >;
  };
}

/** Run one stage, recording wall time and failure as data. A stage
 * failure is recorded and rethrown as a StageFailure so the cell can
 * stop, leaving the record complete up to the failure. */
class StageFailure extends Error {
  readonly stage: string;
  constructor(stage: string, message: string) {
    super(message);
    this.stage = stage;
  }
}

async function runStage(
  stages: StageRecord[],
  name: string,
  fn: () => Promise<Record<string, unknown>>
): Promise<Record<string, unknown>> {
  const startedAt = Date.now();
  const t0 = performance.now();
  try {
    const detail = await fn();
    stages.push({
      name,
      startedAt,
      endedAt: Date.now(),
      ms: Math.round(performance.now() - t0),
      ok: true,
      detail,
    });
    return detail;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    stages.push({
      name,
      startedAt,
      endedAt: Date.now(),
      ms: Math.round(performance.now() - t0),
      ok: false,
      detail: {},
      error: message.slice(0, 2000),
    });
    throw new StageFailure(name, message);
  }
}

/** A stage that is cheap and synchronous-ish but must still be
 * recorded as data when it does not apply: used only for stages the
 * cell definition skips, so the record states the skip rather than
 * omitting the stage silently. */
function skipStage(stages: StageRecord[], name: string, reason: string): void {
  const now = Date.now();
  stages.push({
    name,
    startedAt: now,
    endedAt: now,
    ms: 0,
    ok: true,
    detail: { skipped: reason },
  });
}

// ---------------------------------------------------------------------
// Process-tree and disk sampling (parent side; the MG-028 method)
// ---------------------------------------------------------------------

interface ProcInfo {
  pid: number;
  ppid: number;
  rssKB: number;
  cmdline: string;
}

function readProcTable(): ProcInfo[] {
  const out: ProcInfo[] = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    try {
      const stat = readFileSync(`/proc/${name}/stat`, "utf8");
      const rest = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
      const status = readFileSync(`/proc/${name}/status`, "utf8");
      const m = status.match(/VmRSS:\s+(\d+) kB/);
      out.push({
        pid: Number(name),
        ppid: Number(rest[1]),
        rssKB: m ? Number(m[1]) : 0,
        cmdline: readFileSync(`/proc/${name}/cmdline`, "utf8").replace(/\0/g, " "),
      });
    } catch {
      // The process exited mid-scan; it contributes nothing.
    }
  }
  return out;
}

interface TreeSample {
  rssMB: number;
  processes: number;
  browserMains: number;
}

function sampleTree(rootPid: number): TreeSample {
  const table = readProcTable();
  const byPid = new Map(table.map((p) => [p.pid, p]));
  const childrenOf = new Map<number, number[]>();
  for (const p of table) {
    const arr = childrenOf.get(p.ppid) ?? [];
    arr.push(p.pid);
    childrenOf.set(p.ppid, arr);
  }
  const members = new Set<number>();
  const stack = [rootPid];
  while (stack.length > 0) {
    const pid = stack.pop() as number;
    if (members.has(pid)) continue;
    members.add(pid);
    for (const c of childrenOf.get(pid) ?? []) stack.push(c);
  }
  let rssKB = 0;
  let browserMains = 0;
  for (const pid of members) {
    const p = byPid.get(pid);
    if (!p) continue;
    rssKB += p.rssKB;
    if (
      (p.cmdline.includes("chrome-headless-shell") || p.cmdline.includes("chrome")) &&
      !p.cmdline.includes("--type=")
    ) {
      browserMains += 1;
    }
  }
  return { rssMB: rssKB / 1024, processes: members.size, browserMains };
}

function dirBytes(dir: string): number {
  if (!existsSync(dir)) return 0;
  let total = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) total += dirBytes(p);
    else {
      try {
        total += statSync(p).size;
      } catch {
        // Vanished mid-walk.
      }
    }
  }
  return total;
}

interface SampledRun {
  exitCode: number | null;
  timedOut: boolean;
  wallMs: number;
  peak: TreeSample;
  samples: Array<{ t: number } & TreeSample>;
  peakDiskBytes: number;
  finalDiskBytes: number;
  stdoutTail: string;
  stderrTail: string;
}

const CHILD_TIMEOUT_MS = 25 * 60_000;

function runSampledChild(
  args: string[],
  env: NodeJS.ProcessEnv,
  diskDir: string
): Promise<SampledRun> {
  return new Promise((resolvePromise) => {
    const started = Date.now();
    const child = spawn(process.execPath, args, { env, shell: false });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const peak: TreeSample = { rssMB: 0, processes: 0, browserMains: 0 };
    const samples: Array<{ t: number } & TreeSample> = [];
    let peakDiskBytes = 0;
    const timer = setInterval(() => {
      if (!child.pid) return;
      const s = sampleTree(child.pid);
      samples.push({ t: Date.now(), ...s });
      peak.rssMB = Math.max(peak.rssMB, s.rssMB);
      peak.processes = Math.max(peak.processes, s.processes);
      peak.browserMains = Math.max(peak.browserMains, s.browserMains);
    }, 50);
    const diskTimer = setInterval(() => {
      peakDiskBytes = Math.max(peakDiskBytes, dirBytes(diskDir));
    }, 250);
    const killer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, CHILD_TIMEOUT_MS);
    child.stdout.on("data", (d: Buffer) => {
      stdout = (stdout + d.toString("utf8")).slice(-4000);
    });
    child.stderr.on("data", (d: Buffer) => {
      stderr = (stderr + d.toString("utf8")).slice(-4000);
    });
    child.on("error", () => undefined);
    child.on("close", (code) => {
      clearInterval(timer);
      clearInterval(diskTimer);
      clearTimeout(killer);
      peakDiskBytes = Math.max(peakDiskBytes, dirBytes(diskDir));
      resolvePromise({
        exitCode: code,
        timedOut,
        wallMs: Date.now() - started,
        peak,
        samples,
        peakDiskBytes,
        finalDiskBytes: dirBytes(diskDir),
        stdoutTail: stdout,
        stderrTail: stderr,
      });
    });
  });
}

// ---------------------------------------------------------------------
// Cell definitions and job staging (child side)
// ---------------------------------------------------------------------

const PALETTE = { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" };

interface CellDef {
  cellId: string;
  sceneKind: CellRunRecord["sceneKind"];
  engine: "remotion" | "hyperframes";
  deliberate: boolean;
  /** Frames for the two still stages. */
  stillFrames: [number, number];
  /** Frames extracted for cross-repetition fidelity comparison. */
  fidelityFrames: number[];
  durationFrames: number;
  scenes: Array<{ id: string; durationFrames: number }>;
}

const CELLS: CellDef[] = [
  {
    cellId: "chart-remotion",
    sceneKind: "chart",
    engine: "remotion",
    deliberate: false,
    stillFrames: [75, 45],
    fidelityFrames: [0, 45, 75, 179],
    durationFrames: 180,
    scenes: [{ id: "bar-01", durationFrames: 180 }],
  },
  {
    cellId: "chart-hyperframes",
    sceneKind: "chart",
    engine: "hyperframes",
    deliberate: false,
    stillFrames: [75, 45],
    fidelityFrames: [0, 45, 75, 179],
    durationFrames: 180,
    scenes: [{ id: "bar-01", durationFrames: 180 }],
  },
  {
    cellId: "image-hyperframes",
    sceneKind: "image",
    engine: "hyperframes",
    deliberate: false,
    stillFrames: [60, 90],
    fidelityFrames: [0, 60, 90, 149],
    durationFrames: 150,
    scenes: [{ id: "reveal-01", durationFrames: 150 }],
  },
  {
    cellId: "mixed-hyperframes",
    sceneKind: "mixed",
    engine: "hyperframes",
    deliberate: false,
    stillFrames: [75, 240],
    fidelityFrames: [0, 75, 240, 329],
    durationFrames: 330,
    scenes: [
      { id: "bar-01", durationFrames: 180 },
      { id: "reveal-01", durationFrames: 150 },
    ],
  },
  {
    cellId: "degraded-chart-remotion",
    sceneKind: "degraded",
    engine: "remotion",
    deliberate: true,
    stillFrames: [75, 45],
    fidelityFrames: [45],
    durationFrames: 180,
    scenes: [{ id: "bar-01", durationFrames: 180 }],
  },
  {
    cellId: "sabotage-chart-remotion",
    sceneKind: "sabotage",
    engine: "remotion",
    deliberate: true,
    stillFrames: [75, 45],
    fidelityFrames: [],
    durationFrames: 180,
    scenes: [{ id: "bar-01", durationFrames: 180 }],
  },
];

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg045-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "mg045-benchmark",
    artifact_refs: [],
    actor_id: "mg045-benchmark-harness",
    source_event_ref: null,
    authority_status: "not_verified",
  } as Approval;
}

/** The C01 image-reveal scene spec, following the MG-005 reference
 * suite pattern (run-hyperframes.ts buildRevealJob), with the
 * reference-suite image-led asset (the pass-image-led fixture's
 * mentor-desk illustration, 1200x1000) as the subject. The subject
 * box is aspect-matched to the asset (828x690 = 1.2 = 1200/1000). */
function revealSpec(assetFileName: string, assetAbsPath: string): Record<string, unknown> {
  return {
    schema_version: "mg005-1",
    id: "reveal-01",
    component_id: "C01",
    component_version: "1.0.0",
    engine: "hyperframes",
    duration_frames: 150,
    asset_file: `assets/${assetFileName}`,
    asset_sha256: sha256File(assetAbsPath),
    font_ref: "font-fixture-sans",
    canvas: { width: 1920, height: 1080 },
    design: { colors: PALETTE },
    subject: {
      id: "mentor-figure",
      // Box top 180 clears the one-line headline zone; the caption
      // (one line at 40 px, top = box bottom + 28 = 898) ends well
      // above the fixture label zone (top about 962). The MG-005
      // geometry passes the same audit with a wider box; this
      // narrower aspect-matched box needs the shorter caption, which
      // the harness's first smoke run established empirically.
      box: { x: 546, y: 180, width: 828, height: 690 },
      measure_color: PALETTE.accent,
    },
    copy: {
      headline: "Inside every delivery: the work itself",
      caption: "A mentor at a desk, revealed in full.",
      fixture_label: "ENGINEERING FIXTURE - ILLUSTRATIVE OBJECT",
    },
    headline_px: 84,
    caption_px: 40,
    motion: { kind: "mask_reveal", start_frame: 30, end_frame_exclusive: 90, hold_to_frame_exclusive: 150 },
    semantic_motion_assertions: [
      { id: "reveal-initial", kind: "subject_reveal", frame: 0, min_fraction: 0, max_fraction: 0.02 },
      { id: "reveal-proof", kind: "subject_reveal", frame: 60, min_fraction: 0.4, max_fraction: 0.85 },
      { id: "reveal-final", kind: "subject_reveal", frame: 149, min_fraction: 0.97, max_fraction: 1 },
    ],
  };
}

function writeJson(path: string, value: unknown): void {
  writeFileSync(path, JSON.stringify(value, null, 2) + "\n", "utf8");
}

/** Stage the C05 chart job (copy of the Section 16 fixture), retargeted
 * to Hyperframes when the cell's engine is Hyperframes: the exact
 * retarget the MG-005/MG-028 measurements use. */
function stageChartJob(cellDir: string, engine: "remotion" | "hyperframes"): string {
  const jobDir = join(cellDir, "job");
  rmSync(jobDir, { recursive: true, force: true });
  cpSync(join(FIXTURES_ROOT, "modes", "powerpoint_graphic"), jobDir, { recursive: true });
  if (engine === "hyperframes") {
    const scenePath = join(jobDir, "scenes", "bar-01.json");
    const scene = readJson(scenePath);
    scene.engine = "hyperframes";
    writeJson(scenePath, scene);
    const manifestPath = join(jobDir, "manifest.json");
    const manifest = readJson(manifestPath);
    manifest.rendering.default_engine = "hyperframes";
    writeJson(manifestPath, manifest);
  }
  return jobDir;
}

function baseManifest(jobId: string, durationFrames: number): Record<string, unknown> {
  return {
    schema_version: "2.0",
    job_id: jobId,
    company_id: "fixture-company",
    execution_context: "fixture",
    parent: null,
    mode: "standalone_video",
    content_scope: "insert",
    canvas: { width: 1920, height: 1080, fps: 30 },
    duration_frames: durationFrames,
    authoring: { selection: "inherit_config", provider: null, model: null, harness: null },
    rendering: { default_engine: "hyperframes", allow_legacy_fallback: false, runtime_lock: "runtime-lock.json" },
    storyboard: "storyboard.json",
    assets: "assets.json",
    design: "design.json",
    timeline: "timeline.json",
    audio: { mode: "none", parent_audio_ref: null, create_voiceover: false, create_music: false, source_assets: [] },
    approval_policy: "fixture_only",
    variants: [],
    scenes: [] as Array<{ id: string; spec: string }>,
    delivery: {
      video_profile: "h264_opaque",
      poster_frame: 0,
      placement: "full_frame",
      playback: { start: "automatic", repeat: "once", end: "hold_final" },
      required: ["mp4", "poster", "source_package", "placement_metadata"],
    },
  };
}

function writeTimeline(
  jobDir: string,
  jobId: string,
  scenes: Array<{ id: string; start: number; end: number }>
): void {
  writeJson(join(jobDir, "timeline.json"), {
    schema_version: "2.0",
    job_id: jobId,
    fps: 30,
    total_frames: scenes.length > 0 ? scenes[scenes.length - 1].end : 0,
    scenes: scenes.map((s) => ({
      id: s.id,
      start_frame: s.start,
      end_frame_exclusive: s.end,
      source_start_frame: 0,
      transition_in_frames: 0,
      transition_out_frames: 0,
    })),
    events: [],
    parent_slot: null,
    audio_owner: "none",
  });
}

const MENTOR_ASSET = join(
  FIXTURES_ROOT,
  "style-frames",
  "pass-image-led",
  "media",
  "mentor-desk.png"
);

/** Stage the image-led job: a job shell in the MG-005 suite pattern
 * whose one scene is the C01 mask reveal over the reference-suite
 * image asset. */
function stageImageJob(cellDir: string): string {
  const jobDir = join(cellDir, "job");
  rmSync(jobDir, { recursive: true, force: true });
  mkdirSync(join(jobDir, "assets"), { recursive: true });
  mkdirSync(join(jobDir, "scenes"), { recursive: true });
  const assetName = "mentor-desk.png";
  cpSync(MENTOR_ASSET, join(jobDir, "assets", assetName));
  writeJson(join(jobDir, "scenes", "reveal-01.json"), revealSpec(assetName, join(jobDir, "assets", assetName)));
  const manifest = baseManifest("mg045-image-led", 150);
  manifest.scenes = [{ id: "reveal-01", spec: "scenes/reveal-01.json" }];
  writeJson(join(jobDir, "manifest.json"), manifest);
  writeTimeline(jobDir, "mg045-image-led", [{ id: "reveal-01", start: 0, end: 150 }]);
  return jobDir;
}

/** Stage the mixed-media job: the C05 chart fixture retargeted to
 * Hyperframes, plus the C01 reveal scene and its image asset, as one
 * two-scene 330-frame program. */
function stageMixedJob(cellDir: string): string {
  const jobDir = stageChartJob(cellDir, "hyperframes");
  const assetName = "mentor-desk.png";
  cpSync(MENTOR_ASSET, join(jobDir, "assets", assetName));
  writeJson(join(jobDir, "scenes", "reveal-01.json"), revealSpec(assetName, join(jobDir, "assets", assetName)));
  const manifest = readJson(join(jobDir, "manifest.json"));
  manifest.job_id = "mg045-mixed-program";
  manifest.mode = "standalone_video";
  manifest.content_scope = "full_program";
  manifest.duration_frames = 330;
  manifest.scenes = [
    { id: "bar-01", spec: "scenes/bar-01.json" },
    { id: "reveal-01", spec: "scenes/reveal-01.json" },
  ];
  writeJson(join(jobDir, "manifest.json"), manifest);
  // The chart fixture's timeline keeps its bar-01 placement and
  // events; the reveal scene is placed after it.
  const timeline = readJson(join(jobDir, "timeline.json"));
  timeline.job_id = "mg045-mixed-program";
  timeline.total_frames = 330;
  timeline.scenes = [
    {
      id: "bar-01",
      start_frame: 0,
      end_frame_exclusive: 180,
      source_start_frame: 0,
      transition_in_frames: 0,
      transition_out_frames: 0,
    },
    {
      id: "reveal-01",
      start_frame: 180,
      end_frame_exclusive: 330,
      source_start_frame: 0,
      transition_in_frames: 0,
      transition_out_frames: 0,
    },
  ];
  writeJson(join(jobDir, "timeline.json"), timeline);
  // Storyboard gains an image beat for the reveal scene.
  const storyboard = readJson(join(jobDir, "storyboard.json"));
  (storyboard.beats as Array<Record<string, unknown>>).push({
    id: "beat-mentor",
    scene_id: "reveal-01",
    job: "Show the mentor the chart describes",
    viewer_question: "Who does this work?",
    intended_understanding: "A person does this work; the reveal uncovers her in full.",
    visual_verb: "reveal",
    subject_ids: ["mentor-figure"],
    representation: "image",
    explanatory: true,
    initial_state: "The subject is covered.",
    transformation: "A mask lifts across frames 210 to 270 of the program.",
    proof_state: "The subject is fully visible.",
    final_state: "The subject holds still for reading.",
    asset_ids: ["mentor-desk-illustration"],
    data_ids: [],
    essential_text: ["Inside every delivery: the work itself"],
    proof_frames: [180, 240, 270, 329],
    typography_only_exception: null,
  });
  writeJson(join(jobDir, "storyboard.json"), storyboard);
  return jobDir;
}

function stageJobForCell(def: CellDef, cellDir: string): string {
  switch (def.cellId) {
    case "chart-remotion":
    case "degraded-chart-remotion":
      return stageChartJob(cellDir, "remotion");
    case "sabotage-chart-remotion": {
      const jobDir = stageChartJob(cellDir, "remotion");
      // The sabotage: the scene's declared dataset is removed, so a
      // later pipeline stage must fail. Which stage notices first is
      // part of what the record shows.
      rmSync(join(jobDir, "data", "bars.json"), { force: true });
      return jobDir;
    }
    case "chart-hyperframes":
      return stageChartJob(cellDir, "hyperframes");
    case "image-hyperframes":
      return stageImageJob(cellDir);
    case "mixed-hyperframes":
      return stageMixedJob(cellDir);
    default:
      throw new Error(`unknown cell ${def.cellId}`);
  }
}

/** Build the ValidatedMotionJob for a staged job. Remotion chart jobs
 * go through the contracts layer (loadValidatedJob) inside the
 * compile stage, so this is only the direct-construction path the
 * MG-005 suite uses for Hyperframes jobs (whose C01 scene specs the
 * contracts scene shapes do not yet dispatch; that divergence is
 * documented MG-025 state, recorded in the run record). */
function directJob(jobDir: string): ValidatedMotionJob {
  const manifest = readJson(join(jobDir, "manifest.json")) as unknown as Manifest;
  return { jobDir, jobId: manifest.job_id, manifest };
}

// ---------------------------------------------------------------------
// Asset preparation: the shipped input collection the cache keys on
// ---------------------------------------------------------------------

/** Collect and hash every input that can change a scene's pixels,
 * using the shipped derivation helpers (the same collection the
 * MG-027 cache session keys reuse on). Returns the derived scene
 * cache keys and the number of bytes hashed. This is the asset
 * preparation work a production orchestrator performs before any
 * render: nothing here is benchmark-only machinery. */
function collectKeyInputs(
  job: ValidatedMotionJob,
  timingHash: string,
  runtime: { adapterVersion: string; lockId: string; compilerVersion: string }
): { keys: Record<string, string>; bytesHashed: number; classes: Record<string, string[]> } {
  const jobDir = job.jobDir;
  const manifest = job.manifest;
  const keys: Record<string, string> = {};
  const classes: Record<string, string[]> = {};
  let bytesHashed = 0;
  const hashCounted = (path: string): string => {
    bytesHashed += statSync(path).size;
    return sha256File(path);
  };
  for (const entry of manifest.scenes) {
    const specPath = join(jobDir, entry.spec);
    const spec = readJson(specPath);
    const sceneSourceHash = hashCounted(specPath);
    let propsHash: string;
    let dataHashes: Record<string, string> = {};
    let fontHashes: Record<string, string> = {};
    if (spec.component_id === "C05" && spec.engine === "remotion") {
      const loaded = loadC05Job(job);
      propsHash = hashCanonical(loaded.props);
      dataHashes = { [spec.data_path as string]: hashCounted(join(jobDir, spec.data_path as string)) };
      fontHashes = {
        [loaded.font.requirementId]: hashCanonical(
          loaded.font.files.map((f) => [f.weight, f.sha256])
        ),
      };
      classes[entry.id] = ["scene_source", "props", "fonts", "data", "timing", "geometry", "export", "versions", "runtime"];
    } else if (spec.component_id === "C05") {
      // A C05 scene retargeted to Hyperframes: the shipped props
      // loader (loadC05Job) refuses non-Remotion routing by design,
      // and the Hyperframes adapter consumes the scene document
      // itself as its props payload. The key therefore hashes the
      // canonical scene document plus its declared data file; the
      // class list names this basis so the two engines' keys are
      // never presented as derived from identical inputs.
      propsHash = hashCanonical(spec);
      dataHashes = { [spec.data_path as string]: hashCounted(join(jobDir, spec.data_path as string)) };
      fontHashes = {};
      classes[entry.id] = ["scene_source", "props (scene document, hyperframes basis)", "data", "timing", "geometry", "export", "versions", "runtime"];
    } else {
      // C01 scene: the spec is the props payload; its declared asset
      // is hashed as the scene's asset input.
      propsHash = hashCanonical(spec);
      const assetRel = spec.asset_file as string;
      dataHashes = {};
      fontHashes = { [spec.font_ref as string]: hashCanonical(spec.font_ref) };
      const assetHashes = { [assetRel]: hashCounted(join(jobDir, assetRel)) };
      const inputs: SceneKeyInputs = {
        sceneId: entry.id,
        engine: "hyperframes",
        sceneSourceHash,
        propsHash,
        assetHashes,
        fontHashes,
        dataHashes,
        timingHash,
        width: manifest.canvas.width,
        height: manifest.canvas.height,
        fps: manifest.canvas.fps,
        exportSettings: { container: "mp4", videoProfile: manifest.delivery.video_profile },
        adapterVersion: runtime.adapterVersion,
        compilerVersion: runtime.compilerVersion,
        runtimeLockId: runtime.lockId,
      };
      keys[entry.id] = deriveSceneCacheKey(inputs).key;
      classes[entry.id] = ["scene_source", "props", "assets", "fonts", "timing", "geometry", "export", "versions", "runtime"];
      continue;
    }
    const inputs: SceneKeyInputs = {
      sceneId: entry.id,
      engine: manifest.rendering.default_engine,
      sceneSourceHash,
      propsHash,
      assetHashes: {},
      fontHashes,
      dataHashes,
      timingHash,
      width: manifest.canvas.width,
      height: manifest.canvas.height,
      fps: manifest.canvas.fps,
      exportSettings: { container: "mp4", videoProfile: manifest.delivery.video_profile },
      adapterVersion: runtime.adapterVersion,
      compilerVersion: runtime.compilerVersion,
      runtimeLockId: runtime.lockId,
    };
    keys[entry.id] = deriveSceneCacheKey(inputs).key;
  }
  return { keys, bytesHashed, classes };
}

// ---------------------------------------------------------------------
// Cell child
// ---------------------------------------------------------------------

function probeFactsRecord(path: string): Record<string, unknown> {
  try {
    const facts = probeVideoFile(path);
    return { ...facts } as Record<string, unknown>;
  } catch (err) {
    return { probeError: err instanceof Error ? err.message : String(err) };
  }
}

function artifactRecord(path: string, probe: boolean): ArtifactRecord {
  let bytes = 0;
  try {
    bytes = statSync(path).size;
  } catch {
    bytes = 0;
  }
  return { path, bytes, probe: probe ? probeFactsRecord(path) : null };
}

function bundleEntries(): string[] {
  const dir = join(RUNTIME_STATE, "mg006-bundles");
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

interface CellChildArgs {
  cellId: string;
  rep: number;
  cellDir: string;
  resultPath: string;
}

async function runCellChild(args: CellChildArgs): Promise<number> {
  const def = CELLS.find((c) => c.cellId === args.cellId);
  if (!def) throw new Error(`unknown cell ${args.cellId}`);
  const cellDir = args.cellDir;
  rmSync(cellDir, { recursive: true, force: true });
  mkdirSync(join(cellDir, "tmp"), { recursive: true });
  const startedAt = Date.now();
  const record: CellRunRecord = {
    kind: "cell",
    item: "MG-045",
    cellId: def.cellId,
    sceneKind: def.sceneKind,
    engine: def.engine,
    rep: args.rep,
    deliberate: def.deliberate,
    startedAtIso: new Date(startedAt).toISOString(),
    finishedAtIso: new Date(startedAt).toISOString(),
    machine: machineRecord(),
    runtime: runtimeLockInfo(),
    scene: {
      width: 1920,
      height: 1080,
      fps: 30,
      durationFrames: def.durationFrames,
      scenes: def.scenes,
    },
    status: "failed",
    failedStage: null,
    error: null,
    stages: [],
    artifacts: { stills: [], preview: null, final: null, encode: null },
    qc: null,
    wallMs: 0,
  };
  const persist = (): void => {
    writeFileSync(args.resultPath, JSON.stringify(record, null, 2) + "\n", "utf8");
  };
  persist();
  const stages = record.stages;
  try {
    // Harness staging: copy/build the job. Recorded as its own stage
    // and excluded from pipeline stage comparisons, so staging cost
    // is visible but never attributed to a pipeline stage.
    let jobDir = "";
    await runStage(stages, "stageJob", async () => {
      jobDir = stageJobForCell(def, cellDir);
      return { jobDir, jobId: readJson(join(jobDir, "manifest.json")).job_id as string };
    });

    // Setup: adapter construction and the shipped runtime probe.
    let adapter: MotionRendererAdapter;
    let runtime: RuntimeEvidence | null = null;
    await runStage(stages, "setup", async () => {
      if (def.engine === "remotion") {
        adapter = createRemotionAdapter({ outputDir: join(cellDir, "renders") });
      } else {
        adapter = new HyperframesAdapter();
      }
      runtime = await adapter!.probeRuntime();
      if (runtime.status !== "ready") {
        throw new Error(`runtime probe not ready (${runtime.status}): ${runtime.detail}`);
      }
      return {
        engine: runtime.engine,
        engineVersion: runtime.runtime.engineVersion,
        runtimeLockId: runtime.runtime.runtimeLockId,
        node: runtime.runtime.nodeVersion,
        platform: runtime.runtime.platform,
        probeDetail: runtime.detail,
        bundleEntriesBefore:
          def.engine === "remotion" ? bundleEntries() : "not a remotion cell",
      };
    });

    // Compile: contracts dispatch (Remotion cells), the MG-021
    // timeline compiler, and the adapter's own validate pass.
    let job: ValidatedMotionJob | null = null;
    let compiledTimelinePath = "";
    let compiledSidecarPath = "";
    let adapterVersion = "";
    await runStage(stages, "compile", async () => {
      const detail: Record<string, unknown> = {};
      const t0 = performance.now();
      if (def.engine === "remotion") {
        job = await loadValidatedJob(jobDir);
        detail.contractsDispatchMs = Math.round(performance.now() - t0);
        detail.jobConstruction = "loadValidatedJob (contracts layer dispatch)";
      } else {
        job = directJob(jobDir);
        detail.contractsDispatchMs = 0;
        detail.jobConstruction =
          "direct ValidatedMotionJob construction (MG-005 suite pattern; the contracts scene shapes do not dispatch C01 scenes on this base, the documented MG-025 divergence)";
      }
      const t1 = performance.now();
      const input: TimelineCompileInput = {
        jobId: job!.jobId,
        fps: 30,
        mode: "program",
        audioOwner: "none",
        scenes: def.scenes,
        transitions: [],
      };
      const compiled = compileTimeline(input);
      if (!compiled.ok) {
        throw new Error(`timeline compile failed: ${JSON.stringify(compiled.findings)}`);
      }
      detail.timelineCompileMs = Math.round(performance.now() - t1);
      compiledTimelinePath = join(cellDir, "timeline.compiled.json");
      compiledSidecarPath = join(cellDir, "sidecar.json");
      writeJson(compiledTimelinePath, compiled.compiled.timeline);
      writeJson(compiledSidecarPath, compiled.compiled.sidecar);
      detail.totalFrames = (compiled.compiled.timeline as { total_frames: number }).total_frames;
      const t2 = performance.now();
      const validation = await adapter!.validate(job!);
      detail.adapterValidateMs = Math.round(performance.now() - t2);
      detail.validateValid = validation.valid;
      detail.validateFindings = validation.findings.length;
      if (!validation.valid) {
        throw new Error(
          `adapter validate failed: ${validation.findings.map((f) => f.category).join(", ")}`
        );
      }
      if (runtime) {
        adapterVersion = `${runtime.engine}/${runtime.runtime.engineVersion}`;
      }
      detail.sidecarSchema = compiled.compiled.sidecar.schema_version;
      return detail;
    });

    // Asset preparation: the shipped key-input collection.
    await runStage(stages, "assetPrep", async () => {
      const compiled = readJson(compiledTimelinePath);
      const sidecar = readJson(compiledSidecarPath);
      const timingHash = hashCanonical({ timeline: compiled, sidecar });
      const collected = collectKeyInputs(job!, timingHash, {
        adapterVersion,
        lockId: (runtime as RuntimeEvidence | null)?.runtime.runtimeLockId ?? "unknown",
        compilerVersion: `mg021-timeline/${sidecar.schema_version as string}`,
      });
      return {
        sceneKeys: collected.keys,
        bytesHashed: collected.bytesHashed,
        inputClasses: collected.classes,
        note: "input collection is re-run on every execution; the cache stores renders keyed by these inputs, it does not store the inputs themselves",
      };
    });

    // Stills: two renderStill calls. For Remotion the second runs on
    // a fresh adapter instance (the MG-028 still pattern), which is
    // what separates first-render bundle cost from warm-bundle cost.
    const still = async (frame: number, fresh: boolean): Promise<ArtifactRecord> => {
      const a =
        fresh && def.engine === "remotion"
          ? createRemotionAdapter({ outputDir: join(cellDir, "renders") })
          : adapter!;
      const evidence: ArtifactEvidence = await a.renderStill(job!, frame);
      const out = evidence.outputPaths[0];
      const p = out.startsWith("/") ? out : join(jobDir, out);
      return artifactRecord(p, false);
    };
    await runStage(stages, "still1", async () => {
      const art = await still(def.stillFrames[0], false);
      record.artifacts.stills.push(art);
      return {
        frame: def.stillFrames[0],
        bytes: art.bytes,
        dims: readPngDimensions(art.path),
        bundleEntriesAfter: def.engine === "remotion" ? bundleEntries() : "not a remotion cell",
      };
    });
    await runStage(stages, "still2", async () => {
      const art = await still(def.stillFrames[1], def.engine === "remotion");
      record.artifacts.stills.push(art);
      return {
        frame: def.stillFrames[1],
        bytes: art.bytes,
        dims: readPngDimensions(art.path),
        instance: def.engine === "remotion" ? "fresh adapter instance" : "same adapter instance",
      };
    });

    // Preview.
    await runStage(stages, "preview", async () => {
      const degraded = def.sceneKind === "degraded";
      const evidence = degraded
        ? await adapter!.renderPreview(job!, { scale: 0.5 })
        : await adapter!.renderPreview(job!);
      const out = evidence.outputPaths[0];
      const p = out.startsWith("/") ? out : join(jobDir, out);
      const art = artifactRecord(p, true);
      record.artifacts.preview = art;
      return {
        bytes: art.bytes,
        probe: art.probe,
        adapterDurationMs: evidence.durationMs ?? null,
        options: degraded ? { scale: 0.5 } : "full scale",
      };
    });

    if (def.sceneKind === "degraded") {
      skipStage(stages, "render", "degraded cell measures the preview path only; its output is fidelity-compared against the full preview in analysis");
      skipStage(stages, "encode", "no final render in the degraded cell");
      skipStage(stages, "qc", "no final render in the degraded cell");
    } else {
      // Final render (with the fixture approval record).
      await runStage(stages, "render", async () => {
        const approved: ApprovedMotionJob = { ...job!, approval: fixtureApproval(job!.jobId) };
        const evidence = await adapter!.renderFinal(approved);
        const out = evidence.outputPaths[0];
        const p = out.startsWith("/") ? out : join(jobDir, out);
        const art = artifactRecord(p, true);
        record.artifacts.final = art;
        return {
          bytes: art.bytes,
          probe: art.probe,
          adapterDurationMs: evidence.durationMs ?? null,
          hasExportRecord: Boolean(evidence.exportRecord),
        };
      });

      // Encode: an isolated re-encode of the produced final, the
      // MG-028 isolation method, reported as the encode stage's
      // measured share. The adapters' internal encode is inside
      // their render timings and is not double counted here.
      await runStage(stages, "encode", async () => {
        const finalPath = record.artifacts.final!.path;
        const outDir = join(cellDir, "encode");
        mkdirSync(outDir, { recursive: true });
        const out = join(outDir, "final-reencode.mp4");
        const res = spawnSync(
          "ffmpeg",
          [
            "-hide_banner", "-loglevel", "error", "-y", "-i", finalPath,
            "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-an", out,
          ],
          { encoding: "utf8" }
        );
        if (res.status !== 0) {
          throw new Error(`isolated encode failed: ${(res.stderr ?? "").slice(0, 500)}`);
        }
        const art = artifactRecord(out, true);
        record.artifacts.encode = art;
        return { bytes: art.bytes, settings: "libx264 crf 16 yuv420p, isolated re-encode of the final (MG-028 method)" };
      });

      // QC: the MG-031 critique bundle over the final, against the
      // compiled timeline and sidecar written by the compile stage.
      await runStage(stages, "qc", async () => {
        const outDir = join(cellDir, "qc");
        mkdirSync(outDir, { recursive: true });
        const res = spawnSync(
          "python3",
          [
            join(SKILL_DIR, "scripts", "critique_bundle.py"),
            "build",
            "--video", record.artifacts.final!.path,
            "--outdir", outDir,
            "--job-id", job!.jobId,
            "--timeline", compiledTimelinePath,
            "--sidecar", compiledSidecarPath,
            "--interval", "2",
          ],
          { cwd: SKILL_DIR, encoding: "utf8" }
        );
        const coverageName = readdirSync(outDir).find((n) => n.endsWith("__coverage.json"));
        if (!coverageName) {
          throw new Error(
            `critique bundle produced no coverage record (exit ${res.status}): ${(res.stderr ?? "").slice(0, 500)}`
          );
        }
        const coverage = readJson(join(outDir, coverageName));
        record.qc = {
          verdict: (coverage.verdict as string) ?? null,
          coveragePath: join(outDir, coverageName),
        };
        return {
          verdict: coverage.verdict,
          exitCode: res.status,
          coveredFrames: coverage.coverage?.covered_frames ?? null,
          accountedFrames: coverage.coverage?.accounted_frames ?? null,
          samples: Array.isArray(coverage.samples) ? coverage.samples.length : null,
          note: "a non-complete verdict is recorded as data; the bundle builder ran and reported, which is what this stage measures",
        };
      });
    }

    record.status = "passed";
  } catch (err) {
    if (err instanceof StageFailure) {
      record.status = "failed";
      record.failedStage = err.stage;
      record.error = err.message.slice(0, 2000);
    } else {
      record.status = "failed";
      record.failedStage = "harness";
      record.error = err instanceof Error ? err.message.slice(0, 2000) : String(err);
    }
  } finally {
    record.finishedAtIso = new Date().toISOString();
    record.wallMs = Date.now() - startedAt;
    persist();
  }
  return record.status === "passed" ? 0 : 1;
}

// ---------------------------------------------------------------------
// Cache child: MG-027 savings, measured stage by stage
// ---------------------------------------------------------------------

interface CacheSceneRun {
  sceneId: string;
  key: string;
  action: "rendered" | "reused" | "failed";
  renderMs: number;
}

interface CacheExecutionRecord {
  name: "cold" | "warm" | "partial";
  startedAtIso: string;
  wallMs: number;
  deriveMs: number;
  sessionMs: number;
  scenes: CacheSceneRun[];
  rendererCalls: string[];
  failures: number;
  error: string | null;
}

interface CacheRecord {
  kind: "cache";
  item: "MG-045";
  cacheDir: string;
  machine: MachineCapacity & { loadAvg: number[] };
  runtime: ReturnType<typeof runtimeLockInfo>;
  jobs: Array<{ jobId: string; sceneId: string; durationFrames: number }>;
  executions: CacheExecutionRecord[];
  savings: {
    coldRenderMs: number;
    warmRenderMs: number;
    warmNetMs: number;
    coldSessionWallMs: number;
    warmSessionWallMs: number;
    partialReusedScene: string;
    partialSavedRenderMs: number;
    perStage: Array<{
      stage: string;
      coldMs: number | null;
      warmMs: number | null;
      savedMs: number;
      basis: string;
    }>;
  };
  failures: CacheExecutionRecord[];
}

/** The run-cache.ts derivation, shared by all executions: compile the
 * two-scene program, probe the runtime for version inputs, and build
 * each scene's work unit from the shipped key inputs. Unit scene ids
 * are session labels ("scene-a", "scene-b"), the run-cache.ts
 * convention: the session keys its state by unit scene id, and both
 * jobs carry the same spec scene id ("bar-01"). */
const CACHE_UNIT_LABELS = ["scene-a", "scene-b"];

async function deriveCacheUnits(jobDirs: string[]): Promise<{
  units: SceneWorkUnit[];
  jobs: ValidatedMotionJob[];
  keys: string[];
}> {
  const jobs = jobDirs.map((dir) => {
    const manifest = readJson(join(dir, "manifest.json")) as unknown as Manifest;
    return { jobDir: dir, jobId: manifest.job_id, manifest } as ValidatedMotionJob;
  });
  const compiled = compileTimeline({
    jobId: "mg045-cache-program",
    fps: 30,
    mode: "program",
    audioOwner: "none",
    scenes: jobs.map((j, i) => ({
      id: CACHE_UNIT_LABELS[i],
      durationFrames: 180,
    })),
    transitions: [],
  });
  if (!compiled.ok) throw new Error("cache program compile failed");
  const timingHash = hashCanonical({
    timeline: compiled.compiled.timeline,
    sidecar: compiled.compiled.sidecar,
  });
  const probe = createRemotionAdapter({ outputDir: join(SCRATCH_ROOT, "cache-probe") });
  const runtime = await probe.probeRuntime();
  const units: SceneWorkUnit[] = [];
  const keys: string[] = [];
  jobs.forEach((job, i) => {
    const label = CACHE_UNIT_LABELS[i];
    const entry = job.manifest.scenes[0];
    const specPath = join(job.jobDir, entry.spec);
    const spec = readJson(specPath);
    const loaded = loadC05Job(job);
    const keyInputs: SceneKeyInputs = {
      sceneId: label,
      engine: "remotion",
      sceneSourceHash: sha256File(specPath),
      propsHash: hashCanonical(loaded.props),
      assetHashes: {},
      fontHashes: {
        [loaded.font.requirementId]: hashCanonical(
          loaded.font.files.map((f) => [f.weight, f.sha256])
        ),
      },
      dataHashes: {
        [spec.data_path as string]: sha256File(join(job.jobDir, spec.data_path as string)),
      },
      timingHash,
      width: job.manifest.canvas.width,
      height: job.manifest.canvas.height,
      fps: job.manifest.canvas.fps,
      exportSettings: { container: "mp4", videoProfile: "h264_opaque" },
      adapterVersion: `remotion/${runtime.runtime.engineVersion}`,
      compilerVersion: `mg021-timeline/${compiled.compiled.sidecar.schema_version}`,
      runtimeLockId: runtime.runtime.runtimeLockId ?? "unprobed-lock",
    };
    keys.push(deriveSceneCacheKey(keyInputs).key);
    units.push({
      sceneId: label,
      keyInputs,
      chunksTotal: 1,
      artifactFileName: `${label}.mp4`,
    });
  });
  return { units, jobs, keys };
}

async function runCacheChild(cacheDir: string, resultPath: string): Promise<number> {
  rmSync(cacheDir, { recursive: true, force: true });
  // The parent points the child's TMPDIR at <cacheDir>/tmp; the wipe
  // above removes it, so recreate it before any engine runs (Remotion
  // creates per-render asset dirs directly under TMPDIR).
  mkdirSync(join(cacheDir, "tmp"), { recursive: true });
  const staging = join(cacheDir, "staging");
  const jobA = join(staging, "job-a");
  const jobB = join(staging, "job-b");
  cpSync(join(FIXTURES_ROOT, "modes", "powerpoint_graphic"), jobA, { recursive: true });
  const manifestB = readJson(join(jobA, "manifest.json"));
  manifestB.job_id = "mg045-cache-standalone";
  manifestB.mode = "standalone_video";
  manifestB.content_scope = "full_program";
  cpSync(join(FIXTURES_ROOT, "modes", "powerpoint_graphic"), jobB, { recursive: true });
  writeJson(join(jobB, "manifest.json"), manifestB);
  const workDir = join(cacheDir, "session");
  const renderCalls: string[] = [];
  const renderMsByScene = new Map<string, number>();

  const record: CacheRecord = {
    kind: "cache",
    item: "MG-045",
    cacheDir,
    machine: machineRecord(),
    runtime: runtimeLockInfo(),
    jobs: [
      { jobId: "fixture-powerpoint-graphic", sceneId: "bar-01", durationFrames: 180 },
      { jobId: "mg045-cache-standalone", sceneId: "bar-01", durationFrames: 180 },
    ],
    executions: [],
    savings: {
      coldRenderMs: 0,
      warmRenderMs: 0,
      warmNetMs: 0,
      coldSessionWallMs: 0,
      warmSessionWallMs: 0,
      partialReusedScene: "",
      partialSavedRenderMs: 0,
      perStage: [],
    },
    failures: [],
  };
  const persist = (): void => {
    writeFileSync(resultPath, JSON.stringify(record, null, 2) + "\n", "utf8");
  };
  persist();

  /** One cache execution: derive units (timed; this is the input
   * collection the cache does NOT save), open a session on the shared
   * work dir, plan, and run with renderers that wrap the production
   * Remotion renderFinal and record per-scene render time. */
  async function execution(
    name: CacheExecutionRecord["name"],
    jobDirs: string[]
  ): Promise<CacheExecutionRecord> {
    const startedAtIso = new Date().toISOString();
    const wall0 = performance.now();
    renderCalls.length = 0;
    renderMsByScene.clear();
    const exec: CacheExecutionRecord = {
      name,
      startedAtIso,
      wallMs: 0,
      deriveMs: 0,
      sessionMs: 0,
      scenes: [],
      rendererCalls: [],
      failures: 0,
      error: null,
    };
    try {
      const d0 = performance.now();
      const { units, jobs, keys } = await deriveCacheUnits(jobDirs);
      exec.deriveMs = Math.round(performance.now() - d0);
      const jobByLabel = new Map<string, ValidatedMotionJob>();
      units.forEach((u, i) => jobByLabel.set(u.sceneId, jobs[i]));
      const s0 = performance.now();
      const session = await CachedRenderSession.open({
        workDir,
        jobId: "mg045-cache-program",
        units,
      });
      const rendererFor = (unit: SceneWorkUnit) => {
        const job = jobByLabel.get(unit.sceneId);
        if (!job) throw new Error(`no job for cache unit ${unit.sceneId}`);
        return async (ctx: SceneRenderContext) => {
          const rs = performance.now();
          renderCalls.push(`${job.jobId}:${unit.sceneId}`);
          const adapter = createRemotionAdapter({ outputDir: ctx.chunkDir });
          const approved: ApprovedMotionJob = {
            ...job,
            approval: fixtureApproval(job.jobId),
          };
          const rendered = await adapter.renderFinal(approved);
          const { copyFileSync } = require("node:fs") as typeof import("node:fs");
          copyFileSync(rendered.outputPaths[0], ctx.artifactPath);
          await ctx.reportChunkComplete(0);
          renderMsByScene.set(job.jobId, Math.round(performance.now() - rs));
          const facts = probeVideoFile(ctx.artifactPath);
          return {
            probe: {
              kind: "video" as const,
              width: facts.width,
              height: facts.height,
              fpsNumerator: facts.fpsNumerator,
              fpsDenominator: facts.fpsDenominator,
              frames: facts.frameCount ?? 0,
            },
          };
        };
      };
      const outcome = await session.run(rendererFor);
      exec.sessionMs = Math.round(performance.now() - s0);
      const failedResults = outcome.results.filter((r) => r.action === "failed");
      exec.failures = failedResults.length;
      if (failedResults.length > 0) {
        exec.error = failedResults
          .map(
            (r) =>
              `${r.sceneId}: ${r.findings.map((f) => f.message).join("; ").slice(0, 400)}`
          )
          .join(" | ")
          .slice(0, 1000);
      }
      outcome.results.forEach((result, i) => {
        const job = jobs[i];
        exec.scenes.push({
          sceneId: `${job.jobId}:${result.sceneId}`,
          key: keys[i],
          action: result.action,
          renderMs:
            result.action === "reused" ? 0 : renderMsByScene.get(job.jobId) ?? 0,
        });
      });
      exec.rendererCalls = [...renderCalls];
    } catch (err) {
      exec.error = err instanceof Error ? err.message.slice(0, 1000) : String(err);
      exec.failures += 1;
    }
    exec.wallMs = Math.round(performance.now() - wall0);
    record.executions.push(exec);
    if (exec.error) record.failures.push(exec);
    persist();
    return exec;
  }

  const cold = await execution("cold", [jobA, jobB]);
  const warm = await execution("warm", [jobA, jobB]);
  // Partial: change only job B's dataset value (Group C 30 to 31).
  // Job A's key must be unchanged; job B must re-render.
  const barsPath = join(jobB, "data", "bars.json");
  const bars = readJson(barsPath);
  (bars.rows as Array<{ value: number }>)[2].value = 31;
  writeJson(barsPath, bars);
  const partial = await execution("partial", [jobA, jobB]);

  const coldRenderMs = cold.scenes.reduce((a, s) => a + s.renderMs, 0);
  const warmRenderMs = warm.scenes.reduce((a, s) => a + s.renderMs, 0);
  const sceneA = cold.scenes[0];
  const partialA = partial.scenes.find((s) => s.sceneId === sceneA.sceneId);
  const partialSavedRenderMs =
    partialA && partialA.action === "reused" ? sceneA.renderMs : 0;
  record.savings = {
    coldRenderMs,
    warmRenderMs,
    warmNetMs: cold.wallMs - warm.wallMs,
    coldSessionWallMs: cold.wallMs,
    warmSessionWallMs: warm.wallMs,
    partialReusedScene: partialA ? partialA.sceneId : "",
    partialSavedRenderMs,
    perStage: [
      {
        stage: "render (includes the adapter's internal encode)",
        coldMs: coldRenderMs,
        warmMs: warmRenderMs,
        savedMs: coldRenderMs - warmRenderMs,
        basis:
          "renderer wall time inside CachedRenderSession.run; on a warm hit the renderer is never invoked, so the whole render stage is saved",
      },
      {
        stage: "encode (standalone)",
        coldMs: null,
        warmMs: null,
        savedMs: 0,
        basis:
          "no standalone encode exists in the cache path; the adapter's encode is inside renderFinal and its saving is counted once, in the render stage, never twice",
      },
      {
        stage: "compile (timeline) and asset preparation (key input hashing)",
        coldMs: cold.deriveMs,
        warmMs: warm.deriveMs,
        savedMs: 0,
        basis:
          "unit derivation runs on every execution by design: the cache can only know a hit after the inputs are hashed. Measured cost repeats; savings are zero and are reported as zero",
      },
      {
        stage: "QC",
        coldMs: null,
        warmMs: null,
        savedMs: 0,
        basis: "the cache session performs no QC; there is nothing to save and nothing is claimed",
      },
      {
        stage: "stills and preview",
        coldMs: null,
        warmMs: null,
        savedMs: 0,
        basis: "the cache session renders finals only; stills and previews are not served by it and no savings are claimed for them",
      },
    ],
  };
  persist();
  const failed = record.executions.some((e) => e.error !== null);
  return failed ? 1 : 0;
}

// ---------------------------------------------------------------------
// Analysis: the honesty rules as pure functions (self-checked below)
// ---------------------------------------------------------------------

interface RankableRecord {
  cellId: string;
  rep: number;
  status: "passed" | "failed";
  deliberate: boolean;
  stageMs: Record<string, number>;
}

interface FidelityVerdict {
  degraded: boolean;
  basis: string;
}

/** A run is degraded when its output is not the reference output:
 * different dimensions, or decoded pixels differing beyond the exact
 * tolerance the determinism layer defines (EXACT_PIXELS). */
function verdictForComparison(input: {
  dimensionsMatch: boolean;
  identical: boolean | null;
  differingPixels: number | null;
  referenceLabel: string;
}): FidelityVerdict {
  if (!input.dimensionsMatch) {
    return {
      degraded: true,
      basis: `output dimensions differ from ${input.referenceLabel}`,
    };
  }
  if (input.identical === false) {
    return {
      degraded: true,
      basis: `${input.differingPixels ?? "?"} decoded pixels differ from ${input.referenceLabel} beyond EXACT_PIXELS tolerance`,
    };
  }
  return { degraded: false, basis: `output matches ${input.referenceLabel} exactly at sampled frames` };
}

function rankStage(
  records: RankableRecord[],
  stage: string,
  verdicts: Map<string, FidelityVerdict>
): {
  ranking: Array<{ cellId: string; rep: number; ms: number }>;
  excluded: Array<{ cellId: string; rep: number; reason: string }>;
} {
  const ranking: Array<{ cellId: string; rep: number; ms: number }> = [];
  const excluded: Array<{ cellId: string; rep: number; reason: string }> = [];
  for (const r of records) {
    if (r.status !== "passed") {
      excluded.push({ cellId: r.cellId, rep: r.rep, reason: `run status is ${r.status}` });
      continue;
    }
    const v = verdicts.get(`${r.cellId}@${r.rep}`);
    if (v?.degraded) {
      excluded.push({ cellId: r.cellId, rep: r.rep, reason: `degraded output: ${v.basis}` });
      continue;
    }
    const ms = r.stageMs[stage];
    if (ms === undefined) continue;
    ranking.push({ cellId: r.cellId, rep: r.rep, ms });
  }
  ranking.sort((a, b) => a.ms - b.ms);
  return { ranking, excluded };
}

function failureAccounting(
  records: Array<{ status: string; deliberate: boolean }>
): {
  attempted: number;
  failed: number;
  deliberateFailed: number;
  failureRate: number;
  failureRateExcludingDeliberate: number;
} {
  const attempted = records.length;
  const failed = records.filter((r) => r.status !== "passed").length;
  const deliberateFailed = records.filter(
    (r) => r.status !== "passed" && r.deliberate
  ).length;
  const honest = records.filter((r) => !r.deliberate);
  const honestFailed = honest.filter((r) => r.status !== "passed").length;
  return {
    attempted,
    failed,
    deliberateFailed,
    failureRate: attempted > 0 ? failed / attempted : 0,
    failureRateExcludingDeliberate: honest.length > 0 ? honestFailed / honest.length : 0,
  };
}

function stageVariance(
  records: RankableRecord[]
): Array<{
  cellId: string;
  stage: string;
  values: number[];
  min: number;
  max: number;
  mean: number;
  spreadPct: number;
}> {
  const byKey = new Map<string, number[]>();
  for (const r of records) {
    for (const [stage, ms] of Object.entries(r.stageMs)) {
      const key = `${r.cellId}::${stage}`;
      const arr = byKey.get(key) ?? [];
      arr.push(ms);
      byKey.set(key, arr);
    }
  }
  const out: Array<{
    cellId: string;
    stage: string;
    values: number[];
    min: number;
    max: number;
    mean: number;
    spreadPct: number;
  }> = [];
  for (const [key, values] of [...byKey.entries()].sort()) {
    const [cellId, stage] = key.split("::");
    const min = Math.min(...values);
    const max = Math.max(...values);
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    out.push({
      cellId,
      stage,
      values,
      min,
      max,
      mean: Math.round(mean),
      spreadPct: mean > 0 ? Math.round(((max - min) / mean) * 1000) / 10 : 0,
    });
  }
  return out;
}

function toRankable(rec: CellRunRecord): RankableRecord {
  const stageMs: Record<string, number> = {};
  for (const s of rec.stages) {
    if (s.ok && !("skipped" in s.detail)) stageMs[s.name] = s.ms;
  }
  return {
    cellId: rec.cellId,
    rep: rec.rep,
    status: rec.status,
    deliberate: rec.deliberate,
    stageMs,
  };
}

// ---------------------------------------------------------------------
// Self-check: the analysis logic over synthetic records
// ---------------------------------------------------------------------

function runSelfCheck(): number {
  let failures = 0;
  const check = (cond: boolean, label: string): void => {
    console.log(`${cond ? "PASS" : "FAIL"} ${label}`);
    if (!cond) failures += 1;
  };
  const records: RankableRecord[] = [
    { cellId: "normal-a", rep: 1, status: "passed", deliberate: false, stageMs: { preview: 1000 } },
    { cellId: "normal-a", rep: 2, status: "passed", deliberate: false, stageMs: { preview: 1100 } },
    { cellId: "normal-b", rep: 1, status: "passed", deliberate: false, stageMs: { preview: 800 } },
    { cellId: "fast-degraded", rep: 1, status: "passed", deliberate: true, stageMs: { preview: 300 } },
    { cellId: "broken", rep: 1, status: "failed", deliberate: false, stageMs: {} },
  ];
  const verdicts = new Map<string, FidelityVerdict>([
    [
      "fast-degraded@1",
      verdictForComparison({
        dimensionsMatch: false,
        identical: null,
        differingPixels: null,
        referenceLabel: "the full-scale reference preview",
      }),
    ],
  ]);
  check(verdicts.get("fast-degraded@1")!.degraded, "a dimension mismatch is judged degraded");
  const pixelVerdict = verdictForComparison({
    dimensionsMatch: true,
    identical: false,
    differingPixels: 42,
    referenceLabel: "the reference frame",
  });
  check(pixelVerdict.degraded, "differing decoded pixels beyond EXACT_PIXELS are judged degraded");
  const exactVerdict = verdictForComparison({
    dimensionsMatch: true,
    identical: true,
    differingPixels: 0,
    referenceLabel: "the reference frame",
  });
  check(!exactVerdict.degraded, "an exactly matching output is not degraded");
  const { ranking, excluded } = rankStage(records, "preview", verdicts);
  check(
    ranking.length === 3 && ranking[0].cellId === "normal-b",
    "ranking orders non-degraded runs by stage time (fastest first)"
  );
  check(
    !ranking.some((r) => r.cellId === "fast-degraded"),
    "the faster degraded run is NOT in the ranking: degraded cannot win"
  );
  check(
    excluded.some((e) => e.cellId === "fast-degraded" && e.reason.includes("degraded")),
    "the degraded run is listed as excluded with the degraded reason"
  );
  check(
    excluded.some((e) => e.cellId === "broken"),
    "the failed run is listed as excluded, not dropped"
  );
  const acct = failureAccounting(records);
  check(
    acct.attempted === 5 && acct.failed === 1 && Math.abs(acct.failureRate - 0.2) < 1e-9,
    "failure accounting counts the failed run in the rate (1 of 5)"
  );
  const variance = stageVariance(records);
  const normalA = variance.find((v) => v.cellId === "normal-a" && v.stage === "preview");
  check(
    Boolean(normalA) && normalA!.values.length === 2 && normalA!.spreadPct > 0,
    "variance reports both repetitions and a spread"
  );
  console.log(
    failures === 0
      ? "MG-045 SELF-CHECK: all checks passed"
      : `MG-045 SELF-CHECK: ${failures} check(s) failed`
  );
  return failures === 0 ? 0 : 1;
}

// ---------------------------------------------------------------------
// Fidelity analysis over real outputs (parent side)
// ---------------------------------------------------------------------

function extractFrame(videoPath: string, frame: number, outPng: string): void {
  const res = spawnSync(
    "ffmpeg",
    [
      "-hide_banner", "-loglevel", "error", "-y", "-i", videoPath,
      "-vf", `select='eq(n\\,${frame})'`, "-vframes", "1", outPng,
    ],
    { encoding: "utf8" }
  );
  if (res.status !== 0 || !existsSync(outPng)) {
    throw new Error(`frame extraction failed for frame ${frame} of ${videoPath}: ${(res.stderr ?? "").slice(0, 300)}`);
  }
}

interface FrameComparisonRecord {
  frame: number;
  width: number;
  height: number;
  differingPixels: number;
  differingFraction: number;
  maxChannelDelta: number;
  identical: boolean;
  verdict: string;
}

async function compareVideosAtFrames(
  videoA: string,
  videoB: string,
  frames: number[],
  scratchDir: string,
  label: string
): Promise<FrameComparisonRecord[]> {
  mkdirSync(scratchDir, { recursive: true });
  const out: FrameComparisonRecord[] = [];
  for (const frame of frames) {
    const pngA = join(scratchDir, `${label}-a-${frame}.png`);
    const pngB = join(scratchDir, `${label}-b-${frame}.png`);
    extractFrame(videoA, frame, pngA);
    extractFrame(videoB, frame, pngB);
    const decA = await decodePngPixels(pngA);
    const decB = await decodePngPixels(pngB);
    const cmp = compareDecodedPixels(decA, decB);
    const tol = toleranceVerdict(cmp, EXACT_PIXELS);
    out.push({
      frame,
      width: cmp.width,
      height: cmp.height,
      differingPixels: cmp.differingPixels,
      differingFraction: cmp.differingFraction,
      maxChannelDelta: cmp.maxChannelDelta,
      identical: tol.pass,
      verdict: tol.pass ? "identical" : tol.reasons.join(" "),
    });
  }
  return out;
}

async function buildAnalysis(
  allRecords: CellRunRecord[],
  framesScratch: string,
  cacheRecord: CacheRecord | null
): Promise<Record<string, unknown>> {
  const rankables = allRecords.map(toRankable);
  const verdicts = new Map<string, FidelityVerdict>();
  const fidelity: Record<string, unknown> = {};
  const byCell = new Map<string, CellRunRecord[]>();
  for (const rec of allRecords) {
    const arr = byCell.get(rec.cellId) ?? [];
    arr.push(rec);
    byCell.set(rec.cellId, arr);
  }
  // Cross-repetition fidelity: rep 2 (and later) against rep 1, the
  // reference repetition, per cell, at the cell's fidelity frames.
  for (const [cellId, recs] of byCell) {
    const sorted = [...recs].sort((a, b) => a.rep - b.rep);
    const ref = sorted[0];
    if (!ref?.artifacts.final || sorted.length < 2) continue;
    const def = CELLS.find((c) => c.cellId === cellId);
    if (!def || def.fidelityFrames.length === 0) continue;
    const cellFidelity: Record<string, unknown> = {};
    for (const other of sorted.slice(1)) {
      if (other.status !== "passed" || !other.artifacts.final) {
        cellFidelity[`rep${other.rep}`] = { skipped: `rep ${other.rep} did not produce a final` };
        continue;
      }
      const frames = await compareVideosAtFrames(
        ref.artifacts.final.path,
        other.artifacts.final.path,
        def.fidelityFrames,
        join(framesScratch, cellId),
        `${cellId}-rep${ref.rep}-vs-rep${other.rep}`
      );
      const allIdentical = frames.every((f) => f.identical);
      cellFidelity[`rep${other.rep}`] = {
        reference: `rep ${ref.rep} final`,
        frames,
        allIdentical,
      };
      verdicts.set(
        `${cellId}@${other.rep}`,
        verdictForComparison({
          dimensionsMatch: true,
          identical: allIdentical,
          differingPixels: frames.reduce((a, f) => a + f.differingPixels, 0),
          referenceLabel: `rep ${ref.rep} of the same cell`,
        })
      );
    }
    fidelity[cellId] = cellFidelity;
  }
  // The degraded demonstration: the half-scale preview against the
  // full-scale chart preview of the same repetition.
  const degradedDemo: Record<string, unknown> = {};
  for (const rep of [...new Set(allRecords.map((r) => r.rep))].sort()) {
    const degraded = allRecords.find(
      (r) => r.cellId === "degraded-chart-remotion" && r.rep === rep
    );
    const reference = allRecords.find(
      (r) => r.cellId === "chart-remotion" && r.rep === rep
    );
    if (!degraded?.artifacts.preview || !reference?.artifacts.preview) {
      degradedDemo[`rep${rep}`] = { skipped: "degraded or reference preview missing" };
      continue;
    }
    const scratch = join(framesScratch, "degraded", `rep${rep}`);
    mkdirSync(scratch, { recursive: true });
    const refPng = join(scratch, "reference-f45.png");
    const degPng = join(scratch, "degraded-f45.png");
    extractFrame(reference.artifacts.preview.path, 45, refPng);
    extractFrame(degraded.artifacts.preview.path, 45, degPng);
    const refDims = readPngDimensions(refPng);
    const degDims = readPngDimensions(degPng);
    const dimensionsMatch =
      refDims !== null && degDims !== null &&
      refDims.width === degDims.width && refDims.height === degDims.height;
    // Upscale the degraded frame to the reference size with a plain
    // bilinear scale so pixel difference is measurable at all; the
    // upscale filter is named in the record.
    const upPng = join(scratch, "degraded-f45-upscaled.png");
    const up = spawnSync(
      "ffmpeg",
      ["-hide_banner", "-loglevel", "error", "-y", "-i", degPng, "-vf", "scale=1920:1080:flags=bilinear", upPng],
      { encoding: "utf8" }
    );
    let differingPixels: number | null = null;
    if (up.status === 0 && existsSync(upPng)) {
      const cmp = compareDecodedPixels(
        await decodePngPixels(refPng),
        await decodePngPixels(upPng)
      );
      differingPixels = cmp.differingPixels;
    }
    const verdict = verdictForComparison({
      dimensionsMatch,
      identical: differingPixels === 0,
      differingPixels,
      referenceLabel: "the full-scale chart-remotion preview of the same repetition",
    });
    verdicts.set(`degraded-chart-remotion@${rep}`, verdict);
    const degradedStage = degraded.stages.find((s) => s.name === "preview");
    const referenceStage = reference.stages.find((s) => s.name === "preview");
    degradedDemo[`rep${rep}`] = {
      degradedPreviewMs: degradedStage?.ms ?? null,
      referencePreviewMs: referenceStage?.ms ?? null,
      degradedFasterByMs:
        degradedStage && referenceStage ? referenceStage.ms - degradedStage.ms : null,
      referenceDims: refDims,
      degradedDims: degDims,
      dimensionsMatch,
      differingPixelsAfterBilinearUpscale: differingPixels,
      upscaleFilter: "ffmpeg scale=1920:1080:flags=bilinear",
      verdict: verdict.degraded ? "DEGRADED" : "not degraded",
      basis: verdict.basis,
      rankingTreatment:
        "excluded from every speed ranking by the rankStage rule; its preview time is reported only alongside this verdict",
    };
  }
  const chartCells = rankables.filter((r) => r.cellId.startsWith("chart-"));
  return {
    item: "MG-045",
    generatedAt: new Date().toISOString(),
    machine: machineRecord(),
    runtime: runtimeLockInfo(),
    stageTable: rankables.map((r) => ({
      cellId: r.cellId,
      rep: r.rep,
      status: r.status,
      stageMs: r.stageMs,
    })),
    variance: stageVariance(rankables),
    failures: failureAccounting(
      allRecords.map((r) => ({ status: r.status, deliberate: r.deliberate }))
    ),
    fidelity,
    degradedDemonstration: degradedDemo,
    rankings: {
      note: "rankings contain only passed runs whose output was not judged degraded; excluded runs are listed with their reason",
      chartPreview: rankStage(chartCells, "preview", verdicts),
      chartRender: rankStage(chartCells, "render", verdicts),
      allPreviews: rankStage(rankables, "preview", verdicts),
    },
    cache: cacheRecord
      ? {
          executions: cacheRecord.executions.map((e) => ({
            name: e.name,
            wallMs: e.wallMs,
            deriveMs: e.deriveMs,
            sessionMs: e.sessionMs,
            scenes: e.scenes,
            rendererCalls: e.rendererCalls,
            error: e.error,
          })),
          savings: cacheRecord.savings,
        }
      : null,
  };
}

// ---------------------------------------------------------------------
// Parent
// ---------------------------------------------------------------------

function argValue(argv: string[], name: string): string | null {
  const i = argv.indexOf(name);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : null;
}

async function runParent(argv: string[]): Promise<number> {
  const reps = Number(argValue(argv, "--reps") ?? "2");
  const cellsArg = argValue(argv, "--cells");
  const selected = cellsArg
    ? CELLS.filter((c) => cellsArg.split(",").includes(c.cellId))
    : CELLS;
  const outDir = argValue(argv, "--out-dir") ?? join(SCRATCH_ROOT, "records");
  const writeEvidence = argv.includes("--write-evidence");
  mkdirSync(outDir, { recursive: true });
  const allRecords: CellRunRecord[] = [];
  let missingRecords = 0;
  for (let rep = 1; rep <= reps; rep++) {
    const repRecords: CellRunRecord[] = [];
    for (const def of selected) {
      const cellDir = join(SCRATCH_ROOT, `rep-${rep}`, def.cellId);
      mkdirSync(cellDir, { recursive: true });
      const resultPath = join(cellDir, "record.json");
      const env: NodeJS.ProcessEnv = {
        ...process.env,
        MOTION_RENDER_BUDGET_DIR: join(SCRATCH_ROOT, `rep-${rep}`, "budget-ledger"),
        TMPDIR: join(cellDir, "tmp"),
      };
      const run = await runSampledChild(
        [
          __filename,
          "--role", "cell",
          "--cell", def.cellId,
          "--rep", String(rep),
          "--dir", cellDir,
          "--result", resultPath,
        ],
        env,
        cellDir
      );
      let rec: CellRunRecord | null = null;
      if (existsSync(resultPath)) {
        try {
          rec = readJson(resultPath) as unknown as CellRunRecord;
        } catch {
          rec = null;
        }
      }
      if (!rec) {
        missingRecords += 1;
        rec = {
          kind: "cell",
          item: "MG-045",
          cellId: def.cellId,
          sceneKind: def.sceneKind,
          engine: def.engine,
          rep,
          deliberate: def.deliberate,
          startedAtIso: new Date().toISOString(),
          finishedAtIso: new Date().toISOString(),
          machine: machineRecord(),
          runtime: runtimeLockInfo(),
          scene: {
            width: 1920, height: 1080, fps: 30,
            durationFrames: def.durationFrames, scenes: def.scenes,
          },
          status: "failed",
          failedStage: "harness",
          error: `cell child produced no record (exit ${run.exitCode}, timedOut ${run.timedOut}): ${run.stderrTail.slice(-500)}`,
          stages: [],
          artifacts: { stills: [], preview: null, final: null, encode: null },
          qc: null,
          wallMs: run.wallMs,
        };
      }
      if (run.timedOut) {
        rec.status = "failed";
        rec.failedStage = rec.failedStage ?? "timeout";
        rec.error = `${rec.error ?? ""} child exceeded the ${CHILD_TIMEOUT_MS} ms harness timeout and was killed`.trim();
      }
      const phasePeakMap: NonNullable<CellRunRecord["resources"]>["phasePeaks"] = {};
      for (const stage of rec.stages) {
        const inWindow = run.samples.filter(
          (s) => s.t >= stage.startedAt && s.t <= stage.endedAt
        );
        phasePeakMap[stage.name] = {
          peakRssMB: Math.round(Math.max(0, ...inWindow.map((s) => s.rssMB))),
          peakBrowserMains: Math.max(0, ...inWindow.map((s) => s.browserMains)),
          peakProcesses: Math.max(0, ...inWindow.map((s) => s.processes)),
          wallMs: stage.ms,
        };
      }
      rec.resources = {
        peakRssMB: Math.round(run.peak.rssMB),
        peakProcesses: run.peak.processes,
        peakBrowserMains: run.peak.browserMains,
        peakDiskBytes: run.peakDiskBytes,
        finalDiskBytes: run.finalDiskBytes,
        phasePeaks: phasePeakMap,
      };
      writeFileSync(resultPath, JSON.stringify(rec, null, 2) + "\n", "utf8");
      repRecords.push(rec);
      allRecords.push(rec);
      console.log(
        `[mg045] rep ${rep} ${def.cellId}: ${rec.status}` +
          (rec.failedStage ? ` (failed at ${rec.failedStage})` : "") +
          ` wall ${Math.round(run.wallMs / 100) / 10}s peakRSS ${rec.resources.peakRssMB}MB peakDisk ${Math.round(run.peakDiskBytes / 1e6)}MB`
      );
    }
    writeFileSync(
      join(outDir, `rep-${rep}.json`),
      JSON.stringify(
        {
          item: "MG-045",
          rep,
          generatedAt: new Date().toISOString(),
          machine: machineRecord(),
          runtime: runtimeLockInfo(),
          sharedBundleDirBytes: dirBytes(join(RUNTIME_STATE, "mg006-bundles")),
          cells: repRecords,
        },
        null,
        2
      ) + "\n",
      "utf8"
    );
  }
  // Cache benchmark (its own record; repetitions do not apply to it).
  const cacheDir = join(SCRATCH_ROOT, "cache");
  mkdirSync(join(cacheDir, "tmp"), { recursive: true });
  const cacheResultPath = join(cacheDir, "record.json");
  const cacheRun = await runSampledChild(
    [__filename, "--role", "cache", "--dir", cacheDir, "--result", cacheResultPath],
    {
      ...process.env,
      MOTION_RENDER_BUDGET_DIR: join(SCRATCH_ROOT, "cache-budget-ledger"),
      TMPDIR: join(cacheDir, "tmp"),
    },
    cacheDir
  );
  let cacheRecord: CacheRecord | null = null;
  if (existsSync(cacheResultPath)) {
    try {
      cacheRecord = readJson(cacheResultPath) as unknown as CacheRecord;
    } catch {
      cacheRecord = null;
    }
  }
  if (cacheRecord) {
    writeFileSync(
      join(outDir, "cache.json"),
      JSON.stringify(
        {
          ...cacheRecord,
          sampledResources: {
            peakRssMB: Math.round(cacheRun.peak.rssMB),
            peakDiskBytes: cacheRun.peakDiskBytes,
            wallMs: cacheRun.wallMs,
            timedOut: cacheRun.timedOut,
          },
        },
        null,
        2
      ) + "\n",
      "utf8"
    );
  } else {
    missingRecords += 1;
    console.log(`[mg045] cache child produced no record (exit ${cacheRun.exitCode})`);
  }
  console.log(
    `[mg045] cache: ${cacheRecord ? cacheRecord.executions.map((e) => `${e.name} ${e.wallMs}ms`).join(", ") : "NO RECORD"}`
  );
  const analysis = await buildAnalysis(
    allRecords,
    join(SCRATCH_ROOT, "frames"),
    cacheRecord
  );
  writeFileSync(join(outDir, "analysis.json"), JSON.stringify(analysis, null, 2) + "\n", "utf8");
  if (writeEvidence) {
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    for (let rep = 1; rep <= reps; rep++) {
      cpSync(join(outDir, `rep-${rep}.json`), join(EVIDENCE_DIR, `rep-${rep}.json`));
    }
    if (existsSync(join(outDir, "cache.json"))) {
      cpSync(join(outDir, "cache.json"), join(EVIDENCE_DIR, "cache.json"));
    }
    cpSync(join(outDir, "analysis.json"), join(EVIDENCE_DIR, "analysis.json"));
  }
  console.log(`[mg045] records in ${outDir}${writeEvidence ? `, evidence copied to ${EVIDENCE_DIR}` : ""}`);
  return missingRecords > 0 ? 1 : 0;
}

// ---------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------

async function main(): Promise<number> {
  const argv = process.argv.slice(2);
  if (argv.includes("--self-check")) return runSelfCheck();
  const role = argValue(argv, "--role");
  if (role === "cell") {
    return runCellChild({
      cellId: argValue(argv, "--cell") ?? "",
      rep: Number(argValue(argv, "--rep") ?? "1"),
      cellDir: argValue(argv, "--dir") ?? "",
      resultPath: argValue(argv, "--result") ?? "",
    });
  }
  if (role === "cache") {
    return runCacheChild(argValue(argv, "--dir") ?? "", argValue(argv, "--result") ?? "");
  }
  return runParent(argv);
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(err instanceof Error ? err.stack ?? err.message : String(err));
    process.exit(2);
  });
