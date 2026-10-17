/**
 * Per-operation admission and consumption for run grants (CWE-049,
 * directive Section 25.6).
 *
 * admitOperation is the only path that turns a grant into a reserved
 * provider operation, and recordConsumption is the only path that
 * settles one. Both compose the ONE RunAuthorizationService
 * (run-grants.ts) with CWE-028's ONE DurableBudgetService: admission
 * checks the grant, then reserves the worst-case allowance ONCE under
 * the caller's unique operation key inside CWE-028's reservation
 * transaction (which re-checks the durable grant record's status,
 * expiry, session binding, ceilings, and money ceiling in that same
 * transaction). There is no second ledger and no network call inside
 * either operation.
 *
 * Fence order in admitOperation (any failure refuses, journals the
 * refusal under the session, and throws a typed error):
 *   1. the grant exists in scope, is a granted (not preview-anchor)
 *      record, and is bound to this session;
 *   2. the grant is active and unexpired (a lapsed grant is flipped to
 *      'expired' and journaled on this first observation);
 *   3. a standing parent, when present, still stands;
 *   4. the session's revocation generation has not advanced past the
 *      grant's revocation epoch (session-level revocation fence);
 *   5. the operation kind is inside the grant's allowed kinds and the
 *      grant's purpose admits this operation's purpose;
 *   6. the pinned route snapshot fingerprint equals the grant's pin
 *      (a grant for route X admits nothing on route Y);
 *   7. CWE-028's reservation transaction enforces the session, grant,
 *      and standing-parent ceilings and the money ceiling.
 *
 * Replay law: admitOperation is idempotent per operation key ONLY
 * while every fence still passes. Replaying an earlier admission after
 * revocation or expiry is refused by fence 2 before the existing
 * reservation is ever consulted, and CWE-028's reserve re-checks the
 * grant record inside its own transaction as a second, independent
 * fence. An operation key already reserved under a DIFFERENT grant is
 * refused (RUN_OPERATION_GRANT_MISMATCH): an operation never migrates
 * between grants.
 *
 * Consumption law: recordConsumption settles the reservation with the
 * actual charge, or marks provider completion unknown (the reservation
 * stays counted at its estimate, never zero, never released as free:
 * CWE-028 semantics, reused, not re-derived). Accounting is recorded
 * even when the grant was revoked between admission and consumption:
 * an already-accepted request retains accounting and may produce a
 * valid result unless revocation or cancellation fences it, and the
 * result reports the grant's current status honestly. A revocation
 * racing transport handoff can leave an already-accepted request
 * billable; this module records that uncertainty and never promises
 * an impossible zero charge.
 */

import type { RunGrant } from '../contracts/index.js';
import {
  DurableBudgetService,
  routeSnapshotFingerprint,
  type BudgetReservationKind,
  type DurableBudgetReservation,
  type DurableBudgetSnapshot,
  type PinnedRouteSnapshot,
} from '../budgets/index.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { assertEnvelopePurpose } from '../persistence/envelope.js';
import {
  RunAuthorizationError,
  RunAuthorizationService,
  type RunGrantRecord,
} from './run-grants.js';

export interface AdmitOperationInput {
  grant_id: string;
  session_id: string;
  /** The caller's unique operation key (idempotency identity). */
  operation_id: string;
  kind: BudgetReservationKind;
  /** The operation's purpose; must equal the grant's purpose binding. */
  purpose?: string;
  /** Worst-case charge in minor units; a safe integer >= 0. */
  estimate_minor: number;
  currency?: string | null;
  /** The caller's current operation lease epoch (CWE-028 fence). */
  lease_epoch: number;
  /** The pinned route snapshot this operation charges against. */
  route_snapshot: PinnedRouteSnapshot;
  /** Required for output_repair and transport_retry (per-original ceilings). */
  original_operation_id?: string | null;
}

export interface Admission {
  operation_id: string;
  reservation_id: string;
  grant_id: string;
  session_id: string;
  kind: BudgetReservationKind;
  state: DurableBudgetReservation['state'];
  estimate_minor: number;
  currency: string;
  route_snapshot_fingerprint: string;
  /** The grant revocation epoch this admission was fenced against. */
  revocation_epoch: number;
  /** True when this call returned an already-existing reservation. */
  replayed: boolean;
}

export interface RecordConsumptionInput {
  grant_id: string;
  session_id: string;
  operation_id: string;
  lease_epoch: number;
  outcome: 'settled' | 'unknown';
  /** Required when outcome is 'settled'; a safe integer >= 0. */
  actual_minor?: number;
}

export interface ConsumptionRecord {
  operation_id: string;
  reservation_id: string;
  grant_id: string;
  state: DurableBudgetReservation['state'];
  actual_minor: number | null;
  estimate_minor: number;
  currency: string;
  /** The grant's status AFTER this consumption was recorded. */
  grant_status: string;
  /** Session totals after recording (CWE-028 snapshot, the one ledger). */
  totals: DurableBudgetSnapshot;
}

