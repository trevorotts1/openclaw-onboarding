// Export profile tests for MG-040 (Directive MG-040: verified
// transparency and intermediate-export profiles).
//
// These are REAL toolchain tests: the pinned ffmpeg 8.1.2 encoders,
// the pinned Hyperframes CLI 0.8.155, and the pinned Remotion
// 4.0.535 renderer, exercised end to end. Nothing is mocked.
//
// What is proven, in order:
// - Export profiles are data whose ids match the manifest contract
//   enum exactly; the default stays opaque H.264.
// - The toolchain probe qualifies each alpha encode by a live
//   micro-roundtrip whose decoded alpha is measured, not asserted.
// - Capability selection runs before authoring: it routes alpha to a
//   qualified route or fails by name (MG_CAPABILITY_UNSUPPORTED).
// - An analytic alpha fixture (feathered disc, half-alpha rectangle,
//   chromatic detail: tests/fixtures/export/alpha-edge.json) is
//   exported through both alpha profiles; the decoded alpha channel
//   is measured (varying values, real partial alpha) and the decoded
//   frames are composited over light and dark backgrounds and
//   checked against the analytic composite for matte halo and for
//   missing layers.
// - Transcode integrity: frame counts are exact through every
//   generation; known-patch color stays within the intermediate
//   policy's tolerances through two generations under the policy,
//   while an unmanaged double lossy encode drifts measurably
//   further on the detail region.
// - Packaging metadata tells the truth: records are built from
//   measurement, the default profile records opaque, and a mislabel
//   is impossible (the builder throws) or caught by named checks.
// - Both adapters deliver a ProRes 4444 alpha final for the C05
//   fixture job with a truthful export record; Hyperframes also
//   delivers VP9 alpha natively, and Remotion refuses VP9 alpha by
//   name (its qualified route is the image-sequence encode).
//
// Exit code 0 when every case passes, 1 otherwise.

import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { AdapterError, type ApprovedMotionJob, type ValidatedMotionJob } from "../src/adapters/types";
import { buildMatrixFromProbeRecords, loadCapabilityMatrix, type RuntimeProbeRecord } from "../src/adapters/capabilities";
import { createHyperframesAdapter, resolveSharedRuntime } from "../src/adapters/hyperframes";
import { createRemotionAdapter } from "../src/adapters/remotion";
import type { Approval, Manifest } from "../src/validation/generated-types";
import {
  EXPORT_PROFILES,
  ExportError,
  INTERMEDIATE_POLICY,
  VIDEO_PROFILE_IDS,
  type ExportProfile,
} from "../src/export/profiles";
import { probeExportToolchain, type ExportToolchainProbe } from "../src/export/probe";
import { selectExportRoute } from "../src/export/select";
import {
  decodeVideoToFrames,
  encodeFrameSequence,
  encodeFrameSequenceWithArgs,
} from "../src/export/encode";
import {
  compositeFrameOver,
  decodeFrameRgba,
  measureAlpha,
  patchMeanRgba,
  probeVideoDetailed,
  regionMae,
  samplePixel,
  type DetailedVideoProbe,
} from "../src/export/verify";
import { buildExportRecord, verifyExportRecord, type ExportRecord } from "../src/export/metadata";
import { runTool } from "../src/export/ffmpeg";

// ---------------------------------------------------------------------------
// Paths, harness
// ---------------------------------------------------------------------------

const SKILL_DIR = resolve(__dirname, "..", "..", "..");
const REPO_ROOT = resolve(SKILL_DIR, "..");
const TMP_SCRATCH = join(REPO_ROOT, ".scratch", "tmp");
mkdirSync(TMP_SCRATCH, { recursive: true });
process.env.TMPDIR = TMP_SCRATCH;

const FIXTURES_ROOT = process.env.MOTION_FIXTURES_ROOT
  ? resolve(process.env.MOTION_FIXTURES_ROOT)
  : join(SKILL_DIR, "tests", "fixtures");
const EVIDENCE_DIR = join(SKILL_DIR, "tests", "evidence", "mg040");
const SCRATCH = join(REPO_ROOT, ".scratch", "mg040-tests");
const SCHEMA_PATH = join(SKILL_DIR, "references", "contracts-v2.schema.json");

function assertTrue(cond: boolean, message: string): void {
  if (!cond) throw new Error(message);
}

function assertEq<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function assertClose(actual: number, expected: number, tol: number, message: string): void {
  if (Math.abs(actual - expected) > tol) {
    throw new Error(`${message}: expected ${expected} +/- ${tol}, got ${actual}`);
  }
}

interface Case {
  name: string;
  run: () => Promise<void> | void;
}

const CASES: Case[] = [];
function test(name: string, run: Case["run"]): void {
  CASES.push({ name, run });
}

// ---------------------------------------------------------------------------
// The analytic alpha fixture (tests/fixtures/export/alpha-edge.json)
// ---------------------------------------------------------------------------

interface AlphaFixtureSpec {
  canvas: { width: number; height: number };
  fps: number;
  frames: number;
  disc: { center: [number, number]; solid_radius: number; outer_radius: number; color: [number, number, number] };
  rect: { x0: number; x1: number; y0: number; y1: number; color: [number, number, number]; alpha: number };
  checker: { x0: number; x1: number; y0: number; y1: number; colors: [[number, number, number], [number, number, number]]; alpha: number };
  samples: Record<string, [number, number]>;
  backgrounds: { light: [number, number, number]; dark: [number, number, number] };
}

const SPEC = JSON.parse(
  readFileSync(join(FIXTURES_ROOT, "export", "alpha-edge.json"), "utf8")
) as AlphaFixtureSpec;

/** Analytic alpha of the disc at a distance from its center. */
function discAlphaAt(distance: number): number {
  const { solid_radius, outer_radius } = SPEC.disc;
  if (distance <= solid_radius) return 255;
  if (distance >= outer_radius) return 0;
  return ((outer_radius - distance) / (outer_radius - solid_radius)) * 255;
}

