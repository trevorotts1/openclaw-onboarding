#!/usr/bin/env python3
"""S75-W05-U3 tests: canonical duration registry + one constraint policy.

Dual-mode:

    python3 core/suno_recipe/test_duration_policy_u3.py
    python3 -m pytest core/suno_recipe/test_duration_policy_u3.py

Acceptance under test (Skill_75_Universal_Repair_Spec_v1.1 sections 6.2, 6.3;
findings D09, D12):
  * all six durations including the two-minute profile pass through the same
    canonical data;
  * the 62-second-into-60-second case preserves the take with a warning and an
    exact-placement edit path;
  * extreme mismatches force edit or bounded repair with the decision
    classified;
  * scattered contradictory duration tables removed (delegated to THE one
    table; fresh-interpreter import-order proof);
  * the 11-syllable counterexample passes the recipe under the one policy and
    a 9-syllable acceptance cannot be contradicted without a mode-specific
    reason; warnings never become failures.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import suno_recipe as R            # noqa: E402

CLIENT = "I am not small. I never was. One seed of truth made me strong."
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_PLAN = {"true_at_beat": "the_world"}
SIX = (60, 90, 120, 180, 300, 600)


def sheet(long_line=None):
    s = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]}]
    verse = ["One seed of truth made me stro-o-ong,", "One seed is a-all I ne-e-eed,"]
    if long_line:
        verse = [long_line] + verse[1:]
    s.append({"tag": "Verse", "delivery": "sung", "lines": verse})
    for i in range(3):
        s.append({"tag": "Hook %d" % (i + 1), "delivery": "sung", "lines": list(HOOK)})
    s.append({"tag": "Outro", "delivery": "spoken",
              "lines": ["She Found Power in the Climb. Get the book. Link below."]})
    return s


def seg(d, a, b, src="measured"):
    return {"delivery": d, "start": a, "end": b, "source": src}


def la(n):
    return " ".join(["la"] * n)


class DurationRegistry(unittest.TestCase):
    def test_all_six_durations_one_table(self):
        self.assertEqual(R.CANONICAL_DURATION_S, SIX)
        self.assertEqual(tuple(row["seconds"] for row in R.DURATION_REGISTRY), SIX)
        self.assertEqual(R.durations(), SIX)
        for secs in SIX:
            row = R.duration_row(secs)
            self.assertEqual(row["seconds"], secs)
            self.assertEqual(len(row["profiles"]), len(R.SUPPORTED_SHAPES))

    def test_two_minute_profile_passes_same_canonical_data(self):
        # D12 counterexample: drama-9x16-120s must be derivable from the table.
        self.assertIn("drama-9x16-120s", R.profiles())
        self.assertIn("drama-16x9-120s", R.profiles())
        self.assertIn("drama-9x16-120s", R.preflight_profiles())  # W07's feed
        row = R.profile_row("drama-9x16-120s")
        self.assertEqual(row, {"name": "drama-9x16-120s", "shape": "9x16",
                               "seconds": 120, "label": "2 minutes"})
        self.assertEqual(R.profiles_for(120), ("drama-9x16-120s", "drama-16x9-120s"))

    def test_every_shape_every_duration_has_a_profile(self):
        want = {"drama-%s-%ss" % (shape, secs)
                for secs in SIX for shape in R.SUPPORTED_SHAPES}
        self.assertEqual(set(R.profiles()), want)
        self.assertEqual(len(R.profiles()), 12)

    def test_unknown_duration_and_profile_fail_closed(self):
        for bad in (30, 121, "60", None):
            with self.assertRaises(ValueError):
                R.duration_row(bad)
        with self.assertRaises(ValueError):
            R.profile_row("drama-9x16-121s")

    def test_scattered_tables_delegate_to_the_one_table(self):
        # The contract is ONE canonical table VALUE (the tree may load under
        # two module identities in one process), never a second list.
        import music_styles as MS
        import music_styles.music_styles as MSM
        import prompt_templates as PT
        import style_defaults.defaults as D
        import words_fit as W
        self.assertEqual(MSM.OFFERED_LENGTHS_S, R.CANONICAL_DURATION_S)
        self.assertEqual(MS.OFFERED_LENGTHS_S, R.CANONICAL_DURATION_S)
        self.assertEqual(PT.LENGTH_CLASSES_S, R.CANONICAL_DURATION_S)
        self.assertEqual(D.LENGTH_OPTIONS_S, R.CANONICAL_DURATION_S)
        self.assertEqual(W.CARD_LENGTHS_S, SIX)
        self.assertEqual(D.LENGTH_LABELS_S[120], "2 minutes")
        import batch_mode.batch as B
        self.assertEqual(B.LENGTH_VALUES, tuple(R.DURATION_LABELS_S[s] for s in SIX))
        self.assertIn("2 minutes", B.LENGTH_VALUES)  # the dropped label is back
        import intake_preflight.intake as I
        self.assertEqual(I._LENGTH_LABELS["2 minutes"], 120)

    def test_import_order_has_no_cycle(self):
        probes = {
            "music_styles first": "import music_styles as M; "
                                  "assert tuple(M.OFFERED_LENGTHS_S) == %s" % (SIX,),
            "words_fit first": "import words_fit as W; "
                               "assert tuple(W.CARD_LENGTHS_S) == %s" % (SIX,),
            "prompt_templates first": "import prompt_templates as P; "
                                      "assert tuple(P.LENGTH_CLASSES_S) == %s" % (SIX,),
            "style_defaults first": "import style_defaults.defaults as D; "
                                    "assert tuple(D.LENGTH_OPTIONS_S) == %s" % (SIX,),
            "suno_recipe first": "import suno_recipe as R; "
                                 "assert R.CANONICAL_DURATION_S == %s" % (SIX,),
            "intake first": "import intake_preflight.intake as I; "
                            "assert I._LENGTH_LABELS['2 minutes'] == 120",
            "batch first": "import batch_mode.batch as B; "
                           "assert '2 minutes' in B.LENGTH_VALUES",
            "shadowed suno_recipe dir first":
                "import sys; sys.path.insert(0, %r); "
                "import suno_recipe as R; "
                "assert R.CANONICAL_DURATION_S == %s; "
                "import music_styles as M; "
                "assert tuple(M.OFFERED_LENGTHS_S) == %s"
                % (os.path.join(CORE, "suno_recipe"), SIX, SIX),
        }
        for name, code in probes.items():
            with self.subTest(order=name):
                run = subprocess.run(
                    [sys.executable, "-c",
                     "import sys; sys.path.insert(0, %r); %s" % (CORE, code)],
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(run.returncode, 0, "%s: %s%s"
                                 % (name, run.stdout, run.stderr))


class DurationDecision(unittest.TestCase):
    def test_62_for_60_brief_preserved_with_warning(self):
        d = R.judge_duration_correction(62.0, 60)
        self.assertEqual(d["outcome"], R.OUTCOME_WARNING)
        self.assertIsNone(d["correction_class"])     # no correction needed
        self.assertTrue(d["preserve_take"])
        self.assertFalse(d["regenerate"])            # never regenerate a 2 s over
        self.assertIn("62", d["warning"])
        self.assertEqual(d["reason_code"], "DURATION_MEASURED_VARIATION")

    def test_62_into_exact_60_placement_edit_path(self):
        d = R.judge_duration_correction(62.0, 60, placement_limit_s=60)
        self.assertEqual(d["outcome"], R.OUTCOME_WARNING)      # take preserved
        self.assertTrue(d["preserve_take"])
        self.assertEqual(d["correction_class"], R.EDIT_DETERMINISTIC)
        self.assertEqual(d["reason_code"], "DURATION_EXACT_PLACEMENT_EDIT")
        plan = d["edit_plan"]
        self.assertEqual(plan["route"], "assembly")     # the existing path
        self.assertEqual(tuple(plan["protect"]),
                         ("opening", "plot_points", "hook", "cta"))
        self.assertTrue(plan["master_preserved"])
        self.assertEqual(plan["target_s"], 60)

    def test_extreme_mismatch_never_accepted(self):
        d = R.judge_duration_correction(600.0, 60)
        self.assertNotEqual(d["outcome"], R.OUTCOME_WARNING)   # advisory != accept
        self.assertEqual(d["outcome"], R.OUTCOME_REQUIRED)
        self.assertEqual(d["correction_class"], R.EDIT_DETERMINISTIC)
        self.assertTrue(d["preserve_take"])
        self.assertFalse(d["regenerate"])
        self.assertEqual(d["reason_code"], "DURATION_EXTREME_MISMATCH")

    def test_extreme_mismatch_classified_three_ways(self):
        edit = R.judge_duration_correction(600.0, 60, protected_fits=True)
        self.assertEqual(edit["correction_class"], R.EDIT_DETERMINISTIC)
        repair = R.judge_duration_correction(600.0, 60, protected_fits=False,
                                             repair_allowance_remaining=True)
        self.assertEqual(repair["correction_class"], R.EDIT_WITHIN_ALLOWANCE)
        self.assertEqual(repair["outcome"], R.OUTCOME_REQUIRED)
        user = R.judge_duration_correction(600.0, 60, protected_fits=False,
                                           repair_allowance_remaining=False)
        self.assertEqual(user["correction_class"], R.EDIT_USER_CHOICE)
        self.assertEqual(user["outcome"], R.OUTCOME_USER)
        self.assertEqual(set(R.CORRECTION_CLASSES),
                         {R.EDIT_DETERMINISTIC, R.EDIT_WITHIN_ALLOWANCE,
                          R.EDIT_USER_CHOICE})

    def test_unmeasured_duration_is_never_fabricated(self):
        d = R.judge_duration_correction(None, 60)
        self.assertEqual(d["outcome"], R.OUTCOME_REQUIRED)
        self.assertEqual(d["reason_code"], "DURATION_UNMEASURED")
        self.assertTrue(d["preserve_take"])

    def test_within_target_is_ok(self):
        d = R.judge_duration_correction(60.0, 60)
        self.assertEqual(d["outcome"], "ok")
        self.assertIsNone(d["warning"])

    def test_score_take_carries_the_decision_and_warning(self):
        # 62 s take: spoken 13 s (21%), sung of voice 79%, first singing 4.8%.
        take = {"segments": [seg("spoken", 0, 3), seg("sung", 3, 10),
                             seg("spoken", 10, 20), seg("sung", 20, 62)]}
        out = R.score_take(take, length_s=60)
        self.assertEqual(out["verdict"], "FLAG")          # accepted with warning
        self.assertTrue(out["duration_decision"]["preserve_take"])
        self.assertTrue(out["warnings"])                  # measured-duration warn
        self.assertFalse(any("measured duration" in r for r in out["reasons"]),
                         out["reasons"])                  # warnings never in reasons

    def test_score_take_extreme_mismatch_fails_with_classified_decision(self):
        take = {"segments": [seg("spoken", 0, 3), seg("sung", 3, 10),
                             seg("spoken", 10, 20), seg("sung", 20, 600)]}
        out = R.score_take(take, length_s=60)
        self.assertEqual(out["verdict"], "FAIL")          # never accepted as-is
        self.assertTrue(any("DURATION_EXTREME_MISMATCH" in r
                            for r in out["reasons"]), out["reasons"])
        self.assertIn(out["duration_decision"]["correction_class"],
                      R.CORRECTION_CLASSES)

    def test_score_take_exact_placement_edit_path(self):
        take = {"segments": [seg("spoken", 0, 3), seg("sung", 3, 10),
                             seg("spoken", 10, 20), seg("sung", 20, 62)]}
        out = R.score_take(take, length_s=60, placement_limit_s=60)
        self.assertEqual(out["duration_decision"]["reason_code"],
                         "DURATION_EXACT_PLACEMENT_EDIT")
        self.assertEqual(out["duration_decision"]["edit_plan"]["route"], "assembly")


class OneConstraintPolicy(unittest.TestCase):
    def tearDown(self):
        R.set_constraint_policy(None)

    def test_eleven_syllable_counterexample_passes(self):
        # D09: the writer's 11-syllable sung line must pass the RECIPE too.
        s = sheet(long_line=la(11))
        self.assertEqual(R.check_lyric_sheet(s, CLIENT), [])
        out = R.prepare("soul-ballad", s, CLIENT, 58, hook_plan=HOOK_PLAN)
        self.assertFalse(out["exempt"])
        self.assertEqual(out["constraint_policy"], R.CONSTRAINT_POLICY_VERSION)

    def test_nine_syllable_line_not_contradicted(self):
        s = sheet(long_line=la(9))
        self.assertEqual(R.check_lyric_sheet(s, CLIENT), [])

    def test_preferred_band_miss_is_warning_not_failure(self):
        s = sheet(long_line=la(13))
        warns = []
        self.assertEqual(R.check_lyric_sheet(s, CLIENT, warnings_out=warns), [])
        self.assertTrue(any("13 syllables" in w for w in warns), warns)
        out = R.prepare("soul-ballad", s, CLIENT, 58, hook_plan=HOOK_PLAN)
        self.assertTrue(any("13 syllables" in w for w in out["warnings"]),
                        out["warnings"])                 # accepted with warning

    def test_spoken_scene_outside_intro_outro_preserved(self):
        s = sheet()
        s[0]["tag"] = "Desk Scene"                       # spoken, not Intro/Outro
        self.assertEqual(R.check_lyric_sheet(s, CLIENT), [])
        out = R.prepare("soul-ballad", s, CLIENT, 58, hook_plan=HOOK_PLAN)
        self.assertFalse(out["exempt"])

    def test_unreasoned_downstream_contradiction_is_ignored(self):
        R.set_constraint_policy({"sung_line": {"hard_max_syllables": 8}})
        s = sheet(long_line=la(11))
        self.assertEqual(R.check_lyric_sheet(s, CLIENT), [],
                         "an unreasoned hard bound cannot contradict the writer")
        pol = R.constraint_policy()
        self.assertIsNone(pol["sung_line"]["hard_max_syllables"])
        self.assertIn("POLICY_UNREASONED_CONTRADICTION", pol["source"])

    def test_reasoned_hard_bound_is_honored(self):
        R.set_constraint_policy({"mode_specific_reason": "provider meter cap",
                                 "sung_line": {"hard_max_syllables": 8}})
        s = sheet(long_line=la(11))
        errs = R.check_lyric_sheet(s, CLIENT)
        self.assertTrue(any("hard bound" in e for e in errs), errs)

    def test_injected_policy_wins_and_clears(self):
        R.set_constraint_policy({"mode": "unit-test"})
        self.assertEqual(R.constraint_policy()["mode"], "unit-test")
        R.set_constraint_policy(None)
        self.assertEqual(R.constraint_policy()["mode"], "dramatization")

    def test_policy_sources_name_the_w05_u2_wiring(self):
        self.assertTrue(R.POLICY_SOURCES)
        self.assertTrue(all(len(t) == 2 for t in R.POLICY_SOURCES))
        pol = R.constraint_policy()
        self.assertEqual(pol["policy_version"], R.CONSTRAINT_POLICY_VERSION)
        self.assertEqual(pol["sung_line"]["preferred_min_syllables"], 4)
        self.assertEqual(pol["sung_line"]["preferred_max_syllables"], 12)
        self.assertIsNone(pol["spoken_sections"]["allowed_in"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
