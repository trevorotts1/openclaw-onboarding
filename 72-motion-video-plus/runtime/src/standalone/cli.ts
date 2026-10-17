// Standalone motion-video build driver (Directive MG-039).
//
// This CLI is the TypeScript half of the standalone orchestration in
// scripts/build_standalone.py. It composes shipped layers only; it
// implements no rendering, routing, or proof logic of its own:
//
// - compile: MG-021's compileTimeline over a compile-input document
//   the Python orchestrator derives from the job package (manifest,
//   scene specs, build plan, and the MG-025 narration record through
//   the same sample-to-frame arithmetic as
//   orchestrator/narration.ts toNarrationSegments).
// - render: one single-scene shell job per program scene, rendered
//   through the shipped adapters. C05 shells go through the full
//   MotionDispatcher path (contracts validation, MG-018 catalog,
//   routing, fixture approval), exactly like the MG-006 suite's C05
//   job. C01 shells are built as ValidatedMotionJob objects and driven
//   through the Hyperframes adapter directly, exactly like the MG-005
//   suite, because the dispatcher's contracts gate refuses mg005-1
//   scene specs on this base (the canonical scene $def is closed on
//   C05; the MG-017/MG-018 catalog divergence). The routing decision
//   for those scenes is still computed with the shipped routing
//   module and recorded. Per-scene routing decisions, render
//   receipts, and motion observations land in render-receipt.json.
// - proof: MG-032's evaluateMotionProof over each C05 scene segment
//   (case documents from the job package, coverage bundles built by
//   the shipped scripts/critique_bundle.py), plus the C01 proof
//   evidence gathered during render (adapter inspectMotion for the
//   reveal, decoded-still measurement for the nested detail, the
//   MG-005 method). The aggregate record is written as
//   motion-proof.json in the MG-032 record shape family.
//
// The driver never assembles the program: assembly is MG-022's
// scripts/assemble.py, driven by the Python orchestrator.

import { execFile, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { promisify } from "node:util";
import {
  createRegistry,
  loadCapabilityMatrix,
  MotionDispatcher,
  routeOrThrow,
} from "../adapters";
import type { Approval, Manifest } from "../validation/generated-types";
import type { SceneRequirement } from "../adapters/routing";
import { createHyperframesAdapter, HyperframesAdapter } from "../adapters/hyperframes";
import { createRemotionAdapter } from "../adapters/remotion";
import { evaluateMotionProof } from "../motion-proof";
import { decodePng, measureColorFraction } from "../hyperframes/measure";
import { compileTimeline } from "../timeline";

const execFileP = promisify(execFile);

// ---------------------------------------------------------------------
// Roots. The driver runs from dist/src/standalone; the repo root is
// the first ancestor holding the shared runtime tree.
// ---------------------------------------------------------------------

function findRepoRoot(): string {
  let dir = __dirname;
  for (let i = 0; i < 10; i += 1) {
    if (existsSync(join(dir, "shared-utils", "motion-render-runtime"))) {
      return dir;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error("could not locate the repo root (shared-utils/motion-render-runtime not found above the driver)");
}

const REPO_ROOT = findRepoRoot();
const SKILL_DIR = join(REPO_ROOT, "72-motion-video-plus");
const RUNTIME_ROOT = join(REPO_ROOT, "shared-utils", "motion-render-runtime");
const TMP_SCRATCH = join(REPO_ROOT, ".scratch", "tmp");
mkdirSync(TMP_SCRATCH, { recursive: true });
process.env.TMPDIR = TMP_SCRATCH;

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf8")) as T;
}

function writeJson(path: string, doc: unknown): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(doc, null, 2) + "\n", "utf8");
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function argValue(argv: string[], flag: string): string {
  const idx = argv.indexOf(flag);
  if (idx < 0 || idx + 1 >= argv.length) {
    throw new Error(`missing required argument ${flag}`);
  }
  return argv[idx + 1];
}

async function ffprobeMedia(path: string): Promise<{ frames: number; width: number; height: number }> {
  const { stdout } = await execFileP("ffprobe", [
    "-v", "error", "-count_frames", "-select_streams", "v:0",
    "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", path,
  ]);
  const parsed = JSON.parse(stdout) as { streams: Array<{ width: number; height: number; nb_read_frames: string }> };
  const s = parsed.streams[0];
  return { frames: parseInt(s.nb_read_frames, 10), width: s.width, height: s.height };
}

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg039-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "mg039-fixture",
    artifact_refs: [],
    actor_id: "mg039-standalone-build",
    source_event_ref: null,
    authority_status: "not_verified",
  } as Approval;
}

