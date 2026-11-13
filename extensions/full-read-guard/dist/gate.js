// before_tool_call decisions, receipts hooks, loop breaker, and the guard factory used by index.ts and the tests.
import fs from 'node:fs';
import path from 'node:path';
import { Classifier, SkillIndex, SOPS_NAME } from './classify.js';
import { Closure, walkFiles } from './closure.js';
import { globToRegExp } from './glob.js';
import { loadManifest } from './manifest.js';
import { DEFAULT_CHUNK_CHARS, ReadSkillService } from './read-skill.js';
import { Receipts } from './receipts.js';
import { analyzeCommand } from './shell-parse.js';
import { fileSha, lineCount, resolveRoots, safeReal } from './paths.js';
const RANGE_KEYS = ['offset', 'limit', 'cursor', 'start_line', 'end_line', 'startLine', 'endLine', 'lines', 'line_range', 'range'];
function eventsLogAppend(dir, rec) {
    if (!dir)
        return;
    try {
        fs.mkdirSync(dir, { recursive: true });
        const f = path.join(dir, 'events.jsonl');
        try {
            if (fs.statSync(f).size > 2_000_000)
                fs.renameSync(f, f + '.1');
        }
        catch { /* new file */ }
        fs.appendFileSync(f, JSON.stringify(rec) + '\n');
    }
    catch { /* best effort */ }
}
export function createGuard(opts) {
    const env = opts.env || process.env;
    const mode = ['off', 'audit', 'enforce'].includes(env.OPENCLAW_FRG_MODE || opts.mode) ? (env.OPENCLAW_FRG_MODE || opts.mode) : 'enforce';
    const roots = resolveRoots({ skillsDir: opts.skillsDir, stateDir: opts.stateDir, pluginDir: opts.pluginDir, env });
    const now = opts.now || Date.now;
    const log = opts.log || (() => undefined);
    const manifest = loadManifest(opts.manifestDir);
    for (const e of manifest.errors)
        log('warn', `manifest: ${e}`);
    const index = new SkillIndex(roots, manifest);
    const classifier = new Classifier(index, manifest, env);
    const closure = new Closure(index, classifier, manifest);
    const receipts = new Receipts(roots.stateDir, now);
    const readSkill = new ReadSkillService(index, closure, manifest, receipts, opts.chunkChars || DEFAULT_CHUNK_CHARS);
    const loopRepeats = Math.max(2, opts.loopBreakerRepeats || 3);
    const maxBlocksPerRun = Math.max(3, opts.maxBlocksPerRun || 12);
    const readMaxBytes = opts.readMaxBytes || 51200;
    const readMaxLines = opts.readMaxLines || 2000;
    const chain = new Map();
    const runBlocks = new Map();
    const reqCache = new Map();
    const sessionKeyOf = (ctx) => (ctx && (ctx.sessionKey || ctx.sessionId)) || 'default';
    function required(skill) {
        const hit = reqCache.get(skill);
        if (hit && now() - hit.at < 10000)
            return hit;
        const { files, deps } = closure.requiredFiles(skill);
        const v = { at: now(), files, deps: deps.skills };
        reqCache.set(skill, v);
        return v;
    }
    function cwdList(params, ctx) {
        const out = [];
        if (params && typeof params.workdir === 'string' && params.workdir)
            out.push(params.workdir);
        if (ctx && typeof ctx.workspaceDir === 'string' && ctx.workspaceDir)
            out.push(ctx.workspaceDir);
        return out;
    }
    function dirInstruction(abs) {
        const real = safeReal(abs);
        const rel = path.relative(index.skillsReal, real);
        if (rel === '' || rel.startsWith('..') || path.isAbsolute(rel))
            return null; // ancestor or outside: discovery, allowed
        const parts = rel.split(path.sep);
        const top = parts[0];
        if (top === SOPS_NAME && parts.length === 1)
            return null;
        if (top !== SOPS_NAME && !index.info(top))
            return null;
        const files = walkFiles(real, 5000);
        if (files.length >= 5000)
            return { skill: top };
        for (const f of files) {
            const c = classifier.classifyAbs(path.join(real, f));
            if (c.scope === 'skill' && c.cls === 'instruction')
                return { skill: top };
        }
        return null;
    }
    function expandGlob(pattern, cwds) {
        const bases = path.isAbsolute(pattern) ? [path.parse(pattern).root] : cwds.length ? cwds : [process.cwd()];
        const segs = pattern.split('/').filter((s, i) => !(i === 0 && s === ''));
        const out = [];
        for (const base of bases) {
            let level = [base];
            for (const seg of segs) {
                const next = [];
                for (const dir of level) {
                    if (!/[*?\[]/.test(seg)) {
                        const p = path.join(dir, seg);
                        if (fs.existsSync(p))
                            next.push(p);
                        continue;
                    }
                    const re = globToRegExp(seg);
                    let names = [];
                    try {
                        names = fs.readdirSync(dir);
                    }
                    catch {
                        continue;
                    }
                    for (const n of names)
                        if (!n.startsWith('.') && re.test(n))
                            next.push(path.join(dir, n));
                    if (next.length > 2000)
                        break;
                }
                level = next;
            }
            out.push(...level);
        }
        return out.slice(0, 2000);
    }
    function shellEnv(workdir, ctx) {
        return {
            workdir,
            classify: (p, cwds) => {
                const c = classifier.classify(p, cwds.length ? cwds : workdir ? [workdir] : []);
                return c.scope === 'skill' ? { scope: 'skill', skill: c.skill, cls: c.cls, rel: c.rel, abs: c.abs } : { scope: c.scope };
            },
            isDir: (abs) => { try {
                return fs.statSync(abs).isDirectory();
            }
            catch {
                return false;
            } },
            exists: (abs) => fs.existsSync(abs),
            dirInstruction,
            expandGlob,
        };
    }
    function wholeFileAdvice(skill) {
        if (skill === SOPS_NAME)
            return 'Read the whole file with the read tool (no offset, no limit), or call read_skill on the skill that names this SOP.';
        return `Call read_skill with {"skill":"${skill}"} to get the whole skill and the skills it depends on (step files: read the file whole when you open it), or read the whole file with the read tool (no offset, no limit).`;
    }
    function partialReason(b) {
        const what = b.code === 'recursive-search' ? `Searching inside ${b.file} would show only parts of its instruction files` : `"${b.file}" is an instruction file and "${b.verb}" shows only part of it`;
        return `Full-Read Guard: ${what}. Instruction files must be read in full. ${wholeFileAdvice(b.skill)} Lookup files the skill lists (data, references, scripts, templates) may be searched.`;
    }
    function decide(event, ctx) {
        const tool = String(event.toolName || '');
        const params = event.params && typeof event.params === 'object' ? event.params : {};
        const key = sessionKeyOf(ctx);
        if (tool === 'read') {
            const p = params.path ?? params.file_path;
            if (typeof p !== 'string' || !p)
                return { action: 'allow' };
            const c = classifier.classify(p, cwdList(params, ctx));
            if (c.scope !== 'skill' || c.cls !== 'instruction')
                return { action: 'allow' };
            if (c.skill !== SOPS_NAME)
                receipts.markInUse(key, c.skill);
            const hasRange = RANGE_KEYS.some((k) => params[k] !== undefined && params[k] !== null);
            let size = 0;
            let lines = 0;
            try {
                const buf = fs.readFileSync(c.abs);
                size = buf.length;
                lines = lineCount(buf.toString('utf8'));
            }
            catch {
                return { action: 'allow' };
            }
            if (size > readMaxBytes || lines > readMaxLines) {
                return { action: 'block', code: 'read-too-large', signature: `read|large|${c.abs}|${hasRange}`,
                    reason: `Full-Read Guard: "${c.skill}/${c.rel}" is too large for one read call (${size} bytes, ${lines} lines), and a partial read of an instruction file is not allowed. ${c.skill === SOPS_NAME ? 'Read it through read_skill on the skill that names this SOP.' : `Call read_skill with {"skill":"${c.skill}","file":"${c.rel}"}`} to get it whole, in complete parts.` };
            }
            if (hasRange) {
                const np = { ...params };
                for (const k of RANGE_KEYS)
                    delete np[k];
                return { action: 'rewrite', params: np, note: `ranged read of ${c.skill}/${c.rel} rewritten to a whole-file read` };
            }
            return { action: 'allow' };
        }
        if (tool === 'exec' || tool === 'bash') {
            const cmd = typeof params.command === 'string' ? params.command : typeof params.cmd === 'string' ? params.cmd : '';
            if (!cmd)
                return { action: 'allow' };
            const workdir = typeof params.workdir === 'string' && params.workdir ? params.workdir : ctx && ctx.workspaceDir ? ctx.workspaceDir : null;
            const a = analyzeCommand(cmd, shellEnv(workdir, ctx));
            for (const s of a.touched)
                if (s !== SOPS_NAME)
                    receipts.markInUse(key, s);
            if (a.blocks.length) {
                const b = a.blocks[0];
                const more = a.blocks.length > 1 ? ` (${a.blocks.length} instruction files affected)` : '';
                return { action: 'block', code: b.code, signature: `${tool}|${b.code}|${b.file}|${cmd}`, reason: partialReason(b) + more };
            }
            const seen = new Set();
            for (const skill of a.runs) {
                if (seen.has(skill))
                    continue;
                seen.add(skill);
                receipts.markInUse(key, skill);
                const req = required(skill);
                const missing = receipts.missing(key, req.files);
                if (missing.length) {
                    const depNote = req.deps.length ? ` It also gives you its direct dependencies (${req.deps.join(', ')}).` : '';
                    return { action: 'block', code: 'act-before-read', signature: `${tool}|act|${skill}|${cmd}`,
                        reason: `Full-Read Guard: before running anything from skill "${skill}", read it in full. Call read_skill with {"skill":"${skill}"}.${depNote} ${missing.length} required file(s) have not been read in this session yet.` };
                }
            }
        }
        return { action: 'allow' };
    }
    function beforeToolCall(event, ctx) {
        if (mode === 'off')
            return undefined;
        try {
            if (!event || event.toolName === 'read_skill')
                return undefined;
            const d = decide(event, ctx);
            if (d.action === 'allow')
                return undefined;
            if (d.action === 'rewrite') {
                if (mode === 'audit') {
                    eventsLogAppend(roots.stateDir, { at: now(), kind: 'audit-rewrite', tool: event.toolName, note: d.note });
                    log('info', `audit: would rewrite: ${d.note}`);
                    return undefined;
                }
                eventsLogAppend(roots.stateDir, { at: now(), kind: 'rewrite', tool: event.toolName, note: d.note });
                return { params: d.params };
            }
            if (mode === 'audit') {
                eventsLogAppend(roots.stateDir, { at: now(), kind: 'audit-block', tool: event.toolName, code: d.code });
                log('info', `audit: would block (${d.code})`);
                return undefined;
            }
            // Loop breaker: the Nth identical block in a row is allowed through and logged.
            const key = sessionKeyOf(ctx);
            const prev = chain.get(key);
            const fresh = !prev || prev.sig !== d.signature || now() - prev.at > 10 * 60 * 1000;
            const count = fresh ? 1 : prev.count + 1;
            chain.set(key, { sig: d.signature, count, at: now() });
            const runId = (ctx && ctx.runId) || event.runId || key;
            const rb = (runBlocks.get(runId) || 0) + 1;
            runBlocks.set(runId, rb);
            if (runBlocks.size > 200)
                runBlocks.delete(runBlocks.keys().next().value);
            if (count >= loopRepeats) {
                chain.delete(key);
                eventsLogAppend(roots.stateDir, { at: now(), kind: 'loop-breaker', tool: event.toolName, code: d.code, repeats: count });
                log('warn', `loop-breaker: allowed ${event.toolName} after ${count} identical blocks (${d.code})`);
                return undefined;
            }
            if (rb > maxBlocksPerRun) {
                eventsLogAppend(roots.stateDir, { at: now(), kind: 'loop-breaker-run', tool: event.toolName, code: d.code, blocksInRun: rb });
                log('warn', `loop-breaker: run ${runId} passed ${maxBlocksPerRun} blocks; allowing ${event.toolName}`);
                return undefined;
            }
            eventsLogAppend(roots.stateDir, { at: now(), kind: 'block', tool: event.toolName, code: d.code });
            return { block: true, blockReason: d.reason };
        }
        catch (e) {
            log('warn', `fail-open after internal error: ${String(e)}`);
            eventsLogAppend(roots.stateDir, { at: now(), kind: 'fail-open', error: String(e) });
            return undefined;
        }
    }
    function afterToolCall(event, ctx) {
        try {
            if (!event || event.toolName !== 'read' || event.error)
                return;
            const params = event.params || {};
            if (RANGE_KEYS.some((k) => params[k] !== undefined && params[k] !== null))
                return;
            const p = params.path ?? params.file_path;
            if (typeof p !== 'string')
                return;
            const r = event.result;
            const blob = typeof r === 'string' ? r : JSON.stringify(r ?? '');
            if ((r && r.details && r.details.kind === 'truncated') || /Read output capped|more lines? in file|\[Truncated:|Showing lines/.test(blob))
                return;
            const c = classifier.classify(p, cwdList(params, ctx));
            if (c.scope !== 'skill' || c.cls !== 'instruction')
                return;
            const sha = fileSha(c.abs);
            if (sha)
                receipts.markFile(sessionKeyOf(ctx), c.abs, sha);
        }
        catch (e) {
            log('warn', `after_tool_call error ignored: ${String(e)}`);
        }
    }
    function resetSession(ctx) {
        try {
            if (ctx && ctx.sessionKey)
                receipts.reset(ctx.sessionKey);
            if (ctx && ctx.sessionId)
                receipts.reset(ctx.sessionId);
            if (!ctx || (!ctx.sessionKey && !ctx.sessionId))
                receipts.reset('default');
            const k = sessionKeyOf(ctx);
            chain.delete(k);
        }
        catch (e) {
            log('warn', `reset error ignored: ${String(e)}`);
        }
    }
    function readSkillTool(toolContext) {
        return {
            name: 'read_skill',
            label: 'read_skill',
            description: 'Read a whole skill (its SKILL.md and root-level instruction documents) and the same for everything it directly depends on, in full and in order, so no step is skipped. Use it before you use a skill. Long sets come in numbered parts: keep calling with the next part until it says READ COMPLETE. Step files (prompts, protocols, playbooks, ...) are read whole when you open them; read_skill with "file" returns one such file whole.',
            parameters: {
                type: 'object',
                additionalProperties: false,
                properties: {
                    skill: { type: 'string', description: 'Skill name or number, for example "67-kie-video", "67", or "kie-video".' },
                    file: { type: 'string', description: 'Optional: one file inside the skill, relative path (for example a step file under prompts/). Returns that file whole.' },
                    part: { type: 'integer', minimum: 1, description: 'Part number to fetch when the skill is delivered in several parts. Default 1.' },
                },
                required: ['skill'],
            },
            async execute(_toolCallId, params) {
                const key = sessionKeyOf(toolContext);
                try {
                    const out = readSkill.run(String(params && params.skill || ''), params && params.part, key, params && params.file);
                    if (!out.isError && out.details && out.details.skill)
                        receipts.markInUse(key, String(out.details.skill));
                    return out;
                }
                catch (e) {
                    return { isError: true, content: [{ type: 'text', text: `read_skill failed: ${String(e)}` }], details: { error: 'internal' } };
                }
            },
        };
    }
    return { mode, roots, manifest, index, classifier, closure, receipts, readSkill, decide, beforeToolCall, afterToolCall, resetSession, readSkillTool, required };
}
