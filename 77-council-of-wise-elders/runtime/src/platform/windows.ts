/**
 * Windows durable-volume observation (WER-027, Windows half A).
 *
 * Windows has no `/proc/self/mountinfo`. The facts that ARE observable from
 * Node without a shell are:
 *
 * - the resolved (realpath) location of the data directory, which resolves
 *   8.3 short names and junction/symlink targets;
 * - the volume root from `path.win32.parse(...).root` (a drive letter or a
 *   UNC `\\server\share\` path);
 * - free-space geometry from `fs.statfsSync` (`bsize`, `blocks`, `bfree`,
 *   `bavail`, `files`, `ffree`);
 * - `SystemDrive`, which names the volume Windows booted from. Only that
 *   volume is PROVEN fixed; a different drive letter cannot be proven fixed
 *   or removable without a native `GetDriveTypeW` call, so it stays
 *   `undetermined` and is refused rather than assumed durable.
 *
 * Temporary roots (`TEMP`, `TMP`, `%USERPROFILE%\AppData\Local\Temp`,
 * `%LOCALAPPDATA%\Temp`, `%SystemRoot%\Temp`) are REFUSED for durable state.
 * Every comparison uses `path.win32` so these rules are testable on any host
 * and never depend on the POSIX separator.
 *
 * Nothing here executes a shell command, reads the network, or registers a
 * service. A real Windows host is still required to prove actual volume
 * geometry, junction targets and drive type; this module records what it can
 * observe and refuses the rest.
 */

import { realpathSync, statfsSync } from 'node:fs';
import { win32 } from 'node:path';

import { defaultWritable, type DataDirVerdict } from './mounts.js';
import { platformRefusal, type MountRecord } from './types.js';

/** Free-space facts read from `fs.statfsSync`. */
export interface WindowsVolumeSpace {
  bsize: number;
  blocks: number;
  bfree: number;
  bavail: number;
  files: number;
  ffree: number;
}

export type WindowsVolumeKind = 'fixed' | 'network' | 'undetermined';

export interface WindowsVolumeObservation {
  /** True when the volume kind is characterised (fixed or network). */
  ok: boolean;
  /** `C:` or `\\server\share`. */
  drive: string;
  /** `C:\` or `\\server\share\`. */
  root: string;
  kind: WindowsVolumeKind;
  /** Never presented as a Linux filesystem type. */
  fs_type: string;
  /** null when read-only state cannot be observed. */
  read_only: boolean | null;
  space: WindowsVolumeSpace | null;
  evidence: string[];
  checked: string[];
  error: string | null;
}

export interface WindowsVolumeOptions {
  dataDir: string;
  /** Already-resolved path; observed when omitted. */
  canonicalDataDir?: string;
  env?: NodeJS.ProcessEnv;
  /** Injected for tests; defaults to `fs.statfsSync`. */
  statfs?: (path: string) => WindowsVolumeSpace;
  /** Injected for tests; defaults to `fs.realpathSync.native`. */
  realpath?: (path: string) => string;
}

const TEMP_ENV_KEYS = ['TEMP', 'TMP'] as const;

/**
 * Strip a `\\?\` extended-length prefix. `\\?\UNC\server\share` becomes
 * `\\server\share`; `\\?\C:\dir` becomes `C:\dir`.
 */
export function stripExtendedPrefix(value: string): string {
  if (/^\\\\\?\\UNC\\/i.test(value)) {
    return `\\\\${value.slice('\\\\?\\UNC\\'.length)}`;
  }
  if (/^\\\\\?\\/i.test(value)) {
    return value.slice('\\\\?\\'.length);
  }
  return value;
}

function defaultRealpath(path: string): string {
  const relevant = stripExtendedPrefix(path);
  return stripExtendedPrefix(realpathSync.native(relevant));
}

export interface CanonicalWindowsPath {
  path: string;
  /** True when a realpath observation (not the lexical fallback) answered. */
  resolved: boolean;
  error: string | null;
}

/**
 * Windows-aware canonical path with its provenance. Resolves the nearest
 * existing ancestor when the tail does not exist yet, and falls back to the
 * lexical absolute path when `realpath` fails (for example when the test host
 * is not Windows). The fallback is reported, never silent.
 */
