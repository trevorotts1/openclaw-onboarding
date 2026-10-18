import assert from "node:assert/strict";
import { test } from "node:test";
import { defaultPolicy } from "../policy.mjs";
import {
  NATIVE_ADAPTER_BINDING,
  RESTART_LIMIT,
  RESTART_WINDOW_MS,
  SUPERVISOR_SCHEMA,
  SUPERVISOR_STATES,
  canAutoRestart,
  createSupervisor,
  isExplicitStopFenced,
  mayBeginReconciliation,
  reduceSupervisor,
  restartBudget,
} from "../supervisor.mjs";

const policy = defaultPolicy();

function newSupervisor(now = 0) {
  return createSupervisor({ policy, now_ms: now, leader_id: "supervisor-a" });
}

function apply(supervisor, type, at_ms, extra = {}) {
  return reduceSupervisor(supervisor, { type, at_ms, ...extra });
}

test("states are exactly the seven named in the plan", () => {
  assert.deepEqual([...SUPERVISOR_STATES], [
    "STARTING", "RECONCILING", "HEALTHY", "DEGRADED", "PAUSED", "STOPPING", "STOPPED",
  ]);
  assert.equal(newSupervisor().schema, SUPERVISOR_SCHEMA);
  assert.equal(newSupervisor().state, "STARTING");
});

test("a successful reconciliation is the only path to HEALTHY from RECONCILING", () => {
  let sv = newSupervisor();
  assert.equal(apply(sv, "RECONCILE_SUCCEEDED", 10).accepted, false);

  sv = apply(sv, "BEGIN_RECONCILE", 10).supervisor;
  assert.equal(sv.state, "RECONCILING");
  const done = apply(sv, "RECONCILE_SUCCEEDED", 20);
  assert.equal(done.accepted, true);
  assert.equal(done.supervisor.state, "HEALTHY");
  assert.deepEqual(done.supervisor.last_reconciliation.status, "SUCCEEDED");
  assert.equal(done.supervisor.last_reconciliation.successful, true);
});

test("DEGRADED and PAUSED reconciliation outcomes are never successful", () => {
  let sv = apply(newSupervisor(), "BEGIN_RECONCILE", 10).supervisor;

  const degraded = apply(sv, "RECONCILE_DEGRADED", 20);
  assert.equal(degraded.supervisor.state, "DEGRADED");
  assert.equal(degraded.supervisor.last_reconciliation.status, "DEGRADED");
  assert.equal(degraded.supervisor.last_reconciliation.successful, false);

  const paused = apply(sv, "RECONCILE_PAUSED", 20);
  assert.equal(paused.supervisor.state, "PAUSED");
  assert.equal(paused.supervisor.last_reconciliation.status, "PAUSED");
  assert.equal(paused.supervisor.last_reconciliation.successful, false);

  // Health recovering later must not rewrite the failed reconciliation.
  const recovered = apply(degraded.supervisor, "HEALTH_RECOVERED", 30);
  assert.equal(recovered.supervisor.state, "HEALTHY");
  assert.equal(recovered.supervisor.last_reconciliation.status, "DEGRADED");
  assert.equal(recovered.supervisor.last_reconciliation.successful, false);
});

test("a paused supervisor cannot begin reconciliation", () => {
  let sv = apply(newSupervisor(), "PAUSE", 10).supervisor;
  assert.equal(sv.state, "PAUSED");
  assert.equal(mayBeginReconciliation(sv), false);
  assert.equal(apply(sv, "BEGIN_RECONCILE", 20).accepted, false);
  sv = apply(sv, "RESUME", 30).supervisor;
  assert.equal(sv.state, "STARTING");
  assert.equal(mayBeginReconciliation(sv), true);
});

