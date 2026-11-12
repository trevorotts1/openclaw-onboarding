import test from 'node:test';
import assert from 'node:assert/strict';
import { makeBox } from './helpers.mjs';
import { parseCommand, tokenize } from '../dist/index.js';

let n = 0;
function run(g, command, extra = {}) {
  n += 1;
  return g.decide({ toolName: 'exec', params: { command, ...extra } }, { sessionKey: 'shell-' + n });
}

test('tokenizer: quotes, operators, substitutions, redirects', () => {
  const t = tokenize(`grep -n 'a b' "c d" file.md | head -3 && echo $(cat x) > out.txt`);
  const words = t.toks.filter((x) => x.t === 'word').map((x) => x.v);
  assert.deepEqual(words.slice(0, 5), ['grep', '-n', 'a b', 'c d', 'file.md']);
  assert.deepEqual(t.subs, ['cat x']);
  const segs = parseCommand('cd /a && grep foo x.md | head -2; ls');
  assert.equal(segs.length, 4);
  assert.equal(segs[0].cwd, '/a');
  assert.equal(segs[1].pipeline, segs[0].pipeline);
  assert.equal(segs[2].index, 1);
});

test('wrappers and env assignments are stripped before the verb is read', () => {
  const segs = parseCommand('FOO=1 sudo env BAR=2 nohup grep x file.md');
  assert.equal(segs[0].argv[0], 'grep');
});

test('partial reads of instruction files are blocked, lookup and whole reads are allowed', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const S = box.skills;
    const q = (rel) => `'${S}/${rel}'`;
    const blocked = [
      `grep -n foo ${q('10-alpha/SKILL.md')}`,
      `grep -rn foo ${q('10-alpha')}`,
      `grep -rn foo ${q('10-alpha/references')}`,
      `rg foo ${q('10-alpha/INSTRUCTIONS.md')}`,
      `head -20 ${q('10-alpha/SKILL.md')}`,
      `tail -n 5 ${q('10-alpha/SKILL.md')}`,
      `sed -n '1,10p' ${q('10-alpha/SKILL.md')}`,
      `awk 'NR<5' ${q('10-alpha/SKILL.md')}`,
      `less ${q('10-alpha/SKILL.md')}`,
      `cut -c1-20 ${q('10-alpha/SKILL.md')}`,
      `cat ${q('10-alpha/SKILL.md')} | head -3`,
      `cat ${q('10-alpha/SKILL.md')} | grep foo`,
      `cat ${q('10-alpha/SKILL.md')} | sed -n 1,3p`,
      `cat ${q('10-alpha/SKILL.md')} | tail -n 3`,
      `grep foo < ${q('10-alpha/SKILL.md')}`,
      `cd ${q('10-alpha')} && grep foo SKILL.md`,
      `cd ${q('10-alpha')} && head -5 INSTRUCTIONS.md`,
      `cd ${q('20-beta')}; grep -n beta SKILL.md`,
      `cd ${q('10-alpha')} && cat SKILL.md | grep foo`,
      `bash -c "grep foo ${S}/10-alpha/SKILL.md"`,
      `sh -lc 'head -5 ${S}/10-alpha/SKILL.md'`,
      `echo $(head -2 ${q('10-alpha/SKILL.md')})`,
      `grep foo ${q('10-alpha')}/*.md`,
      `grep -c foo ${q('universal-sops/sop/SOP-1.md')}`,
      `egrep 'a|b' ${q('10-alpha/references/procedure.md')}`,
      `xxd ${q('10-alpha/SKILL.md')} | head`,
      `strings ${q('10-alpha/SKILL.md')}`,
      `git grep foo -- ${q('10-alpha/SKILL.md')}`,
      `sudo grep foo ${q('10-alpha/SKILL.md')}`,
      `env FOO=1 grep foo ${q('10-alpha/SKILL.md')}`,
      `FOO=1 grep foo ${q('10-alpha/SKILL.md')}`,
      `python3 -c "print(open('${S}/10-alpha/SKILL.md').readlines()[:5])"`,
      `node -e "console.log(require('fs').readFileSync('${S}/10-alpha/SKILL.md','utf8').split('\\n').slice(0,5))"`,
      `find ${q('10-alpha')} -name '*.md' -exec grep -l foo {} \;`,
      `find ${q('10-alpha')} -name '*.md' | xargs grep foo`,
      `head -5 ${q('10-alpha/INSTRUCTIONS.md')} ${q('20-beta/SKILL.md')}`,
      `rg foo ${q('20-beta')}`,
      `sed -n 1,3p ${q('20-beta/notes.md')}`,
      `awk '{print}' ${q('10-alpha/references/procedure.md')}`,
      `grep -rn foo ${q('universal-sops/sop')}`,
      `zgrep foo ${q('10-alpha/SKILL.md')}`,
    ];
    for (const c of blocked) assert.equal(run(g, c).action, 'block', c);
    const allowed = [
      `cat ${q('10-alpha/SKILL.md')}`,
      `cat ${q('10-alpha/SKILL.md')} ${q('10-alpha/INSTRUCTIONS.md')}`,
      `wc -l ${q('10-alpha/SKILL.md')}`,
      `ls -la ${q('10-alpha')}`,
      `stat ${q('10-alpha/SKILL.md')}`,
      `sha256sum ${q('10-alpha/SKILL.md')}`,
      `file ${q('10-alpha/SKILL.md')}`,
      `grep -n endpoint ${q('10-alpha/references/api.md')}`,
      `head -5 ${q('10-alpha/references/api.md')}`,
      `sed -n 1,3p ${q('10-alpha/data/x.json')}`,
      `grep -rn foo ${q('10-alpha/scripts')}`,
      `grep -rn foo '${S}'`,
      `rg foo ${q('universal-sops')}`,
      `head -5 ${q('85-docs/articles/a1.md')}`,
      `rg foo ${q('85-docs/articles')}`,
      `grep foo /etc/hosts`,
      `head -5 notes.txt`,
      `echo hello`,
      `sed -i 's/a/b/' ${q('10-alpha/SKILL.md')}`,
      `cat ${q('10-alpha/SKILL.md')} > out.txt`,
      `cd ${q('10-alpha')} && ls`,
      `grep -n alpha ${q('10-alpha/notes/extra.md')}`,
      `git status`,
      `python3 -c "print(1+1)"`,
      `find ${q('10-alpha/scripts')} -name '*.sh' -exec grep -l echo {} \;`,
      `tail -n 5 ${q('10-alpha/scripts/run.sh')}`,
      `cat ${q('10-alpha/data/x.json')} | head -2`,
      `ls ${q('10-alpha/SKILL.md')} | head`,
      `grep foo ${q('10-alpha/references/api.md')} | head`,
    ];
    for (const c of allowed) assert.equal(run(g, c).action, 'allow', c);
    assert.ok(blocked.length + allowed.length >= 60);
  } finally { box.cleanup(); }
});

