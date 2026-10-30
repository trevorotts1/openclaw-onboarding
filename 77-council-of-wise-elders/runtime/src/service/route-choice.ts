/**
 * Per-session model route choice (W28, Decision 1).
 *
 * The route is resolved for each session, never once for the service.
 * The client's explicit route_id / model always wins. Otherwise the
 * convening harness picks the default:
 *
 *   claude-nine -> claude-nine-configured, no --model (the launcher's own
 *                  configured default applies)
 *   claude-code -> claude-configured, model 'sonnet'
 *   deepseek    -> deepseek-configured, the newest DeepSeek Flash id read
 *                  from the provider's live GET {baseUrl}/models at run
 *                  time. The configuration's pinned id is never used.
 *
 * Never guess: no route_id and no known harness is a typed refusal, and a
 * failed or Flash-less model list never falls back to the configured id.
 * Several composable routes existing at once is the normal case here.
 *
 * Transport construction lives here too, resolved from snapshot.routeId on
 * every call (moved from service/composition.ts, same behaviour), so each
 * session's pinned snapshot gets the transport for its own route.
 *
 * Secrets: the model-list request carries the credential in the
 * Authorization header only. No error text built here includes it.
 */

import type { spawn } from 'node:child_process';
import { SubprocessHostCallTransport } from '../cli/host-call-transport.js';
import type { ModelTransport } from '../cli/host-ports.js';
import {
  RouteDiscoveryError,
  discoverConfiguredRoutes,
  resolveDiscoveredCredential,
  resolveRouteForDispatch,
  routeUsableWithModel,
  type DiscoveredRoute,
} from '../cli/route-discovery.js';
import type { ModelPolicy } from '../contracts/index.js';
import type { PinnedRouteSnapshot, RouteTrustedScope } from '../budgets/index.js';
import { CompatibleHttpTransport, type CompatibleTransportBinding } from '../providers/compatible.js';
import { createOllamaTransport } from '../providers/ollama.js';
import type { CouncilRouteSelection } from '../providers/selection.js';

export type ConveningHarness = 'claude-nine' | 'claude-code' | 'deepseek' | 'unknown';

export const HARNESS_DEFAULTS: Readonly<
  Record<
    'claude-nine' | 'claude-code' | 'deepseek',
    { route_id: string; model: 'harness_default' | 'sonnet' | 'latest_deepseek_flash' }
  >
> = Object.freeze({
  'claude-nine': { route_id: 'claude-nine-configured', model: 'harness_default' },
  'claude-code': { route_id: 'claude-configured', model: 'sonnet' },
  deepseek: { route_id: 'deepseek-configured', model: 'latest_deepseek_flash' },
});

export interface RouteChoiceRequest {
  route_id?: string | null;
  model?: string | null;
  harness?: ConveningHarness | null;
}

export interface RouteChoiceOptions {
  homeDir?: string;
  env?: NodeJS.ProcessEnv;
  fetchImpl?: typeof fetch;
  scope: RouteTrustedScope;
  nowUtc: () => string;
}

export interface ResolvedSessionRoute {
  route: DiscoveredRoute;
  /** requestedModelOrAlias is the wire model, or null for the harness default. */
  snapshot: PinnedRouteSnapshot;
  model_policy: ModelPolicy;
  model_label: string;
  selection_source: 'explicit' | 'client_default';
  harness: ConveningHarness | null;
}

export type RouteChoiceErrorCode =
  | 'ROUTE_CHOICE_REQUIRED'
  | 'ROUTE_NOT_CONFIGURED'
  | 'ROUTE_NOT_COMPOSABLE'
  | 'ROUTE_MODEL_LIST_UNAVAILABLE'
  | 'ROUTE_LATEST_FLASH_NOT_FOUND'
  | 'ROUTE_MODEL_NOT_OFFERED';

export class RouteChoiceError extends Error {
  readonly code: RouteChoiceErrorCode;
  readonly recovery: string;
  constructor(code: RouteChoiceErrorCode, message: string, recovery: string) {
    super(`${code}: ${message}`);
    this.name = 'RouteChoiceError';
    this.code = code;
    this.recovery = recovery;
  }
}

