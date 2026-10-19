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
 *   route    ready when at least one discovered route is composable
 *            (W28). The route is chosen PER SESSION by the client (or the
 *            convening harness default), never once for the whole service;
 *            several composable routes are normal. Offline readiness never
 *            calls a provider.
 *   worker   one `startCouncilWorkers` supervisor runs over the durable
 *            runner composed by `composeDeliberationService`, with a live
 *            read of the budget ledger and its poll generation.
 *
 * The deliberation composition's host bindings (W28) are all bound here:
 * the elder-knowledge catalog and seat briefing loader, the standalone
 * trusted principal, a transport resolved per pinned route snapshot, and
 * the approval-gated route budget. The route budget only reports bound
 * once the operator has approved measured numbers, so until then
 * `DeliberationService.readiness()` says "awaiting operator approval"
 * with the proposed numbers and a convene is refused (503
 * COMPOSITION_NOT_READY). Convening is wired through one driver; this
 * module never claims a completed deliberation or a live advisor turn.
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
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { homedir, platform } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  resolveStandaloneInstallation,
  standaloneEnvelope,
  standalonePrincipal,
  standaloneScope,
  type StandaloneInstallation,
} from '../cli/authorization.js';
import type { ModelTransport } from '../cli/host-ports.js';
import {
  discoverConfiguredRoutes,
  type DiscoveredRoute,
  type RouteDiscoveryOptions,
} from '../cli/route-discovery.js';
import type { Clock, IdSource } from '../contracts/index.js';
import { SEAT_IDS } from '../contracts/enums.js';
import type { MaterialCatalog } from '../context/types.js';
import type { StoredSession } from '../cli/host-ports.js';
import {
  COUNCIL_SCHEMA_SQL,
  COUNCIL_TABLES_SECTION_16_2,
} from '../persistence/index.js';
import { parsePersistenceConfig } from '../persistence/config.js';
import { envelopeFromScope, type AuthorizationEnvelope } from '../persistence/envelope.js';
import { ensureInstallationProfile } from '../persistence/profile.js';
import { CouncilRepositories } from '../persistence/repositories.js';
import { CouncilDatabase } from '../persistence/sqlite.js';
import {
  composeDeliberationService,
  type DeliberationCompositionDeps,
  type DeliberationService,
} from '../protocol/composition.js';
import { DurableOperationProducer } from '../queue/producer.js';
import type { RunnerTimers } from '../queue/runner.js';
import {
  startCouncilWorkers,
  stopCouncilWorkers,
  type CouncilWorkerHandle,
} from '../queue/workers.js';
import type { PinnedRouteSnapshot } from '../budgets/index.js';
import {
  loadRouteBudgetApprovals,
  loadRouteBudgetConfig,
  routeBudgetApprovalsPath,
  routeBudgetConfigPath,
  routeBudgetRecovery,
  routeBudgetResolver,
  routeBudgetStatus,
  type RouteBudgetApproval,
  type RouteBudgetConfig,
  type RouteBudgetEntry,
  type RouteBudgetState,
} from '../budgets/route-budget.js';
import { resolveBookToPersonaRoot } from '../sources/persona-root.js';
import { createElderKnowledge, freshFactEvidenceRecord } from '../sources/elder-knowledge.js';
import { createCouncilDriver } from './driver.js';
import {
  HARNESS_DEFAULTS,
  listRouteOptions,
  resolveSessionRoute,
  transportForSnapshot,
} from './route-choice.js';
import { createDurableAdmissionSink } from './durable-admission.js';
import {
  journalEventStreamAdapter,
  repositorySessionReader,
  type CouncilEventStreamAdapter,
  type CouncilSessionReader,
} from './events.js';
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
  CouncilConveningPort,
  CouncilRoutesResponse,
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

type CouncilDriverHandle = ReturnType<typeof createCouncilDriver>;

