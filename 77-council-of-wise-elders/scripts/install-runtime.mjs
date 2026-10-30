#!/usr/bin/env node
// Council of Wise Elders: runtime installer (WER-004 dependency-ready slice).
//
// This is the canonical installer named by INSTALL.md. It builds the runtime
// into an IMMUTABLE EXTERNAL RELEASE PREFIX instead of mutating the checked-out
// skill tree, and it activates a release only after every stage verifies.
//
// Pipeline:
//   1. Prerequisite probe through the EXACT resolved launcher executable:
//      report its own version, then run node:sqlite in-memory
//      create/insert/read/close plus an isolated persistent
//      create/close/reopen cycle. Nothing is written before this passes.
//   2. Source integrity: SHA-256 manifest over protected SOURCE only.
//      node_modules/ and dist/ are NEVER hashed into the source manifest.
//   3. Staged install into <prefix>/staging/: copy source, `npm ci
//      --no-audit --no-fund`, `npm run build`. The active release is untouched.
//   4. Independent generated-artifact receipt over dist/.
//   4b. Dependency-closure receipt over the PRODUCTION dependency set: the
//      package-lock metadata (version/integrity/resolved), the installed
//      package's own package.json (version, exports) and the export targets on
//      disk. This is a STATIC metadata check. It never imports, resolves or
//      executes a module, so it is never reported as runtime resolution proof
//      (`dependencyResolutionProven` stays false everywhere).
//   5. Verification of the staged artifact (sources + artifact bytes, plus a
//      load check of the real entry point: hash + load, never 'ready' from
//      SKILL.md presence or source match alone).
//   6. Atomic activation via an atomically replaced <prefix>/active.json.
//      The previous receipt is preserved and ROLLBACK.md is rewritten.
//   7. Idempotence: an identical source/artifact/node combination is a no-op.
//
// Durable user data lives in <prefix>/data (or --data-dir), never inside a
// replaceable release tree. This installer does not run migrations: the
// application that owns the store acquires its own migration/backup lock.
//
// Usage:
//   node install-runtime.mjs [options]
// Options:
//   --root <skill-folder>       skill folder containing runtime/ (default: ..)
//   --runtime-dir <dir>         explicit runtime source directory
//   --prefix <dir>              external release prefix (env COUNCIL_RUNTIME_PREFIX)
//   --data-dir <dir>            durable user data root (default <prefix>/data)
//   --node-executable <path>    exact launcher executable (default process.execPath)
//   --npm-executable <path>     npm launcher (default npm / npm.cmd on PATH)
//   --check-prereqs             probe only; never installs, never writes a release
//   --verify-release <dir>      verify an installed release against its receipts
//   --rollback                  atomically re-activate the previous release
//   --print-runtime-root        print the dependency-complete ACTIVATED release
//                               root as JSON (the value a plugin's runtimeRoot
//                               must use). Reads active.json only; static
//                               closure check, never a runtime resolution proof.
//   --json                      emit a machine-readable result on stdout
// Exit codes: 0 installed / verified / no-op, 1 preflight or install failure.

import { spawnSync } from "node:child_process";
import {
  accessSync,
  constants as fsConstants,
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createHash, randomBytes } from "node:crypto";
import { builtinModules } from "node:module";
import { homedir } from "node:os";
import { basename, dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SOURCE_RECEIPT_SCHEMA = "wise-elders.council-runtime-source/v1";
const ARTIFACT_RECEIPT_SCHEMA = "wise-elders.council-runtime-artifact/v1";
const RELEASE_RECEIPT_SCHEMA = "wise-elders.council-runtime-release/v1";
const ACTIVE_SCHEMA = "wise-elders.council-runtime-active/v1";
const DEPENDENCY_RECEIPT_SCHEMA = "wise-elders.council-runtime-dependencies/v1";

// Graph roots a consumer can import from the release root: the advertised
// package entry (`exports["."]` -> dist/index.js) plus the two modules the
// plugin's in-process path imports. Their presence and reachable graph are what
// the plugin needs; their absence or an unloadable emit is the observed defect.
// Scope is these three roots, not every file under dist/.
export const RUNTIME_CLOSURE_ENTRIES = [
  "dist/brief/permitted-brief.js",
  "dist/contracts/index.js",
  "dist/index.js",
];

// Never hashed into the canonical SOURCE manifest, never copied into a release
// from the source tree. They are either installed (node_modules) or generated
// (dist) and are covered by the independent artifact receipt instead.
export const SOURCE_IGNORED_NAMES = new Set([
  "node_modules",
  "dist",
  ".git",
  ".cache",
  ".turbo",
  ".nyc_output",
  "coverage",
  ".DS_Store",
]);

export const ENTRY_ARTIFACT = "dist/blackceo-council.mjs";
export const REQUIRED_ARTIFACTS = ["dist/index.js", ENTRY_ARTIFACT];

const PROBE_TIMEOUT_MS = 60_000;
const NPM_TIMEOUT_MS = 15 * 60_000;

/** Accept the tested Node lines only: 22.13+ or 24+. Node 20 must refuse. */
export function isSupportedNodeVersion(version) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)/.exec(String(version));
  if (!match) return false;
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return (major === 22 && minor >= 13) || major >= 24;
}

export function parseArgs(argv) {
  const options = {
    root: resolve(dirname(fileURLToPath(import.meta.url)), ".."),
    runtimeDir: null,
    prefix: null,
    dataDir: null,
    nodeExecutable: process.execPath,
    npmExecutable: process.platform === "win32" ? "npm.cmd" : "npm",
    checkPrereqs: false,
    verifyRelease: null,
    rollback: false,
    printRuntimeRoot: false,
    json: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const take = (name) => {
      const value = argv[i + 1];
      if (!value || value.startsWith("--")) {
        throw new Error(`${name} requires a value`);
      }
      i += 1;
      return value;
    };
    switch (arg) {
      case "--root": options.root = resolve(take(arg)); break;
      case "--runtime-dir": options.runtimeDir = resolve(take(arg)); break;
      case "--prefix": options.prefix = resolve(take(arg)); break;
      case "--data-dir": options.dataDir = resolve(take(arg)); break;
      case "--node-executable": options.nodeExecutable = take(arg); break;
      case "--npm-executable": options.npmExecutable = take(arg); break;
      case "--check-prereqs": options.checkPrereqs = true; break;
      case "--verify-release": options.verifyRelease = resolve(take(arg)); break;
      case "--rollback": options.rollback = true; break;
      case "--print-runtime-root": options.printRuntimeRoot = true; break;
      case "--json": options.json = true; break;
      case "--idempotent": break; // updater parity; idempotence is always on
      case "--help":
      case "-h":
        options.help = true;
        break;
      default:
        throw new Error(`unknown option: ${arg}`);
    }
  }
  options.runtimeDir = options.runtimeDir ?? join(options.root, "runtime");
  return options;
}

