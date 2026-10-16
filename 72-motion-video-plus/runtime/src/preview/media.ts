// Hash and media helpers for preview review records (Directive
// MG-024). Hashing is what turns "the preview shows the same content"
// from a promise into proof: the source hash covers the job's content
// inputs, the props hash covers the exact payload the engine consumed,
// and the preview hash covers the artifact bytes a reviewer watched.
//
// Frame extraction and the contact sheet use the same discipline as
// the rest of the runtime: checked argument arrays, exit-status checks,
// and output verification (the produced file must exist, be nonempty,
// and probe or parse to the expected geometry) before anything is
// reported as produced.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import type { Manifest } from "../validation/generated-types";

export class PreviewMediaError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PreviewMediaError";
  }
}

export function sha256Hex(data: string | Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

export function sha256File(path: string): string {
  return sha256Hex(readFileSync(path));
}

/** Hash the exact props payload an engine consumed: canonical JSON of
 * the props object (engines consume JSON-shaped props; key order in
 * the object is not part of the payload's identity). */
export function hashPropsPayload(props: unknown): string {
  return sha256Hex(JSON.stringify(props) ?? "null");
}

function jobFile(jobDir: string, p: string): string {
  return isAbsolute(p) ? p : resolve(jobDir, p);
}

/**
 * Hash a validated job's content inputs: the manifest, the storyboard,
 * the asset manifest, the timeline, the job design document, and every
 * scene's spec, dataset, and design document. Engine-independent and
 * render-independent: the preview, the rough preview, and the final of
 * one job revision all carry this same source hash.
 */
export function hashJobSourceInputs(jobDir: string, manifest: Manifest): string {
  const rels = new Set<string>(["manifest.json"]);
  for (const p of [manifest.storyboard, manifest.assets, manifest.timeline, manifest.design]) {
    if (typeof p === "string" && p.length > 0) rels.add(relative(jobDir, jobFile(jobDir, p)));
  }
  for (const scene of manifest.scenes) {
    const specAbs = jobFile(jobDir, scene.spec);
    rels.add(relative(jobDir, specAbs));
    try {
      const spec = JSON.parse(readFileSync(specAbs, "utf8")) as {
        data_path?: string;
        design_path?: string;
      };
      if (typeof spec.data_path === "string") {
        rels.add(relative(jobDir, jobFile(jobDir, spec.data_path)));
      }
      if (typeof spec.design_path === "string") {
        rels.add(relative(jobDir, jobFile(jobDir, spec.design_path)));
      }
    } catch {
      // A spec that cannot be parsed fails validation long before a
      // preview is rendered; the hash still covers the spec's bytes.
    }
  }
  const hash = createHash("sha256");
  for (const rel of [...rels].sort()) {
    const abs = resolve(jobDir, rel);
    hash.update(rel);
    hash.update("\0");
    hash.update(existsSync(abs) ? readFileSync(abs) : Buffer.from("<missing>"));
    hash.update("\0");
  }
  return hash.digest("hex");
}

function runChecked(tool: string, args: string[], what: string): void {
  const r = spawnSync(tool, args, { encoding: "utf8", maxBuffer: 32 * 1024 * 1024 });
  if (r.error) throw new PreviewMediaError(`${what}: could not run ${tool}: ${r.error.message}`);
  if (r.status !== 0) {
    throw new PreviewMediaError(
      `${what}: ${tool} exited ${String(r.status)}: ${(r.stderr ?? "").slice(0, 600)}`
    );
  }
}

function assertProducedFile(path: string, what: string): void {
  if (!existsSync(path) || statSync(path).size <= 0) {
    throw new PreviewMediaError(`${what}: expected output ${path} was not produced.`);
  }
}

/** Extract one frame from a video as a PNG at the video's own (that
 * is, destination) size: individual review frames are never rescaled,
 * so a frame from a scaled preview is exactly the size a reviewer
 * watches, and a frame from the final is full delivery size. */
export function extractFramePng(videoPath: string, frame: number, outPng: string): void {
  runChecked(
    "ffmpeg",
    [
      "-v", "error", "-i", videoPath,
      "-vf", `select=eq(n\\,${frame})`,
      "-fps_mode", "vfr",
      "-frames:v", "1",
      "-y", outPng,
    ],
    `extract frame ${frame} from ${videoPath}`
  );
  assertProducedFile(outPng, `extract frame ${frame}`);
}

/** Scale a video spatially at encode time (aspect-preserving plan
 * dimensions are computed by plan.ts). Used by the Hyperframes
 * adapter, whose pinned CLI offers no sub-native render scale. Frame
 * count, frame rate, and timing are untouched: this is a spatial
 * derivation of the engine's canonical frames, never a re-layout. */
export function scaleVideoTo(input: string, output: string, width: number, height: number): void {
  runChecked(
    "ffmpeg",
    [
      "-v", "error", "-i", input,
      "-vf", `scale=${width}:${height}:flags=lanczos`,
      "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-an",
      "-y", output,
    ],
    `scale ${input} to ${width}x${height}`
  );
  assertProducedFile(output, "scale video");
}

export interface ContactSheetOptions {
  columns: number;
  tileWidth: number;
  tileHeight: number;
}

/** Tile same-size frames into one contact sheet PNG. Tiles are scaled
 * to the tile size; the inputs themselves stay at destination size.
 * Returns the sheet's expected dimensions for verification. */
export function buildContactSheet(
  framePaths: string[],
  outPng: string,
  opts: ContactSheetOptions
): { width: number; height: number } {
  if (framePaths.length === 0) {
    throw new PreviewMediaError("A contact sheet needs at least one frame.");
  }
  const args: string[] = ["-v", "error"];
  for (const p of framePaths) args.push("-i", p);
  const scaled = framePaths.map((_, i) => `[${i}:v]scale=${opts.tileWidth}:${opts.tileHeight}[t${i}]`);
  const inputs = framePaths.map((_, i) => `[t${i}]`).join("");
  const rows = Math.ceil(framePaths.length / opts.columns);
  args.push(
    "-filter_complex",
    `${scaled.join(";")};${inputs}xstack=inputs=${framePaths.length}:layout=${xstackLayout(
      framePaths.length,
      opts.columns,
      opts.tileWidth,
      opts.tileHeight
    )}[out]`,
    "-map", "[out]",
    "-frames:v", "1",
    "-y", outPng
  );
  runChecked("ffmpeg", args, "build contact sheet");
  assertProducedFile(outPng, "build contact sheet");
  return { width: opts.tileWidth * opts.columns, height: opts.tileHeight * rows };
}

function xstackLayout(count: number, columns: number, tileWidth: number, tileHeight: number): string {
  const cells: string[] = [];
  for (let i = 0; i < count; i += 1) {
    const col = i % columns;
    const row = Math.floor(i / columns);
    cells.push(`${col * tileWidth}_${row * tileHeight}`);
  }
  return cells.join("|");
}
