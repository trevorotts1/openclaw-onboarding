// MG-028 capacity measurement driver.
//
// Measures representative scene rendering on the actual provisioned
// runtime so the resource profiles in src/resources/profiles.ts are
// numbers from THIS machine class, not folklore. Two roles:
//
// - Parent (default): spawns one child per measurement, samples the
//   child's whole process tree every 50 ms (peak RSS sum, browser
//   main-process count, ffmpeg count), times the phases the child
//   reports, measures the standalone encode share with ffmpeg, and
//   writes the record to tests/evidence/mg028/measurements.json when
//   --write-evidence is passed (otherwise prints it).
// - Child (--role remotion-child | hyperframes-child): performs real
//   adapter renders of the shipped C05 fixture job in-process and
//   writes its phase timings to a result file. Rendering in a child
//   keeps the sampled tree exactly one render's tree.
//
// Method and uncertainty are recorded in the output itself: RSS sums
// overcount shared pages, 50 ms sampling can miss short spikes, and a
// warm bundle cache changes the still timings; the record states the
// bundle cache state it observed rather than hiding it.

import { spawn } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { createRemotionAdapter } from "../src/adapters/remotion";
import { HyperframesAdapter } from "../src/adapters/hyperframes";
import { loadValidatedJob } from "../src/adapters/dispatch";
import type { ValidatedMotionJob } from "../src/adapters/types";
import { measureMachineCapacity } from "../src/resources/preflight";

const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const SCRATCH = join(REPO_ROOT, ".scratch", "mg028-measure");
const TMP_SCRATCH = join(SCRATCH, "tmp");
mkdirSync(TMP_SCRATCH, { recursive: true });
process.env.TMPDIR = TMP_SCRATCH;
const FIXTURES_ROOT = join(SKILL_DIR, "tests", "fixtures");
const EVIDENCE_DIR = join(SKILL_DIR, "tests", "evidence", "mg028");
const RUNTIME_STATE = join(REPO_ROOT, "shared-utils", "motion-render-runtime", ".runtime");

// ---------------------------------------------------------------------
// Process-tree sampling
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
  ffmpegProcesses: number;
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
  let ffmpegProcesses = 0;
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
    if (p.cmdline.includes("ffmpeg")) ffmpegProcesses += 1;
  }
  return { rssMB: rssKB / 1024, processes: members.size, browserMains, ffmpegProcesses };
}

interface RunOutcome {
  exitCode: number;
  wallMs: number;
  peak: TreeSample;
  /** Every sample with its epoch timestamp, so the parent can align
   * peaks to the phases the child reports. */
  samples: Array<{ t: number } & TreeSample>;
  stdoutTail: string;
  stderrTail: string;
}