export function canonicalWindowsPathDetailed(
  path: string,
  realpath: (path: string) => string = defaultRealpath,
): CanonicalWindowsPath {
  let current = win32.resolve(stripExtendedPrefix(path));
  const tail: string[] = [];
  let lastError: string | null = null;
  for (;;) {
    try {
      const real = stripExtendedPrefix(realpath(current));
      return {
        path: tail.length === 0 ? real : win32.join(real, ...tail),
        resolved: true,
        error: lastError,
      };
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      const parent = win32.dirname(current);
      if (parent === current) {
        return {
          path: win32.resolve(stripExtendedPrefix(path)),
          resolved: false,
          error: lastError,
        };
      }
      tail.unshift(win32.basename(current));
      current = parent;
    }
  }
}

export function canonicalWindowsPath(
  path: string,
  realpath: (path: string) => string = defaultRealpath,
): string {
  return canonicalWindowsPathDetailed(path, realpath).path;
}

/** Windows paths are case-insensitive; drive roots keep their separator. */
function trimWindowsPath(value: string): string {
  const resolved = win32.resolve(value);
  const root = win32.parse(resolved).root;
  return resolved === root ? resolved : resolved.replace(/[\\/]+$/, '');
}

/** `child` is `parent` or sits below it on a case-insensitive boundary. */
export function isInsideWindows(child: string, parent: string): boolean {
  const a = trimWindowsPath(child);
  const b = trimWindowsPath(parent);
  if (b.length === 0) return false;
  const loweredChild = a.toLowerCase();
  const loweredParent = b.toLowerCase();
  if (loweredChild === loweredParent) return true;
  const prefix = loweredParent.endsWith(win32.sep) ? loweredParent : `${loweredParent}${win32.sep}`;
  return loweredChild.startsWith(prefix);
}

/** Every Windows temporary root the process can name, with its source. */
export function windowsTempRoots(
  env: NodeJS.ProcessEnv = process.env,
): Array<{ root: string; source: string }> {
  const candidates: Array<{ root: string | undefined; source: string }> = [
    { root: env.TEMP, source: 'env:TEMP' },
    { root: env.TMP, source: 'env:TMP' },
    {
      root: env.USERPROFILE
        ? win32.join(env.USERPROFILE, 'AppData', 'Local', 'Temp')
        : undefined,
      source: 'env:USERPROFILE\\AppData\\Local\\Temp',
    },
    {
      root: env.LOCALAPPDATA ? win32.join(env.LOCALAPPDATA, 'Temp') : undefined,
      source: 'env:LOCALAPPDATA\\Temp',
    },
    {
      root: env.SystemRoot ? win32.join(env.SystemRoot, 'Temp') : undefined,
      source: 'env:SystemRoot\\Temp',
    },
    {
      root: env.WINDIR ? win32.join(env.WINDIR, 'Temp') : undefined,
      source: 'env:WINDIR\\Temp',
    },
  ];

  const seen = new Set<string>();
  const roots: Array<{ root: string; source: string }> = [];
  for (const candidate of candidates) {
    if (!candidate.root || !win32.isAbsolute(candidate.root)) continue;
    const root = win32.resolve(candidate.root);
    const key = root.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    roots.push({ root, source: candidate.source });
  }
  return roots;
}

function driveOf(root: string): string {
  return root.replace(/[\\/]+$/, '');
}

function normalizeDrive(value: string | undefined): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim().replace(/[\\/]+$/, '');
  return trimmed.length > 0 ? trimmed.toLowerCase() : null;
}

function readSpace(
  path: string,
  statfs: (path: string) => WindowsVolumeSpace,
  checked: string[],
  errors: string[],
): WindowsVolumeSpace | null {
  checked.push(`statfs:${path}`);
  try {
    const stats = statfs(path);
    return {
      bsize: Number(stats.bsize),
      blocks: Number(stats.blocks),
      bfree: Number(stats.bfree),
      bavail: Number(stats.bavail),
      files: Number(stats.files),
      ffree: Number(stats.ffree),
    };
  } catch (error) {
    errors.push(`${path}: ${error instanceof Error ? error.message : String(error)}`);
    return null;
  }
}

/**
 * Observe the volume behind `dataDir` from real Windows facts.
 *
 * Classification order:
 *   1. UNC root -> network (observed, never assumed durable);
 *   2. drive letter equal to `SystemDrive` -> fixed (boot volume);
 *   3. anything else -> undetermined, with the reason named.
 *
 * `statfs` is attempted on the resolved data directory and, when that fails,
 * on the volume root. Its values are recorded as evidence in every case.
 */
