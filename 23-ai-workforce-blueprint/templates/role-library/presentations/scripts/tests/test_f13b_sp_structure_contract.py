"""Tests for Unit F13b: P-SP-STRUCTURE's contract must be derived PER RUN,
not hardcoded to one live run's own numbers.

THE FAULT (verified against dispatcher.py before this fix, quoted verbatim in
the unit's own dispatch): ARTIFACT_CONTRACTS["P-SP-STRUCTURE"] was a static
string literal baking ONE run's own client-exact slide count (25) and its
scaled per-phase floors (3/3/9/10) directly into a table shared by EVERY
signature-presentation deck this pipeline will ever build. compose_prompt()
inserted that string into the prompt VERBATIM with no substitution
whatsoever -- so a 40-slide client-exact deck, or (the far more common case)
a deck with NO client-exact override at all, which must get the sacred
>=100-slide floor, was told word-for-word to write EXACTLY 25 slides at
floors 3/3/9/10 regardless of its own real numbers.

prove_sp_structure.py (51-signature-presentation/scripts/prove_sp_structure.py)
itself is untouched by this fix and was never the problem: it is fully
dynamic, reading `client_overrode_slide_floor` / `client_exact_slide_count`
off the deck's own copy ledger and scaling each sacred phase floor by
`max(1, round(min_slides * exact / 100))`. This file proves the NEW
dispatcher.py contract-builder (_sp_read_client_exact_count /
_sp_scaled_floor / _sp_structure_contract) derives numbers that agree with
that REAL, unmodified, live prover -- not by re-deriving the same formula in
parallel and hoping the two never drift, but by feeding synthetic deck
ledgers built from dispatcher's OWN stated floors through
prove_sp_structure.verify() itself and asserting the real verdicts (Parts 3
and 4 below import and execute the actual prove_sp_structure.py module).

These tests FAIL against the pre-fix dispatcher.py (see the unit's own final
report for the revert-in-a-scratch-copy proof: reverting dispatcher.py to the
static ARTIFACT_CONTRACTS["P-SP-STRUCTURE"] string makes
test_40_slide_intake_yields_40_not_25 and
test_no_exact_count_yields_sacred_defaults_no_override fail immediately,
since the static string always says "25" / "3 / 3 / 9 / 10" / no matter the
input, and never contains the sacred ">=100" floor language at all).

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_dispatcher_autospawn.py, test_f15_banked_
revalidation.py).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as d  # noqa: E402

DEPT_ROOT = SCRIPTS.parent  # .../role-library/presentations

_PHASE_ORDER = ("avatar", "story", "teaching", "pitch")
_SACRED_FLOORS = {"avatar": 11, "story": 13, "teaching": 36, "pitch": 40}


# ---------------------------------------------------------------------------
# Locate + import the REAL, unmodified, live prove_sp_structure.py -- the
# SAME resolution build_deck.py's own _sp_prover() uses (a sibling
# 51-signature-presentation/scripts/ walked up from this file's ancestors),
# so this test suite never hand-copies or re-derives the prover's own math.
# ---------------------------------------------------------------------------
def _load_real_prover():
    here = SCRIPTS
    for anc in [here] + list(here.parents):
        cand = anc / "51-signature-presentation" / "scripts" / "prove_sp_structure.py"
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("prove_sp_structure_f13b", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    pytest.skip("51-signature-presentation/scripts/prove_sp_structure.py not found "
                "(worktree layout missing the sibling skill dir) -- cannot run the "
                "real-prover cross-check part of this suite")


PROVER = _load_real_prover()
STRUCTURE_LEDGER = PROVER._load_structure(None)


def _make_run_dir(sp_intake: Optional[Dict[str, Any]] = None,
                   intake: Optional[Dict[str, Any]] = None) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="f13b-run-"))
    (tmp / "working" / "copy").mkdir(parents=True)
    if sp_intake is not None:
        (tmp / "working" / "copy" / "sp_intake.json").write_text(json.dumps(sp_intake))
    if intake is not None:
        (tmp / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
    return tmp


def _sp_scale_reference(min_slides: int, exact: int, default_min: int = 100) -> int:
    """Independent transcription of prove_sp_structure.verify()'s CHECK D formula
    (quoted verbatim from that file):
        _sp_scale = exact / default_min
        floor = max(1, int(round(min_slides * _sp_scale)))
    Used ONLY as a second, independent check alongside the real-module
    execution in Parts 3/4 below -- never the sole proof."""
    scale = exact / default_min
    return max(1, int(round(min_slides * scale)))


def _build_deck(floors: Dict[str, int], *, exact_declared: Optional[int],
                 total_slides: Optional[int] = None) -> Dict[str, Any]:
    """Build a deck ledger that clears EVERY prove_sp_structure.py rule except
    it places exactly `floors[phase]` slides in each phase (plus, when
    `total_slides` exceeds sum(floors), the slack is appended to the LAST
    phase so the total hits `total_slides` exactly while every phase still
    clears its own floor -- mirrors prove_sp_structure.py's own
    `_valid_fixture()` shape, parameterized by the floors under test)."""
    counts = dict(floors)
    base_total = sum(counts.values())
    if total_slides is not None and total_slides > base_total:
        counts[_PHASE_ORDER[-1]] += (total_slides - base_total)

    slides = []
    n = 0
    first_of_phase: Dict[str, int] = {}
    for pid in _PHASE_ORDER:
        for _ in range(counts.get(pid, 0)):
            n += 1
            if pid not in first_of_phase:
                first_of_phase[pid] = n
            slides.append({
                "slide": n,
                "phase": pid,
                "label_slide": False,
                "suggested_image": f"scene seed for slide {n}",
                "tags": [],
            })
    by_num = {s["slide"]: s for s in slides}
    for pid, num in first_of_phase.items():
        by_num[num]["label_slide"] = True
    for pid in ("avatar", "story", "pitch"):
        if pid in first_of_phase:
            by_num[first_of_phase[pid]]["tags"] += ["N.E.E.I.T.", "4-Quadrant"]
    if "avatar" in first_of_phase:
        by_num[first_of_phase["avatar"]]["tags"] += ["MOVEMENT", "MESSAGE", "METHODOLOGY"]
    if slides:
        slides[-1]["tags"].append("CASE_STUDY")

    deck: Dict[str, Any] = {
        "deck_type": "signature_presentation",
        "slides": slides,
        "teaching_steps": 5,
        "hook_package": {
            "central_hook": "You were built for more than this.",
            "section_hooks": [
                "See yourself in their struggle.",
                "My lowest day became the map.",
                "Here is the method, one step at a time.",
                "The door is open -- walk through it.",
            ],
        },
    }
    if exact_declared is not None:
        deck["client_overrode_slide_floor"] = True
        deck["client_exact_slide_count"] = exact_declared
    else:
        deck["client_overrode_slide_floor"] = False
    return deck


# ===========================================================================
# Part 1: a 25-slide intake (sp_intake.json path) yields 25 and floors
# 3/3/9/10 -- the case the ORIGINAL hardcoded string got right (it was the
# one live run it was extracted from), proving this fix did not regress it.
# ===========================================================================
class TestTwentyFiveSlideIntake:
    def test_reads_25_from_sp_intake_json(self):
        run_dir = _make_run_dir(sp_intake={
            "client_overrode_slide_floor": True,
            "client_exact_slide_count": 25,
        })
        exact, source = d._sp_read_client_exact_count(run_dir)
        assert exact == 25
        assert "sp_intake.json" in source

    def test_contract_states_25_and_floors_3_3_9_10(self):
        run_dir = _make_run_dir(sp_intake={
            "client_overrode_slide_floor": True,
            "client_exact_slide_count": 25,
        })
        text = d._sp_structure_contract(run_dir)
        assert "client_exact_slide_count: 25" in text
        assert "EXACTLY 25" in text
        assert "`avatar` >= 3 slides" in text
        assert "`story` >= 3 slides" in text
        assert "`teaching` >= 9 slides" in text
        assert "`pitch` >= 10 slides" in text
        # must NOT also claim some other run's number
        assert "client_exact_slide_count: 40" not in text

    def test_dispatcher_floors_agree_with_real_prover_25(self):
        floors = {p: d._sp_scaled_floor(_SACRED_FLOORS[p], 25) for p in _PHASE_ORDER}
        assert floors == {"avatar": 3, "story": 3, "teaching": 9, "pitch": 10}
        deck = _build_deck(floors, exact_declared=25, total_slides=25)
        violations, notes = PROVER.verify(STRUCTURE_LEDGER, deck)
        assert violations == [], f"real prover rejected a deck built from dispatcher's " \
            f"own stated 25-slide floors: {violations}"


# ===========================================================================
# Part 2: a 40-slide intake yields 40 and CORRECTLY-SCALED floors -- THE test
# that fails hardest against the pre-fix dispatcher.py, whose static contract
# said "25" / "3 / 3 / 9 / 10" unconditionally regardless of input.
# ===========================================================================
class TestFortySlideIntake:
    def test_reads_40_from_sp_intake_json(self):
        run_dir = _make_run_dir(sp_intake={
            "client_overrode_slide_floor": True,
            "client_exact_slide_count": 40,
        })
        exact, _source = d._sp_read_client_exact_count(run_dir)
        assert exact == 40

    def test_contract_states_40_not_25_with_correctly_scaled_floors(self):
        run_dir = _make_run_dir(sp_intake={
            "client_overrode_slide_floor": True,
            "client_exact_slide_count": 40,
        })
        text = d._sp_structure_contract(run_dir)
        # THE regression this fix exists for: the old static string ALWAYS
        # said 25 / 3-3-9-10, no matter the input.
        assert "client_exact_slide_count: 25" not in text
        assert "client_exact_slide_count: 40" in text
        assert "EXACTLY 40" in text
        # correctly-scaled floors: avatar 4, story 5, teaching 14, pitch 16
        # (11*0.4=4.4->4, 13*0.4=5.2->5, 36*0.4=14.4->14, 40*0.4=16.0->16)
        assert "`avatar` >= 4 slides" in text
        assert "`story` >= 5 slides" in text
        assert "`teaching` >= 14 slides" in text
        assert "`pitch` >= 16 slides" in text
        # these floors SUM to 39, one short of 40 -- must be described as
        # MINIMUMS (slack), never as a false "must be EXACTLY 4/5/14/16"
        # claim (that claim is only true when the floors sum exactly to the
        # total, which is not the case here).
        assert "slack" in text.lower()

    def test_dispatcher_floors_agree_with_real_prover_40(self):
        floors = {p: d._sp_scaled_floor(_SACRED_FLOORS[p], 40) for p in _PHASE_ORDER}
        assert floors == {"avatar": 4, "story": 5, "teaching": 14, "pitch": 16}
        assert sum(floors.values()) == 39  # one slide of slack under the 40 total
        deck = _build_deck(floors, exact_declared=40, total_slides=40)
        violations, notes = PROVER.verify(STRUCTURE_LEDGER, deck)
        assert violations == [], f"real prover rejected a deck built from dispatcher's " \
            f"own stated 40-slide floors: {violations}"

    def test_underfloor_deck_is_rejected_by_real_prover(self):
        """Proves the stated floors are exact minimums, not generously padded:
        one slide under any floor must trip AF-SP-PHASE-RANGE."""
        floors = {p: d._sp_scaled_floor(_SACRED_FLOORS[p], 40) for p in _PHASE_ORDER}
        under = dict(floors)
        under["teaching"] -= 1
        # keep the total at 40 by adding the missing slide to pitch instead,
        # so ONLY the teaching floor is violated (isolates the assertion).
        under["pitch"] += 1
        deck = _build_deck(under, exact_declared=40, total_slides=40)
        violations, _notes = PROVER.verify(STRUCTURE_LEDGER, deck)
        codes = {c for c, _m in violations}
        assert "AF-SP-PHASE-RANGE" in codes


# ===========================================================================
# Part 3: an intake with NO exact count yields the SACRED defaults and does
# NOT assert an override -- the case that matters most (the old hardcoded
# text would wrongly force 25/3-3-9-10 here too).
# ===========================================================================
class TestNoExactCountYieldsSacredDefaults:
    def test_no_count_anywhere_returns_none(self):
        run_dir = _make_run_dir()  # no sp_intake.json, no intake.json at all
        exact, _source = d._sp_read_client_exact_count(run_dir)
        assert exact is None

    def test_sp_intake_explicitly_false_returns_none(self):
        run_dir = _make_run_dir(sp_intake={"client_overrode_slide_floor": False})
        exact, _source = d._sp_read_client_exact_count(run_dir)
        assert exact is None

    def test_intake_slide_count_says_no_preference_returns_none(self):
        run_dir = _make_run_dir(intake={
            "deck_brief": {"SLIDE_COUNT": "No preference, let the duration math decide"}
        })
        exact, _source = d._sp_read_client_exact_count(run_dir)
        assert exact is None

    def test_contract_states_sacred_defaults_and_no_override(self):
        run_dir = _make_run_dir()
        text = d._sp_structure_contract(run_dir)
        assert "`avatar` >= 11 slides" in text
        assert "`story` >= 13 slides" in text
        assert "`teaching` >= 36 slides" in text
        assert "`pitch` >= 40 slides" in text
        assert ">= 100" in text
        # must NOT INSTRUCT setting an override (the override-case phrasing is
        # "Top-level keys `client_overrode_slide_floor: true` and ..." -- that
        # exact phrase must be absent, distinct from the "Do NOT set" sentence
        # which legitimately mentions the same field name in the negative).
        assert "Top-level keys `client_overrode_slide_floor: true`" not in text
        assert "Do NOT set `client_overrode_slide_floor: true`" in text
        assert "client_exact_slide_count: 25" not in text
        assert "EXACTLY 25" not in text

    def test_dispatcher_floors_agree_with_real_prover_sacred_default(self):
        deck = _build_deck(_SACRED_FLOORS, exact_declared=None, total_slides=100)
        violations, _notes = PROVER.verify(STRUCTURE_LEDGER, deck)
        assert violations == [], f"real prover rejected a deck built at exactly the " \
            f"sacred 11/13/36/40 floors with a 100-slide total: {violations}"

    def test_99_slides_no_override_fails_real_prover_slide_floor(self):
        """Proves the >=100 default is a REAL floor the prover enforces (not just
        prose) -- a 99-slide deck with no override must fail AF-SP-SLIDE-FLOOR."""
        floors = dict(_SACRED_FLOORS)
        floors["pitch"] -= 1  # 40 -> 39, drops total from 100 to 99
        deck = _build_deck(floors, exact_declared=None, total_slides=99)
        violations, _notes = PROVER.verify(STRUCTURE_LEDGER, deck)
        codes = {c for c, _m in violations}
        assert "AF-SP-SLIDE-FLOOR" in codes


# ===========================================================================
# Part 4: a count so small the naive scaled floor would round to 0 -- the
# prover clamps with max(1, ...); dispatcher must match it and never emit a
# 0 floor. exact=4 is the smallest count where exactly one phase (avatar,
# 11*0.04=0.44) needs the clamp while the OTHER three floors are already
# >=1 without it (see the unit's own arithmetic scan in its report).
# ===========================================================================
class TestSmallCountNeverEmitsZeroFloor:
    def test_dispatcher_floor_for_avatar_is_clamped_to_1_not_0(self):
        raw_unclamped = int(round(_SACRED_FLOORS["avatar"] * 4 / 100))
        assert raw_unclamped == 0, "test setup assumption broken: exact=4 no longer " \
            "naturally rounds avatar's floor to 0 -- pick a different exact value"
        floor = d._sp_scaled_floor(_SACRED_FLOORS["avatar"], 4)
        assert floor == 1  # clamped, never 0
        assert floor == _sp_scale_reference(_SACRED_FLOORS["avatar"], 4)

    def test_no_floor_is_ever_zero_for_exact_4(self):
        floors = {p: d._sp_scaled_floor(_SACRED_FLOORS[p], 4) for p in _PHASE_ORDER}
        assert floors == {"avatar": 1, "story": 1, "teaching": 1, "pitch": 2}
        assert all(v >= 1 for v in floors.values())
        assert "0 slides" not in d._sp_structure_contract(
            _make_run_dir(sp_intake={"client_overrode_slide_floor": True,
                                      "client_exact_slide_count": 4})
        )

    def test_dispatcher_avatar_floor_agrees_with_real_prover_check_d_for_exact_4(self):
        """exact=4's floors (1/1/1/2, sum=5) are individually clamp-correct but
        collectively larger than the 4-slide total itself -- genuinely
        infeasible math the client's own number creates, not something this
        contract can paper over (see _sp_structure_contract's floor_sum >
        exact branch). CHECK D and CHECK F are independent in the real
        prover: CHECK D reads ONLY `deck.get(override_count_field)` (here 4)
        to compute its per-phase floors, regardless of the deck's actual
        slide total -- so a deck can legitimately declare
        client_exact_slide_count=4, carry dispatcher's own stated 1/1/1/2
        per-phase counts (5 slides), and prove CHECK D agrees exactly (zero
        AF-SP-PHASE-RANGE violations) while CHECK F independently and
        correctly fails on the total mismatch -- isolating exactly the part
        of the real prover this unit's fix must agree with."""
        floors = {p: d._sp_scaled_floor(_SACRED_FLOORS[p], 4) for p in _PHASE_ORDER}
        deck = _build_deck(floors, exact_declared=4, total_slides=None)  # 5 real slides
        assert len(deck["slides"]) == 5
        violations, _notes = PROVER.verify(STRUCTURE_LEDGER, deck)
        codes = {c for c, _m in violations}
        assert "AF-SP-PHASE-RANGE" not in codes, (
            f"real prover's CHECK D disagreed with dispatcher's stated exact=4 floors "
            f"{floors}: {violations}"
        )
        # CHECK F independently (and correctly) still fails -- 5 real slides vs the
        # declared exact count of 4 -- proving this deck's clean CHECK D is not an
        # accident of some other bug masking a real disagreement.
        assert "AF-SP-SLIDE-FLOOR" in codes

    def test_contract_never_states_a_zero_floor_for_any_of_1_through_10(self):
        for exact in range(1, 11):
            run_dir = _make_run_dir(sp_intake={
                "client_overrode_slide_floor": True,
                "client_exact_slide_count": exact,
            })
            text = d._sp_structure_contract(run_dir)
            assert "0 slides" not in text, f"exact={exact} produced a 0-slide floor"


