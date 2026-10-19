/**
 * WER-022 platform adapter tests.
 *
 * Runner (the runtime's own test runner):
 *   node --import tsx --test src/platform/platform.test.ts
 *
 * Tier A only: injected mount tables, injected container evidence, injected
 * writability, loopback HTTP servers on ephemeral ports and a durable file in
 * a temporary directory. NO real VPS, NO real container recreate, NO real
 * gateway connectivity, NO systemd/launchd unit and NO authenticated remote
 * origin is claimed. Those remain DEFERRED to WER-026/WER-027.
 *
 * Proven here:
 * - an ephemeral/short-lived mount backs the data dir -> REFUSED with a
 *   concrete reason; a persistent mount -> accepted;
 * - a data dir inside a replaceable tree -> refused;
 * - an unobservable/undetermined platform -> typed BLOCKED_PLATFORM, not a pass;
 * - container loopback ambiguity -> explicit failure, never the host guess;
 * - an unrelated listener -> refused and LEFT RUNNING (never killed);
 * - restart/recreate -> sessions and reservations restored, no duplicate.
 */

import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { CouncilFrontDoor } from '../service/front-door.js';
import { buildServiceIdentity } from '../service/identity.js';
import { resolvePlatform } from './adapter.js';
import { resolveServiceIdentity, SERVICE_NAME_ENV } from './identity.js';
import { observeContainer, resolveLoopback } from './loopback.js';
import { classifyMountType, evaluateDataDir, parseMountInfo } from './mounts.js';
import { acquireServiceEndpoint } from './ports.js';
import {
  createRestoredView,
  fileStateStore,
  restoreAfterRecreation,
  type DurableHandoff,
} from './recreation.js';
import {
  HANDOFF_SCHEMA,
  PLATFORM_SCHEMA,
  isPlatformRefusal,
  type ContainerObservation,
  type MountTable,
} from './types.js';

const FIXED_NOW = '2026-10-18T12:00:00.000Z';
const nowUtc = (): string => FIXED_NOW;

function scratch(): string {
  return mkdtempSync(join(tmpdir(), 'operator-W09-U001-'));
}

function mountTable(records: MountTable['records']): MountTable {
  return {
    observed: true,
    records,
    source: 'test-mountinfo',
    error: null,
    checked: ['test-mountinfo'],
  };
}

const containerPresent: ContainerObservation = {
  evidence: 'present',
  markers: ['/.dockerenv'],
  checked: ['/.dockerenv'],
  error: null,
};

const containerAbsent: ContainerObservation = {
  evidence: 'absent',
  markers: [],
  checked: ['platform:linux'],
  error: null,
};

// ------------------------------------------------------------------- mounts

test('mountinfo parsing unescapes mount points and flags read-only mounts', () => {
  const text = [
    '36 35 98:0 /mnt1 /mnt1 rw,noatime master:1 - ext3 /dev/root rw,errors=continue',
    '37 36 0:32 / /data/council\\040state ro,relatime - ext4 /dev/sdb1 ro',
  ].join('\n');

  const parsed = parseMountInfo(text);

  assert.equal(parsed.unparsed, 0);
  assert.equal(parsed.records.length, 2);
  assert.deepEqual(parsed.records[0], {
    mount_point: '/mnt1',
    fs_type: 'ext3',
    device: '/dev/root',
    read_only: false,
  });
  assert.deepEqual(parsed.records[1], {
    mount_point: '/data/council state',
    fs_type: 'ext4',
    device: '/dev/sdb1',
    read_only: true,
  });

  assert.equal(classifyMountType('overlay'), 'ephemeral');
  assert.equal(classifyMountType('tmpfs'), 'ephemeral');
  assert.equal(classifyMountType('ext4'), 'persistent');
  assert.equal(classifyMountType('virtiofs'), 'undetermined');
});

