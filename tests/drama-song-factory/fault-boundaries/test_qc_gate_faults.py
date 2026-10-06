#!/usr/bin/env python3
"""Fault boundary: qc_gate forged verdicts never advance. Stdlib only."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "core"))
import qc_gate as Q

RUN, STAGE = "fault-qc", "song"


def rec(cid, check, verdict, ident, run=RUN, stage=STAGE,
        session="sess-1", authority="dept-qc"):
    r = {"schema_version": "1.0.0", "check_id": cid, "run_id": run,
         "stage": stage, "check": check, "verdict": verdict,
         "evidence": {"summary": "looks fine"},
         "checker_version": "checker-1",
         "reviewer": {"identity": ident}}
    if session is not None:
        r["reviewer"]["session"] = session
    if authority is not None:
        r["reviewer"]["authority"] = authority
    return r


def codes(res):
    return {f["code"] for f in res["failures"]}


def check(name, cond):
    assert cond, "FAILED: %s" % name
    print("ok: %s" % name)


makers = {"q1": "maker-alice", "q2": "maker-alice"}

# forged PASS from the maker itself
r = Q.evaluate(RUN, STAGE, [rec("q1", "lyrics", "PASS", "maker-alice")],
               makers, ["lyrics"])
check("maker self-PASS blocked", r["gate"] == "BLOCKED"
      and "MAKER_SELF_REVIEW" in codes(r))

# caller-supplied PASS without bound session/authority
r = Q.evaluate(RUN, STAGE, [rec("q1", "lyrics", "PASS", "mallory",
                                session=None)], makers, ["lyrics"])
check("session-less PASS blocked", r["gate"] == "BLOCKED"
      and "SCHEMA_VIOLATION" in codes(r))
r = Q.evaluate(RUN, STAGE, [rec("q1", "lyrics", "PASS", "mallory",
                                authority=None)], makers, ["lyrics"])
check("authority-less PASS blocked", r["gate"] == "BLOCKED"
      and "SCHEMA_VIOLATION" in codes(r))

# UNAVAILABLE on a required check never becomes PASS
r = Q.evaluate(RUN, STAGE, [rec("q1", "lyrics", "UNAVAILABLE", "qc-bob")],
               makers, ["lyrics"])
check("UNAVAILABLE blocked", r["gate"] == "BLOCKED"
      and "UNAVAILABLE_MANDATORY" in codes(r))

# verdict bound to the wrong run
r = Q.evaluate(RUN, STAGE, [rec("q1", "lyrics", "PASS", "qc-bob",
                                run="other-run")], makers, ["lyrics"])
check("wrong-run record blocked", r["gate"] == "BLOCKED"
      and "WRONG_RUN" in codes(r))

# critical FAIL flagged, named for targeted repair, never averaged away
r = Q.evaluate(RUN, STAGE,
               [rec("q1", "lyrics", "FAIL", "qc-bob"),
                rec("q2", "export", "PASS", "qc-bob")],
               makers, ["lyrics", "export"])
check("critical FAIL fails gate", r["gate"] == "FAIL"
      and r["critical_failures"] == ["q1"]
      and r["repair_scope"] == ["q1"])

# one FAIL beside a PASS on the same check still fails
r = Q.evaluate(RUN, STAGE,
               [rec("q1", "export", "PASS", "qc-bob"),
                rec("q2", "export", "FAIL", "qc-bob")],
               makers, ["export"])
check("aggregate cannot erase defect", r["gate"] == "FAIL"
      and "CHECK_FAIL" in codes(r))

# honest independent evidence passes
r = Q.evaluate(RUN, STAGE,
               [rec("q1", "lyrics", "PASS", "qc-bob"),
                rec("q2", "export", "PASS", "qc-bob")],
               makers, ["lyrics", "export"])
check("independent PASS advances", r["gate"] == "PASS")
print("OK test_qc_gate_faults: 8 checks")
