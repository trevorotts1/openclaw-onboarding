#!/usr/bin/env python3
"""face_speaks.py: Part H H4 -- every speaking face is a lip-sync clip, and
lip-sync coverage hits a target band.

Evidence (Kiesett "Stop Stale" ad, 2026-10-08): 19 s of the 63 s ad showed a
character's face with a moving mouth while the words heard were not hers,
and only 9.6 s carried lip-sync against the then 15-20 s rule. Part E E6
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

2. COVERAGE TARGET (planner + QC): DOUBLED by owner order 2026-10-08. A 60 s
   ad carries 6-8 short lip-sync clips of 4-6 s each (30-40 s), scaled
   linearly with ad length; every clip is capped at 6 s. The numbers live in
   core/lipsync_clips.py (the single source). target_band_s() is the seconds
   band with the 5-point grace (GRACE_POINTS of runtime).
   plan_lipsync_lines() picks the clips: every sung hook, the spoken opener
   and the spoken closing line first (line "role": hook / opener / closing),
   then the longest remaining own-face lines, each cut to at most 6 s;
   check_coverage_band() is the QC measurement. Part E E6 floors follow the
   same numbers.

ponytail: the 5-point grace is a constant here; fold it into the G10
constants module when that lands on main.
"""
from __future__ import annotations

import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import lipsync_clips as _LC            # the one source of the clip numbers

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
TARGET_MIN_S = _LC.TOTAL_PER_REF_S[0]   # lip-sync seconds in a 60 s ad: 30 ...
TARGET_MAX_S = _LC.TOTAL_PER_REF_S[1]   # ... to 40 (was 15-20), scaled by L/60
CLIP_MAX_S = _LC.CLIP_MAX_S             # every clip is cut to at most 6 s
GRACE_POINTS = 5.0          # +/- 5 points of runtime around the band
MIN_LINES = _LC.MIN_CLIPS_FLOOR         # absolute floor; per-length in budget()


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

    30-40 s at 60 s, scaled linearly with the ad length (core/lipsync_clips).
    grace = GRACE_POINTS of runtime.
    """
    if not _num(ad_length_s) or ad_length_s <= 0:
        raise FaceRuleError("BAD_INPUT", "ad_length_s must be positive")
    b = _LC.budget(ad_length_s)
    return (b["total_min_s"], b["total_max_s"],
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
    min_clips = _LC.budget(ad_length_s)["min_clips"]
    ev["min_clips"] = min_clips
    ok = lipsync_total_s + 1e-9 >= lo - grace and lipsync_lines_count >= min_clips
    return {"pass": ok, "reason_code": "LIPSYNC_BAND_OK" if ok else BELOW_BAND,
            "evidence": ev}


def plan_lipsync_lines(lines, ad_length_s, must_ids=()):
    """Pick which script lines become lip-sync clips so coverage hits the
    target: MORE PIECES, NOT LONGER ONES (6-8 clips of 4-6 s per 60 s ad).

    Candidates are lines spoken by a person on screen (never a narrator or
    device). A clip is its line cut to at most CLIP_MAX_S (6 s). Taken first:
    must_ids and every line whose "role" is hook / opener / closing (the
    sung hooks, the spoken opener, the spoken closing line). Then the longest
    remaining lines (clips under 4 s last) until the total reaches target_min
    and the clip count reaches min_clips, never passing max_clips or
    target_max.

    Returns {"pass", "reason_code", "selected" (timeline order),
    "clip_s" ({id: seconds}), "total_s", "clips", "target_min_s",
    "target_max_s", "min_clips", "max_clips"}; TARGET_UNREACHABLE when the
    script does not carry enough own-face lines (the script needs more).
    """
    ls = _lines(lines)
    b = _LC.budget(ad_length_s)
    lo, hi = b["total_min_s"], b["total_max_s"]
    dur = {k: min(v["end"] - v["start"], CLIP_MAX_S) for k, v in ls.items()}
    cand = {k for k, v in ls.items() if v["speaker"] and _person(v["speaker"])}
    roles = {r.get("line_id") or r.get("name"): r.get("role")
             for r in (lines if not isinstance(lines, dict) else [])
             if isinstance(r, dict)}
    first = [k for k in list(must_ids) + sorted(
        (k for k in cand if roles.get(k) in _LC.PRIORITY_ROLES),
        key=lambda k: ls[k]["start"]) if k in cand]
    picked = []
    for k in first:
        if k not in picked and len(picked) < b["max_clips"] and \
                sum(dur[x] for x in picked) + dur[k] <= hi + 1e-9:
            picked.append(k)
    total = sum(dur[k] for k in picked)
    rest = sorted(cand - set(picked),
                  key=lambda k: (dur[k] < _LC.CLIP_MIN_S, -dur[k]))
    for k in rest:
        if total >= lo and len(picked) >= b["min_clips"]:
            break
        if len(picked) < b["max_clips"] and total + dur[k] <= hi + 1e-9:
            picked.append(k)
            total += dur[k]
    picked.sort(key=lambda k: ls[k]["start"])
    ok = total + 1e-9 >= lo and len(picked) >= b["min_clips"]
    return {"pass": ok, "reason_code": "LIPSYNC_PLAN_OK" if ok
            else TARGET_UNREACHABLE, "selected": picked,
            "clip_s": {k: round(dur[k], 3) for k in picked},
            "total_s": round(total, 3), "clips": len(picked),
            "target_min_s": lo, "target_max_s": hi,
            "min_clips": b["min_clips"], "max_clips": b["max_clips"]}
