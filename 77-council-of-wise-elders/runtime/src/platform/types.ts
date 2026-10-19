/**
 * OpenClaw VPS/container platform adapter contract (WER-022 dependency-ready
 * slice).
 *
 * Consumed by path import — this slice adds no package export map entry:
 *
 *   import { resolvePlatform } from '../platform/index.js';
 *
 * WHAT THIS IS. A typed, dependency-injected answer to the questions a real
 * VPS or container deployment must answer BEFORE a service may start:
 *
 * - is the durable data directory on a persistent writable mount, and is it
 *   outside every replaceable tree (skill folder, runtime release dir)?
 * - which UID/service identity and service NAME does this process actually
 *   run as (never assumed to be `localhost`)?
 * - does `127.0.0.1` name the host or the current container?
 * - which loopback port is free, without killing an unrelated listener?
 * - after a container recreate, do sessions and reservations come back from
 *   durable state with no duplicate?
 *
 * WHAT THIS IS NOT. No VPS and no container is available to this unit, so
 * nothing here executes a real deployment, recreates a real container,
 * proves real gateway connectivity or yields an authenticated remote URL.
 * Those stay DEFERRED and are named in `PLATFORM_DEFERRED_TO_REAL_HOST`.
 * A condition only a real host can answer is a typed `BLOCKED_PLATFORM`
 * refusal, never a pass.
 *
 * No external product is required: Command Center and Vercel are always
 * optional (`PLATFORM_EXTERNAL_REQUIREMENTS` is empty).
 */

/** Receipt schema for a resolved platform. */
export const PLATFORM_SCHEMA = 'wise-elders.platform-adapter/v1';
/** Durable handoff schema written by the owning authority before a recreate. */
export const HANDOFF_SCHEMA = 'wise-elders.platform-handoff/v1';

/**
 * Proven only on a real host. Never claimed by this unit, and never reported
 * as done by the adapter.
 */
export const PLATFORM_DEFERRED_TO_REAL_HOST: readonly string[] = [
  'a real VPS deployment and a real container recreate',
  'a real gateway connectivity check from a recreated container',
  'an authenticated remote origin (Cloudflare Tunnel/Access, WER-023)',
  'systemd/launchd service registration and unit start',
  'proof of host reachability from inside a container beyond an explicit published address',
];

/** Empty on purpose: no Command Center, no Vercel, no third party. */
export const PLATFORM_EXTERNAL_REQUIREMENTS: readonly string[] = [];

export type PlatformKind = 'host' | 'container';

/** Typed refusal codes. Only BLOCKED_PLATFORM means "needs a real host". */
export type PlatformRefusalCode =
  | 'BLOCKED_PLATFORM'
  | 'PLATFORM_DATA_DIR_EPHEMERAL'
  | 'PLATFORM_DATA_DIR_NOT_WRITABLE'
  | 'PLATFORM_DATA_DIR_INSIDE_REPLACEABLE_TREE'
  | 'PLATFORM_DATA_DIR_NOT_ABSOLUTE'
  | 'PLATFORM_LOOPBACK_AMBIGUOUS'
  | 'PLATFORM_LOOPBACK_UNSUPPORTED'
  | 'PLATFORM_PORT_UNRELATED_LISTENER'
  | 'PLATFORM_HOST_NOT_LOOPBACK'
  | 'PLATFORM_ENDPOINT_UNAVAILABLE'
  | 'PLATFORM_SERVICE_IDENTITY_UNRESOLVED'
  | 'PLATFORM_STATE_HANDOFF_INVALID'
  | 'PLATFORM_STATE_HANDOFF_DUPLICATE';

/** The concrete condition behind a refusal. One refusal, one named cause. */
export type PlatformCondition =
  | 'CONTAINER_RUNTIME_UNOBSERVABLE'
  | 'MOUNT_TABLE_UNREADABLE'
  | 'MOUNT_TABLE_NOT_AVAILABLE_ON_THIS_PLATFORM'
  | 'MOUNT_NOT_OBSERVED_FOR_DATA_DIR'
  | 'MOUNT_PERSISTENCE_UNDETERMINED'
  | 'DATA_DIR_READ_ONLY_MOUNT'
  | 'DATA_DIR_NOT_WRITABLE'
  | 'DATA_DIR_INSIDE_REPLACEABLE_TREE'
  | 'DATA_DIR_EPHEMERAL_MOUNT'
  | 'DATA_DIR_NOT_ABSOLUTE'
  | 'HOST_LOOPBACK_UNVERIFIABLE'
  | 'SERVICE_NAME_UNRESOLVED'
  | 'UNRELATED_LISTENER'
  | 'HOST_NOT_LOOPBACK'
  | 'ENDPOINT_UNAVAILABLE'
  | 'HANDOFF_UNREADABLE'
  | 'HANDOFF_INVALID'
  | 'HANDOFF_DUPLICATE'
  | 'HANDOFF_STALE'
  | 'HANDOFF_STORE_UNWRITABLE';

