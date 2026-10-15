// CWE-041 battery for T116: "A new skill paired with an incompatible
// older Command Center reports not-ready rather than starting a shadow
// session."
//
// Two legs:
//  1. The negotiation gate: the accepted (new) skill descriptor paired
//     with a synthetic older Command Center descriptor (no council
//     endpoint registry contract, older contract package version) must
//     return not-ready with typed codes, and the gate must be pure:
//     it performs no writes and creates no session state anywhere.
//  2. The product leg: on the real runtime, a session start with no
//     valid run grant is refused with RUN_AUTHORIZATION_REQUIRED and
//     the session never leaves DRAFT: the product has no shadow start
//     path around its gates.

import assert from "node:assert/strict";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { gateSessionStart, negotiatePair } from "../negotiate.mjs";
import {
  COMPAT_DIR,
  mkdirp,
  readJson,
  runDriver,
  scratchRoot,
  treeA,
} from "./harness.mjs";

const manifest = readJson(join(COMPAT_DIR, "compatibility-manifest.json"));
const onb = readJson(join(COMPAT_DIR, "descriptors", "onb-canonical.json"));
const cc = readJson(join(COMPAT_DIR, "descriptors", "cc-composed.json"));

const clone = (o) => JSON.parse(JSON.stringify(o));

function olderCommandCenter() {
  // A Command Center from before the council surface existed in it:
  // it declares no council endpoint registry contract and an older
  // contract package version. Labeled synthetic: no older Command
  // Center build exists in the accepted graph to derive from.
  const old = clone(cc);
  old.endpoint_registry_contract = null;
  old.contract_package_version = "wise-elders.core/0.9.0";
  old.council_route_groups = [];
  old.generated_contracts = { artifact: null, package_version: null };
  return old;
}

test("T116 gate: new skill + older Command Center = not-ready with typed codes", () => {
  const r = negotiatePair({ skill: onb, cc: olderCommandCenter(), manifest });
  assert.equal(r.decision, "not-ready");
  assert.equal(r.allowed, false);
  const codes = r.refusals.map((x) => x.code);
  assert.ok(codes.includes("COMPAT_REGISTRY_CONTRACT_MISSING"), codes.join(","));
  assert.ok(codes.includes("COMPAT_CONTRACT_VERSION_MISMATCH"), codes.join(","));
});

test("T116 gate: session-start gate refuses and is pure (no writes, no state)", () => {
  const scratch = scratchRoot();
  const watchDir = mkdirp(join(scratch, "watched"));
  const before = readdirSync(watchDir);
  const gate = gateSessionStart({ skill: onb, cc: olderCommandCenter(), manifest });
  assert.equal(gate.allowed, false);
  assert.equal(gate.decision, "not-ready");
  assert.ok(gate.refusal_codes.includes("COMPAT_REGISTRY_CONTRACT_MISSING"));
  // Purity: the watched directory is untouched and no data directory
  // was created anywhere the gate could have written one.
  assert.deepEqual(readdirSync(watchDir), before);
  assert.equal(existsSync(join(watchDir, "council.db")), false);
  assert.equal(existsSync(join(watchDir, "council-profile.json")), false);
});

test("T116 gate: the same skill with the accepted Command Center is allowed", () => {
  const gate = gateSessionStart({ skill: onb, cc, manifest });
  assert.equal(gate.allowed, true);
  assert.equal(gate.decision, "compatible");
});

test("T116 product leg: a grantless start on the real runtime is refused and leaves no run state", async () => {
  const scratch = scratchRoot();
  const a = treeA(scratch);
  const dataDir = join(scratch, "data-nogrant");
  const { result } = runDriver(a.runtimeDir, {
    op: "start-nogrant",
    dataDir,
    sessionId: "cwe041-t116-nogrant",
  });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.start_error?.code, "RUN_AUTHORIZATION_REQUIRED");
  // No shadow session: the created session never left DRAFT, its state
  // version never advanced past creation, and no run events exist
  // beyond the creation record.
  assert.equal(result.state_after_refusal, "DRAFT");
  assert.equal(result.state_version_after_refusal, 0);
});
