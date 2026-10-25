/**
 * Durable deliberation job runner (CWE-027, directive Sections 15, 16,
 * 18, 29 and 34 CWE-027). This module produces the graph artifact
 * `durable-worker-and-operation-leases`.
 *
 * What this is: the durable scheduling layer between the accepted
 * foundations and the round logic. CWE-024/CWE-025 (composed at
 * CWE-050) decide WHAT a session's operations are; this runner owns
 * HOW they run durably: workers claim operation jobs from CWE-006's
 * scoped store (council_jobs), execute them under council operation
 * leases, admit every provider dispatch through CWE-049's
 * RunAdmissionService (budget reservations only from CWE-028's one
 * DurableBudgetService; this module keeps no ledger of its own), and
 * commit accepted cards only through CWE-006's fenced acceptCard.
 * Per Section 34.3, CWE-028 supplies the single budget service and
 * CWE-049 the purpose-bound grant admission; durable scheduling is
 * built against those real services and a controlled operation
 * callback (the OperationExecutorPort below), without waiting for
 * CWE-024's openings. queue/capacity.ts is CWE-028's and is consumed,
 * never modified, here.
 *
 * Two lease layers, deliberately separate (Section 15.8, binding B05):
 * - The HOST scheduler lease (observed runLeasedJob default 90s) is a
 *   short maintenance/admission wakeup only. No council operation ever
 *   runs inside it. A provider call longer than 90 seconds is governed
 *   by the council operation lease below, never killed by the host
 *   lease (T156).
 * - The COUNCIL operation lease: TTL 60s, heartbeat every 15s, held on
 *   the durable job row (lease_owner, lease_epoch, lease_expires_at)
 *   and paired with a session fencing generation: claiming a job bumps
 *   the session state record's lease_epoch (the epoch CWE-028's budget
 *   service and CWE-049's admission fence on, and one third of
 *   CWE-006's acceptCard commit fence). A worker may commit only while
 *   lease owner, job epoch, session epoch, state version (read fresh
 *   at commit), and cancellation generation all remain current.
 *
 * Self-fencing (T157): the host's throwIfJobLeaseLost() returns
 * immediately when no AsyncLocalStorage job context exists, so it
 * proves nothing for a council worker. This runner never consults host
 * job context. Before EVERY protected commit (card commit, job
 * finish) the worker re-reads the durable job row and session record
 * and checks its own fence (assertFenceCurrent): owner, job epoch,
 * session epoch, cancellation generation. A worker with no host
 * context fences itself from durable state alone.
 *
 * Crash honesty (Sections 15.2, 15.3, 15.9): network calls never run
 * inside a store transaction; every store write here is a short
 * transaction through the composed services. The durable trail of an
 * operation is: job row (claim), budget reservation (admission),
 * attempt-ledger row (council_provider_attempts), validated checkpoint
 * (CWE-006 CouncilJobs), committed card (acceptCard). A crash leaves
 * some prefix of that trail; recovery (recoverExpiredLease) reads the
 * trail and resolves it truthfully:
 * - card committed or checkpoint accepted: the work is done; the job
 *   finishes succeeded and the unrecorded charge is marked UNKNOWN
 *   (counted at estimate, never zero, never invented). Completed
 *   inference is never repeated (T049).
 * - attempt dispatched, no card: provider completion is UNKNOWN. The
 *   reservation is marked unknown through recordConsumption, the
 *   checkpoint records provider_completion_unknown, and the job ends
 *   failed with that reason. It is NEVER auto-replayed (T050).
 * - admitted but never dispatched: the reservation is released (it was
 *   never dispatched, the one case CWE-028 release exists for) and the
 *   job returns to queued.
 * - claimed but never admitted: the job returns to queued.
 * Counters never reset: transport retries and output repairs are
 * separate admitted operations (kinds transport_retry and
 * output_repair, each with original_operation_id) in CWE-028's one
 * ledger, so their ceilings (8 total retries, 1 per original; repairs
 * inside the session envelope, 1 per original; 50 total requests) are
 * enforced across resumption, renewal, and worker changes by the
 * ledger itself (T066). Lease renewal touches no counter and no grant.
 *
 * Transport outcome law (the executor port contract): a dispatch error
 * flagged retryable asserts the provider did NOT accept the request
 * (a transport-level failure before acceptance). Only then may the
 * runner release that attempt's reservation and admit one
 * transport_retry for the same logical operation. An error flagged
 * unknownCompletion, a provider-deadline overrun, or an ambiguous
 * failure is provider completion unknown: never replayed, reservation
 * retained at estimate. A definite rejection settles at the reported
 * actual charge and fails the operation.
 *
 * Session controls (Section 15.4, runner half of T055): pause stops
 * new dispatch and lets in-flight work finish within its deadline;
 * resume returns to the recorded resume phase with the same pinned
 * route and limits (they live in the grant and session spec, which
 * pause never touches, T054); cancel increments the cancellation
 * generation immediately, fences late results out of every commit, and
 * leaves CANCELLED terminal with usage reconciled (Section 29).
 * Pause and cancel are idempotent at their targets; an illegal control
 * is a precise JOB_CONTROL_CONFLICT naming the current state.
 *
 * Control transitions use the canonical assertTransition table and
 * CWE-006's compare-and-swap state writer directly, because the
 * record's resume_phase must be the phase the session was in BEFORE
 * PAUSE_REQUESTED (the CWE-004 engine's own pause does the same record
 * override through its store port). repositories.transitionState is
 * not used for the two-step pause: entering PAUSED through it records
 * resume_phase as PAUSE_REQUESTED, a state the resume legality rule
 * can never target. This divergence is named for CWE-050 in the build
 * report; legality, CAS discipline, event types, and journaling are
 * identical to the repository path.
 */

import {
  assertTransition,
  canonicalHash,
  canonicalStringify,
  validateCard,
  type Clock,
  type CouncilCard,
  type CouncilEventType,
  type IdSource,
  type JobCheckpoint,
  type SeatId,
  type SessionState,
  type SessionStateRecord,
} from '../contracts/index.js';
import type { RunAdmissionService } from '../authorization/admission.js';
import type { RunAuthorizationService } from '../authorization/run-grants.js';
import {
  DurableBudgetService,
  type BudgetReservationKind,
  type PinnedRouteSnapshot,
} from '../budgets/index.js';
import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import { PersistenceError } from '../persistence/errors.js';
import { CouncilJobs, type JobRecord } from '../persistence/jobs.js';
import type { CouncilRepositories } from '../persistence/repositories.js';
import type { CouncilDatabase } from '../persistence/sqlite.js';
import type { StoredSession } from '../cli/host-ports.js';
import { NOT_JSON_ISSUE } from '../cli/card-contract.js';
import { RuntimeCapacity, type CapacityToken } from './capacity.js';
import {
  JobRunnerError,
  SimulatedCrashError,
  isSimulatedCrash,
} from './errors.js';

export { SimulatedCrashError, isSimulatedCrash };

// ------------------------------------------------------------ constants

/**
 * Council operation lease TTL (60 seconds) and heartbeat cadence
 * (15 seconds), Section 15.8: the canonical constants are CWE-004's
 * (cli/leases.ts, the in-process form of the same lease); they are
 * re-exported here, never redefined, so the two forms cannot drift.
 */
export {
  OPERATION_LEASE_TTL_MS,
  OPERATION_LEASE_HEARTBEAT_MS,
} from '../cli/leases.js';
import {
  OPERATION_LEASE_TTL_MS,
  OPERATION_LEASE_HEARTBEAT_MS,
} from '../cli/leases.js';
/**
 * The host scheduler's observed short lease (runLeasedJob default,
 * binding B05). Named here only to keep the two layers distinct in
 * code and tests: no council operation is ever bounded by it (T156).
 */
export const HOST_SCHEDULER_LEASE_MS = 90_000;
/** Default provider deadline per operation (Section 15.8). */
export const DEFAULT_PROVIDER_DEADLINE_MS = 600_000;
/** Default idle poll interval for runnable work (Section 15.8). */
export const DEFAULT_POLL_INTERVAL_MS = 1_000;

const RUNNABLE_STATES: ReadonlySet<SessionState> = new Set([
  'QUEUED',
  'PREPARING',
  'ROUND_1',
  'CRUX_REVIEW',
  'ROUND_2',
  'DRAFT_RESOLUTION',
  'ROUND_3',
  'CONSULTING',
  'VERIFYING',
]);

// ---------------------------------------------------------------- timers

/**
 * Time port for the runner's asynchronous waits (heartbeat cadence,
 * provider deadline). The synchronous clock is the contracts Clock
 * shared with every composed service, so lease math and budget holds
 * read one time source; this port only schedules callbacks. Tests
 * inject a manual implementation and advance it deterministically.
 */
export interface RunnerTimers {
  every(ms: number, fn: () => void): () => void;
  delay(ms: number): Promise<void>;
}

export const systemTimers: RunnerTimers = {
  every(ms, fn) {
    const handle = setInterval(fn, ms);
    handle.unref?.();
    return () => clearInterval(handle);
  },
  delay(ms) {
    return new Promise((resolve) => {
      const handle = setTimeout(resolve, ms);
      handle.unref?.();
    });
  },
};

// ------------------------------------------------------- executor port

/**
 * A transport-level dispatch failure, as reported by the executor
 * port. The flags carry the honesty contract the runner acts on:
 * - retryable: the provider did NOT accept the request; safe to admit
 *   one bounded transport retry. Never set when acceptance is unsure.
 * - unknownCompletion: the request may have completed provider-side;
 *   the outcome is unknown and must never be replayed.
 * Neither flag set: a definite rejection; settles at actual_minor.
 */
export class TransportDispatchError extends Error {
  readonly code = 'TRANSPORT_DISPATCH_FAILED';
  readonly retryable: boolean;
  readonly unknownCompletion: boolean;
  readonly actual_minor: number;
  constructor(
    message: string,
    options: {
      retryable?: boolean;
      unknownCompletion?: boolean;
      actual_minor?: number;
    } = {},
  ) {
    super(message);
    this.name = 'TransportDispatchError';
    this.retryable = options.retryable ?? false;
    this.unknownCompletion = options.unknownCompletion ?? false;
    this.actual_minor = options.actual_minor ?? 0;
  }
}

export type DispatchAttemptKind = 'initial' | 'transport_retry' | 'output_repair';

export interface OperationDispatchContext {
  session: StoredSession;
  claim: JobClaim;
  /** The admitted operation id for THIS dispatch (retry/repair have their own). */
  dispatch_operation_id: string;
  attempt_kind: DispatchAttemptKind;
  /** Validation issues from the previous output, for output_repair dispatches. */
  repair_issues: string[];
  /**
   * Aborted when the runner gives up on this dispatch (provider deadline),
   * so the executor can kill its harness child instead of leaving it to
   * overlap the next seat. Executors pass it to transport.generate.
   */
  signal?: AbortSignal;
}

export interface OperationDispatchResult {
  /** The card author payload, WITHOUT the host stamp (the runner stamps). */
  author: Record<string, unknown>;
  /** Why the reply did not parse into an author payload (author is then {}). */
  parse_error?: string;
  provider_request_id: string | null;
  /** The actual charge for this dispatch, in minor units. */
  actual_minor: number;
  input_tokens: number | null;
  output_tokens: number | null;
  source_status?: 'verified' | 'unverified' | 'not_applicable';
}

