// Preview tests for MG-024 (Directive MG-024: make previews match the
// actual composition; defect D-PREVIEW-FORCE).
//
// Real renders, decoded-pixel proof, no mocks. Coverage:
// - the shared preview planner and the full-fps motion gate (pure
//   rules, asserted against the committed expectation record);
// - Remotion: a scaled full-fps preview of the shipped C05 fixture
//   whose decoded bar landmarks agree with the final's after scaling,
//   a 9:16 job whose preview stays 9:16, identical props and source
//   hashes across final and previews, and a 15 fps rough preview that
//   exists only under the rough_layout_only label and is refused by
//   the motion gate with named findings;
// - Hyperframes: the same program on the staged C05 job retargeted to
//   the pinned CLI, including the post-encode spatial scale and the
//   rough preview's preserved seconds timing;
// - destination-size individual frames and a contact sheet;
// - the legacy scripts/render.js compatibility path: its --preview
//   must now produce a true scaled, full-fps render (it previously
//   forced 960x540 at 15 fps, and the size never reached the pixels),
//   with --rough the only reduced-fps mode, labeled.
//
// Expectations live in tests/evidence/mg024/measurements.json, a static
// record this suite asserts against and never rewrites. Curated
// frames and the contact sheet are copied into that evidence dir.
// Rendered videos stay in scratch space (the shared runtime's
// .runtime dir for Remotion, evidence/mg024/work for Hyperframes,
// git-ignored like the mg005 work dir).
//
// The legacy cases need playwright-core, render.js's one declared
// dependency (see INSTALL.md). It is installed once into a scratch
// deps dir (repo .scratch/mg024-deps) and passed via NODE_PATH, the
// same mechanism the skill's legacy flows use; the pinned version
// (1.64.1) matches the Chromium revision cached on this box.
//
// Exit code 0 when every case passes, 1 otherwise.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { createRegistry, loadValidatedJob, MotionDispatcher } from "../src/adapters";
import { RemotionAdapter, createRemotionAdapter } from "../src/adapters/remotion";
import { HyperframesAdapter } from "../src/adapters/hyperframes";
import type { Approval, Manifest } from "../src/validation/generated-types";
import type { PreviewReviewRecord } from "../src/preview/types";
import {
  checkPreviewMotionGate,
  planPreview,
  PreviewPlanError,
  hashJobSourceInputs,
  hashPropsPayload,
  extractFramePng,
  buildContactSheet,
  PREVIEW_GATE_ASPECT_MISMATCH,
  PREVIEW_GATE_FPS_MISMATCH,
  PREVIEW_GATE_ROUGH_LAYOUT,
} from "../src/preview";
import { loadC05Job, type C05Layout } from "../src/remotion/job-props";
import {
  decodeFrameRgb,
  measureAccentBarWidths,
  probeVideoFile,
  readPngDimensions,
} from "../src/remotion/decode";
import { decodePng, measureBarWidth, pixelMatches } from "../src/hyperframes/measure";

// ---------------------------------------------------------------------------
// Paths and the committed expectation record
// ---------------------------------------------------------------------------

const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const TMP_SCRATCH = join(REPO_ROOT, ".scratch", "tmp");
mkdirSync(TMP_SCRATCH, { recursive: true });
process.env.TMPDIR = TMP_SCRATCH;

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return join(SKILL_DIR, "tests", "fixtures");
}

function runtimeStateDir(): string {
  const override = process.env.MOTION_RUNTIME_STATE_DIR;
  if (override) return resolve(override);
  return join(REPO_ROOT, "shared-utils", "motion-render-runtime", ".runtime");
}

const SCRATCH = join(runtimeStateDir(), "mg024-tests");
const EVIDENCE_DIR = join(SKILL_DIR, "tests", "evidence", "mg024");
const HF_WORK = join(EVIDENCE_DIR, "work");
const LEGACY_SCRATCH = join(SCRATCH, "legacy");

interface Expectations {
  tolerances: { decodedPx: number; scaledBackPx: number; roughTimingPx: number };
  c05Landscape: {
    canvas: { width: number; height: number; fps: number; durationFrames: number };
    previewScale: number;
    previewDims: { width: number; height: number };
    frame45: number[];
    frame75: number[];
  };
  c05Portrait: {
    canvas: { width: number; height: number; fps: number; durationFrames: number };
    previewDims: { width: number; height: number };
  };
  rough: { fps: number; durationFrames: number };
  gate: { roughFindings: string[]; scaledAccepted: boolean };
  legacy: {
    durationSeconds: number;
    portrait: {
      previewDims: { width: number; height: number };
      fps: number;
      frames: number;
      barAtFrame45: { x: number; width: number };
    };
    landscape: { previewDims: { width: number; height: number }; fps: number; frames: number };
    rough: { fps: number; frames: number };
  };
}

const EXPECT = JSON.parse(
  readFileSync(join(EVIDENCE_DIR, "measurements.json"), "utf8")
) as Expectations & { item: string };

const LANDSCAPE_F75 = EXPECT.c05Landscape.frame75;
const ACCENT = "#C04A26";

// Measured values printed for the report and the evidence summary.
const measured: Record<string, unknown> = {};

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

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg024-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "fixture",
    artifact_refs: [],
    actor_id: "mg024-test-runner",
    source_event_ref: null,
    authority_status: "not_verified",
  };
}

function scaledLayout(layout: C05Layout, scale: number): C05Layout {
  return {
    ...layout,
    plot: {
      x: Math.round(layout.plot.x * scale),
      y: Math.round(layout.plot.y * scale),
      width: Math.round(layout.plot.width * scale),
      height: Math.round(layout.plot.height * scale),
    },
    bar_height: Math.round(layout.bar_height * scale),
    row_y: layout.row_y.map((y) => Math.round(y * scale)),
  };
}

