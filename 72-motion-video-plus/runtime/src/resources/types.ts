// Render resource budget types for Skill 72 Motion Graphics V2
// (Directive MG-028).
//
// Why this module exists: render concurrency used to be a per-caller
// choice. Ten authors with eight render workers each can overload a
// client machine even when every individual worker count looks
// reasonable, because nothing accounted for the SUM. This module is
// the single accounting point: every browser or encoder launch the
// production adapters perform is preceded by a reservation against a
// machine-wide budget, and the reservation is what the budget counts,
// not the caller's intentions.
//
// The budget is deliberately engine-agnostic. Adapters declare WHAT a
// render operation will hold (a resource profile: estimated peak
// memory, browser units, encoder units, intermediate disk, and the
// engine's own nested concurrency) and the budget decides whether the
// machine can hold it alongside everything already reserved, after the
// host reserve has been subtracted. Nested engine concurrency (Remotion
// render tabs, Hyperframes CLI workers) is accounted INSIDE the
// caller's reservation: the profile carries the nested count and the
// memory estimate is sized for it, so an engine multiplying its own
// workers never multiplies the machine's load invisibly.

import type { Engine } from "../adapters/types";

/** One render operation's declared resource footprint. Estimates come
 * from the measured profiles in profiles.ts (MG-028 measurement
 * evidence, tests/evidence/mg028/measurements.json) with a stated
 * margin; they are budgets to account against, not predictions. */
export interface ResourceProfile {
  /** Estimated peak resident memory of the whole engine process tree
   * (browser + encoder + driver), in megabytes. */
  memoryMB: number;
  /** Browser instances this operation keeps alive at once. A Remotion
   * render is one browser (its tabs are nested concurrency, below);
   * a Hyperframes render is one browser inside the CLI. */
  browserUnits: number;
  /** Encoder instances this operation keeps alive at once (ffmpeg or
   * the engine's internal muxer). */
  encodeUnits: number;
  /** Intermediate disk the operation may hold at once, in megabytes:
   * scene segments, frame chunks, scaled variants. Bounded so large
   * jobs process in segments instead of materializing everything. */
  diskMB: number;
  /** The engine's own internal parallelism inside this reservation:
   * Remotion render tabs, or Hyperframes CLI workers. The adapters
   * pass this value to the engine so the engine's nesting matches
   * what the reservation accounted for. */
  nestedConcurrency: number;
  /** Human-readable profile name, recorded in the reservation ledger. */
  label: string;
}

/** The machine-wide budget a reservation is accounted against. The
 * memory ceiling is already net of the host reserve: the reserve is
 * recorded here for evidence, and deriveBudgetPolicy subtracts it
 * before any reservation is counted. */
export interface BudgetPolicy {
  /** Directory holding the cross-process reservation ledger. Shared by
   * every render process on the machine, so the budget is global, not
   * per-process. */
  stateDir: string;
  /** True when stateDir is the shared runtime's state directory (the
   * normal case). False when discovery failed and a per-user temp
   * directory is in use: the budget still bounds this machine's
   * cooperating processes that resolve the same directory, and the
   * preflight report says which case applies. */
  sharedStateDir: boolean;
  /** Memory kept for the host OS, the agent processes, and active
   * services; never available to reservations. */
  hostReserveMB: number;
  /** Total memory reservations may sum to (machine total minus the
   * host reserve, unless explicitly overridden). */
  memoryBudgetMB: number;
  /** Maximum browser units alive across all reservations. */
  maxBrowserUnits: number;
  /** Maximum encoder units alive across all reservations. */
  maxEncodeUnits: number;
  /** Maximum intermediate disk reservations may sum to. */
  maxDiskMB: number;
  /** How long an acquire waits for capacity before failing. */
  acquireTimeoutMs: number;
  /** A reservation whose heartbeat is older than this AND whose owner
   * process is gone is reaped as stale. A reservation whose owner is
   * gone is reaped regardless of heartbeat age. */
  staleHeartbeatMs: number;
}

/** One reservation as recorded in the on-disk ledger. The ledger is
 * the cross-process source of truth: capacity checks sum these
 * records, and a crashed holder leaves a record that the next acquire
 * reaps by owner liveness. */
export interface ReservationRecord {
  id: string;
  jobId: string;
  engine: Engine;
  /** Adapter operation name, for example "renderFinal", "renderStill". */
  operation: string;
  /** Process that owns the reservation. */
  pid: number;
  /** ISO timestamp of acquisition. */
  acquiredAt: string;
  /** ISO timestamp of the last heartbeat from the owner. */
  heartbeatAt: string;
  profile: ResourceProfile;
}

/** What a caller asks the budget for. */
export interface ReservationRequest {
  engine: Engine;
  jobId: string;
  operation: string;
  /** Profile override; defaults to the measured profile for the
   * engine and operation (profiles.ts). */
  profile?: ResourceProfile;
}

/** Options governing one acquire wait. */
export interface AcquireOptions {
  /** Per-call timeout override (defaults to the policy's). */
  timeoutMs?: number;
  /** Polled while waiting; when it returns true the wait aborts with
   * a ResourceCancelledError. Adapters pass their cancellation state
   * (dispatcher abort signal, adapter cancel marks). */
  isCancelled?: () => boolean;
}

/** A live reservation. release() is idempotent. Within one process,
 * acquiring again for the same job returns this same reservation with
 * a bumped hold count (adapter operations nest: a Remotion final is a
 * video render plus a still render); the ledger record is removed
 * only when the last hold releases. */
export interface Reservation {
  readonly id: string;
  readonly jobId: string;
  readonly engine: Engine;
  readonly operation: string;
  readonly profile: ResourceProfile;
  readonly acquiredAt: string;
  release(): Promise<void>;
}

/** The budget could not satisfy the request within the timeout. */
export class ResourceExhaustedError extends Error {
  readonly engine: Engine;
  readonly jobId: string;
  readonly waitedMs: number;
  constructor(engine: Engine, jobId: string, waitedMs: number, detail: string) {
    super(
      `Render resource budget exhausted for job ${jobId} (${engine}) after waiting ` +
        `${waitedMs} ms: ${detail}. The render was not started; no browser or encoder ` +
        "was launched. Retry when capacity frees or raise the budget explicitly."
    );
    this.name = "ResourceExhaustedError";
    this.engine = engine;
    this.jobId = jobId;
    this.waitedMs = waitedMs;
  }
}

/** The acquire wait was cancelled by the caller. */
export class ResourceCancelledError extends Error {
  readonly engine: Engine;
  readonly jobId: string;
  constructor(engine: Engine, jobId: string) {
    super(`Render resource acquisition for job ${jobId} (${engine}) was cancelled while waiting.`);
    this.name = "ResourceCancelledError";
    this.engine = engine;
    this.jobId = jobId;
  }
}

/** Measured capacity of the machine the preflight runs on. */
export interface MachineCapacity {
  totalMemMB: number;
  freeMemMB: number;
  cpuCount: number;
  platform: string;
  nodeVersion: string;
  measuredAt: string;
}
