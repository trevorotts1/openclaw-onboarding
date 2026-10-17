// CWE-041 battery: backup, restore, rollback, and active-session
// checkpointing (directive Sections 16.5, 27.4).
//
// Scenario, all on the real built runtime:
//  1. A baseline session runs to completion in the data directory
//     (its transport call count is the uninterrupted reference for a
//     run of this shape).
//  2. A second session starts with a gated transport and is caught
//     mid-flight: some advisor operations have committed cards, the
//     rest have not run. A backup of the whole data directory is
//     taken with a hash inventory.
//  3. The running process is killed (the rollback event: the old
//     build dies mid-flight). With the tree rolled back (tree A
//     again), the session is still there: same session ID, same
//     state, same state version, same committed cards, same event
//     history, no verdict yet.
//  4. The owner pauses the session (checkpoint consolidation) and
//     resumes it under a valid grant. It completes from its
//     checkpoint: calls before the gate plus calls spent resuming
//     equal one uninterrupted run, so no completed operation is
//     repeated and none is skipped; the event sequence is continuous
//     with no gaps or duplicates.
//  5. Data restore leg: the data directory is backed up again,
//     deleted, and restored from the backup. The restored inventory
//     matches the backup inventory hash for hash, and both sessions
//     read back with their verdicts and full histories.

