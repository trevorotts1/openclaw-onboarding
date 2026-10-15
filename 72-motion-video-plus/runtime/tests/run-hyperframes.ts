// Adapter tests for the MG-005 Hyperframes production adapter.
//
// These are real end-to-end tests against the pinned CLI in the shared
// runtime: no fakes. They cover, per the MG-005 acceptance list:
// - probeRuntime against the real runtime lock, and against a missing
//   runtime (unavailable, never a fabricated ready);
// - the Section 16 C05 fixture run through Hyperframes on its native
//   clock (Directive 17.2), through the dispatcher: validation, stills,
//   the 17.2 proof states measured from decoded frames, preview, and a
//   fixture-authorized final render with the exact frame count (M01);
// - the Section 15.3 vertical slice: a C01 image-led mask reveal with
//   the subject's revealed fraction measured at initial, proof, and
//   final states from decoded frames (M10), plus its full-fps clip;
// - a nested composition (data-composition-src) whose sub-composition
//   animates while the root subject stays constant;
// - a media-timed scene whose framework-owned clip timing is proven
//   from decoded frames against the declared media segments;
// - failure cases: missing asset and unknown component fail clearly
//   with structured categories and no success evidence;
// - cancellation: an in-flight render cancelled through the adapter
//   rejects with MG_CANCELLED (exit class 8).
//
// C01 and C02 scene specs use the MG-005 spec shape (schema_version
// "mg005-1") because the contracts catalog registration is MG-018
// scope; those jobs are therefore built as ValidatedMotionJob objects
// directly, exactly as the dispatcher would hand them to the adapter
// after its contracts gate. The C05 job goes through the full
// dispatcher path including contracts validation.
//
// Evidence: curated frames are written to tests/evidence/mg005/.
// Rendered videos stay in the git-ignored work directory;
// measurements.json there is a committed STATIC record (MG-043): this
// runner writes its derived measurements to the work directory and
// compares them against the record, failing on drift instead of
// rewriting it. See runtime/tests/evidence-record.ts.
//
// Exit code 0 when every case passes, 1 otherwise.

import { execFile } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import {
  AdapterError,
  createRegistry,
  MotionDispatcher,
} from "../src/adapters";
import { HyperframesAdapter } from "../src/adapters/hyperframes";
import type {
  ApprovedMotionJob,
  ValidatedMotionJob,
} from "../src/adapters/types";
import type { Approval, Manifest } from "../src/validation/generated-types";
import {
  decodePng,
  dominantColor,
  measureBarWidth,
  measureColorFraction,
} from "../src/hyperframes/measure";
import { resolveFont } from "../src/hyperframes/project";
import { checkStaticEvidenceRecord } from "./evidence-record";

const execFileP = promisify(execFile);

// The box's /tmp is a small shared tmpfs; keep every child's temp usage
// on the home filesystem (Chrome profiles and bundler temp land here).
const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const TMP_SCRATCH = join(REPO_ROOT, ".scratch", "tmp");
mkdirSync(TMP_SCRATCH, { recursive: true });
process.env.TMPDIR = TMP_SCRATCH;

const FIXTURES_ROOT = process.env.MOTION_FIXTURES_ROOT
  ? resolve(process.env.MOTION_FIXTURES_ROOT)
  : join(SKILL_DIR, "tests", "fixtures");
const EVIDENCE_DIR = join(SKILL_DIR, "tests", "evidence", "mg005");
const WORK_DIR = join(EVIDENCE_DIR, "work");
const RUNTIME_ROOT = join(REPO_ROOT, "shared-utils", "motion-render-runtime");

const PALETTE = { background: "#F7F4EE", ink: "#192A38", accent: "#C04A26" };

function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}

function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

async function expectAdapterError(
  promise: Promise<unknown>,
  category: string,
  messagePart: string
): Promise<AdapterError> {
  try {
    await promise;
  } catch (err) {
    assertTrue(err instanceof AdapterError, `expected AdapterError, got ${String(err)}`);
    const e = err as AdapterError;
    assertEq(e.category, category, "error category");
    assertTrue(
      e.message.includes(messagePart),
      `error message should name "${messagePart}", got: ${e.message}`
    );
    return e;
  }
  throw new Error(`expected AdapterError ${category}, but the operation succeeded`);
}

async function ffprobeFrames(path: string): Promise<{ frames: number; width: number; height: number }> {
  const { stdout } = await execFileP("ffprobe", [
    "-v", "error", "-count_frames", "-select_streams", "v:0",
    "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", path,
  ]);
  const parsed = JSON.parse(stdout) as { streams: Array<{ width: number; height: number; nb_read_frames: string }> };
  const s = parsed.streams[0];
  return { frames: parseInt(s.nb_read_frames, 10), width: s.width, height: s.height };
}