/** Resolve the exact executable, not a PATH lookup. */
export function resolveExecutable(candidate) {
  if (!candidate) throw new Error("no executable supplied");
  let real;
  try {
    real = realpathSync(candidate);
  } catch (error) {
    throw new Error(`cannot resolve executable ${candidate}: ${error.message}`);
  }
  const stat = statSync(real);
  if (!stat.isFile()) throw new Error(`not a regular file: ${real}`);
  if (process.platform !== "win32") {
    accessSync(real, fsConstants.X_OK);
  }
  return real;
}

export function isInside(candidate, parent) {
  const rel = relative(resolve(parent), resolve(candidate));
  return rel === "" || (!rel.startsWith(`..${sep}`) && rel !== ".." && !rel.startsWith(sep));
}

export function defaultPrefix() {
  if (process.env.COUNCIL_RUNTIME_PREFIX) {
    return resolve(process.env.COUNCIL_RUNTIME_PREFIX);
  }
  if (process.platform === "win32") {
    return join(process.env.LOCALAPPDATA || homedir(), "blackceo", "council-runtime");
  }
  return join(homedir(), ".local", "share", "blackceo", "council-runtime");
}

// Runs in the child process started with the RESOLVED executable. It must not
// write anything except its own isolated temp database.
const SQLITE_PROBE_SOURCE = `
const assert = (await import("node:assert/strict")).default;
const { mkdtempSync, rmSync } = await import("node:fs");
const { tmpdir } = await import("node:os");
const { join } = await import("node:path");
const { DatabaseSync } = await import("node:sqlite");

// 1. In-memory create / insert / read / close.
const memory = new DatabaseSync(":memory:");
memory.exec("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)");
memory.prepare("INSERT INTO probe (value) VALUES (?)").run("council-sqlite-ok");
assert.equal(memory.prepare("SELECT value FROM probe").get().value, "council-sqlite-ok");
memory.close();

// 2. Isolated persistent create / close / reopen / read / close.
const probeDir = mkdtempSync(join(tmpdir(), "council-sqlite-probe-"));
try {
  const file = join(probeDir, "probe.sqlite");
  const first = new DatabaseSync(file);
  first.exec("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)");
  first.prepare("INSERT INTO probe (value) VALUES (?)").run("persistent-ok");
  first.close();
  const reopened = new DatabaseSync(file);
  assert.equal(reopened.prepare("SELECT value FROM probe").get().value, "persistent-ok");
  reopened.close();
} finally {
  rmSync(probeDir, { recursive: true, force: true });
}
console.log("COUNCIL-SQLITE-PROBE: PASS");
`;

/**
 * Probe the exact executable: its own reported version plus node:sqlite
 * in-memory and persistent reopen cycles. Throws before any install write.
 */
export function probeRuntime(nodeExecutable) {
  const executable = resolveExecutable(nodeExecutable);

  const versionRun = spawnSync(executable, ["--version"], {
    encoding: "utf8",
    timeout: PROBE_TIMEOUT_MS,
  });
  if (versionRun.error) {
    throw new Error(`could not run ${executable} --version: ${versionRun.error.message}`);
  }
  if (versionRun.status !== 0) {
    throw new Error(`${executable} --version exited ${versionRun.status}: ${(versionRun.stderr || "").trim()}`);
  }
  const version = `${versionRun.stdout || ""}`.trim();
  if (!isSupportedNodeVersion(version)) {
    throw new Error(
      `Council runtime requires Node.js ^22.13.0 || >=24 with node:sqlite; ` +
      `the resolved executable ${executable} reports ${version || "(no version)"}`
    );
  }

  const sqliteRun = spawnSync(
    executable,
    ["--input-type=module", "-e", SQLITE_PROBE_SOURCE],
    { encoding: "utf8", timeout: PROBE_TIMEOUT_MS }
  );
  if (sqliteRun.error) {
    throw new Error(`node:sqlite probe could not start under ${executable}: ${sqliteRun.error.message}`);
  }
  if (sqliteRun.status !== 0) {
    throw new Error(
      `node:sqlite in-memory/persistent probe failed under ${executable} ` +
      `(exit ${sqliteRun.status}): ${(sqliteRun.stderr || sqliteRun.stdout || "").trim()}`
    );
  }
  if (!/COUNCIL-SQLITE-PROBE: PASS/.test(sqliteRun.stdout || "")) {
    throw new Error(`node:sqlite probe produced no PASS marker under ${executable}`);
  }
  return { executable, version };
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function canonicalDigest(entries) {
  return createHash("sha256").update(JSON.stringify(entries)).digest("hex");
}

/**
 * Walk `sourceDir` and hash protected SOURCE only. node_modules and dist are
 * excluded by name at every level; they are covered by the artifact receipt.
 */
export function computeSourceManifest(sourceDir) {
  const entries = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      if (SOURCE_IGNORED_NAMES.has(name)) continue;
      const full = join(dir, name);
      const stat = lstatSync(full);
      if (stat.isSymbolicLink()) {
        const target = readlinkSync(full);
        entries.push({
          path: relative(sourceDir, full).split(sep).join("/"),
          kind: "symlink",
          sha256: createHash("sha256").update(target).digest("hex"),
          size: Buffer.byteLength(target),
        });
      } else if (stat.isDirectory()) {
        walk(full);
      } else if (stat.isFile()) {
        entries.push({
          path: relative(sourceDir, full).split(sep).join("/"),
          kind: "file",
          sha256: sha256File(full),
          size: stat.size,
        });
      }
    }
  };
  walk(sourceDir);
  entries.sort((a, b) => a.path.localeCompare(b.path));
  return { entries, digest: canonicalDigest(entries), fileCount: entries.length };
}

/** Hash every generated file under dist/ into an independent receipt. */
export function computeArtifactManifest(releaseDir) {
  const distDir = join(releaseDir, "dist");
  if (!existsSync(distDir)) {
    throw new Error(`generated artifact directory missing: ${distDir}`);
  }
  const entries = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      const full = join(dir, name);
      const stat = lstatSync(full);
      if (stat.isDirectory()) {
        walk(full);
      } else if (stat.isFile()) {
        entries.push({
          path: relative(releaseDir, full).split(sep).join("/"),
          sha256: sha256File(full),
          size: stat.size,
        });
      }
    }
  };
  walk(distDir);
  entries.sort((a, b) => a.path.localeCompare(b.path));
  for (const required of REQUIRED_ARTIFACTS) {
    if (!entries.some((entry) => entry.path === required)) {
      throw new Error(`required build product missing: ${required}`);
    }
  }
  return { entries, digest: canonicalDigest(entries), fileCount: entries.length };
}

/**
 * Relative export targets declared by an installed package, without "./".
 *
 * Pattern targets (`./v4/locales/*`) are export subpath patterns, not files:
 * they cannot be existence-checked as a literal path, and zod 4.4.3 declares
 * two of them. They are skipped rather than reported missing; the literal
 * targets are still checked.
 */
