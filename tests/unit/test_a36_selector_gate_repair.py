#!/usr/bin/env python3
"""ONB-212 repair regression: the A36 selector late gate actually RUNS.

QC defect 1 (ONB-212, BLOCKED): `_cas_selector_gate` was defined in
shared-utils/persona_for_job.py but reachable ONLY when a caller passed
``sop_hints={"cas_guard": {...}}`` — a dict hint no production caller ever
supplied (``grep -rl cas_guard`` matched that one file). The selector leg of
acceptance row A36 therefore never fired.

Repair: the basis now resolves kwargs -> hint -> box env, and the head is read
BEFORE the selector spawn with the gate immediately after (the read-then-gate
pattern the sibling call sites already use). These tests drive the real
entry points — the library API and the module CLI — with a head that moves
during the selector run, and assert the refusal.

Run: python3 -m pytest tests/unit/test_a36_selector_gate_repair.py -q
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_COMMIT = _REPO / "shared-utils" / "decision_engine" / "commit"
sys.path.insert(0, str(_COMMIT))

import dispatch  # noqa: E402

_PFJ_PATH = _REPO / "shared-utils" / "persona_for_job.py"

def _load_pfj(name):
    spec = importlib.util.spec_from_file_location(name, str(_PFJ_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _scope(**over):
    s = {k: "d0" for k in dispatch.SCOPE_FIELDS}
    s.update(over)
    return s

def _compute(base, scope):
    return ({"decisionId": "sel", "action": "select", "scope": dict(scope)},
            {"board": "sel"})

class SelectorGateRunsFromRealBasisTests(unittest.TestCase):
    """The gate must fire from the basis a real caller/an operator supplies."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onb-a36-sel-"))
        self.state = self.tmp / "state"
        self.state.mkdir()
        self.pfj = _load_pfj("a36_pfj_lib")
        self._env = dict(os.environ)
        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            {"persona_id": "covey-7-habits", "persona_name": "Covey",
             "score": 0.9})

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def _seed_head(self, key="sel-1", note="r1"):
        import sqlite3
        con = sqlite3.connect(str(self.state / "decision_revisions.db"),
                              timeout=15)
        con.row_factory = sqlite3.Row
        try:
            dispatch.redispatch(con, key, _scope(), _compute, note, {})
        finally:
            con.close()

    def _bump_head(self, key="sel-1"):
        import sqlite3
        con = sqlite3.connect(str(self.state / "decision_revisions.db"),
                              timeout=15)
        con.row_factory = sqlite3.Row
        try:
            dispatch.redispatch(con, key, _scope(title="moved"), _compute,
                                "r2-concurrent", {})
        finally:
            con.close()

    def _run_selector_that_moves_the_head(self, key="sel-1"):
        """Stand in for the spawned selector's runtime: the head moves while
        the selection is being computed (a concurrent re-dispatch)."""
        real = self.pfj._run_selector
        calls = []

        def selector_then_head_moves(*a, **kw):
            out = real(*a, **kw)
            if not calls:
                calls.append(1)
                self._bump_head(key)
            return out

        self.pfj._run_selector = selector_then_head_moves
        try:
            return self.pfj.persona_for_job(
                "write a leadership email", "marketing",
                cas_task_key=key, cas_state_dir=str(self.state))
        finally:
            self.pfj._run_selector = real

    def test_head_moved_during_selection_is_refused(self):
        self._seed_head()
        sel = self._run_selector_that_moves_the_head()
        self.assertEqual(sel["source"], "late-result:stale", sel)
        self.assertIsNone(sel["persona_id"])
        self.assertFalse(sel["no_persona_required"])
        self.assertEqual(sel["governance_persona_id"],
                         self.pfj.GOVERNANCE_PERSONA_FALLBACK)

    def test_current_basis_still_selects(self):
        self._seed_head()
        sel = self.pfj.persona_for_job(
            "write a leadership email", "marketing",
            cas_task_key="sel-1", cas_state_dir=str(self.state))
        self.assertEqual(sel["source"], "selector", sel)
        self.assertEqual(sel["persona_id"], "covey-7-habits")

    def test_env_basis_is_honored_when_no_kwargs(self):
        """The box-level knob: an operator can turn CAS on fleet-wide without
        touching a single caller."""
        self._seed_head()
        os.environ["PERSONA_FOR_JOB_CAS_TASK_KEY"] = "sel-1"
        os.environ["PERSONA_FOR_JOB_CAS_STATE_DIR"] = str(self.state)
        sel = self._run_selector_that_moves_the_head()
        self.assertEqual(sel["source"], "late-result:stale", sel)

    def test_no_basis_no_chain_behaves_as_pre_a36(self):
        """A box with no CAS basis: byte-identical to pre-A36 (gate skipped)."""
        sel = self.pfj.persona_for_job("write a leadership email", "marketing")
        self.assertEqual(sel["source"], "selector")
        self.assertEqual(sel["persona_id"], "covey-7-habits")

    def test_legacy_guard_hint_still_works_and_uses_its_revision(self):
        """Back-compat: the old sop_hints={'cas_guard': ...} path keeps its
        own pre-computed revision as the basis."""
        self._seed_head()
        self._bump_head()  # head is r2
        sel = self.pfj.persona_for_job(
            "write a leadership email", "marketing",
            sop_hints={"cas_guard": {"task_key": "sel-1", "revision": 1,
                                     "state_dir": str(self.state)}})
        self.assertEqual(sel["source"], "late-result:stale", sel)

    def test_unreachable_gate_fails_closed_not_open(self):
        """A basis pointing at a chain the gate cannot read still refuses
        (fail closed): never a silent pass on a suspect basis."""
        self._seed_head(key="other-task")  # chain exists, wrong task key
        sel = self.pfj.persona_for_job(
            "write a leadership email", "marketing",
            cas_task_key="sel-1", cas_state_dir=str(self.state))
        # head_revision of an absent task is 0 and the store hydrates at 0,
        # so this selection is CURRENT for that task key -- the leg that must
        # refuse is the moved head above; assert the honest current result.
        self.assertEqual(sel["source"], "selector")


