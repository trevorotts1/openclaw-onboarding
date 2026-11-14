// Small glob matcher for manifest patterns. Patterns are relative to a skill folder.
// `*` and `?` stay inside one path segment; `**` crosses segments; `{a,b}` alternation.
// A pattern with no slash matches only at the skill root (use `**/name` for any depth).
// A trailing `/**` matches everything below that directory.
function expandBraces(p) {
    const m = /\{([^{}]*)\}/.exec(p);
    if (!m)
        return [p];
    const out = [];
    for (const alt of m[1].split(','))
        out.push(...expandBraces(p.slice(0, m.index) + alt + p.slice(m.index + m[0].length)));
    return out;
}
function one(p) {
    let re = '';
    for (let i = 0; i < p.length; i++) {
        const c = p[i];
        if (c === '*') {
            if (p[i + 1] === '*') {
                if (p[i + 2] === '/') {
                    re += '(?:.*/)?';
                    i += 2;
                }
                else {
                    re += '.*';
                    i += 1;
                }
            }
            else
                re += '[^/]*';
        }
        else if (c === '?')
            re += '[^/]';
        else if (c === '[') {
            const close = p.indexOf(']', i + 2);
            if (close === -1)
                re += '\\[';
            else {
                let cls = p.slice(i + 1, close);
                if (cls.startsWith('!'))
                    cls = '^' + cls.slice(1);
                re += '[' + cls + ']';
                i = close;
            }
        }
        else if ('\\^$+.()|]{}'.includes(c))
            re += '\\' + c;
        else
            re += c;
    }
    return '^' + re + '$';
}
export function globToRegExp(pattern) {
    const alts = expandBraces(pattern.replace(/^\.\//, '')).map(one);
    return new RegExp(alts.length === 1 ? alts[0] : '(?:' + alts.join('|') + ')');
}
export function makeMatcher(patterns) {
    const res = patterns.map(globToRegExp);
    return (rel) => res.some((r) => r.test(rel));
}
