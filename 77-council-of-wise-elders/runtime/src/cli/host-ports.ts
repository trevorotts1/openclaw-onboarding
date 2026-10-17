/**
 * Injected host ports for the portable council core (CWE-004).
 *
 * Directive Section 5.1: the core owns protocol state, schemas, scoring,
 * evidence references, cancellation rules, and output validation. It does
 * NOT own Command Center authentication or a host's global model
 * configuration. Hosts supply every capability through these ports
 * (dependency injection); the portable core never imports Command Center
 * modules. The Command Center adapter supplies its existing DB, tenant
 * context, scheduler, credential resolver, event channel, and task
 * service. The standalone adapter (local-host.ts) supplies local
 * equivalents and has no Kanban mutation authority.
 *
 * Ownership map for the implementations behind these ports:
 * - CouncilStore repositories, event journal, outbox: CWE-006.
 * - Authorization and privacy adapters: CWE-007.
 * - Route registry and selection policy: CWE-008.
 * - HTTP/local transports: CWE-009. Host bridges: CWE-010.
 * - Durable scheduling and operation leases in production: CWE-027.
 * - Budget reservations and capacity service: CWE-028.
 * - Run authorization service (RunGrant issuance): CWE-049.
 * This unit defines the ports and a standalone local composition so the
 * CLI and the engine have a real, testable foundation today.
 */

import type {
  Clock,
  CouncilCard,
  CouncilEvent,
  DecisionBrief,
  EvidenceManifestEntry,
  IdSource,
  JobCheckpoint,
  ModelPolicy,
  RunGrant,
  ScopeFields,
  SeatId,
  SessionSpec,
  SessionStateRecord,
  Verdict,
} from '../contracts/index.js';

export type { Clock, IdSource };

/** A session as persisted by a store: spec, frozen brief, scope, state. */
export interface StoredSession {
  spec: SessionSpec;
  brief: DecisionBrief;
  scope: ScopeFields;
  state: SessionStateRecord;
  /**
   * True for synthetic sample/replay fixtures. Sample sessions are
   * labeled everywhere they surface and can never create production
   * actions (Sections 18.4, 30.4, 36.5).
   */
  sample: boolean;
}

/**
 * Persistence port. Implementations must enforce the Section 15 rules:
 * card uniqueness per logical operation, ordered event sequences,
 * state-version compare-and-swap, and no provider call inside a store
 * transaction.
 */
export interface CouncilStore {
  createSession(session: StoredSession): Promise<void>;
  getSession(sessionId: string): Promise<StoredSession | null>;
  /** Compare-and-swap on state_version; throws on a stale writer. */
  updateState(record: SessionStateRecord, expectedVersion: number): Promise<void>;
  /** Insert a validated card; a duplicate logical operation is rejected. */
  saveCard(card: CouncilCard): Promise<void>;
  findCard(
    sessionId: string,
    round: number,
    seatId: SeatId,
    inputSha256: string,
  ): Promise<CouncilCard | null>;
  listCards(sessionId: string): Promise<CouncilCard[]>;
  /** Append an event; the store assigns the next session sequence. */
  appendEvent(
    event: Omit<CouncilEvent, 'sequence'>,
  ): Promise<CouncilEvent>;
  listEvents(sessionId: string, afterSequence?: number): Promise<CouncilEvent[]>;
  saveVerdict(verdict: Verdict): Promise<void>;
  getVerdict(sessionId: string): Promise<Verdict | null>;
  saveCheckpoint(checkpoint: JobCheckpoint): Promise<void>;
  getCheckpoint(
    sessionId: string,
    phase: string,
    seatId: SeatId | null,
    inputSha256: string,
  ): Promise<JobCheckpoint | null>;
}

/** One provider request, as the orchestrator issues it to a transport. */
export interface TransportRequest {
  purpose: 'advisor' | 'ratification' | 'consult';
  session_id: string;
  seat_id: SeatId;
  round: 1 | 2 | 3 | null;
  route_id: string;
  model_policy: ModelPolicy;
  /** Logical prompt contract text (Section 14); never contains secrets. */
  system: string;
  /** Structured input: frozen brief, seat context, assigned challenges. */
  input: unknown;
  signal?: AbortSignal;
}

export interface TransportResponse {
  /** Raw model text; the engine validates it against the contracts. */
  text: string;
  provider_request_id: string | null;
  /** Provider-reported identity, kept distinct from verified identity. */
  reported_model_id: string | null;
  usage: { input_tokens: number | null; output_tokens: number | null };
}

