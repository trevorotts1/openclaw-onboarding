// Singleton leadership, mutation fencing and admission drain (HYB-04).
//
// Leadership is not re-invented here: acquireLeadership() and
// commitUnderFence() from the durable wave-1 leader-state module are the only
// authority. This module wraps them with an explicit instance result and adds
// the admission gate that a stop/drain closes BEFORE work is admitted.
import { acquireLeadership, commitUnderFence } from "./leader-state.mjs";

export const SINGLETON_SCHEMA = "wise-elders.hybrid-supervisor-singleton/v1";
export const ADMISSION_SCHEMA = "wise-elders.hybrid-supervisor-admission/v1";
export const ADMISSION_STATES = Object.freeze(["OPEN", "DRAINING", "STOPPED"]);

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function requireGate(gate) {
  if (!gate || gate.schema !== ADMISSION_SCHEMA) {
    throw new TypeError(`gate must be a ${ADMISSION_SCHEMA} object`);
  }
  if (!ADMISSION_STATES.includes(gate.state)) {
    throw new RangeError(`unknown admission state ${String(gate.state)}`);
  }
  return gate;
}

// A second instance either becomes the leader (no live lease) or is told to
// stay read-only. It never receives a fence when it did not acquire.
export function startSupervisorInstance({ leaderState, instance_id, now_ms, lease_ms }) {
  if (typeof instance_id !== "string" || instance_id.length === 0) {
    throw new TypeError("instance_id must be a non-empty string");
  }
  const result = acquireLeadership(leaderState, {
    candidate_id: instance_id,
    now_ms,
    lease_ms,
  });
  return Object.freeze({
    schema: SINGLETON_SCHEMA,
    instance_id,
    acquired: result.acquired,
    read_only: result.read_only,
    duplicate_start: result.duplicate_start,
    reason: result.reason,
    leader_state: result.state,
    fence: result.acquired
      ? Object.freeze({
          leader_id: instance_id,
          fencing_generation: result.state.fencing_generation,
        })
      : null,
  });
}

// Every mutation goes through the durable fence. A non-leader, a stale
// generation or an expired lease is refused before any state change.
export function mutateAsLeader({ leaderState, fence, at_ms, operation, payload = null }) {
  const result = commitUnderFence(leaderState, fence, { at_ms, operation, payload });
  return Object.freeze({
    schema: SINGLETON_SCHEMA,
    mutated: result.committed,
    reason: result.reason,
    commit: result.committed ? result.commit : null,
    leader_state: result.state,
  });
}

export function createAdmissionGate({ now_ms }) {
  requireInteger(now_ms, "now_ms");
  return Object.freeze({
    schema: ADMISSION_SCHEMA,
    state: "OPEN",
    since_ms: now_ms,
    drain: null,
    admitted: 0,
    refused: 0,
  });
}

// Stop/drain closes admissions at request time, not at completion time, so a
// crash during drain cannot re-open the door.
export function beginDrain(gate, { at_ms, reason = "STOP_REQUESTED", by = null } = {}) {
  requireGate(gate);
  requireInteger(at_ms, "at_ms");
  if (gate.state !== "OPEN") {
    return Object.freeze({ schema: ADMISSION_SCHEMA, drained: false, reason: "ALREADY_DRAINING", gate });
  }
  const next = Object.freeze({
    ...gate,
    state: "DRAINING",
    since_ms: at_ms,
    drain: Object.freeze({ requested_at_ms: at_ms, reason, by }),
  });
  return Object.freeze({ schema: ADMISSION_SCHEMA, drained: true, reason: "DRAIN_STARTED", gate: next });
}

export function completeStop(gate, { at_ms }) {
  requireGate(gate);
  requireInteger(at_ms, "at_ms");
  if (gate.state !== "DRAINING") {
    return Object.freeze({ schema: ADMISSION_SCHEMA, stopped: false, reason: "NOT_DRAINING", gate });
  }
  return Object.freeze({
    schema: ADMISSION_SCHEMA,
    stopped: true,
    reason: "STOPPED",
    gate: Object.freeze({ ...gate, state: "STOPPED", since_ms: at_ms }),
  });
}

export function admitUnit(gate, { at_ms, unit_id }) {
  requireGate(gate);
  requireInteger(at_ms, "at_ms");
  if (typeof unit_id !== "string" || unit_id.length === 0) {
    throw new TypeError("unit_id must be a non-empty string");
  }
  if (gate.state !== "OPEN") {
    return Object.freeze({
      admitted: false,
      reason: gate.state === "STOPPED" ? "ADMISSION_STOPPED" : "ADMISSION_FENCED",
      gate: Object.freeze({ ...gate, refused: gate.refused + 1 }),
    });
  }
  return Object.freeze({
    admitted: true,
    reason: "ADMITTED",
    gate: Object.freeze({ ...gate, admitted: gate.admitted + 1 }),
  });
}
