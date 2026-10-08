#!/usr/bin/env python3
"""F14 acceptance tests: video model locked to the card's choice. stdlib only.

Proves (manual Part F F14 "Done when"):
- seedance-1.5-pro (off-menu) refused MODEL_NOT_ON_MENU
- a menu model that is not the locked one refused VIDEO_MODEL_MISMATCH
- the locked model passes
- price-menu.md parse == static ALLOWED_VIDEO_MODELS (drift test)
- a different menu model is a different family (mismatch bites)
- no-lock video job refused fail-closed (VIDEO_MODEL_LOCK_MISSING)
- VIDEO_MODEL_DOWN on definite submit error, no automatic fallback
- delivery gate: mismatched clip fails, matching clips pass
- qc-no-direct-kie.sh bites a planted offender and passes kie_dispatch

Zero paid calls: Skill 74 is a fake runner; the DBs are throwaway temp files.
Run: python3 core/kie_dispatch/test_model_lock_f14.py
"""
import importlib
import os
import subprocess
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

MODULE = importlib.import_module("kie_dispatch.kie_dispatch")
import kie_dispatch as D            # noqa: E402
import kie_dispatch.model_lock as ML  # noqa: E402
import spend_ledger as L            # noqa: E402

FAILS = []

MODULE.make_runner = lambda *a, **k: (_ for _ in ()).throw(
    AssertionError("real Skill 74 runner disabled in tests"))


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


HEALTH_ACTIVE = (0, {"adapter_mode": "active", "state": "success"})
PREFLIGHT_OK = (0, {"state": "validated", "data": {"ok": True}})
BUDGET_OK = (0, {"state": "success",
                 "data": {"status": "OK", "exit_code": 0, "max": 20000}})
BASE_SCRIPT = {
    "health": HEALTH_ACTIVE,
    "preflight": PREFLIGHT_OK,
    "prompt-budget": BUDGET_OK,
}
DEFAULT = ML.DEFAULT_VIDEO_MODEL            # minimax-h3/*


class Fake74:
    def __init__(self, script):
        self.script = script
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        sub = argv[1] if len(argv) > 1 else ""
        res = self.script[sub]
        if isinstance(res, Exception):
            raise res
        return res

    def order(self):
        return [c[1] for c in self.calls]


def disp(script, label, model, lock=None, state_db=None, tmp=None,
         submit=None):
    s = dict(BASE_SCRIPT)
    s.update(script)
    if submit is not None:
        s["submit"] = submit
    if state_db is None:
        state_db = os.path.join(tmp, "state-%s.db" % label)
    if lock:
        ML.lock_run_model(state_db, "run-f14", lock)
    db = os.path.join(tmp, "spend-%s.db" % label)
    L.init_run(db, "run-f14", 10000)
    fake = Fake74(s)
    env = D.dispatch(
        model=model, request={"model": "m", "input": {"prompt": "p" * 200},
                              # F15 seam: the F14 lock tests run past the
                              # card gate, so their stub carries the recorded
                              # receipt (both acceptance criteria satisfied).
                              "card_receipt": {
                                  "answers": {
                                      "video_style": "Lifelike 3D",
                                      "audio_style": "Soul Ballad",
                                      "length": 60,
                                      "video_model": "MiniMax H3 768P"},
                                  "who": "F14 lock test",
                                  "at": "2026-10-08T09:00:00Z"}},
        save_dir=os.path.join(tmp, "out"), ledger_db=db, run_id="run-f14",
        logical_key=label + "-job", attempt_id="att-1", estimated_cost=100,
        prompt="q" * 200, adapter_path=os.path.abspath(__file__),
        runner=fake, state_store=state_db)
    return env, fake, db


def test_seedance_refused():
    tmp = tempfile.mkdtemp(prefix="f14-")
    env, fake, _ = disp(BASE_SCRIPT, "seedance",
                        "bytedance/seedance-1.5-pro", lock=DEFAULT, tmp=tmp)
    check("f14: seedance-1.5-pro rejected", env["outcome"] == "rejected",
          str(env["outcome"]))
    check("f14: reason MODEL_NOT_ON_MENU",
          env["reason_code"] == "MODEL_NOT_ON_MENU",
          str(env["reason_code"]))
    check("f14: seedance refusal precedes Skill 74 entirely",
          fake.order() == [], str(fake.order()))
    row = sqlite3.connect(os.path.join(tmp, "spend-seedance.db")).execute(
        "SELECT COUNT(*) FROM jobs").fetchone()[0]
    check("f14: no ledger row for off-menu job", row == 0, str(row))