test('running a skill script before reading the skill is blocked (act-before-read)', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const S = box.skills;
    const cases = [
      [`bash '${S}/10-alpha/scripts/run.sh'`, {}],
      [`python3 '${S}/10-alpha/scripts/run.py'`, {}],
      [`'${S}/10-alpha/scripts/run.sh'`, {}],
      [`cd '${S}/10-alpha' && ./scripts/run.sh`, {}],
      [`cd '${S}/10-alpha' && python3 scripts/run.py`, {}],
      [`sh -c "bash ${S}/10-alpha/scripts/run.sh"`, {}],
      [`source '${S}/10-alpha/scripts/run.sh'`, {}],
      [`bash scripts/run.sh`, { workdir: `${S}/10-alpha` }],
      [`sudo bash '${S}/10-alpha/scripts/run.sh'`, {}],
      [`cd '${S}/10-alpha' && make`, {}],
      [`bash '${S}/30-gamma/scripts/go.sh'`, {}],
    ];
    for (const [c, extra] of cases) {
      const d = run(g, c, extra);
      assert.equal(d.action, 'block', c);
      assert.equal(d.code, 'act-before-read', c);
      assert.match(d.reason, /read_skill/, c);
    }
    const fine = [`python3 -c "print(2)"`, `bash /nonexistent/outside.sh`, `ls '${S}/10-alpha/scripts'`, `python3 /usr/lib/other.py`];
    for (const c of fine) assert.equal(run(g, c).action, 'allow', c);
  } finally { box.cleanup(); }
});

test('glob expansion finds instruction files behind a wildcard', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    assert.equal(run(g, `grep foo '${box.skills}'/10-alpha/INSTR*.md`).action, 'block');
    assert.equal(run(g, `grep foo '${box.skills}'/10-alpha/scripts/*.sh`).action, 'allow');
  } finally { box.cleanup(); }
});
