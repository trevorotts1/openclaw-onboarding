/**
 * The shared budget reservation service (CWE-028, directive Sections
 * 13, 15.6, 15.9, and 34 CWE-028).
 *
 * This is THE single shared budget service for the council. It is
 * backed by CWE-006's scoped store: reservations are rows in the
 * canonical council_budget_reservations table (CWE-005 schema),
 * every lifecycle transition is journaled in CWE-006's durable,
 * hash-chained event journal inside the same transaction as the row
 * write, and a projection-outbox intent is enqueued in that same
 * transaction, exactly like CWE-006's accepted-card commit unit.
 *
 * Relationship to the CWE-004 foundation (composition, not
 * duplication): CWE-004's InProcessBudgetLedger (cli/budget.ts) is the
 * local standalone form of these same Section 15.6 semantics behind
 * the BudgetLedger host port: same ceilings, same counting rule
 * (committed, reserved, and unknown all spend; released and expired
 * free the slot), same unknown-completion rule. The local host
 * (cli/local-host.ts) composes that in-process form because a
 * standalone single-user run has no scoped store and no durable grant
 * record. This service is the shared form: the same accounting over
 * the scoped store, plus the parts only the shared form can carry:
 * durability across restart, an authorization envelope on every call,
 * a durable RunGrant record (council_approvals, issued by CWE-049's
 * service) as the money authority, lease-epoch fencing, and the
 * pinned CWE-008 route snapshot on every charge. There is never a
 * second ledger competing with this one inside a composition: a host
 * composes either the local form (standalone) or this service
 * (shared), and CWE-050 performs that final composition.
 *
 * Accounting enforced here, all inside the reservation transaction
 * (compare-and-swap discipline of Section 16.4, so two concurrent
 * admissions cannot spend the same remaining allowance, test T061):
 * - The hard session ceiling on TOTAL provider requests
 *   (CouncilSettings.max_session_provider_requests, schema-capped at
 *   50). Every kind counts toward it: planned generations
 *   (provider_request), output repairs, transport retries, and
 *   semantic verifications share the one ceiling (Sections 15.9 and
 *   35.7, test T150: the planning envelope is 33 planned generations
 *   + 9 repairs + 8 transport retries = 50, and the two
 *   semantic-verification calls fit inside the same 50).
 * - Per-kind ceilings from the same settings object, enforced by this
 *   same service (never a second counter): output repairs
 *   (max_output_repair_requests, default 9), transport retries in
 *   total (max_transport_retries_total, default 8), semantic
 *   verifications (max_semantic_verification_requests, default 2),
 *   retries per original request (max_transport_retries_per_request,
 *   default 1), and repairs per original operation
 *   (max_output_repairs_per_original_operation, default 1).
 * - The grant money ceiling: the sum of outstanding worst-case
 *   reservations (estimates for reserved and unknown rows, actuals
 *   for committed rows) plus the new estimate may not exceed the
 *   grant record's max_cost_minor. Unknown completion keeps its
 *   reservation at the estimate: it is never reported as zero and
 *   never auto-released (tests T062, T063).
 *
 * Fencing (Section 15.8): reserve, settle, release, and
 * markProviderCompletionUnknown all present the caller's operation
 * lease epoch, which must equal the session's current lease epoch as
 * recorded in the journaled state record (the same fence source
 * CWE-006's acceptCard checks). A stale epoch is refused with
 * BUDGET_LEASE_FENCED and finalizes nothing.
 *
 * Route accounting (Section 13): every reservation pins the CWE-008
 * route selection snapshot it charges against (see
 * route-snapshot.ts). The snapshot is written verbatim into the
 * operation_reserved journal payload and never mutated. A route
 * change therefore cannot move a charge: the old reservation is
 * released with the RouteChangeRecord journaled
 * (releaseForRouteChange) and a new reservation is minted against the
 * new pinned snapshot. Resolution outcomes ride the journal in the
 * form CWE-009/CWE-010 established: accepted and approved-substitution
 * outcomes are payload on the operation_reserved event they enable,
 * and a refused outcome is journaled as an operation_completed event
 * with outcome 'route_resolution_refused' via recordRouteResolution.
 * The canonical event vocabulary (CWE-003 EVENT_TYPES) has no
 * route_changed type and none is invented here.
 *
 * Lifecycle: reserved -> committed (settle), reserved -> released,
 * reserved -> unknown (provider completion unknown; still counted,
 * settle-able when the outcome is later confirmed, never releasable
 * as free), reserved -> expired (hold lapsed before finalization, via
 * expireHolds or lazily at settle/release time). Every terminal
 * transition is exactly once: the state guard is re-checked inside
 * the transaction and a second settle or release fails with
 * BUDGET_RESERVATION_FINALIZED.
 */

import {
  DEFAULT_COUNCIL_SETTINGS,
  type Clock,
  type CouncilSettings,
  type IdSource,
  type RunCeilings,
} from '../contracts/index.js';
import type { BudgetSnapshot } from '../cli/host-ports.js';
import {
  scopeDenied,
  sessionDeleted,
  sessionNotFound,
} from '../persistence/errors.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { EventJournal } from '../persistence/journal.js';
import { ProjectionOutbox } from '../persistence/outbox.js';
import type {
  CouncilDatabase,
  SqliteDatabaseHandle,
} from '../persistence/sqlite.js';
import {
  BudgetCapacityError,
  budgetExhausted,
  budgetInvalidInput,
  budgetLeaseFenced,
  budgetStoreUnavailable,
} from './errors.js';
import {
  routeSnapshotFingerprint,
  type PinnedRouteSnapshot,
  type RouteChangeRecord,
  type RouteResolutionOutcome,
} from './route-snapshot.js';

export type BudgetReservationKind =
  | 'provider_request'
  | 'output_repair'
  | 'transport_retry'
  | 'semantic_verification';

export type BudgetReservationState =
  | 'reserved'
  | 'committed'
  | 'released'
  | 'expired'
  | 'unknown';

/**
 * How well the money on a reservation is known (WER-010). The union is
 * structurally identical to queue/producer.ts CostKnowledge; it is
 * restated here because budgets is the lower layer and must not import
 * upward from the queue.
 *
 * - `verified`: a metered/confirmed amount.
 * - `estimated`: a bounded quote that may differ from the final charge.
 * - `unknown`: pricing or usage is not known. An unknown reservation
 *   ALWAYS keeps a non-zero conservative hold and is never reported or
 *   settled as zero. A zero-unit unknown charge is refused at reserve
 *   time because that would silently treat unknown money as free.
 */
export type BudgetCostKnowledge = 'estimated' | 'verified' | 'unknown';

const COST_KNOWLEDGE: ReadonlySet<BudgetCostKnowledge> = new Set([
  'estimated',
  'verified',
  'unknown',
]);

/** Default hold lifetime for a reservation that is never finalized. */
export const DEFAULT_RESERVATION_HOLD_TTL_MS = 900_000;

const ACTIVE_STATES: ReadonlySet<BudgetReservationState> = new Set([
  'reserved',
  'committed',
  'unknown',
]);

const STATE_EVENT_TYPES = [
  'session_created',
  'session_state_changed',
  'session_paused',
  'session_cancelled',
  'session_blocked',
  'session_failed',
] as const;

const REQUIRED_TABLES = [
  'council_sessions',
  'council_events',
  'council_approvals',
  'council_budget_reservations',
  'council_projection_outbox',
] as const;

export interface DurableBudgetReservation {
  reservation_id: string;
  session_id: string;
  operation_id: string;
  grant_id: string;
  kind: BudgetReservationKind;
  state: BudgetReservationState;
  estimate_minor: number;
  actual_minor: number | null;
  currency: string;
  /** estimated | verified | unknown; unknown is never treated as zero. */
  cost_knowledge: BudgetCostKnowledge;
  /** The pinned CWE-008 snapshot this charge belongs to. Never migrates. */
  route_snapshot: PinnedRouteSnapshot;
  route_snapshot_fingerprint: string;
  /** Lease epoch the reservation was minted under. */
  lease_epoch: number;
  hold_expires_at: string;
  created_at: string;
  finalized_at: string | null;
}

export interface ReserveInput {
  session_id: string;
  operation_id: string;
  grant_id: string;
  kind: BudgetReservationKind;
  /** Worst-case charge in minor units; a safe integer >= 0. */
  estimate_minor: number;
  /** Defaults to the grant record's currency; a mismatch is refused. */
  currency?: string | null;
  /**
   * estimated | verified | unknown. Defaults to `estimated`. When
   * `unknown`, estimate_minor is a conservative hold and must be > 0:
   * unknown money is never reserved, reported, or settled as zero.
   */
  cost_knowledge?: BudgetCostKnowledge;
  /** The caller's current operation lease epoch (Section 15.8 fence). */
  lease_epoch: number;
  route_snapshot: PinnedRouteSnapshot;
  /** The resolution outcome that produced this snapshot, when any. */
  route_resolution?: RouteResolutionOutcome | null;
  /**
   * For output_repair and transport_retry reservations: the original
   * operation being repaired or retried. The per-original ceilings
   * (one retry per request, one repair per original) key on it.
   */
  original_operation_id?: string | null;
  /**
   * Grant ceilings from the RunGrant contract (CWE-049 composes
   * these). They may only TIGHTEN the settings ceilings: the
   * effective ceiling is the minimum of the two, field by field, so a
   * caller can never gain allowance by supplying values.
   */
  ceilings?: Partial<RunCeilings> | null;
}

