#!/usr/bin/env python3
"""WFWWU1-U3 acceptance tests: WW-02 (story start on the approved plot LINE +
the absolute OPENING_VOCALISE_MAX_S ceiling), WW-05 (in-bounds, voice-
intersected lexical coverage compared RAW + the separate 0.98 text floor),
WW-04 (one physical timeline: the module half in timing_guard + spoken_share),
WW-13 (the words figure and the music-only figure under separate labels) and
WW-17 (first_sung measured on the approved story-bearing line, the owner's 5/10
band recorded separately).

Every threshold here is a NEW ACCEPTANCE RULE from the WW-prevent-recurrence
specification; OPENING_VOCALISE_MAX_S = 3.0 and TEXT_COVERAGE_MIN = 0.98 are
marked NEW PROPOSED in that specification and are never attributed to the owner.

Every fixture is INLINE (no evidence tree, no media, no network): pure
functions over synthetic rows. Zero paid calls.

Run: python3 core/story_coverage/test_story_lexical_timeline.py
"""
from __future__ import annotations

import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import story_coverage as SV                     # noqa: E402
import spoken_share.spoken_share as SS          # noqa: E402
import timing_guard as TG                       # noqa: E402

#: The failed run's sheet, verbatim in the parts the story gate reads: a spoken
#: filler opener, a long wordless vocalise, then the first rap (story) line.
STORED_SHEET = "\n".join([
    "[Intro (spoken): close dry voice, plain speech, no melody]",
    "I'm still up",
    "",
    "[Vocalise (sung): wordless, full melodic voice, two very long held notes]",
    "Oo-oh, oo-oh",
    "",
    "[Verse 1 (rap): rhythmic rap on the beat, tight metered flow, clear diction]",
    "I keep meeting the same man in a new face",
])

#: The failed take's aligned rows 0-9, verbatim from
#: run/music/takes/v1-polished-modern/lyrics/take1/aligned-words.json.
STORED_ROWS = [
    {"word": "[Intro (spoken): close dry voice, plain speech, no melody]\nI'm ",
     "startS": 3.75, "endS": 3.989},
    {"word": "still ", "startS": 4.037, "endS": 4.229},
    {"word": "up\n\n", "startS": 4.3485, "endS": 8.2988},
    {"word": "[Vocalise (sung): wordless, full melodic voice, two very long held notes]\nOo-oh, ",
     "startS": 8.37959, "endS": 22.037},
    {"word": "oo-oh\n\n", "startS": 22.053, "endS": 22.105},
    {"word": "[Verse 1 (rap): rhythmic rap on the beat, tight metered flow, clear diction]\nI ",
     "startS": 22.107, "endS": 22.261},
    {"word": "keep ", "startS": 22.34075, "endS": 22.58},
    {"word": "meeting ", "startS": 22.61975, "endS": 22.899},
    {"word": "the ", "startS": 22.97867, "endS": 23.138},
    {"word": "same ", "startS": 23.21775, "endS": 23.457},
]

STORED_D = 88.032
STORED_PLOT = [["i", "keep", "meeting", "the", "same", "man", "in", "a", "new", "face"]]
#: An approved plot line matching the synthetic boundary rows.
DUMMY_PLOT = [["one", "closed", "door", "seed"]]

FAILURES = []


def check(cond, label):
    if cond:
        print("ok   %s" % label)
    else:
        print("FAIL %s" % label)
        FAILURES.append(label)


def _rows(items):
    return [{"word": w, "startS": s, "endS": e} for (w, s, e) in items]


def _plot_at(start_s, words=("one", "closed", "door", "seed")):
    return [(w, start_s + i * 0.4, start_s + i * 0.4 + 0.3)
            for i, w in enumerate(words)]


# ---- WW-02: story start + the absolute opening-vocalise ceiling ------------

