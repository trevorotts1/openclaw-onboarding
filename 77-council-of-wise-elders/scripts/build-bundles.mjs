#!/usr/bin/env node
// Council of Wise Elders: bundle builder.
// Computes the deterministic tree hash of this skill folder (sorted
// relative paths, per-file SHA-256, aggregate over "sha256  path"
// lines) and writes the generated manifest.json. The manifest excludes
// itself and any generated .skill archive.
//
// The distributable council-of-wise-elders.skill archive is generated
// only at final integration, when the complete pack (runtime, advisor
// packs, schemas) exists. Generating an archive of a scaffold and
// presenting it as the finished bundle would misrepresent its state,
// so this builder records the archive as deferred in the manifest
// instead of producing one.
// Usage: node build-bundles.mjs [--root <skill-folder>]

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const rootIdx = args.indexOf("--root");
const root = rootIdx >= 0
  ? resolve(args[rootIdx + 1])
  : resolve(dirname(fileURLToPath(import.meta.url)), "..");

function walk(dir, out = []) {
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const files = [];
for (const p of walk(root)) {
  const rel = relative(root, p).split("\\").join("/");
  if (rel === "manifest.json" || rel.endsWith(".skill")) continue;
  const bytes = readFileSync(p);
  files.push({
    path: rel,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    bytes: bytes.length,
  });
}
files.sort((a, b) => (a.path < b.path ? -1 : 1));
const aggregate = createHash("sha256")
  .update(files.map((f) => `${f.sha256}  ${f.path}`).join("\n") + "\n")
  .digest("hex");

let sourceCommit = null;
try {
  sourceCommit = execFileSync("git", ["-C", root, "rev-parse", "HEAD"],
    { encoding: "utf8" }).trim();
} catch { /* not a git checkout: source commit stays null */ }

const version = existsSync(join(root, "version"))
  ? readFileSync(join(root, "version"), "utf8").trim() : null;

const manifest = {
  skill: "council-of-wise-elders",
  skill_version: version,
  generated_by: "scripts/build-bundles.mjs",
  source_commit: sourceCommit,
  file_count: files.length,
  aggregate_sha256: aggregate,
  hash_method: "SHA-256 per file over sorted relative paths; aggregate is SHA-256 of the lines \"<sha256>  <path>\" joined by newlines with a trailing newline. manifest.json itself and any .skill archive are excluded.",
  archive: {
    file: "council-of-wise-elders.skill",
    status: "deferred_to_final_integration",
    note: "The distributable archive is generated when the complete pack exists (runtime, advisor packs, schemas). This scaffold ships the verified source tree and this manifest only.",
  },
  files,
};

writeFileSync(join(root, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log(`manifest.json written: ${files.length} files, aggregate ${aggregate}`);
console.log("archive council-of-wise-elders.skill: DEFERRED to final integration (complete pack required)");
