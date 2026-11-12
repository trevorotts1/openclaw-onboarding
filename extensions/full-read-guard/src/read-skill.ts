// The read_skill tool: whole skill + one level of dependencies, in order, chunked, with a receipt.
import fs from 'node:fs';
import { Closure, FileRef } from './closure.js';
import { SkillIndex } from './classify.js';
import { Manifest, expandRoot } from './manifest.js';
import { Receipts } from './receipts.js';
import { sha256 } from './paths.js';

export interface BundleFile { ref: FileRef; text: string; bytes: number; sha: string; role: 'skill' | 'dependency' | 'sop'; start: number; end: number }
export interface Bundle {
  skill: string;
  files: BundleFile[];
  stream: string;
  parts: { start: number; end: number }[];
  signature: string;
  missingDeps: string[];
  depSkills: string[];
}

export const DEFAULT_CHUNK_CHARS = 40000;

export function fileHeader(f: { skill: string; rel: string; bytes: number; sha: string }): string {
  return `===== FILE ${f.skill}/${f.rel} (${f.bytes} bytes, sha256 ${f.sha}) =====\n`;
}
export function fileFooter(f: { skill: string; rel: string }): string {
  return `\n===== END ${f.skill}/${f.rel} =====\n`;
}

/** Split [0, len) into parts that end at a line break where possible. Concatenating the slices gives back the stream exactly. */
export function splitParts(stream: string, chunk: number): { start: number; end: number }[] {
  const parts: { start: number; end: number }[] = [];
  let pos = 0;
  while (pos < stream.length) {
    let end = Math.min(stream.length, pos + chunk);
    if (end < stream.length) {
      const nl = stream.lastIndexOf('\n', end - 1);
      if (nl > pos) end = nl + 1;
    }
    parts.push({ start: pos, end });
    pos = end;
  }
  if (parts.length === 0) parts.push({ start: 0, end: 0 });
  return parts;
}

export class ReadSkillService {
  constructor(private index: SkillIndex, private closure: Closure, private manifest: Manifest, private receipts: Receipts, private chunkChars = DEFAULT_CHUNK_CHARS) {}

  build(folder: string): Bundle {
    const { files: refs, deps } = this.closure.requiredFiles(folder);
    const files: BundleFile[] = [];
    let stream = '';
    const seen = new Set<string>();
    for (const ref of refs) {
      if (seen.has(ref.abs)) continue;
      seen.add(ref.abs);
      let buf: Buffer;
      try { buf = fs.readFileSync(ref.abs); } catch { continue; }
      const text = buf.toString('utf8');
      const sha = sha256(buf);
      const role: BundleFile['role'] = ref.skill === folder ? 'skill' : ref.skill === 'universal-sops' ? 'sop' : 'dependency';
      const head = fileHeader({ skill: ref.skill, rel: ref.rel, bytes: buf.length, sha });
      const start = stream.length;
      stream += head + text + fileFooter(ref);
      files.push({ ref, text, bytes: buf.length, sha, role, start, end: stream.length });
    }
    const parts = splitParts(stream, this.chunkChars);
    const signature = sha256(files.map((f) => f.ref.abs + ':' + f.sha).join('\n'));
    return { skill: folder, files, stream, parts, signature, missingDeps: deps.missing, depSkills: deps.skills };
  }

  private lookupNote(folder: string): string {
    const m = this.manifest.skills.get(folder);
    const lines: string[] = [];
    const rules = m ? m.lookup : [];
    if (rules.length) {
      lines.push('Lookup files of this skill (not required reading, searchable with grep/head/tail):');
      for (const r of rules.slice(0, 40)) lines.push(`  - ${r.glob}${r.why ? ' : ' + r.why : ''}`);
      if (rules.length > 40) lines.push(`  - ... and ${rules.length - 40} more lookup rules`);
    } else lines.push('Lookup files of this skill: only the standard ones (tests, scripts, data, templates, assets, changelog, version files).');
    if (m && m.external_lookup_roots.length) lines.push('External lookup roots: ' + m.external_lookup_roots.map((r) => expandRoot(r.replace('{skills}', this.index.roots.skillsDir))).filter(Boolean).join(', '));
    return lines.join('\n');
  }

