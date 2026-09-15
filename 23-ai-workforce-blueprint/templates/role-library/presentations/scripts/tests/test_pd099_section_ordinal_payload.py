"""PD-TEST-099 -- the WIRE payload a section unit receives must carry its
slide-ordinal range, and a payload that cannot carry one must never be paid for.

THE LIVE DEFECT (run pres-operator-1d269693, P4-COPY).

P4-COPY authors ``working/copy/slides_copy.md``, the input ``slides.json`` is
assembled from.  Its paid retry budget was exhausted twice on the SAME reason,
with an unchanged approved input:

    reasons: ["section-01: unit payload carries no ordinal range"]
    paid_attempts: 3, generation: 2, status: exhausted
    (working/work-orders/.dispatch-state/P4-COPY.json)

and one attempt died differently on the same payload:

    "unit returned empty output (completion_tokens=63999, reasoning_tokens=63999
     of max_tokens=64000 -- reasoning is billed INSIDE that budget)"

WHAT THIS FILE IS FOR, AND WHY IT IS NOT ANOTHER HELPER TEST.

PD-TEST-067 already added ``tests/test_pd067_section_join.py``, which asserts
that ``fanout._sections_for_units`` yields eight named sections and that
``dispatcher._section_ordinal_ranges`` returns eight non-sentinel ranges on the
live P3-ARC shape.  Those tests PASS on a payload that is still unrunnable,
because they stop one call short of the wire: neither of them ever builds the
payload a unit is dispatched with.

The two derivations are still separate.  The ENUMERATOR derives the section
LIST (and can name sections from three different sources: the allocation's
``sections`` array, its slots, or the existing ``slides_copy.md`` headings),
while the payload's range is derived by a SECOND lookup of the section NAME
against the slot labels.  Whenever those two disagree the payload carries no
range, and because the refusal lives in the unit VALIDATOR -- which only runs
after the model answers -- the phase pays for every attempt first and refuses
afterwards.  A P4-COPY unit with no range can NEVER pass: ``_reduce_markdown_
sections`` refuses a payload without ``first_ordinal``/``last_ordinal`` too, so
the whole paid retry budget is spent on a unit that is structurally impossible.

So these tests assert the WIRE SHAPE -- the payload the dispatcher actually
dispatches, through the real ``_dispatch_phase_fanout_units`` path with the
paid call stubbed (zero network, zero tokens) -- on every section-list source
the enumerator itself supports:

  * the live P3-ARC shape (``slide_allocations`` + ``arc_section``): the
    PD-TEST-067 repair's own case, pinned here so it cannot regress;
  * the allocation's DECLARED section list (``sections`` -- the enumerator's
    FIRST priority, and the shape its own docstring calls "its declared
    shape"), whose entries declare their own ``slides``;
  * a shape from which no range is derivable at all, which must be refused
    BEFORE any paid call instead of after the money is gone.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import fanout  # noqa: E402

#: The eight (machine label, display title) pairs the live P3-ARC artifact
#: declares: the slots carry the machine label under ``arc_section``, while the
#: artifact's own section list carries the display title under ``name``.
LIVE_SECTIONS = [
    ("opening", "Opening / Priority Stack"),
    ("cost_of_inaction", "Cost of Inaction"),
    ("higher_aim", "Higher Priority Reframe"),
    ("value_anchor", "Value Anchor / Single-Request Deliverable Set"),
    ("urgency", "Honest Urgency / Capacity Order"),
    ("ability_unblock", "Ability Unblock / First Step"),
    ("decision", "Decision / Re-rank Demand"),
    ("trigger", "Action Trigger / Ending"),
]

#: The unit's own range, as it appears in the scope instruction the model reads.
_RANGE_RE = re.compile(r"slides (\d+)-(\d+)")


class FakePhase:
    """Phase-shaped stub: this test never loads a manifest."""

    def __init__(self, pid: str, role: str):
        self.id = pid
        self.owning_role = role
        self.workers = 1
        self.budget_minutes = 5
        self.executor_kind = "agent"


# ---------------------------------------------------------------------------
# Fixtures: run dirs shaped like the live one.
# ---------------------------------------------------------------------------
def _live_slots() -> list:
    """The live ``slide_allocations`` entries, key set taken from the file."""
    return [{
        "slide_number": n,
        "move": n,
        "arc_section": label,
        "move_tag": f"MOVE_{n}",
        "slide_title": f"Slide {n}",
        "content_summary": f"Summary {n}",
        "arc_marks": {"peak": False, "decision_climax": False, "ending": False},
    } for n, (label, _title) in enumerate(LIVE_SECTIONS, start=1)]


def _live_section_entries() -> list:
    """The live ``arc_sections`` entries: ``section_id`` + display ``name`` +
    the section's own ``slides`` list."""
    return [{"section_id": label, "name": title, "slides": [n],
             "function": f"Function {n}"}
            for n, (label, title) in enumerate(LIVE_SECTIONS, start=1)]


