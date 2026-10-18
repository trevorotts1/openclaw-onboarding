/**
 * WER-005 bridge tests: installed-runtime resolution, wrapper diagnostic
 * parity with the canonical CLI, and URL preservation on browser-open
 * failure.
 *
 * Runner (runtime's own node:test + tsx):
 *   node --import tsx --test src/bridges/installed-cli.test.ts
 *
 * Deterministic fixtures only. No real install, no npm, no browser, no
 * process launched. The receipt fixtures are written in WER-004's exact
 * staged-release shapes.
 *
 * DEFERRED (never claimed here): a fresh harness launched from an unrelated
 * directory, a real Mac profile resolution against a real install, and
 * native Windows execution.
 */

import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { runCli, type CliIo } from '../cli/dispatcher.js';
import { createLocalHost } from '../cli/local-host.js';
import {
  composeClaudeNineLocalHost,
  renderClaudeNineWrapper,
} from './claude-nine.js';
import { openCouncilUrl } from './browser-open.js';
import {
  ACTIVE_RECEIPT_SCHEMA,
  ARTIFACT_RECEIPT_SCHEMA,
  INSTALLED_CLI_RELATIVE,
  RELEASE_RECEIPT_SCHEMA,
  RUNTIME_PREFIX_ENV,
  defaultRuntimePrefix,
  resolveInstalledCli,
} from './installed-cli.js';

const runtimeDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const skillRoot = resolve(runtimeDir, '..');

function laneTemp(label: string): string {
  return mkdtempSync(join(tmpdir(), `operator-W02-U002-${label}-`));
}

