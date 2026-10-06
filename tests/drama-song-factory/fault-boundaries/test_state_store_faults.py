#!/usr/bin/env python3
"""Fault boundary: state_store corrupt-DB-stop + stale-lease. Stdlib only."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "core"))
import state_store as S

RUN, STAGE = "fault-run", "song"


def fresh_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return f.name


def check(name, cond):
    assert cond, "FAILED: %s" % name
    print("ok: %s" % name)


# --- corrupt-DB-stop ---
bad = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
bad.write(b"garbage-not-sqlite")
bad.close()
needs, why = S.needs_recovery(bad.name)
check("corrupt file flagged", needs is True)
try:
    S.Store(bad.name)
    raise AssertionError("Store opened corrupt DB")
except S.StoreError as e:
    check("Store refuses corrupt DB (%s)" % e.code, e.code == "NEEDS_RECOVERY")
os.unlink(bad.name)

# missing tables also flagged
half = fresh_db()
import sqlite3
c = sqlite3.connect(half)
c.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
c.commit()
c.close()
needs, _ = S.needs_recovery(half)
check("schema-drift DB flagged", needs is True)
os.unlink(half)

# --- stale-lease ---
db = fresh_db()
st = S.Store(db)
st.init_run(RUN, [STAGE])
st.transition(RUN, STAGE, "READY", "worker-a")
row = st.claim(RUN, STAGE, "worker-a", lease_s=-1)  # already expired
check("claim works", row["state"] == "RUNNING")
try:
    st.heartbeat(RUN, STAGE, "worker-a")
    raise AssertionError("heartbeat on expired lease passed")
except S.StoreError as e:
    check("expired heartbeat rejected (%s)" % e.code, e.code == "STALE_LEASE")
try:
    st.transition(RUN, STAGE, "WAITING_PROVIDER", "worker-a")
    raise AssertionError("transition on expired lease passed")
except S.StoreError as e:
    check("expired transition rejected (%s)" % e.code, e.code == "STALE_LEASE")
fresh = st.claim(RUN, STAGE, "worker-b")  # takeover on dead lease
check("dead lease takeover works", fresh["owner"] == "worker-b")
live = st.heartbeat(RUN, STAGE, "worker-b")
check("live heartbeat works", live["owner"] == "worker-b")
try:
    st.heartbeat(RUN, STAGE, "worker-a")
    raise AssertionError("non-owner heartbeat passed")
except S.StoreError as e:
    check("non-owner heartbeat rejected (%s)" % e.code, e.code == "NOT_OWNER")
st.close()
os.unlink(db)
print("OK test_state_store_faults: 9 checks")
