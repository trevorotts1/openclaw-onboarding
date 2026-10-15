#!/usr/bin/env node
// CWE-041: derive component descriptor snapshots from the three real
// repository trees, or check the committed snapshots against them.
//
// Usage:
//   node derive-descriptors.mjs [--onb <skill-folder>] [--cc <repo-root>]
//                               [--999 <repo-root>] [--write | --check]
// Defaults: ONB = this repository's 77-council-of-wise-elders folder;
// CC and 999 = $CWE041_CC_ROOT / $CWE041_999_ROOT, or the standard
// Skill 77 worktree layout. --write refreshes descriptors/*.json in
// place; --check exits 3 when any snapshot differs from its tree.

import { existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  derive999Descriptor,
  deriveCcDescriptor,
  deriveOnbSkillDescriptor,
} from "../negotiate.mjs";
import { CANONICAL_SKILL_ROOT, COMPAT_DIR, readJson } from "./harness.mjs";

function argValue(args, name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
}

const args = process.argv.slice(2);
const mode = args.includes("--write") ? "write" : "check";
const home = process.env.HOME ?? "";
const onbRoot = argValue(args, "--onb") ?? CANONICAL_SKILL_ROOT;
const ccRoot =
  argValue(args, "--cc") ??
  process.env.CWE041_CC_ROOT ??
  join(home, "workspace", "skill77", "worktrees", "cc-cwe041");
const nineRoot =
  argValue(args, "--999") ??
  process.env.CWE041_999_ROOT ??
  join(home, "workspace", "skill77", "worktrees", "999-cwe041");

const jobs = [
  { file: "onb-canonical.json", derive: () => deriveOnbSkillDescriptor(onbRoot) },
  { file: "cc-composed.json", derive: () => deriveCcDescriptor(ccRoot), root: ccRoot },
  { file: "nine99-distribution.json", derive: () => derive999Descriptor(nineRoot), root: nineRoot },
];

let failures = 0;
for (const job of jobs) {
  const target = join(COMPAT_DIR, "descriptors", job.file);
  if (job.root && !existsSync(job.root)) {
    console.log(`SKIP ${job.file}: tree not present at ${job.root}`);
    continue;
  }
  const live = job.derive();
  if (mode === "write") {
    writeFileSync(target, JSON.stringify(live, null, 2) + "\n");
    console.log(`WROTE ${job.file} from ${job.root ?? onbRoot}`);
  } else {
    const snapshot = readJson(target);
    const same = JSON.stringify(snapshot) === JSON.stringify(live);
    console.log(`${same ? "MATCH" : "DRIFT"} ${job.file}`);
    if (!same) {
      failures += 1;
      console.log(`  snapshot: ${JSON.stringify(snapshot).slice(0, 400)}`);
      console.log(`  live:     ${JSON.stringify(live).slice(0, 400)}`);
    }
  }
}
process.exit(failures ? 3 : 0);
