#!/usr/bin/env python3
"""Mocked-Skill-74 tests for kie_dispatch: every plan 5.4 outcome. stdlib only.

Outcomes covered (one test each):
  ok | shadow-skip (+ off) | preflight shortfall | prompt over max |
  unknown outcome stops with no retry | adapter missing | crash mid-run

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


def job_row(db, logical_key, attempt_id):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT state, final_outcome, actual_cost FROM jobs "
            "WHERE logical_key=? AND attempt_id=?",
            (logical_key, attempt_id)).fetchone()
    finally:
        conn.close()


def run_case(script, label, adapter_path=None, prompt=None, cost=100):
    tmp = tempfile.mkdtemp(prefix="kie-dispatch-test-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-" + label, 10000)
    save_dir = os.path.join(tmp, "out")
    fake = Fake74(script)
    env = D.dispatch(
        model="gpt-image-2-5-sunburst-text-to-image",
        request={"model": "m", "input": {"prompt": "p" * 200}},
        save_dir=save_dir, ledger_db=db, run_id="run-" + label,
        logical_key=label + "-job", attempt_id="att-1",
        estimated_cost=cost,
        prompt=("q" * 200) if prompt is None else prompt,
        adapter_path=adapter_path or os.path.abspath(__file__),
        runner=fake)
    return env, db, fake, tmp


HEALTH_ACTIVE = (0, {"adapter_mode": "active", "state": "success"})
PREFLIGHT_OK = (0, {"state": "validated", "data": {"ok": True}})
BUDGET_OK = (0, {"state": "success",
                 "data": {"status": "OK", "exit_code": 0, "max": 20000}})


def test_ok():
    tmp = tempfile.mkdtemp(prefix="kie-ok-")
    script = {
        "health": HEALTH_ACTIVE,
        "preflight": PREFLIGHT_OK,
        "prompt-budget": BUDGET_OK,
        "run": (0, {"state": "success", "task_id": "task-1",
                    "saved_paths": [os.path.join(tmp, "shot.png")],
                    "credits_consumed": 16}),
    }
    env, db, fake, _ = run_case(script, "ok")
    check("ok: outcome ok", env["outcome"] == "ok", str(env["outcome"]))
    check("ok: reason KIE_DISPATCH_OK", env["reason_code"] == "KIE_DISPATCH_OK")
    check("ok: exit 0", D.EXIT[env["outcome"]] == 0)
    check("ok: stage order reserve->health->preflight->budget->run",
          fake.order() == ["health", "preflight", "prompt-budget", "run"],
          str(fake.order()))
    check("ok: exactly one run call",
          fake.order().count("run") == 1, str(fake.order()))
    row = job_row(db, "ok-job", "att-1")
    check("ok: ledger reconciled/succeeded",
          row and row[0] == "reconciled" and row[1] == "succeeded", str(row))
    check("ok: actual cost recorded", row[2] == 16, str(row[2]))
    check("ok: generated true", env["evidence"].get("generated") is True)
    check("ok: task id kept", env["evidence"].get("task_id") == "task-1")
    check("ok: files saved", len(env["evidence"].get("saved_paths") or []) == 1)


def _skip_case(mode, label):
    env, db, fake, _ = run_case(
        {"health": (0, {"adapter_mode": mode, "state": "success"})}, label)
    check("%s: waiting" % mode, env["outcome"] == "waiting", str(env["outcome"]))
    check("%s: reason generation-not-switched-on" % mode,
          env["reason_code"] == "generation-not-switched-on",
          str(env["reason_code"]))
    check("%s: stopped on health alone" % mode, fake.order() == ["health"],
          str(fake.order()))
    check("%s: no preflight/prompt-budget/run" % mode,
          not ({"preflight", "prompt-budget", "run"} & set(fake.order())))
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
    check("shortfall: stopped before prompt-budget and run",
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
    check("over max: never reached run",
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
    script = {
        "health": HEALTH_ACTIVE,
        "preflight": PREFLIGHT_OK,
        "prompt-budget": BUDGET_OK,
        "run": (0, {"state": "lost", "task_id": "task-9"}),
    }
    env, db, fake, _ = run_case(script, "unknown")
    check("unknown: waiting", env["outcome"] == "waiting",
          str(env["outcome"]))
    check("unknown: reason unknown-outcome-no-retry",
          env["reason_code"] == "unknown-outcome-no-retry",
          str(env["reason_code"]))
    check("unknown: run attempted exactly once",
          fake.order().count("run") == 1, str(fake.order()))
    check("unknown: no fifth Skill 74 call", len(fake.calls) == 4,
          str(fake.order()))
    row = job_row(db, "unknown-job", "att-1")
    check("unknown: reservation retained (state=unknown)",
          row and row[0] == "unknown" and row[1] is None, str(row))
    check("unknown: no auto-resubmit in next action",
          "do not auto-resubmit" in env["next_action"], env["next_action"])
    check("unknown: retries recorded as 0",
          env["evidence"].get("retries") == 0
          and env["evidence"].get("resubmitted") is False)


def test_run_crash_is_unknown_no_retry():
    script = {
        "health": HEALTH_ACTIVE,
        "preflight": PREFLIGHT_OK,
        "prompt-budget": BUDGET_OK,
        "run": ConnectionError("connection reset during createTask"),
    }
    env, db, fake, _ = run_case(script, "crashrun")
    check("crash run: waiting", env["outcome"] == "waiting",
          str(env["outcome"]))
    check("crash run: unknown, not error",
          env["reason_code"] == "unknown-outcome-no-retry",
          str(env["reason_code"]))
    check("crash run: one run attempt only",
          fake.order().count("run") == 1, str(fake.order()))
    row = job_row(db, "crashrun-job", "att-1")
    check("crash run: reservation retained",
          row and row[0] == "unknown" and row[1] is None, str(row))


def test_run_skipped_is_not_generated():
    script = {
        "health": HEALTH_ACTIVE,
        "preflight": PREFLIGHT_OK,
        "prompt-budget": BUDGET_OK,
        "run": (0, {"state": "skipped", "fallback_used": True}),
    }
    env, db, fake, _ = run_case(script, "rskip")
    check("run skip: waiting", env["outcome"] == "waiting",
          str(env["outcome"]))
    check("run skip: reason generation-skipped-not-generated",
          env["reason_code"] == "generation-skipped-not-generated",
          str(env["reason_code"]))
    check("run skip: skipped treated as not generated",
          env["evidence"].get("generated") is False
          and env["evidence"].get("approval_card") is None)
    check("run skip: no private KIE fallback",
          env["evidence"].get("fallback_used") is False)
    row = job_row(db, "rskip-job", "att-1")
    check("run skip: reservation released at zero",
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
    test_ok,
    test_shadow_skip,
    test_off_mode_skips,
    test_preflight_shortfall,
    test_prompt_over_max,
    test_unknown_outcome_no_retry,
    test_run_crash_is_unknown_no_retry,
    test_run_skipped_is_not_generated,
    test_adapter_missing_fails_closed,
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
