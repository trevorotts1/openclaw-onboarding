/**
 * Standalone per-user data locations (CWE-004; directive Section 16.1).
 *
 * Council state is NOT source code: it never lives inside the skill
 * folder, because update sync replaces skill folders wholesale. Both Mac
 * Claude config roots share this one data profile; no duplicate history
 * is created per skill root.
 *
 * ONE AUTHORITY. The supported OpenClaw entry is the `blackceo-council`
 * shim; the durable store is the one the Council service itself runs on.
 * When the box is wired (wire.sh) the service launcher is given
 * COUNCIL_SERVICE_DATA_DIR and records the same directory in
 * `<runtime prefix>/active.json`. The CLI must read THAT store for a
 * session it convened, never an unrelated per-user default: otherwise
 * `blackceo-council status <id>` answers "not found" for a session the
 * service just created.
 *
 * Resolution order for the data directory:
 *   1. an explicit override (CLI --data-dir)
 *   2. BLACKCEO_COUNCIL_DATA_DIR (documented operator override)
 *   3. COUNCIL_SERVICE_DATA_DIR (the service launcher's own value)
 *   4. `<runtime prefix>/active.json` `dataDir` (durable install receipt)
 *   5. `<openclaw root>/council-data` when it exists (wire.sh layout)
 *   6. the per-platform default below
 *
 * The per-platform default applies only when no wired Council store
 * exists: macOS `~/Library/Application Support/BlackCEO/WiseElders`,
 * Windows `%LOCALAPPDATA%\BlackCEO\WiseElders`, Linux
 * `${XDG_DATA_HOME:-$HOME/.local/share}/blackceo/wise-elders`.
 * An override pointing inside the skill tree is always rejected so state
 * can never be swept away by a skill update.
 */

import { existsSync, mkdirSync, readFileSync, realpathSync } from 'node:fs';
import { homedir, platform } from 'node:os';
import { basename, dirname, join, resolve, sep } from 'node:path';
import { invalidInput } from './errors.js';

export const DATA_DIR_ENV = 'BLACKCEO_COUNCIL_DATA_DIR';
/** The service launcher's own durable data directory (wire.sh sets it). */
export const SERVICE_DATA_DIR_ENV = 'COUNCIL_SERVICE_DATA_DIR';
/** The immutable Council runtime prefix (WER-004 receipts live here). */
export const RUNTIME_PREFIX_ENV = 'COUNCIL_RUNTIME_PREFIX';
/** OPENCLAW_ROOT under the name the Council shim exports. */
export const OPENCLAW_ROOT_ENV = 'WISE_ELDERS_OPENCLAW_ROOT';

/** The home directory every default is measured from. */
export function homeDirFor(env: NodeJS.ProcessEnv = process.env, homeDir?: string): string {
  return homeDir || env.HOME || homedir();
}

/**
 * The OpenClaw root, by the same rule wire.sh and chamber-visual.sh use:
 * the environment value, else a container's /data/.openclaw, else
 * ~/.openclaw.
 */
export function openclawRoot(env: NodeJS.ProcessEnv = process.env, homeDir?: string): string {
  const explicit = env.OPENCLAW_ROOT || env[OPENCLAW_ROOT_ENV];
  if (explicit && explicit.trim().length > 0) return resolve(explicit);
  const home = homeDirFor(env, homeDir);
  if (existsSync('/data/.openclaw') && !existsSync(join(home, '.openclaw'))) return '/data/.openclaw';
  return join(home, '.openclaw');
}

/** The immutable runtime prefix: explicit, else <openclaw root>/council-runtime. */
export function councilRuntimePrefix(env: NodeJS.ProcessEnv = process.env, homeDir?: string): string {
  const explicit = env[RUNTIME_PREFIX_ENV];
  if (explicit && explicit.trim().length > 0) return resolve(explicit);
  return join(openclawRoot(env, homeDir), 'council-runtime');
}

/**
 * The directory the Council service itself runs on, when this box says
 * so. Null when nothing on the box has recorded one, never a guess.
 */
