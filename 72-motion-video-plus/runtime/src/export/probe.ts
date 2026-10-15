// Live toolchain qualification for export profiles (MG-040). A
// profile is qualified only by a probe that actually ran the encode
// on this machine and measured alpha in the decoded output; encoder
// names on a help page are not qualification. The probe generates a
// tiny analytic RGBA sequence (a feathered disc, so partial alpha
// must survive), encodes it with each alpha profile's sequence
// encode, and measures the decoded result with the same code the
// packaging layer trusts (verify.ts).
//
// The probe also captures the pinned Hyperframes CLI's documented
// render formats from its own --help output when the CLI binary is
// supplied, so the native-route claims in profiles.ts trace to the
// pinned binary's documentation, and it records the pinned ffmpeg
// version everything was measured with.

import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { encodeFrameSequence } from "./encode";
import { runTool, runToolText } from "./ffmpeg";
import { EXPORT_PROFILES, type VideoProfileId } from "./profiles";
import { measureAlpha } from "./verify";

export interface ProfileQualification {
  profile: VideoProfileId;
  /** True only when the micro-roundtrip encoded and the decoded
   * output measured real partial alpha (for alpha profiles) or a
   * clean opaque stream (for the opaque profile). */
  qualified: boolean;
  route: "image_sequence_encode";
  measuredCodec: string | null;
  measuredPixelFormat: string | null;
  distinctAlphaValues: number | null;
  partialAlphaPixels: number | null;
  evidence: string[];
}

export interface ExportToolchainProbe {
  probedAt: string;
  ffmpegVersion: string;
  /** Encoder presence and supported pixel formats, from the pinned
   * ffmpeg's own encoder help. */
  encoders: Record<string, { present: boolean; pixelFormats: string[] }>;
  profiles: Record<string, ProfileQualification>;
  /** The pinned Hyperframes CLI's documented render formats, captured
   * from `render --help`; null when no CLI binary was supplied. */
  hyperframesCli: { formats: string[]; transparencyDocumented: boolean } | null;
}

const PROBE_GEOMETRY = { size: 64, frames: 4, fps: 30 };

function encoderPixelFormats(encoder: string): { present: boolean; pixelFormats: string[] } {
  let text: string;
  try {
    text = runToolText("ffmpeg", ["-hide_banner", "-h", `encoder=${encoder}`]);
  } catch {
    return { present: false, pixelFormats: [] };
  }
  const formats: string[] = [];
  let inFormats = false;
  for (const line of text.split("\n")) {
    if (/Supported pixel formats:/.test(line)) {
      inFormats = true;
      formats.push(...line.split(":")[1].trim().split(/\s+/).filter(Boolean));
      continue;
    }
    if (inFormats) {
      if (/^\s{2,}\S/.test(line) && !/:/.test(line)) {
        formats.push(...line.trim().split(/\s+/).filter(Boolean));
      } else {
        inFormats = false;
      }
    }
  }
  return { present: text.includes("Encoder"), pixelFormats: formats };
}

/** Generate the probe's tiny analytic RGBA frames: a feathered disc
 * whose alpha ramps 255 to 0, so a binary-matte encode cannot pass. */
function generateProbeFrames(dir: string): string {
  mkdirSync(dir, { recursive: true });
  const s = PROBE_GEOMETRY.size;
  const expr =
    `geq=r='if(lt(hypot(X-32,Y-32),30),210,0)'` +
    `:g='if(lt(hypot(X-32,Y-32),30),80,0)'` +
    `:b='if(lt(hypot(X-32,Y-32),30),40,0)'` +
    `:a='clip((30-hypot(X-32,Y-32))/8,0,1)*255'`;
  runTool("ffmpeg", [
    "-v",
    "error",
    "-f",
    "lavfi",
    "-i",
    `nullsrc=s=${s}x${s}:r=${PROBE_GEOMETRY.fps}:d=${PROBE_GEOMETRY.frames / PROBE_GEOMETRY.fps},format=rgba,${expr}`,
    "-frames:v",
    String(PROBE_GEOMETRY.frames),
    join(dir, "f%03d.png"),
  ]);
  return join(dir, "f%03d.png");
}

