// Shell command analysis for exec/bash tool calls. Not a full shell: a careful tokenizer plus
// the rules the guard needs. It narrows partial reads of instruction files; it cannot make
// skipping impossible (an unrecognised interpreter trick can still get through).
import path from 'node:path';
const SHELLS = new Set(['bash', 'sh', 'zsh', 'dash', 'ksh', 'ash']);
const INTERPRETERS = new Set(['bash', 'sh', 'zsh', 'dash', 'ksh', 'ash', 'python', 'python2', 'python3', 'node', 'nodejs', 'deno', 'bun', 'ruby', 'perl', 'php', 'lua', 'Rscript', 'tsx', 'ts-node', 'pwsh', 'source', '.']);
const WRAPPERS = new Set(['sudo', 'env', 'nohup', 'time', 'command', 'exec', 'builtin', 'nice', 'ionice', 'stdbuf', 'timeout', 'caffeinate', 'setsid']);
export const PARTIAL_VERBS = new Set(['grep', 'egrep', 'fgrep', 'zgrep', 'rg', 'ag', 'ack', 'head', 'tail', 'sed', 'awk', 'gawk', 'mawk', 'nawk', 'less', 'more', 'most', 'cut', 'od', 'xxd', 'hexdump', 'strings', 'csplit', 'split', 'bat', 'batcat']);
const RECURSIVE_DEFAULT = new Set(['rg', 'ag', 'ack']);
const FULL_READERS = new Set(['cat', 'tac', 'nl', 'zcat', 'pr']);
const INLINE_PARTIAL = /readline|readlines|splitlines|\[\s*\d*\s*:\s*\d*\s*\]|islice|\.find\(|\bre\.|grep|head|tail|slice\(|\.split\(|indexOf|match\(|\.filter\(|\.lines\b|\bsed\b|\bawk\b|\bgetline\b|\bnext\(|\bchomp/;
export function tokenize(cmd) {
    const toks = [];
    const subs = [];
    let i = 0;
    const n = cmd.length;
    let cur = '';
    let has = false;
    const flush = () => { if (has)
        toks.push({ t: 'word', v: cur }); cur = ''; has = false; };
    const grabParen = (start) => {
        // start points just after "$("
        let depth = 1;
        let j = start;
        let q = '';
        while (j < n && depth > 0) {
            const c = cmd[j];
            if (q) {
                if (c === q)
                    q = '';
                else if (c === '\\' && q === '"')
                    j++;
            }
            else if (c === '"' || c === "'")
                q = c;
            else if (c === '\\')
                j++;
            else if (c === '(')
                depth++;
            else if (c === ')') {
                depth--;
                if (depth === 0)
                    break;
            }
            j++;
        }
        return [cmd.slice(start, j), j + 1];
    };
    while (i < n) {
        const c = cmd[i];
        if (c === '\\') {
            if (cmd[i + 1] === '\n') {
                i += 2;
                continue;
            }
            cur += cmd[i + 1] ?? '';
            has = true;
            i += 2;
            continue;
        }
        if (c === "'") {
            const e = cmd.indexOf("'", i + 1);
            const end = e === -1 ? n : e;
            cur += cmd.slice(i + 1, end);
            has = true;
            i = end + 1;
            continue;
        }
        if (c === '"') {
            i++;
            has = true;
            while (i < n && cmd[i] !== '"') {
                if (cmd[i] === '\\' && i + 1 < n) {
                    const nx = cmd[i + 1];
                    if ('"\\$`'.includes(nx)) {
                        cur += nx;
                        i += 2;
                        continue;
                    }
                    if (nx === '\n') {
                        i += 2;
                        continue;
                    }
                    cur += '\\';
                    i++;
                    continue;
                }
                if (cmd[i] === '$' && cmd[i + 1] === '(') {
                    const [inner, nxt] = grabParen(i + 2);
                    subs.push(inner);
                    cur += '\u0000SUB';
                    i = nxt;
                    continue;
                }
                if (cmd[i] === '`') {
                    const e = cmd.indexOf('`', i + 1);
                    const end = e === -1 ? n : e;
                    subs.push(cmd.slice(i + 1, end));
                    cur += '\u0000SUB';
                    i = end + 1;
                    continue;
                }
                cur += cmd[i];
                i++;
            }
            i++;
            continue;
        }
        if (c === '$' && cmd[i + 1] === '(') {
            const [inner, nxt] = grabParen(i + 2);
            subs.push(inner);
            cur += '\u0000SUB';
            has = true;
            i = nxt;
            continue;
        }
        if (c === '`') {
            const e = cmd.indexOf('`', i + 1);
            const end = e === -1 ? n : e;
            subs.push(cmd.slice(i + 1, end));
            cur += '\u0000SUB';
            has = true;
            i = end + 1;
            continue;
        }
        if (c === '#' && !has) {
            while (i < n && cmd[i] !== '\n')
                i++;
            continue;
        }
        if (c === ' ' || c === '\t') {
            flush();
            i++;
            continue;
        }
        if (c === '\n') {
            flush();
            toks.push({ t: 'op', v: ';' });
            i++;
            continue;
        }
        if (c === ';' || c === '(' || c === ')') {
            flush();
            toks.push({ t: 'op', v: ';' });
            i++;
            continue;
        }
        if (c === '&' || c === '|') {
            const two = cmd.slice(i, i + 2);
            if (c === '&' && cmd[i + 1] === '>') {
                flush();
                toks.push({ t: 'redir', v: '>' });
                i += cmd[i + 2] === '>' ? 3 : 2;
                continue;
            }
            flush();
            if (two === '&&' || two === '||') {
                toks.push({ t: 'op', v: two });
                i += 2;
            }
            else if (two === '|&') {
                toks.push({ t: 'op', v: '|' });
                i += 2;
            }
            else {
                toks.push({ t: 'op', v: c === '|' ? '|' : ';' });
                i++;
            }
            continue;
        }
        if (c === '<' || c === '>') {
            if (has && /^\d+$/.test(cur)) {
                cur = '';
                has = false;
            }
            else
                flush();
            let op = c;
            if (cmd[i + 1] === c) {
                op += c;
                if (cmd[i + 2] === '<')
                    op += '<';
            }
            else if (cmd[i + 1] === '&')
                op += '&';
            i += op.length;
            toks.push({ t: 'redir', v: op });
            continue;
        }
        cur += c;
        has = true;
        i++;
    }
    flush();
    return { toks, subs };
}
export function parseCommand(cmd, startCwd = null, depth = 0) {
    const { toks, subs } = tokenize(cmd);
    const segs = [];
    let pipeline = 0;
    let idx = 0;
    let cwd = startCwd;
    let words = [];
    let redirIn = [];
    let pendingRedir = null;
    const end = (isPipe) => {
        if (words.length || redirIn.length) {
            let argv = words.slice();
            while (argv.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(argv[0]))
                argv.shift();
            for (let guard = 0; guard < 4 && argv.length && WRAPPERS.has(path.basename(argv[0])); guard++) {
                const w = path.basename(argv[0]);
                argv.shift();
                while (argv.length && (argv[0].startsWith('-') || /^[A-Za-z_][A-Za-z0-9_]*=/.test(argv[0])))
                    argv.shift();
                if (w === 'timeout' && argv.length)
                    argv.shift();
            }
            if (argv.length && (argv[0] === 'cd' || argv[0] === 'pushd') && argv[1]) {
                const target = argv[1];
                cwd = path.isAbsolute(target) ? target : cwd === null ? target : path.isAbsolute(cwd) ? path.resolve(cwd, target) : path.join(cwd, target);
            }
            else if (argv.length || redirIn.length) {
                segs.push({ argv, redirIn, pipeline, index: idx, cwd, raw: words.slice() });
            }
        }
        words = [];
        redirIn = [];
        if (isPipe)
            idx++;
        else {
            pipeline++;
            idx = 0;
        }
    };
    for (const tk of toks) {
        if (tk.t === 'op') {
            pendingRedir = null;
            end(tk.v === '|');
            continue;
        }
        if (tk.t === 'redir') {
            pendingRedir = tk.v;
            continue;
        }
        if (pendingRedir !== null) {
            if (pendingRedir === '<')
                redirIn.push(tk.v);
            pendingRedir = null;
            continue;
        }
        words.push(tk.v);
    }
    end(false);
    if (depth < 4)
        for (const s of subs)
            segs.push(...parseCommand(s, cwd, depth + 1).map((x) => ({ ...x, pipeline: x.pipeline + 1000 * (depth + 1) + segs.length })));
    return segs;
}
function isFlag(w) { return w.length > 1 && w.startsWith('-'); }
const GLOB_CHARS = /[*?\[]/;
function candidateWords(argv, redirIn) {
    const out = [];
    let afterDD = false;
    for (const w of argv.slice(1)) {
        if (!afterDD && w === '--') {
            afterDD = true;
            continue;
        }
        if (!afterDD && isFlag(w))
            continue;
        if (w.includes('\u0000SUB'))
            continue;
        out.push(w);
    }
    return [...out, ...redirIn];
}
export function analyzeCommand(cmd, env, depth = 0) {
    const res = { blocks: [], runs: [], touched: [] };
    if (typeof cmd !== 'string' || cmd.trim() === '')
        return res;
    const segs = parseCommand(cmd, null);
    const byPipe = new Map();
    for (const s of segs) {
        const l = byPipe.get(s.pipeline) || [];
        l.push(s);
        byPipe.set(s.pipeline, l);
    }
    const cwdsFor = (s) => {
        const list = [];
        if (s.cwd)
            list.push(path.isAbsolute(s.cwd) ? s.cwd : path.resolve(env.workdir || '.', s.cwd));
        if (env.workdir)
            list.push(env.workdir);
        return list;
    };
    const fileTargets = (s, words) => {
        const cwds = cwdsFor(s);
        const out = [];
        for (const w of words) {
            const variants = GLOB_CHARS.test(w) ? env.expandGlob(w, cwds) : [w];
            for (const v of variants) {
                const c = env.classify(v, cwds);
                if (c.scope === 'skill' && c.skill && c.abs && env.isDir(c.abs)) {
                    const d = env.dirInstruction(c.abs);
                    if (d)
                        out.push({ abs: c.abs, cls: 'instruction', skill: d.skill, file: c.rel ? `${c.skill}/${c.rel}` : v, dir: true });
                }
                else if (c.scope === 'skill' && c.skill)
                    out.push({ abs: c.abs, cls: c.cls || 'instruction', skill: c.skill, file: c.rel ? `${c.skill}/${c.rel}` : v });
                else if (c.scope === 'outside') {
                    // directories: skill root and sub-folders are not "files" for classify(); check them.
                    for (const base of cwds.length ? cwds.map((d) => path.resolve(d, v)) : [path.resolve(v)]) {
                        if (path.isAbsolute(v) && base !== v)
                            continue;
                        if (env.isDir(base)) {
                            const d = env.dirInstruction(base);
                            if (d) {
                                out.push({ abs: base, cls: 'instruction', skill: d.skill, file: v, dir: true });
                                break;
                            }
                        }
                    }
                    if (path.isAbsolute(v) && env.isDir(v)) {
                        const d = env.dirInstruction(v);
                        if (d && !out.some((o) => o.abs === v))
                            out.push({ abs: v, cls: 'instruction', skill: d.skill, file: v, dir: true });
                    }
                }
            }
        }
        return out;
    };
    for (const pipe of byPipe.values()) {
        pipe.sort((a, b) => a.index - b.index);
        let upstreamInstruction = null; // content of an instruction file flows on stdin
        let upstreamNames = null; // file names (find, ls) flow on stdin
        for (const s of pipe) {
            if (!s.argv.length)
                continue;
            const verb = path.basename(s.argv[0]);
            const args = s.argv.slice(1);
            // shell -c "...": analyse the inner command
            if (SHELLS.has(verb) || verb === 'eval') {
                let inner = null;
                if (verb === 'eval')
                    inner = args.join(' ');
                else {
                    const ci = args.findIndex((a) => /^-[A-Za-z]*c[A-Za-z]*$/.test(a));
                    if (ci !== -1 && args[ci + 1] !== undefined)
                        inner = args[ci + 1];
                }
                if (inner !== null && depth < 4) {
                    const sub = analyzeCommand(inner, { ...env, workdir: s.cwd || env.workdir }, depth + 1);
                    res.blocks.push(...sub.blocks);
                    res.runs.push(...sub.runs);
                    res.touched.push(...sub.touched);
                    continue;
                }
            }
            const targets = fileTargets(s, candidateWords(s.argv, s.redirIn));
            const instrTargets = targets.filter((t) => t.cls === 'instruction');
            // ---- act-before-read: running a skill's script / working inside a skill folder
            const cwdFolder = (() => {
                for (const d of cwdsFor(s)) {
                    const k = env.classify(path.join(d, '__cwd_probe__'), []);
                    if (k.scope === 'skill' && k.skill)
                        return k.skill;
                }
                return null;
            })();
            let runTarget = null;
            if (verb === 'source' || verb === '.') {
                runTarget = args.find((a) => !isFlag(a)) ?? null;
            }
            else if (INTERPRETERS.has(verb)) {
                const inline = args.some((a) => /^-[A-Za-z]*[cepm]$/.test(a));
                if (!inline)
                    runTarget = args.find((a) => !isFlag(a)) ?? null;
            }
            else if (s.argv[0].includes('/') || s.argv[0].startsWith('.'))
                runTarget = s.argv[0];
            if (runTarget && !runTarget.includes('\u0000SUB')) {
                const c = env.classify(runTarget, cwdsFor(s));
                if (c.scope === 'skill' && c.skill && c.skill !== 'universal-sops')
                    res.runs.push(c.skill);
            }
            else if (['make', 'npm', 'pnpm', 'yarn', 'npx'].includes(verb) && cwdFolder && cwdFolder !== 'universal-sops')
                res.runs.push(cwdFolder);
            // ---- inline interpreter code that slices an instruction file
            if (INTERPRETERS.has(verb) && args.some((a) => /^-[A-Za-z]*[cep]$/.test(a))) {
                for (const a of args) {
                    if (isFlag(a))
                        continue;
                    const lits = a.match(/['"]([^'"\n]+\.(?:md|markdown|mdx))['"]/g) || [];
                    for (const lit of lits) {
                        const p = lit.slice(1, -1);
                        const c = env.classify(p, cwdsFor(s));
                        if (c.scope === 'skill' && c.cls === 'instruction' && INLINE_PARTIAL.test(a))
                            res.blocks.push({ code: 'partial-read', skill: c.skill, file: `${c.skill}/${c.rel}`, verb });
                    }
                }
            }
            // ---- partial read verbs
            let verbForRule = verb;
            let verbArgs = args;
            if (verb === 'git' && args[0] === 'grep') {
                verbForRule = 'grep';
                verbArgs = args.slice(1);
            }
            if (verb === 'sed' && args.some((a) => /^-[A-Za-z]*i/.test(a) || a === '--in-place'))
                verbForRule = '';
            if (verb === 'bat' || verb === 'batcat') {
                if (!args.some((a) => a === '-r' || a.startsWith('--line-range') || a === '-l'))
                    verbForRule = '';
            }
            if (PARTIAL_VERBS.has(verbForRule)) {
                const recursive = RECURSIVE_DEFAULT.has(verbForRule) || verbArgs.some((a) => /^-[A-Za-z]*[rR][A-Za-z]*$/.test(a) || a === '--recursive' || a === '-d' || a === '--directories=recurse');
                for (const t of instrTargets) {
                    if (t.dir && !recursive)
                        continue;
                    res.blocks.push({ code: t.dir ? 'recursive-search' : 'partial-read', skill: t.skill, file: t.file, verb: verbForRule });
                }
                // reading stdin from an upstream cat of an instruction file
                if (s.index > 0 && instrTargets.length === 0 && upstreamInstruction && !targets.some((t) => t.abs && env.exists(t.abs))) {
                    res.blocks.push({ code: 'partial-read', skill: upstreamInstruction.skill, file: upstreamInstruction.file, verb: verbForRule });
                }
            }
            // ---- find -exec <partial>, xargs <partial>
            if (verb === 'find') {
                const ei = args.findIndex((a) => a === '-exec' || a === '-execdir' || a === '-ok');
                if (ei !== -1 && PARTIAL_VERBS.has(path.basename(args[ei + 1] || ''))) {
                    for (const t of targets)
                        if (t.cls === 'instruction')
                            res.blocks.push({ code: 'recursive-search', skill: t.skill, file: t.file, verb: 'find -exec ' + path.basename(args[ei + 1]) });
                }
            }
            if (verb === 'xargs') {
                const vi = args.findIndex((a) => !isFlag(a));
                const up = upstreamInstruction || upstreamNames;
                if (vi !== -1 && PARTIAL_VERBS.has(path.basename(args[vi])) && up) {
                    res.blocks.push({ code: 'partial-read', skill: up.skill, file: up.file, verb: 'xargs ' + path.basename(args[vi]) });
                }
            }
            // ---- bookkeeping for later pipeline stages
            {
                const first = instrTargets[0];
                if (first) {
                    if (FULL_READERS.has(verb))
                        upstreamInstruction = { skill: first.skill, file: first.file };
                    else if (verb === 'find' || verb === 'ls' || (PARTIAL_VERBS.has(verb) && /^-[A-Za-z]*l/.test(args[0] || '')))
                        upstreamNames = { skill: first.skill, file: first.file };
                }
            }
            for (const t of instrTargets)
                if (!res.touched.includes(t.skill))
                    res.touched.push(t.skill);
        }
    }
    return res;
}
