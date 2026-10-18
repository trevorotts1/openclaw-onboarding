/**
 * Container detection and container-vs-host loopback disambiguation
 * (WER-022).
 *
 * `127.0.0.1` inside a container names THE CURRENT CONTAINER's network
 * namespace. It does not name the host, and `host.docker.internal` is a
 * Desktop convenience that (a) does not exist on Linux Docker by default and
 * (b) proves nothing about reachability even when the name resolves. So:
 *
 * - asking for the HOST loopback from inside a container is an explicit
 *   `PLATFORM_LOOPBACK_AMBIGUOUS` refusal, never a guess;
 * - a caller MAY supply an explicit published host address, but it is
 *   accepted only when an injected reachability probe says reachable —
 *   a name or a fixed port is never proof;
 * - when container evidence cannot be observed at all, the answer is a typed
 *   `BLOCKED_PLATFORM` and not a pass.
 */

import { existsSync, readFileSync } from 'node:fs';

import {
  platformRefusal,
  type ContainerEvidence,
  type ContainerObservation,
  type LoopbackObservation,
  type LoopbackTarget,
  type PlatformRefusal,
} from './types.js';

/** Environment marker used by several container runtimes. */
const CONTAINER_ENV_KEYS = ['container', 'container_id', 'OPENCLAW_CONTAINER'] as const;

/**
 * Windows-only container markers. Windows containers have no `/.dockerenv`
 * and no cgroup table, so only an explicit runtime marker is evidence.
 */
const WINDOWS_CONTAINER_ENV_KEYS = [
  'CONTAINER_SANDBOX_MOUNT_POINT',
  'DOTNET_RUNNING_IN_CONTAINER',
  'KUBERNETES_SERVICE_HOST',
] as const;

/** cgroup text markers for the common runtimes. */
const CGROUP_CONTAINER_MARKERS =
  /(docker|kubepods|containerd|libpod|podman|lxc|lxd|crio|garden)/i;

/** Container marker files. */
const CONTAINER_MARKER_FILES = ['/.dockerenv', '/run/.containerenv'] as const;

/** cgroup files read by the default observer. */
const CGROUP_FILES = ['/proc/self/cgroup', '/proc/1/cgroup'] as const;

/**
 * Observe whether this process runs inside a container.
 *
 * `present` requires a positive marker. `absent` requires a successfully
 * read cgroup state (on Linux) or a platform where no Linux container marker
 * can apply (macOS). Windows has neither `/.dockerenv` nor a cgroup table, so
 * without a runtime environment marker the answer is `unknown`, which the
 * callers turn into BLOCKED_PLATFORM instead of assuming "not a container".
 * A read failure also leaves the answer `unknown`.
 */
