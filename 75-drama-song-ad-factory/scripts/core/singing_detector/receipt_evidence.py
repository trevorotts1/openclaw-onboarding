#!/usr/bin/env python3
"""Honest receipts for sung/spoken share (Trevor order 1135, Part G, item 5,
AMENDED by Trevor order 1150 part G amend 2026-10-08 = review item G8).

The failed ad: the receipt claimed "54% sung" -- that number was only time
inside [Verse]/[Chorus] section LABELS, never measured singing. Suno spoke
every line and the waiver accepted the fake number.

Rule from the order: receipts and stage reports print MEASURED sung /
spoken / rap / no-voice shares, the TARGET, the GAP, and EVERY TAKE TRIED,
plus the detector name and confidence. Label-based shares may appear only
under the ``planned`` heading, never as the result.

What this module owns and nothing else:

1. ``measured_share()`` -- the one legal way to put a sung/spoken/rap/
   no-voice % on a receipt. The % must come from the measured singing
   detector (G3) with its detector name and confidence, and the four shares
   must add up to the runtime (Appendix A step 8: sung, spoken, no-voice of
   the runtime; rap is metered time split off by tag). Returns a receipt
   block: ``{source: "measured", detector, confidence, *_pct, *_seconds,
   ...}``.
2. ``labelled_share()`` / ``planned_share()`` -- section-label time is
   NEVER sung. It may appear only under explicitly named ``labelled_*`` /
   ``planned_*`` fields (or nested under the receipt's ``planned`` heading)
   and carries ``source: "labelled"`` / ``planned_source`` so no consumer
   can mistake it for a measurement.
3. ``gap_vs_target()`` -- signed percentage points from every target, the
   one arithmetic the receipt's ``gap`` field carries.
4. ``receipt_block()`` -- the amended G5 receipt: measured four-way shares,
   target, gap, every take tried, rounds used, the selected take, the
   detector version, stem id and timing source per take, and the planned
   (label) shares boxed under ``planned``.
5. ``check_receipt()`` -- the fail-closed reader a receipt test calls:
   hands it any receipt/report dict carrying a sung % and it FAILS if that
   % is label-derived or missing detector + confidence, if a measured % has
   no ``takes`` list, if a take carries no measured shares and no recorded
   reason, or if ``target``/``gap``/``rounds_used``/``selected_take`` are
   malformed or disagree with ``takes``. An empty reasons list is the only
   pass.
6. ``require_measured()`` -- producers call this before printing a sung %;
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
       "spoken_share": <0..1>, "rap_share": <0..1>,
       "no_voice_share": <0..1>, "confidence": <0..1>, "measured": True,
       "runtime_s": <seconds>}`` -- the four shares over the runtime
       (Appendix A step 8); ``runtime_s`` (or ``total_seconds`` /
       ``duration_s``) is what turns them into the seconds the receipt
       must also carry. G3's own ``share_for_stem`` spells the first two
       ``detector`` / ``detector_version`` and stamps ``share_source:
       "measured"``; FIELD_ALIASES accepts those spellings so the units
       never fail on a name -- only on a missing share. G5 reads those
       keys and accepts either the record itself or
       ``{"detector_result": record}``. Until G3 lands on main, callers
       pass the record; this module never imports G3.

stdlib only: no network, no provider, no spend, no media file, no absolute
operator path (nothing in this package opens a file at all).

Run: python3 core/singing_detector/test_receipt_evidence_g5.py
"""
from __future__ import annotations

from math import isfinite

TOOL_NAME = "singing_detector.receipt_evidence"
TOOL_VERSION = "2.0.0"
SCHEMA_VERSION = "blackceo.receipt-evidence/v2"
SOURCE = ("Trevor order 1135 2026-10-08, Part G item G5, AMENDED by "
          "TREVOR-ORDER-1150-partG-amend.md (review item G8)")

#: The only legal source stamp for a sung/spoken % on a receipt.
MEASURED = "measured"
#: Section-label time: legal ONLY under labelled_* / planned_* fields,
#: never as sung.
LABELLED = "labelled"
PLANNED = "planned"

#: The keys G5 reads from a G3 detector result record (the API contract).
#: The four shares are the runtime shares of Appendix A step 8; the record
#: must also name its runtime so the receipt can carry seconds.
DETECTOR_KEYS = ("tool", "tool_version", "sung_share", "spoken_share",
                 "rap_share", "no_voice_share", "confidence", "measured")

