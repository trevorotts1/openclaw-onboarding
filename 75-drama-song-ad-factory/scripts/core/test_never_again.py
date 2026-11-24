#!/usr/bin/env python3
"""The 7 NEVER-AGAIN locks refuse in code, never in prose. $0."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import never_again as NA                          # noqa: E402

fails = []


def check(name, cond):
    if not cond:
        fails.append(name)
        print("FAIL", name)
    else:
        print("ok", name)


# Lock 1: 3rd identical take refuses TEMPLATE_FAIL_LOCK.
p = "sings this line, Minimal head movement, steady locked camera"
check("lock1-allows-first-two",
      NA.check_template_fail([p, p], "a changed prompt with motion") is None)
lock = NA.check_template_fail([p, p], p)
check("lock1-refuses-third-identical",
      lock is not None and lock["code"] == NA.TEMPLATE_FAIL_LOCK)
check("lock1-names-stillness", NA.stillness_words(p) != [])

# Lock 2: direct API post detected, kie_dispatch path clean.
check("lock2-direct-detected",
      NA.is_direct_submit("post https://api.kie.ai/api/v1/jobs/createTask"))
check("lock2-dispatch-clean", not NA.is_direct_submit("kie_dispatch"))

# Lock 3: PROOF-ONLY never a deliverable; delivery needs all four.
check("lock3-proof-flagged", NA.is_proof_only("x/PROOF-ONLY master.mp4"))
check("lock3-proof-not-flagged", not NA.is_proof_only("x/Clean master.mp4"))
check("lock3-delivery-needs-four",
      NA.check_delivery_set({"clean": 1, "captioned": 1}) is not None
      and NA.check_delivery_set({"clean": 1, "captioned": 1, "srt": 1,
                                 "qc_pass": 1}) is None)

# Lock 4: inline gate edit refuses.
check("lock4-inline-refused",
      NA.check_gate_edit(False) is not None
      and NA.check_gate_edit(True) is None)

# Lock 5: drips refuse RETAKE_DRIP.
check("lock5-drip-refused",
      (NA.check_blast(10, 3) or {}).get("code") == NA.RETAKE_DRIP)
check("lock5-one-blast-ok", NA.check_blast(10, 1) is None)

# Lock 6: crop/zoom repair refuses.
check("lock6-crop-refused",
      (NA.check_crop_repair("zoom in to hide letters") or {}).get("code")
      == NA.CROP_REPAIR_REFUSED)
check("lock6-remake-ok", NA.check_crop_repair("full-body remake") is None)

# Lock 7: approval needs recorded reply; waiver needs Trevor signature.
check("lock7-approval-refused", NA.check_approval("") is not None)
check("lock7-approval-ok", NA.check_approval("GO") is None)
check("lock7-waiver-refused",
      NA.check_waiver({"signed_by": "anyone"}) is not None)
check("lock7-waiver-ok",
      NA.check_waiver({"signed_by": "Trevor", "signature": "x"}) is None)


def test_never_again_locks():
    """pytest entry: every module-level lock check must pass."""
    assert not fails, fails


if __name__ == "__main__":
    print("FAILURES: %d" % len(fails))
    sys.exit(1 if fails else 0)
