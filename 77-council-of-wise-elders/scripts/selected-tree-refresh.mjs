#!/usr/bin/env node
// Council of Wise Elders: converge the copy the agent resolver selects with the
// tree this update ships.
//
// scripts/selected-tree-gate.mjs verifies what the runtime resolver selects and
// REFUSES a stale one — correctly, because an unverifiable archive or drifting
// tree is not a distribution artifact. But nothing in the roll ever WROTE that
// copy: update-skills.sh maintains only $OPENCLAW_ROOT/skills, and the
// resolver-selected folder (~/.agents/skills/..., ~/.claude/skills/...) is
// owned by whatever created it. So a copy whose version carriers were updated
// while its .skill archive stayed behind can only ever fail the gate, and the
// box could only reach readiness by a human rsync (measured on
// rescue-eddie-otts: version 1.0.80 everywhere, archive 33e4063d from the
// previous release).
//
// This is the missing install step, not a relaxation: wire.sh converges the
// selected copy from the shipped tree and then runs the SAME gate again. The
// gate is unchanged and still rejects a genuinely stale or modified payload.
//
// Two shapes, decided by the selected copy's own manifest:
//   * plain copy (no canonical_aggregate_sha256): the copy is meant to BE the
//     shipped tree, so every file of the shipped tree is mirrored over it,
//     manifest.json included. Files the copy alone carries are LEFT IN PLACE.
//   * distribution copy (it records a canonical_aggregate_sha256): it differs
//     from the canonical tree BY DESIGN (the 999 packaging scrubs private
//     scopes), so only the release archive is replaced — the one artifact a
//     distribution may never keep from a previous release. Its own manifest and
//     DISTRIBUTION-RECONCILIATION.json are preserved.
//
// Nothing is ever deleted, no symlink is followed or written through, no copy
// is created where none exists, and the shipped tree itself is never touched
// (a selected path that IS the shipped tree is a no-op). Owner data the copy
// alone carries is reported, never removed.
//
// Usage: node scripts/selected-tree-refresh.mjs --source DIR --selected DIR
//        (exit 0 converged-or-nothing-to-do, 1 refused/failed, 2 usage)

import { createHash } from "node:crypto";
import {
  chmodSync, copyFileSync, existsSync, lstatSync, mkdirSync, readFileSync,
  readdirSync, realpathSync, renameSync, rmSync, statSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const SKILL_NAME = "council-of-wise-elders";
const ARCHIVE = `${SKILL_NAME}.skill`;
const RECONCILIATION = "DISTRIBUTION-RECONCILIATION.json";
const MAX_NAMED_EXTRAS = 5;

const readJson = (file) => {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return null;
  }
};

const sha256File = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");

const safeReal = (p) => {
  try {
    return realpathSync(p);
  } catch {
    return resolve(p);
  }
};

/** A council skill copy: SKILL.md + manifest.json (the gate's own signature). */
function isSkillFolder(dir) {
  return existsSync(join(dir, "SKILL.md")) && existsSync(join(dir, "manifest.json"));
}

/**
 * Every regular file of a tree, relative, with the same exclusions
 * scripts/manifest-tree.mjs applies: node_modules, .git and __pycache__ are
 * never skill content, and a root-level .wired-<version> sentinel is roll
 * bookkeeping. A symlink is never followed — a copied tree ships regular files.
 */