function runSampled(command: string, args: string[], env: NodeJS.ProcessEnv): Promise<RunOutcome> {
  return new Promise((resolvePromise, rejectPromise) => {
    const started = Date.now();
    const child = spawn(command, args, { env, shell: false });
    let stdout = "";
    let stderr = "";
    const peak: TreeSample = { rssMB: 0, processes: 0, browserMains: 0, ffmpegProcesses: 0 };
    const samples: Array<{ t: number } & TreeSample> = [];
    const timer = setInterval(() => {
      if (!child.pid) return;
      const s = sampleTree(child.pid);
      samples.push({ t: Date.now(), ...s });
      peak.rssMB = Math.max(peak.rssMB, s.rssMB);
      peak.processes = Math.max(peak.processes, s.processes);
      peak.browserMains = Math.max(peak.browserMains, s.browserMains);
      peak.ffmpegProcesses = Math.max(peak.ffmpegProcesses, s.ffmpegProcesses);
    }, 50);
    child.stdout.on("data", (d: Buffer) => {
      stdout = (stdout + d.toString("utf8")).slice(-4000);
    });
    child.stderr.on("data", (d: Buffer) => {
      stderr = (stderr + d.toString("utf8")).slice(-4000);
    });
    child.on("error", (err) => {
      clearInterval(timer);
      rejectPromise(err);
    });
    child.on("close", (code) => {
      clearInterval(timer);
      resolvePromise({
        exitCode: code ?? 1,
        wallMs: Date.now() - started,
        peak,
        samples,
        stdoutTail: stdout,
        stderrTail: stderr,
      });
    });
  });
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

// ---------------------------------------------------------------------
// Child roles: one real render sequence per engine
// ---------------------------------------------------------------------

function readArg(name: string): string {
  const idx = process.argv.indexOf(`--${name}`);
  if (idx < 0 || idx + 1 >= process.argv.length) throw new Error(`missing --${name}`);
  return process.argv[idx + 1];
}

interface PhaseMark {
  name: string;
  startedAt: number;
  endedAt: number;
}

async function phased<T>(phases: PhaseMark[], name: string, fn: () => Promise<T>): Promise<T> {
  const startedAt = Date.now();
  try {
    return await fn();
  } finally {
    phases.push({ name, startedAt, endedAt: Date.now() });
  }
}

async function remotionChild(): Promise<void> {
  const work = readArg("work");
  const resultPath = readArg("result");
  const jobDir = join(FIXTURES_ROOT, "modes", "powerpoint_graphic");
  const job = loadValidatedJob(jobDir);
  const phases: PhaseMark[] = [];
  const outputs: Array<{ path: string; bytes: number }> = [];
  const bundleDir = join(RUNTIME_STATE, "mg006-bundles");
  const bundleCacheWarmBefore = existsSync(bundleDir) && readdirSync(bundleDir).length > 0;

  const adapter = createRemotionAdapter({ outputDir: join(work, "remotion-out") });
  const still = await phased(phases, "stillFirst", () => adapter.renderStill(job, 75));
  outputs.push({ path: still.outputPaths[0], bytes: statSync(still.outputPaths[0]).size });

  // A fresh adapter on the warm bundle isolates browser startup plus
  // one frame from bundle building.
  const adapter2 = createRemotionAdapter({ outputDir: join(work, "remotion-out") });
  await phased(phases, "stillWarmBundle", () => adapter2.renderStill(job, 45));

  const preview = await phased(phases, "previewRender", () => adapter.renderPreview(job));
  outputs.push({ path: preview.outputPaths[0], bytes: statSync(preview.outputPaths[0]).size });

  writeFileSync(
    resultPath,
    JSON.stringify({ engine: "remotion", bundleCacheWarmBefore, phases, outputs }, null, 2) + "\n",
    "utf8"
  );
}

async function hyperframesChild(): Promise<void> {
  const work = readArg("work");
  const resultPath = readArg("result");
  // The Section 16 C05 fixture retargeted to Hyperframes, exactly as
  // the MG-005 suite builds it.
  const jobDir = join(work, "c05-hf-job");
  rmSync(jobDir, { recursive: true, force: true });
  cpSync(join(FIXTURES_ROOT, "modes", "powerpoint_graphic"), jobDir, { recursive: true });
  const scenePath = join(jobDir, "scenes", "bar-01.json");
  const scene = JSON.parse(readFileSync(scenePath, "utf8")) as Record<string, unknown>;
  scene.engine = "hyperframes";
  writeFileSync(scenePath, JSON.stringify(scene, null, 2) + "\n", "utf8");
  const manifestPath = join(jobDir, "manifest.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as {
    job_id: string;
    rendering: { default_engine: string };
  };
  manifest.rendering.default_engine = "hyperframes";
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  const job: ValidatedMotionJob = { jobDir, jobId: manifest.job_id, manifest: manifest as never };

  const phases: PhaseMark[] = [];
  const outputs: Array<{ path: string; bytes: number }> = [];
  const adapter = new HyperframesAdapter();
  const validation = await phased(phases, "validate", () => adapter.validate(job));
  if (!validation.valid) {
    throw new Error(`hyperframes validate of the fixture job failed: ${JSON.stringify(validation.findings)}`);
  }
  const still = await phased(phases, "stillSnapshot", () => adapter.renderStill(job, 75));
  const stillAbs = join(jobDir, still.outputPaths[0]);
  outputs.push({ path: stillAbs, bytes: statSync(stillAbs).size });

  const preview = await phased(phases, "previewRender", () => adapter.renderPreview(job));
  const previewAbs = join(jobDir, preview.outputPaths[0]);
  outputs.push({ path: previewAbs, bytes: statSync(previewAbs).size });

  writeFileSync(
    resultPath,
    JSON.stringify(
      { engine: "hyperframes", phases, outputs, jobWorkBytes: dirBytes(jobDir) },
      null,
      2
    ) + "\n",
    "utf8"
  );
}

// ---------------------------------------------------------------------
// Parent: run every measurement and assemble the record
// ---------------------------------------------------------------------

async function parent(): Promise<number> {
  rmSync(SCRATCH, { recursive: true, force: true });
  mkdirSync(SCRATCH, { recursive: true });
  const childEnv: NodeJS.ProcessEnv = {
    ...process.env,
    TMPDIR: TMP_SCRATCH,
    MOTION_RENDER_BUDGET_DIR: join(SCRATCH, "budget-ledger"),
  };
  const lock = JSON.parse(readFileSync(join(RUNTIME_STATE, "runtime-lock.json"), "utf8")) as {
    packages?: Record<string, string>;
    timestamp?: string;
  };
  const lockId = realpathSync(join(RUNTIME_STATE, "current")).split("/").pop() ?? null;

  const runChild = async (
    role: string,
    workName: string
  ): Promise<{ outcome: RunOutcome; result: Record<string, unknown> }> => {
    const work = join(SCRATCH, workName);
    mkdirSync(work, { recursive: true });
    const resultPath = join(work, "result.json");
    const outcome = await runSampled(
      process.execPath,
      [__filename, "--role", role, "--work", work, "--result", resultPath],
      childEnv
    );
    if (outcome.exitCode !== 0) {
      throw new Error(
        `${role} child exited ${outcome.exitCode}: ${outcome.stderrTail || outcome.stdoutTail}`
      );
    }
    return { outcome, result: JSON.parse(readFileSync(resultPath, "utf8")) as Record<string, unknown> };
  };

  const remotion = await runChild("remotion-child", "remotion");
  const hyperframes = await runChild("hyperframes-child", "hyperframes");

  // Align the parent's timed samples to the phases the children
  // reported, so each profile is sized from its own operation's peak
  // rather than from a whole-run blur.
  const phasePeaks = (
    run: { outcome: RunOutcome; result: Record<string, unknown> }
  ): Record<string, { peakRssMB: number; peakBrowserMains: number; peakProcesses: number; wallMs: number }> => {
    const marks = (run.result.phases ?? []) as PhaseMark[];
    const out: Record<string, { peakRssMB: number; peakBrowserMains: number; peakProcesses: number; wallMs: number }> = {};
    for (const mark of marks) {
      const inPhase = run.outcome.samples.filter((s) => s.t >= mark.startedAt - 100 && s.t <= mark.endedAt + 100);
      out[mark.name] = {
        peakRssMB: Math.round(Math.max(0, ...inPhase.map((s) => s.rssMB))),
        peakBrowserMains: Math.max(0, ...inPhase.map((s) => s.browserMains)),
        peakProcesses: Math.max(0, ...inPhase.map((s) => s.processes)),
        wallMs: mark.endedAt - mark.startedAt,
      };
    }
    return out;
  };

  // The encode share, isolated: re-encode each produced preview at
  // the render's own settings (libx264, crf 16, yuv420p).
  const encode: Record<string, unknown> = {};
  for (const [name, run] of [
    ["remotion", remotion],
    ["hyperframes", hyperframes],
  ] as const) {
    const outputs = run.result.outputs as Array<{ path: string; bytes: number }>;
    const video = outputs[outputs.length - 1];
    const encOut = join(SCRATCH, `${name}-reencode.mp4`);
    const outcome = await runSampled(
      "ffmpeg",
      ["-v", "error", "-i", video.path, "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-an", "-y", encOut],
      childEnv
    );
    if (outcome.exitCode !== 0) throw new Error(`ffmpeg re-encode for ${name} failed`);
    encode[name] = {
      sourceBytes: video.bytes,
      wallMs: outcome.wallMs,
      peakRssMB: Math.round(outcome.peak.rssMB),
      outputBytes: statSync(encOut).size,
    };
  }

  const record = {
    item: "MG-028",
    kind: "measured render capacity (feeds src/resources/profiles.ts)",
    generatedAt: new Date().toISOString(),
    machine: measureMachineCapacity(),
    runtime: {
      lockId,
      lockTimestamp: lock.timestamp ?? null,
      remotion: lock.packages?.remotion ?? null,
      hyperframes: lock.packages?.hyperframes ?? null,
    },
    method: {
      sampling:
        "parent polls the child render process tree every 50 ms via /proc: peak RSS sum, " +
        "peak browser main-process count (browser executable in cmdline, no --type= argument), " +
        "peak process count, wall time per child-reported phase",
      scenes:
        "Remotion: C05 fixture job (tests/fixtures/modes/powerpoint_graphic, 180 frames, " +
        "1920x1080, 30 fps): first still (bundle build included), warm-bundle still, preview " +
        "render. Hyperframes: the same fixture retargeted to the hyperframes engine: " +
        "validate (compositions + lint + check), still (snapshot), preview render (CLI " +
        "workers 1). Peaks are reported per phase from timestamp-aligned samples.",
      encode:
        "standalone ffmpeg libx264 crf 16 yuv420p re-encode of each produced preview, " +
        "timed and sampled the same way, isolating the encode share of a render",
      disk: "artifact byte sizes from the child reports; hyperframes job work dir total after render",
    },
    uncertainty: [
      "RSS sums count shared pages once per process, so tree peaks overstate true unique memory; the overstatement is the safe direction for a budget and is why profiles add a stated margin rather than trimming to the number",
      "50 ms sampling can miss spikes shorter than the interval; the 1.30 profile margin covers this",
      "this box is shared with other build work: wall times are load-dependent and inflate under contention, while RSS peaks are comparatively stable; treat peaks as +/-10 percent and wall times as upper bounds",
      "Remotion still timings depend on the bundle cache state, which the record states explicitly",
      "Hyperframes peaked at multiple Chromium main processes inside one render: the CLI multiplies browsers internally, which is why profiles are sized from whole-tree peaks and the budget counts operations, not browser processes",
    ],
    remotion: {
      child: remotion.result,
      wallMs: remotion.outcome.wallMs,
      peakRssMB: Math.round(remotion.outcome.peak.rssMB),
      peakProcesses: remotion.outcome.peak.processes,
      peakBrowserMains: remotion.outcome.peak.browserMains,
      phasePeaks: phasePeaks(remotion),
    },
    hyperframes: {
      child: hyperframes.result,
      wallMs: hyperframes.outcome.wallMs,
      peakRssMB: Math.round(hyperframes.outcome.peak.rssMB),
      peakProcesses: hyperframes.outcome.peak.processes,
      peakBrowserMains: hyperframes.outcome.peak.browserMains,
      phasePeaks: phasePeaks(hyperframes),
    },
    encode,
  };

  const text = JSON.stringify(record, null, 2) + "\n";
  if (process.argv.includes("--write-evidence")) {
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    writeFileSync(join(EVIDENCE_DIR, "measurements.json"), text, "utf8");
    console.log(`measurements written to ${join(EVIDENCE_DIR, "measurements.json")}`);
  } else {
    console.log(text);
  }
  return 0;
}

async function main(): Promise<number> {
  const roleIdx = process.argv.indexOf("--role");
  const role = roleIdx >= 0 ? process.argv[roleIdx + 1] : null;
  if (role === "remotion-child") {
    await remotionChild();
    return 0;
  }
  if (role === "hyperframes-child") {
    await hyperframesChild();
    return 0;
  }
  return parent();
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error((err as Error).message);
    process.exit(1);
  }
);
