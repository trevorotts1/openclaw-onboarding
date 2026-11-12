// The read_skill tool: whole skill + one level of dependencies, in order, chunked, with a receipt.
import fs from 'node:fs';
import path from 'node:path';
import { expandRoot } from './manifest.js';
import { sha256 } from './paths.js';
export const DEFAULT_CHUNK_CHARS = 40000;
export function fileHeader(f) {
    return `===== FILE ${f.skill}/${f.rel} (${f.bytes} bytes, sha256 ${f.sha}) =====\n`;
}
export function fileFooter(f) {
    return `\n===== END ${f.skill}/${f.rel} =====\n`;
}
/** Split [0, len) into parts that end at a line break where possible. Concatenating the slices gives back the stream exactly. */
export function splitParts(stream, chunk) {
    const parts = [];
    let pos = 0;
    while (pos < stream.length) {
        let end = Math.min(stream.length, pos + chunk);
        if (end < stream.length) {
            const nl = stream.lastIndexOf('\n', end - 1);
            if (nl > pos)
                end = nl + 1;
        }
        parts.push({ start: pos, end });
        pos = end;
    }
    if (parts.length === 0)
        parts.push({ start: 0, end: 0 });
    return parts;
}
export class ReadSkillService {
    index;
    closure;
    manifest;
    receipts;
    chunkChars;
    constructor(index, closure, manifest, receipts, chunkChars = DEFAULT_CHUNK_CHARS) {
        this.index = index;
        this.closure = closure;
        this.manifest = manifest;
        this.receipts = receipts;
        this.chunkChars = chunkChars;
    }
    build(folder, only) {
        const { files: allRefs, deps } = this.closure.requiredFiles(folder);
        const refs = only || allRefs;
        const files = [];
        let stream = '';
        const seen = new Set();
        for (const ref of refs) {
            if (seen.has(ref.abs))
                continue;
            seen.add(ref.abs);
            let buf;
            try {
                buf = fs.readFileSync(ref.abs);
            }
            catch {
                continue;
            }
            const text = buf.toString('utf8');
            const sha = sha256(buf);
            const role = ref.skill === folder ? 'skill' : ref.skill === 'universal-sops' ? 'sop' : 'dependency';
            const head = fileHeader({ skill: ref.skill, rel: ref.rel, bytes: buf.length, sha });
            const start = stream.length;
            stream += head + text + fileFooter(ref);
            files.push({ ref, text, bytes: buf.length, sha, role, start, end: stream.length });
        }
        const parts = splitParts(stream, this.chunkChars);
        const signature = sha256(files.map((f) => f.ref.abs + ':' + f.sha).join('\n'));
        return { skill: folder, files, stream, parts, signature, missingDeps: only ? [] : deps.missing, depSkills: only ? [] : deps.skills };
    }
    lookupNote(folder) {
        const m = this.manifest.skills.get(folder);
        const lines = [];
        const rules = m ? m.lookup : [];
        if (rules.length) {
            lines.push('Lookup files of this skill (not required reading, searchable with grep/head/tail):');
            for (const r of rules.slice(0, 40))
                lines.push(`  - ${r.glob}${r.why ? ' : ' + r.why : ''}`);
            if (rules.length > 40)
                lines.push(`  - ... and ${rules.length - 40} more lookup rules`);
        }
        else
            lines.push('Lookup files of this skill: only the standard ones (tests, scripts, data, templates, assets, changelog, version files).');
        if (m && m.external_lookup_roots.length)
            lines.push('External lookup roots: ' + m.external_lookup_roots.map((r) => expandRoot(r.replace('{skills}', this.index.roots.skillsDir))).filter(Boolean).join(', '));
        return lines.join('\n');
    }
    validNames() { return this.index.list().map((s) => s.folder); }
    /** Step-folder instruction files (read whole when opened, not required upfront), grouped by folder. */
    readOnOpenNote(folder) {
        const all = this.closure.instructionFiles(folder);
        const groups = new Map();
        for (const f of all) {
            if (this.closure['classifier'].classifyRel(folder, f.rel).upfront)
                continue;
            const top = f.rel.includes('/') ? f.rel.split('/')[0] + '/' : '(other)';
            groups.set(top, (groups.get(top) || 0) + 1);
        }
        if (!groups.size)
            return '';
        return 'Step material (NOT required upfront; when you open any of these files you must read it whole, partial reads and grep are refused; open one with read, or read_skill with "file"): ' + [...groups].map(([k, v]) => `${k} (${v})`).join(', ');
    }
    run(query, partNo, sessionKey, fileArg) {
        const folder = this.index.resolve(query || '');
        if (!folder) {
            const names = this.validNames();
            return {
                isError: true,
                content: [{ type: 'text', text: `read_skill: no skill named "${query}". Valid skills (${names.length}): ${names.join(', ')}` }],
                details: { error: 'unknown-skill', query },
            };
        }
        let only;
        if (fileArg !== undefined && fileArg !== null && String(fileArg) !== '') {
            const rel = String(fileArg).replace(/^\.\//, '').replace(/^\/+/, '');
            const info = this.index.info(folder);
            const abs = info ? path.join(info.dir, rel) : '';
            const bad = !info || rel.split('/').includes('..') || !fs.existsSync(abs) || !fs.statSync(abs).isFile();
            if (bad)
                return { isError: true, content: [{ type: 'text', text: `read_skill ${folder}: no file "${fileArg}" inside this skill.` }], details: { error: 'bad-file', skill: folder, file: fileArg } };
            only = [{ skill: folder, rel, abs }];
        }
        const bundle = this.build(folder, only);
        const progKey = only ? `${folder}::${only[0].rel}` : folder;
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
        let prog = this.receipts.progress(sessionKey, progKey);
        if (!prog || prog.sig !== bundle.signature || prog.total !== total)
            prog = { sig: bundle.signature, total, delivered: [] };
        if (!prog.delivered.includes(part))
            prog.delivered.push(part);
        this.receipts.setProgress(sessionKey, progKey, prog);
        const delivered = new Set(prog.delivered);
        const covers = (f) => {
            for (let i = 0; i < total; i++) {
                const p = bundle.parts[i];
                if (p.end > f.start && p.start < f.end && !delivered.has(i + 1))
                    return false;
            }
            return true;
        };
        let newlyReceipted = 0;
        for (const f of bundle.files)
            if (covers(f)) {
                this.receipts.markFile(sessionKey, f.ref.abs, f.sha, false);
                newlyReceipted++;
            }
        this.receipts.flush(sessionKey);
        const complete = delivered.size === total;
        const slice = bundle.stream.slice(bundle.parts[part - 1].start, bundle.parts[part - 1].end);
        const inPart = bundle.files.filter((f) => bundle.parts[part - 1].end > f.start && bundle.parts[part - 1].start < f.end);
        const banner = [];
        banner.push(`read_skill ${folder}: part ${part} of ${total}. This is the WHOLE text, nothing is summarized or cut.`);
        if (only)
            banner.push(`Single file ${only[0].rel} of ${folder}, whole.`);
        else
            banner.push(`Contents: the skill ${folder}${bundle.depSkills.length ? ', then its direct dependencies: ' + bundle.depSkills.join(', ') : ' (no direct dependencies listed)'}${bundle.files.some((f) => f.role === 'sop') ? ', then the SOP files it names' : ''}. These are the required upfront documents (root-level docs and named SOPs).`);
        if (part === 1 && !only) {
            banner.push(this.lookupNote(folder));
            const ro = this.readOnOpenNote(folder);
            if (ro)
                banner.push(ro);
        }
        if (bundle.missingDeps.length)
            banner.push(`Warning: dependency entries with no matching skill or SOP on this box: ${bundle.missingDeps.join(', ')}`);
        banner.push('Files in this part: ' + inPart.map((f) => `${f.ref.skill}/${f.ref.rel}`).join(', '));
        const remaining = [];
        for (let i = 1; i <= total; i++)
            if (!delivered.has(i))
                remaining.push(i);
        if (complete)
            banner.push(`READ COMPLETE: all ${total} part(s) delivered. Read receipt recorded for ${bundle.files.length} file(s) in this session.${only ? '' : " You may now run this skill's scripts."}`);
        else
            banner.push(`${remaining.length} part(s) remain (${remaining.join(', ')}). Call read_skill with {"skill":"${folder}"${only ? ',"file":"' + only[0].rel + '"' : ''},"part":${remaining[0]}} next. The receipt is only recorded when every part has been delivered.`);
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
