// Cache and resume tests for MG-027 (Directive Section 6 MG-027,
// defect D-RESUME-KEY): content-addressed caching and crash-safe
// resume.
//
// These are REAL render tests. Two single-scene C05 fixture jobs
// (powerpoint_graphic and standalone_video modes) form a two-scene
// program; scene artifacts are produced by the production Remotion
// adapter (renderFinal for whole scenes, renderStill chunks plus an
// ffmpeg encode for the chunk phase), orchestrated by the MG-027
// cache session. Every session execution runs in a child process
// (tests/fixtures/cache/cache-driver.cjs) so the interrupt cases can
// SIGKILL a render mid-flight and resume it in a new process with
// only the state file as the handoff.
//
// Proven here, in order:
//   1. Key derivation: every input class moves the key, and the
//      changed class is named by digest comparison.
//   2. State store: atomic generations, torn-write recovery, the
//      legacy D-RESUME-KEY state shape rejected by name, a foreign
//      job's state rejected by name.
//   3. Interrupt and resume: kill mid-render; completed valid scenes
//      are NOT re-rendered (render-call counts and artifact mtimes);
//      the job still completes and assembles correctly.
//   4. Asset change: only the dependent scene re-renders; the stale
//      finding names the assets class; the old artifact is
//      quarantined, its content-addressed path gone.
//   5. Corruption and deletion: a byte-flipped artifact and a deleted
//      artifact are detected by verification and recomputed, never
//      silently used.
//   6. No frame leakage: after a data change, the assembled output's
//      frames hash-equal the current revision's scene artifacts and
//      differ from the previous revision where the data changed.
//   7. Chunk resume: a killed frame-chunk render resumes without
//      re-rendering completed chunks; after the verified encode the
//      intermediate frames are cleaned while registered review
//      evidence survives.
//   8. Failure bounds: repeated encode failures keep at most
//      MAX_FAILURE_RECORDS bounded records, retain the resume frames,
//      and the retained history survives a later success.
//
// Expected wall time is roughly ten minutes (six full 180-frame
// renders plus about fifty stills). Prerequisites: the shared
// runtime provisioned and the runtime package built (npm test runs
// the build first). Scratch lives in the shared runtime's gitignored
// .runtime dir; the evidence record lands in tests/evidence/mg027.
//
// Exit code 0 when every case passes, 1 otherwise.

import { spawn, spawnSync, type ChildProcess } from "node:child_process";
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
import { join, resolve } from "node:path";
import {
  CacheFindings,
  CacheStateStore,
  CachedRenderSession,
  MAX_FAILURE_LOG_CHARS,
  MAX_FAILURE_RECORDS,
  changedClasses,
  deriveJobCacheKey,
  deriveSceneCacheKey,
  hashCanonical,
  hashInputFiles,
  sha256Hex,
  type CacheFinding,
  type SceneKeyInputs,
  type SceneRenderContext,
  type SceneRenderOutcome,
  type SceneWorkUnit,
} from "../src/cache";
import { loadValidatedJob } from "../src/adapters";
import { createRemotionAdapter } from "../src/adapters/remotion";
import { loadC05Job } from "../src/remotion/job-props";
import { decodeFrameRgb, probeVideoFile } from "../src/remotion/decode";
import { compileTimeline } from "../src/timeline";