/**
 * The controlled operation callback Section 34.3 names: CWE-024 and
 * CWE-025 implement this port (round logic, brief-bound validation,
 * real transports); the runner supplies durability, admission, leases,
 * and commit fencing. The port performs the provider call and returns
 * the unstamped author payload plus accounting facts. It must never
 * commit anything itself, and it runs outside every store transaction.
 */
export interface OperationExecutorPort {
  dispatch(ctx: OperationDispatchContext): Promise<OperationDispatchResult>;
  /**
   * Optional deeper validation of a stamped card (for example against
   * the frozen brief). Returns issue strings; empty means valid. The
   * runner always applies the canonical validateCard as well; failure
   * of either enters the bounded output-repair path.
   */
  validateCard?(ctx: OperationDispatchContext, card: CouncilCard): string[];
}

// ------------------------------------------------------------ job model

/**
 * The durable dispatch descriptor for one logical operation, stored in
 * the job row's payload alongside CWE-006's JobPayload fields (which
 * are preserved untouched). It is written once at enqueue and is part
 * of the job's identity: re-enqueueing the same operation identity
 * with a different descriptor is a JOB_DESCRIPTOR_CONFLICT.
 */
export interface OperationDescriptor {
  kind: BudgetReservationKind;
  /** Admission purpose; must equal the grant's purpose binding. */
  purpose: string;
  grant_id: string;
  estimate_minor: number;
  currency?: string | null;
  /** For jobs that are themselves a repair/retry of another operation. */
  original_operation_id?: string | null;
  round: number;
  pack_version?: string | null;
  model_policy_revision?: number;
}

export interface EnqueueOperationInput {
  session_id: string;
  phase_job_key: string;
  seat_id: SeatId | null;
  input_sha256: string;
  descriptor: OperationDescriptor;
  /** The pinned route snapshot every dispatch of this job charges against. */
  route_snapshot: PinnedRouteSnapshot;
}

interface StoredJobPayload {
  attempt: number;
  brief_revision: number;
  phase_job_key: string;
  seat_id: string | null;
  input_sha256: string;
  cancel_generation: number;
  result_ref?: string;
  runner?: OperationDescriptor & { route_snapshot: PinnedRouteSnapshot };
}

interface JobRowFull {
  id: string;
  session_id: string | null;
  state: JobRecord['state'];
  lease_epoch: number;
  lease_owner: string | null;
  lease_expires_at: string | null;
  payload_json: string;
}

/**
 * A worker's claim on one operation job: the job identity, the job
 * lease (owner + epoch), and the session fencing generation the claim
 * established. Every admission, consumption, checkpoint, and commit
 * the worker makes presents this claim's epochs.
 */
export interface JobClaim {
  job: JobRecord;
  operation_id: string;
  seat_id: SeatId | null;
  worker_id: string;
  /** The job row's lease epoch under this claim. */
  job_lease_epoch: number;
  /** The session fencing generation this claim bumped the record to. */
  session_lease_epoch: number;
  /** The cancellation generation captured at claim time. */
  cancel_generation: number;
  state_version_at_claim: number;
  descriptor: OperationDescriptor;
  route_snapshot: PinnedRouteSnapshot;
}

export interface FenceSnapshot {
  job_lease_epoch: number;
  session_lease_epoch: number;
  cancel_generation: number;
  session_state_version: number;
  session_state: SessionState;
}

export type OperationOutcomeStatus =
  | 'committed'
  | 'already_committed'
  | 'provider_completion_unknown'
  | 'failed'
  | 'cancelled'
  | 'deferred'
  | 'admission_refused'
  | 'fenced';

export interface OperationOutcome {
  status: OperationOutcomeStatus;
  operation_id: string;
  /** Machine-readable cause for non-committed outcomes. */
  reason: string | null;
  /** The committed card, for 'committed' and 'already_committed'. */
  card: CouncilCard | null;
}

export interface RecoveryOutcome {
  job_id: string;
  operation_id: string;
  outcome:
    | 'recovered_committed'
    | 'recovered_unknown'
    | 'recovered_requeued'
    | 'recovered_cancelled';
}

function operationKey(
  sessionId: string,
  attempt: number,
  phaseJobKey: string,
  inputSha256: string,
): string {
  // Identical derivation to CWE-006 CouncilJobs: the admission
  // operation id IS the job's idempotency key, so the job row, the
  // budget reservation, the attempt ledger, and the card host stamp
  // all name one operation with one string.
  return canonicalHash({
    session_id: sessionId,
    attempt,
    phase_job_key: phaseJobKey,
    input_sha256: inputSha256,
  });
}

function controlEventType(to: SessionState): CouncilEventType {
  return to === 'PAUSED'
    ? 'session_paused'
    : to === 'CANCELLED'
      ? 'session_cancelled'
      : to === 'BLOCKED'
        ? 'session_blocked'
        : to === 'FAILED'
          ? 'session_failed'
          : 'session_state_changed';
}

// ---------------------------------------------------------------- runner

export interface DurableJobRunnerDeps {
  db: CouncilDatabase;
  repositories: CouncilRepositories;
  jobs: CouncilJobs;
  budget: DurableBudgetService;
  admission: RunAdmissionService;
  grants: RunAuthorizationService;
  clock: Clock;
  ids: IdSource;
  executor: OperationExecutorPort;
  timers?: RunnerTimers;
  /** CWE-028 runtime capacity admission; optional composition. */
  capacity?: RuntimeCapacity;
  leaseTtlMs?: number;
  heartbeatMs?: number;
  /** Route-specific deadline when known; default 600s (Section 15.8). */
  providerDeadlineMs?: number;
  /**
   * Called when a paid response is discarded because the settle was
   * fenced (a newer lease epoch, or a revoked grant). Never swallowed:
   * the host logs and journals it. A throw here is ignored.
   */
  onFencedSettle?: (error: JobRunnerError, context: { session_id: string }) => void;
}

export class DurableJobRunner {
  private readonly db: CouncilDatabase;
  private readonly repositories: CouncilRepositories;
  private readonly jobs: CouncilJobs;
  private readonly budget: DurableBudgetService;
  private readonly admission: RunAdmissionService;
  private readonly grants: RunAuthorizationService;
  private readonly clock: Clock;
  private readonly ids: IdSource;
  private readonly executor: OperationExecutorPort;
  private readonly timers: RunnerTimers;
  private readonly capacity: RuntimeCapacity | null;
  private readonly leaseTtlMs: number;
  private readonly heartbeatMs: number;
  private readonly providerDeadlineMs: number;
  private readonly onFencedSettle: DurableJobRunnerDeps['onFencedSettle'];
  private readonly capacityTokens = new Map<string, CapacityToken>();

  constructor(deps: DurableJobRunnerDeps) {
    this.db = deps.db;
    this.repositories = deps.repositories;
    this.jobs = deps.jobs;
    this.budget = deps.budget;
    this.admission = deps.admission;
    this.grants = deps.grants;
    this.clock = deps.clock;
    this.ids = deps.ids;
    this.executor = deps.executor;
    this.timers = deps.timers ?? systemTimers;
    this.capacity = deps.capacity ?? null;
    this.onFencedSettle = deps.onFencedSettle;
    this.leaseTtlMs = deps.leaseTtlMs ?? OPERATION_LEASE_TTL_MS;
    this.heartbeatMs = deps.heartbeatMs ?? OPERATION_LEASE_HEARTBEAT_MS;
    this.providerDeadlineMs = deps.providerDeadlineMs ?? DEFAULT_PROVIDER_DEADLINE_MS;
  }

  private nowIso(): string {
    return this.clock.nowUtc();
  }

  private nowMs(): number {
    return Date.parse(this.clock.nowUtc());
  }

  private scopeKey(envelope: AuthorizationEnvelope, sessionId: string): string {
    return `${envelope.tenant_id}:${envelope.company_id}:${envelope.installation_id}:${sessionId}`;
  }

