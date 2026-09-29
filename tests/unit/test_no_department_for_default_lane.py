#!/usr/bin/env python3
"""The Command Center's structural 'default' workspace is not a department.

Seen on a client box: seed-dashboard-content.py seeded a head agent ("General
Lead") for the placeholder 'default' workspace, and scaffold-agent-files.sh then
created ~/.openclaw/workspace/departments/default -- a department folder no
client chose, which fails the ZERO HUMAN EXPERIENCE gate. A real department lane
on the same board still gets its head agent and folder.

Run: python3 tests/unit/test_no_department_for_default_lane.py
"""
import importlib.util
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

S32 = Path(__file__).resolve().parents[2] / "32-command-center-setup" / "scripts"


class DefaultLane(unittest.TestCase):
    def setUp(self):
        if Path("/data/.openclaw").is_dir():
            self.skipTest("/data/.openclaw exists: the scaffolder would write there")
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.home = Path(t.name)
        (self.home / ".openclaw" / "workspace").mkdir(parents=True)
        self.depts = self.home / ".openclaw" / "workspace" / "departments"
        env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)

    def test_board_default_lane_gets_no_head_agent_and_no_folder(self):
        spec = importlib.util.spec_from_file_location("sdc_default_lane", S32 / "seed-dashboard-content.py")
        sdc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sdc)
        db = sqlite3.connect(self.home / "mission-control.db")
        db.executescript("""
            CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, slug TEXT, company_id TEXT);
            CREATE TABLE agents (id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT, role TEXT,
                                 persona TEXT, description TEXT, status TEXT);
            CREATE TABLE tasks (id TEXT PRIMARY KEY, workspace_id TEXT, title TEXT, status TEXT,
                                assigned_agent_id TEXT);
            INSERT INTO workspaces VALUES ('default', 'General', 'default', 'default');
            INSERT INTO workspaces VALUES ('marketing', 'Marketing', 'marketing', 'acme');
        """)
        sdc.insert_agents_and_tasks(db, {}, starter_tasks=True)
        db.commit()
        by_ws = dict(db.execute("SELECT workspace_id, name FROM agents").fetchall())
        self.assertNotIn("default", by_ws)
        self.assertEqual(by_ws.get("marketing"), "Marketing Lead")
        self.assertEqual(db.execute("SELECT count(*) FROM tasks WHERE workspace_id='default'").fetchone()[0], 0)
        self.assertFalse((self.depts / "default").exists())
        self.assertTrue((self.depts / "marketing").is_dir())

    def test_scaffolder_never_creates_departments_default(self):
        r = subprocess.run(["bash", str(S32 / "scaffold-agent-files.sh"), "--agent-slug", "default",
                            "--agent-name", "General Lead"], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("SKIP", r.stdout)
        self.assertFalse((self.depts / "default").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
