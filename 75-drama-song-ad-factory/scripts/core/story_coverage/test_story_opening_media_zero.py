#!/usr/bin/env python3
"""S75-W05-U1 acceptance tests: D10 -- words and music together at time zero
(Skill_75_Universal_Repair_Spec_v1.1 sections 6.1, 15.1; finding D10).

What is pinned here, in acceptance order:

  * the four-second lead-in counterexample NO LONGER PASSES and the wordless
    span is measured FROM ACTUAL DECODED MEDIA TIME ZERO (never the first
    aligned row);
  * untranscribed silence / humming / instrumental initials are measured from
    delivered frame zero and rejected by their own lead kind;
  * rendered-opening verification passes with the stated tolerances (first
    speech onset <= 0.25 s, audible music before speech <= 0.10 s) and fails
    outside them; a prompt saying "no intro" is never evidence;
  * deterministic trim/alignment repair is PROVEN before any new paid
    generation is even listed -- paid generation is last, never first;
  * a low-confidence speech detector triggers ONE bounded independent
    listening review, recorded AS review evidence (reviewer, artifact hash,
    method, finding) and NEVER as a fabricated measurement;
  * both hooks stay distinct (immediate spoken opening attention hook; earned
    Solution Signature Hook never forced into the opening) and the
    no-sung-word-before-ERM rule stays compatible.

Every fixture is INLINE (no media, no network): pure functions over synthetic
rows and synthetic detector evidence. Zero paid calls. The known-good control
runs before every refusal. Run:

    python3 core/story_coverage/test_story_opening_media_zero.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import story_coverage.story_coverage as SV      # noqa: E402 (submodule: the package __init__ does not export _first_aligned_start_s)

PLOT = [["one", "closed", "door", "seed"]]
FAILURES = []


def check(cond, label):
    if cond:
        print("ok   %s" % label)
    else:
        print("FAIL %s" % label)
        FAILURES.append(label)


def _rows(items):
    return [{"word": w, "startS": s, "endS": e} for (w, s, e) in items]


def _plot_at(start_s, words=("one", "closed", "door", "seed"), step=0.4):
    return [(w, start_s + i * step, start_s + i * step + 0.3)
            for i, w in enumerate(words)]


class D10MediaZeroWordlessSpan(unittest.TestCase):
    """The counterexample: a four-second lead-in no longer passes."""

    def test_known_good_control_opens_at_media_zero(self):
        rows = _rows(_plot_at(0.0))
        g = SV.story_start_gate(rows, PLOT, 58.0)
        check(g["verdict"] == "PASS" and g["failed"] == [],
              "D10 control: a story line opening at media zero PASSES")

    def test_four_second_lead_in_no_longer_passes(self):
        rows = _rows(_plot_at(4.0))            # untranscribed lead-in, rows at 4.0
        g = SV.story_start_gate(rows, PLOT, 58.0)
        check(g["verdict"] == "FAIL"
              and "OPENING_VOCALISE_TOO_LONG" in g["failed"],
              "D10: a four-second lead-in FAILS (%r)" % (g["failed"],))
        check(g["opening_wordless_s"] == 4.0
              and g["wordless_span_measured_from_media_zero"] is True
              and g["wordless_span_origin_s"] == 0.0,
              "D10: the wordless span reads 4.0 s measured from media zero "
              "(the old first-aligned-row origin reported 0.0 s)")

    def test_wordless_span_is_measured_from_media_zero_directly(self):
        rows = _rows(_plot_at(4.0))
        span = SV.longest_opening_wordless_s(rows, 4.0)
        check(span == 4.0,
              "D10: longest_opening_wordless_s measures from media zero (%s)" % span)
        # a vocalise lead-in (humming) counts as wordless from delivered frame zero
        hum = _rows([("Oo-oh", 0.5, 3.9)] + _plot_at(4.0))
        check(SV.longest_opening_wordless_s(hum, 4.0) == 4.0,
              "D10: a humming lead-in is wordless opening measured from frame zero")

    def test_untranscribed_initials_are_measured_from_delivered_frame_zero(self):
        rows = _rows(_plot_at(4.0))            # NO row at all before 4.0
        check(SV.classify_wordless_lead(rows) == "untranscribed",
              "D10: an untranscribed initial (silence/humming/instrumental) is "
              "classified untranscribed, never skipped")
        check(SV._first_aligned_start_s(rows) == 4.0
              and SV.story_start_gate(rows, PLOT, 58.0)[
                  "alignment_evidence_starts_s"] == 4.0,
              "D10: the first aligned row is reported as evidence start only, "
              "never as the measurement origin")


class D10RenderedOpening(unittest.TestCase):
    """Decoded-output verification at the spec 6.1 tolerances."""

    def test_control_passes_inside_the_stated_tolerances(self):
        ev = {"first_speech_onset_s": 0.20, "music_before_speech_s": 0.05,
              "first_audible_music_s": 0.15, "speech_onset_confidence": 0.9,
              "lead_kind": "speech"}
        g = SV.rendered_opening_gate(ev)
        check(g["verdict"] == "PASS"
              and g["tolerances"]["first_speech_onset_max_s"] == 0.25
              and g["tolerances"]["music_before_speech_max_s"] == 0.10,
              "D10: words and music at zero within 0.25 s / 0.10 s PASSES")
        at = SV.rendered_opening_gate({"first_speech_onset_s": 0.25,
                                       "music_before_speech_s": 0.10,
                                       "speech_onset_confidence": 0.9})
        check(at["verdict"] == "PASS",
              "D10: exactly at the 0.25 s / 0.10 s tolerances PASSES")

    def test_onset_past_tolerance_fails_and_the_lead_kinds_are_rejected(self):
        late = SV.rendered_opening_gate({"first_speech_onset_s": 0.251,
                                         "music_before_speech_s": 0.0,
                                         "speech_onset_confidence": 0.9})
        check(late["verdict"] == "FAIL" and "SPEECH_ONSET_LATE" in late["failed"],
              "D10: 0.251 s onset FAILS (first speech onset within 0.25 s)")
        mb = SV.rendered_opening_gate({"first_speech_onset_s": 0.05,
                                       "music_before_speech_s": 0.101,
                                       "speech_onset_confidence": 0.9})
        check(mb["verdict"] == "FAIL"
              and "MUSIC_BEFORE_SPEECH_TOO_LONG" in mb["failed"],
              "D10: 0.101 s of audible music before the words FAILS (<= 0.10 s)")
        for kind, code in (("silent_title", "LEAD_IN_SILENT_TITLE"),
                           ("count_in", "LEAD_IN_COUNT_IN"),
                           ("humming", "LEAD_IN_HUMMING"),
                           ("instrumental", "LEAD_IN_INSTRUMENTAL")):
            g = SV.rendered_opening_gate({"first_speech_onset_s": 0.05,
                                          "music_before_speech_s": 0.0,
                                          "lead_kind": kind,
                                          "speech_onset_confidence": 0.9})
            check(g["verdict"] == "FAIL" and code in g["failed"],
                  "D10: a %s lead-in is REJECTED (%s)" % (kind, code))
        hum_rows = _rows([("Oo-oh", 0.2, 4.0)] + _plot_at(4.0))
        g = SV.rendered_opening_gate({}, aligned_words=hum_rows)
        check(g["verdict"] == "FAIL" and "LEAD_IN_HUMMING" in g["failed"],
              "D10: a humming lead-in derived from the rows is rejected")

    def test_four_second_lead_in_cannot_pass_the_rendered_gate_either(self):
        rows = _rows(_plot_at(4.0))
        g = SV.rendered_opening_gate({}, aligned_words=rows)
        check(g["verdict"] == "FAIL" and "SPEECH_ONSET_LATE" in g["failed"]
              and g["onset_source"] == "alignment_upper_bound"
              and g["first_speech_onset_s"] == 4.0,
              "D10: the rendered gate fails the same four-second lead-in from "
              "the alignment upper bound")

    def test_music_evidence_is_derived_and_missing_evidence_never_passes(self):
        derived = SV.rendered_opening_gate(
            {"first_speech_onset_s": 0.05, "first_audible_music_s": 0.0,
             "speech_onset_confidence": 0.9})
        check(derived["verdict"] == "PASS"
              and derived["music_before_speech_s"] == 0.05
              and derived["music_before_source"] == "derived_from_music_onset",
              "D10: music before speech is derived from the measured music onset")
        iv = SV.rendered_opening_gate(
            {"first_speech_onset_s": 0.30,
             "music_intervals": [(0.0, 0.30)],
             "speech_onset_confidence": 0.9})
        check(iv["verdict"] == "FAIL" and iv["music_before_speech_s"] == 0.30
              and "MUSIC_BEFORE_SPEECH_TOO_LONG" in iv["failed"],
              "D10: music_intervals measure the audible music before speech")
        no_music = SV.rendered_opening_gate({"first_speech_onset_s": 0.05,
                                             "speech_onset_confidence": 0.9})
        check(no_music["verdict"] == "UNAVAILABLE"
              and no_music["reason_code"] == "MUSIC_EVIDENCE_UNMEASURED",
              "D10: unmeasured music evidence is UNAVAILABLE, never a pass")
        no_onset = SV.rendered_opening_gate({})
        check(no_onset["verdict"] == "UNAVAILABLE"
              and no_onset["reason_code"] == "ONSET_UNMEASURED",
              "D10: an unmeasured onset is UNAVAILABLE, never a pass")
        late_music = SV.rendered_opening_gate(
            {"first_speech_onset_s": 0.05, "music_before_speech_s": 0.0,
             "first_audible_music_s": 0.5, "speech_onset_confidence": 0.9})
        check(late_music["verdict"] == "FAIL"
              and "MUSIC_NOT_AT_TIME_ZERO" in late_music["failed"],
              "D10: a first music sample at 0.5 s is refused (music at time zero)")

    def test_a_prompt_saying_no_intro_is_not_evidence(self):
        g = SV.rendered_opening_gate({"evidence_kind": "prompt_claim",
                                      "prompt_text": "no intro"})
        check(g["verdict"] == "UNAVAILABLE"
              and g["reason_code"] == "PROMPT_CLAIM_NOT_EVIDENCE",
              "D10: a prompt claim can never verify the rendered opening")


class D10DeterministicRepairFirst(unittest.TestCase):
    """Deterministic trim/alignment repair proven BEFORE any paid generation."""

    def test_proven_projection_and_paid_generation_is_last(self):
        gr = SV.rendered_opening_gate({"first_speech_onset_s": 4.0,
                                       "music_before_speech_s": 0.0,
                                       "speech_onset_confidence": 0.9})
        proof = SV.prove_deterministic_repair(
            gr, {"approved_opening_present": True, "speech_onset_confidence": 0.9})
        check(proof["deterministic_repair_proven"] is True
              and proof["paid_generation_authorized"] is False
              and proof["projected_gate"]["verdict"] == "PASS"
              and proof["measurement_status"] == "repair_projection_not_a_measurement",
              "D10: the deterministic trim/alignment repair is PROVEN before "
              "any paid generation (projection labelled, never a measurement)")
        plan = SV.opening_repair_plan(gr, {"approved_opening_present": True})
        actions = [s["action"] for s in plan["steps"]]
        check(actions[:2] == ["trim_leading_wordless", "align_timeline_and_mix"]
              and actions[-1] == "paid_full_track_generation"
              and plan["deterministic_first"] is True
              and plan["paid_generation_last"] is True
              and plan["paid_generation_authorized_now"] is False,
              "D10: the repair order is deterministic trim/alignment first, "
              "paid generation LAST (%r)" % (actions,))
        check(all(s["kind"] == "deterministic_edit" for s in plan["steps"][:2])
              and "approved opening words and natural articulation"
                  in plan["steps"][0]["preserves"],
              "D10: the deterministic steps preserve the approved opening "
              "words and natural articulation")

    def test_consolidation_path_reconciles_no_separate_spoken_takes(self):
        plan = SV.opening_repair_plan({}, {"approved_opening_present": False})
        rec = SV.NO_SEPARATE_SPOKEN_TAKES_RECONCILED
        check(rec["one_final_consolidated_soundtrack"] is True
              and rec["new_provider_added"] is False
              and rec["character_voice_changed"] is False
              and rec["older_restriction"] == "no separate spoken takes",
              "D10: the no-separate-spoken-takes restriction is reconciled "
              "EXPLICITLY with the one-consolidated-soundtrack outcome")
        step = [s for s in plan["steps"]
                if s["action"] == "consolidate_spoken_opening"][0]
        check(step["kind"] == "authorized_voice_tts_editing"
              and step["new_provider_added"] is False
              and step["character_voice_changed"] is False
              and step["reconciled_restriction"] == "no separate spoken takes",
              "D10: consolidation uses the EXISTING authorized voice/TTS and "
              "editing path -- no new provider, no voice change")
        proof = SV.prove_deterministic_repair({}, {"approved_opening_present": False})
        check(proof["deterministic_repair_proven"] is False
              and proof["next_step"] == "consolidate_spoken_opening",
              "D10: words the take never performed route to consolidation "
              "(trim cannot create words)")


class D10ListeningReviewEvidence(unittest.TestCase):
    """Low confidence -> ONE bounded review, recorded AS review evidence."""

    def test_review_resolves_uncertainty_as_review_evidence(self):
        g = SV.rendered_opening_gate({"first_speech_onset_s": 0.9,
                                      "music_before_speech_s": 0.0,
                                      "speech_onset_confidence": 0.3})
        check(g["verdict"] == "REVIEW_REQUIRED"
              and g["reason_code"] == "LOW_SPEECH_CONFIDENCE"
              and g["next_action"] == "independent_listening_review",
              "D10: a low-confidence speech detector triggers the bounded "
              "listening review, never a fabricated pass")
        req = SV.independent_listening_review_request(g)
        check(req["applicable"] is True and req["bounded"] is True
              and req["max_reviews"] == 1 and req["measurement_claimed"] is False,
              "D10: the review request is bounded (one review) and claims no "
              "measurement")
        review = {"evidence_kind": "review", "reviewer": "qc-listener-1",
                  "artifact_sha256": "abc123", "method": "bounded_listening",
                  "finding": "opening_acceptable"}
        out = SV.apply_review_evidence(g, review)
        check(out["verdict"] == "PASS"
              and out["resolution_evidence"]["evidence_kind"] == "review"
              and out["resolution_evidence"]["reviewer"] == "qc-listener-1"
              and out["numerical_measurement"] is None
              and out["fabricated_measurement"] is False,
              "D10: the review resolves it AS review evidence (reviewer, "
              "artifact hash, method, finding) -- never as a measurement")
        rej = SV.apply_review_evidence(
            g, dict(review, finding="opening_rejected"))
        check(rej["verdict"] == "FAIL"
              and rej["reason_code"] == "REVIEW_REJECTED_OPENING",
              "D10: a rejecting review finding refuses the opening")
        thin = SV.apply_review_evidence(g, {"evidence_kind": "review",
                                            "finding": "opening_acceptable"})
        check(thin["verdict"] == "REVIEW_REQUIRED"
              and thin["review_applicable"] is False,
              "D10: review evidence without reviewer/artifact/method is refused")

    def test_a_missing_measurement_is_never_fabricated_by_a_review(self):
        g = SV.rendered_opening_gate({})
        out = SV.apply_review_evidence(
            g, {"evidence_kind": "review", "reviewer": "qc-listener-1",
                "artifact_sha256": "abc123", "method": "bounded_listening",
                "finding": "opening_acceptable"})
        check(out["verdict"] == "UNAVAILABLE"
              and out["reason_code"] == "ONSET_UNMEASURED"
              and out["review_applicable"] is False,
              "D10: a numerical threshold that needs measurement is never "
              "satisfied by review evidence -- no fabricated measurement")
        req = SV.independent_listening_review_request(g)
        check(req["applicable"] is False,
              "D10: a missing measurement does not even open the review path")


class D10HooksDistinct(unittest.TestCase):
    """Both hooks preserved distinctly; no-sung-word-before-ERM compatible."""

    def test_both_hooks_stay_distinct_and_erm_compatible(self):
        ok = SV.opening_hooks_gate(
            approved_opening_line=["my", "husband", "divorced", "me", "yesterday"],
            solution_signature_words=["i", "rise", "again"],
            solution_signature_first_s=32.0, first_sung_word_s=24.0, erm_s=24.0)
        check(ok["verdict"] == "PASS" and ok["hooks_distinct"] is True
              and ok["no_sung_word_before_erm_compatible"] is True,
              "D10 control: the spoken opening hook and the earned Solution "
              "Signature Hook are distinct and ERM-compatible")
        forced = SV.opening_hooks_gate(
            approved_opening_line=["i", "rise", "again", "today"],
            solution_signature_words=["i", "rise", "again"])
        check(forced["verdict"] == "FAIL"
              and "SOLUTION_SIGNATURE_HOOK_FORCED_INTO_OPENING" in forced["failed"],
              "D10: the earned hook forced into the opening is refused")
        early = SV.opening_hooks_gate(
            approved_opening_line=["my", "husband", "divorced", "me"],
            solution_signature_words=["i", "rise", "again"],
            solution_signature_first_s=1.0)
        check(early["verdict"] == "FAIL"
              and "EARNED_HOOK_APPEARS_IN_OPENING" in early["failed"],
              "D10: the earned hook appearing in the opening window is refused "
              "(it becomes true later)")
        sung = SV.opening_hooks_gate(
            approved_opening_line=["my", "husband", "divorced", "me"],
            first_sung_word_s=10.0, erm_s=24.0)
        check(sung["verdict"] == "FAIL"
              and "SUNG_WORD_BEFORE_ERM" in sung["failed"],
              "D10: a sung word before the ERM is refused (rule stays live)")
        none = SV.opening_hooks_gate()
        check(none["verdict"] == "UNAVAILABLE",
              "D10: no approved opening line is UNAVAILABLE, never a pass")


class D10JudgeSeam(unittest.TestCase):
    """The rendered-opening gate is wired into judge_returned_take."""

    #: a minimal sheet: a spoken opener (non-plot) then the first plot line
    SHEET = "\n".join([
        "[Intro (spoken): close dry voice, plain speech, no melody]",
        "My husband divorced me yesterday",
        "",
        "[Verse 1 (rap): rhythmic rap on the beat, tight metered flow]",
        "one closed door seed truth",
    ])

    def test_rendered_gate_runs_on_the_returned_take(self):
        check("rendered_opening" in SV.GATES,
              "D10: rendered_opening is a declared take-judge gate")
        take = {
            "aligned_words": _rows(_plot_at(0.05)),
            "approved_words": "one closed door seed",
            "observed_words": "one closed door seed",
            "rendered_opening": {"first_speech_onset_s": 0.05,
                                 "music_before_speech_s": 0.0,
                                 "first_audible_music_s": 0.0,
                                 "speech_onset_confidence": 0.9},
            "opening_hooks": {"solution_signature_words": ["i", "rise", "again"],
                              "solution_signature_first_s": 32.0,
                              "first_sung_word_s": 24.0, "erm_s": 24.0},
        }
        out = SV.judge_returned_take(take, {"delivered_s": 58.0}, self.SHEET, 58.0)
        check(out["gates"]["rendered_opening"]["verdict"] == "PASS"
              and out["gates"]["opening_hooks"]["verdict"] == "PASS",
              "D10: the judge runs the rendered-opening and hooks gates")
        bad = dict(take, rendered_opening={"first_speech_onset_s": 4.0,
                                           "music_before_speech_s": 0.0,
                                           "speech_onset_confidence": 0.9})
        out = SV.judge_returned_take(bad, {"delivered_s": 58.0}, self.SHEET, 58.0)
        check(out["verdict"] in ("FAIL", "UNAVAILABLE")
              and out["gates"]["rendered_opening"]["verdict"] == "FAIL"
              and out.get("opening_repair_plan", {}).get("paid_generation_last")
              is True,
              "D10: a four-second lead-in is refused by the judge and the "
              "deterministic repair plan rides with the verdict")
        low = dict(take, rendered_opening={"first_speech_onset_s": 0.5,
                                           "music_before_speech_s": 0.0,
                                           "speech_onset_confidence": 0.2})
        out = SV.judge_returned_take(low, {"delivered_s": 58.0}, self.SHEET, 58.0)
        check(out["verdict"] != "PASS"
              and out["gates"]["rendered_opening"]["verdict"] == "REVIEW_REQUIRED",
              "D10: low confidence blocks PASS pending the bounded review")


def main():
    print("== S75-W05-U1: D10 words and music at time zero ==")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (D10MediaZeroWordlessSpan, D10RenderedOpening,
                D10DeterministicRepairFirst, D10ListeningReviewEvidence,
                D10HooksDistinct, D10JudgeSeam):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    if FAILURES or not result.wasSuccessful():
        print("\n%d CHECK(S) FAILED" % len(FAILURES))
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
