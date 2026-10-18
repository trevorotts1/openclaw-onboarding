// Fixed-cadence full-sweep planner for the Hybrid Council of Wise Elders
// supervisor. Every exported function is PURE over injected time: no Date.now,
// no timers, no I/O. The schedule is anchored, so a late or long-running sweep
// can never drag the next due time to finish+interval.
export const SWEEP_PLANNER_SCHEMA = "wise-elders.hybrid-supervisor-sweep-planner/v1";
export const SWEEP_CADENCE_MS_DEFAULT = 600_000; // full_sweep_interval_seconds 600
export const SWEEP_UNHEALTHY_GATE_MS = 30_000; // due + 30s unhealthy gate
export const SWEEP_MAX_RUNTIME_MS = 120_000;

const DECISIONS = Object.freeze(["IDLE", "SCHEDULED", "EXTRA"]);

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function requirePlannerState(state) {
  if (!state || state.schema !== SWEEP_PLANNER_SCHEMA) {
    throw new TypeError(`state must be a ${SWEEP_PLANNER_SCHEMA} object`);
  }
  requireInteger(state.anchor_ms, "state.anchor_ms");
  requireInteger(state.next_due_at_ms, "state.next_due_at_ms");
  requireInteger(state.cadence_ms, "state.cadence_ms");
  if (state.cadence_ms <= 0) throw new RangeError("state.cadence_ms must be positive");
  // Invariant that makes drift impossible: every due slot stays on the anchor.
  if ((state.next_due_at_ms - state.anchor_ms) % state.cadence_ms !== 0) {
    throw new RangeError("state.next_due_at_ms is not aligned to the fixed schedule anchor");
  }
  return state;
}

export function createPlannerState({ anchor_ms, cadence_ms = SWEEP_CADENCE_MS_DEFAULT }) {
  requireInteger(anchor_ms, "anchor_ms");
  requireInteger(cadence_ms, "cadence_ms");
  if (cadence_ms <= 0) throw new RangeError("cadence_ms must be positive");
  return Object.freeze({
    schema: SWEEP_PLANNER_SCHEMA,
    anchor_ms,
    cadence_ms,
    next_due_at_ms: anchor_ms,
    scheduled_sweeps: 0,
    extra_sweeps: 0,
    skipped_slots: 0,
    last_claim_at_ms: null,
    last_completion_at_ms: null,
    last_completion_kind: null,
  });
}

// A scheduled slot that has not been claimed within the unhealthy gate is a
// health problem, not a normal late start. The gate is reported on the claim.
function gateFor(dueAtMs, nowMs) {
  const overdueByMs = Math.max(0, nowMs - dueAtMs);
  return Object.freeze({
    due_at_ms: dueAtMs,
    overdue_by_ms: overdueByMs,
    unhealthy: overdueByMs > SWEEP_UNHEALTHY_GATE_MS,
    limit_ms: SWEEP_UNHEALTHY_GATE_MS,
  });
}

// planSweep decides what the supervisor should run at `now_ms`.
// - EXTRA never consumes a scheduled slot: next_due_at_ms is untouched.
// - SCHEDULED claims the due slot and advances by WHOLE cadence steps from the
//   prior due (never from completion), skipping slots missed while late.
export function planSweep(state, { now_ms, extra_requested = false } = {}) {
  requirePlannerState(state);
  requireInteger(now_ms, "now_ms");

  if (extra_requested) {
    const next = Object.freeze({
      ...state,
      extra_sweeps: state.extra_sweeps + 1,
      last_claim_at_ms: now_ms,
    });
    return Object.freeze({
      state: next,
      decision: Object.freeze({
        kind: "EXTRA",
        consumes_scheduled_slot: false,
        scheduled_due_at_ms: state.next_due_at_ms,
        anchor_ms: state.anchor_ms,
        due_at_ms: null,
        lateness_ms: 0,
        skipped_slots: 0,
        gate: null,
      }),
    });
  }

  if (now_ms < state.next_due_at_ms) {
    return Object.freeze({
      state,
      decision: Object.freeze({
        kind: "IDLE",
        consumes_scheduled_slot: false,
        scheduled_due_at_ms: state.next_due_at_ms,
        anchor_ms: state.anchor_ms,
        due_at_ms: null,
        lateness_ms: 0,
        skipped_slots: 0,
        gate: null,
      }),
    });
  }

  const dueAtMs = state.next_due_at_ms;
  const latenessMs = now_ms - dueAtMs;
  let next = dueAtMs + state.cadence_ms;
  let skipped = 0;
  while (next <= now_ms) {
    next += state.cadence_ms;
    skipped += 1;
  }
  if ((next - state.anchor_ms) % state.cadence_ms !== 0) {
    throw new Error("planner produced a due slot off the fixed schedule anchor");
  }

  const nextState = Object.freeze({
    ...state,
    next_due_at_ms: next,
    scheduled_sweeps: state.scheduled_sweeps + 1,
    skipped_slots: state.skipped_slots + skipped,
    last_claim_at_ms: now_ms,
  });
  return Object.freeze({
    state: nextState,
    decision: Object.freeze({
      kind: "SCHEDULED",
      consumes_scheduled_slot: true,
      scheduled_due_at_ms: dueAtMs,
      anchor_ms: state.anchor_ms,
      due_at_ms: dueAtMs,
      lateness_ms: latenessMs,
      skipped_slots: skipped,
      gate: gateFor(dueAtMs, now_ms),
    }),
  });
}

// Completion never touches next_due_at_ms. The slot was already advanced at
// claim time from the previous due, so finish-time cannot influence the cadence.
export function completeSweep(state, { kind, finished_at_ms }) {
  requirePlannerState(state);
  requireInteger(finished_at_ms, "finished_at_ms");
  if (!DECISIONS.includes(kind)) throw new RangeError(`unknown sweep kind ${kind}`);
  return Object.freeze({
    ...state,
    last_completion_at_ms: finished_at_ms,
    last_completion_kind: kind,
  });
}

export function sweepRuntimeExceeded({ started_at_ms, now_ms, max_runtime_ms = SWEEP_MAX_RUNTIME_MS }) {
  requireInteger(started_at_ms, "started_at_ms");
  requireInteger(now_ms, "now_ms");
  requireInteger(max_runtime_ms, "max_runtime_ms");
  return now_ms - started_at_ms > max_runtime_ms;
}

// Next slot at or after now_ms, derived from the anchor and whole cadence steps.
export function nextScheduledDueAt({ anchor_ms, cadence_ms = SWEEP_CADENCE_MS_DEFAULT, now_ms }) {
  requireInteger(anchor_ms, "anchor_ms");
  requireInteger(cadence_ms, "cadence_ms");
  requireInteger(now_ms, "now_ms");
  if (cadence_ms <= 0) throw new RangeError("cadence_ms must be positive");
  if (now_ms <= anchor_ms) return anchor_ms;
  const steps = Math.ceil((now_ms - anchor_ms) / cadence_ms);
  return anchor_ms + steps * cadence_ms;
}
