#!/usr/bin/env node
// Council of Wise Elders: selected-tree gate (verify-what-the-resolver-selects).
//
// Truth rule, extended from scripts/entry-point-gate.mjs: the packaging and
// install verifiers must verify the ACTUAL executable AND the ACTUAL tree the
// runtime resolver selects — never 'ready' from having written some directory.
// The runtime resolves its skill tree two ways (runtime/src/cli/dispatcher.ts
// skillRootForAssets): the install-record read module-relative from the
// running entry ({skill_dir}), then a layout walk to the nearest
// skill-signature folder. This gate mirrors that selection and then checks
// the SELECTED copy:
//   (a) it is at the version this update ships (an update that only touched
//       an unused directory can never report success),
//   (b) every competing copy on the box is detected and reported loudly,
//   (c) the selected copy passes the entry-point gate (real executable),
//   (d) the selected artifact ships its executable (runtime/dist + manifest
//       runtime_entry, the .skill archive, or an installed release named by
//       the resolver's own install-record) — a source-only artifact is not
//       shippable,
//   (e) the selected SKILL.md carries the current convene contract
//       ("Convening is the approval ... no grant to resolve") and none of the
//       stale grant language ("Resolve a real purpose-bound run grant").
//
// Duplicates are loud warnings (never silently equated with the selected
// copy); every selected-tree violation fails the gate. An install-record or a
// fallback directory is NOT proof that the intended OpenClaw agent reads that
// tree: when more than one copy exists, the gate requires agent-resolver
// evidence (--agent-selected PATH) and otherwise reports the selection as
// unproven instead of passing. Version identity is the agreement of every
// carrier (version, skill-version.txt, SKILL.md frontmatter, manifest
// skill_version) — a disagreement fails, it never silently prefers one file.
// An archive or an installed path that merely exists is not a valid artifact:
// the archive must be a zip that contains the entry, and the entry must be a
// non-empty JavaScript file that passes node --check when loading is enabled.
// wire.sh runs this gate
// and exits 1 on failure, so update-skills.sh withholds the .wired sentinel
// and no roll reports success for a stale or shadowed tree.
//
// ponytail: competing copies are reported, never deleted or rewritten here —
// converging a foreign root belongs to that root's own installer; add
// auto-convergence when one supported mechanism owns all the roots.
//
// Usage: node scripts/selected-tree-gate.mjs --skill-dir DIR [--prefix DIR]
//        [--home DIR] [--no-load] [--agent-selected PATH] [--agent-source TEXT]
//        (exit 0 ok, 1 problems, 2 usage)

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { closeSync, existsSync, lstatSync, mkdtempSync, openSync, readSync, readdirSync, readFileSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, isAbsolute, join, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { ENTRY_PATH, checkEntryPoint } from "./entry-point-gate.mjs";

export const SKILL_NAME = "council-of-wise-elders";
// The convene contract carried by current SKILL.md (whitespace-normalized).
export const CURRENT_CONTRACT_MARKER = "Convening is the approval";
// Grant-era instruction text that must never survive into a selected tree.
export const STALE_CONTRACT_PHRASES = [
  "Resolve a real purpose-bound run grant",
  "purpose-bound run grant through the installed",
];

const SIGNATURE = ["SKILL.md", "advisors", "manifest.json"];

// ------------------------------------------------------------- small helpers
function readJson(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function normalizedText(file) {
  try {
    return readFileSync(file, "utf8").replace(/\s+/g, " ");
  } catch {
    return "";
  }
}

function listDir(dir) {
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

function frontmatterVersion(dir) {
  try {
    const raw = readFileSync(join(dir, "SKILL.md"), "utf8");
    const block = /^---\r?\n([\s\S]*?)\r?\n---/.exec(raw);
    if (!block) return null;
    const line = /^version:\s*([0-9][^\s]*)\s*$/m.exec(block[1]);
    return line ? line[1].replace(/^v/, "") : null;
  } catch {
    return null;
  }
}

/**
 * Release identity of a copy: every carrier (version, skill-version.txt,
 * SKILL.md frontmatter, manifest skill_version) must agree. Disagreement is a
 * problem, never a preference for the first file that exists.
 */
export function readVersionEvidence(dir) {
  const sources = {};
  const problems = [];
  const plainFile = (file, label) => {
    try {
      const st = lstatSync(file);
      if (st.isSymbolicLink()) {
        let target = "unknown";
        try { target = realpathSync(file); } catch { /* broken link */ }
        problems.push(`${dir}: version carrier ${label} is a symlink (${target}) — a carrier must be a regular file of this tree, not a link that can borrow another tree's identity`);
        return false;
      }
      if (!st.isFile()) {
        problems.push(`${dir}: version carrier ${label} is not a regular file`);
        return false;
      }
      return true;
    } catch {
      return false;
    }
  };
  for (const [key, name] of [["versionFile", "version"], ["skillVersionFile", "skill-version.txt"]]) {
    try {
      if (!plainFile(join(dir, name), name)) continue;
      const v = readFileSync(join(dir, name), "utf8").trim().replace(/^v/, "");
      if (v) sources[key] = v;
    } catch {
      // carrier absent
    }
  }
  let skillMdLink = false;
  try {
    skillMdLink = lstatSync(join(dir, "SKILL.md")).isSymbolicLink();
  } catch {
    skillMdLink = false;
  }
  if (!skillMdLink) {
    const frontmatter = frontmatterVersion(dir);
    if (frontmatter) sources.frontmatter = frontmatter;
  } else {
    problems.push(`${dir}: SKILL.md is a symlink — its frontmatter cannot establish this tree's identity`);
  }
  const manifest = readJson(join(dir, "manifest.json"));
  if (manifest && typeof manifest.skill_version === "string" && manifest.skill_version.trim()) {
    sources.manifestSkillVersion = manifest.skill_version.trim().replace(/^v/, "");
  }
  const values = [...new Set(Object.values(sources))];
  if (values.length === 0) {
    problems.push(`${dir}: no version marker (version, skill-version.txt, SKILL.md frontmatter or manifest skill_version)`);
  } else if (values.length > 1) {
    const listed = Object.entries(sources).map(([k, v]) => `${k}=${v}`).join(", ");
    problems.push(
      `${dir}: version carriers disagree (${listed}); release identity must be consistent before an update or a gate can pass`,
    );
  }
  return { version: values.length === 1 ? values[0] : null, sources, problems };
}

/** Version of a copy, or null when the carriers disagree (evidence is authoritative). */
export function readVersion(dir) {
  return readVersionEvidence(dir).version;
}

function isSkillFolder(dir) {
  return SIGNATURE.every((name) => existsSync(join(dir, name)));
}

function samePath(a, b) {
  if (!a || !b) return false;
  return safeReal(a) === safeReal(b);
}

function safeReal(p) {
  try {
    return realpathSync(p);
  } catch {
    return resolve(p);
  }
}

// ------------------------------------------------------- install-record scan
function recordPathsNear(entryFile) {
  // runtime/src/cli/dispatcher.ts reads '../../install-record.json' relative
  // to the running entry: from <prefix>/releases/<id>/dist/<entry> that is
  // <prefix>/releases/install-record.json; from the 999 bundle
  // <prefix>/runtime/dist/<entry> it is <prefix>/install-record.json (also
  // next to the 999 launcher <prefix>/run-council.mjs).
  const entryDir = dirname(entryFile);
  return [
    join(entryDir, "..", "..", "install-record.json"),
    join(entryDir, "..", "install-record.json"),
    join(entryDir, "install-record.json"),
  ];
}

function readRecord(file) {
  const json = readJson(file);
  if (json && typeof json.skill_dir === "string" && json.skill_dir.length > 0) {
    const relative = !isAbsolute(json.skill_dir);
    return { recordPath: safeReal(file), skillDir: resolve(json.skill_dir), relativeSkillDir: relative, rawSkillDir: json.skill_dir };
  }
  return null;
}

function entryCandidatesForRecord(recordPath) {
  const dir = dirname(recordPath);
  for (const activeFile of [join(dir, "..", "active.json"), join(dir, "active.json")]) {
    const active = readJson(activeFile);
    if (active && typeof active.releasePath === "string") {
      const entry = join(active.releasePath, "dist", "blackceo-council.mjs");
      if (existsSync(entry)) return [entry];
    }
  }
  return [
    join(dir, "current", "run-council.mjs"),
    join(dir, "run-council.mjs"),
    join(dir, "runtime", "dist", "council-entry.mjs"),
    join(dir, "runtime", "dist", "blackceo-council.mjs"),
    join(dir, "dist", "blackceo-council.mjs"),
  ];
}

/** Paths a shell shim may exec, with $SELF_DIR / $PROFILE_ROOT / $HOME filled in. */
function shimEntryCandidates(shimFile, home) {
  let text = "";
  try {
    text = readFileSync(shimFile, "utf8");
  } catch {
    return [];
  }
  const selfDir = dirname(safeReal(shimFile));
  let profileRoot = "";
  const profileFile = join(selfDir, "blackceo-council.profile");
  try {
    profileRoot = readFileSync(profileFile, "utf8").split("\n")[0].trim();
  } catch {
    // default below
  }
  if (!profileRoot) {
    profileRoot = process.platform === "darwin"
      ? join(home, "Library", "Application Support", "BlackCEO", "WiseElders")
      : join(home, ".local", "share", "blackceo", "wise-elders");
  }
  const filled = text
    .replaceAll("$SELF_DIR", selfDir)
    .replaceAll("${SELF_DIR}", selfDir)
    .replaceAll("$PROFILE_ROOT", profileRoot)
    .replaceAll("${PROFILE_ROOT}", profileRoot)
    .replaceAll("$HOME", home)
    .replaceAll("${HOME}", home);
  const out = [];
  // quoted strings first (paths may contain spaces, e.g. "Application Support")
  for (const m of filled.matchAll(/(['"])(\/[^'"]*?\.(?:mjs|js))\1/g)) out.push(m[2]);
  for (const m of filled.matchAll(/(?:^|[\s=(])(\/[^\s'"()]*\.(?:mjs|js))/g)) out.push(m[1]);
  if (/\.(mjs|js)$/.test(shimFile)) out.push(shimFile);
  return out;
}

/**
 * All install-records this box can name, in resolver-priority order:
 * (1) the record the LIVE CLI executable actually consults, (2) the updater's
 * own prefix, (3) the data profile's `current` release (then its newest).
 * Historical releases' records are not live resolver state and are skipped.
 */
export function scanInstallRecords({ home, prefix } = {}) {
  const out = [];
  const push = (rec) => {
    if (rec && !out.some((r) => r.recordPath === rec.recordPath)) out.push(rec);
    return rec;
  };
  const fromEntry = (entry) => {
    if (!entry) return null;
    const real = safeReal(entry);
    for (const file of recordPathsNear(real)) {
      const rec = push(readRecord(file));
      if (rec) return rec;
    }
    return null;
  };
  // (1) the live executable
  for (const exe of [
    join(home, ".local", "bin", "blackceo-council"),
    join(home, ".npm-global", "bin", "blackceo-council"),
  ]) {
    if (!existsSync(exe)) continue;
    for (const entry of shimEntryCandidates(exe, home)) {
      const rec = fromEntry(entry);
      if (rec) return out; // the live executable's record wins outright
    }
  }
  // (2) the updater's own prefix
  if (prefix) {
    const p = resolve(prefix);
    for (const file of [join(p, "releases", "install-record.json"), join(p, "install-record.json")]) {
      const rec = push(readRecord(file));
      if (rec) return out;
    }
  }
  // (3) the data profile: `current` first, then the newest release
  for (const root of [
    join(home, "Library", "Application Support", "BlackCEO", "WiseElders", "runtime"),
    join(home, ".local", "share", "blackceo", "wise-elders", "runtime"),
  ]) {
    const ordered = [];
    const current = join(root, "current");
    if (existsSync(current)) ordered.push(current);
    const releases = listDir(root)
      .map((name) => join(root, name))
      .filter((p) => p !== current)
      .map((p) => {
        try {
          return { p, mtime: statSync(p).mtimeMs };
        } catch {
          return { p, mtime: 0 };
        }
      })
      .sort((a, b) => b.mtime - a.mtime)
      .map((x) => x.p);
    ordered.push(...releases);
    for (const dir of ordered) {
      const rec = push(readRecord(join(dir, "install-record.json"))) || push(readRecord(join(dir, "releases", "install-record.json")));
      if (rec) return out;
    }
  }
  return out;
}

// ------------------------------------------------------------ copy discovery
function loadTreeInfo(dir) {
  const physical = safeReal(dir);
  let kind = "directory";
  try {
    if (lstatSync(dir).isSymbolicLink()) kind = `symlink -> ${physical}`;
  } catch {
    // keep 'directory'
  }
  const manifest = readJson(join(dir, "manifest.json"));
  const recorded = manifest?.runtime_entry ?? null;
  const text = normalizedText(join(dir, "SKILL.md"));
  const versionEvidence = readVersionEvidence(dir);
  return {
    path: dir,
    physical,
    kind,
    version: versionEvidence.version,
    versionSources: versionEvidence.sources,
    versionProblems: versionEvidence.problems,
    hasManifest: !!manifest,
    hasArchive: existsSync(join(dir, `${SKILL_NAME}.skill`)),
    runtimeEntry: recorded,
    executableOnDisk: recorded ? existsSync(join(dir, recorded.path)) : null,
    staleContract: STALE_CONTRACT_PHRASES.some((p) => text.includes(p)),
    carriesContractMarker: text.includes(CURRENT_CONTRACT_MARKER),
  };
}

/** Every council-of-wise-elders copy in the known skill roots (+ explicit dirs). */
export function inspectCopies({ home, claudeConfigDir, openclawRoot, extraDirs = [], extraRoots = [] } = {}) {
  const roots = [
    join(claudeConfigDir ?? join(home, ".claude"), "skills"),
    join(home, ".claude", "skills"),
    join(home, ".claude-nine", "skills"),
    join(home, ".codex", "skills"),
    join(home, ".agents", "skills"),
    join(openclawRoot ?? join(home, ".openclaw"), "skills"),
    ...extraRoots.map((r) => join(r, "skills")),
  ];
  const dirs = [...extraDirs];
  for (const root of roots) {
    for (const name of [SKILL_NAME, `77-${SKILL_NAME}`]) dirs.push(join(root, name));
  }
  const copies = [];
  const seen = new Set();
  for (const dir of dirs) {
    if (!existsSync(dir)) continue;
    const physical = safeReal(dir);
    if (seen.has(physical)) continue;
    seen.add(physical);
    copies.push(loadTreeInfo(dir));
  }
  return copies;
}

// ------------------------------------------------------------------ selection
/**
 * The copy the runtime resolver selects: agent-resolver evidence when the
 * caller supplies it (the only proof of what the intended OpenClaw agent
 * actually reads), then the install-record the live CLI consults, then the
 * install-time resolver order. A record or a fallback directory is a candidate,
 * not proof of agent selection.
 */
export function resolveSelection({ home, claudeConfigDir, openclawRoot, prefix, skillDir, records, agentSelected, agentSource } = {}) {
  if (agentSelected) {
    const abs = resolve(agentSelected);
    const source = agentSource ? ` (${agentSource})` : "";
    if (!isSkillFolder(abs)) {
      return {
        selectedPath: null,
        via: `agent-resolver${source}`,
        problems: [
          `the agent resolver reports ${abs}${source} but that path is not a ${SKILL_NAME} skill folder ` +
          `(needs ${SIGNATURE.join(", ")}): the agent selection evidence is unusable`,
        ],
      };
    }
    return { selectedPath: safeReal(abs), via: `agent-resolver${source}`, problems: [] };
  }
  const found = records ?? scanInstallRecords({ home, prefix });
  if (found.length >= 1) {
    return { selectedPath: found[0].skillDir, via: `install-record ${found[0].recordPath} (not agent evidence)`, problems: [] };
  }
  // No record: the install-time resolver order (council-runtime-install.sh /
  // install.sh candidate lists), then the tree being wired.
  const candidates = [
    join(claudeConfigDir ?? join(home, ".claude"), "skills", SKILL_NAME),
    join(home, ".claude", "skills", SKILL_NAME),
    join(home, ".claude-nine", "skills", SKILL_NAME),
  ];
  if (skillDir) candidates.push(resolve(skillDir));
  for (const cand of candidates) {
    if (isSkillFolder(cand)) {
      return { selectedPath: safeReal(cand), via: "resolver fallback walk", problems: [] };
    }
  }
  return {
    selectedPath: null,
    via: null,
    problems: [
      `no ${SKILL_NAME} copy is selectable: no install-record and no skill-signature folder in the resolver order ` +
      `(${candidates.join(", ")})`,
    ],
  };
}

// ---------------------------------------------------------------- the checks
function executableStatus(copy, records) {
  if (copy.runtimeEntry && copy.executableOnDisk) return "packaged";
  if (copy.hasArchive) return "archive";
  const rec = records.find((r) => samePath(r.skillDir, copy.physical));
  if (rec) {
    const entries = entryCandidatesForRecord(rec.recordPath);
    return entries.some((e) => existsSync(e)) ? "installed" : "record-without-entry";
  }
  return copy.runtimeEntry ? "packaged-missing-entry" : "source-only";
}

/**
 * An entry path that exists is not a valid artifact. Require a non-empty
 * JavaScript file and, when `load` is on, a real `node --check` parse. Cheap,
 * offline, no provider call.
 */
function verifyEntryFile(entry, { load }) {
  const problems = [];
  let st;
  try {
    st = statSync(entry);
  } catch {
    return [`entry ${entry} does not exist`];
  }
  if (!st.isFile()) return [`entry ${entry} is not a regular file`];
  if (st.size === 0) return [`entry ${entry} is empty: an existing path is not a valid artifact`];
  let head = "";
  try {
    head = readFileSync(entry, "utf8").slice(0, 400);
  } catch (e) {
    problems.push(`entry ${entry} is unreadable: ${String(e.message).split("\n")[0]}`);
    return problems;
  }
  // A shebang alone is not JavaScript: a shell script starts with "#!" too.
  const firstLine = head.split("\n")[0] ?? "";
  const nodeShebang = /^#!.*\bnode(\.exe)?\b/.test(firstLine);
  const jsTokens = /\b(import|export|const|let|var|function|class|process)\b/.test(head);
  if (!nodeShebang && !jsTokens) {
    problems.push(`entry ${entry} does not look like a JavaScript entry point (shebang: "${firstLine.slice(0, 60)}")`);
  }
  if (load) {
    try {
      execFileSync(process.execPath, ["--check", entry], { stdio: "pipe" });
    } catch (e) {
      const detail = String(e.stderr ?? e.message).split("\n").find((l) => l.trim()) ?? "parse failed";
      problems.push(`entry ${entry} fails node --check: ${detail.trim()}`);
    }
  }
  return problems;
}

/**
 * A .skill archive must actually be a zip that carries the entry. Existence,
 * size or a filename is not proof.
 */
function verifyArchive(copy, { load }) {
  const archive = join(copy.physical, `${SKILL_NAME}.skill`);
  let st;
  try {
    st = statSync(archive);
  } catch {
    return [`archive ${archive} is unreadable`];
  }
  if (!st.isFile() || st.size === 0) return [`archive ${archive} is empty`];
  try {
    const fd = openSync(archive, "r");
    const magic = Buffer.alloc(4);
    readSync(fd, magic, 0, 4, 0);
    closeSync(fd);
    if (!(magic[0] === 0x50 && magic[1] === 0x4b)) return [`archive ${archive} is not a zip archive`];
  } catch (e) {
    return [`archive ${archive} is unreadable: ${String(e.message).split("\n")[0]}`];
  }
  let listing;
  try {
    listing = execFileSync("unzip", ["-Z1", archive], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  } catch (e) {
    if (e && e.code === "ENOENT") return [`archive ${archive}: cannot verify contents (unzip unavailable)`];
    return [`archive ${archive} cannot be listed: ${String(e.message).split("\n")[0]}`];
  }
  const entry = copy.runtimeEntry?.path ?? ENTRY_PATH;
  const wanted = entry.split(/[\\/]/).pop();
  const member = listing
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.endsWith(entry) || (wanted && line.endsWith(wanted)));
  if (!member) return [`archive ${archive} does not contain the executable ${entry}`];
  // A member NAME in the listing is not the artifact: extract it and validate
  // the bytes (non-empty, JavaScript, and node --check when loading is on).
  let tmpDir;
  try {
    tmpDir = mkdtempSync(join(tmpdir(), "council-archive-"));
    const out = join(tmpDir, "entry.mjs");
    const bytes = execFileSync("unzip", ["-p", archive, member], { maxBuffer: 64 * 1024 * 1024 });
    writeFileSync(out, bytes);
    const problems = verifyEntryFile(out, { load });
    const recorded = copy.runtimeEntry;
    if (!recorded || !recorded.sha256) {
      problems.push(`archive ${archive} carries no recorded runtime_entry hash, so the archived executable cannot be tied to a build`);
    } else {
      const sha = createHash("sha256").update(bytes).digest("hex");
      if (sha !== recorded.sha256 || bytes.length !== recorded.bytes) {
        problems.push(
          `archive member ${member} is sha256 ${sha} (${bytes.length} bytes) but manifest.json records ` +
          `${recorded.sha256} (${recorded.bytes} bytes): the archived executable is not the recorded build`,
        );
      }
    }
    return problems.map((p) => `archive member ${member}: ${p}`);
  } catch (e) {
    return [`archive member ${member} could not be extracted: ${String(e.message).split("\n")[0]}`];
  } finally {
    if (tmpDir) rmSync(tmpDir, { recursive: true, force: true });
  }
}

/** The installed release named by a record must carry a valid, non-empty entry. */
function verifyInstalledEntry(rec, { load }) {
  const entries = entryCandidatesForRecord(rec.recordPath);
  if (!entries.length) return [`the installed release named by ${rec.recordPath} has no executable entry candidate`];
  const perEntry = entries.map((e) => ({ e, problems: verifyEntryFile(e, { load }) }));
  if (perEntry.some((x) => x.problems.length === 0)) return [];
  return perEntry.flatMap((x) => x.problems);
}

/**
 * A record is a promise about a release. Verify the release entry it can
 * reach, not only the skill tree: a live record pointing at a release whose
 * entry is a directory or empty means the CLI cannot run at all.
 */
function verifyRecordRelease(rec, { load }) {
  const dir = dirname(rec.recordPath);
  const releasesDir = dir.endsWith(`${sep}releases`) ? dir : join(dir, "releases");
  const activeFiles = [join(dir, "..", "active.json"), join(dir, "active.json")];
  let releasePath = null;
  for (const file of activeFiles) {
    const active = readJson(file);
    if (active && typeof active.releasePath === "string") {
      releasePath = active.releasePath;
      break;
    }
  }
  const candidates = [];
  if (releasePath) {
    candidates.push(join(releasePath, "dist", "blackceo-council.mjs"));
  } else {
    let releases = [];
    try {
      releases = readdirSync(releasesDir, { withFileTypes: true })
        .filter((e) => e.isDirectory())
        .map((e) => join(releasesDir, e.name, "dist", "blackceo-council.mjs"))
        .filter((p) => existsSync(p));
    } catch {
      releases = [];
    }
    candidates.push(...releases);
    if (!candidates.length) candidates.push(...entryCandidatesForRecord(rec.recordPath));
  }
  if (!candidates.length) {
    return [`the install-record ${rec.recordPath} names no reachable release entry (no active.json releasePath and no releases/*/dist entry): a record that promises a release must be able to name one`];
  }
  const perEntry = candidates.map((e) => ({ e, problems: verifyEntryFile(e, { load }) }));
  if (perEntry.some((x) => x.problems.length === 0)) return [];
  return perEntry.flatMap((x) => x.problems).map((p) => `the release named by ${rec.recordPath}: ${p}`);
}

const sha256File = (file) => {
  try {
    return createHash("sha256").update(readFileSync(file)).digest("hex");
  } catch {
    return "missing";
  }
};

/**
 * Full-tree identity: every regular file (path + content hash) and every
 * symlink (path + target), skipping only generated dependency/cache trees.
 * Equal versions are not equal releases unless this digest matches.
 */
function treeIdentity(dir) {
  const lines = [];
  const walk = (rel) => {
    let entries;
    try {
      entries = readdirSync(join(dir, rel), { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries.sort((x, y) => x.name.localeCompare(y.name))) {
      if (e.name === "node_modules" || e.name === ".git" || e.name === "__pycache__") continue;
      const r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isSymbolicLink()) {
        let target = "broken";
        try { target = realpathSync(join(dir, r)); } catch { /* keep broken */ }
        lines.push(`${r}\tlink:${target}`);
      } else if (e.isDirectory()) {
        walk(r);
      } else if (e.isFile()) {
        lines.push(`${r}\t${sha256File(join(dir, r))}`);
      }
    }
  };
  walk("");
  return `${createHash("sha256").update(lines.join("\n")).digest("hex")}:${lines.length}`;
}

/**
 * Full gate. Returns {ok, selectionProven, agentSelected, problems, warnings, selected, copies, records}.
 * `load` runs the entry-point smoke load (node --check + --help); hash and
 * byte comparison always run for packaged artifacts.
 */
export function checkSelectedTree(opts = {}) {
  const home = opts.home ?? homedir();
  const claudeConfigDir = opts.claudeConfigDir ?? null;
  const openclawRoot = opts.openclawRoot ?? null;
  const prefix = opts.prefix ?? null;
  const skillDir = opts.skillDir ? resolve(opts.skillDir) : null;
  const load = opts.load !== false;
  const agentSelected = opts.agentSelected ? resolve(opts.agentSelected) : null;
  const agentSource = opts.agentSource ?? null;
  const problems = [];
  const warnings = [];

  const records = scanInstallRecords({ home, prefix });
  const selection = resolveSelection({ home, claudeConfigDir, openclawRoot, prefix, skillDir, records, agentSelected, agentSource });
  problems.push(...selection.problems);
  for (const rec of records) {
    if (rec.relativeSkillDir) {
      problems.push(
        `the install-record ${rec.recordPath} records a relative skill_dir ("${rec.rawSkillDir}"): ` +
        `a relative path resolves against whatever directory the verifier runs in, so it cannot name a tree — ` +
        `repair the record with an absolute path`,
      );
    }
    problems.push(...verifyRecordRelease(rec, { load }));
  }
  // Pin the physical targets once: a symlink retargeted mid-run must never be
  // verified as if it were the tree that was checked at the start.
  const pinnedSelection = selection.selectedPath ? safeReal(selection.selectedPath) : null;
  const pinnedSkillDir = skillDir ? safeReal(skillDir) : null;

  const discoveredCopies = inspectCopies({
    home,
    claudeConfigDir,
    openclawRoot,
    extraDirs: skillDir ? [skillDir] : [],
  });
  const copies = [...discoveredCopies];

  let selected = selection.selectedPath ? copies.find((c) => samePath(c.physical, selection.selectedPath)) : null;
  if (selection.selectedPath && !selected) {
    // The resolver selected a tree outside every known root: verify it anyway.
    if (existsSync(selection.selectedPath)) {
      selected = loadTreeInfo(selection.selectedPath);
      copies.push(selected);
    } else {
      problems.push(
        `the resolver selects ${selection.selectedPath} but that tree does not exist; ` +
        `the selected copy is gone`,
      );
    }
  }

  const canonicalEvidence = opts.canonicalVersion
    ? { version: opts.canonicalVersion, problems: [] }
    : skillDir
      ? readVersionEvidence(skillDir)
      : { version: null, problems: [] };
  const canonicalVersion = canonicalEvidence.version;
  problems.push(...canonicalEvidence.problems.map((p) => `the tree this update maintains: ${p}`));

  // Selection proof: one copy is unambiguous; more than one needs agent evidence.
  const selectionProven = Boolean(agentSelected) || copies.length <= 1;
  if (!selectionProven) {
    problems.push(
      `agent selection unproven: ${copies.length} ${SKILL_NAME} copies exist on this box ` +
      `(${copies.map((c) => `${c.path}@${c.version ?? "version-unknown"}`).join(", ")}) and no agent-resolver evidence ` +
      `names the one the intended OpenClaw agent reads; an install-record or a fallback directory is not proof — ` +
      `pass --agent-selected PATH from the agent resolver, or report this as UNKNOWN`,
    );
  }
  // Agent evidence is not a free pass: it must not contradict the record the
  // live CLI consults, and it must name a copy this box can actually see.
  if (agentSelected) {
    if (records.length) {
      const agrees = records.some((r) => samePath(r.skillDir, agentSelected));
      if (!agrees) {
        problems.push(
          `agent evidence names ${agentSelected} but the live install-record(s) name ` +
          `${records.map((r) => r.skillDir).join(", ")}: the two disagree, so neither proves what the agent reads — ` +
          `reconcile the resolver state before any update or gate can pass`,
        );
      }
    } else if (!discoveredCopies.some((c) => samePath(c.physical, agentSelected) || samePath(c.path, agentSelected))) {
      problems.push(
        `agent evidence names ${agentSelected}, which is not a ${SKILL_NAME} copy under any known agent root: ` +
        `the evidence is unverifiable`,
      );
    }
  }

  if (selected) {
    problems.push(...selected.versionProblems.map((p) => `SELECTED copy: ${p}`));
    // (a) the selected copy must be the version this update ships
    if (canonicalVersion && selected.version !== canonicalVersion) {
      problems.push(
        `the copy the resolver selects is ${selected.path} at version ${selected.version ?? "unknown"} ` +
        `while this update ships ${canonicalVersion}: the updater would be updating only an unused directory`,
      );
    }
    // (e) the convene contract, as text the selected tree actually carries
    const text = normalizedText(join(selected.physical, "SKILL.md"));
    for (const phrase of STALE_CONTRACT_PHRASES) {
      if (text.includes(phrase)) {
        problems.push(
          `stale instruction text in the SELECTED copy ${selected.path}: "${phrase}" — ` +
          `upgrades carry the current convene contract (convening is approval, no grant)`,
        );
      }
    }
    if (!text.includes(CURRENT_CONTRACT_MARKER)) {
      problems.push(
        `the SELECTED copy ${selected.path} does not carry the current convene contract ` +
        `("${CURRENT_CONTRACT_MARKER}"): convening is approval, no grant is resolved`,
      );
    }
    // (c)+(d) the selected artifact must ship a verifiable executable
    const state = executableStatus(selected, records);
    if (state === "packaged") {
      const manifest = readJson(join(selected.physical, "manifest.json"));
      const gate = checkEntryPoint(selected.physical, manifest, { load });
      if (!gate.ok) problems.push(...gate.problems.map((p) => `SELECTED copy ${selected.path}: ${p}`));
    } else if (state === "packaged-missing-entry") {
      problems.push(
        `SELECTED artifact ${selected.path} records runtime_entry ${selected.runtimeEntry.path} ` +
        `but does not ship it (no runtime/dist entry, no archive, no installed release): ` +
        `every shipped artifact includes its executable`,
      );
    } else if (state === "record-without-entry") {
      problems.push(
        `the install-record naming ${selected.path} points at a release with no executable entry; ` +
        `the resolver-selected copy is unusable`,
      );
    } else if (state === "source-only") {
      problems.push(
        `source-only artifact at ${selected.path}: no runtime/dist entry, no manifest runtime_entry, ` +
        `no archive, and no installed release naming this tree — every shipped artifact includes its executable`,
      );
    } else if (state === "archive") {
      problems.push(...verifyArchive(selected, { load }).map((p) => `SELECTED copy ${selected.path}: ${p}`));
    } else if (state === "installed") {
      const rec = records.find((r) => samePath(r.skillDir, selected.physical));
      if (!rec) {
        problems.push(`the selected copy ${selected.path} was classified installed without a matching install-record`);
      } else {
        problems.push(...verifyInstalledEntry(rec, { load }).map((p) => `SELECTED copy ${selected.path}: ${p}`));
      }
    }
    // "archive" (executable ships inside the .skill archive) and "installed"
    // (a release named by the resolver's own install-record carries it) both
    // satisfy the shipped-executable rule.
    if (skillDir && !samePath(selected.physical, skillDir)) {
      const selectedIdentity = treeIdentity(selected.physical);
      const maintainedIdentity = treeIdentity(skillDir);
      if (selectedIdentity !== maintainedIdentity) {
        problems.push(
          `the selected copy ${selected.path} and the tree this update maintains ${skillDir} ` +
          (selected.version && selected.version === canonicalVersion
            ? `both claim ${selected.version} `
            : "") +
          `but their trees differ (selected ${selectedIdentity} vs maintained ${maintainedIdentity}): ` +
          `an update that wrote any other file must not report success`,
        );
      }
      warnings.push(
        `the resolver selects ${selected.path} (via ${selection.via}) while this update maintains ${skillDir}; ` +
        `the selected copy is verified above and is NOT the directory being written`,
      );
    }
  }

  // (b) every competing copy: detected and reported loudly, never equated
  for (const copy of copies) {
    if (selected && samePath(copy.physical, selected.physical)) continue;
    const state = executableStatus(copy, records);
    const flags = [
      `version=${copy.version ?? "unknown"}`,
      `entry=${state}`,
      copy.staleContract ? "STALE-CONTRACT-TEXT" : "contract-text=ok",
      copy.hasArchive ? "archive=yes" : "archive=no",
    ].join(" ");
    warnings.push(
      `DUPLICATE ${SKILL_NAME} at ${copy.path} (${copy.kind}) ${flags} — ` +
      `NOT what the resolver selects${copy.staleContract ? "; stale grant instruction text must not survive here" : ""}`,
    );
    if (selected && copy.version && selected.version && copy.version !== selected.version) {
      warnings.push(
        `CONFLICT: ${copy.path} is at version ${copy.version} while the selected copy ${selected.path} ` +
        `is at ${selected.version}`,
      );
    }
  }

  // A symlink that moved while it was being checked cannot be verified.
  for (const pinned of [
    { label: "the resolver-selected path", path: selection.selectedPath, real: pinnedSelection },
    { label: "the tree this update maintains", path: skillDir, real: pinnedSkillDir },
  ]) {
    if (!pinned.path || !pinned.real) continue;
    const now = safeReal(pinned.path);
    if (now !== pinned.real) {
      problems.push(
        `${pinned.label} ${pinned.path} changed target during verification (${pinned.real} -> ${now}): ` +
        `a moving symlink cannot be verified`,
      );
    }
  }

  return {
    ok: problems.length === 0,
    selectionProven,
    agentSelected,
    problems,
    warnings,
    selected: selected ? { ...selected, via: selection.via } : null,
    selectedPath: selection.selectedPath,
    via: selection.via,
    copies,
    records,
  };
}

// ----------------------------------------------------------------------- CLI
function parseArgs(argv) {
  const out = { skillDir: null, prefix: null, home: null, load: true, agentSelected: null, agentSource: null };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    const next = argv[i + 1];
    if (a === "--skill-dir" && next) { out.skillDir = next; i += 1; }
    else if (a === "--prefix" && next) { out.prefix = next; i += 1; }
    else if (a === "--home" && next) { out.home = next; i += 1; }
    else if (a === "--agent-selected" && next) { out.agentSelected = next; i += 1; }
    else if (a === "--agent-source" && next) { out.agentSource = next; i += 1; }
    else if (a === "--no-load") { out.load = false; }
    else return null;
  }
  return out;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = parseArgs(process.argv.slice(2));
  if (!args || !args.skillDir) {
    console.log("usage: node scripts/selected-tree-gate.mjs --skill-dir DIR [--prefix DIR] [--home DIR] [--no-load] [--agent-selected PATH] [--agent-source TEXT]");
    process.exit(2);
  }
  const result = checkSelectedTree({
    home: args.home ?? homedir(),
    skillDir: args.skillDir,
    prefix: args.prefix,
    load: args.load,
    agentSelected: args.agentSelected,
    agentSource: args.agentSource,
  });
  for (const p of result.problems) console.log(`  ✗ ERROR: ${p}`);
  for (const w of result.warnings) console.log(`  ⚠️  ${w}`);
  console.log(
    `SELECTED-TREE: ${result.ok ? "OK" : "FAIL"} selected=${result.selectedPath ?? "<none>"} ` +
    `via=${result.via ?? "<none>"} copies=${result.copies.length}`,
  );
  process.exit(result.ok ? 0 : 1);
}
