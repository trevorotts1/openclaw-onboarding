// Remotion adapter tests for MG-006 (Directive Sections 6, 15.3, 17.2).
//
// These are REAL render tests against the shared runtime's provisioned
// Remotion install: no mocks. They render the C05 fixture jobs and
// measure the outputs two independent ways (instrumented geometry from
// the shared scale calculation, and decoded raster measurement of the
// rendered PNGs and of frames extracted from the rendered MP4), because
// Section 17.2 requires both: a passing dataset validator plus wrong
// rendered geometry is still a failure.
//
// Prerequisites: the shared runtime must be provisioned
// (shared-utils/motion-render-runtime/provision.sh) and the runtime
// package built (npm test runs the build first). Render outputs go to
// scratch space inside the shared runtime's gitignored .runtime dir;
// the proof stills land in 72-motion-video-plus/tests/evidence/mg006,
// whose measurements.json is a committed STATIC record (MG-043): this
// runner writes its derived measurements to scratch and compares them
// against the record, failing on drift instead of rewriting it. See
// runtime/tests/evidence-record.ts.
//
// Exit code 0 when every case passes, 1 otherwise.

import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import {
  AdapterError,
  createRegistry,
  loadCapabilityMatrix,
  loadValidatedJob,
  MotionDispatcher,
} from "../src/adapters";
import { createRemotionAdapter, RemotionAdapter } from "../src/adapters/remotion";
import type { Approval, Manifest } from "../src/validation/generated-types";
import {
  barWidthAt,
  rescaleDurationFrames,
  revealProgressAt,
  scaleBarWidth,
  toInclusiveRange,
} from "../src/remotion/frame-math";
import { instrumentedBarWidths, loadC05Job } from "../src/remotion/job-props";
import {
  decodeFrameRgb,
  measureAccentBarWidths,
  probeVideoFile,
  readPngDimensions,
} from "../src/remotion/decode";
import { checkStaticEvidenceRecord } from "./evidence-record";

// ---------------------------------------------------------------------------
// Paths and shared state
// ---------------------------------------------------------------------------

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

function runtimeStateDir(): string {
  const override = process.env.MOTION_RUNTIME_STATE_DIR;
  if (override) return resolve(override);
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

function evidenceDir(): string {
  return resolve(__dirname, "..", "..", "..", "tests", "evidence", "mg006");
}

const SCRATCH = join(runtimeStateDir(), "mg006-tests");
const PROOF_FRAMES = [0, 15, 45, 75, 150, 179];
const LANDSCAPE_TABLE: Record<number, number[]> = {
  0: [0, 0, 0],
  15: [0, 0, 0],
  45: [240, 360, 600],
  75: [480, 720, 1200],
  150: [480, 720, 1200],
  179: [480, 720, 1200],
};
const PORTRAIT_TABLE: Record<number, number[]> = {
  0: [0, 0, 0],
  15: [0, 0, 0],
  45: [148, 222, 370],
  75: [296, 444, 740],
  150: [296, 444, 740],
  179: [296, 444, 740],
};

const measurements: Record<string, unknown> = {
  item: "MG-006",
  section: "15.3 vertical slice + Section 17.2 proof states",
};
const forwardLandscapeStills = new Map<number, number[]>();

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}

function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertWidthsClose(
  actual: number[],
  expected: number[],
  tolerance: number,
  message: string
): void {
  assertEq(actual.length, expected.length, `${message}: bar count`);
  for (let i = 0; i < expected.length; i += 1) {
    if (Math.abs(actual[i] - expected[i]) > tolerance) {
      throw new Error(
        `${message}: bar ${i} expected ${expected[i]} within ${tolerance}, got ${actual[i]} ` +
          `(all: [${actual.join(", ")}] vs [${expected.join(", ")}])`
      );
    }
  }
}

function assertWidthsExact(actual: number[], expected: number[], message: string): void {
  assertWidthsClose(actual, expected, 0, message);
}