export interface DurableBudgetSnapshot extends BudgetSnapshot {
  money: {
    /** The grant record's money ceiling, or null when unbounded/unknown. */
    authorized_minor: number | null;
    /** Worst-case outstanding: estimates held plus committed actuals. */
    outstanding_minor: number;
    committed_actual_minor: number;
    /** Holds that are not yet finalized (reserved and unknown rows). */
    held_minor: number;
    /** Holds whose completion is unknown; still counted, never zero. */
    unknown_minor: number;
    /** Active reservations minted with cost_knowledge 'unknown'. */
    unknown_cost_reservations: number;
    /** Null only when no reservation and no grant name a currency. */
    currency: string | null;
  };
  /** The Section 15.9 planning-envelope view over the one hard ceiling. */
  envelope_breakdown: {
    hard_ceiling: number;
    total_active: number;
    planned_generations: number;
    output_repairs: number;
    transport_retries: number;
    semantic_verifications: number;
  };
}

interface ReservationRow {
  id: string;
  session_id: string;
  operation_id: string;
  grant_id: string;
  estimate_minor: number;
  actual_minor: number | null;
  currency: string;
  state: BudgetReservationState;
  hold_expires_at: string;
  created_at: string;
  finalized_at: string | null;
}

interface GrantRow {
  id: string;
  session_id: string | null;
  max_cost_minor: number | null;
  currency: string | null;
  status: string;
  expires_at: string;
}

interface JournalChargeFacts {
  kind: BudgetReservationKind;
  original_operation_id: string | null;
  route_snapshot: PinnedRouteSnapshot;
  lease_epoch: number;
  cost_knowledge: BudgetCostKnowledge;
}

/** How far an operation got, as observed by the reconciler. */
export type ReconcileDispatch =
  | 'not_dispatched'
  | 'dispatched_no_response'
  | 'response_observed';

export interface ReconcileOperationInput {
  session_id: string;
  operation_id: string;
  lease_epoch: number;
  dispatch: ReconcileDispatch;
  /** Required for response_observed: the confirmed actual charge. */
  actual_minor?: number | null;
  /** Defaults to `verified`; `unknown` is never a settlement. */
  cost_knowledge?: BudgetCostKnowledge;
}

export type ReconcileOutcome =
  | 'nothing_to_reconcile'
  | 'released_not_dispatched'
  | 'settled'
  | 'already_settled'
  | 'held_unknown'
  | 'already_released'
  | 'already_expired';

export interface ReconcileResult {
  outcome: ReconcileOutcome;
  session_id: string;
  operation_id: string;
  reservation: DurableBudgetReservation | null;
  charged_minor: number | null;
  currency: string | null;
  /** True only for a recorded not-dispatched release. */
  released_not_dispatched: boolean;
}

export interface GrantRenewalInput {
  grant_id: string;
  session_id: string;
  /** Current operation lease epoch; a stale generation cannot renew. */
  lease_epoch: number;
  /** Capacity added to the durable ceiling; safe integer > 0. */
  additional_minor: number;
  currency?: string | null;
  /** Optional extension; never shortens the existing expiry. */
  new_expires_at?: string | null;
  /** Operator/authority reference recorded with the renewal. */
  authority_ref?: string | null;
}

export interface GrantRenewalResult {
  grant_id: string;
  currency: string;
  previous_max_cost_minor: number;
  new_max_cost_minor: number;
  expires_at: string;
  /** Historical usage at renewal time; renewal never resets it. */
  committed_actual_minor: number;
  consumed_provider_requests: number;
  active_reservations: number;
}

/** Durable granted ceiling plus its live usage and holds (WER-010). */
export interface DurableGrantLedger {
  grant_id: string;
  status: string;
  expires_at: string;
  max_cost_minor: number | null;
  currency: string | null;
  committed_actual_minor: number;
  held_minor: number;
  unknown_minor: number;
  outstanding_minor: number;
  remaining_minor: number | null;
  consumed_provider_requests: number;
  active_reservations: number;
}

export interface DurableBudgetServiceDeps {
  db: CouncilDatabase;
  clock: Clock;
  ids: IdSource;
  settings?: CouncilSettings;
  /** Reservation hold lifetime; defaults to DEFAULT_RESERVATION_HOLD_TTL_MS. */
  holdTtlMs?: number;
  /** Projection outbox attempt bound (CWE-006 default is 5). */
  outboxMaxAttempts?: number;
}

export class DurableBudgetService {
  private readonly db: CouncilDatabase;
  private readonly clock: Clock;
  private readonly ids: IdSource;
  private readonly settings: CouncilSettings;
  private readonly holdTtlMs: number;
  private readonly journal: EventJournal;
  private readonly outbox: ProjectionOutbox;

  constructor(deps: DurableBudgetServiceDeps) {
    this.db = deps.db;
    this.clock = deps.clock;
    this.ids = deps.ids;
    this.settings = deps.settings ?? DEFAULT_COUNCIL_SETTINGS;
    this.holdTtlMs = deps.holdTtlMs ?? DEFAULT_RESERVATION_HOLD_TTL_MS;
    this.journal = new EventJournal(deps.db);
    this.outbox = new ProjectionOutbox(deps.db, deps.outboxMaxAttempts ?? 5);
  }

  // ------------------------------------------------------------ readiness

  /**
   * Typed readiness probe: the store must be reachable and carry the
   * canonical schema tables this service depends on. A failed probe
   * throws BUDGET_STORE_UNAVAILABLE; nothing is ever half-granted on
   * the strength of a probe the caller skipped, because reserve()
   * re-checks the schema inside its own transaction.
   */
  readiness(): { ready: true; tables_checked: string[] } {
    try {
      const present = this.db.read((handle) => {
        const rows = handle
          .prepare(
            `SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (${REQUIRED_TABLES.map(() => '?').join(', ')})`,
          )
          .all(...REQUIRED_TABLES) as Array<{ name: string }>;
        return new Set(rows.map((r) => r.name));
      });
      const missing = REQUIRED_TABLES.filter((t) => !present.has(t));
      if (missing.length > 0) {
        throw budgetStoreUnavailable(
          `The council store is missing canonical schema table(s): ${missing.join(', ')}. Reservations cannot be honored against a partial schema.`,
        );
      }
    } catch (error) {
      if (error instanceof BudgetCapacityError) throw error;
      throw budgetStoreUnavailable(
        'The council store could not be probed for budget readiness. Reservations cannot be honored while the store is unavailable.',
      );
    }
    return { ready: true, tables_checked: [...REQUIRED_TABLES] };
  }

  // -------------------------------------------------------------- reserve

