#!/usr/bin/env python3
"""JEV A35: the production re-dispatch caller (move-task.py) through the D23 seam.

These tests FAIL with the wiring deleted:

* ``test_caller_invokes_redispatch_on_real_db`` spies on ``dispatch.redispatch``
  and asserts it was actually entered, with a real ``sqlite3.Connection``, and
  that its result landed in the task row's DB (revision chain + the
  ``tasks.assignment_version`` column TaskSnapshot reads). Delete the caller and
  the spy count is 0 — no log line is consulted.
* ``test_stale_revision_is_refused_not_clobbered`` drives the typed D23 late
  gate (``check_late_result``) and asserts refusal + nothing written.
* ``test_changed_scope_creates_new_auditable_revision`` asserts behaviour
  changes: an unchanged re-dispatch REUSES the committed revision, a changed
  8.12 scope produces a NEW one with reason + evidence.

Run: python3 -m pytest tests/unit/test_move_task_redispatch_caller.py -q
"""

import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_MOVE_TASK = _REPO / "32-command-center-setup" / "scripts" / "move-task.py"
_SHARED_UTILS = _REPO / "shared-utils"
sys.path.insert(0, str(_SHARED_UTILS))
sys.path.insert(0, str(_SHARED_UTILS / "decision_engine" / "commit"))


def _load_move_task():
    spec = importlib.util.spec_from_file_location("move_task_a35", str(_MOVE_TASK))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Spy:
    """Delegating proxy over the REAL dispatch module. Counts the D23 entry
    points and records their arguments; everything else passes through."""

    def __init__(self, real):
        self._real = real
        self.redispatch_calls = 0
        self.late_calls = 0
        self.cons = []

    def redispatch(self, con, *a, **kw):
        self.redispatch_calls += 1
        self.cons.append(con)
        return self._real.redispatch(con, *a, **kw)

    def guard_late_result(self, *a, **kw):
        self.late_calls += 1
        return self._real.guard_late_result(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._real, name)


_SELECTOR_STUB = """\
import json, sys
print(json.dumps({"persona_id": "stub-persona", "persona_name": "Stub",
                  "interaction_mode": "leadership", "score": 0.9}))
sys.exit(0)
"""


class RedispatchCallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="a35-caller-")
        cls.root = Path(cls.tmp.name)
        cls.selector = cls.root / "selector-stub.py"
        cls.selector.write_text(_SELECTOR_STUB, encoding="utf-8")
        cls.mt = _load_move_task()
        assert cls.mt._cas_dispatch is not None, "CAS seam failed to import"
        cls.spy = _Spy(cls.mt._cas_dispatch)
        cls.mt._cas_dispatch = cls.spy  # the module's own seam reference

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.db = self.root / (self._testMethodName + ".db")
        if self.db.exists():
            self.db.unlink()
        con = sqlite3.connect(self.db)
        con.execute(
            "CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, description TEXT,"
            " status TEXT, department TEXT, updated_at TEXT, persona_id TEXT,"
            " persona_name TEXT, persona_mode TEXT, persona_score REAL,"
            " persona_selected_at TEXT, decision_scope TEXT)")
        con.execute(
            "INSERT INTO tasks (id,title,description,status,department,decision_scope)"
            " VALUES ('t1','Write launch email','draft a promo email','backlog',"
            "'marketing',?)", (json.dumps({"model": "M1"}),))
        con.commit()
        con.close()
        self._set_env("MOVE_TASK_SELECTOR", str(self.selector))
        self._set_env("MOVE_TASK_GATED_API", "0")  # documented rollback: local write
        self._set_env("MOVE_TASK_API_STUB", None)

    def _set_env(self, key, value):
        prev = os.environ.get(key)

        def restore():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        self.addCleanup(restore)

    # -- helpers ------------------------------------------------------------
    def _move(self, *extra):
        """Drive the PRODUCTION entry point in-process (so the spy sees it)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = self.mt.main(["--db", str(self.db), "move",
                               "--task", "t1", "--to", "in_progress", *extra])
        return rc, out.getvalue(), err.getvalue()

    def _q(self, sql, args=()):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def _one(self, sql, args=()):
        rows = self._q(sql, args)
        return rows[0][0] if rows else None

    def _status(self):
        return self._one("SELECT status FROM tasks WHERE id='t1'")

    def _reset_to_backlog(self):
        con = sqlite3.connect(self.db)
        con.execute("UPDATE tasks SET status='backlog' WHERE id='t1'")
        con.commit()
        con.close()

    def _set_scope_model(self, model):
        con = sqlite3.connect(self.db)
        con.execute("UPDATE tasks SET decision_scope=? WHERE id='t1'",
                    (json.dumps({"model": model}),))
        con.commit()
        con.close()

    def _revisions(self):
        return self._q("SELECT revision, envelope, reason, evidence"
                       " FROM decision_revisions WHERE task_key='t1'"
                       " ORDER BY revision")

    # -- tests --------------------------------------------------------------
    def test_caller_invokes_redispatch_on_real_db(self):
        """Spy: the move ACTUALLY entered dispatch.redispatch, on a REAL
        sqlite3.Connection, and persisted beside the task row."""
        before = self.spy.redispatch_calls
        rc, out, err = self._move()
        self.assertEqual(rc, 0, "move must succeed: %s%s" % (out, err))
        self.assertEqual(self.spy.redispatch_calls - before, 1,
                         "redispatch must be invoked exactly once per resume "
                         "(0 == the caller is not wired)")

        # GAP 1: a real persistence handle, never a caller-supplied dict.
        self.assertIsInstance(self.spy.cons[-1], sqlite3.Connection)

        # GAP 2: envelope/decisionId/reason persisted beside the task row.
        rows = self._revisions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["revision"], 1)
        self.assertTrue(rows[0]["reason"].startswith("resume:"),
                        "reason recorded: %r" % rows[0]["reason"])
        env = json.loads(rows[0]["envelope"])
        self.assertEqual(env["scope"]["title"], "Write launch email")
        self.assertTrue(env.get("decisionId"))

        # GAP 4: the CAS head is written where TaskSnapshot reads it.
        self.assertEqual(
            self._one("SELECT assignment_version FROM tasks WHERE id='t1'"), 1)
        from decision_engine.continuation import TaskSnapshot
        snap = TaskSnapshot(
            task_id="t1",
            assignment_version=self._one(
                "SELECT assignment_version FROM tasks WHERE id='t1'"))
        self.assertEqual(snap.assignment_version, 1)

        # The chain is readable through the documented board surface.
        history = self.spy.revision_history(sqlite3.connect(self.db), "t1")
        self.assertEqual([r["revision"] for r in history], [1])

    def test_unchanged_resume_reuses_committed_revision(self):
        self._move()
        self._reset_to_backlog()
        rc, out, err = self._move()
        self.assertEqual(rc, 0, err)
        self.assertIn("action=reuse", out)
        self.assertEqual(len(self._revisions()), 1,
                         "unchanged re-dispatch must NOT create a new revision")
        self.assertEqual(
            self._one("SELECT assignment_version FROM tasks WHERE id='t1'"), 1)

    def test_changed_scope_creates_new_auditable_revision(self):
        self._move()
        self._reset_to_backlog()
        self._set_scope_model("M2")
        rc, out, err = self._move()
        self.assertEqual(rc, 0, err)
        self.assertIn("action=recommitted", out)
        rows = self._revisions()
        self.assertEqual([r["revision"] for r in rows], [1, 2])
        ev = json.loads(rows[1]["evidence"])
        self.assertIn("model", ev["changed_fields"],
                      "evidence must name the 8.12 dimension that changed")
        self.assertEqual(ev["prior_revision"], 1)
        self.assertEqual(
            self._one("SELECT assignment_version FROM tasks WHERE id='t1'"), 2)

    def test_stale_revision_is_refused_not_clobbered(self):
        """--expected-revision behind the head -> typed D23 refusal (exit 2),
        head + status untouched."""
        self._move()
        self._reset_to_backlog()
        self._set_scope_model("M2")
        self._move()                      # head is now revision 2
        self._reset_to_backlog()

        before = self.spy.late_calls
        rc, out, err = self._move("--expected-revision", "1")
        self.assertEqual(rc, 2, "stale resume must be REFUSED: %s%s" % (out, err))
        self.assertGreater(self.spy.late_calls - before, 0,
                           "the stale gate must run through check_late_result")
        self.assertIn("REFUSED (stale resume)", err)
        self.assertEqual(self._status(), "backlog", "status must not advance")
        self.assertEqual(len(self._revisions()), 2,
                         "a stale caller may not write a revision")
        self.assertEqual(
            self._one("SELECT assignment_version FROM tasks WHERE id='t1'"), 2)
        self.assertTrue(
            self._one("SELECT 1 FROM task_status_audit WHERE task_id='t1'"
                      " AND gate='cas-refused-LateResultError'"),
            "the typed refusal must be audited")

    def test_current_revision_is_not_refused(self):
        """Control: the same gate with the CORRECT revision proceeds — proves
        the refusal above is a head comparison, not a blanket block."""
        self._move()
        self._reset_to_backlog()
        rc, out, err = self._move("--expected-revision", "1")
        self.assertEqual(rc, 0, "%s%s" % (out, err))
        self.assertIn("action=reuse", out)

    def test_reuse_holds_without_scope_echo_in_recompute(self):
        """Base-seam property: a recompute that does NOT echo the scope dict
        still REUSES at an unchanged scope (a missing scope stamp would mint a
        false new revision on every identical re-dispatch)."""
        import dispatch
        scope = {"title": "T", "description": "D", "model": "M1"}

        def compute(base, new_scope):
            return {"decisionId": "sel-A", "action": "select"}, {"board": "sel"}

        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        first = dispatch.redispatch(con, "t", dict(scope), compute, "first", {})
        again = dispatch.redispatch(con, "t", dict(scope), compute, "retry", {})
        self.assertEqual(first[0], "committed")
        self.assertEqual(again[0], "reuse")
        self.assertEqual(again[1], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
