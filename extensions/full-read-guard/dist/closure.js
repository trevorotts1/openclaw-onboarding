// Dependency set for a skill: ONE level (the skill plus the skills and SOPs it directly names).
// Sources: manifest depends_on and SKILL.md frontmatter depends_on (additive).
// An entry is a skill reference ("38-conversational-ai-system", "38", "conversational-ai-system")
// or an SOP path/glob under the skills tree ("universal-sops/funnel-craft/SOP-FUNNEL-01*.md").
import fs from 'node:fs';
import path from 'node:path';
import { SOPS_NAME } from './classify.js';
import { makeMatcher } from './glob.js';
const ORDER = ['SKILL.md', 'INSTRUCTIONS.md', '__FULL__', 'INSTALL.md', 'QC.md', 'CORE_UPDATES.md', 'README.md'];
function rank(rel) {
    if (!rel.includes('/') && /-full\.md$/i.test(rel))
        return ORDER.indexOf('__FULL__');
    const i = ORDER.indexOf(rel);
    return i === -1 ? ORDER.length : i;
}
export function compareRel(a, b) {
    return rank(a) - rank(b) || (a < b ? -1 : a > b ? 1 : 0);
}
const SKIP_DIRS = new Set(['.git', 'node_modules', '.venv', '__pycache__']);
/** Every regular file under dir (follows symlinked dirs once), as posix relative paths. Bounded. */
export function walkFiles(dir, limit = 60000) {
    const out = [];
    const seen = new Set();
    const stack = [''];
    while (stack.length && out.length < limit) {
        const rel = stack.pop();
        const abs = rel ? path.join(dir, rel) : dir;
        let real = abs;
        try {
            real = fs.realpathSync(abs);
        }
        catch {
            continue;
        }
        if (seen.has(real))
            continue;
        seen.add(real);
        let ents = [];
        try {
            ents = fs.readdirSync(abs, { withFileTypes: true });
        }
        catch {
            continue;
        }
        for (const e of ents) {
            const r = rel ? rel + '/' + e.name : e.name;
            if (e.isDirectory()) {
                if (!SKIP_DIRS.has(e.name))
                    stack.push(r);
                continue;
            }
            if (e.isSymbolicLink()) {
                try {
                    const st = fs.statSync(path.join(abs, e.name));
                    if (st.isDirectory()) {
                        stack.push(r);
                        continue;
                    }
                    if (!st.isFile())
                        continue;
                }
                catch {
                    continue;
                }
            }
            else if (!e.isFile())
                continue;
            out.push(r);
        }
    }
    return out.sort();
}
export class Closure {
    index;
    classifier;
    manifest;
    constructor(index, classifier, manifest) {
        this.index = index;
        this.classifier = classifier;
        this.manifest = manifest;
    }
    directEntries(folder) {
        const m = this.manifest.skills.get(folder);
        const info = this.index.info(folder);
        return [...(m ? m.depends_on : []), ...(info ? info.fmDepends : [])];
    }
    dependencies(folder) {
        const skills = [];
        const sopFiles = [];
        const missing = [];
        for (const raw of this.directEntries(folder)) {
            const entry = raw.trim();
            if (!entry)
                continue;
            if (entry.startsWith(SOPS_NAME + '/') || entry === SOPS_NAME) {
                const files = this.expandSop(entry);
                if (files.length === 0)
                    missing.push(entry);
                for (const f of files)
                    if (!sopFiles.includes(f))
                        sopFiles.push(f);
                continue;
            }
            const dep = this.index.resolve(entry);
            if (!dep) {
                missing.push(entry);
                continue;
            }
            if (dep !== folder && !skills.includes(dep))
                skills.push(dep);
        }
        return { skills, sopFiles, missing };
    }
    expandSop(entry) {
        const root = this.index.soPsDir();
        const relPattern = entry.slice(SOPS_NAME.length + 1);
        if (!relPattern)
            return [];
        const match = makeMatcher([relPattern]);
        const out = [];
        for (const rel of walkFiles(root)) {
            if (!match(rel))
                continue;
            if (this.classifier.classifyRel(SOPS_NAME, rel).cls !== 'instruction')
                continue;
            out.push(path.join(root, rel));
        }
        return out;
    }
    /** Instruction files of one skill folder, in reading order. upfrontOnly: root-level docs only (the required set). */
    instructionFiles(folder, upfrontOnly = false) {
        const info = this.index.info(folder);
        if (!info)
            return [];
        const refs = [];
        for (const rel of walkFiles(info.dir)) {
            const c = this.classifier.classifyRel(folder, rel);
            if (c.cls === 'instruction' && (!upfrontOnly || c.upfront))
                refs.push({ skill: folder, rel, abs: path.join(info.dir, rel) });
        }
        return refs.sort((a, b) => compareRel(a.rel, b.rel));
    }
    /** The REQUIRED UPFRONT set for `folder` (root-level docs, no step folders): itself, then each direct dependency, then named SOP files. */
    requiredFiles(folder) {
        const deps = this.dependencies(folder);
        const files = [...this.instructionFiles(folder, true)];
        // A direct dependency contributes only its SKILL.md upfront; its other root docs are read whole when opened.
        for (const d of deps.skills)
            files.push(...this.instructionFiles(d, true).filter((f) => f.rel === 'SKILL.md'));
        const sopsRoot = this.index.soPsDir();
        for (const abs of deps.sopFiles)
            files.push({ skill: SOPS_NAME, rel: path.relative(sopsRoot, abs).split(path.sep).join('/'), abs });
        return { files, deps };
    }
    /** Cycles in the depends_on graph (informational; one-level closure is cycle-safe). */
    findCycles() {
        const graph = new Map();
        for (const i of this.index.list())
            graph.set(i.folder, this.dependencies(i.folder).skills);
        const cycles = [];
        const state = new Map();
        const stack = [];
        const visit = (n) => {
            state.set(n, 1);
            stack.push(n);
            for (const m of graph.get(n) || []) {
                if (state.get(m) === 1)
                    cycles.push([...stack.slice(stack.indexOf(m)), m]);
                else if (!state.get(m))
                    visit(m);
            }
            stack.pop();
            state.set(n, 2);
        };
        for (const n of graph.keys())
            if (!state.get(n))
                visit(n);
        return cycles;
    }
}
