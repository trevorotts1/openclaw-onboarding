/**
 * WER-027 Windows half A: Windows volume, path, identity and container
 * observation tests.
 *
 * Runner (the runtime's own test runner):
 *   node --import tsx --test src/platform/windows.test.ts
 *
 * These run on the operator host, NOT on Windows. Every Windows fact used
 * here is injected (env, statfs, realpath), so what is proven is the
 * OBSERVATION AND REFUSAL LOGIC, not a real volume, a real junction or a
 * real Windows container state. Those stay deferred to a real Windows host.
 */

import assert from 'node:assert/strict';
import { win32 } from 'node:path';
import test from 'node:test';

import { resolvePlatform } from './adapter.js';
import { resolveServiceIdentity, SERVICE_NAME_ENV } from './identity.js';
import { observeContainer, resolveLoopback } from './loopback.js';
import { isPlatformRefusal } from './types.js';
import {
  canonicalWindowsPath,
  evaluateWindowsDataDir,
  isInsideWindows,
  observeWindowsVolume,
  stripExtendedPrefix,
  windowsTempRoots,
  type WindowsVolumeSpace,
} from './windows.js';

const FIXED_NOW = '2026-10-18T12:00:00.000Z';

const SPACE: WindowsVolumeSpace = {
  bsize: 4096,
  blocks: 1_000_000,
  bfree: 400_000,
  bavail: 380_000,
  files: 200_000,
  ffree: 190_000,
};

const space = (): WindowsVolumeSpace => ({ ...SPACE });

/** Deterministic realpath: only mapped paths resolve, everything else fails. */
function fakeRealpath(map: Record<string, string>): (path: string) => string {
  const entries = new Map(
    Object.entries(map).map(([from, to]) => [win32.resolve(from).toLowerCase(), win32.resolve(to)]),
  );
  return (path: string) => {
    const hit = entries.get(win32.resolve(path).toLowerCase());
    if (hit !== undefined) return hit;
    throw Object.assign(new Error(`ENOENT: ${path}`), { code: 'ENOENT' });
  };
}

// ------------------------------------------------------------------ volumes

test('a data directory under the Windows Temp root is refused with the path and the rule', () => {
  const temp = String.raw`C:\Users\Trevor Otts\AppData\Local\Temp`;
  const dataDir = String.raw`C:\Users\Trevor Otts\AppData\Local\Temp\council`;

  const verdict = evaluateWindowsDataDir({
    dataDir,
    env: { SystemDrive: 'C:', TEMP: temp },
    statfs: space,
    isWritable: () => true,
  });

  assert.ok(isPlatformRefusal(verdict));
  assert.equal(verdict.code, 'PLATFORM_DATA_DIR_EPHEMERAL');
  assert.equal(verdict.condition, 'DATA_DIR_EPHEMERAL_MOUNT');
  assert.ok(verdict.detail.includes(dataDir), 'names the refused path');
  assert.ok(verdict.detail.includes(temp), 'names the temporary root');
  assert.match(verdict.detail, /env:TEMP/);
  assert.match(verdict.detail, /temporary root/i);
});

test('TMP and the USERPROFILE-derived temp root are also refused', () => {
  const cases: NodeJS.ProcessEnv[] = [
    { SystemDrive: 'C:', TMP: String.raw`D:\Scratch Temp` },
    { SystemDrive: 'C:', USERPROFILE: String.raw`C:\Users\Zoe Ng` },
  ];
  for (const env of cases) {
    const root = env.TMP ?? win32.join(String(env.USERPROFILE), 'AppData', 'Local', 'Temp');
    const verdict = evaluateWindowsDataDir({
      dataDir: win32.join(root, 'council'),
      env,
      statfs: space,
      isWritable: () => true,
    });
    assert.ok(isPlatformRefusal(verdict), `expected refusal for ${root}`);
    assert.equal(verdict.code, 'PLATFORM_DATA_DIR_EPHEMERAL');
  }
  assert.equal(windowsTempRoots({ USERPROFILE: String.raw`C:\Users\Zoe Ng` }).length, 1);
});

test('a path resolving THROUGH a junction into temp is refused by its target', () => {
  const temp = String.raw`C:\Users\Trevor\AppData\Local\Temp`;
  const raw = String.raw`D:\CouncilData`;
  const target = win32.join(temp, 'council');

  const verdict = evaluateWindowsDataDir({
    dataDir: raw,
    env: { SystemDrive: 'C:', TEMP: temp },
    realpath: fakeRealpath({ [raw]: target }),
    statfs: space,
    isWritable: () => true,
  });

  assert.ok(isPlatformRefusal(verdict));
  assert.equal(verdict.code, 'PLATFORM_DATA_DIR_EPHEMERAL');
  assert.ok(verdict.detail.includes(raw));
  assert.ok(verdict.detail.includes(target), 'names the resolved target');
  assert.match(verdict.detail, /resolved to/);
});