  validNames(): string[] { return this.index.list().map((s) => s.folder); }

  run(query: string, partNo: number | undefined, sessionKey: string): { content: { type: 'text'; text: string }[]; details: Record<string, unknown>; isError?: boolean } {
    const folder = this.index.resolve(query || '');
    if (!folder) {
      const names = this.validNames();
      return {
        isError: true,
        content: [{ type: 'text', text: `read_skill: no skill named "${query}". Valid skills (${names.length}): ${names.join(', ')}` }],
        details: { error: 'unknown-skill', query },
      };
    }
    const bundle = this.build(folder);
    const total = bundle.parts.length;
    const part = partNo === undefined || partNo === null ? 1 : Math.floor(Number(partNo));
    if (!Number.isFinite(part) || part < 1 || part > total) {
      return {
        isError: true,
        content: [{ type: 'text', text: `read_skill ${folder}: part must be between 1 and ${total}.` }],
        details: { error: 'bad-part', skill: folder, parts: total },
      };
    }
    // Progress is tied to the exact content: if a file changed, start over.
    let prog = this.receipts.progress(sessionKey, folder);
    if (!prog || prog.sig !== bundle.signature || prog.total !== total) prog = { sig: bundle.signature, total, delivered: [] };
    if (!prog.delivered.includes(part)) prog.delivered.push(part);
    this.receipts.setProgress(sessionKey, folder, prog);
    const delivered = new Set(prog.delivered);
    const covers = (f: BundleFile): boolean => {
      for (let i = 0; i < total; i++) {
        const p = bundle.parts[i];
        if (p.end > f.start && p.start < f.end && !delivered.has(i + 1)) return false;
      }
      return true;
    };
    let newlyReceipted = 0;
    for (const f of bundle.files) if (covers(f)) { this.receipts.markFile(sessionKey, f.ref.abs, f.sha, false); newlyReceipted++; }
    this.receipts.flush(sessionKey);
    const complete = delivered.size === total;
    const slice = bundle.stream.slice(bundle.parts[part - 1].start, bundle.parts[part - 1].end);
    const inPart = bundle.files.filter((f) => bundle.parts[part - 1].end > f.start && bundle.parts[part - 1].start < f.end);

    const banner: string[] = [];
    banner.push(`read_skill ${folder}: part ${part} of ${total}. This is the WHOLE text, nothing is summarized or cut.`);
    banner.push(`Contents: the skill ${folder}${bundle.depSkills.length ? ', then its direct dependencies: ' + bundle.depSkills.join(', ') : ' (no direct dependencies listed)'}${bundle.files.some((f) => f.role === 'sop') ? ', then the SOP files it names' : ''}.`);
    if (part === 1) banner.push(this.lookupNote(folder));
    if (bundle.missingDeps.length) banner.push(`Warning: dependency entries with no matching skill or SOP on this box: ${bundle.missingDeps.join(', ')}`);
    banner.push('Files in this part: ' + inPart.map((f) => `${f.ref.skill}/${f.ref.rel}`).join(', '));
    const remaining = [];
    for (let i = 1; i <= total; i++) if (!delivered.has(i)) remaining.push(i);
    if (complete) banner.push(`READ COMPLETE: all ${total} part(s) delivered. Read receipt recorded for ${bundle.files.length} file(s) in this session. You may now run this skill's scripts.`);
    else banner.push(`${remaining.length} part(s) remain (${remaining.join(', ')}). Call read_skill with {"skill":"${folder}","part":${remaining[0]}} next. The receipt is only recorded when every part has been delivered.`);
    return {
      content: [{ type: 'text', text: banner.join('\n') }, { type: 'text', text: slice }],
      details: {
        skill: folder, part, parts: total, complete, receiptedFiles: newlyReceipted,
        files: bundle.files.map((f) => ({ path: `${f.ref.skill}/${f.ref.rel}`, bytes: f.bytes, sha256: f.sha, role: f.role })),
        dependencies: bundle.depSkills, missingDependencies: bundle.missingDeps, bodyChars: slice.length,
      },
    };
  }
}
