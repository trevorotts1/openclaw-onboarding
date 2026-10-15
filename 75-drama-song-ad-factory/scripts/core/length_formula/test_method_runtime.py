#!/usr/bin/env python3
"""W1-method-song-U3: the method's runtime targets in the ONE length function.

Run: python3 core/length_formula/test_method_runtime.py
  or python3 -m pytest -q core/length_formula
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import length_formula.length_formula as LF  # noqa: E402

#: The offered lengths (SPEC B2): 30 s paid ad; 60/90 s testimonial, lesson and
#: short post; 3/5/7/10 min campaign episode (300 and 420 are KIE lengths).
OFFERED = (30, 60, 90, 120, 180, 300, 420, 600)
#: Golden pins: the SHA-256 of the WHOLE plan, key-sorted, for the lengths the
#: old formula already answered, at base commit f825bbff. ``plan(L)`` without
#: ``method=True`` must still produce exactly that plan -- the method is inert
#: until it is asked for.
GOLDEN = {
    60: "c6eb4883554724b07dfc492dce5bccb7b75e213d551f46d62f9f986bdb9cfd8a",
    90: "7fb5bdf26d339034530f11fedcf75b202f4ca87d53e011f2f55eff537b092b14",
    120: "68bcad344f3cb1e1e8ba716110f3ee34f0f325abbcbc59ce1069487653373922",
    180: "f6c4a914210e23b33cd707e9c700af379091bc6a89b79c4cde251310bcb1f028",
    300: "716652d8abc51b58da481f4ee2743f4d57a6936da17779996b93db376ac5e0e3",
    600: "f26e99b2c5eb7fdce56fece4b18497904b447fb07bb89c5d1b9f2ac226daae4c",
}
#: Method section 7.2's own sentence: the first hook begins at 0:40, 1:00,
#: 1:20, 1:35, 2:00 and 2:45 in its 60/90/120/180/300/600 examples.
METHOD_HOOK_TIMES = {60: 40, 90: 60, 120: 80, 180: 95, 300: 120, 600: 165}


def digest(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()


def test_a_method_is_inert_until_it_is_asked_for():
    for L, want in GOLDEN.items():
        got = digest(LF.plan(L))
        assert got == want, (L, got, want)
        assert "method" not in LF.plan(L), L
        assert "method" not in LF.plan(L, style_id="rnb-flow"), L
    assert "method" not in LF.plan(60, None, "soul-ballad", True)


def test_b_the_section_71_table_is_read_verbatim():
    assert LF.plan(60, method=True)["method"]["erm_window_s"] == [12, 18]
    assert LF.plan(600, method=True)["method"]["erm_window_s"] == [40, 65]
    assert LF.plan(60, method=True)["method"]["backstory_s"] == [4, 7]
    assert LF.plan(60, method=True)["method"]["cta_reserve_s"] == [10, 15]
    assert LF.plan(180, method=True)["method"]["erm_window_s"] == [25, 40]

    doc = LF.method_runtime()
    assert len(doc["lengths"]) == 8, len(doc["lengths"])
    assert set(doc["profiles"]) == {"story", "feed"}, sorted(doc["profiles"])
    by_len = {r["length_s"]: r for r in doc["lengths"]}
    # The two lengths the method's own table does not carry are both marked
    # editorial IN THE DATA FILE, with the reason they exist.
    assert by_len[420]["origin"] == "editorial" and "300 and 600" in by_len[420]["note"]
    assert by_len[30]["origin"] == "editorial" and "Trevor" in by_len[30]["note"]
    for L, row in by_len.items():
        assert sum(row["blocks"].values()) == L, (L, row["blocks"])
    feed = doc["profiles"]["feed"]
    assert feed["attention_opener_s"] == [0, 3]
    assert feed["first_sung_pct_of_delivered"] == 0.15


def test_c_anchors_are_strictly_ordered_at_every_offered_length():
    for L in OFFERED:
        for profile in ("story", "feed"):
            m = LF.plan(L, method=True, profile=profile)["method"]
            chain = (m["backstory_s"][1], m["erm_apex_s"], m["hero_shift_s"],
                     m["hook_from_s"], m["commercial_from_s"], L)
            assert all(chain[i] < chain[i + 1] for i in range(len(chain) - 1)), \
                (L, profile, chain)
            assert m["erm_window_s"][0] <= m["erm_apex_s"] <= m["erm_window_s"][1], \
                (L, profile, m)
            assert m["profile"] == profile
            assert m["total_s"] == L, (L, m["total_s"])
    for L, t in METHOD_HOOK_TIMES.items():
        assert LF.plan(L, method=True)["method"]["hook_from_s"] == t, L
    # 420 (7 minutes, offered 2026-10-13) is the linear interpolation at
    # t = 0.4 between the method's 300 and 600 rows.
    m420 = LF.plan(420, method=True)["method"]
    assert m420["origin"] == "editorial" and m420["erm_apex_s"] == 45.0
    assert m420["hero_shift_s"] == 114.0 and m420["hook_from_s"] == 138.0
    assert m420["commercial_from_s"] == 344.0


def test_d_thirty_seconds_plans_twenty_eight_delivered():
    p30 = LF.plan(30, method=True)
    assert p30["chosen_length_s"] == 30 and p30["delivered_s"] == 28
    assert p30["method"]["erm_window_s"] == [6, 9]
    assert p30["method"]["backstory_s"] == [2, 4]
    assert p30["method"]["commercial_from_s"] == 23.0


def test_e_the_two_pacing_profiles():
    # FEED keeps the method's ORDER and compresses only the clock (SPEC B4).
    for L in OFFERED:
        D = L - 2
        s = LF.plan(L, method=True)["method"]
        f = LF.plan(L, method=True, profile="feed")["method"]
        assert f["backstory_s"] == [0, 3], (L, f)
        assert f["first_sung_by_s"] == round(0.15 * D, 2), (L, f)
        assert f["first_sung_by_s"] < f["hero_shift_s"], (L, f)
        assert (f["hero_shift_s"], f["hook_from_s"], f["commercial_from_s"]) == \
            (s["hero_shift_s"], s["hook_from_s"], s["commercial_from_s"]), L
        # one number for "when the first sung line lands", not two
        assert f["first_sung_by_s"] == LF.plan(L)["first_sung_by_s"], L
    assert LF.plan(30, method=True, profile="feed")["method"]["first_sung_by_s"] == 4.2
    assert LF.plan(90, method=True, profile="feed")["method"]["first_sung_by_s"] == 13.2
    for bad in (None, "", "STORY", "paid"):
        try:
            LF.plan(60, method=True, profile=bad)
        except LF.MethodProfileError:
            pass
        else:
            raise AssertionError("profile %r accepted" % (bad,))


def test_f_the_opener_carries_the_backstory_narration():
    # Conflict C2: a method run's opener may carry the narration the method
    # allows, up to the whole backstory window spoken at SPOKEN_WPS words.
    for L in OFFERED:
        plain, meth = LF.plan(L), LF.plan(L, method=True)
        assert meth["words"]["opener_max"] >= plain["words"]["opener_max"], L
        cap = int(meth["method"]["backstory_s"][1] * LF.SPOKEN_WPS)
        assert meth["words"]["opener_max"] <= cap, (L, meth["words"], cap)
        # the spoken share band still applies: the plan reaches at least as much
        assert meth["words"]["spoken"] >= plain["words"]["spoken"], L
        assert meth["spoken_share_pct_planned"] >= plain["spoken_share_pct_planned"], L
    # 14 spoken words in 58 s (the BSW band) still open with the 3-word cap.
    bsw = LF.plan(60, (15, 20), method=True)
    assert bsw["words"]["opener_max"] == 3 and bsw["words"]["spoken"] == 14, bsw["words"]
    # the rap reservation is untouched by the raised opener
    r_meth, r_plain = LF.plan(90, style_id="rnb-flow", method=True), \
        LF.plan(90, style_id="rnb-flow")
    assert r_meth["rap_s"] == r_plain["rap_s"], (r_meth["rap_s"], r_plain["rap_s"])
    assert r_meth["words"]["rap"] == r_plain["words"]["rap"]
    assert r_meth["lexical_gate"]["verdict"] == r_plain["lexical_gate"]["verdict"] == "PASS"


def test_g_lengths_the_table_does_not_carry():
    for L in (20, 29.5):                      # below the table: fail closed
        try:
            LF.plan(L, method=True)
        except LF.LengthError:
            pass
        else:
            raise AssertionError("method targets at %s s" % (L,))
    odd = LF.plan(150, method=True)["method"]  # between rows: interpolate, say so
    assert odd["origin"] == "interpolated" and odd["interpolated_between_s"] == [120, 180]
    assert LF.plan(75, method=True)["method"]["origin"] == "interpolated"
    over = LF.plan(3600, method=True)["method"]  # past the longest row: mark it
    assert over["origin"] == "clamped" and over["total_s"] == 600


def test_h_the_class_cross_check_still_passes():
    for L in GOLDEN:
        assert LF.class_check(L) == [], (L, LF.class_check(L))
    assert LF.selfcheck()["ok"] is True


ALL = (test_a_method_is_inert_until_it_is_asked_for,
       test_b_the_section_71_table_is_read_verbatim,
       test_c_anchors_are_strictly_ordered_at_every_offered_length,
       test_d_thirty_seconds_plans_twenty_eight_delivered,
       test_e_the_two_pacing_profiles,
       test_f_the_opener_carries_the_backstory_narration,
       test_g_lengths_the_table_does_not_carry,
       test_h_the_class_cross_check_still_passes)

if __name__ == "__main__":
    for one in ALL:
        one()
    print("ok: method_runtime")
