// Supervisor state machine for the Hybrid Council of Wise Elders repair.
// The machine is a pure reducer: the caller owns persistence and the clock.
//
// States, in the order the plan names them:
//   STARTING / RECONCILING -> HEALTHY | DEGRADED | PAUSED -> STOPPING -> STOPPED
//
// Two hard rules are encoded here rather than left to callers:
//   1. A DEGRADED or PAUSED reconciliation outcome is never recorded, or
//      transitioned to, as a successful reconciliation.
//   2. An explicit stop sets an automatic-engineering-restart fence. Until an
//      operator clears it, no automatic restart event is accepted, from any
//      state. Restart attempts are additionally capped at 3 per rolling 30 min.
import { validatePolicy } from "./policy.mjs";

export const SUPERVISOR_SCHEMA = "wise-elders.hybrid-supervisor/v1";
export const SUPERVISOR_STATES = Object.freeze([
  "STARTING",
  "RECONCILING",
  "HEALTHY",
  "DEGRADED",
  "PAUSED",
  "STOPPING",
  "STOPPED",
]);
export const RECONCILIATION_OUTCOMES = Object.freeze(["SUCCEEDED", "DEGRADED", "PAUSED"]);
export const RESTART_LIMIT = 3;
export const RESTART_WINDOW_MS = 30 * 60 * 1000;

// The native-adapter binding is a LATER unit. It is deliberately UNKNOWN here:
// this unit implements the policy-driven, testable core only. Nothing in this
// module installs, schedules, launches or attaches to anything.
export const NATIVE_ADAPTER_BINDING = Object.freeze({
  status: "UNKNOWN",
  reason: "native-adapter binding is a later unit (HYB-05); no installed, scheduled or live-swept evidence exists here",
  bound: false,
});

const LIVE_STATES = Object.freeze([
  "STARTING",
  "RECONCILING",
  "HEALTHY",
  "DEGRADED",
  "PAUSED",
  "STOPPING",
]);

const TRANSITIONS = Object.freeze({
  BEGIN_RECONCILE: Object.freeze({ from: Object.freeze(["STARTING", "HEALTHY", "DEGRADED"]), to: "RECONCILING" }),
  RECONCILE_SUCCEEDED: Object.freeze({ from: Object.freeze(["RECONCILING"]), to: "HEALTHY" }),
  RECONCILE_DEGRADED: Object.freeze({ from: Object.freeze(["RECONCILING"]), to: "DEGRADED" }),
  RECONCILE_PAUSED: Object.freeze({ from: Object.freeze(["RECONCILING"]), to: "PAUSED" }),
  HEALTH_DEGRADED: Object.freeze({ from: Object.freeze(["HEALTHY", "RECONCILING"]), to: "DEGRADED" }),
  HEALTH_RECOVERED: Object.freeze({ from: Object.freeze(["DEGRADED"]), to: "HEALTHY" }),
  PAUSE: Object.freeze({ from: Object.freeze(["STARTING", "RECONCILING", "HEALTHY", "DEGRADED"]), to: "PAUSED" }),
  RESUME: Object.freeze({ from: Object.freeze(["PAUSED"]), to: "STARTING" }),
  REQUEST_STOP: Object.freeze({ from: LIVE_STATES, to: "STOPPING" }),
  STOP_COMPLETE: Object.freeze({ from: Object.freeze(["STOPPING"]), to: "STOPPED" }),
});

export const SUPERVISOR_EVENTS = Object.freeze([
  ...Object.keys(TRANSITIONS),
  "AUTO_RESTART",
  "CLEAR_EXPLICIT_STOP",
]);

const NEUTRAL_RECONCILIATION = Object.freeze({
  status: "PENDING",
  successful: false,
  at_ms: null,
  leader_id: null,
});

function requireInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer, got ${String(value)}`);
  }
}

function requireSupervisor(supervisor) {
  if (!supervisor || supervisor.schema !== SUPERVISOR_SCHEMA) {
    throw new TypeError(`supervisor must be a ${SUPERVISOR_SCHEMA} object`);
  }
  return supervisor;
}

export function createSupervisor({ policy, now_ms, leader_id = null }) {
  requireInteger(now_ms, "now_ms");
  const verdict = validatePolicy(policy);
  if (!verdict.ok) {
    throw new Error(`invalid supervisor policy: ${verdict.errors.join("; ")}`);
  }
  if (policy.explicit_stop_disables_automatic_engineering_restart !== true) {
    throw new Error("policy must keep explicit_stop_disables_automatic_engineering_restart true");
  }
  return Object.freeze({
    schema: SUPERVISOR_SCHEMA,
    state: "STARTING",
    since_ms: now_ms,
    leader_id,
    policy,
    explicit_stop: null,
    automatic_engineering_restart_allowed: true,
    restart_history: Object.freeze([]),
    last_reconciliation: NEUTRAL_RECONCILIATION,
    transitions: Object.freeze([]),
  });
}

export function isExplicitStopFenced(supervisor) {
  requireSupervisor(supervisor);
  return supervisor.explicit_stop !== null && supervisor.automatic_engineering_restart_allowed === false;
}

// Rolling-window restart budget: at most RESTART_LIMIT supervisor restarts in
// any RESTART_WINDOW_MS window. Never a lifetime count.
export function restartBudget(supervisor, now_ms) {
  requireSupervisor(supervisor);
  requireInteger(now_ms, "now_ms");
  const inWindow = supervisor.restart_history.filter((at) => now_ms - at < RESTART_WINDOW_MS);
  return Object.freeze({
    allowed: inWindow.length < RESTART_LIMIT,
    restarts_in_window: inWindow.length,
    limit: RESTART_LIMIT,
    window_ms: RESTART_WINDOW_MS,
  });
}

export function canAutoRestart(supervisor, now_ms) {
  requireSupervisor(supervisor);
  if (isExplicitStopFenced(supervisor)) {
    return Object.freeze({
      allowed: false,
      reason: "EXPLICIT_STOP_FENCE",
      restarts_in_window: supervisor.restart_history.length,
      limit: RESTART_LIMIT,
      window_ms: RESTART_WINDOW_MS,
    });
  }
  const budget = restartBudget(supervisor, now_ms);
  return Object.freeze({
    allowed: budget.allowed,
    reason: budget.allowed ? "WITHIN_BUDGET" : "RESTART_BUDGET_EXHAUSTED",
    restarts_in_window: budget.restarts_in_window,
    limit: budget.limit,
    window_ms: budget.window_ms,
  });
}

function refuse(supervisor, reason) {
  return Object.freeze({ accepted: false, reason, supervisor });
}

function accept(next, reason) {
  return Object.freeze({ accepted: true, reason, supervisor: next });
}

// reduceSupervisor(supervisor, { type, at_ms, by?, reason?, operator? })
// Returns { accepted, reason, supervisor }. The input supervisor is never
// mutated; a refused event returns the input object unchanged.
export function reduceSupervisor(supervisor, event) {
  requireSupervisor(supervisor);
  if (!event || typeof event !== "object") {
    throw new TypeError("event must be an object");
  }
  const { type, at_ms } = event;
  requireInteger(at_ms, "event.at_ms");
  if (!SUPERVISOR_EVENTS.includes(type)) {
    throw new RangeError(`unknown supervisor event ${JSON.stringify(type)}`);
  }

  // The explicit-stop fence is checked before every other rule. Only the
  // operator clear and the stop completion may proceed once it is engaged.
  if (isExplicitStopFenced(supervisor)) {
    if (type === "STOP_COMPLETE" && supervisor.state === "STOPPING") {
      return accept(
        freezeNext(supervisor, "STOPPED", { at_ms, type, by: event.by ?? null }),
        "STOP_COMPLETE",
      );
    }
    if (type === "CLEAR_EXPLICIT_STOP") {
      if (event.operator !== true) {
        return refuse(supervisor, "OPERATOR_CLEAR_REQUIRED");
      }
      const next = Object.freeze({
        ...supervisor,
        explicit_stop: null,
        automatic_engineering_restart_allowed: true,
        transitions: Object.freeze([
          ...supervisor.transitions,
          Object.freeze({ type, from: supervisor.state, to: supervisor.state, at_ms, by: event.by ?? null }),
        ]),
      });
      return accept(next, "EXPLICIT_STOP_CLEARED");
    }
    return refuse(supervisor, "EXPLICIT_STOP_FENCE");
  }

  if (type === "AUTO_RESTART") {
    const gate = canAutoRestart(supervisor, at_ms);
    if (!gate.allowed) return refuse(supervisor, gate.reason);
    const next = Object.freeze({
      ...supervisor,
      state: "STARTING",
      since_ms: at_ms,
      restart_history: Object.freeze([...supervisor.restart_history, at_ms]),
      transitions: Object.freeze([
        ...supervisor.transitions,
        Object.freeze({ type, from: supervisor.state, to: "STARTING", at_ms, by: event.by ?? null }),
      ]),
    });
    return accept(next, "RESTARTED");
  }

  if (type === "CLEAR_EXPLICIT_STOP") {
    return refuse(supervisor, "NO_EXPLICIT_STOP");
  }

  const rule = TRANSITIONS[type];
  if (!rule.from.includes(supervisor.state)) {
    return refuse(supervisor, `ILLEGAL_TRANSITION:${supervisor.state}->${type}`);
  }

  const extras = {};
  if (type === "REQUEST_STOP" && event.explicit === true) {
    // The fence is set at request time, not at completion time, so a crash
    // between the two can never re-enable automatic restarts.
    extras.explicit_stop = Object.freeze({
      requested_at_ms: at_ms,
      by: event.by ?? null,
      reason: event.reason ?? null,
    });
    extras.automatic_engineering_restart_allowed = false;
  }

  if (type.startsWith("RECONCILE_")) {
    const status = type.slice("RECONCILE_".length);
    if (!RECONCILIATION_OUTCOMES.includes(status)) {
      return refuse(supervisor, `UNKNOWN_RECONCILIATION_OUTCOME:${status}`);
    }
    extras.last_reconciliation = Object.freeze({
      status,
      // Only an explicit SUCCEEDED outcome is a successful reconciliation.
      successful: status === "SUCCEEDED",
      at_ms,
      leader_id: supervisor.leader_id,
    });
  }

  const next = freezeNext(supervisor, rule.to, { at_ms, type, by: event.by ?? null }, extras);
  return accept(next, type);
}

function freezeNext(supervisor, to, meta, extras = {}) {
  return Object.freeze({
    ...supervisor,
    ...extras,
    state: to,
    since_ms: meta.at_ms,
    transitions: Object.freeze([
      ...supervisor.transitions,
      Object.freeze({ type: meta.type, from: supervisor.state, to, at_ms: meta.at_ms, by: meta.by }),
    ]),
  });
}

// Convenience guard used by callers that must not reconcile while paused.
export function mayBeginReconciliation(supervisor) {
  requireSupervisor(supervisor);
  return TRANSITIONS.BEGIN_RECONCILE.from.includes(supervisor.state) && !isExplicitStopFenced(supervisor);
}
