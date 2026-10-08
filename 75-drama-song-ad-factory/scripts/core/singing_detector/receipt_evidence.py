#!/usr/bin/env python3
"""Honest receipts for sung/spoken share (Trevor order 1135, Part G, item 5).

The failed ad: the receipt claimed "54% sung" -- that number was only time
inside [Verse]/[Chorus] section LABELS, never measured singing. Suno spoke
every line and the waiver accepted the fake number.

Rule from the order: receipts and stage reports print MEASURED sung/spoken
%, the DETECTOR NAME and CONFIDENCE. "Labelled time" may never be reported
as sung.

What this module owns and nothing else:

1. ``measured_share()`` -- the one legal way to put a sung/spoken % on a
   receipt. The % must come from the measured singing detector (G3,
   ``scripts/core/singing_detector/singing_detector.py``, parallel build)
   with its detector name and confidence. Returns a receipt block:
   ``{source: "measured", detector, confidence, share, share_pct, ...}``.
2. ``labelled_share()`` -- section-label time is NEVER sung. It may appear
   only under explicitly named ``labelled_*`` fields
   (``labelled_sung_seconds``, ``labelled_share_pct``, ``labelled_source``),
   and carries ``source: "labelled"`` so no consumer can mistake it for a
   measurement.
3. ``check_receipt()`` -- the fail-closed reader a receipt test calls:
   hands it any receipt/report dict carrying a sung % and it FAILS if that
   % is label-derived or missing detector + confidence. An empty reasons
   list is the only pass.
4. ``require_measured()`` -- producers call this before printing a sung %;
   raises on a label-derived or detector-less share so a bad receipt can
   not be written at all.

Measuring without the detector is impossible here by construction: the
detector shares audio it has itself analysed, so this module takes the
measured share FROM a detector result record, never computes one from
timing segments or lyric labels. A timing-segment share (the D15 spoken-
share band) is a PLANNING number; the G5 rule makes it ineligible for a
receipt's sung % unless it too is stamped measured by the detector.

API contract with G3 (parallel build; the train resolve wires it):
    scripts/core/singing_detector/singing_detector.py exposes
    ``share(name, confidence)`` -> a measured result record, at least
    ``{"tool": <detector name>, "tool_version": ..., "sung_share": <0..1>,
       "confidence": <0..1>, "measured": True}``.
    G5 reads only those five keys (see DETECTOR_KEYS) and accepts either
    the record itself or ``{"detector_result": record}``. Until G3 lands
    on main, callers pass the record; this module never imports G3.

stdlib only: no network, no provider, no spend, no media file, no absolute
operator path (nothing in this package opens a file at all).

Run: python3 core/singing_detector/test_receipt_evidence_g5.py
"""
from __future__ import annotations

from math import isfinite

TOOL_NAME = "singing_detector.receipt_evidence"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.receipt-evidence/v1"
SOURCE = "Trevor order 1135 2026-10-08, Part G item G5"

#: The only legal source stamp for a sung/spoken % on a receipt.
MEASURED = "measured"
#: Section-label time: legal ONLY under labelled_* fields, never as sung.
LABELLED = "labelled"

#: The keys G5 reads from a G3 detector result record (the API contract).
DETECTOR_KEYS = ("tool", "tool_version", "sung_share", "confidence",
                 "measured")

#: Field names a receipt may use for a sung/spoken percent.
SUNG_PCT_FIELDS = ("sung_pct", "sung_share_pct", "sung_share",
                   "share_pct", "share", "sung_seconds",
                   "spoken_pct", "spoken_share_pct", "spoken_share",
                   "spoken_style_share")


