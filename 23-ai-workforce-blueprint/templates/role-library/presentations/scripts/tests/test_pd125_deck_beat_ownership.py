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
def test_ownership_preserves_the_required_beat_order():
    owner = {}
    for it in _items():
        for b in (_payload(it).get("owned_beats") or []):
            owner[b] = it["ordinal"]
    ordinals = [owner[b] for b in D.DECK_ORDERED_BEATS]
    assert ordinals == sorted(ordinals), (
        "a section owning a later beat must sit after the section owning the "
        f"earlier one, or the arc is inverted by construction: {ordinals}")


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