const MODEL_LIST_TIMEOUT_MS = 15_000;

// ---------------------------------------------------------------------------
// Latest Flash selection
// ---------------------------------------------------------------------------

function parseVersion(id: string): number[] {
  const match = /(?:^|[^a-z0-9])v(\d+(?:\.\d+)*)/i.exec(id);
  return match ? match[1].split('.').map(Number) : [];
}

/** Trailing date or build suffix after the Flash marker, as a number. */
function parseBuild(id: string): number {
  const tail = id.slice(id.toLowerCase().indexOf('flash') + 5);
  const runs = tail.match(/\d{4,}/g);
  return runs ? Number(runs[runs.length - 1]) : 0;
}

function compareVersions(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/**
 * The newest Flash id in a provider model list: highest parsed version
 * (v4.1 > v4 > v3.2), then the latest date/build suffix. Null when the
 * list holds no Flash id.
 */
export function pickLatestFlash(modelIds: readonly string[]): string | null {
  const flashes = modelIds.filter((id) => typeof id === 'string' && /flash/i.test(id));
  if (flashes.length === 0) return null;
  flashes.sort((a, b) => {
    const byVersion = compareVersions(parseVersion(b), parseVersion(a));
    if (byVersion !== 0) return byVersion;
    const byBuild = parseBuild(b) - parseBuild(a);
    if (byBuild !== 0) return byBuild;
    return a < b ? -1 : a > b ? 1 : 0;
  });
  return flashes[0];
}

// ---------------------------------------------------------------------------
// Route options
// ---------------------------------------------------------------------------

export interface RouteOption {
  route_id: string;
  provider_slug: string;
  kind: string;
  composable: boolean;
  failure_code: string | null;
  default_for: ConveningHarness[];
  /**
   * True when the route's only blocker is the choice of model: pass one
   * of `model_candidates` and it is usable. The council never picks it.
   */
  usable_with_model: boolean;
  /** Every configured candidate model id on this route. */
  model_candidates: string[];
}

export function listRouteOptions(
  opts: Omit<RouteChoiceOptions, 'scope' | 'nowUtc'>,
): RouteOption[] {
  const routes = discoverConfiguredRoutes({ homeDir: opts.homeDir, env: opts.env });
  const harnesses = Object.keys(HARNESS_DEFAULTS) as Array<keyof typeof HARNESS_DEFAULTS>;
  return routes.map((route) => ({
    route_id: route.routeId,
    provider_slug: route.providerSlug,
    kind: route.kind,
    composable: route.composable,
    failure_code: route.failure?.code ?? null,
    default_for: harnesses.filter((h) => HARNESS_DEFAULTS[h].route_id === route.routeId),
    usable_with_model: routeUsableWithModel(route),
    model_candidates: [...(route.compatible?.modelCandidates ?? [])],
  }));
}

// ---------------------------------------------------------------------------
// Resolution
// ---------------------------------------------------------------------------

function clean(value: string | null | undefined): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function resolveRoute(
  routeId: string,
  opts: { homeDir?: string; env?: NodeJS.ProcessEnv },
  explicitModel: string | null = null,
): DiscoveredRoute {
  try {
    return resolveRouteForDispatch(routeId, { homeDir: opts.homeDir, env: opts.env }, explicitModel)
      .route;
  } catch (error) {
    const code = error instanceof RouteDiscoveryError ? error.code : null;
    if (code === 'ROUTE_ID_UNKNOWN' || code === 'ROUTE_HOST_CONFIG_MISSING') {
      throw new RouteChoiceError(
        'ROUTE_NOT_CONFIGURED',
        `Route ${routeId} is not configured on this host.`,
        'Pick one of the routes from the routes listing, or configure this route (provider account, model and credential presence).',
      );
    }
    if (code === 'ROUTE_MODEL_AMBIGUOUS') {
      const route = discoverConfiguredRoutes({ homeDir: opts.homeDir, env: opts.env }).find(
        (candidate) => candidate.routeId === routeId,
      );
      const candidates = route?.compatible?.modelCandidates ?? [];
      throw new RouteChoiceError(
        'ROUTE_NOT_COMPOSABLE',
        `Route ${routeId} allows ${candidates.length} models (${candidates.join(', ')}) and names no single default, so it needs one named.`,
        'Pass the model to use (one of the candidate models listed above); the council never picks a model itself.',
      );
    }
    throw new RouteChoiceError(
      'ROUTE_NOT_COMPOSABLE',
      `Route ${routeId} is configured but cannot be used now${code ? ` (${code})` : ''}.`,
      'Fix the named route blocker (executable, endpoint, model or credential presence) or pick a different route.',
    );
  }
}

/** GET {baseUrl}/models. Throws ROUTE_MODEL_LIST_UNAVAILABLE on any failure. */
async function fetchModelIds(
  route: DiscoveredRoute,
  opts: { env?: NodeJS.ProcessEnv; fetchImpl?: typeof fetch },
): Promise<string[]> {
  const compatible = route.compatible;
  const unavailable = (why: string): RouteChoiceError =>
    new RouteChoiceError(
      'ROUTE_MODEL_LIST_UNAVAILABLE',
      `The live model list for route ${route.routeId} could not be read (${why}).`,
      'Check the provider endpoint and credential presence, then convene again, or name the model yourself.',
    );
  if (!compatible) throw unavailable('not an HTTP provider route');
  const headers: Record<string, string> = { accept: 'application/json' };
  const credential = resolveDiscoveredCredential(route, opts.env ?? process.env);
  if (credential) headers.authorization = `Bearer ${credential}`;
  const doFetch = opts.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await doFetch(`${compatible.baseUrl.replace(/\/+$/, '')}/models`, {
      method: 'GET',
      headers,
      signal: AbortSignal.timeout(MODEL_LIST_TIMEOUT_MS),
    });
  } catch (error) {
    throw unavailable(error instanceof Error ? error.name : 'request failed');
  }
  if (!response.ok) throw unavailable(`HTTP ${response.status}`);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw unavailable('response was not JSON');
  }
  const record = (body ?? {}) as { data?: unknown; models?: unknown };
  const list = Array.isArray(record.data) ? record.data : Array.isArray(record.models) ? record.models : null;
  if (!list) throw unavailable('unrecognised response shape');
  const ids: string[] = [];
  for (const entry of list) {
    const id = typeof entry === 'string' ? entry : (entry as { id?: unknown } | null)?.id;
    if (typeof id === 'string' && id.length > 0) ids.push(id);
  }
  return ids;
}