test('an ephemeral mount is refused with a concrete reason while a persistent mount is accepted', () => {
  const dataDir = scratch();

  const ephemeral = evaluateDataDir({
    dataDir,
    mounts: mountTable([
      { mount_point: '/', fs_type: 'overlay', device: 'overlay', read_only: false },
    ]),
    isWritable: () => true,
  });

  assert.ok(isPlatformRefusal(ephemeral));
  assert.equal(ephemeral.code, 'PLATFORM_DATA_DIR_EPHEMERAL');
  assert.equal(ephemeral.condition, 'DATA_DIR_EPHEMERAL_MOUNT');
  assert.match(ephemeral.detail, /"overlay"/);
  assert.match(ephemeral.detail, /lost on a container recreate/);
  assert.match(ephemeral.recovery, /durable host volume/);

  const tmpfs = evaluateDataDir({
    dataDir,
    mounts: mountTable([
      { mount_point: '/', fs_type: 'ext4', device: '/dev/sda1', read_only: false },
      { mount_point: dataDir, fs_type: 'tmpfs', device: 'tmpfs', read_only: false },
    ]),
    isWritable: () => true,
  });
  assert.ok(isPlatformRefusal(tmpfs));
  assert.equal(tmpfs.code, 'PLATFORM_DATA_DIR_EPHEMERAL');
  assert.match(tmpfs.detail, /"tmpfs"/);

  const persistent = evaluateDataDir({
    dataDir,
    mounts: mountTable([
      { mount_point: '/', fs_type: 'overlay', device: 'overlay', read_only: false },
      { mount_point: dataDir, fs_type: 'ext4', device: '/dev/sdb1', read_only: false },
    ]),
    isWritable: () => true,
  });

  assert.ok(!isPlatformRefusal(persistent));
  assert.equal(persistent.kind, 'persistent');
  assert.equal(persistent.fs_type, 'ext4');
  assert.equal(persistent.mount.mount_point, dataDir);
});

test('a data dir inside a replaceable tree is refused', () => {
  const root = scratch();
  const verdict = evaluateDataDir({
    dataDir: join(root, 'council-data'),
    replaceableRoots: [root],
    mounts: mountTable([
      { mount_point: '/', fs_type: 'ext4', device: '/dev/sda1', read_only: false },
    ]),
    isWritable: () => true,
  });

  assert.ok(isPlatformRefusal(verdict));
  assert.equal(verdict.code, 'PLATFORM_DATA_DIR_INSIDE_REPLACEABLE_TREE');
});

test('undetermined and unobservable mounts surface typed BLOCKED_PLATFORM, never a pass', () => {
  const dataDir = scratch();

  const undetermined = evaluateDataDir({
    dataDir,
    mounts: mountTable([
      { mount_point: '/', fs_type: 'virtiofs', device: 'virtiofs', read_only: false },
    ]),
    isWritable: () => true,
  });
  assert.ok(isPlatformRefusal(undetermined));
  assert.equal(undetermined.code, 'BLOCKED_PLATFORM');
  assert.equal(undetermined.condition, 'MOUNT_PERSISTENCE_UNDETERMINED');
  assert.equal(undetermined.requires_real_host, true);

  const unobserved = evaluateDataDir({
    dataDir,
    mounts: {
      observed: false,
      records: [],
      source: 'no mount table observer for darwin',
      error: 'no observer',
      checked: [],
    },
    isWritable: () => true,
  });
  assert.ok(isPlatformRefusal(unobserved));
  assert.equal(unobserved.code, 'BLOCKED_PLATFORM');
  assert.equal(unobserved.condition, 'MOUNT_TABLE_NOT_AVAILABLE_ON_THIS_PLATFORM');
  assert.equal(unobserved.requires_real_host, true);
});

// ----------------------------------------------------------------- loopback

