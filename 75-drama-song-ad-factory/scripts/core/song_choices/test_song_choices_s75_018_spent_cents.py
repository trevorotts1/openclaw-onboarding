#!/usr/bin/env python3
"""S75-018 / U-GEN303: the real per-attempt charge reaches the reported block.

The song path counted submissions, not money: ``run_takes`` returned the real
``spent_cents`` but ``one_variant`` dropped it and ``cmd_generate`` published
only ``dispatched``. This test stubs ``run_takes`` at a known charge and
asserts the figure survives BOTH wrapper boundaries and the reported block --
12 cents in, 12 cents out. No provider call, no subprocess, no spend.

Pre-fix this fails on every leg: the key is absent from the wrapper's dict and
from the reported block.

Run directly (``python3 test_song_choices_s75_018_spent_cents.py``) or under
pytest. Set ``S75_SONG_FACTORY_ROOT`` to point at the skill root when the
test is run from outside the repo.
"""
import json
import os
import sys
import tempfile
import types
import unittest

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_skill_root():
    """Repo root (the folder holding scripts/core/kie_dispatch). No guesses."""
    env = os.environ.get("S75_SONG_FACTORY_ROOT") or os.environ.get("S75_ROOT")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    probe = HERE
    while True:
        if os.path.isfile(os.path.join(probe, "scripts", "core",
                                       "kie_dispatch", "kie_dispatch.py")):
            return probe
        if os.path.isfile(os.path.join(probe, "kie_dispatch",
                                       "kie_dispatch.py")) and \
                os.path.basename(probe) == "core":
            return os.path.dirname(os.path.dirname(probe))
        parent = os.path.dirname(probe)
        if parent == probe:
            raise RuntimeError(
                "cannot locate the song factory: set S75_SONG_FACTORY_ROOT")
        probe = parent


SKILL = _find_skill_root()
CORE = os.path.join(SKILL, "scripts", "core")
# CORE is inserted LAST so it ends up FIRST on sys.path. `core/song_dispatch`
# holds BOTH the package dir and `song_dispatch/song_dispatch.py`: with that
# subdir ahead of CORE, `import song_dispatch` binds the inner module file and
# `from song_dispatch import song_dispatch` (song_choices.py) dies. Re-inserting
# (not just when absent) keeps the order deterministic under pytest's
# `-o pythonpath=`, which already puts a subdir on sys.path.
for _sub in ("suno_recipe", "song_dispatch", "song_choices", ""):
    _p = os.path.join(CORE, _sub)
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import suno_recipe as R                        # noqa: E402
from song_choices import song_choices as SC    # noqa: E402

CHARGE = 12                      # the charge the stub says was really spent
CLIENT = ("I am not small. I never was. One seed of truth made me strong. "
          "She Found Power in the Climb.")
HOOK_LINES = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_PLAN = {"true_at_beat": "the_world"}
PACE_ORDER = {"drop": "half-time drop, thin drums",
              "return": "turn and rise back to the groove",
              "boundary_s": 14.0, "return_boundary_s": 38.0}
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung",
          "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK_LINES},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK_LINES},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK_LINES},
         {"tag": "Outro", "delivery": "spoken",
          "lines": ["She Found Power in the Climb. Get the book. Link below."]}]


def _stub_run_takes_result():
    """What run_takes returns: its OWN accumulated charge, passed through."""
    return {"delivered": None, "verdict": "FAIL", "receipts": [],
            "spent_cents": CHARGE, "duration": 0.0,
            "submitted_digest": "stub-digest"}


def _request_doc():
    """A real recipe-generated request file (same shape cmd_generate loads)."""
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58,
                          hook_plan=HOOK_PLAN, pace_plan=PACE_ORDER)
    return {"style_id": "soul-ballad", "sheet_text": req["input"]["lyrics"],
            "client_text": CLIENT, "title": "T", "length_s": 58,
            "vocal_gender": "f", "hook_plan": HOOK_PLAN,
            "pace_plan": PACE_ORDER}


class S75018SpentCents(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="s75018-spent-")
        self.addCleanup(self._rmtree, self.root)
        real = SC._SD.run_takes

        def stub_run_takes(*args, **kw):
            return _stub_run_takes_result()

        SC._SD.run_takes = stub_run_takes
        self.addCleanup(setattr, SC._SD, "run_takes", real)

    @staticmethod
    def _rmtree(path):
        import shutil
        shutil.rmtree(path, True)

    # ---- 1. the wrapper carries the callee's charge --------------------
    def test_one_variant_carries_the_charge(self):
        res = SC.one_variant(
            1, {"id": "v1"}, {"_style_id": "soul-ballad"}, {},
            lambda *a, **k: None, lambda take: {}, lambda *a, **k: None,
            [], "hook")
        self.assertIn("spent_cents", res, res)
        self.assertEqual(res["spent_cents"], CHARGE, res)

    # ---- 2. a HELD attempt reports what it was charged -----------------
    def test_held_attempt_reports_its_charge(self):
        variant = {"id": "v1"}

        def gen(*a, **k):
            raise AssertionError("generate must not be called")

        gen.attempt_envelopes = {variant["id"]: SC.attempt_envelope(
            variant["id"], "a1", "error",
            SC.make_counts(planned=1, submitted=1),
            reason_code="KIE_SAVE_TIMEOUT", detail="save transport timed out",
            next_action="re-save the same task id; never resubmit",
            evidence={"resume": {"command": "save", "task_id": "task-held-1"},
                      "credits_consumed": CHARGE, "actual_cost": CHARGE})}
        res = SC.one_variant(
            1, variant, {"_style_id": "soul-ballad"}, {},
            gen, lambda take: {}, lambda *a, **k: None, [], "hook")
        self.assertEqual(res["status"], "HELD", res)
        self.assertEqual(res["spent_cents"], CHARGE, res)

    # ---- 3. the reported block shows it beside ``dispatched`` ----------
    def test_reported_block_shows_the_charge_beside_dispatched(self):
        run_dir = os.path.join(self.root, "run")
        os.makedirs(run_dir)
        req_path = os.path.join(self.root, "request.json")
        with open(req_path, "w", encoding="utf-8") as f:
            json.dump(_request_doc(), f)
        args = types.SimpleNamespace(
            run_dir=run_dir, request=req_path,
            ledger=os.path.join(self.root, "spend.sqlite3"),
            run_id="run-s75018", variant="", unit_id="WW-001")
        out = SC.cmd_generate(args, generate=lambda *a, **k: None,
                              measure=lambda take: {},
                              save=lambda *a, **k: None)
        self.assertEqual(out["spent_cents"], CHARGE, out)
        self.assertIn("dispatched", out, out)
        print("  reported block: dispatched=%r spent_cents=%r"
              % (out["dispatched"], out["spent_cents"]))
        self.assertEqual(out["spent_cents"], CHARGE, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