function collectExportTargets(exportsField) {
  const targets = new Set();
  const visit = (value, depth) => {
    if (depth > 6 || value === null || value === undefined) return;
    if (typeof value === "string") {
      if (value.startsWith("./") && !value.includes("*")) targets.add(value.slice(2));
      return;
    }
    if (Array.isArray(value)) {
      for (const item of value) visit(item, depth + 1);
      return;
    }
    if (typeof value === "object") {
      for (const item of Object.values(value)) visit(item, depth + 1);
    }
  };
  visit(exportsField, 0);
  return [...targets].sort();
}

const CLOSURE_MAX_FILES = 512;
const CLOSURE_MAX_BYTES = 8 * 1024 * 1024;
const CLOSURE_EXTENSIONS = /\.(js|mjs|cjs|json)$/;
const CLOSURE_BUILTINS = new Set(builtinModules);

/**
 * Static ESM module-specifier extraction. Comments and template literals are
 * skipped, and a string counts only when it is the specifier of a statement
 * level `import`/`export ... from`, the bare `import "x"` form, or `from` inside
 * such a statement. Prose inside a string is never mistaken for an import.
 * Nothing is resolved or executed.
 *
 * This function is duplicated verbatim in the plugin core
 * (extensions/council-before-dispatch/lib/core.mjs). The two trees ship
 * independently; keep the parser identical.
 */
