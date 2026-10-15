// Motion proof tests for MG-032 (Directive MG-032: prove actual
// subject motion, not decorative activity).
//
// Real end-to-end tests, no mocks. The suite renders the real C05
// fixture job through the production dispatcher, renders a DECOY
// composition (the same job's layout and final bar widths, but the
// bars never move: only the headline slides and a decoration band
// sweeps), renders the real C04 mechanism scene to video, and
// synthesizes an occlusion video with ffmpeg. Every artifact gets an
// MG-031 coverage bundle, and the motion proof evaluator judges each
// case against the scene specification.
//
// The four acceptance cases:
//   (1) the static decoy FAILS with MG_FAKE_MOTION (exit 6) even
//       though its whole-frame pixel change is large;
//   (2) the animated C05 chart PASSES (exit 0) with three-way
//       agreement: spec derivation, component geometry, decoded raster;
//   (3) the C04 object-through-mechanism sequence PASSES (exit 0);
//   (4) a depth claim without occlusion or depth evidence is REFUSED
//       (MG_CAPABILITY_UNSUPPORTED, exit 3), while the same claim
//       WITH genuine occlusion evidence passes on measurement.
//
// Plus the honesty paths: incomplete bundles fail, hash and job
// mismatches are refused, rough_layout_only evidence cannot satisfy a
// full-fps claim, semantic cases route to human judgment, and case
// documents are validated against the layer's own schema.
//
// Prerequisites: the shared runtime must be provisioned
// (shared-utils/motion-render-runtime/provision.sh) and the runtime
// package built (npm test runs the build first). Scratch lives in the
// shared runtime's gitignored .runtime dir; committed evidence lands
// in 72-motion-video-plus/tests/evidence/mg032.
//
// Exit code 0 when every case passes, 1 otherwise.

import { spawnSync } from "node:child_process";
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
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import {
  createRegistry,
  loadCapabilityMatrix,
  loadValidatedJob,
  MotionDispatcher,
} from "../src/adapters";
import { createRemotionAdapter } from "../src/adapters/remotion";
import { c04Entry, c05Entry } from "../src/catalog";
import type { DiagramSceneDoc } from "../src/diagrams";
import { FontTextMeasurer, resolveDiagram } from "../src/diagrams";
import { DIAGRAM_COMPOSITION_ID } from "../src/diagrams/render/ids";
import { resolveDiagramRuntime } from "../src/diagrams/render/runtime";
import {
  evaluateMotionProof,
  validateMotionProofCase,
  type HumanVerdict,
  type MotionProofCase,
} from "../src/motion-proof";
import { probeVideoFile } from "../src/remotion/decode";
import { resolveFont } from "../src/remotion/fonts";
import { instrumentedBarWidths, loadC05Job } from "../src/remotion/job-props";
import type { Approval } from "../src/validation/generated-types";
import type { DecoyCompositionProps } from "./motion-proof/decoy-composition";
import { DECOY_COMPOSITION_ID } from "./motion-proof/ids";

// ---------------------------------------------------------------------------
// Paths and harness
// ---------------------------------------------------------------------------

function skillRoot(): string {
  return resolve(__dirname, "..", "..", "..");
}
function fixturesRoot(): string {
  return join(skillRoot(), "tests", "fixtures");
}
function evidenceDir(): string {
  return join(skillRoot(), "tests", "evidence", "mg032");
}
function runtimeStateDir(): string {
  return resolve(
    __dirname,
    "..",
    "..",
    "..",
    "..",
    "shared-utils",
    "motion-render-runtime",
    ".runtime"
  );
}
const SCRATCH = join(runtimeStateDir(), "mg032-tests");
const FONT_PATH = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf";

