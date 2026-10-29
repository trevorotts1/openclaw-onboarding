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
import {
  DISTRIBUTION_KINDS,
  HASH_METHOD,
  aggregateEntries,
  treeAudit,
} from "./manifest-tree.mjs";

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

const HEX64 = /^[0-9a-f]{64}$/;

/** True when the tree presents itself as a distribution of a canonical tree. */
export function isDistributionCandidate(dir) {
  const manifest = readJson(join(dir, "manifest.json"));
  return existsSync(join(dir, "DISTRIBUTION-RECONCILIATION.json"))
    || Boolean(manifest && typeof manifest.canonical_aggregate_sha256 === "string");
}

// ------------------------------------------------------- distribution proof
const byPath = (entries) => new Map(entries.map((f) => [f.path, f.sha256]));

/** {aggregate, fileCount} over already-audited entries, one formula. */
const treeAggregateFrom = (entries) => ({ aggregate: aggregateEntries(entries), fileCount: entries.length });

/** Every path and digest of `expected` must appear identically in `actual`. */
function missingOrDrifting(expected, actual) {
  const have = byPath(actual);
  const drifting = [];
  for (const f of expected) {
    if (!have.has(f.path)) drifting.push(`${f.path} (missing)`);
    else if (have.get(f.path) !== f.sha256) drifting.push(`${f.path} (recomputed ${have.get(f.path)}, recorded ${f.sha256})`);
  }
  return drifting;
}

function isEntryList(list) {
  return Array.isArray(list) && list.every((f) => f && typeof f.path === "string" && typeof f.sha256 === "string" && HEX64.test(f.sha256));
}

/** The reconciliation record, parsed and checked against the canonical tree. */
function reconcileRecord(dir, { maintainedManifest, maintainedAggregate, maintainedFileCount, addedPaths, contentDiffs, maintainedHasArchive }) {
  const record = readJson(join(dir, "DISTRIBUTION-RECONCILIATION.json"));
  if (!record) return { problems: [`the selected copy ${dir} carries no DISTRIBUTION-RECONCILIATION.json (or it is unreadable): a distribution records every difference from the canonical tree`] };
  const problems = [];
  const source = record.canonical_source ?? {};
  if (source.canonical_aggregate_sha256 !== maintainedAggregate) {
    problems.push(
      `its record names the canonical source ${source.canonical_aggregate_sha256 ?? "(none)"} but the maintained tree's canonical aggregate is ` +
      `${maintainedAggregate}: the record describes a DIFFERENT canonical release`,
    );
  }
  if (source.canonical_file_count !== undefined && source.canonical_file_count !== maintainedFileCount) {
    problems.push(`its record names canonical_file_count ${source.canonical_file_count} but the maintained tree has ${maintainedFileCount} files`);
  }
  const declared = Array.isArray(record.intentional_distribution_differences) ? record.intentional_distribution_differences : null;
  if (!declared) return { problems: [...problems, "its record carries no intentional_distribution_differences list, so it declares nothing it can be held to"] };
  for (const d of declared) {
    if (!d || typeof d.kind !== "string") problems.push("its record lists a distribution difference with no kind");
    else if (!DISTRIBUTION_KINDS.includes(d.kind)) problems.push(`its record declares the unprovable difference kind "${d.kind}"`);
  }
  const kinds = new Set(declared.map((d) => d?.kind).filter(Boolean));
  // Each declared kind must be one the canonical release allows.
  const allowed = new Set(Array.isArray(maintainedManifest.distribution?.kinds) ? maintainedManifest.distribution.kinds : []);
  for (const k of kinds) if (!allowed.has(k)) problems.push(`it declares the difference kind "${k}", which the canonical manifest does not allow`);

  const named = new Set();
  for (const d of declared) {
    if (!d || typeof d !== "object") continue;
    if (d.kind === "private_scope_items_dropped" || d.kind === "sentences_scrubbed") {
      // Content-change kinds must name the files whose content actually moved.
      const files = [d.file, ...(Array.isArray(d.items) ? d.items.map((i) => i?.file) : []), ...(Array.isArray(d.fields) ? d.fields.map((i) => i?.file) : [])];
      for (const f of files) if (typeof f === "string") named.add(f);
    }
    if (d.kind === "manifest_regenerated" && d.file !== undefined && d.file !== "manifest.json") {
      problems.push(`it records ${d.file} as the regenerated manifest, but a distribution regenerates manifest.json`);
    }
    if (d.kind === "generated_archive_not_vendored") {
      const recorded = maintainedManifest.archive?.sha256 ?? null;
      if (d.archive_sha256 !== undefined && d.archive_sha256 !== recorded) {
        problems.push(`it records the canonical archive as ${d.archive_sha256} but the maintained manifest records ${recorded ?? "(none)"}`);
      }
      if (typeof d.file === "string" && existsSync(join(dir, d.file))) {
        problems.push(`it records ${d.file} as not vendored, but the selected copy carries it`);
      }
    }
    if (d.kind === "file_added" && typeof d.file === "string" && !addedPaths.includes(d.file)) {
      problems.push(`it records ${d.file} as added, but the canonical manifest's added_paths do not name it`);
    }
  }
  // A record that names a file it did not change is a lie about the difference.
  for (const f of named) {
    if (!contentDiffs.has(f)) problems.push(`it records ${f} as a distribution difference, but that file is byte-identical to the canonical copy`);
  }
  for (const f of contentDiffs.keys()) {
    if (!named.has(f)) problems.push(`the selected copy differs from the canonical copy at ${f}, which the reconciliation record never declares`);
  }
  // The kinds present must be the kinds the observed packaging requires.
  if (addedPaths.length && !kinds.has("file_added")) problems.push("the selected copy adds files but the record does not declare file_added");
  if (contentDiffs.size && !(kinds.has("sentences_scrubbed") || kinds.has("private_scope_items_dropped"))) {
    problems.push("the selected copy changes canonical file content but the record declares neither sentences_scrubbed nor private_scope_items_dropped");
  }
  if (!kinds.has("manifest_regenerated")) problems.push("the record does not declare manifest_regenerated, yet every distribution regenerates its manifest");
  if (maintainedHasArchive && !kinds.has("generated_archive_not_vendored")) {
    problems.push("the canonical tree carries a generated archive the distribution does not vendor, but the record does not declare generated_archive_not_vendored");
  }
  return { problems };
}

