/**
 * Canonical Council front-door composition root (W20-U001, F5).
 *
 * Before this module the only wiring lived OUTSIDE the repository, in a
 * hand-written host launcher that constructed `new CouncilFrontDoor({
 * identity, host, ports })` and bound no readiness probe at all. Every
 * layer therefore reported READINESS_PROBE_NOT_BOUND (or UI_NOT_BUNDLED
 * for `ui`), so `usable` could never be true on the status page of a
 * service that was in fact running.
 *
 * This root moves that wiring INTO the repository and binds exactly the
 * probes this slice can observe truthfully:
 *
 *   ui          `runtime/public/chamber/index.html` resolves from the
 *               module's packaged asset root.
 *   discovery   the service's own loopback identity endpoint answers on
 *               the bound origin with a structurally valid, matching
 *               identity document.
 *   executable  `process.execPath` exists and the tsx CLI resolves from
 *               the installed runtime.
 *   packs       all nine advisor packs and their ten required files
 *               resolve on disk under the installed skill root.
 *
 * `store`, `route`, `routeCallable` and `worker` stay UNBOUND on purpose:
 * they need a real store, a composed provider route and a supervised
 * worker, none of which this slice owns. A truthful `unknown` is the
 * observation; this module never fabricates `ready`.
 *
 * Module-load discipline: no child_process, no process.env read, no
 * network call, no directory is created and no listener is started until
 * the caller invokes the exported functions.
 */

import { existsSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { homedir, platform } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { SEAT_IDS } from '../contracts/enums.js';
import { CouncilFrontDoor, isLoopbackHost } from './front-door.js';
import {
  SERVICE_IDENTITY_PATH,
  buildServiceIdentity,
  isServiceIdentity,
  normalizeOrigin,
  serviceIdentityMatches,
} from './identity.js';
import type { ReadinessObservation, ReadinessProbe } from './readiness.js';
import type {
  AdmissionSink,
  ServiceIdentity,
  StartOutcome,
} from './types.js';

/** Files every installed advisor pack must carry (CWE-012 layout). */
const ADVISOR_PACK_FILES = [
  'profile.json',
  'briefing.md',
  'frameworks.json',
  'decision-rules.json',
  'failure-patterns.json',
  'questions.json',
  'communication.md',
  'sources.json',
  'coverage.json',
  'evals.json',
] as const;

/**
 * Packaged chamber asset roots. Both layouts are tried: TypeScript source
 * (`src/service`) and compiled output (`dist/service`), exactly as the
 * front door resolves its assets.
 */
const CHAMBER_INDEX_CANDIDATES: readonly URL[] = [
  new URL('../../public/chamber/index.html', import.meta.url),
  new URL('../public/chamber/index.html', import.meta.url),
];

const CHAMBER_INDEX_ARTIFACT = 'runtime/public/chamber/index.html';

export interface CouncilServiceCompositionOptions {
  /** Owner tenant served at the identity endpoint. */
  tenantId?: string;
  /** Owner company served at the identity endpoint. */
  companyId?: string;
  /** Durable data directory; created on composition when absent. */
  dataDir?: string;
  /** Observed start time; defaults to the injected clock. */
  startedAt?: string;
  host?: string;
  ports?: readonly number[];
  fetchImpl?: typeof fetch;
  /** The owning authority's admission surface (approval front door + producer). */
  admissionSink?: AdmissionSink;
  /** Injected clock for identity/readiness observation times. */
  nowUtc?: () => string;
}

export interface CouncilServiceComposition {
  identity: ServiceIdentity;
  door: CouncilFrontDoor;
}

export interface StartedCouncilService {
  composition: CouncilServiceComposition;
  outcome: StartOutcome;
  origin: string | null;
  port: number | null;
  /** Drain and stop the listener this handle owns, exactly once. */
  stop(): Promise<void>;
}

function defaultServiceDataDir(): string {
  const home = homedir();
  switch (platform()) {
    case 'darwin':
      return join(home, 'Library', 'Application Support', 'wise-elders', 'service');
    case 'win32':
      return join(home, 'AppData', 'Local', 'wise-elders', 'service');
    default:
      return join(home, '.local', 'share', 'wise-elders', 'service');
  }
}

/**
 * The skill folder that contains this runtime, found by walking up to the
 * first ancestor carrying the skill signature (SKILL.md beside runtime/).
 * Returns null instead of guessing another boundary.
 */
function resolveSkillRoot(): string | null {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let depth = 0; depth < 8; depth += 1) {
    if (existsSync(join(dir, 'SKILL.md')) && existsSync(join(dir, 'runtime'))) {
      return dir;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

/** Resolve the installed tsx CLI without spawning it or reading the env. */
function resolveTsxCli(): string | null {
  try {
    const requireFn = createRequire(import.meta.url);
    const packagePath = requireFn.resolve('tsx/package.json');
    const cli = join(dirname(packagePath), 'dist', 'cli.mjs');
    return existsSync(cli) ? cli : null;
  } catch {
    return null;
  }
}

function uiProbe(): ReadinessObservation {
  for (const candidate of CHAMBER_INDEX_CANDIDATES) {
    if (existsSync(candidate)) {
      return { state: 'ready', artifact: CHAMBER_INDEX_ARTIFACT };
    }
  }
  return {
    state: 'blocked',
    artifact: null,
    blocker: {
      code: 'UI_NOT_BUNDLED',
      detail: 'No packaged chamber index.html resolves from this module layout.',
    },
    recovery:
      'Build or install the runtime assets so runtime/public/chamber/index.html is present, then re-run service-readiness.',
  };
}

function executableProbe(): ReadinessObservation {
  if (!process.execPath || !existsSync(process.execPath)) {
    return {
      state: 'blocked',
      artifact: null,
      blocker: {
        code: 'EXECUTABLE_NOT_FOUND',
        detail: 'process.execPath does not resolve to a file on disk.',
      },
      recovery: 'Run the service from an installed Node.js runtime.',
    };
  }
  if (!resolveTsxCli()) {
    return {
      state: 'blocked',
      artifact: `node ${process.version}; tsx CLI unresolved`,
      blocker: {
        code: 'EXECUTABLE_TSX_MISSING',
        detail: 'The tsx CLI does not resolve from the installed runtime.',
      },
      recovery:
        'Install the runtime development dependencies (npm ci in the skill runtime) or launch the compiled bundle, then re-run service-readiness.',
    };
  }
  return {
    state: 'ready',
    artifact: `node ${process.version}; tsx CLI resolved`,
  };
}

function packsProbe(): ReadinessObservation {
  const skillRoot = resolveSkillRoot();
  if (!skillRoot) {
    return {
      state: 'blocked',
      artifact: null,
      blocker: {
        code: 'PACKS_NOT_RESOLVED',
        detail: 'No installed skill root carrying SKILL.md beside runtime/ was found.',
      },
      recovery:
        'Install the verified Skill 77 advisor tree and re-run service-readiness.',
    };
  }

  const missing: string[] = [];
  for (const seat of SEAT_IDS) {
    for (const file of ADVISOR_PACK_FILES) {
      const relative = `advisors/${seat}/${file}`;
      if (!existsSync(join(skillRoot, relative))) missing.push(relative);
    }
  }

  if (missing.length > 0) {
    return {
      state: 'blocked',
      artifact: `${SEAT_IDS.length * ADVISOR_PACK_FILES.length - missing.length}/${
        SEAT_IDS.length * ADVISOR_PACK_FILES.length
      } advisor pack files resolved`,
      blocker: {
        code: 'PACKS_INCOMPLETE',
        detail: `${missing.length} advisor pack file(s) are missing; first: ${missing[0]}`,
      },
      recovery:
        'Reinstall the verified Skill 77 advisor packs and re-run service-readiness.',
    };
  }

  return {
    state: 'ready',
    artifact: `${SEAT_IDS.length}/${SEAT_IDS.length} advisor packs resolved (${
      ADVISOR_PACK_FILES.length
    } files each)`,
  };
}

/**
 * The identity endpoint must answer on the bound loopback origin with a
 * structurally valid document that matches this owner. Only loopback is
 * consulted, so readiness never reaches an external origin.
 */
function discoveryProbe(input: {
  identity: ServiceIdentity;
  origin: () => string | null;
  fetchImpl?: typeof fetch;
}): ReadinessProbe {
  return async () => {
    const origin = input.origin();
    if (!origin) {
      return {
        state: 'unknown',
        artifact: null,
        blocker: {
          code: 'DISCOVERY_ORIGIN_UNBOUND',
          detail: 'The front door has not bound an origin yet.',
        },
        recovery: 'Start the front door, then re-run service-readiness.',
      };
    }

    let hostname: string;
    try {
      hostname = new URL(origin).hostname;
    } catch {
      return {
        state: 'blocked',
        artifact: null,
        blocker: {
          code: 'DISCOVERY_ORIGIN_INVALID',
          detail: 'The bound origin is not a parseable URL.',
        },
        recovery: 'Restart the front door and re-run service-readiness.',
      };
    }
    const bare = hostname.startsWith('[') && hostname.endsWith(']')
      ? hostname.slice(1, -1)
      : hostname;
    if (!isLoopbackHost(bare)) {
      return {
        state: 'blocked',
        artifact: null,
        blocker: {
          code: 'DISCOVERY_ORIGIN_NOT_LOOPBACK',
          detail: 'Readiness probes only the loopback origin; no external host is consulted.',
        },
        recovery:
          'Bind a loopback host (127.0.0.1/localhost); authenticated remote exposure belongs to the tunnel adapter.',
      };
    }

    const fetchImpl = input.fetchImpl ?? globalThis.fetch;
    const url = `${normalizeOrigin(origin)}${SERVICE_IDENTITY_PATH}`;
    try {
      const response = await fetchImpl(url, {
        method: 'GET',
        headers: { accept: 'application/json' },
        signal: AbortSignal.timeout(1_500),
      });
      if (!response.ok) {
        return {
          state: 'blocked',
          artifact: url,
          blocker: {
            code: 'DISCOVERY_HTTP_ERROR',
            detail: `The identity endpoint answered HTTP ${response.status}.`,
          },
          recovery: 'Restart the front door and re-run service-readiness.',
        };
      }
      const body: unknown = await response.json();
      if (
        !isServiceIdentity(body) ||
        !serviceIdentityMatches(input.identity, body)
      ) {
        return {
          state: 'blocked',
          artifact: url,
          blocker: {
            code: 'DISCOVERY_IDENTITY_MISMATCH',
            detail:
              'The identity endpoint answered with a document that is not this service identity.',
          },
          recovery:
            'Verify the listener on this origin is this Council service, then re-run service-readiness.',
        };
      }
      return { state: 'ready', artifact: `identity endpoint answered at ${origin}` };
    } catch (error) {
      return {
        state: 'blocked',
        artifact: url,
        blocker: {
          code: 'DISCOVERY_UNREACHABLE',
          detail: error instanceof Error ? error.message : String(error),
        },
        recovery: 'Start the front door and re-run service-readiness.',
      };
    }
  };
}

/**
 * Build the identity and the front door with the truthful probe set bound.
 * No listener is started here.
 */
export function composeCouncilService(
  options: CouncilServiceCompositionOptions = {},
): CouncilServiceComposition {
  const nowUtc = options.nowUtc ?? (() => new Date().toISOString());
  const dataDir = options.dataDir ?? defaultServiceDataDir();
  mkdirSync(dataDir, { recursive: true });

  const identity = buildServiceIdentity({
    tenant_id: options.tenantId ?? 'operator',
    company_id: options.companyId ?? 'blackceo',
    data_dir: dataDir,
    started_at: options.startedAt ?? nowUtc(),
  });

  let doorRef: CouncilFrontDoor | null = null;
  const origin = (): string | null => doorRef?.getOrigin() ?? null;

  const door = new CouncilFrontDoor({
    identity,
    host: options.host,
    ports: options.ports,
    fetchImpl: options.fetchImpl,
    admissionSink: options.admissionSink,
    readiness: {
      nowUtc,
      discovery: discoveryProbe({
        identity,
        origin,
        fetchImpl: options.fetchImpl,
      }),
      executable: executableProbe,
      packs: packsProbe,
      ui: uiProbe,
      // store, route, routeCallable and worker intentionally stay unbound:
      // a truthful `unknown` is better than a fabricated `ready`.
    },
  });
  doorRef = door;

  return { identity, door };
}

/**
 * Compose, start, and keep the front door alive until SIGTERM/SIGINT.
 * Signal handlers can be disabled for tests and embedded callers.
 */
export async function startCouncilService(
  options: CouncilServiceCompositionOptions & { handleSignals?: boolean } = {},
): Promise<StartedCouncilService> {
  const composition = composeCouncilService(options);
  const outcome = await composition.door.start();

  let stopping: Promise<void> | null = null;
  const stop = (): Promise<void> => {
    if (!stopping) {
      stopping = (async () => {
        composition.door.drain();
        await composition.door.stop();
      })();
    }
    return stopping;
  };

  if ((options.handleSignals ?? true) && outcome.outcome !== 'refused') {
    const shutdown = (): void => {
      void stop().finally(() => process.exit(0));
    };
    process.once('SIGTERM', shutdown);
    process.once('SIGINT', shutdown);
  }

  return {
    composition,
    outcome,
    origin: outcome.origin,
    port: outcome.port,
    stop,
  };
}
