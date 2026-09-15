"""PD-TEST-067 -- the SECTION JOIN must hold on the shape P3-ARC actually emits.

WHY THIS FILE EXISTS SEPARATELY FROM THE SHAPE-CONTRACT TEST.

The first version of the PD-TEST-067 repair fixed the CONTAINER key (the slide
array) and its test asserted that ``arc_slides.load_slots`` returned all eight
slots. That test PASSED while the deck was still unbuildable, because the real
failure was never the container read -- it was the LABEL JOIN between two
readers:

  * ``fanout._sections_for_units`` derives the section NAMES, and
  * ``dispatcher._section_ordinal_ranges`` looks those names up to compute each
    section's contiguous slide-ordinal range.

Both held their own copy of the key list and both asked for
``arc`` / ``section`` / ``name``, while the live artifact's slots carry
``arc_section``. So the enumerator found no names, collapsed the whole deck to a
single unit called ``whole``, and the range reader then matched nothing and
returned the ``(-1, -1)`` sentinel for every section. Downstream that surfaces as
the live refusal ``section-01: unit payload carries no ordinal range``.

A container-key test cannot catch that. These tests assert the JOIN, on a fixture
shaped exactly like the live artifact, so a future drift in either key list fails
here instead of silently starving the deck.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from presentation_job import arc_slides, dispatcher, fanout  # noqa: E402

#: The eight arc labels the live P3-ARC artifact declares, in order.
LIVE_SECTIONS = [
    "opening",
    "cost_of_inaction",
    "higher_aim",
    "value_anchor",
    "urgency",
    "ability_unblock",
    "decision",
    "trigger",
]


def _live_slot(n: int, section: str) -> dict:
    """One slot exactly as run pres-operator-1d269693's P3-ARC wrote it.

    The key set is taken from the live file, verbatim:
    arc_marks, arc_section, content_summary, move, move_tag, slide_number,
    slide_title.  Note it carries NO arc/section/name and NO ordinal.
    """
    return {
        "slide_number": n,
        "move": n,
        "arc_section": section,
        "move_tag": f"MOVE_{n}",
        "slide_title": f"Slide {n}",
        "content_summary": f"Summary {n}",
        "arc_marks": [],
    }


@pytest.fixture()
def live_run(tmp_path: Path) -> Path:
    """A run dir whose arc allocation is byte-shaped like the live artifact."""
    copy = tmp_path / "working" / "copy"
    copy.mkdir(parents=True)
    (copy / "arc_allocation.json").write_text(json.dumps({
        "artifact": "working/copy/arc_allocation.json",
        "phase": "P3-ARC",
        "slide_count": 8,
        # The live artifact carries BOTH of these, with DIFFERENT spellings:
        # the top-level list holds display titles, the slots hold machine labels.
        "arc_sections": ["Opening / Priority Stack", "Cost of Inaction",
                         "Higher Priority Reframe", "Value Anchor",
                         "Honest Urgency", "Ability Unblock",
                         "Decision", "Action Trigger"],
        "slide_allocations": [_live_slot(i + 1, s) for i, s in enumerate(LIVE_SECTIONS)],
    }), encoding="utf-8")
    return tmp_path


def test_container_read_still_works(live_run: Path) -> None:
    """The part the earlier repair got right must not regress."""
    slots = arc_slides.load_slots(live_run)
    assert slots is not None and len(slots) == 8
    assert arc_slides.load_slide_count(live_run) == 8


def test_enumerator_yields_eight_named_sections(live_run: Path) -> None:
    """THE JOIN, side one: the enumerator must NOT collapse the deck to 'whole'."""
    sections = fanout._sections_for_units(live_run)
    assert [s["name"] for s in sections] == LIVE_SECTIONS
    assert len(sections) == 8, (
        "the live artifact must enumerate EIGHT section units; a single unit "
        "named 'whole' is the PD-TEST-067 defect"
    )


def test_range_reader_gives_every_section_a_real_range(live_run: Path) -> None:
    """THE JOIN, side two: every section must get a real ordinal range.

    ``(-1, -1)`` is the no-range sentinel and is what produced the live
    ``unit payload carries no ordinal range`` refusal.
    """
    names = [s["name"] for s in fanout._sections_for_units(live_run)]
    ranges = dispatcher._section_ordinal_ranges(live_run, names)
    assert len(ranges) == 8
    assert (-1, -1) not in [tuple(r) for r in ranges], (
        f"every section must have a real range, got {ranges}"
    )
    assert [tuple(r) for r in ranges] == [(i, i) for i in range(1, 9)]


def test_ranges_cover_every_slide_exactly_once(live_run: Path) -> None:
    """The ranges must tile the deck: no gap, no overlap, no invented slide."""
    names = [s["name"] for s in fanout._sections_for_units(live_run)]
    covered = []
    for first, last in dispatcher._section_ordinal_ranges(live_run, names):
        covered.extend(range(first, last + 1))
    assert sorted(covered) == list(range(1, 9))


def test_display_titles_are_never_used_as_join_keys(live_run: Path) -> None:
    """The trap: deriving names from the top-level ``arc_sections`` titles.

    Those hold "Opening / Priority Stack" while the slots hold "opening", so
    keying off them would move the join failure one step downstream rather than
    fix it.  Name derivation must come from the SLOTS.
    """
    sections = fanout._sections_for_units(live_run)
    assert "Opening / Priority Stack" not in [s["name"] for s in sections]


def test_canonical_slots_shape_still_joins(tmp_path: Path) -> None:
    """No regression for the declared/canonical shape (``slots`` + ``arc``)."""
    copy = tmp_path / "working" / "copy"
    copy.mkdir(parents=True)
    (copy / "arc_allocation.json").write_text(json.dumps({
        "slots": [{"slide": i + 1, "arc": s} for i, s in enumerate(LIVE_SECTIONS)],
    }), encoding="utf-8")
    sections = fanout._sections_for_units(tmp_path)
    assert [s["name"] for s in sections] == LIVE_SECTIONS
    assert (-1, -1) not in [
        tuple(r) for r in
        dispatcher._section_ordinal_ranges(tmp_path, LIVE_SECTIONS)
    ]


def test_absent_allocation_still_reports_not_determinable(tmp_path: Path) -> None:
    """Absence must stay distinguishable from a determined zero."""
    assert arc_slides.load_slots(tmp_path) is None
    assert arc_slides.section_names_from_obj(None) is None
    assert fanout._sections_for_units(tmp_path) == [{"ordinal": 1, "name": "whole"}]
