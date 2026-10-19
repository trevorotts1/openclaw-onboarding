/**
 * Council worker supervision (CWE-027, directive Section 15.8).
 *
 * The scoped worker lifecycle functions the directive names:
 * startCouncilWorkers, wakeCouncilWorkers, stopCouncilWorkers. They
 * are NEW scoped functions in the portable runtime: the host registers
 * only a short council maintenance/admission wakeup with its own
 * scheduler (never a 27-turn council inside the host's 90-second
 * runLeasedJob lease) and calls startCouncilWorkers once per
 * supervised process; the workers themselves poll the durable store.
 *
 * Registration integrity (T158):
 * - Exactly one supervisor per supervisor id per process: a second
 *   startCouncilWorkers for the same id returns the existing handle
 *   and spawns nothing. Hot reload, restart, and shutdown therefore
 *   cannot duplicate workers for the same job; the durable claim CAS
 *   in the runner is the second line of defense even if two processes
 *   poll the same store.
 * - Polling is state-driven, not wakeup-driven: a lost wakeup costs at
 *   most one interval, because every cycle re-reads the durable queue.
 *   wakeCouncilWorkers exists to cut latency after an enqueue, not to
 *   carry correctness.
 * - Boot reconciliation runs before the first claim: expired leases
 *   are recovered and lapsed budget holds expired (runner
 *   reconcileScope), so a restart strands no durable queue work and
 *   resurrects no uncertain operation.
 * - An ephemeral-only hosting surface (no approved durable worker)
 *   refuses with WORKER_CAPABILITY_UNAVAILABLE instead of silently
 *   pretending to schedule (Section 15.8).
 */

import type { AuthorizationEnvelope } from '../persistence/envelope.js';
import {
  DurableJobRunner,
  DEFAULT_POLL_INTERVAL_MS,
  type RunnerTimers,
  systemTimers,
} from './runner.js';
import { JobRunnerError } from './errors.js';

export interface CouncilWorkerScope {
  envelope: AuthorizationEnvelope;
  worker_id: string;
}

export interface StartCouncilWorkersOptions {
  runner: DurableJobRunner;
  scopes: CouncilWorkerScope[];
  /** Registry key; default 'council-workers'. One live supervisor per key. */
  supervisor_id?: string;
  /** Idle poll interval; default 1 second (Section 15.8), configurable. */
  poll_interval_ms?: number;
  timers?: RunnerTimers;
  /**
   * Host capability declaration: a surface that cannot run durable
   * workers (ephemeral-only hosting without an approved worker) must
   * say so here; startCouncilWorkers then refuses typed instead of
   * silently supporting what it cannot do.
   */
  durable_worker_capability?: boolean;
  /**
   * Every claim, reconcile or execution failure is reported here with the
   * session it concerns (when known); never swallowed.
   */
  on_error?: (error: unknown, context?: { session_id?: string }) => void;
}

export interface CouncilWorkerHandle {
  supervisor_id: string;
  running: boolean;
  /** Number of poll cycles started (observability for tests/hosts). */
  cycles_started: number;
  /** Claims currently executing under this supervisor. */
  in_flight: number;
  wake(): void;
  stop(): Promise<void>;
}

const registry = new Map<string, CouncilWorkerSupervisor>();

class CouncilWorkerSupervisor implements CouncilWorkerHandle {
  readonly supervisor_id: string;
  running = false;
  cycles_started = 0;
  private readonly inFlight = new Set<Promise<unknown>>();
  private cancelPoll: (() => void) | null = null;
  private cycleActive = false;

  constructor(private readonly options: StartCouncilWorkersOptions) {
    this.supervisor_id = options.supervisor_id ?? 'council-workers';
  }

  get in_flight(): number {
    return this.inFlight.size;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    // Boot reconciliation before any claim: recover expired leases
    // and expire lapsed holds in every supervised scope.
    for (const scope of this.options.scopes) {
      try {
        this.options.runner.reconcileScope(scope.envelope, scope.worker_id);
      } catch (error) {
        this.options.on_error?.(error);
      }
    }
    const timers = this.options.timers ?? systemTimers;
    this.cancelPoll = timers.every(
      this.options.poll_interval_ms ?? DEFAULT_POLL_INTERVAL_MS,
      () => this.wake(),
    );
    this.wake();
  }

