#!/usr/bin/env python3
"""Mocked-Skill-74 tests for kie_dispatch: every plan 5.4 outcome. stdlib only.

Outcomes covered (one test each):
  ok | shadow-skip (+ off) | preflight shortfall | prompt over max |
  submit fail | wait timeout keeps task id | unknown stops with no retry |
  submit crash | submit skipped | adapter missing

Zero paid calls: Skill 74 is a fake runner, the module holds no HTTP client of
its own, and the ledger DBs are throwaway files in a temp directory.

Run: python3 core/kie_dispatch/test_kie_dispatch.py
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


# Held for the whole run: any dispatch that forgot its fake runner fails here.
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

    def argv_of(self, sub):
        for c in self.calls:
            if len(c) > 1 and c[1] == sub:
                return c
        return None


def job_row(db, logical_key, attempt_id):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT state, final_outcome, actual_cost, remote_task_id FROM jobs "
            "WHERE logical_key=? AND attempt_id=?",
            (logical_key, attempt_id)).fetchone()
    finally:
        conn.close()


def run_case(script, label, adapter_path=None, prompt=None, cost=100,
             model="gpt-image-2-5-sunburst-text-to-image", request=None,
             no_card=False):
    tmp = tempfile.mkdtemp(prefix="kie-dispatch-test-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-" + label, 10000)
    save_dir = os.path.join(tmp, "out")
    fake = Fake74(script)
    # F15 (owner order 2026-10-08): every paid dispatch carries the recorded
    # choice-card receipt; a request without one refuses CARD_UNANSWERED
    # before the ledger. The default stub request gains the stamp; a case
    # that needs the refusal passes no_card=True.
    if no_card:
        req = {"model": "m", "input": {"prompt": "p" * 200}}
    else:
        req = request if request is not None else {
            "model": "m", "input": {"prompt": "p" * 200}}
        if "card_receipt" not in req and "run_state" not in req:
            req = dict(req, card_receipt=STAMPED_CARD)
    env = D.dispatch(
        model=model,
        request=req,
        save_dir=save_dir, ledger_db=db, run_id="run-" + label,
        logical_key=label + "-job", attempt_id="att-1",
        estimated_cost=cost,
        prompt=("q" * 200) if prompt is None else prompt,
        adapter_path=adapter_path or os.path.abspath(__file__),
        runner=fake)
    return env, db, fake, tmp


#: The recorded card receipt the stub runs carry (the four F15 answers,
#: stamped). One dict, reused; dispatch only reads it.
STAMPED_CARD = {"answers": {"video_style": "Lifelike 3D",
                            "audio_style": "Soul Ballad",
                            "length": 60,
                            "video_model": "MiniMax H3 768P"},
                "who": "W1 dispatch test",
                "at": "2026-10-08T09:00:00Z"}


def test_f15_unanswered_card_refuses_dispatch():
    """F15 done-when: a run without the four card answers refuses ANY paid
    job, fail-closed, and reserves nothing."""
    env, db, fake, tmp = run_case(BASE_SCRIPT, "f15-nocard", no_card=True)
    check("F15 no card: outcome waiting", env.get("outcome") == "waiting",
          repr(env.get("outcome")))
    check("F15 no card: reason CARD_UNANSWERED",
          env.get("reason_code") == "CARD_UNANSWERED",
          repr(env.get("reason_code")))
    check("F15 no card: nothing generated",
          (env.get("evidence") or {}).get("generated") is False,
          repr(env.get("evidence")))
    check("F15 no card: fake 74 never called",
          fake.calls == [] if hasattr(fake, "calls") else True,
          repr(getattr(fake, "calls", "n/a")))
    conn = sqlite3.connect(db)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE logical_key=?",
            ("f15-nocard-job",)).fetchone()[0]
    finally:
        conn.close()
    check("F15 no card: ledger reserved nothing", n == 0, str(n))


HEALTH_ACTIVE = (0, {"adapter_mode": "active", "state": "success"})
PREFLIGHT_OK = (0, {"state": "validated", "data": {"ok": True}})
BUDGET_OK = (0, {"state": "success",
                 "data": {"status": "OK", "exit_code": 0, "max": 20000}})
BASE_SCRIPT = {
    "health": HEALTH_ACTIVE,
    "preflight": PREFLIGHT_OK,
    "prompt-budget": BUDGET_OK,
}


def test_ok():
    tmp = tempfile.mkdtemp(prefix="kie-ok-")
    shot = os.path.join(tmp, "shot.png")
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "task-1",
                       "raw_family": "market"}),
        "wait": (0, {"state": "success", "task_id": "task-1",
                     "raw_family": "market",
                     "result_urls": ["https://example.invalid/a.png"],
                     "credits_consumed": 16}),
        "save": (0, {"state": "success", "task_id": "task-1",
                     "saved_paths": [shot], "credits_consumed": 16}),
    })
    env, db, fake, _ = run_case(script, "ok")
    check("ok: outcome ok", env["outcome"] == "ok", str(env["outcome"]))
    check("ok: reason KIE_DISPATCH_OK", env["reason_code"] == "KIE_DISPATCH_OK")
    check("ok: exit 0", D.EXIT[env["outcome"]] == 0)
    check("ok: stage order health->preflight->budget->submit->wait->save",
          fake.order() == ["health", "preflight", "prompt-budget",
                           "submit", "wait", "save"],
          str(fake.order()))
    w_argv = fake.argv_of("wait")
    check("ok: wait got --task-id task-1",
          w_argv and "task-1" in w_argv, str(w_argv))
    check("ok: wait budget 300 for image model",
          w_argv and w_argv[w_argv.index("--timeout") + 1] == "300",
          str(w_argv))
    row = job_row(db, "ok-job", "att-1")
    check("ok: ledger reconciled/succeeded",
          row and row[0] == "reconciled" and row[1] == "succeeded", str(row))
    check("ok: actual cost recorded", row[2] == 16, str(row[2]))
    check("ok: remote task id stored", row[3] == "task-1", str(row[3]))
    check("ok: generated true", env["evidence"].get("generated") is True)
    check("ok: task id kept", env["evidence"].get("task_id") == "task-1")
    check("ok: files saved", len(env["evidence"].get("saved_paths") or []) == 1)


def test_video_wait_budget():
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "t-vid",
                       "raw_family": "market"}),
        "wait": (0, {"state": "success", "task_id": "t-vid",
                     "raw_family": "market", "credits_consumed": 30}),
        "save": (0, {"state": "success", "task_id": "t-vid",
                     "saved_paths": ["/tmp/x.mp4"], "credits_consumed": 30}),
    })
    env, db, fake, _ = run_case(script, "vidwait",
                                model="kling-2.6/image-to-video")
    w_argv = fake.argv_of("wait")
    check("video: wait budget 1200",
          w_argv and w_argv[w_argv.index("--timeout") + 1] == "1200",
          str(w_argv))
    check("video: outcome ok", env["outcome"] == "ok", str(env["outcome"]))


def test_request_timeout_overrides():
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "t-ovr"}),
        "wait": (0, {"state": "success", "task_id": "t-ovr",
                     "credits_consumed": 5}),
        "save": (0, {"state": "success", "task_id": "t-ovr",
                     "saved_paths": ["/tmp/y.png"]}),
    })
    env, db, fake, _ = run_case(
        script, "ovrwait",
        request={"model": "m", "input": {"prompt": "p" * 200}, "timeout": 99})
    w_argv = fake.argv_of("wait")
    check("override: wait budget from request.timeout=99",
          w_argv and w_argv[w_argv.index("--timeout") + 1] == "99",
          str(w_argv))
    check("override: evidence wait_timeout_s 99",
          env["evidence"].get("wait_timeout_s") == 99,
          str(env["evidence"].get("wait_timeout_s")))


def test_wait_timeout_keeps_task_id():
    """C2 acceptance: wait running+timeout -> unknown WITH task id recorded."""
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "task-42",
                       "raw_family": "market"}),
        "wait": (0, {"state": "running", "task_id": "task-42",
                     "error": {"code": "timeout",
                               "msg": "deadline 300s reached"}}),
    })
    env, db, fake, _ = run_case(script, "waittimeout",
                                model="kling-2.6/image-to-video")
    check("wait-timeout: waiting", env["outcome"] == "waiting",
          str(env["outcome"]))
    check("wait-timeout: reason unknown-outcome-no-retry",
          env["reason_code"] == "unknown-outcome-no-retry",
          str(env["reason_code"]))
    check("wait-timeout: order submit then wait, no save",
          fake.order() == ["health", "preflight", "prompt-budget",
                           "submit", "wait"],
          str(fake.order()))
    check("wait-timeout: submit called before wait",
          fake.order().index("submit") < fake.order().index("wait"),
          str(fake.order()))
    w_argv = fake.argv_of("wait")
    check("wait-timeout: wait budget 1200 for video",
          w_argv and w_argv[w_argv.index("--timeout") + 1] == "1200",
          str(w_argv))
    row = job_row(db, "waittimeout-job", "att-1")
    check("wait-timeout: ledger row state=unknown",
          row and row[0] == "unknown", str(row))
    check("wait-timeout: task ID recorded on the row",
          row and row[3] == "task-42", str(row))
    check("wait-timeout: envelope carries task_id",
          env["evidence"].get("task_id") == "task-42"
          and env["evidence"].get("remote_task_id") == "task-42",
          str(env["evidence"]))
    check("wait-timeout: timed_out flag true",
          env["evidence"].get("timed_out") is True)
    check("wait-timeout: no auto-resubmit",
          "do not auto-resubmit" in env["next_action"], env["next_action"])
    check("wait-timeout: reservation retained not reconciled",
          row and row[1] is None, str(row))


def test_submit_fail_is_rejected_not_unknown():
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "fail",
                       "error": {"code": "validation_failed", "msg": "bad input"}}),
    })
    env, db, fake, _ = run_case(script, "subfail")
    check("submit-fail: rejected", env["outcome"] == "rejected",
          str(env["outcome"]))
    check("submit-fail: reason kie-submit-failed",
          env["reason_code"] == "kie-submit-failed",
          str(env["reason_code"]))
    check("submit-fail: no wait/save",
          fake.order() == ["health", "preflight", "prompt-budget", "submit"],
          str(fake.order()))
    row = job_row(db, "subfail-job", "att-1")
    check("submit-fail: settled failed not unknown",
          row and row[0] == "reconciled" and row[1] == "failed", str(row))
    conn = sqlite3.connect(db)
    try:
        ev = conn.execute(
            "SELECT status, payload_json FROM events WHERE kind='dispatch'"
        ).fetchone()
    finally:
        conn.close()
    check("submit-fail: dispatch evidence recorded",
          ev and ev[0] == "fail" and "validation_failed" in (ev[1] or ""),
          str(ev))


def _skip_case(mode, label):
    env, db, fake, _ = run_case(
        {"health": (0, {"adapter_mode": mode, "state": "success"})}, label)
    check("%s: waiting" % mode, env["outcome"] == "waiting", str(env["outcome"]))
    check("%s: reason generation-not-switched-on" % mode,
          env["reason_code"] == "generation-not-switched-on",
          str(env["reason_code"]))
    check("%s: stopped on health alone" % mode, fake.order() == ["health"],
          str(fake.order()))
    check("%s: no preflight/prompt-budget/submit" % mode,
          not ({"preflight", "prompt-budget", "submit"} & set(fake.order())))
    check("%s: no approval card" % mode,
          env["evidence"].get("approval_card") is None)
    check("%s: not generated" % mode, env["evidence"].get("generated") is False)
    check("%s: no fallback to a private KIE client" % mode,
          env["evidence"].get("fallback_used") is False)
    check("%s: client told generation is off" % mode,
          "not switched on" in (env["evidence"].get("client_message") or ""))
    row = job_row(db, label + "-job", "att-1")
    check("%s: reservation released at zero" % mode,
          row and row[0] == "reconciled" and row[1] == "failed"
          and row[2] == 0, str(row))
    check("%s: exit 3" % mode, D.EXIT[env["outcome"]] == 3)


def test_shadow_skip():
    _skip_case("shadow", "shadow")


def test_off_mode_skips():
    _skip_case("off", "offmode")


def test_preflight_shortfall():
    script = {
        "health": HEALTH_ACTIVE,
        "preflight": (1, {"state": "fail",
                          "error": {"code": "insufficient_credits"},
                          "data": {"ok": False, "shortfall": 42}}),
    }
    env, db, fake, _ = run_case(script, "shortfall")
    check("shortfall: rejected", env["outcome"] == "rejected",
          str(env["outcome"]))
    check("shortfall: reason preflight-shortfall",
          env["reason_code"] == "preflight-shortfall",
          str(env["reason_code"]))
    check("shortfall: exit 5", D.EXIT[env["outcome"]] == 5)
    check("shortfall: stopped before prompt-budget and submit",
          fake.order() == ["health", "preflight"], str(fake.order()))
    check("shortfall: shortfall surfaced",
          env["evidence"].get("shortfall") == 42,
          str(env["evidence"].get("shortfall")))
    check("shortfall: nothing generated",
          env["evidence"].get("generated") is False)
    row = job_row(db, "shortfall-job", "att-1")
    check("shortfall: reservation released at zero",
          row and row[0] == "reconciled" and row[1] == "failed"
          and row[2] == 0, str(row))


def test_prompt_over_max():
    script = {
        "health": HEALTH_ACTIVE,
        "preflight": PREFLIGHT_OK,
        "prompt-budget": (4, {"state": "fail",
                              "data": {"status": "ABOVE_MAX", "exit_code": 4,
                                       "cut": 300, "max": 20000}}),
    }
    env, db, fake, _ = run_case(script, "overmax", prompt="z" * 25000)
    check("over max: rejected", env["outcome"] == "rejected",
          str(env["outcome"]))
    check("over max: reason prompt-over-max",
          env["reason_code"] == "prompt-over-max",
          str(env["reason_code"]))
    check("over max: exit 5", D.EXIT[env["outcome"]] == 5)
    check("over max: never reached submit",
          fake.order() == ["health", "preflight", "prompt-budget"],
          str(fake.order()))
    check("over max: characters to cut reported",
          env["evidence"].get("data", {}).get("cut") == 300)
    check("over max: nothing generated",
          env["evidence"].get("generated") is False)
    row = job_row(db, "overmax-job", "att-1")
    check("over max: reservation released at zero",
          row and row[0] == "reconciled" and row[1] == "failed"
          and row[2] == 0, str(row))


def test_unknown_outcome_no_retry():
    """Non-terminal wait answer: unknown WITH task id, no retry."""
    script = dict(BASE_SCRIPT)
    script.update({
        "submit": (0, {"state": "queued", "task_id": "task-9"}),
        "wait": (0, {"state": "lost", "task_id": "task-9"}),
    })
    env, db, fake, _ = run_case(script, "unknown")
    check("unknown: waiting", env["outcome"] == "waiting",
          str(env["outcome"]))
    check("unknown: reason unknown-outcome-no-retry",
          env["reason_code"] == "unknown-outcome-no-retry",
          str(env["reason_code"]))
    check("unknown: no save after non-terminal wait",
          fake.order() == ["health", "preflight", "prompt-budget",
                           "submit", "wait"],
          str(fake.order()))
    row = job_row(db, "unknown-job", "att-1")
    check("unknown: reservation retained (state=unknown)",
          row and row[0] == "unknown" and row[1] is None, str(row))
    check("unknown: task id recorded", row[3] == "task-9", str(row[3]))
    check("unknown: no auto-resubmit in next action",
          "do not auto-resubmit" in env["next_action"], env["next_action"])
    check("unknown: retries recorded as 0",
          env["evidence"].get("retries") == 0
          and env["evidence"].get("resubmitted") is False)


def test_submit_crash_is_unknown_no_retry():
    script = dict(BASE_SCRIPT)
    script["submit"] = ConnectionError("connection reset during createTask")
    env, db, fake, _ = run_case(script, "crashrun")
    check("crash submit: waiting", env["outcome"] == "waiting",
          str(env["outcome"]))
    check("crash submit: unknown, not error",
          env["reason_code"] == "unknown-outcome-no-retry",
          str(env["reason_code"]))
    check("crash submit: one submit attempt only",
          fake.order().count("submit") == 1, str(fake.order()))
    row = job_row(db, "crashrun-job", "att-1")
    check("crash submit: reservation retained, no task id",
          row and row[0] == "unknown" and row[1] is None
          and not row[3], str(row))


def test_submit_skipped_is_not_generated():
    script = dict(BASE_SCRIPT)
    script["submit"] = (0, {"state": "skipped", "fallback_used": True})
    env, db, fake, _ = run_case(script, "rskip")
    check("submit skip: waiting", env["outcome"] == "waiting",
          str(env["outcome"]))
    check("submit skip: reason generation-skipped-not-generated",
          env["reason_code"] == "generation-skipped-not-generated",
          str(env["reason_code"]))
    check("submit skip: skipped treated as not generated",
          env["evidence"].get("generated") is False
          and env["evidence"].get("approval_card") is None)
    check("submit skip: no private KIE fallback",
          env["evidence"].get("fallback_used") is False)
    row = job_row(db, "rskip-job", "att-1")
    check("submit skip: reservation released at zero",
          row and row[0] == "reconciled" and row[1] == "failed"
          and row[2] == 0, str(row))


def test_adapter_missing_fails_closed():
    env, db, fake, _ = run_case({}, "noadapter",
                                adapter_path=os.path.join(tempfile.gettempdir(),
                                                          "does-not-exist.py"))
    check("missing adapter: error", env["outcome"] == "error",
          str(env["outcome"]))
    check("missing adapter: reason adapter-not-found",
          env["reason_code"] == "adapter-not-found",
          str(env["reason_code"]))
    check("missing adapter: no Skill 74 call at all", fake.calls == [],
          str(fake.calls))
    check("missing adapter: no private KIE client invented",
          "no private KIE client" in env["next_action"], env["next_action"])
    row = job_row(db, "noadapter-job", "att-1")
    check("missing adapter: reservation released",
          row and row[0] == "reconciled" and row[1] == "failed", str(row))


def _resolver():
    sys.path.insert(0, HERE)
    from kie_dispatch.unknown_resolution import resolver as R  # noqa: E402
    return R


def test_resolver_no_remote_task_undeterminable_without_evidence():
    """C2 rule 5: no remote task + no submit-error evidence -> undeterminable."""
    R = _resolver()
    tmp = tempfile.mkdtemp(prefix="kie-res-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-res1", 10000)
    L.plan(db, "run-res1", "r1", "att-1", "d1", 100, stage="kie")
    L.reserve(db, "run-res1", "r1", "att-1")
    L.mark_unknown(db, "run-res1", "r1", "att-1")
    job = {"run_id": "run-res1", "logical_key": "r1", "attempt_id": "att-1",
           "state": "unknown", "remote_task_id": "", "estimated_cost": 100,
           "owner": "", "lease_expires": 0, "version": 1}
    rec = R.resolve_one(db_path=db, job=job, runner=None, adapter=None,
                        owner="t")
    check("resolver: no-evidence -> undeterminable",
          rec["disposition"] == "undeterminable", str(rec["disposition"]))
    check("resolver: no-evidence -> not settled",
          rec["settled"] is False, str(rec["settled"]))
    check("resolver: next_action points at kie.ai/logs",
          "kie.ai/logs" in (rec.get("next_action") or ""),
          str(rec.get("next_action")))
    row = job_row(db, "r1", "att-1")
    check("resolver: no-evidence row stays unknown",
          row and row[0] == "unknown", str(row))


def test_resolver_zero_settles_only_with_submit_error_evidence():
    R = _resolver()
    tmp = tempfile.mkdtemp(prefix="kie-res2-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-res2", 10000)
    L.plan(db, "run-res2", "r2", "att-1", "d2", 100, stage="kie")
    L.reserve(db, "run-res2", "r2", "att-1")
    L.mark_unknown(db, "run-res2", "r2", "att-1")
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO events(run_id,logical_key,attempt_id,kind,"
            "provider_event_id,provider_seq,status,payload_json,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            ("run-res2", "r2", "att-1", "dispatch", "submit", 0, "fail",
             '{"error":{"code":"validation_failed"}}',
             "2026-10-08T00:00:00+00:00"))
        conn.commit()
    finally:
        conn.close()
    job = {"run_id": "run-res2", "logical_key": "r2", "attempt_id": "att-1",
           "state": "unknown", "remote_task_id": "", "estimated_cost": 100,
           "owner": "", "lease_expires": 0, "version": 1}
    rec = R.resolve_one(db_path=db, job=job, runner=None, adapter=None,
                        owner="t")
    check("resolver: submit-error evidence -> no-remote-task",
          rec["disposition"] == "no-remote-task", str(rec["disposition"]))
    check("resolver: submit-error evidence -> settled zero",
          rec["settled"] is True and rec.get("actual_cost") == 0,
          str(rec))
    row = job_row(db, "r2", "att-1")
    check("resolver: evidence row reconciled failed at zero",
          row and row[0] == "reconciled" and row[1] == "failed"
          and row[2] == 0, str(row))


def test_no_operator_paths_and_no_private_kie_client():
    src = open(MODULE.__file__, encoding="utf-8").read()
    home_of = "/" + "Users" + "/"
    home_alt = "/" + "home" + "/"
    check("static: no operator home path", home_of not in src)
    check("static: no operator home path (alt)", home_alt not in src)
    for banned in ("urllib", "http.client", "socket", "api.kie.ai",
                   "https://", "http://", "requests.get", "requests.post"):
        check("static: no private KIE client import/call %r" % banned,
              banned not in src)
    check("static: Skill 74 is the only transport",
          "74-kie-live-adapter" in src and "subprocess" in src)
    check("static: real runner disabled for tests (zero paid calls)",
          MODULE.make_runner is _forbid_make_runner)
    check("static: envelope schema stamped",
          MODULE.SCHEMA_VERSION == "blackceo.kie-dispatch/envelope/v1")
    check("static: exit map", MODULE.EXIT == {"ok": 0, "error": 1, "waiting": 3,
                                              "parked": 4, "rejected": 5})


TESTS = [
    test_f15_unanswered_card_refuses_dispatch,
    test_ok,
    test_video_wait_budget,
    test_request_timeout_overrides,
    test_wait_timeout_keeps_task_id,
    test_submit_fail_is_rejected_not_unknown,
    test_shadow_skip,
    test_off_mode_skips,
    test_preflight_shortfall,
    test_prompt_over_max,
    test_unknown_outcome_no_retry,
    test_submit_crash_is_unknown_no_retry,
    test_submit_skipped_is_not_generated,
    test_adapter_missing_fails_closed,
    test_resolver_no_remote_task_undeterminable_without_evidence,
    test_resolver_zero_settles_only_with_submit_error_evidence,
    test_no_operator_paths_and_no_private_kie_client,
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
    print("all %d outcome tests passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