function buildSnapshot(
  route: DiscoveredRoute,
  wireModel: string | null,
  source: 'explicit' | 'client_default',
  opts: RouteChoiceOptions,
): PinnedRouteSnapshot {
  const compatible = route.compatible;
  const configured = compatible?.capabilitySnapshot ?? {
    contextWindowTokens: null,
    maxOutputTokens: null,
    capabilities: ['text'],
    supportedReasoningLevels: null,
  };
  // Limits belong to the configuration's own model. A different model
  // (for example the latest Flash) has no verified limits here: unknown.
  const sameModel = compatible ? wireModel === compatible.modelId : true;
  const capabilitySnapshot = sameModel
    ? { ...configured, capabilities: [...configured.capabilities] }
    : {
        contextWindowTokens: null,
        maxOutputTokens: null,
        capabilities: [...configured.capabilities],
        supportedReasoningLevels: null,
      };
  const credential = compatible
    ? {
        state: compatible.credential.state,
        envVar: compatible.credential.envVar,
        source: compatible.credential.source,
        checked: [...compatible.credential.checked],
      }
    : { state: 'not_required', envVar: null, source: null, checked: [] as string[] };
  return {
    schema: 'wise-elders.route-selection/v1',
    selectionSource: source,
    routeId: route.routeId,
    routeRevision: 1,
    routeKind: 'fixed_model',
    providerSlug: route.providerSlug,
    requestedRoute: route.routeId,
    requestedModelOrAlias: wireModel,
    combinationMembers: null,
    reasoning: { requested: null, applied: null, supported: null, limitation: null },
    fallbackPolicy: 'none',
    providerAccountRef: null,
    capabilitySnapshot,
    credential,
    identityLevel: 'configured',
    scope: { ...opts.scope },
    createdAt: opts.nowUtc(),
  };
}

