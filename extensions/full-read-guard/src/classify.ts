// Path -> { skill, rel, class }. Two classes: instruction | lookup. `outside` means not a skill/SOP file.
import fs from 'node:fs';
import path from 'node:path';
import { parseFrontmatter, asList } from './frontmatter.js';
import { makeMatcher } from './glob.js';
import { Manifest, isInstructionByName, sanitizeRules, expandRoot, SkillEntry } from './manifest.js';
import { Roots, safeReal, normalizeInputPath } from './paths.js';

/** Root-level docs that are about installing, wiring, checking or archiving the skill, not about doing its work. Still instruction (never partial), but read whole when opened, not required upfront. */
export function isSetupOrArchiveDoc(rel: string): boolean {
  return ['INSTALL.md', 'CORE_UPDATES.md', 'QC.md', 'README.md'].includes(rel) || /-full\.md$/i.test(rel);
}

export const SOPS_NAME = 'universal-sops';

export type Classification =
  | { scope: 'outside' }
  | { scope: 'skill'; skill: string; rel: string; abs: string; cls: 'instruction' | 'lookup'; upfront: boolean; reason: string }
  | { scope: 'external'; skill: string; abs: string; cls: 'lookup'; reason: string };

export interface SkillInfo { folder: string; dir: string; name?: string; fmDepends: string[]; fmLookup: string[] }

export class SkillIndex {
  private byFolder = new Map<string, SkillInfo>();
  private alias = new Map<string, string>();
  private builtAt = 0;
  private realSkillsDir: string;
  constructor(public roots: Roots, public manifest: Manifest, private ttlMs = 5000) {
    this.realSkillsDir = safeReal(roots.skillsDir);
  }
  get skillsReal(): string { return this.realSkillsDir; }
  refresh(force = false): void {
    const now = Date.now();
    if (!force && this.builtAt && now - this.builtAt < this.ttlMs) return;
    this.builtAt = now;
    this.byFolder.clear();
    this.alias.clear();
    this.realSkillsDir = safeReal(this.roots.skillsDir);
    let names: string[] = [];
    try { names = fs.readdirSync(this.roots.skillsDir); } catch { return; }
    for (const folder of names.sort()) {
      if (folder.startsWith('.') || folder === SOPS_NAME) continue;
      const dir = path.join(this.roots.skillsDir, folder);
      let isSkill = false;
      try { isSkill = fs.statSync(path.join(dir, 'SKILL.md')).isFile(); } catch { /* not a skill */ }
      if (!isSkill) continue;
      let fm: Record<string, any> = {};
      try { fm = parseFrontmatter(fs.readFileSync(path.join(dir, 'SKILL.md'), 'utf8')); } catch { /* ignore */ }
      const info: SkillInfo = { folder, dir, name: typeof fm.name === 'string' ? fm.name : undefined, fmDepends: asList(fm.depends_on), fmLookup: asList(fm.lookup) };
      this.byFolder.set(folder, info);
      this.alias.set(folder.toLowerCase(), folder);
      const noNum = folder.replace(/^\d+-/, '').toLowerCase();
      if (!this.alias.has(noNum)) this.alias.set(noNum, folder);
      const num = /^(\d+)-/.exec(folder);
      if (num) { this.alias.set(num[1], folder); this.alias.set(String(parseInt(num[1], 10)), folder); }
      if (info.name && !this.alias.has(info.name.toLowerCase())) this.alias.set(info.name.toLowerCase(), folder);
    }
  }
  list(): SkillInfo[] { this.refresh(); return [...this.byFolder.values()]; }
  info(folder: string): SkillInfo | undefined { this.refresh(); return this.byFolder.get(folder); }
  /** Resolve "67-kie-video" | "67" | "kie-video" | frontmatter name -> folder. */
  resolve(query: string): string | undefined {
    this.refresh();
    const q = query.trim().replace(/\/+$/, '').toLowerCase();
    return this.alias.get(q);
  }
  /** Folder that owns a real path under the skills dir, plus the path relative to it. */
  owner(realAbs: string): { folder: string; rel: string } | { sops: true; rel: string } | null {
    this.refresh();
    const root = this.realSkillsDir;
    const relToRoot = path.relative(root, realAbs);
    if (relToRoot === '' || relToRoot.startsWith('..') || path.isAbsolute(relToRoot)) {
      return this.ownerViaSymlinkedSkill(realAbs);
    }
    const parts = relToRoot.split(path.sep);
    if (parts[0] === SOPS_NAME) return parts.length > 1 ? { sops: true, rel: parts.slice(1).join('/') } : null;
    if (parts.length < 2 || !this.byFolder.has(parts[0])) return null;
    return { folder: parts[0], rel: parts.slice(1).join('/') };
  }
  // A skill folder may itself be a symlink to a tree outside the skills dir (vendored copies).
  private ownerViaSymlinkedSkill(realAbs: string): { folder: string; rel: string } | null {
    for (const info of this.byFolder.values()) {
      const rd = safeReal(info.dir);
      const rel = path.relative(rd, realAbs);
      if (rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel)) return { folder: info.folder, rel: rel.split(path.sep).join('/') };
    }
    return null;
  }
  soPsDir(): string { return path.join(this.roots.skillsDir, SOPS_NAME); }
}

