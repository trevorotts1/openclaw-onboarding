import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import {
  BOOK_TO_PERSONA_FOLDER,
  inventoryLivePersonas,
  resolveBookToPersonaRoot,
} from '../src/sources/persona-root.js';

// Every path below lives under a fresh temp home. The real operator home is never read.
const temp = () => mkdtempSync(join(tmpdir(), 'persona-root-test-'));

const REGISTRY: Record<string, { author: string; book: string }> = {
  'sinek-start-with-why': { author: 'Simon Sinek', book: 'Start With Why' },
  'brown-atlas-of-heart': { author: 'Brené Brown', book: 'Atlas of the Heart' },
  'aliche-get-good-with-money': { author: 'Tiffany Aliche', book: 'Get Good with Money' },
  'jakes-instinct': { author: 'T. D. Jakes', book: 'Instinct' },
  'someone-else-a-book': { author: 'Someone Else', book: 'A Book' },
};

/** A Skill 22 store at `dir`. `withCategories:false` leaves the registry out. */
function makeStore(dir: string, withCategories = true): string {
  mkdirSync(join(dir, 'personas'), { recursive: true });
  const write = (key: string, files: Record<string, string>) => {
    mkdirSync(join(dir, 'personas', key), { recursive: true });
    for (const [name, body] of Object.entries(files)) writeFileSync(join(dir, 'personas', key, name), body);
  };
  write('sinek-start-with-why', { 'persona-blueprint.md': '# b\n', 'extraction-notes.md': '# e\n' });
  write('brown-atlas-of-heart', { 'persona-blueprint.md': '# b\n', 'extraction-notes.md': '# e\n' });
  write('aliche-get-good-with-money', { 'persona-blueprint.md': '# b\n' });
  write('jakes-instinct', { 'analysis-notes.md': '# a\n' }); // no blueprint: not usable
  if (withCategories) writeFileSync(join(dir, 'persona-categories.json'), JSON.stringify({ personas: REGISTRY }));
  return dir;
}

test('env BOOK_TO_PERSONA_ROOT wins over every other branch', () => {
  const home = temp();
  const direct = makeStore(join(home, 'direct'));
  makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER));
  const r = resolveBookToPersonaRoot({ homeDir: home, env: { BOOK_TO_PERSONA_ROOT: direct } });
  assert.equal(r?.resolved_from, 'env:BOOK_TO_PERSONA_ROOT');
  assert.equal(r?.skill_root, direct);
  assert.equal(r?.personas_dir, join(direct, 'personas'));
  assert.equal(r?.categories_path, join(direct, 'persona-categories.json'));
  rmSync(home, { recursive: true, force: true });
});

test('env OPENCLAW_SKILLS_DIR and OC_SKILLS_DIR are joined with the folder name', () => {
  const home = temp();
  makeStore(join(home, 'skills-a', BOOK_TO_PERSONA_FOLDER));
  for (const name of ['OPENCLAW_SKILLS_DIR', 'OC_SKILLS_DIR']) {
    const r = resolveBookToPersonaRoot({ homeDir: home, env: { [name]: join(home, 'skills-a') } });
    assert.equal(r?.resolved_from, 'env:OPENCLAW_SKILLS_DIR', name);
    assert.equal(r?.skill_root, join(home, 'skills-a', BOOK_TO_PERSONA_FOLDER));
  }
  rmSync(home, { recursive: true, force: true });
});

test('host layout extra skill dirs are searched, before the openclaw default', () => {
  const home = temp();
  const extra = join(home, 'extra-skills');
  makeStore(join(extra, BOOK_TO_PERSONA_FOLDER));
  makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER));
  mkdirSync(join(home, '.openclaw'), { recursive: true });
  writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify({ skills: { load: { extraDirs: [extra] } } }));
  const r = resolveBookToPersonaRoot({ homeDir: home, env: {} });
  assert.equal(r?.resolved_from, 'host_layout_skill_dir');
  assert.equal(r?.skill_root, join(extra, BOOK_TO_PERSONA_FOLDER));
  rmSync(home, { recursive: true, force: true });
});