/** Analytic straight-alpha composite of a color over a background. */
function compositeOf(color: [number, number, number], alpha: number, bg: [number, number, number]): [number, number, number] {
  const a = alpha / 255;
  return [
    a * color[0] + (1 - a) * bg[0],
    a * color[1] + (1 - a) * bg[1],
    a * color[2] + (1 - a) * bg[2],
  ];
}

/** What the disc edge would composite to if the stream had been
 * premultiplied against a black matte and then treated as straight
 * alpha (the classic halo corruption): the fringe darkens toward
 * the matte instead of blending with the background. */
function blackMatteCorrupted(color: [number, number, number], alpha: number, bg: [number, number, number]): [number, number, number] {
  const a = alpha / 255;
  return [
    a * a * color[0] + (1 - a) * bg[0],
    a * a * color[1] + (1 - a) * bg[1],
    a * a * color[2] + (1 - a) * bg[2],
  ];
}

/** Generate the fixture's PNG frames from the spec with ffmpeg geq.
 * The expressions are built from the spec's own numbers, so the
 * generator and the expectations cannot drift apart silently. */
function generateFixtureFrames(dir: string): string {
  mkdirSync(dir, { recursive: true });
  const { width, height } = SPEC.canvas;
  const [cx, cy] = SPEC.disc.center;
  const dist = `hypot(X-${cx},Y-${cy})`;
  const inDisc = `lt(${dist},${SPEC.disc.outer_radius})`;
  const inRect = `between(X,${SPEC.rect.x0},${SPEC.rect.x1})*between(Y,${SPEC.rect.y0},${SPEC.rect.y1})`;
  const inChecker = `between(X,${SPEC.checker.x0},${SPEC.checker.x1})*between(Y,${SPEC.checker.y0},${SPEC.checker.y1})`;
  const checkerPick = `eq(mod(X+Y,2),0)`;
  const channel = (idx: 0 | 1 | 2): string =>
    `if(${inDisc},${SPEC.disc.color[idx]},if(${inRect},${SPEC.rect.color[idx]},if(${inChecker},if(${checkerPick},${SPEC.checker.colors[0][idx]},${SPEC.checker.colors[1][idx]}),0)))`;
  const alphaExpr =
    `if(${inDisc},clip((${SPEC.disc.outer_radius}-${dist})/${SPEC.disc.outer_radius - SPEC.disc.solid_radius},0,1)*255,` +
    `if(${inRect},${SPEC.rect.alpha},if(${inChecker},${SPEC.checker.alpha},0)))`;
  const lavfi =
    `nullsrc=s=${width}x${height}:r=${SPEC.fps}:d=${SPEC.frames / SPEC.fps},format=rgba,` +
    `geq=r='${channel(0)}':g='${channel(1)}':b='${channel(2)}':a='${alphaExpr}'`;
  runTool("ffmpeg", [
    "-v",
    "error",
    "-f",
    "lavfi",
    "-i",
    lavfi,
    "-frames:v",
    String(SPEC.frames),
    join(dir, "f%03d.png"),
  ]);
  return join(dir, "f%03d.png");
}

// ---------------------------------------------------------------------------
// Shared state across cases
// ---------------------------------------------------------------------------

const shared: {
  toolchain: ExportToolchainProbe | null;
  fixturePattern: string | null;
  sourceFrame: Buffer | null;
  sourceProbe: DetailedVideoProbe | null;
  artifacts: Record<string, string>;
  measurements: Record<string, unknown>;
} = {
  toolchain: null,
  fixturePattern: null,
  sourceFrame: null,
  sourceProbe: null,
  artifacts: {},
  measurements: {},
};

function fixturePattern(): string {
  if (!shared.fixturePattern) {
    shared.fixturePattern = generateFixtureFrames(join(SCRATCH, "alpha-fixture"));
    const firstFrame = join(SCRATCH, "alpha-fixture", "f001.png");
    shared.sourceProbe = probeVideoDetailed(firstFrame);
    shared.sourceFrame = decodeFrameRgba(firstFrame, 0, shared.sourceProbe);
  }
  return shared.fixturePattern;
}

// ---------------------------------------------------------------------------
// Cases: profile data and toolchain qualification
// ---------------------------------------------------------------------------

test("profile ids match the manifest contract enum exactly", () => {
  const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf8")) as Record<string, unknown>;
  let enumValues: string[] = [];
  let enumFound = false;
  const visit = (node: unknown): void => {
    if (Array.isArray(node)) {
      for (const v of node) visit(v);
      return;
    }
    if (node && typeof node === "object") {
      const rec = node as Record<string, unknown>;
      const vp = rec.video_profile;
      if (vp && typeof vp === "object" && Array.isArray((vp as Record<string, unknown>).enum)) {
        enumValues = (vp as Record<string, unknown>).enum as string[];
        enumFound = true;
      }
      for (const v of Object.values(rec)) visit(v);
    }
  };
  visit(schema);
  assertTrue(enumFound, "video_profile enum not found in contracts-v2.schema.json");
  const sorted = [...enumValues].sort();
  assertEq(
    JSON.stringify(sorted),
    JSON.stringify([...VIDEO_PROFILE_IDS].sort()),
    "export profile ids equal the manifest delivery.video_profile enum"
  );
  for (const id of VIDEO_PROFILE_IDS) {
    const p = EXPORT_PROFILES[id];
    assertEq(p.id, id, "profile id field");
    assertTrue(p.containerExtension.startsWith("."), `${id} names a container extension`);
    assertTrue(p.streamCodec.length > 0, `${id} names a stream codec`);
    if (p.alpha) {
      assertTrue(p.sequenceEncoder !== null, `${id} names a qualified sequence encoder`);
      assertTrue(
        p.sequenceEncodeArgs.join(" ").includes("yuva"),
        `${id} sequence encode names an alpha pixel format`
      );
    }
  }
  const def = EXPORT_PROFILES.h264_opaque;
  assertEq(def.alpha, false, "the default delivery profile is opaque");
  assertEq(def.streamCodec, "h264", "the default delivery profile is H.264 (the PowerPoint path)");
  assertEq(def.containerExtension, ".mp4", "the default delivery profile ships an mp4");
});

