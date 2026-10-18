// Durable leader / fencing-generation state model for the Hybrid Council of
// Wise Elders supervisor. Pure reducers: the caller persists the returned
// state. Every state change bumps `revision`; every leadership change bumps
// `fencing_generation`. A commit carrying an older generation is refused, so a
// paused or partitioned former leader cannot mutate anything.
export const LEADER_SCHEMA = "wise-elders.hybrid-supervisor-leader/v1";

export const FENCE_REFUSALS = Object.freeze([
  "STALE_FENCING_GENERATION",
  "NOT_LEADER",
  "LEASE_EXPIRED",
  "NO_LEADER",
  "MALFORMED_FENCE",
]);

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function requireState(state) {
  if (!state || state.schema !== LEADER_SCHEMA) {
    throw new TypeError(`state must be a ${LEADER_SCHEMA} object`);
  }
  requireInteger(state.fencing_generation, "state.fencing_generation");
  requireInteger(state.revision, "state.revision");
  return state;
}

export function createLeaderState({ owner_id = null, now_ms, lease_ms }) {
  requireInteger(now_ms, "now_ms");
  requireInteger(lease_ms, "lease_ms");
  if (lease_ms <= 0) throw new RangeError("lease_ms must be positive");
  return Object.freeze({
    schema: LEADER_SCHEMA,
    leader_id: owner_id,
    fencing_generation: 1,
    lease_ms,
    lease_expires_at_ms: owner_id ? now_ms + lease_ms : 0,
    revision: 0,
    commits: Object.freeze([]),
  });
}

export function isLeaseLive(state, now_ms) {
  requireState(state);
  requireInteger(now_ms, "now_ms");
  return Boolean(state.leader_id) && now_ms < state.lease_expires_at_ms;
}

// Duplicate start: while another owner holds a live lease the caller must
// refuse to take leadership and stay read-only. It never steals the lease.
export function acquireLeadership(state, { candidate_id, now_ms, lease_ms }) {
  requireState(state);
  requireInteger(now_ms, "now_ms");
  requireInteger(state.revision, "state.revision");
  if (!candidate_id) throw new TypeError("candidate_id is required");
  if (!Number.isInteger(lease_ms) || lease_ms <= 0) {
    throw new RangeError("lease_ms must be a positive integer");
  }
  if (state.leader_id === candidate_id && isLeaseLive(state, now_ms)) {
    return Object.freeze({
      acquired: false,
      read_only: false,
      duplicate_start: true,
      reason: "ALREADY_LEADER",
      state,
    });
  }
  if (isLeaseLive(state, now_ms)) {
    return Object.freeze({
      acquired: false,
      read_only: true,
      duplicate_start: true,
      reason: "LEASE_HELD",
      state,
    });
  }
  const next = Object.freeze({
    ...state,
    leader_id: candidate_id,
    fencing_generation: state.fencing_generation + 1,
    lease_ms,
    lease_expires_at_ms: now_ms + lease_ms,
    revision: state.revision + 1,
  });
  return Object.freeze({
    acquired: true,
    read_only: false,
    duplicate_start: false,
    reason: "ACQUIRED",
    state: next,
  });
}

export function renewLeadership(state, { leader_id, fencing_generation, now_ms, lease_ms }) {
  requireState(state);
  requireInteger(now_ms, "now_ms");
  const fence = verifyFence(state, { leader_id, fencing_generation });
  if (!fence.ok) return Object.freeze({ renewed: false, reason: fence.reason, state });
  if (!Number.isInteger(lease_ms) || lease_ms <= 0) {
    throw new RangeError("lease_ms must be a positive integer");
  }
  const next = Object.freeze({
    ...state,
    lease_ms,
    lease_expires_at_ms: now_ms + lease_ms,
    revision: state.revision + 1,
  });
  return Object.freeze({ renewed: true, reason: "RENEWED", state: next });
}

export function verifyFence(state, fence) {
  requireState(state);
  if (!fence || typeof fence !== "object") {
    return Object.freeze({ ok: false, reason: "MALFORMED_FENCE" });
  }
  if (!Number.isInteger(fence.fencing_generation) || !fence.leader_id) {
    return Object.freeze({ ok: false, reason: "MALFORMED_FENCE" });
  }
  if (!state.leader_id) {
    return Object.freeze({ ok: false, reason: "NO_LEADER" });
  }
  if (fence.leader_id !== state.leader_id) {
    return Object.freeze({ ok: false, reason: "NOT_LEADER" });
  }
  // A generation below the current fence is stale by definition; a generation
  // above it never existed and is also refused.
  if (fence.fencing_generation !== state.fencing_generation) {
    return Object.freeze({ ok: false, reason: "STALE_FENCING_GENERATION" });
  }
  return Object.freeze({ ok: true, reason: "FENCE_VALID" });
}

/**
 * commitUnderFence(state, fence, { at_ms, operation, payload })
 * Pure: returns a NEW state when the fence is current, the input state
 * untouched otherwise. A stale leader generation can never commit.
 */
export function commitUnderFence(state, fence, { at_ms, operation, payload = null } = {}) {
  requireState(state);
  requireInteger(at_ms, "at_ms");
  if (!operation) throw new TypeError("operation is required");
  // Fence first: a stale generation is refused even if the lease has also aged
  // out, so the refusal always names the fencing defect that caused it.
  const verdict = verifyFence(state, fence);
  if (!verdict.ok) {
    return Object.freeze({ committed: false, reason: verdict.reason, state });
  }
  if (at_ms >= state.lease_expires_at_ms) {
    return Object.freeze({ committed: false, reason: "LEASE_EXPIRED", state });
  }
  const commit = Object.freeze({
    revision: state.revision + 1,
    fencing_generation: state.fencing_generation,
    leader_id: state.leader_id,
    at_ms,
    operation,
    payload,
  });
  const next = Object.freeze({
    ...state,
    revision: state.revision + 1,
    commits: Object.freeze([...state.commits, commit]),
  });
  return Object.freeze({ committed: true, reason: "COMMITTED", commit, state: next });
}

export function serializeLeaderState(state) {
  requireState(state);
  return JSON.stringify(state);
}

export function parseLeaderState(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error(`leader state is not valid JSON: ${error.message}`);
  }
  if (parsed?.schema !== LEADER_SCHEMA) {
    throw new Error(`leader state schema must be ${LEADER_SCHEMA}`);
  }
  return freezeLeaderState(parsed);
}

function freezeLeaderState(state) {
  return Object.freeze({
    ...state,
    commits: Object.freeze((state.commits ?? []).map((c) => Object.freeze({ ...c }))),
  });
}
