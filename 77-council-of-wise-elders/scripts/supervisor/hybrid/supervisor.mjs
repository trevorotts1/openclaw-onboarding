/**
 * Hybrid Council of Wise Elders — persistent engineering supervisor (WER-001).
 *
 * Deterministic core: no LLM calls anywhere in this module. Every function takes
 * its time as explicit injected arguments (nowMs / nowMsFn), so the planner and
 * the state machine are pure over fake time and fully unit-testable.
 *
 * Scope fence for this unit:
 *   - Native-adapter binding is a LATER unit and stays NATIVE_ADAPTER_BINDING =
 *     'UNKNOWN' here. No native API names are invented in this file.
 *   - Installed / scheduled / live-swept evidence is DEFERRED to HYB-05. This
 *     unit produces code + tests only and never claims live operation.
 *
 * Policy values come from the v2.4 plan's embedded policy example and are
 * mirrored by the versioned schema file
 * `wise-elders.hybrid-supervisor-policy/v2` (binding_status TEMPLATE_NOT_BOUND,
 * document_version 2.4).
 */

// ---------------------------------------------------------------------------
// Policy constants (mirrored 1:1 by wise-elders.hybrid-supervisor-policy/v2)
// ---------------------------------------------------------------------------

export const POLICY_SCHEMA_ID = 'wise-elders.hybrid-supervisor-policy/v2';

export const POLICY = Object.freeze({
  full_sweep_interval_seconds: 600,
  health_tick_seconds: 60,
  heartbeat_suspect_after_seconds: 180,
  max_concurrent_workflows: 50,
  max_agents_per_workflow: 10,
  max_total_agents: 500,
  require_independent_non_author_review: true,
  require_exact_head_checks: true,
  require_atomic_expected_head_merge_guard: true,
  standing_repository_merge_authorized: true,
  vercel_required: false,
  cloudflare_build_required: true,
  customer_remote_access_opt_in: true,
  explicit_stop_disables_automatic_engineering_restart: true,
  binding_status: 'TEMPLATE_NOT_BOUND',
  document_version: '2.4',
});

export const FULL_SWEEP_INTERVAL_MS = POLICY.full_sweep_interval_seconds * 1000;
export const HEALTH_TICK_MS = POLICY.health_tick_seconds * 1000;
export const HEARTBEAT_SUSPECT_AFTER_MS = POLICY.heartbeat_suspect_after_seconds * 1000;
/** A scheduled sweep more than due+30s late trips the unhealthy gate. */
export const DUE_UNHEALTHY_GATE_MS = 30 * 1000;
/** sweep_max_runtime: a sweep running past 120s is terminated and recorded TIMEOUT. */
export const SWEEP_MAX_RUNTIME_MS = 120 * 1000;
/** Max supervisor restarts per rolling 30 minutes. */
export const MAX_RESTARTS = 3;
export const RESTART_WINDOW_MS = 30 * 60 * 1000;

/**
 * The native-adapter binding is a later unit. It must stay an explicit UNKNOWN
 * here; no native API name is invented by this unit.
 */
export const NATIVE_ADAPTER_BINDING = Object.freeze({
  status: 'UNKNOWN',
  detail: 'native-adapter binding is a later unit; no native API names are asserted here',
});

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class SupervisorError extends Error {}
export class DuplicateStartError extends SupervisorError {}
export class InvalidTransitionError extends SupervisorError {}
export class StaleFencingGenerationError extends SupervisorError {}
export class NotLeaderError extends SupervisorError {}
export class SweepTimeoutError extends SupervisorError {}

// ---------------------------------------------------------------------------
// Sweep planner — PURE functions over injected fake time.
//
// Schedule anchor rule: next_due_at is computed from the PRIOR DUE plus cadence
// (nextDueAt()). Completion time is never an input, so a slow sweep can never
// drift the cadence to finish-time+600. EXTRA sweeps never consume a scheduled
// slot: they leave next_due_at untouched.
// ---------------------------------------------------------------------------

export const SWEEP_KIND = Object.freeze({ SCHEDULED: 'SCHEDULED', EXTRA: 'EXTRA' });

/** The only outcomes a recorded sweep run may carry. */
const SWEEP_OUTCOME = Object.freeze({ SUCCESS: 'SUCCESS', FAILED: 'FAILED', TIMEOUT: 'TIMEOUT' });

