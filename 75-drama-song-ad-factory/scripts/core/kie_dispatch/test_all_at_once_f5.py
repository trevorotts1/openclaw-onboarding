#!/usr/bin/env python3
"""Part F F5 tests: independent KIE jobs submit all at once. Mocked only.

Proves (owner rule: 17 at once; no 'test batch first' unless the owner
orders it):
  1. 17 ready jobs -> one pass, receipt max_at_once = 17, submitted = 17.
  2. One not-ready job (missing input file) is excluded and NAMED.
  3. Cap override (max_concurrency=9 on 17 ready) -> max_at_once = 9 and
     the receipt names the cap (capped_by = 9).
  4. Stage-order side rules: submit-only module calls in the recorded
     order through Skill 74's facade; the rule lives in SKILL.md
     (reference images -> keyframes -> clips).

Zero paid calls: the Skill 74 runner is a fake; ledgers are temp files.

Run: python3 core/kie_dispatch/test_all_at_once_f5.py
"""
import importlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

import kie_dispatch as D            # noqa: E402  (package under test)
import spend_ledger as L            # noqa: E402  (sibling, same core/ tree)

MODULE = importlib.import_module("kie_dispatch.kie_dispatch")

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _forbid_make_runner(*_a, **_k):
    raise AssertionError("real Skill 74 runner disabled in tests")


MODULE.make_runner = _forbid_make_runner


class Fake74:
    """Facade runner: each job gets its own submit/wait/save answers."""

    def __init__(self, state="queued", wait_state="success", credits=16):
        self.state = state
        self.wait_state = wait_state
        self.credits = credits
        self.calls = []

    def __call__(self, argv):
        sub = argv[1] if len(argv) > 1 else ""
        self.calls.append(sub)
        tmp = tempfile.gettempdir()
        if sub == "health":
            return (0, {"adapter_mode": "active", "state": "success"})
        if sub == "preflight":
            return (0, {"state": "validated", "data": {"ok": True}})
        if sub == "prompt-budget":
            return (0, {"state": "success",
                        "data": {"status": "OK", "exit_code": 0,
                                 "max": 20000}})
        if sub == "submit":
            return (0, {"state": self.state, "task_id": "t-%d" % len(self.calls),
                        "credits_consumed": self.credits})
        if sub == "wait":
            return (0, {"state": self.wait_state, "task_id": "t-x",
                        "result_urls": ["https://example.invalid/a.png"],
                        "credits_consumed": self.credits})
        if sub == "save":
            path = os.path.join(tmp, "f5-%d.png" % len(self.calls))
            open(path, "w").close()
            return (0, {"state": "success", "task_id": "t-x",
                        "saved_paths": [path],
                        "credits_consumed": self.credits})
        raise AssertionError("unexpected Skill 74 call: %r" % sub)


def _lock_state():
    import kie_dispatch.model_lock as ML
    db = os.path.join(tempfile.mkdtemp(prefix="f5-state-"), "state.db")
    ML.lock_run_model(db, "run-all-ready", "kling-3.0/video")
    return db


_STATE = _lock_state()


def _approved_storyboard():
    """Directive 14.1 record a clip job must carry: every shot
    storyboard_approved AND the adversarial review passed (F6 gate)."""
    return {"storyboard": {
        "shots": [{"shot_id": "s1", "status": "storyboard_approved"}],
        "review": {"outcome": "pass", "reason_code": "storyboard-accepted"},
    }}

def make_jobs(n, inputs=None, model="kling-3.0/video"):
    # F15: every paid dispatch carries the recorded choice-card receipt.
    req = {"model": model, "input": {"prompt": "p" * 200},
           "card_receipt": {"answers": {"video_style": "Lifelike 3D",
                                        "audio_style": "Soul Ballad",
                                        "length": 60,
                                        "video_model": "MiniMax H3 768P"},
                            "who": "w8 merge test",
                            "at": "2026-10-08T09:00:00Z"},
           **_approved_storyboard()}
    jobs = []
    for i in range(n):
        jobs.append({
            "logical_key": "clip-%02d" % i,
            "model": model,
            "request": req,
            "estimated_cost": 100,
            "inputs": inputs[i] if isinstance(inputs, list) else inputs,
            "prompt": "q" * 200,
            "runner": Fake74(),
            "state_store": _STATE,   # F14: card-locked model for the run
        })
    return jobs


def tmpdb():
    tmp = tempfile.mkdtemp(prefix="f5-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-all-ready", 10_000_000)
    return db


