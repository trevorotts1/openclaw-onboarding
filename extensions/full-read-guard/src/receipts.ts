// Per-session read receipts. File level: abs path -> sha256 delivered to the model.
// Memory first, mirrored to <stateDir>/<session>.json. Reset on session start/end and after compaction.
import fs from 'node:fs';
import path from 'node:path';
import { fileSha } from './paths.js';

interface Progress { sig: string; total: number; delivered: number[] }
interface SessionState {
  files: Record<string, string>;
  inUse: Record<string, number>;
  progress: Record<string, Progress>;
}

function empty(): SessionState { return { files: {}, inUse: {}, progress: {} }; }
function safeName(key: string): string { return key.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 120) || 'default'; }

export class Receipts {
  private sessions = new Map<string, SessionState>();
  constructor(private stateDir: string | null, private now: () => number = Date.now) {}

  private get(key: string): SessionState {
    let s = this.sessions.get(key);
    if (s) return s;
    s = empty();
    if (this.stateDir) {
      try {
        const raw = JSON.parse(fs.readFileSync(path.join(this.stateDir, safeName(key) + '.json'), 'utf8'));
        if (raw && typeof raw.files === 'object') s = { files: raw.files || {}, inUse: raw.inUse || {}, progress: raw.progress || {} };
      } catch { /* no mirror yet */ }
    }
    this.sessions.set(key, s);
    return s;
  }

  private persist(key: string): void {
    if (!this.stateDir) return;
    try {
      fs.mkdirSync(this.stateDir, { recursive: true });
      const file = path.join(this.stateDir, safeName(key) + '.json');
      const tmp = file + '.tmp-' + process.pid;
      fs.writeFileSync(tmp, JSON.stringify(this.sessions.get(key)));
      fs.renameSync(tmp, file);
    } catch { /* mirror is best effort; memory is authoritative */ }
  }

  reset(key: string): void {
    this.sessions.set(key, empty());
    if (this.stateDir) { try { fs.rmSync(path.join(this.stateDir, safeName(key) + '.json'), { force: true }); } catch { /* ignore */ } }
  }

  markFile(key: string, abs: string, sha: string, persist = true): void {
    this.get(key).files[abs] = sha;
    if (persist) this.persist(key);
  }
  flush(key: string): void { this.persist(key); }

  /** True only when the file was delivered AND is unchanged on disk since. */
  hasFile(key: string, abs: string): boolean {
    const want = this.get(key).files[abs];
    if (!want) return false;
    return fileSha(abs) === want;
  }

  markInUse(key: string, folder: string): void {
    const s = this.get(key);
    if (!s.inUse[folder]) { s.inUse[folder] = this.now(); this.persist(key); }
  }
  inUse(key: string): string[] { return Object.keys(this.get(key).inUse); }

  progress(key: string, bundle: string): Progress | undefined { return this.get(key).progress[bundle]; }
  setProgress(key: string, bundle: string, p: Progress): void { this.get(key).progress[bundle] = p; this.persist(key); }

  missing(key: string, files: { abs: string }[]): string[] {
    return files.filter((f) => !this.hasFile(key, f.abs)).map((f) => f.abs);
  }
  snapshot(key: string): SessionState { return JSON.parse(JSON.stringify(this.get(key))); }
}