test('container loopback ambiguity fails explicitly instead of assuming the host', async () => {
  const fromHost = await resolveLoopback({ container: containerPresent, target: 'host' });
  assert.ok(isPlatformRefusal(fromHost));
  assert.equal(fromHost.code, 'PLATFORM_LOOPBACK_AMBIGUOUS');
  assert.equal(fromHost.condition, 'HOST_LOOPBACK_UNVERIFIABLE');
  assert.match(fromHost.detail, /CURRENT CONTAINER/);
  assert.match(fromHost.detail, /host\.docker\.internal/);

  const inContainer = await resolveLoopback({ container: containerPresent, target: 'container' });
  assert.ok(!isPlatformRefusal(inContainer));
  assert.equal(inContainer.scope, 'container');
  assert.equal(inContainer.address, '127.0.0.1');

  const onHost = await resolveLoopback({ container: containerAbsent, target: 'host' });
  assert.ok(!isPlatformRefusal(onHost));
  assert.equal(onHost.scope, 'host');

  const unobservable = await resolveLoopback({
    container: { evidence: 'unknown', markers: [], checked: ['/proc/self/cgroup'], error: 'EACCES' },
    target: 'host',
  });
  assert.ok(isPlatformRefusal(unobservable));
  assert.equal(unobservable.code, 'BLOCKED_PLATFORM');
  assert.equal(unobservable.condition, 'CONTAINER_RUNTIME_UNOBSERVABLE');
  assert.equal(unobservable.requires_real_host, true);

  const unprovenAddress = await resolveLoopback({
    container: containerPresent,
    target: 'host',
    explicitHostAddress: 'host.docker.internal',
    probeHost: async (address) => ({
      reachable: false,
      detail: `${address} did not answer`,
      checked: [address],
    }),
  });
  assert.ok(isPlatformRefusal(unprovenAddress));
  assert.equal(unprovenAddress.code, 'PLATFORM_LOOPBACK_AMBIGUOUS');

  const provenAddress = await resolveLoopback({
    container: containerPresent,
    target: 'host',
    explicitHostAddress: '10.0.0.5',
    probeHost: async (address) => ({
      reachable: true,
      detail: `${address} answered the health probe`,
      checked: [address],
    }),
  });
  assert.ok(!isPlatformRefusal(provenAddress));
  assert.equal(provenAddress.scope, 'host');
  assert.equal(provenAddress.address, '10.0.0.5');
});

test('default container observation is total and never throws', () => {
  const observation = observeContainer({ env: {}, platform: 'darwin' });
  assert.ok(
    observation.evidence === 'present' ||
      observation.evidence === 'absent' ||
      observation.evidence === 'unknown',
  );
  assert.ok(Array.isArray(observation.checked));
});

// -------------------------------------------------------------- service id

test('service identity resolves a service name and never substitutes the hostname', () => {
  const unresolved = resolveServiceIdentity({
    env: {},
    uid: 501,
    gid: 20,
    user: 'operator',
    hostname: 'mac-mini.local',
  });
  assert.ok(isPlatformRefusal(unresolved));
  assert.equal(unresolved.code, 'PLATFORM_SERVICE_IDENTITY_UNRESOLVED');
  assert.match(unresolved.detail, /hostname is not a service name/);

  const fromEnv = resolveServiceIdentity({
    env: { [SERVICE_NAME_ENV]: 'council-service' },
    uid: 0,
    gid: 0,
    user: 'root',
  });
  assert.ok(!isPlatformRefusal(fromEnv));
  assert.equal(fromEnv.identity.service_name, 'council-service');
  assert.equal(fromEnv.identity.service_name_source, 'env');
  assert.equal(fromEnv.identity.is_root, true);

  const fromSystemd = resolveServiceIdentity({
    env: { SYSTEMD_UNIT: 'council.service' },
    uid: 1000,
    gid: 1000,
    user: 'council',
  });
  assert.ok(!isPlatformRefusal(fromSystemd));
  assert.equal(fromSystemd.identity.service_name, 'council');
  assert.equal(fromSystemd.identity.service_name_source, 'systemd_unit');
});

// -------------------------------------------------------------------- ports

async function listen(handler: Parameters<typeof createServer>[0]): Promise<{
  server: Server;
  port: number;
}> {
  const server = createServer(handler);
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve());
  });
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  return { server, port: address.port };
}

async function close(server: Server): Promise<void> {
  await new Promise<void>((resolve) => server.close(() => resolve()));
}

function serviceIdentity() {
  return buildServiceIdentity({
    tenant_id: 'tenant-w09',
    company_id: 'company-w09',
    data_dir: '/data/council',
    started_at: FIXED_NOW,
  });
}

const noOpen = (url: string) => ({
  url,
  opened: false,
  command: null,
  error: 'not opened in tests',
  recovery: url,
});

test('an unrelated listener is refused and left running, never killed', async () => {
  const unrelated = await listen((_req, res) => {
    res.writeHead(200, { 'content-type': 'text/plain' });
    res.end('not the council');
  });

  const frontDoor = new CouncilFrontDoor({
    identity: serviceIdentity(),
    host: '127.0.0.1',
    ports: [unrelated.port],
    openUrl: noOpen,
  });

  const acquisition = await acquireServiceEndpoint(frontDoor);

  assert.equal(acquisition.kind, 'refused');
  if (acquisition.kind !== 'refused') return;
  const refusal = acquisition.refusals.find(
    (entry) => entry.code === 'PLATFORM_PORT_UNRELATED_LISTENER',
  );
  assert.ok(refusal, 'the unrelated listener is reported by code');
  assert.match(refusal.detail, /left running/);

  const stillAlive = await fetch(`http://127.0.0.1:${unrelated.port}/`);
  assert.equal(stillAlive.status, 200);
  assert.equal(await stillAlive.text(), 'not the council');

  await close(unrelated.server);
});