#: G3's own record spells these two differently (singing_detector.py
#: ``share_for_stem``: ``detector`` / ``detector_version`` /
#: ``share_source: "measured"``). Both spellings are accepted so the two
#: units do not fail on cosmetics at the train resolve -- the SHARES and
#: the runtime are what must be there, not the label on the name.
FIELD_ALIASES = {
    "tool": ("tool", "detector"),
    "tool_version": ("tool_version", "detector_version"),
}

#: Accepted spellings for the record's runtime, in priority order.
RUNTIME_KEYS = ("runtime_s", "total_seconds", "duration_s",
                "runtime_seconds")

#: The four shares must add up to the runtime; rounding aside, they do not.
SHARE_SUM_TOLERANCE = 0.02

#: The measured delivery keys, each needing a percent AND seconds.
DELIVERIES = ("sung", "spoken", "rap", "no_voice")

#: Field names a receipt may use for a delivery percent.
SUNG_PCT_FIELDS = ("sung_pct", "sung_share_pct", "sung_share",
                   "share_pct", "share", "sung_seconds",
                   "spoken_pct", "spoken_share_pct", "spoken_share",
                   "spoken_style_share",
                   "rap_pct", "rap_share_pct", "rap_share",
                   "no_voice_pct", "no_voice_share_pct", "no_voice_share")

#: Headings a label-derived share is allowed to live under. Anywhere else a
#: label-derived share is the failed-ad shape.
LABEL_HEADINGS = ("planned", "labelled", "labels", "section-labels")


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


def _field(rec, key):
    """One contract key, under its own name or G3's spelling of it."""
    for name in FIELD_ALIASES.get(key, (key,)):
        if rec.get(name) is not None:
            return rec.get(name)
    return None


def _declared_measured(rec):
    """measured=True, or G3's ``share_source: "measured"``."""
    if rec.get("measured") is True:
        return True
    return str(rec.get("share_source", "")).strip().lower() == MEASURED


