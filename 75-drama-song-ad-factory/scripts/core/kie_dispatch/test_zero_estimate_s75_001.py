#!/usr/bin/env python3
"""S75-001: a paid job never rides a zero estimate. Three checks, all offline.

  (a) production mode, cost 0, video model -> rejected
      ZERO_ESTIMATE_FOR_PAID_JOB and the ledger holds no job row;
  (b) cost = remaining budget + 1 -> the run parks BUDGET_EXCEEDED and
      Skill 74 is never asked to submit;
  (c) cost within budget -> the job goes through (outcome ok).

Zero paid calls: Skill 74 is the Fake74 stand-in used by
test_kie_dispatch.py, the ledger is a throwaway file in a temp directory, and
a dispatch that forgot its fake runner fails closed.

Run: python3 -B scripts/core/kie_dispatch/test_zero_estimate_s75_001.py
"""
import importlib
import os
import sqlite3
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

import kie_dispatch as D            # noqa: E402  (package under test)
import kie_dispatch.model_lock as ML  # noqa: E402  (video-model lock)
import spend_ledger as L            # noqa: E402  (sibling, same core/ tree)

MODULE = importlib.import_module("kie_dispatch.kie_dispatch")

FAILS = []


def _forbid_make_runner(*_a, **_k):
    """Zero paid calls: no test may ever spawn the real Skill 74."""
    raise AssertionError("real Skill 74 runner disabled in tests")


_NO_REAL_RUNNER = mock.patch.object(MODULE, "make_runner", _forbid_make_runner)


def setup_module(_module=None):
    """Scoped, not global: teardown restores the module under test."""
    _NO_REAL_RUNNER.start()


def teardown_module(_module=None):
    _NO_REAL_RUNNER.stop()


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class Fake74:
    """Stands in for kie_live_adapter.py. Records every argv it is handed."""

    def __init__(self, script):
        self.script = script
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        sub = argv[1] if len(argv) > 1 else ""
        if sub not in self.script:
            raise AssertionError("unexpected Skill 74 call: %r" % sub)
        res = self.script[sub]
        if isinstance(res, Exception):
            raise res
        return res

    def argv_of(self, sub):
        for c in self.calls:
            if len(c) > 1 and c[1] == sub:
                return c
        return None


def _real_file(suffix=".png", data=b"\x89PNG\r\n\x1a\n"):
    """A real non-zero output file: F11 refuses to call a missing or empty
    path saved, so an 'ok' fixture must materialize the bytes it claims."""
    path = os.path.join(tempfile.mkdtemp(prefix="zero-est-out-"), "out" + suffix)
    with open(path, "wb") as f:
        f.write(data)
    return path


def job_count(db, logical_key):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE logical_key=?",
            (logical_key,)).fetchone()[0]
    finally:
        conn.close()


HEALTH_ACTIVE = (0, {"adapter_mode": "active", "state": "success"})
PREFLIGHT_OK = (0, {"state": "validated", "data": {"ok": True}})
BUDGET_OK = (0, {"state": "success",
                 "data": {"status": "OK", "exit_code": 0, "max": 20000}})
BASE_SCRIPT = {
    "health": HEALTH_ACTIVE,
    "preflight": PREFLIGHT_OK,
    "prompt-budget": BUDGET_OK,
}

#: The recorded choice-card receipt the stub runs carry (the four F15 answers,
#: stamped). Copied from test_kie_dispatch.py; dispatch only reads it.
STAMPED_CARD = {"answers": {"video_style": "Lifelike 3D",
                            "audio_style": "Soul Ballad",
                            "length": 60,
                            "video_model": "MiniMax H3 768P"},
                "who": "S75-001 dispatch test",
                "at": "2026-11-12T09:00:00Z"}

IMAGE_MODEL = "gpt-image-2-6/sunburst-text-to-image"