// The storyboard-representation to routing-kind map, mirrored from
// adapters/dispatch.ts deriveSceneRequirements (not exported there).
const REPRESENTATION_KIND: Record<string, SceneRequirement["kind"]> = {
  chart: "data_chart",
  image: "editorial_image",
  diagram: "parameterized_infographic",
  mechanism: "spatial_reveal",
  typography: "generic",
};

interface SceneEntry {
  id: string;
  spec: string;
}

interface PackageDocs {
  jobDir: string;
  manifest: Manifest & { scenes: SceneEntry[] };
  storyboard: { id: string; beats: Array<Record<string, unknown>> };
  buildPlan: {
    scenes: Array<{ id: string; role: string; shot_scale: string }>;
  };
}

function loadPackage(jobDir: string): PackageDocs {
  const manifest = readJson<Manifest & { scenes: SceneEntry[] }>(join(jobDir, "manifest.json"));
  const storyboard = readJson<{ id: string; beats: Array<Record<string, unknown>> }>(join(jobDir, manifest.storyboard as unknown as string));
  const buildPlan = readJson<PackageDocs["buildPlan"]>(join(jobDir, "build-plan.json"));
  return { jobDir, manifest, storyboard, buildPlan };
}

function beatFor(pkg: PackageDocs, sceneId: string): Record<string, unknown> {
  const beat = pkg.storyboard.beats.find((b) => b.scene_id === sceneId);
  if (!beat) throw new Error(`storyboard has no beat for scene ${sceneId}`);
  return beat;
}

function requirementFor(pkg: PackageDocs, entry: SceneEntry, spec: Record<string, unknown>): SceneRequirement {
  const beat = beatFor(pkg, entry.id);
  const representation = typeof beat.representation === "string" ? beat.representation : "";
  const profile = (pkg.manifest.delivery as { video_profile: string }).video_profile;
  return {
    sceneId: entry.id,
    kind: REPRESENTATION_KIND[representation] ?? "generic",
    explicitEngine: (spec.engine as SceneRequirement["explicitEngine"]) ?? null,
    requiresAlpha: profile === "prores_4444_alpha" || profile === "vp9_alpha",
    extraCodecs: profile === "prores_4444_alpha" ? ["prores"] : profile === "vp9_alpha" ? ["vp9"] : [],
  };
}

// ---------------------------------------------------------------------
// Subject rasterization (the MG-005 method): the authored SVG from the
// job package, rasterized by the shared runtime's headless Chrome; the
// SVG itself is the fallback asset (Hyperframes renders SVG natively).
// ---------------------------------------------------------------------

