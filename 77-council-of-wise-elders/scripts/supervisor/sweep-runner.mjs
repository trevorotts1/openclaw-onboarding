// Execution wrapper for a planned full sweep.
//
// Ownership rule: only the current fenced leader may start a sweep, and only
// that same caller runs the cleanup. Cleanup runs exactly once on every return
// path, including an execute() exception, so a crashed sweep never leaves
// orphaned resources behind. A non-owner is refused BEFORE planning, so it can
// never clean up resources it does not own.
import { verifyFence } from "./leader-state.mjs";
import { SWEEP_MAX_RUNTIME_MS, planSweep } from "./sweep-planner.mjs";

export async function runPlannedSweep({
  plannerState,
  leaderState,
  fence,
  now_ms,
  extra_requested = false,
  execute,
  cleanup,
}) {
  if (typeof execute !== "function" || typeof cleanup !== "function") {
    throw new TypeError("execute and cleanup must be functions");
  }

  const fenceCheck = verifyFence(leaderState, fence);
  if (!fenceCheck.ok) {
    return Object.freeze({
      started: false,
      reason: fenceCheck.reason,
      cleanup_called: false,
      state: plannerState,
      decision: null,
    });
  }

  // planSweep is pure and may throw on a corrupt/misaligned state. In that case
  // nothing was started, so there is nothing this caller owns to clean up.
  const planned = planSweep(plannerState, { now_ms, extra_requested });
  const decision = planned.decision;

  let outcome;
  try {
    const value = await execute({ decision, deadline_ms: now_ms + SWEEP_MAX_RUNTIME_MS });
    outcome = Object.freeze({ ok: true, value });
  } catch (error) {
    outcome = Object.freeze({ ok: false, error });
  }

  let cleanupOutcome;
  try {
    await cleanup({ decision });
    cleanupOutcome = Object.freeze({ called: true, ok: true });
  } catch (error) {
    cleanupOutcome = Object.freeze({ called: true, ok: false, error });
  }

  return Object.freeze({
    started: true,
    reason: "STARTED",
    state: planned.state,
    decision,
    outcome,
    cleanup: cleanupOutcome,
    cleanup_called: true,
  });
}