test('a junction from a temp path onto a durable target is classified by the target', () => {
  const temp = String.raw`C:\Users\Trevor\AppData\Local\Temp`;
  const raw = win32.join(temp, 'council-link');
  const target = String.raw`C:\CouncilData`;

  const verdict = evaluateWindowsDataDir({
    dataDir: raw,
    env: { SystemDrive: 'C:', TEMP: temp },
    realpath: fakeRealpath({ [raw]: target }),
    statfs: space,
    isWritable: () => true,
  });

  assert.ok(!isPlatformRefusal(verdict));
  assert.equal(verdict.kind, 'persistent');
  assert.equal(verdict.data_dir, raw);
  assert.ok(
    verdict.evidence.some((entry) => entry.toLowerCase().includes(target.toLowerCase())),
    'records the resolved target as evidence',
  );
});

test('a fixed drive is accepted with the observable statfs facts recorded', () => {
  const dataDir = String.raw`C:\CouncilData`;

  const verdict = evaluateWindowsDataDir({
    dataDir,
    env: { SystemDrive: 'C:' },
    statfs: space,
    isWritable: () => true,
  });

  assert.ok(!isPlatformRefusal(verdict));
  assert.equal(verdict.kind, 'persistent');
  assert.equal(verdict.data_dir, dataDir);
  assert.equal(verdict.fs_type, 'windows-fixed-volume');
  assert.equal(verdict.mount.mount_point, 'C:\\');
  assert.equal(verdict.mount.device, 'C:');
  assert.ok(verdict.evidence.some((entry) => entry.includes('bsize=4096')));
  assert.ok(verdict.evidence.some((entry) => entry.includes('ffree=190000')));
  assert.ok(verdict.evidence.some((entry) => entry.includes('env:SystemDrive=C:')));
});

test('a drive that cannot be characterised is BLOCKED_PLATFORM, never ok', () => {
  const verdict = evaluateWindowsDataDir({
    dataDir: String.raw`D:\CouncilData`,
    env: { SystemDrive: 'C:' },
    statfs: space,
    isWritable: () => true,
  });

  assert.ok(isPlatformRefusal(verdict));
  assert.equal(verdict.code, 'BLOCKED_PLATFORM');
  assert.equal(verdict.condition, 'MOUNT_PERSISTENCE_UNDETERMINED');
  assert.equal(verdict.requires_real_host, true);
  assert.match(verdict.detail, /D:/);

  const noSystemDrive = evaluateWindowsDataDir({
    dataDir: String.raw`C:\CouncilData`,
    env: {},
    statfs: space,
    isWritable: () => true,
  });
  assert.ok(isPlatformRefusal(noSystemDrive));
  assert.equal(noSystemDrive.code, 'BLOCKED_PLATFORM');
  assert.match(noSystemDrive.detail, /SystemDrive is not set/);
});

test('a UNC network volume is observed and never assumed durable', () => {
  const dataDir = String.raw`\\fileserver\shares\council`;

  const observation = observeWindowsVolume({
    dataDir,
    env: { SystemDrive: 'C:' },
    statfs: space,
  });
  assert.equal(observation.kind, 'network');
  assert.equal(observation.fs_type, 'windows-network-volume');

  const verdict = evaluateWindowsDataDir({
    dataDir,
    env: { SystemDrive: 'C:' },
    statfs: space,
    isWritable: () => true,
  });
  assert.ok(isPlatformRefusal(verdict));
  assert.equal(verdict.code, 'BLOCKED_PLATFORM');
  assert.match(verdict.detail, /network volume/i);
});

// -------------------------------------------------------------------- paths

test('paths with spaces and non-ASCII characters resolve exactly', () => {
  const dataDir = String.raw`C:\Users\Zoë Nguyễn\Daten Ordner\council`;

  const verdict = evaluateWindowsDataDir({
    dataDir,
    env: { SystemDrive: 'C:' },
    statfs: space,
    isWritable: () => true,
  });

  assert.ok(!isPlatformRefusal(verdict));
  assert.equal(verdict.data_dir, dataDir);
  assert.equal(verdict.data_dir.includes('/'), false, 'no POSIX separator is assumed');

  const insideReplaceable = evaluateWindowsDataDir({
    dataDir,
    replaceableRoots: [String.raw`c:\users\zoë nguyễn\Daten Ordner`],
    env: { SystemDrive: 'C:' },
    statfs: space,
    isWritable: () => true,
  });
  assert.ok(isPlatformRefusal(insideReplaceable));
  assert.equal(insideReplaceable.code, 'PLATFORM_DATA_DIR_INSIDE_REPLACEABLE_TREE');
});