const DEFAULT_CONVENE_DRAIN_TIMEOUT_MS = 25_000;

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
   * Readiness hint only (for example `<providerId>-configured`). The route
   * is chosen per session by the client or the convening harness default;
   * the service never picks one for everybody, and several composable
   * routes are normal.
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
  /**
   * The CWE-022 material catalog the deliberation context assembler reads
   * evidence from. The standalone service has no installed Skill 22 export
   * by default, so this stays null there and `DeliberationService.readiness()`
   * reports the catalog unbound. A host that has an adapted export supplies
   * the catalog it built; the service never invents evidence.
   */
  materialCatalog?: MaterialCatalog | null;
  /**
   * Skill folder holding `advisors/` and `config/`. Default: the folder
   * containing this runtime. A null/absent root leaves seats with no
   * shipped briefing and the route budget config unresolved (never guessed).
   */
  skillRoot?: string | null;
  /** Route budget config override (tests). Default: the shipped config. */
  routeBudgetConfigPath?: string;
  /**
   * Transport override (tests). When set it replaces the per-snapshot
   * transport resolution; production leaves it unset.
   */
  resolveTransport?: (
    snapshot: PinnedRouteSnapshot,
    session: StoredSession,
  ) => ModelTransport | null | Promise<ModelTransport | null>;
  /**
   * Longest `stop()` waits for in-flight convened sessions before it
   * closes the database. Default 25000 ms.
   */
  conveneDrainTimeoutMs?: number;
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
  /** The canonical durable producer the default admission sink forwards to. */
  producer: DurableOperationProducer;
  /** The convening driver (create, approve on convene, deliberate, journal). */
  convening: CouncilDriverHandle;
  /** Routes and convene, as the front door serves them. */
  conveningPort: CouncilConveningPort;
  /** The owner/write envelope every local composition member acts under. */
  ownerEnvelope: AuthorizationEnvelope;
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

/** Everything the route probes and the budget gate read, in one place. */
interface RouteProbeOptions {
  routeId?: string;
  routeHomeDir?: string;
  routeEnv?: NodeJS.ProcessEnv;
  providerDispatch?: () => unknown | Promise<unknown>;
  budgets: RouteBudgetFiles;
}

interface RouteBudgetFiles {
  configPath: string | null;
  approvalsPath: string;
}

function discoverRoutes(options: RouteProbeOptions): readonly DiscoveredRoute[] {
  const discovery: RouteDiscoveryOptions = {
    homeDir: options.routeHomeDir,
    env: options.routeEnv,
  };
  try {
    return discoverConfiguredRoutes(discovery);
  } catch {
    return [];
  }
}

// ---------------------------------------------------------- route budgets

function formatNumber(value: number | null): string {
  return value === null ? 'unmeasured' : String(value);
}

/** The proposed numbers an operator is asked to approve, in plain words. */
function describeProposed(entry: RouteBudgetEntry): string {
  const model = entry.model === null ? 'any model' : entry.model;
  return `${entry.route_id} (${model}): context ${formatNumber(
    entry.context_window_tokens,
  )} tokens, max output ${formatNumber(entry.max_output_tokens)} tokens, ${formatNumber(
    entry.measured_min_bytes_per_token,
  )} min bytes per token, safety factor ${entry.safety_factor}`;
}

interface RouteBudgetOverview {
  /** True when at least one measured entry carries a matching approval. */
  bound: boolean;
  states: Array<{ route_id: string; model: string | null; state: RouteBudgetState['state'] }>;
  detail: string;
}

/**
 * Re-read the budget config and the operator approvals. Cheap, and it is
 * what lets an approval written while the service runs take effect with
 * no restart. An unreadable config is reported, never papered over.
 */
function readRouteBudgets(files: RouteBudgetFiles): {
  config: RouteBudgetConfig | null;
  approvals: RouteBudgetApproval[];
  error: string | null;
} {
  if (files.configPath === null) {
    return { config: null, approvals: [], error: 'no route budget config path resolved' };
  }
  try {
    return {
      config: loadRouteBudgetConfig(files.configPath),
      approvals: loadRouteBudgetApprovals(files.approvalsPath),
      error: null,
    };
  } catch (error) {
    return {
      config: null,
      approvals: [],
      error: error instanceof Error ? error.name : 'unknown error',
    };
  }
}

function routeBudgetOverview(files: RouteBudgetFiles): RouteBudgetOverview {
  const { config, approvals, error } = readRouteBudgets(files);
  if (!config) {
    return {
      bound: false,
      states: [],
      detail: `route budget config unreadable (${error}); no route can be budgeted until it is repaired`,
    };
  }
  const states: RouteBudgetOverview['states'] = [];
  const approved: string[] = [];
  const awaiting: string[] = [];
  const unmeasured: string[] = [];
  for (const entry of config.entries) {
    const status = routeBudgetStatus(config, approvals, entry.route_id, entry.model);
    states.push({ route_id: entry.route_id, model: entry.model, state: status.state });
    if (status.state === 'approved') {
      approved.push(`${entry.route_id}${entry.model === null ? '' : ` (${entry.model})`}`);
    } else if (status.state === 'awaiting_approval' && status.proposed) {
      awaiting.push(describeProposed(status.proposed));
    } else {
      unmeasured.push(status.proposed ? describeProposed(status.proposed) : entry.route_id);
    }
  }
  const parts: string[] = [];
  if (approved.length > 0) parts.push(`approved: ${approved.join(', ')}`);
  if (awaiting.length > 0) {
    parts.push(`awaiting operator approval, proposed numbers: ${awaiting.join('; ')}`);
  }
  if (unmeasured.length > 0) {
    parts.push(`not yet measured, needs a live measurement then operator approval: ${unmeasured.join('; ')}`);
  }
  if (parts.length === 0) parts.push('no route budget entries are configured');
  return { bound: approved.length > 0, states, detail: parts.join('; ') };
}