export function observeWindowsVolume(
  options: WindowsVolumeOptions,
): WindowsVolumeObservation {
  const env = options.env ?? process.env;
  const canonical = options.canonicalDataDir ?? canonicalWindowsPath(options.dataDir, options.realpath);
  const root = win32.parse(canonical).root;
  const drive = driveOf(root);
  const evidence: string[] = [`canonical path: ${canonical}`, `volume root: ${root}`, `volume: ${drive}`];
  const checked: string[] = ['path.win32.parse(root)', 'path.win32.resolve(dataDir)'];
  const errors: string[] = [];

  const statfs = options.statfs ?? ((path: string): WindowsVolumeSpace => statfsSync(path));
  let space = readSpace(canonical, statfs, checked, errors);
  if (!space && root.length > 0) {
    space = readSpace(root, statfs, checked, errors);
  }
  if (space) {
    evidence.push(
      `statfs: bsize=${space.bsize} blocks=${space.blocks} bfree=${space.bfree} bavail=${space.bavail} files=${space.files} ffree=${space.ffree}`,
    );
  } else {
    evidence.push('statfs: unavailable');
  }

  if (root.startsWith('\\\\')) {
    evidence.push('UNC volume path is a network location; durability is not assumed');
    return {
      ok: true,
      drive,
      root,
      kind: 'network',
      fs_type: 'windows-network-volume',
      read_only: null,
      space,
      evidence,
      checked,
      error: errors.join('; ') || null,
    };
  }

  const systemDrive = normalizeDrive(env.SystemDrive);
  checked.push('env:SystemDrive');
  if (systemDrive && drive.toLowerCase() === systemDrive) {
    evidence.push(`env:SystemDrive=${env.SystemDrive} names this volume as the boot/fixed volume`);
    return {
      ok: true,
      drive,
      root,
      kind: 'fixed',
      fs_type: 'windows-fixed-volume',
      read_only: null,
      space,
      evidence,
      checked,
      error: errors.join('; ') || null,
    };
  }

  const reason = systemDrive
    ? `drive ${drive} is not SystemDrive ${env.SystemDrive}; fixed vs removable vs network cannot be observed without a native drive-type call`
    : 'SystemDrive is not set, so no volume can be proven fixed';
  evidence.push(reason);

  return {
    ok: false,
    drive,
    root,
    kind: 'undetermined',
    fs_type: 'windows-volume-undetermined',
    read_only: null,
    space,
    evidence,
    checked,
    error: errors.length > 0 ? `${reason}; ${errors.join('; ')}` : reason,
  };
}

export interface WindowsDataDirOptions {
  dataDir: string;
  replaceableRoots?: readonly string[];
  env?: NodeJS.ProcessEnv;
  /** Injected observation; defaults to `observeWindowsVolume`. */
  volume?: WindowsVolumeObservation;
  realpath?: (path: string) => string;
  statfs?: (path: string) => WindowsVolumeSpace;
  isWritable?: (path: string) => boolean;
}

/**
 * Decide whether a Windows data directory is durable.
 *
 * Order: absolute win32 path, resolve junctions/short names, refusal of any
 * temporary root, refusal of replaceable trees, observed volume, durable
 * volume kind, writability. Every failure is a typed refusal naming the
 * concrete path and rule; an uncharacterisable volume is BLOCKED_PLATFORM,
 * never an `ok`.
 */
