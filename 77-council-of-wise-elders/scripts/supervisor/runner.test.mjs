import assert from "node:assert/strict";
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  EXIT,
  RUNNER_STATE_SCHEMA,
  UsageError,
  admitInstance,
  commitState,
  createState,
  drainAndStop,
  parseArgs,
  parseState,
  readState,
  reconcilePending,
  recoverDeadLeader,
  runOneTick,
  statePath,
  stopState,
} from "./runner.mjs";
import { addPendingAction } from "./restart-reconciler.mjs";

const NOW = 1_000_000;

function withDir(prefix, fn) {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function admitted(intervalSeconds = 1) {
  const dataDir = mkdtempSync(join(tmpdir(), "wise-elders-runner-test-"));
  const result = admitInstance({
    dataDir,
    now_ms: NOW,
    instanceId: "instance-A",
    pid: process.pid,
    intervalSeconds,
    leaseMs: 30_000,
    alive: () => true,
  });
  assert.equal(result.admitted, true, "fresh state must admit");
  return { dataDir, state: result.state, fence: result.fence };
}

function listTree(root, { skip = null } = {}) {
  const entries = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (skip && full === skip) continue;
      const stat = statSync(full);
      if (stat.isDirectory()) {
        entries.push(`dir:${full}`);
        walk(full);
      } else {
        entries.push(`file:${full}:${stat.size}`);
      }
    }
  };
  walk(root);
  return entries.sort();
}

test("parseArgs requires --data-dir unless --ephemeral is explicit", () => {
  assert.throws(() => parseArgs([]), UsageError);
  assert.throws(() => parseArgs(["--interval-seconds", "1"]), /--data-dir is required/);
  assert.throws(
    () => parseArgs(["--data-dir", "/tmp/x", "--ephemeral"]),
    /mutually exclusive/,
  );
  assert.throws(() => parseArgs(["--data-dir", "/tmp/x", "--interval-seconds", "0"]), UsageError);

  const explicit = parseArgs(["--data-dir", "/tmp/example", "--interval-seconds", "7"]);
  assert.equal(explicit.dataDir, "/tmp/example");
  assert.equal(explicit.ephemeral, false);
  assert.equal(explicit.intervalSeconds, 7);
  assert.equal(explicit.tickWorkMs, 0);
  assert.equal(explicit.once, false);

  const ephemeral = parseArgs(["--ephemeral", "--once"]);
  assert.equal(ephemeral.dataDir, null);
  assert.equal(ephemeral.ephemeral, true);
  assert.equal(ephemeral.once, true);
  // The documented default cadence is 600 seconds.
  assert.equal(parseArgs(["--ephemeral"]).intervalSeconds, 600);
});

test("state is written atomically as valid JSON with no temp file left behind", () => {
  withDir("wise-elders-runner-atomic-", (dataDir) => {
    const state = createState({
      now_ms: NOW,
      instance_id: "instance-A",
      pid: process.pid,
      intervalSeconds: 1,
      leaseMs: 30_000,
    });
    const committed = commitState(dataDir, state, {
      expectedGeneration: 0,
      nextGeneration: 1,
      now_ms: NOW,
    });
    assert.equal(committed.committed, true);

    const onDisk = readState(dataDir);
    assert.equal(onDisk.schema, RUNNER_STATE_SCHEMA);
    assert.equal(onDisk.ledger_generation, 1);
    // Read it back through JSON.parse to prove the file itself is not torn.
    assert.doesNotThrow(() => JSON.parse(readFileSync(statePath(dataDir), "utf8")));
    assert.deepEqual(
      readdirSync(dataDir).filter((name) => name.includes(".tmp-")),
      [],
    );
  });
});

test("a stale ledger generation is refused and never overwrites newer state", () => {
  withDir("wise-elders-runner-stale-", (dataDir) => {
    const state = createState({
      now_ms: NOW,
      instance_id: "instance-A",
      pid: process.pid,
      intervalSeconds: 1,
      leaseMs: 30_000,
    });
    commitState(dataDir, state, { expectedGeneration: 0, nextGeneration: 1, now_ms: NOW });
    const newer = commitState(dataDir, { ...state, tick_seq: 5 }, {
      expectedGeneration: 1,
      nextGeneration: 2,
      now_ms: NOW,
    });
    assert.equal(newer.committed, true);

    const stale = commitState(dataDir, { ...state, tick_seq: 99 }, {
      expectedGeneration: 1,
      now_ms: NOW,
    });
    assert.equal(stale.committed, false);
    assert.equal(stale.reason, "STALE_LEDGER_GENERATION");
    assert.equal(stale.disk_generation, 2);

    const onDisk = readState(dataDir);
    assert.equal(onDisk.ledger_generation, 2);
    assert.equal(onDisk.tick_seq, 5, "stale writer must not clobber the newer state");
  });
});

