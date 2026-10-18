import assert from "node:assert/strict";
import { test } from "node:test";
import { acquireLeadership, createLeaderState } from "../leader-state.mjs";
import { createPlannerState } from "../sweep-planner.mjs";
import { SWEEP_EXECUTOR_SCHEMA, executePlannedSweep } from "../sweep-executor.mjs";

const LEASE = 60_000;

function leaderAt(now = 0) {
  let leader = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE });
  leader = acquireLeadership(leader, { candidate_id: "supervisor-a", now_ms: now, lease_ms: LEASE }).state;
  return {
    leader,
    fence: { leader_id: "supervisor-a", fencing_generation: leader.fencing_generation },
  };
}

function baseArgs(overrides = {}) {
  const { leader, fence } = leaderAt();
  return {
    plannerState: createPlannerState({ anchor_ms: 0 }),
    leaderState: leader,
    fence,
    now_ms: 0,
    admission: { fenced: false },
    execute: async () => "swept",
    cleanup: async () => {},
    ...overrides,
  };
}

test("a valid claim executes exactly once, then cleans up exactly once", async () => {
  const calls = [];
  const result = await executePlannedSweep(
    baseArgs({
      execute: async () => {
        calls.push("execute");
        return "swept";
      },
      cleanup: async () => {
        calls.push("cleanup");
      },
    }),
  );
  assert.equal(result.schema, SWEEP_EXECUTOR_SCHEMA);
  assert.equal(result.executed, true);
  assert.equal(result.decision.kind, "SCHEDULED");
  assert.equal(result.outcome.ok, true);
  assert.deepEqual(calls, ["execute", "cleanup"]);
  assert.deepEqual(result.cleanup, { called: true, ok: true });
});

test("a stale fencing generation is refused before any side effect", async () => {
  const { leader } = leaderAt();
  let executed = 0;
  const result = await executePlannedSweep(
    baseArgs({
      leaderState: leader,
      fence: { leader_id: "supervisor-a", fencing_generation: leader.fencing_generation + 1 },
      execute: async () => {
        executed += 1;
      },
    }),
  );
  assert.equal(result.executed, false);
  assert.equal(result.reason, "STALE_FENCING_GENERATION");
  assert.equal(executed, 0);
});

test("an expired lease is refused", async () => {
  const { leader, fence } = leaderAt(0);
  let executed = 0;
  const result = await executePlannedSweep(
    baseArgs({
      leaderState: leader,
      fence,
      now_ms: LEASE,
      execute: async () => {
        executed += 1;
      },
    }),
  );
  assert.equal(result.executed, false);
  assert.equal(result.reason, "LEASE_EXPIRED");
  assert.equal(executed, 0);
});

test("a fenced admission (draining/stopped) is refused before any side effect", async () => {
  let executed = 0;
  const result = await executePlannedSweep(
    baseArgs({
      admission: { fenced: true },
      execute: async () => {
        executed += 1;
      },
    }),
  );
  assert.equal(result.executed, false);
  assert.equal(result.reason, "ADMISSION_FENCED");
  assert.equal(executed, 0);
});

test("preconditions are revalidated after prepare, before execute", async () => {
  const admission = { fenced: false };
  let executed = 0;
  const result = await executePlannedSweep(
    baseArgs({
      admission,
      prepare: async () => {
        admission.fenced = true; // stop/drain lands while preparing
      },
      execute: async () => {
        executed += 1;
      },
    }),
  );
  assert.equal(result.executed, false);
  assert.equal(result.reason, "ADMISSION_FENCED");
  assert.equal(executed, 0);
});

test("an idle plan is refused without executing", async () => {
  let executed = 0;
  const result = await executePlannedSweep(
    baseArgs({
      now_ms: 0,
      plannerState: createPlannerState({ anchor_ms: 600_000 }),
      execute: async () => {
        executed += 1;
      },
    }),
  );
  assert.equal(result.executed, false);
  assert.equal(result.reason, "NOT_DUE");
  assert.equal(executed, 0);
});
