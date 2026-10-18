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
    const verify = (dir, distribution = false, tool = "verify-bundles.mjs") =>
      run(process.execPath, [join(dir, "scripts", tool), ...(distribution ? ["--distribution"] : [])]);
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
    const extractedCheck = verify(packageRoot, true);
    assert.equal(extractedCheck.status, 0, extractedCheck.stdout + extractedCheck.stderr);

    for (const dir of [root, packageRoot]) {
      const doc = join(dir, "runtime/README.md");
      writeFileSync(doc, readFileSync(doc, "utf8") + "\nSynthetic content tamper.\n");
      const result = verify(dir, dir === packageRoot);
      assert.equal(result.status, 1, result.stdout + result.stderr);
      assert.match(result.stdout, /hash drift: runtime\/README.md/);
      const doctor = verify(dir, dir === packageRoot, "doctor.mjs");
      assert.equal(doctor.status, 1, doctor.stdout + doctor.stderr);
      assert.match(doctor.stdout, /manifest drift:/);
    }
    // Default source checks never infer an exemption from the inner manifest.
    for (const tool of ["verify-bundles.mjs", "doctor.mjs"]) {
      const rejected = verify(packageRoot, false, tool);
      assert.equal(rejected.status, 1, rejected.stdout + rejected.stderr);
      assert.match(rejected.stdout, /source verification requires archive status generated/);
    }
    cpSync(join(source, "runtime/README.md"), join(packageRoot, "runtime/README.md"));
    for (const tool of ["verify-bundles.mjs", "doctor.mjs"]) {
      const accepted = verify(packageRoot, true, tool);
      assert.equal(accepted.status, 0, accepted.stdout + accepted.stderr);
      writeFileSync(join(packageRoot, "council-of-wise-elders.skill"), archive);
      const nested = verify(packageRoot, true, tool);
      assert.equal(nested.status, 1, nested.stdout + nested.stderr);
      assert.match(nested.stdout, /unexpectedly contains a nested archive/);
      rmSync(join(packageRoot, "council-of-wise-elders.skill"));
    }
    // Restore source content so each following failure proves the archive gate.
    cpSync(join(source, "runtime/README.md"), join(root, "runtime/README.md"));
    for (const tool of ["verify-bundles.mjs", "doctor.mjs"]) {
      const savedOuter = JSON.stringify(outer);
      for (const status of ["extracted_distribution", "deferred_to_final_integration", "unknown", undefined]) {
        outer.archive.status = status;
        writeFileSync(outerPath, JSON.stringify(outer));
        rmSync(archivePath);
        const switched = verify(root, false, tool);
        assert.equal(switched.status, 1, switched.stdout + switched.stderr);
        assert.match(switched.stdout, /source verification requires archive status generated/);
        assert.match(switched.stdout, /source verification requires the distributable archive/);
        writeFileSync(archivePath, archive);
      }
      Object.assign(outer.archive, JSON.parse(savedOuter).archive);
      writeFileSync(outerPath, savedOuter);
      rmSync(archivePath);
      const missingArchive = verify(root, false, tool);
      assert.equal(missingArchive.status, 1, missingArchive.stdout + missingArchive.stderr);
      assert.match(missingArchive.stdout, /source verification requires the distributable archive/);
      writeFileSync(archivePath, Buffer.concat([archive, Buffer.from("tamper")]));
      const badArchive = verify(root, false, tool);
      assert.equal(badArchive.status, 1, badArchive.stdout + badArchive.stderr);
      assert.match(badArchive.stdout, /archive SHA-256 is missing or does not match/);
      writeFileSync(archivePath, archive);
      delete outer.archive.sha256;
      writeFileSync(outerPath, JSON.stringify(outer));
      const missingHash = verify(root, false, tool);
      assert.equal(missingHash.status, 1, missingHash.stdout + missingHash.stderr);
      assert.match(missingHash.stdout, /archive SHA-256 is missing or does not match/);
      Object.assign(outer.archive, JSON.parse(savedOuter).archive);
      writeFileSync(outerPath, savedOuter);
      const restored = verify(root, false, tool);
      assert.equal(restored.status, 0, restored.stdout + restored.stderr);
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
