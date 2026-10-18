import assert from "node:assert/strict";
import { test } from "node:test";
import {
  JOURNAL_SCHEMA,
  appendAction,
  appendIncident,
  createJournal,
  parseJournal,
  recordAttempt,
  serializeJournal,
} from "../incident-journal.mjs";

const NOW = 3_000_000;

test("IDs are stable deterministic sequences, not timestamps or randomness", () => {
  let journal = createJournal();
  assert.equal(journal.schema, JOURNAL_SCHEMA);
  const first = appendIncident(journal, { at_ms: NOW, kind: "SWEEP_OVERDUE" });
  const second = appendIncident(first.journal, { at_ms: NOW + 1, kind: "QC_BACKLOG" });
  const action = appendAction(second.journal, { at_ms: NOW + 2, kind: "RESTART" });
  assert.equal(first.incident.id, "INC-000001");
  assert.equal(second.incident.id, "INC-000002");
  assert.equal(action.action.id, "ACT-000001");

  // Same inputs from a fresh journal reproduce the same IDs.
  const replay = appendAction(
    appendIncident(appendIncident(createJournal(), { at_ms: NOW, kind: "SWEEP_OVERDUE" }).journal, {
      at_ms: NOW + 1,
      kind: "QC_BACKLOG",
    }).journal,
    { at_ms: NOW + 2, kind: "RESTART" },
  );
  assert.equal(replay.action.id, "ACT-000001");
});

test("counters are cumulative and IDs continue after a simulated restart", () => {
  let journal = createJournal();
  journal = appendIncident(journal, { at_ms: NOW, kind: "A" }).journal;
  journal = appendIncident(journal, { at_ms: NOW + 1, kind: "B" }).journal;
  const inMemory = serializeJournal(journal);

  // Simulated restart: nothing but the durable text survives.
  let restored = parseJournal(inMemory);
  assert.deepEqual(restored.counters, journal.counters);
  assert.equal(restored.counters.incidents, 2);

  const after = appendIncident(restored, { at_ms: NOW + 2, kind: "C" });
  restored = after.journal;
  assert.equal(after.incident.id, "INC-000003");
  assert.equal(restored.counters.incidents, 3);
  assert.equal(restored.incidents.length, 3);
});

test("retries record the observed outcome and count stays cumulative", () => {
  let journal = createJournal();
  const action = appendAction(journal, { at_ms: NOW, kind: "RECONCILE", target: "sweep" });
  journal = action.journal;

  const first = recordAttempt(journal, {
    action_id: action.action.id,
    at_ms: NOW + 10,
    outcome: "FAILED",
    detail: "timeout",
  });
  journal = first.journal;
  assert.equal(first.retry, false);
  assert.equal(first.action.outcome, "FAILED");
  assert.equal(first.action.attempts.length, 1);

  const second = recordAttempt(journal, {
    action_id: action.action.id,
    at_ms: NOW + 20,
    outcome: "SUCCEEDED",
    detail: "recovered",
  });
  journal = second.journal;
  assert.equal(second.retry, true);
  assert.equal(second.action.outcome, "SUCCEEDED");
  assert.deepEqual(
    second.action.attempts.map((attempt) => attempt.outcome),
    ["FAILED", "SUCCEEDED"],
  );
  assert.deepEqual(journal.counters, {
    incidents: 0,
    actions: 1,
    attempts: 2,
    retries: 1,
    succeeded: 1,
    failed: 1,
  });
});

test("attempts and counters survive serialization", () => {
  let journal = createJournal();
  const action = appendAction(journal, { at_ms: NOW, kind: "RESTART" });
  journal = recordAttempt(action.journal, {
    action_id: action.action.id,
    at_ms: NOW + 1,
    outcome: "FAILED",
  }).journal;
  journal = recordAttempt(journal, {
    action_id: action.action.id,
    at_ms: NOW + 2,
    outcome: "SUCCEEDED",
  }).journal;

  const restored = parseJournal(serializeJournal(journal));
  assert.deepEqual(restored.counters, journal.counters);
  assert.equal(restored.actions[0].attempts.length, 2);
  assert.equal(restored.actions[0].outcome, "SUCCEEDED");
});

test("an unknown action id or bad outcome is refused", () => {
  const journal = createJournal();
  assert.throws(
    () => recordAttempt(journal, { action_id: "ACT-999999", at_ms: NOW, outcome: "FAILED" }),
    /unknown action id/,
  );
  const action = appendAction(journal, { at_ms: NOW, kind: "X" });
  assert.throws(
    () => recordAttempt(action.journal, { action_id: action.action.id, at_ms: NOW, outcome: "MAYBE" }),
    /attempt outcome/,
  );
  assert.throws(() => parseJournal("{not json"), /not valid JSON/);
});
