// Dependency set for a skill: ONE level (the skill plus the skills and SOPs it directly names).
// Sources: manifest depends_on and SKILL.md frontmatter depends_on (additive).
// An entry is a skill reference ("38-conversational-ai-system", "38", "conversational-ai-system")
// or an SOP path/glob under the skills tree ("universal-sops/funnel-craft/SOP-FUNNEL-01*.md").
import fs from 'node:fs';
import path from 'node:path';
import { Classifier, SkillIndex, SOPS_NAME } from './classify.js';
import { Manifest } from './manifest.js';
import { makeMatcher } from './glob.js';

export interface Deps { skills: string[]; sopFiles: string[]; missing: string[] }
export interface FileRef { skill: string; rel: string; abs: string }

const ORDER = ['SKILL.md', 'INSTRUCTIONS.md', '__FULL__', 'INSTALL.md', 'QC.md', 'CORE_UPDATES.md', 'README.md'];
function rank(rel: string): number {
  if (!rel.includes('/') && /-full\.md$/i.test(rel)) return ORDER.indexOf('__FULL__');
  const i = ORDER.indexOf(rel);
  return i === -1 ? ORDER.length : i;
}
export function compareRel(a: string, b: string): number {
  return rank(a) - rank(b) || (a < b ? -1 : a > b ? 1 : 0);
}

const SKIP_DIRS = new Set(['.git', 'node_modules', '.venv', '__pycache__']);

/** Every regular file under dir (follows symlinked dirs once), as posix relative paths. Bounded. */
export function walkFiles(dir: string, limit = 60000): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const stack: string[] = [''];
  while (stack.length && out.length < limit) {
    const rel = stack.pop() as string;
    const abs = rel ? path.join(dir, rel) : dir;
    let real = abs;
    try { real = fs.realpathSync(abs); } catch { continue; }
    if (seen.has(real)) continue;
    seen.add(real);
    let ents: fs.Dirent[] = [];
    try { ents = fs.readdirSync(abs, { withFileTypes: true }); } catch { continue; }
    for (const e of ents) {
      const r = rel ? rel + '/' + e.name : e.name;
      if (e.isDirectory()) { if (!SKIP_DIRS.has(e.name)) stack.push(r); continue; }
      if (e.isSymbolicLink()) {
        try {
          const st = fs.statSync(path.join(abs, e.name));
          if (st.isDirectory()) { stack.push(r); continue; }
          if (!st.isFile()) continue;
        } catch { continue; }
      } else if (!e.isFile()) continue;
      out.push(r);
    }
  }
  return out.sort();
}

export class Closure {
  constructor(private index: SkillIndex, private classifier: Classifier, private manifest: Manifest) {}

  directEntries(folder: string): string[] {
    const m = this.manifest.skills.get(folder);
    const info = this.index.info(folder);
    return [...(m ? m.depends_on : []), ...(info ? info.fmDepends : [])];
  }

  dependencies(folder: string): Deps {
    const skills: string[] = [];
    const sopFiles: string[] = [];
    const missing: string[] = [];
    for (const raw of this.directEntries(folder)) {
      const entry = raw.trim();
      if (!entry) continue;
      if (entry.startsWith(SOPS_NAME + '/') || entry === SOPS_NAME) {
        const files = this.expandSop(entry);
        if (files.length === 0) missing.push(entry);
        for (const f of files) if (!sopFiles.includes(f)) sopFiles.push(f);
        continue;
      }
      const dep = this.index.resolve(entry);
      if (!dep) { missing.push(entry); continue; }
      if (dep !== folder && !skills.includes(dep)) skills.push(dep);
    }
    return { skills, sopFiles, missing };
  }

  private expandSop(entry: string): string[] {
    const root = this.index.soPsDir();
    const relPattern = entry.slice(SOPS_NAME.length + 1);
    if (!relPattern) return [];
    const match = makeMatcher([relPattern]);
    const out: string[] = [];
    for (const rel of walkFiles(root)) {
      if (!match(rel)) continue;
      if (this.classifier.classifyRel(SOPS_NAME, rel).cls !== 'instruction') continue;
      out.push(path.join(root, rel));
    }
    return out;
  }

  /** Instruction files of one skill folder, in reading order. upfrontOnly: root-level docs only (the required set). */
  instructionFiles(folder: string, upfrontOnly = false): FileRef[] {
    const info = this.index.info(folder);
    if (!info) return [];
    const refs: FileRef[] = [];
    for (const rel of walkFiles(info.dir)) {
      const c = this.classifier.classifyRel(folder, rel);
      if (c.cls === 'instruction' && (!upfrontOnly || c.upfront)) refs.push({ skill: folder, rel, abs: path.join(info.dir, rel) });
    }
    return refs.sort((a, b) => compareRel(a.rel, b.rel));
  }

  /** The REQUIRED UPFRONT set for `folder` (root-level docs, no step folders): itself, then each direct dependency, then named SOP files. */
  requiredFiles(folder: string): { files: FileRef[]; deps: Deps } {
    const deps = this.dependencies(folder);
    const files: FileRef[] = [...this.instructionFiles(folder, true)];
    // A direct dependency contributes only its SKILL.md upfront; its other root docs are read whole when opened.
    for (const d of deps.skills) files.push(...this.instructionFiles(d, true).filter((f) => f.rel === 'SKILL.md'));
    const sopsRoot = this.index.soPsDir();
    for (const abs of deps.sopFiles) files.push({ skill: SOPS_NAME, rel: path.relative(sopsRoot, abs).split(path.sep).join('/'), abs });
    return { files, deps };
  }

  /** Cycles in the depends_on graph (informational; one-level closure is cycle-safe). */
  findCycles(): string[][] {
    const graph = new Map<string, string[]>();
    for (const i of this.index.list()) graph.set(i.folder, this.dependencies(i.folder).skills);
    const cycles: string[][] = [];
    const state = new Map<string, number>();
    const stack: string[] = [];
    const visit = (n: string) => {
      state.set(n, 1);
      stack.push(n);
      for (const m of graph.get(n) || []) {
        if (state.get(m) === 1) cycles.push([...stack.slice(stack.indexOf(m)), m]);
        else if (!state.get(m)) visit(m);
      }
      stack.pop();
      state.set(n, 2);
    };
    for (const n of graph.keys()) if (!state.get(n)) visit(n);
    return cycles;
  }
}