export async function resolveSessionRoute(
  req: RouteChoiceRequest,
  opts: RouteChoiceOptions,
): Promise<ResolvedSessionRoute> {
  const explicitRoute = clean(req.route_id);
  const explicitModel = clean(req.model);
  const harness: ConveningHarness | null = req.harness ?? null;
  const harnessDefault =
    harness === 'claude-nine' || harness === 'claude-code' || harness === 'deepseek'
      ? HARNESS_DEFAULTS[harness]
      : null;

  const routeId = explicitRoute ?? harnessDefault?.route_id ?? null;
  if (routeId === null) {
    throw new RouteChoiceError(
      'ROUTE_CHOICE_REQUIRED',
      'No route_id was given and the convening harness is not known, so no default route can be chosen.',
      'Ask the client which model route to use (see the routes listing) and pass route_id, or pass the harness (claude-nine, claude-code or deepseek).',
    );
  }
  const source: 'explicit' | 'client_default' =
    explicitRoute || explicitModel ? 'explicit' : 'client_default';

  const route = resolveRoute(routeId, opts, explicitModel);
  // The default model for a route comes from the table row that names it.
  const defaultKind =
    Object.values(HARNESS_DEFAULTS).find((d) => d.route_id === route.routeId)?.model ?? null;

  let wireModel: string | null;
  if (explicitModel) {
    wireModel = explicitModel;
    if (route.compatible && !route.compatible.modelCandidates.includes(explicitModel)) {
      let offered: string[] = [];
      try {
        offered = await fetchModelIds(route, opts);
      } catch {
        offered = [];
      }
      if (!offered.includes(explicitModel)) {
        throw new RouteChoiceError(
          'ROUTE_MODEL_NOT_OFFERED',
          `Model ${explicitModel} is in neither the provider model list nor the configured models of route ${route.routeId}.`,
          'Choose a model the provider offers, or leave the model out to use the default.',
        );
      }
    }
  } else if (defaultKind === 'sonnet') {
    wireModel = 'sonnet';
  } else if (defaultKind === 'latest_deepseek_flash') {
    const ids = await fetchModelIds(route, opts);
    const latest = pickLatestFlash(ids);
    if (latest === null) {
      throw new RouteChoiceError(
        'ROUTE_LATEST_FLASH_NOT_FOUND',
        `The live model list for route ${route.routeId} holds no Flash model. The configured model id is never used in its place.`,
        'Name the model yourself, or retry when the provider lists a Flash model.',
      );
    }
    wireModel = latest;
  } else if (route.compatible) {
    // Explicit route with no default rule: the configuration's own model.
    if (!route.compatible.modelId) {
      throw new RouteChoiceError(
        'ROUTE_MODEL_NOT_OFFERED',
        `Route ${route.routeId} names no single configured model.`,
        'Pass the model to use on this route.',
      );
    }
    wireModel = route.compatible.modelId;
  } else {
    wireModel = null; // harness default
  }

  const snapshot = buildSnapshot(route, wireModel, source, opts);
  return {
    route,
    snapshot,
    model_policy: {
      selection: source,
      route_id: route.routeId,
      requested_model_id: wireModel,
      reasoning_preference: null,
      fallback_policy: 'none',
    },
    model_label: wireModel ?? `${route.providerSlug} configured default`,
    selection_source: source,
    harness,
  };
}

// ---------------------------------------------------------------------------
// Transport (moved from service/composition.ts; resolved per snapshot)
// ---------------------------------------------------------------------------

/**
 * The pinned budget snapshot and the transport selection are the same
 * frozen CWE-008 selection document. Copy the published fields explicitly
 * so a shape drift is a compile error, never a cast that hides it.
 */