/**
 * Proof that two trees whose identities DIFFER are nevertheless the SAME
 * RELEASE: the selected copy is the 999 distribution of the canonical tree
 * this update maintains.
 *
 * The witness is never the selected copy. The selected copy is the unit under
 * test; anything it says about itself is only a claim. Every accepted fact
 * therefore comes from the maintained tree's manifest — the release this
 * update wrote — and every fact claimed by the selected copy is checked
 * against that witness:
 *   (a) the maintained manifest records a distribution contract
 *       {kinds, files, runtime_dist, added_paths}: the canonical release
 *       declares, in advance, exactly what its distributable form looks like;
 *   (b) the maintained tree recomputes to its own manifest, per file
 *       (aggregate, count AND the recorded per-file digests), so the witness
 *       is truthful about the tree in front of us;
 *   (c) the selected tree recomputes to its own manifest, per file, with no
 *       symlinks, unreadable entries, unshipped dependency trees or
 *       unaccounted archives;
 *   (d) every file the witness records is byte-identical in the selected copy,
 *       and every file the selected copy carries beyond that is a declared
 *       added path — so no file, executable or not, is taken on trust;
 *   (e) the vendored build is a byte-identical subset of the build the
 *       canonical manifest records, and the executable it presents is exactly
 *       the executable the canonical manifest records;
 *   (f) the reconciliation record is parsed and held to the witness: its
 *       canonical aggregate, its declared kinds and its named files must all
 *       match what was actually observed;
 *   (g) both copies claim the same version (carrier agreement, read above),
 *       and the selected copy passed its executable checks.
 * Every other mismatch is refused with a reason naming the failed link.
 * Returns {ok: true, aggregate, canonicalPath, files, distFiles} or
 * {ok: false, reason}.
 */