class WW02StoryStart(unittest.TestCase):

    def test_absolute_five_second_line_ceiling_is_a_run_not_a_vocabulary(self):
        # opening wordless span stays 2.5 s so ONLY the line ceiling is judged
        rows = _rows([("filler", 0.0, 2.5)] + _plot_at(5.000))
        g = SV.story_start_gate(rows, DUMMY_PLOT, 58.0)
        check(g["verdict"] == "PASS" and g["first_plot_line_s"] == 5.0,
              "WW-02: an approved plot LINE at exactly 5.000 s passes")
        rows = _rows([("filler", 0.0, 2.5)] + _plot_at(5.001))
        g = SV.story_start_gate(rows, DUMMY_PLOT, 58.0)
        check(g["verdict"] == "FAIL" and "FIRST_STORY_WORD_LATE" in g["failed"],
              "WW-02: the same line at 5.001 s FAILS (absolute 5.0 s ceiling)")

    def test_absolute_three_second_opening_vocalise_ceiling(self):
        # plot line at 4.0 s (within the 5.0 s ceiling); only the opening span judged
        body = _plot_at(4.0)
        ok = _rows([("filler", 0.0, 1.0)] + body)        # opening gap = 3.000 s
        g = SV.story_start_gate(ok, DUMMY_PLOT, 58.0)
        check(g["verdict"] == "PASS" and g["opening_wordless_s"] == 3.0,
              "WW-02: a 3.000 s opening wordless span passes")
        bad = _rows([("filler", 0.0, 0.999)] + body)     # opening gap = 3.001 s
        g = SV.story_start_gate(bad, DUMMY_PLOT, 58.0)
        check("OPENING_VOCALISE_TOO_LONG" in g["failed"],
              "WW-02: a 3.001 s opening wordless span FAILS (absolute 3.0 s ceiling)")

    def test_stored_take_is_refused(self):
        g = SV.story_start_gate(STORED_ROWS, SV.plot_lines_from_sheet(STORED_SHEET),
                                STORED_D)
        check(g["verdict"] == "FAIL"
              and "FIRST_STORY_WORD_LATE" in g["failed"]
              and "OPENING_VOCALISE_TOO_LONG" in g["failed"],
              "WW-02: the stored take (story line 22.107 s, vocalise 8.37959-22.037) "
              "is refused (%r)" % (g["failed"],))
        check(g["first_plot_line_s"] == 22.107,
              "WW-02: the stored first plot line is measured at 22.107 s")
        check(g["opening_wordless_s"] > 3.0,
              "WW-02: the stored opening wordless span %s s exceeds 3.0 s"
              % g["opening_wordless_s"])

    def test_four_repeated_filler_tokens_are_not_the_plot_line(self):
        plot = [["i", "keep", "meeting", "the", "same", "man"]]
        rows = _rows([("i", 0.0, 0.3), ("i", 0.4, 0.7),
                      ("i", 0.8, 1.1), ("i", 1.2, 1.5), ("i", 1.6, 1.9)])
        g = SV.story_start_gate(rows, plot, 58.0)
        check(g["verdict"] == "FAIL" and "NO_PLOT_LINE_SUNG" in g["failed"],
              "WW-02: four repeated filler tokens are not the approved plot line "
              "(the old membership matcher read 1.0 s)")

    def test_the_old_opening_measurement_is_replaced_not_kept(self):
        check(not hasattr(SV, "opening_non_lexical_s")
              and not hasattr(SV, "OPENING_NON_LEXICAL_MAX_SHARE"),
              "WW-02: opening_non_lexical_s and its share rule are REPLACED")
        check(hasattr(SV, "OPENING_VOCALISE_MAX_S")
              and SV.OPENING_VOCALISE_MAX_S == 3.0
              and hasattr(SV, "longest_opening_wordless_s"),
              "WW-02: OPENING_VOCALISE_MAX_S = 3.0 (NEW PROPOSED) is defined")

    def test_vocalise_with_punctuation_is_not_lexical(self):
        check(SV.is_vocalise("Oo-oh,") and not SV.is_lexical("Oo-oh,"),
              "WW-02: the stored vocalise 'Oo-oh,' is not a lexical word")


# ---- WW-05: in-bounds voice-intersected lexical coverage --------------------

