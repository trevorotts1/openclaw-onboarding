#!/usr/bin/env python3
"""Fault boundary: cc_sync outage queue + replay, no duplicates. Stdlib only."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "core"))
import cc_sync as C

WS = "ws-fault"


def check(name, cond):
    assert cond, "FAILED: %s" % name
    print("ok: %s" % name)


def state_of(ob, rid):
    return ob.db.execute("SELECT state FROM outbox WHERE id=?",
                         (rid,)).fetchone()[0]


# --- identical intent enqueued twice: one row, no duplicate ---
calls = []


def ok_sender(method, path, payload):
    calls.append((method, path))
    if method == "POST":
        return 201, {"created": True, "stages": [{"slug": "s1"}]}
    return 200, {}


ob = C.Outbox(db_path=":memory:", workspace=WS, sender=ok_sender)
a = ob.enqueue_create("job-1", "Show", [{"slug": "s1"}], WS)
b = ob.enqueue_create("job-1", "Show", [{"slug": "s1"}], WS)
check("deduped enqueue returns same row", a == b)
check("one pending row", ob.counts().get("pending") == 1)

# --- outage queues (never dispatched): order held, retry sends once ---
down = {"fail": True}


def flaky_sender(method, path, payload):
    calls.append((method, path))
    if down["fail"]:
        raise C.TransportOutage("refused", dispatched=False)
    return 201, {"created": True, "stages": [{"slug": "s1"}]}


ob2 = C.Outbox(db_path=":memory:", workspace=WS, sender=flaky_sender)
r1 = ob2.enqueue_create("job-a", "Show A", [{"slug": "s1"}], WS)
r2 = ob2.enqueue_create("job-b", "Show B", [{"slug": "s1"}], WS)
n_calls = len(calls)
rep = ob2.flush()
check("outage degrades flush", rep["degraded"] is True)
check("order held: one attempt, second row untouched",
      len(calls) - n_calls == 1 and state_of(ob2, r2) == "pending")
down["fail"] = False
rep = ob2.flush()
check("both acked after recovery", sorted(rep["acked"]) == sorted([r1, r2]))
n_rows = ob2.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
check("no duplicate rows (%d)" % n_rows, n_rows == 2)

# --- maybe-dispatched outage: reconcile-first, never blind resend ---
patched = {"n": 0}


def maybe_sender(method, path, payload):
    if method == "PATCH":
        patched["n"] += 1
        if patched["n"] == 1:
            raise C.TransportOutage("timeout", dispatched=True)
        raise AssertionError("blind resend after uncertain outage")
    if method == "GET":
        return 200, {"cards": [{"stage_slug": "s1", "status": "review"}]}
    if method == "POST":
        return 201, {"created": True, "stages": [{"slug": "s1"}]}
    raise AssertionError("unexpected %s" % method)


ob3 = C.Outbox(db_path=":memory:", workspace=WS, sender=maybe_sender)
ob3.enqueue_create("job-m", "Show M", [{"slug": "s1"}], WS)
rep = ob3.flush()
check("create acked", rep["acked"] == [1])
m = ob3.enqueue_move("job-m", "s1", "review", "alice", WS,
                     reason="render done", evidence="frame ok")
rep = ob3.flush()
check("uncertain row held as sent, flush degraded",
      state_of(ob3, m) == "sent" and rep["degraded"] is True)
rep = ob3.flush()
check("reconciled without resend (PATCH n=%d)" % patched["n"],
      patched["n"] == 1 and state_of(ob3, m) == "acked"
      and rep["acked"] == [m])
print("OK test_cc_sync_faults: 9 checks")