export function proveSameRelease({
  selectedDir,
  maintainedDir,
  selectedVersion,
  maintainedVersion,
  entryChecksPassed = true,
} = {}) {
  const refuse = (reason) => ({ ok: false, reason });

  // --- the witness: the release this update maintains ---------------------
  const canonicalManifest = readJson(join(maintainedDir, "manifest.json"));
  if (!canonicalManifest) return refuse(`the maintained tree ${maintainedDir} has no readable manifest.json to compare against`);
  const witness = canonicalManifest.distribution;
  if (!witness || typeof witness !== "object" || Array.isArray(witness)) {
    return refuse(
      `the maintained manifest records no distribution contract (distribution {kinds, files, runtime_dist, added_paths}), ` +
      `so it cannot witness a distribution of itself`,
    );
  }
  if (!Array.isArray(witness.kinds) || witness.kinds.length === 0) {
    return refuse(`the maintained manifest records no allowed distribution difference kinds`);
  }
  const unprovableKinds = witness.kinds.filter((k) => typeof k !== "string" || !DISTRIBUTION_KINDS.includes(k));
  if (unprovableKinds.length) {
    return refuse(
      `the maintained manifest declares distribution difference kinds this gate cannot prove ` +
      `(${unprovableKinds.join(", ")}): only ${DISTRIBUTION_KINDS.join(", ")} are provable`,
    );
  }
  if (!isEntryList(witness.files) || witness.files.length === 0) {
    return refuse(`the maintained manifest records no per-file distribution map (distribution.files), so no distribution file can be proven`);
  }
  if (!isEntryList(witness.runtime_dist) || witness.runtime_dist.length === 0) {
    return refuse(`the maintained manifest records no built runtime map (distribution.runtime_dist), so no vendored executable can be proven`);
  }
  const addedPaths = Array.isArray(witness.added_paths) ? witness.added_paths.filter((p) => typeof p === "string") : [];
  if ((witness.added_paths ?? []).length !== addedPaths.length) {
    return refuse(`the maintained manifest's distribution.added_paths holds entries that are not paths`);
  }
  if (!isEntryList(canonicalManifest.files) || canonicalManifest.files.length === 0) {
    return refuse(`the maintained manifest records no per-file digest map of the canonical tree, so its aggregate cannot be tied to content`);
  }
  const recordedEntry = canonicalManifest.runtime_entry;
  if (!recordedEntry || typeof recordedEntry.sha256 !== "string" || !HEX64.test(recordedEntry.sha256)) {
    return refuse(`the maintained manifest records no runtime_entry (path + sha256), so no vendored executable can be checked against the release`);
  }

  // --- the witness must be truthful about the tree in front of us ---------
  const canonicalAudit = treeAudit(maintainedDir);
  if (canonicalAudit.problems.length) {
    const p = canonicalAudit.problems[0];
    return refuse(`the maintained tree ${maintainedDir} cannot be verified: ${p.path} ${p.reason}`);
  }
  const canonicalTree = treeAggregateFrom(canonicalAudit.entries);
  if (canonicalTree.aggregate !== canonicalManifest.aggregate_sha256 || canonicalTree.fileCount !== canonicalManifest.file_count) {
    return refuse(
      `the maintained tree ${maintainedDir} is not the tree its own manifest records ` +
      `(recomputed ${canonicalTree.aggregate} over ${canonicalTree.fileCount} files, manifest ${canonicalManifest.aggregate_sha256} over ${canonicalManifest.file_count})`,
    );
  }
  const canonicalDrift = missingOrDrifting(canonicalManifest.files, canonicalAudit.entries);
  if (canonicalDrift.length) {
    return refuse(
      `the maintained tree ${maintainedDir} is not the tree its own manifest records per file ` +
      `(${canonicalDrift.slice(0, 3).join("; ")}): the canonical per-file witness is not truthful`,
    );
  }
  // When the maintained tree carries the build it recorded, that record must
  // describe it exactly; an installed tree may ship only the archive, in which
  // case the recorded build is the packaging machine's build.
  if (canonicalAudit.dist.length) {
    const distDrift = missingOrDrifting(witness.runtime_dist, canonicalAudit.dist);
    const unrecorded = canonicalAudit.dist.filter((f) => !witness.runtime_dist.some((r) => r.path === f.path));
    if (distDrift.length || unrecorded.length) {
      return refuse(
        `the maintained tree's built runtime at ${maintainedDir} is not the build its manifest records ` +
        `(${distDrift.concat(unrecorded.map((f) => `${f.path} (unrecorded)`)).slice(0, 3).join("; ")})`,
      );
    }
  }

  // --- the selected copy: claims first, then content ----------------------
  const distManifest = readJson(join(selectedDir, "manifest.json"));
  if (!distManifest) return refuse(`the selected copy ${selectedDir} has no readable manifest.json, so it cannot prove what it packages`);
  if (typeof distManifest.canonical_aggregate_sha256 !== "string" || !HEX64.test(distManifest.canonical_aggregate_sha256)) {
    return refuse(`the selected copy ${selectedDir} records no valid canonical_aggregate_sha256 in its manifest`);
  }
  if (typeof distManifest.hash_method !== "string" || !distManifest.hash_method.trim()) {
    return refuse(`the selected copy ${selectedDir} records no hash_method, so its aggregate cannot be recomputed`);
  }
  if (distManifest.hash_method !== HASH_METHOD) {
    return refuse(
      `the selected copy ${selectedDir} records hash_method "${distManifest.hash_method}", which this gate cannot recompute: ` +
      `an aggregate is only meaningful under the method it names, and only the canonical manifest hash method is implemented`,
    );
  }
  if (!isEntryList(distManifest.files) || distManifest.files.length === 0) {
    return refuse(`the selected copy ${selectedDir} records no per-file digest map, so its aggregate cannot be tied to content`);
  }
  if (!selectedVersion || selectedVersion !== maintainedVersion) {
    return refuse(
      `versions differ (selected ${selectedVersion ?? "unknown"} vs maintained ${maintainedVersion ?? "unknown"}): ` +
      `packaging of one release cannot carry another release's version`,
    );
  }
  if (distManifest.canonical_aggregate_sha256 !== canonicalManifest.aggregate_sha256) {
    return refuse(
      `the distribution records canonical aggregate ${distManifest.canonical_aggregate_sha256} but the maintained tree is ` +
      `${canonicalManifest.aggregate_sha256}: they are packaging of DIFFERENT canonical releases`,
    );
  }
  // The record is checked for existence and its canonical claim before any tree
  // work, so a distribution that is missing or lying about its source is refused
  // for THAT reason and not for a downstream count.
  const record = readJson(join(selectedDir, "DISTRIBUTION-RECONCILIATION.json"));
  if (!record) {
    return refuse(
      `the selected copy ${selectedDir} carries no DISTRIBUTION-RECONCILIATION.json (or it is unreadable): ` +
      `a distribution records every difference from the canonical tree`,
    );
  }
  const recordSource = record.canonical_source ?? {};
  if (recordSource.canonical_aggregate_sha256 !== canonicalManifest.aggregate_sha256) {
    return refuse(
      `the reconciliation record of ${selectedDir} names the canonical source ${recordSource.canonical_aggregate_sha256 ?? "(none)"} ` +
      `but the maintained tree's canonical aggregate is ${canonicalManifest.aggregate_sha256}: the record describes a DIFFERENT canonical release`,
    );
  }
  const selectedAudit = treeAudit(selectedDir);
  if (selectedAudit.problems.length) {
    const p = selectedAudit.problems[0];
    return refuse(`the selected copy ${selectedDir} cannot be verified: ${p.path} ${p.reason}`);
  }
  for (const g of selectedAudit.generated) {
    if (g.kind === "roll-sentinel") {
      // Roll bookkeeping written by update-skills.sh: a roll may legitimately
      // leave an older sentinel behind until it is rewritten, so the bound is
      // the sentinel's own name and content, not the release it sits beside.
      const named = /^\.wired-(\d+\.\d+\.\d+)$/.exec(g.path);
      const content = named ? normalizedText(join(selectedDir, g.path)).trim() : null;
      if (!named || content !== named[1]) {
        return refuse(
          `the selected copy ${selectedDir} carries ${g.path}, which is not a roll sentinel recording its own version: ` +
          `a roll sentinel names a version and contains it`,
        );
      }
      continue;
    }
    return refuse(`the selected copy ${selectedDir} carries ${g.path}, an unshipped dependency tree: nothing in it can be verified against the release`);
  }
  for (const a of selectedAudit.archives) {
    const recordedArchive = canonicalManifest.archive?.sha256 ?? null;
    if (a.sha256 !== recordedArchive) {
      return refuse(
        `the selected copy ${selectedDir} carries the archive ${a.path} (sha256 ${a.sha256}) but the release generated ` +
        `${recordedArchive ?? "(none)"}: an unverifiable archive is not a distribution artifact`,
      );
    }
  }
  const selectedTree = treeAggregateFrom(selectedAudit.entries);
  if (selectedTree.aggregate !== distManifest.aggregate_sha256 || selectedTree.fileCount !== distManifest.file_count) {
    return refuse(
      `the selected copy ${selectedDir} is not the tree its own manifest records ` +
      `(recomputed ${selectedTree.aggregate} over ${selectedTree.fileCount} files, manifest ${distManifest.aggregate_sha256} over ${distManifest.file_count})`,
    );
  }
  const selectedDrift = missingOrDrifting(distManifest.files, selectedAudit.entries);
  if (selectedDrift.length) {
    return refuse(
      `the selected copy ${selectedDir} is not the tree its own manifest records per file ` +
      `(${selectedDrift.slice(0, 3).join("; ")})`,
    );
  }

  // --- the distribution must be exactly the declared derivation -----------
  const drift = missingOrDrifting(witness.files, selectedAudit.entries);
  if (drift.length) {
    return refuse(
      `the selected copy ${selectedDir} does not carry the distribution the release records ` +
      `(${drift.slice(0, 3).join("; ")})`,
    );
  }
  const recordedPaths = new Set(witness.files.map((f) => f.path));
  const extraFiles = selectedAudit.entries.filter((f) => !recordedPaths.has(f.path)).map((f) => f.path);
  for (const p of extraFiles) {
    if (!addedPaths.includes(p)) {
      return refuse(`the selected copy ${selectedDir} carries ${p}, which the release neither records nor declares as an added distribution path`);
    }
  }
  for (const p of addedPaths) {
    if (!extraFiles.includes(p)) {
      return refuse(`the release declares ${p} as an added distribution path, but the selected copy ${selectedDir} does not carry it`);
    }
  }
  // Content the distribution is allowed to differ on is still declared, and
  // the canonical manifest pins the digests it differs TO.
  const selectedByPath = byPath(selectedAudit.entries);
  const contentDiffs = new Map();
  for (const f of canonicalManifest.files) {
    if (!selectedByPath.has(f.path)) continue;
    if (selectedByPath.get(f.path) !== f.sha256) contentDiffs.set(f.path, f.sha256);
  }

  // --- the vendored build must be the release's build ---------------------
  const recordedBuild = byPath(witness.runtime_dist);
  const shippedBuild = selectedAudit.dist;
  if (!shippedBuild.length) return refuse(`the selected copy ${selectedDir} ships no built runtime, so it carries no executable`);
  for (const f of shippedBuild) {
    if (!recordedBuild.has(f.path)) {
      return refuse(
        `the selected copy ${selectedDir} ships ${f.path}, which the release's recorded build does not contain: ` +
        `an executable the release never built cannot be accepted`,
      );
    }
    if (recordedBuild.get(f.path) !== f.sha256) {
      return refuse(
        `the selected copy ${selectedDir} ships ${f.path} as sha256 ${f.sha256}, but the release built ${recordedBuild.get(f.path)}: ` +
        `a modified build is not the release's build`,
      );
    }
  }
  const shippedEntry = shippedBuild.find((f) => f.path === recordedEntry.path);
  if (!shippedEntry || shippedEntry.sha256 !== recordedEntry.sha256 || shippedEntry.bytes !== recordedEntry.bytes) {
    return refuse(
      `the selected copy ${selectedDir} does not ship the release's executable ` +
      `(${recordedEntry.path} ${recordedEntry.sha256}): a distribution presents the build the release recorded`,
    );
  }

  // --- the record ---------------------------------------------------------
  const reconciled = reconcileRecord(selectedDir, {
    maintainedManifest: canonicalManifest,
    maintainedAggregate: canonicalManifest.aggregate_sha256,
    maintainedFileCount: canonicalManifest.file_count,
    addedPaths,
    contentDiffs,
    maintainedHasArchive: canonicalAudit.archives.length > 0,
  });
  if (reconciled.problems.length) return refuse(reconciled.problems[0]);

  if (!entryChecksPassed) {
    return refuse(`the selected copy ${selectedDir} did not pass its executable checks, so it is not a usable distribution`);
  }
  return {
    ok: true,
    aggregate: canonicalManifest.aggregate_sha256,
    canonicalPath: maintainedDir,
    files: witness.files.length,
    distFiles: shippedBuild.length,
  };
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
    // (c)+(d) the selected artifact must ship a verifiable executable.
    // Collected separately: the same result answers condition (f) of the
    // same-release proof below — an unusable copy is never "the distribution".
    const artifactProblems = [];
    const state = executableStatus(selected, records);
    if (state === "packaged") {
      const manifest = readJson(join(selected.physical, "manifest.json"));
      const gate = checkEntryPoint(selected.physical, manifest, { load });
      if (!gate.ok) artifactProblems.push(...gate.problems.map((p) => `SELECTED copy ${selected.path}: ${p}`));
    } else if (state === "packaged-missing-entry") {
      artifactProblems.push(
        `SELECTED artifact ${selected.path} records runtime_entry ${selected.runtimeEntry.path} ` +
        `but does not ship it (no runtime/dist entry, no archive, no installed release): ` +
        `every shipped artifact includes its executable`,
      );
    } else if (state === "record-without-entry") {
      artifactProblems.push(
        `the install-record naming ${selected.path} points at a release with no executable entry; ` +
        `the resolver-selected copy is unusable`,
      );
    } else if (state === "source-only") {
      artifactProblems.push(
        `source-only artifact at ${selected.path}: no runtime/dist entry, no manifest runtime_entry, ` +
        `no archive, and no installed release naming this tree — every shipped artifact includes its executable`,
      );
    } else if (state === "archive") {
      artifactProblems.push(...verifyArchive(selected, { load }).map((p) => `SELECTED copy ${selected.path}: ${p}`));
    } else if (state === "installed") {
      const rec = records.find((r) => samePath(r.skillDir, selected.physical));
      if (!rec) {
        artifactProblems.push(`the selected copy ${selected.path} was classified installed without a matching install-record`);
      } else {
        artifactProblems.push(...verifyInstalledEntry(rec, { load }).map((p) => `SELECTED copy ${selected.path}: ${p}`));
      }
    }
    problems.push(...artifactProblems);
    // "archive" (executable ships inside the .skill archive) and "installed"
    // (a release named by the resolver's own install-record carries it) both
    // satisfy the shipped-executable rule.
    if (skillDir && !samePath(selected.physical, skillDir)) {
      const selectedIdentity = treeIdentity(selected.physical);
      const maintainedIdentity = treeIdentity(skillDir);
      if (selectedIdentity !== maintainedIdentity) {
        // Different bytes are not automatically a different release: the 999
        // distribution of the same canonical tree differs by design. Accept it
        // only on a complete recomputation proof, and say so out loud.
        let proof;
        try {
          proof = proveSameRelease({
            selectedDir: selected.physical,
            maintainedDir: skillDir,
            selectedVersion: selected.version,
            maintainedVersion: canonicalVersion,
            entryChecksPassed: artifactProblems.length === 0,
          });
        } catch (error) {
          // A proof that cannot run is a refusal, never a crash: the caller
          // parses this gate's summary line and must keep getting one.
          proof = { ok: false, reason: `the proof itself failed: ${String(error?.message ?? error).split("\n")[0]}` };
        }
        if (proof.ok) {
          warnings.push(
            `SAME RELEASE: distribution ${selected.path} is the 999 packaging of canonical aggregate ` +
            `${proof.aggregate}, proven by manifest recomputation ` +
            `(${proof.files} recorded files and ${proof.distFiles} built files matched; canonical tree ${skillDir})`,
          );
        } else {
          problems.push(
            `the selected copy ${selected.path} and the tree this update maintains ${skillDir} ` +
            (selected.version && selected.version === canonicalVersion
              ? `both claim ${selected.version} `
              : "") +
            `but their trees differ (selected ${selectedIdentity} vs maintained ${maintainedIdentity}): ` +
            `an update that wrote any other file must not report success`,
          );
          // A tree that presents itself as a distribution gets the specific
          // reason its proof failed, never a silent generic refusal.
          if (isDistributionCandidate(selected.physical) || isDistributionCandidate(skillDir)) {
            problems.push(`SAME-RELEASE PROOF REFUSED: ${proof.reason}`);
          }
        }
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

// Compare REAL paths: node reports import.meta.url with symlinks resolved, so a
// verifier started through a symlinked path (/tmp, /var, a linked skill folder)
// used to match nothing here and exit 0 in silence - a gate that passes by not
// running.
if (process.argv[1] && import.meta.url === pathToFileURL(safeReal(process.argv[1])).href) {
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