class WW05LexicalCoverage(unittest.TestCase):

    def test_malformed_far_out_of_range_interval_is_refused(self):
        bad = _rows([("count", 100.0, 200.0)])          # 100-200 s over 88.032 s
        g = SV.lexical_coverage_gate(bad, 88.032)
        check(g["verdict"] == "FAIL",
              "WW-05: a 100-200 s interval over 88.032 s audio is refused "
              "(coverage_raw=%s)" % g["coverage_raw"])

    def test_raw_comparison_at_the_seventy_percent_boundary(self):
        D = 88.032
        owed = 0.70 * D                                  # 61.6224 s
        ok = _rows([("count", 0.0, owed)])
        g = SV.lexical_coverage_gate(ok, D)
        check(g["verdict"] == "PASS" and abs(g["coverage_raw"] - 0.70) < 1e-9,
              "WW-05: exactly 70.00%% passes (raw comparison)")
        just_below = _rows([("count", 0.0, owed - 0.001)])
        g = SV.lexical_coverage_gate(just_below, D)
        check(g["verdict"] == "FAIL",
              "WW-05: 0.001 s below the floor FAILS (no pre-rounding to 0.70)")

    def test_union_is_intersected_with_the_measured_voice(self):
        words = _rows([("count", 0.0, 10.0)])
        check(SV.lexical_seconds(words, duration_s=88.032) == 10.0,
              "WW-05: the in-bounds union without voice is the raw seconds")
        check(SV.lexical_seconds(words, duration_s=88.032,
                                 voice_intervals=[(0.0, 4.0)]) == 4.0,
              "WW-05: intersected with the measured voice, only 4.0 s counts")

    def test_the_four_floors_are_separate_with_their_own_denominators(self):
        check((SV.LEXICAL_COVERAGE_MIN, SV.WORD_FLOOR_SHARE,
               SV.VOCAL_TIME_FLOOR_SHARE, SV.TEXT_COVERAGE_MIN)
              == (0.70, 0.90, 0.85, 0.98),
              "WW-05: the 0.70 lexical, 0.90 word, 0.85 voice and 0.98 text "
              "floors are four separate numbers")
        ok = SV.text_coverage_gate(["word"] * 100, ["word"] * 98)
        check(ok["verdict"] == "PASS" and ok["approved_n"] == 100
              and ok["text_coverage"] == 0.98,
              "WW-05: 98%% text coverage passes with the approved words as its "
              "own denominator")
        bad = SV.text_coverage_gate(["word"] * 100, ["word"] * 97)
        check(bad["verdict"] == "FAIL",
              "WW-05: 97%% text coverage FAILS the 0.98 floor")


# ---- WW-04: one physical timeline (the module half) ------------------------

class WW04Timeline(unittest.TestCase):

    def test_doubled_timeline_is_refused(self):
        # the shape the lane built: a detector timeline over [0, D] PLUS an
        # aligned overlay over the same audio
        doubled = [{"delivery": "spoken", "start": 0.0, "end": STORED_D},
                   {"delivery": "sung", "start": 3.75, "end": 22.107}]
        r = TG.check_timeline_partition(doubled, STORED_D)
        check(r["verdict"] == "FAIL" and r["reason_code"] == "TIMELINE_NOT_DISJOINT",
              "WW-04: a doubled/overlapping timeline is refused "
              "(TIMELINE_NOT_DISJOINT)")

    def test_duplicate_reversed_out_of_range_and_non_finite_are_refused(self):
        dup = [{"start": 0.0, "end": 44.0}, {"start": 0.0, "end": 44.0}]
        check(TG.check_timeline_partition(dup, STORED_D)["reason_code"]
              == "TIMELINE_NOT_DISJOINT", "WW-04: duplicate segments are refused")
        rev = [{"start": 0.0, "end": 5.0}, {"start": 5.0, "end": 2.0}]
        check(TG.check_timeline_partition(rev, STORED_D)["reason_code"]
              == "TIMELINE_MALFORMED", "WW-04: a reversed timestamp is refused")
        oor = [{"start": 0.0, "end": 200.0}]
        check(TG.check_timeline_partition(oor, STORED_D)["reason_code"]
              == "TIMELINE_MALFORMED", "WW-04: an out-of-range timestamp is refused")
        nan = [{"start": 0.0, "end": float("nan")}]
        check(TG.check_timeline_partition(nan, STORED_D)["reason_code"]
              == "TIMELINE_MALFORMED", "WW-04: a non-finite timestamp is refused")

    def test_valid_partition_passes_and_the_runtime_is_the_measured_duration(self):
        good = [{"delivery": "none", "start": 0.0, "end": 44.0},
                {"delivery": "sung", "start": 44.0, "end": STORED_D}]
        r = TG.check_timeline_partition(good, STORED_D)
        check(r["verdict"] == "PASS" and r["partition_seconds"] == STORED_D
              and r["runtime_denominator_is_measured_duration"] is True,
              "WW-04: a single disjoint partition of [0, D] passes, runtime = D")

    def test_gap_is_refused(self):
        gap = [{"delivery": "spent", "start": 0.0, "end": 40.0},
               {"delivery": "sung", "start": 44.0, "end": STORED_D}]
        check(TG.check_timeline_partition(gap, STORED_D)["reason_code"]
              == "TIMELINE_GAP", "WW-04: a gap in the partition is refused")

    def test_measure_share_uses_the_measured_duration_and_rejects_a_doubled_one(self):
        segs = [{"delivery": "sung", "start": 0.0, "end": 44.0},
                {"delivery": "none", "start": 44.0, "end": STORED_D}]
        m = SS.measure_share(segs, basis="planned", duration_s=STORED_D)
        check(m["total_seconds"] == STORED_D
              and m["runtime_denominator_is_measured_duration"] is True,
              "WW-04: measure_share uses the MEASURED duration as the denominator")
        doubled = segs + [{"delivery": "sung", "start": 0.0, "end": 44.0}]
        try:
            SS.measure_share(doubled, basis="planned", duration_s=STORED_D)
            check(False, "WW-04: a doubled segment list must be refused")
        except SS.SpokenShareError as e:
            check(e.code == "TIMELINE_NOT_DISJOINT",
                  "WW-04: measure_share refuses a doubled timeline (%s)" % e.code)

    def test_identical_segments_deduplicate_without_changing_the_share(self):
        base = [{"delivery": "spoken", "start": 0.0, "end": 10.0},
                {"delivery": "sung", "start": 10.0, "end": 20.0}]
        dup = base + [{"delivery": "spoken", "start": 0.0, "end": 10.0}]
        a = SS.measure_share(base, basis="planned")
        b = SS.measure_share(dup, basis="planned")
        check(a["spoken_seconds"] == b["spoken_seconds"]
              and a["share"] == b["share"],
              "WW-04: a duplicated annotation leaves the share unchanged")