test("toolchain probe qualifies the alpha encodes by live roundtrip", () => {
  const rt = resolveSharedRuntime();
  const probe = probeExportToolchain(join(SCRATCH, "probe"), { hyperframesCliBin: rt.cliBin });
  shared.toolchain = probe;
  assertTrue(
    probe.ffmpegVersion.startsWith("ffmpeg version 8."),
    `pinned ffmpeg measured, got: ${probe.ffmpegVersion}`
  );
  for (const encoder of ["prores_ks", "libvpx-vp9", "libx264"]) {
    assertTrue(probe.encoders[encoder].present, `encoder ${encoder} present in the pinned ffmpeg`);
  }
  assertTrue(
    probe.encoders.prores_ks.pixelFormats.some((f) => f.startsWith("yuva444")),
    "prores_ks supports an alpha 444 pixel format"
  );
  assertTrue(
    probe.encoders["libvpx-vp9"].pixelFormats.includes("yuva420p"),
    "libvpx-vp9 supports yuva420p"
  );
  for (const id of ["prores_4444_alpha", "vp9_alpha"] as const) {
    const q = probe.profiles[id];
    assertTrue(q.qualified, `${id} qualified by live roundtrip: ${q.evidence.join(" ")}`);
    assertTrue(
      (q.partialAlphaPixels ?? 0) > 0,
      `${id} roundtrip measured real partial alpha (${q.partialAlphaPixels} pixels)`
    );
  }
  assertTrue(probe.profiles.h264_opaque.qualified, "h264_opaque qualified by live roundtrip");
  assertTrue(probe.hyperframesCli !== null, "hyperframes CLI help captured");
  assertTrue(
    probe.hyperframesCli!.formats.includes("mov") && probe.hyperframesCli!.formats.includes("webm"),
    `CLI documents mov and webm formats (saw: ${probe.hyperframesCli!.formats.join(", ")})`
  );
  assertTrue(
    probe.hyperframesCli!.transparencyDocumented,
    "CLI help documents transparency and the ProRes 4444 alpha profile"
  );
});

// ---------------------------------------------------------------------------
// Cases: capability selection before authoring
// ---------------------------------------------------------------------------

test("capability selection routes alpha only to qualified routes, or fails by name", () => {
  const toolchain = shared.toolchain;
  assertTrue(toolchain !== null, "toolchain probe ran first");
  const shipped = loadCapabilityMatrix();

  // The shipped matrix confirms no alpha (the adapters' probes
  // measured launch and stills only), so alpha selects the route
  // the live toolchain probe qualified: image-sequence-plus-encode.
  const sel = selectExportRoute({
    profileId: "prores_4444_alpha",
    engine: "hyperframes",
    matrix: shipped,
    toolchain,
  });
  assertEq(sel.route.kind, "image_sequence_encode", "shipped matrix: alpha takes the qualified sequence route");
  assertEq(sel.confirmedBy, "export_toolchain_probe", "sequence route confirmed by the toolchain probe");

  // A matrix refreshed from a probe record that measured alpha
  // confirms the engine-native route instead.
  const confirmingRecord: RuntimeProbeRecord = {
    engine: "hyperframes",
    version: "0.8.155",
    runtimeLockId: "lock-selection-test",
    probedAt: new Date().toISOString(),
    platform: "linux/x64",
    launchSucceeded: true,
    codecs: ["h264", "prores", "vp9"],
    transparency: { alphaVideo: true, profiles: ["prores_4444_alpha", "vp9_alpha"] },
    mediaTypes: ["image/png"],
    features3d: [],
    evidence: ["suite-supplied confirmation record exercising the matrix branch of selection"],
  };
  const refreshed = buildMatrixFromProbeRecords([confirmingRecord], shipped);
  const native = selectExportRoute({
    profileId: "prores_4444_alpha",
    engine: "hyperframes",
    matrix: refreshed,
    toolchain,
  });
  assertEq(native.route.kind, "engine_native", "confirming matrix: alpha takes the engine-native route");
  assertEq(native.confirmedBy, "capability_matrix", "native route confirmed by the capability matrix");

  // With the sequence encode disqualified and no matrix
  // confirmation, selection fails by name before any rendering.
  const disqualified: ExportToolchainProbe = {
    ...toolchain!,
    profiles: {
      ...toolchain!.profiles,
      vp9_alpha: {
        ...toolchain!.profiles.vp9_alpha,
        qualified: false,
        evidence: ["suite-disqualified encode for the refusal case"],
      },
    },
  };
  let caught: unknown = null;
  try {
    selectExportRoute({ profileId: "vp9_alpha", engine: "remotion", matrix: shipped, toolchain: disqualified });
  } catch (err) {
    caught = err;
  }
  assertTrue(caught instanceof ExportError, "unqualified alpha selection throws ExportError");
  const exportErr = caught as ExportError;
  assertEq(exportErr.category, "MG_CAPABILITY_UNSUPPORTED", "refusal category is the Section 16.9 capability name");
  assertEq(exportErr.exitClass, 3, "refusal exit class is 3");
  assertEq(exportErr.check, "export.route_qualified", "refusal names its check");

  // The opaque default is the baseline contract on both engines,
  // with no matrix or probe confirmation required.
  for (const engine of ["hyperframes", "remotion"] as const) {
    const base = selectExportRoute({ profileId: "h264_opaque", engine, matrix: null, toolchain: null });
    assertEq(base.route.kind, "engine_native", `h264_opaque on ${engine} is the native baseline`);
    assertEq(base.confirmedBy, "baseline_contract", "baseline confirmed by contract");
  }

  // Unknown profiles fail by name too.
  let unknown: unknown = null;
  try {
    selectExportRoute({ profileId: "prores_422", engine: "hyperframes", matrix: shipped, toolchain });
  } catch (err) {
    unknown = err;
  }
  assertTrue(unknown instanceof ExportError, "unknown profile throws ExportError");
  assertEq((unknown as ExportError).check, "export.profile_known", "unknown profile names its check");
});