let passed = 0;
let failed = 0;
const failures: string[] = [];
function check(name: string, fn: () => void): void {
  try {
    fn();
    passed += 1;
    console.log(`PASS ${name}`);
  } catch (err) {
    failed += 1;
    const message = err instanceof Error ? err.message : String(err);
    failures.push(`${name}: ${message}`);
    console.log(`FAIL ${name}: ${message}`);
  }
}
async function checkAsync(name: string, fn: () => Promise<void>): Promise<void> {
  try {
    await fn();
    passed += 1;
    console.log(`PASS ${name}`);
  } catch (err) {
    failed += 1;
    const message = err instanceof Error ? err.message : String(err);
    failures.push(`${name}: ${message}`);
    console.log(`FAIL ${name}: ${message}`);
  }
}
function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}
function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(
      `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
  }
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}
function writeJson(path: string, doc: unknown): void {
  writeFileSync(path, JSON.stringify(doc, null, 2) + "\n", "utf8");
}
function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf8")) as T;
}

interface RunResult {
  status: number;
  stdout: string;
  stderr: string;
}
function run(command: string, args: string[]): RunResult {
  const result = spawnSync(command, args, {
    maxBuffer: 256 * 1024 * 1024,
    encoding: "utf8",
  });
  if (result.error) throw new Error(`${command} could not run: ${result.error.message}`);
  return {
    status: result.status ?? -1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

// ---------------------------------------------------------------------------
// MG-031 bundle construction (the real script, as a subprocess)
// ---------------------------------------------------------------------------

interface BundleResult {
  exitCode: number;
  coveragePath: string;
  record: Record<string, unknown>;
}

function buildBundle(options: {
  video: string;
  outdir: string;
  jobId: string;
  timeline?: string;
  beatsSeconds?: number[];
}): BundleResult {
  rmSync(options.outdir, { recursive: true, force: true });
  mkdirSync(options.outdir, { recursive: true });
  const args = [
    join(skillRoot(), "scripts", "critique_bundle.py"),
    "build",
    "--video",
    options.video,
    "--outdir",
    options.outdir,
    "--job-id",
    options.jobId,
  ];
  if (options.timeline) args.push("--timeline", options.timeline);
  if (options.beatsSeconds && options.beatsSeconds.length > 0) {
    const beatsPath = join(options.outdir, "..", `${options.jobId}-beats.json`);
    writeJson(beatsPath, { beat_times: options.beatsSeconds });
    args.push("--beats", beatsPath);
  }
  const result = run("python3", args);
  const coverageName = readdirSync(options.outdir).find((name) =>
    name.endsWith("__coverage.json")
  );
  assertTrue(
    coverageName !== undefined,
    `critique_bundle wrote a coverage record into ${options.outdir} (exit ${result.status}): ${result.stderr.slice(-400)}`
  );
  const coveragePath = join(options.outdir, coverageName as string);
  return {
    exitCode: result.status,
    coveragePath,
    record: readJson<Record<string, unknown>>(coveragePath),
  };
}

// ---------------------------------------------------------------------------
// Generic Remotion video rendering against the shared runtime
// (the MG-017 bundling discipline: cache by source hash + lock id)
// ---------------------------------------------------------------------------

interface BundlerModule {
  bundle: (options: Record<string, unknown>) => Promise<string>;
}
interface RendererModule {
  selectComposition: (options: Record<string, unknown>) => Promise<{
    id: string;
    width: number;
    height: number;
    fps: number;
    durationInFrames: number;
  }>;
  renderMedia: (options: Record<string, unknown>) => Promise<void>;
}
interface WebpackConfigLike {
  resolve?: {
    modules?: string[];
    alias?: Record<string, string | false>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

async function renderVideo(options: {
  entryPoint: string;
  hashSources: string[];
  compositionId: string;
  props: Record<string, unknown>;
  outputPath: string;
  expect: { width: number; height: number; fps: number; durationInFrames: number };
  tag: string;
}): Promise<void> {
  const runtime = resolveDiagramRuntime();
  const req = createRequire(join(runtime.currentDir, "package.json"));
  const bundler = req("@remotion/bundler") as BundlerModule;
  const renderer = req("@remotion/renderer") as RendererModule;
  const hash = createHash("sha256");
  for (const source of options.hashSources) hash.update(readFileSync(source));
  const bundleKey = `${hash.digest("hex").slice(0, 24)}-${runtime.lockId ?? "nolock"}`;
  const bundleDir = join(runtime.stateDir, "mg032-bundles", bundleKey);
  let serveUrl = bundleDir;
  if (!existsSync(join(bundleDir, "index.html"))) {
    mkdirSync(bundleDir, { recursive: true });
    const nodeModules = join(runtime.currentDir, "node_modules");
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
    serveUrl = await bundler.bundle({
      entryPoint: options.entryPoint,
      outDir: bundleDir,
      onProgress: () => undefined,
      webpackOverride: applyResolution,
      rspackOverride: applyResolution,
    });
  }
  const composition = await renderer.selectComposition({
    serveUrl,
    id: options.compositionId,
    inputProps: options.props,
    browserExecutable: runtime.browserExecutable,
  });
  assertEq(composition.width, options.expect.width, `${options.tag}: composition width`);
  assertEq(composition.height, options.expect.height, `${options.tag}: composition height`);
  assertEq(composition.fps, options.expect.fps, `${options.tag}: composition fps`);
  assertEq(
    composition.durationInFrames,
    options.expect.durationInFrames,
    `${options.tag}: composition duration`
  );
  mkdirSync(resolve(options.outputPath, ".."), { recursive: true });
  await renderer.renderMedia({
    composition,
    serveUrl,
    outputLocation: options.outputPath,
    inputProps: options.props,
    browserExecutable: runtime.browserExecutable,
    codec: "h264",
    timeoutInMilliseconds: 900_000,
  });
  assertTrue(existsSync(options.outputPath), `${options.tag}: video rendered`);
}

// ---------------------------------------------------------------------------
// Case documents used by the suite
// ---------------------------------------------------------------------------

function loadCommittedCase(name: string): MotionProofCase {
  const { caseDoc, problems } = validateMotionProofCase(
    readJson(join(fixturesRoot(), "motion-proof", name))
  );
  assertTrue(caseDoc !== null, `committed case ${name} validates: ${problems.join("; ")}`);
  return caseDoc as MotionProofCase;
}

const measurements: Record<string, unknown> = {
  item: "MG-032",
  section: "Directive MG-032: prove actual subject motion, not decorative activity",
  cases: {},
};
function recordCase(key: string, value: Record<string, unknown>): void {
  (measurements.cases as Record<string, unknown>)[key] = value;
}

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg032-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "fixture",
    artifact_refs: [],
    actor_id: "mg032-test-runner",
    source_event_ref: null,
    authority_status: "not_verified",
  };
}

// ---------------------------------------------------------------------------
// The suite
// ---------------------------------------------------------------------------

let c05JobDir = "";
let c05Video: string | null = null;
let c05CoveragePath: string | null = null;
let decoyCoveragePath: string | null = null;

function requireSetup(): { video: string; coveragePath: string } {
  assertTrue(
    c05Video !== null && c05CoveragePath !== null,
    "the C05 positive setup must complete before dependent cases run"
  );
  return { video: c05Video as string, coveragePath: c05CoveragePath as string };
}

async function main(): Promise<void> {
  mkdirSync(evidenceDir(), { recursive: true });
  mkdirSync(SCRATCH, { recursive: true });
  const runtime = resolveDiagramRuntime();
  measurements.runtime = {
    lockId: runtime.lockId,
    remotionVersion: runtime.remotionVersion,
    sharedRuntimeDir: runtime.sharedRuntimeDir,
  };

  // ----- Acceptance case 2 setup + verdict: the animated C05 chart.
  await checkAsync(
    "acceptance 2: the correctly animated C05 data chart PASSES with three-way agreement",
    async () => {
      c05JobDir = join(SCRATCH, "job-c05");
      rmSync(c05JobDir, { recursive: true, force: true });
      cpSync(join(fixturesRoot(), "modes", "powerpoint_graphic"), c05JobDir, {
        recursive: true,
      });
      const adapter = createRemotionAdapter({
        outputDir: join(SCRATCH, "render-c05"),
      });
      const dispatcher = new MotionDispatcher(createRegistry([adapter]));
      const matrix = loadCapabilityMatrix();
      const job = loadValidatedJob(c05JobDir);
      const outcome = await dispatcher.renderFinal(c05JobDir, fixtureApproval(job.jobId), {
        matrix,
        timeoutMs: 900_000,
      });
      c05Video = outcome.evidence.outputPaths[0];
      const probe = probeVideoFile(c05Video);
      assertEq(probe.frameCount, 180, "C05 final frame count");
      const bundle = buildBundle({
        video: c05Video,
        outdir: join(SCRATCH, "bundles", "c05-positive"),
        jobId: "fixture-powerpoint-graphic",
        timeline: join(c05JobDir, "timeline.json"),
        beatsSeconds: [1.5],
      });
      assertEq(bundle.exitCode, 0, "positive bundle builds clean");
      assertEq(bundle.record.verdict, "complete", "positive bundle verdict");
      c05CoveragePath = bundle.coveragePath;

      const caseDoc = loadCommittedCase("c05-bar-reveal.case.json");
      const outputDir = join(SCRATCH, "proofs", "c05-positive");
      const { record, exitCode } = evaluateMotionProof({
        caseDoc,
        videoPath: c05Video,
        coverageRecordPath: bundle.coveragePath,
        outputDir,
        jobDir: c05JobDir,
      });
      assertEq(exitCode, 0, "C05 positive exit code");
      assertEq(record.verdict, "pass", "C05 positive verdict");
      assertEq(record.category, null, "C05 positive category");
      assertTrue(
        record.assertions.every((a) => a.verdict === "pass"),
        `every checkpoint assertion passes: ${JSON.stringify(record.assertions.map((a) => [a.frame, a.verdict, a.detail]))}`
      );
      const proof = record.assertions.find((a) => a.frame === 45);
      assertTrue(proof !== undefined, "the frame-45 proof assertion exists");
      assertEq(
        JSON.stringify(proof?.geometry_measured),
        JSON.stringify([240, 360, 600]),
        "frame 45 component geometry is exactly the half reveal"
      );
      (proof?.raster_measured ?? []).forEach((value, i) => {
        assertTrue(
          Math.abs(value - [240, 360, 600][i]) <= 2,
          `frame 45 decoded width ${i} within 2px of the half reveal (got ${value})`
        );
      });
      assertEq(record.clip?.frames, 60, "the full-fps clip holds the whole reveal interval");
      assertEq(record.frames.length, 4, "four checkpoint frames in the proof package");
      recordCase("c05_positive", {
        verdict: record.verdict,
        exit_code: exitCode,
        video: c05Video,
        video_sha256: sha256File(c05Video),
        frame_45: {
          expected: proof?.expected,
          geometry_measured: proof?.geometry_measured,
          raster_measured: proof?.raster_measured,
        },
        clip_frames: record.clip?.frames,
        context_change: record.context_change,
        proof_record: join(outputDir, "proof-record.json"),
      });
      const frame45 = join(outputDir, "frames", "f45.png");
      if (existsSync(frame45) && statSync(frame45).size < 600_000) {
        cpSync(frame45, join(evidenceDir(), "c05-positive-f45.png"));
      }
    }
  );

  // ----- Acceptance case 1: the decoy. Static bars, moving title and
  // decoration. It must FAIL as fake motion.
  await checkAsync(
    "acceptance 1: a static chart with a moving title and animated decoration FAILS as MG_FAKE_MOTION",
    async () => {
      assertTrue(
        existsSync(join(c05JobDir, "design.json")),
        "the C05 positive setup must complete before the decoy case runs"
      );
      const design = readJson<{
        colors: { background: string; ink: string; accent: string };
        layouts: {
          landscape: {
            plot: { x: number; y: number; width: number; height: number };
            bar_height: number;
            row_y: number[];
            headline_box: { x: number; y: number; width: number; height: number };
          };
        };
      }>(join(c05JobDir, "design.json"));
      const dataset = readJson<{
        rows: { id: string; label: string; value: number }[];
      }>(join(c05JobDir, "data", "bars.json"));
      const loaded = loadC05Job(loadValidatedJob(c05JobDir));
      const finalWidths = instrumentedBarWidths(loaded.props, 179);
      assertEq(
        JSON.stringify(finalWidths),
        JSON.stringify([480, 720, 1200]),
        "decoy bars use the real final instrumented widths"
      );
      const layout = design.layouts.landscape;
      const decoyProps: DecoyCompositionProps = {
        width: 1920,
        height: 1080,
        fps: 30,
        durationFrames: 180,
        headline: "Compare the three groups",
        headlineBox: layout.headline_box,
        plotX: layout.plot.x,
        barHeight: layout.bar_height,
        bars: dataset.rows.map((row, i) => ({
          id: `bar-${row.id}`,
          label: row.label,
          valueLabel: String(row.value),
          finalWidth: finalWidths[i],
          y: layout.row_y[i],
        })),
        colors: design.colors,
      };
      const decoyVideo = join(SCRATCH, "videos", "decoy.mp4");
      const decoyDir = join(skillRoot(), "runtime", "tests", "motion-proof");
      await renderVideo({
        entryPoint: join(decoyDir, "decoy-entry.ts"),
        hashSources: [
          join(decoyDir, "decoy-entry.ts"),
          join(decoyDir, "decoy-root.ts"),
          join(decoyDir, "decoy-composition.ts"),
          join(decoyDir, "ids.ts"),
        ],
        compositionId: DECOY_COMPOSITION_ID,
        props: decoyProps as unknown as Record<string, unknown>,
        outputPath: decoyVideo,
        expect: { width: 1920, height: 1080, fps: 30, durationInFrames: 180 },
        tag: "decoy",
      });
      const bundle = buildBundle({
        video: decoyVideo,
        outdir: join(SCRATCH, "bundles", "decoy"),
        jobId: "fixture-powerpoint-graphic",
        timeline: join(c05JobDir, "timeline.json"),
        beatsSeconds: [1.5],
      });
      assertEq(bundle.record.verdict, "complete", "decoy bundle verdict (the bundle is honest; the motion is not)");
      decoyCoveragePath = bundle.coveragePath;

      const caseDoc = loadCommittedCase("c05-bar-reveal.case.json");
      const outputDir = join(SCRATCH, "proofs", "decoy");
      const { record, exitCode } = evaluateMotionProof({
        caseDoc,
        videoPath: decoyVideo,
        coverageRecordPath: bundle.coveragePath,
        outputDir,
        jobDir: c05JobDir,
      });
      assertEq(exitCode, 6, "decoy exit code");
      assertEq(record.verdict, "fail", "decoy verdict");
      assertEq(record.category, "MG_FAKE_MOTION", "decoy category");
      assertTrue(
        (record.context_change?.mean_abs_diff ?? 0) > 1,
        `the decoy's frame really does change outside the subject regions (mean abs diff ${record.context_change?.mean_abs_diff}); decoration moved and the proof still failed`
      );
      const proofAssertion = record.assertions.find((a) => a.frame === 45);
      assertEq(proofAssertion?.verdict, "fail", "the frame-45 subject assertion fails on the decoy");
      recordCase("decoy_static_chart", {
        verdict: record.verdict,
        exit_code: exitCode,
        category: record.category,
        context_change_mean_abs_diff: record.context_change?.mean_abs_diff,
        frame_45_raster_measured: proofAssertion?.raster_measured,
        frame_45_expected: proofAssertion?.expected,
        detail: proofAssertion?.detail,
      });
      const frame45 = join(outputDir, "frames", "f45.png");
      if (existsSync(frame45) && statSync(frame45).size < 600_000) {
        cpSync(frame45, join(evidenceDir(), "decoy-f45.png"));
      }
    }
  );

  // ----- Acceptance case 3: the C04 object-through-mechanism sequence.
  await checkAsync(
    "acceptance 3: the C04 object-through-mechanism sequence PASSES",
    async () => {
      const docPath = join(fixturesRoot(), "diagrams", "c04-flow-mechanism.json");
      const doc = readJson<DiagramSceneDoc>(docPath);
      const resolvedResult = resolveDiagram(doc.diagram, new FontTextMeasurer(FONT_PATH));
      assertTrue(resolvedResult.ok, "the C04 fixture resolves");
      if (!resolvedResult.ok) return;
      const font = resolveFont("font-fixture-sans", "fixture-sans", [400, 700]);
      const props = {
        resolved: resolvedResult.resolved,
        headline: doc.copy.headline,
        disclosure: doc.copy.disclosure,
        durationFrames: doc.duration_frames,
        font: {
          family: font.family,
          files: font.files.map((f) => ({ weight: f.weight, base64: f.base64 })),
        },
      };
      const video = join(SCRATCH, "videos", "c04-mechanism.mp4");
      const renderDir = join(skillRoot(), "runtime", "src", "diagrams", "render");
      await renderVideo({
        entryPoint: join(renderDir, "entry.ts"),
        hashSources: [
          join(renderDir, "entry.ts"),
          join(renderDir, "Root.ts"),
          join(renderDir, "DiagramComposition.ts"),
        ],
        compositionId: DIAGRAM_COMPOSITION_ID,
        props: props as unknown as Record<string, unknown>,
        outputPath: video,
        expect: { width: 1920, height: 1080, fps: 30, durationInFrames: 180 },
        tag: "c04",
      });
      const timelinePath = join(SCRATCH, "timelines", "c04-mechanism.timeline.json");
      mkdirSync(join(SCRATCH, "timelines"), { recursive: true });
      writeJson(timelinePath, {
        schema_version: "2.0",
        job_id: "mg032-c04-mechanism",
        fps: 30,
        total_frames: 180,
        scenes: [
          {
            id: "c04-flow-mechanism",
            start_frame: 0,
            end_frame_exclusive: 180,
            source_start_frame: 0,
            transition_in_frames: 0,
            transition_out_frames: 0,
          },
        ],
        events: [
          { id: "travel-start", scene_id: "c04-flow-mechanism", frame: 15, type: "reveal_start" },
          { id: "mid-mechanism", scene_id: "c04-flow-mechanism", frame: 75, type: "proof" },
          { id: "hold", scene_id: "c04-flow-mechanism", frame: 135, type: "hold_start" },
        ],
        parent_slot: null,
        audio_owner: "job",
      });
      const bundle = buildBundle({
        video,
        outdir: join(SCRATCH, "bundles", "c04"),
        jobId: "mg032-c04-mechanism",
        timeline: timelinePath,
        beatsSeconds: [1.0, 5.667],
      });
      assertEq(bundle.record.verdict, "complete", "C04 bundle verdict");
      const caseDoc = loadCommittedCase("c04-mechanism.case.json");
      const { record, exitCode } = evaluateMotionProof({
        caseDoc,
        videoPath: video,
        coverageRecordPath: bundle.coveragePath,
        outputDir: join(SCRATCH, "proofs", "c04"),
        diagramScenePath: docPath,
      });
      assertEq(exitCode, 0, "C04 exit code");
      assertEq(record.verdict, "pass", "C04 verdict");
      assertTrue(
        record.assertions.every((a) => a.verdict === "pass"),
        `every C04 checkpoint passes: ${JSON.stringify(record.assertions.map((a) => [a.frame, a.verdict, a.detail]))}`
      );
      recordCase("c04_mechanism", {
        verdict: record.verdict,
        exit_code: exitCode,
        assertions: record.assertions.map((a) => ({
          frame: a.frame,
          expected: a.expected,
          geometry_measured: a.geometry_measured,
          raster_measured: a.raster_measured,
        })),
        clip_frames: record.clip?.frames,
      });
    }
  );

  // ----- Acceptance case 4: depth claims. Without occlusion or depth
  // evidence the claim is refused by name; with genuine occlusion
  // evidence it passes on measurement.
  check("acceptance 4a: a depth claim without depth or occlusion evidence is REFUSED by name", () => {
    const { video, coveragePath } = requireSetup();
    const caseDoc: MotionProofCase = {
      schema_version: "1.0",
      kind: "motion_proof_case",
      id: "depth-claim-unproven",
      job_id: "fixture-powerpoint-graphic",
      scene_id: "bar-01",
      component_id: "C10",
      subjects: [{ id: "hero-object", role: "layered_subject" }],
      transformation: {
        kind: "depth_transit",
        interval: { start_frame: 15, end_frame_exclusive: 75 },
        claims_depth: true,
      },
      checkpoints: [
        { frame: 0, role: "initial" },
        { frame: 45, role: "proof" },
        { frame: 75, role: "final" },
      ],
      evidence_required: ["geometry", "decoded_frame", "full_fps_clip"],
      judgment: { mode: "automated" },
    };
    const { record, exitCode } = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: coveragePath,
      outputDir: join(SCRATCH, "proofs", "depth-refused"),
    });
    assertEq(exitCode, 3, "depth refusal exit code");
    assertEq(record.verdict, "refused", "depth refusal verdict");
    assertEq(record.category, "MG_CAPABILITY_UNSUPPORTED", "depth refusal category");
    assertTrue(
      record.findings.some((f) => /occlusion/.test(f.message)),
      `the refusal names the missing occlusion evidence: ${JSON.stringify(record.findings)}`
    );
    recordCase("depth_refused_no_evidence", {
      verdict: record.verdict,
      exit_code: exitCode,
      category: record.category,
      finding: record.findings[0]?.message,
    });
  });

  check("acceptance 4b: occlusion evidence claimed but no occlusion checkpoints is REFUSED", () => {
    const { video, coveragePath } = requireSetup();
    const caseDoc: MotionProofCase = {
      schema_version: "1.0",
      kind: "motion_proof_case",
      id: "depth-claim-empty-occlusion",
      job_id: "fixture-powerpoint-graphic",
      scene_id: "bar-01",
      component_id: "C10",
      subjects: [{ id: "hero-object", role: "layered_subject" }],
      transformation: {
        kind: "depth_transit",
        interval: { start_frame: 15, end_frame_exclusive: 75 },
        claims_depth: true,
      },
      checkpoints: [
        { frame: 0, role: "initial" },
        { frame: 45, role: "proof" },
        { frame: 75, role: "final" },
      ],
      evidence_required: ["decoded_frame", "occlusion"],
      judgment: { mode: "automated" },
    };
    const { record, exitCode } = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: coveragePath,
      outputDir: join(SCRATCH, "proofs", "depth-refused-empty"),
    });
    assertEq(exitCode, 3, "empty occlusion exit code");
    assertEq(record.category, "MG_CAPABILITY_UNSUPPORTED", "empty occlusion category");
    recordCase("depth_refused_empty_occlusion", {
      verdict: record.verdict,
      exit_code: exitCode,
      category: record.category,
    });
  });

  check("acceptance 4c: a depth-map-only evidence plan is REFUSED (family not implemented, named honestly)", () => {
    const { video, coveragePath } = requireSetup();
    const caseDoc: MotionProofCase = {
      schema_version: "1.0",
      kind: "motion_proof_case",
      id: "depth-claim-depth-map-only",
      job_id: "fixture-powerpoint-graphic",
      scene_id: "bar-01",
      component_id: "C10",
      subjects: [{ id: "hero-object", role: "layered_subject" }],
      transformation: {
        kind: "depth_transit",
        interval: { start_frame: 15, end_frame_exclusive: 75 },
        claims_depth: true,
      },
      checkpoints: [
        { frame: 0, role: "initial" },
        { frame: 45, role: "proof" },
        { frame: 75, role: "final" },
      ],
      evidence_required: ["depth"],
      judgment: { mode: "automated" },
    };
    const { record, exitCode } = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: coveragePath,
      outputDir: join(SCRATCH, "proofs", "depth-refused-map"),
    });
    assertEq(exitCode, 3, "depth-map-only exit code");
    assertEq(record.category, "MG_CAPABILITY_UNSUPPORTED", "depth-map-only category");
    assertTrue(
      record.findings.some((f) => /not an implemented measurement family/.test(f.message)),
      `the refusal names the unimplemented family: ${JSON.stringify(record.findings)}`
    );
    recordCase("depth_refused_map_only", {
      verdict: record.verdict,
      exit_code: exitCode,
      category: record.category,
    });
  });

  await checkAsync(
    "acceptance 4d: a depth claim WITH genuine occlusion evidence PASSES on measured visibility",
    async () => {
      // A subject slab travels left to right and passes BEHIND a fixed
      // pillar: fully visible at frames 10 and 170, 80 percent covered
      // at frame 90. Built from three lavfi color sources composited
      // with overlay (drawbox in this ffmpeg build cannot evaluate a
      // per-frame x expression; overlay's n is the frame counter, so
      // the subject's left edge at frame f is exactly 100 + 8f).
      const video = join(SCRATCH, "videos", "occlusion.mp4");
      mkdirSync(join(SCRATCH, "videos"), { recursive: true });
      const made = run("ffmpeg", [
        "-y",
        "-v", "error",
        "-f", "lavfi",
        "-i", "color=c=0xF7F4EE:s=1920x1080:r=30:d=6",
        "-f", "lavfi",
        "-i", "color=c=0xC04A26:s=200x100:r=30:d=6",
        "-f", "lavfi",
        "-i", "color=c=0x192A38:s=200x200:r=30:d=6",
        "-filter_complex",
        "[0:v][1:v]overlay=x='100+8*(n-1)':y=490:shortest=1[mid];" +
          "[mid][2:v]overlay=x=860:y=440:shortest=1[out]",
        "-map", "[out]",
        "-frames:v", "180",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        video,
      ]);
      assertEq(made.status, 0, `occlusion video synthesizes: ${made.stderr.slice(-300)}`);
      const timelinePath = join(SCRATCH, "timelines", "occlusion.timeline.json");
      writeJson(timelinePath, {
        schema_version: "2.0",
        job_id: "mg032-occlusion",
        fps: 30,
        total_frames: 180,
        scenes: [
          {
            id: "depth-occlusion",
            start_frame: 0,
            end_frame_exclusive: 180,
            source_start_frame: 0,
            transition_in_frames: 0,
            transition_out_frames: 0,
          },
        ],
        events: [
          { id: "behind-pillar", scene_id: "depth-occlusion", frame: 90, type: "proof" },
        ],
        parent_slot: null,
        audio_owner: "job",
      });
      const bundle = buildBundle({
        video,
        outdir: join(SCRATCH, "bundles", "occlusion"),
        jobId: "mg032-occlusion",
        timeline: timelinePath,
        beatsSeconds: [0.333, 3.0, 5.667],
      });
      assertEq(bundle.record.verdict, "complete", "occlusion bundle verdict");
      const caseDoc: MotionProofCase = {
        schema_version: "1.0",
        kind: "motion_proof_case",
        id: "depth-occlusion-pass",
        job_id: "mg032-occlusion",
        scene_id: "depth-occlusion",
        component_id: "C10",
        subjects: [{ id: "hero-object", role: "layered_subject" }],
        subject_appearance: { color: "#C04A26" },
        subject_region: { x: 0, y: 440, width: 1920, height: 200 },
        transformation: {
          kind: "depth_transit",
          interval: { start_frame: 10, end_frame_exclusive: 171 },
          claims_depth: true,
        },
        checkpoints: [
          { frame: 10, role: "initial" },
          { frame: 90, role: "proof" },
          { frame: 170, role: "final" },
        ],
        occlusion_checkpoints: [
          { subject_id: "hero-object", occluder_id: "pillar", frame: 10, expected_visible_fraction: 1 },
          { subject_id: "hero-object", occluder_id: "pillar", frame: 90, expected_visible_fraction: 0.2 },
          { subject_id: "hero-object", occluder_id: "pillar", frame: 170, expected_visible_fraction: 1 },
        ],
        evidence_required: ["decoded_frame", "occlusion", "full_fps_clip"],
        judgment: { mode: "automated" },
        tolerances: { visible_fraction: 0.12 },
      };
      const { record, exitCode } = evaluateMotionProof({
        caseDoc,
        videoPath: video,
        coverageRecordPath: bundle.coveragePath,
        outputDir: join(SCRATCH, "proofs", "occlusion"),
      });
      assertEq(exitCode, 0, "occlusion exit code");
      assertEq(record.verdict, "pass", "occlusion verdict");
      const mid = record.occlusion?.find((o) => o.frame === 90);
      assertTrue(
        mid !== undefined &&
          mid.measured_visible_fraction !== null &&
          Math.abs((mid.measured_visible_fraction as number) - 0.2) <= 0.12,
        `the occluded frame measures about 0.2 visible: ${JSON.stringify(record.occlusion)}`
      );
      recordCase("occlusion_positive", {
        verdict: record.verdict,
        exit_code: exitCode,
        occlusion: record.occlusion,
        clip_frames: record.clip?.frames,
      });
    }
  );

  // ----- Human judgment path: semantic cases are never auto-passed.
  check("human path: a semantic case without a verdict record returns needs_human_judgment", () => {
    const { video, coveragePath } = requireSetup();
    const caseDoc: MotionProofCase = {
      schema_version: "1.0",
      kind: "motion_proof_case",
      id: "semantic-emphasis-case",
      job_id: "fixture-powerpoint-graphic",
      scene_id: "bar-01",
      component_id: "C05",
      subjects: [{ id: "bar-a", role: "data_mark" }],
      transformation: { kind: "semantic_change", interval: null, claims_depth: false },
      checkpoints: [
        { frame: 0, role: "initial" },
        { frame: 45, role: "proof" },
        { frame: 75, role: "final" },
      ],
      evidence_required: ["decoded_frame"],
      judgment: {
        mode: "human",
        reason: "whether the emphasis shift reads as an endorsement is a semantic judgment automation must not fabricate",
      },
    };
    const missing = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: coveragePath,
      outputDir: join(SCRATCH, "proofs", "human-missing"),
    });
    assertEq(missing.exitCode, 3, "human-missing exit code");
    assertEq(missing.record.verdict, "needs_human_judgment", "human-missing verdict");
    assertEq(missing.record.category, "MG_INPUT_MISSING", "human-missing category");

    const approved: HumanVerdict = {
      reviewer_id: "mg032-fixture-reviewer",
      decision: "approved",
      reviewed_at: "2026-10-14T12:00:00Z",
      note: "fixture verdict record for the runner; the emphasis reads as data ordering, not endorsement",
    };
    const ok = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: coveragePath,
      outputDir: join(SCRATCH, "proofs", "human-approved"),
      humanVerdict: approved,
    });
    assertEq(ok.exitCode, 0, "human-approved exit code");
    assertEq(ok.record.verdict, "pass", "human-approved verdict");
    assertTrue(
      ok.record.assertions.every((a) => /human verdict/.test(a.detail)),
      "human-approved assertions name their human source, not a measurement"
    );

    const rejected: HumanVerdict = { ...approved, decision: "rejected" };
    const no = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: coveragePath,
      outputDir: join(SCRATCH, "proofs", "human-rejected"),
      humanVerdict: rejected,
    });
    assertEq(no.exitCode, 6, "human-rejected exit code");
    assertEq(no.record.verdict, "fail", "human-rejected verdict");
    assertEq(no.record.category, "MG_FAKE_MOTION", "human-rejected category");
    recordCase("human_judgment", {
      missing: { verdict: missing.record.verdict, exit_code: missing.exitCode },
      approved: { verdict: ok.record.verdict, exit_code: ok.exitCode },
      rejected: { verdict: no.record.verdict, exit_code: no.exitCode },
    });
  });

  // ----- Coverage honesty: an assertion on an incomplete bundle
  // cannot pass.
  await checkAsync(
    "coverage: a truncated video with an incomplete bundle FAILS as MG_COVERAGE_INCOMPLETE",
    async () => {
      const { video } = requireSetup();
      const truncated = join(SCRATCH, "videos", "c05-truncated.mp4");
      const cut = run("ffmpeg", [
        "-y",
        "-v", "error",
        "-i", video,
        "-frames:v", "90",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        truncated,
      ]);
      assertEq(cut.status, 0, `truncation renders: ${cut.stderr.slice(-300)}`);
      const bundle = buildBundle({
        video: truncated,
        outdir: join(SCRATCH, "bundles", "c05-truncated"),
        jobId: "fixture-powerpoint-graphic",
        timeline: join(c05JobDir, "timeline.json"),
        beatsSeconds: [1.5],
      });
      assertTrue(
        bundle.record.verdict !== "complete",
        `the bundle over the truncated video is honestly incomplete (verdict ${String(bundle.record.verdict)}, build exit ${bundle.exitCode})`
      );
      const caseDoc = loadCommittedCase("c05-bar-reveal.case.json");
      const { record, exitCode } = evaluateMotionProof({
        caseDoc,
        videoPath: truncated,
        coverageRecordPath: bundle.coveragePath,
        outputDir: join(SCRATCH, "proofs", "truncated"),
        jobDir: c05JobDir,
      });
      assertEq(exitCode, 6, "incomplete-bundle exit code");
      assertEq(record.verdict, "fail", "incomplete-bundle verdict");
      assertEq(record.category, "MG_COVERAGE_INCOMPLETE", "incomplete-bundle category");
      recordCase("incomplete_bundle", {
        verdict: record.verdict,
        exit_code: exitCode,
        category: record.category,
        bundle_verdict: bundle.record.verdict,
      });
    }
  );

  // ----- Binding honesty: wrong artifact or wrong job is refused.
  check("binding: the decoy's coverage record against the real video is REFUSED as MG_HASH_MISMATCH", () => {
    const { video } = requireSetup();
    assertTrue(decoyCoveragePath !== null, "the decoy bundle exists");
    const caseDoc = loadCommittedCase("c05-bar-reveal.case.json");
    const { record, exitCode } = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: decoyCoveragePath as string,
      outputDir: join(SCRATCH, "proofs", "hash-mismatch"),
      jobDir: c05JobDir,
    });
    assertEq(exitCode, 9, "hash mismatch exit code");
    assertEq(record.verdict, "refused", "hash mismatch verdict");
    assertEq(record.category, "MG_HASH_MISMATCH", "hash mismatch category");
    recordCase("hash_mismatch", { verdict: record.verdict, exit_code: exitCode, category: record.category });
  });

  check("binding: a coverage record naming another job is REFUSED as MG_FOREIGN_JOB", () => {
    const { video, coveragePath } = requireSetup();
    const cloned = readJson<Record<string, unknown>>(coveragePath);
    cloned.job_id = "some-other-job";
    const clonedPath = join(SCRATCH, "bundles", "foreign-coverage.json");
    writeJson(clonedPath, cloned);
    const caseDoc = loadCommittedCase("c05-bar-reveal.case.json");
    const { record, exitCode } = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: clonedPath,
      outputDir: join(SCRATCH, "proofs", "foreign-job"),
      jobDir: c05JobDir,
    });
    assertEq(exitCode, 9, "foreign job exit code");
    assertEq(record.category, "MG_FOREIGN_JOB", "foreign job category");
    recordCase("foreign_job", { verdict: record.verdict, exit_code: exitCode, category: record.category });
  });

  check("coverage: a rough_layout_only record cannot satisfy a full-fps claim (record-level gate check)", () => {
    const { video, coveragePath } = requireSetup();
    // Record-level check: the positive bundle's own record with its
    // review binding relabeled rough. The gate reads the record; a
    // genuinely rough artifact additionally fails frame measurement,
    // which the decoy case already proves.
    const cloned = readJson<Record<string, unknown>>(coveragePath);
    const inputsRec = (cloned.inputs ?? {}) as Record<string, unknown>;
    inputsRec.review_record = {
      engine: "remotion",
      label: "rough_layout_only",
      rough_layout_only: true,
      source_hash: "fixture",
      props_hash: "fixture",
      preview_hash: "fixture",
    };
    cloned.inputs = inputsRec;
    const roughPath = join(
      SCRATCH,
      "bundles",
      "c05-positive",
      "rough-labeled-coverage.json"
    );
    writeJson(roughPath, cloned);
    const caseDoc = loadCommittedCase("c05-bar-reveal.case.json");
    const { record, exitCode } = evaluateMotionProof({
      caseDoc,
      videoPath: video,
      coverageRecordPath: roughPath,
      outputDir: join(SCRATCH, "proofs", "rough-label"),
      jobDir: c05JobDir,
    });
    assertEq(exitCode, 6, "rough label exit code");
    assertEq(record.verdict, "fail", "rough label verdict");
    assertEq(record.category, "MG_COVERAGE_INCOMPLETE", "rough label category");
    assertTrue(
      record.findings.some((f) => /rough_layout_only/.test(f.message)),
      `the finding names the rough label: ${JSON.stringify(record.findings)}`
    );
    recordCase("rough_label_gate", { verdict: record.verdict, exit_code: exitCode, category: record.category });
  });

  // ----- Schema and catalog discipline.
  check("schema: an invalid case document is REFUSED as MG_SCHEMA_INVALID, and the committed cases validate", () => {
    const { video, coveragePath } = requireSetup();
    const broken = {
      schema_version: "1.0",
      kind: "motion_proof_case",
      id: "broken-case",
      job_id: "fixture-powerpoint-graphic",
      scene_id: "bar-01",
      component_id: "C05",
      // subjects deliberately missing
      transformation: { kind: "linear_reveal", interval: { start_frame: 15, end_frame_exclusive: 75 }, claims_depth: false },
      checkpoints: [
        { frame: 0, role: "initial" },
        { frame: 45, role: "proof" },
        { frame: 75, role: "final" },
      ],
      evidence_required: ["geometry"],
      judgment: { mode: "automated" },
    };
    const { record, exitCode } = evaluateMotionProof({
      caseDoc: broken,
      videoPath: video,
      coverageRecordPath: coveragePath,
      outputDir: join(SCRATCH, "proofs", "schema-invalid"),
      jobDir: c05JobDir,
    });
    assertEq(exitCode, 2, "schema-invalid exit code");
    assertEq(record.verdict, "refused", "schema-invalid verdict");
    assertEq(record.category, "MG_SCHEMA_INVALID", "schema-invalid category");
    loadCommittedCase("c05-bar-reveal.case.json");
    loadCommittedCase("c04-mechanism.case.json");
    recordCase("schema_invalid", { verdict: record.verdict, exit_code: exitCode, category: record.category });
  });

  check("catalog: C04 and C05 carry MG-032 motion proof declarations and the test reference", () => {
    const c05 = c05Entry();
    assertEq(c05.motionProof?.transformation, "linear_reveal", "C05 declares its reveal family");
    assertEq(c05.motionProof?.depthPolicy, "not_claimed", "C05 claims no depth");
    assertTrue(
      c05.tests.some((t) => t.id === "mg032-motion-proof"),
      "C05 references the MG-032 runner"
    );
    const c04 = c04Entry();
    assertEq(c04.motionProof?.transformation, "path_transit", "C04 declares its transit family");
    assertEq(c04.motionProof?.depthPolicy, "not_claimed", "C04 claims no depth");
    assertTrue(
      c04.tests.some((t) => t.id === "mg032-motion-proof"),
      "C04 references the MG-032 runner"
    );
    recordCase("catalog_declarations", {
      c04: c04.motionProof,
      c05: c05.motionProof,
    });
  });

  measurements.cases_summary = { passed, failed };
  writeJson(join(evidenceDir(), "measurements.json"), measurements);
  console.log(`run-motion-proof: ${passed} passed, ${failed} failed`);
  if (failures.length > 0) {
    console.log("failures:\n" + failures.map((f) => ` - ${f}`).join("\n"));
  }
  process.exit(failed === 0 ? 0 : 1);
}

void main();