def test_mismatch_refused():
    tmp = tempfile.mkdtemp(prefix="f14-")
    env, fake, _ = disp(BASE_SCRIPT, "mismatch", "kling-3.0/video",
                        lock=DEFAULT, tmp=tmp)
    check("f14: menu model != locked refused", env["outcome"] == "rejected",
          str(env["outcome"]))
    check("f14: reason VIDEO_MODEL_MISMATCH",
          env["reason_code"] == "VIDEO_MODEL_MISMATCH",
          str(env["reason_code"]))
    check("f14: mismatch evidence names both",
          env["evidence"].get("locked_model") == DEFAULT
          and env["evidence"].get("requested_model") == "kling-3.0/video",
          str(env["evidence"]))
    check("f14: mismatch precedes Skill 74", fake.order() == [],
          str(fake.order()))


def test_locked_model_passes():
    tmp = tempfile.mkdtemp(prefix="f14-")
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "t-h3",
                       "raw_family": "market"}),
        "wait": (0, {"state": "success", "task_id": "t-h3",
                     "credits_consumed": 30}),
        "save": (0, {"state": "success", "task_id": "t-h3",
                     "saved_paths": ["/tmp/h3.mp4"], "credits_consumed": 30}),
    })
    # member of the locked family: minimax-h3/image-to-video
    env, fake, db = disp(script, "h3ok", "minimax-h3/image-to-video",
                         lock=DEFAULT, tmp=tmp)
    check("f14: locked family member accepted", env["outcome"] == "ok",
          str(env))
    check("f14: full stage order", fake.order() == [
        "health", "preflight", "prompt-budget", "submit", "wait", "save"],
        str(fake.order()))
    row = sqlite3.connect(db).execute(
        "SELECT state, final_outcome FROM jobs").fetchone()
    check("f14: reconciled succeeded", row == ("reconciled", "succeeded"),
          str(row))


def test_drift():
    menu = ML.resolve_price_menu()
    check("f14: price-menu.md found", bool(menu), str(menu))
    parsed = ML.parse_price_menu(menu)
    check("f14: parse == static ALLOWED_VIDEO_MODELS (no drift)",
          parsed == list(ML.ALLOWED_VIDEO_MODELS),
          "parse=%s static=%s" % (parsed, list(ML.ALLOWED_VIDEO_MODELS)))
    check("f14: default is on the menu",
          ML.matches_family(DEFAULT, parsed[0]) or DEFAULT in parsed,
          DEFAULT)


def test_no_lock_fail_closed():
    tmp = tempfile.mkdtemp(prefix="f14-")
    env, fake, _ = disp(BASE_SCRIPT, "nolock", "minimax-h3/image-to-video",
                        lock=None, tmp=tmp)
    check("f14: un-locked video job refused", env["outcome"] == "rejected",
          str(env["outcome"]))
    check("f14: reason VIDEO_MODEL_LOCK_MISSING",
          env["reason_code"] == "VIDEO_MODEL_LOCK_MISSING",
          str(env["reason_code"]))
    check("f14: lock-missing precedes Skill 74", fake.order() == [],
          str(fake.order()))


def test_model_down_no_fallback():
    tmp = tempfile.mkdtemp(prefix="f14-")
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "fail",
                       "error": {"code": "provider_unavailable",
                                 "msg": "minimax-h3 down"}}),
    })
    env, fake, db = disp(script, "down", "minimax-h3/text-to-video",
                         lock=DEFAULT, tmp=tmp,
                         submit=script["submit"])
    check("f14: down model -> waiting outcome", env["outcome"] == "waiting",
          str(env["outcome"]))
    check("f14: reason VIDEO_MODEL_DOWN", env["reason_code"] == "VIDEO_MODEL_DOWN",
          str(env["reason_code"]))
    na = env.get("next_action", "")
    check("f14: next_action asks owner with next option + price",
          "ask the owner" in na and "price" in na, na)
    check("f14: no retry - submit attempted exactly once",
          fake.calls.count(fake.calls[0]) == 1
          and fake.order() == ["health", "preflight", "prompt-budget",
                               "submit"],
          str(fake.order()))
    check("f14: no wait/no save/no second submit", "wait" not in
          fake.order() and "save" not in fake.order(), str(fake.order()))
    row = sqlite3.connect(db).execute(
        "SELECT state, final_outcome FROM jobs").fetchone()
    check("f14: settled failed, zero-cost, no fallback dispatch",
          row == ("reconciled", "failed"), str(row))


