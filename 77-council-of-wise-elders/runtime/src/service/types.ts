/**
 * Standalone Council front-door service contract (WER-021 dependency-ready
 * slice).
 *
 * One same-origin local service owns the API/event surface AROUND the
 * canonical durable owner. It is NOT a second engine, scheduler, budget
 * ledger, event history or identity database: admissions are forwarded to
 * the owning authority through an injected sink, and a managed session is
 * LINKED to its owning Command Center URL rather than duplicated locally.
 *
 * This slice emits contracts, commands and artifacts only. Registering a
 * system service, loading a launchd unit, installing a UI build or binding
 * a remote origin is deferred (host authority, WER-021 full packaging /
 * WER-023 remote access) and is never claimed here.
 */

/** Identity document schema served at /api/council/service/identity. */
export const SERVICE_IDENTITY_SCHEMA = 'wise-elders.service-identity/v1';
/** Readiness receipt schema. */
export const SERVICE_READINESS_SCHEMA = 'wise-elders.service-readiness/v1';
/** Front-door API version; part of identity matching. */
export const SERVICE_API_VERSION = 'v1';

/** Default loopback candidates, tried in order. Port 0 is allowed in tests. */
export const DEFAULT_SERVICE_PORTS: readonly number[] = [8787, 8788, 8789];
/** Default bind host. Remote exposure belongs to WER-023, not here. */
export const DEFAULT_SERVICE_HOST = '127.0.0.1';

/**
 * The independent readiness layers the plan names. Each layer is observed
 * and reported separately: a registered handler, a model listing, a zero
 * exit code, an outbox scheduler or a queue admission is never combined
 * into `usable`.
 */
export const READINESS_LAYER_IDS = [
  'discovery',
  'executable',
  'store',
  'route',
  'packs',
  'worker',
  'ui',
] as const;

export type ReadinessLayerId = (typeof READINESS_LAYER_IDS)[number];

/**
 * `ready`    observed and satisfied.
 * `blocked`  observed and unsatisfied; a blocker and a recovery are named.
 * `unknown`  not observed (or the probe could not observe it).
 * `not_checked` deliberately skipped for this composition.
 */
export type ReadinessState = 'ready' | 'blocked' | 'unknown' | 'not_checked';

export interface ServiceBlocker {
  code: string;
  detail: string;
}

/** A refused start always names a concrete recovery as well. */
export interface ServiceStartBlocker extends ServiceBlocker {
  recovery: string;
}

/** One layer's independent result. */
export interface ReadinessLayerResult {
  layer: ReadinessLayerId;
  state: ReadinessState;
  /** Observation time from the injected clock. */
  observed_at: string;
  /** Observed artifact identity (path, hash, version, route id), never a secret. */
  artifact: string | null;
  blocker: ServiceBlocker | null;
  /** Concrete recovery action; required whenever state is `blocked`. */
  recovery: string | null;
  /** True when this layer was evaluated without any provider call. */
  offline: boolean;
}

export interface ServiceReadiness {
  schema_version: typeof SERVICE_READINESS_SCHEMA;
  composition: 'standalone';
  /** Verified local origin when the service is bound; null otherwise. */
  origin: string | null;
  observed_at: string;
  layers: ReadinessLayerResult[];
  /** Layers whose state makes the corresponding use unavailable. */
  blocked_layers: ReadinessLayerId[];
  /** True ONLY when every layer is `ready`. Never inferred from a subset. */
  usable: boolean;
  /** Observed provider dispatches during this evaluation. Offline MUST be 0. */
  provider_calls: number;
}

// ---------------------------------------------------------------- identity

/** Owner scope the service answers for. Matching never uses a port alone. */
export interface ServiceOwner {
  tenant_id: string;
  company_id: string;
  /** SHA-256 of the resolved durable data directory (path is not disclosed). */
  data_dir_sha256: string;
}

