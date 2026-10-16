// Single-pattern render harness for the determinism verifier
// (Directive MG-026). The parent test spawns this file as a child Node
// process so that frame access patterns are honest about process
// state:
//
// - cold: the parent spawns one child per frame, so every frame is
//   rendered by a fresh process that has never rendered anything,
//   with no warm adapter caches carried over from a previous frame.
// - forward, reverse, randomized: the parent spawns one child with
//   the whole frame list in pattern order, so any state the engine
//   accumulates while rendering earlier frames is present, in that
//   order, when later frames render. If a scene's pixels depend on
//   that history, the patterns disagree and the verifier catches it.
//
// Renders go through the shipped adapters only (RemotionAdapter and
// HyperframesAdapter); this harness adds no render path of its own.
// Each rendered still is copied to <out>/f<frame>.png and one JSON
// line per frame is printed on stdout for the parent.

import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { loadValidatedJob } from "../adapters";
import { HyperframesAdapter } from "../adapters/hyperframes";
import { createRemotionAdapter } from "../adapters/remotion";
import type { ValidatedMotionJob } from "../adapters/types";

interface Args {
  engine: "remotion" | "hyperframes";
  jobDir: string;
  frames: number[];
  outDir: string;
  rendersDir: string;
}

function parseArgs(argv: string[]): Args {
  const get = (flag: string): string => {
    const idx = argv.indexOf(flag);
    if (idx < 0 || idx + 1 >= argv.length) {
      throw new Error(`render-one: missing required argument ${flag}`);
    }
    return argv[idx + 1];
  };
  const engine = get("--engine");
  if (engine !== "remotion" && engine !== "hyperframes") {
    throw new Error(`render-one: unknown engine "${engine}"`);
  }
  const frames = get("--frames")
    .split(",")
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isFinite(n));
  if (frames.length === 0) {
    throw new Error("render-one: --frames must list at least one frame number");
  }
  return {
    engine,
    jobDir: get("--job"),
    frames,
    outDir: get("--out"),
    rendersDir: get("--renders"),
  };
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  mkdirSync(args.outDir, { recursive: true });
  mkdirSync(args.rendersDir, { recursive: true });

  if (args.engine === "remotion") {
    const adapter = createRemotionAdapter({ outputDir: args.rendersDir });
    const job = loadValidatedJob(args.jobDir);
    for (const frame of args.frames) {
      const result = await adapter.renderStill(job, frame);
      const dest = join(args.outDir, `f${frame}.png`);
      copyFileSync(result.outputPaths[0], dest);
      process.stdout.write(JSON.stringify({ frame, png: dest }) + "\n");
    }
    return;
  }

  const adapter = new HyperframesAdapter();
  const manifest = JSON.parse(readFileSync(join(args.jobDir, "manifest.json"), "utf8")) as {
    job_id: string;
  };
  const job: ValidatedMotionJob = {
    jobDir: args.jobDir,
    jobId: manifest.job_id,
    manifest: manifest as ValidatedMotionJob["manifest"],
  };
  for (const frame of args.frames) {
    const result = await adapter.renderStill(job, frame);
    // Hyperframes evidence paths are relative to the job directory.
    const dest = join(args.outDir, `f${frame}.png`);
    copyFileSync(join(args.jobDir, result.outputPaths[0]), dest);
    process.stdout.write(JSON.stringify({ frame, png: dest }) + "\n");
  }
}

main().catch((err: unknown) => {
  process.stderr.write(`render-one failed: ${(err as Error)?.stack ?? String(err)}\n`);
  process.exit(1);
});
