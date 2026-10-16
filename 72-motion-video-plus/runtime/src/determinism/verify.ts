// Orchestration for the determinism verifier (Directive MG-026):
// job staging, frozen-input hashing, and access-pattern execution.
//
// Inputs are frozen before any pattern runs: the verifier renders
// only the shipped fixture jobs (copied into scratch, never edited in
// place), and records a sha256 of every job file in the evidence
// record, so a golden result names the exact input revision that
// produced it. The one deliberate exception is the negative-case job,
// whose design file is shifted by a recorded amount; its input hash
// therefore differs from the golden job's, which is the point.

import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

/** The C05 proof frames from Directive Section 17.2, covering the
 * categories MG-026 names: opening (0), transition start (15),
 * transition midpoint and proof (45), proof and final state (75),
 * hold (150), and the final frame (179). */
export const C05_PROOF_FRAMES = [0, 15, 45, 75, 150, 179];

export type AccessPattern = "cold" | "forward" | "reverse" | "randomized";

export const ACCESS_PATTERNS: AccessPattern[] = ["cold", "forward", "reverse", "randomized"];

/** Frame order for a pattern. The randomized order comes from the
 * seeded generator (prng.ts) so the pattern itself is reproducible. */
export function patternOrder(
  pattern: AccessPattern,
  frames: readonly number[],
  seeded: (items: readonly number[]) => number[]
): number[] {
  switch (pattern) {
    case "cold":
    case "forward":
      return [...frames];
    case "reverse":
      return [...frames].reverse();
    case "randomized":
      return seeded(frames);
  }
}

function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function collectFiles(dir: string, base: string, out: string[]): void {
  for (const name of readdirSync(dir).sort()) {
    const abs = join(dir, name);
    if (statSync(abs).isDirectory()) {
      collectFiles(abs, base, out);
    } else {
      out.push(relative(base, abs));
    }
  }
}

/** sha256 of every file in a job directory, keyed by job relative
 * path. This is the frozen-input record stored with the goldens. */
export function hashJobInputs(jobDir: string): Record<string, string> {
  const rels: string[] = [];
  collectFiles(jobDir, jobDir, rels);
  const out: Record<string, string> = {};
  for (const rel of rels.sort()) {
    out[rel] = sha256File(join(jobDir, rel));
  }
  return out;
}

export interface InputHashDiff {
  /** Input files whose bytes changed during rendering. */
  changed: string[];
  /** Input files that disappeared during rendering. */
  removed: string[];
  /** Files that appeared during rendering under a `renders/` output
   * subtree. The Hyperframes adapter writes its snapshot evidence
   * into the job directory's renders area; those are render outputs,
   * not inputs, and enumerating them separately is what keeps the
   * frozen-input check precise instead of falsely accusing them. */
  addedOutputs: string[];
  /** Files that appeared during rendering anywhere else. A non-empty
   * list means something wrote into the job's input space. */
  addedOther: string[];
}

/** Compare a job's frozen-input hashes before and after rendering.
 * Inputs are frozen iff nothing changed and nothing was removed; new
 * files are legitimate only as adapter render outputs under
 * `renders/`. */
export function diffInputHashes(
  before: Record<string, string>,
  after: Record<string, string>
): InputHashDiff {
  const changed: string[] = [];
  const removed: string[] = [];
  const addedOutputs: string[] = [];
  const addedOther: string[] = [];
  for (const rel of Object.keys(before)) {
    if (!(rel in after)) {
      removed.push(rel);
    } else if (after[rel] !== before[rel]) {
      changed.push(rel);
    }
  }
  for (const rel of Object.keys(after)) {
    if (rel in before) continue;
    if (rel.startsWith("renders/")) {
      addedOutputs.push(rel);
    } else {
      addedOther.push(rel);
    }
  }
  return {
    changed: changed.sort(),
    removed: removed.sort(),
    addedOutputs: addedOutputs.sort(),
    addedOther: addedOther.sort(),
  };
}

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

function writeJson(path: string, value: unknown): void {
  writeFileSync(path, JSON.stringify(value, null, 2) + "\n", "utf8");
}

/** Copy the shipped C05 fixture job into scratch and retarget it to
 * Hyperframes, the same construction the MG-005 suite uses: scene
 * engine and manifest default engine become "hyperframes" and
 * everything else is byte identical, so both engines render the same
 * logical scene. */
export function stageHyperframesC05Job(fixtureJobDir: string, destDir: string): string {
  cpSync(fixtureJobDir, destDir, { recursive: true });
  const scenePath = join(destDir, "scenes", "bar-01.json");
  const scene = readJson(scenePath);
  scene.engine = "hyperframes";
  writeJson(scenePath, scene);
  const manifestPath = join(destDir, "manifest.json");
  const manifest = readJson(manifestPath) as { rendering: Record<string, unknown> };
  manifest.rendering.default_engine = "hyperframes";
  writeJson(manifestPath, manifest);
  return destDir;
}