export function serviceDataDirHint(
  env: NodeJS.ProcessEnv = process.env,
  homeDir?: string,
): string | null {
  const explicit = env[SERVICE_DATA_DIR_ENV];
  if (explicit && explicit.trim().length > 0) return resolve(explicit);
  // The installer's atomically replaced receipt names the exact durable
  // directory the activated release was built against.
  try {
    const active = JSON.parse(
      readFileSync(join(councilRuntimePrefix(env, homeDir), 'active.json'), 'utf8'),
    ) as { dataDir?: unknown };
    if (typeof active.dataDir === 'string' && active.dataDir.trim().length > 0) {
      return resolve(active.dataDir);
    }
  } catch {
    /* no wired release receipt on this box */
  }
  // wire.sh keeps the durable store beside the runtime under $OPENCLAW_ROOT.
  const wired = join(openclawRoot(env, homeDir), 'council-data');
  return existsSync(wired) ? wired : null;
}

export function defaultDataDir(
  env: NodeJS.ProcessEnv = process.env,
  homeDir?: string,
): string {
  const home = homeDirFor(env, homeDir);
  switch (platform()) {
    case 'darwin':
      return join(home, 'Library', 'Application Support', 'BlackCEO', 'WiseElders');
    case 'win32': {
      const local = env.LOCALAPPDATA;
      return local
        ? join(local, 'BlackCEO', 'WiseElders')
        : join(home, 'AppData', 'Local', 'BlackCEO', 'WiseElders');
    }
    default: {
      const xdg = env.XDG_DATA_HOME;
      return xdg
        ? join(xdg, 'blackceo', 'wise-elders')
        : join(home, '.local', 'share', 'blackceo', 'wise-elders');
    }
  }
}

/**
 * Canonical form of a path for boundary comparison (F-046-1).
 *
 * realpathSync resolves every symlink in an existing path. A data
 * directory usually does not exist yet, so canonicalize the nearest
 * existing ancestor and re-append the remaining segments: a symlinked
 * ancestor cannot smuggle a not-yet-created directory into the skill
 * tree, and a symlink spelling of the skill root itself (the installed
 * config-root symlink, ~/.claude/skills/council-of-wise-elders)
 * compares equal to the physical root. Segments below the nearest
 * existing ancestor cannot be symlinks, because they do not exist. If
 * no ancestor can be canonicalized (unreachable in practice; the
 * filesystem root always exists), fall back to the textual path.
 */
function canonicalPath(path: string): string {
  let current = path;
  const tail: string[] = [];
  for (;;) {
    try {
      const real = realpathSync(current);
      return tail.length === 0 ? real : join(real, ...tail);
    } catch {
      const parent = dirname(current);
      if (parent === current) {
        return path;
      }
      tail.unshift(basename(current));
      current = parent;
    }
  }
}

export function resolveDataDir(options: {
  override?: string | null;
  env?: NodeJS.ProcessEnv;
  skillRoot?: string | null;
  /** Test seam: the home directory defaults are measured from. */
  homeDir?: string;
}): string {
  const env = options.env ?? process.env;
  const chosen =
    options.override ??
    env[DATA_DIR_ENV] ??
    serviceDataDirHint(env, options.homeDir) ??
    defaultDataDir(env, options.homeDir);
  const absolute = resolve(chosen);
  if (options.skillRoot) {
    // Compare canonical paths, not spellings (F-046-1): the Section
    // 16.1 refusal must fire for the same physical location however it
    // is spelled, while the F-4 boundary stays exact for genuinely
    // outside paths (parent, siblings, prefix-sharing names).
    const root = canonicalPath(resolve(options.skillRoot));
    const candidate = canonicalPath(absolute);
    if (candidate === root || candidate.startsWith(root + sep)) {
      throw invalidInput(
        `Data directory ${absolute} is inside the skill folder. Council state must live outside the synchronized skill tree (Section 16.1).`,
      );
    }
  }
  return absolute;
}

/** Create the data directory (and a named subdirectory) with private perms. */
export function ensureDataDir(dataDir: string, sub?: string): string {
  const target = sub ? join(dataDir, sub) : dataDir;
  if (!existsSync(target)) {
    mkdirSync(target, { recursive: true, mode: 0o700 });
  }
  return target;
}
