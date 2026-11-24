#!/usr/bin/env python3
"""choose_window: the piece is the WHOLE line, 5-30 s, never cut (N-101);
a held note is a receipt flag; a passage over 30 s stitches at a breath
(N-112). $0.
Run: python3 scripts/core/test_choose_window.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lipsync_clips as C                              # noqa: E402


def words(spec, t0=0.0):
    """spec: [(word, dur, gap_after)] -> Suno-style stamps."""
    out, t = [], t0
    for w, d, g in spec:
        out.append({"word": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d + g
    return out


# 12 quick words (~0.5 s each) = ~6 s: one whole line.
FAST = [("we", .48, .02)] * 12
# Four held words of ~2 s: one whole line, held note flagged.
HELD = [("ohh", 2.0, .1), ("mine", 1.8, .1), ("ohh", 2.0, .1), ("home", 1.9, .1)]


def raises(code, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except C.LipsyncClipsError as e:
        assert e.code == code, e.code
        return
    raise AssertionError("did not refuse")


def test_the_whole_line_is_the_piece():
    w = words(FAST)
    c = C.choose_window(w)
    span = w[-1]["end"] - w[0]["start"]
    assert c["start"] == w[0]["start"] and c["end"] == w[-1]["end"]
    assert abs(c["audio_s"] - span) < 1e-3
    assert abs(c["dur"] - (span + C.PRE_S + C.TAIL_S)) < 1e-3
    assert c["whole_sentence"] is True and c["counts_as"] == 1
    assert c["stitch"] is False
    assert abs(c["pad_end"] - (c["end"] + C.TAIL_S)) < 1e-9
    assert "HELD_NOTE" not in c["flags"] and c["held_s"] <= C.MAX_HELD_WORD_S
    assert c["lip_words"] == 12, c                                   # every "we" is lip-friendly


def test_held_note_and_slow_passage_are_flags_only():
    c = C.choose_window(words(HELD))          # 7.7 s
    assert "HELD_NOTE" in c["flags"] and "SLOW_ONSETS" in c["flags"]
    assert c["held_s"] == 2.0 and c["onsets_per_s"] < C.MIN_ONSETS_PER_S
    assert c["start"] == 0.0 and c["audio_s"] > 7.0


def test_under_five_seconds_refused_not_trimmed():
    raises(C.AUDIO_TOO_SHORT, C.choose_window, words([("hi", .5, .0)] * 5))


def test_over_thirty_seconds_refused_to_the_stitch():
    raises(C.AUDIO_TOO_LONG, C.choose_window, words(FAST * 6))


def test_bad_input_and_anchor_clamp():
    raises(C.BAD_PLAN, C.choose_window, [])
    raises(C.BAD_PLAN, C.choose_window,
           [{"word": "x", "start": 1.0, "end": 1.0}])
    c = C.choose_window(words(FAST), pre=5.0)
    assert c["pad_start"] == 0.0
    assert abs(c["pad_end"] - (c["end"] + C.TAIL_S)) < 1e-9
    assert (C.PRE_S, C.TAIL_S) == (0.30, 0.20)


def test_stitch_group_splits_at_a_breath_and_counts_once():
    # Two ~21 s runs with a 1.5 s breath: over the 30 s top -> two pieces.
    run = [("hold", 2.0, .1)] * 10
    passage = words(run) + words(run, 22.5)
    g = C.plan_stitch_passage(passage)
    assert g["counts_as"] == 1 and len(g["pieces"]) == 2, g
    assert all(C.CLIP_MIN_S - 1e-6 <= p["audio_s"]
               <= C.CLIP_MAX_S + 1e-6 for p in g["pieces"])
    assert g["joins"] and g["joins"][0]["kind"] == "breath"


def test_short_passage_is_one_piece():
    g = C.plan_stitch_passage(words(FAST))
    assert len(g["pieces"]) == 1 and g["joins"] == [] and g["counts_as"] == 1


def test_over_thirty_with_no_breath_refused():
    raises(C.STITCH_NOT_ALLOWED, C.split_stitch_group,
           words([("go", .5, .0)] * 70))


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
