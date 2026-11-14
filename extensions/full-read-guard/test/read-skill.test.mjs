import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { makeBox } from './helpers.mjs';

function collect(g, skill, key) {
  const first = g.readSkill.run(skill, undefined, key);
  const bodies = [first.content[1].text];
  const outs = [first];
  for (let p = 2; p <= first.details.parts; p++) { const o = g.readSkill.run(skill, p, key); outs.push(o); bodies.push(o.content[1].text); }
  return { first, outs, bodies, files: first.details.files };
}
const expectedStream = (files, root) => files.map((f) => {
  const rel = f.path;
  const abs = rel.startsWith('universal-sops/') ? `${root}/${rel}` : `${root}/${rel}`;
  const text = fs.readFileSync(abs, 'utf8');
  return `===== FILE ${rel} (${f.bytes} bytes, sha256 ${f.sha256}) =====\n` + text + `\n===== END ${rel} =====\n`;
}).join('');

test('required upfront set: the skill root-level docs, each dependency SKILL.md only, and named SOPs; step folders, setup docs and lookup files are not delivered', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const { files } = collect(g, '10-alpha', 's-order');
    assert.deepEqual(files.map((f) => f.path), [
      '10-alpha/SKILL.md', '10-alpha/INSTRUCTIONS.md',
      '20-beta/SKILL.md',
      'universal-sops/sop/SOP-1.md', 'universal-sops/sop/SOP-2.md',
    ]);
    assert.deepEqual(files.map((f) => f.role), ['skill', 'skill', 'dependency', 'sop', 'sop']);
  } finally { box.cleanup(); }
});

test('one level only: a dependency of a dependency is not pulled in', () => {
  const box = makeBox([['more.json', { version: 1, skills: [{ skill: '30-gamma', depends_on: ['20-beta'] }] }]]);
  try {
    const g = box.guard();
    const { files } = collect(g, '30-gamma', 's-one');
    const paths = files.map((f) => f.path);
    assert.ok(paths.includes('20-beta/SKILL.md'));
    assert.ok(!paths.some((p) => p.startsWith('10-alpha/')), paths.join(', '));
    // cycle alpha <-> beta terminates and lists each file once
    const alpha = collect(g, '10-alpha', 's-cycle').files.map((f) => f.path);
    assert.equal(new Set(alpha).size, alpha.length);
  } finally { box.cleanup(); }
});

test('chunking: concatenated parts equal the source bytes exactly, small and oversized lines', () => {
  const box = makeBox();
  try {
    for (const [skill, chunk] of [['10-alpha', 500], ['10-alpha', 40000], ['50-wide', 2000], ['40-big', 7000]]) {
      const g = box.guard({ chunkChars: chunk, stateDir: null });
      const { bodies, files, first } = collect(g, skill, 's-chunk-' + skill + chunk);
      assert.equal(bodies.join(''), expectedStream(files, box.skills), `${skill} @ ${chunk}`);
      assert.equal(first.details.parts, bodies.length);
      if (skill !== '50-wide') for (const b of bodies) assert.ok(b.length <= chunk + 1, `part length ${b.length} > ${chunk}`);
    }
    const wide = box.guard({ chunkChars: 2000, stateDir: null }).readSkill.run('50-wide', 1, 'x');
    assert.ok(wide.details.parts >= 15);
  } finally { box.cleanup(); }
});

test('banner: part counts, next-part instruction, lookup list, READ COMPLETE only on the last part', () => {
  const box = makeBox();
  try {
    const g = box.guard({ chunkChars: 500 });
    const key = 's-banner';
    const first = g.readSkill.run('10-alpha', undefined, key);
    const b1 = first.content[0].text;
    assert.match(b1, /part 1 of \d+/);
    assert.match(b1, /"part":2/);
    assert.match(b1, /references\/api\.md/);
    assert.ok(!/READ COMPLETE/.test(b1));
    const total = first.details.parts;
    assert.ok(total >= 3);
    const last = g.readSkill.run('10-alpha', total, key);
    assert.ok(!/READ COMPLETE/.test(last.content[0].text)); // parts 2..total-1 still missing
    for (let p = 2; p < total; p++) g.readSkill.run('10-alpha', p, key);
    const done = g.readSkill.run('10-alpha', total, key);
    assert.match(done.content[0].text, /READ COMPLETE/);
    assert.equal(done.details.complete, true);
  } finally { box.cleanup(); }
});

