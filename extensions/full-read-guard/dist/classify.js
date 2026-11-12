// Path -> { skill, rel, class }. Two classes: instruction | lookup. `outside` means not a skill/SOP file.
import fs from 'node:fs';
import path from 'node:path';
import { parseFrontmatter, asList } from './frontmatter.js';
import { makeMatcher } from './glob.js';
import { isInstructionByName, sanitizeRules, expandRoot } from './manifest.js';
import { safeReal, normalizeInputPath } from './paths.js';
export const SOPS_NAME = 'universal-sops';
export class SkillIndex {
    roots;
    manifest;
    ttlMs;
    byFolder = new Map();
    alias = new Map();
    builtAt = 0;
    realSkillsDir;
    constructor(roots, manifest, ttlMs = 5000) {
        this.roots = roots;
        this.manifest = manifest;
        this.ttlMs = ttlMs;
        this.realSkillsDir = safeReal(roots.skillsDir);
    }
    get skillsReal() { return this.realSkillsDir; }
    refresh(force = false) {
        const now = Date.now();
        if (!force && this.builtAt && now - this.builtAt < this.ttlMs)
            return;
        this.builtAt = now;
        this.byFolder.clear();
        this.alias.clear();
        this.realSkillsDir = safeReal(this.roots.skillsDir);
        let names = [];
        try {
            names = fs.readdirSync(this.roots.skillsDir);
        }
        catch {
            return;
        }
        for (const folder of names.sort()) {
            if (folder.startsWith('.') || folder === SOPS_NAME)
                continue;
            const dir = path.join(this.roots.skillsDir, folder);
            let isSkill = false;
            try {
                isSkill = fs.statSync(path.join(dir, 'SKILL.md')).isFile();
            }
            catch { /* not a skill */ }
            if (!isSkill)
                continue;
            let fm = {};
            try {
                fm = parseFrontmatter(fs.readFileSync(path.join(dir, 'SKILL.md'), 'utf8'));
            }
            catch { /* ignore */ }
            const info = { folder, dir, name: typeof fm.name === 'string' ? fm.name : undefined, fmDepends: asList(fm.depends_on), fmLookup: asList(fm.lookup) };
            this.byFolder.set(folder, info);
            this.alias.set(folder.toLowerCase(), folder);
            const noNum = folder.replace(/^\d+-/, '').toLowerCase();
            if (!this.alias.has(noNum))
                this.alias.set(noNum, folder);
            const num = /^(\d+)-/.exec(folder);
            if (num) {
                this.alias.set(num[1], folder);
                this.alias.set(String(parseInt(num[1], 10)), folder);
            }
            if (info.name && !this.alias.has(info.name.toLowerCase()))
                this.alias.set(info.name.toLowerCase(), folder);
        }
    }
    list() { this.refresh(); return [...this.byFolder.values()]; }
    info(folder) { this.refresh(); return this.byFolder.get(folder); }
    /** Resolve "67-kie-video" | "67" | "kie-video" | frontmatter name -> folder. */
    resolve(query) {
        this.refresh();
        const q = query.trim().replace(/\/+$/, '').toLowerCase();
        return this.alias.get(q);
    }
    /** Folder that owns a real path under the skills dir, plus the path relative to it. */
    owner(realAbs) {
        this.refresh();
        const root = this.realSkillsDir;
        const relToRoot = path.relative(root, realAbs);
        if (relToRoot === '' || relToRoot.startsWith('..') || path.isAbsolute(relToRoot)) {
            return this.ownerViaSymlinkedSkill(realAbs);
        }
        const parts = relToRoot.split(path.sep);
        if (parts[0] === SOPS_NAME)
            return parts.length > 1 ? { sops: true, rel: parts.slice(1).join('/') } : null;
        if (parts.length < 2 || !this.byFolder.has(parts[0]))
            return null;
        return { folder: parts[0], rel: parts.slice(1).join('/') };
    }
    // A skill folder may itself be a symlink to a tree outside the skills dir (vendored copies).
    ownerViaSymlinkedSkill(realAbs) {
        for (const info of this.byFolder.values()) {
            const rd = safeReal(info.dir);
            const rel = path.relative(rd, realAbs);
            if (rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel))
                return { folder: info.folder, rel: rel.split(path.sep).join('/') };
        }
        return null;
    }
    soPsDir() { return path.join(this.roots.skillsDir, SOPS_NAME); }
}
export class Classifier {
    index;
    manifest;
    env;
    matchers = new Map();
    externals = null;
    constructor(index, manifest, env = process.env) {
        this.index = index;
        this.manifest = manifest;
        this.env = env;
    }
    rulesFor(skill) {
        const info = skill === SOPS_NAME ? undefined : this.index.info(skill);
        const key = skill + '|' + (info ? info.fmLookup.join(',') : '');
        const hit = this.matchers.get(key);
        if (hit)
            return hit;
        const entry = this.manifest.skills.get(skill);
        const errs = [];
        const fmRules = sanitizeRules((info ? info.fmLookup : []).map((g) => ({ glob: g })), `frontmatter ${skill}`, errs);
        const globs = [...this.manifest.defaults, ...(entry ? entry.lookup : []), ...fmRules].map((r) => r.glob);
        const built = { lookup: makeMatcher(globs), instruction: makeMatcher(entry ? entry.instruction : []) };
        this.matchers.set(key, built);
        return built;
    }
    classifyRel(skill, rel) {
        if (skill !== SOPS_NAME && isInstructionByName(rel))
            return { cls: 'instruction', reason: 'instruction file name' };
        const r = this.rulesFor(skill);
        if (r.instruction(rel))
            return { cls: 'instruction', reason: 'manifest instruction' };
        if (r.lookup(rel))
            return { cls: 'lookup', reason: 'manifest lookup' };
        if (/\.(md|markdown|mdx)$/i.test(rel))
            return { cls: 'instruction', reason: 'markdown not listed as lookup' };
        return { cls: 'lookup', reason: 'code or data' };
    }
    externalRoots() {
        if (this.externals)
            return this.externals;
        const out = [];
        for (const e of this.manifest.skills.values())
            for (const r of e.external_lookup_roots) {
                const exp = expandRoot(r.replace('{skills}', this.index.roots.skillsDir), this.env);
                if (exp)
                    out.push({ root: safeReal(exp), skill: e.skill });
            }
        this.externals = out;
        return out;
    }
    /** Classify any input path. `cwds` are directories to try for relative paths. */
    classify(input, cwds = []) {
        const n = normalizeInputPath(input);
        const candidates = [];
        if (n.kind === 'workspace-skill') {
            const folder = this.index.resolve(n.name);
            if (!folder)
                return { scope: 'outside' };
            candidates.push(path.join(this.index.roots.skillsDir, folder, n.rel));
        }
        else if (path.isAbsolute(n.path)) {
            candidates.push(n.path);
        }
        else {
            for (const c of cwds)
                candidates.push(path.resolve(c, n.path));
            candidates.push(path.resolve(n.path));
        }
        for (const c of candidates) {
            const hit = this.classifyAbs(c);
            if (hit.scope !== 'outside')
                return hit;
        }
        // Tail match: a relative or copied path such as "workspace/skills/67-kie-video/SKILL.md".
        if (n.kind === 'fs') {
            const segs = n.path.split(/[\\/]+/).filter(Boolean);
            for (let i = 0; i < segs.length; i++) {
                const isSops = segs[i] === SOPS_NAME;
                const isSkill = !isSops && this.index.info(segs[i]) !== undefined;
                if (!isSops && !isSkill)
                    continue;
                const guess = path.join(this.index.roots.skillsDir, ...segs.slice(i));
                if (fs.existsSync(guess)) {
                    const hit = this.classifyAbs(guess);
                    if (hit.scope !== 'outside')
                        return hit;
                }
            }
        }
        return { scope: 'outside' };
    }
    classifyAbs(abs) {
        const real = safeReal(abs);
        const own = this.index.owner(real);
        if (own && 'sops' in own) {
            const c = this.classifyRel(SOPS_NAME, own.rel);
            return { scope: 'skill', skill: SOPS_NAME, rel: own.rel, abs: real, cls: c.cls, reason: c.reason };
        }
        if (own && 'folder' in own) {
            const c = this.classifyRel(own.folder, own.rel);
            return { scope: 'skill', skill: own.folder, rel: own.rel, abs: real, cls: c.cls, reason: c.reason };
        }
        for (const e of this.externalRoots()) {
            const rel = path.relative(e.root, real);
            if (rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel))
                return { scope: 'external', skill: e.skill, abs: real, cls: 'lookup', reason: 'external lookup root' };
        }
        return { scope: 'outside' };
    }
}
