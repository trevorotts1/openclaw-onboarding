#!/usr/bin/env python3
"""Provider lookup evidence is required before a PAID RESUBMISSION.

Rewritten deliberately. The preserved WIP version of this file pinned the
refusal inside `reconcile()`; that is wrong for this distribution because it
kills the abandon path (an undeterminable attempt could never be closed out)
and contradicts the contract: `reconcile` stays permissive, the gate belongs at
the resubmission (`plan`). What still holds from the WIP: the hole it was
written against is real -- `plan()` treats a reconciled `failed` job as grounds
for a NEW paid attempt, so without a gate a timed-out paid take could be
resubmitted with no provider record at all.

Pinned here:
  (a) reconcile with no provider/evidence reference is ACCEPTED (permissive);
      it writes state=reconciled/failed and a receipt with empty refs;
  (b) a resubmission after that is REFUSED with PROVIDER_LOOKUP_REQUIRED, and
      no second job row is minted;
  (c) whitespace-only refs do not count as evidence (still refused at plan);
  (d) reconcile WITH provider_ref or WITH evidence_ref still works and still
      permits the retry as attempt 2, keeping the reference on the receipt;
  (e) a succeeded outcome needs no reference and still never unlocks a retry;
  (f) an unknown/cancelled attempt still forbids a retry while active;
  (g) an attempt that never reached a provider (no remote_task_id) reconciles
      and retries without a reference -- the shipped submit-failure path;
  (h) a pre-fix ledger (uncertain row, no evidence) is gated on resubmission;
  (i) the CLI exits non-zero (rejected=5) with the typed code -- the contract's
      operator-facing requirement;
  (j) identity/ordinal behaviour is unchanged (S1/S4/S6/S7/S8).

stdlib only, no network, no paid calls.

Run from the skill root:
  python3 scripts/core/test_provider_evidence_required.py
"""
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

L = importlib.import_module("spend_ledger")

FAILS = []
_TEST_FAILS = []
RUN = "run-pev"


class _CheckFailure(AssertionError):
    """Raised at the END of a test that recorded a failed check."""


def check(name, got, want):
    if got == want:
        print("ok %s" % name)
    else:
        print("FAIL %s: got %r want %r" % (name, got, want))
        FAILS.append(name)
        _TEST_FAILS.append(name)


def _finish():
    """Fail the CALLING test after every check in it has run.

    Why deferred: if check() raised immediately, only the first bad assertion
    would ever be reported and the full failure list would be lost. But a test
    function that never raises is invisible to pytest, which collects these
    functions directly and never calls main() -- it would report green on a
    tree whose checks all failed. Tests are wrapped at import time (see the
    loop at the end of this module) so both runners agree: every check still
    runs, then the test raises.
    """
    failed = list(_TEST_FAILS)
    _TEST_FAILS.clear()
    if failed:
        raise _CheckFailure("checks failed: %s" % ", ".join(failed))


def _guarded(fn):
    def wrapper(*a, **kw):
        try:
            result = fn(*a, **kw)
        except Exception:
            _TEST_FAILS.clear()      # an unexpected error: report it as-is
            raise
        _finish()                    # raises only if a check in THIS test failed
        return result
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def fresh(prefix="pev-"):
    tmp = tempfile.mkdtemp(prefix=prefix)
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, RUN, 10000)
    return db


def q(db, sql, params=()):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, params).fetchone()
    finally:
        con.close()


def _to_unknown(db, key, digest, cost=100):
    """plan -> reserve -> submitted -> unknown. Returns the minted id."""
    p = L.plan(db, RUN, key, "", digest, cost)
    assert p["outcome"] == "ok", p
    aid = p["attempt_id"]
    assert L.reserve(db, RUN, key, aid)["outcome"] == "ok"
    assert L.mark_submitted(db, RUN, key, aid, "remote-1")["outcome"] == "ok"
    assert L.mark_unknown(db, RUN, key, aid)["outcome"] == "ok"
    return aid


def _retry(db, key, digest, cost=100):
    return L.plan(db, RUN, key, "", digest, cost)


