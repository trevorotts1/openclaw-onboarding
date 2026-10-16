// The image-sequence encode executor (MG-040): PNG frames in, one
// qualified encode out. This is the route that exists for every
// profile, including where an engine has no native alpha render
// wired. Encoders only ever consume the PNG mezzanine (or frames
// decoded back to PNG under the intermediate policy); a delivery
// encode is never fed another delivery encode by this layer.

import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { runTool } from "./ffmpeg";
import { ExportError, type ExportProfile } from "./profiles";
import { probeVideoDetailed, type DetailedVideoProbe } from "./verify";

export interface EncodeResult {
  outPath: string;
  probe: DetailedVideoProbe;
}

/** Encode a PNG frame sequence (printf pattern, for example
 * "frames/f%03d.png") with the given ffmpeg codec arguments. A failed
 * encode is MG_ENCODE_FAILED (Section 16.9 exit class 5), never a
 * partial artifact. */
export function encodeFrameSequenceWithArgs(opts: {
  framesPattern: string;
  frameRate: number;
  codecArgs: string[];
  outPath: string;
}): EncodeResult {
  mkdirSync(dirname(opts.outPath), { recursive: true });
  const args = [
    "-v",
    "error",
    "-framerate",
    String(opts.frameRate),
    "-i",
    opts.framesPattern,
    ...opts.codecArgs,
    "-an",
    "-y",
    opts.outPath,
  ];
  try {
    runTool("ffmpeg", args);
  } catch (err) {
    throw new ExportError({
      category: "MG_ENCODE_FAILED",
      check: "export.encode_ran",
      message: `Encoding ${opts.outPath} from ${opts.framesPattern} failed: ${(err as Error).message}`,
    });
  }
  return { outPath: opts.outPath, probe: probeVideoDetailed(opts.outPath) };
}

/** Encode a PNG frame sequence at a profile's delivery settings. */
export function encodeFrameSequence(opts: {
  framesPattern: string;
  frameRate: number;
  profile: ExportProfile;
  outPath: string;
}): EncodeResult {
  if (!opts.profile.sequenceEncoder) {
    throw new ExportError({
      category: "MG_CAPABILITY_UNSUPPORTED",
      check: "export.sequence_encode_qualified",
      message: `Profile ${opts.profile.id} has no qualified image-sequence encode.`,
    });
  }
  return encodeFrameSequenceWithArgs({
    framesPattern: opts.framesPattern,
    frameRate: opts.frameRate,
    codecArgs: opts.profile.sequenceEncodeArgs,
    outPath: opts.outPath,
  });
}

/** Decode a video back to a PNG frame sequence (the mezzanine form).
 * Used between generations under the intermediate policy; VP9 alpha
 * is decoded through libvpx for the reason verify.ts documents. */
export function decodeVideoToFrames(opts: {
  videoPath: string;
  codecName: string;
  framesPattern: string;
}): void {
  mkdirSync(dirname(opts.framesPattern), { recursive: true });
  const args: string[] = ["-v", "error"];
  if (opts.codecName === "vp9") args.push("-c:v", "libvpx-vp9");
  args.push("-i", opts.videoPath, "-vf", "format=rgba", "-y", opts.framesPattern);
  try {
    runTool("ffmpeg", args);
  } catch (err) {
    throw new ExportError({
      category: "MG_ENCODE_FAILED",
      check: "export.decode_ran",
      message: `Decoding ${opts.videoPath} to frames failed: ${(err as Error).message}`,
    });
  }
}
