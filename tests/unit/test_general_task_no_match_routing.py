#!/usr/bin/env python3
"""A "no match" routing decision lands in general-task in EVERY decision-engine mode.

general-task is the catch-all department. This proves, against the REAL shipped
code (no reimplemented logic), that when nothing matches the task it is routed to
general-task:

  * in every configured mode: auto, shadow, legacy, off
  * when JEV is unavailable (no credentials, resolver error, JEV bridge core missing)
  * in all three places a routing decision is made:
      1. the JEV bridge          shared-utils/decision-engine.py --evaluate
      2. the no-JEV fallback     decision_engine.fallback.select
      3. the ladder's no-JEV hook (DirectFirstLadder.run wired to fallback.select)

A real match must still win over the catch-all (the catch-all is never a
lexical winner), so these tests cannot pass by always answering general-task.

Run: python3 -m pytest tests/unit/test_general_task_no_match_routing.py -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parent.parent.parent
_SHARED = _REPO / "shared-utils"
_BRIDGE = _SHARED / "decision-engine.py"

sys.path.insert(0, str(_SHARED))

MODES = ("auto", "shadow", "legacy", "off")
NO_MATCH = "Zorblax the quintessential frobnicator"   # matches no department word
REAL_MATCH = "send the client an invoice and take payment"
GENERAL = "general-task"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fb = _load("gt_nomatch_fallback", _SHARED / "decision_engine" / "fallback" / "__init__.py")
ladder = _load("gt_nomatch_ladder", _SHARED / "decision_engine" / "ladder" / "ladder.py")

CATALOG = [
    {"id": "marketing", "text": "Marketing campaign ad promotion", "topics": ["campaign"]},
    {"id": "billing", "text": "Billing invoice payment refund", "topics": ["invoice"]},
    {"id": GENERAL, "text": "General Task catch-all", "topics": []},
]


def _bridge(task, mode, departments=None, department=None):
    """Run the real JEV bridge as a subprocess with the box's mode env set."""
    req = {"schemaVersion": "1.1.0", "taskDescription": task}
    if departments is not None:
        req["departments"] = departments
    if department is not None:
        req["department"] = department
    env = dict(os.environ, OPENCLAW_DECISION_ENGINE_MODE=mode, OPENCLAW_PLATFORM="mac")
    done = subprocess.run([sys.executable, str(_BRIDGE), "--evaluate"], input=json.dumps(req),
                          capture_output=True, text=True, env=env)
    return done


