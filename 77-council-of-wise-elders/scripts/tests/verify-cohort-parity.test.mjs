// WER-025 dependency-ready slice: cohort-parity detector tests.
//
// Proves the three real failure modes this project has hit:
//   1. three-split version drift (skill-version.txt + SKILL.md bumped, sibling
//      `version` left behind),
//   2. a stale manifest aggregate (content and markers moved, manifest.json
//      never rebuilt),
//   3. skill content changed with no version bump (the G3 condition).
//
// Every fixture is a temp copy; the real skill tree is never modified. The
// verifier is asserted to be read-only (tree hashes and mtimes unchanged
// across a run) and to import no network or write API.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const source = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const verifier = join(source, "scripts", "verify-cohort-parity.mjs");

// Derived from the live tree rather than hardcoded: this suite failed the
// moment the cohort actually bumped its own version, which is exactly when it
// must keep working.
const currentVersion = readFileSync(join(source, "skill-version.txt"), "utf8").trim().replace(/^v/, "");
const esc = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const bump = (version) => {
  const parts = version.split(".");
  parts[parts.length - 1] = String(Number(parts[parts.length - 1]) + 1);
  return parts.join(".");
};
const nextVersion = bump(currentVersion);

function run(root, extra = []) {
  const result = spawnSync(process.execPath, [verifier, "--root", root, ...extra], {
    encoding: "utf8",
  });
  assert.ifError(result.error);
  return result;
}

function fixture() {
  const scratch = mkdtempSync(join(tmpdir(), "council-cohort-parity-"));
  const root = join(scratch, "skill");
  cpSync(source, root, {
    recursive: true,
    filter: (path) => {
      const rel = relative(source, path).split("\\").join("/");
      return rel !== ".git" && !/^runtime\/(dist|node_modules)(\/|$)/.test(rel);
    },
  });
  return { scratch, root };
}

function snapshot(dir, base = dir, out = new Map()) {
  for (const name of readdirSync(dir).sort()) {
    const path = join(dir, name);
    const rel = relative(base, path).split("\\").join("/");
    if (/^runtime\/(dist|node_modules)(\/|$)/.test(rel)) continue;
    const stat = statSync(path);
    if (stat.isDirectory()) snapshot(path, base, out);
    else out.set(rel, `${stat.size}:${stat.mtimeMs}:${createHash("sha256").update(readFileSync(path)).digest("hex")}`);
  }
  return out;
}

function append(path, text) {
  writeFileSync(path, readFileSync(path, "utf8") + text);
}

test("the real tree is coherent, and the verifier is idempotent and writes nothing", () => {
  const before = snapshot(source);
  const first = run(source);
  const second = run(source);
  const after = snapshot(source);

  assert.equal(first.status, 0, first.stdout + first.stderr);
  assert.equal(second.status, 0, second.stdout + second.stderr);
  assert.equal(first.stdout, second.stdout);
  assert.deepEqual(after, before);
  assert.match(first.stdout, new RegExp(`PASS version markers agree: ${esc(currentVersion)}`));
  assert.match(first.stdout, /PASS manifest tree hash matches \(\d+ files\)/);
  assert.match(first.stdout, new RegExp(`PASS CHANGELOG\\.md top entry matches: ${esc(currentVersion)}`));
  assert.match(first.stdout, /COHORT PARITY: PASS/);
});

test("the verifier imports no write or network API", () => {
  const text = readFileSync(verifier, "utf8");
  for (const banned of [
    "node:child_process", "node:http", "node:https", "node:net", "node:dns",
    "node:fs/promises", "writeFile", "appendFile", "createWriteStream",
    "mkdir", "unlink", "rmSync", "rename", "cpSync", "fetch(",
  ]) {
    assert.equal(text.includes(banned), false, `verifier must not reference ${banned}`);
  }
});

