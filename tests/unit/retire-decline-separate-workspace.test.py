#!/usr/bin/env python3
"""Class D: retire-confirmed-decline.sh on a 2026.9.x box with a separate
workspace departments folder and a build state that has no companySlug.

Three gaps, one fixture:
  * the dept agent lives in agents.entries (keyed by id) -- step 1 read only
    agents.list, so the declined dept stayed registered;
  * <oc-root>/workspace/departments/<slug> is a SEPARATE folder (the tree the
    phase-3b vertical-derivation gate reads) -- only the company-tree copy was
    archived, so the gate kept counting the declined department;
  * the build state carries no companySlug/clientSlug -- the company dir was
    never resolved and the identity check refused the whole retirement.
Fails on main (rc 2, nothing archived); passes on the fix. Hermetic: HOME is a
temp dir holding the whole "live" layout (no /data/.openclaw on a dev Mac or CI
runner), --skip-cc.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RETIRE = REPO / "23-ai-workforce-blueprint" / "scripts" / "retire-confirmed-decline.sh"


class RetireSeparateWorkspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.company = self.home / "Downloads" / "openclaw-master-files" / "zero-human-company" / "acme-001"
        (self.company / "departments" / "sales").mkdir(parents=True)
        (self.company / "departments" / "marketing").mkdir(parents=True)
        (self.company / "company-config.json").write_text(json.dumps({"slug": "acme-001"}))
        # The box's LIVE layout (under the sandbox HOME): build state, config and
        # the workspace departments tree the vertical-derivation gate reads.
        self.ws = self.home / ".openclaw" / "workspace"
        self.ws_depts = self.ws / "departments"
        (self.ws_depts / "sales").mkdir(parents=True)       # separate real folder
        (self.ws_depts / "sales" / "SOUL.md").write_text("sales\n")
        self.state = self.ws / ".workforce-build-state.json"   # no companySlug
        self.state.write_text(json.dumps({"canonicalReconciliation": {"decisions": {"sales": {
            "decision": "no", "source": "owner-interview",
            "decidedAt": "2026-08-04T12:40:00Z", "decidedBy": "owner"}}}}))
        self.cfg = self.home / ".openclaw" / "openclaw.json"
        self.cfg.write_text(json.dumps({"agents": {"ownership": "explicit", "entries": {
            "main": {"workspace": str(self.ws)},
            "dept-sales": {"workspace": str(self.company / "departments" / "sales")},
            "dept-marketing": {"workspace": str(self.company / "departments" / "marketing")}}}}))

    def tearDown(self):
        self._tmp.cleanup()

    def test_retire_archives_workspace_copy_and_deregisters_entries(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("DASHBOARD_DB_PATH", "DATABASE_PATH")}
        env["HOME"] = str(self.home)
        # No --company-dir / --oc-config: everything resolves from the live layout.
        r = subprocess.run(["bash", str(RETIRE), "--dept", "sales", "--skip-cc"],
                           capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        # company-tree copy archived (resolved without companySlug)
        self.assertFalse((self.company / "departments" / "sales").exists(), r.stderr)
        self.assertEqual(len(list((self.company / ".retired").glob("sales-*"))), 1)
        # the workspace copy the vertical gate reads is archived, never deleted
        self.assertFalse((self.ws_depts / "sales").exists(), r.stderr)
        archived = list((self.ws / ".retired").glob("sales-*"))
        self.assertEqual(len(archived), 1, r.stderr)
        self.assertEqual((archived[0] / "SOUL.md").read_text(), "sales\n")
        # agents.entries deregistration, shape preserved
        agents = json.loads(self.cfg.read_text())["agents"]
        self.assertNotIn("list", agents)
        self.assertEqual(sorted(agents["entries"]), ["dept-marketing", "main"])
        # untouched neighbour
        self.assertTrue((self.company / "departments" / "marketing").is_dir())


if __name__ == "__main__":
    unittest.main()
