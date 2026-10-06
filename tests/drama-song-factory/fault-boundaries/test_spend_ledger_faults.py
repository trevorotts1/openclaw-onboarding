#!/usr/bin/env python3
"""Fault boundary: spend_ledger uncertainty. Stdlib only."""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "core"))
import spend_ledger as L
import job_recovery as R

RUN = "fault-ledger"


def fresh_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return f.name


def check(name, cond):
    assert cond, "FAILED: %s" % name
    print("ok: %s" % name)


# --- crash-before-dispatch: planned job with no remote id BLOCKS, never resubmits ---
db = fresh_db()
L.init_run(db, RUN, 10000)
out = L.plan(db, RUN, "song-1", "att-1", L.digest_request({"song": 1}),
             estimated_cost=100, stage="song")
check("plan ok", out["outcome"] == "ok")
rec = R.recover(db, RUN)
jobs = rec["evidence"]["jobs"]
check("recover plans crash-before-dispatch as BLOCKED",
      len(jobs) == 1 and jobs[0]["action"] == "BLOCKED"
      and jobs[0]["reason"] == "NO_REMOTE_ID")
s = L.summary(db, RUN)
check("nothing dispatched by recovery",
      s["evidence"]["number_of_generation_calls"] == 0)

# --- unknown-no-resubmit: active unknown job blocks a same-key resubmit ---
out = L.reserve(db, RUN, "song-1", "att-1", owner="w1")
check("reserve ok", out["outcome"] == "ok")
out = L.mark_unknown(db, RUN, "song-1", "att-1", owner="w1")
check("mark_unknown ok", out["outcome"] == "ok")
out = L.plan(db, RUN, "song-1", "att-2", L.digest_request({"song": 1}),
             estimated_cost=100, stage="song")
check("resubmit of uncertain job rejected (%s)" % out["reason_code"],
      out["outcome"] == "rejected"
      and out["reason_code"] == "DUPLICATE_LOGICAL_JOB")
rec = R.recover(db, RUN)
check("unknown job reconciles, never resubmits",
      rec["evidence"]["jobs"][0]["action"] == "BLOCKED")

# --- concurrent-reserve-race: exactly one winner, money counted once ---
db2 = fresh_db()
L.init_run(db2, "race", 10000)
L.plan(db2, "race", "song-r", "att-r", L.digest_request({"r": 1}),
       estimated_cost=100, stage="song")
bar = threading.Barrier(2)
results = {}


def worker(owner):
    bar.wait()
    results[owner] = L.reserve(db2, "race", "song-r", "att-r", owner=owner)


ts = [threading.Thread(target=worker, args=(o,)) for o in ("w1", "w2")]
[t.start() for t in ts]
[t.join() for t in ts]
wins = [o for o, r in results.items() if r["outcome"] == "ok"]
check("exactly one reserve winner (got %s)" % wins, len(wins) == 1)
s = L.summary(db2, "race")
check("committed counted once (%s)" % s["evidence"]["committed_cost"],
      s["evidence"]["committed_cost"] == 100)
out = L.reserve(db2, "race", "song-r", "att-r", owner=wins[0])
check("double reserve rejected (%s)" % out["reason_code"],
      out["outcome"] == "rejected" and out["reason_code"] == "BAD_TRANSITION")

# --- corrupt DB stops spending, never becomes a fresh spendable run ---
bad = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
bad.write(b"garbage-not-sqlite")
bad.close()
out = L.can_spend(bad.name, RUN, 0)
check("corrupt DB blocks spend (%s)" % out["reason_code"],
      out["outcome"] == "rejected" and out["reason_code"] == "CORRUPT_STATE")
os.unlink(bad.name)
os.unlink(db)
os.unlink(db2)
print("OK test_spend_ledger_faults: 10 checks")