function sha256File(path: string): string {
  const { createHash } = require("node:crypto") as typeof import("node:crypto");
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

// ---------------------------------------------------------------------
// Fixture assets (all generated locally; no network, no paid generation)
// ---------------------------------------------------------------------

const SUBJECT_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="690" viewBox="0 0 1200 690">
  <ellipse cx="500" cy="592" rx="380" ry="34" fill="#192A38" opacity="0.18"/>
  <rect x="180" y="200" width="640" height="360" rx="28" fill="#C04A26"/>
  <rect x="180" y="200" width="640" height="76" rx="28" fill="#192A38"/>
  <rect x="300" y="330" width="280" height="130" rx="14" fill="#F7F4EE"/>
  <rect x="330" y="362" width="220" height="22" rx="11" fill="#192A38"/>
  <rect x="330" y="402" width="160" height="22" rx="11" fill="#192A38" opacity="0.55"/>
  <rect x="648" y="316" width="26" height="244" fill="#192A38" opacity="0.25"/>
  <rect x="742" y="316" width="26" height="244" fill="#192A38" opacity="0.25"/>
  <circle cx="950" cy="390" r="112" fill="#192A38"/>
  <polygon points="908,438 950,348 992,438 964,438 964,470 936,470 936,438" fill="#F7F4EE"/>
</svg>
`;

/** Rasterize the authored SVG to a PNG with the shared runtime's own
 * headless Chrome (the same browser the engines render with). The
 * screenshot runs under a virtual-time budget with its own profile dir
 * and a hard timeout: old-style headless screenshot can otherwise hang
 * indefinitely in this sandbox. If rasterization fails, the authored
 * SVG itself is the asset (Hyperframes renders SVG natively); the
 * returned kind records which path produced the asset. */
async function rasterizeSubject(
  workDir: string
): Promise<{ path: string; kind: "png" | "svg"; detail: string }> {
  const svgPath = join(workDir, "subject.svg");
  writeFileSync(svgPath, SUBJECT_SVG, "utf8");
  const htmlPath = join(workDir, "subject-raster.html");
  writeFileSync(
    htmlPath,
    `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;background:transparent}</style></head><body>${SUBJECT_SVG}</body></html>`,
    "utf8"
  );
  const current = realpathSync(join(RUNTIME_ROOT, ".runtime", "current"));
  const remotionCache = join(current, "node_modules", ".remotion");
  const findChrome = (dir: string, depth: number): string | null => {
    if (depth > 4) return null;
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
  assertTrue(chrome !== null, "headless Chrome not found in the shared runtime install");
  const pngPath = join(workDir, "subject.png");
  try {
    await execFileP(
      chrome as string,
      [
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--disable-extensions",
        "--disable-dev-shm-usage",
        `--user-data-dir=${join(workDir, "chrome-profile")}`,
        "--virtual-time-budget=10000",
        "--hide-scrollbars",
        "--default-background-color=00000000",
        "--window-size=1200,690",
        `--screenshot=${pngPath}`,
        `file://${htmlPath}`,
      ],
      { timeout: 30000 }
    );
  } catch (err) {
    return {
      path: svgPath,
      kind: "svg",
      detail:
        "PNG rasterization via the headless Chrome --screenshot flag did not complete " +
        `in this sandbox (${(err as Error).message.slice(0, 120)}); the authored SVG is ` +
        "used as the composition asset directly (Hyperframes rasterizes SVG natively at capture)",
    };
  }
  assertTrue(existsSync(pngPath), "Chrome did not produce the subject PNG");
  return { path: pngPath, kind: "png", detail: "SVG rasterized to PNG by the shared runtime headless Chrome" };
}

/** The media timing fixture: three declared color segments, 2 s each. */
const MEDIA_SEGMENTS = [
  { start: 0, end: 2, color: "#2563EB" },
  { start: 2, end: 4, color: "#16A34A" },
  { start: 4, end: 6, color: "#9333EA" },
];

async function generateMediaClip(workDir: string): Promise<string> {
  const out = join(workDir, "timing-clip.mp4");
  const args: string[] = ["-v", "error"];
  for (const seg of MEDIA_SEGMENTS) {
    args.push("-f", "lavfi", "-i", `color=c=0x${seg.color.slice(1)}:s=1280x720:r=30:d=${seg.end - seg.start}`);
  }
  args.push(
    "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
    "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", out
  );
  await execFileP("ffmpeg", args);
  assertTrue(existsSync(out), "ffmpeg did not produce the timing clip");
  return out;
}