function assertRecordBasics(
  record: PreviewReviewRecord | undefined,
  label: string
): PreviewReviewRecord {
  assertTrue(record !== undefined, `${label}: evidence carries a preview review record`);
  const r = record as PreviewReviewRecord;
  assertEq(r.schemaVersion, "1.0", `${label}: record schema version`);
  assertEq(r.kind, "preview", `${label}: record kind`);
  assertTrue(
    /^[0-9a-f]{64}$/.test(r.sourceHash),
    `${label}: source hash is a sha256 hex digest`
  );
  assertTrue(/^[0-9a-f]{64}$/.test(r.propsHash), `${label}: props hash is a sha256 hex digest`);
  assertTrue(/^[0-9a-f]{64}$/.test(r.previewHash), `${label}: preview hash is a sha256 hex digest`);
  return r;
}

// ---------------------------------------------------------------------------
// Cases
// ---------------------------------------------------------------------------

interface TestCase {
  name: string;
  run: () => Promise<void> | void;
}

// Shared render state, filled by earlier cases for later ones.
let remotionLandscape: {
  adapter: RemotionAdapter;
  jobDir: string;
  finalPath: string;
  scaledPath: string;
  scaledRecord: PreviewReviewRecord;
  layout: C05Layout;
} | null = null;
let hfJob: { jobDir: string; finalPath: string; scaledPath: string } | null = null;