async function rasterizeSubject(
  svgPath: string,
  workDir: string
): Promise<{ path: string; kind: "png" | "svg"; detail: string }> {
  mkdirSync(workDir, { recursive: true });
  const svg = readFileSync(svgPath, "utf8");
  const match = svg.match(/width="(\d+)" height="(\d+)"/);
  const w = match ? parseInt(match[1], 10) : 1200;
  const h = match ? parseInt(match[2], 10) : 690;
  const htmlPath = join(workDir, "subject-raster.html");
  writeFileSync(
    htmlPath,
    `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;background:transparent}</style></head><body>${svg}</body></html>`,
    "utf8"
  );
  const current = resolve(RUNTIME_ROOT, ".runtime", "current");
  const remotionCache = join(current, "node_modules", ".remotion");
  const findChrome = (dir: string, depth: number): string | null => {
    if (depth > 4 || !existsSync(dir)) return null;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, entry.name);
      if (entry.isDirectory()) {
        const found = findChrome(p, depth + 1);
        if (found) return found;
      } else if (entry.name === "chrome-headless-shell") {
        return p;
      }
    }
    return null;
  };
  const chrome = findChrome(remotionCache, 0);
  if (chrome === null) {
    return { path: svgPath, kind: "svg", detail: "headless Chrome not found in the shared runtime install; the authored SVG is the composition asset directly" };
  }
  const pngPath = join(workDir, "subject.png");
  try {
    await execFileP(
      chrome,
      [
        "--headless", "--disable-gpu", "--no-sandbox", "--no-first-run",
        "--disable-extensions", "--disable-dev-shm-usage",
        `--user-data-dir=${join(workDir, "chrome-profile")}`,
        "--virtual-time-budget=10000", "--hide-scrollbars",
        "--default-background-color=00000000",
        `--window-size=${w},${h}`, `--screenshot=${pngPath}`,
        `file://${htmlPath}`,
      ],
      { timeout: 30000 }
    );
  } catch (err) {
    return {
      path: svgPath,
      kind: "svg",
      detail: `PNG rasterization did not complete (${(err as Error).message.slice(0, 120)}); the authored SVG is used as the composition asset directly`,
    };
  }
  if (!existsSync(pngPath)) {
    return { path: svgPath, kind: "svg", detail: "Chrome produced no PNG; the authored SVG is used as the composition asset directly" };
  }
  return { path: pngPath, kind: "png", detail: "SVG rasterized to PNG by the shared runtime headless Chrome" };
}

// ---------------------------------------------------------------------
// compile
// ---------------------------------------------------------------------

function cmdCompile(argv: string[]): number {
  const inputPath = argValue(argv, "--input");
  const timelineOut = argValue(argv, "--timeline-out");
  const sidecarOut = argValue(argv, "--sidecar-out");
  const input = readJson<unknown>(inputPath);
  const result = compileTimeline(input);
  if (!result.ok) {
    console.log(JSON.stringify({ ok: false, findings: result.findings }, null, 2));
    return 1;
  }
  writeJson(timelineOut, result.compiled.timeline);
  writeJson(sidecarOut, result.compiled.sidecar);
  console.log(JSON.stringify({
    ok: true,
    job_id: result.compiled.timeline.job_id,
    total_frames: result.compiled.timeline.total_frames,
    total_samples: result.compiled.sidecar.total_samples,
  }));
  return 0;
}

// ---------------------------------------------------------------------
// render
// ---------------------------------------------------------------------

interface SceneRenderRecord {
  scene_id: string;
  component_id: string;
  routed_engine: string;
  routing: { kind: string; reason_code: string; reason: string };
  dispatch_note: string;
  segment: string;
  segment_sha256: string;
  frames: number;
  width: number;
  height: number;
  engine_version: string | null;
  runtime_lock_id: string | null;
  proof: Record<string, unknown> | null;
}

function shellManifest(pkg: PackageDocs, entry: SceneEntry, durationFrames: number, posterFrame: number): Manifest {
  const m = pkg.manifest as unknown as Record<string, unknown>;
  const shell = {
    ...m,
    duration_frames: durationFrames,
    scenes: [entry],
    delivery: {
      ...(m.delivery as Record<string, unknown>),
      poster_frame: posterFrame,
    },
  };
  return shell as unknown as Manifest;
}

function singleSceneTimeline(jobId: string, sceneId: string, durationFrames: number, events: Array<Record<string, unknown>>, fps = 30): Record<string, unknown> {
  return {
    schema_version: "2.0",
    job_id: jobId,
    fps,
    total_frames: durationFrames,
    scenes: [{
      id: sceneId, start_frame: 0, end_frame_exclusive: durationFrames,
      source_start_frame: 0, transition_in_frames: 0, transition_out_frames: 0,
    }],
    events,
    parent_slot: null,
    audio_owner: "none",
  };
}

