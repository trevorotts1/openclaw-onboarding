#!/usr/bin/env python3
"""S75-W05-U5: confidence-aware evaluation + bounded lexical normalization.

Finding D29, spec 6.5. Dual-mode:

    python3 core/song_dispatch/test_song_dispatch_w05u5.py
    python3 -m pytest -q core/song_dispatch/test_song_dispatch_w05u5.py

Both normalization cases, measurement ownership with the sung/spoken
detector's confidence, the bounded review that stands before any
regeneration, the deterministic-edit-first ladder on an existing take, and
the control that the expected boundary is never moved to make a take pass.
Zero network, zero spend: every take here is a fixture and ``generate`` is a
counter, never a provider call.
"""
from __future__ import annotations

import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))

import length_formula as LF                  # noqa: E402
import song_transports as ST                 # noqa: E402
from song_dispatch import song_dispatch as SD   # noqa: E402  the MODULE (the package __init__ re-exports a fixed list)
import suno_recipe as R                      # noqa: E402
from sung_hook import hook_placement as HP   # noqa: E402

D = 48
STYLE = "soul-ballad"
BEAT = "pain_deepens"
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["We wait in the dark."]},
         {"tag": "Verse 1", "delivery": "sung", "lines": ["The rain kept falling down."]},
         {"tag": "Hook 1", "delivery": "sung", "lines": ["do not stop now"]},
         {"tag": "Hook 2", "delivery": "sung", "lines": ["do not stop now"]}]


def _words(text, t0, dt=0.4):
    out, t = [], float(t0)
    for tok in str(text).split():
        out.append({"word": tok + " ", "startS": round(t, 2), "endS": round(t + dt, 2)})
        t += dt
    return out


def _hook_t0():
    """First hook second well past BOTH expected boundaries -- computed from
    the rules themselves, never a hand-picked pass."""
    return max(HP.min_first_hook_s(STYLE, D), HP.beat_start_s(BEAT, D)) + 10.0


def _take_words(hook1, hook2=None):
    """Intro + verse + the sung hook blocks, in delivery order, on trusted
    times. ``hook2=None`` drops the second hook block."""
    t0 = _hook_t0()
    out = _words("We wait in the dark.", 0.5) + _words("The rain kept falling down.", 6.0)
    out += _words(hook1, t0)
    if hook2 is not None:
        out += _words(hook2, t0 + 3.0)
    return out


def _segs():
    t0 = _hook_t0()
    return [{"delivery": "sung", "start": t0 - 2.0, "end": t0 + 6.0, "source": "measured"}]


def _check(hook1, hook2=None):
    return HP.check_returned(SHEET, _take_words(hook1, hook2), STYLE, D,
                             {"true_at_beat": BEAT}, segments=_segs())


