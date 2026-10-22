#!/usr/bin/env python3
"""W02-U2: paid-attempt identity, ordinal and truthful accounting (D20/D21).

Skill 75 Universal Repair Spec v1.1 sections 8.4 + 17.10 counterexamples.
All checks are $0: temporary SQLite files, no provider calls, no network.

Proof points:
  1. Repair cap zero refuses the second AND third attempts (nothing persisted).
  2. The explicit-ordinal-2 harness control still returns REPAIR_CAP.
  3. The omitted-ordinal call shape (the dispatcher's actual shape) no longer
     persists ordinal 1 twice: ordinals derive from persisted history inside
     the allocation transaction and stay monotonic.
  4. Passing ordinal 1 again is refused (ORDINAL_MISMATCH), never persisted.
  5. Two concurrent authorized creative retakes commit unique ledger-minted
     identities with correct allowance accounting (and cap exhaustion refuses
     the one repair too many).
  6. An uncertain submission must be reconciled, with provider lookup
     evidence recorded, before any resubmission; the categories
     transport_retry / failed_job_retry / creative_retake derive from
     persisted state and a QC-failed provider success stays succeeded.
  7. Fractional credits convert exactly through the recorded contract and
     missing actuals stay reserved-unknown (a reported 0 is not "missing").
  8. One multi-track provider job keeps billable-job, track, saved-artifact
     and selected-artifact counts distinct.

Run: python3 core/test_spend_attempts_w02u2.py
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import spend_ledger as L                     # noqa: E402  (module under test)

FAILS = []
MINTED = re.compile(r"^att-\d{4}-[0-9a-f]{12}$")


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def tmp_db(**run_kw):
    d = tempfile.mkdtemp(prefix="w02u2-")
    db = os.path.join(d, "spend.db")
    r = L.init_run(db, run_kw.pop("run_id", "r1"), run_kw.pop("ceiling", 1000),
                   **run_kw)
    assert r["outcome"] == "ok", r
    return db, d


def rows(db, sql, args=()):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def to_failed(db, run_id, key, attempt_id, cost=0):
    """Drive one attempt to a confirmed failed provider result."""
    assert L.reserve(db, run_id, key, attempt_id)["outcome"] == "ok"
    assert L.mark_submitted(db, run_id, key, attempt_id,
                            "task-%s" % attempt_id)["outcome"] == "ok"
    assert L.mark_terminal(db, run_id, key, attempt_id, "failed")[
        "outcome"] == "ok"
    assert L.reconcile(db, run_id, key, attempt_id, "failed", cost)[
        "outcome"] == "ok"


def to_succeeded(db, run_id, key, attempt_id, cost=0, settle=True):
    """Drive one attempt to a successful provider result; settle=True also
    reconciles the actual charge, settle=False leaves it unreported."""
    assert L.reserve(db, run_id, key, attempt_id)["outcome"] == "ok"
    assert L.mark_submitted(db, run_id, key, attempt_id,
                            "task-%s" % attempt_id)["outcome"] == "ok"
    assert L.mark_terminal(db, run_id, key, attempt_id, "succeeded")[
        "outcome"] == "ok"
    if settle:
        assert L.reconcile(db, run_id, key, attempt_id, "succeeded", cost)[
            "outcome"] == "ok"


# --- 1. repair cap zero refuses second AND third attempts --------------------
def test_cap_zero_refuses_second_and_third():
    db, d = tmp_db(run_id="cap0", repair_cap=0)
    try:
        # Dispatcher's actual call shape: attempt ordinal OMITTED.
        a1 = L.plan(db, "cap0", "k1", "a1", "digest-1", 5, stage="music")
        check("cap0: first attempt ok", a1["outcome"] == "ok", str(a1))
        a2 = L.plan(db, "cap0", "k1", "a2", "digest-2", 5, stage="music")
        check("cap0: second attempt refused", a2["outcome"] == "rejected",
              str(a2))
        check("cap0: second attempt REPAIR_CAP",
              a2["reason_code"] == "REPAIR_CAP", a2["reason_code"])
        a3 = L.plan(db, "cap0", "k1", "a3", "digest-3", 5, stage="music")
        check("cap0: third attempt refused",
              a3["outcome"] == "rejected"
              and a3["reason_code"] == "REPAIR_CAP", str(a3))
        got = rows(db, "SELECT attempt_no FROM jobs WHERE run_id='cap0'")
        check("cap0: exactly one row persisted", len(got) == 1, str(got))
        check("cap0: it carries ordinal 1", got == [(1,)], str(got))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- 2. explicit ordinal 2 still returns REPAIR_CAP -------------------------
def test_explicit_ordinal_two_still_repair_cap():
    db, d = tmp_db(run_id="cap0b", repair_cap=0)
    try:
        assert L.plan(db, "cap0b", "k1", "a1", "digest-1", 5)["outcome"] == "ok"
        ctrl = L.plan(db, "cap0b", "k1", "a2", "digest-2", 5, attempt_no=2)
        check("harness control: explicit ordinal 2 -> REPAIR_CAP",
              ctrl["outcome"] == "rejected"
              and ctrl["reason_code"] == "REPAIR_CAP", str(ctrl))
        # The control is unconditional: claimed ordinal 2 never buys under 0.
        fresh = L.plan(db, "cap0b", "k2", "b1", "digest-b", 5, attempt_no=2)
        check("claimed ordinal 2 on first attempt -> REPAIR_CAP",
              fresh["reason_code"] == "REPAIR_CAP", str(fresh))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- 3+4. omitted ordinal derives history; passing 1 again refused -----------
def test_omitted_ordinal_derived_and_one_again_refused():
    db, d = tmp_db(run_id="ord", repair_cap=2)
    try:
        a1 = L.plan(db, "ord", "k1", "a1", "digest-1", 5)
        assert a1["outcome"] == "ok", a1
        to_failed(db, "ord", "k1", "a1")
        a2 = L.plan(db, "ord", "k1", "a2", "digest-2", 5)   # ordinal omitted
        check("omitted ordinal: second attempt ok", a2["outcome"] == "ok",
              str(a2))
        check("omitted ordinal: derived 2, never another 1",
              a2["evidence"]["attempt_no"] == 2
              and a2["evidence"]["retry_category"] == "failed_job_retry",
              str(a2["evidence"]))
        check("omitted ordinal: caller label kept, accounting ledger-owned",
              a2["evidence"]["identity_minted_by_ledger"] is False
              and a2["attempt_id"] == "a2",
              str((a2["attempt_id"], a2["evidence"])))
        check("omitted ordinal: minted identities are content-derived",
              MINTED.match(L._mint_attempt_id("ord", "k1", 2, "digest-2",
                                              "failed_job_retry", "")) is not
              None
              and L._mint_attempt_id("ord", "k1", 1, "digest-2",
                                     "initial", "") !=
              L._mint_attempt_id("ord", "k1", 2, "digest-2",
                                 "failed_job_retry", ""),
              "pattern/uniqueness")
        to_failed(db, "ord", "k1", a2["attempt_id"], cost=3)
        again = L.plan(db, "ord", "k1", "a1", "digest-1", 5)
        check("passing the same attempt id again -> DUPLICATE_ATTEMPT",
              again["reason_code"] == "DUPLICATE_ATTEMPT", str(again))
        one = L.plan(db, "ord", "k1", "x1", "digest-x", 5, attempt_no=1)
        check("passing 1 again -> ORDINAL_MISMATCH",
              one["reason_code"] == "ORDINAL_MISMATCH", str(one))
        got = rows(db, "SELECT attempt_no FROM jobs WHERE run_id='ord' "
                   "ORDER BY attempt_no")
        check("ordinals stay monotonic 1,2", got == [(1,), (2,)], str(got))
        s = L.summary(db, "ord")
        check("retry cost derives from persisted ordinal",
              s["evidence"]["retry_cost"] == 3, str(s["evidence"]["retry_cost"]))
        check("repair accounting: 1 of 2 used",
              s["evidence"]["repairs_used"] == 1
              and s["evidence"]["repairs_remaining"] == 1,
              str((s["evidence"]["repairs_used"],
                   s["evidence"]["repairs_remaining"])))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- 5. two concurrent authorized retakes -----------------------------------
def test_concurrent_authorized_retakes():
    db, d = tmp_db(run_id="cc", repair_cap=2)
    try:
        first = L.allocate_attempt(db, "cc", "k1", "digest-1", estimated_cost=5)
        assert first["outcome"] == "ok", first
        aid1 = first["attempt_id"]
        to_succeeded(db, "cc", "k1", aid1, cost=5)
        results = []
        barrier = threading.Barrier(2)

        def retake(auth):
            barrier.wait()
            results.append(L.allocate_attempt(
                db, "cc", "k1", "digest-%s" % auth, "creative_retake",
                auth_ref=auth, estimated_cost=5))

        ts = [threading.Thread(target=retake, args=(a,))
              for a in ("auth-A", "auth-B")]
        [t.start() for t in ts]
        [t.join() for t in ts]
        oks = [r for r in results if r["outcome"] == "ok"]
        check("concurrent retakes: both committed", len(oks) == 2,
              str([(r["outcome"], r["reason_code"]) for r in results]))
        ids = {r["attempt_id"] for r in oks}
        ords = sorted(r["evidence"]["attempt_no"] for r in oks)
        check("concurrent retakes: unique committed identities",
              len(ids) == 2 and all(MINTED.match(i) for i in ids), str(ids))
        check("concurrent retakes: ordinals 2 and 3", ords == [2, 3], str(ords))
        s = L.summary(db, "cc")
        check("concurrent retakes: both consume repair allowance",
              s["evidence"]["repairs_used"] == 2
              and s["evidence"]["repairs_remaining"] == 0,
              str((s["evidence"]["repairs_used"],
                   s["evidence"]["repairs_remaining"])))
        # Cap exhaustion: one repair too many is refused.
        db2, d2 = tmp_db(run_id="cc2", repair_cap=1)
        try:
            f = L.allocate_attempt(db2, "cc2", "k1", "digest-1", estimated_cost=5)
            to_succeeded(db2, "cc2", "k1", f["attempt_id"], cost=5)
            r1 = L.allocate_attempt(db2, "cc2", "k1", "digest-2",
                                    "creative_retake", auth_ref="auth-1",
                                    estimated_cost=5)
            r2 = L.allocate_attempt(db2, "cc2", "k1", "digest-3",
                                    "creative_retake", auth_ref="auth-2",
                                    estimated_cost=5)
            check("cap 1: first retake ok", r1["outcome"] == "ok", str(r1))
            check("cap 1: second retake REPAIR_CAP",
                  r2["outcome"] == "rejected"
                  and r2["reason_code"] == "REPAIR_CAP", str(r2))
        finally:
            shutil.rmtree(d2, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- 6. uncertain jobs: reconcile + provider lookup before resubmission ------
def test_uncertain_reconcile_and_categories():
    db, d = tmp_db(run_id="unk", repair_cap=4)
    try:
        a1 = L.plan(db, "unk", "k1", "a1", "digest-1", 5)
        assert a1["outcome"] == "ok", a1
        assert L.reserve(db, "unk", "k1", "a1")["outcome"] == "ok"
        assert L.mark_submitted(db, "unk", "k1", "a1", "t1")["outcome"] == "ok"
        assert L.mark_unknown(db, "unk", "k1", "a1")["outcome"] == "ok"
        early = L.plan(db, "unk", "k1", "a2", "digest-1", 5)
        check("uncertain job: resubmission refused first",
              early["reason_code"] == "RECONCILE_FIRST", str(early))
        rec = L.reconcile(db, "unk", "k1", "a1", "failed", 0,
                          outcome_class="accepted_response_lost")
        check("uncertain job: reconciled", rec["outcome"] == "ok", str(rec))
        no_lookup = L.plan(db, "unk", "k1", "a2", "digest-1", 5)
        check("resubmission without lookup evidence refused",
              no_lookup["reason_code"] == "PROVIDER_LOOKUP_REQUIRED",
              str(no_lookup))
        lu = L.record_provider_lookup(db, "unk", "k1", "a1", "lookup-42")
        check("provider lookup recorded", lu["outcome"] == "ok", str(lu))
        tr = L.plan(db, "unk", "k1", "a2", "digest-1", 5)  # same digest
        check("same uncertain submission -> transport_retry",
              tr["outcome"] == "ok"
              and tr["evidence"]["retry_category"] == "transport_retry",
              str(tr))
        to_failed(db, "unk", "k1", tr["attempt_id"], cost=1)
        fr = L.plan(db, "unk", "k1", "x1", "digest-NEW", 5)
        check("changed request after failure -> failed_job_retry",
              fr["outcome"] == "ok"
              and fr["evidence"]["retry_category"] == "failed_job_retry",
              str(fr))
        claimed = L.plan(db, "unk", "k1", "x2", "digest-2", 5,
                         retry_category="creative_retake", auth_ref="auth-1")
        check("falsified category claim refused",
              claimed["reason_code"] == "RETRY_CATEGORY_MISMATCH",
              str(claimed))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- 6b. QC failure keeps the provider success ------------------------------
def test_qc_failure_keeps_provider_success():
    db, d = tmp_db(run_id="qc", repair_cap=2)
    try:
        first = L.allocate_attempt(db, "qc", "k1", "digest-1", estimated_cost=5)
        aid = first["attempt_id"]
        to_succeeded(db, "qc", "k1", aid, cost=5)
        q = L.record_qc_verdict(db, "qc", "k1", aid, "fail",
                                check_id="creative-qc")
        check("creative QC failure recorded", q["outcome"] == "ok", str(q))
        job = rows(db, "SELECT state,final_outcome FROM jobs "
                   "WHERE run_id='qc' AND attempt_id=?", (aid,))
        check("provider success stays a successful provider result",
              job == [("reconciled", "succeeded")], str(job))
        missing = L.allocate_attempt(db, "qc", "k1", "digest-2",
                                     "creative_retake", estimated_cost=5)
        check("retake without authorization refused",
              missing["reason_code"] == "MISSING_AUTH_REF", str(missing))
        rt = L.allocate_attempt(db, "qc", "k1", "digest-2", "creative_retake",
                                auth_ref="auth-1", estimated_cost=5)
        check("authorized retake allocates on top of the success",
              rt["outcome"] == "ok"
              and rt["evidence"]["retry_category"] == "creative_retake",
              str(rt))
        dup = L.allocate_attempt(db, "qc", "k1", "digest-3", "creative_retake",
                                 auth_ref="auth-1", estimated_cost=5)
        check("same authorization cannot fund twice",
              dup["reason_code"] == "DUPLICATE_AUTHORIZATION", str(dup))
        job = rows(db, "SELECT final_outcome FROM jobs "
                   "WHERE run_id='qc' AND attempt_id=?", (aid,))
        check("prior outcome still succeeded after retake",
              job == [("succeeded",)], str(job))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- 7. fractional credits and missing actuals ------------------------------
def test_fractional_credits_and_missing_actuals():
    db, d = tmp_db(run_id="money", ceiling=100, credit_to_subunit_num=3,
                   credit_to_subunit_den=2)
    try:
        sub, residue = L.credits_to_subunits(2500000, 3, 2)
        check("fractional credits convert by floor",
              (sub, residue) == (3, 1500000), str((sub, residue)))
        check("conversion residue never lost",
              sub * L.MICRO_PER_CREDIT * 2 + residue == 2500000 * 3,
              str((sub, residue)))
        a = L.plan(db, "money", "kA", "a1", "digest-A", 10,
                   est_credits_micro=2500000)
        assert a["outcome"] == "ok", a
        to_succeeded(db, "money", "kA", "a1", settle=False)
        rec = L.reconcile(db, "money", "kA", "a1", "succeeded", None,
                          actual_credits_micro=1250000,
                          outcome_class="accepted_delivered")
        check("reconcile from reported credits only", rec["outcome"] == "ok",
              str(rec))
        check("subunits derived exactly through the contract",
              rec["evidence"]["actual_cost"] == 1,  # floor(1.25 * 3/2) = 1
              str(rec["evidence"]))
        check("fractional usage preserved exactly",
              rec["evidence"]["actual_credits_micro"] == 1250000
              and rec["evidence"]["credit_residue"] == 1750000,
              str(rec["evidence"]))
        b = L.plan(db, "money", "kB", "b1", "digest-B", 7,
                   est_credits_micro=2500000)
        assert b["outcome"] == "ok", b
        assert L.reserve(db, "money", "kB", "b1")["outcome"] == "ok"
        assert L.mark_submitted(db, "money", "kB", "b1", "tb")["outcome"] == "ok"
        assert L.mark_terminal(db, "money", "kB", "b1", "succeeded")[
            "outcome"] == "ok"
        # No reconcile: the actual charge is unreported.
        s = L.summary(db, "money")
        ev = s["evidence"]
        check("missing actual stays reserved-unknown",
              ev["unknown_or_reserved_cost"] == 7, str(ev))
        check("missing actual never becomes an asserted actual",
              ev["actual_cost"] == 1, str(ev["actual_cost"]))
        check("credits buckets exact",
              ev["credits_micro"]["actual_micro"] == 1250000
              and ev["credits_micro"]["unknown_or_reserved_micro"] == 2500000,
              str(ev["credits_micro"]))
        ref = L.reconcile(db, "money", "kB", "b1", "succeeded", None)
        check("reconcile with no reported actual refused",
              ref["reason_code"] == "UNKNOWN_PRICE", str(ref))
        c = L.plan(db, "money", "kC", "c1", "digest-C", 4)
        assert c["outcome"] == "ok", c
        to_succeeded(db, "money", "kC", "c1", settle=False)
        z = L.reconcile(db, "money", "kC", "c1", "succeeded", 0)
        check("reported zero is an asserted actual", z["outcome"] == "ok",
              str(z))
        s = L.summary(db, "money")
        check("asserted zero is not 'missing'",
              s["evidence"]["unknown_or_reserved_cost"] == 7
              and s["evidence"]["actual_cost"] == 1, str(s["evidence"]))
        bad = L.plan(db, "money", "kD", "d1", "digest-D", 1.5)
        check("float money refused at the boundary",
              bad["reason_code"] == "BAD_MONEY", str(bad))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- 8. one multi-track provider job keeps the counts distinct ---------------
def test_multi_track_counts_distinct():
    db, d = tmp_db(run_id="mt", ceiling=1000)
    try:
        a = L.allocate_attempt(db, "mt", "k1", "digest-1", estimated_cost=10)
        aid = a["attempt_id"]
        assert L.reserve(db, "mt", "k1", aid)["outcome"] == "ok"
        assert L.mark_submitted(db, "mt", "k1", aid, "task-mt")["outcome"] == "ok"
        pj = L.record_provider_job(db, "mt", "k1", aid, "task-mt",
                                   billable=1, credits_micro=1500000)
        check("provider job registered", pj["outcome"] == "ok", str(pj))
        for n, path, saved in ((1, "/t/one.mp3", 1), (2, "/t/two.mp3", 0),
                               (3, "/t/three.mp3", 1)):
            rt = L.record_track(db, "mt", "k1", aid, n, artifact_path=path,
                                saved=saved)
            assert rt["outcome"] == "ok", rt
        before = L.summary(db, "mt")["evidence"]["counts"]
        check("unselected run: the four counts read as four different numbers",
              (before["billable_jobs"], before["provider_tracks"],
               before["saved_artifacts"], before["selected_artifacts"])
              == (1, 3, 2, 0), str(before))
        sel = L.select_track(db, "mt", "k1", aid, 1)
        check("one selected artifact", sel["outcome"] == "ok", str(sel))
        s = L.summary(db, "mt")
        c = s["evidence"]["counts"]
        check("billable jobs == 1 for one provider job",
              c["billable_jobs"] == 1, str(c))
        check("provider tracks == 3", c["provider_tracks"] == 3, str(c))
        check("saved artifacts == 2", c["saved_artifacts"] == 2, str(c))
        check("selected artifacts == 1", c["selected_artifacts"] == 1, str(c))
        check("generation calls never inflate from tracks",
              c["number_of_generation_calls"] == 1, str(c))
        check("no measure is conflated with another",
              c["billable_jobs"] != c["provider_tracks"]
              and c["saved_artifacts"] != c["provider_tracks"]
              and c["selected_artifacts"] != c["saved_artifacts"],
              str(c))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- 9. 1.0.0 schema migrates in place, rows preserved ----------------------
OLD_DDL = """
CREATE TABLE schema_info(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE runs(
  run_id TEXT PRIMARY KEY, ceiling INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD', qc_allowance INTEGER NOT NULL DEFAULT 0,
  repair_cap INTEGER NOT NULL DEFAULT 2, status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE jobs(
  logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL,
  run_id TEXT NOT NULL REFERENCES runs(run_id), request_digest TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT '', attempt_no INTEGER NOT NULL DEFAULT 1,
  state TEXT NOT NULL CHECK(state IN
    ('planned','reserved','submitted','unknown','succeeded','failed','reconciled')),
  final_outcome TEXT, remote_task_id TEXT,
  estimated_cost INTEGER, actual_cost INTEGER,
  owner TEXT NOT NULL DEFAULT '', lease_expires INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(logical_key, attempt_id));
CREATE TABLE receipts(
  receipt_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
  logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL, amount INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD', provider_ref TEXT, evidence_ref TEXT,
  created_at TEXT NOT NULL);
CREATE TABLE events(
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
  logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL, kind TEXT NOT NULL,
  provider_event_id TEXT NOT NULL, provider_seq INTEGER NOT NULL DEFAULT 0,
  status TEXT, payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
  UNIQUE(run_id, logical_key, attempt_id, provider_event_id));
CREATE TABLE results(
  run_id TEXT NOT NULL, logical_key TEXT NOT NULL, attempt_id TEXT NOT NULL,
  artifact_path TEXT NOT NULL, sha256 TEXT, bytes_n INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  PRIMARY KEY(run_id, logical_key, attempt_id));
"""


def test_migration_100_preserves_rows():
    d = tempfile.mkdtemp(prefix="w02u2-mig-")
    db = os.path.join(d, "old.db")
    try:
        conn = sqlite3.connect(db)
        conn.executescript(OLD_DDL)
        conn.execute("INSERT INTO schema_info(key,value) "
                     "VALUES('schema_version','1.0.0')")
        conn.execute("INSERT INTO runs(run_id,ceiling,created_at,updated_at) "
                     "VALUES('old',100,'2026-10-08T12:00:00','2026-10-08T12:00:00')")
        conn.execute("INSERT INTO jobs(logical_key,attempt_id,run_id,"
                     "request_digest,attempt_no,state,final_outcome,"
                     "estimated_cost,created_at,updated_at) "
                     "VALUES('k1','a1','old','digest',1,'reconciled','failed',5,"
                     "'2026-10-08T12:00:00','2026-10-08T12:00:00')")
        conn.commit()
        conn.close()
        out = L.summary(db, "old")
        check("1.0.0 DB opens through migration", out["outcome"] == "ok",
              str(out))
        ver = rows(db, "SELECT value FROM schema_info WHERE key='schema_version'")
        check("schema stamped 1.1.0", ver == [("1.1.0",)], str(ver))
        kept = rows(db, "SELECT created_at,attempt_no,state FROM jobs "
                    "WHERE run_id='old'")
        check("existing row untouched",
              kept == [("2026-10-08T12:00:00", 1, "reconciled")], str(kept))
        nxt = L.plan(db, "old", "k1", "a2", "digest-2", 5)
        check("allocation works on migrated DB", nxt["outcome"] == "ok",
              str(nxt))
        check("migrated history keeps ordinal monotonicity",
              nxt["evidence"]["attempt_no"] == 2, str(nxt["evidence"]))
    finally:
        shutil.rmtree(d, ignore_errors=True)


TESTS = [
    test_cap_zero_refuses_second_and_third,
    test_explicit_ordinal_two_still_repair_cap,
    test_omitted_ordinal_derived_and_one_again_refused,
    test_concurrent_authorized_retakes,
    test_uncertain_reconcile_and_categories,
    test_qc_failure_keeps_provider_success,
    test_fractional_credits_and_missing_actuals,
    test_multi_track_counts_distinct,
    test_migration_100_preserves_rows,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d W02-U2 attempt-accounting suites passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
