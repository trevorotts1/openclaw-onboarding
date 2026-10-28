#!/usr/bin/env python3
"""ensure_cc_interview_flag mirrors build-state interviewComplete=true into clients.interview_complete (is_self=1 only)."""
import json, sqlite3, sys, tempfile, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared-utils"))
import ensure_cc_interview_flag as E


def box(td, complete=True, self_flag=0, with_self=True):
    td = Path(td); app = td / "app"; app.mkdir()
    state = td / "state.json"; state.write_text(json.dumps({"interviewComplete": complete}))
    con = sqlite3.connect(app / "mission-control.db")
    con.execute("create table clients(id text primary key, interview_complete integer not null default 0, is_self integer not null default 0, updated_at text)")
    con.execute("insert into clients(id, interview_complete, is_self) values('remote', 0, 0)")
    if with_self:
        con.execute("insert into clients(id, interview_complete, is_self) values('self', ?, 1)", (self_flag,))
    con.commit(); con.close()
    return app, state


def flags(app):
    con = sqlite3.connect(app / "mission-control.db")
    try:
        return dict(con.execute("select id, interview_complete from clients"))
    finally:
        con.close()


class T(unittest.TestCase):
    def test_sets_self_row_only_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            app, state = box(td)
            self.assertEqual(E.run(state, app, check_only=True)[0], 3)       # --check reports, writes nothing
            self.assertEqual(flags(app), {"remote": 0, "self": 0})
            self.assertEqual(E.run(state, app)[0], 0)
            self.assertEqual(flags(app), {"remote": 0, "self": 1})            # the is_self=1 row only
            self.assertEqual(E.run(state, app)[0], 0)
            self.assertEqual(E.run(state, app, check_only=True)[0], 0)
    def test_never_sets_unless_build_state_is_exactly_true(self):
        for value in (False, "true", 1, None):
            with tempfile.TemporaryDirectory() as td:
                app, state = box(td, complete=value)
                self.assertEqual(E.run(state, app)[0], 0)
                self.assertEqual(flags(app)["self"], 0, value)
    def test_never_clears_the_flag(self):
        with tempfile.TemporaryDirectory() as td:
            app, state = box(td, complete=False, self_flag=1)
            self.assertEqual(E.run(state, app)[0], 0)
            self.assertEqual(flags(app)["self"], 1)
    def test_fail_soft_when_nothing_to_write_to(self):
        with tempfile.TemporaryDirectory() as td:
            app, state = box(td, with_self=False)
            self.assertEqual(E.run(state, app)[0], 4)                         # no self row: not applicable, nothing inserted
            self.assertEqual(flags(app), {"remote": 0})
            (app / "mission-control.db").unlink()
            self.assertEqual(E.run(state, app)[0], 4)                         # no database: never created
            self.assertFalse((app / "mission-control.db").exists())
            self.assertEqual(E.run(Path(td) / "missing.json", app)[0], 4)     # no build-state
    def test_wired_into_the_roll_and_the_complete_path(self):
        roll = (REPO / "update-skills.sh").read_text()
        for helper in ("ensure_cc_interview_flag.py", "ensure_cc_tenant_env.py"):
            self.assertIn("shared-utils/" + helper, roll)
        self.assertIn("ensure_cc_interview_flag.py", (REPO / "23-ai-workforce-blueprint/scripts/update-interview-state.sh").read_text())

if __name__ == "__main__":
    unittest.main()
