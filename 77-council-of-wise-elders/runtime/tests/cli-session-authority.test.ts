/**
 * CTR-101 gap B: the supported `blackceo-council` entry and the Council
 * service must resolve the SAME authoritative session store.
 *
 * Before this fix the CLI session commands opened the unrelated per-user
 * default (~/Library/Application Support/BlackCEO/WiseElders) while the
 * service ran on the directory wire.sh gave it
 * ($OPENCLAW_ROOT/council-data). A session convened through the service
 * was therefore invisible to `blackceo-council status <id>`.
 *
 * Every case runs against temporary directories. No real box state is
 * read and no service or provider is contacted.
 */
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { runCli, type CliIo } from '../src/cli/dispatcher.js';
import { createLocalHost } from '../src/cli/local-host.js';
import { resolveDataDir } from '../src/cli/paths.js';

function temp(label: string): string {
  return mkdtempSync(join(tmpdir(), `ctr101-${label}-`));
}

function capture(): { io: CliIo; out: () => string; err: () => string } {
  let out = '';
  let err = '';
  return { io: { out: (t) => (out += t), err: (t) => (err += t) }, out: () => out, err: () => err };
}

test('data dir: COUNCIL_SERVICE_DATA_DIR (the launcher value) wins over the per-user default', () => {
  const home = temp('home');
  const serviceDir = temp('svc-env');
  assert.equal(
    resolveDataDir({
      env: { HOME: home, COUNCIL_SERVICE_DATA_DIR: serviceDir } as NodeJS.ProcessEnv,
      homeDir: home,
    }),
    serviceDir,
  );
});

test('data dir: the install receipt active.json dataDir wins over the default', () => {
  const home = temp('home');
  const prefix = temp('prefix');
  const durable = temp('durable');
  writeFileSync(join(prefix, 'active.json'), JSON.stringify({ dataDir: durable }));
  assert.equal(
    resolveDataDir({
      env: { HOME: home, COUNCIL_RUNTIME_PREFIX: prefix } as NodeJS.ProcessEnv,
      homeDir: home,
    }),
    durable,
  );
});

test('data dir: <openclaw root>/council-data (wire.sh layout) wins when it exists', () => {
  const home = temp('home');
  const oc = temp('openclaw');
  mkdirSync(join(oc, 'council-data'), { recursive: true });
  assert.equal(
    resolveDataDir({
      env: { HOME: home, WISE_ELDERS_OPENCLAW_ROOT: oc } as NodeJS.ProcessEnv,
      homeDir: home,
    }),
    join(oc, 'council-data'),
  );
});

test('data dir: --data-dir still beats every authority, and the env override beats the service hint', () => {
  const home = temp('home');
  const serviceDir = temp('svc-env');
  const explicit = temp('explicit');
  const env = {
    HOME: home,
    COUNCIL_SERVICE_DATA_DIR: serviceDir,
    BLACKCEO_COUNCIL_DATA_DIR: explicit,
  } as NodeJS.ProcessEnv;
  assert.equal(resolveDataDir({ override: explicit, env, homeDir: home }), explicit);
  assert.equal(resolveDataDir({ env: { ...env, BLACKCEO_COUNCIL_DATA_DIR: explicit }, homeDir: home }), explicit);
});

test('data dir: the Section 16.1 skill-tree refusal still fires for a service-hinted path', () => {
  const home = temp('home');
  const skillRoot = temp('skill');
  const inside = join(skillRoot, 'state');
  assert.throws(
    () =>
      resolveDataDir({
        env: { HOME: home, COUNCIL_SERVICE_DATA_DIR: inside } as NodeJS.ProcessEnv,
        skillRoot,
        homeDir: home,
      }),
    /inside the skill folder/,
  );
});

test('CLI status reads the session the service created, from the service data dir', async () => {
  const home = temp('home');
  const serviceDir = temp('svc-store');
  const env = { HOME: home } as NodeJS.ProcessEnv;

  // Seed one sample session exactly as a local create would.
  const seeded = capture();
  const createCode = await runCli(['create', '--sample', '--json', '--data-dir', serviceDir], seeded.io, { env });
  assert.equal(createCode, 0, seeded.err());
  const sessionId = JSON.parse(seeded.out()).session_id as string;

  // Now behave like the shim: the service's durable directory is the only
  // authority named, and no --data-dir flag is passed.
  const read = capture();
  const readCode = await runCli(['status', sessionId, '--json'], read.io, {
    env: { ...env, COUNCIL_SERVICE_DATA_DIR: serviceDir },
  });
  assert.equal(readCode, 0, read.err());
  assert.equal(JSON.parse(read.out()).session_id, sessionId);

  // Control: an unrelated empty home still resolves the OLD default, and
  // the same id is genuinely absent there. This is the pre-fix behaviour,
  // kept here so the fix is what moves the result.
  const emptyHome = temp('empty-home');
  const miss = capture();
  const missCode = await runCli(['status', sessionId, '--json'], miss.io, {
    env: { HOME: emptyHome } as NodeJS.ProcessEnv,
  });
  assert.equal(missCode, 3);
  assert.equal(JSON.parse(miss.err()).error.code, 'COUNCIL_SESSION_NOT_FOUND');
});

test('CLI status stays a read: no new events are recorded against the session', async () => {
  const home = temp('home');
  const dataDir = temp('read-store');
  const env = { HOME: home } as NodeJS.ProcessEnv;

  const seeded = capture();
  assert.equal(await runCli(['create', '--sample', '--json', '--data-dir', dataDir], seeded.io, { env }), 0);
  const sessionId = JSON.parse(seeded.out()).session_id as string;

  const before = createLocalHost({ dataDir, discoverRoutes: false });
  const eventsBefore = await before.store.listEvents(sessionId);

  const read = capture();
  const code = await runCli(['status', sessionId, '--json', '--data-dir', dataDir], read.io, { env });
  assert.equal(code, 0, read.err());

  const after = createLocalHost({ dataDir, discoverRoutes: false });
  const eventsAfter = await after.store.listEvents(sessionId);
  assert.equal(eventsAfter.length, eventsBefore.length);
  assert.equal(JSON.parse(read.out()).session_id, sessionId);
  before.store.close();
  after.store.close();
});
