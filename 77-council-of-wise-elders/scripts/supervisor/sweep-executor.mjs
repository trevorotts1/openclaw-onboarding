// Precondition-revalidating sweep executor (HYB-03).
//
// The planner phase is pure: planSweep() is called with injected time and does
// no I/O. This executor is the only place that may cause side effects, and it
// revalidates every precondition AFTER planning and BEFORE execute():
//   * the fence generation is still current,
//   * the leader lease is still live,
//   * new admissions are not fenced (draining/stopped),
//   * the plan still decides work at this instant.
//
// An optional async `prepare` step runs between the two validation passes, so
// a fence revoked while preparing is caught before the side effect.
import { verifyFence } from "./leader-state.mjs";
import { SWEEP_MAX_RUNTIME_MS, planSweep } from "./sweep-planner.mjs";

export const SWEEP_EXECUTOR_SCHEMA = "wise-elders.hybrid-supervisor-sweep-executor/v1";

function refused(reason, planned = null) {
  return Object.freeze({
    schema: SWEEP_EXECUTOR_SCHEMA,
    executed: false,
    reason,
    decision: planned?.decision ?? null,
    state: planned?.state ?? null,
    outcome: null,
    cleanup: null,
  });
}

function checkPreconditions({ leaderState, fence, now_ms, admission }) {
  const fenceCheck = verifyFence(leaderState, fence);
  if (!fenceCheck.ok) return fenceCheck.reason;
  if (!(now_ms < leaderState.lease_expires_at_ms)) return "LEASE_EXPIRED";
  if (admission?.fenced === true) return "ADMISSION_FENCED";
  return null;
}

export async function executePlannedSweep({
  plannerState,
  leaderState,
  fence,
  now_ms,
  extra_requested = false,
  admission = { fenced: false },
  prepare = null,
  execute,
  cleanup,
}) {
  if (typeof execute !== "function" || typeof cleanup !== "function") {
    throw new TypeError("execute and cleanup must be functions");
  }

  const firstRefusal = checkPreconditions({ leaderState, fence, now_ms, admission });
  if (firstRefusal) return refused(firstRefusal);

  // Pure planning. A corrupt planner state throws before anything happens.
  const planned = planSweep(plannerState, { now_ms, extra_requested });
  if (planned.decision.kind === "IDLE") return refused("NOT_DUE", planned);

  if (typeof prepare === "function") {
    await prepare({ decision: planned.decision });
  }

  // Second pass: the fence may have moved while preparing.
  const secondRefusal = checkPreconditions({ leaderState, fence, now_ms, admission });
  if (secondRefusal) return refused(secondRefusal, planned);

  let outcome;
  try {
    const value = await execute({
      decision: planned.decision,
      deadline_ms: now_ms + SWEEP_MAX_RUNTIME_MS,
    });
    outcome = Object.freeze({ ok: true, value });
  } catch (error) {
    outcome = Object.freeze({ ok: false, error });
  }

  let cleanupOutcome;
  try {
    await cleanup({ decision: planned.decision });
    cleanupOutcome = Object.freeze({ called: true, ok: true });
  } catch (error) {
    cleanupOutcome = Object.freeze({ called: true, ok: false, error });
  }

  return Object.freeze({
    schema: SWEEP_EXECUTOR_SCHEMA,
    executed: true,
    reason: "EXECUTED",
    decision: planned.decision,
    state: planned.state,
    outcome,
    cleanup: cleanupOutcome,
  });
}