// ---------------------------------------------------------------------------
// Scaffolding
// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;
function report(ok: boolean, line: string, detail?: string): void {
  if (ok) passed += 1;
  else failed += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${line}`);
  if (!ok && detail) console.log(`  ${detail}`);
}

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function runtimeStateDir(): string {
  const override = process.env.MOTION_RUNTIME_STATE_DIR;
  if (override) return resolve(override);
  return resolve(
    __dirname, "..", "..", "..", "..",
    "shared-utils", "motion-render-runtime", ".runtime"
  );
}

function evidenceDir(): string {
  return resolve(__dirname, "..", "..", "..", "tests", "evidence", "mg027");
}

const SCRATCH = join(runtimeStateDir(), "mg027-tests");
const DRIVER = join(fixturesRoot(), "cache", "cache-driver.cjs");
const DIST_SRC = resolve(__dirname, "..", "src");
const JOB_ID = "mg027-cache-program";
const EXPORT_SETTINGS: Record<string, unknown> = {
  container: "mp4",
  videoProfile: "h264_opaque",
};

const evidence: Record<string, unknown> = {
  item: "MG-027",
  defect: "D-RESUME-KEY",
  generated_at: new Date().toISOString(),
  phases: {} as Record<string, unknown>,
};
function phaseEvidence(name: string, facts: Record<string, unknown>): void {
  (evidence.phases as Record<string, unknown>)[name] = facts;
}

function readJson(path: string): any {
  return JSON.parse(readFileSync(path, "utf8"));
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function hasFinding(findings: CacheFinding[], category: string, sceneId?: string): boolean {
  return findings.some(
    (f) => f.category === category && (sceneId === undefined || f.sceneId === sceneId)
  );
}

// ---------------------------------------------------------------------------
// Job staging and key-input derivation (the test's stand-in for a
// production orchestrator's input collection)
// ---------------------------------------------------------------------------

function stageJob(mode: string, name: string): string {
  const dir = join(SCRATCH, "jobs", name);
  cpSync(join(fixturesRoot(), "modes", mode), dir, { recursive: true });
  return dir;
}

/** Give scene B a declared image asset: the fixture SVG copied into
 * the job, declared in assets.json with its true sha256, and listed
 * in the scene spec's asset_ids, so the asset is a real, validated
 * dependency of the scene. */
function augmentJobB(jobDir: string): void {
  mkdirSync(join(jobDir, "assets"), { recursive: true });
  const svg = readFileSync(join(fixturesRoot(), "cache", "scene-b-logo.svg"));
  writeFileSync(join(jobDir, "assets", "logo.svg"), svg);
  const assetsPath = join(jobDir, "assets.json");
  const assets = readJson(assetsPath);
  assets.assets.push({
    id: "logo-b",
    path: "assets/logo.svg",
    sha256: createHash("sha256").update(svg).digest("hex"),
    kind: "svg",
    usage: "reference_only",
    rights_ref: "engineering-fixture",
    focal_point: null,
  });
  writeFileSync(assetsPath, `${JSON.stringify(assets, null, 2)}\n`);
  const specPath = join(jobDir, "scenes", "bar-01.json");
  const spec = readJson(specPath);
  spec.asset_ids = ["logo-b"];
  writeFileSync(specPath, `${JSON.stringify(spec, null, 2)}\n`);
}

let TIMING_HASH = "";
let COMPILER_VERSION = "";
let ADAPTER_VERSION = "";
let RUNTIME_LOCK_ID = "";

function deriveUnit(
  jobDir: string,
  sceneId: string,
  chunksTotal: number,
  artifactFileName: string
): { unit: SceneWorkUnit; key: string } {
  const job = loadValidatedJob(jobDir);
  const loaded = loadC05Job(job);
  const specRel = job.manifest.scenes[0].spec;
  const spec = readJson(join(jobDir, specRel));
  const dataRel = spec.data_path as string;
  const assetsDoc = readJson(join(jobDir, job.manifest.assets));
  const declared = new Set<string>((spec.asset_ids ?? []) as string[]);
  const assetHashes: Record<string, string> = {};
  for (const entry of assetsDoc.assets as { id: string; path: string }[]) {
    if (declared.has(entry.id)) {
      assetHashes[entry.id] = sha256File(join(jobDir, entry.path));
    }
  }
  const keyInputs: SceneKeyInputs = {
    sceneId,
    engine: "remotion",
    sceneSourceHash: sha256File(join(jobDir, specRel)),
    propsHash: hashCanonical(loaded.props),
    assetHashes,
    fontHashes: {
      [loaded.font.requirementId]: hashCanonical(
        loaded.font.files.map((f) => [f.weight, f.sha256])
      ),
    },
    dataHashes: { [dataRel]: sha256File(join(jobDir, dataRel)) },
    timingHash: TIMING_HASH,
    width: job.manifest.canvas.width,
    height: job.manifest.canvas.height,
    fps: job.manifest.canvas.fps,
    exportSettings: EXPORT_SETTINGS,
    adapterVersion: ADAPTER_VERSION,
    compilerVersion: COMPILER_VERSION,
    runtimeLockId: RUNTIME_LOCK_ID,
  };
  const unit: SceneWorkUnit = { sceneId, keyInputs, chunksTotal, artifactFileName };
  return { unit, key: deriveSceneCacheKey(keyInputs).key };
}

// ---------------------------------------------------------------------------
// Driver process management
// ---------------------------------------------------------------------------

interface DriverResult {
  code: number | null;
  signal: string | null;
  plan: any;
  report: any;
  stdout: string;
  stderr: string;
}

function parseDriverOutput(stdout: string): { plan: any; report: any } {
  let plan: any = null;
  let reportJson: any = null;
  for (const line of stdout.split("\n")) {
    if (line.startsWith("PLAN ")) plan = JSON.parse(line.slice(5));
    if (line.startsWith("REPORT ")) reportJson = JSON.parse(line.slice(7));
  }
  return { plan, report: reportJson };
}

function writeDriverConfig(name: string, cfg: Record<string, unknown>): string {
  const path = join(SCRATCH, `driver-${name}.json`);
  writeFileSync(path, JSON.stringify(cfg, null, 2));
  return path;
}

function driverConfig(init: {
  workDir: string;
  units: SceneWorkUnit[];
  scenes: Record<string, unknown>;
  callsLog: string;
}): Record<string, unknown> {
  return {
    distSrc: DIST_SRC,
    workDir: init.workDir,
    jobId: JOB_ID,
    units: init.units,
    scenes: init.scenes,
    callsLog: init.callsLog,
    renderOutBase: join(SCRATCH, "render-out"),
  };
}

function runDriverSync(configPath: string): DriverResult {
  const r = spawnSync("node", [DRIVER, configPath], {
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
    timeout: 1_200_000,
  });
  const { plan, report: parsed } = parseDriverOutput(r.stdout ?? "");
  return {
    code: r.status,
    signal: r.signal,
    plan,
    report: parsed,
    stdout: r.stdout ?? "",
    stderr: r.stderr ?? "",
  };
}

function spawnDriver(configPath: string): {
  child: ChildProcess;
  done: Promise<DriverResult>;
} {
  const child = spawn("node", [DRIVER, configPath], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout?.on("data", (d) => (stdout += String(d)));
  child.stderr?.on("data", (d) => (stderr += String(d)));
  const done = new Promise<DriverResult>((resolveDone) => {
    child.on("exit", (code, signal) => {
      const { plan, report: parsed } = parseDriverOutput(stdout);
      resolveDone({ code, signal, plan, report: parsed, stdout, stderr });
    });
  });
  return { child, done };
}

function readStateFile(workDir: string): any | null {
  try {
    return readJson(join(workDir, "render-state.json"));
  } catch {
    return null;
  }
}

async function waitForState(
  workDir: string,
  pred: (state: any) => boolean,
  timeoutMs: number
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const state = readStateFile(workDir);
    if (state && pred(state)) return true;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

/** Poll an arbitrary synchronous condition, for triggers that must
 * combine the state file with another durable record (the render
 * calls log), which waitForState cannot see. */
async function waitForCondition(
  pred: () => boolean,
  timeoutMs: number,
  intervalMs = 50
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (pred()) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return pred();
}

function countCalls(callsLog: string, line: string): number {
  if (!existsSync(callsLog)) return 0;
  return readFileSync(callsLog, "utf8")
    .split("\n")
    .filter((l) => l === line).length;
}

function frameHash(path: string, frame: number): string {
  return sha256Hex(decodeFrameRgb(path, frame, 1920, 1080));
}

function assemble(outPath: string, parts: string[]): { frames: number } {
  const listPath = `${outPath}.concat.txt`;
  writeFileSync(
    listPath,
    parts.map((p) => `file '${p.replace(/'/g, "'\\''")}'`).join("\n") + "\n"
  );
  const r = spawnSync(
    "ffmpeg",
    ["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", listPath, "-c", "copy", outPath],
    { encoding: "utf8" }
  );
  if (r.status !== 0) throw new Error(`ffmpeg concat failed: ${r.stderr}`);
  return { frames: probeVideoFile(outPath).frameCount };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  rmSync(SCRATCH, { recursive: true, force: true });
  mkdirSync(SCRATCH, { recursive: true });

  // ----- Setup: stage jobs, compile timing, probe the runtime. -----
  const jobA = stageJob("powerpoint_graphic", "job-a");
  const jobB = stageJob("standalone_video", "job-b");
  augmentJobB(jobB);

  const compiled = compileTimeline({
    jobId: JOB_ID,
    fps: 30,
    mode: "program",
    audioOwner: "none",
    scenes: [
      { id: "scene-a", durationFrames: 180 },
      { id: "scene-b", durationFrames: 180 },
    ],
    transitions: [],
  });
  report(compiled.ok, "setup: the two-scene program compiles through the MG-021 timeline compiler",
    compiled.ok ? undefined : JSON.stringify(compiled.findings));
  if (!compiled.ok) throw new Error("timeline compile failed; cannot derive timing hash");
  TIMING_HASH = hashCanonical({
    timeline: compiled.compiled.timeline,
    sidecar: compiled.compiled.sidecar,
  });
  COMPILER_VERSION = `mg021-timeline/${compiled.compiled.sidecar.schema_version}`;

  const probeAdapter = createRemotionAdapter({ outputDir: join(SCRATCH, "probe-out") });
  const runtimeEvidence = await probeAdapter.probeRuntime();
  ADAPTER_VERSION = runtimeEvidence.runtime.engineVersion ?? "";
  RUNTIME_LOCK_ID = runtimeEvidence.runtime.runtimeLockId ?? "";
  report(
    runtimeEvidence.status === "ready" && ADAPTER_VERSION !== "" && RUNTIME_LOCK_ID !== "",
    `setup: runtime probed ready (adapter ${ADAPTER_VERSION}, lock ${RUNTIME_LOCK_ID})`,
    runtimeEvidence.detail
  );
  if (runtimeEvidence.status !== "ready") throw new Error("runtime not ready");
  phaseEvidence("setup", {
    adapter_version: ADAPTER_VERSION,
    runtime_lock_id: RUNTIME_LOCK_ID,
    compiler_version: COMPILER_VERSION,
    timing_hash: TIMING_HASH,
    timing_total_frames: compiled.compiled.sidecar.total_frames,
  });

  const unitA = deriveUnit(jobA, "scene-a", 1, "scene.mp4");
  const unitB = deriveUnit(jobB, "scene-b", 1, "scene.mp4");
  report(unitA.key !== unitB.key, "setup: the two scenes derive distinct cache keys");

  // ----- Phase 1: key derivation. -----
  {
    const base = unitA.unit.keyInputs;
    const d0 = deriveSceneCacheKey(base);
    const dAgain = deriveSceneCacheKey(JSON.parse(JSON.stringify(base)) as SceneKeyInputs);
    report(d0.key === dAgain.key && deepEqual(d0.classDigests, dAgain.classDigests),
      "keys: derivation is deterministic (same inputs, same key)");

    const mutations: { name: string; change: (i: SceneKeyInputs) => SceneKeyInputs; cls: string }[] = [
      { name: "scene source", cls: "scene_source", change: (i) => ({ ...i, sceneSourceHash: sha256Hex("other-source") }) },
      { name: "props", cls: "props", change: (i) => ({ ...i, propsHash: sha256Hex("other-props") }) },
      { name: "assets", cls: "assets", change: (i) => ({ ...i, assetHashes: { "logo-b": sha256Hex("other-asset") } }) },
      { name: "fonts", cls: "fonts", change: (i) => ({ ...i, fontHashes: { "font-fixture-sans": sha256Hex("other-font") } }) },
      { name: "data", cls: "data", change: (i) => ({ ...i, dataHashes: { "data/bars.json": sha256Hex("other-data") } }) },
      { name: "compiled timing", cls: "timing", change: (i) => ({ ...i, timingHash: sha256Hex("other-timing") }) },
      { name: "dimensions", cls: "geometry", change: (i) => ({ ...i, width: 1280 }) },
      { name: "fps", cls: "geometry", change: (i) => ({ ...i, fps: 60 }) },
      { name: "export settings", cls: "export_settings", change: (i) => ({ ...i, exportSettings: { ...i.exportSettings, videoProfile: "h264_alpha" } }) },
      { name: "adapter version", cls: "versions", change: (i) => ({ ...i, adapterVersion: "0.0.0-other" }) },
      { name: "compiler version", cls: "versions", change: (i) => ({ ...i, compilerVersion: "mg021-timeline/9.9" }) },
      { name: "runtime lock", cls: "runtime", change: (i) => ({ ...i, runtimeLockId: "lock-000000000000" }) },
    ];
    for (const m of mutations) {
      const dm = deriveSceneCacheKey(m.change(base));
      const changed = changedClasses(d0.classDigests, dm.classDigests);
      report(
        dm.key !== d0.key && deepEqual(changed, [m.cls]),
        `keys: changing ${m.name} changes the key and names class ${m.cls}`,
        `changed=${JSON.stringify(changed)}`
      );
    }

    const jobKey1 = deriveJobCacheKey({
      jobId: JOB_ID,
      sceneKeys: [
        { sceneId: "scene-a", key: unitA.key },
        { sceneId: "scene-b", key: unitB.key },
      ],
      timingHash: TIMING_HASH,
      exportSettings: EXPORT_SETTINGS,
      runtimeLockId: RUNTIME_LOCK_ID,
    });
    const jobKey2 = deriveJobCacheKey({
      jobId: JOB_ID,
      sceneKeys: [
        { sceneId: "scene-a", key: deriveSceneCacheKey(mutations[0].change(base)).key },
        { sceneId: "scene-b", key: unitB.key },
      ],
      timingHash: TIMING_HASH,
      exportSettings: EXPORT_SETTINGS,
      runtimeLockId: RUNTIME_LOCK_ID,
    });
    report(jobKey1 !== jobKey2 && jobKey1.length === 64,
      "keys: the job key moves when any scene key moves");

    const present = hashInputFiles([
      { id: "logo", absPath: join(fixturesRoot(), "cache", "scene-b-logo.svg") },
    ]);
    const absent = hashInputFiles([
      { id: "logo", absPath: join(fixturesRoot(), "cache", "no-such-file.svg") },
    ]);
    report(
      present.findings.length === 0 &&
        present.hashes["logo"] === sha256File(join(fixturesRoot(), "cache", "scene-b-logo.svg")) &&
        absent.findings.length === 1 &&
        absent.findings[0].category === CacheFindings.InputAbsent &&
        absent.hashes["logo"] !== present.hashes["logo"],
      "keys: an absent input file hashes as an explicit sentinel with a MG_CACHE_INPUT_ABSENT finding"
    );
    phaseEvidence("key_derivation", { scene_a_key: unitA.key, scene_b_key: unitB.key, job_key: jobKey1 });
  }

  // ----- Phase 2: state store (torn writes, legacy shape, job mismatch). -----
  {
    const w3 = join(SCRATCH, "w3-store");
    const fakeInputs = (sceneId: string): SceneKeyInputs => ({
      sceneId,
      engine: "fake",
      sceneSourceHash: sha256Hex(`source-${sceneId}`),
      propsHash: sha256Hex("props"),
      assetHashes: {},
      fontHashes: {},
      dataHashes: {},
      timingHash: sha256Hex("timing"),
      width: 320,
      height: 240,
      fps: 30,
      exportSettings: { container: "txt" },
      adapterVersion: "fake-1",
      compilerVersion: "fake-1",
      runtimeLockId: "lock-fake",
    });
    const docUnit: SceneWorkUnit = {
      sceneId: "doc-scene",
      keyInputs: fakeInputs("doc-scene"),
      chunksTotal: 2,
      artifactFileName: "note.txt",
    };
    const fakeRenderer = async (ctx: SceneRenderContext): Promise<SceneRenderOutcome> => {
      await ctx.reportChunkComplete(0);
      await ctx.reportChunkComplete(1);
      writeFileSync(ctx.artifactPath, "cache me if you can\n");
      return { probe: null };
    };
    const s1 = await CachedRenderSession.open({ workDir: w3, jobId: "job-store", units: [docUnit] });
    const r1 = await s1.run(() => fakeRenderer);
    const stateAfterRun = readStateFile(w3);
    report(
      r1.ok && stateAfterRun !== null &&
        stateAfterRun.scenes["doc-scene"].status === "complete" &&
        stateAfterRun.scenes["doc-scene"].artifact.sha256 ===
          sha256Hex("cache me if you can\n") &&
        stateAfterRun.generation >= 4,
      "store: a completed run persists a verified artifact record (generation advances per atomic save)",
      JSON.stringify(stateAfterRun?.scenes?.["doc-scene"] ?? null)
    );
    const fullGeneration = stateAfterRun.generation as number;

    // Torn write: truncate the current state mid-document. The
    // previous generation must be recovered, losing at most the last
    // update (the completion save), never the chunk progress.
    const statePath = join(w3, "render-state.json");
    const bytes = readFileSync(statePath);
    writeFileSync(statePath, bytes.subarray(0, Math.floor(bytes.length * 0.6)));
    const store2 = new CacheStateStore(w3);
    const recovered = store2.load();
    report(
      recovered.state !== null &&
        hasFinding(recovered.findings, CacheFindings.StateTornRecovered) &&
        recovered.state.generation === fullGeneration - 1 &&
        recovered.state.scenes["doc-scene"].status === "in_progress" &&
        deepEqual(recovered.state.scenes["doc-scene"].chunksCompleted, [0, 1]),
      "store: a torn (truncated) state file recovers the previous generation with MG_CACHE_STATE_TORN_RECOVERED",
      JSON.stringify(recovered.findings)
    );

    // Crash between the two renames: main absent, prev intact.
    rmSync(statePath);
    const store3 = new CacheStateStore(w3);
    const recovered2 = store3.load();
    report(
      recovered2.state !== null &&
        hasFinding(recovered2.findings, CacheFindings.StateTornRecovered),
      "store: a missing main state file (crash mid-save) recovers the previous generation"
    );

    // Both generations unreadable: named finding, empty state.
    writeFileSync(statePath, "{not json");
    writeFileSync(join(w3, "render-state.json.prev"), "{also not json");
    const store4 = new CacheStateStore(w3);
    const dead = store4.load();
    report(
      dead.state === null && hasFinding(dead.findings, CacheFindings.StateUnreadable),
      "store: unreadable generations yield MG_CACHE_STATE_UNREADABLE and an empty state, never a guess"
    );

    // The legacy D-RESUME-KEY shape: same scene id and fps, no
    // content keys. It must be rejected by name and plan a render.
    const w4 = join(SCRATCH, "w4-legacy");
    mkdirSync(w4, { recursive: true });
    writeFileSync(
      join(w4, "render-state.json"),
      readFileSync(join(fixturesRoot(), "cache", "legacy-state.json"), "utf8")
    );
    const legacySession = await CachedRenderSession.open({
      workDir: w4, jobId: "job-store", units: [docUnit],
    });
    const legacyPlan = legacySession.plan();
    report(
      hasFinding(legacySession.openFindings, CacheFindings.StateLegacyShape) &&
        legacyPlan[0].action === "render",
      "store: a legacy-shaped state file (scene + fps + doneThrough only) is rejected with MG_CACHE_STATE_LEGACY_SHAPE"
    );

    // A different job's state in the same directory is not reused.
    const w5 = join(SCRATCH, "w5-job");
    const sA = await CachedRenderSession.open({ workDir: w5, jobId: "job-one", units: [docUnit] });
    await sA.run(() => fakeRenderer);
    const sB = await CachedRenderSession.open({ workDir: w5, jobId: "job-two", units: [docUnit] });
    report(
      hasFinding(sB.openFindings, CacheFindings.StateJobMismatch) &&
        sB.plan()[0].action === "render",
      "store: another job's state is rejected with MG_CACHE_STATE_JOB_MISMATCH"
    );
    phaseEvidence("state_store", {
      full_generation: fullGeneration,
      recovered_generation: recovered.state?.generation ?? null,
    });
  }

  // ----- Phases 3 to 6: the two-scene program in workdir W1. -----
  const w1 = join(SCRATCH, "w1-program");
  const calls1 = join(SCRATCH, "calls-w1.log");
  writeFileSync(calls1, "");
  const w1Config = (units: SceneWorkUnit[], name: string): string =>
    writeDriverConfig(
      name,
      driverConfig({
        workDir: w1,
        units,
        scenes: {
          "scene-a": { kind: "final", jobDir: jobA },
          "scene-b": { kind: "final", jobDir: jobB },
        },
        callsLog: calls1,
      })
    );

  // ----- Phase 3: interrupt mid-render, then resume. -----
  let rev1Hashes = { a75: "", b75: "" };
  {
    const cfg = w1Config([unitA.unit, unitB.unit], "w1-kill");
    const { child, done } = spawnDriver(cfg);
    // The kill must land while scene-b's render is genuinely in
    // flight, and two durable records describe that moment with
    // different write ordering. The cache session persists scene-b
    // "in_progress" BEFORE it invokes the renderer (src/cache/
    // session.ts runScene saves the state, then calls the
    // renderer), while the driver appends "render-start scene-b"
    // only after its job load and validation complete
    // (tests/fixtures/cache/cache-driver.cjs), and the state file
    // records scene-b complete only after the artifact is hashed
    // and probed, which is after "render-done scene-b" is appended.
    // A trigger waiting on the state file alone can therefore fire
    // inside the gap before the render-start append: the state is
    // already correct, but the calls log legitimately reads
    // (done-a 1, start-b 0, done-b 0) for a healthy cache layer.
    // The window is as long as the driver's job load takes, which
    // grows with validation work and CPU contention. The trigger
    // below waits for BOTH records to agree that scene-b's render
    // has begun, then kills on a tight 50 ms poll; scene-b's render
    // runs about a minute, so the kill cannot drift to its end.
    const reached = await waitForCondition(
      () => {
        const s = readStateFile(w1);
        return (
          s !== null &&
          s.scenes["scene-a"]?.status === "complete" &&
          s.scenes["scene-b"]?.status === "in_progress" &&
          countCalls(calls1, "render-start scene-b") === 1
        );
      },
      600_000,
      50
    );
    report(reached, "interrupt: the render reached scene-a complete with scene-b in progress");
    if (reached) child.kill("SIGKILL");
    const killed = await done;
    report(
      killed.signal === "SIGKILL",
      "interrupt: the driver process was killed mid-render (SIGKILL)",
      `code=${String(killed.code)} signal=${String(killed.signal)} stderr=${killed.stderr.slice(0, 300)}`
    );
    const stateAfterKill = readStateFile(w1);
    report(
      stateAfterKill !== null &&
        stateAfterKill.scenes["scene-a"].status === "complete" &&
        stateAfterKill.scenes["scene-b"].status === "in_progress",
      "interrupt: the state file parses after the kill (atomic writes) and records the true progress"
    );
    report(
      countCalls(calls1, "render-done scene-a") === 1 &&
        countCalls(calls1, "render-start scene-b") === 1 &&
        countCalls(calls1, "render-done scene-b") === 0,
      "interrupt: render calls at kill time are exactly scene-a done, scene-b started, scene-b not done",
      `done-a=${countCalls(calls1, "render-done scene-a")} start-b=${countCalls(calls1, "render-start scene-b")} done-b=${countCalls(calls1, "render-done scene-b")}`
    );

    const aRecord = stateAfterKill.scenes["scene-a"].artifact;
    const aArtifactPath = join(w1, aRecord.path);
    const aMtimeBefore = statSync(aArtifactPath, { bigint: true }).mtimeNs;
    const aShaBefore = aRecord.sha256 as string;

    const resumed = runDriverSync(w1Config([unitA.unit, unitB.unit], "w1-resume"));
    const byId = new Map<string, any>(
      (resumed.report?.results ?? []).map((r: any) => [r.sceneId, r])
    );
    report(
      resumed.code === 0 && resumed.report?.ok === true &&
        byId.get("scene-a")?.action === "reused" &&
        byId.get("scene-b")?.action === "rendered",
      "resume: the job completes; scene-a is reused and only scene-b renders",
      resumed.stderr.slice(0, 300)
    );
    report(
      countCalls(calls1, "render-done scene-a") === 1 &&
        statSync(aArtifactPath, { bigint: true }).mtimeNs === aMtimeBefore &&
        sha256File(aArtifactPath) === aShaBefore,
      "resume: scene-a was NOT re-rendered (render-call count still 1, artifact mtime and hash unchanged)"
    );

    // Register the adapter-rendered poster as review evidence; later
    // phases prove the record persists across revisions and cleanups.
    const posterPath = join(SCRATCH, "render-out", "scene-a", "renders", "remotion", "poster-f150.png");
    const session = await CachedRenderSession.open({
      workDir: w1, jobId: JOB_ID, units: [unitA.unit, unitB.unit],
    });
    const reviewDir = join(w1, "review");
    mkdirSync(reviewDir, { recursive: true });
    const reviewCopy = join(reviewDir, "scene-a-poster-f150.png");
    cpSync(posterPath, reviewCopy);
    session.registerReviewEvidence(reviewCopy, "poster");
    const stateWithReview = readStateFile(w1);
    report(
      Array.isArray(stateWithReview.reviewEvidence) &&
        stateWithReview.reviewEvidence.length === 1 &&
        stateWithReview.reviewEvidence[0].sha256 === sha256File(reviewCopy),
      "resume: review evidence is registered in state with its hash"
    );

    const aPath = session.artifactPathFor("scene-a");
    const bPath = session.artifactPathFor("scene-b");
    if (!aPath || !bPath) throw new Error("artifact paths missing after resume");
    const assembled = assemble(join(SCRATCH, "program-rev1.mp4"), [aPath, bPath]);
    const aArt75 = frameHash(aPath, 75);
    const bArt75 = frameHash(bPath, 75);
    const out = join(SCRATCH, "program-rev1.mp4");
    rev1Hashes = { a75: frameHash(out, 75), b75: frameHash(out, 255) };
    report(
      assembled.frames === 360 &&
        frameHash(out, 0) === frameHash(aPath, 0) &&
        frameHash(out, 179) === frameHash(aPath, 179) &&
        frameHash(out, 180) === frameHash(bPath, 0) &&
        rev1Hashes.a75 === aArt75 &&
        rev1Hashes.b75 === bArt75,
      "resume: the assembled program is 360 frames and every sampled frame hash-matches its scene artifact (no foreign frames)",
      `frames=${assembled.frames}`
    );
    phaseEvidence("interrupt_resume", {
      scene_a_key: unitA.key,
      scene_b_key: unitB.key,
      scene_a_artifact_sha256: aShaBefore,
      program_frames: assembled.frames,
    });
  }

  // ----- Phase 4: change one asset; only the dependent scene re-renders. -----
  {
    const svgPath = join(jobB, "assets", "logo.svg");
    const changedSvg = readFileSync(svgPath, "utf8").replace("#C04A26", "#192A38");
    writeFileSync(svgPath, changedSvg);
    const assetsPath = join(jobB, "assets.json");
    const assets = readJson(assetsPath);
    assets.assets[0].sha256 = sha256File(svgPath);
    writeFileSync(assetsPath, `${JSON.stringify(assets, null, 2)}\n`);

    const unitB2 = deriveUnit(jobB, "scene-b", 1, "scene.mp4");
    const unitAAgain = deriveUnit(jobA, "scene-a", 1, "scene.mp4");
    report(
      unitB2.key !== unitB.key && unitAAgain.key === unitA.key,
      "asset change: scene-b's key moves; scene-a's key is untouched"
    );
    const run = runDriverSync(w1Config([unitA.unit, unitB2.unit], "w1-asset"));
    const planB = (run.plan ?? []).find((p: any) => p.sceneId === "scene-b");
    const planA = (run.plan ?? []).find((p: any) => p.sceneId === "scene-a");
    const stale = (planB?.findings ?? []).find(
      (f: CacheFinding) => f.category === CacheFindings.StaleRevision
    );
    report(
      stale !== undefined && stale.message.includes("assets") &&
        planA?.action === "reuse" && planB?.action === "render",
      "asset change: the plan rejects scene-b's recorded state with MG_CACHE_STALE_REVISION naming the assets class (the D-RESUME-KEY case: same scene id and fps, different asset)",
      JSON.stringify(planB?.findings ?? null)
    );
    report(
      run.code === 0 && run.report?.ok === true &&
        countCalls(calls1, "render-done scene-a") === 1 &&
        countCalls(calls1, "render-done scene-b") === 2,
      "asset change: only scene-b re-rendered (scene-a render count still 1)"
    );
    const quarantineDir = join(w1, "quarantine", "scene-b");
    const quarantined = existsSync(quarantineDir) ? readdirSync(quarantineDir) : [];
    report(
      quarantined.length === 1 &&
        quarantined[0].startsWith(unitB.key) &&
        !existsSync(join(w1, "artifacts", "scene-b", unitB.key, "scene.mp4")),
      "asset change: the stale artifact was quarantined under its old key and its content-addressed path is gone"
    );
    phaseEvidence("asset_change", { old_scene_b_key: unitB.key, new_scene_b_key: unitB2.key });

    // ----- Phase 5: corrupt one artifact, delete another. -----
    const stateNow = readStateFile(w1);
    const aArtifactPath = join(w1, stateNow.scenes["scene-a"].artifact.path);
    const bArtifactPath = join(w1, stateNow.scenes["scene-b"].artifact.path);
    const aBytes = readFileSync(aArtifactPath);
    aBytes[Math.floor(aBytes.length / 2)] = aBytes[Math.floor(aBytes.length / 2)] ^ 0xff;
    writeFileSync(aArtifactPath, aBytes);
    rmSync(bArtifactPath);
    const run2 = runDriverSync(w1Config([unitA.unit, unitB2.unit], "w1-corrupt"));
    const plan2A = (run2.plan ?? []).find((p: any) => p.sceneId === "scene-a");
    const plan2B = (run2.plan ?? []).find((p: any) => p.sceneId === "scene-b");
    report(
      hasFinding(plan2A?.findings ?? [], CacheFindings.ArtifactCorrupt, "scene-a") &&
        hasFinding(plan2B?.findings ?? [], CacheFindings.ArtifactMissing, "scene-b") &&
        plan2A?.action === "render" && plan2B?.action === "render",
      "corruption: a byte-flipped artifact is MG_CACHE_ARTIFACT_CORRUPT and a deleted one MG_CACHE_ARTIFACT_MISSING; both plan as renders",
      JSON.stringify({ a: plan2A?.findings, b: plan2B?.findings })
    );
    report(
      run2.code === 0 && run2.report?.ok === true &&
        countCalls(calls1, "render-done scene-a") === 2 &&
        countCalls(calls1, "render-done scene-b") === 3 &&
        sha256File(aArtifactPath) === readStateFile(w1).scenes["scene-a"].artifact.sha256,
      "corruption: both scenes were recomputed and the new artifacts verify against their records"
    );
    phaseEvidence("corruption", {
      scene_a_renders: countCalls(calls1, "render-done scene-a"),
      scene_b_renders: countCalls(calls1, "render-done scene-b"),
    });

    // ----- Phase 6: change scene-b data; prove no frame leaks. -----
    const bPathNow = join(w1, readStateFile(w1).scenes["scene-b"].artifact.path);
    const b75Before = frameHash(bPathNow, 75);
    const barsPath = join(jobB, "data", "bars.json");
    const bars = readJson(barsPath);
    bars.rows[2].value = 15;
    writeFileSync(barsPath, `${JSON.stringify(bars, null, 2)}\n`);
    const unitB3 = deriveUnit(jobB, "scene-b", 1, "scene.mp4");
    const run3 = runDriverSync(w1Config([unitA.unit, unitB3.unit], "w1-data"));
    const plan3B = (run3.plan ?? []).find((p: any) => p.sceneId === "scene-b");
    const stale3 = (plan3B?.findings ?? []).find(
      (f: CacheFinding) => f.category === CacheFindings.StaleRevision
    );
    report(
      stale3 !== undefined && stale3.message.includes("data"),
      "data change: scene-b's stale finding names the data class",
      JSON.stringify(plan3B?.findings ?? null)
    );
    const session3 = await CachedRenderSession.open({
      workDir: w1, jobId: JOB_ID, units: [unitA.unit, unitB3.unit],
    });
    const aPath3 = session3.artifactPathFor("scene-a");
    const bPath3 = session3.artifactPathFor("scene-b");
    if (!aPath3 || !bPath3) throw new Error("artifact paths missing after data phase");
    const out2 = join(SCRATCH, "program-rev2.mp4");
    const assembled2 = assemble(out2, [aPath3, bPath3]);
    const out2B75 = frameHash(out2, 255);
    report(
      run3.code === 0 && run3.report?.ok === true &&
        countCalls(calls1, "render-done scene-a") === 2 &&
        assembled2.frames === 360 &&
        out2B75 === frameHash(bPath3, 75) &&
        out2B75 !== b75Before &&
        frameHash(out2, 75) === rev1Hashes.a75,
      "no leakage: the new output's scene-b frames hash-match the NEW scene-b artifact, differ from the previous revision's frames, and scene-a frames are pixel-identical to revision 1",
      `out2B75=${out2B75.slice(0, 12)} before=${b75Before.slice(0, 12)}`
    );
    report(
      session3.verifyReviewEvidence().length === 0 &&
        readStateFile(w1).reviewEvidence.length === 1,
      "no leakage: registered review evidence survived every revision change intact"
    );
    phaseEvidence("data_change_no_leak", {
      scene_b_key_after_data_change: unitB3.key,
      frame75_before: b75Before,
      frame75_after: out2B75,
    });
  }

  // ----- Phase 7: frame-chunk resume, cleanup, review evidence. -----
  const w2 = join(SCRATCH, "w2-chunks");
  const calls2 = join(SCRATCH, "calls-w2.log");
  writeFileSync(calls2, "");
  const jobA2 = stageJob("powerpoint_graphic", "job-a2");
  const unitF = deriveUnit(jobA2, "scene-frames", 3, "segment.mp4");
  const chunkDirF = join(w2, "chunks", "scene-frames", unitF.key);
  const w2Config = (name: string): string =>
    writeDriverConfig(
      name,
      driverConfig({
        workDir: w2,
        units: [unitF.unit],
        scenes: {
          "scene-frames": { kind: "stills", jobDir: jobA2, frames: 30, chunkSize: 10 },
        },
        callsLog: calls2,
      })
    );
  {
    const { child, done } = spawnDriver(w2Config("w2-kill"));
    const reached = await waitForState(
      w2,
      (s) =>
        s.scenes["scene-frames"]?.status === "in_progress" &&
        deepEqual(s.scenes["scene-frames"]?.chunksCompleted, [0]),
      600_000
    );
    report(reached, "chunks: the chunked render recorded chunk 0 complete before the kill");
    if (reached) child.kill("SIGKILL");
    const killed = await done;
    const framesOnDisk = existsSync(chunkDirF) ? readdirSync(chunkDirF) : [];
    report(
      killed.signal === "SIGKILL" &&
        framesOnDisk.filter((f) => f.startsWith("frame-")).length === 10 &&
        existsSync(join(chunkDirF, "frame-0000.png")) &&
        existsSync(join(chunkDirF, "frame-0009.png")) &&
        !existsSync(join(chunkDirF, "frame-0010.png")) &&
        existsSync(join(chunkDirF, "review-f45.png")),
      "chunks: after SIGKILL exactly chunk 0's frames (0 to 9) and the review still survive on disk",
      `signal=${String(killed.signal)} files=${framesOnDisk.length}`
    );

    // Register the review still before resuming, so the completion
    // cleanup must prove it preserves registered evidence even
    // inside the chunk directory it cleans.
    const session = await CachedRenderSession.open({
      workDir: w2, jobId: JOB_ID, units: [unitF.unit],
    });
    session.registerReviewEvidence(join(chunkDirF, "review-f45.png"), "proof_still");
    const stillsBefore = readFileSync(calls2, "utf8")
      .split("\n")
      .filter((l) => l.startsWith("still scene-frames ")).length;

    const resumed = runDriverSync(w2Config("w2-resume"));
    const logAfter = readFileSync(calls2, "utf8").split("\n");
    const stillLines = logAfter.filter((l) => l.startsWith("still scene-frames "));
    const stillFrames = stillLines.map((l) => Number(l.split(" ")[2]));
    const stateF = readStateFile(w2);
    report(
      resumed.code === 0 && resumed.report?.ok === true &&
        logAfter.includes("skip-chunk scene-frames 0") &&
        stillsBefore === 10 && stillFrames.length === 30 &&
        Math.min(...stillFrames.slice(10)) >= 10,
      "chunks: resume skipped chunk 0 entirely (no frame 0 to 9 re-rendered) and rendered only frames 10 to 29",
      `stills total=${stillFrames.length}`
    );
    report(
      stateF.scenes["scene-frames"].status === "complete" &&
        stateF.scenes["scene-frames"].artifact.probe.frames === 30 &&
        stateF.scenes["scene-frames"].artifact.probe.width === 1920,
      "chunks: the resumed scene completed as a verified 30-frame 1920x1080 segment"
    );
    const framesAfter = existsSync(chunkDirF) ? readdirSync(chunkDirF) : [];
    report(
      framesAfter.filter((f) => f.startsWith("frame-")).length === 0 &&
        framesAfter.includes("review-f45.png") &&
        session.verifyReviewEvidence().length === 0 &&
        existsSync(join(chunkDirF, "review-f45.png")),
      "cleanup: after the verified encode, all intermediate frames were cleaned and the registered review still survived inside the cleaned directory"
    );
    phaseEvidence("chunk_resume", {
      scene_frames_key: unitF.key,
      stills_rendered_total: stillFrames.length,
      segment_probe: stateF.scenes["scene-frames"].artifact.probe,
    });
  }

  // ----- Phase 8: bounded failure evidence; resume frames survive. -----
  {
    const barsPath = join(jobA2, "data", "bars.json");
    const bars = readJson(barsPath);
    bars.rows[2].value = 20;
    writeFileSync(barsPath, `${JSON.stringify(bars, null, 2)}\n`);
    const unitF2 = deriveUnit(jobA2, "scene-frames", 3, "segment.mp4");
    const chunkDirF2 = join(w2, "chunks", "scene-frames", unitF2.key);
    const failingRenderer = async (ctx: SceneRenderContext): Promise<SceneRenderOutcome> => {
      for (let c = 0; c < 3; c += 1) {
        writeFileSync(join(ctx.chunkDir, `chunk-${c}.bin`), `fake frame chunk ${c}\n`);
        await ctx.reportChunkComplete(c);
      }
      const err = new Error("ffmpeg encode failed: Invalid argument (synthetic encode failure)") as Error & { logTail?: string };
      err.logTail = `ENCODE-LOG ${"x".repeat(5000)}`;
      throw err;
    };
    const lengths: number[] = [];
    let allFailed = true;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const s = await CachedRenderSession.open({ workDir: w2, jobId: JOB_ID, units: [unitF2.unit] });
      const r = await s.run(() => failingRenderer);
      if (r.ok) allFailed = false;
      lengths.push(readStateFile(w2).scenes["scene-frames"].failures.length);
    }
    const failedState = readStateFile(w2);
    const lastFailure = failedState.scenes["scene-frames"].failures.at(-1);
    report(
      allFailed && deepEqual(lengths, [1, 2, 3, 3]) &&
        failedState.scenes["scene-frames"].status === "failed" &&
        lastFailure.logTail.length === MAX_FAILURE_LOG_CHARS &&
        failedState.scenes["scene-frames"].failures.length === MAX_FAILURE_RECORDS,
      "failure evidence: four failed attempts retain exactly MAX_FAILURE_RECORDS bounded records with log tails capped",
      `lengths=${JSON.stringify(lengths)}`
    );
    report(
      existsSync(join(chunkDirF2, "chunk-0.bin")) &&
        existsSync(join(chunkDirF2, "chunk-1.bin")) &&
        existsSync(join(chunkDirF2, "chunk-2.bin")),
      "failure evidence: the frames needed for resume survive every encode failure (no cleanup on failure)"
    );

    const workingFakeRenderer = async (ctx: SceneRenderContext): Promise<SceneRenderOutcome> => {
      for (let c = 0; c < 3; c += 1) await ctx.reportChunkComplete(c);
      const enc = spawnSync(
        "ffmpeg",
        ["-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0xC04A26:s=320x240:r=30:d=0.1",
         "-frames:v", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", ctx.artifactPath],
        { encoding: "utf8" }
      );
      if (enc.status !== 0) throw new Error(`lavfi encode failed: ${enc.stderr}`);
      const p = probeVideoFile(ctx.artifactPath);
      return {
        probe: {
          kind: "video" as const,
          width: p.width,
          height: p.height,
          fpsNumerator: p.fpsNumerator,
          fpsDenominator: p.fpsDenominator,
          frames: p.frameCount,
        },
      };
    };
    const sFinal = await CachedRenderSession.open({ workDir: w2, jobId: JOB_ID, units: [unitF2.unit] });
    const rFinal = await sFinal.run(() => workingFakeRenderer);
    const finalState = readStateFile(w2);
    report(
      rFinal.ok &&
        finalState.scenes["scene-frames"].status === "complete" &&
        finalState.scenes["scene-frames"].failures.length === MAX_FAILURE_RECORDS &&
        !existsSync(join(chunkDirF2, "chunk-0.bin")),
      "failure evidence: a later success completes the scene, keeps the bounded failure history, and only then cleans the chunk files"
    );
    phaseEvidence("failure_bounds", {
      failure_record_lengths_by_attempt: lengths,
      log_tail_cap: MAX_FAILURE_LOG_CHARS,
    });
  }

  // ----- Evidence record and verdict. -----
  evidence.counts = { passed, failed };
  mkdirSync(evidenceDir(), { recursive: true });
  writeFileSync(
    join(evidenceDir(), "record.json"),
    `${JSON.stringify(evidence, null, 2)}\n`
  );
  console.log(`\nCache: ${passed}/${passed + failed} checks passed, ${failed} failed.`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  try {
    evidence.fatal = String(err);
    evidence.counts = { passed, failed };
    mkdirSync(evidenceDir(), { recursive: true });
    writeFileSync(join(evidenceDir(), "record.json"), `${JSON.stringify(evidence, null, 2)}\n`);
  } catch {
    // Evidence write is best effort on a fatal path.
  }
  process.exit(1);
});
