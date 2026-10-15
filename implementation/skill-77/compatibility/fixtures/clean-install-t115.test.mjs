// CWE-041 battery for T115: "A clean install verifies locked
// dependencies, compiled core and pack hashes; generated consumers
// match canonical source."
//
// Legs:
//  1. A pristine copy of the accepted tree passes the product doctor
//     and bundle verifier before anything is installed.
//  2. The product installer (scripts/install-runtime.mjs) refuses
//     nothing here because the tree is well formed: every dependency
//     in runtime/package.json is an exact pin, the isolated install
//     lands exactly those versions in node_modules, the compiled core
//     (dist/index.js) and the CLI bundle (dist/blackceo-council.mjs)
//     exist, and the runtime doctor reports the cohort contract
//     version against a scratch data directory.
//  3. Pack hashes: the copied tree's recomputed aggregate equals the
//     canonical manifest aggregate, and the archive hash and size
//     equal the accepted record.
//  4. Generated consumers match canonical source: the Command Center's
//     generated contracts artifact carries the same contract package
//     version as the canonical core, and the 999 vendoring record's
//     per-file canonical hashes match the canonical tree file for
//     file; in the vendored tree, every file matches its canonical
//     hash except exactly the files the reconciliation records as
//     intentionally different.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { treeAggregate } from "../negotiate.mjs";
import {
  CANONICAL_SKILL_ROOT,
  COMPAT_DIR,
  copyTree,
  installTree,
  inventory,
  readJson,
  runDriver,
  scratchRoot,
  sha256Hex,
} from "./harness.mjs";

const manifest = readJson(join(COMPAT_DIR, "compatibility-manifest.json"));
const cohortOnb = manifest.release_cohort.members.find((m) => m.component === "onb-skill");

function runNode(args, opts = {}) {
  return spawnSync("node", args, {
    encoding: "utf8",
    timeout: 300_000,
    env: { ...process.env, ...(opts.env ?? {}) },
    cwd: opts.cwd,
  });
}

test("T115 clean install: doctor, locked pins, compiled core, pack hashes", async () => {
  const scratch = scratchRoot();
  const root = join(scratch, "clean", "77-council-of-wise-elders");
  copyTree(CANONICAL_SKILL_ROOT, root);

  // Leg 1: pristine tree passes doctor and bundle verification.
  const doctor = runNode([join(root, "scripts", "doctor.mjs"), "--root", root]);
  assert.equal(doctor.status, 0, doctor.stdout + doctor.stderr);
  assert.match(doctor.stdout, /DOCTOR: PASS/);
  const verify = runNode([join(root, "scripts", "verify-bundles.mjs"), "--root", root]);
  assert.equal(verify.status, 0, verify.stdout + verify.stderr);

  // Leg 3 (before install): pack hashes match the accepted record.
  const agg = treeAggregate(root);
  assert.equal(agg.aggregate_sha256, cohortOnb.tree_identity.aggregate_sha256);
  assert.equal(agg.file_count, cohortOnb.tree_identity.file_count);
  const archiveBytes = readFileSync(join(root, "council-of-wise-elders.skill"));
  assert.equal(sha256Hex(archiveBytes), cohortOnb.archive.sha256);
  assert.equal(archiveBytes.length, cohortOnb.archive.bytes);

  // Leg 2: locked dependencies are exact pins and install lands them.
  const pkg = readJson(join(root, "runtime", "package.json"));
  const pins = [];
  for (const section of ["dependencies", "devDependencies"]) {
    for (const [name, version] of Object.entries(pkg[section] ?? {})) {
      assert.match(version, /^\d+\.\d+\.\d+$/, `${name} must be an exact pin, got ${version}`);
      pins.push([name, version]);
    }
  }
  assert.ok(pins.length >= 4, `expected the pinned set, got ${pins.length}`);
  const install = installTree(root, join(scratch, "clean-install.log"));
  assert.equal(install.status, 0, install.stdout + install.stderr);
  for (const [name, version] of pins) {
    const installed = readJson(join(root, "runtime", "node_modules", name, "package.json"));
    assert.equal(installed.version, version, `${name}: installed ${installed.version}, pin ${version}`);
  }
  assert.ok(existsSync(install.distIndex), "compiled core dist/index.js exists");
  assert.ok(existsSync(install.bundle), "compiled CLI bundle exists");

  // The runtime doctor (the compiled core itself) reports readiness and
  // the cohort contract version against a scratch data directory.
  const dataDir = join(scratch, "doctor-data");
  const { result } = runDriver(install.runtimeDir, {
    op: "cli",
    args: ["doctor", "--json", "--data-dir", dataDir],
  });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.exit, 0, result.stdout + result.stderr);
  const doctorJson = JSON.parse(result.stdout);
  assert.equal(doctorJson.ok, true);
  assert.equal(doctorJson.contracts, manifest.wire_contract.contract_package_version);
});

