import assert from "node:assert/strict";
import { test } from "node:test";
import { RESTART_LIMIT, RESTART_WINDOW_MS } from "../supervisor.mjs";
import {
  RESTART_LEDGER_SCHEMA,
  addPendingAction,
  createRestartLedger,
  parseRestartLedger,
  reconcileAfterRestart,
  recordRestart,
  serializeRestartLedger,
} from "../restart-reconciler.mjs";

test("the persisted budget matches the supervisor: 3 restarts / 30 minutes", () => {
  assert.equal(RESTART_LIMIT, 3);
  assert.equal(RESTART_WINDOW_MS, 30 * 60 * 1000);
  assert.equal(createRestartLedger().schema, RESTART_LEDGER_SCHEMA);
});

test("a fourth restart inside the rolling window is refused", () => {
  let ledger = createRestartLedger();
  for (const at of [0, 1_000, 2_000]) {
    const result = recordRestart(ledger, { at_ms: at });
    assert.equal(result.allowed, true);
    ledger = result.ledger;
  }
  assert.equal(ledger.counters.restarts, 3);

  const refused = recordRestart(ledger, { at_ms: 3_000 });
  assert.equal(refused.allowed, false);
  assert.equal(refused.reason, "RESTART_BUDGET_EXHAUSTED");
  assert.equal(refused.restarts_in_window, 3);
  assert.equal(refused.ledger.counters.refused, 1);
  assert.equal(refused.ledger.restarts.length, 3);
});

test("the window rolls: the oldest restart frees a slot after 30 minutes", () => {
  let ledger = createRestartLedger();
  for (const at of [0, 1_000, 2_000]) ledger = recordRestart(ledger, { at_ms: at }).ledger;
  assert.equal(recordRestart(ledger, { at_ms: 30 * 60 * 1000 - 1 }).allowed, false);

  // At exactly window length, the at=0 restart is no longer inside the window.
  const rolled = recordRestart(ledger, { at_ms: 30 * 60 * 1000 });
  assert.equal(rolled.allowed, true);
  assert.equal(rolled.restarts_in_window, 3);
});

test("the budget and counters survive a simulated restart from durable text", () => {
  let ledger = createRestartLedger();
  for (const at of [0, 1_000, 2_000]) ledger = recordRestart(ledger, { at_ms: at }).ledger;
  ledger = recordRestart(ledger, { at_ms: 3_000 }).ledger; // refused, counted

  const restored = parseRestartLedger(serializeRestartLedger(ledger));
  assert.equal(restored.counters.restarts, 3);
  assert.equal(restored.counters.refused, 1);
  assert.equal(restored.restarts.length, 3);

  const stillRefused = recordRestart(restored, { at_ms: 4_000 });
  assert.equal(stillRefused.allowed, false);
  assert.equal(stillRefused.ledger.counters.refused, 2);
});

test("restart reconciliation reads pending durable actions after a reload", () => {
  let ledger = createRestartLedger();
  ledger = addPendingAction(ledger, {
    at_ms: 100,
    kind: "RESUME_SWEEP",
    payload: { anchor_ms: 0 },
  }).ledger;
  ledger = addPendingAction(ledger, {
    at_ms: 200,
    kind: "DRAIN_ADMISSIONS",
    payload: null,
  }).ledger;

  const durable = parseRestartLedger(serializeRestartLedger(ledger));
  const reconciled = reconcileAfterRestart(durable, { now_ms: 500 });
  assert.equal(reconciled.pending_action_count, 2);
  assert.deepEqual(reconciled.actions_to_resume, ["PEND-000001", "PEND-000002"]);
  assert.deepEqual(
    reconciled.pending_actions.map((action) => action.kind),
    ["RESUME_SWEEP", "DRAIN_ADMISSIONS"],
  );
  assert.equal(reconciled.pending_actions[0].state, "PENDING");
  assert.equal(reconciled.ledger.counters.reconciliations, 1);
  assert.deepEqual(reconciled.ledger.pending_actions, durable.pending_actions);

  const empty = reconcileAfterRestart(createRestartLedger(), { now_ms: 600 });
  assert.equal(empty.pending_action_count, 0);
  assert.deepEqual(empty.actions_to_resume, []);
});

test("a corrupt ledger is a hard error, never a silent reset", () => {
  assert.throws(() => parseRestartLedger("{"), /not valid JSON/);
  assert.throws(() => parseRestartLedger('{"schema":"other"}'), /schema must be/);
});