const CASES: TestCase[] = [
  {
    name: "plan: scale preserves aspect for landscape and portrait; identity is the default",
    run: () => {
      const land = planPreview({ width: 1920, height: 1080, fps: 30 }, 180, { scale: 0.5 });
      assertEq(land.width, EXPECT.c05Landscape.previewDims.width, "landscape preview width");
      assertEq(land.height, EXPECT.c05Landscape.previewDims.height, "landscape preview height");
      assertEq(land.fps, 30, "scaled preview keeps the full fps");
      assertEq(land.durationFrames, 180, "scaled preview keeps the frame count");
      assertEq(land.label, "preview", "scaled preview label");
      const port = planPreview({ width: 1080, height: 1920, fps: 30 }, 180, { scale: 0.5 });
      assertEq(port.width, EXPECT.c05Portrait.previewDims.width, "portrait preview width");
      assertEq(port.height, EXPECT.c05Portrait.previewDims.height, "portrait preview height");
      assertTrue(port.height > port.width, "portrait preview stays vertical (9:16 in, 9:16 out)");
      const identity = planPreview({ width: 1920, height: 1080, fps: 30 }, 180);
      assertEq(identity.width, 1920, "default preview width is canonical");
      assertEq(identity.scale, 1, "default scale is 1");
      assertEq(identity.roughLayoutOnly, false, "default is not rough");
    },
  },
  {
    name: "plan: rough layout reduces fps by the documented rule and rescales duration in seconds",
    run: () => {
      const rough = planPreview({ width: 1920, height: 1080, fps: 30 }, 180, { roughLayout: true });
      assertEq(rough.fps, EXPECT.rough.fps, "rough fps at a 30 fps canvas");
      assertEq(rough.durationFrames, EXPECT.rough.durationFrames, "rough frames keep 6.0 seconds");
      assertEq(rough.label, "rough_layout_only", "rough label");
      assertEq(rough.width, 1920, "rough alone does not change spatial size");
      const rough24 = planPreview({ width: 1920, height: 1080, fps: 24 }, 144, { roughLayout: true });
      assertEq(rough24.fps, 15, "rough fps at a 24 fps canvas is the canonical 15");
      assertEq(rough24.durationFrames, 90, "rough frames at 24 fps keep the same 6.0 seconds");
      const rough12 = planPreview({ width: 1920, height: 1080, fps: 12 }, 72, { roughLayout: true });
      assertEq(rough12.fps, 6, "rough fps below a 15 fps canvas is half the authored fps");
      assertEq(rough12.durationFrames, 36, "rough frames at 12 fps keep the same 6.0 seconds");
      for (const bad of [0, -0.5, 1.5, Number.NaN]) {
        let threw = false;
        try {
          planPreview({ width: 1920, height: 1080, fps: 30 }, 180, { scale: bad });
        } catch (err) {
          threw = err instanceof PreviewPlanError;
        }
        assertTrue(threw, `scale ${String(bad)} is refused with PreviewPlanError`);
      }
    },
  },
  {
    name: "gate: rough-layout and wrong-fps records are refused with named findings; scaled full-fps passes",
    run: () => {
      const base: PreviewReviewRecord = {
        schemaVersion: "1.0",
        engine: "remotion",
        jobId: "gate-fixture",
        kind: "preview",
        label: "preview",
        roughLayoutOnly: false,
        scale: 0.5,
        scaleMethod: "render_scale",
        sourceHash: "a".repeat(64),
        propsHash: "b".repeat(64),
        previewHash: "c".repeat(64),
        final: { width: 1920, height: 1080, fps: 30, durationFrames: 180 },
        preview: { width: 960, height: 540, fps: 30, durationFrames: 180, durationSeconds: 6 },
        generatedAt: new Date().toISOString(),
      };
      const scaledVerdict = checkPreviewMotionGate(base);
      assertEq(scaledVerdict.accepted, EXPECT.gate.scaledAccepted, "scaled full-fps preview passes the gate");
      assertEq(scaledVerdict.findings.length, 0, "scaled full-fps preview has no findings");

      const rough: PreviewReviewRecord = {
        ...base,
        label: "rough_layout_only",
        roughLayoutOnly: true,
        scale: 1,
        scaleMethod: "none",
        preview: { width: 1920, height: 1080, fps: 15, durationFrames: 90, durationSeconds: 6 },
      };
      const roughVerdict = checkPreviewMotionGate(rough);
      assertEq(roughVerdict.accepted, false, "rough-layout record is refused");
      const codes = roughVerdict.findings.map((f) => f.code).sort();
      assertEq(
        JSON.stringify(codes),
        JSON.stringify([...EXPECT.gate.roughFindings].sort()),
        "rough refusal names the expected findings"
      );

      const sneaky: PreviewReviewRecord = {
        ...base,
        preview: { width: 960, height: 540, fps: 15, durationFrames: 90, durationSeconds: 6 },
      };
      const sneakyVerdict = checkPreviewMotionGate(sneaky);
      assertEq(sneakyVerdict.accepted, false, "an unlabeled 15 fps record is still refused");
      assertTrue(
        sneakyVerdict.findings.some((f) => f.code === PREVIEW_GATE_FPS_MISMATCH),
        "fps mismatch finding is named"
      );
      assertTrue(
        roughVerdict.findings.some((f) => f.code === PREVIEW_GATE_ROUGH_LAYOUT),
        "rough layout finding is named"
      );

      const wrongAspect: PreviewReviewRecord = {
        ...base,
        preview: { width: 960, height: 960, fps: 30, durationFrames: 180, durationSeconds: 6 },
      };
      const aspectVerdict = checkPreviewMotionGate(wrongAspect);
      assertEq(aspectVerdict.accepted, false, "an aspect-changing record is refused");
      assertTrue(
        aspectVerdict.findings.some((f) => f.code === PREVIEW_GATE_ASPECT_MISMATCH),
        "aspect mismatch finding is named"
      );
    },
  },
  {
    name: "remotion: C05 final and previews consume identical props and source inputs",
    run: async () => {
      const outDir = join(SCRATCH, "remotion-landscape");
      const adapter = createRemotionAdapter({ outputDir: outDir });
      const jobDir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const job = loadValidatedJob(jobDir);
      const loaded = loadC05Job(job);
      const expectedPropsHash = hashPropsPayload(loaded.props);
      const expectedSourceHash = hashJobSourceInputs(jobDir, job.manifest);

      const final = await adapter.renderFinal({ ...job, approval: fixtureApproval(job.jobId) });
      const finalPath = final.outputPaths[0];
      const finalProbe = probeVideoFile(finalPath);
      assertEq(finalProbe.width, EXPECT.c05Landscape.canvas.width, "final width");
      assertEq(finalProbe.height, EXPECT.c05Landscape.canvas.height, "final height");
      assertEq(finalProbe.frameCount, EXPECT.c05Landscape.canvas.durationFrames, "final frames");
      assertEq(`${finalProbe.fpsNumerator}/${finalProbe.fpsDenominator}`, "30/1", "final fps");

      const def = await adapter.renderPreview(job);
      const defRecord = assertRecordBasics(def.previewReview, "remotion default preview");
      assertEq(defRecord.scale, 1, "default preview scale");
      assertEq(defRecord.scaleMethod, "none", "default preview scale method");
      assertEq(defRecord.propsHash, expectedPropsHash, "default preview props hash equals the final's props");
      assertEq(defRecord.sourceHash, expectedSourceHash, "default preview source hash");
      assertEq(defRecord.previewHash, sha256File(def.outputPaths[0]), "default preview hash is the artifact's sha256");
      assertEq(defRecord.preview.durationFrames, finalProbe.frameCount, "default preview frame count matches the final");
      assertTrue(
        Math.abs(defRecord.preview.durationSeconds - finalProbe.durationSeconds) < 0.05,
        "default preview duration matches the final"
      );
      const defSidecar = JSON.parse(
        readFileSync(join(outDir, "renders", "remotion", "preview.review.json"), "utf8")
      ) as PreviewReviewRecord;
      assertEq(defSidecar.propsHash, defRecord.propsHash, "preview.review.json sidecar matches the record");
      assertEq(defSidecar.previewHash, defRecord.previewHash, "sidecar preview hash matches");

      const scaled = await adapter.renderPreview(job, { scale: EXPECT.c05Landscape.previewScale });
      const scaledRecord = assertRecordBasics(scaled.previewReview, "remotion scaled preview");
      assertEq(scaled.artifacts[0].path, "renders/remotion/preview-scale-0p5.mp4", "scaled preview artifact name");
      assertEq(scaledRecord.scale, 0.5, "scaled preview record scale");
      assertEq(scaledRecord.scaleMethod, "render_scale", "remotion scales at render time");
      assertEq(scaledRecord.propsHash, expectedPropsHash, "scaled preview consumed the final's exact props");
      assertEq(scaledRecord.sourceHash, expectedSourceHash, "scaled preview source hash");
      const scaledProbe = probeVideoFile(scaled.outputPaths[0]);
      assertEq(scaledProbe.width, EXPECT.c05Landscape.previewDims.width, "scaled preview width");
      assertEq(scaledProbe.height, EXPECT.c05Landscape.previewDims.height, "scaled preview height");
      assertEq(scaledProbe.frameCount, finalProbe.frameCount, "scaled preview frame count matches the final at the same fps");
      assertEq(`${scaledProbe.fpsNumerator}/${scaledProbe.fpsDenominator}`, "30/1", "scaled preview fps is the full final fps");
      assertTrue(
        Math.abs(scaledProbe.durationSeconds - finalProbe.durationSeconds) < 0.05,
        "scaled preview duration matches the final"
      );
      const sidecar = JSON.parse(
        readFileSync(join(outDir, "renders", "remotion", "preview-scale-0p5.review.json"), "utf8")
      ) as PreviewReviewRecord;
      assertEq(sidecar.previewHash, scaledRecord.previewHash, "scaled sidecar matches the record");
      const gate = checkPreviewMotionGate(scaledRecord);
      assertEq(gate.accepted, true, "scaled full-fps preview passes the motion gate");

      remotionLandscape = {
        adapter,
        jobDir,
        finalPath,
        scaledPath: scaled.outputPaths[0],
        scaledRecord,
        layout: loaded.props.design.layout,
      };
      measured.remotion = {
        finalProbe,
        scaledProbe: {
          width: scaledProbe.width,
          height: scaledProbe.height,
          frameCount: scaledProbe.frameCount,
          fps: `${scaledProbe.fpsNumerator}/${scaledProbe.fpsDenominator}`,
          durationSeconds: scaledProbe.durationSeconds,
        },
        propsHash: expectedPropsHash,
        sourceHash: expectedSourceHash,
      };
    },
  },
  {
    name: "remotion: scaled preview landmarks agree with the final after scaling (decoded pixels)",
    run: async () => {
      assertTrue(remotionLandscape !== null, "landscape renders exist from the previous case");
      const state = remotionLandscape as NonNullable<typeof remotionLandscape>;
      const layout = state.layout;
      const accent = ACCENT;
      const finalRgb75 = decodeFrameRgb(state.finalPath, 75, 1920, 1080);
      const finalW75 = measureAccentBarWidths(finalRgb75, 1920, layout, accent);
      assertWidthsClose(finalW75, LANDSCAPE_F75, EXPECT.tolerances.decodedPx, "final frame 75 landmarks");
      const finalRgb45 = decodeFrameRgb(state.finalPath, 45, 1920, 1080);
      const finalW45 = measureAccentBarWidths(finalRgb45, 1920, layout, accent);
      assertWidthsClose(finalW45, EXPECT.c05Landscape.frame45, EXPECT.tolerances.decodedPx, "final frame 45 landmarks");

      const sLayout = scaledLayout(layout, 0.5);
      const scaledRgb75 = decodeFrameRgb(state.scaledPath, 75, 960, 540);
      const scaledW75 = measureAccentBarWidths(scaledRgb75, 960, sLayout, accent);
      const scaledBack75 = scaledW75.map((w) => w * 2);
      assertWidthsClose(scaledBack75, LANDSCAPE_F75, EXPECT.tolerances.scaledBackPx, "scaled preview frame 75 landmarks scaled back to canonical");
      assertWidthsClose(scaledBack75, finalW75, EXPECT.tolerances.scaledBackPx, "scaled preview frame 75 agrees with the final's own landmarks");
      const scaledRgb45 = decodeFrameRgb(state.scaledPath, 45, 960, 540);
      const scaledW45 = measureAccentBarWidths(scaledRgb45, 960, sLayout, accent);
      assertWidthsClose(scaledW45.map((w) => w * 2), EXPECT.c05Landscape.frame45, EXPECT.tolerances.scaledBackPx, "scaled preview frame 45 landmarks scaled back");

      measured.landmarks = {
        finalFrame75: finalW75,
        scaledFrame75: scaledW75,
        scaledBackFrame75: scaledBack75,
        finalFrame45: finalW45,
        scaledFrame45: scaledW45,
        maxDeltaScaledBackVsExpected: Math.max(
          ...scaledBack75.map((w, i) => Math.abs(w - LANDSCAPE_F75[i]))
        ),
      };
    },
  },
  {
    name: "remotion: a 9:16 job's preview is 9:16 at full fps (vsl_mobile)",
    run: async () => {
      const outDir = join(SCRATCH, "remotion-portrait");
      const adapter = createRemotionAdapter({ outputDir: outDir });
      const jobDir = join(fixturesRoot(), "modes", "vsl_mobile");
      const job = loadValidatedJob(jobDir);
      const scaled = await adapter.renderPreview(job, { scale: 0.5 });
      const record = assertRecordBasics(scaled.previewReview, "remotion portrait preview");
      assertEq(record.final.width, EXPECT.c05Portrait.canvas.width, "portrait final width in record");
      assertEq(record.final.height, EXPECT.c05Portrait.canvas.height, "portrait final height in record");
      const probe = probeVideoFile(scaled.outputPaths[0]);
      assertEq(probe.width, EXPECT.c05Portrait.previewDims.width, "portrait preview width");
      assertEq(probe.height, EXPECT.c05Portrait.previewDims.height, "portrait preview height");
      assertTrue(probe.height > probe.width, "portrait preview is vertical, never a horizontal viewport");
      assertEq(probe.width * 16, probe.height * 9, "portrait preview aspect is exactly 9:16");
      assertEq(probe.frameCount, EXPECT.c05Portrait.canvas.durationFrames, "portrait preview frames");
      assertEq(`${probe.fpsNumerator}/${probe.fpsDenominator}`, "30/1", "portrait preview fps");
      assertEq(checkPreviewMotionGate(record).accepted, true, "portrait preview passes the motion gate");
      measured.remotionPortrait = { width: probe.width, height: probe.height, frameCount: probe.frameCount };
    },
  },
  {
    name: "remotion: rough preview is 15 fps, labeled rough_layout_only, and refused by the gate",
    run: async () => {
      const outDir = join(SCRATCH, "remotion-landscape");
      const adapter = createRemotionAdapter({ outputDir: outDir });
      const jobDir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const job = loadValidatedJob(jobDir);
      const rough = await adapter.renderPreview(job, { roughLayout: true });
      const record = assertRecordBasics(rough.previewReview, "remotion rough preview");
      assertEq(rough.artifacts[0].path, "renders/remotion/preview-rough.mp4", "rough artifact name");
      assertEq(record.label, "rough_layout_only", "rough record label");
      assertEq(record.roughLayoutOnly, true, "rough record flag");
      assertEq(record.preview.fps, EXPECT.rough.fps, "rough record fps");
      assertEq(record.preview.durationFrames, EXPECT.rough.durationFrames, "rough record frames");
      const probe = probeVideoFile(rough.outputPaths[0]);
      assertEq(probe.width, 1920, "rough preview keeps canonical dimensions by default");
      assertEq(probe.frameCount, EXPECT.rough.durationFrames, "rough decoded frames");
      assertEq(`${probe.fpsNumerator}/${probe.fpsDenominator}`, "15/1", "rough decoded fps");
      assertTrue(Math.abs(probe.durationSeconds - 6.0) < 0.1, "rough preview preserves the 6.0 second timeline");
      // The record's props hash is the payload the rough render
      // actually consumed (the same job loaded at the rough fps).
      const roughLoaded = loadC05Job(job, { fpsOverride: EXPECT.rough.fps });
      assertEq(record.propsHash, hashPropsPayload(roughLoaded.props), "rough props hash names the consumed payload");
      assertTrue(
        record.propsHash !== (measured.remotion as { propsHash: string }).propsHash,
        "rough props differ from the full-fps props (fps and duration fields only)"
      );
      assertEq(record.sourceHash, (measured.remotion as { sourceHash: string }).sourceHash, "rough source hash is the same job revision");
      const sidecarExists = existsSync(join(outDir, "renders", "remotion", "preview-rough.review.json"));
      assertTrue(sidecarExists, "rough sidecar exists");
      const verdict = checkPreviewMotionGate(record);
      assertEq(verdict.accepted, false, "the gate refuses the rough preview as motion evidence");
      const codes = verdict.findings.map((f) => f.code).sort();
      assertEq(
        JSON.stringify(codes),
        JSON.stringify([...EXPECT.gate.roughFindings].sort()),
        "gate refusal findings for the real rough render"
      );
      measured.remotionRough = {
        fps: `${probe.fpsNumerator}/${probe.fpsDenominator}`,
        frameCount: probe.frameCount,
        durationSeconds: probe.durationSeconds,
        gateFindings: codes,
      };
    },
  },
  {
    name: "dispatcher: preview options flow through DispatchCallOptions to the adapter",
    run: async () => {
      const outDir = join(SCRATCH, "remotion-dispatch");
      const adapter = createRemotionAdapter({ outputDir: outDir });
      const dispatcher = new MotionDispatcher(createRegistry([adapter]));
      const jobDir = join(fixturesRoot(), "modes", "powerpoint_graphic");
      const outcome = await dispatcher.renderPreview(jobDir, {
        timeoutMs: 900_000,
        preview: { scale: 0.5 },
      });
      const record = assertRecordBasics(outcome.evidence.previewReview, "dispatched scaled preview");
      assertEq(record.scale, 0.5, "dispatcher forwarded the scale");
      const plain = await dispatcher.renderPreview(jobDir, { timeoutMs: 900_000 });
      const plainRecord = assertRecordBasics(plain.evidence.previewReview, "dispatched default preview");
      assertEq(plainRecord.scale, 1, "dispatcher default stays the canonical preview");
    },
  },
];