export interface ServiceIdentity {
  schema_version: typeof SERVICE_IDENTITY_SCHEMA;
  service: 'council-of-wise-elders';
  composition: 'standalone';
  api_version: typeof SERVICE_API_VERSION;
  owner: ServiceOwner;
  /** Observed start time; deliberately EXCLUDED from identity matching. */
  started_at: string;
}

export interface IdentityProbe {
  reachable: boolean;
  /** Parsed identity when the endpoint answered with a valid document. */
  identity: ServiceIdentity | null;
  error: string | null;
  /** Every URL consulted, for negative-result evidence. */
  checked: string[];
}

export type ListenerClassification =
  | 'matching_service'
  | 'unrelated_listener'
  | 'unreachable';

// ---------------------------------------------------------------- sessions

export type SessionAuthority = 'standalone' | 'managed';

/**
 * A session's authority record. One authority per session: a managed
 * session carries the owning Command Center URL and is never started
 * locally; a standalone session lives on this service's origin.
 */
export interface SessionAuthorityRecord {
  session_id: string;
  authority: SessionAuthority;
  /** Required for managed sessions; the owning CC session URL. */
  owning_session_url?: string | null;
}

export type SessionTarget =
  | {
      kind: 'local';
      session_id: string;
      url: string;
      authority: 'standalone';
      launched_locally: true;
    }
  | {
      kind: 'external';
      session_id: string;
      url: string;
      authority: 'managed';
      launched_locally: false;
    }
  | {
      kind: 'blocked';
      session_id: string;
      url: null;
      authority: SessionAuthority | 'unknown';
      launched_locally: false;
      blocker: ServiceBlocker;
      recovery: string;
    };

// -------------------------------------------------------------- admissions

/** One admission intent forwarded to the owning authority. */
export interface AdmissionRequest {
  session_id: string;
  /** Caller idempotency identity; the durable owner owns replay. */
  operation_id: string;
  /** Opaque bounded fields for the sink (grant, route, reservation, ...). */
  payload?: Readonly<Record<string, unknown>>;
}

export type AdmissionRefusalCode =
  | 'ADMISSION_INVALID'
  | 'SERVICE_DRAINING'
  | 'SERVICE_NOT_ACTIVE'
  | 'ADMISSION_SINK_UNBOUND'
  | 'ADMISSION_SINK_FAILED';

export type AdmissionDecision =
  | { accepted: true; fenced: false; receipt: unknown }
  | {
      accepted: false;
      fenced: boolean;
      code: AdmissionRefusalCode;
      detail: string;
      recovery: string;
    };

/** The owning authority's admission surface (composition root supplies it). */
export type AdmissionSink = (
  request: AdmissionRequest,
) => unknown | Promise<unknown>;

// ------------------------------------------------------------ start / stop

export type ServiceState =
  | 'idle'
  | 'running'
  | 'reused'
  | 'draining'
  | 'stopped'
  | 'refused';

export interface StartStarted {
  outcome: 'started';
  origin: string;
  port: number;
  identity: ServiceIdentity;
  blockers: [];
}

export interface StartReused {
  outcome: 'reused';
  origin: string;
  port: number;
  /** The identity observed on the existing listener (verified match). */
  identity: ServiceIdentity;
  blockers: [];
}

export interface StartRefused {
  outcome: 'refused';
  origin: null;
  port: null;
  identity: null;
  /** One entry per candidate port that could not be used. */
  blockers: ServiceStartBlocker[];
}

export type StartOutcome = StartStarted | StartReused | StartRefused;

export interface DrainOutcome {
  drained: boolean;
  /** True when new admissions are now refused. */
  fenced: boolean;
  origin: string | null;
  reason:
    | null
    | 'SERVICE_NOT_ACTIVE'
    | 'REUSED_SERVICE_NOT_OWNED';
}

export interface StopOutcome {
  stopped: boolean;
  reason:
    | null
    | 'ALREADY_STOPPED'
    | 'REUSED_SERVICE_NOT_OWNED';
}