def test_a_reconcile_stays_permissive():
    db = fresh()
    d = L.digest_request({"k": 1})
    aid = _to_unknown(db, "video/v1", d)
    r = L.reconcile(db, RUN, "video/v1", aid, "failed", 100,
                    provider_ref="", evidence_ref="")
    check("a1: reconcile with no refs is accepted (abandon path stays open)",
          r["outcome"], "ok")
    check("a2: the job moved to reconciled/failed",
          q(db, "SELECT state,final_outcome FROM jobs WHERE attempt_id=?",
            (aid,)), ("reconciled", "failed"))
    check("a3: the receipt records the empty evidence",
          q(db, "SELECT provider_ref,evidence_ref FROM receipts "
                "WHERE attempt_id=?", (aid,)), ("", ""))
    check("a4: the uncertain fact survives the reconcile",
          q(db, "SELECT uncertain FROM jobs WHERE attempt_id=?", (aid,))[0], 1)


def test_b_resubmission_refused():
    db = fresh()
    d = L.digest_request({"k": 2})
    aid = _to_unknown(db, "video/v1", d)
    L.reconcile(db, RUN, "video/v1", aid, "failed", 100)
    p = _retry(db, "video/v1", d)
    check("b1: no paid resubmission without a provider lookup",
          p["outcome"], "rejected")
    check("b2: typed refusal code", p["reason_code"], "PROVIDER_LOOKUP_REQUIRED")
    check("b3: the refusal names the remedy",
          "record_provider_lookup" in p["next_action"], True)
    check("b4: no second job was minted",
          q(db, "SELECT COUNT(*) FROM jobs")[0], 1)


def test_c_whitespace_is_not_evidence():
    db = fresh("pev-ws-")
    d = L.digest_request({"k": 3})
    aid = _to_unknown(db, "video/v1", d)
    r = L.reconcile(db, RUN, "video/v1", aid, "failed", 100,
                    provider_ref="  ", evidence_ref="\t")
    check("c1: whitespace-only refs still reconcile (permissive)",
          r["outcome"], "ok")
    check("c2: but they do not unlock the paid resubmission",
          _retry(db, "video/v1", d)["reason_code"],
          "PROVIDER_LOOKUP_REQUIRED")


def test_d_with_ref_retries():
    for field in ("provider_ref", "evidence_ref"):
        db = fresh("pev-%s-" % field)
        d = L.digest_request({"k": 4})
        aid = _to_unknown(db, "video/v1", d)
        kw = {field: "provider-task-42" if field == "provider_ref"
              else "operator-note://proof"}
        r = L.reconcile(db, RUN, "video/v1", aid, "failed", 100, **kw)
        check("d1[%s]: reconcile with evidence is accepted" % field,
              r["outcome"], "ok")
        p = _retry(db, "video/v1", d)
        check("d2[%s]: the paid retry is permitted" % field,
              p["outcome"], "ok")
        check("d3[%s]: it is attempt 2" % field,
              p["evidence"]["attempt_no"], 2)
        check("d4[%s]: the receipt keeps the ref" % field,
              q(db, "SELECT provider_ref,evidence_ref FROM receipts "
                    "WHERE attempt_id=?", (aid,)),
              ("provider-task-42", "") if field == "provider_ref"
              else ("", "operator-note://proof"))


def test_e_succeeded_needs_no_ref():
    db = fresh("pev-ok-")
    d = L.digest_request({"k": 5})
    aid = _to_unknown(db, "video/v1", d)
    check("e1: reconcile succeeded needs no provider ref",
          L.reconcile(db, RUN, "video/v1", aid, "succeeded", 100)["outcome"],
          "ok")
    check("e2: succeeded does not permit a new paid attempt",
          _retry(db, "video/v1", d)["reason_code"], "MISSING_AUTH_REF")


