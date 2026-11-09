/**
 * Durable queue and worker scheduling barrel.
 *
 * capacity.ts is CWE-028's runtime capacity admission (consumed, not
 * owned, by CWE-027). runner.ts and workers.ts are CWE-027's durable
 * deliberation job runner and worker supervision, built against
 * CWE-006's scoped store, CWE-028's budget and capacity services, and
 * CWE-049's run admission.
 *
 * TWO producers live in this slice. They coexist; neither is the
 * "primary" or "only" one, and picking between them is a caller
 * decision about which durable record must exist:
 *
 * - `DurableOperationProducer` (./producer.ts) owns REQUEST-KEYED
 *   admission. Caller supplies its own idempotency key, which is
 *   recorded in council_request_keys as the canonical idempotency
 *   registry, and then drives the leased worker lifecycle:
 *   claimOperation, releaseLease, recordDispatchIntent,
 *   recordResponseObserved, recordAcceptedResult. Its receipt is the
 *   canonical OperationReceipt projection. Use it for worker-driven
 *   execution.
 * - `OperationProducer` (./operation-producer.ts) owns the
 *   OperationAdmissionReceipt committed inside the job payload at
 *   admission. Caller addresses the operation by the deterministic
 *   operation identity (session, attempt, phase_job_key,
 *   input_sha256) and gets the receipt back by that same identity:
 *   admission-fingerprint conflict law, non-resetting
 *   attempt_ordinal and lease_generation, explicit-null mutable
 *   commits with receipt-level fencing, and readmission of a QUEUED
 *   session that has no durable job. Use it when the receipt itself
 *   must be the durable business record.
 *
 * Both build on the same substrate (CouncilJobs, the journal, the
 * outbox, transitionState), the same operation-identity derivation, and
 * the same one-transaction admission law. They do not duplicate the
 * scheduler: neither claims, executes, or dispatches work.
 *
 * CostKnowledge and RetryDisposition are declared in ./producer.ts and
 * are the shared vocabulary for both producers; the receipted producer
 * re-exports its own copies through its module, so they are not
 * re-exported again here (that would be an ambiguous star export).
 */
export * from './capacity.js';
export * from './errors.js';
export * from './producer.js';
export {
  OperationProducer,
  ProducerStateConflict,
  RECEIPT_STATE_EVENT_TYPES,
  RECEIPT_STATE_TO_JOB_STATE,
  type AdmitOperationRequest,
  type AdmitOperationResult,
  type OperationAdmissionReceipt,
  type OperationProducerDeps,
  type ReceiptStateLabel,
} from './operation-producer.js';
export * from './runner.js';
export * from './workers.js';
