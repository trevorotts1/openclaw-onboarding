#!/usr/bin/env python3
"""test_lipsync_plan_n116.py: lip-sync placement (row N-116, section 3.3c).

Run: python3 scripts/core/storyboard/test_lipsync_plan_n116.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import storyboard.lipsync_plan as P                          # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def cand(cid, start, end, role="lead", anchor="", **kw):
    row = {"candidate_id": cid, "start_s": start, "end_s": end, "role": role,
           "anchor": anchor}
    row.update(kw)
    return row


def codes(plan):
    return sorted({f["code"] for f in plan["findings"]})


# The two fixed anchors are placed before anything is ranked (3.3c step 1).
rows = [cand("a", 1.0, 9.0), cand("b", 20.0, 28.0, role="other speaker"),
        cand("z", 80.0, 90.0, role="cta", anchor="ending")]
plan = P.plan_lipsync(rows, 100.0)


def test_run():
    global plan
    check("N-116 opening anchor placed", plan["anchors"]["opening"] == "a",
          plan["anchors"])
    check("N-116 ending anchor placed", plan["anchors"]["ending"] == "z",
          plan["anchors"])

    # A plan with no lead passage inside the first 15 s is refused.
    no_open = [cand("b", 20.0, 28.0), cand("z", 80.0, 90.0, role="cta",
                                           anchor="ending")]
    plan = P.plan_lipsync(no_open, 100.0)
    check("N-116 missing opening anchor refused",
          "LIPSYNC_ANCHOR_MISSING" in codes(plan), codes(plan))

    # A long sung stretch with no lip-sync between pieces is refused.
    gap = [cand("a", 1.0, 9.0), cand("z", 80.0, 90.0, role="cta",
                                     anchor="ending"),
           cand("m", 60.0, 66.0, instrumental=False)]
    plan = P.plan_lipsync(gap, 100.0, target_lo=0.1, target_hi=0.3,
                          gap_seconds=20.0, gap_fraction=0.0)
    check("N-116 long gap refused", "LIPSYNC_GAP_TOO_LONG" in codes(plan),
          codes(plan))

    # One quarter holding over 40 percent of the share is refused.
    clump = [cand("a", 1.0, 9.0), cand("b", 10.0, 18.0), cand("c", 19.0, 27.0),
             cand("z", 95.0, 100.0, role="cta", anchor="ending")]
    plan = P.plan_lipsync(clump, 100.0, target_lo=0.4, target_hi=0.4,
                          gap_seconds=99.0, gap_fraction=0.0)
    check("N-116 clumped share refused", "LIPSYNC_CLUMPED" in codes(plan),
          codes(plan))

    # The plan is written to storyboard/lipsync-plan.json.
    run_dir = tempfile.mkdtemp()
    path = P.write_plan(run_dir, plan)
    check("N-116 plan file written",
          os.path.basename(path) == "lipsync-plan.json"
          and os.path.exists(path), path)

    # Whole sentences win over the top: an over-target share is reported, not cut.
    # A 40-second video carrying a 14s opening piece and a 9s ending piece holds
    # 23 seconds: 57.5 percent, past the 35 percent top, and every piece is kept.
    over = [cand("a", 1.0, 15.0), cand("z", 30.0, 39.0, role="cta",
                                       anchor="ending")]
    plan = P.plan_lipsync(over, 40.0)
    check("N-116 overrun is reported, not refused",
          plan["share_percent"] > 35.0 and plan["over_hard_top"] is True
          and len(plan["pieces"]) == 2, (plan["share_percent"], plan["pieces"]))

    # 3.3a rule 4: one piece over 30 seconds is refused and stitched instead of
    # being planned whole. A 25-second piece is still one piece.
    long_piece = [cand("a", 1.0, 40.0), cand("z", 95.0, 105.0, role="cta",
                                             anchor="ending")]
    plan = P.plan_lipsync(long_piece, 120.0, gap_seconds=99.0, gap_fraction=0.0)
    check("N-116 a 39s passage refuses LIPSYNC_AUDIO_TOO_LONG",
          "LIPSYNC_AUDIO_TOO_LONG" in codes(plan)
          and all(c["candidate_id"] != "a" for c in plan["pieces"]),
          (codes(plan), plan["pieces"]))
    ok_piece = [cand("a", 1.0, 25.0), cand("z", 95.0, 105.0, role="cta",
                                           anchor="ending")]
    plan = P.plan_lipsync(ok_piece, 120.0, gap_seconds=99.0, gap_fraction=0.0)
    check("N-116 a 24s piece is planned whole, not refused",
          "LIPSYNC_AUDIO_TOO_LONG" not in codes(plan)
          and [c["candidate_id"] for c in plan["pieces"]] == ["a", "z"],
          (codes(plan), plan["pieces"]))

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_run()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