def test_f_abandon_path():
    db = fresh("pev-unknown-")
    d = L.digest_request({"k": 6})
    _to_unknown(db, "video/v1", d)
    check("f1: an unknown attempt forbids a paid retry",
          _retry(db, "video/v1", d)["reason_code"], "RECONCILE_FIRST")

    db2 = fresh("pev-cancel-")
    d2 = L.digest_request({"k": 7})
    p1 = L.plan(db2, RUN, "video/v2", "", d2, 100)
    a1 = p1["attempt_id"]
    L.reserve(db2, RUN, "video/v2", a1)
    L.mark_submitted(db2, RUN, "video/v2", a1, "remote-1")
    check("f2: cancel with no evidence still works",
          L.cancel(db2, RUN, "video/v2", a1)["outcome"], "ok")
    check("f3: cancelled work sits in unknown",
          q(db2, "SELECT state FROM jobs WHERE attempt_id=?", (a1,))[0],
          "unknown")
    check("f4: and a paid retry is still refused",
          L.plan(db2, RUN, "video/v2", "", d2, 100)["reason_code"],
          "RECONCILE_FIRST")
    check("f5: operator parking stays available",
          L.park_run(db, RUN, "OPERATOR_PARK")["outcome"], "parked")


def test_g_never_submitted():
    """A paid submit that failed before any remote id existed must still be
    reconcilable and retryable: there is no provider task to look up."""
    db = fresh("pev-nosub-")
    d = L.digest_request({"k": 8})
    p = L.plan(db, RUN, "video/v3", "", d, 100)
    a = p["attempt_id"]
    L.reserve(db, RUN, "video/v3", a)
    check("g1: cancel with no remote id",
          L.cancel(db, RUN, "video/v3", a)["outcome"], "ok")
    check("g2: terminal failed",
          L.mark_terminal(db, RUN, "video/v3", a, "failed")["outcome"], "ok")
    check("g3: reconcile failed at zero needs no provider ref",
          L.reconcile(db, RUN, "video/v3", a, "failed", 0)["outcome"], "ok")
    p2 = L.plan(db, RUN, "video/v3", "", d, 100)
    check("g4: and the retry is permitted, as shipped", p2["outcome"], "ok")
    check("g5: as attempt 2", p2["evidence"]["attempt_no"], 2)


def test_h_pre_fix_ledger_is_gated():
    """A ledger written before this fix has uncertain rows with no evidence.
    The gate must catch those too, not only rows created through the new API."""
    db = fresh("pev-legacy-")
    d = L.digest_request({"k": 9})
    aid = _to_unknown(db, "video/v1", d)
    L.reconcile(db, RUN, "video/v1", aid, "failed", 100)
    con = sqlite3.connect(db)
    try:
        con.execute("UPDATE jobs SET uncertain=1 WHERE attempt_id=?", (aid,))
        con.commit()
    finally:
        con.close()
    check("h1: a pre-fix uncertain row is still gated on resubmission",
          _retry(db, "video/v1", d)["reason_code"],
          "PROVIDER_LOOKUP_REQUIRED")


def test_k_existing_ledger_migrates():
    """An existing ledger written before this fix has no `uncertain` column.
    Opening it must add the column without losing rows or the run."""
    db = fresh("pev-mig-")
    p = L.plan(db, RUN, "mig/v1", "", "dmig", 100)
    check("k0: baseline plan on the new schema", p["outcome"], "ok")
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE jobs DROP COLUMN uncertain")
        # the 1.1.0 ledger migrates only from a ledger that declares 1.0.0
        con.execute("UPDATE schema_info SET value='1.0.0' "
                    "WHERE key='schema_version'")
        con.commit()
    finally:
        con.close()
    check("k1: the column is really gone",
          "uncertain" in [r[1] for r in sqlite3.connect(db).execute(
              "PRAGMA table_info(jobs)")], False)
    p2 = L.plan(db, RUN, "mig/v2", "", "dmig2", 100)
    check("k2: an old ledger still plans after reopen", p2["outcome"], "ok")
    check("k3: the column is restored",
          "uncertain" in [r[1] for r in sqlite3.connect(db).execute(
              "PRAGMA table_info(jobs)")], True)
    check("k4: prior rows survived the migration",
          q(db, "SELECT COUNT(*) FROM jobs")[0], 2)


