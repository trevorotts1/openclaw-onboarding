#!/usr/bin/env python3
"""F11: every timestamp the spend ledger writes is UTC with a zone.

Fix-manual Part F, item F11 (Low): "Mixed time-zone and no-time-zone rows
crash any comparison. Write every timestamp as UTC with a time zone."
Done when: every new spend row's timestamp carries a time zone, and
existing rows are untouched (no history rewrite / migration).

Proof points (all $0: real SQLite files in a temp dir, mocked providers,
no HTTP of any kind — the ledger has no provider client at all):
  1. The single timestamp helper returns aware UTC with a Z or +00:00
     suffix (the only datetime call in spend_ledger.py; job_recovery.py
     reuses it via L._now_iso for its events/results inserts).
  2. A full new-row flow (init_run -> plan -> reserve -> mark_submitted ->
     mark_terminal -> reconcile) writes ONLY suffixed timestamps into
     runs, jobs and receipts.
  3. Recovery writes (job_recovery.ingest_event) stay suffixed too, for
     events, results and the jobs row it advances.
  4. Administrative writers (park_run/unpark, cancel) stay suffixed.
  5. Existing rows are untouched: a run row seeded with a pre-fix naive
     timestamp keeps that exact naive created_at through later ledger
     writes on the same run (ledger UPDATEs only ever touch updated_at).

Run: python3 core/test_spend_utc_f11.py
"""
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import spend_ledger as L                     # noqa: E402  (module under test)
import job_recovery as JR                    # noqa: E402  (sibling writer)

FAILS = []

# Acceptance regex: ISO-8601, second precision, UTC zone suffix (either form).
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)$")


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def tmp_db():
    d = tempfile.mkdtemp(prefix="f11-")
    return os.path.join(d, "spend.db"), d


def col_vals(db, table, cols):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT %s FROM %s" % (",".join(cols), table)).fetchall()
    finally:
        conn.close()


def assert_table_suffixed(db, table, cols, label):
    rows = col_vals(db, table, cols)
    check("%s: rows present" % label, all(all(c is not None for c in r)
                                          for r in rows),
          "%d rows" % len(rows))
    for r in rows:
        for c, v in zip(cols, r):
            if TS.match(v or "") is None:
                check("%s.%s suffixed" % (table, c), False, repr(v))
                return
    check("%s: all %s carry Z/+00:00" % (label, "/".join(cols)), True)


def test_helper_is_aware_utc():
    v = L._now_iso()
    check("helper matches Z/+00:00 pattern", TS.match(v) is not None, v)
    dt = datetime.fromisoformat(v)
    check("helper parses timezone-aware", dt.tzinfo is not None
          and dt.utcoffset().total_seconds() == 0, str(dt.utcoffset()))


def test_full_flow_new_rows_all_suffixed():
    db, d = tmp_db()
    try:
        r = L.init_run(db, "r-f11", 100)
        assert r["outcome"] == "ok", r
        for res in (
                L.plan(db, "r-f11", "k1", "a1", "d" * 64, 5),
                L.reserve(db, "r-f11", "k1", "a1"),
                L.mark_submitted(db, "r-f11", "k1", "a1", "task-1"),
                L.mark_terminal(db, "r-f11", "k1", "a1", "succeeded"),
                L.reconcile(db, "r-f11", "k1", "a1", "succeeded", 5)):
            assert res["outcome"] == "ok", (res, res.get("reason_code"))
        assert_table_suffixed(db, "runs", ("created_at", "updated_at"),
                              "flow/runs")
        assert_table_suffixed(db, "jobs", ("created_at", "updated_at"),
                              "flow/jobs")
        assert_table_suffixed(db, "receipts", ("created_at",),
                              "flow/receipts")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_recovery_writes_suffixed():
    db, d = tmp_db()
    try:
        assert L.init_run(db, "r-f11b", 100)["outcome"] == "ok"
        assert L.plan(db, "r-f11b", "k2", "a1", "d" * 64, 5)["outcome"] == "ok"
        ev = JR.ingest_event(db, "r-f11b", "k2", "a1", "pev-1", provider_seq=2,
                             status="accepted", payload={"remote_task_id": "t-2"},
                             artifact_path="/tmp/f11/clip.mp4",
                             artifact_sha="ab" * 32, artifact_bytes=11)
        assert ev["outcome"] == "ok", (ev, ev.get("reason_code"))
        assert_table_suffixed(db, "events", ("created_at",), "recovery/events")
        assert_table_suffixed(db, "results", ("created_at",), "recovery/results")
        assert_table_suffixed(db, "jobs", ("created_at", "updated_at"),
                              "recovery/jobs")
        # Second ingest on the same job advances updated_at only.
        ev2 = JR.ingest_event(db, "r-f11b", "k2", "a1", "pev-2",
                              provider_seq=3, status="progress")
        assert ev2["outcome"] == "ok", (ev2, ev2.get("reason_code"))
        assert_table_suffixed(db, "jobs", ("updated_at",),
                              "recovery/jobs-after-second-event")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_admin_writers_suffixed():
    db, d = tmp_db()
    try:
        assert L.init_run(db, "r-f11c", 100)["outcome"] == "ok"
        assert L.plan(db, "r-f11c", "k3", "a1", "d" * 64, 5)["outcome"] == "ok"
        assert L.cancel(db, "r-f11c", "k3", "a1")["outcome"] == "ok"
        assert L.park_run(db, "r-f11c")["outcome"] == "parked"
        assert L.unpark(db, "r-f11c")["outcome"] == "ok"
        assert_table_suffixed(db, "jobs", ("created_at", "updated_at"),
                              "admin/jobs")
        assert_table_suffixed(db, "runs", ("updated_at",), "admin/runs")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_history_untouched():
    """A pre-fix row with a naive timestamp is never rewritten by the ledger."""
    db, d = tmp_db()
    try:
        assert L.init_run(db, "r-f11d", 100)["outcome"] == "ok"
        # Simulate pre-fix history by hand (test-only write, not the ledger):
        conn = sqlite3.connect(db)
        conn.execute("UPDATE runs SET created_at=?, updated_at=? "
                     "WHERE run_id=?", ("2026-10-08T12:34:56",
                                        "2026-10-08T12:34:56", "r-f11d"))
        conn.commit()
        conn.close()
        # New ledger traffic on that same run.
        assert L.plan(db, "r-f11d", "k4", "a1", "d" * 64, 5)["outcome"] == "ok"
        assert L.park_run(db, "r-f11d")["outcome"] == "parked"
        assert L.unpark(db, "r-f11d")["outcome"] == "ok"
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT created_at, updated_at FROM runs WHERE "
                           "run_id=?", ("r-f11d",)).fetchone()
        conn.close()
        check("history created_at untouched (still naive)",
              row[0] == "2026-10-08T12:34:56", repr(row[0]))
        check("history updated_at refreshed WITH zone",
              TS.match(row[1] or "") is not None, repr(row[1]))
        assert_table_suffixed(db, "jobs", ("created_at", "updated_at"),
                              "history/new-jobs")
    finally:
        shutil.rmtree(d, ignore_errors=True)


TESTS = [
    test_helper_is_aware_utc,
    test_full_flow_new_rows_all_suffixed,
    test_recovery_writes_suffixed,
    test_admin_writers_suffixed,
    test_history_untouched,
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
    print("all %d F11 UTC checks passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())