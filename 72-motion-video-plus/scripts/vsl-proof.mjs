#!/usr/bin/env node
// MG-037: motion-proof driver for the VSL handoff layer.
//
// Runs the shipped MG-032 evaluator (runtime/src/motion-proof) over
// one rendered insert and its MG-031 coverage record, so the return
// package's proof claim is the evaluator's own verdict, not a
// restatement. The case document is supplied by the caller (the
// producer derives it from the staged scene's declared assertions).
//
// Usage:
//   node scripts/vsl-proof.mjs --case CASE.json --video VIDEO.mp4 \
//     --coverage COVERAGE.json --job-dir DIR --out-dir DIR
//
// Prints {"record": ..., "exit_code": N} on stdout and exits with
// the evaluator's exit code.

import { readFileSync } from "node:fs";
import { evaluateMotionProof } from "../runtime/dist/src/motion-proof/index.js";

function arg(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
}

const casePath = arg("--case");
const videoPath = arg("--video");
const coveragePath = arg("--coverage");
const jobDir = arg("--job-dir");
const outDir = arg("--out-dir");
if (!casePath || !videoPath || !coveragePath || !jobDir || !outDir) {
  console.error(JSON.stringify({ error: "usage: vsl-proof.mjs --case CASE.json --video VIDEO.mp4 --coverage COVERAGE.json --job-dir DIR --out-dir DIR" }));
  process.exit(2);
}

const caseDoc = JSON.parse(readFileSync(casePath, "utf8"));
const { record, exitCode } = evaluateMotionProof({
  caseDoc,
  videoPath,
  coverageRecordPath: coveragePath,
  outputDir: outDir,
  jobDir,
});
console.log(JSON.stringify({ record, exit_code: exitCode }));
process.exit(exitCode);