test('receipt is complete only when every part was delivered; it names exact file hashes', () => {
  const box = makeBox();
  try {
    const g = box.guard({ chunkChars: 500 });
    const key = 's-receipt';
    const first = g.readSkill.run('10-alpha', 1, key);
    const lastFile = g.classifier.classify(box.p('universal-sops/sop/SOP-2.md')).abs;
    assert.equal(g.receipts.hasFile(key, lastFile), false);
    for (let p = 2; p <= first.details.parts; p++) g.readSkill.run('10-alpha', p, key);
    assert.equal(g.receipts.hasFile(key, lastFile), true);
    for (const f of first.details.files) {
      const sha = crypto.createHash('sha256').update(fs.readFileSync(`${box.skills}/${f.path}`)).digest('hex');
      assert.equal(f.sha256, sha);
    }
  } finally { box.cleanup(); }
});

test('a file that changes between parts restarts the read', () => {
  const box = makeBox();
  try {
    const g = box.guard({ chunkChars: 500 });
    const key = 's-change';
    const first = g.readSkill.run('10-alpha', 1, key);
    fs.appendFileSync(box.p('10-alpha/SKILL.md'), 'one more line\n');
    let out;
    for (let p = 2; p <= first.details.parts; p++) out = g.readSkill.run('10-alpha', p, key);
    assert.equal(out.details.complete, false);
  } finally { box.cleanup(); }
});

test('errors: unknown skill lists valid names; bad part is refused; aliases work', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const bad = g.readSkill.run('nope', undefined, 'k');
    assert.equal(bad.isError, true);
    assert.match(bad.content[0].text, /10-alpha/);
    assert.equal(g.readSkill.run('10-alpha', 999, 'k').isError, true);
    assert.equal(g.readSkill.run('10-alpha', 0, 'k').isError, true);
    for (const q of ['10', 'alpha', 'ALPHA']) assert.equal(g.readSkill.run(q, 1, 'k').details.skill, '10-alpha');
  } finally { box.cleanup(); }
});

test('missing dependencies are reported, not hidden', () => {
  const box = makeBox([['ghost.json', { version: 1, skills: [{ skill: '30-gamma', depends_on: ['99-ghost', 'universal-sops/none/*.md'] }] }]]);
  try {
    const g = box.guard();
    const out = g.readSkill.run('30-gamma', 1, 'k');
    assert.deepEqual(out.details.missingDependencies.sort(), ['99-ghost', 'universal-sops/none/*.md']);
    assert.match(out.content[0].text, /Warning/);
  } finally { box.cleanup(); }
});

test('the registered tool factory carries the session key and returns content', async () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const tool = g.readSkillTool({ sessionKey: 'tool-session' });
    assert.equal(tool.name, 'read_skill');
    assert.deepEqual(tool.parameters.required, ['skill']);
    const out = await tool.execute('call-1', { skill: '30-gamma' });
    assert.equal(out.content.length, 2);
    assert.ok(g.receipts.snapshot('tool-session').inUse['30-gamma']);
  } finally { box.cleanup(); }
});

test('read-on-open: the banner names the step material, and read_skill with "file" returns one file whole', () => {
  const box = makeBox();
  try {
    const g = box.guard();
    const first = g.readSkill.run('10-alpha', 1, 'oo');
    assert.match(first.content[0].text, /NOT required upfront/);
    assert.match(first.content[0].text, /references\/ \(1\)/);
    assert.match(first.content[0].text, /\(other\) \(1\)/); // INSTALL.md at the root
    const one = g.readSkill.run('10-alpha', 1, 'oo', 'references/procedure.md');
    assert.deepEqual(one.details.files.map((f) => f.path), ['10-alpha/references/procedure.md']);
    assert.equal(one.content[1].text, expectedStream(one.details.files, box.skills));
    const abs = g.classifier.classify(box.p('10-alpha/references/procedure.md')).abs;
    assert.equal(g.receipts.hasFile('oo', abs), true);
    for (const bad of ['../20-beta/SKILL.md', 'nope.md']) assert.equal(g.readSkill.run('10-alpha', 1, 'oo', bad).isError, true, bad);
  } finally { box.cleanup(); }
});
