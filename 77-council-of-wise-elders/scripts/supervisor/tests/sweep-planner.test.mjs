import assert from "node:assert/strict";
import { test } from "node:test";
import {
  SWEEP_MAX_RUNTIME_MS,
  SWEEP_UNHEALTHY_GATE_MS,
  completeSweep,
  createPlannerState,
  nextScheduledDueAt,
  planSweep,
  sweepRuntimeExceeded,
} from "../sweep-planner.mjs";

const CADENCE = 600_000;
const ANCHOR = 1_000_000;

test("first scheduled sweep is due exactly at the anchor", () => {
  const state = createPlannerState({ anchor_ms: ANCHOR });
  const idle = planSweep(state, { now_ms: ANCHOR - 1 });
  assert.equal(idle.decision.kind, "IDLE");
  assert.equal(idle.decision.scheduled_due_at_ms, ANCHOR);

  const claim = planSweep(state, { now_ms: ANCHOR });
  assert.equal(claim.decision.kind, "SCHEDULED");
  assert.equal(claim.decision.due_at_ms, ANCHOR);
  assert.equal(claim.decision.lateness_ms, 0);
  assert.equal(claim.decision.gate.unhealthy, false);
  assert.equal(claim.state.next_due_at_ms, ANCHOR + CADENCE);
});

test("cadence cannot drift: completion time never becomes the next due", () => {
  let state = createPlannerState({ anchor_ms: ANCHOR });
  // Deliberately irregular finishes: fast, slow, and near a full cadence.
  const finishOffsets = [12_000, 45_000, 590_000, 3_000, 300_000, 119_000];
  for (let cycle = 0; cycle < 12; cycle += 1) {
    const due = state.next_due_at_ms;
    const claim = planSweep(state, { now_ms: due });
    assert.equal(claim.decision.kind, "SCHEDULED");
    assert.equal(claim.decision.due_at_ms, due);

    const finishedAt = due + finishOffsets[cycle % finishOffsets.length];
    state = completeSweep(claim.state, { kind: "SCHEDULED", finished_at_ms: finishedAt });

    // The invariant that proves no drift: the next due is derived from the
    // anchor and the previous due, never from `finishedAt`.
    assert.equal(state.next_due_at_ms, due + CADENCE);
    assert.equal((state.next_due_at_ms - ANCHOR) % CADENCE, 0);
    assert.notEqual(state.next_due_at_ms, finishedAt + CADENCE);
  }
  assert.equal(state.next_due_at_ms, ANCHOR + 12 * CADENCE);
  assert.equal(state.scheduled_sweeps, 12);
});

test("an EXTRA sweep at t=590 leaves the t=600 scheduled slot pending", () => {
  let state = createPlannerState({ anchor_ms: 600_000 });
  const extra = planSweep(state, { now_ms: 590_000, extra_requested: true });
  assert.equal(extra.decision.kind, "EXTRA");
  assert.equal(extra.decision.consumes_scheduled_slot, false);
  assert.equal(extra.decision.scheduled_due_at_ms, 600_000);
  assert.equal(extra.state.next_due_at_ms, 600_000);
  assert.equal(extra.state.extra_sweeps, 1);
  assert.equal(extra.state.scheduled_sweeps, 0);

  state = completeSweep(extra.state, { kind: "EXTRA", finished_at_ms: 595_000 });
  assert.equal(state.next_due_at_ms, 600_000);

  // The real scheduled slot is still claimable at 600 and records lateness 0.
  const scheduled = planSweep(state, { now_ms: 600_000 });
  assert.equal(scheduled.decision.kind, "SCHEDULED");
  assert.equal(scheduled.decision.due_at_ms, 600_000);
  assert.equal(scheduled.decision.lateness_ms, 0);
  assert.equal(scheduled.state.scheduled_sweeps, 1);
});