  private jobRow(
    envelope: AuthorizationEnvelope,
    jobId: string,
  ): JobRowFull | null {
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT id, session_id, state, lease_epoch, lease_owner,
                  lease_expires_at, payload_json
             FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND kind = 'operation'`,
        )
        .get(envelope.tenant_id, envelope.company_id, jobId),
    ) as JobRowFull | undefined;
    return row ?? null;
  }

  private sessionOrThrow(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): StoredSession {
    const session = this.repositories.getSession(envelope, sessionId);
    if (!session) {
      throw new JobRunnerError(
        'JOB_SESSION_NOT_FOUND',
        `No council session ${sessionId} exists in this scope (or it is not visible to this envelope).`,
        { detail: { session_id: sessionId } },
      );
    }
    return session;
  }

  // ------------------------------------------------------------ enqueue

  /**
   * Enqueue one logical operation for a session. Idempotent per
   * operation identity (session, attempt, phase, input hash): the same
   * identity always resolves to the same durable job. The dispatch
   * descriptor is stored with the job; the same identity with a
   * different descriptor is a conflict, never a silent overwrite.
   */
  enqueueOperation(
    envelope: AuthorizationEnvelope,
    input: EnqueueOperationInput,
  ): JobRecord {
    const session = this.sessionOrThrow(envelope, input.session_id);
    const job = this.jobs.claimJob(envelope, {
      sessionId: input.session_id,
      attempt: session.state.attempt,
      briefRevision: session.state.brief_revision,
      phaseJobKey: input.phase_job_key,
      inputSha256: input.input_sha256,
      cancelGeneration: session.state.cancel_generation,
      seatId: input.seat_id,
    });
    const descriptor: OperationDescriptor & { route_snapshot: PinnedRouteSnapshot } = {
      ...input.descriptor,
      route_snapshot: input.route_snapshot,
    };
    this.db.write((handle) => {
      const row = handle
        .prepare(
          `SELECT payload_json FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND id = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, job.id) as
        | { payload_json: string }
        | undefined;
      if (!row) {
        throw new JobRunnerError('JOB_NOT_FOUND', `Job ${job.id} vanished during enqueue.`);
      }
      const payload = JSON.parse(row.payload_json) as StoredJobPayload;
      if (payload.runner) {
        if (canonicalStringify(payload.runner) !== canonicalStringify(descriptor)) {
          throw new JobRunnerError(
            'JOB_DESCRIPTOR_CONFLICT',
            `Operation ${job.id} was already enqueued with a different dispatch descriptor. The same operation identity with different dispatch meaning is a caller bug, not a re-enqueue.`,
            { detail: { job_id: job.id } },
          );
        }
        return;
      }
      payload.runner = descriptor;
      handle
        .prepare(
          `UPDATE council_jobs SET payload_json = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND state = 'queued'`,
        )
        .run(
          canonicalStringify(payload),
          this.nowIso(),
          envelope.tenant_id,
          envelope.company_id,
          job.id,
        );
    });
    return job;
  }

  /** Sessions visible to the envelope, newest first (worker scans). */
  listSessions(envelope: AuthorizationEnvelope): StoredSession[] {
    return this.repositories.listSessions(envelope, {});
  }

  /** All operation jobs of a session, oldest first. */
  listSessionJobs(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): Array<JobRecord & { lease_owner: string | null; lease_expires_at: string | null }> {
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT id, session_id, state, lease_epoch, lease_owner,
                  lease_expires_at, payload_json
             FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND kind = 'operation'
            ORDER BY created_at ASC, id ASC`,
        )
        .all(envelope.tenant_id, envelope.company_id, sessionId),
    ) as JobRowFull[];
    return rows.map((row) => {
      const payload = JSON.parse(row.payload_json) as StoredJobPayload;
      return {
        id: row.id,
        session_id: sessionId,
        attempt: payload.attempt,
        phase_job_key: payload.phase_job_key,
        input_sha256: payload.input_sha256,
        state: row.state,
        lease_epoch: row.lease_epoch,
        cancel_generation: payload.cancel_generation,
        brief_revision: payload.brief_revision,
        lease_owner: row.lease_owner,
        lease_expires_at: row.lease_expires_at,
      };
    });
  }

  /** Failed operation jobs of a session, oldest first: the seat and the code it ended with. */
  listSessionFailures(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): Array<{ seat_id: string | null; phase_job_key: string; outcome_code: string | null }> {
    const rows = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT payload_json, terminal_reason
             FROM council_jobs
            WHERE tenant_id = ? AND company_id = ? AND session_id = ?
              AND kind = 'operation' AND state IN ('failed', 'dead_letter')
            ORDER BY created_at ASC, id ASC`,
        )
        .all(envelope.tenant_id, envelope.company_id, sessionId),
    ) as Array<{ payload_json: string; terminal_reason: string | null }>;
    return rows.map((row) => {
      const payload = JSON.parse(row.payload_json) as StoredJobPayload;
      return {
        seat_id: payload.seat_id,
        phase_job_key: payload.phase_job_key,
        outcome_code: row.terminal_reason,
      };
    });
  }

  // -------------------------------------------------------------- claim

  /**
   * Claim the session's next runnable operation job for a worker.
   * Returns null when nothing is claimable (no queued job, the session
   * is not runnable, or a live lease already owns the work): a null
   * return IS the rejected claim of T051, never an exception, because
   * losing a claim race is normal operation. The claim is atomic: the
   * job row compare-and-swap (queued, or expired lease after recovery)
   * admits exactly one worker, and the session fencing generation is
   * bumped so every token the previous owner held goes stale.
   */
  claimNextOperation(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    workerId: string,
  ): JobClaim | null {
    let session = this.sessionOrThrow(envelope, sessionId);
    if (!RUNNABLE_STATES.has(session.state.state)) return null;
    const candidates = this.listSessionJobs(envelope, sessionId);
    // One live lease per session: every claim raises the session fencing
    // generation, so claiming while an operation is in flight would fence
    // that operation's settle and lose its paid response. Wait for the
    // live lease to end or expire (T051).
    const now = this.nowMs();
    const live = candidates.some(
      (c) =>
        (c.state === 'leased' || c.state === 'running') &&
        (c.lease_expires_at === null || Date.parse(c.lease_expires_at) > now),
    );
    if (live) return null;
    for (const candidate of candidates) {
      if (candidate.state === 'leased' || candidate.state === 'running') {
        if (
          candidate.lease_expires_at !== null &&
          Date.parse(candidate.lease_expires_at) <= this.nowMs() &&
          candidate.lease_owner !== workerId
        ) {
          // A dead or stalled worker's lease: reconcile its durable
          // trail first. Recovery may finish the job, fail it as
          // provider-unknown, or return it to queued for this claim.
          this.recoverExpiredLease(envelope, candidate.id, workerId);
        }
        continue;
      }
      if (candidate.state !== 'queued') continue;
      const fresh = this.jobRow(envelope, candidate.id);
      if (!fresh || fresh.state !== 'queued') continue;
      const payload = JSON.parse(fresh.payload_json) as StoredJobPayload;
      if (!payload.runner) continue;
      if (payload.cancel_generation !== session.state.cancel_generation) {
        // Written under a superseded cancellation generation: it can
        // never run. Retire it in place rather than stranding it.
        this.retireSupersededJob(envelope, candidate.id);
        continue;
      }
      const claimed = this.db.write((handle) => {
        const expires = new Date(this.nowMs() + this.leaseTtlMs).toISOString();
        const result = handle
          .prepare(
            `UPDATE council_jobs
                SET state = 'leased', lease_owner = ?, lease_epoch = lease_epoch + 1,
                    lease_expires_at = ?, attempt_count = attempt_count + 1,
                    updated_at = ?
              WHERE tenant_id = ? AND company_id = ? AND id = ? AND state = 'queued'`,
          )
          .run(workerId, expires, this.nowIso(), envelope.tenant_id, envelope.company_id, candidate.id);
        return Number(result.changes) === 1;
      });
      if (!claimed) continue; // lost the race to another worker
      const claimedRow = this.jobRow(envelope, candidate.id);
      if (!claimedRow) return null;
      session = this.sessionOrThrow(envelope, sessionId);
      const bumped = this.bumpSessionEpoch(envelope, session, workerId, [candidate.id]);
      const { route_snapshot, ...descriptor } = payload.runner;
      return {
        job: {
          id: candidate.id,
          session_id: sessionId,
          attempt: payload.attempt,
          phase_job_key: payload.phase_job_key,
          input_sha256: payload.input_sha256,
          state: 'leased',
          lease_epoch: claimedRow.lease_epoch,
          cancel_generation: payload.cancel_generation,
          brief_revision: payload.brief_revision,
        },
        operation_id: operationKey(
          sessionId,
          payload.attempt,
          payload.phase_job_key,
          payload.input_sha256,
        ),
        seat_id: payload.seat_id as SeatId | null,
        worker_id: workerId,
        job_lease_epoch: claimedRow.lease_epoch,
        session_lease_epoch: bumped.lease_epoch,
        // The generation the JOB belongs to, not the session's current
        // one: if cancellation moved on after enqueue, the dispatch
        // gate must see the mismatch and fence this claim.
        cancel_generation: payload.cancel_generation,
        state_version_at_claim: bumped.state_version,
        descriptor,
        route_snapshot,
      };
    }
    return null;
  }

  /**
   * Claim up to `limit` queued runnable operations as ONE wave
   * (W77S-MODES). The filters are exactly claimNextOperation's: a
   * runnable session, no live lease anywhere in the session, and only
   * queued jobs whose dispatch descriptor and cancellation generation
   * are current. Expired leases are reconciled first, the same way.
   *
   * The wave bumps the session fencing generation ONCE, so every claim
   * it returns carries the same `session_lease_epoch`. That is the
   * whole point: the budget service and the card commit fence compare
   * the presented epoch with the session's current one, so N claims
   * each bumping their own epoch would fence the earlier settles out
   * and lose paid responses. Waves run to completion before the next
   * wave is claimed, so no in-flight operation is ever fenced.
   *
   * Returns [] when a live lease exists (another worker, or a previous
   * wave, still owns work) or nothing is claimable: an empty wave IS
   * the rejected claim, never an exception, because losing a claim
   * race is normal operation.
   */
  claimWave(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    workerId: string,
    limit: number,
  ): JobClaim[] {
    if (!Number.isSafeInteger(limit) || limit < 1) return [];
    let session = this.sessionOrThrow(envelope, sessionId);
    if (!RUNNABLE_STATES.has(session.state.state)) return [];

    const liveLease = (): boolean =>
      this.listSessionJobs(envelope, sessionId).some(
        (c) =>
          (c.state === 'leased' || c.state === 'running') &&
          (c.lease_expires_at === null || Date.parse(c.lease_expires_at) > this.nowMs()),
      );
    if (liveLease()) return [];

    // Reconcile a dead worker's lapsed lease before claiming, exactly as
    // the single-claim path does: recovery may finish the job, fail it
    // as provider-unknown, or return it to queued for this wave.
    for (const candidate of this.listSessionJobs(envelope, sessionId)) {
      if (candidate.state !== 'leased' && candidate.state !== 'running') continue;
      if (candidate.lease_expires_at === null) continue;
      if (Date.parse(candidate.lease_expires_at) > this.nowMs()) continue;
      if (candidate.lease_owner === workerId) continue;
      this.recoverExpiredLease(envelope, candidate.id, workerId);
    }
    if (liveLease()) return [];

    session = this.sessionOrThrow(envelope, sessionId);
    const taken: Array<{
      id: string;
      payload: StoredJobPayload;
      descriptor: OperationDescriptor;
      route_snapshot: PinnedRouteSnapshot;
      job_lease_epoch: number;
    }> = [];
    for (const candidate of this.listSessionJobs(envelope, sessionId)) {
      if (taken.length >= limit) break;
      if (candidate.state !== 'queued') continue;
      const fresh = this.jobRow(envelope, candidate.id);
      if (!fresh || fresh.state !== 'queued') continue;
      const payload = JSON.parse(fresh.payload_json) as StoredJobPayload;
      if (!payload.runner) continue;
      if (payload.cancel_generation !== session.state.cancel_generation) {
        this.retireSupersededJob(envelope, candidate.id);
        continue;
      }
      const claimed = this.db.write((handle) => {
        const expires = new Date(this.nowMs() + this.leaseTtlMs).toISOString();
        const result = handle
          .prepare(
            `UPDATE council_jobs
                SET state = 'leased', lease_owner = ?, lease_epoch = lease_epoch + 1,
                    lease_expires_at = ?, attempt_count = attempt_count + 1,
                    updated_at = ?
              WHERE tenant_id = ? AND company_id = ? AND id = ? AND state = 'queued'`,
          )
          .run(workerId, expires, this.nowIso(), envelope.tenant_id, envelope.company_id, candidate.id);
        return Number(result.changes) === 1;
      });
      if (!claimed) continue; // lost the race to another worker
      const claimedRow = this.jobRow(envelope, candidate.id);
      if (!claimedRow) continue;
      const { route_snapshot, ...descriptor } = payload.runner;
      taken.push({
        id: candidate.id,
        payload,
        descriptor,
        route_snapshot,
        job_lease_epoch: claimedRow.lease_epoch,
      });
    }
    if (taken.length === 0) return [];

    let bumped: SessionStateRecord;
    try {
      bumped = this.bumpSessionEpoch(
        envelope,
        session,
        workerId,
        taken.map((t) => t.id),
      );
    } catch (error) {
      // A wave that never got a generation owns nothing: hand every
      // claimed row straight back to queued so no lease is stranded
      // under an epoch no worker holds.
      for (const t of taken) this.returnJobToQueued(envelope, t.id, workerId, t.job_lease_epoch);
      throw error;
    }
    // The wave runs as a unit, so the capacity service must admit the
    // whole wave rather than refusing its later members.
    this.capacity?.ensureConcurrentCapacity(taken.length);
    return taken.map((t) => ({
      job: {
        id: t.id,
        session_id: sessionId,
        attempt: t.payload.attempt,
        phase_job_key: t.payload.phase_job_key,
        input_sha256: t.payload.input_sha256,
        state: 'leased' as const,
        lease_epoch: t.job_lease_epoch,
        cancel_generation: t.payload.cancel_generation,
        brief_revision: t.payload.brief_revision,
      },
      operation_id: operationKey(
        sessionId,
        t.payload.attempt,
        t.payload.phase_job_key,
        t.payload.input_sha256,
      ),
      seat_id: t.payload.seat_id as SeatId | null,
      worker_id: workerId,
      job_lease_epoch: t.job_lease_epoch,
      session_lease_epoch: bumped.lease_epoch,
      cancel_generation: t.payload.cancel_generation,
      state_version_at_claim: bumped.state_version,
      descriptor: t.descriptor,
      route_snapshot: t.route_snapshot,
    }));
  }

  /**
   * Advance the session fencing generation for a new claim. Any token
   * minted under an earlier epoch (budget reservations, card commit
   * fences, in-flight workers) goes stale at this instant. Retried on
   * a state-version conflict: losing the epoch race means the other
   * claimer is the current generation, and this bump then fences IT
   * out in turn only if this worker actually won the job CAS first;
   * callers here always hold the job CAS when they bump.
   */
  private bumpSessionEpoch(
    envelope: AuthorizationEnvelope,
    session: StoredSession,
    workerId: string,
    jobIds: readonly string[],
  ): SessionStateRecord {
    let current = session.state;
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const next: SessionStateRecord = {
        ...current,
        lease_epoch: current.lease_epoch + 1,
        updated_at: this.nowIso(),
      };
      try {
        this.repositories.writeStateRecord(envelope, next, current.state_version, {
          type: 'session_state_changed',
          payload: {
            lease_claim: {
              worker_id: workerId,
              job_id: jobIds[0] ?? null,
              ...(jobIds.length > 1 ? { job_ids: [...jobIds] } : {}),
              lease_epoch: next.lease_epoch,
            },
          },
        });
        return next;
      } catch (error) {
        if (
          error instanceof PersistenceError &&
          error.code === 'PERSISTENCE_STATE_CONFLICT'
        ) {
          const fresh = this.sessionOrThrow(envelope, current.session_id);
          current = fresh.state;
          continue;
        }
        throw error;
      }
    }
    throw new JobRunnerError(
      'JOB_LEASE_FENCED',
      `Could not establish a new fencing generation for session ${current.session_id}: the state record kept moving.`,
      { retryable: true, detail: { session_id: current.session_id } },
    );
  }

  /**
   * Return a claimed job to queued without executing it (the session
   * paused, capacity refused, or the claim was fenced before dispatch
   * and the work is still wanted). Only the claim owner at the claim
   * epoch can release; anyone else's release is a no-op returning
   * false, so a stale worker cannot free a live worker's job.
   */
  releaseClaim(envelope: AuthorizationEnvelope, claim: JobClaim): boolean {
    return this.returnJobToQueued(envelope, claim.job.id, claim.worker_id, claim.job_lease_epoch);
  }

  /**
   * Return one leased/running job to queued, but only for the owner at
   * the epoch it holds. A stale owner's write matches nothing, so it
   * cannot free a live worker's job.
   */
  private returnJobToQueued(
    envelope: AuthorizationEnvelope,
    jobId: string,
    workerId: string,
    jobLeaseEpoch: number,
  ): boolean {
    return this.db.write((handle) => {
      const result = handle
        .prepare(
          `UPDATE council_jobs
              SET state = 'queued', lease_owner = NULL, lease_expires_at = NULL,
                  updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?
              AND state IN ('leased', 'running')
              AND lease_owner = ? AND lease_epoch = ?`,
        )
        .run(
          this.nowIso(),
          envelope.tenant_id,
          envelope.company_id,
          jobId,
          workerId,
          jobLeaseEpoch,
        );
      return Number(result.changes) === 1;
    });
  }

  /**
   * Retire a queued job written under a superseded cancellation
   * generation: it can never run, so it is cancelled in place instead
   * of being stranded queued forever.
   */
  private retireSupersededJob(envelope: AuthorizationEnvelope, jobId: string): void {
    this.db.write((handle) => {
      handle
        .prepare(
          `UPDATE council_jobs
              SET state = 'cancelled', terminal_reason = 'superseded_cancel_generation',
                  updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ? AND state = 'queued'`,
        )
        .run(this.nowIso(), envelope.tenant_id, envelope.company_id, jobId);
    });
  }

  /**
   * Renew the claim's job lease for another TTL. Renewal touches only
   * the job row's expiry: it never renews a spending grant, never
   * resets a retry or repair counter, and never moves the session
   * fencing generation (Section 15.8). A lease that already expired
   * cannot be renewed back to life; the job must be reconciled and
   * re-claimed, so a late heartbeat from a replaced worker fails with
   * JOB_LEASE_LOST instead of resurrecting its authority.
   */
  heartbeatClaim(envelope: AuthorizationEnvelope, claim: JobClaim): string {
    const now = this.nowIso();
    const renewed = this.db.write((handle) => {
      const expires = new Date(this.nowMs() + this.leaseTtlMs).toISOString();
      const result = handle
        .prepare(
          `UPDATE council_jobs
              SET lease_expires_at = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?
              AND state IN ('leased', 'running')
              AND lease_owner = ? AND lease_epoch = ?
              AND lease_expires_at > ?`,
        )
        .run(
          expires,
          now,
          envelope.tenant_id,
          envelope.company_id,
          claim.job.id,
          claim.worker_id,
          claim.job_lease_epoch,
          now,
        );
      return Number(result.changes) === 1 ? expires : null;
    });
    if (renewed === null) {
      throw new JobRunnerError(
        'JOB_LEASE_LOST',
        `Lease for job ${claim.job.id} (operation ${claim.operation_id}) is no longer renewable by worker ${claim.worker_id} at epoch ${claim.job_lease_epoch}: it expired, was reclaimed, or finished.`,
        { detail: { job_id: claim.job.id, operation_id: claim.operation_id } },
      );
    }
    const token = this.capacityTokens.get(claim.job.id);
    if (token && this.capacity) this.capacity.heartbeat(token.token_id);
    return renewed;
  }

  /**
   * The worker's OWN fence check (T157): re-reads the durable job row
   * and session record and verifies owner, job epoch, session epoch,
   * and cancellation generation. It consults no host job context, so
   * it protects commits identically inside and outside a host
   * scheduler invocation. Called before every protected commit.
   */
  assertFenceCurrent(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
  ): FenceSnapshot {
    const row = this.jobRow(envelope, claim.job.id);
    if (
      !row ||
      (row.state !== 'leased' && row.state !== 'running') ||
      row.lease_owner !== claim.worker_id ||
      row.lease_epoch !== claim.job_lease_epoch
    ) {
      throw new JobRunnerError(
        'JOB_LEASE_FENCED',
        `Job ${claim.job.id} is no longer owned by worker ${claim.worker_id} at lease epoch ${claim.job_lease_epoch}. Late results are discarded.`,
        { detail: { job_id: claim.job.id, operation_id: claim.operation_id } },
      );
    }
    const session = this.sessionOrThrow(envelope, claim.job.session_id);
    if (session.state.lease_epoch !== claim.session_lease_epoch) {
      throw new JobRunnerError(
        'JOB_LEASE_FENCED',
        `Session ${claim.job.session_id} fencing generation moved from ${claim.session_lease_epoch} to ${session.state.lease_epoch}: a newer claim owns this session's work.`,
        { detail: { job_id: claim.job.id, operation_id: claim.operation_id } },
      );
    }
    if (session.state.cancel_generation !== claim.cancel_generation) {
      throw new JobRunnerError(
        'JOB_LEASE_FENCED',
        `Session ${claim.job.session_id} cancellation generation moved from ${claim.cancel_generation} to ${session.state.cancel_generation}: this claim's results are fenced out.`,
        { detail: { job_id: claim.job.id, operation_id: claim.operation_id } },
      );
    }
    return {
      job_lease_epoch: row.lease_epoch,
      session_lease_epoch: session.state.lease_epoch,
      cancel_generation: session.state.cancel_generation,
      session_state_version: session.state.state_version,
      session_state: session.state.state,
    };
  }

  // ------------------------------------------------------------- execute

  /**
   * Execute one claimed operation end to end: admission, attempt
   * ledger, checkpoint, dispatch through the injected executor (never
   * inside a store transaction), bounded transport retry and output
   * repair as separately admitted operations, fence-checked card
   * commit, and exactly-once consumption recording. SimulatedCrashError
   * from the executor propagates uncaught by design: a crash is
   * reconciled from durable state by the next worker, not converted
   * into a failure verdict here.
   */
  async executeClaimedOperation(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
  ): Promise<OperationOutcome> {
    const session = this.sessionOrThrow(envelope, claim.job.session_id);
    // Resume shortcut: a prior worker committed this operation's card
    // (or recorded its accepted checkpoint) and died before finishing
    // the job. The committed work is authoritative; never re-dispatch.
    const committedCard = this.findCommittedCard(envelope, claim);
    if (committedCard) {
      // The card is durable but the prior worker died before recording
      // consumption: the charge it made is unrecorded, so it is marked
      // unknown (counted at estimate, never zero, never invented).
      const reservation = this.budget.getReservation(
        envelope,
        claim.job.session_id,
        claim.operation_id,
      );
      if (reservation && reservation.state === 'reserved') {
        this.admission.recordConsumption(envelope, {
          grant_id: claim.descriptor.grant_id,
          session_id: claim.job.session_id,
          operation_id: claim.operation_id,
          lease_epoch: claim.session_lease_epoch,
          outcome: 'unknown',
        });
      }
      this.updateAttempt(envelope, claim.operation_id, 'accepted', 'recovered_after_commit');
      this.finishJobRow(envelope, claim.job.id, claim.job_lease_epoch, 'succeeded', claim.operation_id);
      return {
        status: 'already_committed',
        operation_id: claim.operation_id,
        reason: null,
        card: committedCard,
      };
    }
    // Pre-dispatch state gate: pause and cancel land here first.
    const gate = this.dispatchGate(envelope, claim);
    if (gate !== 'run') {
      if (gate === 'cancelled') {
        this.finishJobRow(envelope, claim.job.id, claim.job_lease_epoch, 'cancelled', 'session_cancelled');
        return { status: 'cancelled', operation_id: claim.operation_id, reason: 'session_cancelled', card: null };
      }
      this.releaseClaim(envelope, claim);
      return { status: 'deferred', operation_id: claim.operation_id, reason: gate, card: null };
    }

    // Admission: no operation runs without it (CWE-049 composition).
    try {
      this.admission.admitOperation(envelope, {
        grant_id: claim.descriptor.grant_id,
        session_id: claim.job.session_id,
        operation_id: claim.operation_id,
        kind: claim.descriptor.kind,
        purpose: claim.descriptor.purpose,
        estimate_minor: claim.descriptor.estimate_minor,
        currency: claim.descriptor.currency ?? null,
        lease_epoch: claim.session_lease_epoch,
        route_snapshot: claim.route_snapshot,
        original_operation_id: claim.descriptor.original_operation_id ?? null,
      });
    } catch (error) {
      if (isSimulatedCrash(error)) throw error;
      const code = error instanceof Error && 'code' in error ? String((error as { code: unknown }).code) : 'RUN_ADMISSION_REFUSED';
      // Nothing was dispatched and nothing was spent: the job returns
      // to queued intact, so a renewed grant (or a corrected caller)
      // can run the SAME job later. The refusal itself is journaled by
      // the admission service; refusing here never fails the work item.
      this.releaseClaim(envelope, claim);
      return { status: 'admission_refused', operation_id: claim.operation_id, reason: code, card: null };
    }
    this.recordAttempt(envelope, claim, claim.operation_id, 'reserved', null);
    this.saveCheckpoint(envelope, claim, session, 'reserved', null, {
      input_tokens: null,
      output_tokens: null,
      provider_requests: 0,
    });

    // Capacity admission (CWE-028): a full runtime defers the job;
    // the reservation was never dispatched, so it is released and the
    // job returns to queued with nothing spent.
    if (this.capacity) {
      const decision = this.capacity.tryAcquire({
        operation_key: claim.operation_id,
        work_class: session.spec.visibility === 'private' ? 'private' : 'company',
        scope_key: this.scopeKey(envelope, claim.job.session_id),
      });
      if (!decision.admitted) {
        this.budget.release(envelope, {
          session_id: claim.job.session_id,
          operation_id: claim.operation_id,
          lease_epoch: claim.session_lease_epoch,
          reason: 'capacity_full',
        });
        this.updateAttempt(envelope, claim.operation_id, 'failed', 'capacity_full');
        this.releaseClaim(envelope, claim);
        return { status: 'deferred', operation_id: claim.operation_id, reason: 'capacity_full', card: null };
      }
      this.capacityTokens.set(claim.job.id, decision.token);
    }

    try {
      return await this.dispatchAndSettle(envelope, claim, session, claim.operation_id, claim.descriptor.kind, 'initial', [], 1);
    } finally {
      const token = this.capacityTokens.get(claim.job.id);
      if (token && this.capacity) this.capacity.release(token.token_id);
      this.capacityTokens.delete(claim.job.id);
    }
  }

  /**
   * One dispatch attempt for an admitted operation, plus its bounded
   * follow-ons. Retry and repair recurse exactly once, each as its own
   * admitted operation, so CWE-028's per-original ceilings (1 and 1)
   * and the session totals (8 retries, 9 repairs, 50 requests) are the
   * binding enforcement, not counters kept here.
   */
  private async dispatchAndSettle(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    session: StoredSession,
    dispatchOperationId: string,
    dispatchKind: BudgetReservationKind,
    attemptKind: DispatchAttemptKind,
    repairIssues: string[],
    dispatchesSoFar: number,
  ): Promise<OperationOutcome> {
    const isInitial = attemptKind === 'initial';
    if (isInitial) this.markJobRunning(envelope, claim);
    this.recordAttempt(envelope, claim, dispatchOperationId, 'dispatched', null);
    if (isInitial) {
      this.saveCheckpoint(envelope, claim, session, 'dispatched', null, {
        input_tokens: null,
        output_tokens: null,
        provider_requests: dispatchesSoFar,
      });
    }
    const stopHeartbeat = this.timers.every(this.heartbeatMs, () => {
      try {
        this.heartbeatClaim(envelope, claim);
      } catch {
        // A lost lease surfaces at the next fence check; the heartbeat
        // itself must never crash the dispatch it protects.
      }
    });
    let result: OperationDispatchResult;
    const giveUp = new AbortController();
    try {
      const dispatchPromise = this.executor.dispatch({
        session,
        claim,
        dispatch_operation_id: dispatchOperationId,
        attempt_kind: attemptKind,
        repair_issues: repairIssues,
        signal: giveUp.signal,
      });
      dispatchPromise.catch(() => {
        // A deadline overrun resolves the race first; the late
        // transport settle is observed (and its output discarded by
        // the unknown-completion path) instead of surfacing as an
        // unhandled rejection.
      });
      const raced = await Promise.race([
        dispatchPromise.then((value) => ({ tag: 'value' as const, value })),
        this.timers.delay(this.providerDeadlineMs).then(() => ({ tag: 'timeout' as const })),
      ]);
      if (raced.tag === 'timeout') {
        giveUp.abort();
        return this.settleUnknown(
          envelope,
          claim,
          session,
          dispatchOperationId,
          dispatchesSoFar,
          `The provider call did not return within ${Math.round(this.providerDeadlineMs / 1000)} s; whether the provider completed is unknown, so it is not replayed.`,
        );
      }
      result = raced.value;
    } catch (error) {
      if (isSimulatedCrash(error)) throw error;
      if (error instanceof TransportDispatchError) {
        if (error.unknownCompletion) {
          return this.settleUnknown(envelope, claim, session, dispatchOperationId, dispatchesSoFar, error.message);
        }
        if (error.retryable) {
          // The provider did not accept this attempt: release its
          // reservation (never dispatched in effect) and, for the
          // initial attempt only, admit the one bounded retry.
          this.budget.release(envelope, {
            session_id: claim.job.session_id,
            operation_id: dispatchOperationId,
            lease_epoch: claim.session_lease_epoch,
            reason: 'transport_not_accepted',
          });
          this.updateAttempt(envelope, dispatchOperationId, 'failed', 'transport_not_accepted', { retry_safe: true });
          this.journalAttemptFailure(envelope, claim, dispatchOperationId, 'transport_not_accepted', error.message);
          if (isInitial && dispatchKind === 'provider_request') {
            return this.admitAndDispatchFollowOn(
              envelope,
              claim,
              session,
              `${claim.operation_id}:retry:1`,
              'transport_retry',
              'transport_retry',
            );
          }
          this.saveCheckpoint(envelope, claim, session, 'failed', null, {
            input_tokens: null,
            output_tokens: null,
            provider_requests: dispatchesSoFar,
          });
          this.finishJobRow(envelope, claim.job.id, claim.job_lease_epoch, 'failed', 'transport_failed');
          return { status: 'failed', operation_id: claim.operation_id, reason: 'transport_failed', card: null };
        }
        // Definite rejection: the request was submitted and refused.
        // It counts (settled at its actual charge) and fails the job.
        this.admission.recordConsumption(envelope, {
          grant_id: claim.descriptor.grant_id,
          session_id: claim.job.session_id,
          operation_id: dispatchOperationId,
          lease_epoch: claim.session_lease_epoch,
          outcome: 'settled',
          actual_minor: error.actual_minor,
        });
        this.updateAttempt(envelope, dispatchOperationId, 'failed', 'transport_rejected', {
          actual_minor: error.actual_minor,
        });
        this.journalAttemptFailure(envelope, claim, dispatchOperationId, 'transport_rejected', error.message);
        this.saveCheckpoint(envelope, claim, session, 'failed', null, {
          input_tokens: null,
          output_tokens: null,
          provider_requests: dispatchesSoFar,
        });
        this.finishJobRow(envelope, claim.job.id, claim.job_lease_epoch, 'failed', 'transport_rejected');
        return { status: 'failed', operation_id: claim.operation_id, reason: 'transport_rejected', card: null };
      }
      throw error;
    } finally {
      stopHeartbeat();
    }

    // A result arrived. Stamp it as the host and validate canonically
    // (plus the executor's deeper validation when provided).
    const card = this.stampCard(envelope, claim, session, result);
    // An unparseable reply is repaired as "not valid JSON", never as the
    // schema errors the empty payload would produce.
    const issues = result.parse_error !== undefined
      ? [`${NOT_JSON_ISSUE}${result.parse_error}`]
      : this.validateStamped(envelope, claim, session, dispatchOperationId, attemptKind, card);
    if (issues.length > 0) {
      // The request completed and is charged; settle it, then enter
      // the bounded repair path (initial attempt only).
      this.admission.recordConsumption(envelope, {
        grant_id: claim.descriptor.grant_id,
        session_id: claim.job.session_id,
        operation_id: dispatchOperationId,
        lease_epoch: claim.session_lease_epoch,
        outcome: 'settled',
        actual_minor: result.actual_minor,
      });
      this.updateAttempt(envelope, dispatchOperationId, 'failed', 'output_validation_failed', {
        actual_minor: result.actual_minor,
        input_tokens: result.input_tokens,
        output_tokens: result.output_tokens,
      });
      this.journalAttemptFailure(envelope, claim, dispatchOperationId, 'output_validation_failed', issues.join('; '));
      if (isInitial && dispatchKind === 'provider_request') {
        return this.admitAndDispatchFollowOn(
          envelope,
          claim,
          session,
          `${claim.operation_id}:repair:1`,
          'output_repair',
          'output_repair',
          issues,
        );
      }
      this.saveCheckpoint(envelope, claim, session, 'failed', result.provider_request_id, {
        input_tokens: result.input_tokens,
        output_tokens: result.output_tokens,
        provider_requests: dispatchesSoFar,
      });
      this.finishJobRow(envelope, claim.job.id, claim.job_lease_epoch, 'failed', 'output_validation_failed');
      return { status: 'failed', operation_id: claim.operation_id, reason: 'output_validation_failed', card: null };
    }
    return this.commitResult(envelope, claim, session, dispatchOperationId, card, result, dispatchesSoFar);
  }

  /**
   * Keep why an attempt failed. The attempts table stores only the
   * outcome code, so the message (at most 300 characters, key-shaped
   * text redacted) is journaled beside it; the service reads it back to
   * explain a BLOCKED session. Never throws: it must not fail a dispatch.
   */
  private journalAttemptFailure(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    operationId: string,
    outcomeCode: string,
    message: string,
  ): void {
    try {
      const safe = message.replace(SECRET_SHAPE, '[redacted]').slice(0, 300);
      this.db.write((handle) =>
        this.repositories.journal.append(handle, envelope, claim.job.session_id, {
          event_id: this.ids.newId(),
          type: 'operation_completed',
          from_state: null,
          to_state: null,
          actor_subject: envelope.actor_subject,
          payload: {
            kind: 'attempt_failed',
            operation_id: operationId,
            seat_id: claim.seat_id,
            outcome_code: outcomeCode,
            message: safe,
          },
          created_at: this.nowIso(),
        }),
      );
    } catch (error) {
      if (isSimulatedCrash(error)) throw error;
    }
  }

  /** Admit a retry or repair follow-on operation and dispatch it. */
  private async admitAndDispatchFollowOn(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    session: StoredSession,
    followOnOperationId: string,
    kind: 'transport_retry' | 'output_repair',
    attemptKind: DispatchAttemptKind,
    repairIssues: string[] = [],
  ): Promise<OperationOutcome> {
    try {
      this.admission.admitOperation(envelope, {
        grant_id: claim.descriptor.grant_id,
        session_id: claim.job.session_id,
        operation_id: followOnOperationId,
        kind,
        purpose: claim.descriptor.purpose,
        estimate_minor: claim.descriptor.estimate_minor,
        currency: claim.descriptor.currency ?? null,
        lease_epoch: claim.session_lease_epoch,
        route_snapshot: claim.route_snapshot,
        original_operation_id: claim.operation_id,
      });
    } catch (error) {
      if (isSimulatedCrash(error)) throw error;
      const code = error instanceof Error && 'code' in error ? String((error as { code: unknown }).code) : 'RUN_ADMISSION_REFUSED';
      this.saveCheckpoint(envelope, claim, session, 'failed', null, {
        input_tokens: null,
        output_tokens: null,
        provider_requests: 1,
      });
      this.finishJobRow(envelope, claim.job.id, claim.job_lease_epoch, 'failed', code);
      return { status: 'admission_refused', operation_id: claim.operation_id, reason: code, card: null };
    }
    this.saveCheckpoint(envelope, claim, session, 'dispatched', null, {
      input_tokens: null,
      output_tokens: null,
      provider_requests: 2,
    });
    return this.dispatchAndSettle(
      envelope,
      claim,
      session,
      followOnOperationId,
      kind,
      attemptKind,
      repairIssues,
      2,
    );
  }

  /**
   * Provider completion unknown: retain the reservation at its
   * estimate through recordConsumption, record the checkpoint and
   * attempt truthfully, and end the job. Nothing here replays the
   * operation, and no later path requeues it (T050).
   */
  private settleUnknown(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    session: StoredSession,
    dispatchOperationId: string,
    dispatchesSoFar: number,
    message: string,
  ): OperationOutcome {
    try {
      this.admission.recordConsumption(envelope, {
        grant_id: claim.descriptor.grant_id,
        session_id: claim.job.session_id,
        operation_id: dispatchOperationId,
        lease_epoch: claim.session_lease_epoch,
        outcome: 'unknown',
      });
    } catch (error) {
      // A newer fencing generation owns the session: CWE-028 refuses
      // this stale finalization, and the current owner's recovery
      // marks the dispatched attempt unknown instead. The outcome for
      // THIS operation is unchanged: unknown, never replayed.
      if (
        !(
          error instanceof Error &&
          'code' in error &&
          (error as { code: unknown }).code === 'BUDGET_LEASE_FENCED'
        )
      ) {
        throw error;
      }
      this.keepFencedReservationCounted(envelope, claim, dispatchOperationId);
    }
    this.updateAttempt(envelope, dispatchOperationId, 'provider_completion_unknown', 'completion_unknown');
    this.journalAttemptFailure(envelope, claim, dispatchOperationId, 'provider_completion_unknown', message);
    this.saveCheckpoint(envelope, claim, session, 'provider_completion_unknown', null, {
      input_tokens: null,
      output_tokens: null,
      provider_requests: dispatchesSoFar,
    });
    this.finishJobRow(envelope, claim.job.id, claim.job_lease_epoch, 'failed', 'provider_completion_unknown');
    return {
      status: 'provider_completion_unknown',
      operation_id: claim.operation_id,
      reason: 'provider_completion_unknown',
      card: null,
    };
  }

  /**
   * Commit a validated result. The fence is re-checked immediately
   * before the protected commit (T157); a fenced late result is
   * discarded (no card, no verdict material) while its consumption is
   * still recorded, because the provider work really happened and the
   * accounting must stay truthful (Sections 15.4 and 29).
   */
  private commitResult(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    session: StoredSession,
    dispatchOperationId: string,
    card: CouncilCard,
    result: OperationDispatchResult,
    dispatchesSoFar: number,
  ): OperationOutcome {
    // Grant fence: a grant revoked or expired mid-run fences the
    // in-flight commit (CWE-049 T139 semantics). The already-accepted
    // request's consumption is still recorded in the discard path
    // below; only the commit is refused. resolveRunGrant returns null
    // for revoked, expired, exhausted, and preview records.
    if (
      this.grants.resolveRunGrant(
        envelope,
        claim.descriptor.grant_id,
        claim.job.session_id,
      ) === null
    ) {
      return this.discardLateResult(
        envelope,
        claim,
        session,
        dispatchOperationId,
        result,
        dispatchesSoFar,
        'grant_revoked_or_expired_mid_run',
      );
    }
    let fence: FenceSnapshot;
    try {
      fence = this.assertFenceCurrent(envelope, claim);
    } catch (error) {
      if (!isJobFence(error)) throw error;
      return this.discardLateResult(
        envelope,
        claim,
        session,
        dispatchOperationId,
        result,
        dispatchesSoFar,
        'fenced_late_result',
      );
    }
    const accept = this.repositories.acceptCard(envelope, card, {
      expected_state_version: fence.session_state_version,
      cancel_generation: fence.cancel_generation,
      lease_epoch: fence.session_lease_epoch,
    });
    const committedCard = accept.card;
    this.admission.recordConsumption(envelope, {
      grant_id: claim.descriptor.grant_id,
      session_id: claim.job.session_id,
      operation_id: dispatchOperationId,
      lease_epoch: claim.session_lease_epoch,
      outcome: 'settled',
      actual_minor: result.actual_minor,
    });
    this.updateAttempt(envelope, dispatchOperationId, 'accepted', null, {
      actual_minor: result.actual_minor,
      input_tokens: result.input_tokens,
      output_tokens: result.output_tokens,
      author: result.author,
    });
    this.saveCheckpoint(envelope, claim, session, 'accepted', result.provider_request_id, {
      input_tokens: result.input_tokens,
      output_tokens: result.output_tokens,
      provider_requests: dispatchesSoFar,
    });
    // The job finish is itself a protected commit: fence again.
    this.assertFenceCurrent(envelope, claim);
    this.finishJobRow(envelope, claim.job.id, claim.job_lease_epoch, 'succeeded', claim.operation_id);
    return {
      status: 'committed',
      operation_id: claim.operation_id,
      reason: null,
      card: committedCard,
    };
  }

  /**
   * A fenced settle cannot finalize money, but the provider call was
   * paid for: mark the still-reserved hold 'unknown' under the session's
   * current epoch so it stays counted at its estimate. Left alone it
   * would lapse to 'expired' and free its allowance, dropping a paid
   * call from the ledger.
   */
  private keepFencedReservationCounted(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    operationId: string,
  ): void {
    const sessionId = claim.job.session_id;
    const reservation = this.budget.getReservation(envelope, sessionId, operationId);
    const fresh = this.repositories.getSession(envelope, sessionId);
    if (!reservation || reservation.state !== 'reserved' || !fresh) return;
    try {
      this.admission.recordConsumption(envelope, {
        grant_id: claim.descriptor.grant_id,
        session_id: sessionId,
        operation_id: operationId,
        lease_epoch: fresh.state.lease_epoch,
        outcome: 'unknown',
      });
    } catch {
      // the epoch moved again; the hold remains reserved for the current owner's recovery
    }
  }

  /**
   * Discard a late or authority-less result: no card is committed,
   * nothing downstream can build a verdict on it, and the job ends.
   * The consumption is still recorded whenever this worker's fencing
   * generation is the one that admitted the operation; when a newer
   * generation has taken the session over, CWE-028 refuses the stale
   * finalization (BUDGET_LEASE_FENCED) and the reservation stays held
   * for the current owner's reconciliation, which is the honest
   * outcome: a fenced worker neither commits nor finalizes money.
   */
  private discardLateResult(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    session: StoredSession,
    dispatchOperationId: string,
    result: OperationDispatchResult,
    dispatchesSoFar: number,
    reason: string,
  ): OperationOutcome {
    try {
      this.admission.recordConsumption(envelope, {
        grant_id: claim.descriptor.grant_id,
        session_id: claim.job.session_id,
        operation_id: dispatchOperationId,
        lease_epoch: claim.session_lease_epoch,
        outcome: 'settled',
        actual_minor: result.actual_minor,
      });
    } catch (error) {
      if (
        !(
          error instanceof Error &&
          'code' in error &&
          (error as { code: unknown }).code === 'BUDGET_LEASE_FENCED'
        )
      ) {
        throw error;
      }
      this.keepFencedReservationCounted(envelope, claim, dispatchOperationId);
    }
    this.updateAttempt(envelope, dispatchOperationId, 'cancelled', reason, {
      actual_minor: result.actual_minor,
    });
    const fresh = this.repositories.getSession(envelope, claim.job.session_id);
    const cancelled =
      fresh === null ||
      fresh.state.cancel_generation !== claim.cancel_generation ||
      fresh.state.state === 'CANCELLED' ||
      fresh.state.state === 'CANCEL_REQUESTED';
    this.saveCheckpoint(
      envelope,
      claim,
      session,
      cancelled ? 'cancelled' : 'failed',
      result.provider_request_id,
      {
        input_tokens: result.input_tokens,
        output_tokens: result.output_tokens,
        provider_requests: dispatchesSoFar,
      },
    );
    this.finishJobRow(
      envelope,
      claim.job.id,
      claim.job_lease_epoch,
      cancelled ? 'cancelled' : 'failed',
      reason,
    );
    // A discarded paid response is surfaced, never swallowed. A user
    // cancel is expected and is not an error.
    if (!cancelled) {
      try {
        this.onFencedSettle?.(
          new JobRunnerError(
            'OPERATION_LEASE_FENCED',
            `The paid response for ${dispatchOperationId} was discarded (${reason}); its reservation stays counted.`,
            { detail: { session_id: claim.job.session_id, operation_id: dispatchOperationId, reason } },
          ),
          { session_id: claim.job.session_id },
        );
      } catch {
        // reporting must never break settling
      }
    }
    return {
      status: 'fenced',
      operation_id: claim.operation_id,
      reason,
      card: null,
    };
  }

  // ------------------------------------------------------------ recovery

  /**
   * Reconcile one operation job whose lease expired under a previous
   * worker. Reads only durable state (job row, attempt ledger,
   * checkpoint, committed cards, budget reservation) and resolves the
   * job to its truthful end: committed work finishes, dispatched-but-
   * uncommitted work becomes provider_completion_unknown and is never
   * replayed, never-dispatched work is released and requeued, and work
   * under a superseded cancellation generation is cancelled. The
   * session fencing generation is advanced first, so every token the
   * dead worker held is stale before any accounting is finalized.
   * Returns null when the job is not an expired leased/running job.
   */
  recoverExpiredLease(
    envelope: AuthorizationEnvelope,
    jobId: string,
    workerId: string,
  ): RecoveryOutcome | null {
    const row = this.jobRow(envelope, jobId);
    if (!row || row.session_id === null) return null;
    if (row.state !== 'leased' && row.state !== 'running') return null;
    if (row.lease_expires_at === null || Date.parse(row.lease_expires_at) > this.nowMs()) {
      return null;
    }
    const sessionId = row.session_id;
    const payload = JSON.parse(row.payload_json) as StoredJobPayload;
    if (!payload.runner) return null;
    const descriptor: OperationDescriptor = payload.runner;
    const operationId = operationKey(
      sessionId,
      payload.attempt,
      payload.phase_job_key,
      payload.input_sha256,
    );
    const session = this.sessionOrThrow(envelope, sessionId);
    const epoch = this.bumpSessionEpoch(envelope, session, workerId, [jobId]).lease_epoch;

    const finalizeReservation = (
      action: 'unknown' | 'release' | 'none',
    ): void => {
      const reservation = this.budget.getReservation(envelope, sessionId, operationId);
      if (!reservation || reservation.state !== 'reserved') return;
      if (action === 'unknown') {
        this.admission.recordConsumption(envelope, {
          grant_id: descriptor.grant_id,
          session_id: sessionId,
          operation_id: operationId,
          lease_epoch: epoch,
          outcome: 'unknown',
        });
      } else if (action === 'release') {
        this.budget.release(envelope, {
          session_id: sessionId,
          operation_id: operationId,
          lease_epoch: epoch,
          reason: 'worker_lost_before_dispatch',
        });
      }
    };

    const superseded =
      payload.cancel_generation !== session.state.cancel_generation ||
      session.state.state === 'CANCELLED' ||
      session.state.state === 'CANCEL_REQUESTED';

    const card = superseded ? null : this.findCommittedCardByIdentity(envelope, sessionId, descriptor, payload);
    const checkpoint = superseded
      ? null
      : this.jobs.getCheckpoint(envelope, {
          sessionId,
          attempt: payload.attempt,
          briefRevision: session.state.brief_revision,
          phaseJobKey: payload.phase_job_key,
          seatId: payload.seat_id,
          inputSha256: payload.input_sha256,
          currentCancelGeneration: session.state.cancel_generation,
        });
    const attemptStatus = this.attemptStatus(envelope, operationId);

    if (superseded) {
      finalizeReservation(attemptStatus === 'dispatched' ? 'unknown' : 'release');
      if (attemptStatus === 'dispatched') {
        this.updateAttempt(envelope, operationId, 'provider_completion_unknown', 'completion_unknown');
      }
      this.finishJobRow(envelope, jobId, row.lease_epoch, 'cancelled', 'session_cancelled');
      return { job_id: jobId, operation_id: operationId, outcome: 'recovered_cancelled' };
    }
    if (card || checkpoint?.status === 'accepted') {
      finalizeReservation('unknown');
      this.updateAttempt(envelope, operationId, 'accepted', 'recovered_after_commit');
      this.finishJobRow(envelope, jobId, row.lease_epoch, 'succeeded', operationId);
      return { job_id: jobId, operation_id: operationId, outcome: 'recovered_committed' };
    }
    if (attemptStatus === 'dispatched' || checkpoint?.status === 'dispatched') {
      finalizeReservation('unknown');
      this.updateAttempt(envelope, operationId, 'provider_completion_unknown', 'completion_unknown');
      const claim = this.claimShell(session, payload, descriptor, payload.runner.route_snapshot, operationId, workerId, row.lease_epoch, epoch);
      this.saveCheckpoint(envelope, claim, session, 'provider_completion_unknown', checkpoint?.provider_request_id ?? null, {
        input_tokens: checkpoint?.usage.input_tokens ?? null,
        output_tokens: checkpoint?.usage.output_tokens ?? null,
        provider_requests: checkpoint?.usage.provider_requests ?? 1,
      });
      this.finishJobRow(envelope, jobId, row.lease_epoch, 'failed', 'provider_completion_unknown');
      return { job_id: jobId, operation_id: operationId, outcome: 'recovered_unknown' };
    }
    // Admitted-but-never-dispatched, or claimed-but-never-admitted:
    // free the hold and return the job to queued exactly once.
    finalizeReservation('release');
    if (attemptStatus === 'reserved') {
      this.updateAttempt(envelope, operationId, 'failed', 'released_before_dispatch');
    }
    this.db.write((handle) => {
      handle
        .prepare(
          `UPDATE council_jobs
              SET state = 'queued', lease_owner = NULL, lease_expires_at = NULL,
                  updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?
              AND state IN ('leased', 'running') AND lease_epoch = ?`,
        )
        .run(this.nowIso(), envelope.tenant_id, envelope.company_id, jobId, row.lease_epoch);
    });
    return { job_id: jobId, operation_id: operationId, outcome: 'recovered_requeued' };
  }

  /**
   * Scope sweep for the worker supervisor: expire lapsed budget holds
   * (CWE-028's sweep, which the CWE-049 composition assigns to this
   * scheduler's cadence) and reconcile every expired operation lease
   * in the scope. Idempotent; safe on every poll cycle and at boot.
   */
  reconcileScope(
    envelope: AuthorizationEnvelope,
    workerId: string,
  ): { expired_holds: number; recoveries: RecoveryOutcome[] } {
    const expired = this.budget.expireHolds(envelope);
    const recoveries: RecoveryOutcome[] = [];
    const sessions = this.repositories.listSessions(envelope, { includeArchived: true });
    for (const session of sessions) {
      for (const job of this.listSessionJobs(envelope, session.spec.session_id)) {
        if (job.state !== 'leased' && job.state !== 'running') continue;
        const outcome = this.recoverExpiredLease(envelope, job.id, workerId);
        if (outcome) recoveries.push(outcome);
      }
    }
    return { expired_holds: expired.length, recoveries };
  }

  // ------------------------------------------------------------ controls

  /**
   * Pause a session (Section 15.4): stops new dispatch, lets in-flight
   * work finish within its deadline, preserves all accounting.
   * Idempotent: pausing a PAUSE_REQUESTED or PAUSED session returns
   * its current record unchanged. The recorded resume phase is the
   * state the session was in when pause was requested.
   */
  pauseSession(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): SessionStateRecord {
    const session = this.sessionOrThrow(envelope, sessionId);
    const current = session.state;
    if (current.state === 'PAUSED' || current.state === 'PAUSE_REQUESTED') {
      return current;
    }
    if (!RUNNABLE_STATES.has(current.state)) {
      throw new JobRunnerError(
        'JOB_CONTROL_CONFLICT',
        `Session ${sessionId} is ${current.state}; only an actively processing session can be paused.`,
        { detail: { session_id: sessionId, state: current.state } },
      );
    }
    const requested = this.controlTransition(envelope, session, 'PAUSE_REQUESTED', {
      resumePhaseRecord: current.state,
    });
    return this.controlTransition(envelope, { ...session, state: requested }, 'PAUSED', {
      resumePhaseRecord: current.state,
    });
  }

  /**
   * Resume a paused or blocked session to its recorded resume phase.
   * The pinned route and limits are untouched (they live in the grant
   * and session spec, which pause/resume never modify, T054). A resume
   * of a session that is not paused or blocked is a precise conflict.
   */
  resumeSession(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): SessionStateRecord {
    const session = this.sessionOrThrow(envelope, sessionId);
    const current = session.state;
    if (current.state === 'RESUMING') {
      const target = this.resumeTarget(envelope, session);
      return this.controlTransition(envelope, session, target, {});
    }
    if (current.state !== 'PAUSED' && current.state !== 'BLOCKED') {
      throw new JobRunnerError(
        'JOB_CONTROL_CONFLICT',
        `Session ${sessionId} is ${current.state}; only a PAUSED or BLOCKED session can resume.`,
        { detail: { session_id: sessionId, state: current.state } },
      );
    }
    const target = this.resumeTarget(envelope, session);
    const resuming = this.controlTransition(envelope, session, 'RESUMING', {});
    return this.controlTransition(
      envelope,
      { ...session, state: resuming },
      target,
      { resumePhase: target },
    );
  }

  /**
   * Cancel a session (Section 15.4): the cancellation generation
   * increments immediately (at CANCEL_REQUESTED), in-flight transports
   * are fenced at their next fence check, queued jobs are cancelled in
   * place, held capacity is freed in the same call, and CANCELLED is
   * terminal: no late result can emit a verdict, create actions, or
   * resurrect the session, and usage already spent stays reconciled
   * in CWE-028's ledger. Idempotent at CANCELLED.
   */
  cancelSession(
    envelope: AuthorizationEnvelope,
    sessionId: string,
  ): SessionStateRecord {
    const session = this.sessionOrThrow(envelope, sessionId);
    const current = session.state;
    if (current.state === 'CANCELLED') return current;
    if (current.state === 'COMPLETED' || current.state === 'FAILED') {
      throw new JobRunnerError(
        'JOB_CONTROL_CONFLICT',
        `Session ${sessionId} is already ${current.state}; a terminal session cannot be cancelled.`,
        { detail: { session_id: sessionId, state: current.state } },
      );
    }
    let record = current;
    if (current.state !== 'CANCEL_REQUESTED') {
      record = this.controlTransition(envelope, session, 'CANCEL_REQUESTED', {});
    }
    const cancelled = this.controlTransition(
      envelope,
      { ...session, state: record },
      'CANCELLED',
      {},
    );
    this.db.write((handle) => {
      handle
        .prepare(
          `UPDATE council_jobs
              SET state = 'cancelled', terminal_reason = 'session_cancelled',
                  updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND session_id = ? AND state = 'queued'`,
        )
        .run(this.nowIso(), envelope.tenant_id, envelope.company_id, sessionId);
    });
    if (this.capacity) {
      this.capacity.cancelScope(this.scopeKey(envelope, sessionId));
    }
    return cancelled;
  }

  // --------------------------------------------------------- control core

  /**
   * One legal control transition over the canonical table, written
   * with CWE-006's compare-and-swap state writer and journaled with
   * the same event vocabulary repositories.transitionState uses. The
   * record's resume_phase is set explicitly by the caller for the
   * PAUSED leg (see the module header for why).
   */
  private controlTransition(
    envelope: AuthorizationEnvelope,
    session: StoredSession,
    to: SessionState,
    options: {
      resumePhaseRecord?: SessionState;
      resumePhase?: SessionState | null;
    },
  ): SessionStateRecord {
    const current = session.state;
    const enteringCancel = to === 'CANCEL_REQUESTED';
    let stateVersion: number;
    try {
      ({ stateVersion } = assertTransition({
        mode: current.mode,
        from: current.state,
        to,
        expectedVersion: current.state_version,
        currentVersion: current.state_version,
        actor: envelope.actor,
        resumePhase: options.resumePhase ?? current.resume_phase,
        cancelGeneration: enteringCancel ? current.cancel_generation + 1 : undefined,
        currentCancelGeneration: current.cancel_generation,
      }));
    } catch (error) {
      throw new JobRunnerError(
        'JOB_CONTROL_CONFLICT',
        `Session ${current.session_id} cannot move from ${current.state} to ${to}: ${error instanceof Error ? error.message : String(error)}`,
        { detail: { session_id: current.session_id, from: current.state, to } },
      );
    }
    const next: SessionStateRecord = {
      ...current,
      state: to,
      state_version: stateVersion,
      cancel_generation: enteringCancel
        ? current.cancel_generation + 1
        : current.cancel_generation,
      resume_phase:
        options.resumePhaseRecord !== undefined
          ? options.resumePhaseRecord
          : current.resume_phase,
      updated_at: this.nowIso(),
    };
    this.repositories.writeStateRecord(envelope, next, current.state_version, {
      type: controlEventType(to),
      payload: { from_state: current.state, to_state: to },
    });
    return next;
  }

  /**
   * The phase a RESUMING session returns to: the recorded resume
   * phase when it names a runnable state; otherwise (records written
   * before this runner, where the phase was not preserved) the most
   * recent runnable phase in the session's journaled state history.
   */
  private resumeTarget(
    envelope: AuthorizationEnvelope,
    session: StoredSession,
  ): SessionState {
    const recorded = session.state.resume_phase;
    if (recorded !== null && RUNNABLE_STATES.has(recorded)) return recorded;
    const events = this.repositories.journal.list(envelope, session.spec.session_id, 0);
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const record = events[i].payload.state_record as
        | SessionStateRecord
        | undefined;
      if (record && RUNNABLE_STATES.has(record.state)) return record.state;
    }
    throw new JobRunnerError(
      'JOB_CONTROL_CONFLICT',
      `Session ${session.spec.session_id} has no recorded resume phase and no runnable phase in its journal history; it cannot be resumed honestly.`,
      { detail: { session_id: session.spec.session_id } },
    );
  }

  // ------------------------------------------------------------ internals

  private dispatchGate(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
  ): 'run' | 'session_paused' | 'session_blocked' | 'cancelled' {
    const session = this.sessionOrThrow(envelope, claim.job.session_id);
    if (
      session.state.state === 'CANCELLED' ||
      session.state.state === 'CANCEL_REQUESTED' ||
      session.state.cancel_generation !== claim.cancel_generation
    ) {
      return 'cancelled';
    }
    if (session.state.state === 'PAUSED' || session.state.state === 'PAUSE_REQUESTED') {
      return 'session_paused';
    }
    if (session.state.state === 'BLOCKED') return 'session_blocked';
    if (!RUNNABLE_STATES.has(session.state.state)) return 'cancelled';
    return 'run';
  }

  private findCommittedCard(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
  ): CouncilCard | null {
    return this.findCommittedCardByIdentity(
      envelope,
      claim.job.session_id,
      claim.descriptor,
      {
        attempt: claim.job.attempt,
        phase_job_key: claim.job.phase_job_key,
        seat_id: claim.seat_id,
        input_sha256: claim.job.input_sha256,
      },
    );
  }

  private findCommittedCardByIdentity(
    envelope: AuthorizationEnvelope,
    sessionId: string,
    descriptor: OperationDescriptor,
    identity: {
      attempt: number;
      phase_job_key: string;
      seat_id: string | null;
      input_sha256: string;
    },
  ): CouncilCard | null {
    // Only seat operations have a committed card to find; other
    // operations resume through their checkpoint and reservation
    // trail. A lookup can only hit when this exact (round, seat,
    // input) was committed as a card, so it cannot false-positive.
    if (identity.seat_id === null) return null;
    try {
      return this.repositories.findCard(
        envelope,
        sessionId,
        descriptor.round,
        identity.seat_id,
        identity.input_sha256,
      );
    } catch {
      return null;
    }
  }

  private stampCard(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    session: StoredSession,
    result: OperationDispatchResult,
  ): CouncilCard {
    return {
      ...result.author,
      host: {
        scope: {
          tenant_id: envelope.tenant_id,
          company_id: envelope.company_id,
          installation_id: envelope.installation_id,
          owner_subject: session.scope.owner_subject,
        },
        operation_id: claim.operation_id,
        route_id: session.spec.model_policy.route_id,
        session_id: claim.job.session_id,
        stamped_at: this.nowIso(),
        source_status: result.source_status ?? 'not_applicable',
      },
    } as CouncilCard;
  }

  private validateStamped(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    session: StoredSession,
    dispatchOperationId: string,
    attemptKind: DispatchAttemptKind,
    card: CouncilCard,
  ): string[] {
    const check = validateCard(card);
    if (!check.ok) {
      return check.issues.map((issue) => `${issue.path}: ${issue.message}`);
    }
    if (this.executor.validateCard) {
      return this.executor.validateCard(
        {
          session,
          claim,
          dispatch_operation_id: dispatchOperationId,
          attempt_kind: attemptKind,
          repair_issues: [],
        },
        card,
      );
    }
    return [];
  }

  private markJobRunning(envelope: AuthorizationEnvelope, claim: JobClaim): void {
    this.db.write((handle) => {
      handle
        .prepare(
          `UPDATE council_jobs SET state = 'running', updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND id = ?
              AND state = 'leased' AND lease_owner = ? AND lease_epoch = ?`,
        )
        .run(
          this.nowIso(),
          envelope.tenant_id,
          envelope.company_id,
          claim.job.id,
          claim.worker_id,
          claim.job_lease_epoch,
        );
    });
  }

  private finishJobRow(
    envelope: AuthorizationEnvelope,
    jobId: string,
    leaseEpoch: number,
    status: 'succeeded' | 'failed' | 'cancelled',
    reasonOrRef: string,
  ): boolean {
    return this.db.write((handle) => {
      const result =
        status === 'succeeded'
          ? handle
              .prepare(
                `UPDATE council_jobs
                    SET state = 'succeeded', terminal_reason = NULL, updated_at = ?
                  WHERE tenant_id = ? AND company_id = ? AND id = ?
                    AND state IN ('leased', 'running') AND lease_epoch = ?`,
              )
              .run(this.nowIso(), envelope.tenant_id, envelope.company_id, jobId, leaseEpoch)
          : handle
              .prepare(
                `UPDATE council_jobs
                    SET state = ?, terminal_reason = ?, last_error_code = ?, updated_at = ?
                  WHERE tenant_id = ? AND company_id = ? AND id = ?
                    AND state IN ('leased', 'running') AND lease_epoch = ?`,
              )
              .run(
                status,
                reasonOrRef,
                reasonOrRef,
                this.nowIso(),
                envelope.tenant_id,
                envelope.company_id,
                jobId,
                leaseEpoch,
              );
      return Number(result.changes) === 1;
    });
  }

  private claimShell(
    session: StoredSession,
    payload: StoredJobPayload,
    descriptor: OperationDescriptor,
    routeSnapshot: PinnedRouteSnapshot,
    operationId: string,
    workerId: string,
    jobLeaseEpoch: number,
    sessionLeaseEpoch: number,
  ): JobClaim {
    return {
      job: {
        id: '',
        session_id: session.spec.session_id,
        attempt: payload.attempt,
        phase_job_key: payload.phase_job_key,
        input_sha256: payload.input_sha256,
        state: 'leased',
        lease_epoch: jobLeaseEpoch,
        cancel_generation: payload.cancel_generation,
        brief_revision: payload.brief_revision,
      },
      operation_id: operationId,
      seat_id: payload.seat_id as SeatId | null,
      worker_id: workerId,
      job_lease_epoch: jobLeaseEpoch,
      session_lease_epoch: sessionLeaseEpoch,
      cancel_generation: session.state.cancel_generation,
      state_version_at_claim: session.state.state_version,
      descriptor,
      route_snapshot: routeSnapshot,
    };
  }

  // ------------------------------------------------------- attempt ledger

  private recordAttempt(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    operationId: string,
    status: 'reserved' | 'dispatched',
    outcomeCode: string | null,
  ): void {
    const snapshot = claim.route_snapshot;
    const now = this.nowIso();
    this.db.write((handle) => {
      handle
        .prepare(
          `INSERT INTO council_provider_attempts
             (tenant_id, company_id, session_id, id, job_id, operation_id,
              seat_id, round, provider_id, provider_config_version, model_ref,
              model_selection_source, status, outcome_code, retry_safe,
              input_tokens, output_tokens, actual_cost_minor, currency,
              request_hash, response_hash, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,
                   NULL, NULL, NULL, ?, ?, NULL, ?, ?)
           ON CONFLICT (tenant_id, company_id, operation_id) DO NOTHING`,
        )
        .run(
          envelope.tenant_id,
          envelope.company_id,
          claim.job.session_id,
          this.ids.newId(),
          claim.job.id,
          operationId,
          claim.seat_id,
          claim.descriptor.round,
          snapshot.providerSlug,
          String(snapshot.routeRevision),
          snapshot.requestedModelOrAlias ?? snapshot.routeId,
          snapshot.selectionSource,
          status,
          outcomeCode,
          claim.descriptor.currency ?? null,
          canonicalHash({ operation_id: operationId, input_sha256: claim.job.input_sha256 }),
          now,
          now,
        );
      if (status === 'dispatched') {
        handle
          .prepare(
            `UPDATE council_provider_attempts SET status = 'dispatched', updated_at = ?
              WHERE tenant_id = ? AND company_id = ? AND operation_id = ?
                AND status = 'reserved'`,
          )
          .run(now, envelope.tenant_id, envelope.company_id, operationId);
      }
    });
  }

  private updateAttempt(
    envelope: AuthorizationEnvelope,
    operationId: string,
    status: 'accepted' | 'failed' | 'cancelled' | 'provider_completion_unknown',
    outcomeCode: string | null,
    facts: {
      actual_minor?: number;
      input_tokens?: number | null;
      output_tokens?: number | null;
      retry_safe?: boolean;
      author?: Record<string, unknown>;
    } = {},
  ): void {
    const now = this.nowIso();
    this.db.write((handle) => {
      handle
        .prepare(
          `UPDATE council_provider_attempts
              SET status = ?, outcome_code = ?, retry_safe = ?,
                  input_tokens = ?, output_tokens = ?, actual_cost_minor = ?,
                  response_hash = ?, updated_at = ?
            WHERE tenant_id = ? AND company_id = ? AND operation_id = ?`,
        )
        .run(
          status,
          outcomeCode,
          facts.retry_safe ? 1 : 0,
          facts.input_tokens ?? null,
          facts.output_tokens ?? null,
          facts.actual_minor ?? null,
          facts.author ? canonicalHash(facts.author) : null,
          now,
          envelope.tenant_id,
          envelope.company_id,
          operationId,
        );
    });
  }

  private attemptStatus(
    envelope: AuthorizationEnvelope,
    operationId: string,
  ): string | null {
    const row = this.db.read((handle) =>
      handle
        .prepare(
          `SELECT status FROM council_provider_attempts
            WHERE tenant_id = ? AND company_id = ? AND operation_id = ?`,
        )
        .get(envelope.tenant_id, envelope.company_id, operationId),
    ) as { status: string } | undefined;
    return row?.status ?? null;
  }

  // ------------------------------------------------------------ checkpoint

  private saveCheckpoint(
    envelope: AuthorizationEnvelope,
    claim: JobClaim,
    session: StoredSession,
    status: JobCheckpoint['status'],
    providerRequestId: string | null,
    usage: JobCheckpoint['usage'],
  ): void {
    const checkpoint: JobCheckpoint = {
      schema_version: 'wise-elders.job-checkpoint/v1',
      installation_id: envelope.installation_id,
      tenant_id: envelope.tenant_id,
      session_id: claim.job.session_id,
      attempt: claim.job.attempt,
      brief_revision: session.state.brief_revision,
      phase: claim.job.phase_job_key,
      seat_id: claim.seat_id,
      input_sha256: claim.job.input_sha256,
      pack_version:
        claim.descriptor.pack_version ?? session.spec.source_pack_version,
      model_policy_revision: claim.descriptor.model_policy_revision ?? 0,
      status,
      provider_request_id: providerRequestId,
      usage,
      committed_at: status === 'accepted' ? this.nowIso() : null,
    };
    this.jobs.saveCheckpoint(envelope, checkpoint, claim.cancel_generation);
  }
}

// ------------------------------------------------------------- helpers

const SECRET_SHAPE = /sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+/g;

function isJobFence(error: unknown): boolean {
  return error instanceof JobRunnerError && error.code === 'JOB_LEASE_FENCED';
}