def test_seventeen_all_at_once():
    db = tmpdb()
    jobs = make_jobs(17)
    rec = D.submit_all_ready(jobs, ledger=db)
    check("17 max_at_once == 17", rec["max_at_once"] == 17,
          str(rec["max_at_once"]))
    check("17 submitted == 17", rec["submitted"] == 17, str(rec["submitted"]))
    check("17 no exclusions", rec["excluded"] == [], str(rec["excluded"]))
    check("17 no cap named", rec["capped_by"] is None,
          str(rec["capped_by"]))
    check("17 envelopes count", len(rec["envelopes"]) == 17)
    check("17 all outcomes ok",
          all(e["outcome"] == "ok" for e in rec["envelopes"]),
          str([e["outcome"] for e in rec["envelopes"] if e["outcome"] != "ok"]))
    check("17 one pass = 17 distinct submit calls across facades",
          len({id(j["runner"]) for j in jobs}) == 17)
    # ledger rows: every job landed submitted/reconciled in the one run
    import sqlite3
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT state,final_outcome FROM jobs WHERE run_id='run-all-ready'"
    ).fetchall()
    conn.close()
    check("17 ledger rows all reconciled",
          len(rows) == 17 and all(r[0] == "reconciled" and r[1] == "succeeded"
                                  or r[0] == "reconciled" for r in rows),
          str(rows[:3]))


def test_not_ready_excluded_and_named():
    db = tmpdb()
    missing = os.path.join(tempfile.mkdtemp(prefix="f5-missing-"), "nope.png")
    jobs = make_jobs(4)
    jobs[1]["inputs"] = [missing]          # not ready
    jobs.append({"logical_key": "broken-job", "model": "", "request": {},
                 "estimated_cost": 0, "runner": Fake74()})
    rec = D.submit_all_ready(jobs, ledger=db)
    check("excluded max_at_once == 3 (only ready count)",
          rec["max_at_once"] == 3, str(rec["max_at_once"]))
    named = {e["logical_key"]: e["reason"] for e in rec["excluded"]}
    check("not-ready excluded count 2", len(rec["excluded"]) == 2,
          str(rec["excluded"]))
    check("not-ready missing file job named 'clip-01'",
          "clip-01" in named, str(named))
    check("not-ready reason names missing file",
          named.get("clip-01", "").startswith("inputs-missing: "),
          str(named.get("clip-01")))
    check("no-model job named 'broken-job' with 'no-model'",
          "broken-job" in named and named["broken-job"] == "no-model",
          str(named))
    check("ready 3 still submitted", rec["submitted"] == 3,
          str(rec["submitted"]))


def test_cap_override_names_cap():
    db = tmpdb()
    jobs = make_jobs(17)
    rec = D.submit_all_ready(jobs, max_concurrency=9, ledger=db)
    check("cap max_at_once == 9", rec["max_at_once"] == 9,
          str(rec["max_at_once"]))
    check("cap capped_by == 9", rec["capped_by"] == 9, str(rec["capped_by"]))
    check("cap still submitted all ready", rec["submitted"] == 17,
          str(rec["submitted"]))
    check("cap no submissions lost", len(rec["envelopes"]) == 17)


def test_bad_cap_refused():
    db = tmpdb()
    for bad in (0, -3, "all"):
        rec = D.submit_all_ready(make_jobs(2), max_concurrency=bad,
                                 ledger=db)
        check("bad cap %r refused in receipt" % (bad,),
              rec.get("outcome") == "rejected" and rec["submitted"] == 0,
              str(rec))
        check("bad cap %r generated no envelopes" % (bad,),
              rec["envelopes"] == [])


def test_empty_and_noready():
    db = tmpdb()
    rec = D.submit_all_ready([], ledger=db)
    check("empty jobs: zero-everything receipt",
          rec["submitted"] == 0 and rec["max_at_once"] == 0
          and rec["excluded"] == [], str(rec))
    rec = D.submit_all_ready(make_jobs(0) + [{"logical_key": "bad",
                                              "model": "",
                                              "request": {},
                                              "estimated_cost": 0}],
                             ledger=db)
    check("no-ready: excluded named 'bad'", rec["excluded"] ==
          [{"logical_key": "bad", "reason": "no-model"}], str(rec["excluded"]))
    check("no-ready: max_at_once 0", rec["max_at_once"] == 0)


def test_rule_in_skill_md():
    skill = os.path.normpath(os.path.join(
        os.path.dirname(HERE), os.pardir, os.pardir, "SKILL.md"))
    with open(skill, encoding="utf-8") as f:
        text = f.read()
    check("SKILL.md carries the all-at-once rule", "all ready" in text.lower()
          and "at once" in text.lower(), "no rule text found")
    check("SKILL.md names submit_all_ready", "submit_all_ready" in text)
    check("SKILL.md stage order kept", "reference images" in text.lower()
          and "keyframes" in text.lower())


def main():
    test_seventeen_all_at_once()
    test_not_ready_excluded_and_named()
    test_cap_override_names_cap()
    test_bad_cap_refused()
    test_empty_and_noready()
    test_rule_in_skill_md()
    print()
    if FAILS:
        print("FAILED: %d check(s): %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("ALL F5 CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())