# ===========================================================================
# Part 5: sourcing priority + the real intake.json key (deck_brief.SLIDE_COUNT,
# free text) as the documented fallback when sp_intake.json has no override.
# ===========================================================================
class TestSourcePriorityAndIntakeJsonFallback:
    def test_sp_intake_json_wins_over_intake_json_when_both_present(self):
        run_dir = _make_run_dir(
            sp_intake={"client_overrode_slide_floor": True, "client_exact_slide_count": 25},
            intake={"deck_brief": {"SLIDE_COUNT": "40"}},
        )
        exact, source = d._sp_read_client_exact_count(run_dir)
        assert exact == 25
        assert "sp_intake.json" in source

    def test_falls_back_to_intake_json_deck_brief_slide_count_free_text(self):
        run_dir = _make_run_dir(intake={
            "deck_brief": {"SLIDE_COUNT": "Exactly 25 slides, no more, no less"}
        })
        exact, source = d._sp_read_client_exact_count(run_dir)
        assert exact == 25
        assert "deck_brief.SLIDE_COUNT" in source

    def test_falls_back_to_intake_json_deck_brief_slide_count_bare_number(self):
        run_dir = _make_run_dir(intake={"deck_brief": {"SLIDE_COUNT": "40"}})
        exact, _source = d._sp_read_client_exact_count(run_dir)
        assert exact == 40

    def test_sp_intake_present_but_no_override_falls_back_to_intake_json(self):
        run_dir = _make_run_dir(
            sp_intake={"client_overrode_slide_floor": False},
            intake={"deck_brief": {"SLIDE_COUNT": "40"}},
        )
        exact, _source = d._sp_read_client_exact_count(run_dir)
        assert exact == 40