/** next_due_at = prior due + cadence. Never completion+interval. */
export function nextDueAt(previousDueAtMs, cadenceMs = FULL_SWEEP_INTERVAL_MS) {
  if (!Number.isFinite(previousDueAtMs) || !Number.isFinite(cadenceMs) || cadenceMs <= 0) {
    throw new TypeError('nextDueAt: finite previousDueAtMs and positive cadenceMs required');
  }
  return previousDueAtMs + cadenceMs;
}

/** Fixed schedule anchor: first due is the anchor itself. */
export function makeSweepSchedule({ anchorMs, cadenceMs = FULL_SWEEP_INTERVAL_MS } = {}) {
  if (!Number.isFinite(anchorMs)) throw new TypeError('makeSweepSchedule: anchorMs required');
  return {
    anchorMs,
    cadenceMs,
    nextDueAtMs: anchorMs,
    runs: [],
  };
}

/** Pure due check against fake time. due+30s late trips the unhealthy gate. */
export function dueSweep(schedule, nowMs) {
  const latenessMs = nowMs - schedule.nextDueAtMs;
  if (latenessMs < 0) {
    return { due: false, kind: SWEEP_KIND.SCHEDULED, dueAtMs: schedule.nextDueAtMs, latenessMs: 0, unhealthy: false };
  }
  return {
    due: true,
    kind: SWEEP_KIND.SCHEDULED,
    dueAtMs: schedule.nextDueAtMs,
    latenessMs,
    unhealthy: latenessMs >= DUE_UNHEALTHY_GATE_MS,
  };
}

/**
 * Apply one sweep result to the schedule (pure reducer, returns a new schedule).
 *
 * result: { kind, dueAtMs?, startedAtMs, finishedAtMs, outcome }
 *   outcome: 'SUCCESS' | 'FAILED' | 'TIMEOUT'
 *
 * SCHEDULED: advances next_due_at to prior DUE + cadence and records the real
 *   lateness. EXTRA: recorded with consumesScheduledSlot=false and leaves
 *   next_due_at untouched.
 */