export function moduleSpecifiers(source) {
  const tokens = [];
  const n = source.length;
  const isWord = (c) => c !== undefined && /[A-Za-z0-9_$]/.test(c);
  let i = 0;
  let line = 1;
  while (i < n) {
    const c = source[i];
    if (c === "\n") {
      line += 1;
      i += 1;
      continue;
    }
    if (c === "/" && source[i + 1] === "/") {
      while (i < n && source[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && source[i + 1] === "*") {
      i += 2;
      while (i < n && !(source[i] === "*" && source[i + 1] === "/")) {
        if (source[i] === "\n") line += 1;
        i += 1;
      }
      i += 2;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      const startLine = line;
      let value = "";
      let closed = false;
      i += 1;
      while (i < n) {
        const d = source[i];
        if (d === "\\") {
          value += source[i + 1] ?? "";
          i += 2;
          continue;
        }
        if (d === quote) {
          i += 1;
          closed = true;
          break;
        }
        if (d === "\n") {
          line += 1;
          if (quote !== "`") break;
        }
        value += d;
        i += 1;
      }
      if (closed) tokens.push({ type: quote === "`" ? "template" : "string", value, line: startLine });
      continue;
    }
    if (isWord(c)) {
      const start = i;
      while (i < n && isWord(source[i])) i += 1;
      tokens.push({ type: "word", value: source.slice(start, i), line });
      continue;
    }
    if (!/\s/.test(c)) tokens.push({ type: "punct", value: c, line });
    i += 1;
  }

  const found = [];
  let statement = null;
  let depth = 0;
  let afterFrom = false;
  let bareImport = false;
  let previous = null;
  for (const token of tokens) {
    if (statement === null) {
      if (
        token.type === "word" &&
        (token.value === "import" || token.value === "export") &&
        (previous === null || (previous.type === "punct" && (previous.value === ";" || previous.value === "}")))
      ) {
        statement = token.value;
        depth = 0;
        afterFrom = false;
        bareImport = token.value === "import";
      }
    } else if (token.type === "punct" && (token.value === "{" || token.value === "(" || token.value === "[")) {
      depth += 1;
    } else if (token.type === "punct" && (token.value === "}" || token.value === ")" || token.value === "]")) {
      depth -= 1;
    } else if (token.type === "punct" && token.value === ";" && depth <= 0) {
      statement = null;
      depth = 0;
      afterFrom = false;
      bareImport = false;
    } else if (token.type === "word" && token.value === "from" && depth <= 0) {
      afterFrom = true;
    } else if ((token.type === "string" || token.type === "template") && depth <= 0) {
      if (afterFrom) {
        found.push({ specifier: token.value, line: token.line });
        statement = null;
      } else if (bareImport && statement === "import") {
        found.push({ specifier: token.value, line: token.line });
        statement = null;
      }
      afterFrom = false;
      bareImport = false;
    }
    previous = token;
  }
  return found;
}

/**
 * Static relative-import closure of the modules a consumer imports from the
 * release root: the advertised package entry plus the plugin bridge entries.
 * Every relative specifier must carry a file extension (Node ESM never appends
 * one), every relative target must exist inside the root, and every bare
 * specifier must resolve to a package installed under the root.
 *
 * STATIC ONLY: text and file existence, never import, resolution or execution.
 * A pass is not runtime resolution proof; it is the refusal of a graph Node
 * cannot load. Modules no listed root reaches are outside this check.
 */
export function runtimeClosureProblems(root, entries = RUNTIME_CLOSURE_ENTRIES) {
  const problems = [];
  const queue = [...entries];
  const seen = new Set();
  while (queue.length > 0) {
    const relativePath = queue.pop();
    if (seen.has(relativePath)) continue;
    if (seen.size >= CLOSURE_MAX_FILES) {
      problems.push(`closure check stopped at ${CLOSURE_MAX_FILES} files; refusing an unbounded graph`);
      break;
    }
    seen.add(relativePath);
    const full = join(root, ...relativePath.split("/"));
    let size;
    try {
      const stat = statSync(full);
      if (!stat.isFile()) {
        problems.push(`${relativePath} is not a regular file`);
        continue;
      }
      size = stat.size;
    } catch {
      problems.push(`${relativePath} is missing`);
      continue;
    }
    if (size > CLOSURE_MAX_BYTES) {
      problems.push(`${relativePath} is larger than ${CLOSURE_MAX_BYTES} bytes; refusing to parse it`);
      continue;
    }
    let source;
    try {
      source = readFileSync(full, "utf8");
    } catch {
      problems.push(`${relativePath} is unreadable`);
      continue;
    }
    for (const { specifier, line } of moduleSpecifiers(source)) {
      if (specifier.startsWith("node:") || CLOSURE_BUILTINS.has(specifier)) continue;
      if (specifier.startsWith(".") || specifier.startsWith("/")) {
        const target = resolve(dirname(full), specifier);
        if (!isInside(target, root)) {
          problems.push(`${relativePath}:${line} imports ${specifier}, which leaves the release root`);
          continue;
        }
        if (!CLOSURE_EXTENSIONS.test(specifier)) {
          problems.push(
            `${relativePath}:${line} imports ${specifier} with no file extension; Node ESM never appends one`,
          );
          continue;
        }
        let present = false;
        try {
          present = statSync(target).isFile();
        } catch {
          present = false;
        }
        if (!present) {
          problems.push(`${relativePath}:${line} imports ${specifier}, which does not exist`);
          continue;
        }
        if (/\.(js|mjs)$/.test(specifier)) {
          queue.push(relative(root, target).split(sep).join("/"));
        }
      } else if (!specifier.startsWith("#")) {
        const name = specifier.startsWith("@")
          ? specifier.split("/").slice(0, 2).join("/")
          : specifier.split("/")[0];
        const packageJson = join(root, "node_modules", ...name.split("/"), "package.json");
        if (!existsSync(packageJson)) {
          problems.push(`${relativePath}:${line} imports ${specifier}, but ${name} is not installed under the release root`);
        }
      }
    }
  }
  return problems;
}

/**
 * Production dependency closure for the release root.
 *
 * STATIC ONLY. It compares package.json, package-lock.json metadata and each
 * installed package's own metadata plus its declared export targets on disk.
 * Nothing is imported, resolved or executed, and a passing closure is NOT
 * runtime resolution proof: the receipt records
 * `dependencyResolutionProven: false` and callers must not upgrade that label.
 *
 * Throws on any gap so a release that cannot satisfy its production dependency
 * set is never activated.
 */
export function computeDependencyClosure(releaseDir) {
  const pkgPath = join(releaseDir, "package.json");
  if (!existsSync(pkgPath)) throw new Error(`dependency closure: package.json missing at ${pkgPath}`);
  const pkg = readJson(pkgPath);
  const productionDependencies = Object.entries(pkg.dependencies ?? {})
    .sort(([a], [b]) => a.localeCompare(b));

  const lockPath = join(releaseDir, "package-lock.json");
  if (!existsSync(lockPath)) {
    throw new Error(`dependency closure: package-lock.json missing at ${lockPath}`);
  }
  const lock = readJson(lockPath);
  if (!lock.packages || !lock.packages[""]) {
    throw new Error(`dependency closure: package-lock.json has no lockfileVersion 3 packages map at ${lockPath}`);
  }

  const entries = [];
  for (const [name, declaredRange] of productionDependencies) {
    const locked = lock.packages[`node_modules/${name}`];
    if (!locked) throw new Error(`dependency closure: ${name} is not pinned in package-lock.json`);
    if (locked.dev) throw new Error(`dependency closure: ${name} is recorded as a dev dependency in the lock`);
    if (!locked.version) throw new Error(`dependency closure: ${name} lock entry records no version`);
    if (!locked.integrity) throw new Error(`dependency closure: ${name} lock entry records no integrity digest`);

    const packageDir = join(releaseDir, "node_modules", ...name.split("/"));
    const installedPkgPath = join(packageDir, "package.json");
    if (!existsSync(installedPkgPath)) {
      throw new Error(`dependency closure: ${name} is not installed at ${installedPkgPath}`);
    }
    const installed = readJson(installedPkgPath);
    if (installed.version !== locked.version) {
      throw new Error(`dependency closure: ${name} installed ${installed.version} does not match locked ${locked.version}`);
    }
    const exportTargets = collectExportTargets(installed.exports);
    const missingTargets = exportTargets.filter(
      (target) => !existsSync(join(packageDir, ...target.split("/")))
    );
    if (missingTargets.length > 0) {
      throw new Error(`dependency closure: ${name} export target(s) missing: ${missingTargets.join(", ")}`);
    }
    entries.push({
      name,
      declaredRange,
      lockVersion: locked.version,
      lockIntegrity: locked.integrity,
      lockResolved: typeof locked.resolved === "string" ? locked.resolved : null,
      installedVersion: installed.version,
      packageJsonSha256: sha256File(installedPkgPath),
      moduleType: typeof installed.type === "string" ? installed.type : "commonjs",
      exportTargets,
      installScript: Boolean(installed.scripts?.install || installed.scripts?.postinstall),
    });
  }

  const closure = [];
  for (const relativePath of RUNTIME_CLOSURE_ENTRIES) {
    const full = join(releaseDir, ...relativePath.split("/"));
    if (!existsSync(full)) {
      throw new Error(`dependency closure: runtime entry missing ${relativePath} under ${releaseDir}`);
    }
    closure.push({ path: relativePath, sha256: sha256File(full), size: statSync(full).size });
  }

  const contractsDir = join(releaseDir, "dist", "contracts");
  if (!existsSync(contractsDir)) {
    throw new Error(`dependency closure: dist/contracts missing under ${releaseDir}`);
  }
  const contractsFiles = readdirSync(contractsDir)
    .sort()
    .filter((name) => name.endsWith(".js"))
    .map((name) => ({ path: `dist/contracts/${name}`, sha256: sha256File(join(contractsDir, name)) }));
  if (contractsFiles.length === 0) {
    throw new Error(`dependency closure: dist/contracts holds no modules under ${releaseDir}`);
  }

  // Presence is not loadability. The consumer imports these entries with plain
  // Node ESM, so the emitted graph must resolve: an extensionless relative
  // specifier can never load, and a bare package that is not installed cannot
  // either. A build that emits one is refused before it is ever activated.
  const importProblems = runtimeClosureProblems(releaseDir);
  if (importProblems.length > 0) {
    throw new Error(`dependency closure: emitted graph is not Node-ESM loadable: ${importProblems.join("; ")}`);
  }

  const payload = {
    package: { name: pkg.name, version: pkg.version },
    entries,
    closure,
    contractsFiles,
    importClosure: {
      check: "static_text_and_file_existence",
      resolutionProven: false,
      entries: [...RUNTIME_CLOSURE_ENTRIES],
    },
  };
  return {
    schema: DEPENDENCY_RECEIPT_SCHEMA,
    proof: "static_metadata_only",
    dependencyResolutionProven: false,
    nodeEngine: pkg.engines?.node ?? null,
    ...payload,
    digest: canonicalDigest(payload),
  };
}

/**
 * Parse-level load check of the real entry point (the byte hash is covered by
 * the artifact receipt). The installer is never 'ready' from source match or
 * SKILL.md presence alone: the installed entry must actually load.
 */
export function verifyEntryLoad(nodeExecutable, entryPath) {
  const run = spawnSync(nodeExecutable, ["--check", entryPath], {
    encoding: "utf8",
    timeout: PROBE_TIMEOUT_MS,
  });
  if (run.error) {
    throw new Error(`entry load check could not start under ${nodeExecutable}: ${run.error.message}`);
  }
  if (run.status !== 0) {
    throw new Error(
      `entry load check failed for ${entryPath} (exit ${run.status}): ${(run.stderr || run.stdout || "").trim()}`
    );
  }
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

export function receiptPaths(prefix, releaseId) {
  return {
    source: join(prefix, "receipts", `${releaseId}.source.json`),
    artifact: join(prefix, "receipts", `${releaseId}.artifact.json`),
    dependencies: join(prefix, "receipts", `${releaseId}.dependencies.json`),
    release: join(prefix, "receipts", `${releaseId}.release.json`),
    ...activePaths(prefix),
  };
}

export function activePaths(prefix) {
  return {
    active: join(prefix, "active.json"),
    previousActive: join(prefix, "previous-active.json"),
    rollback: join(prefix, "ROLLBACK.md"),
  };
}

/**
 * Verify a release tree against its receipts. Corruption or drift fails.
 * The actual entry point is hash-covered by the artifact receipt AND load
 * checked here, so a known-broken bundle never verifies as healthy. Never
 * touches the active pointer.
 *
 * `options.dependencies` is "require" (default) or "skip". "skip" exists only
 * for releases that predate the dependency receipt (rollback to an older
 * release); it is reported as unverified, never as verified.
 */
export function verifyRelease(prefix, releaseDir, nodeExecutable = process.execPath, options = {}) {
  const dependenciesMode = options.dependencies === "skip" ? "skip" : "require";
  const releaseId = basename(resolve(releaseDir));
  const paths = receiptPaths(prefix, releaseId);
  const problems = [];
  if (!existsSync(releaseDir)) problems.push(`release directory missing: ${releaseDir}`);
  if (!existsSync(paths.source)) problems.push(`source receipt missing: ${paths.source}`);
  if (!existsSync(paths.artifact)) problems.push(`artifact receipt missing: ${paths.artifact}`);
  if (problems.length > 0) return { ok: false, releaseId, problems, dependenciesVerified: false };

  const sourceReceipt = readJson(paths.source);
  const artifactReceipt = readJson(paths.artifact);
  try {
    const current = computeSourceManifest(releaseDir);
    if (current.digest !== sourceReceipt.digest) {
      problems.push(`source integrity mismatch: receipt ${sourceReceipt.digest} != actual ${current.digest}`);
    }
  } catch (error) {
    problems.push(`source verification failed: ${error.message}`);
  }
  try {
    const current = computeArtifactManifest(releaseDir);
    if (current.digest !== artifactReceipt.digest) {
      problems.push(`artifact integrity mismatch: receipt ${artifactReceipt.digest} != actual ${current.digest}`);
    }
    const expected = new Map(artifactReceipt.entries.map((entry) => [entry.path, entry.sha256]));
    for (const entry of current.entries) {
      const expectedHash = expected.get(entry.path);
      if (!expectedHash) {
        problems.push(`unexpected generated file: ${entry.path}`);
      } else if (expectedHash !== entry.sha256) {
        problems.push(`corrupt generated file: ${entry.path}`);
      }
    }
    for (const entry of artifactReceipt.entries) {
      if (!current.entries.some((actual) => actual.path === entry.path)) {
        problems.push(`generated file missing: ${entry.path}`);
      }
    }
  } catch (error) {
    problems.push(`artifact verification failed: ${error.message}`);
  }
  try {
    const entryPath = join(releaseDir, ...ENTRY_ARTIFACT.split("/"));
    if (!existsSync(entryPath)) {
      problems.push(`entry point missing: ${ENTRY_ARTIFACT}`);
    } else {
      verifyEntryLoad(nodeExecutable, entryPath);
    }
  } catch (error) {
    problems.push(`entry load check failed: ${error.message}`);
  }
  let dependenciesVerified = false;
  if (dependenciesMode === "require") {
    if (!existsSync(paths.dependencies)) {
      problems.push(`dependency receipt missing: ${paths.dependencies}`);
    } else {
      try {
        const receipt = readJson(paths.dependencies);
        const current = computeDependencyClosure(releaseDir);
        if (current.digest !== receipt.digest) {
          problems.push(`dependency closure mismatch: receipt ${receipt.digest} != actual ${current.digest}`);
        } else {
          dependenciesVerified = true;
        }
      } catch (error) {
        problems.push(`dependency closure verification failed: ${error.message}`);
      }
    }
  }
  return { ok: problems.length === 0, releaseId, problems, dependenciesVerified };
}

/**
 * The single supported answer to "which directory is the plugin's runtimeRoot".
 *
 * It is the ACTIVATED release recorded in <prefix>/active.json — the pointer
 * the installer already maintains and rolls back atomically. No second
 * `current` pointer is added: active.json IS the pointer, and a duplicate would
 * be one more thing that can disagree with it.
 *
 * The closure check is static (see computeDependencyClosure) and is labelled as
 * such. Returns a typed NOT_READY instead of guessing.
 */
export function activatedRuntimeRoot(prefix) {
  const paths = activePaths(prefix);
  if (!existsSync(paths.active)) {
    return {
      status: "NOT_READY",
      code: "COUNCIL_RUNTIME_NOT_ACTIVATED",
      detail: `no active release receipt at ${paths.active}`,
      dependencyClosure: "static_metadata_only",
      dependencyResolutionProven: false,
    };
  }
  let active;
  try {
    active = readJson(paths.active);
  } catch (error) {
    return {
      status: "NOT_READY",
      code: "COUNCIL_RUNTIME_ACTIVE_UNREADABLE",
      detail: `cannot read ${paths.active}: ${error instanceof Error ? error.message : String(error)}`,
      dependencyClosure: "static_metadata_only",
      dependencyResolutionProven: false,
    };
  }
  const releasePath = typeof active.releasePath === "string" ? active.releasePath : "";
  if (!releasePath) {
    return {
      status: "NOT_READY",
      code: "COUNCIL_RUNTIME_ACTIVE_NO_RELEASE_PATH",
      detail: `active receipt at ${paths.active} records no releasePath`,
      releaseId: active.releaseId ?? null,
      dependencyClosure: "static_metadata_only",
      dependencyResolutionProven: false,
    };
  }
  if (!existsSync(releasePath)) {
    return {
      status: "NOT_READY",
      code: "COUNCIL_RUNTIME_RELEASE_MISSING",
      detail: `active release path does not exist: ${releasePath}`,
      releaseId: active.releaseId ?? null,
      releasePath,
      dependencyClosure: "static_metadata_only",
      dependencyResolutionProven: false,
    };
  }
  let closure;
  try {
    closure = computeDependencyClosure(releasePath);
  } catch (error) {
    return {
      status: "NOT_READY",
      code: "COUNCIL_RUNTIME_CLOSURE_INCOMPLETE",
      detail: error instanceof Error ? error.message : String(error),
      releaseId: active.releaseId ?? null,
      releasePath,
      dependencyClosure: "static_metadata_only",
      dependencyResolutionProven: false,
    };
  }
  const receipt = receiptPaths(prefix, basename(releasePath)).dependencies;
  if (existsSync(receipt)) {
    try {
      const recorded = readJson(receipt);
      if (recorded.digest !== closure.digest) {
        return {
          status: "NOT_READY",
          code: "COUNCIL_RUNTIME_DEPENDENCY_DRIFT",
          detail: `dependency receipt ${recorded.digest} != actual ${closure.digest} at ${receipt}`,
          releaseId: active.releaseId ?? null,
          releasePath,
          dependencyClosure: "static_metadata_only",
          dependencyResolutionProven: false,
        };
      }
    } catch (error) {
      return {
        status: "NOT_READY",
        code: "COUNCIL_RUNTIME_DEPENDENCY_RECEIPT_UNREADABLE",
        detail: `cannot read ${receipt}: ${error instanceof Error ? error.message : String(error)}`,
        releaseId: active.releaseId ?? null,
        releasePath,
        dependencyClosure: "static_metadata_only",
        dependencyResolutionProven: false,
      };
    }
  }
  return {
    status: "READY",
    runtimeRoot: releasePath,
    releaseId: active.releaseId ?? basename(releasePath),
    sourceManifestDigest: active.sourceManifestDigest ?? null,
    artifactDigest: active.artifactDigest ?? null,
    dependencyDigest: closure.digest,
    productionDependencies: closure.entries.map((entry) => `${entry.name}@${entry.installedVersion}`),
    dependencyClosure: "static_metadata_only",
    dependencyResolutionProven: false,
    receiptRecorded: existsSync(receipt),
  };
}

function writeJsonAtomic(path, value) {
  const tempPath = `${path}.tmp-${process.pid}-${randomBytes(4).toString("hex")}`;
  writeFileSync(tempPath, `${JSON.stringify(value, null, 2)}\n`);
  renameSync(tempPath, path);
}

function runStep(command, args, cwd, label) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    timeout: NPM_TIMEOUT_MS,
    env: process.env,
  });
  if (result.error) {
    throw new Error(`${label}: could not run ${command}: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const output = `${result.stdout || ""}${result.stderr || ""}`.trim();
    throw new Error(`${label}: ${command} exited ${result.status}${output ? `: ${output}` : ""}`);
  }
  return result;
}

function validatePinnedDependencies(pkg) {
  const pins = [];
  for (const section of ["dependencies", "devDependencies"]) {
    for (const [name, version] of Object.entries(pkg[section] ?? {})) {
      if (!/^\d+\.\d+\.\d+$/.test(version)) {
        throw new Error(`${name} is not an exact pin in runtime/package.json (${section}: ${version})`);
      }
      pins.push(`${name}@${version}`);
    }
  }
  pins.sort();
  return pins;
}

function writeRollbackInstructions(prefix, active) {
  const installer = fileURLToPath(import.meta.url);
  const previous = active.previousReleaseId || "(none)";
  const lines = [
    "# Council runtime rollback",
    "",
    `Active release: \`${active.releaseId}\``,
    `Previous release: \`${previous}\``,
    `Prefix: \`${prefix}\``,
    "",
    "## Automated rollback",
    "",
    "```bash",
    `node ${JSON.stringify(installer)} --prefix ${JSON.stringify(prefix)} --rollback`,
    "```",
    "",
    "This atomically re-points `active.json` at the previous verified release and",
    "preserves the current receipt. Durable user data in the data directory is",
    "never touched.",
    "",
    "## Manual rollback",
    "",
    `Restore \`${join(prefix, "previous-active.json")}\` over \`${join(prefix, "active.json")}\`.`,
    "Both files are written atomically by this installer; a manual copy is the",
    "last resort if the installer is unavailable.",
    "",
    "## Limits",
    "",
    "A rollback re-points the executable. It does NOT downgrade or reverse a",
    "schema migration. If a release applied a destructive migration, restore the",
    "database backup taken by the owning application before that migration; the",
    "application that owns the store, not this installer, applies migrations.",
    "",
  ];
  writeFileSync(join(prefix, "ROLLBACK.md"), lines.join("\n"));
}

function activate(prefix, releaseId, releaseDir, sourceManifest, artifactReceipt, dependencyReceipt, probe, dataDir) {
  const paths = receiptPaths(prefix, releaseId);
  const previous = existsSync(paths.active) ? readJson(paths.active) : null;
  if (previous) {
    writeJsonAtomic(paths.previousActive, previous);
  }
  const active = {
    schema: ACTIVE_SCHEMA,
    releaseId,
    releasePath: releaseDir,
    receiptPath: paths.release,
    sourceManifestDigest: sourceManifest.digest,
    artifactDigest: artifactReceipt.digest,
    // Static dependency closure. Consumers must not read this as runtime
    // resolution proof; dependencyResolutionProven is false by construction.
    dependencyDigest: dependencyReceipt.digest,
    dependencyClosure: "static_metadata_only",
    dependencyResolutionProven: false,
    nodeExecutable: probe.executable,
    nodeVersion: probe.version,
    platform: process.platform,
    arch: process.arch,
    dataDir,
    activatedAt: new Date().toISOString(),
    previousReleaseId: previous?.releaseId ?? null,
  };
  writeJsonAtomic(paths.active, active);
  writeRollbackInstructions(prefix, active);
  return active;
}

// The idempotence path returns before activate(), so a requested --data-dir that
// differs from the active record used to be dropped on the floor: wire.sh then
// read the OLD dataDir back out of active.json and baked it into the launcher,
// silently leaving the service on a different store than the one it resolved.
// Record the requested durable data dir on an otherwise-unchanged release (it is
// a config field of active.json, never a release file, never a receipt) so a
// NOOP is honest. Nothing is copied, migrated or deleted here.
function recordDataDir(activePath, active, dataDir) {
  if (!dataDir || active.dataDir === dataDir) return false;
  try {
    mkdirSync(dataDir, { recursive: true });
    writeJsonAtomic(activePath, { ...active, dataDir });
    return true;
  } catch (error) {
    // Never pretend it was recorded: the old value stays and wire.sh refuses the
    // disagreement with NOT_READY STORE_AUTHORITY_MISMATCH.
    console.log(`FAIL data-dir: cannot record ${dataDir}: ${formatError(error)}`);
    return false;
  }
}

function noopDetail(active, dataDir, recorded) {
  if (recorded) return `only active.json dataDir updated to ${dataDir}`;
  if (active.dataDir === dataDir) return "nothing changed";
  return "dataDir NOT updated (see the FAIL line above)";
}

function formatError(error) {
  return error instanceof Error ? error.message : String(error);
}

export async function main(argv) {
  let options;
  try {
    options = parseArgs(argv);
  } catch (error) {
    console.log(`FAIL ${formatError(error)}`);
    return 1;
  }
  if (options.help) {
    console.log([
      "Usage: node install-runtime.mjs [options]",
      "  --root <skill-folder>     skill folder containing runtime/ (default: ..)",
      "  --runtime-dir <dir>       explicit runtime source directory",
      "  --prefix <dir>            external release prefix (env COUNCIL_RUNTIME_PREFIX)",
      "  --data-dir <dir>          durable user data root (default <prefix>/data)",
      "  --node-executable <path>  exact launcher executable (default process.execPath)",
      "  --npm-executable <path>   npm launcher (default npm on PATH)",
      "  --check-prereqs           probe only; installs nothing",
      "  --verify-release <dir>    verify an installed release against its receipts",
      "  --rollback                re-activate the previous verified release",
      "  --print-runtime-root      print the activated, dependency-complete release root as JSON",
      "  --json                    emit a machine-readable result",
    ].join("\n"));
    return 0;
  }

  const prefix = resolve(options.prefix ?? defaultPrefix());

  // ---- Print the activated runtime root (no probe, no writes, no spawn) ----
  // The one supported source of a plugin's runtimeRoot value. Static closure
  // check only; NOT_READY is typed, never guessed.
  if (options.printRuntimeRoot) {
    const result = activatedRuntimeRoot(prefix);
    console.log(JSON.stringify(result, null, 2));
    return result.status === "READY" ? 0 : 1;
  }

  const runtimeDir = options.runtimeDir;

  // ---- 1. Prerequisite probe. Nothing is written before this passes. ----
  let probe;
  try {
    probe = probeRuntime(options.nodeExecutable);
  } catch (error) {
    console.log(`FAIL preflight: ${formatError(error)}`);
    return 1;
  }
  console.log(`PASS preflight: ${probe.version} with in-memory SQLite read/write and persistent reopen (${probe.executable})`);

  // Guard: the release prefix and data dir must be external, replaceable trees.
  if (isInside(prefix, runtimeDir)) {
    console.log(`FAIL preflight: release prefix ${prefix} must live outside the runtime source tree ${runtimeDir}`);
    return 1;
  }
  const dataDir = resolve(options.dataDir ?? join(prefix, "data"));
  if (isInside(dataDir, join(prefix, "releases")) || isInside(dataDir, runtimeDir)) {
    console.log(`FAIL preflight: durable data ${dataDir} must live outside replaceable release trees`);
    return 1;
  }

  // ---- 2. Runtime package identity and exact pins ----
  const pkgPath = join(runtimeDir, "package.json");
  if (!existsSync(pkgPath)) {
    console.log(`FAIL preflight: runtime/package.json missing at ${pkgPath}`);
    return 1;
  }
  let pkg;
  try {
    pkg = readJson(pkgPath);
    validatePinnedDependencies(pkg);
  } catch (error) {
    console.log(`FAIL preflight: ${formatError(error)}`);
    return 1;
  }
  console.log(`INFO runtime package identity: ${pkg.name}@${pkg.version} (private=${pkg.private}, engines=${pkg.engines?.node ?? "unset"})`);

  if (options.checkPrereqs) {
    console.log("RUNTIME-PREREQS: PASS (no installation performed)");
    return 0;
  }

  // ---- Verify an existing release without activating anything ----
  if (options.verifyRelease) {
    const result = verifyRelease(prefix, options.verifyRelease, probe.executable);
    if (!result.ok) {
      console.log(`FAIL verify-release: ${result.problems.join("; ")}`);
      return 1;
    }
    console.log(`PASS verify-release: ${result.releaseId} (dependency closure: static metadata check only, not runtime resolution proof)`);
    return 0;
  }

  const paths = activePaths(prefix);
  const activePath = paths.active;

  // ---- Rollback: re-point the active receipt at the previous verified release ----
  if (options.rollback) {
    if (!existsSync(activePath)) {
      console.log(`FAIL rollback: no active release receipt at ${activePath}`);
      return 1;
    }
    const current = readJson(activePath);
    if (!current.previousReleaseId) {
      console.log("FAIL rollback: active receipt records no previous release");
      return 1;
    }
    const previousDir = join(prefix, "releases", current.previousReleaseId);
    // A release installed before the dependency receipt existed cannot carry
    // one. Rollback stays possible, but the closure is reported UNVERIFIED —
    // never as verified.
    const hasDependencyReceipt = existsSync(receiptPaths(prefix, current.previousReleaseId).dependencies);
    if (!hasDependencyReceipt) {
      console.log(`WARN rollback: ${current.previousReleaseId} predates the dependency receipt; its dependency closure is UNVERIFIED (static check not available).`);
    }
    const checked = verifyRelease(prefix, previousDir, probe.executable, {
      dependencies: hasDependencyReceipt ? "require" : "skip",
    });
    if (!checked.ok) {
      console.log(`FAIL rollback: previous release is not usable: ${checked.problems.join("; ")}`);
      return 1;
    }
    const previousRelease = readJson(receiptPaths(prefix, current.previousReleaseId).release);
    writeJsonAtomic(paths.previousActive, current);
    const rolledBack = {
      ...previousRelease.active,
      activatedAt: new Date().toISOString(),
      previousReleaseId: current.releaseId,
    };
    writeJsonAtomic(activePath, rolledBack);
    writeRollbackInstructions(prefix, rolledBack);
    console.log(`PASS rollback: active release is now ${rolledBack.releaseId} (previous ${current.releaseId} preserved)`);
    return 0;
  }

  // ---- 3. Source integrity over protected source only ----
  let sourceManifest;
  try {
    sourceManifest = computeSourceManifest(runtimeDir);
  } catch (error) {
    console.log(`FAIL source-integrity: ${formatError(error)}`);
    return 1;
  }
  console.log(`INFO source manifest: ${sourceManifest.fileCount} protected file(s), sha256 ${sourceManifest.digest} (node_modules/dist excluded)`);

  const releaseId = `rel-${sourceManifest.digest.slice(0, 12)}`;

  // The installed bundle (<prefix>/releases/<id>/dist/blackceo-council.mjs)
  // has no SKILL.md, advisors/ or manifest.json above it. Its dispatcher
  // reads '../../install-record.json', which from there is
  // <prefix>/releases/install-record.json: record the skill folder it was
  // built from. Written before the idempotence check so a re-run heals a
  // prefix installed without it. Outside every release tree, so receipts
  // and integrity digests are unaffected.
  try {
    mkdirSync(join(prefix, "releases"), { recursive: true });
    writeJsonAtomic(join(prefix, "releases", "install-record.json"), { skill_dir: dirname(runtimeDir) });
  } catch (error) {
    console.log(`FAIL install-record: ${formatError(error)}`);
    return 1;
  }

  // ---- 4. Idempotence: identical, verified, active release is a no-op ----
  if (existsSync(activePath)) {
    try {
      const active = readJson(activePath);
      const sameSource = active.sourceManifestDigest === sourceManifest.digest;
      const sameNode = active.nodeExecutable === probe.executable && active.nodeVersion === probe.version;
      if (sameSource && sameNode && existsSync(active.releasePath)) {
        const checked = verifyRelease(prefix, active.releasePath, probe.executable);
        if (checked.ok) {
          const recorded = recordDataDir(activePath, active, dataDir);
          console.log(`NOOP: release ${active.releaseId} already matches ${sourceManifest.digest} and verifies; ${noopDetail(active, dataDir, recorded)}`);
          return 0;
        }
        console.log(`INFO active release failed verification (${checked.problems.join("; ")}); rebuilding`);
      }
    } catch (error) {
      console.log(`INFO active receipt unreadable (${formatError(error)}); rebuilding`);
    }
  }

  const releasesDir = join(prefix, "releases");
  const receiptsDir = join(prefix, "receipts");
  const stagingDir = join(prefix, "staging");
  const finalDir = join(releasesDir, releaseId);

  // Refuse to reuse a release id that is currently active.
  if (existsSync(activePath)) {
    const active = readJson(activePath);
    if (active.releaseId === releaseId && existsSync(finalDir)) {
      const checked = verifyRelease(prefix, finalDir, probe.executable);
      if (checked.ok) {
        const recorded = recordDataDir(activePath, active, dataDir);
        console.log(`NOOP: release ${releaseId} is active and verifies; ${noopDetail(active, dataDir, recorded)}`);
        return 0;
      }
    }
  }

  // ---- 5. Stage. The active release is untouched from here on. ----
  let stageDir = null;
  try {
    mkdirSync(stagingDir, { recursive: true });
    mkdirSync(releasesDir, { recursive: true });
    mkdirSync(receiptsDir, { recursive: true });
    mkdirSync(dataDir, { recursive: true });
    stageDir = join(stagingDir, `${releaseId}-${process.pid}-${randomBytes(4).toString("hex")}`);
    cpSync(runtimeDir, stageDir, {
      recursive: true,
      dereference: false,
      filter: (src) => !SOURCE_IGNORED_NAMES.has(basename(src)),
    });
    console.log(`INFO staged source at ${stageDir}`);

    runStep(options.npmExecutable, ["ci", "--no-audit", "--no-fund"], stageDir, "dependency install (npm ci)");
    console.log("PASS dependency install (npm ci)");
    runStep(options.npmExecutable, ["run", "build"], stageDir, "runtime build (npm run build)");
    console.log("PASS runtime build (npm run build)");

    // ---- 6. Independent generated-artifact receipt ----
    const artifactReceipt = {
      schema: ARTIFACT_RECEIPT_SCHEMA,
      releaseId,
      sourceManifestDigest: sourceManifest.digest,
      package: { name: pkg.name, version: pkg.version },
      builtAt: new Date().toISOString(),
      node: { executable: probe.executable, version: probe.version },
      platform: process.platform,
      arch: process.arch,
      ...computeArtifactManifest(stageDir),
    };
    console.log(`PASS artifact receipt: ${artifactReceipt.fileCount} generated file(s), sha256 ${artifactReceipt.digest}`);

    // ---- 6b. Dependency-closure receipt (STATIC metadata, not runtime proof) ----
    // npm ci above supplied the production dependency set; this records what is
    // actually installed against the lock metadata so drift and a missing
    // package are detectable without importing anything.
    const dependencyClosure = computeDependencyClosure(stageDir);
    const dependencyReceipt = {
      ...dependencyClosure,
      releaseId,
      createdAt: new Date().toISOString(),
      sourceManifestDigest: sourceManifest.digest,
    };
    console.log(
      `PASS dependency closure (static metadata only, NOT runtime resolution proof): ` +
      `${dependencyReceipt.entries.length} production package(s) ` +
      `[${dependencyReceipt.entries.map((entry) => `${entry.name}@${entry.installedVersion}`).join(", ") || "none"}], ` +
      `${dependencyReceipt.contractsFiles.length} contract module(s), sha256 ${dependencyReceipt.digest}`
    );

    // ---- 7. Move into place, write receipts, verify, then activate ----
    rmSync(finalDir, { recursive: true, force: true });
    renameSync(stageDir, finalDir);
    stageDir = null;

    const sourceReceipt = {
      schema: SOURCE_RECEIPT_SCHEMA,
      releaseId,
      createdAt: new Date().toISOString(),
      sourceDir: runtimeDir,
      exclusions: [...SOURCE_IGNORED_NAMES].sort(),
      ...sourceManifest,
    };
    writeJsonAtomic(receiptPaths(prefix, releaseId).source, sourceReceipt);
    writeJsonAtomic(receiptPaths(prefix, releaseId).artifact, artifactReceipt);
    writeJsonAtomic(receiptPaths(prefix, releaseId).dependencies, dependencyReceipt);

    const checked = verifyRelease(prefix, finalDir, probe.executable);
    if (!checked.ok) {
      throw new Error(`staged release failed verification without activation: ${checked.problems.join("; ")}`);
    }

    const active = activate(prefix, releaseId, finalDir, sourceManifest, artifactReceipt, dependencyReceipt, probe, dataDir);
    writeJsonAtomic(receiptPaths(prefix, releaseId).release, {
      schema: RELEASE_RECEIPT_SCHEMA,
      releaseId,
      sourceManifestDigest: sourceManifest.digest,
      artifactDigest: artifactReceipt.digest,
      dependencyDigest: dependencyReceipt.digest,
      dependencyClosure: "static_metadata_only",
      dependencyResolutionProven: false,
      dataDir,
      active,
    });

    console.log(`PASS activation: active.json now points at ${releaseId}`);
    if (active.previousReleaseId) {
      console.log(`INFO previous release ${active.previousReleaseId} preserved with its receipt; see ${join(prefix, "ROLLBACK.md")}`);
    }
    console.log(`INFO durable data directory: ${dataDir} (outside replaceable release trees)`);
    console.log("INSTALL-RUNTIME: PASS (staged immutable install, artifact receipt, atomic activation)");

    if (options.json) {
      console.log(JSON.stringify({
        status: "activated",
        releaseId,
        sourceManifestDigest: sourceManifest.digest,
        artifactDigest: artifactReceipt.digest,
        dependencyDigest: dependencyReceipt.digest,
        dependencyClosure: "static_metadata_only",
        dependencyResolutionProven: false,
        runtimeRoot: finalDir,
        activePath: activePath,
        dataDir,
      }));
    }
    return 0;
  } catch (error) {
    if (stageDir) {
      rmSync(stageDir, { recursive: true, force: true });
    }
    console.log(`FAIL install: ${formatError(error)}`);
    if (existsSync(activePath)) {
      const active = readJson(activePath);
      console.log(`INFO previous release ${active.releaseId} is unchanged and still active at ${active.releasePath}`);
    } else {
      console.log("INFO no release was activated");
    }
    console.log("INSTALL-RUNTIME: DEGRADED install incomplete (previous files preserved; never report this state as ready). Fix the error above and re-run.");
    return 1;
  }
}

const invokedDirectly = (() => {
  const entry = process.argv[1];
  if (!entry) return false;
  const self = fileURLToPath(import.meta.url);
  try {
    return realpathSync(entry) === realpathSync(self);
  } catch {
    return resolve(entry) === resolve(self);
  }
})();

if (invokedDirectly) {
  process.exit(await main(process.argv.slice(2)));
}