def _seed_run(tmp_path: Path, allocation: dict) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "research").mkdir(parents=True)
    (rd / "working" / "work-orders").mkdir(parents=True)
    (rd / "working" / "copy" / "arc_allocation.json").write_text(
        json.dumps(allocation), encoding="utf-8")
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"client": "t", "slide_count": 8}), encoding="utf-8")
    (rd / "working" / "research" / "research_map.json").write_text(
        json.dumps({"m": 1}), encoding="utf-8")
    (rd / "working" / "research" / "brief-01.md").write_text("BRIEF", encoding="utf-8")
    return rd


def _live_allocation() -> dict:
    """Byte-shaped like run pres-operator-1d269693's real P3-ARC artifact:
    ``arc_sections`` (display titles) AND ``slide_allocations`` (machine labels
    + ``slide_number``)."""
    return {
        "artifact": "working/copy/arc_allocation.json",
        "phase": "P3-ARC",
        "slide_count": 8,
        "arc_sections": _live_section_entries(),
        "slide_allocations": _live_slots(),
    }


def _declared_sections_allocation() -> dict:
    """The LIVE artifact with its section list under the key the enumerator
    itself prioritises: ``sections``.  Same eight sections, same declared
    ``slides`` per section, same slots.  Nothing here is invented -- it is the
    live document with the producer's own key spelling, which is exactly the
    drift this seam has to survive."""
    alloc = _live_allocation()
    alloc.pop("arc_sections")
    alloc["sections"] = _live_section_entries()
    return alloc


def _underivable_allocation() -> dict:
    """A section list that declares NO slides, over slots that carry NO arc
    label: no derivation, from any side, can produce a range.  The honest
    answer is a refusal -- before any paid call."""
    return {
        "artifact": "working/copy/arc_allocation.json",
        "phase": "P3-ARC",
        "slide_count": 8,
        "sections": ["Opening", "Body"],
        "slide_allocations": [{"slide_number": n} for n in range(1, 9)],
    }


def _dept(tmp_path: Path, role: str) -> Path:
    dept = tmp_path / "dept"
    r = dept / role
    r.mkdir(parents=True)
    (r / "how-to.md").write_text("SOP")
    return dept


def _stub_model(calls: list):
    """The paid call, stubbed: records the prompt AND the range it declared,
    then answers as an honest model would -- exactly the unit's own range when
    the prompt names one, and the deck when it does not."""

    def fake_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        assert "AUTHORS EXACTLY ONE SECTION" in user_prompt, \
            "a section unit's prompt must carry its one-scope instruction"
        m = _RANGE_RE.search(user_prompt)
        calls.append({"prompt": user_prompt,
                      "range": (int(m.group(1)), int(m.group(2))) if m else None})
        lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1, 8)
        body = "\n".join(f"SLIDE {n}\nHEADLINE {n}\nNOTE {n}"
                         for n in range(lo, hi + 1))
        return body, {"request_id": "stub"}, {"provider": "stub", "model": "stub-1"}

    return fake_dispatch


def _dispatch(rd: Path, tmp_path: Path, calls: list, monkeypatch) -> "D.DispatchResult":
    monkeypatch.setattr(D, "dispatch_complete", _stub_model(calls))
    monkeypatch.setattr(D, "_verify", lambda pid, rdir: (True, []))
    return D._dispatch_phase_fanout_units(
        rd, {"owning_role": "slide-copywriter",
             "produces_artifact": "working/copy/slides_copy.md"},
        dept_root=_dept(tmp_path, "slide-copywriter"),
        phase_obj=FakePhase("P4-COPY", "slide-copywriter"), worker_id="test",
        spec=fanout.parse_fanout_field({"by": "section", "max_units": 12}),
        patterns=["working/copy/slides_copy.md"],
        target=rd / "working" / "copy" / "slides_copy.md", prior_reasons=[])


def _ordinals(text: str):
    return [int(m) for m in re.findall(r"(?im)^\s*SLIDE\s+(\d+)\s*$", text)]


