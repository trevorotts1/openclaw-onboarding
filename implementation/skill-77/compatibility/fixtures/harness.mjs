// CWE-041 fixture harness: shared scratch, tree-copy, install, driver,
// and inventory machinery for the compatibility batteries.
//
// Trees under test:
//   tree A = an isolated copy of the accepted canonical skill tree,
//            installed with the product's own scripts/install-runtime.mjs
//            (isolated pinned install plus build).
//   tree B = the upgrade simulation: a copy of the same accepted tree
//            with the skill version bumped to v1.0.1 in the copy only
//            (version, skill-version.txt, SKILL.md frontmatter) and its
//            manifest and archive regenerated with the product's own
//            scripts/build-bundles.mjs, then installed the same way.
//            The canonical tree in the repository is never touched.
//
// run-all.mjs prepares both trees once and passes their locations via
// env (CWE041_TREE_A_ROOT / CWE041_TREE_B_ROOT). A battery run on its
// own prepares tree A itself.

import { spawn, spawnSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const HERE = dirname(fileURLToPath(import.meta.url));
export const COMPAT_DIR = resolve(HERE, "..");
export const REPO_ROOT = resolve(HERE, "..", "..", "..", "..");
export const CANONICAL_SKILL_ROOT = join(REPO_ROOT, "77-council-of-wise-elders");
export const DRIVER = join(HERE, "runtime-driver.mjs");

export function scratchRoot() {
  const base = process.env.TMPDIR ?? tmpdir();
  const dir = mkdtempSync(join(base, "cwe041-"));
  return dir;
}

export function sha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function walkFiles(root, out = []) {
  for (const name of readdirSync(root).sort()) {
    const p = join(root, name);
    if (statSync(p).isDirectory()) walkFiles(p, out);
    else out.push(p);
  }
  return out;
}

/** Sorted per-file hash inventory of a directory, plus its digest. */
export function inventory(dir) {
  const files = walkFiles(dir).map((p) => {
    const bytes = readFileSync(p);
    return {
      path: relative(dir, p).split("\\").join("/"),
      sha256: sha256Hex(bytes),
      bytes: bytes.length,
    };
  });
  files.sort((a, b) => (a.path < b.path ? -1 : 1));
  const digest = sha256Hex(
    Buffer.from(files.map((f) => `${f.sha256}  ${f.path}`).join("\n") + "\n", "utf8"),
  );
  return { files, file_count: files.length, inventory_sha256: digest };
}

export function copyTree(src, dst) {
  cpSync(src, dst, {
    recursive: true,
    filter: (p) => {
      const rel = relative(src, p).split("\\").join("/");
      if (rel === "") return true;
      if (rel.startsWith("runtime/node_modules")) return false;
      if (rel.startsWith("runtime/dist")) return false;
      return true;
    },
  });
  return dst;
}

function run(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    encoding: "utf8",
    timeout: opts.timeoutMs ?? 600_000,
    env: { ...process.env, ...(opts.env ?? {}) },
    cwd: opts.cwd,
  });
  return result;
}

/** Install a copied tree with the product installer; returns a record. */
export function installTree(treeRoot, logPath) {
  const result = run(
    "node",
    [join(treeRoot, "scripts", "install-runtime.mjs"), "--root", treeRoot],
    { timeoutMs: 900_000 },
  );
  if (logPath) {
    writeFileSync(logPath, `$ node scripts/install-runtime.mjs --root ${treeRoot}\n${result.stdout ?? ""}${result.stderr ?? ""}\nEXIT ${result.status}\n`);
  }
  return {
    status: result.status,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
    runtimeDir: join(treeRoot, "runtime"),
    srcDir: join(treeRoot, "runtime", "src"),
    distDir: join(treeRoot, "runtime", "dist"),
    distIndex: join(treeRoot, "runtime", "dist", "index.js"),
    bundle: join(treeRoot, "runtime", "dist", "blackceo-council.mjs"),
  };
}

/** Prepare tree A (pristine accepted copy, installed). Cached per process. */
let treeACache = null;
export function treeA(scratch) {
  if (process.env.CWE041_TREE_A_ROOT && existsSync(process.env.CWE041_TREE_A_ROOT)) {
    const root = process.env.CWE041_TREE_A_ROOT;
    return {
      root,
      runtimeDir: join(root, "runtime"),
      srcDir: join(root, "runtime", "src"),
      distDir: join(root, "runtime", "dist"),
      preparedByCaller: true,
    };
  }
  if (treeACache) return treeACache;
  const root = join(scratch, "tree-a", "77-council-of-wise-elders");
  copyTree(CANONICAL_SKILL_ROOT, root);
  const install = installTree(root, join(scratch, "tree-a-install.log"));
  if (install.status !== 0) {
    throw new Error(`tree A install failed (exit ${install.status}); see tree-a-install.log`);
  }
  treeACache = { root, runtimeDir: install.runtimeDir, srcDir: install.srcDir, distDir: install.distDir, install };
  return treeACache;
}

