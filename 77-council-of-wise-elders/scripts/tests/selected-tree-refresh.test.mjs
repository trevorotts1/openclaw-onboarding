// Selected-tree refresh (scripts/selected-tree-refresh.mjs): the install step
// that was missing. The gate was right to refuse a resolver-selected copy
// carrying the PREVIOUS release's archive — measured on rescue-eddie-otts,
// where four copies all reported skill-version 1.0.80 but the agent-resolved
// copy still carried archive 33e4063d while the release generated 4d921542.
// wire.sh now converges that copy from the shipped tree and re-runs the SAME
// gate, so readiness needs no human rsync. One runnable check.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { checkSelectedTree } from "../selected-tree-gate.mjs";
import { refreshSelectedTree } from "../selected-tree-refresh.mjs";
import { ENTRY_PATH } from "../entry-point-gate.mjs";
import { DISTRIBUTION_KINDS, HASH_METHOD, manifestEntries, treeAggregate } from "../manifest-tree.mjs";

const SCRIPTS = join(dirname(fileURLToPath(import.meta.url)), "..");
const GOOD_ENTRY = "#!/usr/bin/env node\nif (process.argv.includes('--help')) process.exit(0);\nprocess.exit(2);\n";
const CONTRACT =
  "4b. Convene with `blackceo-council convene --brief FILE`. Convening is the approval: " +
  "the client chose the model and pays for it, so there is no grant to resolve and no approval step " +
  "to run or wait for. Do not improvise a parallel council.";

const sha = (buf) => createHash("sha256").update(buf).digest("hex");

function fixtureHome(t) {
  const home = mkdtempSync(join(tmpdir(), "cwe-refresh-"));
  t.after(() => rmSync(home, { recursive: true, force: true }));
  return home;
}

/** A council skill copy: all version carriers, SKILL.md, manifest, advisors, packaged entry. */
function makeCopy(dir, version) {
  mkdirSync(join(dir, "advisors"), { recursive: true });
  mkdirSync(join(dir, "runtime", "dist"), { recursive: true });
  writeFileSync(join(dir, "version"), `${version}\n`);
  writeFileSync(join(dir, "skill-version.txt"), `v${version}\n`);
  writeFileSync(join(dir, "SKILL.md"), `---\nname: council-of-wise-elders\nversion: ${version}\n---\n\n${CONTRACT}\n`);
  writeFileSync(join(dir, "advisors", "pack.json"), '{"items":[1,2,3]}\n');
  writeFileSync(join(dir, ENTRY_PATH), GOOD_ENTRY);
  const manifest = {
    skill_version: version,
    runtime_entry: {
      path: ENTRY_PATH,
      sha256: sha(Buffer.from(GOOD_ENTRY)),
      bytes: Buffer.byteLength(GOOD_ENTRY),
    },
  };
  writeFileSync(join(dir, "manifest.json"), JSON.stringify(manifest, null, 2));
  return dir;
}

/** Rewrite manifest.json so it records the tree exactly as it is now. */
function restamp(dir, extra = {}) {
  const manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8"));
  // An inherited witness block belongs to the tree that declared it, not to a copy.
  if (!("distribution" in extra)) delete manifest.distribution;
  Object.assign(manifest, extra, { hash_method: extra.hash_method ?? HASH_METHOD });
  const { entries, aggregate } = treeAggregate(dir);
  Object.assign(manifest, { file_count: entries.length, aggregate_sha256: aggregate, files: entries });
  writeFileSync(join(dir, "manifest.json"), JSON.stringify(manifest, null, 2));
  return manifest;
}

/**
 * The fleet shape: a canonical tree whose manifest records the release archive
 * and its distribution contract, plus the 999 distribution of it sitting where
 * the agent resolver points, carrying the PREVIOUS release's archive while
 * every version carrier and the canonical aggregate already say 1.0.80.
 */