// ---------------------------------------------------------------------------
// Cases: verified alpha on the analytic fixture
// ---------------------------------------------------------------------------

function checkAlphaArtifact(profileId: "prores_4444_alpha" | "vp9_alpha", artifactPath: string): void {
  const profile = EXPORT_PROFILES[profileId];
  const probe = probeVideoDetailed(artifactPath);
  assertEq(probe.codecName, profile.streamCodec, `${profileId} stream codec`);
  assertEq(probe.frameCount, SPEC.frames, `${profileId} exact frame count`);
  assertEq(probe.width, SPEC.canvas.width, `${profileId} width`);
  assertEq(probe.height, SPEC.canvas.height, `${profileId} height`);
  assertTrue(probe.alphaChannelPresent, `${profileId} carries an alpha channel (${probe.pixelFormat})`);

  const measurement = measureAlpha(artifactPath, probe, [0]);
  assertTrue(
    measurement.distinctAlphaValues >= 40,
    `${profileId} alpha genuinely varies: ${measurement.distinctAlphaValues} distinct values (a binary matte has at most 2)`
  );
  assertTrue(
    measurement.partialAlphaPixels >= 1000,
    `${profileId} has real partial alpha: ${measurement.partialAlphaPixels} pixels`
  );

  const alphaTol = profileId === "prores_4444_alpha" ? 6 : 8;
  const colorTol = profileId === "prores_4444_alpha" ? 4 : 10;
  const frame = decodeFrameRgba(artifactPath, 0, probe);
  const w = SPEC.canvas.width;
  const px = (name: string): number[] => samplePixel(frame, w, SPEC.samples[name][0], SPEC.samples[name][1], 4);
  const [cx, cy] = SPEC.disc.center;
  const edge62Alpha = discAlphaAt(Math.abs(SPEC.samples.edge_at_62[0] - cx));
  const edge60Alpha = discAlphaAt(Math.abs(SPEC.samples.edge_at_60[0] - cx));
  assertClose(px("corner")[3], 0, alphaTol, `${profileId} corner is fully transparent`);
  assertClose(px("disc_core")[3], 255, alphaTol, `${profileId} disc core is opaque`);
  assertClose(px("edge_at_62")[3], edge62Alpha, alphaTol, `${profileId} feathered edge at distance 62`);
  assertClose(px("edge_at_60")[3], edge60Alpha, alphaTol, `${profileId} feathered edge at distance 60`);
  assertClose(px("rect_center")[3], SPEC.rect.alpha, alphaTol, `${profileId} rectangle keeps its half alpha`);
  for (let c = 0; c < 3; c += 1) {
    assertClose(px("disc_core")[c], SPEC.disc.color[c], colorTol, `${profileId} disc core color channel ${c}`);
    assertClose(px("rect_center")[c], SPEC.rect.color[c], colorTol + 2, `${profileId} rectangle color channel ${c}`);
  }

  // Composites over both backgrounds, checked against the analytic
  // composite: this is where a matte halo or a missing layer shows.
  const compTol = INTERMEDIATE_POLICY.tolerances.compositeSample;
  for (const bgName of ["light", "dark"] as const) {
    const bg = SPEC.backgrounds[bgName];
    const comp = compositeFrameOver(artifactPath, 0, probe, bg);
    const sample = (name: string): number[] =>
      samplePixel(comp, w, SPEC.samples[name][0], SPEC.samples[name][1], 3);
    for (let c = 0; c < 3; c += 1) {
      assertClose(sample("corner")[c], bg[c], compTol, `${profileId} over ${bgName}: corner shows the background (channel ${c})`);
      assertClose(sample("disc_core")[c], SPEC.disc.color[c], compTol, `${profileId} over ${bgName}: disc core (channel ${c})`);
      const edgeExpected = compositeOf(SPEC.disc.color, edge62Alpha, bg)[c];
      assertClose(sample("edge_at_62")[c], edgeExpected, compTol, `${profileId} over ${bgName}: feathered edge composite (channel ${c})`);
      const rectExpected = compositeOf(SPEC.rect.color, SPEC.rect.alpha, bg)[c];
      assertClose(
        sample("rect_center")[c],
        rectExpected,
        compTol,
        `${profileId} over ${bgName}: half-alpha rectangle composite (channel ${c}); a missing layer would read the bare background`
      );
    }
    // Named halo check: the measured edge composite must sit far
    // from the black-matte-corrupted composite (on the light
    // background the corruption is worth about 50 in the red
    // channel, six times the tolerance).
    if (bgName === "light") {
      const measured = sample("edge_at_62")[0];
      const corrupted = blackMatteCorrupted(SPEC.disc.color, edge62Alpha, bg)[0];
      assertTrue(
        Math.abs(measured - corrupted) >= 25,
        `${profileId}: edge composite red channel ${measured} is not the black-matte value ${corrupted.toFixed(1)} (no matte halo)`
      );
    }
  }

  shared.measurements[profileId] = {
    codec: probe.codecName,
    pixelFormat: probe.pixelFormat,
    distinctAlphaValues: measurement.distinctAlphaValues,
    partialAlphaPixels: measurement.partialAlphaPixels,
    transparentPixels: measurement.transparentPixels,
    opaquePixels: measurement.opaquePixels,
  };
}