function sha256File(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

interface FakeInstall {
  prefix: string;
  releaseId: string;
  releasePath: string;
  cliPath: string;
  activeReceiptPath: string;
  releaseReceiptPath: string;
  artifactReceiptPath: string;
}

/**
 * Write exactly the receipt layout install-runtime.mjs produces.
 * The digests are self-consistent fixtures, not a real build.
 */
function writeFakeInstall(): FakeInstall {
  const prefix = laneTemp('prefix');
  const releaseId = 'rel-0123456789ab';
  const releasePath = join(prefix, 'releases', releaseId);
  const cliPath = join(releasePath, INSTALLED_CLI_RELATIVE);
  mkdirSync(dirname(cliPath), { recursive: true });
  writeFileSync(cliPath, '#!/usr/bin/env node\nconsole.log("fixture-cli");\n', {
    mode: 0o755,
  });

  const receiptsDir = join(prefix, 'receipts');
  mkdirSync(receiptsDir, { recursive: true });
  const cliSha256 = sha256File(cliPath);
  const sourceManifestDigest = 'a'.repeat(64);
  const artifactDigest = 'b'.repeat(64);
  const dataDir = join(prefix, 'data');
  const activeReceiptPath = join(prefix, 'active.json');
  const releaseReceiptPath = join(receiptsDir, `${releaseId}.release.json`);
  const artifactReceiptPath = join(receiptsDir, `${releaseId}.artifact.json`);

  const active = {
    schema: ACTIVE_RECEIPT_SCHEMA,
    releaseId,
    releasePath,
    receiptPath: releaseReceiptPath,
    sourceManifestDigest,
    artifactDigest,
    nodeExecutable: process.execPath,
    nodeVersion: process.version,
    platform: process.platform,
    arch: process.arch,
    dataDir,
    activatedAt: '2026-01-01T00:00:00.000Z',
    previousReleaseId: null,
  };

  writeFileSync(
    artifactReceiptPath,
    JSON.stringify({
      schema: ARTIFACT_RECEIPT_SCHEMA,
      releaseId,
      sourceManifestDigest,
      package: { name: '@blackceo/wise-elders-core', version: '0.1.0' },
      builtAt: '2026-01-01T00:00:00.000Z',
      node: { executable: process.execPath, version: process.version },
      platform: process.platform,
      arch: process.arch,
      entries: [
        { path: 'dist/blackceo-council.mjs', sha256: cliSha256, size: 1 },
        { path: 'dist/index.js', sha256: 'c'.repeat(64), size: 1 },
      ],
      digest: artifactDigest,
      fileCount: 2,
    }),
  );
  writeFileSync(
    releaseReceiptPath,
    JSON.stringify({
      schema: RELEASE_RECEIPT_SCHEMA,
      releaseId,
      sourceManifestDigest,
      artifactDigest,
      dataDir,
      active,
    }),
  );
  writeFileSync(activeReceiptPath, JSON.stringify(active));

  return {
    prefix,
    releaseId,
    releasePath,
    cliPath,
    activeReceiptPath,
    releaseReceiptPath,
    artifactReceiptPath,
  };
}

function captureIo(): { io: CliIo; out: () => string; err: () => string } {
  let outText = '';
  let errText = '';
  return {
    io: {
      out: (text) => {
        outText += text;
      },
      err: (text) => {
        errText += text;
      },
    },
    out: () => outText,
    err: () => errText,
  };
}

// ---------------------------------------------------------------------------
// Installed receipt resolution
// ---------------------------------------------------------------------------

test('installed-cli: resolves the activated receipt CLI independently of process.cwd() and a checkout dist folder', () => {
  const install = writeFakeInstall();
  const cwdA = laneTemp('cwd-a');
  const cwdB = laneTemp('cwd-b');
  // Decoys that a cwd-relative resolver would wrongly pick up.
  mkdirSync(join(cwdA, 'dist'), { recursive: true });
  writeFileSync(join(cwdA, 'dist', 'blackceo-council.mjs'), 'decoy');

  const originalCwd = process.cwd();
  try {
    process.chdir(cwdA);
    const first = resolveInstalledCli({ prefix: install.prefix, skillRoot });
    process.chdir(cwdB);
    const second = resolveInstalledCli({ prefix: install.prefix, skillRoot });

    assert.equal(first.ok, true);
    assert.equal(second.ok, true);
    assert.equal(first.ok && first.cliPath, install.cliPath);
    assert.equal(second.ok && second.cliPath, install.cliPath);
    assert.equal(first.ok && first.releaseId, install.releaseId);
    assert.equal(first.ok && first.releaseReceiptPath, install.releaseReceiptPath);
    assert.equal(first.ok && first.artifactReceiptPath, install.artifactReceiptPath);
    assert.ok(first.ok && first.cliPath.startsWith(install.releasePath));
    assert.ok(first.ok && !first.cliPath.startsWith(resolve(cwdA)));
    assert.equal(first.ok && first.cliSha256, sha256File(install.cliPath));
  } finally {
    process.chdir(originalCwd);
  }
});

test('installed-cli: a missing receipt fails with the exact installer recovery command and the paths checked', () => {
  const prefix = join(laneTemp('missing'), 'council-runtime');
  const result = resolveInstalledCli({ prefix, skillRoot });
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.code, 'RUNTIME_NOT_INSTALLED');
  assert.equal(result.checked[0], join(prefix, 'active.json'));
  assert.ok(result.message.includes(join(prefix, 'active.json')));
  assert.ok(result.recovery.includes('install-runtime.mjs'));
  assert.ok(result.recovery.includes(`--prefix ${JSON.stringify(prefix)}`));
  assert.ok(result.recovery.includes(RUNTIME_PREFIX_ENV));
});

test('installed-cli: a corrupt active receipt fails closed instead of guessing a release', () => {
  const prefix = laneTemp('corrupt');
  writeFileSync(
    join(prefix, 'active.json'),
    JSON.stringify({ schema: 'something-else/v1', releaseId: 'rel-aaaaaaaaaaaa' }),
  );
  const result = resolveInstalledCli({ prefix, skillRoot });
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.code, 'RUNTIME_RECEIPT_INVALID');
  assert.ok(result.message.includes(ACTIVE_RECEIPT_SCHEMA));
  assert.ok(result.recovery.includes('install-runtime.mjs'));
});

