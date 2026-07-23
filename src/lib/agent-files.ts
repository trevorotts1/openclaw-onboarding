/**
 * agent-files.ts — Safe file writer for per-agent workspace files.
 *
 * Every agent directory's shared files (AGENTS.md, TOOLS.md, USER.md) are
 * symbolic links to agents/_shared/. Writing through a symlink without an
 * lstat/link check replaces the operating rules (including safety rules) for
 * every agent in the company.
 *
 * U088 — Symlink write guard (2026-07-23)
 */

import * as fs from 'node:fs';
import * as fsPromises from 'node:fs/promises';
import * as path from 'node:path';

export const SHARED_FILES = new Set(['AGENTS.md', 'TOOLS.md', 'USER.md']);

export class SharedFileError extends Error {
  public readonly code: 'ESHAREDFILE' = 'ESHAREDFILE';
  public readonly symlinkTarget: string | null;

  constructor(message: string, symlinkTarget: string | null = null) {
    super(message);
    this.name = 'SharedFileError';
    this.symlinkTarget = symlinkTarget;
  }
}

export function isSymlinkSync(filePath: string): boolean {
  try {
    const stat = fs.lstatSync(filePath);
    return stat.isSymbolicLink();
  } catch (err: unknown) {
    if (err instanceof Error && 'code' in err && (err as NodeJS.ErrnoException).code === 'ENOENT') {
      return false;
    }
    throw err;
  }
}

export function readlinkSyncSafe(filePath: string): string | null {
  try {
    const stat = fs.lstatSync(filePath);
    if (!stat.isSymbolicLink()) return null;
    return fs.readlinkSync(filePath);
  } catch (err: unknown) {
    if (err instanceof Error && 'code' in err && (err as NodeJS.ErrnoException).code === 'ENOENT') {
      return null;
    }
    throw err;
  }
}

export interface WriteAgentFileOptions {
  filePath: string;
  content: string;
}

export interface WriteAgentFileResult {
  written: boolean;
  path: string;
}

export async function writeAgentFile(
  options: WriteAgentFileOptions,
): Promise<WriteAgentFileResult> {
  const { filePath, content } = options;
  const resolved = path.resolve(filePath);
  const basename = path.basename(resolved);

  if (SHARED_FILES.has(basename)) {
    const target = readlinkSyncSafe(resolved);
    if (target !== null) {
      throw new SharedFileError(
        'Refusing to write shared file "' + basename + '" through a symbolic link. ' +
          'Target path "' + resolved + '" is a symlink to "' + target + '". ' +
          'Writing through this symlink would overwrite the shared rules for ' +
          'every agent in the company. Update the canonical file at the symlink ' +
          'target directly, or replace the symlink with a local copy first.',
        target,
      );
    }
  }

  await fsPromises.mkdir(path.dirname(resolved), { recursive: true });
  await fsPromises.writeFile(resolved, content, 'utf-8');
  return { written: true, path: resolved };
}

export interface PreflightResult {
  allowed: boolean;
  conflict?: string;
  symlinkTarget?: string;
}

export function preflightSharedFields(filePath: string): PreflightResult {
  const basename = path.basename(filePath);

  if (!SHARED_FILES.has(basename)) {
    return { allowed: true };
  }

  const target = readlinkSyncSafe(filePath);
  if (target !== null) {
    return {
      allowed: false,
      conflict: 'Path "' + filePath + '" is a symbolic link (to "' + target + '"). ' +
        'Updating "' + basename + '" through this symlink would replace the shared ' +
        'file for every agent. Update the canonical file directly or convert ' +
        'the symlink to a local (per-agent) copy first.',
      symlinkTarget: target,
    };
  }

  return { allowed: true };
}
