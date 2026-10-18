/**
 * Platform adapter composition (WER-022 dependency-ready slice).
 *
 * `resolvePlatform` answers, in order, the questions a real VPS/container
 * deployment must answer before the council service may start:
 *
 *   1. container or host (and is that observable at all?);
 *   2. is the data directory on a persistent writable mount outside every
 *      replaceable tree?;
 *   3. which UID and which SERVICE NAME does this process run as?;
 *   4. which network namespace does the loopback bind actually name?
 *
 * Any condition this slice cannot observe is a typed refusal — a
 * `BLOCKED_PLATFORM` with `requires_real_host: true` when only a real host can
 * answer it. Nothing here is satisfied by `host.docker.internal`, by a fixed
 * port, by Command Center or by Vercel.
 *
 * The endpoint acquisition (which free port, without killing an unrelated
 * listener) is `acquireServiceEndpoint` in ./ports.ts, which reuses the
 * WER-021 front door rather than duplicating its contract.
 */

import {
  PLATFORM_DEFERRED_TO_REAL_HOST,
  PLATFORM_EXTERNAL_REQUIREMENTS,
  PLATFORM_SCHEMA,
  isPlatformRefusal,
  platformRefusal,
  type ContainerObservation,
  type MountTable,
  type PlatformReceipt,
  type PlatformRefusal,
} from './types.js';
import { resolveServiceIdentity, type ServiceIdentityOptions } from './identity.js';
import { observeContainer, resolveLoopback } from './loopback.js';
import { defaultMountTable, evaluateDataDir, type DataDirVerdict } from './mounts.js';
import { evaluateWindowsDataDir } from './windows.js';

export interface PlatformOptions {
  /** Absolute durable data directory. Never inside a replaceable tree. */
  dataDir: string;
  /** Skill folder, runtime release dir, scratch: never durable storage. */
  replaceableRoots?: readonly string[];
  /** Injected mount table; defaults to Linux /proc/self/mountinfo. */
  mounts?: MountTable;
  /** Injected container observation; defaults to marker + cgroup detection. */
  container?: ContainerObservation;
  /** UID / service-name inputs. */
  identity?: ServiceIdentityOptions;
  platform?: NodeJS.Platform;
  /** Injected writability probe; defaults to a real access(W_OK) check. */
  isWritable?: (path: string) => boolean;
  /** Injected clock for the receipt. */
  nowUtc?: () => string;
}

/**
 * Resolve the platform or refuse with a typed condition.
 *
 * Returns a value in every case; never throws for an observed condition.
 */
export async function resolvePlatform(
  options: PlatformOptions,
): Promise<PlatformReceipt | PlatformRefusal> {
  const platform = options.platform ?? process.platform;
  const checked: string[] = [];

  const container =
    options.container ?? observeContainer({ env: options.identity?.env, platform });
  checked.push(...container.checked);

  if (container.evidence === 'unknown') {
    return platformRefusal({
      code: 'BLOCKED_PLATFORM',
      condition: 'CONTAINER_RUNTIME_UNOBSERVABLE',
      detail: `Container state could not be observed (${container.error ?? 'no marker and no readable cgroup'}). Host-versus-container loopback and durable-mount expectations are undetermined.`,
      recovery:
        'Run the adapter on the real host, or supply an observed container state. A real VPS/container host is required.',
      requires_real_host: true,
      checked,
      unknowns: ['whether this process runs in a container'],
    });
  }

  let verdict: DataDirVerdict;
  if (options.mounts) {
    // An explicitly injected mount table is the caller's evidence.
    checked.push(...options.mounts.checked);
    verdict = evaluateDataDir({
      dataDir: options.dataDir,
      replaceableRoots: options.replaceableRoots,
      mounts: options.mounts,
      isWritable: options.isWritable,
    });
  } else if (platform === 'win32') {
    // Windows has no mount table; observe the volume from real facts.
    verdict = evaluateWindowsDataDir({
      dataDir: options.dataDir,
      replaceableRoots: options.replaceableRoots,
      env: options.identity?.env,
      isWritable: options.isWritable,
    });
  } else {
    const mounts = defaultMountTable(platform);
    checked.push(...mounts.checked);
    verdict = evaluateDataDir({
      dataDir: options.dataDir,
      replaceableRoots: options.replaceableRoots,
      mounts,
      isWritable: options.isWritable,
    });
  }
  if (isPlatformRefusal(verdict)) return verdict;
  checked.push(...verdict.evidence);

  const identityResult = resolveServiceIdentity({
    ...options.identity,
    platform: options.identity?.platform ?? platform,
    hostname: options.identity?.hostname,
  });
  if (isPlatformRefusal(identityResult)) return identityResult;
  const identity = identityResult.identity;
  checked.push('process uid/gid', 'service name sources');

  const kind = container.evidence === 'present' ? 'container' : 'host';
  const loopbackResult = await resolveLoopback({
    container,
    target: kind,
  });
  if (isPlatformRefusal(loopbackResult)) return loopbackResult;

  checked.push(...loopbackResult.evidence);

  return {
    schema_version: PLATFORM_SCHEMA,
    kind: 'ready',
    platform: kind,
    data_dir: verdict.data_dir,
    mount: {
      mount_point: verdict.mount.mount_point,
      fs_type: verdict.mount.fs_type,
      read_only: false,
    },
    identity,
    loopback: { scope: loopbackResult.scope, address: loopbackResult.address },
    external_requirements: PLATFORM_EXTERNAL_REQUIREMENTS,
    deferred_to_real_host: PLATFORM_DEFERRED_TO_REAL_HOST,
    checked: [...new Set(checked)],
    observed_at: (options.nowUtc ?? (() => new Date().toISOString()))(),
  };
}

/** Synchronous guard for callers that must not proceed on a refusal. */
export function assertPlatformReady(
  receipt: PlatformReceipt | PlatformRefusal,
): PlatformReceipt {
  if (isPlatformRefusal(receipt)) {
    throw new Error(`${receipt.code} (${receipt.condition}): ${receipt.detail}`);
  }
  return receipt;
}
