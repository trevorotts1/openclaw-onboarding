"""Tests for the MG-041 safe installation upgrade (scripts/migrate_install.py).

Every test runs against a scratch COPY of the populated fixture
installation in tests/fixtures/install/ (an installed Skill 72 at
version 1.0.0 with client-owned files inside the skill tree, a shared
runtime with a live version pointer, and a storage root holding one V1
job and one V2 job). The fixture itself is never mutated.

Acceptance coverage (directive MG-041):
  1. upgrade a populated fixture installation twice; client files remain
     unchanged (test_upgrade_twice_client_files_unchanged)
  2. legacy job replay and V2 job creation work after upgrade (same test)
  3. failed upgrade rolls back the runtime pointer without deleting job
     data (test_promote_failure_rolls_back_tree_and_pointer, plus the
     readiness variant test_runtime_readiness_failure_promotes_nothing)
  4. upgrade during an active render is refused with a named finding and
     the render completes undisturbed (test_active_render_refuses)
Plus: discovery inventory, removed-command compatibility wrappers, and
the manual rollback command.

Run from the worktree root:
    python3 -m unittest discover -s 72-motion-video-plus/tests/unit
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
TOOL = SKILL_ROOT / "scripts" / "migrate_install.py"
FIXTURES = SKILL_ROOT / "tests" / "fixtures" / "install"
EVIDENCE = SKILL_ROOT / "tests" / "evidence" / "mg041" / "record.json"
SCRATCH_BASE = Path.home() / ".cache" / "skill72-mg041-tests"

PROTECTED_PREFIXES = ("client-data/", "brand/", "style-cards/", "jobs/", "renders/", "history/")
RECORD: dict = {"item": "MG-041", "cases": {}}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tearDownModule():
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(RECORD, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.rmtree(SCRATCH_BASE, ignore_errors=True)


class MigrationInstallTests(unittest.TestCase):
    def setUp(self):
        self.work = SCRATCH_BASE / self.id().split(".")[-1]
        shutil.rmtree(self.work, ignore_errors=True)
        self.install = self.work / "installation"
        shutil.copytree(FIXTURES / "populated", self.install, symlinks=True)
        self.release = self.work / "release"
        shutil.copytree(FIXTURES / "release", self.release, symlinks=True)
        self.skills_root = self.install / "skills"
        self.skill_dir = self.skills_root / "72-motion-video-plus"
        self.storage = self.install / "storage" / "motion-videos"
        self.runtime_state = self.skills_root / "shared-utils" / "motion-render-runtime" / ".runtime"
        self.addCleanup(lambda: shutil.rmtree(self.work, ignore_errors=True))

    # -- helpers -----------------------------------------------------------

    def run_tool(self, *argv: str) -> tuple[int, dict]:
        proc = subprocess.run(
            [sys.executable, str(TOOL), *argv],
            capture_output=True, text=True,
        )
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            self.fail(f"tool did not emit JSON (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
        return proc.returncode, payload

    def base_args(self) -> list[str]:
        return ["--skills-root", str(self.skills_root), "--storage-root", str(self.storage)]

    def upgrade_args(self, source: Path, runtime: str | None = "lock-cccc3333") -> list[str]:
        args = ["upgrade", *self.base_args(), "--source", str(source)]
        if runtime:
            args += ["--runtime-version-dir", str(self.release / "runtime-versions" / runtime)]
        return args

    def client_hashes(self) -> dict[str, str]:
        """Hashes of everything the upgrade must never change: all storage
        files, plus protected and unknown files inside the skill tree."""
        out: dict[str, str] = {}
        for p in sorted(self.storage.rglob("*")):
            if p.is_file():
                out[f"storage/{p.relative_to(self.storage).as_posix()}"] = _sha256(p)
        for p in sorted(self.skill_dir.rglob("*")):
            if p.is_file():
                rel = p.relative_to(self.skill_dir).as_posix()
                if rel.startswith(PROTECTED_PREFIXES) or rel == "operator-notes.txt":
                    out[f"skill/{rel}"] = _sha256(p)
        return out

    def pointer(self) -> str:
        return os.readlink(self.runtime_state / "current")

    def installed_version(self) -> str:
        return (self.skill_dir / "skill-version.txt").read_text(encoding="utf-8").strip()

    def last_journal(self) -> dict:
        txns = self.skills_root / ".skill72-upgrade" / "transactions"
        latest = sorted(txns.iterdir())[-1]
        return json.loads((latest / "journal.json").read_text(encoding="utf-8"))

    def assert_client_subset_unchanged(self, before: dict[str, str]):
        after = self.client_hashes()
        for key, digest in before.items():
            self.assertEqual(digest, after.get(key), f"client file changed: {key}")

    # -- cases -------------------------------------------------------------

    def test_discover_reports_the_installation(self):
        rc, payload = self.run_tool("discover", *self.base_args())
        self.assertEqual(0, rc, payload)
        self.assertEqual("1.0.0", payload["skill"]["file_version"])
        self.assertEqual("motion-video-plus", payload["skill"]["name"])
        self.assertEqual("versions/lock-aaaa1111", payload["runtime"]["pointer_target"])
        self.assertEqual("pass", payload["runtime"]["versions"]["lock-aaaa1111"]["lock_result"])
        jobs = {j["job"]: j["kind"] for j in payload["jobs"]}
        self.assertEqual({"job-legacy-01": "v1", "job-v2-01": "v2"}, jobs)
        self.assertIn("brand/acme-brand-bible.md", payload["protected_client_files_in_skill_tree"])
        RECORD["cases"]["discover"] = {"pointer": payload["runtime"]["pointer_target"], "jobs": jobs}

    def test_upgrade_twice_client_files_unchanged(self):
        source = self.release / "72-motion-video-plus"
        before = self.client_hashes()
        v1_manifest = self.storage / "job-legacy-01" / "manifest.json"
        v1_before = _sha256(v1_manifest)

        args = self.upgrade_args(source) + ["--migrate-jobs", "--mode", "standalone_video",
                                            "--company-id", "fixture-co"]
        rc, receipt = self.run_tool(*args)
        self.assertEqual(0, rc, receipt)
        self.assertEqual("upgraded", receipt["status"])
        self.assertEqual(("1.0.0", "1.1.0"), (receipt["from_version"], receipt["to_version"]))
        self.assertEqual("versions/lock-cccc3333", self.pointer())
        self.assertEqual("1.1.0", self.installed_version())
        self.assertIn("upgraded tree", (self.skill_dir / "INSTRUCTIONS.md").read_text(encoding="utf-8"))
        self.assert_client_subset_unchanged(before)
        self.assertEqual(v1_before, _sha256(v1_manifest), "the V1 manifest must never be modified")

        # Manifest migration produced a NEW revision beside the V1 job,
        # and its manifest passes the full contracts manifest definition.
        scaffold = self.storage / "job-legacy-01.v2"
        self.assertTrue((scaffold / "manifest.json").is_file())
        sys.path.insert(0, str(self.skill_dir / "scripts"))
        import motion_contracts
        migrated = json.loads((scaffold / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([], [str(e.message) for e in motion_contracts._raw_errors(migrated, "manifest")])

        # Legacy replay: the INSTALLED tree's migrator migrates a fresh
        # copy of the V1 manifest and leaves the source byte-identical.
        replay_src = self.work / "replay-manifest.json"
        shutil.copy2(v1_manifest, replay_src)
        replay_out = self.work / "replay-out"
        proc = subprocess.run(
            [sys.executable, str(self.skill_dir / "scripts" / "migrate_manifest.py"),
             str(replay_src), "--mode", "standalone_video", "--company-id", "fixture-co",
             "--out-dir", str(replay_out)],
            capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual(v1_before, _sha256(replay_src))

        # V2 job creation: a new V2 package validates clean with the
        # installed tree's own contract validator.
        new_job = self.storage / "job-v2-02"
        shutil.copytree(self.storage / "job-v2-01", new_job)
        proc = subprocess.run(
            [sys.executable, str(self.skill_dir / "scripts" / "motion_contracts.py"),
             "validate", str(new_job)],
            capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["valid"])

        # Second upgrade: idempotent re-sync, still no client drift. The
        # storage snapshot now legitimately includes job-v2-02 and the
        # migrated scaffold, so compare the new full set across run two.
        before2 = self.client_hashes()
        rc, receipt2 = self.run_tool(*args)
        self.assertEqual(0, rc, receipt2)
        self.assertEqual("upgraded", receipt2["status"])
        self.assertTrue(
            any(f.startswith("MG_INSTALL_ALREADY_CURRENT") for f in receipt2["findings"]),
            receipt2["findings"])
        self.assertEqual("versions/lock-cccc3333", self.pointer())
        self.assert_client_subset_unchanged(before2)
        self.assertEqual(v1_before, _sha256(v1_manifest))

        RECORD["cases"]["upgrade_twice"] = {
            "brand_bible_sha256": before["skill/brand/acme-brand-bible.md"],
            "client_files_tracked": len(before),
            "pointer_after": self.pointer(),
            "v1_manifest_sha256": v1_before,
            "migrated_scaffold": "job-legacy-01.v2",
        }

    def test_runtime_readiness_failure_promotes_nothing(self):
        before = self.client_hashes()
        rc, payload = self.run_tool(*self.upgrade_args(self.release / "72-motion-video-plus",
                                                       runtime="lock-dddd4444"))
        self.assertEqual(4, rc, payload)
        self.assertEqual("MG_INSTALL_READINESS_FAILED", payload["finding"])
        self.assertEqual("1.0.0", self.installed_version())
        self.assertEqual("versions/lock-aaaa1111", self.pointer())
        self.assertEqual("readiness_failed", self.last_journal()["state"])
        self.assert_client_subset_unchanged(before)
        RECORD["cases"]["readiness_failure"] = {"exit": rc, "pointer": self.pointer()}

    def test_promote_failure_rolls_back_tree_and_pointer(self):
        source = self.release / "72-motion-video-plus"
        before = self.client_hashes()
        aaaa_lock_sha = _sha256(self.runtime_state / "versions" / "lock-aaaa1111" / "runtime-lock.json")

        rc, prepared = self.run_tool("prepare", *self.base_args(), "--source", str(source),
                                     "--runtime-version-dir",
                                     str(self.release / "runtime-versions" / "lock-cccc3333"))
        self.assertEqual(0, rc, prepared)
        txn_dir = self.skills_root / ".skill72-upgrade" / "transactions" / prepared["txn_id"]

        # Corrupt one vaulted client file between prepare and promote:
        # the restore hash check must catch it and roll EVERYTHING back,
        # including the runtime pointer flip that already happened.
        vault_file = txn_dir / "vault" / "brand" / "acme-brand-bible.md"
        vault_file.write_bytes(vault_file.read_bytes() + b"tampered\n")

        rc, receipt = self.run_tool("promote", *self.base_args())
        self.assertEqual(5, rc, receipt)
        self.assertEqual("rolled_back", receipt["status"])
        self.assertEqual("1.0.0", self.installed_version())
        self.assertIn("legacy installed tree",
                      (self.skill_dir / "INSTRUCTIONS.md").read_text(encoding="utf-8"))
        self.assertEqual("versions/lock-aaaa1111", self.pointer())
        self.assertEqual(aaaa_lock_sha, _sha256(self.runtime_state / "runtime-lock.json"))
        self.assertTrue((txn_dir / "failed-skill").is_dir(), "the failed tree is retained for forensics")
        self.assert_client_subset_unchanged(before)
        RECORD["cases"]["promote_rollback"] = {
            "exit": rc, "pointer_after_rollback": self.pointer(),
            "skill_version_after_rollback": self.installed_version(),
        }

    def test_active_render_refuses_and_render_completes(self):
        before = self.client_hashes()
        marker = self.work / "render-done.txt"
        proc = subprocess.Popen(["sh", "-c", f"sleep 3; printf done > {marker}"])
        try:
            record = {"renders": [{"job_id": "job-legacy-01", "pid": proc.pid,
                                   "started_at": "fixture"}]}
            (self.runtime_state / "active-renders.json").write_text(
                json.dumps(record), encoding="utf-8")
            rc, payload = self.run_tool(*self.upgrade_args(self.release / "72-motion-video-plus"))
            self.assertEqual(3, rc, payload)
            self.assertEqual("MG_INSTALL_RENDER_ACTIVE", payload["finding"])
            self.assertEqual("1.0.0", self.installed_version(), "a refused upgrade changes nothing")
            self.assertIsNone(proc.poll(), "the render process must be undisturbed")
            deadline = time.time() + 15
            while time.time() < deadline and not marker.exists():
                time.sleep(0.2)
            self.assertTrue(marker.exists(), "the active render must complete undisturbed")
            self.assertEqual("done", marker.read_text(encoding="utf-8"))
        finally:
            proc.wait(timeout=20)
        self.assert_client_subset_unchanged(before)

        # A stale record (dead pid) does not block: it is reported as stale.
        (self.runtime_state / "active-renders.json").write_text(
            json.dumps({"renders": [{"job_id": "old", "pid": 999999, "started_at": "fixture"}]}),
            encoding="utf-8")
        rc, payload = self.run_tool("discover", *self.base_args())
        self.assertEqual(0, rc, payload)
        self.assertEqual([], payload["active_renders"]["live"])
        self.assertEqual(1, len(payload["active_renders"]["stale"]))
        RECORD["cases"]["active_render"] = {"refusal_exit": 3, "render_completed": True}

    def test_removed_command_gets_named_wrapper(self):
        source = self.work / "release-no-qc" / "72-motion-video-plus"
        shutil.copytree(self.release / "72-motion-video-plus", source, symlinks=True)
        (source / "scripts" / "qc.sh").unlink()
        rc, receipt = self.run_tool(*self.upgrade_args(source, runtime=None))
        self.assertEqual(0, rc, receipt)
        self.assertIn("scripts/qc.sh", receipt["wrappers_installed"])
        wrapper = self.skill_dir / "scripts" / "qc.sh"
        self.assertTrue(wrapper.is_file())
        body = wrapper.read_text(encoding="utf-8")
        self.assertIn("MG_INSTALL_COMMAND_REMOVED", body)
        self.assertIn("INSTRUCTIONS.md stage 14", body, "the wrapper must name the replacement")
        proc = subprocess.run(["bash", str(wrapper)], capture_output=True, text=True)
        self.assertEqual(3, proc.returncode)
        self.assertIn("MG_INSTALL_COMMAND_REMOVED", proc.stderr)
        # A command the release still ships stays the real file, no wrapper.
        render_js = (self.skill_dir / "scripts" / "render.js").read_text(encoding="utf-8")
        self.assertNotIn("MG_INSTALL_COMMAND_REMOVED", render_js)
        RECORD["cases"]["wrapper"] = {"wrapped": receipt["wrappers_installed"], "wrapper_exit": 3}

    def test_manual_rollback_after_promote(self):
        before = self.client_hashes()
        rc, receipt = self.run_tool(*self.upgrade_args(self.release / "72-motion-video-plus"))
        self.assertEqual(0, rc, receipt)
        self.assertEqual("1.1.0", self.installed_version())
        self.assertEqual("versions/lock-cccc3333", self.pointer())

        rc, receipt = self.run_tool("rollback", *self.base_args())
        self.assertEqual(0, rc, receipt)
        self.assertEqual("rolled_back", receipt["status"])
        self.assertEqual("1.0.0", self.installed_version())
        self.assertEqual("versions/lock-aaaa1111", self.pointer())
        self.assert_client_subset_unchanged(before)

        rc, receipt = self.run_tool("rollback", *self.base_args())
        self.assertEqual(0, rc, receipt)
        self.assertEqual("rolled_back", receipt["status"], "rollback is idempotent")
        RECORD["cases"]["manual_rollback"] = {
            "pointer_after_rollback": self.pointer(),
            "skill_version_after_rollback": self.installed_version(),
        }


if __name__ == "__main__":
    unittest.main()
