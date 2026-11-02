#!/usr/bin/env python3
"""S75-W53 STORE-R4: continuation origin binding, lock-before-clock leases.

Focused suite for the frozen W42 candidate. Real SQLite files in a temp dir,
real writer contention, real threads, no network, no provider, no production
database, no mocked database. Two clock injections are EXPLICIT test hooks
inside the process under test: frozen timestamps and a recording clock that
only observes the module's own clock samples. No validation logic is mocked.

Covered:
  1. BEGIN IMMEDIATE is the first statement and the lease deadline is the
     WORKER's post-lock sample, checked against the earliest instant the lock
     could be acquired. No tolerance for parent scheduling delay.
  2. Fencing: live claims are never stolen, expired claims are taken over
     with a new token, stale tokens refuse, complete/release stay idempotent.
  3. Atomicity: a failing origin insert rolls back the decision and the row;
     a failing event insert rolls back a lease claim.
  4. Huge integer leases are typed MALFORMED_RECORD, never OverflowError.
  5. Origin is bound once at creation: clock rollback, later decisions, replay
     with different arguments, same-timestamp decisions and reopen all return
     the SAME originating ack. Direct enqueue never adopts a later ack.
  6. Legacy rows (written before origin binding) derive only from ONE saved
     receipt that agrees on attempt id and request digest; several possible
     origins refuse AMBIGUOUS_ASSOCIATION, contradictions refuse
     NEEDS_RECOVERY, none return None. Timestamps are never used.
  7. Migration: a real version-1 database migrates and preserves every row;
     reopening repeats safely and existing rows are never rewritten.
  8. A saved replay receipt that parses to JSON null, a list, a string, a
     number or a boolean refuses NEEDS_RECOVERY instead of crashing; the
     refusal rewrites nothing, and a healthy receipt still replays byte-for-
     byte, including a completed continuation, across a real close/reopen.

Run: python3 -I test_state_store_s75w53_store_r4.py
Negative controls: S75_STORE_UNDER_TEST=<other state_store.py> (expect fails).
"""
import importlib.util
import inspect
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_SEARCH = (os.environ.get("S75_STORE_UNDER_TEST"), HERE,
           os.path.abspath(os.path.join(HERE, os.pardir, "scripts", "core")),
           os.path.abspath(os.path.join(HERE, os.pardir, "candidate",
                                        "scripts", "core")),
           os.path.abspath(os.path.join(HERE, os.pardir, "work", "candidate",
                                        "scripts", "core")))
_MODULE_PATH = None
for _candidate in _SEARCH:
    if not _candidate:
        continue
    if os.path.isfile(_candidate) and _candidate.endswith(".py"):
        _MODULE_PATH = _candidate
        break
    if os.path.isfile(os.path.join(_candidate, "state_store.py")):
        _MODULE_PATH = os.path.join(_candidate, "state_store.py")
        break
if _MODULE_PATH is None:
    raise SystemExit("state_store.py not found (set S75_STORE_UNDER_TEST)")
_spec = importlib.util.spec_from_file_location("state_store", _MODULE_PATH)
ss = importlib.util.module_from_spec(_spec)
sys.modules["state_store"] = ss
_spec.loader.exec_module(ss)

FAILS = []
TMPDIRS = []
DECISION = {"answer": "keep_one", "approval_id": "ap-1"}
LEASE = 0.3
HOLD = 0.5


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def raises(name, fn, exc, code=None, contains=None):
    try:
        fn()
    except exc as e:
        ok = True
        detail = repr(e)
        if code is not None and getattr(e, "code", None) != code:
            ok = False
            detail = "code=%r want %r" % (getattr(e, "code", None), code)
        if contains is not None and contains not in str(e):
            ok = False
            detail = "message %r lacks %r" % (str(e), contains)
        check(name, ok, detail)
        return e
    except Exception as e:                       # noqa: BLE001
        check(name, False, "raised %s: %s" % (type(e).__name__, e))
        return None
    check(name, False, "no %s raised" % exc.__name__)
    return None


def newdir(prefix="s75w53-"):
    d = tempfile.mkdtemp(prefix=prefix)
    TMPDIRS.append(d)
    return d


def db_path(d):
    return os.path.join(d, "state.sqlite3")


def _history(st):
    """Every saved row a refusal must leave untouched, byte-identical."""
    return {
        "decisions": st.con.execute(
            "SELECT run_id, ack_id, channel, decision, receipt, at"
            " FROM decisions ORDER BY ack_id").fetchall(),
        "continuations": st.con.execute(
            "SELECT id, run_id, stage, op, identity, request_digest,"
            " attempt_id, state, claimed_by, created_at, updated_at,"
            " claim_token, lease_expires FROM continuations ORDER BY id")
        .fetchall(),
        "origins": st.con.execute(
            "SELECT continuation_id, run_id, ack_id, origin_source, bound_at"
            " FROM continuation_origins ORDER BY continuation_id").fetchall()}