/** Per-session guard: the chosen route must carry an approved budget. */
class RouteBudgetNotApprovedError extends Error {
  readonly code = 'COMPOSITION_NOT_READY' as const;
  readonly http_status = 503 as const;
  readonly detail: Record<string, unknown>;
  readonly recovery: string;
  constructor(detail: Record<string, unknown>, recovery: string) {
    super('The chosen route has no operator-approved budget.');
    this.name = 'RouteBudgetNotApprovedError';
    this.detail = detail;
    this.recovery = recovery;
  }
}

function assertRouteBudgetApproved(
  files: RouteBudgetFiles,
  snapshot: PinnedRouteSnapshot,
): void {
  const { config, approvals } = readRouteBudgets(files);
  const status = config
    ? routeBudgetStatus(config, approvals, snapshot.routeId, snapshot.requestedModelOrAlias)
    : null;
  if (status?.state === 'approved') return;
  const state = status?.state ?? 'no_entry';
  const proposed = status && 'proposed' in status ? status.proposed : null;
  throw new RouteBudgetNotApprovedError(
    {
      unbound: 'route_budget',
      route_id: snapshot.routeId,
      model: snapshot.requestedModelOrAlias,
      route_budget_state: state,
      summary:
        state === 'awaiting_approval' && proposed
          ? `awaiting operator approval, proposed numbers: ${describeProposed(proposed)}`
          : state === 'not_measured' && proposed
            ? `not yet measured: ${describeProposed(proposed)}`
            : 'no route budget entry covers this route and model',
    },
    routeBudgetRecovery(snapshot.routeId),
  );
}

/** The `GET /api/council/routes` answer: what the agent offers the client. */
function routesResponse(
  options: RouteProbeOptions,
): CouncilRoutesResponse {
  const routes = listRouteOptions({ homeDir: options.routeHomeDir, env: options.routeEnv });
  const overview = routeBudgetOverview(options.budgets);
  const budgets = [...overview.states];
  for (const route of routes) {
    if (!budgets.some((b) => b.route_id === route.route_id)) {
      budgets.push({ route_id: route.route_id, model: null, state: 'no_entry' });
    }
  }
  return { routes, harness_defaults: HARNESS_DEFAULTS, budgets };
}

function routeProbe(options: RouteProbeOptions): ReadinessProbe {
  return () => {
    const discovered = discoverRoutes(options);
    if (discovered.length === 0) {
      return blocked(
        'ROUTE_NOT_CONFIGURED',
        'Route discovery found no configured client route on this host.',
        'Configure a supported client route (provider account + model) and re-run route discovery; no provider call is made by readiness.',
      );
    }
    const composable = discovered.filter((route) => route.composable);
    if (composable.length === 0) {
      const first = discovered[0];
      return blocked(
        first.failure?.code ?? 'ROUTE_NOT_COMPOSABLE',
        `${discovered.length} configured route(s), 0 composable.`,
        'Fix the named route blocker (executable, endpoint, model or credential presence) and re-run route discovery.',
      );
    }
    const described = composable
      .map((route) => {
        const model = route.compatible?.modelId;
        return `${route.routeId} configured (${route.providerSlug}${model ? ` / ${model}` : ''})`;
      })
      .join(', ');
    const notes = [
      `${composable.length}/${discovered.length} route(s) composable: ${described}`,
      'the route is chosen per session (the client picks, or the convening harness default applies)',
    ];
    if (options.routeId && !composable.some((route) => route.routeId === options.routeId)) {
      notes.push(`hinted route ${options.routeId} is not composable`);
    }
    if (typeof options.providerDispatch === 'function') notes.push('dispatch port bound');
    notes.push(`route budget: ${routeBudgetOverview(options.budgets).detail}`);
    return { state: 'ready', artifact: notes.join('; ') };
  };
}

/**
 * Route callable is evaluated ONLY when readiness is online. It reaches
 * the provider exclusively through the readiness evaluator's guarded
 * dispatch port, so an offline evaluation can never make a provider call.
 */
