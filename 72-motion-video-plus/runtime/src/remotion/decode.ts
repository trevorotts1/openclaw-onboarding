// Decoded-frame measurement for the Remotion adapter's evidence
// (Directive MG-006, Section 17.1 M01/M04). Instrumented geometry alone
// is not proof: the adapter also decodes actual rendered output (PNG
// stills and frames extracted from the rendered MP4) and measures bar
// boundaries in the raster.
//
// Decoding uses the ffmpeg/ffprobe of the provisioned environment
// through checked argument arrays (never shell strings). PNG dimension
// checks parse the IHDR header directly.

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import type { C05Layout } from "./job-props";

export interface VideoProbe {
  width: number;
  height: number;
  /** Average frame rate as a rational pair, as ffprobe reports it. */
  fpsNumerator: number;
  fpsDenominator: number;
  /** Exact decoded frame count (ffprobe -count_frames). */
  frameCount: number;
  durationSeconds: number;
}

function runChecked(command: string, args: string[], maxBuffer = 96 * 1024 * 1024): Buffer {
  const result = spawnSync(command, args, { maxBuffer });
  if (result.error) {
    throw new Error(`${command} could not run: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const stderr = result.stderr ? result.stderr.toString("utf8").slice(-800) : "";
    throw new Error(`${command} exited ${result.status}: ${stderr}`);
  }
  return result.stdout;
}

/** Probe a rendered video: dimensions, exact frame count, frame rate,
 * and duration (M01 evidence). */
export function probeVideoFile(path: string): VideoProbe {
  const out = runChecked("ffprobe", [
    "-v",
    "error",
    "-count_frames",
    "-select_streams",
    "v:0",
    "-show_entries",
    "stream=width,height,avg_frame_rate,nb_read_frames",
    "-show_entries",
    "format=duration",
    "-of",
    "json",
    path,
  ]);
  const doc = JSON.parse(out.toString("utf8")) as {
    streams?: Array<{
      width?: number;
      height?: number;
      avg_frame_rate?: string;
      nb_read_frames?: string;
    }>;
    format?: { duration?: string };
  };
  const stream = doc.streams?.[0];
  if (!stream || typeof stream.width !== "number" || typeof stream.height !== "number") {
    throw new Error(`ffprobe found no video stream in ${path}`);
  }
  const [num, den] = (stream.avg_frame_rate ?? "0/1").split("/").map((s) => Number(s));
  return {
    width: stream.width,
    height: stream.height,
    fpsNumerator: num,
    fpsDenominator: den,
    frameCount: Number(stream.nb_read_frames ?? "0"),
    durationSeconds: Number(doc.format?.duration ?? "0"),
  };
}

/** Decode one frame (by zero-based decoded frame index for video, or
 * the image itself for a PNG) to raw RGB24 bytes. */
export function decodeFrameRgb(
  sourcePath: string,
  frameIndex: number | null,
  width: number,
  height: number
): Buffer {
  const args = ["-v", "error", "-i", sourcePath];
  if (frameIndex !== null) {
    args.push("-vf", `select='eq(n\\,${frameIndex})'`);
  }
  args.push("-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1");
  const buf = runChecked("ffmpeg", args, width * height * 3 + 1024 * 1024);
  if (buf.length < width * height * 3) {
    throw new Error(
      `decoded frame from ${sourcePath} has ${buf.length} bytes, expected ${width * height * 3}`
    );
  }
  return buf.subarray(0, width * height * 3);
}

/** Read a PNG's dimensions from its IHDR header and verify the PNG
 * signature. Returns null when the file is not a PNG. */
export function readPngDimensions(path: string): { width: number; height: number } | null {
  const buf = readFileSync(path);
  if (
    buf.length < 24 ||
    buf[0] !== 0x89 ||
    buf[1] !== 0x50 ||
    buf[2] !== 0x4e ||
    buf[3] !== 0x47
  ) {
    return null;
  }
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

function hexToRgb(hex: string): [number, number, number] {
  const m = /^#([0-9a-fA-F]{6})$/.exec(hex);
  if (!m) throw new Error(`not a #RRGGBB color: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/**
 * Measure bar widths in a decoded RGB frame: for each design row, scan
 * the bar's vertical center line from the plot's left edge and count the
 * contiguous run of pixels matching the accent color (per-channel
 * absolute difference sum within tolerance, which absorbs the single
 * antialiased edge pixel; the M04 decoded tolerance is 2 source pixels).
 */
export function measureAccentBarWidths(
  rgb: Buffer,
  frameWidth: number,
  layout: C05Layout,
  accentHex: string,
  channelToleranceSum = 66
): number[] {
  const [ar, ag, ab] = hexToRgb(accentHex);
  const widths: number[] = [];
  for (let row = 0; row < layout.row_y.length; row += 1) {
    const y = layout.row_y[row] + Math.floor(layout.bar_height / 2);
    let run = 0;
    for (let x = layout.plot.x; x < frameWidth; x += 1) {
      const off = (y * frameWidth + x) * 3;
      const dist =
        Math.abs(rgb[off] - ar) + Math.abs(rgb[off + 1] - ag) + Math.abs(rgb[off + 2] - ab);
      if (dist <= channelToleranceSum) run += 1;
      else break;
    }
    widths.push(run);
  }
  return widths;
}
