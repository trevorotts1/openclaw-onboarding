#!/usr/bin/env python3
"""wait_for_stage.py - the one waiter for a background stage job. Stdlib only.

It waits on FACTS, never on a process name:
  --stage S        the stage row in control/state.sqlite3 reaches COMPLETE
  --artifact PATH  the file exists, is at least --min-bytes, and its size was
                   the same on two reads --settle-seconds apart (so a file that
                   is still being written is not mistaken for finished)
Both may be given; then both must hold.

It always ends:
  exit 0   the condition holds (JSON says what was observed)
  exit 2   still waiting at --timeout-seconds  (a FAILURE to investigate)
  exit 4   the stage reached a state that can never become COMPLETE by waiting
           (FAILED_BLOCKED, PARKED, CANCELED)
  exit 1   the state database could not be read

Polls no faster than every 15 seconds. The state database is opened read-only.
"""
import argparse
import json
import os
import sqlite3
import sys
import time

DEAD_END_STATES = ("FAILED_BLOCKED", "PARKED", "CANCELED")
MIN_POLL_SECONDS = 15


def stage_state(run_dir, stage):
    db = os.path.join(os.path.abspath(run_dir), "control", "state.sqlite3")
    if not os.path.isfile(db):
        raise OSError("no state database at %s" % db)
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=10)
    try:
        row = con.execute("SELECT state FROM stages WHERE stage=?", (stage,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def artifact_settled(path, min_bytes, settle_seconds, sleep=time.sleep):
    if not os.path.isfile(path):
        return False, "missing"
    first = os.path.getsize(path)
    if first < min_bytes:
        return False, "%d bytes, below the %d byte floor" % (first, min_bytes)
    sleep(settle_seconds)
    second = os.path.getsize(path) if os.path.isfile(path) else -1
    if second != first:
        return False, "still changing (%d then %d bytes)" % (first, second)
    return True, "%d bytes, unchanged for %s seconds" % (first, settle_seconds)


def wait(run_dir, stage=None, artifact=None, min_bytes=1, timeout_seconds=3600,
         poll_seconds=30, settle_seconds=5, sleep=time.sleep, clock=time.time):
    poll_seconds = max(MIN_POLL_SECONDS, int(poll_seconds))
    deadline = clock() + timeout_seconds
    observed = {"stage_state": None, "artifact": None, "polls": 0}
    while True:
        observed["polls"] += 1
        stage_ok = True
        if stage:
            state = stage_state(run_dir, stage)
            observed["stage_state"] = state
            if state in DEAD_END_STATES:
                return 4, dict(observed, outcome="rejected", reason_code="STAGE_DEAD_END")
            stage_ok = state == "COMPLETE"
        artifact_ok = True
        if artifact:
            artifact_ok, detail = artifact_settled(artifact, min_bytes, settle_seconds, sleep)
            observed["artifact"] = detail
        if stage_ok and artifact_ok:
            return 0, dict(observed, outcome="ok", reason_code="CONDITION_MET")
        if clock() >= deadline:
            return 2, dict(observed, outcome="waiting", reason_code="WAIT_TIMEOUT",
                           next_action="Do not keep waiting. Read the job's own log "
                                       "and the stage row, then report what stopped.")
        sleep(poll_seconds)


def selftest():
    import tempfile
    proofs = []
    with tempfile.TemporaryDirectory() as run:
        os.makedirs(os.path.join(run, "control"))
        db = os.path.join(run, "control", "state.sqlite3")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE stages(run_id TEXT, stage TEXT, state TEXT)")
        con.execute("INSERT INTO stages VALUES('r','music','RUNNING')")
        con.commit()
        fake = {"now": 0.0}

        def sleep(seconds):
            fake["now"] += seconds

        code, _ = wait(run, stage="music", timeout_seconds=60, sleep=sleep,
                       clock=lambda: fake["now"])
        proofs.append(("a stage that never completes times out with exit 2", code == 2))
        con.execute("UPDATE stages SET state='FAILED_BLOCKED'")
        con.commit()
        code, _ = wait(run, stage="music", timeout_seconds=60, sleep=sleep,
                       clock=lambda: fake["now"])
        proofs.append(("a blocked stage ends at once with exit 4", code == 4))
        con.execute("UPDATE stages SET state='COMPLETE'")
        con.commit()
        con.close()
        target = os.path.join(run, "song.mp3")
        code, _ = wait(run, stage="music", artifact=target, timeout_seconds=30,
                       sleep=sleep, clock=lambda: fake["now"])
        proofs.append(("COMPLETE row with a missing file still waits", code == 2))
        open(target, "wb").write(b"x" * 100)
        code, _ = wait(run, stage="music", artifact=target, min_bytes=50,
                       timeout_seconds=30, sleep=sleep, clock=lambda: fake["now"])
        proofs.append(("COMPLETE row plus a settled file returns exit 0", code == 0))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir")
    ap.add_argument("--stage", default=None)
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--min-bytes", type=int, default=1)
    ap.add_argument("--timeout-seconds", type=int, default=3600)
    ap.add_argument("--poll-seconds", type=int, default=30)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.run_dir or not (a.stage or a.artifact):
        ap.error("--run-dir and at least one of --stage / --artifact are required")
    try:
        code, doc = wait(a.run_dir, a.stage, a.artifact, a.min_bytes,
                         a.timeout_seconds, a.poll_seconds)
    except (OSError, sqlite3.Error) as exc:
        print(json.dumps({"outcome": "error", "reason_code": "STATE_UNREADABLE",
                          "detail": str(exc)}, indent=2))
        return 1
    print(json.dumps(doc, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
