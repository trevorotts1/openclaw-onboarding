/**
 * Canonical Council front-door and backend composition root.
 *
 * W20-U001 (F5) moved the host launcher's wiring INTO the repository and
 * bound the four probes that slice could observe truthfully: `ui`,
 * `discovery`, `executable`, `packs`.
 *
 * W22-U001 (this slice) binds the intended BACKEND over the service data
 * directory, so `store`, `route` and `worker` become observed truth
 * instead of READINESS_PROBE_NOT_BOUND:
 *
 *   store    one canonical SQLite handle opens at `<dataDir>/council.db`,
 *            the canonical CWE-005 schema is applied (additive), and all
 *            eighteen Section 16.2 tables are observed in sqlite_master.
 *            `EventJournal` and `ProjectionOutbox` are constructed by
 *            `CouncilRepositories` over that same handle.
 *   route    the SELECTED route (`routeId`, or the single composable
 *            discovered route) resolves read-only through the same
 *            `discoverConfiguredRoutes` / `resolveRouteForDispatch` path
 *            the runtime uses for dispatch, and the guarded provider
 *            dispatch port is bound. Offline readiness never calls it.
 *   worker   one `startCouncilWorkers` supervisor runs over the durable
 *            runner composed by `composeDeliberationService`, with a live
 *            read of the budget ledger and its poll generation.
 *
 * The deliberation composition's four HOST bindings (material catalog,
 * trusted-principal resolver, transport resolver, route budget) stay
 * unbound on purpose: composing them needs a skill-root/pack catalog and a
 * trusted admission principal, which the service root does not own. That
 * makes `DeliberationService.readiness()` honestly not-ready; it does NOT
 * block the service readiness layers above, and this module never claims a
 * completed deliberation or a live advisor turn.
 *
 * Lifecycle: one database handle, one worker supervisor, one listener.
 * `stop()` drains the listener, stops the workers (awaiting in-flight
 * work), and closes the handle exactly once. The supervisor timers are
 * unref'd; no child process is ever spawned.
 *
 * Module-load discipline: no child_process, no process.env read, no
 * network call, no directory is created, no database is opened and no
 * listener is started until the caller invokes the exported functions.
 */

import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { homedir, platform } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { resolveStandaloneInstallation, standaloneScope } from '../cli/authorization.js';
import {
  RouteDiscoveryError,
  discoverConfiguredRoutes,
  resolveRouteForDispatch,
  type DiscoveredRoute,
  type RouteDiscoveryOptions,
} from '../cli/route-discovery.js';
import type { Clock, IdSource } from '../contracts/index.js';
import { SEAT_IDS } from '../contracts/enums.js';
import {
  COUNCIL_SCHEMA_SQL,
  COUNCIL_TABLES_SECTION_16_2,
} from '../persistence/index.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import { envelopeFromScope } from '../persistence/envelope.js';
import { ensureInstallationProfile } from '../persistence/profile.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import { CouncilDatabase } from '../persistence/sqlite.js';
import {
  composeDeliberationService,
  type DeliberationService,
} from '../protocol/composition.js';
import type { RunnerTimers } from '../queue/runner.js';
import {
  startCouncilWorkers,
  stopCouncilWorkers,
  type CouncilWorkerHandle,
} from '../queue/workers.js';
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
  ServiceBlocker,
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

const WORKER_ID = 'council-service-worker';

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
  /**
   * The client's selected model route id (for example
   * `<providerId>-configured`). When absent, exactly one composable
   * discovered route is accepted; two or more is ambiguous.
   */
  routeId?: string;
  /** Home directory route discovery reads under. Default: the OS home. */
  routeHomeDir?: string;
  /** Environment route discovery reads. Default: process.env at call time. */
  routeEnv?: NodeJS.ProcessEnv;
  /**
   * The guarded provider dispatch port for the selected route. Bound by
   * the host launcher; readiness checks its presence and never invokes it
   * offline.
   */
  providerDispatch?: () => unknown | Promise<unknown>;
  /** Start the durable worker supervisor. Default true. */
  startWorkers?: boolean;
  /** Worker idle poll interval in milliseconds. Default: runner default. */
  workerPollIntervalMs?: number;
  /** Injected runner timers (tests). Default: unref'd system timers. */
  workerTimers?: RunnerTimers;
}

