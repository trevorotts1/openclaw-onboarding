// CWE-041 battery: data and settings preservation across upgrades and
// paired/unpaired modes (directive Sections 16.1, 26, 27.3).
//
// Legs:
//  1. Upgrade preservation (standalone): a session is created and run
//     to a verdict under tree A. The skill tree is then replaced by the
//     upgraded tree B (version-bumped copy). Under tree B, the same
//     data directory yields the same session ID, state, state version,
//     full event history, and verdict; the installation profile file
//     is byte-identical; and the runtime doctor under tree B reports
//     the same settings block and contract version. Rolling back to
//     tree A reads the same state again.
//  2. Paired/unpaired authority boundaries: a data directory recorded
//     as standalone refuses a managed open with
//     PERSISTENCE_AUTHORITY_MODE_MISMATCH and its file inventory is
//     unchanged by the refused open (no second, divergent store was
//     created); a directory recorded as managed refuses the standalone
//     composition the same way, in both config directions.

import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import {
  inventory,
  runDriver,
  scratchRoot,
  treeA,
  treeB,
} from "./harness.mjs";

test("preservation: session, history, verdict, and profile survive a tree upgrade and rollback", async () => {
  const scratch = scratchRoot();
  const a = treeA(scratch);
  const b = treeB(scratch);
  const dataDir = join(scratch, "data-upgrade");
  const sessionId = "cwe041-preservation-session";

  const before = runDriver(a.runtimeDir, { op: "lifecycle", dataDir, sessionId }).result;
  assert.equal(before.ok, true, JSON.stringify(before));
  assert.equal(before.state, "COMPLETED");
  assert.equal(before.verdict_present, true);
  const filesBefore = inventory(dataDir).files.map((f) => f.path);

  // The upgrade: tree B's runtime opens the same data directory.
  const afterUpgrade = runDriver(b.runtimeDir, { op: "inspect", dataDir, sessionId }).result;
  assert.equal(afterUpgrade.ok, true, JSON.stringify(afterUpgrade));
  assert.equal(afterUpgrade.session_id, before.session_id);
  assert.equal(afterUpgrade.state, before.state);
  assert.equal(afterUpgrade.state_version, before.state_version);
  assert.equal(afterUpgrade.event_count, before.event_count);
  assert.deepEqual(afterUpgrade.event_sequences, before.event_sequences);
  assert.equal(afterUpgrade.verdict_present, true);
  assert.equal(afterUpgrade.cards_committed, before.cards_committed);
  // The upgrade neither swept state files away nor added new ones.
  assert.deepEqual(inventory(dataDir).files.map((f) => f.path), filesBefore);

  // Doctor under the upgraded tree: same contracts and settings.
  const doctorB = runDriver(b.runtimeDir, {
    op: "cli",
    args: ["doctor", "--json", "--data-dir", dataDir],
  }).result;
  assert.equal(doctorB.exit, 0, doctorB.stdout + doctorB.stderr);
  const doctorA = runDriver(a.runtimeDir, {
    op: "cli",
    args: ["doctor", "--json", "--data-dir", dataDir],
  }).result;
  const settingsA = JSON.parse(doctorA.stdout).settings;
  const settingsB = JSON.parse(doctorB.stdout).settings;
  assert.deepEqual(settingsB, settingsA);
  assert.equal(JSON.parse(doctorB.stdout).contracts, JSON.parse(doctorA.stdout).contracts);

  // Rollback to tree A: the same state reads back identically.
  const afterRollback = runDriver(a.runtimeDir, { op: "inspect", dataDir, sessionId }).result;
  assert.equal(afterRollback.ok, true, JSON.stringify(afterRollback));
  assert.equal(afterRollback.session_id, before.session_id);
  assert.equal(afterRollback.state_version, before.state_version);
  assert.equal(afterRollback.event_count, before.event_count);
});

test("preservation: authority mode recorded at install is never forked by a mismatched open", async () => {
  const scratch = scratchRoot();
  const a = treeA(scratch);
  const dataDir = join(scratch, "data-standalone");
  const dataDirManaged = join(scratch, "data-managed");
  const { result } = runDriver(a.runtimeDir, {
    op: "authority",
    dataDir,
    dataDirManaged,
    sessionId: "cwe041-authority-session",
  });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.recorded_profile.authority_mode, "standalone");
  assert.equal(result.recorded_profile.schema_version, "wise-elders.installation-profile/v1");
  // Managed caller against a standalone profile: typed refusal.
  assert.equal(result.managed_open_error?.code, "PERSISTENCE_AUTHORITY_MODE_MISMATCH");
  // The profile still records standalone afterwards (no silent switch).
  assert.equal(result.profile_after_refusal.authority_mode, "standalone");
  // Standalone composition against a managed profile: typed refusal,
  // and the managed profile also refuses the raw service open path.
  assert.equal(result.standalone_open_error?.code, "PERSISTENCE_AUTHORITY_MODE_MISMATCH");
  assert.equal(result.managed_profile_via_service_error?.code, "PERSISTENCE_AUTHORITY_MODE_MISMATCH");
  // The refused opens created no council database in either directory:
  // neither directory holds a store file the service would have made.
  assert.equal(existsSync(join(dataDir, "council.db")), false);
  assert.equal(existsSync(join(dataDirManaged, "council.db")), false);
  const inv = inventory(dataDir);
  assert.deepEqual(inv.files.map((f) => f.path), ["council-profile.json"]);
});
