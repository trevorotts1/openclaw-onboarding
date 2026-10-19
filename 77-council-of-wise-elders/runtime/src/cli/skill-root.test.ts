/**
 * The skill folder the runtime measures (defects 1 and 2).
 *
 * Runner:
 *   node --import tsx --test src/cli/skill-root.test.ts
 *
 * Defect 1: the installed prefix carries neither advisors/ nor a
 * SKILL.md, so the module climb named the prefix and every advisor load
 * failed. Defect 2: the data-dir guard measured that same wrong root,
 * so a data dir inside the real skill folder was accepted.
 *
 * Proven here:
 * - a source layout resolves to THIS skill folder (advisors/ and
 *   manifest.json beside SKILL.md);
 * - doctor refuses a data dir inside it and accepts one outside it;
 * - an installed prefix (copied dispatcher, no SKILL.md anywhere above,
 *   an install record naming the skill folder) measures the RECORDED
 *   folder: the guard refuses a data dir inside it and accepts the same
 *   path once it is outside;
 * - an installed prefix with no record yields no root, never a guess.
 */

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { runCli, skillRootForAssets } from './dispatcher.js';

const here = dirname(fileURLToPath(import.meta.url));
const runtimeRoot = resolve(here, '..', '..');
const SKILL_ROOT = resolve(runtimeRoot, '..');

function capture() {
  let out = '';
  let err = '';
  return {
    io: { out: (t: string) => void (out += t), err: (t: string) => void (err += t) },
    text: () => out,
    all: () => out + err,
  };
}

function guardLine(text: string): string {
  const line = text.split('\n').find((l) => l.includes('data_dir_outside_skill_tree'));
  assert.ok(line, `doctor did not report the guard: ${text}`);
  return line;
}

test('source layout resolves to this skill folder', () => {
  assert.equal(skillRootForAssets(), SKILL_ROOT);
});

test('doctor refuses a data dir inside the actual skill folder', async () => {
  const c = capture();
  const rc = await runCli(['doctor', '--data-dir', join(SKILL_ROOT, 'state')], c.io, {
    createHost: () => assert.fail('host must not be built for a refused data dir'),
  });
  assert.notEqual(rc, 1, 'doctor reports findings, never COUNCIL_INTERNAL');
  const line = guardLine(c.all());
  assert.match(line, /\[not ready\]/);
  assert.match(line, /inside the skill folder/);
});

test('doctor accepts a data dir outside the skill folder', async () => {
  const c = capture();
  let built = 0;
  await runCli(['doctor', '--data-dir', join(SKILL_ROOT, '..', 'outside-state')], c.io, {
    createHost: (opts) => {
      built += 1;
      assert.match(String(opts.dataDir), /outside-state$/);
      return {
        host: { transportRegistry: { listRoutes: () => [] } },
      } as unknown as ReturnType<typeof import('./local-host.js').createLocalHost>;
    },
  }).catch(() => undefined);
  assert.equal(built, 1, 'an outside data dir reaches host construction');
  assert.match(guardLine(c.all()), /\[ok\]/);
});

// Copies the dispatcher (with the subtree its top-level imports need)
// into <prefix>/runtime/dist/cli, the installed bundle layout, and runs
// `doctor` there in a child process.
function installedPrefixDoctor(
  record: string | null,
  dataDir: string,
): { root: string; out: string; raw: string } {
  const fixture = mkdtempSync(join(tmpdir(), 'council-prefix-'));
  try {
    const dist = join(fixture, 'runtime', 'dist');
    // The shipped layout: the CLI is ONE file at runtime/dist/, with no
    // SKILL.md, advisors/ or manifest.json anywhere above it.
    // The installed build: the dispatcher at dist/cli (its siblings one
    // level up at dist/contracts, dist/persistence, ...) and no SKILL.md,
    // advisors/ or manifest.json anywhere above it.
    cpSync(join(runtimeRoot, 'src'), dist, { recursive: true });
    const cliDir = join(dist, 'cli');
    rmSync(join(cliDir, 'skill-root.test.ts'), { force: true });
    assert.equal(existsSync(join(cliDir, 'dispatcher.ts')), true, 'fixture entry is in cli/');
    cpSync(join(runtimeRoot, 'package.json'), join(fixture, 'runtime', 'package.json'));
    // The child runs under a temp folder where no node_modules lies
    // above it: give it the runtime's own dev dependencies.
    symlinkSync(join(runtimeRoot, 'node_modules'), join(fixture, 'runtime', 'node_modules'));
    if (record !== null) {
      writeFileSync(
        join(fixture, 'runtime', 'install-record.json'),
        JSON.stringify({ aggregate: 'fixture-skill-1', skill_dir: record }),
      );
    }
    writeFileSync(
      join(cliDir, 'probe.ts'),
      [
        "import { runCli, skillRootForAssets } from './dispatcher.js';",
        'process.stdout.write("ROOT " + String(skillRootForAssets()) + "\\n");',
        'let out = "";',
        `await runCli(['doctor', '--data-dir', ${JSON.stringify(dataDir)}],`,
        '  { out: (t) => { out += t; }, err: (t) => { out += t; } },',
        "  { createHost: () => { throw new Error('host-built'); } });",
        'process.stdout.write("OUT " + out.replace(/\\n/g, " | ") + "\\n");',
      ].join('\n'),
    );
    assert.equal(existsSync(join(cliDir, 'SKILL.md')), false);
    assert.equal(existsSync(join(fixture, 'SKILL.md')), false);
    const r = spawnSync(process.execPath, ['--import', 'tsx', 'probe.ts'], {
      cwd: cliDir,
      encoding: 'utf8',
    });
    const text = `${r.stdout}${r.stderr}`;
    return {
      root: (/^ROOT (.*)$/m.exec(text)?.[1] ?? '').trim(),
      out: /OUT (.*)/.exec(text)?.[1] ?? text,
      raw: text,
    };
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
}

test('installed prefix: measures the recorded skill folder', () => {
  const inside = installedPrefixDoctor(SKILL_ROOT, join(SKILL_ROOT, 'state'));
  assert.equal(inside.root, SKILL_ROOT, `the record names the skill folder: ${inside.raw}`);
  assert.match(
    guardLine(inside.out),
    /inside the skill folder/,
    'the guard refuses a data dir inside the recorded folder',
  );

  // Outside the recorded folder as a sibling path, never inside the
  // skill folder itself.
  const ok = installedPrefixDoctor(SKILL_ROOT, join(runtimeRoot, 'outside-state'));
  assert.equal(ok.root, SKILL_ROOT);
  assert.match(guardLine(ok.out), /\[ok\]/);
});

test('installed prefix without a record has no root', () => {
  const r = installedPrefixDoctor(null, join(SKILL_ROOT, 'state'));
  assert.equal(r.root, 'null', 'no record, no guessed root');
});