/** Copy the shipped C05 fixture job into scratch and shift the plot
 * origin by shiftPx. This is the broken-layout negative case: every
 * bar moves by a clearly visible amount while the dataset, copy, and
 * design otherwise stay identical, so any verifier tolerance that
 * passes this frame is wide enough to pass a broken layout. */
export function stageShiftedC05Job(fixtureJobDir: string, destDir: string, shiftPx: number): string {
  cpSync(fixtureJobDir, destDir, { recursive: true });
  const designPath = join(destDir, "design.json");
  const design = readJson(designPath) as {
    layouts: Record<string, { plot: { x: number } }>;
  };
  design.layouts.landscape.plot.x += shiftPx;
  writeJson(designPath, design);
  return destDir;
}

export interface PatternRunResult {
  pattern: AccessPattern;
  /** Frame number to rendered PNG path (copied out of the engine's
   * own render directory by the child harness). */
  pngByFrame: Map<number, string>;
  /** The exact order frames were requested in. */
  requestedOrder: number[];
}

interface RenderOneOptions {
  engine: "remotion" | "hyperframes";
  jobDir: string;
  framesInOrder: number[];
  outDir: string;
  rendersDir: string;
  tmpDir: string;
  timeoutMs: number;
}

function runRenderOne(opts: RenderOneOptions): Promise<Map<number, string>> {
  const childPath = join(__dirname, "render-one.js");
  const args = [
    childPath,
    "--engine",
    opts.engine,
    "--job",
    opts.jobDir,
    "--frames",
    opts.framesInOrder.join(","),
    "--out",
    opts.outDir,
    "--renders",
    opts.rendersDir,
  ];
  return new Promise((resolvePromise, rejectPromise) => {
    execFile(
      process.execPath,
      args,
      {
        env: { ...process.env, TMPDIR: opts.tmpDir },
        timeout: opts.timeoutMs,
        maxBuffer: 64 * 1024 * 1024,
      },
      (err, stdout, stderr) => {
        if (err) {
          rejectPromise(
            new Error(
              `render-one (${opts.engine}, frames ${opts.framesInOrder.join(",")}) failed: ${err.message}\n${stderr.slice(-2000)}`
            )
          );
          return;
        }
        const map = new Map<number, string>();
        for (const line of stdout.split("\n")) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("{")) continue;
          const parsed = JSON.parse(trimmed) as { frame: number; png: string };
          map.set(parsed.frame, parsed.png);
        }
        for (const frame of opts.framesInOrder) {
          if (!map.has(frame)) {
            rejectPromise(
              new Error(
                `render-one (${opts.engine}) did not report frame ${frame}. stdout tail: ${stdout.slice(-500)}`
              )
            );
            return;
          }
        }
        resolvePromise(map);
      }
    );
  });
}

/** Execute one access pattern for one engine.
 *
 * Cold runs spawn one fresh child process per frame. The other
 * patterns spawn one child for the whole list, in pattern order, so
 * warm in-process engine state is exercised exactly the way a real
 * batch render would exercise it. */
export async function runAccessPattern(opts: {
  engine: "remotion" | "hyperframes";
  jobDir: string;
  pattern: AccessPattern;
  frames: readonly number[];
  order: number[];
  scratchDir: string;
  tmpDir: string;
  timeoutPerProcessMs: number;
}): Promise<PatternRunResult> {
  const outDir = join(opts.scratchDir, "patterns", opts.engine, opts.pattern);
  const rendersDir = join(opts.scratchDir, "renders", opts.engine, opts.pattern);
  mkdirSync(outDir, { recursive: true });
  mkdirSync(rendersDir, { recursive: true });
  const pngByFrame = new Map<number, string>();
  if (opts.pattern === "cold") {
    for (const frame of opts.order) {
      const one = await runRenderOne({
        engine: opts.engine,
        jobDir: opts.jobDir,
        framesInOrder: [frame],
        outDir,
        rendersDir,
        tmpDir: opts.tmpDir,
        timeoutMs: opts.timeoutPerProcessMs,
      });
      for (const [f, p] of one) pngByFrame.set(f, p);
    }
  } else {
    const all = await runRenderOne({
      engine: opts.engine,
      jobDir: opts.jobDir,
      framesInOrder: opts.order,
      outDir,
      rendersDir,
      tmpDir: opts.tmpDir,
      timeoutMs: opts.timeoutPerProcessMs,
    });
    for (const [f, p] of all) pngByFrame.set(f, p);
  }
  return { pattern: opts.pattern, pngByFrame, requestedOrder: opts.order };
}
