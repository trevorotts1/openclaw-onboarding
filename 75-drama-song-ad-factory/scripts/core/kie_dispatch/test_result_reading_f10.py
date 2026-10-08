#!/usr/bin/env python3
"""F10 tests for kie_dispatch: result reading + placeholder refusal. Mocked.

Unit W-F-U10 (manual 02 Part F F10, High). Proves:
  1. a request whose JSON still carries an unfilled placeholder refuses at
     submission with reason REQUEST_PLACEHOLDER - before the ledger is
     touched and before any Skill 74 call (Kiesett's 9 x 422 loop must die);
  2. a task failing at poll 1 is reported at poll 1 - not later - with its
     task id, the outcome and a receipt row (dispatch evidence + ledger row).

Zero paid calls: Skill 74 is a fake runner, the ledger DB is a throwaway
file in a temp directory. Run: python3 core/kie_dispatch/test_result_reading_f10.py
"""
import importlib
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

import kie_dispatch as D            # noqa: E402  (package under test)
import spend_ledger as L            # noqa: E402  (sibling, same core/ tree)

MODULE = importlib.import_module("kie_dispatch.kie_dispatch")

FAILS = []


def _forbid_make_runner(*_a, **_k):
    """Zero paid calls: no test may ever spawn the real Skill 74."""
    raise AssertionError("real Skill 74 runner disabled in tests")


MODULE.make_runner = _forbid_make_runner


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


HEALTH_ACTIVE = (0, {"adapter_mode": "active", "state": "success"})
PREFLIGHT_OK = (0, {"state": "validated", "data": {"ok": True}})
BUDGET_OK = (0, {"state": "success",
                 "data": {"status": "OK", "exit_code": 0, "max": 20000}})
BASE_SCRIPT = {
    "health": HEALTH_ACTIVE,
    "preflight": PREFLIGHT_OK,
    "prompt-budget": BUDGET_OK,
}


def job_row(db, logical_key, attempt_id):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT state, final_outcome, actual_cost, remote_task_id FROM jobs "
            "WHERE logical_key=? AND attempt_id=?",
            (logical_key, attempt_id)).fetchone()
    finally:
        conn.close()


def dispatch_events(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT status, payload_json FROM events WHERE kind='dispatch'"
        ).fetchall()
    finally:
        conn.close()


def run_case(script, label, request=None, model="gpt-image-2-5-sunburst-text-to-image"):
    tmp = tempfile.mkdtemp(prefix="kie-f10-test-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-" + label, 10000)
    save_dir = os.path.join(tmp, "out")
    fake = Fake74(script)
    req = request if request is not None else {
        "model": "m", "input": {"prompt": "p" * 200}}
    env = D.dispatch(
        model=model,
        request=req,
        save_dir=save_dir, ledger_db=db, run_id="run-" + label,
        logical_key=label + "-job", attempt_id="att-1",
        estimated_cost=100,
        prompt="q" * 200,
        adapter_path=os.path.abspath(__file__),
        runner=fake)
    return env, db, fake, tmp


CLEAN_REQ = {
    "model": "m",
    "input": {"prompt": "Photorealistic still frame, warm light." * 6},
}


# ---- 1. placeholder refusal ------------------------------------------------

def test_placeholder_in_prompt_refused():
    req = {"model": "m",
           "input": {"prompt": "A shot of {{KEYFRAME_NAME}} at golden hour. "
                               "Warm light." * 4}}
    env, db, fake, _ = run_case(dict(BASE_SCRIPT), "ph1", request=req)
    check("ph: rejected", env["outcome"] == "rejected", str(env["outcome"]))
    check("ph: reason REQUEST_PLACEHOLDER",
          env["reason_code"] == "REQUEST_PLACEHOLDER",
          str(env["reason_code"]))
    check("ph: exit 5", D.EXIT[env["outcome"]] == 5)
    check("ph: NOTHING sent to Skill 74 (refused before submit)",
          fake.calls == [], "calls: %s" % fake.order())
    check("ph: path and token surfaced",
          env["evidence"].get("placeholder_token") == "{{"
          and "/input/prompt" in str(env["evidence"].get("placeholder_path")),
          str(env["evidence"]))
    check("ph: generated false", env["evidence"].get("generated") is False)