# ---- WW-13: the words figure and the music-only figure --------------------

class WW13Labels(unittest.TestCase):

    def test_coverage_report_keeps_the_two_labels_apart(self):
        rep = SV.coverage_report(50.416, 8.0)
        check(rep["vocal_words_s"] == 50.416 and rep["music_only_s"] == 8.0
              and rep["runtime_s"] == 58.416
              and rep["words_and_music_are_separate_labels"] is True,
              "WW-13: 50.416 s of words + 8 s of music-only = 58.416 s RUNTIME")

    def test_audit_fails_a_single_conflated_label(self):
        bad = SV.audit_summary_labels({"seconds_of_words": 58.4158})
        check(bad["verdict"] == "FAIL"
              and bad["reason_code"] == "WORDS_AND_MUSIC_UNDER_ONE_LABEL",
              "WW-13: a single 'seconds of words' label that sums music FAILS")
        good = SV.audit_summary_labels(SV.coverage_report(50.416, 8.0))
        check(good["verdict"] == "PASS",
              "WW-13: the two separate labels PASS the audit")

    def test_words_vs_music_is_wired_to_coverage_report(self):
        fig = SV.words_vs_music_figures({"words": {"spoken": 13, "rap": 19, "sung": 69},
                                         "intro_outro_s": 8.0})
        check(fig["music_only_s"] == 8.0 and fig["vocal_words_s"] > 0
              and fig["runtime_s"] == round(fig["vocal_words_s"] + 8.0, 3),
              "WW-13: the summary figures are wired to coverage_report")


# ---- WW-17: first_sung on the approved story line --------------------------

class WW17FirstSung(unittest.TestCase):

    def test_stored_take_fails_the_story_first_sung_measure(self):
        r = SS.check_first_sung_story(22.107, STORED_D, detector_first_sung_s=7.0)
        check(r["verdict"] == "FAIL",
              "WW-17: the stored take (story line 22.107 s, detector 7.0 s) "
              "FAILS the story-based first_sung measure")

    def test_the_owner_band_is_recorded_separately_and_not_tightened(self):
        r = SS.check_first_sung_story(22.107, STORED_D, detector_first_sung_s=7.0)
        expect = SS.judge_gap(round(7.0 / STORED_D * 100.0, 3), SS.FIRST_SUNG_TARGET_PCT)
        check(r["detector"]["verdict"] == expect["verdict"]
              and r["detector"]["band"] == expect["band"]
              and r["band_owner"]["accept_pts"] == 5
              and r["band_owner"]["flag_pts"] == 10,
              "WW-17: the detector's first-sung figure keeps the owner's 5/10 band "
              "as a SEPARATE recorded number (%s)" % r["detector"]["verdict"])

    def test_a_story_line_at_the_target_passes(self):
        r = SS.check_first_sung_story(13.2, STORED_D, detector_first_sung_s=7.0)
        check(r["verdict"] == "PASS",
              "WW-17: a story line at the 15%% target passes the story measure")


def main():
    print("== WFWWU1-U3: story / lexical / timeline ==")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (WW02StoryStart, WW05LexicalCoverage, WW04Timeline,
                WW13Labels, WW17FirstSung):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    unittest.TextTestRunner(verbosity=0).run(suite)
    if FAILURES:
        print("\n%d CHECK(S) FAILED" % len(FAILURES))
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
