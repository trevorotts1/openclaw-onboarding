#!/usr/bin/env python3
"""G5 honest-receipt suite: a sung % with source=labels FAILS.

Trevor order 1135, Part G item G5, AMENDED by TREVOR-ORDER-1150-partG-amend
(review item G8): the receipt carries the measured sung / spoken / rap /
no-voice shares (percent AND seconds), the target, the gap and every take
tried; label-based shares live only under the ``planned`` heading.

The failed ad's receipt claimed "54% sung" -- that number was only time
inside [Verse]/[Chorus] LABELS, never measured. This suite plants the
failed-ad shape and proves the reader fails it, then proves the only legal
shape (source=measured, detector name, confidence, four-way shares, target,
gap, takes). A checker that cannot fail is not evidence.

stdlib only. Run: python3 core/singing_detector/test_receipt_evidence_g5.py
"""
from __future__ import annotations

import os
import sys

# pytest-collectable: this is a self-running suite (CI runs the file
# directly); when pytest imports it for collection, skip -- its module
# body runs checks and exits, which used to raise INTERNALERROR /
# collection errors.
if "pytest" in sys.modules:  # imported by pytest for collection
    import pytest as _pytest
    _pytest.skip("self-running suite: run `python3 test_receipt_evidence_g5.py`",
                 allow_module_level=True)

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from singing_detector import receipt_evidence as RE  # noqa: E402

_passed = [0]
_failed = [0]


def check(name, ok, got=None):
    if ok:
        _passed[0] += 1
    else:
        _failed[0] += 1
        print("FAIL %s: %r" % (name, got))


def meas(sung=0.54, conf=0.9, name="singing_detector.v1", spoken=None,
         rap=0.0, no_voice=0.0, runtime=300.0, take="o3", **extra):
    """A complete G3 record: four runtime shares that add up to 1."""
    if spoken is None:
        spoken = 1.0 - sung - rap - no_voice
    rec = {"tool": name, "tool_version": "1.0.0", "sung_share": sung,
           "spoken_share": spoken, "rap_share": rap,
           "no_voice_share": no_voice, "confidence": conf,
           "measured": True, "runtime_s": runtime, "take": take}
    rec.update(extra)
    return rec


# ---- 1. the failed-ad shape: labels are not measured -----------------------
LABELLERD = {                       # the shape that lied: 54% from labels
    "sung_pct": 54.0,
    "source": "labels",
}
r = RE.check_receipt(dict(LABELLERD, receipt_id="o3"))
check("label-source-fails", r["verdict"] == "FAIL", r)
check("label-reason-names-labels",
      any("label" in x for x in r["reasons"]), r["reasons"])

for bad_source in ("labelled", "section-labels", "timing", "plan", "LYRICS",
                   "planned"):
    r = RE.check_receipt({"sung_pct": 54.0, "source": bad_source})
    check("source-%s-fails" % bad_source, r["verdict"] == "FAIL", r)

# ---- 2. no source at all fails ---------------------------------------------
r = RE.check_receipt({"sung_pct": 54.0})
check("no-source-fails", r["verdict"] == "FAIL", r)

# ---- 3. measured stamp without detector/confidence fails -------------------
r = RE.check_receipt({"sung_pct": 54.0, "source": "measured"})
check("measured-no-detector-fails", r["verdict"] == "FAIL", r)
r = RE.check_receipt({"sung_pct": 54.0, "source": "measured",
                      "detector": "singing_detector.v1"})
check("measured-no-confidence-fails", r["verdict"] == "FAIL", r)
r = RE.check_receipt({"sung_pct": 54.0, "source": "measured",
                      "detector": "singing_detector.v1",
                      "confidence": 1.5})
check("measured-bad-confidence-fails", r["verdict"] == "FAIL", r)

# ---- 4. the four measured shares, percent AND seconds ----------------------
block = RE.measured_share(meas(sung=0.02, conf=0.93))
check("measured-block-source", block["source"] == "measured", block)
check("measured-block-detector",
      block["detector"] == "singing_detector.v1", block)
check("measured-block-confidence", block["confidence"] == 0.93, block)
check("measured-block-pct", block["sung_pct"] == 2.0, block)
check("measured-block-spoken", block["spoken_pct"] == 98.0, block)
check("measured-block-rap-pct", block["rap_pct"] == 0.0, block)
check("measured-block-no-voice-pct", block["no_voice_pct"] == 0.0, block)
check("measured-block-sung-seconds",
      block["sung_seconds"] == 6.0, block["sung_seconds"])