test('a free port is acquired alongside, and the unrelated listener is untouched', async () => {
  const unrelated = await listen((_req, res) => {
    res.writeHead(200, { 'content-type': 'text/plain' });
    res.end('not the council');
  });

  const frontDoor = new CouncilFrontDoor({
    identity: serviceIdentity(),
    host: '127.0.0.1',
    ports: [unrelated.port, 0],
    openUrl: noOpen,
  });

  const acquisition = await acquireServiceEndpoint(frontDoor);
  assert.equal(acquisition.kind, 'acquired');
  if (acquisition.kind !== 'acquired') return;
  assert.equal(acquisition.outcome, 'started');
  assert.ok(acquisition.port > 0);
  assert.notEqual(acquisition.port, unrelated.port);

  const stillAlive = await fetch(`http://127.0.0.1:${unrelated.port}/`);
  assert.equal(await stillAlive.text(), 'not the council');

  await frontDoor.stop();
  await close(unrelated.server);
});

// --------------------------------------------------------------- recreation

function handoff(generation: number): DurableHandoff {
  return {
    schema_version: HANDOFF_SCHEMA,
    generation,
    sessions: [
      { session_id: 'session-a', authority: 'standalone' },
      {
        session_id: 'session-b',
        authority: 'managed',
        owning_session_url: 'https://cc.example.test/council/session-b',
      },
    ],
    reservations: [
      { reservation_id: 'res-1', operation_id: 'op-1', state: 'held' },
      { reservation_id: 'res-2', operation_id: 'op-2', state: 'held' },
      { reservation_id: 'res-3', operation_id: 'op-3', state: 'released' },
    ],
    written_at: FIXED_NOW,
  };
}

test('restart/recreation restores sessions and reservations with no duplicate', async () => {
  const path = join(scratch(), 'handoff.json');
  const store = fileStateStore(path);
  await store.write(JSON.stringify(handoff(7)));

  const before = createRestoredView();
  const restored = await restoreAfterRecreation({ store, view: before, nowUtc });

  assert.equal(restored.kind, 'restored');
  if (restored.kind !== 'restored') return;
  assert.equal(restored.generation, 7);
  assert.equal(restored.sessions, 2);
  assert.equal(restored.reservations, 3);
  assert.equal(restored.added_sessions, 2);
  assert.equal(restored.added_reservations, 3);
  assert.equal(restored.duplicates_created, 0);

  // Simulated container recreate: a NEW process with an EMPTY view.
  const after = createRestoredView();
  const recreated = await restoreAfterRecreation({ store, view: after, nowUtc });

  assert.equal(recreated.kind, 'restored');
  if (recreated.kind !== 'restored') return;
  assert.equal(recreated.sessions, 2);
  assert.equal(recreated.reservations, 3);
  assert.equal(recreated.added_sessions, 2);
  assert.equal(recreated.added_reservations, 3);
  assert.equal(recreated.duplicates_created, 0);
  assert.deepEqual([...after.sessions.keys()].sort(), ['session-a', 'session-b']);
  assert.deepEqual([...after.reservations.keys()].sort(), ['res-1', 'res-2', 'res-3']);

  // Double-init on the SAME view must not duplicate anything.
  const twice = await restoreAfterRecreation({ store, view: before, nowUtc });
  assert.equal(twice.kind, 'restored');
  if (twice.kind !== 'restored') return;
  assert.equal(twice.added_sessions, 0);
  assert.equal(twice.existing_sessions, 2);
  assert.equal(twice.added_reservations, 0);
  assert.equal(twice.existing_reservations, 3);
  assert.equal(before.sessions.size, 2);
  assert.equal(before.reservations.size, 3);
  assert.equal(twice.duplicates_created, 0);
});