async function renderHyperframesScene(
  pkg: PackageDocs,
  entry: SceneEntry,
  spec: Record<string, unknown>,
  stageDir: string,
  subject: { path: string; kind: string; detail: string },
  adapter: HyperframesAdapter
): Promise<SceneRenderRecord> {
  const jobId = pkg.manifest.job_id;
  const duration = spec.duration_frames as number;
  const shellDir = join(stageDir, "shells", entry.id);
  rmSync(shellDir, { recursive: true, force: true });
  mkdirSync(join(shellDir, "scenes"), { recursive: true });
  mkdirSync(join(shellDir, "assets"), { recursive: true });
  const assetName = `subject.${subject.kind}`;
  cpSync(subject.path, join(shellDir, "assets", assetName));
  const shellSpec = {
    ...spec,
    asset_file: `assets/${assetName}`,
    asset_sha256: sha256File(join(shellDir, "assets", assetName)),
  };
  writeJson(join(shellDir, "scenes", `${entry.id}.json`), shellSpec);
  const manifest = shellManifest(pkg, { id: entry.id, spec: `scenes/${entry.id}.json` }, duration, 0);
  writeJson(join(shellDir, "manifest.json"), manifest);
  writeJson(join(shellDir, "timeline.json"), singleSceneTimeline(jobId, entry.id, duration, [], pkg.manifest.canvas.fps));
  const job = { jobDir: shellDir, jobId, manifest };

  const validation = await adapter.validate(job);
  if (!validation.valid) {
    throw new Error(`hyperframes validation failed for scene ${entry.id}: ${JSON.stringify(validation.findings)}`);
  }

  let proof: Record<string, unknown> | null = null;
  if (spec.component_id === "C01" && spec.variant === undefined) {
    const motion = await adapter.inspectMotion(job, { startFrame: 0, endFrameExclusive: duration });
    proof = {
      mechanism: "adapter_inspect_motion",
      assertions_checked: motion.assertionsChecked,
      assertions_passed: motion.assertionsPassed,
      observations: motion.observations,
    };
    if (motion.assertionsChecked === 0 || motion.assertionsPassed !== motion.assertionsChecked) {
      throw new Error(`inspectMotion did not pass every assertion for scene ${entry.id}: ${JSON.stringify(motion.observations)}`);
    }
  } else if (spec.component_id === "C01" && spec.variant === "nested_detail") {
    const detail = spec.detail as { box: { x: number; y: number; width: number; height: number }; measure_color: string };
    const subjectBox = (spec.subject as { box: { x: number; y: number; width: number; height: number }; measure_color: string });
    const early = await adapter.renderStill(job, 10);
    const late = await adapter.renderStill(job, duration - 10);
    const earlyImg = await decodePng(join(shellDir, early.outputPaths[0]));
    const lateImg = await decodePng(join(shellDir, late.outputPaths[0]));
    const chipEarly = measureColorFraction(earlyImg, detail.box, detail.measure_color);
    const chipLate = measureColorFraction(lateImg, detail.box, detail.measure_color);
    const subjEarly = measureColorFraction(earlyImg, subjectBox.box, subjectBox.measure_color);
    const subjLate = measureColorFraction(lateImg, subjectBox.box, subjectBox.measure_color);
    proof = {
      mechanism: "adapter_stills_measurement",
      method: "MG-005 nested-detail method: detail chip color fraction in decoded stills before and after its start frame, root subject fraction held constant",
      detail_chip_fraction_early: chipEarly,
      detail_chip_fraction_late: chipLate,
      subject_fraction_early: subjEarly,
      subject_fraction_late: subjLate,
    };
    if (!(chipEarly < 0.05 && chipLate > 0.4 && Math.abs(subjEarly - subjLate) < 0.02)) {
      throw new Error(`nested detail measurement failed for scene ${entry.id}: ${JSON.stringify(proof)}`);
    }
  }

  const fin = await adapter.renderFinal({ ...job, approval: fixtureApproval(jobId) });
  const segmentSrc = isAbsolute(fin.outputPaths[0]) ? fin.outputPaths[0] : join(shellDir, fin.outputPaths[0]);
  const segmentDst = join(stageDir, "segments", `${entry.id}.mp4`);
  mkdirSync(join(stageDir, "segments"), { recursive: true });
  cpSync(segmentSrc, segmentDst);
  const probe = await ffprobeMedia(segmentDst);
  if (probe.frames !== duration) {
    throw new Error(`segment ${entry.id} holds ${probe.frames} frames, expected ${duration}`);
  }
  const matrix = loadCapabilityMatrix();
  const decision = routeOrThrow(
    { scenes: [requirementFor(pkg, entry, spec)], manifestDefaultEngine: pkg.manifest.rendering.default_engine, allowLegacyFallback: false },
    matrix
  );
  const assignment = decision.assignments[0];
  return {
    scene_id: entry.id,
    component_id: spec.component_id as string,
    routed_engine: assignment.engine,
    routing: { kind: requirementFor(pkg, entry, spec).kind, reason_code: assignment.reasonCode, reason: assignment.reason },
    dispatch_note: "Rendered through the Hyperframes adapter directly on a ValidatedMotionJob built by this driver, the MG-005 suite pattern: the dispatcher's contracts gate refuses mg005-1 scene specs on this base (canonical scene $def closed on C05), so dispatcher.renderFinal cannot take this scene until the MG-017/MG-018 catalog registration lands. The routing decision above is computed by the shipped routing module.",
    segment: `segments/${entry.id}.mp4`,
    segment_sha256: sha256File(segmentDst),
    frames: probe.frames,
    width: probe.width,
    height: probe.height,
    engine_version: fin.runtime.engineVersion,
    runtime_lock_id: fin.runtime.runtimeLockId,
    proof,
  };
}