def test_l_migration_backfills_hanging_attempt():
    """The live upgrade case: a job in `unknown` when the column is added must
    be flagged, or it could be reconciled without evidence and retried."""
    db = fresh("pev-backfill-")
    d = L.digest_request({"k": 20})
    hung = _to_unknown(db, "video/hung", d)
    planned = L.plan(db, RUN, "video/planned", "", d, 100)["attempt_id"]

    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE jobs DROP COLUMN uncertain")
        # the 1.1.0 ledger migrates only from a ledger that declares 1.0.0
        con.execute("UPDATE schema_info SET value='1.0.0' "
                    "WHERE key='schema_version'")
        con.commit()
    finally:
        con.close()

    L._open(db).close()          # the migration runs here
    check("l1: a hanging attempt is backfilled to uncertain=1",
          q(db, "SELECT uncertain FROM jobs WHERE attempt_id=?", (hung,))[0], 1)
    check("l2: a merely planned attempt is not backfilled",
          q(db, "SELECT uncertain FROM jobs WHERE attempt_id=?",
            (planned,))[0], 0)

    # the behaviour the backfill exists for: reconcile it without evidence...
    r = L.reconcile(db, RUN, "video/hung", hung, "failed", 100)
    check("l3: reconcile stays permissive after the backfill",
          r["outcome"], "ok")
    p = L.plan(db, RUN, "video/hung", "", d, 100)
    check("l4: and the retry is refused, so the live window is closed",
          p["reason_code"], "PROVIDER_LOOKUP_REQUIRED")


def test_m_receipt_lookup_uses_an_index():
    """The gate's lookup must be index-served, not a table scan. Drops the
    index to simulate a ledger created before it, then reopens."""
    db = fresh("pev-index-")
    d = L.digest_request({"k": 21})
    aid = _to_unknown(db, "video/idx", d)
    L.reconcile(db, RUN, "video/idx", aid, "failed", 100,
                provider_ref="task-idx")

    con = sqlite3.connect(db)
    try:
        con.execute("DROP INDEX idx_receipts_attempt")
        con.commit()
    finally:
        con.close()
    check("m1: index really gone before migration",
          q(db, "SELECT COUNT(*) FROM sqlite_master WHERE type='index' "
                "AND name='idx_receipts_attempt'")[0], 0)

    L._open(db).close()          # the migration recreates it
    check("m2: migration recreates the index",
          q(db, "SELECT COUNT(*) FROM sqlite_master WHERE type='index' "
                "AND name='idx_receipts_attempt'")[0], 1)

    plan = sqlite3.connect(db).execute(
        "EXPLAIN QUERY PLAN SELECT provider_ref,evidence_ref FROM receipts "
        "WHERE run_id=? AND logical_key=? AND attempt_id=?",
        (RUN, "video/idx", aid)).fetchall()
    detail = " | ".join(str(r[-1]) for r in plan)
    check("m3: the lookup names the index", "idx_receipts_attempt" in detail,
          True)
    check("m4: and is not a table scan", "SCAN receipts" in detail, False)


def test_i_cli_exit_code():
    tmp = tempfile.mkdtemp(prefix="pev-cli-")
    db = os.path.join(tmp, "spend.db")
    script = os.path.join(HERE, "spend_ledger.py")

    def cli(*args):
        p = subprocess.run([sys.executable, "-I", script, "--db", db, *args],
                           capture_output=True, text=True)
        try:
            doc = json.loads(p.stdout)
        except ValueError:
            doc = {}
        return p.returncode, doc

    cli("init_run", "--run", RUN, "--ceiling", "10000")
    _, p = cli("plan", "--run", RUN, "--key", "video/v9", "--attempt", "",
               "--digest", "d9", "--est", "100")
    aid = p["attempt_id"]
    cli("reserve", "--run", RUN, "--key", "video/v9", "--attempt", aid)
    cli("mark_submitted", "--run", RUN, "--key", "video/v9", "--attempt", aid,
        "--remote-id", "r9")
    cli("mark_unknown", "--run", RUN, "--key", "video/v9", "--attempt", aid)
    cli("reconcile", "--run", RUN, "--key", "video/v9", "--attempt", aid,
        "--final", "failed", "--actual", "100")
    rc, doc = cli("plan", "--run", RUN, "--key", "video/v9", "--attempt", "",
                  "--digest", "d9", "--est", "100")
    check("i1: the CLI exits non-zero on the refused resubmission", rc, 5)
    check("i2: with the typed code", doc.get("reason_code"),
          "PROVIDER_LOOKUP_REQUIRED")
    check("i3: and mints nothing", doc.get("attempt_id"), "")