import assert from "node:assert/strict";
import { cpSync, existsSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import {
  inventory,
  runDriver,
  scratchRoot,
  startDriver,
  treeA,
  waitForFile,
} from "./harness.mjs";

const ALLOW_CALLS = 3;

// Copying a live SQLite data directory races the store's own WAL
// bookkeeping (companion files appear and disappear as connections
// open and close). A backup is therefore copied with retries and then
// PROVEN: the copy must open through the real runtime and reproduce
// the expected session snapshot before the battery trusts it.
function copyWithRetries(src, dst, attempts = 5) {
  let lastError = null;
  for (let i = 0; i < attempts; i++) {
    try {
      rmSync(dst, { recursive: true, force: true });
      cpSync(src, dst, { recursive: true });
      return;
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}

test("rollback: mid-flight session survives process death and resumes from checkpoint", async () => {
  const scratch = scratchRoot();
  const a = treeA(scratch);
  const dataDir = join(scratch, "data-rollback");
  const baselineId = "cwe041-rollback-baseline";
  const sessionId = "cwe041-rollback-midflight";

  // 1. Baseline completed session in the same data directory.
  const baseline = runDriver(a.runtimeDir, {
    op: "lifecycle",
    dataDir,
    sessionId: baselineId,
  }).result;
  assert.equal(baseline.ok, true, JSON.stringify(baseline));
  assert.equal(baseline.state, "COMPLETED");
  assert.equal(baseline.verdict_present, true);
  assert.ok(
    baseline.transport_calls > ALLOW_CALLS,
    `reference run should spend more than ${ALLOW_CALLS} calls, spent ${baseline.transport_calls}`,
  );

  // 2. Mid-flight session, gated after ALLOW_CALLS committed calls.
  const midflightFile = join(scratch, "midflight.json");
  const running = startDriver(a.runtimeDir, {
    op: "gated-start",
    dataDir,
    sessionId,
    allowCalls: ALLOW_CALLS,
    midflightFile,
  });
  const gated = await waitForFile(midflightFile, 90_000);
  if (!gated) {
    running.child.kill("SIGKILL");
    assert.fail(`session never reached the gate; driver output: ${JSON.stringify(running.output())}`);
  }
  const midflight = JSON.parse(readFileSync(midflightFile, "utf8"));
  assert.equal(midflight.session_id, sessionId);
  assert.equal(midflight.transport_calls_before_gate, ALLOW_CALLS);
  assert.ok(midflight.cards_committed >= 1, `expected committed work before the gate, got ${midflight.cards_committed}`);
  assert.ok(midflight.event_count >= 1);

  // Backup before the rollback, with its hash inventory. The backup is
  // verified by opening it: it must reproduce the mid-flight snapshot.
  const backupDir = join(scratch, "backup-midflight");
  copyWithRetries(dataDir, backupDir);
  const backupInventory = inventory(backupDir);
  assert.ok(backupInventory.file_count >= 1);
  const backupCheck = runDriver(a.runtimeDir, { op: "inspect", dataDir: backupDir, sessionId }).result;
  assert.equal(backupCheck.ok, true, JSON.stringify(backupCheck));
  assert.equal(backupCheck.state, midflight.state);
  assert.equal(backupCheck.state_version, midflight.state_version);
  assert.equal(backupCheck.event_count, midflight.event_count);
  assert.equal(backupCheck.cards_committed, midflight.cards_committed);

  // 3. The old process dies mid-flight; the session reads back as left.
  running.child.kill("SIGKILL");
  await Promise.race([
    new Promise((r) => running.child.on("exit", r)),
    new Promise((r) => setTimeout(r, 10_000)),
  ]);
  const afterDeath = runDriver(a.runtimeDir, { op: "inspect", dataDir, sessionId }).result;
  assert.equal(afterDeath.ok, true, JSON.stringify(afterDeath));
  assert.equal(afterDeath.session_id, sessionId);
  assert.equal(afterDeath.state, midflight.state);
  assert.equal(afterDeath.state_version, midflight.state_version);
  assert.equal(afterDeath.event_count, midflight.event_count);
  assert.equal(afterDeath.cards_committed, midflight.cards_committed);
  assert.equal(afterDeath.verdict_present, false);

  // 4. Pause (checkpoint consolidation), then resume from checkpoint.
  const paused = runDriver(a.runtimeDir, { op: "pause", dataDir, sessionId }).result;
  assert.equal(paused.ok, true, JSON.stringify(paused));
  assert.equal(paused.state, "PAUSED");
  assert.equal(paused.resume_phase, midflight.state);

  const resumed = runDriver(a.runtimeDir, { op: "resume", dataDir, sessionId }).result;
  assert.equal(resumed.ok, true, JSON.stringify(resumed));
  assert.equal(resumed.state, "COMPLETED");
  assert.equal(resumed.verdict_present, true);
  assert.equal(
    ALLOW_CALLS + resumed.transport_calls,
    baseline.transport_calls,
    `gate ${ALLOW_CALLS} + resume ${resumed.transport_calls} != uninterrupted ${baseline.transport_calls}`,
  );
  const seqs = resumed.event_sequences;
  assert.deepEqual(seqs, Array.from({ length: seqs.length }, (_, i) => i + 1));
  assert.ok(resumed.event_count > midflight.event_count);

  // 5. Backup, delete, restore: inventory identical, sessions intact.
  const backup2Dir = join(scratch, "backup-final");
  copyWithRetries(dataDir, backup2Dir);
  const backup2 = inventory(backup2Dir);
  rmSync(dataDir, { recursive: true, force: true });
  assert.equal(existsSync(dataDir), false);
  copyWithRetries(backup2Dir, dataDir);
  const restoredInventory = inventory(dataDir);
  assert.equal(restoredInventory.inventory_sha256, backup2.inventory_sha256);

  const restoredMid = runDriver(a.runtimeDir, { op: "inspect", dataDir, sessionId }).result;
  assert.equal(restoredMid.ok, true, JSON.stringify(restoredMid));
  assert.equal(restoredMid.session_id, sessionId);
  assert.equal(restoredMid.state, "COMPLETED");
  assert.equal(restoredMid.state_version, resumed.state_version);
  assert.equal(restoredMid.event_count, resumed.event_count);
  assert.equal(restoredMid.verdict_present, true);

  const restoredBase = runDriver(a.runtimeDir, { op: "inspect", dataDir, sessionId: baselineId }).result;
  assert.equal(restoredBase.ok, true, JSON.stringify(restoredBase));
  assert.equal(restoredBase.session_id, baselineId);
  assert.equal(restoredBase.state, "COMPLETED");
  assert.equal(restoredBase.state_version, baseline.state_version);
  assert.equal(restoredBase.event_count, baseline.event_count);
  assert.equal(restoredBase.verdict_present, true);

  // Receipt fields named by the compatibility manifest, on disk here:
  // backup_inventory_sha256 == restored_inventory_sha256 above, plus
  // session IDs, state versions, event counts, and verdict presence
  // for both sessions.
});