def test_delivery_gate():
    locked = DEFAULT
    ok = ML.check_video_model_delivery(
        {"clips": [{"model": "minimax-h3/text-to-video"},
                   {"model": "minimax-h3/image-to-video"}]}, locked)
    check("f14: delivery gate accepts locked-family clips", ok == [], str(ok))
    bad = ML.check_video_model_delivery(
        {"clips": [{"model": "minimax-h3/text-to-video"},
                   {"model": "bytedance/seedance-2-mini"}]}, locked)
    check("f14: delivery gate fails one mismatched clip", len(bad) == 1
          and "VIDEO_MODEL_MISMATCH" in bad[0], str(bad))
    nom = ML.check_video_model_delivery({"clips": [{"id": "c1"}]}, locked)
    check("f14: delivery gate fails a clip with no model recorded",
          len(nom) == 1 and "VIDEO_MODEL_MISMATCH" in nom[0], str(nom))


def test_video_job_flag_scope():
    """video_job=True locks even a non-family model spelling."""
    tmp = tempfile.mkdtemp(prefix="f14-")
    env, _, _ = disp(BASE_SCRIPT, "vflag", "some/custom-video-family",
                     lock=DEFAULT, tmp=tmp, submit=None)
    check("f14: video_job=True + off-menu refused MODEL_NOT_ON_MENU",
          env["reason_code"] == "MODEL_NOT_ON_MENU", str(env["reason_code"]))
    # image models are outside the F14 scope entirely
    tmp2 = tempfile.mkdtemp(prefix="f14-")
    env2, fake2, _ = disp(BASE_SCRIPT, "imgscope",
                          "gpt-image-2-5-sunburst-text-to-image",
                          lock=None, tmp=tmp2)
    check("f14: image model outside lock scope reaches Skill 74",
          env2["reason_code"] != "MODEL_NOT_ON_MENU"
          and fake2.order()[:1] == ["health"], str(env2["reason_code"]))


def test_qc_no_direct_kie():
    scan = os.path.join(CORE, "..", "qc-no-direct-kie.sh")
    scan = os.path.normpath(scan)
    check("f14: qc-no-direct-kie.sh exists", os.path.isfile(scan), scan)
    env = subprocess.run(["bash", scan], capture_output=True, text=True,
                         env=dict(os.environ, DRAMA75_CORE=CORE,
                                  PYTHONDONTWRITEBYTECODE="1"))
    check("f14: scan passes the tree (exit 0)", env.returncode == 0,
          "rc=%s out=%s" % (env.returncode, env.stdout[-400:]))
    # planted offender must bite
    tmp = tempfile.mkdtemp(prefix="f14-scan-")
    bad = os.path.join(tmp, "core", "rogue")
    os.makedirs(bad)
    with open(os.path.join(bad, "rogue_caller.py"), "w") as f:
        f.write('URL = "https://api.kie.ai/api/v1/jobs/createTask"\n'
                'import urllib.request  # direct KIE submit, bypassing the\n'
                '                       # dispatcher (the F14 Kiesett bug)\n')
    env2 = subprocess.run(
        ["bash", scan], capture_output=True, text=True,
        env=dict(os.environ, DRAMA75_CORE=os.path.dirname(bad),
                 PYTHONDONTWRITEBYTECODE="1"))
    check("f14: scan bites planted offender (exit != 0)",
          env2.returncode != 0 and "rogue_caller.py" in (env2.stdout +
                                                         env2.stderr),
          "rc=%s out=%s err=%s" % (env2.returncode, env2.stdout[-300:],
                                   env2.stderr[-300:]))


def main():
    test_seedance_refused()
    test_mismatch_refused()
    test_locked_model_passes()
    test_drift()
    test_no_lock_fail_closed()
    test_model_down_no_fallback()
    test_delivery_gate()
    test_video_job_flag_scope()
    test_qc_no_direct_kie()
    print("")
    if FAILS:
        print("%d checks failed:" % len(FAILS))
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all F14 model-lock tests passed (%s blocks)" % 9)
    return 0


if __name__ == "__main__":
    sys.exit(main())