function qualifyProfile(
  profileId: VideoProfileId,
  framesPattern: string,
  scratchDir: string
): ProfileQualification {
  const profile = EXPORT_PROFILES[profileId];
  const evidence: string[] = [];
  const outPath = join(scratchDir, `probe-${profileId}${profile.containerExtension}`);
  try {
    const { probe } = encodeFrameSequence({
      framesPattern,
      frameRate: PROBE_GEOMETRY.fps,
      profile,
      outPath,
    });
    evidence.push(
      `micro-roundtrip encoded ${PROBE_GEOMETRY.frames} analytic frames: stream codec ` +
        `${probe.codecName}, pixel format ${probe.pixelFormat}, frames ${probe.frameCount}.`
    );
    if (probe.codecName !== profile.streamCodec) {
      evidence.push(`codec mismatch: profile names ${profile.streamCodec}.`);
      return {
        profile: profileId,
        qualified: false,
        route: "image_sequence_encode",
        measuredCodec: probe.codecName,
        measuredPixelFormat: probe.pixelFormat,
        distinctAlphaValues: null,
        partialAlphaPixels: null,
        evidence,
      };
    }
    if (!profile.alpha) {
      const ok = !probe.alphaChannelPresent;
      evidence.push(ok ? "opaque stream confirmed (no alpha channel)." : "unexpected alpha channel.");
      return {
        profile: profileId,
        qualified: ok,
        route: "image_sequence_encode",
        measuredCodec: probe.codecName,
        measuredPixelFormat: probe.pixelFormat,
        distinctAlphaValues: null,
        partialAlphaPixels: null,
        evidence,
      };
    }
    const measurement = measureAlpha(outPath, probe, [0]);
    evidence.push(
      `decoded alpha: ${measurement.distinctAlphaValues} distinct values, ` +
        `${measurement.partialAlphaPixels} partial-alpha pixels of ${measurement.totalPixels}.`
    );
    const qualified =
      probe.alphaChannelPresent && measurement.partialAlphaPixels > 0 && measurement.distinctAlphaValues >= 8;
    return {
      profile: profileId,
      qualified,
      route: "image_sequence_encode",
      measuredCodec: probe.codecName,
      measuredPixelFormat: probe.pixelFormat,
      distinctAlphaValues: measurement.distinctAlphaValues,
      partialAlphaPixels: measurement.partialAlphaPixels,
      evidence,
    };
  } catch (err) {
    evidence.push(`encode failed: ${(err as Error).message}`);
    return {
      profile: profileId,
      qualified: false,
      route: "image_sequence_encode",
      measuredCodec: null,
      measuredPixelFormat: null,
      distinctAlphaValues: null,
      partialAlphaPixels: null,
      evidence,
    };
  }
}

/** Run the full toolchain probe in a scratch directory. Nothing here
 * reads or writes the shipped capability matrix; the probe is a
 * record, and selection (select.ts) decides what it confirms. */
export function probeExportToolchain(
  scratchDir: string,
  opts?: { hyperframesCliBin?: string }
): ExportToolchainProbe {
  rmSync(scratchDir, { recursive: true, force: true });
  mkdirSync(scratchDir, { recursive: true });
  const ffmpegVersion = runToolText("ffmpeg", ["-version"]).split("\n")[0].trim();
  const encoders: ExportToolchainProbe["encoders"] = {};
  for (const encoder of ["prores_ks", "libvpx-vp9", "libx264"]) {
    encoders[encoder] = encoderPixelFormats(encoder);
  }
  const framesPattern = generateProbeFrames(join(scratchDir, "frames"));
  const profiles: Record<string, ProfileQualification> = {};
  for (const profileId of Object.keys(EXPORT_PROFILES) as VideoProfileId[]) {
    profiles[profileId] = qualifyProfile(profileId, framesPattern, scratchDir);
  }
  let hyperframesCli: ExportToolchainProbe["hyperframesCli"] = null;
  if (opts?.hyperframesCliBin) {
    try {
      const help = runToolText(opts.hyperframesCliBin, ["render", "--help"]);
      const formatsLine = help.split("\n").find((l) => l.includes("--format"));
      const formats = ["mp4", "webm", "mov", "gif", "png-sequence", "hls"].filter((f) =>
        formatsLine ? formatsLine.includes(f) : help.includes(f)
      );
      hyperframesCli = {
        formats,
        transparencyDocumented: /transparency/i.test(help) && /ProRes 4444/.test(help),
      };
    } catch {
      hyperframesCli = null;
    }
  }
  return {
    probedAt: new Date().toISOString(),
    ffmpegVersion,
    encoders,
    profiles,
    hyperframesCli,
  };
}
