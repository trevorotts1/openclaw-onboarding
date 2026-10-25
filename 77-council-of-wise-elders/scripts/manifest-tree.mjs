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

/** The one aggregate formula over [{path, sha256}], sorted by path. */
export function aggregateEntries(entries) {
  const sorted = [...entries].sort((a, b) => (a.path < b.path ? -1 : 1));
  return createHash("sha256")
    .update(sorted.map((f) => `${f.sha256}  ${f.path}`).join("\n") + "\n")
    .digest("hex");
}

/** The aggregate a manifest records, recomputed from the tree as it is now. */
export function treeAggregate(dir, opts = {}) {
  const entries = manifestEntries(dir, opts);
  return { entries, aggregate: aggregateEntries(entries), fileCount: entries.length };
}

// The only distribution differences a verifier can prove from the canonical
// release alone. A distribution may declare nothing outside this set.
export const DISTRIBUTION_KINDS = Object.freeze([
  "private_scope_items_dropped",
  "sentences_scrubbed",
  "generated_archive_not_vendored",
  "file_added",
  "manifest_regenerated",
]);

/**
 * Fail-closed walk for verification. Unlike walkTree()/treeAggregate(), this
 * never throws and never follows a symlink: anything it cannot reconstruct
 * exactly (a link, an unreadable or unstattable entry, an unshippable
 * dependency tree) becomes a problem the caller must refuse on. It also
 * reports what the aggregate deliberately excludes, so a verifier can bound
 * those paths instead of ignoring them:
 *   entries   [{path, sha256, bytes}] for the files a manifest covers
 *   dist      the same, for the built runtime under runtime/dist
 *   archives  [{path, sha256, bytes}] for every *.skill archive present
 *   generated [{path, kind}] for runtime/node_modules and root .wired-* files
 *   problems  [{path, reason}] for every entry that cannot be verified
 */
export function treeAudit(dir, { includeRuntimeDist = true } = {}) {
  const entries = [];
  const dist = [];
  const archives = [];
  const generated = [];
  const problems = [];
  const push = (entry) => (entry.path.startsWith("runtime/dist/") ? dist : entries).push(entry);
  const walk = (rel) => {
    const abs = rel ? join(dir, rel) : dir;
    let dirents;
    try {
      dirents = readdirSync(abs, { withFileTypes: true });
    } catch (error) {
      problems.push({ path: rel || ".", reason: `unreadable directory (${String(error.message).split("\n")[0]})` });
      return;
    }
    for (const e of dirents.sort((x, y) => x.name.localeCompare(y.name))) {
      const r = rel ? `${rel}/${e.name}` : e.name;
      const full = join(dir, r);
      // Version-control metadata and bytecode caches are never skill content;
      // treeIdentity() skips them too, so the proof must not diverge on them.
      if (e.name === ".git" || e.name === "__pycache__") continue;
      if (e.name === "node_modules") {
        generated.push({ path: r, kind: "runtime/node_modules" });
        continue;
      }
      if (/^\.wired-/.test(e.name) && !rel) {
        generated.push({ path: r, kind: "roll-sentinel" });
        continue;
      }
      if (e.isSymbolicLink()) {
        problems.push({ path: r, reason: "is a symlink — a vendored tree must ship regular files, never a link to content outside it" });
        continue;
      }
      if (e.isDirectory()) {
        walk(r);
        continue;
      }
      if (!e.isFile()) {
        problems.push({ path: r, reason: "is not a regular file" });
        continue;
      }
      let bytes;
      try {
        bytes = readFileSync(full);
      } catch (error) {
        problems.push({ path: r, reason: `unreadable (${String(error.message).split("\n")[0]})` });
        continue;
      }
      const entry = { path: r, sha256: createHash("sha256").update(bytes).digest("hex"), bytes: bytes.length };
      if (r === "manifest.json") continue;
      if (r.endsWith(".skill")) archives.push(entry);
      else if (includeRuntimeDist || !isGeneratedRuntimePath(r)) push(entry);
    }
  };
  walk("");
  entries.sort((a, b) => (a.path < b.path ? -1 : 1));
  dist.sort((a, b) => (a.path < b.path ? -1 : 1));
  archives.sort((a, b) => (a.path < b.path ? -1 : 1));
  return { entries, dist, archives, generated, problems };
}
