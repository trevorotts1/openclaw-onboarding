#!/usr/bin/env python3
"""sc23_provider_error_classification.py — acceptance row SC-23 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-23, verbatim):
    "401 / 402 / 429 classification"

Required result (verbatim):
    "NEGATIVE: 401 is not retried (auth failure surfaces), 402 is not charged
     or retried as transient, 429 backs off with a bounded retry; no retry
     storm and no duplicate paid entry for any class"

The classifier is the REAL ``capability_control.failures``, the 429 retry loop
is the REAL ``load_governor.kie_request`` and the money path is the REAL
``spend_ledger`` of the tree under test. Provider answers are fixture dicts.
Sleep is injected so no real backoff runs. No network, no paid provider, no
channel, no graph mutation.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc23"
TITLE = "401/402/429 classified; bounded retry, no storm, no duplicate charge"

RUN_ID = "runSC23"
KEY = "music.job"
COST = 5
NOW = 1_700_000_000.0

AUTH_401 = {"status": 401, "message": "invalid api key for this account"}
CREDIT_402 = {"status": 402, "message": "insufficient balance: payment required"}
QUOTA_402 = {"status": 402, "message": "monthly quota exceeded for the billing period"}
THROTTLE_429 = {"status": 429, "message": "too many requests",
                "headers": {"retry-after": "2"}}
THROTTLE_429_NO_RESET = {"status": 429, "message": "too many requests"}


def load_core(core):
    sys.path.insert(0, str(core))
    try:
        fail = importlib.import_module("capability_control.failures")
        gov = importlib.import_module("load_governor")
        led = importlib.import_module("spend_ledger")
    finally:
        try:
            sys.path.remove(str(core))
        except ValueError:
            pass
    return fail, gov, led


def _call(fn, answer):
    """Count provider calls and return the fixture answer."""
    box = {"calls": 0}

    def run():
        box["calls"] += 1
        return answer
    return run, box


def _job_rows(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    finally:
        conn.close()


def scenario(core, muts=frozenset()):
    fail, gov, led = load_core(core)
    c = H.Checks(ROW, TITLE)
    print("SC23 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        db = str(Path(tmp) / "spend.db")
        init = led.init_run(db, RUN_ID, ceiling=10000, repair_cap=2)
        if init.get("outcome") != "ok":
            c.check("sc23:ledger-initialised", False,
                    "init_run outcome=%r reason=%r"
                    % (init.get("outcome"), init.get("reason_code")))
            return c
        c.check("sc23:ledger-initialised", True,
                "init_run outcome=%r ceiling=%d"
                % (init.get("outcome"), 10000))
        planned = led.plan(db, RUN_ID, KEY, "", "d" * 16,
                           estimated_cost=COST, stage="music")
        attempt = planned.get("attempt_id")
        reserved = led.reserve(db, RUN_ID, KEY, attempt)
        c.check("sc23:one-paid-entry-before-any-provider-call",
                reserved.get("outcome") == "ok"
                and led.summary(db, RUN_ID)["evidence"]["committed_cost"] == COST,
                "reserve outcome=%r committed_cost=%r"
                % (reserved.get("outcome"),
                   led.summary(db, RUN_ID)["evidence"]["committed_cost"]))

        # ---- 401: authorization failure, surfaced, never retried ---------
        f401 = fail.classify(AUTH_401, now=NOW)
        c.check("sc23:401-classified-hard-authorization-failure",
                f401.kind == "AUTHORIZATION_FAILURE" and f401.hard is True
                and f401.retry_at is None and f401.retry_at_source == "none",
                "kind=%r hard=%r retry_at=%r source=%r detail=%r"
                % (f401.kind, f401.hard, f401.retry_at,
                   f401.retry_at_source, f401.detail[:60]))

        limited = (lambda _r: True) if "retry_401" in muts else gov.is_rate_limited
        fn401, box401 = _call(None, AUTH_401)
        exc401 = None
        try:
            res401 = gov.kie_request(fn401, label="music", retries=3,
                                     sleep=lambda _s: None,
                                     acquire=lambda: None, is_limited=limited)
        except gov.KieRateLimitError as exc:
            res401, exc401 = {}, exc
        c.check("sc23:401-not-retried",
                box401["calls"] == 1 and res401 == AUTH_401
                and f401.retry_at is None and exc401 is None,
                "provider calls=%d (must be 1), returned status=%r, "
                "retry_at=%r, exception=%r"
                % (box401["calls"], res401.get("status"), f401.retry_at,
                   type(exc401).__name__ if exc401 is not None else None))

        # ---- 402: credit exhausted, not charged again, not transient -----
        f402 = fail.classify(CREDIT_402, now=NOW)
        c.check("sc23:402-classified-credit-not-transient",
                f402.kind == "CREDIT_EXHAUSTED" and f402.hard is True
                and f402.retry_at is None,
                "kind=%r hard=%r retry_at=%r detail=%r"
                % (f402.kind, f402.hard, f402.retry_at, f402.detail[:60]))

        fq = fail.classify(QUOTA_402, now=NOW)
        c.check("sc23:402-monthly-cap-keeps-no-invented-reset",
                fq.kind == "HARD_QUOTA" and fq.hard is True
                and fq.retry_at is None and fq.retry_at_source == "none",
                "kind=%r hard=%r retry_at=%r source=%r"
                % (fq.kind, fq.hard, fq.retry_at, fq.retry_at_source))

        fn402, box402 = _call(None, CREDIT_402)
        res402 = gov.kie_request(fn402, label="music", retries=3,
                                 sleep=lambda _s: None, acquire=lambda: None)
        c.check("sc23:402-not-retried-as-transient",
                box402["calls"] == 1 and res402.get("status") == 402,
                "provider calls=%d (must be 1), returned status=%r"
                % (box402["calls"], res402.get("status")))

        after402 = led.summary(db, RUN_ID)["evidence"]
        c.check("sc23:402-not-charged-a-second-time",
                after402["committed_cost"] == COST and _job_rows(db) == 1,
                "committed_cost=%r jobs=%d (one %d-unit entry; a 402 is a "
                "hard credit failure, never a transient retry)"
                % (after402["committed_cost"], _job_rows(db), COST))

        # ---- 429: throttle, authoritative retry-at, bounded backoff ------
        f429 = fail.classify(THROTTLE_429, now=NOW)
        c.check("sc23:429-classified-throttle-with-authoritative-retry-at",
                f429.kind == "THROTTLED" and f429.hard is False
                and f429.retry_at == NOW + 2.0
                and f429.retry_at_source == "authoritative",
                "kind=%r hard=%r retry_at=%r source=%r"
                % (f429.kind, f429.hard, f429.retry_at,
                   f429.retry_at_source))

        f429b = fail.classify(THROTTLE_429_NO_RESET, now=NOW)
        policy = fail.BoundedPolicy()
        c.check("sc23:429-without-retry-after-uses-bounded-policy",
                f429b.kind == "THROTTLED" and f429b.hard is False
                and f429b.retry_at == NOW + policy.throttle_max_retry_after_s
                and f429b.retry_at_source == "bounded_policy",
                "kind=%r retry_at=%r source=%r (policy bound=%rs)"
                % (f429b.kind, f429b.retry_at, f429b.retry_at_source,
                   policy.throttle_max_retry_after_s))

        slept = []
        answers = [THROTTLE_429, {"status": 200, "ok": True}]
        box_calls = {"n": 0}

        def run429ok():
            box_calls["n"] += 1
            return answers[0] if box_calls["n"] == 1 else answers[1]

        res429 = gov.kie_request(run429ok, label="music", retries=3,
                                 backoff_s=2.0, sleep=slept.append,
                                 acquire=lambda: None)
        c.check("sc23:429-succeeds-within-the-bounded-retry",
                box_calls["n"] == 2 and res429.get("status") == 200
                and slept == [2.0],
                "provider calls=%d, slept=%r, final status=%r"
                % (box_calls["n"], slept, res429.get("status")))

        storm = {"calls": 0, "sleeps": []}
        backoff = 1000.0 if "unbounded_429" in muts else 2.0
        retries = 0 if "unbounded_429" in muts else 2

        def always_429():
            storm["calls"] += 1
            return THROTTLE_429

        try:
            gov.kie_request(always_429, label="music", retries=retries,
                            backoff_s=backoff,
                            sleep=storm["sleeps"].append,
                            acquire=lambda: None)
            boom = None
        except gov.KieRateLimitError as exc:
            boom = exc
        c.check("sc23:429-retry-is-bounded-no-storm",
                storm["calls"] == 3 and boom is not None
                and storm["sleeps"] == [2.0, 4.0]
                and "NOT submitted" in str(boom),
                "provider calls=%d, backoff sleeps=%r, raised=%r, "
                "message=%r"
                % (storm["calls"], storm["sleeps"],
                   type(boom).__name__ if boom is not None else None,
                   (str(boom) if boom is not None else "")[:70]))

        # ---- breaker: one event for hard, none for throttling ------------
        breaker = fail.AccountBreaker(policy=policy,
                                      now_fn=lambda: NOW)
        ev1 = breaker.record_failure("acct-sc23", AUTH_401)
        ev2 = breaker.record_failure("acct-sc23", AUTH_401)
        throttle_ev = breaker.record_failure("acct-sc23-t", THROTTLE_429)
        c.check("sc23:hard-failure-opens-exactly-one-event",
                ev1 is not None and ev2 is None and len(breaker.open_events()) == 1,
                "first record kind=%r, second record=%r, open events=%d"
                % (ev1.kind if ev1 else None,
                   ev2.kind if ev2 else None,
                   len(breaker.open_events())))

        c.check("sc23:throttle-never-opens-a-breaker",
                throttle_ev is None,
                "throttle record returned=%r (None means no breaker opened)"
                % (throttle_ev.kind if throttle_ev else None))

        # ---- 429 resubmission of the in-flight job needs its own attempt --
        dup = led.plan(db, RUN_ID, KEY, "", "e" * 16,
                       estimated_cost=COST, stage="music")
        c.check("sc23:no-duplicate-paid-entry-for-any-class",
                dup.get("outcome") == "rejected"
                and dup.get("reason_code") == "DUPLICATE_LOGICAL_JOB",
                "resubmission outcome=%r reason=%r next=%r"
                % (dup.get("outcome"), dup.get("reason_code"),
                   (dup.get("next_action") or "")[:70]))

        if "duplicate_charge" in muts:
            other = led.plan(db, RUN_ID, "music.job-dup", "", "f" * 16,
                             estimated_cost=COST, stage="music")
            if other.get("outcome") == "ok":
                led.reserve(db, RUN_ID, "music.job-dup",
                            other.get("attempt_id"))

        final = led.summary(db, RUN_ID)["evidence"]
        c.check("sc23:no-duplicate-charge-after-all-classes",
                final["committed_cost"] == COST and _job_rows(db) == 1
                and final["repairs_used"] == 0,
                "committed_cost=%r jobs=%d repairs_used=%r (one %d-unit entry "
                "for all three classes)"
                % (final["committed_cost"], _job_rows(db),
                   final["repairs_used"], COST))
    return c


MUTATIONS = {
    "retry_401": [
        "sc23:401-not-retried",
    ],
    "unbounded_429": [
        "sc23:429-retry-is-bounded-no-storm",
    ],
    "duplicate_charge": [
        "sc23:no-duplicate-charge-after-all-classes",
    ],
}


def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good
                 else "DID NOT FAIL AS EXPECTED", failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s"
          % ("harness fails on every defect" if ok
             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc23 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc23.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
