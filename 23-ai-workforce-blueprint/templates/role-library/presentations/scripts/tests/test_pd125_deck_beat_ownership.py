"""PD-TEST-125 -- DECK-LEVEL ORDERED BEATS MUST BE OWNED BY A NAMED UNIT.

THE DEFECT, measured on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4.
P4-COPY's 8 section units each author ONE section, while the writing engines
require six DECK-LEVEL beats in a fixed order. The unit prompt already carried
the whole requirement (a rebuilt prompt is system 50,954 + user 103,895 chars and
contains `AF-NO-VILLAIN`, `VILLAIN beat`, `<!-- ARC: VILLAIN -->` and the derived
constraint index), and the assembled artifact still had ZERO villain tokens and
only three ARC markers, none of them a story beat -- because the contract states
the beats as whole-deck properties ("must be the FIRST slide that carries either
the VILLAIN prose/marker or the PROMISE prose/marker"), which a section-scoped
author cannot evaluate. The equilibrium is that NO section claims the beat.

THE FIX. Assign each ordered beat to exactly one section, by position, and say so
in that unit's scope instruction -- the same mechanism PD-TEST-098 used for the
design phases' single `[ARCHETYPE` header and single `DO-NOT BLOCK`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import intelligence_engines_check as IEC  # noqa: E402
from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import fanout  # noqa: E402

PHASE = "P4-COPY"


def _items(n: int = 8):
    return [{"key": f"section-{i:02d}", "ordinal": i, "name": f"Section {i}"}
            for i in range(1, n + 1)]


def _payload(item, n=8):
    # run_dir is unused for a section payload without a manifest section range.
    return D._unit_payload_enrichment(Path("."), PHASE, item, n)


# ---------------------------------------------------------------------------
# 1 -- every ordered beat is owned exactly once.
# ---------------------------------------------------------------------------
def test_every_beat_is_owned_exactly_once():
    owned = []
    for it in _items():
        pl = _payload(it)
        for b in (pl.get("owned_beats") or []):
            owned.append(b)
    assert sorted(owned) == sorted(D.DECK_ORDERED_BEATS), (
        f"each ordered beat must be owned exactly once: {owned}")
    assert len(owned) == len(set(owned)), f"a beat was assigned twice: {owned}"


# ---------------------------------------------------------------------------
# 2 -- the assignment PRESERVES THE REQUIRED ORDER.
# ---------------------------------------------------------------------------
def _canonical_beat_order_from_the_verifier():
    """The beat names and order as the JUDGING ENGINE declares them, parsed from
    its own source.

    This is the whole point: an earlier version of this test asserted the
    assignment against `D.DECK_ORDERED_BEATS` -- the same constant the assignment
    reads -- so inverting that constant changed BOTH sides and the test still
    PASSED. The independent review proved that by inverting it in memory. The
    assertion is only meaningful against the VERIFIER's order, because that is
    what the arc has to satisfy."""
    import inspect
    import re as _re
    src = inspect.getsource(IEC.check_narrative_harmony)
    names = _re.findall(r'\("([A-Z_]+)",', src)
    assert names, "could not read the verifier's beats list"
    return names


def test_ownership_preserves_the_required_beat_order():
    """Each beat's owner must sit at a deck position that ASCENDS in the
    VERIFIER's order -- otherwise the assignment inverts the very arc it exists
    to preserve. Measured against `first_ordinal` (the section's real slide
    position), never against the constant being tested."""
    import presentation_job.dispatcher as D2
    canonical = _canonical_beat_order_from_the_verifier()

    real_range = D2._section_payload_range
    D2._section_payload_range = lambda item, run_dir, name: (
        int(item["ordinal"]), int(item["ordinal"]))
    try:
        owner = {}
        for it in _items():
            pl = _payload(it)
            assert pl.get("first_ordinal") == it["ordinal"], pl
            for b in (pl.get("owned_beats") or []):
                owner[b] = pl["first_ordinal"]
    finally:
        D2._section_payload_range = real_range

    assert set(owner) == set(canonical), (
        f"the assignment and the verifier disagree about WHICH beats exist: "
        f"assigned={sorted(owner)} verifier={sorted(canonical)}")
    positions = [owner[b] for b in canonical]
    assert positions == sorted(positions), (
        "a beat the VERIFIER wants earlier is owned by a section that sits LATER "
        f"in the deck, so the assignment inverts the arc: {list(zip(canonical, positions))}")


# ---------------------------------------------------------------------------
# 3 -- a section beyond the beat list owns NONE, and is told nothing.
# ---------------------------------------------------------------------------
def test_sections_beyond_the_beat_list_own_none():
    for it in _items():
        pl = _payload(it)
        if it["ordinal"] > len(D.DECK_ORDERED_BEATS):
            assert not pl.get("owned_beats"), it
            assert D._owned_beat_clause(pl) == "", (
                "a unit that owns no beat must be told NOTHING -- a clause would "
                "invite it to plant a sibling's beat and duplicate it")


# ---------------------------------------------------------------------------
# 4 -- the clause actually reaches the unit (not just the payload).
# ---------------------------------------------------------------------------
def test_the_owner_is_told_it_is_the_sole_owner():
    payload = _payload(_items()[1])          # section-02 -> VILLAIN
    assert payload["owned_beats"] == ["VILLAIN"], payload.get("owned_beats")
    scope = D._unit_scope_text(payload) or ""
    assert "SOLE OWNER" in scope and "VILLAIN" in scope, scope[:200]
    assert "<BEAT>" in scope, "the clause must point at the literal ARC marker form"


# ---------------------------------------------------------------------------
# 5 -- DRIFT GUARD: our names and order are the VERIFIER's names and order.
# ---------------------------------------------------------------------------
def test_beat_names_and_order_match_the_judging_engine():
    """`intelligence_engines_check.check_narrative_harmony` owns the authoritative
    `beats` list. If a beat is renamed or reordered there and not here, the
    assignment silently stops covering what the verifier checks -- which is the
    whole defect class this file exists to close."""
    import inspect
    src = inspect.getsource(IEC.check_narrative_harmony)
    positions = []
    for beat in D.DECK_ORDERED_BEATS:
        assert f'("{beat}"' in src, (
            f"{beat!r} is not named in check_narrative_harmony -- the verifier and "
            "the ownership assignment have diverged")
        positions.append(src.index(f'("{beat}"'))
    assert positions == sorted(positions), (
        "the beats appear in check_narrative_harmony in a different order than "
        f"{D.DECK_ORDERED_BEATS}")


# ---------------------------------------------------------------------------
# 6 -- no assignment for a phase whose verifier does not ask for beats.
# ---------------------------------------------------------------------------
def test_other_phases_get_no_beat_assignment():
    assert "P4-COPY" in D.DECK_BEAT_PHASES
    pl = D._unit_payload_enrichment(Path("."), "P-STYLE-SPEC", _items()[0], 3)
    assert not pl.get("owned_beats"), pl.get("owned_beats")

# ---------------------------------------------------------------------------
# 7 -- PD-TEST-125 CORRECTED: a PITCHLESS deck gets no assignment and its
#      verifier defers, because the contract forbids fabricating these beats.
# ---------------------------------------------------------------------------
def test_pitchless_deck_gets_no_beat_assignment(tmp_path):
    """The contract's FIRST rule: when `intake.json` declares `pitch_included:
    false` for a non-signature deck, commercial ARC beats 'are not applicable and
    must not be fabricated'. Assigning them would order the author to violate
    AF-PITCH-LEAK in order to satisfy AF-NO-VILLAIN -- measured live, where BOTH
    fired on the same copy and no text can satisfy both."""
    rd = tmp_path / "pitchless"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"deck_type": "webinar", "pitch_included": False}))
    for it in _items():
        pl = D._unit_payload_enrichment(rd, PHASE, it, 8)
        assert not pl.get("owned_beats"), (
            f"{it['key']} was assigned {pl.get('owned_beats')} on a PITCHLESS deck")
    assert D._deck_commercial_beats_apply(rd) is False


def test_pitched_deck_still_gets_the_assignment(tmp_path):
    """REGRESSION GUARD for the guard: gating must not switch the feature off for
    the decks the defect was measured on."""
    rd = tmp_path / "pitched"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"deck_type": "webinar", "pitch_included": True}))
    owned = []
    for it in _items():
        owned += (D._unit_payload_enrichment(rd, PHASE, it, 8).get("owned_beats") or [])
    assert sorted(owned) == sorted(D.DECK_ORDERED_BEATS), owned


def test_unset_applicability_keeps_the_assignment_ON(tmp_path):
    """FAIL DIRECTION: a missing/malformed selection must not silently switch the
    commercial engines off -- it keeps today's behaviour so the dedicated
    AF-PITCH-APPLICABILITY-UNSET code is still the thing that reports it."""
    rd = tmp_path / "unset"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"deck_type": "webinar"}))          # no pitch_included at all
    assert D._deck_commercial_beats_apply(rd) is True