// ---------------------------------------------------------------------------
// Hyperframes cases
// ---------------------------------------------------------------------------

function stageHyperframesC05(): { jobDir: string; manifest: Manifest } {
  const src = join(fixturesRoot(), "modes", "powerpoint_graphic");
  const jobDir = join(HF_WORK, "c05-job");
  rmSync(jobDir, { recursive: true, force: true });
  cpSync(src, jobDir, { recursive: true });
  const scenePath = join(jobDir, "scenes", "bar-01.json");
  const scene = JSON.parse(readFileSync(scenePath, "utf8")) as Record<string, unknown>;
  scene.engine = "hyperframes";
  writeFileSync(scenePath, JSON.stringify(scene, null, 2) + "\n", "utf8");
  const manifestPath = join(jobDir, "manifest.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Manifest;
  (manifest.rendering as { default_engine: string }).default_engine = "hyperframes";
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  return { jobDir, manifest };
}

function hyperframesDesign(jobDir: string): {
  layout: { plot: { x: number; width: number }; row_y: number[]; bar_height: number };
  accent: string;
} {
  const scene = JSON.parse(readFileSync(join(jobDir, "scenes", "bar-01.json"), "utf8")) as {
    design_path: string;
    layout_variant: string;
  };
  const design = JSON.parse(readFileSync(join(jobDir, scene.design_path), "utf8")) as {
    layouts: Record<string, { plot: { x: number; width: number }; row_y: number[]; bar_height: number }>;
    colors: { accent: string };
  };
  return { layout: design.layouts[scene.layout_variant], accent: design.colors.accent };
}

async function hfBarWidths(
  videoPath: string,
  frame: number,
  layout: { plot: { x: number; width: number }; row_y: number[]; bar_height: number },
  accent: string,
  outPng: string
): Promise<number[]> {
  extractFramePng(videoPath, frame, outPng);
  const img = await decodePng(outPng);
  return layout.row_y.map((y) =>
    measureBarWidth(img, layout.plot.x, y + Math.floor(layout.bar_height / 2), layout.plot.width, accent)
  );
}

CASES.push(
  {
    name: "hyperframes: scaled preview matches the final's landmarks after scaling (decoded pixels)",
    run: async () => {
      const { jobDir, manifest } = stageHyperframesC05();
      const adapter = new HyperframesAdapter();
      const job = { jobDir, jobId: manifest.job_id, manifest };
      const { layout, accent } = hyperframesDesign(jobDir);
      const sourceHash = hashJobSourceInputs(jobDir, manifest);

      const fin = await adapter.renderFinal({ ...job, approval: fixtureApproval(job.jobId) });
      const finalPath = join(jobDir, fin.outputPaths[0]);
      const finalProbe = probeVideoFile(finalPath);
      assertEq(finalProbe.width, 1920, "HF final width");
      assertEq(finalProbe.height, 1080, "HF final height");
      assertEq(finalProbe.frameCount, 180, "HF final frames");
      const finalW75 = await hfBarWidths(
        finalPath, 75, layout, accent, join(HF_WORK, "final-f75.png")
      );
      assertWidthsClose(finalW75, LANDSCAPE_F75, EXPECT.tolerances.decodedPx, "HF final frame 75 landmarks");

      const def = await adapter.renderPreview(job);
      const defRecord = assertRecordBasics(def.previewReview, "HF default preview");
      assertEq(defRecord.scale, 1, "HF default preview scale");
      assertEq(defRecord.sourceHash, sourceHash, "HF default preview source hash");
      assertEq(defRecord.previewHash, sha256File(join(jobDir, def.outputPaths[0])), "HF default preview hash is the artifact sha256");
      const defProbe = probeVideoFile(join(jobDir, def.outputPaths[0]));
      assertEq(defProbe.frameCount, finalProbe.frameCount, "HF default preview frames match the final");

      const scaled = await adapter.renderPreview(job, { scale: 0.5 });
      const scaledPath = join(jobDir, scaled.outputPaths[0]);
      const record = assertRecordBasics(scaled.previewReview, "HF scaled preview");
      assertEq(scaled.outputPaths[0], "renders/hyperframes/preview-scale-0p5.mp4", "HF scaled artifact path");
      assertEq(record.scaleMethod, "post_encode_scale", "HF scale is honestly named a post-encode derivation");
      assertEq(record.propsHash, defRecord.propsHash, "HF scaled and default previews consumed the identical generated project");
      assertEq(record.sourceHash, sourceHash, "HF scaled preview source hash");
      assertEq(record.previewHash, sha256File(scaledPath), "HF scaled preview hash is the artifact sha256");
      const probe = probeVideoFile(scaledPath);
      assertEq(probe.width, EXPECT.c05Landscape.previewDims.width, "HF scaled preview width");
      assertEq(probe.height, EXPECT.c05Landscape.previewDims.height, "HF scaled preview height");
      assertEq(probe.frameCount, 180, "HF scaled preview frames");
      assertEq(`${probe.fpsNumerator}/${probe.fpsDenominator}`, "30/1", "HF scaled preview fps is the full final fps");
      assertEq(checkPreviewMotionGate(record).accepted, true, "HF scaled preview passes the motion gate");

      const receipt = JSON.parse(
        readFileSync(join(jobDir, "renders", "hyperframes", "render-receipt-preview-scale-0p5.json"), "utf8")
      ) as { previewReview?: PreviewReviewRecord };
      assertTrue(receipt.previewReview !== undefined, "HF receipt embeds the preview review record");
      assertEq(receipt.previewReview?.previewHash, record.previewHash, "HF receipt record matches the evidence record");

      const sLayout = {
        plot: { x: Math.round(layout.plot.x / 2), width: Math.round(layout.plot.width / 2) },
        row_y: layout.row_y.map((y) => Math.round(y / 2)),
        bar_height: Math.round(layout.bar_height / 2),
      };
      const scaledW75 = await hfBarWidths(
        scaledPath, 75, sLayout, accent, join(HF_WORK, "scaled-f75.png")
      );
      assertWidthsClose(
        scaledW75.map((w) => w * 2),
        LANDSCAPE_F75,
        EXPECT.tolerances.scaledBackPx,
        "HF scaled preview frame 75 landmarks scaled back to canonical"
      );
      assertWidthsClose(
        scaledW75.map((w) => w * 2),
        finalW75,
        EXPECT.tolerances.scaledBackPx,
        "HF scaled preview frame 75 agrees with the HF final's own landmarks"
      );
      hfJob = { jobDir, finalPath, scaledPath };
      measured.hyperframes = {
        finalFrame75: finalW75,
        scaledFrame75: scaledW75,
        scaledBackFrame75: scaledW75.map((w) => w * 2),
        propsHash: record.propsHash,
        sourceHash,
      };
    },
  },
  {
    name: "hyperframes: rough preview is 15 fps, labeled, gate-refused, and preserves seconds timing",
    run: async () => {
      assertTrue(hfJob !== null, "HF job staged by the previous case");
      const { jobDir } = hfJob as NonNullable<typeof hfJob>;
      const manifest = JSON.parse(readFileSync(join(jobDir, "manifest.json"), "utf8")) as Manifest;
      const adapter = new HyperframesAdapter();
      const job = { jobDir, jobId: manifest.job_id, manifest };
      const { layout, accent } = hyperframesDesign(jobDir);
      const rough = await adapter.renderPreview(job, { roughLayout: true });
      const record = assertRecordBasics(rough.previewReview, "HF rough preview");
      assertEq(rough.outputPaths[0], "renders/hyperframes/preview-rough.mp4", "HF rough artifact path");
      assertEq(record.label, "rough_layout_only", "HF rough label");
      assertEq(record.preview.fps, EXPECT.rough.fps, "HF rough fps");
      assertEq(record.preview.durationFrames, EXPECT.rough.durationFrames, "HF rough frames in record");
      assertEq(
        record.propsHash,
        (measured.hyperframes as { propsHash: string }).propsHash,
        "HF rough preview consumed the identical generated project as the full-fps previews"
      );
      const roughPath = join(jobDir, rough.outputPaths[0]);
      const probe = probeVideoFile(roughPath);
      assertEq(probe.frameCount, EXPECT.rough.durationFrames, "HF rough decoded frames");
      assertEq(`${probe.fpsNumerator}/${probe.fpsDenominator}`, "15/1", "HF rough decoded fps");
      assertTrue(Math.abs(probe.durationSeconds - 6.0) < 0.1, "HF rough preserves the 6.0 second timeline");
      const verdict = checkPreviewMotionGate(record);
      assertEq(verdict.accepted, false, "gate refuses the HF rough preview");
      assertTrue(
        verdict.findings.some((f) => f.code === PREVIEW_GATE_ROUGH_LAYOUT),
        "gate names the rough-layout finding for HF"
      );
      // Seconds timing: frame 30 at 15 fps is t = 2.0 s, where the
      // reveal (0.5 s to 2.5 s) is at 75 percent: [360, 540, 900].
      const wAt2s = await hfBarWidths(roughPath, 30, layout, accent, join(HF_WORK, "rough-f30.png"));
      assertWidthsClose(wAt2s, [360, 540, 900], EXPECT.tolerances.roughTimingPx, "HF rough frame at t=2.0s matches the full-fps timeline position");
      measured.hyperframesRough = { frameAt2s: wAt2s, probe: { frameCount: probe.frameCount } };
    },
  },
  {
    name: "frames: destination-size individual frames and a contact sheet are produced",
    run: async () => {
      assertTrue(remotionLandscape !== null && hfJob !== null, "engine renders exist");
      const rem = remotionLandscape as NonNullable<typeof remotionLandscape>;
      const hf = hfJob as NonNullable<typeof hfJob>;
      const framesDir = join(SCRATCH, "frames");
      mkdirSync(framesDir, { recursive: true });

      // A destination-size frame from the final itself (1920x1080).
      const finalF150 = join(framesDir, "remotion-final-f150.png");
      extractFramePng(rem.finalPath, 150, finalF150);
      const d1 = readPngDimensions(finalF150);
      assertEq(d1?.width, 1920, "destination frame width (final size)");
      assertEq(d1?.height, 1080, "destination frame height (final size)");

      // A destination-size frame from the scaled preview (960x540:
      // the size a reviewer actually watches).
      const scaledF75 = join(framesDir, "remotion-scaled-f75.png");
      extractFramePng(rem.scaledPath, 75, scaledF75);
      const d2 = readPngDimensions(scaledF75);
      assertEq(d2?.width, 960, "preview frame width (preview destination size)");
      assertEq(d2?.height, 540, "preview frame height");

      const hfF75 = join(HF_WORK, "scaled-f75.png");
      assertTrue(existsSync(hfF75), "HF scaled frame 75 was extracted by the HF case");

      const sheet = join(framesDir, "contact-sheet.png");
      const dims = buildContactSheet([finalF150, scaledF75, hfF75], sheet, {
        columns: 3,
        tileWidth: 480,
        tileHeight: 270,
      });
      assertEq(dims.width, 1440, "contact sheet width");
      assertEq(dims.height, 270, "contact sheet height");
      const sheetDims = readPngDimensions(sheet);
      assertEq(sheetDims?.width, 1440, "contact sheet PNG width");
      assertEq(sheetDims?.height, 270, "contact sheet PNG height");
      measured.contactSheet = { path: sheet, width: sheetDims?.width, height: sheetDims?.height };

      // Curate the evidence frames.
      cpSync(finalF150, join(EVIDENCE_DIR, "remotion-final-f150.png"));
      cpSync(scaledF75, join(EVIDENCE_DIR, "remotion-scaled-f75.png"));
      cpSync(hfF75, join(EVIDENCE_DIR, "hyperframes-scaled-f75.png"));
      cpSync(sheet, join(EVIDENCE_DIR, "contact-sheet.png"));
    },
  }
);

// ---------------------------------------------------------------------------
// Legacy render.js cases
// ---------------------------------------------------------------------------

function legacyDepsNodePath(): string {
  if (process.env.MG024_NODE_PATH) return process.env.MG024_NODE_PATH;
  const depsDir = join(REPO_ROOT, ".scratch", "mg024-deps");
  const marker = join(depsDir, "node_modules", "playwright-core", "package.json");
  if (!existsSync(marker)) {
    mkdirSync(depsDir, { recursive: true });
    const install = spawnSync(
      "npm",
      ["install", "--prefix", depsDir, "--no-save", "playwright-core@1.64.1"],
      { encoding: "utf8", timeout: 300_000 }
    );
    if (install.status !== 0 || !existsSync(marker)) {
      throw new Error(
        `playwright-core scratch install failed (status ${String(install.status)}): ` +
          `${(install.stderr ?? "").slice(-400)}`
      );
    }
  }
  return join(depsDir, "node_modules");
}

interface LegacyRun {
  status: number | null;
  stdoutJson: Record<string, unknown> | null;
  stderrTail: string;
}

function runLegacy(args: string[], nodePath: string): LegacyRun {
  const r = spawnSync("node", [join(SKILL_DIR, "scripts", "render.js"), ...args], {
    encoding: "utf8",
    timeout: 600_000,
    env: { ...process.env, NODE_PATH: nodePath },
    maxBuffer: 32 * 1024 * 1024,
  });
  let stdoutJson: Record<string, unknown> | null = null;
  const line = (r.stdout ?? "").trim().split("\n").pop() ?? "";
  try {
    stdoutJson = JSON.parse(line) as Record<string, unknown>;
  } catch {
    stdoutJson = null;
  }
  return { status: r.status, stdoutJson, stderrTail: (r.stderr ?? "").slice(-600) };
}

async function legacyBarRun(pngPath: string, y: number): Promise<{ start: number; width: number }> {
  const img = await decodePng(pngPath);
  let start = -1;
  for (let x = 0; x < img.width; x += 1) {
    if (pixelMatches(img, x, y, ACCENT)) {
      start = x;
      break;
    }
  }
  assertTrue(start >= 0, `legacy frame has an accent bar on row ${y}`);
  const width = measureBarWidth(img, start, y, img.width - start, ACCENT);
  return { start, width };
}

CASES.push(
  {
    name: "legacy: portrait preview is a true 540x960 render at the full 30 fps (was 960x540-forced at 15 fps)",
    run: async () => {
      const nodePath = legacyDepsNodePath();
      const outDir = join(LEGACY_SCRATCH, "portrait-preview");
      const run = runLegacy(
        [
          "--manifest", join(fixturesRoot(), "preview", "legacy", "portrait", "manifest.json"),
          "--scene", "legacy-portrait",
          "--outdir", outDir,
          "--preview",
        ],
        nodePath
      );
      assertEq(run.status, 0, `legacy portrait preview exits cleanly (stderr tail: ${run.stderrTail})`);
      const info = (run.stdoutJson as { preview?: Record<string, unknown> } | null)?.preview;
      assertTrue(info !== undefined, "stdout JSON carries the preview record");
      assertEq(info?.kind, "preview", "legacy preview kind");
      assertEq(info?.scale, 0.5, "legacy preview scale");
      assertEq(info?.fps, EXPECT.legacy.portrait.fps, "legacy preview fps is the full manifest fps");
      const segment = join(outDir, "legacy-portrait.mp4");
      const probe = probeVideoFile(segment);
      assertEq(probe.width, EXPECT.legacy.portrait.previewDims.width, "legacy portrait preview width");
      assertEq(probe.height, EXPECT.legacy.portrait.previewDims.height, "legacy portrait preview height");
      assertTrue(probe.height > probe.width, "legacy portrait preview is vertical");
      assertEq(probe.frameCount, EXPECT.legacy.portrait.frames, "legacy portrait preview frames (3 s at 30 fps)");
      assertEq(`${probe.fpsNumerator}/${probe.fpsDenominator}`, "30/1", "legacy portrait preview fps");
      const sidecar = JSON.parse(
        readFileSync(join(outDir, "legacy-portrait.preview.json"), "utf8")
      ) as { kind: string; width: number; height: number; sourceWidth: number; sourceHeight: number };
      assertEq(sidecar.kind, "preview", "legacy sidecar kind");
      assertEq(sidecar.width, 540, "legacy sidecar preview width");
      assertEq(sidecar.sourceWidth, 1080, "legacy sidecar source width");
      // Decoded landmark: frame 45 is t = 1.5 s, reveal progress 0.5,
      // authored bar 432 px wide at x = 108; at scale 0.5 the capture
      // must measure x = 54, width = 216.
      const framePng = join(LEGACY_SCRATCH, "portrait-f45.png");
      extractFramePng(segment, 45, framePng);
      const bar = await legacyBarRun(framePng, 480);
      assertTrue(
        Math.abs(bar.start - EXPECT.legacy.portrait.barAtFrame45.x) <= EXPECT.tolerances.decodedPx,
        `legacy portrait bar starts at x=${bar.start}, expected ${EXPECT.legacy.portrait.barAtFrame45.x}`
      );
      assertTrue(
        Math.abs(bar.width - EXPECT.legacy.portrait.barAtFrame45.width) <= EXPECT.tolerances.decodedPx,
        `legacy portrait bar width ${bar.width}, expected ${EXPECT.legacy.portrait.barAtFrame45.width}`
      );
      cpSync(framePng, join(EVIDENCE_DIR, "legacy-portrait-preview-f45.png"));
      measured.legacyPortrait = { probe: { width: probe.width, height: probe.height, frameCount: probe.frameCount }, bar };
    },
  },
  {
    name: "legacy: rough preview is the only reduced-fps mode and is labeled rough_layout_only",
    run: () => {
      const nodePath = legacyDepsNodePath();
      const outDir = join(LEGACY_SCRATCH, "portrait-rough");
      const run = runLegacy(
        [
          "--manifest", join(fixturesRoot(), "preview", "legacy", "portrait", "manifest.json"),
          "--scene", "legacy-portrait",
          "--outdir", outDir,
          "--preview", "--rough",
        ],
        nodePath
      );
      assertEq(run.status, 0, `legacy rough preview exits cleanly (stderr tail: ${run.stderrTail})`);
      const info = (run.stdoutJson as { preview?: Record<string, unknown> } | null)?.preview;
      assertEq(info?.kind, "rough_layout_only", "legacy rough kind label");
      assertEq(info?.fps, EXPECT.legacy.rough.fps, "legacy rough fps");
      const probe = probeVideoFile(join(outDir, "legacy-portrait.mp4"));
      assertEq(probe.frameCount, EXPECT.legacy.rough.frames, "legacy rough frames (3 s at 15 fps)");
      assertEq(`${probe.fpsNumerator}/${probe.fpsDenominator}`, "15/1", "legacy rough decoded fps");
      assertEq(probe.width, 540, "legacy rough keeps the scaled size");
      const sidecar = JSON.parse(
        readFileSync(join(outDir, "legacy-portrait.preview.json"), "utf8")
      ) as { kind: string };
      assertEq(sidecar.kind, "rough_layout_only", "legacy rough sidecar label");
      measured.legacyRough = { frameCount: probe.frameCount };
    },
  },
  {
    name: "legacy: landscape preview derives 960x540 from the manifest at full fps, not from a hardcode",
    run: () => {
      const nodePath = legacyDepsNodePath();
      const outDir = join(LEGACY_SCRATCH, "landscape-preview");
      const run = runLegacy(
        [
          "--manifest", join(fixturesRoot(), "preview", "legacy", "landscape", "manifest.json"),
          "--scene", "legacy-landscape",
          "--outdir", outDir,
          "--preview",
        ],
        nodePath
      );
      assertEq(run.status, 0, `legacy landscape preview exits cleanly (stderr tail: ${run.stderrTail})`);
      const probe = probeVideoFile(join(outDir, "legacy-landscape.mp4"));
      assertEq(probe.width, EXPECT.legacy.landscape.previewDims.width, "legacy landscape preview width");
      assertEq(probe.height, EXPECT.legacy.landscape.previewDims.height, "legacy landscape preview height");
      assertEq(probe.frameCount, EXPECT.legacy.landscape.frames, "legacy landscape preview frames (was 45 at the forced 15 fps)");
      assertEq(`${probe.fpsNumerator}/${probe.fpsDenominator}`, "30/1", "legacy landscape preview fps");
      measured.legacyLandscape = { width: probe.width, height: probe.height, frameCount: probe.frameCount };
    },
  }
);

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<number> {
  assertEq(EXPECT.item, "MG-024", "expectation record is the MG-024 record");
  rmSync(SCRATCH, { recursive: true, force: true });
  mkdirSync(SCRATCH, { recursive: true });
  mkdirSync(HF_WORK, { recursive: true });
  mkdirSync(EVIDENCE_DIR, { recursive: true });
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
  console.log(`MEASURED ${JSON.stringify(measured, null, 1)}`);
  console.log(`Preview: ${passed}/${CASES.length} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