/** The backend members this root actually constructed. */
export interface CouncilServiceBackend {
  dataDir: string;
  databasePath: string;
  /** The one canonical handle the store, journal and workers share. */
  database: CouncilDatabase;
  /** Canonical repositories; `journal` and `outbox` are constructed here. */
  repositories: CouncilRepositories;
  /** Journal and outbox, kept as first-class handles for future surfaces. */
  journal: CouncilRepositories['journal'];
  outbox: CouncilRepositories['outbox'];
  /** The durable deliberation composition (runner, jobs, ledger, grants). */
  deliberation: DeliberationService;
  /** The running supervisor, or null when workers were disabled. */
  workers: CouncilWorkerHandle | null;
  /** Stop workers (awaiting in-flight work), then close the database once. */
  stop(): Promise<void>;
}

export interface CouncilServiceComposition {
  identity: ServiceIdentity;
  door: CouncilFrontDoor;
  backend: CouncilServiceBackend;
  /** Stop the backend (workers + database). The door is stopped separately. */
  stop(): Promise<void>;
}

export interface StartedCouncilService {
  composition: CouncilServiceComposition;
  outcome: StartOutcome;
  origin: string | null;
  port: number | null;
  /** Drain and stop the listener and backend this handle owns, exactly once. */
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

function blocked(
  code: string,
  detail: string,
  recovery: string,
  artifact: string | null = null,
): ReadinessObservation {
  const blocker: ServiceBlocker = { code, detail };
  return { state: 'blocked', artifact, blocker, recovery };
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
 * The store layer is ready only when the canonical handle opens and every
 * Section 16.2 table is present. Only table names are cited; no filesystem
 * path is ever served.
 */
function storeProbe(db: CouncilDatabase): ReadinessProbe {
  return () => {
    try {
      const rows = db.read((handle) =>
        handle
          .prepare(`SELECT name FROM sqlite_master WHERE type = 'table'`)
          .all(),
      ) as Array<{ name: string }>;
      const names = new Set(rows.map((row) => row.name));
      const missing = COUNCIL_TABLES_SECTION_16_2.filter(
        (table) => !names.has(table),
      );
      if (missing.length > 0) {
        return blocked(
          'PERSISTENCE_SCHEMA_UNAVAILABLE',
          `${missing.length} canonical council table(s) are missing from the open database; first: ${missing[0]}.`,
          'Apply the canonical council schema (council-0001) to the service data directory, then re-run service-readiness.',
          `council.db open; ${COUNCIL_TABLES_SECTION_16_2.length - missing.length}/${
            COUNCIL_TABLES_SECTION_16_2.length
          } canonical tables present`,
        );
      }
      return {
        state: 'ready',
        artifact: `council.db open; ${COUNCIL_TABLES_SECTION_16_2.length}/${COUNCIL_TABLES_SECTION_16_2.length} canonical tables present; journal and outbox bound`,
      };
    } catch (error) {
      return blocked(
        'PERSISTENCE_STORE_UNREADABLE',
        `The council database handle could not be read (${error instanceof Error ? error.name : 'unknown error'}).`,
        'Check the service data directory permissions and the database file, then re-run service-readiness.',
      );
    }
  };
}

interface RouteSelection {
  route: DiscoveredRoute | null;
  discovered: readonly DiscoveredRoute[];
  observation: ReadinessObservation | null;
}

/**
 * Resolve the SELECTED route read-only through the runtime's own strict
 * discovery path. Error messages are never surfaced (they name host
 * paths); only typed codes and route ids are.
 */
function selectRoute(options: {
  routeId?: string;
  routeHomeDir?: string;
  routeEnv?: NodeJS.ProcessEnv;
}): RouteSelection {
  const discovery: RouteDiscoveryOptions = {
    homeDir: options.routeHomeDir,
    env: options.routeEnv,
  };
  let discovered: readonly DiscoveredRoute[] = [];
  try {
    discovered = discoverConfiguredRoutes(discovery);
  } catch {
    discovered = [];
  }

  if (options.routeId) {
    try {
      const resolved = resolveRouteForDispatch(options.routeId, discovery);
      return { route: resolved.route, discovered, observation: null };
    } catch (error) {
      const code =
        error instanceof RouteDiscoveryError
          ? error.code
          : 'ROUTE_DISCOVERY_FAILED';
      return {
        route: null,
        discovered,
        observation: blocked(
          code,
          `The selected route ${options.routeId} is not configured and composable on this host.`,
          'Configure the selected client route (provider account, model and credential presence), or select a different route id, then re-run service-readiness.',
        ),
      };
    }
  }

  const composed = discovered.filter((route) => route.composable);
  if (discovered.length === 0) {
    return {
      route: null,
      discovered,
      observation: blocked(
        'ROUTE_NOT_CONFIGURED',
        'Route discovery found no configured client route on this host.',
        'Configure a supported client route (provider account + model) and re-run route discovery; no provider call is made by readiness.',
      ),
    };
  }
  if (composed.length === 0) {
    const first = discovered[0];
    return {
      route: null,
      discovered,
      observation: blocked(
        first.failure?.code ?? 'ROUTE_NOT_COMPOSABLE',
        `${discovered.length} configured route(s), 0 composable.`,
        'Fix the named route blocker (executable, endpoint, model or credential presence) and re-run route discovery.',
      ),
    };
  }
  if (composed.length > 1) {
    return {
      route: null,
      discovered,
      observation: blocked(
        'ROUTE_SELECTION_AMBIGUOUS',
        `${composed.length} composable routes are configured; the service requires an explicit selected route id.`,
        'Pass the client-selected route id (routeId) to the composition root; the service never picks among routes.',
      ),
    };
  }
  try {
    const resolved = resolveRouteForDispatch(composed[0].routeId, discovery);
    return { route: resolved.route, discovered, observation: null };
  } catch (error) {
    const code =
      error instanceof RouteDiscoveryError
        ? error.code
        : 'ROUTE_DISCOVERY_FAILED';
    return {
      route: null,
      discovered,
      observation: blocked(
        code,
        `The selected route ${composed[0].routeId} could not be resolved.`,
        'Fix the named route blocker and re-run route discovery.',
      ),
    };
  }
}

function routeProbe(options: {
  routeId?: string;
  routeHomeDir?: string;
  routeEnv?: NodeJS.ProcessEnv;
  providerDispatch?: () => unknown | Promise<unknown>;
}): ReadinessProbe {
  return () => {
    const selection = selectRoute(options);
    if (!selection.route) {
      return (
        selection.observation ??
        blocked(
          'ROUTE_NOT_CONFIGURED',
          'No selected route resolved.',
          'Configure and select a client route, then re-run service-readiness.',
        )
      );
    }
    if (typeof options.providerDispatch !== 'function') {
      return blocked(
        'ROUTE_DISPATCH_PORT_UNBOUND',
        `The selected route ${selection.route.routeId} is configured, but no provider dispatch port is bound for it.`,
        'Bind the selected route dispatch port in the host launcher, then re-run service-readiness; readiness never invents a transport.',
        `${selection.route.routeId} configured; dispatch port unbound`,
      );
    }
    const model = selection.route.compatible?.modelId;
    return {
      state: 'ready',
      artifact: `${selection.route.routeId} configured (${selection.route.providerSlug}${
        model ? ` / ${model}` : ''
      }); dispatch port bound`,
    };
  };
}

/**
 * Route callable is evaluated ONLY when readiness is online. It reaches
 * the provider exclusively through the readiness evaluator's guarded
 * dispatch port, so an offline evaluation can never make a provider call.
 */
function routeCallableProbe(options: {
  routeId?: string;
  routeHomeDir?: string;
  routeEnv?: NodeJS.ProcessEnv;
  providerDispatch?: () => unknown | Promise<unknown>;
}): ReadinessProbe {
  return async (context) => {
    const selection = selectRoute(options);
    if (!selection.route) {
      return (
        selection.observation ??
        blocked(
          'ROUTE_NOT_CONFIGURED',
          'No selected route resolved.',
          'Configure and select a client route, then re-run service-readiness.',
        )
      );
    }
    if (typeof options.providerDispatch !== 'function') {
      return blocked(
        'ROUTE_DISPATCH_PORT_UNBOUND',
        'No provider dispatch port is bound for the selected route.',
        'Bind the selected route dispatch port in the host launcher, then re-run service-readiness.',
      );
    }
    try {
      await context.dispatchProvider();
      return {
        state: 'ready',
        artifact: `${selection.route.routeId} dispatch port answered`,
      };
    } catch (error) {
      return blocked(
        'ROUTE_DISPATCH_FAILED',
        `The selected route dispatch port failed (${error instanceof Error ? error.name : 'unknown error'}).`,
        'Check the selected route endpoint and credential presence, then re-run an online readiness check.',
      );
    }
  };
}

/**
 * The worker layer is ready only when the supervisor is running AND the
 * durable budget ledger is readable from the same handle. The poll
 * generation is the supervisor's own observed cycle count.
 */
function workerProbe(
  handle: () => CouncilWorkerHandle | null,
  db: CouncilDatabase,
): ReadinessProbe {
  return () => {
    const supervisor = handle();
    if (!supervisor) {
      return {
        state: 'blocked',
        artifact: null,
        blocker: {
          code: 'WORKER_NOT_STARTED',
          detail: 'No council worker supervisor is running in this process.',
        },
        recovery:
          'Start the durable council workers (startCouncilWorkers) in the supervised service process and re-check readiness.',
      };
    }
    if (!supervisor.running) {
      return {
        state: 'blocked',
        artifact: 'supervisor stopped',
        blocker: {
          code: 'WORKER_NOT_RUNNING',
          detail: 'The council worker supervisor exists but is not running.',
        },
        recovery:
          'Restart the supervised worker and re-check readiness; durably admitted work stays in the store.',
      };
    }
    try {
      const row = db.read((reader) =>
        reader
          .prepare(
            `SELECT COUNT(*) AS reservations FROM council_budget_reservations`,
          )
          .get(),
      ) as { reservations: number } | undefined;
      return {
        state: 'ready',
        artifact: `worker supervisor ${supervisor.supervisor_id} running; poll generation ${supervisor.cycles_started}; durable ledger readable (${row?.reservations ?? 0} reservation row(s))`,
      };
    } catch (error) {
      return blocked(
        'WORKER_LEDGER_UNREADABLE',
        `The worker is running but the durable budget ledger could not be read (${error instanceof Error ? error.name : 'unknown error'}).`,
        'Check the council database handle, then re-run service-readiness; the supervisor keeps durable work intact.',
      );
    }
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
 * Open the canonical store over the service data directory and compose the
 * durable backend. The four host bindings the deliberation needs are left
 * null (see the module header); the runner, jobs, ledger, grants and
 * admission are real.
 */
function composeBackend(input: {
  dataDir: string;
  clock: Clock;
  ids: IdSource;
  startWorkers: boolean;
  workerPollIntervalMs?: number;
  workerTimers?: RunnerTimers;
}): CouncilServiceBackend {
  const config = parsePersistenceConfig();
  const installation = resolveStandaloneInstallation(input.dataDir);
  ensureInstallationProfile(input.dataDir, {
    authority_mode: config.authority_mode,
    authority_ref: null,
    installation_id: installation.installation_id,
    recorded_at: input.clock.nowUtc(),
  });

  const databasePath = join(input.dataDir, 'council.db');
  const db = CouncilDatabase.open(databasePath, {
    busyTimeoutMs: config.busy_timeout_ms,
    busyMaxAttempts: config.busy_max_attempts,
    busyBaseDelayMs: config.busy_base_delay_ms,
  });

  try {
    // The canonical schema is additive (IF NOT EXISTS throughout); applying
    // it on open is the restart and self-heal path.
    db.write((handle) => handle.exec(COUNCIL_SCHEMA_SQL));
  } catch (error) {
    db.close();
    throw error;
  }

  const repositories = new CouncilRepositories(db, {
    clock: input.clock,
    ids: input.ids,
    config,
  });
  const workerEnvelope = envelopeFromScope(
    standaloneScope(installation),
    installation.owner_subject,
    'worker',
    'write',
  );
  const deliberation = composeDeliberationService({
    db,
    clock: input.clock,
    ids: input.ids,
    // The service root does not own a material catalog, a trusted
    // principal resolver, a transport resolver or verified route limits.
    // They stay honestly unbound; DeliberationService.readiness() says so.
    catalog: null,
    resolvePrincipal: null,
    resolveTransport: null,
    routeBudget: null,
    workerId: WORKER_ID,
  });

  let workers: CouncilWorkerHandle | null = null;
  try {
    workers = input.startWorkers
      ? startCouncilWorkers({
          runner: deliberation.runner,
          scopes: [{ envelope: workerEnvelope, worker_id: WORKER_ID }],
          supervisor_id: `council-service-${installation.installation_id}`,
          poll_interval_ms: input.workerPollIntervalMs,
          timers: input.workerTimers,
        })
      : null;
  } catch (error) {
    db.close();
    throw error;
  }

  let stopping: Promise<void> | null = null;
  const stop = (): Promise<void> => {
    if (!stopping) {
      stopping = (async () => {
        try {
          if (workers) await stopCouncilWorkers(workers);
        } finally {
          db.close();
        }
      })();
    }
    return stopping;
  };

  return {
    dataDir: input.dataDir,
    databasePath,
    database: db,
    repositories,
    journal: repositories.journal,
    outbox: repositories.outbox,
    deliberation,
    workers,
    stop,
  };
}

/**
 * Build the identity, the durable backend and the front door with the
 * truthful probe set bound. No listener is started here; the database is
 * opened and the workers start (unref'd timers) so readiness observes a
 * live backend.
 */
export function composeCouncilService(
  options: CouncilServiceCompositionOptions = {},
): CouncilServiceComposition {
  const nowUtc = options.nowUtc ?? (() => new Date().toISOString());
  const clock: Clock = { nowUtc };
  const ids: IdSource = { newId: () => randomUUID() };
  const dataDir = options.dataDir ?? defaultServiceDataDir();
  mkdirSync(dataDir, { recursive: true });

  const backend = composeBackend({
    dataDir,
    clock,
    ids,
    startWorkers: options.startWorkers !== false,
    workerPollIntervalMs: options.workerPollIntervalMs,
    workerTimers: options.workerTimers,
  });

  const identity = buildServiceIdentity({
    tenant_id: options.tenantId ?? 'operator',
    company_id: options.companyId ?? 'blackceo',
    data_dir: dataDir,
    started_at: options.startedAt ?? nowUtc(),
  });

  let doorRef: CouncilFrontDoor | null = null;
  const origin = (): string | null => doorRef?.getOrigin() ?? null;

  const routeOptions = {
    routeId: options.routeId,
    routeHomeDir: options.routeHomeDir,
    routeEnv: options.routeEnv,
    providerDispatch: options.providerDispatch,
  };

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
      store: storeProbe(backend.database),
      route: routeProbe(routeOptions),
      routeCallable: routeCallableProbe(routeOptions),
      worker: workerProbe(() => backend.workers, backend.database),
      providerDispatch: options.providerDispatch,
    },
  });
  doorRef = door;

  return {
    identity,
    door,
    backend,
    stop: backend.stop,
  };
}

/**
 * Compose, start, and keep the front door alive until SIGTERM/SIGINT.
 * Signal handlers can be disabled for tests and embedded callers.
 */
export async function startCouncilService(
  options: CouncilServiceCompositionOptions & { handleSignals?: boolean } = {},
): Promise<StartedCouncilService> {
  const composition = composeCouncilService(options);
  let outcome: StartOutcome;
  try {
    outcome = await composition.door.start();
  } catch (error) {
    await composition.stop();
    throw error;
  }

  if (outcome.outcome === 'refused') {
    // A refused listener leaves no running service behind: stop the
    // workers and close the handle before returning the typed refusal.
    await composition.stop();
  }

  let stopping: Promise<void> | null = null;
  const stop = (): Promise<void> => {
    if (!stopping) {
      stopping = (async () => {
        composition.door.drain();
        await composition.door.stop();
        await composition.stop();
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