def test_j_identity_untouched():
    db = fresh("pev-id-")
    d = L.digest_request({"k": 10})
    p1 = L.plan(db, RUN, "song/v1", "", d, 100)
    a1 = p1["attempt_id"]
    check("j1[S1]: ledger mints the identity",
          p1["evidence"]["identity_minted_by_ledger"], True)
    check("j2[S1]: ordinal derived as 1", p1["evidence"]["attempt_no"], 1)
    L.reserve(db, RUN, "song/v1", a1)
    L.mark_submitted(db, RUN, "song/v1", a1, "remote-1")
    L.mark_terminal(db, RUN, "song/v1", a1, "failed")
    check("j3[S4]: explicit reuse is refused",
          L.plan(db, RUN, "song/v1", a1, d, 100)["reason_code"],
          "DUPLICATE_ATTEMPT")
    L.reconcile(db, RUN, "song/v1", a1, "failed", 100)
    p2 = L.plan(db, RUN, "song/v1", "", d, 100)
    a2 = p2["attempt_id"]
    check("j4[S6]: replay mints", p2["evidence"]["identity_minted_by_ledger"],
          True)
    check("j5[S6]: new id differs", a2 != a1, True)
    check("j6[S7]: no suffix/superstring relation",
          a1 in a2 or a2 in a1, False)
    check("j7[S7]: ordinal 2 from persisted history",
          p2["evidence"]["attempt_no"], 2)
    db3 = fresh("pev-race-")
    d3 = L.digest_request({"k": 11})
    results = []

    def go():
        results.append(L.plan(db3, RUN, "song/v9", "", d3, 100))

    ts = [threading.Thread(target=go) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    oks = [r for r in results if r["outcome"] == "ok"]
    others = [r for r in results if r["outcome"] != "ok"]
    check("j8[S8]: exactly one concurrent plan wins", len(oks), 1)
    check("j9[S8]: the rest are refused, not errors",
          all(r["outcome"] == "rejected" for r in others), True)
    check("j10[S8]: one job row for the key",
          q(db3, "SELECT COUNT(*) FROM jobs WHERE logical_key='song/v9'")[0], 1)


def main():
    for fn in (test_a_reconcile_stays_permissive, test_b_resubmission_refused,
               test_c_whitespace_is_not_evidence, test_d_with_ref_retries,
               test_e_succeeded_needs_no_ref, test_f_abandon_path,
               test_g_never_submitted, test_h_pre_fix_ledger_is_gated,
               test_k_existing_ledger_migrates,
               test_l_migration_backfills_hanging_attempt,
               test_m_receipt_lookup_uses_an_index,
               test_i_cli_exit_code, test_j_identity_untouched):
        try:
            fn()
        except _CheckFailure:
            pass          # the individual check names are already recorded
        except Exception as e:                       # noqa: BLE001
            import traceback
            traceback.print_exc()
            FAILS.append("%s raised %s: %s"
                         % (fn.__name__, type(e).__name__, e))
    print()
    if FAILS:
        print("%d FAILED: %s" % (len(FAILS), ", ".join(map(str, FAILS))))
        return 1
    print("ALL PASS")
    return 0


# Wrap every test so pytest (which calls these functions directly, never
# main()) fails the same way the __main__ runner does. Must run after all test
# functions are defined.
for _name, _fn in list(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        globals()[_name] = _guarded(_fn)


if __name__ == "__main__":
    sys.exit(main())
