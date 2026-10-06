from __future__ import annotations

"""
presentation_job/arc_slides.py -- THE ONE READER for the deck's slide list.

WHY THIS MODULE EXISTS (PD-TEST-067, 2026-09-15).

FIVE independent readers each re-implemented the same "where is the deck's
slide array?" question, and all five agreed on a shape the PRODUCER does not
emit:

    fanout._slides_for_units            (the fan-out unit enumerator)
    dispatcher._prompt_slide_count      (P4-PROMPT's N + the serial fan-out plan)
    build_deck._count_output_slides     (the REAL coverage/rich-prompt gate)
    craft_judgement._arc_slots          (the AF-DEN density auto-fails)
    build_deck._chk_* / _chk_arc        (P3-ARC's own preflights)

Every one of them looked for the container key ``slots`` | ``allocation`` |
``slides`` and the per-slide ordinal key ``slide`` -- the shape of the repo's
own committed reference artifact
(``51-signature-presentation/examples/golden-quest/working/copy/arc_allocation.json``,
``slots`` + ``slide``, verified by an independent re-derivation in
``ledgers/evidence/U87-GK-25``).

P3-ARC is an AGENT-executed phase whose SOP never pins a JSON key shape, and
on run ``pres-operator-1d269693`` it emitted its 8 slides as
``slide_allocations`` with per-slide ``slide_number`` -- plus ``arc_sections``.
The string ``slide_allocations`` appeared NOWHERE ELSE in the repository, so
no reader could see it. P3-ARC's verifier was
``_verify_json_artifact("working/copy/arc_allocation.json")`` with NO
required_keys -- valid JSON only -- so a structurally valid but wholly
unconsumable artifact was blessed ``done``, and the phase's own preflights
(presence/non-emptiness, arc-section token scans) passed too.

THE LIVE CONSEQUENCE. ``fanout._slides_for_units`` returned ``[]`` (its
first-priority ``working/copy/slides.json`` is absent, and the arc fallback
could not read ``slide_allocations``), so ``_dispatch_phase_fanout_units``
emitted its zero-unit refusal -- correctly, since a fan-out must never invent
a unit -- but that refusal is a byte-identical ``error`` on every tick, and
``record_outcome`` folded 8 of them into DISPATCH_REPEAT_CEILING and parked
P-U-DESIGN-VSL, P-U-DESIGN-SALES, P-U-DESIGN-CHECKOUT and P-STYLE-SPEC
(43 error rows each in the sidecar, paid_attempts 0). Five dependents then
waited on those quarantines forever.

THE FIX, AND WHY IT IS SHAPED THIS WAY. The divergence -- not the refusal --
is the defect, so this module is the ONE place that knows the shape, and
every reader above now asks it. It accepts EVERY shape any producer in this
tree has actually emitted, and it reports "not determinable" (``None``)
SEPARATELY from "determined, and the answer is zero" (``[]``) -- the
distinction the zero-unit refusal needs to stay honest:

  * ``None``  -- no slide array is present/recognisable anywhere. The caller
                 keeps its own established contract for that (a coverage gate
                 defers/refuses; ``_prompt_slide_count`` returns None).
  * ``[]``    -- the artifact IS present and IS a recognised slide array, and
                 it declares zero slides. That is a real, loud defect and
                 every caller must keep failing on it.

A WIDER CONSUMER (reading ``slide_allocations``) was chosen over narrowing the
producer, for three reasons grounded in this tree:

  1. The producer is an LLM. Its SOP does not pin a key shape, so a prompt-only
     change cannot enforce one. Only the verifier can, and that is fixed too
     (``phase_verifiers``' P3-ARC entry): the shape is now validated where it
     is promised, so the NEXT drift fails loudly at P3-ARC instead of silently
     starving four downstream phases.
  2. The live artifact is already blessed ``done``. Narrowing the producer
     would leave the current run stuck behind an artifact no reader accepts.
  3. This tree's own precedent for exactly this defect class is the consumer
     widening to the artifact actually produced -- see the
     ``_verify_converter`` note in ``phase_verifiers.py`` ("This is the gate
     MOVED to the artifact the phase actually produces, per its own SOP --
     not weakened").

WHAT IS DELIBERATELY UNCHANGED. The zero-unit refusal in
``_dispatch_phase_fanout_units`` stays byte-for-byte (the repo's own
``tests/test_fanout_zero_units_ceiling.py`` states it "is CORRECT and stays
byte-for-byte: a fanout spec that enumerates no units must never invent a
unit"). This module changes only WHICH artifacts are readable, never whether
an unreadable/empty one may be papered over.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Container keys, in the order this tree has seen them emitted. The first
#: present LIST wins. ``slots`` is the declared/canonical shape (the
#: golden-quest reference artifact, AF-DEN-3's "arc_allocation.json slots
#: carry slide + arc_section"); ``slide_allocations`` is what the live P3-ARC
#: agent actually wrote on run pres-operator-1d269693 (PD-TEST-067).
SLIDE_LIST_KEYS = ("slots", "allocation", "slides", "slide_allocations")

#: Per-slide ordinal keys this tree has seen, in precedence order. ``slide``
#: is canonical; ``slide_number`` is P3-ARC's live spelling.
SLIDE_ORDINAL_KEYS = ("ordinal", "slide", "slide_number")

#: Per-slide ARC-SECTION label keys this tree has seen, in precedence order.
#: ``arc_section`` is BOTH the canonical spelling (AF-DEN-3: "arc_allocation.json
#: slots carry slide + arc_section") AND the live P3-ARC spelling, so it leads.
#: The remaining three are the legacy keys four readers used to look for -- and
#: looking ONLY for those is precisely what made the section join fail on the
#: live artifact (PD-TEST-067): the slots carried ``arc_section``, every reader
#: asked for ``arc``/``section``/``name``, so `_sections_for_units` collapsed the
#: whole deck to ONE unit named "whole" and `_section_ordinal_ranges` returned
#: (-1,-1) for every section, which is the live 'unit payload carries no ordinal
#: range' refusal. The array key and the label key are the SAME class of defect,
#: so they are fixed in the SAME place.
SLIDE_ARC_LABEL_KEYS = ("arc_section", "arc", "section", "name")

#: The renderer's direct input, in the priority order build_deck.py:4715 and
#: dispatcher.py:3074 already established. NOTE: no phase in the manifest
#: produces this file (it is the manifest's ONE orphan consumed pattern --
#: see find_unproduced_consumed_artifacts); it is tried first only because
#: when it DOES exist it is the file the renderer itself reads.
SLIDES_JSON_CANDIDATES = (
    "working/copy/slides.json",
    "slides.json",
    "working/slides.json",
)

#: P3-ARC's declared output -- the fallback source every reader shares.
ARC_ALLOCATION_REL = "working/copy/arc_allocation.json"

#: Sentinel build_deck._read_json puts in place of an unparseable file. Such
#: a value is "not determinable", never an empty slide list.
_PARSE_ERROR_KEY = "__parse_error__"


def _ordinal_of(slot: Dict[str, Any], position: int) -> int:
    """The declared slide ordinal of one slot, or its 1-based position.

    The positional fallback keeps ORDER honest for a source that carries no
    ordinals at all (a bare list); it never renumbers a slot that declares
    one, so a non-contiguous or out-of-order allocation keeps its own numbers.
    """
    for key in SLIDE_ORDINAL_KEYS:
        value = slot.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return int(value)
    return position


def slots_from_obj(obj: Any) -> Optional[List[Dict[str, Any]]]:
    """The deck's ordered slide slots from ONE already-parsed JSON value.

    Returns ``None`` when NO slide array is present/recognisable ("not
    determinable" -- the caller keeps its own absent-input contract), or the
    list of slot dicts otherwise -- INCLUDING an empty list, which means the
    artifact really does declare zero slides and is a loud defect downstream.

    Every returned slot is a COPY carrying the canonical ordinal under BOTH
    ``ordinal`` and ``slide`` (all other producer keys preserved), so a
    reader written against either spelling -- ``craft_judgement`` reads
    ``slot["slide"]``, the enumerator reads ``ordinal`` -- sees the same
    number for the same artifact. Order is by ordinal.
    """
    if isinstance(obj, list):
        raw: Any = obj
    elif isinstance(obj, dict):
        if _PARSE_ERROR_KEY in obj:
            return None
        raw = None
        for key in SLIDE_LIST_KEYS:
            value = obj.get(key)
            if isinstance(value, list):
                raw = value
                break
        if raw is None:
            return None
    else:
        return None

    slots: List[Dict[str, Any]] = []
    for position, entry in enumerate(raw, start=1):
        slot = dict(entry) if isinstance(entry, dict) else {"slot": entry}
        ordinal = _ordinal_of(slot, position)
        slot["ordinal"] = ordinal
        slot["slide"] = ordinal
        slots.append(slot)
    return sorted(slots, key=lambda s: s["ordinal"])


def slot_label(slot: Any) -> Optional[str]:
    """THE one reader for a slot's ARC-SECTION label.

    Both sides of the section join must agree on this: the enumerator
    (``fanout._sections_for_units``) derives its section NAMES from it, and the
    range reader (``dispatcher._section_ordinal_ranges``) looks those names up
    through it. They previously held two private copies of the key list and
    disagreed about the live artifact; one accessor makes that unrepresentable.

    Returns the stripped label, or None when the slot declares none.
    """
    if not isinstance(slot, dict):
        return None
    for key in SLIDE_ARC_LABEL_KEYS:
        value = slot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def section_names_from_obj(obj: Any) -> Optional[List[str]]:
    """The deck's ordered, de-duplicated ARC-SECTION names from ONE parsed value.

    Derived from the SLOTS (via ``slot_label``) -- deliberately NOT from the
    artifact's top-level ``arc_sections`` list. The live artifact carries both,
    and they are spelled differently: ``arc_sections`` holds display titles
    ("Opening / Priority Stack") while each slot's ``arc_section`` holds the
    machine label ("opening"). Deriving names from the top-level list would
    simply move the join failure one step downstream, because the range reader
    matches against the SLOT label. One source, therefore: the slots.

    Returns None when no slide array is determinable, or when no slot declares
    a label (the caller then keeps its own fallback, e.g. the single
    whole-file unit).
    """
    slots = slots_from_obj(obj)
    if slots is None:
        return None
    names: List[str] = []
    for slot in slots:
        label = slot_label(slot)
        if label is not None and label not in names:
            names.append(label)
    return names or None


def slide_count_from_obj(obj: Any) -> Optional[int]:
    """``len()`` of the recognised slide array, or None when not determinable.

    The whole difference between this and ``len(obj.get("slides") or [])`` is
    the None: a caller that cannot tell "no artifact" from "an artifact that
    declares zero slides" cannot tell a missing dependency from a real bug.
    """
    slots = slots_from_obj(obj)
    return None if slots is None else len(slots)


def _read_json(path: Path) -> Any:
    """Parse one JSON file, or None when it is absent/unreadable/unparseable.

    Callers that need build_deck's ``__parse_error__`` sentinel semantics pass
    their own already-parsed object to ``slots_from_obj`` instead; this is the
    convenience reader for the shared candidate order below.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def load_slots(run_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """The deck's slide slots from the established source priority.

    ``working/copy/slides.json`` (then the two legacy spots) FIRST, because
    when it exists it is the exact file the renderer renders; then
    ``working/copy/arc_allocation.json``. Returns None when neither yields a
    recognisable slide array.
    """
    for rel in SLIDES_JSON_CANDIDATES:
        path = run_dir / rel
        if not path.is_file():
            continue
        slots = slots_from_obj(_read_json(path))
        if slots is not None:
            return slots
    arc = run_dir / ARC_ALLOCATION_REL
    if arc.is_file():
        return slots_from_obj(_read_json(arc))
    return None


def load_slide_count(run_dir: Path) -> Optional[int]:
    """``len()`` of ``load_slots(run_dir)``, or None when not determinable."""
    slots = load_slots(run_dir)
    return None if slots is None else len(slots)


def load_arc_slots(run_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """The arc allocation's own slots, ignoring the slides.json candidates.

    ``craft_judgement``'s AF-DEN checks read the Director's allocation
    specifically -- the density/ladder beats -- so they must NOT be satisfied
    by a slides.json that happens to exist.
    """
    arc = run_dir / ARC_ALLOCATION_REL
    if not arc.is_file():
        return None
    return slots_from_obj(_read_json(arc))
