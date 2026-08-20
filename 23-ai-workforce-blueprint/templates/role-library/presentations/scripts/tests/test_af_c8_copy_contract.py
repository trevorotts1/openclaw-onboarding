"""Tests for the AF-C8 density-ceiling gap in ARTIFACT_CONTRACTS["P4-COPY"].

THE FAULT (verified against dispatcher.py before this fix, and against the
real live-run failure that proved it): P1Q-COPY-QC (the QC Specialist phase,
graded per qc-specialist-presentations.md's AF-C8 doctrine -- there is no
mechanical Python AF-C8 check anywhere in this codebase, confirmed by
`grep -rn AF-C8 --include=*.py` returning zero hits outside dispatcher.py
after this fix) enforces a hard 30-TOTAL-word-per-slide ceiling summed across
every on-slide text field. But ARTIFACT_CONTRACTS["P4-COPY"] -- the ONLY
contract text the Slide Copywriter phase is dispatched with -- never mentioned
AF-C8, "density", "ceiling", or the field names (SUBHEAD/SUPPORTING) needed to
compute the total. The writer was graded on a rule it was never shown.

Live proof (run pres-wave-e-v3-1787240658, 2026-08-20):
working/qc/copy_qc_report.json's triggered_autofails recorded:
  "AF-C8 density ceiling exceeded on slide 20 (34 words vs 30 max; offer-stack
  component list)"
  "AF-C8 density ceiling exceeded on slide 25 (37 words vs 30 max; re-pitch
  recap list)"
Hand-counting that run's real working/copy/slides_copy.md confirms the exact
arithmetic the report cites: slide 20 = HEADLINE(7) + SUBHEAD(4) + 5
SUPPORTING lines(23) = 34; slide 25 = HEADLINE(4) + SUBHEAD(5) + 6 SUPPORTING
lines(28) = 37. In both cases the PRESENTER NOTE field already carried the
same itemized list as narration -- proving the fix (move the enumeration to
PRESENTER NOTE, leave only the tally on-slide) is not a guess but literally
what the live copywriter almost did, just without also stripping the
duplicate list out of the audience-facing SUPPORTING field.

This test proves the fix teaches: (1) the literal AF-C8 code and the 30-word
number in a density-ceiling context: (2) exactly which of THIS contract's own
declared fields count toward the total (HEADLINE, SUBHEAD, SUPPORTING) and
which do not (PRESENTER NOTE, explicitly, since it is spoken narration); (3)
that this is graded downstream by P1Q-COPY-QC as an auto-fail independent of
each field's own individual limits; (4) the practical fix direction for
value-stack/offer-stack/recap slides that overflow.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_dispatcher_autospawn.py, test_f13b_sp_
structure_contract.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as d  # noqa: E402


class TestP4CopyContractTeachesAfC8DensityCeiling:
    def test_contract_exists(self):
        assert "P4-COPY" in d.ARTIFACT_CONTRACTS

    def test_states_the_af_c8_code(self):
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        assert "AF-C8" in text

    def test_states_the_30_word_ceiling_in_a_density_context(self):
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        assert "30" in text
        assert "density" in text.lower()
        assert "ceiling" in text.lower()
        # THE literal number, spelled out near "word" so this cannot be
        # satisfied by an unrelated "30" (e.g. a percentage) landing nearby.
        assert "30 TOTAL words" in text or "30 total words" in text.lower()

    def test_names_which_fields_count_toward_the_total(self):
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        assert "HEADLINE" in text
        assert "SUBHEAD" in text
        assert "SUPPORTING" in text

    def test_explicitly_excludes_presenter_note_from_the_total(self):
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        assert "PRESENTER NOTE" in text
        # Must say PRESENTER NOTE does NOT count -- not merely mention the
        # field name in passing.
        idx = text.find("PRESENTER NOTE")
        window = text[max(0, idx - 200):idx + 400]
        assert "NOT count" in window or "excluded" in window.lower()

    def test_states_it_is_graded_by_p1q_copy_qc_as_an_auto_fail(self):
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        assert "auto-fail" in text.lower()

    def test_states_it_is_independent_of_individual_field_limits(self):
        """The mechanically distinct part of AF-C8: a slide can clear every
        per-field rule and still fail on the SUMMED total."""
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        lowered = text.lower()
        assert "independent" in lowered or "even when" in lowered \
            or "even if" in lowered or "still auto-fail" in lowered

    def test_gives_practical_guidance_for_overflowing_stack_slides(self):
        """value-stack / offer-stack / recap slides that cannot fit their
        component list in 30 words: components belong in PRESENTER NOTE, the
        slide carries the tally."""
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        lowered = text.lower()
        assert "presenter note" in lowered
        assert "tally" in lowered

    def test_cites_the_real_live_run_that_proved_the_gap(self):
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        assert "pres-wave-e-v3-1787240658" in text

    def test_matches_the_live_qc_reports_exact_arithmetic(self):
        """Regression pin: the two real triggered_autofails strings from the
        live run's copy_qc_report.json, quoted verbatim, must be traceable in
        the contract's own cited word counts (34 vs 30, slide 20; 37 vs 30,
        slide 25) -- proves this was not a guessed number."""
        text = d.ARTIFACT_CONTRACTS["P4-COPY"]
        assert "34" in text
        assert "37" in text
        assert "slide 20" in text.lower()
        assert "slide 25" in text.lower()