test('duplicate ids in the durable handoff are refused, never silently deduplicated', async () => {
  const path = join(scratch(), 'handoff.json');
  const store = fileStateStore(path);
  const duplicated = handoff(3);
  duplicated.sessions.push({ session_id: 'session-a', authority: 'standalone' });
  await store.write(JSON.stringify(duplicated));

  const outcome = await restoreAfterRecreation({
    store,
    view: createRestoredView(),
    nowUtc,
  });

  assert.ok(isPlatformRefusal(outcome));
  assert.equal(outcome.code, 'PLATFORM_STATE_HANDOFF_DUPLICATE');
  assert.equal(outcome.condition, 'HANDOFF_DUPLICATE');
});

test('a stale handoff generation is refused so a released reservation is not resurrected', async () => {
  const path = join(scratch(), 'handoff.json');
  const store = fileStateStore(path);
  await store.write(JSON.stringify(handoff(4)));

  const view = createRestoredView();
  view.generation = 9;

  const outcome = await restoreAfterRecreation({ store, view, nowUtc });

  assert.ok(isPlatformRefusal(outcome));
  assert.equal(outcome.code, 'PLATFORM_STATE_HANDOFF_INVALID');
  assert.equal(outcome.condition, 'HANDOFF_STALE');
});

test('an absent durable handoff is an explicit empty restore, not an error', async () => {
  const store = fileStateStore(join(scratch(), 'missing.json'));
  const outcome = await restoreAfterRecreation({
    store,
    view: createRestoredView(),
    nowUtc,
  });

  assert.equal(outcome.kind, 'empty');
  if (outcome.kind !== 'empty') return;
  assert.equal(outcome.sessions, 0);
  assert.equal(outcome.reservations, 0);
});

// ------------------------------------------------------------------ adapter

test('resolvePlatform returns a ready receipt on a simulated container with a durable bind mount', async () => {
  const dataDir = scratch();
  const receipt = await resolvePlatform({
    dataDir,
    replaceableRoots: ['/opt/openclaw/skills/77-council-of-wise-elders'],
    mounts: mountTable([
      { mount_point: '/', fs_type: 'overlay', device: 'overlay', read_only: false },
      { mount_point: dataDir, fs_type: 'ext4', device: '/dev/sdb1', read_only: false },
    ]),
    container: containerPresent,
    identity: { serviceName: 'council-service', uid: 1000, gid: 1000, user: 'council' },
    isWritable: () => true,
    nowUtc,
  });

  assert.ok(!isPlatformRefusal(receipt));
  assert.equal(receipt.kind, 'ready');
  assert.equal(receipt.schema_version, PLATFORM_SCHEMA);
  assert.equal(receipt.platform, 'container');
  assert.equal(receipt.data_dir, dataDir);
  assert.equal(receipt.mount.fs_type, 'ext4');
  assert.equal(receipt.identity.service_name, 'council-service');
  assert.equal(receipt.loopback.scope, 'container');
  assert.equal(receipt.loopback.address, '127.0.0.1');
  assert.deepEqual(receipt.external_requirements, []);
  assert.ok(receipt.deferred_to_real_host.length > 0);
  assert.equal(receipt.observed_at, FIXED_NOW);
});

test('resolvePlatform surfaces typed BLOCKED_PLATFORM when the platform cannot be observed', async () => {
  const receipt = await resolvePlatform({
    dataDir: scratch(),
    platform: 'darwin',
    identity: { serviceName: 'council-service', uid: 501, gid: 20, user: 'operator' },
    isWritable: () => true,
    nowUtc,
  });

  assert.ok(isPlatformRefusal(receipt));
  assert.equal(receipt.code, 'BLOCKED_PLATFORM');
  assert.equal(receipt.requires_real_host, true);
  assert.ok(receipt.condition === 'MOUNT_TABLE_NOT_AVAILABLE_ON_THIS_PLATFORM');
});

test('resolvePlatform refuses an ephemeral data dir before any service start', async () => {
  const dataDir = scratch();
  const receipt = await resolvePlatform({
    dataDir,
    mounts: mountTable([
      { mount_point: '/', fs_type: 'overlay', device: 'overlay', read_only: false },
    ]),
    container: containerPresent,
    identity: { serviceName: 'council-service', uid: 1000, gid: 1000, user: 'council' },
    isWritable: () => true,
    nowUtc,
  });

  assert.ok(isPlatformRefusal(receipt));
  assert.equal(receipt.code, 'PLATFORM_DATA_DIR_EPHEMERAL');
  assert.match(receipt.detail, /overlay/);
});
