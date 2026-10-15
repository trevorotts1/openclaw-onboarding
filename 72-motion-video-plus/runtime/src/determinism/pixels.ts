// Decoded-pixel comparison for the determinism verifier (Directive
// MG-026). Every claim this module supports is made against decoded
// raster pixels, never against PNG file bytes: two PNG files may differ
// in metadata or encoding while decoding to identical pixels, and the
// reproducibility promise of MG-026 is about the pictures a viewer
// would see, not about container bytes. PNG stills are decoded to raw
// RGB24 through the system ffmpeg, the same decode path the MG-006
// measurement code uses (remotion/decode.ts), so a golden hash here is
// a hash of decoded pixels and nothing else.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { decodeFrameRgb, readPngDimensions } from "../remotion/decode";

export interface DecodedPixels {
  path: string;
  width: number;
  height: number;
  /** Raw RGB24 bytes, row-major, 3 bytes per pixel. */
  rgb: Buffer;
  /** sha256 of the decoded RGB bytes: the golden identity of a frame. */
  pixelSha256: string;
  /** sha256 of the PNG file bytes, recorded for provenance only. The
   * verifier never requires file bytes to match. */
  fileSha256: string;
}

export interface PixelComparison {
  width: number;
  height: number;
  totalPixels: number;
  /** Pixels where at least one of the three channels differs. */
  differingPixels: number;
  differingFraction: number;
  /** Largest absolute per-channel difference observed. */
  maxChannelDelta: number;
  /** Mean absolute per-channel difference across every channel of
   * every pixel. */
  meanAbsDelta: number;
  leftPixelSha256: string;
  rightPixelSha256: string;
  identical: boolean;
}

/** A comparison tolerance. The MG-026 doctrine (see
 * references/determinism-and-reproducibility.md) is exactness on the
 * pinned CPU render paths: EXACT_PIXELS is the default and a wider
 * tolerance is only ever introduced with a written justification and a
 * negative case proving a broken layout still fails. */
export interface PixelTolerance {
  maxDifferingPixels: number;
  maxChannelDelta: number;
}

export const EXACT_PIXELS: PixelTolerance = {
  maxDifferingPixels: 0,
  maxChannelDelta: 0,
};

export function sha256Bytes(bytes: Buffer | string): string {
  return createHash("sha256").update(bytes).digest("hex");
}

/** Decode a PNG still to raw pixels and hash the decoded bytes. */
export async function decodePngPixels(path: string): Promise<DecodedPixels> {
  const dims = readPngDimensions(path);
  if (!dims) {
    throw new Error(`Could not read PNG dimensions from ${path}; the file is missing or not a PNG.`);
  }
  const { width, height } = dims;
  const rgb = await decodeFrameRgb(path, null, width, height);
  const expected = width * height * 3;
  if (rgb.length !== expected) {
    throw new Error(
      `Decoded PNG ${path} produced ${rgb.length} RGB bytes, expected exactly ${expected} (${width}x${height}).`
    );
  }
  return {
    path,
    width,
    height,
    rgb,
    pixelSha256: sha256Bytes(rgb),
    fileSha256: sha256Bytes(readFileSync(path)),
  };
}

/** Full pixel statistics between two decoded frames of equal size. */
export function compareDecodedPixels(left: DecodedPixels, right: DecodedPixels): PixelComparison {
  if (left.width !== right.width || left.height !== right.height) {
    throw new Error(
      `Cannot compare decoded frames of different sizes: ${left.width}x${left.height} vs ${right.width}x${right.height}.`
    );
  }
  const totalPixels = left.width * left.height;
  let differingPixels = 0;
  let maxChannelDelta = 0;
  let absSum = 0;
  const a = left.rgb;
  const b = right.rgb;
  for (let i = 0; i < a.length; i += 3) {
    const dr = Math.abs(a[i] - b[i]);
    const dg = Math.abs(a[i + 1] - b[i + 1]);
    const db = Math.abs(a[i + 2] - b[i + 2]);
    if (dr !== 0 || dg !== 0 || db !== 0) {
      differingPixels += 1;
    }
    const m = Math.max(dr, dg, db);
    if (m > maxChannelDelta) maxChannelDelta = m;
    absSum += dr + dg + db;
  }
  return {
    width: left.width,
    height: left.height,
    totalPixels,
    differingPixels,
    differingFraction: totalPixels === 0 ? 0 : differingPixels / totalPixels,
    maxChannelDelta,
    meanAbsDelta: totalPixels === 0 ? 0 : absSum / (totalPixels * 3),
    leftPixelSha256: left.pixelSha256,
    rightPixelSha256: right.pixelSha256,
    identical: left.pixelSha256 === right.pixelSha256,
  };
}

export interface ToleranceVerdict {
  pass: boolean;
  reasons: string[];
}

/** Judge a comparison against a tolerance. Both conditions must hold;
 * a tolerance never excuses a single pixel moving by more than
 * maxChannelDelta, and never excuses more than maxDifferingPixels
 * moving at all. */
export function toleranceVerdict(cmp: PixelComparison, tolerance: PixelTolerance): ToleranceVerdict {
  const reasons: string[] = [];
  if (cmp.differingPixels > tolerance.maxDifferingPixels) {
    reasons.push(
      `${cmp.differingPixels} pixels differ, tolerance allows at most ${tolerance.maxDifferingPixels}.`
    );
  }
  if (cmp.maxChannelDelta > tolerance.maxChannelDelta) {
    reasons.push(
      `largest channel difference is ${cmp.maxChannelDelta}, tolerance allows at most ${tolerance.maxChannelDelta}.`
    );
  }
  return { pass: reasons.length === 0, reasons };
}
