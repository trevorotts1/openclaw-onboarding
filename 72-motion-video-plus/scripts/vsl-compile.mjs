#!/usr/bin/env node
// MG-037: timeline compile driver for the VSL handoff layer.
//
// A thin, checked wrapper over the shipped MG-021 compiler
// (runtime/src/timeline). The Python producer
// (scripts/vsl_handoff.py) builds a compiler input document; this
// driver compiles it and writes the combined {timeline, sidecar}
// document. Compilation failures are the compiler's own findings,
// printed verbatim: the driver never adjusts a duration, a slot, or
// a cue to make a plan fit.
//
// Usage:
//   node scripts/vsl-compile.mjs --input INPUT.json --out PLAN.json
//
// Exit 0 with {"ok": true, "out": PATH} on stdout when the plan
// compiles; exit 2 with {"ok": false, "findings": [...]} when the
// compiler refuses; exit 1 for driver-level failures (bad arguments,
// unreadable input, missing build).

import { readFileSync, writeFileSync } from "node:fs";
import { compileTimeline } from "../runtime/dist/src/timeline/index.js";

function arg(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
}

const inputPath = arg("--input");
const outPath = arg("--out");
if (!inputPath || !outPath) {
  console.error(JSON.stringify({ ok: false, error: "usage: vsl-compile.mjs --input INPUT.json --out PLAN.json" }));
  process.exit(1);
}

let input;
try {
  input = JSON.parse(readFileSync(inputPath, "utf8"));
} catch (err) {
  console.error(JSON.stringify({ ok: false, error: `cannot read compiler input ${inputPath}: ${err.message}` }));
  process.exit(1);
}

const result = compileTimeline(input);
if (!result.ok) {
  console.log(JSON.stringify({ ok: false, findings: result.findings }));
  process.exit(2);
}
writeFileSync(outPath, JSON.stringify(result.compiled, null, 2) + "\n", "utf8");
console.log(JSON.stringify({ ok: true, out: outPath, total_frames: result.compiled.sidecar.total_frames }));
