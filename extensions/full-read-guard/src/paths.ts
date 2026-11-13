import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';

export interface Roots { ocRoot: string; skillsDir: string; stateDir: string }

export interface RootOptions { skillsDir?: string; stateDir?: string; pluginDir?: string; env?: Record<string, string | undefined> }

function isDir(p: string): boolean { try { return fs.statSync(p).isDirectory(); } catch { return false; } }

/** Resolve the OpenClaw root the way the fleet updater does: OPENCLAW_ROOT, OC_CONFIG, /data/.openclaw (container), else ~/.openclaw. */
export function resolveRoots(opts: RootOptions = {}): Roots {
  const env = opts.env || process.env;
  let ocRoot = env.OPENCLAW_ROOT || env.OC_CONFIG || '';
  if (!ocRoot && opts.pluginDir) {
    // Installed plugin lives at <root>/extensions/full-read-guard
    const up = path.resolve(opts.pluginDir, '..', '..');
    if (path.basename(path.resolve(opts.pluginDir, '..')) === 'extensions') ocRoot = up;
  }
  if (!ocRoot) ocRoot = isDir('/data/.openclaw') ? '/data/.openclaw' : path.join(env.HOME || os.homedir(), '.openclaw');
  const skillsDir = opts.skillsDir || env.OC_SKILLS_DIR || path.join(ocRoot, 'skills');
  const stateDir = opts.stateDir || path.join(ocRoot, 'state', 'full-read-guard');
  return { ocRoot, skillsDir, stateDir };
}

export function safeReal(p: string): string {
  try { return fs.realpathSync(p); } catch {
    // Resolve the deepest existing ancestor so a not-yet-existing file still compares correctly.
    const parts: string[] = [];
    let cur = path.resolve(p);
    for (;;) {
      try { return path.join(fs.realpathSync(cur), ...parts.reverse()); } catch {
        const parent = path.dirname(cur);
        if (parent === cur) return path.resolve(p);
        parts.push(path.basename(cur));
        cur = parent;
      }
    }
  }
}

export function sha256(buf: Buffer | string): string {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

const shaCache = new Map<string, { mtimeMs: number; size: number; sha: string }>();
/** sha256 of a file, cached by mtime+size. Returns null when unreadable. */
export function fileSha(abs: string): string | null {
  try {
    const st = fs.statSync(abs);
    const hit = shaCache.get(abs);
    if (hit && hit.mtimeMs === st.mtimeMs && hit.size === st.size) return hit.sha;
    const sha = sha256(fs.readFileSync(abs));
    shaCache.set(abs, { mtimeMs: st.mtimeMs, size: st.size, sha });
    return sha;
  } catch { return null; }
}

export const WORKSPACE_SKILL_PREFIX = 'workspace-skill://workspace/';

/** `file:///x`, `~/x` and `workspace-skill://workspace/<name>/<rest>` -> filesystem-ish path (relative parts untouched). */
export function normalizeInputPath(p: string): { kind: 'fs'; path: string } | { kind: 'workspace-skill'; name: string; rel: string } {
  if (p.startsWith(WORKSPACE_SKILL_PREFIX)) {
    const parts = p.slice(WORKSPACE_SKILL_PREFIX.length).split('/').map((x) => { try { return decodeURIComponent(x); } catch { return x; } });
    return { kind: 'workspace-skill', name: parts[0] || '', rel: parts.slice(1).join('/') || 'SKILL.md' };
  }
  let out = p;
  if (out.startsWith('file://')) { try { out = decodeURIComponent(out.slice(7)); } catch { out = out.slice(7); } }
  if (out.startsWith('@')) out = out.slice(1);
  if (out === '~' || out.startsWith('~/')) out = path.join(os.homedir(), out.slice(1));
  return { kind: 'fs', path: out };
}

export function lineCount(text: string): number {
  if (text === '') return 0;
  let n = 1;
  for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) n++;
  return text.endsWith('\n') ? n - 1 : n;
}