class ReceiptEvidenceError(ValueError):
    """Malformed input or a dishonest receipt -- caller bug or producer bug."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _fraction(value, what, code):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReceiptEvidenceError(code, "%s must be a number, got %r"
                                   % (what, value))
    value = float(value)
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ReceiptEvidenceError(
            code, "%s must be a finite fraction 0..1, got %r" % (what, value))
    return value


def measured_share(detector_result):
    """The one legal sung/spoken receipt block, from a measured detector run.

    ``detector_result`` is the G3 record (or {"detector_result": record}).
    Returns a receipt block stamped ``source: "measured"`` carrying the
    detector name, its version, the confidence, and the sung share in both
    fraction and percent. Raises (never coerces) on a malformed record or
    a record that does not declare itself measured -- a silent fall-back
    to labels is exactly the failure this unit exists to make impossible.
    """
    if not isinstance(detector_result, dict):
        raise ReceiptEvidenceError(
            "BAD_DETECTOR_RESULT",
            "detector_result must be a record, got %r"
            % (type(detector_result).__name__,))
    rec = detector_result.get("detector_result", detector_result)
    if not isinstance(rec, dict):
        raise ReceiptEvidenceError(
            "BAD_DETECTOR_RESULT",
            "detector_result must carry the detector record")
    if rec.get("measured") is not True:
        raise ReceiptEvidenceError(
            "NOT_MEASURED",
            "detector record must carry measured=True; a receipt sung % "
            "without a measured detector run is the failed-ad shape")
    missing = [k for k in DETECTOR_KEYS if rec.get(k) is None]
    if missing:
        raise ReceiptEvidenceError(
            "DETECTOR_RECORD_INCOMPLETE",
            "detector record missing %s" % (missing,))
    sung = _fraction(rec["sung_share"], "sung_share", "BAD_SHARE")
    confidence = _fraction(rec["confidence"], "confidence", "BAD_CONFIDENCE")
    return {
        "source": MEASURED,
        "source_detail": "measured singing detector (G3), never labels",
        "detector": str(rec["tool"]),
        "detector_version": str(rec["tool_version"]),
        "confidence": round(confidence, 4),
        "sung_share": round(sung, 6),
        "sung_pct": round(sung * 100.0, 1),
        "spoken_pct": round((1.0 - sung) * 100.0, 1),
        "checker_version": TOOL_VERSION,
        "source_ref": SOURCE,
    }


def labelled_share(labelled_sung_seconds, total_seconds):
    """Section-label time, boxed where it can never be read as sung.

    Field names say what they are: ``labelled_sung_seconds``,
    ``labelled_share_pct`` and ``labelled_source``. Raises on a negative
    or non-finite input; total <= 0 is refused (share undefined), never
    reported as 0%.
    """
    secs = labelled_sung_seconds
    if isinstance(secs, bool) or not isinstance(secs, (int, float)) \
            or not isfinite(secs) or secs < 0:
        raise ReceiptEvidenceError(
            "BAD_LABELLED_SECONDS",
            "labelled_sung_seconds must be a finite number >= 0, got %r"
            % (secs,))
    total = total_seconds
    if isinstance(total, bool) or not isinstance(total, (int, float)) \
            or not isfinite(total) or total <= 0:
        raise ReceiptEvidenceError(
            "BAD_TOTAL_SECONDS",
            "total_seconds must be a finite positive number, got %r"
            % (total,))
    share = min(1.0, secs / total)
    return {
        "labelled_source": "section labels ([Verse]/[Chorus] time), "
                           "NOT measured singing",
        "labelled_sung_seconds": round(float(secs), 6),
        "labelled_share_pct": round(share * 100.0, 1),
    }


def check_receipt(receipt):
    """Fail-closed receipt reader: FAIL when a sung % is label-derived.

    Hand it any receipt / stage-report dict. Rules:

    * every sung/spoken percent field present must carry ``source ==
      "measured"`` (a measured_share() block) -- same dict or nested
      under the field's own record;
    * any ``source`` of "labelled", "labels", "section-labels", "timing"
      or "plan" on a sung % field is a FAIL (the failed-ad shape);
    * a measured block without detector + confidence is a FAIL.

    Returns {"verdict": PASS|FAIL, "reasons": [...]}. Never raises on a
    dishonest receipt -- that is a FAIL verdict, not an error. Raises
    ReceiptEvidenceError only for a malformed (non-dict) receipt.
    """
    if not isinstance(receipt, dict):
        raise ReceiptEvidenceError(
            "BAD_RECEIPT", "receipt must be a dict, got %r"
            % (type(receipt).__name__,))
    reasons = []
    for field in SUNG_PCT_FIELDS:
        if field not in receipt:
            continue
        value = receipt[field]
        block = value if isinstance(value, dict) else receipt
        source = block.get("source")
        if source is None:
            reasons.append(
                "%s carries no source; a sung %% must be stamped "
                "source=measured with detector + confidence" % field)
        elif str(source).strip().lower() != MEASURED:
            reasons.append(
                "%s source=%r: labelled time may never be reported as "
                "sung; print the measured detector %% instead" % (field, source))
            continue
        if str(source).strip().lower() == MEASURED:
            if not block.get("detector"):
                reasons.append("%s is stamped measured but carries no "
                               "detector name" % field)
            conf = block.get("confidence")
            if (isinstance(conf, bool) or not isinstance(conf, (int, float))
                    or not isfinite(conf) or not 0.0 <= float(conf) <= 1.0):
                reasons.append("%s is stamped measured but carries no "
                               "valid confidence (0..1)" % field)
    return {"verdict": "FAIL" if reasons else "PASS",
            "verifier_version": TOOL_VERSION,
            "source_ref": SOURCE,
            "reasons": reasons}


def require_measured(detector_result):
    """Producers call this before printing a sung %: measured block or raise.

    The G5 gate for every receipt/stage-report writer -- a label-derived
    share can never reach a receipt because this raises first.
    """
    return measured_share(detector_result)


__all__ = [
    "DETECTOR_KEYS", "LABELLED", "MEASURED", "RECEIPT_SOURCE_LABEL",
    "ReceiptEvidenceError", "SCHEMA_VERSION", "SOURCE", "SUNG_PCT_FIELDS",
    "TOOL_NAME", "TOOL_VERSION", "check_receipt", "labelled_share",
    "measured_share", "require_measured",
]

# ``RECEIPT_SOURCE_LABEL`` is the deprecated alias kept so the first tests
# referencing it by typo'd name still import; do not use in new code.
RECEIPT_SOURCE_LABEL = LABELLED
