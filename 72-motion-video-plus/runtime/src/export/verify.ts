// Measured truth for export artifacts (MG-040): ffprobe stream facts,
// decoded alpha statistics, and background composites. Nothing in the
// export layer asserts transparency; this module measures it.
//
// Decoder note (probed on this machine, ffmpeg 8.1.2): a VP9 stream
// carrying alpha in a WebM reports pixel format yuv420p and carries
// the stream tag alpha_mode=1; the native decoder drops the alpha,
// and only the libvpx-vp9 decoder returns it. Decoding here therefore
// selects the decoder from the probed codec, never from the file
// extension.

import { runTool } from "./ffmpeg";

export interface DetailedVideoProbe {
  codecName: string;
  pixelFormat: string;
  width: number;
  height: number;
  /** Exact decoded frame count (ffprobe -count_frames). */
  frameCount: number;
  fpsNumerator: number;
  fpsDenominator: number;
  durationSeconds: number;
  /** The WebM alpha_mode stream tag ("1" when alpha is carried). */
  alphaModeTag: string | null;
  /** True when the stream carries an alpha channel: an alpha pixel
   * format, or the VP9 alpha_mode tag. */
  alphaChannelPresent: boolean;
}

export function probeVideoDetailed(path: string): DetailedVideoProbe {
  const out = runTool("ffprobe", [
    "-v",
    "error",
    "-count_frames",
    "-select_streams",
    "v:0",
    "-show_entries",
    "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_read_frames",
    "-show_entries",
    "stream_tags",
    "-show_entries",
    "format=duration",
    "-of",
    "json",
    path,
  ]);
  const doc = JSON.parse(out.toString("utf8")) as {
    streams?: Array<{
      codec_name?: string;
      pix_fmt?: string;
      width?: number;
      height?: number;
      avg_frame_rate?: string;
      nb_read_frames?: string;
      tags?: Record<string, string>;
    }>;
    format?: { duration?: string };
  };
  const stream = doc.streams?.[0];
  if (!stream || typeof stream.width !== "number" || typeof stream.height !== "number") {
    throw new Error(`ffprobe found no video stream in ${path}`);
  }
  const pixelFormat = stream.pix_fmt ?? "unknown";
  // The WebM alpha tag's case depends on which muxer wrote the file
  // (ALPHA_MODE from ffmpeg's matroska muxer, alpha_mode elsewhere);
  // match it case-insensitively or real VP9 alpha reads as absent.
  let alphaModeTag: string | null = null;
  for (const [key, value] of Object.entries(stream.tags ?? {})) {
    if (key.toLowerCase() === "alpha_mode") alphaModeTag = value;
  }
  const [num, den] = (stream.avg_frame_rate ?? "0/1").split("/").map((s) => Number(s));
  return {
    codecName: stream.codec_name ?? "unknown",
    pixelFormat,
    width: stream.width,
    height: stream.height,
    frameCount: Number(stream.nb_read_frames ?? "0"),
    fpsNumerator: num,
    fpsDenominator: den,
    durationSeconds: Number(doc.format?.duration ?? "0"),
    alphaModeTag,
    alphaChannelPresent:
      pixelFormat.startsWith("yuva") ||
      pixelFormat.startsWith("gbrap") ||
      pixelFormat.includes("rgba") ||
      pixelFormat.includes("argb") ||
      pixelFormat.includes("bgra") ||
      alphaModeTag === "1",
  };
}

/** Decode one frame to raw RGBA bytes, selecting the alpha-capable
 * decoder for VP9 as documented above. */
export function decodeFrameRgba(
  path: string,
  frameIndex: number,
  probe: DetailedVideoProbe
): Buffer {
  const args: string[] = ["-v", "error"];
  if (probe.codecName === "vp9") args.push("-c:v", "libvpx-vp9");
  args.push(
    "-i",
    path,
    "-vf",
    `select='eq(n\\,${frameIndex})'`,
    "-frames:v",
    "1",
    "-f",
    "rawvideo",
    "-pix_fmt",
    "rgba",
    "pipe:1"
  );
  const expected = probe.width * probe.height * 4;
  const buf = runTool("ffmpeg", args, expected + 1024 * 1024);
  if (buf.length < expected) {
    throw new Error(
      `decoded frame ${frameIndex} from ${path} has ${buf.length} bytes, expected ${expected}`
    );
  }
  return buf.subarray(0, expected);
}

export interface AlphaMeasurement {
  /** Frames whose alpha plane was measured. */
  framesMeasured: number[];
  minAlpha: number;
  maxAlpha: number;
  /** Count of distinct alpha values across the measured frames. A
   * binary matte has at most 2; a genuinely feathered edge has many. */
  distinctAlphaValues: number;
  /** Pixels with 0 < alpha < 255 (real partial alpha). */
  partialAlphaPixels: number;
  transparentPixels: number;
  opaquePixels: number;
  totalPixels: number;
}

/** Measure the alpha plane of the given frames. When the stream has
 * no alpha channel the decoded RGBA alpha is uniformly 255 by
 * construction, so callers must gate on probe.alphaChannelPresent;
 * this function measures what decodes either way and reports the
 * channel flag it was given. */
