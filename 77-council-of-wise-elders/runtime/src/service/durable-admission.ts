/**
 * The composed durable admission sink (W25-U001 Lane E).
 *
 * The front door forwards one bounded admission request to the owning
 * authority; this module is that authority for a composed standalone
 * service. It is a thin adapter over the canonical durable producer
 * (`queue/producer.ts`), never a second queue:
 *
 *   POST /api/council/admissions
 *     -> AdmissionRequest { session_id, operation_id, payload }
 *     -> DurableOperationProducer.admitOperation(envelope, AdmissionCommand)
 *     -> one transaction: request key, optional session transition,
 *        council_jobs row, `operation_reserved` journal event, outbox intent
 *
 * The payload carries the operator-supplied command fields the front door
 * cannot invent: the granted run id, the frozen route snapshot hash, the
 * input hash and the reservation. A missing or malformed payload is a
 * typed refusal; the service never fabricates a grant, a hash, a
 * reservation or a session to make an admission succeed.
 */

import type { SeatId } from '../contracts/index.js';
import {
  DurableOperationProducer,
  type AdmissionCommand,
  type AdmissionResult,
  type OperationReservation,
} from '../queue/producer.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import type { AdmissionRequest, AdmissionSink } from './types.js';

/** The payload keys the sink requires before the producer validates types. */
export const REQUIRED_ADMISSION_PAYLOAD_FIELDS = [
  'operation_kind',
  'purpose',
  'input_hash',
  'route_snapshot_hash',
  'grant_id',
  'reservation',
] as const;

export interface DurableAdmissionSinkOptions {
  producer: DurableOperationProducer;
  /** The owner/worker write envelope this installation acts under. */
  envelope: AuthorizationEnvelope;
}

/** Typed refusal for a front-door payload that cannot be mapped honestly. */
export class DurableAdmissionError extends Error {
  readonly code = 'ADMISSION_COMMAND_INCOMPLETE';
  readonly retryable = false;
  constructor(missing: readonly string[]) {
    super(
      `The admission payload is missing required durable command field(s): ${missing.join(
        ', ',
      )}. The service does not invent a grant, hash, reservation or session.`,
    );
    this.name = 'DurableAdmissionError';
  }
}

function payloadOf(request: AdmissionRequest): Readonly<Record<string, unknown>> {
  const payload = request.payload;
  if (payload === undefined || payload === null || typeof payload !== 'object') {
    throw new DurableAdmissionError(REQUIRED_ADMISSION_PAYLOAD_FIELDS);
  }
  return payload;
}

function missingFields(payload: Readonly<Record<string, unknown>>): string[] {
  return REQUIRED_ADMISSION_PAYLOAD_FIELDS.filter((field) => {
    const value = payload[field];
    return value === undefined || value === null || value === '';
  });
}

/**
 * Map one front-door request onto the canonical command. The request's
 * session_id and operation_id are the identity; every other field comes
 * from the caller's payload and is validated by the producer itself.
 */
export function admissionCommandFromRequest(
  request: AdmissionRequest,
  payload: Readonly<Record<string, unknown>>,
): AdmissionCommand {
  return {
    sessionId: request.session_id,
    idempotencyKey: request.operation_id,
    operationKind: payload.operation_kind as AdmissionCommand['operationKind'],
    purpose: payload.purpose as string,
    inputHash: payload.input_hash as string,
    routeSnapshotHash: payload.route_snapshot_hash as string,
    grantId: payload.grant_id as string,
    packHash: (payload.pack_hash ?? null) as string | null,
    round: (payload.round ?? null) as number | null,
    seatId: (payload.seat_id ?? null) as SeatId | null,
    ownerId: typeof payload.owner_id === 'string' ? payload.owner_id : undefined,
    reservation: payload.reservation as OperationReservation,
    transition: payload.transition as AdmissionCommand['transition'],
  };
}

/** Build the canonical durable admission sink bound to one producer. */
export function createDurableAdmissionSink(
  options: DurableAdmissionSinkOptions,
): AdmissionSink {
  return (request: AdmissionRequest): AdmissionResult => {
    const payload = payloadOf(request);
    const missing = missingFields(payload);
    if (missing.length > 0) throw new DurableAdmissionError(missing);
    return options.producer.admitOperation(
      options.envelope,
      admissionCommandFromRequest(request, payload),
    );
  };
}