test('falls back to <home>/.openclaw/skills/<folder>', () => {
  const home = temp();
  const dir = makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER));
  const r = resolveBookToPersonaRoot({ homeDir: home, env: {} });
  assert.equal(r?.resolved_from, 'openclaw_default');
  assert.equal(r?.skill_root, dir);
  rmSync(home, { recursive: true, force: true });
});

test('a candidate lacking categories or personas/ is skipped for the next branch', () => {
  const home = temp();
  const noCategories = makeStore(join(home, 'bad-a'), false);
  const noPersonas = join(home, 'bad-b');
  mkdirSync(noPersonas, { recursive: true });
  writeFileSync(join(noPersonas, 'persona-categories.json'), '{}');
  makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER));
  assert.equal(resolveBookToPersonaRoot({ homeDir: home, env: { BOOK_TO_PERSONA_ROOT: noCategories } })?.resolved_from, 'openclaw_default');
  assert.equal(resolveBookToPersonaRoot({ homeDir: home, env: { BOOK_TO_PERSONA_ROOT: noPersonas } })?.resolved_from, 'openclaw_default');
  rmSync(home, { recursive: true, force: true });
});

test('returns null and never throws when no store exists', () => {
  const home = temp();
  assert.equal(resolveBookToPersonaRoot({ homeDir: home, env: {} }), null);
  assert.equal(resolveBookToPersonaRoot({ homeDir: home, env: { BOOK_TO_PERSONA_ROOT: join(home, 'nope'), OPENCLAW_SKILLS_DIR: join(home, 'nope2') } }), null);
  const inv = inventoryLivePersonas({ homeDir: home, env: {} });
  assert.deepEqual(inv.root, { resolved_from: 'none', found: false });
  assert.equal(inv.seats.length, 9);
  assert.ok(inv.seats.every((s) => s.layer === 'shipped_brief_fallback' && s.personas.length === 0));
  rmSync(home, { recursive: true, force: true });
});

test('categories missing from the skill root fall back to the workspace copy', () => {
  const home = temp();
  const dir = makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER), false);
  assert.equal(resolveBookToPersonaRoot({ homeDir: home, env: {} }), null, 'no categories anywhere');
  const ws = join(home, '.openclaw', 'workspace', 'data', 'coaching-personas');
  mkdirSync(ws, { recursive: true });
  writeFileSync(join(ws, 'persona-categories.json'), JSON.stringify({ personas: REGISTRY }));
  const r = resolveBookToPersonaRoot({ homeDir: home, env: {} });
  assert.equal(r?.categories_path, join(ws, 'persona-categories.json'));
  assert.equal(r?.skill_root, dir);
  const inv = inventoryLivePersonas({ homeDir: home, env: {} });
  assert.equal(inv.root.found, true);
  assert.equal(inv.seats.find((s) => s.seat_id === 'simon-sinek')?.layer, 'live_book_to_persona');
  rmSync(home, { recursive: true, force: true });
});

test('inventory lists all 9 seats, maps brown-atlas-of-heart to brene-brown, and marks fallbacks', () => {
  const home = temp();
  makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER));
  const inv = inventoryLivePersonas({ homeDir: home, env: {} });
  assert.equal(inv.root.resolved_from, 'openclaw_default');
  assert.equal(inv.seats.length, 9);
  const seat = (id: string) => inv.seats.find((s) => s.seat_id === id)!;
  assert.deepEqual(seat('brene-brown').personas.map((p) => p.key), ['brown-atlas-of-heart']);
  assert.equal(seat('brene-brown').layer, 'live_book_to_persona');
  assert.deepEqual(seat('les-brown').personas, []);
  assert.equal(seat('les-brown').layer, 'shipped_brief_fallback');
  assert.equal(seat('oprah-winfrey').layer, 'shipped_brief_fallback');
  assert.equal(seat('tiffany-aliche').layer, 'live_book_to_persona'); // blueprint only still briefs
  // td-jakes is registered but has only analysis notes: not usable, so it falls back.
  assert.equal(seat('td-jakes').layer, 'shipped_brief_fallback');
  assert.equal(seat('td-jakes').personas[0]?.content_level, 'other_derived');
  assert.ok(!JSON.stringify(inv).includes(home), 'no absolute path in the inventory');
  rmSync(home, { recursive: true, force: true });
});