test("an EXTRA sweep never turns a late scheduled sweep into an on-time one", () => {
  let state = createPlannerState({ anchor_ms: 600_000 });
  state = planSweep(state, { now_ms: 590_000, extra_requested: true }).state;
  state = completeSweep(state, { kind: "EXTRA", finished_at_ms: 590_500 });
  const late = planSweep(state, { now_ms: 615_000 });
  assert.equal(late.decision.kind, "SCHEDULED");
  assert.equal(late.decision.due_at_ms, 600_000);
  assert.equal(late.decision.lateness_ms, 15_000);
  assert.equal(late.state.extra_sweeps, 1);
  assert.equal(late.state.scheduled_sweeps, 1);
});

test("a late claim skips whole anchored slots and keeps anchor alignment", () => {
  const state = createPlannerState({ anchor_ms: ANCHOR });
  const claim = planSweep(state, { now_ms: ANCHOR + 2.5 * CADENCE });
  assert.equal(claim.decision.kind, "SCHEDULED");
  assert.equal(claim.decision.due_at_ms, ANCHOR);
  assert.equal(claim.decision.skipped_slots, 2);
  assert.equal(claim.state.skipped_slots, 2);
  assert.equal(claim.state.next_due_at_ms, ANCHOR + 3 * CADENCE);
  assert.equal((claim.state.next_due_at_ms - ANCHOR) % CADENCE, 0);
});

test("due+30s is the unhealthy gate boundary", () => {
  const state = createPlannerState({ anchor_ms: 0 });
  const atGate = planSweep(state, { now_ms: SWEEP_UNHEALTHY_GATE_MS });
  assert.equal(atGate.decision.lateness_ms, 30_000);
  assert.equal(atGate.decision.gate.overdue_by_ms, 30_000);
  assert.equal(atGate.decision.gate.unhealthy, false);

  const overGate = planSweep(createPlannerState({ anchor_ms: 0 }), { now_ms: SWEEP_UNHEALTHY_GATE_MS + 1 });
  assert.equal(overGate.decision.gate.unhealthy, true);
});

test("sweep_max_runtime is 120s and is exceeded strictly after it", () => {
  assert.equal(SWEEP_MAX_RUNTIME_MS, 120_000);
  assert.equal(sweepRuntimeExceeded({ started_at_ms: 0, now_ms: 120_000 }), false);
  assert.equal(sweepRuntimeExceeded({ started_at_ms: 0, now_ms: 120_001 }), true);
});

test("planner is pure: input state is never mutated and outputs are frozen", () => {
  const state = createPlannerState({ anchor_ms: ANCHOR });
  const snapshot = JSON.stringify(state);
  const result = planSweep(state, { now_ms: ANCHOR });
  assert.equal(JSON.stringify(state), snapshot);
  assert.notEqual(result.state, state);
  assert.equal(Object.isFrozen(result.state), true);
  assert.equal(Object.isFrozen(result.decision), true);
  const completed = completeSweep(result.state, { kind: "SCHEDULED", finished_at_ms: ANCHOR + 1 });
  assert.equal(JSON.stringify(result.state), JSON.stringify(JSON.parse(JSON.stringify(result.state))));
  assert.notEqual(completed, result.state);
});

test("planner refuses a state whose next due is off the anchor", () => {
  const state = createPlannerState({ anchor_ms: ANCHOR });
  assert.throws(
    () => planSweep({ ...state, next_due_at_ms: ANCHOR + 1 }, { now_ms: ANCHOR }),
    /not aligned to the fixed schedule anchor/,
  );
});

test("nextScheduledDueAt stays on the anchored grid", () => {
  assert.equal(nextScheduledDueAt({ anchor_ms: 0, now_ms: 0 }), 0);
  assert.equal(nextScheduledDueAt({ anchor_ms: 0, now_ms: 1 }), 600_000);
  assert.equal(nextScheduledDueAt({ anchor_ms: 0, now_ms: 600_000 }), 600_000);
  assert.equal(nextScheduledDueAt({ anchor_ms: 0, now_ms: 600_001 }), 1_200_000);
});