export function applySweepResult(schedule, result) {
  const { kind, startedAtMs, finishedAtMs, outcome } = result;
  if (!Object.values(SWEEP_KIND).includes(kind)) throw new TypeError(`applySweepResult: bad kind ${kind}`);
  if (!Object.values(SWEEP_OUTCOME).includes(outcome)) {
    throw new TypeError(
      `applySweepResult: bad outcome ${outcome}; expected one of ${Object.values(SWEEP_OUTCOME).join('/')}`,
    );
  }
  if (!Number.isFinite(startedAtMs) || !Number.isFinite(finishedAtMs)) {
    throw new TypeError('applySweepResult: startedAtMs/finishedAtMs required');
  }
  const run = {
    kind,
    startedAtMs,
    finishedAtMs,
    runtimeMs: finishedAtMs - startedAtMs,
    outcome,
    successful: outcome === SWEEP_OUTCOME.SUCCESS,
  };
  if (kind === SWEEP_KIND.EXTRA) {
    return {
      ...schedule,
      runs: [...schedule.runs, { ...run, consumesScheduledSlot: false }],
    };
  }
  const dueAtMs = result.dueAtMs ?? schedule.nextDueAtMs;
  return {
    ...schedule,
    nextDueAtMs: nextDueAt(dueAtMs, schedule.cadenceMs),
    runs: [
      ...schedule.runs,
      {
        ...run,
        dueAtMs,
        latenessMs: startedAtMs - dueAtMs,
        consumesScheduledSlot: true,
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Lease store — ownership-safe cleanup. Only the owning token may release.
// ---------------------------------------------------------------------------

export function createLeaseStore() {
  let owner = null;
  return {
    acquire(token) {
      if (owner !== null && owner !== token) return { ok: false, reason: 'held', owner };
      owner = token;
      return { ok: true, owner: token };
    },
    release(token) {
      if (owner !== token) return { ok: false, reason: 'foreign_owner', owner };
      owner = null;
      return { ok: true };
    },
    owner() {
      return owner;
    },
  };
}

// ---------------------------------------------------------------------------
// Sweep runner — sweep_max_runtime 120s, ownership-safe cleanup on EVERY
// return path and on exceptions.
// ---------------------------------------------------------------------------

/** Settles the sweep race when the runtime budget is breached. */
const SWEEP_TIMEOUT = Symbol('sweep-timeout');

/**
 * work({ kind, deadlineMs, shouldAbort }) may be async. The work is raced
 * against the runtime budget: when sweep_max_runtime elapses the sweep RETURNS
 * TIMEOUT even if work never settles, and any result arriving after the breach
 * is discarded, never recorded. Cleanup (lease release) runs in a finally block
 * on success, failure, timeout and exception alike, and only ever releases the
 * runner's own lease.
 *
 * `scheduler` is injectable ({setTimeout, clearTimeout}); default globalThis.
 * `nowMsFn` is injectable fake time; default Date.now.
 */
export async function runSweep({
  kind,
  ownerToken,
  leaseStore,
  work,
  nowMsFn = () => Date.now(),
  scheduler = globalThis,
  sweepMaxRuntimeMs = SWEEP_MAX_RUNTIME_MS,
} = {}) {
  if (typeof work !== 'function') throw new TypeError('runSweep: work fn required');
  const startedAtMs = nowMsFn();
  const lease = leaseStore.acquire(ownerToken);
  if (!lease.ok) return { ok: false, outcome: 'REFUSED', reason: 'lease_held', startedAtMs };

  let timedOut = false;
  let timerId = null;
  const shouldAbort = () => timedOut;
  const budgetBreached = (finishedAtMs) => timedOut || finishedAtMs - startedAtMs > sweepMaxRuntimeMs;
  const timeoutError = (cause) =>
    new SweepTimeoutError(
      `sweep exceeded sweep_max_runtime ${sweepMaxRuntimeMs}ms`,
      cause === undefined ? undefined : { cause },
    );
  try {
    // The timer both flips shouldAbort (cooperative work) and settles the race
    // below, so work that never settles cannot hold the sweep or its lease.
    let timeoutSignal = null;
    if (scheduler && typeof scheduler.setTimeout === 'function') {
      timeoutSignal = new Promise((resolve) => {
        timerId = scheduler.setTimeout(() => {
          timedOut = true;
          resolve(SWEEP_TIMEOUT);
        }, sweepMaxRuntimeMs);
      });
    }
    const workPromise = work({ kind, deadlineMs: startedAtMs + sweepMaxRuntimeMs, shouldAbort });
    const workResult = timeoutSignal ? await Promise.race([workPromise, timeoutSignal]) : await workPromise;
    const finishedAtMs = nowMsFn();
    const runtimeMs = finishedAtMs - startedAtMs;
    if (workResult === SWEEP_TIMEOUT || budgetBreached(finishedAtMs)) {
      return {
        ok: false,
        outcome: SWEEP_OUTCOME.TIMEOUT,
        kind,
        startedAtMs,
        finishedAtMs,
        runtimeMs,
        error: timeoutError(),
      };
    }
    return {
      ok: true,
      outcome: SWEEP_OUTCOME.SUCCESS,
      kind,
      startedAtMs,
      finishedAtMs,
      runtimeMs,
      workResult,
    };
  } catch (error) {
    const finishedAtMs = nowMsFn();
    // A breached runtime budget outranks whatever work threw: the sweep was
    // already terminated at its deadline, so the record is TIMEOUT, not FAILED.
    if (budgetBreached(finishedAtMs)) {
      return {
        ok: false,
        outcome: SWEEP_OUTCOME.TIMEOUT,
        kind,
        startedAtMs,
        finishedAtMs,
        runtimeMs: finishedAtMs - startedAtMs,
        error: timeoutError(error),
      };
    }
    return {
      ok: false,
      outcome: SWEEP_OUTCOME.FAILED,
      kind,
      startedAtMs,
      finishedAtMs,
      error,
    };
  } finally {
    if (timerId !== null && scheduler && typeof scheduler.clearTimeout === 'function') {
      scheduler.clearTimeout(timerId);
    }
    leaseStore.release(ownerToken); // ownership-safe: no-op refusal for foreign owners
  }
}

// ---------------------------------------------------------------------------
// Deterministic health observer — ~60s tick (HEALTH_TICK_MS), NO LLM calls.
// Pure function of injected observations.
// ---------------------------------------------------------------------------

export const HEALTH_STATUS = Object.freeze({ HEALTHY: 'HEALTHY', DEGRADED: 'DEGRADED', UNHEALTHY: 'UNHEALTHY' });

export function observeHealth({ nowMs, lastHeartbeatAtMs, dueInfo }) {
  const reasons = [];
  let status = HEALTH_STATUS.HEALTHY;

  if (Number.isFinite(lastHeartbeatAtMs) && nowMs - lastHeartbeatAtMs > HEARTBEAT_SUSPECT_AFTER_MS) {
    reasons.push('heartbeat_suspect');
    status = HEALTH_STATUS.DEGRADED;
  }
  if (dueInfo && dueInfo.due && dueInfo.unhealthy) {
    reasons.push('sweep_overdue'); // due+30s gate tripped
    status = HEALTH_STATUS.UNHEALTHY;
  }
  return { status, checkedAtMs: nowMs, tickIntervalMs: HEALTH_TICK_MS, reasons };
}

// ---------------------------------------------------------------------------
// Durable leader / fencing-generation state model.
//
// Every successful claim bumps the fencing generation. Commits must carry the
// generation they were issued under: a stale generation can never commit, even
// if its holder was leader when it started.
// ---------------------------------------------------------------------------

export function createLeadership({ holderId = null, fencingGeneration = 0 } = {}) {
  return { holderId, fencingGeneration };
}

export function claimLeadership(lead, claimantId) {
  if (typeof claimantId !== 'string' || claimantId.length === 0) {
    throw new TypeError('claimLeadership: claimantId required');
  }
  return { holderId: claimantId, fencingGeneration: lead.fencingGeneration + 1 };
}

export function commitUnderFence(lead, { fencingGeneration, actorId, apply }) {
  // Generation is the fencing authority and is checked first: a stale
  // generation can never commit, whatever identity carries it.
  if (fencingGeneration !== lead.fencingGeneration) {
    throw new StaleFencingGenerationError(
      `stale fencing generation ${fencingGeneration}; current is ${lead.fencingGeneration}`,
    );
  }
  if (actorId !== lead.holderId) throw new NotLeaderError(`actor ${actorId} is not the current leader`);
  const value = typeof apply === 'function' ? apply() : undefined;
  return { ok: true, fencingGeneration: lead.fencingGeneration, value };
}

/** Durable round-trip: JSON-safe serialization with shape validation. */
export function serializeLeadership(lead) {
  return JSON.stringify({ holderId: lead.holderId, fencingGeneration: lead.fencingGeneration });
}

export function parseLeadership(text) {
  const parsed = JSON.parse(text);
  if (typeof parsed.fencingGeneration !== 'number' || !Number.isInteger(parsed.fencingGeneration)) {
    throw new TypeError('parseLeadership: fencingGeneration must be an integer');
  }
  if (parsed.holderId !== null && typeof parsed.holderId !== 'string') {
    throw new TypeError('parseLeadership: holderId must be string or null');
  }
  return { holderId: parsed.holderId, fencingGeneration: parsed.fencingGeneration };
}

// ---------------------------------------------------------------------------
// Supervisor state machine:
//   STARTING -> RECONCILING -> HEALTHY | DEGRADED | PAUSED -> STOPPING -> STOPPED
// Explicit-stop fence: an explicit stop permanently disables automatic
// engineering restart (policy explicit_stop_disables_automatic_engineering_restart).
// ---------------------------------------------------------------------------

export const SUPERVISOR_STATE = Object.freeze({
  STARTING: 'STARTING',
  RECONCILING: 'RECONCILING',
  HEALTHY: 'HEALTHY',
  DEGRADED: 'DEGRADED',
  PAUSED: 'PAUSED',
  STOPPING: 'STOPPING',
  STOPPED: 'STOPPED',
});

const ALLOWED_TRANSITIONS = Object.freeze({
  [SUPERVISOR_STATE.STARTING]: [SUPERVISOR_STATE.RECONCILING, SUPERVISOR_STATE.STOPPING],
  [SUPERVISOR_STATE.RECONCILING]: [SUPERVISOR_STATE.HEALTHY, SUPERVISOR_STATE.DEGRADED, SUPERVISOR_STATE.PAUSED, SUPERVISOR_STATE.STOPPING],
  [SUPERVISOR_STATE.HEALTHY]: [SUPERVISOR_STATE.RECONCILING, SUPERVISOR_STATE.DEGRADED, SUPERVISOR_STATE.PAUSED, SUPERVISOR_STATE.STOPPING],
  [SUPERVISOR_STATE.DEGRADED]: [SUPERVISOR_STATE.RECONCILING, SUPERVISOR_STATE.HEALTHY, SUPERVISOR_STATE.PAUSED, SUPERVISOR_STATE.STOPPING],
  [SUPERVISOR_STATE.PAUSED]: [SUPERVISOR_STATE.RECONCILING, SUPERVISOR_STATE.STOPPING],
  [SUPERVISOR_STATE.STOPPING]: [SUPERVISOR_STATE.STOPPED],
  [SUPERVISOR_STATE.STOPPED]: [SUPERVISOR_STATE.STARTING],
});

export function createSupervisor({ supervisorId } = {}) {
  return {
    supervisorId: supervisorId ?? 'supervisor',
    state: SUPERVISOR_STATE.STARTING,
    explicitStop: false,
    lastReconciliation: null,
  };
}

/** Duplicate start refuses: only a STOPPED machine may start. */
export function startSupervisor(machine) {
  if (machine.state !== SUPERVISOR_STATE.STOPPED) {
    throw new DuplicateStartError(`start refused: supervisor already running in state ${machine.state}`);
  }
  return { ...machine, state: SUPERVISOR_STATE.STARTING, explicitStop: false };
}

export function transition(machine, nextState) {
  const allowed = ALLOWED_TRANSITIONS[machine.state] ?? [];
  if (!allowed.includes(nextState)) {
    throw new InvalidTransitionError(`${machine.state} -> ${nextState} is not a legal transition`);
  }
  return { ...machine, state: nextState };
}

/** Explicit stop: sets the fence and moves to STOPPING (any non-STOPPED state). */
export function requestExplicitStop(machine) {
  if (machine.state === SUPERVISOR_STATE.STOPPED) return { ...machine, explicitStop: true };
  return { ...machine, explicitStop: true, state: SUPERVISOR_STATE.STOPPING };
}

export function finishStop(machine) {
  return transition({ ...machine, explicitStop: true }, SUPERVISOR_STATE.STOPPED);
}

/**
 * Reconciliation outcomes: PAUSED / DEGRADED / FAILED are NEVER marked as
 * successful reconciliation. Only a HEALTHY outcome is.
 */
export function recordReconciliationOutcome(machine, { outcome, atMs }) {
  const successfulReconciliation = outcome === SUPERVISOR_STATE.HEALTHY;
  const record = {
    outcome,
    atMs,
    successfulReconciliation,
  };
  const nextState =
    outcome === SUPERVISOR_STATE.HEALTHY
      ? SUPERVISOR_STATE.HEALTHY
      : outcome === SUPERVISOR_STATE.PAUSED
        ? SUPERVISOR_STATE.PAUSED
        : outcome === SUPERVISOR_STATE.DEGRADED
          ? SUPERVISOR_STATE.DEGRADED
          : SUPERVISOR_STATE.DEGRADED;
  return { machine: transition(machine, nextState), record };
}

// ---------------------------------------------------------------------------
// Restart governor — max 3 supervisor restarts per rolling 30 minutes.
// ---------------------------------------------------------------------------

export function createRestartGovernor({ maxRestarts = MAX_RESTARTS, windowMs = RESTART_WINDOW_MS, restarts = [] } = {}) {
  return { maxRestarts, windowMs, restarts };
}

function pruneRestarts(governor, nowMs) {
  return governor.restarts.filter((t) => nowMs - t < governor.windowMs);
}

export function canRestart(governor, nowMs) {
  return pruneRestarts(governor, nowMs).length < governor.maxRestarts;
}

export function recordRestart(governor, nowMs) {
  return { ...governor, restarts: [...pruneRestarts(governor, nowMs), nowMs] };
}

/**
 * Automatic engineering restart. Refused outright once the explicit-stop fence
 * is set, and refused again once the rolling restart budget is exhausted.
 */
export function attemptAutomaticRestart(machine, governor, nowMs) {
  if (machine.explicitStop) {
    return { ok: false, reason: 'explicit_stop_fence', machine, governor };
  }
  if (!canRestart(governor, nowMs)) {
    return { ok: false, reason: 'restart_budget_exhausted', machine, governor };
  }
  return {
    ok: true,
    reason: 'restarted',
    machine: { ...machine, state: SUPERVISOR_STATE.STARTING },
    governor: recordRestart(governor, nowMs),
  };
}
