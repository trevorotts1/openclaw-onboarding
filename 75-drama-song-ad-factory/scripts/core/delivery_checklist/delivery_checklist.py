#!/usr/bin/env python3
"""delivery_checklist.py: the 11-question delivery QC (Trevor order 2026-10-08).

Simple on purpose. This module is the ONE independent checker step that
rides on the existing Final edit QC gate (17.5, qc_gate check "final_edit").
It does NOT build a new framework: it reuses the sibling checker contract
(lipsync_coverage / sung_vocal_guard) -- evaluate() -> to_qc_record() emits
a qc-schema 1.0.0 record with check="final_edit" that the run's Final edit
QC passes in its records array to core/qc_gate.py evaluate (G7 wiring:
"--required final_edit,delivery_checklist").

The checklist lives verbatim at
references/QC-CHECKLIST-BEFORE-DELIVERY.md; its 11 questions are answered
from MEASURED evidence in the delivery receipt -- each answer carries a
yes/no plus the measurement that proves it.

H11 (Part H, order 1225) adds Q8 LIP_SYNC (H2 numbers), Q9 FIRST_SUNG
(H6 first-sung % of runtime), Q10 PICTURES_MATCH (H5 shot/time/line/match)
and Q11 GOALS_BAND (every numeric goal judged by Trevor's band: within 5
accept, over 5 to 10 accept WITH a flag shown, over 10 REDO). Q2 now uses
the same band. Same gate, same record, same laws -- no new framework.

The three G7 laws (order, verbatim):
  * a "no" re-does only the failing part (the repair_scope names exactly
    the failing answers) and never cancels the run -- gate stays FAIL,
    never BLOCKED, for a missing answer;
  * "yes" without a measurement counts as "no" (CHECKLIST_NO_MEASUREMENT);
  * an answer missing entirely fails the gate (CHECKLIST_ANSWER_MISSING).

What evaluate() does per question, measured from the receipt only:

  1 SUNG      -- receipt singing detector numbers on the vocal stem
                 (sung_pct / spoken_pct present, sung style required).
                 Sung share must be > 0 for a sung ad. Detector field
                 (receipt.detector) must name core/singing_detector (G3,
                 any separator form); labels/section names and any
                 share_source other than "measured" are never evidence.
  2 ON TARGET -- every share and the length within CHECKLIST_TOLERANCE_PCT
                 (5.0) points of its target in the receipt.
  3 WORDS     -- receipt word coverage: words_present / words_total == 100%
                 and invented_words empty (the diff the checklist asks for).
  4 FACES     -- every shot in receipt.shots carries a frame reference and
                 an emotion match verdict (no smiling under a pain line).
  5 VOICE+MUSIC -- receipt music_unbroken true WITH the measurement
                 (music_gaps_s == 0.0), no reverb tail (tail verdict), and
                 every line's delivery matches its mode (sung lines sung).
  6 MODELS    -- every asset's model is in the locked set (exact strings
                 from the checklist, compared case-insensitively), AND
                 every delivered clip used the video model the card locked
                 (F16: model_lock.check_video_model_delivery, fail-closed).
  7 HONEST    -- every receipt number names its source (non-empty
                 "source"/"source_ref" next to each measured value);
                 anything unmeasured must be written "UNMEASURED" and an
                 UNMEASURED value can never stand as a pass.

Fail-closed: a receipt that is not an object, a question with no answer, or
an answer without its measurement is a FAIL naming exactly that part.
stdlib only, no network, no provider call, no spend, no absolute operator
path; evaluate() opens no file at all (the receipt is handed in as data).

FU-U14 (Trevor: "make the mp3 part of the deliverable"): check_song_mp3()
adds the song-mp3 item to the delivery battery as PASS/FAIL rows: the final
song file sits in the ad folder beside the captioned and clean-master mp4s,
duration-matches the ad audio (0.1 s) and cross-correlates >= 0.95 with it.
Missing or mismatched = FAIL, fail closed. mp3 is probed through ffmpeg
when present; wav is measured with the stdlib wave module.

Run: python3 core/delivery_checklist/test_delivery_checklist.py
Run: python3 core/delivery_checklist/test_song_mp3_u14.py
"""
from __future__ import annotations

import math
import re
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

# F16 delivery gate: the video-model lock lives in the sibling kie_dispatch
# package. Same core/ tree, the same sys.path pattern kie_dispatch.py uses;
# no file is opened and no provider is called -- the receipt stays data.
_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
import kie_dispatch.model_lock as model_lock  # noqa: E402  (F16)

TOOL_NAME = "delivery_checklist"
TOOL_VERSION = "1.4.0"
SCHEMA_VERSION = "1.0.0"          # final_assembler receipt schema
QC_SCHEMA_VERSION = "1.0.0"       # core/qc_gate.py
CHECK = "delivery_checklist"      # new required check ON gate 4 (17.5 Final)
CHECK_ID = "delivery-checklist"   # record id inside the shared gate

CHECKLIST_REF = "references/QC-CHECKLIST-BEFORE-DELIVERY.md"
# Q1-Q7 = G7; Q8-Q11 = Part H unit H11 (Trevor order 1225): lip-sync
# measured (H2), first-sung % (H6), pictures match words (H5), and every
# numeric goal judged by Trevor's band.
QUESTIONS = ("SUNG", "ON_TARGET", "WORDS", "FACES", "VOICE_MUSIC",
             "MODELS", "HONEST_RECEIPT",
             "LIP_SYNC", "FIRST_SUNG", "PICTURES_MATCH", "GOALS_BAND")

#: Trevor's TARGET RULE (2026-10-08 12:30, verbatim): "We always want to try
#: to be within 5% of the goal. Once you get past 5%, 5% to 7% gets a flag.
#: Once you get past 10%, it's got to be redone."  Within 5 points = ACCEPT;
#: over 5 up to 10 = ACCEPT_WITH_FLAG (the flag is shown in the receipt);
#: over 10 = REDO (never keep the closest).
CHECKLIST_TOLERANCE_PCT = 5.0       # Q2 / Q11 clean-accept limit
CHECKLIST_REDO_PCT = 10.0           # Q2 / Q11 redo line
BAND_ACCEPT, BAND_FLAG, BAND_REDO = "ACCEPT", "ACCEPT_WITH_FLAG", "REDO"

#: Q8 lip-sync gate: the sync_check verdicts (LSL002) under Trevor's two-try
#: keep-best rule (2026-10-08). The numbers live in lip_sync/lip_gate/sync_check.py.
LIPSYNC_OK_VERDICTS = ("PASS", "ACCEPT_WITH_FLAG")
LIPSYNC_HELD_VERDICTS = ("UNDETERMINED", "UNMEASURABLE")   # a person looked at the strip
LIPSYNC_ALL_VERDICTS = LIPSYNC_OK_VERDICTS + LIPSYNC_HELD_VERDICTS + ("FAIL",)
LIPSYNC_KEPT = "KEPT_BEST_OF_2"
LIPSYNC_MAX_JOBS = 2
#: Q9: first real singing (vocal stem) target, share of runtime (H6).
FIRST_SUNG_TARGET_PCT = 15.0

#: FU-U13 product-connection row: 10-15% of runtime connecting story to
#: product. A TARGET, never a hard cap: outside the band is FLAG with the
#: measured seconds and percent -- this row never joins repair_scope and
#: never blocks the gate by itself. The planner computes these (Q12 in the
#: runbook); this checker MEASURES them from the delivered shots/lyrics.
PRODUCT_TARGET_LO_PCT = 10.0
PRODUCT_TARGET_HI_PCT = 15.0
PRODUCT_ROW = "PRODUCT_CONNECTION"

#: FU-U16 villain doctrine row: "People don't care about the hero until they
#: meet the villain." - Trevor Otts. Reports villain shots, villain screen
#: seconds, pain seconds and rise seconds. Pain 20-35% of runtime is a
#: TARGET: outside is FLAG with the measured seconds, never a block. Only
#: the planner fails closed (no villain named / villain has no shot); this
#: checker row is evidence and never joins repair_scope.
VILLAIN_PAIN_LO_PCT = 20.0
VILLAIN_PAIN_HI_PCT = 35.0
VILLAIN_ROW = "VILLAIN_DOCTRINE"
_VD_SHOT_S = 3.0

def _vd_tagged(obj, tag):
    if not isinstance(obj, dict):
        return False
    if obj.get(tag) is True:
        return True
    if tag == "villain":
        vis = obj.get("villain_visibility")
        if isinstance(vis, str) and vis.strip().lower() not in ("", "none"):
            return True
    tags = obj.get("tags") or ()
    if isinstance(tags, str):
        tags = (tags,)
    return tag in tags

def _vd_seconds(obj):
    for k in ("seconds", "duration_s", "duration"):
        v = obj.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return float(v)
    return _VD_SHOT_S
#: Q10: no slow-motion above this speed-down factor (H5).
MAX_SLOWDOWN = 1.15

#: G5 amend (order 1150 part G): the amended receipt carries the block
#: core/singing_detector/receipt_evidence.measured_share() builds. The
#: checklist reads it: a stamp that is not "measured" (labels / planned) is
#: the failed-ad shape, and a block missing any field it promises is a
#: claim without its measurement (G7 law 2).
G5_MEASURED = "measured"
G5_BLOCK_KEYS = ("measured_share", "receipt_evidence")
G5_SHARES = ("sung", "spoken", "rap", "no_voice")
#: receipt_evidence SHARE_SUM_TOLERANCE (0.02 of the runtime), in points.
G5_SHARE_SUM_PTS = 2.0