async function expectAdapterError(
  promise: Promise<unknown>,
  category: string,
  exitClass: number
): Promise<AdapterError> {
  try {
    await promise;
  } catch (err) {
    assertTrue(err instanceof AdapterError, `expected AdapterError, got ${String(err)}`);
    const e = err as AdapterError;
    assertEq(e.category, category, "error category");
    assertEq(e.exitClass, exitClass, "error exit class");
    return e;
  }
  throw new Error(`expected AdapterError ${category}, but the operation succeeded`);
}

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg006-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "fixture",
    artifact_refs: [],
    actor_id: "mg006-test-runner",
    source_event_ref: null,
    // Fixture-context approval for a fixture_only job (Section 15.3:
    // diagnostic fixture rendering never needs a forged owner approval;
    // this record is the test runner's own and says so).
    authority_status: "not_verified",
  };
}

function stageFixture(mode: string, name: string): string {
  const dir = join(SCRATCH, `staged-${name}`);
  rmSync(dir, { recursive: true, force: true });
  cpSync(join(fixturesRoot(), "modes", mode), dir, { recursive: true });
  return dir;
}

function editJson(path: string, fn: (doc: Record<string, unknown>) => void): void {
  const doc = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  fn(doc);
  writeFileSync(path, JSON.stringify(doc, null, 2) + "\n", "utf8");
}

const ALL_ADAPTERS: RemotionAdapter[] = [];

function makeDispatcher(outputDir: string): { adapter: RemotionAdapter; dispatcher: MotionDispatcher } {
  const adapter = createRemotionAdapter({ outputDir });
  ALL_ADAPTERS.push(adapter);
  return { adapter, dispatcher: new MotionDispatcher(createRegistry([adapter])) };
}

function measureStill(
  stillPath: string,
  width: number,
  height: number,
  layout: Parameters<typeof measureAccentBarWidths>[2],
  accent: string
): number[] {
  const rgb = decodeFrameRgb(stillPath, null, width, height);
  return measureAccentBarWidths(rgb, width, layout, accent);
}

// ---------------------------------------------------------------------------
// Cases
// ---------------------------------------------------------------------------

interface TestCase {
  name: string;
  run: () => Promise<void> | void;
}