export function listTreeFiles(dir, rel = "", out = [], links = []) {
  let entries;
  try {
    entries = readdirSync(join(dir, rel), { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.name === ".git" || e.name === "__pycache__" || e.name === "node_modules") continue;
    if (!rel && /^\.wired-/.test(e.name)) continue;
    if (e.isSymbolicLink()) {
      links.push(r);
      continue;
    }
    if (e.isDirectory()) listTreeFiles(dir, r, out, links);
    else if (e.isFile()) out.push(r);
  }
  return out;
}

function treeLinks(dir) {
  const links = [];
  listTreeFiles(dir, "", [], links);
  return links;
}

/** True when `dir` or any ancestor is a git work tree (never rewrite a checkout). */
function insideGitWorkTree(dir) {
  let probe = safeReal(dir);
  for (;;) {
    if (existsSync(join(probe, ".git"))) return probe;
    const up = dirname(probe);
    if (up === probe) return null;
    probe = up;
  }
}

/** Write one file atomically, with the source's mode; replaces a link, never a dir. */
function overwrite(srcFile, dstRoot, rel) {
  const dst = join(dstRoot, rel);
  mkdirSync(dirname(dst), { recursive: true });
  let existing = null;
  try {
    existing = lstatSync(dst);
  } catch {
    existing = null;
  }
  if (existing && existing.isDirectory()) {
    throw new Error("a directory sits where the shipped tree has a file");
  }
  const tmp = `${dst}.selected-tree-refresh-${process.pid}`;
  try {
    copyFileSync(srcFile, tmp);
    chmodSync(tmp, statSync(srcFile).mode & 0o777);
    renameSync(tmp, dst);
  } catch (error) {
    try { rmSync(tmp, { force: true }); } catch { /* best effort */ }
    throw error;
  }
}

function sameBytes(a, b) {
  try {
    if (!lstatSync(b).isFile()) return false;
    return statSync(a).size === statSync(b).size && sha256File(a) === sha256File(b);
  } catch {
    return false;
  }
}

/**
 * Converge `selectedDir` onto the release `sourceDir`. Returns
 *   {status, mode, selected, source, written, unchanged, extras, links,
 *    archive, archiveExpected, problems, reason}
 * status: same | already-current | refreshed | partial | skipped
 */
export function refreshSelectedTree({ sourceDir, selectedDir } = {}) {
  const result = {
    status: "skipped",
    mode: null,
    selected: selectedDir ?? null,
    source: sourceDir ?? null,
    written: [],
    unchanged: 0,
    extras: [],
    links: [],
    archive: null,
    archiveExpected: null,
    problems: [],
    reason: null,
  };
  const skip = (reason) => {
    result.status = "skipped";
    result.reason = reason;
    return result;
  };

  if (!sourceDir || !selectedDir) return skip("both --source (the shipped tree) and --selected (the resolver-selected copy) are required");
  if (!isSkillFolder(sourceDir)) return skip(`the shipped tree ${sourceDir} is not a ${SKILL_NAME} folder (SKILL.md + manifest.json)`);
  if (!existsSync(selectedDir)) return skip(`the selected copy ${selectedDir} does not exist: a refresh converges an existing copy and never creates one`);
  // A link is reported as a link before anything else: it is never followed and
  // never written through, whether or not its target looks like a skill folder.
  let lst = null;
  try {
    lst = lstatSync(selectedDir);
  } catch {
    lst = null;
  }
  if (lst && lst.isSymbolicLink()) {
    return skip(
      `the selected copy is a symlink to ${safeReal(selectedDir)}: a refresh never writes through a link it did not create ` +
      `(point the agent at the shipped tree, or replace the link deliberately)`,
    );
  }
  if (!isSkillFolder(selectedDir)) return skip(`the selected path ${selectedDir} is not a ${SKILL_NAME} folder (SKILL.md + manifest.json): it is not a copy this step may rewrite`);

  const sourceManifest = readJson(join(sourceDir, "manifest.json"));
  if (!sourceManifest) return skip(`the shipped tree ${sourceDir} has no readable manifest.json`);
  const expectedArchive = sourceManifest.archive?.sha256 ?? null;
  result.archiveExpected = expectedArchive;

  const sourceReal = safeReal(sourceDir);
  const selectedReal = safeReal(selectedDir);
  if (sourceReal === selectedReal) {
    result.status = "same";
    result.reason = "the selected copy IS the shipped tree: nothing to converge";
    return result;
  }
  const gitRoot = insideGitWorkTree(selectedDir);
  if (gitRoot) return skip(`the selected copy sits inside the git work tree ${gitRoot}: a refresh never rewrites a checkout`);

  const selectedManifest = readJson(join(selectedDir, "manifest.json"));
  const distribution = Boolean(selectedManifest && typeof selectedManifest.canonical_aggregate_sha256 === "string");
  result.mode = distribution ? "distribution-archive" : "mirror";

  if (distribution) {
    // A distribution differs from the canonical tree by design; its own
    // manifest and reconciliation record are the owner's and stay untouched.
    // The release ARCHIVE is the artifact it may never keep from a previous
    // release — that is exactly the file a partial sync leaves behind.
    const srcArchive = join(sourceDir, ARCHIVE);
    const dstArchive = join(selectedDir, ARCHIVE);
    if (!expectedArchive || !existsSync(srcArchive)) {
      return skip(`the shipped tree records no ${ARCHIVE} (manifest.archive.sha256), so the selected copy's archive cannot be converged`);
    }
    if (existsSync(dstArchive) && sha256File(dstArchive) === expectedArchive) {
      result.archive = expectedArchive;
      result.status = "already-current";
      result.reason = "the selected distribution already carries the release archive";
      return result;
    }
    try {
      overwrite(srcArchive, selectedDir, ARCHIVE);
    } catch (error) {
      result.problems.push(`${ARCHIVE}: ${String(error?.message ?? error).split("\n")[0]}`);
      result.status = "partial";
      return result;
    }
    const got = sha256File(dstArchive);
    result.archive = got;
    if (got !== expectedArchive) {
      result.problems.push(`${ARCHIVE}: copied ${got} but the shipped manifest records ${expectedArchive}`);
      result.status = "partial";
      return result;
    }
    result.written.push(ARCHIVE);
    result.status = "refreshed";
    return result;
  }

  // Plain copy: it is meant to BE the shipped tree. Mirror every file the
  // shipped tree carries (manifest.json and the release archive included).
  for (const rel of listTreeFiles(sourceDir)) {
    const src = join(sourceDir, rel);
    const dst = join(selectedDir, rel);
    if (sameBytes(src, dst)) {
      result.unchanged += 1;
      continue;
    }
    try {
      overwrite(src, selectedDir, rel);
      result.written.push(rel);
    } catch (error) {
      result.problems.push(`${rel}: ${String(error?.message ?? error).split("\n")[0]}`);
    }
  }
  const mirrored = new Set(listTreeFiles(sourceDir));
  for (const rel of listTreeFiles(selectedDir)) {
    if (!mirrored.has(rel)) result.extras.push(rel);
  }
  result.links = treeLinks(selectedDir);
  const archivePath = join(selectedDir, ARCHIVE);
  if (existsSync(archivePath)) result.archive = sha256File(archivePath);
  if (expectedArchive && result.archive !== expectedArchive) {
    result.problems.push(`${ARCHIVE}: the selected copy carries ${result.archive ?? "(none)"} but the shipped manifest records ${expectedArchive}`);
  }
  result.status = result.problems.length ? "partial" : result.written.length ? "refreshed" : "already-current";
  if (!result.reason) {
    result.reason = result.written.length
      ? `mirrored ${result.written.length} file(s) of the shipped tree over the selected copy`
      : "the selected copy already matches the shipped tree";
  }
  return result;
}

/** One line per refresh, for wire.sh and a reader of the roll log. */
export function refreshLine(result) {
  const bits = [
    `SELECTED-TREE-REFRESH: ${result.status.toUpperCase()}`,
    `mode=${result.mode ?? "none"}`,
    `selected=${result.selected ?? "<none>"}`,
    `written=${result.written.length}`,
    `archive=${result.archive ?? "none"}`,
  ];
  if (result.archiveExpected && result.archiveExpected !== result.archive) bits.push(`expected=${result.archiveExpected}`);
  if (result.reason) bits.push(`- ${result.reason}`);
  return bits.join(" ");
}

if (process.argv[1] && import.meta.url === pathToFileURL(safeReal(process.argv[1])).href) {
  const argv = process.argv.slice(2);
  const opt = (name) => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };
  const unknown = argv.filter((a) => a.startsWith("--") && !["--source", "--selected"].includes(a));
  const source = opt("--source");
  const selected = opt("--selected");
  if (unknown.length || !source || !selected) {
    console.error("usage: node scripts/selected-tree-refresh.mjs --source DIR --selected DIR");
    process.exit(2);
  }
  const result = refreshSelectedTree({ sourceDir: resolve(source), selectedDir: resolve(selected) });
  console.log(refreshLine(result));
  for (const p of result.problems) console.log(`  ✗ ERROR: ${p}`);
  if (result.extras.length) {
    const named = result.extras.slice(0, MAX_NAMED_EXTRAS).join(", ");
    console.log(
      `  ⚠️  extras: the selected copy alone carries ${result.extras.length} file(s) (${named}` +
      `${result.extras.length > MAX_NAMED_EXTRAS ? ", ..." : ""}); they are left in place, never deleted`,
    );
  }
  if (result.links.length) {
    console.log(`  ⚠️  links: the selected copy carries ${result.links.length} symlink(s) (${result.links.slice(0, MAX_NAMED_EXTRAS).join(", ")}); no link is followed or written through`);
  }
  const ok = ["same", "already-current", "refreshed"].includes(result.status);
  process.exit(ok ? 0 : 1);
}