class BridgeNoMatch(unittest.TestCase):
    """1. The JEV bridge: no match -> general-task, fallback True, in every mode."""

    def test_no_match_lands_in_general_task_in_every_mode(self):
        for mode in MODES:
            for label, catalog in (("standard floor", None),
                                   ("caller catalog", [{"slug": "marketing", "name": "Marketing"},
                                                       {"slug": "billing", "name": "Billing"}]),
                                   ("only the catch-all", [{"slug": GENERAL, "name": "General Task"}])):
                with self.subTest(mode=mode, catalog=label):
                    done = _bridge(NO_MATCH, mode, departments=catalog)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    route = json.loads(done.stdout)["route"]
                    self.assertEqual(route["action"], "route")
                    self.assertEqual(route["department"], GENERAL)
                    self.assertTrue(route["fallback"])

    def test_unknown_requested_department_lands_in_general_task(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                done = _bridge(NO_MATCH, mode, department="not-a-real-department",
                               departments=[{"slug": "marketing", "name": "Marketing"}])
                route = json.loads(done.stdout)["route"]
                self.assertEqual(route["department"], GENERAL)
                self.assertTrue(route["fallback"])

    def test_real_match_still_beats_the_catch_all(self):
        catalog = [{"slug": "billing", "name": "Billing", "description": "invoice payment refund"},
                   {"slug": GENERAL, "name": "General Task"}]
        for mode in MODES:
            with self.subTest(mode=mode):
                route = json.loads(_bridge(REAL_MATCH, mode, departments=catalog).stdout)["route"]
                self.assertEqual(route["department"], "billing")
                self.assertFalse(route["fallback"])

    def test_bridge_unusable_is_loud_never_a_wrong_department(self):
        """JEV bridge core missing: exit 3, no stdout. The caller's own no-JEV path decides (class 2)."""
        lone = tempfile.mkdtemp(prefix="gt-nomatch-")
        try:
            shutil.copy(_BRIDGE, lone)
            done = subprocess.run([sys.executable, str(Path(lone) / "decision-engine.py"), "--evaluate"],
                                  input=json.dumps({"schemaVersion": "1.1.0", "taskDescription": NO_MATCH}),
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 3)
            self.assertEqual(done.stdout, "")
        finally:
            shutil.rmtree(lone, ignore_errors=True)


class NoJevFallbackNoMatch(unittest.TestCase):
    """2. The no-JEV fallback selector: no match -> general-task, in every mode, for every skip reason."""

    def test_no_match_lands_in_general_task_in_every_mode_and_skip_reason(self):
        for mode in MODES:
            for reason in fb.SKIP_REASONS:
                with self.subTest(mode=mode, reason=reason):
                    got = fb.select(CATALOG, NO_MATCH, {"configuredMode": mode}, skip_reason=reason)
                    self.assertEqual(got["selectedId"], GENERAL)
                    self.assertIn("no_match_general_task", got["reasonCodes"])
                    self.assertEqual((got["jevCalls"], got["probeCalls"], got["shadowRemoteCalls"]), (0, 0, 0))

    def test_catch_all_listed_first_or_last_gives_the_same_answer(self):
        for catalog in (CATALOG, list(reversed(CATALOG))):
            self.assertEqual(fb.select(catalog, NO_MATCH, skip_reason="jev_unavailable")["selectedId"], GENERAL)

    def test_dept_prefixed_catch_all_is_recognised(self):
        catalog = [{"id": "marketing", "text": "Marketing campaign", "topics": []},
                   {"id": "dept-general-task", "text": "General Task", "topics": []}]
        self.assertEqual(fb.select(catalog, NO_MATCH, skip_reason="jev_unavailable")["selectedId"],
                         "dept-general-task")

    def test_real_match_still_wins_in_every_mode(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                got = fb.select(CATALOG, REAL_MATCH, {"configuredMode": mode}, skip_reason="jev_unavailable")
                self.assertEqual(got["selectedId"], "billing")
                self.assertNotIn("no_match_general_task", got["reasonCodes"])

    def test_catalog_without_a_catch_all_is_unchanged(self):
        """The catch-all rule applies only when the caller's catalog carries general-task."""
        plain = [c for c in CATALOG if c["id"] != GENERAL]
        got = fb.select(plain, NO_MATCH, skip_reason="jev_unavailable")
        self.assertEqual(got["selectedId"], "marketing")           # old behaviour: first entry, truthful rank
        self.assertIn("zero_overlap_truthful_rank", got["reasonCodes"])
        self.assertIsNone(fb.select([], NO_MATCH, skip_reason="jev_unavailable")["selectedId"])

    def test_ranking_is_unchanged_by_the_catch_all_rule(self):
        got = fb.select(CATALOG, REAL_MATCH, skip_reason="jev_unavailable")
        self.assertEqual([r["id"] for r in got["ranking"]][0], "billing")
        self.assertEqual(sorted(r["id"] for r in got["ranking"]), sorted(c["id"] for c in CATALOG))


def _creds(direct, openrouter):
    return {"direct": SimpleNamespace(configured=direct), "openrouter": SimpleNamespace(configured=openrouter)}


def _no_jev_router(review):
    """The no-JEV hook a caller wires into the ladder: the real fallback selector."""
    got = fb.select(CATALOG, NO_MATCH, skip_reason="jev_unavailable")
    return {"decision_source": "no_jev", "ok": True, "outcome": "no_jev_fallback",
            "selected_department": got["selectedId"], "reason_codes": got["reasonCodes"]}


class LadderNoMatch(unittest.TestCase):
    """3. The ladder with JEV unavailable: the no-JEV hook's no-match answer is general-task in every mode."""

    def _run(self, mode, resolve):
        remote = []

        def _direct(**kw):
            remote.append("direct")
            return {"outcome": "ok", "attempts": 1, "estimated_cost": 0.0, "actual_cost": 0.0}

        def _router(**kw):
            remote.append("openrouter")
            return {"outcome": "ok", "attempts": 1, "estimated_cost": 0.0, "actual_cost": 0.0}

        lad = ladder.DirectFirstLadder(
            resolve_credentials=resolve, direct_call=_direct, openrouter_call=_router,
            policy_fn=lambda provider, purpose="decide": {"spend_ok": True, "transmit_ok": True, "reason": "test"})
        verdict = lad.run(company_id="acme", state={"s": 1}, questions=[{"id": "q1", "type": "select"}],
                          keys={}, config={"configuredMode": mode}, no_jev_fallback=_no_jev_router)
        return verdict, remote

    def _assert_general(self, verdict):
        self.assertEqual(verdict["decision_source"], "no_jev")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["fallback"]["selected_department"], GENERAL)
        self.assertIn("no_match_general_task", verdict["fallback"]["reason_codes"])

    def test_no_credentials_in_every_mode(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                verdict, remote = self._run(mode, lambda *a: _creds(False, False))
                self._assert_general(verdict)
                self.assertEqual(remote, [])           # JEV unavailable: nothing was sent

    def test_resolver_error_in_every_mode(self):
        def boom(*a):
            raise RuntimeError("credential store unreadable")

        for mode in MODES:
            with self.subTest(mode=mode):
                verdict, _ = self._run(mode, boom)
                self._assert_general(verdict)

    def test_off_legacy_shadow_never_touch_jev(self):
        for mode in ("off", "legacy", "shadow"):
            with self.subTest(mode=mode):
                verdict, remote = self._run(mode, lambda *a: _creds(True, True))
                self._assert_general(verdict)
                self.assertEqual(remote, [])
                self.assertEqual(verdict["mode"]["configuredMode"], mode)

    def test_a_failing_hook_never_loses_the_task(self):
        """If the no-JEV hook itself raises, the ladder reports ok=False loudly rather than inventing a route."""
        lad = ladder.DirectFirstLadder(resolve_credentials=lambda *a: _creds(False, False),
                                       direct_call=lambda **k: {}, openrouter_call=lambda **k: {})

        def explode(review):
            raise ValueError("hook broke")

        verdict = lad.run(company_id="acme", state={}, questions=[], keys={},
                          config={"configuredMode": "auto"}, no_jev_fallback=explode)
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["fallback"]["outcome"], "fallback_error")


if __name__ == "__main__":
    unittest.main()
