#!/usr/bin/env python3
"""choose_window: phrase-boundary cut with 0.30 s / 0.20 s padding, 4-6 s total,
onset density, no held word, lip-friendly words, a different line per clip. $0.
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


# 10 quick words (~0.45 s each), a rest, then 4 slow held words
FAST = [("we", .4, .02), ("walk", .4, .02), ("the", .4, .02), ("long", .4, .02),
        ("road", .4, .02), ("home", .4, .02), ("to", .4, .02), ("you", .4, .02),
        ("and", .4, .02), ("me", .4, .5)]
SLOW = [("ohh", 1.8, .1), ("mine", 1.6, .1), ("ohh", 1.9, .1), ("home", 1.7, .1)]


def test_window_is_4_to_6_seconds_padded_at_word_edges():
    w = words(FAST + SLOW)
    c = C.choose_window(w)
    assert 4.0 - 1e-6 <= c["dur"] <= 6.0 + 1e-6, c
    starts = {x["start"] for x in w}
    ends = {x["end"] for x in w}
    assert c["start"] in starts and c["end"] in ends          # phrase boundaries
    assert abs((c["end"] - c["start"]) + C.PRE_S + C.TAIL_S - c["dur"]) < 1e-3
    assert (C.PRE_S, C.TAIL_S) == (0.30, 0.20)
    assert abs(c["pad_end"] - (c["end"] + 0.20)) < 1e-9


def test_prefers_dense_onsets_over_held_notes():
    c = C.choose_window(words(FAST + SLOW))
    assert c["onsets_per_s"] >= C.MIN_ONSETS_PER_S and c["held_s"] <= C.MAX_HELD_WORD_S
    assert "HELD_NOTE" not in c["flags"]
    assert c["start"] < 4.0                                    # inside the fast part


def test_all_held_notes_picks_the_shortest_and_marks_it():
    c = C.choose_window(words(SLOW))
    assert "HELD_NOTE" in c["flags"] and c["held_s"] > C.MAX_HELD_WORD_S
    assert "SPARSE_ONSETS" in c["flags"]


def test_prefers_p_b_m_f_v_w_words_all_else_equal():
    plain = [("sun", .5, .0), ("sky", .5, .0), ("sea", .5, .0), ("rain", .5, .0),
             ("star", .5, .0), ("star", .5, .0), ("sun", .5, .0), ("sky", .5, .0),
             ("sea", .5, .6)]
    lipsy = [("mom", .5, .0), ("baby", .5, .0), ("moon", .5, .0), ("free", .5, .0),
             ("very", .5, .0), ("wind", .5, .0), ("map", .5, .0), ("buy", .5, .0),
             ("fire", .5, .0)]
    c = C.choose_window(words(plain, 0) + words(lipsy, 12))
    assert c["start"] >= 12 and c["lip_words"] >= 6, c


def test_cuts_at_a_real_rest_when_one_exists():
    c = C.choose_window(words(FAST + FAST))
    w = words(FAST + FAST)
    gaps = {x["start"] for i, x in enumerate(w) if i == 0 or x["start"] - w[i - 1]["end"] >= C.MIN_REST_S}
    assert c["start"] in gaps


def test_different_line_per_clip_for_a_repeated_hook():
    hook = [("ohh", .4, .0), ("my", .4, .0), ("love", .4, .0), ("is", .4, .0),
            ("home", .4, .0), ("again", .4, .0), ("now", .4, .0), ("hold", .4, .0),
            ("me", .4, .0), ("close", .4, .0), ("sing", .4, .0), ("it", .4, .0)]
    w = words(hook + [("x", .1, 1.0)] + hook[::-1])
    first = C.choose_window(w)
    second = C.choose_window(w, used_lines=(first["words"],))
    assert second["words"] != first["words"]


def test_start_of_track_clamps_pre_roll_and_bad_input_refused():
    c = C.choose_window(words([("ah", .5, .02)] * 9))
    assert c["pad_start"] >= 0.0
    for bad in ([], [{"word": "x", "start": 1.0, "end": 1.0}]):
        try:
            C.choose_window(bad)
        except C.LipsyncClipsError as e:
            assert e.code == C.BAD_PLAN
        else:
            raise AssertionError
    try:
        C.choose_window(words([("hi", .5, .0)] * 3))           # only 1.5 s of words
    except C.LipsyncClipsError as e:
        assert e.code == C.BAD_PLAN
    else:
        raise AssertionError("a window under 4 s was returned")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("ALL CHECKS PASS")