test("analytic alpha fixture through the ProRes 4444 profile", () => {
  const out = join(SCRATCH, "alpha-prores.mov");
  const { probe } = encodeFrameSequence({
    framesPattern: fixturePattern(),
    frameRate: SPEC.fps,
    profile: EXPORT_PROFILES.prores_4444_alpha,
    outPath: out,
  });
  assertEq(probe.frameCount, SPEC.frames, "encoded frame count is exact");
  shared.artifacts.prores_4444_alpha = out;
  checkAlphaArtifact("prores_4444_alpha", out);
});

test("analytic alpha fixture through the VP9 alpha profile", () => {
  const out = join(SCRATCH, "alpha-vp9.webm");
  const { probe } = encodeFrameSequence({
    framesPattern: fixturePattern(),
    frameRate: SPEC.fps,
    profile: EXPORT_PROFILES.vp9_alpha,
    outPath: out,
  });
  assertEq(probe.frameCount, SPEC.frames, "encoded frame count is exact");
  shared.artifacts.vp9_alpha = out;
  checkAlphaArtifact("vp9_alpha", out);
});

// ---------------------------------------------------------------------------
// Cases: transcode integrity and the intermediate policy
// ---------------------------------------------------------------------------

function patchDiffs(frame: Buffer, source: Buffer): { core: number[]; rect: number[] } {
  const w = SPEC.canvas.width;
  const mean = (buf: Buffer, cx: number, cy: number): number[] => patchMeanRgba(buf, w, cx, cy, 8);
  const diff = (a: number[], b: number[]): number[] => a.map((v, i) => Math.abs(v - b[i]));
  return {
    core: diff(mean(frame, SPEC.disc.center[0], SPEC.disc.center[1]), mean(source, SPEC.disc.center[0], SPEC.disc.center[1])),
    rect: diff(mean(frame, SPEC.samples.rect_center[0], SPEC.samples.rect_center[1]), mean(source, SPEC.samples.rect_center[0], SPEC.samples.rect_center[1])),
  };
}

function frameZeroOf(path: string): Buffer {
  const probe = probeVideoDetailed(path);
  assertEq(probe.frameCount, SPEC.frames, `${path} keeps the exact frame count`);
  return decodeFrameRgba(path, 0, probe);
}

function countPngs(dir: string): number {
  return readdirSync(dir).filter((f) => f.endsWith(".png")).length;
}

test("transcode integrity: two generations under the policy stay in tolerance, unmanaged drifts further", () => {
  const pattern = fixturePattern();
  const source = shared.sourceFrame!;
  const tol = INTERMEDIATE_POLICY.tolerances;
  const genDir = join(SCRATCH, "generations");
  const checkerRegion = { x0: SPEC.checker.x0, x1: SPEC.checker.x1 + 1, y0: SPEC.checker.y0, y1: SPEC.checker.y1 + 1 };
  const checkerMae = (frame: Buffer): number => {
    const mae = regionMae(frame, source, SPEC.canvas.width, 4, checkerRegion);
    return (mae[0] + mae[1] + mae[2]) / 3;
  };
  const checkerMaeRed = (frame: Buffer): number =>
    regionMae(frame, source, SPEC.canvas.width, 4, checkerRegion)[0];

  // ProRes 4444 under the policy: PNG mezzanine, one encode per
  // generation, generation 2 re-encoded from generation 1 decoded
  // back to the PNG mezzanine (the worst case the policy allows).
  const prores = EXPORT_PROFILES.prores_4444_alpha;
  const p1 = encodeFrameSequence({ framesPattern: pattern, frameRate: SPEC.fps, profile: prores, outPath: join(genDir, "prores-g1.mov") });
  const p1FramesDir = join(genDir, "prores-g1-frames");
  decodeVideoToFrames({ videoPath: p1.outPath, codecName: "prores", framesPattern: join(p1FramesDir, "f%03d.png") });
  assertEq(countPngs(p1FramesDir), SPEC.frames, "decoded generation 1 frame count is exact");
  const p2 = encodeFrameSequence({ framesPattern: join(p1FramesDir, "f%03d.png"), frameRate: SPEC.fps, profile: prores, outPath: join(genDir, "prores-g2.mov") });
  const p1Diffs = patchDiffs(frameZeroOf(p1.outPath), source);
  const p2Diffs = patchDiffs(frameZeroOf(p2.outPath), source);
  for (let c = 0; c < 4; c += 1) {
    assertTrue(p1Diffs.core[c] <= tol.patchMeanProres && p1Diffs.rect[c] <= tol.patchMeanProres, `prores gen1 patch channel ${c} within ${tol.patchMeanProres}: core ${p1Diffs.core[c].toFixed(2)}, rect ${p1Diffs.rect[c].toFixed(2)}`);
    assertTrue(p2Diffs.core[c] <= tol.patchMeanTwoGenerationsProres && p2Diffs.rect[c] <= tol.patchMeanTwoGenerationsProres, `prores gen2 patch channel ${c} within ${tol.patchMeanTwoGenerationsProres}: core ${p2Diffs.core[c].toFixed(2)}, rect ${p2Diffs.rect[c].toFixed(2)}`);
  }
  const proresChecker2 = checkerMae(frameZeroOf(p2.outPath));
  assertTrue(
    proresChecker2 <= tol.detailRegionMaeProresTwoGenerations,
    `prores gen2 detail region MAE ${proresChecker2.toFixed(3)} within ${tol.detailRegionMaeProresTwoGenerations}`
  );

  // VP9 under the policy: the video mezzanine is VP9 lossless, so
  // generation 2 adds no quantization on top of the first encode.
  const mezzanineArgs = INTERMEDIATE_POLICY.videoMezzanineArgs.vp9_alpha;
  const v1 = encodeFrameSequenceWithArgs({ framesPattern: pattern, frameRate: SPEC.fps, codecArgs: [...mezzanineArgs], outPath: join(genDir, "vp9-mezz-g1.webm") });
  const v1FramesDir = join(genDir, "vp9-g1-frames");
  decodeVideoToFrames({ videoPath: v1.outPath, codecName: "vp9", framesPattern: join(v1FramesDir, "f%03d.png") });
  assertEq(countPngs(v1FramesDir), SPEC.frames, "decoded VP9 generation 1 frame count is exact");
  const v2 = encodeFrameSequenceWithArgs({ framesPattern: join(v1FramesDir, "f%03d.png"), frameRate: SPEC.fps, codecArgs: [...mezzanineArgs], outPath: join(genDir, "vp9-mezz-g2.webm") });
  const v2Diffs = patchDiffs(frameZeroOf(v2.outPath), source);
  for (let c = 0; c < 4; c += 1) {
    assertTrue(v2Diffs.core[c] <= tol.patchMeanTwoGenerationsVp9 && v2Diffs.rect[c] <= tol.patchMeanTwoGenerationsVp9, `vp9 policy gen2 patch channel ${c} within ${tol.patchMeanTwoGenerationsVp9}: core ${v2Diffs.core[c].toFixed(2)}, rect ${v2Diffs.rect[c].toFixed(2)}`);
  }

  // The unmanaged chain the policy forbids: a delivery-grade lossy
  // encode (VP9 crf 40) used as the intermediate and encoded again.
  const unmanagedArgs = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "40"];
  const u1 = encodeFrameSequenceWithArgs({ framesPattern: pattern, frameRate: SPEC.fps, codecArgs: unmanagedArgs, outPath: join(genDir, "vp9-unmanaged-g1.webm") });
  const u1FramesDir = join(genDir, "vp9-u1-frames");
  decodeVideoToFrames({ videoPath: u1.outPath, codecName: "vp9", framesPattern: join(u1FramesDir, "f%03d.png") });
  const u2 = encodeFrameSequenceWithArgs({ framesPattern: join(u1FramesDir, "f%03d.png"), frameRate: SPEC.fps, codecArgs: unmanagedArgs, outPath: join(genDir, "vp9-unmanaged-g2.webm") });
  const u1Frame = frameZeroOf(u1.outPath);
  const u2Frame = frameZeroOf(u2.outPath);
  const u1Mae = checkerMae(u1Frame);
  const u2Mae = checkerMae(u2Frame);
  const u1Red = checkerMaeRed(u1Frame);
  const u2Red = checkerMaeRed(u2Frame);
  assertTrue(u1Mae >= 40, `unmanaged gen1 detail MAE ${u1Mae.toFixed(1)} is already far outside the policy tolerance`);
  assertTrue(
    u2Red > u1Red + 3,
    `unmanaged drift compounds on the detail region: gen2 red MAE ${u2Red.toFixed(1)} exceeds gen1 ${u1Red.toFixed(1)}`
  );
  assertTrue(
    u2Mae >= 10 * Math.max(proresChecker2, 0.01),
    `unmanaged gen2 detail MAE ${u2Mae.toFixed(1)} dwarfs the policy gen2 ${proresChecker2.toFixed(3)}`
  );
  shared.measurements.generations = {
    proresCheckerMaeGen2: proresChecker2,
    unmanagedCheckerMaeGen1: u1Mae,
    unmanagedCheckerMaeGen2: u2Mae,
  };
});

