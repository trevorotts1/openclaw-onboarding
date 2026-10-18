import assert from "node:assert/strict";
import { test } from "node:test";
import {
  COLLECTION_VERDICTS,
  HEALTH_COLLECTION_SCHEMA,
  LIVENESS_STATES,
  SUBJECT_KINDS,
  collectHealth,
} from "../health-collector.mjs";

const NOW = 10_000_000;

function snapshot(overrides = {}) {
  return {
    now_ms: NOW,
    subjects: [
      { id: "native-adapter", kind: "native", liveness: "ALIVE" },
      { id: "supervisor", kind: "process", liveness: "ALIVE" },
      { id: "launchctl", kind: "tool", liveness: "ALIVE" },
    ],
    due: { next_due_at_ms: NOW + 60_000 },
    ...overrides,
  };
}

test("collection is deterministic for identical injected time and observations", () => {
  const first = collectHealth(snapshot());
  const second = collectHealth(snapshot());
  assert.equal(first.schema, HEALTH_COLLECTION_SCHEMA);
  assert.deepEqual(first, second);
  assert.deepEqual([...COLLECTION_VERDICTS], ["HEALTHY", "SUSPECT", "DEGRADED"]);
  assert.deepEqual([...SUBJECT_KINDS], ["native", "process", "tool"]);
  assert.deepEqual([...LIVENESS_STATES], ["ALIVE", "DEAD", "UNKNOWN"]);
});

test("clean snapshot is HEALTHY with no faults and no changes", () => {
  const health = collectHealth(snapshot());
  assert.equal(health.verdict, "HEALTHY");
  assert.deepEqual(health.faults, []);
  assert.equal(health.significant_change, false);
  assert.equal(health.llm_calls, 0);
});

test("native, process and tool liveness produce named faults", () => {
  const health = collectHealth(
    snapshot({
      subjects: [
        { id: "native-adapter", kind: "native", liveness: "DEAD" },
        { id: "supervisor", kind: "process", liveness: "DEAD" },
        { id: "launchctl", kind: "tool", liveness: "UNKNOWN" },
      ],
    }),
  );
  assert.equal(health.verdict, "DEGRADED");
  const codes = health.faults.map((fault) => fault.code);
  assert.deepEqual(codes, ["SUBJECT_DEAD", "SUBJECT_DEAD", "SUBJECT_UNKNOWN"]);
  assert.deepEqual(
    health.faults.map((fault) => fault.detail),
    ["native-adapter", "supervisor", "launchctl"],
  );
});

test("due-time faults respect the 30s gate", () => {
  const future = collectHealth(snapshot({ due: { next_due_at_ms: NOW + 1 } }));
  assert.equal(future.verdict, "HEALTHY");
  assert.deepEqual(future.faults, []);

  const late = collectHealth(snapshot({ due: { next_due_at_ms: NOW - 1 } }));
  assert.equal(late.verdict, "SUSPECT");
  assert.deepEqual(late.faults.map((fault) => fault.code), ["DUE_LATE"]);

  // Exactly at the gate is still "late", not yet "overdue".
  const atGate = collectHealth(snapshot({ due: { next_due_at_ms: NOW - 30_000 } }));
  assert.equal(atGate.verdict, "SUSPECT");
  assert.deepEqual(atGate.faults.map((fault) => fault.code), ["DUE_LATE"]);

  const overdue = collectHealth(snapshot({ due: { next_due_at_ms: NOW - 30_001 } }));
  assert.equal(overdue.verdict, "DEGRADED");
  assert.deepEqual(overdue.faults.map((fault) => fault.code), ["DUE_OVERDUE"]);

  const unknown = collectHealth(snapshot({ due: {} }));
  assert.equal(unknown.verdict, "SUSPECT");
  assert.deepEqual(unknown.faults.map((fault) => fault.code), ["DUE_UNKNOWN"]);
});

test("significant changes are reported against the previous collection", () => {
  const before = collectHealth(snapshot());
  const after = collectHealth(
    snapshot({
      subjects: [
        { id: "native-adapter", kind: "native", liveness: "ALIVE" },
        { id: "supervisor", kind: "process", liveness: "DEAD" },
        { id: "launchctl", kind: "tool", liveness: "ALIVE" },
      ],
      previous: before,
    }),
  );
  assert.equal(after.significant_change, true);
  assert.deepEqual(after.changes, [
    { kind: "FAULT_ADDED", code: "SUBJECT_DEAD", from: null, to: "SUBJECT_DEAD" },
    { kind: "LIVENESS_CHANGED", subject: "supervisor", from: "ALIVE", to: "DEAD" },
  ]);
  assert.deepEqual(after.changes, [...after.changes]);
});

test("invalid subject kinds and liveness states are rejected", () => {
  assert.throws(
    () => collectHealth(snapshot({ subjects: [{ id: "x", kind: "daemon", liveness: "ALIVE" }] })),
    /kind must be one of/,
  );
  assert.throws(
    () => collectHealth(snapshot({ subjects: [{ id: "x", kind: "tool", liveness: "MAYBE" }] })),
    /liveness must be one of/,
  );
});
