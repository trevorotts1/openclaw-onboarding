// Rules the shipped manifest must always satisfy, checked against the real repository tree.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { REPO, REAL_MANIFEST_DIR } from './helpers.mjs';
import { createGuard, loadManifest, walkFiles, makeMatcher, globHitsInstructionNames, isInstructionByName } from '../dist/index.js';

const manifest = loadManifest(REAL_MANIFEST_DIR);
const guard = createGuard({ skillsDir: REPO, stateDir: null, manifestDir: REAL_MANIFEST_DIR, env: { HOME: '/nonexistent-home' } });
const skillDir = (name) => [path.join(REPO, name), path.join(REPO, 'skills', name)].find((d) => fs.existsSync(d));
// Skill 85's article set is installed from outside the repository, so its lookup globs match nothing here.
const NO_FILES_IN_REPO = new Set(['85-android-sms-system']);

test('the shipped manifest loads with no errors and covers the skills', () => {
  assert.deepEqual(manifest.errors, []);
  assert.ok(manifest.skills.size >= 75, String(manifest.skills.size));
  assert.ok(manifest.files.includes('_defaults.json'));
});

test('no lookup glob (default or per skill) can match an instruction file name', () => {
  for (const r of manifest.defaults) assert.deepEqual(globHitsInstructionNames(r.glob), [], r.glob);
  for (const e of manifest.skills.values()) for (const r of e.lookup) assert.deepEqual(globHitsInstructionNames(r.glob), [], `${e.skill}: ${r.glob}`);
});

test('every manifest skill exists in the repository', () => {
  for (const name of manifest.skills.keys()) assert.ok(skillDir(name), name);
});

test('every lookup glob matches at least one real file (except skills whose docs are installed from outside)', () => {
  for (const e of manifest.skills.values()) {
    if (NO_FILES_IN_REPO.has(e.skill)) continue;
    const files = walkFiles(skillDir(e.skill));
    for (const r of e.lookup) assert.ok(files.some((f) => makeMatcher([r.glob])(f)), `${e.skill}: ${r.glob} matches nothing`);
  }
});

test('every depends_on names an existing skill or SOP; 01 and 02 are never dependencies', () => {
  for (const e of manifest.skills.values()) {
    for (const d of e.depends_on) {
      if (d.startsWith('universal-sops/')) {
        const rel = d.slice('universal-sops/'.length);
        const hits = walkFiles(path.join(REPO, 'universal-sops')).filter((f) => makeMatcher([rel])(f));
        assert.ok(hits.length > 0, `${e.skill}: SOP entry ${d} matches nothing`);
      } else {
        assert.ok(guard.index.resolve(d), `${e.skill}: dependency ${d} does not resolve`);
        assert.ok(!/^0[12]-/.test(d), `${e.skill}: ${d}`);
      }
    }
  }
});

test('instruction file names are instruction in every real skill folder', () => {
  let checked = 0;
  for (const info of guard.index.list()) {
    for (const rel of fs.readdirSync(info.dir)) {
      if (!isInstructionByName(rel)) continue;
      const c = guard.classifier.classifyRel(info.folder, rel);
      assert.equal(c.cls, 'instruction', `${info.folder}/${rel}`);
      checked++;
    }
  }
  assert.ok(checked > 100, String(checked));
});