// ---------------------------------------------------------------------------
// Cases: packaging metadata truth
// ---------------------------------------------------------------------------

test("default profile artifact probes opaque and its record says so", () => {
  const out = join(SCRATCH, "default-h264.mp4");
  const { probe } = encodeFrameSequence({
    framesPattern: fixturePattern(),
    frameRate: SPEC.fps,
    profile: EXPORT_PROFILES.h264_opaque,
    outPath: out,
  });
  assertEq(probe.codecName, "h264", "default profile codec is h264");
  assertEq(probe.pixelFormat, "yuv420p", "default profile pixel format is yuv420p (portable, opaque)");
  assertEq(probe.alphaChannelPresent, false, "default profile artifact has no alpha channel");
  assertEq(probe.frameCount, SPEC.frames, "default profile frame count is exact");
  shared.artifacts.h264_opaque = out;
  const record = buildExportRecord({
    profile: EXPORT_PROFILES.h264_opaque,
    route: { engine: "export-layer", kind: "image_sequence_encode", detail: "suite default-profile case" },
    artifactAbsPath: out,
    artifactLogicalPath: "mg040/default-h264.mp4",
  });
  assertEq(record.alpha.verdict, "opaque", "default profile record verdict is opaque");
  assertEq(record.alpha.channelPresent, false, "default profile record channelPresent is false");
  assertEq(record.stream.codec, "h264", "default profile record codec is the measured h264");
  for (const f of verifyExportRecord(record, out)) {
    assertTrue(f.ok, `default record check ${f.check}: ${f.detail}`);
  }
});