async function renderRemotionScene(
  pkg: PackageDocs,
  entry: SceneEntry,
  spec: Record<string, unknown>,
  stageDir: string,
  dispatcher: MotionDispatcher
): Promise<SceneRenderRecord> {
  const jobId = pkg.manifest.job_id;
  const duration = spec.duration_frames as number;
  const shellDir = join(stageDir, "shells", entry.id);
  rmSync(shellDir, { recursive: true, force: true });
  cpSync(pkg.jobDir, shellDir, { recursive: true });
  const motion = spec.motion as { start_frame: number; end_frame_exclusive: number };
  const manifest = shellManifest(pkg, entry, duration, motion.end_frame_exclusive);
  writeJson(join(shellDir, "manifest.json"), manifest);
  const storyboard = {
    schema_version: "2.0",
    id: pkg.storyboard.id,
    beats: pkg.storyboard.beats.filter((b) => b.scene_id === entry.id),
  };
  writeJson(join(shellDir, "storyboard.json"), storyboard);
  const events = [
    { id: `cue-${entry.id}-reveal`, scene_id: entry.id, frame: motion.start_frame, type: "reveal_start" },
    { id: `cue-${entry.id}-proof`, scene_id: entry.id, frame: motion.end_frame_exclusive, type: "proof" },
    { id: `cue-${entry.id}-hold`, scene_id: entry.id, frame: motion.end_frame_exclusive, type: "hold_start" },
  ];
  writeJson(join(shellDir, "timeline.json"), singleSceneTimeline(jobId, entry.id, duration, events, pkg.manifest.canvas.fps));
  rmSync(join(shellDir, "renders"), { recursive: true, force: true });

  const routed = dispatcher.routeJob(shellDir);
  const assignment = routed.routing.assignments.find((a) => a.sceneId === entry.id) ?? routed.routing.assignments[0];
  const outcome = await dispatcher.renderFinal(shellDir, fixtureApproval(jobId), { timeoutMs: 900_000 });
  const segmentSrc = isAbsolute(outcome.evidence.outputPaths[0])
    ? outcome.evidence.outputPaths[0]
    : join(shellDir, outcome.evidence.outputPaths[0]);
  const segmentDst = join(stageDir, "segments", `${entry.id}.mp4`);
  mkdirSync(join(stageDir, "segments"), { recursive: true });
  cpSync(segmentSrc, segmentDst);
  const probe = await ffprobeMedia(segmentDst);
  if (probe.frames !== duration) {
    throw new Error(`segment ${entry.id} holds ${probe.frames} frames, expected ${duration}`);
  }
  return {
    scene_id: entry.id,
    component_id: spec.component_id as string,
    routed_engine: assignment.engine,
    routing: { kind: requirementFor(pkg, entry, spec).kind, reason_code: assignment.reasonCode, reason: assignment.reason },
    dispatch_note: "Rendered through MotionDispatcher.renderFinal on a single-scene shell of the program package (contracts validation, catalog consult, routing, fixture approval), the MG-006 suite pattern. Program assembly belongs to MG-022's assembler, so the dispatcher is never asked to render the multi-scene job itself.",
    segment: `segments/${entry.id}.mp4`,
    segment_sha256: sha256File(segmentDst),
    frames: probe.frames,
    width: probe.width,
    height: probe.height,
    engine_version: outcome.evidence.runtime.engineVersion,
    runtime_lock_id: outcome.evidence.runtime.runtimeLockId,
    proof: null,
  };
}

