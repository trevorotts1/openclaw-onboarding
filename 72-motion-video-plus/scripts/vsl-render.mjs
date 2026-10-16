#!/usr/bin/env node
// MG-037: insert render driver for the VSL handoff layer.
//
// Renders one staged V2 job package through the shipped dispatcher
// and the shipped Remotion adapter (the same path
// runtime/tests/run-remotion.ts exercises), under an approval record
// supplied by the caller. The driver adds no rendering behavior of
// its own: routing, contracts validation, and the delivery gate all
// belong to the dispatcher. Its only job is to carry the render
// evidence back to the Python producer as one JSON document.
//
// Usage:
//   node scripts/vsl-render.mjs --job-dir DIR --out-dir DIR \
//     --approval APPROVAL.json
//
// Exit 0 with the evidence JSON on stdout. A refused render exits
// with the adapter error's own exit class and prints the error's
// category and message as JSON on stderr.

import { readFileSync } from "node:fs";
import {
  createRegistry,
  loadCapabilityMatrix,
  MotionDispatcher,
} from "../runtime/dist/src/adapters/index.js";
import { createRemotionAdapter } from "../runtime/dist/src/adapters/remotion.js";
import { probeVideoFile } from "../runtime/dist/src/remotion/decode.js";

function arg(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
}

const jobDir = arg("--job-dir");
const outDir = arg("--out-dir");
const approvalPath = arg("--approval");
if (!jobDir || !outDir || !approvalPath) {
  console.error(JSON.stringify({ error: { category: "MG_SCHEMA_INVALID", message: "usage: vsl-render.mjs --job-dir DIR --out-dir DIR --approval APPROVAL.json" } }));
  process.exit(2);
}

const approval = JSON.parse(readFileSync(approvalPath, "utf8"));
const adapter = createRemotionAdapter({ outputDir: outDir });
const dispatcher = new MotionDispatcher(createRegistry([adapter]));
const matrix = loadCapabilityMatrix();

try {
  const outcome = await dispatcher.renderFinal(jobDir, approval, {
    matrix,
    timeoutMs: 900_000,
  });
  const evidence = outcome.evidence;
  const mp4 = evidence.outputPaths[0];
  const poster = evidence.outputPaths[1] ?? null;
  const probe = probeVideoFile(mp4);
  console.log(JSON.stringify({
    engine: evidence.engine ?? "remotion",
    kind: evidence.kind,
    output_paths: evidence.outputPaths,
    artifacts: evidence.artifacts,
    mp4,
    poster,
    probe: {
      width: probe.width,
      height: probe.height,
      frame_count: probe.frameCount,
      duration_seconds: probe.durationSeconds,
      fps: `${probe.fpsNumerator}/${probe.fpsDenominator}`,
    },
  }));
} catch (err) {
  const category = err && err.category ? err.category : "MG_RENDER_FAILED";
  const exitClass = err && typeof err.exitClass === "number" ? err.exitClass : 5;
  console.error(JSON.stringify({ error: { category, exitClass, message: String(err && err.message ? err.message : err) } }));
  process.exit(exitClass);
}