def test_placeholder_refused_before_ledger_reserve():
    """The refusal happens before plan/reserve: no jobs row exists at all."""
    req = {"model": "m",
           "input": {"prompt": "Portrait of <TODO your subject here>." * 8}}
    env, db, fake, _ = run_case(dict(BASE_SCRIPT), "ph2", request=req)
    check("ph-before-ledger: rejected", env["outcome"] == "rejected")
    check("ph-before-ledger: no Skill 74 call", fake.calls == [])
    row = job_row(db, "ph2-job", "att-1")
    check("ph-before-ledger: no ledger row reserved",
          row is None, str(row))
    check("ph-before-ledger: no dispatch evidence written either",
          dispatch_events(db) == [], str(dispatch_events(db)))


def test_placeholder_tokens_matrix():
    """Each incident token refuses; ordinary prose passes."""
    bad = [
        ("curly-open", "{in}/input/prompt".replace("{in}", ""),
         "Music bed over {{LINE_3}} then out."),
        ("angle-todo", "/input/negative_tags",
         "Style notes: <TODO fill from choice card>"),
        ("angle-placeholder", "/input/lyrics",
         "Verse: <placeholder>"),
        ("bare-todo", "/input/prompt",
         "Shot of TODO at the shop door."),        # Kiesett incident token
        ("bare-placeholder", "/input/style",
         "PLACEHOLDER until the card is answered."),
        ("bare-keyframe", "/input/prompt",
         "KEYFRAME: name the subject here."),      # Kiesett incident token
    ]
    for name, path, frag in bad:
        req = {"model": "m",
               "input": {"prompt": ("Warm daylight. " * 40) + frag}}
        env, db, fake, _ = run_case(dict(BASE_SCRIPT), "token-" + name,
                                    request=req)
        check("token %s: rejected" % name, env["outcome"] == "rejected",
              str(env["outcome"]))
        check("token %s: reason REQUEST_PLACEHOLDER" % name,
              env["reason_code"] == "REQUEST_PLACEHOLDER")
        check("token %s: nothing sent" % name, fake.calls == [])
    # Ordinary prose that must NOT trip the scan (no false positives).
    good = [
        ("prose-angle", {"prompt": "A 9:16 frame at <golden hour>, warm light. "
                                   "No text anywhere." * 8}),
        ("prose-braces-as-json", {"prompt": r'Return JSON like {"ok": true}. '
                                            "Warm daylight scene. " * 8}),
        ("nested-lists", {"prompts": ["Warm daylight. " * 20,
                                      "Second angle, same wardrobe. " * 20]}),
    ]
    for name, inp in good:
        req = {"model": "m", "input": inp}
        env, db, fake, _ = run_case(dict(BASE_SCRIPT), "good-" + name,
                                    request=req)
        check("prose %s: not refused by placeholder scan" % name,
              not (env["outcome"] == "rejected"
                   and env["reason_code"] == "REQUEST_PLACEHOLDER"),
              "%s/%s" % (env["outcome"], env["reason_code"]))


def test_prose_request_reaches_submit():
    """Guard test: a clean request still passes the new gate and dispatches."""
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "task-clean"}),
        "wait": (0, {"state": "success", "task_id": "task-clean",
                     "credits_consumed": 7}),
        "save": (0, {"state": "success", "task_id": "task-clean",
                     "saved_paths": ["/tmp/f10-clean.png"]}),
    })
    env, db, fake, _ = run_case(script, "cleanflow", request=CLEAN_REQ)
    check("clean: outcome ok", env["outcome"] == "ok", str(env["outcome"]))
    check("clean: full stage order", fake.order() == [
        "health", "preflight", "prompt-budget", "submit", "wait", "save"],
        str(fake.order()))


# ---- 2. one-poll failure reporting -----------------------------------------