export function evaluateWindowsDataDir(options: WindowsDataDirOptions): DataDirVerdict {
  const env = options.env ?? process.env;
  const checked: string[] = [];
  const raw = options.dataDir;

  if (typeof raw !== 'string' || raw.trim().length === 0 || !win32.isAbsolute(raw)) {
    return platformRefusal({
      code: 'PLATFORM_DATA_DIR_NOT_ABSOLUTE',
      condition: 'DATA_DIR_NOT_ABSOLUTE',
      detail: `The data directory ${JSON.stringify(raw)} is not an absolute Windows path; a relative path would make durability depend on the process working directory.`,
      recovery:
        'Pass the absolute per-user council data directory (see src/cli/paths.ts resolveDataDir).',
      checked,
    });
  }

  const dataDir = win32.resolve(stripExtendedPrefix(raw));
  const canonical = canonicalWindowsPathDetailed(dataDir, options.realpath);
  const canonicalDataDir = canonical.path;
  checked.push(dataDir);
  if (canonicalDataDir.toLowerCase() !== dataDir.toLowerCase()) {
    checked.push(`resolved: ${canonicalDataDir}`);
  }
  if (!canonical.resolved) {
    checked.push(`realpath fallback (lexical): ${canonical.error ?? 'realpath failed'}`);
  }

  for (const candidate of windowsTempRoots(env)) {
    const canonicalRoot = canonicalWindowsPath(candidate.root, options.realpath);
    checked.push(`${candidate.source}=${candidate.root}`);
    if (isInsideWindows(canonicalDataDir, canonicalRoot)) {
      const resolvedNote =
        canonicalDataDir.toLowerCase() === dataDir.toLowerCase()
          ? ''
          : ` (resolved to ${canonicalDataDir})`;
      return platformRefusal({
        code: 'PLATFORM_DATA_DIR_EPHEMERAL',
        condition: 'DATA_DIR_EPHEMERAL_MOUNT',
        detail: `The data directory ${dataDir}${resolvedNote} is inside the Windows temporary root ${canonicalRoot} (${candidate.source}). Temporary storage does not survive a reboot, profile reset or cleanup, so sessions, reservations and the budget ledger would be lost.`,
        recovery:
          'Move the data directory to a durable volume (a fixed drive outside every temporary root) and re-run platform resolution.',
        checked,
      });
    }
  }

  for (const root of options.replaceableRoots ?? []) {
    const canonicalRoot = canonicalWindowsPath(root, options.realpath);
    checked.push(canonicalRoot);
    if (isInsideWindows(canonicalDataDir, canonicalRoot)) {
      return platformRefusal({
        code: 'PLATFORM_DATA_DIR_INSIDE_REPLACEABLE_TREE',
        condition: 'DATA_DIR_INSIDE_REPLACEABLE_TREE',
        detail: `The data directory ${dataDir} (resolved ${canonicalDataDir}) is inside the replaceable tree ${canonicalRoot}. An update that replaces that tree would destroy durable council state.`,
        recovery:
          'Move the data directory outside the skill folder and the runtime release directory, then re-run platform resolution.',
        checked,
      });
    }
  }

  const volume =
    options.volume ??
    observeWindowsVolume({ dataDir, canonicalDataDir, env, realpath: options.realpath, statfs: options.statfs });
  checked.push(...volume.checked, ...volume.evidence);

  if (!volume.ok || volume.kind === 'undetermined') {
    return platformRefusal({
      code: 'BLOCKED_PLATFORM',
      condition: 'MOUNT_PERSISTENCE_UNDETERMINED',
      detail: `The data directory ${dataDir} is on Windows volume ${volume.drive || '(unknown)'}. ${volume.error ?? 'Durability cannot be proven from the observable volume facts, so it is not assumed.'}`,
      recovery:
        'Place the data directory on the fixed system volume or supply an observed Windows volume record, and re-run on the real host.',
      requires_real_host: true,
      checked,
      unknowns: ['drive type (fixed/removable/network) and filesystem type of the volume'],
    });
  }

  if (volume.kind === 'network') {
    return platformRefusal({
      code: 'BLOCKED_PLATFORM',
      condition: 'MOUNT_PERSISTENCE_UNDETERMINED',
      detail: `The data directory ${dataDir} is on network volume ${volume.drive}. A network volume is not assumed durable: availability and persistence are outside this process.`,
      recovery:
        'Place the data directory on a fixed local volume and re-run platform resolution.',
      requires_real_host: true,
      checked,
      unknowns: ['durability of the network volume'],
    });
  }

  const isWritable = options.isWritable ?? defaultWritable;
  if (!isWritable(dataDir)) {
    return platformRefusal({
      code: 'PLATFORM_DATA_DIR_NOT_WRITABLE',
      condition: 'DATA_DIR_NOT_WRITABLE',
      detail: `The data directory ${dataDir} (or its nearest existing ancestor) is not writable by the current process identity.`,
      recovery:
        'Fix ownership/permissions on the durable volume for the service account, then re-run platform resolution.',
      checked,
    });
  }

  const mount: MountRecord = {
    mount_point: volume.root,
    fs_type: volume.fs_type,
    device: volume.drive,
    read_only: false,
  };

  return {
    kind: 'persistent',
    data_dir: dataDir,
    mount,
    fs_type: volume.fs_type,
    evidence: checked,
  };
}
