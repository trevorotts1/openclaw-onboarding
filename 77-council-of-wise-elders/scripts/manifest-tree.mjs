// Council of Wise Elders: the one manifest tree-hash implementation.
//
// Every verifier that asks "is this tree exactly what its manifest records?"
// must ask it the same way, so the walk, the exclusions and the aggregate live
// here. scripts/build-bundles.mjs, scripts/verify-bundles.mjs,
// scripts/doctor.mjs and scripts/selected-tree-gate.mjs all import them: a
// second copy of this algorithm is how two verifiers start disagreeing.
//
// Method: SHA-256 per file over sorted relative paths; the aggregate is the
// SHA-256 of the lines "<sha256>  <path>" joined by newlines with a trailing
// newline. manifest.json, any .skill archive, runtime/dist and
// runtime/node_modules are excluded from the tree aggregate; so are the
// root-level .wired-<version> roll sentinels update-skills.sh writes.

import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

export const HASH_METHOD =
  "SHA-256 per file over sorted relative paths; aggregate is SHA-256 of the lines \"<sha256>  <path>\" joined by newlines with a trailing newline. manifest.json, any .skill archive, runtime/dist and runtime/node_modules are excluded from the tree aggregate; the built executable entry point is recorded in runtime_entry and verified by scripts/entry-point-gate.mjs.";

// Root-level .wired-<version> sentinels are written into every skill folder by
// update-skills.sh during a fleet roll. They are roll bookkeeping, not skill
// content, so they must not count toward the manifest tree hash.
export function isGeneratedRuntimePath(rel) {
  return rel === "runtime/dist" || rel.startsWith("runtime/dist/")
    || rel === "runtime/node_modules" || rel.startsWith("runtime/node_modules/")
    || /^\.wired-[^/]*$/.test(rel);
}

// node_modules and roll sentinels never enter the package. The BUILT runtime
// (runtime/dist) DOES: the distribution delivers the executable, its bundled
// dependencies and the skill instructions together.
export function isPackagingExcluded(rel) {
  return rel === "runtime/node_modules" || rel.startsWith("runtime/node_modules/")
    || /^\.wired-[^/]*$/.test(rel);
}

export function walkTree(dir, out = [], base = dir, includeRuntimeDist = false) {
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    const rel = relative(base, p).split("\\").join("/");
    if (includeRuntimeDist ? isPackagingExcluded(rel) : isGeneratedRuntimePath(rel)) continue;
    if (statSync(p).isDirectory()) walkTree(p, out, base, includeRuntimeDist);
    else out.push(p);
  }
  return out;
}

/** Sorted [{path, sha256, bytes}] for the files a manifest covers. */
export function manifestEntries(dir, { includeRuntimeDist = false } = {}) {
  const files = [];
  for (const p of walkTree(dir, [], dir, includeRuntimeDist)) {
    const rel = relative(dir, p).split("\\").join("/");
    if (rel === "manifest.json" || rel.endsWith(".skill")) continue;
    const bytes = readFileSync(p);
    files.push({
      path: rel,
      sha256: createHash("sha256").update(bytes).digest("hex"),
      bytes: bytes.length,
    });
  }
  files.sort((a, b) => (a.path < b.path ? -1 : 1));
  return files;
}

/** The aggregate a manifest records, recomputed from the tree as it is now. */
export function treeAggregate(dir, opts = {}) {
  const entries = manifestEntries(dir, opts);
  const aggregate = createHash("sha256")
    .update(entries.map((f) => `${f.sha256}  ${f.path}`).join("\n") + "\n")
    .digest("hex");
  return { entries, aggregate, fileCount: entries.length };
}