test('installed-cli: a CLI that no longer matches the receipt hash is refused', () => {
  const install = writeFakeInstall();
  writeFileSync(install.cliPath, '#!/usr/bin/env node\nconsole.log("tampered");\n');
  const result = resolveInstalledCli({ prefix: install.prefix, skillRoot });
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.code, 'RUNTIME_ARTIFACT_INVALID');
  assert.ok(result.message.includes(install.cliPath));
  assert.ok(result.checked.includes(install.cliPath));
  assert.ok(result.recovery.includes(`--prefix ${JSON.stringify(install.prefix)}`));
});

test('installed-cli: a relative prefix is refused rather than resolved against cwd', () => {
  const result = resolveInstalledCli({
    env: { [RUNTIME_PREFIX_ENV]: 'relative/council-runtime' },
    homeDir: laneTemp('home'),
  });
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.code, 'RUNTIME_PREFIX_INVALID');
  assert.deepEqual(result.checked, ['relative/council-runtime']);
  assert.ok(result.message.includes('working directory'));
});

test('installed-cli: the default prefix matches the installer default', () => {
  const home = laneTemp('default-home');
  assert.equal(
    defaultRuntimePrefix({}, home),
    join(home, '.local', 'share', 'blackceo', 'council-runtime'),
  );
});

// ---------------------------------------------------------------------------
// Diagnostics survive the bridge wrapper
// ---------------------------------------------------------------------------

interface FixtureHome {
  home: string;
  env: NodeJS.ProcessEnv;
}

function writeFixtureHome(): FixtureHome {
  const home = laneTemp('home-fixture');
  mkdirSync(join(home, '.claude-nine'), { recursive: true });
  const binDir = join(home, '.local', 'bin');
  mkdirSync(binDir, { recursive: true });
  const launcher = join(binDir, 'claude-nine');
  writeFileSync(launcher, '#!/bin/sh\nexit 0\n');
  chmodSync(launcher, 0o755);

  mkdirSync(join(home, '.openclaw'), { recursive: true });
  writeFileSync(
    join(home, '.openclaw', 'openclaw.json'),
    JSON.stringify({
      models: {
        providers: {
          fixture: {
            baseUrl: 'https://fixture.invalid/v1',
            api: 'openai-completions',
            apiKey: '${FIXTURE_COUNCIL_KEY}',
            models: [{ id: 'fixture-model' }],
          },
        },
      },
      agents: { defaults: { model: { primary: 'fixture/fixture-model' } } },
    }),
  );

  return {
    home,
    env: { ...process.env, HOME: home, FIXTURE_COUNCIL_KEY: 'present' },
  };
}

test('wrapper: routeDiscovery and the route catalog survive the Claude-Nine host view', () => {
  const fixture = writeFixtureHome();
  const canonicalDir = laneTemp('canonical-data');
  const wrapperDir = laneTemp('wrapper-data');

  const canonical = createLocalHost({
    dataDir: canonicalDir,
    skillRoot,
    homeDir: fixture.home,
    env: fixture.env,
  });
  const wrapped = composeClaudeNineLocalHost({
    dataDir: wrapperDir,
    skillRoot,
    homeDir: fixture.home,
    env: fixture.env,
  });

  assert.deepEqual(wrapped.routeDiscovery, canonical.routeDiscovery);
  assert.deepEqual(
    wrapped.host.transportRegistry.listRoutes(),
    canonical.host.transportRegistry.listRoutes(),
  );
  assert.ok(
    wrapped.routeDiscovery.some(
      (route) => route.route_id === 'claude-nine-configured' && route.composed,
    ),
    'harness route diagnostic must reach the wrapper',
  );
  assert.ok(
    wrapped.routeDiscovery.some((route) => route.route_id === 'fixture-configured'),
    'compatible route diagnostic must reach the wrapper',
  );
  assert.equal(wrapped.catalog.length, 0);
  assert.equal(wrapped.bridge.routeDiscovery, wrapped.routeDiscovery);
});

