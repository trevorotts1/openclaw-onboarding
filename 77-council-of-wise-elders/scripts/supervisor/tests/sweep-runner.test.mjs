import assert from "node:assert/strict";
import { test } from "node:test";
import { acquireLeadership, createLeaderState } from "../leader-state.mjs";
import { createPlannerState } from "../sweep-planner.mjs";
import { runPlannedSweep } from "../sweep-runner.mjs";

function owner() {
  let leader = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: 60_000 });
  leader = acquireLeadership(leader, { candidate_id: "supervisor-a", now_ms: 0, lease_ms: 60_000 }).state;
  return { leader, fence: { leader_id: "supervisor-a", fencing_generation: leader.fencing_generation } };
}

test("cleanup runs exactly once on the success path", async () => {
  const { leader, fence } = owner();
  const calls = [];
  const result = await runPlannedSweep({
    plannerState: createPlannerState({ anchor_ms: 0 }),
    leaderState: leader,
    fence,
    now_ms: 0,
    execute: async () => { calls.push("execute"); return "done"; },
    cleanup: async () => { calls.push("cleanup"); },
  });
  assert.equal(result.started, true);
  assert.equal(result.decision.kind, "SCHEDULED");
  assert.equal(result.outcome.ok, true);
  assert.equal(result.outcome.value, "done");
  assert.deepEqual(calls, ["execute", "cleanup"]);
  assert.deepEqual(result.cleanup, { called: true, ok: true });
});

test("cleanup still runs exactly once when execute throws", async () => {
  const { leader, fence } = owner();
  let cleanups = 0;
  const result = await runPlannedSweep({
    plannerState: createPlannerState({ anchor_ms: 0 }),
    leaderState: leader,
    fence,
    now_ms: 0,
    execute: async () => { throw new Error("sweep blew up"); },
    cleanup: async () => { cleanups += 1; },
  });
  assert.equal(result.started, true);
  assert.equal(result.outcome.ok, false);
  assert.equal(result.outcome.error.message, "sweep blew up");
  assert.equal(cleanups, 1);
  assert.equal(result.cleanup.ok, true);
});

test("a cleanup failure is reported without masking the sweep outcome", async () => {
  const { leader, fence } = owner();
  const result = await runPlannedSweep({
    plannerState: createPlannerState({ anchor_ms: 0 }),
    leaderState: leader,
    fence,
    now_ms: 0,
    execute: async () => "ok",
    cleanup: async () => { throw new Error("cannot release"); },
  });
  assert.equal(result.outcome.ok, true);
  assert.equal(result.cleanup.ok, false);
  assert.equal(result.cleanup.error.message, "cannot release");
});

test("a non-owner is refused and never cleans up another owner's sweep", async () => {
  const { leader } = owner();
  let cleanups = 0;
  const result = await runPlannedSweep({
    plannerState: createPlannerState({ anchor_ms: 0 }),
    leaderState: leader,
    fence: { leader_id: "supervisor-b", fencing_generation: leader.fencing_generation },
    now_ms: 0,
    execute: async () => { throw new Error("must not run"); },
    cleanup: async () => { cleanups += 1; },
  });
  assert.equal(result.started, false);
  assert.equal(result.reason, "NOT_LEADER");
  assert.equal(result.cleanup_called, false);
  assert.equal(cleanups, 0);
});

test("a stale fencing generation is refused before any work starts", async () => {
  const { leader, fence } = owner();
  const result = await runPlannedSweep({
    plannerState: createPlannerState({ anchor_ms: 0 }),
    leaderState: leader,
    fence: { ...fence, fencing_generation: fence.fencing_generation - 1 },
    now_ms: 0,
    execute: async () => "never",
    cleanup: async () => { throw new Error("must not clean"); },
  });
  assert.equal(result.started, false);
  assert.equal(result.reason, "STALE_FENCING_GENERATION");
  assert.equal(result.cleanup_called, false);
});

test("an EXTRA sweep carries the untouched scheduled slot and a 120s deadline", async () => {
  const { leader, fence } = owner();
  const result = await runPlannedSweep({
    plannerState: createPlannerState({ anchor_ms: 600_000 }),
    leaderState: leader,
    fence,
    now_ms: 590_000,
    extra_requested: true,
    execute: async ({ deadline_ms }) => deadline_ms,
    cleanup: async () => {},
  });
  assert.equal(result.decision.kind, "EXTRA");
  assert.equal(result.decision.consumes_scheduled_slot, false);
  assert.equal(result.state.next_due_at_ms, 600_000);
  assert.equal(result.outcome.value, 590_000 + 120_000);
});