/**
 * A model transport. Implementations are route-specific adapters owned by
 * CWE-009/CWE-010. A transport error may set `retryable: true` for
 * transient network/429/5xx classes only (Section 15.5); auth, missing
 * model, and policy errors must not be marked retryable.
 */
export interface ModelTransport {
  generate(request: TransportRequest): Promise<TransportResponse>;
}

export interface TransportRegistry {
  register(routeId: string, transport: ModelTransport): void;
  resolve(routeId: string): ModelTransport | null;
  listRoutes(): string[];
}

/**
 * Evidence access port. Retrieval is authorized and bounded (Sections 8
 * and 9): the engine receives the frozen manifest and, when a host
 * supports it, a seat's pack context. Raw source books never flow through
 * this port into a distributable artifact.
 */
export interface EvidenceProvider {
  loadEvidenceManifest(sessionId: string): Promise<EvidenceManifestEntry[]>;
  /**
   * The seat's approved pack context for prompt assembly, or null when
   * no pack is installed yet. Pack authoring is CWE-013 to CWE-021.
   */
  loadSeatPack(
    seatId: SeatId,
  ): Promise<{ pack_version: string; briefing_text: string } | null>;
}

/**
 * Secret presence only. The core never receives credential values
 * (Sections 13.1 and 28.5); it can only learn whether a route's
 * credential exists so readiness can be reported honestly.
 */
export interface SecretResolver {
  credentialPresent(routeId: string): Promise<boolean>;
}

/** One budget reservation handle (Section 15.6 reservation accounting). */
export interface BudgetReservation {
  operation_key: string;
  session_id: string;
  kind: 'provider_request' | 'output_repair' | 'transport_retry' | 'semantic_verification';
}

export interface BudgetSnapshot {
  session_id: string;
  ceilings: {
    max_provider_requests: number;
    max_output_repairs: number;
    max_transport_retries: number;
    max_semantic_verifications: number;
  };
  /** Actual provider requests dispatched, by kind. */
  consumed: {
    provider_requests: number;
    output_repairs: number;
    transport_retries: number;
    semantic_verifications: number;
  };
  /** Outstanding reservations not yet committed or released. */
  reserved: number;
  /** Requests whose provider completion is unknown; still reserved. */
  unknown: number;
}

/**
 * Budget ledger port (service owned by CWE-028). Available budget is
 * authorized limit minus consumed minus outstanding worst-case
 * reservations; unknown billed usage remains reserved, never zero.
 */
export interface BudgetLedger {
  reserve(input: {
    session_id: string;
    operation_key: string;
    kind: BudgetReservation['kind'];
  }): BudgetReservation;
  commit(reservation: BudgetReservation): void;
  release(reservation: BudgetReservation): void;
  /** Keep the reservation: the provider may have accepted the request. */
  markProviderCompletionUnknown(reservation: BudgetReservation): void;
  snapshot(session_id: string): BudgetSnapshot;
}

/** An operation lease with a monotonically increasing fencing epoch. */
export interface OperationLease {
  operation_key: string;
  owner_id: string;
  epoch: number;
  expires_at_ms: number;
}

/**
 * Capacity/operation lease port (production lifecycle owned by CWE-027).
 * Defaults: TTL 60 seconds, heartbeat every 15 seconds (Section 15.8).
 * Only a current lease confers commit authority for its operation.
 */
export interface CapacityLeaseProvider {
  claim(operation_key: string, owner_id: string, ttl_ms?: number): OperationLease;
  heartbeat(lease: OperationLease): OperationLease;
  assertCurrent(lease: OperationLease): void;
  release(lease: OperationLease): void;
}

/** Committed-event sink: the UI consumes committed events, never guesses. */
export interface CouncilEventSink {
  publish(event: Omit<CouncilEvent, 'sequence'>): Promise<CouncilEvent>;
}

/**
 * Run-authorization port. The engine resolves a grant reference here
 * before any provider request is admitted. The issuing service is
 * CWE-049 (Section 25.6); flags, files, or model output are never a
 * grant. A host without the service resolves null, and the engine
 * refuses to start with RUN_AUTHORIZATION_REQUIRED.
 */
export interface AuthorizationProvider {
  resolveRunGrant(
    grantRef: string,
    sessionId: string,
  ): Promise<RunGrant | null>;
}

/** The complete injected host, per directive Section 5.1. */
export interface CouncilHost {
  store: CouncilStore;
  transportRegistry: TransportRegistry;
  evidence: EvidenceProvider;
  secrets: SecretResolver;
  budget: BudgetLedger;
  capacity: CapacityLeaseProvider;
  events: CouncilEventSink;
  clock: Clock;
  ids: IdSource;
  authorize: AuthorizationProvider;
}
