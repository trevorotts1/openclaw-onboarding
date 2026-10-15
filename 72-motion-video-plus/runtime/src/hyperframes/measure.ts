// Decoded-frame measurement for the Hyperframes adapter (MG-005).
//
// Inspection claims are made against decoded raster pixels, never
// against the DOM the generator authored (Directive M04, M10, M16).
// PNG frames are decoded to raw RGB through the system ffmpeg (a shared
// utility of the stack, Section 3.3) and measured here with plain byte
// arithmetic: bar widths along a scanline, and color fractions inside a
// box. Colors in generated compositions are flat fills, so a small
// channel-distance threshold separates subject pixels from antialiased
// edges; decoded-video frames get a wider threshold for codec noise.

import { spawn } from "node:child_process";

export interface DecodedImage {
  width: number;
  height: number;
  /** RGB bytes, row-major, 3 bytes per pixel. */
  rgb: Buffer;
}

/** Decode a PNG file to raw RGB pixels with ffmpeg. */
export async function decodePng(path: string, timeoutMs = 60000): Promise<DecodedImage> {
  const head = await readPngSize(path);
  const rgb = await new Promise<Buffer>((resolvePromise, rejectPromise) => {
    const child = spawn(
      "ffmpeg",
      ["-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
      { shell: false }
    );
    const chunks: Buffer[] = [];
    let stderr = "";
    const timer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        // Already exited.
      }
      rejectPromise(new Error(`ffmpeg decode of ${path} timed out after ${timeoutMs} ms`));
    }, timeoutMs);
    child.stdout.on("data", (d: Buffer) => chunks.push(d));
    child.stderr.on("data", (d: Buffer) => {
      stderr += d.toString("utf8");
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      rejectPromise(err);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        rejectPromise(new Error(`ffmpeg failed to decode ${path} (exit ${code}): ${stderr.slice(-400)}`));
        return;
      }
      resolvePromise(Buffer.concat(chunks));
    });
  });
  const expected = head.width * head.height * 3;
  if (rgb.length < expected) {
    throw new Error(`Decoded frame ${path} has ${rgb.length} bytes, expected at least ${expected}.`);
  }
  return { width: head.width, height: head.height, rgb };
}

async function readPngSize(path: string): Promise<{ width: number; height: number }> {
  const { readFile } = await import("node:fs/promises");
  const buf = await readFile(path);
  if (buf.length < 24 || buf[0] !== 0x89 || buf[1] !== 0x50 || buf[2] !== 0x4e || buf[3] !== 0x47) {
    throw new Error(`File ${path} is not a PNG.`);
  }
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

export function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!m) throw new Error(`Not a hex color: ${hex}`);
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 0xff, g: (n >> 8) & 0xff, b: n & 0xff };
}

function channelDistance(
  img: DecodedImage,
  x: number,
  y: number,
  target: { r: number; g: number; b: number }
): number {
  const i = (y * img.width + x) * 3;
  return Math.max(
    Math.abs(img.rgb[i] - target.r),
    Math.abs(img.rgb[i + 1] - target.g),
    Math.abs(img.rgb[i + 2] - target.b)
  );
}

/** True when the pixel at (x, y) matches the target color within the
 * per-channel threshold. */
export function pixelMatches(
  img: DecodedImage,
  x: number,
  y: number,
  hex: string,
  threshold = 40
): boolean {
  return channelDistance(img, x, y, hexToRgb(hex)) <= threshold;
}

/**
 * Measure a horizontal bar's width on one scanline: the count of
 * consecutive subject-colored pixels starting at the bar's origin x.
 * Flat fills make the run exact except at the antialiased end edge,
 * which the threshold excludes (Directive M04 decoded tolerance).
 */
export function measureBarWidth(
  img: DecodedImage,
  originX: number,
  y: number,
  maxWidth: number,
  hex: string,
  threshold = 40
): number {
  let width = 0;
  while (width < maxWidth && originX + width < img.width) {
    if (!pixelMatches(img, originX + width, y, hex, threshold)) break;
    width += 1;
  }
  return width;
}

/** Fraction of pixels inside a box that match the target color. */
export function measureColorFraction(
  img: DecodedImage,
  box: { x: number; y: number; width: number; height: number },
  hex: string,
  threshold = 40
): number {
  let match = 0;
  let total = 0;
  for (let y = box.y; y < box.y + box.height && y < img.height; y += 1) {
    for (let x = box.x; x < box.x + box.width && x < img.width; x += 1) {
      total += 1;
      if (pixelMatches(img, x, y, hex, threshold)) match += 1;
    }
  }
  return total === 0 ? 0 : match / total;
}

/**
 * The best-matching declared color for a box: returns the segment whose
 * color has the highest pixel fraction inside the box. Used to prove
 * framework-owned media timing: at a known composition time, the box
 * must be dominated by the segment the media clock selects.
 */
export function dominantColor(
  img: DecodedImage,
  box: { x: number; y: number; width: number; height: number },
  hexes: string[],
  threshold = 64
): { color: string; fraction: number } {
  let best = { color: hexes[0] ?? "", fraction: -1 };
  for (const hex of hexes) {
    const fraction = measureColorFraction(img, box, hex, threshold);
    if (fraction > best.fraction) best = { color: hex, fraction };
  }
  return best;
}