async function cmdRender(argv: string[]): Promise<number> {
  const packageDir = resolve(argValue(argv, "--package"));
  const stageDir = resolve(argValue(argv, "--stage"));
  const pkg = loadPackage(packageDir);
  mkdirSync(stageDir, { recursive: true });

  const subjectSvg = join(packageDir, "assets", "subject.svg");
  const subject = await rasterizeSubject(subjectSvg, join(stageDir, "assets-src"));
  const hfAdapter = new HyperframesAdapter();
  const dispatcher = new MotionDispatcher(
    createRegistry([createRemotionAdapter(), createHyperframesAdapter()])
  );

  const records: SceneRenderRecord[] = [];
  for (const entry of pkg.manifest.scenes) {
    const spec = readJson<Record<string, unknown>>(join(packageDir, entry.spec));
    const engine = spec.engine as string;
    let record: SceneRenderRecord;
    if (engine === "hyperframes") {
      record = await renderHyperframesScene(pkg, entry, spec, stageDir, subject, hfAdapter);
    } else if (engine === "remotion") {
      record = await renderRemotionScene(pkg, entry, spec, stageDir, dispatcher);
    } else {
      throw new Error(`scene ${entry.id} declares unsupported engine ${engine}`);
    }
    records.push(record);
    console.log(`rendered ${entry.id} via ${record.routed_engine}: ${record.frames} frames`);
  }

  const receipt = {
    schema_version: "1.0",
    item: "MG-039",
    kind: "standalone_render_receipt",
    job_id: pkg.manifest.job_id,
    subject_asset: {
      source: "assets/subject.svg",
      source_sha256: sha256File(subjectSvg),
      used: subject.kind,
      used_sha256: sha256File(subject.path),
      detail: subject.detail,
    },
    scenes: records,
  };
  writeJson(join(stageDir, "render-receipt.json"), receipt);
  console.log(JSON.stringify({ ok: true, job_id: pkg.manifest.job_id, scenes: records.length }));
  return 0;
}

// ---------------------------------------------------------------------
// proof
// ---------------------------------------------------------------------