/** Every path under `dir` with size and mtime, so any create/modify/delete shows up. */
function snapshot(dir: string): string[] {
  const out: string[] = [];
  const walk = (d: string) => {
    for (const name of readdirSync(d).sort()) {
      const p = join(d, name);
      const st = statSync(p);
      out.push(`${p.slice(dir.length)}|${st.isDirectory() ? 'd' : st.size}|${st.mtimeMs}`);
      if (st.isDirectory()) walk(p);
    }
  };
  walk(dir);
  return out;
}

test('workspace categories fallback reads in place and writes nothing', () => {
  const home = temp();
  const scratch = temp(); // stands in for the system temp dir
  makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER), false);
  const ws = join(home, '.openclaw', 'workspace', 'data', 'coaching-personas');
  mkdirSync(ws, { recursive: true });
  writeFileSync(join(ws, 'persona-categories.json'), JSON.stringify({ personas: REGISTRY }));
  const script = new URL('../../scripts/inventory-live-personas.mjs', import.meta.url).pathname;
  const env = { PATH: process.env.PATH ?? '', HOME: home, USERPROFILE: home, TMPDIR: scratch, TEMP: scratch, TMP: scratch };
  const before = snapshot(home);
  for (const args of [[], ['--json']]) {
    const r = spawnSync(process.execPath, [script, ...args], { env, encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    assert.match(r.stdout, /brene-brown/);
    assert.ok(!r.stdout.includes(home) && !r.stdout.includes(scratch));
  }
  assert.deepEqual(snapshot(home), before, 'store and home are untouched');
  assert.deepEqual(readdirSync(scratch), [], 'no scratch files were created in the temp dir');
  rmSync(home, { recursive: true, force: true });
  rmSync(scratch, { recursive: true, force: true });
});

test('a resolved store that cannot be read is reported as unreadable, not as not found', () => {
  const home = temp();
  const dir = makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER));
  writeFileSync(join(dir, 'persona-categories.json'), '{ not json');
  const inv = inventoryLivePersonas({ homeDir: home, env: {} });
  assert.equal(inv.root.found, true);
  assert.equal(inv.root.unreadable, true);
  assert.equal(inv.root.error, 'SyntaxError');
  assert.equal(inv.root.resolved_from, 'openclaw_default');
  assert.equal(inv.seats.length, 9);
  assert.ok(inv.seats.every((s) => s.layer === 'shipped_brief_fallback'));
  assert.ok(!JSON.stringify(inv).includes(home));
  const script = new URL('../../scripts/inventory-live-personas.mjs', import.meta.url).pathname;
  const r = spawnSync(process.execPath, [script], { env: { PATH: process.env.PATH ?? '', HOME: home, USERPROFILE: home }, encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /UNREADABLE/);
  assert.doesNotMatch(r.stdout, /not found/);
  rmSync(home, { recursive: true, force: true });
});

test('script prints and --json both omit absolute paths and write nothing', () => {
  const home = temp();
  const scratch = temp();
  makeStore(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER));
  const script = new URL('../../scripts/inventory-live-personas.mjs', import.meta.url).pathname;
  const env = { PATH: process.env.PATH ?? '', HOME: home, USERPROFILE: home, TMPDIR: scratch, TEMP: scratch, TMP: scratch };
  const before = snapshot(home);
  for (const args of [[], ['--json']]) {
    const r = spawnSync(process.execPath, [script, ...args], { env, encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    assert.ok(!r.stdout.includes(home) && !r.stdout.includes(scratch) && !/\/(Users|home|tmp|var)\//.test(r.stdout), r.stdout);
    assert.match(r.stdout, /openclaw_default/);
    assert.match(r.stdout, /brene-brown/);
  }
  assert.deepEqual(snapshot(home), before);
  assert.deepEqual(readdirSync(scratch), []);
  rmSync(home, { recursive: true, force: true });
  rmSync(scratch, { recursive: true, force: true });
});
