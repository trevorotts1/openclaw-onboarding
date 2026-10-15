"""Tests for shared-utils/motion-render-runtime/rollback.sh (MG-041).

The provisioner (MG-003) promotes a runtime only after its probe passes
and never deletes a version directory; rollback.sh is the pointer flip
back. These tests run it against a scratch fixture runtime via the
MOTION_RUNTIME_HOME override, so the live runtime is never touched.

Run from the worktree root:
    python3 -m unittest discover -s 72-motion-video-plus/tests/unit
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ROLLBACK = REPO_ROOT / "shared-utils" / "motion-render-runtime" / "rollback.sh"
SCRATCH_BASE = Path.home() / ".cache" / "skill72-mg041-rollback-tests"


def _lock(result: str) -> str:
    return json.dumps(
        {"result": result,
         "engines": {"remotion": {"status": result}, "hyperframes": {"status": result}},
         "packages": {"remotion": "4.0.535", "hyperframes": "0.8.155"}},
        indent=2) + "\n"


class RuntimeRollbackTests(unittest.TestCase):
    def setUp(self):
        self.work = SCRATCH_BASE / self.id().split(".")[-1]
        shutil.rmtree(self.work, ignore_errors=True)
        self.home = self.work / "runtime-home"
        self.state = self.home / ".runtime"
        versions = self.state / "versions"
        for name, result, age in (("lock-aaaa1111", "pass", 300),
                                  ("lock-bbbb2222", "pass", 100),
                                  ("lock-ffff6666", "fail", 50)):
            vdir = versions / name
            vdir.mkdir(parents=True)
            (vdir / "runtime-lock.json").write_text(_lock(result), encoding="utf-8")
            stamp = time.time() - age
            os.utime(vdir, (stamp, stamp))
        (self.state / "runtime-lock.json").write_text(_lock("pass"), encoding="utf-8")
        (self.state / "current").symlink_to("versions/lock-aaaa1111")
        self.addCleanup(lambda: shutil.rmtree(self.work, ignore_errors=True))

    def run_rollback(self, *argv: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, MOTION_RUNTIME_HOME=str(self.home))
        return subprocess.run(["bash", str(ROLLBACK), *argv],
                              capture_output=True, text=True, env=env)

    def pointer(self) -> str:
        return os.readlink(self.state / "current")

    def test_rollback_flips_to_newest_other_verified_version(self):
        proc = self.run_rollback()
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        # lock-ffff6666 is newer than bbbb but its probe failed: skipped.
        self.assertEqual("versions/lock-bbbb2222", self.pointer())
        active = json.loads((self.state / "runtime-lock.json").read_text(encoding="utf-8"))
        self.assertEqual("pass", active["result"])

    def test_rollback_to_named_version(self):
        proc = self.run_rollback("lock-bbbb2222")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual("versions/lock-bbbb2222", self.pointer())
        proc = self.run_rollback("lock-aaaa1111")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual("versions/lock-aaaa1111", self.pointer())

    def test_rollback_refuses_unverified_target(self):
        proc = self.run_rollback("lock-ffff6666")
        self.assertEqual(1, proc.returncode)
        self.assertIn("FAIL", proc.stderr)
        self.assertEqual("versions/lock-aaaa1111", self.pointer(), "a refused rollback moves nothing")

    def test_rollback_refuses_while_render_active(self):
        proc_sleep = subprocess.Popen(["sleep", "30"])
        try:
            (self.state / "active-renders.json").write_text(
                json.dumps({"renders": [{"job_id": "job-1", "pid": proc_sleep.pid,
                                         "started_at": "fixture"}]}),
                encoding="utf-8")
            proc = self.run_rollback()
            self.assertEqual(1, proc.returncode)
            self.assertIn("active", proc.stderr)
            self.assertEqual("versions/lock-aaaa1111", self.pointer())
            self.assertIsNone(proc_sleep.poll(), "the render process is never touched")
        finally:
            proc_sleep.terminate()
            proc_sleep.wait(timeout=10)

    def test_rollback_never_deletes_versions(self):
        self.run_rollback()
        names = sorted(p.name for p in (self.state / "versions").iterdir())
        self.assertEqual(["lock-aaaa1111", "lock-bbbb2222", "lock-ffff6666"], names)


if __name__ == "__main__":
    unittest.main()