def test_failure_on_first_poll_reported_immediately():
    """Poll 1 says fail -> reported at poll 1: evidence row + task id, saved
    files never attempted, ledger failed right away. Exactly ONE wait call."""
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "task-422"}),
        "wait": (0, {"state": "fail",
                     "task_id": "task-422",
                     "error": {"code": "validation_failed",
                               "msg": "request carries an unfilled "
                                      "placeholder"}}),
    })
    env, db, fake, _ = run_case(script, "pollfail")
    check("pollfail: rejected", env["outcome"] == "rejected",
          str(env["outcome"]))
    check("pollfail: reason kie-run-failed",
          env["reason_code"] == "kie-run-failed", str(env["reason_code"]))
    check("pollfail: reported at poll 1 (exactly one wait call)",
          fake.order().count("wait") == 1, str(fake.order()))
    check("pollfail: no save, no second poll, no retry",
          fake.order() == ["health", "preflight", "prompt-budget",
                           "submit", "wait"], str(fake.order()))
    check("pollfail: failure_poll marker is 1",
          env["evidence"].get("failure_poll") == 1, str(env["evidence"]))
    check("pollfail: task id in the outcome",
          env["evidence"].get("task_id") == "task-422", str(env["evidence"]))
    check("pollfail: error surfaced",
          env["evidence"].get("error", {}).get("code") == "validation_failed",
          str(env["evidence"]))
    evs = dispatch_events(db)
    check("pollfail: receipt row written (dispatch evidence, fail)",
          len(evs) == 1 and evs[0][0] == "fail", str(evs))
    check("pollfail: receipt row names the task id",
          "task-422" in evs[0][1], str(evs[0][1]))
    row = job_row(db, "pollfail-job", "att-1")
    check("pollfail: ledger settled failed immediately",
          row and row[0] == "reconciled" and row[1] == "failed", str(row))
    check("pollfail: remote task id stored on the row",
          row and row[3] == "task-422", str(row))


def test_failure_after_second_poll_answer_still_single_report():
    """Adapter answers running once, fail after - still one report, at the
    poll where fail was first read."""
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "task-slow"}),
        "wait": (0, {"state": "fail", "task_id": "task-slow",
                     "error": {"code": "generation_failed"}}),
    })
    env, db, fake, _ = run_case(script, "pollfail2")
    check("pollfail2: rejected and reported once",
          env["outcome"] == "rejected"
          and fake.order().count("wait") == 1, str(fake.order()))
    row = job_row(db, "pollfail2-job", "att-1")
    check("pollfail2: row failed not unknown",
          row and row[0] == "reconciled" and row[1] == "failed", str(row))


def test_placeholder_still_refused_with_no_adapter():
    """Order check: the placeholder gate fires before the adapter search."""
    req = {"model": "m",
           "input": {"prompt": "Text {{UNFILLED}} in frame. Warm shot." * 6}}
    tmp = tempfile.mkdtemp(prefix="kie-f10-order-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-order", 10000)
    fake = Fake74({})
    env = D.dispatch(
        model="m", request=req, save_dir=os.path.join(tmp, "out"),
        ledger_db=db, run_id="run-order", logical_key="order-job",
        attempt_id="att-1", estimated_cost=100, prompt="q" * 200,
        adapter_path=None, runner=fake)
    check("order: REQUEST_PLACEHOLDER wins over adapter-not-found",
          env["reason_code"] == "REQUEST_PLACEHOLDER",
          str(env["reason_code"]))
    check("order: no Skill 74 call attempted", fake.calls == [])


def main():
    tests = [
        test_placeholder_in_prompt_refused,
        test_placeholder_refused_before_ledger_reserve,
        test_placeholder_tokens_matrix,
        test_prose_request_reaches_submit,
        test_failure_on_first_poll_reported_immediately,
        test_failure_after_second_poll_answer_still_single_report,
        test_placeholder_still_refused_with_no_adapter,
    ]
    for t in tests:
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
    print("all %d F10 tests passed" % len(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())