test("an explicit stop fences automatic engineering restart from every state", () => {
  let sv = newSupervisor();
  const requested = apply(sv, "REQUEST_STOP", 10, { explicit: true, by: "operator" });
  assert.equal(requested.accepted, true);
  sv = requested.supervisor;
  assert.equal(sv.state, "STOPPING");
  assert.equal(isExplicitStopFenced(sv), true);
  assert.equal(sv.automatic_engineering_restart_allowed, false);
  assert.equal(canAutoRestart(sv, 20).allowed, false);
  assert.equal(canAutoRestart(sv, 20).reason, "EXPLICIT_STOP_FENCE");

  const restart = apply(sv, "AUTO_RESTART", 20);
  assert.equal(restart.accepted, false);
  assert.equal(restart.reason, "EXPLICIT_STOP_FENCE");
  assert.equal(restart.supervisor, sv);

  sv = apply(sv, "STOP_COMPLETE", 30).supervisor;
  assert.equal(sv.state, "STOPPED");
  for (const type of ["AUTO_RESTART", "RESUME", "BEGIN_RECONCILE", "PAUSE"]) {
    const refused = apply(sv, type, 40);
    assert.equal(refused.accepted, false, type);
    assert.equal(refused.reason, "EXPLICIT_STOP_FENCE", type);
  }

  // Only an operator clear re-arms the machine.
  const nonOperator = apply(sv, "CLEAR_EXPLICIT_STOP", 50);
  assert.equal(nonOperator.accepted, false);
  assert.equal(nonOperator.reason, "OPERATOR_CLEAR_REQUIRED");
  const cleared = apply(sv, "CLEAR_EXPLICIT_STOP", 60, { operator: true, by: "operator" });
  assert.equal(cleared.accepted, true);
  assert.equal(isExplicitStopFenced(cleared.supervisor), false);
  assert.equal(apply(cleared.supervisor, "AUTO_RESTART", 70).accepted, true);
});

test("a non-explicit stop does not fence automatic restart", () => {
  let sv = apply(newSupervisor(), "REQUEST_STOP", 10).supervisor;
  assert.equal(sv.state, "STOPPING");
  assert.equal(isExplicitStopFenced(sv), false);
  const restarted = apply(sv, "AUTO_RESTART", 20);
  assert.equal(restarted.accepted, true);
  assert.equal(restarted.supervisor.state, "STARTING");
});

test("at most 3 supervisor restarts per rolling 30 minutes", () => {
  let sv = newSupervisor();
  assert.equal(RESTART_LIMIT, 3);
  assert.equal(RESTART_WINDOW_MS, 1_800_000);

  for (const at of [0, 1_000, 2_000]) {
    const result = apply(sv, "AUTO_RESTART", at);
    assert.equal(result.accepted, true, `restart at ${at}`);
    sv = result.supervisor;
  }
  assert.equal(sv.restart_history.length, 3);
  assert.equal(restartBudget(sv, 3_000).restarts_in_window, 3);

  const fourth = apply(sv, "AUTO_RESTART", 3_000);
  assert.equal(fourth.accepted, false);
  assert.equal(fourth.reason, "RESTART_BUDGET_EXHAUSTED");
  assert.equal(fourth.supervisor.restart_history.length, 3);

  // The window rolls: once the oldest restart ages out, one slot reopens.
  assert.equal(restartBudget(sv, 1_800_001).restarts_in_window, 2);
  const afterWindow = apply(sv, "AUTO_RESTART", 1_800_001);
  assert.equal(afterWindow.accepted, true);
  assert.equal(afterWindow.supervisor.restart_history.length, 4);
});

test("illegal transitions are refused without mutating state", () => {
  const sv = newSupervisor();
  const refused = apply(sv, "STOP_COMPLETE", 10);
  assert.equal(refused.accepted, false);
  assert.match(refused.reason, /^ILLEGAL_TRANSITION/);
  assert.equal(refused.supervisor, sv);
  assert.throws(() => apply(sv, "TELEPORT", 10), /unknown supervisor event/);
});

test("policy without the explicit-stop guarantee is rejected", () => {
  assert.throws(
    () => createSupervisor({
      policy: { ...policy, explicit_stop_disables_automatic_engineering_restart: false },
      now_ms: 0,
    }),
    /invalid supervisor policy/,
  );
});

test("the reducer is pure: frozen input and no clock dependence", () => {
  const sv = newSupervisor();
  const before = JSON.stringify(sv);
  const result = apply(sv, "BEGIN_RECONCILE", 10);
  assert.equal(JSON.stringify(sv), before);
  assert.notEqual(result.supervisor, sv);
  assert.equal(Object.isFrozen(result.supervisor), true);
});

test("native adapter binding is deferred and explicitly UNKNOWN", () => {
  assert.equal(NATIVE_ADAPTER_BINDING.status, "UNKNOWN");
  assert.equal(NATIVE_ADAPTER_BINDING.bound, false);
  assert.match(NATIVE_ADAPTER_BINDING.reason, /HYB-05/);
});