function routeCallableProbe(options: RouteProbeOptions): ReadinessProbe {
  return async (context) => {
    const composable = discoverRoutes(options).filter((route) => route.composable);
    if (composable.length === 0) {
      return blocked(
        'ROUTE_NOT_CONFIGURED',
        'No composable route resolved.',
        'Configure a client route, then re-run service-readiness.',
      );
    }
    if (typeof options.providerDispatch !== 'function') {
      return blocked(
        'ROUTE_DISPATCH_PORT_UNBOUND',
        'No provider dispatch port is bound for an online route check.',
        'Bind a route dispatch port in the host launcher, then re-run an online readiness check.',
      );
    }
    try {
      await context.dispatchProvider();
      return {
        state: 'ready',
        artifact: `${composable.length} composable route(s); dispatch port answered`,
      };
    } catch (error) {
      return blocked(
        'ROUTE_DISPATCH_FAILED',
        `The route dispatch port failed (${error instanceof Error ? error.name : 'unknown error'}).`,
        'Check the route endpoint and credential presence, then re-run an online readiness check.',
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
 * durable backend: the runner, jobs, ledger, grants and admission, the
 * elder-knowledge catalog and briefing loader, and the convening driver
 * (see the module header).
 */
function composeBackend(input: {
  dataDir: string;
  /** The provisioned standalone installation this backend writes under. */
  installation: StandaloneInstallation;
  clock: Clock;
  ids: IdSource;
  startWorkers: boolean;
  workerPollIntervalMs?: number;
  workerTimers?: RunnerTimers;
  skillRoot: string | null;
  /** Route discovery inputs shared by transports, route choice and probes. */
  route: RouteProbeOptions;
  fetchImpl?: typeof fetch;
  nowUtc: () => string;
  /** Host-supplied catalog; absent means the elder-knowledge catalog. */
  materialCatalog?: MaterialCatalog | null;
  resolveTransport?: CouncilServiceCompositionOptions['resolveTransport'];
  conveneDrainTimeoutMs?: number;
}): CouncilServiceBackend {
  const config = parsePersistenceConfig();
  const installation = input.installation;
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
  const ownerEnvelope = standaloneEnvelope(installation, 'write');
  const scope = standaloneScope(installation);

  // Elder knowledge (W28): live Book-to-Persona first, the shipped briefs as
  // the safety net, per-session web facts in their own labelled section.
  const elderKnowledge = createElderKnowledge({
    skillRoot: input.skillRoot,
    personaRoot: resolveBookToPersonaRoot({
      env: input.route.routeEnv,
      homeDir: input.route.routeHomeDir,
    }),
    scope,
    listSessionEvidence: (session: StoredSession) =>
      repositories.listEvidenceRecords(ownerEnvelope, session.spec.session_id),
  });

  const transportOptions = { homeDir: input.route.routeHomeDir, env: input.route.routeEnv };
  const deliberation = composeDeliberationService({
    db,
    clock: input.clock,
    ids: input.ids,
    catalog: input.materialCatalog ?? elderKnowledge.catalog,
    resolvePrincipal: (_session: StoredSession) => standalonePrincipal(installation),
    // Transport is resolved from the pinned snapshot on every call, so each
    // session runs on the route it chose. The credential is resolved at
    // flight time, never during composition.
    resolveTransport:
      input.resolveTransport ??
      ((snapshot: PinnedRouteSnapshot) => transportForSnapshot(snapshot, transportOptions)),
    // Re-reads the config and the operator approvals on each call: an
    // approval written while the service runs takes effect with no restart.
    routeBudget: input.route.budgets.configPath
      ? routeBudgetResolver({
          configPath: input.route.budgets.configPath,
          approvalsPath: input.route.budgets.approvalsPath,
        })
      : null,
    loadSeatBriefing: elderKnowledge.loadSeatBriefing,
    workerId: WORKER_ID,
  });

  // The resolver is always callable, so the protocol's own readiness would
  // call the budget bound. It is bound only once the operator approved
  // measured numbers; say so, with the proposed numbers, until then.
  const protocolReadiness = deliberation.readiness.bind(deliberation);
  deliberation.readiness = () => {
    const base = protocolReadiness();
    const overview = routeBudgetOverview(input.route.budgets);
    const checks = base.checks.map((check) =>
      check.name === 'route_budget'
        ? {
            name: check.name,
            bound: check.bound && overview.bound,
            detail: overview.bound
              ? `route-budget resolver bound; ${overview.detail}`
              : overview.detail,
          }
        : check,
    );
    return { ready: checks.every((check) => check.bound), checks };
  };

  // The canonical durable producer the front-door admission sink forwards
  // to. It shares the one handle, journal and outbox with the workers.
  const producer = new DurableOperationProducer({
    db,
    repositories,
    jobs: deliberation.jobs,
    outbox: repositories.outbox,
    clock: input.clock,
    ids: input.ids,
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

  const trustedScope = {
    tenantId: installation.tenant_id,
    companyId: installation.company_id,
    installationId: installation.installation_id,
    ownerSubject: installation.owner_subject,
  };
  const convening = createCouncilDriver({
    deliberation,
    envelope: ownerEnvelope,
    scope,
    principal: standalonePrincipal(installation),
    clock: input.clock,
    ids: input.ids,
    resolveRoute: async (request) => {
      const resolved = await resolveSessionRoute(request, {
        homeDir: input.route.routeHomeDir,
        env: input.route.routeEnv,
        fetchImpl: input.fetchImpl,
        scope: trustedScope,
        nowUtc: input.nowUtc,
      });
      // Refuse before a session exists: a route without an approved budget
      // cannot assemble context, and a half-run session would be worse.
      assertRouteBudgetApproved(input.route.budgets, resolved.snapshot);
      return resolved;
    },
    recordFreshFacts: (sessionId, facts) => {
      for (const fact of facts) {
        repositories.addEvidenceRecord(
          ownerEnvelope,
          sessionId,
          freshFactEvidenceRecord(fact, input.ids.newId()),
        );
      }
    },
    auditLogPath: join(input.dataDir, 'convening-audit.jsonl'),
  });
  const conveningPort: CouncilConveningPort = {
    routes: () => routesResponse(input.route),
    convene: (request) => convening.convene(request),
  };

  const drainTimeoutMs = input.conveneDrainTimeoutMs ?? DEFAULT_CONVENE_DRAIN_TIMEOUT_MS;
  let stopping: Promise<void> | null = null;
  const stop = (): Promise<void> => {
    if (!stopping) {
      stopping = (async () => {
        try {
          // Convened sessions deliberate in the background on this handle:
          // give them a bounded chance to settle before it closes.
          let timer: NodeJS.Timeout | undefined;
          try {
            await Promise.race([
              convening.drain(),
              new Promise<void>((resolve) => {
                timer = setTimeout(resolve, drainTimeoutMs);
                timer.unref();
              }),
            ]);
          } finally {
            clearTimeout(timer);
          }
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
    producer,
    convening,
    conveningPort,
    ownerEnvelope,
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

  const installation = resolveStandaloneInstallation(dataDir);
  const skillRoot =
    options.skillRoot === undefined ? resolveSkillRoot() : options.skillRoot;
  const routeOptions: RouteProbeOptions = {
    routeId: options.routeId,
    routeHomeDir: options.routeHomeDir,
    routeEnv: options.routeEnv,
    providerDispatch: options.providerDispatch,
    budgets: {
      configPath:
        options.routeBudgetConfigPath ??
        (skillRoot ? routeBudgetConfigPath(skillRoot, options.routeEnv) : null),
      approvalsPath: routeBudgetApprovalsPath(dataDir),
    },
  };

  const backend = composeBackend({
    dataDir,
    installation,
    clock,
    ids,
    startWorkers: options.startWorkers !== false,
    workerPollIntervalMs: options.workerPollIntervalMs,
    workerTimers: options.workerTimers,
    skillRoot,
    route: routeOptions,
    fetchImpl: options.fetchImpl,
    nowUtc,
    materialCatalog: options.materialCatalog,
    resolveTransport: options.resolveTransport,
    conveneDrainTimeoutMs: options.conveneDrainTimeoutMs,
  });

  const identity = buildServiceIdentity({
    tenant_id: options.tenantId ?? 'operator',
    company_id: options.companyId ?? 'blackceo',
    data_dir: dataDir,
    started_at: options.startedAt ?? nowUtc(),
  });

  let doorRef: CouncilFrontDoor | null = null;
  const origin = (): string | null => doorRef?.getOrigin() ?? null;

  const readEnvelope = standaloneEnvelope(installation, 'read');
  const door = new CouncilFrontDoor({
    identity,
    host: options.host,
    ports: options.ports,
    fetchImpl: options.fetchImpl,
    // ONE composition binds the durable admission, event stream and
    // session reader over the same store/journal/outbox the workers use.
    admissionSink:
      options.admissionSink ??
      createDurableAdmissionSink({
        producer: backend.producer,
        envelope: backend.ownerEnvelope,
      }),
    eventsAdapter: journalEventStreamAdapter({
      journal: backend.journal,
      envelope: readEnvelope,
    }),
    sessionReader: repositorySessionReader({
      repositories: backend.repositories,
      envelope: readEnvelope,
    }),
    convening: backend.conveningPort,
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