test('segment boundaries are case-insensitive and never prefix-match siblings', () => {
  assert.equal(isInsideWindows(String.raw`C:\Data\council`, String.raw`C:\Data`), true);
  assert.equal(isInsideWindows(String.raw`C:\DATEN\council`, String.raw`C:\Daten`), true);
  assert.equal(isInsideWindows(String.raw`C:\Data2\council`, String.raw`C:\Data`), false);
  assert.equal(isInsideWindows(String.raw`C:\Data`, 'C:\\Data\\'), true);
});

test('extended-length prefixes and 8.3 spellings resolve through win32 path rules', () => {
  assert.equal(stripExtendedPrefix(String.raw`\\?\C:\Council`), String.raw`C:\Council`);
  assert.equal(
    stripExtendedPrefix(String.raw`\\?\UNC\fileserver\share\council`),
    String.raw`\\fileserver\share\council`,
  );
  assert.equal(
    canonicalWindowsPath(String.raw`C:\PROGRA~1\Council`),
    String.raw`C:\PROGRA~1\Council`,
  );

  const verdict = evaluateWindowsDataDir({
    dataDir: String.raw`\\?\C:\CouncilData`,
    env: { SystemDrive: 'C:' },
    statfs: space,
    isWritable: () => true,
  });
  assert.ok(!isPlatformRefusal(verdict));
  assert.equal(verdict.data_dir, String.raw`C:\CouncilData`);
});

// ----------------------------------------------------------------- identity

test('Windows service identity uses the observable account values', () => {
  const result = resolveServiceIdentity({
    platform: 'win32',
    env: {
      [SERVICE_NAME_ENV]: 'council-service',
      USERNAME: 'trevor',
      USERDOMAIN: 'BLACKCEO',
      COMPUTERNAME: 'OPS-MINI',
    },
    uid: null,
    gid: null,
    user: null,
  });

  assert.ok(!isPlatformRefusal(result));
  assert.equal(result.identity.user, 'trevor');
  assert.equal(result.identity.user_source, 'observed');
  assert.equal(result.identity.domain, 'BLACKCEO');
  assert.equal(result.identity.computer_name, 'OPS-MINI');
  assert.equal(result.identity.uid, null);
  assert.equal(result.identity.uid_source, 'unobservable');
});

test('Windows identity stays unobservable rather than inventing a name', () => {
  const result = resolveServiceIdentity({
    platform: 'win32',
    env: { [SERVICE_NAME_ENV]: 'council-service' },
    uid: null,
    gid: null,
    user: null,
  });

  assert.ok(!isPlatformRefusal(result));
  assert.equal(result.identity.user, null);
  assert.equal(result.identity.user_source, 'unobservable');
  assert.equal(result.identity.domain, null);
  assert.equal(result.identity.computer_name, null);
});

// ---------------------------------------------------------------- loopback

test('unknown Windows container state returns BLOCKED_PLATFORM, never host', async () => {
  const observation = observeContainer({ env: {}, platform: 'win32' });
  assert.equal(observation.evidence, 'unknown');
  assert.match(observation.error ?? '', /no container marker file and no cgroup/);

  const loopback = await resolveLoopback({ container: observation, target: 'host' });
  assert.ok(isPlatformRefusal(loopback));
  assert.equal(loopback.code, 'BLOCKED_PLATFORM');
  assert.equal(loopback.condition, 'CONTAINER_RUNTIME_UNOBSERVABLE');
  assert.equal(loopback.requires_real_host, true);

  const receipt = await resolvePlatform({
    dataDir: String.raw`C:\CouncilData`,
    platform: 'win32',
    identity: {
      env: { SystemDrive: 'C:', [SERVICE_NAME_ENV]: 'council-service' },
      platform: 'win32',
    },
    isWritable: () => true,
    nowUtc: () => FIXED_NOW,
  });
  assert.ok(isPlatformRefusal(receipt));
  assert.equal(receipt.code, 'BLOCKED_PLATFORM');
  assert.equal(receipt.condition, 'CONTAINER_RUNTIME_UNOBSERVABLE');
});

test('a Windows runtime container marker is observed as a container', async () => {
  const observation = observeContainer({
    env: { CONTAINER_SANDBOX_MOUNT_POINT: 'C:\\' },
    platform: 'win32',
  });
  assert.equal(observation.evidence, 'present');
  assert.ok(observation.markers.includes('env:CONTAINER_SANDBOX_MOUNT_POINT'));

  const loopback = await resolveLoopback({ container: observation, target: 'container' });
  assert.ok(!isPlatformRefusal(loopback));
  assert.equal(loopback.scope, 'container');
});
