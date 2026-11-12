#!/usr/bin/env python3
"""Full-Read Guard: the committed dist/ must equal a fresh build of src/.

A client box never builds the plugin, so the committed dist/ is what runs.
This test rebuilds src/ into a scratch directory with extensions/full-read-guard/build.sh
(FRG_OUT_DIR) and compares every file byte for byte. It is skipped when no TypeScript
compiler or Node type definitions can be found on the machine running it.

It also checks the plugin folder is complete: manifest shards, plugin manifest, package file.
"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = REPO / "extensions" / "full-read-guard"


class FullReadGuardDist(unittest.TestCase):
    def test_plugin_folder_is_complete(self):
        for rel in ("openclaw.plugin.json", "package.json", "tsconfig.json", "build.sh",
                    "dist/index.js", "dist/gate.js", "dist/read-skill.js", "dist/shell-parse.js",
                    "manifest.d/_defaults.json", "docs/tool-parameters.md"):
            self.assertTrue((PLUGIN / rel).is_file(), rel)
        shards = sorted(p.name for p in (PLUGIN / "manifest.d").glob("*.json"))
        self.assertGreaterEqual(len(shards), 6, shards)
        for name in shards:
            json.loads((PLUGIN / "manifest.d" / name).read_text())

    def test_versions_agree(self):
        manifest = json.loads((PLUGIN / "openclaw.plugin.json").read_text())
        package = json.loads((PLUGIN / "package.json").read_text())
        self.assertEqual(manifest["version"], package["version"])
        self.assertEqual(manifest["contracts"]["tools"], ["read_skill"])
        self.assertNotIn("hooks", manifest)

    def test_dist_matches_fresh_build(self):
        if not shutil.which("tsc") and not os.environ.get("TSC"):
            self.skipTest("tsc not found")
        out = pathlib.Path(tempfile.mkdtemp(prefix="frg-dist-", dir=os.environ.get("TMPDIR") or None))
        try:
            env = dict(os.environ, FRG_OUT_DIR=str(out / "dist"))
            proc = subprocess.run(["bash", str(PLUGIN / "build.sh")], cwd=PLUGIN, env=env,
                                  capture_output=True, text=True)
            if proc.returncode == 2:
                self.skipTest("build prerequisites missing: " + proc.stderr.strip())
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            built = sorted(p.name for p in (out / "dist").glob("*.js"))
            committed = sorted(p.name for p in (PLUGIN / "dist").glob("*.js"))
            self.assertEqual(built, committed)
            for name in built:
                self.assertEqual((out / "dist" / name).read_text(), (PLUGIN / "dist" / name).read_text(),
                                 f"dist/{name} is stale: run extensions/full-read-guard/build.sh and commit")
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
