#!/usr/bin/env python3
"""sc21_lost_provider_response.py — acceptance row SC-21 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-21, verbatim):
    "Lost provider response reconciliation"

Required result (verbatim):
    "NEGATIVE: a lost provider response is reconciled to the existing job id;
     no second submission and no duplicate paid ledger entry"

The ledger is the REAL ``spend_ledger`` of the tree under test and the
reconciliation is the REAL ``job_recovery``; the provider event is a fixture
dict shaped like the verified relay record. No network, no paid provider, no
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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc21"
TITLE = "lost provider response reconciled, never resubmitted"

RUN_ID = "runSC21"
KEY = "music.job"
COST = 5
TASK_ID = "task-X"
DIGEST_1 = "d" * 16
DIGEST_2 = "e" * 16
DIGEST_3 = "f" * 16
DIGEST_4 = "a" * 16


def load_core(core):
    sys.path.insert(0, str(core))
    try:
        led = importlib.import_module("spend_ledger")
        rec = importlib.import_module("job_recovery")
    finally:
        try:
            sys.path.remove(str(core))
        except ValueError:
            pass
    return led, rec


def cost_total(ev):
    return ((ev.get("committed_cost") or 0)
            + (ev.get("unknown_or_reserved_cost") or 0)
            + (ev.get("actual_cost") or 0))


def scenario(core, muts=frozenset()):
    led, rec = load_core(core)
    c = H.Checks(ROW, TITLE)
    print("SC21 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        db = str(Path(tmp) / "spend.db")
        init = led.init_run(db, RUN_ID, ceiling=10000, repair_cap=2)
        if init.get("outcome") != "ok":
            c.check("sc21:ledger-initialised", False,
                    "init_run outcome=%r reason=%r"
                    % (init.get("outcome"), init.get("reason_code")))
            return c
        c.check("sc21:ledger-initialised", True,
                "init_run outcome=%r ceiling=%d"
                % (init.get("outcome"), 10000))

        # ---- one paid attempt, then its response is lost ----------------
        planned = led.plan(db, RUN_ID, KEY, "", DIGEST_1,
                           estimated_cost=COST, stage="music")
        attempt = planned.get("attempt_id")
        reserved = led.reserve(db, RUN_ID, KEY, attempt)
        after_reserve = led.summary(db, RUN_ID)["evidence"]
        c.check("sc21:one-paid-reservation-for-the-logical-job",
                reserved.get("outcome") == "ok"
                and after_reserve["committed_cost"] == COST,
                "reserve outcome=%r committed_cost=%r (one %d-unit "
                "reservation)"
                % (reserved.get("outcome"),
                   after_reserve["committed_cost"], COST))

        lost = led.mark_unknown(db, RUN_ID, KEY, attempt)
        # ---- a second submission while the outcome is unknown ----------
        dup = led.plan(db, RUN_ID, KEY, "", DIGEST_2,
                       estimated_cost=COST, stage="music")
        c.check("sc21:lost-response-refuses-second-submission",
                dup.get("outcome") == "rejected"
                and dup.get("reason_code") == "RECONCILE_FIRST",
                "second plan outcome=%r reason=%r after mark_unknown=%r"
                % (dup.get("outcome"), dup.get("reason_code"),
                   lost.get("outcome")))

        # ---- recovery before any provider record: never resubmits ------
        pre = rec.recover(db, RUN_ID)
        pre_jobs = (pre.get("evidence") or {}).get("jobs") or []
        pre_job = next((j for j in pre_jobs
                        if j.get("logical_key") == KEY), {})
        c.check("sc21:recovery-never-auto-resubmits",
                pre.get("outcome") == "ok"
                and pre_job.get("action") == "BLOCKED"
                and pre_job.get("reason") == "NO_REMOTE_ID",
                "recover action=%r reason=%r for attempt=%r"
                % (pre_job.get("action"), pre_job.get("reason"),
                   pre_job.get("attempt_id")))

        # ---- the provider record arrives late: reconcile to ITS job id --
        payload = {} if "lost_task_id" in muts else {"task_id": TASK_ID}
        ev = rec.ingest_event(db, RUN_ID, KEY, attempt, "evt-1",
                              provider_seq=1, status="in_progress",
                              payload=payload)
        ev_evidence = ev.get("evidence") or {}
        c.check("sc21:recovery-reconciles-to-existing-job-id",
                ev.get("outcome") == "ok"
                and ev.get("attempt_id") == attempt
                and ev_evidence.get("remote_task_id") == TASK_ID
                and ev_evidence.get("state") == "unknown",
                "ingest outcome=%r attempt=%r remote_task_id=%r state=%r"
                % (ev.get("outcome"), ev.get("attempt_id"),
                   ev_evidence.get("remote_task_id"),
                   ev_evidence.get("state")))

        post = rec.recover(db, RUN_ID)
        post_jobs = (post.get("evidence") or {}).get("jobs") or []
        post_job = next((j for j in post_jobs
                         if j.get("logical_key") == KEY), {})
        c.check("sc21:recovery-plans-poll-of-the-reconciled-job",
                post_job.get("action") == "RECONCILE"
                and post_job.get("state") == "unknown",
                "recover action=%r state=%r reason=%r"
                % (post_job.get("action"), post_job.get("state"),
                   post_job.get("reason")))

        mis = rec.ingest_event(db, RUN_ID, KEY, attempt, "evt-mis",
                               provider_seq=2, status="in_progress",
                               payload={"task_id": "task-OTHER"})
        c.check("sc21:mismatched-task-id-is-refused",
                mis.get("outcome") == "rejected"
                and mis.get("reason_code") == "TASK_MISMATCH",
                "foreign task id outcome=%r reason=%r (recorded %r)"
                % (mis.get("outcome"), mis.get("reason_code"), TASK_ID))

        term = rec.ingest_event(db, RUN_ID, KEY, attempt, "evt-2",
                                provider_seq=3, status="succeeded",
                                payload={"task_id": TASK_ID})
        term_evidence = term.get("evidence") or {}
        c.check("sc21:terminal-response-closes-the-existing-job",
                term.get("outcome") == "ok"
                and term.get("attempt_id") == attempt
                and term_evidence.get("state") == "succeeded"
                and term_evidence.get("remote_task_id") == TASK_ID,
                "terminal outcome=%r attempt=%r state=%r remote=%r"
                % (term.get("outcome"), term.get("attempt_id"),
                   term_evidence.get("state"),
                   term_evidence.get("remote_task_id")))

        # ---- after success a resubmission needs its own authorization --
        later = led.plan(db, RUN_ID, KEY, "", DIGEST_3,
                         estimated_cost=COST, stage="music")
        c.check("sc21:no-free-resubmission-after-success",
                later.get("outcome") == "rejected"
                and later.get("reason_code") == "MISSING_AUTH_REF",
                "unauthorized retake outcome=%r reason=%r"
                % (later.get("outcome"), later.get("reason_code")))

        # ---- deliberate defect: an authorized duplicate paid attempt ---
        if "resubmit_after_success" in muts:
            led.record_provider_lookup(db, RUN_ID, KEY, attempt, "lookup-1",
                                       owner="worker-a")
            again = led.plan(db, RUN_ID, KEY, "", DIGEST_4,
                             estimated_cost=COST, stage="music",
                             auth_ref="auth-dup")
            if again.get("outcome") == "ok":
                led.reserve(db, RUN_ID, KEY, again.get("attempt_id"))

        final = led.summary(db, RUN_ID)["evidence"]
        total = cost_total(final)
        c.check("sc21:no-duplicate-paid-entry",
                final["number_of_generation_calls"] == 1
                and total == COST
                and final["repairs_used"] == 0,
                "generation_calls=%r paid total=%r (one %d-unit job), "
                "repairs_used=%r"
                % (final["number_of_generation_calls"], total, COST,
                   final["repairs_used"]))
    return c


MUTATIONS = {
    "lost_task_id": [
        "sc21:recovery-reconciles-to-existing-job-id",
        "sc21:recovery-plans-poll-of-the-reconciled-job",
    ],
    "resubmit_after_success": [
        "sc21:no-duplicate-paid-entry",
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
        args = H.add_args(description="sc21 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc21.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