export class RunAdmissionService {
  constructor(
    private readonly grants: RunAuthorizationService,
    private readonly budget: DurableBudgetService,
  ) {}

  admitOperation(
    envelope: AuthorizationEnvelope,
    input: AdmitOperationInput,
  ): Admission
   {
    assertEnvelopePurpose(envelope, 'write', 'Operation admission');
    try {
      return this.admitChecked(envelope, input);
    } catch (error) {
      // Every refusal is journaled under the session (its own commit,
      // so the refusal survives the refusal) and then rethrown typed.
      const code =
        error instanceof RunAuthorizationError
          ? error.code
          : error instanceof Error && 'code' in error
            ? String((error as { code: unknown }).code)
            : 'RUN_ADMISSION_REFUSED';
      try {
        this.grants.journalAdmissionRefused(envelope, input.session_id, {
          grant_id: input.grant_id,
          operation_id: input.operation_id,
          code,
        });
      } catch {
        // Journaling a refusal must never mask the refusal itself.
      }
      throw error;
    }
  }

  private admitChecked(
    envelope: AuthorizationEnvelope,
    input: AdmitOperationInput,
  ): Admission {
    const record = this.grants.loadGrantRecord(envelope, input.grant_id);
    if (!record || record.proof.stage !== 'granted' || record.proof.standing) {
      throw new RunAuthorizationError(
        'RUN_GRANT_NOT_FOUND',
        `No granted run grant ${input.grant_id} exists in this scope. A preview, a standing authorization, or an unknown id admits nothing.`,
        { detail: { grant_id: input.grant_id } },
      );
    }
    if (record.session_id !== input.session_id) {
      throw new RunAuthorizationError(
        'RUN_GRANT_SCOPE_MISMATCH',
        `Run grant ${record.grant_id} is bound to session ${record.session_id}, not ${input.session_id}. A grant never pays for another session.`,
        { detail: { grant_id: record.grant_id, session_id: input.session_id } },
      );
    }
    if (record.proof.installation_id !== envelope.installation_id) {
      throw new RunAuthorizationError(
        'RUN_GRANT_SCOPE_MISMATCH',
        `Run grant ${record.grant_id} is bound to a different installation than the authorization envelope.`,
        { detail: { grant_id: record.grant_id } },
      );
    }
    if (record.status === 'revoked' || record.status === 'exhausted') {
      throw new RunAuthorizationError(
        'RUN_GRANT_INACTIVE',
        `Run grant ${record.grant_id} is ${record.status}. It admits nothing, including replays of an earlier admission.`,
        { detail: { grant_id: record.grant_id, status: record.status } },
      );
    }
    if (record.status === 'expired' || this.grants.expireGrantIfLapsed(envelope, record)) {
      throw new RunAuthorizationError(
        'RUN_GRANT_INACTIVE',
        `Run grant ${record.grant_id} expired at ${record.expires_at}. Expiry fences new admissions; remaining work is resumably blocked, not silently continued.`,
        { detail: { grant_id: record.grant_id, status: 'expired' } },
      );
    }
    if (record.parent_grant_id) {
      const parent = this.grants.loadGrantRecord(envelope, record.parent_grant_id);
      if (!parent || !this.grants.standingParentStands(parent)) {
        throw new RunAuthorizationError(
          'RUN_GRANT_PARENT_INVALID',
          `The standing parent of grant ${record.grant_id} no longer stands (revoked, expired, or missing). The session grant's authority collapses with its parent.`,
          { detail: { grant_id: record.grant_id, standing_parent_grant_id: record.parent_grant_id } },
        );
      }
    }
    const session = this.grants.sessionFor(envelope, input.session_id);
    if (session.state.revocation_generation > record.proof.revocation_epoch) {
      throw new RunAuthorizationError(
        'RUN_GRANT_INACTIVE',
        `Session ${input.session_id} advanced its revocation generation past grant ${record.grant_id}'s epoch. The grant is fenced.`,
        {
          detail: {
            grant_id: record.grant_id,
            grant_revocation_epoch: record.proof.revocation_epoch,
            session_revocation_generation: session.state.revocation_generation,
          },
        },
      );
    }
    if (input.purpose !== undefined && input.purpose !== record.purpose) {
      throw new RunAuthorizationError(
        'RUN_GRANT_PURPOSE_MISMATCH',
        `Operation purpose ${input.purpose} does not match grant ${record.grant_id}'s purpose ${record.purpose}. Inference for one purpose never spends another purpose's allowance (T142).`,
        { detail: { grant_id: record.grant_id, purpose: record.purpose } },
      );
    }
    if (!record.proof.allowed_operation_kinds.includes(input.kind)) {
      throw new RunAuthorizationError(
        'RUN_GRANT_KIND_NOT_ALLOWED',
        `Operation kind ${input.kind} is outside grant ${record.grant_id}'s allowed kinds (${record.proof.allowed_operation_kinds.join(', ')}).`,
        { detail: { grant_id: record.grant_id, kind: input.kind } },
      );
    }
    // Route pin: the operation's snapshot must fingerprint to the
    // exact snapshot the grant was approved against.
    const fingerprint = routeSnapshotFingerprint(input.route_snapshot);
    if (
      record.proof.route_snapshot_fingerprint !== null &&
      fingerprint !== record.proof.route_snapshot_fingerprint
    ) {
      throw new RunAuthorizationError(
        'RUN_GRANT_ROUTE_MISMATCH',
        `The operation's pinned route snapshot does not match grant ${record.grant_id}'s approved route pin. A grant for one route admits nothing on another.`,
        { detail: { grant_id: record.grant_id } },
      );
    }
    const existing = this.budget.getReservation(
      envelope,
      input.session_id,
      input.operation_id,
    );
    if (existing && existing.grant_id !== input.grant_id) {
      throw new RunAuthorizationError(
        'RUN_OPERATION_GRANT_MISMATCH',
        `Operation ${input.operation_id} is already reserved under grant ${existing.grant_id}. An operation never migrates between grants.`,
        { detail: { operation_id: input.operation_id, grant_id: existing.grant_id } },
      );
    }
    const reservation = this.budget.reserve(envelope, {
      session_id: input.session_id,
      operation_id: input.operation_id,
      grant_id: input.grant_id,
      kind: input.kind,
      estimate_minor: input.estimate_minor,
      currency: input.currency ?? null,
      lease_epoch: input.lease_epoch,
      route_snapshot: input.route_snapshot,
      original_operation_id: input.original_operation_id ?? null,
      ceilings: record.proof.ceilings,
    });
    return {
      operation_id: input.operation_id,
      reservation_id: reservation.reservation_id,
      grant_id: input.grant_id,
      session_id: input.session_id,
      kind: input.kind,
      state: reservation.state,
      estimate_minor: reservation.estimate_minor,
      currency: reservation.currency,
      route_snapshot_fingerprint: reservation.route_snapshot_fingerprint,
      revocation_epoch: record.proof.revocation_epoch,
      replayed: existing !== null && existing.reservation_id === reservation.reservation_id,
    };
  }  // --------------------------------------------------------- recordConsumption