# ===========================================================================
# 1. THE LIVE SHAPE (PD-TEST-067's case): pinned at the WIRE, not the helper.
# ===========================================================================
def test_live_shape_wire_payload_carries_its_own_range(tmp_path, monkeypatch):
    calls: list = []
    rd = _seed_run(tmp_path, _live_allocation())
    res = _dispatch(rd, tmp_path, calls, monkeypatch)

    assert res.status == "ok", res.reasons
    assert len(calls) == 8, "exactly one paid call per section unit"
    # EVERY unit's prompt named ITS OWN range -- never the placeholder text the
    # degenerate payload produces ("its own slide range"), which tells the model
    # nothing and is the shape the live empty-completion ran under.
    # (units dispatch through a pool, so assert the SET, never the completion
    # order)
    assert sorted(c["range"] for c in calls) == [(n, n) for n in range(1, 9)], calls
    for c in calls:
        assert "its own slide range" not in c["prompt"]
    assert _ordinals((rd / "working" / "copy" / "slides_copy.md").read_text()) == \
        list(range(1, 9))


# ===========================================================================
# 2. THE STILL-OPEN CASE: the allocation's DECLARED section list.
# ===========================================================================
def test_declared_section_list_carries_its_own_declared_range(tmp_path, monkeypatch):
    """A section list under ``sections`` declares each section's ``slides``.

    The enumerator names its units from that list (its OWN first priority), so
    the range must come from the SAME entries -- not from a second lookup of
    those names against the slot labels, which is the join that produced the
    live refusal.  Before PD-TEST-099 this paid for every unit and refused
    every one of them AFTERWARDS with ``unit payload carries no ordinal range``.
    """
    calls: list = []
    rd = _seed_run(tmp_path, _declared_sections_allocation())
    res = _dispatch(rd, tmp_path, calls, monkeypatch)

    assert res.status == "ok", res.reasons
    assert not [r for r in res.reasons if "carries no ordinal range" in r], res.reasons
    assert len(calls) == 8, "exactly one paid call per section unit"
    assert sorted(c["range"] for c in calls) == [(n, n) for n in range(1, 9)], calls
    assert _ordinals((rd / "working" / "copy" / "slides_copy.md").read_text()) == \
        list(range(1, 9))


# ===========================================================================
# 3. NO DERIVABLE RANGE: refuse BEFORE the paid call, never after it.
# ===========================================================================
def test_underivable_range_is_refused_before_any_paid_call(tmp_path, monkeypatch):
    """The cost half of the defect.

    A section unit with no ordinal range fails its own contract validator
    unconditionally, so a paid attempt on it can only be refused once the money
    is spent -- the live ledger's three paid attempts on one impossible unit.
    The dispatcher must refuse the fan-out first, and spend nothing.
    """
    calls: list = []
    rd = _seed_run(tmp_path, _underivable_allocation())
    res = _dispatch(rd, tmp_path, calls, monkeypatch)

    assert calls == [], \
        f"a payload that can never validate must not be paid for; paid {calls!r}"
    assert res.status == "error", res
    joined = " ".join(res.reasons)
    assert "no derivable slide-ordinal range" in joined, res.reasons
    assert not (rd / "working" / "copy" / "slides_copy.md").exists()


# ===========================================================================
# 4. THE SEAM ITSELF: the payload builder must carry the enumerator's range.
# ===========================================================================
@pytest.mark.parametrize("label,allocation", [
    ("live-slide_allocations", _live_allocation()),
    ("declared-sections", _declared_sections_allocation()),
])
def test_enumerator_carries_the_range_into_the_unit_payload(
        tmp_path, label, allocation):
    """``enumerate_fanout_items`` -> ``_unit_payload_enrichment``: the range the
    PAYLOAD carries is the range the SECTION declared, for every section-list
    source, with no second join in between."""
    rd = _seed_run(tmp_path, allocation)
    items = fanout.enumerate_fanout_items(
        rd, fanout.parse_fanout_field({"by": "section", "max_units": 12}),
        phase_id="P4-COPY", produces_artifact=["working/copy/slides_copy.md"])
    assert len(items) == 8, f"{label}: expected 8 section units, got {len(items)}"

    seen = []
    for i, item in enumerate(items, start=1):
        payload = D._unit_payload_enrichment(rd, "P4-COPY", item, len(items))
        assert payload["scope"] == "section"
        assert (payload["first_ordinal"], payload["last_ordinal"]) == (i, i), \
            (label, item, payload)
        ok, why = D._validate_copy_section(payload, f"SLIDE {i}\nBODY {i}")
        assert ok, why
        seen.append(i)
    assert seen == list(range(1, 9))
