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
                 (receipt.detector) must name the stem-based detector --
                 labels/section names are never evidence (G5).
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
                 from the checklist, compared case-insensitively).
  7 HONEST    -- every receipt number names its source (non-empty
                 "source"/"source_ref" next to each measured value);
                 anything unmeasured must be written "UNMEASURED" and an
                 UNMEASURED value can never stand as a pass.

Fail-closed: a receipt that is not an object, a question with no answer, or
an answer without its measurement is a FAIL naming exactly that part.
stdlib only, no network, no provider call, no spend, no absolute operator
path, opens no file at all (the receipt is handed in as data).

Run: python3 core/delivery_checklist/test_delivery_checklist.py
"""
from __future__ import annotations

TOOL_NAME = "delivery_checklist"
TOOL_VERSION = "1.1.0"
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

#: Q8 lip-sync gate: the H2 measured numbers (report 05, order 1225).
LIPSYNC_MAX_OFFSET_S = 0.05         # mouth-vs-voice offset
LIPSYNC_MIN_CORR = 0.55             # mouth/voice envelope correlation
LIPSYNC_MIN_CONTROL_GAP = 0.25      # above the wrong-audio control
LIPSYNC_MAX_FROZEN_S = 0.75         # longest frozen face
#: Q9: first real singing (vocal stem) target, share of runtime (H6).
FIRST_SUNG_TARGET_PCT = 15.0
#: Q10: no slow-motion above this speed-down factor (H5).
MAX_SLOWDOWN = 1.15

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


# ------------------------------------------------------------------ Q1 SUNG
def _q1_sung(receipt, ans, codes, details):
    """Measured sung/spoken percents from the vocal-stem detector."""
    style = ans.get("style") or ans.get("delivery_style") or receipt.get("style")
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
    details["detector"] = detector.strip()
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
def _q6_models(receipt, ans, codes, details):
    """Only the locked models were used."""
    used = ans.get("used") if isinstance(ans.get("used"), dict) else \
        {k: v for k, v in ans.items() if k != "used"}
    if not isinstance(used, dict) or not used:
        codes.append("%s:MODELS no per-asset model list in the receipt"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    ok = True
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
def _q8_lip_sync(receipt, ans, codes, details):
    """Every lip-sync clip passes the H2 measured gate; numbers shown."""
    clips = ans.get("clips")
    src = _source_named(ans, codes, "LIP_SYNC")
    if not isinstance(clips, list) or not clips:
        codes.append("%s:LIP_SYNC no per-clip offset/correlation list"
                     % CHECKLIST_NO_MEASUREMENT)
        return False
    ok = src is not None
    worst_off, worst_corr = 0.0, 1.0
    for i, c in enumerate(clips):
        cid = c.get("clip", "clip-%d" % (i + 1)) if isinstance(c, dict) \
            else "clip-%d" % (i + 1)
        vals = {k: _num(c.get(k)) if isinstance(c, dict) else None
                for k in ("offset_s", "correlation", "control_correlation",
                          "frozen_s")}
        missing = [k for k, v in vals.items() if v is None]
        if missing:
            codes.append("%s:LIP_SYNC %s missing %s"
                         % (CHECKLIST_NO_MEASUREMENT, cid, "/".join(missing)))
            ok = False
            continue
        bad = []
        if abs(vals["offset_s"]) > LIPSYNC_MAX_OFFSET_S + 1e-9:
            bad.append("offset %.3fs > %.2fs" % (vals["offset_s"],
                                                 LIPSYNC_MAX_OFFSET_S))
        if vals["correlation"] < LIPSYNC_MIN_CORR:
            bad.append("corr %.2f < %.2f" % (vals["correlation"],
                                              LIPSYNC_MIN_CORR))
        if vals["correlation"] - vals["control_correlation"] \
                < LIPSYNC_MIN_CONTROL_GAP - 1e-9:
            bad.append("only %.2f above wrong-audio control (need %.2f)" % (
                vals["correlation"] - vals["control_correlation"],
                LIPSYNC_MIN_CONTROL_GAP))
        if vals["frozen_s"] > LIPSYNC_MAX_FROZEN_S + 1e-9:
            bad.append("frozen face %.2fs > %.2fs" % (vals["frozen_s"],
                                                      LIPSYNC_MAX_FROZEN_S))
        if bad:
            codes.append("%s:LIP_SYNC %s %s" % (CHECKLIST_LIPSYNC_FAILED, cid,
                                                  ", ".join(bad)))
            ok = False
        worst_off = max(worst_off, abs(vals["offset_s"]))
        worst_corr = min(worst_corr, vals["correlation"])
    details["lipsync_clips"] = len(clips)
    details["lipsync_worst_offset_s"] = worst_off
    details["lipsync_worst_corr"] = worst_corr
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
        return "sung %.1f%% / spoken %.1f%% (%s)" % (
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
        return ", ".join("%s=%s" % (k, v)
                         for k, v in d.get("models", {}).items())
    if q == "LIP_SYNC":
        return "%d clip(s), worst offset %.3fs, worst corr %.2f" % (
            d.get("lipsync_clips", 0), d.get("lipsync_worst_offset_s", 0.0),
            d.get("lipsync_worst_corr", 0.0))
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
