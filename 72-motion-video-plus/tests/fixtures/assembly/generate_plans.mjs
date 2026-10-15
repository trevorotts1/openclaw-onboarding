// MG-022 fixture plan generator.
//
// Builds the assembly fixture plans with the REAL MG-021 timeline
// compiler (runtime/src/timeline), never by hand, so the fixtures
// assemble against exactly the documents the production compiler
// emits. Input: specs/*.json (the single source of truth shared with
// make_media.py). Output: plans/<id>.json = {timeline, sidecar}.
//
// Run after building the runtime (npm ci && npm run build):
//   node tests/fixtures/assembly/generate_plans.mjs

import { readFileSync, writeFileSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const here = dirname(fileURLToPath(import.meta.url));
const runtimeDist = join(here, "..", "..", "..", "runtime", "dist", "src", "timeline", "index.js");
const require = createRequire(import.meta.url);
const { compileTimeline } = require(runtimeDist);

const specDir = join(here, "specs");
const planDir = join(here, "plans");
mkdirSync(planDir, { recursive: true });

for (const name of readdirSync(specDir).filter((n) => n.endsWith(".json")).sort()) {
  const spec = JSON.parse(readFileSync(join(specDir, name), "utf8"));
  const hasAudio = spec.narration.length > 0 || spec.sfx.length > 0 || spec.music;
  const input = {
    jobId: "mg022-" + spec.id,
    fps: spec.fps,
    mode: "program",
    // A spec may pin the owner explicitly (MG-023's inherited-mode
    // fixture carries a music bed in its package while the parent
    // owns the audio); otherwise ownership follows audio presence.
    audioOwner: spec.audioOwner || (hasAudio ? "self" : "none"),
    scenes: spec.scenes.map((s) => {
      const scene = { id: s.id, durationFrames: s.durationFrames };
      if (s.sourceStartFrame) scene.sourceStartFrame = s.sourceStartFrame;
      if (s.sourceDurationFrames) scene.sourceDurationFrames = s.sourceDurationFrames;
      return scene;
    }),
    transitions: spec.transitions.map((t, i) => ({
      id: "t" + (i + 1),
      fromSceneId: t.from,
      toSceneId: t.to,
      frames: t.frames,
      ownerSceneId: t.owner,
    })),
    narration: spec.narration.map((n) => ({
      id: n.id,
      startFrame: n.startFrame,
      endFrameExclusive: n.endFrameExclusive,
    })),
    sfxCues: spec.sfx.map((x) => ({ id: x.id, frame: x.frame })),
  };
  const result = compileTimeline(input);
  if (!result.ok) {
    console.error("compile failed for " + spec.id + ": " + JSON.stringify(result.findings, null, 2));
    process.exit(1);
  }
  const out = join(planDir, spec.id + ".json");
  writeFileSync(out, JSON.stringify(result.compiled, null, 2) + "\n");
  console.log("wrote " + out + " total_frames=" + result.compiled.sidecar.total_frames);
}