def seed_pending(d, ack="msg-1", stage="music", op="rejudge",
                 digest="sha256:paid-1", attempt="att-1", run_id="r1"):
    st = ss.Store(db_path(d))
    first = st.record_decision(
        run_id, ack, DECISION, stage=stage, op=op,
        request_digest=digest, attempt_id=attempt)
    st.close()
    return first


class frozen:
    """Explicit external clock injection: the module sees one fixed instant."""

    def __init__(self, instant):
        self.instant = instant

    def __enter__(self):
        self.real = ss.time.time
        ss.time.time = lambda: self.instant
        return self

    def __exit__(self, *exc):
        ss.time.time = self.real


class recording:
    """Records every clock sample the module itself takes."""

    def __enter__(self):
        self.real = ss.time.time
        self.samples = []

        def clock():
            now = self.real()
            self.samples.append(now)
            return now

        ss.time.time = clock
        return self

    def __exit__(self, *exc):
        ss.time.time = self.real

    def matching(self, expires, lease_s):
        """Samples s for which the module computed expires == s + lease_s."""
        return [s for s in self.samples if s + lease_s == expires]


# --------------------------------------------------------------------------
# 1. Writer lock before the clock; the deadline uses the worker's sample
# --------------------------------------------------------------------------

def run_blocked(d, op):
    """Hold a REAL writer lock, let the worker block, release at a known
    instant, and return the worker's own clock samples and return time."""
    ready, go, reached = (threading.Event(), threading.Event(),
                          threading.Event())
    first_sql, out = [], {}

    def worker():
        st = ss.Store(db_path(d))

        def trace(sql):
            if not first_sql:
                first_sql.append(sql.strip())
            reached.set()

        st.con.set_trace_callback(trace)
        ready.set()
        go.wait(5)
        try:
            out["value"] = op(st)
        except Exception as e:                   # noqa: BLE001
            out["error"] = e
        finally:
            out["returned_at"] = time.time()
            try:
                st.con.set_trace_callback(None)
            except Exception:                    # noqa: BLE001
                pass
            st.close()

    thread = threading.Thread(target=worker)
    thread.start()
    if not ready.wait(5):
        raise AssertionError("worker store never opened")
    blocker = sqlite3.connect(db_path(d), timeout=5, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    go.set()
    if not reached.wait(5):
        raise AssertionError("worker never reached SQLite")
    time.sleep(HOLD)                       # worker is provably blocked here
    released_at = time.time()              # earliest instant the lock is free
    blocker.rollback()
    blocker.close()
    thread.join(10)
    if thread.is_alive():
        raise AssertionError("blocked worker never finished")
    return {"value": out.get("value"), "error": out.get("error"),
            "first_sql": first_sql[0] if first_sql else None,
            "returned_at": out.get("returned_at"), "released_at": released_at}


def test_blocked_claim_deadline_is_post_lock_worker_sample():
    d = newdir()
    seed_pending(d)
    with recording() as rec:
        got = run_blocked(
            d, lambda st: st.resume_continuations("r1", "w1", lease_s=LEASE))
    check("claim lock: first statement is BEGIN IMMEDIATE",
          (got["first_sql"] or "").upper().startswith("BEGIN IMMEDIATE"),
          repr(got["first_sql"]))
    check("claim lock: blocked claim succeeds after release",
          got["error"] is None and isinstance(got["value"], list)
          and len(got["value"]) == 1, repr(got))
    if got["error"] is None and got["value"]:
        row = got["value"][0]
        matched = rec.matching(row["lease_expires"], LEASE)
        check("claim lock: persisted deadline is worker-sample + lease",
              len(matched) == 1,
              "expires=%r samples=%r" % (row["lease_expires"], rec.samples))
        if matched:
            check("claim lock: the validation sample is AFTER the lock was"
                  " released (no parent scheduling tolerance)",
                  matched[0] >= got["released_at"],
                  "sample=%r released_at=%r"
                  % (matched[0], got["released_at"]))
            check("claim lock: the validation sample precedes the worker's"
                  " own return", matched[0] <= got["returned_at"],
                  "sample=%r returned=%r"
                  % (matched[0], got["returned_at"]))
        check("claim lock: the full requested lease survives the wait",
              row["lease_expires"] >= got["released_at"] + LEASE,
              "expires=%r released=%r lease=%r"
              % (row["lease_expires"], got["released_at"], LEASE))
        check("claim lock: claim keeps the original attempt",
              row["attempt_id"] == "att-1")


def test_unblocked_control_samples_between_call_bounds():
    d = newdir()
    seed_pending(d)
    st = ss.Store(db_path(d))
    before = time.time()
    with recording() as rec:
        claimed = st.resume_continuations("r1", "w1", lease_s=LEASE)[0]
    after = time.time()
    matched = rec.matching(claimed["lease_expires"], LEASE)
    check("control: one clock sample produced the deadline",
          len(matched) == 1, repr(rec.samples))
    if matched:
        check("control: unblocked claim samples inside its own call window",
              before <= matched[0] <= after,
              "before=%r sample=%r after=%r"
              % (before, matched[0], after))
    st.close()


def test_all_four_operations_lock_first_and_refuse_expired():
    cases = (
        ("heartbeat", lambda st, cid, tok: st.heartbeat_continuation(
            "r1", cid, "w1", tok, lease_s=LEASE)),
        ("complete", lambda st, cid, tok: st.complete_continuation(
            "r1", cid, "w1", tok)),
        ("release", lambda st, cid, tok: st.release_continuation(
            "r1", cid, "w1", tok)),
    )
    for name, op in cases:
        d = newdir()
        seed_pending(d)
        st = ss.Store(db_path(d))
        claimed = st.resume_continuations("r1", "w1", lease_s=LEASE)[0]
        st.close()
        cid, token = claimed["id"], claimed["claim_token"]
        got = run_blocked(d, lambda st, op=op, cid=cid, token=token:
                          op(st, cid, token))
        check("%s lock: first statement is BEGIN IMMEDIATE" % name,
              (got["first_sql"] or "").upper()
              .startswith("BEGIN IMMEDIATE"), repr(got["first_sql"]))
        check("%s lock: expired work refuses STALE_LEASE" % name,
              isinstance(got["error"], ss.StoreError)
              and got["error"].code == "STALE_LEASE",
              repr(got["error"]))


# --------------------------------------------------------------------------
# 2. Fencing and takeover
# --------------------------------------------------------------------------

def test_fencing_and_takeover():
    d = newdir()
    seed_pending(d)
    st = ss.Store(db_path(d))
    first = st.resume_continuations("r1", "w1", lease_s=60)[0]
    again = st.resume_continuations("r1", "w2", lease_s=60, include_expired=True)
    check("fencing: a live claim is never stolen", again == [], repr(again))
    raises("fencing: wrong token refuses",
           lambda: st.heartbeat_continuation("r1", first["id"], "w1", "bogus"),
           ss.StoreError, "NOT_OWNER")
    raises("fencing: wrong worker refuses",
           lambda: st.complete_continuation("r1", first["id"], "w2",
                                            first["claim_token"]),
           ss.StoreError, "NOT_OWNER")
    done = st.complete_continuation("r1", first["id"], "w1",
                                    first["claim_token"])
    dup = st.complete_continuation("r1", first["id"], "w1",
                                   first["claim_token"])
    check("fencing: completion then duplicate completion acknowledged",
          done["duplicate"] is False and dup["duplicate"] is True)
    st.close()

    d = newdir()
    seed_pending(d)
    st = ss.Store(db_path(d))
    short = st.resume_continuations("r1", "w1", lease_s=0.05)[0]
    time.sleep(0.08)
    taken = st.resume_continuations("r1", "w2", lease_s=60,
                                    include_expired=True)
    check("takeover: the expired claim is taken over",
          len(taken) == 1, repr(taken))
    if taken:
        row = taken[0]
        check("takeover: identity, attempt and creation survive",
              row["id"] == short["id"] and row["attempt_id"] == "att-1"
              and row["created_at"] == short["created_at"], str(row))
        check("takeover: a NEW unpredictable token is issued",
              row["claim_token"] and row["claim_token"] != short["claim_token"])
        raises("takeover: the old token can no longer act",
               lambda: st.heartbeat_continuation(
                   "r1", row["id"], "w1", short["claim_token"]),
               ss.StoreError, "NOT_OWNER")
        done = st.complete_continuation("r1", row["id"], "w2",
                                        row["claim_token"])
        check("takeover: the new owner completes",
              done["duplicate"] is False
              and done["continuation"]["state"] == "done")
    st.close()

    d = newdir()
    seed_pending(d)
    st = ss.Store(db_path(d))
    claimed = st.resume_continuations("r1", "w1", lease_s=60)[0]
    rel = st.release_continuation("r1", claimed["id"], "w1",
                                  claimed["claim_token"])
    dup = st.release_continuation("r1", claimed["id"], "w1",
                                  claimed["claim_token"])
    retry = st.resume_continuations("r1", "w2", lease_s=60)[0]
    check("release: release, duplicate release and retry on the same attempt",
          rel["continuation"]["state"] == "pending"
          and dup["duplicate"] is True and retry["id"] == claimed["id"]
          and retry["attempt_id"] == "att-1")
    st.close()


# --------------------------------------------------------------------------
# 3. Atomicity: origin insert and event insert failures roll everything back
# --------------------------------------------------------------------------

def test_origin_and_event_failures_roll_back():
    d = newdir()
    st = ss.Store(db_path(d))
    st.con.execute(
        "CREATE TRIGGER fail_origin BEFORE INSERT ON continuation_origins"
        " BEGIN SELECT RAISE(ABORT, 'injected origin failure'); END;")
    st.con.commit()
    try:
        st.record_decision("r1", "msg-1", DECISION, stage="music",
                           op="rejudge", request_digest="sha256:paid-1",
                           attempt_id="att-1")
        check("atomic: origin insert failure raises", False, "no error")
    except sqlite3.Error:
        check("atomic: origin insert failure raises", True)
    except Exception as e:                       # noqa: BLE001
        check("atomic: origin insert failure raises", False, repr(e))
    rows = st.con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    conts = st.con.execute("SELECT COUNT(*) FROM continuations").fetchone()[0]
    check("atomic: no decision row survives the failed origin insert",
          rows == 0, str(rows))
    check("atomic: no continuation row survives the failed origin insert",
          conts == 0, str(conts))
    st.con.execute("DROP TRIGGER fail_origin")
    st.con.commit()
    ok = st.record_decision("r1", "msg-1", DECISION, stage="music",
                            op="rejudge", request_digest="sha256:paid-1",
                            attempt_id="att-1")
    check("atomic: after the trigger is dropped the same call commits",
          ok["duplicate"] is False
          and st.get_continuation_decision(
              "r1", ok["continuation"]["id"])["ack_id"] == "msg-1")
    st.con.execute(
        "CREATE TRIGGER fail_event BEFORE INSERT ON events"
        " BEGIN SELECT RAISE(ABORT, 'injected event failure'); END;")
    st.con.commit()
    try:
        st.resume_continuations("r1", "w1", lease_s=60)
        check("atomic: event insert failure raises", False, "no error")
    except sqlite3.Error:
        check("atomic: event insert failure raises", True)
    pending = st.scan_pending_continuations("r1")
    check("atomic: the failed claim leaves the row pending",
          len(pending) == 1 and pending[0]["state"] == "pending",
          repr(pending))
    st.con.execute("DROP TRIGGER fail_event")
    st.con.commit()
    st.close()


# --------------------------------------------------------------------------
# 4. Lease numeric boundaries
# --------------------------------------------------------------------------

def test_lease_numeric_boundary():
    d = newdir()
    seed_pending(d)
    st = ss.Store(db_path(d))
    bad = (True, False, 0, -1, 10 ** 400, -(10 ** 400), 10 ** 1000,
           float("inf"), float("nan"), "300", None, 86401)
    for value in bad:
        raises("lease: %r -> MALFORMED_RECORD" % (value,),
               lambda v=value: st.resume_continuations(
                   "r1", "w1", lease_s=v),
               ss.StoreError, "MALFORMED_RECORD")
    check("lease: refused values mutate nothing",
          st.scan_pending_continuations("r1")[0]["state"] == "pending")
    claimed = st.resume_continuations("r1", "w1", lease_s=86400)[0]
    check("lease: exactly one day is allowed",
          claimed["lease_expires"] > time.time() + 86000)
    raises("lease: huge integer on heartbeat -> MALFORMED_RECORD",
           lambda: st.heartbeat_continuation(
               "r1", claimed["id"], "w1", claimed["claim_token"],
               lease_s=10 ** 400),
           ss.StoreError, "MALFORMED_RECORD")
    st.close()


# --------------------------------------------------------------------------
# 5. Origin binding: clock rollback, replay, direct enqueue, restart
# --------------------------------------------------------------------------

def test_origin_binding_survives_clock_rollback():
    d = newdir()
    with frozen(100.0):
        first = seed_pending(d)
    cid = first["continuation"]["id"]
    st = ss.Store(db_path(d))
    with frozen(90.0):
        later = st.record_decision(
            "r1", "msg-2", {"answer": "later"}, stage="music", op="rejudge",
            request_digest="sha256:paid-1", attempt_id="att-2")
    check("rollback: both acknowledgements share the open continuation",
          later["continuation"]["id"] == cid
          and len(st.scan_pending_continuations("r1")) == 1, str(later))
    check("rollback: the row keeps the original attempt",
          later["continuation"]["attempt_id"] == "att-1")
    origin = st.get_continuation_decision("r1", cid)
    check("rollback: origin is the RECORDED creator, not the lower clock",
          origin is not None and origin["ack_id"] == "msg-1"
          and origin["decision"] == DECISION, repr(origin))
    check("rollback: origin is marked as recorded, never derived",
          origin is not None and origin["origin_source"] == "recorded")
    st.close()
    st = ss.Store(db_path(d))                    # process restart
    again = st.get_continuation_decision("r1", cid)
    check("rollback: the same origin survives reopen",
          again is not None and again["ack_id"] == "msg-1"
          and again["origin_source"] == "recorded", repr(again))
    st.close()


def test_origin_same_timestamp_and_replay_different_arguments():
    d = newdir()
    st = ss.Store(db_path(d))
    with frozen(50.0):
        first = st.record_decision(
            "r1", "msg-1", {"answer": "first"}, stage="music", op="rejudge",
            request_digest="sha256:paid-1", attempt_id="att-1")
        second = st.record_decision(
            "r1", "msg-2", {"answer": "second"}, stage="music", op="rejudge",
            request_digest="sha256:paid-1", attempt_id="att-2")
    cid = first["continuation"]["id"]
    check("same-time: one open continuation is shared",
          second["continuation"]["id"] == cid)
    origin = st.get_continuation_decision("r1", cid)
    check("same-time: the bound origin wins without an ambiguity refusal",
          origin is not None and origin["ack_id"] == "msg-1", repr(origin))
    saved_receipt_raw = st.con.execute(
        "SELECT receipt FROM decisions WHERE run_id='r1' AND ack_id='msg-1'"
    ).fetchone()[0]
    saved_receipt = json.loads(saved_receipt_raw)
    saved_attempt = st.get_continuation("r1", cid)["attempt_id"]
    replay = st.record_decision(
        "r1", "msg-1", {"answer": "CHANGED"}, stage="video", op="other",
        request_digest="sha256:other", attempt_id="att-9")
    check("replay: duplicate is acknowledged with the EXACT saved receipt",
          replay["duplicate"] is True and replay["receipt"] == saved_receipt,
          "%r" % (replay["receipt"],))
    check("replay: the same continuation and attempt are unchanged",
          replay["continuation"]["id"] == cid
          and replay["continuation"]["attempt_id"] == saved_attempt
          and saved_attempt == "att-1", str(replay["continuation"]))
    check("replay: changed replay arguments are never used as routing",
          len(st.scan_pending_continuations("r1")) == 1
          and st.get_continuation("r1", cid)["stage"] == "music")
    after = st.get_continuation_decision("r1", cid)
    check("replay: origin is unchanged by the replay",
          after is not None and after["ack_id"] == "msg-1"
          and after["decision"] == {"answer": "first"}, repr(after))
    claimed = st.resume_continuations("r1", "w1", lease_s=60)[0]
    st.complete_continuation("r1", cid, "w1", claimed["claim_token"])
    st.close()
    st = ss.Store(db_path(d))                        # real close/reopen
    before = _history(st)
    replayed = st.record_decision(
        "r1", "msg-1", {"answer": "AGAIN"}, stage="video", op="other",
        request_digest="sha256:other", attempt_id="att-9")
    check("replay: a COMPLETED continuation is returned exactly by the"
          " duplicate acknowledgement",
          replayed["duplicate"] is True
          and replayed["continuation"]["id"] == cid
          and replayed["continuation"]["state"] == "done"
          and replayed["continuation"]["attempt_id"] == "att-1",
          repr(replayed))
    check("replay: the reopened receipt is byte-identical to the saved bytes",
          json.dumps(replayed["receipt"], sort_keys=True) == saved_receipt_raw,
          repr(replayed["receipt"]))
    check("replay: the completed replay writes no history row",
          _history(st) == before)
    st.close()


def test_direct_enqueue_never_adopts_a_later_ack():
    d = newdir()
    st = ss.Store(db_path(d))
    direct = st.enqueue_continuation("r1", "video", "resume",
                                     request_digest="sha256:direct")
    cid = direct["continuation"]["id"]
    check("direct: an unassociated row reads as no origin",
          st.get_continuation_decision("r1", cid) is None)
    ack = st.record_decision(
        "r1", "msg-1", DECISION, stage="video", op="resume",
        request_digest="sha256:direct", attempt_id="att-direct")
    check("direct: a later acknowledgement reuses the open row",
          ack["continuation"]["id"] == cid, str(ack))
    check("direct: the later acknowledgement is NEVER promoted to origin",
          st.get_continuation_decision("r1", cid) is None)
    check("direct: the continuation attempt is untouched",
          st.get_continuation("r1", cid)["attempt_id"] is None)
    st.close()
    st = ss.Store(db_path(d))
    check("direct: still no origin after reopen",
          st.get_continuation_decision("r1", cid) is None)
    st.close()


def test_origin_missing_receipt_and_wrong_run():
    d = newdir()
    first = seed_pending(d)
    cid = first["continuation"]["id"]
    st = ss.Store(db_path(d))
    raises("origin: a foreign run is NOT_FOUND",
           lambda: st.get_continuation_decision("other-run", cid),
           ss.StoreError, "NOT_FOUND")
    st.con.execute(
        "INSERT INTO decisions(run_id, ack_id, channel, decision, receipt, at)"
        " VALUES('r1', 'msg-broken', 'message', '{}', NULL, 1.0)")
    st.con.execute(
        "INSERT OR REPLACE INTO continuation_origins(continuation_id, run_id,"
        " ack_id, origin_source, bound_at)"
        " VALUES(?, 'r1', 'msg-broken', 'recorded', 1.0)", (cid,))
    st.con.commit()
    raises("origin: a missing saved receipt refuses NEEDS_RECOVERY",
           lambda: st.get_continuation_decision("r1", cid),
           ss.StoreError, "NEEDS_RECOVERY")
    raises("origin: replay of a decision with no receipt refuses",
           lambda: st.record_decision("r1", "msg-broken", DECISION),
           ss.StoreError, "NEEDS_RECOVERY")
    st.close()

    # A saved receipt that PARSES but is not an object is corrupted history,
    # not an absent one: the duplicate acknowledgement must refuse typed and
    # rewrite nothing. Every shape below is real JSON on disk, real reopen.
    wrong_shapes = ("null", "[]", "[\"continuation_id\"]", "\"cont-1\"",
                    "42", "0", "-1", "3.5", "true", "false")
    for raw in wrong_shapes:
        d = newdir()
        first = seed_pending(d)
        cid = first["continuation"]["id"]
        st = ss.Store(db_path(d))
        healthy = st.con.execute(
            "SELECT receipt FROM decisions WHERE run_id='r1' AND ack_id='msg-1'"
        ).fetchone()[0]
        st.con.execute(
            "UPDATE decisions SET receipt=? WHERE run_id='r1'"
            " AND ack_id='msg-1'", (raw,))
        st.con.commit()
        st.close()
        st = ss.Store(db_path(d))                    # real close/reopen
        before = _history(st)
        err = raises("shape: receipt %s on a duplicate ack refuses"
                     " NEEDS_RECOVERY" % raw,
                     lambda st=st: st.record_decision("r1", "msg-1", DECISION),
                     ss.StoreError, "NEEDS_RECOVERY")
        check("shape: receipt %s refusal is a typed StoreError" % raw,
              isinstance(err, ss.StoreError), repr(err))
        check("shape: receipt %s leaves every saved row untouched" % raw,
              _history(st) == before)
        check("shape: receipt %s is never rewritten by the refusal" % raw,
              st.con.execute(
                  "SELECT receipt FROM decisions WHERE run_id='r1'"
                  " AND ack_id='msg-1'").fetchone()[0] == raw
              and healthy != raw)
        raises("shape: receipt %s still refuses the restart read" % raw,
               lambda st=st, cid=cid:
               st.get_continuation_decision("r1", cid),
               ss.StoreError, "NEEDS_RECOVERY")
        check("shape: receipt %s keeps the recorded origin row" % raw,
              _history(st)["origins"] == before["origins"])
        st.close()

    # Positive control in the same scenario: a healthy receipt still replays
    # byte-for-byte after reopening, and changed replay arguments are ignored.
    d = newdir()
    first = seed_pending(d)
    healthy_id = first["continuation"]["id"]
    st = ss.Store(db_path(d))
    saved = st.con.execute(
        "SELECT receipt FROM decisions WHERE run_id='r1' AND ack_id='msg-1'"
    ).fetchone()[0]
    st.close()
    st = ss.Store(db_path(d))                        # real close/reopen
    before = _history(st)
    dup = st.record_decision(
        "r1", "msg-1", {"answer": "CHANGED"}, stage="video", op="other",
        request_digest="sha256:other", attempt_id="att-9")
    check("shape: a healthy saved receipt still duplicates",
          dup["duplicate"] is True and dup["receipt"] == json.loads(saved),
          repr(dup))
    check("shape: the healthy duplicate is byte-identical to the saved bytes",
          json.dumps(dup["receipt"], sort_keys=True) == saved,
          repr(dup["receipt"]))
    check("shape: the healthy duplicate keeps the original continuation",
          dup["continuation"]["id"] == healthy_id
          and dup["continuation"]["attempt_id"] == "att-1"
          and dup["continuation"]["stage"] == "music", str(dup))
    check("shape: the healthy duplicate writes no history row",
          _history(st) == before)
    st.close()


# --------------------------------------------------------------------------
# 6. Legacy rows: one unambiguous receipt or a named refusal
# --------------------------------------------------------------------------

def _make_legacy(d, attempt="att-1", digest="sha256:paid-1",
                 continuation_id="c-legacy"):
    """A row written before origin binding: no continuation_origins row."""
    st = ss.Store(db_path(d))
    st.con.execute(
        "INSERT INTO continuations(id, run_id, stage, op, identity,"
        " request_digest, attempt_id, state, claimed_by, created_at,"
        " updated_at, claim_token, lease_expires) VALUES"
        "(?, 'r1', 'music', 'rejudge', ?, ?, ?, 'pending', NULL, 1.0, 1.0,"
        " NULL, NULL)", (continuation_id, digest, digest, attempt))
    st.con.commit()
    return st


def _add_legacy_decision(st, ack, continuation_id, attempt, digest,
                         decision=None, at=1.0):
    action = decision or {"answer": ack}
    receipt = {"ack_id": ack, "channel": "message", "decision": action,
               "continuation_id": continuation_id, "attempt_id": attempt,
               "request_digest": digest}
    st.con.execute(
        "INSERT INTO decisions(run_id, ack_id, channel, decision, receipt, at)"
        " VALUES('r1', ?, 'message', ?, ?, ?)",
        (ack, json.dumps(action, sort_keys=True),
         json.dumps(receipt, sort_keys=True), at))
    st.con.commit()


def test_legacy_rows_derive_only_from_one_agreeing_receipt():
    d = newdir()
    st = _make_legacy(d)
    check("legacy: a row with no receipt has no origin",
          st.get_continuation_decision("r1", "c-legacy") is None)
    _add_legacy_decision(st, "old-1", "c-legacy", "att-1", "sha256:paid-1",
                         at=5.0)
    got = st.get_continuation_decision("r1", "c-legacy")
    check("legacy: one agreeing receipt binds the read contract",
          got is not None and got["ack_id"] == "old-1"
          and got["decision"] == {"answer": "old-1"}, repr(got))
    check("legacy: the binding is labelled as derived, not recorded",
          got is not None and got["origin_source"] == "receipt_derivation")
    check("legacy: the evidence names the proven fields",
          got is not None and got["evidence"]["continuation_id"] is True
          and got["evidence"]["attempt_id"] == "match"
          and got["evidence"]["request_digest"] == "match", repr(got))
    check("legacy: the receipt itself is returned unchanged",
          got is not None
          and got["receipt"]["continuation_id"] == "c-legacy")
    st.close()


def test_legacy_multiple_origins_refuse_without_using_time():
    d = newdir()
    st = _make_legacy(d)
    _add_legacy_decision(st, "old-1", "c-legacy", "att-1", "sha256:paid-1",
                         at=9.0)
    _add_legacy_decision(st, "old-2", "c-legacy", "att-1", "sha256:paid-1",
                         at=2.0)
    raises("legacy: two agreeing receipts refuse AMBIGUOUS_ASSOCIATION",
           lambda: st.get_continuation_decision("r1", "c-legacy"),
           ss.StoreError, "AMBIGUOUS_ASSOCIATION")
    st.close()


def test_legacy_contradictory_receipts_refuse():
    d = newdir()
    st = _make_legacy(d, attempt="att-1", digest="sha256:paid-1")
    _add_legacy_decision(st, "old-1", "c-legacy", "att-DIFFERENT",
                         "sha256:paid-1")
    raises("legacy: a contradicting attempt id refuses NEEDS_RECOVERY",
           lambda: st.get_continuation_decision("r1", "c-legacy"),
           ss.StoreError, "NEEDS_RECOVERY")
    d = newdir()
    st = _make_legacy(d, attempt="att-1", digest="sha256:paid-1")
    _add_legacy_decision(st, "old-1", "c-legacy", "att-1",
                         "sha256:OTHER")
    raises("legacy: a contradicting request digest refuses NEEDS_RECOVERY",
           lambda: st.get_continuation_decision("r1", "c-legacy"),
           ss.StoreError, "NEEDS_RECOVERY")
    st.close()


def test_legacy_contradiction_excluded_when_one_agreeing_receipt_remains():
    d = newdir()
    st = _make_legacy(d)
    _add_legacy_decision(st, "old-1", "c-legacy", "att-1", "sha256:paid-1")
    _add_legacy_decision(st, "late", "c-legacy", "att-1", "sha256:OTHER")
    got = st.get_continuation_decision("r1", "c-legacy")
    check("legacy: the contradicting receipt is excluded, not chosen",
          got is not None and got["ack_id"] == "old-1"
          and got["evidence"]["excluded_contradictory"] == 1, repr(got))
    st.close()


# --------------------------------------------------------------------------
# 7. Migration: a real version-1 database migrates and keeps every row
# --------------------------------------------------------------------------

V1_DDL = """
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE stages(run_id TEXT, stage TEXT, state TEXT, version INTEGER,
 owner TEXT, lease_expires REAL, reason TEXT, updated_at REAL,
 PRIMARY KEY(run_id, stage));
CREATE TABLE events(id TEXT PRIMARY KEY, run_id TEXT, stage TEXT, kind TEXT,
 detail TEXT, at REAL);
CREATE TABLE receipts(cache_key TEXT PRIMARY KEY, run_id TEXT, stage TEXT,
 kind TEXT, audio_hash TEXT, evaluator_version TEXT, policy_version TEXT,
 plan_revision TEXT, parent_key TEXT, receipt TEXT, valid INTEGER,
 created_at REAL);
CREATE TABLE decisions(run_id TEXT, ack_id TEXT, channel TEXT, decision TEXT,
 receipt TEXT, at REAL, PRIMARY KEY(run_id, ack_id));
CREATE TABLE continuations(id TEXT PRIMARY KEY, run_id TEXT, stage TEXT,
 op TEXT, identity TEXT, request_digest TEXT, attempt_id TEXT, state TEXT,
 claimed_by TEXT, created_at REAL, updated_at REAL);
CREATE UNIQUE INDEX cont_open_identity ON continuations(run_id, identity)
 WHERE state != 'done';
INSERT INTO meta VALUES('db_version', '1');
INSERT INTO stages VALUES('r1', 'music', 'RUNNING', 7, 'w1', 9999999999.0,
 NULL, 1.0);
INSERT INTO events VALUES('e1', 'r1', 'music', 'claim', 'w1', 1.0);
INSERT INTO receipts VALUES('k1', 'r1', 'music', 'measurement', 'a1', 'ev1',
 'pv1', 'pr1', NULL, '{"m": 1}', 1, 1.0);
INSERT INTO decisions VALUES('r1', 'old-ack', 'message', '{"answer": "x"}',
 '{"ack_id": "old-ack", "channel": "message", "decision": {"answer": "x"},
 "continuation_id": "c-old", "attempt_id": "att-old",
 "request_digest": "sha256:old"}', 2.0);
INSERT INTO continuations VALUES('c-old', 'r1', 'music', 'rejudge',
 'sha256:old', 'sha256:old', 'att-old', 'claimed', 'w1', 1.5, 1.5);
"""


def test_migration_preserves_every_row_and_repeats_safely():
    d = newdir()
    con = sqlite3.connect(db_path(d))
    con.executescript(V1_DDL)
    con.commit()
    con.close()
    before = None
    con = sqlite3.connect(db_path(d))
    try:
        before = {
            "stages": con.execute("SELECT * FROM stages ORDER BY stage")
            .fetchall(),
            "events": con.execute("SELECT * FROM events ORDER BY id")
            .fetchall(),
            "receipts": con.execute(
                "SELECT * FROM receipts ORDER BY cache_key").fetchall(),
            "decisions": con.execute(
                "SELECT * FROM decisions ORDER BY ack_id").fetchall(),
            # The ORIGINAL continuation columns only: migration may add
            # columns, and added columns must not rewrite existing values.
            "continuations": con.execute(
                "SELECT id, run_id, stage, op, identity, request_digest,"
                " attempt_id, state, claimed_by, created_at, updated_at"
                " FROM continuations ORDER BY id").fetchall()}
    finally:
        con.close()
    st = ss.Store(db_path(d))
    tables = {r[0] for r in st.con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    version = st.con.execute(
        "SELECT v FROM meta WHERE k='db_version'").fetchone()[0]
    check("migration: the version-1 database is migrated",
          version == str(ss.DB_SCHEMA_VERSION), str(version))
    check("migration: the origin association table is added",
          "continuation_origins" in tables, str(tables))
    after = {
        "stages": st.con.execute("SELECT * FROM stages ORDER BY stage")
        .fetchall(),
        "events": st.con.execute("SELECT * FROM events ORDER BY id")
        .fetchall(),
        "receipts": st.con.execute(
            "SELECT * FROM receipts ORDER BY cache_key").fetchall(),
        "decisions": st.con.execute(
            "SELECT * FROM decisions ORDER BY ack_id").fetchall(),
        "continuations": st.con.execute(
            "SELECT id, run_id, stage, op, identity, request_digest,"
            " attempt_id, state, claimed_by, created_at, updated_at"
            " FROM continuations ORDER BY id").fetchall()}
    check("migration: every original row survives byte-for-byte",
          before == after, "%r != %r" % (before, after))
    legacy = st.get_continuation_decision("r1", "c-old")
    check("migration: the pre-binding row derives from its one receipt",
          legacy is not None and legacy["ack_id"] == "old-ack"
          and legacy["origin_source"] == "receipt_derivation", repr(legacy))
    st.close()
    st = ss.Store(db_path(d))                     # reopen repeats safely
    check("migration: reopening keeps the origin table and the row",
          st.get_continuation_decision("r1", "c-old")["ack_id"] == "old-ack")
    st.close()


TESTS = [
    test_blocked_claim_deadline_is_post_lock_worker_sample,
    test_unblocked_control_samples_between_call_bounds,
    test_all_four_operations_lock_first_and_refuse_expired,
    test_fencing_and_takeover,
    test_origin_and_event_failures_roll_back,
    test_lease_numeric_boundary,
    test_origin_binding_survives_clock_rollback,
    test_origin_same_timestamp_and_replay_different_arguments,
    test_direct_enqueue_never_adopts_a_later_ack,
    test_origin_missing_receipt_and_wrong_run,
    test_legacy_rows_derive_only_from_one_agreeing_receipt,
    test_legacy_multiple_origins_refuse_without_using_time,
    test_legacy_contradictory_receipts_refuse,
    test_legacy_contradiction_excluded_when_one_agreeing_receipt_remains,
    test_migration_preserves_every_row_and_repeats_safely,
]


def main():
    print("module under test: %s" % ss.__file__)
    reader = getattr(ss.Store, "get_continuation_decision", None)
    print("signature: %s"
          % (inspect.signature(reader) if reader else "MISSING"))
    for t in TESTS:
        try:
            t()
        except Exception as e:                   # noqa: BLE001
            check("%s raised" % t.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    for d in TMPDIRS:
        shutil.rmtree(d, ignore_errors=True)
    print("\n%d groups, %d checks failed" % (len(TESTS), len(FAILS)))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d S75-W53 store-R4 groups passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