/** Prepare tree B (version-bumped upgrade copy, installed). */
let treeBCache = null;
export function treeB(scratch) {
  if (process.env.CWE041_TREE_B_ROOT && existsSync(process.env.CWE041_TREE_B_ROOT)) {
    const root = process.env.CWE041_TREE_B_ROOT;
    return {
      root,
      runtimeDir: join(root, "runtime"),
      srcDir: join(root, "runtime", "src"),
      distDir: join(root, "runtime", "dist"),
      preparedByCaller: true,
    };
  }
  if (treeBCache) return treeBCache;
  const root = join(scratch, "tree-b", "77-council-of-wise-elders");
  copyTree(CANONICAL_SKILL_ROOT, root);
  // Bump the version in the copy only: exactly the three places the
  // doctor requires to agree (version, skill-version.txt, SKILL.md
  // frontmatter).
  for (const rel of ["version", "skill-version.txt"]) {
    writeFileSync(join(root, rel), "v1.0.1\n");
  }
  const skillMdPath = join(root, "SKILL.md");
  const skillMd = readFileSync(skillMdPath, "utf8");
  if (!/^version:\s*1\.0\.0\s*$/m.test(skillMd)) {
    throw new Error("SKILL.md frontmatter version line not found for the upgrade bump");
  }
  writeFileSync(skillMdPath, skillMd.replace(/^version:\s*1\.0\.0\s*$/m, "version: 1.0.1"));
  // Regenerate the copy's manifest and archive with the product script.
  const bundles = run("node", ["scripts/build-bundles.mjs"], { cwd: root, timeoutMs: 300_000 });
  writeFileSync(join(scratch, "tree-b-bundles.log"), `${bundles.stdout ?? ""}${bundles.stderr ?? ""}\nEXIT ${bundles.status}\n`);
  if (bundles.status !== 0) {
    throw new Error(`tree B bundle regeneration failed (exit ${bundles.status}); see tree-b-bundles.log`);
  }
  const install = installTree(root, join(scratch, "tree-b-install.log"));
  if (install.status !== 0) {
    throw new Error(`tree B install failed (exit ${install.status}); see tree-b-install.log`);
  }
  treeBCache = { root, runtimeDir: install.runtimeDir, srcDir: install.srcDir, distDir: install.distDir, install };
  return treeBCache;
}

/** Run one driver job to completion and return the parsed result. */
export function runDriver(runtimeDir, job, opts = {}) {
  const jobDir = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), "cwe041-job-"));
  const jobPath = join(jobDir, "job.json");
  writeFileSync(jobPath, JSON.stringify(job));
  const result = spawnSync("node", ["--import", "tsx", DRIVER, jobPath], {
    encoding: "utf8",
    timeout: opts.timeoutMs ?? 300_000,
    cwd: runtimeDir,
    env: { ...process.env, CWE041_SRC_DIR: join(runtimeDir, "src") },
  });
  const line = (result.stdout ?? "")
    .split("\n")
    .find((l) => l.startsWith("CWE041_RESULT "));
  if (!line) {
    throw new Error(
      `driver produced no result (exit ${result.status}): stdout=${(result.stdout ?? "").slice(0, 800)} stderr=${(result.stderr ?? "").slice(0, 800)}`,
    );
  }
  return {
    status: result.status,
    result: JSON.parse(line.slice("CWE041_RESULT ".length)),
    stdout: result.stdout,
    stderr: result.stderr,
  };
}

/** Start a driver job in the background (for the gated mid-flight run). */
export function startDriver(runtimeDir, job) {
  const jobDir = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), "cwe041-job-"));
  const jobPath = join(jobDir, "job.json");
  writeFileSync(jobPath, JSON.stringify(job));
  const child = spawn("node", ["--import", "tsx", DRIVER, jobPath], {
    cwd: runtimeDir,
    env: { ...process.env, CWE041_SRC_DIR: join(runtimeDir, "src") },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d));
  child.stderr.on("data", (d) => (stderr += d));
  return { child, output: () => ({ stdout, stderr }) };
}

export async function waitForFile(path, timeoutMs = 120_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (existsSync(path)) return true;
    await new Promise((r) => setTimeout(r, 100));
  }
  return false;
}

export function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

export function mkdirp(path) {
  mkdirSync(path, { recursive: true });
  return path;
}