/** Every refusal is explicit: code, condition, detail, recovery, evidence. */
export interface PlatformRefusal {
  schema_version: typeof PLATFORM_SCHEMA;
  kind: 'refused';
  code: PlatformRefusalCode;
  condition: PlatformCondition;
  detail: string;
  recovery: string;
  /** True only when no caller input can resolve it; a real host is required. */
  requires_real_host: boolean;
  /** Every input consulted, for negative-result evidence. */
  checked: string[];
  /** What was NOT observed. Never silently omitted. */
  unknowns: string[];
}

export function platformRefusal(input: {
  code: PlatformRefusalCode;
  condition: PlatformCondition;
  detail: string;
  recovery: string;
  requires_real_host?: boolean;
  checked?: readonly string[];
  unknowns?: readonly string[];
}): PlatformRefusal {
  return {
    schema_version: PLATFORM_SCHEMA,
    kind: 'refused',
    code: input.code,
    condition: input.condition,
    detail: input.detail,
    recovery: input.recovery,
    requires_real_host: input.requires_real_host === true,
    checked: [...(input.checked ?? [])],
    unknowns: [...(input.unknowns ?? [])],
  };
}

export function isPlatformRefusal(value: unknown): value is PlatformRefusal {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { kind?: unknown }).kind === 'refused' &&
    typeof (value as { code?: unknown }).code === 'string'
  );
}

// ---------------------------------------------------------------- mounts

/** One mount table entry, normalized. */
export interface MountRecord {
  mount_point: string;
  fs_type: string;
  device: string;
  read_only: boolean;
}

/** An observed (or injected) mount table with its provenance. */
export interface MountTable {
  observed: boolean;
  records: MountRecord[];
  source: string;
  error: string | null;
  checked: string[];
}

export type MountPersistence = 'persistent' | 'ephemeral' | 'undetermined';

// ------------------------------------------------------------ container

/**
 * Tri-state container observation. `unknown` is a real answer and forces a
 * BLOCKED_PLATFORM refusal rather than a guess.
 */
export type ContainerEvidence = 'present' | 'absent' | 'unknown';

export interface ContainerObservation {
  evidence: ContainerEvidence;
  markers: string[];
  checked: string[];
  error: string | null;
}

// ------------------------------------------------------------ identity

export type ServiceNameSource =
  | 'explicit'
  | 'env'
  | 'systemd_unit'
  | 'container_label'
  | 'unresolved';

export interface ProcessIdentity {
  uid: number | null;
  gid: number | null;
  user: string | null;
  uid_source: 'observed' | 'unobservable';
  /**
   * Windows account domain (`USERDOMAIN`) when observable. null on platforms
   * that have no such value and when it cannot be observed.
   */
  domain: string | null;
  /**
   * Windows `COMPUTERNAME` when observable. Recorded evidence only; it is
   * never used as a service name.
   */
  computer_name: string | null;
  /** Whether `user` came from a real observation or stays unobservable. */
  user_source: 'observed' | 'unobservable';
  /** Resolved service name. NEVER the hostname and NEVER `localhost`. */
  service_name: string | null;
  service_name_source: ServiceNameSource;
  /** Recorded for evidence only; deliberately not a service name. */
  hostname: string | null;
  is_root: boolean;
}

// ------------------------------------------------------------ loopback

export type LoopbackTarget = 'container' | 'host';

export interface LoopbackObservation {
  ok: true;
  scope: PlatformKind;
  address: string;
  evidence: string[];
}

// ------------------------------------------------------------ platform

export interface PlatformReceipt {
  schema_version: typeof PLATFORM_SCHEMA;
  kind: 'ready';
  platform: PlatformKind;
  data_dir: string;
  mount: {
    mount_point: string;
    fs_type: string;
    read_only: false;
  };
  identity: ProcessIdentity;
  loopback: {
    scope: PlatformKind;
    address: string;
  };
  /** Always empty: Command Center and Vercel are never required. */
  external_requirements: readonly string[];
  deferred_to_real_host: readonly string[];
  checked: string[];
  observed_at: string;
}