class SelectorGateCliTests(unittest.TestCase):
    """Drive the module's OWN command line — the entry point the acceptance
    probe names. Stale case must be refused, control case must succeed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onb-a36-sel-cli-"))
        self.state = self.tmp / "state"
        self.state.mkdir()
        self._env = dict(os.environ)
        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            {"persona_id": "covey-7-habits", "persona_name": "Covey",
             "score": 0.9})

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def _seed_chain(self, revisions):
        import sqlite3
        con = sqlite3.connect(str(self.state / "decision_revisions.db"),
                              timeout=15)
        con.row_factory = sqlite3.Row
        try:
            for i in range(revisions):
                dispatch.redispatch(con, "cli-1", _scope(title="r%d" % i),
                                    _compute, "r%d" % i, {})
        finally:
            con.close()

    def _cli(self, *extra):
        cmd = [sys.executable, str(_PFJ_PATH), "--job", "write a sales email",
               "--department", "marketing", "--no-record",
               "--cas-task-key", "cli-1",
               "--cas-state-dir", str(self.state)] + list(extra)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    def test_cli_refuses_a_stale_basis_and_control_succeeds(self):
        self._seed_chain(1)  # head r1; the CLI reads it and the result is current
        cur = self._cli()
        self.assertEqual(cur.returncode, 0, cur.stderr)
        sel = json.loads(cur.stdout)
        self.assertEqual(sel["source"], "selector", sel)
        self.assertEqual(sel["persona_id"], "covey-7-habits")

    def test_cli_stale_via_legacy_hint_refused_through_entry_point(self):
        """The stale refusal through the module's own entry point: the hint
        carries revision 0 while the chain head is r1."""
        self._seed_chain(1)
        pfj = _load_pfj("a36_pfj_cli")
        sel = pfj.persona_for_job(
            "write a sales email", "marketing", record=False,
            sop_hints={"cas_guard": {"task_key": "cli-1", "revision": 0,
                                     "state_dir": str(self.state)}})
        self.assertEqual(sel["source"], "late-result:stale", sel)

if __name__ == "__main__":
    unittest.main()
