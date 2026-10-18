import assert from "node:assert/strict";
import { test } from "node:test";
import {
  LEADER_SCHEMA,
  acquireLeadership,
  commitUnderFence,
  createLeaderState,
  isLeaseLive,
  parseLeaderState,
  renewLeadership,
  serializeLeaderState,
  verifyFence,
} from "../leader-state.mjs";

const LEASE = 60_000;

test("a fresh leader gets generation 1 and a live lease", () => {
  const state = createLeaderState({ owner_id: "supervisor-a", now_ms: 0, lease_ms: LEASE });
  assert.equal(state.schema, LEADER_SCHEMA);
  assert.equal(state.fencing_generation, 1);
  assert.equal(state.leader_id, "supervisor-a");
  assert.equal(isLeaseLive(state, 0), true);
  assert.equal(isLeaseLive(state, LEASE), false);
});

test("duplicate start refuses leadership and stays read-only", () => {
  let state = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE });
  const first = acquireLeadership(state, { candidate_id: "supervisor-a", now_ms: 0, lease_ms: LEASE });
  assert.equal(first.acquired, true);
  assert.equal(first.state.fencing_generation, 2);
  state = first.state;

  const duplicate = acquireLeadership(state, { candidate_id: "supervisor-b", now_ms: 10_000, lease_ms: LEASE });
  assert.equal(duplicate.acquired, false);
  assert.equal(duplicate.read_only, true);
  assert.equal(duplicate.reason, "LEASE_HELD");
  assert.equal(duplicate.state, state, "a refused duplicate start must not mutate durable state");

  const sameOwner = acquireLeadership(state, { candidate_id: "supervisor-a", now_ms: 10_000, lease_ms: LEASE });
  assert.equal(sameOwner.acquired, false);
  assert.equal(sameOwner.duplicate_start, true);
  assert.equal(sameOwner.reason, "ALREADY_LEADER");
});

test("stale leader generation cannot commit", () => {
  let state = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE });
  state = acquireLeadership(state, { candidate_id: "supervisor-a", now_ms: 0, lease_ms: LEASE }).state;
  const staleFence = { leader_id: "supervisor-a", fencing_generation: state.fencing_generation };

  const good = commitUnderFence(state, staleFence, { at_ms: 1_000, operation: "record-sweep" });
  assert.equal(good.committed, true);
  state = good.state;

  // Leadership moves on: a new holder fences generation 3.
  const takeover = acquireLeadership(state, { candidate_id: "supervisor-b", now_ms: LEASE, lease_ms: LEASE });
  assert.equal(takeover.acquired, true);
  const taken = takeover.state;
  assert.equal(taken.fencing_generation, 3);

  const stale = commitUnderFence(taken, staleFence, { at_ms: LEASE + 1, operation: "record-sweep" });
  assert.equal(stale.committed, false);
  assert.equal(stale.reason, "NOT_LEADER");
  assert.equal(stale.state, taken);

  // Same leader id but an older generation is stale too.
  const regressed = commitUnderFence(
    taken,
    { leader_id: "supervisor-b", fencing_generation: 2 },
    { at_ms: LEASE + 1, operation: "record-sweep" },
  );
  assert.equal(regressed.committed, false);
  assert.equal(regressed.reason, "STALE_FENCING_GENERATION");
  assert.equal(regressed.state.commits.length, taken.commits.length);
});

test("a commit after lease expiry is refused", () => {
  let state = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE });
  state = acquireLeadership(state, { candidate_id: "supervisor-a", now_ms: 0, lease_ms: LEASE }).state;
  const fence = { leader_id: "supervisor-a", fencing_generation: state.fencing_generation };
  const expired = commitUnderFence(state, fence, { at_ms: LEASE, operation: "late" });
  assert.equal(expired.committed, false);
  assert.equal(expired.reason, "LEASE_EXPIRED");
});

test("renew requires a current fence and extends the lease", () => {
  let state = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE });
  state = acquireLeadership(state, { candidate_id: "supervisor-a", now_ms: 0, lease_ms: LEASE }).state;
  const fence = { leader_id: "supervisor-a", fencing_generation: state.fencing_generation };
  const renewed = renewLeadership(state, { ...fence, now_ms: 30_000, lease_ms: LEASE });
  assert.equal(renewed.renewed, true);
  assert.equal(renewed.state.lease_expires_at_ms, 90_000);
  assert.equal(renewed.state.revision, state.revision + 1);

  const refused = renewLeadership(state, {
    leader_id: "supervisor-a",
    fencing_generation: fence.fencing_generation - 1,
    now_ms: 30_000,
    lease_ms: LEASE,
  });
  assert.equal(refused.renewed, false);
  assert.equal(refused.reason, "STALE_FENCING_GENERATION");
});

test("fence verification names each refusal", () => {
  let state = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE });
  assert.equal(verifyFence(state, { leader_id: "a", fencing_generation: 1 }).reason, "NO_LEADER");
  state = acquireLeadership(state, { candidate_id: "supervisor-a", now_ms: 0, lease_ms: LEASE }).state;
  assert.equal(verifyFence(state, null).reason, "MALFORMED_FENCE");
  assert.equal(verifyFence(state, { leader_id: "b", fencing_generation: 2 }).reason, "NOT_LEADER");
  assert.deepEqual(
    verifyFence(state, { leader_id: "supervisor-a", fencing_generation: state.fencing_generation }),
    { ok: true, reason: "FENCE_VALID" },
  );
});

test("durable state round-trips through JSON without losing the fence", () => {
  let state = createLeaderState({ owner_id: null, now_ms: 0, lease_ms: LEASE });
  state = acquireLeadership(state, { candidate_id: "supervisor-a", now_ms: 0, lease_ms: LEASE }).state;
  state = commitUnderFence(
    state,
    { leader_id: "supervisor-a", fencing_generation: state.fencing_generation },
    { at_ms: 1_000, operation: "record-sweep", payload: { sweep: 1 } },
  ).state;

  const restored = parseLeaderState(serializeLeaderState(state));
  assert.equal(restored.fencing_generation, state.fencing_generation);
  assert.equal(restored.revision, state.revision);
  assert.deepEqual(restored.commits, state.commits);
  assert.equal(Object.isFrozen(restored.commits), true);

  assert.throws(() => parseLeaderState("{}"), /schema must be/);
  assert.throws(() => parseLeaderState("not-json"), /not valid JSON/);
});
