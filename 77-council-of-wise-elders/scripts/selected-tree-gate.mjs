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
// copy); every selected-tree violation fails the gate. wire.sh runs this gate
// and exits 1 on failure, so update-skills.sh withholds the .wired sentinel
// and no roll reports success for a stale or shadowed tree.
//
// ponytail: competing copies are reported, never deleted or rewritten here —
// converging a foreign root belongs to that root's own installer; add
// auto-convergence when one supported mechanism owns all the roots.
//
// Usage: node scripts/selected-tree-gate.mjs --skill-dir DIR [--prefix DIR]
//        [--home DIR] [--no-load]   (exit 0 ok, 1 problems, 2 usage)

import { existsSync, lstatSync, readdirSync, readFileSync, realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { checkEntryPoint } from "./entry-point-gate.mjs";

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

/** Version of a copy: version file, then skill-version.txt (leading v stripped). */
export function readVersion(dir) {
  for (const name of ["version", "skill-version.txt"]) {
    try {
      const v = readFileSync(join(dir, name), "utf8").trim().replace(/^v/, "");
      if (v) return v;
    } catch {
      // fall through
    }
  }
  return null;
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
    return { recordPath: safeReal(file), skillDir: resolve(json.skill_dir) };
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
  return {
    path: dir,
    physical,
    kind,
    version: readVersion(dir),
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
 * The copy the runtime resolver selects: the install-record the live CLI (or
 * the updater's prefix) consults first; otherwise the install-time resolver
 * order. A record that is unreadable fails closed rather than guessing.
 */
export function resolveSelection({ home, claudeConfigDir, openclawRoot, prefix, skillDir, records } = {}) {
  const found = records ?? scanInstallRecords({ home, prefix });
  if (found.length >= 1) {
    return { selectedPath: found[0].skillDir, via: `install-record ${found[0].recordPath}`, problems: [] };
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
 * Full gate. Returns {ok, problems, warnings, selected, copies, records}.
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
  const problems = [];
  const warnings = [];

  const records = scanInstallRecords({ home, prefix });
  const selection = resolveSelection({ home, claudeConfigDir, openclawRoot, prefix, skillDir, records });
  problems.push(...selection.problems);

  const copies = inspectCopies({
    home,
    claudeConfigDir,
    openclawRoot,
    extraDirs: skillDir ? [skillDir] : [],
  });

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

  const canonicalVersion = opts.canonicalVersion ?? (skillDir ? readVersion(skillDir) : null);

  if (selected) {
    // (a) the selected copy must be the version this update ships
    if (canonicalVersion && selected.version !== canonicalVersion) {
      problems.push(
        `the copy the resolver selects is ${selected.path} at version ${selected.version ?? "unknown"} ` +
        `while this update ships ${canonicalVersion}: the updater would be updating only an unused directory`,
      );
    }
    // (e) the convene contract, as text the selected tree actually carries
    const text = normalizedText(join(selected.path, "SKILL.md"));
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
      const manifest = readJson(join(selected.path, "manifest.json"));
      const gate = checkEntryPoint(selected.path, manifest, { load });
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
    }
    // "archive" (executable ships inside the .skill archive) and "installed"
    // (a release named by the resolver's own install-record carries it) both
    // satisfy the shipped-executable rule.
    if (skillDir && !samePath(selected.physical, skillDir)) {
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

  return {
    ok: problems.length === 0,
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
  const out = { skillDir: null, prefix: null, home: null, load: true };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    const next = argv[i + 1];
    if (a === "--skill-dir" && next) { out.skillDir = next; i += 1; }
    else if (a === "--prefix" && next) { out.prefix = next; i += 1; }
    else if (a === "--home" && next) { out.home = next; i += 1; }
    else if (a === "--no-load") { out.load = false; }
    else return null;
  }
  return out;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = parseArgs(process.argv.slice(2));
  if (!args || !args.skillDir) {
    console.log("usage: node scripts/selected-tree-gate.mjs --skill-dir DIR [--prefix DIR] [--home DIR] [--no-load]");
    process.exit(2);
  }
  const result = checkSelectedTree({
    home: args.home ?? homedir(),
    skillDir: args.skillDir,
    prefix: args.prefix,
    load: args.load,
  });
  for (const p of result.problems) console.log(`  ✗ ERROR: ${p}`);
  for (const w of result.warnings) console.log(`  ⚠️  ${w}`);
  console.log(
    `SELECTED-TREE: ${result.ok ? "OK" : "FAIL"} selected=${result.selectedPath ?? "<none>"} ` +
    `via=${result.via ?? "<none>"} copies=${result.copies.length}`,
  );
  process.exit(result.ok ? 0 : 1);
}
