/**
 * Process UID and service-name resolution (WER-022).
 *
 * The host is never assumed to be `localhost`, and the hostname is never
 * used as a service name. A service name resolves from, in order:
 *
 *   1. an explicit caller value;
 *   2. `BLACKCEO_COUNCIL_SERVICE_NAME`;
 *   3. `SYSTEMD_UNIT` (the unit suffix is stripped);
 *   4. a container-provided name, when this process is inside a container.
 *
 * Nothing else qualifies. When a name is required and none resolves, the
 * answer is a typed refusal — the adapter does not fall back to the hostname,
 * to `localhost` or to a fixed port.
 *
 * `uid`/`gid` are observed where the platform exposes them and reported as
 * `unobservable` where it does not (Windows); they are never invented. On
 * Windows the observable account facts are `os.userInfo().username` with
 * `USERNAME` as fallback, plus `USERDOMAIN` and `COMPUTERNAME`. When none of
 * them resolve the user stays `unobservable`.
 */

import { hostname as osHostname, userInfo } from 'node:os';

import {
  platformRefusal,
  type ProcessIdentity,
  type PlatformRefusal,
  type ServiceNameSource,
} from './types.js';

export interface ServiceIdentityOptions {
  /** Highest-precedence service name. */
  serviceName?: string | null;
  env?: NodeJS.ProcessEnv;
  /** Platform whose observable identity values are read. Default `process.platform`. */
  platform?: NodeJS.Platform;
  /** Injected process ids; defaults to `process.getuid()`/`getgid()` when present. */
  uid?: number | null;
  gid?: number | null;
  /** Injected login name; defaults to `os.userInfo().username`. */
  user?: string | null;
  /** Container-provided name (only used when `containerNameIsFromContainer` is true). */
  containerName?: string | null;
  /** Defaults to `os.hostname()`. Recorded, never used as a service name. */
  hostname?: string | null;
  /** When true, an unresolved name is an explicit refusal. Default true. */
  requireServiceName?: boolean;
}

export const SERVICE_NAME_ENV = 'BLACKCEO_COUNCIL_SERVICE_NAME';

function trimmed(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

function observeUid(): number | null {
  const getuid = (process as NodeJS.Process & { getuid?: () => number }).getuid;
  return typeof getuid === 'function' ? getuid() : null;
}

function observeGid(): number | null {
  const getgid = (process as NodeJS.Process & { getgid?: () => number }).getgid;
  return typeof getgid === 'function' ? getgid() : null;
}

function observeUser(): string | null {
  try {
    return userInfo().username || null;
  } catch {
    return null;
  }
}

function stripUnitSuffix(unit: string): string {
  return unit.replace(/\.service$/i, '');
}

export function resolveServiceIdentity(
  options: ServiceIdentityOptions = {},
): { ok: true; identity: ProcessIdentity } | PlatformRefusal {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const windows = platform === 'win32';
  const uid = options.uid !== undefined ? options.uid : observeUid();
  const gid = options.gid !== undefined ? options.gid : observeGid();
  const observedUser = options.user !== undefined ? options.user : observeUser();
  // Windows: os.userInfo() is tried first; `USERNAME` is the observable
  // fallback when it fails. Neither is invented when both are absent.
  const user = observedUser ?? (windows ? trimmed(env.USERNAME) : null);
  const domain = windows ? trimmed(env.USERDOMAIN) : null;
  const computerName = windows
    ? trimmed(env.COMPUTERNAME) ?? (process.platform === 'win32' ? observeHostname() : null)
    : null;

  let serviceName: string | null = null;
  let source: ServiceNameSource = 'unresolved';

  const explicit = trimmed(options.serviceName);
  const fromEnv = trimmed(env[SERVICE_NAME_ENV]);
  const fromSystemd = trimmed(env.SYSTEMD_UNIT);
  const fromContainer = trimmed(options.containerName);

  if (explicit) {
    serviceName = explicit;
    source = 'explicit';
  } else if (fromEnv) {
    serviceName = fromEnv;
    source = 'env';
  } else if (fromSystemd) {
    serviceName = stripUnitSuffix(fromSystemd);
    source = 'systemd_unit';
  } else if (fromContainer) {
    serviceName = fromContainer;
    source = 'container_label';
  }

  const identity: ProcessIdentity = {
    uid,
    gid,
    user,
    uid_source: uid === null ? 'unobservable' : 'observed',
    domain,
    computer_name: computerName,
    user_source: user === null ? 'unobservable' : 'observed',
    service_name: serviceName,
    service_name_source: source,
    hostname: options.hostname !== undefined ? options.hostname : observeHostname(),
    is_root: uid === 0,
  };

  if (options.requireServiceName !== false && serviceName === null) {
    return platformRefusal({
      code: 'PLATFORM_SERVICE_IDENTITY_UNRESOLVED',
      condition: 'SERVICE_NAME_UNRESOLVED',
      detail: `No service name resolved from explicit input, ${SERVICE_NAME_ENV}, SYSTEMD_UNIT or a container label. The hostname is not a service name, so it is not substituted.`,
      recovery: `Set ${SERVICE_NAME_ENV} (or pass serviceName) to the service this host runs, then re-run platform resolution.`,
      checked: ['option:serviceName', SERVICE_NAME_ENV, 'SYSTEMD_UNIT', 'container labels'],
      unknowns: ['the service name this process answers for'],
    });
  }

  return { ok: true, identity };
}

function observeHostname(): string | null {
  try {
    return osHostname() || null;
  } catch {
    return null;
  }
}
