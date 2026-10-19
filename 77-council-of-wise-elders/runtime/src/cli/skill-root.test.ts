/**
 * The skill folder the runtime measures (defects 1 and 2).
 *
 * Runner (not part of `npm test`, whose glob is tests/**):
 *   npm run test:skill-root
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
 * - each shipped layout, as an esbuild bundle (onboarding's
 *   <prefix>/releases/<id>/dist/blackceo-council.mjs and 999-setup's
 *   <prefix>/runtime/dist/council-entry.mjs), with no SKILL.md anywhere
 *   above and an install record naming the skill folder, measures the
 *   RECORDED folder: the guard refuses a data dir inside it and accepts
 *   a path outside it;
 * - the same layouts with no record yield no root, never a guess.
 */

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
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
  const line = text
    .split(/\n| \| /)
    .find((l) => l.includes('data_dir_outside_skill_tree'));
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

// The two shipped layouts, each a single esbuild bundle (the toolchain's
// own `bundle` step) with no SKILL.md, advisors/ or manifest.json above it:
//   onboarding: <prefix>/releases/<id>/dist/blackceo-council.mjs, record at
//               <prefix>/releases/install-record.json (scripts/install-runtime.mjs)
//   999-setup:  <prefix>/runtime/dist/council-entry.mjs, record at
//               <prefix>/install-record.json (council-runtime-install.sh)
const LAYOUTS = {
  onboarding: { entry: 'releases/rel-0123456789ab/dist/blackceo-council.mjs', record: 'releases/install-record.json' },
  '999': { entry: 'runtime/dist/council-entry.mjs', record: 'install-record.json' },
} as const;

let bundleDir: string | null = null;
function probeBundle(): string {
  if (bundleDir) return join(bundleDir, 'probe.mjs');
  bundleDir = mkdtempSync(join(tmpdir(), 'council-bundle-'));
  const src = join(bundleDir, 'probe.ts');
  writeFileSync(
    src,
    [
      `import { runCli, skillRootForAssets } from ${JSON.stringify(join(here, 'dispatcher.js'))};`,
      'process.stdout.write("ROOT " + String(skillRootForAssets()) + "\\n");',
      'let out = "";',
      "await runCli(['doctor', '--data-dir', process.argv[2]],",
      '  { out: (t) => { out += t; }, err: (t) => { out += t; } },',
      '  { createHost: () => ({ host: { transportRegistry: { listRoutes: () => [] } } }) as never });',
      'process.stdout.write("OUT " + out.replace(/\\n/g, " | ") + "\\n");',
      'let sampleOut = "";',
      "const sampleRc = await runCli(['sample', 'run'],",
      '  { out: (t) => { sampleOut += t; }, err: (t) => { sampleOut += t; } }, {});',
      'process.stdout.write("SAMPLE " + sampleRc + " " + sampleOut.replace(/\\n/g, " | ") + "\\n");',
    ].join('\n'),
  );
  const r = spawnSync(
    join(runtimeRoot, 'node_modules', '.bin', 'esbuild'),
    [src, '--bundle', '--platform=node', '--format=esm', '--target=node20', `--outfile=${join(bundleDir, 'probe.mjs')}`],
    { encoding: 'utf8' },
  );
  assert.equal(r.status, 0, `esbuild failed: ${r.stdout}${r.stderr}`);
  return join(bundleDir, 'probe.mjs');
}

test.after(() => {
  if (bundleDir) rmSync(bundleDir, { recursive: true, force: true });
});

// Places the bundled probe in a shipped layout under a fresh prefix and
// runs it there in a child process.
function installedDoctor(
  layout: keyof typeof LAYOUTS,
  record: string | null,
  dataDir: string,
): { root: string; out: string; sample: string; raw: string } {
  const prefix = mkdtempSync(join(tmpdir(), 'council-prefix-'));
  try {
    const entry = join(prefix, LAYOUTS[layout].entry);
    mkdirSync(dirname(entry), { recursive: true });
    copyFileSync(probeBundle(), entry);
    // The build's copy-runtime-assets step puts the schema beside the entry.
    cpSync(join(runtimeRoot, 'src', 'persistence', 'migrations'), join(dirname(entry), 'migrations'), { recursive: true });
    if (record !== null) {
      writeFileSync(
        join(prefix, LAYOUTS[layout].record),
        JSON.stringify({ aggregate: 'fixture-skill-1', skill_dir: record }),
      );
    }
    assert.equal(existsSync(join(prefix, 'SKILL.md')), false);
    const r = spawnSync(process.execPath, [entry, dataDir], { cwd: prefix, encoding: 'utf8' });
    const text = `${r.stdout}${r.stderr}`;
    return {
      root: (/^ROOT (.*)$/m.exec(text)?.[1] ?? '').trim(),
      out: /OUT (.*)/.exec(text)?.[1] ?? text,
      sample: /SAMPLE (.*)/.exec(text)?.[1] ?? text,
      raw: text,
    };
  } finally {
    rmSync(prefix, { recursive: true, force: true });
  }
}

for (const layout of Object.keys(LAYOUTS) as (keyof typeof LAYOUTS)[]) {
  test(`${layout} layout: measures the recorded skill folder`, () => {
    const inside = installedDoctor(layout, SKILL_ROOT, join(SKILL_ROOT, 'state'));
    assert.equal(inside.root, SKILL_ROOT, `the record names the skill folder: ${inside.raw}`);
    assert.match(
      guardLine(inside.out),
      /\[not ready\] data_dir_outside_skill_tree.*inside the skill folder/,
      'the guard refuses a data dir inside the recorded folder',
    );

    // A path that really is outside the recorded skill folder.
    const ok = installedDoctor(layout, SKILL_ROOT, join(SKILL_ROOT, '..', 'outside-state'));
    assert.equal(ok.root, SKILL_ROOT);
    assert.match(guardLine(ok.out), /\[ok\] data_dir_outside_skill_tree/);
  });

  test(`${layout} layout without a record has no root and refuses`, () => {
    for (const dataDir of [join(SKILL_ROOT, 'state'), join(SKILL_ROOT, '..', 'outside-state')]) {
      const r = installedDoctor(layout, null, dataDir);
      assert.equal(r.root, 'null', 'no record, no guessed root');
      assert.match(
        guardLine(r.out),
        /\[not ready\] data_dir_outside_skill_tree.*skill folder could not be located/,
        `doctor refuses ${dataDir} when there is no boundary to measure`,
      );
      assert.match(r.sample, /^[1-9]\d* /, 'sample run exits non-zero without a root');
      assert.match(r.sample, /skill folder could not be located/);
    }
  });
}
