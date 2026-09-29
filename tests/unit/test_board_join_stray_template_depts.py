"""AF-BOARD-JOIN-DRIFT must not fire on stray role-library template trees.

Seen on a client Mac with interviewComplete=false: five role-library template
department trees (client-experience-booking, founding-member-concierge,
launch-operations, product-production, rescue-rangers) sat under
~/.openclaw/workspace/zero-human-company/<slug>/departments since provisioning.
None is in the 30-entry chosen departments.json and none has a board column, so
prove-board-join.py returned drift, prebuild-standard-workforce.py exited 7 and
update-skills.sh exited 8. They are stray template copies: WARN, never drift, and
never deleted. A chosen department with no board column must still drift.
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JOIN = REPO / "23-ai-workforce-blueprint" / "scripts" / "prove-board-join.py"
STRAY = ["client-experience-booking", "founding-member-concierge", "launch-operations",
         "product-production", "rescue-rangers"]

_spec = importlib.util.spec_from_file_location(
    "department_floor_t", REPO / "23-ai-workforce-blueprint" / "scripts" / "department-floor.py")
df = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(df)
_nm = df.load_naming_map()
FLOOR = df.mandatory_ids(_nm) + df.universal_primary_vertical_departments(_nm)


class StrayTemplateTrees(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.home = Path(td.name)
        self.company = self.home / ".openclaw/workspace/zero-human-company/acme"
        # departments.json the way build-workforce writes it: the CEO column as slug
        # "ceo" (tree departments/master-orchestrator) + every other floor dept = 30.
        chosen = [{"id": "dept-ceo", "slug": "ceo",
                   "workspacePath": "departments/master-orchestrator"}]
        chosen += [{"id": f"dept-{d}", "slug": d} for d in FLOOR if d != "master-orchestrator"]
        self.assertEqual(len(chosen), 30)
        self.company.mkdir(parents=True)
        (self.company / "departments.json").write_text(json.dumps(chosen))
        for d in FLOOR + STRAY:
            (self.company / "departments" / d).mkdir(parents=True)
        self.lanes = ["ceo"] + [d for d in FLOOR if d != "master-orchestrator"]

    def _db(self, lanes):
        db = self.home / "mission-control.db"
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE workspaces (slug TEXT, name TEXT, company_id TEXT)")
        c.executemany("INSERT INTO workspaces VALUES (?, ?, 'acme')", [(s, s) for s in lanes])
        c.commit()
        c.close()
        return db

    def _join(self, lanes):
        env = {k: v for k, v in os.environ.items()
               if k not in ("DATABASE_PATH", "DASHBOARD_DB_PATH")}
        env["HOME"] = str(self.home)
        p = subprocess.run([sys.executable, str(JOIN), "--company-dir", str(self.company),
                            "--db", str(self._db(lanes)), "--json"],
                           capture_output=True, text=True, env=env, timeout=60)
        verdict = json.loads(p.stdout[p.stdout.index("\n{") + 1:]) if "\n{" in p.stdout else {}
        return p.returncode, verdict, p.stdout + p.stderr

    def test_stray_template_trees_warn_not_drift(self):
        rc, v, out = self._join(self.lanes)
        self.assertEqual(rc, 0, out)
        self.assertEqual(v["status"], "JOIN-OK")
        self.assertEqual(sorted(e["department"] for e in v["stray_template_departments"]),
                         STRAY)
        self.assertIn("WARN stray template department tree(s)", out)
        for d in STRAY:
            self.assertTrue((self.company / "departments" / d).is_dir())  # never deleted

    def test_chosen_department_without_a_board_column_still_drifts(self):
        rc, v, out = self._join([s for s in self.lanes if s != "podcast"])
        self.assertEqual(rc, 2, out)
        self.assertIn("CHOSEN_NOT_DISPLAYED", v["drift_classes"])

    def test_unchosen_floor_tree_still_drifts(self):
        # A floor dept on disk that departments.json dropped is a declined tree that
        # was never removed, not a stray template copy.
        chosen = json.loads((self.company / "departments.json").read_text())
        (self.company / "departments.json").write_text(
            json.dumps([e for e in chosen if e["slug"] != "podcast"]))
        rc, v, out = self._join([s for s in self.lanes if s != "podcast"])
        self.assertEqual(rc, 2, out)
        self.assertIn("PROVISIONED_NOT_CHOSEN", v["drift_classes"])

    def test_stray_template_with_a_board_column_still_drifts(self):
        rc, v, out = self._join(self.lanes + ["launch-operations"])
        self.assertEqual(rc, 2, out)
        # A column makes it a ghost the client can see: full drift, no WARN pass.
        self.assertEqual(v["drift_classes"], ["DISPLAYED_NOT_CHOSEN", "PROVISIONED_NOT_CHOSEN"])
        self.assertNotIn("launch-operations",
                         [e["department"] for e in v["stray_template_departments"]])


if __name__ == "__main__":
    unittest.main()