def _run(script, label, cost, model=IMAGE_MODEL, production=False):
    """One dispatch against a fake Skill 74 and a fresh throwaway ledger."""
    tmp = tempfile.mkdtemp(prefix="zero-est-")
    db = os.path.join(tmp, "spend.db")
    run_id = "run-" + label
    L.init_run(db, run_id, 10000)
    state_db = os.path.join(tmp, "state.db")
    try:
        is_vid = (MODULE._is_menu_video(model)
                  or MODULE._modality(model) == "video")
    except Exception:                                   # noqa: BLE001
        is_vid = False
    if is_vid:
        ML.lock_run_model(state_db, run_id, ML.DEFAULT_VIDEO_MODEL)
    fake = Fake74(script)
    if production:
        # Only this marker makes dispatch() read the run as production; the
        # fake still answers every Skill 74 command it is handed.
        fake._s75_live_runner = True
    env = D.dispatch(
        model=model,
        request={"model": model, "input": {"prompt": "p" * 200},
                 "card_receipt": STAMPED_CARD},
        save_dir=os.path.join(tmp, "out"), ledger_db=db, run_id=run_id,
        logical_key=label + "-job", attempt_id="att-1",
        estimated_cost=cost, prompt="q" * 200,
        adapter_path=os.path.abspath(__file__), runner=fake,
        state_store=state_db)
    return env, db, fake


def test_a_zero_estimate_production_is_refused():
    """(a) A production video job with cost 0 reserves nothing, sends
    nothing, and says exactly why."""
    env, db, fake = _run(BASE_SCRIPT, "zero-prod", cost=0,
                         model=ML.DEFAULT_VIDEO_MODEL, production=True)
    check("(a) outcome rejected", env.get("outcome") == "rejected",
          repr(env.get("outcome")))
    check("(a) reason ZERO_ESTIMATE_FOR_PAID_JOB",
          env.get("reason_code") == "ZERO_ESTIMATE_FOR_PAID_JOB",
          repr(env.get("reason_code")))
    check("(a) nothing generated",
          (env.get("evidence") or {}).get("generated") is False,
          repr(env.get("evidence")))
    check("(a) ledger has no job row", job_count(db, "zero-prod-job") == 0,
          str(job_count(db, "zero-prod-job")))
    check("(a) Skill 74 never called", fake.calls == [], repr(fake.calls))


def test_b_above_budget_parks_without_submit():
    """(b) One unit over the remaining budget parks the run; Skill 74 never
    sees a submit."""
    shot = _real_file()
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "task-over"}),
        "wait": (0, {"state": "success", "task_id": "task-over",
                     "credits_consumed": 16}),
        "save": (0, {"state": "success", "task_id": "task-over",
                     "saved_paths": [shot], "credits_consumed": 16}),
    })
    env, db, fake = _run(script, "over-budget", cost=10001)
    check("(b) outcome parked", env.get("outcome") == "parked",
          repr(env.get("outcome")))
    check("(b) reason BUDGET_EXCEEDED",
          env.get("reason_code") == "BUDGET_EXCEEDED",
          repr(env.get("reason_code")))
    check("(b) submit was never called", fake.argv_of("submit") is None,
          repr(fake.calls))


def test_c_within_budget_dispatches():
    """(c) A cost inside the budget still dispatches normally."""
    shot = _real_file()
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "task-ok"}),
        "wait": (0, {"state": "success", "task_id": "task-ok",
                     "credits_consumed": 16}),
        "save": (0, {"state": "success", "task_id": "task-ok",
                     "saved_paths": [shot], "credits_consumed": 16}),
    })
    env, db, fake = _run(script, "within-budget", cost=100)
    check("(c) outcome ok", env.get("outcome") == "ok",
          repr({k: env.get(k) for k in ("outcome", "reason_code")}))
    check("(c) reason KIE_DISPATCH_OK",
          env.get("reason_code") == "KIE_DISPATCH_OK",
          repr(env.get("reason_code")))
    check("(c) submit was called", fake.argv_of("submit") is not None,
          repr(fake.calls))


TESTS = [
    test_a_zero_estimate_production_is_refused,
    test_b_above_budget_parks_without_submit,
    test_c_within_budget_dispatches,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                          # noqa: BLE001
            check("%s raised" % t.__name__, False, "%s: %s"
                  % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("%d passes" % len(TESTS))
    return 0


if __name__ == "__main__":
    setup_module()
    sys.exit(main())