  /**
   * Record what an admitted operation actually consumed, through
   * CWE-028's exactly-once finalization. The returned totals are
   * CWE-028's session snapshot for this grant: reconciliation is a
   * direct comparison, because there is only one ledger.
   */
  recordConsumption(
    envelope: AuthorizationEnvelope,
    input: RecordConsumptionInput,
  ): ConsumptionRecord {
    assertEnvelopePurpose(envelope, 'write', 'Consumption recording');
    const existing = this.budget.getReservation(
      envelope,
      input.session_id,
      input.operation_id,
    );
    if (!existing) {
      throw new RunAuthorizationError(
        'RUN_GRANT_NOT_FOUND',
        `No budget reservation for operation ${input.operation_id} exists in session ${input.session_id} in this scope. Consumption is recorded only for admitted operations.`,
        { detail: { operation_id: input.operation_id } },
      );
    }
    if (existing.grant_id !== input.grant_id) {
      throw new RunAuthorizationError(
        'RUN_OPERATION_GRANT_MISMATCH',
        `Operation ${input.operation_id} was admitted under grant ${existing.grant_id}, not ${input.grant_id}. Consumption never migrates between grants.`,
        { detail: { operation_id: input.operation_id, grant_id: existing.grant_id } },
      );
    }
    let finalized: DurableBudgetReservation;
    if (input.outcome === 'settled') {
      if (input.actual_minor === undefined) {
        throw new RunAuthorizationError(
          'RUN_INVALID_INPUT',
          'A settled consumption requires actual_minor.',
          { detail: { operation_id: input.operation_id } },
        );
      }
      finalized = this.budget.settle(envelope, {
        session_id: input.session_id,
        operation_id: input.operation_id,
        lease_epoch: input.lease_epoch,
        actual_minor: input.actual_minor,
      });
    } else {
      finalized = this.budget.markProviderCompletionUnknown(envelope, {
        session_id: input.session_id,
        operation_id: input.operation_id,
        lease_epoch: input.lease_epoch,
      });
    }
    this.grants.markConsumed(envelope, input.grant_id);
    const record = this.grants.loadGrantRecord(envelope, input.grant_id);
    return {
      operation_id: input.operation_id,
      reservation_id: finalized.reservation_id,
      grant_id: input.grant_id,
      state: finalized.state,
      actual_minor: finalized.actual_minor,
      estimate_minor: finalized.estimate_minor,
      currency: finalized.currency,
      grant_status: record ? record.status : 'missing',
      totals: this.budget.snapshot(envelope, input.session_id, input.grant_id),
    };
  }
}
