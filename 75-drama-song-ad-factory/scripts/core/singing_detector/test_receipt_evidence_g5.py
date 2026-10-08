#!/usr/bin/env python3
"""G5 honest-receipt suite: a sung % with source=labels FAILS.

Trevor order 1135, Part G item G5. The failed ad's receipt claimed "54%
sung" -- that number was only time inside [Verse]/[Chorus] LABELS, never
measured. This suite plants the failed-ad shape and proves the reader
fails it, then proves the only legal shape (source=measured, detector
name, confidence). A checker that cannot fail is not evidence.

stdlib only. Run: python3 core/singing_detector/test_receipt_evidence_g5.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import receipt_evidence as RE  # noqa: E402

_passed = [0]
_failed = [0]


def check(name, ok, got=None):
    if ok:
        _passed[0] += 1
    else:
        _failed[0] += 1
        print("FAIL %s: %r" % (name, got))


def meas(sung=0.54, conf=0.9, name="singing_detector.v1"):
    return {"tool": name, "tool_version": "1.0.0", "sung_share": sung,
            "confidence": conf, "measured": True}


# ---- 1. the failed-ad shape: labels are not measured -----------------------
LABELLERD = {                       # the shape that lied: 54% from labels
    "sung_pct": 54.0,
    "source": "labels",
}
r = RE.check_receipt(dict(LABELLERD, receipt_id="o3"))
check("label-source-fails", r["verdict"] == "FAIL", r)
check("label-reason-names-labels",
      any("label" in x for x in r["reasons"]), r["reasons"])

for bad_source in ("labelled", "section-labels", "timing", "plan", "LYRICS"):
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

# ---- 4. the only legal shape passes ----------------------------------------
block = RE.measured_share(meas(sung=0.02, conf=0.93))
check("measured-block-source", block["source"] == "measured", block)
check("measured-block-detector",
      block["detector"] == "singing_detector.v1", block)
check("measured-block-confidence", block["confidence"] == 0.93, block)
check("measured-block-pct", block["sung_pct"] == 2.0, block)
check("measured-block-spoken", block["spoken_pct"] == 98.0, block)
r = RE.check_receipt({"receipt_id": "honest", "sung_pct": block})
check("measured-block-passes", r["verdict"] == "PASS", r)

# the failed-ad receipt REBUILT honestly: detector says ~0% sung
block0 = RE.measured_share(meas(sung=0.0, conf=0.95))
check("all-spoken-measured-zero",
      block0["sung_pct"] == 0.0 and block0["spoken_pct"] == 100.0, block0)
r = RE.check_receipt({"receipt_id": "honest-o3", "sung_pct": block0,
                      "labelled": RE.labelled_share(162.0, 300.0)})
check("labels-boxed-under-labelled-fields-pass",
      r["verdict"] == "PASS", r)

# ---- 5. labelled_share boxes labels where they can never be sung -----------
lab = RE.labelled_share(162.0, 300.0)
check("labelled-fields-prefixed",
      set(lab) == {"labelled_source", "labelled_sung_seconds",
                   "labelled_share_pct"}, lab)
check("labelled-pct-value", lab["labelled_share_pct"] == 54.0, lab)
check("labelled-source-says-not-measured",
      "NOT measured" in lab["labelled_source"], lab)
# and a receipt carrying ONLY labelled fields (no measured block) fails
r = RE.check_receipt({"sung_pct": lab["labelled_share_pct"],
                      "source": "labelled"})
check("bare-labelled-as-sung-fails", r["verdict"] == "FAIL", r)

# ---- 6. require_measured: producer gate raises on the lie ------------------
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

# ---- 7. detector wrapper accepted ({"detector_result": record}) ------------
block = RE.measured_share({"detector_result": meas()})
check("wrapper-record-accepted", block["detector"] == "singing_detector.v1",
      block)

# ---- 8. every sung-pct field name is covered --------------------------------
for field in ("sung_pct", "sung_share_pct", "share_pct",
              "spoken_pct", "spoken_share", "sung_seconds"):
    r = RE.check_receipt({field: 54.0, "source": "labels"})
    check("field-%s-labels-fail" % field, r["verdict"] == "FAIL", r)

# ---- 9. malformed input raises (caller bug), never a silent pass -----------
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

# ---- 10. receipt carrying no sung fields at all passes ----------------------
r = RE.check_receipt({"receipt_id": "audio-only", "frames": 900})
check("no-sung-fields-passes", r["verdict"] == "PASS", r)

print("PASS %d / FAIL %d" % (_passed[0], _failed[0]))
sys.exit(1 if _failed[0] else 0)
