// CWE-041 battery for T060: "A stale worker from a pre-upgrade core
// cannot write incompatible schema output into a newer session."
//
// Three surfaces, all on the real built runtime of the accepted tree:
//  1. The standalone store the CLI composes (LocalSqliteStore): state
//     writes are compare-and-swap on state_version. A stale worker
//     holding the pre-upgrade v0 record tries to write a forged state
//     into a session the current worker already advanced to v1. The
//     write is refused with COUNCIL_STATE_CONFLICT and the stored
//     record is byte-identical afterwards.
//  2. The canonical store service (CouncilStoreService): the same
//     attempt is refused with PERSISTENCE_STATE_CONFLICT, the record
//     is unchanged, and every journal hash chain still verifies.
//  3. The contract surface: a session-state payload stamped with a
//     pre-upgrade schema version (wise-elders.session-state/v0) fails
//     validation, while the current v1 record validates.

import assert from "node:assert/strict";
import { join } from "node:path";
import test from "node:test";
import { runDriver, scratchRoot, treeA } from "./harness.mjs";

test("T060 standalone store: stale worker write is refused, record unchanged", () => {
  const scratch = scratchRoot();
  const a = treeA(scratch);
  const { result } = runDriver(a.runtimeDir, {
    op: "stale-worker-local",
    dataDir: join(scratch, "data-local"),
    sessionId: "cwe041-t060-local",
  });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.stale_error?.code, "COUNCIL_STATE_CONFLICT");
  assert.equal(result.state_after, "READY");
  assert.equal(result.state_version_after, 1);
  assert.equal(result.record_unchanged, true);
});

test("T060 canonical store: stale worker write is refused, chains verify, record unchanged", () => {
  const scratch = scratchRoot();
  const a = treeA(scratch);
  const { result } = runDriver(a.runtimeDir, {
    op: "stale-worker-canonical",
    dataDir: join(scratch, "data-canonical"),
    sessionId: "cwe041-t060-canonical",
  });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.stale_error?.code, "PERSISTENCE_STATE_CONFLICT");
  assert.equal(result.state_after, "READY");
  assert.equal(result.state_version_after, 1);
  assert.equal(result.record_unchanged, true);
  assert.ok(Array.isArray(result.chains) && result.chains.length >= 1);
  assert.ok(result.chains.every((c) => c.ok), JSON.stringify(result.chains));
});

test("T060 contract surface: pre-upgrade schema version fails validation, current passes", () => {
  const scratch = scratchRoot();
  const a = treeA(scratch);
  const { result } = runDriver(a.runtimeDir, {
    op: "stale-worker-canonical",
    dataDir: join(scratch, "data-contract"),
    sessionId: "cwe041-t060-contract",
  });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.bad_schema_validation.ok, false);
  assert.ok(
    result.bad_schema_validation.issues.some((i) => i.includes("schema_version")),
    JSON.stringify(result.bad_schema_validation),
  );
  assert.equal(result.good_schema_validation.ok, true);
});