#: Q8 amend: the operator's kept-take vocabulary (KEPT-TAKES.md rows). A
#: clip tagged KEPT_BEST or FLAGGED is kept though not fully clean: it must
#: still carry its measurement AND its reason, and the flag is shown.
LIPSYNC_TAGS = ("KEPT", "KEPT_BEST", "FLAGGED")
LIPSYNC_FLAG_TAGS = ("KEPT_BEST", "FLAGGED")

#: Question 1: a sung ad must show a measured sung share above zero.
SUNG_MIN_PCT = 1.0

#: Question 6: the locked models, verbatim from the checklist (compared
#: case-insensitively; aliases live in MODEL_ALIASES).
LOCKED_MODELS = {
    "video": "minimax h3 768p",
    "images": "gpt-image sunburst",
    "song": "suno v6",
    "lip_sync": "kling avatar",
}
MODEL_ALIASES = {
    "video": ("minimax", "minimax-h3", "h3 768p", "minimax h3"),
    "images": ("gpt-image", "sunburst", "gpt image"),
    "song": ("suno", "suno v6", "suno-v6"),
    "lip_sync": ("kling", "kling avatar", "kling-avatar"),
}

EXIT = {"ok": 0, "error": 1, "rejected": 5}

REASON_CODES = {
    "SUNG": "CHECKLIST_SUNG_NOT_MEASURED",
    "ON_TARGET": "CHECKLIST_OFF_TARGET",
    "WORDS": "CHECKLIST_WORDS_INCOMPLETE",
    "FACES": "CHECKLIST_FACE_MISMATCH",
    "VOICE_MUSIC": "CHECKLIST_VOICE_MUSIC_BROKEN",
    "MODELS": "CHECKLIST_WRONG_MODEL",
    "HONEST_RECEIPT": "CHECKLIST_NOT_HONEST",
    "LIP_SYNC": "CHECKLIST_LIPSYNC_FAILED",
    "FIRST_SUNG": "CHECKLIST_FIRST_SUNG_OFF",
    "PICTURES_MATCH": "CHECKLIST_PICTURE_MISMATCH",
    "GOALS_BAND": "CHECKLIST_GOAL_REDO",
    "ANSWER_MISSING": "CHECKLIST_ANSWER_MISSING",
    "NO_MEASUREMENT": "CHECKLIST_NO_MEASUREMENT",
}
# flat aliases used throughout the per-question checks below
CHECKLIST_SUNG_NOT_MEASURED = REASON_CODES["SUNG"]
CHECKLIST_OFF_TARGET = REASON_CODES["ON_TARGET"]
CHECKLIST_WORDS_INCOMPLETE = REASON_CODES["WORDS"]
CHECKLIST_FACE_MISMATCH = REASON_CODES["FACES"]
CHECKLIST_VOICE_MUSIC_BROKEN = REASON_CODES["VOICE_MUSIC"]
CHECKLIST_WRONG_MODEL = REASON_CODES["MODELS"]
CHECKLIST_NOT_HONEST = REASON_CODES["HONEST_RECEIPT"]
CHECKLIST_LIPSYNC_FAILED = REASON_CODES["LIP_SYNC"]
CHECKLIST_FIRST_SUNG_OFF = REASON_CODES["FIRST_SUNG"]
CHECKLIST_PICTURE_MISMATCH = REASON_CODES["PICTURES_MATCH"]
CHECKLIST_GOAL_REDO = REASON_CODES["GOALS_BAND"]
CHECKLIST_ANSWER_MISSING = REASON_CODES["ANSWER_MISSING"]
CHECKLIST_NO_MEASUREMENT = REASON_CODES["NO_MEASUREMENT"]


class ChecklistError(Exception):
    """Structural problem (receipt not an object). Fail closed, never pass."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ helpers
def _num(value):
    """True float value or None (bools/strings/NaN are not numbers here)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if v == v else None            # NaN -> None


def _truthy_measured(value):
    """A measured boolean: True/False only. Anything else is not evidence."""
    return value is True or value is False


def _answer(receipt, q):
    """The answer dict for question q, or None when the question is absent.

    Accepts answers keyed by the question name directly or nested under
    receipt["answers"]. An empty dict counts as MISSING (no measurement).
    """
    ans = receipt.get(q)
    if ans is None and isinstance(receipt.get("answers"), dict):
        ans = receipt["answers"].get(q)
    if not isinstance(ans, dict):
        return None
    return ans or None


def _measured_num(ans, keys, what, codes, q):
    """Pull the first present numeric measurement, else record a miss."""
    for k in keys:
        v = _num(ans.get(k))
        if v is not None:
            return v, k
    codes.append("%s:%s" % (CHECKLIST_NO_MEASUREMENT,
                            "%s missing %s" % (q, what)))
    return None, None


def _measured_bool(ans, keys, what, codes, q):
    """Pull the first present true/false measurement, else record a miss."""
    for k in keys:
        if _truthy_measured(ans.get(k)):
            return ans[k], k
    codes.append("%s:%s" % (CHECKLIST_NO_MEASUREMENT,
                            "%s missing %s" % (q, what)))
    return None, None


def _clamp_pct(v):
    """Percent clamp for share comparisons; out-of-range shares are OFF_TARGET."""
    if v is None:
        return None
    return min(max(v, 0.0), 100.0)


def band(delta):
    """Trevor's band for a distance from goal (points or relative percent)."""
    if delta <= CHECKLIST_TOLERANCE_PCT + 1e-6:
        return BAND_ACCEPT
    if delta <= CHECKLIST_REDO_PCT + 1e-6:
        return BAND_FLAG
    return BAND_REDO


def _flag_text(name, got, want, delta):
    return "FLAG %s %.1f vs goal %.1f (%.1f off, over %.0f)" % (
        name, got, want, delta, CHECKLIST_TOLERANCE_PCT)


def _source_named(ans, codes, q):
    """A new-question answer must name its instrument (honest receipt)."""
    src = ans.get("source")
    if isinstance(src, str) and src.strip():
        return src.strip()
    codes.append("%s:%s answer names no source" % (CHECKLIST_NO_MEASUREMENT, q))
    return None

def _is_singing_detector(name):
    """G3: the sung share must come from core/singing_detector.

    Normalizes separators, so "singing-detector(vocal-stem)",
    "singing_detector" and "singing detector v2" all count; "section
    labels", "verse/chorus time" and bare "manual" do not.
    """
    if not isinstance(name, str):
        return False
    return "singingdetector" in "".join(ch for ch in name.lower()
                                        if ch.isalnum())


# ------------------------------------------- G5 amended receipt evidence ---
# Order 1150 part G: the receipt carries the block
# core/singing_detector/receipt_evidence builds (measured four-way shares +
# detector + confidence + target + gap + every take tried). The checklist
# consumes that block as the authority for Q1; label-shaped shares are
# never the result.
_G5_RE = None