function cmdProof(argv: string[]): number {
  const packageDir = resolve(argValue(argv, "--package"));
  const stageDir = resolve(argValue(argv, "--stage"));
  const pkg = loadPackage(packageDir);
  const jobId = pkg.manifest.job_id;
  const renderReceipt = readJson<{ scenes: SceneRenderRecord[] }>(join(stageDir, "render-receipt.json"));

  const sceneRecords: Array<Record<string, unknown>> = [];
  let allPass = true;

  for (const entry of pkg.manifest.scenes) {
    const spec = readJson<Record<string, unknown>>(join(packageDir, entry.spec));
    const rendered = renderReceipt.scenes.find((s) => s.scene_id === entry.id);
    if (!rendered) throw new Error(`render receipt has no record for scene ${entry.id}`);
    if (spec.component_id === "C05") {
      const caseDoc = readJson<{ checkpoints: Array<{ frame: number }> }>(join(packageDir, "proof-cases", `${entry.id}.case.json`));
      const segment = join(stageDir, rendered.segment);
      const bundleDir = join(stageDir, "proof-bundles", entry.id);
      rmSync(bundleDir, { recursive: true, force: true });
      mkdirSync(bundleDir, { recursive: true });
      // The bundle's targeted samples come from timeline events and
      // scene boundaries; a case checkpoint between events (the
      // half-reveal proof state) is requested through the bundle's
      // beats channel, the same mechanism the MG-032 suite uses.
      const fps = pkg.manifest.canvas.fps;
      const beatSeconds = [...new Set(caseDoc.checkpoints.map((c) => c.frame / fps))].sort((a, b) => a - b);
      const beatsPath = join(stageDir, "proof-bundles", `${entry.id}-beats.json`);
      writeJson(beatsPath, { beat_times: beatSeconds });
      const bundle = spawnSync("python3", [
        join(SKILL_DIR, "scripts", "critique_bundle.py"), "build",
        "--video", segment,
        "--outdir", bundleDir,
        "--job-id", jobId,
        "--timeline", join(stageDir, "shells", entry.id, "timeline.json"),
        "--beats", beatsPath,
      ], { encoding: "utf8", maxBuffer: 256 * 1024 * 1024 });
      if (bundle.status !== 0) {
        throw new Error(`critique_bundle failed for scene ${entry.id}: ${bundle.stderr?.slice(-400)}`);
      }
      const coverageName = readdirSync(bundleDir).find((n) => n.endsWith("__coverage.json"));
      if (!coverageName) throw new Error(`no coverage record produced for scene ${entry.id}`);
      const outputDir = join(stageDir, "proof", entry.id);
      const { record, exitCode } = evaluateMotionProof({
        caseDoc,
        videoPath: segment,
        coverageRecordPath: join(bundleDir, coverageName),
        outputDir,
        jobDir: join(stageDir, "shells", entry.id),
      });
      if (!existsSync(join(outputDir, "proof-record.json"))) {
        writeJson(join(outputDir, "proof-record.json"), record);
      }
      if (record.verdict !== "pass" || exitCode !== 0) allPass = false;
      sceneRecords.push({
        scene_id: entry.id,
        component_id: "C05",
        mechanism: "mg032_evaluator",
        verdict: record.verdict,
        category: record.category,
        record: `proof/${entry.id}/proof-record.json`,
        assertions: record.assertions,
        clip_frames: record.clip?.frames ?? null,
      });
    } else {
      const proof = rendered.proof;
      let verdict = "not_evaluated";
      if (proof && proof.mechanism === "adapter_inspect_motion") {
        verdict = proof.assertions_passed === proof.assertions_checked && (proof.assertions_checked as number) > 0 ? "pass" : "fail";
      } else if (proof && proof.mechanism === "adapter_stills_measurement") {
        verdict =
          (proof.detail_chip_fraction_early as number) < 0.05 &&
          (proof.detail_chip_fraction_late as number) > 0.4 &&
          Math.abs((proof.subject_fraction_late as number) - (proof.subject_fraction_early as number)) < 0.02
            ? "pass"
            : "fail";
      }
      if (verdict !== "pass") allPass = false;
      sceneRecords.push({
        scene_id: entry.id,
        component_id: spec.component_id,
        mechanism: proof ? (proof.mechanism as string) : "none",
        verdict,
        record: "render-receipt.json",
        detail: proof,
      });
    }
  }

  const aggregate = {
    schema_version: "1.0",
    kind: "motion_proof_record",
    item: "MG-032",
    job_id: jobId,
    verdict: allPass ? "pass" : "fail",
    scope: "standalone program: MG-032 evaluator per C05 scene; adapter motion assertions per C01 scene (the components' supported proof surfaces)",
    scenes: sceneRecords,
    generated_at: new Date().toISOString(),
  };
  writeJson(join(stageDir, "proof", "motion-proof.json"), aggregate);
  console.log(JSON.stringify({ ok: allPass, job_id: jobId, verdict: aggregate.verdict }));
  return allPass ? 0 : 1;
}

// ---------------------------------------------------------------------

async function main(): Promise<number> {
  const argv = process.argv.slice(2);
  const command = argv[0];
  if (command === "compile") return cmdCompile(argv.slice(1));
  if (command === "render") return cmdRender(argv.slice(1));
  if (command === "proof") return cmdProof(argv.slice(1));
  console.error("usage: cli.js <compile|render|proof> [args]");
  return 2;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.log(JSON.stringify({ ok: false, error: (err as Error).message }));
    process.exit(1);
  }
);
