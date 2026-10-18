import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const source = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  assert.ifError(result.error);
  return result;
}

test("generated and extracted packages verify, while source and archive tampering fail", () => {
  const scratch = mkdtempSync(join(tmpdir(), "council-bundle-contract-"));
  try {
    const root = join(scratch, "source");
    cpSync(source, root, {
      recursive: true,
      filter: (path) => {
        const rel = relative(source, path).split("\\").join("/");
        return rel !== "manifest.json" && !rel.endsWith(".skill")
          && !/^runtime\/(dist|node_modules)(\/|$)/.test(rel);
      },
    });
    const built = run(process.execPath, [join(root, "scripts/build-bundles.mjs")]);
    assert.equal(built.status, 0, built.stdout + built.stderr);
    const verify = (dir) => run(process.execPath, [join(dir, "scripts/verify-bundles.mjs")]);
    const pristine = verify(root);
    assert.equal(pristine.status, 0, pristine.stdout + pristine.stderr);
    const archivePath = join(root, "council-of-wise-elders.skill");
    const archive = readFileSync(archivePath);
    const outerPath = join(root, "manifest.json");
    const outer = JSON.parse(readFileSync(outerPath, "utf8"));
    assert.equal(outer.archive.status, "generated");
    assert.equal(outer.archive.sha256, createHash("sha256").update(archive).digest("hex"));

    const unpack = join(scratch, "extracted");
    const extracted = run("python3", ["-m", "zipfile", "-e", archivePath, unpack]);
    assert.equal(extracted.status, 0, extracted.stdout + extracted.stderr);
    const packageRoot = join(unpack, "council-of-wise-elders");
    const inner = JSON.parse(readFileSync(join(packageRoot, "manifest.json"), "utf8"));
    assert.equal(inner.archive.status, "extracted_distribution");
    assert.equal(existsSync(join(packageRoot, "council-of-wise-elders.skill")), false);
    const extractedCheck = verify(packageRoot);
    assert.equal(extractedCheck.status, 0, extractedCheck.stdout + extractedCheck.stderr);

    for (const dir of [root, packageRoot]) {
      const doc = join(dir, "runtime/README.md");
      writeFileSync(doc, readFileSync(doc, "utf8") + "\nSynthetic content tamper.\n");
      const result = verify(dir);
      assert.equal(result.status, 1, result.stdout + result.stderr);
      assert.match(result.stdout, /hash drift: runtime\/README.md/);
    }
    // Restore the source content so the following failures prove the archive gate.
    cpSync(join(source, "runtime/README.md"), join(root, "runtime/README.md"));
    writeFileSync(archivePath, Buffer.concat([archive, Buffer.from("tamper")]));
    const badArchive = verify(root);
    assert.equal(badArchive.status, 1, badArchive.stdout + badArchive.stderr);
    assert.match(badArchive.stdout, /archive SHA-256 is missing or does not match/);
    writeFileSync(archivePath, archive);
    delete outer.archive.sha256;
    writeFileSync(outerPath, JSON.stringify(outer));
    const missingHash = verify(root);
    assert.equal(missingHash.status, 1, missingHash.stdout + missingHash.stderr);
    assert.match(missingHash.stdout, /archive SHA-256 is missing or does not match/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