test("T115 generated consumers: Command Center artifact matches canonical contract", (t) => {
  const ccRoot =
    process.env.CWE041_CC_ROOT ??
    join(process.env.HOME ?? "", "workspace", "skill77", "worktrees", "cc-cwe041");
  const generatedPath = join(ccRoot, "src", "lib", "council", "contracts", "generated", "json-schemas.json");
  if (!existsSync(generatedPath)) {
    t.skip(`CC tree not present at ${ccRoot}`);
    return;
  }
  const generated = readJson(generatedPath);
  assert.equal(generated.package_version, manifest.wire_contract.contract_package_version);
  // The generated schemas carry the same per-surface schema versions.
  const verdict = generated.schemas?.Verdict;
  assert.ok(verdict, "generated artifact carries the Verdict schema");
  assert.equal(
    JSON.stringify(verdict).includes(manifest.wire_contract.schema_versions.verdict),
    true,
  );
});

test("T115 generated consumers: 999 vendoring record matches canonical tree and vendored copy", (t) => {
  const nineRoot =
    process.env.CWE041_999_ROOT ??
    join(process.env.HOME ?? "", "workspace", "skill77", "worktrees", "999-cwe041");
  const recordPath = join(nineRoot, "installer-registration", "council-vendoring.json");
  if (!existsSync(recordPath)) {
    t.skip(`999 tree not present at ${nineRoot}`);
    return;
  }
  const record = readJson(recordPath);
  // The record's canonical source is the accepted cohort commit.
  assert.equal(record.canonical_source.source_commit, cohortOnb.commit);
  assert.equal(record.canonical_source.canonical_aggregate_sha256, cohortOnb.tree_identity.aggregate_sha256);
  // Every per-file canonical hash in the record matches the canonical
  // tree on disk.
  const canonicalFiles = record.canonical_files ?? {};
  const names = Object.keys(canonicalFiles);
  assert.ok(names.length >= 290, `expected the full canonical file map, got ${names.length}`);
  for (const rel of names) {
    const bytes = readFileSync(join(CANONICAL_SKILL_ROOT, rel));
    assert.equal(sha256Hex(bytes), canonicalFiles[rel], `canonical file drift: ${rel}`);
  }
  // In the vendored copy, a file may differ from its canonical hash
  // only when the reconciliation records that file as intentionally
  // different.
  const vendoredRoot = join(nineRoot, ".claude", "skills", "council-of-wise-elders");
  const differingAllowed = new Set();
  for (const diff of record.intentional_distribution_differences ?? []) {
    for (const item of diff.items ?? []) if (item.file) differingAllowed.add(item.file);
    for (const field of diff.fields ?? []) if (field.file) differingAllowed.add(field.file);
    for (const f of diff.files ?? []) differingAllowed.add(f);
    if (diff.file) differingAllowed.add(diff.file);
  }
  const mismatches = [];
  for (const rel of names) {
    const vendoredPath = join(vendoredRoot, rel);
    if (!existsSync(vendoredPath)) {
      mismatches.push(`${rel} (missing in vendored copy)`);
      continue;
    }
    const h = sha256Hex(readFileSync(vendoredPath));
    if (h !== canonicalFiles[rel] && !differingAllowed.has(rel)) {
      mismatches.push(`${rel} (differs, not recorded)`);
    }
  }
  assert.deepEqual(mismatches, []);
  // And the vendored tree's own distribution aggregate reproduces.
  const distAgg = treeAggregate(vendoredRoot);
  assert.equal(distAgg.aggregate_sha256, record.distribution.distribution_aggregate_sha256);
  assert.equal(distAgg.file_count, record.distribution.distribution_file_count);
});