function staleDistributionFixture(t) {
  const home = fixtureHome(t);
  const canonical = makeCopy(join(home, "wired", "council-of-wise-elders"), "1.0.80");
  const dist = join(home, ".agents", "skills", "council-of-wise-elders");

  const released = Buffer.from("PK\u0003\u0004 the 1.0.80 release archive\n");
  writeFileSync(join(canonical, "council-of-wise-elders.skill"), released);
  const archiveSha = sha(released);

  // The distribution contract is computed from the packaged staging tree: the
  // same files, plus the reconciliation record it adds, plus the built runtime.
  cpSync(canonical, dist, { recursive: true });
  writeFileSync(
    join(dist, "DISTRIBUTION-RECONCILIATION.json"),
    JSON.stringify(
      {
        artifact: "council-of-wise-elders distribution reconciliation",
        canonical_source: { canonical_aggregate_sha256: "pending", canonical_file_count: 0, skill_version: "1.0.80" },
        intentional_distribution_differences: [],
      },
      null,
      2,
    ),
  );
  const witness = {
    kinds: [...DISTRIBUTION_KINDS],
    files: manifestEntries(dist).filter((f) => f.path !== "DISTRIBUTION-RECONCILIATION.json"),
    runtime_dist: manifestEntries(dist, { includeRuntimeDist: true }).filter((f) => f.path.startsWith("runtime/dist/")),
    added_paths: ["DISTRIBUTION-RECONCILIATION.json"],
  };
  const canonicalManifest = restamp(canonical, { archive: { file: "council-of-wise-elders.skill", sha256: archiveSha }, distribution: witness });

  // The distribution as found on the box: canonical content, its own manifest,
  // a truthful record, and the archive from the PREVIOUS release.
  writeFileSync(join(dist, "council-of-wise-elders.skill"), "PK\u0003\u0004 the 1.0.79 release archive\n");
  writeFileSync(
    join(dist, "DISTRIBUTION-RECONCILIATION.json"),
    JSON.stringify(
      {
        artifact: "council-of-wise-elders distribution reconciliation",
        canonical_source: {
          canonical_aggregate_sha256: canonicalManifest.aggregate_sha256,
          canonical_file_count: canonicalManifest.file_count,
          skill_version: "1.0.80",
        },
        intentional_distribution_differences: [
          { kind: "file_added", file: "DISTRIBUTION-RECONCILIATION.json" },
          { kind: "manifest_regenerated", file: "manifest.json" },
          { kind: "generated_archive_not_vendored", archive_sha256: archiveSha },
        ],
      },
      null,
      2,
    ),
  );
  const stale = restamp(dist, {
    canonical_aggregate_sha256: canonicalManifest.aggregate_sha256,
    canonical_file_count: canonicalManifest.file_count,
  });
  return { home, canonical, dist, canonicalManifest, stale, archiveSha };
}

function gate(home, canonical, dist) {
  return checkSelectedTree({ home, skillDir: canonical, agentSelected: dist, agentSource: "refresh test", load: false });
}

test("(resolver copy) a stale release archive is converged, and the SAME gate then passes", (t) => {
  const { home, canonical, dist, archiveSha } = staleDistributionFixture(t);
  const before = gate(home, canonical, dist);
  assert.equal(before.ok, false, "the gate must refuse a distribution carrying the previous release's archive");
  assert.match(before.problems.join("\n"), /SAME-RELEASE PROOF REFUSED: .*an unverifiable archive is not a distribution artifact/);
  assert.match(before.problems.join("\n"), /carries the archive council-of-wise-elders\.skill/);

  const refresh = refreshSelectedTree({ sourceDir: canonical, selectedDir: dist });
  assert.equal(refresh.status, "refreshed", refresh.problems.join(" | "));
  assert.equal(refresh.mode, "distribution-archive");
  assert.deepEqual(refresh.written, ["council-of-wise-elders.skill"]);
  assert.equal(refresh.archive, archiveSha, "the selected copy must carry the archive this release generated");
  // Owner data is never deleted: the distribution's own reconciliation record stays.
  assert.ok(existsSync(join(dist, "DISTRIBUTION-RECONCILIATION.json")));
  assert.ok(existsSync(join(dist, "manifest.json")));

  const after = gate(home, canonical, dist);
  assert.equal(after.ok, true, after.problems.join(" | "));
  assert.match(after.warnings.join("\n"), /SAME RELEASE: distribution .* is the 999 packaging of canonical aggregate/);
});

test("(resolver copy) the gate still refuses a genuinely stale archive after a refresh", (t) => {
  const { home, canonical, dist } = staleDistributionFixture(t);
  assert.equal(refreshSelectedTree({ sourceDir: canonical, selectedDir: dist }).status, "refreshed");
  // A payload that is not the release's archive is refused exactly as before:
  // the refresh converges the copy, it never teaches the gate to accept drift.
  writeFileSync(join(dist, "council-of-wise-elders.skill"), "junk bytes, not the release's archive\n");
  const after = gate(home, canonical, dist);
  assert.equal(after.ok, false);
  assert.match(after.problems.join("\n"), /an unverifiable archive is not a distribution artifact/);
});

