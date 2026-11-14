// Central manifest loader. Shards live in manifest.d/*.json:
//   { "version": 1, "skills": [ { "skill": "67-kie-video", "depends_on": [...],
//       "lookup": [ {"glob": "models.json", "why": "..."} ],
//       "external_lookup_roots": [ "$HOME/..." ] } ] }
// `_defaults.json` holds { "defaults": { "lookup": [ {glob, why} ] } } applied to every skill.
// Two classes only: INSTRUCTION (read in full) and LOOKUP (searchable). Anything not
// matched by a lookup glob is INSTRUCTION when it is markdown, LOOKUP otherwise (code/data).
// HARD RULE: the root instruction names below can never be lookup, whatever a shard says.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { makeMatcher } from './glob.js';

export const INSTRUCTION_ROOT_NAMES = ['SKILL.md', 'INSTRUCTIONS.md', 'INSTALL.md', 'QC.md', 'CORE_UPDATES.md', 'README.md'];

/** True when the skill-relative path is instruction by name alone (never lookup, never auto-exempt). */
export function isInstructionByName(rel: string): boolean {
  if (INSTRUCTION_ROOT_NAMES.includes(rel)) return true;
  return !rel.includes('/') && /-full\.md$/i.test(rel);
}

export interface LookupRule { glob: string; why?: string }
export interface SkillEntry {
  skill: string;
  depends_on: string[];
  lookup: LookupRule[];
  instruction: string[];
  /** Subfolder instruction files that must still be read upfront (rare). Default: only root-level files are upfront. */
  upfront: string[];
  external_lookup_roots: string[];
  /** Same roots with their flags. optional:true means a missing folder is expected and never an error. */
  external_roots: { path: string; optional: boolean }[];
}
export interface Manifest {
  defaults: LookupRule[];
  skills: Map<string, SkillEntry>;
  errors: string[];
  files: string[];
}

export function expandRoot(p: string, env: Record<string, string | undefined> = process.env): string {
  let out = p.replace(/\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?/g, (_m, name) => (name === 'HOME' ? env.HOME || os.homedir() : env[name] ?? ''));
  if (out.startsWith('~')) out = path.join(os.homedir(), out.slice(1));
  return out;
}

function ruleList(v: any, where: string, errors: string[]): LookupRule[] {
  if (v === undefined) return [];
  if (!Array.isArray(v)) { errors.push(`${where}: lookup must be a list`); return []; }
  const out: LookupRule[] = [];
  for (const r of v) {
    const glob = typeof r === 'string' ? r : r && typeof r.glob === 'string' ? r.glob : '';
    if (!glob) { errors.push(`${where}: lookup entry without a glob`); continue; }
    out.push({ glob, why: typeof r === 'object' ? r.why : undefined });
  }
  return out;
}

/** Names a lookup glob must never match (hard rule). Returns the offending names. */
export function globHitsInstructionNames(glob: string): string[] {
  const m = makeMatcher([glob]);
  const probes = [...INSTRUCTION_ROOT_NAMES, 'example-full.md', 'ghl-convert-and-flow-full.md'];
  return probes.filter((n) => m(n));
}

/** Drop (and report) any lookup rule that would exempt an instruction name. */
export function sanitizeRules(rules: LookupRule[], where: string, errors: string[]): LookupRule[] {
  const keep: LookupRule[] = [];
  for (const r of rules) {
    const hits = globHitsInstructionNames(r.glob);
    if (hits.length) errors.push(`${where}: lookup glob "${r.glob}" matches instruction file name(s) ${hits.join(', ')}; rule dropped`);
    else keep.push(r);
  }
  return keep;
}

export function loadManifest(dir: string): Manifest {
  const mf: Manifest = { defaults: [], skills: new Map(), errors: [], files: [] };
  let names: string[] = [];
  try { names = fs.readdirSync(dir).filter((n) => n.endsWith('.json')).sort(); } catch (e) {
    mf.errors.push(`manifest directory unreadable: ${dir}`);
    return mf;
  }
  for (const n of names) {
    const file = path.join(dir, n);
    mf.files.push(n);
    let data: any;
    try { data = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { mf.errors.push(`${n}: invalid JSON`); continue; }
    if (data.defaults) {
      mf.defaults.push(...sanitizeRules(ruleList(data.defaults.lookup, `${n} defaults`, mf.errors), `${n} defaults`, mf.errors));
    }
    for (const s of Array.isArray(data.skills) ? data.skills : []) {
      if (!s || typeof s.skill !== 'string') { mf.errors.push(`${n}: skill entry without a name`); continue; }
      const prev = mf.skills.get(s.skill);
      const entry: SkillEntry = prev || { skill: s.skill, depends_on: [], lookup: [], instruction: [], upfront: [], external_lookup_roots: [], external_roots: [] };
      if (prev) mf.errors.push(`${n}: skill ${s.skill} appears in more than one shard (merged)`);
      entry.depends_on.push(...(Array.isArray(s.depends_on) ? s.depends_on.filter((x: any) => typeof x === 'string') : []));
      entry.lookup.push(...sanitizeRules(ruleList(s.lookup, `${n} ${s.skill}`, mf.errors), `${n} ${s.skill}`, mf.errors));
      entry.upfront.push(...(Array.isArray(s.upfront) ? s.upfront.filter((x: any) => typeof x === 'string') : []));
      entry.instruction.push(...(Array.isArray(s.instruction) ? s.instruction.filter((x: any) => typeof x === 'string') : []));
      for (const r of Array.isArray(s.external_lookup_roots) ? s.external_lookup_roots : []) {
        const pth = typeof r === 'string' ? r : r && typeof r.path === 'string' ? r.path : '';
        if (!pth) continue;
        entry.external_lookup_roots.push(pth);
        entry.external_roots.push({ path: pth, optional: typeof r === 'object' ? r.optional === true : false });
      }
      mf.skills.set(s.skill, entry);
    }
  }
  return mf;
}