const CASES: TestCase[] = [
  {
    name: "frame math: exact reveal progress, shared scale, and range adaptation at the Section 17.2 anchors",
    run: () => {
      const motion = { startFrame: 15, endFrameExclusive: 75, authoredFps: 30 };
      const expectedProgress: Record<number, number> = { 0: 0, 15: 0, 45: 0.5, 75: 1, 150: 1, 179: 1 };
      for (const [frame, progress] of Object.entries(expectedProgress)) {
        assertEq(revealProgressAt(Number(frame), 30, motion), progress, `progress at frame ${frame} (30 fps)`);
      }
      // Same seconds at 60 fps: reveal runs frames 30..150.
      assertEq(revealProgressAt(30, 60, motion), 0, "progress at 0.5 s (60 fps frame 30)");
      assertEq(revealProgressAt(90, 60, motion), 0.5, "progress at 1.5 s (60 fps frame 90)");
      assertEq(revealProgressAt(150, 60, motion), 1, "progress at 2.5 s (60 fps frame 150)");
      // The shared scale, exact integers for the fixture values.
      assertEq(scaleBarWidth(12, [0, 30], 1200), 480, "landscape scale for value 12");
      assertEq(scaleBarWidth(18, [0, 30], 1200), 720, "landscape scale for value 18");
      assertEq(scaleBarWidth(30, [0, 30], 1200), 1200, "landscape scale for value 30");
      assertEq(scaleBarWidth(12, [0, 30], 740), 296, "portrait scale for value 12");
      assertEq(scaleBarWidth(18, [0, 30], 740), 444, "portrait scale for value 18");
      assertEq(barWidthAt(30, [0, 30], 1200, 45, 30, motion), 600, "bar width at half reveal");
      // Half-open to inclusive adaptation (Section 5.4).
      const full = toInclusiveRange({ startFrame: 0, endFrameExclusive: 180 });
      assertEq(full[0], 0, "inclusive range start");
      assertEq(full[1], 179, "inclusive range end for [0, 180)");
      const partial = toInclusiveRange({ startFrame: 15, endFrameExclusive: 75 });
      assertEq(partial[1], 74, "inclusive range end for [15, 75)");
      assertEq(rescaleDurationFrames(180, 30, 60), 360, "duration rescale 30 to 60 fps");
    },
  },
  {
    name: "probe: probeRuntime reads the shared runtime lock and reports the measured engine",
    run: async () => {
      const { dispatcher } = makeDispatcher(join(SCRATCH, "probe"));
      const evidence = await dispatcher.probe("remotion");
      const lockPath = join(runtimeStateDir(), "runtime-lock.json");
      assertTrue(existsSync(lockPath), `runtime lock exists at ${lockPath} (provision the shared runtime first)`);
      const lock = JSON.parse(readFileSync(lockPath, "utf8")) as {
        result: string;
        packages: Record<string, string>;
        browser?: { revision?: string };
        timestamp: string;
      };
      const lockId = realpathSync(join(runtimeStateDir(), "current")).split("/").pop() as string;
      assertEq(evidence.status, "ready", "probe status");
      assertEq(evidence.runtime.engineVersion, lock.packages.remotion, "probe engine version matches the lock");
      assertEq(evidence.runtime.runtimeLockId, lockId, "probe lock identity matches .runtime/current");
      assertEq(lock.result, "pass", "lock result");
      assertTrue(
        evidence.capabilities?.mediaTypes.includes("image/png") ?? false,
        "capabilities claim the probed media type (rendered PNG)"
      );
      assertEq(evidence.capabilities?.codecs.length, 0, "no codec claimed beyond the probe evidence");
      measurements.runtime = {
        engineVersion: evidence.runtime.engineVersion,
        runtimeLockId: lockId,
        lockTimestamp: lock.timestamp,
        browserRevision: lock.browser?.revision ?? null,
        nodeVersion: evidence.runtime.nodeVersion,
        platform: evidence.runtime.platform,
      };
    },
  },
  {
    name: "validate: the powerpoint fixture validates for the remotion engine through the dispatcher",
    run: async () => {
      const { dispatcher } = makeDispatcher(join(SCRATCH, "validate"));
      const matrix = loadCapabilityMatrix();
      const dir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const outcome = await dispatcher.validate(dir, { matrix });
      assertTrue(outcome.evidence.valid, `job validates (findings: ${JSON.stringify(outcome.evidence.findings)})`);
      assertEq(outcome.routing.primaryEngine, "remotion", "chart job routes to remotion");
      assertEq(outcome.evidence.runtime.engineVersion, "4.0.535", "validate receipt names the runtime");
    },
  },
  {
    name: "render final: six-second landscape video, poster, and exact proof states (instrumented + decoded)",
    run: async () => {
      const outDir = join(SCRATCH, "landscape");
      const { adapter, dispatcher } = makeDispatcher(outDir);
      const matrix = loadCapabilityMatrix();
      const dir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const job = loadValidatedJob(dir);
      const loaded = loadC05Job(job);
      measurements.font = {
        requirementId: loaded.font.requirementId,
        alias: loaded.font.alias,
        family: loaded.font.family,
        files: loaded.font.files.map((f) => ({ weight: f.weight, path: f.path, sha256: f.sha256 })),
      };
      measurements.bundle = { bundleKeys: [] as string[] };

      const finalOutcome = await dispatcher.renderFinal(dir, fixtureApproval(job.jobId), {
        matrix,
        timeoutMs: 900_000,
      });
      const finalEvidence = finalOutcome.evidence;
      assertEq(finalEvidence.kind, "final", "final evidence kind");
      assertEq(finalEvidence.artifacts.length, 2, "final artifacts: mp4 + poster");
      const mp4 = finalEvidence.outputPaths[0];
      const poster = finalEvidence.outputPaths[1];
      assertTrue(existsSync(mp4), "final mp4 exists");
      assertEq(finalEvidence.artifacts[0].sha256, sha256File(mp4), "mp4 artifact hash matches the file");
      const probe = probeVideoFile(mp4);
      assertEq(probe.width, 1920, "video width");
      assertEq(probe.height, 1080, "video height");
      assertEq(probe.frameCount, 180, "video frame count (M01)");
      assertEq(`${probe.fpsNumerator}/${probe.fpsDenominator}`, "30/1", "video frame rate (M01)");
      assertTrue(
        Math.abs(probe.durationSeconds - 6.0) <= 1 / 30 + 0.001,
        `video duration ${probe.durationSeconds}s within one frame of 6.0s (M01)`
      );
      const posterDims = readPngDimensions(poster);
      assertEq(posterDims?.width, 1920, "poster width");
      assertEq(posterDims?.height, 1080, "poster height");
      measurements.videos = {
        final: {
          path: mp4,
          sizeBytes: statSync(mp4).size,
          sha256: sha256File(mp4),
          probe,
        },
        poster: { path: poster, sizeBytes: statSync(poster).size, sha256: sha256File(poster) },
      };
      (measurements.bundle as { bundleKeys: string[] }).bundleKeys = adapter
        .describeBundles()
        .map((b) => b.bundleKey);

      // Proof states, measured three ways.
      const proofStates: Record<string, unknown>[] = [];
      for (const frame of PROOF_FRAMES) {
        const expected = LANDSCAPE_TABLE[frame];
        const instrumented = instrumentedBarWidths(loaded.props, frame);
        assertWidthsExact(instrumented, expected, `landscape instrumented frame ${frame}`);
        const stillOutcome = await dispatcher.renderStill(dir, frame, { matrix, timeoutMs: 300_000 });
        const stillPath = stillOutcome.evidence.outputPaths[0];
        const fromStill = measureStill(
          stillPath,
          1920,
          1080,
          loaded.props.design.layout,
          loaded.props.design.colors.accent
        );
        assertWidthsClose(fromStill, expected, 2, `landscape decoded-from-still frame ${frame}`);
        forwardLandscapeStills.set(frame, fromStill);
        const frameRgb = decodeFrameRgb(mp4, frame, 1920, 1080);
        const fromVideo = measureAccentBarWidths(
          frameRgb,
          1920,
          loaded.props.design.layout,
          loaded.props.design.colors.accent
        );
        assertWidthsClose(fromVideo, expected, 2, `landscape decoded-from-video frame ${frame}`);
        proofStates.push({
          frame,
          expected,
          instrumented,
          decodedFromStill: fromStill,
          decodedFromVideo: fromVideo,
          stillPath,
        });
      }
      measurements.proofStatesLandscape = proofStates;
    },
  },
  {
    name: "render preview: same source, props, and timing as the final (M15 parity)",
    run: async () => {
      const outDir = join(SCRATCH, "landscape");
      const { dispatcher } = makeDispatcher(outDir);
      const matrix = loadCapabilityMatrix();
      const dir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const outcome = await dispatcher.renderPreview(dir, { matrix, timeoutMs: 900_000 });
      const mp4 = outcome.evidence.outputPaths[0];
      const probe = probeVideoFile(mp4);
      assertEq(probe.frameCount, 180, "preview frame count");
      assertEq(probe.width, 1920, "preview width");
      const job = loadValidatedJob(dir);
      const loaded = loadC05Job(job);
      const rgb = decodeFrameRgb(mp4, 75, 1920, 1080);
      const widths = measureAccentBarWidths(rgb, 1920, loaded.props.design.layout, loaded.props.design.colors.accent);
      assertWidthsClose(widths, LANDSCAPE_TABLE[75], 2, "preview frame 75 geometry matches the final's");
      (measurements.videos as Record<string, unknown>).preview = {
        path: mp4,
        sizeBytes: statSync(mp4).size,
        sha256: sha256File(mp4),
        probe,
      };
    },
  },
  {
    name: "portrait variant: vsl_mobile stills match the portrait proof table (genuine recomposition)",
    run: async () => {
      const outDir = join(SCRATCH, "portrait");
      const { dispatcher } = makeDispatcher(outDir);
      const matrix = loadCapabilityMatrix();
      const dir = join(fixturesRoot(), "modes", "vsl_mobile");
      const routed = dispatcher.routeJob(dir, { matrix });
      assertEq(routed.routing.primaryEngine, "remotion", "mobile chart job routes to remotion");
      const job = loadValidatedJob(dir);
      const loaded = loadC05Job(job);
      assertEq(loaded.props.canvas.width, 1080, "portrait canvas width");
      assertEq(loaded.props.canvas.height, 1920, "portrait canvas height");
      const proofStates: Record<string, unknown>[] = [];
      for (const frame of PROOF_FRAMES) {
        const expected = PORTRAIT_TABLE[frame];
        const instrumented = instrumentedBarWidths(loaded.props, frame);
        assertWidthsExact(instrumented, expected, `portrait instrumented frame ${frame}`);
        const stillOutcome = await dispatcher.renderStill(dir, frame, { matrix, timeoutMs: 300_000 });
        const stillPath = stillOutcome.evidence.outputPaths[0];
        const dims = readPngDimensions(stillPath);
        assertEq(dims?.width, 1080, `portrait still frame ${frame} width`);
        assertEq(dims?.height, 1920, `portrait still frame ${frame} height`);
        const decoded = measureStill(
          stillPath,
          1080,
          1920,
          loaded.props.design.layout,
          loaded.props.design.colors.accent
        );
        assertWidthsClose(decoded, expected, 2, `portrait decoded frame ${frame}`);
        proofStates.push({ frame, expected, instrumented, decodedFromStill: decoded, stillPath });
      }
      measurements.proofStatesPortrait = proofStates;
    },
  },
  {
    name: "seek determinism: stills rendered in shuffled order measure identically to forward order",
    run: async () => {
      const outDir = join(SCRATCH, "seek");
      const { adapter } = makeDispatcher(outDir);
      const dir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const job = loadValidatedJob(dir);
      const loaded = loadC05Job(job);
      const order = [179, 45, 0, 150, 75, 15];
      const results: Record<string, number[]> = {};
      for (const frame of order) {
        const evidence = await adapter.renderStill(job, frame);
        const decoded = measureStill(
          evidence.outputPaths[0],
          1920,
          1080,
          loaded.props.design.layout,
          loaded.props.design.colors.accent
        );
        results[String(frame)] = decoded;
        const forward = forwardLandscapeStills.get(frame);
        assertTrue(forward !== undefined, `forward measurement for frame ${frame} exists`);
        assertWidthsExact(decoded, forward as number[], `seek frame ${frame} equals forward render`);
      }
      measurements.seekDeterminism = { order, decodedByFrame: results, matchesForwardOrder: true };
    },
  },
  {
    name: "two datasets, one component: a second dataset renders through the same composition to its own scale",
    run: async () => {
      const staged = stageFixture("powerpoint_graphic", "dataset-b");
      editJson(join(staged, "data", "bars.json"), (d) => {
        d.domain = [0, 40];
        d.rows = [
          { id: "a", label: "Group A", value: 10 },
          { id: "b", label: "Group B", value: 20 },
          { id: "c", label: "Group C", value: 40 },
        ];
      });
      const outDir = join(SCRATCH, "dataset-b");
      const { dispatcher } = makeDispatcher(outDir);
      const matrix = loadCapabilityMatrix();
      const job = loadValidatedJob(staged);
      const loaded = loadC05Job(job);
      const frames: Record<string, unknown> = {};
      const expectations: Record<number, number[]> = { 45: [150, 300, 600], 75: [300, 600, 1200] };
      for (const frame of [45, 75]) {
        const expected = expectations[frame];
        const instrumented = instrumentedBarWidths(loaded.props, frame);
        assertWidthsExact(instrumented, expected, `dataset B instrumented frame ${frame}`);
        const outcome = await dispatcher.renderStill(staged, frame, { matrix, timeoutMs: 300_000 });
        const decoded = measureStill(
          outcome.evidence.outputPaths[0],
          1920,
          1080,
          loaded.props.design.layout,
          loaded.props.design.colors.accent
        );
        assertWidthsClose(decoded, expected, 2, `dataset B decoded frame ${frame}`);
        frames[String(frame)] = { expected, instrumented, decodedFromStill: decoded };
      }
      measurements.secondDataset = {
        domain: [0, 40],
        values: [10, 20, 40],
        frames,
      };
    },
  },
  {
    name: "fps change preserves seconds: at 60 fps the reveal occupies 0.5 s to 2.5 s with doubled frame indices",
    run: async () => {
      const outDir = join(SCRATCH, "fps60");
      const { adapter } = makeDispatcher(outDir);
      const dir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const job = loadValidatedJob(dir);
      const loaded60 = loadC05Job(job, { fpsOverride: 60 });
      assertEq(loaded60.durationFrames, 360, "60 fps duration in frames");
      const checks: Record<number, number[]> = {
        30: [0, 0, 0],
        90: [240, 360, 600],
        150: [480, 720, 1200],
        359: [480, 720, 1200],
      };
      const frames: Record<string, unknown> = {};
      for (const [frameText, expected] of Object.entries(checks)) {
        const frame = Number(frameText);
        const instrumented = instrumentedBarWidths(loaded60.props, frame);
        assertWidthsExact(instrumented, expected, `60 fps instrumented frame ${frame}`);
        const evidence = await adapter.renderStill(job, frame, { fpsOverride: 60 });
        const decoded = measureStill(
          evidence.outputPaths[0],
          1920,
          1080,
          loaded60.props.design.layout,
          loaded60.props.design.colors.accent
        );
        assertWidthsClose(decoded, expected, 2, `60 fps decoded frame ${frame}`);
        frames[frameText] = { expected, instrumented, decodedFromStill: decoded };
      }
      measurements.fps60 = { durationFrames: 360, frames };
    },
  },
  {
    name: "inspectMotion: both scene assertions pass on instrumented and decoded evidence",
    run: async () => {
      const outDir = join(SCRATCH, "landscape");
      const { dispatcher } = makeDispatcher(outDir);
      const matrix = loadCapabilityMatrix();
      const dir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const outcome = await dispatcher.inspectMotion(
        dir,
        { startFrame: 0, endFrameExclusive: 180 },
        { matrix, timeoutMs: 300_000 }
      );
      assertEq(outcome.evidence.assertionsChecked, 2, "assertions checked");
      assertEq(outcome.evidence.assertionsPassed, 2, "assertions passed");
      assertTrue(
        outcome.evidence.observations.some((o) => o.includes("half-reveal")),
        "observations cover the half-reveal assertion"
      );
      assertTrue(
        outcome.evidence.observations.some((o) => o.includes("final-ratios")),
        "observations cover the final-ratios assertion"
      );
      measurements.inspectMotion = { observations: outcome.evidence.observations };
    },
  },
  {
    name: "negative: a missing dataset file fails validation and a direct render claims no artifact",
    run: async () => {
      const staged = stageFixture("powerpoint_graphic", "missing-dataset");
      rmSync(join(staged, "data", "bars.json"));
      const outDir = join(SCRATCH, "missing-dataset");
      const { adapter, dispatcher } = makeDispatcher(outDir);
      const matrix = loadCapabilityMatrix();
      const outcome = await dispatcher.validate(staged, { matrix });
      assertEq(outcome.evidence.valid, false, "job with missing dataset is invalid for the engine");
      assertEq(outcome.evidence.firstErrorCategory, "MG_SCHEMA_INVALID", "first error category");
      assertTrue(
        outcome.evidence.findings.some((f) => f.message.includes("data/bars.json")),
        "finding names the missing dataset file"
      );
      const job = loadValidatedJob(staged);
      const err = await expectAdapterError(adapter.renderStill(job, 45), "MG_SCHEMA_INVALID", 2);
      assertTrue(err.message.includes("data/bars.json"), "render error names the missing dataset");
      assertTrue(
        !existsSync(join(outDir, "renders")),
        "no artifact directory was produced by the failed render"
      );
      measurements.negatives = [
        ...(measurements.negatives as unknown[] ?? []),
        { case: "missing-dataset", category: err.category, exitClass: err.exitClass, message: err.message },
      ];
    },
  },
  {
    name: "negative: a wrong-mode canvas is rejected by the contracts layer before any render",
    run: async () => {
      const staged = stageFixture("powerpoint_graphic", "wrong-canvas");
      editJson(join(staged, "manifest.json"), (m) => {
        const canvas = m.canvas as Record<string, unknown>;
        canvas.width = 1080;
        canvas.height = 1920;
      });
      const { dispatcher } = makeDispatcher(join(SCRATCH, "wrong-canvas"));
      const matrix = loadCapabilityMatrix();
      const err = await expectAdapterError(
        dispatcher.renderStill(staged, 45, { matrix }),
        "MG_MODE_MISMATCH",
        2
      );
      measurements.negatives = [
        ...(measurements.negatives as unknown[] ?? []),
        { case: "wrong-mode-canvas", category: err.category, exitClass: err.exitClass, message: err.message },
      ];
    },
  },
  {
    name: "negative: missing font bytes fail the render instead of substituting a font",
    run: async () => {
      const adapter = createRemotionAdapter({
        outputDir: join(SCRATCH, "missing-font"),
        fontSearchDirs: [],
      });
      const dir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const job = loadValidatedJob(dir);
      const err = await expectAdapterError(adapter.renderStill(job, 45), "MG_SCHEMA_INVALID", 2);
      assertTrue(err.message.includes("LiberationSans"), "error names the unresolved font file");
      assertTrue(err.message.includes("substitution"), "error states the no-substitution rule");
      measurements.negatives = [
        ...(measurements.negatives as unknown[] ?? []),
        { case: "missing-font", category: err.category, exitClass: err.exitClass, message: err.message },
      ];
    },
  },
  {
    name: "negative: a scene missing required copy fails in the adapter with a named prop",
    run: async () => {
      const staged = stageFixture("powerpoint_graphic", "missing-prop");
      editJson(join(staged, "scenes", "bar-01.json"), (s) => {
        const copy = s.copy as Record<string, unknown>;
        delete copy.headline;
      });
      const { adapter } = makeDispatcher(join(SCRATCH, "missing-prop"));
      // The job object is built by hand on purpose: the dispatcher's
      // contracts gate would (correctly) reject this job first, and
      // this case proves the ADAPTER's own missing-prop guard fires
      // when it is handed a job whose scene lacks required copy.
      const manifest = JSON.parse(readFileSync(join(staged, "manifest.json"), "utf8")) as Manifest;
      const job = { jobDir: staged, jobId: manifest.job_id, manifest };
      const err = await expectAdapterError(adapter.renderStill(job, 45), "MG_SCHEMA_INVALID", 2);
      assertTrue(err.message.includes("copy.headline"), "error names the missing prop");
      measurements.negatives = [
        ...(measurements.negatives as unknown[] ?? []),
        { case: "missing-prop", category: err.category, exitClass: err.exitClass, message: err.message },
      ];
    },
  },
  {
    name: "bundle once: every render above was served by a single bundle per source-plus-runtime hash",
    run: () => {
      // Every adapter instance created during this run reports the
      // bundles it built or reused; renders that succeeded across all
      // cases must trace back to exactly one bundle key, and that
      // bundle must exist on disk under the shared runtime state dir.
      const keys = new Set(
        ALL_ADAPTERS.flatMap((a) => a.describeBundles().map((b) => b.bundleKey))
      );
      assertEq(
        keys.size,
        1,
        `all renders in this run used exactly one bundle (found: ${[...keys].join(", ") || "none"})`
      );
      const [key] = [...keys];
      const bundleDir = join(runtimeStateDir(), "mg006-bundles", key);
      assertTrue(
        existsSync(join(bundleDir, "index.html")),
        `the shared bundle exists on disk at ${bundleDir}`
      );
      measurements.bundle = {
        bundleKeys: [key],
        note: "the single bundle key every render in the suite was served by",
      };
    },
  },
];

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<number> {
  rmSync(SCRATCH, { recursive: true, force: true });
  mkdirSync(SCRATCH, { recursive: true });
  measurements.generatedAt = new Date().toISOString();
  let passed = 0;
  let failed = 0;
  for (const c of CASES) {
    try {
      await c.run();
      passed += 1;
      console.log(`PASS ${c.name}`);
    } catch (err) {
      failed += 1;
      console.log(`FAIL ${c.name}`);
      console.log(`  ${(err as Error).message}`);
    }
  }

  // Commit the evidence: measurements plus the proof stills and poster.
  try {
    const dir = evidenceDir();
    mkdirSync(dir, { recursive: true });
    const copies: [string, string][] = [];
    for (const frame of PROOF_FRAMES) {
      copies.push([
        join(SCRATCH, "landscape", "renders", "remotion", `still-landscape-f${frame}.png`),
        join(dir, `still-landscape-f${frame}.png`),
      ]);
      copies.push([
        join(SCRATCH, "portrait", "renders", "remotion", `still-portrait-f${frame}.png`),
        join(dir, `still-portrait-f${frame}.png`),
      ]);
    }
    copies.push([
      join(SCRATCH, "landscape", "renders", "remotion", "poster-f150.png"),
      join(dir, "poster-f150.png"),
    ]);
    const evidenceFiles: string[] = [];
    for (const [src, dst] of copies) {
      if (existsSync(src)) {
        cpSync(src, dst);
        evidenceFiles.push(dst.split("/").pop() as string);
      }
    }
    measurements.evidenceFiles = evidenceFiles;
    // MG-043 static-record pattern (D-EVIDENCE-REWRITE): never rewrite
    // the committed measurements.json. Compare the derived record
    // against it and fail on drift; adoption is a reviewed copy of the
    // derived file (see runtime/tests/evidence-record.ts).
    const recordCheck = checkStaticEvidenceRecord({
      derived: measurements,
      recordPath: join(dir, "measurements.json"),
      scratchPath: join(SCRATCH, "measurements.derived.json"),
      repoRoot: resolve(__dirname, "..", "..", "..", ".."),
    });
    if (recordCheck.ok) {
      console.log(
        `Evidence written to ${dir} (${evidenceFiles.length} frames); static measurements record matches`
      );
    } else {
      failed += 1;
      console.log("FAIL static evidence record drift (tests/evidence/mg006/measurements.json):");
      for (const d of recordCheck.diffs) console.log(`  ${d}`);
      console.log(`  derived measurements: ${recordCheck.scratchPath}`);
      console.log(
        "  if this change is intentional, adopt it by copying the derived file over the record in a reviewed change"
      );
    }
  } catch (err) {
    failed += 1;
    console.log(`FAIL evidence write: ${(err as Error).message}`);
  }

  const total = passed + failed;
  console.log(`Remotion: ${passed}/${total} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
