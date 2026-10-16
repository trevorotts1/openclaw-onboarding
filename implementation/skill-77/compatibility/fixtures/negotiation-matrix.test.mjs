// CWE-041 battery: the version-negotiation matrix.
//
// Exercises negotiate.mjs against the committed descriptor snapshots
// (derived from the three accepted trees) and against synthetic skew
// variants the matrix must handle: contract mismatch in both directions,
// an older Command Center with no registry contract (T116 lives in its
// own battery file), schema surface disagreement, an unrecorded tree, a
// recorded distribution tree, skill-version skew (portable), an
// authority-mode clash, and standalone negotiation with no peer.
//
// When the three source trees are available (env CWE041_CC_ROOT /
// CWE041_999_ROOT, or the standard worktree layout), descriptors are
// re-derived live and must equal the committed snapshots field for
// field, so the snapshots can never silently go stale.

import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import {
  checkManifest,
  derive999Descriptor,
  deriveCcDescriptor,
  deriveOnbSkillDescriptor,
  gateSessionStart,
  negotiatePair,
} from "../negotiate.mjs";
import { CANONICAL_SKILL_ROOT, COMPAT_DIR, readJson } from "./harness.mjs";

const manifest = readJson(join(COMPAT_DIR, "compatibility-manifest.json"));
const onb = readJson(join(COMPAT_DIR, "descriptors", "onb-canonical.json"));
const cc = readJson(join(COMPAT_DIR, "descriptors", "cc-composed.json"));
const nine = readJson(join(COMPAT_DIR, "descriptors", "nine99-distribution.json"));

const clone = (o) => JSON.parse(JSON.stringify(o));

test("manifest self-check passes and binds the accepted cohort", () => {
  assert.deepEqual(checkManifest(manifest), []);
  const commits = manifest.release_cohort.members.map((m) => m.commit).sort();
  assert.deepEqual(commits, [cc.commit, nine.commit, onb.commit].sort());
});

test("snapshots agree with the manifest's recorded identities", () => {
  assert.equal(onb.tree_identity.computed_aggregate_sha256, "6b523e97b3b27daeb529bf798e6525065e4967337d2182d0880afcc1690e8dbf");
  assert.equal(onb.tree_identity.computed_file_count, 309);
  assert.equal(onb.tree_identity.archive.sha256, "cdfdb8a6d903f79f101a8950666bbfe412d1e6ae1bc91a75134c080e5814552c");
  assert.equal(onb.tree_identity.archive.bytes, 979_759);
  assert.equal(nine.tree_identity.computed_aggregate_sha256, "0c11a84dbaef9bcfeac3f804079a3c04d5c27e9b63be015eef955ac5d19edd71");
  assert.equal(nine.tree_identity.computed_file_count, 310);
  assert.equal(nine.canonical_source.source_commit, onb.commit);
  assert.equal(cc.contract_package_version, onb.contract_package_version);
  assert.equal(cc.generated_contracts.package_version, onb.contract_package_version);
  assert.equal(cc.endpoint_registry_contract, manifest.wire_contract.endpoint_registry_contract);
  assert.equal(cc.cc_migration_allocated, false);
});

test("accepted cohort, canonical skill paired with Command Center: compatible", () => {
  const r = negotiatePair({ skill: onb, cc, manifest });
  assert.equal(r.decision, "compatible");
  assert.equal(r.allowed, true);
  assert.deepEqual(r.refusals, []);
  assert.deepEqual(r.advisories.map((a) => a.code), ["MIGRATION_ID_UNALLOCATED"]);
  assert.ok(r.checks.every((c) => c.ok), JSON.stringify(r.checks.filter((c) => !c.ok)));
});

test("accepted cohort, 999 distribution skill paired with Command Center: compatible", () => {
  const r = negotiatePair({ skill: nine, cc, manifest });
  assert.equal(r.decision, "compatible");
  assert.equal(r.allowed, true);
  assert.deepEqual(r.refusals, []);
});

test("standalone negotiation (no Command Center peer): compatible, recorded identity required", () => {
  const r = negotiatePair({ skill: onb, cc: null, manifest });
  assert.equal(r.decision, "compatible");
  assert.equal(r.mode, "standalone");
  const tampered = clone(onb);
  tampered.tree_identity.computed_aggregate_sha256 = "0".repeat(64);
  const r2 = negotiatePair({ skill: tampered, cc: null, manifest });
  assert.equal(r2.decision, "not-ready");
  assert.deepEqual(r2.refusals.map((x) => x.code), ["COMPAT_TREE_IDENTITY_MISMATCH"]);
});

test("new skill with an older Command Center contract: not-ready, contract mismatch", () => {
  const oldCc = clone(cc);
  oldCc.contract_package_version = "wise-elders.core/0.9.0";
  const r = negotiatePair({ skill: onb, cc: oldCc, manifest });
  assert.equal(r.decision, "not-ready");
  assert.ok(r.refusals.map((x) => x.code).includes("COMPAT_CONTRACT_VERSION_MISMATCH"));
});

test("older skill contract with the new Command Center: not-ready, contract mismatch", () => {
  const oldSkill = clone(onb);
  oldSkill.contract_package_version = "wise-elders.core/0.9.0";
  const r = negotiatePair({ skill: oldSkill, cc, manifest });
  assert.equal(r.decision, "not-ready");
  assert.ok(r.refusals.map((x) => x.code).includes("COMPAT_CONTRACT_VERSION_MISMATCH"));
});