test("packaging metadata: measured records verify, forgeries are caught by name, mislabels are impossible", () => {
  const proresPath = shared.artifacts.prores_4444_alpha;
  const h264Path = shared.artifacts.h264_opaque;
  assertTrue(Boolean(proresPath && h264Path), "alpha and default artifacts exist from earlier cases");

  const record = buildExportRecord({
    profile: EXPORT_PROFILES.prores_4444_alpha,
    route: { engine: "export-layer", kind: "image_sequence_encode", detail: "suite metadata case" },
    artifactAbsPath: proresPath,
    artifactLogicalPath: "mg040/alpha-prores.mov",
  });
  assertEq(record.alpha.verdict, "verified_alpha", "the feathered fixture measures verified_alpha");
  assertEq(record.stream.codec, "prores", "record codec is the measured codec");
  assertTrue(record.alpha.measurement.partialAlphaPixels > 0, "record carries the measured partial alpha");
  for (const f of verifyExportRecord(record, proresPath)) {
    assertTrue(f.ok, `record check ${f.check}: ${f.detail}`);
  }

  // Forgery 1: the same record relabeled as a different profile.
  const forgedProfile: ExportRecord = { ...record, profile: "vp9_alpha" };
  const labelFinding = verifyExportRecord(forgedProfile, proresPath).find((f) => f.check === "export.label_match");
  assertTrue(labelFinding !== undefined && !labelFinding.ok, "a record claiming the wrong profile is caught by export.label_match");

  // Forgery 2: an opaque artifact whose record claims verified alpha.
  const opaqueRecord = buildExportRecord({
    profile: EXPORT_PROFILES.h264_opaque,
    route: { engine: "export-layer", kind: "image_sequence_encode", detail: "suite metadata case" },
    artifactAbsPath: h264Path,
    artifactLogicalPath: "mg040/default-h264.mp4",
  });
  const forgedVerdict: ExportRecord = {
    ...opaqueRecord,
    alpha: { ...opaqueRecord.alpha, verdict: "verified_alpha", channelPresent: true },
  };
  const verdictFinding = verifyExportRecord(forgedVerdict, h264Path).find((f) => f.check === "export.alpha_verdict_match");
  assertTrue(verdictFinding !== undefined && !verdictFinding.ok, "a record claiming alpha for an opaque encode is caught by export.alpha_verdict_match");

  // Mislabel by construction: the builder refuses both directions.
  let alphaOverOpaque: unknown = null;
  try {
    buildExportRecord({
      profile: EXPORT_PROFILES.prores_4444_alpha,
      route: { engine: "export-layer", kind: "image_sequence_encode", detail: "suite metadata case" },
      artifactAbsPath: h264Path,
      artifactLogicalPath: "mg040/mislabeled.mov",
    });
  } catch (err) {
    alphaOverOpaque = err;
  }
  assertTrue(alphaOverOpaque instanceof ExportError, "alpha profile over an opaque artifact throws");
  assertEq((alphaOverOpaque as ExportError).check, "export.alpha_channel_present", "refusal names export.alpha_channel_present");
  assertEq((alphaOverOpaque as ExportError).category, "MG_QC_FAILED", "mislabel refusal is MG_QC_FAILED");
  assertEq((alphaOverOpaque as ExportError).exitClass, 6, "mislabel refusal exit class is 6");

  let opaqueOverAlpha: unknown = null;
  try {
    buildExportRecord({
      profile: EXPORT_PROFILES.h264_opaque,
      route: { engine: "export-layer", kind: "image_sequence_encode", detail: "suite metadata case" },
      artifactAbsPath: proresPath,
      artifactLogicalPath: "mg040/mislabeled.mp4",
    });
  } catch (err) {
    opaqueOverAlpha = err;
  }
  assertTrue(opaqueOverAlpha instanceof ExportError, "opaque profile over an alpha artifact throws");
  assertEq((opaqueOverAlpha as ExportError).check, "export.alpha_unexpected", "mirror refusal names export.alpha_unexpected");
});

// ---------------------------------------------------------------------------
// Cases: adapter end-to-end finals on the C05 fixture job
// ---------------------------------------------------------------------------

function fixtureApproval(jobId: string): Approval {
  return {
    schema_version: "2.0",
    approval_id: "mg040-fixture-approval",
    job_id: jobId,
    company_id: "fixture-company",
    scope: "delivery",
    decision: "approved",
    subject_revision: "mg040-fixture",
    artifact_refs: [],
    actor_id: "mg040-export-test",
    source_event_ref: null,
    authority_status: "not_verified",
  };
}