check("measured-block-spoken-seconds",
      block["spoken_seconds"] == 294.0, block["spoken_seconds"])
check("measured-block-runtime", block["runtime_s"] == 300.0, block)

# the amended receipt shape: shares + target + gap + takes
amended = RE.receipt_block(
    meas(sung=0.24, rap=0.12, spoken=0.49, no_voice=0.15, take="C-0"),
    target={"sung_share": 0.55, "spoken_share": 0.375, "length_s": 300.0},
    takes=[{"take": "C-0", "source": "measured",
            "detector": "singing_detector.v1", "confidence": 0.9,
            "sung_pct": 24.0, "spoken_pct": 49.0, "rap_pct": 12.0,
            "no_voice_pct": 15.0},
           {"take": "X0", "rejected": True,
            "reasons": ["unmeasurable: OSError: stem missing"]}],
    rounds_used=2,
    selected_take="C-0",
    planned=RE.planned_share(61.1, 300.0),
)
check("amended-carries-sung-rap-no-voice",
      {"sung_pct", "rap_pct", "no_voice_pct", "spoken_pct"} <= set(amended),
      sorted(amended))
check("amended-carries-target", amended["target"]["sung_share"] == 0.55,
      amended["target"])
check("amended-gap-sung",
      amended["gap"]["sung_share"] == -31.0, amended["gap"])
check("amended-gap-spoken",
      amended["gap"]["spoken_share"] == 11.5, amended["gap"])
check("amended-gap-length-from-verdict-absent",
      amended["gap"]["length_s"] is None, amended["gap"])
check("amended-carries-takes", len(amended["takes"]) == 2, amended["takes"])
check("amended-carries-rounds", amended["rounds_used"] == 2, amended)
check("amended-carries-selected", amended["selected_take"] == "C-0",
      amended)
check("amended-planned-boxed",
      "planned_share_pct" in amended["planned"], amended["planned"])
r = RE.check_receipt(amended)
check("amended-receipt-passes", r["verdict"] == "PASS", r)

# the failed-ad receipt REBUILT honestly: detector says ~0% sung
block0 = RE.measured_share(meas(sung=0.0, conf=0.95))
check("all-spoken-measured-zero",
      block0["sung_pct"] == 0.0 and block0["spoken_pct"] == 100.0, block0)
r = RE.check_receipt(RE.receipt_block(
    meas(sung=0.0, conf=0.95, take="o3"),
    planned=RE.labelled_share(162.0, 300.0)))
check("honest-o3-passes", r["verdict"] == "PASS", r)

# ---- 5. a measured % with no takes is an incomplete receipt ----------------
r = RE.check_receipt({"sung_pct": block, "target": {"sung_share": 0.55},
                      "gap": {"sung_share": -31.0}})
check("measured-without-takes-fails", r["verdict"] == "FAIL", r)
check("measured-without-takes-reason",
      any("takes" in x for x in r["reasons"]), r["reasons"])
r = RE.check_receipt({"sung_pct": block, "takes": []})
check("empty-takes-fails", r["verdict"] == "FAIL", r)
r = RE.check_receipt({"sung_pct": block, "takes": "C-0"})
check("takes-not-a-list-fails", r["verdict"] == "FAIL", r)

# a take with neither measured shares nor a recorded reason fails
r = RE.check_receipt({"sung_pct": block, "takes": [{"take": "Y1"}]})
check("take-without-shares-or-reason-fails", r["verdict"] == "FAIL", r)
r = RE.check_receipt({"sung_pct": block,
                      "takes": [{"take": "Y1", "rejected": True,
                                 "reasons": ["all-spoken take"]}]})
check("rejected-take-with-reason-passes", r["verdict"] == "PASS", r)

# a take that lies about its shares fails
r = RE.check_receipt({"sung_pct": block,
                      "takes": [{"take": "Z0", "sung_pct": 54.0,
                                 "source": "labels"}]})
check("label-derived-take-share-fails", r["verdict"] == "FAIL", r)

# selected_take must be one of the takes on the receipt
r = RE.check_receipt({"sung_pct": block,
                      "takes": [{"take": "C-0", "source": "measured",
                                 "detector": "d", "confidence": 0.9,
                                 "sung_pct": 24.0}],
                      "selected_take": "M2b"})