// ---------------------------------------------------------------------
// Job builders
// ---------------------------------------------------------------------

function baseManifest(jobId: string, durationFrames: number): Manifest {
  const manifest = {
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
  return manifest as unknown as Manifest;
}

function writeJobShell(jobDir: string, jobId: string, durationFrames: number): Manifest {
  mkdirSync(jobDir, { recursive: true });
  const manifest = baseManifest(jobId, durationFrames);
  writeFileSync(
    join(jobDir, "timeline.json"),
    JSON.stringify(
      {
        schema_version: "2.0",
        job_id: jobId,
        fps: 30,
        total_frames: durationFrames,
        scenes: [],
        events: [],
        parent_slot: null,
        audio_owner: "none",
      },
      null,
      2
    ) + "\n",
    "utf8"
  );
  return manifest;
}

function saveManifest(jobDir: string, manifest: Manifest): void {
  writeFileSync(join(jobDir, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n", "utf8");
}

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg005-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "mg005-fixture",
    artifact_refs: [],
    actor_id: "mg005-adapter-test",
    source_event_ref: null,
    authority_status: "not_verified",
  };
}

/** Copy the Section 16 PowerPoint fixture job and retarget its scene to
 * Hyperframes: the same fixture on the Hyperframes native clock (17.2). */
function buildC05Job(): { jobDir: string; job: ValidatedMotionJob } {
  const src = join(FIXTURES_ROOT, "modes", "powerpoint_graphic");
  const jobDir = join(WORK_DIR, "c05-job");
  rmSync(jobDir, { recursive: true, force: true });
  cpSync(src, jobDir, { recursive: true });
  const scenePath = join(jobDir, "scenes", "bar-01.json");
  const scene = JSON.parse(readFileSync(scenePath, "utf8")) as Record<string, unknown>;
  scene.engine = "hyperframes";
  writeFileSync(scenePath, JSON.stringify(scene, null, 2) + "\n", "utf8");
  const manifestPath = join(jobDir, "manifest.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Manifest;
  (manifest.rendering as { default_engine: string }).default_engine = "hyperframes";
  saveManifest(jobDir, manifest);
  return { jobDir, job: { jobDir, jobId: manifest.job_id, manifest } };
}

const SUBJECT_BOX = { x: 360, y: 190, width: 1200, height: 690 };

function buildRevealJob(subjectAsset: string): { jobDir: string; job: ValidatedMotionJob } {
  const jobDir = join(WORK_DIR, "reveal-job");
  rmSync(jobDir, { recursive: true, force: true });
  const manifest = writeJobShell(jobDir, "mg005-reveal", 150);
  mkdirSync(join(jobDir, "assets"), { recursive: true });
  mkdirSync(join(jobDir, "scenes"), { recursive: true });
  const assetName = subjectAsset.split("/").pop() as string;
  cpSync(subjectAsset, join(jobDir, "assets", assetName));
  const spec = {
    schema_version: "mg005-1",
    id: "reveal-01",
    component_id: "C01",
    component_version: "1.0.0",
    engine: "hyperframes",
    duration_frames: 150,
    asset_file: `assets/${assetName}`,
    asset_sha256: sha256File(join(jobDir, "assets", assetName)),
    font_ref: "font-fixture-sans",
    canvas: { width: 1920, height: 1080 },
    design: { colors: PALETTE },
    subject: { id: "work-crate", box: SUBJECT_BOX, measure_color: PALETTE.accent },
    copy: {
      headline: "Inside every delivery: the work itself",
      caption: "One work crate, uncovered in full. Nothing else in the frame moves.",
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
  writeFileSync(join(jobDir, "scenes", "reveal-01.json"), JSON.stringify(spec, null, 2) + "\n", "utf8");
  manifest.scenes = [{ id: "reveal-01", spec: "scenes/reveal-01.json" }] as Manifest["scenes"];
  saveManifest(jobDir, manifest);
  return { jobDir, job: { jobDir, jobId: "mg005-reveal", manifest } };
}

const DETAIL_BOX = { x: 1220, y: 330, width: 580, height: 300 };
const DETAIL_COLOR = "#1D6FB8";

function buildNestedJob(subjectAsset: string): { jobDir: string; job: ValidatedMotionJob } {
  const jobDir = join(WORK_DIR, "nested-job");
  rmSync(jobDir, { recursive: true, force: true });
  const manifest = writeJobShell(jobDir, "mg005-nested", 120);
  mkdirSync(join(jobDir, "assets"), { recursive: true });
  mkdirSync(join(jobDir, "scenes"), { recursive: true });
  const assetName = subjectAsset.split("/").pop() as string;
  cpSync(subjectAsset, join(jobDir, "assets", assetName));
  const spec = {
    schema_version: "mg005-1",
    id: "nested-01",
    component_id: "C01",
    component_version: "1.0.0",
    variant: "nested_detail",
    engine: "hyperframes",
    duration_frames: 120,
    asset_file: `assets/${assetName}`,
    asset_sha256: sha256File(join(jobDir, "assets", assetName)),
    font_ref: "font-fixture-sans",
    canvas: { width: 1920, height: 1080 },
    design: { colors: PALETTE },
    subject: { id: "work-crate", box: { x: 120, y: 250, width: 1000, height: 620 }, measure_color: PALETTE.accent },
    detail: {
      box: DETAIL_BOX,
      start_frame: 30,
      measure_color: DETAIL_COLOR,
      variables: { label: "crates delivered this week", value: "128" },
    },
    copy: {
      headline: "The work, with its detail attached",
      fixture_label: "ENGINEERING FIXTURE - ILLUSTRATIVE OBJECT",
    },
    headline_px: 84,
  };
  writeFileSync(join(jobDir, "scenes", "nested-01.json"), JSON.stringify(spec, null, 2) + "\n", "utf8");
  manifest.scenes = [{ id: "nested-01", spec: "scenes/nested-01.json" }] as Manifest["scenes"];
  saveManifest(jobDir, manifest);
  return { jobDir, job: { jobDir, jobId: "mg005-nested", manifest } };
}

const CLIP_BOX = { x: 420, y: 170, width: 1150, height: 647 };

function buildMediaJob(clipPath: string): { jobDir: string; job: ValidatedMotionJob } {
  const jobDir = join(WORK_DIR, "media-job");
  rmSync(jobDir, { recursive: true, force: true });
  const manifest = writeJobShell(jobDir, "mg005-media", 150);
  mkdirSync(join(jobDir, "assets"), { recursive: true });
  mkdirSync(join(jobDir, "scenes"), { recursive: true });
  cpSync(clipPath, join(jobDir, "assets", "timing-clip.mp4"));
  const spec = {
    schema_version: "mg005-1",
    id: "media-01",
    component_id: "C02",
    component_version: "1.0.0",
    variant: "media_timing",
    engine: "hyperframes",
    duration_frames: 150,
    media_file: "assets/timing-clip.mp4",
    media_sha256: sha256File(join(jobDir, "assets", "timing-clip.mp4")),
    font_ref: "font-fixture-sans",
    canvas: { width: 1920, height: 1080 },
    design: { colors: PALETTE },
    clip: { start_frame: 30, duration_frames: 120, media_start_seconds: 1, box: CLIP_BOX },
    media_segments: MEDIA_SEGMENTS,
    copy: {
      headline: "The framework owns the clip timing",
      caption: "Blue, then green, then purple: the media clock, trimmed by one second, decides.",
      fixture_label: "ENGINEERING FIXTURE - ABSTRACT TIMING CLIP",
    },
    headline_px: 84,
    caption_px: 40,
  };
  writeFileSync(join(jobDir, "scenes", "media-01.json"), JSON.stringify(spec, null, 2) + "\n", "utf8");
  manifest.scenes = [{ id: "media-01", spec: "scenes/media-01.json" }] as Manifest["scenes"];
  saveManifest(jobDir, manifest);
  return { jobDir, job: { jobDir, jobId: "mg005-media", manifest } };
}

function buildBrokenJobs(subjectAsset: string): {
  missingAsset: { jobDir: string; job: ValidatedMotionJob };
  unknownComponent: { jobDir: string; job: ValidatedMotionJob };
} {
  const missingDir = join(WORK_DIR, "broken-missing-asset");
  rmSync(missingDir, { recursive: true, force: true });
  const m1 = writeJobShell(missingDir, "mg005-broken-missing", 60);
  mkdirSync(join(missingDir, "scenes"), { recursive: true });
  const missingSpec = {
    schema_version: "mg005-1",
    id: "broken-01",
    component_id: "C01",
    component_version: "1.0.0",
    engine: "hyperframes",
    duration_frames: 60,
    asset_file: "assets/does-not-exist.png",
    font_ref: "font-fixture-sans",
    canvas: { width: 1920, height: 1080 },
    design: { colors: PALETTE },
    subject: { id: "ghost", box: SUBJECT_BOX, measure_color: PALETTE.accent },
    copy: { headline: "Missing", caption: "Missing", fixture_label: "FIXTURE" },
    headline_px: 84,
    caption_px: 40,
    motion: { kind: "mask_reveal", start_frame: 10, end_frame_exclusive: 40, hold_to_frame_exclusive: 60 },
    semantic_motion_assertions: [],
  };
  writeFileSync(join(missingDir, "scenes", "broken-01.json"), JSON.stringify(missingSpec, null, 2) + "\n", "utf8");
  m1.scenes = [{ id: "broken-01", spec: "scenes/broken-01.json" }] as Manifest["scenes"];
  saveManifest(missingDir, m1);

  const unknownDir = join(WORK_DIR, "broken-unknown-component");
  rmSync(unknownDir, { recursive: true, force: true });
  const m2 = writeJobShell(unknownDir, "mg005-broken-unknown", 60);
  mkdirSync(join(unknownDir, "assets"), { recursive: true });
  mkdirSync(join(unknownDir, "scenes"), { recursive: true });
  const assetName = subjectAsset.split("/").pop() as string;
  cpSync(subjectAsset, join(unknownDir, "assets", assetName));
  const unknownSpec = {
    schema_version: "mg005-1",
    id: "broken-02",
    component_id: "C99",
    component_version: "1.0.0",
    engine: "hyperframes",
    duration_frames: 60,
    asset_file: `assets/${assetName}`,
    font_ref: "font-fixture-sans",
    canvas: { width: 1920, height: 1080 },
    design: { colors: PALETTE },
    subject: { id: "ghost", box: SUBJECT_BOX, measure_color: PALETTE.accent },
    copy: { headline: "Unknown", caption: "Unknown", fixture_label: "FIXTURE" },
    headline_px: 84,
    caption_px: 40,
    motion: { kind: "mask_reveal", start_frame: 10, end_frame_exclusive: 40, hold_to_frame_exclusive: 60 },
    semantic_motion_assertions: [],
  };
  writeFileSync(join(unknownDir, "scenes", "broken-02.json"), JSON.stringify(unknownSpec, null, 2) + "\n", "utf8");
  m2.scenes = [{ id: "broken-02", spec: "scenes/broken-02.json" }] as Manifest["scenes"];
  saveManifest(unknownDir, m2);

  return {
    missingAsset: { jobDir: missingDir, job: { jobDir: missingDir, jobId: "mg005-broken-missing", manifest: m1 } },
    unknownComponent: { jobDir: unknownDir, job: { jobDir: unknownDir, jobId: "mg005-broken-unknown", manifest: m2 } },
  };
}

// ---------------------------------------------------------------------
// Cases
// ---------------------------------------------------------------------

interface Case {
  name: string;
  run: () => Promise<void>;
}

const measurements: Record<string, unknown> = {
  adapter: "hyperframes",
  directive_item: "MG-005",
  generated_by: "runtime/tests/run-hyperframes.ts",
};

async function main(): Promise<number> {
  rmSync(WORK_DIR, { recursive: true, force: true });
  mkdirSync(WORK_DIR, { recursive: true });
  mkdirSync(EVIDENCE_DIR, { recursive: true });

  const adapter = new HyperframesAdapter();
  const dispatcher = new MotionDispatcher(createRegistry([adapter]));
  const assetDir = join(WORK_DIR, "assets-src");
  mkdirSync(assetDir, { recursive: true });
  const subject = await rasterizeSubject(assetDir);
  const clipPath = await generateMediaClip(assetDir);
  const c05 = buildC05Job();
  const reveal = buildRevealJob(subject.path);
  const nested = buildNestedJob(subject.path);
  const media = buildMediaJob(clipPath);
  const broken = buildBrokenJobs(subject.path);

  const font = resolveFont("font-fixture-sans");
  measurements.font = {
    alias: font.alias,
    cssFamily: font.cssFamily,
    files: font.files.map((f) => ({ weight: f.weight, path: f.sourcePath, sha256: f.sha256 })),
  };
  measurements.subject_asset = {
    svg: "authored in run-hyperframes.ts (SUBJECT_SVG)",
    asset: { path: subject.path, kind: subject.kind, sha256: sha256File(subject.path) },
    rasterizer: subject.detail,
  };

  const cases: Case[] = [
    {
      name: "probe: reports ready from the real runtime lock with measured version",
      run: async () => {
        const ev = await adapter.probeRuntime();
        assertEq(ev.status, "ready", "probe status");
        assertEq(ev.runtime.engineVersion, "0.8.155", "engine version");
        assertEq(ev.runtime.runtimeLockId, "lock-314fc289b233ca9e", "runtime lock id");
        measurements.probe = { status: ev.status, detail: ev.detail, runtime: ev.runtime };
      },
    },
    {
      name: "probe: a missing runtime reports unavailable and names the cause",
      run: async () => {
        const empty = join(WORK_DIR, "no-runtime");
        mkdirSync(empty, { recursive: true });
        const ev = await new HyperframesAdapter({ runtimeRoot: empty }).probeRuntime();
        assertEq(ev.status, "unavailable", "probe status for missing runtime");
        assertEq(ev.runtime.engineVersion, null, "no version is invented");
        assertTrue(ev.detail.includes("no .runtime/runtime-lock.json"), "detail names the missing lock");
      },
    },
    {
      name: "c05: dispatcher validation passes with zero findings (lint and check gates ran)",
      run: async () => {
        const outcome = await dispatcher.validate(c05.jobDir);
        assertTrue(
          outcome.evidence.valid,
          `expected a valid job, findings: ${JSON.stringify(outcome.evidence.findings)}`
        );
        assertEq(outcome.evidence.findings.length, 0, "finding count");
        assertEq(outcome.routing.primaryEngine, "hyperframes", "routed engine");
      },
    },
    {
      name: "c05: proof states at frames 45 and 75 measure the 17.2 widths from decoded frames",
      run: async () => {
        const motion = await dispatcher.inspectMotion(c05.jobDir, { startFrame: 0, endFrameExclusive: 180 });
        assertEq(motion.evidence.assertionsChecked, 2, "assertions checked");
        assertEq(motion.evidence.assertionsPassed, 2, "assertions passed");
        measurements.c05_proof_states = motion.evidence.observations;
      },
    },
    {
      name: "c05: stable hold at frames 150 and 179 keeps the final widths",
      run: async () => {
        const still150 = await dispatcher.renderStill(c05.jobDir, 150);
        const still179 = await dispatcher.renderStill(c05.jobDir, 179);
        const p150 = join(c05.jobDir, still150.evidence.outputPaths[0]);
        const p179 = join(c05.jobDir, still179.evidence.outputPaths[0]);
        const design = JSON.parse(readFileSync(join(c05.jobDir, "design.json"), "utf8")) as {
          layouts: { landscape: { plot: { x: number; width: number }; row_y: number[]; bar_height: number } };
          colors: { accent: string };
        };
        const layout = design.layouts.landscape;
        const widths = async (p: string): Promise<number[]> => {
          const img = await decodePng(p);
          return layout.row_y.map((y) =>
            measureBarWidth(img, layout.plot.x, y + Math.floor(layout.bar_height / 2), layout.plot.width, design.colors.accent)
          );
        };
        const w150 = await widths(p150);
        const w179 = await widths(p179);
        const expected = [480, 720, 1200];
        for (let i = 0; i < 3; i += 1) {
          assertTrue(Math.abs(w150[i] - expected[i]) <= 2, `frame 150 bar ${i}: ${w150[i]} vs ${expected[i]}`);
          assertTrue(Math.abs(w179[i] - expected[i]) <= 2, `frame 179 bar ${i}: ${w179[i]} vs ${expected[i]}`);
        }
        measurements.c05_hold = { frame150: w150, frame179: w179, expected };
        cpSync(p150, join(EVIDENCE_DIR, "c05-frame150.png"));
      },
    },
    {
      name: "c05: preview and fixture-authorized final render hold exactly 180 frames at 1920x1080",
      run: async () => {
        const preview = await dispatcher.renderPreview(c05.jobDir);
        const previewPath = join(c05.jobDir, preview.evidence.outputPaths[0]);
        const pProbe = await ffprobeFrames(previewPath);
        assertEq(pProbe.frames, 180, "preview decoded frames");
        assertEq(pProbe.width, 1920, "preview width");
        const fin = await dispatcher.renderFinal(c05.jobDir, fixtureApproval("fixture-powerpoint-graphic"));
        const finalPath = join(c05.jobDir, fin.evidence.outputPaths[0]);
        const fProbe = await ffprobeFrames(finalPath);
        assertEq(fProbe.frames, 180, "final decoded frames");
        assertEq(fProbe.height, 1080, "final height");
        const receipt = JSON.parse(
          readFileSync(join(c05.jobDir, "renders", "hyperframes", "render-receipt-final.json"), "utf8")
        ) as { engineVersion: string; renderingMode?: string; scenes: Array<{ renderingMode: string }> };
        assertEq(receipt.engineVersion, "0.8.155", "receipt engine version");
        measurements.c05_renders = {
          preview: { path: previewPath, sha256: sha256File(previewPath), frames: pProbe.frames },
          final: { path: finalPath, sha256: sha256File(finalPath), frames: fProbe.frames },
          rendering_mode: receipt.scenes[0]?.renderingMode ?? null,
        };
      },
    },
    {
      name: "c01 reveal: validation passes and revealed fractions measure subject-owned motion",
      run: async () => {
        const validation = await adapter.validate(reveal.job);
        assertTrue(validation.valid, `reveal job should validate: ${JSON.stringify(validation.findings)}`);
        const motion = await adapter.inspectMotion(reveal.job, { startFrame: 0, endFrameExclusive: 150 });
        assertEq(motion.assertionsChecked, 3, "reveal assertions checked");
        assertEq(motion.assertionsPassed, 3, "reveal assertions passed");
        measurements.c01_reveal = { observations: motion.observations };
        for (const frame of [0, 75, 149]) {
          const still = await adapter.renderStill(reveal.job, frame);
          cpSync(
            join(reveal.jobDir, still.outputPaths[0]),
            join(EVIDENCE_DIR, `c01-frame${frame}.png`)
          );
        }
      },
    },
    {
      name: "c01 reveal: final render is the full-fps clip with exactly 150 frames",
      run: async () => {
        const approved: ApprovedMotionJob = { ...reveal.job, approval: fixtureApproval("mg005-reveal") };
        const fin = await adapter.renderFinal(approved);
        const finalPath = join(reveal.jobDir, fin.outputPaths[0]);
        const probe = await ffprobeFrames(finalPath);
        assertEq(probe.frames, 150, "reveal final decoded frames");
        measurements.c01_clip = {
          path: finalPath,
          sha256: sha256File(finalPath),
          frames: probe.frames,
          note: "full-fps clip of the reveal scene (M10 evidence)",
        };
      },
    },
    {
      name: "nested: sub-composition animates in while the root subject stays constant",
      run: async () => {
        const validation = await adapter.validate(nested.job);
        assertTrue(validation.valid, `nested job should validate: ${JSON.stringify(validation.findings)}`);
        const early = await adapter.renderStill(nested.job, 10);
        const late = await adapter.renderStill(nested.job, 110);
        const earlyImg = await decodePng(join(nested.jobDir, early.outputPaths[0]));
        const lateImg = await decodePng(join(nested.jobDir, late.outputPaths[0]));
        const chipEarly = measureColorFraction(earlyImg, DETAIL_BOX, DETAIL_COLOR);
        const chipLate = measureColorFraction(lateImg, DETAIL_BOX, DETAIL_COLOR);
        const subjectBox = { x: 120, y: 250, width: 1000, height: 620 };
        const subjEarly = measureColorFraction(earlyImg, subjectBox, PALETTE.accent);
        const subjLate = measureColorFraction(lateImg, subjectBox, PALETTE.accent);
        assertTrue(chipEarly < 0.05, `detail chip should be absent at frame 10, fraction ${chipEarly}`);
        assertTrue(chipLate > 0.4, `detail chip should be present at frame 110, fraction ${chipLate}`);
        assertTrue(
          Math.abs(subjEarly - subjLate) < 0.02,
          `subject should stay constant: ${subjEarly} vs ${subjLate}`
        );
        measurements.nested = { chipEarly, chipLate, subjEarly, subjLate };
        cpSync(join(nested.jobDir, late.outputPaths[0]), join(EVIDENCE_DIR, "nested-frame110.png"));
      },
    },
    {
      name: "media: framework-owned clip timing matches the declared segments in decoded frames",
      run: async () => {
        const validation = await adapter.validate(media.job);
        assertTrue(validation.valid, `media job should validate: ${JSON.stringify(validation.findings)}`);
        const inset = { x: CLIP_BOX.x + 16, y: CLIP_BOX.y + 16, width: CLIP_BOX.width - 32, height: CLIP_BOX.height - 32 };
        const checks = [
          { frame: 45, expect: "#2563EB", mediaTime: 1.5 },
          { frame: 105, expect: "#16A34A", mediaTime: 3.5 },
          { frame: 140, expect: "#9333EA", mediaTime: 4.67 },
        ];
        const seen: Array<Record<string, unknown>> = [];
        for (const c of checks) {
          const still = await adapter.renderStill(media.job, c.frame);
          const img = await decodePng(join(media.jobDir, still.outputPaths[0]));
          const dom = dominantColor(img, inset, MEDIA_SEGMENTS.map((s) => s.color));
          assertEq(dom.color, c.expect, `frame ${c.frame} (media time ${c.mediaTime}) dominant segment`);
          assertTrue(dom.fraction > 0.8, `frame ${c.frame} segment fraction ${dom.fraction}`);
          seen.push({ frame: c.frame, mediaTime: c.mediaTime, dominant: dom.color, fraction: dom.fraction });
          if (c.frame === 105) {
            cpSync(join(media.jobDir, still.outputPaths[0]), join(EVIDENCE_DIR, "media-frame105.png"));
          }
        }
        measurements.media_timing = seen;
        const preview = await adapter.renderPreview(media.job);
        const probe = await ffprobeFrames(join(media.jobDir, preview.outputPaths[0]));
        assertEq(probe.frames, 150, "media preview decoded frames");
      },
    },
    {
      name: "failure: a missing asset fails validation and rendering clearly, with no success evidence",
      run: async () => {
        const validation = await adapter.validate(broken.missingAsset.job);
        assertEq(validation.valid, false, "missing asset job must not validate");
        assertTrue(
          validation.findings.some((f) => f.message.includes("assets/does-not-exist.png")),
          `a finding must name the missing asset: ${JSON.stringify(validation.findings)}`
        );
        const err = await expectAdapterError(
          adapter.renderPreview(broken.missingAsset.job),
          "MG_SCHEMA_INVALID",
          "assets/does-not-exist.png"
        );
        assertEq(err.exitClass, 2, "missing asset exit class");
        assertTrue(
          !existsSync(join(broken.missingAsset.jobDir, "renders", "hyperframes", "preview.mp4")),
          "no preview artifact may exist for the failed job"
        );
      },
    },
    {
      name: "failure: an unknown component fails with MG_UNKNOWN_COMPONENT",
      run: async () => {
        const validation = await adapter.validate(broken.unknownComponent.job);
        assertEq(validation.valid, false, "unknown component job must not validate");
        assertEq(validation.firstErrorCategory, "MG_UNKNOWN_COMPONENT", "first error category");
        const err = await expectAdapterError(
          adapter.renderStill(broken.unknownComponent.job, 0),
          "MG_UNKNOWN_COMPONENT",
          "C99"
        );
        assertEq(err.exitClass, 2, "unknown component exit class");
      },
    },
    {
      name: "cancellation: an in-flight render cancelled through the adapter rejects MG_CANCELLED",
      run: async () => {
        const pending = adapter.renderPreview(c05.job);
        // Attach a handler immediately so a rejection that lands before
        // the cancel call is never an unhandled rejection; the outcome
        // is still asserted through expectAdapterError below.
        void pending.catch(() => undefined);
        await new Promise((r) => setTimeout(r, 1500));
        await adapter.cancel(c05.job.jobId);
        const err = await expectAdapterError(pending, "MG_CANCELLED", "cancelled");
        assertEq(err.exitClass, 8, "cancel exit class");
        measurements.cancellation = { category: err.category, exitClass: err.exitClass };
      },
    },
  ];

  let passed = 0;
  let failed = 0;
  for (const c of cases) {
    try {
      await c.run();
      passed += 1;
      console.log(`PASS ${c.name}`);
    } catch (err) {
      failed += 1;
      console.log(`FAIL ${c.name}: ${(err as Error).message}`);
    }
  }
  measurements.cases = { passed, failed, total: cases.length };
  // MG-043 static-record pattern (D-EVIDENCE-REWRITE): never rewrite
  // the committed measurements.json. Compare the derived record
  // against it and fail on drift; adoption is a reviewed copy of the
  // derived file (see runtime/tests/evidence-record.ts).
  const recordCheck = checkStaticEvidenceRecord({
    derived: measurements,
    recordPath: join(EVIDENCE_DIR, "measurements.json"),
    scratchPath: join(WORK_DIR, "measurements.derived.json"),
    repoRoot: REPO_ROOT,
  });
  if (recordCheck.ok) {
    console.log("Static evidence record matches (tests/evidence/mg005/measurements.json)");
  } else {
    failed += 1;
    console.log("FAIL static evidence record drift (tests/evidence/mg005/measurements.json):");
    for (const d of recordCheck.diffs) console.log(`  ${d}`);
    console.log(`  derived measurements: ${recordCheck.scratchPath}`);
    console.log(
      "  if this change is intentional, adopt it by copying the derived file over the record in a reviewed change"
    );
  }
  console.log(`Hyperframes adapter: ${passed}/${cases.length} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(`run-hyperframes setup failed: ${(err as Error).message}`);
    process.exit(1);
  }
);
