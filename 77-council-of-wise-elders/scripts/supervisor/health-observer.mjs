// Deterministic health observer for the Hybrid Council of Wise Elders
// supervisor. Runs on the policy health tick (60s) and makes NO LLM calls: it
// is pure arithmetic over an injected snapshot and injected time. There is no
// clock, no timer, no network and no randomness in this module.
import { SWEEP_MAX_RUNTIME_MS, SWEEP_UNHEALTHY_GATE_MS } from "./sweep-planner.mjs";

export const HEALTH_SCHEMA = "wise-elders.hybrid-supervisor-health/v1";
export const HEALTH_VERDICTS = Object.freeze(["HEALTHY", "SUSPECT", "DEGRADED"]);

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

/**
 * observeHealth({ now_ms, policy, heartbeat, sweep, leader })
 *   heartbeat: { last_seen_ms: number|null }
 *   sweep:     { running_started_at_ms?: number|null, gate?: {overdue_by_ms} | null }
 *   leader:    { lease_expires_at_ms?: number|null, is_leader?: boolean }
 * Pure: identical input yields identical output.
 */
export function observeHealth({ now_ms, policy, heartbeat = {}, sweep = {}, leader = {} }) {
  requireInteger(now_ms, "now_ms");
  if (!policy || !Number.isInteger(policy.health_tick_seconds)) {
    throw new TypeError("policy.health_tick_seconds is required");
  }
  const tickMs = policy.health_tick_seconds * 1000;
  const suspectAfterMs = policy.heartbeat_suspect_after_seconds * 1000;
  const reasons = [];
  let verdict = "HEALTHY";

  const escalate = (next, reason) => {
    reasons.push(reason);
    const order = { HEALTHY: 0, SUSPECT: 1, DEGRADED: 2 };
    if (order[next] > order[verdict]) verdict = next;
  };

  const lastSeen = heartbeat.last_seen_ms ?? null;
  let heartbeatAgeMs = null;
  if (lastSeen === null) {
    escalate("DEGRADED", "HEARTBEAT_MISSING");
  } else {
    requireInteger(lastSeen, "heartbeat.last_seen_ms");
    heartbeatAgeMs = now_ms - lastSeen;
    if (heartbeatAgeMs > suspectAfterMs) {
      escalate("DEGRADED", "HEARTBEAT_STALE");
    } else if (heartbeatAgeMs > tickMs) {
      escalate("SUSPECT", "HEARTBEAT_LATE");
    }
  }

  const startedAt = sweep.running_started_at_ms ?? null;
  let sweepRunningMs = null;
  if (startedAt !== null) {
    requireInteger(startedAt, "sweep.running_started_at_ms");
    sweepRunningMs = now_ms - startedAt;
    if (sweepRunningMs > SWEEP_MAX_RUNTIME_MS) {
      escalate("DEGRADED", "SWEEP_RUNTIME_EXCEEDED");
    }
  }

  const overdueByMs = sweep.gate?.overdue_by_ms ?? 0;
  requireInteger(overdueByMs, "sweep.gate.overdue_by_ms");
  if (overdueByMs > SWEEP_UNHEALTHY_GATE_MS) {
    escalate("DEGRADED", "SWEEP_UNHEALTHY_GATE_EXCEEDED");
  }

  const leaseExpires = leader.lease_expires_at_ms ?? null;
  let leaseRemainingMs = null;
  if (leaseExpires !== null) {
    requireInteger(leaseExpires, "leader.lease_expires_at_ms");
    leaseRemainingMs = leaseExpires - now_ms;
    if (leaseRemainingMs <= 0) escalate("DEGRADED", "LEADER_LEASE_EXPIRED");
  } else if (leader.is_leader === false) {
    escalate("DEGRADED", "NOT_LEADER");
  }

  if (verdict === "HEALTHY" && reasons.length === 0) reasons.push("ALL_SIGNALS_WITHIN_POLICY");

  return Object.freeze({
    schema: HEALTH_SCHEMA,
    observed_at_ms: now_ms,
    verdict,
    reasons: Object.freeze(reasons),
    signals: Object.freeze({
      heartbeat_age_ms: heartbeatAgeMs,
      heartbeat_suspect_after_ms: suspectAfterMs,
      sweep_running_ms: sweepRunningMs,
      sweep_max_runtime_ms: SWEEP_MAX_RUNTIME_MS,
      sweep_overdue_by_ms: overdueByMs,
      sweep_unhealthy_gate_ms: SWEEP_UNHEALTHY_GATE_MS,
      leader_lease_remaining_ms: leaseRemainingMs,
    }),
    // This observer is arithmetic only. There is no model in the loop.
    llm_calls: 0,
  });
}

// The next observation tick. Fixed cadence from the scheduled tick time, so a
// slow observer never stretches the health cadence.
export function nextHealthTickAt({ now_ms, policy }) {
  requireInteger(now_ms, "now_ms");
  if (!policy || !Number.isInteger(policy.health_tick_seconds)) {
    throw new TypeError("policy.health_tick_seconds is required");
  }
  return now_ms + policy.health_tick_seconds * 1000;
}
