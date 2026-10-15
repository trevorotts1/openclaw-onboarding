#!/usr/bin/env node
// CWE-041 battery runner: prepares the isolated trees once, runs every
// battery with logs captured to disk, and writes a reproducible
// evidence receipt (inputs hashed, per-battery verdicts and counts
// read from the TAP logs, never from console readouts alone).
//
// Usage: node run-all.mjs [--evidence-dir <dir>] [--cc-root <dir>]
//                         [--999-root <dir>]
// Defaults: evidence dir ~/workspace/skill77/cwe-041/evidence/run-<ts>;
// TMPDIR from the environment (the build brief pins
// TMPDIR=~/workspace/skill77/tmp-scratch).
// Exit 0 when every battery passes, 3 otherwise.
// The receipt is also written to ../evidence/receipt.json for commit.

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  COMPAT_DIR,
  HERE,
  inventory,
  readJson,
  scratchRoot,
  sha256Hex,
  treeA,
  treeB,
} from "./harness.mjs";

function argValue(args, name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
}

const args = process.argv.slice(2);
const home = process.env.HOME ?? "";
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const evidenceDir =
  argValue(args, "--evidence-dir") ??
  join(home, "workspace", "skill77", "cwe-041", "evidence", `run-${stamp}`);
mkdirSync(evidenceDir, { recursive: true });
const ccRoot =
  argValue(args, "--cc-root") ??
  process.env.CWE041_CC_ROOT ??
  join(home, "workspace", "skill77", "worktrees", "cc-cwe041");
const nineRoot =
  argValue(args, "--999-root") ??
  process.env.CWE041_999_ROOT ??
  join(home, "workspace", "skill77", "worktrees", "999-cwe041");

const scratch = scratchRoot();
console.log(`run-all: scratch ${scratch}`);
console.log(`run-all: evidence ${evidenceDir}`);

// Prepare trees once, in this process, then hand their locations to the
// battery processes through the environment.
const a = treeA(scratch);
const b = treeB(scratch);
console.log(`run-all: tree A ${a.root}`);
console.log(`run-all: tree B ${b.root}`);

const manifestPath = join(COMPAT_DIR, "compatibility-manifest.json");
const manifest = readJson(manifestPath);
const inputs = {
  compatibility_manifest_sha256: sha256Hex(readFileSync(manifestPath)),
  descriptor_sha256: {
    "onb-canonical.json": sha256Hex(readFileSync(join(COMPAT_DIR, "descriptors", "onb-canonical.json"))),
    "cc-composed.json": sha256Hex(readFileSync(join(COMPAT_DIR, "descriptors", "cc-composed.json"))),
    "nine99-distribution.json": sha256Hex(readFileSync(join(COMPAT_DIR, "descriptors", "nine99-distribution.json"))),
  },
  cohort: manifest.release_cohort.members.map((m) => ({
    component: m.component,
    commit: m.commit,
  })),
  canonical_aggregate_sha256: manifest.release_cohort.members.find((m) => m.component === "onb-skill").tree_identity.aggregate_sha256,
  node_version: process.version,
  runtime_verified: false,
};

const batteries = [
  "negotiation-matrix.test.mjs",
  "not-ready-t116.test.mjs",
  "stale-worker-t060.test.mjs",
  "clean-install-t115.test.mjs",
  "preservation.test.mjs",
  "rollback.test.mjs",
];

const results = [];
let allOk = true;
for (const file of batteries) {
  const logPath = join(evidenceDir, `${file}.log`);
  const started = new Date().toISOString();
  const run = spawnSync("node", ["--test", "--test-reporter=tap", join(HERE, file)], {
    encoding: "utf8",
    timeout: 1_800_000,
    env: {
      ...process.env,
      CWE041_TREE_A_ROOT: a.root,
      CWE041_TREE_B_ROOT: b.root,
      CWE041_CC_ROOT: ccRoot,
      CWE041_999_ROOT: nineRoot,
    },
  });
  const output = `${run.stdout ?? ""}\n${run.stderr ?? ""}`;
  writeFileSync(logPath, output);
  const count = (label) => {
    const m = output.match(new RegExp(`^# ${label} (\\d+)$`, "m"));
    return m ? Number(m[1]) : null;
  };
  const entry = {
    battery: file,
    started_at: started,
    exit: run.status,
    tests: count("tests"),
    pass: count("pass"),
    fail: count("fail"),
    skipped: count("skipped"),
    log: logPath,
  };
  results.push(entry);
  const ok = run.status === 0 && entry.fail === 0;
  allOk = allOk && ok;
  console.log(`run-all: ${file}: exit ${run.status}, pass ${entry.pass}, fail ${entry.fail}, skipped ${entry.skipped}`);
}

const receipt = {
  receipt: "skill77.cwe-041.evidence-receipt/v1",
  unit: "CWE-041",
  generated_at: new Date().toISOString(),
  verdict: allOk ? "PASS" : "FAIL",
  inputs,
  trees: {
    a: { root: a.root, skill_version: "v1.0.0", note: "isolated copy of the accepted canonical tree, product installer" },
    b: { root: b.root, skill_version: "v1.0.1", note: "upgrade simulation: version bumped in the copy only, manifest and archive regenerated with the product bundle script, product installer" },
  },
  batteries: results,
  evidence_dir: evidenceDir,
  scratch,
};
writeFileSync(join(evidenceDir, "receipt.json"), JSON.stringify(receipt, null, 2) + "\n");
const committedDir = join(COMPAT_DIR, "evidence");
mkdirSync(committedDir, { recursive: true });
writeFileSync(join(committedDir, "receipt.json"), JSON.stringify(receipt, null, 2) + "\n");
console.log(`run-all: receipt written to ${join(evidenceDir, "receipt.json")} and ${join(committedDir, "receipt.json")}`);
console.log(`run-all: verdict ${receipt.verdict}`);
process.exit(allOk ? 0 : 3);