export function measureAlpha(
  path: string,
  probe: DetailedVideoProbe,
  frameIndices: number[]
): AlphaMeasurement {
  const distinct = new Set<number>();
  let minAlpha = 255;
  let maxAlpha = 0;
  let partial = 0;
  let transparent = 0;
  let opaque = 0;
  let total = 0;
  for (const frameIndex of frameIndices) {
    const rgba = decodeFrameRgba(path, frameIndex, probe);
    for (let off = 3; off < rgba.length; off += 4) {
      const a = rgba[off];
      distinct.add(a);
      if (a < minAlpha) minAlpha = a;
      if (a > maxAlpha) maxAlpha = a;
      if (a === 0) transparent += 1;
      else if (a === 255) opaque += 1;
      else partial += 1;
      total += 1;
    }
  }
  return {
    framesMeasured: frameIndices,
    minAlpha: total > 0 ? minAlpha : 0,
    maxAlpha,
    distinctAlphaValues: distinct.size,
    partialAlphaPixels: partial,
    transparentPixels: transparent,
    opaquePixels: opaque,
    totalPixels: total,
  };
}

/** The three honest alpha verdicts. "verified_alpha" requires a
 * channel AND measured partial alpha with many distinct values;
 * "alpha_opaque_content" is a real channel whose content is uniformly
 * opaque; "opaque" is no channel at all. */
export type AlphaVerdict = "verified_alpha" | "alpha_opaque_content" | "opaque";

export function verdictFromMeasurement(
  probe: DetailedVideoProbe,
  measurement: AlphaMeasurement
): AlphaVerdict {
  if (!probe.alphaChannelPresent) return "opaque";
  if (measurement.partialAlphaPixels > 0 && measurement.distinctAlphaValues >= 8) {
    return "verified_alpha";
  }
  return "alpha_opaque_content";
}

/** Composite one decoded frame over a solid background and return raw
 * RGB24 bytes. The composite runs through ffmpeg's overlay in the
 * same decode pipeline a consumer would use, so a matte baked into
 * the stream shows up here exactly as it would on screen. */
export function compositeFrameOver(
  path: string,
  frameIndex: number,
  probe: DetailedVideoProbe,
  background: [number, number, number]
): Buffer {
  const hex = background.map((v) => v.toString(16).padStart(2, "0")).join("");
  const args: string[] = [
    "-v",
    "error",
    "-f",
    "lavfi",
    "-i",
    `color=c=0x${hex}:s=${probe.width}x${probe.height}`,
  ];
  // The decoder option binds to the input that follows it: the video
  // file, not the lavfi background.
  if (probe.codecName === "vp9") args.push("-c:v", "libvpx-vp9");
  args.push(
    "-i",
    path,
    "-filter_complex",
    `[1:v]trim=start_frame=${frameIndex}:end_frame=${frameIndex + 1},setpts=PTS-STARTPTS,format=rgba[fg];` +
      `[0:v][fg]overlay=0:0:format=rgb,format=rgb24[out]`,
    "-map",
    "[out]",
    "-frames:v",
    "1",
    "-f",
    "rawvideo",
    "-pix_fmt",
    "rgb24",
    "pipe:1"
  );
  const expected = probe.width * probe.height * 3;
  const buf = runTool("ffmpeg", args, expected + 1024 * 1024);
  if (buf.length < expected) {
    throw new Error(
      `composite of frame ${frameIndex} from ${path} has ${buf.length} bytes, expected ${expected}`
    );
  }
  return buf.subarray(0, expected);
}

/** One pixel of a raw buffer with the given channel count. */
export function samplePixel(
  buf: Buffer,
  width: number,
  x: number,
  y: number,
  channels: number
): number[] {
  const off = (y * width + x) * channels;
  const out: number[] = [];
  for (let c = 0; c < channels; c += 1) out.push(buf[off + c]);
  return out;
}

/** Mean channel values over a square patch of a raw RGBA buffer. */
export function patchMeanRgba(
  buf: Buffer,
  width: number,
  cx: number,
  cy: number,
  radius: number
): [number, number, number, number] {
  const sums = [0, 0, 0, 0];
  let n = 0;
  for (let y = cy - radius; y <= cy + radius; y += 1) {
    for (let x = cx - radius; x <= cx + radius; x += 1) {
      const off = (y * width + x) * 4;
      for (let c = 0; c < 4; c += 1) sums[c] += buf[off + c];
      n += 1;
    }
  }
  return [sums[0] / n, sums[1] / n, sums[2] / n, sums[3] / n];
}

/** Per-channel mean absolute error between two same-sized raw buffers
 * over a rectangle. */
export function regionMae(
  a: Buffer,
  b: Buffer,
  width: number,
  channels: number,
  region: { x0: number; x1: number; y0: number; y1: number }
): number[] {
  const totals = new Array<number>(channels).fill(0);
  let n = 0;
  for (let y = region.y0; y < region.y1; y += 1) {
    for (let x = region.x0; x < region.x1; x += 1) {
      const off = (y * width + x) * channels;
      for (let c = 0; c < channels; c += 1) totals[c] += Math.abs(a[off + c] - b[off + c]);
      n += 1;
    }
  }
  return totals.map((t) => t / n);
}