test('wrapper: models diagnostics from the wrapper equal the canonical CLI for the same input', async () => {
  const fixture = writeFixtureHome();
  const originalHome = process.env.HOME;
  const originalKey = process.env.FIXTURE_COUNCIL_KEY;
  process.env.HOME = fixture.home;
  process.env.FIXTURE_COUNCIL_KEY = 'present';
  try {
    const canonicalRun = captureIo();
    const canonicalCode = await runCli(
      ['models', '--json', '--data-dir', laneTemp('cli-canonical-data')],
      canonicalRun.io,
    );
    assert.equal(canonicalCode, 0, canonicalRun.err());

    const wrapperRun = captureIo();
    const wrapperCode = await runCli(
      ['models', '--json', '--data-dir', laneTemp('cli-wrapper-data')],
      wrapperRun.io,
      {
        createHost: (opts) =>
          composeClaudeNineLocalHost({
            ...opts,
            homeDir: fixture.home,
            env: process.env,
          }),
      },
    );
    assert.equal(wrapperCode, 0, wrapperRun.err());

    const canonical = JSON.parse(canonicalRun.out()) as {
      routes: string[];
      discovered: Array<Record<string, unknown>>;
    };
    const wrapper = JSON.parse(wrapperRun.out()) as {
      routes: string[];
      discovered: Array<Record<string, unknown>>;
    };
    assert.deepEqual(wrapper.routes, canonical.routes);
    assert.deepEqual(wrapper.discovered, canonical.discovered);
    assert.ok(wrapper.routes.includes('claude-nine-configured'));
  } finally {
    if (originalHome === undefined) delete process.env.HOME;
    else process.env.HOME = originalHome;
    if (originalKey === undefined) delete process.env.FIXTURE_COUNCIL_KEY;
    else process.env.FIXTURE_COUNCIL_KEY = originalKey;
  }
});

test('wrapper: generated wrapper template imports the canonical LocalHost view', () => {
  const source = renderClaudeNineWrapper();
  assert.ok(source.includes('composeClaudeNineLocalHost'));
  assert.ok(source.includes('createClaudeNineBridge'));
  assert.ok(source.includes('runCli'));
  for (const line of source.split('\n').filter((line) => line.trim().startsWith('import'))) {
    assert.ok(!line.includes('openclaw'), `wrapper imports another host tree: ${line}`);
  }
});

// ---------------------------------------------------------------------------
// URL preservation on browser-open failure
// ---------------------------------------------------------------------------

test('browser-open: a throw from the opener preserves the exact URL and a manual-open recovery', () => {
  const url = 'https://council.invalid/report/session-42?seat=simon-sinek';
  const result = openCouncilUrl(url, {
    platform: 'darwin',
    spawn: () => {
      throw new Error('no display');
    },
  });
  assert.equal(result.url, url);
  assert.equal(result.opened, false);
  assert.ok(result.error?.includes('no display'));
  assert.ok(result.recovery?.includes(url));
  assert.ok(result.command?.startsWith('open '));
});

test('browser-open: a nonzero opener exit preserves the exact URL', () => {
  const url = 'https://council.invalid/report/session-43';
  const result = openCouncilUrl(url, {
    platform: 'linux',
    spawn: () => ({ status: 1 }),
  });
  assert.equal(result.url, url);
  assert.equal(result.opened, false);
  assert.ok(result.recovery?.includes(url));
  assert.ok(result.command?.startsWith('xdg-open '));
});

test('browser-open: a successful open returns the URL and no recovery text', () => {
  const url = 'https://council.invalid/report/session-44';
  const result = openCouncilUrl(url, {
    platform: 'darwin',
    spawn: () => ({ status: 0 }),
  });
  assert.equal(result.url, url);
  assert.equal(result.opened, true);
  assert.equal(result.error, null);
  assert.equal(result.recovery, null);
});

test('browser-open: an invalid URL is still returned verbatim with a usable recovery', () => {
  const url = 'not a url';
  const result = openCouncilUrl(url, {
    spawn: () => {
      throw new Error('must not be called');
    },
  });
  assert.equal(result.url, url);
  assert.equal(result.opened, false);
  assert.ok(result.recovery?.includes(url));
});