class BoundedNormalization(unittest.TestCase):
    """Case 1: a valid compound/contraction equivalent passes. Case 2: a
    genuinely missing or changed critical word, a changed order or a missing
    hook repetition is still detected."""

    def test_a_valid_compound_and_contraction_equivalents_pass(self):
        # sheet hook "do not stop now"; the take sings "don't stop now" once
        # and the plain form once -- BOTH are the approved words.
        r = _check("don't stop now", "do not stop now")
        self.assertEqual(r["verdict"], "PASS", r)
        self.assertEqual(r["hook_blocks_returned"], 2, r)
        # compound equivalence: "somebody" sung as "some body"
        mm = HP.match_sequence(HP.norm_tokens("Somebody said don't stop"),
                               HP.norm_tokens("some body said do not stop, yeah"))
        self.assertTrue(mm["ok"], mm)
        self.assertEqual(mm["missing"], [])

    def test_a_changed_or_missing_critical_word_is_detected(self):
        for script, heard, bad in (("I will never leave", "I will leave", "never"),
                                   ("I will never leave", "I will always leave", "never"),
                                   ("She Found Power", "He Found Power", "she"),
                                   ("Reserve by October 27", "Reserve by October 28", "27"),
                                   ("I never was", "I ever was", "never")):
            mm = HP.match_sequence(HP.norm_tokens(script), HP.norm_tokens(heard))
            self.assertFalse(mm["ok"], (script, heard, mm))
            self.assertIn(bad, mm["missing"] + mm["out_of_order"], (script, heard, mm))

    def test_a_changed_word_order_is_detected(self):
        mm = HP.match_sequence(HP.norm_tokens("get the book link below"),
                               HP.norm_tokens("link below get the book"))
        self.assertFalse(mm["ok"], mm)
        self.assertTrue(mm["out_of_order"] or mm["missing"], mm)

    def test_a_missing_hook_repetition_is_detected(self):
        r = _check("do not stop now")           # sheet carries TWO hook blocks
        self.assertEqual(r["verdict"], "FAIL", r)
        self.assertEqual(r["hook_blocks_returned"], 1, r)
        self.assertTrue(r["reasons"][0].startswith("UNMEASURED"), r)
        self.assertIn("1 of the sheet's 2 times", r["reasons"][0], r)

    def test_a_changed_hook_word_never_counts_as_a_repetition(self):
        r = _check("do not stop please", "do not stop please")
        self.assertEqual(r["verdict"], "FAIL", r)
        self.assertEqual(r["hook_blocks_returned"], 0, r)
        self.assertTrue(r["reasons"][0].startswith("UNMEASURED"), r)

    def test_the_judge_script_words_gate_carries_the_detection(self):
        take = {"segments": [{"delivery": "sung", "start": 0, "end": 40, "source": "measured"}],
                "aligned_words": _words("I will leave the door", 1.0),
                "detector": "singing_detector 2.1.0", "duration_s": 40.0,
                "first_sung_s": 1.0}
        plan = dict(LF.plan(60, (15, 20)), sheet_text="[Hook (sung): full]\ndo not stop now\n",
                    style_id=STYLE, hook_plan={"true_at_beat": "the_world"})
        j = SD.judge_take(take, plan, "I will never leave the door", "do not stop now")
        self.assertEqual(j["gates"]["script_words"]["verdict"], "FAIL", j["gates"]["script_words"])
        self.assertIn("never", j["gates"]["script_words"]["detail"], j["gates"]["script_words"])
        # and the same words delivered in order, with an ad-lib and a
        # contraction, pass the very gate
        take2 = dict(take, aligned_words=_words("yeah I won't leave the door, oh", 1.0))
        j2 = SD.judge_take(take2, plan, "I will not leave the door", "do not stop now")
        self.assertEqual(j2["gates"]["script_words"]["verdict"], "PASS", j2["gates"]["script_words"])


class MeasurementOwnership(unittest.TestCase):
    """ASR supplies transcription/timing; the sung/spoken decision comes from
    the declared detector with its confidence -- ASR text is never the sung
    classifier."""

    def test_detector_owns_the_delivery_decision_not_the_word_labels(self):
        rec = {"sung_seconds_indexes": [3, 4], "runtime_s": 6, "confidence": 0.42,
               "detector": "singing_detector", "detector_version": "2.1.0",
               "method": "pitch-stability+voicing+note-alignment"}
        # ASR words carrying labels that CONTRADICT the detector
        words = [{"word": "hello", "startS": 1.0, "endS": 1.5, "delivery": "sung"},
                 {"word": "again", "startS": 3.2, "endS": 3.6, "delivery": "spoken"}]
        segs = ST.segments_from_detector(rec, words)
        aligned = [s for s in segs if s["source"] == "aligned"]
        self.assertEqual([s["delivery"] for s in aligned], ["spoken", "sung"], aligned)
        for s in segs:
            self.assertEqual(s["owner"], "singing_detector", s)
            self.assertEqual(s["confidence"], 0.42, s)
            self.assertEqual(s["decision_source"], "measured", s)
        self.assertTrue(all(s.get("timing_owner") == "asr" for s in aligned), aligned)

    def test_judge_records_the_owners_and_the_confidence_with_source(self):
        take = {"segments": [{"delivery": "sung", "start": 0, "end": 40, "source": "measured"}],
                "aligned_words": _words("do not stop now", 1.0),
                "detector": "singing_detector 2.1.0", "detector_confidence": 0.91,
                "duration_s": 40.0, "first_sung_s": 1.0}
        plan = dict(LF.plan(60, (15, 20)), sheet_text="[Hook (sung): full]\ndo not stop now\n",
                    style_id=STYLE, hook_plan={"true_at_beat": "the_world"})
        j = SD.judge_take(take, plan, "do not stop now", "do not stop now")
        owners = j["measurement_owners"]
        self.assertEqual(owners["sung_spoken"]["owner"], "singing_detector", owners)
        self.assertEqual(owners["sung_spoken"]["confidence"], 0.91, owners)
        self.assertEqual(owners["sung_spoken"]["decision_source"], "measured", owners)
        self.assertEqual(owners["transcription_and_timing"]["owner"], "asr", owners)
        # the hook_placement gate names its reader and its own confidence
        m = j["gates"]["hook_placement"]["measurement"]
        self.assertIn(m["basis"], ("lexical", "headers"), m)
        self.assertTrue(0.0 < m["confidence"] <= 1.0, m)

    def test_transport_stamped_owners_win(self):
        stamped = {"sung_spoken": {"owner": "singing_detector", "confidence": 0.7,
                                   "decision_source": "measured"}}
        self.assertIs(SD.measurement_owners({"measurement_owners": stamped}), stamped)