test("one session exchange surface at a different schema version: not-ready, named surface", () => {
  const skewed = clone(cc);
  skewed.schema_versions.verdict = "wise-elders.verdict/v2";
  const r = negotiatePair({ skill: onb, cc: skewed, manifest });
  assert.equal(r.decision, "not-ready");
  const refusal = r.refusals.find((x) => x.code === "COMPAT_SCHEMA_VERSION_UNSUPPORTED");
  assert.ok(refusal, JSON.stringify(r.refusals));
  assert.match(refusal.detail, /verdict/);
});

test("registry contract present but different: not-ready, registry mismatch", () => {
  const other = clone(cc);
  other.endpoint_registry_contract = "wise-elders.endpoint-contract/v2";
  const r = negotiatePair({ skill: onb, cc: other, manifest });
  assert.equal(r.decision, "not-ready");
  assert.ok(r.refusals.map((x) => x.code).includes("COMPAT_REGISTRY_CONTRACT_MISMATCH"));
});

test("hand-edited skill tree (unrecorded identity): not-ready, tree identity mismatch", () => {
  const edited = clone(nine);
  edited.tree_identity.computed_aggregate_sha256 = "f".repeat(64);
  const r = negotiatePair({ skill: edited, cc, manifest });
  assert.equal(r.decision, "not-ready");
  assert.ok(r.refusals.map((x) => x.code).includes("COMPAT_TREE_IDENTITY_MISMATCH"));
});

test("distribution tree vendored from a stale canonical commit: not-ready", () => {
  const stale = clone(nine);
  stale.canonical_source.source_commit = "b2bc56aa25c66703134f4b4cf3807c4da515a8d9";
  const r = negotiatePair({ skill: stale, cc, manifest });
  assert.equal(r.decision, "not-ready");
  assert.ok(r.refusals.map((x) => x.code).includes("COMPAT_TREE_IDENTITY_MISMATCH"));
});

test("skill version skew with equal contract: compatible-portable, visual not ready", () => {
  const older = clone(onb);
  older.skill_version = "v0.9.0";
  const r = negotiatePair({ skill: older, cc, manifest });
  assert.equal(r.decision, "compatible-portable");
  assert.equal(r.allowed, true);
  assert.ok(r.advisories.map((a) => a.code).includes("VISUAL_EXPERIENCE_NOT_READY"));
});

test("Command Center ahead of the cohort with equal contract: compatible-portable", () => {
  const ahead = clone(cc);
  ahead.commit = "a".repeat(40);
  const r = negotiatePair({ skill: onb, cc: ahead, manifest });
  assert.equal(r.decision, "compatible-portable");
  assert.ok(r.advisories.map((a) => a.code).includes("PEER_AHEAD_OF_COHORT"));
});

test("authority mode clash: recorded standalone, managed requested: not-ready", () => {
  const r = negotiatePair({
    skill: onb,
    cc,
    manifest,
    requestedAuthorityMode: "managed",
    recordedAuthorityMode: "standalone",
  });
  assert.equal(r.decision, "not-ready");
  assert.ok(r.refusals.map((x) => x.code).includes("COMPAT_AUTHORITY_MODE_MISMATCH"));
  const ok = negotiatePair({
    skill: onb,
    cc,
    manifest,
    requestedAuthorityMode: "managed",
    recordedAuthorityMode: "managed",
  });
  assert.equal(ok.decision, "compatible");
});

test("missing component: not-ready, component missing", () => {
  const r = negotiatePair({ skill: null, cc, manifest });
  assert.equal(r.decision, "not-ready");
  assert.ok(r.refusals.map((x) => x.code).includes("COMPAT_COMPONENT_MISSING"));
});

test("session-start gate agrees with negotiation on every matrix row", () => {
  const rows = [
    { skill: onb, cc },
    { skill: nine, cc },
    { skill: onb, cc: null },
    { skill: onb, cc: { ...clone(cc), endpoint_registry_contract: null } },
    { skill: { ...clone(onb), contract_package_version: "wise-elders.core/0.9.0" }, cc },
  ];
  for (const row of rows) {
    const gate = gateSessionStart({ ...row, manifest });
    const neg = negotiatePair({ ...row, manifest });
    assert.equal(gate.allowed, neg.allowed);
    assert.equal(gate.decision, neg.decision);
  }
});

// ------------------------------------------------------------ live derivation

const ccRoot = process.env.CWE041_CC_ROOT ?? join(process.env.HOME ?? "", "workspace", "skill77", "worktrees", "cc-cwe041");
const nineRoot = process.env.CWE041_999_ROOT ?? join(process.env.HOME ?? "", "workspace", "skill77", "worktrees", "999-cwe041");

test("live derivation from the accepted ONB tree equals the snapshot", () => {
  const live = deriveOnbSkillDescriptor(CANONICAL_SKILL_ROOT);
  assert.deepEqual(live, onb);
});

test("live derivation from the accepted CC tree equals the snapshot", (t) => {
  if (!existsSync(join(ccRoot, "src", "lib", "council"))) {
    t.skip(`CC tree not present at ${ccRoot}`);
    return;
  }
  const live = deriveCcDescriptor(ccRoot);
  assert.deepEqual(live, cc);
});

test("live derivation from the accepted 999 tree equals the snapshot", (t) => {
  if (!existsSync(join(nineRoot, "installer-registration", "council-vendoring.json"))) {
    t.skip(`999 tree not present at ${nineRoot}`);
    return;
  }
  const live = derive999Descriptor(nineRoot);
  assert.deepEqual(live, nine);
});