  /**
   * Reserve one provider request against the session ceilings, the
   * grant money ceiling, and the pinned route snapshot, BEFORE
   * dispatch. Idempotent per operation: re-reserving the same
   * operation while its reservation is reserved, committed, or
   * unknown returns the existing reservation and counts nothing twice;
   * re-reserving after a release or expiry revives the operation's row
   * as a fresh reservation (the journal keeps the full history).
   */
  reserve(
    envelope: AuthorizationEnvelope,
    input: ReserveInput,
  ): DurableBudgetReservation {
    this.assertReserveInput(input);
    // The pinned snapshot's trusted scope must be the envelope's
    // scope: a snapshot minted for another tenant, company, or
    // installation is not a charge target here (planted-scope defense,
    // mirroring CWE-008's UNTRUSTED_SCOPE_FIELD rule).
    const snapScope = input.route_snapshot.scope;
    if (
      snapScope.tenantId !== envelope.tenant_id ||
      snapScope.companyId !== envelope.company_id ||
      snapScope.installationId !== envelope.installation_id
    ) {
      throw scopeDenied(
        'The pinned route snapshot scope does not match the authorization envelope. A reservation is never minted against a snapshot from another scope.',
      );
    }
    if (input.route_resolution?.outcome === 'refused') {
      throw new BudgetCapacityError(
        'BUDGET_ROUTE_RESOLUTION_REFUSED',
        `Route resolution for ${input.route_snapshot.routeId} was refused; no reservation is minted for a refused route. The refusal is recorded via recordRouteResolution.`,
        {
          retryable: false,
          action:
            'Keep the pinned route, or obtain a client-approved substitution and reserve against the new pinned snapshot.',
          detail: { route_id: input.route_snapshot.routeId },
        },
      );
    }
    const now = this.clock.nowUtc();
    return this.db.write((handle) => {
      this.assertSchema(handle);
      this.assertSessionUsable(handle, envelope, input.session_id);
      const currentEpoch = this.currentLeaseEpoch(envelope, input.session_id);
      if (input.lease_epoch !== currentEpoch) {
        throw budgetLeaseFenced({
          sessionId: input.session_id,
          operationId: input.operation_id,
          presentedEpoch: input.lease_epoch,
          currentEpoch,
        });
      }
      const grant = this.grantRow(handle, envelope, input.grant_id);
      if (!grant) {
        throw new BudgetCapacityError(
          'BUDGET_GRANT_NOT_FOUND',
          `No run grant record ${input.grant_id} exists in this scope. A reservation is never minted without the durable grant record CWE-049 issues.`,
          {
            retryable: false,
            action: 'Resolve a valid RunGrant first (CWE-049), then reserve.',
            detail: { grant_id: input.grant_id },
          },
        );
      }
      if (grant.status !== 'active' || grant.expires_at <= now) {
        throw new BudgetCapacityError(
          'BUDGET_GRANT_INACTIVE',
          `Run grant ${grant.id} is not active (status ${grant.status}, expires ${grant.expires_at}). Reservations under an expired, revoked, or exhausted grant are refused, never partially granted.`,
          {
            retryable: false,
            action: 'Obtain a fresh grant through CWE-049 admission.',
            detail: { grant_id: grant.id, status: grant.status },
          },
        );
      }
      if (grant.session_id !== null && grant.session_id !== input.session_id) {
        throw new BudgetCapacityError(
          'BUDGET_GRANT_SESSION_MISMATCH',
          `Run grant ${grant.id} is bound to session ${grant.session_id}, not ${input.session_id}. A grant never pays for another session.`,
          { retryable: false, detail: { grant_id: grant.id } },
        );
      }
      const currency = input.currency ?? grant.currency;
      if (!currency) {
        throw budgetInvalidInput(
          'A reservation needs a currency: neither the input nor the grant record names one.',
        );
      }
      if (grant.currency !== null && currency !== grant.currency) {
        throw new BudgetCapacityError(
          'BUDGET_CURRENCY_MISMATCH',
          `Reservation currency ${currency} does not match grant currency ${grant.currency}. Charges never convert or mix currencies silently.`,
          { retryable: false, detail: { grant_id: grant.id } },
        );
      }

      const costKnowledge = input.cost_knowledge ?? 'estimated';
      if (!COST_KNOWLEDGE.has(costKnowledge)) {
        throw budgetInvalidInput(
          `cost_knowledge must be estimated|verified|unknown; received ${String(costKnowledge)}.`,
        );
      }
      if (costKnowledge === 'unknown' && input.estimate_minor === 0) {
        throw budgetInvalidInput(
          'Unknown money cannot be reserved at zero: an unknown charge always keeps a conservative non-zero hold. Supply the worst-case estimate, or state cost_knowledge estimated|verified for a genuinely zero charge.',
        );
      }

      const existing = this.reservationRow(
        handle,
        envelope,
        input.session_id,
        input.operation_id,
      );
      if (existing && ACTIVE_STATES.has(existing.state)) {
        return this.toRecord(envelope, existing);
      }

      const ceilings = this.effectiveCeilings(input.ceilings ?? null);
      const rows = this.sessionRows(handle, envelope, input.session_id);
      const facts = this.journalFacts(envelope, input.session_id);
      const active = rows.filter((r) => ACTIVE_STATES.has(r.state));
      if (active.length + 1 > ceilings.max_provider_requests) {
        throw budgetExhausted({
          ceiling: 'max_session_provider_requests',
          limit: ceilings.max_provider_requests,
          current: active.length,
          sessionId: input.session_id,
        });
      }
      const kindOf = (r: ReservationRow) => facts.get(r.operation_id)?.kind;
      const kindActive = active.filter((r) => kindOf(r) === input.kind);
      const kindCeiling =
        input.kind === 'output_repair'
          ? ceilings.max_output_repairs
          : input.kind === 'transport_retry'
            ? ceilings.max_transport_retries
            : input.kind === 'semantic_verification'
              ? ceilings.max_semantic_verifications
              : ceilings.max_provider_requests;
      if (kindActive.length + 1 > kindCeiling) {
        throw budgetExhausted({
          ceiling:
            input.kind === 'output_repair'
              ? 'max_output_repair_requests'
              : input.kind === 'transport_retry'
                ? 'max_transport_retries_total'
                : 'max_semantic_verification_requests',
          limit: kindCeiling,
          current: kindActive.length,
          sessionId: input.session_id,
        });
      }
      if (input.original_operation_id) {
        const perOriginal =
          input.kind === 'transport_retry'
            ? ceilings.max_transport_retries_per_request
            : input.kind === 'output_repair'
              ? ceilings.max_output_repairs_per_original_operation
              : null;
        if (perOriginal !== null) {
          const siblings = active.filter(
            (r) =>
              kindOf(r) === input.kind &&
              facts.get(r.operation_id)?.original_operation_id ===
                input.original_operation_id,
          );
          if (siblings.length + 1 > perOriginal) {
            throw budgetExhausted({
              ceiling:
                input.kind === 'transport_retry'
                  ? 'max_transport_retries_per_request'
                  : 'max_output_repairs_per_original_operation',
              limit: perOriginal,
              current: siblings.length,
              sessionId: input.session_id,
            });
          }
        }
      }
      const moneyLimit = this.effectiveMoneyLimit(grant, input.ceilings ?? null, currency);
      if (moneyLimit !== null) {
        let outstanding = 0;
        for (const row of active) {
          if (row.currency !== currency) {
            throw new BudgetCapacityError(
              'BUDGET_CURRENCY_MISMATCH',
              `Session ${input.session_id} already holds a reservation in ${row.currency} under a ${currency} grant. Mixed-currency sessions are refused rather than summed.`,
              { retryable: false, detail: { session_id: input.session_id } },
            );
          }
          outstanding +=
            row.state === 'committed'
              ? (row.actual_minor ?? row.estimate_minor)
              : row.estimate_minor;
        }
        if (outstanding + input.estimate_minor > moneyLimit) {
          throw budgetExhausted({
            ceiling: 'grant_max_cost_minor',
            limit: moneyLimit,
            current: outstanding,
            sessionId: input.session_id,
          });
        }
      }

      const holdExpiresAt = new Date(
        Date.parse(now) + this.holdTtlMs,
      ).toISOString();
      const reservationId = existing ? existing.id : this.ids.newId();
      if (existing) {
        handle
          .prepare(
            `UPDATE council_budget_reservations
                SET grant_id = ?, estimate_minor = ?, actual_minor = NULL,
                    currency = ?, state = 'reserved', hold_expires_at = ?,
                    created_at = ?, finalized_at = NULL
              WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?`,
          )
          .run(
            input.grant_id,
            input.estimate_minor,
            currency,
            holdExpiresAt,
            now,
            envelope.tenant_id,
            envelope.company_id,
            input.session_id,
            existing.id,
          );
      } else {
        handle
          .prepare(
            `INSERT INTO council_budget_reservations
               (tenant_id, company_id, session_id, id, operation_id, grant_id,
                estimate_minor, actual_minor, currency, state, hold_expires_at,
                created_at, finalized_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 'reserved', ?, ?, NULL)`,
          )
          .run(
            envelope.tenant_id,
            envelope.company_id,
            input.session_id,
            reservationId,
            input.operation_id,
            input.grant_id,
            input.estimate_minor,
            currency,
            holdExpiresAt,
            now,
          );
      }
      const fingerprint = routeSnapshotFingerprint(input.route_snapshot);
      const event = this.journal.append(handle, envelope, input.session_id, {
        event_id: this.ids.newId(),
        type: 'operation_reserved',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          reservation_id: reservationId,
          operation_id: input.operation_id,
          grant_id: input.grant_id,
          kind: input.kind,
          original_operation_id: input.original_operation_id ?? null,
          estimate_minor: input.estimate_minor,
          currency,
          cost_knowledge: costKnowledge,
          lease_epoch: input.lease_epoch,
          hold_expires_at: holdExpiresAt,
          route_snapshot: input.route_snapshot,
          route_snapshot_fingerprint: fingerprint,
          route_resolution: input.route_resolution ?? null,
          reissued_from_state: existing ? existing.state : null,
        },
        created_at: now,
      });
      this.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: input.session_id,
        event_sequence: event.sequence,
        topic: 'budget.reserved',
        idempotency_key: `budget:${reservationId}:reserved:${event.sequence}`,
        payload: {
          session_id: input.session_id,
          reservation_id: reservationId,
          operation_id: input.operation_id,
          event_sequence: event.sequence,
        },
        created_at: now,
      });
      return {
        reservation_id: reservationId,
        session_id: input.session_id,
        operation_id: input.operation_id,
        grant_id: input.grant_id,
        kind: input.kind,
        state: 'reserved' as const,
        estimate_minor: input.estimate_minor,
        actual_minor: null,
        currency,
        cost_knowledge: costKnowledge,
        route_snapshot: input.route_snapshot,
        route_snapshot_fingerprint: fingerprint,
        lease_epoch: input.lease_epoch,
        hold_expires_at: holdExpiresAt,
        created_at: now,
        finalized_at: null,
      };
    });
  }

  // ----------------------------------------------------------- finalize

  /**
   * Settle a reservation with the actual charge. Allowed from
   * 'reserved' and from 'unknown' (the provider outcome was later
   * confirmed). Exactly once: settling a committed, released, or
   * expired reservation throws BUDGET_RESERVATION_FINALIZED.
   */
  settle(
    envelope: AuthorizationEnvelope,
    input: {
      session_id: string;
      operation_id: string;
      lease_epoch: number;
      actual_minor: number;
      /** verified (default) or estimated; `unknown` is never a settle. */
      cost_knowledge?: BudgetCostKnowledge;
    },
  ): DurableBudgetReservation {
    if (!Number.isSafeInteger(input.actual_minor) || input.actual_minor < 0) {
      throw budgetInvalidInput('actual_minor must be a safe integer >= 0.');
    }
    const knowledge = input.cost_knowledge ?? 'verified';
    if (!COST_KNOWLEDGE.has(knowledge) || knowledge === 'unknown') {
      throw budgetInvalidInput(
        'A settlement must carry cost_knowledge verified or estimated. Unknown money is held, not settled; call markProviderCompletionUnknown and reconcile later.',
      );
    }
    const minted = this.journalFacts(envelope, input.session_id).get(
      input.operation_id,
    );
    if (minted?.cost_knowledge === 'unknown' && knowledge !== 'verified') {
      throw budgetInvalidInput(
        `Reservation ${input.operation_id} was minted with cost_knowledge unknown; only a verified amount may settle it. An estimate never resolves unknown money.`,
      );
    }
    return this.finalize(envelope, input, {
      outcome: 'settled',
      allowedFrom: ['reserved', 'unknown'],
      apply: (handle, row, now) => {
        const result = handle
          .prepare(
            `UPDATE council_budget_reservations
                SET state = 'committed', actual_minor = ?, finalized_at = ?
              WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?
                AND state = ?`,
          )
          .run(
            input.actual_minor,
            now,
            envelope.tenant_id,
            envelope.company_id,
            input.session_id,
            row.id,
            row.state,
          );
        if (Number(result.changes) !== 1) {
          throw this.finalizedError(row, 'settled');
        }
      },
      payload: (row) => ({
        actual_minor: input.actual_minor,
        currency: row.currency,
        cost_knowledge: knowledge,
      }),
    });
  }

  /**
   * Release a reservation that was never dispatched (or was cancelled
   * before dispatch). Only 'reserved' may be released: a committed,
   * unknown, expired, or already released reservation throws
   * BUDGET_RESERVATION_FINALIZED. An unknown-completion request is
   * never released as though it were free.
   */
  release(
    envelope: AuthorizationEnvelope,
    input: {
      session_id: string;
      operation_id: string;
      lease_epoch: number;
      reason?: string | null;
    },
  ): DurableBudgetReservation {
    return this.finalize(envelope, input, {
      outcome: 'released',
      allowedFrom: ['reserved'],
      apply: (handle, row, now) => {
        const result = handle
          .prepare(
            `UPDATE council_budget_reservations
                SET state = 'released', finalized_at = ?
              WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?
                AND state = 'reserved'`,
          )
          .run(now, envelope.tenant_id, envelope.company_id, input.session_id, row.id);
        if (Number(result.changes) !== 1) {
          throw this.finalizedError(row, 'released');
        }
      },
      payload: () => ({ reason: input.reason ?? null }),
    });
  }

  /**
   * Release a reservation because an approved route change superseded
   * its pinned route. The charge never migrates: this reservation
   * ends here, the RouteChangeRecord is journaled with the release,
   * and the caller reserves anew against the replacement snapshot.
   * Only a 'reserved' (not yet dispatched) reservation may be
   * route-released.
   */
  releaseForRouteChange(
    envelope: AuthorizationEnvelope,
    input: {
      session_id: string;
      operation_id: string;
      lease_epoch: number;
      change: RouteChangeRecord;
    },
  ): DurableBudgetReservation {
    return this.finalize(envelope, input, {
      outcome: 'route_changed_released',
      allowedFrom: ['reserved'],
      apply: (handle, row, now) => {
        const result = handle
          .prepare(
            `UPDATE council_budget_reservations
                SET state = 'released', finalized_at = ?
              WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?
                AND state = 'reserved'`,
          )
          .run(now, envelope.tenant_id, envelope.company_id, input.session_id, row.id);
        if (Number(result.changes) !== 1) {
          throw this.finalizedError(row, 'released');
        }
      },
      payload: () => ({ change_record: { ...input.change } }),
    });
  }

  /**
   * Mark a dispatched request whose provider completion is unknown.
   * The reservation stays fully counted at its estimate (never zero,
   * never auto-replayed); it can later be settled when the outcome is
   * confirmed, but it can never be released as free.
   */
  markProviderCompletionUnknown(
    envelope: AuthorizationEnvelope,
    input: { session_id: string; operation_id: string; lease_epoch: number },
  ): DurableBudgetReservation {
    const now = this.clock.nowUtc();
    return this.db.write((handle) => {
      this.assertSchema(handle);
      this.assertSessionUsable(handle, envelope, input.session_id);
      const row = this.reservationRow(handle, envelope, input.session_id, input.operation_id);
      if (!row) throw this.notFoundError(input.session_id, input.operation_id);
      this.assertEpoch(envelope, input.session_id, input.operation_id, input.lease_epoch);
      if (row.state === 'unknown') {
        return this.toRecord(envelope, row);
      }
      if (row.state !== 'reserved') {
        throw this.finalizedError(row, 'marked unknown');
      }
      const result = handle
        .prepare(
          `UPDATE council_budget_reservations SET state = 'unknown'
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?
              AND state = 'reserved'`,
        )
        .run(envelope.tenant_id, envelope.company_id, input.session_id, row.id);
      if (Number(result.changes) !== 1) throw this.finalizedError(row, 'marked unknown');
      const event = this.journal.append(handle, envelope, input.session_id, {
        event_id: this.ids.newId(),
        type: 'operation_completed',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          reservation_id: row.id,
          operation_id: row.operation_id,
          outcome: 'completion_unknown',
          from_state: 'reserved',
          estimate_minor: row.estimate_minor,
          currency: row.currency,
          lease_epoch: input.lease_epoch,
        },
        created_at: now,
      });
      this.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: input.session_id,
        event_sequence: event.sequence,
        topic: 'budget.finalized',
        idempotency_key: `budget:${row.id}:completion_unknown:${event.sequence}`,
        payload: {
          session_id: input.session_id,
          reservation_id: row.id,
          operation_id: row.operation_id,
          outcome: 'completion_unknown',
          event_sequence: event.sequence,
        },
        created_at: now,
      });
      return this.toRecord(envelope, { ...row, state: 'unknown' });
    });
  }

  /**
   * Expire every lapsed hold in the envelope scope (optionally one
   * session): reserved rows whose hold_expires_at has passed become
   * 'expired' and free their allowance. Unknown rows are never
   * expired: a possibly-billed request does not become free with time.
   * CWE-027's scheduler calls this on its sweep cadence; settle and
   * release also expire a lapsed hold lazily, in a small commit unit
   * immediately before their own finalize transaction, so the
   * refusal that follows cannot roll the expiry back.
   */
  expireHolds(
    envelope: AuthorizationEnvelope,
    sessionId?: string,
  ): Array<{ session_id: string; operation_id: string; reservation_id: string }> {
    const now = this.clock.nowUtc();
    return this.db.write((handle) => {
      this.assertSchema(handle);
      const rows = handle
        .prepare(
          `SELECT id, session_id, operation_id, grant_id, estimate_minor,
                  actual_minor, currency, state, hold_expires_at, created_at,
                  finalized_at
             FROM council_budget_reservations
            WHERE tenant_id = ? AND company_id = ? AND state = 'reserved'
              AND hold_expires_at <= ?
              ${sessionId ? 'AND session_id = ?' : ''}
            ORDER BY created_at ASC`,
        )
        .all(
          envelope.tenant_id,
          envelope.company_id,
          now,
          ...(sessionId ? [sessionId] : []),
        ) as ReservationRow[];
      const expired: Array<{
        session_id: string;
        operation_id: string;
        reservation_id: string;
      }> = [];
      for (const row of rows) {
        if (!this.expireRow(handle, envelope, row, now)) continue;
        expired.push({
          session_id: row.session_id,
          operation_id: row.operation_id,
          reservation_id: row.id,
        });
      }
      return expired;
    });
  }

  // ------------------------------------------------------ route outcomes

  /**
   * Journal a route resolution outcome that produced no reservation.
   * A refused outcome is recorded as an operation_completed event
   * with outcome 'route_resolution_refused', carrying the full
   * CWE-008 outcome (including its substitution_refused event and any
   * prose-claim-ignored record). Accepted and approved-substitution
   * outcomes are NOT journaled here: they ride the operation_reserved
   * event of the reservation they enable, so one resolution is never
   * double-counted in the audit trail.
   */
  recordRouteResolution(
    envelope: AuthorizationEnvelope,
    input: {
      session_id: string;
      route_snapshot: PinnedRouteSnapshot;
      resolution: RouteResolutionOutcome;
    },
  ): { recorded: boolean; reason: string } {
    if (input.resolution.outcome !== 'refused') {
      return {
        recorded: false,
        reason:
          'Accepted and approved-substitution outcomes are journaled with the reservation they enable (operation_reserved payload).',
      };
    }
    const now = this.clock.nowUtc();
    this.db.write((handle) => {
      this.assertSchema(handle);
      this.assertSessionUsable(handle, envelope, input.session_id);
      this.journal.append(handle, envelope, input.session_id, {
        event_id: this.ids.newId(),
        type: 'operation_completed',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          outcome: 'route_resolution_refused',
          route_id: input.route_snapshot.routeId,
          route_revision: input.route_snapshot.routeRevision,
          route_snapshot_fingerprint: routeSnapshotFingerprint(input.route_snapshot),
          resolution: input.resolution,
        },
        created_at: now,
      });
    });
    return {
      recorded: true,
      reason: 'Refusal journaled as operation_completed with outcome route_resolution_refused.',
    };
  }

  // --------------------------------------------------------------- reads

  /** One reservation by operation, or null outside the envelope scope. */
  getReservation(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    operationId: string,
  ): DurableBudgetReservation | null {
    const row = this.db.read((handle) =>
      this.reservationRow(handle, envelope, sessionId, operationId),
    );
    return row ? this.toRecord(envelope, row) : null;
  }

  /** All reservations of a session in the envelope scope, oldest first. */
  listReservations(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): DurableBudgetReservation[] {
    const rows = this.db.read((handle) =>
      this.sessionRows(handle, envelope, sessionId),
    );
    return rows.map((row) => this.toRecord(envelope, row));
  }

  /**
   * The session budget snapshot. Count fields match the CWE-004
   * BudgetLedger port shape exactly (consumed counts committed and
   * unknown; reserved counts outstanding holds), extended with the
   * money view and the Section 15.9 envelope breakdown.
   */
  snapshot(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    grantId?: string,
  ): DurableBudgetSnapshot {
    const rows = this.db.read((handle) =>
      this.sessionRows(handle, envelope, sessionId),
    );
    const facts = this.journalFacts(envelope, sessionId);
    // The service settings are the maximum any grant may use; the cap this
    // session is actually held to is the tighter of that and the session's
    // approved run grant (a light session is refused at request 51 even
    // though the service admits 100).
    const ceilings = this.effectiveCeilings(
      this.grantedCeilings(envelope, sessionId, grantId),
    );
    const kindOf = (r: ReservationRow) => facts.get(r.operation_id)?.kind;
    const inStates = (states: BudgetReservationState[]) =>
      rows.filter((r) => states.includes(r.state));
    const consumedStates: BudgetReservationState[] = ['committed', 'unknown'];
    const countKind = (
      kind: BudgetReservationKind,
      states: BudgetReservationState[],
    ) => rows.filter((r) => kindOf(r) === kind && states.includes(r.state)).length;
    const active = inStates(['reserved', 'committed', 'unknown']);
    let grant: GrantRow | null = null;
    if (grantId) {
      grant = this.db.read((handle) => this.grantRow(handle, envelope, grantId));
    }
    const currency =
      grant?.currency ?? (rows.length > 0 ? rows[0].currency : null);
    let outstanding = 0;
    let committedActual = 0;
    let held = 0;
    let unknownMoney = 0;
    let unknownCostReservations = 0;
    for (const row of active) {
      outstanding +=
        row.state === 'committed'
          ? (row.actual_minor ?? row.estimate_minor)
          : row.estimate_minor;
      if (row.state === 'committed') {
        committedActual += row.actual_minor ?? row.estimate_minor;
      } else {
        held += row.estimate_minor;
        if (row.state === 'unknown') unknownMoney += row.estimate_minor;
        if (facts.get(row.operation_id)?.cost_knowledge === 'unknown') {
          unknownCostReservations += 1;
        }
      }
    }
    return {
      session_id: sessionId,
      ceilings: {
        max_provider_requests: ceilings.max_provider_requests,
        max_output_repairs: ceilings.max_output_repairs,
        max_transport_retries: ceilings.max_transport_retries,
        max_semantic_verifications: ceilings.max_semantic_verifications,
      },
      consumed: {
        provider_requests: inStates(consumedStates).length,
        output_repairs: countKind('output_repair', consumedStates),
        transport_retries: countKind('transport_retry', consumedStates),
        semantic_verifications: countKind('semantic_verification', consumedStates),
      },
      reserved: inStates(['reserved']).length,
      unknown: inStates(['unknown']).length,
      money: {
        authorized_minor: grant ? grant.max_cost_minor : null,
        outstanding_minor: outstanding,
        committed_actual_minor: committedActual,
        held_minor: held,
        unknown_minor: unknownMoney,
        unknown_cost_reservations: unknownCostReservations,
        currency,
      },
      envelope_breakdown: {
        hard_ceiling: ceilings.max_provider_requests,
        total_active: active.length,
        planned_generations: countKind('provider_request', [
          'reserved',
          'committed',
          'unknown',
        ]),
        output_repairs: countKind('output_repair', ['reserved', 'committed', 'unknown']),
        transport_retries: countKind('transport_retry', [
          'reserved',
          'committed',
          'unknown',
        ]),
        semantic_verifications: countKind('semantic_verification', [
          'reserved',
          'committed',
          'unknown',
        ]),
      },
    };
  }

  // ------------------------------------------------------- grant lifecycle

  /**
   * The durable granted ceiling with its live usage and held
   * reservations (WER-010). A read-only projection over the grant row
   * (the durable authority) and the reservation rows (the durable
   * usage): nothing here is a process-local counter.
   */
  grantLedger(
    envelope: AuthorizationEnvelope,
    grantId: string,
  ): DurableGrantLedger {
    const grant = this.db.read((handle) => {
      this.assertSchema(handle);
      return this.grantRow(handle, envelope, grantId);
    });
    if (!grant) {
      throw new BudgetCapacityError(
        'BUDGET_GRANT_NOT_FOUND',
        `No run grant record ${grantId} exists in this scope.`,
        { retryable: false, detail: { grant_id: grantId } },
      );
    }
    const rows = this.db.read((handle) =>
      this.grantRows(handle, envelope, grantId),
    );
    const facts = new Map<string, JournalChargeFacts>();
    for (const row of rows) {
      const fact = this.journalFacts(envelope, row.session_id).get(row.operation_id);
      if (fact) facts.set(row.operation_id, fact);
    }
    let committed = 0;
    let held = 0;
    let unknownMoney = 0;
    let consumed = 0;
    let active = 0;
    for (const row of rows) {
      if (!ACTIVE_STATES.has(row.state)) continue;
      active += 1;
      if (row.state === 'committed') {
        committed += row.actual_minor ?? row.estimate_minor;
        consumed += 1;
      } else {
        held += row.estimate_minor;
        if (row.state === 'unknown') {
          unknownMoney += row.estimate_minor;
          consumed += 1;
        }
      }
    }
    const outstanding = committed + held;
    return {
      grant_id: grant.id,
      status: grant.status,
      expires_at: grant.expires_at,
      max_cost_minor: grant.max_cost_minor,
      currency: grant.currency,
      committed_actual_minor: committed,
      held_minor: held,
      unknown_minor: unknownMoney,
      outstanding_minor: outstanding,
      remaining_minor:
        grant.max_cost_minor === null
          ? null
          : Math.max(0, grant.max_cost_minor - outstanding),
      consumed_provider_requests: consumed,
      active_reservations: active,
    };
  }

  /**
   * Renew one session-bound grant: add authorized money capacity (and
   * optionally extend expiry) in ONE short transaction, fenced by the
   * caller's current lease epoch.
   *
   * - Only an active, unexpired, bounded grant renews. An unbounded
   *   grant has nothing to add; a standing (session-less) grant has no
   *   lease to fence against and is refused here.
   * - Capacity is ADDITIVE on the durable row. No reservation row, no
   *   journal event, and no counter is deleted or reset: historical
   *   usage and consumed counts are reported back unchanged.
   * - The update is compare-and-swap on the previous ceiling, so two
   *   concurrent renewals cannot silently overwrite each other.
   */
  renewGrantCeiling(
    envelope: AuthorizationEnvelope,
    input: GrantRenewalInput,
  ): GrantRenewalResult {
    if (!Number.isSafeInteger(input.additional_minor) || input.additional_minor <= 0) {
      throw budgetInvalidInput(
        'additional_minor must be a safe integer > 0. A renewal adds capacity; it never revokes.',
      );
    }
    if (!Number.isSafeInteger(input.lease_epoch) || input.lease_epoch < 0) {
      throw budgetInvalidInput('lease_epoch must be a safe integer >= 0.');
    }
    const now = this.clock.nowUtc();
    return this.db.write((handle) => {
      this.assertSchema(handle);
      this.assertSessionUsable(handle, envelope, input.session_id);
      const grant = this.grantRow(handle, envelope, input.grant_id);
      if (!grant) {
        throw new BudgetCapacityError(
          'BUDGET_GRANT_NOT_FOUND',
          `No run grant record ${input.grant_id} exists in this scope. Nothing was renewed.`,
          { retryable: false, detail: { grant_id: input.grant_id } },
        );
      }
      if (grant.status !== 'active' || grant.expires_at <= now) {
        throw new BudgetCapacityError(
          'BUDGET_GRANT_INACTIVE',
          `Run grant ${grant.id} is not active (status ${grant.status}, expires ${grant.expires_at}). A revoked, expired, or exhausted grant cannot be renewed.`,
          { retryable: false, detail: { grant_id: grant.id } },
        );
      }
      if (grant.session_id !== input.session_id) {
        throw new BudgetCapacityError(
          'BUDGET_GRANT_SESSION_MISMATCH',
          `Run grant ${grant.id} is bound to session ${grant.session_id ?? '(none)'}, not ${input.session_id}. Only a session-bound grant has a lease to fence a renewal.`,
          { retryable: false, detail: { grant_id: grant.id } },
        );
      }
      this.assertEpoch(
        envelope,
        input.session_id,
        `grant:${grant.id}`,
        input.lease_epoch,
      );
      if (grant.max_cost_minor === null) {
        throw budgetInvalidInput(
          `Run grant ${grant.id} has no money ceiling to renew (unbounded). Nothing was renewed.`,
        );
      }
      const currency = grant.currency;
      if (!currency) {
        throw budgetInvalidInput(
          `Run grant ${grant.id} names no currency, so a money renewal cannot be expressed.`,
        );
      }
      if (input.currency !== undefined && input.currency !== null && input.currency !== currency) {
        throw new BudgetCapacityError(
          'BUDGET_CURRENCY_MISMATCH',
          `Renewal currency ${input.currency} does not match grant currency ${currency}.`,
          { retryable: false, detail: { grant_id: grant.id } },
        );
      }
      let expiresAt = grant.expires_at;
      if (input.new_expires_at !== undefined && input.new_expires_at !== null) {
        const parsed = Date.parse(input.new_expires_at);
        if (Number.isNaN(parsed) || new Date(parsed).toISOString() !== input.new_expires_at) {
          throw budgetInvalidInput(
            'new_expires_at must be a UTC ISO 8601 timestamp.',
          );
        }
        if (input.new_expires_at > expiresAt) expiresAt = input.new_expires_at;
      }
      const previous = grant.max_cost_minor;
      const next = previous + input.additional_minor;
      if (!Number.isSafeInteger(next)) {
        throw budgetInvalidInput(
          'The renewed ceiling would exceed the safe integer range. Split the renewal.',
        );
      }
      const result = handle
        .prepare(
          `UPDATE council_approvals
              SET max_cost_minor = ?, expires_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = 'run_grant'
              AND status = 'active' AND max_cost_minor = ?`,
        )
        .run(
          next,
          expiresAt,
          envelope.tenant_id,
          envelope.company_id,
          grant.id,
          previous,
        );
      if (Number(result.changes) !== 1) {
        throw new BudgetCapacityError(
          'BUDGET_GRANT_INACTIVE',
          `Grant ${grant.id} changed state while renewal was in flight. Nothing was renewed.`,
          { retryable: true, detail: { grant_id: grant.id } },
        );
      }
      const event = this.journal.append(handle, envelope, input.session_id, {
        event_id: this.ids.newId(),
        type: 'grant_issued',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          grant_kind: 'run_grant',
          lifecycle: 'renewed',
          grant_id: grant.id,
          currency,
          previous_max_cost_minor: previous,
          added_minor: input.additional_minor,
          max_cost_minor: next,
          expires_at: expiresAt,
          lease_epoch: input.lease_epoch,
          authority_ref: input.authority_ref ?? null,
        },
        created_at: now,
      });
      this.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: input.session_id,
        event_sequence: event.sequence,
        topic: 'budget.grant_renewed',
        idempotency_key: `budget:grant:${grant.id}:renewed:${event.sequence}`,
        payload: {
          grant_id: grant.id,
          session_id: input.session_id,
          previous_max_cost_minor: previous,
          max_cost_minor: next,
          event_sequence: event.sequence,
        },
        created_at: now,
      });
      const ledger = this.grantLedger(envelope, grant.id);
      return {
        grant_id: grant.id,
        currency,
        previous_max_cost_minor: previous,
        new_max_cost_minor: next,
        expires_at: expiresAt,
        committed_actual_minor: ledger.committed_actual_minor,
        consumed_provider_requests: ledger.consumed_provider_requests,
        active_reservations: ledger.active_reservations,
      };
    });
  }

  // ---------------------------------------------------------- reconcile

  /**
   * Reconcile one operation after a crash (WER-010). Idempotent: the
   * same observation may be replayed any number of times and charges
   * once.
   *
   * - not_dispatched: a 'reserved' hold is released as free. That is
   *   the ONLY outcome that frees money. A committed or unknown
   *   reservation is never released.
   * - dispatched_no_response: the hold is marked unknown and stays
   *   counted at its estimate (never zero, never free).
   * - response_observed: the confirmed actual settles the reservation
   *   exactly once. Replaying the same amount on an already committed
   *   reservation returns `already_settled` and charges nothing again;
   *   a different amount conflicts.
   * - No row at all (crash before reserve): nothing to reconcile.
   *
   * Every branch presents the caller's lease epoch, and the underlying
   * commit re-checks it inside its own transaction.
   */
  reconcileOperation(
    envelope: AuthorizationEnvelope,
    input: ReconcileOperationInput,
  ): ReconcileResult {
    const dispatch = input.dispatch;
    if (
      dispatch !== 'not_dispatched' &&
      dispatch !== 'dispatched_no_response' &&
      dispatch !== 'response_observed'
    ) {
      throw budgetInvalidInput(
        'dispatch must be not_dispatched|dispatched_no_response|response_observed.',
      );
    }
    if (
      input.cost_knowledge !== undefined &&
      !COST_KNOWLEDGE.has(input.cost_knowledge)
    ) {
      throw budgetInvalidInput(
        'cost_knowledge must be estimated|verified|unknown.',
      );
    }
    const base = {
      session_id: input.session_id,
      operation_id: input.operation_id,
      charged_minor: null,
      currency: null,
      released_not_dispatched: false,
    };
    const readRow = () =>
      this.db.read((handle) => {
        this.assertSchema(handle);
        this.assertSessionUsable(handle, envelope, input.session_id);
        return this.reservationRow(
          handle,
          envelope,
          input.session_id,
          input.operation_id,
        );
      });
    const row = readRow();
    if (!row) {
      return {
        ...base,
        outcome: 'nothing_to_reconcile',
        reservation: null,
      };
    }
    this.assertEpoch(
      envelope,
      input.session_id,
      input.operation_id,
      input.lease_epoch,
    );
    const record = () => this.getReservation(envelope, input.session_id, input.operation_id);
    const result = (
      outcome: ReconcileOutcome,
      options: {
        charged?: number | null;
        released?: boolean;
      } = {},
    ): ReconcileResult => ({
      ...base,
      outcome,
      reservation: record(),
      charged_minor: options.charged ?? null,
      currency: row.currency,
      released_not_dispatched: options.released ?? false,
    });

    if (dispatch === 'not_dispatched') {
      if (row.state === 'reserved') {
        this.release(envelope, {
          session_id: input.session_id,
          operation_id: input.operation_id,
          lease_epoch: input.lease_epoch,
          reason: 'reconciled: known not dispatched',
        });
        return result('released_not_dispatched', { released: true });
      }
      if (row.state === 'released') return result('already_released');
      if (row.state === 'expired') return result('already_expired');
      // committed or unknown: prior effects stand, never undone.
      return result(
        row.state === 'unknown' ? 'held_unknown' : 'already_settled',
        { charged: row.actual_minor },
      );
    }

    if (dispatch === 'dispatched_no_response') {
      if (row.state === 'reserved') {
        this.markProviderCompletionUnknown(envelope, {
          session_id: input.session_id,
          operation_id: input.operation_id,
          lease_epoch: input.lease_epoch,
        });
      }
      if (row.state === 'unknown' || row.state === 'reserved') {
        return result('held_unknown');
      }
      if (row.state === 'committed') {
        return result('already_settled', { charged: row.actual_minor });
      }
      return result(row.state === 'released' ? 'already_released' : 'already_expired');
    }

    // response_observed
    if (input.actual_minor === undefined || input.actual_minor === null) {
      throw budgetInvalidInput(
        'response_observed reconciliation requires actual_minor (a safe integer >= 0).',
      );
    }
    if (!Number.isSafeInteger(input.actual_minor) || input.actual_minor < 0) {
      throw budgetInvalidInput('actual_minor must be a safe integer >= 0.');
    }
    const knowledge = input.cost_knowledge ?? 'verified';
    if (row.state === 'committed') {
      if (row.actual_minor === input.actual_minor) {
        return result('already_settled', { charged: row.actual_minor });
      }
      throw new BudgetCapacityError(
        'BUDGET_RECONCILE_CONFLICT',
        `Operation ${input.operation_id} is already committed at ${row.actual_minor ?? 'unknown'} ${row.currency}; reconciliation observed ${input.actual_minor} ${row.currency}. A committed charge is never silently rewritten.`,
        {
          retryable: false,
          action: 'Review both records; correct the charge through an audited adjustment.',
          detail: {
            operation_id: input.operation_id,
            committed_minor: row.actual_minor,
            observed_minor: input.actual_minor,
          },
        },
      );
    }
    if (row.state === 'released' || row.state === 'expired') {
      throw new BudgetCapacityError(
        'BUDGET_RECONCILE_CONFLICT',
        `Operation ${input.operation_id} ended as ${row.state} without dispatch; a response cannot settle it.`,
        { retryable: false, detail: { operation_id: input.operation_id } },
      );
    }
    try {
      const settled = this.settle(envelope, {
        session_id: input.session_id,
        operation_id: input.operation_id,
        lease_epoch: input.lease_epoch,
        actual_minor: input.actual_minor,
        cost_knowledge: knowledge,
      });
      return result('settled', { charged: settled.actual_minor });
    } catch (error) {
      if (
        error instanceof BudgetCapacityError &&
        error.code === 'BUDGET_RESERVATION_FINALIZED'
      ) {
        // A concurrent settlement won; replay only if it matches.
        const current = this.getReservation(
          envelope,
          input.session_id,
          input.operation_id,
        );
        if (current?.state === 'committed' && current.actual_minor === input.actual_minor) {
          return result('already_settled', { charged: current.actual_minor });
        }
      }
      throw error;
    }
  }

  // ------------------------------------------------------------ internals

  private finalize(
    envelope: AuthorizationEnvelope,
    input: { session_id: string; operation_id: string; lease_epoch: number },
    plan: {
      outcome: 'settled' | 'released' | 'route_changed_released';
      allowedFrom: BudgetReservationState[];
      apply: (
        handle: SqliteDatabaseHandle,
        row: ReservationRow,
        now: string,
      ) => void;
      payload: (row: ReservationRow) => Record<string, unknown>;
    },
  ): DurableBudgetReservation {
    const now = this.clock.nowUtc();
    // Lazy expiry, as its OWN commit unit before the finalize
    // transaction: a hold that lapsed before finalization ends as
    // expired, and the finalize below is then refused against that
    // final state. The expiry must not live inside the finalize
    // transaction, because the refusal would roll it back and the
    // lapsed hold would keep its allowance forever.
    const peek = this.db.read((handle) =>
      this.reservationRow(handle, envelope, input.session_id, input.operation_id),
    );
    if (peek && peek.state === 'reserved' && peek.hold_expires_at <= now) {
      this.db.write((handle) => {
        const row = this.reservationRow(
          handle,
          envelope,
          input.session_id,
          input.operation_id,
        );
        if (row && row.state === 'reserved' && row.hold_expires_at <= now) {
          this.expireRow(handle, envelope, row, now);
        }
      });
    }
    return this.db.write((handle) => {
      this.assertSchema(handle);
      this.assertSessionUsable(handle, envelope, input.session_id);
      const row = this.reservationRow(handle, envelope, input.session_id, input.operation_id);
      if (!row) throw this.notFoundError(input.session_id, input.operation_id);
      this.assertEpoch(envelope, input.session_id, input.operation_id, input.lease_epoch);
      if (!plan.allowedFrom.includes(row.state)) {
        throw this.finalizedError(row, plan.outcome);
      }
      plan.apply(handle, row, now);
      const stored = this.reservationRow(
        handle,
        envelope,
        input.session_id,
        input.operation_id,
      );
      const finalRow: ReservationRow = stored ?? row;
      const event = this.journal.append(handle, envelope, input.session_id, {
        event_id: this.ids.newId(),
        type: 'operation_completed',
        from_state: null,
        to_state: null,
        actor_subject: envelope.actor_subject,
        payload: {
          reservation_id: row.id,
          operation_id: row.operation_id,
          outcome: plan.outcome,
          from_state: row.state,
          lease_epoch: input.lease_epoch,
          ...plan.payload(row),
        },
        created_at: now,
      });
      this.outbox.enqueue(handle, envelope, {
        id: this.ids.newId(),
        session_id: input.session_id,
        event_sequence: event.sequence,
        topic: 'budget.finalized',
        idempotency_key: `budget:${row.id}:${plan.outcome}:${event.sequence}`,
        payload: {
          session_id: input.session_id,
          reservation_id: row.id,
          operation_id: row.operation_id,
          outcome: plan.outcome,
          event_sequence: event.sequence,
        },
        created_at: now,
      });
      return this.toRecord(envelope, finalRow);
    });
  }

  /**
   * Transition one reserved row to expired, with its journal event and
   * outbox intent. Returns false when the row was no longer reserved
   * (a concurrent finalization won; impossible inside one write
   * transaction, but the guard keeps the sweep honest).
   */
  private expireRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    row: ReservationRow,
    now: string,
  ): boolean {
    const result = handle
      .prepare(
        `UPDATE council_budget_reservations
            SET state = 'expired', finalized_at = ?
          WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND id = ?
            AND state = 'reserved'`,
      )
      .run(now, envelope.tenant_id, envelope.company_id, row.session_id, row.id);
    if (Number(result.changes) !== 1) return false;
    const event = this.journal.append(handle, envelope, row.session_id, {
      event_id: this.ids.newId(),
      type: 'operation_completed',
      from_state: null,
      to_state: null,
      actor_subject: envelope.actor_subject,
      payload: {
        reservation_id: row.id,
        operation_id: row.operation_id,
        outcome: 'expired',
        from_state: 'reserved',
        hold_expires_at: row.hold_expires_at,
      },
      created_at: now,
    });
    this.outbox.enqueue(handle, envelope, {
      id: this.ids.newId(),
      session_id: row.session_id,
      event_sequence: event.sequence,
      topic: 'budget.finalized',
      idempotency_key: `budget:${row.id}:expired:${event.sequence}`,
      payload: {
        session_id: row.session_id,
        reservation_id: row.id,
        operation_id: row.operation_id,
        outcome: 'expired',
        event_sequence: event.sequence,
      },
      created_at: now,
    });
    return true;
  }

  private assertReserveInput(input: ReserveInput): void {
    if (!Number.isSafeInteger(input.estimate_minor) || input.estimate_minor < 0) {
      throw budgetInvalidInput('estimate_minor must be a safe integer >= 0.');
    }
    if (!Number.isSafeInteger(input.lease_epoch) || input.lease_epoch < 0) {
      throw budgetInvalidInput('lease_epoch must be a safe integer >= 0.');
    }
    if (
      input.route_snapshot.schema !== 'wise-elders.route-selection/v1' ||
      typeof input.route_snapshot.routeId !== 'string' ||
      input.route_snapshot.routeId.length === 0
    ) {
      throw budgetInvalidInput(
        'route_snapshot must be a pinned CWE-008 route selection snapshot (schema wise-elders.route-selection/v1).',
      );
    }
    if (
      (input.kind === 'transport_retry' || input.kind === 'output_repair') &&
      !input.original_operation_id
    ) {
      throw budgetInvalidInput(
        `${input.kind} reservations must name original_operation_id: the per-original ceilings key on the operation being retried or repaired.`,
      );
    }
  }

  private assertSchema(handle: SqliteDatabaseHandle): void {
    const rows = handle
      .prepare(
        `SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (${REQUIRED_TABLES.map(() => '?').join(', ')})`,
      )
      .all(...REQUIRED_TABLES) as Array<{ name: string }>;
    if (rows.length !== REQUIRED_TABLES.length) {
      throw budgetStoreUnavailable(
        'The council store does not carry the full canonical schema. The reservation was not recorded.',
      );
    }
  }

  private assertSessionUsable(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): void {
    const tombstone = handle
      .prepare(
        `SELECT request_key FROM council_request_keys
          WHERE tenant_id = ? AND source = 'council-persistence'
            AND operation = 'session_deleted' AND request_key = ?`,
      )
      .get(envelope.tenant_id, sessionId) as { request_key: string } | undefined;
    if (tombstone) throw sessionDeleted(sessionId);
    const row = handle
      .prepare(
        `SELECT installation_id FROM council_sessions
          WHERE tenant_id = ? AND company_id = ? AND id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId) as
      | { installation_id: string }
      | undefined;
    if (!row) throw sessionNotFound(sessionId);
    if (row.installation_id !== envelope.installation_id) {
      throw scopeDenied(
        'The session belongs to a different installation than the authorization envelope. Repository writes never cross a tenant, company, or installation boundary.',
      );
    }
  }

  /** The session's current lease epoch, from its journaled state record. */
  private currentLeaseEpoch(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): number {
    const latest = this.journal.latestOfType(
      envelope,
      sessionId,
      [...STATE_EVENT_TYPES],
    );
    const record = latest?.payload.state_record as
      | { lease_epoch?: unknown }
      | undefined;
    if (!record || typeof record.lease_epoch !== 'number') {
      throw budgetStoreUnavailable(
        `Session ${sessionId} has no journaled state record to fence against. The reservation was not recorded.`,
      );
    }
    return record.lease_epoch;
  }

  private assertEpoch(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    operationId: string,
    presentedEpoch: number,
  ): void {
    const currentEpoch = this.currentLeaseEpoch(envelope, sessionId);
    if (presentedEpoch !== currentEpoch) {
      throw budgetLeaseFenced({
        sessionId,
        operationId,
        presentedEpoch,
        currentEpoch,
      });
    }
  }

  private grantRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    grantId: string,
  ): GrantRow | null {
    const row = handle
      .prepare(
        `SELECT id, session_id, max_cost_minor, currency, status, expires_at
           FROM council_approvals
          WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = 'run_grant'`,
      )
      .get(envelope.tenant_id, envelope.company_id, grantId) as GrantRow | undefined;
    return row ?? null;
  }

  private reservationRow(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
    operationId: string,
  ): ReservationRow | null {
    const row = handle
      .prepare(
        `SELECT id, session_id, operation_id, grant_id, estimate_minor,
                actual_minor, currency, state, hold_expires_at, created_at,
                finalized_at
           FROM council_budget_reservations
          WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND operation_id = ?`,
      )
      .get(envelope.tenant_id, envelope.company_id, sessionId, operationId) as
      | ReservationRow
      | undefined;
    return row ?? null;
  }

  private sessionRows(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): ReservationRow[] {
    return handle
      .prepare(
        `SELECT id, session_id, operation_id, grant_id, estimate_minor,
                actual_minor, currency, state, hold_expires_at, created_at,
                finalized_at
           FROM council_budget_reservations
          WHERE tenant_id = ? AND company_id = ? AND session_id = ?
          ORDER BY created_at ASC, id ASC`,
      )
      .all(envelope.tenant_id, envelope.company_id, sessionId) as ReservationRow[];
  }

  /** Every reservation row charged to one grant, newest last. */
  private grantRows(
    handle: SqliteDatabaseHandle,
    envelope: AuthorizationEnvelope,
    grantId: string,
  ): ReservationRow[] {
    return handle
      .prepare(
        `SELECT id, session_id, operation_id, grant_id, estimate_minor,
                actual_minor, currency, state, hold_expires_at, created_at,
                finalized_at
           FROM council_budget_reservations
          WHERE tenant_id = ? AND company_id = ? AND grant_id = ?
          ORDER BY created_at ASC, id ASC`,
      )
      .all(envelope.tenant_id, envelope.company_id, grantId) as ReservationRow[];
  }

  /**
   * Charge facts the reservation row does not carry (kind, original
   * operation, pinned route snapshot, minting epoch) are read from the
   * operation_reserved journal events: the journal is the durable
   * record, and the latest reserve event per operation wins (a revived
   * operation's newest facts govern).
   */
  private journalFacts(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): Map<string, JournalChargeFacts> {
    const facts = new Map<string, JournalChargeFacts>();
    for (const event of this.journal.list(envelope, sessionId, 0)) {
      if (event.type !== 'operation_reserved') continue;
      const p = event.payload;
      if (typeof p.operation_id !== 'string') continue;
      facts.set(p.operation_id, {
        kind: p.kind as BudgetReservationKind,
        original_operation_id:
          typeof p.original_operation_id === 'string'
            ? p.original_operation_id
            : null,
        route_snapshot: p.route_snapshot as PinnedRouteSnapshot,
        lease_epoch: typeof p.lease_epoch === 'number' ? p.lease_epoch : 0,
        // Records minted before WER-010 carry no field; estimated is
        // the honest historical reading (a bounded quote, never free).
        cost_knowledge: COST_KNOWLEDGE.has(p.cost_knowledge as BudgetCostKnowledge)
          ? (p.cost_knowledge as BudgetCostKnowledge)
          : 'estimated',
      });
    }
    return facts;
  }

  private toRecord(
    envelope: AuthorizationEnvelope,
    row: ReservationRow,
  ): DurableBudgetReservation {
    const facts = this.journalFacts(envelope, row.session_id).get(row.operation_id);
    if (!facts) {
      throw budgetStoreUnavailable(
        `Reservation ${row.id} has no operation_reserved journal event; the store is inconsistent and the record is not served.`,
      );
    }
    return {
      reservation_id: row.id,
      session_id: row.session_id,
      operation_id: row.operation_id,
      grant_id: row.grant_id,
      kind: facts.kind,
      state: row.state,
      estimate_minor: row.estimate_minor,
      actual_minor: row.actual_minor,
      currency: row.currency,
      cost_knowledge: facts.cost_knowledge,
      route_snapshot: facts.route_snapshot,
      route_snapshot_fingerprint: routeSnapshotFingerprint(facts.route_snapshot),
      lease_epoch: facts.lease_epoch,
      hold_expires_at: row.hold_expires_at,
      created_at: row.created_at,
      finalized_at: row.finalized_at,
    };
  }

  /**
   * The tightest count ceilings carried by the run grants funding this
   * session, so a report states the cap that is actually enforced instead
   * of the service-wide maximum. The grant's ceilings live in the
   * council_approvals scope proof, the same durable record the admission
   * path enforces. An unreadable proof is skipped: it can neither widen
   * nor narrow the reported cap.
   */
  private grantedCeilings(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    grantId?: string,
  ): Partial<RunCeilings> | null {
    const rows = this.db.read((handle) => {
      const select =
        `SELECT id, scope_proof FROM council_approvals
          WHERE tenant_id = ? AND company_id = ? AND kind = 'run_grant'`;
      return (
        grantId
          ? handle
              .prepare(`${select} AND id = ?`)
              .all(envelope.tenant_id, envelope.company_id, grantId)
          : handle
              .prepare(`${select} AND session_id = ?`)
              .all(envelope.tenant_id, envelope.company_id, sessionId)
      ) as Array<{ id: string; scope_proof: string }>;
    });
    const found: Array<Partial<RunCeilings>> = [];
    for (const row of rows) {
      try {
        const ceilings = (JSON.parse(row.scope_proof) as {
          ceilings?: Partial<RunCeilings>;
        }).ceilings;
        if (ceilings) found.push(ceilings);
      } catch {
        // An unreadable proof narrows nothing.
      }
    }
    if (found.length === 0) return null;
    const tightest = (pick: (c: Partial<RunCeilings>) => number | undefined) => {
      const values = found
        .map(pick)
        .filter((value): value is number => typeof value === 'number');
      return values.length === 0 ? undefined : Math.min(...values);
    };
    return {
      max_provider_requests: tightest((c) => c.max_provider_requests),
      max_output_repairs: tightest((c) => c.max_output_repairs),
      max_transport_retries: tightest((c) => c.max_transport_retries),
    };
  }

  private effectiveCeilings(tighten: Partial<RunCeilings> | null): {
    max_provider_requests: number;
    max_output_repairs: number;
    max_transport_retries: number;
    max_semantic_verifications: number;
    max_transport_retries_per_request: number;
    max_output_repairs_per_original_operation: number;
  } {
    const s = this.settings;
    const base = {
      max_provider_requests: s.max_session_provider_requests,
      max_output_repairs: s.max_output_repair_requests,
      max_transport_retries: s.max_transport_retries_total,
      max_semantic_verifications: s.max_semantic_verification_requests,
      max_transport_retries_per_request: s.max_transport_retries_per_request,
      max_output_repairs_per_original_operation:
        s.max_output_repairs_per_original_operation,
    };
    if (!tighten) return base;
    const min = (a: number, b: number | undefined) =>
      typeof b === 'number' ? Math.min(a, b) : a;
    return {
      ...base,
      max_provider_requests: min(base.max_provider_requests, tighten.max_provider_requests),
      max_output_repairs: min(base.max_output_repairs, tighten.max_output_repairs),
      max_transport_retries: min(base.max_transport_retries, tighten.max_transport_retries),
    };
  }

  private effectiveMoneyLimit(
    grant: GrantRow,
    tighten: Partial<RunCeilings> | null,
    currency: string,
  ): number | null {
    let limit = grant.max_cost_minor;
    const money = tighten?.max_money ?? null;
    if (money) {
      if (money.currency !== currency) {
        throw new BudgetCapacityError(
          'BUDGET_CURRENCY_MISMATCH',
          `Grant ceiling currency ${money.currency} does not match the reservation currency ${currency}.`,
          { retryable: false, detail: { grant_id: grant.id } },
        );
      }
      limit = limit === null ? money.amount_minor : Math.min(limit, money.amount_minor);
    }
    return limit;
  }

  private notFoundError(sessionId: string, operationId: string): BudgetCapacityError {
    return new BudgetCapacityError(
      'BUDGET_RESERVATION_NOT_FOUND',
      `No budget reservation for operation ${operationId} exists in session ${sessionId} in this scope. A reservation minted in another scope is indistinguishable from one that does not exist.`,
      {
        retryable: false,
        action: 'Reserve the operation first, under the owning scope envelope.',
        detail: { session_id: sessionId, operation_id: operationId },
      },
    );
  }

  private finalizedError(row: ReservationRow, attempted: string): BudgetCapacityError {
    return new BudgetCapacityError(
      'BUDGET_RESERVATION_FINALIZED',
      `Reservation for operation ${row.operation_id} is already ${row.state}; it cannot be ${attempted}. Settled and released reservations are final exactly once, and an unknown-completion reservation is never released as free.`,
      {
        retryable: false,
        action: 'Treat the recorded final state as authoritative.',
        detail: {
          operation_id: row.operation_id,
          final_state: row.state,
          attempted,
        },
      },
    );
  }
}