  /**
   * Run one poll cycle now: for each scope, claim runnable work and
   * execute it. Lost wakeups are repaired by the next interval cycle
   * reading the same durable queue; a wake during an active cycle is
   * folded into it (no duplicate claims can result: claiming is a
   * durable compare-and-swap).
   */
  wake(): void {
    if (!this.running || this.cycleActive) return;
    this.cycleActive = true;
    this.cycles_started += 1;
    try {
      for (const scope of this.options.scopes) {
        // Recover expired leases every cycle, not only at boot: a stuck
        // running job / dispatched attempt resolves truthfully once its
        // lease lapses (live leases are never touched).
        try {
          this.options.runner.reconcileScope(scope.envelope, scope.worker_id);
        } catch (error) {
          this.options.on_error?.(error);
        }
        this.pollScope(scope);
      }
    } finally {
      this.cycleActive = false;
    }
  }

  private pollScope(scope: CouncilWorkerScope): void {
    const { runner } = this.options;
    const sessions = runner.listSessions(scope.envelope);
    for (const session of sessions) {
      // Claim and execute until this session yields no claim; each
      // execution is tracked so stop() can observe in-flight work.
      for (;;) {
        let claim;
        try {
          claim = runner.claimNextOperation(
            scope.envelope,
            session.spec.session_id,
            scope.worker_id,
          );
        } catch (error) {
          this.options.on_error?.(error, { session_id: session.spec.session_id });
          break;
        }
        if (!claim) break;
        const execution = runner
          .executeClaimedOperation(scope.envelope, claim)
          .catch((error: unknown) => {
            // A simulated (or real) crash leaves durable state for
            // reconciliation; other errors are reported, never hidden.
            this.options.on_error?.(error, { session_id: session.spec.session_id });
            return null;
          });
        this.inFlight.add(execution);
        void execution.finally(() => this.inFlight.delete(execution));
        // One execution per session per cycle: a session's operations
        // are ordered under one fencing generation at a time.
        break;
      }
    }
  }

  async stop(): Promise<void> {
    this.running = false;
    this.cancelPoll?.();
    this.cancelPoll = null;
    // In-flight operations finish under their own leases and fences;
    // stop() waits for the current executions to settle but never
    // cancels durable work: unclaimed and unrecovered work remains in
    // the store for the next supervisor (T158).
    await Promise.allSettled([...this.inFlight]);
  }
}

/**
 * Start the council workers for this process. Registering the same
 * supervisor id twice returns the existing handle (idempotent across
 * hot reloads); use stopCouncilWorkers before starting a replacement.
 */
export function startCouncilWorkers(
  options: StartCouncilWorkersOptions,
): CouncilWorkerHandle {
  if (options.durable_worker_capability === false) {
    throw new JobRunnerError(
      'WORKER_CAPABILITY_UNAVAILABLE',
      'This hosting surface cannot run durable council workers (ephemeral-only hosting without an approved worker). Durable deliberation scheduling is refused rather than silently unsupported.',
      { detail: { supervisor_id: options.supervisor_id ?? 'council-workers' } },
    );
  }
  const id = options.supervisor_id ?? 'council-workers';
  const existing = registry.get(id);
  if (existing && existing.running) return existing;
  const supervisor = new CouncilWorkerSupervisor(options);
  registry.set(id, supervisor);
  supervisor.start();
  return supervisor;
}

/** Trigger an immediate poll cycle (cuts enqueue-to-claim latency). */
export function wakeCouncilWorkers(handle: CouncilWorkerHandle): void {
  handle.wake();
}

/** Stop a supervisor and unregister it, leaving durable work intact. */
export async function stopCouncilWorkers(
  handle: CouncilWorkerHandle,
): Promise<void> {
  await handle.stop();
  if (registry.get(handle.supervisor_id) === handle) {
    registry.delete(handle.supervisor_id);
  }
}

/** Test and diagnostics surface: the live supervisor ids in this process. */
export function liveCouncilWorkerSupervisors(): string[] {
  return [...registry.entries()]
    .filter(([, supervisor]) => supervisor.running)
    .map(([id]) => id);
}
