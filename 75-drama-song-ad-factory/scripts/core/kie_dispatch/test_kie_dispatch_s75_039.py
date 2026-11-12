#!/usr/bin/env python3
"""S75-039: Skill 74's exit-5 "pass with a note" prompt result is accepted.

Skill 74's `prompt-budget --check` uses exit 5 for two opposite answers:

  0  in the target band (pass)
  3  below the 80 percent hard floor (refused)
  4  above the documented maximum (refused)
  5  80 to below 95 percent of the maximum: PASSES with a warn-and-expand
     note - but the same code also carries a prompt the adapter REFUSES
     (unknown maximum, policy unavailable, above the target ceiling)

Only the JSON tells them apart, so dispatch must read it: exit 5 proceeds
only when the JSON reports a pass, and the band is written into the job's
ledger note so QC can see the prompt ran below target.

Cases:
  exit 5 + JSON pass  -> the job proceeds, the band is in the ledger note
  exit 5 + JSON fail  -> refused prompt-budget-failed, nothing submitted
  exit 4              -> refused prompt-over-max, exactly as before
  exit 0              -> proceeds, no band note

Zero paid calls: Skill 74 is an injected fake runner and every ledger is a
throwaway file in a temp directory.

Run: python3 -B scripts/core/kie_dispatch/test_kie_dispatch_s75_039.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

import kie_dispatch as D            # noqa: E402  (package under test)
import spend_ledger as L            # noqa: E402  (sibling, same core/ tree)

import importlib                    # noqa: E402

MODULE = importlib.import_module("kie_dispatch.kie_dispatch")

FAILS = []

IMAGE_MODEL = "gpt-image-2-6/sunburst-text-to-image"

#: The recorded choice-card receipt a paid dispatch carries (F15).
STAMPED_CARD = {"answers": {"video_style": "Lifelike 3D",
                            "audio_style": "Soul Ballad",
                            "length": 60,
                            "video_model": "MiniMax H3 768P"},
                "who": "S75-039 prompt-band test",
                "at": "2026-10-08T09:00:00Z"}

HEALTH_ACTIVE = (0, {"adapter_mode": "active", "state": "success"})
PREFLIGHT_OK = (0, {"state": "validated", "data": {"ok": True}})

#: Exit 5, band PASS: the adapter prints state "validated" plus the band data.
BUDGET_BELOW_TARGET = (5, {"state": "validated",
                           "data": {"status": "BELOW_TARGET", "exit_code": 5,
                                    "chars": 17000, "target_min": 19000,
                                    "max": 20000}})
#: Exit 5, but the adapter REFUSED (its own state is "fail").
BUDGET_REFUSED = (5, {"state": "fail",
                      "data": {"status": "UNKNOWN_MAX", "exit_code": 5,
                               "max": None},
                      "error": {"code": "prompt_max_unknown",
                                "msg": "prompt maximum UNKNOWN"}})
BUDGET_OVER_MAX = (4, {"state": "fail",
                       "data": {"status": "ABOVE_MAX", "exit_code": 4,
                                "cut": 300, "max": 20000}})
BUDGET_OK = (0, {"state": "success",
                 "data": {"status": "OK", "exit_code": 0, "max": 20000}})


def _forbid_make_runner(*_a, **_k):
    """Zero paid calls: no test may ever spawn the real Skill 74."""
    raise AssertionError("real Skill 74 runner disabled in tests")


_NO_REAL_RUNNER = mock.patch.object(MODULE, "make_runner", _forbid_make_runner)


def setup_module(_module=None):
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

    def order(self):
        return [c[1] for c in self.calls]


def _real_file(suffix=".png", data=b"\x89PNG\r\n\x1a\n"):
    """A real non-zero output file: dispatch refuses to call an empty path saved."""
    path = os.path.join(tempfile.mkdtemp(prefix="kie-s75039-out-"), "out" + suffix)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _full_script(budget):
    """A budget answer plus the submit/wait/save that reach a saved output."""
    shot = _real_file()
    script = {"health": HEALTH_ACTIVE,
              "preflight": PREFLIGHT_OK,
              "prompt-budget": budget,
              "submit": (0, {"state": "queued", "task_id": "task-s75039",
                             "raw_family": "market"}),
              "wait": (0, {"state": "success", "task_id": "task-s75039",
                           "raw_family": "market",
                           "result_urls": ["https://example.invalid/a.png"],
                           "credits_consumed": 16}),
              "save": (0, {"state": "success", "task_id": "task-s75039",
                           "saved_paths": [shot], "credits_consumed": 16})}
    return script


def run_case(script, label, prompt="q" * 200):
    """One dispatch against a fake Skill 74. Never touches the network."""
    tmp = tempfile.mkdtemp(prefix="kie-s75039-")
    db = os.path.join(tmp, "spend.db")
    run_id = "run-" + label
    L.init_run(db, run_id, 10000)
    save_dir = os.path.join(tmp, "out")
    fake = Fake74(script)
    req = {"model": "m", "input": {"prompt": "p" * 200},
           "card_receipt": STAMPED_CARD}
    env = D.dispatch(
        model=IMAGE_MODEL, request=req, save_dir=save_dir, ledger_db=db,
        run_id=run_id, logical_key=label + "-job", attempt_id="att-1",
        estimated_cost=100, prompt=prompt,
        adapter_path=os.path.abspath(__file__),
        runner=fake, state_store=None)
    return env, db, fake, run_id, label


def budget_note(db, run_id, logical_key):
    """The dispatch evidence row for the prompt-budget stage, parsed."""
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT status, payload_json FROM events WHERE run_id=? "
            "AND logical_key=? AND kind='dispatch' "
            "AND provider_event_id='prompt-budget'",
            (run_id, logical_key)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None, None
    try:
        return row[0], json.loads(row[1])
    except ValueError:
        return row[0], None


def test_exit5_pass_proceeds_with_note():
    """Exit 5 + JSON pass: the job runs and the band is in the ledger note."""
    env, db, fake, run_id, label = run_case(_full_script(BUDGET_BELOW_TARGET),
                                            "s75039-pass")
    check("exit5 pass: outcome ok", env.get("outcome") == "ok",
          str(env.get("outcome")) + " " + str(env.get("reason_code")))
    check("exit5 pass: reason KIE_DISPATCH_OK",
          env.get("reason_code") == "KIE_DISPATCH_OK",
          str(env.get("reason_code")))
    check("exit5 pass: submit was called", "submit" in fake.order(),
          str(fake.order()))
    ev = env.get("evidence") or {}
    check("exit5 pass: envelope carries the band",
          ev.get("prompt_band") == {"prompt_band": "below-target",
                                    "chars": 17000, "target_min": 19000},
          repr(ev.get("prompt_band")))
    status, payload = budget_note(db, run_id, label + "-job")
    check("exit5 pass: ledger note written", payload is not None, repr(status))
    payload = payload or {}
    check("exit5 pass: note status ok", status == "ok", repr(status))
    check("exit5 pass: note band below-target",
          payload.get("prompt_band") == "below-target",
          repr(payload.get("prompt_band")))
    check("exit5 pass: note chars 17000", payload.get("chars") == 17000,
          repr(payload.get("chars")))
    check("exit5 pass: note target_min 19000",
          payload.get("target_min") == 19000, repr(payload.get("target_min")))


def test_exit5_refused_still_refuses():
    """Exit 5 without a passing JSON: refused exactly as before."""
    env, db, fake, run_id, label = run_case(_full_script(BUDGET_REFUSED),
                                            "s75039-refused")
    check("exit5 fail: rejected", env.get("outcome") == "rejected",
          str(env.get("outcome")))
    check("exit5 fail: reason prompt-budget-failed",
          env.get("reason_code") == "prompt-budget-failed",
          str(env.get("reason_code")))
    check("exit5 fail: never submitted", "submit" not in fake.order(),
          str(fake.order()))
    check("exit5 fail: nothing generated",
          (env.get("evidence") or {}).get("generated") is False,
          repr(env.get("evidence")))
    status, payload = budget_note(db, run_id, label + "-job")
    check("exit5 fail: no pass note written", payload is None, repr(status))


def test_exit5_explicit_ok_false_refuses():
    """A literal `ok: false` on exit 5 refuses even with state validated."""
    budget = (5, {"state": "validated", "ok": False,
                  "data": {"status": "ABOVE_TARGET", "exit_code": 5,
                           "chars": 19900, "target_min": 19000}})
    env, db, fake, run_id, label = run_case(_full_script(budget),
                                            "s75039-okfalse")
    check("exit5 ok false: rejected", env.get("outcome") == "rejected",
          str(env.get("outcome")))
    check("exit5 ok false: reason prompt-budget-failed",
          env.get("reason_code") == "prompt-budget-failed",
          str(env.get("reason_code")))
    check("exit5 ok false: never submitted", "submit" not in fake.order(),
          str(fake.order()))


def test_exit5_explicit_ok_true_proceeds():
    """A literal `ok: true` on exit 5 proceeds even with no adapter state."""
    budget = (5, {"ok": True,
                  "data": {"status": "BELOW_TARGET", "exit_code": 5,
                           "chars": 16500, "target_min": 19000}})
    env, db, fake, run_id, label = run_case(_full_script(budget),
                                            "s75039-oktrue")
    check("exit5 ok true: outcome ok", env.get("outcome") == "ok",
          str(env.get("outcome")) + " " + str(env.get("reason_code")))
    status, payload = budget_note(db, run_id, label + "-job")
    check("exit5 ok true: note written", (payload or {}).get("chars") == 16500,
          repr(status) + " " + repr(payload))


def test_exit4_over_max_unchanged():
    """Exit 4 keeps today's handling: prompt-over-max, nothing submitted."""
    env, db, fake, run_id, label = run_case(_full_script(BUDGET_OVER_MAX),
                                            "s75039-overmax")
    check("exit4: rejected", env.get("outcome") == "rejected",
          str(env.get("outcome")))
    check("exit4: reason prompt-over-max",
          env.get("reason_code") == "prompt-over-max",
          str(env.get("reason_code")))
    check("exit4: never submitted", "submit" not in fake.order(),
          str(fake.order()))


def test_exit0_proceeds_without_note():
    """Exit 0 proceeds as always and writes no band note."""
    env, db, fake, run_id, label = run_case(_full_script(BUDGET_OK),
                                            "s75039-ok")
    check("exit0: outcome ok", env.get("outcome") == "ok",
          str(env.get("outcome")))
    ev = env.get("evidence") or {}
    check("exit0: no band in evidence", ev.get("prompt_band") is None,
          repr(ev.get("prompt_band")))
    status, payload = budget_note(db, run_id, label + "-job")
    check("exit0: no band note", payload is None, repr(status))


TESTS = [
    test_exit5_pass_proceeds_with_note,
    test_exit5_refused_still_refuses,
    test_exit5_explicit_ok_false_refuses,
    test_exit5_explicit_ok_true_proceeds,
    test_exit4_over_max_unchanged,
    test_exit0_proceeds_without_note,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False, "%s: %s"
                  % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d S75-039 prompt-band tests passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    setup_module()
    sys.exit(main())