test('hand decisions from the exemption analysis hold', () => {
  const cls = (skill, rel) => guard.classifier.classifyRel(skill, rel).cls;
  assert.equal(cls('29-ghl-convert-and-flow', 'references/auth.md'), 'lookup'); // GHL API reference: named exempt
  assert.equal(cls('36-ghl-mcp-setup', 'GHL-LOOKUP-SOP.md'), 'instruction'); // name says LOOKUP, content is an SOP
  assert.equal(cls('67-kie-video', 'models.json'), 'lookup');
  assert.equal(cls('67-kie-video', 'references/models.md'), 'lookup');
  assert.equal(cls('67-kie-video', 'references/prompt-policy.md'), 'instruction');
  assert.equal(cls('85-android-sms-system', 'articles/MCS-001.md'), 'lookup');
  assert.equal(cls('85-android-sms-system', 'android-sms-system-full.md'), 'instruction');
  assert.equal(cls('23-ai-workforce-blueprint', 'templates/some/role.md'), 'lookup');
  assert.equal(cls('22-book-to-persona-coaching-leadership-system', 'personas/a.md'), 'lookup');
  assert.equal(cls('45-design-intelligence-library', 'library/INDEX.md'), 'instruction');
  assert.equal(cls('45-design-intelligence-library', 'library/x/design.md'), 'lookup');
  assert.equal(cls('38-conversational-ai-system', 'protocols/anything.md'), 'instruction'); // two classes only
  assert.equal(guard.classifier.classifyRel('38-conversational-ai-system', 'protocols/anything.md').upfront, false); // read-on-open
  assert.equal(cls('52-avatar-alchemist', 'prompts/step-01.md'), 'instruction');
});

test('skill 85 external roots are optional and include the three documented locations', () => {
  const e = manifest.skills.get('85-android-sms-system');
  assert.equal(e.external_roots.length, 3);
  assert.ok(e.external_roots.every((r) => r.optional === true));
  const paths = e.external_roots.map((r) => r.path);
  assert.ok(paths.includes('$ASMS_DOCS_DIR'));
  assert.ok(paths.some((p) => /85-android-sms-system\/docs$/.test(p)));
  assert.ok(paths.some((p) => /openclaw-master-files\/mycrmsim$/.test(p)));
});

test('closure is exactly one level deep and cycle safe', () => {
  const required = guard.closure.requiredFiles('44-convert-and-flow-operator');
  const owners = new Set(required.files.map((f) => f.skill));
  assert.ok(owners.has('44-convert-and-flow-operator'));
  assert.ok(owners.has('36-ghl-mcp-setup'));
  // 36 depends on 05, but 44 does not: 05 must not be pulled in transitively
  assert.ok(!owners.has('05-ghl-setup'), [...owners].join(', '));
  const cycles = guard.closure.findCycles();
  assert.ok(Array.isArray(cycles));
  for (const c of cycles) assert.equal(c[0], c[c.length - 1]);
  // a skill in a known two-way pair still terminates
  assert.ok(guard.closure.requiredFiles('38-conversational-ai-system').files.length > 0);
});

test('every real skill resolves its dependencies with none missing', () => {
  for (const info of guard.index.list()) {
    const d = guard.closure.dependencies(info.folder);
    assert.deepEqual(d.missing, [], `${info.folder}: ${d.missing.join(', ')}`);
  }
});

test('upfront set is root-level docs only: no step-folder file and no setup/archive doc is required upfront', () => {
  const cap = { 'SKILL.md': 1, 'INSTRUCTIONS.md': 1 };
  for (const info of guard.index.list()) {
    for (const f of guard.closure.instructionFiles(info.folder, true)) {
      assert.ok(!f.rel.includes('/'), `${info.folder}/${f.rel} is in a folder`);
      assert.ok(!/^(INSTALL|CORE_UPDATES|QC|README)\.md$/.test(f.rel) && !/-full\.md$/.test(f.rel), `${info.folder}/${f.rel}`);
    }
    assert.ok(guard.closure.instructionFiles(info.folder, true).some((f) => f.rel === 'SKILL.md'), info.folder);
  }
  assert.ok(cap);
});

test('upfront size of the formerly huge skills dropped well below the all-instruction total', () => {
  const size = (skill, upfrontOnly) => {
    const { files } = guard.closure.requiredFiles(skill);
    return files.reduce((a, f) => a + fs.statSync(f.abs).size, 0);
  };
  for (const s of ['44-convert-and-flow-operator', '38-conversational-ai-system', '83-black-friday-launcher', '35-social-media-planner', '23-ai-workforce-blueprint', '84-purple-billboard-blueprint']) {
    const all = [s, ...guard.closure.dependencies(s).skills].reduce((a, k) => a + guard.closure.instructionFiles(k).reduce((x, f) => x + fs.statSync(f.abs).size, 0), 0);
    assert.ok(size(s) < all * 0.6, `${s}: upfront ${size(s)} vs all ${all}`);
  }
});