test("a pristine fixture passes through --root", () => {
  const { scratch, root } = fixture();
  try {
    const result = run(root);
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /COHORT PARITY: PASS/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("three-split version drift is detected and names the sibling version file", () => {
  const { scratch, root } = fixture();
  try {
    writeFileSync(join(root, "version"), `${nextVersion}\n`);
    const result = run(root);
    assert.equal(result.status, 1, result.stdout + result.stderr);
    assert.match(result.stdout, /FAIL version marker drift/);
    assert.match(result.stdout, new RegExp(`version="${esc(nextVersion)}"`));
    assert.match(result.stdout, new RegExp(`expected "${esc(currentVersion)}"`));
    assert.match(result.stdout, /COHORT PARITY: FAIL/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("a stale manifest aggregate after a version bump is detected", () => {
  const { scratch, root } = fixture();
  try {
    writeFileSync(join(root, "skill-version.txt"), `v${nextVersion}\n`);
    writeFileSync(join(root, "version"), `${nextVersion}\n`);
    const skillMdPath = join(root, "SKILL.md");
    writeFileSync(skillMdPath, readFileSync(skillMdPath, "utf8")
      .replace(new RegExp(`^version: ${esc(currentVersion)}$`, "m"), `version: ${nextVersion}`));
    append(join(root, "references", "protocol.md"), "\nSynthetic cohort change.\n");

    const result = run(root);
    assert.equal(result.status, 1, result.stdout + result.stderr);
    assert.match(result.stdout, new RegExp(`FAIL manifest\\.json skill_version = "${esc(currentVersion)}", expected "${esc(nextVersion)}"`));
    assert.match(result.stdout, /FAIL manifest drift: computed aggregate [0-9a-f]{64}/);
    assert.match(result.stdout, /references\/protocol\.md/);
    assert.match(result.stdout, /Rebuild with scripts\/build-bundles\.mjs/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("skill content changed without moving skill-version.txt is detected as G3", () => {
  const { scratch, root } = fixture();
  try {
    append(join(root, "references", "protocol.md"), "\nSynthetic content change, no bump.\n");
    const result = run(root);
    assert.equal(result.status, 1, result.stdout + result.stderr);
    assert.match(result.stdout, /FAIL skill content changed without moving skill-version\.txt/);
    assert.match(result.stdout, /references\/protocol\.md/);
    assert.match(result.stdout, new RegExp(`skill-version\\.txt is still "${esc(currentVersion)}"`));
    assert.match(result.stdout, /computed aggregate [0-9a-f]{64} over \d+ files/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("an arbitrary added file is detected, so the detector exemption stays exact", () => {
  const { scratch, root } = fixture();
  try {
    writeFileSync(join(root, "references", "intruder.md"), "not in the manifest\n");
    const result = run(root);
    assert.equal(result.status, 1, result.stdout + result.stderr);
    assert.match(result.stdout, /FAIL skill content changed without moving skill-version\.txt/);
    assert.match(result.stdout, /references\/intruder\.md/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("--strict-changelog makes the pending changelog entry fatal", () => {
  const { scratch, root } = fixture();
  try {
    // A pending changelog cannot be produced by simply editing the fixture:
    // aging the top entry also changes the tree, which would trip manifest
    // drift first and mask the thing under test. So age the changelog, then
    // rebuild the manifest exactly as the real workflow does. The fixture has
    // no .git, which build-bundles.mjs tolerates (source commit stays null).
    const changelogPath = join(root, "CHANGELOG.md");
    const aged = readFileSync(changelogPath, "utf8")
      .replace(/^## v[\d.]+/m, "## v0.0.0-stale");
    assert.notEqual(aged, readFileSync(changelogPath, "utf8"));
    writeFileSync(changelogPath, aged);
    const rebuild = spawnSync(process.execPath, [join(root, "scripts", "build-bundles.mjs")], {
      cwd: root, encoding: "utf8",
    });
    assert.ifError(rebuild.error);
    assert.equal(rebuild.status, 0, rebuild.stdout + rebuild.stderr);

    const lenient = run(root);
    assert.equal(lenient.status, 0, lenient.stdout + lenient.stderr);
    assert.match(lenient.stdout, /WARN CHANGELOG\.md top entry = "0\.0\.0"/);
    assert.match(lenient.stdout, /COHORT PARITY: PASS/);

    const strict = run(root, ["--strict-changelog"]);
    assert.equal(strict.status, 1, strict.stdout + strict.stderr);
    assert.match(strict.stdout, new RegExp(`FAIL CHANGELOG\\.md top entry = "0\\.0\\.0", expected "${esc(currentVersion)}"`));
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("fixture tampering never reaches the real tree", () => {
  const before = snapshot(source);
  const { scratch, root } = fixture();
  try {
    writeFileSync(join(root, "version"), "0.0.1\n");
    assert.equal(run(root).status, 1);
    assert.equal(run(source).status, 0);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
  assert.deepEqual(snapshot(source), before);
});