test("parseState rejects a corrupt or foreign state file", () => {
  assert.throws(() => parseState("{not json"), /not valid JSON/);
  assert.throws(() => parseState(JSON.stringify({ schema: "other" })), /schema must be/);
  assert.throws(
    () => parseState(JSON.stringify({ schema: RUNNER_STATE_SCHEMA, ledger_generation: -1 })),
    /ledger_generation/,
  );
});

test("a dead owner's lease is recovered and the fencing generation advances", () => {
  const { dataDir, state, fence } = admitted();
  try {
    assert.equal(state.leader.fencing_generation, fence.fencing_generation);
    const crashed = commitState(dataDir, { ...state, pid: 999_999 }, {
      expectedGeneration: state.ledger_generation,
      now_ms: NOW + 10,
    });
    assert.equal(crashed.committed, true);

    const recovery = recoverDeadLeader(crashed.state, {
      now_ms: NOW + 20,
      alive: () => false,
    });
    assert.equal(recovery.recovered, true);
    assert.equal(recovery.reason, "DEAD_OWNER_RECOVERED");
    assert.equal(recovery.state.leader.leader_id, null);
    assert.equal(recovery.state.leader.fencing_generation, state.leader.fencing_generation);
    assert.equal(
      recovery.state.journal.incidents.at(-1).kind,
      "STALE_LEASE_RECOVERED",
    );

    const next = admitInstance({
      dataDir,
      now_ms: NOW + 30,
      instanceId: "instance-B",
      pid: process.pid,
      intervalSeconds: 1,
      leaseMs: 30_000,
      alive: () => false,
    });
    assert.equal(next.admitted, true);
    assert.equal(next.recovered, true);
    assert.ok(
      next.fence.fencing_generation > fence.fencing_generation,
      "restart must advance the fencing generation",
    );
    assert.equal(next.state.ledger_generation, state.ledger_generation + 1);
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test("a second live instance is refused by the singleton lease with LEASE_HELD", () => {
  const { dataDir, state } = admitted();
  try {
    const second = admitInstance({
      dataDir,
      now_ms: NOW + 10,
      instanceId: "instance-B",
      pid: process.pid + 1,
      intervalSeconds: 1,
      leaseMs: 30_000,
      alive: () => true,
    });
    assert.equal(second.admitted, false);
    assert.equal(second.receipt.reason, "LEASE_HELD");
    assert.equal(second.receipt.duplicate_start, true);
    assert.equal(second.receipt.read_only, true);
    assert.equal(second.state.ledger_generation, state.ledger_generation);
    assert.equal(readState(dataDir).ledger_generation, state.ledger_generation);
    assert.ok(
      readdirSync(dataDir).some((name) => name.startsWith("refusal-")),
      "the refusal is recorded durably inside the data directory",
    );
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test("one tick plans through the executor, journals a receipt and clears the pending action", async () => {
  const { dataDir, state, fence } = admitted();
  try {
    const result = await runOneTick({
      dataDir,
      state,
      fence,
      now_ms: state.planner.next_due_at_ms,
      tickWorkMs: 0,
    });
    assert.equal(result.stale, false);
    assert.equal(result.executed, true);
    assert.equal(result.decision.kind, "SCHEDULED");
    assert.equal(result.receipt.receipt_id, "RCPT-000001");

    const after = readState(dataDir);
    assert.equal(after.tick_seq, 1);
    assert.equal(after.completed_sweeps, 1);
    assert.equal(after.planner.scheduled_sweeps, 1);
    assert.deepEqual(after.restart_ledger.pending_actions, []);
    assert.equal(after.restart_ledger.next_pending_seq, 2);

    const receipt = after.journal.actions.find((action) => action.kind === "SWEEP_RECEIPT");
    assert.equal(receipt.target, "PEND-000001");
    assert.equal(receipt.outcome, "SUCCEEDED");
    assert.equal(receipt.payload.receipt_id, "RCPT-000001");
    assert.equal(after.journal.counters.attempts, 1);
    assert.equal(after.last_health.llm_calls, 0);
    assert.equal(after.last_observation.llm_calls, 0);
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test("an interrupted tick is reconciled exactly once and resumed as an EXTRA sweep", async () => {
  const { dataDir, state, fence } = admitted();
  try {
    const first = await runOneTick({
      dataDir,
      state,
      fence,
      now_ms: state.planner.next_due_at_ms,
    });
    assert.equal(first.executed, true);

    // Simulate kill -9 after the pending action was made durable but before the
    // tick committed: exactly the state a real crash leaves on disk.
    const added = addPendingAction(first.state.restart_ledger, {
      at_ms: NOW + 500,
      kind: "SCHEDULED_SWEEP_TICK",
      payload: { tick_seq: first.state.tick_seq + 1, cadence_ms: first.state.planner.cadence_ms },
    });
    const crashed = {
      ...first.state,
      tick_seq: first.state.tick_seq + 1,
      restart_ledger: added.ledger,
    };
    const committed = commitState(dataDir, crashed, {
      expectedGeneration: first.state.ledger_generation,
      now_ms: NOW + 500,
    });
    assert.equal(committed.committed, true);
    const pendingId = added.action.id;
    assert.equal(readState(dataDir).restart_ledger.pending_actions.length, 1);

    const reconciliation = await reconcilePending({
      dataDir,
      state: committed.state,
      fence,
      now_ms: NOW + 1_000,
    });
    assert.equal(reconciliation.stale, false);
    assert.deepEqual(reconciliation.consumed, [pendingId]);
    assert.deepEqual(reconciliation.resumed, [pendingId]);

    const second = await reconcilePending({
      dataDir,
      state: reconciliation.state,
      fence,
      now_ms: NOW + 2_000,
    });
    assert.deepEqual(second.consumed, [], "a second reconcile must consume nothing");

    const after = readState(dataDir);
    assert.deepEqual(after.restart_ledger.pending_actions, []);
    assert.equal(after.restart_ledger.counters.reconciliations, 1);
    assert.equal(after.reconciled_actions.length, 1);
    assert.equal(after.reconciled_actions[0].id, pendingId);
    assert.equal(after.reconciled_actions[0].state, "RECONCILED");

    const reconciliationIncidents = after.journal.incidents.filter(
      (incident) => incident.kind === "INTERRUPTED_TICK_RECONCILED",
    );
    assert.equal(reconciliationIncidents.length, 1);
    assert.equal(reconciliationIncidents[0].detail.pending_id, pendingId);

    const targets = after.journal.actions.filter((action) => action.target === pendingId);
    assert.equal(targets.length, 1, "the pending action is consumed exactly once");
    assert.equal(targets[0].kind, "RECOVERY_SWEEP");
    assert.equal(targets[0].payload.consumes_scheduled_slot, false);
    assert.equal(targets[0].payload.decision_kind, "EXTRA");
    // The interrupted tick consumed its scheduled slot before the crash; the
    // resume must not consume a second one.
    assert.equal(after.planner.scheduled_sweeps, 1);
    assert.equal(after.planner.extra_sweeps, 1);
    assert.equal(after.planner.next_due_at_ms, first.state.planner.next_due_at_ms);
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test("a tick refuses to write on a stale ledger and leaves the newer file intact", async () => {
  const { dataDir, state, fence } = admitted();
  try {
    const newer = commitState(dataDir, { ...state, tick_seq: 42 }, {
      expectedGeneration: state.ledger_generation,
      nextGeneration: state.ledger_generation + 1,
      now_ms: NOW,
    });
    assert.equal(newer.committed, true);

    const result = await runOneTick({
      dataDir,
      state,
      fence,
      now_ms: state.planner.next_due_at_ms,
    });
    assert.equal(result.stale, true);
    assert.equal(result.reason, "STALE_LEDGER_GENERATION");
    const onDisk = readState(dataDir);
    assert.equal(onDisk.tick_seq, 42);
    assert.equal(onDisk.ledger_generation, state.ledger_generation + 1);
    assert.deepEqual(onDisk.restart_ledger.pending_actions, []);
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test("graceful stop drains to STOPPED and leaves a valid JSON state file", () => {
  withDir("wise-elders-runner-stop-", (dataDir) => {
    const admission = admitInstance({
      dataDir,
      now_ms: NOW,
      instanceId: "instance-A",
      pid: process.pid,
      intervalSeconds: 1,
      leaseMs: 30_000,
      alive: () => true,
    });
    assert.equal(admission.admitted, true);

    const drained = stopState(admission.state, { now_ms: NOW + 10, reason: "SIGTERM" });
    assert.equal(drained.supervisor.state, "STOPPED");
    assert.equal(drained.admission.state, "STOPPED");

    const committed = drainAndStop({
      dataDir,
      state: admission.state,
      now_ms: NOW + 10,
      reason: "SIGTERM",
    });
    assert.equal(committed.stopped, true);
    assert.equal(committed.state.supervisor.state, "STOPPED");

    const raw = readFileSync(statePath(dataDir), "utf8");
    const parsed = JSON.parse(raw);
    assert.equal(parsed.schema, RUNNER_STATE_SCHEMA);
    assert.equal(parsed.supervisor.state, "STOPPED");
    assert.equal(parsed.admission.state, "STOPPED");
    assert.equal(parsed.stopped_at_ms, NOW + 10);
    assert.deepEqual(
      readdirSync(dataDir).filter((name) => name.includes(".tmp-")),
      [],
    );
  });
});

test("the driver has no process-spawning and no network capability", () => {
  const source = readFileSync(new URL("./runner.mjs", import.meta.url), "utf8");
  const importLines = source.split("\n").filter((line) => line.trim().startsWith("import"));
  const importText = importLines.join("\n");
  for (const forbidden of [
    "child_process",
    "node:http",
    "node:https",
    "node:net",
    "node:dns",
    "node:tls",
    "node:dgram",
    "node:worker_threads",
  ]) {
    assert.equal(
      importText.includes(forbidden),
      false,
      `runner.mjs must not import ${forbidden}`,
    );
  }
  assert.equal(importText.includes("execSync"), false);
  assert.equal(importText.includes("spawn"), false);
  for (const api of ["fetch(", "XMLHttpRequest", "WebSocket", "EventSource"]) {
    assert.equal(source.includes(api), false, `runner.mjs must not use ${api}`);
  }
  // No credential or environment read of any kind.
  assert.equal(source.includes("process.env"), false);
  assert.equal(source.includes("homedir"), false);
});

test("a tick writes only inside its data directory", async () => {
  const root = mkdtempSync(join(tmpdir(), "wise-elders-runner-fs-"));
  try {
    writeFileSync(join(root, "sentinel.txt"), "outside the data dir\n");
    const dataDir = join(root, "data");
    const admission = admitInstance({
      dataDir,
      now_ms: NOW,
      instanceId: "instance-A",
      pid: process.pid,
      intervalSeconds: 1,
      leaseMs: 30_000,
      alive: () => true,
    });
    assert.equal(admission.admitted, true);

    const before = listTree(root, { skip: dataDir });
    const result = await runOneTick({
      dataDir,
      state: admission.state,
      fence: admission.fence,
      now_ms: admission.state.planner.next_due_at_ms,
    });
    assert.equal(result.executed, true);
    const after = listTree(root, { skip: dataDir });
    assert.deepEqual(after, before, "nothing outside the data directory may change");
    assert.equal(existsSync(join(root, "sentinel.txt")), true);
    assert.equal(readFileSync(join(root, "sentinel.txt"), "utf8"), "outside the data dir\n");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("the CLI exit codes are stable and documented", () => {
  assert.deepEqual(
    { ...EXIT },
    { OK: 0, FAILED: 1, USAGE: 2, REFUSED: 3, STALE_LEDGER: 4 },
  );
});

// Regression for a real defect found by independent QC: the entry-point guard
// compared `import.meta.url` to `pathToFileURL(process.argv[1]).href`, which is
// FALSE whenever the script is reached through a symlink. The process then
// exited 0 having done nothing at all — no tick, no data dir, no output. On
// macOS /tmp is a symlink to /private/tmp, so this was not a rare path.
test("invoking the runner through a symlink still executes a real sweep", () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const runner = join(here, "runner.mjs");
  const scratch = mkdtempSync(join(tmpdir(), "runner-symlink-"));
  try {
    const link = join(scratch, "runner-via-symlink.mjs");
    symlinkSync(runner, link);
    const dataDir = join(scratch, "data");

    const viaLink = spawnSync(process.execPath, [link, "--data-dir", dataDir, "--once"], {
      encoding: "utf8",
    });
    assert.equal(viaLink.status, EXIT.OK, viaLink.stderr);
    assert.match(viaLink.stdout, /"event":"tick"/, "a symlinked invocation must actually sweep");
    assert.match(viaLink.stdout, /"executed":true/);
    assert.match(viaLink.stdout, /"completed_sweeps":1/);
    assert.equal(existsSync(dataDir), true, "the data dir must be created when run via a symlink");

    // And the real path must behave identically.
    const viaReal = spawnSync(process.execPath, [runner, "--data-dir", join(scratch, "data2"), "--once"], {
      encoding: "utf8",
    });
    assert.equal(viaReal.status, EXIT.OK, viaReal.stderr);
    assert.match(viaReal.stdout, /"completed_sweeps":1/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
