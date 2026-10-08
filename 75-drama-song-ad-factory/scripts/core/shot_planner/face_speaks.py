#!/usr/bin/env python3
"""face_speaks.py: Part H H4 -- every speaking face is a lip-sync clip, and
lip-sync coverage hits a target band.

Evidence (Kiesett "Stop Stale" ad, 2026-10-08): 19 s of the 63 s ad showed a
character's face with a moving mouth while the words heard were not hers,
and only 9.6 s carried lip-sync against the 15-20 s rule. Part E E6
(final_assembler/lipsync_coverage.py) counts seconds and lines only; it
never asked WHICH faces are speaking. This module adds the two missing
pieces, stdlib only, no network, no spend:

1. FACE RULE (QC): speaking_face_rows() lists every shot where a face is
   visibly speaking; check_face_speaks() fails FACE_SPEAKS_NO_LIPSYNC for any
   such shot that is not a lip-sync clip of that character's OWN line, and
   LIPSYNC_WRONG_FACE for a lip-sync clip of a line whose speaker is not on
   screen. A face is "visibly speaking" in a shot when
     * that character is in faces_on_screen AND speaks a line that overlaps
       the shot window by more than OVERLAP_MIN_S, or
     * the shot lists the character in speaking_faces (picture analysis: the
       mouth moves, e.g. an invented talking H3 clip).
   Allowed instead of a speaking face: back of head, hands, over-the-shoulder
   (leave the character out of faces_on_screen), another character, or an
   off-screen voice (narrator).

2. COVERAGE TARGET (planner + QC): target_band_s() is the 15-20 s target of a
   60-90 s ad (scaled by runtime outside it) with the 5-point grace
   (GRACE_POINTS of runtime). plan_lipsync_lines() picks enough of the
   script's own-face lines to reach the target; check_coverage_band() is the
   QC measurement. Part E E6 hard floors stay as they are.

ponytail: the 5-point grace and the 15-20 s band are constants here; fold
them into the G10 constants module when that lands on main.
"""
from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:                                   # reuse the Decision-26 predicate
    from lip_sync.narrator_rule import person_on_screen as _person
except ImportError:                    # ponytail: fallback keeps module usable
    def _person(name):                 # when the narrator package is absent
        n = (name or "").strip().lower()
        return bool(n) and n not in ("narrator", "voiceover", "voice-over",
                                     "off-screen", "offscreen", "host",
                                     "announcer", "device", "phone")

FACE_SPEAKS_NO_LIPSYNC = "FACE_SPEAKS_NO_LIPSYNC"
LIPSYNC_WRONG_FACE = "LIPSYNC_WRONG_FACE"
BELOW_BAND = "LIPSYNC_COVERAGE_BELOW_BAND"
TARGET_UNREACHABLE = "LIPSYNC_TARGET_UNREACHABLE"

OVERLAP_MIN_S = 0.25        # a boundary brush shorter than this is not "heard"
TARGET_MIN_S = 15.0         # lip-sync seconds in a 60-90 s ad ...
TARGET_MAX_S = 20.0         # ... the documented 15-20 s
GRACE_POINTS = 5.0          # +/- 5 points of runtime around the band
MIN_LINES = 3               # same floor as Part E E6


class FaceRuleError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _norm(v):
    return v.strip().lower() if isinstance(v, str) and v.strip() else None


def _lines(lines):
    """{line_id: {start,end,speaker,text}} from a map or a list of records
    (start/end or start_s/end_s). Fail closed on bad windows."""
    recs = lines.items() if isinstance(lines, dict) else (
        (r.get("line_id") or r.get("name"), r) for r in (lines or [])
        if isinstance(r, dict))
    out = {}
    for lid, r in recs:
        st = r.get("start", r.get("start_s"))
        en = r.get("end", r.get("end_s"))
        if not isinstance(lid, str) or not lid.strip() or not _num(st) \
                or not _num(en) or not st < en:
            raise FaceRuleError("BAD_LINE", "line %r needs id and ordered "
                                "start/end" % (lid,))
        out[lid] = {"start": float(st), "end": float(en),
                    "speaker": _norm(r.get("speaker")),
                    "text": r.get("text") if isinstance(r.get("text"), str)
                    else ""}
    return out


