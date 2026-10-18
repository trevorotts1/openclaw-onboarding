/**
 * Layered service readiness (WER-021).
 *
 * Each layer is observed INDEPENDENTLY: one failing probe never rewrites
 * another layer's result, and nothing combines handlers, a model listing,
 * a zero exit code, a scheduler or a queue admission into `usable`.
 *
 * Offline readiness makes ZERO provider calls. Probes receive a guarded
 * dispatch context: calling it while offline is refused, counted, and
 * turns that layer blocked. The evaluator itself never calls the provider
 * dispatch port.
 *
 * Deferred and never claimed here: an installed service, a real browser
 * launch, a live session, host registration, and a completed live run.
 */

import type { RouteDiscoveryInfo } from '../cli/route-discovery.js';
import type { CouncilWorkerHandle } from '../queue/index.js';
import {
  READINESS_LAYER_IDS,
  SERVICE_READINESS_SCHEMA,
  type ReadinessLayerId,
  type ReadinessLayerResult,
  type ReadinessState,
  type ServiceBlocker,
  type ServiceReadiness,
} from './types.js';

export interface ReadinessObservation {
  state: ReadinessState;
  artifact?: string | null;
  blocker?: ServiceBlocker | null;
  recovery?: string | null;
}

export interface ReadinessProbeContext {
  /** True when this evaluation is offline (the default). */
  offline: boolean;
  /**
   * Guarded provider dispatch. Offline calls are refused and counted;
   * there is no other provider route inside readiness.
   */
  dispatchProvider: () => Promise<unknown>;
}

export type ReadinessProbe = (
  context: ReadinessProbeContext,
) => ReadinessObservation | Promise<ReadinessObservation>;

export interface ServiceReadinessDeps {
  nowUtc?: () => string;
  origin?: string | null;
  discovery?: ReadinessProbe;
  executable?: ReadinessProbe;
  store?: ReadinessProbe;
  /** Route configured (host/config/credential presence), no provider call. */
  route?: ReadinessProbe;
  /**
   * Route callable. Invoked ONLY when the evaluation is not offline; it
   * is the sole place a route probe may reach the guarded dispatch.
   */
  routeCallable?: ReadinessProbe;
  packs?: ReadinessProbe;
  worker?: ReadinessProbe;
  ui?: ReadinessProbe;
  /** The provider dispatch port itself, guarded by the evaluator. */
  providerDispatch?: () => unknown | Promise<unknown>;
}

export interface ReadinessOptions {
  /** Default true. Offline readiness makes zero provider calls. */
  offline?: boolean;
}

const PROBE_BY_LAYER: Readonly<
  Record<ReadinessLayerId, keyof ServiceReadinessDeps>
> = {
  discovery: 'discovery',
  executable: 'executable',
  store: 'store',
  route: 'route',
  packs: 'packs',
  worker: 'worker',
  ui: 'ui',
};

function unboundObservation(layer: ReadinessLayerId): ReadinessObservation {
  if (layer === 'ui') {
    return {
      state: 'blocked',
      artifact: null,
      blocker: {
        code: 'UI_NOT_BUNDLED',
        detail:
          'No shared Council UI build is packaged by this service slice; the front door exposes the API/event contract only.',
      },
      recovery:
        'Package the accepted shared Council UI build and bind its asset manifest (WER-021 full packaging), then re-run service-readiness.',
    };
  }
  return {
    state: 'unknown',
    artifact: null,
    blocker: {
      code: 'READINESS_PROBE_NOT_BOUND',
      detail: `No ${layer} probe is bound for this composition.`,
    },
    recovery: `Bind the ${layer} probe in the composition root; this slice does not fabricate an observation.`,
  };
}

function normalizeObservation(
  layer: ReadinessLayerId,
  raw: ReadinessObservation,
): ReadinessObservation {
  if (raw.state === 'blocked') {
    return {
      state: 'blocked',
      artifact: raw.artifact ?? null,
      blocker: raw.blocker ?? {
        code: 'READINESS_BLOCKED',
        detail: `${layer} reported blocked without a named blocker.`,
      },
      recovery:
        raw.recovery ?? 'Resolve the named blocker and re-run service-readiness.',
    };
  }
  return {
    state: raw.state,
    artifact: raw.artifact ?? null,
    blocker: raw.blocker ?? null,
    recovery: raw.recovery ?? null,
  };
}