export class Classifier {
  private matchers = new Map<string, { lookup: (rel: string) => boolean; instruction: (rel: string) => boolean; upfront: (rel: string) => boolean }>();
  private externals: { root: string; skill: string }[] | null = null;
  constructor(public index: SkillIndex, public manifest: Manifest, private env: Record<string, string | undefined> = process.env) {}

  private rulesFor(skill: string): { lookup: (rel: string) => boolean; instruction: (rel: string) => boolean; upfront: (rel: string) => boolean } {
    const info = skill === SOPS_NAME ? undefined : this.index.info(skill);
    const key = skill + '|' + (info ? info.fmLookup.join(',') : '');
    const hit = this.matchers.get(key);
    if (hit) return hit;
    const entry: SkillEntry | undefined = this.manifest.skills.get(skill);
    const errs: string[] = [];
    const fmRules = sanitizeRules((info ? info.fmLookup : []).map((g) => ({ glob: g })), `frontmatter ${skill}`, errs);
    const globs = [...this.manifest.defaults, ...(entry ? entry.lookup : []), ...fmRules].map((r) => r.glob);
    const built = { lookup: makeMatcher(globs), instruction: makeMatcher(entry ? entry.instruction : []), upfront: makeMatcher(entry ? entry.upfront : []) };
    this.matchers.set(key, built);
    return built;
  }

  /** Two classes: instruction | lookup. Instruction files are upfront (root-level docs) or read-on-open (step folders). */
  classifyRel(skill: string, rel: string): { cls: 'instruction' | 'lookup'; upfront: boolean; reason: string } {
    const r = this.rulesFor(skill);
    const upfront = skill !== SOPS_NAME && ((!rel.includes('/') && !isSetupOrArchiveDoc(rel)) || r.upfront(rel));
    if (skill !== SOPS_NAME && isInstructionByName(rel)) return { cls: 'instruction', upfront, reason: upfront ? 'instruction file name (upfront)' : 'instruction file name (setup/maintenance doc: read whole when opened)' };
    if (r.instruction(rel)) return { cls: 'instruction', upfront, reason: 'manifest instruction' };
    if (r.lookup(rel)) return { cls: 'lookup', upfront: false, reason: 'manifest lookup' };
    if (/\.(md|markdown|mdx)$/i.test(rel)) return { cls: 'instruction', upfront, reason: upfront ? 'root-level markdown' : 'step-folder markdown (read whole when opened)' };
    return { cls: 'lookup', upfront: false, reason: 'code or data' };
  }

  private externalRoots(): { root: string; skill: string }[] {
    if (this.externals) return this.externals;
    const out: { root: string; skill: string }[] = [];
    for (const e of this.manifest.skills.values()) for (const r of e.external_lookup_roots) {
      const exp = expandRoot(r.replace('{skills}', this.index.roots.skillsDir), this.env);
      if (exp) out.push({ root: safeReal(exp), skill: e.skill });
    }
    this.externals = out;
    return out;
  }

  /** Classify any input path. `cwds` are directories to try for relative paths. */
  classify(input: string, cwds: string[] = []): Classification {
    const n = normalizeInputPath(input);
    const candidates: string[] = [];
    if (n.kind === 'workspace-skill') {
      const folder = this.index.resolve(n.name);
      if (!folder) return { scope: 'outside' };
      candidates.push(path.join(this.index.roots.skillsDir, folder, n.rel));
    } else if (path.isAbsolute(n.path)) {
      candidates.push(n.path);
    } else {
      for (const c of cwds) candidates.push(path.resolve(c, n.path));
      candidates.push(path.resolve(n.path));
    }
    for (const c of candidates) {
      const hit = this.classifyAbs(c);
      if (hit.scope !== 'outside') return hit;
    }
    // Tail match: a relative or copied path such as "workspace/skills/67-kie-video/SKILL.md".
    if (n.kind === 'fs') {
      const segs = n.path.split(/[\\/]+/).filter(Boolean);
      for (let i = 0; i < segs.length; i++) {
        const isSops = segs[i] === SOPS_NAME;
        const isSkill = !isSops && this.index.info(segs[i]) !== undefined;
        if (!isSops && !isSkill) continue;
        const guess = path.join(this.index.roots.skillsDir, ...segs.slice(i));
        if (fs.existsSync(guess)) {
          const hit = this.classifyAbs(guess);
          if (hit.scope !== 'outside') return hit;
        }
      }
    }
    return { scope: 'outside' };
  }

  classifyAbs(abs: string): Classification {
    const real = safeReal(abs);
    const own = this.index.owner(real);
    if (own && 'sops' in own) {
      const c = this.classifyRel(SOPS_NAME, own.rel);
      return { scope: 'skill', skill: SOPS_NAME, rel: own.rel, abs: real, cls: c.cls, upfront: c.upfront, reason: c.reason };
    }
    if (own && 'folder' in own) {
      const c = this.classifyRel(own.folder, own.rel);
      return { scope: 'skill', skill: own.folder, rel: own.rel, abs: real, cls: c.cls, upfront: c.upfront, reason: c.reason };
    }
    for (const e of this.externalRoots()) {
      const rel = path.relative(e.root, real);
      if (rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel)) return { scope: 'external', skill: e.skill, abs: real, cls: 'lookup', reason: 'external lookup root' };
    }
    return { scope: 'outside' };
  }
}
