// Per-session read receipts. File level: abs path -> sha256 delivered to the model.
// Memory first, mirrored to <stateDir>/<session>.json. Reset on session start/end and after compaction.
import fs from 'node:fs';
import path from 'node:path';
import { fileSha, safeReal } from './paths.js';
function empty() { return { files: {}, inUse: {}, progress: {} }; }
function safeName(key) { return key.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 120) || 'default'; }
export class Receipts {
    stateDir;
    now;
    sessions = new Map();
    constructor(stateDir, now = Date.now) {
        this.stateDir = stateDir;
        this.now = now;
    }
    get(key) {
        let s = this.sessions.get(key);
        if (s)
            return s;
        s = empty();
        if (this.stateDir) {
            try {
                const raw = JSON.parse(fs.readFileSync(path.join(this.stateDir, safeName(key) + '.json'), 'utf8'));
                if (raw && typeof raw.files === 'object')
                    s = { files: raw.files || {}, inUse: raw.inUse || {}, progress: raw.progress || {} };
            }
            catch { /* no mirror yet */ }
        }
        this.sessions.set(key, s);
        return s;
    }
    persist(key) {
        if (!this.stateDir)
            return;
        try {
            fs.mkdirSync(this.stateDir, { recursive: true });
            const file = path.join(this.stateDir, safeName(key) + '.json');
            const tmp = file + '.tmp-' + process.pid;
            fs.writeFileSync(tmp, JSON.stringify(this.sessions.get(key)));
            fs.renameSync(tmp, file);
        }
        catch { /* mirror is best effort; memory is authoritative */ }
    }
    reset(key) {
        this.sessions.set(key, empty());
        if (this.stateDir) {
            try {
                fs.rmSync(path.join(this.stateDir, safeName(key) + '.json'), { force: true });
            }
            catch { /* ignore */ }
        }
    }
    // Keys are real paths, so a skills tree reached through a symlink (macOS /var -> /private/var,
    // linked skill folders) matches the realpath the classifier reports.
    markFile(key, abs, sha, persist = true) {
        this.get(key).files[safeReal(abs)] = sha;
        if (persist)
            this.persist(key);
    }
    flush(key) { this.persist(key); }
    /** True only when the file was delivered AND is unchanged on disk since. */
    hasFile(key, abs) {
        const real = safeReal(abs);
        const want = this.get(key).files[real];
        if (!want)
            return false;
        return fileSha(real) === want;
    }
    markInUse(key, folder) {
        const s = this.get(key);
        if (!s.inUse[folder]) {
            s.inUse[folder] = this.now();
            this.persist(key);
        }
    }
    inUse(key) { return Object.keys(this.get(key).inUse); }
    progress(key, bundle) { return this.get(key).progress[bundle]; }
    setProgress(key, bundle, p) { this.get(key).progress[bundle] = p; this.persist(key); }
    missing(key, files) {
        return files.filter((f) => !this.hasFile(key, f.abs)).map((f) => f.abs);
    }
    snapshot(key) { return JSON.parse(JSON.stringify(this.get(key))); }
}