check("selected-take-not-on-receipt-fails", r["verdict"] == "FAIL", r)

# ---- 6. target / gap / rounds shape ----------------------------------------
r = RE.check_receipt({"sung_pct": block, "takes": RE.receipt_block(
    meas())["takes"], "target": "55%"})
check("target-not-a-dict-fails", r["verdict"] == "FAIL", r)
r = RE.check_receipt({"sung_pct": block, "takes": RE.receipt_block(
    meas())["takes"], "gap": {"sung_share": "31 points"}})
check("gap-not-numeric-fails", r["verdict"] == "FAIL", r)
r = RE.check_receipt({"sung_pct": block, "takes": RE.receipt_block(
    meas())["takes"], "rounds_used": 0})
check("rounds-must-be-positive-fails", r["verdict"] == "FAIL", r)
r = RE.check_receipt({"sung_pct": block, "takes": RE.receipt_block(
    meas())["takes"], "rounds_used": 3})
check("good-rounds-pass", r["verdict"] == "PASS", r)

# ---- 7. labelled_share / planned_share box label time ----------------------
lab = RE.labelled_share(162.0, 300.0)
check("labelled-fields-prefixed",
      set(lab) == {"labelled_source", "labelled_sung_seconds",
                   "labelled_share_pct"}, lab)
check("labelled-pct-value", lab["labelled_share_pct"] == 54.0, lab)
check("labelled-source-says-not-measured",
      "NOT measured" in lab["labelled_source"], lab)
plan = RE.planned_share(162.0, 300.0)
check("planned-fields-prefixed",
      set(plan) == {"planned_source", "planned_sung_seconds",
                    "planned_share_pct"}, plan)
check("planned-pct-value", plan["planned_share_pct"] == 54.0, plan)
check("planned-source-says-never-result",
      "NEVER the measured result" in plan["planned_source"], plan)
# and a receipt carrying ONLY labelled fields (no measured block) fails
r = RE.check_receipt({"sung_pct": lab["labelled_share_pct"],
                      "source": "labelled"})
check("bare-labelled-as-sung-fails", r["verdict"] == "FAIL", r)