def _runtime_of(rec):
    """The record's runtime in seconds, or None when it carries none."""
    for key in RUNTIME_KEYS:
        if key in rec and rec[key] is not None:
            value = rec[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not isfinite(value) or value <= 0:
                raise ReceiptEvidenceError(
                    "BAD_RUNTIME",
                    "%s must be a finite positive number of seconds, got %r"
                    % (key, value))
            return float(value)
    return None


def measured_share(detector_result):
    """The one legal delivery receipt block, from a measured detector run.

    ``detector_result`` is the G3 record (or {"detector_result": record}).
    Returns a receipt block stamped ``source: "measured"`` carrying the
    detector name, its version, the confidence, and the sung / spoken /
    rap / no-voice share in both fraction and percent plus their seconds.
    Raises (never coerces) on a malformed record, a record that does not
    declare itself measured, a record missing any of the four shares or
    its runtime, or four shares that do not add up to the runtime -- a
    silent fall-back to labels is exactly the failure this unit exists to
    make impossible.
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
    if not _declared_measured(rec):
        raise ReceiptEvidenceError(
            "NOT_MEASURED",
            "detector record must carry measured=True (or G3's "
            "share_source='measured'); a receipt sung % without a measured "
            "detector run is the failed-ad shape")
    missing = [k for k in DETECTOR_KEYS if k != "measured"
               and _field(rec, k) is None]
    if missing:
        raise ReceiptEvidenceError(
            "DETECTOR_RECORD_INCOMPLETE",
            "detector record missing %s (the amended receipt carries the "
            "measured sung/spoken/rap/no-voice shares and its runtime)"
            % (missing,))
    runtime = _runtime_of(rec)
    if runtime is None:
        raise ReceiptEvidenceError(
            "DETECTOR_RECORD_INCOMPLETE",
            "detector record carries no runtime (%s); the amended receipt "
            "must print measured seconds as well as percent"
            % ("/".join(RUNTIME_KEYS),))
    shares = {name: _fraction(_field(rec, "%s_share" % name),
                              "%s_share" % name, "BAD_SHARE")
              for name in DELIVERIES}
    total = sum(shares.values())
    if abs(total - 1.0) > SHARE_SUM_TOLERANCE:
        raise ReceiptEvidenceError(
            "SHARE_SUM",
            "sung + spoken + rap + no_voice = %s of the runtime; the four "
            "measured shares must add up to 1 (tolerance %s)"
            % (round(total, 6), SHARE_SUM_TOLERANCE))
    confidence = _fraction(rec["confidence"], "confidence", "BAD_CONFIDENCE")
    block = {
        "source": MEASURED,
        "source_detail": "measured singing detector (G3), never labels",
        "detector": str(_field(rec, "tool")),
        "detector_version": str(_field(rec, "tool_version")),
        "confidence": round(confidence, 4),
        "runtime_s": round(runtime, 6),
        "checker_version": TOOL_VERSION,
        "source_ref": SOURCE,
    }
    for name, share in shares.items():
        seconds_key = "%s_seconds" % name
        if rec.get(seconds_key) is not None:
            secs = rec[seconds_key]
            if isinstance(secs, bool) or not isinstance(secs, (int, float)) \
                    or not isfinite(secs) or secs < 0 \
                    or secs > runtime + 1e-6:
                raise ReceiptEvidenceError(
                    "BAD_SECONDS",
                    "%s must be a finite number within 0..runtime_s, got "
                    "%r" % (seconds_key, rec[seconds_key]))
            secs = float(secs)
        else:
            secs = share * runtime
        block["%s_share" % name] = round(share, 6)
        block["%s_pct" % name] = round(share * 100.0, 1)
        block[seconds_key] = round(secs, 3)
    return block


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


def planned_share(planned_sung_seconds, total_seconds):
    """The amended vocabulary: label time reported as PLANNED, never sung.

    Same arithmetic and the same refusal rules as ``labelled_share()``;
    the field names say ``planned_*`` (Trevor order 1150 part G amend,
    review G8: "Planned (label) shares may appear only under the heading
    'planned', never as the result").
    """
    lab = labelled_share(planned_sung_seconds, total_seconds)
    return {
        "planned_source": "planned from section labels ([Verse]/[Chorus] "
                          "time), NEVER the measured result",
        "planned_sung_seconds": lab["labelled_sung_seconds"],
        "planned_share_pct": lab["labelled_share_pct"],
    }


def gap_vs_target(block, target=None, verdict=None):
    """Signed percentage points from every target, or {} with no target.

    Share axes (``*_share``) are compared in points against the measured
    percent of the same delivery: negative = under target, positive =
    over. Non-share axes (``length_s``) take the absolute points-off the
    target engine's own score already computed, because seconds have no
    signed percent against a receipt percent. Axes nothing measured are
    recorded as None -- an unmeasured gap is never reported as 0.
    """
    if target is None:
        target = verdict.get("targets") if isinstance(verdict, dict) else None
    if target is None:
        return {}
    if not isinstance(target, dict) or not target:
        raise ReceiptEvidenceError(
            "BAD_TARGET", "target must be a non-empty dict, got %r"
            % (type(target).__name__,))
    score = verdict.get("score") if isinstance(verdict, dict) else None
    devs = (score or {}).get("deviations_pct") if isinstance(score, dict) \
        else None
    gap = {}
    for axis, value in target.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not isfinite(value) or value < 0:
            raise ReceiptEvidenceError(
                "BAD_TARGET", "target[%r] must be a finite number >= 0, "
                "got %r" % (axis, value))
        if axis.endswith("_share"):
            name = axis[:-len("_share")]
            pct = block.get("%s_pct" % name)
            if pct is None:
                gap[axis] = None
            else:
                gap[axis] = round(float(pct) - float(value) * 100.0, 2)
        else:
            gap[axis] = None if not isinstance(devs, dict) \
                else devs.get(axis)
    return gap


def _take_from_block(block, rec):
    """The default take record: the measured take itself, honestly."""
    take = {"take": str(rec.get("take") or rec.get("id")
                        or rec.get("name") or "measured-take"),
            "source": block["source"],
            "detector": block["detector"],
            "detector_version": block["detector_version"],
            "confidence": block["confidence"]}
    for name in DELIVERIES:
        take["%s_pct" % name] = block["%s_pct" % name]
        take["%s_seconds" % name] = block["%s_seconds" % name]
    for key in ("stem_id", "timing_source", "rounds_used"):
        if rec.get(key) is not None:
            take[key] = rec[key]
    return take


def receipt_block(detector_result, target=None, takes=None, verdict=None,
                  planned=None, rounds_used=None, selected_take=None):
    """The amended G5 receipt: shares + target + gap + every take tried.

    Returns one flat dict carrying:

    * the measured sung / spoken / rap / no-voice percent AND seconds with
      the detector name, version and confidence (``measured_share()``);
    * ``target`` -- the target set (from ``verdict["targets"]`` when the
      caller passes a target-engine verdict and no explicit target);
    * ``gap`` -- signed points from every target (``gap_vs_target()``);
    * ``takes`` -- every take tried, each stamped measured or carrying its
      recorded reason; defaults to the one take the detector measured;
    * ``rounds_used`` / ``selected_take`` -- from the verdict when given;
    * ``planned`` -- the label-based shares, under their own heading only.

    Raises on a malformed record/target/takes (caller bug). A dishonest
    label-derived share can not be built here at all: shares only come
    from the measured detector record.
    """
    rec = detector_result.get("detector_result", detector_result) \
        if isinstance(detector_result, dict) else detector_result
    block = measured_share(detector_result)
    if isinstance(rec, dict):
        if target is None and isinstance(verdict, dict):
            target = verdict.get("targets")
        if rounds_used is None and isinstance(verdict, dict):
            rounds_used = verdict.get("rounds_used")
        if selected_take is None and isinstance(verdict, dict):
            candidate = verdict.get("candidate")
            if isinstance(candidate, dict):
                selected_take = candidate.get("id", candidate.get("take"))
            elif candidate is not None:
                selected_take = candidate
        if takes is None:
            takes = [_take_from_block(block, rec)]
    if takes is None:
        takes = [_take_from_block(block, rec if isinstance(rec, dict)
                                  else detector_result)]
    if takes is not None and len(takes) == 1 \
            and isinstance(takes[0], dict) \
            and takes[0].get("take") == "measured-take" \
            and selected_take is not None:
        # one take measured and the verdict names it: stamp the id, the
        # record itself did not carry one.
        takes[0]["take"] = selected_take
    if not isinstance(takes, list) or not takes:
        raise ReceiptEvidenceError(
            "BAD_TAKES", "takes must be a non-empty list of take records, "
            "got %r" % (takes,))
    block["target"] = target
    block["gap"] = gap_vs_target(block, target, verdict)
    block["takes"] = takes
    block["rounds_used"] = rounds_used
    block["selected_take"] = selected_take
    if planned is not None:
        if not isinstance(planned, dict) or not planned:
            raise ReceiptEvidenceError(
                "BAD_PLANNED", "planned must be a non-empty dict of "
                "planned_* fields, got %r" % (planned,))
        block["planned"] = planned
    return block


def _scan_share_fields(block, label, reasons):
    """One dict's sung/% fields must all be stamped measured."""
    measured_seen = False
    for field in SUNG_PCT_FIELDS:
        if field not in block:
            continue
        value = block[field]
        inner = value if isinstance(value, dict) else block
        source = inner.get("source")
        if source is None:
            reasons.append(
                "%s.%s carries no source; a sung %% must be stamped "
                "source=measured with detector + confidence"
                % (label, field))
            continue
        if str(source).strip().lower() != MEASURED:
            reasons.append(
                "%s.%s source=%r: labelled time may never be reported as "
                "sung; print the measured detector %% instead"
                % (label, field, source))
            continue
        measured_seen = True
        if not inner.get("detector"):
            reasons.append("%s.%s is stamped measured but carries no "
                           "detector name" % (label, field))
        conf = inner.get("confidence")
        if (isinstance(conf, bool) or not isinstance(conf, (int, float))
                or not isfinite(conf) or not 0.0 <= float(conf) <= 1.0):
            reasons.append("%s.%s is stamped measured but carries no "
                           "valid confidence (0..1)" % (label, field))
    return measured_seen


def _valid_number_map(value):
    if not isinstance(value, dict) or not value:
        return False
    for item in value.values():
        if isinstance(item, bool) or not isinstance(item, (int, float)) \
                or not isfinite(item):
            return False
    return True


def check_receipt(receipt):
    """Fail-closed receipt reader: FAIL when a sung % is label-derived.

    Hand it any receipt / stage-report dict. Rules:

    * every sung/spoken/rap/no-voice percent field present must carry
      ``source == "measured"`` (a measured_share() block) -- same dict or
      nested under the field's own record;
    * any ``source`` of "labelled", "labels", "section-labels", "timing"
      or "plan" on a sung % field is a FAIL (the failed-ad shape) -- a
      label-derived share belongs under the ``planned`` heading only;
    * a measured block without detector + confidence is a FAIL;
    * a measured sung % without a non-empty ``takes`` list is a FAIL --
      every take tried belongs on the receipt;
    * a take carrying neither measured shares nor a recorded reason is a
      FAIL;
    * ``target`` and ``gap`` must be dicts of finite numbers when present;
      ``rounds_used`` a positive integer; ``selected_take`` must name a
      take that is on the receipt.

    Returns {"verdict": PASS|FAIL, "reasons": [...]}. Never raises on a
    dishonest receipt -- that is a FAIL verdict, not an error. Raises
    ReceiptEvidenceError only for a malformed (non-dict) receipt.
    """
    if not isinstance(receipt, dict):
        raise ReceiptEvidenceError(
            "BAD_RECEIPT", "receipt must be a dict, got %r"
            % (type(receipt).__name__,))
    reasons = []
    measured_seen = _scan_share_fields(receipt, "receipt", reasons)

    takes = receipt.get("takes")
    if takes is None:
        if measured_seen:
            reasons.append(
                "measured sung %% but no takes: every take tried belongs "
                "on the receipt (takes must be a non-empty list)")
    elif not isinstance(takes, list) or not takes:
        reasons.append("takes must be a non-empty list of take records, "
                       "got %r" % (takes,))
    else:
        take_ids = []
        for index, take in enumerate(takes):
            label = "takes[%d]" % index
            if not isinstance(take, dict):
                reasons.append("%s must be a dict take record, got %r"
                               % (label, type(take).__name__))
                continue
            for key in ("take", "id"):
                if take.get(key) is not None:
                    take_ids.append(take.get(key))
                    break
            if _scan_share_fields(take, label, reasons):
                continue
            has_reason = bool(take.get("reasons")) \
                or bool(take.get("rejected")) or bool(take.get("unmeasured"))
            if not has_reason:
                reasons.append(
                    "%s carries neither measured shares nor a recorded "
                    "reason; a take that could not be measured must say so"
                    % label)
        selected = receipt.get("selected_take")
        if selected is not None:
            if isinstance(selected, dict):
                selected = selected.get("take", selected.get("id"))
            if selected is not None and take_ids \
                    and selected not in take_ids:
                reasons.append(
                    "selected_take=%r is not one of the takes on the "
                    "receipt (%r)" % (selected, take_ids))

    for key in ("target",):
        value = receipt.get(key)
        if value is None:
            continue
        if not _valid_number_map(value) \
                or any(float(v) < 0 for v in value.values()):
            reasons.append("%s must be a non-empty dict of finite numbers "
                           ">= 0 when present, got %r" % (key, value))
    gap = receipt.get("gap")
    if gap is not None:
        if not isinstance(gap, dict):
            reasons.append("gap must be a dict of percentage points when "
                           "present, got %r" % (gap,))
        elif receipt.get("target") is not None and not gap:
            reasons.append("the receipt carries a target but no gap: the "
                           "gap is the points off that target")
        else:
            for axis, points in gap.items():
                # None = that axis was never measured; never 0 by default.
                if points is None:
                    continue
                if isinstance(points, bool) or not isinstance(points, (int, float)) \
                        or not isfinite(points):
                    reasons.append(
                        "gap[%r] must be a finite number of points or None "
                        "(unmeasured), got %r" % (axis, points))
    rounds = receipt.get("rounds_used")
    if rounds is not None and (isinstance(rounds, bool)
                               or not isinstance(rounds, int)
                               or rounds < 1):
        reasons.append("rounds_used must be a positive integer, got %r"
                       % (rounds,))
    planned = receipt.get("planned")
    if planned is not None and (not isinstance(planned, dict) or not planned):
        reasons.append("planned must be a non-empty dict of planned_* "
                       "fields when present, got %r" % (planned,))
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
    "DETECTOR_KEYS", "DELIVERIES", "FIELD_ALIASES", "LABELLED",
    "LABEL_HEADINGS", "MEASURED",
    "PLANNED", "RECEIPT_SOURCE_LABEL", "ReceiptEvidenceError",
    "RUNTIME_KEYS", "SCHEMA_VERSION", "SHARE_SUM_TOLERANCE", "SOURCE",
    "SUNG_PCT_FIELDS", "TOOL_NAME", "TOOL_VERSION", "check_receipt",
    "gap_vs_target", "labelled_share", "measured_share", "planned_share",
    "receipt_block", "require_measured",
]

# ``RECEIPT_SOURCE_LABEL`` is the deprecated alias kept so the first tests
# referencing it by typo'd name still import; do not use in new code.
RECEIPT_SOURCE_LABEL = LABELLED