def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def speaking_face_rows(shots, lines):
    """One row per (shot, speaking face): the QC list.

    shots: [{shot_id, start, end (or song_start/song_end), faces_on_screen:
    [names], speaking_faces: [names] (optional), lip_sync_line_ids: [ids]
    (optional)}]. Row: {shot_id, start, end, speaker, line_id, text,
    lip_sync, ok, reason_code}.
    """
    ls = _lines(lines)
    rows = []
    for sh in shots:
        sid = sh.get("shot_id")
        st = sh.get("start", sh.get("song_start"))
        en = sh.get("end", sh.get("song_end"))
        if not _num(st) or not _num(en) or not st < en:
            raise FaceRuleError("BAD_SHOT", "shot %r needs an ordered window"
                                % (sid,))
        faces = {_norm(f) for f in sh.get("faces_on_screen") or [] if _norm(f)}
        lids = list(sh.get("lip_sync_line_ids") or [])
        for lid in lids:
            if lid not in ls:
                raise FaceRuleError("LIPSYNC_LINE_UNKNOWN",
                                    "shot %s lip-syncs unknown line %r"
                                    % (sid, lid))
        synced = set(lids)
        for lid in lids:               # a lip-sync clip needs its own face
            sp = ls[lid]["speaker"]
            if sp not in faces:
                rows.append({"shot_id": sid, "start": st, "end": en,
                             "speaker": sp, "line_id": lid,
                             "text": ls[lid]["text"], "lip_sync": True,
                             "ok": False, "reason_code": LIPSYNC_WRONG_FACE})
        covered = set()
        for lid, ln in sorted(ls.items(), key=lambda kv: kv[1]["start"]):
            if ln["speaker"] in faces and _person(ln["speaker"]) and \
                    _overlap(st, en, ln["start"], ln["end"]) > OVERLAP_MIN_S:
                ok = lid in synced
                covered.add(ln["speaker"])
                rows.append({"shot_id": sid, "start": st, "end": en,
                             "speaker": ln["speaker"], "line_id": lid,
                             "text": ln["text"], "lip_sync": ok, "ok": ok,
                             "reason_code": None if ok
                             else FACE_SPEAKS_NO_LIPSYNC})
        for f in sh.get("speaking_faces") or []:   # mouth moves in picture
            f = _norm(f)
            if f and f not in covered:
                ok = any(ls[l]["speaker"] == f for l in synced)
                rows.append({"shot_id": sid, "start": st, "end": en,
                             "speaker": f, "line_id": None, "text": "",
                             "lip_sync": ok, "ok": ok,
                             "reason_code": None if ok
                             else FACE_SPEAKS_NO_LIPSYNC})
    return rows


def check_face_speaks(shots, lines):
    """QC: {"pass", "reason_code", "rows", "failed"}; fails on any bad row."""
    rows = speaking_face_rows(shots, lines)
    bad = [r for r in rows if not r["ok"]]
    codes = sorted({r["reason_code"] for r in bad})
    return {"pass": not bad,
            "reason_code": "FACE_RULE_OK" if not bad else "+".join(codes),
            "rows": rows, "failed": bad,
            "detail": "; ".join("%s %.2f-%.2f s %s%s: %s" % (
                r["shot_id"], r["start"], r["end"], r["speaker"],
                " (%s)" % r["line_id"] if r["line_id"] else "",
                r["reason_code"]) for r in bad)}


def target_band_s(ad_length_s):
    """(target_min_s, target_max_s, grace_s) for one ad length.

    15-20 s from 60 to 90 s; scaled down below 60 s and up above 90 s so the
    share of runtime never drifts. grace = GRACE_POINTS of runtime.
    """
    if not _num(ad_length_s) or ad_length_s <= 0:
        raise FaceRuleError("BAD_INPUT", "ad_length_s must be positive")
    scale = ad_length_s / 60.0 if ad_length_s < 60 else (
        1.0 if ad_length_s <= 90 else ad_length_s / 90.0)
    return (TARGET_MIN_S * scale, TARGET_MAX_S * scale,
            GRACE_POINTS / 100.0 * ad_length_s)


def check_coverage_band(ad_length_s, lipsync_total_s, lipsync_lines_count):
    """QC measurement of the target. Fails only BELOW the band (target_min
    minus grace) or under MIN_LINES; above the band is reported, not failed
    (same stance as Part E E6)."""
    lo, hi, grace = target_band_s(ad_length_s)
    ev = {"ad_length_s": ad_length_s, "lipsync_total_s": lipsync_total_s,
          "lipsync_lines_count": lipsync_lines_count,
          "target_min_s": lo, "target_max_s": hi, "grace_s": grace,
          "band_low_s": lo - grace, "band_high_s": hi + grace,
          "share_pct": round(100.0 * lipsync_total_s / ad_length_s, 2),
          "in_band": lo - grace - 1e-9 <= lipsync_total_s <= hi + grace + 1e-9}
    ok = lipsync_total_s + 1e-9 >= lo - grace and lipsync_lines_count >= MIN_LINES
    return {"pass": ok, "reason_code": "LIPSYNC_BAND_OK" if ok else BELOW_BAND,
            "evidence": ev}


def plan_lipsync_lines(lines, ad_length_s, must_ids=()):
    """Pick which script lines become lip-sync clips so coverage hits the
    target. Candidates are lines spoken by a person on screen (never a
    narrator or device). must_ids (e.g. lines whose face is on screen) are
    taken first; then the longest remaining lines that keep the total at or
    below target_max, until the total reaches target_min and MIN_LINES.

    Returns {"pass", "reason_code", "selected" (timeline order), "total_s",
    "target_min_s", "target_max_s"}; TARGET_UNREACHABLE when the script does
    not carry enough own-face lines (the script needs more).
    """
    ls = _lines(lines)
    lo, hi, _ = target_band_s(ad_length_s)
    dur = {k: v["end"] - v["start"] for k, v in ls.items()}
    cand = {k for k, v in ls.items() if v["speaker"] and _person(v["speaker"])}
    picked = [k for k in must_ids if k in cand]
    total = sum(dur[k] for k in picked)
    for k in sorted(cand - set(picked), key=lambda k: -dur[k]):
        if total >= lo and len(picked) >= MIN_LINES:
            break
        if total + dur[k] <= hi + 1e-9:
            picked.append(k)
            total += dur[k]
    picked.sort(key=lambda k: ls[k]["start"])
    ok = total + 1e-9 >= lo and len(picked) >= MIN_LINES
    return {"pass": ok, "reason_code": "LIPSYNC_PLAN_OK" if ok
            else TARGET_UNREACHABLE, "selected": picked,
            "total_s": round(total, 3), "target_min_s": lo,
            "target_max_s": hi}
