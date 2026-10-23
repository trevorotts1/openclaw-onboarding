#!/usr/bin/env python3
"""sc22_provider_pending_over_ten_minutes.py — acceptance row SC-22 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-22, verbatim):
    "Provider pending over ten minutes"

Required result (verbatim):
    "NEGATIVE: a pending provider job older than ten minutes is
     reconciled/polled, never re-submitted; the state remains pending with
     evidence"

The ledger and the recovery plan are the REAL ``spend_ledger`` and
``job_recovery`` of the tree under test. The provider event is a fixture dict
shaped like the verified relay record; ageing the job is a fixture write to
the scratch DB only. No network, no paid provider, no channel, no graph
mutation.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc22"
TITLE = "pending provider job past ten minutes is polled, never resubmitted"

RUN_ID = "runSC22"
KEY = "music.job"
COST = 5
TASK_ID = "task-pending-0001"
AGE_SECONDS = 11 * 60


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


def _db_hash(db):
    with open(db, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _job_row(db, logical_key, attempt_id):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT state,remote_task_id,updated_at FROM jobs "
            "WHERE logical_key=? AND attempt_id=?",
            (logical_key, attempt_id)).fetchone()
    finally:
        conn.close()


def _event_status(db, provider_event_id):
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT status FROM events WHERE provider_event_id=?",
            (provider_event_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _age_job(db, logical_key, attempt_id, seconds):
    """Fixture write: move the job's updated_at into the past."""
    when = (datetime.now(timezone.utc)
            - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE jobs SET updated_at=? WHERE logical_key=? "
                     "AND attempt_id=?", (when, logical_key, attempt_id))
        conn.commit()
    finally:
        conn.close()
    return when


def _age_of(stamp):
    then = datetime.fromisoformat(stamp)
    return (datetime.now(timezone.utc) - then).total_seconds()


def scenario(core, muts=frozenset()):
    led, rec = load_core(core)
    c = H.Checks(ROW, TITLE)
    print("SC22 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        db = str(Path(tmp) / "spend.db")
        init = led.init_run(db, RUN_ID, ceiling=10000, repair_cap=2)
        if init.get("outcome") != "ok":
            c.check("sc22:ledger-initialised", False,
                    "init_run outcome=%r reason=%r"
                    % (init.get("outcome"), init.get("reason_code")))
            return c
        c.check("sc22:ledger-initialised", True,
                "init_run outcome=%r ceiling=%d"
                % (init.get("outcome"), 10000))

        planned = led.plan(db, RUN_ID, KEY, "", "b" * 16,
                           estimated_cost=COST, stage="music")
        attempt = planned.get("attempt_id")
        reserved = led.reserve(db, RUN_ID, KEY, attempt)
        after_reserve = led.summary(db, RUN_ID)["evidence"]
        c.check("sc22:one-paid-reservation",
                reserved.get("outcome") == "ok"
                and after_reserve["committed_cost"] == COST,
                "reserve outcome=%r committed_cost=%r (one %d-unit "
                "reservation)"
                % (reserved.get("outcome"),
                   after_reserve["committed_cost"], COST))

        submitted = led.mark_submitted(db, RUN_ID, KEY, attempt, TASK_ID)
        c.check("sc22:remote-task-id-persisted-before-waiting",
                submitted.get("outcome") == "ok"
                and _job_row(db, KEY, attempt)[1] == TASK_ID,
                "mark_submitted outcome=%r persisted remote_task_id=%r"
                % (submitted.get("outcome"),
                   _job_row(db, KEY, attempt)[1]))

        # ---- provider still says pending, well under the ten-minute mark --
        pend = rec.ingest_event(db, RUN_ID, KEY, attempt, "evt-pending-1",
                                provider_seq=1, status="pending",
                                payload={"task_id": TASK_ID})
        pend_ev = pend.get("evidence") or {}
        c.check("sc22:pending-event-recorded-without-resubmission",
                pend.get("outcome") == "ok"
                and pend_ev.get("remote_task_id") == TASK_ID
                and _event_status(db, "evt-pending-1") == "pending",
                "ingest outcome=%r evidence state=%r remote=%r stored "
                "event status=%r"
                % (pend.get("outcome"), pend_ev.get("state"),
                   pend_ev.get("remote_task_id"),
                   _event_status(db, "evt-pending-1")))

        # ---- fixture: the job has now been pending for over ten minutes --
        if "never_ages" in muts:
            _age_job(db, KEY, attempt, 0)
        elif "lose_remote_id" in muts:
            _age_job(db, KEY, attempt, AGE_SECONDS)
            conn = sqlite3.connect(db)
            try:
                conn.execute("UPDATE jobs SET remote_task_id='' WHERE "
                             "logical_key=? AND attempt_id=?",
                             (KEY, attempt))
                conn.commit()
            finally:
                conn.close()
        else:
            _age_job(db, KEY, attempt, AGE_SECONDS)

        state, remote, stamp = _job_row(db, KEY, attempt)
        age = _age_of(stamp)
        c.check("sc22:aged-beyond-ten-minutes",
                age >= 600,
                "job updated_at=%r age=%.0fs (need >= 600s); state=%r "
                "remote=%r" % (stamp, age, state, remote))

        before_hash = _db_hash(db)
        plan = rec.recover(db, RUN_ID)
        plans = (plan.get("evidence") or {}).get("jobs") or []
        job = next((j for j in plans if j.get("logical_key") == KEY), {})
        c.check("sc22:recovery-polls-instead-of-resubmitting",
                plan.get("outcome") == "ok"
                and job.get("action") == "POLL"
                and job.get("reason") == "REMOTE_TRACKED",
                "recover action=%r reason=%r next=%r for attempt=%r"
                % (job.get("action"), job.get("reason"),
                   (job.get("next") or "")[:80], job.get("attempt_id")))

        state_after, remote_after, stamp_after = _job_row(db, KEY, attempt)
        c.check("sc22:pending-state-remains-with-evidence",
                state_after == "submitted"
                and remote_after == TASK_ID
                and stamp_after == stamp,
                "state=%r remote_task_id=%r updated_at unchanged=%r"
                % (state_after, remote_after, stamp_after == stamp))

        after_hash = _db_hash(db)
        c.check("sc22:recovery-writes-nothing",
                before_hash == after_hash,
                "db sha256 before=%r after=%r"
                % (before_hash[:16], after_hash[:16]))

        dup = led.plan(db, RUN_ID, KEY, "", "c" * 16,
                       estimated_cost=COST, stage="music")
        c.check("sc22:second-submission-refused-while-pending",
                dup.get("outcome") == "rejected"
                and dup.get("reason_code") == "DUPLICATE_LOGICAL_JOB",
                "second plan outcome=%r reason=%r next=%r"
                % (dup.get("outcome"), dup.get("reason_code"),
                   (dup.get("next_action") or "")[:80]))

        final = led.summary(db, RUN_ID)["evidence"]
        total = ((final.get("committed_cost") or 0)
                 + (final.get("unknown_or_reserved_cost") or 0)
                 + (final.get("actual_cost") or 0))
        c.check("sc22:no-duplicate-paid-entry",
                final["number_of_generation_calls"] == 1 and total == COST,
                "generation_calls=%r paid total=%r (one %d-unit job), "
                "repairs_used=%r"
                % (final["number_of_generation_calls"], total, COST,
                   final["repairs_used"]))
    return c


MUTATIONS = {
    "never_ages": [
        "sc22:aged-beyond-ten-minutes",
    ],
    "lose_remote_id": [
        "sc22:recovery-polls-instead-of-resubmitting",
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
        args = H.add_args(description="sc22 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc22.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
