#!/usr/bin/env python3
"""FU-U3 (plan unit U3): bands per music style; rap is its own delivery;
silence is not speech.

Plan 18-OPUS-SKILL75-FUTURE-PLAN section 7, unit row U3. Proves:

  (a) a MUSIC-ONLY gap no longer counts as spoken in sung-of-voice -- the
      legacy builder labeled every non-sung second "spoken", so the intro,
      gaps and the end card deflated the sung share of voice (today they do;
      `segments_from_sung_stretches(..., voiced=)` turns them into "none",
      which counts in runtime and never in voice time);
  (b) the R&B Flow judge on the g1b fixture is NOT FAIL by construction when
      the take matches its approved plan -- plan 18 section 9 item 1
      (R&B Flow targets) is a TREVOR-DECISION ITEM and this unit uses the
      DOCUMENTED DEFAULT: the target = the share planned from the approved
      sheet (the U2 plan's word counts at the style's measured rates),
      judged with Trevor's unchanged 5/10 band; plain spoken (not rap)
      keeps the 22.5% runtime target; rap is its own delivery; the 6 s sung
      stretch and the hook count stay hard. NO new number is invented here;
      sung-of-voice on a rap sheet is RECORDED, not gated (its sung content
      is the hook, which no word count can plan -- a 77.5 gate on it would
      be FAIL by construction for a different reason than the bands);
  (c) the soul-ballad verdicts on the existing BSW fixtures are UNCHANGED
      (pinned from the base tree before this unit's change).

The g1b segment fixture is the delivered One-Check Chanel 150 s take:
the sung stretches in song/SONG-RECEIPT.md (3-13, 24-25, 84-89, 108-117,
127-133, 141-148), voiced time from the measured Suno word timestamps of
take g1b, and the rap-versus-speech split = measured word timestamps x the
sheet's own delivery labels, recorded as basis "aligned", NEVER "measured".

LOCKED (asserted, never changed by this unit): the 5/10 band
(spoken_share.ACCEPT_PTS / FLAG_PTS), Soul Ballad and Soul Rise targets
exactly 22.5 runtime spoken / 77.5 sung-of-voice, and the 6 s sung stretch
as the only hard singing reject.

Run: python3 core/spoken_share/test_style_bands_u3.py
stdlib only, no network, no spend.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

import spoken_share as SS                     # noqa: E402
import song_dispatch as SD                    # noqa: E402
import suno_recipe as R                       # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------------------
# The g1b fixture: SONG-RECEIPT sung stretches + measured word timestamps.
# ---------------------------------------------------------------------------
G1B_SUNG = [(3, 13), (24, 25), (84, 89), (108, 117), (127, 133), (141, 148)]
G1B_VOCED = [(2.87, 148.28)]          # union of the take's aligned word times
G1B_DURATION_S = 150.0                # the delivered file (trimmed take)
#: (start, end, delivery) runs of the take's aligned words x the sheet labels.
G1B_ALIGN_RUNS = [
    (2.87, 8.38, "spoken"), (8.38, 10.93, "sung"), (10.94, 23.78, "rap"),
    (23.78, 25.85, "sung"), (25.86, 40.94, "rap"), (40.94, 43.01, "sung"),
    (43.09, 58.01, "rap"), (58.01, 59.76, "sung"), (59.76, 86.57, "rap"),
    (86.58, 88.49, "sung"), (88.49, 107.96, "rap"), (107.96, 116.37, "sung"),
    (116.82, 130.78, "rap"), (130.78, 133.22, "sung"), (133.23, 148.28, "spoken"),
]
#: The approved One-Check sheet (U1 counts: spoken 24, rap 254, sung 25) --
#: this IS the approved plan the take was cut to; its planned shares come
#: from words_fit's measured rates for rnb-flow, never from a new constant.
G1B_APPROVED_PLAN = {
    "chosen_length_s": 152, "delivered_s": G1B_DURATION_S,
    "words": {"spoken": 24, "rap": 254, "sung": 25, "total": 303},
}
#: Aligned words the judge needs: the client hook x4 (times from
#: SONG-RECEIPT) and the intro script line, as the aligner delivered them.
G1B_ALIGNED_WORDS = []
for _t in (23.78, 86.58, 107.96, 130.78):
    for _i, _w in enumerate(("Girl,", "I", "got", "you-", "u")):
        G1B_ALIGNED_WORDS.append({"word": _w, "startS": round(_t + _i * 0.1, 3),
                                  "endS": round(_t + _i * 0.1 + 0.1, 3)})
G1B_ALIGNED_WORDS += [
    {"word": "Of", "startS": 4.0, "endS": 4.2},
    {"word": "course.", "startS": 4.3, "endS": 4.6},
]


def build_g1b_segments():
    """The g1b segment fixture: detector sung stretches (measured) on the
    voiced timeline, non-sung voice split by the aligned word runs (rap /
    spoken, source "aligned"), music-only time "none"."""
    base = SS.segments_from_sung_stretches(G1B_SUNG, G1B_DURATION_S,
                                           detector_version="2.0.0",
                                           stem_id="g1b",
                                           voiced=G1B_VOCED)
    out = []
    for seg in base:
        if seg["delivery"] == "sung":
            out.append(seg)
            continue
        a, b = seg["start"], seg["end"]
        pos = a
        for ra, rb, rd in G1B_ALIGN_RUNS:
            if rb <= pos or ra >= b:
                continue
            if ra > pos:
                out.append(dict(seg, start=pos, end=min(ra, b)))
            lo, hi = max(pos, ra), min(rb, b)
            if hi > lo:
                if rd == "sung":
                    out.append(dict(seg, delivery="sung", start=lo, end=hi))
                else:
                    out.append(dict(seg, delivery=rd, source="aligned",
                                    start=lo, end=hi))
            pos = max(pos, hi)
            if pos >= b:
                break
        if pos < b:
            out.append(dict(seg, start=pos, end=b))
    merged = []
    for s in sorted(out, key=lambda x: (x["start"], x["end"])):
        if s["end"] <= s["start"]:
            continue
        if (merged and merged[-1]["delivery"] == s["delivery"]
                and merged[-1]["source"] == s["source"]
                and s["start"] - merged[-1]["end"] <= 0.011):
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)
    return merged


# ---------------------------------------------------------------------------
# (a) a music-only gap is not speech
# ---------------------------------------------------------------------------
def test_a_music_only_gap_is_not_spoken():
    # one sung block, voice only in [0, 52): 0-10 spoken, 10-50 sung,
    # 50-52 spoken, 52-60 music only.
    with_voiced = SS.segments_from_sung_stretches(
        [(10, 50)], 60.0, voiced=[(0.0, 52.0)])
    m = SS.measure_share(with_voiced)
    check("(a) music-only seconds are delivery 'none', not spoken",
          m["none_seconds"] == 8.0 and m["spoken_seconds"] == 12.0,
          "none=%s spoken=%s" % (m["none_seconds"], m["spoken_seconds"]))
    sov = SS.check_sung_of_voice(with_voiced)
    # sung 40 / (40 + 12 spoken) = 76.9% -> within 5 of 77.5: PASS.
    check("(a) sung-of-voice ignores the music-only gap (PASS)",
          sov["verdict"] == "PASS", "%s %s" % (sov["verdict"],
                                               sov.get("sung_of_voice_pct")))
    # today's behavior: without voiced= the gap is spoken and the same cut
    # is FAIL -- the gap used to count as speech.
    legacy = SS.segments_from_sung_stretches([(10, 50)], 60.0)
    m2 = SS.measure_share(legacy)
    sov2 = SS.check_sung_of_voice(legacy)
    check("(a) legacy builder (no voiced) still counts the gap as spoken",
          m2["spoken_seconds"] == 20.0 and sov2["verdict"] == "FAIL",
          "spoken=%s sov=%s" % (m2["spoken_seconds"], sov2["verdict"]))


# ---------------------------------------------------------------------------
# (b) R&B Flow judge on the g1b fixture vs the approved plan
# ---------------------------------------------------------------------------
def test_b_rnb_judge_not_fail_by_construction():
    segs = build_g1b_segments()
    basis = SS.segment_basis(segs)
    check("(b) g1b fixture basis is 'aligned', never 'measured'",
          basis == "aligned", repr(basis))
    m = SS.measure_share(segs, basis, style_id="rnb-flow")
    check("(b) rap is reported as its own delivery (share %)"
          .replace("%", ""), m["rap_share_pct"] > 40,
          "rap_share_pct=%s" % m["rap_share_pct"])
    check("(b) music-only head/tail counted as none, not speech",
          m["none_seconds"] > 1.5, "none=%s" % m["none_seconds"])

    take = {
        "segments": segs, "detector": "singing_detector 2.0.0",
        "duration_s": G1B_DURATION_S, "music_under_speech_ratio": 0.92,
        "tail_rms_dbfs": -42.1, "first_sung_s": 3.0,
        "aligned_words": G1B_ALIGNED_WORDS,
    }
    script = "Of course."
    j = SD.judge_take(take, G1B_APPROVED_PLAN, script, "Girl, I got you-u",
                      None, "rnb-flow")
    band_gates = ("spoken_share", "rap_share", "sung_of_voice")
    bad = [g for g in band_gates if j["gates"][g]["verdict"] == "FAIL"]
    # The sheet-dependent gates (FU-RNBFLOW-SONG song_contract, FU-HOOK-PLACEMENT
    # hook_placement) need the approved sheet text and hook_plan, which this band
    # fixture does not carry: they must fail CLOSED as UNMEASURED, and nothing
    # else may fail. Their own tests cover them with a real sheet.
    sheet_gates = ("song_contract", "hook_placement")
    check("(b) without a sheet the song-contract and hook-placement gates fail closed (UNMEASURED)",
          all("UNMEASURED" in j["gates"][g]["detail"] for g in sheet_gates)
          and set(j["failed"]) <= set(sheet_gates), repr(j["failed"]))
    check("(b) the R&B Flow judge is not FAIL when the take matches its "
          "approved plan", not [g for g in j["failed"] if g not in sheet_gates] and not bad,
          "verdict=%s failed=%s band=%s" % (j["verdict"], j["failed"],
                                            {g: j["gates"][g] for g in band_gates}))
    check("(b) spoken_share judged against the approved plan's planned share "
          "(documented default, no new number)",
          "approved plan" in j["gates"]["spoken_share"]["detail"],
          j["gates"]["spoken_share"]["detail"])
    check("(b) sung-of-voice is recorded, not gated, for a rap sheet",
          j["gates"]["sung_of_voice"]["verdict"] != "FAIL"
          and "recorded" in j["gates"]["sung_of_voice"]["detail"],
          j["gates"]["sung_of_voice"]["detail"])
    check("(b) the 6 s sung stretch stays hard and passes here",
          j["gates"]["sung_stretch"]["verdict"] == "PASS",
          j["gates"]["sung_stretch"]["detail"])
    st = R.score_take({"segments": segs}, style_id="rnb-flow",
                      plan=G1B_APPROVED_PLAN, length_s=G1B_DURATION_S)
    check("(b) suno_recipe.score_take with style+plan is not FAIL",
          st["verdict"] != "FAIL",
          "%s %s" % (st["verdict"], st["reasons"]))
    check("(b) score_take records basis 'aligned'", st.get("basis") == "aligned",
          repr(st.get("basis")))

    # a take that does NOT match its plan still fails: plain spoken blown
    # way past the plan (band unchanged).
    loud = [dict(s, start=s["start"], end=s["end"])
            for s in segs if s["delivery"] in ("spoken", "rap", "sung", "none")]
    for s in loud:
        if s["delivery"] == "rap":
            s["delivery"] = "spoken"
        if s["delivery"] == "sung":
            s["delivery"] = "spoken"
    loud[0] = {"delivery": "spoken", "start": 0, "end": 140, "source": "measured"}
    loud[1] = {"delivery": "sung", "start": 140, "end": 150, "source": "measured"}
    j2 = SD.judge_take(dict(take, segments=loud[:2]),
                       G1B_APPROVED_PLAN, script, "Girl, I got you-u",
                       None, "rnb-flow")
    check("(b) a take far from the plan is still FAIL (band bites)",
          j2["verdict"] == "FAIL" and "spoken_share" in j2["failed"],
          "%s %s" % (j2["verdict"], j2["failed"]))


# ---------------------------------------------------------------------------
# (c) soul-ballad verdicts on the existing BSW fixtures: UNCHANGED
# ---------------------------------------------------------------------------
#: Pinned on the BASE tree (origin/unit/FU-U2) before this unit's change.
BASE_BSW = {
    "bsw58": {"L": 58, "share_pct": 30.4, "check_share": "FLAG",
              "sung_of_voice": "FLAG", "sung_of_voice_pct": 69.565,
              "real_singing": "PASS", "check_plan": "FLAG",
              "first_sung": "PASS"},
    "short60": {"L": 60, "share_pct": 91.7, "check_share": "FAIL",
                "sung_of_voice": "FAIL", "sung_of_voice_pct": 8.333,
                "real_singing": "FAIL", "check_plan": "FAIL",
                "first_sung": "FAIL"},
    "six60": {"L": 60, "share_pct": 90.0, "check_share": "FAIL",
              "sung_of_voice": "FAIL", "sung_of_voice_pct": 10.0,
              "real_singing": "PASS", "check_plan": "FAIL",
              "first_sung": "FAIL"},
    "good90": {"L": 90, "share_pct": 22.5, "check_share": "PASS",
               "sung_of_voice": "PASS", "sung_of_voice_pct": 77.5,
               "real_singing": "PASS", "check_plan": "PASS",
               "first_sung": "PASS"},
    "late90": {"L": 90, "share_pct": 44.4, "check_share": "FAIL",
               "sung_of_voice": "FAIL", "sung_of_voice_pct": 55.556,
               "real_singing": "PASS", "check_plan": "FAIL",
               "first_sung": "FAIL"},
}
BSW_FIXTURES = {
    "bsw58": ([{"delivery": "spoken", "start": 0, "end": 8, "source": "measured"},
               {"delivery": "sung", "start": 8, "end": 48, "source": "measured"},
               {"delivery": "spoken", "start": 48, "end": 57.5, "source": "measured"}]),
    "short60": ([{"delivery": "spoken", "start": 0, "end": 20, "source": "measured"},
                 {"delivery": "sung", "start": 20, "end": 25, "source": "measured"},
                 {"delivery": "spoken", "start": 25, "end": 60, "source": "measured"}]),
    "six60": ([{"delivery": "spoken", "start": 0, "end": 20, "source": "measured"},
               {"delivery": "sung", "start": 20, "end": 26, "source": "measured"},
               {"delivery": "spoken", "start": 26, "end": 60, "source": "measured"}]),
    "good90": ([{"delivery": "spoken", "start": 0, "end": 13.5, "source": "measured"},
                {"delivery": "sung", "start": 13.5, "end": 19.5, "source": "measured"},
                {"delivery": "rap", "start": 19.5, "end": 26.25, "source": "measured"},
                {"delivery": "sung", "start": 26.25, "end": 90, "source": "measured"}]),
    "late90": ([{"delivery": "spoken", "start": 0, "end": 40, "source": "measured"},
                {"delivery": "sung", "start": 40, "end": 90, "source": "measured"}]),
}


def test_c_soul_bsw_verdicts_unchanged():
    for name, segs in BSW_FIXTURES.items():
        want = BASE_BSW[name]
        m = SS.measure_share(segs)
        p = SS.check_plan(want["L"], segs)
        got = {
            "share_pct": m["share_pct"],
            "check_share": SS.check_share(m["share"], segs)["verdict"],
            "sung_of_voice": SS.check_sung_of_voice(segs)["verdict"],
            "sung_of_voice_pct": SS.check_sung_of_voice(segs)["sung_of_voice_pct"],
            "real_singing": SS.check_real_singing(segs)["verdict"],
            "check_plan": p["verdict"],
            "first_sung": p["first_sung"]["verdict"],
        }
        for k, v in want.items():
            if k == "L":
                continue
            check("(c) %s %s unchanged" % (name, k), got[k] == v,
                  "%r vs base %r" % (got[k], v))


def test_locked_rules_hold():
    check("LOCKED: band is 5/10 (ACCEPT_PTS/FLAG_PTS)",
          SS.ACCEPT_PTS == 5 and SS.FLAG_PTS == 10,
          "%s/%s" % (SS.ACCEPT_PTS, SS.FLAG_PTS))
    check("LOCKED: 6 s sung stretch is the only hard singing reject",
          SS.NO_REAL_SINGING_STRETCH_S == 6.0,
          repr(SS.NO_REAL_SINGING_STRETCH_S))
    for sid in ("soul-ballad", "soul-rise"):
        t = SS.style_targets(sid)
        check("LOCKED: %s targets stay 22.5 / 77.5" % sid,
              t["spoken_pct"] == 22.5 and t["sung_of_voice_pct"] == 77.5,
              repr(t))
    check("STYLE_TARGETS names the three offered styles",
          set(SS.STYLE_TARGETS) == {"soul-ballad", "soul-rise", "rnb-flow"},
          repr(sorted(SS.STYLE_TARGETS)))
    check("unknown style falls back to the default targets (fail closed)",
          SS.style_targets("no-such-style") == SS.style_targets("soul-ballad"),
          repr(SS.style_targets("no-such-style")))


def main():
    test_a_music_only_gap_is_not_spoken()
    test_b_rnb_judge_not_fail_by_construction()
    test_c_soul_bsw_verdicts_unchanged()
    test_locked_rules_hold()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