# ---- 8. require_measured: producer gate raises on the lie ------------------
try:
    RE.require_measured({"sung_share": 0.54, "measured": False})
    check("require-raises-not-measured", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("require-raises-not-measured",
          exc.code == "NOT_MEASURED", exc.code)
try:
    RE.require_measured({"tool": "d", "tool_version": "1",
                         "sung_share": 0.5, "confidence": 0.9})
    check("require-raises-missing-measured-flag", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("require-raises-missing-measured-flag",
          exc.code == "NOT_MEASURED", exc.code)
check("require-returns-measured-block",
      RE.require_measured(meas())["source"] == "measured")

# ---- 9. detector wrapper accepted ({"detector_result": record}) ------------
block = RE.measured_share({"detector_result": meas()})
check("wrapper-record-accepted", block["detector"] == "singing_detector.v1",
      block)

# ---- 10. every delivery field name is covered -------------------------------
for field in ("sung_pct", "sung_share_pct", "share_pct",
              "spoken_pct", "spoken_share", "sung_seconds",
              "rap_pct", "no_voice_pct", "no_voice_share"):
    r = RE.check_receipt({field: 54.0, "source": "labels"})
    check("field-%s-labels-fail" % field, r["verdict"] == "FAIL", r)

# ---- 11. malformed input raises (caller bug), never a silent pass ----------
for bad in (None, "nope", [1, 2]):
    try:
        RE.check_receipt(bad)
        check("bad-receipt-%r-raises" % (bad,), False, "no raise")
    except RE.ReceiptEvidenceError as exc:
        check("bad-receipt-%r-raises" % (bad,), exc.code == "BAD_RECEIPT",
              exc.code)
try:
    RE.measured_share({"measured": True})
    check("incomplete-detector-record-raises", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("incomplete-detector-record-raises",
          exc.code == "DETECTOR_RECORD_INCOMPLETE", exc.code)
try:
    # sung + spoken + rap + no_voice do not add up to the runtime
    RE.measured_share(meas(sung=0.54, spoken=0.46, rap=0.30, no_voice=0.20))
    check("shares-that-do-not-sum-raise", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("shares-that-do-not-sum-raise", exc.code == "SHARE_SUM", exc.code)
try:
    # no runtime: the receipt could not carry seconds
    rec = meas()
    del rec["runtime_s"]
    RE.measured_share(rec)
    check("missing-runtime-raises", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("missing-runtime-raises",
          exc.code == "DETECTOR_RECORD_INCOMPLETE", exc.code)
try:
    # rap declared but no spoken share on the record
    rec = meas()
    del rec["rap_share"]
    RE.measured_share(rec)
    check("missing-rap-share-raises", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("missing-rap-share-raises",
          exc.code == "DETECTOR_RECORD_INCOMPLETE", exc.code)
try:
    RE.measured_share(meas(sung=1.5))
    check("share-out-of-range-raises", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("share-out-of-range-raises", exc.code == "BAD_SHARE", exc.code)
try:
    RE.labelled_share(-1.0, 300.0)
    check("negative-labelled-raises", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("negative-labelled-raises", exc.code == "BAD_LABELLED_SECONDS",
          exc.code)
try:
    RE.receipt_block(meas(), target={"sung_share": -1.0})
    check("negative-target-raises", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("negative-target-raises", exc.code == "BAD_TARGET", exc.code)

# ---- 12. target-engine verdict fills rounds / selected / gap ---------------
verdict = {
    "verdict": "ACCEPT",
    "rounds_used": 1,
    "targets": {"spoken_share": 0.225, "length_s": 300.0},
    "score": {"deviations_pct": {"spoken_share": 3.0, "length_s": 1.5}},
    "candidate": {"id": "t2"},
    "history": [{"round": 1, "verdict": "ACCEPT"}],
}
blk = RE.receipt_block(meas(sung=0.5, spoken=0.5, take="t2"), verdict=verdict)
check("verdict-rounds", blk["rounds_used"] == 1, blk)
check("verdict-selected", blk["selected_take"] == "t2", blk)
check("verdict-target", blk["target"]["spoken_share"] == 0.225, blk["target"])
check("verdict-gap-spoken", blk["gap"]["spoken_share"] == 27.5,
      blk["gap"])
check("verdict-gap-length",
      blk["gap"]["length_s"] == 1.5, blk["gap"])
check("verdict-receipt-passes", RE.check_receipt(blk)["verdict"] == "PASS",
      RE.check_receipt(blk))

# ---- 13. receipt carrying no sung fields at all passes ---------------------
r = RE.check_receipt({"receipt_id": "audio-only", "frames": 900})
check("no-sung-fields-passes", r["verdict"] == "PASS", r)

# ---- 14. G3's own spelling of the record (share_for_stem on main) ----------
g3 = {"detector": "singing_detector.v1", "detector_version": "2.0.0",
      "sung_share": 0.24, "spoken_share": 0.49, "rap_share": 0.12,
      "no_voice_share": 0.15, "confidence": 0.9,
      "share_source": "measured", "runtime_s": 300.0}
blk = RE.measured_share(g3)
check("g3-spelling-accepted",
      blk["detector"] == "singing_detector.v1"
      and blk["detector_version"] == "2.0.0"
      and blk["source"] == "measured", blk)
check("g3-spelling-shares",
      (blk["sung_pct"], blk["spoken_pct"], blk["rap_pct"],
       blk["no_voice_pct"]) == (24.0, 49.0, 12.0, 15.0), blk)
# ... but a detector that only measured SUNG is still refused, BY NAME:
# the amended receipt cannot print rap / spoken / no-voice it never got.
g3_sung_only = {"detector": "singing_detector.v1",
                "detector_version": "2.0.0", "sung_share": 0.24,
                "confidence": 0.9, "share_source": "measured",
                "runtime_s": 300.0}
try:
    RE.measured_share(g3_sung_only)
    check("g3-sung-only-refused", False, "no raise")
except RE.ReceiptEvidenceError as exc:
    check("g3-sung-only-refused",
          exc.code == "DETECTOR_RECORD_INCOMPLETE", exc.code)
    check("g3-sung-only-names-the-missing-shares",
          all(k in str(exc) for k in
              ("spoken_share", "rap_share", "no_voice_share")), str(exc))

def test_suite_checks_pass():
    assert _failed[0] == 0, "%d check(s) failed" % _failed[0]


if __name__ == "__main__":
    print("PASS %d / FAIL %d" % (_passed[0], _failed[0]))
    sys.exit(1 if _failed[0] else 0)
