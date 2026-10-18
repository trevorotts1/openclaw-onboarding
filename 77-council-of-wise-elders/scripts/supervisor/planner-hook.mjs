// Fixed ten-minute full-sweep planner hook (HYB-03).
//
// This module is a thin, PURE adapter over the existing wave-1 sweep-planner.
// It adds the one thing the policy pins down (the ten-minute cadence) and
// nothing else: the planner still owns anchoring, whole-cadence advancement,
// skipped-slot accounting and the 30s unhealthy gate.
//
// Purity contract: no Date.now, no performance.now, no setTimeout/setInterval
// and no I/O. Time is always the caller's `now_ms`. The regression test scans
// this source for those symbols, so the contract cannot rot silently.
import {
  SWEEP_CADENCE_MS_DEFAULT,
  completeSweep,
  createPlannerState,
  nextScheduledDueAt,
  planSweep,
} from "./sweep-planner.mjs";

export const PLANNER_HOOK_SCHEMA = "wise-elders.hybrid-supervisor-planner-hook/v1";
export const FULL_SWEEP_INTERVAL_MS = 600_000; // ten minutes, per policy

function requireHook(hook) {
  if (!hook || hook.schema !== PLANNER_HOOK_SCHEMA) {
    throw new TypeError(`hook must be a ${PLANNER_HOOK_SCHEMA} object`);
  }
  if (hook.cadence_ms !== FULL_SWEEP_INTERVAL_MS) {
    throw new RangeError(`hook cadence must stay ${FULL_SWEEP_INTERVAL_MS}ms`);
  }
  return hook;
}

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

export function createFullSweepHook({ anchor_ms, cadence_ms = FULL_SWEEP_INTERVAL_MS }) {
  requireInteger(anchor_ms, "anchor_ms");
  if (cadence_ms !== FULL_SWEEP_INTERVAL_MS || cadence_ms !== SWEEP_CADENCE_MS_DEFAULT) {
    throw new RangeError(
      `full-sweep cadence must be exactly ${FULL_SWEEP_INTERVAL_MS}ms, got ${String(cadence_ms)}`,
    );
  }
  return Object.freeze({
    schema: PLANNER_HOOK_SCHEMA,
    cadence_ms,
    planner_state: createPlannerState({ anchor_ms, cadence_ms }),
  });
}

// Delegates to the pure planner; returns the advanced hook and the decision.
export function planFullSweep(hook, { now_ms, extra_requested = false } = {}) {
  requireHook(hook);
  requireInteger(now_ms, "now_ms");
  const planned = planSweep(hook.planner_state, { now_ms, extra_requested });
  return Object.freeze({
    schema: PLANNER_HOOK_SCHEMA,
    hook: Object.freeze({ ...hook, planner_state: planned.state }),
    decision: planned.decision,
  });
}

export function completeFullSweep(hook, { kind, finished_at_ms }) {
  requireHook(hook);
  return Object.freeze({
    schema: PLANNER_HOOK_SCHEMA,
    hook: Object.freeze({
      ...hook,
      planner_state: completeSweep(hook.planner_state, { kind, finished_at_ms }),
    }),
  });
}

export function nextFullSweepDueAt(hook, now_ms) {
  requireHook(hook);
  requireInteger(now_ms, "now_ms");
  return nextScheduledDueAt({
    anchor_ms: hook.planner_state.anchor_ms,
    cadence_ms: hook.cadence_ms,
    now_ms,
  });
}
