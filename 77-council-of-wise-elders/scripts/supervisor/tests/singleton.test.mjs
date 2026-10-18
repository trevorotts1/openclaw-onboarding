import assert from "node:assert/strict";
import { test } from "node:test";
import { createLeaderState } from "../leader-state.mjs";
import {
  ADMISSION_STATES,
  SINGLETON_SCHEMA,
  admitUnit,
  beginDrain,
  completeStop,
  createAdmissionGate,
  mutateAsLeader,
  startSupervisorInstance,
} from "../singleton.mjs";

const LEASE = 60_000;

test("one instance leads; a duplicate start is read-only and gets no fence", () => {
  let state = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE });
  const first = startSupervisorInstance({
    leaderState: state,
    instance_id: "supervisor-a",
    now_ms: 0,
    lease_ms: LEASE,
  });
  assert.equal(first.schema, SINGLETON_SCHEMA);
  assert.equal(first.acquired, true);
  assert.equal(first.read_only, false);
  assert.deepEqual(first.fence, {
    leader_id: "supervisor-a",
    fencing_generation: first.leader_state.fencing_generation,
  });

  state = first.leader_state;
  const second = startSupervisorInstance({
    leaderState: state,
    instance_id: "supervisor-b",
    now_ms: 1_000,
    lease_ms: LEASE,
  });
  assert.equal(second.acquired, false);
  assert.equal(second.read_only, true);
  assert.equal(second.reason, "LEASE_HELD");
  assert.equal(second.fence, null);
});

test("a second supervisor instance cannot mutate through the leader fence", () => {
  const first = startSupervisorInstance({
    leaderState: createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE }),
    instance_id: "supervisor-a",
    now_ms: 0,
    lease_ms: LEASE,
  });

  const impostor = mutateAsLeader({
    leaderState: first.leader_state,
    fence: { leader_id: "supervisor-b", fencing_generation: first.leader_state.fencing_generation },
    at_ms: 10,
    operation: "WRITE_PENDING_ACTION",
  });
  assert.equal(impostor.mutated, false);
  assert.equal(impostor.reason, "NOT_LEADER");
  assert.equal(impostor.leader_state, first.leader_state);

  const owner = mutateAsLeader({
    leaderState: first.leader_state,
    fence: first.fence,
    at_ms: 10,
    operation: "WRITE_PENDING_ACTION",
  });
  assert.equal(owner.mutated, true);
  assert.equal(owner.commit.operation, "WRITE_PENDING_ACTION");
});

test("a former leader with an old fence cannot mutate after failover", () => {
  const first = startSupervisorInstance({
    leaderState: createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE }),
    instance_id: "supervisor-a",
    now_ms: 0,
    lease_ms: LEASE,
  });
  const second = startSupervisorInstance({
    leaderState: first.leader_state,
    instance_id: "supervisor-b",
    now_ms: LEASE,
    lease_ms: LEASE,
  });
  assert.equal(second.acquired, true);

  const stale = mutateAsLeader({
    leaderState: second.leader_state,
    fence: first.fence,
    at_ms: LEASE + 1,
    operation: "WRITE_PENDING_ACTION",
  });
  assert.equal(stale.mutated, false);
  // Identity changed first: the old leader is no longer the leader at all.
  assert.equal(stale.reason, "NOT_LEADER");
  assert.equal(stale.leader_state.commits.length, 0);
});

test("stop/drain fences new admissions immediately and permanently", () => {
  let gate = createAdmissionGate({ now_ms: 0 });
  assert.deepEqual([...ADMISSION_STATES], ["OPEN", "DRAINING", "STOPPED"]);

  const admitted = admitUnit(gate, { at_ms: 0, unit_id: "unit-1" });
  assert.equal(admitted.admitted, true);
  gate = admitted.gate;

  const drain = beginDrain(gate, { at_ms: 10, reason: "OPERATOR_STOP", by: "trevor" });
  assert.equal(drain.drained, true);
  gate = drain.gate;

  const duringDrain = admitUnit(gate, { at_ms: 11, unit_id: "unit-2" });
  assert.equal(duringDrain.admitted, false);
  assert.equal(duringDrain.reason, "ADMISSION_FENCED");
  assert.equal(duringDrain.gate.admitted, 1);
  assert.equal(duringDrain.gate.refused, 1);

  const stop = completeStop(duringDrain.gate, { at_ms: 12 });
  assert.equal(stop.stopped, true);
  const afterStop = admitUnit(stop.gate, { at_ms: 13, unit_id: "unit-3" });
  assert.equal(afterStop.admitted, false);
  assert.equal(afterStop.reason, "ADMISSION_STOPPED");

  const secondDrain = beginDrain(stop.gate, { at_ms: 14 });
  assert.equal(secondDrain.drained, false);
  assert.equal(secondDrain.reason, "ALREADY_DRAINING");
});