def _receipt_evidence():
    """core/singing_detector/receipt_evidence.py, loaded by path (G5 reader).

    By path on purpose: receipt_evidence is stdlib-only, while its package
    __init__ pulls in the numpy detector. The delivery checklist must not
    grow a numpy/ffmpeg dependency to read a receipt. None when absent
    (the G7 measured path then decides alone; never a silent pass).
    """
    global _G5_RE
    if _G5_RE is None:
        import importlib.util
        path = _CORE / "singing_detector" / "receipt_evidence.py"
        try:
            spec = importlib.util.spec_from_file_location(
                "_g5_receipt_evidence", str(path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _G5_RE = mod
        except (OSError, ImportError, AttributeError, SyntaxError,
                ValueError):
            _G5_RE = False                      # absent: report, never pass
    return _G5_RE or None


def _g5_evidence(ans, receipt):
    """The amended G5 block, wherever the receipt carries it.

    ``measured_share()`` / ``receipt_block()`` output rides the SUNG answer
    or the receipt itself, under "receipt_evidence" or "measured_share".
    Returns the block dict, or None when the receipt carries none (the G7
    measured path alone then decides).
    """
    for source in (ans, receipt):
        if not isinstance(source, dict):
            continue
        for key in G5_BLOCK_KEYS:
            value = source.get(key)
            if isinstance(value, dict) and value:
                inner = value.get("measured_share")
                return inner if isinstance(inner, dict) else value
    return None


def _g5_problem(block):
    """Every field the amended G5 receipt promises, or the reason it fails.

    Empty string = the block is complete and measured. The reader is
    receipt_evidence.check_receipt whenever the block carries a take ledger
    (the full amended receipt), so label-shaped shares inside takes and a
    missing take ledger fail exactly as G5 runs them; the bare
    measured_share() block is read field by field here.
    """
    RE = _receipt_evidence()
    if RE is None:
        return ("G5 reader missing: core/singing_detector/receipt_evidence.py "
                "not found")
    if "takes" in block:
        verdict = RE.check_receipt(block)
        if verdict["verdict"] == "FAIL":
            return "; ".join(verdict["reasons"][:3])
    source = block.get("source", block.get("share_source"))
    if not isinstance(source, str) or source.strip().lower() != G5_MEASURED:
        return ("receipt evidence source=%r is not measured: label-shaped "
                "shares are never the result" % (source,))
    if not _is_singing_detector(block.get("detector")):
        return ("receipt evidence detector %r is not the singing detector"
                % (block.get("detector"),))
    conf = _num(block.get("confidence"))
    if conf is None or not 0.0 <= conf <= 1.0:
        return "receipt evidence carries no confidence (0..1)"
    runtime = _num(block.get("runtime_s"))
    if runtime is None or runtime <= 0:
        return "receipt evidence carries no runtime_s"
    missing, total = [], 0.0
    for name in G5_SHARES:
        pct = _num(block.get("%s_pct" % name))
        secs = _num(block.get("%s_seconds" % name))
        if pct is None:
            missing.append("%s_pct" % name)
        else:
            total += pct
        if secs is None:
            missing.append("%s_seconds" % name)
    if missing:
        return "receipt evidence missing %s" % ", ".join(missing)
    if abs(total - 100.0) > G5_SHARE_SUM_PTS:
        return ("sung + spoken + rap + no_voice = %.1f%% of the runtime "
                "(need 100)" % total)
    return ""


#: Source strings that name label/plan time: never a measured sung share.
LABEL_SHAPED = ("label", "planned", "plan", "timing_map", "timing map",
                "section", "verse", "chorus")


def _label_shaped(source):
    """True when a source string names label/plan time, not a measurement."""
    if not isinstance(source, str):
        return False
    flat = source.strip().lower()
    return any(word in flat for word in LABEL_SHAPED)


#: The G3-WIRE provenance suffix the qc_gate requires on a PASS sung claim
#: (sung_vocal_guard.record_for_gate prints the same shape).
def provenance_suffix(detector, version, sung_pct):
    return ("detector=%s v%s share_source=measured sung_share=%.1f%%"
            % (detector, version or "?", sung_pct))


# ------------------------------------------------------------------ Q1 SUNG
def _q1_sung(receipt, ans, codes, details):
    """Measured sung/spoken percents from the vocal-stem detector.

    Order 1150 part G: when the receipt carries the amended G5 block
    (core/singing_detector/receipt_evidence.measured_share /
    receipt_block), that block IS the authority -- it must be complete and
    measured, its four-way shares are the numbers this question answers
    with, and its detector provenance is stamped on the answer. A block
    missing any field, carrying a label-shaped source, or failing
    receipt_evidence.check_receipt FAILS here (G7 law 2: a claimed share
    without its measurement is a "no").
    """
    style = ans.get("style") or ans.get("delivery_style") or receipt.get("style")
    block = _g5_evidence(ans, receipt)
    if block is not None:
        problem = _g5_problem(block)
        if problem:
            codes.append("%s:SUNG amended receipt evidence: %s"
                         % (CHECKLIST_NO_MEASUREMENT, problem))
            return False
        sung = _clamp_pct(_num(block.get("sung_pct")))
        spoken = _clamp_pct(_num(block.get("spoken_pct")))
        detector = block.get("detector")
        details["receipt_evidence"] = "measured four-way shares (%s)" \
            % detector.strip()
        details["provenance"] = provenance_suffix(
            detector.strip(), block.get("detector_version"), sung or 0.0)
    else:
        sung = ans.get("sung_pct", ans.get("sung_share_pct"))
        spoken = ans.get("spoken_pct", ans.get("spoken_share_pct"))
        sung = _clamp_pct(_num(sung))
        spoken = _clamp_pct(_num(spoken))
        if sung is None or spoken is None:
            codes.append("%s:SUNG missing measured sung_pct/spoken_pct"
                         % CHECKLIST_NO_MEASUREMENT)
            return False
        detector = ans.get("detector") or receipt.get("detector") or ""
        if not isinstance(detector, str) or not detector.strip():
            codes.append("%s:SUNG detector (vocal-stem) not named"
                         % CHECKLIST_NO_MEASUREMENT)
            return False
        if not _is_singing_detector(detector):
            # G3: a named-but-wrong instrument (labels, ears, "manual") is
            # the fake-number path; only core/singing_detector measures.
            codes.append("%s:SUNG detector %r is not the singing detector"
                         % (CHECKLIST_NO_MEASUREMENT, detector.strip()))
            return False
        share_source = ans.get("share_source") or receipt.get("share_source")
        if isinstance(share_source, str) and share_source.strip() \
                and share_source.strip().lower() != "measured":
            codes.append("%s:SUNG share_source=%s (need measured)"
                         % (CHECKLIST_NO_MEASUREMENT, share_source.strip()))
            return False
        label_src = ans.get("source") or receipt.get("source")
        if _label_shaped(label_src):
            # G5 amend: a sung % whose source names labels/plan time is the
            # failed-ad shape, whatever the detector field claims.
            codes.append("%s:SUNG source=%r is label-shaped; a sung %% must "
                         "be measured" % (CHECKLIST_NO_MEASUREMENT,
                                          label_src.strip()))
            return False
        detector = detector.strip()
    is_sung_style = isinstance(style, str) and \
        style.strip().lower() in ("sung", "all_suno", "all-suno", "suno")
    if is_sung_style and sung < SUNG_MIN_PCT:
        codes.append("%s:SUNG sung %.1f%% on a %s ad (need > %.0f%%)"
                     % (CHECKLIST_SUNG_NOT_MEASURED, sung, style,
                        SUNG_MIN_PCT))
        return False
    if sung + spoken > 100.0 + 1e-6:
        codes.append("%s:SUNG sung %.1f%% + spoken %.1f%% > 100%%"
                     % (CHECKLIST_SUNG_NOT_MEASURED, sung, spoken))
        return False
    details["sung_pct"] = sung
    details["spoken_pct"] = spoken
    details["detector"] = detector
    if "provenance" not in details:
        details["provenance"] = provenance_suffix(detector, None, sung)
    return True


# ------------------------------------------------------------- Q2 ON TARGET
def _q2_on_target(receipt, ans, codes, details):
    """Every measured share and the length within 5 points of its target."""
    ok = True
    flags = []
    shares = ans.get("shares")
    measured = {}
    if isinstance(shares, dict):
        for name, pair in shares.items():
            if not isinstance(pair, dict):
                continue
            got = _num(pair.get("measured_pct", pair.get("pct")))
            want = _num(pair.get("target_pct", pair.get("target")))
            if got is None or want is None:
                codes.append("%s:ON_TARGET %s missing measured_pct/target_pct"
                             % (CHECKLIST_NO_MEASUREMENT, name))
                ok = False
                continue
            delta = abs(got - want)
            measured[name] = {"measured_pct": got, "target_pct": want,
                              "delta_pts": round(delta, 1)}
            if band(delta) == BAND_REDO:
                codes.append("%s:ON_TARGET %s %.1f%% vs target %.1f%% "
                             "(> %.0f pts, redo)" % (
                                 CHECKLIST_OFF_TARGET, name, got, want,
                                 CHECKLIST_REDO_PCT))
                ok = False
            elif band(delta) == BAND_FLAG:
                flags.append(_flag_text(name, got, want, delta))
    length_s = _num(ans.get("length_s", ans.get("measured_length_s")))
    target_s = _num(ans.get("target_length_s"))
    if length_s is not None and target_s is not None and target_s > 0:
        # length shares the band, expressed relative to the target length
        delta_pct = abs(length_s - target_s) / target_s * 100.0
        measured["length"] = {"measured_s": length_s, "target_s": target_s,
                              "delta_pct": round(delta_pct, 1)}
        if band(delta_pct) == BAND_REDO:
            codes.append("%s:ON_TARGET length %.1fs vs target %.1fs "
                         "(%.1f%% off, redo over %.0f%%)"
                         % (CHECKLIST_OFF_TARGET, length_s, target_s,
                            delta_pct, CHECKLIST_REDO_PCT))
            ok = False
        elif band(delta_pct) == BAND_FLAG:
            flags.append(_flag_text("length", length_s, target_s, delta_pct))
    if not measured:
        codes.append("%s:ON_TARGET no measured shares or length in the "
                     "receipt" % CHECKLIST_NO_MEASUREMENT)
        return False
    details["measured"] = measured
    details["tolerance_pts"] = CHECKLIST_TOLERANCE_PCT
    if flags:
        details["on_target_flags"] = flags
    return ok


# ----------------------------------------------------------------- Q3 WORDS
def _q3_words(receipt, ans, codes, details):
    """Every script word present, in order, nothing invented."""
    present = _num(ans.get("words_present"))
    total = _num(ans.get("words_total"))
    if present is None or total is None or total <= 0:
        codes.append("%s:WORDS missing words_present/words_total"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    invented = ans.get("invented_words")
    if not isinstance(invented, list):
        codes.append("%s:WORDS missing invented_words diff list"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    missing = ans.get("missing_words")
    if not isinstance(missing, list):
        codes.append("%s:WORDS missing missing_words diff list"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    ok = True
    if present != total:
        codes.append("%s:WORDS %d/%d words present"
                     % (CHECKLIST_WORDS_INCOMPLETE, present, total))
        ok = False
    if missing:
        codes.append("%s:WORDS missing: %s"
                     % (CHECKLIST_WORDS_INCOMPLETE,
                        ", ".join(str(w) for w in missing[:10])))
        ok = False
    if invented:
        codes.append("%s:WORDS invented: %s"
                     % (CHECKLIST_WORDS_INCOMPLETE,
                        ", ".join(str(w) for w in invented[:10])))
        ok = False
    details["words_present"] = present
    details["words_total"] = total
    details["missing_count"] = len(missing)
    details["invented_count"] = len(invented)
    return ok


# ----------------------------------------------------------------- Q4 FACES
def _q4_faces(receipt, ans, codes, details):
    """Every shot: one sampled frame, emotion matches its line."""
    shots = ans.get("shots")
    if not isinstance(shots, list) or not shots:
        codes.append("%s:FACES no per-shot frame/emotion list in the receipt"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    ok = True
    bad_frames, bad_emotion = [], []
    for i, s in enumerate(shots):
        shot_id = s.get("shot", s.get("shot_id", "shot-%d" % (i + 1))) \
            if isinstance(s, dict) else "shot-%d" % (i + 1)
        if not isinstance(s, dict):
            codes.append("%s:FACES %s not a shot record"
                         % (CHECKLIST_NO_MEASUREMENT, shot_id))
            ok = False
            continue
        frame = s.get("frame", s.get("frame_ref"))
        if not isinstance(frame, str) or not frame.strip():
            bad_frames.append(str(shot_id))
            ok = False
            continue
        if not _truthy_measured(s.get("emotion_match")) \
                and s.get("emotion_match") is not False:
            # absent or not a measured boolean (a "yes" string is not
            # evidence): counts as no measurement, never as a pass
            codes.append("%s:FACES %s missing emotion_match verdict"
                         % (CHECKLIST_NO_MEASUREMENT, shot_id))
            ok = False
            continue
        if s.get("emotion_match") is False:
            bad_emotion.append("%s (%s)" % (shot_id, frame))
            ok = False
    if bad_frames:
        codes.append("%s:FACES no sampled frame for %s"
                     % (CHECKLIST_NO_MEASUREMENT, ", ".join(bad_frames[:10])))
    if bad_emotion:
        codes.append("%s:FACES emotion mismatch (frame+line): %s"
                     % (CHECKLIST_FACE_MISMATCH,
                        "; ".join(bad_emotion[:10])))
    details["shots_checked"] = len(shots)
    details["face_mismatch_shots"] = [b.split(" (")[0] for b in bad_emotion]
    return ok


# --------------------------------------------------------- Q5 VOICE + MUSIC
def _q5_voice_music(receipt, ans, codes, details):
    """Music unbroken, no reverb tail, delivery modes match the lines."""
    ok = True
    unbroken = _truthy_measured(ans.get("music_unbroken"))
    gaps = _num(ans.get("music_gaps_s"))
    if unbroken is None or gaps is None:
        codes.append("%s:VOICE_MUSIC missing music_unbroken + music_gaps_s"
                     % CHECKLIST_NO_MEASUREMENT)
        ok = False
    elif not unbroken or gaps > 0.0:
        codes.append("%s:VOICE_MUSIC music broken (%.2f s of gaps)"
                     % (CHECKLIST_VOICE_MUSIC_BROKEN, gaps))
        ok = False
    tail = ans.get("reverb_tail")
    tail_s = _num(ans.get("reverb_tail_s"))
    if tail is not None or tail_s is not None:
        present = (tail is False) if _truthy_measured(tail) \
            else (tail_s == 0.0)
        if not present:
            codes.append("%s:VOICE_MUSIC reverb/echo tail measured %.3fs"
                         % (CHECKLIST_VOICE_MUSIC_BROKEN,
                            tail_s if tail_s is not None else 0.0))
            ok = False
        details["reverb_tail_s"] = tail_s
    lines = ans.get("lines")
    if not isinstance(lines, list) or not lines:
        codes.append("%s:VOICE_MUSIC no per-line delivery/mode list"
                     % CHECKLIST_NO_MEASUREMENT)
        ok = False
    else:
        mismatched = []
        for i, ln in enumerate(lines):
            if not isinstance(ln, dict):
                continue
            line_delivery = ln.get("delivery", "")
            line_mode = ln.get("mode", "")
            if not isinstance(line_delivery, str) \
                    or not isinstance(line_mode, str) or not line_mode:
                codes.append("%s:VOICE_MUSIC line %d missing delivery/mode"
                             % (CHECKLIST_NO_MEASUREMENT, i + 1))
                ok = False
                continue
            if line_delivery.strip().lower() != line_mode.strip().lower():
                mismatched.append("line %d: %s vs %s"
                                  % (i + 1, line_delivery, line_mode))
        if mismatched:
            codes.append("%s:VOICE_MUSIC spoken lines speech / sung lines "
                         "sung violated: %s"
                         % (CHECKLIST_VOICE_MUSIC_BROKEN,
                            "; ".join(mismatched[:10])))
            ok = False
        details["lines_checked"] = len(lines)
    details["music_gaps_s"] = gaps
    return ok


# ----------------------------------------------------------------- Q6 MODELS
#: keys a delivery receipt / MODELS answer uses for clip provenance and for
#: the card-locked video model (F16). They are NOT per-asset model names.
_CLIP_KEYS = ("clips", "video_clips")
_LOCK_KEYS = ("locked_video_model", "video_model_locked", "locked")


def _clip_list(receipt, ans):
    """The receipt's per-clip video provenance, or None when it has none.

    Clip rows may ride the receipt itself or the MODELS answer. None means
    this receipt records no clip list, so the video-model gate has nothing
    to check -- the per-asset `used` check below still governs Q6.
    """
    for source in (receipt, ans):
        if not isinstance(source, dict):
            continue
        for key in _CLIP_KEYS:
            value = source.get(key)
            if isinstance(value, list):
                return value
    return None


def _locked_video_model(receipt, ans):
    """The card-locked video model the receipt records, else None (unproven)."""
    for source in (receipt, ans):
        if not isinstance(source, dict):
            continue
        for key in _LOCK_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _q6_video_gate(receipt, ans, codes, details):
    """F16: every delivered clip used the video model the card locked.

    This is the wiring of model_lock.check_video_model_delivery into the
    delivery path. A mismatch fails Q6, and with it the delivery gate. A
    receipt that lists clips but records no lock fails too (G7: a claim
    with no measurement is a "no") -- it is never silently judged against
    a default the run never proved. No clip list -> nothing to check here.
    """
    clips = _clip_list(receipt, ans)
    if clips is None:
        return True
    locked = _locked_video_model(receipt, ans)
    bad = model_lock.check_video_model_delivery({"clips": clips}, locked)
    ok = True
    if locked is None:
        codes.append("%s:MODELS the receipt lists clips but records no "
                     "locked video model" % CHECKLIST_NO_MEASUREMENT)
        ok = False
    if bad:
        codes.append("%s:MODELS %s"
                     % (CHECKLIST_WRONG_MODEL, "; ".join(bad[:10])))
        ok = False
    details["video_model"] = {"locked": locked or "",
                              "clips": len(clips),
                              "mismatches": len(bad),
                              "lock_recorded": locked is not None}
    return ok


def _q6_models(receipt, ans, codes, details):
    """Only the locked models were used -- clip by clip (F16), asset by asset."""
    ok = _q6_video_gate(receipt, ans, codes, details)
    used = ans.get("used") if isinstance(ans.get("used"), dict) else \
        {k: v for k, v in ans.items() if k not in _CLIP_KEYS + _LOCK_KEYS
         and k != "used"}
    if not isinstance(used, dict) or not used:
        codes.append("%s:MODELS no per-asset model list in the receipt"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    wrong = []
    for kind, value in sorted(used.items()):
        if not isinstance(value, str) or not value.strip():
            codes.append("%s:MODELS %s has no named model"
                         % (CHECKLIST_NO_MEASUREMENT, kind))
            ok = False
            continue
        v = value.strip().lower()
        locked = LOCKED_MODELS.get(kind)
        aliases = MODEL_ALIASES.get(kind, ())
        if locked is None:
            continue                       # unknown kind: not a locked slot
        if locked not in v and not any(a in v for a in aliases):
            wrong.append("%s: %s (locked: %s)" % (kind, value.strip(), locked))
            ok = False
    if wrong:
        codes.append("%s:MODELS %s"
                     % (CHECKLIST_WRONG_MODEL, "; ".join(wrong[:10])))
    details["models"] = {k: (v.strip() if isinstance(v, str) else "")
                         for k, v in sorted(used.items())}
    return ok


# ------------------------------------------------------------ Q7 HONEST
def _field_source(ans, key):
    """The source ref for one measured field, or None.

    Accepts source_<field>, <field>_source, a "sources" dict entry, or a
    receipt-wide "source" (the instrument named once for the whole answer).
    """
    src = ans.get("source_" + key) or ans.get(key + "_source")
    if isinstance(src, str) and src.strip():
        return src.strip()
    sources = ans.get("sources")
    if isinstance(sources, dict):
        src = sources.get(key)
        if isinstance(src, str) and src.strip():
            return src.strip()
    wide = ans.get("source")
    if isinstance(wide, str) and wide.strip():
        return wide.strip()
    return None


def _q7_honest(receipt, ans, codes, details):
    """Every measured number names its source. Anything unmeasured must be
    written "UNMEASURED" (honest, not a pass) -- a value that is neither a
    measurement nor UNMEASURED is dishonest by construction."""
    ok = True
    unnamed, bad_values = [], []
    for key, value in sorted(ans.items()):
        if key.startswith("source") or key.endswith("_source") \
                or key in ("source", "sources", "note", "style",
                           "delivery_style"):
            continue
        is_number = _num(value) is not None
        is_bool = _truthy_measured(value)
        if not (is_number or is_bool):
            if not (isinstance(value, str)
                    and value.strip().upper() == "UNMEASURED"):
                bad_values.append("%s=%r" % (key, str(value)[:40]))
                ok = False
            continue
        if _field_source(ans, key) is None:
            unnamed.append(key)
            ok = False
    if unnamed:
        codes.append("%s:HONEST_RECEIPT measured fields without a source: %s"
                     % (CHECKLIST_NOT_HONEST, ", ".join(unnamed[:10])))
    if bad_values:
        codes.append("%s:HONEST_RECEIPT values neither measured nor "
                     "UNMEASURED: %s"
                     % (CHECKLIST_NOT_HONEST, ", ".join(bad_values[:10])))
    wide = ans.get("source")
    details["source"] = wide.strip() if isinstance(wide, str) and wide.strip() \
        else "per-field source refs"
    return ok


# --------------------------------------------------------- Q8 LIP-SYNC
def _clip_tag(c):
    """The kept-take tag on a clip row (operator KEPT-TAKES vocabulary),
    upper-cased, or None when the row carries no tag."""
    tag = c.get("tag", c.get("kept")) if isinstance(c, dict) else None
    if not isinstance(tag, str) or not tag.strip():
        return None
    return tag.strip().split()[0].upper()


def _clip_reason(c):
    """The flag/reason text a kept-but-not-clean row must carry."""
    for key in ("flag", "reason", "note", "flags", "defect"):
        v = c.get(key) if isinstance(c, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and any(isinstance(x, str) and x.strip()
                                       for x in v):
            return "; ".join(x for x in v if isinstance(x, str))
    return None


def _q8_lip_sync(receipt, ans, codes, details):
    """Every lip-sync clip carries its lip_gate verdict and numbers. PASS and
    ACCEPT_WITH_FLAG clips pass. UNDETERMINED / UNMEASURABLE (a sung line) pass
    only after a person looked at the mouth strip (person_verdict PASS). A FAIL
    take passes only as a flagged KEPT_BEST_OF_2 row (2 tries used at most, best
    take kept, mouth-strip path shown). No clip is ever rejected for a
    correlation number alone.

    Amendment (order 1150 part G): rows may carry the operator's kept-take
    tag (KEPT-TAKES.md: KEPT / KEPT_BEST / FLAGGED). A tagged row must be
    one of those three and still carry its measurement. KEPT_BEST and
    FLAGGED rows are kept though not fully clean: they must carry their
    flag/reason (missing -> FAIL) and the flag is shown in the receipt.
    Untagged rows keep the hard gate."""
    clips = ans.get("clips")
    src = _source_named(ans, codes, "LIP_SYNC")
    if not isinstance(clips, list) or not clips:
        codes.append("%s:LIP_SYNC no per-clip lip_gate verdict list"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    ok = src is not None
    flagged = []
    flags, tagged, tag_names = [], 0, set()
    for i, c in enumerate(clips):
        cid = c.get("clip", "clip-%d" % (i + 1)) if isinstance(c, dict) \
            else "clip-%d" % (i + 1)
        c = c if isinstance(c, dict) else {}
        tag = _clip_tag(c)
        if tag is not None:
            if tag not in LIPSYNC_TAGS:
                codes.append("%s:LIP_SYNC %s tag %r is not a kept-take tag "
                             "(%s)" % (CHECKLIST_NO_MEASUREMENT, cid, tag,
                                       "/".join(LIPSYNC_TAGS)))
                ok = False
                continue
            tagged += 1
            tag_names.add(tag)
            if tag in LIPSYNC_FLAG_TAGS and _clip_reason(c) is None:
                codes.append("%s:LIP_SYNC %s is tagged %s with no flag/reason "
                             "shown" % (CHECKLIST_NO_MEASUREMENT, cid, tag))
                ok = False
                continue
        verdict = c.get("lip_verdict")
        if verdict not in LIPSYNC_ALL_VERDICTS or _num(c.get("corr")) is None:
            codes.append("%s:LIP_SYNC %s missing lip_verdict/corr"
                         % (CHECKLIST_NO_MEASUREMENT, cid))
            ok = False
            continue
        bad = []
        kept = c.get("verdict") == LIPSYNC_KEPT
        if verdict != "PASS":
            flagged.append(cid)
        if verdict in LIPSYNC_HELD_VERDICTS and c.get("person_verdict") != "PASS" \
                and not (kept and c.get("flag") and c.get("mouth_strip")):
            bad.append("%s and no person_verdict PASS on the mouth strip" % verdict)
        if verdict == "FAIL" and not (kept and c.get("flag") and c.get("mouth_strip")):
            bad.append("FAIL and not a flagged %s row with a mouth strip" % LIPSYNC_KEPT)
        if (c.get("jobs_total") or c.get("jobs_used") or 0) > LIPSYNC_MAX_JOBS:
            bad.append("more than %d paid jobs on one segment" % LIPSYNC_MAX_JOBS)
        if bad:
            if tag in LIPSYNC_FLAG_TAGS:
                # kept though not clean (the operator's KEPT-TAKES decision):
                # shown as a flag on the receipt, not hidden.
                flags.append("%s %s: %s (%s)" % (cid, tag, ", ".join(bad),
                                                 _clip_reason(c)))
            else:
                codes.append("%s:LIP_SYNC %s %s" % (CHECKLIST_LIPSYNC_FAILED,
                                                      cid, ", ".join(bad)))
                ok = False
    details["lipsync_clips"] = len(clips)
    details["lipsync_flagged"] = flagged
    details["lipsync_tagged"] = tagged
    details["lipsync_tag_names"] = sorted(tag_names)
    if flags:
        details["lipsync_flags"] = flags
    return ok


# --------------------------------------------------------- Q9 FIRST SUNG
def _q9_first_sung(receipt, ans, codes, details):
    """First real singing (vocal stem) lands near 15% of runtime, in the band."""
    src = _source_named(ans, codes, "FIRST_SUNG")
    got = _num(ans.get("first_sung_pct"))
    if got is None:
        codes.append("%s:FIRST_SUNG missing measured first_sung_pct"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    want = _num(ans.get("target_pct"))
    want = FIRST_SUNG_TARGET_PCT if want is None else want
    detector = ans.get("detector") or receipt.get("detector") or ""
    if not (isinstance(detector, str) and detector.strip()):
        codes.append("%s:FIRST_SUNG detector (vocal-stem) not named"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    if not _is_singing_detector(detector):
        # G3: first-sung position is measured on the vocal stem by
        # core/singing_detector, never read off section labels.
        codes.append("%s:FIRST_SUNG detector %r is not the singing detector"
                     % (CHECKLIST_NO_MEASUREMENT, detector.strip()))
        return False
    delta = abs(got - want)
    details["first_sung_pct"] = got
    details["first_sung_band"] = band(delta)
    if band(delta) == BAND_REDO:
        codes.append("%s:FIRST_SUNG first singing at %.1f%% vs goal %.1f%% "
                     "(%.1f off, redo over %.0f)" % (
                         CHECKLIST_FIRST_SUNG_OFF, got, want, delta,
                         CHECKLIST_REDO_PCT))
        return False
    if band(delta) == BAND_FLAG:
        details["first_sung_flag"] = _flag_text("first_sung", got, want, delta)
    return src is not None


# ------------------------------------------------------ Q10 PICTURES MATCH
def _q10_pictures(receipt, ans, codes, details):
    """Every shot names its line and its real Suno time; subject matches."""
    src = _source_named(ans, codes, "PICTURES_MATCH")
    shots = ans.get("shots")
    if not isinstance(shots, list) or not shots:
        codes.append("%s:PICTURES_MATCH no shot/time/line/match list"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    ok = src is not None
    bad = []
    matched = 0
    for i, s in enumerate(shots):
        sid = s.get("shot", "shot-%d" % (i + 1)) if isinstance(s, dict) \
            else "shot-%d" % (i + 1)
        if not isinstance(s, dict) or _num(s.get("time_s")) is None \
                or not isinstance(s.get("line"), str) or not s["line"].strip() \
                or not _truthy_measured(s.get("match")):
            codes.append("%s:PICTURES_MATCH %s missing time_s/line/match"
                         % (CHECKLIST_NO_MEASUREMENT, sid))
            ok = False
            continue
        speed = _num(s.get("slowdown"))
        if s["match"] is False:
            bad.append("%s @%.1fs" % (sid, _num(s["time_s"])))
        elif speed is not None and speed > MAX_SLOWDOWN + 1e-9:
            bad.append("%s slowed %.2fx > %.2fx" % (sid, speed, MAX_SLOWDOWN))
        else:
            matched += 1
    if bad:
        codes.append("%s:PICTURES_MATCH picture does not match its line: %s"
                     % (CHECKLIST_PICTURE_MISMATCH, "; ".join(bad[:10])))
        ok = False
    details["pictures_matched"] = matched
    details["pictures_total"] = len(shots)
    return ok


# ------------------------------------------------------- Q11 GOALS BAND
def _q11_goals(receipt, ans, codes, details):
    """Every numeric goal judged by Trevor's band; the flag is shown."""
    src = _source_named(ans, codes, "GOALS_BAND")
    goals = ans.get("goals")
    if not isinstance(goals, list) or not goals:
        codes.append("%s:GOALS_BAND no numeric goals listed"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    ok = src is not None
    flags = 0
    for i, g in enumerate(goals):
        name = g.get("name", "goal-%d" % (i + 1)) if isinstance(g, dict) \
            else "goal-%d" % (i + 1)
        got = _num(g.get("measured")) if isinstance(g, dict) else None
        want = _num(g.get("target")) if isinstance(g, dict) else None
        if got is None or want is None:
            codes.append("%s:GOALS_BAND %s missing measured/target"
                         % (CHECKLIST_NO_MEASUREMENT, name))
            ok = False
            continue
        if g.get("unit", "pct") == "pct":           # points of a percent
            delta = abs(got - want)
        elif want != 0:                             # relative percent
            delta = abs(got - want) / abs(want) * 100.0
        else:
            codes.append("%s:GOALS_BAND %s target 0 with a non-pct unit"
                         % (CHECKLIST_NO_MEASUREMENT, name))
            ok = False
            continue
        b = band(delta)
        if b == BAND_REDO:
            codes.append("%s:GOALS_BAND %s %.1f vs goal %.1f (%.1f off, "
                         "over %.0f: redo)" % (CHECKLIST_GOAL_REDO, name, got,
                                              want, delta,
                                              CHECKLIST_REDO_PCT))
            ok = False
        elif b == BAND_FLAG:
            flags += 1
            flag = g.get("flag")
            if not (isinstance(flag, str) and flag.strip()):
                codes.append("%s:GOALS_BAND %s is %.1f off (5-10 band) but "
                             "the receipt shows no flag"
                             % (CHECKLIST_NO_MEASUREMENT, name, delta))
                ok = False
    details["goals_judged"] = len(goals)
    details["goals_flagged"] = flags
    return ok


# ----------------------------------------------------------------- evaluate
# ---------------------------------------------------------- FU-U13 (product)
_PC_WPS = 1.07                      # sung words per second (length_formula)
_PC_SHOT_S = 3.0                    # a tagged shot with no stated duration
_PC_END_CARD = ("end_card", "endcard", "cta_card")


def _pc_tagged(obj, tag):
    if not isinstance(obj, dict):
        return False
    if obj.get(tag) is True:
        return True
    tags = obj.get("tags") or ()
    if isinstance(tags, str):
        tags = (tags,)
    return tag in tags


def _pc_seconds(obj, fallback):
    for k in ("seconds", "duration_s", "duration"):
        v = obj.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return float(v)
    words = len(str(obj.get("text", "")).split())
    return words / _PC_WPS if words else fallback


def measure_product_connection(shots, lyrics, runtime_s):
    """FU-U13: measure the product-connection seconds from the delivered run.

    Totals the seconds of shots tagged product plus lyric lines tagged
    product, against the measured runtime. 10-15% is a TARGET: inside is
    PASS, outside is FLAG carrying the measured seconds and percent, and it
    is NEVER a blocker by itself. A run whose product appears only on an end
    card is flagged (the product must be named in the lyrics and on screen).
    """
    def _num(v):
        return float(v) if isinstance(v, (int, float)) \
            and not isinstance(v, bool) and v > 0 else None

    rt = _num(runtime_s)
    if rt is None:
        return {"verdict": "UNAVAILABLE",
                "measurement": "UNMEASURED: no runtime_s for the run",
                "seconds": None, "percent": None, "blocking": False}
    shots = [s for s in (shots or []) if isinstance(s, dict)]
    lines = [l for l in (lyrics or []) if isinstance(l, dict)]
    product_shots = [s for s in shots if _pc_tagged(s, "product")]
    product_lines = [l for l in lines if _pc_tagged(l, "product")]
    seconds = round(sum(_pc_seconds(o, _PC_SHOT_S)
                        for o in product_shots + product_lines), 1)
    percent = round(seconds / rt * 100.0, 1)
    in_band = PRODUCT_TARGET_LO_PCT <= percent <= PRODUCT_TARGET_HI_PCT
    end_card_only = bool(product_shots) and all(
        any(_pc_tagged(s, t) for t in _PC_END_CARD) for s in product_shots)
    verdict = "PASS" if in_band and not end_card_only else "FLAG"
    why = []
    if not in_band:
        why.append("%.1f%% of %.1fs runtime outside the %.0f-%.0f%% target"
                   % (percent, rt, PRODUCT_TARGET_LO_PCT,
                      PRODUCT_TARGET_HI_PCT))
    if end_card_only:
        why.append("product appears only on an end card; name it in the "
                   "lyrics and on screen (cover, title, link)")
    return {"verdict": verdict, "seconds": seconds, "percent": percent,
            "runtime_s": rt, "in_target": in_band,
            "end_card_only": end_card_only, "blocking": False,
            "measurement": ("product connection %.1fs = %.1f%% of runtime "
                            "(%s%s)" % (seconds, percent, verdict,
                                        "; " + "; ".join(why) if why else ""))}
def measure_villain_doctrine(shots, lines, runtime_s, villain=None):
    """FU-U16: measure the villain, pain and rise from the delivered run.

    "People don't care about the hero until they meet the villain."
    - Trevor Otts. Reports villain shots, villain screen seconds, pain
    seconds and rise seconds against the measured runtime. Evidence only:
    this row never joins repair_scope and never blocks beyond the planner's
    two fail-closed cases (no villain named / villain with no shot).
    """
    def _num(v):
        return float(v) if isinstance(v, (int, float)) \
            and not isinstance(v, bool) and v > 0 else None

    rt = _num(runtime_s)
    if rt is None:
        return {"verdict": "UNAVAILABLE",
                "measurement": "UNMEASURED: no runtime_s for the run",
                "reason_codes": ["VILLAIN_DOCTRINE_UNMEASURED"],
                "seconds": None, "blocking": False}
    shots = [s for s in (shots or []) if isinstance(s, dict)]
    lines = [l for l in (lines or []) if isinstance(l, dict)]
    name = None
    if isinstance(villain, dict):
        name = villain.get("name")
    elif isinstance(villain, str) and villain.strip():
        name = villain
    named = bool(isinstance(name, str) and name.strip())
    villain_shots = [s for s in shots if _vd_tagged(s, "villain")]
    villain_seconds = round(sum(_vd_seconds(s) for s in villain_shots), 1)
    pain_seconds = round(sum(_vd_seconds(o) for o in shots + lines
                             if _vd_tagged(o, "pain")), 1)
    rise_seconds = round(sum(_vd_seconds(o) for o in shots + lines
                             if _vd_tagged(o, "rise")), 1)
    pain_percent = round(pain_seconds / rt * 100.0, 1)
    in_band = VILLAIN_PAIN_LO_PCT <= pain_percent <= VILLAIN_PAIN_HI_PCT
    codes = []
    if not named:
        codes.append("NO_VILLAIN_NAMED")
    if named and not villain_shots:
        codes.append("VILLAIN_HAS_NO_SHOT")
    if not in_band:
        codes.append("PAIN_SHARE_OUTSIDE_TARGET")
    verdict = "FAIL" if any(c in ("NO_VILLAIN_NAMED", "VILLAIN_HAS_NO_SHOT")
                            for c in codes) else ("PASS" if not codes else "FLAG")
    why = []
    if "NO_VILLAIN_NAMED" in codes:
        why.append("no villain named in the story plan")
    if "VILLAIN_HAS_NO_SHOT" in codes:
        why.append("villain has no shot of its own")
    if "PAIN_SHARE_OUTSIDE_TARGET" in codes:
        why.append("%.1f%% pain outside the %.0f-%.0f%% target"
                   % (pain_percent, VILLAIN_PAIN_LO_PCT, VILLAIN_PAIN_HI_PCT))
    return {"verdict": verdict,
            "villain_shots": len(villain_shots),
            "villain_seconds": villain_seconds,
            "pain_seconds": pain_seconds, "pain_percent": pain_percent,
            "rise_seconds": rise_seconds, "runtime_s": rt,
            "in_target": in_band, "reason_codes": codes,
            "blocking": False,     # evidence row; the planner carries the gate
            "card_line": "Villain: %s, shown in %d shots"
                         % (name if named else "NONE", len(villain_shots)),
            "measurement": ("villain doctrine: %s; pain %.1fs = %.1f%% of "
                            "%.1fs runtime; villain %d shots / %.1fs; rise "
                            "%.1fs (%s%s)" % (name if named else "NO VILLAIN",
                                              pain_seconds, pain_percent, rt,
                                        len(villain_shots), villain_seconds,
                                        rise_seconds, verdict,
                                        "; " + "; ".join(why) if why else ""))}



def evaluate(receipt):
    """Answer the 11 questions from the delivery receipt.

    receipt maps question names (or "answers") to answer dicts carrying the
    MEASURED evidence. Returns:
      {"pass": bool, "answers": {q: {"answer": "yes"|"no",
                                     "measurement": str}},
       "reason_code": "+".join(codes), "detail": str,
       "repair_scope": [failing questions], "evidence": {...}}

    G7 laws: a missing answer or a "yes" without a measurement is a "no";
    the failing part (the question) is named in repair_scope; the run is
    never cancelled by this checker (gate verdict stays FAIL, targeted
    repair per 17.7).
    """
    if not isinstance(receipt, dict):
        raise ChecklistError("BAD_INPUT",
                             "receipt must be an object, got %s"
                             % type(receipt).__name__)
    answers = {}
    codes = []
    details = {}
    failing = []
    for q in QUESTIONS:
        ans = _answer(receipt, q)
        if ans is None:
            codes.append("%s:%s" % (REASON_CODES["ANSWER_MISSING"], q))
            answers[q] = {"answer": "no",
                          "measurement": "UNMEASURED: no answer in receipt"}
            failing.append(q)
            continue
        qcodes = []
        qok = True
        qdetails = {}
        if q == "SUNG":
            qok = _q1_sung(receipt, ans, qcodes, qdetails)
        elif q == "ON_TARGET":
            qok = _q2_on_target(receipt, ans, qcodes, qdetails)
        elif q == "WORDS":
            qok = _q3_words(receipt, ans, qcodes, qdetails)
        elif q == "FACES":
            qok = _q4_faces(receipt, ans, qcodes, qdetails)
        elif q == "VOICE_MUSIC":
            qok = _q5_voice_music(receipt, ans, qcodes, qdetails)
        elif q == "MODELS":
            qok = _q6_models(receipt, ans, qcodes, qdetails)
        elif q == "HONEST_RECEIPT":
            qok = _q7_honest(receipt, ans, qcodes, qdetails)
        elif q == "LIP_SYNC":
            qok = _q8_lip_sync(receipt, ans, qcodes, qdetails)
        elif q == "FIRST_SUNG":
            qok = _q9_first_sung(receipt, ans, qcodes, qdetails)
        elif q == "PICTURES_MATCH":
            qok = _q10_pictures(receipt, ans, qcodes, qdetails)
        elif q == "GOALS_BAND":
            qok = _q11_goals(receipt, ans, qcodes, qdetails)
        codes.extend(qcodes)
        details.update(qdetails)
        if qok:
            answers[q] = {"answer": "yes",
                          "measurement": _measurement_line(q, ans, qdetails)}
        else:
            answers[q] = {"answer": "no",
                          "measurement": "; ".join(qcodes) or
                                         "UNMEASURED: no measurement"}
            failing.append(q)
    # FU-U13: the product-connection row is reported, never enforced. The
    # check finds no measurement -> UNAVAILABLE, which is neither pass nor
    # fail here: the row carries no weight in repair_scope by construction.
    pc = measure_product_connection(receipt.get("shots"),
                                    receipt.get("lyrics"),
                                    receipt.get("runtime_s"))
    details[PRODUCT_ROW] = pc
    # FU-U16: the villain-doctrine row is reported, never enforced. Evidence
    # only: it never joins repair_scope, and the planner owns the two
    # fail-closed cases.
    details[VILLAIN_ROW] = measure_villain_doctrine(
        receipt.get("shots"), receipt.get("lyrics"),
        receipt.get("runtime_s"), receipt.get("villain"))
    if codes:
        return {"pass": False,
                "answers": answers,
                "reason_code": "+".join(sorted({c.split(":")[0]
                                                for c in codes})),
                "detail": "; ".join(codes[:12]),
                "repair_scope": failing,       # only the failing part
                "evidence": details}
    return {"pass": True, "answers": answers,
            "reason_code": "CHECKLIST_ALL_MEASURED_PASS",
            "detail": "", "repair_scope": [], "evidence": details}


def _measurement_line(q, ans, qdetails):
    """One plain-English measured line per question, for the receipt."""
    d = qdetails
    if q == "SUNG":
        # G3-WIRE: the provenance suffix rides the answer so a PASS record
        # satisfies core/qc_gate's SUNG_CLAIM_UNMEASURED rule unchanged.
        # It leads the line because to_qc_record truncates each measurement
        # to 80 chars in the record summary -- the suffix must survive that.
        return "%s | sung %.1f%% / spoken %.1f%% (%s)" % (
            d.get("provenance", "share_source=UNMEASURED"),
            d.get("sung_pct", 0.0), d.get("spoken_pct", 0.0),
            d.get("detector", "detector"))
    if q == "ON_TARGET":
        worst = max(((v["delta_pts"] if "delta_pts" in v
                      else v.get("delta_pct", 0.0))
                     for v in d.get("measured", {}).values()),
                    default=0.0)
        return "max delta %.1f pts, tolerance %.0f pts" % (
            worst, d.get("tolerance_pts", CHECKLIST_TOLERANCE_PCT))
    if q == "WORDS":
        return "%d/%d words, %d missing, %d invented" % (
            d.get("words_present", 0), d.get("words_total", 0),
            d.get("missing_count", 0), d.get("invented_count", 0))
    if q == "FACES":
        return "%d shot(s) frame-checked, %d emotion mismatch" % (
            d.get("shots_checked", 0), len(d.get("face_mismatch_shots", [])))
    if q == "VOICE_MUSIC":
        return "music gaps %.2f s, %d line(s) delivery-checked%s" % (
            d.get("music_gaps_s", 0.0), d.get("lines_checked", 0),
            ("reverb tail %.3f s" % d["reverb_tail_s"])
            if "reverb_tail_s" in d and d["reverb_tail_s"] is not None else "")
    if q == "MODELS":
        parts = ["%s=%s" % (k, v)
                 for k, v in d.get("models", {}).items()]
        vm = d.get("video_model")          # F16 clip gate evidence
        if isinstance(vm, dict):
            parts.append("video clips=%d locked=%s mismatches=%d" % (
                vm.get("clips", 0),
                vm.get("locked") or "UNMEASURED",
                vm.get("mismatches", 0)))
        return ", ".join(parts)
    if q == "LIP_SYNC":
        return "%d clip(s), %d flagged (ACCEPT_WITH_FLAG / held / kept best of 2), %d tagged kept-take%s%s" % (
            d.get("lipsync_clips", 0), len(d.get("lipsync_flagged", [])),
            d.get("lipsync_tagged", 0),
            (" (" + "/".join(d["lipsync_tag_names"]) + ")")
            if d.get("lipsync_tag_names") else "",
            ("; " + " | ".join(d["lipsync_flags"])) if d.get("lipsync_flags") else "")
    if q == "FIRST_SUNG":
        return "first real singing at %.1f%% of runtime (%s)%s" % (
            d.get("first_sung_pct", 0.0), d.get("first_sung_band", ""),
            (" " + d["first_sung_flag"]) if "first_sung_flag" in d else "")
    if q == "PICTURES_MATCH":
        return "%d/%d pictures match their line" % (
            d.get("pictures_matched", 0), d.get("pictures_total", 0))
    if q == "GOALS_BAND":
        return "%d goal(s) judged, %d flagged" % (
            d.get("goals_judged", 0), d.get("goals_flagged", 0))
    return "source: %s" % d.get("source", "per-field source refs")


# ---------------------------------------------------------------- gate rec
def to_qc_record(result, run_id, stage, reviewer, check_id=None,
                 checker_version=None):
    """qc-schema 1.0.0 record (check=final_edit) for core/qc_gate.py.

    Same contract as sibling checkers: the run's Final edit QC (17.5)
    includes this record in the records array it hands
    core/qc_gate.evaluate -- the shared gate, no new framework. The gate
    still requires an independent reviewer (17.6); this record alone never
    advances a stage. reviewer must carry identity/session/authority
    (24.4).
    """
    if not isinstance(result, dict) or "pass" not in result:
        raise ChecklistError("BAD_INPUT", "result must be an evaluate result")
    if not isinstance(reviewer, dict):
        raise ChecklistError("BAD_INPUT", "reviewer must be an object")
    rev = {}
    for key in ("identity", "session", "authority"):
        v = reviewer.get(key)
        if not (isinstance(v, str) and v.strip()):
            raise ChecklistError("BAD_INPUT",
                                 "reviewer.%s is required" % key)
        rev[key] = v.strip()
    answers = result.get("answers", {})
    # qc-schema evidence carries summary + refs only; the 7 answers ride in
    # the summary, each as yes/no plus the measurement that proves it
    lines = ["%s=%s(%s)" % (q, a["answer"], a["measurement"][:80])
             for q, a in sorted(answers.items())]
    # FU-U13: the product-connection measurement rides the same summary so
    # the receipt/checklist output reports it every run (measured, flagged
    # when outside the 10-15% target, never a blocker).
    pc = (result.get("evidence") or {}).get(PRODUCT_ROW)
    if isinstance(pc, dict):
        lines.append("%s=%s(%s)" % (PRODUCT_ROW, pc.get("verdict", "?"),
                                    str(pc.get("measurement", ""))[:120]))
    # FU-U16: the villain-doctrine measurement rides the same summary (the
    # approval card line is evidence["VILLAIN_DOCTRINE"]["card_line"]).
    vd = (result.get("evidence") or {}).get(VILLAIN_ROW)
    if isinstance(vd, dict):
        lines.append("%s=%s(%s)" % (VILLAIN_ROW, vd.get("verdict", "?"),
                                    str(vd.get("measurement", ""))[:120]))
    passed = bool(result["pass"])
    summary = ("delivery checklist %s: %d/%d measured%s | %s"
               % ("pass" if passed else "FAIL",
                  sum(1 for a in answers.values() if a["answer"] == "yes"),
                  len(QUESTIONS),
                  (" [%s]" % result["reason_code"]) if not passed else "",
                  "; ".join(lines)))
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "check_id": check_id or CHECK_ID,
        "run_id": run_id,
        "stage": stage,
        "check": CHECK,
        "verdict": "PASS" if passed else "FAIL",
        "evidence": {
            "summary": summary,
            "refs": [CHECKLIST_REF],
        },
        "reason_code": "CHECKLIST_ALL_MEASURED_PASS" if passed
                       else result.get("reason_code", "CHECKLIST_FAIL"),
        "checker_version": checker_version or TOOL_VERSION,
        "reviewer": rev,
    }


# --------------------------------------------------- FU-U14 SONG MP3 ITEM
#: Trevor (order FU-U14, verbatim): "make an update so that the mp3 is a part
#: of the deliverable ... so clients can release the songs as an album". Every
#: delivered ad folder MUST hold the FINAL SONG as an mp3 (320 kbps, the exact
#: song used in the ad), named "<Author> - <Title> - Song.mp3".
SONG_MP3_SUFFIX = " - Song"
SONG_MP3_TOL_S = 0.1        # duration match, seconds ("within 0.1 s")
SONG_MP3_CORR_MIN = 0.95    # cross-correlation floor vs the ad's audio
SONG_MP3_WINDOW_S = 0.05    # envelope window for the correlation
SONG_MP3_WINDOWS_MAX = 2000

#: The new REQUIRED battery item (rows, same shape as the checklist's own).
SONG_MP3_ITEM = "SONG_MP3"
SONG_MP3_CODES = {
    "FILE": "SONG_MP3_MISSING",
    "DURATION": "SONG_MP3_DURATION_MISMATCH",
    "CORRELATION": "SONG_MP3_CORRELATION_LOW",
    "UNMEASURED": "SONG_MP3_UNMEASURED",
}


def safe_song_name(author, title):
    """The deliverable's song stem: "<Author> - <Title> - Song"."""
    clean = lambda s: re.sub(r"\s+", " ", (s or "").strip())
    author, title = clean(author), clean(title)
    if not (author and title):
        raise ChecklistError("BAD_INPUT", "author and title are required")
    return "%s - %s%s" % (author, title, SONG_MP3_SUFFIX)


def _wav_measure(path):
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        width = w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if rate <= 0 or w.getnchannels() < 1:
        return None
    # mono downmix; 8/16/24/32-bit little-endian PCM (the wave module's own)
    chans = 2 if width in (2, 3, 4) else 1
    step = width * chans
    window = max(1, int(rate * SONG_MP3_WINDOW_S))
    env, acc, n = [], 0.0, 0
    total = len(frames) // step
    for i in range(total):
        chunk = frames[i * step:i * step + width]
        if width == 1:
            v = (chunk[0] - 128) / 128.0
        else:
            v = struct.unpack("<h", chunk[:2])[0] / 32768.0
        acc += v * v
        n += 1
        if n == window:
            env.append(math.sqrt(acc / n))
            acc, n = 0.0, 0
    if n:
        env.append(math.sqrt(acc / n))
    return {"duration_s": total / float(rate), "envelope": env}


def _mp3_measure(path, ffprobe="ffprobe", ffmpeg="ffmpeg"):
    """mp3 (and any non-wav): ffprobe duration + ffmpeg decode -> wave."""
    if not (shutil.which(ffprobe) and shutil.which(ffmpeg)):
        return None
    import json as _json
    import tempfile
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=60).stdout
        dur = float(_json.loads(out)["format"]["duration"])
    except (OSError, ValueError, KeyError,
            subprocess.SubprocessError):
        return None
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "decoded.wav"
        try:
            subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(path),
                            "-ac", "1", "-ar", "8000", str(wav)],
                           capture_output=True, text=True, check=True,
                           timeout=600)
        except (OSError, subprocess.SubprocessError):
            return None
        m = _wav_measure(wav)
    if m is None:
        return None
    m["duration_s"] = dur            # ffprobe's number is the container truth
    return m


def measure_audio(path):
    """{"duration_s", "envelope"} for wav (wave module) or mp3 (ffmpeg).

    None when the file has no readable audio: the caller fails closed.
    """
    try:
        return _wav_measure(path)
    except (wave.Error, OSError, EOFError, struct.error):
        return _mp3_measure(path)


def _pearson(env_a, env_b):
    """Normalized (Pearson) correlation of two envelopes, stdlib math only."""
    n = min(len(env_a), len(env_b))
    if n < 3:
        return None
    a, b = env_a[:n], env_b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0.0 or vb <= 0.0:      # constant envelope: nothing to correlate
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def check_song_mp3(ad_dir, ad_audio_path, title, author, ffprobe="ffprobe",
                   ffmpeg="ffmpeg"):
    """The song-mp3 battery item: PASS/FAIL rows, fail closed.

    Rows (the checklist's own row shape: item / answer / measurement):
      SONG_MP3_FILE         the "<Author> - <Title> - Song.<ext>" file exists
      SONG_MP3_DURATION     its duration covers the ad's audio (0.1 s)
      SONG_MP3_CORRELATION  >= 0.95 with the ad's audio (mono envelopes)
    """
    d = Path(ad_dir)
    stem = safe_song_name(author, title)
    hits = sorted(p for p in d.glob(stem + ".*")
                  if p.suffix.lower() in (".mp3", ".wav"))
    rows = []

    def row(item, ok, measurement, code=None, value=None):
        r = {"item": item, "answer": "yes" if ok else "no",
             "measurement": measurement}
        if code and not ok:
            r["code"] = code
        if value is not None:
            r["value"] = value
        rows.append(r)
        return ok

    if not hits:
        row("SONG_MP3_FILE", False,
            "no %s.{mp3,wav} in %s" % (stem, d), SONG_MP3_CODES["FILE"])
        row("SONG_MP3_DURATION", False, "UNMEASURED: no song file",
            SONG_MP3_CODES["DURATION"])
        row("SONG_MP3_CORRELATION", False, "UNMEASURED: no song file",
            SONG_MP3_CODES["CORRELATION"])
        return rows
    song_path = hits[0]
    row("SONG_MP3_FILE", True, "found %s" % song_path.name)

    song = measure_audio(song_path)
    ad = measure_audio(ad_audio_path)
    if song is None:
        row("SONG_MP3_DURATION", False,
            "UNMEASURED: cannot read audio from %s" % song_path.name,
            SONG_MP3_CODES["UNMEASURED"])
        row("SONG_MP3_CORRELATION", False,
            "UNMEASURED: cannot read audio from %s" % song_path.name,
            SONG_MP3_CODES["UNMEASURED"])
        return rows
    if ad is None:
        row("SONG_MP3_DURATION", False,
            "UNMEASURED: cannot read audio from %s" % Path(ad_audio_path).name,
            SONG_MP3_CODES["UNMEASURED"])
        row("SONG_MP3_CORRELATION", False,
            "UNMEASURED: cannot read audio from %s" % Path(ad_audio_path).name,
            SONG_MP3_CODES["UNMEASURED"])
        return rows

    # the song is the FULL track: it must at least cover the ad's span
    dur_ok = song["duration_s"] >= ad["duration_s"] - SONG_MP3_TOL_S
    row("SONG_MP3_DURATION", dur_ok,
        "song %.2fs vs ad %.2fs (tolerance %.1fs%s)"
        % (song["duration_s"], ad["duration_s"], SONG_MP3_TOL_S,
           "" if dur_ok else ", song shorter than the ad span"),
        SONG_MP3_CODES["DURATION"])

    corr = _pearson(song["envelope"], ad["envelope"])
    if corr is None:
        row("SONG_MP3_CORRELATION", False,
            "UNMEASURED: envelope has no variance (silence or unreadable)",
            SONG_MP3_CODES["UNMEASURED"], 0.0)
    else:
        row("SONG_MP3_CORRELATION", corr >= SONG_MP3_CORR_MIN,
            "correlation %.3f vs floor %.2f" % (corr, SONG_MP3_CORR_MIN),
            SONG_MP3_CODES["CORRELATION"], round(corr, 4))
    return rows


def delivery_battery(ad_dir, ad_audio_path, title, author):
    """The file-backed delivery battery rows (FU-U14: the song mp3 item).

    Same contract shape as evaluate(): pass / rows / reason_code /
    repair_scope / detail; a "no" row names only the failing item (the
    repair scope) and never cancels the run.
    """
    rows = check_song_mp3(ad_dir, ad_audio_path, title, author)
    failing = [r["item"] for r in rows if r["answer"] != "yes"]
    codes = sorted({r.get("code") for r in rows if r.get("code")})
    detail = "; ".join("%s: %s" % (r["item"], r["measurement"])
                       for r in rows if r["answer"] != "yes")
    return {"pass": not failing, "rows": rows,
            "reason_code": "+".join(codes) if codes
                           else "CHECKLIST_SONG_MP3_PASS",
            "repair_scope": failing, "detail": detail,
            "item": SONG_MP3_ITEM}


# ------------------------------------------------------------------- CLI
def main(argv=None):
    import argparse
    import json
    p = argparse.ArgumentParser(
        prog="delivery_checklist",
        description="G7 delivery QC: the 7 checklist questions, answered "
                    "with measured evidence from the receipt (fail-closed)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("check", help="evaluate a receipt")
    a.add_argument("--receipt", required=True, help="receipt JSON path")
    a.add_argument("--qc-record", default="",
                   help="also write the qc-schema final_edit record here")
    a.add_argument("--run-id", default="")
    a.add_argument("--stage", default="final")
    a.add_argument("--reviewer-identity", default="")
    a.add_argument("--reviewer-session", default="")
    a.add_argument("--reviewer-authority", default="")
    ns = p.parse_args(argv)
    try:
        with open(ns.receipt, encoding="utf-8") as f:
            receipt = json.load(f)
        res = evaluate(receipt)
    except (OSError, ValueError) as e:
        print(json.dumps({"outcome": "error", "reason_code": "BAD_INPUT",
                          "detail": str(e)}))
        return EXIT["error"]
    out = {"outcome": "ok" if res["pass"] else "rejected",
           "reason_code": res["reason_code"],
           "answers": res["answers"],
           "repair_scope": res["repair_scope"],
           "evidence": res["evidence"]}
    if ns.qc_record:
        if not (ns.run_id and ns.reviewer_identity and ns.reviewer_session
                and ns.reviewer_authority):
            print(json.dumps({"outcome": "error",
                              "reason_code": "RECORD_NEEDS_RUN_AND_REVIEWER",
                              "detail": "--run-id + reviewer identity/"
                                        "session/authority required for "
                                        "--qc-record"}))
            return EXIT["error"]
        rec = to_qc_record(res, ns.run_id, ns.stage,
                           {"identity": ns.reviewer_identity,
                            "session": ns.reviewer_session,
                            "authority": ns.reviewer_authority})
        with open(ns.qc_record, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
        out["qc_record"] = ns.qc_record
    print(json.dumps(out, indent=2))
    return EXIT["ok"] if res["pass"] else EXIT["rejected"]


if __name__ == "__main__":
    raise SystemExit(main())