export function observeContainer(
  options: { env?: NodeJS.ProcessEnv; platform?: NodeJS.Platform } = {},
): ContainerObservation {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const markers: string[] = [];
  const checked: string[] = [];

  for (const file of CONTAINER_MARKER_FILES) {
    checked.push(file);
    try {
      if (existsSync(file)) markers.push(file);
    } catch {
      // An unreadable marker is simply not evidence; the cgroup check below
      // still decides, and an unreadable state ends as `unknown`.
    }
  }

  const envKeys =
    platform === 'win32'
      ? [...CONTAINER_ENV_KEYS, ...WINDOWS_CONTAINER_ENV_KEYS]
      : [...CONTAINER_ENV_KEYS];
  for (const key of envKeys) {
    if (platform === 'win32') checked.push(`env:${key}`);
    const value = env[key];
    if (typeof value === 'string' && value.trim().length > 0) {
      markers.push(`env:${key}`);
    }
  }

  if (markers.length > 0) {
    return { evidence: 'present', markers, checked, error: null };
  }

  if (platform === 'win32') {
    // Windows has no `/.dockerenv` and no cgroup table. Absence of a marker
    // does not prove this is a host process, so the answer stays unknown and
    // the callers surface BLOCKED_PLATFORM.
    checked.push('platform:win32', 'marker:/.dockerenv', 'marker:/run/.containerenv', 'cgroup(none)');
    return {
      evidence: 'unknown',
      markers,
      checked,
      error:
        'Windows exposes no container marker file and no cgroup table; only runtime environment markers are observable, and none is present.',
    };
  }

  if (platform !== 'linux') {
    // No Linux container marker can apply; on macOS this process is a host
    // process unless a marker above said otherwise.
    checked.push(`platform:${platform}`);
    return { evidence: 'absent', markers, checked, error: null };
  }

  let readAny = false;
  const errors: string[] = [];
  for (const file of CGROUP_FILES) {
    checked.push(file);
    try {
      const text = readFileSync(file, 'utf8');
      readAny = true;
      if (CGROUP_CONTAINER_MARKERS.test(text)) {
        markers.push(file);
        return { evidence: 'present', markers, checked, error: null };
      }
    } catch (error) {
      errors.push(`${file}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (!readAny) {
    return {
      evidence: 'unknown',
      markers,
      checked,
      error: errors.join('; ') || 'no cgroup file could be read',
    };
  }

  return { evidence: 'absent', markers, checked, error: errors.join('; ') || null };
}

export interface LoopbackOptions {
  container: ContainerObservation;
  /** Which network namespace the caller wants. Default: `host`. */
  target?: LoopbackTarget;
  /** The address the service binds. Loopback only in this slice. */
  address?: string;
  /**
   * An explicit host address the caller claims is published. Never trusted
   * on its own: `probeHost` must confirm reachability.
   */
  explicitHostAddress?: string | null;
  probeHost?: (address: string) => Promise<{
    reachable: boolean;
    detail: string;
    checked: string[];
  }>;
}

/**
 * Resolve which namespace a loopback address names.
 *
 * A host process: loopback is the host. A container process asking for the
 * container: loopback is the current container. A container process asking
 * for the host: refused as ambiguous unless an explicit published address is
 * proven reachable.
 */
export async function resolveLoopback(
  options: LoopbackOptions,
): Promise<LoopbackObservation | PlatformRefusal> {
  const address = options.address ?? '127.0.0.1';
  const target = options.target ?? 'host';
  const checked = [...options.container.checked];
  const evidence: string[] = [];

  if (options.container.evidence === 'unknown') {
    return platformRefusal({
      code: 'BLOCKED_PLATFORM',
      condition: 'CONTAINER_RUNTIME_UNOBSERVABLE',
      detail: `Container state could not be observed (${options.container.error ?? 'no marker and no readable cgroup'}). Whether ${address} names the host or a container is undetermined, so neither is assumed.`,
      recovery:
        'Run the adapter on the real host, or supply an observed container state. A real VPS/container host is required to prove the network namespace.',
      requires_real_host: true,
      checked,
      unknowns: ['network namespace behind the loopback address'],
    });
  }

  const inContainer = options.container.evidence === 'present';
  evidence.push(`container=${options.container.evidence}`);
  evidence.push(...options.container.markers);

  if (!inContainer) {
    return { ok: true, scope: 'host', address, evidence };
  }

  if (target === 'container') {
    evidence.push('loopback names the current container network namespace');
    return { ok: true, scope: 'container', address, evidence };
  }

  const explicit = options.explicitHostAddress?.trim();
  if (explicit) {
    const probe = options.probeHost;
    if (!probe) {
      return platformRefusal({
        code: 'PLATFORM_LOOPBACK_UNSUPPORTED',
        condition: 'HOST_LOOPBACK_UNVERIFIABLE',
        detail: `A host address ${explicit} was supplied from inside a container, but no reachability probe is bound. Neither a name nor a fixed port proves reachability.`,
        recovery:
          'Bind a reachability probe for the published host address, or resolve the loopback target as `container`.',
        checked: [...checked, explicit],
        unknowns: ['reachability of the published host address'],
      });
    }
    const result = await probe(explicit);
    checked.push(...result.checked, explicit);
    if (result.reachable) {
      evidence.push(`probe:${result.detail}`);
      return { ok: true, scope: 'host', address: explicit, evidence };
    }
    return platformRefusal({
      code: 'PLATFORM_LOOPBACK_AMBIGUOUS',
      condition: 'HOST_LOOPBACK_UNVERIFIABLE',
      detail: `This process runs inside a container. ${address} names the CURRENT CONTAINER, not the host, and the supplied host address ${explicit} was not reachable (${result.detail}). It is never assumed.`,
      recovery:
        'Publish the service on an explicit host address and prove it reachable, or resolve the loopback target as `container`; host.docker.internal is never treated as proof.',
      checked,
      unknowns: ['a proven host address for the service'],
    });
  }

  return platformRefusal({
    code: 'PLATFORM_LOOPBACK_AMBIGUOUS',
    condition: 'HOST_LOOPBACK_UNVERIFIABLE',
    detail: `This process runs inside a container (${options.container.markers.join(', ') || 'container marker observed'}). ${address} names the CURRENT CONTAINER's network namespace, not the host. host.docker.internal and a fixed port are never treated as proof of host reachability.`,
    recovery:
      'Resolve the loopback target as `container`, or supply an explicit published host address together with a reachability probe.',
    checked,
    unknowns: ['a proven host address for the service'],
  });
}

/** Convenience for callers that only need the boolean shape. */
export function containerKind(evidence: ContainerEvidence): 'host' | 'container' | 'unknown' {
  if (evidence === 'present') return 'container';
  if (evidence === 'absent') return 'host';
  return 'unknown';
}
