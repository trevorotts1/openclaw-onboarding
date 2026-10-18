import assert from "node:assert/strict";
import { test } from "node:test";
import {
  OVERDUE_GRACE_MS,
  OVERDUE_SCHEMA,
  SUPERVISOR_OVERDUE,
  detectOverdue,
} from "../overdue-detector.mjs";

const DUE = 7_000_000;

test("the grace period is exactly 30 seconds", () => {
  assert.equal(OVERDUE_GRACE_MS, 30_000);
});

test("due + 29,999ms is not overdue even with a live PID", () => {
  const result = detectOverdue({ now_ms: DUE + 29_999, due_at_ms: DUE, pid_alive: true });
  assert.equal(result.schema, OVERDUE_SCHEMA);
  assert.equal(result.overdue, false);
  assert.deepEqual(result.events, []);
});

test("SUPERVISOR_OVERDUE fires at due + 30s with the PID still alive", () => {
  const result = detectOverdue({ now_ms: DUE + 30_000, due_at_ms: DUE, pid_alive: true });
  assert.equal(result.overdue, true);
  assert.equal(result.independent_of_pid, true);
  assert.equal(result.overdue_at_ms, DUE + 30_000);
  assert.equal(result.events.length, 1);
  assert.equal(result.events[0].type, SUPERVISOR_OVERDUE);
  assert.equal(result.events[0].at_ms, DUE + 30_000);
  assert.equal(result.events[0].pid_alive, true);
  assert.equal(result.events[0].independent_of_pid, true);
});

test("a dead PID does not change the firing time", () => {
  const alive = detectOverdue({ now_ms: DUE + 45_000, due_at_ms: DUE, pid_alive: true });
  const dead = detectOverdue({ now_ms: DUE + 45_000, due_at_ms: DUE, pid_alive: false });
  // The liveness observation is carried, but it never moves the firing time.
  assert.equal(alive.events[0].at_ms, dead.events[0].at_ms);
  assert.equal(alive.events[0].type, dead.events[0].type);
  assert.equal(alive.overdue, dead.overdue);
  assert.equal(alive.overdue_at_ms, dead.overdue_at_ms);
});

test("the detector is pure over injected time", () => {
  assert.deepEqual(
    detectOverdue({ now_ms: DUE + 30_000, due_at_ms: DUE, pid_alive: true }),
    detectOverdue({ now_ms: DUE + 30_000, due_at_ms: DUE, pid_alive: true }),
  );
  assert.throws(
    () => detectOverdue({ now_ms: DUE, due_at_ms: DUE, pid_alive: "yes" }),
    /pid_alive/,
  );
});