function stageAdapterJob(
  engine: "hyperframes" | "remotion",
  profileId: string,
  dest: string
): { jobDir: string; approved: ApprovedMotionJob } {
  const src = join(FIXTURES_ROOT, "modes", "powerpoint_graphic");
  const jobDir = join(SCRATCH, dest);
  rmSync(jobDir, { recursive: true, force: true });
  cpSync(src, jobDir, { recursive: true });
  if (engine === "hyperframes") {
    const scenePath = join(jobDir, "scenes", "bar-01.json");
    const scene = JSON.parse(readFileSync(scenePath, "utf8")) as Record<string, unknown>;
    scene.engine = "hyperframes";
    writeFileSync(scenePath, JSON.stringify(scene, null, 2) + "\n", "utf8");
  }
  const manifestPath = join(jobDir, "manifest.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Manifest;
  if (engine === "hyperframes") {
    (manifest.rendering as { default_engine: string }).default_engine = "hyperframes";
  }
  (manifest.delivery as { video_profile: string }).video_profile = profileId;
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  const job: ValidatedMotionJob = { jobDir, jobId: manifest.job_id, manifest };
  return { jobDir, approved: { ...job, approval: fixtureApproval(manifest.job_id) } };
}

function callCtx(jobId: string): { jobId: string; signal: AbortSignal; timeoutMs: number; deadlineEpochMs: number } {
  const ac = new AbortController();
  return { jobId, signal: ac.signal, timeoutMs: 1800000, deadlineEpochMs: Date.now() + 1800000 };
}

function checkAdapterFinal(
  evidenceRecord: ExportRecord | undefined,
  outAbs: string,
  profile: ExportProfile,
  frames: number
): void {
  assertTrue(existsSync(outAbs), `adapter produced ${outAbs}`);
  const probe = probeVideoDetailed(outAbs);
  assertEq(probe.codecName, profile.streamCodec, `adapter final codec is ${profile.streamCodec}`);
  assertEq(probe.frameCount, frames, "adapter final frame count is exact");
  assertTrue(probe.alphaChannelPresent, "adapter final carries an alpha channel");
  if (profile.id === "prores_4444_alpha") {
    assertTrue(probe.pixelFormat.startsWith("yuva444p"), `adapter prores pixel format is 444 alpha (saw ${probe.pixelFormat})`);
  }
  assertTrue(evidenceRecord !== undefined, "adapter evidence carries the export record");
  const record = evidenceRecord!;
  assertEq(record.profile, profile.id, "record names the job's delivery profile");
  assertEq(record.stream.codec, probe.codecName, "record codec equals the probed codec");
  assertEq(record.alpha.channelPresent, true, "record channelPresent is measured true");
  for (const f of verifyExportRecord(record, outAbs)) {
    assertTrue(f.ok, `adapter record check ${f.check}: ${f.detail}`);
  }
  const sidecar = `${outAbs}.export-record.json`;
  assertTrue(existsSync(sidecar), "export record sidecar written beside the artifact");
  const parsed = JSON.parse(readFileSync(sidecar, "utf8")) as ExportRecord;
  assertEq(parsed.artifactSha256, record.artifactSha256, "sidecar matches the evidence record");
  assertEq(parsed.alpha.verdict, record.alpha.verdict, "sidecar verdict matches the measured verdict");
}

test("hyperframes adapter delivers a ProRes 4444 alpha final with a truthful record", async () => {
  const { jobDir, approved } = stageAdapterJob("hyperframes", "prores_4444_alpha", "hf-prores-job");
  const adapter = createHyperframesAdapter();
  adapter.beginCall(callCtx(approved.jobId));
  const ev = await adapter.renderFinal(approved);
  const outAbs = join(jobDir, "renders", "hyperframes", "final.mov");
  checkAdapterFinal(ev.exportRecord, outAbs, EXPORT_PROFILES.prores_4444_alpha, 180);
  shared.measurements.hyperframesProres = {
    verdict: ev.exportRecord!.alpha.verdict,
    partialAlphaPixels: ev.exportRecord!.alpha.measurement.partialAlphaPixels,
    framesMeasured: ev.exportRecord!.alpha.measurement.framesMeasured,
  };
});

test("hyperframes adapter delivers a VP9 alpha final with a truthful record", async () => {
  const { jobDir, approved } = stageAdapterJob("hyperframes", "vp9_alpha", "hf-vp9-job");
  const adapter = createHyperframesAdapter();
  adapter.beginCall(callCtx(approved.jobId));
  const ev = await adapter.renderFinal(approved);
  const outAbs = join(jobDir, "renders", "hyperframes", "final.webm");
  checkAdapterFinal(ev.exportRecord, outAbs, EXPORT_PROFILES.vp9_alpha, 180);
  shared.measurements.hyperframesVp9 = {
    verdict: ev.exportRecord!.alpha.verdict,
    partialAlphaPixels: ev.exportRecord!.alpha.measurement.partialAlphaPixels,
    framesMeasured: ev.exportRecord!.alpha.measurement.framesMeasured,
  };
});

test("remotion adapter delivers a ProRes 4444 alpha final with a truthful record", async () => {
  const { jobDir, approved } = stageAdapterJob("remotion", "prores_4444_alpha", "remotion-prores-job");
  const adapter = createRemotionAdapter();
  adapter.beginCall(callCtx(approved.jobId));
  const ev = await adapter.renderFinal(approved);
  const outAbs = join(jobDir, "renders", "remotion", "final.mov");
  checkAdapterFinal(ev.exportRecord, outAbs, EXPORT_PROFILES.prores_4444_alpha, 180);
  assertTrue(
    existsSync(join(jobDir, "renders", "remotion", "poster-f150.png")),
    "the delivery poster still ships with the alpha final"
  );
  shared.measurements.remotionProres = {
    verdict: ev.exportRecord!.alpha.verdict,
    partialAlphaPixels: ev.exportRecord!.alpha.measurement.partialAlphaPixels,
    framesMeasured: ev.exportRecord!.alpha.measurement.framesMeasured,
  };
});

test("remotion adapter refuses VP9 alpha by name instead of mislabeling", async () => {
  const { approved } = stageAdapterJob("remotion", "vp9_alpha", "remotion-vp9-job");
  const adapter = createRemotionAdapter();
  adapter.beginCall(callCtx(approved.jobId));
  let caught: unknown = null;
  try {
    await adapter.renderFinal(approved);
  } catch (err) {
    caught = err;
  }
  assertTrue(caught instanceof AdapterError, "remotion vp9 final throws AdapterError");
  assertEq((caught as AdapterError).category, "MG_CAPABILITY_UNSUPPORTED", "refusal category is MG_CAPABILITY_UNSUPPORTED");
  assertEq((caught as AdapterError).exitClass, 3, "refusal exit class is 3");
});

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<number> {
  rmSync(SCRATCH, { recursive: true, force: true });
  mkdirSync(SCRATCH, { recursive: true });
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

  // Evidence: the live toolchain probe record and the measured alpha
  // summary. These are probe records, refreshed by every run.
  try {
    mkdirSync(EVIDENCE_DIR, { recursive: true });
    if (shared.toolchain) {
      writeFileSync(
        join(EVIDENCE_DIR, "export-capabilities.json"),
        JSON.stringify(
          { item: "MG-040", kind: "export-toolchain-probe", ...shared.toolchain },
          null,
          2
        ) + "\n",
        "utf8"
      );
    }
    writeFileSync(
      join(EVIDENCE_DIR, "alpha-measurements.json"),
      JSON.stringify(
        { item: "MG-040", kind: "alpha-measurements", generatedAt: new Date().toISOString(), measurements: shared.measurements },
        null,
        2
      ) + "\n",
      "utf8"
    );
    console.log(`Evidence written to ${EVIDENCE_DIR}`);
  } catch (err) {
    failed += 1;
    console.log(`FAIL evidence write: ${(err as Error).message}`);
  }

  const total = passed + failed;
  console.log(`Export profiles: ${passed}/${total} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