# ===========================================================================
# Part 6: audit finding -- ARTIFACT_CONTRACTS carries no static
# "P-SP-STRUCTURE" entry anymore (regression guard: a static re-addition
# would be silently ignored by compose_prompt's special case, but its
# presence would mislead future readers of the table), and no OTHER entry
# in the table contains the same class of defect (a baked run-specific
# number). See the unit's final report for the full manual audit of every
# other key; this only pins the one entry that WAS the defect.
# ===========================================================================
class TestAuditRegressionGuard:
    def test_no_static_sp_structure_entry_in_artifact_contracts(self):
        assert "P-SP-STRUCTURE" not in d.ARTIFACT_CONTRACTS

    def test_compose_prompt_uses_dynamic_contract_for_sp_structure(self):
        run25 = _make_run_dir(sp_intake={
            "client_overrode_slide_floor": True, "client_exact_slide_count": 25})
        run40 = _make_run_dir(sp_intake={
            "client_overrode_slide_floor": True, "client_exact_slide_count": 40})
        _sys25, user25 = d.compose_prompt(
            phase_id="P-SP-STRUCTURE", owning_role="signature-presentation-architect",
            dept_root=DEPT_ROOT, run_dir=run25, order={"phase_id": "P-SP-STRUCTURE"},
            attempt=1, prior_reasons=None)
        _sys40, user40 = d.compose_prompt(
            phase_id="P-SP-STRUCTURE", owning_role="signature-presentation-architect",
            dept_root=DEPT_ROOT, run_dir=run40, order={"phase_id": "P-SP-STRUCTURE"},
            attempt=1, prior_reasons=None)
        assert "client_exact_slide_count: 25" in user25
        assert "client_exact_slide_count: 40" in user40
        assert user25 != user40  # THE proof the contract is no longer static/frozen