test("(resolver copy) a plain copy at the shipped version is mirrored to the shipped tree", (t) => {
  const home = fixtureHome(t);
  const canonical = makeCopy(join(home, "wired", "council-of-wise-elders"), "1.0.80");
  writeFileSync(join(canonical, "council-of-wise-elders.skill"), "PK\u0003\u0004 the 1.0.80 release archive\n");
  const canonicalManifest = restamp(canonical, { archive: { file: "council-of-wise-elders.skill", sha256: sha(readFileSync(join(canonical, "council-of-wise-elders.skill"))) } });

  const dist = join(home, ".claude", "skills", "council-of-wise-elders");
  cpSync(canonical, dist, { recursive: true });
  writeFileSync(join(dist, "council-of-wise-elders.skill"), "PK\u0003\u0004 the 1.0.79 release archive\n");
  restamp(dist); // a plain copy records itself, never a canonical aggregate

  const before = gate(home, canonical, dist);
  assert.equal(before.ok, false, "a copy carrying another release's archive cannot pass");

  const refresh = refreshSelectedTree({ sourceDir: canonical, selectedDir: dist });
  assert.equal(refresh.status, "refreshed", refresh.problems.join(" | "));
  assert.equal(refresh.mode, "mirror");
  assert.ok(refresh.written.includes("council-of-wise-elders.skill"));
  assert.equal(refresh.archive, canonicalManifest.archive.sha256);
  assert.equal(refresh.extras.length, 0);

  const after = gate(home, canonical, dist);
  assert.equal(after.ok, true, after.problems.join(" | "));
});

test("(resolver copy) a symlink and owner-only files are never rewritten or deleted", (t) => {
  const home = fixtureHome(t);
  const canonical = makeCopy(join(home, "wired", "council-of-wise-elders"), "1.0.80");
  restamp(canonical);
  const real = join(home, "elsewhere", "council-of-wise-elders");
  mkdirSync(real, { recursive: true });
  const linked = join(home, ".agents", "skills", "council-of-wise-elders");
  mkdirSync(dirname(linked), { recursive: true });
  symlinkSync(real, linked);

  const symlinked = refreshSelectedTree({ sourceDir: canonical, selectedDir: linked });
  assert.equal(symlinked.status, "skipped");
  assert.match(symlinked.reason, /symlink/);
  assert.deepEqual(symlinked.written, [], "a refresh never writes through a link it did not create");

  const plain = join(home, ".claude", "skills", "council-of-wise-elders");
  cpSync(canonical, plain, { recursive: true });
  // The copy is one release behind in content, not just in its archive.
  writeFileSync(
    join(plain, "SKILL.md"),
    "---\nname: council-of-wise-elders\nversion: 1.0.80\n---\n\nResolve a real purpose-bound run grant through the installed authorization service.\n",
  );
  restamp(plain);
  writeFileSync(join(plain, "OPERATOR-NOTES.md"), "owner data\n");
  const refresh = refreshSelectedTree({ sourceDir: canonical, selectedDir: plain });
  assert.equal(refresh.status, "refreshed");
  assert.ok(refresh.written.includes("SKILL.md"), "the stale instruction text is replaced by the shipped tree's");
  assert.deepEqual(refresh.extras, ["OPERATOR-NOTES.md"], "a file the copy alone carries is reported, never deleted");
  assert.equal(readFileSync(join(plain, "OPERATOR-NOTES.md"), "utf8"), "owner data\n");
  assert.match(readFileSync(join(plain, "SKILL.md"), "utf8"), /Convening is the approval/);
});

test("(cli) the script prints one refresh line and exits 0 only when it converged", (t) => {
  const { canonical, dist } = staleDistributionFixture(t);
  const run = spawnSync(process.execPath, [join(SCRIPTS, "selected-tree-refresh.mjs"), "--source", canonical, "--selected", dist], { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr);
  assert.match(run.stdout, /SELECTED-TREE-REFRESH: REFRESHED mode=distribution-archive/);
  const again = spawnSync(process.execPath, [join(SCRIPTS, "selected-tree-refresh.mjs"), "--source", canonical, "--selected", dist], { encoding: "utf8" });
  assert.equal(again.status, 0, again.stderr);
  assert.match(again.stdout, /SELECTED-TREE-REFRESH: ALREADY-CURRENT/);
  const usage = spawnSync(process.execPath, [join(SCRIPTS, "selected-tree-refresh.mjs")], { encoding: "utf8" });
  assert.equal(usage.status, 2);
});