function selectionFromSnapshot(snapshot: PinnedRouteSnapshot): CouncilRouteSelection {
  const credentialState = snapshot.credential.state;
  if (
    credentialState !== 'present' &&
    credentialState !== 'absent' &&
    credentialState !== 'not_required'
  ) {
    throw new Error(
      `Route snapshot credential state ${JSON.stringify(credentialState)} is not a canonical presence state; no transport is composed.`,
    );
  }
  const credentialSource = snapshot.credential.source;
  if (
    credentialSource !== null &&
    credentialSource !== 'process.env' &&
    credentialSource !== 'env_file' &&
    credentialSource !== 'openclaw_json' &&
    credentialSource !== 'openclaw_auth_store'
  ) {
    throw new Error(
      `Route snapshot credential source ${JSON.stringify(credentialSource)} is not a canonical source name; no transport is composed.`,
    );
  }
  return {
    schema: snapshot.schema,
    selectionSource: snapshot.selectionSource,
    routeId: snapshot.routeId,
    routeRevision: snapshot.routeRevision,
    routeKind: snapshot.routeKind,
    providerSlug: snapshot.providerSlug,
    requestedRoute: snapshot.requestedRoute,
    requestedModelOrAlias: snapshot.requestedModelOrAlias,
    combinationMembers: snapshot.combinationMembers,
    reasoning: snapshot.reasoning,
    fallbackPolicy: snapshot.fallbackPolicy,
    providerAccountRef: snapshot.providerAccountRef,
    capabilitySnapshot: snapshot.capabilitySnapshot,
    credential: {
      state: credentialState,
      envVar: snapshot.credential.envVar,
      source: credentialSource,
      checked: snapshot.credential.checked,
    },
    identityLevel: snapshot.identityLevel,
    scope: snapshot.scope,
    createdAt: snapshot.createdAt,
  };
}

/**
 * Compose the real transport for the route a snapshot pins, at flight
 * time. A harness route runs its own executable and passes --model when
 * the snapshot pins one; a compatible route uses the configured endpoint
 * and resolves the credential value only when a call is made. A route that
 * no longer resolves gives null (an honest pre-dispatch refusal upstream).
 */
export function transportForSnapshot(
  snapshot: PinnedRouteSnapshot,
  opts: {
    homeDir?: string;
    env?: NodeJS.ProcessEnv;
    spawnImpl?: typeof spawn;
    /**
     * CTR-134: one-shot preparation. The same configured adapter, but it may
     * make exactly one attempt and never retries, so the preparatory request
     * can never spend a second provider request or fall through to a retry.
     */
    singleAttempt?: boolean;
  },
): ModelTransport | null {
  let route: DiscoveredRoute;
  try {
    route = resolveRouteForDispatch(
      snapshot.routeId,
      { homeDir: opts.homeDir, env: opts.env },
      // The snapshot's pinned model is the caller's explicit choice on a
      // route whose only otherwise-blocker is ROUTE_MODEL_AMBIGUOUS.
      snapshot.requestedModelOrAlias,
    ).route;
  } catch (error) {
    if (error instanceof RouteDiscoveryError) return null;
    throw error;
  }
  if (route.harness?.executable) {
    return new SubprocessHostCallTransport({
      executable: route.harness.executable,
      // Plain Claude Code keys its macOS Keychain login on whether
      // CLAUDE_CONFIG_DIR is set, so set it only when it is not the default.
      configDir:
        route.harness.configRootName === '.claude' && !(opts.env ?? process.env).CLAUDE_CONFIG_DIR
          ? undefined
          : route.harness.configDir,
      model: snapshot.requestedModelOrAlias,
      spawnImpl: opts.spawnImpl,
      ...(opts.singleAttempt ? { maxAttempts: 1 } : {}),
    });
  }
  if (route.compatible) {
    const binding: CompatibleTransportBinding = {
      selection: selectionFromSnapshot(snapshot),
      baseUrl: route.compatible.baseUrl,
      credentialResolver: async () =>
        resolveDiscoveredCredential(route, opts.env ?? process.env),
      // One attempt only: the engine retry mode performs a single dispatch
      // and reports a transient failure instead of re-sending.
      ...(opts.singleAttempt ? { retryMode: 'none' as const } : {}),
    };
    // An Ollama route composes through the existing OpenAI-compatible
    // Ollama profile: the configured /v1 surface, the local daemon with
    // no credential, Ollama Cloud with its configured key reference.
    return route.compatible.apiFamily === 'ollama_chat'
      ? createOllamaTransport(binding)
      : new CompatibleHttpTransport(binding);
  }
  return null;
}