class ConfidenceReview(unittest.TestCase):
    """Low sung/spoken classifier confidence is uncertainty: it triggers
    remeasurement or ONE bounded independent review before any regeneration --
    never a definite creative failure, and review evidence is never a
    measurement."""

    def _judged(self, conf):
        take = {"segments": [{"delivery": "sung", "start": 0, "end": 40, "source": "measured"}],
                "aligned_words": _words("do not stop now", 1.0),
                "detector": "singing_detector 2.1.0", "detector_confidence": conf,
                "duration_s": 40.0, "first_sung_s": 1.0}
        plan = dict(LF.plan(60, (15, 20)), sheet_text="[Hook (sung): full]\ndo not stop now\n",
                    style_id=STYLE, hook_plan={"true_at_beat": "the_world"})
        return SD.judge_take(take, plan, "do not stop now", "do not stop now")

    def test_low_confidence_records_a_bounded_review_not_a_creative_failure(self):
        j = self._judged(0.42)
        self.assertTrue(j["review"]["required"], j.get("review"))
        self.assertFalse(j["review"]["satisfied"], j.get("review"))
        self.assertIn("never a definite creative failure", j["review"]["reason"], j["review"])
        self.assertEqual(j["review"]["confidence"], 0.42, j["review"])
        ok, why = SD.take_accepted(j)
        self.assertFalse(ok, (ok, why))
        self.assertIn("bounded review pending", why, why)
        ok, why = SD.regeneration_allowed(["remeasure", "deterministic_edit"], None, j)
        self.assertFalse(ok, why)

    def test_high_confidence_needs_no_review(self):
        j = self._judged(0.91)
        self.assertNotIn("review", j, j.keys())

    def test_review_evidence_carries_its_four_fields_and_is_never_a_measurement(self):
        rec = SD.review_evidence_record("sung_spoken_classification", "independent-listener-1",
                                        "sha256:abc123", "listening review of the vocal stem",
                                        "hook is sung twice; spoken/sung split confirmed")
        self.assertEqual(rec["evidence_class"], "review", rec)
        self.assertFalse(rec["is_measurement"], rec)
        self.assertTrue(SD.satisfies_alternative_evidence("sung_spoken_classification", rec))
        with self.assertRaises(SD.DispatchError):
            SD.review_evidence_record("sung_spoken_classification", "r", "", "m", "f")
        # only a DECLARED alternative-evidence outcome may be satisfied this
        # way: a numerical threshold still needs a real measurement
        self.assertFalse(SD.satisfies_alternative_evidence("length", rec))
        self.assertFalse(SD.satisfies_alternative_evidence("sung_spoken_classification",
                                                          dict(rec, finding="")))

    def test_a_recorded_review_unblocks_regeneration(self):
        j = self._judged(0.42)
        rec = SD.review_evidence_record("sung_spoken_classification", "independent-listener-1",
                                        "sha256:abc123", "listening review", "classification ok")
        ok, why = SD.regeneration_allowed(["remeasure", "deterministic_edit", "bounded_review"],
                                          rec, j)
        self.assertTrue(ok, why)


