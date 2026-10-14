/**
 * In-process budget ledger (CWE-004 foundation; service owned by
 * CWE-028). Implements directive Section 15.6 reservation accounting:
 *
 *   available = authorized limit - consumed - outstanding reservations
 *
 * Every actual provider request counts toward the session ceiling of 50,
 * whatever its kind: planned generations, output repairs, transport
 * retries, and semantic verifications share the one hard ceiling
 * (Section 15.9). Repairs and retries additionally have their own
 * ceilings. A request whose provider completion is unknown keeps its
 * reservation; it is never released as though it were free, and unknown
 * usage is never reported as zero.
 */

import type { CouncilSettings } from '../contracts/index.js';
import { DEFAULT_COUNCIL_SETTINGS } from '../contracts/index.js';
import { CouncilError } from './errors.js';
import type {
  BudgetLedger,
  BudgetReservation,
  BudgetSnapshot,
} from './host-ports.js';

interface OperationRecord {
  reservation: BudgetReservation;
  state: 'reserved' | 'committed' | 'released' | 'unknown';
}

export class InProcessBudgetLedger implements BudgetLedger {
  private readonly settings: CouncilSettings;
  private readonly operations = new Map<string, OperationRecord>();

  constructor(settings: CouncilSettings = DEFAULT_COUNCIL_SETTINGS) {
    this.settings = settings;
  }

  private ceilings() {
    return {
      max_provider_requests: this.settings.max_session_provider_requests,
      max_output_repairs: this.settings.max_output_repair_requests,
      max_transport_retries: this.settings.max_transport_retries_total,
      max_semantic_verifications:
        this.settings.max_semantic_verification_requests,
    };
  }

  private sessionRecords(sessionId: string): OperationRecord[] {
    return [...this.operations.values()].filter(
      (r) => r.reservation.session_id === sessionId,
    );
  }

  reserve(input: {
    session_id: string;
    operation_key: string;
    kind: BudgetReservation['kind'];
  }): BudgetReservation {
    const existing = this.operations.get(input.operation_key);
    if (existing && existing.state !== 'released') {
      return existing.reservation; // idempotent re-reserve of the same operation
    }
    const records = this.sessionRecords(input.session_id);
    const ceilings = this.ceilings();
    const spentOrHeld = records.filter(
      (r) => r.state === 'committed' || r.state === 'reserved' || r.state === 'unknown',
    ).length;
    if (spentOrHeld + 1 > ceilings.max_provider_requests) {
      throw new CouncilError(
        'COUNCIL_BUDGET_EXHAUSTED',
        `Session ${input.session_id} has reached its provider request ceiling of ${ceilings.max_provider_requests}. No further requests can be reserved.`,
        {
          retryable: false,
          action:
            'Review the session usage, or start a separately authorized session with its own envelope.',
          exitCode: 3,
        },
      );
    }
    const kindCount = records.filter(
      (r) =>
        r.reservation.kind === input.kind &&
        (r.state === 'committed' || r.state === 'reserved' || r.state === 'unknown'),
    ).length;
    const kindCeiling =
      input.kind === 'output_repair'
        ? ceilings.max_output_repairs
        : input.kind === 'transport_retry'
          ? ceilings.max_transport_retries
          : input.kind === 'semantic_verification'
            ? ceilings.max_semantic_verifications
            : ceilings.max_provider_requests;
    if (kindCount + 1 > kindCeiling) {
      throw new CouncilError(
        'COUNCIL_BUDGET_EXHAUSTED',
        `Session ${input.session_id} has reached its ${input.kind} ceiling of ${kindCeiling}.`,
        {
          retryable: false,
          action: 'Continue with the completed work, or record a partial result honestly.',
          exitCode: 3,
        },
      );
    }
    const reservation: BudgetReservation = {
      operation_key: input.operation_key,
      session_id: input.session_id,
      kind: input.kind,
    };
    this.operations.set(input.operation_key, { reservation, state: 'reserved' });
    return reservation;
  }

  commit(reservation: BudgetReservation): void {
    const record = this.operations.get(reservation.operation_key);
    if (record) record.state = 'committed';
  }

  release(reservation: BudgetReservation): void {
    const record = this.operations.get(reservation.operation_key);
    if (record && record.state === 'reserved') record.state = 'released';
  }

  markProviderCompletionUnknown(reservation: BudgetReservation): void {
    const record = this.operations.get(reservation.operation_key);
    if (record) record.state = 'unknown';
  }

  snapshot(session_id: string): BudgetSnapshot {
    const records = this.sessionRecords(session_id);
    const count = (
      kind: BudgetReservation['kind'],
      states: Array<OperationRecord['state']>,
    ) =>
      records.filter(
        (r) => r.reservation.kind === kind && states.includes(r.state),
      ).length;
    const active: Array<OperationRecord['state']> = ['committed', 'unknown'];
    return {
      session_id,
      ceilings: this.ceilings(),
      consumed: {
        provider_requests: records.filter((r) =>
          ['committed', 'unknown'].includes(r.state),
        ).length,
        output_repairs: count('output_repair', active),
        transport_retries: count('transport_retry', active),
        semantic_verifications: count('semantic_verification', active),
      },
      reserved: records.filter((r) => r.state === 'reserved').length,
      unknown: records.filter((r) => r.state === 'unknown').length,
    };
  }
}
