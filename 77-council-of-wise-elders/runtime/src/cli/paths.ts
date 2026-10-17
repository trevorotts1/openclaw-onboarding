/**
 * Standalone per-user data locations (CWE-004; directive Section 16.1).
 *
 * Council state is NOT source code: it never lives inside the skill
 * folder, because update sync replaces skill folders wholesale. Both Mac
 * Claude config roots share this one data profile; no duplicate history
 * is created per skill root.
 *
 * Defaults: macOS `~/Library/Application Support/BlackCEO/WiseElders`;
 * Windows `%LOCALAPPDATA%\BlackCEO\WiseElders`; Linux
 * `${XDG_DATA_HOME:-$HOME/.local/share}/blackceo/wise-elders`.
 * An explicit override (CLI --data-dir or BLACKCEO_COUNCIL_DATA_DIR) is
 * validated and wins; an override pointing inside the skill tree is
 * rejected so state can never be swept away by a skill update.
 */

import { existsSync, mkdirSync, realpathSync } from 'node:fs';
import { homedir, platform } from 'node:os';
import { basename, dirname, join, resolve, sep } from 'node:path';
import { invalidInput } from './errors.js';

export const DATA_DIR_ENV = 'BLACKCEO_COUNCIL_DATA_DIR';

export function defaultDataDir(env: NodeJS.ProcessEnv = process.env): string {
  const home = homedir();
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
}): string {
  const env = options.env ?? process.env;
  const chosen =
    options.override ?? env[DATA_DIR_ENV] ?? defaultDataDir(env);
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