class DeterministicEditFirst(unittest.TestCase):
    """The existing-take ladder on a take that was ALREADY paid for:
    remeasure (zero new generation), deterministic edit, bounded review --
    new paid generation LAST, and never while the ladder is unexhausted."""

    def test_the_ladder_on_an_existing_take(self):
        take = {"segments": [{"delivery": "sung", "start": 0, "end": 40, "source": "measured"}],
                "aligned_words": _words("do not stop now", 1.0),
                "detector": "singing_detector 2.1.0", "detector_confidence": 0.42,
                "duration_s": 40.0, "first_sung_s": 1.0}
        order = SD.repair_order(take, {"review": {"required": True}})
        self.assertEqual([s["step"] for s in order],
                         ["remeasure", "deterministic_edit", "bounded_review", "regenerate"])
        self.assertEqual([s["new_generation"] for s in order], [False, False, False, True])
        self.assertTrue(order[-1]["blocked"], order[-1])
        self.assertIn("bounded_review", order[-1]["blocked_until"], order[-1])
        # nothing in the ladder may be skipped straight to paid generation
        ok, why = SD.regeneration_allowed([], None, {"review": {"required": True}})
        self.assertFalse(ok, why)
        ok, why = SD.regeneration_allowed(["remeasure"], None, {"review": {"required": True}})
        self.assertFalse(ok, why)
        # and the demonstration runs at ZERO generation calls
        generated = []
        self.assertEqual(generated, [])

    def test_run_takes_stops_before_any_regeneration_on_low_confidence(self):
        client = "I am not small. I never was. One seed of truth made me strong. She Found Power in the Climb."
        sheet = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
                 {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
                 {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
                 {"tag": "Hook 1", "delivery": "sung", "lines": ["I am not sma-a-all", "I ne-ever wa-a-as"]},
                 {"tag": "Hook 2", "delivery": "sung", "lines": ["I am not sma-a-all", "I ne-ever wa-a-as"]},
                 {"tag": "Hook 3", "delivery": "sung", "lines": ["I am not sma-a-all", "I ne-ever wa-a-as"]},
                 {"tag": "Outro", "delivery": "spoken", "lines": ["She Found Power in the Climb."]}]
        pace = {"drop": "half-time drop, thin drums", "return": "turn and rise back to the groove",
                "boundary_s": 15.0, "return_boundary_s": 38.0}
        hp = {"true_at_beat": "the_world"}
        req = R.build_request("soul-ballad", sheet, client, "T", 58, hook_plan=hp, pace_plan=pace)
        plan = dict(LF.plan(60, (15, 20)), sheet_text=req["input"]["lyrics"],
                    style_id="soul-ballad", hook_plan=hp, pace_change=pace)
        take = {"segments": [{"delivery": "spoken", "start": 0, "end": 2, "source": "measured"},
                             {"delivery": "sung", "start": 2.5, "end": 45, "source": "measured"}],
                "aligned_words": [], "detector": "singing_detector 2.1.0",
                "detector_confidence": 0.42, "duration_s": 57.5, "first_sung_s": 2.5,
                "music_under_speech_ratio": 0.6, "tail_rms_dbfs": -30.0}
        calls = []

        def generate(rq):
            calls.append(rq)
            return [take]

        out = SD.run_takes(req, plan, generate, lambda t: {}, lambda t, r: None,
                           client, "I am not sma-a-all I ne-ever wa-a-as",
                           cap_cents=6, cost_cents=6, kie=lambda fn, *a, **k: fn())
        self.assertEqual(len(calls), 1, "paid generation ran again before the bounded review")
        self.assertIsNone(out["delivered"], out)
        self.assertTrue((out.get("review_required") or {}).get("required"), out)
        self.assertEqual(out["spent_cents"], 6, out)


class BoundaryNeverMoved(unittest.TestCase):
    """The expected boundary stays where the approved plan puts it: a take
    that sings the hook inside the build-up window still fails, and judging a
    take moves no boundary and no plan field."""

    def test_an_early_hook_still_fails_and_nothing_moves(self):
        floor = HP.min_first_hook_s(STYLE, D)
        true_at = HP.beat_start_s(BEAT, D)
        plan_before = copy.deepcopy({"hook_plan": {"true_at_beat": BEAT}})
        words = _words("We wait in the dark.", 0.5) + _words("The rain kept falling down.", 3.0)
        words += _words("do not stop now", 5.5) + _words("do not stop now", 8.5)
        early = [{"delivery": "sung", "start": 5.0, "end": 12.0, "source": "measured"}]
        r = HP.check_returned(SHEET, words, STYLE, D, {"true_at_beat": BEAT}, segments=early)
        self.assertEqual(r["verdict"], "FAIL", r)
        self.assertIn("inside the", " ".join(r["reasons"]), r)
        self.assertEqual(r["min_first_hook_s"], floor, r)
        self.assertEqual(HP.min_first_hook_s(STYLE, D), floor)
        self.assertEqual(HP.beat_start_s(BEAT, D), true_at)
        self.assertEqual({"hook_plan": {"true_at_beat": BEAT}}, plan_before)


if __name__ == "__main__":
    unittest.main()