/** Route readiness derived from the existing route-discovery output. */
export function routeObservationFromDiscovery(
  routes: readonly RouteDiscoveryInfo[] | null | undefined,
): ReadinessObservation {
  if (!routes || routes.length === 0) {
    return {
      state: 'blocked',
      artifact: null,
      blocker: {
        code: 'ROUTE_NOT_CONFIGURED',
        detail: 'Route discovery returned no configured route on this host.',
      },
      recovery:
        'Configure a supported client route (provider account + model) and re-run route discovery; no provider call is made by readiness.',
    };
  }
  const composed = routes.filter((route) => route.composed);
  if (composed.length === 0) {
    const reasons = routes
      .map(
        (route) =>
          `${route.route_id}${route.not_composed_reason ? `: ${route.not_composed_reason}` : ''}`,
      )
      .join('; ');
    return {
      state: 'blocked',
      artifact: `${routes.length} configured route(s), 0 composable`,
      blocker: {
        code: 'ROUTE_NOT_COMPOSABLE',
        detail: reasons,
      },
      recovery:
        'Fix the named route blocker (executable, endpoint, model or credential presence) and re-run route discovery.',
    };
  }
  return {
    state: 'ready',
    artifact: `${composed.length}/${routes.length} route(s) composable: ${composed
      .map((route) => route.route_id)
      .join(', ')}`,
  };
}

/** Worker readiness derived from the existing supervised-worker handle. */
export function workerObservationFromHandle(
  handle: Pick<CouncilWorkerHandle, 'running'> | null | undefined,
): ReadinessObservation {
  if (!handle) {
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
  if (!handle.running) {
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
  return { state: 'ready', artifact: 'worker supervisor running' };
}

/**
 * Evaluate every layer independently. A probe that throws marks only its
 * own layer blocked with the observed error; no layer is retried through
 * another layer's path.
 */
export async function evaluateServiceReadiness(
  deps: ServiceReadinessDeps = {},
  options: ReadinessOptions = {},
): Promise<ServiceReadiness> {
  const offline = options.offline ?? true;
  const nowUtc = deps.nowUtc ?? (() => new Date().toISOString());
  let providerCalls = 0;

  const dispatchProvider = async (): Promise<unknown> => {
    providerCalls += 1;
    if (offline || !deps.providerDispatch) {
      throw new Error(
        offline
          ? 'Provider dispatch is refused during offline readiness.'
          : 'No provider dispatch port is bound for this composition.',
      );
    }
    return deps.providerDispatch();
  };
  const context: ReadinessProbeContext = { offline, dispatchProvider };

  const layers: ReadinessLayerResult[] = [];
  for (const layer of READINESS_LAYER_IDS) {
    const observedAt = nowUtc();
    const probe = deps[PROBE_BY_LAYER[layer]] as ReadinessProbe | undefined;
    let observation: ReadinessObservation;
    if (!probe) {
      observation = unboundObservation(layer);
    } else {
      try {
        observation = normalizeObservation(layer, await probe(context));
      } catch (error) {
        observation = {
          state: 'blocked',
          artifact: null,
          blocker: {
            code: 'READINESS_PROBE_FAILED',
            detail:
              error instanceof Error ? error.message : String(error),
          },
          recovery:
            'Fix the named probe failure and re-run service-readiness; the other layers remain independently observed.',
        };
      }
    }

    // Route callable is a separate observation folded into the route
    // layer, and is ONLY reached when this evaluation is online.
    if (layer === 'route' && !offline && deps.routeCallable) {
      try {
        const callable = normalizeObservation(
          'route',
          await deps.routeCallable(context),
        );
        if (callable.state !== 'ready' && observation.state === 'ready') {
          observation = callable;
        } else if (observation.state === 'ready' && callable.artifact) {
          observation = {
            ...observation,
            artifact: `${observation.artifact}; ${callable.artifact}`,
          };
        }
      } catch (error) {
        observation = {
          state: 'blocked',
          artifact: observation.artifact ?? null,
          blocker: {
            code: 'ROUTE_CALLABLE_PROBE_FAILED',
            detail: error instanceof Error ? error.message : String(error),
          },
          recovery:
            'Fix the named route-callable failure and re-run readiness; no provider call is retried offline.',
        };
      }
    }

    observation = normalizeObservation(layer, observation);
    layers.push({
      layer,
      state: observation.state,
      observed_at: observedAt,
      artifact: observation.artifact ?? null,
      blocker: observation.blocker ?? null,
      recovery: observation.recovery ?? null,
      offline,
    });
  }

  const blockedLayers = layers
    .filter((layer) => layer.state === 'blocked')
    .map((layer) => layer.layer);

  return {
    schema_version: SERVICE_READINESS_SCHEMA,
    composition: 'standalone',
    origin: deps.origin ?? null,
    observed_at: nowUtc(),
    layers,
    blocked_layers: blockedLayers,
    usable: layers.every((layer) => layer.state === 'ready'),
    provider_calls: providerCalls,
  };
}
